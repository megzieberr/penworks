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
  pages: 'id,owner_id,note_id,position,orientation,background,bookmark,snapshot_path,snapshot_at,flagged,deleted_at,created_at,updated_at',
};
// the signed-in person's own row (U3c): settings.tray = the pen tray's state (js/tray.js), settings.tray_at = when it was
// saved (newer wins across devices). pen_colours is not used: her 13 colours are code in tray.js, only their order follows her.
const PROFILE_COLS = 'id,username,display_name,pen_colours,settings';
// page pictures (U3b): bucket `snapshots`, private, one object per page at <owner uuid>/<page id>.webp (js/snap.js)
const SNAP_BUCKET = 'snapshots';
// strokes (U3a): only through strokesOf and putStrokes (js/store.js calls them); owner_id defaults to auth.uid()
const STROKE_COLS = 'id,page_id,seq,kind,style,data';
const STROKE_KEYS = STROKE_COLS.split(',');
const ROWS = 1000;     // the API hands back at most this many rows per request (Supabase's max rows): ask page by page
const CHUNK = 100;     // ids per delete and rows per insert, so no request grows too big

let sb = null;
async function client() {
  if (!sb) {
    const { createClient } = await import(SB_JS);
    sb = createClient(SB_URL, SB_KEY, { auth: { persistSession: true, autoRefreshToken: true } });
  }
  return sb;
}
function check(table) { if (!TABLES.includes(table)) throw new Error('Unknown table ' + table); }
async function me(c) {
  const { data } = await c.auth.getSession();
  if (!data.session) throw new Error('Not signed in');
  return data.session.user.id;
}
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

  // every stroke of these pages, in seq order (one query, read in pages of ROWS rows)
  async strokesOf(pageIds) {
    if (!pageIds.length) return [];
    const c = await client(), out = [];
    for (let from = 0; ; from += ROWS) {
      const { data, error } = await c.from('strokes').select(STROKE_COLS).in('page_id', pageIds)
        .order('seq').order('id').range(from, from + ROWS - 1);
      if (error) throw error;
      out.push(...data);
      if (data.length < ROWS) return out;
    }
  },

  // one queued change: delete these ids first, then insert these rows, so running it twice is harmless.
  // An insert that meets an id already there (23505) counts as done: a batch that does is sent again row by row.
  async putStrokes(removedIds, added) {
    const c = await client();
    for (let i = 0; i < removedIds.length; i += CHUNK) {
      const { error } = await c.from('strokes').delete().in('id', removedIds.slice(i, i + CHUNK));
      if (error) throw error;
    }
    const rows = added.map((r) => Object.fromEntries(STROKE_KEYS.map((k) => [k, r[k]])));
    for (let i = 0; i < rows.length; i += CHUNK) {
      const part = rows.slice(i, i + CHUNK);
      const { error } = await c.from('strokes').insert(part);
      if (!error) continue;
      if (error.code !== '23505') throw error;
      for (const r of part) {
        const { error: e } = await c.from('strokes').insert(r);
        if (e && e.code !== '23505') throw e;
      }
    }
  },

  // ---------------------------------------------------------------- page pictures (U3b, js/snap.js)
  // the picture itself, replacing the one already there. max-age 0: a download never gets an older copy from a cache.
  async putSnapshot(path, blob) {
    const c = await client();
    const { error } = await c.storage.from(SNAP_BUCKET).upload(path, blob,
      { upsert: true, contentType: blob.type || 'image/webp', cacheControl: '0' });
    if (error) throw error;
  },

  // the picture as a Blob (the bucket is private: the download carries her login)
  async getSnapshot(path) {
    const c = await client();
    const { data, error } = await c.storage.from(SNAP_BUCKET).download(path);
    if (error) throw error;
    return data;
  },

  // the page's updated_at as the database has it (null when the row is not there): taken before a render
  async pageStamp(pageId) {
    const c = await client();
    const { data, error } = await c.from('pages').select('updated_at').eq('id', pageId).maybeSingle();
    if (error) throw error;
    return data ? data.updated_at : null;
  },

  // the picture is in the bucket: the page row says where. Only when the page's updated_at is still `at` (the stamp
  // read before the render): a stroke that landed meanwhile leaves the row as it was and the answer is null.
  // snapshot_at is the literal 'now', the database's own clock: the trigger pages_updated_at (0001) sets updated_at
  // to now() on this very update, and in one transaction both are the same instant, so a fresh page reads
  // updated_at = snapshot_at and any later stroke (strokes_touch_page) makes updated_at the newer one.
  async setSnapshot(pageId, path, at) {
    const c = await client();
    let q = c.from('pages').update({ snapshot_path: path, snapshot_at: 'now' }).eq('id', pageId);
    if (at) q = q.eq('updated_at', at);
    const { data, error } = await q.select('snapshot_at');
    if (error) throw error;
    return data && data.length ? data[0].snapshot_at : null;
  },

  // the note's cover = its first page's picture (null: none yet). Not an edit: notes_updated_at fires on name only.
  async setCover(noteId, path) {
    const c = await client();
    const { data, error } = await c.from('notes').update({ cover_path: path }).eq('id', noteId).select('id');
    if (error) throw error;
    if (!data || !data.length) throw new Error('The cover was not saved');
  },

  // the tests' clean-up (the app itself never deletes a picture; the bin purge will, later)
  async removeSnapshots(paths) {
    const c = await client();
    const { error } = await c.storage.from(SNAP_BUCKET).remove(paths);
    if (error) throw error;
  },

  // ---------------------------------------------------------------- her profile row (U3c)
  async profile() {
    const c = await client(), uid = await me(c);
    const { data, error } = await c.from('profiles').select(PROFILE_COLS).eq('id', uid).maybeSingle();
    if (error) throw error;
    return data;
  },

  // patch = some keys of settings; the row's settings are read and merged here (the row is tiny), then written whole,
  // so a key another device wrote and this patch does not name stays. Answers the settings as saved.
  // whole = true: the patch IS the settings (the live test puts the row back as it found it).
  async setSettings(patch, whole = false) {
    const c = await client(), uid = await me(c);
    const { data: row, error: e1 } = await c.from('profiles').select('settings').eq('id', uid).single();
    if (e1) throw e1;
    const settings = whole ? { ...patch } : { ...((row && row.settings) || {}), ...patch };
    const { data, error } = await c.from('profiles').update({ settings }).eq('id', uid).select('settings');
    if (error) throw error;
    if (!data || !data.length) throw new Error('The settings were not saved');
    return data[0].settings;
  },

  failNext() { /* local twin only */ },
  refuseNext() { /* local twin only */ },
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
  createPage: (r) => base.insert('pages', pick(r, ['id', 'note_id', 'position', 'orientation', 'background', 'bookmark'])),
  reorderPages: (pairs) => eachPos('pages', pairs),
  setPages: (ids, patch) => base.update('pages', ids, pick(patch, ['orientation', 'background'])),
  // the bookmark (U3c, a column since 0004): not an edit, the note's "last edited" stays where it was
  setBookmark: (id, on) => base.update('pages', [id], { bookmark: !!on }),
  deletePage: (id) => base.remove('pages', [id]),             // gone for good; the app's undo puts it back

  // ids = { folders: [...], notes: [...], pages: [...] }
  bin: (ids, at) => setBin(ids, at),
  restore: (ids) => setBin(ids, null),
};
