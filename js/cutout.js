// PenWorks Cut out (pw-v9e, her ask 7 Nov 18:27 "pick ANY image, then ... pick the transparent background", 18:29 "Tap the
// background, I don't want an AI cut-out"; the look is _build/cutout/cutout-mock.png). Her touchstone is PowerPoint's "Set
// Transparent Color"; this one is kinder: a fussiness slider, and the connected region or everywhere. No AI model, no
// cloud service: a flood fill over the picture's own pixels, here on the device.
//
// The way in: the Select tool's chips. ONE unlocked picture selected = a wand chip, Cut out, after Lock (js/ink.js
// fillChips); it opens the full-screen sheet (#cutout) on that picture. The sheet: the picture large on a checkerboard
// (12 px light grey and white squares in both modes: it means "see-through"), fitted with its aspect kept; two fingers pinch
// to zoom and pan, one finger (or the pen, or the mouse) taps; the laptop's wheel zooms about the pointer. The bar: Undo,
// Reset, the Fussiness slider (0 to 100, 30 to start), the Everywhere switch, Cancel and Done. On the phone (under 600 px)
// the bar is three rows: the slider, then Undo / Reset / Everywhere, then Cancel / Done at the right.
//
// A TAP takes the background away (cutFill below): from the tapped pixel through every connected pixel whose colour is
// within the fussiness of the tapped colour (Euclidean RGB on 0 to 255 channels; fussiness 0 to 100 = a distance of 0 to
// 180, so 30 = 54). Those go fully see-through. The FEATHER: a pixel between 1 and 1.5 times that distance keeps a share of
// its alpha growing linearly to all of it at 1.5 times, so an anti-aliased or soft edge leaves no light halo. In the
// connected fill a feather pixel is one next to a removed pixel, or next to a feather pixel and further from the tapped
// colour than it (the feather follows an edge's gradient outward and never spreads over a flat near-colour area). Pixels
// already see-through (alpha under 8) are walls: never matched, never crossed. EVERYWHERE on: every matching pixel in the
// whole picture goes, connected or not, with the same feather. Only alpha changes; the colours stay as they came, so a
// re-run starts from the true colours.
// THE SLIDER IS LIVE ON THE LAST TAP: moving it runs the last tap again (its pixel, its Everywhere) over the picture as it
// was before that tap; later taps use the new value. Undo steps back one tap (each step keeps the alpha plane from before
// it), Reset is the picture as it came (no steps), Cancel, Escape and the Back press change nothing.
// DONE: the edited pixels at the picture's own size (nw x nh) as a PNG (canvas.toBlob), kept on this device under a NEW path
// <owner>/<uuid>.png (js/pdfin.js keepPicture: never over the old file, so undo works and the phone's copy is never half
// replaced) and sent up the same upload ladder as a new picture; then the record's data.path becomes that path, everything
// else kept, ONE undo step on the page (js/ink.js setImagePath). A JPEG becomes a PNG by it (alpha needs it). Nothing
// removed (no steps): Done is Cancel. Over the 10 MB cap: the IMG_TOO_BIG toast, the sheet stays open.
// Bytes not on this device yet (the phone before its download): the sheet says "This picture has not downloaded yet" and
// asks again 2, 5, 10, 30 s later (then every 30 s) while it is open; Done waits for them, Cancel is the way out.

import { bytesOf, keepPicture, IMG_TOO_BIG } from './pdfin.js';

export const WALL = 8;                 // alpha under this is see-through already: a wall
export const FUSS_MAX = 180;           // the colour distance at fussiness 100
export const FUSS_START = 30;
const ZMAX = 8;                        // the stage zooms from fitted (1) to 8 x
const TAP_PX = 10;                     // a press that moves further than this (screen px) is not a tap
const WAIT = [2000, 5000, 10000, 30000];

export const distOf = (fuss) => Math.max(0, Math.min(100, +fuss || 0)) * FUSS_MAX / 100;

