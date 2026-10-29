// PenWorks pen readout: loaded only with ?dbg=1 in the address (app.js imports it behind that flag).
// A small box at the bottom-left of the desk shows the last pointer events on the desk, one per line:
// type pointerType button buttons pressure, e.g. "pointerdown pen 2 2 0.41". A move is shown only when its
// buttons changed since the last shown line, so a stroke does not flood it. It only listens: no preventDefault,
// no stopPropagation, pointer-events none, so the app behaves exactly as without it.
// A second box above it (#dbgView) shows the view every 250 ms and at every event: the desk's native scroll (must stay
// 0 0), the stack's transform, and where the stack REALLY sits on the desk against where the transform says it does
// ("drift 0" is healthy; a drift means the ink will land that far from the pen).
// Last stroke (pw-v4n): the events box gets a last line, "last: <n> pts, <len> px, <pointerType>, classify: <type or none>,
// <snapped | freehand>" (or "last: none"), read from ink.lastStroke(); a "Copy last stroke" button (#dbgCopy) above #dbgView
// puts that stroke's raw points on the clipboard as JSON (a read-only textarea #dbgText when the clipboard is refused), so a
// real pen stroke can be pasted back for the arrow fix. The button stops its own pointerdown: it never starts a stroke.
// Parabola fit (pw-v4s): a parabola's classify word carries its fit and the arc's, "classify: parabola (p 2.1 / a 6.3)"
// (lastStroke().fit, px).
// pw-v7b: #dbgView has a second line, "resize <n> | fit <n> (<last cause>) | lock on/off" (page.js viewStats()): the
// window resizes seen and the zoom resets, so the next "the page shot back" can be read off the screen. The boxes sit
// 64 px in from the left, clear of the zoom lock chip (bottom-left, 12 + 44 px).
// pw-v7i: that second line ends with "| oe <mincutoff> <beta>", the pen filter's pair (ink.OE; ?oe= in the address sets it).
import { view, deskScroll, viewStats } from './page.js';

const KEEP = 4;                                   // the last event and the three before it
const TYPES = ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'contextmenu'];
const CSS = `
#dbgView { position: absolute; left: 64px; bottom: 96px; z-index: 50; pointer-events: none; margin: 0; padding: 4px 8px;
  font: 11px/1.35 ui-monospace, Consolas, "Courier New", monospace; white-space: pre; border-radius: 6px;
  background: rgba(20,22,26,.6); color: #FFFFFF; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) #dbgView { background: rgba(255,255,255,.6); color: #14161A; } }
:root[data-theme="dark"] #dbgView { background: rgba(255,255,255,.6); color: #14161A; }
#dbgCopy { position: absolute; left: 64px; bottom: 150px; z-index: 50; pointer-events: auto; min-height: 44px; padding: 0 14px;
  font: 14px/1.2 ui-monospace, Consolas, "Courier New", monospace; border: 0; border-radius: 6px;
  background: rgba(20,22,26,.6); color: #FFFFFF; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) #dbgCopy { background: rgba(255,255,255,.6); color: #14161A; } }
:root[data-theme="dark"] #dbgCopy { background: rgba(255,255,255,.6); color: #14161A; }
#dbgText { position: absolute; left: 64px; bottom: 202px; z-index: 50; pointer-events: auto; box-sizing: border-box;
  width: calc(100% - 72px); font: 11px/1.35 ui-monospace, Consolas, "Courier New", monospace; }
#dbg { position: absolute; left: 64px; bottom: 8px; z-index: 50; pointer-events: none; margin: 0; padding: 5px 8px;
  font: 11px/1.35 ui-monospace, Consolas, "Courier New", monospace; white-space: pre; border-radius: 6px;
  background: rgba(20,22,26,.6); color: #FFFFFF; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) #dbg { background: rgba(255,255,255,.6); color: #14161A; } }
:root[data-theme="dark"] #dbg { background: rgba(255,255,255,.6); color: #14161A; }`;

