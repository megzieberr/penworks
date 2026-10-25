// PenWorks ink: the stroke model, one SVG layer per page, pen and highlighter drawing, the two
// erasers, hit tests, and the ink operations that join the note's one undo stack (js/app.js).
// A stroke is one record, exactly the strokes table's shape:
//   { id, page_id, seq, kind, style: { colour, width, dash, opacity }, data }
//   pen / highlighter: data = { points: [[x, y], ...] } in page px at zoom 1 (A4 = 794 x 1123)
//   shape (Part B):    data = { type, ...params }; the erasers already remove a shape whole
// Rendering: one <path> per stroke, so every stroke stays crisp at every zoom and can be hit on its own.
// Each page's SVG holds two groups: <g class="hl"> (bottom) and <g class="pen"> (top, pen and shapes).
// Inside .hl there is one <g class="hlo" data-opacity> per opacity used on the page; its paths are fully
// opaque and the group's opacity makes them see-through, so going over a spot again stays one flat colour.
// Storage goes through js/store-local.js only.
// Part B: hold the pen still at the end of a pen stroke and it snaps into a line, arrow, arc, triangle, rect,
// circle or ellipse (SVG primitives); with the pen tool a shape's handles can be grabbed and dragged; the restyle
// tool gives strokes the restyle colour and the pen's (or the highlighter's) width, dash or opacity; rectangle
// select moves, resizes, copies, deletes and (from the tray) recolours or restyles. Every one of these is one
// step on the note's undo stack.
// A held highlighter stroke snaps too (never to an arrow): a shape whose style.opacity is under 1 is a
// highlighter-born shape and lives in the highlighter layer (inHl below is that one rule).
// Shape handles (pw-v4e): with the pen tool, the pen landing within reach of an end point, corner or compass point
// grabs it and drags it, button or no button; anywhere else the pen draws. The pen button changes nothing.
// Arc snap (pw-v4f): an open curve held still snaps into a circular arc, data { type: 'arc', x1, y1, xm, ym, x2, y2 }
// (start, the point half way round, end); its three handles move one point each, the arc is the circle through them.
// Select turns (pw-v4g): a ring above the selection box turns the selection about the box's centre (snapping to
// multiples of 15 degrees within 2.5); an ellipse keeps its turn in data.angle (degrees, absent = 0). A selection
// that is moved, resized or turned comes to the front (fresh seq values, its own order kept); a resize keeps the
// ink's width, only the shape grows or shrinks.

import * as store from './store-local.js';
import { pageAt, pagePoint, view } from './page.js';

// snap: the pen held still this long (ms) at the end of a stroke; ?hold=400 in the address overrides it
export const HOLD_MS = (() => { const v = +new URLSearchParams(location.search).get('hold'); return v >= 100 && v <= 3000 ? v : 500; })();
const SVGNS = 'http://www.w3.org/2000/svg';
export const ERASE_REACH = 6;    // stroke eraser: px on screen around the pen (6 px at zoom 1)
export const AREA_SIZE = 24;     // area eraser: circle diameter, px on screen (24 px at zoom 1)
const MIN_STEP = 0.4;            // page px; closer points than this are dropped while drawing
const HOLD_PX = 4;               // snap: "still" means within 4 px on screen of where the pen settled
const SNAP_MIN = 30;             // snap: a stroke shorter than this (page px) never snaps
const SNAP_ANIM = 150;           // snap: the soft cross-fade, ms
export const GRAB = 12;          // selection corners: px on screen (12 px at zoom 1)
export const HANDLE_REACH = 20;  // shape handles (pen tool): px on screen (20 px at zoom 1), a pen tip needs room
const SEL_BLUE = '#2F4BB8';      // the selection box (the paper is white in both modes)

const P = new Map();             // page id -> { strokes (by seq), byId, svg, hl, pen, hlo (opacity -> group), els (id -> path), w, h }
const boxes = new WeakMap();     // record -> [x0, y0, x1, y1], its points' bounding box
const T = { tool: 'pen', style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 } };
// what restyle hands out: its own colour, and the pen's and the highlighter's current settings (the tray keeps these up to date)
const ST = { pen: { colour: '#000000', width: 2.5, dash: 'solid' }, highlighter: { colour: '#FFC107', width: 18, opacity: 0.4 }, restyle: null };
let doOp = (op) => op.redo();
let G = null;                    // the gesture in progress
let ring = null, hring = null, deskEl = null, deskBox = null;
let SEL = null;                  // the selection: { page, ids, g, chips, z }

const uuid = () => crypto.randomUUID();
const r1 = (v) => Math.round(v * 10) / 10;
const bySeq = (a, b) => a.seq - b.seq;

export function initInk(o) {
  if (o.doOp) doOp = o.doOp;
  deskEl = o.desk || document.getElementById('desk');
  deskEl.addEventListener('pointerleave', hideHandle);
  // the selection's handles and chips keep their size on screen: redraw them when the zoom changes
  const stack = deskEl.querySelector('#stack');
  if (stack) new MutationObserver(() => { if (SEL && SEL.z !== view().z) renderSel(); })
    .observe(stack, { attributes: true, attributeFilter: ['data-zoom', 'style'] });
}
export function setTool(tool, style) {
  if (tool !== T.tool) { clearSelection(); hideHandle(); }
  T.tool = tool; if (style) T.style = { ...style };
}
export function setStyles(pen, highlighter, restyle) { ST.pen = { ...pen }; ST.highlighter = { ...highlighter }; ST.restyle = restyle ? { ...restyle } : null; }
export function tool() { return { tool: T.tool, style: { ...T.style } }; }

// ---------------------------------------------------------------- the model
function data(id) {
  let d = P.get(id);
  if (!d) {
    const strokes = store.load(id).sort(bySeq);
    d = { strokes, byId: new Map(strokes.map((r) => [r.id, r])), svg: null, hl: null, pen: null, hlo: new Map(), els: new Map(), w: 0, h: 0 };
    P.set(id, d);
  }
  return d;
}
export function strokesOf(pageId) { return data(pageId).strokes.slice(); }
export function copyStrokes(pageId) { return JSON.parse(JSON.stringify(data(pageId).strokes)); }

