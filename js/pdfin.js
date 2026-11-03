// PenWorks PDF in (U4a): the + button opens a PDF as note pages, her ink on top (js/pdfview.js draws them).
// importPdf(file, target) is the one way in: target = { folderId } makes a NEW note named after the file (the name
// without .pdf) in that folder (null = Loose), target = { noteId } puts the PDF's pages at the END of that note. U4b's
// share target calls it the same way with the File sw.js kept for it (sharedFile, at the end of this file).
//
// The file is read once. Over 50 MB (the imports bucket's limit), a broken file or a password-protected one: ONE plain
// toast and nothing made. Otherwise its bytes are kept on this device at once (IndexedDB, a database of its own,
// penworks.<mode>.<user id>.pdf, store `files`, key = the storage path), so the pages draw straight away and offline,
// and app.js (cfg.makeNote / cfg.addPages) makes the note and one page row per PDF page through save(), the tree queue
// (js/treeq.js): a PDF opened without wifi lands later like any page. Each row: pdf_path = <owner>/<a new uuid>.pdf in
// the `imports` bucket, pdf_page 1-based (as pdf.js counts), pdf_w / pdf_h = that page's size in PDF points at scale 1
// (after its own rotation), orientation = landscape when wider than tall, background = blank.
// The bytes go up to `imports` in the background, one file at a time, retried 2, 5, 10, 30 s after a failure (js/snap.js's
// ladder), and on `online` or when the app is visible again; they stay on the device after the upload. A device without
// them (the phone) downloads them the first time it draws such a page, and keeps them.
// pdf.js (vendor/pdf.min.mjs and its worker) loads the first time a PDF is opened or drawn, never on app start.
// U4c (pw-v8n): pictures share all of it (keepImport, bytesOf, the upload ladder); importImage reads, downscales and keeps one.

const LIB = new URL('../vendor/pdf.min.mjs', import.meta.url).href;           // beside the app, whatever page loads this file
const WORKER = new URL('../vendor/pdf.worker.min.mjs', import.meta.url).href;
const MAX_BYTES = 52428800;                       // 50 MB, the bucket's file_size_limit (0002)
const BACKOFF = [2000, 5000, 10000, 30000];
const DOCS = 3;                                   // open PDF documents kept (each one lives in the pdf.js worker)
const LOCAL_MARK = 'pw.pdf.local';                // local mode only: a cleared localStorage is a fresh twin, so the cache starts fresh
export const TOO_BIG = 'This PDF is too big to open (over 50 MB).';
export const BROKEN = 'This PDF could not be opened.';

const cfg = {
  mode: 'local', userId: 'local', api: null,
  toast: () => {},
  makeNote: null,       // (folderId, name) -> note id: the note row, through save()
  addPages: null,       // (noteId, specs, isNew) -> the page rows through save(), then the note on screen
  onBytes: () => {},    // (path) the bytes of that PDF (or U4c picture) are on this device now (the pages can draw)
  placeImage: null,     // U4c: (pageId, { path, nw, nh, blob }) -> the picture's record on that page (js/ink.js placeImage)
};
let dbp = Promise.reject(new Error('initPdf has not run'));
dbp.catch(() => {});
const mem = new Map();                            // path -> record, when the device would not keep it (no IndexedDB)
const gets = new Map();                           // path -> a download on its way
const docs = new Map();                           // path -> { p: Promise<PDFDocumentProxy>, used }
let lib = null, useN = 0, importing = Promise.resolve();
let upBusy = false, upT = 0, upTries = 0, upTold = false;
const stats = { imports: 0, uploads: 0, downloads: 0, failures: 0, opened: 0, pictures: 0 };

// ---------------------------------------------------------------- IndexedDB, the device's copy of each opened PDF
function openDb(name) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(name, 1);
    r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains('files')) r.result.createObjectStore('files'); };
    r.onsuccess = () => { const db = r.result; db.onversionchange = () => db.close(); resolve(db); };
    r.onerror = () => reject(r.error);
  });
}
function dropDb(name) {
  return new Promise((resolve) => { const r = indexedDB.deleteDatabase(name); r.onsuccess = r.onerror = r.onblocked = () => resolve(); });
}
function run(mode, fn) {
  return dbp.then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(['files'], mode), out = {};
    fn(t.objectStore('files'), out);
    t.oncomplete = () => resolve(out);
    t.onerror = t.onabort = () => reject(t.error);
  }));
}
// a record: { path, blob, up (true once it is in the bucket), at, name }
async function getRec(path) {
  try { const o = await run('readonly', (s, out) => { s.get(path).onsuccess = (e) => { out.v = e.target.result || null; }; }); if (o.v) return o.v; }
  catch (_) { /* fall back to memory */ }
  return mem.get(path) || null;
}
async function putRec(rec) {
  try { await run('readwrite', (s) => { s.put(rec, rec.path); }); mem.delete(rec.path); return true; }
  catch (e) { mem.set(rec.path, rec); console.warn('PenWorks: an opened PDF could not be kept on this device', e); return false; }
}
async function allRecs() {
  let list = [];
  try { list = (await run('readonly', (s, out) => { s.getAll().onsuccess = (e) => { out.v = e.target.result || []; }; })).v; }
  catch (_) { list = []; }
  return [...list, ...mem.values()];
}

