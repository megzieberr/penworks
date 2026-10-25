# PenWorks scroll checks: one move per frame, glide after a flick, pattern paper.
# Run: python tests/test_scroll.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 8 grid pages into the localStorage twin and drives a finger through CDP touch input,
# the S Pen through CDP mouse input with pointerType "pen", and a burst of moves through synthetic
# PointerEvents. The stack's place is read from its transform; an in-page frame recorder logs every frame.
import sys, subprocess, time, pathlib, re, io
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8776
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-25T10:00:00Z', pages = [];
  for (let k = 0; k < 8; k++) pages.push({ id: 'q' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Scroll', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Eight pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
# frame recorder: every frame, the stack's place and the counter text; a spy counts transform writes
REC = """() => {
  const st = document.getElementById('stack').style;
  window.__w = 0;
  Object.defineProperty(st, 'transform', { configurable: true, get() { return st.getPropertyValue('transform'); },
    set(v) { window.__w++; st.setProperty('transform', v); } });
  window.__f = []; window.__rec = false;
  const y = () => +/translate\\([^,]+, ([-\\d.]+)px/.exec(st.getPropertyValue('transform'))[1];
  const loop = (t) => { if (window.__rec) window.__f.push([t, y(), document.getElementById('counter').textContent]); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
}"""
Y = "() => +/translate\\([^,]+, ([-\\d.]+)px/.exec(document.getElementById('stack').style.transform)[1]"
def y(pg): return pg.evaluate(Y)
def rec_on(pg): pg.evaluate("window.__f = []; window.__rec = true; window.__w = 0")
def rec_off(pg): return pg.evaluate("window.__rec = false; window.__f")
def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)

def touch(cdp, kind, x=None, yy=None):
    pts = [] if kind == "touchEnd" else [{"x": x, "y": yy}]
    cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})
def drag(cdp, x, y0, dy, n, pause, lift=True):
    """one finger from (x, y0), n moves of dy each, `pause` seconds between moves"""
    touch(cdp, "touchStart", x, y0)
    for k in range(1, n + 1):
        if pause: time.sleep(pause)
        touch(cdp, "touchMove", x, y0 + dy * k)
    if lift: touch(cdp, "touchEnd")
def rest(pg, quiet=250, limit=6000):
    """wait until the stack has not moved for `quiet` ms; returns its place"""
    last, still, t0 = y(pg), 0, time.time()
    while time.time() - t0 < limit / 1000:
        pg.wait_for_timeout(50); now = y(pg)
        still = still + 50 if abs(now - last) < 0.01 else 0
        last = now
        if still >= quiet: break
    return last
