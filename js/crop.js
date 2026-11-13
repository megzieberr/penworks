// PenWorks Crop (pw-v9g, her ask 13 Nov: "I want to be able to crop my images please"). A rectangle only: no lasso, no free
// shape, no aspect lock, no turning in here (her rulings).
//
// The way in: the Select tool's chips. ONE unlocked picture selected (on a page or on a sticky) = a Crop chip right after the
// wand (js/ink.js fillChips); it starts crop mode ON THE PAGE through the cropIt hook (js/app.js). The picture stays exactly
// where it lies. The selection clears; a layer (svg.cropLayer, in the picture's own page or sticky px, never clipped) draws,
// in the picture's TURNED frame (rotate(rot) about the box's centre, as the picture itself is drawn): the part outside the
// crop rectangle dimmed, the rectangle's line, four corner and four side handles. Each handle's target is a circle of
// HIT screen px radius (40 px across at every zoom), redrawn when the zoom changes; the handles are drawn 7 screen px.
// The rectangle starts at the whole picture. A handle drag resizes it, a drag inside moves it; it never leaves the picture
// and is never under MIN page px (or the picture's own side, when that is smaller). The press on a handle or inside the
// rectangle (pen, mouse or finger) is crop's own: it never reaches js/page.js (stopPropagation), so it never draws and never
// scrolls; a press anywhere else reaches the desk as always: a finger pans, two fingers pinch, the wheel scrolls, but the
// pen and the mouse draw nothing (app.js's desk hook swallows them while crop mode is on) and a finger's tap or hold does
// nothing either.
// The bar: Cancel and Done (words, not icons) where the selection chips sit, above the picture's box. On the laptop Enter is
// Done and Escape is Cancel; Ctrl+Z / Ctrl+Y are held back while crop mode is on (the note's undo must not run under it);
// the undo and redo buttons, closing the note, the Back press and the pen button end it as Cancel (app.js).
// DONE: the kept region cut out of the picture's ORIGINAL file at its full natural size (the rectangle snapped to whole
// pixels of the file; see-through kept), as a NEW file (js/pdfin.js keepPicture, the old one stays: undo needs it). A JPEG's
// crop stays a JPEG (quality 0.92: its photo would be several times bigger as a PNG, and a JPEG has no see-through to keep);
// a PNG's stays a PNG. Then ONE undo step (js/ink.js setImageCrop) changes the path and the box (x, y, w, h, nw, nh) so the
// kept part stays exactly where it was on the page: the new box's centre is the kept region's centre turned about the old
// box's centre by rot, and the new box turns by the same rot about it. The picture stays selected. The rectangle still the
// whole picture: Done is Cancel. Over the 10 MB cap: the IMG_TOO_BIG toast, crop mode stays. Bytes not on this device yet:
// "This picture has not downloaded yet", crop mode stays.

import { view } from './page.js';
import { bytesOf, keepPicture, IMG_TOO_BIG } from './pdfin.js';
import { clearSelection, selectRecs, strokesOf, setImageCrop } from './ink.js';

const SVGNS = 'http://www.w3.org/2000/svg';
export const HIT = 20;                 // a handle's target: radius in screen px (40 px across)
const KNOB = 7;                        // a handle drawn: radius in screen px
export const MIN = 20;                 // the rectangle's smallest side, page px (about 5 mm)
const GAP = HIT + 6;                   // the bar's distance from the box, screen px: clear of the handles' targets
const BLUE = '#2F4BB8';
const KINDS = ['n', 's', 'w', 'e', 'nw', 'ne', 'se', 'sw'];   // sides first, the corners drawn (and hit) on top

let K = null;                          // crop mode: { page, id, rec, host, layer, g, els, bar, r: { l, t, r, b }, drag, z, ... }
const stats = { started: 0, done: 0, cancelled: 0, lastMs: 0, lastType: '' };

