// PenWorks U1b + U2 A: Samsung Notes' flow. Folder view (folders two levels deep, note names showing under
// each folder, Loose, Bin), the grid of notes, the note view (every page stacked), page list, the one
// undo/redo stack per note (page operations and ink together), full screen, autosave, dark mode.
// Ink lives in js/ink.js (strokes), js/store.js (the device cache and the queue to the database) and js/tray.js (the pen tray).
// pw-v4q: the page list's Select (tick mode): tick several pages, then Delete, Copy, Cut or Move them together.
// pw-v4r: page bookmarks (the page menu's Bookmark, a ribbon tab on the page and its thumb, a Bookmarks filter in the list).
// pw-v4t: tick mode's Share: name the file first, then share the ticked pages as one PDF or as PNG images.
// U3b: page pictures to storage a few seconds after she stops writing (js/snap.js); a note's card shows its first page.
// U3c: a page's bookmark is the pages.bookmark column (migration 0004); the tray state follows her across devices
// through profiles.settings (newer wins, by its tray_at stamp).
import { api } from './api.js';
import { initPage, showStack, fit, scrollToPage, relayout, current, bookmarkTab, markSheet, bgSvg, pageSize } from './page.js';
import * as ink from './ink.js';
import * as store from './store.js';
import { initTray, closePanel, trayState, chooseTool, localTray, adopt as adoptTray } from './tray.js';
import * as pics from './snap.js';

