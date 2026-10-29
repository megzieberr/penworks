// PenWorks PDF pages on screen (U4a). A page made from a PDF page (pages.pdf_path) has a .pdfLayer in its sheet
// (js/page.js): above the plain paper, under the ink layer, so no eraser, select, restyle, page Erase or undo can reach
// it (they only ever touch ink records). This file puts the PDF page's picture in that layer.
//
// AT ONCE (pw-v6d, her "a bit of a lag when loading the pdf pages"): a page coming near the screen (on it, or KEEP pages
// either side) that has no canvas gets its small thumb first (the page list's 240 px JPEG, scaled up to the page), with
// no wait for the stack to be still. The sharp canvas replaces the thumb when it lands. A sharp render also leaves its
// page's thumb behind (a scaled-down copy, no second pdf.js render), so a page seen once shows at once from then on, in
// the page list too.
// pw-v7n (her "hakkerig", 29 Oct: one-finger scrolling through a PDF note felt like fighting it; plain ink notes were
// fine): NOTHING FROM PDF.JS RUNS WHILE THE STACK MOVES (a pan, a glide, a pinch). Measured before: the thumbs made
// mid-pan (a pdf.js render and a GPU read-back each) were in every slow frame of a first scroll. Now a thumb not made yet
// is made only once the stack has been still for QUIET, and a render already going pauses between its slices while the
// stack moves (pdf.js asks onContinue before each slice). A near page with no thumb shows its plain white paper meanwhile.
// THUMBS ARE KEPT ON THE DEVICE (js/pdfin.js thumbGet / thumbPut, IndexedDB, at most 2000): read from there while moving
// too, so a note scrolled once never renders a thumb again, even after a restart. After a note with PDF pages opens (or
// its PDF arrives) the BACKGROUND FILL makes the thumbs of all its pages, lowest page first, one at a time, only while the
// stack is still, nothing else renders and the app is visible, so a first scroll through a new note is smooth after a
// few seconds.
// SHARP: a canvas is rendered at the screen's resolution for the zoom (zoom x device pixels, at most CAP_PX pixels), and
// only once the stack has been still for QUIET ms (page.js sinceMove): a pan, a glide or a pinch never waits for a
// render, the pinch just scales the old bitmap with the stack. A jump or a note opening is not a move: it renders at
// once. The pages on screen and the one each side render, the current page first; then, while she stays still, the next
// page the way she last moved (render ahead), so a page-flick lands on a sharp page. One render at a time; a render ahead
// is cancelled the moment the view changes. When the zoom has settled a page that is now too soft (or wastefully big)
// renders again, into a fresh canvas that replaces the old one when it is done. In dark mode the PDF shows as it is (the
// paper is white in both modes).
// KEPT: the pages on screen and KEEP pages either side keep their canvas; beyond that the canvases seen last stay while all
// of them together hold under BUDGET_PX pixels, the least recently seen go first (her tablet has a 40-page paper in mind).
// Also: thumbInto (the page list's thumbs and the folder grid's note card: a small render, cached as a blob: URL per
// PDF page) and paint (the page picture of U3b and Share draw the PDF under the ink).

import { docOf, thumbGet, thumbPut, thumbKeys } from './pdfin.js';
import { pageSize, sinceMove } from './page.js';

const CAP_PX = 12e6;        // a page canvas holds at most this many pixels (about 46 MB of memory)
const QUIET = 180;          // ms of a still stack before a sharp render starts
const RETRY = 3000;         // ms before a page whose PDF could not be had (no bytes yet) is tried again
const THUMB_W = 240;        // px across a thumb's render (the page list's thumbs are about 130 px across)
const KEEP = 2;             // pages either side of the screen that keep their canvas and get their thumb at once
// pw-v6d: canvases beyond KEEP stay while all canvases hold under this many pixels (4 bytes each: 240 MB). A scanned A4
// page on her Tab S11 Ultra (zoom 1, about 2.4 device px) is about 5 Mpx, so this keeps about 12 pages; her 40-page
// scan would need about 200 Mpx (800 MB) to keep every page, well past what Android Chrome gives one tab.
const BUDGET_PX = 60e6;
const cfg = { page: () => null };
const R = new Map();        // page id -> { id, el, layer, idx, canvas, s, failAt, used, ph }
let order = [];             // the records of the PDF pages in the stack, in stack order
let range = [-1, -1], zoom = 1, timer = 0, working = false, again = false;   // again: asked for while a render ran
let dir = 1, useN = 0, job = null, placeT = 0, budget = BUDGET_PX;           // dir: 1 = she last moved down the pages, -1 up
const stats = { renders: 0, freed: 0, peak: 0, thumbs: 0, fails: 0, pixels: 0, placeholders: 0, ahead: 0, cancelled: 0, seeded: 0,
                thumbRenders: 0, held: 0, fromStore: 0, stored: 0, filled: 0 };   // pw-v7n: pdf.js thumb renders, slices held, the device's thumbs
