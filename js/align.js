// PenWorks U5g (pw-v8q, pw-v8r): the PERPENDICULAR snap, one pure helper (no DOM, no imports), shared by js/ink.js (the
// Select tool dragging a line's or an arrow's end, a held stroke that becomes a line) and js/tools.js (the ruler's and
// the protractor's turn, inside snapTurn). Her ask (3 Nov 14:13): a line that meets another at nearly a right angle
// becomes exactly 90 degrees, with the paper's small square at the corner. pw-v8q also snapped a nearly PARALLEL line
// exactly parallel (with a chevron on each line); her tablet verdict 5 Nov 12:47 took that out (pw-v8r): perpendicular
// only. The hit's kind is always 'perp' now (the field stays, so the callers' checks read the same).
// - alignDir(u, segs, probe, z, cm): u is the moving line's unit direction, segs the page's segments ({ a, b, id }, page
//   px), probe { A, P, O, id }: the moving line's two ends, the point it turns about (O, default A) and its own record id
//   (never a target), z the zoom, cm page px per cm. Returns null or { u2, kind: 'perp', seg, corner, deg }: u2 the
//   exact new direction (the sign nearest u), seg the target, corner where the line through O along u2 crosses the
//   target's line, deg the correction in degrees.
// - A segment is MET when the moving segment A P comes within MEET screen px of it (an end near it, a crossing, or its
//   end on the moving line's body: the segments' nearest distance). It snaps when it is met and within ALIGN degrees of
//   90. The smallest correction wins. Segments under MIN_SEG cm never count.
// - segsOf(recs, axesGeom): every line and arrow shape (fixed ones too: the ruler's lines) and every axes stamp's axis
//   lines (axesGeom is ink.js's, passed in so this file stays import free).
// - markOf(hit, A, P, z): the mark's geometry in page px (the square's four corners), never a record.
export const MEET = 10;          // screen px
export const ALIGN = 2;          // degrees
const ROUND_SLACK = 0.02;        // degrees: a stored end is rounded to 0.1 px, so a line drawn at 88 may read 88.01
export const MIN_SEG = 0.5;      // cm
export const SQ = 9;             // screen px: the square's side
export const FADE_MS = 600;      // the mark fades out over this long after the lift

const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const crs = (a, b) => a[0] * b[1] - a[1] * b[0];
const len = (a) => Math.hypot(a[0], a[1]);
const unit = (a) => { const l = len(a) || 1; return [a[0] / l, a[1] / l]; };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export function distToSeg(p, a, b) {
  const ab = sub(b, a), L = dot(ab, ab), t = L ? clamp(dot(sub(p, a), ab) / L, 0, 1) : 0;
  return len(sub(p, add(a, mul(ab, t))));
}
// the crossing of two segments (tools.js segSeg's maths), or null
export function segCross(a1, b1, a2, b2) {
  const r = sub(b1, a1), q = sub(b2, a2), den = crs(r, q);
  if (Math.abs(den) < 1e-12) return null;
  const w = sub(a2, a1), u = crs(w, q) / den, v = crs(w, r) / den, e = 1e-9;
  return u >= -e && u <= 1 + e && v >= -e && v <= 1 + e ? add(a1, mul(r, u)) : null;
}
export function segDist(a1, b1, a2, b2) {
  if (segCross(a1, b1, a2, b2)) return 0;
  return Math.min(distToSeg(a1, a2, b2), distToSeg(b1, a2, b2), distToSeg(a2, a1, b1), distToSeg(b2, a1, b1));
}
// where the line through o along u crosses the line through a and b (null when they are parallel)
export function lineCross(o, u, a, b) {
  const v = sub(b, a), den = crs(u, v);
  if (Math.abs(den) < 1e-12) return null;
  const t = crs(sub(a, o), v) / den;
  return add(o, mul(u, t));
}

export function segsOf(recs, axesGeom) {
  const out = [];
  for (const r of recs || []) {
    if (r.kind === 'axes' && axesGeom) {
      const g = axesGeom(r);
      if (g) g.lines.forEach(([p, q], k) => out.push({ a: p.slice(), b: q.slice(), id: r.id, axis: k }));
      continue;
    }
    if (r.kind !== 'shape' || !r.data) continue;
    const d = r.data;
    if (d.type !== 'line' && d.type !== 'arrow') continue;
    if (![d.x1, d.y1, d.x2, d.y2].every(Number.isFinite)) continue;
    out.push({ a: [d.x1, d.y1], b: [d.x2, d.y2], id: r.id });
  }
  return out;
}