// a shape's outline as a polyline (hit tests now; Part B draws shapes with SVG primitives)
export function outline(rec) {
  const d = rec.data || {};
  if (d.type === 'line' || d.type === 'arrow') return [[d.x1, d.y1], [d.x2, d.y2]];
  if ((d.type === 'rect' || d.type === 'triangle') && d.points && d.points.length) return [...d.points, d.points[0]];
  if (d.type === 'circle' || d.type === 'ellipse') {
    const rx = d.type === 'circle' ? d.r : d.rx, ry = d.type === 'circle' ? d.r : d.ry, out = [];
    const tu = d.type === 'ellipse' ? d.angle || 0 : 0, c = [d.cx, d.cy];
    for (let k = 0; k <= 48; k++) { const a = (k / 48) * 2 * Math.PI; out.push(turn([d.cx + rx * Math.cos(a), d.cy + ry * Math.sin(a)], c, tu)); }
    return out;
  }
  if (d.type === 'arc') {                                          // 48 points from the start to the end
    const g = arcGeom(d);
    if (!g) return [[d.x1, d.y1], [d.xm, d.ym], [d.x2, d.y2]];
    const out = [[d.x1, d.y1]];
    for (let k = 1; k < 47; k++) { const a = g.t1 + (g.sweep * k) / 47; out.push([g.ox + g.r * Math.cos(a), g.oy + g.r * Math.sin(a)]); }
    out.push([d.x2, d.y2]);
    return out;
  }
  return [];
}
// an arc's circle, through its start, middle and end: { ox, oy, r, t1 (the start's angle), sweep (signed, radians:
// plus is the way angles grow on the page, SVG's sweep flag 1) }; null when the three sit in a line (the middle
// under 0.5 px off the chord) or the ends meet
function arcGeom(d) {
  const ax = d.x1, ay = d.y1, bx = d.xm, by = d.ym, cx = d.x2, cy = d.y2, chord = Math.hypot(cx - ax, cy - ay);
  if (!chord || Math.abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / chord < 0.5) return null;
  const D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  const a2 = ax * ax + ay * ay, b2 = bx * bx + by * by, c2 = cx * cx + cy * cy;
  const ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / D, oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / D;
  const t1 = Math.atan2(ay - oy, ax - ox), tm = Math.atan2(by - oy, bx - ox), t2 = Math.atan2(cy - oy, cx - ox);
  const toEnd = nrmA(t2 - t1);
  return { ox, oy, r: Math.hypot(ax - ox, ay - oy), t1, sweep: nrmA(tm - t1) <= toEnd ? toEnd : toEnd - 2 * Math.PI };
}
const nrmA = (t) => ((t % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);   // an angle in [0, 2 pi)
// the point q turned deg degrees about c (plus = clockwise on the page, the way SVG's rotate() turns)
function turn(q, c, deg) {
  if (!deg) return q;
  const t = deg * Math.PI / 180, cs = Math.cos(t), sn = Math.sin(t), x = q[0] - c[0], y = q[1] - c[1];
  return [c[0] + x * cs - y * sn, c[1] + x * sn + y * cs];
}
const nrmDeg = (a) => { const v = ((a % 360) + 540) % 360 - 180; return v === -180 ? 180 : v; };   // degrees in (-180, 180]
const pointsOf = (rec) => (rec.kind === 'shape' ? outline(rec) : ((rec.data && rec.data.points) || []));
function boxOf(rec) {
  let b = boxes.get(rec);
  if (!b) {
    b = [Infinity, Infinity, -Infinity, -Infinity];
    for (const [x, y] of pointsOf(rec)) { if (x < b[0]) b[0] = x; if (y < b[1]) b[1] = y; if (x > b[2]) b[2] = x; if (y > b[3]) b[3] = y; }
    boxes.set(rec, b);
  }
  return b;
}

// ---------------------------------------------------------------- rendering
const f1 = (v) => String(r1(v));
function pathD(pts) {
  const n = pts.length;
  if (!n) return '';
  const p = (q) => f1(q[0]) + ' ' + f1(q[1]);
  if (n === 1) return 'M' + p(pts[0]) + 'h0.01';
  if (n === 2) return 'M' + p(pts[0]) + 'L' + p(pts[1]);
  // smooth: quadratic curves through the midpoints, each point a control point
  let d = 'M' + p(pts[0]);
  for (let i = 1; i < n - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    d += 'Q' + p(a) + ' ' + f1((a[0] + b[0]) / 2) + ' ' + f1((a[1] + b[1]) / 2);
  }
  return d + 'L' + p(pts[n - 1]);
}
function dOf(rec) {
  if (rec.kind !== 'shape') return pathD(pointsOf(rec));
  const o = outline(rec);
  return o.length ? 'M' + o.map((q) => f1(q[0]) + ' ' + f1(q[1])).join('L') : '';
}
export const dashOf = (w) => { const a = f1(Math.max(4, w * 3)); return a + ' ' + a; };
function styleEl(el, rec) {
  const s = rec.style || {}, w = s.width || 2.5;
  el.setAttribute('fill', 'none');
  el.setAttribute('stroke', s.colour || '#000000');
  el.setAttribute('stroke-width', String(w));
  el.setAttribute('stroke-linejoin', 'round');
  el.setAttribute('class', rec.kind);
  if (inHl(rec)) {
    el.setAttribute('stroke-linecap', 'round');             // fully opaque: its .hlo group does the see-through
    el.removeAttribute('stroke-opacity');
  } else {
    el.setAttribute('stroke-linecap', 'round');
    if (s.opacity !== undefined && s.opacity !== 1) el.setAttribute('stroke-opacity', String(s.opacity));
  }
  if (s.dash === 'dashed') el.setAttribute('stroke-dasharray', dashOf(w));
  else el.removeAttribute('stroke-dasharray');
}
// shapes are SVG primitives: line, polygon (rect, triangle), circle, ellipse, path (arc); an arrow is a <g> of its
// line and an open head (the head never dashed, so every arrow ends the same way)
const SHAPE_TAG = { line: 'line', arrow: 'g', rect: 'polygon', triangle: 'polygon', circle: 'circle', ellipse: 'ellipse', arc: 'path' };
function arrowHead(d, w) {
  const dx = d.x2 - d.x1, dy = d.y2 - d.y1, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
  const len = Math.min(L * 0.45, Math.max(14, w * 4)), a = 28 * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  const b1 = [d.x2 - len * (ux * c - uy * s), d.y2 - len * (uy * c + ux * s)];
  const b2 = [d.x2 - len * (ux * c + uy * s), d.y2 - len * (uy * c - ux * s)];
  return 'M' + f1(b1[0]) + ' ' + f1(b1[1]) + 'L' + f1(d.x2) + ' ' + f1(d.y2) + 'L' + f1(b2[0]) + ' ' + f1(b2[1]);
}
function setGeom(el, rec) {
  const d = rec.data, at = (k, v) => el.setAttribute(k, f1(v));
  if (d.type === 'line') { at('x1', d.x1); at('y1', d.y1); at('x2', d.x2); at('y2', d.y2); }
  else if (d.type === 'arrow') {
    const [ln, hd] = el.children;
    for (const k of ['x1', 'y1', 'x2', 'y2']) ln.setAttribute(k, f1(d[k]));
    hd.setAttribute('d', arrowHead(d, (rec.style && rec.style.width) || 2.5));
  } else if (d.type === 'rect' || d.type === 'triangle') el.setAttribute('points', d.points.map((q) => f1(q[0]) + ',' + f1(q[1])).join(' '));
  else if (d.type === 'circle') { at('cx', d.cx); at('cy', d.cy); at('r', d.r); }
  else if (d.type === 'ellipse') {                                 // a turned ellipse: rotate(angle cx cy), none at 0
    at('cx', d.cx); at('cy', d.cy); at('rx', d.rx); at('ry', d.ry);
    if (d.angle) el.setAttribute('transform', `rotate(${f1(d.angle)} ${f1(d.cx)} ${f1(d.cy)})`); else el.removeAttribute('transform');
  }
  else if (d.type === 'arc') {                                     // M start A r r 0 large sweep end; in a line: straight
    const g = arcGeom(d), p = (x, y) => f1(x) + ' ' + f1(y);
    el.setAttribute('d', g
      ? 'M' + p(d.x1, d.y1) + 'A' + f1(g.r) + ' ' + f1(g.r) + ' 0 ' + (Math.abs(g.sweep) > Math.PI ? 1 : 0) + ' ' + (g.sweep > 0 ? 1 : 0) + ' ' + p(d.x2, d.y2)
      : 'M' + p(d.x1, d.y1) + 'L' + p(d.xm, d.ym) + 'L' + p(d.x2, d.y2));
  }
}
function makeEl(rec) {
  const shape = rec.kind === 'shape' && rec.data && SHAPE_TAG[rec.data.type];
  const el = document.createElementNS(SVGNS, shape || 'path');
  el.dataset.id = rec.id;
  styleEl(el, rec);
  if (shape) {
    el.dataset.type = rec.data.type;
    if (rec.data.type === 'arrow') {
      const hd = document.createElementNS(SVGNS, 'path');
      hd.setAttribute('class', 'head'); hd.setAttribute('stroke-dasharray', 'none');
      el.append(document.createElementNS(SVGNS, 'line'), hd);
    }
    setGeom(el, rec);
  } else el.setAttribute('d', dOf(rec));
  return el;
}
// the layer groups: which group a record's path lives in, made on demand. THE one rule: a highlighter stroke,
// or a shape with opacity under 1 (a highlighter-born shape), lives in the highlighter layer
const inHl = (rec) => rec.kind === 'highlighter' || (rec.kind === 'shape' && +((rec.style && rec.style.opacity) ?? 1) < 1);
const opKey = (rec) => String(+((rec.style && rec.style.opacity) ?? 0.4));
const keyOf = (rec) => (inHl(rec) ? 'hl' + opKey(rec) : 'pen');
function hloGroup(d, key) {
  let g = d.hlo.get(key);
  if (!g) {
    g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('class', 'hlo'); g.dataset.opacity = key; g.setAttribute('opacity', key);
    d.hlo.set(key, g);
    const after = [...d.hl.children].find((x) => +x.dataset.opacity > +key);   // ascending opacity
    d.hl.insertBefore(g, after || null);
  }
  return g;
}
function groupFor(d, rec) { return inHl(rec) ? hloGroup(d, opKey(rec)) : d.pen; }
// put a record's path in its group, before the next record (by seq) that shares that group
function place(d, rec, el, idx) {
  const parent = groupFor(d, rec), k = keyOf(rec);
  let next = null;
  for (let j = idx + 1; j < d.strokes.length; j++) {
    const r = d.strokes[j];
    if (keyOf(r) === k) { const e = d.els.get(r.id); if (e && e.parentNode === parent) { next = e; break; } }
  }
  parent.insertBefore(el, next);
}
// take a path out; an opacity group left empty goes too
function unplace(d, el) {
  const g = el.parentNode;
  el.remove();
  if (g && g.classList && g.classList.contains('hlo') && !g.firstChild) { d.hlo.delete(g.dataset.opacity); g.remove(); }
}
function buildLayer(d, w, h) {
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'ink');
  d.hl = document.createElementNS(SVGNS, 'g'); d.hl.setAttribute('class', 'hl');
  d.pen = document.createElementNS(SVGNS, 'g'); d.pen.setAttribute('class', 'pen');
  d.hlo = new Map();
  for (const rec of d.strokes) { const el = makeEl(rec); d.els.set(rec.id, el); groupFor(d, rec).appendChild(el); }
  svg.append(d.hl, d.pen);
  d.svg = svg;
  sizeLayer(d, w, h);
}
function sizeLayer(d, w, h) {
  if (d.w === w && d.h === h) return;
  d.w = w; d.h = h;
  d.svg.setAttribute('width', w); d.svg.setAttribute('height', h);
  d.svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
}

