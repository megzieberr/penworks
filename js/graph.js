// PenWorks quick graph, unit 2 (pw-v9j; unit 2b pw-v9k: a second curve on the same axes, a curve on her axes stamp; _docs/PENWORKS-GRAPH-PLAN.md, Tool 1, build step 2; the signed-off look is
// _build/graph/graph-mock.html, panel 2). The graph's own maths and drawing; ink.js keeps it as one record and owns Select,
// the erasers and undo; tools.js lands it from the Tools panel's Graph card; pdfout.js draws the same parts.
//
// The record: kind 'graph' (the strokes table's check has allowed 'graph' since 0001_init.sql), ONE record:
//   style { colour '#000000', width 1.5, dash 'solid', opacity 1 }   the AXES' style: always black (her ruling 15 Nov 09:54)
//   data {
//     x0, y0      page px of the origin (where the y-axis meets the x-axis)
//     px, py      page px per 90 degrees across, page px per 1 unit up (a resize multiplies both)
//     axes: { on, xl, xr, yh }   the window belongs to the axes: on = axes, marks and letters shown; xl the left end in
//                 degrees (0 down to -360, the left handle), xr the right end (360), yh the height (y from -yh to yh)
//     curves: [ { kind, colour, width, dx, dy, sx, sy } ]   a LIST (pw-v9k: more curves on the same axes, newest last and
//                 drawn on top; see "unit 2b" below): kind one of KINDS, its own colour and width (the pen's when it landed), offset dx (degrees across)
//                 and dy (units up), stretch sx (across) and sy (up): y = sy * f((x - dx) / sx) + dy. 0, 0, 1, 1 for now.
//   }
// Drawn, in this order (graphParts): the axis lines and the ticks, the two heads, the marks and the letters (filled glyph
// outlines, black), then tan's asymptotes (black, dashed), then the curves (their colour). So where a number and the curve
// meet the number is BEHIND the curve, with no halo (her 15 Nov rule). Hidden axes (on false) hide the lines, the ticks,
// the heads, the marks and the letters together; the asymptotes and the curve stay.
// The marks: every 90 degrees inside the window and nothing more, never at 0 (90, 180, 270, 360; -90 .. -360 when the
// window is opened to the left), the real minus sign (U+2212). Nothing on the y-axis, no 0, no equation, no snapping.
// The text is Caveat 500 drawn as its own glyph outlines (js/caveat-glyphs.js, generated from the font file the app
// carries in fonts/), so the page, the thumbs, a shared picture and the PDF show exactly the same shapes and never wait
// for a font to load. Sizes are the mock's, as fractions of px (the mock drew px = 55): numbers 18, letters 21, ticks 9,
// a number 4 under its tick, the heads 14 long at 28 degrees.
// The curve is worked out over whatever window is showing (it never runs out) and cut exactly at the window's edges.
import { UPM, GLYPHS } from './caveat-glyphs.js';

export const KINDS = ['sin', '-sin', 'cos', '-cos', 'tan', '-tan'];
export const LABEL = { sin: 'sin', '-sin': '−sin', cos: 'cos', '-cos': '−cos', tan: 'tan', '-tan': '−tan' };
export const XL_MIN = -360;                          // the left handle stops here
const MOCK = 55;                                     // the mock's px (page px per 90 degrees)
const TK = 9 / MOCK, GAP = 4 / MOCK, FS = 18 / MOCK, FL = 21 / MOCK, DIG = 0.62, HEAD = 14 / MOCK, OVER = 0.6;
const DASH = [5 / MOCK, 4 / MOCK];                    // tan's asymptotes, on and off
const RAD = Math.PI / 180;
const r2 = (v) => Math.round(v * 100) / 100;
const s2 = (v) => String(r2(v));

