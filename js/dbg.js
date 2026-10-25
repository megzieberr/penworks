// PenWorks pen readout: loaded only with ?dbg=1 in the address (app.js imports it behind that flag).
// A small box at the bottom-left of the desk shows the last pointer events on the desk, one per line:
// type pointerType button buttons pressure, e.g. "pointerdown pen 2 2 0.41". A move is shown only when its
// buttons changed since the last shown line, so a stroke does not flood it. It only listens: no preventDefault,
// no stopPropagation, pointer-events none, so the app behaves exactly as without it.
const KEEP = 4;                                   // the last event and the three before it
const TYPES = ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'contextmenu'];
const CSS = `
#dbg { position: absolute; left: 8px; bottom: 8px; z-index: 50; pointer-events: none; margin: 0; padding: 5px 8px;
  font: 11px/1.35 ui-monospace, Consolas, "Courier New", monospace; white-space: pre; border-radius: 6px;
  background: rgba(20,22,26,.6); color: #FFFFFF; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) #dbg { background: rgba(255,255,255,.6); color: #14161A; } }
:root[data-theme="dark"] #dbg { background: rgba(255,255,255,.6); color: #14161A; }`;

export function startDbg(desk) {
  if (!desk || document.getElementById('dbg')) return;
  const st = document.createElement('style'); st.id = 'dbgCss'; st.textContent = CSS; document.head.appendChild(st);
  const box = document.createElement('pre'); box.id = 'dbg'; box.textContent = 'dbg: waiting for the pen';
  desk.appendChild(box);
  const lines = [];
  let shownButtons = null;
  const num = (v) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(2)) : '-');
  const on = (e) => {
    if (e.type === 'pointermove' && e.buttons === shownButtons) return;
    shownButtons = e.buttons;
    lines.push([e.type, e.pointerType || '-', num(e.button), num(e.buttons), num(e.pressure)].join(' '));
    while (lines.length > KEEP) lines.shift();
    box.textContent = lines.slice().reverse().join('\n');   // the newest on top
  };
  for (const t of TYPES) desk.addEventListener(t, on, { capture: true, passive: true });
}
