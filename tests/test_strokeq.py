# PenWorks round 7 checks: short held lines snap straight, and pen strokes stop looking washy (her 29 Oct 15:17).
# Run: python tests/test_strokeq.py        (local mode only: ?local=1, Supabase is never touched)
# Two passes over the same feeds, each in its own browser context at zoom 2 (she writes zoomed in about 2x):
#   BEFORE: js/ink.js as it was at BEFORE_REF (pw-v7h, the fixed SMOOTH pull), served in place of the file on disk
#           (git show; the service worker is blocked so the swap really reaches the page);
#   AFTER:  js/ink.js on disk (the One Euro filter, the end hook dropped, RDP at 0.25 page px).
# Feeds are synthetic pen PointerEvents on the desk with their own timeStamp (240 Hz), so the filter sees real timing.
# Part A: her seven short held lines (tests/fixtures/her-short-lines-29oct.json, stayed_pen) replayed as pen events and held
#   still: all snap to a line AFTER; the three arrow fixtures classify exactly as BEFORE; a 6 px scribble and a 6 px line
#   do not snap; HOLD_MS is 350.
# Part B: her two letters (handwriting_12_45) and the seven lines, each resampled at 240 Hz along the fixture path at
#   30 page px/s with Gaussian noise of 0.3 page px per sample (fixed seeds 1 to 3, the same in both passes).
#   wobble = (sum of absolute turning angles along the stored points) / (path length), in radians per page px.
#   AFTER must be lower than BEFORE for every feed, every stored point within 0.6 page px of the clean fixture path, and
#   (letters) every point of the clean path within 0.6 page px of the stored polyline (the letter's turn is reached).
#   A fast stroke (600 page px/s) does not lag: its stored end within 1 page px of the lift point, and (AFTER) the
#   filter's own point at the lift within 1 page px of the pen (lastStroke().lag).
# Pictures: _build/out/strokeq-before.png and strokeq-after.png, the seed 1 feeds at 4x side by side: top row the pen as
#   drawn (2.5 page px wide), bottom row the centre line (thin black) over the clean fixture path (thin red).
import sys, subprocess, time, pathlib, math, json, random
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8813
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
BEFORE_REF = "b1c27ea"          # pw-v7h, the last commit before round 7
OUT = ROOT / "_build" / "out"
FX = json.load(open(ROOT / "tests" / "fixtures" / "her-short-lines-29oct.json", encoding="utf-8"))
SEEDS = (1, 2, 3)
ZOOM = 2.0

res = []
group = ["?"]
info = []
def check(n, ok, detail=""):
    res.append((group[0], n, bool(ok), detail))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-29T10:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Strokes', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Quality', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [{ id: 's1', note_id: 'n1', position: 0, orientation: 'portrait', background: 'plain', deleted_at: null, created_at: t, updated_at: t }] }));
}"""
# ctrl + wheel on the desk at the screen point of page point p, so the zoom lands on z exactly (page.js: f = exp(-dy * 0.0025))
ZOOM_JS = """([p, want]) => {
  const desk = document.getElementById('desk'), sheet = document.querySelector('#stack .sheet[data-index="1"]');
  const r = sheet.getBoundingClientRect(), z = +document.getElementById('stack').dataset.zoom;
  const dy = -Math.log(want / z) / 0.0025;
  desk.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: dy, clientX: r.left + p[0] * z, clientY: r.top + p[1] * z, bubbles: true, cancelable: true }));
}"""
# pen down at pts[0], then a move per point; each event carries its own timeStamp (base + t seconds). No lift here.
FEED = """([pts]) => {
  const desk = document.getElementById('desk'), sheet = document.querySelector('#stack .sheet[data-index="1"]');
  const r = sheet.getBoundingClientRect(), z = +document.getElementById('stack').dataset.zoom, base = performance.now();
  const ev = (type, q) => {
    const e = new PointerEvent(type, { pointerId: 93, pointerType: 'pen', isPrimary: true, bubbles: true, cancelable: true,
      button: type === 'pointermove' ? -1 : 0, buttons: 1, pressure: 0.5, clientX: r.left + q[0] * z, clientY: r.top + q[1] * z });
    Object.defineProperty(e, 'timeStamp', { value: base + q[2] * 1000 });
    desk.dispatchEvent(e);
  };
  ev('pointerdown', pts[0]);
  for (let k = 1; k < pts.length; k++) ev('pointermove', pts[k]);
  window.__sqLast = [pts[pts.length - 1], base, r.left, r.top, z];
  return z;
}"""
UP = """() => {
  const [q, base, L, T, z] = window.__sqLast, desk = document.getElementById('desk');
  const e = new PointerEvent('pointerup', { pointerId: 93, pointerType: 'pen', isPrimary: true, bubbles: true, cancelable: true,
    button: 0, buttons: 0, pressure: 0, clientX: L + q[0] * z, clientY: T + q[1] * z });
  desk.dispatchEvent(e);
}"""
NEWEST = """() => { const s = window.__pw.ink.strokesOf('s1'); let r = s[0];
  for (const x of s) if (x.seq >= r.seq) r = x;
  const el = document.querySelector(`#stack .sheet[data-index="1"] svg.ink [data-id="${r.id}"]`);
  return { kind: r.kind, data: r.data, html: el ? el.outerHTML : null, last: window.__pw.ink.lastStroke() }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)

