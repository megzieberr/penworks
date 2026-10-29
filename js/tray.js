// PenWorks pen tray (right edge): her 13 colours, a spare spectrum slot, pen, highlighter, stroke eraser, area eraser,
// restyle, rectangle select, a gap, undo, redo, and an empty slot for the Tools button (U5). One icon per tool, no
// labels. The pen and the highlighter each open a small panel when tapped while already selected.
// Round 1 (pw-v7k, her ruling 29 Oct): ONE colour for the pen and the highlighter. The colour belongs to her hand, not
// the tool: a colour tap sets it, a switch between pen and highlighter never changes it. Width, dash and opacity stay
// per tool.
// Colours: hold a swatch (350 ms, still) and drag it up or down to put her 13 in her order; the order is
// kept on the device. Under them a 14th spare slot (rainbow ring) holds any colour picked from the honeycomb.
// Restyle has its own colour (it starts as the current ink colour when restyle is picked); a colour tap
// while restyle is on changes only that. With the select tool and a selection on the page, a colour tap
// recolours the selection and a tap on Restyle restyles it (the select tool and the selection stay).
// U3c: the tray state follows her across devices. keep() writes it here (localStorage pw.tools, with its tray_at stamp)
// and hands it to app.js (onKeep), which sends it to profiles.settings a second after the last change. At start the
// device copy is used at once; app.js then offers the database's copy to adopt() when it is the newer one.
import { setTool, setStyles, hasSelection, recolourSelection, restyleSelection } from './ink.js';

// Megan's own 13 (25 Oct 17:43: Sky blue out, Light green and Teal in), in her order: [hex, name].
// This stays the DEFAULT order.
export const COLOURS = [
  ['#2CB05F', 'Green'], ['#37D366', 'Light green'], ['#0D0DFF', 'Blue'], ['#FF0C84', 'Pink'], ['#FF7043', 'Orange'],
  ['#A83AFF', 'Purple'], ['#FFC107', 'Amber'], ['#00BCD5', 'Cyan'], ['#04878F', 'Teal'], ['#FF00FF', 'Magenta'],
  ['#FF3636', 'Red'], ['#000000', 'Black'], ['#808080', 'Grey'],
];
// The one ink colour starts as Black (the highlighter's old Amber default is gone: she picks Amber when she wants it).
// Both pen.colour and highlighter.colour are still kept, always equal: profiles.settings.tray and the device copy keep
// the shape an older app (and a row saved before round 1) has, so either one still loads.
const DEFAULT_COLOUR = '#000000';
const DEFAULTS = {
  pen: { colour: DEFAULT_COLOUR, width: 2.5, dash: 'solid' },
  highlighter: { colour: DEFAULT_COLOUR, width: 18, opacity: 0.4 },
};
const KNOWN = new Set(COLOURS.map(([c]) => c.toLowerCase()));
const CANON = new Map(COLOURS.map(([c]) => [c.toLowerCase(), c]));
const NAME = new Map(COLOURS);
const HOLD_MS = 350, HOLD_PX = 6;
const HEX = /^#?([0-9a-f]{6})$/i;
const normHex = (v) => { const m = HEX.exec(String(v || '').trim()); return m ? '#' + m[1].toUpperCase() : null; };
const same = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
const RANGE = {
  pen: { min: 1, max: 12, step: 0.5 },
  highlighter: { min: 6, max: 40, step: 2 },
  opacity: { min: 20, max: 80, step: 10 },
};
const KEY = 'pw.tools';
const INK = ['pen', 'highlighter'];

