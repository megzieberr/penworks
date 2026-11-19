# PenWorks pw-v9j checks: the QUICK GRAPH, unit 2 (sin, cos and tan on the page; _docs/PENWORKS-GRAPH-PLAN.md, Tool 1,
# build step 2; the signed-off look: _build/graph/graph-mock.html).
# Run: python -E -P tests/test_graph.py        (local mode only: ?local=1, Supabase is never touched)
# The harness of tests/test_axes.py: one note of 3 blank pages seeded into the localStorage twin, 1280 x 800 (the tablet
# landscape size); pen gestures are PointerEvents (pointerType 'pen') fired on the desk. The PDF is read with PyMuPDF, the
# shared picture with Pillow.
# What it proves: the Graph row under Axes opens the Graph card (the row pressed), ONE family "sin, cos, tan" with six
# blocks and nothing else; each block lands ONE 'graph' record on the current page (the panel closes), axes black, the curve
# in the pen's colour and width, a third of the page wide, 0 to 360 with the y-axis at the left; marks at 90, 180, 270, 360
# only, in Caveat glyphs, drawn BEFORE the curve with no stroke (no halo); tan and -tan carry dashed asymptotes at 90 and
# 270; the curve is the real function; undo removes it in one step; the Axes pill hides and shows the axes, marks and letters
# (one undo step each); a box picks the whole graph, moves and resizes it, a turn leaves it; the left handle opens the x-axis
# smoothly to -360 (marks -90 .. -360 with a real minus), stops there and comes back to 0, the y-axis and the scale staying;
# a reload keeps it; it is in the page thumb, the PDF (glyphs filled, curve stroked) and a shared picture; Caveat comes from
# the app's own fonts/ folder and nothing asks Google for it.
# Pictures for the report go to _build/graph/unit2/.
# pw-v9l (group I): the Cubic row (cubic, −cubic): plain axes crossing in the middle, no marks, no left handle; select,
# Axes pill, colour, move, resize, a second cubic curve, mismatched families land a new graph, a cubic on her stamp; thumb,
# PDF, shared picture, reload. Its pictures go to _build/graph/cubic/.
# pw-v9m (group J, unit 3 "tap the curve"): a select tap on a curve picks that curve alone (two handles, Axes + Delete);
# slide, squash, widen, taller, the limits, tan's asymptotes travelling, marks staying, two curves (colour, Delete), all
# eight kinds, thumb, PDF, shared picture, reload. Its pictures go to _build/graph/unit3/.
import sys, subprocess, time, pathlib, math, base64, io, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8832
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "graph" / "unit2"
W, H = 794, 1123
BLUE = "#0D0DFF"
KINDS = ["sin", "-sin", "cos", "-cos", "tan", "-tan"]
NAMES = ["sin", "−sin", "cos", "−cos", "tan", "−tan"]
CUBICS = ["cubic", "-cubic"]                                       # pw-v9l

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-15T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'blank', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Maths', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Graphs', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
SHARE_STUB = """
  navigator.canShare = () => true;
  navigator.share = async (d) => { window.__shared = d; };
"""
HELP = """async () => {
  window.__P = await import('./js/page.js');
  window.__GR = await import('./js/graph.js');
  const T = window.__T = {};
  T.z = () => window.__P.view().z;
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.client = (id, x, y) => { const r = T.sheet(id).getBoundingClientRect(), z = T.z(); return [r.left + x * z, r.top + y * z]; };
  T.ev = (type, id, kind, x, y, buttons) => document.getElementById('desk').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: kind,
    isPrimary: true, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0,
    buttons: buttons !== undefined ? buttons : type === 'pointerup' ? 0 : 1, clientX: x, clientY: y, screenX: x + 10, screenY: y + 80 }));
  T.pen = (id, pts, up = true, pid = 31) => {
    const c = pts.map((p) => T.client(id, p[0], p[1]));
    T.ev('pointerdown', pid, 'pen', c[0][0], c[0][1]);
    for (const q of c.slice(1)) T.ev('pointermove', pid, 'pen', q[0], q[1]);
    if (up) T.ev('pointerup', pid, 'pen', c[c.length - 1][0], c[c.length - 1][1]);
  };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.clear = (id) => { const op = window.__pw.ink.erasePageOp(id); if (op) op.redo(); };
  T.geo = (rid) => { const r = T.recs('s0').find((x) => x.id === rid); const g = r ? window.__pw.ink.graphGeom(r) : null;
    return g && { box: g.box, left: g.left, xl: g.xl, xr: g.xr, yh: g.yh, on: g.on, labels: g.labels.map((l) => ({ t: l.t, x: l.x, y: l.y, size: l.size, cls: l.cls, b: l.b })),
      asym: g.asym.map((a) => a.x), runs: g.curves.map((c) => c.runs.map((r) => [r[0], r[r.length - 1], r.length])), lines: g.lines, ticks: g.ticks }; };
  T.el = (rid, root) => { const g = (root || T.sheet('s0').querySelector('svg.ink')).querySelector(`[data-id="${rid}"]`); if (!g) return null;
    const kids = [...g.children];
    return { tag: g.tagName, type: g.dataset.type, group: g.parentNode.getAttribute('class'),
      parts: kids.map((k) => ({ cls: k.getAttribute('class'), t: k.dataset.t || null, stroke: k.getAttribute('stroke'), fill: k.getAttribute('fill'),
        width: k.getAttribute('stroke-width'), dash: k.getAttribute('stroke-dasharray'), tag: k.tagName, dl: (k.getAttribute('d') || '').length })),
      texts: g.querySelectorAll('text').length }; };
  T.sgeo = (rid) => { const r = T.recs('s0').find((x) => x.id === rid); if (!r) return null;   // pw-v9k: an axes stamp and the curves it carries
    const s = window.__GR.stampGeom(r), a = window.__pw.ink.axesGeom(r);
    return { box: a && a.box, asym: s ? s.asym.map((q) => q.x) : [], runs: s ? s.curves.map((c) => c.runs.map((u) => [u[0], u[u.length - 1], u.length])) : [],
      ys: s ? s.curves.map((c) => c.runs.flat().map((q) => q[1])) : [], xs: s ? s.curves.map((c) => c.runs.flat().map((q) => q[0])) : [] }; };
  T.vis = (idx) => { const b = document.getElementById('desk').getBoundingClientRect(), a = window.__P.pagePoint(idx, b.left, b.top), c = window.__P.pagePoint(idx, b.right, b.bottom);
    const cx = (v) => Math.max(0, Math.min(794, v)), cy = (v) => Math.max(0, Math.min(1123, v));
    return [cx(a[0]), cy(a[1]), cx(c[0]), cy(c[1])]; };
  return 1;
}"""
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
  return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height, shown: !e.hidden && b.width > 0 }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def rect(pg, sel): return pg.evaluate(RECT, sel)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def z(pg): return pg.evaluate("window.__T.z()")
def recs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.recs(id)", pid)
def graphs(pg, pid="s0"): return [r for r in recs(pg, pid) if r["kind"] == "graph"]
def el(pg, i): return pg.evaluate("(i) => window.__T.el(i)", i)
def geo(pg, i): return pg.evaluate("(i) => window.__T.geo(i)", i)
def pen(pg, pts, up=True, page="s0"): pg.evaluate("([id, p, up]) => window.__T.pen(id, p, up, 31)", [page, pts, up])
def pen_on(pg, pts, page="s0"):                                   # the same pen (no new down): moves through pts, then lifts
    pg.evaluate("""([id, p]) => { const T = window.__T, c = p.map((q) => T.client(id, q[0], q[1]));
      for (const q of c) T.ev('pointermove', 31, 'pen', q[0], q[1]); const l = c[c.length - 1]; T.ev('pointerup', 31, 'pen', l[0], l[1]); }""", [page, pts])
def addv(a, b): return [a[0] + b[0], a[1] + b[1]]
def subv(a, b): return [a[0] - b[0], a[1] - b[1]]
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def open_panel(pg):
    if pg.locator("#toolsPanel").is_hidden(): pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
def close_panel(pg): pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
def open_gcard(pg):
    open_panel(pg)
    if pg.locator("#graphCard").count() == 0 or pg.locator("#graphCard").is_hidden(): pg.click("#trow-graph"); pg.wait_for_timeout(60)
def gcard_shown(pg): return pg.locator("#graphCard").count() > 0 and pg.locator("#graphCard").is_visible()
def panel_shown(pg): return pg.locator("#toolsPanel").is_visible()
def bid(k): return "#gblk-" + k.replace("-", "n")
def land(pg, kind):
    open_gcard(pg); pg.click(bid(kind)); pg.wait_for_timeout(80)
def sel(pg): return pg.evaluate("window.__pw.ink.selection()")
def clear_sel(pg): pg.evaluate("window.__pw.ink.clearSelection()")
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(60)
def show(pg, p, page="s0"):
    pg.evaluate("""([id, p]) => { const c = window.__T.client(id, p[0], p[1]);
      const d = document.getElementById('desk'), b = d.getBoundingClientRect();
      d.dispatchEvent(new WheelEvent('wheel', { deltaY: c[1] - (b.top + b.height / 2), clientX: b.left + 200, clientY: b.top + 200, bubbles: true, cancelable: true })); }""", [page, p])
    pg.wait_for_timeout(80)
def pdf_of(pg, name):
    b64 = pg.evaluate("""async (n) => { const m = await import('./js/pdfout.js');
      const blob = await m.buildPdf([{ id: 's0', orientation: 'portrait', background: 'blank', pdf_path: null }], n);
      const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode(...b.subarray(i, i + 8192));
      return btoa(s); }""", name)
    return fitz.open(stream=base64.b64decode(b64), filetype="pdf")
def shot(pg, name, clip=None):
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(SHOTS / name), clip=clip)
def box_select(pg, b, m=20):
    pen(pg, [[b[0] - m, b[1] - m], [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], [b[2] + m, b[3] + m]]); pg.wait_for_timeout(50)
