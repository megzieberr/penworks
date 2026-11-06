# PenWorks pw-v9a checks: bookmarks the Samsung way, a tappable ribbon on every thumb in the page list (her ask 1, 6 Nov).
# Run: python tests/test_bookmarks.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note, 'Weekly plan', with six pages, pages 2 and 5 bookmarked, into the localStorage twin. At 1280 x 800,
# light and dark: six ribbon buttons, two pressed, marked blue and unmarked grey; a tap on a grey one bookmarks the page
# (toast, the page row, the big page's tab), the list does not scroll (a second seed of fourteen pages, so the list has a scroll), the panel stays open, the current page stays and
# nothing lifts; a second tap takes it off. The Bookmarks filter, tick mode (the tick wins its corner), the big page's
# ribbon (blue, no pointer events). At 390 x 844: the button is at least 40 x 40 and a tap works.
# The proof pictures go to _build/bookmarks/shots/.
import sys, subprocess, time, pathlib, re
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8824
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "bookmarks" / "shots"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-01T08:00:00Z';
  const P = (k, background, bookmark) => ({ id: 'p' + k, note_id: 'n1', position: k - 1, orientation: 'portrait', background, bookmark,
    deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Grade 11', colour: '#3A86D6', position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Weekly plan', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-11-05T09:00:00Z' }],
    pages: [P(1, 'grid', false), P(2, 'lined', true), P(3, 'grid', false), P(4, 'grid', false), P(5, 'lined', true), P(6, 'grid', false)] }));
}"""

LONG = "".join(f", P({k}, 'grid', false)" for k in range(7, 15))     # pages 7 to 14 for the scroll group
BLUE, BLUE_DARK = "rgb(47, 75, 184)", "rgb(147, 166, 242)"
GREY, GREY_DARK = "rgb(226, 224, 218)", "rgb(74, 80, 88)"

RIBBONS = """() => [...document.querySelectorAll('#plThumbs .thumbP')].map((t) => { const b = t.querySelector('.bmBtn');
  return b ? { i: +t.dataset.index, pressed: b.getAttribute('aria-pressed'), label: b.getAttribute('aria-label'),
               fill: getComputedStyle(b.querySelector('svg path')).fill } : { i: +t.dataset.index, none: true }; })"""
ROW_JS = """async (id) => { await window.__pw.idle(); const r = (await window.__pw.api.loadAll()).pages.find(p => p.id === id); return r ? r.bookmark : null; }"""
SHEET_TAB = "(id) => !!document.querySelector(`#stack .sheet[data-id='${id}'] > .bookmarkTab`)"
FILL4 = "getComputedStyle(document.querySelector('#plThumbs .thumbP[data-index=\"4\"] .bmBtn path')).fill"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def card(pg, name): return pg.locator("#grid .card").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def open_note(pg):
    card(pg, "Weekly plan").click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='6']"); pg.wait_for_timeout(200)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(300)
def ribbons(pg): return pg.evaluate(RIBBONS)
def btn(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}'] .bmBtn")
def toast(pg): return pg.evaluate("document.getElementById('toast').textContent")
def scroll_top(pg): return pg.evaluate("document.getElementById('plThumbs').scrollTop")
def cur(pg): return pg.evaluate("[...document.querySelectorAll('#plThumbs .thumbP.cur')].map((t) => +t.dataset.index)")
def lifted(pg): return pg.evaluate("document.querySelectorAll('#plThumbs .thumbP.lift').length")
def centre_of(pg, i):
    b = btn(pg, i).bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
def show_thumb(pg, i):
    """scroll the list by hand so thumb i's ribbon is inside it (never scrollIntoView), then return the scrollTop"""
    pg.evaluate("""(i) => { const T = document.getElementById('plThumbs'), t = T.querySelector(`.thumbP[data-index="${i}"]`);
      const a = T.getBoundingClientRect(), b = t.getBoundingClientRect(); T.scrollTop = Math.max(0, T.scrollTop + b.top - a.top - 40); }""", i)
    pg.wait_for_timeout(80); return scroll_top(pg)
