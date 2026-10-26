// PenWorks tree queue (U3e): every change to the tree (folders, notes, pages) goes up through here, the way her ink goes
// up through js/store.js. An op is one named call of api.js and its arguments, { call: 'createPage', args: [row] },
// copied (JSON) the moment it is made. The queue lives in IndexedDB, its OWN database penworks.<mode>.<user id>.tree
// (store `queue`, numbered keys), so a page or note made without wifi (or just before a crash) goes up at the next chance.
// Ops go up in order, one at a time: api[call](...args).
//
// Running an op twice is harmless: an insert that meets its own row (23505: it landed on a run that died before the ack)
// counts as done; an update that comes back short ('Not every row was saved') because a LATER op in the queue deletes
// that row counts as done too. Every other short update is a refusal.
// Triggers and backoff as the stroke queue: at once when online, again on `online`, on focus, when the app is visible,
// and 2 / 5 / 10 / 30 s after a failure. Offline or a network error: the op stays, the state is `waiting`.
// A REFUSAL (42501, 23514, 23502, 22P02, a short update, or 23503 that survives three retries) is not like ink: after
// the third failure the op is DROPPED, onDrop(what) says so (one toast in plain words), the console says why with the
// code, and the next tree refresh puts the screen back to what the server has. Her ink is never dropped; a tree op can
// be, because the server's rule won and the screen must agree with it.
//
// The same database keeps one more record: store `snapshot`, key `tree` = { folders, notes, pages, at }, the server's
// tree as this device last knew it (the last loadAll answer, with every op that has landed since applied to it, in the
// same transaction that takes the op off the queue). With no connection at start, app.js loads from it and overlay()
// re-applies the queued ops on top, so the screen shows what she last saw.

const BACKOFF = [2000, 5000, 10000, 30000];
const REFUSE = new Set(['42501', '23514', '23502', '22P02']);
const FK = '23503', DUP = '23505';
const TRIES = 3;                     // a refusal: dropped on the third failure
const FK_RETRIES = 3;                // a missing parent row: the first try plus three retries, then dropped
const SHORT = /Not every row was saved/;
const LOCAL_MARK = 'pw.tree.local';  // local mode only: a cleared localStorage is a fresh twin, so the queue starts fresh
const TABLES = ['folders', 'notes', 'pages'];
const INSERTS = { createFolder: 'folders', createNote: 'notes', createPage: 'pages' };
const PAGE_EDIT = new Set(['createPage', 'deletePage', 'reorderPages', 'setPages']);   // the note counts as edited
// what the toast calls each change, in plain words
const WHAT = {
  createFolder: 'a new folder', renameFolder: 'a rename', recolourFolder: 'a folder colour', moveFolder: 'moving a folder',
  reorderFolders: 'moving a folder', createNote: 'a new note', renameNote: 'a rename', moveNote: 'moving a note',
  pinNote: 'pinning a note', createPage: 'a new page', reorderPages: 'moving a page', setPages: 'a paper change',
  setBookmark: 'a bookmark', deletePage: 'deleting a page', bin: 'moving to the Bin', restore: 'a restore',
};
// a row the overlay adds: the database's defaults under what the op carried
const DEFAULTS = {
  folders: { parent_id: null, name: '', colour: null, position: 0, deleted_at: null },
  notes: { folder_id: null, name: 'Untitled', pinned: false, cover_path: null, deleted_at: null },
  pages: { note_id: null, position: 0, orientation: 'portrait', background: 'grid', bookmark: false,
           snapshot_path: null, snapshot_at: null, flagged: false, deleted_at: null },
};

let Q = [];                          // oldest first: { key, call, args, at, busy, fails, fk, wait: [resolve] }
let nextKey = 1;
const cfg = { mode: 'local', api: null, onState: () => {}, onDrop: () => {} };
let dbp = Promise.reject(new Error('treeq.init has not run'));
dbp.catch(() => {});
let opened = Promise.resolve();
let writes = Promise.resolve();
let pumping = null, retryT = null, tries = 0, state = 'saved', held = false, dropped = 0;
let snapMem = null;                  // the snapshot record, in memory
let acked = [], flushDue = false;    // landed ops that leave the device copy (with the snapshot) in the next write

