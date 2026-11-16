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
        check("ONE family row, headed 'sin, cos, tan'", info["title"] == "Graph" and info["fams"] == ["sin, cos, tan"], info["fams"])
        check("six blocks: sin, −sin, cos, −cos, tan, −tan (the real minus), each a picture and its name, 80 px wide",
              [x[0] for x in info["blocks"]] == KINDS and [x[1] for x in info["blocks"]] == NAMES and all(x[2] and x[3] == 80 for x in info["blocks"]), info["blocks"])
        check("no Parabola, Hyperbola or Exponential row (no dead buttons)", not re.search("Parabola|Hyperbola|Exponential", info["text"]), info["text"])
        tb = pg.evaluate("[...document.querySelectorAll('#graphCard .gBlk')].map((b) => b.querySelectorAll('line[stroke-dasharray]').length)")
        check("the two tan blocks show their dashed asymptotes, the others none", tb == [0, 0, 0, 0, 2, 2], tb)
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
        check("sw.js: CACHE pw-v9k, its version line, and graph.js, caveat-glyphs.js and the font in the shell",
              'const CACHE = "pw-v9k";' in swt and "   pw-v9k (16 Nov): " in swt and all(f in swt for f in ['"./js/graph.js"', '"./js/caveat-glyphs.js"', '"./fonts/caveat-500.woff2"']))
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