const ICONS = {
  pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 19.5l1.1-4.4L15.4 5.3a2 2 0 0 1 2.8 0l.5.5a2 2 0 0 1 0 2.8L8.9 18.4z"/><path d="M13.6 7.1l3.3 3.3"/></svg>',
  highlighter: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8.6 13.4l6.9-6.9a2 2 0 0 1 2.8 0l.2.2a2 2 0 0 1 0 2.8l-6.9 6.9z"/><path d="M8.6 13.4L6.2 15.8l2 2 2.4-2.4"/><path d="M6.2 15.8L4 20h4.2"/></svg>',
  eraser: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8.6 19.5L4 14.9a1.6 1.6 0 0 1 0-2.3l7.6-7.6a1.6 1.6 0 0 1 2.3 0l5.6 5.6a1.6 1.6 0 0 1 0 2.3l-7 7z"/><path d="M8.3 8.7l6.4 6.4"/><path d="M12.5 19.5H20"/></svg>',
  restyle: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18.5 4.5a2.1 2.1 0 0 1 0 3L12 14l-3-3 6.5-6.5a2.1 2.1 0 0 1 3 0z"/><path d="M9 11c-2.2 0-3.6 1.4-3.6 3.4 0 1.6-.8 2.6-2 3.1 1.2 1.4 3.3 1.9 5.2 1.4 2.1-.6 3.4-2.3 3.4-4.4z"/></svg>',
  select: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7V4h3M10 4h4M17 4h3v3M20 10v4M20 17v3h-3M14 20h-4M7 20H4v-3M4 14v-4"/></svg>',
  area: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7.4 15L3.6 11.2a1.3 1.3 0 0 1 0-1.8l5.8-5.8a1.3 1.3 0 0 1 1.8 0l3.8 3.8a1.3 1.3 0 0 1 0 1.8L9.2 15z"/><path d="M6.6 6.4l5 5"/><circle cx="16.8" cy="16.8" r="4.6"/></svg>',
};
// pw-v7d: the calculator button at the very bottom of the tray (later it becomes the Tools panel)
const CALC_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8.5 7.5h7"/><path d="M9 13h.01M12 13h.01M15 13h.01M9 16.5h.01M12 16.5h.01M15 16.5h.01" stroke-width="2.4"/></svg>';
const TITLES = { pen: 'Pen', highlighter: 'Highlighter', eraser: 'Stroke eraser', area: 'Area eraser', restyle: 'Restyle', select: 'Select' };

let st, tray, panel, picker, colours, specBtn, btns = {}, swatches = [];

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids) if (c !== null && c !== undefined) e.append(c);
  return e;
}

// whatever was saved (this device's copy, or the database's): unknown colours fall back, a bad order is ignored
function sanitise(saved) {
  if (!saved || typeof saved !== 'object') saved = {};
  const s = { tool: INK.includes(saved.tool) ? saved.tool : 'pen',
              pen: { ...DEFAULTS.pen, ...(saved.pen || {}) }, highlighter: { ...DEFAULTS.highlighter, ...(saved.highlighter || {}) } };
  // her order: used only when it is exactly her 13 hex values in some order, otherwise her default order
  const o = saved.order;
  const okOrder = Array.isArray(o) && o.length === COLOURS.length && o.every((c) => typeof c === 'string' && KNOWN.has(c.toLowerCase()))
    && new Set(o.map((c) => c.toLowerCase())).size === COLOURS.length;
  s.order = okOrder ? o.map((c) => CANON.get(c.toLowerCase())) : COLOURS.map(([c]) => c);
  s.spec = normHex(saved.spec);                                   // the spare slot: null until she first picks
  // the one colour: the colour of the saved tool (a row from before round 1 can hold two different ones; the tool she
  // had on wins). A colour from an older set (not one of the 13, not the spare slot's) falls back to Black; width,
  // dash, opacity stay
  const c = String(s[s.tool].colour);
  const one = KNOWN.has(c.toLowerCase()) ? CANON.get(c.toLowerCase()) : s.spec && same(c, s.spec) ? s.spec : DEFAULT_COLOUR;
  for (const t of INK) s[t].colour = one;
  s.lastInk = s.tool;
  const rc = String((saved.restyle && saved.restyle.colour) || '');   // restyle's own colour, the same rule
  s.restyle = { colour: KNOWN.has(rc.toLowerCase()) ? CANON.get(rc.toLowerCase()) : s.spec && same(rc, s.spec) ? s.spec : s[s.lastInk].colour };
  return s;
}
function readLocal() {
  try { const v = JSON.parse(localStorage.getItem(KEY) || 'null'); return v && typeof v === 'object' ? v : null; } catch (_) { return null; }
}
function load() { return sanitise(readLocal() || {}); }
// the one shape that is kept, here and in profiles.settings.tray
const kept = () => JSON.parse(JSON.stringify({ tool: st.lastInk, pen: st.pen, highlighter: st.highlighter, restyle: st.restyle, order: st.order, spec: st.spec }));
function writeLocal(tray, at) {
  try { localStorage.setItem(KEY, JSON.stringify({ ...tray, tray_at: at })); } catch (_) { /* ignore */ }
}
let onKeep = () => {};
function keep() {
  const tray = kept(), at = new Date().toISOString();
  writeLocal(tray, at);
  try { onKeep(tray, at); } catch (_) { /* the device copy is kept either way */ }
}
function push() {
  setStyles(st.pen, st.highlighter, st.restyle);                 // restyle hands out these
  setTool(st.tool, INK.includes(st.tool) ? st[st.tool] : null);
  paint();
}
const inkColour = () => st.pen.colour;                          // the one colour (highlighter.colour is always the same)
const setInk = (c) => { for (const t of INK) st[t].colour = c; };
const ringColour = () => (st.tool === 'restyle' ? st.restyle.colour : inkColour());   // the swatch ring
const specOn = () => !!st.spec && same(ringColour(), st.spec);
function paint() {
  for (const [t, b] of Object.entries(btns)) { b.classList.toggle('on', t === st.tool); b.setAttribute('aria-pressed', t === st.tool ? 'true' : 'false'); }
  const c = ringColour();
  swatches.forEach((s) => s.classList.toggle('on', same(s.dataset.colour, c)));
  if (specBtn) {
    specBtn.dataset.colour = st.spec || '';
    specBtn.style.setProperty('--spec', st.spec || '#FFFFFF');
    specBtn.classList.toggle('on', specOn());
  }
}

