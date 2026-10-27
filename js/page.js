// PenWorks page area: a note's A4 pages stacked under each other on the desk (Samsung's scroll),
// their paper, and finger zoom and pan. The S Pen and the mouse are handed to the ink hook (js/ink.js)
// together with the page under them; a finger never draws.
// One finger scrolls the stack (and pans sideways when zoomed in), two fingers zoom about the pinch
// point (lifted from the constructions tool, including "ignore fingers while the pen is near").
// On a laptop the wheel scrolls and Ctrl + wheel (or a trackpad pinch) zooms. Zoom is one value for
// the whole stack. The current page is the one with most of itself on screen.
// Moves only change the view (V) and ask for a frame: one requestAnimationFrame callback clamps, writes the
// transform once and finds the current page, so many moves inside one frame cost one write. A finger flick
// glides on after the lift and slows down (Samsung's scroll); any new touch, the pen, a pinch, the wheel or a
// jump to a page stops the glide at once.
// A finger held still for 500 ms on the desk (pw-v4k) stops that finger's pan and asks the ink hook for the hold
// menu (Paste); a second finger, a move of more than 6 px, the lift or the pen cancels it. The pen button's
// contextmenu never opens a menu; since pw-v4v it flips between Select and the last ink tool.
// pw-v7b: nothing but opening a note (fit) changes the zoom by itself: a window resize, full screen and the header
// hiding keep the zoom and the place (relayout), only the clamp moves the stack. The zoom lock (setLock, the round
// padlock chip app.js owns; Samsung Notes' "fix zoom"): while locked the zoom never changes, ONE finger only taps
// (clears the selection) and holds (Paste), never pans or glides, and TWO fingers move the stack by their midpoint.
// The S Pen and the jumps to a page work as always. viewStats() counts resizes and fits for ?dbg=1.

export const CM = 96 / 2.54;                 // 1 cm at 96 px per inch
export const A4 = { w: 794, h: 1123 };       // 21 x 29.7 cm at zoom 1
const GRID = A4.w / 22;                      // grid paper: 22 blocks across A4 (210 mm / 22 = 9.545 mm), matches her sample page
const GRID_TOP = 0.6 * CM;                   // grid paper: 6 mm blank strip at the top, matches her sample page
const LINE_GAP = GRID;                       // lined paper: the grid's rows (9.545 mm), so words written on grid rows sit on the lines after a paper switch (her ask 26 Oct)
const LINE_TOP = GRID_TOP;                   // and the grid's 6 mm start, for the same reason
const ZMIN = 0.2, ZMAX = 4, MARGIN = 24, GAP = 24, BELOW = 90;   // BELOW: room for "Add a page below"
const SVGNS = 'http://www.w3.org/2000/svg';
const FLICK = 0.25, STOP = 0.02, DECAY = 0.95, FRAME = 1000 / 60, WINDOW = 100;   // glide: px per ms, per 16.7 ms, ms

let desk, stack, addBelow, onCurrent = () => {}, onSheets = () => {}, onPenButton = () => {}, onView = () => {}, ink = null;
let viewKey = '';     // U4a: the pages on screen and the zoom, as last told to onView
const V = { x: 0, y: 0, z: 1 };
const L = { tops: [], sizes: [], ids: [], w: A4.w, h: 0 };
let R = null;        // the desk's place on screen, refreshed at every pen-down and resize
let cur = -1;
let pinned = null;   // a page asked for by number (arrows, page list) stays current while any of it shows
let raf = 0;         // a frame is asked for
let glide = null;    // { vx, vy (px per ms on screen), t } while the stack glides after a flick
let shown = '';      // the transform last written
let movedAt = 0;     // U4a: when a frame last moved the stack (a pan, a glide, a pinch, the wheel)
let bgN = 0;         // unique pattern ids, one set per page
let lock = false;    // pw-v7b: the zoom lock, per open note (app.js turns it off on every open and close; never saved)
const stats = { resizes: 0, fits: 0, cause: '' };   // pw-v7b: window resizes, fit() calls and the last fit's cause, for ?dbg=1

