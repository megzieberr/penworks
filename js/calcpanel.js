// PenWorks pw-v7d: the Blipwork Casio fx-991ZA Plus II as a floating card beside the pen tray.
// The calculator itself (js/calc/calculator.js) is a byte-for-byte copy of Blipwork's and is never edited here; this file is
// only the card around it: where it sits, how it is dragged, and how it keeps out of the page's way.
//
// - #calcCard is built once (the first time it opens) and kept: hide = `hidden`, never rebuilt, so the LCD state survives a
//   close (the real fx-991ZA remembers its screen when you put it down).
// - It opens BESIDE THE TRAY, up top (pw-v7e; it was the bottom): 12 px under the note bar, or level with the tray's top when
//   the bar is hidden (full screen); 12 px from the tray: the tray on the right (default) puts the
//   card's right edge 12 px left of the tray; body.trayLeft (pw-v7c) puts its left edge 12 px right of the tray. The tray's
//   rectangle is read at open time. A flip of the tray side while it is open puts it beside the tray again.
// - Dragged by its head (pen or finger). pw-v7o: the dragged place is remembered on this device (localStorage pw.calc, like
//   pw.traySide: only the tablet has a tray, so it is not in the database) and comes back after a reload, clamped to the screen.
// - Its size (pw-v7o, her ask 29 Oct 17:47 "much much bigger... or at least lemme adjust it"): one scale for the whole card,
//   CSS `zoom` on .calc-wrap (the card's own box is 344 px x scale wide, css/app.css --calc-s). zoom lays the calculator out
//   again at the bigger size, so the keys stay where calculator.js put them, a tap lands on the key under it and the LCD text
//   is drawn sharp at its new size (no picture of it blown up). Default 1.6x (1.0x before), never more than fits: on open
//   beside the tray it also keeps under the note bar. The round handle at the bottom-right corner (20 px, outside the zoom so it
//   stays 20 px) drags the scale between 1.0x and 2.5x; the one she sets is remembered with the place (pw.calc) and comes back
//   next time, made smaller only while the screen is too small for it (never off-screen: below 1.0x only on a tiny screen).
// - A tap outside the card does NOT close it: she writes on the page with it open. Only the X or the tray button closes it.
// - A press inside the card must not reach the page's closers (the pen panel and the colour picker in tray.js, the menu
//   in app.js). Those listen on `document` in the CAPTURE phase, which runs before anything on the card itself, so the
//   card's stop is a capture listener on `window` (earlier still). It stops pointerdown only: the keys work on `click`.
// - The S Pen's button is a `contextmenu` on her tablet: swallowed inside the card so it never opens a menu or flips the tool.
// - Not role="dialog" on purpose: app.js overlayOpen() treats any visible [role="dialog"] as an overlay and the pen button
//   (Select <-> pen) does nothing while one is open. The calculator is a tool lying on the desk, not an overlay.
// - pw-v8v (calculator item 3, her ask 5 Nov "I actually want to be able to change the colours as well"): the face is the
//   look of her fx-991ZA, redrawn in CSS (css/app.css, every rule under #calcCard; css/calc.css is still never edited). The
//   head says fx-991ZA (the brand name went, the model stayed). Its colours are eight slots (FACE below, the CSS variables
//   --cf-*), hers to change: the palette button in the head opens a panel inside the card with a colour swatch per slot
//   (live while she picks) and one reset button back to the fx-991ZA look. What she changed is kept on this device in
//   localStorage pw.calcFace (only the changed slots; a missing one is the fx-991ZA value), read before the card first shows
//   so the old colours never flash. Like the card's place and size it is not in the database. The text on a key is not a
//   slot: it is worked out here from the key's colour (white on a dark face, near-black on a light one, whichever reads
//   better), so she can pick any colour without white text on a white key.
import { mountCalculator } from './calc/calculator.js';

const GAP = 12;          // px between the tray and the card
const EDGE = 0;          // px kept clear of the viewport edge (flush: the clamp lets it touch the edge)
const BASE_W = 344;      // the card's width at 1.0x (Blipwork's .calc-wrap max-width)
const MIN_S = 1, MAX_S = 2.5, START_S = 1.6;   // her calls: 1.0x to 2.5x, 1.6x when she has not set one
const KEY = 'pw.calc';   // { scale, left, top } on this device
let card = null, head = null, grip = null, btn = null, mine = null, drag = null, size = null, wasLeft = false;
let scale = 1, chosen = null;   // the scale on screen; the one she set with the handle (null: never set, the default applies)