// ---------------------------------------------------------------- the fill (pure: typed arrays in, typed arrays out)
// px: RGBA (Uint8ClampedArray, as getImageData gives it); w, h; (sx, sy) the tapped pixel; D the colour distance; every:
// the whole picture, connected or not. Writes the new alphas into px and returns the box of the changed pixels
// [x0, y0, x1, y1] (inclusive), or null when nothing changed (a tap on a wall). work: { seen, stack } typed arrays of at
// least w * h, kept between taps so a 2048 x 2048 picture does not allocate 20 MB a tap.
export function cutFill(px, w, h, sx, sy, D, every, work) {
  sx = Math.floor(sx); sy = Math.floor(sy);
  if (!(sx >= 0 && sy >= 0 && sx < w && sy < h)) return null;
  const s = sy * w + sx, s4 = s * 4;
  if (px[s4 + 3] < WALL) return null;
  const r0 = px[s4], g0 = px[s4 + 1], b0 = px[s4 + 2];
  const D2 = D * D, F = 1.5 * D, F2 = F * F, band = F - D;
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  if (every) {
    for (let y = 0, j = 0; y < h; y++) {
      for (let x = 0; x < w; x++, j += 4) {
        const a = px[j + 3];
        if (a < WALL) continue;
        const dr = px[j] - r0, dg = px[j + 1] - g0, db = px[j + 2] - b0, d2 = dr * dr + dg * dg + db * db;
        let na;
        if (d2 <= D2) na = 0;
        else if (d2 < F2) na = Math.round(a * (Math.sqrt(d2) - D) / band);
        else continue;
        if (na === a) continue;
        px[j + 3] = na;
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
    return x1 < 0 ? null : [x0, y0, x1, y1];
  }
  const N = w * h, seen = work && work.seen && work.seen.length >= N ? work.seen : new Uint8Array(N);
  const stack = work && work.stack && work.stack.length >= N ? work.stack : new Int32Array(N);
  if (work) { work.seen = seen; work.stack = stack; }
  seen.fill(0, 0, N);
  let sp = 0;
  seen[s] = 1; px[s4 + 3] = 0; stack[sp++] = s;
  x0 = x1 = sx; y0 = y1 = sy;
  while (sp) {
    const v = stack[--sp], fea = v < 0, p = fea ? ~v : v, x = p % w, y = (p - x) / w;
    let dp2 = 0;
    if (fea) { const j = p * 4, dr = px[j] - r0, dg = px[j + 1] - g0, db = px[j + 2] - b0; dp2 = dr * dr + dg * dg + db * db; }
    for (let k = 0; k < 4; k++) {
      let q;
      if (k === 0) { if (x === 0) continue; q = p - 1; }
      else if (k === 1) { if (x === w - 1) continue; q = p + 1; }
      else if (k === 2) { if (y === 0) continue; q = p - w; }
      else { if (y === h - 1) continue; q = p + w; }
      if (seen[q]) continue;
      const j = q * 4, a = px[j + 3];
      if (a < WALL) continue;
      const dr = px[j] - r0, dg = px[j + 1] - g0, db = px[j + 2] - b0, d2 = dr * dr + dg * dg + db * db;
      if (!fea && d2 <= D2) { seen[q] = 1; px[j + 3] = 0; stack[sp++] = q; }
      else if (d2 > D2 && d2 < F2 && (!fea || d2 > dp2)) {
        seen[q] = 1; px[j + 3] = Math.round(a * (Math.sqrt(d2) - D) / band); stack[sp++] = ~q;
      } else continue;
      const qx = q % w, qy = (q - qx) / w;
      if (qx < x0) x0 = qx; if (qx > x1) x1 = qx; if (qy < y0) y0 = qy; if (qy > y1) y1 = qy;
    }
  }
  return [x0, y0, x1, y1];
}
// the alpha plane of px (one byte a pixel), and back
function alphaOf(px, N, out) { const a = out || new Uint8Array(N); for (let p = 0, j = 3; p < N; p++, j += 4) a[p] = px[j]; return a; }
function alphaTo(px, a) { for (let p = 0, j = 3, n = a.length; p < n; p++, j += 4) px[j] = a[p]; }
const union = (a, b) => (!a ? b : !b ? a : [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])]);