// a page's size in page px at zoom 1. `p` is the page row (or, as before U4a, just its orientation). A normal page is A4
// in its orientation. U4a: a page made from a PDF page (pdf_w, pdf_h = that page's size in PDF points) takes the PDF
// page's own shape, no white bars: taller than wide (or square) = the A4 portrait width, wider than tall = the A4
// landscape width, the height by the PDF page's aspect, rounded to a whole px (an A4 PDF page is exactly an A4 page).
export function pageSize(p) {
  const o = typeof p === 'string' ? p : (p && p.orientation);
  if (p && typeof p === 'object' && p.pdf_w > 0 && p.pdf_h > 0) {
    const w = p.pdf_w > p.pdf_h ? A4.h : A4.w;
    return { w, h: Math.max(1, Math.round(w * p.pdf_h / p.pdf_w)) };
  }
  return o === 'landscape' ? { w: A4.h, h: A4.w } : { ...A4 };
}

// the paper pattern as its own <svg> (also drawn into a shared page, pw-v4t)
export function bgSvg(w, h, kind) {
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('width', w); svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.dataset.bg = kind;
  const el = (tag, at, parent) => {
    const e = document.createElementNS(SVGNS, tag);
    for (const k in at) e.setAttribute(k, typeof at[k] === 'number' ? String(+at[k].toFixed(3)) : at[k]);
    parent.appendChild(e); return e;
  };
  // one pattern per direction: a tile one gap wide (or tall) and the whole page long, with its line in the
  // middle of the tile, so no line touches a tile edge (no seams) and every line is one piece. Vertical
  // lines sit at x = at + k * gap, horizontal ones at y = at + k * gap; the rect sets where they stop.
  let defs = null;
  const lines = (dir, at, gap, cls, rect) => {
    if (!defs) defs = el('defs', {}, svg);
    const id = `pw-${cls}-${++bgN}`, v = dir === 'v';
    const p = el('pattern', { id, patternUnits: 'userSpaceOnUse', x: v ? at - gap / 2 : 0, y: v ? 0 : at - gap / 2,
      width: v ? gap : w, height: v ? h : gap }, defs);
    el('line', { ...(v ? { x1: gap / 2, y1: 0, x2: gap / 2, y2: h } : { x1: 0, y1: gap / 2, x2: w, y2: gap / 2 }),
      class: cls, stroke: '#D3D7DE', 'stroke-width': '1' }, p);
    el('rect', { ...rect, fill: `url(#${id})`, class: cls }, svg);
  };
  if (kind === 'grid') {
    // as before: verticals at 0, GRID, ... across the page, top to bottom; horizontals from GRID_TOP down
    lines('v', 0, GRID, 'gv', { x: 0, y: 0, width: w, height: h });
    lines('h', GRID_TOP, GRID, 'gh', { x: 0, y: 0, width: w, height: h });
  } else if (kind === 'lined') {
    // as before: lines from LINE_TOP every LINE_GAP, the last one at or above h - 1 cm
    const n = Math.floor((h - CM - LINE_TOP) / LINE_GAP + 1e-6);
    if (n >= 0) lines('h', LINE_TOP, LINE_GAP, 'ln', { x: 0, y: LINE_TOP - LINE_GAP / 2, width: w, height: (n + 1) * LINE_GAP });
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
  const t = `translate(${V.x}px, ${V.y}px) scale(${V.z})`;
  if (t !== shown) { shown = t; stack.style.transform = t; stack.dataset.zoom = V.z.toFixed(3); }
  const c = findCurrent();
  if (c !== cur) { cur = c; onCurrent(cur); }
  tellView();
}
// U4a: the first and last page with any of itself on screen, and the zoom; told only when one of them changes (cheap: the
// PDF layer (js/pdfview.js) only takes note and renders later, never inside this frame)
function tellView() {
  const dh = desk.clientHeight;
  let first = -1, last = -1;
  for (let i = 0; i < L.tops.length; i++) {
    const a = V.y + L.tops[i] * V.z, b = a + L.sizes[i].h * V.z;
    if (b > 0 && a < dh) { if (first < 0) first = i; last = i; }
  }
  const key = first + ',' + last + ',' + V.z.toFixed(3);
  if (key === viewKey) return;
  viewKey = key;
  onView(first, last, V.z);
}

// moves call this; the frame does the clamp, the one transform write and the current page
function request() { if (!raf) raf = requestAnimationFrame(frame); }
function frame(now) {
  raf = 0;
  movedAt = performance.now();
  if (glide) {
    const dt = Math.min(50, Math.max(0, now - glide.t)); glide.t = now;
    const x = V.x + glide.vx * dt, y = V.y + glide.vy * dt;
    V.x = x; V.y = y; clampView();
    if (Math.abs(V.x - x) > 0.01) glide.vx = 0;       // the end of the stack (or a centred page) stops that axis
    if (Math.abs(V.y - y) > 0.01) glide.vy = 0;
    const k = Math.pow(DECAY, dt / FRAME); glide.vx *= k; glide.vy *= k;
    if (Math.hypot(glide.vx, glide.vy) < STOP) glide = null;
  } else clampView();
  apply();
  if (glide) request();
}
function stopGlide() { glide = null; }
// a move still waiting for its frame is shown now (a jump, the pen or a new finger needs the view as seen)
function settle() {
  if (raf) { cancelAnimationFrame(raf); raf = 0; clampView(); apply(); }
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
  L.tops = []; L.sizes = []; L.ids = []; L.w = 0;
  pages.forEach((p) => { const s = pageSize(p); L.sizes.push(s); L.w = Math.max(L.w, s.w); });
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
    if (p.pdf_path) { el.dataset.pdf = '1'; el.appendChild(Object.assign(document.createElement('div'), { className: 'pdfLayer' })); }   // U4a: under the ink
    if (p.bookmark) el.appendChild(bookmarkTab());
    stack.insertBefore(el, addBelow);
    L.tops.push(y); L.ids.push(p.id);
    y += s.h + GAP;
  });
  addBelow.style.top = Math.max(0, y - GAP) + 22 + 'px';
  L.h = Math.max(0, y - GAP) + BELOW;
  stack.style.width = L.w + 'px'; stack.style.height = L.h + 'px';
  cur = -1; viewKey = '';
  if (pinned !== null && pinned >= L.tops.length) pinned = L.tops.length - 1;
  stopGlide(); settle(); clampView(); apply();
  onSheets([...stack.querySelectorAll('.sheet')]);
}

