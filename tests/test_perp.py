# PenWorks U5g checks (pw-v8q): the PERPENDICULAR and PARALLEL snap with the paper marks (_build/U5G-PERP-SNAP-BRIEF.md).
# Run: python tests/test_perp.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800 (the tablet landscape size), the way
# tests/test_tools.py does. Pen gestures are PointerEvents (pointerType 'pen') fired on the desk, with a constant
# screen-minus-client gap (pw-v8m, as tests/test_axes.py). The PDF is read with PyMuPDF.
# What it proves: A. js/align.js alignDir: 88.5 degrees snaps to 90, 87.5 does not; 1.9 degrees parallel alongside snaps,
# 2.1 does not; a parallel 4 cm away does not; a far crossing does; the moving record itself and an arc are never
# targets. B. the Select tool dragging a line's or an arrow's end: 88 and 92 degrees land exactly 90 (the anchor holds,
# the end stays under the pen), 85 stays; an arrow's tip; a T from the other side; a crossing. C. parallel at 1.5
# degrees 2 cm away lands exactly parallel, 3.5 cm away nothing; two chevrons, no square. D. the square: side 9 / z at
# the crossing, in the ink quadrant, fades after the lift; never a record, never in the thumb or the PDF. E. the ruler's
# turn: perpendicular against a line it is stuck to, a stick point still wins, the 45 degree step unchanged. F. the
# protractor's turn, the same. I. held strokes: a held line lands perpendicular or parallel, a held triangle untouched.
# H. no page errors. Screenshots go to _build/shots-u5g/.
import sys, subprocess, time, pathlib, math, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8807
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-u5g"
CM = 96 / 2.54
BLUE = (0x2F / 255, 0x4B / 255, 0xB8 / 255)

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-05T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Tools', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
HELP = """async () => {
  window.__P = await import('./js/page.js');
  window.__TL = await import('./js/tools.js');
  window.__AL = await import('./js/align.js');
  const T = window.__T = {};
  T.z = () => window.__P.view().z;
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.client = (id, x, y) => { const r = T.sheet(id).getBoundingClientRect(), z = T.z(); return [r.left + x * z, r.top + y * z]; };
  T.ev = (type, id, kind, x, y, buttons) => document.getElementById('desk').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: kind,
    isPrimary: true, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0,
    buttons: buttons !== undefined ? buttons : type === 'pointerup' ? 0 : 1, clientX: x, clientY: y,
    screenX: x + 10, screenY: y + 80 }));   // pw-v8m: a constant screen-minus-client gap, as a real pen has
  T.R = () => window.__TL.rulerState();
  T.P = () => window.__TL.protractorState();
  T.local = (lx, ly) => { const s = T.R(), u = [Math.cos(s.ang), Math.sin(s.ang)], n = [-u[1], u[0]];
    return [s.o[0] + u[0] * lx + n[0] * ly, s.o[1] + u[1] * lx + n[1] * ly]; };
  T.pl = (lx, ly) => { const s = T.P(), u = [Math.cos(s.ang), Math.sin(s.ang)], up = [u[1], -u[0]];
    return [s.o[0] + u[0] * lx + up[0] * ly, s.o[1] + u[1] * lx + up[1] * ly]; };
  T.pen = (id, pts, up = true, pid = 31, kind = 'pen') => {
    const c = pts.map((p) => (id ? T.client(id, p[0], p[1]) : p));
    T.ev('pointerdown', pid, kind, c[0][0], c[0][1]);
    for (const q of c.slice(1)) T.ev('pointermove', pid, kind, q[0], q[1]);
    if (up) T.ev('pointerup', pid, kind, c[c.length - 1][0], c[c.length - 1][1]);
  };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.rec = (id, rid) => T.recs(id).find((r) => r.id === rid) || null;
  T.line = (id, x1, y1, x2, y2, type = 'line') => { const r = { id: crypto.randomUUID(), page_id: id, seq: Date.now() + Math.floor(Math.random() * 1000), kind: 'shape',
    style: { colour: '#FF0C84', width: 2.5, dash: 'solid', opacity: 1 }, data: { type, x1, y1, x2, y2 } };
    window.__pw.ink.put(id, [r]); return r.id; };
  T.clear = (id) => { const op = window.__pw.ink.erasePageOp(id); if (op) op.redo(); };
  T.marks = (sel) => [...document.querySelectorAll(sel)].map((g) => ({ fade: g.classList.contains('fade'), kind: g.dataset.kind,
    x: +g.dataset.x, y: +g.dataset.y, side: +g.dataset.side,
    paths: [...g.querySelectorAll('path')].map((p) => ({ cls: p.getAttribute('class'), d: p.getAttribute('d'), stroke: p.getAttribute('stroke'), w: +p.getAttribute('stroke-width'), fill: p.getAttribute('fill') })) }));
  T.rings = () => [...document.querySelectorAll('#stack svg.toolLayer circle.stickRing')].filter((c) => c.getAttribute('display') !== 'none')
    .map((c) => [+c.getAttribute('cx'), +c.getAttribute('cy')]);
  return 1;
}"""
INKMARK = "#stack .sheet[data-id='s0'] svg.ink g.alignMark"
TOOLMARK = "#stack svg.toolLayer g.alignMark"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def z(pg): return pg.evaluate("window.__T.z()")
def recs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.recs(id)", pid)
def rec(pg, rid, pid="s0"): return pg.evaluate("([p, i]) => window.__T.rec(p, i)", [pid, rid])
def line(pg, a, b, typ="line", pid="s0"): return pg.evaluate("([p, a, b, t]) => window.__T.line(p, a[0], a[1], b[0], b[1], t)", [pid, a, b, typ])
def clear(pg, pid="s0"): pg.evaluate("(id) => window.__T.clear(id)", pid)
def pen(pg, pts, up=True, page="s0", kind="pen"): pg.evaluate("([id, p, up, k]) => window.__T.pen(id, p, up, 31, k)", [page, pts, up, kind])
def pen_up(pg, p, page="s0"):
    pg.evaluate("([id, p]) => { const c = window.__T.client(id, p[0], p[1]); window.__T.ev('pointerup', 31, 'pen', c[0], c[1]); }", [page, p])
