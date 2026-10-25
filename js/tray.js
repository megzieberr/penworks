// PenWorks pen tray (right edge): her 13 colours, a spare spectrum slot, pen, highlighter, stroke eraser, area eraser, two
// empty slots for restyle and rectangle select (Part B), a gap, undo, redo, and an empty slot for the
// Tools button (U5). One icon per tool, no labels. The pen and the highlighter each open a small
// panel when tapped while already selected. Each remembers its own colour, width and dash or opacity.
// Colours: hold a swatch (350 ms, still) and drag it up or down to put her 13 in her order; the order is
// kept on the device. Under them a 14th spare slot (rainbow ring) holds any colour picked from the spectrum.
import { setTool } from './ink.js';

// Megan's own 13 (25 Oct 17:43: Sky blue out, Light green and Teal in), in her order: [hex, name].
// This stays the DEFAULT order.
export const COLOURS = [
  ['#2CB05F', 'Green'], ['#37D366', 'Light green'], ['#0D0DFF', 'Blue'], ['#FF0C84', 'Pink'], ['#FF7043', 'Orange'],
  ['#A83AFF', 'Purple'], ['#FFC107', 'Amber'], ['#00BCD5', 'Cyan'], ['#04878F', 'Teal'], ['#FF00FF', 'Magenta'],
  ['#FF3636', 'Red'], ['#000000', 'Black'], ['#808080', 'Grey'],
];
const DEFAULTS = {
  pen: { colour: '#000000', width: 2.5, dash: 'solid' },
  highlighter: { colour: '#FFC107', width: 18, opacity: 0.4 },
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
  area: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7.4 15L3.6 11.2a1.3 1.3 0 0 1 0-1.8l5.8-5.8a1.3 1.3 0 0 1 1.8 0l3.8 3.8a1.3 1.3 0 0 1 0 1.8L9.2 15z"/><path d="M6.6 6.4l5 5"/><circle cx="16.8" cy="16.8" r="4.6"/></svg>',
};
const TITLES = { pen: 'Pen', highlighter: 'Highlighter', eraser: 'Stroke eraser', area: 'Area eraser' };

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

function load() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (_) { /* defaults */ }
  const s = { tool: INK.includes(saved.tool) ? saved.tool : 'pen',
              pen: { ...DEFAULTS.pen, ...(saved.pen || {}) }, highlighter: { ...DEFAULTS.highlighter, ...(saved.highlighter || {}) } };
  // her order: used only when it is exactly her 13 hex values in some order, otherwise her default order
  const o = saved.order;
  const okOrder = Array.isArray(o) && o.length === COLOURS.length && o.every((c) => typeof c === 'string' && KNOWN.has(c.toLowerCase()))
    && new Set(o.map((c) => c.toLowerCase())).size === COLOURS.length;
  s.order = okOrder ? o.map((c) => CANON.get(c.toLowerCase())) : COLOURS.map(([c]) => c);
  s.spec = normHex(saved.spec);                                   // the spare slot: null until she first picks
  // a colour saved from an older set (not one of the 13, not the spare slot's) falls back to that tool's
  // default; width, dash, opacity stay
  for (const t of INK) {
    const c = String(s[t].colour);
    if (KNOWN.has(c.toLowerCase())) s[t].colour = CANON.get(c.toLowerCase());
    else if (s.spec && same(c, s.spec)) s[t].colour = s.spec;
    else s[t].colour = DEFAULTS[t].colour;
  }
  s.lastInk = s.tool;
  return s;
}
function keep() {
  try { localStorage.setItem(KEY, JSON.stringify({ tool: st.lastInk, pen: st.pen, highlighter: st.highlighter, order: st.order, spec: st.spec })); } catch (_) { /* ignore */ }
}
function push() {
  setTool(st.tool, INK.includes(st.tool) ? st[st.tool] : null);
  paint();
}
const specOn = () => !!st.spec && same(st[st.lastInk].colour, st.spec);
function paint() {
  for (const [t, b] of Object.entries(btns)) { b.classList.toggle('on', t === st.tool); b.setAttribute('aria-pressed', t === st.tool ? 'true' : 'false'); }
  const c = st[st.lastInk].colour;
  swatches.forEach((s) => s.classList.toggle('on', same(s.dataset.colour, c)));
  if (specBtn) {
    specBtn.dataset.colour = st.spec || '';
    specBtn.style.setProperty('--spec', st.spec || '#FFFFFF');
    specBtn.classList.toggle('on', specOn());
  }
}

