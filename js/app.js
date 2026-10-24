// PenWorks U1: login, the tree (notebooks > sections > pages, Loose, Bin), the page area, autosave.
import { api } from './api.js';
import { initPage, showPage, fit } from './page.js';

const $ = (id) => document.getElementById(id);
const S = { notebooks: [], sections: [], pages: [], openPage: null, openSec: null, binOpen: false, renaming: null, user: null };
const OPEN_KEY = 'penworks.open.' + api.mode;
const DAY = 864e5;

// ---------------------------------------------------------------- small helpers
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) el.append(c);
  return el;
}
const byPos = (a, b) => (a.position - b.position) || String(a.created_at).localeCompare(String(b.created_at));
const nb = (id) => S.notebooks.find((r) => r.id === id);
const sec = (id) => S.sections.find((r) => r.id === id);
const pg = (id) => S.pages.find((r) => r.id === id);
const liveNb = (r) => r && !r.deleted_at;
const liveSec = (r) => r && !r.deleted_at && liveNb(nb(r.notebook_id));
const livePage = (r) => r && !r.deleted_at && (r.section_id === null || liveSec(sec(r.section_id)));
const notebooks = () => S.notebooks.filter(liveNb).sort(byPos);
const sectionsOf = (nbId) => S.sections.filter((r) => r.notebook_id === nbId && liveSec(r)).sort(byPos);
const pagesOf = (secId) => S.pages.filter((r) => (r.section_id || null) === (secId || null) && livePage(r)).sort(byPos);
const nbCount = (nbId) => sectionsOf(nbId).reduce((n, s) => n + pagesOf(s.id).length, 0);
const nextPos = (rows) => rows.reduce((m, r) => Math.max(m, r.position + 1), 0);
const shortDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
const pageLabel = (p) => p.title || 'Page ' + shortDate(p.created_at);
const same = (a, b) => a && b && Date.parse(a) === Date.parse(b);
const TABLE = { nb: 'notebooks', sec: 'sections', pg: 'pages' };
const rowOf = (kind, id) => S[TABLE[kind]].find((r) => r.id === id);

// what shows in the Bin: binned things whose parents are still live (children binned with them travel along)
function binItems() {
  const out = [];
  S.notebooks.filter((r) => r.deleted_at).forEach((r) => out.push({ kind: 'nb', r }));
  S.sections.filter((r) => r.deleted_at && liveNb(nb(r.notebook_id))).forEach((r) => out.push({ kind: 'sec', r }));
  S.pages.filter((r) => r.deleted_at && (r.section_id === null || liveSec(sec(r.section_id)))).forEach((r) => out.push({ kind: 'pg', r }));
  return out.sort((a, b) => Date.parse(b.r.deleted_at) - Date.parse(a.r.deleted_at));
}

let toastT = null;
function toast(msg, ms = 2600) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), ms);
}

// ---------------------------------------------------------------- autosave: writes go out in order, one retry
let chain = Promise.resolve();
let failed = 0;
function save(fn) {
  chain = chain.then(async () => {
    try { await fn(); }
    catch (_) {
      toast('Not saved, trying again');
      await new Promise((r) => setTimeout(r, 1500));
      try { await fn(); }
      catch (e2) { failed++; toast('Still not saved. Check the connection, then reload.', 6000); console.warn(e2); }
    }
  });
  return chain;
}
const patch = (table, ids, p) => save(() => api.update(table, ids, p));

function remember() {
  try { localStorage.setItem(OPEN_KEY, JSON.stringify({ page: S.openPage, sec: S.openSec })); } catch (_) { /* ignore */ }
}

// ---------------------------------------------------------------- actions
function openPage(id) {
  const p = pg(id);
  if (!p || !livePage(p)) { S.openPage = null; render(); return; }
  S.openPage = id; S.openSec = p.section_id || 'loose';
  remember(); closeDrawer(); render(true);
}
function openSection(key) {
  S.openSec = key;
  const first = pagesOf(key === 'loose' ? null : key)[0];
  if (first) openPage(first.id); else { S.openPage = null; remember(); render(true); }
}