// the window a new graph gets: sin and cos 1.35 up and down at 52/55 of px per unit (the mock); tan taller, 2.6 at 0.6 px
export function startWindow(kind) {
  return String(kind).endsWith('tan') ? { yh: 2.6, py: 0.6 } : { yh: 1.35, py: 52 / MOCK };
}
const base = (k) => (k === 'sin' ? (u) => Math.sin(u * RAD) : k === 'cos' ? (u) => Math.cos(u * RAD)
  : (u) => { const c = Math.cos(u * RAD); return Math.abs(c) < 1e-12 ? NaN : Math.tan(u * RAD); });
export function curveFn(c) {
  const k = String(c.kind || 'sin'), neg = k[0] === '-', f = base(neg ? k.slice(1) : k);
  const dx = +c.dx || 0, dy = +c.dy || 0, sx = +c.sx || 1, sy = c.sy === undefined ? 1 : +c.sy;
  return (x) => (neg ? -1 : 1) * sy * f((x - dx) / sx) + dy;
}
// tan's asymptotes inside [a, b] (degrees): where (x - dx) / sx = 90 + 180 k
function asymptotes(c, a, b) {
  if (!String(c.kind).endsWith('tan')) return [];
  const dx = +c.dx || 0, sx = +c.sx || 1, out = [];
  const lo = Math.min((a - dx) / sx, (b - dx) / sx), hi = Math.max((a - dx) / sx, (b - dx) / sx);
  for (let k = Math.ceil((lo - 90) / 180 - 1e-9); 90 + 180 * k <= hi + 1e-9; k++) out.push(dx + sx * (90 + 180 * k));
  return out;
}

// a line of text as Caveat glyph outlines: { d (one path, page px), w (advance), b [x0, y0, x1, y1] }; baseline y,
// anchor 'start' | 'middle' | 'end' at x
export function textPath(t, x, y, size, anchor) {
  const s = size / UPM, chars = [...String(t)].filter((ch) => GLYPHS[ch]);
  const w = chars.reduce((a, ch) => a + GLYPHS[ch][0] * s, 0);
  let cx = anchor === 'middle' ? x - w / 2 : anchor === 'end' ? x - w : x;
  const out = [], b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const ch of chars) {
    const [adv, d] = GLYPHS[ch], tok = d.match(/[A-Za-z]|-?\d+(?:\.\d+)?/g) || [];
    let odd = false, px = 0;
    for (const k of tok) {
      if (/[A-Za-z]/.test(k)) { out.push(k); odd = false; continue; }
      if (!odd) { px = cx + +k * s; out.push(s2(px)); b[0] = Math.min(b[0], px); b[2] = Math.max(b[2], px); }
      else { const py = y + +k * s; out.push(s2(py)); b[1] = Math.min(b[1], py); b[3] = Math.max(b[3], py); }
      odd = !odd;
    }
    cx += adv * s;
  }
  return { d: out.join(' ').replace(/ ?([A-Za-z]) ?/g, '$1'), w, b };
}
const minus = (v) => (v < 0 ? '−' + Math.abs(v) : String(v));

// the curve over [a, b] degrees, cut to y in [-yh, yh]: runs of points (page px). One sample about every page px across;
// where it crosses the top or the bottom the crossing is found by halving (so a steep tan meets the edge exactly, on
// the right side of an asymptote too: the halving runs from the inside sample).
// pw-v9k: the cut runs from ylo to yhi (a quick graph's -yh to yh; an axes stamp's own drawn extent, which need not be
// even about 0)
function curveRuns(f, a, b, ylo, yhi, X, Y) {
  const n = Math.max(8, Math.ceil(Math.abs(X(b) - X(a)) / 1)), runs = [];
  const inside = (v) => Number.isFinite(v) && v >= ylo && v <= yhi;
  const edge = (x1, x2) => {                         // x1 inside, x2 outside (or not finite): the last inside x
    let lo = x1, hi = x2;
    for (let k = 0; k < 40; k++) { const m = (lo + hi) / 2; if (inside(f(m))) lo = m; else hi = m; }
    const v = f(lo); return [lo, Math.max(ylo, Math.min(yhi, v))];
  };
  let cur = null, px0 = a, pv = f(a);
  if (inside(pv)) cur = [[X(a), Y(pv)]];
  for (let i = 1; i <= n; i++) {
    const x = a + (b - a) * i / n, v = f(x), ins = inside(v);
    if (ins && cur) cur.push([X(x), Y(v)]);
    else if (ins && !cur) {                           // coming in: from the edge it crossed (none across a jump of tan)
      const [ex, ev] = edge(x, px0);
      cur = [[X(ex), Y(ev)], [X(x), Y(v)]];
    } else if (!ins && cur) {                         // going out: to the edge
      const [ex, ev] = edge(px0, x); cur.push([X(ex), Y(ev)]);
      if (cur.length > 1) runs.push(cur);
      cur = null;
    }
    px0 = x; pv = v;
  }
  if (cur && cur.length > 1) runs.push(cur);
  return runs;
}
const runD = (pts) => 'M' + pts.map((q) => s2(q[0]) + ' ' + s2(q[1])).join('L');

