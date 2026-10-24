// PenWorks U1b + U2 A: Samsung Notes' flow. Folder view (folders two levels deep, note names showing under
// each folder, Loose, Bin), the grid of notes, the note view (every page stacked), page list, the one
// undo/redo stack per note (page operations and ink together), full screen, autosave, dark mode.
// Ink lives in js/ink.js (strokes), js/store-local.js (kept on the device) and js/tray.js (the pen tray).
import { api } from './api.js';
import { initPage, showStack, fit, scrollToPage, relayout, current } from './page.js';
import * as ink from './ink.js';
import { initTray, closePanel, trayState } from './tray.js';

const $ = (id) => document.getElementById(id);
const S = { folders: [], notes: [], pages: [], sel: 'loose', openNote: null, cur: 0, fold: {}, renaming: null,
            listOpen: false, hist: {}, clip: {}, user: null };
const PREF = 'penworks.' + api.mode + '.';
const DAY = 864e5;
// Samsung's small folder palette
const COLOURS = [['Grey', '#8A8F98'], ['Red', '#E0524A'], ['Orange', '#EE8A2F'], ['Yellow', '#E6B52C'],
                 ['Green', '#45A866'], ['Blue', '#3A86D6'], ['Purple', '#7B5ACD'], ['Pink', '#D45A9C']];
const isPhone = () => innerWidth < 600;

// ---------------------------------------------------------------- small helpers
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) el.append(c);
  return el;
}
const uuid = () => crypto.randomUUID();
const nowIso = () => new Date().toISOString();
const byPos = (a, b) => (a.position - b.position) || String(a.created_at).localeCompare(String(b.created_at));
const noteOrder = (a, b) => (Number(b.pinned) - Number(a.pinned)) || (Date.parse(b.updated_at) - Date.parse(a.updated_at));
const folder = (id) => S.folders.find((r) => r.id === id);
const note = (id) => S.notes.find((r) => r.id === id);
const page = (id) => S.pages.find((r) => r.id === id);
const liveFolder = (f) => !!f && !f.deleted_at && (!f.parent_id || liveFolder(folder(f.parent_id)));
const liveNote = (n) => !!n && !n.deleted_at && (!n.folder_id || liveFolder(folder(n.folder_id)));
const topFolders = () => S.folders.filter((f) => !f.parent_id && liveFolder(f)).sort(byPos);
const subFolders = (id) => S.folders.filter((f) => f.parent_id === id && liveFolder(f)).sort(byPos);
const notesIn = (fid) => S.notes.filter((n) => (n.folder_id || null) === (fid || null) && liveNote(n)).sort(noteOrder);
const folderCount = (id) => notesIn(id).length + subFolders(id).reduce((k, s) => k + notesIn(s.id).length, 0);
const pagesOf = (nid) => S.pages.filter((p) => p.note_id === nid && !p.deleted_at).sort(byPos);
const nextPos = (rows) => rows.reduce((m, r) => Math.max(m, r.position + 1), 0);
const same = (a, b) => a && b && Date.parse(a) === Date.parse(b);
const shortDate = (t) => new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
function edited(iso) {
  const d = new Date(iso);
  if (d.toDateString() === new Date().toDateString()) return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return shortDate(d);
}
const folderPath = (f) => (f.parent_id ? folder(f.parent_id).name + ' / ' : '') + f.name;
const keyOf = (fid) => fid || 'loose';
const selKey = () => (S.sel === 'loose' || S.sel === 'bin' ? null : S.sel);

// icons (a folder, a sheet, a bin, a chevron, a pin; nothing bookmark-shaped)
const svgFolder = (c) => `<svg viewBox="0 0 24 24"><path d="M3 6.6A1.6 1.6 0 0 1 4.6 5h4.5l2 2.1h8.3A1.6 1.6 0 0 1 21 8.7v8.7a1.6 1.6 0 0 1-1.6 1.6H4.6A1.6 1.6 0 0 1 3 17.4z" fill="${c}"/></svg>`;
const SVG_SHEET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg>';
const SVG_BIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/></svg>';
const SVG_CHEV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>';
const SVG_PIN = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M14.5 2.5l7 7-2.2.7-3.6 3.6.6 4.6-1.6 1.6-4.3-4.3L5 21l-1-1 5.3-5.4L5 10.3l1.6-1.6 4.6.6 3.6-3.6z"/></svg>';
const SVG_PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>';

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

function remember() {
  try { localStorage.setItem(PREF + 'open', JSON.stringify({ sel: S.sel, note: S.openNote })); } catch (_) { /* ignore */ }
}
function rememberFold() {
  try { localStorage.setItem(PREF + 'fold', JSON.stringify(S.fold)); } catch (_) { /* ignore */ }
}

// ---------------------------------------------------------------- folders
function select(key) {
  S.sel = key; S.renaming = null; remember();
  if (isPhone()) document.body.classList.add('showGrid');
  render();
}
function toggleFold(key) { S.fold[key] = !S.fold[key]; rememberFold(); renderSide(); }

