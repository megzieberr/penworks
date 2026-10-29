# PenWorks pw-v7d checks: the Blipwork Casio fx-991ZA Plus II inside PenWorks (a verbatim copy, a floating card).
# Run: python tests/test_calc.py        (local mode only: ?local=1, Supabase is never touched)
# Part A: tests/verify-calc-casio.html (Blipwork's own spec page, one import + one stylesheet line changed) is loaded from
#   PenWorks and must pass every row; Blipwork's own page is run the same way and both counts are printed (they must match).
#   The page also loads Blipwork's quest01 consumer for its "Build 8 / 9" rows: that file is Blipwork's, not PenWorks'. The
#   test serves it (and its two imports) from the Blipwork folder, READ ONLY, for the URLs /tests/js/** (a fixture, not a copy).
# Part B: the real app. The tools button at the top of the tray (pw-v7e; it was the bottom), the card beside the tray on both sides, the keys, the LCD
#   surviving a close, a stroke next to the card landing under the pointer, a press on a key drawing nothing, the head
#   dragging the card, the pen panel NOT closed by a tap inside the card (and closed by a tap on the desk as before), the
#   card NOT closed by a tap on the desk. Screenshots of both sides go to _build/shots-calc/.
#   pw-v7o: Part B runs at 1.0x (Blipwork's own size), stored the way she would leave it (localStorage pw.calc), so its
#   numbers stay the pw-v7d ones; the dragged place is now remembered on the device.
# Part C (pw-v7o, round 8, her ask "much much bigger... or at least lemme adjust it"): the size. 1.6x by default on a
#   1280 px screen (the box measured), the corner handle (20 px) changes it with the proportions kept, 1.0x and 2.5x are
#   the limits, a reload brings size and place back, a 375 px phone never has it off-screen, every key's centre hits that
#   key at 2.5x and a tap on "=" gives the answer, a long input keeps its cursor in view at 2.5x, the LCD is laid out again
#   (no transform anywhere up the tree), and a stroke beside the card at 2.5x lands under the pointer.
import sys, subprocess, time, pathlib, re, math
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLIP = pathlib.Path(r"C:\Users\megzi\Desktop\Claude Code Projects\maths-homework-quest")
PORT, BPORT = 8797, 8798
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-calc"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-29T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Calc', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
  return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height, shown: !e.hidden && b.width > 0 }; }"""
LCD = """() => { const e = document.querySelector('#calcCard .lcd-res'); return e ? e.textContent.trim() : null; }"""
STROKES = "() => ['s0','s1','s2'].flatMap((id) => window.__pw.ink.strokesOf(id).map((r) => r.id))"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def rect(pg, sel): return pg.evaluate(RECT, sel)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def menu_flip(pg):
    pg.click("#noteMore"); pg.wait_for_selector("#menu:not([hidden])")
    pg.locator("#menu button[role='menuitem']", has_text=re.compile(r"^Tray to the ")).first.click()
    pg.wait_for_timeout(200)
def key(pg, kid): pg.click(f'#calcCard [data-keyid="{kid}"]'); pg.wait_for_timeout(30)
def center(r): return r["l"] + r["w"] / 2, r["t"] + r["h"] / 2
def stroke_lands(pg, x0, y0):
    """a mouse stroke from client (x0, y0); the new record's first point, mapped through the page's place and the zoom, against the pointer"""
    pg.click("#tool-pen"); pg.wait_for_timeout(40); pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
    before = pg.evaluate(STROKES)
    pg.mouse.move(x0, y0); pg.mouse.down()
    for k in range(1, 7): pg.mouse.move(x0 + 20 * k, y0 + 6 * k, steps=3)
    pg.mouse.up(); pg.wait_for_timeout(80)
    got = pg.evaluate("""(before) => {
      const z = +document.getElementById('stack').dataset.zoom;
      for (const id of ['s0', 's1', 's2']) for (const r of window.__pw.ink.strokesOf(id)) {
        if (before.includes(r.id)) continue;
        const sh = document.querySelector(`#stack .sheet[data-id="${id}"]`).getBoundingClientRect(), p = r.data.points[0];
        return { page: id, x: sh.left + p[0] * z, y: sh.top + p[1] * z, n: r.data.points.length, z };
      }
      return null; }""", before)
    if not got: return False, None
    return math.hypot(got["x"] - x0, got["y"] - y0) <= 1.5, got

def spec_page(b, base, url_path, route_blip):
    """load a verify page at 375 x 812 (the harness size), wait for window.__VERIFY__; returns (verify, errors)"""
    ctx = b.new_context(viewport={"width": 375, "height": 812}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    if route_blip:
        def fulfil(route):
            rel = route.request.url.split("/tests/js/", 1)[1].split("?")[0]
            f = BLIP / "js" / rel
            if f.is_file(): route.fulfill(status=200, body=f.read_bytes(), content_type="text/javascript")
            else: route.fulfill(status=404, body="")
        pg.route("**/tests/js/**", fulfil)
    pg.goto(base + url_path, wait_until="load", timeout=120000)
    pg.wait_for_function("window.__VERIFY__ !== undefined", timeout=900000, polling=2000)
    v = pg.evaluate("window.__VERIFY__"); ctx.close()
    return v, errs

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
bsrv = subprocess.Popen([sys.executable, "-m", "http.server", str(BPORT), "--bind", "127.0.0.1"], cwd=str(BLIP),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------ A: the Casio spec, Blipwork's page and the copy
        group[0] = "A. Casio spec"
        vb, eb = spec_page(b, f"http://127.0.0.1:{BPORT}/", "verify-calc-casio.html", False)
        vc, ec = spec_page(b, f"http://127.0.0.1:{PORT}/", "tests/verify-calc-casio.html", True)
        print(f"Casio spec, Blipwork's own page: {vb['passed']}/{vb['total']}  ok={vb['ok']}  errs={eb[:1]}")
        print(f"Casio spec, PenWorks copy:       {vc['passed']}/{vc['total']}  ok={vc['ok']}  errs={ec[:1]}")
        for f in (vc.get('fails') or [])[:10]: print('   copy mismatch:', f[:300])
        for f in (vb.get('fails') or [])[:10]: print('   Blipwork mismatch:', f[:300])
        check("Blipwork's own spec page passes every row", vb["ok"] is True and vb["passed"] == vb["total"], vb)
        check("the PenWorks copy of the spec page passes every row (ok === true)", vc["ok"] is True and vc["passed"] == vc["total"], vc)
        check("both pages run the same number of rows", vb["total"] == vc["total"], [vb["total"], vc["total"]])
        check("no page errors on either spec page", not eb and not ec, [eb, ec])

        # ------------------------------------------------------------ B: the real app, 1280 x 800
        group[0] = "B. tools button + card"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED)
        pg.evaluate("localStorage.setItem('pw.calc', JSON.stringify({ scale: 1 }))")   # pw-v7o: Part B at Blipwork's 1.0x
        pg.reload(); ready(pg)
        open_note(pg)
        kids = pg.evaluate("[...document.getElementById('tray').children].map((e) => e.id || e.className)")
        tb, rb, tray = rect(pg, "#toolsBtn"), rect(pg, "#redoBtn"), rect(pg, "#tray")
        check("the tools button exists: class 'ib tool', aria-label and title 'Calculator'",
              tb is not None and pg.get_attribute("#toolsBtn", "aria-label") == "Calculator" and pg.get_attribute("#toolsBtn", "title") == "Calculator"
              and "ib" in pg.get_attribute("#toolsBtn", "class") and "tool" in pg.get_attribute("#toolsBtn", "class"), tb)
        cl = rect(pg, "#tray .colours")   # pw-v7e: the button moved to the top (her palm kept opening it at the bottom)
        check("it is the FIRST thing in the tray, above the colours, at the very top", kids[0] == "toolsBtn" and tb["t"] - tray["t"] < 30 and cl["t"] >= tb["b"] - 1, [kids, tb, cl, tray])
        check("the old empty slot is gone", pg.locator("#tray div.slot").count() == 0)
        check("it holds a calculator icon (an svg with a rect and six dots)", pg.evaluate("() => { const s = document.querySelector('#toolsBtn svg'); return !!s && !!s.querySelector('rect') && s.querySelector('path[d*=\"13h.01\"]') !== null; }"))
        check("before the first tap there is no card, and the button is not 'on'", pg.locator("#calcCard").count() == 0 and "on" not in pg.get_attribute("#toolsBtn", "class").split())

        pg.click("#toolsBtn"); pg.wait_for_timeout(150)
        c, tray = rect(pg, "#calcCard"), rect(pg, "#tray")
        check("a tap shows #calcCard; the button lights up (.on, aria-pressed true)", c and c["shown"] and "on" in pg.get_attribute("#toolsBtn", "class").split() and pg.get_attribute("#toolsBtn", "aria-pressed") == "true", c)
        check("tray on the RIGHT: the card's right edge is 12 px left of the tray", c and abs(c["r"] - (tray["l"] - 12)) <= 1, [c, tray])
        bar = rect(pg, "#noteBar")
        check("the card's top is 12 px under the note bar (pw-v7e review: never over the More button)", c and abs(c["t"] - min(bar["b"] + 12, 800 - c["h"])) <= 1.5, [c, bar])
        check("the card is inside the viewport", c and c["l"] >= 0 and c["t"] >= 0 and c["r"] <= 1280 and c["b"] <= 800, c)
        cs = pg.evaluate("() => { const s = getComputedStyle(document.getElementById('calcCard')); return [s.position, s.zIndex, document.querySelector('#calcCard .calc-wrap').getBoundingClientRect().width]; }")
        check("position fixed, z-index 45, the .calc-wrap gives the width (344 px)", cs[0] == "fixed" and cs[1] == "45" and abs(cs[2] - 344) <= 1, cs)
        check("the head reads 'CASIO fx-991ZA Plus II' and has a ✕ labelled 'Close calculator'",
              pg.inner_text("#calcCard .calcHead").replace("\n", " ").startswith("CASIO fx-991ZA Plus II")
              and pg.get_attribute("#calcCard .calcClose", "aria-label") == "Close calculator", pg.inner_text("#calcCard .calcHead"))
        check("the card is not a role=dialog (that would stop the S Pen button flip)", pg.evaluate("() => !document.querySelector('#calcCard[role=dialog], #calcCard [role=dialog]')"))
        pg.screenshot(path=str(SHOTS / "right-tray-card.png"))

        # the keys work through the rendered buttons
        for kid in ("d2", "plus", "d3", "eq"): key(pg, kid)
        check("2 + 3 = shows 5 on the LCD", pg.evaluate(LCD) == "5", pg.evaluate(LCD))

        # close and reopen: the LCD keeps its 5 and the calculator was mounted only once
        pg.click("#calcCard .calcClose"); pg.wait_for_timeout(80)
        check("the ✕ closes it (hidden, still in the page) and the button is not 'on'", pg.evaluate("document.getElementById('calcCard').hidden") and "on" not in pg.get_attribute("#toolsBtn", "class").split())
        n_before = pg.locator(".calc-lcd").count()
        pg.click("#toolsBtn"); pg.wait_for_timeout(120)
        check("reopened with the tray button: the LCD still shows 5 (built once, never rebuilt)", pg.evaluate(LCD) == "5" and pg.locator(".calc-lcd").count() == n_before == 1, [pg.evaluate(LCD), n_before])
        pg.click("#toolsBtn"); pg.wait_for_timeout(80)
        check("the tray button toggles it shut", pg.evaluate("document.getElementById('calcCard').hidden"))
        pg.click("#toolsBtn"); pg.wait_for_timeout(120)
        check("and open again, the LCD still 5", pg.evaluate(LCD) == "5")

        # a stroke NEXT to the open card lands under the pointer; a press on a key draws nothing
        c = rect(pg, "#calcCard")
        sx, sy = c["l"] - 190, c["t"] + 140
        ok, got = stroke_lands(pg, sx, sy)
        check("with the card open, a mouse stroke beside it lands within 1.5 px of the pointer", ok, [sx, sy, got])
        check("the card stayed open after drawing next to it (a tap or stroke outside does not close it)", not pg.evaluate("document.getElementById('calcCard').hidden"))
        before = pg.evaluate(STROKES)
        kx, ky = center(rect(pg, '#calcCard [data-keyid="d7"]'))
        pg.mouse.move(kx, ky); pg.mouse.down(); pg.mouse.move(kx + 6, ky + 4, steps=4); pg.mouse.move(kx + 20, ky + 10, steps=4); pg.mouse.up(); pg.wait_for_timeout(100)
        check("a pointer-down and move on a calculator key draws NO stroke on the page", pg.evaluate(STROKES) == before, [before, pg.evaluate(STROKES)])
        pg.mouse.move(kx, ky); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(60)
        check("(a plain press on a key still types: 7 on the LCD line)", "7" in pg.evaluate("() => document.querySelector('#calcCard .calc-lcd').textContent"))

        # the S Pen button = contextmenu: swallowed inside the card
        r = pg.evaluate("""() => { const k = document.querySelector('#calcCard [data-keyid="d1"]'), t0 = window.__pw.ink.tool().tool;
          const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, button: 2 }); k.dispatchEvent(ev);
          return { prevented: ev.defaultPrevented, tool: window.__pw.ink.tool().tool, t0, menuHidden: document.getElementById('menu').hidden }; }""")
        check("a contextmenu on a key is swallowed (prevented, no menu, the tool unchanged)", r["prevented"] and r["menuHidden"] and r["tool"] == r["t0"], r)

        # dragging the head
        pg.click("#calcCard .calcClose"); pg.click("#toolsBtn"); pg.wait_for_timeout(100)
        c0 = rect(pg, "#calcCard"); hx, hy = center(rect(pg, "#calcCard .calc-name"))
        # pw-v7e: the card now opens at the top (y 0), so the drag goes down-left (it was up-left, which now clamps at the top)
        pg.mouse.move(hx, hy); pg.mouse.down(); pg.mouse.move(hx - 120, hy + 60, steps=6); pg.mouse.move(hx - 300, hy + 150, steps=6); pg.mouse.up(); pg.wait_for_timeout(80)
        c1 = rect(pg, "#calcCard")
        check("dragging the head moves the card by the drag (-300, +150)", abs((c1["l"] - c0["l"]) + 300) <= 1.5 and abs((c1["t"] - c0["t"]) - 150) <= 1.5, [c0, c1])
        # drag far off: clamped inside the viewport
        hx, hy = center(rect(pg, "#calcCard .calc-name"))
        pg.mouse.move(hx, hy); pg.mouse.down(); pg.mouse.move(hx + 2000, hy + 2000, steps=8); pg.mouse.up(); pg.wait_for_timeout(80)
        c2 = rect(pg, "#calcCard")
        check("dragged far past the corner: clamped inside the viewport", c2["r"] <= 1280.5 and c2["b"] <= 800.5 and c2["l"] >= -0.5, c2)
        pg.mouse.move(*center(rect(pg, "#calcCard .calc-name"))); pg.mouse.down(); pg.mouse.move(600, 300, steps=8); pg.mouse.up(); pg.wait_for_timeout(60)
        c3 = rect(pg, "#calcCard")
        pg.click("#calcCard .calcClose"); pg.click("#toolsBtn"); pg.wait_for_timeout(100)
        c4 = rect(pg, "#calcCard")
        check("the dragged place is kept over a close and reopen (this session)", abs(c4["l"] - c3["l"]) <= 1 and abs(c4["t"] - c3["t"]) <= 1, [c3, c4])
        check("the head drag did not draw on the page or close the card", not pg.evaluate("document.getElementById('calcCard').hidden"))
        saved = pg.evaluate("() => JSON.parse(localStorage.getItem('pw.calc'))")
        check("pw-v7o: the dragged place is remembered on this device (pw.calc), the size with it, nothing else stored",
              saved and saved.get("scale") == 1 and abs(saved.get("left", -99) - c3["l"]) <= 1 and abs(saved.get("top", -99) - c3["t"]) <= 1
              and pg.evaluate("() => Object.keys(localStorage).filter((k) => /calc/i.test(k))") == ["pw.calc"], [saved, c3])

        # a flip puts it beside the tray again (the card is open and was dragged)
        menu_flip(pg)
        check("set-up: the tray is now on the left", pg.evaluate("document.body.classList.contains('trayLeft')"))
        check("pw-v7o: the flip drops the remembered place and keeps the size", pg.evaluate("() => JSON.parse(localStorage.getItem('pw.calc'))") == {"scale": 1},
              pg.evaluate("() => localStorage.getItem('pw.calc')"))
        c, tray = rect(pg, "#calcCard"), rect(pg, "#tray")
        bar = rect(pg, "#noteBar")
        check("tray on the LEFT, card open and dragged: the flip puts it 12 px right of the tray, 12 px under the note bar (pw-v7e)",
              abs(c["l"] - (tray["r"] + 12)) <= 1 and abs(c["t"] - min(bar["b"] + 12, 800 - c["h"])) <= 1.5, [c, tray, bar])
        pg.screenshot(path=str(SHOTS / "left-tray-card.png"))
        pg.click("#calcCard .calcClose"); pg.wait_for_timeout(50); pg.click("#toolsBtn"); pg.wait_for_timeout(120)
        c, tray = rect(pg, "#calcCard"), rect(pg, "#tray")
        check("tray on the left, closed and opened again: still beside the tray", abs(c["l"] - (tray["r"] + 12)) <= 1, [c, tray])
        check("the LCD still shows what it showed (the calculator was never rebuilt through all of this)", pg.locator(".calc-lcd").count() == 1)
        ok, got = stroke_lands(pg, c["r"] + 60, c["t"] + 120)
        check("tray left, card open: a stroke beside the card lands within 1.5 px of the pointer", ok, got)
        menu_flip(pg)
        c, tray = rect(pg, "#calcCard"), rect(pg, "#tray")
        check("flipped back to the right: the card follows, 12 px left of the tray", abs(c["r"] - (tray["l"] - 12)) <= 1, [c, tray])
        # Fable review: leaving the note puts the calculator away; opening a note again brings it back on a tap, LCD kept
        pg.click("#backBtn"); pg.wait_for_timeout(200)
        check("back to the folder view: the card is hidden", pg.evaluate("document.getElementById('calcCard').hidden"))
        open_note(pg)
        check("a note opened again: the card stays hidden until the button is tapped", pg.evaluate("document.getElementById('calcCard').hidden"))
        pg.click("#toolsBtn"); pg.wait_for_timeout(100)
        check("tapped: the card is back, the same card (never rebuilt)", not pg.evaluate("document.getElementById('calcCard').hidden") and pg.locator("#calcCard").count() == 1)

        # the pen panel and the desk
        group[0] = "B. panels and the desk"
        pg.click("#tool-pen"); pg.wait_for_timeout(60)
        if pg.locator("#toolPanel").is_hidden(): pg.click("#tool-pen"); pg.wait_for_timeout(60)
        check("set-up: the pen panel is open", not pg.evaluate("document.getElementById('toolPanel').hidden"))
        kx, ky = center(rect(pg, '#calcCard [data-keyid="ac"]'))
        pg.mouse.click(kx, ky); pg.wait_for_timeout(100)
        check("a tap on a calculator key does NOT close the pen panel", not pg.evaluate("document.getElementById('toolPanel').hidden"))
        hx, hy = center(rect(pg, "#calcCard .calc-name"))
        pg.mouse.click(hx, hy); pg.wait_for_timeout(100)
        check("nor does a tap on the card's head", not pg.evaluate("document.getElementById('toolPanel').hidden"))
        check("the card is still open after those taps", not pg.evaluate("document.getElementById('calcCard').hidden"))
        dx, dy = rect(pg, "#calcCard")["l"] - 250, 300
        pg.mouse.click(dx, dy); pg.wait_for_timeout(100)
        check("a tap on the desk still closes the pen panel, as before", pg.evaluate("document.getElementById('toolPanel').hidden"))
        check("and the card is NOT closed by a tap on the desk", not pg.evaluate("document.getElementById('calcCard').hidden"))
        # the colour picker (another document-level closer)
        pg.click("#tray .spec"); pg.wait_for_timeout(80)
        picker_open = not pg.evaluate("document.getElementById('specPicker').hidden")
        pg.mouse.click(*center(rect(pg, '#calcCard [data-keyid="ac"]'))); pg.wait_for_timeout(80)
        check("the colour picker: a tap on a key does not close it", picker_open and not pg.evaluate("document.getElementById('specPicker').hidden"), picker_open)
        pg.mouse.click(dx, dy); pg.wait_for_timeout(80)
        check("the colour picker: a tap on the desk closes it as before", pg.evaluate("document.getElementById('specPicker').hidden"))
        # the app menu (the third closer): the note menu stays open under a tap inside the card
        # pw-v7e review (Fable): the card opens UNDER the note bar, so the More button is never covered and is tapped for real
        cov = pg.evaluate("() => { const m = document.getElementById('noteMore').getBoundingClientRect(), c = document.getElementById('calcCard').getBoundingClientRect(); return m.left < c.right && c.left < m.right && m.top < c.bottom && c.top < m.bottom; }")
        check("pw-v7e review: the open card does NOT lie over the note's More button", not cov, cov)
        pg.click("#noteMore"); pg.wait_for_selector("#menu:not([hidden])")
        # the open menu drops down over the card's top keys (AC is under it), so the tap goes to "=", below the menu
        pg.mouse.click(*center(rect(pg, '#calcCard [data-keyid="eq"]'))); pg.wait_for_timeout(80)
        menu_kept = not pg.evaluate("document.getElementById('menu').hidden")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(50)
        check("the note menu: a tap inside the card does not close it (Escape does)", menu_kept and pg.evaluate("document.getElementById('menu').hidden"), menu_kept)
        # the S Pen button on the desk still flips the tool while the card is open (the card is no overlay)
        r = pg.evaluate("""() => { const t0 = window.__pw.ink.tool().tool, d = document.getElementById('desk'), b = d.getBoundingClientRect();
          d.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, button: 2, clientX: b.left + 100, clientY: b.top + 100 }));
          return [t0, window.__pw.ink.tool().tool]; }""")
        check("(information) the S Pen button's contextmenu on the desk with the card open: tool before/after", True, r)
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ C: the size (pw-v7o, round 8)
        group[0] = "C. size"
        SC = "() => +document.getElementById('calcCard').style.getPropertyValue('--calc-s')"
        STORED = "() => JSON.parse(localStorage.getItem('pw.calc'))"
        def grip_drag(pg, dx, dy):
            gx, gy = center(rect(pg, "#calcCard .calcGrip"))
            pg.mouse.move(gx, gy); pg.mouse.down()
            pg.mouse.move(gx + dx / 2, gy + dy / 2, steps=5); pg.mouse.move(gx + dx, gy + dy, steps=5)
            pg.mouse.up(); pg.wait_for_timeout(80)
        def fresh(vw, vh, stored=None, **kw):
            ctx = b.new_context(viewport={"width": vw, "height": vh}, **kw)
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(LOCAL); ready(pg); pg.evaluate(SEED)
            if stored is not None: pg.evaluate("(v) => localStorage.setItem('pw.calc', JSON.stringify(v))", stored)
            pg.reload(); ready(pg); open_note(pg)
            return ctx, pg, errs
        inside = lambda c, vw, vh: c["l"] >= -0.5 and c["t"] >= -0.5 and c["r"] <= vw + 0.5 and c["b"] <= vh + 0.5

        # C1: 1280 x 1000, nothing stored: the default
        ctx, pg, errs = fresh(1280, 1000)
        pg.click("#toolsBtn"); pg.wait_for_timeout(150)
        c, tray, bar, s = rect(pg, "#calcCard"), rect(pg, "#tray"), rect(pg, "#noteBar"), pg.evaluate(SC)
        print(f"MEASURED default on 1280 x 1000: scale {s}, card {c['w']:.1f} x {c['h']:.1f} at ({c['l']:.0f}, {c['t']:.0f})")
        check("1280 px screen, nothing stored: the card opens at 1.6x, 550.4 px wide (344 x 1.6)", abs(s - 1.6) < 1e-9 and abs(c["w"] - 550.4) <= 0.5, [s, c])
        check("... beside the tray (12 px) and 12 px under the note bar, all on screen",
              abs(c["r"] - (tray["l"] - 12)) <= 1 and abs(c["t"] - (bar["b"] + 12)) <= 1.5 and inside(c, 1280, 1000), [c, tray, bar])
        z = pg.evaluate("""() => { const w = document.querySelector('#calcCard .calc-wrap'), out = { zoom: getComputedStyle(w).zoom, transforms: [] };
          for (let e = document.querySelector('#calcCard .lcd-res'); e; e = e.parentElement) { const t = getComputedStyle(e).transform; if (t && t !== 'none') out.transforms.push(e.className || e.tagName); }
          return out; }""")
        check("scaled by CSS zoom on .calc-wrap (1.6) with no transform anywhere from the LCD up (laid out again, not a blown-up picture)", z["zoom"] == "1.6" and z["transforms"] == [], z)
        lcd16 = rect(pg, "#calcCard .calc-lcd")
        g = rect(pg, "#calcCard .calcGrip")
        check("the corner handle: 20 x 20 px, in the card's bottom-right corner (2 px in)",
              g and abs(g["w"] - 20) <= 0.5 and abs(g["h"] - 20) <= 0.5 and abs(c["r"] - g["r"] - 2) <= 0.5 and abs(c["b"] - g["b"] - 2) <= 0.5, [g, c])
        gs = pg.evaluate("() => { const s = getComputedStyle(document.querySelector('#calcCard .calcGrip')); return [s.borderTopColor, s.backgroundColor, s.borderRadius, s.touchAction]; }")
        check("... the selection corner's look (white, ringed in the selection blue, round) and it gives up touch scrolling", gs[0] == "rgb(47, 75, 184)" and gs[1] == "rgb(255, 255, 255)" and gs[2] == "50%" and gs[3] == "none", gs)
        pg.screenshot(path=str(SHOTS / "size-1.6x.png"))
        # the handle: smaller, proportions kept, the top-left corner stays put
        grip_drag(pg, -150, -150)
        c2, s2 = rect(pg, "#calcCard"), pg.evaluate(SC)
        check("dragging the handle in (-150, -150) makes it smaller (between 1.0x and 1.6x), 344 px x scale wide",
              1 < s2 < 1.6 and abs(c2["w"] - 344 * s2) <= 0.5, [s2, c2])
        check("... the top-left corner stays where it was", abs(c2["l"] - c["l"]) <= 1 and abs(c2["t"] - c["t"]) <= 1, [c, c2])
        check("... the proportions kept (height / width within 1% of the 1.6x card's)", abs((c2["h"] / c2["w"]) / (c["h"] / c["w"]) - 1) < 0.01, [c["h"] / c["w"], c2["h"] / c2["w"]])
        check("... and the drag did not draw on the page or close the card", pg.evaluate(STROKES) == [] and not pg.evaluate("document.getElementById('calcCard').hidden"))
        grip_drag(pg, -3000, -3000)
        c1, s1 = rect(pg, "#calcCard"), pg.evaluate(SC)
        check("dragged far in: it stops at 1.0x (344 px wide, Blipwork's size)", s1 == 1 and abs(c1["w"] - 344) <= 0.5, [s1, c1])
        lcd10 = rect(pg, "#calcCard .calc-lcd")
        check("the LCD at 1.6x is 1.6 times the LCD at 1.0x (both sides, within 1.5 px: its 2 px border rounds)", abs(lcd16["w"] - 1.6 * lcd10["w"]) <= 1.5 and abs(lcd16["h"] - 1.6 * lcd10["h"]) <= 1.5, [lcd16, lcd10])
        check("proportions at 1.0x: within 1% of the 1.6x card's", abs((c1["h"] / c1["w"]) / (c["h"] / c["w"]) - 1) < 0.01, [c1["w"], c1["h"]])
        grip_drag(pg, 3000, 3000)
        cb, sb = rect(pg, "#calcCard"), pg.evaluate(SC)
        print(f"MEASURED biggest that fits 1280 x 1000: scale {sb:.3f}, card {cb['w']:.1f} x {cb['h']:.1f}")
        check("dragged far out on a 1000 px tall screen: as big as fits (below 2.5x, at least 99% of the height) and still all on screen", 1.6 < sb < 2.5 and inside(cb, 1280, 1000) and cb["h"] >= 990, [sb, cb])
        # a mid size and a dragged place, then a reload
        grip_drag(pg, -250, -250)
        hx, hy = center(rect(pg, "#calcCard .calc-name"))
        pg.mouse.move(hx, hy); pg.mouse.down(); pg.mouse.move(hx - 200, hy + 20, steps=6); pg.mouse.move(hx - 400, hy + 40, steps=6); pg.mouse.up(); pg.wait_for_timeout(80)
        cm, sm, st = rect(pg, "#calcCard"), pg.evaluate(SC), pg.evaluate(STORED)
        check("set-up: a mid size and a dragged place, stored in pw.calc", 1 < sm < sb and st and abs(st["scale"] - sm) < 0.001 and abs(st["left"] - cm["l"]) <= 1 and abs(st["top"] - cm["t"]) <= 1, [sm, cm, st])
        pg.reload(); ready(pg); pg.wait_for_timeout(300)
        if pg.evaluate("document.getElementById('noteView').hidden"): open_note(pg)   # the app may reopen the last note itself
        pg.click("#toolsBtn"); pg.wait_for_timeout(150)
        cr_, sr = rect(pg, "#calcCard"), pg.evaluate(SC)
        print(f"MEASURED after a reload: scale {sr:.3f} (was {sm:.3f}), card at ({cr_['l']:.0f}, {cr_['t']:.0f}) (was ({cm['l']:.0f}, {cm['t']:.0f}))")
        check("a reload brings the size and the place back", abs(sr - sm) < 0.001 and abs(cr_["l"] - cm["l"]) <= 1 and abs(cr_["t"] - cm["t"]) <= 1 and abs(cr_["w"] - cm["w"]) <= 0.5, [sm, sr, cm, cr_])
        hx, hy = center(rect(pg, "#calcCard .calc-name"))
        pg.mouse.move(hx, hy); pg.mouse.down(); pg.mouse.move(hx + 60, hy + 25, steps=6); pg.mouse.move(hx + 120, hy + 50, steps=6); pg.mouse.up(); pg.wait_for_timeout(80)
        cd = rect(pg, "#calcCard")
        check("the head drag at this size moves the card by the drag (+120, +50)", abs(cd["l"] - cr_["l"] - 120) <= 1.5 and abs(cd["t"] - cr_["t"] - 50) <= 1.5, [cr_, cd])
        # a smaller screen now: made smaller to fit, her size kept for when the screen is big again
        pg.set_viewport_size({"width": 1280, "height": 700}); pg.wait_for_timeout(150)
        cs_, ss = rect(pg, "#calcCard"), pg.evaluate(SC)
        check("the screen made shorter (700 px): the card shrinks to fit, all on screen", ss < sm and inside(cs_, 1280, 700), [ss, cs_])
        check("... and her size is still the stored one", abs(pg.evaluate(STORED)["scale"] - sm) < 0.001, pg.evaluate(STORED))
        pg.set_viewport_size({"width": 1280, "height": 1000}); pg.wait_for_timeout(150)
        check("the screen tall again: her size is back", abs(pg.evaluate(SC) - sm) < 0.001, pg.evaluate(SC))
        check("no page errors (1280 x 1000)", not errs, errs)
        ctx.close()

        # C1b: 1280 x 800, nothing stored: the default keeps under the note bar, as big as the room there allows
        ctx, pg, errs = fresh(1280, 800)
        pg.click("#toolsBtn"); pg.wait_for_timeout(150)
        c, bar, s = rect(pg, "#calcCard"), rect(pg, "#noteBar"), pg.evaluate(SC)
        print(f"MEASURED default on 1280 x 800: scale {s:.3f}, card {c['w']:.1f} x {c['h']:.1f}")
        check("1280 x 800, nothing stored: bigger than 1.0x, no more than 1.6x, under the note bar and all on screen",
              1 < s <= 1.6 and abs(c["t"] - (bar["b"] + 12)) <= 1.5 and inside(c, 1280, 800), [s, c, bar])
        ctx.close()

        # C2: 1600 x 1400 (room for 2.5x): the upper limit, the keys, "=", a long input, a stroke beside
        ctx, pg, errs = fresh(1600, 1400)
        pg.click("#toolsBtn"); pg.wait_for_timeout(150)
        check("1600 px screen, nothing stored: 1.6x", abs(pg.evaluate(SC) - 1.6) < 1e-9, pg.evaluate(SC))
        grip_drag(pg, 3000, 3000)
        c, s = rect(pg, "#calcCard"), pg.evaluate(SC)
        print(f"MEASURED at the top limit: scale {s}, card {c['w']:.1f} x {c['h']:.1f}")
        check("dragged far out: it stops at 2.5x (860 px wide), all on screen", s == 2.5 and abs(c["w"] - 860) <= 0.5 and inside(c, 1600, 1400), [s, c])
        tray = rect(pg, "#tray")
        check("... grown beside the tray it slid left, never over the tray (its right edge 12 px left of the tray)", abs(c["r"] - (tray["l"] - 12)) <= 1, [c, tray])
        check("2.5x is remembered", pg.evaluate(STORED)["scale"] == 2.5, pg.evaluate(STORED))
        miss = pg.evaluate("""() => [...document.querySelectorAll('#calcCard [data-keyid]')].filter((k) => {
            const r = k.getBoundingClientRect(), e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return !e || !e.closest('[data-keyid]') || e.closest('[data-keyid]') !== k; }).map((k) => k.dataset.keyid)""")
        nkeys = pg.locator("#calcCard [data-keyid]").count()
        check(f"at 2.5x the centre of every key ({nkeys}) hits that key", nkeys >= 50 and miss == [], miss)
        for kid in ("ac", "d2", "mult", "d4"):
            pg.mouse.click(*center(rect(pg, f'#calcCard [data-keyid="{kid}"]'))); pg.wait_for_timeout(30)
        ex, ey = center(rect(pg, '#calcCard [data-keyid="eq"]'))
        hit = pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); const k = e && e.closest('[data-keyid]'); return k ? k.dataset.keyid : null; }", [ex, ey])
        pg.mouse.click(ex, ey); pg.wait_for_timeout(60)
        check('a tap on "=" at 2.5x hits "=": 2 x 4 = shows 8', hit == "eq" and pg.evaluate(LCD) == "8", [hit, pg.evaluate(LCD)])
        # a long input: the copied calculator scrolls its entry line; the cursor stays in view at 2.5x
        CUR = """() => { const ex = document.querySelector('#calcCard .lcd-expr'), c = ex && ex.querySelector('.calc-cursor'), m = document.querySelector('#calcCard .lcd-lmark');
          if (!c) return null; const a = ex.getBoundingClientRect(), b = c.getBoundingClientRect(), mr = m.getBoundingClientRect();
          return { inView: b.left >= a.left - 0.5 && b.right <= a.right + 0.5, clearOfMark: m.hidden || b.left >= mr.right - 0.5, mark: !m.hidden, sl: ex.scrollLeft }; }"""
        pg.mouse.click(*center(rect(pg, '#calcCard [data-keyid="ac"]')))
        for k in range(60): pg.mouse.click(*center(rect(pg, f'#calcCard [data-keyid="d{1 + k % 9}"]')))
        pg.wait_for_timeout(60)
        a = pg.evaluate(CUR)
        lefts = []
        for k in range(30):
            pg.mouse.click(*center(rect(pg, '#calcCard [data-keyid="left"]'))); lefts.append(pg.evaluate(CUR))
        bad = [i for i, v in enumerate(lefts) if not (v and v["inView"] and v["clearOfMark"])]
        check("a 60-digit input at 2.5x: the cursor is in view at the end (the line scrolled, the marker shown)", a and a["inView"] and a["mark"], a)
        check("... and stays in view, clear of the marker, through 30 steps left", bad == [], [bad, lefts[-1]])
        lcd = rect(pg, "#calcCard .calc-lcd")
        pg.screenshot(path=str(SHOTS / "lcd-2.5x.png"), clip={"x": lcd["l"], "y": lcd["t"], "width": lcd["w"], "height": lcd["h"]})
        pg.screenshot(path=str(SHOTS / "size-2.5x.png"))
        c = rect(pg, "#calcCard")
        sx, sy = (c["l"] - 190, c["t"] + 140) if c["l"] > 400 else (c["r"] + 60, c["t"] + 140)
        ok, got = stroke_lands(pg, sx, sy)
        check("with the card open at 2.5x, a mouse stroke beside it lands within 1.5 px of the pointer", ok, [sx, sy, c, got])
        check("the card stayed open, never rebuilt", not pg.evaluate("document.getElementById('calcCard').hidden") and pg.locator(".calc-lcd").count() == 1)
        check("no page errors (1600 x 1400)", not errs, errs)
        ctx.close()

        # C3: a 375 px phone with 2.5x and a far-right place stored: never off-screen
        ctx, pg, errs = fresh(375, 812, {"scale": 2.5, "left": 900, "top": 500}, has_touch=True, is_mobile=True)
        pg.evaluate("() => import('./js/calcpanel.js').then((m) => m.openCalc())"); pg.wait_for_timeout(150)
        c, s = rect(pg, "#calcCard"), pg.evaluate(SC)
        print(f"MEASURED on a 375 x 812 phone with 2.5x stored: scale {s:.3f}, card {c['w']:.1f} x {c['h']:.1f} at ({c['l']:.0f}, {c['t']:.0f})")
        check("375 px phone, 2.5x and a far place stored: the card is all on screen (no wider than the phone)", c["shown"] and inside(c, 375, 812) and s <= 375 / 344 + 1e-9, [s, c])
        check("no page errors (phone, stored size)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ B: the phone has no tray, so no calculator button
        group[0] = "B. phone"
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        check("phone: no tools button on screen (the whole tray is hidden)", pg.evaluate("() => { const e = document.getElementById('toolsBtn'); return !e || e.getBoundingClientRect().width === 0; }"))
        check("phone: no card", pg.locator("#calcCard").count() == 0 or pg.evaluate("document.getElementById('calcCard').hidden"))
        check("no page errors (phone)", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate(); bsrv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:500]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
