// PenWorks local twin of the database layer. Switched on with ?local=1.
// Same calls and the same row shapes as js/api.js, kept in this browser's localStorage, so the whole
// app can be built and tested without touching Supabase. It copies the database's rules too:
// folders two levels deep (a hard stop), "on delete cascade / set null", and what counts as
// "last edited" for a note (renamed, or a page added, deleted, moved or re-papered).
// Strokes (U3a): a `strokes` array of rows (the strokes table's shape), reached only through strokesOf and putStrokes;
// a page deleted for good takes its strokes with it, a stroke for a page that is not there is refused (23503).

const KEY = 'penworks.local.v2';
const TABLES = ['folders', 'notes', 'pages'];
const DEFAULTS = {
  folders: { parent_id: null, name: '', colour: null, position: 0, deleted_at: null },
  notes: { folder_id: null, name: 'Untitled', pinned: false, cover_path: null, deleted_at: null },
  pages: { note_id: null, position: 0, orientation: 'portrait', background: 'grid',
           snapshot_path: null, flagged: false, deleted_at: null },
};
const PAGE_EDIT = ['position', 'orientation', 'background'];
const STROKE_KEYS = ['id', 'page_id', 'seq', 'kind', 'style', 'data'];

function read() {
  try {
    const d = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (d && TABLES.every((t) => Array.isArray(d[t]))) {
      if (!Array.isArray(d.strokes)) d.strokes = [];      // a store from before U3a: no strokes yet
      return d;
    }
  } catch (_) { /* fall through to an empty store */ }
  return { folders: [], notes: [], pages: [], strokes: [] };
}
function write(d) { localStorage.setItem(KEY, JSON.stringify(d)); }
function check(table) { if (!TABLES.includes(table)) throw new Error('Unknown table ' + table); }
function clone(o) { return JSON.parse(JSON.stringify(o)); }
function refuse(msg, code = '23514') { const e = new Error(msg); e.code = code; throw e; }
// the database's "on delete cascade" from pages to strokes
function dropStrokes(d) { const live = new Set(d.pages.map((p) => p.id)); d.strokes = d.strokes.filter((s) => live.has(s.page_id)); }
// the strokes_touch_page trigger: a stroke added or removed bumps its page's updated_at
function touchPages(d, pageIds, now) { const set = new Set(pageIds); d.pages.forEach((p) => { if (set.has(p.id)) p.updated_at = now; }); }

// the database's folders_two_levels trigger, word for word
function twoLevels(d, id, parentId) {
  if (parentId === null || parentId === undefined) return;
  if (parentId === id) refuse('A folder cannot sit inside itself.');
  const p = d.folders.find((f) => f.id === parentId);
  if (!p) refuse('That folder does not exist.');
  if (p.parent_id) refuse('Folders go two levels deep, no further.');
  if (id && d.folders.some((f) => f.parent_id === id)) refuse('A folder with folders inside it cannot go inside another folder.');
}
function touchNotes(d, noteIds, now) {
  const set = new Set(noteIds);
  d.notes.forEach((n) => { if (set.has(n.id)) n.updated_at = now; });
}

let failNext = 0;   // test hook: make the next n writes fail, to prove the retry toast (and the strokes queue's retry)
function maybeFail() {
  if (failNext > 0) { failNext--; throw new Error('Simulated failed write'); }
}
let refuseNext = 0; // test hook: the next n stroke pushes are refused the way RLS refuses them (code 42501)
function maybeRefuse() {
  if (refuseNext > 0) { refuseNext--; refuse('new row violates row-level security policy for table "strokes"', '42501'); }
}

