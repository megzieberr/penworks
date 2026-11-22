// PenWorks stroke storage (U3a). Three layers, one set of calls for ink.js:
//   1. a mirror in memory: page id -> its stroke records (seq order). load() reads it synchronously.
//   2. a cache on this device in IndexedDB (penworks.<mode>.<user id>): store `strokes` (key = page id, value = the
//      records array) and store `queue` (numbered keys, value = one op { page_id, removed: [ids], added: [records] }).
//   3. the database (api.strokesOf / api.putStrokes): every change goes up through the queue, oldest first, one op at a
//      time; the queue lives in IndexedDB, so a change made offline (or before a crash) goes up at the next chance.
// No wifi = she keeps working from the device copy; the dot (#saveDot) says saved / saving / waiting / refused.
// A stroke record is the strokes table's row minus owner_id and created_at: { id, page_id, seq, kind, style, data }.
// Strokes from before U3 (localStorage pw.strokes.<page_id>) are taken over the first time their page is read: they go
// into the cache and into the queue (so they reach the database), and the old key goes once the cache holds them.
// U3b: onPushed(pageId) after each op lands (js/snap.js makes the page's picture), known / pending for it, and the note
// covers' device cache (coverGet / coverPut / coverDrop).
// U3d (js/live.js): a row another device wrote comes in through applyRemote (mirror and cache only, nothing queued: the
// database has it already); pageOf finds the page a deleted id was on; echo tells a row this device wrote itself (its own
// push coming back) from someone else's; reconcile is exported for the gap check after a dropped channel.
// U3e: idle() is the tree queue's gate (js/treeq.js): it throws, like a network error, while tree changes still wait, so
// a page's strokes never go up before its row; nudge() starts the push again once the tree queue is empty.
// pw-v9v: a change the server refuses (400 403 404 409 422) is parked, so the rest flows; onNotice(kind) asks app.js
// for one toast ('slow': ink unsent 5 minutes while online; 'parked'); persistent storage is asked for once.

const LEGACY = 'pw.strokes.';
const LOCAL_MARK = 'pw.cache.local';      // local mode only: the twin lives in localStorage, its cache lives with it
const MERGE_MS = 300;                      // two ops on one page this close together become one
const BACKOFF = [2000, 5000, 10000, 30000];
// pw-v9v: a definite no from the server parks the change (kept on this device, out of the queue's way); no answer, 401,
// 408, 429 and 5xx are tried again as before
const NO = new Set([400, 403, 404, 409, 422]);
const FK = '23503', FK_RETRIES = 3;        // a missing page: the first try plus three retries, then refused
const SLOW_MS = 300000;                    // pw-v9v: ink unsent this long while online = one plain toast
const PERSIST = 'pw.persist.asked';        // pw-v9v: navigator.storage.persist() asked once per device
const bySeq = (a, b) => a.seq - b.seq;
const ECHO_MS = 10000;                     // U3d: an event for an id this device changed this recently is its own push coming back

const mirror = new Map();     // page id -> records (seq order); a page is "known" once it is in here
const blind = new Set();      // pages load() was asked for before their cache was read (they were handed [])
const version = new Map();    // page id -> how many changes so far (a reconcile answer older than a change is dropped)
const recheck = new Set();    // pages a reconcile skipped while the queue held their ops: checked again once it drains
const unchecked = new Set();  // pages whose reconcile could not reach the database: checked on the next trigger
const touched = new Map();    // U3d: stroke id -> when this device last added or removed it (store.change)
// pw-v9s: per page, the database's updated_at (its exact text) when this device last read its ink whole and took it in.
// Kept in store `strokes` under STAMP + page id, written in the same transaction as the page's records; any other change
// to the page here drops it. Only pages in the mirror have one in memory; none = read the page.
const STAMP = 'at:';
const stamps = new Map();
let Q = [];                   // the queue, oldest first: { key, page_id, removed, added, t, busy, fk, told }
let nextKey = 1;
// pw-v9v: refused ops (and ops that touch their strokes), oldest first. Kept in store `queue` with parked: true, never
// deleted here; at every start and on `online` they go back to the head of the queue and are tried again.
let parked = [];
const flags = { slow: false, parked: false };   // pw-v9v: which notice is up (onNotice fires when one comes on)
let slowT = null, slowHead = null, slowFor = 0, slowLast = 0;
const cfg = { mode: 'local', api: null, idle: () => Promise.resolve(), onRemote: () => {}, onState: () => {}, onPushed: () => {},
              onNotice: () => {}, slowMs: SLOW_MS };
