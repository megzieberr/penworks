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

const LEGACY = 'pw.strokes.';
const LOCAL_MARK = 'pw.cache.local';      // local mode only: the twin lives in localStorage, its cache lives with it
const MERGE_MS = 300;                      // two ops on one page this close together become one
const BACKOFF = [2000, 5000, 10000, 30000];
const REFUSE = new Set(['42501', '23514', '23502', '22P02']);
const FK = '23503', FK_RETRIES = 3;        // a missing page: the first try plus three retries, then refused
const bySeq = (a, b) => a.seq - b.seq;
const ECHO_MS = 10000;                     // U3d: an event for an id this device changed this recently is its own push coming back

const mirror = new Map();     // page id -> records (seq order); a page is "known" once it is in here
const blind = new Set();      // pages load() was asked for before their cache was read (they were handed [])
const version = new Map();    // page id -> how many changes so far (a reconcile answer older than a change is dropped)
const recheck = new Set();    // pages a reconcile skipped while the queue held their ops: checked again once it drains
const unchecked = new Set();  // pages whose reconcile could not reach the database: checked on the next trigger
const touched = new Map();    // U3d: stroke id -> when this device last added or removed it (store.change)
let Q = [];                   // the queue, oldest first: { key, page_id, removed, added, t, busy, fk, told }
let nextKey = 1;
const cfg = { mode: 'local', api: null, idle: () => Promise.resolve(), onRemote: () => {}, onState: () => {}, onPushed: () => {} };
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
const serial = (op) => ({ page_id: op.page_id, removed: op.removed, added: op.added });
function keepOp(op) {
  return write((s) => { if (op.key == null) op.key = nextKey++; s.queue.put(serial(op), op.key); });
}
function dropOp(op) {
  return write((s) => { if (op.key != null) s.queue.delete(op.key); });
}
function keepPage(id, recs) {
  return write((s) => { if (recs.length) s.strokes.put(recs, id); else s.strokes.delete(id); });
}

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
  addEventListener('online', trigger);
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
  mirror.delete(pageId); blind.delete(pageId); recheck.delete(pageId); unchecked.delete(pageId);
  try { localStorage.removeItem(LEGACY + pageId); } catch (_) { /* ignore */ }
  write((s) => { s.strokes.delete(pageId); });
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
  const gone = Q.filter((op) => op.page_id === pageId);
  if (!gone.length) return;
  Q = Q.filter((op) => op.page_id !== pageId);
  recheck.delete(pageId);
  gone.forEach(dropOp);
  show(Q.length ? state : 'saved');
}

// ink.js apply(): the exact change, ids actually removed and records actually added. The mirror follows at once; the
// op joins the queue (merged into the page's last op when that one is not on its way yet and came within 300 ms).
export function change(pageId, removed, added) {
  if (!removed.length && !added.length) return;
  version.set(pageId, (version.get(pageId) || 0) + 1);
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
    if (!last.removed.length && !last.added.length) { Q = Q.filter((o) => o !== last); dropOp(last); show(Q.length ? state : 'saved'); return; }
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
    let got = {};
    try {
      await writes;
      got = await run(['strokes'], 'readonly', (s, out) => need.forEach((id) => { s.strokes.get(id).onsuccess = (e) => { out[id] = e.target.result; }; }));
    } catch (_) { /* no cache: empty until the database answers */ }
    for (const id of need) {
      if (mirror.has(id)) continue;                      // changed while the cache was read: the newer copy wins
      const wasBlind = blind.has(id);
      const recs = adopt(id) || (Array.isArray(got[id]) ? got[id].slice().sort(bySeq) : []);
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
export async function reconcile(ids) {
  if (!ids.length || !cfg.api || !cfg.api.strokesOf) return;
  const at = new Map(ids.map((id) => [id, version.get(id) || 0]));
  let rows;
  try { rows = await cfg.api.strokesOf(ids); }
  catch (_) { ids.forEach((id) => unchecked.add(id)); return; }
  const up = new Map(ids.map((id) => [id, []]));
  for (const r of rows || []) if (up.has(r.page_id)) up.get(r.page_id).push(r);
  const again = [];
  for (const [id, theirs] of up) {
    unchecked.delete(id);
    if (!mirror.has(id)) continue;                                   // forgotten while the query ran
    if (Q.some((op) => op.page_id === id)) { recheck.add(id); continue; }
    if ((version.get(id) || 0) !== at.get(id)) { again.push(id); continue; }   // changed (and pushed) since the query
    const mine = mirror.get(id), have = new Map(mine.map((r) => [r.id, r]));
    if (mine.length === theirs.length && theirs.every((r) => have.has(r.id))) continue;
    const next = theirs.map((r) => have.get(r.id) || r).sort(bySeq);
    mirror.set(id, next);
    keepPage(id, next);
    cfg.onRemote(id, next.slice());
  }
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
  return Q.some((op) => op.removed.includes(id) || op.added.some((r) => r.id === id));
}
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
  try { cfg.onState(s, Q.length); } catch (_) { /* the dot is only a dot */ }
}
function trigger() {
  if (unchecked.size) reconcile([...unchecked]);
  if (Q.length) pump();
}
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
      op.busy = true;
      show('saving');
      try {
        await cfg.idle();                                   // a new page's row reaches the database before its strokes
        if (Q[0] !== op) { op.busy = false; continue; }      // forgotten while the app's writes went out
        await cfg.api.putStrokes(op.removed, op.added);
      } catch (e) {
        op.busy = false;
        if (!Q.includes(op)) continue;
        failed(op, e);
        return;
      }
      op.busy = false;
      tries = 0;
      if (!Q.includes(op)) continue;
      Q = Q.filter((o) => o !== op);
      dropOp(op);
      const pid = op.page_id;
      if (recheck.has(pid) && !Q.some((o) => o.page_id === pid)) { recheck.delete(pid); reconcile([pid]); }
      try { cfg.onPushed(pid); } catch (_) { /* the page picture (U3b) is only a picture */ }
    }
    show('saved');
  })().finally(() => { pumping = null; });
  return pumping;
}
function failed(op, e) {
  const code = e && e.code ? String(e.code) : '';
  let refused = REFUSE.has(code);
  if (code === FK) { op.fk++; refused = op.fk > FK_RETRIES; }
  if (refused) {
    if (!op.told) { op.told = true; console.warn(`PenWorks: the database refused a change to page ${op.page_id} (${code}): ${(e && e.message) || e}. It stays queued and is tried again.`); }
    show('refused');
  } else show('waiting');
  retryLater();
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
export async function cached(pageId) {
  await writes;
  try { return (await run(['strokes'], 'readonly', (s, out) => { s.strokes.get(pageId).onsuccess = (e) => { out.v = e.target.result; }; })).v ?? null; }
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
