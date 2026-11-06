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
// pw-v9c: sticky notes on the desk (her design 27 Oct, built 6 Nov). A sticky is a small coloured square she writes on and
// drags by its top strip, with the pen or a finger: into the margin beside a page ("the sidelines": things to show quickly
// in class without scrolling), between pages, or onto a page. THE ANCHOR RULE: every sticky belongs with one page (its
// anchor) and sits at sk_x, sk_y page px from that page's top-left, so it goes wherever its page goes; dropped with its
// centre over ANOTHER page it re-anchors to that page, dropped over no page it keeps its anchor. THE EXPORT RULE, her
// words: a sticky on a page goes into that page's PDF and pictures as it looks (clipped at the page's edge); a sticky in
// the margin simply is not there (js/ink.js thumbSvg, js/pdfout.js). Here: each sticky is a div.sticky.<colour> in #stack
// AFTER the sheets (above every page's ink), its own ink layer inside (js/ink.js attach). The pages' lists (L.ids, L.tops,
// L.sizes), the current page, pageAt and pagePoint stay PAGES ONLY; the stickies have their own list L.sk (z-order: last
// = on top). The clamp uses the box of the pages AND the stickies (L.box), so a margin sticky can always be panned into
// view; with no sticky the box is exactly the pages' box (0, 0, L.w, L.h) and the layout is as before, number for number.
// A press on a sticky wins over the page under it (stickyAt, topmost first): the strip drags it (a lift within 8 screen
// px = a tap = the sticky menu), the corner handle resizes it (square, 113 to 454 page px, top-left fixed), the body
// takes the pen's tool on its own layer (surfaceAt / surfacePoint, js/ink.js) or a finger's pan, as a page does.

export const CM = 96 / 2.54;                 // 1 cm at 96 px per inch
export const A4 = { w: 794, h: 1123 };       // 21 x 29.7 cm at zoom 1
export const GRID = A4.w / 22;                     // grid paper: 22 blocks across A4 (210 mm / 22 = 9.545 mm), matches her sample page
export const GRID_TOP = 0.6 * CM;                  // grid paper: 6 mm blank strip at the top, matches her sample page
export const LINE_GAP = GRID;                      // lined paper: the grid's rows (9.545 mm), so words written on grid rows sit on the lines after a paper switch (her ask 26 Oct)
export const LINE_TOP = GRID_TOP;                  // and the grid's 6 mm start, for the same reason
const ZMIN = 0.2, ZMAX = 4, MARGIN = 24, GAP = 24, BELOW = 90;   // BELOW: room for "Add a page below"
const SVGNS = 'http://www.w3.org/2000/svg';
const FLICK = 0.25, STOP = 0.02, DECAY = 0.95, FRAME = 1000 / 60, WINDOW = 100;   // glide: px per ms, per 16.7 ms, ms
const HINT_MS = 250;        // pw-v8i: ms of a still stack before the will-change hint comes off (Chrome then redraws at the new zoom)
const HINT_BACK_MS = 1000;  // pw-v8i: ms after that before the hint goes back on (the stack composited before her next finger lands)

