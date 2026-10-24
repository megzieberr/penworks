// PenWorks pen tray (right edge): the 12 colours, pen, highlighter, stroke eraser, area eraser, two
// empty slots for restyle and rectangle select (Part B), a gap, undo, redo, and an empty slot for the
// Tools button (U5). One icon per tool, no labels. The pen and the highlighter each open a small
// panel when tapped while already selected. Each remembers its own colour, width and dash or opacity.
import { setTool } from './ink.js';

// Fable's placeholder set until Megan sends her own 12: [hex, name]
export const COLOURS = [
  ['#1F2328', 'Near-black'], ['#5B6470', 'Grey'], ['#C62828', 'Red'], ['#E65100', 'Orange'],
  ['#F9A825', 'Yellow'], ['#2E7D32', 'Green'], ['#00838F', 'Teal'], ['#1565C0', 'Blue'],
  ['#283593', 'Navy'], ['#6A1B9A', 'Purple'], ['#AD1457', 'Pink'], ['#5D4037', 'Brown'],
];
const DEFAULTS = {
  pen: { colour: '#1F2328', width: 2.5, dash: 'solid' },
  highlighter: { colour: '#F9A825', width: 18, opacity: 0.4 },
};
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

let st, tray, panel, btns = {}, swatches = [];

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
  s.lastInk = s.tool;
  return s;
}
function keep() {
  try { localStorage.setItem(KEY, JSON.stringify({ tool: st.lastInk, pen: st.pen, highlighter: st.highlighter })); } catch (_) { /* ignore */ }
}
function push() {
  setTool(st.tool, INK.includes(st.tool) ? st[st.tool] : null);
  paint();
}
function paint() {
  for (const [t, b] of Object.entries(btns)) { b.classList.toggle('on', t === st.tool); b.setAttribute('aria-pressed', t === st.tool ? 'true' : 'false'); }
  const c = st[st.lastInk].colour;
  swatches.forEach((s) => s.classList.toggle('on', s.dataset.colour.toLowerCase() === String(c).toLowerCase()));
}

function pickColour(c) {
  if (!INK.includes(st.tool)) st.tool = st.lastInk;              // after an eraser, a colour hands back the last ink tool
  st[st.tool].colour = c;
  keep(); push();
}
function pickTool(t) {
  if (st.tool === t && INK.includes(t)) {
    if (!panel.hidden && panel.dataset.for === t) closePanel(); else openPanel(t);
    return;
  }
  st.tool = t;
  if (INK.includes(t)) st.lastInk = t;
  closePanel(); keep(); push();
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
  const tb = tray.getBoundingClientRect(), bb = btns[t].getBoundingClientRect();
  const ph = panel.offsetHeight;
  panel.style.right = Math.max(8, innerWidth - tb.left + 8) + 'px';
  panel.style.top = Math.max(8, Math.min(innerHeight - ph - 8, bb.top + bb.height / 2 - ph / 2)) + 'px';
}
export function closePanel() { if (panel && !panel.hidden) { panel.hidden = true; panel.textContent = ''; } }

// ---------------------------------------------------------------- build
export function initTray() {
  st = load();
  tray = document.getElementById('tray');
  const undo = document.getElementById('undoBtn'), redo = document.getElementById('redoBtn');
  const colours = el('div', { class: 'colours', role: 'group', 'aria-label': 'Colours' });
  swatches = COLOURS.map(([c, name]) => el('button', { type: 'button', class: 'sw', 'data-colour': c, 'aria-label': name, title: name,
    style: `background:${c}`, onclick: () => pickColour(c) }));
  colours.append(...swatches);
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
  document.body.append(panel);
  document.addEventListener('pointerdown', (e) => {
    if (panel.hidden || e.target.closest('#toolPanel, #tray .colours')) return;   // a colour tap keeps it open
    if (e.target.closest('#tool-' + panel.dataset.for)) return;     // its own button toggles it
    closePanel();
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePanel(); });
  window.addEventListener('resize', closePanel);
  push();
}
export function trayState() { return JSON.parse(JSON.stringify(st)); }