// ---------------------------------------------------------------- the sheet
let C = null;                          // the open sheet: { rec, commit, toast, veil, ... }
const stats = { opened: 0, taps: 0, fillMs: 0, tapMs: 0, done: 0 };

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
  return e;
}

// open the sheet on a picture record (a copy). commit(path, blob) puts the new file on the record (js/ink.js setImagePath
// through js/app.js); toast(msg) is the app's toast. One sheet at a time.
export function openCutout(rec, { commit, toast } = {}) {
  if (!rec || rec.kind !== 'image' || !rec.data || !rec.data.path) return false;
  if (C) close();
  stats.opened++;
  const fuss = el('input', { type: 'range', min: '0', max: '100', step: '1', value: String(FUSS_START), id: 'cutFuss', 'aria-label': 'Fussiness' });
  const val = el('span', { class: 'cutVal', 'aria-hidden': 'true' }, String(FUSS_START));
  const every = el('button', { type: 'button', class: 'cutSw', role: 'switch', 'aria-checked': 'false', 'data-cut': 'everywhere' }, el('i'), 'Everywhere');
  const undoB = el('button', { type: 'button', class: 'dlgBtn', 'data-cut': 'undo', disabled: true }, 'Undo');
  const resetB = el('button', { type: 'button', class: 'dlgBtn', 'data-cut': 'reset', disabled: true }, 'Reset');
  const cancelB = el('button', { type: 'button', class: 'dlgBtn', 'data-cut': 'cancel' }, 'Cancel');
  const doneB = el('button', { type: 'button', class: 'dlgBtn main', 'data-cut': 'done', disabled: true }, 'Done');
  const canvas = el('canvas', { class: 'cutCanvas' });
  const mark = el('div', { class: 'cutMark', hidden: true });
  const board = el('div', { class: 'cutBoard', hidden: true }, canvas, mark);
  const msg = el('div', { class: 'cutMsg', role: 'status' });
  const stage = el('div', { class: 'cutStage' }, board, msg);
  const box = el('div', { class: 'cut', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'cutTitle' },
    el('div', { class: 'cutHead' }, el('b', { id: 'cutTitle' }, 'Cut out'), el('span', {}, 'Tap the background to take it away')),
    stage,
    el('div', { class: 'cutBar' }, undoB, resetB,
      el('div', { class: 'cutGrow' }, el('label', { class: 'cutSl', for: 'cutFuss' }, 'Fussiness'), fuss, val),
      every,
      el('div', { class: 'cutEnd' }, cancelB, doneB)));
  const veil = el('div', { id: 'cutout' }, box);
  C = { rec, commit, toast: toast || (() => {}), veil, stage, board, canvas, mark, msg, fuss, val, every, undoB, resetB, doneB,
        g: null, img: null, w: 0, h: 0, orig: null, steps: [], work: {}, everywhere: false, zoom: { s: 1, tx: 0, ty: 0 },
        ptrs: new Map(), gest: null, tap: null, waitT: 0, tries: 0, busy: false, raf: 0, ro: null, fit: null };
  const me = C;
  undoB.addEventListener('click', () => { if (C === me) undoStep(); });
  resetB.addEventListener('click', () => { if (C === me) reset(); });
  cancelB.addEventListener('click', () => { if (C === me && !me.busy) close(); });   // not while Done is saving
  doneB.addEventListener('click', () => { if (C === me) done(); });
  every.addEventListener('click', () => {
    if (C !== me) return;
    me.everywhere = !me.everywhere;
    every.setAttribute('aria-checked', String(me.everywhere)); every.classList.toggle('on', me.everywhere);
  });
  fuss.addEventListener('input', () => {
    if (C !== me) return;
    val.textContent = fuss.value;
    if (!me.raf) me.raf = requestAnimationFrame(() => { me.raf = 0; if (C === me) rerun(); });
  });
  stage.addEventListener('pointerdown', down);
  stage.addEventListener('pointermove', move);
  stage.addEventListener('pointerup', up);
  stage.addEventListener('pointercancel', cancelPtr);
  stage.addEventListener('wheel', wheel, { passive: false });
  stage.addEventListener('contextmenu', (e) => e.preventDefault());
  document.body.append(veil);
  document.addEventListener('keydown', keys, true);
  me.ro = new ResizeObserver(() => { if (C === me) layout(); });
  me.ro.observe(stage);
  load(me);
  return true;
}
export const cutoutOpen = () => !!C;

