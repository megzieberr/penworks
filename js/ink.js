// PenWorks ink: the stroke model, one SVG layer per page, pen and highlighter drawing, the two
// erasers, hit tests, and the ink operations that join the note's one undo stack (js/app.js).
// A stroke is one record, exactly the strokes table's shape:
//   { id, page_id, seq, kind, style: { colour, width, dash, opacity }, data }
//   pen / highlighter: data = { points: [[x, y], ...] } in page px at zoom 1 (A4 = 794 x 1123)
//   shape (Part B):    data = { type, ...params }; the stroke eraser removes a shape whole; the area eraser turns it into ink and cuts it
// Rendering: one <path> per stroke, so every stroke stays crisp at every zoom and can be hit on its own.
// Each page's SVG holds two groups: <g class="hl"> (bottom) and <g class="pen"> (top, pen and shapes).
// Inside .hl there is one <g class="hlo" data-opacity> per opacity used on the page; its paths are fully
// opaque and the group's opacity makes them see-through, so going over a spot again stays one flat colour.
// Storage goes through js/store-local.js only.
// Part B: hold the pen still at the end of a pen stroke and it snaps into a line, arrow, arc, triangle, rect,
// circle or ellipse (SVG primitives); with the select tool a shape's handles can be grabbed and dragged; the restyle
// tool gives strokes the restyle colour and the pen's (or the highlighter's) width, dash or opacity; rectangle
// select moves, resizes, copies, deletes and (from the tray) recolours or restyles. Every one of these is one
// step on the note's undo stack.
// A held highlighter stroke snaps too (never to an arrow): a shape whose style.opacity is under 1 is a
// highlighter-born shape and lives in the highlighter layer (inHl below is that one rule).
// Shape handles (pw-v4v, her ruling 26 Oct: "I want the drag in the select button rather"): the plain pen never grabs,
// it always draws. With the SELECT tool, a pen landing within reach of an end point, corner or compass point of any shape
// on the page grabs it and drags it (after the selection's own turn ring and corners, before a move inside the box); a grab
// that moves under 4 px on screen is a tap and selects as any select tap does (that shape when nothing else wins). The pen button (a contextmenu on the desk, page.js)
// flips between Select and the last ink tool.
// Arc snap (pw-v4f): an open curve held still snaps into a circular arc, data { type: 'arc', x1, y1, xm, ym, x2, y2 }
// (start, the point half way round, end); its three handles move one point each, the arc is the circle through them.
// Select turns (pw-v4g): a ring above the selection box turns the selection about the box's centre (snapping to
// multiples of 15 degrees within 2.5); an ellipse keeps its turn in data.angle (degrees, absent = 0). A selection
// that is moved, resized or turned comes to the front (fresh seq values, its own order kept); a resize keeps the
// ink's width, only the shape grows or shrinks.
// Select polish (pw-v4j): a tap selects the topmost stroke under it, a drag selects everything in the box; a finger
// tap outside the selection clears it (any tool); a turn shows its degrees beside the ring; the chips are icons.
// Clipboard (pw-v4k): the Copy chip puts the selection on a clipboard (CLIP, kept while the app is open, across notes)
// and adds nothing; a finger held still on a page (page.js) opens a small menu with Paste, which puts a copy there,
// centred on the finger and kept inside the page, selected, as one undo step.
// Area eraser cuts shapes (pw-v4l): a shape the area eraser's ring touches turns into plain ink (shapeToInk: pen or
// highlighter records sampled every 3 px along its outline) and the ring cuts that ink like a stroke; one bite out of
// a closed shape leaves one open piece. The stroke eraser still removes a shape whole.
// Overlap tie-break (pw-v4m): a select tap where highlighter-layer and pen-layer records overlap picks from the layer
// of the last ink tool (T.lastInk); with no overlap across the layers it picks the topmost record, whatever is there.
// Last stroke (pw-v4n): LAST remembers the raw points of the last finished pen or highlighter stroke (before any snap) and
// lastStroke() returns it; ?dbg=1 shows and copies it (js/dbg.js), so a real pen stroke can be caught on the tablet.
// Duplicate chip (pw-v4o): a + chip between Copy and Delete puts a copy of the selection 24 px right and down (kept inside
// the page), selected, as one undo step; the clipboard is not touched.
// Select all (pw-v4p): the finger hold menu has Select all above Paste; it selects every stroke on the page under the finger.
// Parabola snap (pw-v4s): an open curve with one turn whose arms straighten, held still, snaps into a parabola, data
// { type: 'parabola', x1, y1, cx, cy, x2, y2 }: a quadratic Bezier (start, control, end; drawn M x1 y1 Q cx cy x2 y2), which
// stays a parabola under every move, resize and turn. Its three handles are the ends and the curve's middle (t = 0.5). The
// fit runs after the line and before the arc, and wins only when it is under 0.6 of the arc's own fit (an even curve stays
// an arc); lastStroke().fit holds both numbers for ?dbg=1.

import * as store from './store-local.js';
import { pageAt, pagePoint, view, pageSize } from './page.js';

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
export const HANDLE_REACH = 20;  // shape handles (select tool): px on screen (20 px at zoom 1), a pen tip needs room
const SEL_BLUE = '#2F4BB8';      // the selection box (the paper is white in both modes)

