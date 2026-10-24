// PenWorks database layer: every Supabase call lives in this file.
// js/local-backend.js is its twin (same calls, same row shapes), used when the address has ?local=1.

import { localApi } from './local-backend.js';

const SB_URL = 'https://duibtdcxmnvsuczuceld.supabase.co';
const SB_KEY = 'sb_publishable_bj2rpL9bwuYSrWCnZxkAuA_uIHYRVJR';   // publishable key, safe in the app
const SB_JS = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm';
const EMAIL_DOMAIN = '@penworks.app';
const TABLES = ['notebooks', 'sections', 'pages'];
const COLS = {
  notebooks: 'id,owner_id,name,position,deleted_at,created_at,updated_at',
  sections: 'id,owner_id,notebook_id,name,position,background,deleted_at,created_at,updated_at',
  pages: 'id,owner_id,section_id,title,position,orientation,background,snapshot_path,flagged,deleted_at,created_at,updated_at',
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
    const [nb, sec, pg] = await Promise.all(TABLES.map((t) => c.from(t).select(COLS[t])));
    for (const r of [nb, sec, pg]) if (r.error) throw r.error;
    return { notebooks: nb.data, sections: sec.data, pages: pg.data };
  },

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

  // hard delete: not used by the app (the bin does that after 30 days); the U1 test uses it to clean up
  async remove(table, ids) {
    check(table);
    const c = await client();
    const { error } = await c.from(table).delete().in('id', ids);
    if (error) throw error;
  },
};

export const api = new URLSearchParams(location.search).has('local') ? localApi : liveApi;