let desk, stack, addBelow, onCurrent = () => {}, onSheets = () => {}, onPenButton = () => {}, onView = () => {}, ink = null;
// pw-v9c: app.js's sticky callbacks: new elements to attach and sizes that changed (onStickies), a live resize
// (onStickySize), a strip tap (onStickyTap), a finished move or resize (onStickyChange)
let onStickies = () => {}, onStickySize = () => {}, onStickyTap = () => {}, onStickyChange = () => {};
let viewKey = '';     // U4a: the pages on screen and the zoom, as last told to onView
const V = { x: 0, y: 0, z: 1 };
const L = { tops: [], sizes: [], ids: [], w: A4.w, h: 0, sk: [], box: [0, 0, A4.w, 0] };   // pw-v9c: sk = the stickies, box = the pan box
// pw-v9c: the sticky's numbers (page px) and her four colours (the paper and the strip a shade darker; the same in dark mode)
export const SK_SIZE = 227, SK_MIN = 113, SK_MAX = 454, SK_STRIP = 30;
export const SK_COLOURS = { yellow: ['#FFE882', '#F0D55A'], blue: ['#BFDDF6', '#9CC7EC'], green: ['#C6EBBC', '#A3D996'], purple: ['#DFCDF3', '#C7ACE7'] };
const SK_TAP = 8;          // screen px: a strip press that moves less than this is a tap (the menu)
const SK_CORNER = 24;      // screen px around the corner mark that grab the resize
let R = null;        // the desk's place on screen, refreshed at every pen-down and resize
let cur = -1;
let pinned = null;   // a page asked for by number (arrows, page list) stays current while any of it shows
let raf = 0;         // a frame is asked for
let glide = null;    // { vx, vy (px per ms on screen), t } while the stack glides after a flick
let shown = '';      // the transform last written
let hintT = 0;       // pw-v8i: while set, #stack carries will-change: transform for a gesture (hint()); the timer takes it off
let backT = 0;       // pw-v8i: the timer that puts the hint back on after HINT_BACK_MS of rest
let movedAt = 0;     // U4a: when a frame last moved the stack (a pan, a glide, a pinch, the wheel)
let bgN = 0;         // unique pattern ids, one set per page
let lock = false;    // pw-v7b: the zoom lock, per open note (app.js turns it off on every open and close; never saved)
let held = false;    // pw-v8k: the stack was shifted to stay under the pen across a resize; the clamp waits for the lift
let gap = null;      // pw-v8l: [screenX - clientX, screenY - clientY] of the pen's last event = where the window sits on the screen
let lastHold = { src: '', dx: 0, dy: 0 };   // pw-v8l: the last hold's source (rect | gap) and shift, for ?dbg=1
const stats = { resizes: 0, fits: 0, cause: '', redraws: 0, holds: 0 };   // pw-v7b: window resizes, fit() calls and the last fit's cause, for ?dbg=1; pw-v8i: redraws = the will-change hint taken off after a still moment; pw-v8k: holds = resizes ridden out under the pen