function createFolder(parentId = null) {
  if (parentId && folder(parentId).parent_id) { toast('Folders go two levels deep, no further.'); return; }
  const r = { id: uuid(), parent_id: parentId, name: 'New folder', colour: null,
              position: nextPos(S.folders.filter((f) => (f.parent_id || null) === parentId)),
              deleted_at: null, created_at: nowIso(), updated_at: nowIso() };
  S.folders.push(r);
  save(() => api.createFolder(r));
  if (parentId) { S.fold[parentId] = false; rememberFold(); }
  S.renaming = { kind: 'folder', id: r.id }; render();
}
function renameFolder(id, value) {
  const f = folder(id), v = value.trim().slice(0, 120);
  if (!v || v === f.name) return;
  f.name = v; save(() => api.renameFolder(id, v));
}
function recolour(id, c) { const f = folder(id); f.colour = c; save(() => api.recolourFolder(id, c)); render(); }
// where a folder may go: never under a sub-folder, never deeper than two levels
function folderTargets(f) {
  if (S.folders.some((c) => c.parent_id === f.id)) return [];           // it holds folders: it stays on top
  const out = [];
  if (f.parent_id) out.push({ label: 'Top level', id: null });
  for (const t of topFolders()) if (t.id !== f.id && t.id !== f.parent_id) out.push({ label: t.name, id: t.id });
  return out;
}
function moveFolder(id, parentId) {
  const f = folder(id);
  if (parentId && (folder(parentId).parent_id || S.folders.some((c) => c.parent_id === id))) { toast('Folders go two levels deep, no further.'); return; }
  f.parent_id = parentId;
  f.position = nextPos(S.folders.filter((x) => (x.parent_id || null) === parentId && x.id !== id));
  save(() => api.moveFolder(id, parentId, f.position));
  if (parentId) { S.fold[parentId] = false; rememberFold(); }
  render();
}
function stepFolder(id, dir) {
  const f = folder(id), list = f.parent_id ? subFolders(f.parent_id) : topFolders(), i = list.indexOf(f), j = i + dir;
  if (j < 0 || j >= list.length) return;
  [list[i], list[j]] = [list[j], list[i]];
  const pairs = [];
  list.forEach((x, k) => { if (x.position !== k) { x.position = k; pairs.push([x.id, k]); } });
  if (pairs.length) save(() => api.reorderFolders(pairs));
  render();
}

// ---------------------------------------------------------------- notes
function createNote(fid) {
  const t = nowIso();
  const n = { id: uuid(), folder_id: fid || null, name: 'Untitled', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t };
  const p = { id: uuid(), note_id: n.id, position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t };
  S.notes.push(n); S.pages.push(p);
  save(() => api.createNote(n));
  save(() => api.createPage(p));
  openNote(n.id);
}
function renameNote(id, value) {
  const n = note(id), v = value.trim().slice(0, 120);
  if (!v || v === n.name) return;
  n.name = v; n.updated_at = nowIso();                 // a rename counts as an edit (the database agrees)
  save(() => api.renameNote(id, v));
}
function moveNote(id, fid) {
  const n = note(id); n.folder_id = fid;               // moving does not count as an edit
  save(() => api.moveNote(id, fid));
  render();
}
function pinNote(id, on) {
  const n = note(id); n.pinned = on;                    // pinning does not count as an edit
  save(() => api.pinNote(id, on));
  render();
}
function noteTargets(n) {
  const out = [];
  if (n.folder_id) out.push({ label: 'Loose', id: null });
  for (const t of topFolders()) {
    if (t.id !== n.folder_id) out.push({ label: t.name, id: t.id });
    for (const s of subFolders(t.id)) if (s.id !== n.folder_id) out.push({ label: t.name + ' / ' + s.name, id: s.id });
  }
  return out;
}

// ---------------------------------------------------------------- bin and restore (one timestamp per binning)
function binIds(kind, id, test) {
  const ids = { folders: [], notes: [], pages: [] };
  const addNote = (n) => { ids.notes.push(n.id); S.pages.filter((p) => p.note_id === n.id && test(p)).forEach((p) => ids.pages.push(p.id)); };
  if (kind === 'note') addNote(note(id));
  else {
    const fs = [folder(id), ...S.folders.filter((c) => c.parent_id === id && test(c))];
    fs.forEach((f) => { ids.folders.push(f.id); S.notes.filter((n) => n.folder_id === f.id && test(n)).forEach(addNote); });
  }
  return ids;
}
function setDeleted(ids, value) {
  const all = new Set([...ids.folders, ...ids.notes, ...ids.pages]);
  for (const t of ['folders', 'notes', 'pages']) S[t].forEach((r) => { if (all.has(r.id)) r.deleted_at = value; });
}
function binThing(kind, id) {
  const T = nowIso(), ids = binIds(kind, id, (r) => !r.deleted_at);
  setDeleted(ids, T);
  save(() => api.bin(ids, T));
  if (S.openNote && !liveNote(note(S.openNote))) closeNote(true);
  if (S.sel !== 'loose' && S.sel !== 'bin' && !liveFolder(folder(S.sel))) { S.sel = 'loose'; remember(); }
  toast('Moved to the Bin. It stays there for 30 days.');
  render();
}
function restoreThing(kind, id) {
  const r = kind === 'note' ? note(id) : folder(id), T = r.deleted_at;
  const ids = binIds(kind, id, (x) => same(x.deleted_at, T));
  setDeleted(ids, null);
  save(() => api.restore(ids));
  toast('Restored.');
  render();
}
function binItems() {
  const out = [];
  S.folders.filter((f) => f.deleted_at && (!f.parent_id || liveFolder(folder(f.parent_id)))).forEach((r) => out.push({ kind: 'folder', r }));
  S.notes.filter((n) => n.deleted_at && (!n.folder_id || liveFolder(folder(n.folder_id)))).forEach((r) => out.push({ kind: 'note', r }));
  return out.sort((a, b) => Date.parse(b.r.deleted_at) - Date.parse(a.r.deleted_at));
}