function addNotebook() {
  const r = { id: crypto.randomUUID(), name: 'New notebook', position: nextPos(S.notebooks), deleted_at: null, created_at: new Date().toISOString() };
  S.notebooks.push(r);
  save(() => api.insert('notebooks', { id: r.id, name: r.name, position: r.position }));
  S.renaming = { kind: 'nb', id: r.id }; render();
}
function addSection(nbId) {
  const r = { id: crypto.randomUUID(), notebook_id: nbId, name: 'New section', position: nextPos(S.sections.filter((s) => s.notebook_id === nbId)),
              background: 'blank', deleted_at: null, created_at: new Date().toISOString() };
  S.sections.push(r);
  save(() => api.insert('sections', { id: r.id, notebook_id: nbId, name: r.name, position: r.position }));
  S.openSec = r.id; S.openPage = null; remember();
  S.renaming = { kind: 'sec', id: r.id }; render(true);
}
// a new page lands in the open section, or Loose; "below" puts it straight after the open page
function addPage(below) {
  const secId = S.openSec && S.openSec !== 'loose' && liveSec(sec(S.openSec)) ? S.openSec : null;
  const list = pagesOf(secId);
  const cur = pg(S.openPage);
  const model = cur && (cur.section_id || null) === secId ? cur : null;
  let position = nextPos(S.pages.filter((p) => (p.section_id || null) === secId));
  if (below && model) {
    const i = list.findIndex((p) => p.id === model.id);
    list.slice(i + 1).forEach((p, k) => {
      const np = model.position + 2 + k;
      if (p.position !== np) { p.position = np; patch('pages', [p.id], { position: np }); }
    });
    position = model.position + 1;
  }
  const r = { id: crypto.randomUUID(), section_id: secId, title: '', position,
              orientation: model ? model.orientation : 'portrait',
              background: model ? model.background : (secId ? sec(secId).background : 'blank'),
              deleted_at: null, created_at: new Date().toISOString() };
  S.pages.push(r);
  save(() => api.insert('pages', { id: r.id, section_id: r.section_id, title: '', position: r.position,
                                    orientation: r.orientation, background: r.background }));
  openPage(r.id);
}

function rename(kind, id, value) {
  const r = rowOf(kind, id); if (!r) return;
  const field = kind === 'pg' ? 'title' : 'name';
  let v = value.trim().slice(0, 120);
  if (!v && kind !== 'pg') v = r[field];        // notebooks and sections always keep a name
  if (v === r[field]) return;
  r[field] = v; patch(TABLE[kind], [id], { [field]: v });
}

function moveTo(kind, id, target) {
  const r = rowOf(kind, id);
  if (kind === 'pg') {
    r.section_id = target; r.position = nextPos(S.pages.filter((p) => (p.section_id || null) === target && p.id !== id));
    patch('pages', [id], { section_id: target, position: r.position });
    if (S.openPage === id) { S.openSec = target || 'loose'; remember(); }
  } else if (kind === 'sec') {
    r.notebook_id = target; r.position = nextPos(S.sections.filter((s) => s.notebook_id === target && s.id !== id));
    patch('sections', [id], { notebook_id: target, position: r.position });
  }
  render(true);
}

function siblings(kind, r) {
  if (kind === 'nb') return notebooks();
  if (kind === 'sec') return sectionsOf(r.notebook_id);
  return pagesOf(r.section_id || null);
}
function moveStep(kind, id, dir) {
  const r = rowOf(kind, id), list = siblings(kind, r), i = list.indexOf(r), j = i + dir;
  if (j < 0 || j >= list.length) return;
  [list[i], list[j]] = [list[j], list[i]];
  list.forEach((x, k) => { if (x.position !== k) { x.position = k; patch(TABLE[kind], [x.id], { position: k }); } });
  render(true);
}

