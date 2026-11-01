// PenWorks U5a (pw-v8a): the Tools button's little panel and the sticky RULER (tools round 1, her design of 1 Nov 2026,
// briefs/U5-TOOLS-DESIGN.md). The ruler's engine is the constructions app's (..\constructions\index.html: rGeo,
// hitRuler, stickRuler, snapTurn, edgeTargets, snapEdgeX and the three ruler gestures), moved from its infinite canvas
// at 32 px per cm onto a PenWorks page at CM px per cm (K below scales its sizes).
//
// - The Tools button (#drawToolsBtn, under the calculator in js/tray.js) opens a small panel beside the tray, on the
//   desk side like the pen panel: Ruler, Compass, Protractor, Axes. Only Ruler is live this round, the other three are
//   disabled ("Next round"). A row is a toggle: the tool comes out on the CURRENT page, a second tap puts it away
//   (wherever it is). The panel closes on a press anywhere but itself and its button (the pen panel's rule), on Escape
//   and on a resize. The button is pressed (aria-pressed, .on) while any tool is out. Not role="dialog": app.js
//   overlayOpen() treats any visible dialog as an overlay (calcpanel.js has the same reasons).
// - The ruler is NOT a stroke. It is an <svg class="toolLayer"> on its page's sheet, over the ink, in page px (the
//   pinch scales paper, ink and ruler together, so a ruler cm is a paper cm), overflow visible (it may hang off the page).
//   Never saved, never in undo, never in a thumb, a PDF or strokesOf(). Leaving the note puts it away; a stack rebuilt
//   without its page puts it away. It stays on its own page when she scrolls to another one.
// - One size: 20 cm long, 2.2 cm wide, mm and cm ticks on both long edges, cm numbers, the two round turn knobs past
//   the ends. No length readout (her ruling). Out it comes across the lower third of the page, level.
// - The PEN only (pen or mouse): app.js hands page.js an ink object whose down() asks penDown() first; a press this
//   module takes is followed here (move, up) until the lift. A finger never reaches it (page.js pans and pinches).
// - Zones, as hitRuler: a knob turns (about the stuck point when stuck, else the centre; through a stick point when
//   stuck, else onto 45 degree steps; the degrees show in the selection's pill), a band along each long edge (14 px
//   inside to 26 px outside on screen) draws along that edge, the rest of the body moves it (an edge within reach of a
//   stick point sticks to it, a ring marks the point).
// - A line drawn along an edge lands as ONE shape record { type: 'line', x1, y1, x2, y2, fixed: true } in the current
//   ink tool's style (the pen's for select, an eraser or restyle), through ink.liveShape (snapNow's own commit).
// - Stick points, on the ruler's page: both ends of every line, arrow, arc and curved arrow, and every crossing of two
//   of them; never freehand ink. Reach: HANDLE_REACH screen px (20), so HANDLE_REACH / zoom page px.
import { CM, view, pagePoint, current } from './page.js';
import * as ink from './ink.js';
import { trayState } from './tray.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const PI = Math.PI, TAU = 2 * PI;
const K = CM / 32;                                   // the constructions app's px (32 per cm) to page px
const MM = CM / 10;
const RULER_LEN = 20 * CM, RULER_W = 2.2 * CM, RULER_PAD = 14 * K, KNOB_R = 17 * K, KNOB_OFF = 28 * K;
const EDGE_IN = 14, EDGE_OUT = 26;                   // the edge band, screen px inside and outside an edge
const KNOB_REACH = 9;                                // screen px past a knob's rim that still turns it
const STICK = ink.HANDLE_REACH;                      // stick reach, screen px (the Select tool's 20)
const ON_EDGE = 2.5;                                 // screen px: a stick point this close to an edge lies on it
const MIN_PIVOT = 24;                                // screen px: a stick point this close to the pivot never sets a turn
const TURN_SNAP = 6 * PI / 180;                      // a turn within 6 degrees of a 45 degree step lands on the step
const MIN_LINE = 1.5;                                // page px: a shorter ruler line lands nothing
const RING_BLUE = '#2F4BB8';                         // the handle ring's blue (ink.js SEL_BLUE)

