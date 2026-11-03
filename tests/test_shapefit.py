# PenWorks regular shapes checks (pw-v8h, her ask 2 Nov 16:54: "I want my specific shapes likes squares and triangles to
# come out as proper shapes, not just as straightened lines"). Headless Playwright (Python), the tests/test_u2b.py harness
# (fresh, draw, strokes, hold): every shape is drawn with the mouse on a local-mode page (?local=1, Supabase never touched),
# held still so it snaps, and its record is measured. js/ink.js classify -> fitTriangle, fitQuad, unhook.
#   equilateral: upright, upside down, turned 20 degrees, and one of her small ones (14 px): a PERFECT equilateral, sides
#     equal to 1 px, angles 60 to 1 degree; the first two upright to 1 degree, the third still at 20
#   right triangle 3-4-5: upright comes out exactly 90 with axis-true legs; turned 30 degrees, exactly 90, not axis-true;
#     never equilateral
#   tall isosceles 200 / 200 / 100: stays as drawn
#   square upright (u2b's rough_square: today's upright box, now a perfect square), square at 30 degrees (a perfect square
#     at 30), a 2:1 rectangle at 30 (a true rectangle), a parallelogram with 60 degree corners (as drawn)
#   the hook: a landing tick out and back at the start (12 px on a 160 px triangle, 3 px on a 14 px one) stays a triangle
#   one snapped equilateral: undo and redo, a select tap on its side, the page list thumb (thumbSvg) draws it
#   blunt corners (pw-v8h, her 3 Nov triangle: 12.8 / 3.7 / 10.4 / 13.3 px sides saved as a 4-corner rect): that very ring
#     and the same at 5 x are triangles, perfect equilaterals (destub); a 60 px square with a 17 px cut corner is a square;
#     a thin 12 x 48 bar keeps its 4 corners; a trapezium with a 40 px top on a 100 px base stays as drawn; a 16 px triangle
#     that ends 3.5 px short of its start closes and snaps (CLOSE_PX), a 60 px one that ends 10 px short stays ink
# Every check prints its measured numbers. Run: python tests/test_shapefit.py   Screenshot: _build/shots-shapes/shapefit.png
import sys, subprocess, time, pathlib, re, math
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8805
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-shapes"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))
    print(f"{'ok  ' if ok else 'FAIL'} [{group[0]}] {n}  {str(info)[:300]}")

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-11-02T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Shapes', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Snap', '2026-11-02T10:06:00Z')],
    pages: [P('p1', 'n1', 0), P('p2', 'n1', 1), P('p3', 'n1', 2)] }));
}"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def strokes(pg, pid): return pg.evaluate("(id) => window.__pw.ink.strokesOf(id)", pid)
def last(pg, pid): s = strokes(pg, pid); return s[-1] if s else None
def sel(pg): return pg.evaluate("() => window.__pw.ink.selection()")
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def open_note(pg, name):
    if pg.locator("#noteView").is_visible(): return
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def go_page(pg, i):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
    pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120)
    if pg.locator("#pageList").is_visible(): pg.click("#listBtn"); pg.wait_for_timeout(80)
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, pts, steps=3, hold=650):
    sx, sy = screen(pg, i, *pts[0])
    pg.mouse.move(sx, sy); pg.mouse.down()
    for x, y in pts[1:]:
        tx, ty = screen(pg, i, x, y); pg.mouse.move(tx, ty, steps=steps)
    if hold: pg.wait_for_timeout(hold)
    pg.mouse.up(); pg.wait_for_timeout(40)
def tap_page(pg, i, x, y):
    sx, sy = screen(pg, i, x, y); pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(40)
def U(pg): return pg.evaluate("window.__pw.S.hist[window.__pw.S.openNote] ? window.__pw.S.hist[window.__pw.S.openNote].u.length : 0")
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(30)
def redo(pg): pg.click("#redoBtn"); pg.wait_for_timeout(30)
def tool(pg, t): pg.click(f"#tool-{t}"); pg.wait_for_timeout(20)
def fresh(b):
    ctx = b.new_context(viewport={"width": 1280, "height": 1300})
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg)
    pg.evaluate(SEED_JS); pg.reload(); ready(pg)
    return ctx, pg, errs