// ---------------------------------------------------------------- IndexedDB
function openDb(name) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(name, 1);
    r.onupgradeneeded = () => {
      const db = r.result;
      if (!db.objectStoreNames.contains('queue')) db.createObjectStore('queue');
      if (!db.objectStoreNames.contains('snapshot')) db.createObjectStore('snapshot');
    };
    r.onsuccess = () => { const db = r.result; db.onversionchange = () => db.close(); resolve(db); };
    r.onerror = () => reject(r.error);
  });
}
function dropDb(name) {
  return new Promise((resolve) => {
    const r = indexedDB.deleteDatabase(name);
    r.onsuccess = r.onerror = r.onblocked = () => resolve();
  });
}
function run(mode, fn) {
  return dbp.then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(['queue', 'snapshot'], mode), out = {};
    fn({ queue: t.objectStore('queue'), snapshot: t.objectStore('snapshot') }, out);
    t.oncomplete = () => resolve(out);
    t.onerror = t.onabort = () => reject(t.error);
  }));
}
// every write in one chain, in order; true once committed, false when the device would not keep it
function write(fn) {
  const p = writes.then(() => run('readwrite', fn)).then(() => true,
    (e) => { console.warn('Tree changes not kept on this device', e); return false; });
  writes = p;
  return p;
}
const serial = (op) => ({ call: op.call, args: op.args, at: op.at });
// an op that landed or was dropped before its own put ran is never put (op.gone)
function keepOp(op) { return write((s) => { if (op.gone) return; if (op.key == null) op.key = nextKey++; s.queue.put(serial(op), op.key); }); }
function dropOp(op) { return write((s) => { if (op.key != null) s.queue.delete(op.key); }); }
// the snapshot (as it is when the write runs) and the keys of the ops it now holds, in one transaction
function flush() {
  if (flushDue) return;
  flushDue = true;
  write((s) => {
    flushDue = false;
    if (snapMem) s.snapshot.put(snapMem, 'tree');
    for (const op of acked) if (op.key != null) s.queue.delete(op.key);
    acked = [];
  });
}

// ---------------------------------------------------------------- start
export function init(o) {
  Object.assign(cfg, o);
  const name = `penworks.${o.mode}.${o.userId}.tree`;
  let wipe = Promise.resolve();
  if (o.mode === 'local') {
    try {
      if (localStorage.getItem(LOCAL_MARK) !== name) { wipe = dropDb(name); localStorage.setItem(LOCAL_MARK, name); }
    } catch (_) { /* ignore */ }
  }
  dbp = wipe.then(() => openDb(name));
  dbp.catch((e) => console.warn('No device copy for tree changes', e));
  // the queue left from last time comes first; ops made before it was read keep their place after it
  opened = writes = writes.then(() => run('readonly', (s, out) => {
    s.queue.getAll().onsuccess = (e) => { out.vals = e.target.result; };
    s.queue.getAllKeys().onsuccess = (e) => { out.keys = e.target.result; };
    s.snapshot.get('tree').onsuccess = (e) => { out.tree = e.target.result; };
  })).then((out) => {
    const old = out.keys.map((key, i) => ({ ...out.vals[i], key, busy: false, fails: 0, fk: 0, wait: [] }));
    nextKey = Math.max(0, ...out.keys) + 1;
    Q = [...old, ...Q];
    if (out.tree && !snapMem) snapMem = out.tree;
  }, () => {});
  opened.then(() => { if (Q.length) kick(); else show('saved'); });
  addEventListener('online', trigger);
  addEventListener('offline', () => { if (Q.length && !pumping) show('waiting'); });
  addEventListener('focus', trigger);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) trigger(); });
}

// ---------------------------------------------------------------- the calls app.js makes
// one change to the tree: queued (and kept on the device) at once, sent when it can be. Resolves true when THAT op has
// landed, false when it was dropped; it stays open while the device is offline (the op is kept, it lands later).
export function push(call, args) {
  if (!cfg.api || typeof cfg.api[call] !== 'function') throw new Error('Unknown tree call ' + call);
  const op = { key: null, call, args: JSON.parse(JSON.stringify(args)), at: new Date().toISOString(),
               busy: false, fails: 0, fk: 0, wait: [] };
  const done = new Promise((r) => op.wait.push(r));
  Q.push(op);
  keepOp(op);
  kick();
  return done;
}