function headPts(tip, ux, uy, len) {
  const a = 28 * RAD, c = Math.cos(a), s = Math.sin(a);
  return [[tip[0] - len * (ux * c - uy * s), tip[1] - len * (uy * c + ux * s)], [tip[0], tip[1]], [tip[0] - len * (ux * c + uy * s), tip[1] - len * (uy * c - ux * s)]];
}

// the drawing of a graph record, worked out from data every time (cached per data object). null when it cannot be drawn.
// { on, lines [[a, b]] (the axes), ticks, heads, labels [{ t, x, y, size, anchor, cls, d, b }], asym [{ x, a, b }],
//   curves [{ runs, colour, width }], box [x0, y0, x1, y1], ends (the axes' ends), left [x, y] (the left handle),
//   cross [x, y], X, Y }
const CACHE = new WeakMap();
export function graphGeom(rec) {
  const d = rec && rec.data;
  if (!d || typeof d !== 'object') return null;
  const hit = CACHE.get(d);
  if (hit) return hit;
  const g = build(d);
  if (g) CACHE.set(d, g);
  return g;
}
function build(d) {
  const px = +d.px, py = +d.py, A = d.axes || {}, xl = Math.max(XL_MIN, Math.min(0, Number.isFinite(+A.xl) ? +A.xl : 0));
  const xr = Number.isFinite(+A.xr) ? +A.xr : 360, yh = +A.yh > 0 ? +A.yh : 1.35, on = A.on !== false;
  if (![d.x0, d.y0, px, py].every(Number.isFinite) || px <= 0 || py <= 0 || !(xr > xl) || !Array.isArray(d.curves)) return null;
  const X = (deg) => d.x0 + deg / 90 * px, Y = (v) => d.y0 - v * py;
  const xL = X(xl), xR = X(xr) + OVER * px, yB = Y(-yh), yT = Y(yh) - OVER * 0.945 * px;   // the mock: 0.6 py over the top, py = 52/55 px
  const lines = [], ticks = [], heads = [], labels = [];
  if (on) {
    lines.push([[xL, d.y0], [xR, d.y0]], [[d.x0, yB], [d.x0, yT]]);
    heads.push(headPts([xR, d.y0], 1, 0, HEAD * px), headPts([d.x0, yT], 0, -1, HEAD * px));
    const fs = FS * px, base = d.y0 + (TK + GAP) * px + DIG * fs;
    for (let k = Math.ceil(xl / 90 - 1e-9); k * 90 <= xr + 1e-9; k++) {
      if (k === 0) continue;
      const x = X(k * 90);
      ticks.push([[x, d.y0], [x, d.y0 + TK * px]]);
      const t = minus(k * 90) + '°', p = textPath(t, x, base, fs, 'middle');
      labels.push({ t, x, y: base, size: fs, anchor: 'middle', cls: 'num', d: p.d, b: p.b });
    }
    const fl = FL * px;
    const lx = textPath('x', xR + 0.08 * px, d.y0 + 13.31 / MOCK * px, fl, 'start');
    labels.push({ t: 'x', x: xR + 0.08 * px, y: d.y0 + 13.31 / MOCK * px, size: fl, anchor: 'start', cls: 'letter', d: lx.d, b: lx.b });
    const ly = textPath('y', d.x0 - 7.8 / MOCK * px, yT - 4.16 / MOCK * px, fl, 'end');
    labels.push({ t: 'y', x: d.x0 - 7.8 / MOCK * px, y: yT - 4.16 / MOCK * px, size: fl, anchor: 'end', cls: 'letter', d: ly.d, b: ly.b });
  }
  const asym = [], curves = [];
  for (const c of d.curves) {
    for (const ax of asymptotes(c, xl, xr)) asym.push({ x: X(ax), a: [X(ax), Y(yh)], b: [X(ax), Y(-yh)] });
    curves.push({ runs: curveRuns(curveFn(c), xl, xr, -yh, yh, X, Y), colour: c.colour || '#000000', width: +c.width || 2.5 });
  }
  const b = [Infinity, Infinity, -Infinity, -Infinity], grow = (q) => { b[0] = Math.min(b[0], q[0]); b[1] = Math.min(b[1], q[1]); b[2] = Math.max(b[2], q[0]); b[3] = Math.max(b[3], q[1]); };
  for (const s of [...lines, ...ticks, ...heads]) s.forEach(grow);
  for (const l of labels) if (Number.isFinite(l.b[0])) { grow([l.b[0], l.b[1]]); grow([l.b[2], l.b[3]]); }
  for (const a of asym) { grow(a.a); grow(a.b); }
  for (const c of curves) for (const r of c.runs) r.forEach(grow);
  if (!Number.isFinite(b[0])) { grow([xL, Y(yh)]); grow([X(xr), Y(-yh)]); }   // nothing showing at all: the window
  return { on, lines, ticks, heads, labels, asym, curves, box: b, ends: lines.flat().map((q) => q.slice()), left: [xL, d.y0],
           cross: [d.x0, d.y0], xl, xr, yh, px, py, dash: DASH.map((v) => v * px) };
}