# ---------------------------------------------------------------- strokes (page px) and measures
def wobble(k, amp): return amp * math.sin(k * 1.7) * math.cos(k * 0.6)
def ring(V, n=8, amp=1.8, close=(2, 1)):
    """a hand ring through the corners V (in order), n points a side, wobbled, ending a hair past the start"""
    pts = []
    for i in range(len(V)):
        (ax, ay), (bx, by) = V[i], V[(i + 1) % len(V)]
        for k in range(n): pts.append((ax + (bx - ax) * k / n + wobble(len(pts), amp), ay + (by - ay) * k / n + wobble(len(pts) + 1, amp)))
    pts.append((V[0][0] + close[0], V[0][1] + close[1])); return pts
def rot(p, c, deg):
    a = math.radians(deg); dx, dy = p[0] - c[0], p[1] - c[1]
    return (c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a))
def eq_corners(cx, cy, s, turn):                       # apex up at turn 0 (page y down), corners clockwise
    R = s / math.sqrt(3); return [(cx + R * math.cos(math.radians(-90 + turn + 120 * i)), cy + R * math.sin(math.radians(-90 + turn + 120 * i))) for i in range(3)]
def sides(P): return [math.dist(P[i], P[(i + 1) % len(P)]) for i in range(len(P))]
def angles(P):
    n = len(P); out = []
    for i in range(n):
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        ux, uy, vx, vy = a[0] - b[0], a[1] - b[1], c[0] - b[0], c[1] - b[1]
        out.append(math.degrees(abs(math.atan2(ux * vy - uy * vx, ux * vx + uy * vy))))
    return out
def dirdeg(a, b): return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
def mod(x, m): return (x % m + m) % m
def off(x, m):                                          # how far x (degrees) is from the nearest multiple of m
    r = mod(x, m); return min(r, m - r)
def centre(P): return (sum(q[0] for q in P) / len(P), sum(q[1] for q in P) / len(P))
def r1(L): return [round(x, 1) for x in L]
def tri_turn(P):                                        # how far a triangle is from upright: its most level side's tilt
    return min(off(dirdeg(P[i], P[(i + 1) % 3]), 180) for i in range(3))
def eq_turn(P):                                         # an equilateral's turn: the corner directions about the centre, modulo 120, from apex-up
    c = centre(P); th = [math.atan2(q[1] - c[1], q[0] - c[0]) for q in P]
    phi = math.degrees(math.atan2(sum(math.sin(3 * t) for t in th), sum(math.cos(3 * t) for t in th)) / 3)
    return mod(phi - 30 + 60, 120) - 60                 # 0 = apex up; the turn in -60 .. 60

def snap(pg, pts, pid="p1", i=1):
    draw(pg, i, pts); r = last(pg, pid)
    return r, (r["data"].get("points") if r and r["kind"] == "shape" else None)