// ---------------------------------------------------------------- the open note
function openNote(id, index = 0) {
  if (!liveNote(note(id))) return;
  S.openNote = id; S.cur = index; S.listOpen = false; S.renaming = null; remember();
  document.body.classList.add('noteMode');
  if (!(history.state && history.state.note)) history.pushState({ note: id }, '');
  stackKey = ''; render(); fit(index);
}
function closeNote(skipHistory) {
  if (document.body.classList.contains('full')) exitFull();
  closePanel();
  if (S.openNote) { delete S.hist[S.openNote]; tidyInk(); }    // closing a note ends its undo history
  S.openNote = null; S.listOpen = false; S.renaming = null; remember();
  document.body.classList.remove('noteMode');
  if (!skipHistory && history.state && history.state.note) history.replaceState(null, '');
  render();
}

// page and ink operations: each one can be undone (one stack per note, 100 deep, in the order she did them).
// An op that names `pages` holds those pages' strokes: a page deleted for good keeps its strokes on the
// device until no op can bring it back (the op drops off the stack, or the note closes).
const DEPTH = 100;
const orphans = new Set();
const hist = () => (S.hist[S.openNote] ||= { u: [], r: [] });
function doOp(op) {
  op.redo();
  const H = hist(); H.u.push(op);
  const dropped = H.r.length + Math.max(0, H.u.length - DEPTH);
  if (H.u.length > DEPTH) H.u.splice(0, H.u.length - DEPTH);
  H.r = [];
  if (dropped) tidyInk();
  renderTray();
}
function tidyInk() {
  if (!orphans.size) return;
  const held = new Set();
  for (const H of Object.values(S.hist)) for (const op of [...H.u, ...H.r]) (op.pages || []).forEach((id) => held.add(id));
  for (const id of [...orphans]) if (!held.has(id) && !page(id)) { ink.forget(id); orphans.delete(id); }
}
function undo() { if (!S.openNote) return; const H = hist(), op = H.u.pop(); if (!op) return; op.undo(); H.r.push(op); renderTray(); }
function redo() { if (!S.openNote) return; const H = hist(), op = H.r.pop(); if (!op) return; op.redo(); H.u.push(op); renderTray(); }

function touchNote(nid) { const n = note(nid); if (n) n.updated_at = nowIso(); }
function renumber(list) {
  const pairs = [];
  list.forEach((p, k) => { if (p.position !== k) { p.position = k; pairs.push([p.id, k]); } });
  if (pairs.length) save(() => api.reorderPages(pairs));
}
function insertPage(snap, i) {
  const list = pagesOf(snap.note_id);
  const p = { ...snap, position: i, deleted_at: null };
  list.splice(i, 0, p);
  const pairs = [];                                         // the pages below it move down one
  list.forEach((x, k) => { if (x !== p && x.position !== k) { x.position = k; pairs.push([x.id, k]); } });
  if (pairs.length) save(() => api.reorderPages(pairs));
  S.pages.push(p);
  save(() => api.createPage(p));
  touchNote(p.note_id);
}
function removePage(id) {
  const p = page(id), list = pagesOf(p.note_id).filter((x) => x !== p);
  S.pages = S.pages.filter((x) => x !== p);
  orphans.add(id);
  save(() => api.deletePage(id));
  renumber(list);
  touchNote(p.note_id);
}
function movePage(id, j) {
  const p = page(id), list = pagesOf(p.note_id), i = list.indexOf(p);
  list.splice(i, 1); list.splice(j, 0, p);
  renumber(list);
  touchNote(p.note_id);
}
function shown(index) { render(); scrollToPage(index); }