function useColour(c) {
  if (st.tool === 'restyle') { st.restyle.colour = c; keep(); push(); return; }   // restyle stays: only its own colour changes
  if (st.tool === 'select' && hasSelection()) { recolourSelection(c); return; }   // the selection takes it; no tool colour moves
  if (!INK.includes(st.tool)) st.tool = st.lastInk;              // after an eraser, a colour hands back the last ink tool
  setInk(c);                                                      // pen and highlighter both: one colour
  keep(); push();
}
function pickColour(c) { closePicker(); useColour(c); }
function pickTool(t) {
  closePicker();
  if (st.tool === t && INK.includes(t)) {
    if (!panel.hidden && panel.dataset.for === t) closePanel(); else openPanel(t);
    return;
  }
  if (t === 'restyle' && st.tool !== 'restyle') st.restyle.colour = inkColour();   // restyle starts in the current colour
  if (t === 'restyle' && st.tool === 'select' && hasSelection()) {  // a selection: restyle it, select stays, restyle is not entered
    closePanel(); keep(); push(); restyleSelection();
    return;
  }
  st.tool = t;
  if (INK.includes(t)) st.lastInk = t;
  closePanel(); keep(); push();
}
// the spare slot: the first tap (still empty) opens the picker; holding a colour, a tap selects it; tapped
// again while it is the selected swatch, the picker opens (the pen and highlighter panel rule)
function tapSpec() {
  if (!st.spec) { openPicker(); return; }
  if (specOn() && (INK.includes(st.tool) || st.tool === 'restyle')) { if (picker.hidden) openPicker(); else closePicker(); return; }
  useColour(st.spec);
}