# ---------------------------------------------------------------- geometry
def segd2(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]; L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    qx, qy = a[0] + dx * t - p[0], a[1] + dy * t - p[1]
    return qx * qx + qy * qy
def pdist(p, poly):
    if len(poly) == 1: return math.dist(p, poly[0])
    return math.sqrt(min(segd2(p, poly[i - 1], poly[i]) for i in range(1, len(poly))))
def dense(poly, s=0.2):
    out = []
    for i in range(1, len(poly)):
        a, b = poly[i - 1], poly[i]; n = max(1, int(math.dist(a, b) / s))
        for k in range(n): out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    out.append(tuple(poly[-1])); return out
def turn(a, b, c):
    t = abs(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0])) % (2 * math.pi)
    return 2 * math.pi - t if t > math.pi else t
def wobble(pts):
    q = [pts[0]]
    for p in pts[1:]:
        if p != q[-1]: q.append(p)                     # a zero-length step has no direction
    L = sum(math.dist(q[i - 1], q[i]) for i in range(1, len(q)))
    T = sum(turn(q[i - 1], q[i], q[i + 1]) for i in range(1, len(q) - 1))
    return T / L if L else 0.0
def resample(P, speed, seed, noise=0.3, hz=240.0):
    """points along the polyline P every speed/hz page px, one per 1/hz s, each with Gaussian noise (not the first or
    the last: the pen lands and lifts on the path); [x, y, t]"""
    rnd = random.Random(seed); step = speed / hz
    cum = [0.0]
    for i in range(1, len(P)): cum.append(cum[-1] + math.dist(P[i - 1], P[i]))
    n = max(1, int(cum[-1] / step)); out = []; j = 0
    for k in range(n + 1):
        s = min(cum[-1], k * step)
        while j < len(P) - 2 and cum[j + 1] < s: j += 1
        seg = cum[j + 1] - cum[j]; t = 0 if seg == 0 else (s - cum[j]) / seg
        x = P[j][0] + (P[j + 1][0] - P[j][0]) * t; y = P[j][1] + (P[j + 1][1] - P[j][1]) * t
        if 0 < k < n: x += rnd.gauss(0, noise); y += rnd.gauss(0, noise)
        out.append([x, y, k / hz])
    out[-1] = [P[-1][0], P[-1][1], n / hz]
    return out
PLACE = (380, 380)              # every stroke is moved (by whole px, so the 0.1 px rounding is unchanged) to start its box here
def placed(P):
    dx, dy = PLACE[0] - math.floor(min(p[0] for p in P)), PLACE[1] - math.floor(min(p[1] for p in P))
    return [[p[0] + dx, p[1] + dy] for p in P], (dx, dy)

STROKES = [("letter", FX["handwriting_12_45"][0]["points"]), ("c", FX["handwriting_12_45"][1]["points"])] + \
          [(f"line {s['len']}", s["points"]) for s in FX["stayed_pen"]]

def git_ink():
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{BEFORE_REF}:js/ink.js"], capture_output=True, check=True).stdout