function addPageBelow(i) {
  const nid = S.openNote, list = pagesOf(nid), model = list[i] || list[list.length - 1];
  const at = Math.min(list.length, i + 1);
  const snap = { id: uuid(), note_id: nid, orientation: model ? model.orientation : 'portrait',
                 background: model ? model.background : 'grid', created_at: nowIso() };
  doOp({ pages: [snap.id], redo: () => { insertPage(snap, at); shown(at); }, undo: () => { removePage(snap.id); shown(Math.max(0, at - 1)); } });
}
function deletePage(i) {
  const list = pagesOf(S.openNote);
  if (list.length <= 1) return;                       // a note keeps at least one page
  const snap = { ...list[i] };
  doOp({ pages: [snap.id], redo: () => { removePage(snap.id); shown(Math.min(i, list.length - 2)); },
         undo: () => { insertPage(snap, i); shown(i); } });
}
// Samsung's page menu: Copy keeps the page (orientation, paper, strokes) on a clipboard for this note,
// Cut = Copy then Delete, Paste puts it below the pressed page, Erase page clears its strokes
function copyPage(i, quiet) {
  const p = pagesOf(S.openNote)[i];
  if (!p) return;
  S.clip[S.openNote] = { orientation: p.orientation, background: p.background, strokes: ink.copyStrokes(p.id) };
  if (!quiet) toast('Page copied.');
}
function cutPage(i) {
  if (pagesOf(S.openNote).length <= 1) return;
  copyPage(i, true); deletePage(i); toast('Page cut.');
}
function pastePage(i) {
  const nid = S.openNote, c = S.clip[nid];
  if (!c) return;
  const at = i + 1;
  const snap = { id: uuid(), note_id: nid, orientation: c.orientation, background: c.background, created_at: nowIso() };
  const recs = c.strokes.map((r) => ({ ...JSON.parse(JSON.stringify(r)), id: uuid(), page_id: snap.id }));
  doOp({ pages: [snap.id], redo: () => { insertPage(snap, at); ink.put(snap.id, recs); shown(at); },
         undo: () => { removePage(snap.id); shown(i); } });
}
function erasePage(i) {
  const p = pagesOf(S.openNote)[i], op = p && ink.erasePageOp(p.id);
  if (!op) { toast('Nothing to erase on this page.'); return; }
  doOp(op);
}
function stepPage(i, dir) {
  const list = pagesOf(S.openNote), j = i + dir;
  if (j < 0 || j >= list.length) return;
  const id = list[i].id;
  doOp({ redo: () => { movePage(id, j); shown(j); }, undo: () => { movePage(id, i); shown(i); } });
}
// orientation or paper, for the current page or all of them
function setPaper(field, value, all) {
  const list = pagesOf(S.openNote), targets = all ? list : [list[S.cur]].filter(Boolean);
  const changes = targets.filter((p) => p[field] !== value).map((p) => ({ id: p.id, old: p[field] }));
  if (!changes.length) return;
  const at = S.cur;
  const put = (pairs) => {
    const groups = new Map();
    pairs.forEach(([id, v]) => { const p = page(id); if (!p) return; p[field] = v; groups.set(v, [...(groups.get(v) || []), id]); });
    groups.forEach((ids, v) => save(() => api.setPages(ids, { [field]: v })));
    touchNote(S.openNote);
    shown(at);
  };
  doOp({ redo: () => put(changes.map((c) => [c.id, value])), undo: () => put(changes.map((c) => [c.id, c.old])) });
}

// ---------------------------------------------------------------- full screen (the real Fullscreen API, so the Android bar goes)
async function enterFull() {
  document.body.classList.add('full'); $('exitFs').hidden = false;
  relayout();
  try {
    const el = document.documentElement;
    if (el.requestFullscreen) await el.requestFullscreen({ navigationUI: 'hide' });
  } catch (_) { /* refused (older browser, not installed): our own elements stay hidden anyway */ }
  relayout();
}
function exitFull() {
  document.body.classList.remove('full'); $('exitFs').hidden = true;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  relayout();
}

