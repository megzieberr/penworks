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
// - Dragged by its head (pen or finger). The dragged place is kept for this session only (a module variable), never saved.
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
let card = null, head = null, btn = null, mine = null, drag = null, wasLeft = false;

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
  card.append(wrap);
  document.body.append(card);
  mountCalculator(host);                                           // once: the LCD state lives in this closure
  card.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); });   // the S Pen's button
  head.addEventListener('pointermove', dragMove);
  head.addEventListener('pointerup', dragEnd);
  head.addEventListener('pointercancel', dragEnd);
  head.addEventListener('lostpointercapture', dragEnd);
}

function clamp(left, top) {
  const w = card.offsetWidth, h = card.offsetHeight;
  return [Math.max(EDGE, Math.min(innerWidth - w - EDGE, left)), Math.max(EDGE, Math.min(innerHeight - h - EDGE, top))];
}
function put(left, top) {
  const [l, t] = clamp(left, top);
  card.style.left = l + 'px'; card.style.top = t + 'px';
}
// where it goes: the dragged place if there is one this session, else beside the tray
function place() {
  if (!card || card.hidden) return;
  if (mine) { put(mine.left, mine.top); return; }
  const tray = document.getElementById('tray'), t = tray && tray.getBoundingClientRect();
  const w = card.offsetWidth, h = card.offsetHeight;
  if (!t || !t.width) { put(innerWidth - w - 80, innerHeight - h - EDGE); return; }   // no tray on screen: bottom right
  // pw-v7e: up top, by its button; Fable review: just UNDER the note bar (the More button lives there), so the bar's buttons
  // stay tappable; in full screen the bar is gone (no height) and the card sits level with the tray's top
  const bar = document.getElementById('noteBar'), b = bar && bar.getBoundingClientRect();
  const top = b && b.height > 0 ? Math.max(t.top, b.bottom + GAP) : t.top;
  put(trayLeft() ? t.right + GAP : t.left - GAP - w, top);
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
  drag = null;
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
function dragEnd(e) { if (drag && e.pointerId === drag.id) drag = null; }

export function initCalc({ trayBtn }) {
  btn = trayBtn;
  if (btn) btn.addEventListener('click', toggleCalc);
  wasLeft = trayLeft();
  // a press inside the card never reaches the page, the tray's closers or the menu's; the head still drags from here
  window.addEventListener('pointerdown', (e) => {
    if (!card || card.hidden || !card.contains(e.target)) return;
    e.stopPropagation();
    if (e.target.closest('.calcHead') && !e.target.closest('.calcClose')) dragStart(e);
  }, true);
  // the tray changed sides: the card goes beside it again (a dragged place is dropped); pw-v7c also fires `resize`
  new MutationObserver(() => {
    if (!document.body.classList.contains('noteMode')) { closeCalc(); return; }   // Fable review: leaving the note puts the calculator away (its LCD is kept)
    const now = trayLeft();
    if (now === wasLeft) return;
    wasLeft = now;
    mine = null;
    place();
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  window.addEventListener('resize', place);                        // only keeps it inside the viewport (or beside the tray)
}