const $ = (id) => document.getElementById(id);
const S = { folders: [], notes: [], pages: [], sel: 'loose', openNote: null, cur: 0, fold: {}, renaming: null,
            listOpen: false, hist: {}, clip: [], tick: null, user: null };
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
let openTok = 0;
async function openNote(id, index = 0) {
  if (!liveNote(note(id))) return;
  const tok = ++openTok;
  await store.ensure(pagesOf(id).map((p) => p.id));        // the pages' strokes from the device cache before the sheets attach
  if (tok !== openTok || !liveNote(note(id))) return;       // another note was opened meanwhile
  S.openNote = id; S.cur = index; S.listOpen = false; S.renaming = null; remember();
  document.body.classList.add('noteMode');
  if (!(history.state && history.state.note)) history.pushState({ note: id }, '');
  stackKey = ''; render(); fit(index);
}
function closeNote(skipHistory) {
  if (document.body.classList.contains('full')) exitFull();
  closePanel(); ink.clearSelection();
  if (S.openNote) { delete S.hist[S.openNote]; tidyInk(); }    // closing a note ends its undo history
  S.openNote = null; S.listOpen = false; S.tick = null; S.renaming = null; remember();
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
  if (list.length) pics.syncCover(list[0].note_id);          // U3b: the cover follows the first page
}
function insertPage(snap, i) {
  const list = pagesOf(snap.note_id);
  const p = { ...snap, position: i, deleted_at: null, bookmark: !!snap.bookmark, snapshot_path: null, snapshot_at: null };   // a new row: no picture yet
  list.splice(i, 0, p);
  const pairs = [];                                         // the pages below it move down one
  list.forEach((x, k) => { if (x !== p && x.position !== k) { x.position = k; pairs.push([x.id, k]); } });
  if (pairs.length) save(() => api.reorderPages(pairs));
  S.pages.push(p);
  save(() => api.createPage(p));                          // U3c: the row carries the bookmark (undo of a delete, a paste)
  store.change(p.id, [], ink.strokesOf(p.id));              // U3a: undo of a delete: the database cascaded its strokes, send them again
  touchNote(p.note_id);
  pics.syncCover(p.note_id);                                // U3b: a page at the top takes over the cover
}
function removePage(id) {
  const p = page(id), list = pagesOf(p.note_id).filter((x) => x !== p);
  S.pages = S.pages.filter((x) => x !== p);                 // the op's snapshot still holds its bookmark, for undo
  orphans.add(id);
  save(() => api.deletePage(id));
  store.unqueue(id);                                        // U3a: its strokes cascade on the server; queued ops for it can never land
  renumber(list);
  touchNote(p.note_id);
  pics.syncCover(p.note_id);                                // U3b: the first page gone: the next one's picture
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
// Samsung's page menu: Copy keeps the page (orientation, paper, strokes) on the page clipboard, Cut = Copy then
// Delete, Paste puts it below the pressed page, Erase page clears its strokes. The page clipboard is a list
// (pw-v4q): S.clip = [page, page, ...], one entry per page in list order; a single-page Copy makes a list of one.
// It is not tied to a note, so pages cut in one note paste into another (her ruling, 26 Oct).
const clipEntry = (p) => ({ orientation: p.orientation, background: p.background, bookmark: !!p.bookmark, strokes: ink.copyStrokes(p.id) });
function copyPage(i, quiet) {
  const p = pagesOf(S.openNote)[i];
  if (!p) return;
  S.clip = [clipEntry(p)];
  if (!quiet) toast('Page copied.');
}
function cutPage(i) {
  if (pagesOf(S.openNote).length <= 1) return;
  copyPage(i, true); deletePage(i); toast('Page cut.');
}
// every page on the clipboard, in order, directly after page i: one undo step
function pastePage(i) {
  const nid = S.openNote, clip = S.clip;
  if (!clip.length) return;
  const at = i + 1;
  const adds = clip.map((c) => {
    const snap = { id: uuid(), note_id: nid, orientation: c.orientation, background: c.background, bookmark: !!c.bookmark, created_at: nowIso() };
    return { snap, recs: c.strokes.map((r) => ({ ...JSON.parse(JSON.stringify(r)), id: uuid(), page_id: snap.id })) };
  });
  doOp({ pages: adds.map((a) => a.snap.id),
         redo: () => { adds.forEach((a, k) => { insertPage(a.snap, at + k); ink.put(a.snap.id, a.recs); }); shown(at); },
         undo: () => { adds.forEach((a) => removePage(a.snap.id)); shown(i); } });
}
const pagesWord = (n) => n + (n === 1 ? ' page' : ' pages');
// tick mode's Delete: the ticked pages go in ONE undo step (undo puts every one back in its place). A note keeps
// at least one page: when every page goes, one fresh empty page takes their place (in the same undo step).
function deletePages(ids) {
  const list = pagesOf(S.openNote), gone = list.map((p, k) => [k, { ...p }]).filter(([, p]) => ids.includes(p.id));
  if (!gone.length) return 0;
  const all = gone.length === list.length, first = gone[0][0], model = list[0];
  const fresh = all ? { id: uuid(), note_id: S.openNote, orientation: model.orientation, background: model.background, created_at: nowIso() } : null;
  const left = list.length - gone.length;
  doOp({ pages: [...gone.map(([, p]) => p.id), ...(fresh ? [fresh.id] : [])],
         redo: () => { gone.forEach(([, p]) => removePage(p.id)); if (fresh) insertPage(fresh, 0); shown(fresh ? 0 : Math.min(first, left - 1)); },
         undo: () => { if (fresh) removePage(fresh.id); gone.forEach(([k, p]) => insertPage(p, k)); shown(first); } });
  return gone.length;
}
// tick mode's Move: the ticked pages, in their current order, go to gap g of the unticked pages (0 = above the
// first unticked page, k = below unticked page k). ONE undo step; undo puts the old order back.
function setOrder(ids) {
  const list = ids.map(page).filter(Boolean);
  renumber(list);
  if (list.length) touchNote(list[0].note_id);
}
function movePages(ids, g) {
  const old = pagesOf(S.openNote).map((p) => p.id), set = new Set(ids);
  const moving = old.filter((id) => set.has(id)), rest = old.filter((id) => !set.has(id));
  const next = [...rest.slice(0, g), ...moving, ...rest.slice(g)];
  if (next.join() === old.join()) return false;
  const from = old.indexOf(moving[0]);
  doOp({ redo: () => { setOrder(next); shown(g); }, undo: () => { setOrder(old); shown(from); } });
  return true;
}
function erasePage(i) {
  const p = pagesOf(S.openNote)[i], op = p && ink.erasePageOp(p.id);
  if (!op) { toast('Nothing to erase on this page.'); return; }
  doOp(op);
}
// orientation or paper, for the current page or all of them
function setPaper(field, value, all) {
  const list = pagesOf(S.openNote), targets = all ? list : [list[S.cur]].filter(Boolean);
  const changes = targets.filter((p) => p[field] !== value).map((p) => ({ id: p.id, old: p[field] }));
  if (!changes.length) return;
  const at = S.cur;
  const put = (pairs) => {
    const groups = new Map();
    pairs.forEach(([id, v]) => { const p = page(id); if (!p) return; p[field] = v; groups.set(v, [...(groups.get(v) || []), id]); pics.changed(id); });   // U3b: a new paper, a new picture
    groups.forEach((ids, v) => save(() => api.setPages(ids, { [field]: v })));
    touchNote(S.openNote);
    shown(at);
  };
  doOp({ redo: () => put(changes.map((c) => [c.id, value])), undo: () => put(changes.map((c) => [c.id, c.old])) });
}

// a page's bookmark (pw-v4r), on or off from the page menu. Toggling is NOT an undo step (like Samsung Notes: a
// bookmark marks the page, it does not change what is on it), so undo and redo never touch it.
function setBookmark(id, on) {
  const p = page(id);
  if (!p) return;
  p.bookmark = on;
  save(() => api.setBookmark(id, on));                      // U3c: the row; not an edit, the note keeps its place
  markSheet(id, on);
  if (S.listOpen) renderPageList();
  toast(on ? 'Bookmarked' : 'Bookmark removed');
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
// anchor: an element (the menu under it, right edges lined up) or a point { x, y } (the menu's top-left 8 px down
// and right of it); either way the menu stays inside the viewport
function placeMenu(anchor) {
  const m = $('menu'); m.hidden = false;
  const mw = m.offsetWidth, mh = m.offsetHeight;
  if (!(anchor instanceof Element)) {
    m.style.left = Math.max(8, Math.min(innerWidth - mw - 8, anchor.x + 8)) + 'px';
    m.style.top = Math.max(8, Math.min(innerHeight - mh - 8, anchor.y + 8)) + 'px';
    return;
  }
  const a = anchor.getBoundingClientRect();
  m.style.left = Math.max(8, Math.min(innerWidth - mw - 8, a.right - mw)) + 'px';
  m.style.top = (a.bottom + mh + 8 < innerHeight ? a.bottom + 4 : Math.max(8, a.top - mh - 4)) + 'px';
}
function openMenu(anchor, items) {
  const m = $('menu'); m.textContent = '';
  for (const it of items.filter(Boolean)) {
    if (it.head) m.append(h('div', { class: 'hd' }, it.head));
    else m.append(h('button', { type: 'button', class: it.on ? 'on' : '', role: 'menuitem', disabled: !!it.disabled,
      onclick: (e) => { e.stopPropagation(); if (it.disabled) return; if (!it.keep) closeMenu(); it.fn(); } }, it.label));
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
  if (S.clip.length) items.push({ label: S.clip.length > 1 ? `Paste ${S.clip.length} pages` : 'Paste', fn: () => pastePage(i) });
  if (n > 1) items.push({ label: 'Delete', fn: () => deletePage(i) });
  items.push({ label: 'Erase page', fn: () => erasePage(i) });     // to move a page: hold it and drag (no Move up / down)
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
    { label: 'Lined', on: p.background === 'lined', keep: true, fn: () => ask('background', 'lined') },
    p.id ? { label: p.bookmark ? 'Remove bookmark' : 'Bookmark', fn: () => setBookmark(p.id, !p.bookmark) } : null,
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
    const thumb = h('div', { class: 'thumb' }, paper(first), n.pinned ? h('span', { class: 'pin', html: SVG_PIN, title: 'Pinned' }) : null);
    cardCover(thumb, n);
    const card = h('div', { class: 'card' + (n.pinned ? ' pinned' : ''), 'data-id': n.id, onclick: () => openNote(n.id) },
      thumb,
      h('div', { class: 'meta' },
        nameOrInput('note', n.id, n.name, 'card'),
        h('small', { class: 'when' }, edited(n.updated_at))));
    pressable(card, () => noteMenu(n.id, card.querySelector('.thumb'), 'card'));
    G.append(card);
  }
}

// U3b: a card shows its note's first page. On the tablet (anything wider than a phone), when that page's strokes are in
// the mirror already (the note was opened this session), its ink is drawn over the paper: sharper, and no download.
// Otherwise the cover picture (notes.cover_path), from this device's cover cache when it has the first page's current
// picture (same path, same snapshot_at), else downloaded once and kept. Until it is there the card shows the paper.
const coverUrl = new Map();        // note id -> { path, at, url } (one blob: URL per note while its picture stays)
const coverGets = new Map();       // note id + path + at -> the download on its way
function cardCover(thumb, n) {
  thumb.querySelectorAll('img.cover, .paper > svg.thumbInk').forEach((e) => e.remove());
  const first = pagesOf(n.id)[0];
  if (!first) return;
  if (!isPhone() && store.known(first.id)) {
    const svg = ink.thumbSvg(first.id, first.orientation);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid slice');
    thumb.querySelector('.paper').append(svg);
    return;
  }
  const path = n.cover_path, at = first.snapshot_at || null;
  if (!path) return;
  const put = (url) => {
    if (!thumb.isConnected && thumb.parentNode) return;     // a card the grid has since replaced (a new one is still being built: no parent yet)
    if (thumb.querySelector('img.cover, .paper > svg.thumbInk')) return;
    thumb.querySelector('.paper').after(h('img', { class: 'cover', src: url, alt: n.name, draggable: 'false' }));
  };
  const m = coverUrl.get(n.id);
  if (m && m.path === path && m.at === at) { put(m.url); return; }
  coverBlob(n.id, path, at).then((blob) => {
    const cur = note(n.id);
    if (!blob || !cur || cur.cover_path !== path) return;
    let k = coverUrl.get(n.id);
    if (!k || k.path !== path || k.at !== at) {
      if (k) URL.revokeObjectURL(k.url);
      k = { path, at, url: URL.createObjectURL(blob) };
      coverUrl.set(n.id, k);
    }
    put(k.url);
  });
}
async function coverBlob(nid, path, at) {
  const e = await store.coverGet(nid);
  if (e && e.path === path && e.at === at && e.blob) return e.blob;
  if (navigator.onLine === false) return null;
  const key = nid + ' ' + path + ' ' + at;
  if (!coverGets.has(key)) {
    coverGets.set(key, api.getSnapshot(path)
      .then(async (blob) => { await store.coverPut(nid, { path, at, blob }); return blob; })
      .catch(() => null)                                     // not there yet, or no connection: the paper stays
      .finally(() => coverGets.delete(key)));
  }
  return coverGets.get(key);
}
// js/snap.js: a note's cover changed (or its first page's picture did): just that card, never the whole grid
function refreshCard(nid) {
  const n = note(nid), card = n && document.querySelector(`#grid .card[data-id="${CSS.escape(nid)}"]`);
  if (card) cardCover(card.querySelector('.thumb'), n);
}

// ---------------------------------------------------------------- the note view
let stackKey = '';
function updateCount() {
  const list = S.openNote ? pagesOf(S.openNote) : [], n = list.length, c = Math.min(S.cur, n - 1);
  const txt = n ? `${c + 1} / ${n}` : '';
  $('counter').textContent = txt; $('barCount').textContent = txt;
  $('plCount').textContent = bmOnly ? list.filter((p) => p.bookmark).length + ' bookmarked' : txt;
  $('prevBtn').disabled = c <= 0; $('nextBtn').disabled = c >= n - 1;
  document.querySelectorAll('#plThumbs .thumbP').forEach((t) => t.classList.toggle('cur', +t.dataset.index === c + 1));
}
// the Bookmarks toggle in the list header (pw-v4r): on, the list shows only the bookmarked pages (a tap still jumps,
// the panel stays open) and the header says "<n> bookmarked". Kept while the app is open, off at start. Tick mode
// works on the shown pages; hold-and-drag and tick mode's Move are off while it is on (the shown pages are not
// side by side in the note, so a place between two of them means nothing).
let bmOnly = false;
const shownPages = () => { const all = S.openNote ? pagesOf(S.openNote) : []; return bmOnly ? all.filter((p) => p.bookmark) : all; };
function toggleBookmarks() {
  bmOnly = !bmOnly;
  renderPageList();
  $('plThumbs').scrollTop = 0;
}
function renderPageList() {
  const P = $('pageList');
  P.hidden = !S.listOpen;
  if (!S.listOpen) { S.tick = null; return; }                              // closing the panel ends tick mode
  const T = $('plThumbs'); T.textContent = '';
  const all = pagesOf(S.openNote), list = shownPages();
  const B = $('plMarks');
  B.classList.toggle('on', bmOnly); B.setAttribute('aria-pressed', bmOnly ? 'true' : 'false');
  if (bmOnly && !list.length) T.append(h('p', { class: 'plEmpty' }, 'No bookmarks yet'));
  list.forEach((p) => {
    const i = all.indexOf(p);                                                // the page's place in the note
    const t = h('div', { class: 'thumbP ' + p.orientation, 'data-index': i + 1, 'data-id': p.id, role: 'button', tabindex: '0',
      onclick: () => { if (S.tick) { if (!S.tick.moving) toggleTick(p.id); } else scrollToPage(i); },   // the panel stays open (her ruling, pw-v4i)
      onpointerdown: thumbDown,
      oncontextmenu: (e) => { e.preventDefault(); if (!pd && !S.tick) thumbMenu(i, t); } },   // right-click; a long press lifts instead
      paper(p, ' ' + p.orientation), h('span', { class: 'num' }, String(i + 1)),
      h('button', { class: 'more', type: 'button', 'aria-label': 'Page menu',
        onclick: (e) => { e.stopPropagation(); thumbMenu(i, e.currentTarget); } }, '⋯'),
      h('button', { class: 'tick', type: 'button', 'aria-label': 'Tick page ' + (i + 1), 'aria-pressed': 'false', html: SVG_TICK,
        onclick: (e) => { e.stopPropagation(); if (S.tick && !S.tick.moving) toggleTick(p.id); } }));
    if (p.bookmark) t.querySelector('.paper').append(bookmarkTab());           // the same ribbon tab as the page
    t.querySelector('.paper').append(ink.thumbSvg(p.id, p.orientation));   // the page's ink on the paper
    T.append(t);
  });
  renderTick();
  updateCount();
}

// ---------------------------------------------------------------- page list tick mode (pw-v4q)
// Select (in the list header) puts the list in tick mode, S.tick = { ids: Set of page ids, moving }. Every thumb shows
// a round tick box at its top-right; a thumb tap toggles its tick (the desk does not move); hold-and-drag and the page
// menu are off. The header shows All (tick every shown page, again to clear them), "<n> selected" and Done; a bar at
// the bottom has Delete, Copy, Cut and Move (disabled while nothing is ticked). Move swaps the bar for "Move <n> pages:
// tap where they go" and Cancel and puts a "Move here" bar above the first unticked page and below every unticked
// page, leaving out any spot where the move would change nothing. Done, the X, Escape and closing the panel end it.
const SVG_TICK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 12.5l3.6 3.6 7.4-8"/></svg>';
function ticked() {                                                         // the ticked pages, in list order
  if (!S.tick) return [];
  return shownPages().filter((p) => S.tick.ids.has(p.id)).map((p) => p.id);
}
function startTick() { if (!S.listOpen) return; S.tick = { ids: new Set(), moving: false }; closeMenu(); renderTick(); }
function endTick() { if (!S.tick) return; S.tick = null; renderTick(); }
function toggleTick(id) {
  const T = S.tick.ids;
  if (T.has(id)) T.delete(id); else T.add(id);
  renderTick();
}
function tickAll() {
  const ids = shownPages().map((p) => p.id), every = ids.length && ids.every((id) => S.tick.ids.has(id));
  S.tick.ids = new Set(every ? [] : ids);
  renderTick();
}
// the gaps a Move may use: g = 0 above the first unticked page, g = k below unticked page k; a gap where the move
// changes nothing is left out
function moveGaps() {
  const old = pagesOf(S.openNote).map((p) => p.id), set = S.tick.ids;
  const moving = old.filter((id) => set.has(id)), rest = old.filter((id) => !set.has(id));
  const out = [];
  if (!moving.length || !rest.length) return out;
  for (let g = 0; g <= rest.length; g++) {
    const next = [...rest.slice(0, g), ...moving, ...rest.slice(g)];
    if (next.join() !== old.join()) out.push({ g, before: g < rest.length ? rest[g] : null, after: g ? rest[g - 1] : null });
  }
  return out;
}
function tickAction(kind) {
  const ids = ticked(), n = ids.length;
  if (!n) return;
  if (kind === 'delete') { deletePages(ids); S.tick = { ids: new Set(), moving: false }; renderTick(); toast(pagesWord(n) + ' deleted'); }
  else if (kind === 'copy' || kind === 'cut') {
    S.clip = shownPages().filter((p) => S.tick.ids.has(p.id)).map(clipEntry);
    S.tick = null;
    if (kind === 'cut') deletePages(ids); else renderTick();
    toast(pagesWord(n) + (kind === 'cut' ? ' cut' : ' copied'));
  } else if (kind === 'move') { S.tick.moving = true; renderTick(); }
  else if (kind === 'share') openShare(ids);
}
function moveTo(g) {
  const ids = ticked();
  S.tick = null;
  if (!movePages(ids, g)) { renderTick(); return; }
  const t = document.querySelector(`#plThumbs .thumbP[data-index="${g + 1}"]`);   // the first moved page, in the list
  if (t && t.scrollIntoView) t.scrollIntoView({ block: 'nearest' });
}
// the tick look, the header and the bar (no thumb is rebuilt: a tap stays quick on a heavy note)
function renderTick() {
  const P = $('pageList'), on = !!S.tick && S.listOpen, T = $('plThumbs');
  P.classList.toggle('ticking', on);
  P.classList.toggle('moving', on && S.tick.moving);
  const ids = on ? new Set(ticked()) : new Set(), n = ids.size, total = shownPages().length;
  T.querySelectorAll('.moveHere').forEach((el) => el.remove());
  T.querySelectorAll('.thumbP').forEach((t) => {
    const yes = ids.has(t.dataset.id);
    t.classList.toggle('ticked', yes);
    t.querySelector('.tick').setAttribute('aria-pressed', yes ? 'true' : 'false');
  });
  $('plAll').hidden = !on; $('plSel').hidden = !on; $('plDone').hidden = !on;
  $('plCount').hidden = on; $('plSelect').hidden = on; $('plMarks').hidden = on;
  const all = on && total > 0 && n === total;
  $('plAll').classList.toggle('on', all); $('plAll').setAttribute('aria-pressed', all ? 'true' : 'false');
  $('plSel').textContent = on ? n + ' selected' : '';
  const B = $('plBar'); B.textContent = ''; B.hidden = !on;
  if (!on) return;
  if (S.tick.moving) {
    B.append(h('span', { class: 'moveLbl' }, `Move ${pagesWord(n)}: tap where ${n === 1 ? 'it goes' : 'they go'}`),
             h('button', { type: 'button', class: 'plAct', 'data-act': 'cancel', onclick: () => { S.tick.moving = false; renderTick(); } }, 'Cancel'));
    for (const s of moveGaps()) {
      const bar = h('button', { type: 'button', class: 'moveHere', 'data-gap': s.g, onclick: () => moveTo(s.g) }, 'Move here');
      const ref = s.before && T.querySelector(`.thumbP[data-id="${CSS.escape(s.before)}"]`);
      const aft = s.after && T.querySelector(`.thumbP[data-id="${CSS.escape(s.after)}"]`);
      if (aft) aft.after(bar); else if (ref) ref.before(bar);
    }
    return;
  }
  for (const [act, label] of [['delete', 'Delete'], ['copy', 'Copy'], ['cut', 'Cut'], ['move', 'Move'], ['share', 'Share']]) {
    const off = !n || (act === 'move' && (n === total || bmOnly));          // moving every page changes nothing; no Move in the filter
    B.append(h('button', { type: 'button', class: 'plAct', 'data-act': act, disabled: off, onclick: () => tickAction(act) }, label));
  }
}
// ---------------------------------------------------------------- share the ticked pages (pw-v4t)
// Share (last in the tick bar) opens a small dialog: a Name box (the note's name, plus " p3" or " p3-5" when the ticked
// pages are not the whole note, all of it selected) and Share as PDF / Share as images. Cancel, Escape or a tap outside
// closes it. Every ticked page is drawn off-screen at 2x page px: one SVG (white paper, its paper pattern, both ink
// layers with the highlighter groups' opacity) through a Blob URL into an <img>, onto a <canvas>, then toBlob. The PDF
// (vendor/jspdf.umd.min.js, loaded the first time) gets one A4 page per page in note order, in that page's orientation,
// a JPEG 0.92 at full bleed; images are one PNG per page. navigator.share takes the files when it can (Android: the
// system share sheet); otherwise, or when it fails with anything but a cancel, every file downloads. Tick mode ends
// after a share. Her ask (26 Oct): Samsung Notes never lets her name the PDF before it goes.
const SVGNS = 'http://www.w3.org/2000/svg';
const SHARE_SCALE = 2;
const fileName = (t) => String(t).replace(/[^\p{L}\p{N} _\-()[\]]/gu, '').trim() || 'PenWorks';
// the name box's first text: the note's name, plus the page numbers when not every page of the note is ticked
function shareName(ids) {
  const all = pagesOf(S.openNote), nums = ids.map((id) => all.findIndex((p) => p.id === id) + 1).filter((k) => k > 0).sort((a, b) => a - b);
  const base = (note(S.openNote) || {}).name || 'PenWorks';
  if (!nums.length || nums.length === all.length) return base;
  const a = nums[0], b = nums[nums.length - 1];
  return base + ' p' + (a === b ? a : a + '-' + b);
}
// one page as an SVG document at 2x (the share; U3b's page picture asks for 1x): the viewBox is the page in page px, so
// the paper and the ink keep their own numbers. `recs` given = those records instead of the page's own (U3b).
function pageSvgText(p, scale = SHARE_SCALE, recs = null) {
  const { w, h } = pageSize(p.orientation);
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('width', w * scale); svg.setAttribute('height', h * scale);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  const white = document.createElementNS(SVGNS, 'rect');
  white.setAttribute('width', w); white.setAttribute('height', h); white.setAttribute('fill', '#FFFFFF');
  svg.append(white);
  const bg = bgSvg(w, h, p.background);
  while (bg.firstChild) svg.append(bg.firstChild);
  const layer = ink.thumbSvg(p.id, p.orientation, recs);           // the page's ink, built from its records (hl below pen)
  while (layer.firstChild) svg.append(layer.firstChild);
  return new XMLSerializer().serializeToString(svg);
}
async function renderPage(p, type, quality, scale = SHARE_SCALE, recs = null) {
  const { w, h } = pageSize(p.orientation), W = w * scale, H = h * scale;
  const url = URL.createObjectURL(new Blob([pageSvgText(p, scale, recs)], { type: 'image/svg+xml' }));
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const g = c.getContext('2d');
    g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, W, H);
    g.drawImage(img, 0, 0, W, H);
    return await new Promise((ok, no) => c.toBlob((b) => (b ? ok(b) : no(new Error('a page could not be drawn'))), type, quality));
  } finally { URL.revokeObjectURL(url); }
}
let jspdfLoad = null;
function loadJsPdf() {
  if (window.jspdf) return Promise.resolve(window.jspdf);
  return (jspdfLoad ||= new Promise((ok, no) => {
    const s = document.createElement('script');
    s.src = './vendor/jspdf.umd.min.js';
    s.onload = () => (window.jspdf ? ok(window.jspdf) : no(new Error('the PDF maker did not load')));
    s.onerror = () => { jspdfLoad = null; s.remove(); no(new Error('the PDF maker did not load')); };
    document.head.append(s);
  }));
}
// the ticked pages as File objects; progress(k, n) before page k of n
async function shareFiles(ids, kind, name, progress) {
  const list = ids.map(page).filter(Boolean), n = list.length, blobs = [];
  for (let k = 0; k < n; k++) {
    progress(k + 1, n);
    await new Promise((r) => setTimeout(r, 0));                     // a yield between pages: the screen stays alive
    blobs.push(await renderPage(list[k], kind === 'pdf' ? 'image/jpeg' : 'image/png', kind === 'pdf' ? 0.92 : undefined));
  }
  if (kind === 'images') {
    return blobs.map((b, k) => new File([b], n === 1 ? name + '.png' : `${name}-${k + 1}.png`, { type: 'image/png' }));
  }
  const { jsPDF } = await loadJsPdf();
  let doc = null;
  for (let k = 0; k < n; k++) {
    const o = list[k].orientation === 'landscape' ? 'landscape' : 'portrait';
    if (!doc) doc = new jsPDF({ orientation: o, unit: 'pt', format: 'a4', compress: true });
    else doc.addPage('a4', o);
    const pw = doc.internal.pageSize.getWidth(), ph = doc.internal.pageSize.getHeight();
    doc.addImage(new Uint8Array(await blobs[k].arrayBuffer()), 'JPEG', 0, 0, pw, ph, undefined, 'NONE');
  }
  doc.setProperties({ title: name });
  return [new File([doc.output('blob')], name + '.pdf', { type: 'application/pdf' })];
}
// the share sheet when it takes files, else one download per file (150 ms apart); '' when she cancelled the sheet
async function deliver(files, name) {
  let can = false;
  try { can = typeof navigator.share === 'function' && !!navigator.canShare && navigator.canShare({ files }); } catch (_) { can = false; }
  if (can) {
    try { await navigator.share({ files, title: name }); return 'Shared'; }
    catch (e) { if (e && e.name === 'AbortError') return ''; }      // any other refusal: download instead
  }
  for (let k = 0; k < files.length; k++) {
    if (k) await new Promise((r) => setTimeout(r, 150));
    const url = URL.createObjectURL(files[k]), a = h('a', { href: url, download: files[k].name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  return 'Saved to downloads';
}
// the dialog: centred on a veil, the app's card look. While it works its buttons are off (and, past 3 pages, the
// pressed one counts "Rendering 2 / 12"); Cancel, Escape and a tap outside do nothing until it is done.
let shareDlg = null;
function closeShare() { if (shareDlg) { shareDlg.remove(); shareDlg = null; } }
function openShare(ids) {
  closeShare(); closeMenu();
  let busy = false;
  const inp = h('input', { class: 'dlgName', id: 'shareName', value: shareName(ids), 'aria-label': 'Name', autocomplete: 'off', spellcheck: 'false' });
  const go = async (kind, btn) => {
    if (busy) return;
    busy = true;
    const name = fileName(inp.value), label = btn.textContent;
    btns.forEach((b) => { b.disabled = true; }); inp.disabled = true;
    try {
      const files = await shareFiles(ids, kind, name, (k, n) => { if (n > 3) btn.textContent = `Rendering ${k} / ${n}`; });
      btn.textContent = label;
      const said = await deliver(files, name);
      closeShare();
      if (said) { endTick(); toast(said); }
    } catch (e) {
      closeShare();
      toast('Could not share: ' + ((e && e.message) || e));
    }
  };
  const pdfBtn = h('button', { type: 'button', class: 'dlgBtn main', 'data-share': 'pdf', onclick: () => go('pdf', pdfBtn) }, 'Share as PDF');
  const imgBtn = h('button', { type: 'button', class: 'dlgBtn main', 'data-share': 'images', onclick: () => go('images', imgBtn) }, 'Share as images');
  const cancel = h('button', { type: 'button', class: 'dlgBtn', 'data-share': 'cancel', onclick: () => { if (!busy) closeShare(); } }, 'Cancel');
  const btns = [pdfBtn, imgBtn, cancel];
  const box = h('div', { class: 'dlg', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'shareTitle' },
    h('b', { class: 'dlgTitle', id: 'shareTitle' }, 'Share ' + pagesWord(ids.length)),
    h('label', { class: 'dlgLbl', for: 'shareName' }, 'Name'), inp,
    h('div', { class: 'dlgRow' }, pdfBtn, imgBtn), h('div', { class: 'dlgRow end' }, cancel));
  shareDlg = h('div', { class: 'dlgVeil', id: 'shareDlg' }, box);
  shareDlg.addEventListener('pointerdown', (e) => { if (e.target === shareDlg && !busy) closeShare(); });
  shareDlg.addEventListener('keydown', (e) => {
    e.stopPropagation();                                            // the app's own keys (Escape ends tick mode) wait
    if (e.key === 'Escape' && !busy) closeShare();
  });
  document.body.append(shareDlg);
  inp.focus(); inp.select();
}

// the thumb of a page whose ink changed (ink.js apply: drawing, erasing, undo, redo): rebuild just its svg, once per
// frame, so a stroke that lands in many pieces rebuilds once
const thumbDue = new Set();
let thumbRaf = 0;
function refreshThumb(pageId) {
  thumbDue.add(pageId);
  if (thumbRaf) return;
  thumbRaf = requestAnimationFrame(() => {
    thumbRaf = 0;
    const ids = [...thumbDue]; thumbDue.clear();
    if (!S.listOpen) return;
    for (const id of ids) {
      const t = document.querySelector(`#plThumbs .thumbP[data-id="${CSS.escape(id)}"]`), p = t && page(id);
      if (!t || !p) continue;
      const old = t.querySelector('.paper > svg.thumbInk'), svg = ink.thumbSvg(id, p.orientation);
      if (old) old.replaceWith(svg); else t.querySelector('.paper').append(svg);
    }
  });
}

// page list: hold a page (350 ms, still) and drag it to its place. A quick tap goes to the page, a move
// before the hold time scrolls the list. While a page is lifted the others slide apart to show the gap
// (the nearest slot by centre distance), the list scrolls near its top and bottom edge, and the drop is
// ONE undo step. pointercancel puts it back where it was.
const HOLD_MS = 350, HOLD_PX = 6, EDGE = 40;
let pd = null, eatThumbClick = false;
function thumbDown(e) {
  if (e.button !== 0 || pd || S.tick || bmOnly || e.target.closest('button') || pagesOf(S.openNote).length < 2) return;   // one page, tick mode or the Bookmarks filter: nothing lifts
  pd = { t: e.currentTarget, id: e.pointerId, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, lifted: false,
         timer: setTimeout(liftPage, HOLD_MS) };
  addEventListener('pointermove', pageDragMove, { passive: false });
  addEventListener('pointerup', pageDragUp);
  addEventListener('pointercancel', pageDragCancel);
}
function liftPage() {
  const d = pd;
  if (!d) return;
  d.timer = 0;
  const T = $('plThumbs');
  d.r = T.getBoundingClientRect();
  d.list = [...T.querySelectorAll('.thumbP')];
  d.from = d.to = d.list.indexOf(d.t);
  if (d.from < 0) { endPageDrag(true); return; }
  d.max = Math.max(0, T.scrollHeight - T.clientHeight);          // the lifted page must not stretch the list
  d.p0 = [d.x0 - d.r.left, d.y0 - d.r.top + T.scrollTop];         // where it was picked up, in list coordinates
  d.slots = d.list.map((el) => {
    const b = el.getBoundingClientRect();
    return [b.left - d.r.left + b.width / 2, b.top - d.r.top + T.scrollTop + b.height / 2];
  });
  d.lifted = true;
  closeMenu();
  T.classList.add('dragging'); d.t.classList.add('lift');
  placeLift();
  const edge = () => {
    if (!pd || pd !== d) return;
    const top = d.y - d.r.top, bot = d.r.bottom - d.y;
    let v = 0;
    if (top < EDGE) v = -(1 + 5 * Math.min(1, (EDGE - top) / EDGE));
    else if (bot < EDGE) v = 1 + 5 * Math.min(1, (EDGE - bot) / EDGE);
    const st = Math.max(0, Math.min(d.max, T.scrollTop + v));
    if (v && st !== T.scrollTop) { T.scrollTop = st; placeLift(); }
    d.raf = requestAnimationFrame(edge);
  };
  d.raf = requestAnimationFrame(edge);
}
function placeLift() {
  const d = pd, T = $('plThumbs');
  const px = d.x - d.r.left, py = d.y - d.r.top + T.scrollTop;
  let to = d.from, best = Infinity;
  d.slots.forEach(([cx, cy], k) => { const dist = Math.hypot(px - cx, py - cy); if (dist < best) { best = dist; to = k; } });
  d.to = to;
  d.list.forEach((el, k) => {
    if (k === d.from) return;
    let n = k < d.from ? k : k - 1;                                   // its place with the lifted page taken out
    if (n >= to) n++;                                                  // and the gap opened at `to`
    const [ax, ay] = d.slots[k], [bx, by] = d.slots[n];
    el.style.transform = n === k ? '' : `translate(${bx - ax}px, ${by - ay}px)`;
  });
  d.t.style.transform = `translate(${px - d.p0[0]}px, ${py - d.p0[1]}px) scale(1.06)`;
}
function pageDragMove(e) {
  const d = pd;
  if (!d || e.pointerId !== d.id) return;
  d.x = e.clientX; d.y = e.clientY;
  if (!d.lifted) {                                                     // moved before the hold time: a scroll, nothing lifts
    if (d.timer && Math.hypot(d.x - d.x0, d.y - d.y0) > HOLD_PX) endPageDrag(true);
    return;
  }
  e.preventDefault();
  placeLift();
}
function pageDragUp(e) { if (pd && e.pointerId === pd.id) endPageDrag(false); }
function pageDragCancel(e) { if (pd && e.pointerId === pd.id) endPageDrag(true); }
function endPageDrag(cancelled) {
  const d = pd;
  pd = null;
  clearTimeout(d.timer); cancelAnimationFrame(d.raf);
  removeEventListener('pointermove', pageDragMove, { passive: false });
  removeEventListener('pointerup', pageDragUp);
  removeEventListener('pointercancel', pageDragCancel);
  if (!d.lifted) return;                                               // a tap: the click goes to the page
  eatThumbClick = true;                                                // the click that ends a drag goes nowhere
  $('plThumbs').classList.remove('dragging');
  d.t.classList.remove('lift');
  d.list.forEach((el) => { el.style.transform = ''; });
  const from = d.from, to = d.to, p = pagesOf(S.openNote)[from];
  if (cancelled || to === from || !p) return;                          // same slot or cancelled: nothing moves
  const id = p.id;
  doOp({ redo: () => { movePage(id, to); shown(to); }, undo: () => { movePage(id, from); shown(from); } });
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
  const prof = api.profile().catch(() => null);           // U3c: the tray state, asked for beside the notes
  let d;
  try { d = await api.loadAll(); }
  catch (_) { toast('Could not load your notes. Check the connection, then reload.', 8000); return; }
  S.folders = d.folders; S.notes = d.notes; S.pages = d.pages;
  S.pages.forEach((p) => { p.bookmark = p.bookmark === true; });         // U3c: the row's column (0004)
  takeOverBookmarks();
  try { S.fold = JSON.parse(localStorage.getItem(PREF + 'fold') || '{}') || {}; } catch (_) { S.fold = {}; }
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(PREF + 'open') || '{}') || {}; } catch (_) { /* ignore */ }
  if (saved.sel === 'loose' || saved.sel === 'bin' || liveFolder(folder(saved.sel))) S.sel = saved.sel;
  render();
  if (saved.note && liveNote(note(saved.note))) await openNote(saved.note);
  trayFrom(await prof);
  document.body.dataset.ready = '1';
}

// U3c, once per device: bookmarks from pw-v4r were kept in localStorage (pw.bookmark.<page_id> = '1'). A page that is
// still there (live or in the bin) and not yet bookmarked in its row takes the bookmark through the database, and its
// key goes once the row has it; every other pw.bookmark.* key goes at once. A failed write keeps its key for next time.
const OLD_MARK = 'pw.bookmark.';
let tookOver = { keys: 0, set: 0 };
function takeOverBookmarks() {
  const keys = [];
  try {
    for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.startsWith(OLD_MARK)) keys.push(k); }
  } catch (_) { return; }
  const drop = (k) => { try { localStorage.removeItem(k); } catch (_) { /* ignore */ } };
  tookOver = { keys: keys.length, set: 0 };
  for (const k of keys) {
    const id = k.slice(OLD_MARK.length), p = page(id);
    let on = false;
    try { on = localStorage.getItem(k) === '1'; } catch (_) { /* ignore */ }
    if (!on || !p || p.bookmark) { drop(k); continue; }
    p.bookmark = true;
    tookOver.set++;
    save(async () => { await api.setBookmark(id, true); drop(k); });
  }
}