// ---------------------------------------------------------------- menu (long-press, right-click or the dots)
function closeMenu() { $('menu').hidden = true; $('menu').textContent = ''; }
function placeMenu(anchor) {
  const m = $('menu'); m.hidden = false;
  const a = anchor.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(innerWidth - mw - 8, a.right - mw)) + 'px';
  m.style.top = (a.bottom + mh + 8 < innerHeight ? a.bottom + 4 : Math.max(8, a.top - mh - 4)) + 'px';
}
function openMenu(anchor, items) {
  const m = $('menu'); m.textContent = '';
  for (const it of items) {
    if (it.head) m.append(h('div', { class: 'hd' }, it.head));
    else m.append(h('button', { type: 'button', class: it.on ? 'on' : '', role: 'menuitem',
      onclick: (e) => { e.stopPropagation(); if (!it.keep) closeMenu(); it.fn(); } }, it.label));
  }
  placeMenu(anchor);
}
function colourMenu(id, anchor) {
  const f = folder(id), m = $('menu'); m.textContent = '';
  m.append(h('div', { class: 'hd' }, 'Colour'));
  const row = h('div', { class: 'swatches' });
  for (const [name, c] of COLOURS) {
    row.append(h('button', { type: 'button', class: 'sw' + (f.colour === c ? ' on' : ''), 'aria-label': name, title: name,
      style: `background:${c}`, onclick: (e) => { e.stopPropagation(); closeMenu(); recolour(id, c); } }));
  }
  m.append(row);
  m.append(h('button', { type: 'button', role: 'menuitem', onclick: (e) => { e.stopPropagation(); closeMenu(); recolour(id, null); } }, 'No colour'));
  placeMenu(anchor);
}
function folderMenu(id, anchor) {
  const f = folder(id), list = f.parent_id ? subFolders(f.parent_id) : topFolders(), i = list.indexOf(f);
  const items = [{ label: 'Rename', fn: () => { S.renaming = { kind: 'folder', id }; render(); } },
                 { label: 'Colour', keep: true, fn: () => colourMenu(id, anchor) }];
  if (!f.parent_id) items.push({ label: 'New folder inside', fn: () => createFolder(id) });
  items.push({ label: 'New note', fn: () => createNote(id) });
  if (folderTargets(f).length) items.push({ label: 'Move to...', keep: true, fn: () => targetMenu(anchor, folderTargets(f), (t) => moveFolder(id, t)) });
  if (i > 0) items.push({ label: 'Move up', fn: () => stepFolder(id, -1) });
  if (i < list.length - 1) items.push({ label: 'Move down', fn: () => stepFolder(id, 1) });
  items.push({ label: 'Put in the Bin', fn: () => binThing('folder', id) });
  openMenu(anchor, items);
}
function noteMenu(id, anchor, where) {
  const n = note(id);
  openMenu(anchor, [
    { label: 'Rename', fn: () => { S.renaming = { kind: 'note', id, where }; render(); } },
    { label: 'Move to...', keep: true, fn: () => targetMenu(anchor, noteTargets(n), (t) => moveNote(id, t)) },
    n.pinned ? { label: 'Unpin', fn: () => pinNote(id, false) } : { label: 'Pin to top', fn: () => pinNote(id, true) },
    { label: 'Put in the Bin', fn: () => binThing('note', id) }]);
}
function targetMenu(anchor, targets, go) {
  const items = [{ head: 'Move to' }, ...targets.map((t) => ({ label: t.label, fn: () => go(t.id) }))];
  if (!targets.length) items.push({ head: 'There is nowhere else to move it yet.' });
  openMenu(anchor, items);
}
function thumbMenu(i, anchor) {
  const n = pagesOf(S.openNote).length;
  const items = [{ label: 'Add page', fn: () => addPageBelow(i) }, { label: 'Copy', fn: () => copyPage(i) }];
  if (n > 1) items.push({ label: 'Cut', fn: () => cutPage(i) });
  if (S.clip[S.openNote]) items.push({ label: 'Paste', fn: () => pastePage(i) });
  if (n > 1) items.push({ label: 'Delete', fn: () => deletePage(i) });
  items.push({ label: 'Erase page', fn: () => erasePage(i) });
  if (i > 0) items.push({ label: 'Move up', fn: () => stepPage(i, -1) });
  if (i < n - 1) items.push({ label: 'Move down', fn: () => stepPage(i, 1) });
  openMenu(anchor, items);
}
function paperMenu(anchor) {
  const p = pagesOf(S.openNote)[S.cur] || {};
  const ask = (field, value) => openMenu(anchor, [{ head: 'Change' },
    { label: 'Just this page', fn: () => setPaper(field, value, false) },
    { label: 'All pages', fn: () => setPaper(field, value, true) }]);
  openMenu(anchor, [{ head: 'Page' },
    { label: 'Portrait', on: p.orientation === 'portrait', keep: true, fn: () => ask('orientation', 'portrait') },
    { label: 'Landscape', on: p.orientation === 'landscape', keep: true, fn: () => ask('orientation', 'landscape') },
    { head: 'Paper' },
    { label: 'Blank', on: p.background === 'blank', keep: true, fn: () => ask('background', 'blank') },
    { label: 'Grid, 1 cm squares', on: p.background === 'grid', keep: true, fn: () => ask('background', 'grid') },
    { label: 'Lined, 8 mm', on: p.background === 'lined', keep: true, fn: () => ask('background', 'lined') },
    { head: 'Note' },
    { label: 'Bin this note', fn: () => binThing('note', S.openNote) }]);
}

// long-press on touch, right-click on a laptop
function pressable(el, open) {
  let t = null, fired = false, s0 = null;
  el.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button:not(.card), input') || e.button > 0) return;
    fired = false; s0 = [e.clientX, e.clientY];
    t = setTimeout(() => { fired = true; open(); }, 550);
  });
  el.addEventListener('pointermove', (e) => { if (t && s0 && Math.hypot(e.clientX - s0[0], e.clientY - s0[1]) > 8) clearTimeout(t); });
  for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) el.addEventListener(ev, () => clearTimeout(t));
  el.addEventListener('click', (e) => { if (fired) { e.stopPropagation(); e.preventDefault(); fired = false; } }, true);
  el.addEventListener('contextmenu', (e) => { e.preventDefault(); clearTimeout(t); open(); });
}

