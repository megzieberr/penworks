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
  pages: 'id,owner_id,note_id,position,orientation,background,bookmark,pdf_path,pdf_page,pdf_w,pdf_h,pdf_rot,snapshot_path,snapshot_at,flagged,deleted_at,created_at,updated_at,kind,anchor_id,sk_x,sk_y,sk_w,sk_colour',
};
// U4a: pdf_w and pdf_h exist from migration 0005 on; until it is applied every loadAll above fails on the live project.
// pw-v7p: the same for pdf_rot and migration 0006: the migration lands BEFORE the push.
// pw-v9c: the same for the sticky columns (kind, anchor_id, sk_x, sk_y, sk_w, sk_colour) and migration 0007: 0007 lands BEFORE the push.
// the signed-in person's own row (U3c): settings.tray = the pen tray's state (js/tray.js), settings.tray_at = when it was
// saved (newer wins across devices). pen_colours is not used: her 13 colours are code in tray.js, only their order follows her.
const PROFILE_COLS = 'id,username,display_name,pen_colours,settings';
// page pictures (U3b): bucket `snapshots`, private, one object per page at <owner uuid>/<page id>.webp (js/snap.js)
const SNAP_BUCKET = 'snapshots';
// PDFs opened into notes (U4a): bucket `imports`, private, one object per opened file at <owner uuid>/<uuid>.pdf (js/pdfin.js).
// The app never deletes one (a deleted page leaves its PDF where it is); only the tests' clean-up does.
const IMPORT_BUCKET = 'imports';
// strokes (U3a): only through strokesOf and putStrokes (js/store.js calls them); owner_id defaults to auth.uid()
const STROKE_COLS = 'id,page_id,seq,kind,style,data';
const STROKE_KEYS = STROKE_COLS.split(',');
const ROWS = 1000;     // the API hands back at most this many rows per request (Supabase's max rows): ask page by page
const CHUNK = 100;     // ids per delete and rows per insert, so no request grows too big
const IDS = 100;       // pw-v9s: ids per request address (600 still works, 700 is refused)