def pressed_all(pg): return [x.get("pressed") for x in ribbons(pg)]

def basics(pg, dark):
    want_on, want_off = (BLUE_DARK, GREY_DARK) if dark else (BLUE, GREY)
    r = ribbons(pg)
    check("six .bmBtn, pages 2 and 5 pressed", len(r) == 6 and [x.get("pressed") for x in r] == ["false", "true", "false", "false", "true", "false"], r)
    check("labels: 'Remove bookmark' on the marked, 'Bookmark page N' on the others",
          [x.get("label") for x in r] == ["Bookmark page 1", "Remove bookmark", "Bookmark page 3", "Bookmark page 4", "Remove bookmark", "Bookmark page 6"], r)
    fills_on = {x["fill"] for x in r if x.get("pressed") == "true"}; fills_off = {x["fill"] for x in r if x.get("pressed") == "false"}
    check("marked fill is the ink blue, unmarked the grey, and they differ", fills_on == {want_on} and fills_off == {want_off}, [fills_on, fills_off])
    check("no old .paper > .bookmarkTab on any thumb", pg.locator("#plThumbs .paper > .bookmarkTab").count() == 0)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------ tablet, light
        group[0] = "tablet 1280x800"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg); pg.wait_for_timeout(200)
        open_note(pg); open_list(pg)
        basics(pg, False)
        pg.screenshot(path=str(SHOTS / "list.png"))

        # tap page 4's grey ribbon
        top0 = show_thumb(pg, 4); cur0 = cur(pg); sel0 = pg.evaluate("window.__pw.S.cur")
        x, y = centre_of(pg, 4); pg.mouse.click(x, y); pg.wait_for_timeout(120); idle(pg)
        check("tap a grey ribbon: aria-pressed true, label 'Remove bookmark'", btn(pg, 4).get_attribute("aria-pressed") == "true"
              and btn(pg, 4).get_attribute("aria-label") == "Remove bookmark", btn(pg, 4).get_attribute("aria-pressed"))
        check("the toast says 'Bookmarked'", toast(pg) == "Bookmarked", toast(pg))
        check("the page row's bookmark is true in the store", pg.evaluate(ROW_JS, "p4") is True, pg.evaluate(ROW_JS, "p4"))
        check("the big page's sheet now has a .bookmarkTab", pg.evaluate(SHEET_TAB, "p4"))
        check("the list did not scroll (scrollTop the same)", abs(scroll_top(pg) - top0) < 1, [top0, scroll_top(pg)])
        check("the panel stayed open", pg.locator("#pageList").is_visible())
        check("the current page did not change (.thumbP.cur, S.cur)", cur(pg) == cur0 and pg.evaluate("window.__pw.S.cur") == sel0, [cur0, cur(pg)])
        check("the blue fill now", pg.evaluate(FILL4) == BLUE, pg.evaluate(FILL4))
        x, y = centre_of(pg, 4); pg.mouse.click(x, y); pg.wait_for_timeout(120); idle(pg)
        check("tap again: off, label 'Bookmark page 4'", btn(pg, 4).get_attribute("aria-pressed") == "false"
              and btn(pg, 4).get_attribute("aria-label") == "Bookmark page 4")
        check("the toast says 'Bookmark removed'", toast(pg) == "Bookmark removed", toast(pg))
        check("the row is false and the sheet's tab is gone", pg.evaluate(ROW_JS, "p4") is False and not pg.evaluate(SHEET_TAB, "p4"))
        check("still no scroll, still open, same page", abs(scroll_top(pg) - top0) < 1 and pg.locator("#pageList").is_visible() and cur(pg) == cur0,
              [top0, scroll_top(pg), cur(pg)])

        # a hold on the ribbon never lifts the thumb (the closest('button') guard)
        x, y = centre_of(pg, 3); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(600)
        check("a hold on the ribbon: no .lift, no page drag", lifted(pg) == 0 and pg.evaluate("window.__pw.pageDrag()") is None,
              [lifted(pg), pg.evaluate("window.__pw.pageDrag()")])
        pg.mouse.up(); pg.wait_for_timeout(120); idle(pg)
        check("and its release is a tap: page 3 bookmarked", btn(pg, 3).get_attribute("aria-pressed") == "true" and pg.evaluate(ROW_JS, "p3") is True)
        x, y = centre_of(pg, 3); pg.mouse.click(x, y); pg.wait_for_timeout(120); idle(pg)
        check("set back: page 3 off", pg.evaluate(ROW_JS, "p3") is False)

        # the Bookmarks filter
        pg.click("#plMarks"); pg.wait_for_timeout(150)
        r = ribbons(pg)
        check("filter on: only pages 2 and 5, each with a pressed blue ribbon", [x["i"] for x in r] == [2, 5]
              and all(x["pressed"] == "true" and x["fill"] == BLUE for x in r), r)
        pg.screenshot(path=str(SHOTS / "filter.png"))
        x, y = centre_of(pg, 5); pg.mouse.click(x, y); pg.wait_for_timeout(150); idle(pg)
        r = ribbons(pg)
        check("a tap in the filter unmarks page 5 and it leaves the list", [x["i"] for x in r] == [2] and pg.evaluate(ROW_JS, "p5") is False
              and toast(pg) == "Bookmark removed", [r, toast(pg)])
        pg.click("#plMarks"); pg.wait_for_timeout(150)
        show_thumb(pg, 5); x, y = centre_of(pg, 5); pg.mouse.click(x, y); pg.wait_for_timeout(120); idle(pg)
        check("filter off, page 5 marked again", pressed_all(pg) == ["false", "true", "false", "false", "true", "false"], pressed_all(pg))

        # tick mode: the tick wins the corner
        pg.click("#plSelect"); pg.wait_for_timeout(80)
        pe = pg.evaluate("getComputedStyle(document.querySelector('#plThumbs .bmBtn')).pointerEvents")
        vis = btn(pg, 1).is_visible()
        check("tick mode: the ribbon button has pointer-events none and stays visible", pe == "none" and vis, [pe, vis])
        show_thumb(pg, 1)
        x, y = centre_of(pg, 1); pg.mouse.click(x, y); pg.wait_for_timeout(120); idle(pg)
        ticked = pg.evaluate("[...document.querySelectorAll('#plThumbs .thumbP.ticked')].map((t) => +t.dataset.index)")
        check("a tap on the ribbon's corner ticks page 1, the bookmark does not flip", ticked == [1] and btn(pg, 1).get_attribute("aria-pressed") == "false"
              and pg.evaluate(ROW_JS, "p1") is False, [ticked, btn(pg, 1).get_attribute("aria-pressed")])
        pg.click("#plDone"); pg.wait_for_timeout(80)
        check("Done ends tick mode, the ribbon takes taps again",
              pg.evaluate("getComputedStyle(document.querySelector('#plThumbs .bmBtn')).pointerEvents") != "none")

        # the big page's ribbon
        tab = pg.evaluate("""() => { const t = document.querySelector("#stack .sheet[data-id='p2'] > .bookmarkTab");
            return t ? { pe: getComputedStyle(t).pointerEvents, fill: getComputedStyle(t.querySelector('path')).fill } : null; }""")
        check("the big page's ribbon: pointer-events none, the ink blue", tab and tab["pe"] == "none" and tab["fill"] == BLUE, tab)

        # dark (the attribute, as the theme button sets it)
        group[0] = "tablet dark"
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')"); pg.wait_for_timeout(80)
        pg.evaluate("document.getElementById('plThumbs').scrollTop = 0"); pg.wait_for_timeout(60)
        basics(pg, True)
        tab = pg.evaluate("getComputedStyle(document.querySelector(\"#stack .sheet[data-id='p2'] > .bookmarkTab path\")).fill")
        check("dark: the big page's ribbon is the dark ink blue", tab == BLUE_DARK, tab)
        pg.evaluate("document.getElementById('toast').classList.remove('show')"); pg.wait_for_timeout(300)   # the picture without the last toast
        pg.screenshot(path=str(SHOTS / "list-dark.png"))
        pg.evaluate("document.documentElement.removeAttribute('data-theme')"); pg.wait_for_timeout(80)

        # the picture of a bookmarked big page: page 2, the list closed
        group[0] = "tablet 1280x800"
        pg.click("#plClose"); pg.wait_for_selector("#pageList", state="hidden")
        pg.evaluate("import('./js/page.js').then((m) => m.scrollToPage(1))"); pg.wait_for_timeout(600)
        pg.evaluate("document.getElementById('toast').classList.remove('show')"); pg.wait_for_timeout(300)   # the picture without the last toast
        pg.screenshot(path=str(SHOTS / "page.png"))
        check("no page errors (tablet)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ system dark (no data-theme set): the same grey
        group[0] = "system dark"
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, color_scheme="dark")
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg); pg.wait_for_timeout(200)
        open_note(pg); open_list(pg)
        theme = pg.evaluate("document.documentElement.getAttribute('data-theme')")
        check("set-up: no data-theme or dark (the system's dark shows)", theme in (None, "", "dark"), theme)
        basics(pg, True)
        check("no page errors (system dark)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ a long note: the list keeps its scroll
        group[0] = "long note scroll"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED.replace("P(6, 'grid', false)]", "P(6, 'grid', false)" + LONG + "]")); pg.reload(); ready(pg); pg.wait_for_timeout(200)
        card(pg, "Weekly plan").click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='14']")
        pg.wait_for_timeout(200); open_list(pg)
        top = show_thumb(pg, 11)
        scrolls = pg.evaluate("(() => { const T = document.getElementById('plThumbs'); return T.scrollHeight > T.clientHeight + 10; })()")
        check("set-up: fourteen thumbs, the list scrolled away from the top", scrolls and top > 0 and len(ribbons(pg)) == 14, [scrolls, top])
        x, y = centre_of(pg, 11); pg.mouse.click(x, y); pg.wait_for_timeout(150); idle(pg)
        check("a tap low in the list: page 11 bookmarked, scrollTop the same", btn(pg, 11).get_attribute("aria-pressed") == "true"
              and abs(scroll_top(pg) - top) < 1 and pg.evaluate(ROW_JS, "p11") is True, [top, scroll_top(pg)])
        x, y = centre_of(pg, 11); pg.mouse.click(x, y); pg.wait_for_timeout(150); idle(pg)
        check("and off again, still the same scrollTop", btn(pg, 11).get_attribute("aria-pressed") == "false" and abs(scroll_top(pg) - top) < 1,
              [top, scroll_top(pg)])
        check("no page errors (long note)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ phone
        group[0] = "phone 390x844"
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, device_scale_factor=2)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg); pg.wait_for_timeout(300)
        card(pg, "Weekly plan").tap()
        pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='6']"); pg.wait_for_timeout(300)
        pg.tap("#listBtn"); pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(300)
        check("phone: six ribbons, pages 2 and 5 pressed", pressed_all(pg) == ["false", "true", "false", "false", "true", "false"], pressed_all(pg))
        pg.screenshot(path=str(SHOTS / "phone.png"))
        bb = btn(pg, 1).bounding_box()
        check("phone: the ribbon button is at least 40 x 40", bb and bb["width"] >= 40 and bb["height"] >= 40, bb)
        show_thumb(pg, 1); x, y = centre_of(pg, 1)
        pg.touchscreen.tap(x, y); pg.wait_for_timeout(150); idle(pg)
        check("phone: a tap bookmarks page 1 (toast, row) and the panel stays open", btn(pg, 1).get_attribute("aria-pressed") == "true"
              and toast(pg) == "Bookmarked" and pg.evaluate(ROW_JS, "p1") is True and pg.locator("#pageList").is_visible(),
              [btn(pg, 1).get_attribute("aria-pressed"), toast(pg)])
        check("no page errors (phone)", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:400]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