// page.js calls this after it (re)builds the stack: every sheet gets its page's ink layer back
export function attach(sheets) {
  clearSelection();
  for (const el of sheets) {
    const d = data(el.dataset.id), w = parseFloat(el.style.width), h = parseFloat(el.style.height);
    if (!d.svg) buildLayer(d, w, h); else sizeLayer(d, w, h);
    el.appendChild(d.svg);
  }
}

// ---------------------------------------------------------------- changes (every one is saved)
const dirty = new Set();
let saveT = null;
function schedule(id) { dirty.add(id); if (!saveT) saveT = setTimeout(flush, 0); }
export function flush() {
  clearTimeout(saveT); saveT = null;
  for (const id of dirty) { const d = P.get(id); if (d) store.save(id, d.strokes); }
  dirty.clear();
}
addEventListener('pagehide', flush);
document.addEventListener('visibilitychange', () => { if (document.hidden) flush(); });

function apply(pageId, removeIds, adds) {
  const d = data(pageId);
  if (removeIds.length) {
    const rm = new Set(removeIds.filter((id) => d.byId.has(id)));
    if (rm.size) {
      d.strokes = d.strokes.filter((r) => !rm.has(r.id));
      for (const id of rm) { d.byId.delete(id); const el = d.els.get(id); if (el) { unplace(d, el); d.els.delete(id); } }
    }
  }
  for (const rec of adds) {
    if (d.byId.has(rec.id)) continue;
    let lo = 0, hi = d.strokes.length;                     // after every stroke with the same or an earlier seq
    while (lo < hi) { const m = (lo + hi) >> 1; if (d.strokes[m].seq <= rec.seq) lo = m + 1; else hi = m; }
    d.strokes.splice(lo, 0, rec); d.byId.set(rec.id, rec);
    if (d.svg) {
      const el = d.els.get(rec.id) || makeEl(rec);
      d.els.set(rec.id, el);
      place(d, rec, el, lo);
    }
  }
  schedule(pageId);
  if (SEL && SEL.page === pageId) syncSel();          // an undo, redo or move: the box follows its strokes
}

// one undo step: [{ page, removed: [records], added: [records] }]
function changeOp(changes) {
  return {
    pages: changes.map((c) => c.page),
    redo: () => changes.forEach((c) => apply(c.page, c.removed.map((r) => r.id), c.added)),
    undo: () => changes.slice().reverse().forEach((c) => apply(c.page, c.added.map((r) => r.id), c.removed)),
  };
}

// for the page menu (app.js): put records on a page, erase a page, forget a page that is gone for good
export function put(pageId, recs) { apply(pageId, [], recs); }
export function erasePageOp(pageId) {
  const all = data(pageId).strokes.slice();
  return all.length ? changeOp([{ page: pageId, removed: all, added: [] }]) : null;
}
export function forget(pageId) { P.delete(pageId); dirty.delete(pageId); store.clear(pageId); }

// ---------------------------------------------------------------- geometry
function segDist2(px, py, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
  let t = L2 ? ((px - a[0]) * dx + (py - a[1]) * dy) / L2 : 0;
  t = Math.max(0, Math.min(1, t));
  const x = a[0] + t * dx - px, y = a[1] + t * dy - py;
  return x * x + y * y;
}
function near(rec, x, y, reach) {
  const b = boxOf(rec);
  if (x < b[0] - reach || x > b[2] + reach || y < b[1] - reach || y > b[3] + reach) return false;
  const pts = pointsOf(rec), r2 = reach * reach;
  if (pts.length === 1) return (pts[0][0] - x) ** 2 + (pts[0][1] - y) ** 2 <= r2;
  for (let i = 1; i < pts.length; i++) if (segDist2(x, y, pts[i - 1], pts[i]) <= r2) return true;
  return false;
}
// where segment a-b crosses the circle (cx, cy, R): t values strictly inside (0, 1)
function crossings(a, b, cx, cy, R) {
  const dx = b[0] - a[0], dy = b[1] - a[1], fx = a[0] - cx, fy = a[1] - cy;
  const A = dx * dx + dy * dy, B = 2 * (fx * dx + fy * dy), C = fx * fx + fy * fy - R * R;
  const disc = B * B - 4 * A * C;
  if (!A || disc <= 1e-9) return [];
  const s = Math.sqrt(disc);
  return [(-B - s) / (2 * A), (-B + s) / (2 * A)].filter((t) => t > 0 && t < 1);
}
const polyLen = (pts) => { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; };
// cut a polyline with a circle: the runs left outside it, or null when the circle misses it
function cut(pts, cx, cy, R) {
  const inside = (q) => (q[0] - cx) ** 2 + (q[1] - cy) ** 2 < R * R;
  if (pts.length === 1) return inside(pts[0]) ? [] : null;
  const runs = [];
  let changed = false, cur = inside(pts[0]) ? null : [pts[0]];
  if (!cur) changed = true;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    for (const t of crossings(a, b, cx, cy, R)) {
      const q = [r1(a[0] + t * (b[0] - a[0])), r1(a[1] + t * (b[1] - a[1]))];
      if (cur) { cur.push(q); runs.push(cur); cur = null; } else cur = [q];
      changed = true;
    }
    if (inside(b)) { if (cur) { runs.push(cur); cur = null; changed = true; } }
    else if (cur) cur.push(b);
    else { cur = [b]; changed = true; }
  }
  if (cur) runs.push(cur);
  return changed ? runs.filter((r) => r.length > 1 && polyLen(r) >= 1) : null;
}