// ---------------------------------------------------------------- the two panels
const snap = (v, R) => Math.min(R.max, Math.max(R.min, Math.round((v - R.min) / R.step) * R.step + R.min));
const fmtW = (v) => String(Math.round(v * 2) / 2);
function stepper(label, R, get, set, fmt) {
  const num = el('b', { class: 'num' });
  const slider = el('input', { type: 'range', min: R.min, max: R.max, step: R.step, 'aria-label': label });
  const minus = el('button', { class: 'step', type: 'button', 'aria-label': label + ' smaller' }, '−');
  const plus = el('button', { class: 'step', type: 'button', 'aria-label': label + ' bigger' }, '+');
  const show = () => { const v = get(); num.textContent = fmt(v); slider.value = String(v); minus.disabled = v <= R.min; plus.disabled = v >= R.max; };
  const put = (v) => { set(snap(v, R)); keep(); push(); show(); };
  minus.addEventListener('click', () => put(get() - R.step));
  plus.addEventListener('click', () => put(get() + R.step));
  slider.addEventListener('input', () => put(+slider.value));
  show();
  return el('div', { class: 'pgroup', 'data-field': label.toLowerCase() },
    el('div', { class: 'phd' }, label), el('div', { class: 'prow' }, minus, num, plus), slider);
}
function dashPair() {
  const row = el('div', { class: 'dashes' });
  for (const [k, label] of [['solid', 'Solid'], ['dashed', 'Dashed']]) {
    const line = `<svg viewBox="0 0 40 8"><line x1="3" y1="4" x2="37" y2="4" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"${k === 'dashed' ? ' stroke-dasharray="6 6"' : ''}/></svg>`;
    const b = el('button', { type: 'button', class: 'dash' + (st.pen.dash === k ? ' on' : ''), 'data-dash': k, 'aria-pressed': st.pen.dash === k ? 'true' : 'false' },
      el('span', { class: 'dl', html: line }), el('span', {}, label));
    b.addEventListener('click', () => {
      st.pen.dash = k; keep(); push();
      row.querySelectorAll('.dash').forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
    });
    row.append(b);
  }
  return row;
}
function openPanel(t) {
  closePicker();
  panel.textContent = '';
  panel.dataset.for = t;
  if (t === 'pen') {
    panel.append(stepper('Width', RANGE.pen, () => st.pen.width, (v) => { st.pen.width = v; }, fmtW), dashPair());
  } else {
    panel.append(
      stepper('Width', RANGE.highlighter, () => st.highlighter.width, (v) => { st.highlighter.width = v; }, fmtW),
      stepper('Opacity', RANGE.opacity, () => Math.round(st.highlighter.opacity * 100), (v) => { st.highlighter.opacity = v / 100; }, (v) => v + '%'));
  }
  panel.hidden = false;
  place(panel, btns[t]);
}
function place(card, by) {                                        // a card beside the tray (on its desk side), level with its button
  const tb = tray.getBoundingClientRect(), bb = by.getBoundingClientRect();
  const ph = card.offsetHeight;
  if (document.body.classList.contains('trayLeft')) {             // pw-v7c: the tray down the left edge, the card to its right
    card.style.left = tb.right + 8 + 'px'; card.style.right = '';
  } else {
    card.style.right = Math.max(8, innerWidth - tb.left + 8) + 'px'; card.style.left = '';
  }
  card.style.top = Math.max(8, Math.min(innerHeight - ph - 8, bb.top + bb.height / 2 - ph / 2)) + 'px';
}
export function closePanel() { if (panel && !panel.hidden) { panel.hidden = true; panel.textContent = ''; } }