let dbp = Promise.reject(new Error('store.init has not run'));
dbp.catch(() => {});
let opened = Promise.resolve();
let writes = Promise.resolve();
let pumping = null, retryT = null, tries = 0, state = 'saved';
let coverDb = Promise.reject(new Error('store.init has not run'));   // U3b: the note covers, a database of their own
coverDb.catch(() => {});

// ---------------------------------------------------------------- IndexedDB, a tiny promise helper
function openDb(name) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(name, 1);
    r.onupgradeneeded = () => {
      const db = r.result;
      if (!db.objectStoreNames.contains('strokes')) db.createObjectStore('strokes');
      if (!db.objectStoreNames.contains('queue')) db.createObjectStore('queue', { autoIncrement: true });
    };
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
function dropDb(name) {
  return new Promise((resolve) => {
    const r = indexedDB.deleteDatabase(name);
    r.onsuccess = r.onerror = r.onblocked = () => resolve();
  });
}
// one transaction: fn(stores, out) queues its requests and fills `out` from their onsuccess; resolves with `out`
// once the transaction has committed
function run(names, mode, fn) {
  return dbp.then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(names, mode), out = {};
    fn(Object.fromEntries(names.map((n) => [n, t.objectStore(n)])), out);
    t.oncomplete = () => resolve(out);
    t.onerror = t.onabort = () => reject(t.error);
  }));
}
// every write goes through one chain, in order; resolves true once committed, false when the device would not keep it
function write(fn) {
  const p = writes.then(() => run(['strokes', 'queue'], 'readwrite', fn)).then(() => true,
    (e) => { console.warn('Strokes not kept on this device', e); return false; });
  writes = p;
  return p;
}
const serial = (op) => ({ page_id: op.page_id, removed: op.removed, added: op.added, ...(op.parked ? { parked: true } : {}) });
function keepOp(op) {
  return write((s) => { if (op.key == null) op.key = nextKey++; s.queue.put(serial(op), op.key); });
}
function dropOp(op) {
  return write((s) => { if (op.key != null) s.queue.delete(op.key); });
}
// pages' records and stamps (list of [id, recs, stamp or null]) in one transaction; no stamp = the kept one goes
function keepPages(list) {
  for (const [id, , at] of list) { if (at) stamps.set(id, at); else stamps.delete(id); }
  return write((s) => {
    for (const [id, recs, at] of list) {
      if (recs.length) s.strokes.put(recs, id); else s.strokes.delete(id);
      if (at) s.strokes.put(at, STAMP + id); else s.strokes.delete(STAMP + id);
    }
  });
}
function keepPage(id, recs) { return keepPages([[id, recs, null]]); }
function unstamp(id) { if (stamps.delete(id)) write((s) => { s.strokes.delete(STAMP + id); }); }

// ---------------------------------------------------------------- start
export function init(o) {
  Object.assign(cfg, o);
  const name = `penworks.${o.mode}.${o.userId}`;
  let wipe = Promise.resolve();
  if (o.mode === 'local') {          // ?local=1: a cleared localStorage is a fresh twin database, so its cache starts fresh
    try {
      if (localStorage.getItem(LOCAL_MARK) !== name) {
        wipe = Promise.all([dropDb(name), dropDb(name + '.covers')]);
        localStorage.setItem(LOCAL_MARK, name);
      }
    } catch (_) { /* ignore */ }
  }
  dbp = wipe.then(() => openDb(name));
  dbp.catch((e) => console.warn('No device cache for strokes', e));
  coverDb = wipe.then(() => openCovers(name + '.covers'));
  coverDb.catch(() => { /* no cover cache: the cards download, or show the paper */ });
  // the queue left from last time comes first; ops made before it was read keep their place after it
  opened = writes = writes.then(() => run(['queue'], 'readonly', (s, out) => {
    s.queue.getAll().onsuccess = (e) => { out.vals = e.target.result; };
    s.queue.getAllKeys().onsuccess = (e) => { out.keys = e.target.result; };
  })).then((out) => {
    const old = out.keys.map((key, i) => ({ ...out.vals[i], key, t: 0, busy: false, fk: 0, told: false }));
    nextKey = Math.max(0, ...out.keys) + 1;
    Q = [...old, ...Q];
    for (const op of old) version.set(op.page_id, (version.get(op.page_id) || 0) + 1);
  }, () => {});
  opened.then(() => { if (Q.length) kick(); else show('saved'); });
  if (o.mode === 'local') {          // test hook: a shorter wait before the unsent-ink notice
    try { const v = Number(localStorage.getItem('penworks.local.slowms')); if (v > 0) cfg.slowMs = v; } catch (_) { /* ignore */ }
  }
  if (!slowT) { slowLast = Date.now(); slowT = setInterval(slowTick, Math.max(50, Math.min(10000, cfg.slowMs / 5))); }
  askPersist();
  addEventListener('online', () => { unpark(); trigger(); });
  addEventListener('offline', () => { if (Q.length && !pumping) show('waiting'); });
  addEventListener('focus', trigger);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) trigger(); });
}