// ---------------------------------------------------------------- start
export function initPdf(o) {
  Object.assign(cfg, o);
  const name = `penworks.${o.mode}.${o.userId}.pdf`, tname = `penworks.${o.mode}.${o.userId}.thumbs`;
  let wipe = Promise.resolve();
  if (o.mode === 'local') {
    try { if (localStorage.getItem(LOCAL_MARK) !== name) { wipe = Promise.all([dropDb(name), dropDb(tname)]); localStorage.setItem(LOCAL_MARK, name); } }
    catch (_) { /* ignore */ }
  }
  dbp = wipe.then(() => openDb(name));
  dbp.catch((e) => console.warn('PenWorks: no device copy for opened PDFs', e));
  tdbp = wipe.then(() => openThumbDb(tname));
  tdbp.catch(() => {});                           // no thumb store: thumbs are made again each session, as before pw-v7n
  dbp.then(() => kickUploads(), () => kickUploads());
  const now = () => { clearTimeout(upT); upT = 0; kickUploads(); };   // a retry waiting goes at once
  addEventListener('online', () => { upTries = 0; now(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) now(); });
}

// pdf.js itself, the first time it is needed
export function loadLib() {
  return (lib ||= import(LIB).then((m) => { m.GlobalWorkerOptions.workerSrc = WORKER; return m; })
    .catch((e) => { lib = null; throw e; }));
}

// ---------------------------------------------------------------- the bytes and the open documents (js/pdfview.js)
// the PDF's bytes as a Blob: this device's copy, else the bucket (then kept here); null when they cannot be had now
export async function bytesOf(path) {
  const r = await getRec(path);
  if (r && r.blob) return r.blob;
  if (navigator.onLine === false || !cfg.api) return null;
  if (!gets.has(path)) {
    gets.set(path, cfg.api.getImport(path)
      .then(async (blob) => {
        stats.downloads++;
        await putRec({ path, blob, up: true, at: new Date().toISOString(), name: '' });
        try { cfg.onBytes(path); } catch (_) { /* only a redraw */ }
        return blob;
      })
      .catch(() => null)                              // not uploaded yet (the other device is offline), or no connection
      .finally(() => gets.delete(path)));
  }
  return gets.get(path);
}
export async function cached(path) { const r = await getRec(path); return !!(r && r.blob); }

// the open pdf.js document for a path (a few are kept, the least used goes first)
export function docOf(path) {
  const hit = docs.get(path);
  if (hit) { hit.used = ++useN; return hit.p; }
  const e = { used: ++useN, p: null };
  e.p = (async () => {
    const blob = await bytesOf(path);
    if (!blob) throw new Error('The PDF is not on this device yet');
    const m = await loadLib();
    const d = await m.getDocument({ data: new Uint8Array(await blob.arrayBuffer()), isEvalSupported: false }).promise;
    stats.opened++;
    return d;
  })();
  docs.set(path, e);
  e.p.catch(() => { if (docs.get(path) === e) docs.delete(path); });
  trimDocs(path);
  return e.p;
}
function keepDoc(path, doc) {
  const e = { used: ++useN, p: Promise.resolve(doc) };
  docs.set(path, e);
  trimDocs(path);
}
function trimDocs(keep) {
  while (docs.size > DOCS) {
    let old = null;
    for (const [k, v] of docs) if (k !== keep && (!old || v.used < old[1].used)) old = [k, v];
    if (!old) return;
    docs.delete(old[0]);
    old[1].p.then((d) => d.destroy(), () => {});
  }
}

