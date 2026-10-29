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
import { mountCalculator } from './calc/calculator.js';

const GAP = 12;          // px between the tray and the card
const EDGE = 0;          // px kept clear of the viewport edge (flush: the clamp lets it touch the edge)
const BASE_W = 344;      // the card's width at 1.0x (Blipwork's .calc-wrap max-width)
const MIN_S = 1, MAX_S = 2.5, START_S = 1.6;   // her calls: 1.0x to 2.5x, 1.6x when she has not set one
const KEY = 'pw.calc';   // { scale, left, top } on this device
let card = null, head = null, grip = null, btn = null, mine = null, drag = null, size = null, wasLeft = false;
let scale = 1, chosen = null;   // the scale on screen; the one she set with the handle (null: never set, the default applies)

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
function setScale(s) {
  scale = s;
  card.style.setProperty('--calc-s', String(s));
}
// the card's height at 1.0x, read from what is on screen (the LCD can grow a line, so it is read each time)
const baseH = () => card.getBoundingClientRect().height / scale;
// the biggest scale that fits the screen at all
const fitMax = () => Math.min((innerWidth - 2 * EDGE) / BASE_W, (innerHeight - 2 * EDGE) / baseH());
// a scale, made smaller if the rounding of the zoomed layout still leaves it a pixel too big
function fitScale(s) {
  setScale(Math.min(s, fitMax()));
  const r = card.getBoundingClientRect(), k = Math.min((innerWidth - 2 * EDGE) / r.width, (innerHeight - 2 * EDGE) / r.height);
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
  name.textContent = 'CASIO fx-991ZA Plus II';
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'calc-close calcClose';
  close.setAttribute('aria-label', 'Close calculator');
  close.textContent = '✕';
  close.addEventListener('click', closeCalc);
  head.append(name, close);
  const host = document.createElement('div');
  host.className = 'calcHost';
  wrap.append(head, host);
  grip = document.createElement('div');                            // pw-v7o: the size handle, outside the zoom
  grip.className = 'calcGrip';
  grip.title = 'Drag to make the calculator bigger or smaller';
  grip.setAttribute('aria-hidden', 'true');
  card.append(wrap, grip);
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
  // a press inside the card never reaches the page, the tray's closers or the menu's; the head still drags from here, and
  // the corner handle sizes it
  window.addEventListener('pointerdown', (e) => {
    if (!card || card.hidden || !card.contains(e.target)) return;
    e.stopPropagation();
    if (e.target.closest('.calcGrip')) sizeStart(e);
    else if (e.target.closest('.calcHead') && !e.target.closest('.calcClose')) dragStart(e);
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