function bin(kind, id) {
  const T = new Date().toISOString();
  const ids = { notebooks: [], sections: [], pages: [] };
  const r = rowOf(kind, id);
  ids[TABLE[kind]].push(id);
  const secs = kind === 'nb' ? S.sections.filter((s) => s.notebook_id === id && !s.deleted_at) : kind === 'sec' ? [r] : [];
  if (kind === 'nb') ids.sections = secs.map((s) => s.id);
  secs.forEach((s) => S.pages.filter((p) => p.section_id === s.id && !p.deleted_at).forEach((p) => ids.pages.push(p.id)));
  for (const t of Object.keys(ids)) {
    if (!ids[t].length) continue;
    S[t].forEach((x) => { if (ids[t].includes(x.id)) x.deleted_at = T; });
    patch(t, ids[t], { deleted_at: T });
  }
  if (S.openPage && !livePage(pg(S.openPage))) {
    const list = S.openSec && S.openSec !== 'loose' && liveSec(sec(S.openSec)) ? pagesOf(S.openSec) : S.openSec === 'loose' ? pagesOf(null) : [];
    S.openPage = list[0] ? list[0].id : null;
    if (!S.openPage && S.openSec !== 'loose' && !liveSec(sec(S.openSec))) S.openSec = null;
    remember();
  }
  toast('Moved to the Bin. It stays there for 30 days.');
  render(true);
}

function restore(kind, id) {
  const r = rowOf(kind, id), T = r.deleted_at;
  const ids = { notebooks: [], sections: [], pages: [] };
  ids[TABLE[kind]].push(id);
  const secs = kind === 'nb' ? S.sections.filter((s) => s.notebook_id === id && same(s.deleted_at, T)) : kind === 'sec' ? [r] : [];
  if (kind === 'nb') ids.sections = secs.map((s) => s.id);
  secs.forEach((s) => S.pages.filter((p) => p.section_id === s.id && same(p.deleted_at, T)).forEach((p) => ids.pages.push(p.id)));
  for (const t of Object.keys(ids)) {
    if (!ids[t].length) continue;
    S[t].forEach((x) => { if (ids[t].includes(x.id)) x.deleted_at = null; });
    patch(t, ids[t], { deleted_at: null });
  }
  toast('Restored.');
  render(true);
}

// ---------------------------------------------------------------- menu (long-press or the small dots)
function closeMenu() { $('menu').hidden = true; $('menu').textContent = ''; }
function openMenu(anchor, items) {
  const m = $('menu'); m.textContent = '';
  for (const it of items) {
    if (it.head) m.append(h('div', { class: 'hd' }, it.head));
    else m.append(h('button', { type: 'button', class: it.on ? 'on' : '', role: 'menuitem',
      onclick: (e) => { e.stopPropagation(); if (!it.keep) closeMenu(); it.fn(); } }, it.label));
  }
  m.hidden = false;
  const a = anchor.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(innerWidth - mw - 8, a.right - mw)) + 'px';
  m.style.top = (a.bottom + mh + 8 < innerHeight ? a.bottom + 4 : Math.max(8, a.top - mh - 4)) + 'px';
}
function rowMenu(kind, id, anchor) {
  const r = rowOf(kind, id), list = siblings(kind, r), i = list.indexOf(r);
  const items = [{ label: 'Rename', fn: () => { S.renaming = { kind, id }; render(); } }];
  if (kind !== 'nb') items.push({ label: 'Move to...', keep: true, fn: () => moveMenu(kind, id, anchor) });
  if (i > 0) items.push({ label: 'Move up', fn: () => moveStep(kind, id, -1) });
  if (i < list.length - 1) items.push({ label: 'Move down', fn: () => moveStep(kind, id, 1) });
  items.push({ label: 'Put in the Bin', fn: () => bin(kind, id) });
  openMenu(anchor, items);
}
function moveMenu(kind, id, anchor) {
  const r = rowOf(kind, id), items = [{ head: 'Move to' }];
  if (kind === 'pg') {
    if (r.section_id !== null) items.push({ label: 'Loose', fn: () => moveTo('pg', id, null) });
    for (const n of notebooks()) for (const s of sectionsOf(n.id)) {
      if (s.id !== r.section_id) items.push({ label: n.name + ' / ' + s.name, fn: () => moveTo('pg', id, s.id) });
    }
  } else {
    for (const n of notebooks()) if (n.id !== r.notebook_id) items.push({ label: n.name, fn: () => moveTo('sec', id, n.id) });
  }
  if (items.length === 1) items.push({ head: 'There is nowhere else to move it yet.' });
  openMenu(anchor, items);
}

