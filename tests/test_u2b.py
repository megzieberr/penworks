# PenWorks U2 B checks (shapes and selection): headless Playwright (Python), same style as tests/test_u2a.py.
# Run: python tests/test_u2b.py               (local mode only: ?local=1, Supabase is never touched)
#      add --shots <folder> for small screenshots
# Every group seeds its own folder > notes > pages into the localStorage twin, draws with the mouse, and reads
# the stroke records and the SVG layers: hold-to-snap, grabbable handles, restyle, rectangle select, erasers.
# U2 B fix round (pw-v4a): real pen events on a handle (20 px reach), touch-any-part select, highlighter snap,
# restyle's own colour, colour tap and Restyle tap on a selection.
# Pen button round (pw-v4b): the plain pen always draws; a handle is grabbed only with the S Pen's side button
# (buttons & 2) or the right mouse button; the ?dbg=1 pointer readout.
# Pen button 2 round (pw-v4c): her tablet sends the button only as one contextmenu per press, so a press near a
# handle picks it up, the pen's moves carry it, a touch and lift (or a second press, a tool change, Escape, undo) drops it.
# Desk scroll fix (pw-v4d): #desk is overflow: clip, never a scroll container (her tablet: ink landed a fixed distance
# above the pen after a button press / long hold until a reopen); the proof test lives in tests/test_scroll.py.
import sys, subprocess, time, pathlib, re, json, math
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8779
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None

res = []
group = ["?"]
info_lines = []
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-25T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U2B', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Snap', '2026-10-25T10:06:00Z'), N('n2', 'Handles', '2026-10-25T10:05:00Z'), N('n3', 'Restyle', '2026-10-25T10:04:00Z'),
            N('n4', 'Select', '2026-10-25T10:03:00Z'), N('n5', 'Erase', '2026-10-25T10:02:00Z')],
    pages: [P('p1', 'n1', 0), P('p2', 'n2', 0), P('p3', 'n3', 0), P('p4', 'n4', 0), P('p4b', 'n4', 1), P('p5', 'n5', 0)] }));
}"""
STROKES_JS = "(id) => window.__pw.ink.strokesOf(id)"
STORED_JS = "(id) => JSON.parse(localStorage.getItem('pw.strokes.' + id) || 'null')"
EL_JS = """([i, id]) => { const e = document.querySelector(`#stack .sheet[data-index="${i}"] svg.ink [data-id="${id}"]`);
  if (!e) return null;
  const a = (k) => e.getAttribute(k);
  return { tag: e.tagName, parent: e.parentNode.getAttribute('class'), gp: e.parentNode.parentNode.getAttribute('class'), stroke: a('stroke'),
    width: a('stroke-width'), dash: a('stroke-dasharray'), fill: a('fill'), type: e.dataset.type, transform: a('transform'),
    opacity: e.parentNode.getAttribute('opacity'), kids: [...e.children].map(c => c.tagName) }; }"""
SEL_JS = "() => window.__pw.ink.selection()"
SELUI_JS = """() => { const g = document.querySelector('svg.ink g.sel'), c = document.querySelector('.selChips');
  return { g: !!g, box: g ? !!g.querySelector('rect.selbox') : false, dash: g && g.querySelector('rect.selbox') ? g.querySelector('rect.selbox').getAttribute('stroke-dasharray') : null,
    corners: g ? g.querySelectorAll('circle.selh').length : 0,
    chips: c ? [...c.querySelectorAll('button')].map(b => b.textContent) : [], chipsShown: c ? c.getBoundingClientRect().height > 0 : false }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def strokes(pg, pid): return pg.evaluate(STROKES_JS, pid)
def stored(pg, pid): return pg.evaluate(STORED_JS, pid)
def elinfo(pg, i, sid): return pg.evaluate(EL_JS, [i, sid])
def sel(pg): return pg.evaluate(SEL_JS)
def selui(pg): return pg.evaluate(SELUI_JS)
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name):
    if pg.locator("#noteView").is_visible(): return          # a reload reopens the note she was in
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def go_page(pg, i):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
    pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120)
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, pts, steps=6, hold=0):
    sx, sy = screen(pg, i, *pts[0])
    pg.mouse.move(sx, sy); pg.mouse.down()
    for x, y in pts[1:]:
        tx, ty = screen(pg, i, x, y); pg.mouse.move(tx, ty, steps=steps)
    if hold: pg.wait_for_timeout(hold)
    pg.mouse.up(); pg.wait_for_timeout(40)
def tap_page(pg, i, x, y):
    sx, sy = screen(pg, i, x, y); pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(40)
def drag_page(pg, i, a, b, steps=10):
    sx, sy = screen(pg, i, *a); pg.mouse.move(sx, sy); pg.mouse.down()
    tx, ty = screen(pg, i, *b); pg.mouse.move(tx, ty, steps=steps); pg.mouse.up(); pg.wait_for_timeout(40)
def grab_page(pg, i, a, b, steps=10):          # a handle grab: the right mouse button, the laptop's stand-in for the pen button
    sx, sy = screen(pg, i, *a); pg.mouse.move(sx, sy); pg.mouse.down(button="right")
    tx, ty = screen(pg, i, *b); pg.mouse.move(tx, ty, steps=steps); pg.mouse.up(button="right"); pg.wait_for_timeout(40)
def last(pg, pid): s = strokes(pg, pid); return s[-1] if s else None
def U(pg): return pg.evaluate("window.__pw.S.hist[window.__pw.S.openNote] ? window.__pw.S.hist[window.__pw.S.openNote].u.length : 0")
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(30)
def redo(pg): pg.click("#redoBtn"); pg.wait_for_timeout(30)
def tool(pg, t): pg.click(f"#tool-{t}"); pg.wait_for_timeout(20)
def near(a, b, tol): return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
def wobble(k, amp=2.0): return amp * math.sin(k * 1.7) * math.cos(k * 0.6)
def fresh(b, url=LOCAL, **kw):
    ctx = b.new_context(viewport={"width": 1280, "height": 1300}, **kw)   # tall: the whole A4 page on screen
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url); ready(pg)
    pg.evaluate(SEED_JS); pg.reload(); ready(pg)
    return ctx, pg, errs

# rough shapes, in page px (zoom 1)
def rough_line(y=200, x0=100, x1=420): return [(x0 + (x1 - x0) * k / 12, y + wobble(k, 2.5) + k * 0.4) for k in range(13)]
def rough_square(x0=150, y0=380, s=200):
    pts = []
    for (ax, ay), (bx, by) in [((x0, y0), (x0 + s, y0)), ((x0 + s, y0), (x0 + s, y0 + s)), ((x0 + s, y0 + s), (x0, y0 + s)), ((x0, y0 + s), (x0, y0))]:
        for k in range(8): pts.append((ax + (bx - ax) * k / 8 + wobble(len(pts), 2.2), ay + (by - ay) * k / 8 + wobble(len(pts) + 3, 2.2)))
    pts.append((x0 + 3, y0 + 2)); return pts
def rough_circle(cx=560, cy=480, rx=90, ry=None, n=36):
    ry = ry or rx
    return [(cx + rx * (1 + wobble(k, 0.04)) * math.cos(2 * math.pi * k / n - math.pi / 2), cy + ry * (1 + wobble(k + 2, 0.04)) * math.sin(2 * math.pi * k / n - math.pi / 2)) for k in range(n + 1)]
def rough_triangle():
    A, B, C = (150, 700), (350, 700), (250, 880)
    pts = []
    for (ax, ay), (bx, by) in [(A, B), (B, C), (C, A)]:
        for k in range(8): pts.append((ax + (bx - ax) * k / 8 + wobble(len(pts), 1.8), ay + (by - ay) * k / 8 + wobble(len(pts) + 1, 1.8)))
    pts.append((A[0] + 2, A[1] + 1)); return pts
def rough_arrow(y=980, x0=120, x1=420):
    return [(x0 + (x1 - x0) * k / 8, y + wobble(k, 1.5)) for k in range(9)] + [(x1 - 24, y - 20), (x1, y), (x1 - 24, y + 20)]
def squiggle(): return [(100 + 20 * k, 1060 + (18 if k % 2 else -18)) for k in range(12)]

# real pen input: Chromium's own input pipeline (CDP Input.dispatchMouseEvent with pointerType 'pen'), so the
# browser hit-tests, fires pointerdown / pointermove / pointerup with pointerType 'pen' and page.js sees a pen
# bb=2: the pen's side button held (bit 2 in buttons) on every event, hover included
class Pen:
    def __init__(self, ctx, pg): self.pg = pg; self.cdp = ctx.new_cdp_session(pg)
    def ev(self, t, x, y, down, bb=0, button=None):
        self.cdp.send("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "pointerType": "pen",
                                                   "button": button or ("left" if t != "mouseMoved" or down else "none"),
                                                   "buttons": (1 if down else 0) | bb, "clickCount": 0 if t == "mouseMoved" else 1})
    def hover(self, x, y, bb=0): self.ev("mouseMoved", x, y, False, bb); self.pg.wait_for_timeout(15)
    # the tip down and along: with bb=2 the button is held from the hover on, so (as the spec says) the touch
    # arrives as a move with button 0, buttons 3, not a pointerdown; the tip lifts with the button still held
    def stroke(self, pts, hold=0, steps=6, bb=0):
        (x, y) = pts[0]; self.ev("mouseMoved", x, y, False, bb); self.ev("mousePressed", x, y, True, bb)
        for (tx, ty) in pts[1:]:
            for k in range(1, steps + 1): self.ev("mouseMoved", x + (tx - x) * k / steps, y + (ty - y) * k / steps, True, bb)
            x, y = tx, ty
            self.pg.wait_for_timeout(5)
        if hold: self.pg.wait_for_timeout(hold)
        self.ev("mouseReleased", x, y, False, bb); self.pg.wait_for_timeout(20)
        if bb: self.ev("mouseMoved", x, y, False); self.pg.wait_for_timeout(20)    # the button let go in the air
        self.pg.wait_for_timeout(20)
    # a press of the side button itself: pointerdown pen, button 2, buttons 2, then the drag and the release
    def bstroke(self, pts, steps=6):
        (x, y) = pts[0]; self.ev("mouseMoved", x, y, False); self.ev("mousePressed", x, y, False, 2, "right")
        for (tx, ty) in pts[1:]:
            for k in range(1, steps + 1): self.ev("mouseMoved", x + (tx - x) * k / steps, y + (ty - y) * k / steps, False, 2, "right")
            x, y = tx, ty
            self.pg.wait_for_timeout(5)
        self.ev("mouseReleased", x, y, False, 0, "right"); self.pg.wait_for_timeout(40)
