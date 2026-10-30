# PenWorks scroll checks: one move per frame, glide after a flick, pattern paper.
# Run: python tests/test_scroll.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 8 grid pages into the localStorage twin and drives a finger through CDP touch input,
# the S Pen through CDP mouse input with pointerType "pen", and a burst of moves through synthetic
# PointerEvents. The stack's place is read from its transform; an in-page frame recorder logs every frame.
# pw-v4n: the "dbg last stroke (pw-v4n)" group: ?dbg=1 shows the last stroke's line and a Copy last stroke button (ink.lastStroke()).
# pw-v7b: the "zoom lock (pw-v7b)" group: a resize or full screen never resets the zoom (only opening a note fits), and the
# zoom lock chip (#zoomLock): locked, the zoom stays, one finger only taps and holds, two fingers move the stack.
import sys, subprocess, time, pathlib, re, io, json, math
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

def touch(cdp, kind, x=None, yy=None, pts=None):
    """one finger at (x, yy); or pts = [(x, y), ...] for several fingers at once (pw-v7b), each keeping its id by its place
    in the list. CDP lifts the fingers only all together (touchEnd): a touchMove that leaves one out keeps it down."""
    if kind == "touchEnd": tp = []
    elif pts is not None: tp = [{"x": px, "y": py, "id": k} for k, (px, py) in enumerate(pts)]
    else: tp = [{"x": x, "y": yy}]
    cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": tp})
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
    pg.click("#plClose"); pg.wait_for_selector("#pageList", state="hidden")    # pw-v4i: a thumb tap keeps the list open

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
        vline = pg2.evaluate("document.getElementById('dbgView').textContent").split("\n")[0]   # pw-v7b: a second line follows
        check("?dbg=1 shows a view line 'scroll 0 0 | view x y zN | drift 0 0'", re.fullmatch(r"scroll 0 0 \| view -?\d+ -?\d+ z\d\.\d\d \| drift -?0 -?0", vline) is not None, vline)
        check("the view line sits in its own box above the events box, inside the desk", pg2.evaluate("""() => { const v = document.getElementById('dbgView'), e = document.getElementById('dbg');
          return v.parentNode.id === 'desk' && v.getBoundingClientRect().bottom <= e.getBoundingClientRect().top && getComputedStyle(v).pointerEvents === 'none'; }"""))
        ctx2.close()
        # ------------------------------------------------------------ pw-v4n: ?dbg=1 shows and copies the last stroke
        prev_group = group[0]
        group[0] = "dbg last stroke (pw-v4n)"
        ctx3 = b.new_context(viewport={"width": 1280, "height": 800}, has_touch=True)
        ctx3.grant_permissions(["clipboard-read", "clipboard-write"])
        pg3 = ctx3.new_page(); errs3 = []
        pg3.on("pageerror", lambda e: errs3.append(str(e)))
        pg3.goto(LOCAL + "&dbg=1"); ready(pg3); pg3.evaluate(SEED); pg3.reload(); ready(pg3)
        pg3.locator(".nrow").first.click(); pg3.wait_for_selector("#noteView:not([hidden])"); pg3.wait_for_timeout(400)
        n_all = lambda: pg3.evaluate("(ids) => ids.reduce((k, id) => k + window.__pw.ink.strokesOf(id).length, 0)", ids)
        dbg_text = lambda: pg3.evaluate("document.getElementById('dbg').textContent")
        btn_text = lambda: pg3.evaluate("document.getElementById('dbgCopy').textContent")
        check("before any stroke: #dbg shows 'last: none'", "last: none" in dbg_text(), dbg_text())
        check("before any stroke: #dbgCopy is disabled and says 'No stroke yet'", pg3.evaluate("() => { const b = document.getElementById('dbgCopy'); return !!b && b.disabled && b.textContent === 'No stroke yet'; }"))
        check("before any stroke: lastStroke() is null", pg3.evaluate("window.__pw.ink.lastStroke()") is None)
        check("the button sits on the desk above #dbgView, 44 px tall at least, takes pointer events, same left edge", pg3.evaluate("""() => { const b = document.getElementById('dbgCopy'), v = document.getElementById('dbgView'), r = b.getBoundingClientRect();
          return b.parentNode.id === 'desk' && r.bottom <= v.getBoundingClientRect().top && r.height >= 44 && getComputedStyle(b).pointerEvents === 'auto' && r.left === v.getBoundingClientRect().left; }"""))
        sh = pg3.locator(".sheet").first.bounding_box()
        x0, y0 = sh["x"] + sh["width"] * 0.3, sh["y"] + 160
        # a freehand pen stroke: 20 moves along a wobbly curve, no hold
        pg3.mouse.move(x0, y0); pg3.mouse.down()
        for k in range(1, 21): pg3.mouse.move(x0 + k * 9, y0 + 30 * math.sin(k / 3.0) + k * 2)
        pg3.mouse.up(); pg3.wait_for_timeout(400)
        L = pg3.evaluate("window.__pw.ink.lastStroke()")
        info = L and {k: L[k] for k in L if k != "points"}
        check("a freehand stroke: lastStroke() has n equal to points.length, pointerType 'mouse', not snapped", L is not None and L["n"] == len(L["points"]) and L["n"] >= 10 and L["pointerType"] == "mouse" and L["snapped"] is False, info)
        check("a freehand stroke: classify is null or a shape type, z and at are numbers, len has one decimal", L is not None and (L["classify"] is None or isinstance(L["classify"], str)) and isinstance(L["z"], (int, float)) and isinstance(L["at"], (int, float)) and abs(L["len"] * 10 - round(L["len"] * 10)) < 1e-6 and L["len"] > 50, info)
        line = dbg_text().split("\n")[-1]
        check("a freehand stroke: #dbg shows 'last: <n> pts' and 'freehand'", L is not None and line.startswith(f"last: {L['n']} pts, ") and line.endswith("freehand") and "mouse" in line, line)
        check("a freehand stroke: the button is enabled and says 'Copy last stroke'", pg3.evaluate("() => { const b = document.getElementById('dbgCopy'); return !b.disabled && b.textContent === 'Copy last stroke'; }"))
        # a line held still for 650 ms snaps
        before = n_all()
        ly = y0 + 300
        pg3.mouse.move(x0, ly); pg3.mouse.down()
        for k in range(1, 31): pg3.mouse.move(x0 + k * 10, ly + k * 1.0)
        pg3.wait_for_timeout(650)
        pg3.mouse.up(); pg3.wait_for_timeout(400)
        L2 = pg3.evaluate("window.__pw.ink.lastStroke()")
        info2 = L2 and {k: L2[k] for k in L2 if k != "points"}
        check("a held line snaps: one more stroke, snapped true, classify 'line', raw freehand points (more than 2)", n_all() == before + 1 and L2["snapped"] is True and L2["classify"] == "line" and len(L2["points"]) > 2 and L2["n"] == len(L2["points"]), info2)
        check("a held line: the stored record is a shape without points, so lastStroke holds the raw freehand", pg3.evaluate("(ids) => { const s = ids.flatMap((id) => window.__pw.ink.strokesOf(id)); const t = s[s.length - 1]; return t.kind === 'shape' && !t.data.points; }", ids))
        line2 = dbg_text().split("\n")[-1]
        check("a held line: #dbg shows 'classify: line, snapped'", "classify: line, snapped" in line2, line2)
        # copy: the clipboard holds the same stroke
        pg3.click("#dbgCopy"); pg3.wait_for_timeout(200)
        clip = pg3.evaluate("navigator.clipboard.readText()")
        try: cj = json.loads(clip)
        except Exception: cj = None
        check("copy: the clipboard parses as JSON with the same n and points", cj is not None and cj["n"] == L2["n"] and cj["points"] == L2["points"] and cj["snapped"] is True, clip[:80])
        check("copy: the button reads 'Copied (<n> pts)'", btn_text() == f"Copied ({L2['n']} pts)", btn_text())
        pg3.wait_for_timeout(2300)
        check("copy: after 2 s the button reads 'Copy last stroke' again", btn_text() == "Copy last stroke", btn_text())
        # a pointerdown on the button starts no stroke
        before = n_all(); at0 = pg3.evaluate("window.__pw.ink.lastStroke().at")
        bb = pg3.locator("#dbgCopy").bounding_box(); cx, cy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
        pg3.mouse.move(cx, cy); pg3.mouse.down(); pg3.mouse.move(cx + 12, cy + 3); pg3.mouse.up(); pg3.wait_for_timeout(300)
        check("a pointerdown and a drag on the button adds no stroke and leaves lastStroke alone", n_all() == before and pg3.evaluate("window.__pw.ink.lastStroke().at") == at0, [n_all(), before])
        # clipboard refused: the textarea appears
        pg3.evaluate("Object.defineProperty(navigator, 'clipboard', { value: { writeText: () => Promise.reject(new Error('no')) }, configurable: true })")
        pg3.click("#dbgCopy"); pg3.wait_for_timeout(200)
        ta = pg3.evaluate("() => { const t = document.getElementById('dbgText'); return t && { ro: t.readOnly, rows: t.rows, focus: document.activeElement === t, json: t.value, sel: t.selectionEnd - t.selectionStart === t.value.length }; }")
        check("clipboard refused: a read-only focused selected textarea (6 rows) holds the JSON and the button says 'Select + copy above'", bool(ta) and ta["ro"] and ta["rows"] == 6 and ta["focus"] and ta["sel"] and json.loads(ta["json"])["n"] == L2["n"] and btn_text() == "Select + copy above", ta and {k: ta[k] for k in ta if k != "json"})
        check("no page errors (dbg group)", not errs3, errs3)
        ctx3.close()
        # without ?dbg=1 there is no readout and no button
        check("without ?dbg=1: no #dbg, no #dbgView, no #dbgCopy", pg.evaluate("() => !document.getElementById('dbg') && !document.getElementById('dbgView') && !document.getElementById('dbgCopy')"))
        check("without ?dbg=1: ink.lastStroke() is still there (always kept)", pg.evaluate("typeof window.__pw.ink.lastStroke === 'function'"))
        group[0] = prev_group
        check("no page errors", not errs, errs)

        # ------------------------------------------------------------ pw-v7b: the zoom never resets by itself; the zoom lock
        # Her tablet (27 Oct): zoomed in and explaining, the page shot back to a fitted view about 30 times in a day. Every
        # window resize (and full screen) ran relayout() = fit(): the zoom thrown away. Now only opening a note fits, and the
        # lock chip (#zoomLock, bottom-left) keeps the zoom fixed: one finger only taps and holds, two fingers move the stack.
        group[0] = "zoom lock (pw-v7b)"
        ctx4 = b.new_context(viewport={"width": 1280, "height": 800}, has_touch=True)
        pg4 = ctx4.new_page(); errs4 = []
        pg4.on("pageerror", lambda e: errs4.append(str(e)))
        pg4.goto(LOCAL); ready(pg4); pg4.evaluate(SEED); pg4.reload(); ready(pg4)
        pg4.locator(".nrow").first.click(); pg4.wait_for_selector("#noteView:not([hidden])"); pg4.wait_for_timeout(200)
        cdp4 = ctx4.new_cdp_session(pg4)
        VIEW = """() => import('./js/page.js').then((m) => { const d = document.getElementById('desk'), s = document.getElementById('stack');
          return { ...m.view(), ...m.viewStats(), cur: m.current(), dw: d.clientWidth, dh: d.clientHeight,
                   w: parseFloat(s.style.width), h: parseFloat(s.style.height), top: s.getBoundingClientRect().top }; })"""
        vw = lambda: pg4.evaluate(VIEW)
        def inside(v):     # the view inside page.js's clamp (MARGIN 24): a stack narrower than the desk centred, else within the edges
            w, h = v["w"] * v["z"], v["h"] * v["z"]
            okx = abs(v["x"] - (v["dw"] - w) / 2) < 0.01 if w <= v["dw"] - 48 else v["dw"] - w - 24.01 <= v["x"] <= 24.01
            oky = abs(v["y"] - 24) < 0.01 if h <= v["dh"] - 48 else v["dh"] - h - 24.01 <= v["y"] <= 24.01
            return okx and oky
        def same(a, c): return abs(a["x"] - c["x"]) < 0.01 and abs(a["y"] - c["y"]) < 0.01 and a["z"] == c["z"]
        def lerp(a, c, f): return (a[0] + (c[0] - a[0]) * f, a[1] + (c[1] - a[1]) * f)
        def two(a0, b0, a1, b1, n=10, lift=True):          # two fingers down together, moved in n steps, lifted together
            touch(cdp4, "touchStart", pts=[a0, b0]); pg4.wait_for_timeout(30)
            for k in range(1, n + 1):
                touch(cdp4, "touchMove", pts=[lerp(a0, a1, k / n), lerp(b0, b1, k / n)]); pg4.wait_for_timeout(16)
            if lift: touch(cdp4, "touchEnd"); pg4.wait_for_timeout(80)
        def one(x0, y0, dx, dy, n=10, pause=0.03):         # one finger dragged in n steps, `pause` s apart, then lifted
            touch(cdp4, "touchStart", x0, y0)
            for k in range(1, n + 1):
                if pause: time.sleep(pause)
                touch(cdp4, "touchMove", x0 + dx * k / n, y0 + dy * k / n)
            touch(cdp4, "touchEnd")
        def still4(quiet=250, limit=6000):                 # until the view has not changed for `quiet` ms
            last, quiet_for, t0 = vw(), 0, time.time()
            while time.time() - t0 < limit / 1000:
                pg4.wait_for_timeout(50); now = vw()
                quiet_for = quiet_for + 50 if same(now, last) else 0
                last = now
                if quiet_for >= quiet: break
            return last
        def wheel(dy, ctrl):
            pg4.evaluate("""([dy, ctrl]) => document.getElementById('desk').dispatchEvent(new WheelEvent('wheel',
              { deltaY: dy, ctrlKey: ctrl, clientX: 640, clientY: 400, bubbles: true, cancelable: true }))""", [dy, ctrl])
            pg4.wait_for_timeout(80)
        lockbtn = pg4.locator("#zoomLock")
        pressed = lambda: lockbtn.get_attribute("aria-pressed")
        toast4 = lambda: pg4.evaluate("document.getElementById('toast').textContent")
        strokes4 = lambda: pg4.evaluate("(ids) => ids.reduce((k, id) => k + window.__pw.ink.strokesOf(id).length, 0)", ids)
        GEO = """() => { const c = document.getElementById('zoomLock'), r = c.getBoundingClientRect(), nb = document.getElementById('noteBody').getBoundingClientRect(), cs = getComputedStyle(c);
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return { w: r.width, h: r.height, left: r.left - nb.left, bottom: nb.bottom - r.bottom, parent: c.parentNode.id, inDesk: !!c.closest('#desk'),
                   label: c.getAttribute('aria-label'), bg: cs.backgroundColor, round: cs.borderRadius === '50%', z: cs.zIndex, hit: hit === c,
                   open: getComputedStyle(c.querySelector('.lockOpen')).display, shut: getComputedStyle(c.querySelector('.lockShut')).display }; }"""

        v0 = vw()
        check("a note opens fitted (zoom 1 at 1280 x 800) and unlocked: one fit, its cause 'open'",
              abs(v0["z"] - 1) < 1e-9 and v0["lock"] is False and v0["fits"] == 1 and v0["cause"] == "open" and pressed() == "false", v0)
        g = pg4.evaluate(GEO)
        check("(l) #zoomLock: a round 44 x 44 chip in #noteBody (not the desk), 12 px from the left and bottom, z-index 6, 'Lock zoom', nothing over it",
              g["w"] == 44 and g["h"] == 44 and g["round"] and g["parent"] == "noteBody" and not g["inDesk"] and abs(g["left"] - 12) < 0.5
              and abs(g["bottom"] - 12) < 0.5 and g["z"] == "6" and g["label"] == "Lock zoom" and g["hit"] and lockbtn.is_visible(), g)
        check("(l) unlocked: the translucent graphite chip with the open padlock", g["bg"] == "rgba(38, 42, 48, 0.35)" and g["open"] != "none" and g["shut"] == "none", g)

        # (k) + (a): a pinch zooms (unlocked), then a resize keeps that zoom
        two((590, 400), (690, 400), (540, 400), (740, 400)); pg4.wait_for_timeout(150)
        v1 = vw()
        check("(k) unlocked: a pinch of two points moving apart zooms as before (100 to 200 px apart: zoom 2.0), no fit",
              abs(v1["z"] - 2) < 0.01 and v1["fits"] == 1, v1)
        pg4.set_viewport_size({"width": 1100, "height": 700}); pg4.wait_for_timeout(250)
        v2 = vw()
        check("(a) a viewport resize (1280 x 800 to 1100 x 700) keeps the zoom at 2.0 and the place, the fit count unchanged",
              same(v1, v2) and v2["fits"] == 1 and v2["resizes"] > v1["resizes"] and inside(v2), [v1, v2])
        pg4.set_viewport_size({"width": 1280, "height": 800}); pg4.wait_for_timeout(250)
        v3 = vw()
        check("(a) and back to 1280 x 800: zoom 2.0, the place, still the one fit from opening", same(v1, v3) and v3["fits"] == 1, v3)

        # (b) full screen and back
        bar_h = pg4.evaluate("document.getElementById('noteBar').offsetHeight")
        pg4.click("#fsBtn"); pg4.wait_for_timeout(400)
        vf = vw(); chip_full = lockbtn.is_visible()
        check("(b) the full-screen button keeps the zoom (2.0) and the place, no fit", same(v3, vf) and vf["fits"] == 1 and inside(vf), [v3, vf])
        check("(b) the desk grew up by the note bar: the page moved up with it, by the bar's height and no more",
              bar_h > 0 and abs((v3["top"] - vf["top"]) - bar_h) < 0.6, [bar_h, v3["top"], vf["top"]])
        check("(l) full screen (body.full): the note bar and the counter hide, the chip stays",
              pg4.evaluate("document.body.classList.contains('full')") and pg4.locator("#noteBar").is_hidden() and pg4.locator("#counter").is_hidden() and chip_full)
        pg4.click("#exitFs"); pg4.wait_for_timeout(400)
        vx = vw()
        check("(b) leaving full screen keeps the zoom (2.0) and the place, no fit", same(v3, vx) and vx["fits"] == 1 and abs(vx["top"] - v3["top"]) < 0.6, [v3, vx])

        # (c) a resize with the zoomed stack wider than the desk: the clamp holds
        one(1000, 500, -700, 0, n=14, pause=0.03); vc0 = still4()
        check("(c) set-up: a one-finger pan to the zoomed stack's right edge (24 px in from the desk's)",
              abs(vc0["x"] - (vc0["dw"] - vc0["w"] * vc0["z"] - 24)) < 0.01 and vc0["z"] == v1["z"], vc0)
        pg4.set_viewport_size({"width": 1500, "height": 800}); pg4.wait_for_timeout(250)
        vc1 = vw()
        check("(c) the window grows wider: the stack's right edge comes back to 24 px from the desk's, zoom 2.0, no fit",
              abs(vc1["x"] - (vc1["dw"] - vc1["w"] * vc1["z"] - 24)) < 0.01 and vc1["z"] == v1["z"] and vc1["fits"] == 1 and inside(vc1), [vc0, vc1])
        pg4.set_viewport_size({"width": 1000, "height": 700}); pg4.wait_for_timeout(250)
        vc2 = vw()
        check("(c) narrower: the stack stays where it was, inside the clamp", inside(vc2) and abs(vc2["x"] - vc1["x"]) < 0.01 and vc2["z"] == v1["z"], [vc1, vc2])
        pg4.set_viewport_size({"width": 1720, "height": 800}); pg4.wait_for_timeout(250)
        vc3 = vw()
        check("(c) so wide the zoomed stack fits across: it is centred, zoom still 2.0",
              inside(vc3) and abs(vc3["x"] - (vc3["dw"] - vc3["w"] * vc3["z"]) / 2) < 0.01 and vc3["z"] == v1["z"], vc3)
        pg4.set_viewport_size({"width": 1280, "height": 800}); pg4.wait_for_timeout(250)
        vc4 = vw()
        check("(c) back to 1280 x 800: inside the clamp, zoom 2.0, still the one fit", inside(vc4) and vc4["z"] == v1["z"] and vc4["fits"] == 1, vc4)
        one(640, 500, -200, 0, n=20, pause=0.08); still4()           # a slow pan: the stack away from the edges for the lock checks

        # locking stops a glide where it is
        one(640, 650, 0, -400, n=10, pause=0.004); pg4.wait_for_timeout(60)
        ga, n_before = vw(), strokes4()
        lockbtn.click(); pg4.wait_for_timeout(30); gb = vw(); pg4.wait_for_timeout(250); gc = vw()
        check("a tap on the chip during a glide stops it where it is (and the tap draws nothing)", same(gb, gc) and strokes4() == n_before, [ga, gb, gc])

        # (d) locked: a pinch only moves the stack by its midpoint
        vd0 = vw(); g2 = pg4.evaluate(GEO)
        check("(d) a tap on the chip locks: aria-pressed true, the toast 'Zoom locked', solid graphite with the closed padlock",
              pressed() == "true" and vd0["lock"] is True and toast4() == "Zoom locked" and g2["bg"] == "rgb(38, 42, 48)" and g2["shut"] != "none" and g2["open"] == "none", [g2, toast4()])
        pg4.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        dk = pg4.evaluate("[getComputedStyle(document.getElementById('zoomLock')).backgroundColor, getComputedStyle(document.getElementById('zoomLock')).color]")
        pg4.evaluate("document.documentElement.removeAttribute('data-theme')")
        check("(d) dark mode: the same chip (solid #262A30, white padlock), it sits on the light desk", dk == ["rgb(38, 42, 48)", "rgb(255, 255, 255)"], dk)
        two((540, 400), (740, 400), (430, 360), (930, 360))            # 200 to 500 px apart; the midpoint (640, 400) to (680, 360)
        vd1 = vw()
        check("(d) locked: a pinch of two points moving apart (200 to 500 px) leaves the zoom at 2.0", vd1["z"] == vd0["z"] and vd1["fits"] == 1, [vd0, vd1])
        check("(d) ... and moves the stack by the midpoint's move (+40, -40)", abs((vd1["x"] - vd0["x"]) - 40) < 0.6 and abs((vd1["y"] - vd0["y"]) + 40) < 0.6, [vd0, vd1])
        # one of the two lifts: the other finger then does nothing (no pan, no glide). CDP cannot lift one finger of two (see
        # touch()), so this one runs on synthetic touch PointerEvents fired on the desk, as in "one move per frame"
        PEV = """([type, id, x, y]) => { const desk = document.getElementById('desk'), r = desk.getBoundingClientRect();
          desk.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch', isPrimary: id === 81, bubbles: true, cancelable: true,
                                                      clientX: r.left + x, clientY: r.top + y })); }"""
        pev = lambda t, i, x, yy: pg4.evaluate(PEV, [t, i, x, yy])
        vq0 = vw()
        pev("pointerdown", 81, 500, 400); pev("pointerdown", 82, 700, 400)
        for k in range(1, 7): pev("pointermove", 81, 500, 400 - 10 * k); pev("pointermove", 82, 700, 400 - 10 * k); pg4.wait_for_timeout(16)
        pev("pointerup", 82, 700, 340); pg4.wait_for_timeout(40); vq1 = vw()                       # the second finger lifts
        for k in range(1, 11): pev("pointermove", 81, 500, 340 - 30 * k)                            # the first flicks on alone
        pev("pointerup", 81, 500, 40); pg4.wait_for_timeout(400); vq2 = vw()
        check("locked: two fingers move the stack 60 px; when one lifts, the other neither pans nor glides",
              abs((vq0["y"] - vq1["y"]) - 60) < 0.6 and same(vq1, vq2) and vq2["z"] == vq0["z"], [vq0, vq1, vq2])

        # (e) locked: one finger moves nothing
        ve0 = vw()
        one(640, 500, 0, -200, n=10, pause=0.05); pg4.wait_for_timeout(300); ve1 = vw()
        check("(e) locked: a one-finger drag of 200 px moves nothing", same(ve0, ve1), [ve0, ve1])
        one(640, 650, 0, -400, n=10, pause=0.004); pg4.wait_for_timeout(500); ve2 = vw()
        check("(e) locked: a fast one-finger flick glides nothing", same(ve1, ve2), [ve1, ve2])

        # (f) locked: two fingers pan
        vf0 = vw()
        two((500, 560), (760, 560), (500, 410), (760, 410)); vf1 = vw(); pg4.wait_for_timeout(300); vf2 = vw()
        check("(f) locked: a two-finger drag of 150 px moves the stack 150 px, the zoom unchanged",
              abs((vf0["y"] - vf1["y"]) - 150) < 0.6 and abs(vf1["x"] - vf0["x"]) < 0.6 and vf1["z"] == vf0["z"], [vf0, vf1])
        check("(f) ... and stops on the lift (no glide)", same(vf1, vf2), [vf1, vf2])

        # (g) locked: Ctrl + wheel does nothing, the plain wheel scrolls
        vg0 = vw()
        wheel(-300, True); vg1 = vw()
        check("(g) locked: Ctrl + wheel leaves the zoom (and the place)", same(vg0, vg1), [vg0, vg1])
        pg4.mouse.move(640, 400); pg4.mouse.wheel(0, 300); pg4.wait_for_timeout(150); vg2 = vw()
        check("(g) locked: the plain wheel still scrolls (300 px), the zoom unchanged", abs((vg1["y"] - vg2["y"]) - 300) < 0.6 and vg2["z"] == vg0["z"], [vg1, vg2])

        # (h) locked: a page-list jump
        go_page(pg4, 6); vh = vw()
        check("(h) locked: a page-list jump to page 6 lands on page 6 (its top 24 px down) at the same zoom, still locked",
              vh["cur"] == 5 and vh["z"] == vg0["z"] and abs(vh["y"] - (24 - 5 * (1123 + 24) * vh["z"])) < 0.6 and vh["lock"] and pressed() == "true", vh)

        # (i) locked: the pen draws, a finger tap clears a selection, a finger hold opens the menu
        pen4 = lambda t, x, yy: cdp4.send("Input.dispatchMouseEvent", {"type": t, "x": x, "y": yy, "button": "left", "buttons": 1, "clickCount": 1, "pointerType": "pen"})
        vi0, n0 = vw(), strokes4()
        pen4("mousePressed", 400, 300)
        for k in range(1, 9): pen4("mouseMoved", 400 + 25 * k, 300 + 3 * k)
        pen4("mouseReleased", 600, 324); pg4.wait_for_timeout(200)
        check("(i) locked: the S Pen still draws (one new stroke) and moves nothing", strokes4() == n0 + 1 and same(vi0, vw()), [n0, strokes4()])
        pg4.click("#tool-select"); pg4.wait_for_timeout(30)
        pg4.mouse.move(370, 260); pg4.mouse.down(); pg4.mouse.move(640, 370, steps=8); pg4.mouse.up(); pg4.wait_for_timeout(100)
        s1 = pg4.evaluate("window.__pw.ink.selection()")
        check("(i) set-up: the Select tool's box around the stroke selects it", bool(s1) and len(s1["ids"]) == 1, s1)
        pg4.wait_for_timeout(700)                                    # past the pen's palm time
        touch(cdp4, "touchStart", 900, 620); pg4.wait_for_timeout(40); touch(cdp4, "touchEnd"); pg4.wait_for_timeout(100)
        check("(i) locked: a finger tap outside the selection clears it, nothing moved", pg4.evaluate("window.__pw.ink.selection()") is None and same(vi0, vw()))
        touch(cdp4, "touchStart", 700, 560); pg4.wait_for_timeout(650)
        menu4 = pg4.evaluate("() => { const m = document.getElementById('menu'); return !m.hidden && m.getBoundingClientRect().height > 0; }")
        touch(cdp4, "touchEnd"); pg4.wait_for_timeout(60)
        check("(i) locked: a finger held 500 ms still opens the hold menu, nothing moved", menu4 and same(vi0, vw()), [menu4, vw()])
        pg4.keyboard.press("Escape"); pg4.wait_for_timeout(30)
        pg4.click("#tool-pen"); pg4.wait_for_timeout(30)

        # (j) + (l): close the note (chip hidden, lock off), open it again: unlocked and fitted
        pg4.click("#backBtn"); pg4.wait_for_selector("#listView:not([hidden])"); pg4.wait_for_timeout(100)
        vj0 = vw()
        check("(l) outside a note the chip is hidden", lockbtn.is_hidden())
        check("(j) closing the note turns the lock off", vj0["lock"] is False and pressed() == "false", vj0)
        pg4.locator(".nrow").first.click(); pg4.wait_for_selector("#noteView:not([hidden])"); pg4.wait_for_timeout(200)
        vj = vw()
        check("(j) opened again: unlocked (aria-pressed false), fitted (zoom back to the fit value, on the page she left, pw-v7p), the second fit, cause 'open'",
              vj["lock"] is False and pressed() == "false" and abs(vj["z"] - v0["z"]) < 1e-9 and vj["cur"] > 0
              and vj["fits"] == 2 and vj["cause"] == "open" and lockbtn.is_visible(), vj)
        lockbtn.click(); pg4.wait_for_timeout(60); lockbtn.click(); pg4.wait_for_timeout(60)
        check("a second tap unlocks: aria-pressed false, the toast 'Zoom unlocked', the open padlock again",
              pressed() == "false" and toast4() == "Zoom unlocked" and vw()["lock"] is False and pg4.evaluate(GEO)["open"] != "none", toast4())

        # (k) unlocked again: everything as before
        vk0 = vw()
        two((590, 400), (690, 400), (565, 400), (715, 400)); pg4.wait_for_timeout(150); vk1 = vw()
        check("(k) unlocked again: the pinch zooms (100 to 150 px apart: zoom x 1.5)", abs(vk1["z"] - 1.5 * vk0["z"]) < 0.01, [vk0, vk1])
        wheel(-200, True); vk2 = vw()
        check("(k) unlocked: Ctrl + wheel zooms", vk2["z"] > vk1["z"] + 0.1, [vk1, vk2])
        vk3 = vw(); one(640, 600, 0, -150, n=15, pause=0.08); pg4.wait_for_timeout(300); vk4 = vw()
        check("(k) unlocked: one finger pans again (150 px)", abs((vk3["y"] - vk4["y"]) - 150) < 1, [vk3, vk4])
        check("no page errors (zoom lock)", not errs4, errs4)
        ctx4.close()

        # (m) ?dbg=1: the resize / fit / lock line
        ctx5 = b.new_context(viewport={"width": 1280, "height": 800}, has_touch=True)
        pg5 = ctx5.new_page(); errs5 = []
        pg5.on("pageerror", lambda e: errs5.append(str(e)))
        pg5.goto(LOCAL + "&dbg=1"); ready(pg5); pg5.evaluate(SEED); pg5.reload(); ready(pg5)
        pg5.locator(".nrow").first.click(); pg5.wait_for_selector("#noteView:not([hidden])"); pg5.wait_for_timeout(400)
        LINE = r"resize (\d+) \| fit (\d+) \((\w+)\) \| lock (on|off)(?: \| oe [\d.]+ [\d.]+)?"   # pw-v7i: the pen filter pair follows
        dl = lambda: pg5.evaluate("document.getElementById('dbgView').textContent").split("\n")
        l1 = dl(); m1 = re.fullmatch(LINE, l1[1]) if len(l1) == 2 else None
        check("(m) ?dbg=1: #dbgView's second line reads 'resize <n> | fit 1 (open) | lock off'", m1 is not None and m1.group(2) == "1" and m1.group(3) == "open" and m1.group(4) == "off", l1)
        r0 = int(m1.group(1)) if m1 else -99
        pg5.set_viewport_size({"width": 1200, "height": 760}); pg5.wait_for_timeout(400)
        l2 = dl(); m2 = re.fullmatch(LINE, l2[1]) if len(l2) == 2 else None
        check("(m) a viewport resize: the resize count goes up by one, the fit count stays 1", m2 is not None and int(m2.group(1)) == r0 + 1 and m2.group(2) == "1", [l1, l2])
        pg5.click("#zoomLock"); pg5.wait_for_timeout(350)
        check("(m) after a tap on the chip the line says 'lock on'", "| lock on" in dl()[-1], dl())   # pw-v7i: '| oe ...' follows
        geo5 = pg5.evaluate("""() => { const d = document.getElementById('desk').getBoundingClientRect(), c = document.getElementById('zoomLock').getBoundingClientRect();
          const left = (id) => document.getElementById(id).getBoundingClientRect().left - d.left;
          const hit = document.elementFromPoint(c.left + c.width / 2, c.top + c.height / 2);
          return { dbg: left('dbg'), view: left('dbgView'), copy: left('dbgCopy'), hit: !!hit && hit.id === 'zoomLock', chipRight: c.right - d.left }; }""")
        check("(m) the dbg boxes sit 64 px in (right of the chip), the chip stays tappable with them up",
              all(abs(geo5[k] - 64) < 0.5 for k in ("dbg", "view", "copy")) and geo5["hit"] and geo5["chipRight"] <= 64, geo5)
        check("no page errors (zoom lock, dbg)", not errs5, errs5)
        ctx5.close()
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