const events = [];          // the last few things the layer did, for the tests: 'ph 3', 'sharp 3', 'ahead 5', 'free 1'
let evN = 0;                // how many there have been in all (the tests take the ones since a moment)
function note(s) { evN++; events.push(s); if (events.length > 200) events.shift(); }

export function initView(o) {
  Object.assign(cfg, o);
  addEventListener('online', () => arm(0));
}

// page.js has (re)built the stack: these are the sheets now. A page still there keeps its bitmap (moved into its new layer).
export function attach(sheets) {
  const here = new Set();
  let known = 0;
  order = [];
  for (const el of sheets) {
    if (!el.dataset.pdf) continue;
    const id = el.dataset.id, layer = el.querySelector(':scope > .pdfLayer');
    here.add(id);
    let r = R.get(id);
    if (r) known++;
    else { r = { id, canvas: null, s: 0, failAt: 0, used: 0, ph: null }; R.set(id, r); }
    if (r.layer !== layer) {
      const p = cfg.page(id), sz = p && pageSize(p), same = sz && r.w === sz.w && r.h === sz.h;
      if (r.canvas) { if (same) layer.append(r.canvas); else free(r); }
      if (r.ph instanceof Element) layer.prepend(r.ph); else r.ph = null;
    }
    r.el = el; r.layer = layer; r.idx = +el.dataset.index - 1;
    order.push(r);
  }
  for (const [id, r] of R) if (!here.has(id)) { free(r); unplace(r); R.delete(id); }
  if (!known) dir = 1;                                                   // another note: it reads down from the top
  place();
  arm(0);
  startFill();
}

// page.js: the pages on screen (first, last; -1 when none) and the zoom changed (told inside its frame: only take note)
export function view(first, last, z) {
  const was = (range[0] + range[1]) / 2, now = (first + last) / 2, pages = first !== range[0] || last !== range[1];
  if (first >= 0 && range[0] >= 0 && now !== was) dir = now > was ? 1 : -1;
  range = [first, last]; zoom = z;
  if (!order.length) return;
  for (const r of order) if (r.idx >= first && r.idx <= last) r.used = ++useN;
  if (job && job.ahead && job.task) job.task.cancel();                   // she moved: the page ahead may not be ahead now
  if (pages) place();                                                    // pw-v7n: a pinch changes the zoom every frame, not the pages
  arm(Math.max(0, QUIET - sinceMove()));                                  // still (a jump, a note opening): at once
}

// a page's PDF bytes came in (the phone downloaded them): draw what is waiting
export function bytesArrived() { R.forEach((r) => { r.failAt = 0; }); place(); arm(0); startFill(); }

function arm(ms) { clearTimeout(timer); timer = setTimeout(work, ms); }
function free(r) {
  if (!r.canvas) return;
  r.canvas.width = 0; r.canvas.height = 0; r.canvas.remove();
  r.canvas = null; r.s = 0; stats.freed++; note('free ' + (r.idx + 1));
}
function live() { let n = 0; R.forEach((r) => { if (r.canvas) n++; }); return n; }
function pixels() { let n = 0; R.forEach((r) => { if (r.canvas) n += r.canvas.width * r.canvas.height; }); return n; }
// the resolution a page wants now: zoom x device pixels, kept under CAP_PX
function target(w, h) {
  const s = zoom * (devicePixelRatio || 1);
  return Math.max(0.2, Math.min(s, Math.sqrt(CAP_PX / (w * h))));
}
// canvases outside the kept pages go back, least recently seen first, until all of them fit the budget
function trim() {
  const [a, b] = range;
  if (a < 0) { for (const r of order) free(r); return; }
  const out = order.filter((r) => r.canvas && (r.idx < a - KEEP || r.idx > b + KEEP)).sort((x, y) => x.used - y.used);
  let px = pixels();
  for (const r of out) { if (px <= budget) break; px -= r.canvas.width * r.canvas.height; free(r); }
}