let sb = null;
let leaving = Promise.resolve();   // U3d: a strokes channel being closed, so the next one never joins on top of it
// pw-v9n, the sign-in check: where supabase-js keeps her sign-in on this device (its default storage key)
const SESSION_KEY = 'sb-' + new URL(SB_URL).hostname.split('.')[0] + '-auth-token';
const SESSION_MS = 3000;           // getSession() gets this long; then the app opens on the kept sign-in
// the sign-in kept on this device, or null (none, unreadable, or not a whole session): the same test supabase-js makes
function keptSession() {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY));
    return s && typeof s === 'object' && s.access_token && s.refresh_token && 'expires_at' in s && s.user && s.user.id ? s : null;
  } catch (_) { return null; }
}
// pw-v9n, rule C: supabase-js sends a data request whose token it could not refresh with NO sign-in (the publishable key
// as Bearer); the database refuses it (RLS) and the tree queue drops a refusal. Such a request never leaves: it fails
// like no connection (no code), so both queues wait and try again. Exempt: the auth calls themselves (the refresh, the
// sign-in) and the login lock's question (login_gate is asked before any sign-in, by design).
function guardedFetch(input, init) {
  const url = String((input && input.url) || input);
  const auth = new Headers((init && init.headers) || (input && input.headers) || {}).get('Authorization');
  if (auth === 'Bearer ' + SB_KEY && url.startsWith(SB_URL + '/') && !url.startsWith(SB_URL + '/auth/v1/')
      && !url.startsWith(SB_URL + '/rest/v1/rpc/login_gate')) {
    return Promise.reject(new TypeError('Failed to fetch: not signed in yet'));
  }
  return fetch(input, init);
}
async function client() {
  if (!sb) {
    const { createClient } = await import(SB_JS);
    sb = createClient(SB_URL, SB_KEY, { auth: { persistSession: true, autoRefreshToken: true }, global: { fetch: guardedFetch } });
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

  // pw-v9n, the sign-in check: an expired token makes getSession() refresh over the network, with no time limit (dead
  // wifi: never). After SESSION_MS the app opens on the sign-in kept on this device and the refresh carries on in the
  // background. A refresh that FAILED for a network reason (supabase-js keeps the session then) also opens on the kept
  // one; a real refusal removes it (supabase-js), so the login shows. Nothing kept: wait for getSession() as before
  // (with no session it answers at once, without the network).
  async session() {
    const c = await client();
    const ask = c.auth.getSession().then(({ data, error }) => {
      if (data.session) return userOf(data.session);
      if (error && error.name === 'AuthRetryableFetchError') return userOf(keptSession());
      return null;
    });
    const kept = keptSession();
    if (!kept) return ask;
    let t;
    const late = new Promise((ok) => { t = setTimeout(() => ok(userOf(keptSession())), SESSION_MS); });
    return Promise.race([ask, late]).finally(() => clearTimeout(t));
  },

  // username + password; the username becomes <username>@penworks.app. No signup here: accounts are made by SQL.
  async signIn(username, password) {
    const name = String(username || '').trim().toLowerCase();
    if (!name || !password) return { ok: false, message: 'Type your username and password.' };
    let c;
    try { c = await client(); } catch (_) { return { ok: false, message: 'Could not reach PenWorks. Check the connection.' }; }
    const OFF = 'Could not reach PenWorks. Check the connection.';
    const login = async (pwd, refused) => {
      const { data, error } = await c.auth.signInWithPassword({ email: name + EMAIL_DOMAIN, password: pwd });
      if (error) {
        const wrong = error.status === 400 || /invalid/i.test(error.message || '');
        return { ok: false, message: wrong ? refused : OFF };
      }
      return { ok: true, user: userOf(data.session) };
    };
    const oldWay = () => login(password, 'That username or password is not right.');
    // pw-v9h: the login lock (migration 0008). A short code is asked of login_gate first (it counts wrong tries and locks);
    // a right code hands back the long secret, the real password. A long password (the laptop tools' secret) never asks.
    // No gate function yet (PGRST202) or no gate row for this person ('none'): the old way.
    const code = String(password);
    if (code.length >= 32) return oldWay();
    let g;
    try { g = await c.rpc('login_gate', { p_username: name, p_code: code }); } catch (_) { return { ok: false, message: OFF }; }
    if (g.error) return g.error.code === 'PGRST202' ? oldWay() : { ok: false, message: OFF };
    const a = g.data || {};
    if (a.status === 'none') return oldWay();
    if (a.status === 'wrong') {
      const left = typeof a.left === 'number' ? (a.left === 1 ? ' 1 try left.' : ' ' + a.left + ' tries left.') : '';
      return { ok: false, message: 'That password is not right.' + left };
    }
    if (a.status === 'locked') {
      const u = new Date(a.until), now = new Date();
      if (isNaN(u)) return { ok: false, message: 'Too many wrong tries. Try again later.' };
      const hm = String(u.getHours()).padStart(2, '0') + ':' + String(u.getMinutes()).padStart(2, '0');
      const day = u.toDateString() === now.toDateString() ? '' : 'tomorrow ';
      return { ok: false, message: 'Too many wrong tries. Try again ' + day + 'at ' + hm + '.' };
    }
    if (a.status !== 'ok' || !a.secret) return { ok: false, message: OFF };
    return login(a.secret, 'The login lock and the password do not match. Ask Claude to check it.');
  },

  async signOut() { const c = await client(); await c.auth.signOut(); },

  // empties this person's bin of anything older than 30 days; the number it returns is not needed
  async purgeBin(days = 30) {
    const c = await client();
    const { data, error } = await c.rpc('purge_bin', { days });
    if (error) throw error;
    return data;
  },

  // pw-v8o (4 Nov): every row, read in pages of ROWS rows. One plain select stops at Supabase's 1000 rows; her 1025
  // page rows hid the most recently written pages (her Sept P2 Q4 and Q5 d) and a paste then renumbered without them.
  async loadAll() {
    const c = await client();
    const all = async (t) => {
      const out = [];
      for (let from = 0; ; from += ROWS) {
        const { data, error } = await c.from(t).select(COLS[t]).order('id').range(from, from + ROWS - 1);
        if (error) throw error;
        out.push(...data);
        if (data.length < ROWS) return out;
      }
    };
    const [folders, notes, pages] = await Promise.all(TABLES.map(all));
    return { folders, notes, pages };
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

  // every stroke of these pages, in seq order (one query, read in pages of ROWS rows). pw-v9s: at most IDS ids a call
  // (the api below splits a longer list and joins the answers)
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
  // pw-v9v: a failure carries the answer's HTTP status (0 = no answer), so store.js can tell a refusal from a lost connection
  async putStrokes(removedIds, added) {
    const c = await client();
    const st = (e, status) => { try { e.status = status || 0; } catch (_) { /* keep the error as it is */ } return e; };
    for (let i = 0; i < removedIds.length; i += CHUNK) {
      const { error, status } = await c.from('strokes').delete().in('id', removedIds.slice(i, i + CHUNK));
      if (error) throw st(error, status);
    }
    const rows = added.map((r) => Object.fromEntries(STROKE_KEYS.map((k) => [k, r[k]])));
    for (let i = 0; i < rows.length; i += CHUNK) {
      const part = rows.slice(i, i + CHUNK);
      const { error, status } = await c.from('strokes').insert(part);
      if (!error) continue;
      if (error.code !== '23505') throw st(error, status);
      for (const r of part) {
        const { error: e, status: s } = await c.from('strokes').insert(r);
        if (e && e.code !== '23505') throw st(e, s);
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

  // pw-v9s: id and updated_at of these pages (at most IDS ids), fresh from the database; a page not there is left out
  async pageStamps(pageIds) {
    if (!pageIds.length) return [];
    const c = await client();
    const { data, error } = await c.from('pages').select('id,updated_at').in('id', pageIds);
    if (error) throw error;
    return data || [];
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

  // ---------------------------------------------------------------- opened PDFs (U4a, js/pdfin.js)
  // upsert: an upload that landed but whose answer was lost goes again harmlessly (the same bytes at the same path)
  // U4c: a picture goes up as what it is (image/png or image/jpeg, the bucket allows both); a PDF as before
  async putImport(path, blob) {
    const c = await client();
    const type = /\.png$/i.test(path) ? 'image/png' : /\.jpe?g$/i.test(path) ? 'image/jpeg' : 'application/pdf';
    const { error } = await c.storage.from(IMPORT_BUCKET).upload(path, blob,
      { upsert: true, contentType: type, cacheControl: '3600' });
    if (error) throw error;
  },
  async getImport(path) {
    const c = await client();
    const { data, error } = await c.storage.from(IMPORT_BUCKET).download(path);
    if (error) throw error;
    return data;
  },
  async removeImports(paths) {        // the tests' clean-up only
    const c = await client();
    const { error } = await c.storage.from(IMPORT_BUCKET).remove(paths);
    if (error) throw error;
  },
  // the live test: false while migration 0005 is not applied (the columns pdf_w, pdf_h are missing)
  async pdfColumns() {
    const c = await client();
    const { error } = await c.from('pages').select('pdf_w,pdf_h').limit(1);
    if (error && (error.code === '42703' || /pdf_w|pdf_h/.test(error.message || ''))) return false;
    if (error) throw error;
    return true;
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

  // ---------------------------------------------------------------- the live mirror (U3d, js/live.js)
  // One Realtime channel `strokes:<uid>`; h = { onRow(type, row), onStatus(status) }, status as supabase-js names it
  // (SUBSCRIBED, CLOSED, CHANNEL_ERROR, TIMED_OUT). INSERT carries the whole row and is filtered to her rows (RLS limits
  // the authenticated role to them anyway). DELETE carries only old.id (the default replica identity) and Supabase cannot
  // filter DELETE events (a filter on owner_id would never match an old row that holds only the id), so that listener has
  // no filter: an id that is not one of hers matches no stroke on this device and is ignored. The socket carries her
  // login (setAuth), so RLS sees her. Answers { unsubscribe }.
  // Round 6b (pw-v7h): the same channel also carries her notes and pages rows to h.onTree(table, type, row): INSERT and
  // UPDATE filtered to her rows (the whole new row), DELETE unfiltered (only old.id, as for strokes). The database
  // publishes notes and pages on supabase_realtime; folders are not published, so a folder change still waits for the
  // tree refresh.
  subscribeStrokes(userId, h) {
    let ch = null, dead = false;
    (async () => {
      const c = await client();
      await leaving;
      if (dead) return;
      try { const { data } = await c.auth.getSession(); if (data.session) c.realtime.setAuth(data.session.access_token); }
      catch (_) { /* the client sets it itself on sign-in */ }
      if (dead) return;
      const where = { schema: 'public', table: 'strokes' };
      ch = c.channel('strokes:' + userId)
        .on('postgres_changes', { ...where, event: 'INSERT', filter: 'owner_id=eq.' + userId }, (p) => h.onRow('INSERT', p.new))
        .on('postgres_changes', { ...where, event: 'DELETE' }, (p) => h.onRow('DELETE', p.old));
      if (h.onTree) {
        for (const table of ['notes', 'pages']) {
          const t = { schema: 'public', table };
          ch = ch
            .on('postgres_changes', { ...t, event: 'INSERT', filter: 'owner_id=eq.' + userId }, (p) => h.onTree(table, 'INSERT', p.new))
            .on('postgres_changes', { ...t, event: 'UPDATE', filter: 'owner_id=eq.' + userId }, (p) => h.onTree(table, 'UPDATE', p.new))
            .on('postgres_changes', { ...t, event: 'DELETE' }, (p) => h.onTree(table, 'DELETE', p.old));
        }
      }
      ch.subscribe((status) => { if (!dead) h.onStatus(status); });
    })().catch(() => { if (!dead) h.onStatus('CHANNEL_ERROR'); });
    return {
      unsubscribe() {
        dead = true;
        if (ch && sb) { const gone = ch; ch = null; leaving = sb.removeChannel(gone).catch(() => {}); }
      },
    };
  },

  failNext() { /* local twin only */ },
  refuseNext() { /* local twin only */ },
  failStatus() { /* local twin only */ },
  emitStroke() { /* local twin only */ },
  callLog() { return []; },   // local twin only (U3e)
};

const base = new URLSearchParams(location.search).has('local') ? localApi : liveApi;
// pw-v9c: a sticky's own columns; a page row never carries them (pick leaves out the keys a row does not have)
const STICKY_KEYS = ['kind', 'anchor_id', 'sk_x', 'sk_y', 'sk_w', 'sk_colour'];
const pick = (r, keys) => Object.fromEntries(keys.filter((k) => k in r).map((k) => [k, r[k]]));
const eachPos = async (table, pairs) => { for (const [id, position] of pairs) await base.update(table, [id], { position }); };

// pw-v9s: a list of ids goes IDS at a time, one request after another; the first failed part fails the whole call
async function byIds(ids, fn) {
  const all = [...new Set(ids)], out = [];
  for (let i = 0; i < all.length; i += IDS) out.push(...((await fn(all.slice(i, i + IDS))) || []));
  return out;
}
const seqOrder = (a, b) => (a.seq - b.seq) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);   // the database's order by seq, id

// bin and restore: one timestamp for everything binned together, so restore brings back exactly that
async function setBin(ids, value) {
  for (const t of ['folders', 'notes', 'pages']) if (ids[t] && ids[t].length) await base.update(t, ids[t], { deleted_at: value });
}

export const api = {
  ...base,
  // pw-v9s: the ink of any number of pages, IDS page ids a request, joined in seq order. strokesPart and stampsPart are
  // one request each, looked up at call time so the checks can count them and fail one.
  strokesOf: async (pageIds) => (await byIds(pageIds, (part) => api.strokesPart(part))).sort(seqOrder),
  strokesPart: (part) => base.strokesOf(part),
  pageStamps: (pageIds) => byIds(pageIds, (part) => api.stampsPart(part)),
  stampsPart: (part) => base.pageStamps(part),

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
  // U4a: a page made from a PDF page carries pdf_path, pdf_page (1-based), pdf_w and pdf_h (that page's size in points)
  createPage: (r) => base.insert('pages', pick(r, ['id', 'note_id', 'position', 'orientation', 'background', 'bookmark',
    ...(r.pdf_path ? ['pdf_path', 'pdf_page', 'pdf_w', 'pdf_h', 'pdf_rot'] : []), ...STICKY_KEYS])),
  reorderPages: (pairs) => eachPos('pages', pairs),
  // pw-v9b: pages that change note (a merge, the page list's To note, an undo of either): rows = [[id, note_id, position], ...].
  // No new column: pages.note_id and position were always there; the touch trigger marks the note they join as edited.
  movePagesTo: async (rows) => { for (const [id, note_id, position] of rows) await base.update('pages', [id], { note_id, position }); },
  setPages: (ids, patch) => base.update('pages', ids, pick(patch, ['orientation', 'background', 'pdf_rot'])),
  // the bookmark (U3c, a column since 0004): not an edit, the note's "last edited" stays where it was
  setBookmark: (id, on) => base.update('pages', [id], { bookmark: !!on }),
  deletePage: (id) => base.remove('pages', [id]),             // gone for good; the app's undo puts it back
  // pw-v9c: a sticky (a pages row, kind 'sticky'): where it sits, its size, its colour, the page it hangs on; one update.
  // A move or a resize is a note edit like any page update: whatever the touch trigger does, nothing special here.
  setSticky: (id, patch) => base.update('pages', [id], pick(patch, ['anchor_id', 'sk_x', 'sk_y', 'sk_w', 'sk_colour'])),

  // ids = { folders: [...], notes: [...], pages: [...] }
  bin: (ids, at) => setBin(ids, at),
  restore: (ids) => setBin(ids, null),
};