// ---------------------------------------------------------------- the tray state across devices (U3c)
// profiles.settings = { tray: <what tray.js keeps>, tray_at: <ISO stamp> }; this device keeps the same with its own
// tray_at. At start the database's copy wins only when it is newer: both stamps there and the database's later, or no
// copy on this device at all. A copy here without a stamp (saved before U3c, or a test's seed) wins over the database.
// Every tray change goes up a second after the last one, one update in flight, retried (2, 5, 10, 30 s, and on
// `online`) until it lands. No dot, no toast: the tray state is a convenience, not her ink.
const TRAY_MS = 1000, TRAY_BACKOFF = [2000, 5000, 10000, 30000];
const later = (a, b) => Date.parse(a) > Date.parse(b);
let trayNext = null, trayT = null, trayBusy = false, trayTries = 0;
function trayFrom(profile) {
  const s = (profile && profile.settings) || {}, mine = localTray();
  const theirs = s.tray && typeof s.tray === 'object' && typeof s.tray_at === 'string' && !isNaN(Date.parse(s.tray_at)) ? s : null;
  if (theirs && (!mine.present || (mine.at && later(theirs.tray_at, mine.at)))) { adoptTray(theirs.tray, theirs.tray_at); return; }
  // this device's stamped copy is the newer one (or the database has none): it goes up, under its own stamp
  if (profile && mine.present && mine.at && (!theirs || later(mine.at, theirs.tray_at))) { trayNext = { tray: mine.tray, at: mine.at }; trayFlush(); }
}
function trayKeep(tray, at) {
  trayNext = { tray, at };
  clearTimeout(trayT);
  trayT = setTimeout(trayFlush, TRAY_MS);
}
async function trayFlush() {
  trayT = null;
  if (trayBusy || !trayNext) return;
  const s = trayNext;
  trayNext = null; trayBusy = true;
  let ok = true;
  try { await api.setSettings({ tray: s.tray, tray_at: s.at }); }
  catch (_) { ok = false; if (!trayNext) trayNext = s; }
  trayBusy = false;
  if (ok) trayTries = 0;
  if (!trayNext || trayT) return;                          // nothing left, or a newer change is still waiting its second
  trayT = setTimeout(trayFlush, ok ? 0 : TRAY_BACKOFF[Math.min(trayTries++, TRAY_BACKOFF.length - 1)]);
}
addEventListener('online', () => { if (trayNext && !trayBusy) { clearTimeout(trayT); trayFlush(); } });