// ---------------------------------------------------------------- the four calls ink.js has always used
export function load(pageId) {
  if (!mirror.has(pageId)) {
    const legacy = adopt(pageId);
    if (legacy) return legacy.slice();
    blind.add(pageId);
    return [];
  }
  return mirror.get(pageId).slice();
}

export function save(pageId, strokes) {
  const recs = strokes.slice();
  mirror.set(pageId, recs); blind.delete(pageId);
  keepPage(pageId, recs);
  return true;
}

export function clear(pageId) {
  mirror.delete(pageId); blind.delete(pageId); recheck.delete(pageId); unchecked.delete(pageId); stamps.delete(pageId);
  try { localStorage.removeItem(LEGACY + pageId); } catch (_) { /* ignore */ }
  write((s) => { s.strokes.delete(pageId); s.strokes.delete(STAMP + pageId); });
}

// every page that has strokes kept here
export function pageIds() {
  const out = new Set([...mirror].filter(([, r]) => r.length).map(([id]) => id));
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(LEGACY)) out.add(k.slice(LEGACY.length));
    }
  } catch (_) { /* ignore */ }
  return [...out];
}

// ---------------------------------------------------------------- new in U3a
// a page gone for good: its mirror entry, its cache entry and every queued op for it (the database cascaded its
// strokes; an insert now would fail on the missing page for ever)
export function forget(pageId) {
  clear(pageId);
  unqueue(pageId);
  version.delete(pageId);
}

// a page deleted on the server (its strokes cascaded) that undo may still bring back: its queued ops can never land,
// so they go; the mirror and the cache keep its strokes, and app.js queues them all again if the page comes back
export function unqueue(pageId) {
  const gone = Q.filter((op) => op.page_id === pageId && !op.parked);   // pw-v9v: a parked change is never dropped
  if (!gone.length) return;
  Q = Q.filter((op) => !gone.includes(op));
  recheck.delete(pageId);
  gone.forEach(dropOp);
  show(Q.length ? state : rest());
}

// ink.js apply(): the exact change, ids actually removed and records actually added. The mirror follows at once; the
// op joins the queue (merged into the page's last op when that one is not on its way yet and came within 300 ms).
export function change(pageId, removed, added) {
  if (!removed.length && !added.length) return;
  version.set(pageId, (version.get(pageId) || 0) + 1);
  unstamp(pageId);                                  // pw-v9s
  touch(removed, added);
  const cur = mirror.get(pageId) || [], rm = new Set(removed), have = new Set();
  const next = cur.filter((r) => !rm.has(r.id));
  next.forEach((r) => have.add(r.id));
  for (const r of added) if (!have.has(r.id)) { next.push(r); have.add(r.id); }
  next.sort(bySeq);
  mirror.set(pageId, next); blind.delete(pageId);
  const now = Date.now();
  let last = null;
  for (let i = Q.length - 1; i >= 0; i--) if (Q[i].page_id === pageId) { last = Q[i]; break; }
  if (last && !last.busy && now - last.t <= MERGE_MS) {
    merge(last, removed, added);
    last.t = now;
    if (!last.removed.length && !last.added.length) { Q = Q.filter((o) => o !== last); dropOp(last); show(Q.length ? state : rest()); return; }
    keepOp(last);
  } else {
    const op = { key: null, page_id: pageId, removed: removed.slice(), added: added.slice(), t: now, busy: false, fk: 0, told: false };
    Q.push(op);
    keepOp(op);
  }
  kick();
}
// op then (removed, added): an id the op added and this removes cancels out; an id this re-adds after the op removed
// it stays in both lists (the push deletes first, then inserts)
function merge(op, removed, added) {
  const rm = new Set(removed), had = new Set(op.added.map((r) => r.id));
  op.added = op.added.filter((r) => !rm.has(r.id));
  const opRm = new Set(op.removed);
  for (const id of removed) if (!had.has(id) && !opRm.has(id)) { op.removed.push(id); opRm.add(id); }
  const ids = new Set(op.added.map((r) => r.id));
  for (const r of added) if (!ids.has(r.id)) { op.added.push(r); ids.add(r.id); }
}