// ---------------------------------------------------------------- the thumb first (no wait for a still stack)
function place() { if (!placeT) placeT = setTimeout(placeAll, 0); }      // after page.js's frame, never inside it
function placeAll() {
  placeT = 0;
  const [a, b] = range, cur = (a + b) / 2;
  if (a < 0) return;
  const want = order.filter((r) => r.idx >= a - KEEP && r.idx <= b + KEEP && !r.canvas && !r.ph)
    .sort((x, y) => Math.abs(x.idx - cur) - Math.abs(y.idx - cur));
  for (const r of want) placeOne(r, r.idx >= a && r.idx <= b);
}
function placeOne(r, onScreen) {
  const p = cfg.page(r.id);
  if (!p || !p.pdf_path || !r.layer) return;
  // pw-v7n: a thumb already made (in memory, or kept on the device) goes in at once, also while the stack moves. One not
  // made yet is made once the stack is still (pumpThumbs), and only for the KEEP pages off the screen: a page on screen
  // gets its sharp render then instead, as on a scan a thumb costs about what the sharp render does (measured, round C).
  const tok = {};
  r.ph = tok;
  tok.p = thumbUrl(p, r, !onScreen).then(async (url) => {
    if (r.ph !== tok) return;
    if (!url || r.canvas || !r.layer || !r.layer.isConnected) { r.ph = null; return; }
    const img = new Image();
    img.className = 'pdfPh'; img.alt = ''; img.draggable = false; img.src = url;
    try { await img.decode(); } catch (_) { if (r.ph === tok) r.ph = null; return; }
    if (r.ph !== tok) return;
    if (r.canvas || !r.layer || !r.layer.isConnected) { r.ph = null; return; }
    r.layer.prepend(img); r.ph = img;
    stats.placeholders++; note('ph ' + (r.idx + 1));
  });
}
function unplace(r) { if (r.ph instanceof Element) r.ph.remove(); r.ph = null; }

// ---------------------------------------------------------------- the sharp renders
async function work() {
  timer = 0;
  if (working) { again = true; return; }
  const still = sinceMove();
  if (still < QUIET) { arm(QUIET - still + 10); return; }
  working = true;
  try {
    trim();
    const [a, b] = range, cur = (a + b) / 2;
    if (a < 0) return;
    const want = order.filter((r) => r.idx >= a - 1 && r.idx <= b + 1).sort((x, y) => Math.abs(x.idx - cur) - Math.abs(y.idx - cur));
    const next = order.find((r) => r.idx === (dir > 0 ? b + 2 : a - 2));          // the page ahead, last and lowest
    if (next) want.push(next);
    let later = 0;
    for (const r of want) {
      const p = cfg.page(r.id);
      if (!p || !p.pdf_path || !r.layer || !r.layer.isConnected) continue;
      const { w, h } = pageSize(p), t = target(w, h), ahead = r === next;
      if (r.canvas && r.s >= t / 1.2 && r.s <= t * 2.5) continue;          // sharp enough, and not wastefully big
      if (r.failAt && performance.now() - r.failAt < RETRY) { later = RETRY; continue; }
      if (ahead && sinceMove() < QUIET) { later = QUIET; break; }
      try { await draw(r, p, w, h, t, ahead); r.failAt = 0; }
      catch (e) {
        if (e === MOVED) { later = QUIET; break; }
        if (e && e.name === 'RenderingCancelledException') { stats.cancelled++; later = QUIET; break; }
        r.failAt = performance.now(); stats.fails++; later = RETRY;
      }
      if (sinceMove() < QUIET) { later = QUIET; break; }                   // she moved meanwhile: look again when still
    }
    if (later) arm(later);
  } finally { working = false; job = null; if (again) { again = false; arm(0); } }
}