// a name, or the box to rename it in
function nameOrInput(kind, id, text, where) {
  const R = S.renaming;
  if (!R || R.kind !== kind || R.id !== id || (R.where || 'side') !== where) return h('span', { class: 'name' }, text);
  const inp = h('input', { class: 'rename', value: text, 'aria-label': 'Name' });
  let done = false;
  const finish = (keep) => {
    if (done) return; done = true;
    if (keep) (kind === 'note' ? renameNote : renameFolder)(id, inp.value);
    S.renaming = null; render();
  };
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false); });
  inp.addEventListener('blur', () => finish(true));
  inp.addEventListener('click', (e) => e.stopPropagation());
  inp.addEventListener('pointerdown', (e) => e.stopPropagation());
  setTimeout(() => { inp.focus(); inp.select(); }, 0);
  return inp;
}

// ---------------------------------------------------------------- the folder view
function chev(key) {
  return h('button', { class: 'chev' + (S.fold[key] ? '' : ' open'), type: 'button', 'aria-label': S.fold[key] ? 'Unfold' : 'Fold',
    'aria-expanded': S.fold[key] ? 'false' : 'true', html: SVG_CHEV, onclick: (e) => { e.stopPropagation(); toggleFold(key); } });
}
function noteRow(n, depth) {
  const el = h('div', { class: 'nrow d' + depth + (n.id === S.openNote ? ' sel' : ''), 'data-id': n.id, onclick: () => openNote(n.id) },
    h('span', { class: 'ico', html: SVG_SHEET }),
    nameOrInput('note', n.id, n.name, 'side'),
    n.pinned ? h('span', { class: 'pinMark', html: SVG_PIN, title: 'Pinned' }) : null,
    h('span', { class: 'pc', title: 'Pages' }, String(pagesOf(n.id).length)),
    h('button', { class: 'more', type: 'button', 'aria-label': 'More', onclick: (e) => { e.stopPropagation(); noteMenu(n.id, e.currentTarget, 'side'); } }, '⋯'));
  pressable(el, () => noteMenu(n.id, el.querySelector('.more'), 'side'));
  return el;
}
function folderBlock(f, depth) {
  const box = h('div', { class: 'fbox', 'data-id': f.id });
  const el = h('div', { class: 'frow d' + depth + (S.sel === f.id ? ' sel' : ''), 'data-id': f.id, 'data-depth': depth, onclick: () => select(f.id) },
    chev(f.id),
    h('span', { class: 'ico', html: svgFolder(f.colour || '#9AA0A8') }),
    nameOrInput('folder', f.id, f.name, 'side'),
    h('span', { class: 'count' }, String(folderCount(f.id))),
    h('button', { class: 'more', type: 'button', 'aria-label': 'More', onclick: (e) => { e.stopPropagation(); folderMenu(f.id, e.currentTarget); } }, '⋯'));
  pressable(el, () => folderMenu(f.id, el.querySelector('.more')));
  box.append(el);
  if (!S.fold[f.id]) {
    const kids = h('div', { class: 'kids' });
    if (depth === 0) for (const s of subFolders(f.id)) kids.append(folderBlock(s, 1));
    for (const n of notesIn(f.id)) kids.append(noteRow(n, depth + 1));
    box.append(kids);
  }
  return box;
}
function renderSide() {
  const L = $('folderList'), keep = L.scrollTop; L.textContent = '';
  const loose = notesIn(null);
  const lbox = h('div', { class: 'fbox loose' });
  lbox.append(h('div', { class: 'frow d0 loose' + (S.sel === 'loose' ? ' sel' : ''), 'data-id': 'loose', onclick: () => select('loose') },
    chev('loose'), h('span', { class: 'ico plain', html: SVG_SHEET }), h('span', { class: 'name' }, 'Loose'),
    h('span', { class: 'count' }, String(loose.length))));
  if (!S.fold.loose) lbox.append(h('div', { class: 'kids' }, loose.map((n) => noteRow(n, 1))));
  L.append(lbox);
  for (const f of topFolders()) L.append(folderBlock(f, 0));
  L.append(h('button', { class: 'addFolder', type: 'button', id: 'addFolder', onclick: () => createFolder(null) }, '+ Folder'));
  L.append(h('div', { class: 'frow d0 bin' + (S.sel === 'bin' ? ' sel' : ''), 'data-id': 'bin', onclick: () => select('bin') },
    h('span', { class: 'chevGap' }), h('span', { class: 'ico plain', html: SVG_BIN }), h('span', { class: 'name' }, 'Bin'),
    h('span', { class: 'count' }, String(binItems().length))));
  L.scrollTop = keep;
}