def pen_down(pg, p, page="s0"):
    pg.evaluate("([id, p]) => { const c = window.__T.client(id, p[0], p[1]); window.__T.ev('pointerdown', 31, 'pen', c[0], c[1]); }", [page, p])
def pen_move(pg, pts, page="s0"):
    pg.evaluate("([id, ps]) => { for (const p of ps) { const c = window.__T.client(id, p[0], p[1]); window.__T.ev('pointermove', 31, 'pen', c[0], c[1]); } }", [page, pts])
def marks(pg, sel): return pg.evaluate("(s) => window.__T.marks(s)", sel)
def live(pg, sel): return [m for m in marks(pg, sel) if not m["fade"]]
def R(pg): return pg.evaluate("window.__T.R()")
def P(pg): return pg.evaluate("window.__T.P()")
def local(pg, lx, ly): return pg.evaluate("([a, b]) => window.__T.local(a, b)", [lx, ly])
def pl(pg, lx, ly): return pg.evaluate("([a, b]) => window.__T.pl(a, b)", [lx, ly])
def addv(a, b): return [a[0] + b[0], a[1] + b[1]]
def subv(a, b): return [a[0] - b[0], a[1] - b[1]]
def mulv(a, k): return [a[0] * k, a[1] * k]
def dotv(a, b): return a[0] * b[0] + a[1] * b[1]
def crsv(a, b): return a[0] * b[1] - a[1] * b[0]
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def unit(a): l = math.hypot(*a) or 1; return [a[0] / l, a[1] / l]
def dirdeg(d): return [math.cos(math.radians(d)), math.sin(math.radians(d))]
def r1(v): return round(v * 10) / 10
def r1p(p): return [r1(p[0]), r1(p[1])]
def ends(r): d = r["data"]; return [d["x1"], d["y1"]], [d["x2"], d["y2"]]
def rdir(r): a, b = ends(r); return unit(subv(b, a))
def rotate(p, c, deg):
    a = math.radians(deg); dx, dy = p[0] - c[0], p[1] - c[1]
    return [c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a)]
def turn_path(c, k, deg, steps=None):
    steps = steps or max(2, int(abs(deg) / 2.5))
    return [rotate(k, c, deg * i / steps) for i in range(steps + 1)]
def open_panel(pg):
    if pg.locator("#toolsPanel").is_hidden(): pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
