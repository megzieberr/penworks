# PenWorks U5b + U5c checks (tools round 2 and the stick feel): the COMPASS on the paper, Mathspad-exact (the constructions app's compass,
# ported to the page; briefs/U5-TOOLS-DESIGN.md and _build/U5B-COMPASS-BRIEF.md).
# Run: python tests/test_compass.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800 (the tablet landscape size), the way
# tests/test_tools.py does. Pen gestures are PointerEvents (pointerType 'pen') fired on the desk; fingers are touch
# PointerEvents on the desk. The PDF is read with PyMuPDF.
# What it proves: the Compass row is live and toggles, ruler and compass may be out together; the compass is in page px
# (the zoom scales it), never a record, never in a thumb or the PDF; the zones in hitCompass's order (lock, draw, move,
# width); the width clamps; a swing lands ONE fixed arc (or ONE fixed circle from a full turn), the arc only grows,
# a tiny swing lands nothing, the style is the current ink tool's, undo and redo; fingers pan and pinch even on the
# compass; the needle and the pencil tip snap to stick points, the ruler sticks to a fixed circle's crossing; Select
# moves a fixed arc whole with no handles, Copy and Paste keep fixed; the last tool touched takes the press; closing
# the note puts the tools away. Screenshots go to _build/shots-compass/.
import sys, subprocess, time, pathlib, re, math, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8802
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-compass"
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
  window.__I = await import('./js/ink.js');
  const T = window.__T = {};
  T.z = () => window.__P.view().z;
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.client = (id, x, y) => { const r = T.sheet(id).getBoundingClientRect(), z = T.z(); return [r.left + x * z, r.top + y * z]; };
  T.ev = (type, id, kind, x, y, buttons) => document.getElementById('desk').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: kind,
    isPrimary: true, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0,
    buttons: buttons !== undefined ? buttons : type === 'pointerup' ? 0 : 1, clientX: x, clientY: y }));
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
  T.hover = (id, p) => { const c = T.client(id, p[0], p[1]); T.ev('pointermove', 33, 'pen', c[0], c[1], 0); };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.line = (id, x1, y1, x2, y2, extra = {}) => { const r = { id: crypto.randomUUID(), page_id: id, seq: Date.now() + Math.floor(Math.random() * 1000), kind: 'shape',
    style: { colour: '#FF0C84', width: 2.5, dash: 'solid', opacity: 1 }, data: { type: 'line', x1, y1, x2, y2, ...extra } };
    window.__pw.ink.put(id, [r]); return r.id; };
  T.shape = (id, data) => { const r = { id: crypto.randomUUID(), page_id: id, seq: Date.now() + Math.floor(Math.random() * 1000), kind: 'shape',
    style: { colour: '#FF0C84', width: 2.5, dash: 'solid', opacity: 1 }, data };
    window.__pw.ink.put(id, [r]); return r.id; };
  T.clear = (id) => { const op = window.__pw.ink.erasePageOp(id); if (op) op.redo(); };
  T.rings = () => [...document.querySelectorAll('#stack svg.toolLayer circle.stickRing')].filter((c) => c.getAttribute('display') !== 'none')
    .map((c) => [+c.getAttribute('cx'), +c.getAttribute('cy'), +c.getAttribute('r')]);
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
def ids(pg, pid="s0"): return [r["id"] for r in recs(pg, pid)]
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
def lerp(a, b, t): return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
def addv(a, b): return [a[0] + b[0], a[1] + b[1]]
def subv(a, b): return [a[0] - b[0], a[1] - b[1]]
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def norm(a): return a % (2 * math.pi)
def open_panel(pg):
    if pg.locator("#toolsPanel").is_hidden(): pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
def toggle(pg, tool):
    open_panel(pg); pg.click(f"#trow-{tool}"); pg.wait_for_timeout(60)
def close_panel(pg): pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
def finger(pg, kind, pid, x, y):
    pg.evaluate("([t, i, x, y]) => window.__T.ev(t, i, 'touch', x, y)", [kind, pid, x, y])
def pressed(pg, sel): return pg.get_attribute(sel, "aria-pressed")
def cl(pg, p, page="s0"): return pg.evaluate("([id, x, y]) => window.__T.client(id, x, y)", [page, p[0], p[1]])
def needle_pt(c): return lerp(c["c1"], c["geo"]["c2"], 0.15)            # on the needle's arm, near the needle
def pencil_pt(c): return lerp(c["geo"]["c3"], c["geo"]["pTop"], 0.3)    # on the pencil's body
def arc_sweep(d, c1):
    a1 = math.atan2(d["y1"] - c1[1], d["x1"] - c1[0]); am = math.atan2(d["ym"] - c1[1], d["xm"] - c1[0]); a2 = math.atan2(d["y2"] - c1[1], d["x2"] - c1[0])
    sw = norm(a2 - a1); return sw, norm(am - a1)
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
def edge_perp_(r, q):                                            # q's distance from the stuck edge's line (A or B), page px
    u = (math.cos(r["ang"]), math.sin(r["ang"])); n = (-u[1], u[0]); v = (q[0] - r["o"][0], q[1] - r["o"][1]); y = v[0] * n[0] + v[1] * n[1]
    return abs(y - (0 if r["stuck"]["edge"] == "A" else r["w"]))