const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
const ROWS = [
  ['ruler', 'Ruler', ICON + '<rect x="3" y="8.5" width="18" height="7" rx="1"/><path d="M7 8.5V11M10.5 8.5v1.6M14 8.5V11M17.5 8.5v1.6"/></svg>'],
  ['compass', 'Compass', ICON + '<circle cx="12" cy="4.6" r="1.6"/><path d="M11.2 6.1L7.5 19.5M12.8 6.1l3.7 13.4M8.9 14.5h6.2"/></svg>'],
  ['protractor', 'Protractor', ICON + '<path d="M3 17.5a9 9 0 0 1 18 0z"/><path d="M12 17.5v-3"/></svg>'],
  ['axes', 'Axes', ICON + '<path d="M12 21V3M3 12h18M9.5 5.5L12 3l2.5 2.5M18.5 9.5L21 12l-2.5 2.5"/></svg>'],
];

let btn = null, panel = null, deskEl = null;
const rowBtn = {};
let R = null;          // the ruler when out: { page (id), o: [x, y] (edge A's 0 mark, page px), ang (radians), stuck: { p, edge } | null }
let G = null;          // the ruler gesture in progress
let hoverZone = null;  // the zone under the hovering pen
let SP = null;         // the stick points of one page: { page, pts: [[x, y]], curves: [seg | arc] }
let layer = null, gR = null, hi = null, rings = [], degEl = null;

// ---------------------------------------------------------------- geometry
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const dirOf = (a) => [Math.cos(a), Math.sin(a)];
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const normAng = (a) => ((a % TAU) + TAU) % TAU;
const wrapPi = (a) => { const t = normAng(a + PI); return t - PI; };
const r2 = (v) => Math.round(v * 100) / 100;
const f3 = (v) => String(Math.round(v * 1000) / 1000);
function sweep(prev, p, pivot) {
  const a0 = Math.atan2(prev[1] - pivot[1], prev[0] - pivot[0]), a1 = Math.atan2(p[1] - pivot[1], p[0] - pivot[0]);
  return wrapPi(a1 - a0);
}

// the circle through an arc's three points, or null when they lie in a line (ink.js draws that straight)
function arcOf(d) {
  const ax = d.x1, ay = d.y1, bx = d.xm, by = d.ym, cx = d.x2, cy = d.y2, chord = Math.hypot(cx - ax, cy - ay);
  if (!chord || Math.abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / chord < 0.5) return null;
  const D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  const a2 = ax * ax + ay * ay, b2 = bx * bx + by * by, c2 = cx * cx + cy * cy;
  const ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / D, oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / D;
  const t1 = Math.atan2(ay - oy, ax - ox), tm = Math.atan2(by - oy, bx - ox), t2 = Math.atan2(cy - oy, cx - ox);
  const toEnd = normAng(t2 - t1), sw = normAng(tm - t1) <= toEnd ? toEnd : toEnd - TAU;
  return { t: 'arc', c: [ox, oy], r: Math.hypot(ax - ox, ay - oy), t1, sw };
}
function onArc(a, q) {                                             // point q (on the circle) lies on the arc's span
  const th = Math.atan2(q[1] - a.c[1], q[0] - a.c[0]), e = 1e-7;
  return a.sw >= 0 ? normAng(th - a.t1) <= a.sw + e || normAng(th - a.t1) >= TAU - e
                   : normAng(a.t1 - th) <= -a.sw + e || normAng(a.t1 - th) >= TAU - e;
}
function segSeg(s, t) {
  const r = sub(s.b, s.a), q = sub(t.b, t.a), den = r[0] * q[1] - r[1] * q[0];
  if (Math.abs(den) < 1e-12) return [];
  const w = sub(t.a, s.a), u = (w[0] * q[1] - w[1] * q[0]) / den, v = (w[0] * r[1] - w[1] * r[0]) / den, e = 1e-9;
  return u >= -e && u <= 1 + e && v >= -e && v <= 1 + e ? [add(s.a, mul(r, u))] : [];
}
function segArc(s, a) {
  const d = sub(s.b, s.a), f = sub(s.a, a.c), A = dot(d, d), B = 2 * dot(f, d), C = dot(f, f) - a.r * a.r;
  const disc = B * B - 4 * A * C;
  if (!A || disc < 0) return [];
  const sq = Math.sqrt(disc), out = [], e = 1e-9;
  for (const u of disc ? [(-B - sq) / (2 * A), (-B + sq) / (2 * A)] : [-B / (2 * A)]) {
    if (u < -e || u > 1 + e) continue;
    const p = add(s.a, mul(d, u));
    if (onArc(a, p)) out.push(p);
  }
  return out;
}
function arcArc(a, b) {
  const dd = dist(a.c, b.c);
  if (!dd || dd > a.r + b.r || dd < Math.abs(a.r - b.r)) return [];
  const x = (dd * dd + a.r * a.r - b.r * b.r) / (2 * dd), h2 = a.r * a.r - x * x, h = h2 > 0 ? Math.sqrt(h2) : 0;
  const u = mul(sub(b.c, a.c), 1 / dd), m = add(a.c, mul(u, x)), n = [-u[1], u[0]];
  const ps = h ? [add(m, mul(n, h)), sub(m, mul(n, h))] : [m];
  return ps.filter((p) => onArc(a, p) && onArc(b, p));
}
function cross(s, t) {
  if (s.t === 'seg' && t.t === 'seg') return segSeg(s, t);
  if (s.t === 'seg') return segArc(s, t);
  if (t.t === 'seg') return segArc(t, s);
  return arcArc(s, t);
}

