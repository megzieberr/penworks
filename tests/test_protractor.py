# PenWorks U5d checks (pw-v8d, tools round 3, first half): the PROTRACTOR on the paper (the constructions app's
# protractor, ported to the page; briefs/U5-TOOLS-DESIGN.md and _build/U5D-PROTRACTOR-BRIEF.md).
# Run: python tests/test_protractor.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800 (the tablet landscape size), the way
# tests/test_compass.py does. Pen gestures are PointerEvents (pointerType 'pen') fired on the desk; fingers are touch
# PointerEvents on the desk. The PDF is read with PyMuPDF.
# What it proves: the Protractor row is live and toggles on the current page; its - and + are greyed while it is away,
# change the radius by one step, stop at the bounds and never close the panel; the drawing (ticks, outer numbers,
# inner numbers only from 140 x K); the size is remembered (localStorage pw.proR, across a reload); the body moves it
# and the CENTRE snaps (a line's end within 16 screen px, not 17; a line's middle within 9, not 10); a turn zone turns
# it (45 degrees clicks 1 degree off, not 2; a stick point within 10 px of the baseline's line pulls the turn through
# it); the turn zone lights amber on hover; it draws nothing (no record, no undo, not in a thumb, the PDF or
# strokesOf); the last touched is on top over the ruler; a finger pans; leaving the note puts it away.
# Screenshots go to _build/shots-protractor/.
import sys, subprocess, time, pathlib, math, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8803
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-protractor"
CM = 96 / 2.54
K = CM / 32

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-01T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Tools', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
HELP = """async () => {
  window.__P = await import('./js/page.js');
  window.__TL = await import('./js/tools.js');
  const T = window.__T = {};
  T.z = () => window.__P.view().z;
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.client = (id, x, y) => { const r = T.sheet(id).getBoundingClientRect(), z = T.z(); return [r.left + x * z, r.top + y * z]; };
  T.ev = (type, id, kind, x, y, buttons) => document.getElementById('desk').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: kind,
    isPrimary: true, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0,
    buttons: buttons !== undefined ? buttons : type === 'pointerup' ? 0 : 1, clientX: x, clientY: y }));
  T.R = () => window.__TL.rulerState();
  T.P = () => window.__TL.protractorState();
  T.pl = (lx, ly) => { const s = T.P(), u = [Math.cos(s.ang), Math.sin(s.ang)], up = [u[1], -u[0]];   // protractor local (x along, y up) to page
    return [s.o[0] + u[0] * lx + up[0] * ly, s.o[1] + u[1] * lx + up[1] * ly]; };
  T.local = (lx, ly) => { const s = T.R(), u = [Math.cos(s.ang), Math.sin(s.ang)], n = [-u[1], u[0]];
    return [s.o[0] + u[0] * lx + n[0] * ly, s.o[1] + u[1] * lx + n[1] * ly]; };
  T.pen = (id, pts, up = true, pid = 31, kind = 'pen') => {
    const c = pts.map((p) => (id ? T.client(id, p[0], p[1]) : p));
    T.ev('pointerdown', pid, kind, c[0][0], c[0][1]);
    for (const q of c.slice(1)) T.ev('pointermove', pid, kind, q[0], q[1]);
    if (up) T.ev('pointerup', pid, kind, c[c.length - 1][0], c[c.length - 1][1]);
  };
  T.hover = (id, p) => { const c = T.client(id, p[0], p[1]); T.ev('pointermove', 33, 'pen', c[0], c[1], 0); };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.line = (id, x1, y1, x2, y2) => { const r = { id: crypto.randomUUID(), page_id: id, seq: Date.now() + Math.floor(Math.random() * 1000), kind: 'shape',
    style: { colour: '#FF0C84', width: 2.5, dash: 'solid', opacity: 1 }, data: { type: 'line', x1, y1, x2, y2 } };
    window.__pw.ink.put(id, [r]); return r.id; };
  T.clear = (id) => { const op = window.__pw.ink.erasePageOp(id); if (op) op.redo(); };
  T.rings = () => [...document.querySelectorAll('#stack svg.toolLayer circle.stickRing')].filter((c) => c.getAttribute('display') !== 'none')
    .map((c) => [+c.getAttribute('cx'), +c.getAttribute('cy'), +c.getAttribute('r')]);
  T.lights = () => [...document.querySelectorAll('#stack g.protractor circle.halo')].filter((c) => c.getAttribute('display') !== 'none').map((c) => c.dataset.zone);
  T.draw = () => { const g = document.querySelector('#stack g.protractor'); if (!g) return null;
    const cnt = (sel) => g.querySelectorAll(sel).length, ticks = (sel) => ((g.querySelector(sel) || {}).getAttribute ? (g.querySelector(sel).getAttribute('d').match(/M/g) || []).length : 0);
    return { outer: [...g.querySelectorAll('text.outer')].map((t) => t.textContent), inner: [...g.querySelectorAll('text.inner')].map((t) => t.textContent),
      small: ticks('path.ticks:not(.ten)'), ten: ticks('path.ticks.ten'), body: !!g.querySelector('path.body'), arc: !!g.querySelector('path.innerArc'),
      centre: cnt('circle.centre'), clip: cnt('clipPath'), lights: cnt('circle.halo'),
      fill: g.querySelector('path.body').getAttribute('fill'), stroke: g.querySelector('path.body').getAttribute('stroke'),
      outerSize: +g.querySelector('text.outer').getAttribute('font-size'), outerY0: +g.querySelector('text.outer').getAttribute('x') }; };
  return 1;
}"""
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
  return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height, shown: !e.hidden && b.width > 0 }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def rect(pg, sel): return pg.evaluate(RECT, sel)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def P(pg): return pg.evaluate("window.__T.P()")