def pen_live(pg):
    return pg.evaluate("window.__T.sheet('s0').querySelectorAll('svg.ink g.pen > *').length")

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

        # ------------------------------------------------------------ A: the panel
        group[0] = "A. panel"
        pg.click('#tray .sw[data-colour="#0D0DFF"]'); pg.wait_for_timeout(40)   # the pen in Blue (not the default Black)
        open_panel(pg)
        rows = pg.evaluate("[...document.querySelectorAll('#toolsPanel .trow')].map((b) => [b.textContent.trim(), b.disabled, b.title, b.getAttribute('aria-pressed')])")
        check("the Compass row is live (not disabled, no 'Next round' title), unpressed", rows[1][0] == "Compass" and rows[1][1] is False and rows[1][2] == "" and rows[1][3] == "false", rows)
        check("Axes stays disabled ('Next round'); the Protractor is live (U5d)", rows[3][1] is True and rows[3][2] == "Next round" and rows[2][1] is False, rows)
        pg.click("#trow-compass"); pg.wait_for_timeout(60)
        c = C(pg)
        check("a tap brings the compass out on the current page (page 1), the row and the Tools button pressed",
              c is not None and c["page"] == "s0" and pressed(pg, "#trow-compass") == "true" and pressed(pg, "#drawToolsBtn") == "true", c)
        pg.click("#trow-ruler"); pg.wait_for_timeout(60)
        check("ruler and compass out at the same time, both rows pressed", R(pg) is not None and C(pg) is not None
              and pressed(pg, "#trow-ruler") == "true" and pressed(pg, "#trow-compass") == "true")
        lay = pg.evaluate("""() => { const ls = [...window.__T.sheet('s0').querySelectorAll(':scope > svg.toolLayer')];
          return ls.map((l) => [...l.children].filter((e) => e.tagName === 'g').map((e) => e.getAttribute('class'))); }""")
        check("one tool layer on the page holding both tools, the one brought out last on top (ruler over compass)", lay == [["compass", "ruler"]], lay)
        pg.click("#trow-ruler"); pg.wait_for_timeout(60)
        check("the ruler away, the compass still out: the Tools button stays pressed (ANY tool out)",
              R(pg) is None and C(pg) is not None and pressed(pg, "#drawToolsBtn") == "true" and pressed(pg, "#trow-ruler") == "false")
        pg.click("#trow-compass"); pg.wait_for_timeout(60)
        check("a second tap puts the compass away: no layer anywhere, row and button unpressed",
              C(pg) is None and pg.locator("#stack svg.toolLayer").count() == 0 and pressed(pg, "#trow-compass") == "false" and pressed(pg, "#drawToolsBtn") == "false")

        # ------------------------------------------------------------ B: out on the paper
        group[0] = "B. compass out"
        pg.click("#trow-compass"); pg.wait_for_timeout(60); close_panel(pg)
        c = C(pg); g = c["geo"]
        check("one fixed size: arm 240 x CM/32 (7.5 cm), R_MIN 6 x CM/32, R_MAX 1.85 arms, handle 56 x CM/32",
              abs(c["arm"] - 7.5 * CM) < 1e-9 and abs(c["rMin"] - 6 * K) < 1e-9 and abs(c["rMax"] - 1.85 * c["arm"]) < 1e-9 and abs(c["handle"] - 56 * K) < 1e-9, c)
        check("it comes out 5 cm wide, unlocked, level (angle 0)", abs(c["r"] - 5 * CM) < 1e-9 and c["locked"] is False and c["th"] == 0, c)
        check("the needle a little left of centre and below the middle: (0.42, 0.68) of the page",
              abs(c["c1"][0] - 794 * 0.42) < 1e-9 and abs(c["c1"][1] - 1123 * 0.68) < 1e-9, c["c1"])
        check("the arms are ARM long (needle to hinge, hinge to pencil tip), the tip a width from the needle, hinge up",
              abs(dist(c["c1"], g["c2"]) - c["arm"]) < 1e-6 and abs(dist(g["c3"], g["c2"]) - c["arm"]) < 1e-6 and abs(dist(c["c1"], g["c3"]) - c["r"]) < 1e-6
              and g["c2"][1] < c["c1"][1] - 200, [c["c1"], g])
        lay = pg.evaluate("""() => { const s = window.__T.sheet('s0'), l = s.querySelector(':scope > svg.toolLayer'), ink = s.querySelector(':scope > svg.ink');
          if (!l) return null; const gc = l.querySelector('g.compass');
          return { after: !!ink && !!(ink.compareDocumentPosition(l) & 4), view: l.getAttribute('viewBox'), g: !!gc,
                   lock: !!gc.querySelector('circle.lockBtn'), hinge: !!gc.querySelector('circle.hinge'), needle: !!gc.querySelector('[data-part="needle"]'),
                   pencil: gc.querySelectorAll('[data-part="pencil"]').length, tip: (gc.querySelector('[data-part="tip"]') || {}).getAttribute && gc.querySelector('[data-part="tip"]').getAttribute('fill'),
                   halos: gc.querySelectorAll('.halo').length }; }""")
        check("a g.compass in page 1's tool layer, over the ink, page px viewBox", lay and lay["after"] and lay["view"] == "0 0 794 1123" and lay["g"], lay)
        check("its parts: the padlock button, the hinge, the needle, the pencil (4 pieces) with her ink colour on its tip, no halo at rest",
              lay and lay["lock"] and lay["hinge"] and lay["needle"] and lay["pencil"] == 4 and lay["tip"] == "#0D0DFF" and lay["halos"] == 0, lay)
        pg.click('#tray .sw[data-colour="#FF0C84"]'); pg.wait_for_timeout(60)
        tip2 = pg.evaluate("window.__T.sheet('s0').querySelector('g.compass [data-part=\"tip\"]').getAttribute('fill')")
        pg.click('#tray .sw[data-colour="#0D0DFF"]'); pg.wait_for_timeout(60)
        check("a colour picked on the tray: the pencil's tip takes it at once", tip2 == "#FF0C84", tip2)
        check("the compass is not a record: strokesOf(page 1) is empty", recs(pg) == [])
        th = pg.evaluate("() => { const s = window.__pw.ink.thumbSvg('s0'); return [s.querySelectorAll('*').length, s.querySelectorAll('.compass, polygon, line').length]; }")
        check("... and not in the page's thumb", th == [2, 0], th)
        z1 = z(pg); w1 = rect(pg, "#stack svg.toolLayer g.compass")
        zoom_to(pg, z1 * 2); z2 = z(pg); w2 = rect(pg, "#stack svg.toolLayer g.compass"); c2_ = C(pg)
        check("a zoom to 2x doubles its screen box, its page px unchanged (paper, ink and compass scale together)",
              abs(z2 / z1 - 2) < 1e-6 and abs(w2["w"] / w1["w"] - 2) < 0.01 and abs(w2["h"] / w1["h"] - 2) < 0.01 and c2_["c1"] == c["c1"] and c2_["r"] == c["r"], [z1, z2, w1, w2])
        zoom_to(pg, z1)
        check("zoomed back to 1x", abs(z(pg) - 1) < 1e-6, z(pg))
        pg.evaluate("window.__P.scrollToPage(1)"); pg.wait_for_timeout(80)
        toggle(pg, "compass"); toggle(pg, "compass")
        check("put away and brought out while page 2 is current, it comes out fresh on page 2",
              C(pg)["page"] == "s1" and C(pg)["c1"] == c["c1"] and C(pg)["r"] == c["r"] and pg.evaluate("!!window.__T.sheet('s1').querySelector(':scope > svg.toolLayer g.compass')"))
        pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)
        check("scrolled back to page 1, it stays on page 2", pg.evaluate("window.__P.current()") == 0 and C(pg)["page"] == "s1")
        toggle(pg, "compass"); toggle(pg, "compass"); close_panel(pg)
        check("away and out again: on page 1", C(pg)["page"] == "s0")

        # ------------------------------------------------------------ C: the zones, in Mathspad's order
        group[0] = "C. zones"
        show(pg, C(pg)["geo"]["c2"])
        c = C(pg); g = c["geo"]
        hover(pg, lerp(g["c2"], g["hEnd"], 0.5)); h1 = pg.evaluate("window.__T.sheet('s0').querySelectorAll('g.compass .halo').length")
        hover(pg, pencil_pt(c)); h2 = pg.evaluate("window.__T.sheet('s0').querySelectorAll('g.compass .halo').length")
        hover(pg, needle_pt(c)); h3 = pg.evaluate("window.__T.sheet('s0').querySelectorAll('g.compass .halo').length")
        hover(pg, [40, 40]); h4 = pg.evaluate("window.__T.sheet('s0').querySelectorAll('g.compass .halo').length")
        check("hovering: a halo on the handle (draw) and the needle arm (move), NONE on the pencil (width), none off the compass",
              (h1, h2, h3, h4) == (1, 0, 1, 0), [h1, h2, h3, h4])
        n0 = pen_live(pg)
        pen(pg, [g["lockC"]], up=False); kk = C(pg); pen_up(pg, g["lockC"]); c1 = C(pg)
        look = pg.evaluate("[window.__T.sheet('s0').querySelector('g.compass circle.lockBtn').getAttribute('fill'), window.__T.sheet('s0').querySelector('g.compass .padlock').dataset.locked]")
        check("a press on the padlock flips the lock (a 'noop' gesture) and nothing else: same place, width, angle",
              kk["gesture"] == "noop" and c1["locked"] is True and c1["c1"] == c["c1"] and c1["r"] == c["r"] and c1["th"] == c["th"], [kk, c1])
        check("... the bar and the button show the locked look", look == ["#8FA3D6", "1"], look)
        check("... and lands nothing", recs(pg) == [] and pen_live(pg) == n0)
        pen(pg, [g["lockC"]]); c1 = C(pg)
        check("a second press unlocks it", c1["locked"] is False)
        pen(pg, [g["c2"]], up=False); kk = C(pg); pen_up(pg, g["c2"])
        pen(pg, [lerp(g["c2"], g["hEnd"], 0.8)], up=False); kh = C(pg); pen_up(pg, lerp(g["c2"], g["hEnd"], 0.8))
        check("a press on the hinge draws ('cDraw'), and so does one on the handle above it", kk["gesture"] == "cDraw" and kh["gesture"] == "cDraw", [kk["gesture"], kh["gesture"]])
        check("a press on the hinge with no swing lands nothing", recs(pg) == [] and pen_live(pg) == n0)
        q = needle_pt(c)
        pen(pg, [q, addv(q, [20, -10]), addv(q, [60, -40])], up=False); kk = C(pg); pen_up(pg, addv(q, [60, -40])); c1 = C(pg)
        check("a drag on the needle's arm moves the whole compass ('cMove'): the needle by the drag, width and angle kept",
              kk["gesture"] == "cMove" and abs(c1["c1"][0] - c["c1"][0] - 60) < 1e-6 and abs(c1["c1"][1] - c["c1"][1] + 40) < 1e-6
              and c1["r"] == c["r"] and c1["th"] == c["th"], [c, c1])
        pen(pg, [addv(q, [60, -40]), q]); c = C(pg); g = c["geo"]
        check("... and back (no records from moving)", abs(c["c1"][0] - 794 * 0.42) < 1e-6 and recs(pg) == [])
        p0 = pencil_pt(c)
        pen(pg, [p0, addv(p0, [20, 0]), addv(p0, [40, 0])], up=False); kk = C(pg)
        pill = pg.evaluate("() => { const e = document.querySelector('#stack .sheet .toolCm'); return e ? [e.textContent, e.classList.contains('on'), e.classList.contains('selDeg')] : null; }")
        pen_up(pg, addv(p0, [40, 0])); c1 = C(pg)
        check("a drag on the pencil sets the width ('cWidth'): the tip follows the pen, 40 px out, still level",
              kk["gesture"] == "cWidth" and abs(c1["r"] - c["r"] - 40) < 1e-6 and abs(c1["th"]) < 1e-9 and c1["c1"] == c["c1"], [c, c1])
        check("while setting it, a pill shows the width in cm", pill and pill[1] and pill[0] == f"{(c['r'] + 40) / CM:.1f} cm", pill)
        check("after the lift the pill is gone", not pg.evaluate("() => { const e = document.querySelector('#stack .toolCm'); return !!e && e.classList.contains('on'); }"))
        p0 = pencil_pt(c1)
        pen(pg, [p0, addv(p0, [0, 60])]); c2_ = C(pg)
        tip = addv(c1["geo"]["c3"], [0, 60])
        check("pulled off its line, the compass turns so the pencil arm points at the pen, the width = tip to needle",
              abs(c2_["r"] - dist(tip, c1["c1"])) < 1e-6 and abs(c2_["th"] - math.atan2(tip[1] - c1["c1"][1], tip[0] - c1["c1"][0])) < 1e-9, [c2_, tip])
        pen(pg, [C(pg)["geo"]["lockC"]])                            # locked: the pencil arm turns it
        c = C(pg); p0 = pencil_pt(c)
        pen(pg, turn_path(c["c1"], p0, 30), up=False); kk = C(pg); pen_up(pg, turn_path(c["c1"], p0, 30)[-1]); c1 = C(pg)
        check("locked, the pencil arm turns it about the needle ('cTurn'): 30 degrees, the width unchanged to 0.01 px",
              kk["gesture"] == "cTurn" and abs(c1["r"] - c["r"]) < 0.01 and abs(c1["th"] - c["th"] - math.radians(30)) < 1e-7 and c1["c1"] == c["c1"],
              [kk["gesture"], c["r"], c1["r"], c["th"], c1["th"], c["c1"], c1["c1"]])
        check("... and draws nothing", recs(pg) == [] and pen_live(pg) == n0)
        pen(pg, [c1["geo"]["lockC"]]); c = C(pg)
        check("unlocked again", c["locked"] is False)

        # ------------------------------------------------------------ D: the width clamps
        group[0] = "D. clamps"
        p0 = pencil_pt(c); toward = subv(c["c1"], c["geo"]["c3"])
        pen(pg, [p0, addv(p0, lerp([0, 0], toward, 0.5)), addv(p0, toward)]); c1 = C(pg)
        check("the tip pulled onto the needle: the width stops at R_MIN", abs(c1["r"] - c1["rMin"]) < 1e-9, c1["r"])
        p0 = lerp(c1["geo"]["c3"], c1["geo"]["pTop"], 0.92); u = [math.cos(c1["th"]), math.sin(c1["th"])]   # at R_MIN the pencil's top is the width zone
        pen(pg, [p0, addv(p0, [u[0] * 300, u[1] * 300]), addv(p0, [u[0] * 900, u[1] * 900])]); c2_ = C(pg)
        check("pulled far out: it stops at R_MAX (1.85 arms)", abs(c2_["r"] - c2_["rMax"]) < 1e-9, c2_["r"])
        toggle(pg, "compass"); toggle(pg, "compass"); close_panel(pg)
        c = C(pg)
        check("put away and out again it is fresh: 5 cm, level, unlocked", abs(c["r"] - 5 * CM) < 1e-9 and c["th"] == 0 and not c["locked"], c)

        # ------------------------------------------------------------ E: swinging an arc
        group[0] = "E. arcs"
        show(pg, C(pg)["c1"])                                       # the needle mid-desk: the whole swing on screen
        tr = pg.evaluate("window.__pw.tray()")
        c = C(pg); g = c["geo"]; path = turn_path(c["c1"], g["c2"], 90)
        pen(pg, path[:19], up=False)                                # 45 degrees in, the pen still down
        mid = C(pg)                                       # U5c: the live arc is a <g> (its path and the needle mark)
        live = pg.evaluate("""() => { const l = [...window.__T.sheet('s0').querySelectorAll('svg.ink g.pen > g')]; const e = l[l.length - 1];
          return e ? [l.length, e.getAttribute('stroke'), e.getAttribute('stroke-width')] : null; }""")
        midlook = pg.evaluate("""() => { const gc = window.__T.sheet('s0').querySelector('g.compass');
          return [gc.querySelector('circle.lockBtn').getAttribute('fill'), [...gc.querySelectorAll('.halo')].map((h) => h.tagName), window.__T.rings().length,
                  gc.querySelector('g.pencilSide').getAttribute('opacity')]; }""")
        pg.screenshot(path=str(SHOTS / "compass-mid-swing.png"))
        for qq in path[19:]: pg.evaluate("([id, p]) => { const c = window.__T.client(id, p[0], p[1]); window.__T.ev('pointermove', 31, 'pen', c[0], c[1]); }", ["s0", qq])
        pen_up(pg, path[-1])
        rs = recs(pg)
        check("mid-swing: a live arc in the pen's colour and width, the compass in its locked look",
              mid["gesture"] == "cDraw" and live and live[0] == 1 and live[1] == "#0D0DFF" and live[2] == "2.5" and midlook[0] == "#8FA3D6", [live, midlook])
        check("mid-swing: only the handle's halo, no ring anywhere, nothing at the pencil tip", midlook[1] == ["line"] and midlook[2] == 0, midlook)
        check("mid-swing: the pencil side is see-through (0.4), so the arc under it shows; solid again after the lift",
              midlook[3] == "0.4" and pg.evaluate("window.__T.sheet('s0').querySelector('g.compass g.pencilSide').getAttribute('opacity')") == "1", midlook)
        check("a 90 degree swing lands exactly ONE record: kind 'shape', data.type 'arc', data.fixed true",
              len(rs) == 1 and rs[0]["kind"] == "shape" and rs[0]["data"]["type"] == "arc" and rs[0]["data"].get("fixed") is True, rs)
        d = rs[0]["data"] if rs else {}
        pts = [[d.get("x1"), d.get("y1")], [d.get("xm"), d.get("ym")], [d.get("x2"), d.get("y2")]]
        check("its three points lie on the circle (centre the needle, radius the width) within 0.5 page px",
              rs and all(abs(dist(p, c["c1"]) - c["r"]) < 0.5 for p in pts), [dist(p, c["c1"]) - c["r"] for p in pts] if rs else None)
        sw, sm = arc_sweep(d, c["c1"]) if rs else (0, 0)
        check("its sweep is 90 degrees (within 0.5), the middle point half way round", abs(math.degrees(sw) - 90) < 0.5 and abs(math.degrees(sm) - 45) < 0.5, [math.degrees(sw), math.degrees(sm)])
        check("it starts where the swing started (the pencil tip's place at the press)", rs and dist(pts[0], g["c3"]) < 0.02, [pts[0], g["c3"]])
        check("colour and width of the current pen (Blue, 2.5), solid, opacity 1",
              rs and rs[0]["style"] == {"colour": tr["pen"]["colour"], "width": tr["pen"]["width"], "dash": "solid", "opacity": 1}, rs and rs[0]["style"])
        check("one element on the page for it (the live arc became the arc)", pen_live(pg) == 1, pen_live(pg))
        c1 = C(pg)
        check("after the lift the compass stays out where it is, turned 90, its angle normalised (0 to 2 pi)",
              c1["c1"] == c["c1"] and 0 <= c1["th"] < 2 * math.pi and abs(c1["th"] - math.pi / 2) < 1e-6 and c1["gesture"] is None, c1)
        arc_id = rs[0]["id"] if rs else None
        pg.screenshot(path=str(SHOTS / "compass-arc-landed.png"))
        pg.click("#undoBtn"); pg.wait_for_timeout(50); after_undo = ids(pg)
        pg.click("#redoBtn"); pg.wait_for_timeout(50)
        check("undo takes the arc away (one step), redo brings it back", after_undo == [] and ids(pg) == [arc_id], [after_undo, ids(pg)])
        c = C(pg); g = c["geo"]; before = set(ids(pg))
        fw = turn_path(c["c1"], g["c2"], 120); back = turn_path(c["c1"], fw[-1], -60)
        pen(pg, fw + back[1:])
        nw = [x for x in recs(pg) if x["id"] not in before]
        sw = arc_sweep(nw[0]["data"], c["c1"])[0] if nw else 0
        check("swung forward 120 then back 60, it lands 120 (the arc only grows)", len(nw) == 1 and abs(math.degrees(sw) - 120) < 0.5, math.degrees(sw))
        c = C(pg); g = c["geo"]; before = set(ids(pg))
        pen(pg, turn_path(c["c1"], g["c2"], -70))
        nw = [x for x in recs(pg) if x["id"] not in before]
        sw = arc_sweep(nw[0]["data"], c["c1"])[0] if nw else 0
        check("a swing the other way lands its 70 too", len(nw) == 1 and nw[0]["data"]["type"] == "arc" and abs(math.degrees(sw) - 70) < 0.5, math.degrees(sw))
        c = C(pg); g = c["geo"]; before = set(ids(pg))
        pen(pg, turn_path(c["c1"], g["c2"], 370))
        nw = [x for x in recs(pg) if x["id"] not in before]
        cd = nw[0]["data"] if nw else {}
        check("a full swing lands ONE circle record, fixed, centre the needle, radius the width (0.01 px)",
              len(nw) == 1 and cd.get("type") == "circle" and cd.get("fixed") is True and abs(cd["cx"] - c["c1"][0]) < 0.006 and abs(cd["cy"] - c["c1"][1]) < 0.006
              and abs(cd["r"] - c["r"]) < 0.006, [nw, c])
        check("... drawn as one <g> in the pen group: its <circle> and (U5c) the needle mark", pg.evaluate("(id) => { const e = window.__T.sheet('s0').querySelector(`svg.ink g.pen > [data-id=\"${id}\"]`); return e ? [e.tagName, ...[...e.children].map((k) => k.tagName + '.' + (k.getAttribute('class') || ''))] : null; }", nw[0]["id"] if nw else "") == ["g", "circle.", "circle.needle"])
        c = C(pg); g = c["geo"]; before = ids(pg); n1 = pen_live(pg)
        pen(pg, turn_path(c["c1"], g["c2"], 0.2, steps=4))          # 0.0035 rad
        check("a swing under 0.004 rad lands nothing and leaves no live arc behind", ids(pg) == before and pen_live(pg) == n1, [len(before), len(ids(pg))])
        pg.click("#tool-highlighter"); pg.wait_for_timeout(40)
        tr = pg.evaluate("window.__pw.tray()")
        c = C(pg); g = c["geo"]; before = set(ids(pg))
        pen(pg, turn_path(c["c1"], g["c2"], 45))
        hl = [x for x in recs(pg) if x["id"] not in before]
        where = pg.evaluate("""(id) => { const e = window.__T.sheet('s0').querySelector(`svg.ink [data-id="${id}"]`);
          return e ? [e.parentNode.getAttribute('class'), e.parentNode.parentNode.getAttribute('class')] : null; }""", hl[0]["id"] if hl else "")
        check("with the highlighter on, the arc takes the highlighter's style and lands in the highlighter group",
              len(hl) == 1 and hl[0]["style"] == {"colour": tr["highlighter"]["colour"], "width": tr["highlighter"]["width"], "dash": "solid", "opacity": tr["highlighter"]["opacity"]}
              and hl[0]["data"].get("fixed") is True and where == ["hlo", "hl"], [hl, where])
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        c = C(pg); g = c["geo"]; before = set(ids(pg))
        pen(pg, turn_path(c["c1"], g["c2"], 30))
        sl = [x for x in recs(pg) if x["id"] not in before]
        check("with Select on, the arc takes the PEN's style", len(sl) == 1 and sl[0]["style"]["colour"] == tr["pen"]["colour"] and sl[0]["style"]["opacity"] == 1, sl)
        pg.click("#tool-pen"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ F: fingers are never the compass's
        group[0] = "F. fingers"
        pg.wait_for_timeout(700)                                   # page.js ignores a finger for 600 ms after the pen (palm)
        c0 = C(pg); v0 = pg.evaluate("window.__P.view()"); n_recs = len(recs(pg))
        cpt = cl(pg, needle_pt(c0))
        finger(pg, "pointerdown", 71, cpt[0], cpt[1])
        for k in range(1, 7): finger(pg, "pointermove", 71, cpt[0], cpt[1] - 15 * k); pg.wait_for_timeout(16)
        finger(pg, "pointerup", 71, cpt[0], cpt[1] - 90); pg.wait_for_timeout(120)
        v1 = pg.evaluate("window.__P.view()"); c1 = C(pg)
        check("a finger drag starting on the compass pans the page", v1["y"] < v0["y"] - 50, [v0, v1])
        check("... and the compass stays where it was on the paper, no records", c1["c1"] == c0["c1"] and c1["th"] == c0["th"] and len(recs(pg)) == n_recs, [c0, c1])
        z0 = z(pg); a1 = cl(pg, needle_pt(c0)); a2 = cl(pg, c0["geo"]["c2"])
        finger(pg, "pointerdown", 81, a1[0], a1[1]); finger(pg, "pointerdown", 82, a2[0], a2[1])
        for k in range(1, 7):
            finger(pg, "pointermove", 81, a1[0], a1[1] + 15 * k); finger(pg, "pointermove", 82, a2[0], a2[1] - 15 * k); pg.wait_for_timeout(16)
        finger(pg, "pointerup", 81, a1[0], a1[1] + 90); finger(pg, "pointerup", 82, a2[0], a2[1] - 90); pg.wait_for_timeout(120)
        z1 = z(pg); c2_ = C(pg)
        check("two fingers starting on the compass pinch: the zoom grows", z1 > z0 * 1.2, [z0, z1])
        check("... and the compass keeps its place on the paper", c2_["c1"] == c0["c1"] and c2_["r"] == c0["r"], [c0, c2_])
        zoom_to(pg, 1); pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)
        check("zoom back at 1x for the stick checks", abs(z(pg) - 1) < 1e-6, z(pg))

        # ------------------------------------------------------------ G: stick points
        group[0] = "G. stick points"
        pg.evaluate("window.__T.clear('s0')"); pg.wait_for_timeout(40)
        toggle(pg, "compass"); toggle(pg, "compass"); close_panel(pg)
        zz = z(pg); c = C(pg)
        pg.evaluate("window.__T.line('s0', 450, 380, 450, 300)")    # a line: its end (450, 380) is a stick point
        q = needle_pt(c); want = [450 + 15 / zz, 380]; dlt = subv(want, c["c1"])
        pen(pg, [q, addv(q, lerp([0, 0], dlt, 0.5)), addv(q, dlt)], up=False)
        ring_mid = pg.evaluate("window.__T.rings()")
        pen_up(pg, addv(q, dlt)); c1 = C(pg)
        check("the needle released 15 px (screen) from a line's end lands exactly on it", c1["c1"] == [450, 380], c1["c1"])
        check("... a small ring marks the point (while moving and after)", len(ring_mid) == 1 and abs(ring_mid[0][0] - 450) < 0.01 and abs(ring_mid[0][1] - 380) < 0.01
              and pg.evaluate("window.__T.rings()") == ring_mid, [ring_mid, pg.evaluate("window.__T.rings()")])
        col = pg.evaluate("[...document.querySelectorAll('#stack svg.toolLayer circle.stickRing')].find((c) => c.getAttribute('display') !== 'none').getAttribute('stroke')")
        check("... in the handle blue", col == "#2F4BB8", col)
        q = needle_pt(c1)
        pen(pg, [q, addv(q, [-60, 120]), addv(q, [-150, 320])]); c2_ = C(pg)
        check("moved away (out of reach) it lets go: no ring", c2_["stuck"] is None and pg.evaluate("window.__T.rings()") == [], c2_)
        pg.evaluate("window.__T.clear('s0')")
        pg.evaluate("window.__T.line('s0', 450, 690, 590, 830)"); pg.evaluate("window.__T.line('s0', 450, 830, 590, 690)")   # crossing at (520, 760)
        c = C(pg); p0 = pencil_pt(c); want = [520, 760 + 15 / zz]; dlt = subv(want, c["geo"]["c3"])
        pen(pg, [p0, addv(p0, lerp([0, 0], dlt, 0.5)), addv(p0, dlt)], up=False)
        ring_mid = pg.evaluate("window.__T.rings()")
        pen_up(pg, addv(p0, dlt)); c1 = C(pg)
        check("the pencil tip released 15 px (screen) from a crossing lands exactly on it (width = needle to crossing)",
              dist(c1["geo"]["c3"], [520, 760]) < 1e-6 and abs(c1["r"] - dist(c["c1"], [520, 760])) < 1e-9, [c1["geo"]["c3"], c1["r"]])
        check("... a ring marked the crossing while the width was set, gone after the lift",
              any(abs(r[0] - 520) < 1e-6 and abs(r[1] - 760) < 1e-6 for r in ring_mid) and pg.evaluate("window.__T.rings()") == [], [ring_mid, pg.evaluate("window.__T.rings()")])
        pg.evaluate("window.__T.clear('s0')")
        toggle(pg, "compass"); toggle(pg, "ruler"); close_panel(pg)   # the compass away, the ruler out
        cid = pg.evaluate("window.__T.shape('s0', { type: 'circle', cx: 400, cy: 500, r: 100, fixed: true })")
        pg.evaluate("window.__T.line('s0', 400, 300, 400, 900)")    # crosses the circle at (400, 400) and (400, 600), its ends out of reach
        r0 = R(pg); g0 = local(pg, 300, r0["w"] / 2); dy = (600 + 10 / zz) - r0["o"][1]
        pen(pg, [g0, [g0[0], g0[1] + dy / 2], [g0[0], g0[1] + dy]])
        r1 = R(pg)
        check("the ruler's edge sticks to the crossing of a fixed circle and a line (400, 600)",
              r1["stuck"] is not None and abs(r1["stuck"]["p"][0] - 400) < 1e-9 and abs(r1["stuck"]["p"][1] - 600) < 1e-9, r1)
        pg.evaluate("window.__T.clear('s0')")
        pg.evaluate("window.__T.shape('s0', { type: 'circle', cx: 400, cy: 500, r: 100 })")
        pg.evaluate("window.__T.line('s0', 400, 300, 400, 900)")
        r0 = R(pg); g0 = local(pg, 300, r0["w"] / 2); dy = (600 + 10 / zz) - r0["o"][1]
        pen(pg, [g0, [g0[0], g0[1] + dy]])
        check("... a snapped (not fixed) circle is not a compass circle: no stick there", R(pg)["stuck"] is None, R(pg))
        pg.evaluate("window.__T.clear('s0')")
        toggle(pg, "ruler"); close_panel(pg)

        # ------------------------------------------------------------ H: fixed arcs and the Select tool
        group[0] = "H. fixed + select"
        toggle(pg, "compass"); close_panel(pg)
        c = C(pg); pen(pg, turn_path(c["c1"], c["geo"]["c2"], 90))
        fx = recs(pg)[0]
        toggle(pg, "compass"); close_panel(pg)                      # away: a press on the arc is the arc's
        check("handles() of a fixed arc: none; the same arc unfixed keeps its three",
              pg.evaluate("(r) => window.__I.handles(r).length", fx) == 0 and pg.evaluate("(r) => window.__I.handles({ ...r, data: { ...r.data, fixed: undefined } }).length", fx) == 3)
        check("handles() of a fixed circle: none (a plain circle has four)",
              pg.evaluate("() => window.__I.handles({ data: { type: 'circle', cx: 1, cy: 2, r: 30, fixed: true } }).length") == 0
              and pg.evaluate("() => window.__I.handles({ data: { type: 'circle', cx: 1, cy: 2, r: 30 } }).length") == 4)
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        d0 = fx["data"]; show(pg, [d0["xm"], d0["ym"]]); mp = cl(pg, [d0["xm"], d0["ym"]])   # on screen: the real mouse taps it
        pg.mouse.click(mp[0], mp[1]); pg.wait_for_timeout(60)
        sel = pg.evaluate("window.__pw.ink.selection()")
        check("Select taps the fixed arc: it alone is selected", sel and sel["ids"] == [fx["id"]], sel)
        pg.evaluate("window.__pw.ink.clearSelection()")
        ep = cl(pg, [d0["x2"], d0["y2"]])
        pg.mouse.move(ep[0] - 20, ep[1] - 20); pg.mouse.move(ep[0], ep[1]); pg.wait_for_timeout(40)
        hr = pg.evaluate("() => { const h = document.getElementById('handleRing'); return !!h && !h.hidden; }")
        check("the pen hovering on its end shows no handle ring", hr is False, hr)
        pg.mouse.click(mp[0], mp[1]); pg.wait_for_timeout(60)
        pg.mouse.move(mp[0], mp[1]); pg.mouse.down(); pg.mouse.move(mp[0] + 20, mp[1] + 15, steps=3); pg.mouse.move(mp[0] + 40, mp[1] + 30, steps=3); pg.mouse.up(); pg.wait_for_timeout(60)
        mv = recs(pg); dd = mv[0]["data"] if mv else {}
        check("Select drags it whole: all three points move by the same 40, 30, still a fixed arc",
              len(mv) == 1 and all(abs(dd[a] - d0[a] - 40) < 0.11 for a in ("x1", "xm", "x2")) and all(abs(dd[a] - d0[a] - 30) < 0.11 for a in ("y1", "ym", "y2"))
              and dd.get("fixed") is True and dd["type"] == "arc", [d0, dd])
        pg.evaluate("() => { const c = document.querySelector('.selChips .chip[data-act=\"copy\"]'); if (c) c.click(); }"); pg.wait_for_timeout(40)
        pg.evaluate("window.__pw.ink.pasteAt('s0', 400, 300)"); pg.wait_for_timeout(60)
        ps = recs(pg)
        check("Copy then Paste: the pasted copy is still a fixed arc", len(ps) == 2 and all(x["data"].get("fixed") is True and x["data"]["type"] == "arc" for x in ps), ps)
        pg.evaluate("window.__pw.ink.clearSelection()"); pg.click("#tool-pen"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ I: what is saved, thumbs and the PDF
        group[0] = "I. records, thumb, PDF"
        toggle(pg, "compass"); close_panel(pg)
        c = C(pg); pen(pg, turn_path(c["c1"], c["geo"]["c2"], 370))  # and a circle
        rs = recs(pg)
        check("strokesOf carries the arcs and the circle and nothing else (3 'shape' records), the compass still out",
              len(rs) == 3 and sorted(x["data"]["type"] for x in rs) == ["arc", "arc", "circle"] and C(pg) is not None, [x["data"]["type"] for x in rs])
        th = pg.evaluate("""() => { const s = window.__pw.ink.thumbSvg('s0'); return { paths: s.querySelectorAll('g.pen > g > path').length, circles: s.querySelectorAll('g.pen > g > circle:not(.needle)').length,
          needles: s.querySelectorAll('g.pen > g > circle.needle').length, compass: s.querySelectorAll('.compass, .toolLayer, polygon, line').length }; }""")
        check("the thumb draws the 2 arcs and the circle (U5c: each a <g> with its needle mark) and no compass", th == {"paths": 2, "circles": 1, "needles": 3, "compass": 0}, th)
        pdf64 = pg.evaluate("""async () => { const m = await import('./js/pdfout.js');
          const blob = await m.buildPdf([{ id: 's0', orientation: 'portrait', background: 'blank', pdf_path: null }], 'Compass');
          const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode(...b.subarray(i, i + 8192));
          return btoa(s); }""")
        doc = fitz.open(stream=base64.b64decode(pdf64), filetype="pdf"); page = doc[0]
        drs = page.get_drawings(); kpt = 595.28 / 794
        items = [it for dr in drs if dr.get("type") != "f" for it in dr["items"]]     # the strokes (U5c: the needle marks are fills)
        def circ_of(dA):                                            # an arc record's circle (centre, radius), page px
            ax, ay = dA["x1"], dA["y1"]; bx, by = dA["xm"], dA["ym"]; cx_, cy_ = dA["x2"], dA["y2"]
            D = 2 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
            ox = ((ax * ax + ay * ay) * (by - cy_) + (bx * bx + by * by) * (cy_ - ay) + (cx_ * cx_ + cy_ * cy_) * (ay - by)) / D
            oy = ((ax * ax + ay * ay) * (cx_ - bx) + (bx * bx + by * by) * (ax - cx_) + (cx_ * cx_ + cy_ * cy_) * (bx - ax)) / D
            return ox, oy, math.hypot(ax - ox, ay - oy)
        def on(q, cc): return abs(math.hypot(q.x - cc[0] * kpt, q.y - cc[1] * kpt) - cc[2] * kpt) < 0.3
        arcs = [x["data"] for x in rs if x["data"]["type"] == "arc"]; cd = [x["data"] for x in rs if x["data"]["type"] == "circle"][0]
        circles = [circ_of(a) for a in arcs] + [(cd["cx"], cd["cy"], cd["r"])]
        ok_arcs = [any(it[0] == "c" and on(it[1], cc) and on(it[-1], cc) and math.hypot(it[1].x - a["x1"] * kpt, it[1].y - a["y1"] * kpt) < 0.3 for it in items)
                   for a, cc in zip(arcs, circles)]
        check("Share as PDF (buildPdf) draws both compass arcs on their circles, from their start (vector curves, in pt)", ok_arcs == [True, True],
              [ok_arcs, [(it[0], round(it[1].x, 1), round(it[1].y, 1)) for it in items]])
        cc = circles[-1]
        check("... and the compass circle all the way round (4 or more curves on it)", sum(1 for it in items if it[0] == "c" and on(it[1], cc) and on(it[-1], cc)) >= 4, len(items))
        check("... and not the compass: every piece drawn is a curve on one of the three circles, no text",
              items and all(it[0] == "c" and any(on(it[1], c_) and on(it[-1], c_) for c_ in circles) for it in items) and page.get_text().strip() == "",
              [[(it[0]) for it in items], page.get_text()])
        doc.close()

        # ------------------------------------------------------------ J: two tools, one press
        group[0] = "J. overlap"
        pg.evaluate("window.__T.clear('s0')")
        toggle(pg, "compass"); toggle(pg, "compass"); toggle(pg, "ruler"); close_panel(pg)   # compass fresh, the ruler out last (on top)
        r0 = R(pg); c = C(pg)
        q = needle_pt(c); dn = [0, r0["o"][1] + r0["w"] / 2 - c["c1"][1]]           # the needle onto the ruler's middle line
        check("the ruler came out last: it is on top", C(pg)["order"] == ["compass", "ruler"], C(pg)["order"])
        pen(pg, [q, addv(q, [0, -20])])                              # a press clear of the ruler: the compass, now on top
        c = C(pg); q = needle_pt(c)
        pen(pg, [q, addv(q, lerp([0, 0], dn, 0.5)), addv(q, dn)])
        c = C(pg); r1 = R(pg)
        over = c["c1"]
        inside = 0 < (over[1] - r1["o"][1]) < r1["w"] and r1["o"][0] < over[0] < r1["o"][0] + r1["len"]
        check("the compass touched last is on top; its needle now sits over the ruler's body", c["order"] == ["ruler", "compass"] and inside and r1["o"] == r0["o"], [c["order"], over, r1])
        pen(pg, [over, addv(over, [30, 0])]); c1 = C(pg); r2 = R(pg)
        check("a press where both lie goes to the compass (the needle moves, the ruler stays)", abs(c1["c1"][0] - over[0] - 30) < 1e-6 and r2["o"] == r0["o"], [c1["c1"], r2["o"]])
        far = local(pg, r0["len"] - 30, r0["w"] / 2)
        pen(pg, [far, addv(far, [0, 1])]); r3 = R(pg)              # a touch on the ruler, clear of the compass
        check("touching the ruler puts it on top", C(pg)["order"] == ["compass", "ruler"], C(pg)["order"])
        over = C(pg)["c1"]
        pen(pg, [over, addv(over, [-25, 0])]); c2_ = C(pg); r4 = R(pg)
        check("now the same overlap goes to the ruler (it moves, the compass stays)", abs(r4["o"][0] - r3["o"][0] + 25) < 1e-6 and c2_["c1"] == over, [r3["o"], r4["o"], c2_["c1"], over])
        check("no records from any of it", recs(pg) == [])
        lay = pg.evaluate("[...window.__T.sheet('s0').querySelector(':scope > svg.toolLayer').children].filter((e) => e.tagName === 'g').map((e) => e.getAttribute('class'))")
        check("... and the layer draws them in that order (the ruler over the compass)", lay == ["compass", "ruler"], lay)
        show(pg, C(pg)["geo"]["c2"])
        pg.screenshot(path=str(SHOTS / "compass-out.png"))

        # ------------------------------------------------------------ L: U5c, the needle mark and the constructions app's stick feel
        group[0] = "L. U5c needle mark + feel"
        if R(pg) is not None: toggle(pg, "ruler")
        if C(pg) is not None: toggle(pg, "compass")
        close_panel(pg); pg.evaluate("window.__T.clear('s0')"); pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(60)
        zz = z(pg)
        PINK = "#FF0C84"
        def arc_data(cx, cy, r, a0, a1, fixed=True):                 # three points rounded to 0.01, as the compass lands them
            at = lambda a: [round(cx + r * math.cos(math.radians(a)), 2), round(cy + r * math.sin(math.radians(a)), 2)]
            p1, pm, p2 = at(a0), at((a0 + a1) / 2), at(a1)
            d = {"type": "arc", "x1": p1[0], "y1": p1[1], "xm": pm[0], "ym": pm[1], "x2": p2[0], "y2": p2[1]}
            if fixed: d["fixed"] = True
            return d
        def put(data, style=None):
            return pg.evaluate("""([d, s]) => { const r = { id: crypto.randomUUID(), page_id: 's0', seq: Date.now() + Math.floor(Math.random() * 1000), kind: 'shape',
              style: s || { colour: '#FF0C84', width: 2.5, dash: 'solid', opacity: 1 }, data: d }; window.__pw.ink.put('s0', [r]); return r.id; }""", [data, style])
        def el_of(i):
            return pg.evaluate("""(id) => { const e = window.__T.sheet('s0').querySelector(`svg.ink [data-id="${id}"]`); if (!e) return null;
              const n = e.querySelector('circle.needle');
              return { tag: e.tagName, kids: [...e.children].map((k) => k.tagName + (k.getAttribute('class') ? '.' + k.getAttribute('class') : '')), group: e.parentNode.getAttribute('class'),
                       needle: n ? { cx: +n.getAttribute('cx'), cy: +n.getAttribute('cy'), r: +n.getAttribute('r'), fill: n.getAttribute('fill'), stroke: n.getAttribute('stroke'),
                                     op: n.getAttribute('fill-opacity'), shown: n.getAttribute('display') !== 'none' } : null }; }""", i)
        def near(a, b, tol): return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol
        def needle_to(want, up=True):                                 # drag the needle by its arm so it would land on want
            c = C(pg); q = needle_pt(c); dlt = subv(want, c["c1"])
            pen(pg, [q, addv(q, lerp([0, 0], dlt, 0.5)), addv(q, dlt)], up=False)
            mid_ = pg.evaluate("window.__T.rings()")
            if up: pen_up(pg, addv(q, dlt))
            return C(pg), mid_
        def tip_to(want):                                             # drag the pencil so its tip would land on want
            c = C(pg); p0 = pencil_pt(c); dlt = subv(want, c["geo"]["c3"])
            pen(pg, [p0, addv(p0, lerp([0, 0], dlt, 0.5)), addv(p0, dlt)], up=False)
            mid_ = pg.evaluate("window.__T.rings()")
            pen_up(pg, addv(p0, dlt))
            return C(pg), mid_
        def ruler_to(y):                                              # drag the (level) ruler straight so edge A would sit at y
            r0 = R(pg); g0 = local(pg, 300, r0["w"] / 2); dy = y - r0["o"][1]
            pen(pg, [g0, [g0[0], g0[1] + dy / 2], [g0[0], g0[1] + dy]])
            return R(pg)

        # the needle mark on the page, in the thumb and in the PDF
        A = arc_data(400, 500, 100, 30, 150)                         # below its centre (400, 500): ends (486.6, 550) and (313.4, 550)
        aid = put(A)
        tid = put(arc_data(200, 250, 80, 0, 90), {"colour": "#0D0DFF", "width": 6, "dash": "solid", "opacity": 1})
        hid = put(arc_data(600, 650, 70, 180, 300), {"colour": "#FFD400", "width": 12, "dash": "solid", "opacity": 0.4})
        cid = put({"type": "circle", "cx": 600, "cy": 300, "r": 60, "fixed": True})
        nid = put(arc_data(200, 850, 80, 0, 120, fixed=False))
        pid = put({"type": "circle", "cx": 600, "cy": 950, "r": 50})
        e = el_of(aid); n = e and e["needle"]
        check("a fixed arc is a <g> of its path and its needle mark (circle.needle), in the pen group",
              e and e["tag"] == "g" and e["kids"] == ["path", "circle.needle"] and e["group"] == "pen", e)
        check("... the dot at the arc's centre (0.1 px), radius max(1.6, w x 0.55) = 1.6 at width 2.5, filled in the arc's colour, no stroke",
              n and near([n["cx"], n["cy"]], [400, 500], 0.1) and n["r"] == 1.6 and n["fill"] == PINK and n["stroke"] == "none" and n["shown"] and n["op"] is None, n)
        e = el_of(tid); n = e and e["needle"]
        check("a width-6 arc's dot: radius 6 x 0.55 = 3.3, in its own colour", n and near([n["cx"], n["cy"]], [200, 250], 0.1) and n["r"] == 3.3 and n["fill"] == "#0D0DFF", e)
        e = el_of(hid); n = e and e["needle"]
        check("a highlighter arc's dot is a highlighter dot: in the see-through group, its colour, radius 6.6, the group does the 0.4",
              e and e["group"] == "hlo" and n and near([n["cx"], n["cy"]], [600, 650], 0.1) and n["r"] == 6.6 and n["fill"] == "#FFD400" and n["op"] is None, e)
        e = el_of(cid); n = e and e["needle"]
        check("a fixed circle is a <g> of its <circle> and the dot at its centre", e and e["kids"] == ["circle", "circle.needle"] and n and [n["cx"], n["cy"], n["r"]] == [600, 300, 1.6], e)
        e1 = el_of(nid); e2 = el_of(pid)
        check("a snapped (not fixed) arc and circle: a plain <path> and <circle>, no dot", e1 and e1["tag"] == "path" and e1["needle"] is None
              and e2 and e2["tag"] == "circle" and e2["needle"] is None, [e1, e2])
        th = pg.evaluate("""() => [...window.__pw.ink.thumbSvg('s0').querySelectorAll('circle.needle')].map((n) => [+n.getAttribute('cx'), +n.getAttribute('cy'), +n.getAttribute('r'), n.getAttribute('fill')])""")
        want_dots = [[400, 500, 1.6, PINK], [200, 250, 3.3, "#0D0DFF"], [600, 650, 6.6, "#FFD400"], [600, 300, 1.6, PINK]]
        check("the page thumb draws the same 4 needle marks (none for the snapped shapes)",
              len(th) == 4 and all(any(near(t[:2], w_[:2], 0.1) and t[2] == w_[2] and t[3] == w_[3] for t in th) for w_ in want_dots), th)
        show(pg, [400, 520]); pg.screenshot(path=str(SHOTS / "u5c-needle-marks.png"))
        pdf64 = pg.evaluate("""async () => { const m = await import('./js/pdfout.js');
          const blob = await m.buildPdf([{ id: 's0', orientation: 'portrait', background: 'blank', pdf_path: null }], 'Needle');
          const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode(...b.subarray(i, i + 8192));
          return btoa(s); }""")
        doc = fitz.open(stream=base64.b64decode(pdf64), filetype="pdf"); kpt = 595.28 / 794
        fills = [dr for dr in doc[0].get_drawings() if dr.get("type") == "f"]
        def pdf_dot(cx, cy, r):
            for dr in fills:
                rc = dr["rect"]
                if abs((rc.x0 + rc.x1) / 2 - cx * kpt) < 0.15 and abs((rc.y0 + rc.y1) / 2 - cy * kpt) < 0.15 and abs(rc.width - 2 * r * kpt) < 0.15: return dr
            return None
        d1 = pdf_dot(400, 500, 1.6); d2 = pdf_dot(600, 650, 6.6)
        check("Share as PDF: a filled circle at each of the 4 centres (PyMuPDF get_drawings), and no other fill",
              len(fills) == 4 and all(pdf_dot(w_[0], w_[1], w_[2]) for w_ in want_dots), [(round(f["rect"].x0, 1), round(f["rect"].y0, 1), round(f["rect"].width, 2)) for f in fills])
        check("... in the shape's colour (pink, opaque), the highlighter's yellow at 0.4",
              d1 and d2 and all(abs(a - b_) < 0.01 for a, b_ in zip(d1["fill"], (1, 12 / 255, 132 / 255))) and (d1.get("fill_opacity") in (None, 1, 1.0))
              and all(abs(a - b_) < 0.01 for a, b_ in zip(d2["fill"], (1, 212 / 255, 0))) and abs((d2.get("fill_opacity") or 0) - 0.4) < 0.01,
              [d1 and (d1["fill"], d1.get("fill_opacity")), d2 and (d2["fill"], d2.get("fill_opacity"))])
        doc.close()

        # the centre is a stick point: the ruler's edge (14 px) and the needle (16 px) stick to it; not a snapped arc's
        pg.evaluate("window.__T.clear('s0')"); put(A)
        pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(60)
        toggle(pg, "ruler"); close_panel(pg)
        r1 = ruler_to(500 + 10 / zz)
        check("the ruler's edge released 10 px from a fixed arc's centre sticks to it",
              r1["stuck"] is not None and near(r1["stuck"]["p"], [400, 500], 0.02) and edge_perp_(r1, r1["stuck"]["p"]) < 1e-6, r1)
        r1 = ruler_to(500 + 13 / zz); r2 = ruler_to(500 + 15 / zz)
        check("... the ruler's reach is 14 px: 13 px sticks, 15 px does not", r1["stuck"] is not None and r2["stuck"] is None, [r1["stuck"], r2["stuck"]])
        pg.evaluate("window.__T.clear('s0')"); put({"type": "circle", "cx": 400, "cy": 500, "r": 100, "fixed": True})
        r1 = ruler_to(500 + 10 / zz)
        check("... and to a fixed circle's centre", r1["stuck"] is not None and r1["stuck"]["p"] == [400, 500], r1)
        pg.evaluate("window.__T.clear('s0')"); put(arc_data(400, 500, 100, 30, 150, fixed=False))
        r1 = ruler_to(500 + 10 / zz)
        check("... never to a snapped (not fixed) arc's centre", r1["stuck"] is None, r1)
        toggle(pg, "ruler"); toggle(pg, "compass"); close_panel(pg)
        c1, mid_ = needle_to([400, 500 - 15 / zz])
        check("the needle released 15 px from a snapped arc's centre stays where it was put (no stick, no ring)",
              c1["stuck"] is None and near(c1["c1"], [400, 500 - 15 / zz], 1e-6) and mid_ == [], [c1, mid_])
        pg.evaluate("window.__T.clear('s0')"); put(A)
        c1, mid_ = needle_to([400, 500 - 15 / zz])
        check("the needle released 15 px from a fixed arc's centre lands on it, a ring marks it", near(c1["c1"], [400, 500], 0.02) and c1["stuck"] is not None
              and len(mid_) == 1 and near(mid_[0], [400, 500], 0.02), [c1["c1"], mid_])
        c1, _ = needle_to([400, 500 - 17 / zz])
        check("... the point reach is 16 px: released 17 px off it stays free", c1["stuck"] is None and near(c1["c1"], [400, 500 - 17 / zz], 1e-6), c1)
        pg.evaluate("window.__T.clear('s0')"); put({"type": "circle", "cx": 400, "cy": 500, "r": 100, "fixed": True})
        c1, _ = needle_to([400 + 12 / zz, 500 - 9 / zz])
        check("the needle lands on a fixed circle's centre", c1["c1"] == [400, 500] and c1["stuck"] == [400, 500], c1)

        # the needle and the tip settle ON a curve (9 px), the way the constructions app's snapPoint does
        pg.evaluate("window.__T.clear('s0')"); pg.evaluate("window.__T.line('s0', 250, 400, 650, 400)")
        c1, mid_ = needle_to([450, 400 + 8 / zz])
        check("the needle released 8 px from the MIDDLE of a line lands on the line (450, 400), a ring marks it",
              near(c1["c1"], [450, 400], 1e-6) and c1["stuck"] is not None and len(mid_) == 1 and near(mid_[0], [450, 400], 1e-3), [c1, mid_])
        c1, _ = needle_to([450, 400 + 10 / zz])
        check("... the curve reach is 9 px: 10 px off the line stays free", c1["stuck"] is None and near(c1["c1"], [450, 400 + 10 / zz], 1e-6), c1)
        pg.evaluate("window.__T.clear('s0')"); put(arc_data(450, 600, 100, 180, 360))   # over the top: (350, 600) to (550, 600) through (450, 500)
        u300 = [math.cos(math.radians(300)), math.sin(math.radians(300))]; P = [450 + 100 * u300[0], 600 + 100 * u300[1]]
        c0 = C(pg); c1, mid_ = tip_to(addv(P, [8 / zz * u300[0], 8 / zz * u300[1]]))
        check("the pencil tip released 8 px outside a fixed arc lands ON the arc (the width = needle to that point), a ring while it was set",
              near(c1["geo"]["c3"], P, 0.05) and abs(c1["r"] - dist(c0["c1"], P)) < 0.05 and any(near(m_, P, 0.05) for m_ in mid_), [c1["geo"]["c3"], P, mid_])
        c1, _ = tip_to(addv(P, [10 / zz * u300[0], 10 / zz * u300[1]]))
        check("... 10 px outside it stays free", near(c1["geo"]["c3"], addv(P, [10 / zz * u300[0], 10 / zz * u300[1]]), 1e-6), [c1["geo"]["c3"], P])
        Q = [450 + 100 * math.cos(math.radians(150)), 600 + 100 * math.sin(math.radians(150))]   # on the circle, off the arc's sweep
        c1, _ = tip_to(addv(Q, [0, 5 / zz]))
        check("... off the arc's sweep (its circle's other half) the tip stays free", near(c1["geo"]["c3"], addv(Q, [0, 5 / zz]), 1e-6), [c1["geo"]["c3"], Q])

        # the dot and the stick point ride a Select move (derived, nothing stored)
        pg.evaluate("window.__T.clear('s0')"); aid = put(A)
        toggle(pg, "compass"); close_panel(pg)
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        show(pg, [A["xm"], A["ym"]]); mp = cl(pg, [A["xm"], A["ym"]])
        pg.mouse.click(mp[0], mp[1]); pg.wait_for_timeout(60)
        pg.mouse.move(mp[0], mp[1]); pg.mouse.down(); pg.mouse.move(mp[0] + 20, mp[1] + 15, steps=3); pg.mouse.move(mp[0] + 40, mp[1] + 30, steps=3); pg.mouse.up(); pg.wait_for_timeout(60)
        mv = recs(pg); e = el_of(aid); n = e and e["needle"]
        check("Select drags the fixed arc by (40, 30): its dot moves with it to (440, 530), the record has no new fields",
              len(mv) == 1 and sorted(mv[0]["data"].keys()) == sorted(A.keys()) and n and near([n["cx"], n["cy"]], [440, 530], 0.15), [mv, n])
        pg.evaluate("window.__pw.ink.clearSelection()"); pg.click("#tool-pen"); pg.wait_for_timeout(40)
        pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(60)
        toggle(pg, "compass"); close_panel(pg)
        c1, _ = needle_to([440, 530 - 12 / zz])
        check("... and its centre is a stick point where it is now", near(c1["c1"], [440, 530], 0.15) and c1["stuck"] is not None, c1)
        toggle(pg, "compass"); close_panel(pg)

        # the turn: the 45 degree click is 1.2 degrees wide (the constructions app's)
        pg.evaluate("window.__T.clear('s0')")
        toggle(pg, "ruler"); close_panel(pg)
        r0 = R(pg); ctr = local(pg, r0["len"] / 2, r0["w"] / 2)
        kn = lambda: local(pg, R(pg)["len"] + R(pg)["pad"] + R(pg)["knobOff"], R(pg)["w"] / 2)
        pen(pg, turn_path(ctr, kn(), -44))
        check("a free turn 1 degree short of 45 clicks onto 45", abs(R(pg)["ang"] + math.pi / 4) < 1e-9, math.degrees(R(pg)["ang"]))
        pen(pg, turn_path(ctr, kn(), 45))
        check("... back to level", abs(R(pg)["ang"]) < 1e-9, math.degrees(R(pg)["ang"]))
        pen(pg, turn_path(ctr, kn(), -43))
        check("a turn 2 degrees short of 45 stays where it is (43)", abs(math.degrees(R(pg)["ang"]) + 43) < 0.05, math.degrees(R(pg)["ang"]))
        toggle(pg, "ruler"); close_panel(pg)
        pg.evaluate("window.__T.clear('s0')")

        # ------------------------------------------------------------ K: closing the note
        group[0] = "K. close + reopen"
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(50)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        check("closing the note puts both tools away (no layer), the panel closes, the button unpressed",
              R(pg) is None and C(pg) is None and pg.locator("svg.toolLayer").count() == 0 and pg.locator("#toolsPanel").is_hidden() and pressed(pg, "#drawToolsBtn") == "false")
        open_note(pg)
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
        rows = pg.evaluate("[...document.querySelectorAll('#toolsPanel .trow')].map((b) => b.getAttribute('aria-pressed'))")
        check("reopened: no tool out, every row unpressed", R(pg) is None and C(pg) is None and pg.locator("svg.toolLayer").count() == 0 and rows == ["false"] * 4, rows)
        close_panel(pg)
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