def rgb(c): return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
def bluish(p): return p[2] > 150 and p[0] < 120 and p[1] < 120
def darkish(p): return p[0] < 110 and p[1] < 110 and p[2] < 110
def any_px(img, cx, cy, r, fn):
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            x, y = int(round(cx + dx)), int(round(cy + dy))
            if 0 <= x < img.width and 0 <= y < img.height and fn(img.getpixel((x, y))[:3]): return True
    return False

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(SHARE_STUB)
        pg = ctx.new_page(); errs = []; reqs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("request", lambda r: reqs.append(r.url))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        open_note(pg); pg.evaluate(HELP)
        pg.click(f'#tray .sw[data-colour="{BLUE}"]'); pg.wait_for_timeout(40)   # the pen in Blue (the mock's)
        pen_w = pg.evaluate("window.__pw.tray().pen.width")

        # ------------------------------------------------------------ A: the row and the card
        group[0] = "A. row + card"
        open_panel(pg)
        rows = pg.evaluate("[...document.querySelectorAll('#toolsPanel .trow')].map((b) => b.id)")
        check("the Tools panel has a Graph row right under Axes", rows[-2:] == ["trow-axes", "trow-graph"], rows)
        row = pg.evaluate("(() => { const b = document.getElementById('trow-graph'); return [b.textContent.trim(), b.disabled, b.getAttribute('aria-pressed'), b.getAttribute('aria-expanded')]; })()")
        check("it reads 'Graph…', is live, not pressed, aria-expanded false", row == ["Graph…", False, "false", "false"], row)
        pg.click("#trow-graph"); pg.wait_for_timeout(60)
        check("a tap opens the Graph card; the panel stays open; the row looks pressed (aria-pressed true) and says aria-expanded true",
              gcard_shown(pg) and panel_shown(pg) and pg.get_attribute("#trow-graph", "aria-pressed") == "true" and pg.get_attribute("#trow-graph", "aria-expanded") == "true")
        gr, pr = rect(pg, "#graphCard"), rect(pg, "#toolsPanel")
        check("the card sits beside the panel on the desk side (8 px left of it), its top level with the panel's, on screen",
              abs(gr["r"] - (pr["l"] - 8)) < 1 and abs(gr["t"] - pr["t"]) < 1 and gr["l"] >= 8 and gr["b"] <= 792, [gr, pr])
        info = pg.evaluate("""() => { const c = document.getElementById('graphCard');
          return { title: c.querySelector('.gTitle').textContent, fams: [...c.querySelectorAll('.gFam')].map((e) => e.textContent),
            blocks: [...c.querySelectorAll('.gBlk')].map((b) => [b.dataset.kind, b.querySelector('b').textContent, !!b.querySelector('svg path'), Math.round(b.getBoundingClientRect().width)]),
            text: c.textContent }; }""")
        check("TWO family rows (pw-v9l), headed 'sin, cos, tan' then 'Cubic'", info["title"] == "Graph" and info["fams"] == ["sin, cos, tan", "Cubic"], info["fams"])
        check("six trig blocks then two cubic blocks: sin, −sin, cos, −cos, tan, −tan, cubic, −cubic (the real minus), each a picture and its name, 80 px wide",
              [x[0] for x in info["blocks"]] == KINDS + CUBICS and [x[1] for x in info["blocks"]] == NAMES + ["cubic", "−cubic"] and all(x[2] and x[3] == 80 for x in info["blocks"]), info["blocks"])
        check("no Parabola, Hyperbola or Exponential row (no dead buttons)", not re.search("Parabola|Hyperbola|Exponential", info["text"]), info["text"])
        tb = pg.evaluate("[...document.querySelectorAll('#graphCard .gBlk')].map((b) => b.querySelectorAll('line[stroke-dasharray]').length)")
        check("the two tan blocks show their dashed asymptotes, the others none", tb == [0, 0, 0, 0, 2, 2, 0, 0], tb)
        rws = pg.evaluate("""() => [...document.querySelectorAll('#graphCard .gBlocks')].map((r) => [r.dataset.family, [...r.querySelectorAll('.gBlk')].map((b) => b.dataset.kind),
          Math.round(r.getBoundingClientRect().top)])""")
        check("the cubic blocks sit in their own row UNDER the trig row (data-family 'cubic')",
              [r[0] for r in rws] == ["trig", "cubic"] and rws[1][1] == CUBICS and rws[1][2] > rws[0][2] + 40, rws)
        cb = pg.evaluate("""() => ['cubic', '-cubic'].map((k) => { const s = document.querySelector('#gblk-' + k.replace('-', 'n') + ' svg'), l = [...s.querySelectorAll('line')];
          return [l.length, +l[1].getAttribute('x1'), +l[0].getAttribute('y1')]; })""")
        check("each cubic block: plain axes crossing in the MIDDLE of its picture (x 35, y 25 of 70 x 50)", all(c[0] == 2 and abs(c[1] - 35) < 0.01 and abs(c[2] - 25) < 0.01 for c in cb), cb)
        SHC = ROOT / "_build" / "graph" / "cubic"; SHC.mkdir(parents=True, exist_ok=True)
        gr_ = rect(pg, "#graphCard"); pg.screenshot(path=str(SHC / "1-card.png"), clip={"x": gr_["l"] - 10, "y": gr_["t"] - 10, "width": gr_["w"] + 20, "height": gr_["h"] + 20})
        shot(pg, "1-grid.png")
        pg.click("#trow-axes"); pg.wait_for_timeout(60)
        check("opening the Axes card closes the Graph card (one card at a time); the Graph row is not pressed",
              not gcard_shown(pg) and pg.locator("#axesCard").is_visible() and pg.get_attribute("#trow-graph", "aria-pressed") == "false")
        pg.click("#trow-graph"); pg.wait_for_timeout(60)
        check("... and the other way round", gcard_shown(pg) and pg.locator("#axesCard").is_hidden())
        pg.click("#graphClose"); pg.wait_for_timeout(40)
        check("its X closes the card; the panel stays; the row lets go", not gcard_shown(pg) and panel_shown(pg) and pg.get_attribute("#trow-graph", "aria-pressed") == "false")
        open_gcard(pg); close_panel(pg)
        check("Escape closes the card and the panel", not gcard_shown(pg) and not panel_shown(pg))
        check("nothing landed", recs(pg) == [])

        # ------------------------------------------------------------ B: each of the six lands
        group[0] = "B. landing"
        px_want = round(W / 12, 2)
        for k in KINDS:
            pg.evaluate("window.__T.clear('s0')"); pg.wait_for_timeout(30)
            vis = pg.evaluate("window.__T.vis(0)"); mid = [(vis[0] + vis[2]) / 2, (vis[1] + vis[3]) / 2]
            land(pg, k)
            gs = graphs(pg)
            ok1 = len(recs(pg)) == 1 and len(gs) == 1 and gs[0]["page_id"] == "s0" and not panel_shown(pg) and not gcard_shown(pg)
            check(f"{k}: a tap on its block lands ONE 'graph' record on page 1 and closes the panel and the card", ok1, [r["kind"] for r in recs(pg)])
            if not ok1: continue
            r = gs[0]; d = r["data"]; c = d["curves"][0]
            check(f"{k}: style black, 1.5, solid (the axes'); ONE curve: kind {k}, Blue, the pen's width, offsets 0, stretches 1",
                  r["style"] == {"colour": "#000000", "width": 1.5, "dash": "solid", "opacity": 1} and len(d["curves"]) == 1
                  and c == {"kind": k, "colour": BLUE, "width": pen_w, "dx": 0, "dy": 0, "sx": 1, "sy": 1}, [r["style"], d["curves"]])
            tan = k.endswith("tan")
            check(f"{k}: a third of the page wide (0 to 360 over {round(W / 3)} px: px {px_want} per 90), window 0 to 360, axes on, the y-axis at the left",
                  abs(d["px"] - px_want) < 0.006 and d["axes"]["xl"] == 0 and d["axes"]["xr"] == 360 and d["axes"]["on"] is True
                  and d["axes"]["yh"] == (2.6 if tan else 1.35), d)
            g = geo(pg, r["id"])
            check(f"{k}: centred in the part of the page she sees (the 0 to 360 span's middle, the x-axis at its middle height)",
                  abs(d["x0"] + 2 * d["px"] - mid[0]) < 0.02 and abs(d["y0"] - mid[1]) < 0.02, [d["x0"], d["y0"], mid])
            nums = [l for l in g["labels"] if l["cls"] == "num"]
            check(f"{k}: marks at 90°, 180°, 270°, 360° only (none at 0, nothing on the y-axis), centred under their ticks, close under the axis",
                  [l["t"] for l in nums] == ["90°", "180°", "270°", "360°"] and all(abs(l["x"] - (d["x0"] + (j + 1) * d["px"])) < 1e-6 for j, l in enumerate(nums))
                  and all(abs(l["y"] - (d["y0"] + (13 / 55) * d["px"] + 0.62 * 18 / 55 * d["px"])) < 1e-6 for l in nums) and len(g["ticks"]) == 4, [(l["t"], l["x"], l["y"]) for l in nums])
            check(f"{k}: number size 18/55 px, letters x and y 21/55 px (the mock's 18 and 21 at px 55)",
                  all(abs(l["size"] - 18 / 55 * d["px"]) < 1e-6 for l in nums) and [l["t"] for l in g["labels"] if l["cls"] == "letter"] == ["x", "y"]
                  and all(abs(l["size"] - 21 / 55 * d["px"]) < 1e-6 for l in g["labels"] if l["cls"] == "letter"), [l["size"] for l in g["labels"]])
            e = el(pg, r["id"]); parts = e["parts"]; cls = [p["cls"] for p in parts]
            check(f"{k}: drawn as a <g data-type=graph> in the pen group, no <text> (glyph outlines)", e["tag"] == "g" and e["type"] == "graph" and e["group"] == "pen" and e["texts"] == 0, e and e["group"])
            ax = [p for p in parts if p["cls"] in ("axis", "head")]; lab = [p for p in parts if p["cls"] in ("num", "letter")]; cv = [p for p in parts if p["cls"] == "curve"]
            check(f"{k}: the axes, ticks and heads stroked BLACK; the marks and letters filled BLACK with no stroke (no halo)",
                  len(ax) == 2 and all(p["stroke"] == "#000000" and p["fill"] == "none" for p in ax) and len(lab) == 6
                  and all(p["fill"] == "#000000" and p["stroke"] == "none" and p["dl"] > 50 for p in lab), ax + lab)
            check(f"{k}: the curve is stroked in the pen's colour (Blue) at the pen's width, and drawn LAST, after every mark (the marks sit behind it)",
                  len(cv) == 1 and cv[0]["stroke"] == BLUE and cv[0]["width"] == str(pen_w) and cls[-1] == "curve"
                  and max(i for i, p in enumerate(parts) if p["cls"] == "num") < cls.index("curve"), cls)
            asy = [p for p in parts if p["cls"] == "asym"]
            if tan:
                check(f"{k}: two dashed asymptotes, at 90° and 270°, black, between the marks and the curve",
                      g["asym"] == [d["x0"] + d["px"], d["x0"] + 3 * d["px"]] and len(asy) == 1 and asy[0]["dash"] and asy[0]["stroke"] == "#000000"
                      and cls.index("asym") < cls.index("curve"), [g["asym"], asy])
            else:
                check(f"{k}: no asymptotes", g["asym"] == [] and asy == [], g["asym"])
            f0 = {"sin": 0, "-sin": 0, "cos": 1, "-cos": -1, "tan": 0, "-tan": 0}[k]
            first = g["runs"][0][0][0]
            check(f"{k}: the curve is the real function: it starts at (0°, {f0}), on the y-axis",
                  dist(first, [d["x0"], d["y0"] - f0 * d["py"]]) < 0.02, [first, d["x0"], d["y0"]])
            last = g["runs"][0][-1][1]
            check(f"{k}: and ends at 360° (the window's right edge)", abs(last[0] - (d["x0"] + 4 * d["px"])) < 0.02, last)
            if tan:
                check(f"{k}: tan is cut exactly at the window's top and bottom (3 pieces, the middle one from edge to edge)",
                      len(g["runs"][0]) == 3 and abs(abs(g["runs"][0][1][0][1] - d["y0"]) - 2.6 * d["py"]) < 0.02 and abs(abs(g["runs"][0][1][1][1] - d["y0"]) - 2.6 * d["py"]) < 0.02, g["runs"][0])
            if k == "cos":
                show(pg, [d["x0"] + 2 * d["px"], d["y0"]])
                g2 = geo(pg, r["id"]); bx = g2["box"]; tl = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[0] - 120, bx[1] - 160]); br = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[2] + 240, bx[3] + 140])
                shot(pg, "2-cos-landed.png", {"x": max(0, tl[0]), "y": max(0, tl[1]), "width": min(1280, br[0]) - max(0, tl[0]), "height": min(800, br[1]) - max(0, tl[1])})
            if k == "tan":
                show(pg, [d["x0"] + 2 * d["px"], d["y0"]])
                g2 = geo(pg, r["id"]); bx = g2["box"]; tl = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[0] - 120, bx[1] - 60]); br = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[2] + 240, bx[3] + 60])
                shot(pg, "3-tan-landed.png", {"x": max(0, tl[0]), "y": max(0, tl[1]), "width": min(1280, br[0]) - max(0, tl[0]), "height": min(800, br[1]) - max(0, tl[1])})
            undo(pg)
            check(f"{k}: ONE undo removes it", graphs(pg) == [] and el(pg, r["id"]) is None, len(recs(pg)))
        pg.click(f'#tray .sw[data-colour="#000000"]'); pg.wait_for_timeout(40)
        pg.click(f'#tray .sw[data-colour="{BLUE}"]'); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ C: the Axes pill, box-select, move, resize
        group[0] = "C. select + Axes pill"
        pg.evaluate("window.__T.clear('s0')"); land(pg, "cos")
        gid = graphs(pg)[0]["id"]; d0 = graphs(pg)[0]["data"]
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        g0 = geo(pg, gid)
        box_select(pg, g0["box"])
        s = sel(pg)
        check("a box around the graph picks the WHOLE graph as one thing", s and s["ids"] == [gid], s)
        chip = pg.evaluate("(() => { const c = document.querySelector('.selChips .chip.gchip'); if (!c) return null; const b = c.getBoundingClientRect(); return [c.textContent.trim(), c.dataset.act, c.getAttribute('aria-pressed'), Math.round(b.height), b.width > b.height, getComputedStyle(c).borderRadius]; })()")
        check("an 'Axes' pill shows above it (word and icon, 38 px high, wider than tall), pressed while the axes show", chip and chip[0] == "Axes" and chip[1] == "axes" and chip[2] == "true" and chip[3] == 38 and chip[4], chip)
        check("no Dotted copy chip", pg.locator(".selChips [data-act='dotted'], .selChips .chip:has-text('Dotted')").count() == 0)
        hl = pg.evaluate("(() => { const c = document.querySelector('#stack svg.ink circle.selgl'); return c ? [+c.getAttribute('cx'), +c.getAttribute('cy')] : null; })()")
        check("the left handle shows at the x-axis's left end (the origin while the window starts at 0°)", hl and dist(hl, [d0["x0"], d0["y0"]]) < 0.15, [hl, d0["x0"], d0["y0"]])
        show(pg, [d0["x0"] + 2 * d0["px"], d0["y0"]])
        bx = sel(pg)["box"]; tl = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[0] - 120, bx[1] - 140]); br = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[2] + 240, bx[3] + 120])
        clip = {"x": max(0, tl[0]), "y": max(0, tl[1]), "width": min(1280, br[0]) - max(0, tl[0]), "height": min(800, br[1]) - max(0, tl[1])}
        shot(pg, "4-selected-axes-chip.png", clip)
        pg.click(".selChips .chip.gchip"); pg.wait_for_timeout(60)
        r1 = graphs(pg)[0]; e1 = el(pg, gid)
        check("one tap hides the axes, the marks and the letters together (data.axes.on false); the curve stays",
              r1["data"]["axes"]["on"] is False and [p["cls"] for p in e1["parts"]] == ["curve"], [p["cls"] for p in e1["parts"]])
        check("... the graph stays selected, the pill now not pressed", sel(pg) and sel(pg)["ids"] == [gid] and pg.get_attribute(".selChips .chip.gchip", "aria-pressed") == "false")
        shot(pg, "6-axes-off.png", clip)
        pg.click(".selChips .chip.gchip"); pg.wait_for_timeout(60)
        e2 = el(pg, gid)
        check("another tap brings them back", graphs(pg)[0]["data"]["axes"]["on"] is True and [p["cls"] for p in e2["parts"]].count("num") == 4, [p["cls"] for p in e2["parts"]])
        undo(pg)
        check("undo: off again (each tap is one undo step)", graphs(pg)[0]["data"]["axes"]["on"] is False)
        undo(pg)
        check("undo again: on, as it landed", graphs(pg)[0]["data"] == d0, graphs(pg)[0]["data"])
        clear_sel(pg)
        pen(pg, [[d0["x0"] + 0.5 * d0["px"], d0["y0"] - 1.6 * d0["py"]], [d0["x0"] + 1.5 * d0["px"], d0["y0"] - 1.45 * d0["py"]]]); pg.wait_for_timeout(40)
        check("a box in empty space above the curve does not take it", sel(pg) is None, sel(pg))
        box_select(pg, g0["box"])
        st = [d0["x0"] + 2 * d0["px"], d0["y0"] + 0.5 * d0["py"]]
        pen(pg, [st, addv(st, [20, 15]), addv(st, [40, 30])]); pg.wait_for_timeout(60)
        a1 = graphs(pg); dd1 = a1[0]["data"]
        check("a move inside the box carries the whole graph (x0, y0 + (40, 30)); px, py, window and curve unchanged; still ONE record",
              len(a1) == 1 and abs(dd1["x0"] - d0["x0"] - 40) < 0.011 and abs(dd1["y0"] - d0["y0"] - 30) < 0.011 and dd1["px"] == d0["px"] and dd1["py"] == d0["py"]
              and dd1["axes"] == d0["axes"] and dd1["curves"] == d0["curves"], [d0, dd1])
        zz = z(pg)
        sb = sel(pg)["box"]; pad = 4 / zz
        o, c = [sb[0] - pad, sb[1] - pad], [sb[2] + pad, sb[3] + pad]
        u = subv(c, o); L = math.hypot(*u); u = [u[0] / L, u[1] / L]
        st = addv(c, [u[0] * 5 / zz, u[1] * 5 / zz]); sc = 1.25
        pen(pg, [st, addv(st, [(c[0] - o[0]) * (sc - 1) / 2, (c[1] - o[1]) * (sc - 1) / 2]), addv(st, [(c[0] - o[0]) * (sc - 1), (c[1] - o[1]) * (sc - 1)])]); pg.wait_for_timeout(60)
        dd2 = graphs(pg)[0]["data"]; g2 = geo(pg, gid)
        exp0 = [o[0] + (dd1["x0"] - o[0]) * sc, o[1] + (dd1["y0"] - o[1]) * sc]
        check("a corner resize multiplies px and py by 1.25 and carries the origin about the opposite corner (all of it together)",
              abs(dd2["px"] / dd1["px"] - sc) < 0.002 and abs(dd2["py"] / dd1["py"] - sc) < 0.002 and dist([dd2["x0"], dd2["y0"]], exp0) < 0.03, [dd1, dd2, exp0])
        check("... the marks and letters grow with it (18/55 and 21/55 of the new px)",
              all(abs(l["size"] - (18 if l["cls"] == "num" else 21) / 55 * dd2["px"]) < 1e-6 for l in g2["labels"]), [l["size"] for l in g2["labels"]])
        check("... and the curve's width stays the pen's (ink never thickens on a resize)", dd2["curves"][0]["width"] == pen_w and graphs(pg)[0]["style"]["width"] == 1.5)
        undo(pg)
        check("undo puts the size back", graphs(pg)[0]["data"] == dd1)
        rot = pg.evaluate("(() => { const k = document.querySelector('#stack svg.ink circle.selrot'); return k ? [+k.getAttribute('cx'), +k.getAttribute('cy')] : null; })()")
        sb = sel(pg)["box"]; cc = [(sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2]
        before = graphs(pg)[0]
        def rotp(p, c, deg):
            a = math.radians(deg); dx, dy = p[0] - c[0], p[1] - c[1]
            return [c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a)]
        pen(pg, [rotp(rot, cc, k * 6) for k in range(11)]); pg.wait_for_timeout(60)
        check("a turn on the ring leaves the graph exactly as it was (a graph never turns)", rot is not None and graphs(pg)[0] == before)
        pg.click("#tray .sw[data-colour='#FF0C84']"); pg.wait_for_timeout(60)
        rc = graphs(pg)[0]
        check("a colour tapped on the tray with the graph selected recolours the CURVE only; the axes stay black",
              rc["data"]["curves"][0]["colour"].lower() == "#ff0c84" and rc["style"]["colour"] == "#000000", [rc["style"], rc["data"]["curves"]])
        undo(pg)
        check("... one undo step", graphs(pg)[0]["data"]["curves"][0]["colour"] == BLUE)

        # ------------------------------------------------------------ D: the left handle opens the x-axis to -360
        group[0] = "D. opening left"
        pg.evaluate("window.__T.clear('s0')"); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        land(pg, "cos"); gid = graphs(pg)[0]["id"]; d0 = graphs(pg)[0]["data"]; P_ = d0["px"]
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        show(pg, [d0["x0"], d0["y0"]])
        box_select(pg, geo(pg, gid)["box"])
        hl = [d0["x0"], d0["y0"]]
        pen(pg, [addv(hl, [1, 1]), addv(hl, [-0.6 * P_, 1]), addv(hl, [-1.37 * P_ + 1, 1])]); pg.wait_for_timeout(60)
        r1 = graphs(pg)[0]; d1 = r1["data"]
        want = -1.37 * 90
        check("dragging the handle left opens the window smoothly (no snapping): xl about -123.3 for a 1.37 px drag",
              abs(d1["axes"]["xl"] - want) < 0.2 and abs(d1["axes"]["xl"] / 90 - round(d1["axes"]["xl"] / 90)) > 0.1, d1["axes"])
        check("... the y-axis stays on the page where it was (x0, y0), the scale per degree stays (px, py), the right end stays 360",
              d1["x0"] == d0["x0"] and d1["y0"] == d0["y0"] and d1["px"] == d0["px"] and d1["py"] == d0["py"] and d1["axes"]["xr"] == 360, [d0, d1])
        g1 = geo(pg, gid)
        check("... a mark at −90° appears (a real minus), none further left yet", [l["t"] for l in g1["labels"] if l["cls"] == "num"][:2] == ["−90°", "90°"], [l["t"] for l in g1["labels"]])
        check("... the curve now runs from the new left end (cos(-123.3) at the window's left edge)",
              dist(g1["runs"][0][0][0], [d0["x0"] + d1["axes"]["xl"] / 90 * P_, d0["y0"] - math.cos(math.radians(d1["axes"]["xl"])) * d0["py"]]) < 0.05, g1["runs"][0][0])
        check("... it stays selected; the handle sits at the new left end", sel(pg) and sel(pg)["ids"] == [gid]
              and abs(pg.evaluate("+document.querySelector('#stack svg.ink circle.selgl').getAttribute('cx')") - g1["left"][0]) < 0.15)
        undo(pg)
        check("ONE undo step puts the window back to 0", graphs(pg)[0]["data"]["axes"]["xl"] == 0)
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        check("... redo opens it again", abs(graphs(pg)[0]["data"]["axes"]["xl"] - d1["axes"]["xl"]) < 1e-9)
        hl = geo(pg, gid)["left"]
        # her fix 15 Nov 10:32: in ONE drag, open past the page's left edge (the graph slides right), then push back to where
        # the drag started (the y-axis comes back to its starting place)
        pen(pg, [hl, addv(hl, [-2 * P_, 0]), addv(hl, [-6 * P_, 0])], up=False); pg.wait_for_timeout(40)
        mid = pg.evaluate("+document.querySelector('#stack svg.ink circle.selgl').getAttribute('cx')")
        check("mid-drag, opened past the page's left edge: the handle (the x-axis's left end) stays on the page, PAGE_M inside or more",
              mid >= 8 - 0.01 and mid > d0["x0"] - 4 * P_ + 1, mid)
        pen_on(pg, [addv(hl, [-1 * P_, 0]), hl]); pg.wait_for_timeout(60)
        db = graphs(pg)[0]["data"]
        check("... pushed back in the same drag to where it started: the y-axis back at its starting place, the window as it was",
              db["x0"] == d0["x0"] and abs(db["axes"]["xl"] - d1["axes"]["xl"]) < 0.02, [db["x0"], d0["x0"], db["axes"]])
        hl = geo(pg, gid)["left"]
        pen(pg, [hl, addv(hl, [-2 * P_, 0]), addv(hl, [-6 * P_, 0])]); pg.wait_for_timeout(60)
        d2 = graphs(pg)[0]["data"]; g2 = geo(pg, gid)
        check("pushed far past it, it STOPS at -360", d2["axes"]["xl"] == -360, d2["axes"])
        need = pg.evaluate("(r) => { const g = window.__pw.ink.graphGeom(r); return 8 - g.box[0]; }",
                           {"kind": "graph", "data": {**d2, "x0": d0["x0"]}})
        n360 = [l for l in g2["labels"] if l["t"] == "−360°"][0]["b"]
        check("... where it landed that ran off the left edge, so the whole graph slid RIGHT by just the amount needed (the y-axis moved, y0 not)",
              need > 0 and abs(d2["x0"] - (d0["x0"] + need)) < 0.011 and d2["y0"] == d0["y0"] and d2["px"] == d0["px"], [need, d0["x0"], d2["x0"]])
        check("... nothing left of the 8 px margin: the leftmost drawn thing sits right on it; the −360° number wholly inside the page",
              8 - 0.001 <= g2["box"][0] <= 8 + 0.02 and n360[0] >= 8 - 0.001 and n360[2] <= W, [g2["box"], n360])
        check("... and the right end (the head, the letter x) still inside the page, 8 px in", g2["box"][2] <= W - 8, g2["box"])
        undo(pg)
        d2u = graphs(pg)[0]["data"]
        check("ONE undo puts back both the window and the position", d2u == d1, [d2u, d1])
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        check("... redo: opened and slid again", graphs(pg)[0]["data"] == d2)
        check("marks every 90 inside the window: −360° −270° −180° −90° 90° 180° 270° 360°",
              [l["t"] for l in g2["labels"] if l["cls"] == "num"] == ["−360°", "−270°", "−180°", "−90°", "90°", "180°", "270°", "360°"], [l["t"] for l in g2["labels"]])
        check("the negative marks: same size and drop as the others, centred under their ticks, still before the curve",
              all(abs(l["size"] - 18 / 55 * P_) < 1e-6 and abs(l["y"] - g2["labels"][4]["y"]) < 1e-9 for l in g2["labels"] if l["cls"] == "num")
              and [p["cls"] for p in el(pg, gid)["parts"]][-1] == "curve", [l["y"] for l in g2["labels"]])
        check("the x-axis now starts at -360 (4 px per 90 left of the y-axis)", abs(g2["lines"][0][0][0] - (d2["x0"] - 4 * P_)) < 0.02, g2["lines"][0])
        sb = sel(pg)["box"]; tl = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [sb[0] - 60, sb[1] - 120]); br = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [sb[2] + 60, sb[3] + 80])
        shot(pg, "5-opened-to-minus-360.png", {"x": max(0, tl[0]), "y": max(0, tl[1]), "width": min(1280, br[0]) - max(0, tl[0]), "height": min(800, br[1]) - max(0, tl[1])})
        hl = addv(g2["left"], [3 / z(pg), 0])                          # grab the end 3 px (screen) inside
        pen(pg, [hl, addv(hl, [3 * P_, 0]), addv(hl, [6 * P_, 0])]); pg.wait_for_timeout(60)
        d3 = graphs(pg)[0]["data"]
        check("pushed back right past the y-axis (a new drag) it stops at 0°, the window as it landed; the graph stays where the last drag left it",
              d3["axes"]["xl"] == 0 and d3["axes"] == d0["axes"] and d3["x0"] == d2["x0"] and d3["y0"] == d0["y0"], [d3["axes"], d3["x0"]])
        pen(pg, [geo(pg, gid)["left"], addv(geo(pg, gid)["left"], [-4 * P_, 0])]); pg.wait_for_timeout(60)
        check("open to -360 again (for the checks below): it already fits, so it does not move", graphs(pg)[0]["data"]["axes"]["xl"] == -360 and graphs(pg)[0]["data"]["x0"] == d2["x0"])
        keep_d = graphs(pg)[0]["data"]

        # a graph first moved far enough right: opening it to -360 never moves the y-axis
        pg.evaluate("window.__T.clear('s0')"); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        land(pg, "sin"); gid2 = graphs(pg)[0]["id"]; e0 = graphs(pg)[0]["data"]
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        box_select(pg, geo(pg, gid2)["box"])
        st = [e0["x0"] + 2 * e0["px"], e0["y0"] + 0.5 * e0["py"]]
        pen(pg, [st, addv(st, [40, 0]), addv(st, [80, 0])]); pg.wait_for_timeout(60)
        e1 = graphs(pg)[0]["data"]
        hl = geo(pg, gid2)["left"]
        pen(pg, [hl, addv(hl, [-2 * P_, 0]), addv(hl, [-6 * P_, 0])]); pg.wait_for_timeout(60)
        e2 = graphs(pg)[0]["data"]; ge2 = geo(pg, gid2)
        check("a graph first moved 80 px right: opened to -360 the y-axis does not move at all (x0, y0 as before the drag), all of it on the page",
              abs(e1["x0"] - e0["x0"] - 80) < 0.011 and e2["axes"]["xl"] == -360 and e2["x0"] == e1["x0"] and e2["y0"] == e1["y0"]
              and ge2["box"][0] >= 8 and ge2["box"][2] <= W - 8, [e0["x0"], e1["x0"], e2["x0"], ge2["box"]])

        # a graph resized too wide to fit: the handle stops short of -360, nothing off the page on either side
        pg.evaluate("window.__T.clear('s0')"); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        land(pg, "cos"); gid3 = graphs(pg)[0]["id"]; f0 = graphs(pg)[0]["data"]
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        box_select(pg, geo(pg, gid3)["box"])
        zz = z(pg); sb = sel(pg)["box"]; pad = 4 / zz
        o, c = [sb[0] - pad, sb[1] - pad], [sb[2] + pad, sb[3] + pad]
        u = subv(c, o); L = math.hypot(*u); u = [u[0] / L, u[1] / L]
        st = addv(c, [u[0] * 5 / zz, u[1] * 5 / zz]); sc = 1.5
        pen(pg, [st, addv(st, [(c[0] - o[0]) * (sc - 1) / 2, (c[1] - o[1]) * (sc - 1) / 2]), addv(st, [(c[0] - o[0]) * (sc - 1), (c[1] - o[1]) * (sc - 1)])]); pg.wait_for_timeout(60)
        f1 = graphs(pg)[0]["data"]; gf1 = geo(pg, gid3)
        hl = gf1["left"]
        pen(pg, [hl, addv(hl, [-3 * f1["px"], 0]), addv(hl, [-8 * f1["px"], 0])]); pg.wait_for_timeout(60)
        f2 = graphs(pg)[0]["data"]; gf2 = geo(pg, gid3)
        check("a graph resized 1.5 times (too wide for -360 to fit): the handle stops short of -360",
              f1["px"] > f0["px"] * 1.4 and 8.6 * f1["px"] > W - 16 and -360 < f2["axes"]["xl"] < -90, [f0["px"], f1["px"], f2["axes"]])
        check("... and nothing is off the page on either side (left on the 8 px margin, right end inside 8 px or where it already was)",
              gf2["box"][0] >= 8 - 0.001 and gf2["box"][2] <= max(W - 8, gf1["box"][2]) + 0.02 and gf2["box"][2] <= W, [gf1["box"], gf2["box"]])
        check("... it opened as far as it could: the right end reaches the right margin (within 1 px)",
              abs(gf2["box"][2] - max(W - 8, gf1["box"][2])) < 1, gf2["box"])

        # back to the cos graph opened to -360 (for E and F)
        pg.evaluate("window.__T.clear('s0')"); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        land(pg, "cos"); gid = graphs(pg)[0]["id"]
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        box_select(pg, geo(pg, gid)["box"])
        hl = geo(pg, gid)["left"]
        pen(pg, [hl, addv(hl, [-2 * P_, 0]), addv(hl, [-6 * P_, 0])]); pg.wait_for_timeout(60)
        check("a fresh cos landed and opened to -360 again (for E and F): the same place as before",
              graphs(pg)[0]["data"]["axes"] == keep_d["axes"] and graphs(pg)[0]["data"]["x0"] == keep_d["x0"], [graphs(pg)[0]["data"], keep_d])
        clear_sel(pg); pg.click("#tool-pen"); pg.wait_for_timeout(30)

        # ------------------------------------------------------------ E: thumb, PDF, shared picture
        group[0] = "E. thumb + PDF + share"
        gr_ = graphs(pg)[0]; dd = gr_["data"]
        th = pg.evaluate("(i) => window.__T.el(i, window.__pw.ink.thumbSvg('s0'))", gid)
        check("it is in the page's thumb (thumbSvg): the same parts, 8 marks, 2 letters, the curve last in Blue",
              th and th["type"] == "graph" and [p["cls"] for p in th["parts"]].count("num") == 8 and th["parts"][-1]["cls"] == "curve" and th["parts"][-1]["stroke"] == BLUE, th and [p["cls"] for p in th["parts"]])
        pg.click("#listBtn"); pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(300)
        tg = pg.evaluate("(i) => !!document.querySelector(`#plThumbs .thumbP[data-index='1'] [data-id='${i}']`)", gid)
        check("the page list's thumb of page 1 holds the graph", tg)
        tb = rect(pg, "#plThumbs .thumbP[data-index='1']")
        if tb: shot(pg, "8-thumbnail.png", {"x": tb["l"] - 6, "y": tb["t"] - 6, "width": tb["w"] + 12, "height": tb["h"] + 12})
        doc = pdf_of(pg, "Graph"); p0 = doc[0]; k = p0.rect.width / W
        drs = p0.get_drawings()
        fills = [dr for dr in drs if dr.get("fill") is not None and tuple(round(v, 2) for v in dr["fill"]) == (0, 0, 0)]
        blues = [dr for dr in drs if dr.get("color") is not None and dr["color"][2] > 0.9 and dr["color"][0] < 0.1]
        blacks = [dr for dr in drs if dr.get("color") is not None and max(dr["color"]) < 0.01]
        check("the PDF: the 8 marks and 2 letters as FILLED black glyph outlines (no text, no embedded font)",
              len(fills) == 10 and p0.get_text().strip() == "" and p0.get_fonts() == [], [len(fills), p0.get_text()[:40], p0.get_fonts()])
        check("... the axes stroked black, the curve stroked Blue at the pen's width", blacks and blues and any(abs(dr["width"] - pen_w * k) < 0.05 for dr in blues), [len(blacks), len(blues), [dr["width"] for dr in blues]])
        pix = p0.get_pixmap(dpi=144); img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"); sk = pix.width / W
        on180 = [dd["x0"] + 2 * dd["px"], dd["y0"] + dd["py"]]
        on_m180 = [dd["x0"] - 2 * dd["px"], dd["y0"] + dd["py"]]
        n90 = [l for l in geo(pg, gid)["labels"] if l["t"] == "90°"][0]["b"]
        check("... the PDF page shows Blue on the curve at 180° and at −180° (cos = -1)", any_px(img, on180[0] * sk, on180[1] * sk, 2, bluish) and any_px(img, on_m180[0] * sk, on_m180[1] * sk, 2, bluish))
        check("... and dark ink inside the 90° mark's glyph box", any(darkish(img.getpixel((x, y))) for x in range(int(n90[0] * sk), int(n90[2] * sk) + 1) for y in range(int(n90[1] * sk), int(n90[3] * sk) + 1)))
        page_img = img if img.width <= 1400 else img.resize((1400, round(img.height * 1400 / img.width)))   # the whole PDF page
        SHOTS.mkdir(parents=True, exist_ok=True); page_img.save(str(SHOTS / "7-pdf-page.png"))
        doc.close()
        pg.click("#plSelect"); pg.wait_for_timeout(40)
        pg.locator("#plThumbs .thumbP[data-index='1']").click(); pg.wait_for_timeout(40)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg")
        pg.evaluate("window.__shared = null")
        pg.click("#shareDlg button[data-share='images']"); pg.wait_for_selector("#shareReady", timeout=30000)
        pg.click("#shareDlg button[data-share='send']"); pg.wait_for_function("window.__shared", timeout=10000)
        png = pg.evaluate("""async () => { const f = window.__shared.files[0]; const u = new Uint8Array(await f.arrayBuffer()); let s = '';
          for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return [f.type, btoa(s)]; }""")
        si = Image.open(io.BytesIO(base64.b64decode(png[1]))).convert("RGB"); ss = si.width / W
        check("a shared picture (Share as images) is a PNG with the curve in Blue at 180° and −180°",
              png[0] == "image/png" and any_px(si, on180[0] * ss, on180[1] * ss, 2, bluish) and any_px(si, on_m180[0] * ss, on_m180[1] * ss, 2, bluish), png[0])
        check("... and the 90° mark drawn (dark ink inside its glyph box)", any(darkish(si.getpixel((x, y))) for x in range(int(n90[0] * ss), int(n90[2] * ss) + 1) for y in range(int(n90[1] * ss), int(n90[3] * ss) + 1)))
        if pg.evaluate("window.__pw.tick()") is not None: pg.click("#plDone"); pg.wait_for_timeout(40)
        if not pg.locator("#pageList").is_hidden(): pg.click("#plClose"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ F: reload keeps it
        group[0] = "F. reload"
        keep = graphs(pg)[0]
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(200)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        pg.reload(); ready(pg); open_note(pg); pg.evaluate(HELP)
        back = graphs(pg)
        check("after closing the note and a reload the graph is back exactly (data, style, id)", len(back) == 1 and back[0]["data"] == keep["data"] and back[0]["style"] == keep["style"] and back[0]["id"] == keep["id"], back)
        e = el(pg, keep["id"])
        check("... and drawn: 8 marks, the curve last", e and [p["cls"] for p in e["parts"]].count("num") == 8 and e["parts"][-1]["cls"] == "curve", e and [p["cls"] for p in e["parts"]])

        # ------------------------------------------------------------ H: unit 2b (pw-v9k): a second curve on the same axes, a curve on her axes stamp
        group[0] = "H. 2b: add to a graph"
        SH2 = ROOT / "_build" / "graph" / "unit2b"
        PINK = "#FF0C84"
        sws = pg.evaluate("[...document.querySelectorAll('#tray .sw')].map((b) => b.dataset.colour)")
        THIRD = [c for c in sws if c.lower() not in (BLUE.lower(), PINK.lower(), "#000000")][0]
        def pen_colour(c):
            pg.click("#tool-pen"); pg.wait_for_timeout(30); pg.click(f'#tray .sw[data-colour="{c}"]'); pg.wait_for_timeout(40)
        def pick(bx):
            pg.click("#tool-select"); pg.wait_for_timeout(40); box_select(pg, bx)
        def tap(kind):
            open_gcard(pg); pg.click(bid(kind)); pg.wait_for_timeout(80)
        def sgeo(i): return pg.evaluate("(i) => window.__T.sgeo(i)", i)
        def gys(i): return pg.evaluate("""(i) => { const r = window.__T.recs('s0').find((x) => x.id === i); const g = window.__pw.ink.graphGeom(r);
            return g.curves.map((c) => c.runs.flat().map((q) => q[1])); }""", i)
        def axrecs(): return [r for r in recs(pg) if r["kind"] == "axes"]
        def shot2(name, bx, top=150, bottom=110):
            show(pg, [(bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2])
            tl = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[0], bx[1]]); br = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[2], bx[3]])
            y0 = max(0, tl[1] - top); y1 = min(800, br[1] + bottom); w = 900; x0 = max(0, min(1280 - w, (tl[0] + br[0]) / 2 - w / 2))
            SH2.mkdir(parents=True, exist_ok=True); pg.screenshot(path=str(SH2 / name), clip={"x": x0, "y": y0, "width": w, "height": y1 - y0})
        def nonum_before_curve(parts):
            cls = [p["cls"] for p in parts]
            return "curve" in cls and all(i < cls.index("curve") for i, c in enumerate(cls) if c in ("num", "letter", "axis", "head"))

        # tan added to a sin graph: clipped by the sin window; sin added to a tan graph sits in tan's taller window
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        land(pg, "sin"); gid = graphs(pg)[0]["id"]; d0 = graphs(pg)[0]["data"]
        pen_colour(PINK); pick(geo(pg, gid)["box"])
        check("a box picks the sin graph", sel(pg) and sel(pg)["ids"] == [gid], sel(pg))
        open_gcard(pg)
        check("opening Tools, Graph… keeps the selection alive (the card shows, the graph still selected)", gcard_shown(pg) and sel(pg) and sel(pg)["ids"] == [gid], sel(pg))
        pg.click(bid("tan")); pg.wait_for_timeout(80)
        r = graphs(pg); dd = r[0]["data"]
        check("tan tapped with the sin graph selected: still ONE record (same id); tan ADDED as the second curve, in the pen's colour at the tap (pink)",
              len(recs(pg)) == 1 and r[0]["id"] == gid and [c["kind"] for c in dd["curves"]] == ["sin", "tan"] and dd["curves"][1]["colour"].lower() == PINK.lower()
              and dd["curves"][1] == {"kind": "tan", "colour": dd["curves"][1]["colour"], "width": pen_w, "dx": 0, "dy": 0, "sx": 1, "sy": 1}, dd["curves"])
        check("... the window, size and place unchanged (x0, y0, px, py, axes as landed: sin's 1.35)", {k: v for k, v in dd.items() if k != "curves"} == {k: v for k, v in d0.items() if k != "curves"}, dd)
        g = geo(pg, gid); ys = gys(gid)
        check("... tan brings its dashed asymptotes at 90° and 270°; tan is simply clipped by the sin window (every point within ±1.35)",
              g["asym"] == [d0["x0"] + d0["px"], d0["x0"] + 3 * d0["px"]] and all(abs(y - d0["y0"]) <= 1.35 * d0["py"] + 0.02 for y in ys[1]) and len(g["runs"][1]) == 3, [g["asym"], len(g["runs"][1])])
        check("... the panel and the card closed; the graph stays selected", not panel_shown(pg) and not gcard_shown(pg) and sel(pg) and sel(pg)["ids"] == [gid])
        shot2("a3-sin-tan.png", sel(pg)["box"])
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        land(pg, "tan"); gid = graphs(pg)[0]["id"]; d0 = graphs(pg)[0]["data"]
        pick(geo(pg, gid)["box"]); tap("sin")
        dd = graphs(pg)[0]["data"]
        check("sin added to a tan graph sits in tan's taller window (yh stays 2.6, nothing else moves)",
              [c["kind"] for c in dd["curves"]] == ["tan", "sin"] and dd["axes"]["yh"] == 2.6 and {k: v for k, v in dd.items() if k != "curves"} == {k: v for k, v in d0.items() if k != "curves"}, dd)

        # sin with cos over it
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        land(pg, "sin"); gid = graphs(pg)[0]["id"]; d0 = graphs(pg)[0]["data"]
        pen_colour(PINK); pick(geo(pg, gid)["box"]); tap("cos")
        dd = graphs(pg)[0]["data"]; d1 = dd
        check("cos added to sin: curves sin (Blue) then cos (pink), one record", len(recs(pg)) == 1 and [(c["kind"], c["colour"].lower()) for c in dd["curves"]] == [("sin", BLUE.lower()), ("cos", PINK.lower())], dd["curves"])
        parts = el(pg, gid)["parts"]; cv = [p for p in parts if p["cls"] == "curve"]
        check("drawn in the order added, newest on top: two curve paths last, cos (pink) the very last; every mark, letter and axis BEHIND both",
              len(cv) == 2 and parts[-1]["cls"] == "curve" and parts[-1]["stroke"].lower() == PINK.lower() and parts[-2]["stroke"] == BLUE and nonum_before_curve(parts), [(p["cls"], p["stroke"]) for p in parts])
        undo(pg)
        check("ONE undo takes the cos away (the graph as it landed); the graph stays", graphs(pg)[0]["data"] == d0 and len(recs(pg)) == 1, graphs(pg)[0]["data"]["curves"])
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        check("... redo puts it back", graphs(pg)[0]["data"] == d1)
        if not (sel(pg) and sel(pg)["ids"] == [gid]): pick(geo(pg, gid)["box"])
        tap("cos")
        check("cos tapped again (already on those axes): nothing changes", graphs(pg)[0]["data"] == d1 and len(recs(pg)) == 1, graphs(pg)[0]["data"]["curves"])
        tap("sin")
        check("sin tapped (already there, now with a pink pen): nothing changes either (no stacked duplicate)", graphs(pg)[0]["data"] == d1)
        undo(pg)
        check("... and no undo step was made: the next undo takes the cos away", graphs(pg)[0]["data"] == d0)
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        if not (sel(pg) and sel(pg)["ids"] == [gid]): pick(geo(pg, gid)["box"])
        shot2("a1-sin-cos.png", sel(pg)["box"])
        pg.click(f'#tray .sw[data-colour="{THIRD}"]'); pg.wait_for_timeout(60)
        cs = graphs(pg)[0]["data"]["curves"]
        check("a colour tap with the two-curve graph selected recolours only the NEWEST curve (cos); sin stays Blue", cs[0]["colour"] == BLUE and cs[1]["colour"].lower() == THIRD.lower(), cs)
        undo(pg)
        check("... one undo step", graphs(pg)[0]["data"] == d1)
        pg.click(".selChips .chip.gchip"); pg.wait_for_timeout(60)
        e1 = el(pg, gid)
        check("the Axes pill hides the axes, marks and letters; both curves stay", graphs(pg)[0]["data"]["axes"]["on"] is False and [p["cls"] for p in e1["parts"]] == ["curve", "curve"], [p["cls"] for p in e1["parts"]])
        shot2("a4-axes-hidden.png", sel(pg)["box"])
        pg.click(".selChips .chip.gchip"); pg.wait_for_timeout(60)
        check("... and shows them again", graphs(pg)[0]["data"]["axes"]["on"] is True)
        undo(pg); undo(pg)
        sb = sel(pg)["box"]; st = [d1["x0"] + 2 * d1["px"], d1["y0"] + 0.5 * d1["py"]]
        pen(pg, [st, addv(st, [20, 15]), addv(st, [40, 30])]); pg.wait_for_timeout(60)
        dm = graphs(pg)[0]["data"]
        check("a move carries the whole graph, both curves with it (x0, y0 + (40, 30); curves and window unchanged)",
              abs(dm["x0"] - d1["x0"] - 40) < 0.011 and abs(dm["y0"] - d1["y0"] - 30) < 0.011 and dm["curves"] == d1["curves"] and dm["axes"] == d1["axes"], dm)
        gm = geo(pg, gid)
        check("... both curves drawn at the new place (sin from the new origin, cos from 1 above it)",
              dist(gm["runs"][0][0][0], [dm["x0"], dm["y0"]]) < 0.05 and dist(gm["runs"][1][0][0], [dm["x0"], dm["y0"] - dm["py"]]) < 0.05, [gm["runs"][0][0][0], gm["runs"][1][0][0]])
        zz = z(pg); sb = sel(pg)["box"]; pad = 4 / zz
        o, c = [sb[0] - pad, sb[1] - pad], [sb[2] + pad, sb[3] + pad]
        u = subv(c, o); L = math.hypot(*u); u = [u[0] / L, u[1] / L]
        st = addv(c, [u[0] * 5 / zz, u[1] * 5 / zz]); sc = 1.25
        pen(pg, [st, addv(st, [(c[0] - o[0]) * (sc - 1) / 2, (c[1] - o[1]) * (sc - 1) / 2]), addv(st, [(c[0] - o[0]) * (sc - 1), (c[1] - o[1]) * (sc - 1)])]); pg.wait_for_timeout(60)
        dr = graphs(pg)[0]["data"]; gr2 = geo(pg, gid)
        check("a resize scales all of it, both curves too (px x 1.25; cos still from 1 above the origin at the new scale)",
              abs(dr["px"] / dm["px"] - sc) < 0.002 and dr["curves"] == d1["curves"] and dist(gr2["runs"][1][0][0], [dr["x0"], dr["y0"] - dr["py"]]) < 0.05, dr)
        undo(pg); undo(pg)
        check("... two undos: back where it was", graphs(pg)[0]["data"] == d1)
        hl = geo(pg, gid)["left"]
        pen(pg, [hl, addv(hl, [-2 * d1["px"], 0]), addv(hl, [-6 * d1["px"], 0])]); pg.wait_for_timeout(60)
        d2 = graphs(pg)[0]["data"]; g2 = geo(pg, gid); X = lambda deg: d2["x0"] + deg / 90 * d2["px"]
        check("the left handle opens the window to -360 with two curves on it", d2["axes"]["xl"] == -360 and d2["curves"] == d1["curves"], d2["axes"])
        check("... EVERY curve fills the opened window: sin from (-360°, 0), cos from (-360°, 1), both to 360°",
              dist(g2["runs"][0][0][0], [X(-360), d2["y0"]]) < 0.05 and dist(g2["runs"][1][0][0], [X(-360), d2["y0"] - d2["py"]]) < 0.05
              and abs(g2["runs"][0][-1][1][0] - X(360)) < 0.05 and abs(g2["runs"][1][-1][1][0] - X(360)) < 0.05, [g2["runs"][0][0][0], g2["runs"][1][0][0]])
        p2 = el(pg, gid)["parts"]
        check("... the 8 marks still sit BEHIND both curves", [p["cls"] for p in p2].count("num") == 8 and nonum_before_curve(p2) and [p["cls"] for p in p2][-2:] == ["curve", "curve"])
        shot2("a2-sin-cos-minus360.png", sel(pg)["box"])
        th = pg.evaluate("(i) => window.__T.el(i, window.__pw.ink.thumbSvg('s0'))", gid)
        check("the page thumb (thumbSvg) carries both curves, cos last in pink", th and [p["cls"] for p in th["parts"]][-2:] == ["curve", "curve"] and th["parts"][-1]["stroke"].lower() == PINK.lower(), th and [p["cls"] for p in th["parts"]])
        undo(pg)
        check("one undo closes the window again (the curves stay)", graphs(pg)[0]["data"] == d1)

        group[0] = "H. 2b: anything else lands a new graph"
        clear_sel(pg); tap("cos")
        check("nothing selected: a block tap lands a NEW graph, as before (two graphs now; the first unchanged)", len(graphs(pg)) == 2 and graphs(pg)[0]["data"] == d1, len(graphs(pg)))
        g_new = [x for x in graphs(pg) if x["id"] != gid][0]
        check("... the new one holds just its own curve", [c["kind"] for c in g_new["data"]["curves"]] == ["cos"])
        undo(pg)
        land(pg, "-cos"); gid2 = [x for x in graphs(pg) if x["id"] != gid][0]["id"]
        pg.click("#tool-select"); pg.wait_for_timeout(30)
        bA, bB = geo(pg, gid)["box"], geo(pg, gid2)["box"]
        box_select(pg, [min(bA[0], bB[0]), min(bA[1], bB[1]), max(bA[2], bB[2]), max(bA[3], bB[3])])
        two = sel(pg)
        tap("tan")
        check("two graphs selected: a NEW graph lands; neither selected graph changes", two and len(two["ids"]) == 2 and len(graphs(pg)) == 3
              and graphs(pg)[0]["data"] == d1 and len([x for x in graphs(pg) if x["id"] == gid2][0]["data"]["curves"]) == 1, [two, len(graphs(pg))])
        undo(pg); undo(pg)
        clear_sel(pg); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        vis = pg.evaluate("window.__T.vis(0)")
        sx_, sy_ = vis[0] + 30, vis[1] + 30
        pen(pg, [[sx_, sy_], [sx_ + 30, sy_ + 10], [sx_ + 60, sy_ + 4]]); pg.wait_for_timeout(60)
        stroke_ = [x for x in recs(pg) if x["kind"] not in ("graph", "axes")]
        pick([sx_, sy_ - 2, sx_ + 60, sy_ + 12])
        one = sel(pg)
        tap("sin")
        check("a pen stroke alone selected: a NEW graph lands; the stroke and the old graph are unchanged",
              stroke_ and one and one["ids"] == [stroke_[0]["id"]] and len(graphs(pg)) == 2 and graphs(pg)[0]["data"] == d1, [one, len(graphs(pg))])

        # ------------------------------------------------------------ B: a curve on her own axes stamp
        group[0] = "H. 2b: a curve on her axes stamp"
        def place_stamp(v, deg, line=False):
            open_panel(pg)
            if pg.locator("#axesCard").count() == 0 or pg.locator("#axesCard").is_hidden(): pg.click("#trow-axes"); pg.wait_for_timeout(60)
            if pg.is_checked("#ax-deg") != deg: pg.click("#ax-deg"); pg.wait_for_timeout(30)
            if pg.is_checked("#ax-line") != line: pg.click("#ax-line"); pg.wait_for_timeout(30)
            for k, x in zip(["xs", "xe", "xd"] if line else ["xs", "xe", "xd", "ys", "ye", "yd"], v): pg.fill(f"#ax-{k}", str(x))
            pg.click("#axesPlace"); pg.wait_for_timeout(80)
            return axrecs()[-1]
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour("#000000")
        st0 = place_stamp([0, 360, 90, -2, 2, 1], True); sid = st0["id"]; sd = st0["data"]
        check("her stamp placed from the Axes card (Degrees on, 0 to 360 by 90, -2 to 2 by 1)", sd["deg"] is True and sd["xe"] == 360 and sd["ye"] == 2 and "curves" not in sd, sd)
        e_before = el(pg, sid)
        pen_colour(PINK); pick(sgeo(sid)["box"])
        check("a box picks the stamp", sel(pg) and sel(pg)["ids"] == [sid], sel(pg))
        tap("cos")
        a1 = axrecs()
        check("cos tapped with the stamp selected: NO new graph; still ONE record, the same stamp (kind axes, same id, style untouched)",
              len(recs(pg)) == 1 and len(a1) == 1 and a1[0]["id"] == sid and a1[0]["style"] == st0["style"], [x["kind"] for x in recs(pg)])
        sd1 = a1[0]["data"]
        check("... the curve is stored IN the stamp's data (data.curves: cos in pink), every other number of the stamp unchanged",
              {k: v for k, v in sd1.items() if k != "curves"} == sd and [(c["kind"], c["colour"].lower()) for c in sd1["curves"]] == [("cos", PINK.lower())], sd1)
        e1 = el(pg, sid)
        check("... her stamp draws exactly as before (same lines, ticks, heads and text, no degree glyphs, no Caveat letters), the curve added LAST, in pink",
              e1["parts"][:-1] == e_before["parts"] and e1["texts"] == e_before["texts"] and e1["parts"][-1]["cls"] == "curve" and e1["parts"][-1]["stroke"].lower() == PINK.lower()
              and not any(p["cls"] in ("num", "letter") and p["tag"] == "path" for p in e1["parts"]), [len(e_before["parts"]), len(e1["parts"])])
        sg = sgeo(sid); SX = lambda deg: sd["x0"] + deg / 90 * sd["px"]; SY = lambda v: sd["y0"] - v * sd["py"]
        check("... Degrees on: the curve follows the stamp's own scale exactly: from (0°, 1) to (360°, 1), through (180°, -1)",
              dist(sg["runs"][0][0][0], [SX(0), SY(1)]) < 0.05 and dist(sg["runs"][0][-1][1], [SX(360), SY(1)]) < 0.05
              and min(abs(x - SX(180)) + abs(y - SY(-1)) for x, y in zip(sg["xs"][0], sg["ys"][0])) < 0.6, sg["runs"])
        check("... the stamp stays selected; the panel closed", sel(pg) and sel(pg)["ids"] == [sid] and not panel_shown(pg))
        undo(pg)
        check("ONE undo takes the curve off her stamp (the stamp as placed)", len(recs(pg)) == 1 and axrecs()[0]["data"] == sd and el(pg, sid)["parts"] == e_before["parts"])
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        check("... redo puts it back", axrecs()[0]["data"] == sd1)
        if not (sel(pg) and sel(pg)["ids"] == [sid]): pick(sgeo(sid)["box"])
        tap("cos")
        check("cos tapped again: nothing changes", axrecs()[0]["data"] == sd1 and len(recs(pg)) == 1)
        undo(pg)
        check("... and no undo step was made (the next undo takes the curve off)", axrecs()[0]["data"] == sd)
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        if not (sel(pg) and sel(pg)["ids"] == [sid]): pick(sgeo(sid)["box"])
        shot2("b1-stamp-cos.png", sel(pg)["box"])
        clear_sel(pg); pen_colour(BLUE); pick(sgeo(sid)["box"]); tap("tan")
        sd2 = axrecs()[0]["data"]; sg2 = sgeo(sid)
        check("a second block tap with the stamp still selected adds a second curve (tan in Blue), same rules",
              [(c["kind"], c["colour"]) for c in sd2["curves"]] == [("cos", sd1["curves"][0]["colour"]), ("tan", BLUE)] and len(recs(pg)) == 1, sd2["curves"])
        check("... tan brings its dashed black asymptotes at 90° and 270°, cut to the stamp's drawn height (-2 to 2)",
              sg2["asym"] == [SX(90), SX(270)] and all(SY(2) - 0.02 <= y <= SY(-2) + 0.02 for y in sg2["ys"][1]) and len(sg2["runs"][1]) == 3, [sg2["asym"], len(sg2["runs"][1])])
        e2 = el(pg, sid)
        check("... drawn: the stamp's own parts, then the asymptotes, then cos, then tan (newest on top)",
              e2["parts"][:len(e_before["parts"])] == e_before["parts"] and [p["cls"] for p in e2["parts"][len(e_before["parts"]):]] == ["asym", "curve", "curve"]
              and e2["parts"][-1]["stroke"] == BLUE and e2["parts"][-3]["dash"] and e2["parts"][-3]["stroke"] == "#000000", [p["cls"] for p in e2["parts"]])
        sb = sel(pg)["box"]; st = [SX(45), SY(-1.5)]
        pen(pg, [st, addv(st, [20, 15]), addv(st, [40, 30])]); pg.wait_for_timeout(60)
        sdm = axrecs()[0]["data"]; sgm = sgeo(sid)
        check("a move carries the stamp AND its curves as one thing (x0, y0 + (40, 30); the curves' data unchanged; cos drawn from the new (0°, 1))",
              abs(sdm["x0"] - sd["x0"] - 40) < 0.011 and abs(sdm["y0"] - sd["y0"] - 30) < 0.011 and sdm["curves"] == sd2["curves"]
              and dist(sgm["runs"][0][0][0], [sdm["x0"], sdm["y0"] - sdm["py"]]) < 0.05, [sdm, sgm["runs"][0][0][0]])
        zz = z(pg); sb = sel(pg)["box"]; pad = 4 / zz
        o, c = [sb[0] - pad, sb[1] - pad], [sb[2] + pad, sb[3] + pad]
        u = subv(c, o); L = math.hypot(*u); u = [u[0] / L, u[1] / L]
        st = addv(c, [u[0] * 5 / zz, u[1] * 5 / zz]); sc = 1.25
        pen(pg, [st, addv(st, [(c[0] - o[0]) * (sc - 1) / 2, (c[1] - o[1]) * (sc - 1) / 2]), addv(st, [(c[0] - o[0]) * (sc - 1), (c[1] - o[1]) * (sc - 1)])]); pg.wait_for_timeout(60)
        sdr = axrecs()[0]["data"]; sgr = sgeo(sid)
        check("a resize scales the stamp and its curves together (px, py x 1.25; cos still from (0°, 1) at the new scale, to 360°)",
              abs(sdr["px"] / sdm["px"] - sc) < 0.002 and abs(sdr["py"] / sdm["py"] - sc) < 0.002 and sdr["curves"] == sd2["curves"]
              and dist(sgr["runs"][0][0][0], [sdr["x0"], sdr["y0"] - sdr["py"]]) < 0.05 and abs(sgr["runs"][0][-1][1][0] - (sdr["x0"] + 4 * sdr["px"])) < 0.05, sdr)
        shot2("b2-stamp-two.png", sel(pg)["box"])
        sd_keep = sdr
        undo(pg)
        check("one undo: the resize back, the curves still on", axrecs()[0]["data"] == sdm)
        undo(pg)
        check("one more: the move back", axrecs()[0]["data"] == sd2)
        pg.click("#redoBtn"); pg.wait_for_timeout(60); pg.click("#redoBtn"); pg.wait_for_timeout(60)
        check("redo, redo: moved and resized again, curves on", axrecs()[0]["data"] == sd_keep)
        if not (sel(pg) and sel(pg)["ids"] == [sid]): pick(sgeo(sid)["box"])
        pg.click(".selChips .chip[data-act='duplicate']"); pg.wait_for_timeout(80)
        ax2 = axrecs()
        check("Duplicate copies the stamp WITH its curves (two stamps, both carrying cos and tan)", len(ax2) == 2 and all(x["data"]["curves"] == sd2["curves"] for x in ax2), [len(ax2)])
        undo(pg)
        if not (sel(pg) and sel(pg)["ids"] == [sid]): pick(sgeo(sid)["box"])
        pg.click(".selChips .chip[data-act='delete']"); pg.wait_for_timeout(80)
        check("Delete takes the stamp and its curves together (nothing left, no curve drawn)", recs(pg) == [] and el(pg, sid) is None)
        undo(pg)
        check("... undo brings both back as one", len(recs(pg)) == 1 and axrecs()[0]["data"] == sd_keep and [p["cls"] for p in el(pg, sid)["parts"]][-3:] == ["asym", "curve", "curve"])
        clear_sel(pg); pg.click("#tool-select"); pg.wait_for_timeout(30)
        sgk = sgeo(sid); q = [x for x in zip(sgk["xs"][0], sgk["ys"][0])][len(sgk["xs"][0]) // 3]
        pen(pg, [[q[0] - 6, q[1] - 6], [q[0] + 6, q[1] + 6]]); pg.wait_for_timeout(60)
        check("a small box over the curve alone (no axis line in it) picks the stamp", sel(pg) and sel(pg)["ids"] == [sid], sel(pg))
        clear_sel(pg)

        # a stamp with no Degrees (no scale for degrees): one full wave fits the positive x-axis; 1 sits at 1/1.35 of the positive y-axis
        pg.evaluate("window.__T.clear('s0')"); pen_colour("#000000")
        st3 = place_stamp([-5, 5, 1, -5, 5, 1], False); sid3 = st3["id"]; s3 = st3["data"]
        pen_colour(PINK); pick(sgeo(sid3)["box"]); tap("sin")
        s3b = axrecs()[0]["data"]; g3 = sgeo(sid3)
        UX = lambda deg: s3["x0"] + deg / 360 * 5 * s3["px"]; UY = lambda v: s3["y0"] - v * 5 / 1.35 * s3["py"]
        check("Degrees off (-5 to 5): the curve is added to the stamp; 0° to 360° fills the positive x-axis (0 to 5), so it runs -360° to 360° across the whole stamp",
              [c["kind"] for c in s3b["curves"]] == ["sin"] and dist(g3["runs"][0][0][0], [UX(-360), UY(0)]) < 0.05 and dist(g3["runs"][0][-1][1], [UX(360), UY(0)]) < 0.05, g3["runs"])
        check("... height 1 at the quick graph's share of the positive y-axis (1 / 1.35 of 5 units): sin's top at 90°",
              min(abs(x - UX(90)) + abs(y - UY(1)) for x, y in zip(g3["xs"][0], g3["ys"][0])) < 0.6 and abs(min(g3["ys"][0]) - UY(1)) < 0.05, [min(g3["ys"][0]), UY(1)])
        # a number line is no place for a curve: a new graph lands
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour("#000000")
        st4 = place_stamp([-5, 5, 1, -5, 5, 1], False, line=True)
        pick(pg.evaluate("(i) => window.__pw.ink.axesGeom(window.__T.recs('s0').find((x) => x.id === i)).box", st4["id"]))
        nl = sel(pg); tap("cos")
        check("a number line selected: a NEW graph lands, the number line unchanged", nl and nl["ids"] == [st4["id"]] and len(graphs(pg)) == 1 and axrecs()[0]["data"] == st4["data"], [nl, len(graphs(pg))])

        # ------------------------------------------------------------ thumb, PDF, shared picture for both
        group[0] = "H. 2b: thumb + PDF + share"
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        show(pg, [W / 2, 260]); land(pg, "sin"); gid = graphs(pg)[0]["id"]
        pen_colour(PINK); pick(geo(pg, gid)["box"]); tap("cos"); clear_sel(pg)
        gd = graphs(pg)[0]["data"]
        show(pg, [W / 2, 800]); pen_colour("#000000")
        stc = place_stamp([0, 360, 90, -2, 2, 1], True); close_panel(pg); sid = stc["id"]
        pen_colour(PINK); pick(sgeo(sid)["box"]); tap("cos"); clear_sel(pg); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        sdd = axrecs()[0]["data"]
        gb, sbx = geo(pg, gid)["box"], sgeo(sid)["box"]
        check("the page holds a two-curve graph and a stamp carrying a curve, apart", len(graphs(pg)) == 1 and len(gd["curves"]) == 2 and len(sdd["curves"]) == 1 and gb[3] < sbx[1], [gb, sbx])
        ts = pg.evaluate("(i) => window.__T.el(i, window.__pw.ink.thumbSvg('s0'))", sid)
        tg = pg.evaluate("(i) => window.__T.el(i, window.__pw.ink.thumbSvg('s0'))", gid)
        check("thumbSvg: the graph with both curves, the stamp with its curve last in pink",
              tg and [p["cls"] for p in tg["parts"]].count("curve") == 2 and ts and ts["parts"][-1]["cls"] == "curve" and ts["parts"][-1]["stroke"].lower() == PINK.lower(), [tg and len(tg["parts"]), ts and ts["parts"][-1]])
        pg.click("#listBtn"); pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(300)
        okth = pg.evaluate("([a, b]) => !!document.querySelector(`#plThumbs .thumbP[data-index='1'] [data-id='${a}'] path.curve`) && document.querySelectorAll(`#plThumbs .thumbP[data-index='1'] [data-id='${b}'] path.curve`).length === 2", [sid, gid])
        check("the page list's thumb of page 1 draws the stamp's curve and both graph curves", okth)
        tb = rect(pg, "#plThumbs .thumbP[data-index='1']")
        thumb_png = SH2 / "_thumb.png"
        pg.screenshot(path=str(thumb_png), clip={"x": tb["l"] - 6, "y": tb["t"] - 6, "width": tb["w"] + 12, "height": tb["h"] + 12})
        doc = pdf_of(pg, "Graph 2b"); p0 = doc[0]; k = p0.rect.width / W
        drs = p0.get_drawings()
        pinks = [dr for dr in drs if dr.get("color") is not None and dr["color"][0] > 0.9 and 0.0 < dr["color"][1] < 0.1 and dr["color"][2] > 0.45]
        check("the PDF strokes the pink curves (the graph's cos and the stamp's cos) at the pen's width", len(pinks) >= 2 and all(abs(dr["width"] - pen_w * k) < 0.05 for dr in pinks), [len(pinks), [dr["width"] for dr in pinks]])
        pix = p0.get_pixmap(dpi=144); img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"); sk = pix.width / W
        def pinkish(p): return p[0] > 180 and p[1] < 110 and p[2] > 70
        on_g = [gd["x0"] + 2 * gd["px"], gd["y0"] + gd["py"]]                        # the graph's cos at 180° (-1)
        on_s = [sdd["x0"] + 2 * sdd["px"], sdd["y0"] + sdd["py"]]                    # the stamp's cos at 180° (-1 on its own scale)
        on_s0 = [sdd["x0"] + 0.02 * sdd["px"], sdd["y0"] - sdd["py"]]                # and at 0° (1)
        check("... the PDF page shows pink on the graph's cos at 180° and on the stamp's cos at 180° and at 0°",
              any_px(img, on_g[0] * sk, on_g[1] * sk, 2, pinkish) and any_px(img, on_s[0] * sk, on_s[1] * sk, 2, pinkish) and any_px(img, on_s0[0] * sk, on_s0[1] * sk, 3, pinkish))
        check("... the stamp's numbers are still Helvetica text in the PDF (its own look), the graph's marks still glyph outlines",
              "90°" in p0.get_text() and "180°" in p0.get_text() and any("Helvetica" in f[3] for f in p0.get_fonts()), [p0.get_text()[:60], p0.get_fonts()])
        pdf_img = img
        doc.close()
        th_img = Image.open(str(thumb_png)).convert("RGB")
        hh = 800; t2 = th_img.resize((round(th_img.width * hh / th_img.height), hh)); p2i = pdf_img.resize((round(pdf_img.width * hh / pdf_img.height), hh))
        comp = Image.new("RGB", (t2.width + p2i.width + 30, hh + 20), (210, 210, 210)); comp.paste(t2, (10, 10)); comp.paste(p2i, (t2.width + 20, 10))
        if comp.width > 900: comp = comp.resize((900, round(comp.height * 900 / comp.width)))
        comp.save(str(SH2 / "c1-thumb-pdf.png")); thumb_png.unlink()
        pg.click("#plSelect"); pg.wait_for_timeout(40)
        pg.locator("#plThumbs .thumbP[data-index='1']").click(); pg.wait_for_timeout(40)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg")
        pg.evaluate("window.__shared = null")
        pg.click("#shareDlg button[data-share='images']"); pg.wait_for_selector("#shareReady", timeout=30000)
        pg.click("#shareDlg button[data-share='send']"); pg.wait_for_function("window.__shared", timeout=10000)
        png = pg.evaluate("""async () => { const f = window.__shared.files[0]; const u = new Uint8Array(await f.arrayBuffer()); let s = '';
          for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return [f.type, btoa(s)]; }""")
        si = Image.open(io.BytesIO(base64.b64decode(png[1]))).convert("RGB"); ss = si.width / W
        check("a shared picture shows pink on the graph's cos and on the stamp's cos",
              any_px(si, on_g[0] * ss, on_g[1] * ss, 2, pinkish) and any_px(si, on_s[0] * ss, on_s[1] * ss, 2, pinkish))
        if pg.evaluate("window.__pw.tick()") is not None: pg.click("#plDone"); pg.wait_for_timeout(40)
        if not pg.locator("#pageList").is_hidden(): pg.click("#plClose"); pg.wait_for_timeout(40)
        keep_g, keep_s = graphs(pg)[0], axrecs()[0]
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(200)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        pg.reload(); ready(pg); open_note(pg); pg.evaluate(HELP)
        check("after a reload the two-curve graph and the stamp with its curve are back exactly",
              graphs(pg) and graphs(pg)[0]["data"] == keep_g["data"] and axrecs() and axrecs()[0]["data"] == keep_s["data"] and el(pg, keep_s["id"])["parts"][-1]["cls"] == "curve")

        # ------------------------------------------------------------ I: pw-v9l, the cubic (f(x) = x³ - 3x and its mirror)
        group[0] = "I. cubic: landing"
        def shotc(name, bx, top=70, bottom=70, w=700):
            show(pg, [(bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2])
            tl = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[0], bx[1]]); br = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[2], bx[3]])
            y0 = max(0, tl[1] - top); y1 = min(800, br[1] + bottom); x0 = max(0, min(1280 - w, (tl[0] + br[0]) / 2 - w / 2))
            SHC.mkdir(parents=True, exist_ok=True); pg.screenshot(path=str(SHC / name), clip={"x": x0, "y": y0, "width": w, "height": y1 - y0})
        def cpts(i):                                               # every curve's points, page px
            return pg.evaluate("""(i) => { const r = window.__T.recs('s0').find((x) => x.id === i); const g = window.__pw.ink.graphGeom(r);
              return g.curves.map((c) => c.runs.flat()); }""", i)
        cub = lambda x: x ** 3 - 3 * x
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        vis = pg.evaluate("window.__T.vis(0)"); mid = [(vis[0] + vis[2]) / 2, (vis[1] + vis[3]) / 2]
        land(pg, "cubic")
        gs = graphs(pg)
        check("cubic: a tap on its block lands ONE 'graph' record on page 1 and closes the panel and the card",
              len(recs(pg)) == 1 and len(gs) == 1 and not panel_shown(pg) and not gcard_shown(pg), [r["kind"] for r in recs(pg)])
        cg = gs[0]; cd = cg["data"]; cid = cg["id"]; pxc = round(W / 3 / 5.2, 2)
        check("... its axes: fam 'cubic', the window x -2.6 to 2.6, y -3.2 to 3.2; px a third of the page over 5.2 units, py 0.8 px; the axes' style black",
              cd["axes"] == {"on": True, "fam": "cubic", "xl": -2.6, "xr": 2.6, "yh": 3.2} and cd["px"] == pxc and cd["py"] == round(0.8 * pxc, 2)
              and cg["style"]["colour"] == "#000000", [cd, cg["style"]])
        check("... ONE curve, an ordinary curves entry: cubic in the pen's colour and width, offset 0, stretch 1",
              cd["curves"] == [{"kind": "cubic", "colour": BLUE, "width": pen_w, "dx": 0, "dy": 0, "sx": 1, "sy": 1}], cd["curves"])
        g = geo(pg, cid); bx = g["box"]
        check("... the origin (where the axes cross) in the middle of the part of the page she sees; the whole graph 8 px inside the page",
              abs(cd["x0"] - mid[0]) < 1 and abs(cd["y0"] - mid[1]) < 1 and bx[0] >= 8 - 0.01 and bx[1] >= 8 - 0.01 and bx[2] <= W - 8 + 0.01 and bx[3] <= H - 8 + 0.01, [cd["x0"], cd["y0"], mid, bx])
        xa, ya = g["lines"][0], g["lines"][1]
        check("... the axes cross in the MIDDLE of the window: the x-axis from x = -2.6 to past 2.6, the y-axis from -3.2 to past 3.2, both through the origin",
              abs(xa[0][0] - (cd["x0"] - 2.6 * cd["px"])) < 0.02 and xa[1][0] > cd["x0"] + 2.6 * cd["px"] and abs(xa[0][1] - cd["y0"]) < 0.01
              and abs(ya[0][1] - (cd["y0"] + 3.2 * cd["py"])) < 0.02 and ya[1][1] < cd["y0"] - 3.2 * cd["py"] and abs(ya[0][0] - cd["x0"]) < 0.01, g["lines"])
        check("... PLAIN axes: no ticks, no numbers, no degrees; only the letters x and y", g["ticks"] == [] and [l["t"] for l in g["labels"]] == ["x", "y"] and all(l["cls"] == "letter" for l in g["labels"]), g["labels"])
        e = el(pg, cid)
        check("... drawn: axes, heads and the two letters BLACK (letters filled glyph outlines, no <text>), then the curve in Blue",
              [p["cls"] for p in e["parts"]] == ["axis", "head", "letter", "letter", "curve"] and all(p["stroke"] == "#000000" for p in e["parts"][:2])
              and all(p["fill"] == "#000000" and p["tag"] == "path" for p in e["parts"][2:4]) and e["parts"][4]["stroke"] == BLUE and e["texts"] == 0, e["parts"])
        check("... no round left handle on a cubic (that handle is trig only)", g["left"] is None)
        P = cpts(cid)[0]; XX = lambda q: (q[0] - cd["x0"]) / cd["px"]; YY = lambda q: (cd["y0"] - q[1]) / cd["py"]
        check("... the curve is f(x) = x³ - 3x itself (every point within 0.02 of it, or on the cut), and stays inside the window",
              len(P) > 50 and all(abs(YY(q) - cub(XX(q))) < 0.02 or abs(abs(YY(q)) - 3.2) < 0.02 for q in P) and all(abs(XX(q)) <= 2.6 + 1e-6 and abs(YY(q)) <= 3.2 + 0.01 for q in P), len(P))
        check("... ONE run from the BOTTOM edge (left arm) to the TOP edge (right arm): both arms carry on to the window's edge",
              len(g["runs"][0]) == 1 and abs(YY(g["runs"][0][0][0]) + 3.2) < 0.01 and abs(YY(g["runs"][0][0][1]) - 3.2) < 0.01 and XX(g["runs"][0][0][0]) < -2 and XX(g["runs"][0][0][1]) > 2, g["runs"])
        check("... over a hill at (-1, 2), through the origin, a dip at (1, -2)",
              min(abs(XX(q) + 1) + abs(YY(q) - 2) for q in P) < 0.06 and min(abs(XX(q)) + abs(YY(q)) for q in P) < 0.06 and min(abs(XX(q) - 1) + abs(YY(q) + 2) for q in P) < 0.06
              and abs(max(YY(q) for q in P if abs(XX(q)) < 1.5) - 2) < 0.01,
              [min(abs(XX(q) + 1) + abs(YY(q) - 2) for q in P), min(abs(XX(q)) + abs(YY(q)) for q in P), min(abs(XX(q) - 1) + abs(YY(q) + 2) for q in P), max(YY(q) for q in P if abs(XX(q)) < 1.5)])
        cubic_box = bx
        shotc("2-cubic-landed.png", bx)
        undo(pg)
        check("ONE undo takes it away", recs(pg) == [])
        land(pg, "-cubic"); mg = graphs(pg)[0]; md = mg["data"]; mgeo = geo(pg, mg["id"]); P2 = cpts(mg["id"])[0]
        check("−cubic: its mirror lands the same way (same window): -f(x) itself, from the TOP edge on the left to the BOTTOM edge on the right",
              md["axes"] == {"on": True, "fam": "cubic", "xl": -2.6, "xr": 2.6, "yh": 3.2} and md["curves"][0]["kind"] == "-cubic"
              and abs((md["y0"] - mgeo["runs"][0][0][0][1]) / md["py"] - 3.2) < 0.01 and abs((md["y0"] - mgeo["runs"][0][0][1][1]) / md["py"] + 3.2) < 0.01
              and all(abs((md["y0"] - q[1]) / md["py"] + cub((q[0] - md["x0"]) / md["px"])) < 0.02 or abs(abs((md["y0"] - q[1]) / md["py"]) - 3.2) < 0.02 for q in P2), mgeo["runs"])
        shotc("3-minus-cubic-landed.png", mgeo["box"])
        undo(pg); land(pg, "cubic"); cid = graphs(pg)[0]["id"]; cd = graphs(pg)[0]["data"]

        group[0] = "I. cubic: selected"
        pick(geo(pg, cid)["box"])
        check("a box picks the whole cubic graph", sel(pg) and sel(pg)["ids"] == [cid], sel(pg))
        check("... the Axes pill shows; there is NO round left handle", pg.locator(".selChips .chip.gchip").count() == 1 and pg.locator(".sel .selgl").count() == 0)
        shotc("4-selected.png", sel(pg)["box"], top=110)
        pg.click(".selChips .chip.gchip"); pg.wait_for_timeout(60)
        check("the Axes pill hides the axes and letters; the curve stays", graphs(pg)[0]["data"]["axes"]["on"] is False and [p["cls"] for p in el(pg, cid)["parts"]] == ["curve"])
        pg.click(".selChips .chip.gchip"); pg.wait_for_timeout(60)
        check("... and shows them again", graphs(pg)[0]["data"]["axes"]["on"] is True and len(el(pg, cid)["parts"]) == 5)
        undo(pg); undo(pg)
        check("... one undo step each", graphs(pg)[0]["data"] == cd)
        if not (sel(pg) and sel(pg)["ids"] == [cid]): pick(geo(pg, cid)["box"])
        pg.click(f'#tray .sw[data-colour="{THIRD}"]'); pg.wait_for_timeout(60)
        c3 = graphs(pg)[0]
        check("a colour tap recolours the curve only (the axes style stays black)", c3["data"]["curves"][0]["colour"].lower() == THIRD.lower() and c3["style"]["colour"] == "#000000"
              and [p["stroke"] for p in el(pg, cid)["parts"][:2]] == ["#000000", "#000000"], c3["data"]["curves"])
        undo(pg)
        check("... one undo step", graphs(pg)[0]["data"] == cd)
        if not (sel(pg) and sel(pg)["ids"] == [cid]): pick(geo(pg, cid)["box"])
        st = [cd["x0"] + 1.5 * cd["px"], cd["y0"] + 0.5 * cd["py"]]
        pen(pg, [st, addv(st, [20, 15]), addv(st, [40, 30])]); pg.wait_for_timeout(60)
        dm = graphs(pg)[0]["data"]
        check("a move carries the whole graph (x0, y0 + (40, 30); window and curve unchanged)",
              abs(dm["x0"] - cd["x0"] - 40) < 0.011 and abs(dm["y0"] - cd["y0"] - 30) < 0.011 and dm["curves"] == cd["curves"] and dm["axes"] == cd["axes"], dm)
        zz = z(pg); sb = sel(pg)["box"]; pad = 4 / zz
        o, c = [sb[0] - pad, sb[1] - pad], [sb[2] + pad, sb[3] + pad]
        u = subv(c, o); L = math.hypot(*u); u = [u[0] / L, u[1] / L]
        st = addv(c, [u[0] * 5 / zz, u[1] * 5 / zz]); sc = 1.25
        pen(pg, [st, addv(st, [(c[0] - o[0]) * (sc - 1) / 2, (c[1] - o[1]) * (sc - 1) / 2]), addv(st, [(c[0] - o[0]) * (sc - 1), (c[1] - o[1]) * (sc - 1)])]); pg.wait_for_timeout(60)
        dr = graphs(pg)[0]["data"]; Pr = cpts(cid)[0]
        check("a resize scales all of it (px, py x 1.25), the curve still f(x) at the new scale",
              abs(dr["px"] / dm["px"] - sc) < 0.002 and abs(dr["py"] / dm["py"] - sc) < 0.002 and dr["curves"] == cd["curves"] and dr["axes"] == cd["axes"]
              and all(abs((dr["y0"] - q[1]) / dr["py"] - cub((q[0] - dr["x0"]) / dr["px"])) < 0.02 or abs(abs((dr["y0"] - q[1]) / dr["py"]) - 3.2) < 0.02 for q in Pr), dr)
        undo(pg); undo(pg)
        check("... two undos: back where it landed", graphs(pg)[0]["data"] == cd)

        group[0] = "I. cubic: a second curve"
        if not (sel(pg) and sel(pg)["ids"] == [cid]): pick(geo(pg, cid)["box"])
        pen_colour(PINK); pick(geo(pg, cid)["box"]); tap("-cubic")
        dd = graphs(pg)[0]["data"]
        check("−cubic tapped with the cubic graph selected: ONE record, −cubic ADDED in pink; window, size and place unchanged",
              len(recs(pg)) == 1 and [(k["kind"], k["colour"].lower()) for k in dd["curves"]] == [("cubic", BLUE.lower()), ("-cubic", PINK.lower())]
              and {k: v for k, v in dd.items() if k != "curves"} == {k: v for k, v in cd.items() if k != "curves"}, dd)
        check("... drawn in the order added: two curves last, −cubic (pink) on top", [p["cls"] for p in el(pg, cid)["parts"]][-2:] == ["curve", "curve"] and el(pg, cid)["parts"][-1]["stroke"].lower() == PINK.lower())
        if not (sel(pg) and sel(pg)["ids"] == [cid]): pick(geo(pg, cid)["box"])
        tap("cubic")
        check("cubic tapped again (already there): nothing changes", graphs(pg)[0]["data"] == dd and len(recs(pg)) == 1)
        if not (sel(pg) and sel(pg)["ids"] == [cid]): pick(geo(pg, cid)["box"])
        clear_sel(pg); shotc("5-two-curves.png", geo(pg, cid)["box"])
        pick(geo(pg, cid)["box"]); tap("sin")
        check("sin tapped with the cubic graph selected: the axes do not match, so a NEW graph lands; the cubic graph unchanged",
              len(graphs(pg)) == 2 and [x for x in graphs(pg) if x["id"] == cid][0]["data"] == dd
              and [k["kind"] for k in [x for x in graphs(pg) if x["id"] != cid][0]["data"]["curves"]] == ["sin"], len(graphs(pg)))
        tid = [x for x in graphs(pg) if x["id"] != cid][0]["id"]; td = [x for x in graphs(pg) if x["id"] == tid][0]["data"]
        clear_sel(pg); pg.evaluate("(i) => window.__pw.ink.selectRecs('s0', [i])", tid); pg.wait_for_timeout(40)   # it lies over the cubic: picked by id
        if sel(pg) and sel(pg)["ids"] == [tid]:
            tap("cubic")
            check("cubic tapped with a trig graph selected: a NEW cubic graph lands; the trig graph unchanged",
                  len(graphs(pg)) == 3 and [x for x in graphs(pg) if x["id"] == tid][0]["data"] == td, len(graphs(pg)))
            undo(pg)
        else:
            check("cubic tapped with a trig graph selected: a NEW cubic graph lands (could not pick the trig graph alone)", False, sel(pg))
        undo(pg); clear_sel(pg)
        check("... undo, undo: the two-curve cubic graph alone", len(recs(pg)) == 1 and graphs(pg)[0]["data"] == dd)

        group[0] = "I. cubic: on her axes stamp"
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour("#000000")
        stc = place_stamp([-5, 5, 1, -5, 5, 1], False); sidc = stc["id"]; sdc = stc["data"]; close_panel(pg)
        e_before = el(pg, sidc)
        pen_colour(BLUE); pick(sgeo(sidc)["box"]); tap("cubic")
        a1 = axrecs(); s1 = a1[0]["data"]
        check("cubic tapped with her stamp selected: NO new graph; the curve stored in the stamp's data, everything else unchanged",
              len(recs(pg)) == 1 and a1[0]["id"] == sidc and {k: v for k, v in s1.items() if k != "curves"} == sdc and [k["kind"] for k in s1["curves"]] == ["cubic"], [x["kind"] for x in recs(pg)])
        e1 = el(pg, sidc)
        check("... her stamp draws exactly as before, the curve added last in Blue", e1["parts"][:-1] == e_before["parts"] and e1["parts"][-1]["cls"] == "curve" and e1["parts"][-1]["stroke"] == BLUE)
        sg = sgeo(sidc); kx, ky = 5 / 2.6, 5 / 3.2
        SXc = lambda x: sdc["x0"] + x * kx / sdc["xd"] * sdc["px"]; SYc = lambda v: sdc["y0"] - v * ky / sdc["yd"] * sdc["py"]
        check("... centred on the stamp's ORIGIN, the quick graph's window fitted to the stamp (x 2.6 at 5, y 3.2 at 5): through (0, 0), hill at (-1, 2), dip at (1, -2)",
              max(min(math.hypot(x - SXc(a), y - SYc(v)) for x, y in zip(sg["xs"][0], sg["ys"][0])) for a, v in [(0, 0), (-1, 2), (1, -2)]) < 1.5,
              [min(math.hypot(x - SXc(a), y - SYc(v)) for x, y in zip(sg["xs"][0], sg["ys"][0])) for a, v in [(0, 0), (-1, 2), (1, -2)]])
        check("... cut to the stamp's drawn height (-5 to 5), from its bottom edge to its top edge",
              all(SYc(3.2) - 0.02 <= y <= SYc(-3.2) + 0.02 for y in sg["ys"][0]) and abs(sg["runs"][0][0][0][1] - SYc(-3.2)) < 0.05 and abs(sg["runs"][0][-1][1][1] - SYc(3.2)) < 0.05, sg["runs"])
        shotc("6-on-stamp.png", sel(pg)["box"])
        if not (sel(pg) and sel(pg)["ids"] == [sidc]): pick(sgeo(sidc)["box"])
        tap("cos")
        check("cos tapped with the cubic-carrying stamp selected: a NEW graph lands; the stamp unchanged", len(graphs(pg)) == 1 and axrecs()[0]["data"] == s1, len(graphs(pg)))
        undo(pg); undo(pg)
        check("... undo, undo: the stamp bare again", len(recs(pg)) == 1 and axrecs()[0]["data"] == sdc)

        group[0] = "I. cubic: thumb + PDF + share"
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        show(pg, [W / 2, 260]); land(pg, "cubic"); cid = graphs(pg)[0]["id"]
        pen_colour(PINK); pick(geo(pg, cid)["box"]); tap("-cubic"); clear_sel(pg)
        cdd = graphs(pg)[0]["data"]
        show(pg, [W / 2, 800]); pen_colour("#000000")
        stc = place_stamp([-5, 5, 1, -5, 5, 1], False); close_panel(pg); sidc = stc["id"]
        pen_colour(PINK); pg.click("#tool-select"); pg.wait_for_timeout(30)
        pg.evaluate("(i) => window.__pw.ink.selectRecs('s0', [i])", sidc); pg.wait_for_timeout(40)   # its box reaches the graph's arm: picked by id
        tap("cubic"); clear_sel(pg); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        sdd = axrecs()[0]["data"]
        check("the page holds the two-curve cubic graph and a stamp carrying a cubic (one graph only)", len(graphs(pg)) == 1 and [k["kind"] for k in sdd.get("curves", [])] == ["cubic"], sdd)
        tg = pg.evaluate("(i) => window.__T.el(i, window.__pw.ink.thumbSvg('s0'))", cid)
        check("thumbSvg: the cubic graph with both curves, no numbers", tg and [p["cls"] for p in tg["parts"]] == ["axis", "head", "letter", "letter", "curve", "curve"], tg and [p["cls"] for p in tg["parts"]])
        pg.click("#listBtn"); pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(300)
        okth = pg.evaluate("([a, b]) => [document.querySelectorAll(`#plThumbs .thumbP[data-index='1'] [data-id='${a}'] path.curve`).length, document.querySelectorAll(`#plThumbs .thumbP[data-index='1'] [data-id='${b}'] path.curve`).length]", [cid, sidc])
        check("the page list's thumb of page 1 draws both cubic curves and the stamp's cubic", okth == [2, 1], okth)
        tb = rect(pg, "#plThumbs .thumbP[data-index='1']")
        thumb_png = SHC / "_thumb.png"
        pg.screenshot(path=str(thumb_png), clip={"x": tb["l"] - 6, "y": tb["t"] - 6, "width": tb["w"] + 12, "height": tb["h"] + 12})
        doc = pdf_of(pg, "Cubic"); p0 = doc[0]; k = p0.rect.width / W
        pix = p0.get_pixmap(dpi=144); img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"); sk = pix.width / W
        on_b = [cdd["x0"] + cdd["px"], cdd["y0"] + 2 * cdd["py"]]                 # the cubic's dip (1, -2): Blue
        on_p = [cdd["x0"] + cdd["px"], cdd["y0"] - 2 * cdd["py"]]                 # the −cubic's hill (1, 2): pink
        on_s = [sdd["x0"] + 1 * 5 / 2.6 * sdd["px"], sdd["y0"] + 2 * 5 / 3.2 * sdd["py"]]   # the stamp's cubic at (1, -2)
        on_x = [cdd["x0"] - 2.4 * cdd["px"], cdd["y0"]]                           # the x-axis, black
        pdf_hits = [any_px(img, on_b[0] * sk, on_b[1] * sk, 2, bluish), any_px(img, on_p[0] * sk, on_p[1] * sk, 2, pinkish), any_px(img, on_s[0] * sk, on_s[1] * sk, 2, pinkish),
                    any_px(img, on_x[0] * sk, on_x[1] * sk, 2, darkish)]
        check("the PDF page shows Blue at the cubic's dip, pink at the −cubic's hill and on the stamp's cubic, black on the x-axis", all(pdf_hits), [pdf_hits, cdd, sdd])
        pt = p0.get_text()
        check("... no degree marks anywhere in the PDF (the cubic's axes are plain; only the stamp's own numbers are text)", "°" not in pt, pt[:80])
        doc.close()
        th_img = Image.open(str(thumb_png)).convert("RGB")
        hh = 800; t2 = th_img.resize((round(th_img.width * hh / th_img.height), hh)); p2i = img.resize((round(img.width * hh / img.height), hh))
        comp = Image.new("RGB", (t2.width + p2i.width + 30, hh + 20), (210, 210, 210)); comp.paste(t2, (10, 10)); comp.paste(p2i, (t2.width + 20, 10))
        if comp.width > 900: comp = comp.resize((900, round(comp.height * 900 / comp.width)))
        comp.save(str(SHC / "7-thumb-pdf.png")); thumb_png.unlink()
        pg.click("#plSelect"); pg.wait_for_timeout(40)
        pg.locator("#plThumbs .thumbP[data-index='1']").click(); pg.wait_for_timeout(40)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg")
        pg.evaluate("window.__shared = null")
        pg.click("#shareDlg button[data-share='images']"); pg.wait_for_selector("#shareReady", timeout=30000)
        pg.click("#shareDlg button[data-share='send']"); pg.wait_for_function("window.__shared", timeout=10000)
        png = pg.evaluate("""async () => { const f = window.__shared.files[0]; const u = new Uint8Array(await f.arrayBuffer()); let s = '';
          for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return [f.type, btoa(s)]; }""")
        si = Image.open(io.BytesIO(base64.b64decode(png[1]))).convert("RGB"); ss = si.width / W
        sh_hits = [any_px(si, on_b[0] * ss, on_b[1] * ss, 2, bluish), any_px(si, on_p[0] * ss, on_p[1] * ss, 2, pinkish), any_px(si, on_s[0] * ss, on_s[1] * ss, 2, pinkish)]
        check("a shared picture shows Blue at the cubic's dip, pink at the −cubic's hill and on the stamp's cubic", all(sh_hits), sh_hits)
        if pg.evaluate("window.__pw.tick()") is not None: pg.click("#plDone"); pg.wait_for_timeout(40)
        if not pg.locator("#pageList").is_hidden(): pg.click("#plClose"); pg.wait_for_timeout(40)
        keep_g, keep_s = graphs(pg)[0], axrecs()[0]
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(200)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        pg.reload(); ready(pg); open_note(pg); pg.evaluate(HELP)
        check("after a reload the two-curve cubic graph and the stamp with its cubic are back exactly",
              graphs(pg) and graphs(pg)[0]["data"] == keep_g["data"] and axrecs() and axrecs()[0]["data"] == keep_s["data"])

        # ------------------------------------------------------------ J: pw-v9m, unit 3: tap the curve (slide and stretch inside the axes)
        group[0] = "J. tap the curve: picking"
        SH3 = ROOT / "_build" / "graph" / "unit3"; SH3.mkdir(parents=True, exist_ok=True)
        def shot3(name, bx, top=110, bottom=70, w=700):
            show(pg, [(bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2])
            tl = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[0], bx[1]]); br = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [bx[2], bx[3]])
            y0 = max(0, tl[1] - top); y1 = min(800, br[1] + bottom); x0 = max(0, min(1280 - w, (tl[0] + br[0]) / 2 - w / 2))
            pg.screenshot(path=str(SH3 / name), clip={"x": x0, "y": y0, "width": w, "height": y1 - y0})
        def gd(): return graphs(pg)[0]["data"]
        def selt(): pg.click("#tool-select"); pg.wait_for_timeout(30)
        def tapp(p): pen(pg, [p]); pg.wait_for_timeout(60)
        def drag(p, v, n=5): pen(pg, [p] + [addv(p, [v[0] * k / n, v[1] * k / n]) for k in range(1, n + 1)]); pg.wait_for_timeout(70)
        def fval(kind, t):
            k = kind.lstrip("-"); s_ = -1 if kind.startswith("-") else 1
            if k == "cubic": return s_ * (t ** 3 - 3 * t)
            return s_ * {"sin": math.sin, "cos": math.cos, "tan": math.tan}[k](math.radians(t))
        def cpt(d, i, u):                                          # the page point of curve i at x = u (degrees, or units for a cubic)
            c = d["curves"][i]; cub_ = d["axes"].get("fam") == "cubic"
            v = c.get("sy", 1) * fval(c["kind"], (u - c.get("dx", 0)) / c.get("sx", 1)) + c.get("dy", 0)
            return [d["x0"] + (u if cub_ else u / 90) * d["px"], d["y0"] - v * d["py"]]
        def but(d, *ks): return {k: v for k, v in d.items() if k not in ks}
        def cpts0(i, j=0):
            return pg.evaluate("""([i, j]) => { const r = window.__T.recs('s0').find((x) => x.id === i); return window.__pw.ink.graphGeom(r).curves[j].runs.flat(); }""", [i, j])
        XD = lambda d, u: d["x0"] + u / 90 * d["px"]; YD = lambda d, v: d["y0"] - v * d["py"]
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        show(pg, [W / 2, 300]); land(pg, "sin"); gid = graphs(pg)[0]["id"]; d0 = gd(); g0 = geo(pg, gid)
        selt(); tapp(cpt(d0, 0, 90)); s = sel(pg)
        check("a select tap on the sine's curve picks the CURVE alone: the one graph, curve 0", s and s["ids"] == [gid] and s["curve"] == 0, s)
        acts = pg.evaluate("[...document.querySelectorAll('.selChips .chip')].map((b) => b.dataset.act)")
        check("... its chips: the Axes pill and Delete only (no Copy, Cut, Duplicate, no Dotted copy)", sorted(acts) == ["axes", "delete"], acts)
        hs = pg.evaluate("[...document.querySelectorAll('.sel circle')].map((c) => c.getAttribute('class'))")
        check("... TWO round handles only, right and bottom: no corners, no turn ring, no left handle", sorted(hs) == ["selcx", "selcy"], hs)
        zz = z(pg); pad = 4 / zz; cb = s and s["cbox"]
        check("... the dashed box hugs what shows of the curve (0 to 360 across, 1 to -1 up), 4 px out; the right handle mid right side, the bottom one mid bottom",
              cb and abs(cb[0] - (XD(d0, 0) - pad)) < 0.6 and abs(cb[2] - (XD(d0, 360) + pad)) < 0.6 and abs(cb[1] - (YD(d0, 1) - pad)) < 0.6 and abs(cb[3] - (YD(d0, -1) + pad)) < 0.6
              and abs(s["hx"][0] - cb[2]) < 0.01 and abs(s["hx"][1] - (cb[1] + cb[3]) / 2) < 0.01 and abs(s["hy"][0] - (cb[0] + cb[2]) / 2) < 0.01 and abs(s["hy"][1] - cb[3]) < 0.01, [cb, s and s["hx"], s and s["hy"]])
        check("... the tap changed nothing", gd() == d0)
        shot3("1-curve-picked.png", g0["box"])
        tapp([XD(d0, 135), d0["y0"]])
        s = sel(pg)
        check("a tap on the x-axis (inside the curve's box) picks the WHOLE graph, as before", s and s["ids"] == [gid] and s["curve"] is None, s)
        tapp(cpt(d0, 0, 90)); s = sel(pg)
        check("with the whole graph selected, a tap on its curve picks the curve alone", s and s["ids"] == [gid] and s["curve"] == 0, s)
        tapp([XD(d0, 45), YD(d0, -0.6)]); s = sel(pg)
        check("a tap on bare paper inside the curve's box keeps the curve picked", s and s["curve"] == 0, s)
        tapp([XD(d0, 200), YD(d0, 4)]); s = sel(pg)
        check("a tap on bare paper outside picks nothing", s is None, s)
        box_select(pg, g0["box"]); s = sel(pg)
        check("a box still picks the WHOLE graph (corners, turn ring, left handle), exactly as before", s and s["ids"] == [gid] and s["curve"] is None
              and pg.locator(".sel .selh").count() == 4 and pg.locator(".sel .selgl").count() == 1, s)
        clear_sel(pg); selt(); tapp(cpt(d0, 0, 90))

        group[0] = "J. tap the curve: slide"
        drag(cpt(d0, 0, 90), [-0.5 * d0["px"], 0])
        d1 = gd(); c1 = d1["curves"][0]; g1 = geo(pg, gid)
        check("a drag on the picked curve slides it LEFT 45 degrees: only its dx changes (-45); dy 0, stretches 1; the graph's place, size and window unchanged",
              abs(c1["dx"] + 45) < 0.05 and c1["dy"] == 0 and c1["sx"] == 1 and c1["sy"] == 1 and but(c1, "dx") == but(d0["curves"][0], "dx") and but(d1, "curves") == but(d0, "curves"), c1)
        check("... the axes, ticks, 90 degree marks and letters did not move", g1["labels"] == g0["labels"] and g1["lines"] == g0["lines"] and g1["ticks"] == g0["ticks"])
        r1 = g1["runs"][0]
        check("... the curve still fills the window, one run 0 to 360; at 360 it reads sin(405): the wave that came in from the right",
              len(r1) == 1 and abs(r1[0][0][0] - XD(d0, 0)) < 0.01 and abs(r1[0][1][0] - XD(d0, 360)) < 0.01 and abs(r1[0][1][1] - YD(d0, math.sin(math.radians(405)))) < 0.3
              and abs(r1[0][0][1] - YD(d0, math.sin(math.radians(45)))) < 0.3, r1)
        s = sel(pg)
        check("... still picked; its box went with it (the right handle level with the curve's middle)", s and s["curve"] == 0 and abs(s["hx"][1] - (s["cbox"][1] + s["cbox"][3]) / 2) < 0.01, s)
        shot3("2-slid-left.png", g0["box"])
        undo(pg)
        check("ONE undo: back where it landed", gd() == d0, gd()["curves"])
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        check("redo: slid again", gd() == d1)
        undo(pg)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        drag(cpt(d0, 0, 90), [0.25 * d0["px"], -0.3 * d0["py"]]); c = gd()["curves"][0]
        check("a drag right and up: dx +22.5, dy +0.3 (free values, no snapping)", abs(c["dx"] - 22.5) < 0.05 and abs(c["dy"] - 0.3) < 0.002, c)
        undo(pg)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        drag(cpt(d0, 0, 90), [0, 4 * d0["py"]]); c = gd()["curves"][0]
        check("dragged far down: it stops with its middle line on the window's bottom (dy -1.35), so it can always be grabbed back", c["dy"] == -1.35, c)
        undo(pg)
        lims = pg.evaluate("""(i) => { const r = window.__T.recs('s0').find((x) => x.id === i), GR = window.__GR;
          const a = GR.curveSet(r, 0, { dx: 1000, dy: 9, sx: 100, sy: 0.001 }).data.curves[0], b = GR.curveSet(r, 0, { dx: -1000, dy: -9, sx: 0.01, sy: 50 }).data.curves[0];
          return [a, b, GR.SMIN, GR.SMAX]; }""", gid)
        check("the limits (graph.js curveSet): stretches 1/8 to 8, dy within the window, a trig dx kept to one period about 0 (1000 -> 1000 - 3 x 360 / 8 ...)",
              lims[2] == 0.125 and lims[3] == 8 and lims[0]["sx"] == 8 and lims[0]["sy"] == 0.125 and lims[0]["dy"] == 1.35 and abs(lims[0]["dx"]) <= 360 * 8 / 2
              and lims[1]["sx"] == 0.125 and lims[1]["sy"] == 8 and lims[1]["dy"] == -1.35 and abs(lims[1]["dx"]) <= 360 * 0.125 / 2 + 1e-9, lims)

        group[0] = "J. tap the curve: stretch"
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        s = sel(pg); hx = s["hx"]; lev = hx[0] - d0["x0"]
        drag(hx, [-lev / 2, 0])
        d2 = gd(); c2 = d2["curves"][0]; g2 = geo(pg, gid)
        check("the right handle dragged halfway to the y-axis SQUASHES it: sx 0.5 (dx 0, dy 0, sy 1); the graph unchanged",
              abs(c2["sx"] - 0.5) < 0.01 and c2["dx"] == 0 and c2["dy"] == 0 and c2["sy"] == 1 and but(d2, "curves") == but(d0, "curves"), c2)
        P = cpts0(gid)
        near_ = lambda q: min(math.hypot(a[0] - q[0], a[1] - q[1]) for a in P)
        check("... more waves in the same axes: peaks at 45 and 225 degrees, troughs at 135 and 315",
              all(near_([XD(d0, u), YD(d0, v)]) < 0.6 for u, v in [(45, 1), (225, 1), (135, -1), (315, -1)]), [near_([XD(d0, u), YD(d0, v)]) for u, v in [(45, 1), (225, 1), (135, -1), (315, -1)]])
        check("... the marks stay put (90, 180, 270, 360 where they were)", g2["labels"] == g0["labels"] and g2["ticks"] == g0["ticks"])
        shot3("3-squashed.png", g0["box"])
        undo(pg)
        check("ONE undo: back", gd() == d0)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        hx = sel(pg)["hx"]; drag(hx, [lev / 2, 0]); c = gd()["curves"][0]
        check("dragged out instead: WIDER, each wave longer (sx 1.5)", abs(c["sx"] - 1.5) < 0.01, c)
        undo(pg)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        hx = sel(pg)["hx"]; drag(hx, [-(lev + 150), 0]); c = gd()["curves"][0]
        check("dragged past the y-axis: it stops at sx 1/8 (8 waves in 360 degrees), never squashed to nothing", c["sx"] == 0.125, c)
        undo(pg)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        s = sel(pg); hy = s["hy"]; levy = hy[1] - d0["y0"]
        drag(hy, [0, levy / 2]); d3 = gd(); c3 = d3["curves"][0]
        check("the bottom handle dragged down: TALLER (sy 1.5 about its middle line; dx 0, dy 0, sx 1); the graph unchanged",
              abs(c3["sy"] - 1.5) < 0.01 and c3["dx"] == 0 and c3["dy"] == 0 and c3["sx"] == 1 and but(d3, "curves") == but(d0, "curves"), c3)
        P = cpts0(gid)
        check("... cut at the window's top and bottom (1.35 up and down)", abs(min(q[1] for q in P) - YD(d0, 1.35)) < 0.05 and abs(max(q[1] for q in P) - YD(d0, -1.35)) < 0.05)
        shot3("4-taller.png", g0["box"])
        undo(pg)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        hy = sel(pg)["hy"]; drag(hy, [0, -(levy + 150)]); c = gd()["curves"][0]
        check("dragged up past its middle: it stops at sy 1/8 (shorter, never flat)", c["sy"] == 0.125, c)
        undo(pg)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(d0, 0, 90))
        tapp(sel(pg)["hx"])
        check("a tap on a handle changes nothing; the curve stays picked", gd() == d0 and sel(pg) and sel(pg)["curve"] == 0)

        group[0] = "J. tap the curve: two curves"
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        land(pg, "sin"); gid = graphs(pg)[0]["id"]
        pen_colour(PINK); pick(geo(pg, gid)["box"]); tap("cos")
        dd = gd(); gb = geo(pg, gid)["box"]
        check("set up: one graph, sin (Blue) and cos (pink)", [(k["kind"], k["colour"].lower()) for k in dd["curves"]] == [("sin", BLUE.lower()), ("cos", PINK.lower())], dd["curves"])
        clear_sel(pg); selt(); tapp(cpt(dd, 1, 180)); s = sel(pg)
        check("a tap on the cos picks the cos alone (curve 1)", s and s["curve"] == 1, s)
        drag(cpt(dd, 1, 180), [0.5 * dd["px"], 0]); dm = gd()
        check("a drag slides ONLY the cos (dx +45); the sin untouched", abs(dm["curves"][1]["dx"] - 45) < 0.05 and dm["curves"][0] == dd["curves"][0] and but(dm, "curves") == but(dd, "curves"), dm["curves"])
        shot3("7-two-curves-one-moved.png", gb)
        pg.click(f'#tray .sw[data-colour="{THIRD}"]'); pg.wait_for_timeout(60)
        cs = gd()["curves"]
        check("a colour tap with the cos picked recolours the COS; the sin stays Blue", cs[1]["colour"].lower() == THIRD.lower() and cs[0]["colour"] == BLUE, cs)
        undo(pg)
        if not (sel(pg) and sel(pg)["curve"] is not None): selt()
        tapp(cpt(dm, 0, 90)); s = sel(pg)
        check("a tap on the sin picks the sin (curve 0)", s and s["curve"] == 0, s)
        pg.click(f'#tray .sw[data-colour="{THIRD}"]'); pg.wait_for_timeout(60)
        cs = gd()["curves"]
        check("... a colour tap now recolours the SIN (the older curve); the cos stays pink", cs[0]["colour"].lower() == THIRD.lower() and cs[1]["colour"].lower() == PINK.lower(), cs)
        undo(pg)
        check("... one undo step", gd() == dm)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(dm, 0, 90))
        pg.click(".selChips .chip[data-act='delete']"); pg.wait_for_timeout(60)
        check("Delete with the sin picked removes the sin only; the graph stays with its (moved) cos, nothing picked",
              len(recs(pg)) == 1 and gd()["curves"] == [dm["curves"][1]] and but(gd(), "curves") == but(dm, "curves") and sel(pg) is None, gd()["curves"])
        dc = gd(); selt(); tapp(cpt(dc, 0, 225))
        pg.click(".selChips .chip[data-act='delete']"); pg.wait_for_timeout(60)
        check("Delete with the ONLY curve picked removes the whole graph (no bare axes left behind)", recs(pg) == [], recs(pg))
        undo(pg)
        check("undo: the graph with its cos is back", len(graphs(pg)) == 1 and gd() == dc)
        undo(pg)
        check("undo again: both curves are back", gd() == dm)

        group[0] = "J. tap the curve: every kind"
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        land(pg, "tan"); gid = graphs(pg)[0]["id"]; dt = gd(); gt = geo(pg, gid)
        selt(); tapp(cpt(dt, 0, 45))
        drag(cpt(dt, 0, 45), [-dt["px"] / 3, 0]); gt2 = geo(pg, gid); c = gd()["curves"][0]
        check("tan slid left 30 degrees: its dashed asymptotes went along (90, 270 -> 60, 240); the marks stayed",
              abs(c["dx"] + 30) < 0.05 and len(gt2["asym"]) == 2 and abs(gt2["asym"][0] - XD(dt, 60)) < 0.05 and abs(gt2["asym"][1] - XD(dt, 240)) < 0.05 and gt2["labels"] == gt["labels"], [c, gt2["asym"]])
        shot3("5-tan-slid.png", gt["box"])
        for k in KINDS + CUBICS:
            pg.evaluate("window.__T.clear('s0')"); clear_sel(pg)
            land(pg, k); d = gd(); gid = graphs(pg)[0]["id"]; cub_ = k in CUBICS; u = {"sin": 90, "cos": 180, "tan": 45, "cubic": -1}[k.lstrip("-")]
            selt(); tapp(cpt(d, 0, u)); s = sel(pg); ok_p = bool(s and s["ids"] == [gid] and s["curve"] == 0)
            drag(cpt(d, 0, u), [20, -10]); c = gd()["curves"][0]
            ex = 20 / d["px"] * (1 if cub_ else 90); ey = 10 / d["py"]
            ok_s = abs(c["dx"] - ex) < 0.02 and abs(c["dy"] - ey) < 0.002 and c["sx"] == 1 and c["sy"] == 1 and but(gd(), "curves") == but(d, "curves")
            zz = z(pg); s = sel(pg); hx, hy = s["hx"], s["hy"]
            drag(hx, [max(hx[0] - d["x0"], 40 / zz) * 0.5, 0]); c2 = gd()["curves"][0]
            ok_w = abs(c2["sx"] - 1.5) < 0.01 and abs(c2["dx"] - c["dx"] * c2["sx"]) < 0.02 and c2["dy"] == c["dy"]
            hy = sel(pg)["hy"]; drag(hy, [0, max(hy[1] - (d["y0"] - c2["dy"] * d["py"]), 40 / zz) * 0.5]); c3 = gd()["curves"][0]
            ok_t = abs(c3["sy"] - 1.5) < 0.01 and c3["dy"] == c2["dy"] and c3["sx"] == c2["sx"] and c3["dx"] == c2["dx"]
            undo(pg); undo(pg); undo(pg)
            check(f"{k}: a tap picks the curve; it slides (dx, dy), widens (sx 1.5 about the y-axis) and grows taller (sy 1.5); three undos put it back",
                  ok_p and ok_s and ok_w and ok_t and gd() == d, [ok_p, ok_s, ok_w, ok_t, c, c2, c3])
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg)
        land(pg, "cubic"); gid = graphs(pg)[0]["id"]; dcub = gd(); gcub = geo(pg, gid)
        selt(); tapp(cpt(dcub, 0, -1))
        drag(cpt(dcub, 0, -1), [0.4 * dcub["px"], -0.5 * dcub["py"]])
        hx = sel(pg)["hx"]; drag(hx, [(hx[0] - dcub["x0"]) * 0.3, 0]); c = gd()["curves"][0]
        check("a cubic slid up and right (dx 0.4, dy 0.5) then stretched wider (sx 1.3, its centre carried out from the y-axis to 0.52)",
              abs(c["sx"] - 1.3) < 0.01 and abs(c["dx"] - 0.52) < 0.02 and abs(c["dy"] - 0.5) < 0.003, c)
        check("... the cubic's axes did not move", geo(pg, gid)["lines"] == gcub["lines"] and geo(pg, gid)["labels"] == gcub["labels"])
        shot3("6-cubic-slid-stretched.png", gcub["box"])
        undo(pg); undo(pg)
        if not (sel(pg) and sel(pg)["curve"] == 0): selt(); tapp(cpt(dcub, 0, -1))
        drag(cpt(dcub, 0, -1), [5 * dcub["px"], 0]); c = gd()["curves"][0]
        check("a cubic dragged far right stops with its centre on the window's edge (dx 2.6)", c["dx"] == 2.6, c)
        undo(pg)

        group[0] = "J. tap the curve: thumb + PDF + share + reload"
        pg.evaluate("window.__T.clear('s0')"); clear_sel(pg); pen_colour(BLUE)
        show(pg, [W / 2, 300]); land(pg, "sin"); gid = graphs(pg)[0]["id"]; d = gd()
        selt(); tapp(cpt(d, 0, 90)); hx = sel(pg)["hx"]; drag(hx, [-(hx[0] - d["x0"]) / 2, 0])
        dsq = gd(); clear_sel(pg); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        check("set up: a squashed sine (sx 0.5)", abs(dsq["curves"][0]["sx"] - 0.5) < 0.01, dsq["curves"])
        same_d = pg.evaluate("""(i) => { const a = document.querySelector(`#stack .sheet[data-id='s0'] svg.ink [data-id='${i}'] path.curve`);
          const t = window.__pw.ink.thumbSvg('s0').querySelector(`[data-id='${i}'] path.curve`); return !!a && !!t && a.getAttribute('d') === t.getAttribute('d'); }""", gid)
        check("thumbSvg draws exactly the page's moved curve (the same path)", same_d)
        pg.click("#listBtn"); pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(300)
        thd = pg.evaluate("""(i) => { const a = document.querySelector(`#stack .sheet[data-id='s0'] svg.ink [data-id='${i}'] path.curve`);
          const t = document.querySelector(`#plThumbs .thumbP[data-index='1'] [data-id='${i}'] path.curve`); return !!t && a.getAttribute('d') === t.getAttribute('d'); }""", gid)
        check("the page list's thumb of page 1 draws the moved curve", thd)
        tb = rect(pg, "#plThumbs .thumbP[data-index='1']"); thumb_png = SH3 / "_thumb.png"
        pg.screenshot(path=str(thumb_png), clip={"x": tb["l"] - 6, "y": tb["t"] - 6, "width": tb["w"] + 12, "height": tb["h"] + 12})
        on_new = [XD(dsq, 45), YD(dsq, 1)]; on_old = [XD(dsq, 90), YD(dsq, 1)]
        doc = pdf_of(pg, "Unit3"); p0 = doc[0]
        pix = p0.get_pixmap(dpi=144); img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"); sk = pix.width / W
        check("the PDF shows the squashed sine: Blue at its new peak (45 degrees), nothing at the old one (90 degrees)",
              any_px(img, on_new[0] * sk, on_new[1] * sk, 2, bluish) and not any_px(img, on_old[0] * sk, on_old[1] * sk, 2, bluish))
        doc.close()
        th_img = Image.open(str(thumb_png)).convert("RGB")
        hh = 800; t2 = th_img.resize((round(th_img.width * hh / th_img.height), hh)); p2i = img.resize((round(img.width * hh / img.height), hh))
        comp = Image.new("RGB", (t2.width + p2i.width + 30, hh + 20), (210, 210, 210)); comp.paste(t2, (10, 10)); comp.paste(p2i, (t2.width + 20, 10))
        if comp.width > 900: comp = comp.resize((900, round(comp.height * 900 / comp.width)))
        comp.save(str(SH3 / "8-thumb-pdf.png")); thumb_png.unlink()
        pg.click("#plSelect"); pg.wait_for_timeout(40)
        pg.locator("#plThumbs .thumbP[data-index='1']").click(); pg.wait_for_timeout(40)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg")
        pg.evaluate("window.__shared = null")
        pg.click("#shareDlg button[data-share='images']"); pg.wait_for_selector("#shareReady", timeout=30000)
        pg.click("#shareDlg button[data-share='send']"); pg.wait_for_function("window.__shared", timeout=10000)
        png = pg.evaluate("""async () => { const f = window.__shared.files[0]; const u = new Uint8Array(await f.arrayBuffer()); let s = '';
          for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return [f.type, btoa(s)]; }""")
        si = Image.open(io.BytesIO(base64.b64decode(png[1]))).convert("RGB"); ss = si.width / W
        check("a shared picture shows it the same: Blue at the new peak, nothing at the old one",
              any_px(si, on_new[0] * ss, on_new[1] * ss, 2, bluish) and not any_px(si, on_old[0] * ss, on_old[1] * ss, 2, bluish))
        if pg.evaluate("window.__pw.tick()") is not None: pg.click("#plDone"); pg.wait_for_timeout(40)
        if not pg.locator("#pageList").is_hidden(): pg.click("#plClose"); pg.wait_for_timeout(40)
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(200)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        pg.reload(); ready(pg); open_note(pg); pg.evaluate(HELP)
        check("after a reload the squashed sine is back exactly", graphs(pg) and gd() == dsq)

        # ------------------------------------------------------------ G: Caveat from the app's own files
        group[0] = "G. Caveat offline"
        open_gcard(pg); pg.wait_for_timeout(300); close_panel(pg)
        fnt = pg.evaluate("""async () => { await document.fonts.load('500 18px Caveat'); const r = await fetch('./fonts/caveat-500.woff2'); const b = new Uint8Array(await r.arrayBuffer());
          const lic = await (await fetch('./fonts/OFL-Caveat.txt')).text();
          return [r.status, String.fromCharCode(...b.slice(0, 4)), b.length, document.fonts.check('500 18px Caveat'), lic.includes('SIL Open Font License')]; }""")
        check("fonts/caveat-500.woff2 is served by the app (a real woff2), the licence beside it, and the face loads as 'Caveat' 500", fnt[0] == 200 and fnt[1] == "wOF2" and fnt[2] > 10000 and fnt[3] and fnt[4], fnt)
        css = (ROOT / "css" / "app.css").read_text(encoding="utf-8"); swt = (ROOT / "sw.js").read_text(encoding="utf-8"); idx = (ROOT / "index.html").read_text(encoding="utf-8")
        check("app.css declares it with @font-face from ../fonts/caveat-500.woff2; index.html links no Caveat",
              "font-family: 'Caveat'" in css and "url('../fonts/caveat-500.woff2')" in css and "caveat" not in idx.lower())
        g_req = [u for u in reqs if "caveat" in u.lower() and ("googleapis" in u or "gstatic" in u)]
        own = [u for u in reqs if u.endswith("/fonts/caveat-500.woff2")]
        check("no request ever asked Google for Caveat; the app's own file was fetched", g_req == [] and own, [g_req, own[:2]])
        check("sw.js: CACHE pw-v9m, its version line, and graph.js, caveat-glyphs.js and the font in the shell",
              'const CACHE = "pw-v9m";' in swt and "   pw-v9m (19 Nov): " in swt and all(f in swt for f in ['"./js/graph.js"', '"./js/caveat-glyphs.js"', '"./fonts/caveat-500.woff2"']))
        check("no page errors", not errs, errs)
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