// ---------------------------------------------------------------- hold and drag to reorder the 13
let drag = null, eatClick = false;
function dragStart(e) {
  if (e.button !== 0 || drag) return;
  const sw = e.currentTarget;
  eatClick = false;
  try { sw.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  drag = { sw, id: e.pointerId, x0: e.clientX, y0: e.clientY, lifted: false, timer: setTimeout(lift, HOLD_MS) };
}
function lift() {
  if (!drag) return;
  drag.timer = 0;
  drag.list = [...swatches];
  drag.from = drag.list.indexOf(drag.sw);
  drag.mid = drag.list.map((s) => { const r = s.getBoundingClientRect(); return r.top + r.height / 2; });
  drag.to = drag.from;
  drag.lifted = true;
  colours.classList.add('dragging');
  drag.sw.classList.add('lift');
  drag.sw.style.transform = 'scale(1.15)';
}
function dragMove(e) {
  if (!drag || e.pointerId !== drag.id) return;
  const dy = e.clientY - drag.y0;
  if (!drag.lifted) {                                             // moved before the hold time: a normal tap, nothing lifts
    if (drag.timer && Math.hypot(e.clientX - drag.x0, dy) > HOLD_PX) { clearTimeout(drag.timer); drag.timer = 0; }
    return;
  }
  e.preventDefault();
  const { mid, from, list } = drag, last = mid.length - 1;
  const d = Math.max(mid[0] - mid[from], Math.min(mid[last] - mid[from], dy));
  const y = mid[from] + d;
  let to = 0;                                                     // it lands past every neighbour whose midpoint it crossed
  mid.forEach((m, k) => { if (k !== from && m < y) to++; });
  drag.to = to;
  list.forEach((s, k) => {
    if (k === from) { s.style.transform = `translateY(${d}px) scale(1.15)`; return; }
    let n = k < from ? k : k - 1;
    if (n >= to) n++;
    s.style.transform = n === k ? '' : `translateY(${mid[n] - mid[k]}px)`;
  });
}
function dragEnd(e, cancelled) {
  if (!drag || e.pointerId !== drag.id) return;
  const d = drag; drag = null;
  clearTimeout(d.timer);
  if (!d.lifted) return;                                          // a tap (or a move before the hold): the click selects
  eatClick = true;
  if (!cancelled && d.to !== d.from) {
    const list = d.list.slice();
    list.splice(d.from, 1); list.splice(d.to, 0, d.sw);
    swatches = list;
    st.order = list.map((s) => s.dataset.colour);
    colours.prepend(...list);                                     // the spare slot stays last
    keep();
  }
  d.list.forEach((s) => { s.style.transform = ''; });
  d.sw.classList.remove('lift');
  colours.classList.remove('dragging');
  // eatClick stays set until the click that ends the drag (or the next pointerdown) clears it
}
function swatchClick(e) {
  if (eatClick) { eatClick = false; e.preventDefault(); return; }  // the click that ends a drag selects nothing
  pickColour(e.currentTarget.dataset.colour);
}

// ---------------------------------------------------------------- the honeycomb picker (the spare slot)
// Office's "Colors" honeycomb: a white centre and six rings of pointy-top hexagons (1 + 6 + 12 + ... + 36 = 127
// cells, no gaps). Each ring runs the hue once round (red straight up in every ring, so the colours line up in
// spokes): pastel in ring 1, the pure colours in ring 4, deep colours at the rim. Under it 15 greys from white to
// black and one bigger black cell. A tap (finger, pen or mouse) on a cell picks it.
const HC = { R: 10, pad: 4, gap: 10, Rs: 7.55, Rb: 14 };       // cell radius, edge room, gap above the greys, grey radii
const RING_S = [0, 70, 85, 95, 100, 100, 100];                  // HSL saturation % per ring (ring 0 = the white centre)
const RING_L = [100, 88, 76, 63, 50, 37, 25];                   // HSL lightness % per ring
const SQ3 = Math.sqrt(3);
let pkEls = null, pkCell = null;
function hslToHex(h, s, l) {
  s /= 100; l /= 100;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => { const k = (n + h / 30) % 12; return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)); };
  return '#' + [f(0), f(8), f(4)].map((x) => Math.round(x * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
}
const hexPts = (cx, cy, R) => Array.from({ length: 6 }, (_, k) => {    // pointy top: corners at -30, 30, 90, ... degrees
  const a = Math.PI / 180 * (60 * k - 30);
  return (cx + R * Math.cos(a)).toFixed(2) + ',' + (cy + R * Math.sin(a)).toFixed(2);
}).join(' ');
function combCells() {                                           // [{ id, x, y, k, colour, grey }]
  const { R, pad, gap, Rs, Rb } = HC, N = RING_S.length - 1;
  const W = 2 * pad + (2 * N + 1) * SQ3 * R, cx0 = W / 2, cy0 = pad + (1.5 * N + 1) * R;
  const rings = Array.from({ length: N + 1 }, () => []);
  for (let q = -N; q <= N; q++) for (let r = -N; r <= N; r++) {
    const ring = Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r));
    if (ring > N) continue;
    const x = SQ3 * R * (q + r / 2), y = 1.5 * R * r;
    let ang = Math.round(Math.atan2(x, -y) * 180 / Math.PI * 1e4) / 1e4;   // 0 = straight up, clockwise
    ang = ((ang % 360) + 360) % 360;
    rings[ring].push({ x: cx0 + x, y: cy0 + y, ang });
  }
  const cells = [];
  rings.forEach((list, ring) => {
    list.sort((a, b) => a.ang - b.ang).forEach((c, i) => cells.push({ id: ring + '-' + i, x: c.x, y: c.y, k: 1,
      colour: ring ? hslToHex(c.ang, RING_S[ring], RING_L[ring]) : '#FFFFFF' }));
  });
  const wS = SQ3 * Rs, wB = SQ3 * Rb, rowW = 15 * wS + 4 + wB, x0 = (W - rowW) / 2, gy = cy0 + (1.5 * N + 1) * R + gap + Rb;
  for (let i = 0; i < 15; i++) {
    const v = Math.round(255 * (1 - i / 14)).toString(16).padStart(2, '0').toUpperCase();
    cells.push({ id: 'g' + i, x: x0 + wS * (i + 0.5), y: gy, k: Rs / R, colour: '#' + v + v + v, grey: true });
  }
  cells.push({ id: 'g15', x: x0 + 15 * wS + 4 + wB / 2, y: gy, k: Rb / R, colour: '#000000', grey: true });
  return { cells, W, H: gy + Rb + pad };
}
function setSpec(c) {                                             // picking a colour also selects the slot
  st.spec = c;
  useColour(c);
}
function showPicker() {
  const { comb, sel, prev } = pkEls;
  let cell = pkCell && comb.querySelector(`[data-cell="${pkCell}"]`);
  if (!cell || !same(cell.dataset.colour, st.spec)) cell = st.spec ? comb.querySelector(`[data-colour="${st.spec}"]`) : null;
  pkCell = cell ? cell.dataset.cell : null;
  comb.querySelectorAll('[data-cell].on').forEach((c) => c.classList.remove('on'));
  if (cell) {
    cell.classList.add('on');
    sel.setAttribute('transform', `translate(${cell.dataset.x} ${cell.dataset.y}) scale(${cell.dataset.k})`);
    sel.removeAttribute('display');
  } else sel.setAttribute('display', 'none');
  prev.style.backgroundColor = st.spec || '#FFFFFF';
}
function buildPicker() {
  const { cells, W, H } = combCells();
  const polys = cells.map((c) => {
    const R = HC.R * c.k;
    return `<polygon class="${c.grey ? 'grey' : 'hx'}" data-cell="${c.id}" data-colour="${c.colour}" data-x="${c.x.toFixed(2)}" data-y="${c.y.toFixed(2)}"`
      + ` data-k="${c.k.toFixed(4)}" fill="${c.colour}" stroke="${c.colour}" points="${hexPts(c.x, c.y, R)}"/>`;
  }).join('');
  const ring = (R) => hexPts(0, 0, R);
  const comb = el('div', { class: 'comb', html:
    `<svg viewBox="0 0 ${W.toFixed(2)} ${H.toFixed(2)}" width="${W.toFixed(2)}" height="${H.toFixed(2)}" role="group" aria-label="Colours">`
    + polys + `<g class="hsel" display="none"><polygon class="o" points="${ring(HC.R + 1)}" vector-effect="non-scaling-stroke"/>`
    + `<polygon class="i" points="${ring(HC.R - 0.9)}" vector-effect="non-scaling-stroke"/></g></svg>` });
  const prev = el('span', { class: 'prev', 'aria-hidden': 'true' });
  const done = el('button', { type: 'button', class: 'done' }, 'Done');
  comb.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const c = e.target.closest && e.target.closest('[data-cell]');
    if (!c) return;
    e.preventDefault();
    pkCell = c.dataset.cell;
    setSpec(c.dataset.colour);
    showPicker();
  });
  done.addEventListener('click', closePicker);
  pkEls = { comb, sel: comb.querySelector('.hsel'), prev };
  picker.append(comb, el('div', { class: 'pkrow' }, prev, done));
}
function openPicker() {
  closePanel();
  if (!pkEls) buildPicker();
  picker.hidden = false;
  showPicker();
  place(picker, specBtn);
}
export function closePicker() {
  if (picker && !picker.hidden) picker.hidden = true;
}