export const localApi = {
  mode: 'local',

  async session() { return { id: 'local', username: 'local' }; },
  async signIn() { return { ok: true }; },
  async signOut() { /* nothing to end */ },

  async purgeBin(days = 30) {
    const d = read(), cut = Date.now() - days * 864e5;
    const old = (r) => r.deleted_at && Date.parse(r.deleted_at) < cut;
    const before = d.folders.length + d.notes.length + d.pages.length;
    d.pages = d.pages.filter((r) => !old(r));
    const goneNotes = new Set(d.notes.filter(old).map((r) => r.id));
    d.notes = d.notes.filter((r) => !goneNotes.has(r.id));
    d.pages = d.pages.filter((r) => !goneNotes.has(r.note_id));
    const goneF = new Set(d.folders.filter(old).map((r) => r.id));
    d.folders.forEach((f) => { if (goneF.has(f.parent_id)) goneF.add(f.id); });
    d.folders = d.folders.filter((r) => !goneF.has(r.id));
    d.notes.forEach((n) => { if (goneF.has(n.folder_id)) n.folder_id = null; });
    dropStrokes(d);
    write(d);
    return before - (d.folders.length + d.notes.length + d.pages.length);
  },

  async loadAll() {
    const d = read();
    return { folders: clone(d.folders), notes: clone(d.notes), pages: clone(d.pages) };
  },

  async insert(table, row) {
    check(table); maybeFail();
    const d = read(), now = new Date().toISOString();
    const id = row.id || crypto.randomUUID();
    if (d[table].some((r) => r.id === id)) refuse('That row is there already.');
    if (table === 'folders') twoLevels(d, id, row.parent_id);
    if (table === 'notes' && row.folder_id && !d.folders.some((f) => f.id === row.folder_id)) refuse('That folder does not exist.');
    if (table === 'pages' && !d.notes.some((n) => n.id === row.note_id)) refuse('That note does not exist.');
    const r = { ...DEFAULTS[table], ...row, id, owner_id: 'local', created_at: row.created_at || now, updated_at: now };
    d[table].push(r);
    if (table === 'pages') touchNotes(d, [r.note_id], now);
    write(d);
    return clone(r);
  },

  async update(table, ids, patch) {
    check(table); maybeFail();
    const d = read(), now = new Date().toISOString(), set = new Set(ids);
    const hit = d[table].filter((r) => set.has(r.id));
    if (hit.length !== set.size) throw new Error('Some rows were not found');
    if (table === 'folders' && 'parent_id' in patch) hit.forEach((r) => twoLevels(d, r.id, patch.parent_id));
    hit.forEach((r) => {
      Object.assign(r, patch);
      if (table !== 'notes' || 'name' in patch) r.updated_at = now;   // notes: only a rename counts
    });
    if (table === 'pages' && PAGE_EDIT.some((k) => k in patch)) touchNotes(d, hit.map((r) => r.note_id), now);
    write(d);
  },

  // hard delete with the database's cascades
  async remove(table, ids) {
    check(table); maybeFail();
    const d = read(), set = new Set(ids), now = new Date().toISOString();
    if (table === 'folders') {
      d.folders.forEach((f) => { if (set.has(f.parent_id)) set.add(f.id); });
      d.notes.forEach((n) => { if (set.has(n.folder_id)) n.folder_id = null; });
    }
    if (table === 'notes') d.pages = d.pages.filter((p) => !set.has(p.note_id));
    if (table === 'pages') touchNotes(d, d.pages.filter((p) => set.has(p.id)).map((p) => p.note_id), now);
    d[table] = d[table].filter((r) => !set.has(r.id));
    if (table === 'pages' || table === 'notes') dropStrokes(d);
    write(d);
  },

  // strokes (U3a): every row of these pages, in seq order, in the columns api.js selects
  async strokesOf(pageIds) {
    const d = read(), set = new Set(pageIds);
    return clone(d.strokes.filter((s) => set.has(s.page_id)).sort((a, b) => a.seq - b.seq)
      .map((s) => Object.fromEntries(STROKE_KEYS.map((k) => [k, s[k]]))));
  },

  // delete these ids, then insert these rows (two writes, like the two calls api.js makes); a row whose id is there
  // already counts as done, a row for a page that is not there is refused (the foreign key, 23503)
  async putStrokes(removedIds, added) {
    maybeFail(); maybeRefuse();
    const now = new Date().toISOString();
    if (removedIds.length) {
      const d = read(), rm = new Set(removedIds), hit = d.strokes.filter((s) => rm.has(s.id));
      d.strokes = d.strokes.filter((s) => !rm.has(s.id));
      touchPages(d, hit.map((s) => s.page_id), now);
      write(d);
    }
    if (added.length) {
      const d = read(), pages = new Set(d.pages.map((p) => p.id)), have = new Set(d.strokes.map((s) => s.id));
      const bad = added.find((r) => !pages.has(r.page_id));
      if (bad) refuse('insert or update on table "strokes" violates foreign key constraint "strokes_page_id_fkey"', '23503');
      const rows = added.filter((r) => !have.has(r.id))
        .map((r) => ({ ...clone(Object.fromEntries(STROKE_KEYS.map((k) => [k, r[k]]))), owner_id: 'local', created_at: now }));
      d.strokes.push(...rows);
      touchPages(d, rows.map((s) => s.page_id), now);
      write(d);
    }
  },

  failNext(n) { failNext = n; },
  refuseNext(n) { refuseNext = n; },
};