// one PDF page into a fresh canvas the size of the page at resolution s; it replaces the old one (or the thumb) when done
async function draw(r, p, w, h, s, ahead) {
  const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
  if (sinceMove() < QUIET) { pg.cleanup(); throw MOVED; }                 // pw-v7n: she moved while the page was fetched
  const W = Math.max(1, Math.round(w * s)), H = Math.max(1, Math.round(h * s));
  const c = document.createElement('canvas');
  c.width = W; c.height = H; c.className = 'pdfCanvas';
  const g = c.getContext('2d', { alpha: false });
  job = { r, ahead, task: null };
  try { await renderInto(pg, g, W, H, true, (task) => { job.task = task; holdWhileMoving(task); }); }
  catch (e) { c.width = 0; c.height = 0; throw e; }
  finally { pg.cleanup(); }
  if (!r.layer || !r.layer.isConnected || !cfg.page(r.id)) { c.width = 0; c.height = 0; return; }
  if (r.canvas) { const old = r.canvas; old.replaceWith(c); old.width = 0; old.height = 0; } else r.layer.append(c);
  unplace(r);
  r.canvas = c; r.s = s; r.w = w; r.h = h; r.used = ++useN;
  seedThumb(p, c);
  stats.renders++; if (ahead) stats.ahead++;
  note((ahead ? 'ahead ' : 'sharp ') + (r.idx + 1));
  trim();
  stats.peak = Math.max(stats.peak, live());
}
// the PDF page fills W x H exactly (the page's own aspect; a rounding px is stretched, never a bar)
async function renderInto(pg, g, W, H, white, hold) {
  const v1 = pg.getViewport({ scale: 1 }), vp = pg.getViewport({ scale: W / v1.width });
  const sy = H / vp.height;
  if (white) { g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, W, H); }
  const task = pg.render({ canvasContext: g, viewport: vp, transform: sy !== 1 ? [1, 0, 0, sy, 0, 0] : undefined });
  if (hold) hold(task);
  await task.promise;
}
// pw-v7n: pdf.js draws a page in slices (about 15 ms each, one per animation frame) and asks onContinue before each one:
// while the stack moves (a pan, a glide, a pinch) the next slice waits until it has been still for QUIET
function holdWhileMoving(task) {
  task.onContinue = (go) => {
    const s = sinceMove();
    if (s >= QUIET) { go(); return; }
    stats.held++;
    setTimeout(() => task.onContinue(go), QUIET - s + 5);
  };
}
const MOVED = new Error('the stack moved');   // pw-v7n: a sharp render not started, as she moved (work() looks again when still)
// resolves once the stack has been still for QUIET (a jump or a note opening is not a move)
function stillFor() {
  return new Promise((ok) => { const look = () => { const s = sinceMove(); if (s >= QUIET) ok(); else setTimeout(look, QUIET - s + 5); }; look(); });
}

// ---------------------------------------------------------------- pictures of a page elsewhere
// the PDF page drawn into a 2D context at 0, 0, W x H (the page picture and Share, js/app.js renderPage). Throws when
// the PDF is not on this device and cannot be downloaded now: the picture waits (snap.js tries again).
export async function paint(g, p, W, H) {
  const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
  // pw-v7n: the page pictures (js/snap.js, in the background) draw no pdf.js slice while the stack moves either (measured:
  // after an import, a page picture's render started and ran inside the first pan through the new note)
  while (sinceMove() < QUIET) await stillFor();
  g.save();
  try { await renderInto(pg, g, W, H, false, holdWhileMoving); } finally { g.restore(); pg.cleanup(); }
}