def toggle(pg, tool): open_panel(pg); pg.click(f"#trow-{tool}"); pg.wait_for_timeout(60)
def close_panel(pg): pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
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
def blue_count(doc):
    n = 0
    for dr in doc[0].get_drawings():
        c = dr.get("color")
        if c and all(abs(c[i] - BLUE[i]) < 0.02 for i in range(3)): n += 1
    return n
def wiggle(end, d):
    """a grab of a handle that is a real drag (past the 4 px tap rule, sideways) and comes back to 1 px on along the line
    (direction d), so the drag itself does not change the angle"""
    return [end, addv(end, mulv([-d[1], d[0]], 6)), addv(end, d)]

S_A, S_B = [200.0, 600.0], [200.0 + 6 * CM, 600.0]          # line S: horizontal, 6 cm
L4 = 4 * CM

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

        # ------------------------------------------------------------ A: the helper
        group[0] = "A. helper"
        A = pg.evaluate("""(CMv) => { const L = window.__AL, S = { a: [100, 500], b: [400, 500], id: 'S' }, out = {};
          const dir = (d) => [Math.cos(d * Math.PI / 180), -Math.sin(d * Math.PI / 180)];
          const run = (A, d, l, segs = [S], id) => { const u = dir(d), P = [A[0] + u[0] * l, A[1] + u[1] * l]; return L.alignDir(u, segs, { A, P, id }, 1, CMv); };
          out.p885 = run([250, 500], 88.5, 100); out.p875 = run([250, 500], 87.5, 100);
          out.q19 = run([150, 450], 1.9, 200); out.q21 = run([150, 450], 2.1, 200);
          out.far = run([150, 500 - 4 * CMv], 1, 200);
          out.cross = run([250, 700], 89, 400);
          out.self = run([250, 500], 90, 100, [S, { a: [250, 500], b: [250, 400], id: 'M' }].slice(1), 'M');
          const arc = { id: 'C', kind: 'shape', data: { type: 'arc', x1: 100, y1: 500, xm: 250, ym: 420, x2: 400, y2: 500 } };
          out.arcSegs = L.segsOf([arc], null).length; out.arc = run([250, 500], 89, 100, L.segsOf([arc], null));
          out.short = run([250, 500], 89, 100, [{ a: [240, 500], b: [250, 500], id: 'X' }]);
          return out; }""", CM)
        h = A["p885"]
        check("88.5 degrees meeting S snaps to 90 (kind perp, u2 straight up, the corner on S)",
              h and h["kind"] == "perp" and abs(h["u2"][0]) < 1e-12 and abs(h["u2"][1] + 1) < 1e-12 and abs(h["corner"][1] - 500) < 1e-9 and abs(h["corner"][0] - 250) < 1e-9, h)
        check("87.5 degrees does not snap", A["p875"] is None, A["p875"])
        check("1.9 degrees alongside (1.3 cm off, overlapping) snaps parallel, the sign nearest u", A["q19"] and A["q19"]["kind"] == "par" and A["q19"]["u2"] == [1, 0] and A["q19"]["corner"] is None, A["q19"])
        check("2.1 degrees does not", A["q21"] is None, A["q21"])
        check("a parallel 4 cm away does not", A["far"] is None, A["far"])
        check("a far crossing (both ends 200 px off S) snaps perpendicular", A["cross"] and A["cross"]["kind"] == "perp", A["cross"])
        check("the moving record itself is never a target", A["self"] is None, A["self"])
        check("an arc is never a target (segsOf skips it, nothing snaps)", A["arcSegs"] == 0 and A["arc"] is None, A)
        check("a segment under 0.5 cm is never a target", A["short"] is None, A["short"])

        # ------------------------------------------------------------ B: Select drag, a line's end
        group[0] = "B. select drag"
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        show(pg, [300, 560])
        zz = z(pg)
        def drag_case(deg, typ="line", start=None, length=L4, up=True, hook=None):
            """seed S and M (from start, at deg measured from S's +x, page y down), grab M's free end, wiggle, lift"""
            clear(pg); pg.wait_for_timeout(20)
            line(pg, S_A, S_B)
            a = start or [300.0, 600.0]
            e = r1p(addv(a, mulv(dirdeg(deg), length)))
            mid = line(pg, r1p(a), e, typ)
            if hook: hook()
            path = wiggle(e, dirdeg(deg))
            pen(pg, path, up=up)
            return mid, r1p(a), path[-1]
        def perp_ok(r, anchor, penp):
            d = rdir(r); a, e = ends(r)
            proj = addv(anchor, mulv(d, dotv(subv(penp, anchor), d)))
            return abs(dotv(d, [1, 0])) < 1e-3 and a == anchor and dist(e, proj) <= 1, [dotv(d, [1, 0]), a, e, proj]
        for deg in (-88, -92):
            mid, a0, p0 = drag_case(deg)
            ok, info = perp_ok(rec(pg, mid), a0, p0)
            check(f"from {abs(deg)} degrees: the drag lands exactly 90 to S (dot < 1e-3), the anchor unchanged, the end under the pen", ok, info)
        mid, a0, p0 = drag_case(-85)
        r = rec(pg, mid); d = rdir(r)
        check("from 85 degrees nothing snaps (the end lands at the pen, rounded)", abs(dotv(d, [1, 0]) - math.cos(math.radians(85))) < 0.01 and ends(r)[1] == r1p(p0), [dotv(d, [1, 0]), ends(r), p0])
        mid, a0, p0 = drag_case(-88, typ="arrow")
        ok, info = perp_ok(rec(pg, mid), a0, p0)
        check("an arrow's tip the same (still an arrow)", ok and rec(pg, mid)["data"]["type"] == "arrow", info)
        top = [300.0, 600.0 - L4]
        mid, a0, p0 = drag_case(88, start=top)                     # down at 88 degrees: the free end lands on S
        ok, info = perp_ok(rec(pg, mid), a0, p0)
        check("a T from the other side (M's free end landing on S) snaps too", ok, info)
        mid, a0, p0 = drag_case(-88, start=[300.0, 700.0], length=200)   # crosses S at y 600
        ok, info = perp_ok(rec(pg, mid), a0, p0)
        check("a crossing (neither end near S) snaps", ok, info)

        # ------------------------------------------------------------ C: Select drag, parallel
        group[0] = "C. parallel"
        pg.wait_for_timeout(700)                                    # B's last square has faded (a clean picture)
        mid, a0, p0 = drag_case(-1.5, start=[220.0, 600.0 - 2 * CM], up=False)
        lm = live(pg, INKMARK)
        check("during the drag: .alignMark holds 2 chevrons, no square", len(lm) == 1 and lm[0]["kind"] == "par"
              and [q["cls"] for q in lm[0]["paths"]] == ["alignTick", "alignTick"], lm)
        show(pg, [300, 560]); pg.screenshot(path=str(SHOTS / "par.png"))
        pen_up(pg, p0)
        r = rec(pg, mid); d = rdir(r)
        check("1.5 degrees, 2 cm away: lands exactly parallel (|dot| within 1e-3 of 1, sin under 1e-3), the anchor unchanged",
              abs(abs(dotv(d, [1, 0])) - 1) < 1e-3 and abs(crsv(d, [1, 0])) < 1e-3 and ends(r)[0] == a0, [d, ends(r)])
        mid, a0, p0 = drag_case(-1.5, start=[220.0, 600.0 - 3.5 * CM])
        r = rec(pg, mid); d = rdir(r)
        check("3.5 cm away nothing snaps (still 1.5 degrees)", abs(math.degrees(math.asin(abs(crsv(d, [1, 0])))) - 1.5) < 0.1 and ends(r)[1] == r1p(p0), [d, ends(r)])

        # ------------------------------------------------------------ D: the marks
        group[0] = "D. marks"
        pg.wait_for_timeout(700)
        clear(pg); line(pg, S_A, S_B)
        pre = {}
        def before():
            pre["n"] = len(recs(pg)); pre["nd"] = len(pdf_of(pg, "before")[0].get_drawings())
        mid, a0, p0 = drag_case(-88, up=False, hook=before)
        n0, nd0 = pre["n"] - 1, pre["nd"]
        n1 = len(recs(pg))
        lm = live(pg, INKMARK); zz = z(pg)
        sq = lm[0] if lm else None
        check("during a perpendicular drag: one mark, one square path, side 9 / z, the handle ring's blue, 1.5 / z wide, no fill",
              len(lm) == 1 and sq["kind"] == "perp" and [q["cls"] for q in sq["paths"]] == ["alignSq"] and abs(sq["side"] - 9 / zz) < 1e-6
              and sq["paths"][0]["stroke"] == "#2F4BB8" and abs(sq["paths"][0]["w"] - 1.5 / zz) < 0.01 and sq["paths"][0]["fill"] == "none", lm)
        if sq:
            import re as _re
            nums = [float(v) for v in _re.findall(r"-?\d+(?:\.\d+)?", sq["paths"][0]["d"])]
            pts = [nums[i:i + 2] for i in range(0, 8, 2)]
            check("the square's corner is the crossing of the two lines (300, 600) within 0.5 px", dist(pts[0], [300, 600]) < 0.5 and dist([sq["x"], sq["y"]], [300, 600]) < 0.5, pts)
            far = pts[2]
            check("... and it sits in the ink quadrant: up along M, right along S's longer part", far[0] > 300 + 9 / zz - 0.5 and far[1] < 600 - 9 / zz + 0.5
                  and abs(dist(pts[0], pts[1]) - 9 / zz) < 0.01 and abs(dist(pts[0], pts[3]) - 9 / zz) < 0.01, pts)
        th = pg.evaluate("() => window.__pw.ink.thumbSvg('s0').outerHTML")
        pdf1 = pdf_of(pg, "during")
        check("while it shows: the record count as before, the thumb has no mark", n1 == n0 + 1 and "alignMark" not in th and "alignSq" not in th, [n0, n1])
        check("... and the PDF neither (same drawings as before the drag, nothing in the mark's blue)",
              len(pdf1[0].get_drawings()) == nd0 and blue_count(pdf1) == 0, [nd0, len(pdf1[0].get_drawings()), blue_count(pdf1)])
        show(pg, [300, 560]); pg.screenshot(path=str(SHOTS / "perp.png"))
        pen_up(pg, p0)
        after = marks(pg, INKMARK)
        check("on the lift the mark starts fading (class fade)", len(after) == 1 and after[0]["fade"], after)
        pg.wait_for_timeout(750)
        check("... and after 600 ms it is gone", len(marks(pg, INKMARK)) == 0, marks(pg, INKMARK))
        check("the lift wrote one record for M (one undo step), no mark record", len(recs(pg)) == n1 and all(r["kind"] == "shape" for r in recs(pg)), len(recs(pg)))
        pg.click("#undoBtn"); pg.wait_for_timeout(60)
        r = rec(pg, mid)
        check("undo puts M back at 88 degrees (one step)", r and abs(dotv(rdir(r), [1, 0]) - math.cos(math.radians(88))) < 0.01, r)
        mid, a0, p0 = drag_case(-88, up=False)
        pen_move(pg, [addv(a0, mulv(dirdeg(-80), L4))])             # the hit lets go mid-gesture
        lm = live(pg, INKMARK)
        check("leaving the 2 degree band mid-drag lets go at once: no live mark", len(lm) == 0, marks(pg, INKMARK))
        pen_up(pg, addv(a0, mulv(dirdeg(-80), L4)))
        pg.wait_for_timeout(700)

        # ------------------------------------------------------------ E: the ruler's turn
        group[0] = "E. ruler turn"
        pg.click("#tool-pen"); pg.wait_for_timeout(40)
        clear(pg)
        piv = [400.0, 700.0]
        sdir = dirdeg(120); s_end = addv(piv, mulv(sdir, 6 * CM))
        line(pg, piv, s_end)                                        # S: from the pivot down-left at 120 degrees (screen)
        toggle(pg, "ruler"); close_panel(pg)
        show(pg, [400, 600])
        bp = local(pg, R(pg)["len"] / 2, R(pg)["w"] / 2); delta = subv([400, 697], local(pg, R(pg)["len"] / 2, 0))
        pen(pg, [bp, addv(bp, mulv(delta, 0.5)), addv(bp, delta)])
        rr = R(pg)
        check("the ruler's edge A sticks to S's end (the pivot)", rr["stuck"] is not None and dist(rr["stuck"]["p"], piv) < 1e-6, rr)
        k1 = local(pg, rr["len"] + rr["pad"] + rr["knobOff"], rr["w"] / 2)
        path = turn_path(piv, k1, 28.5)
        pen(pg, path, up=False)
        rr = R(pg); u = [math.cos(rr["ang"]), math.sin(rr["ang"])]
        check("turned to 88.5 degrees against S: the edge makes exactly 90 with S", rr["gesture"] == "turn" and abs(dotv(u, sdir)) < 1e-9 and rr["align"] and rr["align"]["kind"] == "perp",
              [math.degrees(rr["ang"]), dotv(u, sdir), rr["align"]])
        tm = live(pg, TOOLMARK)
        check("... and the tool layer shows the square at the pivot (side 9 / z)", len(tm) == 1 and tm[0]["kind"] == "perp" and dist([tm[0]["x"], tm[0]["y"]], piv) < 0.5
              and abs(tm[0]["side"] - 9 / z(pg)) < 1e-6, tm)
        check("... the degree pill keeps the plain degrees (no other text)", pg.evaluate("[...document.querySelectorAll('#stack .selDeg.on, #stack .on')].map((e) => e.textContent).filter((t) => t.includes('°'))") in (["30°"], ["150°"]),
              pg.evaluate("[...document.querySelectorAll('#stack .on')].map((e) => e.textContent)"))
        show(pg, [400, 600]); pg.screenshot(path=str(SHOTS / "ruler-perp.png"))
        pen_up(pg, path[-1])
        tm = marks(pg, TOOLMARK)
        check("the turn ends: the mark fades", len(tm) == 1 and tm[0]["fade"], tm)
        pg.wait_for_timeout(750)
        check("... and goes", len(marks(pg, TOOLMARK)) == 0, marks(pg, TOOLMARK))
        # order: a stick point 1 degree off the perpendicular still wins
        pen(pg, turn_path(piv, local(pg, rr["len"] + rr["pad"] + rr["knobOff"], rr["w"] / 2), -28.5))
        q = addv(piv, mulv(dirdeg(29), 6 * CM)); line(pg, q, addv(q, mulv(dirdeg(29), 2 * CM)))
        rr = R(pg)
        pen(pg, turn_path(piv, local(pg, rr["len"] + rr["pad"] + rr["knobOff"], rr["w"] / 2), 28.5), up=False)
        rr = R(pg)
        check("a stick point at 29 degrees still wins over the perpendicular at 30 (order kept)", abs(math.degrees(rr["ang"]) - 29) < 1e-6 and rr["align"] is None, math.degrees(rr["ang"]))
        pen_up(pg, local(pg, rr["len"] + rr["pad"] + rr["knobOff"], rr["w"] / 2))
        # the brief's 44 against a 45 degree point pull
        rr = R(pg)
        q45 = addv(piv, mulv(dirdeg(45), 6 * CM)); line(pg, q45, addv(q45, [0, 3]))
        pen(pg, turn_path(piv, local(pg, rr["len"] + rr["pad"] + rr["knobOff"], rr["w"] / 2), 44 - math.degrees(rr["ang"])), up=False)
        rr = R(pg); rg = pg.evaluate("window.__T.rings()")
        check("turned to 44 against a 45 degree stick point pull: 45, the ring on the point", abs(math.degrees(rr["ang"]) - 45) < 1e-6 and any(dist(x, q45) < 0.01 for x in rg), [math.degrees(rr["ang"]), rg])
        pen_up(pg, local(pg, rr["len"] + rr["pad"] + rr["knobOff"], rr["w"] / 2))
        clear(pg); pg.wait_for_timeout(40)
        rr = R(pg); ctr = local(pg, rr["len"] / 2, rr["w"] / 2)
        pen(pg, turn_path(ctr, local(pg, rr["len"] + rr["pad"] + rr["knobOff"], rr["w"] / 2), 89 - math.degrees(rr["ang"])))
        rr = R(pg)
        check("no lines on the page: the 45 degree step still snaps (89 lands on 90)", rr["stuck"] is None and abs(math.degrees(rr["ang"]) - 90) < 1e-9, math.degrees(rr["ang"]))
        toggle(pg, "ruler"); close_panel(pg)

        # ------------------------------------------------------------ F: the protractor's turn
        group[0] = "F. protractor turn"
        clear(pg)
        toggle(pg, "protractor"); close_panel(pg)
        c = P(pg)["o"]
        line(pg, c, addv(c, mulv(sdir, 6 * CM)))                    # S: from the centre down-left at 120 degrees
        show(pg, c)
        pp = P(pg); tp = pl(pg, pp["r"] * 0.85, pp["r"] * 0.1)
        path = turn_path(c, tp, 28.5)
        pen(pg, path, up=False)
        pp = P(pg); u = [math.cos(pp["ang"]), math.sin(pp["ang"])]
        check("turned to 88.5 against S: the baseline makes exactly 90 with S", pp["gesture"] == "pTurn" and abs(dotv(u, sdir)) < 1e-9 and pp["align"]["kind"] == "perp", [math.degrees(pp["ang"]), pp["align"]])
        tm = live(pg, TOOLMARK)
        check("... the square on the protractor's layer at the centre", len(tm) == 1 and tm[0]["kind"] == "perp" and dist([tm[0]["x"], tm[0]["y"]], c) < 0.5, tm)
        pen_up(pg, path[-1]); pg.wait_for_timeout(750)
        check("... gone after the turn and its fade", len(marks(pg, TOOLMARK)) == 0, marks(pg, TOOLMARK))
        toggle(pg, "protractor"); close_panel(pg)

        # ------------------------------------------------------------ I: held strokes
        group[0] = "I. held strokes"
        def held(pts, page="s0"):
            pen_down(pg, pts[0], page); pen_move(pg, pts[1:], page); pg.wait_for_timeout(520)
            a = pg.evaluate("window.__pw.ink.alignNow()")
            m = marks(pg, INKMARK) if page == "s0" else []   # shown, already on its way out (it shows for the fade time)
            pen_up(pg, pts[-1], page); pg.wait_for_timeout(60)
            return a, m
        def stroke(a, deg, length, n=60): return [addv(a, mulv(dirdeg(deg), length * i / n)) for i in range(n + 1)]
        # the record the held stroke landed: by id, never recs[-1] (T.line seeds with seq = now + a random 0..999 ms, so
        # the seeded line may sort AFTER a stroke that lands within the next second)
        def newest(before, page="s0"):
            new = [r for r in recs(pg, page) if r["id"] not in before]
            return new[-1] if new else None
        ids = lambda page="s0": {r["id"] for r in recs(pg, page)}
        clear(pg); line(pg, S_A, S_B); show(pg, [300, 560])
        b0 = ids()
        al, mk = held(stroke([300, 600], -88, L4))
        r = newest(b0)
        ok = r and r["data"]["type"] == "line"
        check("a held stroke from S up at 88 lands a line exactly 90 to S (dot < 1e-3)", ok and abs(dotv(rdir(r), [1, 0])) < 1e-3, r)
        check("... its anchor end within 1 px of where the stroke began", ok and dist(ends(r)[0], [300, 600]) <= 1, r and ends(r))
        check("... the square showed while it held", al and al["kind"] == "perp" and len(mk) == 1 and mk[0]["kind"] == "perp", [al, mk])
        pg.wait_for_timeout(700)
        check("... and faded away", len(marks(pg, INKMARK)) == 0, marks(pg, INKMARK))
        b0 = ids()
        al, mk = held(stroke([250, 600], -85, L4))
        r = newest(b0) or {"data": {}}
        check("at 85 the held line keeps its own angle", r["data"].get("type") == "line" and abs(dotv(rdir(r), [1, 0]) - math.cos(math.radians(85))) < 0.01 and al is None, [r, al])
        clear(pg); line(pg, S_A, S_B)
        b0 = ids()
        al, mk = held(stroke([220, 600 - 1.5 * CM], -1.5, L4))
        r = newest(b0) or {"data": {}}
        check("a held stroke alongside S at 1.5 degrees lands exactly parallel", r["data"].get("type") == "line" and abs(crsv(rdir(r), [1, 0])) < 1e-3 and al and al["kind"] == "par", [r, al])
        tri = [[260, 585], [300, 585], [340, 585], [320, 551], [300, 517], [280, 551], [260, 585]]
        def tri_path(t):
            out = []
            for i in range(len(t) - 1):
                for k in range(10): out.append([t[i][0] + (t[i + 1][0] - t[i][0]) * k / 10, t[i][1] + (t[i + 1][1] - t[i][1]) * k / 10])
            out.append(t[-1]); return out
        b1 = ids("s1"); held(tri_path(tri), page="s1"); ctl = newest(b1, "s1") or {"data": {}}
        pg.wait_for_timeout(700)
        b0 = ids(); held(tri_path(tri)); got = newest(b0) or {"data": {}}
        check("a held triangle next to S is untouched (the same shape as on an empty page)", got["data"]["type"] == ctl["data"]["type"] == "triangle"
              and got["data"] == ctl["data"], [got["data"], ctl["data"]])

        group[0] = "H. page errors"
        check("no page errors", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:600]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