// ---------------------------------------------------------------- stick points (one page, cached until its records change)
function stickData(pageId) {
  if (SP && SP.page === pageId) return SP;
  const pts = [], curves = [];
  for (const r of ink.strokesOf(pageId)) {
    if (r.kind !== 'shape' || !r.data) continue;
    const d = r.data;
    if (d.type !== 'line' && d.type !== 'arrow' && d.type !== 'arc' && d.type !== 'carrow') continue;
    const a = [d.x1, d.y1], b = [d.x2, d.y2];
    if (![a, b].every((q) => Number.isFinite(q[0]) && Number.isFinite(q[1]))) continue;
    pts.push(a, b);
    curves.push(d.type === 'line' || d.type === 'arrow' ? { t: 'seg', a, b } : arcOf(d) || { t: 'seg', a, b });
  }
  for (let i = 0; i < curves.length; i++) for (let j = i + 1; j < curves.length; j++) pts.push(...cross(curves[i], curves[j]));
  SP = { page: pageId, pts, curves };
  return SP;
}

// ---------------------------------------------------------------- the ruler (ported: rGeo, hitRuler, stickRuler, snapTurn, edgeTargets, snapEdgeX)
function rGeo(r) {
  const u = dirOf(r.ang), n = [-u[1], u[0]];                       // n points from the ticked edge A into the ruler
  const L2W = (lx, ly) => add(r.o, add(mul(u, lx), mul(n, ly)));
  return { u, n, L2W, toL: (p) => { const v = sub(p, r.o); return [dot(v, u), dot(v, n)]; },
    knobs: [L2W(-RULER_PAD - KNOB_OFF, RULER_W / 2), L2W(RULER_LEN + RULER_PAD + KNOB_OFF, RULER_W / 2)],
    centre: L2W(RULER_LEN / 2, RULER_W / 2) };
}
function hitRuler(p, z) {
  const g = rGeo(R);
  if (dist(p, g.knobs[0]) <= KNOB_R + KNOB_REACH / z) return 'turnL';
  if (dist(p, g.knobs[1]) <= KNOB_R + KNOB_REACH / z) return 'turnR';
  const [x, y] = g.toL(p);
  if (x < -RULER_PAD || x > RULER_LEN + RULER_PAD) return null;
  const bi = Math.min(EDGE_IN / z, RULER_W / 3), bo = EDGE_OUT / z;   // zoomed far out the body still keeps a middle to move it by
  if (y >= -bo && y <= bi) return 'edgeA';
  if (y >= RULER_W - bi && y <= RULER_W + bo) return 'edgeB';
  if (y >= 0 && y <= RULER_W) return 'move';
  return null;
}
function stickRuler(z) {
  const g = rGeo(R);
  let best = null, bd = STICK / z;
  for (const q of stickData(R.page).pts) {
    const [x, y] = g.toL(q);
    if (x < -RULER_PAD || x > RULER_LEN + RULER_PAD) continue;
    for (const [edge, ey] of [['A', 0], ['B', RULER_W]]) { const d = y - ey; if (Math.abs(d) < bd) { bd = Math.abs(d); best = { q, edge, d }; } }
  }
  if (best) { R.o = add(R.o, mul(g.n, best.d)); R.stuck = { p: best.q.slice(), edge: best.edge }; } else R.stuck = null;
}
function snapTurn(raw, pivot, lx, usePoints, z) {
  if (usePoints) {
    const u = dirOf(raw), n = [-u[1], u[0]];
    let best = null, bd = STICK / z;
    for (const q of stickData(R.page).pts) {
      const v = sub(q, pivot);
      if (Math.hypot(v[0], v[1]) < MIN_PIVOT / z) continue;
      const along = lx + dot(v, u);
      if (along < -RULER_PAD || along > RULER_LEN + RULER_PAD) continue;
      const perp = Math.abs(dot(v, n));
      if (perp < bd) { bd = perp; best = q; }
    }
    if (best) {
      const v = sub(best, pivot);
      let a = Math.atan2(v[1], v[0]);
      if (dot(v, u) < 0) a += PI;
      return { ang: raw + wrapPi(a - raw), target: best };
    }
  }
  const step = PI / 4, k = Math.round(raw / step);
  if (Math.abs(raw - k * step) <= TURN_SNAP) return { ang: k * step, target: null };
  return { ang: raw, target: null };
}
// along-the-edge positions to snap a ruler line's ends to: stick points lying on the edge, and where the edge crosses a
// line or an arc
function edgeTargets(base, u, n, z) {
  const xs = [], a = add(base, mul(u, -RULER_PAD)), b = add(base, mul(u, RULER_LEN + RULER_PAD)), { pts, curves } = stickData(R.page);
  for (const q of pts) { const v = sub(q, base); if (Math.abs(dot(v, n)) <= ON_EDGE / z) xs.push(dot(v, u)); }
  const edge = { t: 'seg', a, b };
  for (const s of curves) for (const q of cross(edge, s)) xs.push(dot(sub(q, base), u));
  return xs;
}
function snapEdgeX(x, targets, z) {
  let best = null, bd = STICK / z;
  for (const t of targets) { const d = Math.abs(t - x); if (d < bd) { bd = d; best = t; } }
  if (best !== null) return { x: clamp(best, -RULER_PAD, RULER_LEN + RULER_PAD), hit: true };
  return { x: clamp(x, -RULER_PAD, RULER_LEN + RULER_PAD), hit: false };
}