// ---------------------------------------------------------------- pw-v7n: the PDF pages' thumbs, kept on this device
// js/pdfview.js makes a page's thumb (a 240 px JPEG) once and keeps it here, so a note scrolled once never renders a thumb
// again, even after a restart. A database of its own (penworks.<mode>.<user id>.thumbs, store `thumbs`), so the PDFs' own
// database is never upgraded for it. A record: { k: pdf_path#page, blob, at (ms, when it was made) }; a PDF's path never
// changes (a new uuid per import), so a thumb never goes stale. At most THUMB_CAP thumbs: the oldest made go first.
const THUMB_CAP = 2000;
let tdbp = Promise.reject(new Error('initPdf has not run'));
tdbp.catch(() => {});
let thumbCap = THUMB_CAP;
const tstats = { thumbReads: 0, thumbHits: 0, thumbPuts: 0, thumbDropped: 0 };
function openThumbDb(name) {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(name, 1);
    r.onupgradeneeded = () => {
      if (!r.result.objectStoreNames.contains('thumbs')) r.result.createObjectStore('thumbs', { keyPath: 'k' }).createIndex('at', 'at');
    };
    r.onsuccess = () => { const db = r.result; db.onversionchange = () => db.close(); resolve(db); };
    r.onerror = () => reject(r.error);
  });
}
function trun(mode, fn) {
  return tdbp.then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(['thumbs'], mode), out = {};
    fn(t.objectStore('thumbs'), out);
    t.oncomplete = () => resolve(out);
    t.onerror = t.onabort = () => reject(t.error);
  }));
}
// the thumb's JPEG for pdf_path#page, or null (none kept, or no store)
export async function thumbGet(k) {
  tstats.thumbReads++;
  try {
    const o = await trun('readonly', (s, out) => { s.get(k).onsuccess = (e) => { out.v = e.target.result || null; }; });
    if (o.v && o.v.blob) { tstats.thumbHits++; return o.v.blob; }
  } catch (_) { /* no store */ }
  return null;
}
// keep a thumb; past the cap the oldest made go (in the same transaction)
export async function thumbPut(k, blob) {
  try {
    await trun('readwrite', (s) => {
      s.put({ k, blob, at: Date.now() });
      s.count().onsuccess = (e) => {
        let over = e.target.result - thumbCap;
        if (over <= 0) return;
        s.index('at').openCursor().onsuccess = (ev) => {
          const c = ev.target.result;
          if (!c || over <= 0) return;
          if (c.value.k !== k) { c.delete(); over--; tstats.thumbDropped++; }
          c.continue();
        };
      };
    });
    tstats.thumbPuts++;
    return true;
  } catch (_) { return false; }
}
// every key kept (pdfview's background fill skips these without reading them)
export async function thumbKeys() {
  try { return new Set((await trun('readonly', (s, out) => { s.getAllKeys().onsuccess = (e) => { out.v = e.target.result || []; }; })).v); }
  catch (_) { return new Set(); }
}
export async function thumbCount() {
  try { return (await trun('readonly', (s, out) => { s.count().onsuccess = (e) => { out.v = e.target.result; }; })).v; }
  catch (_) { return 0; }
}
// the tests' small cap, so the cap is reached with a few pages; no argument = the real one
export function setThumbCap(n) { thumbCap = n > 0 ? n : THUMB_CAP; }

// ---------------------------------------------------------------- the import
const round2 = (v) => Math.round(v * 100) / 100;
const nameOf = (file) => String((file && file.name) || '').replace(/\.pdf$/i, '').trim().slice(0, 120) || 'Untitled';
// one import at a time, in the order they were asked for
export function importPdf(file, target = {}) {
  const job = importing.then(() => doImport(file, target));
  importing = job.catch(() => {});
  return job;
}
async function doImport(file, target) {
  const no = (msg, why) => { if (why) console.warn('PenWorks: a PDF was not opened:', why); cfg.toast(msg, 5000); return null; };
  if (!file || typeof file.size !== 'number') return null;
  if (file.size > MAX_BYTES) return no(TOO_BIG);
  let buf, doc;
  try {
    buf = await file.arrayBuffer();
    const m = await loadLib();
    doc = await m.getDocument({ data: new Uint8Array(buf.slice(0)), isEvalSupported: false }).promise;   // the copy goes to the worker
  } catch (e) { return no(BROKEN, (e && (e.name + ': ' + e.message)) || e); }   // broken, or a password (PasswordException)
  const n = doc.numPages, sizes = [];
  try {
    if (!n) throw new Error('no pages');
    for (let k = 1; k <= n; k++) {
      if (n > 1) cfg.toast(`Opening PDF: ${k} of ${n}`, 4000);
      const pg = await doc.getPage(k), v = pg.getViewport({ scale: 1 });
      sizes.push([round2(v.width), round2(v.height)]);
      pg.cleanup();
    }
  } catch (e) { doc.destroy(); return no(BROKEN, e && e.message); }
  const path = `${cfg.userId}/${crypto.randomUUID()}.pdf`;
  await putRec({ path, blob: new Blob([buf], { type: 'application/pdf' }), up: false, at: new Date().toISOString(), name: file.name || '' });
  keepDoc(path, doc);                                 // the pages about to draw need not read it again
  const specs = sizes.map(([w, h], i) => ({ pdf_path: path, pdf_page: i + 1, pdf_w: w, pdf_h: h,
    orientation: w > h ? 'landscape' : 'portrait', background: 'blank' }));
  const isNew = !target.noteId;
  const noteId = isNew ? cfg.makeNote(target.folderId || null, nameOf(file)) : target.noteId;
  const pageIds = cfg.addPages(noteId, specs, isNew);
  stats.imports++;
  kickUploads();
  return { noteId, path, pages: n, pageIds };
}