// before a note's sheets attach: its pages' strokes from the cache into the mirror; then, in the background, ONE query
// for the database's copy of those pages (reconcile)
export async function ensure(pageIds) {
  const ids = [...new Set(pageIds)];
  try { await opened; } catch (_) { /* no cache: the database still answers */ }
  const need = ids.filter((id) => !mirror.has(id));
  if (need.length) {
    let got = {}, at = {};
    try {
      await writes;
      ({ got, at } = await run(['strokes'], 'readonly', (s, out) => {
        out.got = {}; out.at = {};
        need.forEach((id) => {
          s.strokes.get(id).onsuccess = (e) => { out.got[id] = e.target.result; };
          s.strokes.get(STAMP + id).onsuccess = (e) => { out.at[id] = e.target.result; };   // pw-v9s: its stamp, same transaction
        });
      }));
    } catch (_) { got = {}; at = {}; /* no cache: empty until the database answers */ }
    for (const id of need) {
      if (mirror.has(id)) continue;                      // changed while the cache was read: the newer copy wins
      const wasBlind = blind.has(id);
      const old = adopt(id);
      const recs = old || (Array.isArray(got[id]) ? got[id].slice().sort(bySeq) : []);
      const sound = got[id] === undefined || Array.isArray(got[id]);   // no records kept = an empty page
      if (!old && sound && typeof at[id] === 'string' && at[id]) stamps.set(id, at[id]); else stamps.delete(id);
      mirror.set(id, recs); blind.delete(id);
      if (wasBlind && recs.length) cfg.onRemote(id, recs.slice());
    }
  }
  reconcile(ids);
}

// strokes from before U3 (localStorage pw.strokes.<page_id>): mirror, cache and queue; the old key goes once the cache
// and the queue hold them. Null when the page has none.
function adopt(pageId) {
  let recs;
  try {
    const raw = localStorage.getItem(LEGACY + pageId);
    if (raw == null) return null;
    recs = JSON.parse(raw);
  } catch (_) { return null; }
  recs = (Array.isArray(recs) ? recs : []).slice().sort(bySeq);
  mirror.set(pageId, recs); blind.delete(pageId);
  if (recs.length) {
    version.set(pageId, (version.get(pageId) || 0) + 1);
    const op = { key: null, page_id: pageId, removed: [], added: recs.slice(), t: 0, busy: false, fk: 0, told: false };
    Q.push(op);
    keepOp(op);
  }
  keepPage(pageId, recs).then((ok) => { if (ok) try { localStorage.removeItem(LEGACY + pageId); } catch (_) { /* ignore */ } });
  if (recs.length) kick();
  return recs;
}