const q3 = (v) => Math.round(v * 1000) / 1000;
const f2 = (v) => String(Math.round(v * 100) / 100);
function turn(q, c, deg) {             // as js/ink.js: plus = clockwise on the page
  if (!deg) return q;
  const t = deg * Math.PI / 180, cs = Math.cos(t), sn = Math.sin(t), x = q[0] - c[0], y = q[1] - c[1];
  return [c[0] + x * cs - y * sn, c[1] + x * sn + y * cs];
}
function box(rec) {
  const d = rec.data || {}, x = +d.x || 0, y = +d.y || 0, w = +d.w || 0, h = +d.h || 0;
  return { x, y, w, h, rot: +d.rot || 0, c: [x + w / 2, y + h / 2] };
}
function svgEl(tag, at = {}) { const e = document.createElementNS(SVGNS, tag); for (const k in at) e.setAttribute(k, at[k]); return e; }
const hostOf = (id) => document.querySelector(`#stack .sheet[data-id="${CSS.escape(id)}"], #stack .sticky[data-id="${CSS.escape(id)}"]`);

// ---------------------------------------------------------------- start, end
// start crop mode on picture rec (a copy) on page or sticky pageId. toast(msg, ms): the app's toast.
export function startCrop(pageId, rec, { toast } = {}) {
  if (!rec || rec.kind !== 'image' || !rec.data || !rec.data.path || rec.data.locked) return false;
  const host = hostOf(pageId), b = box(rec);
  if (!host || !(b.w > 0 && b.h > 0)) return false;
  if (K) cancelCrop();
  clearSelection();
  stats.started++;
  const W = parseFloat(host.style.width) || host.clientWidth, H = parseFloat(host.style.height) || host.clientHeight;
  const layer = svgEl('svg', { class: 'cropLayer', width: W, height: H, viewBox: `0 0 ${W} ${H}` });
  const g = svgEl('g', b.rot ? { transform: `rotate(${f2(b.rot)} ${f2(b.c[0])} ${f2(b.c[1])})` } : {});
  const els = {
    dim: svgEl('path', { class: 'cropDim', fill: 'rgba(20,22,26,0.5)', 'fill-rule': 'evenodd' }),
    line: svgEl('rect', { class: 'cropLine', fill: 'none', stroke: '#FFFFFF' }),
    line2: svgEl('rect', { class: 'cropLine2', fill: 'none', stroke: BLUE }),
    body: svgEl('rect', { class: 'cropBody', 'data-k': 'move', fill: 'transparent' }),
    hs: KINDS.map((k) => {
      const hg = svgEl('g', { class: 'cropH', 'data-k': k });
      const hit = svgEl('circle', { class: 'cropHit', fill: 'transparent' });
      const knob = k.length === 2 ? svgEl('circle', { class: 'cropKnob', fill: '#FFFFFF', stroke: BLUE })
        : svgEl('rect', { class: 'cropKnob', fill: '#FFFFFF', stroke: BLUE });
      hg.append(hit, knob);
      return { k, g: hg, hit, knob };
    }),
  };
  g.append(els.dim, els.body, els.line2, els.line, ...els.hs.map((h) => h.g));
  layer.append(g);
  const cancelB = document.createElement('button'), doneB = document.createElement('button');
  cancelB.type = 'button'; cancelB.dataset.crop = 'cancel'; cancelB.textContent = 'Cancel';
  doneB.type = 'button'; doneB.dataset.crop = 'done'; doneB.textContent = 'Done';
  const bar = document.createElement('div'); bar.className = 'cropBar'; bar.append(cancelB, doneB);
  if (host.classList.contains('sticky')) host.insertBefore(layer, host.querySelector('.strip'));
  else host.appendChild(layer);
  host.appendChild(bar);
  K = { page: pageId, id: rec.id, rec, b, host, layer, g, els, bar, doneB, r: { l: 0, t: 0, r: b.w, b: b.h }, drag: null, z: 0,
        toast: toast || (() => {}), busy: false, bmp: null, bytes: null, mo: null };
  const me = K;
  cancelB.addEventListener('click', (e) => { e.stopPropagation(); if (K === me && !me.busy) cancelCrop(); });
  doneB.addEventListener('click', (e) => { e.stopPropagation(); if (K === me) doneCrop(); });
  layer.addEventListener('pointerdown', down);
  layer.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); });
  const stack = document.getElementById('stack');
  if (stack) { me.mo = new MutationObserver(() => { if (K === me && K.z !== view().z) draw(); }); me.mo.observe(stack, { attributes: true, attributeFilter: ['data-zoom', 'style'] }); }
  me.bytes = bytesOf(rec.data.path).catch(() => null);           // fetched now, so Done is quick
  draw();
  return true;
}
export const cropActive = () => !!K;