// small renders, one blob: URL per PDF page, made one at a time. The desk's asks go first (nearest the screen first);
// one for a page the desk has scrolled away from, that nothing else asked for, is dropped (asked for again when needed)
// pw-v7n: a thumb is looked for on the device first (js/pdfin.js thumbGet); only a thumb not kept there is rendered, and
// only once the stack is still; every thumb made is kept there (thumbPut)
const thumbs = new Map();   // pdf_path#page -> { key, p (Promise<url|null>), ok, page, recs (desk records), list, run }
const thumbQ = [];
let thumbBusy = false, thumbDrawing = false;
let kept = null, keptP = null;                // pw-v7n: the keys of the thumbs kept on the device (loaded once, then kept up to date)
const keyOf = (p) => p.pdf_path + '#' + p.pdf_page;
const thumbH = (p) => { const { w, h } = pageSize(p); return Math.max(1, Math.round(THUMB_W * h / w)); };
function keptKeys() { return (keptP ||= thumbKeys().then((s) => { kept = s; return s; })); }
// render false: from the device or not at all (the desk's pages on screen: their sharp render comes instead)
function thumbUrl(p, rec, render = true) {
  const key = keyOf(p);
  let e = thumbs.get(key);
  if (!e) {
    e = { key, page: p, recs: new Set(), list: false, run: false };
    e.p = new Promise((ok) => { e.ok = ok; });
    thumbs.set(key, e);
    fromDevice(e, render);
  }
  if (rec) e.recs.add(rec); else e.list = true;                           // who asked, before the queue looks at it
  return e.p;
}
async function fromDevice(e, render) {
  const blob = !kept || kept.has(e.key) ? await thumbGet(e.key) : null;   // a key not kept: no read at all
  if (thumbs.get(e.key) !== e) return;
  if (blob) { stats.fromStore++; e.run = true; e.ok(URL.createObjectURL(blob)); return; }
  if (!render && !e.list) { thumbs.delete(e.key); e.ok(null); return; }
  thumbQ.push(e);
  pumpThumbs();
}
function keep(key, blob) {
  if (kept) kept.add(key);
  stats.stored++;
  thumbPut(key, blob);
}
function nextThumb() {
  const [a, b] = range, cur = (a + b) / 2, near = (r) => a >= 0 && r.idx >= a - KEEP && r.idx <= b + KEEP && R.get(r.id) === r;
  let best = -1, bd = Infinity;
  for (let i = thumbQ.length - 1; i >= 0; i--) {
    const e = thumbQ[i], recs = [...e.recs].filter(near);
    if (!recs.length && !e.list) {                                         // the desk has moved on and nothing else wants it
      thumbQ.splice(i, 1); thumbs.delete(e.key); e.ok(null); if (best > i) best--; continue;
    }
    const d = recs.length ? Math.min(...recs.map((r) => Math.abs(r.idx - cur))) : Infinity;
    if (d <= bd) { bd = d; best = i; }
  }
  if (best < 0) return null;
  if (bd === Infinity) best = 0;                                           // only the page list's: in the order it asked
  return thumbQ.splice(best, 1)[0];
}
async function pumpThumbs() {
  if (thumbBusy) return;
  thumbBusy = true;
  try {
    while (thumbQ.length) {
      await stillFor();                                                    // pw-v7n: never while the stack moves
      const e = nextThumb();
      if (!e) break;
      e.run = true;
      let url = null;
      try { const blob = await makeThumb(e.page); if (blob) { keep(e.key, blob); url = URL.createObjectURL(blob); } } catch (_) { url = null; }
      if (!url) thumbs.delete(e.key);                                      // not there yet: asked for again next time
      e.ok(url);
    }
  } finally { thumbBusy = false; }
}
// a thumb's JPEG, rendered by pdf.js (held while the stack moves). pw-v7n: its canvas lives in memory (willReadFrequently),
// so the JPEG is read without waiting on the GPU (that wait was 15 to 20 ms a thumb, measured)
async function makeThumb(p) {
  const W = THUMB_W, H = thumbH(p);
  const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
  while (sinceMove() < QUIET) await stillFor();                           // she moved while the page was fetched: after
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  thumbDrawing = true;
  try { await renderInto(pg, c.getContext('2d', { alpha: false, willReadFrequently: true }), W, H, true, holdWhileMoving); }
  finally { pg.cleanup(); thumbDrawing = false; }
  stats.thumbRenders++;
  return jpeg(c);
}
async function jpeg(c) {
  const blob = await new Promise((ok) => c.toBlob(ok, 'image/jpeg', 0.85));
  c.width = 0; c.height = 0;
  if (blob) stats.thumbs++;
  return blob || null;
}
// a sharp canvas just landed: its page's thumb is a scaled-down copy of it (when there is none yet)
function seedThumb(p, src) {
  const key = keyOf(p);
  if (thumbs.has(key)) return;
  const W = THUMB_W, H = thumbH(p), c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d', { alpha: false });
  g.imageSmoothingQuality = 'high';
  g.drawImage(src, 0, 0, W, H);
  const e = { key, page: p, recs: new Set(), list: false, run: true };
  e.p = jpeg(c).then((blob) => {
    if (!blob) { thumbs.delete(key); return null; }
    stats.seeded++;
    if (!kept || !kept.has(key)) keep(key, blob);                          // pw-v7n: kept on the device as well
    return URL.createObjectURL(blob);
  }, () => { thumbs.delete(key); return null; });
  thumbs.set(key, e);
}