// the database's records for these pages against the mirror, by id. A page with ops still queued keeps its local copy
// (it is checked again once its last op is acknowledged). A page whose set differs takes the database's set.
// pw-v9s: first one light read of the pages' updated_at, fresh; a page is skipped only when it is in the mirror with no
// ops queued, unchanged here since, and its kept stamp is exactly the text the database gave now. Anything else is read.
// No light read (it failed): every page is read, as before. A read that fails leaves everything as it was.
export async function reconcile(ids) {
  if (!ids.length || !cfg.api || !cfg.api.strokesOf) return;
  const at = new Map(ids.map((id) => [id, version.get(id) || 0]));
  let fresh = null;
  if (cfg.api.pageStamps) {
    try { fresh = new Map((await cfg.api.pageStamps(ids)).map((r) => [r.id, r.updated_at])); }
    catch (_) { fresh = null; }
  }
  const stampOf = (id) => { const f = fresh && fresh.get(id); return typeof f === 'string' && f ? f : null; };
  const same = (id) => !!stampOf(id) && stamps.get(id) === stampOf(id) && mirror.has(id)
    && !held(id) && (version.get(id) || 0) === at.get(id);
  const read = ids.filter((id) => !same(id)), reading = new Set(read);
  ids.forEach((id) => { if (!reading.has(id)) unchecked.delete(id); });
  if (!read.length) return;
  let rows;
  try { rows = await cfg.api.strokesOf(read); }
  catch (e) {
    read.forEach((id) => unchecked.add(id));
    console.warn(`PenWorks: the ink of ${read.length} pages could not be read from the database; tried again later.`, e);
    return;
  }
  const up = new Map(read.map((id) => [id, []]));
  for (const r of rows || []) if (up.has(r.page_id)) up.get(r.page_id).push(r);
  const again = [], keep = [];
  for (const [id, theirs] of up) {
    unchecked.delete(id);
    if (!mirror.has(id)) continue;                                   // forgotten while the query ran
    if (held(id)) { recheck.add(id); continue; }                     // pw-v9v: a parked change keeps the local copy too
    if ((version.get(id) || 0) !== at.get(id)) { again.push(id); continue; }   // changed (and pushed) since the query
    const mine = mirror.get(id), have = new Map(mine.map((r) => [r.id, r])), st = stampOf(id);
    if (mine.length === theirs.length && theirs.every((r) => have.has(r.id))) {
      if (st && stamps.get(id) !== st) keep.push([id, mine, st]);
      continue;
    }
    const next = theirs.map((r) => have.get(r.id) || r).sort(bySeq);
    mirror.set(id, next);
    keep.push([id, next, st]);
    cfg.onRemote(id, next.slice());
  }
  if (keep.length) keepPages(keep);
  if (again.length) reconcile(again);
}

// ---------------------------------------------------------------- U3d: rows from another device (js/live.js)
function touch(removed, added) {
  const now = Date.now();
  for (const id of removed) touched.set(id, now);
  for (const r of added) touched.set(r.id, now);
  if (touched.size > 2000) for (const [id, t] of touched) if (now - t > ECHO_MS) touched.delete(id);
}
// this device's own write coming back: an op still queued names the id, or this device changed it in the last 10 s
export function echo(id) {
  const t = touched.get(id);
  if (t && Date.now() - t < ECHO_MS) return true;
  return Q.some(names(id)) || parked.some(names(id));
}
const names = (id) => (op) => op.removed.includes(id) || op.added.some((r) => r.id === id);
// the page whose records (in the mirror) hold this id, or null
export function pageOf(id) {
  for (const [pid, recs] of mirror) if (recs.some((r) => r.id === id)) return pid;
  return null;
}
// a change the database already holds (another device made it): the mirror and the device cache follow, nothing is
// queued, nothing is pushed, no picture becomes due. A page not in the mirror is left alone (the next ensure reads the
// database's copy). The version moves on, so a reconcile answer read before this row arrived is asked again.
export function applyRemote(pageId, removed, added) {
  if (!mirror.has(pageId) || (!removed.length && !added.length)) return false;
  version.set(pageId, (version.get(pageId) || 0) + 1);
  const rm = new Set(removed), next = mirror.get(pageId).filter((r) => !rm.has(r.id)), have = new Set(next.map((r) => r.id));
  for (const r of added) if (!have.has(r.id)) { next.push(r); have.add(r.id); }
  next.sort(bySeq);
  mirror.set(pageId, next); blind.delete(pageId);
  keepPage(pageId, next);
  return true;
}

