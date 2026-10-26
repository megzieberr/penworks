// PenWorks PDF in (U4a): the + button opens a PDF as note pages, her ink on top (js/pdfview.js draws them).
// importPdf(file, target) is the one way in: target = { folderId } makes a NEW note named after the file (the name
// without .pdf) in that folder (null = Loose), target = { noteId } puts the PDF's pages at the END of that note. A
// share-target handler (U4b) can call it the same way with the File it is handed.
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
  onBytes: () => {},    // (path) the bytes of that PDF are on this device now (the pages can draw)
};
let dbp = Promise.reject(new Error('initPdf has not run'));
dbp.catch(() => {});
const mem = new Map();                            // path -> record, when the device would not keep it (no IndexedDB)
const gets = new Map();                           // path -> a download on its way
const docs = new Map();                           // path -> { p: Promise<PDFDocumentProxy>, used }
let lib = null, useN = 0, importing = Promise.resolve();
let upBusy = false, upT = 0, upTries = 0, upTold = false;
const stats = { imports: 0, uploads: 0, downloads: 0, failures: 0, opened: 0 };

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
  const name = `penworks.${o.mode}.${o.userId}.pdf`;
  let wipe = Promise.resolve();
  if (o.mode === 'local') {
    try { if (localStorage.getItem(LOCAL_MARK) !== name) { wipe = dropDb(name); localStorage.setItem(LOCAL_MARK, name); } }
    catch (_) { /* ignore */ }
  }
  dbp = wipe.then(() => openDb(name));
  dbp.catch((e) => console.warn('PenWorks: no device copy for opened PDFs', e));
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

// ---------------------------------------------------------------- for the tests (window.__pw.pdf)
export async function uploadsPending() { return (await allRecs()).filter((r) => r && !r.up).length; }
export function pdfStats() { return { ...stats, docs: docs.size, uploading: upBusy, retry: !!upT }; }