def R(pg): return pg.evaluate("window.__T.R()")
def z(pg): return pg.evaluate("window.__T.z()")
def recs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.recs(id)", pid)
def pl(pg, lx, ly): return pg.evaluate("([a, b]) => window.__T.pl(a, b)", [lx, ly])
def local(pg, lx, ly): return pg.evaluate("([a, b]) => window.__T.local(a, b)", [lx, ly])
def pen(pg, pts, up=True, page="s0", kind="pen"): pg.evaluate("([id, p, up, k]) => window.__T.pen(id, p, up, 31, k)", [page, pts, up, kind])
def pen_up(pg, p, page="s0"):
    pg.evaluate("([id, p]) => { const c = window.__T.client(id, p[0], p[1]); window.__T.ev('pointerup', 31, 'pen', c[0], c[1]); }", [page, p])
def hover(pg, p, page="s0"): pg.evaluate("([id, p]) => window.__T.hover(id, p)", [page, p])
def rotate(p, c, deg):
    a = math.radians(deg); dx, dy = p[0] - c[0], p[1] - c[1]
    return [c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a)]
def turn_path(c, k, deg, steps=None):
    steps = steps or max(2, int(abs(deg) / 2.5))
    return [rotate(k, c, deg * i / steps) for i in range(steps + 1)]
def addv(a, b): return [a[0] + b[0], a[1] + b[1]]
def subv(a, b): return [a[0] - b[0], a[1] - b[1]]
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def near(a, b, tol=1e-6): return a is not None and b is not None and dist(a, b) <= tol
def open_panel(pg):
    if pg.locator("#toolsPanel").is_hidden(): pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
def toggle(pg, tool):
    open_panel(pg); pg.click(f"#trow-{tool}"); pg.wait_for_timeout(60)
def close_panel(pg): pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
def finger(pg, kind, pid, x, y):
    pg.evaluate("([t, i, x, y]) => window.__T.ev(t, i, 'touch', x, y)", [kind, pid, x, y])
def pressed(pg, sel): return pg.get_attribute(sel, "aria-pressed")
def cl(pg, p, page="s0"): return pg.evaluate("([id, x, y]) => window.__T.client(id, x, y)", [page, p[0], p[1]])
def sizes(pg): return pg.evaluate("[document.getElementById('pro-minus').disabled, document.getElementById('pro-plus').disabled]")
def draw(pg): return pg.evaluate("window.__T.draw()")
def show(pg, p, page="s0"):
    """scroll the stack (a plain wheel) so page point p sits in the middle of the desk (the screenshots need it on screen)"""
    pg.evaluate("""([id, p]) => { const c = window.__T.client(id, p[0], p[1]);
      const d = document.getElementById('desk'), b = d.getBoundingClientRect();
      d.dispatchEvent(new WheelEvent('wheel', { deltaY: c[1] - (b.top + b.height / 2), clientX: b.left + 200, clientY: b.top + 200, bubbles: true, cancelable: true })); }""", [page, p])
    pg.wait_for_timeout(80)
def zoom_to(pg, target):
    pg.evaluate("""(t) => { const d = document.getElementById('desk'), b = d.getBoundingClientRect();
      d.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: Math.log(window.__T.z() / t) / 0.0025, clientX: b.left + 400, clientY: b.top + 300, bubbles: true, cancelable: true })); }""", target)
    pg.wait_for_timeout(80)