// ---------------------------------------------------------------- the push
function show(s) {
  state = s;
  try { cfg.onState(s, Q.length + parked.length); } catch (_) { /* the dot is only a dot */ }
}
// pw-v9v: an empty queue is saved, unless something is parked (then the dot stays red)
const rest = () => (parked.length ? 'refused' : 'saved');
const held = (pid) => Q.some((op) => op.page_id === pid) || parked.some((op) => op.page_id === pid);
function trigger() {
  if (unchecked.size) reconcile([...unchecked]);
  if (Q.length) pump();
}
// U3e: the tree queue just emptied (js/treeq.js): strokes held back behind a tree change go now, not at their next retry
export function nudge() { trigger(); }
function kick() {
  if (navigator.onLine === false) { if (!pumping) show('waiting'); return; }
  pump();
}
function retryLater() {
  clearTimeout(retryT);
  retryT = setTimeout(() => { retryT = null; pump(); }, BACKOFF[Math.min(tries, BACKOFF.length - 1)]);
  tries++;
}
function pump() {
  if (pumping) return pumping;
  clearTimeout(retryT); retryT = null;
  pumping = (async () => {
    try { await opened; } catch (_) { /* go on without the cache */ }
    while (Q.length) {
      if (navigator.onLine === false) { show('waiting'); return; }
      const op = Q[0];
      if (behind(op)) { park(op, null, null); continue; }  // pw-v9v: it touches a parked change's strokes, so it waits with it
      op.busy = true;
      show('saving');
      try {
        await cfg.idle();                                   // a new page's row reaches the database before its strokes
        if (Q[0] !== op) { op.busy = false; continue; }      // forgotten while the app's writes went out
        await cfg.api.putStrokes(op.removed, op.added);
      } catch (e) {
        op.busy = false;
        if (!Q.includes(op)) continue;
        if (failed(op, e)) continue;                        // pw-v9v: refused and parked: the rest of the queue goes on
        return;
      }
      op.busy = false;
      tries = 0;
      if (!Q.includes(op)) continue;
      Q = Q.filter((o) => o !== op);
      dropOp(op);
      const pid = op.page_id;
      version.set(pid, (version.get(pid) || 0) + 1);       // pw-v9s: the database moved; a reconcile read before this is asked again
      if (recheck.has(pid) && !held(pid)) { recheck.delete(pid); reconcile([pid]); }
      if (op.parked) noticeParked();                        // pw-v9v: a parked change landed and leaves the list
      try { cfg.onPushed(pid); } catch (_) { /* the page picture (U3b) is only a picture */ }
    }
    show(rest());
  })().finally(() => { pumping = null; });
  return pumping;
}
// true when the op was parked (the queue goes on), false when it waits for a retry (the queue waits too)
function failed(op, e) {
  const code = e && e.code ? String(e.code) : '', status = Number(e && e.status) || 0;
  let no = NO.has(status);
  if (no && code === FK && !op.parked) { op.fk++; no = op.fk > FK_RETRIES; }   // a page row may still be on its way
  if (no) { park(op, code || `HTTP ${status}`, e); return true; }
  show('waiting');
  retryLater();
  return false;
}

// ---------------------------------------------------------------- pw-v9v: parked changes
// out of the queue into the parked list, kept in store `queue` with parked: true (never deleted until it lands)
function park(op, why, e) {
  Q = Q.filter((o) => o !== op);
  Object.assign(op, { busy: false, t: 0, fk: 0, parked: true });
  parked.push(op);
  keepOp(op);
  if (!op.told) {
    op.told = true;
    console.warn(why
      ? `PenWorks: the database refused a change to page ${op.page_id} (${why}): ${(e && e.message) || e}. It is kept on this device and tried again at the next start or connection.`
      : `PenWorks: a change to page ${op.page_id} touches a refused change's strokes, so it is kept with it on this device.`);
  }
  noticeParked();
}
// an op that names a stroke a parked op names: sending it first would put her strokes in the wrong order
function behind(op) {
  if (!parked.length) return false;
  const ids = new Set();
  for (const p of parked) { p.removed.forEach((id) => ids.add(id)); p.added.forEach((r) => ids.add(r.id)); }
  return op.removed.some((id) => ids.has(id)) || op.added.some((r) => ids.has(r.id));
}
// on `online`: the parked ops back to the head of the queue (after one already on its way), oldest first
function unpark() {
  if (!parked.length) return;
  const back = parked, head = Q.length && Q[0].busy ? 1 : 0;
  parked = [];
  Q = [...Q.slice(0, head), ...back, ...Q.slice(head)];
}
function noticeParked() {
  if (parked.length) flag('parked', true);
  else if (!Q.some((o) => o.parked)) flag('parked', false);   // cleared only once none is left, parked or on retry
}
function flag(kind, on) {
  if (flags[kind] === on) return;
  flags[kind] = on;
  if (on) try { cfg.onNotice(kind); } catch (_) { /* a notice is only a notice */ }
}
// every few seconds: the queue's head unsent for SLOW_MS of online time = the notice; an empty queue clears it
function slowTick() {
  const now = Date.now(), dt = now - slowLast, head = Q[0];
  slowLast = now;
  if (!head) { slowHead = null; slowFor = 0; flag('slow', false); return; }
  if (head !== slowHead) { slowHead = head; slowFor = 0; return; }
  if (navigator.onLine !== false) slowFor += dt;
  if (slowFor >= cfg.slowMs) flag('slow', true);
}
// once per device: ask the browser to keep this site's storage (her ink on the tablet) through a storage clean-up
function askPersist() {
  try {
    const s = navigator.storage;
    if (!s || !s.persist || !s.persisted || localStorage.getItem(PERSIST)) return;
    s.persisted().then((yes) => {
      if (yes || localStorage.getItem(PERSIST)) return null;
      localStorage.setItem(PERSIST, '1');
      return s.persist();
    }).catch(() => {});
  } catch (_) { /* no storage manager: nothing to ask */ }
}