// long-press on touch, right-click on a laptop, or the small dots
function pressable(el, open) {
  let t = null, fired = false, s0 = null;
  el.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button, input') || e.button > 0) return;
    fired = false; s0 = [e.clientX, e.clientY];
    t = setTimeout(() => { fired = true; open(); }, 550);
  });
  el.addEventListener('pointermove', (e) => { if (t && s0 && Math.hypot(e.clientX - s0[0], e.clientY - s0[1]) > 8) clearTimeout(t); });
  for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) el.addEventListener(ev, () => clearTimeout(t));
  el.addEventListener('click', (e) => { if (fired) { e.stopPropagation(); e.preventDefault(); fired = false; } }, true);
  el.addEventListener('contextmenu', (e) => { e.preventDefault(); clearTimeout(t); open(); });
}

// ---------------------------------------------------------------- the tree
function nameOrInput(kind, id, text) {
  if (!S.renaming || S.renaming.kind !== kind || S.renaming.id !== id) return h('span', { class: 'name' }, text);
  const r = rowOf(kind, id);
  const inp = h('input', { class: 'rename', value: kind === 'pg' ? r.title : r.name, 'aria-label': 'Name',
                           placeholder: kind === 'pg' ? pageLabel({ ...r, title: '' }) : '' });
  let done = false;
  const finish = (keep) => { if (done) return; done = true; if (keep) rename(kind, id, inp.value); S.renaming = null; render(); };
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false); });
  inp.addEventListener('blur', () => finish(true));
  inp.addEventListener('click', (e) => e.stopPropagation());
  setTimeout(() => { inp.focus(); inp.select(); }, 0);
  return inp;
}
function row(kind, id, cls, text, count, onTap) {
  const el = h('div', { class: 'row ' + cls, 'data-kind': kind, 'data-id': id, onclick: onTap },
    nameOrInput(kind, id, text),
    count === null ? null : h('span', { class: 'count' }, String(count)),
    h('button', { class: 'more', type: 'button', 'aria-label': 'More', onclick: (e) => { e.stopPropagation(); rowMenu(kind, id, e.currentTarget); } }, '⋯'));
  pressable(el, () => rowMenu(kind, id, el.querySelector('.more')));
  return el;
}
function pageRows(secId) {
  return pagesOf(secId).map((p) => row('pg', p.id, 'pg' + (p.id === S.openPage ? ' open' : ''), pageLabel(p), null, () => openPage(p.id)));
}
function renderTree() {
  const L = $('treeList'); const keepScroll = L.scrollTop; L.textContent = '';
  const loose = pagesOf(null);
  L.append(h('div', { class: 'row loose' + (S.openSec === 'loose' ? ' openSec' : ''), 'data-kind': 'loose', onclick: () => openSection('loose') },
    h('span', { class: 'name' }, 'Loose'), h('span', { class: 'count' }, String(loose.length))));
  L.append(...pageRows(null));
  for (const n of notebooks()) {
    const box = h('div', { class: 'nbBox', 'data-id': n.id });
    box.append(row('nb', n.id, 'nb', n.name, nbCount(n.id), null));
    for (const s of sectionsOf(n.id)) {
      box.append(row('sec', s.id, 'sec' + (S.openSec === s.id ? ' openSec' : ''), s.name, pagesOf(s.id).length, () => openSection(s.id)));
      const pr = pageRows(s.id);
      box.append(...(pr.length ? pr : [h('div', { class: 'empty' }, 'No pages yet')]));
    }
    box.append(h('button', { class: 'add secAdd', type: 'button', onclick: () => addSection(n.id) }, '+ Section'));
    L.append(box);
  }
  L.append(h('button', { class: 'add nbAdd', type: 'button', id: 'addNotebook', onclick: addNotebook }, '+ Notebook'));
  const items = binItems();
  L.append(h('div', { class: 'row bin', 'data-kind': 'bin', onclick: () => { S.binOpen = !S.binOpen; render(); } },
    h('span', { class: 'name' }, 'Bin'), h('span', { class: 'count' }, String(items.length))));
  if (S.binOpen) {
    if (!items.length) L.append(h('div', { class: 'empty' }, 'The Bin is empty.'));
    for (const it of items) {
      const what = it.kind === 'nb' ? 'Notebook' : it.kind === 'sec' ? 'Section' : 'Page';
      const name = it.kind === 'pg' ? pageLabel(it.r) : it.r.name;
      L.append(h('div', { class: 'binItem', 'data-kind': it.kind, 'data-id': it.r.id },
        h('div', { class: 'what' }, h('b', {}, name), h('small', {}, what + ', goes for good on ' + shortDate(Date.parse(it.r.deleted_at) + 30 * DAY))),
        h('button', { type: 'button', onclick: () => restore(it.kind, it.r.id) }, 'Restore')));
    }
  }
  L.scrollTop = keepScroll;
}

