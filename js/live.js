// PenWorks live mirror (U3d). A stroke written on the tablet shows on the phone (and on any other open device) about
// a second later. One channel per login while the app is open: api.subscribeStrokes(userId, handlers), which is a
// Supabase Realtime channel `strokes:<uid>` (postgres_changes on public.strokes, INSERT and DELETE) in live mode and an
// in-memory twin in ?local=1 (js/local-backend.js, driven by the tests through api.emitStroke).
// Every row goes to onRow(type, row) (app.js decides what it means: js/ink.js applyRemote). Nothing on the screen: no
// dot, no text (her ruling, the save dot is U3a's and means saving, not receiving); state() is for the tests.
// Gaps: Realtime can drop events (the tab in the background, a reconnect). After every subscribe that follows a drop
// (the first one too: rows written between load() and the subscribe) and every time the app comes back to the front,
// onGap() runs (app.js: store.reconcile of the open note's pages). On `online` and on coming back to the front, a
// channel that is not subscribed is opened again.
// Round 6b (pw-v7h): the same channel carries her notes and pages rows too; each goes to onTree(table, type, row)
// (app.js remoteTree decides whether the tree is read again). onGap(why) says why it runs: 'first' (the first
// subscribe), 'drop' (a subscribe after a dropped channel: tree rows may have been missed too) or 'front'.

const L = { api: null, userId: null, onRow: () => {}, onTree: () => {}, onGap: () => {} };
let handle = null;          // the open subscription: { unsubscribe }
let st = 'closed';          // subscribed | closed | error
let dropped = true;         // the next SUBSCRIBED follows a gap (true at start)
let on = false, wired = false, first = true;
const stats = { subscribes: 0, gaps: 0, rows: 0, tree: 0 };

export function initLive(o) {
  Object.assign(L, o);
  on = true;
  if (!wired) {
    wired = true;
    document.addEventListener('visibilitychange', () => { if (!document.hidden) front(); });
    addEventListener('online', () => { if (on && st !== 'subscribed') open(); });
  }
  open();
}

// back to the front: a closed channel opens again, and the open note catches up either way
function front() {
  if (!on) return;
  if (st !== 'subscribed') open();
  gap('front');
}

function open() {
  if (handle) { try { handle.unsubscribe(); } catch (_) { /* it was going anyway */ } }
  handle = null;
  stats.subscribes++;
  let me = null;
  const h = {
    onRow: (type, row) => {
      if (!on || handle !== me) return;
      stats.rows++;
      try { L.onRow(type, row); } catch (e) { console.warn('PenWorks: a live stroke could not be shown', e); }
    },
    onTree: (table, type, row) => {
      if (!on || handle !== me) return;
      stats.tree++;
      try { L.onTree(table, type, row); } catch (e) { console.warn('PenWorks: a live note or page could not be shown', e); }
    },
    onStatus: (s) => { if (handle === me) status(s); },
  };
  try { me = L.api.subscribeStrokes(L.userId, h); }
  catch (_) { st = 'error'; dropped = true; return; }
  handle = me;
}

function status(s) {
  if (s === 'SUBSCRIBED') {
    const gapBefore = dropped;
    st = 'subscribed'; dropped = false;
    if (gapBefore) { gap(first ? 'first' : 'drop'); first = false; }
    return;
  }
  st = s === 'CLOSED' ? 'closed' : 'error';     // CHANNEL_ERROR, TIMED_OUT
  dropped = true;
}

function gap(why) {
  stats.gaps++;
  try { L.onGap(why); } catch (_) { /* the next trigger tries again */ }
}

// logout: the channel closes and stays closed
export function stopLive() {
  on = false;
  if (handle) { try { handle.unsubscribe(); } catch (_) { /* ignore */ } }
  handle = null; st = 'closed';
}

// ---------------------------------------------------------------- for the tests (window.__pw.live)
export function state() { return st; }
export function liveStats() { return { ...stats, state: st }; }
// the channel drops the way a background tab loses it: events go nowhere until it is opened again
export function simulateDrop() {
  if (handle) { try { handle.unsubscribe(); } catch (_) { /* ignore */ } }
  handle = null; st = 'closed'; dropped = true;
}
