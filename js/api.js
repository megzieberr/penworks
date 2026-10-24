// PenWorks database layer: every Supabase call lives in this file.
// js/local-backend.js is its twin (same calls, same row shapes), used when the address has ?local=1.
// The bottom half names every thing the app does (folders, notes, pages); both backends go through it.

import { localApi } from './local-backend.js';

const SB_URL = 'https://duibtdcxmnvsuczuceld.supabase.co';
const SB_KEY = 'sb_publishable_bj2rpL9bwuYSrWCnZxkAuA_uIHYRVJR';   // publishable key, safe in the app
const SB_JS = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm';
const EMAIL_DOMAIN = '@penworks.app';
const TABLES = ['folders', 'notes', 'pages'];
const COLS = {
  folders: 'id,owner_id,parent_id,name,colour,position,deleted_at,created_at,updated_at',
  notes: 'id,owner_id,folder_id,name,pinned,cover_path,deleted_at,created_at,updated_at',
  pages: 'id,owner_id,note_id,position,orientation,background,snapshot_path,flagged,deleted_at,created_at,updated_at',
};

let sb = null;
async function client() {
  if (!sb) {
    const { createClient } = await import(SB_JS);
    sb = createClient(SB_URL, SB_KEY, { auth: { persistSession: true, autoRefreshToken: true } });
  }
  return sb;
}
function check(table) { if (!TABLES.includes(table)) throw new Error('Unknown table ' + table); }
function userOf(session) {
  if (!session) return null;
  const email = session.user.email || '';
  return { id: session.user.id, username: email.endsWith(EMAIL_DOMAIN) ? email.slice(0, -EMAIL_DOMAIN.length) : email };
}

const liveApi = {
  mode: 'live',

  async session() {
    const c = await client();
    const { data } = await c.auth.getSession();
    return userOf(data.session);
  },

  // username + password; the username becomes <username>@penworks.app. No signup here: accounts are made by SQL.
  async signIn(username, password) {
    const name = String(username || '').trim().toLowerCase();
    if (!name || !password) return { ok: false, message: 'Type your username and password.' };
    let c;
    try { c = await client(); } catch (_) { return { ok: false, message: 'Could not reach PenWorks. Check the connection.' }; }
    const { data, error } = await c.auth.signInWithPassword({ email: name + EMAIL_DOMAIN, password });
    if (error) {
      const wrong = error.status === 400 || /invalid/i.test(error.message || '');
      return { ok: false, message: wrong ? 'That username or password is not right.' : 'Could not reach PenWorks. Check the connection.' };
    }
    return { ok: true, user: userOf(data.session) };
  },

  async signOut() { const c = await client(); await c.auth.signOut(); },

  // empties this person's bin of anything older than 30 days; the number it returns is not needed
  async purgeBin(days = 30) {
    const c = await client();
    const { data, error } = await c.rpc('purge_bin', { days });
    if (error) throw error;
    return data;
  },

  async loadAll() {
    const c = await client();
    const [f, n, p] = await Promise.all(TABLES.map((t) => c.from(t).select(COLS[t])));
    for (const r of [f, n, p]) if (r.error) throw r.error;
    return { folders: f.data, notes: n.data, pages: p.data };
  },

  // the database refuses a third folder level itself (trigger folders_two_levels, migration 0003)
  async insert(table, row) {
    check(table);
    const c = await client();
    const { data, error } = await c.from(table).insert(row).select(COLS[table]).single();
    if (error) throw error;
    return data;
  },

  // patch several rows at once; a row that RLS hides counts as a failed write, never a silent one
  async update(table, ids, patch) {
    check(table);
    const c = await client();
    const { data, error } = await c.from(table).update(patch).in('id', ids).select('id');
    if (error) throw error;
    if (!data || data.length !== new Set(ids).size) throw new Error('Not every row was saved');
  },

  // hard delete: a page deleted for good, and the tests cleaning up (the bin itself purges after 30 days)
  async remove(table, ids) {
    check(table);
    const c = await client();
    const { error } = await c.from(table).delete().in('id', ids);
    if (error) throw error;
  },

  failNext() { /* local twin only */ },
};

const base = new URLSearchParams(location.search).has('local') ? localApi : liveApi;
const pick = (r, keys) => Object.fromEntries(keys.filter((k) => k in r).map((k) => [k, r[k]]));
const eachPos = async (table, pairs) => { for (const [id, position] of pairs) await base.update(table, [id], { position }); };

// bin and restore: one timestamp for everything binned together, so restore brings back exactly that
async function setBin(ids, value) {
  for (const t of ['folders', 'notes', 'pages']) if (ids[t] && ids[t].length) await base.update(t, ids[t], { deleted_at: value });
}

export const api = {
  ...base,

  // folders: a top folder (parent_id null) or a sub-folder of a top folder, never deeper
  createFolder: (r) => base.insert('folders', pick(r, ['id', 'parent_id', 'name', 'colour', 'position'])),
  renameFolder: (id, name) => base.update('folders', [id], { name }),
  recolourFolder: (id, colour) => base.update('folders', [id], { colour }),
  moveFolder: (id, parent_id, position) => base.update('folders', [id], { parent_id, position }),
  reorderFolders: (pairs) => eachPos('folders', pairs),

  // notes: folder_id null = Loose; no position, the app orders them (pinned, then last edited)
  createNote: (r) => base.insert('notes', pick(r, ['id', 'folder_id', 'name', 'pinned'])),
  renameNote: (id, name) => base.update('notes', [id], { name }),
  moveNote: (id, folder_id) => base.update('notes', [id], { folder_id }),
  pinNote: (id, pinned) => base.update('notes', [id], { pinned }),

  // pages: numbered by position inside their note
  createPage: (r) => base.insert('pages', pick(r, ['id', 'note_id', 'position', 'orientation', 'background'])),
  reorderPages: (pairs) => eachPos('pages', pairs),
  setPages: (ids, patch) => base.update('pages', ids, pick(patch, ['orientation', 'background'])),
  deletePage: (id) => base.remove('pages', [id]),             // gone for good; the app's undo puts it back

  // ids = { folders: [...], notes: [...], pages: [...] }
  bin: (ids, at) => setBin(ids, at),
  restore: (ids) => setBin(ids, null),
};