// what to draw, in order: { d, stroke, width, dash, fill, cls } (stroke and fill are colours or null)
export function graphParts(rec) {
  const g = graphGeom(rec);
  if (!g) return [];
  const aw = (rec.style && +rec.style.width) || 1.5, black = '#000000', out = [];
  const L2 = (q) => 'M' + s2(q[0][0]) + ' ' + s2(q[0][1]) + 'L' + s2(q[1][0]) + ' ' + s2(q[1][1]);
  if (g.on) {
    out.push({ cls: 'axis', d: [...g.lines, ...g.ticks].map(L2).join(''), stroke: black, width: aw, dash: null, fill: null });
    out.push({ cls: 'head', d: g.heads.map((h) => 'M' + h.map((q) => s2(q[0]) + ' ' + s2(q[1])).join('L')).join(''), stroke: black, width: aw, dash: null, fill: null });
    for (const l of g.labels) out.push({ cls: l.cls, t: l.t, d: l.d, stroke: null, width: 0, dash: null, fill: black });
  }
  if (g.asym.length) out.push({ cls: 'asym', d: g.asym.map((a) => L2([a.a, a.b])).join(''), stroke: black, width: aw, dash: g.dash, fill: null });
  g.curves.forEach((c, i) => out.push({ cls: 'curve', i, d: c.runs.map(runD).join(''), stroke: c.colour, width: c.width, dash: null, fill: null }));
  return out;
}

// a new graph record (tools.js): the pen's colour and width on the curve; about a third of the page wide (0 to 360 degrees
// over W / 3); the window 0 to 360 with the y-axis at the left; its middle at (cx, cy)
export function newGraph(id, pageId, kind, pen, W, cx, cy) {
  const px = r2(W / 3 / 4), w0 = startWindow(kind), py = r2(w0.py * px);
  return { id, page_id: pageId, seq: 0, kind: 'graph', style: { colour: '#000000', width: 1.5, dash: 'solid', opacity: 1 },
    data: { x0: r2(cx - 2 * px), y0: r2(cy), px, py, axes: { on: true, xl: 0, xr: 360, yh: w0.yh }, curves: [newCurve(kind, pen)] } };
}