// ---------------------------------------------------------------- hold-to-snap: which shape is this stroke?
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
function bbox(pts) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of pts) { if (x < b[0]) b[0] = x; if (y < b[1]) b[1] = y; if (x > b[2]) b[2] = x; if (y > b[3]) b[3] = y; }
  return b;
}
// Ramer-Douglas-Peucker: the few points that keep the stroke's shape within eps
function rdp(pts, eps) {
  if (pts.length < 3) return pts.slice();
  const keep = new Uint8Array(pts.length); keep[0] = keep[pts.length - 1] = 1;
  const todo = [[0, pts.length - 1]], e2 = eps * eps;
  while (todo.length) {
    const [i, j] = todo.pop();
    let best = -1, bd = e2;
    for (let k = i + 1; k < j; k++) { const d2 = segDist2(pts[k][0], pts[k][1], pts[i], pts[j]); if (d2 > bd) { bd = d2; best = k; } }
    if (best > 0) { keep[best] = 1; todo.push([i, best], [best, j]); }
  }
  return pts.filter((_, k) => keep[k]);
}
// every point within frac x the chord's length of the chord a-b
function straight(pts, a, b, frac) {
  const L = dist(a, b), lim = (frac * L) ** 2;
  return L > 0 && pts.every((q) => segDist2(q[0], q[1], a, b) <= lim);
}
// a closed polygon's corners: near points merged, nearly straight corners dropped
function corners(poly, size) {
  let v = poly.slice();
  if (v.length > 1 && dist(v[0], v[v.length - 1]) < 1e-6) v.pop();
  const near = 0.12 * size;
  for (let changed = true; changed && v.length > 2;) {
    changed = false;
    for (let i = 0; i < v.length; i++) {
      const j = (i + 1) % v.length;
      if (dist(v[i], v[j]) < near) { v[i] = [(v[i][0] + v[j][0]) / 2, (v[i][1] + v[j][1]) / 2]; v.splice(j, 1); changed = true; break; }
    }
  }
  const turn = (a, b, c) => {
    const a1 = Math.atan2(b[1] - a[1], b[0] - a[0]), a2 = Math.atan2(c[1] - b[1], c[0] - b[0]);
    let t = Math.abs(a2 - a1) % (2 * Math.PI); if (t > Math.PI) t = 2 * Math.PI - t;
    return t * 180 / Math.PI;
  };
  while (v.length > 2) {
    let lo = -1, lt = 30;
    for (let i = 0; i < v.length; i++) { const t = turn(v[(i - 1 + v.length) % v.length], v[i], v[(i + 1) % v.length]); if (t < lt) { lt = t; lo = i; } }
    if (lo < 0) break;
    v.splice(lo, 1);
  }
  return v;
}
// how far the stroke strays from the polygon's sides, at most
function strays(pts, v) {
  let worst = 0;
  for (const q of pts) {
    let m = Infinity;
    for (let i = 0; i < v.length; i++) m = Math.min(m, segDist2(q[0], q[1], v[i], v[(i + 1) % v.length]));
    worst = Math.max(worst, m);
  }
  return Math.sqrt(worst);
}
const rp = (q) => [r1(q[0]), r1(q[1])];
// arc: an open stroke that sits on one circle. The Kasa fit (least squares on x^2 + y^2 + a x + b y + c = 0, the
// points centred on their mean first so the sums stay small): every point within 6% of the size from the circle,
// the radius at most 3 x the size, the end further than 10% of the size from the start, and 25 to 330 degrees swept
// the way the stroke travels (the raw point half way along its length, against the chord, gives that way)
function arcOf(raw, A, Z, size) {
  if (dist(A, Z) <= 0.1 * size) return null;                       // closed: the closed test's
  const n = raw.length;
  let mx = 0, my = 0;
  for (const q of raw) { mx += q[0]; my += q[1]; }
  mx /= n; my /= n;
  let sxx = 0, sxy = 0, syy = 0, sx = 0, sy = 0, sxz = 0, syz = 0, sz = 0;
  for (const q of raw) {
    const x = q[0] - mx, y = q[1] - my, z = x * x + y * y;
    sxx += x * x; sxy += x * y; syy += y * y; sx += x; sy += y; sxz += x * z; syz += y * z; sz += z;
  }
  // the normal equations [sxx sxy sx; sxy syy sy; sx sy n] [a b c] = -[sxz syz sz], by Cramer's rule
  const M = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]], R = [-sxz, -syz, -sz];
  const det3 = (m) => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
    + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const D = det3(M);
  if (!(Math.abs(D) > 1e-12 * n * sxx * syy)) return null;        // all in a line: no circle
  const col = (i) => M.map((row, k) => row.map((v, j) => (j === i ? R[k] : v)));
  const a = det3(col(0)) / D, b = det3(col(1)) / D, c = det3(col(2)) / D;
  const ox = mx - a / 2, oy = my - b / 2, r2 = (a * a + b * b) / 4 - c;
  if (!(r2 > 0)) return null;
  const r = Math.sqrt(r2);
  if (r > 3 * size) return null;                                   // flatter: a line or freehand
  for (const q of raw) if (Math.abs(Math.hypot(q[0] - ox, q[1] - oy) - r) > 0.06 * size) return null;
  const half = polyLen(raw) / 2;
  let walked = 0, mid = raw[n - 1];
  for (let i = 1; i < n; i++) { walked += dist(raw[i - 1], raw[i]); if (walked >= half) { mid = raw[i]; break; } }
  const cross = (mid[0] - A[0]) * (Z[1] - A[1]) - (mid[1] - A[1]) * (Z[0] - A[0]);
  if (!cross) return null;
  const t1 = Math.atan2(A[1] - oy, A[0] - ox), t2 = Math.atan2(Z[1] - oy, Z[0] - ox);
  const sweep = cross > 0 ? nrmA(t2 - t1) : -nrmA(t1 - t2), deg = (Math.abs(sweep) * 180) / Math.PI;
  if (deg < 25 || deg > 330) return null;
  const on = (t) => [r1(ox + r * Math.cos(t)), r1(oy + r * Math.sin(t))];  // the ends and middle ON the fitted circle
  const [x1, y1] = on(t1), [xm, ym] = on(t1 + sweep / 2), [x2, y2] = on(t2);
  return { type: 'arc', x1, y1, xm, ym, x2, y2 };
}
// in this order: arrow, line, arc, then closed: triangle, rect, circle or ellipse; null = stays freehand
export function classify(raw) {
  if (!raw || raw.length < 3 || polyLen(raw) < SNAP_MIN) return null;
  const b = bbox(raw), W = b[2] - b[0], H = b[3] - b[1], size = Math.hypot(W, H);
  if (size < 10) return null;
  const pts = rdp(raw, Math.max(0.75, 0.02 * size)), A = raw[0], Z = raw[raw.length - 1];
  // arrow: a straight shaft to the tip (the point farthest from the start), then a short tail that comes back
  // on both sides of the shaft (the V of the head)
  let ti = 0, shaft = 0;
  raw.forEach((q, i) => { const dd = dist(A, q); if (dd > shaft) { shaft = dd; ti = i; } });
  if (ti < raw.length - 1 && shaft >= SNAP_MIN) {
    const tip = raw[ti], tail = raw.slice(ti), tl = polyLen(tail);
    if (tl >= 0.08 * shaft && tl <= 0.9 * shaft && straight(raw.slice(0, ti + 1), A, tip, 0.06)) {
      const ux = (tip[0] - A[0]) / shaft, uy = (tip[1] - A[1]) / shaft;
      let left = 0, right = 0, backMax = 0;
      for (const q of tail) {
        const qx = q[0] - tip[0], qy = q[1] - tip[1], lat = ux * qy - uy * qx, along = ux * qx + uy * qy;
        left = Math.max(left, lat); right = Math.max(right, -lat); backMax = Math.max(backMax, -along);
      }
      const need = Math.max(3, 0.04 * shaft);
      if (left >= need && right >= need && backMax >= need && backMax <= 0.6 * shaft) {
        return { type: 'arrow', x1: r1(A[0]), y1: r1(A[1]), x2: r1(tip[0]), y2: r1(tip[1]) };
      }
    }
  }
  // line: every point close to the chord
  if (straight(raw, A, Z, 0.06)) return { type: 'line', x1: r1(A[0]), y1: r1(A[1]), x2: r1(Z[0]), y2: r1(Z[1]) };
  // arc: open, and on one circle (arcOf above)
  const arc = arcOf(raw, A, Z, size);
  if (arc) return arc;
  // closed: the end (or, for an overshoot, the point nearest the start in the last 30%) within 10% of the size
  let ci = raw.length - 1, cd = Infinity;
  for (let i = Math.floor(raw.length * 0.7); i < raw.length; i++) { const dd = dist(A, raw[i]); if (dd < cd) { cd = dd; ci = i; } }
  if (cd > 0.1 * size) return null;
  const ring = raw.slice(0, ci + 1);
  const v = corners(rdp(ring, Math.max(0.75, 0.02 * size)).concat([A]), size);
  if (v.length === 3 && strays(ring, v) <= 0.07 * size) return { type: 'triangle', points: v.map(rp) };
  if (v.length === 4 && strays(ring, v) <= 0.07 * size) {
    const axis = v.every((q, i) => {
      const n = v[(i + 1) % 4], a = Math.abs(Math.atan2(n[1] - q[1], n[0] - q[0]) * 180 / Math.PI) % 90;
      return a <= 15 || a >= 75;
    });
    if (axis) {                                                    // within 15 degrees of square: straighten it
      const xs = v.map((q) => q[0]).sort((m, n) => m - n), ys = v.map((q) => q[1]).sort((m, n) => m - n);
      const l = (xs[0] + xs[1]) / 2, r = (xs[2] + xs[3]) / 2, t = (ys[0] + ys[1]) / 2, bt = (ys[2] + ys[3]) / 2;
      return { type: 'rect', points: [[l, t], [r, t], [r, bt], [l, bt]].map(rp) };
    }
    return { type: 'rect', points: v.map(rp) };                    // turned: the 4 corners as drawn
  }
  // circle or ellipse: an upright ellipse through the box; every point's distance from the centre (measured
  // on that ellipse, so a round one is a circle) within 15% of the mean
  const rb = bbox(ring), cx = (rb[0] + rb[2]) / 2, cy = (rb[1] + rb[3]) / 2, rx = (rb[2] - rb[0]) / 2, ry = (rb[3] - rb[1]) / 2;
  if (rx < 3 || ry < 3) return null;
  const nd = ring.map((q) => Math.hypot((q[0] - cx) / rx, (q[1] - cy) / ry)), m = nd.reduce((s, x) => s + x, 0) / nd.length;
  if (!nd.every((x) => Math.abs(x - m) <= 0.15 * m)) return null;
  const RX = rx * m, RY = ry * m;
  if (Math.abs(RX - RY) / Math.max(RX, RY) > 0.2) return { type: 'ellipse', cx: r1(cx), cy: r1(cy), rx: r1(RX), ry: r1(RY) };
  return { type: 'circle', cx: r1(cx), cy: r1(cy), r: r1((RX + RY) / 2) };
}

