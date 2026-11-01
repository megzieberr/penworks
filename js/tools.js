// PenWorks U5a (pw-v8a): the Tools button's little panel and the sticky RULER (tools round 1, her design of 1 Nov 2026,
// briefs/U5-TOOLS-DESIGN.md). The ruler's engine is the constructions app's (..\constructions\index.html: rGeo,
// hitRuler, stickRuler, snapTurn, edgeTargets, snapEdgeX and the three ruler gestures), moved from its infinite canvas
// at 32 px per cm onto a PenWorks page at CM px per cm (K below scales its sizes).
//
// - The Tools button (#drawToolsBtn, under the calculator in js/tray.js) opens a small panel beside the tray, on the
//   desk side like the pen panel: Ruler, Compass, Protractor, Axes. Ruler and Compass are live, Protractor and Axes
//   are disabled ("Next round"). A row is a toggle: the tool comes out on the CURRENT page, a second tap puts it away
//   (wherever it is). The panel closes on a press anywhere but itself and its button (the pen panel's rule), on Escape
//   and on a resize. The button is pressed (aria-pressed, .on) while any tool is out. Not role="dialog": app.js
//   overlayOpen() treats any visible dialog as an overlay (calcpanel.js has the same reasons).
// - The tools are NOT strokes. Each page holding a tool has ONE <svg class="toolLayer"> on its sheet, over the ink, in
//   page px (the pinch scales paper, ink and tools together, so a ruler cm is a paper cm), overflow visible (a tool may
//   hang off the page); each tool is a <g> in its page's layer (g.ruler, g.compass). Never saved, never in undo, never
//   in a thumb, a PDF or strokesOf(). Leaving the note puts every tool away; a stack rebuilt without a tool's page puts
//   that tool away. A tool stays on its own page when she scrolls to another one.
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
// - Stick points, on a tool's page: both ends of every line, arrow, arc and curved arrow, and every crossing of two
//   of them or of a fixed circle; never freehand ink. Reach: HANDLE_REACH screen px (20), so HANDLE_REACH / zoom page px
//   (U5c: the constructions app's reaches now, see below).
//
// U5b (tools round 2): the COMPASS, Mathspad-exact (her ruling 23 Oct), the constructions app's cGeo,
// hitCompass, drawCompass and the four compass gestures, in SVG on the page, scaled by K like the ruler.
// - One size: arm ARM (7.5 cm), width R_MIN .. R_MAX, handle HANDLE. Out it comes at a width of 5 cm, hinge up, the
//   needle at (0.42, 0.68) of the CURRENT page; put away and brought out again it comes out fresh there.
// - Zones in hitCompass's order: lock (the padlock button), draw (the hinge and the handle above it), move (the needle
//   and its arm), width (the pencil, its arm, the knee, the clamp). The radii are the constructions app's x K, never
//   smaller on screen than at zoom 1 when zoomed out (x 1 / zoom below zoom 1).
// - Gestures: lock flips the lock and does nothing else; move carries the whole compass (the NEEDLE snaps to a stick
//   point in reach, a ring marks it while it sits there); width, unlocked, sets the width to the pencil tip's distance
//   from the needle and turns the compass to the pen (the TIP snaps to a stick point in reach, a ring and a "5.0 cm"
//   pill while it is set); width, locked, turns the compass about the needle, the width kept; draw turns it about the
//   needle and the arc only GROWS (lo and hi: the smallest and largest angle reached). Halos on move, draw and lock;
//   none on the pencil, and nothing at the pencil's tip while an arc is swung (she watches the arc grow).
// - The arc is a live shape (ink.liveShape) in the current ink style while it is swung, and on the lift lands as ONE
//   shape record: { type: 'arc', x1, y1, xm, ym, x2, y2, fixed: true } (lo, half way, hi) under a full turn, or
//   { type: 'circle', cx, cy, r, fixed: true } from a full turn on; a swing of 0.004 rad or less lands nothing.
// - Ruler and compass may be out together (a real desk): the tool touched LAST (or brought out last) is on top and
//   gets the press where they overlap.
//
// U5c (pw-v8c): the constructions app's FEEL for sticking (her tablet pass on the U5b build: the needle left no mark and the
// ruler would not stick to a circle's centre).
// - A FIXED arc or circle (the compass's) has its centre as a stick point (derived from the record, nothing stored, so a
//   Select move, turn or resize carries it) and ink.js draws its needle mark there (ink.needleOf). Snapped (not fixed)
//   arcs and circles: no centre, no mark. Stick points closer than 0.75 page px are one.
// - snapPt (the needle and the pencil tip) is the constructions app's snapPoint: the nearest stick POINT within PT_REACH,
//   else the nearest point ON a stick curve (a line or arrow's segment, a fixed arc along its sweep, a fixed circle)
//   within CURVE_REACH. The ruler's edge (stickRuler) sticks to points only, EDGE_STICK (a ruler line's ends: U5a's 20).
// - Reaches are the constructions app's, screen px / zoom: PT_REACH 16, CURVE_REACH 9, EDGE_STICK 14, TURN_PULL 10 (a
//   point that close to a stuck ruler's edge line pulls the turn through it); a free turn clicks onto a 45 degree step
//   only within TURN_SNAP (1.2 degrees).
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
const PT_REACH = 16, CURVE_REACH = 9;                // U5c: screen px: a stick point, else a point on a stick curve (needle, tip)
const EDGE_STICK = 14;                               // U5c: screen px: the ruler's edge (and a ruler line's end) to a stick point
const LINE_END = 14;                                 // U5c: screen px: a ruler line's end to a point on the edge (the constructions app's 14)
const TURN_PULL = 10;                                // U5c: screen px: a point this near a stuck ruler's edge line pulls the turn
const ON_EDGE = 2.5;                                 // screen px: a stick point this close to an edge lies on it
const MIN_PIVOT = 24;                                // screen px: a stick point this close to the pivot never sets a turn
const TURN_SNAP = 1.2 * PI / 180;                    // U5c: a turn within 1.2 degrees of a 45 degree step lands on the step
const MIN_LINE = 1.5;                                // page px: a shorter ruler line lands nothing
const RING_BLUE = '#2F4BB8';                         // the handle ring's blue (ink.js SEL_BLUE)
const HALO = 'rgba(242,179,61,.55)';
// the compass (the constructions app's COMPASS_L, R_MIN, R_MAX, HANDLE and pencil length, x K)
const ARM = 240 * K, R_MIN = 6 * K, R_MAX = 1.85 * ARM, HANDLE = 56 * K, PENCIL = 192 * K, C_START = 160 * K;
const MIN_SWEEP = 0.004;                             // radians: a swing this small or smaller lands nothing
const C_ARM = '#8FA3D6', C_EDGE = '#1E2A44', C_OFF = '#A9B1C2', C_DARK = '#2A2F3A';

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
let C = null;          // the compass when out: { page, c1: [x, y] (the needle), r (width), th (needle to pencil tip, radians), locked, stuck: [x, y] | null }
let G = null;          // the gesture in progress (G.tool: 'ruler' or 'compass')
let hov = null;        // the tool and zone under the hovering pen: { tool, zone }
let order = [];        // the tools out, bottom to top (the last touched is on top)
const SP = new Map();  // page id -> its stick points { pts: [[x, y]], curves: [seg | arc] }, until its records change
const layers = new Map();   // page id -> its <svg class="toolLayer">
let gR = null, hi = null, rings = [], degEl = null;      // the ruler's group, knob halos, rings and degree pill
let gC = null, cRings = [], cmEl = null;                 // the compass's group, rings (needle, pencil tip) and width pill