// pw-v8v: the face's colour slots: [key in pw.calcFace, CSS variable, name in the panel, the look of her fx-991ZA]. The values
// must stay in step with the #calcCard defaults in css/app.css.
const FACE = [
  ['body', '--cf-body', 'Body', '#ecedef'],
  ['lcd', '--cf-lcd', 'Screen', '#cfd4cc'],
  ['lcdInk', '--cf-lcd-ink', 'Screen ink', '#1e2320'],
  ['fn', '--cf-fn', 'Keys', '#f8f8f9'],
  ['num', '--cf-num', 'Number keys', '#5b6066'],
  ['ac', '--cf-ac', 'DEL and AC', '#9ccc3c'],
  ['shift', '--cf-shift', 'SHIFT labels', '#e8a21c'],
  ['alpha', '--cf-alpha', 'ALPHA labels', '#d9484a'],
];
const INKS = [['body', '--cf-body-ink'], ['fn', '--cf-fn-ink'], ['num', '--cf-num-ink'], ['ac', '--cf-ac-ink']];   // text on these faces
const INK_LIGHT = '#ffffff', INK_DARK = '#1b1e22';
const FACE_KEY = 'pw.calcFace';  // { body, lcd, lcdInk, fn, num, ac, shift, alpha }: only the slots she changed
const RESET_TEXT = 'fx-991ZA look';
let face = {}, faceBtn = null, facePanel = null;