export function length() { return Q.length; }
// every row id the queued ops touch: a row id, the ids of setPages, the pairs of a reorder, the ids of bin / restore
export function pending() { return [...new Set(Q.flatMap(idsOf))]; }
function idsOf(op) {
  const a = op.args[0];
  if (INSERTS[op.call]) return a && a.id ? [a.id] : [];
  if (op.call === 'reorderFolders' || op.call === 'reorderPages') return (a || []).map((p) => p[0]);
  if (op.call === 'setPages') return (a || []).slice();
  if (op.call === 'bin' || op.call === 'restore') return TABLES.flatMap((t) => (a && a[t]) || []);
  return a == null ? [] : [a];
}

// the queue empty, or it cannot push at all now (offline, or held by a test). A retry that is due while online is
// waited for, so __pw.idle() and the page pictures see the database as it will be.
export async function settled() {
  const end = Date.now() + 60000;
  while (Date.now() < end) {
    await new Promise((r) => setTimeout(r, 0));
    await opened.catch(() => {});
    await writes;
    if (pumping) { await pumping; continue; }
    if (Q.length && !held && navigator.onLine !== false) { await new Promise((r) => setTimeout(r, 50)); continue; }
    break;
  }
  await writes;
}
// the stroke queue's idle(): resolves once the tree queue is empty (a new page's row goes before its strokes); throws a
// network-style error (no code) while tree ops wait (offline, a retry to come, held), so the stroke op waits as well
export async function gate() {
  for (;;) {
    await opened.catch(() => {});
    if (!Q.length) return;
    if (pumping) { await pumping; continue; }
    throw new Error('Tree changes go up first');
  }
}

// ---------------------------------------------------------------- the snapshot (app.js load / refreshTree)
// a loadAll answer that just came in: it is the snapshot now (a copy, taken at once: the app changes its rows)
export function keepTree(d) {
  snapMem = { folders: clone(d.folders || []), notes: clone(d.notes || []), pages: clone(d.pages || []), at: new Date().toISOString() };
  flush();
}
// the last snapshot (a copy), or null when this device has none
export async function lastTree() {
  await opened.catch(() => {});
  return snapMem ? clone(snapMem) : null;
}
// the queued ops applied in order to a tree (changed in place and returned): what she last saw
export async function overlay(d) {
  await opened.catch(() => {});
  for (const op of Q) apply(d, op);
  return d;
}
const clone = (o) => JSON.parse(JSON.stringify(o));
function apply(d, op) {
  const [a, b, c] = op.args;
  const list = (t) => (d[t] ||= []);
  const row = (t, id) => list(t).find((r) => r.id === id);
  const patch = (t, ids, p) => ids.forEach((id) => { const r = row(t, id); if (r) Object.assign(r, p); });
  const edited = (nid) => { const n = row('notes', nid); if (n) n.updated_at = op.at; };
  const pageNote = (id) => { const p = row('pages', id); return p && p.note_id; };
  let notes = [];
  if (PAGE_EDIT.has(op.call)) {
    if (op.call === 'createPage') notes = [a.note_id];
    else if (op.call === 'deletePage') notes = [pageNote(a)];
    else if (op.call === 'setPages') notes = a.map(pageNote);
    else notes = a.map((p) => pageNote(p[0]));
  }
  switch (op.call) {
    case 'createFolder': case 'createNote': case 'createPage': {
      const t = INSERTS[op.call];
      if (a && a.id && !row(t, a.id)) list(t).push({ ...DEFAULTS[t], created_at: op.at, updated_at: op.at, ...clone(a) });
      break;
    }
    case 'renameFolder': patch('folders', [a], { name: b }); break;
    case 'recolourFolder': patch('folders', [a], { colour: b }); break;
    case 'moveFolder': patch('folders', [a], { parent_id: b, position: c }); break;
    case 'reorderFolders': a.forEach(([id, position]) => patch('folders', [id], { position })); break;
    case 'renameNote': patch('notes', [a], { name: b }); edited(a); break;
    case 'moveNote': patch('notes', [a], { folder_id: b }); break;
    case 'pinNote': patch('notes', [a], { pinned: b }); break;
    case 'reorderPages': a.forEach(([id, position]) => patch('pages', [id], { position })); break;
    case 'setPages': patch('pages', a, b || {}); break;
    case 'setBookmark': patch('pages', [a], { bookmark: !!b }); break;
    case 'deletePage': d.pages = list('pages').filter((r) => r.id !== a); break;
    case 'bin': case 'restore':
      for (const t of TABLES) patch(t, (a && a[t]) || [], { deleted_at: op.call === 'bin' ? b : null });
      break;
    default: break;
  }
  notes.filter(Boolean).forEach(edited);
}