// ---------------------------------------------------------------- the upload, in the background
function kickUploads() { if (!upBusy && !upT) pumpUploads(); }
async function pumpUploads() {
  upT = 0;
  if (upBusy || navigator.onLine === false || !cfg.api) return;
  upBusy = true;
  try {
    for (;;) {
      const rec = (await allRecs()).find((r) => r && !r.up && r.blob);
      if (!rec) return;
      try { await cfg.api.putImport(rec.path, rec.blob); }
      catch (e) {
        stats.failures++;
        if (!upTold) { upTold = true; console.warn(`PenWorks: an opened PDF could not be uploaded yet (${(e && e.message) || e}). It is tried again.`); }
        upT = setTimeout(pumpUploads, BACKOFF[Math.min(upTries++, BACKOFF.length - 1)]);
        return;
      }
      upTries = 0; upTold = false; stats.uploads++;
      await putRec({ ...rec, up: true });
    }
  } finally { upBusy = false; }
}

// ---------------------------------------------------------------- U4c: pictures (the + menu's Image)
// A picture's file lives exactly where a PDF's does: this device's copy (the `files` store) at once, then the bucket in the
// background (kickUploads), so a picture placed without wifi works and goes up later. keepImport is that one step;
// bytesOf serves a picture's path like a PDF's (the phone downloads it the first time it draws the page).
export async function keepImport(path, blob, name = '') {
  await putRec({ path, blob, up: false, at: new Date().toISOString(), name });
  kickUploads();
}
export const IMG_BROKEN = 'This picture could not be opened.';
export const IMG_TOO_BIG = 'This picture is too big (over 10 MB).';
const IMG_LONG = 2048;                            // the long side kept: a 4000 px phone photo is 3 x the page's 794 px; 2048 stays crisp to about zoom 2.5
const IMG_MAX = 10485760;                         // 10 MB, after the downscale
// what the bytes are (the first few, not the name or the picker's type): 'png', 'jpeg', 'webp' or ''
async function sniff(file) {
  const b = new Uint8Array(await file.slice(0, 12).arrayBuffer()), at = (k, s) => [...s].every((c, i) => b[k + i] === c.charCodeAt(0));
  if (b[0] === 0x89 && at(1, 'PNG')) return 'png';
  if (b[0] === 0xFF && b[1] === 0xD8 && b[2] === 0xFF) return 'jpeg';
  if (at(0, 'RIFF') && at(8, 'WEBP')) return 'webp';
  return '';
}
// a JPEG's EXIF orientation (1 = upright, as stored; 0 = none found). A turned one is drawn upright and stored again,
// since the PDF export puts a JPEG's pixels in as they are stored
async function jpegTurn(file) {
  const v = new DataView(await file.slice(0, 131072).arrayBuffer());
  let i = 2;
  while (i + 4 <= v.byteLength && v.getUint8(i) === 0xFF) {
    const m = v.getUint8(i + 1), len = v.getUint16(i + 2);
    if (m === 0xE1 && i + 10 <= v.byteLength && v.getUint32(i + 4) === 0x45786966) {   // APP1 "Exif"
      const t = i + 10, le = v.getUint16(t) === 0x4949, u16 = (k) => v.getUint16(k, le), u32 = (k) => v.getUint32(k, le);
      if (t + 8 > v.byteLength) return 0;
      const ifd = t + u32(t + 4), n = ifd + 2 <= v.byteLength ? u16(ifd) : 0;
      for (let k = 0; k < n; k++) { const e = ifd + 2 + k * 12; if (e + 10 > v.byteLength) break; if (u16(e) === 0x0112) return u16(e + 8); }
      return 0;
    }
    if (m === 0xDA) break;                                         // the picture data starts: no EXIF before it
    i += 2 + len;
  }
  return 0;
}
// the one way a picture comes in: decode it (a broken file = ONE toast, nothing lands), keep its long side at 2048 px at
// most (PNG and WebP go out as PNG, alpha kept; JPEG stays JPEG at 0.9; a small PNG or upright JPEG is kept as it came, a
// small WebP becomes PNG: the PDF export cannot embed WebP), keep it on the device (keepImport), then cfg.placeImage puts
// the record on page pageId (js/ink.js placeImage). Returns that record, or null
export async function importImage(file, pageId) {
  const no = (msg, why) => { if (why) console.warn('PenWorks: a picture was not opened:', why); cfg.toast(msg, 5000); return null; };
  if (!file || typeof file.size !== 'number') return null;
  let kind = '', bmp = null;
  try { kind = await sniff(file); bmp = await createImageBitmap(file); }
  catch (e) { return no(IMG_BROKEN, (e && (e.name + ': ' + e.message)) || e); }
  const w0 = bmp.width, h0 = bmp.height;
  if (!(w0 > 0 && h0 > 0)) { bmp.close(); return no(IMG_BROKEN, 'no pixels'); }
  const s = Math.min(1, IMG_LONG / Math.max(w0, h0)), nw = Math.max(1, Math.round(w0 * s)), nh = Math.max(1, Math.round(h0 * s));
  const jpeg = kind === 'jpeg';
  let blob = null;
  try {
    if (s === 1 && (kind === 'png' || (jpeg && (await jpegTurn(file)) <= 1))) blob = new Blob([file], { type: jpeg ? 'image/jpeg' : 'image/png' });
    else {
      const c = document.createElement('canvas');
      c.width = nw; c.height = nh;
      const g = c.getContext('2d');
      g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
      g.drawImage(bmp, 0, 0, nw, nh);
      blob = await new Promise((ok, bad) => c.toBlob((b) => (b ? ok(b) : bad(new Error('the picture could not be drawn'))), jpeg ? 'image/jpeg' : 'image/png', jpeg ? 0.9 : undefined));
      c.width = 0; c.height = 0;
    }
  } catch (e) { return no(IMG_BROKEN, e && e.message); }
  finally { bmp.close(); }
  if (blob.size > IMG_MAX) return no(IMG_TOO_BIG);
  const path = `${cfg.userId}/${crypto.randomUUID()}.${jpeg ? 'jpg' : 'png'}`;
  await keepImport(path, blob, (file && file.name) || '');
  stats.pictures++;
  return cfg.placeImage ? cfg.placeImage(pageId, { path, nw, nh, blob }) : null;
}