function end(reselect) {
  if (!K) return;
  const me = K;
  K = null;
  if (me.mo) me.mo.disconnect();
  me.layer.remove(); me.bar.remove();
  if (me.bmp) { try { me.bmp.close(); } catch (_) { /* ignore */ } }
  if (reselect && me.host.isConnected) selectRecs(me.page, [me.id]);
}
// Cancel (and Escape, the undo button, the Back press, ...): nothing changes; the picture is selected again
export function cancelCrop(reselect = true) { if (!K) return; stats.cancelled++; end(reselect); }
// js/app.js onSheets: the stack was rebuilt; crop mode goes when its page went with it
export function sheetsChanged() { if (K && !K.host.isConnected) cancelCrop(false); }

// ---------------------------------------------------------------- drawing (attributes updated in place: a held pointer keeps its element)
function draw() {
  if (!K) return;
  const z = view().z || 1, { x, y, w, h } = K.b, r = K.r, e = K.els;
  K.z = z;
  const X0 = x + r.l, Y0 = y + r.t, X1 = x + r.r, Y1 = y + r.b;
  e.dim.setAttribute('d', `M${f2(x)} ${f2(y)}H${f2(x + w)}V${f2(y + h)}H${f2(x)}Z M${f2(X0)} ${f2(Y0)}H${f2(X1)}V${f2(Y1)}H${f2(X0)}Z`);
  const rect = (el) => { el.setAttribute('x', f2(X0)); el.setAttribute('y', f2(Y0)); el.setAttribute('width', f2(X1 - X0)); el.setAttribute('height', f2(Y1 - Y0)); };
  rect(e.body); rect(e.line); rect(e.line2);
  e.line.setAttribute('stroke-width', f2(1.5 / z));
  e.line2.setAttribute('stroke-width', f2(3.5 / z));
  const mx = (X0 + X1) / 2, my = (Y0 + Y1) / 2;
  const at = { n: [mx, Y0], s: [mx, Y1], w: [X0, my], e: [X1, my], nw: [X0, Y0], ne: [X1, Y0], se: [X1, Y1], sw: [X0, Y1] };
  for (const hd of e.hs) {
    const [cx, cy] = at[hd.k];
    hd.hit.setAttribute('cx', f2(cx)); hd.hit.setAttribute('cy', f2(cy)); hd.hit.setAttribute('r', f2(HIT / z));
    const kb = hd.knob;
    kb.setAttribute('stroke-width', f2(1.5 / z));
    if (hd.k.length === 2) { kb.setAttribute('cx', f2(cx)); kb.setAttribute('cy', f2(cy)); kb.setAttribute('r', f2(KNOB / z)); }
    else {                                                        // a side: a short bar along its edge
      const long = 18 / z, thin = 7 / z, horiz = hd.k === 'n' || hd.k === 's', bw = horiz ? long : thin, bh = horiz ? thin : long;
      kb.setAttribute('x', f2(cx - bw / 2)); kb.setAttribute('y', f2(cy - bh / 2)); kb.setAttribute('width', f2(bw)); kb.setAttribute('height', f2(bh));
      kb.setAttribute('rx', f2(thin / 2));
    }
  }
  placeBar();
}
// the bar above the picture's box (its turned corners' box), in page px, the same size on screen at every zoom; no room
// above it on screen: below the box; pulled back inside the desk sideways
function placeBar() {
  const { x, y, w, h, rot, c } = K.b, z = K.z, bar = K.bar;
  const q = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map((p) => turn(p, c, rot));
  const x0 = Math.min(...q.map((p) => p[0])), y0 = Math.min(...q.map((p) => p[1])), y1 = Math.max(...q.map((p) => p[1]));
  bar.style.left = f2(x0) + 'px'; bar.style.top = f2(y0) + 'px';
  bar.style.transform = `scale(${1 / z}) translateY(calc(-100% - ${GAP}px))`;
  const desk = document.getElementById('desk');
  if (!desk || !bar.isConnected) return;
  const d = desk.getBoundingClientRect();
  let br = bar.getBoundingClientRect();
  if (br.top < d.top + 4) {
    bar.style.top = f2(y1) + 'px'; bar.style.transform = `scale(${1 / z}) translateY(${GAP}px)`;
    br = bar.getBoundingClientRect();
  }
  const M = 8, lo = x0 + (d.left + M - br.left) / z, hi = x0 + (d.right - M - br.right) / z;
  const nx = Math.max(Math.min(x0, hi), lo);
  if (nx !== x0) bar.style.left = f2(nx) + 'px';
}