def run_pass(b, before):
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    if before:
        old = git_ink()
        pg.route("**/js/ink.js*", lambda route: route.fulfill(status=200, body=old, headers={"Content-Type": "text/javascript"}))
    pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(150)
    pg.click("#tool-pen")
    pg.evaluate(ZOOM_JS, [[400, 400], ZOOM]); pg.wait_for_timeout(200)
    z = float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
    out = {"z": z, "errs": errs, "feeds": {}, "partA": {}, "arrows": {}}
    out["hold"] = pg.evaluate("import('./js/ink.js').then(m => m.HOLD_MS)")

    def stroke(pts, hold=0):
        pg.evaluate(FEED, [pts])
        if hold: pg.wait_for_timeout(hold)
        pg.evaluate(UP); pg.wait_for_timeout(30)
        return pg.evaluate(NEWEST)

    # Part A: her short lines replayed as she drew them (her stored points, 1/240 s apart) and held still
    for name, P in STROKES[2:]:
        Q, _ = placed(P)
        r = stroke([[q[0], q[1], k / 240] for k, q in enumerate(Q)], hold=650)
        out["partA"][name] = {"kind": r["kind"], "type": r["data"].get("type"), "classify": r["last"]["classify"], "snapped": r["last"]["snapped"]}
    sc = [[0, 0], [6, 0], [0, 1], [6, 1], [0, 2]]                       # a 6 px scribble (path 25 px, box 6 px)
    r = stroke([[380 + q[0], 600 + q[1], k / 30] for k, q in enumerate(sc)], hold=650)
    out["partA"]["scribble 6 px"] = {"kind": r["kind"], "snapped": r["last"]["snapped"]}
    r = stroke([[380 + 0.5 * k, 620, k / 240] for k in range(13)], hold=650)   # a straight 6 px line
    out["partA"]["line 6 px"] = {"kind": r["kind"], "snapped": r["last"]["snapped"]}
    if not before:                                                      # the new hold: 400 ms is enough (HOLD_MS 350)
        Q, _ = placed(FX["stayed_pen"][0]["points"])
        r = stroke([[q[0], q[1], k / 240] for k, q in enumerate(Q)], hold=400)
        out["partA"]["held 400 ms"] = {"kind": r["kind"], "snapped": r["last"]["snapped"]}
    else: out["partA"]["held 400 ms"] = {}
    for nm in ("arrow-pen-fail", "arrow-pen-ok", "curved-arrow-pen"):
        pts = json.load(open(ROOT / "tests" / "fixtures" / f"{nm}.json", encoding="utf-8"))["points"]
        out["arrows"][nm] = pg.evaluate("(p) => import('./js/ink.js').then(m => m.classify(p))", pts)

    # Part B: the noisy slow feeds
    for name, P in STROKES:
        Q, off = placed(P)
        for seed in SEEDS:
            r = stroke(resample(Q, 30.0, seed))
            pts = r["data"]["points"] if r["kind"] != "shape" else None
            out["feeds"][(name, seed)] = {"kind": r["kind"], "pts": pts, "clean": Q, "html": r["html"], "lag": r["last"].get("lag")}
    # the fast stroke: 300 page px at 600 page px/s
    F = [[100.0, 700.0], [400.0, 690.0]]
    feed = resample(F, 600.0, 7)
    r = stroke(feed)
    out["fast"] = {"kind": r["kind"], "pts": r["data"].get("points"), "lift": feed[-1][:2], "lag": r["last"].get("lag")}
    # a tap stays one point (AFTER only checks it, BEFORE prints it)
    r = stroke([[500.0, 900.0, 0.0]])
    out["tap"] = r["data"].get("points")
    if not before:
        out["oe"] = pg.evaluate("import('./js/ink.js').then(m => m.OE)")
    ctx.close()
    return out