// ---------------------------------------------------------------- shape handles (grab with the pen tool)
export function handles(rec) {
  const d = rec.data || {};
  if (d.type === 'line' || d.type === 'arrow') return [[d.x1, d.y1], [d.x2, d.y2]];
  if (d.type === 'rect' || d.type === 'triangle') return d.points.map((q) => [q[0], q[1]]);
  if (d.type === 'circle' || d.type === 'ellipse') {
    const rx = d.type === 'circle' ? d.r : d.rx, ry = d.type === 'circle' ? d.r : d.ry, c = [d.cx, d.cy];
    const tu = d.type === 'ellipse' ? d.angle || 0 : 0;                                     // a turned ellipse: turned too
    return [[d.cx, d.cy - ry], [d.cx + rx, d.cy], [d.cx, d.cy + ry], [d.cx - rx, d.cy]].map((q) => turn(q, c, tu));   // N, E, S, W
  }
  if (d.type === 'arc') return [[d.x1, d.y1], [d.xm, d.ym], [d.x2, d.y2]];                  // start, middle, end
  return [];
}
// the handle nearest (x, y) on page `id`, within reach: { rec, h, at }
function handleAt(id, x, y, reach) {
  let best = null, bd = reach;
  for (const r of data(id).strokes) {
    if (r.kind !== 'shape') continue;
    handles(r).forEach((q, h) => { const dd = Math.hypot(q[0] - x, q[1] - y); if (dd <= bd) { bd = dd; best = { rec: r, h, at: q }; } });
  }
  return best;
}
// the shape with handle h dragged to (x, y)
function dragHandle(rec, h, x, y) {
  const d = { ...rec.data };
  if (d.type === 'line' || d.type === 'arrow') { if (h === 0) { d.x1 = r1(x); d.y1 = r1(y); } else { d.x2 = r1(x); d.y2 = r1(y); } }
  else if (d.type === 'triangle') d.points = d.points.map((q, k) => (k === h ? [r1(x), r1(y)] : q));
  else if (d.type === 'rect') {
    const p = d.points, upright = p.every((q, k) => { const n = p[(k + 1) % 4]; return Math.abs(q[0] - n[0]) < 0.5 || Math.abs(q[1] - n[1]) < 0.5; });
    if (upright) {                                                 // an upright rect stays upright: the opposite corner holds
      const o = p[(h + 2) % 4];
      d.points = p.map((q, k) => (k === h ? [r1(x), r1(y)] : k === (h + 2) % 4 ? q
        : (Math.abs(q[0] - o[0]) < 0.5 ? [q[0], r1(y)] : [r1(x), q[1]])));
    } else d.points = p.map((q, k) => (k === h ? [r1(x), r1(y)] : q));
  } else if (d.type === 'circle') d.r = r1(Math.max(2, Math.hypot(x - d.cx, y - d.cy)));
  else if (d.type === 'ellipse') {                                 // the centre holds; N and S set the height, E and W the width
    const [lx, ly] = turn([x, y], [d.cx, d.cy], -(d.angle || 0));   // a turned ellipse: in its own frame
    if (h % 2) d.rx = r1(Math.max(2, Math.abs(lx - d.cx))); else d.ry = r1(Math.max(2, Math.abs(ly - d.cy)));
  } else if (d.type === 'arc') {                                   // only that point moves: the arc is the circle through the three
    const k = ['1', 'm', '2'][h];
    d['x' + k] = r1(x); d['y' + k] = r1(y);
  }
  return { ...rec, data: d };
}
function showHandle(cx, cy) {
  if (!hring) { hring = document.createElement('div'); hring.id = 'handleRing'; deskEl.appendChild(hring); }
  const r = deskEl.getBoundingClientRect();
  hring.hidden = false;
  hring.style.transform = `translate(${cx - r.left}px, ${cy - r.top}px)`;
}
function hideHandle() { if (hring) hring.hidden = true; }
// the S Pen's side button (the barrel button) or the right mouse button: bit 2 in buttons, button 2 on a press
const barrel = (e) => !!(e.buttons & 2) || e.button === 2;
// the pen hovering (or a mouse moving), button or not, with the pen tool: a small ring on a handle within reach,
// meaning "a touch here grabs this point"; out of reach, no ring
function hover(e) {
  if (T.tool !== 'pen' || G) { hideHandle(); return; }
  const at = pageAt(e.clientX, e.clientY), z = view().z;
  const h = at && handleAt(at.id, at.x, at.y, HANDLE_REACH / z);
  if (!h) { hideHandle(); return; }
  showHandle(e.clientX + (h.at[0] - at.x) * z, e.clientY + (h.at[1] - at.y) * z);
}

// ---------------------------------------------------------------- moving, scaling and turning records (selection)
// f maps a point; s is the scale (circle and ellipse radii follow it, the ink's width never does); rot is the
// turn in degrees, added to an ellipse's own angle (every other shape turns through its points)
function xform(rec, f, s, rot) {
  const d = rec.data, P = (q) => rp(f(q));
  let nd;
  if (rec.kind !== 'shape') nd = { ...d, points: d.points.map(P) };
  else if (d.type === 'line' || d.type === 'arrow') { const a = P([d.x1, d.y1]), b = P([d.x2, d.y2]); nd = { ...d, x1: a[0], y1: a[1], x2: b[0], y2: b[1] }; }
  else if (d.type === 'rect' || d.type === 'triangle') nd = { ...d, points: d.points.map(P) };
  else if (d.type === 'arc') {
    const a = P([d.x1, d.y1]), m = P([d.xm, d.ym]), z = P([d.x2, d.y2]);
    nd = { ...d, x1: a[0], y1: a[1], xm: m[0], ym: m[1], x2: z[0], y2: z[1] };
  } else if (d.type === 'circle') { const c = P([d.cx, d.cy]); nd = { ...d, cx: c[0], cy: c[1], r: r1(d.r * s) }; }
  else if (d.type === 'ellipse') {
    const c = P([d.cx, d.cy]);
    nd = { ...d, cx: c[0], cy: c[1], rx: r1(d.rx * s), ry: r1(d.ry * s) };
    if (rot) { const a = r1(nrmDeg((d.angle || 0) + rot)); if (a) nd.angle = a; else delete nd.angle; }
  } else nd = { ...d };
  return { ...rec, style: { ...rec.style }, data: nd };
}
// what a selection gesture does to a point: [f, s, rot] for a move, a resize or a turn
function selXf(g) {
  if (g.kind === 'smove') { const { dx, dy } = g; return [(q) => [q[0] + dx, q[1] + dy], 1, 0]; }
  if (g.kind === 'sresize') { const { o, s } = g; return [(q) => [o[0] + (q[0] - o[0]) * s, o[1] + (q[1] - o[1]) * s], s, 0]; }
  const { c, a } = g;
  return [(q) => turn(q, c, a), 1, a];
}

