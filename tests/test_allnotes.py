# PenWorks pw-v8y checks: "All notes" on top of the folder view, the app opens on it every time (her rule 1 Nov), the
# phone grid in two columns and the folder view as a drawer behind the menu button (her ask 3, 6 Nov).
# Run: python tests/test_allnotes.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds three folders (Grade 11 with the sub-folder Extra class, Grade 12, NWU) and six notes (two pinned, two in Loose,
# each edited on a different day) into the localStorage twin. At 1280 x 800: the All notes row (first, count 6, selected
# at start), its grid in noteOrder with a .where line on every card, a folder grid without one, a New note there lands in
# Loose, a reload never reopens the note (and the note still opens on the page she was last on), Back lands where the note
# was opened from. At 390 x 844: two columns, the drawer (menu button, veil tap, folder tap, note row tap, the resize).
# Dark mode: the drawer, the veil and the All notes row's tint. The proof pictures (a bigger seed, so the grid scrolls)
# go to _build/allnotes/shots/.
import sys, subprocess, time, pathlib, re
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8822
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "allnotes" / "shots"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-01T08:00:00Z';
  const F = (id, parent_id, name, colour, position) => ({ id, parent_id, name, colour, position, deleted_at: null, created_at: t, updated_at: t });
  const N = (id, folder_id, name, pinned, upd) => ({ id, folder_id, name, pinned, cover_path: null, deleted_at: null, created_at: t, updated_at: upd });
  const P = (id, note_id, position, background) => ({ id, note_id, position, orientation: 'portrait', background, deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [F('f1', null, 'Grade 11', '#3A86D6', 0), F('f1a', 'f1', 'Extra class', '#3A86D6', 0),
              F('f2', null, 'Grade 12', '#E0524A', 1), F('f3', null, 'NWU', '#45A866', 2)],
    notes: [N('n1', 'f1a', 'Trig round 1', true, '2026-11-01T09:00:00Z'), N('n2', 'f3', 'MATH121 limits', true, '2026-10-20T09:00:00Z'),
            N('n3', 'f1', 'Identities', false, '2026-11-05T09:00:00Z'), N('n4', 'f2', 'Proef V2', false, '2026-11-03T09:00:00Z'),
            N('n5', null, 'Shopping list', false, '2026-11-04T09:00:00Z'), N('n6', null, 'Constructions', false, '2026-10-29T09:00:00Z')],
    pages: [P('p1', 'n1', 0, 'grid'), P('p2', 'n2', 0, 'lined'), P('p3a', 'n3', 0, 'grid'), P('p3b', 'n3', 1, 'grid'), P('p3c', 'n3', 2, 'grid'),
            P('p4', 'n4', 0, 'lined'), P('p5', 'n5', 0, 'grid'), P('p6', 'n6', 0, 'grid')] }));
}"""
ORDER = ["Trig round 1", "MATH121 limits", "Identities", "Shopping list", "Proef V2", "Constructions"]
WHERE = {"Trig round 1": "Grade 11 / Extra class", "MATH121 limits": "NWU", "Identities": "Grade 11", "Shopping list": "Loose",
         "Proef V2": "Grade 12", "Constructions": "Loose"}

# the pictures: the same folders and eighteen notes, so the grid scrolls at both sizes
SHOT_SEED = """() => {
  localStorage.clear();
  const t = '2026-10-01T08:00:00Z';
  const F = (id, parent_id, name, colour, position) => ({ id, parent_id, name, colour, position, deleted_at: null, created_at: t, updated_at: t });
  const where = ['f1a', 'f1a', 'f1', 'f1a', 'f1', 'f2', 'f1a', 'f3', 'f1', 'f3', null, null, 'f2', 'f1', 'f1a', 'f3', null, 'f2'];
  const names = ['Trig round 1 (Wed 4 Nov)', 'Sept 2025 P2', 'Identities and general solution', 'Reduction formulae', 'Graphs 2D',
                 'Proef V2 marking notes', 'Finance: one equation', 'MATH121 limits', 'Statistics', 'MATV121 tutorial 5', 'Shopping list',
                 'Constructions test', 'Gr12 P2 mock', 'Analytical geometry', 'Probability', 'EDCC125 reading', 'Grocery run', 'Gr12 V1 mock'];
  const notes = [], pages = [];
  names.forEach((name, k) => {
    notes.push({ id: 'n' + k, folder_id: where[k], name, pinned: k < 2, cover_path: null, deleted_at: null, created_at: t,
                 updated_at: new Date(Date.parse('2026-11-06T09:00:00Z') - k * 864e5 * 0.7).toISOString() });
    pages.push({ id: 'p' + k, note_id: 'n' + k, position: 0, orientation: 'portrait', background: k % 3 === 1 ? 'lined' : 'grid', deleted_at: null, created_at: t, updated_at: t });
  });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [F('f1', null, 'Grade 11', '#3A86D6', 0), F('f1a', 'f1', 'Extra class', '#3A86D6', 0),
              F('f2', null, 'Grade 12', '#E0524A', 1), F('f3', null, 'NWU', '#45A866', 2)], notes, pages }));
}"""

CARDS = """() => [...document.querySelectorAll('#grid .card:not(.plus)')].map((c) => ({
  name: c.querySelector('.name').textContent, where: c.querySelector('.where') ? c.querySelector('.where').textContent : null,
  x: Math.round(c.getBoundingClientRect().x) }))"""
STATE = """() => { const b = (id) => { const e = document.getElementById(id); if (!e) return null; const r = e.getBoundingClientRect();
    return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width }; };
  const v = document.getElementById('sideVeil'), vs = getComputedStyle(v);
  return { drawer: document.body.classList.contains('drawer'), side: b('side'), veilShown: vs.display !== 'none' && b('sideVeil').w > 0,
           veilBg: vs.backgroundColor, title: document.getElementById('gridTitle').textContent,
           noteOpen: !document.getElementById('noteView').hidden, sel: window.__pw.S.sel }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def cards(pg): return pg.evaluate(CARDS)