def picture(pg, data, path, title):
    """the seed 1 feeds side by side at 4x: top row as drawn, bottom row the centre line over the clean path"""
    S, pad = 4, 6
    cell = max(max(p[1] for p in P) - min(p[1] for p in P) for _, P in STROKES) + 2 * pad
    cells = []
    for i, (name, _) in enumerate(STROKES):
        f = data["feeds"][(name, 1)]
        cl = f["clean"]; x0, y0 = min(p[0] for p in cl) - pad, min(p[1] for p in cl) - pad
        w = max(p[0] for p in cl) - x0 + pad
        cells.append((name, f, cl, x0, y0, w))
    W = sum(c[5] for c in cells) + 8 * (len(cells) + 1)
    H = 2 * cell + 28
    g = []
    x = 8
    for name, f, cl, x0, y0, w in cells:
        html = (f["html"] or "")
        thin = html.replace('stroke-width="2.5"', 'stroke-width="0.3"')
        clean = '<path d="M' + ' L'.join(f"{p[0]} {p[1]}" for p in cl) + '" fill="none" stroke="#E53935" stroke-width="0.3" stroke-linejoin="round"/>'
        g.append(f'<g transform="translate({x - x0} {16 - y0})">{html}</g>')
        g.append(f'<g transform="translate({x - x0} {16 + cell - y0})">{clean}{thin}</g>')
        g.append(f'<text x="{x}" y="9" font-size="3.2" font-family="Arial" fill="#444">{name} (w {wobble(f["pts"]):.2f})</text>' if f["pts"] else "")
        x += w + 8
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * S}" height="{H * S}" viewBox="0 0 {W} {H}">'
           f'<rect width="100%" height="100%" fill="#FFFFFF"/><text x="8" y="{H - 4}" font-size="3.6" font-family="Arial" fill="#222">{title}</text>'
           + "".join(g) + '</svg>')
    pg.set_content(f'<html><body style="margin:0;background:#fff">{svg}</body></html>')
    pg.locator("svg").screenshot(path=str(path))

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        BEF = run_pass(b, True)
        AFT = run_pass(b, False)

        group[0] = "set-up"
        check(f"both passes at zoom {ZOOM}", abs(BEF["z"] - ZOOM) < 0.01 and abs(AFT["z"] - ZOOM) < 0.01, [BEF["z"], AFT["z"]])
        check("no page errors (either pass)", not BEF["errs"] and not AFT["errs"], BEF["errs"] + AFT["errs"])
        check("the BEFORE pass ran the old code (HOLD_MS 500)", BEF["hold"] == 500, BEF["hold"])

        group[0] = "Part A: short held lines"
        check("HOLD_MS default is 350", AFT["hold"] == 350, AFT["hold"])
        for name, _ in STROKES[2:]:
            a, o = AFT["partA"][name], BEF["partA"][name]
            info.append(f"{name}: before {o['kind']}/{o['classify']}, after {a['kind']}/{a.get('type')}")
            check(f"her {name} px line, held: snaps to a line", a["kind"] == "shape" and a["type"] == "line" and a["snapped"], [a, "before:", o])
        check("a 400 ms hold is enough now", AFT["partA"]["held 400 ms"].get("kind") == "shape", AFT["partA"]["held 400 ms"])
        check("a 6 px scribble, held: stays pen", AFT["partA"]["scribble 6 px"]["kind"] == "pen", AFT["partA"]["scribble 6 px"])
        check("a 6 px line, held: stays pen", AFT["partA"]["line 6 px"]["kind"] == "pen", AFT["partA"]["line 6 px"])
        for nm in AFT["arrows"]:
            info.append(f"{nm}: before {BEF['arrows'][nm] and BEF['arrows'][nm].get('type')}, after {AFT['arrows'][nm] and AFT['arrows'][nm].get('type')}")
            check(f"{nm} classifies exactly as before", AFT["arrows"][nm] == BEF["arrows"][nm], [BEF["arrows"][nm], AFT["arrows"][nm]])

        group[0] = "Part B: wobble"
        rows = []
        for name, _ in STROKES:
            for seed in SEEDS:
                o, a = BEF["feeds"][(name, seed)], AFT["feeds"][(name, seed)]
                ok = o["pts"] is not None and a["pts"] is not None
                if not ok:
                    check(f"{name} seed {seed}: stays freehand in both passes", False, [o["kind"], a["kind"]]); continue
                wo, wa = wobble(o["pts"]), wobble(a["pts"])
                cl = a["clean"]
                fw_o, fw_a = max(pdist(q, cl) for q in o["pts"]), max(pdist(q, cl) for q in a["pts"])
                rv_o, rv_a = max(pdist(q, o["pts"]) for q in dense(cl)), max(pdist(q, a["pts"]) for q in dense(cl))
                rows.append((name, seed, wo, wa, len(o["pts"]), len(a["pts"]), fw_o, fw_a, rv_o, rv_a))
                check(f"{name} seed {seed}: wobble lower after ({wo:.3f} -> {wa:.3f})", wa < wo, [wo, wa])
                check(f"{name} seed {seed}: every stored point within 0.6 page px of the clean path", fw_a <= 0.6, round(fw_a, 3))
                if not name.startswith("line"):
                    check(f"{name} seed {seed}: the clean path (its turn too) within 0.6 page px of the stored stroke", rv_a <= 0.6, round(rv_a, 3))
                st = a["pts"]
                hook = len(st) >= 3 and math.dist(st[-1], st[-2]) <= 1 and turn(st[-3], st[-2], st[-1]) > math.radians(120)
                check(f"{name} seed {seed}: no end hook in the stored points", not hook, st[-3:])
                check(f"{name} seed {seed}: the first stored point is where the pen landed", st[0] == [round(cl[0][0], 1), round(cl[0][1], 1)], [st[0], cl[0]])

        group[0] = "fast stroke and tap"
        fo, fa = BEF["fast"], AFT["fast"]
        de_o, de_a = math.dist(fo["pts"][-1], fo["lift"]), math.dist(fa["pts"][-1], fa["lift"])
        check(f"600 px/s: the stored end within 1 page px of the lift point ({de_a:.2f})", de_a <= 1, [fa["pts"][-1], fa["lift"]])
        check(f"600 px/s: the filter's own point at the lift within 1 page px of the pen (lag {fa['lag']})", fa["lag"] is not None and fa["lag"] <= 1, fa["lag"])
        FL = [[100, 700], [400, 690]]
        fdev_o, fdev_a = max(pdist(q, FL) for q in fo["pts"]), max(pdist(q, FL) for q in fa["pts"])
        info.append(f"fast 600 px/s: wobble before {wobble(fo['pts']):.3f} after {wobble(fa['pts']):.3f}; points {len(fo['pts'])}/{len(fa['pts'])}; "
                    f"worst stored point off the path before {fdev_o:.2f} after {fdev_a:.2f}")
        check("a tap is one point", AFT["tap"] == [[500, 900]], AFT["tap"])
        check("?oe= default pair is in OE", isinstance(AFT.get("oe"), dict), AFT.get("oe"))

        group[0] = "?oe= and ?dbg=1"
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL + "&oe=2.5,0.05&dbg=1"); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        oe = pg.evaluate("import('./js/ink.js').then(m => m.OE)")
        check("?oe=2.5,0.05 sets the filter's mincutoff and beta", bool(oe) and oe.get("mincutoff") == 2.5 and oe.get("beta") == 0.05, oe)
        pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(400)
        txt = pg.evaluate("document.getElementById('dbgView') && document.getElementById('dbgView').textContent")
        check("?dbg=1 shows the pair ('oe 2.5 0.05')", txt and "oe 2.5 0.05" in txt, txt)
        pg.goto(LOCAL + "&oe=nonsense"); ready(pg)
        oe2 = pg.evaluate("import('./js/ink.js').then(m => m.OE)")
        check("a broken ?oe= keeps the defaults", bool(oe2) and oe2 == AFT.get("oe"), [oe2, AFT.get("oe")])
        check("no page errors (oe, dbg)", not errs, errs)

        OUT.mkdir(parents=True, exist_ok=True)
        pg2 = ctx.new_page()
        picture(pg2, BEF, OUT / "strokeq-before.png", f"BEFORE ({BEFORE_REF}, SMOOTH 0.5), seed 1, 30 px/s, noise 0.3 px, zoom {ZOOM}, shown at 4x")
        picture(pg2, AFT, OUT / "strokeq-after.png", f"AFTER (One Euro {(AFT.get('oe') or {}).get('mincutoff')} / {(AFT.get('oe') or {}).get('beta')}, hook dropped, RDP 0.25), seed 1, shown at 4x")
        check("the two pictures were written", (OUT / "strokeq-before.png").exists() and (OUT / "strokeq-after.png").exists())
        ctx.close()
        b.close()
finally:
    srv.terminate()

print("wobble (rad per page px) and fit, BEFORE -> AFTER")
print(f"{'stroke':12s} seed  wobble before  after   pts b/a   stored->clean b/a   clean->stored b/a")
for name, seed, wo, wa, nb, na, fo_, fa_, ro, ra in rows:
    print(f"{name:12s} {seed:4d}  {wo:13.3f}  {wa:5.3f}   {nb:3d}/{na:<3d}   {fo_:6.2f} / {fa_:4.2f}       {ro:6.2f} / {ra:4.2f}")
print(f"fast 600 px/s: stored end to lift point before {de_o:.2f}, after {de_a:.2f}; filter lag at lift after {AFT['fast']['lag']}")
print(f"tap: before {BEF['tap']}, after {AFT['tap']}")
for l in info: print(l)
groups = []
for g, n, ok, detail in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(detail)[:300]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