def body_pt(pg): return pl(pg, 0, P(pg)["r"] * 0.5)                # the body, straight above the centre (the move zone)
def turn_pt(pg): return pl(pg, P(pg)["r"] * 0.85, P(pg)["r"] * 0.1)   # inside the right end's turn zone
def move_centre(pg, target, up=True):                                # a pen drag on the body that would put the centre on target
    s = body_pt(pg); o = P(pg)["o"]; e = addv(s, subv(target, o))
    pen(pg, [s, addv(s, [(e[0] - s[0]) / 2, (e[1] - s[1]) / 2]), e], up)
def resize_to(pg, units):                                            # click - or + until the radius is units x K
    for _ in range(20):
        r = round(P(pg)["r"] / K)
        if r == units: return
        pg.click("#pro-plus" if r < units else "#pro-minus"); pg.wait_for_timeout(20)

def fresh_size(pg, units):                                           # a clamped size never steps back onto 170 (340 - 20 n): set it and reload
    pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
    pg.evaluate("(v) => localStorage.setItem('pw.proR', String(v))", units * K)
    pg.reload(); ready(pg); open_note(pg); pg.evaluate(HELP)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        open_note(pg); pg.evaluate(HELP)

        # ------------------------------------------------------------ A: the panel row and its - and +
        group[0] = "A. panel"
        open_panel(pg)
        rows = pg.evaluate("[...document.querySelectorAll('#toolsPanel .trow')].map((b) => [b.textContent.trim(), b.disabled, b.title, b.getAttribute('aria-pressed')])")
        check("still four rows in order (Ruler, Compass, Protractor, Axes); the Protractor row is live, unpressed; Axes stays 'Next round'",
              [r[0] for r in rows] == ["Ruler", "Compass", "Protractor", "Axes"] and rows[2][1] is False and rows[2][2] == "" and rows[2][3] == "false"
              and rows[3][1] is True and rows[3][2] == "Next round", rows)
        sb = pg.evaluate("""() => { const row = document.getElementById('trow-protractor'), line = row.parentElement;
          return { line: line.className, kids: [...line.children].map((e) => e.id), aria: [...line.querySelectorAll('.tsz')].map((e) => [e.textContent, e.getAttribute('aria-label')]),
                   inRow: !!row.querySelector('.tsz'), right: [...line.querySelectorAll('.tsz')].every((e) => e.getBoundingClientRect().left > row.getBoundingClientRect().right - 1) }; }""")
        check("the row's right end carries - and + (beside the toggle, not inside it), labelled 'Smaller protractor' / 'Bigger protractor'",
              sb["kids"] == ["trow-protractor", "pro-minus", "pro-plus"] and sb["aria"] == [["−", "Smaller protractor"], ["+", "Bigger protractor"]]
              and not sb["inRow"] and sb["right"], sb)
        check("- and + are greyed (disabled) while the protractor is away", sizes(pg) == [True, True], sizes(pg))
        pg.click("#pro-plus", force=True); pg.wait_for_timeout(40)
        check("a tap on the greyed + brings nothing out and keeps the panel open", P(pg) is None and pg.locator("#toolsPanel").is_visible())
        pg.click("#trow-protractor"); pg.wait_for_timeout(60)
        p0 = P(pg)
        check("the row brings the protractor out on the current page (page 1), the row and the Tools button pressed, the panel stays open",
              p0 is not None and p0["page"] == "s0" and pressed(pg, "#trow-protractor") == "true" and pressed(pg, "#drawToolsBtn") == "true"
              and pg.locator("#toolsPanel").is_visible(), p0)
        check("- and + are live while it is out (at the default size)", sizes(pg) == [False, False], sizes(pg))
        pg.click("#pro-plus"); pg.wait_for_timeout(40); p1 = P(pg)
        check("+ grows the radius by one step (20 x K), the centre and the angle kept",
              abs(p1["r"] - p0["r"] - 20 * K) < 1e-9 and p1["o"] == p0["o"] and p1["ang"] == p0["ang"], [p0["r"], p1["r"]])
        check("... and does not close the panel or toggle the tool", pg.locator("#toolsPanel").is_visible() and pressed(pg, "#trow-protractor") == "true" and P(pg) is not None)
        pg.click("#pro-minus"); pg.click("#pro-minus"); pg.wait_for_timeout(40); p2 = P(pg)
        check("- shrinks it a step at a time (two taps: one step under the default)", abs(p2["r"] - (170 - 20) * K) < 1e-9 and pg.locator("#toolsPanel").is_visible(), p2["r"] / K)
        n = 0
        while not sizes(pg)[0] and n < 20: pg.click("#pro-minus"); pg.wait_for_timeout(15); n += 1
        check("at the smallest (100 x K) - is greyed, + live; it took 3 taps from 150 (130, 110, then clamped to 100)",
              abs(P(pg)["r"] - 100 * K) < 1e-9 and sizes(pg) == [True, False] and n == 3, [P(pg)["r"] / K, n, sizes(pg)])
        pg.click("#pro-minus", force=True); pg.wait_for_timeout(30)
        check("a tap on the greyed - changes nothing", abs(P(pg)["r"] - 100 * K) < 1e-9)
        dw = draw(pg)
        check("below 140 x K: the inner number row is gone, the outer row stays (19 numbers)", dw["inner"] == [] and len(dw["outer"]) == 19, dw)
        pg.click("#pro-plus"); pg.wait_for_timeout(20)
        check("at 120 x K still no inner numbers", draw(pg)["inner"] == [] and abs(P(pg)["r"] - 120 * K) < 1e-9, P(pg)["r"] / K)
        pg.click("#pro-plus"); pg.wait_for_timeout(20)
        check("at 140 x K the inner numbers come back (0 up to 180)", draw(pg)["inner"] == [str(d) for d in range(0, 181, 10)] and abs(P(pg)["r"] - 140 * K) < 1e-9, draw(pg)["inner"])
        n = 0
        while not sizes(pg)[1] and n < 20: pg.click("#pro-plus"); pg.wait_for_timeout(15); n += 1
        check("at the biggest (340 x K) + is greyed, - live (10 taps from 140: 160 ... 320, then clamped to 340)",
              abs(P(pg)["r"] - 340 * K) < 1e-9 and sizes(pg) == [False, True] and n == 10, [P(pg)["r"] / K, n])
        check("the panel stayed open through all of it, the protractor out, its centre where it came out",
              pg.locator("#toolsPanel").is_visible() and P(pg)["o"] == p0["o"])
        pg.click("#trow-protractor"); pg.wait_for_timeout(60)
        check("a second tap on the row puts it away (no layer), - and + greyed, nothing pressed",
              P(pg) is None and pg.locator("#stack svg.toolLayer").count() == 0 and sizes(pg) == [True, True]
              and pressed(pg, "#trow-protractor") == "false" and pressed(pg, "#drawToolsBtn") == "false")
        close_panel(pg)
        fresh_size(pg, 170)

        # ------------------------------------------------------------ B: out on the paper
        group[0] = "B. protractor out"
        th_empty = pg.evaluate("() => window.__pw.ink.thumbSvg('s0').querySelectorAll('*').length")
        toggle(pg, "protractor"); close_panel(pg)
        p = P(pg)
        check("default radius 170 x CM/32 (about 5.3 cm), range 100 .. 340 x CM/32, step 20 x CM/32",
              abs(p["r"] - 170 * K) < 1e-9 and abs(p["def"] - 170 * K) < 1e-9 and abs(p["min"] - 100 * K) < 1e-9 and abs(p["max"] - 340 * K) < 1e-9
              and abs(p["step"] - 20 * K) < 1e-9 and abs(p["r"] / CM - 5.3125) < 1e-9, p)
        check("centred at (0.62, 0.62) of the current page, level", abs(p["o"][0] - 794 * 0.62) < 1e-9 and abs(p["o"][1] - 1123 * 0.62) < 1e-9 and p["ang"] == 0, p["o"])
        lay = pg.evaluate("""() => { const s = window.__T.sheet('s0'), l = s.querySelector(':scope > svg.toolLayer'), ink = s.querySelector(':scope > svg.ink');
          if (!l) return null; const g = l.querySelector('g.protractor');
          return { after: !!ink && !!(ink.compareDocumentPosition(l) & 4), view: l.getAttribute('viewBox'), g: !!g, tf: g && g.getAttribute('transform') }; }""")
        check("a g.protractor in page 1's tool layer, over the ink, page px viewBox, placed by its transform",
              lay and lay["after"] and lay["view"] == "0 0 794 1123" and lay["g"] and lay["tf"].startswith("translate(492.28 696.26) rotate(0)"), lay)
        dw = draw(pg)
        check("drawPro's parts: the body (fixed colours, not the ink's), the inner arc, the centre ring, the clip for the zone light",
              dw["body"] and dw["arc"] and dw["centre"] == 1 and dw["clip"] == 1 and dw["fill"] == "rgba(158,196,240,.32)" and dw["stroke"] == "rgba(59,111,182,.95)", dw)
        check("a tick every degree: 19 ten-degree ticks and 162 others", dw["ten"] == 19 and dw["small"] == 162, [dw["ten"], dw["small"]])
        check("the outer numbers run 180 down to 0 (10 x K, the right end first), the inner 0 up to 180 at the default size",
              dw["outer"] == [str(180 - d) for d in range(0, 181, 10)] and dw["inner"] == [str(d) for d in range(0, 181, 10)]
              and abs(dw["outerSize"] - 10 * K) < 1e-3 and abs(dw["outerY0"] - (p["r"] - 24 * K)) < 1e-3, dw)
        check("two zone lights, none lit at rest", dw["lights"] == 2 and pg.evaluate("window.__T.lights()") == [], dw)
        check("the protractor is not a record: strokesOf(page 1) is empty", recs(pg) == [])
        th = pg.evaluate("() => { const s = window.__pw.ink.thumbSvg('s0'); return [s.querySelectorAll('*').length, s.querySelectorAll('.protractor, text, clipPath').length]; }")
        check("... and not in the page's thumb", th == [th_empty, 0], [th, th_empty])
        z1 = z(pg); w1 = rect(pg, "#stack svg.toolLayer g.protractor")
        zoom_to(pg, z1 * 2); z2 = z(pg); w2 = rect(pg, "#stack svg.toolLayer g.protractor"); p2 = P(pg)
        check("a zoom to 2x doubles its screen box, its page px unchanged (a paper size, not a screen size)",
              abs(z2 / z1 - 2) < 1e-6 and abs(w2["w"] / w1["w"] - 2) < 0.01 and abs(w2["h"] / w1["h"] - 2) < 0.01 and p2["o"] == p["o"] and p2["r"] == p["r"], [z1, z2, w1, w2])
        zoom_to(pg, z1)
        check("zoomed back to 1x", abs(z(pg) - 1) < 1e-6, z(pg))
        pg.evaluate("window.__P.scrollToPage(1)"); pg.wait_for_timeout(80)
        toggle(pg, "protractor"); toggle(pg, "protractor")
        check("put away and brought out while page 2 is current, it comes out fresh on page 2",
              P(pg)["page"] == "s1" and P(pg)["o"] == p["o"] and pg.evaluate("!!window.__T.sheet('s1').querySelector(':scope > svg.toolLayer g.protractor')"))
        pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)
        check("scrolled back to page 1, it stays on page 2", pg.evaluate("window.__P.current()") == 0 and P(pg)["page"] == "s1")
        toggle(pg, "protractor"); toggle(pg, "protractor"); pg.click("#pro-plus"); pg.wait_for_timeout(30)
        p190 = P(pg)
        toggle(pg, "protractor"); toggle(pg, "protractor"); p3 = P(pg)
        check("away and out again: on page 1, fresh at its spot, at the LAST size used (190 x K), remembered as page px",
              p3["page"] == "s0" and p3["o"] == p["o"] and abs(p3["r"] - 190 * K) < 1e-9 and abs(p3["saved"] - 190 * K) < 1e-9
              and abs(float(pg.evaluate("localStorage.getItem('pw.proR')")) - 190 * K) < 1e-9, [p190, p3])
        resize_to(pg, 170); close_panel(pg)

        # ------------------------------------------------------------ C: the move zone and the centre's snap
        group[0] = "C. move + snap"
        pg.evaluate("window.__T.clear('s0')")
        check("zoom 1 for the reach checks", abs(z(pg) - 1) < 1e-6, z(pg))
        o0 = P(pg)["o"]; pen(pg, [body_pt(pg), addv(body_pt(pg), [-30, 20]), addv(body_pt(pg), [-60, 40])])
        p = P(pg)
        check("a pen drag on the body carries it by the offset from its centre (60 left, 40 down), level, same size",
              near(p["o"], [o0[0] - 60, o0[1] + 40]) and p["ang"] == 0 and abs(p["r"] - 170 * K) < 1e-9 and p["stuck"] is None, p)
        pg.evaluate("window.__T.line('s0', 200, 300, 500, 300)"); pg.wait_for_timeout(30)
        undo0 = pg.evaluate("document.getElementById('undoBtn').disabled")
        end = [200, 300]
        move_centre(pg, addv(end, [-11, 11])); p = P(pg)          # 15.56 px from the end
        check("the centre snaps onto a line's END within 16 screen px (15.6 away)", near(p["o"], end) and near(p["stuck"], end), p)
        rg = pg.evaluate("window.__T.rings()")
        check("... and a ring marks it while it sits there (the needle's ring: 7 px)", any(abs(r[0] - 200) < 1e-3 and abs(r[1] - 300) < 1e-3 and abs(r[2] - 7) < 1e-3 for r in rg), rg)
        tgt = addv(end, [-12.03, 12.03])                            # 17.01 px from the end, past the line's own end
        move_centre(pg, tgt); p = P(pg)
        check("... but not at 17 (it lands where the pen put it, no ring)", near(p["o"], tgt, 1e-6) and p["stuck"] is None and pg.evaluate("window.__T.rings()") == [], p)
        move_centre(pg, [350, 308.5]); p = P(pg)
        check("onto a line's MIDDLE within 9 screen px (8.5 below it): the centre lands on the line", near(p["o"], [350, 300]) and near(p["stuck"], [350, 300]), p)
        move_centre(pg, [350, 310]); p = P(pg)
        check("... but not at 10", near(p["o"], [350, 310], 1e-6) and p["stuck"] is None, p)
        move_centre(pg, [280, 304], up=False); mid = P(pg)
        check("mid-drag the centre already sits on the line, ringed", mid["gesture"] == "pMove" and near(mid["o"], [280, 300]) and len(pg.evaluate("window.__T.rings()")) == 1, mid)
        pen_up(pg, body_pt(pg))
        check("no stroke record from any of it (only the seeded line), the undo button as it was",
              len(recs(pg)) == 1 and pg.evaluate("document.getElementById('undoBtn').disabled") == undo0, [len(recs(pg)), undo0])
        # the screenshot: at the default size over a line, the centre snapped on it
        pg.evaluate("window.__T.clear('s0')"); pg.evaluate("window.__T.line('s0', 160, 560, 640, 560)")
        move_centre(pg, [400, 564]); p = P(pg)
        check("over a fresh line: the centre snaps onto it (for the picture)", near(p["o"], [400, 560]) and p["stuck"] is not None, p)
        show(pg, [400, 470]); pg.screenshot(path=str(SHOTS / "u5d-protractor.png"))

        # ------------------------------------------------------------ D: the turn zones
        group[0] = "D. turn"
        pg.evaluate("window.__T.clear('s0')")
        toggle(pg, "protractor"); toggle(pg, "protractor"); close_panel(pg)
        p = P(pg); c = p["o"]
        hover(pg, turn_pt(pg))
        check("a pen hovering over the right end's turn zone lights it amber (one light)", pg.evaluate("window.__T.lights()") == ["turnR"], pg.evaluate("window.__T.lights()"))
        hover(pg, pl(pg, -p["r"] * 0.85, p["r"] * 0.1))
        check("... the left end's lights the other", pg.evaluate("window.__T.lights()") == ["turnL"], pg.evaluate("window.__T.lights()"))
        hover(pg, body_pt(pg))
        check("... over the body (the move zone) none is lit", pg.evaluate("window.__T.lights()") == [], pg.evaluate("window.__T.lights()"))
        hover(pg, [40, 40])
        path = turn_path(c, turn_pt(pg), -20)
        pen(pg, path, up=False); mid = P(pg)
        check("a press in a turn zone turns it about its centre (20 degrees), the zone lit while held",
              mid["gesture"] == "pTurn" and abs(math.degrees(mid["ang"]) + 20) < 0.05 and mid["o"] == c and pg.evaluate("window.__T.lights()") == ["turnR"], [math.degrees(mid["ang"]), mid])
        pen_up(pg, path[-1])
        pen(pg, turn_path(c, turn_pt(pg), 20))
        check("... and back to level", abs(P(pg)["ang"]) < 1e-9, math.degrees(P(pg)["ang"]))
        pen(pg, turn_path(c, turn_pt(pg), -44))
        check("a turn 1 degree off 45 clicks onto 45", abs(P(pg)["ang"] + math.pi / 4) < 1e-9, math.degrees(P(pg)["ang"]))
        pen(pg, turn_path(c, turn_pt(pg), 45))
        check("... back to level", abs(P(pg)["ang"]) < 1e-9, math.degrees(P(pg)["ang"]))
        pen(pg, turn_path(c, turn_pt(pg), -43))
        check("a turn 2 degrees off 45 stays free (43)", abs(math.degrees(P(pg)["ang"]) + 43) < 0.05, math.degrees(P(pg)["ang"]))
        pen(pg, turn_path(c, pl(pg, -P(pg)["r"] * 0.85, P(pg)["r"] * 0.1), 43))
        check("the left end turns it too (back to level)", abs(P(pg)["ang"]) < 1e-6, math.degrees(P(pg)["ang"]))
        # a stick point near the baseline's line pulls the turn through it (the line's end Q, 250 px out at -30 degrees)
        a30 = math.radians(-30)
        Q = [c[0] + 250 * math.cos(a30), c[1] + 250 * math.sin(a30)]; Q2 = [c[0] + 330 * math.cos(a30), c[1] + 330 * math.sin(a30)]
        pg.evaluate("([a, b]) => window.__T.line('s0', a[0], a[1], b[0], b[1])", [Q, Q2])
        off_in = math.degrees(math.asin(9.5 / 250)); off_out = math.degrees(math.asin(10.5 / 250))
        path = turn_path(c, turn_pt(pg), -30 + off_in)
        pen(pg, path, up=False); mid = P(pg)
        check("turned until the baseline's line is 9.5 px from a line's end: the turn is pulled through it (exactly -30)",
              abs(math.degrees(mid["ang"]) + 30) < 1e-6 and near(mid["target"], Q, 1e-6), [math.degrees(mid["ang"]), mid["target"], Q])
        rg = pg.evaluate("window.__T.rings()")
        check("... a ring marks the point while it pulls", any(abs(r[0] - Q[0]) < 1e-3 and abs(r[1] - Q[1]) < 1e-3 for r in rg), rg)
        pen_up(pg, path[-1])
        check("... and it stays there on the lift, its centre unmoved", abs(math.degrees(P(pg)["ang"]) + 30) < 1e-6 and P(pg)["o"] == c, math.degrees(P(pg)["ang"]))
        pen(pg, turn_path(c, turn_pt(pg), 30))
        pen(pg, turn_path(c, turn_pt(pg), -30 + off_out)); p = P(pg)
        check("at 10.5 px it stays free (no pull)", abs(math.degrees(p["ang"]) - (-30 + off_out)) < 0.01, math.degrees(p["ang"]))
        check("the turns added no records (only the line)", len(recs(pg)) == 1)
        pg.evaluate("window.__T.clear('s0')")

        # ------------------------------------------------------------ E: the strip and the zoomed-out reach
        group[0] = "E. reach"
        toggle(pg, "protractor"); toggle(pg, "protractor"); close_panel(pg)
        p = P(pg); s0 = pl(pg, 0, -14 * K + 1)                       # inside the strip under the baseline
        pen(pg, [s0, addv(s0, [0, 30])])
        check("a press on the strip under the baseline (14 x K) moves it", near(P(pg)["o"], addv(p["o"], [0, 30])), P(pg)["o"])
        toggle(pg, "protractor"); toggle(pg, "protractor"); close_panel(pg)
        p = P(pg); s1 = pl(pg, 0, -14 * K - 3)
        pen(pg, [s1, addv(s1, [0, 30])])
        check("3 px below the strip, at zoom 1, the pen draws instead (the protractor stays)", P(pg)["o"] == p["o"] and len(recs(pg)) == 1, [P(pg)["o"], len(recs(pg))])
        pg.evaluate("window.__T.clear('s0')")
        zoom_to(pg, 0.5); show(pg, p["o"])
        pen(pg, [s1, addv(s1, [0, 30])])
        check("zoomed out to 0.5 the strip keeps its size on screen: the same press now moves it", abs(z(pg) - 0.5) < 1e-6 and near(P(pg)["o"], addv(p["o"], [0, 30])) and recs(pg) == [],
              [z(pg), P(pg)["o"], len(recs(pg))])
        zoom_to(pg, 1); pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)

        # ------------------------------------------------------------ F: it draws nothing
        group[0] = "F. records, thumb, PDF"
        pg.evaluate("window.__T.clear('s0')")
        toggle(pg, "protractor"); toggle(pg, "protractor"); close_panel(pg)
        move_centre(pg, [400, 500]); pen(pg, turn_path(P(pg)["o"], turn_pt(pg), -60))
        check("after a move and a turn: strokesOf(page 1) is empty, no live shape in the ink layer, the protractor still out",
              recs(pg) == [] and pg.evaluate("window.__T.sheet('s0').querySelectorAll('svg.ink g.pen > *').length") == 0 and P(pg) is not None)
        th = pg.evaluate("() => { const s = window.__pw.ink.thumbSvg('s0'); return [s.querySelectorAll('*').length, s.querySelectorAll('.protractor, text, clipPath, .toolLayer').length]; }")
        check("not in the page's thumb", th == [th_empty, 0], th)
        pdf64 = pg.evaluate("""async () => { const m = await import('./js/pdfout.js');
          const blob = await m.buildPdf([{ id: 's0', orientation: 'portrait', background: 'blank', pdf_path: null }], 'Protractor');
          const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode(...b.subarray(i, i + 8192));
          return btoa(s); }""")
        doc = fitz.open(stream=base64.b64decode(pdf64), filetype="pdf")
        drs = doc[0].get_drawings(); txt = doc[0].get_text().strip()
        check("Share as PDF (buildPdf): get_drawings() finds nothing (no half disc, no ticks) and no numbers", drs == [] and txt == "", [len(drs), txt[:80]])
        doc.close()

        # ------------------------------------------------------------ G: with the ruler, one press
        group[0] = "G. overlap"
        toggle(pg, "protractor"); toggle(pg, "ruler"); toggle(pg, "protractor"); close_panel(pg)
        r0 = R(pg)
        check("the protractor came out last: it is on top", P(pg)["order"] == ["ruler", "protractor"], P(pg)["order"])
        tgt = [397, r0["o"][1] + r0["w"] * 0.6]                       # the centre down onto the ruler's body
        move_centre(pg, tgt); p = P(pg)
        over = pl(pg, 0, 12)                                          # inside the half disc, over the ruler (y between its edges' bands)
        ry = over[1] - r0["o"][1]
        check("its half disc now lies over the ruler (the press point is in the ruler's move band)", near(p["o"], tgt) and 16 < ry < r0["w"] - 16 and R(pg)["o"] == r0["o"], [p["o"], ry])
        pen(pg, [over, addv(over, [30, 0])]); p1 = P(pg)
        check("a press where both lie goes to the protractor (on top): it moves, the ruler stays",
              near(p1["o"], addv(tgt, [30, 0])) and R(pg)["o"] == r0["o"], [p1["o"], R(pg)["o"]])
        far = local(pg, 30, r0["w"] / 2)
        pen(pg, [far, addv(far, [0, 1])]); r3 = R(pg)
        check("touching the ruler clear of it puts the ruler on top", P(pg)["order"] == ["protractor", "ruler"], P(pg)["order"])
        over = pl(pg, 0, 12)
        pen(pg, [over, addv(over, [-25, 0])]); r4 = R(pg)
        check("now the same overlap goes to the ruler (it moves, the protractor stays)", abs(r4["o"][0] - r3["o"][0] + 25) < 1e-6 and P(pg)["o"] == p1["o"], [r3["o"], r4["o"]])
        lay = pg.evaluate("[...window.__T.sheet('s0').querySelector(':scope > svg.toolLayer').children].filter((e) => e.tagName === 'g').map((e) => e.getAttribute('class'))")
        check("the layer draws them in that order (the ruler over the protractor)", lay == ["protractor", "ruler"], lay)
        check("no records from any of it", recs(pg) == [])
        toggle(pg, "ruler"); close_panel(pg)

        # ------------------------------------------------------------ H: fingers are never the protractor's
        group[0] = "H. fingers"
        pg.wait_for_timeout(700)                                   # page.js ignores a finger for 600 ms after the pen (palm)
        p0 = P(pg); v0 = pg.evaluate("window.__P.view()")
        cpt = cl(pg, pl(pg, 0, p0["r"] * 0.5))
        finger(pg, "pointerdown", 71, cpt[0], cpt[1])
        for k in range(1, 7): finger(pg, "pointermove", 71, cpt[0], cpt[1] - 15 * k); pg.wait_for_timeout(16)
        finger(pg, "pointerup", 71, cpt[0], cpt[1] - 90); pg.wait_for_timeout(120)
        v1 = pg.evaluate("window.__P.view()"); p1 = P(pg)
        check("a finger drag starting on the protractor pans the page", v1["y"] < v0["y"] - 50, [v0, v1])
        check("... and the protractor stays where it was on the paper, no records", p1["o"] == p0["o"] and p1["ang"] == p0["ang"] and recs(pg) == [], [p0, p1])
        pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)

        # ------------------------------------------------------------ I: closing the note, and tomorrow
        group[0] = "I. close + reload"
        open_panel(pg); pg.click("#pro-plus"); pg.wait_for_timeout(30)
        check("one step bigger before closing (190 x K)", abs(P(pg)["r"] - 190 * K) < 1e-9, P(pg)["r"] / K)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        check("closing the note puts it away (no layer), the panel closes, the button unpressed",
              P(pg) is None and pg.locator("svg.toolLayer").count() == 0 and pg.locator("#toolsPanel").is_hidden() and pressed(pg, "#drawToolsBtn") == "false")
        pg.reload(); ready(pg); open_note(pg); pg.evaluate(HELP)
        check("reloaded: nothing out", P(pg) is None and pg.locator("svg.toolLayer").count() == 0)
        toggle(pg, "protractor")
        check("brought out after the reload it has the size of yesterday (190 x K, from localStorage pw.proR)",
              P(pg) is not None and abs(P(pg)["r"] - 190 * K) < 1e-9 and sizes(pg) == [False, False], P(pg))
        resize_to(pg, 170); toggle(pg, "protractor"); close_panel(pg)
        check("no page errors", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g_, n, ok, info in res:
    if g_ not in groups: groups.append(g_)
    if not ok: print(f"FAIL [{g_}] {n}  -> {str(info)[:500]}")
print()
for g_ in groups:
    rs_ = [r for r in res if r[0] == g_]
    print(f"{g_}: {sum(r[2] for r in rs_)}/{len(rs_)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