def state(pg): return pg.evaluate(STATE)
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def card(pg, name): return pg.locator("#grid .card").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def opened(pg): pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(200)
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(100)
def bg(pg, sel): return pg.evaluate("(s) => getComputedStyle(document.querySelector(s)).backgroundColor", sel)
SLIDE = 350                                                     # the drawer's .22 s slide, and a little

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------ tablet
        group[0] = "tablet 1280x800"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        first = pg.locator("#folderList .frow").first
        check("the first row of the folder view is All notes, count 6, selected at start",
              first.locator(".name").inner_text() == "All notes" and first.locator(".count").inner_text() == "6"
              and "sel" in (first.get_attribute("class") or "").split() and "all" in (first.get_attribute("class") or "").split(),
              [first.locator(".name").inner_text(), first.locator(".count").inner_text(), first.get_attribute("class")])
        check("All notes has no chevron and no menu, and sits above Loose",
              first.locator(".chev").count() == 0 and first.locator(".more").count() == 0 and first.locator(".chevGap").count() == 1
              and pg.locator("#folderList .frow").nth(1).locator(".name").inner_text() == "Loose")
        check("only one row is selected", pg.locator("#folderList .frow.sel").count() == 1)
        check("#gridTitle reads All notes", pg.inner_text("#gridTitle") == "All notes", pg.inner_text("#gridTitle"))
        c = cards(pg)
        check("every note, pinned first, then last edited", [x["name"] for x in c] == ORDER, [x["name"] for x in c])
        check("each card says where its note lives (the folder path, or Loose)", all(x["where"] == WHERE[x["name"]] for x in c), c)
        check("the New note and Open PDF tiles lead the grid", pg.locator("#grid .card.plus").count() == 2
              and pg.evaluate("document.querySelector('#grid').firstElementChild.id") == "newNote")

        frow(pg, "Grade 11").click(); pg.wait_for_timeout(100)
        c = cards(pg)
        check("a folder grid: its own notes, no .where line", pg.inner_text("#gridTitle") == "Grade 11"
              and [x["name"] for x in c] == ["Identities"] and pg.locator("#grid .where").count() == 0, c)
        frow(pg, "Bin").click(); pg.wait_for_timeout(100)
        check("the Bin: no .where line", pg.locator("#grid .where").count() == 0 and pg.inner_text("#gridTitle") == "Bin")

        # a New note in All notes lands in Loose, the grid stays on All notes
        frow(pg, "All notes").click(); pg.wait_for_timeout(80)
        pg.click("#newNote"); opened(pg)
        nid = pg.evaluate("window.__pw.S.openNote")
        fid = pg.evaluate("(id) => window.__pw.S.notes.find((n) => n.id === id).folder_id", nid)
        back(pg); idle(pg)
        check("New note in All notes: the note is in Loose (folder_id null)", fid is None, fid)
        check("and Back lands on All notes, the new note on its grid saying Loose", pg.inner_text("#gridTitle") == "All notes"
              and card(pg, "Untitled").locator(".where").inner_text() == "Loose"
              and frow(pg, "All notes").locator(".count").inner_text() == "7" and frow(pg, "Loose").locator(".count").inner_text() == "3")

        # a reload never reopens the note; the note still opens on the page she was last on
        card(pg, "Identities").click(); opened(pg)
        pg.evaluate("import('./js/page.js').then((m) => m.scrollToPage(2))"); pg.wait_for_timeout(600)
        cur = pg.evaluate("window.__pw.S.cur")
        check("set-up: Identities scrolled to its third page", cur == 2, cur)
        pg.reload(); ready(pg); pg.wait_for_timeout(300); s = state(pg)
        check("reload with a note open: the grid shows, #noteView hidden, All notes selected",
              not s["noteOpen"] and s["title"] == "All notes" and s["sel"] == "all"
              and "sel" in (frow(pg, "All notes").get_attribute("class") or ""), s)
        card(pg, "Identities").click(); opened(pg)
        check("opening it again lands on the page she was last on (3 of 3)", pg.evaluate("window.__pw.S.cur") == 2
              and pg.inner_text("#counter").strip().startswith("3"), pg.inner_text("#counter"))

        # Back lands where the note was opened from
        back(pg); s = state(pg)
        check("Back from a note opened from All notes lands on All notes", s["title"] == "All notes" and s["sel"] == "all", s)
        frow(pg, "Grade 12").click(); pg.wait_for_timeout(80)
        card(pg, "Proef V2").click(); opened(pg); back(pg); s = state(pg)
        check("Back from a note opened from a folder lands on that folder", s["title"] == "Grade 12" and s["sel"] == "f2"
              and "sel" in (frow(pg, "Grade 12").get_attribute("class") or ""), s)
        frow(pg, "All notes").click(); pg.wait_for_timeout(80)
        nrow(pg, "Shopping list").click(); opened(pg); back(pg); s = state(pg)
        check("a note row in the folder view keeps the selection too (All notes)", s["title"] == "All notes", s)
        check("the veil never shows on the tablet", not s["veilShown"] and not s["drawer"], s)
        check("no page errors (tablet)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ phone
        group[0] = "phone 390x844"
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        s = state(pg); c = cards(pg)
        tiles = pg.evaluate("[...document.querySelectorAll('#grid .card.plus')].map((e) => Math.round(e.getBoundingClientRect().x))")
        check("the phone opens on the All notes grid", s["title"] == "All notes" and not s["noteOpen"] and pg.locator("#main").is_visible(), s)
        check("two columns: two distinct card x positions, the tiles side by side", len({x["x"] for x in c}) == 2 and len(set(tiles)) == 2, [c, tiles])
        check("the cards still say where they live", all(x["where"] == WHERE[x["name"]] for x in c), c)
        check("#side is off screen, the drawer shut, no veil", s["side"]["r"] <= 0.5 and not s["drawer"] and not s["veilShown"], s)
        check("no horizontal scroll (phone grid)", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        check("the menu button keeps its id and its label", pg.get_attribute("#gridBack", "aria-label") == "Folders"
              and pg.locator("#gridBack svg path").get_attribute("d") == "M4 7h16M4 12h16M4 17h16")

        pg.tap("#gridBack"); pg.wait_for_timeout(SLIDE); s = state(pg)
        check("the menu button opens the drawer: body.drawer, #side on screen, the veil showing",
              s["drawer"] and abs(s["side"]["l"]) < 0.5 and 300 <= s["side"]["w"] <= 320 and s["veilShown"], s)
        check("the veil dims the grid", s["veilBg"] == "rgba(38, 42, 48, 0.32)", s["veilBg"])
        pg.touchscreen.tap(370, 500); pg.wait_for_timeout(SLIDE); s = state(pg)
        check("a tap on the veil closes it", not s["drawer"] and s["side"]["r"] <= 0.5 and not s["veilShown"], s)

        pg.tap("#gridBack"); pg.wait_for_timeout(SLIDE)
        frow(pg, "Grade 11").tap(); pg.wait_for_timeout(SLIDE); s = state(pg)
        check("a folder tap in the drawer closes it and shows that folder's grid", not s["drawer"] and s["title"] == "Grade 11"
              and s["side"]["r"] <= 0.5 and [x["name"] for x in cards(pg)] == ["Identities"], s)
        pg.tap("#gridBack"); pg.wait_for_timeout(SLIDE)
        nrow(pg, "Proef V2").tap(); opened(pg); s = state(pg)
        check("a note row tap in the drawer opens the note (and the drawer is shut)", s["noteOpen"] and not s["drawer"]
              and pg.inner_text("#noteName .nn") == "Proef V2", s)
        pg.tap("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(150); s = state(pg)
        check("Back from it: the grid, the drawer still shut", not s["noteOpen"] and not s["drawer"] and s["title"] == "Grade 11", s)
        pg.tap("#gridBack"); pg.wait_for_timeout(SLIDE)
        check("set-up: drawer open before the resize", state(pg)["drawer"])
        pg.set_viewport_size({"width": 1280, "height": 800}); pg.wait_for_timeout(300); s = state(pg)
        check("the resize to 1280 drops body.drawer and the veil", not s["drawer"] and not s["veilShown"] and s["side"]["l"] >= -0.5, s)
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(300); s = state(pg)
        check("and back to the phone: the drawer shut", not s["drawer"] and s["side"]["r"] <= 0.5, s)
        check("no page errors (phone)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ the pictures, and dark mode
        group[0] = "pictures and dark"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SHOT_SEED); pg.reload(); ready(pg); pg.wait_for_timeout(400)
        scrolls = pg.evaluate("(() => { const g = document.getElementById('grid'); return g.scrollHeight > g.clientHeight + 10; })()")
        check("tablet: the picture's grid scrolls", scrolls)
        pg.screenshot(path=str(SHOTS / "tablet.png"))
        frow(pg, "Grade 11").click(); pg.wait_for_timeout(300)
        check("tablet: the folder picture has no .where line", pg.locator("#grid .where").count() == 0)
        pg.screenshot(path=str(SHOTS / "tablet-folder.png"))
        ctx.close()

        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, device_scale_factor=2)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SHOT_SEED); pg.reload(); ready(pg); pg.wait_for_timeout(400)
        pg.screenshot(path=str(SHOTS / "phone.png"))
        pg.tap("#gridBack"); pg.wait_for_timeout(SLIDE)
        pg.screenshot(path=str(SHOTS / "phone-drawer.png"))
        light_all, light_loose = bg(pg, ".frow.all"), bg(pg, ".frow.loose")
        pg.evaluate("localStorage.setItem('penworks.theme', 'dark')"); pg.reload(); ready(pg); pg.wait_for_timeout(300)
        check("dark: data-theme is dark", pg.evaluate("document.documentElement.dataset.theme") == "dark")
        pg.tap("#gridBack"); pg.wait_for_timeout(SLIDE); s = state(pg)
        check("dark: the drawer and the veil render", s["drawer"] and abs(s["side"]["l"]) < 0.5 and s["veilShown"]
              and bg(pg, "#side") == "rgb(34, 38, 43)", [s, bg(pg, "#side")])
        dark_all, dark_loose = bg(pg, ".frow.all"), bg(pg, ".frow.loose")
        check("dark: the All notes row's .sel tint shows (differs from the Loose row)", dark_all != dark_loose
              and dark_all not in ("rgba(0, 0, 0, 0)", "transparent"), [dark_all, dark_loose])
        check("light: the same tint shows", light_all != light_loose, [light_all, light_loose])
        pg.screenshot(path=str(SHOTS / "phone-dark.png"))
        check("no page errors (pictures)", not errs, errs)
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