// ---------------------------------------------------------------- pw-v7n: the background fill
// after a note with PDF pages opens (attach) or its PDF arrives (bytesArrived): the thumbs of all its pages, lowest page
// first, one at a time, kept on the device (not in memory: the desk reads them from there when it needs them). Only while
// the stack is still, no sharp render or desk thumb is going and the app is visible; a thumb under way pauses between
// its slices when she moves. A page whose PDF cannot be had now stops the fill (bytesArrived starts it again).
let fillGen = 0, filling = false;
const FILL_GAP = 40;          // ms between two thumbs of the fill, so the main thread breathes
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));
const idle = () => sinceMove() >= QUIET && !working && !thumbBusy && !thumbDrawing && document.visibilityState === 'visible';
function startFill() { fillGen++; if (!filling) fill(); }
function fillNext() {
  for (const r of order) {
    const p = cfg.page(r.id);
    if (p && p.pdf_path && !kept.has(keyOf(p)) && !thumbs.has(keyOf(p))) return p;
  }
  return null;
}
async function fill() {
  filling = true;
  try {
    await keptKeys();
    for (let gen = fillGen; ;) {
      while (!idle()) await sleep(100);
      if (gen !== fillGen) gen = fillGen;                                 // another note (or its PDF arrived): from its top
      const p = fillNext();
      if (!p) break;
      let blob = null;
      try { blob = await makeThumb(p); } catch (_) { break; }               // the PDF is not on this device yet
      if (!blob) break;
      if (!kept.has(keyOf(p))) { keep(keyOf(p), blob); stats.filled++; }
      await sleep(FILL_GAP);
    }
  } finally { filling = false; }
}
function fillLeft() {
  if (!kept) return null;
  const left = new Set();
  for (const r of order) { const p = cfg.page(r.id); if (p && p.pdf_path && !kept.has(keyOf(p))) left.add(keyOf(p)); }
  return left.size;
}
// a thumb's .paper (the page list) or a note card's .paper: the PDF page under its ink
export function thumbInto(paperEl, p) {
  if (!p || !p.pdf_path || paperEl.querySelector(':scope > img.pdfThumb')) return;
  const img = document.createElement('img');
  img.className = 'pdfThumb'; img.alt = ''; img.draggable = false;
  paperEl.prepend(img);
  thumbUrl(p).then((url) => { if (url) img.src = url; else img.remove(); });
}

// ---------------------------------------------------------------- for the tests (window.__pw.pdf)
export function viewStats() {
  let ph = 0; R.forEach((r) => { if (r.ph instanceof Element) ph++; });
  return { ...stats, canvases: live(), pixels: pixels(), pdfPages: order.length, range: [...range], thumbsCached: thumbs.size,
           placeholdersLive: ph, keep: KEEP, budget, dir, events: [...events], evN,
           filling, fillLeft: fillLeft(), kept: kept ? kept.size : null };
}
// the tests' small budget, so the 40-page fixture (under 1 Mpx a page) reaches it; no argument = the real one
export function setBudget(px) { budget = px > 0 ? px : BUDGET_PX; trim(); }