// ---------------------------------------------------------------- the page area
const ICON_PORTRAIT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="6" y="3" width="12" height="18" rx="1.5"/></svg>';
const ICON_LANDSCAPE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="6" width="18" height="12" rx="1.5"/></svg>';
let shownKey = '';
function renderPage(refit) {
  const p = S.openPage ? pg(S.openPage) : null;
  const ok = p && livePage(p);
  const list = ok ? pagesOf(p.section_id || null) : [];
  const i = ok ? list.indexOf(p) : -1;
  $('prevBtn').disabled = !(i > 0);
  $('nextBtn').disabled = !(ok && i < list.length - 1);
  $('orientBtn').disabled = $('bgBtn').disabled = !ok;
  $('orientBtn').innerHTML = ok && p.orientation === 'landscape' ? ICON_LANDSCAPE : ICON_PORTRAIT;
  $('orientBtn').setAttribute('aria-label', ok && p.orientation === 'landscape' ? 'Landscape, tap for portrait' : 'Portrait, tap for landscape');
  const where = ok ? (p.section_id ? sec(p.section_id).name : 'Loose') : '';
  $('pageTitle').querySelector('b').textContent = ok ? pageLabel(p) : '';
  $('pageTitle').querySelector('small').textContent = ok ? `${where} · ${i + 1} of ${list.length}` : '';
  $('nothing').hidden = !!ok;
  $('nothing').textContent = S.openSec && S.openSec !== 'loose' && sec(S.openSec)
    ? 'This section has no pages yet. Tap + Page to start one.'
    : 'No page open. Tap a page in the list, or + Page to start one.';
  const key = ok ? [p.id, p.orientation, p.background].join('|') : '';
  if (key !== shownKey) {
    const [prevId, prevOr] = shownKey.split('|');
    showPage(ok ? p : null);
    if (ok && (prevId !== p.id || prevOr !== p.orientation)) fit();   // a new page or a turned page starts fitted
    shownKey = key;
  }
}

function render() { renderTree(); renderPage(); }