// ---------------------------------------------------------------- the selection: dashed box, corners, Copy and Delete
const selRecs = () => { const d = data(SEL.page); return [...SEL.ids].map((id) => d.byId.get(id)).filter(Boolean); };
function selBox(recs) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const r of recs) {
    const q = boxOf(r), w = (r.style.width || 0) / 2;
    b[0] = Math.min(b[0], q[0] - w); b[1] = Math.min(b[1], q[1] - w); b[2] = Math.max(b[2], q[2] + w); b[3] = Math.max(b[3], q[3] + w);
  }
  return b;
}
const selCorners = (b) => [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
export function clearSelection() {
  if (!SEL) return;
  SEL.g.remove(); SEL.chips.remove();
  SEL = null;
}
export function selection() { return SEL ? { page: SEL.page, ids: [...SEL.ids], box: selBox(selRecs()) } : null; }
function setAttrs(el, at) { for (const k in at) el.setAttribute(k, typeof at[k] === 'number' ? f1(at[k]) : at[k]); }
function renderSel(t) {                          // t: a live transform while dragging the selection
  const d = data(SEL.page), z = view().z, b = selBox(selRecs());
  SEL.z = z;
  if (!SEL.g.parentNode) d.svg.appendChild(SEL.g);
  if (!SEL.chips.parentNode) d.svg.parentNode.appendChild(SEL.chips);
  const pad = 4 / z, x0 = b[0] - pad, y0 = b[1] - pad, x1 = b[2] + pad, y1 = b[3] + pad;
  SEL.g.textContent = '';
  const box = document.createElementNS(SVGNS, 'rect');
  setAttrs(box, { class: 'selbox', x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: 'none', stroke: SEL_BLUE,
    'stroke-width': 1.5 / z, 'stroke-dasharray': f1(6 / z) + ' ' + f1(4 / z) });
  SEL.g.appendChild(box);
  selCorners([x0, y0, x1, y1]).forEach((q, k) => {
    const c = document.createElementNS(SVGNS, 'circle');
    setAttrs(c, { class: 'selh', 'data-corner': String(k), cx: q[0], cy: q[1], r: 6 / z, fill: '#FFFFFF', stroke: SEL_BLUE, 'stroke-width': 1.5 / z });
    SEL.g.appendChild(c);
  });
  // the turn handle: a ring 28 px (on screen) above the top edge's middle, on a thin stem
  const cx = (x0 + x1) / 2, ry = y0 - 28 / z;
  const stem = document.createElementNS(SVGNS, 'line');
  setAttrs(stem, { class: 'selstem', x1: cx, y1: y0, x2: cx, y2: ry + 6 / z, stroke: SEL_BLUE, 'stroke-width': 1.2 / z });
  const knob = document.createElementNS(SVGNS, 'circle');
  setAttrs(knob, { class: 'selrot', cx, cy: ry, r: 6 / z, fill: '#FFFFFF', stroke: SEL_BLUE, 'stroke-width': 1.5 / z });
  SEL.g.append(stem, knob);
  SEL.rot = [cx, ry];
  if (t) SEL.g.setAttribute('transform', t); else SEL.g.removeAttribute('transform');
  SEL.box = [x0, y0, x1, y1];
  placeChips(t ? SEL.live : null);
}
function placeChips(m) {                         // m: [s, ox, oy, dx, dy] while dragging, so the chips ride along
  let [x0, y0] = SEL.box, rx = SEL.rot ? SEL.rot[0] : -Infinity;
  if (m) { const [s, ox, oy, dx, dy] = m; x0 = ox + (x0 - ox) * s + dx; y0 = oy + (y0 - oy) * s + dy; rx = ox + (rx - ox) * s + dx; }
  const c = SEL.chips, gap = 14 / SEL.z;
  if (x0 + c.offsetWidth / SEL.z > rx - gap) x0 = rx + gap;      // they would cover the turn ring: they start just right of it
  c.style.left = f1(x0) + 'px'; c.style.top = f1(y0) + 'px';
  c.style.transform = `scale(${1 / SEL.z}) translateY(calc(-100% - 8px))`;
}
function syncSel() {
  const d = data(SEL.page);
  for (const id of [...SEL.ids]) if (!d.byId.has(id)) SEL.ids.delete(id);
  if (!SEL.ids.size || !d.svg) { clearSelection(); return; }
  renderSel();
}
function makeSel(page, ids) {
  clearSelection();
  const g = document.createElementNS(SVGNS, 'g'); g.setAttribute('class', 'sel');
  const chips = document.createElement('div'); chips.className = 'selChips';
  const chip = (act, label, fn) => {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'chip'; btn.dataset.act = act; btn.textContent = label;
    btn.addEventListener('click', (e) => { e.stopPropagation(); fn(); });
    chips.appendChild(btn);
  };
  chip('copy', 'Copy', copySel); chip('delete', 'Delete', deleteSel);
  SEL = { page, ids: new Set(ids), g, chips, z: 0, box: null, rot: null, live: null };
  renderSel();
}
function copySel() {
  if (!SEL) return;
  const page = SEL.page, now = Date.now();
  const copies = selRecs().sort(bySeq).map((r, k) => ({ ...xform(r, (q) => [q[0] + 24, q[1] + 24], 1), id: uuid(), seq: now + k }));
  doOp(changeOp([{ page, removed: [], added: copies }]));
  if (SEL && SEL.page === page) { SEL.ids = new Set(copies.map((r) => r.id)); renderSel(); }
  else makeSel(page, copies.map((r) => r.id));
}
function deleteSel() {
  if (!SEL) return;
  const page = SEL.page, recs = selRecs();
  clearSelection();
  if (recs.length) doOp(changeOp([{ page, removed: recs, added: [] }]));
}
// does segment a-b touch the box B (inside it or crossing an edge)? Liang-Barsky clipping
function segInBox(a, b, B) {
  let t0 = 0, t1 = 1;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  for (const [p, q] of [[-dx, a[0] - B[0]], [dx, B[2] - a[0]], [-dy, a[1] - B[1]], [dy, B[3] - a[1]]]) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return true;
}
// strokes that touch the box b anywhere: a point inside, or a segment (of the stroke, or of a shape's outline)
// crossing its edge; the ink's half width counts as part of the stroke
function inBox(id, b) {
  const out = [];
  for (const r of data(id).strokes) {
    const q = boxOf(r), w = Math.max(1, (r.style.width || 0) / 2), B = [b[0] - w, b[1] - w, b[2] + w, b[3] + w];
    if (q[2] < B[0] || q[0] > B[2] || q[3] < B[1] || q[1] > B[3]) continue;   // nowhere near
    const pts = pointsOf(r);
    let hit = pts.some(([x, y]) => x >= B[0] && x <= B[2] && y >= B[1] && y <= B[3]);
    for (let i = 1; !hit && i < pts.length; i++) hit = segInBox(pts[i - 1], pts[i], B);
    if (hit) out.push(r.id);
  }
  return out;
}
// the tray's colour tap and Restyle tap while a selection exists: one undo step each, the selection stays
export function hasSelection() { return !!SEL; }
function changeSel(fn) {
  if (!SEL) return false;
  const olds = [], news = [];
  for (const r of selRecs()) { const n = fn(r); if (n) { olds.push(r); news.push(n); } }
  if (olds.length) doOp(changeOp([{ page: SEL.page, removed: olds, added: news }]));
  return true;
}
export function recolourSelection(c) {          // colour only: width, dash, opacity and geometry stay
  return changeSel((r) => (same((r.style || {}).colour, c) ? null : { ...r, style: { ...r.style, colour: c } }));
}
export function restyleSelection() { return changeSel(restyled); }   // the full restyle rule

// ---------------------------------------------------------------- restyle: its own colour, the matching tool's width, dash, opacity
function restyled(r) {
  const p = ST.pen, h = ST.highlighter, hl = inHl(r), c = ST.restyle && ST.restyle.colour;
  const style = hl                                                 // a highlight (stroke or shape) stays a highlight
    ? { colour: c || h.colour, width: h.width, dash: 'solid', opacity: h.opacity }
    : { colour: c || p.colour, width: p.width, dash: p.dash || 'solid', opacity: 1 };
  const s = r.style || {};
  if (same(s.colour, style.colour) && +s.width === +style.width && (s.dash || 'solid') === style.dash && +(s.opacity ?? 1) === +style.opacity) return null;
  return { ...r, style };
}
const same = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();

// ---------------------------------------------------------------- the pen on the page (page.js hands events here)
function showRing(cx, cy) {
  if (!ring) {
    ring = document.createElement('div'); ring.id = 'eraserRing';
    ring.style.width = ring.style.height = AREA_SIZE + 'px';
    deskEl.appendChild(ring);
  }
  ring.hidden = false;
  ring.style.transform = `translate(${cx - deskBox.left - AREA_SIZE / 2}px, ${cy - deskBox.top - AREA_SIZE / 2}px)`;
}
function hideRing() { if (ring) ring.hidden = true; }

function note(page, removed, added) {
  let c = G.changes.get(page);
  if (!c) { c = { removed: new Map(), added: new Map() }; G.changes.set(page, c); }
  for (const r of removed) { if (c.added.has(r.id)) c.added.delete(r.id); else c.removed.set(r.id, r); }
  for (const r of added) c.added.set(r.id, r);
}
function eraseHere(cx, cy) {
  const at = pageAt(cx, cy);
  if (!at) return;
  const d = data(at.id);
  if (G.kind === 'eraser') {
    const reach = ERASE_REACH / G.z;
    const hits = d.strokes.filter((r) => near(r, at.x, at.y, reach + (r.style.width || 0) / 2));
    if (!hits.length) return;
    note(at.id, hits, []);
    apply(at.id, hits.map((r) => r.id), []);
    return;
  }
  if (G.kind === 'restyle') {                                      // each stroke it touches, once per drag
    const reach = ERASE_REACH / G.z, olds = [], news = [];
    for (const r of d.strokes) {
      if (G.done.has(r.id) || !near(r, at.x, at.y, reach + (r.style.width || 0) / 2)) continue;
      G.done.add(r.id);
      const n = restyled(r);
      if (n) { olds.push(r); news.push(n); }
    }
    if (!olds.length) return;
    note(at.id, olds, news);
    apply(at.id, olds.map((r) => r.id), news);
    return;
  }
  const rad = AREA_SIZE / 2 / G.z, gone = [], pieces = [];
  for (const r of d.strokes) {
    const R = rad + (r.style.width || 0) / 2;
    if (r.kind !== 'pen' && r.kind !== 'highlighter') {          // shapes (and later kinds) go whole
      if (near(r, at.x, at.y, R)) gone.push(r);
      continue;
    }
    const b = boxOf(r);
    if (at.x < b[0] - R || at.x > b[2] + R || at.y < b[1] - R || at.y > b[3] + R) continue;
    const runs = cut(r.data.points, at.x, at.y, R);
    if (!runs) continue;
    gone.push(r);
    for (const pts of runs) pieces.push({ ...r, id: uuid(), style: { ...r.style }, data: { ...r.data, points: pts } });
  }
  if (!gone.length) return;
  note(at.id, gone, pieces);
  apply(at.id, gone.map((r) => r.id), pieces);
}
function eraseTo(cx, cy) {
  const step = G.kind === 'area' ? AREA_SIZE / 4 : 3;               // stroke eraser and restyle: every 3 px
  const [lx, ly] = G.last || [cx, cy], n = Math.max(1, Math.ceil(Math.hypot(cx - lx, cy - ly) / step));
  for (let k = G.last ? 1 : n; k <= n; k++) eraseHere(lx + (cx - lx) * k / n, ly + (cy - ly) * k / n);
  G.last = [cx, cy];
  if (G.kind === 'area') showRing(cx, cy);
}

// the pen held still: rearm the snap timer whenever the pen settles somewhere new
function armHold(cx, cy) {
  clearTimeout(G.holdT);
  G.anchor = [cx, cy];
  G.holdT = setTimeout(snapNow, HOLD_MS);
}
function snapNow() {
  const g = G;
  if (!g || g.kind !== 'draw') return;
  let shape = classify(g.rec.data.points);
  if (!shape) return;                                              // stays freehand
  const hl = g.rec.kind === 'highlighter';
  if (hl && shape.type === 'arrow') shape = { type: 'line', x1: shape.x1, y1: shape.y1, x2: shape.x2, y2: shape.y2 };   // no highlighter arrows
  // a highlighter shape keeps the highlighter's look (opacity under 1: it stays in its .hlo group)
  const style = hl ? { colour: g.rec.style.colour, width: g.rec.style.width, dash: 'solid', opacity: g.rec.style.opacity } : g.rec.style;
  const d = data(g.page), rec = { ...g.rec, kind: 'shape', style, data: shape }, el = makeEl(rec);
  g.el.after(el);
  const old = g.el;                                                // the soft cross-fade, then the freehand goes
  try {
    old.animate([{ opacity: 1 }, { opacity: 0 }], { duration: SNAP_ANIM, easing: 'ease-out', fill: 'forwards' });
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: SNAP_ANIM, easing: 'ease-out' });
  } catch (_) { /* no animations: it just swaps */ }
  setTimeout(() => old.remove(), SNAP_ANIM);
  G = { kind: 'snapped', page: g.page, rec, el, d };
}

