// PenWorks page area: a note's A4 pages stacked under each other on the desk (Samsung's scroll),
// their paper, and finger zoom and pan. The S Pen and the mouse draw nothing yet (ink is U2).
// One finger scrolls the stack (and pans sideways when zoomed in), two fingers zoom about the pinch
// point (lifted from the constructions tool, including "ignore fingers while the pen is near").
// On a laptop the wheel scrolls and Ctrl + wheel (or a trackpad pinch) zooms. Zoom is one value for
// the whole stack. The current page is the one with most of itself on screen.

export const CM = 96 / 2.54;                 // 1 cm at 96 px per inch
export const A4 = { w: 794, h: 1123 };       // 21 x 29.7 cm at zoom 1
const LINE_GAP = 0.8 * CM;                   // lined paper: 8 mm
const LINE_TOP = 2.4 * CM;                   // first line sits below a top margin
const ZMIN = 0.2, ZMAX = 4, MARGIN = 24, GAP = 24, BELOW = 90;   // BELOW: room for "Add a page below"
const SVGNS = 'http://www.w3.org/2000/svg';

let desk, stack, addBelow, onCurrent = () => {};
const V = { x: 0, y: 0, z: 1 };
const L = { tops: [], sizes: [], w: A4.w, h: 0 };
let cur = -1;
let pinned = null;   // a page asked for by number (arrows, page list) stays current while any of it shows

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

function findCurrent() {
  const dh = desk.clientHeight;
  let best = -1, most = -1;
  L.tops.forEach((t, i) => {
    const a = V.y + t * V.z, b = a + L.sizes[i].h * V.z;
    const seen = Math.min(b, dh) - Math.max(a, 0);
    if (seen > most + 0.5) { most = seen; best = i; }
    if (i === pinned && seen > 0) { most = Infinity; best = i; }
  });
  return best;
}

function apply() {
  stack.style.transform = `translate(${V.x}px, ${V.y}px) scale(${V.z})`;
  stack.dataset.zoom = V.z.toFixed(3);
  const c = findCurrent();
  if (c !== cur) { cur = c; onCurrent(cur); }
}

function clampView() {
  const dw = desk.clientWidth, dh = desk.clientHeight;
  const w = L.w * V.z, h = L.h * V.z;
  if (w <= dw - 2 * MARGIN) V.x = (dw - w) / 2;
  else V.x = Math.min(MARGIN, Math.max(dw - w - MARGIN, V.x));
  if (h <= dh - 2 * MARGIN) V.y = MARGIN;
  else V.y = Math.min(MARGIN, Math.max(dh - h - MARGIN, V.y));
}

// draws every page of the note, in order; keeps the view where it was
export function showStack(pages) {
  stack.querySelectorAll('.sheet').forEach((e) => e.remove());
  L.tops = []; L.sizes = []; L.w = 0;
  pages.forEach((p) => { const s = pageSize(p.orientation); L.sizes.push(s); L.w = Math.max(L.w, s.w); });
  if (!pages.length) L.w = A4.w;
  let y = 0;
  pages.forEach((p, i) => {
    const s = L.sizes[i];
    const el = document.createElement('div');
    el.className = 'sheet';
    el.style.left = (L.w - s.w) / 2 + 'px'; el.style.top = y + 'px';
    el.style.width = s.w + 'px'; el.style.height = s.h + 'px';
    el.dataset.id = p.id; el.dataset.index = String(i + 1);
    el.dataset.orientation = p.orientation; el.dataset.bg = p.background;
    el.appendChild(bgSvg(s.w, s.h, p.background));
    stack.insertBefore(el, addBelow);
    L.tops.push(y);
    y += s.h + GAP;
  });
  addBelow.style.top = Math.max(0, y - GAP) + 22 + 'px';
  L.h = Math.max(0, y - GAP) + BELOW;
  stack.style.width = L.w + 'px'; stack.style.height = L.h + 'px';
  cur = -1;
  if (pinned !== null && pinned >= L.tops.length) pinned = L.tops.length - 1;
  clampView(); apply();
}

// fit page `index` across the desk (zoom 1 at most) and show it at the top; a wider (landscape) page
// in the same note then pans sideways with one finger
export function fit(index = Math.max(0, cur)) {
  const dw = desk.clientWidth, w = (L.sizes[index] || L.sizes[0] || A4).w;
  V.z = Math.min(1, Math.max(ZMIN, (dw - 2 * MARGIN) / w));
  V.x = (dw - L.w * V.z) / 2;                            // pages sit centred in the stack
  pinned = L.tops.length ? Math.min(index, L.tops.length - 1) : null;
  V.y = MARGIN - (L.tops[index] || 0) * V.z;
  clampView(); apply();
}

export function scrollToPage(index) {
  if (!L.tops.length) return;
  const i = Math.max(0, Math.min(L.tops.length - 1, index));
  pinned = i;
  V.y = MARGIN - L.tops[i] * V.z;
  clampView(); apply();
}

// after the desk changes size (full screen, header hidden): keep the current page in place
export function relayout() { const i = Math.max(0, cur); fit(i); }

export function current() { return cur; }
export function view() { return { ...V }; }

function zoomAt(p, f) {
  pinned = null;
  const z = Math.min(ZMAX, Math.max(ZMIN, V.z * f));
  const wx = (p[0] - V.x) / V.z, wy = (p[1] - V.y) / V.z;
  V.z = z; V.x = p[0] - wx * z; V.y = p[1] - wy * z;
  clampView(); apply();
}

export function initPage(els) {
  ({ desk, stack, addBelow } = els);
  if (els.onCurrent) onCurrent = els.onCurrent;
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
    if (e.target.closest('button, #pageList')) return;                     // buttons and the page list stay tappable
    if (performance.now() - penSeen < 600) return;                         // palm while the pen is near
    touches.set(e.pointerId, pt(e));
    try { desk.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    pinned = null;
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
    if (e.target.closest('#pageList')) return;                             // the page list scrolls itself
    e.preventDefault();
    if (e.ctrlKey) zoomAt(pt(e), Math.exp(-e.deltaY * 0.0025));
    else { pinned = null; V.x -= e.shiftKey ? e.deltaY : e.deltaX; V.y -= e.shiftKey ? 0 : e.deltaY; clampView(); apply(); }
  }, { passive: false });
  desk.addEventListener('contextmenu', (e) => e.preventDefault());
  window.addEventListener('resize', () => { if (L.tops.length) relayout(); });
}
