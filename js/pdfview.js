// PenWorks PDF pages on screen (U4a). A page made from a PDF page (pages.pdf_path) has a .pdfLayer in its sheet
// (js/page.js): above the plain paper, under the ink layer, so no eraser, select, restyle, page Erase or undo can reach
// it (they only ever touch ink records). This file puts the PDF page's picture in that layer.
//
// AT ONCE (pw-v6d, her "a bit of a lag when loading the pdf pages"): a page coming near the screen (on it, or KEEP pages
// either side) that has no canvas gets its small thumb first (the page list's 240 px JPEG, scaled up to the page), with
// no wait for the stack to be still. A thumb not made yet is made then only while the stack moves (the sharp render is
// held back meanwhile); on a still stack (a jump, a note opening) the sharp render starts at once instead, as on a scan a
// thumb costs about what the sharp render does. The sharp canvas replaces the thumb when it lands. A sharp render also
// leaves its page's thumb behind (a scaled-down copy, no second pdf.js render), so a page seen once shows at once from
// then on, in the page list too.
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

import { docOf } from './pdfin.js';
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
const stats = { renders: 0, freed: 0, peak: 0, thumbs: 0, fails: 0, pixels: 0, placeholders: 0, ahead: 0, cancelled: 0, seeded: 0 };
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
}

// page.js: the pages on screen (first, last; -1 when none) and the zoom changed (told inside its frame: only take note)
export function view(first, last, z) {
  const was = (range[0] + range[1]) / 2, now = (first + last) / 2;
  if (first >= 0 && range[0] >= 0 && now !== was) dir = now > was ? 1 : -1;
  range = [first, last]; zoom = z;
  if (!order.length) return;
  for (const r of order) if (r.idx >= first && r.idx <= last) r.used = ++useN;
  if (job && job.ahead && job.task) job.task.cancel();                   // she moved: the page ahead may not be ahead now
  place();
  arm(Math.max(0, QUIET - sinceMove()));                                  // still (a jump, a note opening): at once
}

// a page's PDF bytes came in (the phone downloaded them): draw what is waiting
export function bytesArrived() { R.forEach((r) => { r.failAt = 0; }); place(); arm(0); }

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
  for (const r of want) placeOne(r, r.idx >= a - 1 && r.idx <= b + 1);
}
function placeOne(r, near) {
  const p = cfg.page(r.id);
  if (!p || !p.pdf_path || !r.layer) return;
  // a thumb not made yet is made only for the pages on screen and one each side, and only while the stack moves (the
  // sharp render waits then): on a still stack the sharp render starts at once, as on a scan a thumb costs about what
  // the sharp render does (measured, round C). A thumb already made goes in for all KEEP pages either side.
  if (!thumbs.has(keyOf(p)) && (!near || sinceMove() >= QUIET)) return;
  const tok = {};
  r.ph = tok;
  tok.p = thumbUrl(p, r).then(async (url) => {
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
  const W = Math.max(1, Math.round(w * s)), H = Math.max(1, Math.round(h * s));
  const c = document.createElement('canvas');
  c.width = W; c.height = H; c.className = 'pdfCanvas';
  const g = c.getContext('2d', { alpha: false });
  job = { r, ahead, task: null };
  try { await renderInto(pg, g, W, H, true, (task) => { job.task = task; }); }
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

// ---------------------------------------------------------------- pictures of a page elsewhere
// the PDF page drawn into a 2D context at 0, 0, W x H (the page picture and Share, js/app.js renderPage). Throws when
// the PDF is not on this device and cannot be downloaded now: the picture waits (snap.js tries again).
export async function paint(g, p, W, H) {
  const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
  g.save();
  try { await renderInto(pg, g, W, H, false); } finally { g.restore(); pg.cleanup(); }
}

// small renders, one blob: URL per PDF page, made one at a time. The desk's asks go first (nearest the screen first);
// one for a page the desk has scrolled away from, that nothing else asked for, is dropped (asked for again when needed)
const thumbs = new Map();   // pdf_path#page -> { key, p (Promise<url|null>), ok, page, recs (desk records), list, run }
const thumbQ = [];
let thumbBusy = false;
const keyOf = (p) => p.pdf_path + '#' + p.pdf_page;
const thumbH = (p) => { const { w, h } = pageSize(p); return Math.max(1, Math.round(THUMB_W * h / w)); };
function thumbUrl(p, rec) {
  const key = keyOf(p);
  let e = thumbs.get(key);
  if (!e) {
    e = { key, page: p, recs: new Set(), list: false, run: false };
    e.p = new Promise((ok) => { e.ok = ok; });
    thumbs.set(key, e); thumbQ.push(e);
  }
  if (rec) e.recs.add(rec); else e.list = true;                           // who asked, before the queue looks at it
  pumpThumbs();
  return e.p;
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
    for (let e; (e = nextThumb());) {
      e.run = true;
      let url = null;
      try { url = await makeThumb(e.page); } catch (_) { url = null; }
      if (!url) thumbs.delete(e.key);                                      // not there yet: asked for again next time
      e.ok(url);
    }
  } finally { thumbBusy = false; }
}
async function makeThumb(p) {
  const W = THUMB_W, H = thumbH(p);
  const doc = await docOf(p.pdf_path), pg = await doc.getPage(p.pdf_page);
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  try { await renderInto(pg, c.getContext('2d', { alpha: false }), W, H, true); } finally { pg.cleanup(); }
  return toUrl(c);
}
async function toUrl(c) {
  const blob = await new Promise((ok) => c.toBlob(ok, 'image/jpeg', 0.85));
  c.width = 0; c.height = 0;
  if (!blob) return null;
  stats.thumbs++;
  return URL.createObjectURL(blob);
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
  e.p = toUrl(c).then((url) => { if (!url) thumbs.delete(key); else stats.seeded++; return url; }, () => { thumbs.delete(key); return null; });
  thumbs.set(key, e);
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
           placeholdersLive: ph, keep: KEEP, budget, dir, events: [...events], evN };
}
// the tests' small budget, so the 40-page fixture (under 1 Mpx a page) reaches it; no argument = the real one
export function setBudget(px) { budget = px > 0 ? px : BUDGET_PX; trim(); }