async function enter(user) {
  S.user = user;
  $('login').hidden = true; $('app').hidden = false;
  if (api.mode === 'local') { $('modeNote').textContent = 'local copy'; $('logoutBtn').hidden = true; }
  store.init({ mode: api.mode, userId: user.id, api, idle: () => chain, onRemote: ink.replace, onState: saveDot, onPushed: pics.pushed });
  pics.initSnap({ api, store, ink, owner: () => user.id, pages: () => S.pages, page, note, pagesOf, liveNote, onCover: refreshCard,
                  render: (p, recs) => renderPage(p, 'image/webp', 0.8, 1, recs),
                  idle: async () => { await chain; await store.settled(); await chain; } });
  await load();
  pics.scan();                                              // U3b rule (b): pages whose picture is older than their ink
}

// the save dot (U3a) beside the dark-mode toggle: grey saved, blue saving, amber waiting, red refused. No text, no toast.
const DOT_TITLE = { saved: () => 'All saved', saving: () => 'Saving', refused: () => 'A change was refused, see the console',
                    waiting: (n) => `Waiting for a connection, ${n} ${n === 1 ? 'change' : 'changes'} to send` };
// Two dots, the same state: one in the folder view's footer, one in the note bar (the footer is hidden while she writes).
function saveDot(state, count) {
  if (!DOT_TITLE[state]) return;
  const title = DOT_TITLE[state](count);
  document.querySelectorAll('.saveDot').forEach((d) => {
    d.dataset.state = state;
    d.title = title;
    d.setAttribute('aria-label', title);
  });
}