// ---------------------------------------------------------------- the grid (or the Bin)
function paper(p, extra = '') {
  return h('div', { class: 'paper ' + (p ? p.background : 'grid') + extra });
}
function renderGrid() {
  const G = $('grid'); G.textContent = '';
  if (S.sel === 'bin') {
    $('gridTitle').textContent = 'Bin';
    G.className = 'binList';
    const items = binItems();
    if (!items.length) G.append(h('p', { class: 'empty' }, 'The Bin is empty.'));
    for (const it of items) {
      const what = it.kind === 'folder' ? 'Folder' : 'Note';
      G.append(h('div', { class: 'binItem', 'data-kind': it.kind, 'data-id': it.r.id },
        h('div', { class: 'what' }, h('b', {}, it.r.name), h('small', {}, what + ', goes for good on ' + shortDate(Date.parse(it.r.deleted_at) + 30 * DAY))),
        h('button', { type: 'button', onclick: () => restoreThing(it.kind, it.r.id) }, 'Restore')));
    }
    return;
  }
  const fid = selKey(), f = fid ? folder(fid) : null;
  $('gridTitle').textContent = f ? folderPath(f) : 'Loose';
  G.className = 'grid';
  G.append(h('button', { class: 'card plus', type: 'button', id: 'newNote', 'aria-label': 'New note', onclick: () => createNote(fid) },
    h('div', { class: 'thumb', html: SVG_PLUS }), h('span', { class: 'cname' }, 'New note')));
  for (const n of notesIn(fid)) {
    const first = pagesOf(n.id)[0];
    const card = h('div', { class: 'card' + (n.pinned ? ' pinned' : ''), 'data-id': n.id, onclick: () => openNote(n.id) },
      h('div', { class: 'thumb' }, paper(first), n.pinned ? h('span', { class: 'pin', html: SVG_PIN, title: 'Pinned' }) : null),
      h('div', { class: 'meta' },
        nameOrInput('note', n.id, n.name, 'card'),
        h('small', { class: 'when' }, edited(n.updated_at))));
    pressable(card, () => noteMenu(n.id, card.querySelector('.thumb'), 'card'));
    G.append(card);
  }
}

// ---------------------------------------------------------------- the note view
let stackKey = '';
function updateCount() {
  const list = S.openNote ? pagesOf(S.openNote) : [], n = list.length, c = Math.min(S.cur, n - 1);
  const txt = n ? `${c + 1} / ${n}` : '';
  $('counter').textContent = txt; $('barCount').textContent = txt; $('plCount').textContent = txt;
  $('prevBtn').disabled = c <= 0; $('nextBtn').disabled = c >= n - 1;
  document.querySelectorAll('#plThumbs .thumbP').forEach((t, i) => t.classList.toggle('cur', i === c));
}
function renderPageList() {
  const P = $('pageList');
  P.hidden = !S.listOpen;
  if (!S.listOpen) return;
  const T = $('plThumbs'); T.textContent = '';
  pagesOf(S.openNote).forEach((p, i) => {
    const t = h('div', { class: 'thumbP ' + p.orientation, 'data-index': i + 1, role: 'button', tabindex: '0',
      onclick: () => { S.listOpen = false; renderPageList(); scrollToPage(i); } },
      paper(p, ' ' + p.orientation), h('span', { class: 'num' }, String(i + 1)));
    pressable(t, () => thumbMenu(i, t));
    T.append(t);
  });
  updateCount();
}
function renderNote() {
  const n = note(S.openNote);
  if (!liveNote(n)) { closeNote(true); return; }
  const N = $('noteName'); N.textContent = '';
  const R = S.renaming;
  if (R && R.kind === 'note' && R.id === n.id && R.where === 'head') N.append(nameOrInput('note', n.id, n.name, 'head'));
  else N.append(h('button', { class: 'nn', type: 'button', title: 'Rename',
    onclick: () => { S.renaming = { kind: 'note', id: n.id, where: 'head' }; renderNote(); } }, n.name));
  const list = pagesOf(n.id);
  const key = n.id + '#' + list.map((p) => p.id + p.orientation[0] + p.background[0]).join(',');
  if (key !== stackKey) { stackKey = key; showStack(list); }
  S.cur = Math.max(0, Math.min(current(), list.length - 1));
  renderPageList();
  updateCount();
}
function renderTray() {
  const H = S.openNote ? hist() : { u: [], r: [] };
  $('undoBtn').disabled = !H.u.length; $('redoBtn').disabled = !H.r.length;
}

function render() {
  const inNote = !!S.openNote;
  $('noteView').hidden = !inNote; $('listView').hidden = inNote;
  document.body.classList.toggle('noteMode', inNote);
  renderSide();
  if (inNote) renderNote(); else renderGrid();
  renderTray();
}

