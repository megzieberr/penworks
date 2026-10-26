// PenWorks page pictures (U3b). A page's picture (what Claude reads later) is a WebP of the whole page at 1x
// (794 x 1123 page px, landscape the other way round), quality 0.8, made by app.js renderPage, kept in the private
// bucket `snapshots` at <owner uuid>/<page id>.webp, and named on the page row (pages.snapshot_path, snapshot_at).
// The first live page's picture is the note's cover (notes.cover_path), which the note grid shows.
//
// When a page is DUE:
//   (a) its ink changed (ink.js onChange: a stroke drawn, erased, undone, or swapped in from the database), and 4 s have
//       passed since the last change on that page; a push of its strokes landing (store.js onPushed) makes it due too,
//       still 4 s after its last change;
//   (b) at startup and on every `online`: any live page whose updated_at is newer than its snapshot_at, or that has no
//       picture yet and has strokes.
// Rules: never while a gesture runs (wait for the lift, then 4 s); one render at a time, app-wide; one pending picture
// per page (a change while one is on its way just makes the page due again); only online, and only once the page's
// queued strokes are in the database (the picture shows what the database holds). A failed upload waits 2, 5, 10, then
// 30 s (U3a's ladder), or for the next `online`; the console says why once. No dot, no toast, no button.
//
// Staleness is the database's clock pair. The trigger pages_updated_at (0001) sets updated_at = now() on EVERY page
// update, the picture's own update included, so a client time in snapshot_at would always read stale. Instead: the
// page's updated_at is read before the render, and the row is only updated while it still has that value
// (api.setSnapshot), writing snapshot_at = the database's 'now', the same instant the trigger gives updated_at. A stroke
// that lands during the render changes updated_at first: the update finds no row and the page is due again.

const QUIET_MS = 4000;
const BACKOFF = [2000, 5000, 10000, 30000];
const LIFT_POLL = 250;

const cfg = {
  api: null, store: null, ink: null,
  render: null,                // (page, recs or null) -> Promise<Blob>
  idle: () => Promise.resolve(),   // the app's writes and the stroke queue, settled
  owner: () => 'local',
  pages: () => [], page: () => null, note: () => null, pagesOf: () => [], liveNote: () => false,
  onCover: () => {},           // a note's card should show its cover again
};
const due = new Map();         // page id -> the earliest time (ms) it may be drawn
const lastInk = new Map();     // page id -> the time of its last ink change
const coverDirty = new Set();  // note ids whose cover_path has not reached the database yet
let timer = 0, running = false, waitLift = false, holdUntil = 0, tries = 0, told = false;
const stats = { renders: 0, uploads: 0, bytes: 0, renderMs: 0, failures: 0, skipped: 0 };

export function initSnap(o) {
  Object.assign(cfg, o);
  addEventListener('online', () => { holdUntil = 0; scan(); });
}

// ---------------------------------------------------------------- what makes a page due
export function changed(pageId) {
  const t = Date.now();
  lastInk.set(pageId, t);
  due.set(pageId, t + QUIET_MS);
  arm();
}
export function pushed(pageId) {
  due.set(pageId, Math.max(Date.now(), (lastInk.get(pageId) || 0) + QUIET_MS));
  arm();
}
// rule (b), and every note's cover checked against its first page
export function scan() {
  const now = Date.now();
  for (const p of cfg.pages()) {
    if (p.deleted_at || !cfg.liveNote(cfg.note(p.note_id)) || due.has(p.id)) continue;
    if (stale(p)) due.set(p.id, now);
  }
  const notes = new Set(cfg.pages().map((p) => p.note_id));
  notes.forEach((nid) => syncCover(nid));
  arm();
}
// a page with a picture: its updated_at is newer. A page without: it may have strokes (a row never updated since its
// insert has none; the job itself looks before it draws anything).
function stale(p) {
  if (!p.snapshot_at) return !p.created_at || !p.updated_at || p.updated_at !== p.created_at || cfg.store.known(p.id);
  return micros(p.updated_at) > micros(p.snapshot_at);
}
// a timestamptz as microseconds (Supabase gives six decimals, Date.parse keeps three)
function micros(s) {
  const t = Date.parse(s);
  if (Number.isNaN(t)) return 0;
  const m = /\.(\d+)/.exec(s), frac = m ? (m[1] + '000000').slice(3, 6) : '000';
  return t * 1000 + Number(frac);
}

// ---------------------------------------------------------------- the cover: the first live page's picture
export function syncCover(noteId) {
  const n = cfg.note(noteId);
  if (!n) return;
  const first = cfg.pagesOf(noteId)[0], want = first ? (first.snapshot_path || null) : null;
  if ((n.cover_path || null) === want) return;
  n.cover_path = want;
  coverDirty.add(noteId);
  try { cfg.onCover(noteId); } catch (_) { /* the card is only a card */ }
  arm();
}
async function pushCovers() {
  for (const nid of [...coverDirty]) {
    const n = cfg.note(nid);
    if (!n) { coverDirty.delete(nid); continue; }
    const path = n.cover_path || null;
    await cfg.idle();                                          // the note's row is in the database first
    await cfg.api.setCover(nid, path);
    if ((n.cover_path || null) === path) coverDirty.delete(nid);
  }
}