// the bytes, then the pixels; not here yet: the message and the ladder
async function load(me) {
  const blob = await bytesOf(me.rec.data.path).catch(() => null);
  if (C !== me) return;
  if (!blob) {
    me.msg.textContent = 'This picture has not downloaded yet';
    me.waitT = setTimeout(() => { me.waitT = 0; if (C === me) load(me); }, WAIT[Math.min(me.tries++, WAIT.length - 1)]);
    return;
  }
  let bmp;
  try { bmp = await createImageBitmap(blob); }
  catch (_) { if (C === me) me.msg.textContent = 'This picture could not be opened.'; return; }
  if (C !== me) { bmp.close(); return; }
  const d = me.rec.data, w = d.nw > 0 ? Math.round(d.nw) : bmp.width, h = d.nh > 0 ? Math.round(d.nh) : bmp.height;
  me.canvas.width = w; me.canvas.height = h;
  const g = me.canvas.getContext('2d', { willReadFrequently: true });
  g.drawImage(bmp, 0, 0, w, h);
  bmp.close();
  me.g = g; me.w = w; me.h = h;
  me.img = g.getImageData(0, 0, w, h);
  me.orig = alphaOf(me.img.data, w * h);
  me.msg.textContent = '';
  me.board.hidden = false;
  me.board.style.aspectRatio = `${w} / ${h}`;
  layout();
  buttons();
}

// the board fitted inside the stage, aspect kept; the zoom is a transform on top of that
function layout() {
  if (!C || !C.w) return;
  const cs = getComputedStyle(C.stage), pw = C.stage.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const ph = C.stage.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  if (!(pw > 0 && ph > 0)) return;
  const k = Math.min(pw / C.w, ph / C.h), bw = C.w * k, bh = C.h * k;
  C.board.style.width = bw.toFixed(1) + 'px'; C.board.style.height = bh.toFixed(1) + 'px';
  C.fit = { bw, bh };
  applyZoom();
}
function applyZoom() {
  const z = C.zoom;
  if (z.s <= 1.0001) { z.s = 1; z.tx = 0; z.ty = 0; }
  else if (C.fit) {                                         // the board never leaves the stage's middle entirely
    const mx = (C.fit.bw * z.s) / 2, my = (C.fit.bh * z.s) / 2;
    z.tx = Math.max(-mx, Math.min(mx, z.tx)); z.ty = Math.max(-my, Math.min(my, z.ty));
  }
  C.board.style.transform = z.s === 1 ? '' : `translate(${z.tx.toFixed(1)}px, ${z.ty.toFixed(1)}px) scale(${z.s.toFixed(4)})`;
  C.mark.style.transform = `translate(-50%, -50%) scale(${(1 / z.s).toFixed(4)})`;
}
// the board's centre on screen before the zoom's transform (the stage centres it)
function boardCentre() {
  const r = C.stage.getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2];
}
function zoomAbout(cx, cy, s) {
  const z = C.zoom, [bx, by] = boardCentre(), ns = Math.max(1, Math.min(ZMAX, s));
  const lx = (cx - bx - z.tx) / z.s, ly = (cy - by - z.ty) / z.s;   // the board point under (cx, cy), from its centre
  z.s = ns; z.tx = cx - bx - ns * lx; z.ty = cy - by - ns * ly;
  applyZoom();
}