def go_page(pg, i):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
    pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, has_touch=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED); pg.reload(); ready(pg)
        pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(200)
        pg.evaluate(REC)
        cdp = ctx.new_cdp_session(pg)
        ids = [f"q{k}" for k in range(8)]
        strokes = lambda: pg.evaluate("(ids) => ids.reduce((k, id) => k + window.__pw.ink.strokesOf(id).length, 0)", ids)

        # ------------------------------------------------------------ slow drag
        group[0] = "slow drag"
        y0 = y(pg)
        drag(cdp, 640, 600, -8, 10, 0.08)          # 80 px at about 0.1 px per ms
        pg.wait_for_timeout(60); y1 = y(pg); pg.wait_for_timeout(400); y2 = y(pg)
        check("a slow drag moves the stack by the finger distance (80 px)", abs((y0 - y1) - 80) < 1, [y0, y1])
        check("and stops dead on lift (no glide)", abs(y2 - y1) < 0.01, [y1, y2])

        # ------------------------------------------------------------ flick
        group[0] = "flick"
        pg.evaluate("window.scrollTo(0, 0)"); go_page(pg, 1); y0 = y(pg)
        rec_on(pg)
        drag(cdp, 640, 700, -40, 10, 0.004)       # 400 px fast
        pg.wait_for_timeout(30); y1 = y(pg)
        y_end = rest(pg); f = rec_off(pg)
        check("a fast flick keeps moving after the lift", y_end < y1 - 50, [y0, y1, y_end])
        moving = [r for r in f if r[1] < y1 - 1]
        check("and comes to rest further on (several frames of glide, slowing down)", len(moving) > 10, len(moving))
        steps = [f[k][1] - f[k + 1][1] for k in range(len(f) - 1) if f[k][1] < y1 - 1 and f[k + 1][1] < f[k][1]]
        check("the glide slows down (late steps smaller than early ones)", len(steps) > 6 and steps[-1] < steps[1], steps[:3] + steps[-3:])
        c0 = f[0][2]
        changed = [k for k, r in enumerate(f) if r[2] != c0]
        later_moves = changed and any(f[k][1] < f[changed[0]][1] - 0.5 for k in range(changed[0] + 1, len(f)))
        check("the page counter updates during the glide", bool(changed) and later_moves, [c0, f[changed[0]][2] if changed else None])

        # ------------------------------------------------------------ end of the stack
        group[0] = "end of stack"
        go_page(pg, 8)
        lo = pg.evaluate("""() => { const d = document.getElementById('desk'), s = document.getElementById('stack');
          return d.clientHeight - parseFloat(s.style.height) * +s.dataset.zoom - 24; }""")
        rec_on(pg)
        drag(cdp, 640, 700, -40, 6, 0.003)        # a hard flick towards the end (240 px of drag, the rest glides)
        pg.wait_for_timeout(30); y1 = y(pg)
        y_end = rest(pg); f = rec_off(pg)
        check("the flick glided on after the lift", y_end < y1 - 20, [y1, y_end])
        low = min(r[1] for r in f)
        check("a glide stops at the end of the stack", abs(y_end - lo) < 0.01, [y_end, lo])
        check("without going past the clamp, even for one frame", low >= lo - 0.01, [low, lo])

        # ------------------------------------------------------------ a touch during a glide
        group[0] = "touch stops"
        go_page(pg, 1)
        drag(cdp, 640, 700, -40, 10, 0.004)
        pg.wait_for_timeout(60); ya = y(pg); pg.wait_for_timeout(60); yb = y(pg)
        touch(cdp, "touchStart", 640, 500); pg.wait_for_timeout(30); y_hold = y(pg)
        pg.wait_for_timeout(300); y_hold2 = y(pg)
        check("the glide was still going when the finger landed", yb < ya - 1, [ya, yb])
        check("a finger landing during a glide holds the stack where it is", abs(y_hold2 - y_hold) < 0.01, [y_hold, y_hold2])
        for k in range(1, 6):
            time.sleep(0.08); touch(cdp, "touchMove", 640, 500 - 10 * k)
        touch(cdp, "touchEnd"); pg.wait_for_timeout(60); y_after = y(pg); pg.wait_for_timeout(300)
        check("and a drag from there works as normal (50 px)", abs((y_hold2 - y_after) - 50) < 1, [y_hold2, y_after])
        check("and stops on lift", abs(y(pg) - y_after) < 0.01)

        # ------------------------------------------------------------ the pen during a glide
        group[0] = "pen stops"
        go_page(pg, 1)
        before = strokes()
        drag(cdp, 640, 700, -40, 10, 0.004)
        pg.wait_for_timeout(60); ya = y(pg); pg.wait_for_timeout(60); yb = y(pg)
        check("the glide was still going when the pen came down", yb < ya - 1, [ya, yb])
        # a pen point well inside a page (not in a 24 px gap), even if the glide moves on a little
        py = pg.evaluate("""() => { const rs = [...document.querySelectorAll('#stack .sheet')].map(s => s.getBoundingClientRect());
          for (let yy = 300; yy <= 650; yy += 10) if (rs.some(r => r.top < yy - 120 && r.bottom > yy + 120)) return yy; return 400; }""")
        pen = lambda t, x, yy, btn="left", n=1: cdp.send("Input.dispatchMouseEvent", {"type": t, "x": x, "y": yy, "button": btn, "buttons": 1 if btn == "left" else 0, "clickCount": n, "pointerType": "pen"})
        pen("mousePressed", 400, py); pg.wait_for_timeout(20); y_pen = y(pg)
        for k in range(1, 9): pen("mouseMoved", 400 + 20 * k, py + 5 * k)
        pen("mouseReleased", 560, py + 40); pg.wait_for_timeout(300); y_pen2 = y(pg)
        check("a pen down during a glide stops it", abs(y_pen2 - y_pen) < 0.01, [y_pen, y_pen2])
        check("and the pen still draws (one new stroke)", strokes() == before + 1, [before, strokes()])

        # ------------------------------------------------------------ one move per frame
        group[0] = "one move per frame"
        pg.wait_for_timeout(700)                   # past the pen's palm time
        go_page(pg, 2); y0 = y(pg)
        burst = pg.evaluate("""() => {
          const desk = document.getElementById('desk'), r = desk.getBoundingClientRect();
          const ev = (type, yy) => new PointerEvent(type, { pointerId: 77, pointerType: 'touch', isPrimary: true, bubbles: true, cancelable: true, clientX: r.left + 600, clientY: r.top + yy });
          window.__w = 0;
          desk.dispatchEvent(ev('pointerdown', 650));
          for (let k = 1; k <= 60; k++) desk.dispatchEvent(ev('pointermove', 650 - k * 5));
          window.__up = () => desk.dispatchEvent(ev('pointerup', 350));
          return window.__w; }""")
        pg.wait_for_timeout(120); writes = pg.evaluate("window.__w"); y1 = y(pg)
        pg.wait_for_timeout(200); pg.evaluate("window.__up()"); pg.wait_for_timeout(200)
        check("60 pointermoves in one burst: no transform write inside the burst", burst == 0, burst)
        check("and far fewer than 60 writes in all (at most 2)", writes <= 2, writes)
        check("and the stack still lands on the finger (300 px)", abs((y0 - y1) - 300) < 1, [y0, y1])
        check("a held finger lifted later does not glide", abs(y(pg) - y1) < 0.01, [y1, y(pg)])

        # ------------------------------------------------------------ the finger never draws
        group[0] = "finger never draws"
        check("no stroke from all those finger drags (only the one pen stroke)", strokes() == before + 1, strokes())
        mouse_y = y(pg)
        pg.mouse.move(300, 300); pg.mouse.down(); pg.mouse.move(500, 200, steps=4); pg.mouse.up(); pg.wait_for_timeout(300)
        check("a mouse drag draws and never moves or glides the stack", abs(y(pg) - mouse_y) < 0.01 and strokes() == before + 2, [mouse_y, y(pg), strokes()])
        pg.mouse.move(640, 400); pg.mouse.wheel(0, 300); pg.wait_for_timeout(120)
        check("the wheel still scrolls (300 px, through the frame)", abs((mouse_y - y(pg)) - 300) < 1, [mouse_y, y(pg)])

        # ------------------------------------------------------------ pattern paper
        group[0] = "paper"
        go_page(pg, 1); pg.wait_for_timeout(100)
        z = float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
        nodes = pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg[data-bg] *').length")
        ids_ = pg.evaluate("[...document.querySelectorAll('#stack svg[data-bg] pattern')].map(p => p.id)")
        check("zoom 1 and the paper is a handful of nodes (patterns, not a line per row)", z == 1 and nodes <= 8, [z, nodes])
        check("pattern ids are unique per page", len(ids_) == len(set(ids_)) == 16, len(ids_))
        shot = Image.open(io.BytesIO(pg.locator("#stack .sheet[data-index='1']").screenshot())).convert("L")
        W, H = shot.size
        row = [shot.getpixel((x, 500)) for x in range(W)]
        runs, inside = [], False
        for x, v in enumerate(row):
            if v < 245 and not inside: runs.append(x); inside = True
            elif v >= 245: inside = False
        inner = [x for x in runs if 3 < x < W - 3]
        check("a pixel row across page 1 shows 21 inner grid lines (22 blocks)", len(inner) == 21
              and all(abs(inner[k + 1] - inner[k] - 794 / 22) < 1.5 for k in range(20)), [W, len(inner), inner[:3]])
        col = [shot.getpixel((18, yy)) for yy in range(60)]
        first = next((yy for yy, v in enumerate(col) if v < 245), None)
        check("the top strip: the first grid row is 6 mm (22.7 px) down, blank above", first is not None and abs(first - 22.68) <= 1.5, first)

        # ------------------------------------------------------------ the desk never scrolls natively (pw-v4d)
        # Her tablet bug (25 Oct): after a pen button press or a long hold the view jumped to another page and every
        # stroke landed a fixed distance above the pen until a reopen. Cause: #desk was overflow: hidden, which is still
        # a scroll container, so Chrome could scroll it by itself (a focus, scrollIntoView, a long press) and the pen
        # maths, which only know the transform, were off by exactly that scroll. Now overflow: clip + a reset on pointer down.
        group[0] = "desk never scrolls"
        go_page(pg, 1); pg.wait_for_timeout(100)
        STATE = """() => { const d = document.getElementById('desk'), s = document.getElementById('stack');
          const dr = d.getBoundingClientRect(), sr = s.getBoundingClientRect();
          return { st: d.scrollTop, sl: d.scrollLeft, ov: getComputedStyle(d).overflowY, top: sr.top - dr.top, sel: getComputedStyle(d).userSelect }; }"""
        s0 = pg.evaluate(STATE)
        check("#desk is overflow: clip (never a scroll container) and user-select none", s0["ov"] == "clip" and s0["sel"] == "none", s0)
        pg.evaluate("document.getElementById('desk').scrollTop = 300; document.getElementById('desk').scrollLeft = 40")
        s1 = pg.evaluate(STATE)
        check("a scripted desk.scrollTop = 300 does nothing (stays 0 0, the stack does not move)", s1["st"] == 0 and s1["sl"] == 0 and abs(s1["top"] - s0["top"]) < 0.01, s1)
        pg.evaluate("document.getElementById('addBelow').focus()")
        s2 = pg.evaluate(STATE)
        check("focusing 'Add a page below' (off screen, bottom of the stack) does not scroll the desk", s2["st"] == 0 and abs(s2["top"] - s0["top"]) < 0.01, s2)
        pg.evaluate("document.querySelectorAll('.sheet')[5].scrollIntoView()")
        s3 = pg.evaluate(STATE)
        check("scrollIntoView of page 6 does not scroll the desk either", s3["st"] == 0 and abs(s3["top"] - s0["top"]) < 0.01, s3)
        pg.evaluate("document.getElementById('desk').blur(); document.activeElement && document.activeElement.blur()")
        # and the ink still lands under the pen after all that
        pg.wait_for_timeout(700)
        n0 = strokes()
        per0 = pg.evaluate("(ids) => ids.map((id) => window.__pw.ink.strokesOf(id).length)", ids)
        pen("mousePressed", 500, 400); pen("mouseMoved", 540, 410); pen("mouseReleased", 580, 420); pg.wait_for_timeout(200)
        land = pg.evaluate("""([ids, per0]) => {
          const k = ids.findIndex((id, i) => window.__pw.ink.strokesOf(id).length > per0[i]);   // the page that got the stroke
          if (k < 0) return null;
          const s = window.__pw.ink.strokesOf(ids[k]), last = s[s.length - 1];
          const sh = document.querySelector(`.sheet[data-id="${ids[k]}"]`), r = sh.getBoundingClientRect(), sc = r.width / sh.offsetWidth, p = last.data.points[0];
          return [r.left + p[0] * sc - 500, r.top + p[1] * sc - 400]; }""", [ids, per0])
        check("a pen stroke after those triggers lands under the pen (0 px off)", strokes() == n0 + 1 and land is not None and abs(land[0]) < 1 and abs(land[1]) < 1, land)
        # the readout's view line (?dbg=1): scroll 0 0 and drift 0 0
        ctx2 = b.new_context(viewport={"width": 1280, "height": 800}, has_touch=True); pg2 = ctx2.new_page()
        pg2.goto(LOCAL + "&dbg=1"); ready(pg2); pg2.evaluate(SEED); pg2.reload(); ready(pg2)
        pg2.locator(".nrow").first.click(); pg2.wait_for_selector("#noteView:not([hidden])"); pg2.wait_for_timeout(400)
        vline = pg2.evaluate("document.getElementById('dbgView').textContent")
        check("?dbg=1 shows a view line 'scroll 0 0 | view x y zN | drift 0 0'", re.fullmatch(r"scroll 0 0 \| view -?\d+ -?\d+ z\d\.\d\d \| drift -?0 -?0", vline) is not None, vline)
        check("the view line sits in its own box above the events box, inside the desk", pg2.evaluate("""() => { const v = document.getElementById('dbgView'), e = document.getElementById('dbg');
          return v.parentNode.id === 'desk' && v.getBoundingClientRect().bottom <= e.getBoundingClientRect().top && getComputedStyle(v).pointerEvents === 'none'; }"""))
        ctx2.close()
        check("no page errors", not errs, errs)
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