// a page's bookmark (pw-v4r), the Samsung Notes way: a ribbon tab hanging from the page's top edge near the right
// (16 x 26 page px, 12 px in from the right, its bottom notched into a V), above the ink, never in the pen's way.
// The page list's thumbs use the same tab, smaller (css). Its colour is fixed: the paper is white in both modes.
const RIBBON = '<svg viewBox="0 0 16 26" preserveAspectRatio="none" aria-hidden="true"><path d="M0 0H16V26L8 19L0 26Z" fill="#3A4250"/></svg>';
export function bookmarkTab() {
  const t = document.createElement('div');
  t.className = 'bookmarkTab';
  t.innerHTML = RIBBON;
  return t;
}
// put the tab on (or take it off) the page's sheet without rebuilding the stack
export function markSheet(pageId, on) {
  const el = [...stack.querySelectorAll('.sheet')].find((s) => s.dataset.id === pageId);
  if (!el) return;
  const t = el.querySelector(':scope > .bookmarkTab');
  if (on && !t) el.appendChild(bookmarkTab());
  else if (!on && t) t.remove();
}

// fit page `index` across the desk (zoom 1 at most) and show it at the top; a wider (landscape) page
// in the same note then pans sideways with one finger. pw-v7b: only opening a note calls this (app.js openNote, cause
// 'open'); nothing else may reset her zoom. `cause` is counted for ?dbg=1 (viewStats).
export function fit(index = Math.max(0, cur), cause = '?') {
  stats.fits++; stats.cause = cause;
  const dw = desk.clientWidth, w = (L.sizes[index] || L.sizes[0] || A4).w;
  V.z = Math.min(1, Math.max(ZMIN, (dw - 2 * MARGIN) / w));
  V.x = (dw - L.w * V.z) / 2;                            // pages sit centred in the stack
  pinned = L.tops.length ? Math.min(index, L.tops.length - 1) : null;
  V.y = MARGIN - (L.tops[index] || 0) * V.z;
  stopGlide(); settle(); clampView(); apply();
}

export function scrollToPage(index) {
  if (!L.tops.length) return;
  const i = Math.max(0, Math.min(L.tops.length - 1, index));
  pinned = i;
  V.y = MARGIN - L.tops[i] * V.z;
  stopGlide(); settle(); clampView(); apply();
}