// ---------------------------------------------------------------- drawing it (an svg on its page's sheet, page px)
function sv(tag, at = {}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in at) e.setAttribute(k, typeof at[k] === 'number' ? f3(at[k]) : at[k]);
  return e;
}
function buildLayer() {
  layer = sv('svg', { class: 'toolLayer', 'aria-hidden': 'true' });
  gR = sv('g', { class: 'ruler' });
  hi = {};
  const mid = RULER_W / 2;
  for (const [side, kx] of [['turnL', -RULER_PAD - KNOB_OFF], ['turnR', RULER_LEN + RULER_PAD + KNOB_OFF]]) {
    const ex = side === 'turnL' ? -RULER_PAD : RULER_LEN + RULER_PAD;
    gR.append(sv('rect', { x: Math.min(kx, ex), y: mid - 4 * K, width: Math.abs(ex - kx), height: 8 * K, fill: 'rgba(59,111,182,.55)' }));
    hi[side] = sv('circle', { cx: kx, cy: mid, r: KNOB_R + 8 * K, fill: 'rgba(242,179,61,.55)', display: 'none' });
    gR.append(hi[side], sv('circle', { class: 'knob', 'data-side': side, cx: kx, cy: mid, r: KNOB_R, fill: '#3B6FB6' }));
    const r = 8 * K, a0 = -PI * 0.15, a1 = PI * 1.25, s = [kx + r * Math.cos(a0), mid + r * Math.sin(a0)], e = [kx + r * Math.cos(a1), mid + r * Math.sin(a1)];
    const w = { fill: 'none', stroke: '#FFFFFF', 'stroke-width': 2 * K, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
    gR.append(sv('path', { ...w, d: `M${f3(s[0])} ${f3(s[1])}A${f3(r)} ${f3(r)} 0 1 1 ${f3(e[0])} ${f3(e[1])}` }),
      sv('path', { ...w, d: `M${f3(e[0] - 4.5 * K)} ${f3(e[1] + 0.5 * K)}L${f3(e[0])} ${f3(e[1])}L${f3(e[0] + 0.5 * K)} ${f3(e[1] + 4.5 * K)}` }));
  }
  gR.append(sv('rect', { class: 'body', x: -RULER_PAD, y: 0, width: RULER_LEN + 2 * RULER_PAD, height: RULER_W, rx: 7 * K,
    fill: 'rgba(158,196,240,.34)', stroke: 'rgba(59,111,182,.95)', 'stroke-width': 1.2 * K }));
  for (const [edge, y] of [['edgeA', 0], ['edgeB', RULER_W]]) {
    hi[edge] = sv('line', { x1: -RULER_PAD, y1: y, x2: RULER_LEN + RULER_PAD, y2: y, stroke: 'rgba(242,179,61,.9)', 'stroke-width': 5 * K, 'stroke-linecap': 'round', display: 'none' });
    gR.append(hi[edge]);
  }
  // mm and cm ticks on BOTH long edges (edge A's grow down from y 0, edge B's up from the ruler's width)
  const cmD = [], mmD = [];
  for (let i = 0; i <= 200; i++) {
    const x = f3(i * MM), len = (i % 10 === 0 ? 16 : i % 5 === 0 ? 11 : 7) * K;
    const d = `M${x} 0V${f3(len)}M${x} ${f3(RULER_W)}V${f3(RULER_W - len)}`;
    (i % 10 === 0 ? cmD : mmD).push(d);
  }
  gR.append(sv('path', { class: 'ticks', d: mmD.join(''), stroke: '#1E2A44', 'stroke-width': 0.8 * K, fill: 'none' }),
    sv('path', { class: 'ticks cm', d: cmD.join(''), stroke: '#1E2A44', 'stroke-width': 1.1 * K, fill: 'none' }));
  const font = { fill: '#1E2A44', 'font-family': 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', 'font-weight': '600',
    'text-anchor': 'middle', 'dominant-baseline': 'central' };
  for (let c = 0; c <= 20; c++) { const t = sv('text', { ...font, x: c * CM, y: 27 * K, 'font-size': 11 * K }); t.textContent = String(c); gR.append(t); }
  const cm = sv('text', { ...font, x: RULER_LEN / 2, y: 48 * K, 'font-size': 10 * K }); cm.textContent = 'cm'; gR.append(cm);
  layer.append(gR);
  rings = [0, 1].map(() => { const c = sv('circle', { class: 'stickRing', fill: 'rgba(255,255,255,.6)', stroke: RING_BLUE, display: 'none' }); layer.append(c); return c; });
  degEl = document.createElement('div');
  degEl.className = 'selDeg toolDeg';                              // the selection turn's own pill
}
const sheetOf = (pageId) => [...document.querySelectorAll('#stack .sheet')].find((s) => s.dataset.id === pageId) || null;
function pageIndex(pageId) { const s = sheetOf(pageId); return s ? +s.dataset.index - 1 : -1; }
function mount(sheet) {
  if (!layer) buildLayer();
  const w = parseFloat(sheet.style.width), h = parseFloat(sheet.style.height);
  layer.setAttribute('width', w); layer.setAttribute('height', h); layer.setAttribute('viewBox', `0 0 ${w} ${h}`);
  if (layer.parentNode !== sheet) sheet.appendChild(layer);
  if (degEl.parentNode !== sheet) sheet.appendChild(degEl);
}
function render() {
  if (!R || !layer || !layer.isConnected) return;
  const z = view().z;
  gR.setAttribute('transform', `translate(${f3(R.o[0])} ${f3(R.o[1])}) rotate(${f3(R.ang * 180 / PI)})`);
  const zone = G ? G.zone : hoverZone;
  for (const k in hi) hi[k].setAttribute('display', k === zone ? 'inline' : 'none');
  const marks = [];
  if (G && G.k === 'draw') { if (G.snapA) marks.push(G.snapA); if (G.snap) marks.push(G.snap); }
  else { if (R.stuck) marks.push(R.stuck.p); if (G && G.k === 'turn' && G.target) marks.push(G.target); }
  rings.forEach((c, i) => {
    const q = marks[i];
    if (!q) { c.setAttribute('display', 'none'); return; }
    c.setAttribute('cx', f3(q[0])); c.setAttribute('cy', f3(q[1])); c.setAttribute('r', f3(7 / z)); c.setAttribute('stroke-width', f3(2 / z));
    c.setAttribute('display', 'inline');
  });
  if (G && G.k === 'turn') {                                       // the turn's degrees beside the knob that turns it
    const g = rGeo(R), knob = g.knobs[G.zone === 'turnL' ? 0 : 1], at = add(knob, mul(g.n, -(KNOB_R + 26 / z)));
    degEl.textContent = (Math.round(normAng(-R.ang) * 180 / PI) % 180) + '°';
    degEl.style.left = f3(at[0] - 22 / z) + 'px'; degEl.style.top = f3(at[1]) + 'px';
    degEl.style.transform = `scale(${f3(1 / z)}) translateY(-50%)`;
    degEl.classList.add('on');
  } else degEl.classList.remove('on');
}

// ---------------------------------------------------------------- out and away
function paint() {
  const any = !!R;
  if (btn) { btn.classList.toggle('on', any); btn.setAttribute('aria-pressed', any ? 'true' : 'false'); }
  if (rowBtn.ruler) rowBtn.ruler.setAttribute('aria-pressed', R ? 'true' : 'false');
}
function rulerOut() {
  const i = current(), sheet = i >= 0 ? document.querySelector(`#stack .sheet[data-index="${i + 1}"]`) : null;
  if (!sheet) return;
  const w = parseFloat(sheet.style.width), h = parseFloat(sheet.style.height);
  R = { page: sheet.dataset.id, o: [(w - RULER_LEN) / 2, Math.round(h * 0.72)], ang: 0, stuck: null };
  mount(sheet);
  render(); paint();
}
function rulerAway() {
  if (G && G.live) G.live.drop();
  G = null; R = null; hoverZone = null;
  if (layer) layer.remove();
  if (degEl) { degEl.classList.remove('on'); degEl.remove(); }
  paint();
}
export function putAway() { rulerAway(); }
function toggleRuler() { if (R) rulerAway(); else rulerOut(); }

// ---------------------------------------------------------------- the panel
function place() {                                                 // beside the tray on its desk side, level with the button (tray.js place)
  const tray = document.getElementById('tray'), tb = tray.getBoundingClientRect(), bb = btn.getBoundingClientRect(), ph = panel.offsetHeight;
  if (document.body.classList.contains('trayLeft')) { panel.style.left = tb.right + 8 + 'px'; panel.style.right = ''; }
  else { panel.style.right = Math.max(8, innerWidth - tb.left + 8) + 'px'; panel.style.left = ''; }
  panel.style.top = Math.max(8, Math.min(innerHeight - ph - 8, bb.top + bb.height / 2 - ph / 2)) + 'px';
}
function buildPanel() {
  panel = document.createElement('div');
  panel.id = 'toolsPanel'; panel.className = 'panel toolsPanel'; panel.hidden = true;
  panel.setAttribute('role', 'group'); panel.setAttribute('aria-label', 'Tools');
  for (const [id, label, icon] of ROWS) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'trow'; b.id = 'trow-' + id; b.dataset.tool = id;
    b.setAttribute('aria-pressed', 'false');
    b.innerHTML = icon + '<span>' + label + '</span>';
    if (id === 'ruler') b.addEventListener('click', toggleRuler);
    else { b.disabled = true; b.title = 'Next round'; }
    rowBtn[id] = b;
    panel.append(b);
  }
  panel.addEventListener('contextmenu', (e) => e.preventDefault());   // the S Pen's button never opens a menu here
  document.body.append(panel);
}
export function openPanel() { if (!panel) return; panel.hidden = false; place(); paint(); }
export function closePanel() { if (panel && !panel.hidden) panel.hidden = true; }
function togglePanel() { if (panel.hidden) openPanel(); else closePanel(); }