// ---------------------------------------------------------------- U3b: what the page pictures ask
export function known(pageId) { return mirror.has(pageId); }                 // its strokes are in the mirror
export function pending(pageId) { return Q.some((op) => op.page_id === pageId); }   // ops for it still to go up

// the note covers (U3b): their own small database penworks.<mode>.<user id>.covers, store `covers`, key = note id,
// value = { path, at (the first page's snapshot_at), blob }. Their own, not a store in the strokes database: adding a
// store there means a version 2, and a tab still open on version 1 would hold the strokes database shut until it closes.
function openCovers(name) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(name, 1);
    r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains('covers')) r.result.createObjectStore('covers'); };
    r.onsuccess = () => { const db = r.result; db.onversionchange = () => db.close(); resolve(db); };
    r.onerror = () => reject(r.error);
  });
}
function coverRun(mode, fn) {
  return coverDb.then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(['covers'], mode), out = {};
    fn(t.objectStore('covers'), out);
    t.oncomplete = () => resolve(out.v);
    t.onerror = t.onabort = () => reject(t.error);
  }));
}
export function coverGet(noteId) {
  return coverRun('readonly', (s, out) => { s.get(noteId).onsuccess = (e) => { out.v = e.target.result || null; }; }).catch(() => null);
}
export function coverPut(noteId, v) {
  return coverRun('readwrite', (s) => { s.put(v, noteId); }).then(() => true, () => false);
}
export function coverDrop(noteId) {
  return coverRun('readwrite', (s) => { s.delete(noteId); }).then(() => true, () => false);
}

// ---------------------------------------------------------------- for the tests (window.__pw.store)
export async function queueLength() {
  await opened.catch(() => {});
  await writes;
  try { return (await run(['queue'], 'readonly', (s, out) => { s.queue.count().onsuccess = (e) => { out.n = e.target.result; }; })).n; }
  catch (_) { return Q.length; }
}
export function queued() { return Q.map(serial); }
export function saveState() { return { state, count: Q.length }; }
// pw-v9v: the parked list in memory, the notices that are up, and every op kept on this device (parked or not)
export function parkedOps() { return parked.map(serial); }
export function notices() { return { ...flags }; }
export async function keptOps() {
  await opened.catch(() => {});
  await writes;
  try {
    const out = await run(['queue'], 'readonly', (s, o) => {
      s.queue.getAll().onsuccess = (e) => { o.vals = e.target.result; };
      s.queue.getAllKeys().onsuccess = (e) => { o.keys = e.target.result; };
    });
    return out.keys.map((key, i) => ({ key, ...out.vals[i] }));
  } catch (_) { return null; }
}
export async function cached(pageId) {
  await writes;
  try { return (await run(['strokes'], 'readonly', (s, out) => { s.strokes.get(pageId).onsuccess = (e) => { out.v = e.target.result; }; })).v ?? null; }
  catch (_) { return null; }
}
// pw-v9s: a page's stamp, in memory and as kept on this device (null: none)
export function stampOf(pageId) { return stamps.get(pageId) ?? null; }
export async function cachedStamp(pageId) {
  await writes;
  try { return (await run(['strokes'], 'readonly', (s, out) => { s.strokes.get(STAMP + pageId).onsuccess = (e) => { out.v = e.target.result; }; })).v ?? null; }
  catch (_) { return null; }
}
// every write on this device done and the push stopped (saved, or waiting / refused until the next trigger)
export async function settled() {
  for (let i = 0; i < 100; i++) {
    await new Promise((r) => setTimeout(r, 0));           // ink's save timer (0 ms) first
    await writes;
    if (pumping) { await pumping; continue; }
    break;
  }
  await writes;
}