// ---------------------------------------------------------------- U4b: a PDF shared to PenWorks
// sw.js keeps the shared file in IndexedDB penworks.share (store `files`, key `pending` = { blob, name, at }) and sends
// the app to ./?share=1; app.js asks for it once she is logged in, imports it with importPdf like any other, and drops
// it when she has answered the sheet. Not per user: the file waits before anyone is logged in.
const SHARE_DB = 'penworks.share';
async function shareRun(mode, fn) {
  const db = await openDb(SHARE_DB);
  try {
    return await new Promise((resolve, reject) => {
      const t = db.transaction(['files'], mode), out = {};
      fn(t.objectStore('files'), out);
      t.oncomplete = () => resolve(out);
      t.onerror = t.onabort = () => reject(t.error);
    });
  } finally { db.close(); }
}
// the file waiting, as a File named as it was shared; null when there is none
export async function sharedFile() {
  try {
    const v = (await shareRun('readonly', (s, out) => { s.get('pending').onsuccess = (e) => { out.v = e.target.result || null; }; })).v;
    if (!v || !v.blob) return null;
    return new File([v.blob], v.name || 'Shared.pdf', { type: 'application/pdf' });
  } catch (e) { console.warn('PenWorks: the shared PDF could not be read', e); return null; }
}
// drop it; olderThan (ms): only a file waiting longer than that (a share she never answered)
export async function dropShared(olderThan = 0) {
  try {
    await shareRun('readwrite', (s) => {
      s.get('pending').onsuccess = (e) => {
        const v = e.target.result;
        if (v && (!olderThan || !(Date.now() - Date.parse(v.at) < olderThan))) s.delete('pending');
      };
    });
  } catch (_) { /* nothing to drop */ }
}

// ---------------------------------------------------------------- for the tests (window.__pw.pdf)
export async function uploadsPending() { return (await allRecs()).filter((r) => r && !r.up).length; }
export function pdfStats() { return { ...stats, ...tstats, docs: docs.size, uploading: upBusy, retry: !!upT }; }