// a page's size in page px at zoom 1. `p` is the page row (or, as before U4a, just its orientation). A normal page is A4
// in its orientation. U4a: a page made from a PDF page (pdf_w, pdf_h = that page's size in PDF points) takes the PDF
// page's own shape, no white bars: taller than wide (or square) = the A4 portrait width, wider than tall = the A4
// landscape width, the height by the PDF page's aspect, rounded to a whole px (an A4 PDF page is exactly an A4 page).
export function pageSize(p) {
  const o = typeof p === 'string' ? p : (p && p.orientation);
  if (p && typeof p === 'object' && p.pdf_w > 0 && p.pdf_h > 0) {
    const s = pdfShape(p), w = s.w > s.h ? A4.h : A4.w;
    return { w, h: Math.max(1, Math.round(w * s.h / s.w)) };
  }
  return o === 'landscape' ? { w: A4.h, h: A4.w } : { ...A4 };
}
// pw-v7p: a PDF page's shape as it is shown, in points: pdf_w, pdf_h are the file's, a quarter turn (pages.pdf_rot) swaps them
export function pdfShape(p) {
  return (p.pdf_rot || 0) % 180 ? { w: p.pdf_h, h: p.pdf_w } : { w: p.pdf_w, h: p.pdf_h };
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

// pw-v8i (her "washy, still loading" look on an old note, PROVEN on her tablet 3 Nov over the cable): with `will-change:
// transform` always on #stack, Chrome kept the raster it drew at the OLD zoom and stretched it after every pinch (her
// ink's edges faded over 4 px instead of 1; the PDF canvases, their own layers, were fine) until something redrew the
// stack: a page added (the stack's size changes), the screen off and on (her "10 minutes"). So the hint is on the stack
// only while it moves: put on before the first move's frame (request, a finger down) and taken off once the stack has
// been still HINT_MS, which makes Chrome redraw at the new zoom; the pinch itself stays composited. Measured on the
// tablet: the same screen went crisp within 0.3 s of the hint coming off (measured at 0.3, 0.6 and 1.0 s), and STAYED
// crisp when the hint went back on a second later (twice: after 1.0 s and after 1.5 s off). So the hint goes back on
// HINT_BACK_MS after it came off: left off until the next gesture, Chrome composited the stack again at that gesture's
// first frame, a 66 ms frame on the slowed-CPU scroll measurement (tests/test_pdfscroll.py, the plain ink note); this
// way both redraws land while she is still. A gesture inside that second just puts the hint on at once. (A one-frame
// off, two rAFs, was never proven on the tablet: a short off may not finish its redraw before the layer is made again.)
// stats.redraws counts the hint coming off (viewStats).
// pw-v8j: opening a note (fit) draws a FRESH sheet tree, which Chrome rasters at the zoom it has, so no off/on redraw is
// needed there: the hint simply stays on and her first pan starts composited. Measured (tests/test_pdfscroll.py --after,
// slowed CPU): with the off/on cycle after an open, the first pan of a PDF note paid 1 to 3 frames of 33 to 67 ms; the
// previous release (pw-v8h, the hint always on) paid none.
function hintKeep() {
  clearTimeout(hintT); hintT = 0; clearTimeout(backT); backT = 0;
  stack.style.willChange = 'transform';
}
function hint() {
  if (backT) { clearTimeout(backT); backT = 0; }
  if (!hintT) stack.style.willChange = 'transform';
  else clearTimeout(hintT);
  hintT = setTimeout(() => {
    hintT = 0; stats.redraws++;
    stack.style.willChange = '';                                             // off: Chrome redraws the stack at this zoom
    backT = setTimeout(() => { backT = 0; if (!hintT) stack.style.willChange = 'transform'; }, HINT_BACK_MS);
  }, HINT_MS);
}

function apply() {
  const t = `translate(${V.x}px, ${V.y}px) scale(${V.z})`;
  if (t !== shown) { hint(); shown = t; stack.style.transform = t; stack.dataset.zoom = V.z.toFixed(3); }
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
function request() { hint(); if (!raf) raf = requestAnimationFrame(frame); }   // pw-v8i: the hint goes on before the move's frame
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

// pw-v9c: the box is the pages' and the stickies' together (L.box = [x0, y0, x1, y1] in stack px); with no sticky it is
// [0, 0, L.w, L.h] and every line below works out exactly as it did
function clampView() {
  const dw = desk.clientWidth, dh = desk.clientHeight, [x0, y0, x1, y1] = L.box;
  const w = (x1 - x0) * V.z, h = (y1 - y0) * V.z;
  if (w <= dw - 2 * MARGIN) V.x = (dw - w) / 2 - x0 * V.z;
  else V.x = Math.min(MARGIN - x0 * V.z, Math.max(dw - MARGIN - x1 * V.z, V.x));
  if (h <= dh - 2 * MARGIN) V.y = MARGIN - y0 * V.z;
  else V.y = Math.min(MARGIN - y0 * V.z, Math.max(dh - MARGIN - y1 * V.z, V.y));
}

// draws every page of the note, in order; keeps the view where it was. pw-v9c: `stickies` (the second argument) = the
// note's live sticky rows; they are laid out after the sheets (setStickies)
export function showStack(pages, stickies = []) {
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
  L.box = [0, 0, L.w, L.h];
  stack.style.width = L.w + 'px'; stack.style.height = L.h + 'px';
  cur = -1; viewKey = '';
  if (pinned !== null && pinned >= L.tops.length) pinned = L.tops.length - 1;
  stopGlide(); settle(); clampView(); apply();
  onSheets([...stack.querySelectorAll('.sheet')]);
  setStickies(stickies);
}

// ---------------------------------------------------------------- pw-v9c: the stickies on the desk
// a page's top-left x in stack px (by its index in the stack)
const pageLeft = (i) => (L.w - L.sizes[i].w) / 2;
// the stickies as they are now, laid out: elements made for new rows (handed to onStickies, so js/ink.js attaches their
// layers), moved, resized and recoloured for known ones, removed for rows that left. A sticky whose anchor is not in the
// stack is not shown. The z-order of the stickies already shown is kept (most recently touched on top); new ones go on top.
export function setStickies(rows) {
  const want = new Map();
  for (const r of rows) if (L.ids.includes(r.anchor_id)) want.set(r.id, r);
  if (SG && !want.has(SG.id)) SG = null;                                   // the sticky under a gesture went (another device)
  L.sk = L.sk.filter((k) => { if (want.has(k.id)) return true; k.el.remove(); return false; });
  const made = [], resized = [];
  for (const [id, r] of want) {
    let k = L.sk.find((x) => x.id === id);
    if (!k) {
      const el = document.createElement('div');
      el.dataset.id = id;
      el.innerHTML = '<div class="strip"><i></i></div><span class="corner"></span>';
      k = { id, el };
      L.sk.push(k); made.push(el);
    } else if (k.w !== r.sk_w) resized.push(k);
    Object.assign(k, { anchor: r.anchor_id, x: r.sk_x, y: r.sk_y, w: r.sk_w, colour: r.sk_colour });
  }
  for (const k of L.sk) { if (SG && SG.k === k) continue; placeSticky(k); if (!k.el.parentNode) stack.appendChild(k.el); }
  stickyBox();
  if (made.length || resized.length) onStickies(made, resized.map((k) => [k.id, k.w]));
}
// one sticky's element where its row says
function placeSticky(k) {
  const i = L.ids.indexOf(k.anchor), el = k.el;
  el.className = 'sticky ' + (SK_COLOURS[k.colour] ? k.colour : 'yellow');
  el.dataset.anchor = k.anchor;
  el.style.left = (pageLeft(i) + k.x) + 'px'; el.style.top = (L.tops[i] + k.y) + 'px';
  el.style.width = el.style.height = k.w + 'px';
  el.style.transform = '';
}
// the pan box grows to cover every sticky; the stack's own size covers the positive side of it. Right after she drops or
// resizes a sticky (keepOnce) the box also covers what the desk shows now, so a box that shrank (a far-margin sticky
// dragged back in) never makes the clamp jump the stack, and the sticky stays exactly where she let go; the next layout
// measures the box plainly again.
let keepOnce = false;
function stickyBox() {
  let [x0, y0, x1, y1] = [0, 0, L.w, L.h];
  for (const k of L.sk) {
    const i = L.ids.indexOf(k.anchor), l = pageLeft(i) + k.x, t = L.tops[i] + k.y;
    x0 = Math.min(x0, l); y0 = Math.min(y0, t); x1 = Math.max(x1, l + k.w); y1 = Math.max(y1, t + k.w);
  }
  if (keepOnce && L.sk.length) {
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    const dw = desk.clientWidth, dh = desk.clientHeight;
    x0 = Math.min(x0, (MARGIN - V.x) / V.z); x1 = Math.max(x1, (dw - MARGIN - V.x) / V.z);
    y0 = Math.min(y0, (MARGIN - V.y) / V.z); y1 = Math.max(y1, (dh - MARGIN - V.y) / V.z);
  }
  keepOnce = false;
  L.box = [x0, y0, x1, y1];
  stack.style.width = x1 + 'px'; stack.style.height = y1 + 'px';
  stopGlide(); settle(); clampView(); apply();
}
// a sticky to the top of the pile (Bring to front, and every strip press): last in L.sk and in the DOM. Nothing is saved.
export function stickyFront(id) {
  const k = L.sk.find((x) => x.id === id);
  if (!k) return;
  L.sk = [...L.sk.filter((x) => x !== k), k];
  if (stack.lastElementChild !== k.el) stack.appendChild(k.el);
}
export function stickyOrder() { return L.sk.map((k) => k.id); }
// the corner mark's centre along the diagonal (css: 4 px in, 12% of the side, at most 18 px)
const cornerAt = (w) => w - 4 - Math.min(0.12 * w, 18) / 2;
// the sticky under a client point, topmost first: { id, x, y (sticky px), w, part: 'strip' | 'corner' | 'body' } or null.
// The corner reaches SK_CORNER screen px around its mark (a little past the square).
export function stickyAt(cx, cy) {
  if (!L.sk.length) return null;
  const [sx, sy] = deskPoint(cx, cy), reach = SK_CORNER / V.z;
  for (let j = L.sk.length - 1; j >= 0; j--) {
    const k = L.sk[j], i = L.ids.indexOf(k.anchor);
    if (i < 0) continue;
    const x = sx - pageLeft(i) - k.x, y = sy - L.tops[i] - k.y, m = cornerAt(k.w);
    if (Math.hypot(x - m, y - m) <= reach) return { id: k.id, x, y, w: k.w, part: 'corner' };
    if (x >= 0 && x <= k.w && y >= 0 && y <= k.w) return { id: k.id, x, y, w: k.w, part: y <= SK_STRIP ? 'strip' : 'body' };
  }
  return null;
}
// pw-v9c, for js/ink.js: the surface (a sticky first, then a page) under a client point, in that surface's own px. A
// sticky's index is 'sk:<id>' (a string), a page's its number, exactly as pageAt gives it.
export function surfaceAt(cx, cy) {
  const k = stickyAt(cx, cy);
  if (k && k.x >= 0 && k.y >= 0 && k.x <= k.w && k.y <= k.w) return { index: 'sk:' + k.id, id: k.id, x: k.x, y: k.y, w: k.w, h: k.w, sticky: true };
  return pageAt(cx, cy);
}
export function surfacePoint(index, cx, cy) {
  if (typeof index !== 'string') return pagePoint(index, cx, cy);
  const k = L.sk.find((x) => 'sk:' + x.id === index), i = k ? L.ids.indexOf(k.anchor) : -1;
  if (i < 0) return [NaN, NaN];
  const [sx, sy] = deskPoint(cx, cy);
  return [sx - pageLeft(i) - k.x, sy - L.tops[i] - k.y];
}
// where a new sticky of side w lands on page `index` (her design): beside the page on the right, 24 px out, 24 px below
// the top of what she sees of that page (kept within the page's height); when the page's right edge is within 0.6 of the
// sticky's width of the desk's right edge on screen (portrait on the tablet): its left third on the page, the rest
// hanging off
export function stickySpot(index, w = SK_SIZE) {
  const s = L.sizes[index];
  if (!s) return { x: 0, y: 0 };
  if (raf) clampView();
  const dw = desk.clientWidth, right = V.x + (pageLeft(index) + s.w) * V.z;
  const top = -V.y / V.z - L.tops[index];
  const y = Math.max(0, Math.min(s.h - w, Math.max(0, top) + 24));
  const x = dw - right < w * V.z * 0.6 ? s.w - w / 3 : s.w + 24;
  return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
}
// the page a stack point lies on (its index), or -1
function pageAtStack(sx, sy) {
  for (let i = 0; i < L.tops.length; i++) {
    const s = L.sizes[i], x = sx - pageLeft(i), y = sy - L.tops[i];
    if (x >= 0 && x <= s.w && y >= 0 && y <= s.h) return i;
  }
  return -1;
}
// a sticky being dragged (strip) or resized (corner): { id, k, pid, kind, c0, c, dx, dy, w, far, touch }
let SG = null;
let cancelHoldOuter = () => {};
export function stickyBusy() { return !!SG; }
function stickyStart(e, hit, touch) {
  const k = L.sk.find((x) => x.id === hit.id);
  if (!k) return false;
  stickyFront(k.id);
  SG = { id: k.id, k, pid: e.pointerId, kind: hit.part === 'corner' ? 'resize' : 'move', c0: [e.clientX, e.clientY], c: [e.clientX, e.clientY],
         dx: 0, dy: 0, w: k.w, far: 0, touch };
  stopGlide(); cancelHoldOuter();
  try { desk.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  e.preventDefault();
  return true;
}
function stickyMove(e) {
  const g = SG;
  g.c = [e.clientX, e.clientY];
  const ex = e.clientX - g.c0[0], ey = e.clientY - g.c0[1];
  g.far = Math.max(g.far, Math.hypot(ex, ey));
  g.dx = ex / V.z; g.dy = ey / V.z;
  if (g.kind === 'move') { g.k.el.style.transform = `translate(${g.dx}px, ${g.dy}px)`; return; }   // live, a transform only
  g.w = Math.round(Math.max(SK_MIN, Math.min(SK_MAX, g.k.w + (g.dx + g.dy) / 2)) * 10) / 10;       // along the diagonal: square, top-left fixed
  g.k.el.style.width = g.k.el.style.height = g.w + 'px';
  onStickySize(g.id, g.w);
}
// the lift: a tap (the menu), or the move / resize handed to app.js as the row's new numbers (it saves them, lays out)
function stickyEnd(e, cancelled) {
  const g = SG;
  SG = null;
  try { desk.releasePointerCapture(g.pid); } catch (_) { /* ignore */ }
  if (!cancelled && e && Number.isFinite(e.clientX)) { SG = g; stickyMove(e); SG = null; }
  const k = g.k;
  if (cancelled || (g.kind === 'move' && g.far < SK_TAP) || (g.kind === 'resize' && g.w === k.w)) {
    placeSticky(k);
    if (g.kind === 'resize') onStickySize(g.id, k.w);
    if (!cancelled && g.kind === 'move') onStickyTap(g.id, g.c[0], g.c[1]);
    return;
  }
  keepOnce = true;
  if (g.kind === 'resize') { onStickyChange(g.id, { sk_w: g.w }); keepOnce = false; return; }
  // the centre over another page: that page becomes its anchor; over no page: the anchor stays
  const i0 = L.ids.indexOf(k.anchor), l = pageLeft(i0) + k.x + g.dx, t = L.tops[i0] + k.y + g.dy;
  let i = pageAtStack(l + k.w / 2, t + k.w / 2);
  if (i < 0) i = i0;
  const r = (v) => Math.round(v * 10) / 10;
  onStickyChange(g.id, { anchor_id: L.ids[i], sk_x: r(l - pageLeft(i)), sk_y: r(t - L.tops[i]) });
  keepOnce = false;
}

// a page's bookmark (pw-v4r), the Samsung Notes way: a ribbon tab hanging from the page's top edge near the right
// (16 x 26 page px, 12 px in from the right, its bottom notched into a V), above the ink, never in the pen's way.
// pw-v9a: the page list's thumbs no longer use this tab; each thumb has its own tappable ribbon button (app.js, RIB).
// This tab is the big page's only, untouchable by the pen; css paints it the ink blue, the paper is white in both modes.
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
  hintKeep();                                             // pw-v8j: a fresh stack at this zoom, no redraw cycle needed
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

// pw-v8k: a resize WHILE THE PEN WRITES. Her palm on the screen's edge shows Android's bars (and a few seconds later hides
// them); Chrome resizes the page each time, so the desk moves on screen by the bar's height while her pen stays where it
// is. The maths were right and the ink wrong: it carried on where the pen now sat on the moved page, a kink the height
// of a bar mid-stroke (her video, 3 Nov 16:51). Now the stack is shifted the other way by exactly what the desk moved,
// with no clamp, so the page point under the pen tip does not move and the stroke runs straight on; the clamp (and a
// normal relayout) waits for the lift. R is the desk's place as last measured (pen-down or the previous hold).
// pw-v8l: pw-v8k read only the desk's move INSIDE the window, and on her tablet that is not what moves: the status bar
// pushes the whole window down the screen while the desk keeps its place inside it, so the rect read 0 and the ink still
// stepped. Now every pen event is checked two ways: (1) the desk's rect against R (a move inside the window: a header, a
// safe-area inset, a relayout with or without a resize event), (2) the event's screen-minus-client gap against the last
// event's (the window itself moved on the screen; the pen tip did not move, so its screen position holds while the client
// position jumps by the bar). Either feeds holdBy with the move; the resize event itself only re-reads the rect now.
function holdBy(src, dx, dy) {
  V.x -= dx; V.y -= dy;
  held = true; stats.holds++; lastHold = { src, dx, dy };
  stopGlide(); if (raf) { cancelAnimationFrame(raf); raf = 0; }
  apply();
}
function holdUnderPen() {
  const old = R, r = (R = desk.getBoundingClientRect());
  if (old && (r.left !== old.left || r.top !== old.top)) holdBy('rect', r.left - old.left, r.top - old.top);
}
const GAP_MIN = 12;    // px: a jump of the window on the screen smaller than this is ignored (a bar is 24 px or more); a pen cannot fake it, its screen position moves with it
const GAP_MAX = 400;   // px: bigger than any bar: nonsense, ignored
// one pen event: the window's place on the screen from screenX/Y - clientX/Y, compared with the last event's
function penGap(e) {
  if (!Number.isFinite(e.screenX) || !Number.isFinite(e.screenY)) return;
  const g = [e.screenX - e.clientX, e.screenY - e.clientY];
  if (gap) {
    const dx = g[0] - gap[0], dy = g[1] - gap[1], m = Math.max(Math.abs(dx), Math.abs(dy));
    if (m >= GAP_MIN && m <= GAP_MAX) holdBy('gap', dx, dy);
    else if (m > GAP_MAX) { gap = g; return; }
    else return;
  }
  gap = g;
}

// pw-v7b: the zoom lock. Locked: the zoom cannot change and only two fingers move the stack (see initPage); a glide
// still running stops where it is. app.js owns the button and turns the lock off on every note open and close.
export function setLock(on) { lock = !!on; if (lock) stopGlide(); }
export function locked() { return lock; }
// ?dbg=1 (js/dbg.js): window resizes seen, fit() calls and the last fit's cause, and the lock
export function viewStats() { return { resizes: stats.resizes, fits: stats.fits, cause: stats.cause, lock, hint: !!hintT, redraws: stats.redraws, holds: stats.holds, held, lastHold: { ...lastHold }, gap: gap ? [...gap] : null }; }   // pw-v8i: hint = a gesture's hint is on now; redraws = settles so far

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
  if (els.onStickies) onStickies = els.onStickies;      // pw-v9c
  if (els.onStickySize) onStickySize = els.onStickySize;
  if (els.onStickyTap) onStickyTap = els.onStickyTap;
  if (els.onStickyChange) onStickyChange = els.onStickyChange;
  const touches = new Map();
  let pinch = null, drag = null, penSeen = -1e9, inkId = null, chord = false, holdT = 0;
  const now = () => performance.now();
  const when = (e) => e.timeStamp || now();       // when the finger was there (a late event keeps its own time)
  let gRect = null;                                 // pw-v7n: the desk's place, measured once per finger gesture (it was every move)
  const rect = () => gRect || desk.getBoundingClientRect();
  const pt = (e) => { const r = rect(); return [e.clientX - r.left, e.clientY - r.top]; };
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const TAP_PX = 6;                                 // a finger that lifts within 6 px of where it landed is a tap (the selection clears)
  const FINGER_HOLD = 500;                          // ms a finger stays still (within TAP_PX) before the hold menu opens
  function cancelHold() { clearTimeout(holdT); holdT = 0; }
  cancelHoldOuter = cancelHold;
  // one finger down: when it is still there and still 500 ms later, its pan stops and the hold menu opens
  function armHold(id) {
    cancelHold();
    holdT = setTimeout(() => {
      holdT = 0;
      if (!drag || drag.id !== id || pinch || inkId !== null || touches.size !== 1 || now() - penSeen < 600) return;
      const [cx, cy] = drag.c;
      drag = null; touches.delete(id); if (!touches.size) gRect = null;
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
    gap = null; penGap(e);                                                  // pw-v8l: where the window sits on the screen at pen-down
    if (!ink.down(e)) return false;
    inkId = e.pointerId;
    touches.clear(); pinch = null; drag = null; cancelHold(); gRect = null;   // a palm already down stops panning
    try { desk.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    e.preventDefault();
    return true;
  }
  // pw-v9c: a press on a sticky's strip or corner (pen, mouse or ONE finger) drags or resizes it, before anything else
  const stickyGrip = (e) => {
    if (SG || inkId !== null || e.button > 0 || e.target.closest('button, #pageList')) return false;
    const hit = stickyAt(e.clientX, e.clientY);
    return !!hit && hit.part !== 'body' && stickyStart(e, hit, e.pointerType === 'touch');
  };
  desk.addEventListener('pointerdown', (e) => {
    stopGlide(); settle(); unscroll();                                     // any touch, pen or click holds the stack where it is
    if (SG && e.pointerType === 'touch' && SG.touch && e.pointerId !== SG.pid) {   // pw-v9c: a second finger: the drag lets go, the pinch takes both
      const first = { id: SG.pid, c: SG.c };
      stickyEnd(null, true);
      if (!touches.size) gRect = desk.getBoundingClientRect();
      touches.set(first.id, [first.c[0] - gRect.left, first.c[1] - gRect.top]);
      try { desk.setPointerCapture(first.id); } catch (_) { /* ignore */ }
    } else if (SG) return;                                                 // one sticky gesture at a time
    if (e.pointerType === 'pen' || e.pointerType === 'mouse') {           // the S Pen and the mouse draw
      if (e.pointerType === 'pen') { penSeen = performance.now(); cancelHold(); }
      if (e.button > 0 && e.button !== 2) return;                         // button 2: the pen button / right mouse (ink.down turns it away)
      if (stickyGrip(e)) return;                                           // pw-v9c
      chord = false;
      inkDown(e);
      return;
    }
    if (e.pointerType !== 'touch') return;
    if (inkId !== null) return;                                            // a finger is ignored while the pen writes
    if (e.target.closest('button, #pageList')) return;                     // buttons and the page list stay tappable
    if (performance.now() - penSeen < 600) return;                         // palm while the pen is near
    if (!touches.size && stickyGrip(e)) return;                            // pw-v9c: one finger on a strip drags it, even zoom-locked
    if (!touches.size) gRect = desk.getBoundingClientRect();              // the first finger: the desk's place for this gesture
    touches.set(e.pointerId, pt(e));
    hint();                                                                // pw-v8i: composited before the first move
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
    if (SG && e.pointerId === SG.pid) { stickyMove(e); return; }          // pw-v9c: a sticky being dragged or resized
    if (e.pointerType === 'pen') { penSeen = performance.now(); if (holdT) cancelHold(); }
    if (e.pointerId === inkId) {
      if (chord && !(e.buttons & 1)) {                                     // the tip lifted, the pen button still held: the end
        endInk(e, false);
        try { desk.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
        return;
      }
      const all = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
      holdUnderPen(); penGap(e);                                           // pw-v8l: the desk or the window moved under the pen? shift first, then draw
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
  // the pen's stroke ends (lift, cancel, or the tip up with the button still held). pw-v8k: a stroke that rode out a
  // resize (holdUnderPen) gets its normal relayout now, the clamp included: a jump between strokes, never inside one
  function endInk(e, cancelled) {
    if (!cancelled) { holdUnderPen(); penGap(e); }                         // pw-v8l: the last point measured like every other
    inkId = null; chord = false; gap = null; ink.up(e, cancelled);
    if (held) { held = false; gRect = null; relayout(); }
  }
  const up = (e) => {
    if (SG && e.pointerId === SG.pid) { stickyEnd(e, e.type === 'pointercancel'); return; }   // pw-v9c
    if (e.pointerId === inkId) { endInk(e, e.type === 'pointercancel'); return; }
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
    if (!touches.size) gRect = null;
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
  // pw-v8k: while the pen writes, the resize is ridden out under the pen (holdUnderPen) and the relayout waits for the lift
  window.addEventListener('resize', () => {
    stats.resizes++;
    if (inkId !== null && L.tops.length) { holdUnderPen(); return; }
    R = null; gRect = null; stopGlide(); if (L.tops.length) relayout();
  });
  desk.addEventListener('scroll', () => { unscroll(); R = null; gRect = null; }, { passive: true });   // cannot fire with overflow: clip; a fallback only
}