function useColour(c) {
  if (!INK.includes(st.tool)) st.tool = st.lastInk;              // after an eraser, a colour hands back the last ink tool
  st[st.tool].colour = c;
  keep(); push();
}
function pickColour(c) { closePicker(); useColour(c); }
function pickTool(t) {
  closePicker();
  if (st.tool === t && INK.includes(t)) {
    if (!panel.hidden && panel.dataset.for === t) closePanel(); else openPanel(t);
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
  if (specOn() && INK.includes(st.tool)) { if (picker.hidden) openPicker(); else closePicker(); return; }
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
function place(card, by) {                                        // a card to the left of the tray, beside its button
  const tb = tray.getBoundingClientRect(), bb = by.getBoundingClientRect();
  const ph = card.offsetHeight;
  card.style.right = Math.max(8, innerWidth - tb.left + 8) + 'px';
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

// ---------------------------------------------------------------- the spectrum picker (the spare slot)
const SQ = 180;
let pk = { h: 0, s: 0, v: 1 }, pkEls = null;
function hsvToHex({ h, s, v }) {
  const f = (n) => { const k = (n + h / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
  return '#' + [f(5), f(3), f(1)].map((x) => Math.round(x * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
}
function hexToHsv(hex, keepH) {
  const n = parseInt(hex.slice(1), 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), c = mx - mn;
  let h = keepH;                                                  // a grey keeps the hue strip where it was
  if (c) h = 60 * (mx === r ? ((g - b) / c + 6) % 6 : mx === g ? (b - r) / c + 2 : (r - g) / c + 4);
  return { h, s: mx ? c / mx : 0, v: mx };
}
function showPicker() {
  const { sq, sqDot, hue, hueDot, prev, hex } = pkEls, c = hsvToHex(pk);
  sq.style.backgroundColor = `hsl(${pk.h}, 100%, 50%)`;
  sqDot.style.left = pk.s * 100 + '%'; sqDot.style.top = (1 - pk.v) * 100 + '%'; sqDot.style.backgroundColor = c;
  hueDot.style.left = pk.h / 360 * 100 + '%'; hueDot.style.backgroundColor = `hsl(${pk.h}, 100%, 50%)`;
  prev.style.backgroundColor = c;
  if (document.activeElement !== hex) hex.value = c;
  hue.setAttribute('aria-valuenow', String(Math.round(pk.h)));
}
function setSpec(c) {                                             // picking a colour also selects the slot
  st.spec = c;
  useColour(c);
}
function track(area, onPoint) {                                   // pen, finger or mouse on the square or the strip
  const at = (e) => { const r = area.getBoundingClientRect();
    onPoint(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)), Math.max(0, Math.min(1, (e.clientY - r.top) / r.height))); };
  area.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    try { area.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    at(e);
  });
  area.addEventListener('pointermove', (e) => { if (area.hasPointerCapture(e.pointerId)) at(e); });
}
function buildPicker() {
  const sqDot = el('span', { class: 'dot' }), hueDot = el('span', { class: 'dot' });
  const sq = el('div', { class: 'sq', 'aria-label': 'Saturation and lightness' }, sqDot);
  const hue = el('div', { class: 'hue', role: 'slider', 'aria-label': 'Hue', 'aria-valuemin': '0', 'aria-valuemax': '360' }, hueDot);
  const prev = el('span', { class: 'prev', 'aria-hidden': 'true' });
  const hex = el('input', { class: 'hex', type: 'text', maxlength: '7', spellcheck: 'false', autocomplete: 'off', autocapitalize: 'characters', 'aria-label': 'Hex colour' });
  const done = el('button', { type: 'button', class: 'done' }, 'Done');
  sq.style.width = sq.style.height = SQ + 'px'; hue.style.width = SQ + 'px';
  track(sq, (x, y) => { pk = { h: pk.h, s: x, v: 1 - y }; setSpec(hsvToHex(pk)); showPicker(); });
  track(hue, (x) => { pk = { ...pk, h: x * 360 }; setSpec(hsvToHex(pk)); showPicker(); });
  hex.addEventListener('input', () => { const c = normHex(hex.value); if (c) { pk = hexToHsv(c, pk.h); setSpec(c); showPicker(); } });
  hex.addEventListener('blur', () => { hex.value = hsvToHex(pk); });
  hex.addEventListener('keydown', (e) => { if (e.key === 'Enter') hex.blur(); });
  done.addEventListener('click', closePicker);
  pkEls = { sq, sqDot, hue, hueDot, prev, hex };
  picker.append(sq, hue, el('div', { class: 'pkrow' }, prev, hex, done));
}
function openPicker() {
  closePanel();
  if (!pkEls) buildPicker();
  pk = st.spec ? hexToHsv(st.spec, pk.h) : { h: pk.h, s: 0, v: 1 };
  picker.hidden = false;
  showPicker();
  place(picker, specBtn);
}
export function closePicker() {
  if (picker && !picker.hidden) { if (pkEls && document.activeElement === pkEls.hex) pkEls.hex.blur(); picker.hidden = true; }
}

// ---------------------------------------------------------------- build
export function initTray() {
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
  for (const t of ['pen', 'highlighter', 'eraser', 'area']) {
    btns[t] = el('button', { type: 'button', class: 'ib tool', id: 'tool-' + t, 'data-tool': t, 'aria-label': TITLES[t], title: TITLES[t],
      html: ICONS[t], onclick: () => pickTool(t) });
    tools.append(btns[t]);
  }
  tools.append(el('div', { class: 'slot', 'data-slot': 'restyle' }), el('div', { class: 'slot', 'data-slot': 'select' }));
  tray.textContent = '';
  tray.append(colours, tools, el('div', { class: 'gap' }), undo, redo, el('div', { class: 'slot', 'data-slot': 'tools' }));
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
  window.addEventListener('resize', () => {
    closePanel();
    // the tablet keyboard for the hex field resizes the window: keep the picker then, just move it
    if (pkEls && !picker.hidden && document.activeElement === pkEls.hex) place(picker, specBtn); else closePicker();
  });
  push();
}
export function trayState() { return JSON.parse(JSON.stringify(st)); }
