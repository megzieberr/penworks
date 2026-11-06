# PenWorks pw-v9b checks: Select, Move, Merge on the notes grid, and To note in the page list's Select (her ask 4, 6 Nov).
# Run: python tests/test_selectmerge.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds two folders (Algebra, Geometry) and five notes (Note A to Note E) with two or three pages each and one stroke on
# every page into the localStorage twin. At 1280 x 800: Select in the grid bar (All notes, Loose, a folder, never the
# Bin), the ticks and their order badges, All, a long press, Move to..., Put in the Bin, Merge with its Undo, a merge left
# alone past 8 s and its emptied note restored from the Bin, Escape and a folder pick ending select mode, the page list's
# To note with its picker and Undo. At 390 x 844: the bars fit, the badges show, the drawer button still works.
# Dark mode: a ticked card's outline and badge differ from an unticked one. The proof pictures go to _build/selectmerge/shots/.
import sys, subprocess, time, pathlib, re, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8825
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "selectmerge" / "shots"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-01T08:00:00Z';
  const F = (id, name, colour, position) => ({ id, parent_id: null, name, colour, position, deleted_at: null, created_at: t, updated_at: t });
  const N = (id, folder_id, name, upd) => ({ id, folder_id, name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: upd });
  const P = (id, note_id, position, background) => ({ id, note_id, position, orientation: 'portrait', background, bookmark: false,
    deleted_at: null, created_at: t, updated_at: t });
  const pages = [], strokes = [];
  const counts = { A: 3, B: 2, C: 3, D: 3, E: 2 };
  let seq = 0;
  for (const [k, n] of Object.entries(counts)) for (let i = 1; i <= n; i++) {
    const pid = 'p' + k + i;
    pages.push(P(pid, 'n' + k, i - 1, i % 2 ? 'grid' : 'lined'));
    strokes.push({ id: 's' + k + i, page_id: pid, seq: ++seq, kind: 'pen', style: { colour: '#2F4BB8', width: 2.5, dash: 'solid', opacity: 1 },
      data: { points: [[120 + 40 * i, 220], [300, 300 + 30 * i], [520, 260], [640, 420 + 20 * i]] } });
  }
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [F('f1', 'Algebra', '#3A86D6', 0), F('f2', 'Geometry', '#E0524A', 1)],
    notes: [N('nA', 'f1', 'Note A', '2026-11-05T09:00:00Z'), N('nB', 'f1', 'Note B', '2026-11-04T09:00:00Z'),
            N('nC', 'f2', 'Note C', '2026-11-03T09:00:00Z'), N('nD', null, 'Note D', '2026-11-02T09:00:00Z'),
            N('nE', 'f2', 'Note E', '2026-11-01T09:00:00Z')],
    pages, strokes }));
}"""

GRID = """() => ({ gsel: document.body.classList.contains('gsel'), title: document.getElementById('gridTitle').textContent,
  select: !!document.getElementById('gridSelect'), done: !!document.getElementById('gridDone'), all: !!document.getElementById('gridAll'),
  acts: document.getElementById('gridActs').hidden ? null : [...document.querySelectorAll('#gridActs .plAct')].map((b) => [b.dataset.act, b.disabled]),
  badges: Object.fromEntries([...document.querySelectorAll('#grid .card:not(.plus)')].map((c) => [c.querySelector('.name').textContent,
    c.classList.contains('ticked') ? c.querySelector('.gtick b').textContent : ''])),
  ticks: [...document.querySelectorAll('#grid .card .gtick')].filter((g) => getComputedStyle(g).display !== 'none').length,
  plusOpacity: [...document.querySelectorAll('#grid .card.plus')].map((c) => getComputedStyle(c).opacity),
  ids: window.__pw.S.gsel ? window.__pw.S.gsel.ids.slice() : null })"""
TWIN = "() => JSON.parse(localStorage.getItem('penworks.local.v2'))"
LIVE = """(nid) => window.__pw.S.pages.filter((p) => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position)
  .map((p) => [p.id, p.position])"""
NOTE = "(id) => { const n = window.__pw.S.notes.find((x) => x.id === id); return { folder: n.folder_id, deleted: !!n.deleted_at }; }"
TOAST = """() => { const t = document.getElementById('toast'); return { text: (t.firstChild && t.firstChild.nodeType === 3 ? t.firstChild.textContent : t.textContent),
  undo: !!t.querySelector('.toastAct'), shown: t.classList.contains('show') }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def grid(pg): return pg.evaluate(GRID)
def toast(pg): return pg.evaluate(TOAST)
def live(pg, nid): return pg.evaluate(LIVE, nid)
def noteof(pg, nid): return pg.evaluate(NOTE, nid)
def twin(pg): return pg.evaluate(TWIN)
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def card(pg, name): return pg.locator("#grid .card").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def tap(pg, *names):
    for n in names: card(pg, n).click(); pg.wait_for_timeout(40)
def act(pg, name): pg.click(f"#gridActs button[data-act='{name}']"); pg.wait_for_timeout(80)
def menu_items(pg): return [t_.strip() for t_ in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def menu_click(pg, label): pg.get_by_role("menuitem", name=label, exact=True).click(); pg.wait_for_timeout(80)
def long_press(pg, name):
    b = card(pg, name).locator(".thumb").bounding_box()
    pg.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2); pg.mouse.down(); pg.wait_for_timeout(700); pg.mouse.up(); pg.wait_for_timeout(80)
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def open_note_card(pg, name):
    card(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(120)
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(100)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------ tablet: the Select word and the ticks
        group[0] = "tablet select"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg); pg.wait_for_timeout(200)
        g = grid(pg)
        check("All notes: Select in the grid bar, no select mode yet", g["select"] and not g["gsel"] and g["acts"] is None, g)
        frow(pg, "Loose").click(); pg.wait_for_timeout(80)
        check("Loose: Select shows", grid(pg)["select"])
        frow(pg, "Algebra").click(); pg.wait_for_timeout(80)
        check("a folder: Select shows", grid(pg)["select"])
        frow(pg, "Bin").click(); pg.wait_for_timeout(80)
        check("the Bin: no Select", not grid(pg)["select"] and pg.locator("#gridBar .plWord").count() == 0)
        frow(pg, "All notes").click(); pg.wait_for_timeout(80)
        pg.click("#gridSelect"); pg.wait_for_timeout(80); g = grid(pg)
        check("tap Select: '0 selected', All and Done, body.gsel", g["gsel"] and g["title"] == "0 selected" and g["all"] and g["done"] and not g["select"], g)
        check("every note card shows its tick circle", g["ticks"] == 5, g["ticks"])
        check("the New note and Open PDF tiles fade", g["plusOpacity"] == ["0.35", "0.35"], g["plusOpacity"])
        check("the three action words, all disabled", g["acts"] == [["move", True], ["merge", True], ["bin", True]], g["acts"])
        bin_col = pg.evaluate("getComputedStyle(document.querySelector('#gridActs .plAct.bin')).color")

        tap(pg, "Note A", "Note B", "Note C"); g = grid(pg)
        check("tick A, B, C: badges 1, 2, 3", g["badges"]["Note A"] == "1" and g["badges"]["Note B"] == "2" and g["badges"]["Note C"] == "3"
              and g["badges"]["Note D"] == "" and g["title"] == "3 selected", g["badges"])
        check("three ticked: Move, Merge and the Bin enabled", g["acts"] == [["move", False], ["merge", False], ["bin", False]], g["acts"])
        check("the Bin word is red when enabled", pg.evaluate("getComputedStyle(document.querySelector('#gridActs .plAct.bin')).color") == "rgb(178, 58, 58)",
              [bin_col, pg.evaluate("getComputedStyle(document.querySelector('#gridActs .plAct.bin')).color")])
        check("a tap on a card in select mode does not open the note", pg.locator("#noteView").is_hidden())
        pg.screenshot(path=str(SHOTS / "tablet-select.png"))
        tap(pg, "Note B"); g = grid(pg)
        check("untick B: A reads 1, C reads 2", g["badges"]["Note A"] == "1" and g["badges"]["Note C"] == "2" and g["badges"]["Note B"] == "", g["badges"])
        tap(pg, "Note A"); g = grid(pg)
        check("one ticked: Merge disabled, Move and the Bin enabled", g["acts"] == [["move", False], ["merge", True], ["bin", False]], g["acts"])
        pg.click("#gridAll"); pg.wait_for_timeout(60); g = grid(pg)
        check("All ticks every note", len(g["ids"]) == 5 and g["title"] == "5 selected", g)
        pg.click("#gridAll"); pg.wait_for_timeout(60); g = grid(pg)
        check("All again: none", g["ids"] == [] and g["title"] == "0 selected", g)
        pg.click("#gridDone"); pg.wait_for_timeout(60); g = grid(pg)
        check("Done ends select mode", not g["gsel"] and g["select"] and g["title"] == "All notes" and g["ids"] is None, g)

        long_press(pg, "Note D"); g = grid(pg)
        check("a long press outside select mode: select mode with that card ticked", g["gsel"] and g["ids"] == ["nD"] and g["badges"]["Note D"] == "1"
              and pg.locator("#menu").is_hidden(), g)
        long_press(pg, "Note A"); g = grid(pg)
        check("a long press inside select mode: no menu, nothing new", pg.locator("#menu").is_hidden() and g["ids"] == ["nD"], g)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(60); g = grid(pg)
        check("Escape ends select mode", not g["gsel"] and g["ids"] is None, g)
        card(pg, "Note D").click(button="right"); pg.wait_for_timeout(80)
        check("a mouse right-click outside select mode keeps the note's menu (Rename, Move to..., Pin, Bin)",
              "Rename" in menu_items(pg) and not grid(pg)["gsel"], menu_items(pg))
        pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
        pg.click("#gridSelect"); pg.wait_for_timeout(40); tap(pg, "Note D")
        frow(pg, "Algebra").click(); pg.wait_for_timeout(80); g = grid(pg)
        check("a folder pick in the side list ends select mode", not g["gsel"] and g["title"] == "Algebra", g)
        frow(pg, "All notes").click(); pg.wait_for_timeout(60)

        # ------------------------------------------------------------ Move to...
        group[0] = "tablet move + bin"
        pg.click("#gridSelect"); pg.wait_for_timeout(40); tap(pg, "Note A", "Note B")
        act(pg, "move"); items = menu_items(pg)
        check("Move to...: Algebra (where both are) is left out; Loose and Geometry offered", "Algebra" not in items
              and "Loose" in items and "Geometry" in items, items)
        menu_click(pg, "Geometry"); idle(pg); g = grid(pg)
        check("the pick moves both (folder_id in the store)", noteof(pg, "nA")["folder"] == "f2" and noteof(pg, "nB")["folder"] == "f2")
        tw = {n["id"]: n for n in twin(pg)["notes"]}
        check("and in the twin", tw["nA"]["folder_id"] == "f2" and tw["nB"]["folder_id"] == "f2")
        check("toast 'Moved 2 notes to Geometry'", toast(pg)["text"] == "Moved 2 notes to Geometry", toast(pg))
        check("select mode ended, the grid re-rendered with the new places", not g["gsel"]
              and card(pg, "Note A").locator(".where").inner_text() == "Geometry", g)

        # ------------------------------------------------------------ Put in the Bin
        pg.click("#gridSelect"); pg.wait_for_timeout(40); tap(pg, "Note D", "Note E")
        act(pg, "bin"); idle(pg)
        check("Put in the Bin: both notes have deleted_at", noteof(pg, "nD")["deleted"] and noteof(pg, "nE")["deleted"])
        check("one toast '2 notes put in the Bin'", toast(pg)["text"] == "2 notes put in the Bin", toast(pg))
        check("select mode ended", not grid(pg)["gsel"])
        frow(pg, "Bin").click(); pg.wait_for_timeout(80)
        names = pg.locator("#grid .binItem b").all_inner_texts()
        check("the Bin lists them", "Note D" in names and "Note E" in names, names)
        pg.locator("#grid .binItem[data-id='nD'] button").click(); idle(pg)
        check("Restore brings Note D back with its pages", not noteof(pg, "nD")["deleted"] and len(live(pg, "nD")) == 3, live(pg, "nD"))
        frow(pg, "All notes").click(); pg.wait_for_timeout(60)

        # ------------------------------------------------------------ Merge and Undo
        group[0] = "tablet merge"
        a0, b0, c0 = live(pg, "nA"), live(pg, "nB"), live(pg, "nC")
        pg.click("#gridSelect"); pg.wait_for_timeout(40); tap(pg, "Note A", "Note B", "Note C")
        act(pg, "merge")
        title = pg.inner_text("#mergeTitle") if pg.locator("#mergeTitle").count() else ""
        text = pg.inner_text("#mergeText") if pg.locator("#mergeText").count() else ""
        check("the Merge dialog's title names A", title == "Merge 3 notes into Note A?", title)
        check("its paragraph names the order", text.startswith("Its pages come first, then Note B, then Note C, in the order you tapped them.")
              and "two emptied notes go to the Bin" in text, text)
        pg.evaluate("document.getElementById('toast').classList.remove('show')")   # an older toast out of the picture
        pg.screenshot(path=str(SHOTS / "tablet-merge.png"))
        pg.click("#mergeDlg [data-merge='ok']"); pg.wait_for_timeout(120)
        merged = live(pg, "nA")
        want = [x[0] for x in a0 + b0 + c0]
        check("A has all the pages: A's, then B's, then C's", [x[0] for x in merged] == want, [merged, want])
        pos = [x[1] for x in merged]
        check("the order values are strictly increasing", all(pos[i] < pos[i + 1] for i in range(len(pos) - 1)), pos)
        check("B and C are in the Bin with no live pages", noteof(pg, "nB")["deleted"] and noteof(pg, "nC")["deleted"]
              and live(pg, "nB") == [] and live(pg, "nC") == [])
        t_ = toast(pg)
        check("the toast carries Undo", t_["undo"] and t_["shown"] and t_["text"] == "3 notes merged into Note A", t_)
        check("select mode ended, Note A's card still there", not grid(pg)["gsel"] and card(pg, "Note A").count() == 1)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(SHOTS / "tablet-after.png"))
        idle(pg); d = twin(pg)
        tp = {p["id"]: p for p in d["pages"]}
        st = [s for s in d["strokes"] if s["id"] == "sB1"]
        check("the ink of B's first page now sits on a page of A (stroke page_id unchanged, that page's note_id = A)",
              st and st[0]["page_id"] == "pB1" and tp["pB1"]["note_id"] == "nA", [st, tp.get("pB1")])
        check("the twin's rows agree (A has 8 live pages there)", len([p for p in d["pages"] if p["note_id"] == "nA" and not p["deleted_at"]]) == 8)
        pg.click("#toast .toastAct"); pg.wait_for_timeout(120); idle(pg)
        check("Undo: B and C live again with their own pages in their old order", not noteof(pg, "nB")["deleted"] and not noteof(pg, "nC")["deleted"]
              and live(pg, "nB") == b0 and live(pg, "nC") == c0, [live(pg, "nB"), b0, live(pg, "nC"), c0])
        check("Undo: A back to its own pages", live(pg, "nA") == a0, live(pg, "nA"))
        check("toast 'Merge undone'", toast(pg)["text"] == "Merge undone", toast(pg))
        d = twin(pg)
        check("the twin agrees after Undo", sorted(p["id"] for p in d["pages"] if p["note_id"] == "nB" and not p["deleted_at"]) == ["pB1", "pB2"]
              and not [n for n in d["notes"] if n["id"] == "nB"][0]["deleted_at"])

        # merge again and let the 8 s pass
        pg.click("#gridSelect"); pg.wait_for_timeout(40); tap(pg, "Note A", "Note B")
        act(pg, "merge")
        text2 = pg.inner_text("#mergeText")
        check("two notes: the paragraph says 'The emptied note goes to the Bin.'", "The emptied note goes to the Bin." in text2, text2)
        pg.click("#mergeDlg [data-merge='ok']"); pg.wait_for_timeout(8400)
        check("after 8 s the toast and its Undo are gone", not toast(pg)["shown"], toast(pg))
        idle(pg); pg.reload(); ready(pg); pg.wait_for_timeout(200)
        check("after a reload A still has its 5 pages (the twin kept the note_id op)", len(live(pg, "nA")) == 5, live(pg, "nA"))
        frow(pg, "Bin").click(); pg.wait_for_timeout(80)
        pg.locator("#grid .binItem[data-id='nB'] button").click(); idle(pg)
        check("the Bin's Restore on B gives a live note with no pages", not noteof(pg, "nB")["deleted"] and live(pg, "nB") == [])
        frow(pg, "All notes").click(); pg.wait_for_timeout(60)
        n_err = len(errs)
        open_note_card(pg, "Note B")
        check("opening the empty note does not throw, and it gets one blank page", len(errs) == n_err and len(live(pg, "nB")) == 1
              and pg.locator("#stack .sheet").count() == 1, [errs[n_err:], live(pg, "nB")])
        back(pg)

        # ------------------------------------------------------------ the page list: To note
        group[0] = "page list To note"
        open_note_card(pg, "Note D")
        pg.click("#listBtn"); pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(260)
        pg.click("#plSelect"); pg.wait_for_timeout(40)
        d0, a_before = live(pg, "nD"), live(pg, "nA")
        thumb(pg, 1).click(); thumb(pg, 2).click(); pg.wait_for_timeout(40)
        tn = pg.locator("#plBar button[data-act='tonote']")
        check("'To note' sits after Move in the bar", pg.evaluate("[...document.querySelectorAll('#plBar .plAct')].map(b => b.dataset.act)")[:5]
              == ["delete", "copy", "cut", "move", "tonote"])
        check("two of three ticked: To note enabled", tn.is_enabled())
        bar = pg.evaluate("(() => { const b = document.getElementById('plBar'); return [b.scrollWidth, b.clientWidth, b.getBoundingClientRect().height]; })()")
        check("the bar fits on one row (no overflow)", bar[0] <= bar[1] + 1 and bar[2] < 70, bar)
        pg.click("#plAll"); pg.wait_for_timeout(40)
        check("every page ticked: To note disabled", not tn.is_enabled())
        pg.click("#plAll"); pg.wait_for_timeout(40)
        thumb(pg, 1).click(); thumb(pg, 2).click(); pg.wait_for_timeout(40)
        tn.click(); pg.wait_for_timeout(150)
        pick_ids = pg.evaluate("[...document.querySelectorAll('#pickGrid .card')].map(c => c.dataset.id)")
        check("the picker: every live note but the open one", "nD" not in pick_ids and "nA" in pick_ids and "nC" in pick_ids, pick_ids)
        check("its title and line", pg.inner_text("#pickTitle") == "Move 2 pages to"
              and "They land at the end of the note you pick." in pg.inner_text("#pickNote"), pg.inner_text("#pickTitle"))
        pg.evaluate("document.getElementById('toast').classList.remove('show')")   # an older toast out of the picture
        pg.screenshot(path=str(SHOTS / "pagelist-picker.png"))
        pg.click("#pickGrid .card[data-id='nA']"); pg.wait_for_timeout(200); idle(pg)
        a_after, d_after = live(pg, "nA"), live(pg, "nD")
        check("the pages are at the END of A, in order", [x[0] for x in a_after] == [x[0] for x in a_before] + [d0[0][0], d0[1][0]]
              and all(a_after[i][1] < a_after[i + 1][1] for i in range(len(a_after) - 1)), a_after)
        check("D renumbered without gaps", d_after == [[d0[2][0], 0]], d_after)
        check("the list shows the remaining page, tick mode ended", pg.locator("#plThumbs .thumbP").count() == 1
              and pg.evaluate("window.__pw.tick()") is None and pg.locator("#pageList").is_visible())
        check("the big page stack has 1 page", pg.locator("#stack .sheet").count() == 1)
        check("toast '2 pages moved to Note A' with Undo", toast(pg)["text"] == "2 pages moved to Note A" and toast(pg)["undo"], toast(pg))
        pg.click("#toast .toastAct"); pg.wait_for_timeout(200); idle(pg)
        check("Undo puts them back where they were", live(pg, "nD") == d0 and live(pg, "nA") == a_before, [live(pg, "nD"), live(pg, "nA")])
        check("and the list and stack show 3 again", pg.locator("#plThumbs .thumbP").count() == 3 and pg.locator("#stack .sheet").count() == 3)
        d = twin(pg)
        check("the twin agrees after Undo", sorted((p["id"], p["position"]) for p in d["pages"] if p["note_id"] == "nD") == sorted(tuple(x) for x in d0))
        check("no page errors (tablet)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ dark mode
        group[0] = "dark"
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, color_scheme="dark")
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg); pg.wait_for_timeout(200)
        pg.click("#gridSelect"); pg.wait_for_timeout(40); tap(pg, "Note A", "Note C")
        look = pg.evaluate("""() => { const c = (n) => [...document.querySelectorAll('#grid .card')].find((x) => x.querySelector('.name') && x.querySelector('.name').textContent === n);
          const o = (n) => { const t = c(n).querySelector('.thumb'); const s = getComputedStyle(t); return s.outlineStyle + ' ' + s.outlineColor; };
          const g = (n) => getComputedStyle(c(n).querySelector('.gtick'), '::before').backgroundColor;
          const r = (n) => c(n).querySelector('.gtick b').getBoundingClientRect();
          return { on: o('Note A'), off: o('Note B'), gOn: g('Note A'), gOff: g('Note B'), badge: getComputedStyle(c('Note A').querySelector('.gtick b')).visibility,
                   w: r('Note A').width }; }""")
        check("dark: a ticked card's outline differs from an unticked one", look["on"] != look["off"] and "solid" in look["on"], look)
        check("dark: the ticked badge's fill differs and its number shows", look["gOn"] != look["gOff"] and look["badge"] == "visible" and look["w"] > 0, look)
        pg.screenshot(path=str(SHOTS / "tablet-dark.png"))
        check("no page errors (dark)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ phone
        group[0] = "phone 390x844"
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg); pg.wait_for_timeout(200)
        pg.click("#gridSelect"); pg.wait_for_timeout(40); tap(pg, "Note A", "Note B")
        fit = pg.evaluate("""() => ['gridBar', 'gridActs'].map((id) => { const e = document.getElementById(id); const r = e.getBoundingClientRect();
          return [id, e.scrollWidth, e.clientWidth, Math.round(r.right)]; })""")
        check("the grid bar and the action bar fit (no horizontal overflow)", all(x[1] <= x[2] + 1 and x[3] <= 390 for x in fit), fit)
        vis = pg.evaluate("""() => [...document.querySelectorAll('#grid .card.ticked .gtick b')].map((b) => { const r = b.getBoundingClientRect();
          return [b.textContent, r.width > 0 && r.right <= innerWidth && r.left >= 0, getComputedStyle(b).visibility]; })""")
        check("the badges 1 and 2 are visible", [v[0] for v in vis] == ["1", "2"] and all(v[1] and v[2] == "visible" for v in vis), vis)
        pg.screenshot(path=str(SHOTS / "phone-select.png"))
        pg.tap("#gridBack"); pg.wait_for_timeout(350)
        check("the drawer button still opens the drawer in select mode", pg.evaluate("document.body.classList.contains('drawer')")
              and grid(pg)["gsel"])
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