// ---------------------------------------------------------------- dark mode: follows the system, the footer toggle overrides it
// (the paper stays white and the ink keeps its colours either way)
const THEME = 'penworks.theme';
const SVG_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19.5 14.6A8 8 0 0 1 9.4 4.5a8 8 0 1 0 10.1 10.1z"/></svg>';
const SVG_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>';
const darkQuery = matchMedia('(prefers-color-scheme: dark)');
function chosenTheme() { try { const t = localStorage.getItem(THEME); return t === 'dark' || t === 'light' ? t : null; } catch (_) { return null; } }
const isDark = () => (chosenTheme() || (darkQuery.matches ? 'dark' : 'light')) === 'dark';
function applyTheme() {
  const t = chosenTheme(), root = document.documentElement;
  if (t) root.dataset.theme = t; else delete root.dataset.theme;
  const dark = isDark(), b = $('themeBtn');
  b.innerHTML = dark ? SVG_SUN : SVG_MOON;
  b.setAttribute('aria-label', dark ? 'Light mode' : 'Dark mode'); b.title = dark ? 'Light mode' : 'Dark mode';
  document.querySelector('meta[name="theme-color"]').setAttribute('content', dark ? '#1C1F23' : '#262A30');
}
function toggleTheme() {
  try { localStorage.setItem(THEME, isDark() ? 'light' : 'dark'); } catch (_) { /* ignore */ }
  applyTheme();
}

// ---------------------------------------------------------------- start
async function load() {
  try { await api.purgeBin(30); } catch (_) { /* the bin empties itself next time */ }
  let d;
  try { d = await api.loadAll(); }
  catch (_) { toast('Could not load your notes. Check the connection, then reload.', 8000); return; }
  S.folders = d.folders; S.notes = d.notes; S.pages = d.pages;
  try { S.fold = JSON.parse(localStorage.getItem(PREF + 'fold') || '{}') || {}; } catch (_) { S.fold = {}; }
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(PREF + 'open') || '{}') || {}; } catch (_) { /* ignore */ }
  if (saved.sel === 'loose' || saved.sel === 'bin' || liveFolder(folder(saved.sel))) S.sel = saved.sel;
  render();
  if (saved.note && liveNote(note(saved.note))) openNote(saved.note);
  document.body.dataset.ready = '1';
}

async function enter(user) {
  S.user = user;
  $('login').hidden = true; $('app').hidden = false;
  if (api.mode === 'local') { $('modeNote').textContent = 'local copy'; $('logoutBtn').hidden = true; }
  await load();
}

function wire() {
  applyTheme();
  darkQuery.addEventListener('change', applyTheme);
  $('themeBtn').addEventListener('click', toggleTheme);
  $('eyeBtn').addEventListener('click', () => {
    const show = $('lp').type === 'password';
    $('lp').type = show ? 'text' : 'password';
    $('eyeBtn').setAttribute('aria-pressed', show ? 'true' : 'false');
    $('eyeBtn').setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    $('eyeBtn').classList.toggle('on', show);
  });
  ink.initInk({ doOp, desk: $('desk') });
  initTray();
  initPage({ desk: $('desk'), stack: $('stack'), addBelow: $('addBelow'),
             onCurrent: (i) => { S.cur = Math.max(0, i); updateCount(); },
             onSheets: ink.attach, ink: ink.hook });
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
  $('gridBack').addEventListener('click', () => { document.body.classList.remove('showGrid'); });
  $('backBtn').addEventListener('click', () => { if (history.state && history.state.note) history.back(); else closeNote(); });
  window.addEventListener('popstate', () => { if (S.openNote) closeNote(true); });
  $('addPageBtn').addEventListener('click', () => addPageBelow(S.cur));
  $('addBelow').addEventListener('click', () => addPageBelow(pagesOf(S.openNote).length - 1));
  $('listBtn').addEventListener('click', () => { S.listOpen = !S.listOpen; renderPageList(); });
  $('plClose').addEventListener('click', () => { S.listOpen = false; renderPageList(); });
  $('desk').addEventListener('pointerdown', () => { if (S.listOpen) { S.listOpen = false; renderPageList(); } });
  $('prevBtn').addEventListener('click', () => scrollToPage(S.cur - 1));
  $('nextBtn').addEventListener('click', () => scrollToPage(S.cur + 1));
  $('fsBtn').addEventListener('click', enterFull);
  $('exitFs').addEventListener('click', exitFull);
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && document.body.classList.contains('full')) exitFull();
    else relayout();
  });
  $('noteMore').addEventListener('click', (e) => paperMenu(e.currentTarget));
  $('undoBtn').addEventListener('click', undo);
  $('redoBtn').addEventListener('click', redo);
  document.addEventListener('pointerdown', (e) => { if (!$('menu').hidden && !e.target.closest('#menu')) closeMenu(); });
  document.addEventListener('keydown', (e) => {
    if (e.target.closest && e.target.closest('input')) return;
    if (e.key === 'Escape') {
      if (!$('menu').hidden) closeMenu();
      else if (S.listOpen) { S.listOpen = false; renderPageList(); }
      else if (document.body.classList.contains('full') && !document.fullscreenElement) exitFull();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
  });
  let wasPhone = isPhone();
  window.addEventListener('resize', () => { if (isPhone() !== wasPhone) { wasPhone = isPhone(); render(); } });
}

// test hook: the checks wait for writes and clean up their rows through this
window.__pw = { S, api, idle: () => chain, failed: () => failed, current, ink, tray: trayState };

wire();
(async () => {
  let user = null;
  try { user = await api.session(); } catch (_) { /* treat as logged out */ }
  if (user) enter(user);
  else { $('login').hidden = false; $('lu').focus(); }
})();