def check_equilateral(name, r, P, want_turn, want_c, turn_tol=1.0, c_tol=4):
    ok = r and r["kind"] == "shape" and r["data"]["type"] == "triangle" and P and len(P) == 3
    check(f"{name}: a triangle with 3 points", ok, [r and r["kind"], r and r["data"]])
    if not ok: return
    s, a = sides(P), angles(P)
    check(f"{name}: a PERFECT equilateral, sides equal to 1 px, angles 60 to 1 degree", max(s) - min(s) <= 1 and all(abs(x - 60) <= 1 for x in a), ["sides", r1(s), "angles", r1(a)])
    t = eq_turn(P)
    check(f"{name}: turned {want_turn} degrees (to {turn_tol})", abs(t - want_turn) <= turn_tol, ["turn", round(t, 2)])
    c = centre(P)
    check(f"{name}: centred on the drawn triangle (to {c_tol} px)", math.dist(c, want_c) <= c_tol, ["centre", r1(c), "drawn", r1(want_c)])

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx, pg, errs = fresh(b)
        open_note(pg, "Snap")
        tool(pg, "pen")

        # ------------------------------------------------------------ equilateral
        group[0] = "equilateral"
        # lopsided on purpose: one corner pulled 10 px, the rest wobbled
        V = eq_corners(200, 200, 160, 0); V[1] = (V[1][0] + 8, V[1][1] + 6)
        r, P = snap(pg, ring(V))
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        check_equilateral("upright (apex up), drawn lopsided", r, P, 0, centre(V))
        if P: check("upright: one side level (to 1 degree)", tri_turn(P) <= 1, ["tilt", round(tri_turn(P), 2)])
        V = eq_corners(520, 200, 160, 180); V[2] = (V[2][0] - 7, V[2][1] + 5)
        r, P = snap(pg, ring(V))
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        check_equilateral("upside down (apex down), drawn lopsided", r, P, 60 if eq_turn(P or V) > 0 else -60, centre(V))
        if P: check("upside down: one side level (to 1 degree), the apex below", tri_turn(P) <= 1 and max(P, key=lambda q: q[1])[1] > centre(P)[1] + 50, ["tilt", round(tri_turn(P), 2), P])
        V = eq_corners(200, 470, 160, 20)
        r, P = snap(pg, ring(V))
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        check_equilateral("turned 20 degrees", r, P, 20, centre(V), turn_tol=2)
        if P: check("turned 20: NOT made upright (tilt about 20)", abs(tri_turn(P) - 20) <= 2, ["tilt", round(tri_turn(P), 2)])
        V = eq_corners(520, 470, 14, 0); V[0] = (V[0][0] + 1.2, V[0][1])          # one of hers: 14 px a side, apex 1.2 px off
        r, P = snap(pg, ring(V, n=5, amp=0.3, close=(0.3, 0.2)))
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        check_equilateral("her size (14 px a side)", r, P, 0, centre(V), turn_tol=1, c_tol=1.5)

        # ------------------------------------------------------------ right triangles
        group[0] = "right triangle"
        Pc, Qc, Rc = (100, 900), (260, 900), (106, 780)                            # legs 160 and 120, the corner 87 degrees
        r, P = snap(pg, ring([Pc, Qc, Rc]))
        print("   drawn sides", r1(sides([Pc, Qc, Rc])), "angles", r1(angles([Pc, Qc, Rc])))
        ok = r and r["data"]["type"] == "triangle" and P and len(P) == 3
        check("3-4-5 upright: a triangle with 3 points", ok, r and r["data"])
        if ok:
            a = angles(P); k = min(range(3), key=lambda j: abs(a[j] - 90)); C = P[k]; Q, R = P[(k + 1) % 3], P[(k - 1) % 3]
            check("3-4-5 upright: exactly 90 (to 0.5), never equilateral", abs(a[k] - 90) <= 0.5 and max(a) - min(a) > 30, ["angles", r1(a)])
            check("3-4-5 upright: the right-angle corner stays (to 4 px)", math.dist(C, Pc) <= 4, ["corner", C])
            check("3-4-5 upright: the legs are axis-true (one level, one upright, to 0.2 px)",
                  sorted([min(abs(Q[0] - C[0]), abs(Q[1] - C[1])), min(abs(R[0] - C[0]), abs(R[1] - C[1]))])[1] <= 0.2, P)
            check("3-4-5 upright: the legs keep their lengths (160 and 120, to 6 px)",
                  abs(max(math.dist(C, Q), math.dist(C, R)) - 160) <= 5 and abs(min(math.dist(C, Q), math.dist(C, R)) - 120) <= 6, [round(math.dist(C, Q), 1), round(math.dist(C, R), 1)])
        V = [rot(q, (400, 900), 30) for q in [(400, 900), (560, 900), (406, 780)]]
        r, P = snap(pg, ring(V))
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        ok = r and r["data"]["type"] == "triangle" and P and len(P) == 3
        check("3-4-5 turned 30: a triangle with 3 points", ok, r and r["data"])
        if ok:
            a = angles(P); k = min(range(3), key=lambda j: abs(a[j] - 90)); C = P[k]; Q, R = P[(k + 1) % 3], P[(k - 1) % 3]
            check("3-4-5 turned 30: exactly 90 (to 0.5)", abs(a[k] - 90) <= 0.5, ["angles", r1(a)])
            legs = [off(dirdeg(C, Q), 90), off(dirdeg(C, R), 90)]
            check("3-4-5 turned 30: NOT axis-true (the legs about 30 degrees off the axes)", all(x > 20 for x in legs), ["legs off axis", r1(legs)])

        # ------------------------------------------------------------ as drawn
        group[0] = "tall isosceles"
        V = [(650, 600), (700, 794), (600, 794)]                                   # 200 / 200 / 100: apex 29, base 75.5
        r, P = snap(pg, ring(V))
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        ok = r and r["data"]["type"] == "triangle" and P and len(P) == 3
        check("a tall isosceles: a triangle with 3 points", ok, r and r["data"])
        if ok:
            check("a tall isosceles stays as drawn (every corner within 5 px of the drawn one)", all(min(math.dist(q, v) for q in P) <= 5 for v in V),
                  ["sides", r1(sides(P)), "angles", r1(angles(P))])

        # ------------------------------------------------------------ four corners (page 2)
        group[0] = "four corners"
        go_page(pg, 2); tool(pg, "pen")
        x0, y0, s = 150, 380, 200                                                  # u2b's rough_square
        sq = []
        for (ax, ay), (bx, by) in [((x0, y0), (x0 + s, y0)), ((x0 + s, y0), (x0 + s, y0 + s)), ((x0 + s, y0 + s), (x0, y0 + s)), ((x0, y0 + s), (x0, y0))]:
            for k in range(8): sq.append((ax + (bx - ax) * k / 8 + wobble(len(sq), 2.2), ay + (by - ay) * k / 8 + wobble(len(sq) + 3, 2.2)))
        sq.append((x0 + 3, y0 + 2))
        r, P = snap(pg, sq, "p2", 2)
        ok = r and r["data"]["type"] == "rect" and P and len(P) == 4
        check("u2b's rough square: a rect with 4 points", ok, r and r["data"])
        if ok:
            s4 = sides(P)
            check("... axis-true (upright sides), near its corners (8 px)", P[0][1] == P[1][1] and P[1][0] == P[2][0] and P[2][1] == P[3][1] and P[3][0] == P[0][0]
                  and math.dist(P[0], (150, 380)) <= 8 and math.dist(P[2], (350, 580)) <= 8, P)
            check("... a perfect square (sides to 0.2 px)", max(s4) - min(s4) <= 0.2, ["sides", r1(s4)])
        c = (520, 300); V = [rot(q, c, 30) for q in [(450, 230), (592, 228), (590, 372), (450, 370)]]
        r, P = snap(pg, ring(V), "p2", 2)
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        ok = r and r["data"]["type"] == "rect" and P and len(P) == 4
        check("a square at 30 degrees: a rect with 4 points", ok, r and r["data"])
        if ok:
            s4, a4 = sides(P), angles(P); t = mod(dirdeg(P[0], P[1]), 90)
            check("... a PERFECT square: sides equal to 1 px, angles 90 to 1 degree", max(s4) - min(s4) <= 1 and all(abs(x - 90) <= 1 for x in a4), ["sides", r1(s4), "angles", r1(a4)])
            check("... at its own turn: 30 degrees (to 2)", abs(t - 30) <= 2, ["turn", round(t, 2)])
        c = (300, 800); V = [rot(q, c, 30) for q in [(180, 740), (420, 744), (418, 860), (182, 862)]]
        r, P = snap(pg, ring(V, n=10), "p2", 2)
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        ok = r and r["data"]["type"] == "rect" and P and len(P) == 4
        check("a 2:1 rectangle at 30 degrees: a rect with 4 points", ok, r and r["data"])
        if ok:
            s4, a4 = sides(P), angles(P); L_ = max(s4[0], s4[1]); t = mod(dirdeg(*((P[0], P[1]) if s4[0] >= s4[1] else (P[1], P[2]))), 180)
            check("... a TRUE rectangle: opposite sides equal to 1 px, angles 90 to 1 degree", abs(s4[0] - s4[2]) <= 1 and abs(s4[1] - s4[3]) <= 1 and all(abs(x - 90) <= 1 for x in a4),
                  ["sides", r1(s4), "angles", r1(a4)])
            check("... still 2:1 (to 0.1), the long side at 30 degrees (to 2)", abs(max(s4) / min(s4) - 2) <= 0.1 and abs(t - 30) <= 2, ["ratio", round(max(s4) / min(s4), 3), "turn", round(t, 2)])
        V = [(480, 600), (680, 600), (740, 704), (540, 704)]                      # a parallelogram: 200 and 120, corners 60 and 120
        r, P = snap(pg, ring(V, n=10), "p2", 2)
        print("   drawn sides", r1(sides(V)), "angles", r1(angles(V)))
        ok = r and r["data"]["type"] == "rect" and P and len(P) == 4
        check("a parallelogram (60 degree corners): a rect record with 4 points", ok, r and r["data"])
        if ok:
            a4 = angles(P)
            check("... stays as drawn: its corners near 60 and 120 (to 4 degrees), within 5 px of the drawn ones",
                  sorted(round(x) for x in a4)[0] >= 56 and sorted(a4)[0] <= 64 and all(min(math.dist(q, v) for q in P) <= 5 for v in V), ["angles", r1(a4)])

        # ------------------------------------------------------------ the hook (page 3)
        group[0] = "hook"
        go_page(pg, 3); tool(pg, "pen")
        V = eq_corners(250, 300, 160, 0); A = V[0]; d = (math.cos(math.radians(200)), math.sin(math.radians(200)))
        tick = [A, (A[0] + d[0] * 6, A[1] + d[1] * 6), (A[0] + d[0] * 12, A[1] + d[1] * 12), (A[0] + d[0] * 6, A[1] + d[1] * 6)]
        r, P = snap(pg, tick + ring(V)[1:], "p3", 3)
        check("a 160 px triangle with a 12 px landing tick (out and back) at the start: a triangle with 3 points", r and r["data"]["type"] == "triangle" and P and len(P) == 3,
              [r and r["kind"], r and r["data"]])
        if P and len(P) == 3:
            s = sides(P); check("... a perfect equilateral (sides to 1 px)", max(s) - min(s) <= 1, ["sides", r1(s), "angles", r1(angles(P))])
        V = eq_corners(550, 300, 14, 0); A = V[0]; d = (math.cos(math.radians(250)), math.sin(math.radians(250)))
        tick = [A, (A[0] + d[0] * 1.5, A[1] + d[1] * 1.5), (A[0] + d[0] * 3, A[1] + d[1] * 3), (A[0] + d[0] * 1.5, A[1] + d[1] * 1.5)]
        r, P = snap(pg, tick + ring(V, n=5, amp=0.3, close=(0.3, 0.2))[1:], "p3", 3)
        check("her size (14 px) with a 3 px landing tick: a triangle with 3 points, not a 4-corner rect", r and r["data"]["type"] == "triangle" and P and len(P) == 3,
              [r and r["kind"], r and r["data"]])
        if P and len(P) == 3:
            s = sides(P); check("... a perfect equilateral (sides to 1 px)", max(s) - min(s) <= 1, ["sides", r1(s), "angles", r1(angles(P))])

        # ------------------------------------------------------------ one snapped equilateral: undo, select, thumb
        group[0] = "undo, select, thumb"
        n0, u0 = len(strokes(pg, "p3")), U(pg)
        V = eq_corners(250, 700, 160, 0)
        r, P = snap(pg, ring(V), "p3", 3)
        check("the equilateral snapped (one more record, one undo step)", r["data"]["type"] == "triangle" and len(strokes(pg, "p3")) == n0 + 1 and U(pg) == u0 + 1, [len(strokes(pg, "p3")), U(pg)])
        undo(pg)
        check("undo takes it away", len(strokes(pg, "p3")) == n0, len(strokes(pg, "p3")))
        redo(pg)
        r2 = last(pg, "p3")
        check("redo brings it back, the same perfect points", r2 and r2["id"] == r["id"] and r2["data"]["points"] == P, r2 and r2["data"])
        tool(pg, "select")
        tap_page(pg, 3, (P[0][0] + P[1][0]) / 2, (P[0][1] + P[1][1]) / 2)
        check("a select tap on its side selects it alone", (sel(pg) or {}).get("ids") == [r["id"]], sel(pg))
        th = pg.evaluate("""(id) => import('./js/ink.js').then(m => { const s = m.thumbSvg('p3'), g = s.querySelector(`[data-id="${id}"]`);
          return g ? [g.tagName, g.getAttribute('points')] : null; })""", r["id"])
        want = " ".join(f"{q[0]},{q[1]}" for q in P)
        check("the page list thumb (thumbSvg) draws it: a polygon through the same 3 points", th and th[0] == "polygon" and th[1] and
              [round(float(x), 1) for x in re.split(r"[ ,]+", th[1].strip())] == [round(float(x), 1) for x in re.split(r"[ ,]+", want)], [th, want])
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ blunt corners and the closing floor (pw-v8h, page 1)
        group[0] = "blunt corner"
        ctx, pg, errs = fresh(b)
        open_note(pg, "Snap"); tool(pg, "pen")
        HER = [(617.2, 376.6), (630, 377.4), (630.6, 373.7), (624.3, 365.4)]        # her 3 Nov 08:48 triangle's saved corners (a 3.7 px 4th side)
        def her_ring(k, dx, dy, n, amp, close):
            cx, cy = centre(HER); V = [(cx + (x - cx) * k + dx, cy + (y - cy) * k + dy) for x, y in HER]
            return V, ring(V, n=n, amp=amp, close=close)
        V, pts = her_ring(1, -400, -150, 4, 0.3, (0.4, 0.3))
        r, P = snap(pg, pts)
        check("her 3 Nov triangle (12.8 / 3.7 / 10.4 / 13.3 px sides, one blunt corner): a triangle with 3 points, not a 4-corner rect",
              r and r["data"]["type"] == "triangle" and P and len(P) == 3, [r and r["kind"], r and r["data"]])
        if P and len(P) == 3:
            sd, a = sides(P), angles(P)
            check("... a PERFECT equilateral (sides to 1 px, angles 60 to 1 degree)", max(sd) - min(sd) <= 1 and all(abs(x - 60) <= 1 for x in a), ["sides", r1(sd), "angles", r1(a)])
            check("... about 15 px a side, where she drew it (centre to 4 px)", 13 <= sd[0] <= 17 and math.dist(centre(P), centre(V)) <= 4, ["side", round(sd[0], 1), "centre", r1(centre(P)), "drawn", r1(centre(V))])
        V, pts = her_ring(5, -150, 0, 8, 1.2, (2, 1))
        r, P = snap(pg, pts)
        check("the same ring at 5 x (64 / 18 / 52 / 66 px sides, an 18 px blunt corner): a triangle with 3 points", r and r["data"]["type"] == "triangle" and P and len(P) == 3,
              [r and r["kind"], r and r["data"]])
        if P and len(P) == 3:
            sd, a = sides(P), angles(P)
            check("... a PERFECT equilateral, about 75 px a side", max(sd) - min(sd) <= 1 and all(abs(x - 60) <= 1 for x in a) and 68 <= sd[0] <= 82, ["sides", r1(sd), "angles", r1(a)])
        r, P = snap(pg, ring([(300, 450), (348, 450), (360, 462), (360, 510), (300, 510)], n=6, amp=1.0, close=(1.5, 1)))
        check("a 60 px square with one corner cut 12 px (a 17 px 5th side): a rect with 4 points", r and r["data"]["type"] == "rect" and P and len(P) == 4, [r and r["kind"], r and r["data"]])
        if P and len(P) == 4:
            sd = sides(P); check("... a perfect square, 60 to 2 px, axis-true", max(sd) - min(sd) <= 1 and 58 <= sd[0] <= 62 and all(off(dirdeg(P[i], P[(i + 1) % 4]), 90) <= 0.5 for i in range(4)), ["sides", r1(sd)])
        r, P = snap(pg, ring([(450, 450), (498, 450), (498, 462), (450, 462)], n=6, amp=0.6, close=(1, 0.5)))
        check("a thin 12 x 48 bar: a rect with 4 points (its short sides are not stubs)", r and r["data"]["type"] == "rect" and P and len(P) == 4, [r and r["kind"], r and r["data"]])
        if P and len(P) == 4:
            sd = sorted(sides(P)); check("... 12 x 48 to 2 px", abs(sd[0] - 12) <= 2 and abs(sd[-1] - 48) <= 2, ["sides", r1(sd)])
        r, P = snap(pg, ring([(300, 700), (400, 700), (370, 650), (330, 650)], n=8, amp=1.2, close=(1, 1)))
        check("a trapezium, 40 px top on a 100 px base: 4 points as drawn (the top is not a stub)", r and r["data"]["type"] == "rect" and P and len(P) == 4, [r and r["kind"], r and r["data"]])
        if P and len(P) == 4:
            sd = sorted(sides(P)); check("... its 40 px top kept (to 3 px), its 100 px base kept", abs(sd[0] - 40) <= 3 and abs(sd[-1] - 100) <= 3, ["sides", r1(sd)])
        # the closing floor: her other 3 Nov triangle ended 3.1 px short on a 19 px shape (10% is 1.9 px) and stayed ink
        V = eq_corners(560, 470, 16, 0); pts = ring(V, n=5, amp=0.3, close=(0, 0))[:-2]                       # the last drawn point 6.4 px short, then the end
        d = (V[0][0] - pts[-1][0], V[0][1] - pts[-1][1]); L = math.hypot(*d)
        pts.append((V[0][0] - d[0] / L * 3.5, V[0][1] - d[1] / L * 3.5))                 # the end 3.5 px short of the start
        r, P = snap(pg, pts)
        check("a 16 px triangle whose ring ends 3.5 px short of its start: closed (CLOSE_PX 4), a triangle with 3 points", r and r["kind"] == "shape" and r["data"]["type"] == "triangle" and P and len(P) == 3,
              [r and r["kind"], r and r["data"]])
        V = eq_corners(650, 650, 60, 0); pts = ring(V, n=8, amp=1.0, close=(0, 0))[:-2]                       # the last drawn point 15 px short, then the end
        d = (V[0][0] - pts[-1][0], V[0][1] - pts[-1][1]); L = math.hypot(*d)
        pts.append((V[0][0] - d[0] / L * 10, V[0][1] - d[1] / L * 10))                   # the end 10 px short on a 70 px size: open
        r, P = snap(pg, pts)
        check("a 60 px triangle whose ring ends 10 px short (over 10% of the size): not closed, stays pen ink", r and r["kind"] == "pen", [r and r["kind"], r and r["data"].get("type")])
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ the screenshot: equilateral, right triangle, square at 30
        group[0] = "screenshot"
        ctx, pg, errs = fresh(b)
        open_note(pg, "Snap"); tool(pg, "pen")
        V = eq_corners(170, 200, 170, 0); V[1] = (V[1][0] + 8, V[1][1] + 6)
        draw(pg, 1, ring(V))
        draw(pg, 1, ring([(330, 280), (500, 280), (336, 150)]))
        c = (650, 210); draw(pg, 1, ring([rot(q, c, 30) for q in [(580, 140), (722, 138), (720, 282), (580, 280)]]))
        kinds = [(x["kind"], x["data"].get("type")) for x in strokes(pg, "p1")]
        check("three snapped shapes on the page: triangle, triangle, rect", kinds == [("shape", "triangle"), ("shape", "triangle"), ("shape", "rect")], kinds)
        SHOTS.mkdir(parents=True, exist_ok=True)
        x0, y0 = screen(pg, 1, 40, 60); x1, y1 = screen(pg, 1, 780, 380)
        pg.mouse.move(5, 5)
        pg.screenshot(path=str(SHOTS / "shapefit.png"), clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
        check("screenshot saved", (SHOTS / "shapefit.png").exists(), str(SHOTS / "shapefit.png"))
        check("cache is pw-v8i", "pw-v8i" in pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())"), pg.evaluate("caches.keys()"))
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/ink.js", "./sw.js"])
        check("no em-dashes in ink.js or sw.js", chr(0x2014) not in srcs)
        check("no page errors", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g_, n, ok, info in res:
    if g_ not in groups: groups.append(g_)
print()
for g_, n, ok, info in res:
    if not ok: print(f"FAIL [{g_}] {n}  -> {str(info)[:600]}")
for g_ in groups:
    rs_ = [r for r in res if r[0] == g_]
    print(f"{g_}: {sum(r[2] for r in rs_)}/{len(rs_)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
