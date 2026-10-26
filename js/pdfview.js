// PenWorks PDF pages on screen (U4a). A page made from a PDF page (pages.pdf_path) has a .pdfLayer in its sheet
// (js/page.js): above the plain paper, under the ink layer, so no eraser, select, restyle, page Erase or undo can reach
// it (they only ever touch ink records). This file puts the PDF page's picture in that layer.
//
// LAZY: only the pages on screen and the one each side of them have a canvas; a page further away gives its canvas back
// (her tablet has a 40-page paper in mind). A canvas is rendered at the screen's resolution for the zoom (zoom x device
// pixels, at most CAP_PX pixels), and only once the stack has been still for QUIET ms (page.js sinceMove): a pan, a
// glide or a pinch never waits for a render, the pinch just scales the old bitmap with the stack. When the zoom has
// settled a page that is now too soft (or wastefully big) renders again, into a fresh canvas that replaces the old one
// when it is done. One render at a time, the current page first. In dark mode the PDF shows as it is (the paper is
// white in both modes).
// Also: thumbInto (the page list's thumbs and the folder grid's note card: a small render, cached as a blob: URL per
// PDF page) and paint (the page picture of U3b and Share draw the PDF under the ink).

import { docOf } from './pdfin.js';
import { pageSize, sinceMove } from './page.js';

const CAP_PX = 12e6;        // a page canvas holds at most this many pixels (about 46 MB of memory)
const QUIET = 180;          // ms of a still stack before a render starts
const RETRY = 3000;         // ms before a page whose PDF could not be had (no bytes yet) is tried again
const THUMB_W = 240;        // px across a thumb's render (the page list's thumbs are about 130 px across)
const cfg = { page: () => null };
const R = new Map();        // page id -> { id, el, layer, idx, canvas, s, failAt }
let order = [];             // the records of the PDF pages in the stack, in stack order
let range = [-1, -1], zoom = 1, timer = 0, working = false, again = false;   // again: asked for while a render ran
const stats = { renders: 0, freed: 0, peak: 0, thumbs: 0, fails: 0, pixels: 0 };

export function initView(o) {
  Object.assign(cfg, o);
  addEventListener('online', () => arm(0));
}

// page.js has (re)built the stack: these are the sheets now. A page still there keeps its bitmap (moved into its new layer).
export function attach(sheets) {
  const here = new Set();
  order = [];
  for (const el of sheets) {
    if (!el.dataset.pdf) continue;
    const id = el.dataset.id, layer = el.querySelector(':scope > .pdfLayer');
    here.add(id);
    let r = R.get(id);
    if (!r) { r = { id, canvas: null, s: 0, failAt: 0 }; R.set(id, r); }
    if (r.canvas && r.layer !== layer) {
      const p = cfg.page(id), sz = p && pageSize(p);
      if (sz && r.w === sz.w && r.h === sz.h) layer.append(r.canvas); else free(r);
    }
    r.el = el; r.layer = layer; r.idx = +el.dataset.index - 1;
    order.push(r);
  }
  for (const [id, r] of R) if (!here.has(id)) { free(r); R.delete(id); }
  arm(0);
}

// page.js: the pages on screen (first, last; -1 when none) and the zoom changed
export function view(first, last, z) {
  range = [first, last]; zoom = z;
  if (order.length) arm(QUIET);
}

// a page's PDF bytes came in (the phone downloaded them): draw what is waiting
export function bytesArrived() { R.forEach((r) => { r.failAt = 0; }); arm(0); }

function arm(ms) { clearTimeout(timer); timer = setTimeout(work, ms); }
function free(r) {
  if (!r.canvas) return;
  r.canvas.width = 0; r.canvas.height = 0; r.canvas.remove();
  r.canvas = null; r.s = 0; stats.freed++;
}
function live() { let n = 0; R.forEach((r) => { if (r.canvas) n++; }); return n; }
// the resolution a page wants now: zoom x device pixels, kept under CAP_PX
function target(w, h) {
  const s = zoom * (devicePixelRatio || 1);
  return Math.max(0.2, Math.min(s, Math.sqrt(CAP_PX / (w * h))));
}

