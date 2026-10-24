// PenWorks ink: the stroke model, one SVG layer per page, pen and highlighter drawing, the two
// erasers, hit tests, and the ink operations that join the note's one undo stack (js/app.js).
// A stroke is one record, exactly the strokes table's shape:
//   { id, page_id, seq, kind, style: { colour, width, dash, opacity }, data }
//   pen / highlighter: data = { points: [[x, y], ...] } in page px at zoom 1 (A4 = 794 x 1123)
//   shape (Part B):    data = { type, ...params }; the erasers already remove a shape whole
// Rendering: one <path> per stroke, so every stroke stays crisp at every zoom and can be hit on its own.
// Storage goes through js/store-local.js only.

import * as store from './store-local.js';
import { pageAt, pagePoint, view } from './page.js';

const SVGNS = 'http://www.w3.org/2000/svg';
export const ERASE_REACH = 6;    // stroke eraser: px on screen around the pen (6 px at zoom 1)
export const AREA_SIZE = 24;     // area eraser: circle diameter, px on screen (24 px at zoom 1)
const MIN_STEP = 0.4;            // page px; closer points than this are dropped while drawing

const P = new Map();             // page id -> { strokes (by seq), byId, svg, els (id -> path), w, h }
const boxes = new WeakMap();     // record -> [x0, y0, x1, y1], its points' bounding box
const T = { tool: 'pen', style: { colour: '#1F2328', width: 2.5, dash: 'solid', opacity: 1 } };
let doOp = (op) => op.redo();
let G = null;                    // the gesture in progress
let ring = null, deskEl = null, deskBox = null;

const uuid = () => crypto.randomUUID();
const r1 = (v) => Math.round(v * 10) / 10;
const bySeq = (a, b) => a.seq - b.seq;

export function initInk(o) { if (o.doOp) doOp = o.doOp; deskEl = o.desk || document.getElementById('desk'); }
export function setTool(tool, style) { T.tool = tool; if (style) T.style = { ...style }; }
export function tool() { return { tool: T.tool, style: { ...T.style } }; }

// ---------------------------------------------------------------- the model
function data(id) {
  let d = P.get(id);
  if (!d) {
    const strokes = store.load(id).sort(bySeq);
    d = { strokes, byId: new Map(strokes.map((r) => [r.id, r])), svg: null, els: new Map(), w: 0, h: 0 };
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
    for (let k = 0; k <= 48; k++) { const a = (k / 48) * 2 * Math.PI; out.push([d.cx + rx * Math.cos(a), d.cy + ry * Math.sin(a)]); }
    return out;
  }
  return [];
}
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
  el.setAttribute('stroke', s.colour || '#1F2328');
  el.setAttribute('stroke-width', String(w));
  el.setAttribute('stroke-linejoin', 'round');
  el.setAttribute('class', rec.kind);
  if (rec.kind === 'highlighter') {
    el.setAttribute('stroke-linecap', 'round');
    el.setAttribute('stroke-opacity', String(s.opacity ?? 0.4));
    el.style.mixBlendMode = 'multiply';
  } else {
    el.setAttribute('stroke-linecap', 'round');
    if (s.opacity !== undefined && s.opacity !== 1) el.setAttribute('stroke-opacity', String(s.opacity));
  }
  if (s.dash === 'dashed') el.setAttribute('stroke-dasharray', dashOf(w));
  else el.removeAttribute('stroke-dasharray');
}
function makeEl(rec) {
  const el = document.createElementNS(SVGNS, 'path');
  el.dataset.id = rec.id;
  styleEl(el, rec);
  el.setAttribute('d', dOf(rec));
  return el;
}
function buildLayer(d, w, h) {
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'ink');
  const frag = document.createDocumentFragment();
  for (const rec of d.strokes) { const el = makeEl(rec); d.els.set(rec.id, el); frag.appendChild(el); }
  svg.appendChild(frag);
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
      for (const id of rm) { d.byId.delete(id); const el = d.els.get(id); if (el) { el.remove(); d.els.delete(id); } }
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
      const next = d.strokes[lo + 1];
      d.svg.insertBefore(el, next ? d.els.get(next.id) || null : null);
    }
  }
  schedule(pageId);
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
  const step = G.kind === 'area' ? AREA_SIZE / 4 : 3;
  const [lx, ly] = G.last || [cx, cy], n = Math.max(1, Math.ceil(Math.hypot(cx - lx, cy - ly) / step));
  for (let k = G.last ? 1 : n; k <= n; k++) eraseHere(lx + (cx - lx) * k / n, ly + (cy - ly) * k / n);
  G.last = [cx, cy];
  if (G.kind === 'area') showRing(cx, cy);
}

function down(e) {
  const at = pageAt(e.clientX, e.clientY);
  if (!at) return false;
  if (T.tool === 'pen' || T.tool === 'highlighter') {
    const d = data(at.id);
    if (!d.svg) return false;
    const s = T.style;
    const style = T.tool === 'pen'
      ? { colour: s.colour, width: s.width, dash: s.dash || 'solid', opacity: 1 }
      : { colour: s.colour, width: s.width, dash: 'solid', opacity: s.opacity };
    const rec = { id: uuid(), page_id: at.id, seq: 0, kind: T.tool, style, data: { points: [[r1(at.x), r1(at.y)]] } };
    const el = makeEl(rec);
    d.svg.appendChild(el);
    G = { kind: 'draw', index: at.index, page: at.id, rec, el };
    return true;
  }
  if (T.tool === 'eraser' || T.tool === 'area') {
    deskBox = deskEl.getBoundingClientRect();
    G = { kind: T.tool, z: view().z, changes: new Map(), last: null };
    eraseTo(e.clientX, e.clientY);
    return true;
  }
  return false;                                                    // restyle and select arrive with Part B
}
function move(events) {
  if (!G) return;
  if (G.kind === 'draw') {
    const pts = G.rec.data.points;
    for (const ev of events) {
      const [x, y] = pagePoint(G.index, ev.clientX, ev.clientY), l = pts[pts.length - 1];
      if (Math.hypot(x - l[0], y - l[1]) >= MIN_STEP) pts.push([r1(x), r1(y)]);
    }
    G.el.setAttribute('d', pathD(pts));
    return;
  }
  for (const ev of events) eraseTo(ev.clientX, ev.clientY);
}
function up(e) {
  const g = G; G = null;
  if (!g) return;
  if (g.kind === 'draw') {
    g.rec.seq = Date.now();
    data(g.page).els.set(g.rec.id, g.el);
    doOp(changeOp([{ page: g.page, removed: [], added: [g.rec] }]));
    return;
  }
  hideRing();
  const changes = [];
  g.changes.forEach((c, page) => { if (c.removed.size || c.added.size) changes.push({ page, removed: [...c.removed.values()], added: [...c.added.values()] }); });
  if (changes.length) doOp(changeOp(changes));
}
export const hook = { down, move, up };