// ---------------------------------------------------------------- pw-v9k, unit 2b: more curves on the same axes
// A block tap with ONE quick graph selected adds its curve to that graph's data.curves (tools.js placeGraph, ink.js
// addCurveSel): the pen's colour and width at the tap, offsets 0, stretches 1, drawn after the others (newest on top). The
// window, the size and the place stay: the window belongs to the axes. The same curve (kind and sign, offset, stretch)
// already there: nothing at all happens (withCurve gives null). With ONE axes stamp selected the same tap adds the curve to
// the STAMP's data.curves instead (her stamp's own look stays; stampCurveParts below draws only the curves and tan's
// asymptotes, in the stamp's own frame, stampFrame).
export function newCurve(kind, pen) {
  return { kind, colour: (pen && pen.colour) || '#000000', width: +(pen && pen.width) || 2.5, dx: 0, dy: 0, sx: 1, sy: 1 };
}
const num = (v, d) => (v === undefined || v === null || !Number.isFinite(+v) ? d : +v);
export function sameCurve(a, b) {
  return String(a.kind) === String(b.kind) && num(a.dx, 0) === num(b.dx, 0) && num(a.dy, 0) === num(b.dy, 0)
    && num(a.sx, 1) === num(b.sx, 1) && num(a.sy, 1) === num(b.sy, 1);
}
// rec (a graph or an axes stamp) with the curve of kind added last; null when that curve is already on it
export function withCurve(rec, kind, pen) {
  const d = rec.data || {}, cs = Array.isArray(d.curves) ? d.curves : [], c = newCurve(kind, pen);
  if (cs.some((k) => sameCurve(k, c))) return null;
  return { ...rec, style: { ...rec.style }, data: { ...d, curves: [...cs, c] } };
}