function load() {
  let v = null;
  try { v = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (_) { v = null; }
  if (!v || typeof v !== 'object') return;
  if (Number.isFinite(v.scale)) chosen = Math.max(MIN_S, Math.min(MAX_S, v.scale));
  if (Number.isFinite(v.left) && Number.isFinite(v.top)) mine = { left: v.left, top: v.top };
}
function save() {
  const v = {};
  if (chosen != null) v.scale = Math.round(chosen * 1000) / 1000;
  if (mine) { v.left = Math.round(mine.left); v.top = Math.round(mine.top); }
  try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (_) { /* private mode: it just is not remembered */ }
}
// ---------------------------------------------------------------- pw-v8v: the face's colours
const HEX = /^#[0-9a-f]{6}$/;
function loadFace() {
  let v = null;
  try { v = JSON.parse(localStorage.getItem(FACE_KEY) || 'null'); } catch (_) { v = null; }
  face = {};
  if (!v || typeof v !== 'object') return;
  for (const [k, , , def] of FACE) {
    const c = typeof v[k] === 'string' ? v[k].toLowerCase() : '';
    if (HEX.test(c) && c !== def) face[k] = c;
  }
}
function saveFace() {
  try {
    if (Object.keys(face).length) localStorage.setItem(FACE_KEY, JSON.stringify(face));
    else localStorage.removeItem(FACE_KEY);                        // all back to the fx-991ZA look: nothing to keep
  } catch (_) { /* private mode: it just is not remembered */ }
}
const slot = (k) => face[k] || FACE.find((f) => f[0] === k)[3];
// how light a colour is to the eye (the WCAG relative luminance), and how far apart two of those read
function lum(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [16, 8, 0].map((sh) => { const c = ((n >> sh) & 255) / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}
const contrast = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
// white or near-black, whichever reads better on this face
const inkFor = (hex) => (contrast(lum(hex), lum(INK_LIGHT)) >= contrast(lum(hex), lum(INK_DARK)) ? INK_LIGHT : INK_DARK);
function applyFace() {
  if (!card) return;
  for (const [k, prop] of FACE) {                                  // a changed slot goes on the card; the rest are the CSS defaults
    if (face[k]) card.style.setProperty(prop, face[k]); else card.style.removeProperty(prop);
  }
  for (const [k, prop] of INKS) card.style.setProperty(prop, inkFor(slot(k)));
  if (facePanel) for (const inp of facePanel.querySelectorAll('input[data-slot]')) inp.value = slot(inp.dataset.slot);
}
function setSlot(k, value) {
  const c = String(value).toLowerCase(), def = FACE.find((f) => f[0] === k)[3];
  if (!HEX.test(c)) return;
  if (c === def) delete face[k]; else face[k] = c;
  saveFace();
  applyFace();
}
function buildFacePanel() {
  facePanel = document.createElement('div');
  facePanel.className = 'calcFace';
  facePanel.hidden = true;
  facePanel.setAttribute('role', 'group');
  facePanel.setAttribute('aria-label', 'Calculator colours');
  for (const [k, , name] of FACE) {
    const row = document.createElement('label');
    row.className = 'calcFaceRow';
    const span = document.createElement('span');
    span.textContent = name;
    const inp = document.createElement('input');
    inp.type = 'color';
    inp.dataset.slot = k;
    inp.addEventListener('input', () => setSlot(k, inp.value));    // live while she picks
    inp.addEventListener('change', () => setSlot(k, inp.value));
    row.append(span, inp);
    facePanel.append(row);
  }
  const reset = document.createElement('button');
  reset.type = 'button';
  reset.className = 'calcFaceReset';
  reset.textContent = RESET_TEXT;
  reset.addEventListener('click', () => { face = {}; saveFace(); applyFace(); });
  facePanel.append(reset);
  return facePanel;
}
// the panel's height on screen while it is open (the size and fit sums leave it out: it is only open while she picks)
function panelH() {
  if (!facePanel || facePanel.hidden) return 0;
  return facePanel.getBoundingClientRect().height + 12 * scale;   // + its 12 px bottom margin, zoomed
}
function showFace(on) {
  if (!facePanel) return;
  facePanel.hidden = !on;
  faceBtn.classList.toggle('on', on);
  faceBtn.setAttribute('aria-expanded', on ? 'true' : 'false');
  if (card.hidden) return;
  if (on) { const r = card.getBoundingClientRect(); put(r.left, r.top); }   // taller now: slid up as far as needed to stay on screen
  else if (mine) put(mine.left, mine.top);                         // shut: back where she left it
  else place();
}

function setScale(s) {
  scale = s;
  card.style.setProperty('--calc-s', String(s));
}
// the card's height at 1.0x, read from what is on screen (the LCD can grow a line, so it is read each time)
const baseH = () => (card.getBoundingClientRect().height - panelH()) / scale;
// the biggest scale that fits the screen at all
const fitMax = () => Math.min((innerWidth - 2 * EDGE) / BASE_W, (innerHeight - 2 * EDGE) / baseH());
// a scale, made smaller if the rounding of the zoomed layout still leaves it a pixel too big
function fitScale(s) {
  setScale(Math.min(s, fitMax()));
  const r = card.getBoundingClientRect(), k = Math.min((innerWidth - 2 * EDGE) / r.width, (innerHeight - 2 * EDGE) / (r.height - panelH()));
  if (k < 1) setScale(scale * k);
}

const trayLeft = () => document.body.classList.contains('trayLeft');

function build() {
  card = document.createElement('div');
  card.id = 'calcCard';
  card.hidden = true;
  card.setAttribute('role', 'group');
  card.setAttribute('aria-label', 'Calculator');
  const wrap = document.createElement('div');
  wrap.className = 'calc-wrap';
  head = document.createElement('div');
  head.className = 'calc-head calcHead';
  const name = document.createElement('span');
  name.className = 'calc-name';
  name.textContent = 'fx-991ZA';                                   // pw-v8v: the model, not the brand
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'calc-close calcClose';
  close.setAttribute('aria-label', 'Close calculator');
  close.textContent = '✕';
  close.addEventListener('click', closeCalc);
  faceBtn = document.createElement('button');                      // pw-v8v: the colours of the face
  faceBtn.type = 'button';
  faceBtn.className = 'calcFaceBtn';
  faceBtn.setAttribute('aria-label', 'Calculator colours');
  faceBtn.setAttribute('aria-expanded', 'false');
  faceBtn.title = 'Colours';
  faceBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="M12 3a9 9 0 0 0 0 18c1 0 1.7-.8 1.7-1.7 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-.9.8-1.7 1.7-1.7h2A4.6 4.6 0 0 0 21 10.6C21 6.4 17 3 12 3z"/>'
    + '<circle cx="7.5" cy="11" r="1.2" fill="currentColor"/><circle cx="10" cy="7" r="1.2" fill="currentColor"/>'
    + '<circle cx="14.5" cy="7" r="1.2" fill="currentColor"/><circle cx="17.3" cy="10.5" r="1.2" fill="currentColor"/></svg>';
  faceBtn.addEventListener('click', () => showFace(facePanel.hidden));
  const btns = document.createElement('span');
  btns.className = 'calcHeadBtns';
  btns.append(faceBtn, close);
  head.append(name, btns);
  const host = document.createElement('div');
  host.className = 'calcHost';
  wrap.append(head, buildFacePanel(), host);
  grip = document.createElement('div');                            // pw-v7o: the size handle, outside the zoom
  grip.className = 'calcGrip';
  grip.title = 'Drag to make the calculator bigger or smaller';
  grip.setAttribute('aria-hidden', 'true');
  card.append(wrap, grip);
  applyFace();                                                     // pw-v8v: her colours before it is ever on screen
  document.body.append(card);
  setScale(chosen != null ? chosen : START_S);
  mountCalculator(host);                                           // once: the LCD state lives in this closure
  card.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); });   // the S Pen's button
  head.addEventListener('pointermove', dragMove);
  head.addEventListener('pointerup', dragEnd);
  head.addEventListener('pointercancel', dragEnd);
  head.addEventListener('lostpointercapture', dragEnd);
  grip.addEventListener('pointermove', sizeMove);
  grip.addEventListener('pointerup', sizeEnd);
  grip.addEventListener('pointercancel', sizeEnd);
  grip.addEventListener('lostpointercapture', sizeEnd);
}