// after the desk changes size (a window resize, full screen, the header hidden or back): the zoom and the place stay
// exactly as they were (V untouched); only the clamp moves the stack, when the desk grew or shrank past it (a stack
// narrower than the desk is centred, a stack past an edge comes back). pw-v7b: this used to re-fit the current page,
// so every resize her tablet fired while she explained threw her zoom away (27 Oct, about 30 times in a day).
export function relayout() { R = null; stopGlide(); settle(); clampView(); apply(); }

// pw-v7b: the zoom lock. Locked: the zoom cannot change and only two fingers move the stack (see initPage); a glide
// still running stops where it is. app.js owns the button and turns the lock off on every note open and close.
export function setLock(on) { lock = !!on; if (lock) stopGlide(); }
export function locked() { return lock; }
// ?dbg=1 (js/dbg.js): window resizes seen, fit() calls and the last fit's cause, and the lock
export function viewStats() { return { resizes: stats.resizes, fits: stats.fits, cause: stats.cause, lock }; }

// the desk must never scroll natively (css overflow: clip); if a browser scrolled it anyway, the stack would show
// shifted while the pen maths below still use the transform alone: every stroke off by that scroll. Reset it.
export function unscroll() { if (desk.scrollTop || desk.scrollLeft) { desk.scrollTop = 0; desk.scrollLeft = 0; } }
export function deskScroll() { return [desk.scrollTop, desk.scrollLeft]; }

export function current() { return cur; }
// U4a: ms since the stack last moved; the PDF layer renders only once it has been still a moment (a render never runs
// inside a pan, a glide or a pinch, where it could cost a frame)
export function sinceMove() { return performance.now() - movedAt; }
export function view() { if (raf) clampView(); return { ...V }; }

// screen point to page px at zoom 1. pageAt: the page under the point (or null);
// pagePoint: the same point measured on page `index`, even when it is off that page
function deskPoint(cx, cy) {
  if (raf) clampView();                            // a move waiting for its frame: measure where it will show
  const r = R || (R = desk.getBoundingClientRect());
  return [(cx - r.left - V.x) / V.z, (cy - r.top - V.y) / V.z];
}
export function pagePoint(index, cx, cy) {
  const [sx, sy] = deskPoint(cx, cy), s = L.sizes[index];
  return [sx - (L.w - s.w) / 2, sy - L.tops[index]];
}
export function pageAt(cx, cy) {
  const [sx, sy] = deskPoint(cx, cy);
  for (let i = 0; i < L.tops.length; i++) {
    const s = L.sizes[i], x = sx - (L.w - s.w) / 2, y = sy - L.tops[i];
    if (x >= 0 && x <= s.w && y >= 0 && y <= s.h) return { index: i, id: L.ids[i], x, y, w: s.w, h: s.h };
  }
  return null;
}

function zoomAt(p, f) {
  if (lock) return;                                // pw-v7b: Ctrl + wheel never zooms while locked
  pinned = null;
  clampView();
  const z = Math.min(ZMAX, Math.max(ZMIN, V.z * f));
  const wx = (p[0] - V.x) / V.z, wy = (p[1] - V.y) / V.z;
  V.z = z; V.x = p[0] - wx * z; V.y = p[1] - wy * z;
  request();
}