// ---------------------------------------------------------------- the pen (app.js asks penDown first; move and up follow)
function inkStyle() {                                              // the current ink tool's style; the pen's for select, erasers, restyle
  const s = trayState();
  if (s.tool === 'highlighter') { const h = s.highlighter; return { colour: h.colour, width: h.width, dash: 'solid', opacity: h.opacity }; }
  const p = s.pen;
  return { colour: p.colour, width: p.width, dash: p.dash || 'solid', opacity: 1 };
}
export function penDown(e) {
  if (!R || G || e.button === 2 || (e.buttons & 2)) return false;   // the pen button: never a tool gesture
  const idx = pageIndex(R.page);
  if (idx < 0) return false;
  const z = view().z, p = pagePoint(idx, e.clientX, e.clientY), zone = hitRuler(p, z);
  if (!zone) return false;
  hoverZone = null;
  const g = rGeo(R);
  if (zone === 'move') G = { k: 'move', zone, idx, off: sub(R.o, p) };
  else if (zone === 'turnL' || zone === 'turnR') {
    const pivot = R.stuck ? R.stuck.p.slice() : g.centre, [lx, ly] = g.toL(pivot);
    G = { k: 'turn', zone, idx, pivot, lx, ly, raw: R.ang, prev: p, stuck: !!R.stuck, target: null };
  } else {
    const base = zone === 'edgeA' ? R.o.slice() : add(R.o, mul(g.n, RULER_W)), targets = edgeTargets(base, g.u, g.n, z);
    const sx = snapEdgeX(dot(sub(p, base), g.u), targets, z);
    G = { k: 'draw', zone, idx, base, u: g.u, targets, xs: sx.x, xe: sx.x, snapA: sx.hit ? add(base, mul(g.u, sx.x)) : null, snap: null,
          style: inkStyle(), live: null, rec: null };
  }
  render();
  return true;
}
function lineRec(g) {
  const a = add(g.base, mul(g.u, g.xs)), b = add(g.base, mul(g.u, g.xe));
  return { id: g.rec ? g.rec.id : crypto.randomUUID(), page_id: R.page, seq: 0, kind: 'shape', style: { ...g.style },
           data: { type: 'line', x1: r2(a[0]), y1: r2(a[1]), x2: r2(b[0]), y2: r2(b[1]), fixed: true } };
}
function moveTo(g, ev) {
  const z = view().z, p = pagePoint(g.idx, ev.clientX, ev.clientY);
  if (g.k === 'move') { R.o = add(p, g.off); stickRuler(z); return; }
  if (g.k === 'turn') {
    g.raw += sweep(g.prev, p, g.pivot); g.prev = p;
    const s = snapTurn(g.raw, g.pivot, g.lx, g.stuck, z);
    R.ang = s.ang; g.target = s.target;
    const u = dirOf(R.ang), n = [-u[1], u[0]];
    R.o = sub(sub(g.pivot, mul(u, g.lx)), mul(n, g.ly));
    return;
  }
  const sx = snapEdgeX(dot(sub(p, g.base), g.u), g.targets, z);
  g.xe = sx.x;
  g.snap = sx.hit ? add(g.base, mul(g.u, g.xe)) : null;
}
function penMove(events) {
  const g = G;
  if (!g || !R) return;
  for (const ev of events) moveTo(g, ev);
  if (g.k === 'draw' && Math.abs(g.xe - g.xs) >= 1) {              // the live line, in the ink's own layer and look
    const rec = lineRec(g);
    if (!g.rec) g.rec = rec;
    if (!g.live) g.live = ink.liveShape(R.page, rec);
    else g.live.set(rec);
  }
  render();
}
function penUp(e, cancelled) {
  const g = G; G = null;
  if (!g || !R) { render(); return; }
  if (g.k === 'draw') {
    if (!cancelled && e && Number.isFinite(e.clientX)) moveTo(g, e);   // the line reaches where the pen lifted
    if (!cancelled && Math.abs(g.xe - g.xs) >= MIN_LINE) {
      const rec = lineRec(g);
      if (!g.live) g.live = ink.liveShape(R.page, rec);
      if (g.live) g.live.commit(rec);                               // ONE undo step, the way a snapped shape lands
    } else if (g.live) g.live.drop();
  } else if (!cancelled && e && Number.isFinite(e.clientX)) moveTo(g, e);
  render();
}
function penHover(e) {
  if (!R || G) return;
  const idx = pageIndex(R.page);
  const z = view().z, zone = idx < 0 ? null : hitRuler(pagePoint(idx, e.clientX, e.clientY), z);
  if (zone !== hoverZone) { hoverZone = zone; render(); }
}
export const hook = { down: penDown, move: penMove, up: penUp, hover: penHover };