// An axes stamp's frame for its curves (null when it has none, or is a number line, or cannot be drawn). The stamp's own
// numbers: a value u sits at x0 + u / xd * px across and y0 - u / yd * py up (ink.js axesGeom). Degrees ON: its x numbers
// ARE degrees and its y numbers the values, so a curve follows them exactly. Degrees OFF (no scale for degrees): one full
// wave, 0 to 360 degrees, fits the positive x-axis, and height 1 sits at the same share of the positive y-axis as on a quick
// graph (1 / 1.35 for sin and cos, 1 / 2.6 for tan; the FIRST curve decides, so every curve on the stamp shares one frame).
// The curves run over the stamp's whole drawn x-extent (left of the origin too) and are cut to its drawn y-extent.
// { X (degrees to page x), Y (value to page y), a, b (degrees), lo, hi (values), p90 (page px per 90 degrees) }
export function stampFrame(d) {
  if (!d || d.line || !Array.isArray(d.curves) || !d.curves.length) return null;
  const px = +d.px, py = +d.py, xs = +d.xs, xd = +d.xd, ys = +d.ys, yd = +d.yd;
  if (![d.x0, d.y0, px, py, xs, xd, ys, yd, +d.xe, +d.ye].every(Number.isFinite) || px <= 0 || py <= 0 || xd <= 0 || yd <= 0) return null;
  const xT = xs + Math.floor((+d.xe - xs) / xd + 1e-6) * xd, yT = ys + Math.floor((+d.ye - ys) / yd + 1e-6) * yd;
  if (!(xT > xs) || !(yT > ys)) return null;
  let kx = 1, ky = 1;                                              // stamp units per degree, per value
  if (!d.deg) {
    const xP = xT > 0 ? xT : xT - xs, yP = yT > 0 ? yT : yT - ys;
    kx = xP / 360; ky = yP / startWindow(d.curves[0].kind).yh;
  }
  const X = (deg) => d.x0 + deg * kx / xd * px, Y = (v) => d.y0 - v * ky / yd * py;
  return { X, Y, a: xs / kx, b: xT / kx, lo: ys / ky, hi: yT / ky, p90: 90 * kx / xd * px };
}
const SCACHE = new WeakMap();
// the stamp's curves as runs in page px, and tan's asymptotes: { asym [{ x, a, b }], curves [{ runs, colour, width }], dash }
export function stampGeom(rec) {
  const d = rec && rec.data;
  if (!d || typeof d !== 'object' || !Array.isArray(d.curves) || !d.curves.length) return null;
  const hit = SCACHE.get(d);
  if (hit) return hit;
  const F = stampFrame(d);
  if (!F) return null;
  const asym = [], curves = [];
  for (const c of d.curves) {
    for (const ax of asymptotes(c, F.a, F.b)) asym.push({ x: F.X(ax), a: [F.X(ax), F.Y(F.hi)], b: [F.X(ax), F.Y(F.lo)] });
    curves.push({ runs: curveRuns(curveFn(c), F.a, F.b, F.lo, F.hi, F.X, F.Y), colour: c.colour || '#000000', width: +c.width || 2.5 });
  }
  const g = { asym, curves, dash: DASH.map((v) => v * F.p90), frame: F };
  SCACHE.set(d, g);
  return g;
}
// what to draw on top of the stamp's own drawing, in order: tan's asymptotes (black, dashed, the stamp's line width), then
// the curves in the order added. The same part shape as graphParts
export function stampCurveParts(rec) {
  const g = stampGeom(rec);
  if (!g) return [];
  const aw = (rec.style && +rec.style.width) || 1.5, out = [];
  const L2 = (q) => 'M' + s2(q[0][0]) + ' ' + s2(q[0][1]) + 'L' + s2(q[1][0]) + ' ' + s2(q[1][1]);
  if (g.asym.length) out.push({ cls: 'asym', d: g.asym.map((a) => L2([a.a, a.b])).join(''), stroke: '#000000', width: aw, dash: g.dash, fill: null });
  g.curves.forEach((c, i) => out.push({ cls: 'curve', i, d: c.runs.map(runD).join(''), stroke: c.colour, width: c.width, dash: null, fill: null }));
  return out;
}
// the segments of a stamp's curves and asymptotes (ink.js: a tap, an eraser or a box can meet them too)
export function stampCurveSegs(rec) {
  const g = stampGeom(rec), out = [];
  if (!g) return out;
  for (const a of g.asym) out.push([a.a, a.b]);
  for (const c of g.curves) for (const r of c.runs) for (let i = 1; i < r.length; i++) out.push([r[i - 1], r[i]]);
  return out;
}

// the panel's block picture: tiny plain axes and the one computed shape (the mock's block(), 70 x 50)
export function blockSvg(kind) {
  const BW = 70, BH = 50, M = 5, xa = -25, xb = 375, tan = kind.endsWith('tan'), ya = tan ? -3.2 : -1.4, yb = -ya;
  const X = (x) => M + (x - xa) / (xb - xa) * (BW - 2 * M), Y = (y) => BH - M - (y - ya) / (yb - ya) * (BH - 2 * M);
  const f = curveFn({ kind }), runs = curveRuns(f, 0, 360, -yb, yb, X, Y).map(runD).join('');
  const ax = 'stroke="#8E939B" stroke-width="1" stroke-linecap="round"';
  let as = '';
  if (tan) for (const a of [90, 270]) as += `<line x1="${s2(X(a))}" y1="${s2(Y(ya))}" x2="${s2(X(a))}" y2="${s2(Y(yb))}" stroke="currentColor" stroke-width="1" stroke-dasharray="2.5 2"/>`;
  return `<svg viewBox="0 0 ${BW} ${BH}" aria-hidden="true"><line x1="${s2(X(xa))}" y1="${s2(Y(0))}" x2="${s2(X(xb))}" y2="${s2(Y(0))}" ${ax}/>`
    + `<line x1="${s2(X(0))}" y1="${s2(Y(ya))}" x2="${s2(X(0))}" y2="${s2(Y(yb))}" ${ax}/>${as}`
    + `<path d="${runs}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