// ---------------------------------------------------------------- pointers: one taps, two pinch and pan
function down(e) {
  if (!C || e.button > 0) return;
  e.preventDefault();
  try { C.stage.setPointerCapture(e.pointerId); } catch (_) { /* a synthetic event */ }
  C.ptrs.set(e.pointerId, [e.clientX, e.clientY]);
  if (C.ptrs.size === 1) { C.tap = { id: e.pointerId, x: e.clientX, y: e.clientY, ok: true }; C.gest = null; }
  else {
    if (C.tap) C.tap.ok = false;                             // a second finger: never a tap
    startPinch();
  }
}
function startPinch() {
  const p = [...C.ptrs.values()].slice(0, 2);
  if (p.length < 2) { C.gest = null; return; }
  const z = C.zoom, mx = (p[0][0] + p[1][0]) / 2, my = (p[0][1] + p[1][1]) / 2, [bx, by] = boardCentre();
  C.gest = { d0: Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) || 1, s0: z.s, lx: (mx - bx - z.tx) / z.s, ly: (my - by - z.ty) / z.s };
}
function move(e) {
  if (!C || !C.ptrs.has(e.pointerId)) return;
  C.ptrs.set(e.pointerId, [e.clientX, e.clientY]);
  if (C.tap && C.tap.id === e.pointerId && Math.hypot(e.clientX - C.tap.x, e.clientY - C.tap.y) > TAP_PX) C.tap.ok = false;
  if (C.gest && C.ptrs.size >= 2) {
    const p = [...C.ptrs.values()].slice(0, 2), g = C.gest, z = C.zoom, [bx, by] = boardCentre();
    const mx = (p[0][0] + p[1][0]) / 2, my = (p[0][1] + p[1][1]) / 2, d = Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]);
    z.s = Math.max(1, Math.min(ZMAX, g.s0 * d / g.d0));
    z.tx = mx - bx - z.s * g.lx; z.ty = my - by - z.s * g.ly;   // the point under the fingers stays under them
    applyZoom();
  }
}
function up(e) {
  if (!C || !C.ptrs.has(e.pointerId)) return;
  C.ptrs.delete(e.pointerId);
  const t = C.tap;
  if (t && t.id === e.pointerId) {
    C.tap = null;
    if (t.ok && !C.ptrs.size) tapAt(e.clientX, e.clientY);
  }
  if (C.ptrs.size >= 2) startPinch(); else C.gest = null;
}
function cancelPtr(e) { if (!C) return; C.ptrs.delete(e.pointerId); if (C.tap && C.tap.id === e.pointerId) C.tap = null; if (C.ptrs.size < 2) C.gest = null; }
function wheel(e) {                                          // the laptop: the wheel zooms about the pointer
  if (!C || !C.w) return;
  e.preventDefault();
  zoomAbout(e.clientX, e.clientY, C.zoom.s * Math.exp(-e.deltaY / 400));
}

// ---------------------------------------------------------------- taps, the slider, Undo, Reset
// a tap at (cx, cy) on screen: the pixel under it on the canvas (the zoom's transform is in its box)
function tapAt(cx, cy) {
  if (!C || !C.img || C.busy) return;
  const r = C.canvas.getBoundingClientRect();
  if (!(r.width > 0 && r.height > 0)) return;
  const x = Math.floor((cx - r.left) / r.width * C.w), y = Math.floor((cy - r.top) / r.height * C.h);
  if (x < 0 || y < 0 || x >= C.w || y >= C.h) return;
  tapPixel(x, y);
}
// a tap on pixel (x, y): one step, from the picture as it is now
function tapPixel(x, y) {
  const N = C.w * C.h, t0 = performance.now(), before = alphaOf(C.img.data, N);
  const f0 = performance.now(), D = distOf(C.fuss.value);
  const box = cutFill(C.img.data, C.w, C.h, x, y, D, C.everywhere, C.work);
  stats.fillMs = performance.now() - f0;
  if (!box) { stats.tapMs = performance.now() - t0; return false; }
  C.steps.push({ x, y, every: C.everywhere, D, before, box });
  draw(box);
  stats.tapMs = performance.now() - t0;
  stats.taps++;
  showMark();
  buttons();
  return true;
}
// the slider moved: the last tap again, over the picture as it was before it, with the new distance
function rerun() {
  const st = C.steps[C.steps.length - 1], D = distOf(C.fuss.value);
  if (!st || !C.img || st.D === D) return;
  const t0 = performance.now();
  alphaTo(C.img.data, st.before);
  const f0 = performance.now();
  const box = cutFill(C.img.data, C.w, C.h, st.x, st.y, D, st.every, C.work);
  stats.fillMs = performance.now() - f0;
  draw(union(st.box, box));
  st.D = D; st.box = box || st.box;
  stats.tapMs = performance.now() - t0;
}
function undoStep() {
  const st = C.steps.pop();
  if (!st) return;
  alphaTo(C.img.data, st.before);
  draw(st.box);
  showMark(); buttons();
}
function reset() {
  if (!C.img || !C.steps.length) return;
  alphaTo(C.img.data, C.orig);
  C.steps = [];
  draw([0, 0, C.w - 1, C.h - 1]);
  showMark(); buttons();
}
function draw(b) {
  if (!b) return;
  C.g.putImageData(C.img, 0, 0, b[0], b[1], b[2] - b[0] + 1, b[3] - b[1] + 1);
}
// the ring where the last tap landed (the one the slider works on)
function showMark() {
  const st = C.steps[C.steps.length - 1];
  C.mark.hidden = !st;
  if (st) { C.mark.style.left = ((st.x + 0.5) / C.w * 100).toFixed(3) + '%'; C.mark.style.top = ((st.y + 0.5) / C.h * 100).toFixed(3) + '%'; }
}
function buttons() {
  const n = C.steps.length;
  C.undoB.disabled = !n || C.busy; C.resetB.disabled = !n || C.busy; C.doneB.disabled = !C.img || C.busy;
}