const P = new Map();             // page id -> { strokes (by seq), byId, svg, hl, pen, hlo (opacity -> group), els (id -> path), w, h }
const boxes = new WeakMap();     // record -> [x0, y0, x1, y1], its points' bounding box
const T = { tool: 'pen', lastInk: 'pen', style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 } };
// what restyle hands out: its own colour, and the pen's and the highlighter's current settings (the tray keeps these up to date)
const ST = { pen: { colour: '#000000', width: 2.5, dash: 'solid' }, highlighter: { colour: '#FFC107', width: 18, opacity: 0.4 }, restyle: null };
let doOp = (op) => op.redo();
let onChange = null;             // optional: told the page id after every stroke change (apply), the page list's thumbs
let G = null;                    // the gesture in progress
let LAST = null;                 // the last finished pen or highlighter stroke, raw: { points, pointerType, z, n, len, classify, snapped, at, fit? }
let FIT = null;                  // the last classify's parabola fit when it returned a parabola: { p, a } (its residual, the arc's), else null
let ring = null, hring = null, deskEl = null, deskBox = null;
let SEL = null;                  // the selection: { page, ids, g, chips, deg, z }
let CLIP = null;                 // the selection clipboard: { recs (deep copies, by seq), box (their selBox) }
let toast = null, openMenuAt = null, selectTool = null;   // optional, from app.js: a toast, the menu at a point, the tray's select tool
// the chips' three icons (the same drawing style as SVG_BIN in js/app.js)
const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">';
const SVG_COPY = ICON + '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>';
const SVG_PLUS = ICON + '<path d="M12 5v14M5 12h14"/></svg>';
const SVG_BIN = ICON + '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/></svg>';

const uuid = () => crypto.randomUUID();
const r1 = (v) => Math.round(v * 10) / 10;
const bySeq = (a, b) => a.seq - b.seq;

export function initInk(o) {
  if (o.doOp) doOp = o.doOp;
  if (o.onChange) onChange = o.onChange;
  if (o.toast) toast = o.toast;
  if (o.openMenuAt) openMenuAt = o.openMenuAt;
  if (o.selectTool) selectTool = o.selectTool;
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
  if (tool === 'pen' || tool === 'highlighter') T.lastInk = tool;   // the overlap tie-break (topAt) follows it
}
export function setStyles(pen, highlighter, restyle) { ST.pen = { ...pen }; ST.highlighter = { ...highlighter }; ST.restyle = restyle ? { ...restyle } : null; }
export function tool() { return { tool: T.tool, lastInk: T.lastInk, style: { ...T.style } }; }
export function busy() { return !!G; }   // a gesture is running (the pen button flip waits for the lift)

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
export function lastStroke() { return LAST; }
export function strokesOf(pageId) { return data(pageId).strokes.slice(); }
export function copyStrokes(pageId) { return JSON.parse(JSON.stringify(data(pageId).strokes)); }