// ---------------------------------------------------------------- the push
function show(s) {
  state = s;
  try { cfg.onState(s, Q.length); } catch (_) { /* the dot is only a dot */ }
}
function trigger() { if (Q.length) kick(); }
function kick() {
  if (held || navigator.onLine === false) { if (!pumping) show(Q.length ? 'waiting' : 'saved'); return; }
  pump();
}
function retryLater() {
  clearTimeout(retryT);
  retryT = setTimeout(() => { retryT = null; pump(); }, BACKOFF[Math.min(tries, BACKOFF.length - 1)]);
  tries++;
}
const codeOf = (e) => (e && e.code ? String(e.code) : '');
const short = (e) => !!e && SHORT.test(String(e.message || e));
// a later op in the queue deletes (one of) the rows this update names: the update met a row gone for good
function deletedLater(op) {
  const ids = new Set(idsOf(op)), i = Q.indexOf(op);
  return Q.slice(i + 1).some((o) => o.call === 'deletePage' && ids.has(o.args[0]));
}
async function send(op) {
  try { await cfg.api[op.call](...op.args); }
  catch (e) {
    if (INSERTS[op.call] && codeOf(e) === DUP) return;      // it landed before (a run that died before the ack)
    if (short(e) && deletedLater(op)) return;               // its row is deleted for good further down the queue
    throw e;
  }
}
function pump() {
  if (pumping) return pumping;
  clearTimeout(retryT); retryT = null;
  pumping = (async () => {
    try { await opened; } catch (_) { /* go on without the device copy */ }
    while (Q.length) {
      if (held || navigator.onLine === false) { show('waiting'); return; }
      const op = Q[0];
      op.busy = true;
      show('saving');
      let err = null;
      try { await send(op); } catch (e) { err = e; }
      op.busy = false;
      if (!Q.includes(op)) continue;
      if (err) {
        if (failed(op, err)) { drop(op, err); continue; }
        return;
      }
      tries = 0;
      land(op);
    }
    show('saved');
  })().finally(() => { pumping = null; });
  return pumping;
}
// true = drop it now; otherwise the state says why it waits and a retry is set
function failed(op, e) {
  const code = codeOf(e);
  if (code === FK) {
    op.fk++;
    if (op.fk > FK_RETRIES) return true;
    show('waiting');
  } else if (REFUSE.has(code) || short(e)) {
    op.fails++;
    if (op.fails >= TRIES) return true;
    show('refused');
  } else show('waiting');                                   // offline or a network error: it stays
  retryLater();
  return false;
}
function land(op) {
  Q = Q.filter((o) => o !== op);
  op.gone = true;
  if (snapMem) apply(snapMem, op);                          // the server has it now
  acked.push(op);
  flush();
  op.wait.forEach((r) => r(true));
}
function drop(op, e) {
  Q = Q.filter((o) => o !== op);
  op.gone = true;
  dropOp(op);
  dropped++;
  tries = 0;
  const what = WHAT[op.call] || 'a change';
  console.warn(`PenWorks: the database refused ${what} (${op.call}, code ${codeOf(e) || 'none'}): ${(e && e.message) || e}. `
    + 'It was dropped; the next tree refresh shows what the database has.');
  try { cfg.onDrop(what, op.call); } catch (_) { /* the toast is only a toast */ }
  op.wait.forEach((r) => r(false));
}

// ---------------------------------------------------------------- for the tests (window.__pw.treeq)
export function dropCount() { return dropped; }
export function hold(on) { held = !!on; if (!held) kick(); else if (!pumping) show(Q.length ? 'waiting' : 'saved'); }
export function queued() { return Q.map(serial); }
export function saveState() { return { state, count: Q.length }; }
export async function queueLength() {
  await opened.catch(() => {});
  await writes;
  try { return (await run('readonly', (s, out) => { s.queue.count().onsuccess = (e) => { out.n = e.target.result; }; })).n; }
  catch (_) { return Q.length; }
}
// the snapshot record as it sits on the device: its size in bytes of JSON, and its row counts
export async function snapshotInfo() {
  await writes;
  let rec = null;
  try { rec = (await run('readonly', (s, out) => { s.snapshot.get('tree').onsuccess = (e) => { out.v = e.target.result; }; })).v || null; }
  catch (_) { rec = null; }
  if (!rec) return null;
  return { bytes: new TextEncoder().encode(JSON.stringify(rec)).length,
           folders: rec.folders.length, notes: rec.notes.length, pages: rec.pages.length };
}