// ---------------------------------------------------------------- the one worker
function arm() {
  clearTimeout(timer); timer = 0;
  if (running) return;                                         // the worker looks again when it stops
  let at = Infinity;
  if (waitLift) at = Date.now() + LIFT_POLL;
  else {
    if (coverDirty.size) at = Date.now();
    for (const t of due.values()) at = Math.min(at, t);
  }
  if (at === Infinity) return;
  if (holdUntil) at = Math.max(at, holdUntil);
  timer = setTimeout(work, Math.max(0, at - Date.now()));
}
function nextDue() {
  const now = Date.now();
  let best = null, bt = Infinity;
  for (const [id, t] of due) if (t <= now && t < bt) { best = id; bt = t; }
  return best;
}
async function work() {
  timer = 0;
  if (running) return;
  running = true;
  try {
    for (;;) {
      if (navigator.onLine === false) break;                   // the `online` event starts it again
      if (Date.now() < holdUntil) break;
      if (coverDirty.size) {
        try { await pushCovers(); }
        catch (e) { fail(e, 'a note cover'); break; }
      }
      const pid = nextDue();
      if (!pid) break;
      if (cfg.ink.busy()) { waitLift = true; break; }
      if (waitLift) {                                          // the pen just lifted: 4 s from now
        waitLift = false;
        const t = Date.now() + QUIET_MS;
        for (const [id, v] of due) due.set(id, Math.max(v, t));
        continue;
      }
      if (await one(pid) === 'failed') break;
    }
  } finally {
    running = false;
    if (waitLift && !cfg.ink.busy()) {                         // lifted while the worker was busy
      waitLift = false;
      const t = Date.now() + QUIET_MS;
      for (const [id, v] of due) due.set(id, Math.max(v, t));
    }
    arm();
  }
}
const idleSlot = () => new Promise((r) => {
  if (typeof requestIdleCallback === 'function') requestIdleCallback(() => r(), { timeout: 1500 });
  else setTimeout(r, 0);
});

async function one(pid) {
  const p = cfg.page(pid);
  if (!p || p.deleted_at || !cfg.liveNote(cfg.note(p.note_id))) { due.delete(pid); return 'skip'; }
  await cfg.idle();                                            // the page's row, then its queued strokes
  if (!due.has(pid) || due.get(pid) > Date.now()) return 'later';          // changed meanwhile: its new time comes
  if (navigator.onLine === false) return 'later';
  if (cfg.ink.busy()) { waitLift = true; return 'later'; }
  due.delete(pid);
  if (cfg.store.pending(pid)) return 'later';                  // not in the database yet: onPushed brings it back
  try {
    const recs = cfg.store.known(pid) ? null : await cfg.api.strokesOf([pid]);   // a page this device has not read
    const count = recs ? recs.length : cfg.ink.strokesOf(pid).length;
    if (!count && !p.snapshot_at) { stats.skipped++; return 'skip'; }   // nothing on it and no picture to replace
    const at = await cfg.api.pageStamp(pid);
    if (!at) return 'skip';                                    // its row is not there (deleted, or not made yet)
    await idleSlot();
    const live = cfg.page(pid);
    if (!live) return 'skip';
    if (cfg.ink.busy() || due.has(pid)) {                      // a gesture began, or the page changed, meanwhile
      if (!due.has(pid)) due.set(pid, Date.now());
      if (cfg.ink.busy()) waitLift = true;
      return 'later';
    }
    stats.renders++;
    const t0 = performance.now();
    const blob = await cfg.render(live, recs);
    stats.renderMs = Math.round(performance.now() - t0);
    const path = `${cfg.owner()}/${pid}.webp`;
    await cfg.api.putSnapshot(path, blob);
    const stamp = await cfg.api.setSnapshot(pid, path, at);
    tries = 0; told = false; holdUntil = 0;
    stats.uploads++; stats.bytes = blob.size;
    if (!stamp) {                                              // a stroke (or a move) landed during the render
      if (!due.has(pid)) due.set(pid, Math.max(Date.now(), (lastInk.get(pid) || 0) + QUIET_MS));
      return 'again';
    }
    const now = cfg.page(pid);
    if (!now) return 'done';
    now.snapshot_path = path; now.snapshot_at = stamp; now.updated_at = stamp;
    const first = cfg.pagesOf(now.note_id)[0];
    if (first && first.id === pid) {
      await cfg.store.coverPut(now.note_id, { path, at: stamp, blob });   // the card needs no download for it
      syncCover(now.note_id);
      try { cfg.onCover(now.note_id); } catch (_) { /* the card is only a card */ }
    }
    return 'done';
  } catch (e) {
    if (!due.has(pid)) due.set(pid, Date.now());
    fail(e, 'a page picture');
    return 'failed';
  }
}
function fail(e, what) {
  stats.failures++;
  holdUntil = Date.now() + BACKOFF[Math.min(tries, BACKOFF.length - 1)];
  tries++;
  if (!told) { told = true; console.warn(`PenWorks: ${what} could not be saved (${(e && e.message) || e}). It is tried again.`); }
}

// ---------------------------------------------------------------- for the tests (window.__pw.snap)
export function snapStats() {
  return { ...stats, due: [...due.keys()], covers: [...coverDirty], running, waitLift, hold: holdUntil ? holdUntil - Date.now() : 0 };
}
