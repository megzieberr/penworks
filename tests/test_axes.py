# PenWorks U5e checks (pw-v8f, tools round 3, second half): the AXES stamp (briefs/U5-TOOLS-DESIGN.md and
# _build/U5E-AXES-BRIEF.md).
# Run: python tests/test_axes.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800 (the tablet landscape size), the way
# tests/test_protractor.py does. Pen gestures are PointerEvents (pointerType 'pen') fired on the desk; fingers are touch
# PointerEvents on the desk. The PDF is read with PyMuPDF.
# What it proves: the Axes row is live and opens the settings card beside the panel (the panel stays open); the defaults
# (-5, 5, 1 twice, both ticks off); Degrees sets x to 0, 360, 90 and back; Number line greys the y fields; a bad range
# reddens its fields, says why and Place lands nothing; a press on the page keeps the card; X, Escape and the panel close
# it; Place lands ONE 'axes' record on the current page in the pen's colour, 1.5 px, centred in the view, px = py = min(0.7 Wv /
# 10, 0.7 Hv / 10, 2 cm) (Wv, Hv: the part of the page she sees), a degrees stamp's px != py; its <g> (2 axis lines, 20 ticks, 2 heads, x and y, 21 numbers); degrees labels; a number line; the
# settings survive a reload (localStorage pw.axes); Select picks it up by tap and by a box, moves it, resizes it (p and the
# fonts x s), a turn leaves it as it was; the stroke eraser removes it whole, undo brings it back; it is in the page thumb;
# the PDF has its lines and its numbers as text; the ruler's edge sticks to its origin and the compass needle to a tick end.
# Screenshots go to _build/shots-axes/.
import sys, subprocess, time, pathlib, math, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8804
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-axes"
CM = 96 / 2.54
W, H = 794, 1123
BLUE = "#0D0DFF"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-02T08:00:00Z', pages = [];
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
    buttons: buttons !== undefined ? buttons : type === 'pointerup' ? 0 : 1, clientX: x, clientY: y,
    screenX: x + 10, screenY: y + 80 }));   // pw-v8m: a constant screen-minus-client gap, as a real pen has (pw-v8l penGap reads it; 0 made the view jump)
  T.R = () => window.__TL.rulerState();
  T.C = () => window.__TL.compassState();
  T.local = (lx, ly) => { const s = T.R(), u = [Math.cos(s.ang), Math.sin(s.ang)], n = [-u[1], u[0]];
    return [s.o[0] + u[0] * lx + n[0] * ly, s.o[1] + u[1] * lx + n[1] * ly]; };
  T.pen = (id, pts, up = true, pid = 31, kind = 'pen') => {
    const c = pts.map((p) => (id ? T.client(id, p[0], p[1]) : p));
    T.ev('pointerdown', pid, kind, c[0][0], c[0][1]);
    for (const q of c.slice(1)) T.ev('pointermove', pid, kind, q[0], q[1]);
    if (up) T.ev('pointerup', pid, kind, c[c.length - 1][0], c[c.length - 1][1]);
  };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.clear = (id) => { const op = window.__pw.ink.erasePageOp(id); if (op) op.redo(); };
  T.geo = (id) => { const r = T.recs('s0').find((x) => x.id === id); return r ? window.__pw.ink.axesGeom(r) : null; };
  T.el = (id) => { const g = T.sheet('s0').querySelector(`svg.ink [data-id="${id}"]`); if (!g) return null;
    const tx = (sel) => [...g.querySelectorAll(sel)];
    return { tag: g.tagName, type: g.dataset.type, group: g.parentNode.getAttribute('class'), stroke: g.getAttribute('stroke'), width: g.getAttribute('stroke-width'),
      axis: tx('line.axis').length, tick: tx('line.tick').length, head: tx('path.head').length,
      letters: tx('text.letter').map((t) => [t.textContent, t.getAttribute('font-style'), +t.getAttribute('font-size')]),
      nums: tx('text.num').map((t) => t.textContent), zero: tx('text.zero').map((t) => t.textContent),
      numSize: tx('text.num').map((t) => +t.getAttribute('font-size')), fills: [...new Set(tx('text').map((t) => t.getAttribute('fill')))],
      tstroke: [...new Set(tx('text').map((t) => t.getAttribute('stroke')))] }; };
  T.vis = (idx) => { const b = document.getElementById('desk').getBoundingClientRect(), a = window.__P.pagePoint(idx, b.left, b.top), c = window.__P.pagePoint(idx, b.right, b.bottom);
    const cx = (v) => Math.max(0, Math.min(794, v)), cy = (v) => Math.max(0, Math.min(1123, v));
    return [cx(a[0]), cy(a[1]), cx(c[0]), cy(c[1])]; };   // the part of page 1 she sees, page px
  return 1;
}"""
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
  return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height, shown: !e.hidden && b.width > 0 }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def rect(pg, sel): return pg.evaluate(RECT, sel)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def R(pg): return pg.evaluate("window.__T.R()")
def C(pg): return pg.evaluate("window.__T.C()")
def z(pg): return pg.evaluate("window.__T.z()")
def recs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.recs(id)", pid)
def axes_recs(pg, pid="s0"): return [r for r in recs(pg, pid) if r["kind"] == "axes"]
def el(pg, i): return pg.evaluate("(i) => window.__T.el(i)", i)
def geo(pg, i): return pg.evaluate("(i) => window.__T.geo(i)", i)
def local(pg, lx, ly): return pg.evaluate("([a, b]) => window.__T.local(a, b)", [lx, ly])
def pen(pg, pts, up=True, page="s0", kind="pen"): pg.evaluate("([id, p, up, k]) => window.__T.pen(id, p, up, 31, k)", [page, pts, up, kind])
def pen_up(pg, p, page="s0"):
    pg.evaluate("([id, p]) => { const c = window.__T.client(id, p[0], p[1]); window.__T.ev('pointerup', 31, 'pen', c[0], c[1]); }", [page, p])
def finger(pg, kind, pid, x, y):
    pg.evaluate("([t, i, x, y]) => window.__T.ev(t, i, 'touch', x, y)", [kind, pid, x, y])
def addv(a, b): return [a[0] + b[0], a[1] + b[1]]
def subv(a, b): return [a[0] - b[0], a[1] - b[1]]
def lerp(a, b, t): return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def open_panel(pg):
    if pg.locator("#toolsPanel").is_hidden(): pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
def toggle(pg, tool):
    open_panel(pg); pg.click(f"#trow-{tool}"); pg.wait_for_timeout(60)
def close_panel(pg): pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
def open_card(pg):
    open_panel(pg)
    if pg.locator("#axesCard").count() == 0 or pg.locator("#axesCard").is_hidden(): pg.click("#trow-axes"); pg.wait_for_timeout(60)
def card_shown(pg): return pg.locator("#axesCard").count() > 0 and pg.locator("#axesCard").is_visible()
def panel_shown(pg): return pg.locator("#toolsPanel").is_visible()
FIELDS = ["xs", "xe", "xd", "ys", "ye", "yd"]
def vals(pg): return [pg.input_value(f"#ax-{k}") for k in FIELDS]
def bads(pg): return [k for k in FIELDS if pg.evaluate("(k) => document.getElementById('ax-' + k).classList.contains('bad')", k)]
def msg(pg): return pg.text_content("#axesMsg")
def set_fields(pg, v):
    for k, x in zip(FIELDS, v): pg.fill(f"#ax-{k}", str(x))
def ticks(pg): return [pg.is_checked("#ax-deg"), pg.is_checked("#ax-line")]
def set_tick(pg, sel, on):
    if pg.is_checked(sel) != on: pg.click(sel); pg.wait_for_timeout(30)
def place(pg): pg.click("#axesPlace"); pg.wait_for_timeout(80)
def pdf_of(pg, name):
    b64 = pg.evaluate("""async (n) => { const m = await import('./js/pdfout.js');
      const blob = await m.buildPdf([{ id: 's0', orientation: 'portrait', background: 'blank', pdf_path: null }], n);
      const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode(...b.subarray(i, i + 8192));
      return btoa(s); }""", name)
    return fitz.open(stream=base64.b64decode(b64), filetype="pdf")
def show(pg, p, page="s0"):
    """scroll the stack (a plain wheel) so page point p sits in the middle of the desk"""
    pg.evaluate("""([id, p]) => { const c = window.__T.client(id, p[0], p[1]);
      const d = document.getElementById('desk'), b = d.getBoundingClientRect();
      d.dispatchEvent(new WheelEvent('wheel', { deltaY: c[1] - (b.top + b.height / 2), clientX: b.left + 200, clientY: b.top + 200, bubbles: true, cancelable: true })); }""", [page, p])
    pg.wait_for_timeout(80)
def rotate(p, c, deg):
    a = math.radians(deg); dx, dy = p[0] - c[0], p[1] - c[1]
    return [c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a)]

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
        pg.click(f'#tray .sw[data-colour="{BLUE}"]'); pg.wait_for_timeout(40)   # the pen in Blue (not the default Black)

        # ------------------------------------------------------------ A: the row and the card
        group[0] = "A. row + card"
        open_panel(pg)
        row = pg.evaluate("(() => { const b = document.getElementById('trow-axes'); return [b.textContent.trim(), b.disabled, b.title, b.getAttribute('aria-pressed'), b.getAttribute('aria-expanded')]; })()")
        check("the Axes row reads 'Axes…', is live (no 'Next round'), no toggle (no aria-pressed), aria-expanded false",
              row == ["Axes…", False, "", None, "false"], row)
        pg.click("#trow-axes"); pg.wait_for_timeout(60)
        cr, pr, rr = rect(pg, "#axesCard"), rect(pg, "#toolsPanel"), rect(pg, "#trow-axes")
        check("a tap opens the card; the panel stays open behind it; the row says aria-expanded true",
              card_shown(pg) and panel_shown(pg) and pg.get_attribute("#trow-axes", "aria-expanded") == "true")
        check("the card is not a dialog (role group, labelled 'Axes settings')",
              pg.get_attribute("#axesCard", "role") == "group" and pg.get_attribute("#axesCard", "aria-label") == "Axes settings")
        check("right tray: it sits beside the panel on the desk side (8 px left of it), level with the Axes row, on screen",
              abs(cr["r"] - (pr["l"] - 8)) < 1 and cr["t"] <= rr["t"] + rr["h"] / 2 <= cr["b"] and cr["l"] >= 8 and cr["b"] <= 800 - 8 + 0.5, [cr, pr, rr])
        check("the defaults: -5, 5, 1 for x and for y, Degrees and Number line off, no message",
              vals(pg) == ["-5", "5", "1", "-5", "5", "1"] and ticks(pg) == [False, False] and msg(pg) == "" and bads(pg) == [], [vals(pg), ticks(pg), msg(pg)])
        fs = pg.evaluate("[...document.querySelectorAll('#axesCard input.axNum')].map((f) => [f.type, f.step, f.getAttribute('inputmode'), Math.round(f.getBoundingClientRect().width), Math.round(f.getBoundingClientRect().height)])")
        check("six number fields (type number, step any, NO inputmode: a number pad with - and .), 56 x 40 px (pw-v8m)", len(fs) == 6 and all(f == ["number", "any", None, 56, 40] for f in fs), fs)
        tk = pg.evaluate("[...document.querySelectorAll('#axesCard .axTick input')].map((c) => [c.id, Math.round(c.getBoundingClientRect().width)])")
        check("two ticks of 24 px: Degrees and Number line", tk == [["ax-deg", 24], ["ax-line", 24]], tk)
        set_tick(pg, "#ax-deg", True)
        check("ticking Degrees sets x to 0, 360, 90 (y stays)", vals(pg) == ["0", "360", "90", "-5", "5", "1"], vals(pg))
        set_tick(pg, "#ax-deg", False)
        check("unticking it puts -5, 5, 1 back", vals(pg) == ["-5", "5", "1", "-5", "5", "1"], vals(pg))
        set_tick(pg, "#ax-line", True)
        gy = pg.evaluate("[['ys','ye','yd'].map((k) => document.getElementById('ax-' + k).disabled), document.querySelector('#axesCard .axRow[data-axis=\"y\"]').classList.contains('off'), ['xs','xe','xd'].map((k) => document.getElementById('ax-' + k).disabled)]")
        check("ticking Number line greys the y line (its fields disabled), x stays live", gy == [[True, True, True], True, [False, False, False]], gy)
        set_tick(pg, "#ax-line", False)
        check("unticked, the y line is live again", pg.evaluate("['ys','ye','yd'].every((k) => !document.getElementById('ax-' + k).disabled)"))
        n0 = len(recs(pg))
        pg.fill("#ax-xs", "5"); pg.wait_for_timeout(20)
        check("start = end (5 to 5): start and end go red, the line says 'Start must be smaller than End'",
              bads(pg) == ["xs", "xe"] and msg(pg) == "Start must be smaller than End", [bads(pg), msg(pg)])
        place(pg)
        check("... and Place lands nothing (the card stays)", len(recs(pg)) == n0 and card_shown(pg))
        pg.fill("#ax-xs", "-5"); pg.fill("#ax-yd", "0"); pg.wait_for_timeout(20)
        check("step 0: the step goes red, 'Step must be more than 0'", bads(pg) == ["yd"] and msg(pg) == "Step must be more than 0", [bads(pg), msg(pg)])
        place(pg)
        check("... Place lands nothing", len(recs(pg)) == n0)
        pg.fill("#ax-yd", "1"); set_fields(pg, [0, 61, 1, -5, 5, 1]); pg.wait_for_timeout(20)
        check("0 to 61 step 1 (61 steps): the step goes red, 'Too many steps (60 at most)'", bads(pg) == ["xd"] and msg(pg) == "Too many steps (60 at most)", [bads(pg), msg(pg)])
        place(pg)
        check("... Place lands nothing", len(recs(pg)) == n0)
        pg.fill("#ax-xe", "60"); pg.wait_for_timeout(20)
        check("0 to 60 step 1 (60 steps) is fine: nothing red, no message", bads(pg) == [] and msg(pg) == "", [bads(pg), msg(pg)])
        set_fields(pg, [-5, 5, 1, -5, 5, 1])
        d = rect(pg, "#desk")
        finger(pg, "pointerdown", 61, d["l"] + 300, d["t"] + 300); finger(pg, "pointerup", 61, d["l"] + 300, d["t"] + 300); pg.wait_for_timeout(50)
        check("a press on the page does NOT close the card (nor the panel behind it)", card_shown(pg) and panel_shown(pg))
        pg.click("#axesClose"); pg.wait_for_timeout(40)
        check("its X closes the card; the panel stays", not card_shown(pg) and panel_shown(pg) and pg.get_attribute("#trow-axes", "aria-expanded") == "false")
        open_card(pg); close_panel(pg)
        check("Escape closes the card and the panel", not card_shown(pg) and not panel_shown(pg))
        open_card(pg); pg.click("#drawToolsBtn"); pg.wait_for_timeout(40)
        check("closing the panel (its button) closes the card", not card_shown(pg) and not panel_shown(pg))
        open_card(pg); pg.click("#tool-pen"); pg.wait_for_timeout(40)
        check("a tap on another tray button closes both", not card_shown(pg) and not panel_shown(pg))
        check("nothing landed from any of it", len(recs(pg)) == n0)

        # ------------------------------------------------------------ B: Place
        group[0] = "B. place"
        open_card(pg)
        vis = pg.evaluate("window.__T.vis(0)"); Wv, Hv = vis[2] - vis[0], vis[3] - vis[1]; mid = [(vis[0] + vis[2]) / 2, (vis[1] + vis[3]) / 2]
        place(pg)
        ax = axes_recs(pg)
        check("Place lands exactly ONE record, kind 'axes', on the current page (page 1); the card closes, the panel stays",
              len(recs(pg)) == n0 + 1 and len(ax) == 1 and ax[0]["page_id"] == "s0" and not card_shown(pg) and panel_shown(pg), [len(recs(pg)), ax])
        a = ax[0]; dd = a["data"]; aid = a["id"]
        check("style: the pen's colour (Blue), width 1.5, solid, opacity 1",
              a["style"] == {"colour": BLUE, "width": 1.5, "dash": "solid", "opacity": 1}, a["style"])
        pexp = min(0.7 * Wv / 10, 0.7 * Hv / 10, 2 * CM)
        check("px = py = min(0.7 Wv / 10, 0.7 Hv / 10, 2 cm) over the part of the page she sees (square squares)",
              abs(dd["px"] - pexp) < 0.006 and dd["py"] == dd["px"], [dd["px"], dd["py"], pexp, Wv, Hv])
        check("data carries the ranges, steps and ticks: -5, 5, 1 twice, deg and line false",
              [dd[k] for k in FIELDS] == [-5, 5, 1, -5, 5, 1] and dd["deg"] is False and dd["line"] is False, dd)
        check("centred in the view: the origin (the ranges' middle) is the middle of the part of the page she sees", abs(dd["x0"] - mid[0]) < 0.006 and abs(dd["y0"] - mid[1]) < 0.006, [dd, mid])
        e = el(pg, aid)
        check("drawn as a <g data-type=axes> in the pen group, stroked in Blue at 1.5",
              e and e["tag"] == "g" and e["type"] == "axes" and e["group"] == "pen" and e["stroke"] == BLUE and e["width"] == "1.5", e)
        check("2 axis lines, 20 tick lines (10 + 10), 2 heads", e["axis"] == 2 and e["tick"] == 20 and e["head"] == 2, e)
        check("the letters x and y, italic, font 0.32 p", [l[0] for l in e["letters"]] == ["x", "y"] and all(l[1] == "italic" and abs(l[2] - 0.32 * dd["px"]) < 0.01 for l in e["letters"]), e["letters"])
        want = [str(v) for v in range(-5, 6) if v] * 2 + ["0"]
        check("21 numbers: -5 .. 5 without 0 on each axis, the shared 0 once", sorted(e["nums"]) == sorted(want) and e["zero"] == ["0"] and e["nums"].count("0") == 1, e["nums"])
        check("numbers 0.3 p, filled in Blue, no stroke", all(abs(s - 0.3 * dd["px"]) < 0.01 for s in e["numSize"]) and e["fills"] == [BLUE] and e["tstroke"] == ["none"], [e["numSize"][:2], e["fills"], e["tstroke"]])
        g = geo(pg, aid)
        zl = [l for l in g["labels"] if l["cls"] == "num zero"][0]
        check("the shared 0 sits below left of the origin", zl["x"] < dd["x0"] and zl["y"] > dd["y0"], zl)
        xl = [l for l in g["labels"] if l["cls"] == "num" and l["anchor"] == "middle"]; yl = [l for l in g["labels"] if l["cls"] == "num" and l["anchor"] == "end"]
        check("x numbers centred under the x-axis, y numbers right-aligned left of the y-axis",
              len(xl) == 10 and all(l["y"] > dd["y0"] for l in xl) and len(yl) == 10 and all(abs(l["x"] - (dd["x0"] - 0.35 * dd["px"])) < 1e-6 for l in yl), [xl[:1], yl[:1]])
        th = pg.evaluate("(i) => { const s = window.__pw.ink.thumbSvg('s0'), g = s.querySelector(`g[data-id=\"${i}\"]`); return g ? [g.dataset.type, g.querySelectorAll('line.axis').length, g.querySelectorAll('text').length] : null; }", aid)
        check("it is in the page's thumb (thumbSvg has the <g>, its lines and its labels)", th == ["axes", 2, 23], th)
        fm = pg.evaluate("() => window.__pw.ink.axesGeom({ style: { width: 1.5 }, data: { x0: 300, y0: 300, px: 60, py: 60, xs: -1, xe: 1, xd: 0.5, ys: -1, ye: 1, yd: 0.25, deg: false, line: false } }).labels.filter((l) => l.cls !== 'letter').map((l) => l.t)")
        check("numbers keep up to 2 decimals, trailing zeros dropped (-0.5, 0.25, 1)", "-0.5" in fm and "0.5" in fm and "-0.25" in fm and "0.75" in fm and "1" in fm and "-1" in fm and "0" in fm, fm)
        close_panel(pg)
        show(pg, [dd["x0"], dd["y0"]])
        open_card(pg)
        pg.screenshot(path=str(SHOTS / "u5e-axes.png"))
        close_panel(pg)

        # ------------------------------------------------------------ C: Select
        group[0] = "C. select"
        zz = z(pg)
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        tapat = [dd["x0"] + 2.5 * dd["px"], dd["y0"]]                   # on the x-axis, between two ticks
        pen(pg, [tapat]); pg.wait_for_timeout(40)
        sel = pg.evaluate("window.__pw.ink.selection()")
        check("Select picks it up by a tap on an axis line", sel and sel["ids"] == [aid], sel)
        pg.evaluate("window.__pw.ink.clearSelection()")
        bx = g["box"]
        pen(pg, [[bx[0] - 20, bx[1] - 20], [(bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2], [bx[2] + 20, bx[3] + 20]]); pg.wait_for_timeout(40)
        sel = pg.evaluate("window.__pw.ink.selection()")
        check("... and by a box over it", sel and sel["ids"] == [aid], sel)
        pg.evaluate("window.__pw.ink.clearSelection()")
        pen(pg, [[dd["x0"] - 30, dd["y0"] - 30], [dd["x0"] + 30, dd["y0"] + 30]]); pg.wait_for_timeout(40)
        sel = pg.evaluate("window.__pw.ink.selection()")
        check("a small box over the origin only (no axis end inside) still takes it (the axes cross the box)", sel and sel["ids"] == [aid], sel)
        pg.evaluate("window.__pw.ink.clearSelection()")
        pen(pg, [[dd["x0"] + 0.5 * dd["px"], dd["y0"] - 1.5 * dd["px"]], [dd["x0"] + 4.5 * dd["px"], dd["y0"] - 4.5 * dd["px"]]]); pg.wait_for_timeout(40)
        check("a box inside one quarter (her graph's place, no axis line) does not take it", pg.evaluate("window.__pw.ink.selection()") is None, pg.evaluate("window.__pw.ink.selection()"))
        pen(pg, [tapat]); pg.wait_for_timeout(40)
        pen(pg, [tapat, addv(tapat, [20, 15]), addv(tapat, [40, 30])]); pg.wait_for_timeout(60)
        a1 = axes_recs(pg)[0]; d1 = a1["data"]
        check("a move shifts x0, y0 by the drag (40, 30); p, ranges unchanged; still ONE record",
              len(axes_recs(pg)) == 1 and abs(d1["x0"] - dd["x0"] - 40) < 0.011 and abs(d1["y0"] - dd["y0"] - 30) < 0.011 and d1["px"] == dd["px"]
              and [d1[k] for k in FIELDS] == [dd[k] for k in FIELDS], [dd, d1])
        sb = pg.evaluate("window.__pw.ink.selection()")["box"]; pad = 4 / zz             # the dashed box: the strokes' box plus 4 px (screen)
        o, c = [sb[0] - pad, sb[1] - pad], [sb[2] + pad, sb[3] + pad]
        u = subv(c, o); L = math.hypot(*u); u = [u[0] / L, u[1] / L]
        st = addv(c, [u[0] * 5 / zz, u[1] * 5 / zz]); s = 1.25
        pen(pg, [st, addv(st, [(c[0] - o[0]) * (s - 1) / 2, (c[1] - o[1]) * (s - 1) / 2]), addv(st, [(c[0] - o[0]) * (s - 1), (c[1] - o[1]) * (s - 1)])]); pg.wait_for_timeout(60)
        a2 = axes_recs(pg)[0]; d2 = a2["data"]; e2 = el(pg, a2["id"])
        exp0 = [o[0] + (d1["x0"] - o[0]) * s, o[1] + (d1["y0"] - o[1]) * s]
        check("a corner resize multiplies px and py by s (1.25) and carries the origin about the opposite corner",
              abs(d2["px"] / d1["px"] - s) < 0.001 and abs(d2["py"] / d1["py"] - s) < 0.001 and dist([d2["x0"], d2["y0"]], exp0) < 0.02, [d1, d2, exp0])
        check("... the font sizes follow p by the same s", all(abs(x - 0.3 * d2["px"]) < 0.01 for x in e2["numSize"]) and all(abs(l[2] - 0.32 * d2["px"]) < 0.01 for l in e2["letters"])
              and abs(e2["numSize"][0] / e["numSize"][0] - s) < 0.002, [e["numSize"][0], e2["numSize"][0]])
        rot = pg.evaluate("(() => { const k = document.querySelector('#stack svg.ink circle.selrot'); return k ? [+k.getAttribute('cx'), +k.getAttribute('cy')] : null; })()")
        sb = pg.evaluate("window.__pw.ink.selection()")["box"]; cc = [(sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2]
        before = axes_recs(pg)[0]
        pen(pg, [rotate(rot, cc, k * 6) for k in range(11)]); pg.wait_for_timeout(60)
        after = axes_recs(pg)[0]
        check("a turn (60 degrees on the ring) leaves the axes record exactly as it was (data and seq)",
              rot is not None and after == before, [rot, before["data"], after["data"], before["seq"], after["seq"]])
        pg.evaluate("window.__pw.ink.clearSelection()")
        check("handles(): none for an axes record (no reshape handles)", pg.evaluate("(r) => window.__pw.ink.handles(r).length", after) == 0)

        # ------------------------------------------------------------ D: erasers and undo
        group[0] = "D. eraser + undo"
        pg.click("#tool-eraser"); pg.wait_for_timeout(40)
        dA = after["data"]; yax = [dA["x0"], dA["y0"] - 2.5 * dA["px"]]
        pen(pg, [addv(yax, [-15, 0]), yax, addv(yax, [15, 0])]); pg.wait_for_timeout(60)
        check("the stroke eraser across the y-axis removes it WHOLE (no ink pieces left)", recs(pg) == [], recs(pg))
        pg.click("#undoBtn"); pg.wait_for_timeout(60)
        back = recs(pg)
        check("undo brings it back exactly", len(back) == 1 and back[0]["id"] == after["id"] and back[0]["data"] == after["data"] and el(pg, after["id"]) is not None, back)
        pg.click("#tool-area"); pg.wait_for_timeout(40)
        pen(pg, [addv(yax, [-15, 0]), yax, addv(yax, [15, 0])]); pg.wait_for_timeout(60)
        check("the area eraser removes it whole too (never cut into ink)", recs(pg) == [], recs(pg))
        pg.click("#undoBtn"); pg.wait_for_timeout(60)
        check("undo again: back", len(recs(pg)) == 1 and recs(pg)[0]["kind"] == "axes")
        pg.click("#tool-pen"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ E: the PDF
        group[0] = "E. PDF"
        pg.evaluate("window.__T.clear('s0')"); open_card(pg); place(pg); close_panel(pg)   # a fresh default stamp, all of it on the page
        doc = pdf_of(pg, "Axes")
        drs = doc[0].get_drawings(); txt = doc[0].get_text()
        nlines = sum(1 for dr in drs for it in dr["items"] if it[0] == "l")
        words = txt.split()
        check("Share as PDF carries the axis lines, ticks and heads as stroked paths (get_drawings finds them)", len(drs) >= 1 and nlines >= 2 + 20, [len(drs), nlines])
        check("... and the labels as TEXT: '-5', '5', 'x' and 'y' among the words", "-5" in words and "5" in words and "x" in words and "y" in words, words)
        fonts = sorted({f[3] for f in doc[0].get_fonts()})
        check("... in Helvetica and Helvetica-Oblique", any("Helvetica" == f or f.endswith("Helvetica") for f in fonts) and any("Oblique" in f for f in fonts), fonts)
        k = doc[0].rect.width / W; blk = doc[0].get_text("dict")
        spans = [sp for bl in blk["blocks"] for ln in bl.get("lines", []) for sp in ln["spans"]]
        s5 = [sp for sp in spans if sp["text"].strip() == "-5"]
        dA = recs(pg)[0]["data"]
        check("... at the screen's size x k (0.3 p x k pt)", s5 and all(abs(sp["size"] - 0.3 * dA["px"] * k) < 0.05 for sp in s5), [sp["size"] for sp in s5])
        doc.close()

        # ------------------------------------------------------------ F: degrees, number line
        group[0] = "F. degrees + number line"
        pg.evaluate("window.__T.clear('s0')"); pg.wait_for_timeout(40)
        open_card(pg); set_tick(pg, "#ax-deg", True)
        vis = pg.evaluate("window.__T.vis(0)"); Wv, Hv = vis[2] - vis[0], vis[3] - vis[1]
        place(pg)
        dg = axes_recs(pg)
        e3 = el(pg, dg[0]["id"]) if dg else None
        xs3 = [t for t in (e3["nums"] if e3 else []) if t.endswith("°")]
        check("a degrees stamp: data deg true, x 0 to 360 step 90", len(dg) == 1 and dg[0]["data"]["deg"] is True and [dg[0]["data"][k] for k in ("xs", "xe", "xd")] == [0, 360, 90], dg)
        check("... its x labels end in ° (90°, 180°, 270°, 360°) and the origin's shared 0 reads plain '0'",
              e3 and sorted(xs3) == sorted(["90°", "180°", "270°", "360°"]) and e3["zero"] == ["0"], e3 and e3["nums"])
        gd = dg[0]["data"]
        check("... px != py (a trig graph's units differ): px = min(0.7 Wv / 4, 2 cm), py = min(0.7 Hv / 10, 2 cm)",
              gd["px"] != gd["py"] and abs(gd["px"] - min(0.7 * Wv / 4, 2 * CM)) < 0.006 and abs(gd["py"] - min(0.7 * Hv / 10, 2 * CM)) < 0.006, [gd["px"], gd["py"], Wv, Hv])
        g3 = pg.evaluate("(i) => window.__T.geo(i)", dg[0]["id"])
        check("... its fonts go by min(px, py) (0.3 of it), every 90 degrees one px across", all(abs(l["size"] - 0.3 * min(gd["px"], gd["py"])) < 1e-6 for l in g3["labels"] if l["cls"] != "letter")
              and abs(g3["feet"][1][0] - g3["feet"][0][0] - gd["px"]) < 1e-6, g3["feet"][:2])
        doc = pdf_of(pg, "Degrees"); words = doc[0].get_text().split(); doc.close()
        check("the PDF writes '90°' as text", "90°" in words and "360°" in words, words)
        show(pg, [gd["x0"] + 2 * gd["px"], gd["y0"] - 0.5 * gd["py"]])
        pg.screenshot(path=str(SHOTS / "u5e-degrees.png"))
        pg.evaluate("window.__T.clear('s0')"); pg.wait_for_timeout(40)
        open_card(pg); set_tick(pg, "#ax-deg", False); set_tick(pg, "#ax-line", True)
        vis = pg.evaluate("window.__T.vis(0)"); Wv = vis[2] - vis[0]
        place(pg)
        nl = axes_recs(pg); e4 = el(pg, nl[0]["id"]) if nl else None
        check("a number line: one axis, two heads, no letters, 11 ticks and 11 labels (-5 .. 5, 0 included)",
              e4 and e4["axis"] == 1 and e4["head"] == 2 and e4["letters"] == [] and e4["tick"] == 11 and sorted(e4["nums"]) == sorted(str(v) for v in range(-5, 6)), e4)
        check("... its px = min(0.7 Wv / 10, 2 cm), py the same", abs(nl[0]["data"]["px"] - min(0.7 * Wv / 10, 2 * CM)) < 0.006 and nl[0]["data"]["py"] == nl[0]["data"]["px"], nl[0]["data"])
        pg.evaluate("window.__T.clear('s0')"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ G: remembered
        group[0] = "G. remembered"
        open_card(pg); set_tick(pg, "#ax-line", False); set_fields(pg, [-3, 4, 0.5, -2, 6, 2]); set_tick(pg, "#ax-deg", False); close_panel(pg)
        saved = pg.evaluate("JSON.parse(localStorage.getItem('pw.axes'))")
        check("the settings are kept on the device (localStorage pw.axes)", saved == {"deg": False, "line": False, "xs": -3, "xe": 4, "xd": 0.5, "ys": -2, "ye": 6, "yd": 2}, saved)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        pg.reload(); ready(pg); open_note(pg); pg.evaluate(HELP)
        open_card(pg)
        check("after a reload the card comes back with them", vals(pg) == ["-3", "4", "0.5", "-2", "6", "2"] and ticks(pg) == [False, False], vals(pg))
        set_fields(pg, [-5, 5, 1, -5, 5, 1]); close_panel(pg)

        # ------------------------------------------------------------ H: stick points
        group[0] = "H. stick points"
        pg.click(f'#tray .sw[data-colour="{BLUE}"]'); pg.wait_for_timeout(40)
        open_card(pg); place(pg); close_panel(pg)
        a = axes_recs(pg)[0]; dd = a["data"]; g = geo(pg, a["id"]); zz = z(pg)
        origin = [dd["x0"], dd["y0"]]
        check("the crossing of a default stamp is its origin", g["cross"] == origin or dist(g["cross"], origin) < 1e-9, [g["cross"], origin])
        toggle(pg, "ruler"); close_panel(pg)
        r0 = R(pg); g0 = local(pg, 60, r0["w"] / 2); dy = (origin[1] - 10 / zz) - r0["o"][1]   # above: below it the ticks' outer ends are nearer
        pen(pg, [g0, [g0[0], g0[1] + dy / 2], [g0[0], g0[1] + dy]])
        r1 = R(pg)
        check("the ruler's edge released 10 px (screen) above the origin sticks to the origin: edge A runs through it",
              r1["stuck"] is not None and dist(r1["stuck"]["p"], origin) < 1e-9 and r1["stuck"]["edge"] == "A" and abs(r1["o"][1] - origin[1]) < 1e-9, r1)
        toggle(pg, "ruler"); close_panel(pg)
        toggle(pg, "compass"); close_panel(pg)
        tip = g["outer"][2]                                           # the third x tick's outer end (x = -3), below the axis
        c = C(pg); q = lerp(c["c1"], c["geo"]["c2"], 0.15); want = addv(tip, [3 / zz, 3 / zz]); dlt = subv(want, c["c1"])
        pen(pg, [q, addv(q, lerp([0, 0], dlt, 0.5)), addv(q, dlt)])
        c1 = C(pg)
        check("the compass needle dropped 4 px (screen) from a tick's outer end snaps onto it", dist(c1["c1"], tip) < 1e-9 and c1["stuck"] is not None, [c1["c1"], tip])
        foot = g["feet"][2]
        c = C(pg); q = lerp(c["c1"], c["geo"]["c2"], 0.15); want = addv(foot, [2 / zz, -3 / zz]); dlt = subv(want, c["c1"])
        pen(pg, [q, addv(q, lerp([0, 0], dlt, 0.5)), addv(q, dlt)])
        check("... and dropped beside the tick ON the axis it snaps to the tick's point on the axis (x = -3, y = 0)",
              dist(C(pg)["c1"], foot) < 1e-9 and abs(foot[1] - origin[1]) < 1e-9, [C(pg)["c1"], foot])
        mid_ax = [origin[0] + 2.5 * dd["px"], origin[1]]
        c = C(pg); q = lerp(c["c1"], c["geo"]["c2"], 0.15); want = addv(mid_ax, [0, 6 / zz]); dlt = subv(want, c["c1"])
        pen(pg, [q, addv(q, lerp([0, 0], dlt, 0.5)), addv(q, dlt)])
        check("between ticks the needle runs along the x-axis (a stick curve, within 9 px)", abs(C(pg)["c1"][1] - origin[1]) < 1e-9 and abs(C(pg)["c1"][0] - mid_ax[0]) < 1e-6, C(pg)["c1"])
        toggle(pg, "compass"); close_panel(pg)
        check("only the stamp is on the page (the tools drew nothing)", [r["kind"] for r in recs(pg)] == ["axes"], [r["kind"] for r in recs(pg)])
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ J: the sign buttons (pw-v8m)
        group[0] = "J. sign"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        open_note(pg); pg.evaluate(HELP)
        open_card(pg)
        IDS = {"xs": "x start", "xe": "x end", "ys": "y start", "ye": "y end"}
        info = pg.evaluate("Object.fromEntries(['xs','xe','ys','ye'].map((k) => { const b = document.getElementById('ax-' + k + '-sign'); return [k, b ? [b.type, b.getAttribute('aria-label'), b.textContent, b.getBoundingClientRect().width, b.getBoundingClientRect().height, b.closest('#axesCard') !== null] : null]; }))")
        check("four sign buttons exist (ax-xs-sign, ax-xe-sign, ax-ys-sign, ax-ye-sign), type button, plus-minus text, inside the card, aria 'Flip the sign of <a> <word>'",
              all(info[k] and info[k][0] == "button" and info[k][1] == "Flip the sign of " + IDS[k] and info[k][2] == "±" and info[k][5] for k in IDS), info)
        check("... and only four: #axesCard .axSign count 4; the step cells hold no button",
              pg.locator("#axesCard .axSign").count() == 4 and pg.locator("#axesCard .axCell button").count() == 4 and pg.locator("#ax-xd-sign, #ax-yd-sign").count() == 0)
        check("each button is at least 36 x 36 CSS px", all(info[k][3] >= 36 and info[k][4] >= 36 for k in IDS), {k: info[k][3:5] for k in IDS})
        check("every row has three .axCell cells; each holds its field", pg.evaluate("[...document.querySelectorAll('#axesCard .axRow')].every((r) => r.querySelectorAll(':scope > .axCell').length === 3 && [...r.querySelectorAll('.axCell')].every((c) => c.querySelector('input.axNum')))"))
        cw = rect(pg, "#axesCard")["w"]
        check("the card's width at 1280 px (for the report)", 280 <= cw <= 340, cw)
        print("card width at 1280 px:", cw)
        pg.click("#ax-xs-sign"); pg.wait_for_timeout(30)
        check("x start reads -5 by default; one tap gives 5", vals(pg)[0] == "5", vals(pg))
        check("... the flip ran checkAxes: 5 to 5 reddens start and end, the line says 'Start must be smaller than End'",
              bads(pg) == ["xs", "xe"] and msg(pg) == "Start must be smaller than End", [bads(pg), msg(pg)])
        sv = pg.evaluate("JSON.parse(localStorage.getItem('pw.axes'))")
        check("... and saveAxes ran: localStorage pw.axes carries xs = 5", sv.get("xs") == 5, sv)
        pg.click("#ax-xs-sign"); pg.wait_for_timeout(30)
        check("a second tap gives -5 again; the red and the message clear",
              vals(pg)[0] == "-5" and bads(pg) == [] and msg(pg) == "", [vals(pg), bads(pg), msg(pg)])
        check("... and the saved value is -5 again", pg.evaluate("JSON.parse(localStorage.getItem('pw.axes')).xs") == -5)
        pg.fill("#ax-xs", ""); pg.click("#ax-xs-sign"); pg.wait_for_timeout(30)
        check("an empty field: a tap leaves it empty and focuses it",
              pg.input_value("#ax-xs") == "" and pg.evaluate("document.activeElement.id") == "ax-xs", [pg.input_value("#ax-xs"), pg.evaluate("document.activeElement.id")])
        pg.fill("#ax-xs", "0"); pg.click("#ax-xs-sign"); pg.wait_for_timeout(30)
        check("a 0 field: a tap leaves 0 (and focuses it)", pg.input_value("#ax-xs") == "0" and pg.evaluate("document.activeElement.id") == "ax-xs", pg.input_value("#ax-xs"))
        pg.fill("#ax-xs", "-5")
        set_tick(pg, "#ax-line", True)
        dis = pg.evaluate("['xs','xe','ys','ye'].map((k) => document.getElementById('ax-' + k + '-sign').disabled)")
        check("Number line ticked: the two y buttons are disabled, the two x buttons stay live", dis == [False, False, True, True], dis)
        set_tick(pg, "#ax-line", False)
        dis = pg.evaluate("['xs','xe','ys','ye'].map((k) => document.getElementById('ax-' + k + '-sign').disabled)")
        check("unticked: all four are enabled again", dis == [False] * 4, dis)
        set_fields(pg, [-5, 5, 1, -5, 5, 1])
        pg.click("#ax-ys-sign"); pg.click("#ax-ye-sign"); pg.wait_for_timeout(30)
        check("flip y start to 5 and y end to -5 is refused (both red, 'Start must be smaller than End')",
              vals(pg)[3:5] == ["5", "-5"] and bads(pg) == ["ys", "ye"] and msg(pg) == "Start must be smaller than End", [vals(pg), bads(pg), msg(pg)])
        n0 = len(recs(pg)); place(pg)
        check("... and Place lands nothing (the card stays)", len(recs(pg)) == n0 and card_shown(pg))
        set_fields(pg, [-5, 5, 1, 2, 5, 1])
        pg.click("#ax-ys-sign"); pg.wait_for_timeout(30)
        check("y start 2 flipped gives -2; the fields read x -5, 5, 1 and y -2, 5, 1", vals(pg) == ["-5", "5", "1", "-2", "5", "1"] and bads(pg) == [], [vals(pg), bads(pg)])
        al = pg.evaluate("""() => { const hc = [...document.querySelectorAll('#axesCard .axCols span')].map((e) => { const b = e.getBoundingClientRect(); return b.left + b.width / 2; });
          return ['x', 'y'].map((a) => [...document.querySelectorAll('#axesCard .axRow[data-axis="' + a + '"] .axCell')].map((e) => { const b = e.getBoundingClientRect(); return b.left + b.width / 2; })).map((cs) => cs.map((c, i) => Math.abs(c - hc[i]))); }""")
        check("the header cells line up with the row cells (x centres within 1 px, both rows)", len(al) == 2 and all(len(r) == 3 and all(d <= 1 for d in r) for r in al), al)
        pg.click("#ax-xe-sign"); pg.wait_for_timeout(30); pg.click("#ax-xe-sign"); pg.wait_for_timeout(30)
        check("a press on a sign button does not close the card or the panel", card_shown(pg) and panel_shown(pg))
        place(pg)
        ar = axes_recs(pg)
        check("Place lands ONE axes record whose data.ys is -2 (the flipped value went into the stamp)",
              len(ar) == 1 and ar[0]["data"]["ys"] == -2 and ar[0]["data"]["ye"] == 5 and ar[0]["data"]["xs"] == -5, [r["data"] for r in ar])
        check("no page errors (sign)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ I: the phone width (a look, for the report)
        group[0] = "I. phone width"
        ctx = b.new_context(viewport={"width": 375, "height": 812}, has_touch=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        open_note(pg); pg.evaluate(HELP)
        btn = pg.locator("#drawToolsBtn")
        if btn.is_visible():
            open_card(pg)
            cr = rect(pg, "#axesCard")
            check("at 375 px the card stays on screen (8 px gutters)", cr and cr["l"] >= 7.5 and cr["r"] <= 375 - 7.5 and cr["t"] >= 7.5 and cr["b"] <= 812 - 7.5, cr)
            pg.screenshot(path=str(SHOTS / "u5e-phone.png"))
        else:
            check("at 375 px there is no Tools button (the tray is tablet only): nothing to show", True, "no tray on the phone")
        check("no page errors (phone)", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g_, n, ok, info in res:
    if g_ not in groups: groups.append(g_)
    if not ok: print(f"FAIL [{g_}] {n}  -> {str(info)[:600]}")
print()
for g_ in groups:
    rs_ = [r for r in res if r[0] == g_]
    print(f"{g_}: {sum(r[2] for r in rs_)}/{len(rs_)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
