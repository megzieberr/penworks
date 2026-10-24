// PenWorks local twin of the database layer. Switched on with ?local=1.
// Same calls and the same row shapes as js/api.js, kept in this browser's localStorage, so the whole
// app can be built and tested without touching Supabase.

const KEY = 'penworks.local.v1';
const TABLES = ['notebooks', 'sections', 'pages'];
const DEFAULTS = {
  notebooks: { name: '', position: 0, deleted_at: null },
  sections: { notebook_id: null, name: '', position: 0, background: 'blank', deleted_at: null },
  pages: { section_id: null, title: '', position: 0, orientation: 'portrait', background: 'blank',
           snapshot_path: null, flagged: false, deleted_at: null },
};

function read() {
  try {
    const d = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (d && TABLES.every((t) => Array.isArray(d[t]))) return d;
  } catch (_) { /* fall through to an empty store */ }
  return { notebooks: [], sections: [], pages: [] };
}
function write(d) { localStorage.setItem(KEY, JSON.stringify(d)); }
function check(table) { if (!TABLES.includes(table)) throw new Error('Unknown table ' + table); }
function clone(o) { return JSON.parse(JSON.stringify(o)); }

let failNext = 0;   // test hook: make the next n writes fail, to prove the retry toast

function maybeFail() {
  if (failNext > 0) { failNext--; throw new Error('Simulated failed write'); }
}

export const localApi = {
  mode: 'local',

  async session() { return { id: 'local', username: 'local' }; },
  async signIn() { return { ok: true }; },
  async signOut() { /* nothing to end */ },

  async purgeBin(days = 30) {
    const d = read(), cut = Date.now() - days * 864e5;
    const old = (r) => r.deleted_at && Date.parse(r.deleted_at) < cut;
    let n = 0;
    const goneNb = new Set(d.notebooks.filter(old).map((r) => r.id));
    d.notebooks = d.notebooks.filter((r) => !goneNb.has(r.id));
    const goneSec = new Set(d.sections.filter((r) => old(r) || goneNb.has(r.notebook_id)).map((r) => r.id));
    d.sections = d.sections.filter((r) => !goneSec.has(r.id));
    const before = d.pages.length;
    d.pages = d.pages.filter((r) => !old(r));
    d.pages.forEach((r) => { if (goneSec.has(r.section_id)) r.section_id = null; });   // matches "on delete set null"
    n = goneNb.size + goneSec.size + (before - d.pages.length);
    write(d);
    return n;
  },

  async loadAll() {
    const d = read();
    return { notebooks: clone(d.notebooks), sections: clone(d.sections), pages: clone(d.pages) };
  },

  async insert(table, row) {
    check(table); maybeFail();
    const d = read(), now = new Date().toISOString();
    const r = { ...DEFAULTS[table], ...row, id: row.id || crypto.randomUUID(), owner_id: 'local',
                created_at: row.created_at || now, updated_at: now };
    d[table].push(r); write(d);
    return clone(r);
  },

  async update(table, ids, patch) {
    check(table); maybeFail();
    const d = read(), now = new Date().toISOString(), set = new Set(ids);
    const hit = d[table].filter((r) => set.has(r.id));
    if (hit.length !== set.size) throw new Error('Some rows were not found');
    hit.forEach((r) => Object.assign(r, patch, { updated_at: now }));
    write(d);
  },

  async remove(table, ids) {
    check(table);
    const d = read(), set = new Set(ids);
    d[table] = d[table].filter((r) => !set.has(r.id));
    if (table === 'sections') d.pages.forEach((p) => { if (set.has(p.section_id)) p.section_id = null; });
    if (table === 'notebooks') {
      const secs = new Set(d.sections.filter((s) => set.has(s.notebook_id)).map((s) => s.id));
      d.sections = d.sections.filter((s) => !secs.has(s.id));
      d.pages.forEach((p) => { if (secs.has(p.section_id)) p.section_id = null; });
    }
    write(d);
  },

  failNext(n) { failNext = n; },
};