// ---------------------------------------------------------------- Escape, Cancel, Done
function keys(e) {
  if (!C) return;
  const k = e.key.toLowerCase();
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (!C.busy) close(); }
  else if ((e.ctrlKey || e.metaKey) && (k === 'z' || k === 'y')) {   // the note's undo must not run behind the sheet
    e.preventDefault(); e.stopPropagation();
    if (k === 'z' && !e.shiftKey && !C.busy) undoStep();
  }
}
// the Back press closes the note behind the sheet (the app pops its history then); the sheet goes with it, as Cancel
addEventListener('popstate', () => { if (C && !C.busy) close(); });

export function close() {
  if (!C) return;
  const me = C;
  C = null;
  clearTimeout(me.waitT);
  if (me.raf) cancelAnimationFrame(me.raf);
  if (me.ro) me.ro.disconnect();
  document.removeEventListener('keydown', keys, true);
  me.veil.remove();
  me.canvas.width = 0; me.canvas.height = 0;
}
async function done() {
  if (!C || C.busy || !C.img) return;
  if (!C.steps.length) { close(); return; }                 // nothing removed: Done is Cancel
  const me = C;
  me.busy = true; buttons();
  let blob = null;
  try { blob = await new Promise((ok, no) => me.canvas.toBlob((b) => (b ? ok(b) : no(new Error('no PNG'))), 'image/png')); }
  catch (e) { console.warn('PenWorks: the cut-out picture could not be made', e); }
  if (C !== me) return;
  const path = blob ? await keepPicture(blob, 'cut-out.png') : null;
  if (C !== me) return;
  if (!path) {                                              // over the 10 MB cap (or no PNG): say so, the sheet stays
    me.busy = false; buttons();
    me.toast(blob ? IMG_TOO_BIG : 'This picture could not be saved.', 5000);
    return;
  }
  let ok = false;
  try { ok = !!(me.commit && me.commit(path, blob)); } catch (e) { console.warn('PenWorks: the cut-out could not be put on the page', e); }
  stats.done += ok ? 1 : 0;
  close();
}

// for the checks (window.__pw.cutout): the sheet's state, a pixel of the working picture, and a tap by pixel
export function cutoutState() {
  if (!C) return { open: false, ...stats };
  return { open: true, ...stats, w: C.w, h: C.h, loaded: !!C.img, steps: C.steps.length, fuss: +C.fuss.value,
           everywhere: C.everywhere, zoom: C.zoom.s, msg: C.msg.textContent, busy: C.busy, path: C.rec.data.path };
}
export function cutoutPixel(x, y) {
  if (!C || !C.img) return null;
  const j = (y * C.w + x) * 4, p = C.img.data;
  return [p[j], p[j + 1], p[j + 2], p[j + 3]];
}
export function cutoutTap(x, y) { return !!(C && C.img && !C.busy && tapPixel(x, y)); }