function clamp(left, top) {
  const w = card.offsetWidth, h = card.offsetHeight;
  return [Math.max(EDGE, Math.min(innerWidth - w - EDGE, left)), Math.max(EDGE, Math.min(innerHeight - h - EDGE, top))];
}
function put(left, top) {
  const [l, t] = clamp(left, top);
  card.style.left = l + 'px'; card.style.top = t + 'px';
}
// where it goes: the dragged place if there is one (remembered on this device since pw-v7o), else beside the tray
function place() {
  if (!card || card.hidden) return;
  const want = chosen != null ? chosen : START_S;
  if (mine) { fitScale(want); put(mine.left, mine.top); return; }
  const tray = document.getElementById('tray'), t = tray && tray.getBoundingClientRect();
  if (!t || !t.width) {                                            // no tray on screen: bottom right
    fitScale(want);
    put(innerWidth - card.offsetWidth - 80, innerHeight - card.offsetHeight - EDGE);
    return;
  }
  // pw-v7e: up top, by its button; Fable review: just UNDER the note bar (the More button lives there), so the bar's buttons
  // stay tappable; in full screen the bar is gone (no height) and the card sits level with the tray's top
  const bar = document.getElementById('noteBar'), b = bar && bar.getBoundingClientRect();
  const top = b && b.height > 0 ? Math.max(t.top, b.bottom + GAP) : t.top;
  // pw-v7o: the default 1.6x also keeps under the bar (smaller if the room there is short, not below 1.0x); a size she set
  // herself is hers, kept as long as the screen holds it
  if (chosen == null) { setScale(want); fitScale(Math.min(want, Math.max(MIN_S, (innerHeight - top - EDGE) / baseH()))); }
  else fitScale(want);
  put(trayLeft() ? t.right + GAP : t.left - GAP - card.offsetWidth, top);
}

function setOn(on) {
  if (!btn) return;
  btn.classList.toggle('on', on);
  btn.setAttribute('aria-pressed', on ? 'true' : 'false');
}
export function openCalc() {
  if (!card) build();
  if (!card.hidden) return;
  card.hidden = false;
  place();
  setOn(true);
}
export function closeCalc() {
  if (card && !card.hidden) card.hidden = true;
  if (facePanel && !facePanel.hidden) showFace(false);             // pw-v8v: it opens again without the colour panel
  if (size) chosen = Math.max(MIN_S, Math.min(MAX_S, scale));
  if (drag || size) save();                                        // put away mid-drag: keep what was reached
  drag = null; size = null;
  setOn(false);
}
export function toggleCalc() { if (card && !card.hidden) closeCalc(); else openCalc(); }