// ---------------------------------------------------------------- dragging
// a client point in the picture's own frame: page (or sticky) px, turned back by rot, from the box's top-left
function local(cx, cy) {
  const hr = K.host.getBoundingClientRect(), z = view().z || 1, b = K.b;
  const p = turn([(cx - hr.left) / z, (cy - hr.top) / z], b.c, -b.rot);
  return [p[0] - b.x, p[1] - b.y];
}
function down(e) {
  if (!K || K.busy) return;
  const t = e.target.closest && e.target.closest('[data-k]');
  if (!t) return;
  e.preventDefault(); e.stopPropagation();                         // never the desk's: no ink, no pan
  if (K.drag || e.button > 0) return;
  try { t.setPointerCapture(e.pointerId); } catch (_) { /* a synthetic event */ }
  K.drag = { pid: e.pointerId, k: t.dataset.k, p0: local(e.clientX, e.clientY), r0: { ...K.r } };
}
function move(e) {
  if (!K || !K.drag || e.pointerId !== K.drag.pid) return;
  e.stopPropagation(); if (e.cancelable) e.preventDefault();
  const p = local(e.clientX, e.clientY), dr = K.drag;
  setRect(drag(dr.k, dr.r0, p[0] - dr.p0[0], p[1] - dr.p0[1]));
}
function up(e) {
  if (!K || !K.drag || e.pointerId !== K.drag.pid) return;
  e.stopPropagation();
  if (e.type === 'pointercancel') setRect(K.drag.r0);
  K.drag = null;
}
addEventListener('pointermove', move, true);
addEventListener('pointerup', up, true);
addEventListener('pointercancel', up, true);
// the rectangle r0 after a drag of handle k by (dx, dy) in the picture's frame: kept on the picture, never under the minimum
function drag(k, r0, dx, dy) {
  const { w, h } = K.b, mw = Math.min(MIN, w), mh = Math.min(MIN, h), cl = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const r = { ...r0 };
  if (k === 'move') {
    const rw = r0.r - r0.l, rh = r0.b - r0.t;
    r.l = cl(r0.l + dx, 0, w - rw); r.r = r.l + rw; r.t = cl(r0.t + dy, 0, h - rh); r.b = r.t + rh;
    return r;
  }
  if (k.includes('w')) r.l = cl(r0.l + dx, 0, r0.r - mw);
  if (k.includes('e')) r.r = cl(r0.r + dx, r0.l + mw, w);
  if (k.includes('n')) r.t = cl(r0.t + dy, 0, r0.b - mh);
  if (k.includes('s')) r.b = cl(r0.b + dy, r0.t + mh, h);
  return r;
}
function setRect(r) { K.r = { ...r }; draw(); }

// ---------------------------------------------------------------- keys, Back
function keys(e) {
  if (!K) return;
  if (e.target && e.target.closest && e.target.closest('input, textarea, [contenteditable]')) return;
  const k = (e.key || '').toLowerCase();
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (!K.busy) cancelCrop(); }
  else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); doneCrop(); }
  else if ((e.ctrlKey || e.metaKey) && (k === 'z' || k === 'y')) { e.preventDefault(); e.stopPropagation(); }
}
addEventListener('keydown', keys, true);
addEventListener('popstate', () => { if (K && !K.busy) cancelCrop(false); });