export function initPage(els) {
  ({ desk, stack, addBelow } = els);
  if (els.onCurrent) onCurrent = els.onCurrent;
  if (els.onSheets) onSheets = els.onSheets;
  if (els.ink) ink = els.ink;                       // { down(e), move(events), up(e, cancelled), hover(e), fingerTap(cx, cy), holdMenu(cx, cy) }
  if (els.onPenButton) onPenButton = els.onPenButton;   // the pen button's contextmenu on the desk (pw-v4v): app.js flips the tool
  if (els.onView) onView = els.onView;                  // U4a: (first, last, zoom) of the pages on screen, for the PDF layer
  const touches = new Map();
  let pinch = null, drag = null, penSeen = -1e9, inkId = null, chord = false, holdT = 0;
  const now = () => performance.now();
  const when = (e) => e.timeStamp || now();       // when the finger was there (a late event keeps its own time)
  const rect = () => desk.getBoundingClientRect();
  const pt = (e) => { const r = rect(); return [e.clientX - r.left, e.clientY - r.top]; };
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const TAP_PX = 6;                                 // a finger that lifts within 6 px of where it landed is a tap (the selection clears)
  const FINGER_HOLD = 500;                          // ms a finger stays still (within TAP_PX) before the hold menu opens
  function cancelHold() { clearTimeout(holdT); holdT = 0; }
  // one finger down: when it is still there and still 500 ms later, its pan stops and the hold menu opens
  function armHold(id) {
    cancelHold();
    holdT = setTimeout(() => {
      holdT = 0;
      if (!drag || drag.id !== id || pinch || inkId !== null || touches.size !== 1 || now() - penSeen < 600) return;
      const [cx, cy] = drag.c;
      drag = null; touches.delete(id);
      try { desk.releasePointerCapture(id); } catch (_) { /* ignore */ }
      if (ink && ink.holdMenu) ink.holdMenu(cx, cy);
    }, FINGER_HOLD);
  }
  function startPinch() {
    cancelHold();
    const [a, b] = [...touches.values()];
    stopGlide(); settle();
    pinch = { z0: V.z, x0: V.x, y0: V.y, m0: mid(a, b), d0: Math.max(10, dist(a, b)) };
    drag = null;
  }
  function movePinch() {
    const [a, b] = [...touches.values()], m = mid(a, b), d = Math.max(10, dist(a, b));
    if (lock) {                                     // pw-v7b: locked, two fingers only move the stack by their midpoint
      if (pinch.z0 !== V.z) Object.assign(pinch, { z0: V.z, x0: V.x, y0: V.y, m0: m, d0: d });   // locked mid-pinch: from here
      V.x = pinch.x0 + m[0] - pinch.m0[0]; V.y = pinch.y0 + m[1] - pinch.m0[1];
      request();
      return;
    }
    const z = Math.min(ZMAX, Math.max(ZMIN, pinch.z0 * d / pinch.d0));
    const w = [(pinch.m0[0] - pinch.x0) / pinch.z0, (pinch.m0[1] - pinch.y0) / pinch.z0];
    V.z = z; V.x = m[0] - w[0] * z; V.y = m[1] - w[1] * z;
    request();
  }
  // on lift: the speed over the last 100 ms of the drag; a careful slow drag just stops
  function flick(d, e) {
    const t = when(e), s = d.trail.filter((q) => t - q[0] <= WINDOW);
    if (s.length < 2) return;
    const a = s[0], b = s[s.length - 1], dt = b[0] - a[0];
    if (dt < 8) return;
    const vx = (b[1] - a[1]) / dt, vy = (b[2] - a[2]) / dt;
    if (Math.hypot(vx, vy) < FLICK) return;
    glide = { vx, vy, t: now() }; request();
  }

  // the pen or mouse going down on the desk: true when the ink layer took it
  function inkDown(e) {
    if (inkId !== null || !ink) return false;
    if (e.target.closest('button, #pageList')) return false;
    R = desk.getBoundingClientRect();
    if (!ink.down(e)) return false;
    inkId = e.pointerId;
    touches.clear(); pinch = null; drag = null; cancelHold();              // a palm already down stops panning
    try { desk.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    e.preventDefault();
    return true;
  }
  desk.addEventListener('pointerdown', (e) => {
    stopGlide(); settle(); unscroll();                                     // any touch, pen or click holds the stack where it is
    if (e.pointerType === 'pen' || e.pointerType === 'mouse') {           // the S Pen and the mouse draw
      if (e.pointerType === 'pen') { penSeen = performance.now(); cancelHold(); }
      if (e.button > 0 && e.button !== 2) return;                         // button 2: the pen button / right mouse (ink.down turns it away)
      chord = false;
      inkDown(e);
      return;
    }
    if (e.pointerType !== 'touch') return;
    if (inkId !== null) return;                                            // a finger is ignored while the pen writes
    if (e.target.closest('button, #pageList')) return;                     // buttons and the page list stay tappable
    if (performance.now() - penSeen < 600) return;                         // palm while the pen is near
    touches.set(e.pointerId, pt(e));
    try { desk.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    pinned = null;
    if (touches.size >= 2) startPinch();
    else {
      const p = pt(e);
      drag = { id: e.pointerId, s0: p, x0: V.x, y0: V.y, trail: [[when(e), p[0], p[1]]], c: [e.clientX, e.clientY] };
      armHold(e.pointerId);
    }
    e.preventDefault();
  });
  desk.addEventListener('pointermove', (e) => {
    if (e.pointerType === 'pen') { penSeen = performance.now(); if (holdT) cancelHold(); }
    if (e.pointerId === inkId) {
      if (chord && !(e.buttons & 1)) {                                     // the tip lifted, the pen button still held: the end
        inkId = null; chord = false; ink.up(e, false);
        try { desk.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
        return;
      }
      const all = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
      ink.move(all.length ? all : [e]);
      return;
    }
    // the tip touching while the pen button is already held: the spec sends that as a move (button 0, buttons 3),
    // not a pointerdown, because a button was already down; it is a pen down all the same
    if (inkId === null && e.pointerType === 'pen' && e.button === 0 && (e.buttons & 3) === 3) {
      stopGlide(); settle();
      if (inkDown(e)) { chord = true; return; }
    }
    if (inkId === null && e.pointerType !== 'touch' && ink && ink.hover) ink.hover(e);   // the pen or mouse hovering: a shape handle in reach shows its ring
    if (e.pointerType === 'pen' || inkId !== null) return;
    if (!touches.has(e.pointerId)) return;
    touches.set(e.pointerId, pt(e));
    if (pinch && touches.size >= 2) { movePinch(); return; }
    if (drag && drag.id === e.pointerId) {
      const p = pt(e), t = when(e);
      if (!lock) { V.x = drag.x0 + p[0] - drag.s0[0]; V.y = drag.y0 + p[1] - drag.s0[1]; }   // pw-v7b: locked, one finger never pans
      drag.c = [e.clientX, e.clientY];
      if (dist(p, drag.s0) > TAP_PX) cancelHold();                       // moved: a pan, never a hold
      if (dist(p, drag.s0) >= TAP_PX) drag.panned = true;                // once a pan, never a tap
      drag.trail.push([t, p[0], p[1]]);
      while (drag.trail.length > 2 && t - drag.trail[0][0] > WINDOW) drag.trail.shift();
      if (!lock) request();
    }
  });
  const up = (e) => {
    if (e.pointerId === inkId) { inkId = null; chord = false; ink.up(e, e.type === 'pointercancel'); return; }
    if (!touches.has(e.pointerId)) return;
    touches.delete(e.pointerId);
    if (drag && drag.id === e.pointerId) cancelHold();                     // lifted or cancelled before the hold
    if (drag && drag.id === e.pointerId && e.type === 'pointerup' && !pinch) {                             // a finger only
      settle();
      if (!drag.panned && dist(pt(e), drag.s0) < TAP_PX) { if (ink && ink.fingerTap) ink.fingerTap(e.clientX, e.clientY); }   // a tap: no flick
      else if (!lock) flick(drag, e);                                     // pw-v7b: locked, one finger never glides
    }
    if (touches.size >= 2) startPinch();
    else { pinch = null; drag = null; }
  };
  desk.addEventListener('pointerup', up);
  desk.addEventListener('pointercancel', up);
  desk.addEventListener('wheel', (e) => {
    if (e.target.closest('#pageList')) return;                             // the page list scrolls itself
    e.preventDefault();
    stopGlide();
    if (e.ctrlKey) zoomAt(pt(e), Math.exp(-e.deltaY * 0.0025));
    else { pinned = null; clampView(); V.x -= e.shiftKey ? e.deltaY : e.deltaX; V.y -= e.shiftKey ? 0 : e.deltaY; request(); }
  }, { passive: false });
  // the S Pen's button on her tablet arrives only as this contextmenu, once per press: no menu, and (pw-v4v) it flips
  // the tool between Select and the last ink tool (app.js, onPenButton). A finger's long press never flips (its
  // contextmenu says touch, or a finger is still down), nor does a press while the pen is on the paper
  desk.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    unscroll();
    if (e.pointerType === 'touch' || touches.size || drag || inkId !== null) return;
    onPenButton(e);
  });
  // pw-v7b: a resize keeps the zoom and the place (relayout), whatever fired it (the system bars, a keyboard, split screen)
  window.addEventListener('resize', () => { stats.resizes++; R = null; stopGlide(); if (L.tops.length) relayout(); });
  desk.addEventListener('scroll', () => { unscroll(); R = null; }, { passive: true });   // cannot fire with overflow: clip; a fallback only
}