// ---------------------------------------------------------------- the app's calls
// ink.js onChange (through app.js): a page's records changed, so its stick points are read again; a stuck point that
// is gone lets go
export function changed(pageId) {
  if (SP && SP.page === pageId) SP = null;
  if (R && R.page === pageId && R.stuck && !G) {
    if (!stickData(pageId).pts.some((q) => dist(q, R.stuck.p) < 0.75)) R.stuck = null;
    render();
  }
}
// page.js rebuilt the stack (app.js onSheets): the ruler goes back on its page's new sheet, or away when its page is gone
export function attach(sheets) {
  if (!R) return;
  const sheet = sheets.find((s) => s.dataset.id === R.page);
  if (!sheet) { rulerAway(); return; }
  if (G && G.live) { G.live.drop(); G = null; }
  SP = null;
  mount(sheet);
  render();
}
export function rulerState() {                                     // for the checks: a copy, or null when the ruler is away
  return R ? { page: R.page, o: R.o.slice(), ang: R.ang, stuck: R.stuck ? { p: R.stuck.p.slice(), edge: R.stuck.edge } : null,
               len: RULER_LEN, w: RULER_W, pad: RULER_PAD, knobR: KNOB_R, knobOff: KNOB_OFF, gesture: G ? G.k : null } : null;
}

export function initTools({ trayBtn, desk }) {
  btn = trayBtn; deskEl = desk || document.getElementById('desk');
  buildPanel();
  if (btn) btn.addEventListener('click', togglePanel);
  // the pen panel's rule: a press anywhere but the panel and its own button closes it (capture: before anything else)
  document.addEventListener('pointerdown', (e) => {
    if (!panel || panel.hidden) return;
    if (e.target.closest && e.target.closest('#toolsPanel, #drawToolsBtn')) return;
    closePanel();
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePanel(); });
  window.addEventListener('resize', closePanel);
  if (deskEl) deskEl.addEventListener('pointerleave', () => { if (hoverZone && !G) { hoverZone = null; render(); } });
  // leaving the note puts every tool away (a note opens with none out)
  new MutationObserver(() => {
    if (!document.body.classList.contains('noteMode')) { closePanel(); if (R) rulerAway(); }
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  // the rings and the pill keep their size on screen: drawn again when the zoom changes
  const stack = document.getElementById('stack');
  if (stack) new MutationObserver(() => { if (R) render(); }).observe(stack, { attributes: true, attributeFilter: ['data-zoom'] });
  paint();
}