export function alignDir(u, segs, probe, z, cm) {
  const A = probe.A, P = probe.P, O = probe.O || A, meet = MEET / z;
  let best = null;
  for (const s of segs || []) {
    if (probe.id && s.id === probe.id) continue;
    const d = sub(s.b, s.a), L = len(d);
    if (L < MIN_SEG * cm) continue;
    const v = [d[0] / L, d[1] / L], c = clamp(Math.abs(dot(u, v)), 0, 1), th = Math.acos(c) * 180 / Math.PI;   // 0 .. 90
    const corr = Math.abs(th - 90);
    if (corr > ALIGN + ROUND_SLACK) continue;
    if (segDist(A, P, s.a, s.b) > meet) continue;                   // not met: no snap (pw-v8r: alongside no longer counts)
    if (!best || corr < best.corr - 1e-9) best = { corr, s, v };
  }
  if (!best) return null;
  let u2 = [-best.v[1], best.v[0]];
  if (dot(u2, u) < 0) u2 = mul(u2, -1);
  const corner = lineCross(O, u2, best.s.a, best.s.b);
  return { u2, kind: 'perp', seg: { a: best.s.a.slice(), b: best.s.b.slice(), id: best.s.id }, corner, deg: best.corr };
}

// the free end's rounded spot (0.1 page px, ink.js r1): of the nine grid points round `end`, the one whose direction from
// `anchor` lies nearest u2, so a rounded record still reads as exactly perpendicular
export function roundAlong(anchor, end, u2) {
  const r1 = (v) => Math.round(v * 10) / 10, c = [r1(end[0]), r1(end[1])];
  let best = c, bd = Infinity;
  for (const dx of [0, -0.1, 0.1]) for (const dy of [0, -0.1, 0.1]) {
    const q = [r1(c[0] + dx), r1(c[1] + dy)], w = sub(q, anchor), l = len(w);
    if (!l) continue;
    const e = Math.abs(crs(w, u2)) / l + 1e-6 * len(sub(q, end));
    if (e < bd - 1e-12) { bd = e; best = q; }
  }
  return best;
}

// the mark's geometry, page px: { kind: 'perp', corner, side, pts: the square's four corners from the corner }
export function markOf(hit, A, P, z) {
  if (!hit || hit.kind !== 'perp') return null;
  const u2 = hit.u2;
  const c = hit.corner, s = SQ / z, eps = Math.max(MEET / z, 1e-6);
  if (!c) return null;
  const ta = dot(sub(A, c), u2), tp = dot(sub(P, c), u2);
  let m;                                                             // along the moving line, towards its ink
  const crossesM = Math.min(ta, tp) < -eps && Math.max(ta, tp) > eps;
  if (crossesM) m = tp >= 0 ? u2 : mul(u2, -1);                      // ink on both sides: towards P
  else m = (Math.abs(ta) > Math.abs(tp) ? ta : tp) >= 0 ? u2 : mul(u2, -1);
  const sv = unit(sub(hit.seg.b, hit.seg.a)), la = dot(sub(hit.seg.a, c), sv), lb = dot(sub(hit.seg.b, c), sv);
  let t;                                                             // along the target, towards its longer part
  if (crossesM) t = lb >= 0 ? sv : mul(sv, -1);                      // a crossing: towards the target's end b
  else t = (Math.abs(lb) >= Math.abs(la) ? lb : la) >= 0 ? sv : mul(sv, -1);
  const p1 = add(c, mul(m, s)), p3 = add(c, mul(t, s)), p2 = add(p1, mul(t, s));
  return { kind: 'perp', corner: c.slice(), side: s, pts: [c.slice(), p1, p2, p3] };
}
// the mark as SVG path data (both callers draw it with the handle ring's blue, 1.5 screen px, no fill)
export function markPaths(mk) {
  if (!mk || mk.kind !== 'perp') return [];
  const f = (q) => (Math.round(q[0] * 1000) / 1000) + ' ' + (Math.round(q[1] * 1000) / 1000);
  return [{ cls: 'alignSq', d: 'M' + mk.pts.map(f).join('L') + 'Z' }];
}