// ---------------------------------------------------------------- build
export function initTray(o = {}) {
  if (o.onKeep) onKeep = o.onKeep;
  st = load();
  tray = document.getElementById('tray');
  const undo = document.getElementById('undoBtn'), redo = document.getElementById('redoBtn');
  colours = el('div', { class: 'colours', role: 'group', 'aria-label': 'Colours' });
  swatches = st.order.map((c) => el('button', { type: 'button', class: 'sw', 'data-colour': c, 'aria-label': NAME.get(c), title: NAME.get(c),
    style: `background:${c}`, onclick: swatchClick, onpointerdown: dragStart, onpointermove: dragMove,
    onpointerup: (e) => dragEnd(e, false), onpointercancel: (e) => dragEnd(e, true), onlostpointercapture: (e) => dragEnd(e, true) }));
  specBtn = el('button', { type: 'button', class: 'spec', 'data-spec': '', 'aria-label': 'Any colour', title: 'Any colour', onclick: tapSpec },
    el('span', { class: 'mid' }));
  colours.append(...swatches, specBtn);
  colours.addEventListener('contextmenu', (e) => e.preventDefault());   // a long press never opens a menu
  const tools = el('div', { class: 'tools' });
  for (const t of ['pen', 'highlighter', 'eraser', 'area', 'restyle', 'select']) {
    btns[t] = el('button', { type: 'button', class: 'ib tool', id: 'tool-' + t, 'data-tool': t, 'aria-label': TITLES[t], title: TITLES[t],
      html: ICONS[t], onclick: () => pickTool(t) });
    tools.append(btns[t]);
    if (t === 'highlighter') tools.append(undo);       // pw-v6c: undo straight under the highlighter, where her hand goes (27 Oct)
  }
  tray.textContent = '';
  // pw-v7e: the calculator is the FIRST thing in the tray, above the colours: at the bottom her palm kept opening it (29 Oct).
  // js/calcpanel.js wires the tap (pw-v7d)
  const toolsBtn = el('button', { type: 'button', class: 'ib tool', id: 'toolsBtn', 'data-slot': 'tools', 'aria-label': 'Calculator', title: 'Calculator', 'aria-pressed': 'false', html: CALC_ICON });
  tray.append(toolsBtn, colours, tools, el('div', { class: 'gap' }), redo);
  panel = el('div', { id: 'toolPanel', class: 'panel', hidden: true, role: 'dialog', 'aria-label': 'Tool settings' });
  picker = el('div', { id: 'specPicker', class: 'panel picker', hidden: true, role: 'dialog', 'aria-label': 'Any colour' });
  document.body.append(panel, picker);
  document.addEventListener('pointerdown', (e) => {
    if (!picker.hidden && !e.target.closest('#specPicker, #tray .spec')) closePicker();   // only its own slot keeps it open
    if (panel.hidden || e.target.closest('#toolPanel, #tray .colours')) return;   // a colour tap keeps it open
    if (e.target.closest('#tool-' + panel.dataset.for)) return;     // its own button toggles it
    closePanel();
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closePanel(); closePicker(); } });
  window.addEventListener('resize', () => { closePanel(); closePicker(); });
  push();
}
export function trayState() { return JSON.parse(JSON.stringify(st)); }
// U3c: this device's copy: is there one, and its stamp (null for a copy saved before U3c, or a test's seed)
export function localTray() {
  const v = readLocal();
  return { present: !!v, at: v && typeof v.tray_at === 'string' ? v.tray_at : null, tray: st ? kept() : null };
}
// U3c: the database's copy, newer than this device's: the same sanitising as load(), then the tray shows it and this
// device keeps it under the database's stamp (so the next start finds them equal)
export function adopt(saved, at) {
  if (!st || !saved || typeof saved !== 'object') return;
  closePanel(); closePicker();
  st = sanitise(saved);
  if (colours) {
    const byColour = new Map(swatches.map((s) => [s.dataset.colour, s]));
    swatches = st.order.map((c) => byColour.get(c)).filter(Boolean);
    colours.prepend(...swatches);                                 // the spare slot stays last
  }
  writeLocal(kept(), at);
  push();
}
// another part of the app picks a tool (a paste turns select on): the same path as a tap on its button, so it lights up
export function chooseTool(t) { if (st && st.tool !== t) pickTool(t); }
