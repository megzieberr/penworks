// PenWorks page area: one fixed A4 page on the desk, its background, and finger zoom and pan.
// The S Pen and the mouse do nothing on the page yet (ink is U2). One finger moves the page, two fingers
// zoom and move it (lifted from the constructions tool, including "ignore fingers while the pen is near").
// On a laptop the wheel scrolls the page and Ctrl + wheel (or a trackpad pinch) zooms.

export const CM = 96 / 2.54;                 // 1 cm at 96 px per inch
export const A4 = { w: 794, h: 1123 };       // 21 x 29.7 cm at zoom 1
const LINE_GAP = 0.8 * CM;                   // lined paper: 8 mm
const LINE_TOP = 2.4 * CM;                   // first line sits below a top margin
const ZMIN = 0.3, ZMAX = 4, MARGIN = 24;
const SVGNS = 'http://www.w3.org/2000/svg';

let desk, wrap, sheet;
const V = { x: 0, y: 0, z: 1 };
let size = { ...A4 };

export function pageSize(orientation) {
  return orientation === 'landscape' ? { w: A4.h, h: A4.w } : { ...A4 };
}

function bgSvg(w, h, kind) {
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('width', w); svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.dataset.bg = kind;
  const line = (x1, y1, x2, y2, cls) => {
    const l = document.createElementNS(SVGNS, 'line');
    l.setAttribute('x1', x1.toFixed(2)); l.setAttribute('y1', y1.toFixed(2));
    l.setAttribute('x2', x2.toFixed(2)); l.setAttribute('y2', y2.toFixed(2));
    l.setAttribute('class', cls);
    l.setAttribute('stroke', '#D3D7DE'); l.setAttribute('stroke-width', '1');
    svg.appendChild(l);
  };
  if (kind === 'grid') {
    for (let i = 0; i * CM <= w + 0.01; i++) line(i * CM, 0, i * CM, h, 'gv');
    for (let j = 0; j * CM <= h + 0.01; j++) line(0, j * CM, w, j * CM, 'gh');
  } else if (kind === 'lined') {
    for (let y = LINE_TOP; y <= h - CM; y += LINE_GAP) line(0, y, w, y, 'ln');
  }
  return svg;
}

function apply() {
  wrap.style.transform = `translate(${V.x}px, ${V.y}px) scale(${V.z})`;
  wrap.dataset.zoom = V.z.toFixed(3);
}

function clampView() {
  const dw = desk.clientWidth, dh = desk.clientHeight;
  const w = size.w * V.z, h = (size.h + 90) * V.z;          // 90: room for "Add a page below"
  const lo = (a, b) => Math.min(a, b), hi = (a, b) => Math.max(a, b);
  V.x = Math.min(hi(MARGIN, dw - w - MARGIN), Math.max(lo(MARGIN, dw - w - MARGIN), V.x));
  V.y = Math.min(hi(MARGIN, dh - h - MARGIN), Math.max(lo(MARGIN, dh - h - MARGIN), V.y));
}

// zoom 1 when the page fits across the desk with margins, otherwise shrink until it does
export function fit() {
  const dw = desk.clientWidth;
  V.z = Math.min(1, Math.max(ZMIN, (dw - 2 * MARGIN) / size.w));
  V.x = (dw - size.w * V.z) / 2;
  V.y = MARGIN;
  apply();
}

function zoomAt(p, f) {
  const z = Math.min(ZMAX, Math.max(ZMIN, V.z * f));
  const wx = (p[0] - V.x) / V.z, wy = (p[1] - V.y) / V.z;
  V.z = z; V.x = p[0] - wx * z; V.y = p[1] - wy * z;
  clampView(); apply();
}

export function showPage(page) {
  sheet.textContent = '';
  if (!page) { wrap.hidden = true; return; }
  wrap.hidden = false;
  size = pageSize(page.orientation);
  sheet.style.width = size.w + 'px'; sheet.style.height = size.h + 'px';
  sheet.dataset.orientation = page.orientation; sheet.dataset.bg = page.background;
  sheet.appendChild(bgSvg(size.w, size.h, page.background));
  wrap.style.width = size.w + 'px';
}

export function view() { return { ...V }; }

export function initPage(els) {
  ({ desk, wrap, sheet } = els);
  const touches = new Map();
  let pinch = null, drag = null, penSeen = -1e9;
  const rect = () => desk.getBoundingClientRect();
  const pt = (e) => { const r = rect(); return [e.clientX - r.left, e.clientY - r.top]; };
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  function startPinch() {
    const [a, b] = [...touches.values()];
    pinch = { z0: V.z, x0: V.x, y0: V.y, m0: mid(a, b), d0: Math.max(10, dist(a, b)) };
    drag = null;
  }
  function movePinch() {
    const [a, b] = [...touches.values()], m = mid(a, b), d = Math.max(10, dist(a, b));
    const z = Math.min(ZMAX, Math.max(ZMIN, pinch.z0 * d / pinch.d0));
    const w = [(pinch.m0[0] - pinch.x0) / pinch.z0, (pinch.m0[1] - pinch.y0) / pinch.z0];
    V.z = z; V.x = m[0] - w[0] * z; V.y = m[1] - w[1] * z;
    clampView(); apply();
  }

  desk.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'pen') { penSeen = performance.now(); return; }   // ink arrives in U2
    if (e.pointerType !== 'touch') return;                                 // the mouse does nothing
    if (e.target.closest('button')) return;                                // let "Add a page below" be tapped
    if (performance.now() - penSeen < 600) return;                         // palm while the pen is near
    touches.set(e.pointerId, pt(e));
    try { desk.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    if (touches.size >= 2) startPinch();
    else drag = { id: e.pointerId, s0: pt(e), x0: V.x, y0: V.y };
    e.preventDefault();
  });
  desk.addEventListener('pointermove', (e) => {
    if (e.pointerType === 'pen') { penSeen = performance.now(); return; }
    if (!touches.has(e.pointerId)) return;
    touches.set(e.pointerId, pt(e));
    if (pinch && touches.size >= 2) { movePinch(); return; }
    if (drag && drag.id === e.pointerId) {
      const p = pt(e);
      V.x = drag.x0 + p[0] - drag.s0[0]; V.y = drag.y0 + p[1] - drag.s0[1];
      clampView(); apply();
    }
  });
  const up = (e) => {
    if (!touches.has(e.pointerId)) return;
    touches.delete(e.pointerId);
    if (touches.size >= 2) startPinch();
    else { pinch = null; drag = null; }
  };
  desk.addEventListener('pointerup', up);
  desk.addEventListener('pointercancel', up);
  desk.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (e.ctrlKey) zoomAt(pt(e), Math.exp(-e.deltaY * 0.0025));
    else { V.x -= e.shiftKey ? e.deltaY : e.deltaX; V.y -= e.shiftKey ? 0 : e.deltaY; clampView(); apply(); }
  }, { passive: false });
  desk.addEventListener('contextmenu', (e) => e.preventDefault());
  window.addEventListener('resize', () => fit());
}