// a shape's outline as a polyline (hit tests now; Part B draws shapes with SVG primitives); n: how many points a
// circle, ellipse, arc or parabola gets (48 for the hit tests, more when it turns into ink)
export function outline(rec, n = 48) {
  const d = rec.data || {};
  if (d.type === 'line' || d.type === 'arrow') return [[d.x1, d.y1], [d.x2, d.y2]];
  if ((d.type === 'rect' || d.type === 'triangle') && d.points && d.points.length) return [...d.points, d.points[0]];
  if (d.type === 'circle' || d.type === 'ellipse') {
    const rx = d.type === 'circle' ? d.r : d.rx, ry = d.type === 'circle' ? d.r : d.ry, out = [];
    const tu = d.type === 'ellipse' ? d.angle || 0 : 0, c = [d.cx, d.cy];
    for (let k = 0; k <= n; k++) { const a = (k / n) * 2 * Math.PI; out.push(turn([d.cx + rx * Math.cos(a), d.cy + ry * Math.sin(a)], c, tu)); }
    return out;
  }
  if (d.type === 'arc') {                                          // n points from the start to the end
    const g = arcGeom(d);
    if (!g) return [[d.x1, d.y1], [d.xm, d.ym], [d.x2, d.y2]];
    const out = [[d.x1, d.y1]], m = n - 1;
    for (let k = 1; k < m; k++) { const a = g.t1 + (g.sweep * k) / m; out.push([g.ox + g.r * Math.cos(a), g.oy + g.r * Math.sin(a)]); }
    out.push([d.x2, d.y2]);
    return out;
  }
  if (d.type === 'parabola') {                                     // n points along the curve, t = 0 to 1
    const out = [];
    for (let k = 0; k < n; k++) out.push(qbez(d, k / (n - 1)));
    return out;
  }
  return [];
}
// a parabola's point at t (0 = the start, 1 = the end): the quadratic Bezier (1-t)^2 P0 + 2t(1-t) C + t^2 P2
function qbez(d, t) {
  const u = 1 - t;
  return [u * u * d.x1 + 2 * u * t * d.cx + t * t * d.x2, u * u * d.y1 + 2 * u * t * d.cy + t * t * d.y2];
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
// a shape as plain ink (the area eraser, pw-v4l): one or two pen or highlighter records (the inHl rule picks the kind,
// so a highlighter-born shape's ink stays in its .hlo group), same page, seq and style, fresh ids, points every 3 px
// along the outline. Closed shapes give ONE closed polyline (its last point repeats the first); an arrow gives two,
// the shaft and the head (the head's two lines through the tip, where makeEl draws them, solid like the drawn head).
const INK_STEP = 3;
function densify(poly, step) {                                     // every vertex kept, no gap over step
  if (!poly.length) return [];
  const out = [rp(poly[0])];
  for (let i = 1; i < poly.length; i++) {
    const a = poly[i - 1], b = poly[i], k = Math.max(1, Math.ceil(dist(a, b) / step));
    for (let j = 1; j < k; j++) out.push(rp([a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k]));
    out.push(rp(b));
  }
  return out;
}
function shapeToInk(rec) {
  const d = rec.data || {}, kind = inHl(rec) ? 'highlighter' : 'pen';
  const ink = (pts, style = rec.style) => ({ id: uuid(), page_id: rec.page_id, seq: rec.seq, kind, style: { ...style }, data: { points: pts } });
  if (d.type === 'arrow') {
    const h = arrowHeadPts(d, (rec.style && rec.style.width) || 2.5);
    return [ink(densify([[d.x1, d.y1], [d.x2, d.y2]], INK_STEP)), ink(densify(h, INK_STEP), { ...rec.style, dash: 'solid' })];
  }
  let len = 0;                                                     // curves: enough points for a 3 px step
  if (d.type === 'circle') len = 2 * Math.PI * d.r;
  else if (d.type === 'ellipse') { const a = d.rx, b = d.ry; len = Math.PI * (3 * (a + b) - Math.sqrt((3 * a + b) * (a + 3 * b))); }
  else if (d.type === 'arc') { const g = arcGeom(d); len = g ? g.r * Math.abs(g.sweep) : 0; }
  else if (d.type === 'parabola') len = polyLen(outline(rec, 96));
  const o = outline(rec, Math.max(48, Math.ceil(len / INK_STEP)));
  if (o.length < 2) return [];
  const closed = d.type === 'rect' || d.type === 'triangle' || d.type === 'circle' || d.type === 'ellipse';
  const pts = densify(o, INK_STEP);
  if (closed) pts[pts.length - 1] = pts[0].slice();
  return [ink(pts)];
}
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
// shapes are SVG primitives: line, polygon (rect, triangle), circle, ellipse, path (arc, parabola); an arrow is a <g> of its
// line and an open head (the head never dashed, so every arrow ends the same way)
const SHAPE_TAG = { line: 'line', arrow: 'g', rect: 'polygon', triangle: 'polygon', circle: 'circle', ellipse: 'ellipse', arc: 'path', parabola: 'path' };
function arrowHeadPts(d, w) {                                    // [one barb's end, the tip, the other barb's end]
  const dx = d.x2 - d.x1, dy = d.y2 - d.y1, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
  const len = Math.min(L * 0.45, Math.max(14, w * 4)), a = 28 * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  const b1 = [d.x2 - len * (ux * c - uy * s), d.y2 - len * (uy * c + ux * s)];
  const b2 = [d.x2 - len * (ux * c + uy * s), d.y2 - len * (uy * c - ux * s)];
  return [b1, [d.x2, d.y2], b2];
}
function arrowHead(d, w) { return 'M' + arrowHeadPts(d, w).map((q) => f1(q[0]) + ' ' + f1(q[1])).join('L'); }
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
  else if (d.type === 'parabola') {                                // M start Q control end
    const p = (x, y) => f1(x) + ' ' + f1(y);
    el.setAttribute('d', 'M' + p(d.x1, d.y1) + 'Q' + p(d.cx, d.cy) + ' ' + p(d.x2, d.y2));
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

// the page list (pw-v4i): a page's ink as its own small <svg>, built from the records with the same builders as the
// page (makeEl + groupFor, in seq order, highlighter groups below the pen group), so a thumb shows what the page
// shows. Never a clone of the live layer: a page that is not attached has none. viewBox = the page in page px
// (the attached size, else its orientation's size); the thumb's .paper already has the page's aspect ratio.
export function thumbSvg(pageId, orientation = 'portrait') {
  const d = data(pageId), sz = d.w && d.h ? { w: d.w, h: d.h } : pageSize(orientation);
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'thumbInk');
  svg.setAttribute('viewBox', `0 0 ${sz.w} ${sz.h}`);
  svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('pointer-events', 'none');
  const t = { hl: document.createElementNS(SVGNS, 'g'), pen: document.createElementNS(SVGNS, 'g'), hlo: new Map() };
  t.hl.setAttribute('class', 'hl'); t.pen.setAttribute('class', 'pen');
  for (const rec of d.strokes) groupFor(t, rec).appendChild(makeEl(rec));
  svg.append(t.hl, t.pen);
  return svg;
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
  if (onChange) onChange(pageId);                      // the page list refreshes that page's thumb
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
// cut a shape's ink (pw-v4l): for a closed loop whose first and last runs both survive (the bite missed the seam),
// the last run and the first run join into one piece, so one bite leaves one open piece
function cutInk(pts, cx, cy, R) {
  const runs = cut(pts, cx, cy, R), n = pts.length;
  if (!runs || runs.length < 2 || n < 3) return runs;
  const a = pts[0], z = pts[n - 1], first = runs[0], lastRun = runs[runs.length - 1];
  if (a[0] !== z[0] || a[1] !== z[1] || first[0] !== a || lastRun[lastRun.length - 1] !== z) return runs;
  return [[...lastRun, ...first.slice(1)], ...runs.slice(1, -1)];
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
// the Kasa circle fit (least squares on x^2 + y^2 + a x + b y + c = 0, the points centred on their mean first so the
// sums stay small): { ox, oy, r, res (the largest distance of a point from the circle) }; null when there is no circle
function kasa(raw) {
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
  let res = 0;
  for (const q of raw) res = Math.max(res, Math.abs(Math.hypot(q[0] - ox, q[1] - oy) - r));
  return { ox, oy, r, res };
}
// arc: an open stroke that sits on one circle (the Kasa fit above, k): every point within 6% of the size from the
// circle, the radius at most 3 x the size, the end further than 10% of the size from the start, and 25 to 330 degrees
// swept the way the stroke travels (the raw point half way along its length, against the chord, gives that way)
function arcOf(raw, A, Z, size, k = kasa(raw)) {
  if (dist(A, Z) <= 0.1 * size) return null;                       // closed: the closed test's
  if (!k) return null;
  const n = raw.length, { ox, oy, r } = k;
  if (r > 3 * size) return null;                                   // flatter: a line or freehand
  if (k.res > 0.06 * size) return null;                            // every point within 6% of the size from the circle
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
// parabola (pw-v4s): an open stroke on one quadratic Bezier from its first raw point to its last. It works on the stroke
// as drawn: its raw points and the line between them, every 3 px (so a sparse 5 point tick cannot slip a curve between
// its points). The control point C by closed-form least squares (B0 = (1-t)^2, B1 = 2t(1-t), B2 = t^2: C = sum(B1 (p - B0 P0 - B2 P2)) / sum(B1^2)),
// first on chord-length t, then refined: each point's t moves to its nearest point on the curve and C is solved
// again (up to 12 rounds; chord-length t alone runs too fast along the steep arms and leaves the fit 2 to 15 x worse
// than the curve really is); every point within 5% of the size from the curve (the curve as 96 points,
// distance to its polyline); one turn only (rdp's points change their turning direction at most once, turns
// under 5 degrees not counted); and it must beat the arc: its residual under 0.6 x the circle fit's (k.res), so an
// even curve stays an arc. { shape, p, a } (p, a: the two residuals, px) or null
function parabolaOf(stroke, A, Z, size, k) {
  if (dist(A, Z) <= 0.1 * size) return null;                       // closed: the closed test's
  const raw = densify(stroke, INK_STEP), n = raw.length, cum = [0];
  for (let i = 1; i < n; i++) cum.push(cum[i - 1] + dist(raw[i - 1], raw[i]));
  const L = cum[n - 1];
  if (!(L > 0)) return null;
  const ts = cum.map((c) => c / L), d = { x1: A[0], y1: A[1], cx: 0, cy: 0, x2: Z[0], y2: Z[1] };
  const solve = () => {                                            // C for the current ts; false when it has none
    let sx = 0, sy = 0, den = 0;
    for (let i = 0; i < n; i++) {
      const t = ts[i], u = 1 - t, b0 = u * u, b1 = 2 * t * u, b2 = t * t;
      sx += b1 * (raw[i][0] - b0 * A[0] - b2 * Z[0]); sy += b1 * (raw[i][1] - b0 * A[1] - b2 * Z[1]); den += b1 * b1;
    }
    if (!(den > 0)) return false;
    d.cx = sx / den; d.cy = sy / den;
    return true;
  };
  if (!solve()) return null;
  let curve = [];
  const sample = () => { curve = []; for (let j = 0; j < 96; j++) curve.push(qbez(d, j / 95)); };
  for (let round = 0; round < 12; round++) {                       // each t to its nearest point on the curve, C again
    sample();
    const ddx = 2 * (d.x2 - 2 * d.cx + d.x1), ddy = 2 * (d.y2 - 2 * d.cy + d.y1);   // B'' (the same at every t)
    for (let i = 1; i < n - 1; i++) {
      const q = raw[i];
      let bj = 0, bd = Infinity;
      for (let j = 0; j < 96; j++) { const e = (curve[j][0] - q[0]) ** 2 + (curve[j][1] - q[1]) ** 2; if (e < bd) { bd = e; bj = j; } }
      let t = bj / 95;
      for (let it = 0; it < 3; it++) {                             // Newton on (B(t) - q) . B'(t) = 0
        const b = qbez(d, t), dx = 2 * (1 - t) * (d.cx - d.x1) + 2 * t * (d.x2 - d.cx), dy = 2 * (1 - t) * (d.cy - d.y1) + 2 * t * (d.y2 - d.cy);
        const f = (b[0] - q[0]) * dx + (b[1] - q[1]) * dy, fp = dx * dx + dy * dy + (b[0] - q[0]) * ddx + (b[1] - q[1]) * ddy;
        if (!(fp > 0)) break;
        t = Math.min(1, Math.max(0, t - f / fp));
      }
      ts[i] = t;
    }
    const ox = d.cx, oy = d.cy;
    if (!solve()) return null;
    if (Math.hypot(d.cx - ox, d.cy - oy) < 0.01) break;
  }
  sample();
  let worst = 0;
  for (const q of raw) {
    let m = Infinity;
    for (let j = 1; j < curve.length; j++) m = Math.min(m, segDist2(q[0], q[1], curve[j - 1], curve[j]));
    worst = Math.max(worst, m);
  }
  const p = Math.sqrt(worst);
  if (p > 0.05 * size) return null;
  const v = rdp(raw, Math.max(0.75, 0.02 * size));                 // one turn: the sign of the turns flips at most once
  let sign = 0, flips = 0;
  for (let i = 1; i < v.length - 1; i++) {
    const ax = v[i][0] - v[i - 1][0], ay = v[i][1] - v[i - 1][1], bx = v[i + 1][0] - v[i][0], by = v[i + 1][1] - v[i][1];
    const cr = ax * by - ay * bx;
    if (Math.abs(Math.atan2(cr, ax * bx + ay * by)) < 5 * Math.PI / 180) continue;
    const sg = Math.sign(cr);
    if (sign && sg !== sign) flips++;
    sign = sg;
  }
  if (flips > 1) return null;
  const a = k ? k.res : Infinity;
  if (!(p < 0.6 * a)) return null;                                 // the arc fits about as well: the arc branch has it
  return { shape: { type: 'parabola', x1: r1(A[0]), y1: r1(A[1]), cx: r1(d.cx), cy: r1(d.cy), x2: r1(Z[0]), y2: r1(Z[1]) }, p, a };
}
// in this order: arrow, line, parabola, arc, then closed: triangle, rect, circle or ellipse; null = stays freehand.
// A parabola leaves its two fit numbers in FIT (lastStroke().fit); every other answer leaves FIT null
export function classify(raw) {
  FIT = null;
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
  // parabola: open, one turn, and a better fit than the arc's (parabolaOf above)
  const k = kasa(raw), par = parabolaOf(raw, A, Z, size, k);
  if (par) { FIT = { p: r1(par.p), a: Number.isFinite(par.a) ? r1(par.a) : null }; return par.shape; }
  // arc: open, and on one circle (arcOf above)
  const arc = arcOf(raw, A, Z, size, k);
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

// ---------------------------------------------------------------- shape handles (grab with the select tool)
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
  if (d.type === 'parabola') return [[d.x1, d.y1], qbez(d, 0.5), [d.x2, d.y2]];           // start, the curve's middle M, end
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
  } else if (d.type === 'parabola') {                              // an end moves alone (the control holds); the middle M' sets
    if (h === 1) { d.cx = r1(2 * x - (d.x1 + d.x2) / 2); d.cy = r1(2 * y - (d.y1 + d.y2) / 2); }   // C = 2 M' - (P0 + P2) / 2
    else if (h === 0) { d.x1 = r1(x); d.y1 = r1(y); } else { d.x2 = r1(x); d.y2 = r1(y); }
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
// the selection's own grips at page point `at` (page at.id): 'rot' on its turn ring, a corner index 0..3, else null
function selGrip(at, z) {
  if (!SEL || SEL.page !== at.id || !SEL.box) return null;
  const reach = GRAB / z;
  if (SEL.rot && Math.hypot(SEL.rot[0] - at.x, SEL.rot[1] - at.y) <= reach) return 'rot';
  const k = selCorners(SEL.box).findIndex((q) => Math.hypot(q[0] - at.x, q[1] - at.y) <= reach);
  return k >= 0 ? k : null;
}
// the pen hovering (or a mouse moving), button or not, with the select tool: a small ring on a handle within reach,
// meaning "a touch here grabs this point"; out of reach, or where the selection's ring or a corner would win, no ring.
// The pen tool shows nothing: it only draws
function hover(e) {
  if (T.tool !== 'select' || G) { hideHandle(); return; }
  const at = pageAt(e.clientX, e.clientY), z = view().z;
  const h = at && selGrip(at, z) === null && handleAt(at.id, at.x, at.y, HANDLE_REACH / z);
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
  } else if (d.type === 'parabola') {                              // a Bezier maps through its three points
    const a = P([d.x1, d.y1]), c = P([d.cx, d.cy]), z = P([d.x2, d.y2]);
    nd = { ...d, x1: a[0], y1: a[1], cx: c[0], cy: c[1], x2: z[0], y2: z[1] };
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

// ---------------------------------------------------------------- the selection: dashed box, corners, Copy, Duplicate and Delete
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
  SEL.g.remove(); SEL.chips.remove(); SEL.deg.remove();
  SEL = null;
}
export function selection() { return SEL ? { page: SEL.page, ids: [...SEL.ids], box: selBox(selRecs()) } : null; }
function setAttrs(el, at) { for (const k in at) el.setAttribute(k, typeof at[k] === 'number' ? f1(at[k]) : at[k]); }
function renderSel(t) {                          // t: a live transform while dragging the selection
  const d = data(SEL.page), z = view().z, b = selBox(selRecs());
  SEL.z = z;
  if (!SEL.g.parentNode) d.svg.appendChild(SEL.g);
  if (!SEL.chips.parentNode) d.svg.parentNode.appendChild(SEL.chips);
  if (!SEL.deg.parentNode) d.svg.parentNode.appendChild(SEL.deg);
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
  // the turn handle: a ring 28 px (on screen) above the top edge's middle, on a thin stem;
  // when that would pass the page's top edge, the ring goes 28 px BELOW the bottom edge instead
  const cx = (x0 + x1) / 2, below = y0 - 28 / z - 6 / z < 0, ry = below ? y1 + 28 / z : y0 - 28 / z;
  const stem = document.createElementNS(SVGNS, 'line');
  setAttrs(stem, below
    ? { class: 'selstem', x1: cx, y1: y1, x2: cx, y2: ry - 6 / z, stroke: SEL_BLUE, 'stroke-width': 1.2 / z }
    : { class: 'selstem', x1: cx, y1: y0, x2: cx, y2: ry + 6 / z, stroke: SEL_BLUE, 'stroke-width': 1.2 / z });
  const knob = document.createElementNS(SVGNS, 'circle');
  setAttrs(knob, { class: 'selrot', cx, cy: ry, r: 6 / z, fill: '#FFFFFF', stroke: SEL_BLUE, 'stroke-width': 1.5 / z });
  SEL.g.append(stem, knob);
  SEL.rot = [cx, ry];
  if (t) SEL.g.setAttribute('transform', t); else SEL.g.removeAttribute('transform');
  SEL.box = [x0, y0, x1, y1];
  placeChips(t ? SEL.live : null);
}
function placeChips(m) {                         // m: [s, ox, oy, dx, dy] while dragging, so the chips ride along
  let [x0, y0] = SEL.box, rx = SEL.rot && SEL.rot[1] < SEL.box[1] ? SEL.rot[0] : Infinity;   // only a ring ABOVE the box crowds the chips (Infinity: nothing to dodge)
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
  const chip = (act, label, icon, fn) => {        // an icon only: the word lives in aria-label and title
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'chip'; btn.dataset.act = act; btn.innerHTML = icon;
    btn.setAttribute('aria-label', label); btn.title = label;
    btn.addEventListener('click', (e) => { e.stopPropagation(); fn(); });
    chips.appendChild(btn);
  };
  chip('copy', 'Copy', SVG_COPY, copySel); chip('duplicate', 'Duplicate', SVG_PLUS, duplicateSel); chip('delete', 'Delete', SVG_BIN, deleteSel);
  const deg = document.createElement('div'); deg.className = 'selDeg';   // the turn's degrees, shown only while turning
  SEL = { page, ids: new Set(ids), g, chips, deg, z: 0, box: null, rot: null, live: null };
  renderSel();
}
// Copy: the selection goes on the clipboard; nothing is added, the selection stays, no undo step
function copySel() {
  if (!SEL) return;
  const recs = selRecs().sort(bySeq);
  if (!recs.length) return;
  CLIP = { recs: JSON.parse(JSON.stringify(recs)), box: selBox(recs) };
  if (toast) toast('Copied.');
}
export function hasClip() { return !!CLIP; }
// Paste: the clipboard's strokes on page pageId, the box's centre on (x, y) (page px), nudged inside the page where
// it fits (a box bigger than the page is centred on it); fresh ids, seq values above every stroke on the page in the
// copied order; one undo step; the pasted strokes become the selection with the select tool on. The clipboard stays.
export function pasteAt(pageId, x, y) {
  if (!CLIP) return false;
  const d = data(pageId), b = CLIP.box;
  const fit = (lo, hi, at, W) => keepIn(lo, hi, at - (lo + hi) / 2, W, W / 2 - (lo + hi) / 2);   // centre on at, kept on the page
  addCopies(pageId, CLIP.recs, fit(b[0], b[2], x, d.w), fit(b[1], b[3], y, d.h));
  return true;
}
// the shift v along one axis, cut back so [lo, hi] stays on [0, W]; a span wider than W gets big instead (no page size: v)
function keepIn(lo, hi, v, W, big) {
  if (!W) return v;
  if (hi - lo > W) return big;
  return Math.min(W - hi, Math.max(-lo, v));
}
// Paste and Duplicate: copies of recs (by seq) on page pageId moved by (dx, dy), fresh ids, seq values above every stroke
// on the page in the same order, one undo step; the copies become the selection with the select tool on
function addCopies(pageId, recs, dx, dy) {
  const d = data(pageId);
  const top = d.strokes.length ? d.strokes[d.strokes.length - 1].seq : 0, base = Math.max(Date.now(), top + 1);
  const news = recs.map((r, k) => ({ ...xform(r, (q) => [q[0] + dx, q[1] + dy], 1, 0), id: uuid(), page_id: pageId, seq: base + k }));
  doOp(changeOp([{ page: pageId, removed: [], added: news }]));
  if (T.tool !== 'select') { if (selectTool) selectTool(); else setTool('select'); }
  if (d.svg) makeSel(pageId, news.map((r) => r.id));
  return news;
}
// Duplicate (pw-v4o): a copy of the selection 24 px right and down, pulled back inside the page where it would leave it
// (along an axis where the box is wider than the page it keeps the plain 24 px); the copy is selected; CLIP stays as it was
const DUP_STEP = 24;
function duplicateSel() {
  if (!SEL) return;
  const page = SEL.page, d = data(page), recs = selRecs().sort(bySeq);
  if (!recs.length) return;
  const b = selBox(recs);
  // right and down, or where that is pulled back (the box sits at the edge) the other way, so the copy never lands on itself
  const step = (lo, hi, W) => { const v = keepIn(lo, hi, DUP_STEP, W, DUP_STEP), u = keepIn(lo, hi, -DUP_STEP, W, -DUP_STEP); return Math.abs(v) >= Math.abs(u) ? v : u; };
  addCopies(page, recs, step(b[0], b[2], d.w), step(b[1], b[3], d.h));
}
// Select all (pw-v4p): every stroke on page pageId (pen, highlighter and shapes, both layers) becomes the selection with
// the select tool on, the way a paste does; no undo step (a selection is not a change). False when the page is empty.
export function selectAll(pageId) {
  const d = data(pageId);
  if (!d.strokes.length || !d.svg) return false;
  if (T.tool !== 'select') { if (selectTool) selectTool(); else setTool('select'); }
  makeSel(pageId, d.strokes.map((r) => r.id));
  return true;
}
// a finger held still on the desk (page.js): over a page, a small menu with Select all (disabled on an empty page)
// and Paste (disabled with nothing copied)
function holdMenu(cx, cy) {
  if (G || !openMenuAt) return;
  const at = pageAt(cx, cy);
  if (!at) return;                                 // off every page: nothing opens
  const pageId = at.id, x = at.x, y = at.y;
  openMenuAt(cx, cy, [data(pageId).strokes.length ? { label: 'Select all', fn: () => selectAll(pageId) }
                                                  : { label: 'Nothing to select', disabled: true, fn: () => {} },
                      CLIP ? { label: 'Paste', fn: () => pasteAt(pageId, x, y) }
                           : { label: 'Nothing to paste', disabled: true, fn: () => {} }]);
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
// the stroke a tap lands on: every record within reach; when the hits hold both a highlighter-layer and a pen-layer
// record, only the layer of the last ink tool counts (pw-v4m); the topmost of what counts (highest seq) wins
function topAt(id, x, y, reach) {
  const all = data(id).strokes, hits = [];
  for (let i = all.length - 1; i >= 0; i--) if (near(all[i], x, y, reach)) hits.push(all[i]);   // top of the stack first
  if (!hits.length) return null;
  if (hits.some(inHl) && hits.some((r) => !inHl(r))) {
    const wantHl = T.lastInk === 'highlighter';
    return hits.find((r) => inHl(r) === wantHl).id;
  }
  return hits[0].id;
}
// a finger tap (page.js: a touch that lifted within 6 px of where it landed): outside the selection's box it clears
function fingerTap(cx, cy) {
  if (!SEL || G) return;
  const at = pageAt(cx, cy), b = SEL.box;
  if (at && b && at.id === SEL.page && at.x >= b[0] && at.x <= b[2] && at.y >= b[1] && at.y <= b[3]) return;   // inside: the pen moves it
  clearSelection();
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

// ---------------------------------------------------------------- restyle: its own colour, the matching tool's width and opacity; restyle never changes the dash
function restyled(r) {
  const p = ST.pen, h = ST.highlighter, hl = inHl(r), c = ST.restyle && ST.restyle.colour;
  const style = hl                                                 // a highlight (stroke or shape) stays a highlight
    ? { colour: c || h.colour, width: h.width, dash: 'solid', opacity: h.opacity }
    : { colour: c || p.colour, width: p.width, dash: (r.style && r.style.dash) || 'solid', opacity: 1 };
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
    if (r.kind === 'shape') {                                      // the stroke eraser removes a shape whole; this ring turns it into ink and cuts it
      if (!near(r, at.x, at.y, R)) continue;
      const out = [];
      let hit = false;
      for (const k of shapeToInk(r)) {
        const runs = cutInk(k.data.points, at.x, at.y, R);
        if (!runs) { out.push(k); continue; }                      // a part the ring misses stays whole, as ink
        hit = true;
        for (const pts of runs) out.push({ ...k, id: uuid(), style: { ...k.style }, data: { points: pts } });
      }
      if (!hit) continue;
      gone.push(r); pieces.push(...out);
      continue;
    }
    if (r.kind !== 'pen' && r.kind !== 'highlighter') {          // later kinds go whole
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
  G = { kind: 'snapped', page: g.page, rec, el, d, raw: g.rec.data.points.slice(), pt: g.pt, z: g.z };   // raw: the freehand points, kept for lastStroke
}

function down(e) {
  if (e.button === 2) return false;                                // the right button / pen button press: never a gesture (page.js flips the tool on its contextmenu)
  if (T.tool === 'pen' && barrel(e)) return false;                 // the pen tip down with the button held: a harmless miss, as before
  const at = pageAt(e.clientX, e.clientY);
  if (!at) { if (T.tool === 'select') clearSelection(); return false; }
  const d = data(at.id);
  if (!d.svg) return false;
  hideHandle();
  const z = view().z;
  if (T.tool === 'pen' || T.tool === 'highlighter') {              // the pen and the highlighter always draw, even on a shape's end
    const s = T.style;
    const style = T.tool === 'pen'
      ? { colour: s.colour, width: s.width, dash: s.dash || 'solid', opacity: 1 }
      : { colour: s.colour, width: s.width, dash: 'solid', opacity: s.opacity };
    const rec = { id: uuid(), page_id: at.id, seq: 0, kind: T.tool, style, data: { points: [[r1(at.x), r1(at.y)]] } };
    const el = makeEl(rec);
    groupFor(d, rec).appendChild(el);                              // newest, so last in its group
    G = { kind: 'draw', index: at.index, page: at.id, rec, el, holdT: 0, anchor: null, pt: e.pointerType || 'mouse', z: view().z };
    armHold(e.clientX, e.clientY);                                 // pen and highlighter both snap when held
    return true;
  }
  if (T.tool === 'eraser' || T.tool === 'area' || T.tool === 'restyle') {
    deskBox = deskEl.getBoundingClientRect();
    G = { kind: T.tool, z, changes: new Map(), last: null, done: new Set() };
    eraseTo(e.clientX, e.clientY);
    return true;
  }
  if (T.tool === 'select') {                                       // first match wins: ring, corner, shape handle, inside the box, a new box
    const grip = selGrip(at, z);
    if (grip === 'rot') {                                          // the ring: turn about the box's centre
      const b = SEL.box, c = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
      G = { kind: 'srotate', index: at.index, page: at.id, c, a0: Math.atan2(at.y - c[1], at.x - c[0]), a: 0, recs: selRecs() };
      return true;
    }
    if (grip !== null) {                                           // a corner: scale about the opposite one
      const q = selCorners(SEL.box), o = q[(grip + 2) % 4], c = q[grip];
      G = { kind: 'sresize', index: at.index, page: at.id, o, c, s: 1, recs: selRecs() };
      return true;
    }
    const h = handleAt(at.id, at.x, at.y, HANDLE_REACH / z);       // a shape's handle within reach, on any shape of the page
    if (h) {
      clearSelection();                                            // no box or chips on a shape being reshaped
      G = { kind: 'grab', page: at.id, index: at.index, rec: h.rec, h: h.h, el: d.els.get(h.rec.id), now: h.rec, z,
            off: [h.at[0] - at.x, h.at[1] - at.y], p0: [at.x, at.y], far: 0 };   // the handle keeps its offset from the pen: no jump
      showHandle(e.clientX + (h.at[0] - at.x) * z, e.clientY + (h.at[1] - at.y) * z);
      return true;
    }
    if (SEL && SEL.page === at.id) {
      const b = SEL.box;
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
    const z = SEL.z || view().z, dg = SEL.deg;                     // the degrees just right of the ring (where it was drawn)
    dg.textContent = Math.round(g.a) + '°';
    dg.style.left = f1(SEL.rot[0] + 14 / z) + 'px'; dg.style.top = f1(SEL.rot[1]) + 'px';
    dg.style.transform = `scale(${1 / z}) translateY(-50%)`;
    dg.classList.add('on');
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
  if (SEL) { SEL.live = null; SEL.g.removeAttribute('transform'); SEL.chips.style.visibility = ''; SEL.deg.classList.remove('on'); placeChips(null); }
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
    for (const e of events) {                                      // how far the pen ever got from where it landed (the tap rule)
      const [qx, qy] = pagePoint(G.index, e.clientX, e.clientY);
      G.far = Math.max(G.far, Math.hypot(qx - G.p0[0], qy - G.p0[1]));
    }
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
    const points = (g.raw || g.rec.data.points).map((p) => [p[0], p[1]]), c = classify(points);   // a snapped stroke keeps its freehand points in g.raw
    LAST = { points, pointerType: g.pt || 'mouse', z: g.z, n: points.length, len: Math.round(polyLen(points) * 10) / 10,
      classify: c ? c.type : null, snapped: g.kind === 'snapped', at: Date.now() };
    if (FIT) LAST.fit = { ...FIT };                                 // a parabola: its fit and the arc's (pw-v4s)
    g.rec.seq = Date.now();
    data(g.page).els.set(g.rec.id, g.el);
    doOp(changeOp([{ page: g.page, removed: [], added: [g.rec] }]));   // a snap is one step: the shape
    return;
  }
  if (g.kind === 'grab') {
    hideHandle();
    const moved = JSON.stringify(g.now.data) !== JSON.stringify(g.rec.data);
    if (e && Number.isFinite(e.clientX)) { const [qx, qy] = pagePoint(g.index, e.clientX, e.clientY); g.far = Math.max(g.far, Math.hypot(qx - g.p0[0], qy - g.p0[1])); }
    if (!cancelled && g.far * g.z < 4) {                           // a tap on a handle (under 4 px on screen): no change, no undo step; it
      if (g.el) setGeom(g.el, g.rec);                              // selects as any select tap does (topAt, so the pw-v4m tie-break holds),
      makeSel(g.page, [topAt(g.page, g.p0[0], g.p0[1], GRAB / g.z) || g.rec.id]);   // else the shape whose handle it was
      return;
    }
    if (cancelled || !moved) { if (g.el) setGeom(g.el, g.rec); return; }
    doOp(changeOp([{ page: g.page, removed: [g.rec], added: [g.now] }]));
    return;
  }
  if (g.kind === 'box') {
    g.band.remove();
    const b = [Math.min(g.p0[0], g.p1[0]), Math.min(g.p0[1], g.p1[1]), Math.max(g.p0[0], g.p1[0]), Math.max(g.p0[1], g.p1[1])];
    if (cancelled) return;
    if ((b[2] - b[0]) * g.z < 4 || (b[3] - b[1]) * g.z < 4) {     // a tap: the topmost stroke under it, alone
      const id = topAt(g.page, g.p0[0], g.p0[1], GRAB / g.z);
      if (id) makeSel(g.page, [id]);
      return;
    }
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
export const hook = { down, move, up, hover, fingerTap, holdMenu };