// ---------------------------------------------------------------- Done
const same = (a, b) => !!a && !!b && a.path === b.path && +a.x === +b.x && +a.y === +b.y && +a.w === +b.w && +a.h === +b.h && (+a.rot || 0) === (+b.rot || 0);
export async function doneCrop() {
  if (!K || K.busy) return false;
  const me = K, { x, y, w, h, rot, c } = me.b, r = me.r;
  me.busy = true; me.doneB.disabled = true;
  const t0 = performance.now();
  const stay = (msg) => { me.busy = false; me.doneB.disabled = false; if (msg) me.toast(msg, 5000); return false; };
  try {
    if (!me.bmp) {
      const blob = await me.bytes;
      if (K !== me) return false;
      if (!blob) { me.bytes = bytesOf(me.rec.data.path).catch(() => null); return stay('This picture has not downloaded yet'); }
      me.bmp = await createImageBitmap(blob, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
      if (K !== me) return false;
    }
    const bw = me.bmp.width, bh = me.bmp.height, cl = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    // the rectangle in whole pixels of the file
    let sx0 = cl(Math.round(r.l / w * bw), 0, bw - 1), sy0 = cl(Math.round(r.t / h * bh), 0, bh - 1);
    let sx1 = cl(Math.round(r.r / w * bw), sx0 + 1, bw), sy1 = cl(Math.round(r.b / h * bh), sy0 + 1, bh);
    if (sx0 === 0 && sy0 === 0 && sx1 === bw && sy1 === bh) { cancelCrop(); return false; }   // the whole picture: Cancel
    const sw = sx1 - sx0, sh = sy1 - sy0, jpeg = /\.jpe?g$/i.test(me.rec.data.path);
    const cv = document.createElement('canvas');
    cv.width = sw; cv.height = sh;
    cv.getContext('2d').drawImage(me.bmp, sx0, sy0, sw, sh, 0, 0, sw, sh);
    let out = null;
    try { out = await new Promise((ok, no) => cv.toBlob((b) => (b ? ok(b) : no(new Error('no picture'))), jpeg ? 'image/jpeg' : 'image/png', jpeg ? 0.92 : undefined)); }
    catch (err) { console.warn('PenWorks: the cropped picture could not be made', err); }
    cv.width = 0; cv.height = 0;
    if (K !== me) return false;
    const path = out ? await keepPicture(out, jpeg ? 'crop.jpg' : 'crop.png', jpeg) : null;
    if (K !== me) return false;
    if (!path) return stay(out ? IMG_TOO_BIG : 'This picture could not be saved.');
    // the kept part, in page px, from the snapped pixels; its centre turned about the old centre: nothing on the page moves
    const nl = sx0 / bw * w, nr = sx1 / bw * w, nt = sy0 / bh * h, nb = sy1 / bh * h, nw = nr - nl, nh = nb - nt;
    const nc = turn([x + (nl + nr) / 2, y + (nt + nb) / 2], c, rot);
    const nbx = { x: q3(nc[0] - nw / 2), y: q3(nc[1] - nh / 2), w: q3(nw), h: q3(nh), nw: sw, nh: sh };
    const now = strokesOf(me.page).find((s) => s.id === me.id);
    let ok = false;
    if (now && same(now.data, me.rec.data)) ok = setImageCrop(me.page, me.id, me.rec.data.path, path, out, nbx);
    stats.lastMs = performance.now() - t0; stats.lastType = jpeg ? 'jpeg' : 'png';
    if (ok) stats.done++;
    end(true);
    return ok;
  } catch (err) {
    console.warn('PenWorks: the crop could not be finished', err);
    if (K === me) return stay('This picture could not be saved.');
    return false;
  }
}

// ---------------------------------------------------------------- for the checks (window.__pw.crop)
export function cropState() {
  if (!K) return { active: false, ...stats };
  return { active: true, ...stats, page: K.page, id: K.id, rect: { ...K.r }, w: K.b.w, h: K.b.h, rot: K.b.rot, busy: K.busy, z: K.z,
           dragging: !!K.drag, path: K.rec.data.path };
}
export function cropSet(l, t, r, b) {
  if (!K) return false;
  const { w, h } = K.b, cl = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const L = cl(l, 0, w - Math.min(MIN, w)), T = cl(t, 0, h - Math.min(MIN, h));
  setRect({ l: L, t: T, r: cl(r, L + Math.min(MIN, w), w), b: cl(b, T + Math.min(MIN, h), h) });
  return true;
}