// ---------------------------------------------------------------- the pen button (pw-v4v)
// Her S Pen's button reaches Chrome only as one contextmenu on the desk per press (page.js passes it here, never a
// finger's). It flips the tool: Select from anything else, and from Select back to the last ink tool (pen or
// highlighter), through the tray, exactly like a tap on the tray button. It does nothing while the pen is on the paper,
// or while the page list (tick mode included), a menu (the Paste menu too), a tray panel or a dialog is open.
let rightOverOpen = false;
function overlayOpen() {
  return S.listOpen || !!S.tick || !$('menu').hidden || !!document.querySelector('[role="dialog"]:not([hidden])');
}
function penButton() {
  const blocked = rightOverOpen; rightOverOpen = false;
  if (blocked || overlayOpen() || ink.busy()) return;
  const t = ink.tool();
  chooseTool(t.tool === 'select' ? t.lastInk : 'select');
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
  ink.initInk({ doOp, desk: $('desk'), onChange: (pageId) => { if (S.listOpen) refreshThumb(pageId); pics.changed(pageId); },
                toast, openMenuAt: (x, y, items) => openMenu({ x, y }, items), selectTool: () => chooseTool('select') });
  // a right mouse press that lands while something is open (the press itself closes it before its contextmenu):
  // remembered here, before the tray's and the menu's own closers run, so that contextmenu does not flip the tool
  document.addEventListener('pointerdown', (e) => { rightOverOpen = e.button === 2 && overlayOpen(); }, true);   // any other press forgets it
  initTray({ onKeep: (tray, at) => trayKeep(tray, at) });
  initPage({ desk: $('desk'), stack: $('stack'), addBelow: $('addBelow'),
             onCurrent: (i) => { S.cur = Math.max(0, i); updateCount(); ink.clearSelection(); },   // a new page: the selection clears
             onSheets: ink.attach, ink: ink.hook, onPenButton: penButton });
  if (new URLSearchParams(location.search).get('dbg') === '1') import('./dbg.js').then((m) => m.startDbg($('desk'), ink));   // the pen readout, ?dbg=1 only
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
  $('plSelect').addEventListener('click', startTick);
  $('plMarks').addEventListener('click', toggleBookmarks);
  $('plDone').addEventListener('click', endTick);
  $('plAll').addEventListener('click', () => { if (S.tick && !S.tick.moving) tickAll(); });
  // a lifted page: Chrome has not started a scroll (the finger was still for the hold), so cancelling the
  // touchmove keeps it from starting; the click that ends a drag is eaten, a fresh press clears that
  $('plThumbs').addEventListener('touchmove', (e) => { if (pd && pd.lifted && e.cancelable) e.preventDefault(); }, { passive: false });
  $('plThumbs').addEventListener('pointerdown', () => { eatThumbClick = false; }, true);
  $('plThumbs').addEventListener('click', (e) => { if (eatThumbClick) { eatThumbClick = false; e.stopPropagation(); e.preventDefault(); } }, true);
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
      else if (S.tick && S.tick.moving) { S.tick.moving = false; renderTick(); }      // Escape in Move: back to the ticks
      else if (S.tick) endTick();                                                  // Escape in tick mode: the list stays open
      else if (S.listOpen) { S.listOpen = false; renderPageList(); }
      else if (document.body.classList.contains('full') && !document.fullscreenElement) exitFull();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
  });
  let wasPhone = isPhone();
  window.addEventListener('resize', () => { if (isPhone() !== wasPhone) { wasPhone = isPhone(); render(); } });
}

// test hook: the checks wait for writes and clean up their rows through this
window.__pw = { S, api, idle: async () => { await chain; await store.settled(); await chain; }, failed: () => failed, current, ink, store, tray: trayState,
                snap: pics.snapStats, renderGrid, covers: coverUrl, bookmarksTaken: () => ({ ...tookOver }),
                trayPending: () => ({ next: !!trayNext, busy: trayBusy, timer: !!trayT }),
                pageDrag: () => (pd ? { lifted: pd.lifted, from: pd.from, to: pd.to } : null),
                tick: () => (S.tick ? { ids: ticked(), moving: S.tick.moving } : null) };

wire();
(async () => {
  let user = null;
  try { user = await api.session(); } catch (_) { /* treat as logged out */ }
  if (user) enter(user);
  else { $('login').hidden = false; $('lu').focus(); }
})();
