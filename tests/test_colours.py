# PenWorks colour strip checks: hold and drag to reorder her 13 colours, and the spare slot's honeycomb picker.
# Run: python tests/test_colours.py              (local mode only: ?local=1, Supabase is never touched)
#      add --shots <folder> for a lifted swatch and the open honeycomb with a cell selected
# Headless Playwright (Python), same style as tests/test_u2a.py. The mouse stands in for the finger and the
# S Pen: the strip only listens to pointer events, which are the same for all three.
import sys, subprocess, time, pathlib, json, colorsys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8777
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
if SHOTS: SHOTS.mkdir(parents=True, exist_ok=True)

HERS = [["#2CB05F", "Green"], ["#37D366", "Light green"], ["#0D0DFF", "Blue"], ["#FF0C84", "Pink"], ["#FF7043", "Orange"],
        ["#A83AFF", "Purple"], ["#FFC107", "Amber"], ["#00BCD5", "Cyan"], ["#04878F", "Teal"], ["#FF00FF", "Magenta"],
        ["#FF3636", "Red"], ["#000000", "Black"], ["#808080", "Grey"]]
HEXES = [c for c, _ in HERS]

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-25T10:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Colours', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Colour test', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [{ id: 'p1', note_id: 'n1', position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t }] }));
}"""
STRIP_JS = """() => [...document.querySelectorAll('#tray .colours > *')].map(e => ({ cls: e.className, colour: e.dataset.colour,
  name: e.getAttribute('aria-label'), title: e.getAttribute('title') }))"""
SW_JS = "() => [...document.querySelectorAll('#tray .colours .sw')].map(s => [s.dataset.colour, s.getAttribute('aria-label')])"
SAVED_JS = "() => JSON.parse(localStorage.getItem('pw.tools') || '{}')"
MID_JS = "() => getComputedStyle(document.querySelector('#tray .spec .mid')).backgroundColor"
PREV_JS = "() => getComputedStyle(document.querySelector('#specPicker .prev')).backgroundColor"
CELLS_JS = """() => [...document.querySelectorAll('#specPicker [data-cell]')].map(c => { const r = c.getBoundingClientRect();
  return { id: c.dataset.cell, cls: c.getAttribute('class').split(' ')[0], colour: c.dataset.colour, x: r.x, y: r.y, w: r.width, h: r.height }; })"""
SEL_JS = """() => { const s = document.querySelector('#specPicker .hsel'), on = document.querySelectorAll('#specPicker [data-cell].on');
  if (!s || s.getAttribute('display') === 'none') return null; const r = s.getBoundingClientRect();
  return { cx: r.x + r.width / 2, cy: r.y + r.height / 2, w: r.width, on: [...on].map(c => c.dataset.cell) }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def open_note(pg):
    if not pg.locator("#noteView").is_visible():          # after a reload the app may reopen the note itself
        pg.locator(".nrow", has_text="Colour test").first.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(80)
def tray(pg): return pg.evaluate("window.__pw.tray()")
def centre(pg, sel):
    b = pg.locator(sel).first.bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
def sw_sel(c): return f"#tray .sw[data-colour='{c}']"
def pitch(pg):
    a, b = pg.locator("#tray .colours .sw").nth(0).bounding_box(), pg.locator("#tray .colours .sw").nth(1).bounding_box()
    return b["y"] - a["y"]
def hold(pg, sel, ms=450):
    x, y = centre(pg, sel); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(ms); return x, y
def rgb(h): n = int(h[1:], 16); return f"rgb({n >> 16 & 255}, {n >> 8 & 255}, {n & 255})"
def hls(h):                                               # (hue, lightness, saturation) as 0..1, HSL as in CSS
    return colorsys.rgb_to_hls(*(int(h[k:k + 2], 16) / 255 for k in (1, 3, 5)))
def sel_on(pg, cid):                                     # the outline centred on that cell, about its size, only it marked on
    s = pg.evaluate(SEL_JS)
    c = pg.locator(f"#specPicker [data-cell='{cid}']").bounding_box()
    return bool(s) and s["on"] == [cid] and abs(s["cx"] - (c["x"] + c["width"] / 2)) < 1.5 and abs(s["cy"] - (c["y"] + c["height"] / 2)) < 1.5 and s["w"] >= c["width"] - 3   # Chrome pads the cell box for its stroke
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def draw(pg, y):
    b = pg.locator("#stack .sheet[data-index='1']").bounding_box(); z = zoom(pg)
    pg.mouse.move(b["x"] + 100 * z, b["y"] + y * z); pg.mouse.down()
    for k in range(1, 5): pg.mouse.move(b["x"] + (100 + 75 * k) * z, b["y"] + y * z, steps=5)
    pg.mouse.up(); pg.wait_for_timeout(40)
def last_stroke(pg): return pg.evaluate("window.__pw.ink.strokesOf('p1').slice(-1)[0]")
def picker_open(pg): return pg.locator("#specPicker").is_visible()
def fresh(b, **kw):
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, **kw)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg)
    return ctx, pg, errs

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx, pg, errs = fresh(b)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg)

        # ------------------------------------------------------------ the strip
        group[0] = "strip"
        strip = pg.evaluate(STRIP_JS)
        check("14 slots in the strip: her 13 and the spare one", len(strip) == 14 and sum(s["cls"].split()[0] == "sw" for s in strip) == 13, [s["cls"] for s in strip])
        check("the spare slot is last (under Grey), named Any colour", strip[-1]["cls"].split()[0] == "spec" and strip[-2]["colour"] == "#808080"
              and strip[-1]["name"] == "Any colour", strip[-2:])
        spec_bg = pg.evaluate("getComputedStyle(document.querySelector('#tray .spec')).backgroundImage")
        check("the spare slot has a rainbow ring (conic gradient)", spec_bg.startswith("conic-gradient"), spec_bg)
        check("its middle is white before she has ever picked", pg.evaluate(MID_JS) == "rgb(255, 255, 255)" and tray(pg)["spec"] is None, pg.evaluate(MID_JS))
        gap = pg.evaluate("""(() => { const s = [...document.querySelectorAll('#tray .colours > *')], a = s[11].getBoundingClientRect(),
          g = s[12].getBoundingClientRect(), x = s[13].getBoundingClientRect(); return [g.top - a.bottom, x.top - g.bottom]; })()""")
        check("a small gap sets it apart (wider than between colours)", gap[1] > gap[0], gap)
        check("her 13 in her order by default, with her names", pg.evaluate(SW_JS) == HERS, pg.evaluate(SW_JS))
        check("names also on the title", all(s["title"] == s["name"] for s in strip[:13]))
        check("default: ONE colour, Black, for the pen and the highlighter (round 1)", tray(pg)["pen"]["colour"] == "#000000" and tray(pg)["highlighter"]["colour"] == "#000000")
        ta = pg.evaluate("['#tray .colours'].map(s => getComputedStyle(document.querySelector(s)).touchAction)")
        check("the colour group has touch-action none (no scroll or zoom during a hold)", ta == ["none"], ta)
        fit = pg.evaluate("(() => { const t = document.getElementById('tray'); return [t.scrollHeight, t.clientHeight]; })()")
        check("1280x800: all 14 slots, the tools, undo and redo fit (no tray scroll)", fit[0] <= fit[1], fit)

        # ------------------------------------------------------------ tap and drag
        group[0] = "reorder"
        pg.click(sw_sel("#0D0DFF"))
        check("a quick tap selects (pen goes Blue) without reordering", tray(pg)["pen"]["colour"] == "#0D0DFF" and pg.evaluate(SW_JS) == HERS
              and pg.locator("#tray .sw.lift").count() == 0)
        x, y = centre(pg, sw_sel("#FF0C84")); pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x, y + 12, steps=3)
        pg.wait_for_timeout(450); lifted = pg.locator("#tray .sw.lift").count(); pg.mouse.up(); pg.wait_for_timeout(40)
        check("a move before the hold time: nothing lifts, it is a tap", lifted == 0 and pg.evaluate(SW_JS) == HERS and tray(pg)["pen"]["colour"] == "#FF0C84", [lifted, tray(pg)["pen"]])
        pg.click(sw_sel("#000000"))
        p = pitch(pg)
        x, y = hold(pg, sw_sel("#2CB05F"))
        lift = pg.evaluate("(() => { const s = document.querySelector('#tray .sw.lift'); return s ? [s.dataset.colour, s.style.transform, getComputedStyle(s).boxShadow] : null; })()")
        check("hold 350 ms still: the swatch lifts (scale 1.15, a soft shadow)", lift and lift[0] == "#2CB05F" and "scale(1.15)" in lift[1] and lift[2].count("rgba") >= 2, lift)
        pg.mouse.move(x, y + 2 * p + 4, steps=10)
        moved = pg.evaluate("[...document.querySelectorAll('#tray .colours .sw')].slice(0, 3).map(s => s.style.transform)")
        check("the two neighbours it passed step aside (up by one place)", moved[1].startswith("translateY(-") and moved[2].startswith("translateY(-"), moved)
        if SHOTS:
            t = pg.locator("#tray").bounding_box()
            pg.screenshot(path=str(SHOTS / "colours-lift.png"), clip={"x": t["x"] - 20, "y": t["y"], "width": t["width"] + 20, "height": 420})
        pg.mouse.up(); pg.wait_for_timeout(60)
        want = [HERS[1], HERS[2], HERS[0]] + HERS[3:]
        dom, saved = pg.evaluate(SW_JS), pg.evaluate(SAVED_JS)
        check("drop: Green moved two places down; DOM order and names agree", dom == want, dom)
        check("the saved order agrees (13 hex values in order)", saved.get("order") == [c for c, _ in want], saved.get("order"))
        check("the drop selects nothing: pen still Black, the ring stays on Black", tray(pg)["pen"]["colour"] == "#000000"
              and pg.evaluate("[...document.querySelectorAll('#tray .sw.on')].map(s => s.dataset.colour)") == ["#000000"])
        check("no transforms left behind, nothing lifted", pg.evaluate("[...document.querySelectorAll('#tray .colours .sw')].every(s => !s.style.transform) && !document.querySelector('#tray .lift, #tray .dragging')"))
        check("the spare slot is still last", pg.evaluate("document.querySelector('#tray .colours').lastElementChild.classList.contains('spec')"))
        pg.reload(); ready(pg); open_note(pg)
        check("the order survives a reload", pg.evaluate(SW_JS) == want, pg.evaluate(SW_JS))
        # pointercancel mid-drag puts it back
        pg.evaluate("document.addEventListener('pointerdown', (e) => { window.__pid = e.pointerId; }, true)")
        x, y = hold(pg, sw_sel("#FF7043")); pg.mouse.move(x, y - 3 * p - 4, steps=8)
        mid = pg.locator("#tray .sw.lift").count()
        pg.evaluate("(s) => document.querySelector(s).dispatchEvent(new PointerEvent('pointercancel', { pointerId: window.__pid, bubbles: true }))", sw_sel("#FF7043"))
        pg.mouse.up(); pg.wait_for_timeout(60)
        check("pointercancel during a drag: the order is unchanged", mid == 1 and pg.evaluate(SW_JS) == want and pg.evaluate(SAVED_JS)["order"] == [c for c, _ in want], pg.evaluate(SW_JS))
        check("and nothing got selected", tray(pg)["pen"]["colour"] == "#000000" and not pg.evaluate("document.querySelector('#tray .lift')"))
        # corrupt saved orders fall back to her default
        bad_orders = [["#2CB05F", "#0D0DFF", "#FF0C84", "#FF7043", "#A83AFF", "#FFC107", "#00BCD5", "#FF00FF", "#3396FF", "#FF3636", "#000000", "#808080"],
                      HEXES[:12] + ["#2CB05F"], HEXES + ["#123456"], "nonsense", [1, 2, 3]]
        fell = []
        for o in bad_orders:
            pg.evaluate("(o) => { const s = JSON.parse(localStorage.getItem('pw.tools') || '{}'); s.order = o; localStorage.setItem('pw.tools', JSON.stringify(s)); }", o)
            pg.reload(); ready(pg); open_note(pg); fell.append(pg.evaluate(SW_JS) == HERS)
        check("a corrupt saved order (old 12-list, a duplicate, 14 values, a string, numbers) falls back to her default", all(fell), fell)
        pg.evaluate("(o) => { const s = JSON.parse(localStorage.getItem('pw.tools')); s.order = o; localStorage.setItem('pw.tools', JSON.stringify(s)); }",
                    [c.lower() for c in reversed(HEXES)])
        pg.reload(); ready(pg); open_note(pg)
        check("a valid saved order in lower case is used (and shown in her spelling)", pg.evaluate(SW_JS) == list(reversed(HERS)), pg.evaluate(SW_JS)[:3])
        pg.evaluate("() => { const s = JSON.parse(localStorage.getItem('pw.tools')); delete s.order; localStorage.setItem('pw.tools', JSON.stringify(s)); }")
        pg.reload(); ready(pg); open_note(pg)
        check("no page errors (strip, reorder)", not errs, errs)

        # ------------------------------------------------------------ the honeycomb picker
        group[0] = "honeycomb"
        pg.click("#tray .spec")
        check("the first tap on the spare slot opens the picker", picker_open(pg))
        pb, tb, sb = pg.locator("#specPicker").bounding_box(), pg.locator("#tray").bounding_box(), pg.locator("#tray .spec").bounding_box()
        check("a card left of the tray, beside the spare slot", pb["x"] + pb["width"] <= tb["x"] and pb["y"] <= sb["y"] + sb["height"] and pb["y"] + pb["height"] >= sb["y"], [pb, sb])
        cells = pg.evaluate(CELLS_JS)
        hx, gr = [c for c in cells if c["cls"] == "hx"], [c for c in cells if c["cls"] == "grey"]
        cb = pg.locator("#specPicker .comb svg").bounding_box()
        check("ONE svg honeycomb: 127 colour cells plus 16 grey cells, about 230 px wide",
              pg.locator("#specPicker svg").count() == 1 and len(hx) == 127 and len(gr) == 16 and 220 <= cb["width"] <= 240, [len(hx), len(gr), cb])
        per = [sum(c["id"].split("-")[0] == str(k) for c in hx) for k in range(7)]
        check("a centre and six rings: 1, 6, 12, 18, 24, 30, 36", per == [1, 6, 12, 18, 24, 30, 36], per)
        check("the greys sit under the hexagon", min(c["y"] for c in gr) > max(c["y"] + c["h"] for c in hx), [min(c["y"] for c in gr)])
        check("no square, no hue strip, no hex box; a round preview and Done",
              pg.locator("#specPicker .sq, #specPicker .hue, #specPicker input").count() == 0 and pg.locator("#specPicker .prev").count() == 1
              and pg.locator("#specPicker button", has_text="Done").count() == 1)
        check("the honeycomb has touch-action none", pg.evaluate("getComputedStyle(document.querySelector('#specPicker .comb')).touchAction") == "none")
        byid = {c["id"]: c for c in cells}
        check("the centre cell is white", byid["0-0"]["colour"] == "#FFFFFF", byid["0-0"])
        rim = [hls(c["colour"]) for c in hx if c["id"].startswith("6-")]
        check("the rim (ring 6) is dark: lightness under 35%", all(l < 0.35 for _, l, _ in rim), max(l for _, l, _ in rim))
        mid4 = [hls(c["colour"]) for c in hx if c["id"].startswith("4-")]
        check("a middle ring (ring 4) is saturated (the pure colours)", all(s > 0.9 and 0.4 < l < 0.6 for _, l, s in mid4), mid4[:3])
        ring1 = [hls(c["colour"]) for c in hx if c["id"].startswith("1-")]
        check("ring 1 is pastel (lightness over 80%)", all(l > 0.8 for _, l, _ in ring1), ring1[:2])
        hues = [round(hls(byid[f"{k}-0"]["colour"])[0] * 360) % 360 for k in (2, 4, 6)]
        check("red at the same place in every ring (cell 0 of rings 2, 4 and 6 is red)", all(h in (0, 359, 1) for h in hues), hues)
        g = [c["colour"] for c in gr]
        check("greys run white to black in 15 even steps, then one bigger black",
              g[0] == "#FFFFFF" and g[14] == "#000000" and g[15] == "#000000" and all(c[1:3] == c[3:5] == c[5:7] for c in g)
              and len(set(g[:15])) == 15 and max(abs((int(g[k][1:3], 16) - int(g[k + 1][1:3], 16)) - 255 / 14) for k in range(14)) < 1
              and gr[15]["h"] > gr[0]["h"] * 1.5, g)
        check("pen still Black: opening the picker alone picks nothing", tray(pg)["pen"]["colour"] == "#000000" and tray(pg)["spec"] is None)
        A = byid["4-3"]["colour"]
        pg.click("#specPicker [data-cell='4-3']")
        st = tray(pg)
        check("tapping cell 4-3 sets the spare slot, the pen and the saved value", st["spec"] == A and st["pen"]["colour"] == A
              and pg.evaluate(SAVED_JS)["spec"] == A and pg.evaluate(SAVED_JS)["pen"]["colour"] == A, [A, st["spec"], st["pen"]])
        check("preview and slot middle show it", pg.evaluate(PREV_JS) == rgb(A) and pg.evaluate(MID_JS) == rgb(A), [pg.evaluate(PREV_JS), pg.evaluate(MID_JS)])
        check("picking selects the slot (ring on it, none on the 13)", "on" in pg.get_attribute("#tray .spec", "class").split()
              and pg.locator("#tray .sw.on").count() == 0)
        check("the picker stays open after a tap", picker_open(pg))
        check("the selected outline sits on the tapped cell", sel_on(pg, "4-3"), pg.evaluate(SEL_JS))
        if SHOTS:
            pg.screenshot(path=str(SHOTS / "colours-honeycomb.png"), clip={"x": pb["x"] - 20, "y": max(0, pb["y"] - 20), "width": 1280 - pb["x"] + 20, "height": pb["height"] + 40})
        G = byid["g7"]["colour"]
        pg.click("#specPicker [data-cell='g7']")
        st = tray(pg)
        check("tapping a grey sets a grey (spare, pen, saved)", G[1:3] == G[3:5] == G[5:7] and G not in ("#FFFFFF", "#000000")
              and st["spec"] == G and st["pen"]["colour"] == G and pg.evaluate(SAVED_JS)["spec"] == G, [G, st["spec"]])
        check("the outline moved to the grey", sel_on(pg, "g7"), pg.evaluate(SEL_JS))
        pg.mouse.move(cb["x"] + 6, cb["y"] + 6); pg.mouse.down(); pg.mouse.up()       # the card's empty corner, beside the hexagon
        check("a tap on the card between cells picks nothing and keeps it open", tray(pg)["spec"] == G and picker_open(pg))
        pg.click("#specPicker [data-cell='4-3']")
        pg.click("#specPicker button.done")
        check("Done closes the picker", not picker_open(pg))
        draw(pg, 300)
        r1 = last_stroke(pg)
        check("a pen stroke drawn after the tap has that colour", r1 and r1["kind"] == "pen" and r1["style"]["colour"] == A, r1 and r1["style"])
        # the highlighter
        pg.click("#tool-highlighter")
        check("the highlighter takes the colour too (round 1); the ring stays on the spare slot", tray(pg)["highlighter"]["colour"] == A
              and tray(pg)["pen"]["colour"] == A and "on" in pg.get_attribute("#tray .spec", "class").split() and pg.locator("#tray .sw.on").count() == 0)
        pg.click(sw_sel("#FFC107"))                           # Amber on one of her 13, so the spare slot is not selected
        check("Amber with the highlighter: pen and highlighter both Amber, the ring on Amber", tray(pg)["highlighter"]["colour"] == "#FFC107"
              and tray(pg)["pen"]["colour"] == "#FFC107" and pg.evaluate("[...document.querySelectorAll('#tray .colours .on')].map(s => s.dataset.colour)") == ["#FFC107"])
        pg.click("#tray .spec")
        check("tap on the holding slot (not selected): it selects, the picker stays shut", tray(pg)["highlighter"]["colour"] == A and not picker_open(pg)
              and "on" in pg.get_attribute("#tray .spec", "class").split())
        pg.click("#tray .spec")
        check("tap again while it is selected: the picker opens, the outline still on 4-3", picker_open(pg) and sel_on(pg, "4-3"), pg.evaluate(SEL_JS))
        B = byid["6-10"]["colour"]
        pg.click("#specPicker [data-cell='6-10']")
        st = tray(pg)
        check("with the highlighter active, picking sets the one colour (pen and highlighter both)", st["highlighter"]["colour"] == B
              and st["pen"]["colour"] == B and st["spec"] == B, [st["pen"], st["highlighter"], st["spec"]])
        pg.click("#tray .spec")
        check("tap again while open: it closes (the panel rule)", not picker_open(pg))
        draw(pg, 500)
        r2 = last_stroke(pg)
        check("a highlighter stroke carries the picked colour", r2 and r2["kind"] == "highlighter" and r2["style"]["colour"] == B, r2 and r2["style"])
        # closing rules
        pg.click("#tray .spec"); o1 = picker_open(pg)
        pg.click(sw_sel("#0D0DFF")); o2 = picker_open(pg)
        check("a tap on one of her 13 closes the picker (and selects it)", o1 and not o2 and tray(pg)["highlighter"]["colour"] == "#0D0DFF")
        pg.click("#tray .spec"); pg.click("#tray .spec"); o1 = picker_open(pg)
        pg.click("#tool-pen"); o2 = picker_open(pg)
        check("picking a tool closes it", o1 and not o2)
        pg.click(sw_sel("#000000"))                           # the pen on Black (not the spare's B): the next tap selects
        pg.click("#tray .spec"); o1 = picker_open(pg)
        pg.click("#tray .spec"); o2 = picker_open(pg)
        pg.mouse.click(500, 400); o3 = picker_open(pg)
        check("a tap outside closes it", not o1 and o2 and not o3, [o1, o2, o3])
        pg.click("#tool-pen"); panel_was = pg.locator("#toolPanel").is_visible(); pg.click("#tray .spec")   # the spare is selected: this opens it
        check("opening the picker closes the pen panel", panel_was and picker_open(pg) and pg.locator("#toolPanel").is_hidden())
        pg.keyboard.press("Escape")
        check("Escape closes it", not picker_open(pg))
        # reload
        pg.reload(); ready(pg); open_note(pg)
        st = tray(pg)
        check("a reload keeps the picked colour (slot middle, pen and highlighter on it)", st["spec"] == B and pg.evaluate(MID_JS) == rgb(B)
              and st["pen"]["colour"] == B and st["highlighter"]["colour"] == B and "on" in pg.get_attribute("#tray .spec", "class").split(), [st["spec"], st["pen"], st["highlighter"]])
        pg.click("#tray .spec")
        check("after a reload the picker opens with the outline on the saved cell", picker_open(pg) and sel_on(pg, "6-10"), pg.evaluate(SEL_JS))
        pg.keyboard.press("Escape")
        pg.evaluate("() => { const s = JSON.parse(localStorage.getItem('pw.tools')); s.spec = 'red'; s.pen.colour = '#123456'; localStorage.setItem('pw.tools', JSON.stringify(s)); }")
        pg.reload(); ready(pg); open_note(pg)
        st = tray(pg)
        check("a bad saved spare colour is dropped: white middle, the pen back to Black", st["spec"] is None and pg.evaluate(MID_JS) == "rgb(255, 255, 255)"
              and st["pen"]["colour"] == "#000000", [st["spec"], st["pen"]])
        check("the spare slot is not draggable (holding it lifts nothing)", (hold(pg, "#tray .spec"), pg.locator("#tray .lift").count())[1] == 0)
        pg.mouse.up(); pg.wait_for_timeout(40); pg.keyboard.press("Escape")
        check("no page errors (honeycomb)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ round 1: ONE colour for the pen and the highlighter
        group[0] = "one colour"
        ctx, pg, errs = fresh(b)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg)
        RING_JS = "() => [...document.querySelectorAll('#tray .colours .on')].map(s => s.dataset.colour || 'spec')"
        pg.click(sw_sel("#0D0DFF"))
        pg.click("#tool-highlighter")
        check("Blue with the pen, then the highlighter: it is Blue, the ring stays on Blue", tray(pg)["highlighter"]["colour"] == "#0D0DFF"
              and pg.evaluate(RING_JS) == ["#0D0DFF"], [tray(pg)["highlighter"], pg.evaluate(RING_JS)])
        draw(pg, 200)
        r = last_stroke(pg)
        check("... and its stroke is Blue", r and r["kind"] == "highlighter" and r["style"]["colour"] == "#0D0DFF", r and r["style"])
        pg.click(sw_sel("#2CB05F"))
        pg.click("#tool-pen")
        check("Green with the highlighter, back to the pen: the pen is Green", tray(pg)["pen"]["colour"] == "#2CB05F" and pg.evaluate(RING_JS) == ["#2CB05F"],
              [tray(pg)["pen"], pg.evaluate(RING_JS)])
        draw(pg, 300)
        r = last_stroke(pg)
        check("... and its stroke is Green", r and r["kind"] == "pen" and r["style"]["colour"] == "#2CB05F", r and r["style"])
        pg.click("#tool-highlighter"); pg.click("#tool-pen"); pg.click("#tool-highlighter")
        check("switching back and forth never changes it", tray(pg)["pen"]["colour"] == tray(pg)["highlighter"]["colour"] == "#2CB05F")
        pg.click("#tool-eraser")
        pg.click(sw_sel("#FF0C84"))
        st = tray(pg)
        check("after an eraser a colour tap hands back the last ink tool (the highlighter) in that colour",
              st["tool"] == "highlighter" and st["highlighter"]["colour"] == "#FF0C84" and st["pen"]["colour"] == "#FF0C84"
              and "on" in pg.get_attribute("#tool-highlighter", "class").split(), [st["tool"], st["pen"], st["highlighter"]])
        draw(pg, 400)
        r = last_stroke(pg)
        check("... its stroke is a Pink highlighter stroke", r and r["kind"] == "highlighter" and r["style"]["colour"] == "#FF0C84", r and r["style"])
        pg.click("#tool-highlighter"); pg.click("#toolPanel [aria-label='Width bigger']"); pg.keyboard.press("Escape")
        pg.click("#tool-pen"); pg.click("#tool-pen"); pg.click("#toolPanel [aria-label='Width bigger']"); pg.keyboard.press("Escape")
        st = tray(pg)
        check("width stays per tool (pen 3, highlighter 20)", st["pen"]["width"] == 3 and st["highlighter"]["width"] == 20, [st["pen"], st["highlighter"]])
        pg.click("#tool-restyle")
        check("restyle starts in the current colour (Pink)", tray(pg)["restyle"]["colour"] == "#FF0C84" and pg.evaluate(RING_JS) == ["#FF0C84"])
        pg.click(sw_sel("#FF3636"))
        st = tray(pg)
        check("a colour tap with restyle on changes only restyle's own colour", st["restyle"]["colour"] == "#FF3636"
              and st["pen"]["colour"] == st["highlighter"]["colour"] == "#FF0C84", [st["restyle"], st["pen"]])
        pg.click("#tool-pen")
        check("back to the pen: still Pink, the ring on Pink", tray(pg)["pen"]["colour"] == "#FF0C84" and pg.evaluate(RING_JS) == ["#FF0C84"], pg.evaluate(RING_JS))
        saved = pg.evaluate(SAVED_JS)
        check("the saved copy keeps both fields, equal (the shape older apps read)", saved["pen"]["colour"] == saved["highlighter"]["colour"] == "#FF0C84"
              and saved["pen"]["width"] == 3 and saved["highlighter"]["width"] == 20, [saved["pen"], saved["highlighter"]])
        pg.reload(); ready(pg); open_note(pg)
        st = tray(pg)
        check("a reload keeps the one colour (Pink for both, the ring on Pink)", st["pen"]["colour"] == st["highlighter"]["colour"] == "#FF0C84"
              and pg.evaluate(RING_JS) == ["#FF0C84"], [st["pen"], st["highlighter"]])
        # a copy saved by the old app: pen Black, highlighter Amber, the highlighter on
        OLD = {"tool": "highlighter", "pen": {"colour": "#000000", "width": 4, "dash": "dashed"},
               "highlighter": {"colour": "#FFC107", "width": 22, "opacity": 0.5}, "restyle": {"colour": "#FFC107"}, "order": HEXES, "spec": None}
        pg.evaluate("(v) => localStorage.setItem('pw.tools', JSON.stringify(v))", OLD)
        pg.reload(); ready(pg); open_note(pg)
        st = tray(pg)
        check("an old device copy (pen Black, highlighter Amber, highlighter on) loads as Amber for both",
              st["tool"] == "highlighter" and st["pen"]["colour"] == st["highlighter"]["colour"] == "#FFC107" and pg.evaluate(RING_JS) == ["#FFC107"],
              [st["tool"], st["pen"], st["highlighter"]])
        check("... width, dash and opacity stay per tool", st["pen"]["width"] == 4 and st["pen"]["dash"] == "dashed" and st["highlighter"]["width"] == 22
              and st["highlighter"]["opacity"] == 0.5, [st["pen"], st["highlighter"]])
        pg.click("#tool-pen"); draw(pg, 500)
        r = last_stroke(pg)
        check("... and the pen then draws Amber", r and r["kind"] == "pen" and r["style"]["colour"] == "#FFC107", r and r["style"])
        # the same row from the database (profiles.settings.tray), newer than the device's copy
        pg.evaluate("(v) => localStorage.setItem('pw.tools', JSON.stringify(v))", dict(OLD, tool="pen", pen=dict(OLD["pen"], colour="#0D0DFF"), tray_at="2026-10-20T00:00:00.000Z"))
        pg.evaluate("([t, at]) => window.__pw.api.setSettings({ tray: t, tray_at: at })", [OLD, "2026-10-28T00:00:00.000Z"])
        pg.reload(); ready(pg)
        try: pg.wait_for_function("() => window.__pw.tray().pen.colour !== '#0D0DFF'", timeout=4000)
        except Exception: pass                                # the check below reports it
        st = tray(pg)
        check("an old database row (pen Black, highlighter Amber, highlighter on) adopted: Amber for both",
              st["tool"] == "highlighter" and st["pen"]["colour"] == st["highlighter"]["colour"] == "#FFC107", [st["tool"], st["pen"], st["highlighter"]])
        OLDP = dict(OLD, tool="pen")
        pg.evaluate("(v) => localStorage.setItem('pw.tools', JSON.stringify(v))", OLDP)
        pg.reload(); ready(pg); open_note(pg)
        st = tray(pg)
        check("the same old copy with the pen on loads as Black for both", st["pen"]["colour"] == st["highlighter"]["colour"] == "#000000", [st["pen"], st["highlighter"]])
        check("no page errors (one colour)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ rings on both trays, portrait fit
        group[0] = "rings and fit"
        ctx, pg, errs = fresh(b)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg)
        ring = pg.evaluate("(s) => getComputedStyle(document.querySelector(s)).boxShadow", sw_sel("#808080"))
        check("light tray: Grey has its dark ring", "rgba(38, 42, 48, 0.45)" in ring and "inset" in ring, ring)
        ctx.close()
        ctx, pg, errs = fresh(b, color_scheme="dark")
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg)
        ring = pg.evaluate("(s) => getComputedStyle(document.querySelector(s)).boxShadow", sw_sel("#000000"))
        check("dark tray: Black has its light ring", "rgba(255, 255, 255, 0.6)" in ring and "inset" in ring, ring)
        pg.click("#tray .spec")
        dk = pg.evaluate("""(() => { const p = document.getElementById('specPicker'), w = document.querySelector('#specPicker [data-cell="0-0"]');
          return [getComputedStyle(p).backgroundColor, getComputedStyle(document.documentElement).getPropertyValue('--card').trim(), getComputedStyle(w).fill]; })()""")
        check("dark mode: the picker card is the panel colour, the cells unchanged (centre still white)",
              dk[0] == "rgb(42, 46, 52)" and dk[1].upper() == "#2A2E34" and dk[2] == "rgb(255, 255, 255)", dk)
        pg.keyboard.press("Escape")
        pg.set_viewport_size({"width": 800, "height": 1280}); pg.wait_for_timeout(100)
        size = pg.locator(sw_sel("#000000")).bounding_box()
        fit = pg.evaluate("(() => { const t = document.getElementById('tray'); return [t.scrollHeight, t.clientHeight]; })()")
        check("tablet portrait 800x1280: full-size 26 px circles, everything fits", round(size["height"]) == 26 and fit[0] <= fit[1], [size, fit])
        check("no page errors (rings)", not errs, errs)
        ctx.close()
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