# a synthetic pen gesture: PointerEvents with pointerType 'pen' fired on whatever element is under the point
# (bubbling to the desk), the way the S Pen's own events arrive
SYNTH_JS = """([pts, bb]) => { const fire = (t, [x, y], b) => { const el = document.elementFromPoint(x, y) || document.getElementById('desk');
    el.dispatchEvent(new PointerEvent(t, { bubbles: true, cancelable: true, composed: true, pointerId: 7, pointerType: 'pen', isPrimary: true,
      clientX: x, clientY: y, button: t === 'pointermove' ? -1 : 0, buttons: b, pressure: b ? 0.5 : 0 })); return el; };
  const first = fire('pointerdown', pts[0], 1 | (bb || 0));
  for (const q of pts.slice(1)) fire('pointermove', q, 1 | (bb || 0));
  fire('pointerup', pts[pts.length - 1], 0);
  return first.closest('svg.ink') ? 'svg' : (first.id || first.className || first.tagName); }"""

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
shots = 0
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx, pg, errs = fresh(b)

        # ------------------------------------------------------------ the tray: the two new tools
        group[0] = "tray"
        open_note(pg, "Snap")
        order = pg.evaluate("""[...document.getElementById('tray').querySelectorAll(':scope > *, :scope > .tools > *')]
          .map(e => e.dataset.tool || e.dataset.slot || e.id || e.className)""")
        check("order: colours, pen, highlighter, stroke eraser, area eraser, restyle, select, gap, undo, redo, Tools slot",
              order == ["colours", "tools", "pen", "highlighter", "eraser", "area", "restyle", "select", "gap", "undoBtn", "redoBtn", "tools"], order)
        tb = pg.evaluate("""['restyle', 'select'].map(t => { const e = document.getElementById('tool-' + t), r = e.getBoundingClientRect();
          return [e.tagName, e.className, e.title, e.getAttribute('aria-label'), Math.round(r.width), Math.round(r.height), !!e.querySelector('svg'), e.textContent.trim()]; })""")
        pen_r = pg.evaluate("(() => { const r = document.getElementById('tool-pen').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })()")
        check("restyle and select are real tool buttons: icon only, a title each, the pen's size",
              all(t[0] == "BUTTON" and "tool" in t[1] and t[2] and t[3] and [t[4], t[5]] == pen_r and t[6] and t[7] == "" for t in tb), [tb, pen_r])
        check("their titles: Restyle, Select", [t[2] for t in tb] == ["Restyle", "Select"], tb)
        check("only the Tools slot is still an empty slot", pg.evaluate("[...document.querySelectorAll('#tray .slot')].map(s => s.dataset.slot + ':' + s.children.length)") == ["tools:0"])
        tool(pg, "restyle")
        on = pg.evaluate("[...document.querySelectorAll('#tray .tool.on')].map(e => e.dataset.tool)")
        tint = pg.evaluate("getComputedStyle(document.getElementById('tool-restyle')).backgroundColor")
        pen_tint = pg.evaluate("(() => { document.getElementById('tool-pen').click(); return getComputedStyle(document.getElementById('tool-pen')).backgroundColor; })()")
        check("restyle selected shows the same soft tint as the pen", on == ["restyle"] and tint == pen_tint and tint != "rgba(0, 0, 0, 0)", [on, tint, pen_tint])
        check("tray still fits (no tray scroll)", pg.evaluate("(() => { const t = document.getElementById('tray'); return t.scrollHeight <= t.clientHeight; })()"))
        check("HOLD_MS default is 500", pg.evaluate("import('./js/ink.js').then(m => m.HOLD_MS)") == 500)

        # ------------------------------------------------------------ hold-to-snap
        group[0] = "snap"
        tool(pg, "pen")
        u0 = U(pg)
        L0 = rough_line()
        draw(pg, 1, L0, hold=650)
        r = last(pg, "p1")
        check("a nearly straight stroke held 600+ ms becomes shape/line", r and r["kind"] == "shape" and r["data"]["type"] == "line", r and [r["kind"], r["data"]])
        if r and r["kind"] == "shape":
            d = r["data"]
            check("the line's ends sit near the stroke's ends", near((d["x1"], d["y1"]), L0[0], 6) and near((d["x2"], d["y2"]), L0[-1], 6), [d, L0[0], L0[-1]])
            check("same colour, width and dash as the pen", r["style"] == {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1}, r["style"])
            e = elinfo(pg, 1, r["id"])
            check("drawn as an SVG <line> inside g.pen", e and e["tag"] == "line" and e["parent"] == "pen" and e["stroke"] == "#000000" and e["width"] == "2.5" and e["fill"] == "none", e)
            check("one stroke on the page (the freehand is gone)", len(strokes(pg, "p1")) == 1)
            pg.wait_for_timeout(200)
            check("after the 150 ms fade only the shape is in the layer", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 1)
        check("a snap is ONE undo step", U(pg) == u0 + 1, [u0, U(pg)])
        undo(pg)
        check("undo takes the shape away", len(strokes(pg, "p1")) == 0)
        redo(pg)
        check("redo brings it back", len(strokes(pg, "p1")) == 1 and last(pg, "p1")["kind"] == "shape")

        draw(pg, 1, rough_square(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a rough square held: shape/rect with 4 points", r["kind"] == "shape" and r["data"]["type"] == "rect" and len(r["data"]["points"]) == 4, [r["kind"], r["data"]])
        if r["data"].get("type") == "rect":
            P = r["data"]["points"]
            check("the square is straightened (sides upright) and near its corners", P[0][1] == P[1][1] and P[1][0] == P[2][0] and P[2][1] == P[3][1] and P[3][0] == P[0][0]
                  and near(P[0], (150, 380), 8) and near(P[2], (350, 580), 8), P)
            check("drawn as an SVG <polygon>", elinfo(pg, 1, r["id"])["tag"] == "polygon")
        draw(pg, 1, rough_circle(), steps=2, hold=650)
        r = last(pg, "p1")
        check("a rough circle held: circle", r["kind"] == "shape" and r["data"]["type"] == "circle", [r["kind"], r["data"]])
        if r["data"].get("type") == "circle":
            check("centre and radius close", near((r["data"]["cx"], r["data"]["cy"]), (560, 480), 6) and abs(r["data"]["r"] - 90) <= 8, r["data"])
            check("drawn as an SVG <circle>", elinfo(pg, 1, r["id"])["tag"] == "circle")
        draw(pg, 1, rough_circle(560, 760, 130, 65), steps=2, hold=650)
        r = last(pg, "p1")
        check("a long oval held: ellipse", r["kind"] == "shape" and r["data"]["type"] == "ellipse", [r["kind"], r["data"]])
        draw(pg, 1, rough_triangle(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a rough triangle held: triangle with 3 points", r["kind"] == "shape" and r["data"]["type"] == "triangle" and len(r["data"]["points"]) == 3, [r["kind"], r["data"]])
        draw(pg, 1, rough_arrow(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a line with a V at the end held: arrow", r["kind"] == "shape" and r["data"]["type"] == "arrow", [r["kind"], r["data"]])
        if r["data"].get("type") == "arrow":
            check("the arrow runs from the start to the V's tip", near((r["data"]["x1"], r["data"]["y1"]), (120, 980), 6) and near((r["data"]["x2"], r["data"]["y2"]), (420, 980), 6), r["data"])
            e = elinfo(pg, 1, r["id"])
            check("an arrow is a <g> with its line and an open head", e["tag"] == "g" and e["kids"] == ["line", "path"], e)
        n = len(strokes(pg, "p1"))
        draw(pg, 1, squiggle(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a squiggle held: stays pen", len(strokes(pg, "p1")) == n + 1 and r["kind"] == "pen", r["kind"])
        draw(pg, 1, [(450, 1080), (700, 1082)], steps=8, hold=0)
        r = last(pg, "p1")
        check("a straight stroke lifted at once: stays pen", r["kind"] == "pen", r["kind"])
        draw(pg, 1, [(450, 1040), (700, 1042)], steps=8, hold=250)
        check("a straight stroke held only 250 ms: stays pen", last(pg, "p1")["kind"] == "pen")
        draw(pg, 1, [(30, 60), (40, 62)], steps=4, hold=650)
        check("a short stroke (under 30 px) held: stays pen", last(pg, "p1")["kind"] == "pen")
        tool(pg, "highlighter")
        draw(pg, 1, [(450, 120), (720, 124)], steps=8, hold=650)
        check("a highlighter stroke held: snaps too now (fix round point 3)", last(pg, "p1")["kind"] == "shape" and last(pg, "p1")["style"]["opacity"] < 1, last(pg, "p1"))
        tool(pg, "pen"); pg.click("#tool-pen")
        pg.locator("#toolPanel .dash[data-dash='dashed']").click(); pg.mouse.click(400, 10)
        draw(pg, 1, [(450, 300), (600, 302), (720, 303)], steps=6, hold=650)
        r = last(pg, "p1")
        e = elinfo(pg, 1, r["id"])
        check("a dashed pen line snaps dashed (dasharray on the <line>)", r["kind"] == "shape" and r["style"]["dash"] == "dashed" and e["dash"], [r["style"], e])
        pg.click("#tool-pen"); pg.locator("#toolPanel .dash[data-dash='solid']").click(); pg.mouse.click(400, 10)
        idle(pg)
        kinds = [(s["kind"], s["data"].get("type")) for s in stored(pg, "p1")]
        pg.reload(); ready(pg); open_note(pg, "Snap")
        k2 = [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p1")]
        tags = pg.evaluate("[...document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink [data-type]')].map(e => e.dataset.type)")
        check("reload keeps every shape and redraws it (pen and highlighter layers)", k2 == kinds and sorted(tags) == sorted(t for k, t in kinds if k == "shape"), [kinds, tags])
        if SHOTS and shots < 3:
            SHOTS.mkdir(parents=True, exist_ok=True); pg.screenshot(path=str(SHOTS / "u2b-snap.png")); shots += 1
        # the classifier on harder hand shapes (straight from ink.js, no drawing)
        def cls(pts): r = pg.evaluate("(p) => import('./js/ink.js').then(m => m.classify(p))", [list(q) for q in pts]); return r and r["type"]
        def turn(pts, a, c=(300, 300)):
            ca, sa = math.cos(a), math.sin(a)
            return [(c[0] + (x - c[0]) * ca - (y - c[1]) * sa, c[1] + (x - c[0]) * sa + (y - c[1]) * ca) for x, y in pts]
        sq = rough_square(200, 200, 200)
        tsq = turn(sq, math.radians(35))
        check("a square turned 35 degrees: rect", cls(tsq) == "rect", cls(tsq))
        r = pg.evaluate("(p) => import('./js/ink.js').then(m => m.classify(p))", [list(q) for q in tsq])
        check("... stored as its 4 turned corners (not straightened)", r and len(r["points"]) == 4 and r["points"][0][1] != r["points"][1][1], r)
        over = sq[:-1] + [(200 + 10 * k, 200 + wobble(k)) for k in range(1, 5)]
        check("a square closed with an overshoot past the start: rect", cls(over) == "rect", cls(over))
        ccw = [(300 + 70 * math.cos(-2 * math.pi * k / 30), 300 + 70 * math.sin(-2 * math.pi * k / 30)) for k in range(31)]
        check("a circle started at 3 o'clock, drawn the other way: circle", cls(ccw) == "circle", cls(ccw))
        check("an L stays freehand", cls([(100, 100), (100, 160), (100, 220), (140, 220), (180, 220)]) is None)
        check("a tick (V) stays freehand", cls([(100, 200), (120, 220), (140, 240), (180, 180), (220, 120)]) is None)
        check("a zigzag stays freehand", cls(squiggle()) is None)
        check("a half circle (arc) stays freehand", cls([(300 + 80 * math.cos(math.pi * k / 20), 300 - 80 * math.sin(math.pi * k / 20)) for k in range(21)]) is None)
        bow = [(100 + 15 * k, 300 + 6 * math.sin(math.pi * k / 20)) for k in range(21)]
        check("a line with a slight bow (2% of its length): line", cls(bow) == "line", cls(bow))

        ctx.close()

        # the hold override
        ctx, pg, errs2 = fresh(b, LOCAL + "&hold=1500")
        check("?hold=1500 sets HOLD_MS", pg.evaluate("import('./js/ink.js').then(m => m.HOLD_MS)") == 1500)
        open_note(pg, "Snap")
        draw(pg, 1, rough_line(), hold=650)
        check("with ?hold=1500 a 650 ms hold stays pen", last(pg, "p1")["kind"] == "pen")
        draw(pg, 1, rough_line(400), hold=1650)
        check("and a 1650 ms hold snaps", last(pg, "p1")["kind"] == "shape")
        errs += errs2
        ctx.close()

        # ------------------------------------------------------------ grabbable handles
        group[0] = "handles"
        ctx, pg, e3 = fresh(b); errs += e3
        open_note(pg, "Handles")
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2")
        check("a line to grab", ln["kind"] == "shape" and ln["data"]["type"] == "line", ln["data"])
        d0 = dict(ln["data"]); u0 = U(pg)
        hx, hy = screen(pg, 1, d0["x2"], d0["y2"])
        ring_xy = "(() => { const r = document.getElementById('handleRing'); if (!r || r.hidden) return null; const b = r.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })()"
        pg.mouse.move(hx + 6, hy + 4); pg.wait_for_timeout(20)
        plain = pg.evaluate(ring_xy)
        pg.mouse.move(hx + 300, hy + 200); pg.mouse.down(button="right"); pg.wait_for_timeout(20)   # the right button held, away from any handle
        far = pg.evaluate(ring_xy)
        pg.mouse.move(hx + 6, hy + 4); pg.wait_for_timeout(20)
        ring = pg.evaluate(ring_xy)
        check("handles are invisible until the pen is near", not far)
        check("no ring near a handle without the button", not plain, plain)
        check("within 12 px, the right button held: a small ring shows on the handle", ring and near(ring, (hx, hy), 2), [ring, hx, hy])
        pg.mouse.move(hx + 40, hy + 40); pg.wait_for_timeout(20)
        check("the ring hides when the pen moves away", pg.evaluate("document.getElementById('handleRing').hidden"))
        pg.mouse.up(button="right"); pg.wait_for_timeout(20)
        check("the right-button miss drew nothing and changed nothing", len(strokes(pg, "p2")) == 1 and last(pg, "p2")["data"] == d0 and U(pg) == u0)
        grab_page(pg, 1, (d0["x2"] + 5, d0["y2"] + 3), (d0["x2"] + 105, d0["y2"] + 3))
        d1 = last(pg, "p2")["data"]
        check("dragging the end 100 px moves x2 by 100, y2 stays", abs(d1["x2"] - (d0["x2"] + 100)) <= 1.5 and abs(d1["y2"] - d0["y2"]) <= 1.5 and d1["x1"] == d0["x1"] and d1["y1"] == d0["y1"], [d0, d1])
        check("no new stroke drawn by the grab", len(strokes(pg, "p2")) == 1)
        check("one undo step per drag", U(pg) == u0 + 1)
        check("the <line> follows", elinfo(pg, 1, ln["id"]) and abs(float(pg.evaluate(f"document.querySelector('[data-id=\"{ln['id']}\"]').getAttribute('x2')")) - d1["x2"]) < 0.2)
        undo(pg)
        check("undo puts the end back", last(pg, "p2")["data"] == d0, [last(pg, "p2")["data"], d0])
        redo(pg)
        check("redo moves it again", last(pg, "p2")["data"] == d1)
        draw(pg, 1, [(200, 280), (260, 330), (330, 290)], steps=5)
        check("pen-down on the shape's middle (no handle) draws as normal", len(strokes(pg, "p2")) == 2 and last(pg, "p2")["kind"] == "pen")
        draw(pg, 1, rough_circle(500, 650, 80), steps=2, hold=650)
        c0 = last(pg, "p2")["data"]
        grab_page(pg, 1, (c0["cx"] + c0["r"], c0["cy"]), (c0["cx"] + c0["r"] + 40, c0["cy"]))
        c1 = last(pg, "p2")["data"]
        check("a circle's E handle changes its radius (centre stays)", c1["type"] == "circle" and abs(c1["r"] - (c0["r"] + 40)) <= 1.5 and c1["cx"] == c0["cx"] and c1["cy"] == c0["cy"], [c0, c1])
        draw(pg, 1, rough_square(150, 800, 160), steps=3, hold=650)
        q0 = last(pg, "p2")
        check("a rough square to grab", q0["kind"] == "shape" and q0["data"]["type"] == "rect", [q0["kind"], q0["data"]])
        q0 = q0["data"].get("points") or [[0, 0]] * 4
        grab_page(pg, 1, tuple(q0[2]), (q0[2][0] + 50, q0[2][1] + 30))
        q1 = last(pg, "p2")["data"]["points"]
        check("a rect's corner: the rect grows and stays upright, the opposite corner holds",
              q1[0] == q0[0] and abs(q1[2][0] - (q0[2][0] + 50)) <= 1.5 and abs(q1[2][1] - (q0[2][1] + 30)) <= 1.5 and q1[1][0] == q1[2][0] and q1[3][1] == q1[2][1] and q1[1][1] == q1[0][1], [q0, q1])
        tool(pg, "highlighter")
        n = len(strokes(pg, "p2"))
        drag_page(pg, 1, (c1["cx"], c1["cy"] - c1["r"]), (c1["cx"] + 60, c1["cy"] - c1["r"] - 40))
        check("the highlighter never grabs: it draws", len(strokes(pg, "p2")) == n + 1 and last(pg, "p2")["kind"] == "highlighter")
        top = last(pg, "p2")["data"]
        grab_page(pg, 1, (c1["cx"], c1["cy"] - c1["r"]), (c1["cx"] + 60, c1["cy"] - c1["r"] - 40))
        check("the highlighter with the right button: nothing at all (no stroke, no grab)", len(strokes(pg, "p2")) == n + 1 and last(pg, "p2")["data"] == top)
        ctx.close()

        # ------------------------------------------------------------ restyle
        group[0] = "restyle"
        ctx, pg, e4 = fresh(b); errs += e4
        open_note(pg, "Restyle")
        draw(pg, 1, [(100, 200), (250, 210), (400, 200)])
        draw(pg, 1, [(100, 300), (250, 310), (400, 300)])
        draw(pg, 1, [(100, 400), (250, 410), (400, 400)])
        A, B, C = [s["id"] for s in strokes(pg, "p3")]
        old = strokes(pg, "p3")[0]["style"]
        pg.click("#tray .sw[data-colour='#FF3636']")
        pg.click("#tool-pen")                                  # already selected: the panel opens
        for _ in range(7): pg.locator("#toolPanel [aria-label='Width bigger']").click()
        pg.locator("#toolPanel .dash[data-dash='dashed']").click()
        pg.mouse.click(400, 10)
        st = pg.evaluate("window.__pw.tray()")["pen"]
        check("the pen is set to red, width 6, dashed", st == {"colour": "#FF3636", "width": 6, "dash": "dashed"}, st)
        tool(pg, "restyle")
        u0 = U(pg)
        tap_page(pg, 1, 250, 211)
        s = {x["id"]: x for x in strokes(pg, "p3")}
        check("a tap on a stroke: it takes red, 6, dashed", s[A]["style"] == {"colour": "#FF3636", "width": 6, "dash": "dashed", "opacity": 1}, s[A]["style"])
        check("the others are untouched", s[B]["style"] == old and s[C]["style"] == old)
        e = elinfo(pg, 1, A)
        check("its path shows it (stroke, width, dasharray)", e["stroke"] == "#FF3636" and e["width"] == "6" and e["dash"] == "18 18", e)
        check("the points did not change", s[A]["data"]["points"][0] == [100, 200])
        check("one undo step per tap", U(pg) == u0 + 1)
        undo(pg)
        check("undo restores the old style", {x["id"]: x for x in strokes(pg, "p3")}[A]["style"] == old)
        redo(pg)
        check("redo restyles again", {x["id"]: x for x in strokes(pg, "p3")}[A]["style"]["colour"] == "#FF3636")
        u1 = U(pg)
        tap_page(pg, 1, 250, 211)
        check("restyling an already restyled stroke adds no step", U(pg) == u1)
        tap_page(pg, 1, 600, 800)
        check("a tap on empty paper adds no step", U(pg) == u1)
        pg.click("#tray .sw[data-colour='#2CB05F']")
        on = pg.evaluate("[...document.querySelectorAll('#tray .tool.on')].map(e => e.dataset.tool)")
        ts = pg.evaluate("window.__pw.tray()")
        check("a colour tap with restyle on: restyle stays, restyle's own colour changes, the pen's does not (fix round point 4)",
              on == ["restyle"] and ts["restyle"]["colour"] == "#2CB05F" and ts["pen"]["colour"] == "#FF3636", [on, ts["restyle"], ts["pen"]])
        drag_page(pg, 1, (250, 280), (250, 430), steps=12)
        s = {x["id"]: x for x in strokes(pg, "p3")}
        check("a drag across two strokes restyles both", s[B]["style"]["colour"] == "#2CB05F" and s[C]["style"]["colour"] == "#2CB05F" and s[A]["style"]["colour"] == "#FF3636")
        check("... in one undo step", U(pg) == u1 + 1)
        undo(pg)
        s = {x["id"]: x for x in strokes(pg, "p3")}
        check("one undo puts both back", s[B]["style"] == old and s[C]["style"] == old)
        # a highlighter stroke takes the highlighter's settings and moves to its opacity group
        tool(pg, "highlighter")
        draw(pg, 1, [(100, 600), (400, 604)])
        H = last(pg, "p3")["id"]
        pg.click("#tool-highlighter")
        pg.locator("#toolPanel [aria-label='Opacity bigger']").click(); pg.locator("#toolPanel [aria-label='Opacity bigger']").click()
        pg.mouse.click(400, 10)
        pg.click("#tray .sw[data-colour='#0D0DFF']")
        tool(pg, "restyle")
        tap_page(pg, 1, 250, 602)
        h = {x["id"]: x for x in strokes(pg, "p3")}[H]
        e = elinfo(pg, 1, H)
        check("a highlighter stroke takes the highlighter's colour, width and opacity", h["style"] == {"colour": "#0D0DFF", "width": 18, "dash": "solid", "opacity": 0.6}, h["style"])
        check("... and sits in the 0.6 .hlo group with no own opacity", e["parent"] == "hlo" and e["gp"] == "hl" and e["opacity"] == "0.6", e)
        check("the empty 0.4 group went", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.hlo[data-opacity=\"0.4\"]').length") == 0)
        undo(pg)
        check("undo puts it back in the 0.4 group", elinfo(pg, 1, H)["opacity"] == "0.4")
        tool(pg, "pen")
        draw(pg, 1, rough_circle(560, 850, 70), steps=2, hold=650)
        S_ = last(pg, "p3")
        tool(pg, "restyle")
        pg.click("#tray .sw[data-colour='#2CB05F']")           # restyle starts in the pen's red: green is a change
        tap_page(pg, 1, 560 + 70, 850)
        s2 = {x["id"]: x for x in strokes(pg, "p3")}[S_["id"]]
        check("a shape restyles too (pen settings)", S_["kind"] == "shape" and s2["style"]["colour"] == "#2CB05F" and s2["style"]["width"] == 6 and s2["style"]["dash"] == "dashed", s2["style"])
        check("... and stays the same shape", s2["data"] == S_["data"] and elinfo(pg, 1, S_["id"])["tag"] == "circle")
        ctx.close()

        # ------------------------------------------------------------ rectangle select
        group[0] = "select"
        ctx, pg, e5 = fresh(b); errs += e5
        open_note(pg, "Select")
        draw(pg, 1, [(150, 200), (250, 220), (350, 200)])
        draw(pg, 1, [(150, 280), (250, 300), (350, 280)])
        draw(pg, 1, [(150, 600), (250, 620), (350, 600)])
        A, B, C = [s["id"] for s in strokes(pg, "p4")]
        P0 = {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")}
        tool(pg, "select")
        u0 = U(pg)
        drag_page(pg, 1, (120, 170), (380, 330))
        sl = sel(pg)
        check("a box around two of three: those two are selected", sl and sorted(sl["ids"]) == sorted([A, B]), sl)
        ui = selui(pg)
        check("a dashed blue box with four corner handles", ui["box"] and ui["dash"] and ui["corners"] == 4, ui)
        check("two chips above it: Copy and Delete", ui["chips"] == ["Copy", "Delete"] and ui["chipsShown"], ui)
        cb = pg.locator(".selChips").bounding_box(); bb = pg.locator("svg.ink g.sel rect.selbox").bounding_box()
        check("the chips sit above the box", cb["y"] + cb["height"] <= bb["y"] + 1, [cb, bb])
        check("selecting is not an undo step", U(pg) == u0)
        if SHOTS and shots < 3:
            pg.screenshot(path=str(SHOTS / "u2b-select.png")); shots += 1
        drag_page(pg, 1, (250, 250), (300, 300))
        S1 = {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")}
        mv = lambda pts, dx, dy: [[round(x + dx, 1), round(y + dy, 1)] for x, y in pts]
        check("drag inside 50 px: the two move by 50, 50", S1[A] == mv(P0[A], 50, 50) and S1[B] == mv(P0[B], 50, 50), [S1[A][:2], P0[A][:2]])
        check("the third does not move", S1[C] == P0[C])
        check("one undo step for the move", U(pg) == u0 + 1)
        check("the selection stays on the moved strokes", sorted(sel(pg)["ids"]) == sorted([A, B]))
        check("no transform left on the paths", elinfo(pg, 1, A)["transform"] is None)
        undo(pg)
        check("undo puts them back", {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")} == P0)
        sb = sel(pg)
        check("the box follows the undo", sb and abs(sb["box"][0] - (150 - 1.25)) < 0.5, sb)
        redo(pg)
        check("redo moves them again", {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")} == S1)
        u1 = U(pg)
        pg.locator(".selChips .chip[data-act='copy']").click(); pg.wait_for_timeout(30)
        all_ = strokes(pg, "p4")
        copies = [s for s in all_ if s["id"] not in (A, B, C)]
        check("Copy adds two more", len(all_) == 5 and len(copies) == 2)
        cp = {tuple(s["data"]["points"][0]) for s in copies}
        check("the copies sit 24 px down and right", cp == {tuple(mv([S1[A][0]], 24, 24)[0]), tuple(mv([S1[B][0]], 24, 24)[0])}, cp)
        check("the copy becomes the selection", sorted(sel(pg)["ids"]) == sorted(s["id"] for s in copies))
        check("Copy is one undo step", U(pg) == u1 + 1)
        pg.locator(".selChips .chip[data-act='delete']").click(); pg.wait_for_timeout(30)
        check("Delete removes the selection (the copies)", sorted(s["id"] for s in strokes(pg, "p4")) == sorted([A, B, C]))
        check("Delete clears the selection and its chips", sel(pg) is None and not selui(pg)["g"] and not selui(pg)["chips"])
        check("Delete is one undo step", U(pg) == u1 + 2)
        undo(pg)
        check("undo Delete: the copies are back", len(strokes(pg, "p4")) == 5)
        undo(pg)
        check("undo Copy: back to three", len(strokes(pg, "p4")) == 3)
        redo(pg); redo(pg)
        check("redo Copy and redo Delete", len(strokes(pg, "p4")) == 3 and U(pg) == u1 + 2)
        # resize: scale about the opposite corner, aspect kept
        drag_page(pg, 1, (120, 570), (380, 650))
        check("box around the third only", sel(pg)["ids"] == [C])
        bx = sel(pg)["box"]
        q = pg.evaluate("(() => { const c = [...document.querySelectorAll('svg.ink g.sel circle.selh')].map(e => [+e.getAttribute('cx'), +e.getAttribute('cy')]); return c; })()")
        c2 = q[2]
        drag_page(pg, 1, (c2[0], c2[1]), (c2[0] + 100, c2[1] + 20), steps=12)
        rc = {s["id"]: s for s in strokes(pg, "p4")}[C]
        b0 = [min(p[0] for p in P0[C]), min(p[1] for p in P0[C]), max(p[0] for p in P0[C]), max(p[1] for p in P0[C])]
        b1 = [min(p[0] for p in rc["data"]["points"]), min(p[1] for p in rc["data"]["points"]), max(p[0] for p in rc["data"]["points"]), max(p[1] for p in rc["data"]["points"])]
        sx = (b1[2] - b1[0]) / (b0[2] - b0[0]); sy = (b1[3] - b1[1]) / (b0[3] - b0[1])
        check("a corner drag scales the stroke up", sx > 1.2, [sx, b0, b1])
        check("the aspect is kept", abs(sx - sy) < 0.03, [sx, sy])
        check("the opposite (top-left) corner holds", abs(b1[0] - b0[0]) < 3 and abs(b1[1] - b0[1]) < 3, [b0, b1])
        check("the ink width scales with it", abs(rc["style"]["width"] - 2.5 * sx) < 0.1, rc["style"])
        undo(pg)
        check("undo puts its size back", {s["id"]: s for s in strokes(pg, "p4")}[C]["data"]["points"] == P0[C])
        # touch any part (fix round point 2: the old "half inside" checks now follow the new rule)
        tap_page(pg, 1, 700, 1000)
        check("a tap outside clears the selection", sel(pg) is None and not selui(pg)["g"])
        drag_page(pg, 1, (140, 170), (290, 250))      # A spans x 150..350 (+50 moved): 200..400, so this box holds a quarter of it
        check("a stroke only a quarter inside is selected now (touch any part)", sel(pg) is not None and A in sel(pg)["ids"], sel(pg))
        tap_page(pg, 1, 700, 1000)
        drag_page(pg, 1, (500, 170), (700, 330))
        check("a box that touches nothing selects nothing", sel(pg) is None, sel(pg))
        drag_page(pg, 1, (190, 170), (330, 330))      # A after the move: x 200..400; 190..330 holds 65% of it
        sl = sel(pg)
        check("a stroke mostly inside is selected", sl and A in sl["ids"], sl)
        tool(pg, "pen")
        check("a tool change clears the selection", sel(pg) is None and not selui(pg)["g"])
        tool(pg, "select")
        drag_page(pg, 1, (120, 170), (420, 360))
        check("selected again", sel(pg) is not None)
        go_page(pg, 2)
        check("a page change clears the selection", sel(pg) is None and not selui(pg)["g"], pg.evaluate("window.__pw.current()"))
        go_page(pg, 1)
        if pg.locator("#pageList").is_visible(): pg.click("#plClose")
        drag_page(pg, 1, (120, 170), (420, 360))
        z0 = zoom(pg)
        r0 = float(pg.evaluate("document.querySelector('svg.ink g.sel circle.selh').getAttribute('r')"))
        pg.mouse.move(640, 400); pg.keyboard.down("Control"); pg.mouse.wheel(0, -200); pg.keyboard.up("Control"); pg.wait_for_timeout(120)
        z1 = zoom(pg)
        r1_ = float(pg.evaluate("document.querySelector('svg.ink g.sel circle.selh') ? document.querySelector('svg.ink g.sel circle.selh').getAttribute('r') : 0"))
        check("zooming keeps the corner handles the same size on screen", z1 != z0 and abs(r1_ * z1 - r0 * z0) < 0.2, [z0, z1, r0, r1_])
        tool(pg, "pen")
        check("the layer has only hl and pen again after the selection", pg.evaluate("[...document.querySelector('#stack .sheet[data-index=\"1\"] svg.ink').children].map(c => c.getAttribute('class')).join()") == "hl,pen")
        ctx.close()

        # ------------------------------------------------------------ erasers on shapes
        group[0] = "erasers"
        ctx, pg, e6 = fresh(b); errs += e6
        open_note(pg, "Erase")
        draw(pg, 1, rough_circle(300, 300, 90), steps=2, hold=650)
        draw(pg, 1, rough_line(600, 100, 500), hold=650)
        kinds = [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")]
        check("a circle and a line to erase", kinds == [("shape", "circle"), ("shape", "line")], kinds)
        u0 = U(pg)
        tool(pg, "area")
        drag_page(pg, 1, (300 + 90, 280), (300 + 90, 320), steps=4)
        kinds = [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")]
        check("the area eraser over the circle removes the whole circle (no pieces)", kinds == [("shape", "line")], kinds)
        check("one undo step", U(pg) == u0 + 1)
        undo(pg)
        check("undo brings the circle back whole", [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")] == [("shape", "circle"), ("shape", "line")])
        tool(pg, "eraser")
        tap_page(pg, 1, 300, 600 + 2)
        check("the stroke eraser removes the line whole", [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")] == [("shape", "circle")])
        ctx.close()


        # ------------------------------------------------------------ fix round point 1: real pen events on a handle
        group[0] = "pen handles (fix 1)"
        ctx, pg, e8 = fresh(b); errs += e8
        open_note(pg, "Handles")
        pen = Pen(ctx, pg)
        check("the ink layer lets the pen through (svg.ink pointer-events: none)",
              pg.evaluate("getComputedStyle(document.querySelector('#stack .sheet svg.ink')).pointerEvents") == "none")
        check("the shape handle reach is 20 px, selection corners 12 px",
              pg.evaluate("import('./js/ink.js').then(m => [m.HANDLE_REACH, m.GRAB])") == [20, 12])
        pg.evaluate("""() => { window.__pl = []; const d = document.getElementById('desk');
          for (const t of ['pointerdown', 'pointerup']) d.addEventListener(t, (e) => window.__pl.push(t + ':' + e.pointerType), true); }""")
        pen.stroke([screen(pg, 1, *q) for q in rough_line(300, 150, 450)], hold=650)
        ln = last(pg, "p2")
        check("a line drawn and held with the PEN snaps", ln and ln["kind"] == "shape" and ln["data"]["type"] == "line", ln)
        check("the desk saw pen events (pointerType pen)", pg.evaluate("window.__pl").count("pointerdown:pen") == 1, pg.evaluate("window.__pl"))
        d0 = dict(ln["data"]); u0 = U(pg)
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        hit = pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e.closest('svg.ink') ? 'svg.ink' : (e.id || e.className); }", [ex, ey])
        check("the element under the line's end is not the ink layer (the desk gets the pen)", hit != "svg.ink", hit)
        ring_on = lambda: pg.evaluate("(() => { const r = document.getElementById('handleRing'); return !!r && !r.hidden; })()")
        pen.hover(ex + 26, ey, 2); off26 = ring_on()
        pen.hover(ex + 16, ey, 2); on16 = ring_on()
        pen.hover(ex + 16, ey); bare16 = ring_on()
        check("pen hovering 16 px from the end, button held: the ring shows", on16)
        check("pen hovering 26 px away, button held: no ring", not off26)
        check("pen hovering 16 px from the end, no button: no ring", not bare16)
        pen.bstroke([(ex + 16, ey + 2), (ex + 116, ey + 2)])
        d1 = last(pg, "p2")["data"]
        check("pen button down 16 px from the end grabs it: x2 moves 100, y2 stays", abs(d1["x2"] - (d0["x2"] + 100)) <= 1.5 and abs(d1["y2"] - d0["y2"]) <= 1.5, [d0, d1])
        check("the other end stays put (the gradient changes)", d1["x1"] == d0["x1"] and d1["y1"] == d0["y1"], d1)
        check("no stroke drawn by the grab, one undo step", len(strokes(pg, "p2")) == 1 and U(pg) == u0 + 1, [len(strokes(pg, "p2")), U(pg), u0])
        sx, sy = screen(pg, 1, d1["x1"], d1["y1"])
        first = pg.evaluate(SYNTH_JS, [[[sx - 8, sy + 6], [sx - 8, sy + 46], [sx - 8, sy + 86]], 2])
        d2 = last(pg, "p2")["data"]
        check("synthetic pen PointerEvents (buttons 3: tip and button) on the start end: x1 y1 move, x2 y2 stay", abs(d2["y1"] - (d1["y1"] + 80)) <= 1.5 and d2["x2"] == d1["x2"] and d2["y2"] == d1["y2"], [first, d1, d2])
        n = len(strokes(pg, "p2"))
        ex, ey = screen(pg, 1, d2["x2"], d2["y2"])
        pen.stroke([(ex + 30, ey + 30), (ex + 90, ey + 60)])
        check("pen down 30 px from any handle draws as normal", len(strokes(pg, "p2")) == n + 1 and last(pg, "p2")["kind"] == "pen")
        ctx.close()

        # ------------------------------------------------------------ fix round point 2: touch any part
        group[0] = "touch any part (fix 2)"
        ctx, pg, e9 = fresh(b); errs += e9
        open_note(pg, "Select")
        draw(pg, 1, [(100, 150), (250, 152), (400, 150)])
        draw(pg, 1, [(100, 300), (300, 300)])
        draw(pg, 1, [(450, 340), (560, 230)], steps=1)              # a diagonal: its two points stay outside the box below
        draw(pg, 1, rough_circle(300, 800, 90), steps=2, hold=650)
        S1, S2, D, CI = [s["id"] for s in strokes(pg, "p4")]
        check("a diagonal of just two points, and a circle", len(strokes(pg, "p4")[2]["data"]["points"]) == 2 and strokes(pg, "p4")[3]["data"]["type"] == "circle",
              [strokes(pg, "p4")[2]["data"], strokes(pg, "p4")[3]["data"].get("type")])
        tool(pg, "select")
        drag_page(pg, 1, (370, 100), (520, 200))                     # holds x 370..400 of 100..400: 10%
        check("a stroke 10% inside the box is taken (whole)", sel(pg) and sel(pg)["ids"] == [S1], sel(pg))
        tap_page(pg, 1, 700, 1050)
        drag_page(pg, 1, (520, 250), (650, 350))                     # only the diagonal's middle crosses this box's corner
        check("a diagonal that only crosses the box's corner is taken", sel(pg) and sel(pg)["ids"] == [D], sel(pg))
        tap_page(pg, 1, 700, 1050)
        drag_page(pg, 1, (330, 260), (450, 290))                     # S2 ends at x 300, y 300: fully outside
        check("a stroke fully outside is not taken", sel(pg) is None, sel(pg))
        drag_page(pg, 1, (370, 700), (500, 900))                     # catches the circle's right side
        check("a box over part of a circle's outline takes the circle", sel(pg) and sel(pg)["ids"] == [CI], sel(pg))
        tap_page(pg, 1, 700, 1050)
        drag_page(pg, 1, (260, 760), (340, 840))                     # inside the circle, touching no ink
        check("a box inside the circle that touches no outline takes nothing", sel(pg) is None, sel(pg))
        drag_page(pg, 1, (50, 100), (700, 1000))
        check("a box round everything takes all four", sel(pg) and sorted(sel(pg)["ids"]) == sorted([S1, S2, D, CI]), sel(pg))
        src = pg.evaluate("(u) => fetch(u).then(r => r.text())", "./js/ink.js")
        check("no half rule left in inBox", "0.5 * (x1 - x0)" not in src)
        ctx.close()

        # ------------------------------------------------------------ fix round point 3: the highlighter snaps too
        group[0] = "highlighter snap (fix 3)"
        ctx, pg, e10 = fresh(b); errs += e10
        open_note(pg, "Snap")
        tool(pg, "highlighter")
        u0 = U(pg)
        draw(pg, 1, rough_line(), hold=650)
        r = last(pg, "p1")
        check("a held highlighter line becomes shape/line", r["kind"] == "shape" and r["data"]["type"] == "line", [r["kind"], r["data"]])
        check("it keeps the highlighter's look (colour, width, solid, opacity)", r["style"] == {"colour": "#FFC107", "width": 18, "dash": "solid", "opacity": 0.4}, r["style"])
        e = elinfo(pg, 1, r["id"])
        check("it renders inside the highlighter layer: g.hlo (0.4) under g.hl", e["tag"] == "line" and e["parent"] == "hlo" and e["gp"] == "hl" and e["opacity"] == "0.4", e)
        own = pg.evaluate(f"(() => {{ const e = document.querySelector('[data-id=\"{r['id']}\"]'); return [e.getAttribute('stroke-opacity'), e.getAttribute('stroke-linecap')]; }})()")
        check("no own opacity on it (the group does it), round ends", own == [None, "round"], own)
        check("nothing in g.pen", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 0)
        pg.wait_for_timeout(200)
        check("after the fade only the shape is in its .hlo group", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.hlo > *').length") == 1)
        check("a highlighter snap is ONE undo step", U(pg) == u0 + 1, [u0, U(pg)])
        undo(pg)
        check("undo takes it away (and its empty group)", len(strokes(pg, "p1")) == 0 and pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.hlo').length") == 0)
        redo(pg)
        check("redo brings it back in its .hlo group", elinfo(pg, 1, r["id"])["parent"] == "hlo")
        draw(pg, 1, rough_arrow(), steps=3, hold=650)
        a = last(pg, "p1")
        check("a highlighter arrow is stored as a line", a["kind"] == "shape" and a["data"]["type"] == "line", a["data"])
        if a["data"].get("type") == "line":
            check("... from the start to the V's tip", near((a["data"]["x1"], a["data"]["y1"]), (120, 980), 6) and near((a["data"]["x2"], a["data"]["y2"]), (420, 980), 6), a["data"])
        draw(pg, 1, rough_square(), steps=3, hold=650)
        q = last(pg, "p1")
        check("a held highlighter square: rect in the .hlo group", q["kind"] == "shape" and q["data"]["type"] == "rect" and elinfo(pg, 1, q["id"])["parent"] == "hlo", [q["kind"], q["data"]])
        draw(pg, 1, rough_circle(), steps=2, hold=650)
        c = last(pg, "p1")
        check("a held highlighter circle: circle in the .hlo group", c["kind"] == "shape" and c["data"]["type"] == "circle" and elinfo(pg, 1, c["id"])["parent"] == "hlo", [c["kind"], c["data"]])
        draw(pg, 1, [(450, 1080), (700, 1082)], steps=8, hold=0)
        check("a highlighter stroke lifted at once stays a highlighter stroke", last(pg, "p1")["kind"] == "highlighter")
        idle(pg)
        pg.reload(); ready(pg); open_note(pg, "Snap")
        check("after a reload the highlighter shapes are still in the .hlo group",
              all(elinfo(pg, 1, x)["parent"] == "hlo" for x in (r["id"], q["id"], c["id"])) and pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 0)
        # its handles: the pen tool grabs a highlighter line's end like any shape's
        tool(pg, "pen")
        L = {x["id"]: x for x in strokes(pg, "p1")}[r["id"]]["data"]
        grab_page(pg, 1, (L["x2"] + 4, L["y2"]), (L["x2"] + 64, L["y2"] + 30))
        L2 = {x["id"]: x for x in strokes(pg, "p1")}[r["id"]]["data"]
        check("the pen grabs a highlighter line's end: only that end moves", abs(L2["x2"] - (L["x2"] + 60)) <= 1.5 and L2["x1"] == L["x1"] and elinfo(pg, 1, r["id"])["parent"] == "hlo", [L, L2])
        # restyle: the highlighter's settings, and it may change opacity group
        pg.click("#tool-highlighter"); pg.click("#tool-highlighter")
        pg.locator("#toolPanel [aria-label='Opacity bigger']").click(); pg.locator("#toolPanel [aria-label='Opacity bigger']").click()
        pg.mouse.click(400, 10)
        tool(pg, "restyle")
        pg.click("#tray .sw[data-colour='#FF3636']")
        cx_, cy_ = {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]["data"]["cx"], {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]["data"]["cy"]
        rr = {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]["data"]["r"]
        tap_page(pg, 1, cx_ + rr, cy_)
        c2 = {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]
        e = elinfo(pg, 1, c["id"])
        check("restyle on a highlighter circle: red, the highlighter's width and new opacity, still a circle",
              c2["style"] == {"colour": "#FF3636", "width": 18, "dash": "solid", "opacity": 0.6} and c2["data"]["type"] == "circle", c2["style"])
        check("... and it moved to the 0.6 .hlo group", e["parent"] == "hlo" and e["opacity"] == "0.6" and e["tag"] == "circle", e)
        tool(pg, "eraser")
        n = len(strokes(pg, "p1"))
        P0 = q["data"]["points"][0]
        tap_page(pg, 1, P0[0] + 40, P0[1])
        check("the stroke eraser takes a highlighter rect whole", len(strokes(pg, "p1")) == n - 1 and q["id"] not in [x["id"] for x in strokes(pg, "p1")])
        ctx.close()

        # ------------------------------------------------------------ fix round point 4: restyle has its own colour
        group[0] = "restyle colour (fix 4)"
        ctx, pg, e11 = fresh(b); errs += e11
        open_note(pg, "Restyle")
        draw(pg, 1, [(100, 200), (250, 210), (400, 200)])
        PS = last(pg, "p3")["id"]
        tool(pg, "highlighter")
        draw(pg, 1, [(100, 400), (400, 404)])
        HS = last(pg, "p3")["id"]
        tool(pg, "restyle")
        ts = pg.evaluate("window.__pw.tray()")
        check("restyle picked after the highlighter: its colour starts as the highlighter's", ts["restyle"]["colour"] == "#FFC107", ts.get("restyle"))
        pg.click("#tray .sw[data-colour='#FF3636']")
        ts = pg.evaluate("window.__pw.tray()")
        check("a colour tap with restyle on: only restyle's colour changes", ts["restyle"]["colour"] == "#FF3636" and ts["pen"]["colour"] == "#000000" and ts["highlighter"]["colour"] == "#FFC107", [ts["restyle"], ts["pen"], ts["highlighter"]])
        check("the swatch ring shows the restyle colour", pg.evaluate("[...document.querySelectorAll('#tray .sw.on')].map(e => e.dataset.colour)") == ["#FF3636"])
        u0 = U(pg)
        tap_page(pg, 1, 250, 211)
        p_ = {x["id"]: x for x in strokes(pg, "p3")}[PS]
        check("a tap on a PEN stroke: red at the pen's width and dash", p_["style"] == {"colour": "#FF3636", "width": 2.5, "dash": "solid", "opacity": 1}, p_["style"])
        tap_page(pg, 1, 250, 402)
        h_ = {x["id"]: x for x in strokes(pg, "p3")}[HS]
        check("a tap on a highlight: red, still a highlight (width 18, opacity 0.4, in .hlo)",
              h_["style"] == {"colour": "#FF3636", "width": 18, "dash": "solid", "opacity": 0.4} and elinfo(pg, 1, HS)["parent"] == "hlo", h_["style"])
        check("two taps, two undo steps", U(pg) == u0 + 2)
        ts = pg.evaluate("window.__pw.tray()")
        check("the pen's and the highlighter's own colours did not move", ts["pen"]["colour"] == "#000000" and ts["highlighter"]["colour"] == "#FFC107", [ts["pen"], ts["highlighter"]])
        # the spare slot while restyle is on: it sets the restyle colour
        pg.click("#tray .spec")
        pg.wait_for_selector("#specPicker:not([hidden])")
        cell = pg.locator("#specPicker polygon[data-cell='4-0']")
        cc = cell.get_attribute("data-colour")
        bb = cell.bounding_box(); pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        pg.click("#specPicker .done")
        ts = pg.evaluate("window.__pw.tray()")
        check("the spare slot's pick with restyle on sets the restyle colour (pen unchanged)", ts["restyle"]["colour"] == cc and ts["pen"]["colour"] == "#000000" and ts["tool"] == "restyle", [cc, ts["restyle"], ts["pen"], ts["tool"]])
        tap_page(pg, 1, 250, 211)
        check("... and a tap gives the stroke that colour", {x["id"]: x for x in strokes(pg, "p3")}[PS]["style"]["colour"] == cc)
        idle(pg)
        check("restyle's colour is saved with the tray", json.loads(pg.evaluate("localStorage.getItem('pw.tools')")).get("restyle", {}).get("colour") == cc)
        tool(pg, "pen")
        check("back to the pen: the ring shows the pen's own black", pg.evaluate("[...document.querySelectorAll('#tray .sw.on')].map(e => e.dataset.colour)") == ["#000000"])
        draw(pg, 1, [(100, 600), (400, 610)])
        check("the pen draws in its own colour, unchanged", last(pg, "p3")["style"]["colour"] == "#000000")
        ctx.close()

        # ------------------------------------------------------------ fix round point 5: restyle on a selection
        group[0] = "selection restyle (fix 5)"
        ctx, pg, e12 = fresh(b); errs += e12
        open_note(pg, "Select")
        pg.click("#tool-pen")                                    # pen dashed for one stroke, then back to solid
        pg.locator("#toolPanel .dash[data-dash='dashed']").click(); pg.mouse.click(400, 10)
        draw(pg, 1, [(150, 200), (250, 220), (350, 200)])
        A = last(pg, "p4")["id"]
        pg.click("#tool-pen"); pg.locator("#toolPanel .dash[data-dash='solid']").click(); pg.mouse.click(400, 10)
        tool(pg, "highlighter")
        draw(pg, 1, [(150, 300), (350, 304)])
        H = last(pg, "p4")["id"]
        draw(pg, 1, rough_line(400, 150, 350), hold=650)
        S = last(pg, "p4")["id"]
        tool(pg, "pen")
        draw(pg, 1, [(150, 800), (250, 820), (350, 800)])
        C = last(pg, "p4")["id"]
        before = {x["id"]: x for x in strokes(pg, "p4")}
        check("set up: a dashed pen stroke, a highlight, a highlighter shape, one more pen stroke",
              before[A]["style"]["dash"] == "dashed" and before[H]["kind"] == "highlighter" and before[S]["kind"] == "shape" and before[S]["style"]["opacity"] == 0.4, [before[A]["style"], before[S]["kind"]])
        tool(pg, "select")
        drag_page(pg, 1, (120, 170), (380, 430))
        check("the box takes the three", sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, H, S]), sel(pg))
        u0 = U(pg)
        pg.click("#tray .sw[data-colour='#FF0C84']")
        now = {x["id"]: x for x in strokes(pg, "p4")}
        check("a colour tap recolours every selected stroke", all(now[i]["style"]["colour"] == "#FF0C84" for i in (A, H, S)), [now[i]["style"] for i in (A, H, S)])
        check("... keeping width, dash, opacity and geometry", all({**before[i]["style"], "colour": "#FF0C84"} == now[i]["style"] and before[i]["data"] == now[i]["data"] for i in (A, H, S)))
        check("the highlight and the highlighter shape stay in the .hlo group", elinfo(pg, 1, H)["parent"] == "hlo" and elinfo(pg, 1, S)["parent"] == "hlo")
        check("the stroke outside the selection is untouched", now[C]["style"] == before[C]["style"])
        check("ONE undo step", U(pg) == u0 + 1, [u0, U(pg)])
        ts = pg.evaluate("window.__pw.tray()")
        check("select stays the tool, the selection and its box stay", ts["tool"] == "select" and sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, H, S]) and selui(pg)["box"], [ts["tool"], sel(pg)])
        check("the pen's colour did not become pink", ts["pen"]["colour"] == "#000000" and ts["highlighter"]["colour"] == "#FFC107", [ts["pen"], ts["highlighter"]])
        undo(pg)
        check("undo puts every colour back (the selection follows)", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"] == before[i]["style"] for i in (A, H, S)) and sel(pg) is not None)
        redo(pg)
        check("redo recolours again", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"]["colour"] == "#FF0C84" for i in (A, H, S)))
        # the full restyle: tap Restyle while the selection exists (the pen is black 2.5 solid, the highlighter amber 18 at 0.4)
        u1 = U(pg)
        tool(pg, "restyle")
        now = {x["id"]: x for x in strokes(pg, "p4")}
        check("tapping Restyle restyles the selection: pen settings for the pen stroke", now[A]["style"] == {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1}, now[A]["style"])
        check("... highlighter settings for the highlight and the highlighter shape (colour from restyle)",
              all(now[i]["style"] == {"colour": "#000000", "width": 18, "dash": "solid", "opacity": 0.4} for i in (H, S)), [now[H]["style"], now[S]["style"]])
        check("one undo step, the selection kept, select still the tool, restyle not entered",
              U(pg) == u1 + 1 and sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, H, S]) and pg.evaluate("window.__pw.tray()")["tool"] == "select"
              and pg.evaluate("[...document.querySelectorAll('#tray .tool.on')].map(e => e.dataset.tool)") == ["select"], [U(pg), u1, sel(pg)])
        undo(pg)
        check("undo restores the pink", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"]["colour"] == "#FF0C84" for i in (A, H, S)) and sel(pg) is not None)
        # the spare slot on a selection
        pg.click("#tray .spec"); pg.wait_for_selector("#specPicker:not([hidden])")
        cell = pg.locator("#specPicker polygon[data-cell='3-2']"); cc = cell.get_attribute("data-colour")
        bb = cell.bounding_box(); pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        pg.click("#specPicker .done")
        check("the spare slot's pick recolours the selection too", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"]["colour"] == cc for i in (A, H, S))
              and pg.evaluate("window.__pw.tray()")["tool"] == "select" and sel(pg) is not None, cc)
        tool(pg, "eraser")
        check("any other tool change still clears the selection", sel(pg) is None)
        tool(pg, "select")
        pg.click("#tray .sw[data-colour='#2CB05F']")
        ts = pg.evaluate("window.__pw.tray()")
        check("a colour tap with select on and NO selection hands back the last ink tool (as before)", ts["tool"] == "pen" and ts["pen"]["colour"] == "#2CB05F", [ts["tool"], ts["pen"]])
        ctx.close()

        # ------------------------------------------------------------ pen button round: the plain pen always draws
        group[0] = "pen button"
        ctx, pg, e9 = fresh(b); errs += e9
        open_note(pg, "Handles")
        pen = Pen(ctx, pg)
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2"); d0 = dict(ln["data"]); u0 = U(pg)
        check("a line to work with", ln["kind"] == "shape" and ln["data"]["type"] == "line", ln["data"])
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        pen.stroke([(ex, ey), (ex + 80, ey + 40), (ex + 140, ey + 20)])
        s1 = strokes(pg, "p2")
        check("plain pen down ON the line's end draws a new stroke (count +1)", len(s1) == 2 and s1[-1]["kind"] == "pen", [x["kind"] for x in s1])
        check("... and the line is unchanged", [x for x in s1 if x["id"] == ln["id"]][0]["data"] == d0)
        check("... the new stroke starts at the end point", near(s1[-1]["data"]["points"][0], (d0["x2"], d0["y2"]), 1.5), s1[-1]["data"]["points"][:2])
        sx0, sy0 = screen(pg, 1, d0["x1"], d0["y1"])
        pen.stroke([(sx0 + 4, sy0 + 3), (sx0 - 60, sy0 + 50)])
        check("plain pen down 5 px from the start end draws too", len(strokes(pg, "p2")) == 3 and [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"] == d0)
        draw(pg, 1, [(d0["x1"], d0["y1"]), (d0["x1"] - 40, d0["y1"] + 80)], steps=4)
        check("the plain left mouse button on an end draws as well", len(strokes(pg, "p2")) == 4 and [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"] == d0)
        n = len(strokes(pg, "p2")); u1 = U(pg)
        L = lambda: [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"]
        # the button held from the hover on, then the tip touches the end: the spec's chorded move (button 0, buttons 3)
        pen.stroke([(ex + 4, ey + 2), (ex + 64, ey + 42)], bb=2)
        g1 = L()
        check("pen button held, tip down on the end: it grabs and moves (x2 +60, y2 +40)", abs(g1["x2"] - (d0["x2"] + 60)) <= 1.5 and abs(g1["y2"] - (d0["y2"] + 40)) <= 1.5 and g1["x1"] == d0["x1"], [d0, g1])
        check("... no new stroke, one undo step", len(strokes(pg, "p2")) == n and U(pg) == u1 + 1, [len(strokes(pg, "p2")), n, U(pg), u1])
        # a press of the button itself (pointerdown pen, button 2, buttons 2) on the end
        ex, ey = screen(pg, 1, g1["x2"], g1["y2"])
        pen.bstroke([(ex - 3, ey + 2), (ex - 53, ey + 2)])
        g2 = L()
        check("pointerdown pen with buttons 2 on the end grabs it (x2 -50)", abs(g2["x2"] - (g1["x2"] - 50)) <= 1.5 and abs(g2["y2"] - g1["y2"]) <= 1.5, [g1, g2])
        check("... no new stroke, one more undo step", len(strokes(pg, "p2")) == n and U(pg) == u1 + 2)
        undo(pg)
        check("undo puts that end back", L() == g1, [L(), g1])
        redo(pg)
        # away from any handle: a harmless miss, both ways
        fx, fy = screen(pg, 1, 600, 900)
        pen.bstroke([(fx, fy), (fx + 80, fy + 30)])
        check("pen button down away from any handle: nothing (no stroke, no change, no undo step)", len(strokes(pg, "p2")) == n and L() == g2 and U(pg) == u1 + 2)
        pen.stroke([(fx, fy + 60), (fx + 80, fy + 90)], bb=2)
        check("pen button held, tip down away from any handle: nothing either", len(strokes(pg, "p2")) == n and L() == g2 and U(pg) == u1 + 2)
        # the hover ring needs the button
        ring_on = lambda: pg.evaluate("(() => { const r = document.getElementById('handleRing'); return !!r && !r.hidden; })()")
        ex, ey = screen(pg, 1, g2["x2"], g2["y2"])
        pen.hover(ex + 10, ey); bare = ring_on()
        pen.hover(ex + 10, ey, 2); held = ring_on()
        pen.hover(ex + 10, ey)
        check("hovering near a handle with the button: the ring shows", held)
        check("hovering near a handle without the button: no ring", not bare)
        # the right mouse button grabs too
        grab_page(pg, 1, (g2["x2"] + 3, g2["y2"] - 2), (g2["x2"] + 3, g2["y2"] + 58))
        g3 = L()
        check("the right mouse button grabs the end (y2 +60)", abs(g3["y2"] - (g2["y2"] + 60)) <= 1.5 and abs(g3["x2"] - g2["x2"]) <= 1.5 and len(strokes(pg, "p2")) == n, [g2, g3])
        # the button let go mid-drag: the drag runs on until the pen lifts
        ex, ey = screen(pg, 1, g3["x2"], g3["y2"])
        pg.evaluate("""([x, y]) => { const fire = (t, x, y, b) => (document.elementFromPoint(x, y) || document.getElementById('desk')).dispatchEvent(new PointerEvent(t,
            { bubbles: true, cancelable: true, composed: true, pointerId: 9, pointerType: 'pen', isPrimary: true, clientX: x, clientY: y,
              button: t === 'pointermove' ? -1 : 0, buttons: b, pressure: b ? 0.5 : 0 }));
          fire('pointerdown', x, y, 3); fire('pointermove', x + 20, y, 3); fire('pointermove', x + 40, y, 1); fire('pointermove', x + 70, y, 1); fire('pointerup', x + 70, y, 0); }""", [ex, ey])
        g4 = L()
        check("button let go mid-drag: the end follows the pen to the lift (x2 +70)", abs(g4["x2"] - (g3["x2"] + 70)) <= 1.5 and len(strokes(pg, "p2")) == n, [g3, g4])
        # the CDP version: tip lifted while the button is still held ends the grab there
        pen.stroke([(screen(pg, 1, g4["x2"], g4["y2"])), (screen(pg, 1, g4["x2"], g4["y2"] - 30))], bb=2)
        g5 = L()
        check("button held, tip lifted: the grab ends at the lift (y2 -30)", abs(g5["y2"] - (g4["y2"] - 30)) <= 1.5 and len(strokes(pg, "p2")) == n, [g4, g5])
        # other tools ignore the button
        tool(pg, "eraser")
        a5, b5 = screen(pg, 1, 100, 550), screen(pg, 1, 700, 550)
        pg.mouse.move(*a5); pg.mouse.down(button="right"); pg.mouse.move(b5[0], b5[1], steps=12); pg.mouse.up(button="right"); pg.wait_for_timeout(40)
        check("the stroke eraser with the right button erases nothing (as before)", len(strokes(pg, "p2")) == n)
        tool(pg, "pen")
        # no context menu on the desk
        cm = pg.evaluate("""() => { const d = document.getElementById('desk'), s = d.querySelector('#stack .sheet');
          const fire = (el) => el.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, button: 2 }));
          return [fire(d), fire(s)]; }""")
        check("contextmenu on the desk and on a page is default-prevented", cm == [False, False], cm)
        pg.evaluate("() => { window.__cm = []; document.addEventListener('contextmenu', (e) => window.__cm.push(e.defaultPrevented)); }")
        grab_page(pg, 1, (600, 900), (610, 900))
        check("a real right click on the page: its contextmenu is default-prevented", pg.evaluate("window.__cm") == [True], pg.evaluate("window.__cm"))
        cmo = pg.evaluate("() => document.getElementById('backBtn').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }))")
        check("contextmenu outside the desk is left alone", cmo is True, cmo)
        check("no #dbg and no readout without ?dbg=1", pg.locator("#dbg").count() == 0 and pg.locator("#dbgCss").count() == 0)
        ctx.close()

        # the readout: off without the flag (no request at all), on with it
        ctx = b.new_context(viewport={"width": 1280, "height": 1300}); pg = ctx.new_page(); reqs = []; e10 = []
        pg.on("pageerror", lambda e: e10.append(str(e))); pg.on("request", lambda r: reqs.append(r.url))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg, "Handles")
        draw(pg, 1, [(200, 200), (300, 260)], steps=4); pg.wait_for_timeout(100)
        res_dbg = pg.evaluate("performance.getEntriesByType('resource').filter(e => e.name.includes('dbg')).length")
        check("no ?dbg=1: no #dbg element, no dbg.js request", pg.locator("#dbg").count() == 0 and not [u for u in reqs if "dbg.js" in u] and res_dbg == 0, [u for u in reqs if "dbg" in u])
        ctx.close(); errs += e10
        ctx, pg, e11 = fresh(b, url=LOCAL + "&dbg=1"); errs += e11
        open_note(pg, "Handles")
        pg.wait_for_selector("#dbg", state="attached", timeout=5000)
        info = pg.evaluate("""() => { const e = document.getElementById('dbg'), c = getComputedStyle(e), r = e.getBoundingClientRect(), d = document.getElementById('desk').getBoundingClientRect();
          return { pe: c.pointerEvents, font: c.fontSize, fam: c.fontFamily, left: r.left - d.left, bottom: d.bottom - r.bottom, parent: e.parentNode.id, bg: c.backgroundColor }; }""")
        check("?dbg=1: the #dbg box is on the desk, bottom-left, 11 px monospace, pointer-events none",
              info["parent"] == "desk" and info["pe"] == "none" and info["font"] == "11px" and "monospace" in info["fam"] and info["left"] < 20 and info["bottom"] < 20, info)
        pen = Pen(ctx, pg)
        n0 = len(strokes(pg, "p2"))
        a, b2 = screen(pg, 1, 200, 400), screen(pg, 1, 400, 480)
        pen.stroke([a, b2], steps=12)
        txt = pg.evaluate("document.getElementById('dbg').textContent").split("\n")
        check("a pen stroke still draws with the readout on", len(strokes(pg, "p2")) == n0 + 1)
        check("the readout shows at most 4 lines, the newest first: 'pointerup pen 0 0 0'", len(txt) <= 4 and txt[0] == "pointerup pen 0 0 0", txt)
        check("every line is 'type pointerType button buttons pressure'", all(re.fullmatch(r"(pointer\w+|contextmenu) \w+ -?\d+ \d+ (-|\d+(\.\d\d)?)", t) for t in txt), txt)
        check("a stroke's moves are collapsed (only a move whose buttons changed is shown)", sum(t.startswith("pointermove") for t in txt) <= 2, txt)
        pen.bstroke([b2, (b2[0] + 30, b2[1])])
        txt = pg.evaluate("document.getElementById('dbg').textContent").split("\n")
        check("the pen button shows: 'pointerdown pen 2 2 ...' then 'pointerup pen 2 0 ...'", any(t.startswith("pointerdown pen 2 2 ") for t in txt) and any(t.startswith("pointerup pen 2 0 ") for t in txt), txt)
        theme = pg.evaluate("""() => { const e = document.getElementById('dbg'), h = document.documentElement, o = h.dataset.theme;
          h.dataset.theme = 'light'; const l = getComputedStyle(e).color; h.dataset.theme = 'dark'; const d = getComputedStyle(e).color;
          if (o === undefined) delete h.dataset.theme; else h.dataset.theme = o; return [l, d]; }""")
        check("light text on the light theme's dark box, dark text on the dark theme's light box", theme[0] != theme[1] and theme[0] == "rgb(255, 255, 255)", theme)
        check("dbg.js is in the service worker shell list", "./js/dbg.js" in pg.evaluate("fetch('./sw.js').then(r => r.text())"))
        ctx.close()

        # ------------------------------------------------------------ pen button 2: pick up, follow, drop
        group[0] = "pen button 2"
        ctx, pg, e12 = fresh(b); errs += e12
        open_note(pg, "Handles")
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2"); d0 = dict(ln["data"])
        check("a line to work with", ln["kind"] == "shape" and ln["data"]["type"] == "line", ln["data"])
        L = lambda: [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"]
        CM = """([x, y, pt]) => { const el = document.elementFromPoint(x, y) || document.getElementById('desk');
          const o = { clientX: x, clientY: y, bubbles: true, cancelable: true };
          return el.dispatchEvent(pt ? new PointerEvent('contextmenu', { ...o, pointerType: pt }) : new MouseEvent('contextmenu', o)); }"""
        PE = """([t, x, y, b]) => (document.elementFromPoint(x, y) || document.getElementById('desk')).dispatchEvent(new PointerEvent(t,
          { bubbles: true, cancelable: true, composed: true, pointerId: 11, pointerType: 'pen', isPrimary: true, clientX: x, clientY: y,
            button: t === 'pointermove' ? -1 : 0, buttons: b, pressure: b ? 0.5 : 0 }))"""
        cmx = lambda x, y, pt=None: pg.evaluate(CM, [x, y, pt])
        pe = lambda t, x, y, bt=0: pg.evaluate(PE, [t, x, y, bt])
        fl = lambda: pg.evaluate("window.__pw.ink.floating()")
        ring = lambda: pg.evaluate("""(() => { const r = document.getElementById('handleRing'); if (!r || r.hidden) return null;
          const b = r.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; })()""")
        ex2 = lambda: pg.evaluate("""(id) => { const e = document.querySelector(`svg.ink [data-id="${id}"]`); return [+e.getAttribute('x2'), +e.getAttribute('y2')]; }""", ln["id"])
        n = len(strokes(pg, "p2")); u0 = U(pg)
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        ok = cmx(ex + 6, ey + 4)
        check("a press 7 px from the line's end: its contextmenu is default-prevented", ok is False, ok)
        f = fl()
        check("... the end is picked up (a float on that handle)", f is not None and f["id"] == ln["id"] and f["h"] == 1 and not f["touching"], f)
        r0 = ring()
        check("... the ring shows on the end itself", r0 is not None and near(r0, (ex, ey), 1.5), [r0, (ex, ey)])
        check("... no stroke, the shape unchanged, no undo step yet", len(strokes(pg, "p2")) == n and L() == d0 and U(pg) == u0)
        pe("pointermove", ex + 36, ey + 24); pe("pointermove", ex + 66, ey + 44)
        g = ex2()
        check("hover moves (buttons 0) carry the end along, offset kept (x2 +60, y2 +40)", near(g, (d0["x2"] + 60, d0["y2"] + 40), 1.0), [d0, g])
        r1 = ring(); tx, ty = screen(pg, 1, d0["x2"] + 60, d0["y2"] + 40)
        check("... the ring follows the end", r1 is not None and near(r1, (tx, ty), 1.5), [r1, (tx, ty)])
        check("... still floating, the record not written yet, no undo step", fl() is not None and L() == d0 and U(pg) == u0)
        pg.evaluate("() => { const d = document.getElementById('desk'); for (const t of ['pointerout', 'pointerleave']) d.dispatchEvent(new PointerEvent(t, { pointerId: 11, pointerType: 'pen' })); }")
        check("the pen leaving the desk (pointerleave / pointerout) does not drop, the ring stays", fl() is not None and ring() is not None)
        pe("pointerdown", ex + 66, ey + 44, 1); pe("pointermove", ex + 72, ey + 44, 1); pe("pointermove", ex + 76, ey + 44, 1)
        check("the pen touching while floating: still the float (touching), no stroke", (fl() or {}).get("touching") is True and len(strokes(pg, "p2")) == n, fl())
        pe("pointerup", ex + 76, ey + 44, 0)
        g1 = L()
        check("touch and lift drops it there (x2 +70, y2 +40)", fl() is None and near((g1["x2"], g1["y2"]), (d0["x2"] + 70, d0["y2"] + 40), 1.0) and g1["x1"] == d0["x1"], [d0, g1])
        check("... stroke count unchanged, ONE undo step, the ring gone", len(strokes(pg, "p2")) == n and U(pg) == u0 + 1 and ring() is None, [len(strokes(pg, "p2")), U(pg)])
        idle(pg)
        check("... and it is saved", [x for x in stored(pg, "p2") if x["id"] == ln["id"]][0]["data"] == g1)
        undo(pg)
        check("undo puts the old end back", L() == d0, [L(), d0])
        redo(pg)
        check("redo moves it again", L() == g1)
        # a second press drops instead
        ex, ey = screen(pg, 1, g1["x2"], g1["y2"])
        cmx(ex - 3, ey + 2); pe("pointermove", ex - 23, ey + 2); pe("pointermove", ex - 43, ey + 2)
        cmx(*screen(pg, 1, 650, 1000))
        g2 = L()
        check("a second press (anywhere) drops it where it is (x2 -40)", fl() is None and near((g2["x2"], g2["y2"]), (g1["x2"] - 40, g1["y2"]), 1.0), [g1, g2])
        check("... one more undo step, no stroke", U(pg) == u0 + 2 and len(strokes(pg, "p2")) == n)
        pe("pointermove", ex + 100, ey + 100)
        check("... and later hover moves leave it alone", L() == g2)
        # a press away from any handle: nothing at all, and the next touch draws
        fx, fy = screen(pg, 1, 600, 900)
        cmx(fx, fy)
        check("a press away from any handle does nothing (no float, no ring)", fl() is None and ring() is None and U(pg) == u0 + 2)
        pg.evaluate(SYNTH_JS, [[(fx, fy), (fx + 40, fy + 20), (fx + 80, fy + 30)], 0])
        s3 = strokes(pg, "p2")
        check("... the next pen touch draws as normal (count +1)", len(s3) == n + 1 and s3[-1]["kind"] == "pen" and L() == g2, [x["kind"] for x in s3])
        n += 1; u1 = U(pg)
        # picked up, never moved: nothing recorded
        ex, ey = screen(pg, 1, g2["x2"], g2["y2"])
        cmx(ex + 2, ey); pe("pointerdown", ex + 2, ey, 1); pe("pointerup", ex + 2, ey, 0)
        check("picked up and put down without moving: no undo step, no stroke", fl() is None and U(pg) == u1 and L() == g2 and len(strokes(pg, "p2")) == n)
        # a tool change while floating drops it
        cmx(ex + 2, ey); pe("pointermove", ex + 2, ey + 25)
        tool(pg, "eraser")
        g3 = L()
        check("a tool change while floating drops it where it is (y2 +25)", fl() is None and near((g3["x2"], g3["y2"]), (g2["x2"], g2["y2"] + 25), 1.0) and U(pg) == u1 + 1, [g2, g3])
        ex, ey = screen(pg, 1, g3["x2"], g3["y2"])
        cmx(ex, ey)
        check("with the eraser on, a press near the end does nothing", fl() is None and ring() is None)
        tool(pg, "pen")
        # Escape drops; undo while floating takes the move back
        cmx(ex, ey); pe("pointermove", ex + 15, ey)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(20)
        g4 = L()
        check("Escape drops it where it is (x2 +15)", fl() is None and near((g4["x2"], g4["y2"]), (g3["x2"] + 15, g3["y2"]), 1.0) and U(pg) == u1 + 2, [g3, g4])
        ex, ey = screen(pg, 1, g4["x2"], g4["y2"])
        cmx(ex, ey); pe("pointermove", ex, ey - 30)
        undo(pg)
        check("undo while floating: dropped first, so the undo takes that move back", fl() is None and L() == g4 and U(pg) == u1 + 2, [L(), g4, U(pg)])
        # a finger never picks up
        cmx(ex, ey, "touch")
        check("a finger's long press (contextmenu, pointerType touch) does not pick up", fl() is None)
        # the laptop: a right-mouse grab still works once, its own contextmenu does not grab again
        pg.evaluate("() => { window.__cm = []; document.addEventListener('contextmenu', (e) => window.__cm.push(e.defaultPrevented)); }")
        u2 = U(pg)
        grab_page(pg, 1, (g4["x2"] + 3, g4["y2"] - 2), (g4["x2"] + 3, g4["y2"] + 48))
        g5 = L()
        check("the right mouse button grabs and drags the end once (y2 +50)", abs(g5["y2"] - (g4["y2"] + 50)) <= 1.5 and abs(g5["x2"] - g4["x2"]) <= 1.5 and U(pg) == u2 + 1, [g4, g5, U(pg) - u2])
        check("... its contextmenu fired, was prevented, and started no float (no double grab)", pg.evaluate("window.__cm") == [True] and fl() is None and ring() is None, [pg.evaluate("window.__cm"), fl()])
        px, py = screen(pg, 1, g5["x2"] + 40, g5["y2"] + 40)
        pe("pointermove", px, py); pg.mouse.move(px, py)
        check("... and later moves leave the end alone", L() == g5 and len(strokes(pg, "p2")) == n)
        check("no page errors in this group", not e12, e12)
        ctx.close()
        # the readout stays and logs the press
        ctx, pg, e13 = fresh(b, url=LOCAL + "&dbg=1"); errs += e13
        open_note(pg, "Handles")
        pg.wait_for_selector("#dbg", state="attached", timeout=5000)
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2"); d0 = dict(ln["data"]); u0 = U(pg)
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        cmx(ex, ey)
        txt = pg.evaluate("document.getElementById('dbg').textContent").split("\n")
        check("?dbg=1: the box is there and logs the press as a contextmenu line", txt[0].startswith("contextmenu "), txt)
        pe("pointermove", ex + 30, ey); pe("pointerdown", ex + 30, ey, 1); pe("pointerup", ex + 30, ey, 0)
        g = [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"]
        check("... and the pick up, follow and drop work with the readout on (x2 +30)", abs(g["x2"] - (d0["x2"] + 30)) <= 1.0 and U(pg) == u0 + 1, [d0, g])
        ctx.close()

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        ctx, pg, e7 = fresh(b); errs += e7
        check("cache is pw-v4d", "pw-v4d" in pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())"), pg.evaluate("caches.keys()"))
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/ink.js", "./js/tray.js", "./js/page.js", "./js/app.js", "./js/dbg.js", "./css/app.css", "./sw.js"])
        check("no em-dashes in the code", chr(0x2014) not in srcs)
        check("no shape menu or shape tool in the tray", pg.locator("#tray [data-tool='shape'], #tray [data-tool='shapes']").count() == 0)
        check("no page errors", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:400]}")
print()
for line_ in info_lines: print(line_)
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
