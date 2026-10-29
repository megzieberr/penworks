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
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
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
        check("the card's top is the tray's top (clamped inside the viewport) (pw-v7e: it was bottom to bottom)", c and abs(c["t"] - min(tray["t"], 800 - c["h"])) <= 1.5, [c, tray])
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
        check("nothing about the place is saved (no calc key in localStorage)", pg.evaluate("() => Object.keys(localStorage).filter((k) => /calc/i.test(k))") == [])

        # a flip puts it beside the tray again (the card is open and was dragged)
        menu_flip(pg)
        check("set-up: the tray is now on the left", pg.evaluate("document.body.classList.contains('trayLeft')"))
        c, tray = rect(pg, "#calcCard"), rect(pg, "#tray")
        check("tray on the LEFT, card open and dragged: the flip puts it 12 px right of the tray, top-aligned (pw-v7e)",
              abs(c["l"] - (tray["r"] + 12)) <= 1 and abs(c["t"] - min(tray["t"], 800 - c["h"])) <= 1.5, [c, tray])
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
        # pw-v7e: the card now opens level with the tray's top (y 0), so at its own place it lies over the note's More button;
        # the button is clicked through the DOM here (this check is about the closers, not the place). Flagged to Fable.
        cov = pg.evaluate("() => { const m = document.getElementById('noteMore').getBoundingClientRect(), c = document.getElementById('calcCard').getBoundingClientRect(); return m.left < c.right && c.left < m.right && m.top < c.bottom && c.top < m.bottom; }")
        check("(information) pw-v7e: the open card lies over the note's More button (top bar)", True, cov)
        pg.evaluate("document.getElementById('noteMore').click()"); pg.wait_for_selector("#menu:not([hidden])")
        pg.mouse.click(*center(rect(pg, '#calcCard [data-keyid="ac"]'))); pg.wait_for_timeout(80)
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