// ---------------------------------------------------------------- geometry
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
const unit = (a) => { const l = Math.hypot(a[0], a[1]) || 1; return [a[0] / l, a[1] / l]; };
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
function distToSeg(p, a, b) {
  const ab = sub(b, a), L = dot(ab, ab), t = L ? clamp(dot(sub(p, a), ab) / L, 0, 1) : 0;
  return dist(p, add(a, mul(ab, t)));
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
  if (a.sw >= TAU) return true;                                    // a whole circle
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
  const d = sub(s.b, s.a), f = sub(s.a, a.c), A = dot(d, d), B = 2 * dot(f, d), C2 = dot(f, f) - a.r * a.r;
  const disc = B * B - 4 * A * C2;
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
// U5b: a FIXED circle (a compass's full turn) is a curve too: no ends, its crossings are stick points
// U5c: a FIXED arc's or circle's centre (the needle's spot) is a stick point; points closer than 0.75 px are one
function stickData(pageId) {
  if (SP.has(pageId)) return SP.get(pageId);
  const pts = [], curves = [];
  const push = (p) => { for (const q of pts) if (dist(p, q) < 0.75) return; pts.push(p); };
  for (const r of ink.strokesOf(pageId)) {
    if (r.kind !== 'shape' || !r.data) continue;
    const d = r.data;
    if (d.type === 'circle') {
      if (d.fixed && [d.cx, d.cy, d.r].every(Number.isFinite) && d.r > 0) {
        curves.push({ t: 'arc', c: [d.cx, d.cy], r: d.r, t1: 0, sw: TAU });
        push([d.cx, d.cy]);
      }
      continue;
    }
    if (d.type !== 'line' && d.type !== 'arrow' && d.type !== 'arc' && d.type !== 'carrow') continue;
    const a = [d.x1, d.y1], b = [d.x2, d.y2];
    if (![a, b].every((q) => Number.isFinite(q[0]) && Number.isFinite(q[1]))) continue;
    push(a); push(b);
    const arc = d.type === 'line' || d.type === 'arrow' ? null : arcOf(d);
    curves.push(arc || { t: 'seg', a, b });
    if (arc && d.type === 'arc' && d.fixed) push(arc.c.slice());
  }
  for (let i = 0; i < curves.length; i++) for (let j = i + 1; j < curves.length; j++) for (const p of cross(curves[i], curves[j])) push(p);
  const out = { page: pageId, pts, curves };
  SP.set(pageId, out);
  return out;
}
// the point on a stick curve nearest p (a segment: its closest point; an arc: p put on its circle, only where the arc
// runs), or null (the constructions app's nearestOnCurve)
function nearestOnCurve(p, s) {
  if (s.t === 'seg') {
    const ab = sub(s.b, s.a), L = dot(ab, ab), t = L ? clamp(dot(sub(p, s.a), ab) / L, 0, 1) : 0;
    return add(s.a, mul(ab, t));
  }
  const v = sub(p, s.c), d = Math.hypot(v[0], v[1]);
  if (d < 1e-9) return null;
  const q = add(s.c, mul(v, s.r / d));
  return onArc(s, q) ? q : null;
}
// U5c, the constructions app's snapPoint: the stick point nearest q within PT_REACH, else the point ON a stick curve
// nearest q within CURVE_REACH (skip: points never to take), else q itself
function snapPt(pageId, q, z, skip) {
  const { pts, curves } = stickData(pageId);
  let best = null, bd = PT_REACH / z;
  for (const s of pts) {
    if (skip && skip(s)) continue;
    const d = dist(s, q);
    if (d < bd) { bd = d; best = s; }
  }
  if (best) return { p: best.slice(), hit: true };
  bd = CURVE_REACH / z;
  for (const s of curves) {
    const c = nearestOnCurve(q, s);
    if (!c || (skip && skip(c))) continue;
    const d = dist(c, q);
    if (d < bd) { bd = d; best = c; }
  }
  return best ? { p: best, hit: true } : { p: q, hit: false };
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
  let best = null, bd = EDGE_STICK / z;
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
    let best = null, bd = TURN_PULL / z;
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
  let best = null, bd = LINE_END / z;
  for (const t of targets) { const d = Math.abs(t - x); if (d < bd) { bd = d; best = t; } }
  if (best !== null) return { x: clamp(best, -RULER_PAD, RULER_LEN + RULER_PAD), hit: true };
  return { x: clamp(x, -RULER_PAD, RULER_LEN + RULER_PAD), hit: false };
}

// ---------------------------------------------------------------- the compass (ported: cGeo, hitCompass)
function cGeo(c) {
  const u = dirOf(c.th), r = c.r, h = Math.sqrt(Math.max(0, ARM * ARM - r * r / 4));
  const a = normAng(c.th), left = a > PI / 2 && a < 1.5 * PI;
  const up = left ? [-u[1], u[0]] : [u[1], -u[0]];                // the hinge always sits on the upper side
  const W2 = (lx, ly) => add(c.c1, add(mul(u, lx), mul(up, ly)));
  const c1 = c.c1, c3 = W2(r, 0), m = W2(r / 2, 0), c2 = W2(r / 2, h);
  const half = Math.atan2(r / 2, h), pa = half - PI / 14;          // the pencil sits a little more upright than its arm
  const pd = add(mul(u, -Math.sin(pa)), mul(up, Math.cos(pa)));
  const yk = 0.3 * h, knee = W2(r - (r / 2) * (yk / (h || 1)), yk), clampP = W2(r - Math.tan(pa) * yk, yk);
  return { u, up, h, c1, c2, c3, m, lockC: mid(c2, m), hEnd: add(c2, mul(up, HANDLE)), pd, knee, clampP, pTop: add(c3, mul(pd, PENCIL)),
    L1: W2(r / 4, h / 2), L2: W2(3 * r / 4, h / 2) };
}
function hitCompass(p, z) {
  const g = cGeo(C), s = K * Math.max(1, 1 / z);                  // the constructions app's radii; zoomed out, a steady size on screen
  if (dist(p, g.lockC) <= 26 * s) return 'lock';
  if (dist(p, g.c2) <= 40 * s || distToSeg(p, g.c2, g.hEnd) <= 16 * s) return 'draw';
  if (dist(p, g.c1) <= 30 * s || distToSeg(p, g.c1, g.c2) <= 20 * s) return 'move';
  if (dist(p, g.c3) <= 30 * s || distToSeg(p, g.c2, g.knee) <= 20 * s || distToSeg(p, g.knee, g.clampP) <= 16 * s
      || distToSeg(p, g.c3, g.pTop) <= 16 * s) return 'width';
  return null;
}

// ---------------------------------------------------------------- drawing them (one svg per page, page px)
function sv(tag, at = {}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in at) e.setAttribute(k, typeof at[k] === 'number' ? f3(at[k]) : at[k]);
  return e;
}
function ringEl() { return sv('circle', { class: 'stickRing', fill: 'rgba(255,255,255,.6)', stroke: RING_BLUE, display: 'none' }); }
function buildRuler() {
  gR = sv('g', { class: 'ruler' });
  hi = {};
  const mid0 = RULER_W / 2;
  for (const [side, kx] of [['turnL', -RULER_PAD - KNOB_OFF], ['turnR', RULER_LEN + RULER_PAD + KNOB_OFF]]) {
    const ex = side === 'turnL' ? -RULER_PAD : RULER_LEN + RULER_PAD;
    gR.append(sv('rect', { x: Math.min(kx, ex), y: mid0 - 4 * K, width: Math.abs(ex - kx), height: 8 * K, fill: 'rgba(59,111,182,.55)' }));
    hi[side] = sv('circle', { cx: kx, cy: mid0, r: KNOB_R + 8 * K, fill: HALO, display: 'none' });
    gR.append(hi[side], sv('circle', { class: 'knob', 'data-side': side, cx: kx, cy: mid0, r: KNOB_R, fill: '#3B6FB6' }));
    const r = 8 * K, a0 = -PI * 0.15, a1 = PI * 1.25, s = [kx + r * Math.cos(a0), mid0 + r * Math.sin(a0)], e = [kx + r * Math.cos(a1), mid0 + r * Math.sin(a1)];
    const w = { fill: 'none', stroke: '#FFFFFF', 'stroke-width': 2 * K, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
    gR.append(sv('path', { ...w, d: `M${f3(s[0])} ${f3(s[1])}A${f3(r)} ${f3(r)} 0 1 1 ${f3(e[0])} ${f3(e[1])}` }),
      sv('path', { ...w, d: `M${f3(e[0] - 4.5 * K)} ${f3(e[1] + 0.5 * K)}L${f3(e[0])} ${f3(e[1])}L${f3(e[0] + 0.5 * K)} ${f3(e[1] + 4.5 * K)}` }));
  }
  gR.append(sv('rect', { class: 'body', x: -RULER_PAD, y: 0, width: RULER_LEN + 2 * RULER_PAD, height: RULER_W, rx: 7 * K,
    fill: 'rgba(158,196,240,.34)', stroke: 'rgba(59,111,182,.95)', 'stroke-width': 1.2 * K }));
  // No light on the edges (her ask 1 Nov 16:39): the amber edge line sat over the line she was drawing and hid where it
  // started and where it was. The knobs keep their halo; the edge band shows nothing, the growing line is the feedback.
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
  rings = [ringEl(), ringEl()];
  degEl = document.createElement('div');
  degEl.className = 'selDeg toolDeg';                              // the selection turn's own pill
}
function buildCompass() {
  gC = sv('g', { class: 'compass' });
  cRings = [ringEl(), ringEl()];                                   // the needle's point, the pencil tip's while the width is set
  cmEl = document.createElement('div');
  cmEl.className = 'selDeg toolCm';                                // the width in cm while it is set (a measure of the tool)
}
const sheetOf = (pageId) => [...document.querySelectorAll('#stack .sheet')].find((s) => s.dataset.id === pageId) || null;
function pageIndex(pageId) { const s = sheetOf(pageId); return s ? +s.dataset.index - 1 : -1; }
function curSheet() { const i = current(); return i >= 0 ? document.querySelector(`#stack .sheet[data-index="${i + 1}"]`) : null; }
function layerFor(sheet) {                                         // the page's tool layer, made when a tool first lands there
  let l = layers.get(sheet.dataset.id);
  if (!l) { l = sv('svg', { class: 'toolLayer', 'aria-hidden': 'true' }); layers.set(sheet.dataset.id, l); }
  const w = parseFloat(sheet.style.width), h = parseFloat(sheet.style.height);
  l.setAttribute('width', w); l.setAttribute('height', h); l.setAttribute('viewBox', `0 0 ${w} ${h}`);
  if (l.parentNode !== sheet) sheet.appendChild(l);
  return l;
}
const partsOf = (t) => (t === 'ruler' ? [gR, ...rings] : [gC, ...cRings]);
const pillOf = (t) => (t === 'ruler' ? degEl : cmEl);
function restack() {                                               // groups bottom to top in `order`, every ring over them
  for (const t of order) { const g = partsOf(t)[0]; if (g && g.parentNode) g.parentNode.appendChild(g); }
  for (const t of order) { const [g, ...rs] = partsOf(t); if (g && g.parentNode) for (const r of rs) g.parentNode.appendChild(r); }
}
function prune() {                                                 // a layer with no tool left goes
  for (const [id, l] of layers) if (!l.querySelector('g.ruler, g.compass')) { l.remove(); layers.delete(id); }
}
function mountTool(t, sheet) {
  const l = layerFor(sheet);
  for (const e of partsOf(t)) l.appendChild(e);
  const pill = pillOf(t);
  if (pill.parentNode !== sheet) sheet.appendChild(pill);
  restack(); prune();
}
function unmountTool(t) {
  for (const e of partsOf(t)) if (e) e.remove();
  const pill = pillOf(t);
  if (pill) { pill.classList.remove('on'); pill.remove(); }
  prune();
}
function toFront(t) { order = order.filter((x) => x !== t).concat(t); restack(); }
function zoneOf(t) {
  if (G) return G.tool === t ? G.zone : null;
  return hov && hov.tool === t ? hov.zone : null;
}
function putRing(c, q, z) {
  if (!q) { c.setAttribute('display', 'none'); return; }
  c.setAttribute('cx', f3(q[0])); c.setAttribute('cy', f3(q[1])); c.setAttribute('r', f3(7 / z)); c.setAttribute('stroke-width', f3(2 / z));
  c.setAttribute('display', 'inline');
}
function renderRuler() {
  if (!R || !gR || !gR.isConnected) return;
  const z = view().z, gg = G && G.tool === 'ruler' ? G : null;
  gR.setAttribute('transform', `translate(${f3(R.o[0])} ${f3(R.o[1])}) rotate(${f3(R.ang * 180 / PI)})`);
  const zone = zoneOf('ruler');
  for (const k in hi) hi[k].setAttribute('display', k === zone ? 'inline' : 'none');
  const marks = [];
  if (gg && gg.k === 'draw') { if (gg.snapA) marks.push(gg.snapA); if (gg.snap) marks.push(gg.snap); }
  else { if (R.stuck) marks.push(R.stuck.p); if (gg && gg.k === 'turn' && gg.target) marks.push(gg.target); }
  rings.forEach((c, i) => putRing(c, marks[i], z));
  if (gg && gg.k === 'turn') {                                     // the turn's degrees beside the knob that turns it
    const g = rGeo(R), knob = g.knobs[gg.zone === 'turnL' ? 0 : 1], at = add(knob, mul(g.n, -(KNOB_R + 26 / z)));
    degEl.textContent = (Math.round(normAng(-R.ang) * 180 / PI) % 180) + '°';
    degEl.style.left = f3(at[0] - 22 / z) + 'px'; degEl.style.top = f3(at[1]) + 'px';
    degEl.style.transform = `scale(${f3(1 / z)}) translateY(-50%)`;
    degEl.classList.add('on');
  } else degEl.classList.remove('on');
}
// the compass in SVG, the constructions app's drawCompass part for part (capsule = a round-capped edge line under a fill line)
function renderCompass() {
  if (!C || !gC || !gC.isConnected) return;
  const z = view().z, g = cGeo(C), zone = zoneOf('compass'), gg = G && G.tool === 'compass' ? G : null, kids = [];
  const seg = (a, b, at) => sv('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], ...at });
  const capsule = (a, b, w, fill, edge, part) => {
    kids.push(seg(a, b, { stroke: edge, 'stroke-width': w + 2.5 * K, 'stroke-linecap': 'round', 'data-part': part }),
      seg(a, b, { stroke: fill, 'stroke-width': w, 'stroke-linecap': 'round', 'data-part': part }));
  };
  const halo = (a, b, w) => kids.push(seg(a, b, { class: 'halo', stroke: HALO, 'stroke-width': w, 'stroke-linecap': 'round' }));
  const poly = (pts, fill, edge, lw, part) => kids.push(sv('polygon', { points: pts.map((q) => f3(q[0]) + ',' + f3(q[1])).join(' '),
    fill, stroke: edge || 'none', 'stroke-width': lw || 0, 'stroke-linejoin': 'round', 'data-part': part }));
  const disc = (c, r, at) => kids.push(sv('circle', { cx: c[0], cy: c[1], r, ...at }));
  if (zone === 'move') halo(g.c2, g.c1, 32 * K);
  if (zone === 'draw') halo(g.c2, g.hEnd, 34 * K);                 // no halo on the pencil or its arm (the width zone)
  const locked = C.locked || !!(gg && gg.k === 'cDraw');
  // the lock bar and its button with the padlock
  kids.push(seg(g.L1, g.L2, { class: 'lockBar', stroke: locked ? C_EDGE : C_OFF, 'stroke-width': (locked ? 9 : 6) * K, 'stroke-linecap': 'butt' }));
  if (locked) kids.push(seg(g.L1, g.L2, { stroke: C_ARM, 'stroke-width': 6 * K, 'stroke-linecap': 'butt' }));
  if (zone === 'lock') disc(g.lockC, 22 * K, { class: 'halo', fill: HALO });
  disc(g.lockC, 15 * K, { class: 'lockBtn', fill: locked ? C_ARM : '#FFFFFF', stroke: locked ? C_EDGE : C_OFF, 'stroke-width': 2.5 * K });
  const col = locked ? C_EDGE : C_OFF, lk = sv('g', { class: 'padlock', 'data-locked': locked ? '1' : '0',
    transform: `translate(${f3(g.lockC[0])} ${f3(g.lockC[1])}) scale(${f3(K)})` });
  const sh = locked ? 'M-4 -2A4 4 0 0 1 4 -2'
    : `M${f3(3 + 4 * Math.cos(PI * 1.15))} ${f3(-4 + 4 * Math.sin(PI * 1.15))}A4 4 0 0 1 ${f3(3 + 4 * Math.cos(TAU * 0.98))} ${f3(-4 + 4 * Math.sin(TAU * 0.98))}`;
  lk.append(sv('path', { d: sh, fill: 'none', stroke: col, 'stroke-width': 1.8 }), sv('rect', { x: -5.5, y: -2, width: 11, height: 8, fill: col }));
  kids.push(lk);
  // the needle's arm and the needle
  const na = unit(sub(g.c2, g.c1)), ns = add(g.c1, mul(na, 20 * K)), nn = [-na[1], na[0]];
  capsule(g.c2, ns, 13 * K, C_ARM, C_EDGE, 'needleArm');
  poly([add(ns, mul(nn, 3.2 * K)), add(ns, mul(nn, -3.2 * K)), g.c1], '#C9CED8', C_EDGE, 0.8 * K, 'needle');
  // the pencil (drawPencil), its point in her current ink colour; while an arc is swung the pencil side is see-through:
  // on a swing toward the hinge side the pencil lies right along the arc it has just drawn and would hide it
  const side0 = kids.length, pd = g.pd, n = [-pd[1], pd[0]], w = 6.5 * K, at = (d, s) => add(add(g.c3, mul(pd, d * K)), mul(n, s));
  const B = '#8A5A00', lw = K, ink0 = inkStyle().colour;
  poly([at(24, -w), at(176, -w), at(176, w), at(24, w)], '#F2B33D', B, lw, 'pencil');
  kids.push(seg(at(24, 0), at(176, 0), { stroke: 'rgba(138,90,0,.35)', 'stroke-width': K }));
  poly([at(176, -w), at(182, -w), at(182, w), at(176, w)], '#C9CED8', '#6B7280', lw, 'pencil');
  poly([at(182, -w), at(192, -w), at(192, w), at(182, w)], '#F29BAA', B, lw, 'pencil');
  poly([at(24, -w), at(24, w), at(6, 1.8 * K), at(6, -1.8 * K)], '#F3D6A4', B, lw, 'pencil');
  poly([at(6, -1.8 * K), at(6, 1.8 * K), at(0, 0)], ink0, ink0, 0.5 * K, 'tip');
  // the pencil's arm, the knee, the clamp
  capsule(g.c2, g.knee, 13 * K, C_ARM, C_EDGE, 'pencilArm');
  capsule(g.knee, g.clampP, 9 * K, C_ARM, C_EDGE, 'pencilArm');
  disc(g.clampP, 6 * K, { fill: C_EDGE, 'data-part': 'clamp' });
  const side = sv('g', { class: 'pencilSide', opacity: gg && gg.k === 'cDraw' ? '0.4' : '1' });
  side.append(...kids.splice(side0));
  kids.push(side);
  // the handle and the hinge with its screw
  capsule(g.c2, g.hEnd, 11 * K, C_DARK, C_EDGE, 'handle');
  disc(g.c2, 16 * K, { class: 'hinge', fill: C_DARK, stroke: C_EDGE, 'stroke-width': 1.5 * K });
  disc(g.c2, 5.5 * K, { fill: '#D9DCE3' });
  const x = g.c2[0], y = g.c2[1], q = 3 * K;
  kids.push(sv('path', { d: `M${f3(x - q)} ${f3(y - q)}L${f3(x + q)} ${f3(y + q)}M${f3(x + q)} ${f3(y - q)}L${f3(x - q)} ${f3(y + q)}`, stroke: C_DARK, 'stroke-width': 1.2 * K }));
  gC.replaceChildren(...kids);
  // the rings: the needle on its stick point; the pencil tip while the width is set (never while an arc is swung)
  putRing(cRings[0], C.stuck, z);
  putRing(cRings[1], gg && gg.k === 'cWidth' ? gg.snap : null, z);
  if (gg && gg.k === 'cWidth') {                                   // the width in cm above the handle
    const p = add(g.hEnd, mul(g.up, 22 * K + 14 / z));             // the pill's middle, clear of the handle's end
    cmEl.textContent = (C.r / CM).toFixed(1) + ' cm';
    cmEl.style.left = f3(p[0]) + 'px'; cmEl.style.top = f3(p[1]) + 'px';
    cmEl.style.transform = `scale(${f3(1 / z)}) translate(-50%, -50%)`;
    cmEl.classList.add('on');
  } else cmEl.classList.remove('on');
}
function render() { renderRuler(); renderCompass(); }

// ---------------------------------------------------------------- out and away
function paint() {
  const any = !!(R || C);
  if (btn) { btn.classList.toggle('on', any); btn.setAttribute('aria-pressed', any ? 'true' : 'false'); }
  if (rowBtn.ruler) rowBtn.ruler.setAttribute('aria-pressed', R ? 'true' : 'false');
  if (rowBtn.compass) rowBtn.compass.setAttribute('aria-pressed', C ? 'true' : 'false');
}
function rulerOut() {
  const sheet = curSheet();
  if (!sheet) return;
  if (!gR) buildRuler();
  const w = parseFloat(sheet.style.width), h = parseFloat(sheet.style.height);
  R = { page: sheet.dataset.id, o: [(w - RULER_LEN) / 2, Math.round(h * 0.72)], ang: 0, stuck: null };
  mountTool('ruler', sheet); toFront('ruler');
  render(); paint();
}
function rulerAway() {
  if (G && G.tool === 'ruler') { if (G.live) G.live.drop(); G = null; }
  R = null;
  if (hov && hov.tool === 'ruler') hov = null;
  order = order.filter((t) => t !== 'ruler');
  if (gR) unmountTool('ruler');
  paint();
}
function compassOut() {
  const sheet = curSheet();
  if (!sheet) return;
  if (!gC) buildCompass();
  const w = parseFloat(sheet.style.width), h = parseFloat(sheet.style.height);
  C = { page: sheet.dataset.id, c1: [w * 0.42, h * 0.68], r: C_START, th: 0, locked: false, stuck: null };
  mountTool('compass', sheet); toFront('compass');
  render(); paint();
}
function compassAway() {
  if (G && G.tool === 'compass') { if (G.live) G.live.drop(); G = null; }
  C = null;
  if (hov && hov.tool === 'compass') hov = null;
  order = order.filter((t) => t !== 'compass');
  if (gC) unmountTool('compass');
  paint();
}
export function putAway() { rulerAway(); compassAway(); }
function toggleRuler() { if (R) rulerAway(); else rulerOut(); }
function toggleCompass() { if (C) compassAway(); else compassOut(); }

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
    else if (id === 'compass') b.addEventListener('click', toggleCompass);
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
// the topmost tool under a client point: { tool, zone, idx, p, z } or null (the last touched first)
function hitAt(cx, cy) {
  const z = view().z;
  for (let i = order.length - 1; i >= 0; i--) {
    const t = order[i], T = t === 'ruler' ? R : C;
    if (!T) continue;
    const idx = pageIndex(T.page);
    if (idx < 0) continue;
    const p = pagePoint(idx, cx, cy), zone = t === 'ruler' ? hitRuler(p, z) : hitCompass(p, z);
    if (zone) return { tool: t, zone, idx, p, z };
  }
  return null;
}
export function penDown(e) {
  if (G || e.button === 2 || (e.buttons & 2)) return false;       // the pen button: never a tool gesture
  const h = hitAt(e.clientX, e.clientY);
  if (!h) return false;
  hov = null;
  toFront(h.tool);
  const { zone, idx, p, z } = h;
  if (h.tool === 'compass') {
    if (zone === 'lock') { C.locked = !C.locked; G = { k: 'noop', tool: 'compass', zone, idx }; }
    else if (zone === 'move') G = { k: 'cMove', tool: 'compass', zone, idx, off: sub(C.c1, p), snap: null };
    else if (zone === 'width') G = { k: C.locked ? 'cTurn' : 'cWidth', tool: 'compass', zone, idx, rel: sub(cGeo(C).c3, p), prev: p, snap: null };
    else G = { k: 'cDraw', tool: 'compass', zone, idx, prev: p, lo: C.th, hi: C.th, style: inkStyle(), id: crypto.randomUUID(), live: null, liveType: null };
    render();
    return true;
  }
  const g = rGeo(R);
  if (zone === 'move') G = { k: 'move', tool: 'ruler', zone, idx, off: sub(R.o, p) };
  else if (zone === 'turnL' || zone === 'turnR') {
    const pivot = R.stuck ? R.stuck.p.slice() : g.centre, [lx, ly] = g.toL(pivot);
    G = { k: 'turn', tool: 'ruler', zone, idx, pivot, lx, ly, raw: R.ang, prev: p, stuck: !!R.stuck, target: null };
  } else {
    const base = zone === 'edgeA' ? R.o.slice() : add(R.o, mul(g.n, RULER_W)), targets = edgeTargets(base, g.u, g.n, z);
    const sx = snapEdgeX(dot(sub(p, base), g.u), targets, z);
    G = { k: 'draw', tool: 'ruler', zone, idx, base, u: g.u, targets, xs: sx.x, xe: sx.x, snapA: sx.hit ? add(base, mul(g.u, sx.x)) : null, snap: null,
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
// the compass's arc so far: from lo to hi on the circle about the needle (half way = the middle point), a circle from a
// full turn on
function arcRec(g) {
  const c = C.c1, r = C.r, sw = g.hi - g.lo, at = (a) => [c[0] + r * Math.cos(a), c[1] + r * Math.sin(a)];
  let data;
  if (sw >= TAU) data = { type: 'circle', cx: r2(c[0]), cy: r2(c[1]), r: r2(r), fixed: true };
  else {
    const a = at(g.lo), m = at((g.lo + g.hi) / 2), b = at(g.hi);
    data = { type: 'arc', x1: r2(a[0]), y1: r2(a[1]), xm: r2(m[0]), ym: r2(m[1]), x2: r2(b[0]), y2: r2(b[1]), fixed: true };
  }
  return { id: g.id, page_id: C.page, seq: 0, kind: 'shape', style: { ...g.style }, data };
}
function liveArc(g, rec) {                                         // the live shape follows the record (an arc becomes a circle at a full turn)
  if (g.live && g.liveType !== rec.data.type) { g.live.drop(); g.live = null; }
  if (!g.live) { g.live = ink.liveShape(C.page, rec); g.liveType = rec.data.type; }
  else g.live.set(rec);
  return g.live;
}
function moveCompass(g, p, z) {
  if (g.k === 'cMove') {
    const sn = snapPt(C.page, add(p, g.off), z);
    C.c1 = sn.p; g.snap = sn.hit ? sn.p : null; C.stuck = g.snap ? g.snap.slice() : null;
    return;
  }
  if (g.k === 'cWidth') {                                          // the tip follows the pen, the width is the tip to the needle
    const sn = snapPt(C.page, add(p, g.rel), z, (s) => dist(s, C.c1) < R_MIN), v = sub(sn.p, C.c1), d = Math.hypot(v[0], v[1]);
    if (d > 1e-6) C.th = Math.atan2(v[1], v[0]);
    C.r = clamp(d, R_MIN, R_MAX);
    g.snap = sn.hit && d <= R_MAX ? sn.p : null;
    return;
  }
  if (g.k === 'cTurn' || g.k === 'cDraw') {                        // turn about the needle; drawing, the arc only grows
    C.th += sweep(g.prev, p, C.c1); g.prev = p;
    if (g.k === 'cDraw') { g.lo = Math.min(g.lo, C.th); g.hi = Math.max(g.hi, C.th); }
  }
}
function moveTo(g, ev) {
  const z = view().z, p = pagePoint(g.idx, ev.clientX, ev.clientY);
  if (g.tool === 'compass') { moveCompass(g, p, z); return; }
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
const toolOf = (g) => (g.tool === 'ruler' ? R : C);
function penMove(events) {
  const g = G;
  if (!g || !toolOf(g)) return;
  if (g.k !== 'noop') for (const ev of events) moveTo(g, ev);
  if (g.k === 'draw' && Math.abs(g.xe - g.xs) >= 1) {              // the live line, in the ink's own layer and look
    const rec = lineRec(g);
    if (!g.rec) g.rec = rec;
    if (!g.live) g.live = ink.liveShape(R.page, rec);
    else g.live.set(rec);
  }
  if (g.k === 'cDraw' && g.hi - g.lo > MIN_SWEEP) liveArc(g, arcRec(g));   // the live arc, in the ink's own layer and look
  render();
}
function penUp(e, cancelled) {
  const g = G; G = null;
  if (!g || !toolOf(g)) { render(); return; }
  const lifted = !cancelled && e && Number.isFinite(e.clientX);
  if (g.k === 'draw') {
    if (lifted) moveTo(g, e);                                      // the line reaches where the pen lifted
    if (!cancelled && Math.abs(g.xe - g.xs) >= MIN_LINE) {
      const rec = lineRec(g);
      if (!g.live) g.live = ink.liveShape(R.page, rec);
      if (g.live) g.live.commit(rec);                               // ONE undo step, the way a snapped shape lands
    } else if (g.live) g.live.drop();
  } else if (g.k === 'cDraw') {
    if (lifted) moveTo(g, e);                                      // the arc reaches where the pen lifted
    if (!cancelled && g.hi - g.lo > MIN_SWEEP) {
      const rec = arcRec(g), live = liveArc(g, rec);
      if (live) live.commit(rec);                                   // ONE undo step, as the ruler's line
    } else if (g.live) g.live.drop();
    C.th = normAng(C.th);
  } else if (g.k !== 'noop' && lifted) moveTo(g, e);
  render();
}
function penHover(e) {
  if (G || (!R && !C)) return;
  const h = hitAt(e.clientX, e.clientY), next = h ? { tool: h.tool, zone: h.zone } : null;
  if ((next && next.tool) !== (hov && hov.tool) || (next && next.zone) !== (hov && hov.zone)) { hov = next; render(); }
}
export const hook = { down: penDown, move: penMove, up: penUp, hover: penHover };

// ---------------------------------------------------------------- the app's calls
// ink.js onChange (through app.js): a page's records changed, so its stick points are read again; a stuck point that
// is gone lets go
export function changed(pageId) {
  SP.delete(pageId);
  const sd = stickData(pageId), gone = (q) => !sd.pts.some((s) => dist(s, q) < 0.75);
  const offCurves = (q) => !sd.curves.some((s) => { const c = nearestOnCurve(q, s); return c && dist(c, q) < 0.75; });
  if (R && R.page === pageId && R.stuck && !G) { if (gone(R.stuck.p)) R.stuck = null; }
  if (C && C.page === pageId && C.stuck && !G) { if (gone(C.stuck) && offCurves(C.stuck)) C.stuck = null; }   // U5c: the needle may sit on a curve
  if ((R && R.page === pageId) || (C && C.page === pageId)) render();
}
// page.js rebuilt the stack (app.js onSheets): each tool goes back on its page's new sheet, or away when its page is gone
export function attach(sheets) {
  if (!R && !C) return;
  if (G && G.live) { G.live.drop(); G = null; }
  SP.clear();
  for (const [t, T, away] of [['ruler', R, rulerAway], ['compass', C, compassAway]]) {
    if (!T) continue;
    const sheet = sheets.find((s) => s.dataset.id === T.page);
    if (!sheet) away(); else mountTool(t, sheet);
  }
  render();
}
export function rulerState() {                                     // for the checks: a copy, or null when the ruler is away
  return R ? { page: R.page, o: R.o.slice(), ang: R.ang, stuck: R.stuck ? { p: R.stuck.p.slice(), edge: R.stuck.edge } : null,
               len: RULER_LEN, w: RULER_W, pad: RULER_PAD, knobR: KNOB_R, knobOff: KNOB_OFF, gesture: G && G.tool === 'ruler' ? G.k : null } : null;
}
export function compassState() {                                   // for the checks: a copy, or null when the compass is away
  if (!C) return null;
  const g = cGeo(C), cp = (q) => q.slice();
  return { page: C.page, c1: cp(C.c1), r: C.r, th: C.th, locked: C.locked, stuck: C.stuck ? cp(C.stuck) : null,
           arm: ARM, rMin: R_MIN, rMax: R_MAX, handle: HANDLE, pencil: PENCIL, k: K,
           geo: { c2: cp(g.c2), c3: cp(g.c3), lockC: cp(g.lockC), hEnd: cp(g.hEnd), knee: cp(g.knee), clampP: cp(g.clampP), pTop: cp(g.pTop), up: cp(g.up) },
           gesture: G && G.tool === 'compass' ? G.k : null, lo: G && G.k === 'cDraw' ? G.lo : null, hi: G && G.k === 'cDraw' ? G.hi : null,
           order: order.slice() };
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
  if (deskEl) deskEl.addEventListener('pointerleave', () => { if (hov && !G) { hov = null; render(); } });
  // a colour or ink tool picked on the tray: the compass's pencil point takes her new ink colour
  const tray = document.getElementById('tray');
  if (tray) tray.addEventListener('click', () => { if (C) setTimeout(renderCompass, 0); });
  // leaving the note puts every tool away (a note opens with none out)
  new MutationObserver(() => {
    if (!document.body.classList.contains('noteMode')) { closePanel(); if (R || C) putAway(); }
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  // the rings and the pills keep their size on screen: drawn again when the zoom changes
  const stack = document.getElementById('stack');
  if (stack) new MutationObserver(() => { if (R || C) render(); }).observe(stack, { attributes: true, attributeFilter: ['data-zoom'] });
  paint();
}