// ---------------------------------------------------------------- drawer (tablet portrait and phone)
function closeDrawer() { document.body.classList.remove('drawer'); $('scrim').hidden = true; }
function openDrawer() { document.body.classList.add('drawer'); $('scrim').hidden = false; }

// ---------------------------------------------------------------- start
async function load() {
  try { await api.purgeBin(30); } catch (_) { /* the bin empties itself next time */ }
  let d;
  try { d = await api.loadAll(); }
  catch (_) { toast('Could not load your notebooks. Check the connection, then reload.', 8000); return; }
  S.notebooks = d.notebooks; S.sections = d.sections; S.pages = d.pages;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(OPEN_KEY) || '{}') || {}; } catch (_) { /* ignore */ }
  if (saved.page && livePage(pg(saved.page))) { S.openPage = saved.page; S.openSec = pg(saved.page).section_id || 'loose'; }
  else if (saved.sec === 'loose' || liveSec(sec(saved.sec))) { S.openSec = saved.sec; const f = pagesOf(saved.sec === 'loose' ? null : saved.sec)[0]; S.openPage = f ? f.id : null; }
  render();
  fit();
  document.body.dataset.ready = '1';
}

async function enter(user) {
  S.user = user;
  $('login').hidden = true; $('app').hidden = false;
  if (api.mode === 'local') { $('modeNote').textContent = 'local copy'; $('logoutBtn').hidden = true; }
  await load();
}

function wire() {
  initPage({ desk: $('desk'), wrap: $('sheetWrap'), sheet: $('sheet') });
  $('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('loginBtn').disabled = true; $('loginMsg').textContent = '';
    const res = await api.signIn($('lu').value, $('lp').value);
    $('loginBtn').disabled = false;
    if (!res.ok) { $('loginMsg').textContent = res.message; return; }
    $('lp').value = '';
    enter(res.user || await api.session());
  });
  $('logoutBtn').addEventListener('click', async () => { await chain; await api.signOut(); location.reload(); });
  $('menuBtn').addEventListener('click', openDrawer);
  $('scrim').addEventListener('click', closeDrawer);
  $('newPageBtn').addEventListener('click', () => addPage(false));
  $('addBelow').addEventListener('click', () => addPage(true));
  const step = (d) => { const p = pg(S.openPage); if (!p) return; const l = pagesOf(p.section_id || null), j = l.indexOf(p) + d; if (l[j]) openPage(l[j].id); };
  $('prevBtn').addEventListener('click', () => step(-1));
  $('nextBtn').addEventListener('click', () => step(1));
  $('orientBtn').addEventListener('click', () => {
    const p = pg(S.openPage); if (!p) return;
    p.orientation = p.orientation === 'landscape' ? 'portrait' : 'landscape';
    patch('pages', [p.id], { orientation: p.orientation });
    renderPage();
  });
  $('bgBtn').addEventListener('click', (e) => {
    const p = pg(S.openPage); if (!p) return;
    const choose = (b) => { p.background = b; patch('pages', [p.id], { background: b }); renderPage(); };
    openMenu(e.currentTarget, [{ head: 'Paper' },
      { label: 'Blank', on: p.background === 'blank', fn: () => choose('blank') },
      { label: 'Grid, 1 cm squares', on: p.background === 'grid', fn: () => choose('grid') },
      { label: 'Lined, 8 mm', on: p.background === 'lined', fn: () => choose('lined') }]);
  });
  document.addEventListener('pointerdown', (e) => { if (!$('menu').hidden && !e.target.closest('#menu')) closeMenu(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeMenu(); closeDrawer(); } });
}

// test hook: the U1 checks wait for writes and clean up their rows through this
window.__pw = { S, api, idle: () => chain, failed: () => failed };

wire();
(async () => {
  let user = null;
  try { user = await api.session(); } catch (_) { /* treat as logged out */ }
  if (user) enter(user);
  else { $('login').hidden = false; $('lu').focus(); }
})();