async function work() {
  timer = 0;
  if (working) { again = true; return; }
  const still = sinceMove();
  if (still < QUIET) { arm(QUIET - still + 10); return; }
  working = true;
  try {
    const [a, b] = range, lo = a - 1, hi = b + 1, cur = (a + b) / 2;
    for (const r of order) if (r.canvas && (a < 0 || r.idx < lo || r.idx > hi)) free(r);   // far away: the memory goes back
    if (a < 0) return;
    const want = order.filter((r) => r.idx >= lo && r.idx <= hi).sort((x, y) => Math.abs(x.idx - cur) - Math.abs(y.idx - cur));
    let later = 0;
    for (const r of want) {
      const p = cfg.page(r.id);
      if (!p || !p.pdf_path || !r.layer || !r.layer.isConnected) continue;
      const { w, h } = pageSize(p), t = target(w, h);
      if (r.canvas && r.s >= t / 1.2 && r.s <= t * 2.5) continue;          // sharp enough, and not wastefully big
      if (r.failAt && performance.now() - r.failAt < RETRY) { later = RETRY; continue; }
      try { await draw(r, p, w, h, t); r.failAt = 0; }
      catch (e) { r.failAt = performance.now(); stats.fails++; later = RETRY; }
      if (sinceMove() < QUIET) { later = QUIET; break; }                   // she moved meanwhile: look again when still
    }
    if (later) arm(later);
  } finally { working = false; if (again) { again = false; arm(0); } }
}

// one PDF page into a fresh canvas the size of the page at resolution s; it replaces the old one when it is done
async function draw(r, p, w, h, s) {
  const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
  const W = Math.max(1, Math.round(w * s)), H = Math.max(1, Math.round(h * s));
  const c = document.createElement('canvas');
  c.width = W; c.height = H; c.className = 'pdfCanvas';
  const g = c.getContext('2d', { alpha: false });
  await renderInto(pg, g, W, H, true);
  pg.cleanup();
  if (!r.layer || !r.layer.isConnected || !cfg.page(r.id)) { c.width = 0; c.height = 0; return; }
  if (r.canvas) { const old = r.canvas; old.replaceWith(c); old.width = 0; old.height = 0; } else r.layer.append(c);
  r.canvas = c; r.s = s; r.w = w; r.h = h;
  stats.renders++; stats.peak = Math.max(stats.peak, live());
}
// the PDF page fills W x H exactly (the page's own aspect; a rounding px is stretched, never a bar)
async function renderInto(pg, g, W, H, white) {
  const v1 = pg.getViewport({ scale: 1 }), vp = pg.getViewport({ scale: W / v1.width });
  const sy = H / vp.height;
  if (white) { g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, W, H); }
  await pg.render({ canvasContext: g, viewport: vp, transform: sy !== 1 ? [1, 0, 0, sy, 0, 0] : undefined }).promise;
}

// ---------------------------------------------------------------- pictures of a page elsewhere
// the PDF page drawn into a 2D context at 0, 0, W x H (the page picture and Share, js/app.js renderPage). Throws when
// the PDF is not on this device and cannot be downloaded now: the picture waits (snap.js tries again).
export async function paint(g, p, W, H) {
  const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
  g.save();
  try { await renderInto(pg, g, W, H, false); } finally { g.restore(); pg.cleanup(); }
}

// small renders, one blob: URL per PDF page, made one at a time
const thumbs = new Map();   // pdf_path#page -> Promise<url|null>
let thumbChain = Promise.resolve();
function thumbUrl(p) {
  const key = p.pdf_path + '#' + p.pdf_page;
  if (!thumbs.has(key)) {
    const job = thumbChain.then(async () => {
      const { w, h } = pageSize(p), W = THUMB_W, H = Math.max(1, Math.round(THUMB_W * h / w));
      const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
      const c = document.createElement('canvas'); c.width = W; c.height = H;
      await renderInto(pg, c.getContext('2d', { alpha: false }), W, H, true);
      pg.cleanup();
      const blob = await new Promise((ok) => c.toBlob(ok, 'image/jpeg', 0.85));
      c.width = 0; c.height = 0;
      if (!blob) throw new Error('no thumb');
      stats.thumbs++;
      return URL.createObjectURL(blob);
    });
    thumbChain = job.catch(() => {});
    const out = job.catch(() => { thumbs.delete(key); return null; });   // not there yet: asked for again next time
    thumbs.set(key, out);
  }
  return thumbs.get(key);
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
  let px = 0; R.forEach((r) => { if (r.canvas) px += r.canvas.width * r.canvas.height; });
  return { ...stats, canvases: live(), pixels: px, pdfPages: order.length, range: [...range], thumbsCached: thumbs.size };
}