function down(e) {
  if (e.button === 2 && T.tool !== 'pen') return false;            // the right button / pen button: only the pen tool uses it
  const at = pageAt(e.clientX, e.clientY);
  if (!at) { if (T.tool === 'select') clearSelection(); return false; }
  const d = data(at.id);
  if (!d.svg) return false;
  hideHandle();
  const z = view().z;
  if (T.tool === 'pen') {                                          // within reach of a shape handle: grab it, button or not
    const h = handleAt(at.id, at.x, at.y, HANDLE_REACH / z);
    if (h) {
      G = { kind: 'grab', page: at.id, index: at.index, rec: h.rec, h: h.h, el: d.els.get(h.rec.id), now: h.rec, z,
            off: [h.at[0] - at.x, h.at[1] - at.y] };                   // the handle keeps its offset from the pen: no jump
      showHandle(e.clientX + (h.at[0] - at.x) * z, e.clientY + (h.at[1] - at.y) * z);
      return true;
    }
    if (barrel(e)) return false;                                   // the button away from any handle: a harmless miss
  }                                                                // anywhere else the pen draws
  if (T.tool === 'pen' || T.tool === 'highlighter') {
    const s = T.style;
    const style = T.tool === 'pen'
      ? { colour: s.colour, width: s.width, dash: s.dash || 'solid', opacity: 1 }
      : { colour: s.colour, width: s.width, dash: 'solid', opacity: s.opacity };
    const rec = { id: uuid(), page_id: at.id, seq: 0, kind: T.tool, style, data: { points: [[r1(at.x), r1(at.y)]] } };
    const el = makeEl(rec);
    groupFor(d, rec).appendChild(el);                              // newest, so last in its group
    G = { kind: 'draw', index: at.index, page: at.id, rec, el, holdT: 0, anchor: null };
    armHold(e.clientX, e.clientY);                                 // pen and highlighter both snap when held
    return true;
  }
  if (T.tool === 'eraser' || T.tool === 'area' || T.tool === 'restyle') {
    deskBox = deskEl.getBoundingClientRect();
    G = { kind: T.tool, z, changes: new Map(), last: null, done: new Set() };
    eraseTo(e.clientX, e.clientY);
    return true;
  }
  if (T.tool === 'select') {
    if (SEL && SEL.page === at.id) {
      const b = SEL.box, reach = GRAB / z;
      if (SEL.rot && Math.hypot(SEL.rot[0] - at.x, SEL.rot[1] - at.y) <= reach) {   // the ring: turn about the box's centre
        const c = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
        G = { kind: 'srotate', index: at.index, page: at.id, c, a0: Math.atan2(at.y - c[1], at.x - c[0]), a: 0, recs: selRecs() };
        return true;
      }
      const k = selCorners(b).findIndex((q) => Math.hypot(q[0] - at.x, q[1] - at.y) <= reach);
      if (k >= 0) {                                                // a corner: scale about the opposite one
        const o = selCorners(b)[(k + 2) % 4], c = selCorners(b)[k];
        G = { kind: 'sresize', index: at.index, page: at.id, o, c, s: 1, recs: selRecs() };
        return true;
      }
      if (at.x >= b[0] && at.x <= b[2] && at.y >= b[1] && at.y <= b[3]) {   // inside: move
        G = { kind: 'smove', index: at.index, page: at.id, p0: [at.x, at.y], dx: 0, dy: 0, recs: selRecs() };
        return true;
      }
    }
    clearSelection();                                              // outside (or another page): a new box
    const band = document.createElementNS(SVGNS, 'rect');
    setAttrs(band, { class: 'selband', x: at.x, y: at.y, width: 0, height: 0, fill: 'rgba(47,75,184,.06)', stroke: SEL_BLUE,
      'stroke-width': 1.2 / z, 'stroke-dasharray': f1(5 / z) + ' ' + f1(4 / z) });
    d.svg.appendChild(band);
    G = { kind: 'box', index: at.index, page: at.id, p0: [at.x, at.y], p1: [at.x, at.y], band, z };
    return true;
  }
  return false;
}
// the live preview while the selection is dragged: each selected path is redrawn from its record put through the
// gesture (no transform on the ink, so its width never changes); the records change on lift. The box and its
// handles ride a transform; the chips ride a move or a resize and hide during a turn
function redraw(el, rec) { if (rec.kind === 'shape') setGeom(el, rec); else el.setAttribute('d', dOf(rec)); }
function liveSel(g) {
  const d = data(g.page), [f, s, rot] = selXf(g);
  for (const r of g.recs) { const el = d.els.get(r.id); if (el) redraw(el, xform(r, f, s, rot)); }
  if (g.kind === 'srotate') {
    SEL.live = null;
    SEL.g.setAttribute('transform', `rotate(${f1(g.a)} ${f1(g.c[0])} ${f1(g.c[1])})`);
    SEL.chips.style.visibility = 'hidden';
    return;
  }
  const ox = g.kind === 'sresize' ? g.o[0] : 0, oy = g.kind === 'sresize' ? g.o[1] : 0, dx = g.dx || 0, dy = g.dy || 0;
  SEL.live = [s, ox, oy, dx, dy];
  SEL.g.setAttribute('transform', `matrix(${s} 0 0 ${s} ${ox * (1 - s) + dx} ${oy * (1 - s) + dy})`);
  placeChips(SEL.live);
}
function unliveSel(g) {
  const d = data(g.page);
  for (const r of g.recs) { const el = d.els.get(r.id); if (el) redraw(el, r); }
  if (SEL) { SEL.live = null; SEL.g.removeAttribute('transform'); SEL.chips.style.visibility = ''; placeChips(null); }
}
function move(events) {
  if (!G) return;
  const ev = events[events.length - 1];
  if (G.kind === 'draw') {
    const pts = G.rec.data.points;
    for (const e of events) {
      const [x, y] = pagePoint(G.index, e.clientX, e.clientY), l = pts[pts.length - 1];
      if (Math.hypot(x - l[0], y - l[1]) >= MIN_STEP) pts.push([r1(x), r1(y)]);
      if (G.anchor && Math.hypot(e.clientX - G.anchor[0], e.clientY - G.anchor[1]) > HOLD_PX) armHold(e.clientX, e.clientY);
    }
    G.el.setAttribute('d', pathD(pts));
    return;
  }
  if (G.kind === 'snapped') return;                                // a snapped shape stays put until the pen lifts
  if (G.kind === 'grab') {
    const [x, y] = pagePoint(G.index, ev.clientX, ev.clientY);
    G.now = dragHandle(G.rec, G.h, x + G.off[0], y + G.off[1]);
    if (G.el) setGeom(G.el, G.now);
    showHandle(ev.clientX + G.off[0] * G.z, ev.clientY + G.off[1] * G.z);
    return;
  }
  if (G.kind === 'box') {
    const [x, y] = pagePoint(G.index, ev.clientX, ev.clientY);
    G.p1 = [x, y];
    setAttrs(G.band, { x: Math.min(G.p0[0], x), y: Math.min(G.p0[1], y), width: Math.abs(x - G.p0[0]), height: Math.abs(y - G.p0[1]) });
    return;
  }
  if (G.kind === 'smove') {
    const [x, y] = pagePoint(G.index, ev.clientX, ev.clientY);
    G.dx = x - G.p0[0]; G.dy = y - G.p0[1];
    liveSel(G);
    return;
  }
  if (G.kind === 'srotate') {                                      // the pen's angle about the centre, less where it started
    const [x, y] = pagePoint(G.index, ev.clientX, ev.clientY), c = G.c;
    let a = nrmDeg((Math.atan2(y - c[1], x - c[0]) - G.a0) * 180 / Math.PI);
    const n = Math.round(a / 15) * 15;
    if (Math.abs(a - n) <= 2.5) a = n;                             // near a multiple of 15: exactly that
    G.a = nrmDeg(r1(a)) || 0;
    liveSel(G);
    return;
  }
  if (G.kind === 'sresize') {
    const [x, y] = pagePoint(G.index, ev.clientX, ev.clientY), { o, c } = G;
    const vx = c[0] - o[0], vy = c[1] - o[1], L2 = vx * vx + vy * vy || 1;
    G.s = Math.max(0.05, ((x - o[0]) * vx + (y - o[1]) * vy) / L2);   // along the diagonal, so the aspect holds
    liveSel(G);
    return;
  }
  for (const e of events) eraseTo(e.clientX, e.clientY);
}
function up(e, cancelled) {
  const g = G; G = null;
  if (!g) return;
  if (g.kind === 'draw' || g.kind === 'snapped') {
    clearTimeout(g.holdT);
    g.rec.seq = Date.now();
    data(g.page).els.set(g.rec.id, g.el);
    doOp(changeOp([{ page: g.page, removed: [], added: [g.rec] }]));   // a snap is one step: the shape
    return;
  }
  if (g.kind === 'grab') {
    hideHandle();
    const moved = JSON.stringify(g.now.data) !== JSON.stringify(g.rec.data);
    if (cancelled || !moved) { if (g.el) setGeom(g.el, g.rec); return; }
    doOp(changeOp([{ page: g.page, removed: [g.rec], added: [g.now] }]));
    return;
  }
  if (g.kind === 'box') {
    g.band.remove();
    const b = [Math.min(g.p0[0], g.p1[0]), Math.min(g.p0[1], g.p1[1]), Math.max(g.p0[0], g.p1[0]), Math.max(g.p0[1], g.p1[1])];
    if (cancelled || (b[2] - b[0]) * g.z < 4 || (b[3] - b[1]) * g.z < 4) return;    // a tap outside only clears
    const ids = inBox(g.page, b);
    if (ids.length) makeSel(g.page, ids);
    return;
  }
  if (g.kind === 'smove' || g.kind === 'sresize' || g.kind === 'srotate') {
    unliveSel(g);
    const same = g.kind === 'smove' ? Math.hypot(g.dx, g.dy) < 0.5 : g.kind === 'sresize' ? Math.abs(g.s - 1) < 1e-3 : !g.a;
    if (cancelled || same) return;                                 // a tap or a 0 px drag: nothing changes, no reorder
    // the changed selection comes to the front: fresh seq values after every stroke on the page, in its own order
    const [f, s, rot] = selXf(g), all = data(g.page).strokes, top = all.length ? all[all.length - 1].seq : 0;
    const base = Math.max(Date.now(), top + 1);
    const news = g.recs.slice().sort(bySeq).map((r, k) => ({ ...xform(r, f, s, rot), seq: base + k }));
    doOp(changeOp([{ page: g.page, removed: g.recs, added: news }]));
    return;
  }
  hideRing();
  const changes = [];
  g.changes.forEach((c, page) => { if (c.removed.size || c.added.size) changes.push({ page, removed: [...c.removed.values()], added: [...c.added.values()] }); });
  if (changes.length) doOp(changeOp(changes));
}
export const hook = { down, move, up, hover };