export function startDbg(desk, ink) {
  if (!desk || document.getElementById('dbg')) return;
  const st = document.createElement('style'); st.id = 'dbgCss'; st.textContent = CSS; document.head.appendChild(st);
  const box = document.createElement('pre'); box.id = 'dbg';
  desk.appendChild(box);
  const vbox = document.createElement('pre'); vbox.id = 'dbgView'; desk.appendChild(vbox);
  const stack = desk.querySelector('#stack');
  const last = () => (ink && ink.lastStroke ? ink.lastStroke() : null);
  const lastLine = () => { const L = last(); return L ? `last: ${L.n} pts, ${L.len} px, ${L.pointerType}, classify: ${L.classify || 'none'}${L.fit ? ` (p ${L.fit.p.toFixed(1)} / a ${L.fit.a == null ? '-' : L.fit.a.toFixed(1)})` : ''}, ${L.snapped ? 'snapped' : 'freehand'}` : 'last: none'; };
  const btn = document.createElement('button'); btn.id = 'dbgCopy'; btn.type = 'button'; desk.appendChild(btn);
  let flash = false, flashT = 0, events = '';                  // flash: the button shows its own text for 2 s after a tap
  const paint = () => {
    const L = last();
    btn.disabled = !L;
    if (!flash) btn.textContent = L ? 'Copy last stroke' : 'No stroke yet';
    box.textContent = (events || 'dbg: waiting for the pen') + '\n' + lastLine();
  };
  const flashFor = (text) => { flash = true; btn.textContent = text; clearTimeout(flashT); flashT = setTimeout(() => { flash = false; paint(); }, 2000); };
  btn.addEventListener('pointerdown', (e) => e.stopPropagation());   // the desk never sees it: no stroke starts under the button
  btn.addEventListener('click', async () => {
    const L = last(); if (!L) return;
    const json = JSON.stringify(L);
    try {
      await navigator.clipboard.writeText(json);
      flashFor(`Copied (${L.n} pts)`);
    } catch (_) {                                              // refused or missing: she copies it by hand from the textarea
      let ta = document.getElementById('dbgText');
      if (!ta) { ta = document.createElement('textarea'); ta.id = 'dbgText'; ta.readOnly = true; ta.rows = 6; desk.appendChild(ta); ta.addEventListener('pointerdown', (e) => e.stopPropagation()); }
      ta.value = json; ta.focus(); ta.select();
      flashFor('Select + copy above');
    }
  });
  const showView = () => {
    const [st, sl] = deskScroll(), v = view(), dr = desk.getBoundingClientRect(), sr = stack.getBoundingClientRect();
    const dx = sr.left - dr.left - v.x, dy = sr.top - dr.top - v.y;
    const s = viewStats();
    vbox.textContent = `scroll ${st} ${sl} | view ${v.x.toFixed(0)} ${v.y.toFixed(0)} z${v.z.toFixed(2)} | drift ${dx.toFixed(0)} ${dy.toFixed(0)}`
      + `\nresize ${s.resizes} | fit ${s.fits} (${s.cause || 'none'}) | lock ${s.lock ? 'on' : 'off'}`
      + (ink && ink.OE ? ` | oe ${ink.OE.mincutoff} ${ink.OE.beta}` : '');
  };
  const tick = () => { showView(); paint(); };
  tick(); setInterval(tick, 250);
  const lines = [];
  let shownButtons = null;
  const num = (v) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(2)) : '-');
  const on = (e) => {
    if (e.type === 'pointermove' && e.buttons === shownButtons) return;
    shownButtons = e.buttons;
    lines.push([e.type, e.pointerType || '-', num(e.button), num(e.buttons), num(e.pressure)].join(' '));
    while (lines.length > KEEP) lines.shift();
    events = lines.slice().reverse().join('\n');   // the newest on top
    tick();
  };
  for (const t of TYPES) desk.addEventListener(t, on, { capture: true, passive: true });
  desk.addEventListener('pointerup', () => setTimeout(tick, 0), { capture: true, passive: true });   // ink stores the stroke after this runs
}