// ---------------------------------------------------------------- drag by the head
function dragStart(e) {
  if (e.button !== 0 || drag) return;
  const r = card.getBoundingClientRect();
  drag = { id: e.pointerId, dx: e.clientX - r.left, dy: e.clientY - r.top };
  try { head.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  e.preventDefault();
}
function dragMove(e) {
  if (!drag || e.pointerId !== drag.id) return;
  mine = { left: e.clientX - drag.dx, top: e.clientY - drag.dy };
  put(mine.left, mine.top);
  const r = card.getBoundingClientRect();                          // keep what the clamp allowed, not what the pointer asked
  mine = { left: r.left, top: r.top };
  e.preventDefault();
}
function dragEnd(e) { if (drag && e.pointerId === drag.id) { drag = null; save(); } }

// ---------------------------------------------------------------- pw-v7o: size by the corner handle
// One scale, the calculator's proportions kept: the pointer's move is laid along the card's diagonal, so a pull straight out
// from the corner grows it by just that much. The top-left corner stays put; if the new size would reach past the screen's
// edge (or over the tray, for a card lying beside it), the card slides back in. Everything here is in screen px
// (getBoundingClientRect), the scaled size.
function sizeStart(e) {
  if (e.button !== 0 || drag || size) return;
  const r = card.getBoundingClientRect();
  // a card lying beside the tray grows away from it, never over it: her pens and colours stay in reach
  const tray = document.getElementById('tray'), t = tray && tray.getBoundingClientRect();
  let minL = EDGE, maxR = innerWidth - EDGE;
  if (t && t.width) {
    if (!trayLeft() && r.right <= t.left + 1) maxR = t.left - GAP;
    else if (trayLeft() && r.left >= t.right - 1) minL = t.right + GAP;
  }
  size = { id: e.pointerId, x0: e.clientX, y0: e.clientY, w: r.width, h: r.height, s: scale, left: r.left, top: r.top, minL, maxR };
  try { grip.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  e.preventDefault();
}
function sizeMove(e) {
  if (!size || e.pointerId !== size.id) return;
  const { w, h, s } = size, dx = e.clientX - size.x0, dy = e.clientY - size.y0;
  const k = ((w + dx) * w + (h + dy) * h) / (w * w + h * h);
  const fit = Math.min((size.maxR - size.minL) / BASE_W, (innerHeight - 2 * EDGE) / (h / s));
  fitScale(Math.max(Math.min(MIN_S, fit), Math.min(MAX_S, fit, s * k)));
  put(Math.max(size.minL, Math.min(size.maxR - card.getBoundingClientRect().width, size.left)), size.top);
  const r = card.getBoundingClientRect();
  mine = { left: r.left, top: r.top };
  e.preventDefault();
}
function sizeEnd(e) {
  if (!size || e.pointerId !== size.id) return;
  size = null;
  chosen = Math.max(MIN_S, Math.min(MAX_S, scale));   // a squeeze below 1.0x on a tiny screen is not kept as her choice
  save();
}

export function initCalc({ trayBtn }) {
  btn = trayBtn;
  if (btn) btn.addEventListener('click', toggleCalc);
  wasLeft = trayLeft();
  load();                                                          // pw-v7o: her size and place on this device
  loadFace();                                                      // pw-v8v: her colours on this device
  // a press inside the card never reaches the page, the tray's closers or the menu's; the head still drags from here, and
  // the corner handle sizes it
  window.addEventListener('pointerdown', (e) => {
    if (!card || card.hidden || !card.contains(e.target)) return;
    e.stopPropagation();
    if (e.target.closest('.calcGrip')) sizeStart(e);
    else if (e.target.closest('.calcHead') && !e.target.closest('.calcClose, .calcFaceBtn')) dragStart(e);
  }, true);
  // the tray changed sides: the card goes beside it again (a dragged place is dropped); pw-v7c also fires `resize`
  new MutationObserver(() => {
    if (!document.body.classList.contains('noteMode')) { closeCalc(); return; }   // Fable review: leaving the note puts the calculator away (its LCD is kept)
    const now = trayLeft();
    if (now === wasLeft) return;
    wasLeft = now;
    mine = null;
    save();                                                        // the size she set stays; the dragged place goes
    place();
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  window.addEventListener('resize', place);                        // only keeps it inside the viewport (or beside the tray)
}
