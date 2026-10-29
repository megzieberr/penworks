# PenWorks U1b checks: headless Playwright (Python), same style as the U1 checks it replaces.
# Run: python tests/test_u1b.py            (every group, live included)
#      python tests/test_u1b.py --no-live  (skip the live Supabase group)
#      add --shots <folder> for two small screenshots
# The live group logs in with a throwaway test account read from the environment (PW_TEST_USER,
# PW_TEST_PASS) or from the gitignored .env file in the app folder. Neither is ever printed. It makes a
# "U1b test" folder > note > 2 pages, bins and restores it, then deletes every row it made.
import sys, os, subprocess, time, pathlib, re
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8773
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
LIVE = "--no-live" not in sys.argv

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SIDE_JS = """() => {
  const c = (r) => r ? +r.querySelector('.count').textContent : null;
  const out = { loose: c(document.querySelector('.frow.loose')), bin: c(document.querySelector('.frow.bin')), folders: {} };
  document.querySelectorAll('.fbox[data-id]').forEach((b) => {
    const row = b.querySelector(':scope > .frow'), kids = b.querySelector(':scope > .kids');
    out.folders[row.querySelector('.name').textContent] = { count: c(row), depth: +row.dataset.depth, open: !!kids,
      notes: kids ? [...kids.querySelectorAll(':scope > .nrow')].map((n) => [n.querySelector('.name').textContent, +n.querySelector('.pc').textContent]) : [] };
  });
  const lk = document.querySelector('.fbox.loose > .kids');
  out.looseNotes = lk ? [...lk.querySelectorAll('.nrow .name')].map((e) => e.textContent) : [];
  return out;
}"""
GRID_JS = "() => [...document.querySelectorAll('#grid .card:not(.plus)')].map(c => c.querySelector('.name').textContent)"
STACK_JS = "() => [...document.querySelectorAll('#stack .sheet')].map(s => [s.dataset.id, s.offsetWidth, s.dataset.bg])"
ORDER_JS = """(name) => { const S = window.__pw.S, n = S.notes.find(x => x.name === name && !x.deleted_at);
  return S.pages.filter(p => p.note_id === n.id && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id); }"""
STORED_JS = """async (name) => { const d = await window.__pw.api.loadAll(), n = d.notes.find(x => x.name === name && !x.deleted_at);
  return d.pages.filter(p => p.note_id === n.id && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id); }"""
# pw-v4r: her page bookmark (26 Oct, the newer ruling) is the one exception: the ribbon tab on a bookmarked page (#stack)
# or its thumb (#plThumbs) and the page list's Bookmarks toggle (#plMarks). Anything else bookmark- or ribbon-named fails.
NO_RIBBON_JS = """() => [...document.querySelectorAll('*')].filter(e =>
  !(e.closest('.bookmarkTab') && e.closest('#stack, #plThumbs')) && e.id !== 'plMarks' &&
  /ribbon|bookmark/i.test((typeof e.className === 'string' ? e.className : (e.className && e.className.baseVal) || '') + ' ' + e.id + ' '
    + (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || ''))).map(e => e.tagName + '#' + e.id)"""

def side(pg): return pg.evaluate(SIDE_JS)
def grid(pg): return pg.evaluate(GRID_JS)
def stack(pg): return pg.evaluate(STACK_JS)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
# the paper's lines, read from its patterns (one pattern + rect per direction): every line position
# (x for class gv, y for gh and ln) that the rect lets show, in page px
LINES_JS = r"""([i, cls]) => {
  const svg = document.querySelectorAll('#stack .sheet')[i].querySelector('svg[data-bg]'), out = [];
  for (const r of svg.querySelectorAll(`rect.${cls}`)) {
    const p = svg.querySelector('#' + CSS.escape(/url\(#(.+)\)/.exec(r.getAttribute('fill'))[1])), l = p.querySelector('line');
    const v = l.getAttribute('x1') === l.getAttribute('x2');
    const step = +p.getAttribute(v ? 'width' : 'height'), at = +p.getAttribute(v ? 'x' : 'y') + +l.getAttribute(v ? 'x1' : 'y1');
    const lo = +r.getAttribute(v ? 'x' : 'y'), hi = lo + +r.getAttribute(v ? 'width' : 'height');
    for (let k = Math.ceil((lo - at) / step - 1e-6); at + k * step <= hi + 0.01; k++) out.push(+(at + k * step).toFixed(3));
  }
  return out;
}"""
def paper_lines(pg, i, cls): return pg.evaluate(LINES_JS, [i, cls])
def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def menu_items(pg): return [t.strip() for t in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def menu(pg, label): pg.locator("#menu button", has_text=label).first.click()
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def card(pg, name): return pg.locator("#grid .card").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")
def rename_open_note(pg, text):
    pg.click("#noteName .nn"); type_name(pg, text)
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def count_text(pg): return pg.inner_text("#counter")
def wheel(pg, dy):
    b = pg.locator("#desk").bounding_box(); pg.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2); pg.mouse.wheel(0, dy)
    pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def drag_thumb(pg, i, j):          # hold thumbnail i (mouse = finger = S Pen: pointer events), drag it onto slot j
    a, c = thumb(pg, i).bounding_box(), thumb(pg, j).bounding_box()
    pg.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2); pg.mouse.down(); pg.wait_for_timeout(450)
    pg.mouse.move(c["x"] + c["width"] / 2, c["y"] + c["height"] / 2, steps=8); pg.mouse.up(); pg.wait_for_timeout(60)

def creds():
    u, p = os.environ.get("PW_TEST_USER"), os.environ.get("PW_TEST_PASS")
    env = ROOT / ".env"
    if (not u or not p) and env.exists():
        kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        u, p = kv.get("PW_TEST_USER", "").strip(), kv.get("PW_TEST_PASS", "").strip()
    return u, p

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # ------------------------------------------------------------ folder view (local mode)
        group[0] = "folder view"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        s = side(pg)
        check("starts empty: Loose 0, Bin 0, no folders", s["loose"] == 0 and s["bin"] == 0 and not s["folders"], s)
        pg.click("#addFolder"); type_name(pg, "Grade 9")
        frow(pg, "Grade 9").locator(".more").click(); menu(pg, "New folder inside"); type_name(pg, "Term 1")
        frow(pg, "Term 1").locator(".more").click(); menu(pg, "New note")
        pg.wait_for_selector("#noteView:not([hidden])"); rename_open_note(pg, "Algebra"); back(pg)
        pg.wait_for_timeout(30)
        frow(pg, "Term 1").locator(".more").click(); menu(pg, "New note")
        pg.wait_for_selector("#noteView:not([hidden])"); rename_open_note(pg, "Geometry"); pg.click("#addPageBtn"); pg.click("#menu button:text-is('Page')"); back(pg)
        pg.wait_for_timeout(30)
        frow(pg, "Loose").click(); pg.click("#newNote"); pg.wait_for_selector("#noteView:not([hidden])")
        rename_open_note(pg, "Loose one"); back(pg); idle(pg)
        s = side(pg)
        f9, t1 = s["folders"].get("Grade 9", {}), s["folders"].get("Term 1", {})
        check("Grade 9 > Term 1: two levels", f9.get("depth") == 0 and t1.get("depth") == 1, s)
        check("note names under Term 1 with page counts (last edited first)", t1.get("notes") == [["Geometry", 2], ["Algebra", 1]], t1)
        check("counts: Term 1 = 2, Grade 9 = 2, Loose = 1", t1.get("count") == 2 and f9.get("count") == 2 and s["loose"] == 1, s)
        check("Loose shows its note name", s["looseNotes"] == ["Loose one"], s["looseNotes"])
        frow(pg, "Term 1").locator(".chev").click()
        s = side(pg)
        check("fold Term 1 shut: names hidden, count stays", not s["folders"]["Term 1"]["open"] and s["folders"]["Term 1"]["count"] == 2, s)
        pg.reload(); ready(pg)
        check("reload keeps it folded", not side(pg)["folders"]["Term 1"]["open"])
        frow(pg, "Term 1").locator(".chev").click()
        pg.reload(); ready(pg)
        s = side(pg)
        check("unfold, reload keeps it open with both names", s["folders"]["Term 1"]["open"] and len(s["folders"]["Term 1"]["notes"]) == 2, s)

        # ------------------------------------------------------------ the grid
        group[0] = "grid"
        frow(pg, "Term 1").click()
        check("Term 1 selected: soft tint on its row", "sel" in (frow(pg, "Term 1").get_attribute("class") or ""))
        check("two cards plus the + card and the Open PDF tile (U4a)", grid(pg) == ["Geometry", "Algebra"] and pg.locator("#grid .card.plus").count() == 2, grid(pg))
        whens = pg.locator("#grid .card .when").all_inner_texts()
        check("last-edited time shows (today = hh:mm)", len(whens) == 2 and all(re.match(r"^\d\d:\d\d$", w) for w in whens), whens)
        pg.wait_for_timeout(30)
        pg.click("#newNote"); pg.wait_for_selector("#noteView:not([hidden])")
        check("+ makes Untitled with one page and opens it", pg.inner_text("#noteName") == "Untitled" and len(stack(pg)) == 1, [pg.inner_text("#noteName"), len(stack(pg))])
        back(pg)
        check("newest first", grid(pg) == ["Untitled", "Geometry", "Algebra"], grid(pg))
        pg.wait_for_timeout(30)
        card(pg, "Untitled").click(button="right"); menu(pg, "Rename"); type_name(pg, "Revision"); idle(pg)
        check("rename from the card", grid(pg) == ["Revision", "Geometry", "Algebra"], grid(pg))
        before = pg.evaluate("window.__pw.S.notes.find(n => n.name === 'Algebra').updated_at")
        card(pg, "Algebra").click(button="right"); menu(pg, "Pin to top"); idle(pg)
        check("pin the oldest: it jumps to the top", grid(pg) == ["Algebra", "Revision", "Geometry"], grid(pg))
        check("pinned card shows the pin mark", card(pg, "Algebra").locator(".pin").count() == 1 and pg.locator("#grid .card .pin").count() == 1)
        check("pinning is not an edit", pg.evaluate("window.__pw.S.notes.find(n => n.name === 'Algebra').updated_at") == before)
        pg.reload(); ready(pg)
        check("pin survives a reload", grid(pg) == ["Algebra", "Revision", "Geometry"], grid(pg))
        card(pg, "Algebra").click(button="right"); menu(pg, "Unpin"); idle(pg)
        check("unpin: it drops back", grid(pg) == ["Revision", "Geometry", "Algebra"], grid(pg))
        check("folder view uses the same order", side(pg)["folders"]["Term 1"]["notes"] == [["Revision", 1], ["Geometry", 2], ["Algebra", 1]])

        # ------------------------------------------------------------ folders: two levels, hard stop
        group[0] = "folders"
        frow(pg, "Grade 9").locator(".more").click(); top_items = menu_items(pg); pg.keyboard.press("Escape")
        frow(pg, "Term 1").locator(".more").click(); sub_items = menu_items(pg)
        check("top folder menu", top_items[:4] == ["Rename", "Colour", "New folder inside", "New note"] and "Put in the Bin" in top_items, top_items)
        check("sub-folder menu has no 'New folder inside'", "New folder inside" not in sub_items and "New note" in sub_items, sub_items)
        pg.keyboard.press("Escape")
        pg.click("#addFolder"); type_name(pg, "Grade 10")
        frow(pg, "Grade 10").locator(".more").click(); menu(pg, "Move to"); targets = [t for t in pg.locator("#menu button").all_inner_texts()]
        check("Move to never offers a sub-folder as a parent", targets == ["Grade 9"], targets)
        pg.keyboard.press("Escape")
        frow(pg, "Grade 9").locator(".more").click()
        check("a folder holding folders cannot move", "Move to..." not in menu_items(pg), menu_items(pg))
        pg.keyboard.press("Escape")
        frow(pg, "Grade 10").locator(".more").click(); menu(pg, "Move to"); menu(pg, "Grade 9"); idle(pg)
        s = side(pg)
        check("a folder inside a folder works (Grade 10 under Grade 9)", s["folders"]["Grade 10"]["depth"] == 1, s["folders"]["Grade 10"])
        frow(pg, "Grade 10").locator(".more").click(); items = menu_items(pg); menu(pg, "Move to")
        targets = pg.locator("#menu button").all_inner_texts()
        check("its menu: no 'New folder inside'; Move to = Top level only", "New folder inside" not in items and targets == ["Top level"], [items, targets])
        menu(pg, "Top level"); idle(pg)
        check("moved back to the top", side(pg)["folders"]["Grade 10"]["depth"] == 0)
        frow(pg, "Grade 10").locator(".more").click(); menu(pg, "Colour"); pg.locator("#menu .sw[aria-label='Blue']").click(); idle(pg)
        check("colour shows on the folder icon", frow(pg, "Grade 10").locator(".ico path").get_attribute("fill") == "#3A86D6")
        refused = pg.evaluate("""async () => {
          const S = window.__pw.S, a = window.__pw.api, t1 = S.folders.find(f => f.name === 'Term 1'), g9 = S.folders.find(f => f.name === 'Grade 9'),
                g10 = S.folders.find(f => f.name === 'Grade 10'), out = [];
          try { await a.createFolder({ id: crypto.randomUUID(), parent_id: t1.id, name: 'Too deep', position: 0 }); out.push('made'); } catch (e) { out.push(e.message); }
          try { await a.moveFolder(g9.id, g10.id, 0); out.push('moved'); } catch (e) { out.push(e.message); }
          const d = await a.loadAll();
          out.push(d.folders.some(f => f.name === 'Too deep'), d.folders.find(f => f.name === 'Grade 9').parent_id);
          return out; }""")
        check("API refuses a third level (local)", "two levels" in str(refused[0]) and refused[2] is False, refused)
        check("API refuses moving a folder that holds folders (local)", "cannot go inside" in str(refused[1]) and refused[3] is None, refused)

        # ------------------------------------------------------------ the note view
        group[0] = "note view"
        nrow(pg, "Algebra").click(); pg.wait_for_selector("#noteView:not([hidden])")
        check("the folder view is gone while a note is open", pg.locator("#side").is_hidden())
        for _ in range(3): pg.click("#addPageBtn"); pg.click("#menu button:text-is('Page')")
        idle(pg)
        ids = pg.evaluate(ORDER_JS, "Algebra")
        check("three pages added: 4 in the stack", len(ids) == 4 and len(stack(pg)) == 4, len(ids))
        wheel(pg, -100000)
        open_list(pg)
        check("page list: 4 numbered thumbnails and '1 / 4'", pg.locator("#plThumbs .thumbP").count() == 4 and pg.inner_text("#plCount") == "1 / 4",
              [pg.locator("#plThumbs .thumbP").count(), pg.inner_text("#plCount")])
        check("current thumbnail outlined", thumb(pg, 1).get_attribute("class").split().count("cur") == 1)
        pg.click("#plClose")
        wheel(pg, 100000)
        check("scrolled to the bottom: 4 / 4", count_text(pg) == "4 / 4", count_text(pg))
        open_list(pg); thumb(pg, 2).click(); pg.wait_for_timeout(80)
        check("tap thumbnail 2: page 2 is current, the list stays open (pw-v4i)", count_text(pg) == "2 / 4" and pg.locator("#pageList").is_visible(), count_text(pg))
        open_list(pg); thumb(pg, 4).click(button="right"); items = menu_items(pg)
        check("thumbnail menu: Add page, Copy, Cut, Delete, Erase page (no Move up / down: pages are dragged)",
              items == ["Add page", "Copy", "Cut", "Delete", "Erase page", "Share page"], items)
        pg.keyboard.press("Escape")
        drag_thumb(pg, 4, 3); idle(pg)
        moved = [ids[0], ids[1], ids[3], ids[2]]
        check("hold page 4 and drag it to slot 3", pg.evaluate(ORDER_JS, "Algebra") == moved and pg.evaluate(STORED_JS, "Algebra") == moved)
        thumb(pg, 3).click(button="right"); menu(pg, "Delete"); idle(pg)
        gone = [ids[0], ids[1], ids[2]]
        check("delete page 3: gone for good (no Bin)", pg.evaluate(STORED_JS, "Algebra") == gone
              and pg.evaluate(f"window.__pw.api.loadAll().then(d => d.pages.some(p => p.id === '{ids[3]}'))") is False)
        check("undo is lit after the delete", pg.locator("#undoBtn").is_enabled())
        pg.click("#undoBtn"); idle(pg)
        check("undo brings it back at position 3", pg.evaluate(STORED_JS, "Algebra") == moved and pg.locator("#plThumbs .thumbP").count() == 4,
              pg.evaluate(STORED_JS, "Algebra"))
        pg.click("#redoBtn"); idle(pg)
        check("redo deletes it again", pg.evaluate(STORED_JS, "Algebra") == gone)
        pg.click("#undoBtn"); idle(pg)
        back(pg)
        nrow(pg, "Loose one").click(); pg.wait_for_selector("#noteView:not([hidden])")
        open_list(pg); thumb(pg, 1).click(button="right"); items = menu_items(pg); pg.keyboard.press("Escape")
        check("the last page has no Delete", "Delete" not in items and "Add page" in items, items)
        pg.keyboard.press("Escape"); back(pg)

        # ------------------------------------------------------------ paper and orientation
        group[0] = "paper"
        nrow(pg, "Algebra").click(); pg.wait_for_selector("#noteView:not([hidden])")
        open_list(pg); thumb(pg, 2).click(); pg.wait_for_timeout(80)
        pg.click("#noteMore"); menu(pg, "Landscape"); items = menu_items(pg); menu(pg, "Just this page"); idle(pg)
        check("asks 'Just this page' or 'All pages'", items == ["Just this page", "All pages"], items)
        widths = [w for _, w, _ in stack(pg)]
        check("one wide sheet among portrait ones", widths == [794, 1123, 794, 794], widths)
        pg.click("#noteMore"); menu(pg, "Lined"); menu(pg, "All pages"); idle(pg)
        check("All pages lined: every page lined", [bg for _, _, bg in stack(pg)] == ["lined"] * 4, stack(pg))
        ys = paper_lines(pg, 0, 'ln')
        check("lined = the grid's rows apart (794 / 22)", len(ys) > 25 and all(abs(ys[i + 1] - ys[i] - 794 / 22) < 0.02 for i in range(len(ys) - 1)), len(ys))
        pg.click("#undoBtn"); idle(pg)
        check("undo puts the old paper back", [bg for _, _, bg in stack(pg)] == ["grid"] * 4, stack(pg))
        gx = paper_lines(pg, 0, 'gv')
        gy = paper_lines(pg, 0, 'gh')
        check("lined rows sit exactly on the grid rows (same start, same gap)", len(ys) > 25 and len(gy) >= len(ys) and all(abs(a - b) < 0.02 for a, b in zip(ys, gy)), (ys[:3], gy[:3]))
        gy = paper_lines(pg, 0, 'gh')
        lx = paper_lines(pg, 1, 'gv')
        ly = paper_lines(pg, 1, 'gh')
        P = 794 / 22
        check("grid portrait: 22 blocks across, pitch 794/22 px", len(gx) == 23 and gx[0] == 0 and abs(gx[-1] - 794) < 0.02
              and all(abs(gx[i + 1] - gx[i] - P) < 0.02 for i in range(len(gx) - 1)), gx[:3] + gx[-2:])
        check("grid: first line 6 mm (22.68 px) from the top, rows 794/22 px", abs(gy[0] - 0.6 * 96 / 2.54) < 0.02
              and all(abs(gy[i + 1] - gy[i] - P) < 0.02 for i in range(len(gy) - 1)), gy[:3])
        check("grid landscape: same pitch and top strip", len(lx) == 32 and lx[0] == 0 and abs(ly[0] - 0.6 * 96 / 2.54) < 0.02
              and all(abs(lx[i + 1] - lx[i] - P) < 0.02 for i in range(len(lx) - 1))
              and all(abs(ly[i + 1] - ly[i] - P) < 0.02 for i in range(len(ly) - 1)), (len(lx), lx[:2], ly[:2]))
        pg.click("#redoBtn"); idle(pg)
        xs = paper_lines(pg, 0, 'gv')
        pg.reload(); ready(pg)
        check("reload: note reopens, paper and orientation saved", pg.inner_text("#noteName") == "Algebra"
              and [bg for _, _, bg in stack(pg)] == ["lined"] * 4 and [w for _, w, _ in stack(pg)] == [794, 1123, 794, 794], stack(pg))

        # ------------------------------------------------------------ full screen
        group[0] = "full screen"
        pg.click("#fsBtn"); pg.wait_for_timeout(400)
        check("document.fullscreenElement is set", pg.evaluate("!!document.fullscreenElement"))
        check("header hidden, tray stays, collapse icon shows", pg.locator("#noteBar").is_hidden() and pg.locator("#tray").is_visible() and pg.locator("#exitFs").is_visible())
        pg.click("#exitFs"); pg.wait_for_timeout(400)
        check("exit restores the header", pg.locator("#noteBar").is_visible() and not pg.evaluate("!!document.fullscreenElement") and pg.locator("#exitFs").is_hidden())
        back(pg)

        # ------------------------------------------------------------ move, bin, restore
        group[0] = "move and bin"
        nrow(pg, "Loose one").locator(".more").click(); menu(pg, "Move to"); menu(pg, "Grade 9 / Term 1"); idle(pg)
        s = side(pg)
        check("note moved out of Loose: counts", s["loose"] == 0 and s["folders"]["Term 1"]["count"] == 4 and s["folders"]["Grade 9"]["count"] == 4, s)
        nrow(pg, "Loose one").locator(".more").click(); menu(pg, "Move to"); menu(pg, "Loose"); idle(pg)
        s = side(pg)
        check("and back to Loose", s["loose"] == 1 and s["folders"]["Term 1"]["count"] == 3, s)
        geo = pg.evaluate("window.__pw.S.notes.find(n => n.name === 'Geometry').id")
        nrow(pg, "Geometry").locator(".more").click(); menu(pg, "Bin"); idle(pg)
        s = side(pg)
        binned_pages = pg.evaluate(f"window.__pw.api.loadAll().then(d => d.pages.filter(p => p.note_id === '{geo}').map(p => !!p.deleted_at))")
        check("bin a note: its pages go with it", binned_pages == [True, True], binned_pages)
        check("counts after binning", s["bin"] == 1 and s["folders"]["Term 1"]["count"] == 2, s)
        frow(pg, "Bin").click()
        check("the Bin offers Restore only", pg.locator(".binItem button").all_inner_texts() == ["Restore"], pg.locator(".binItem button").all_inner_texts())
        pg.click(".binItem button"); idle(pg)
        s = side(pg)
        restored = pg.evaluate(f"window.__pw.api.loadAll().then(d => d.pages.filter(p => p.note_id === '{geo}').map(p => !!p.deleted_at))")
        check("restore brings it back with its pages", s["bin"] == 0 and s["folders"]["Term 1"]["count"] == 3 and restored == [False, False], [s, restored])
        frow(pg, "Grade 9").locator(".more").click(); menu(pg, "Bin"); idle(pg)
        s = side(pg)
        check("bin a folder: everything inside goes with it", "Grade 9" not in s["folders"] and "Term 1" not in s["folders"] and s["bin"] == 1 and s["loose"] == 1, s)
        frow(pg, "Bin").click(); pg.click(".binItem button"); idle(pg)
        s = side(pg)
        check("restore the folder: all of it back", s["folders"]["Grade 9"]["count"] == 3 and s["folders"]["Term 1"]["count"] == 3 and s["bin"] == 0, s)
        pg.evaluate("window.__pw.api.failNext(1)")
        nrow(pg, "Loose one").locator(".more").click(); menu(pg, "Rename"); type_name(pg, "Loose two")
        pg.wait_for_timeout(400)
        # U3e: a failed write is the dot's business (waiting, then saving on the retry), never a toast
        shown = pg.locator("#toast.show").inner_text() if pg.locator("#toast.show").count() else ""
        dot_state = pg.evaluate("document.getElementById('saveDot').dataset.state")
        check("a failed write shows no toast and the dot says waiting or saving",
              "saved" not in shown.lower() and dot_state in ("waiting", "saving"), [shown, dot_state])
        idle(pg); pg.reload(); ready(pg)
        check("the retry saved it", side(pg)["looseNotes"] == ["Loose two"] and pg.evaluate("window.__pw.failed()") == 0)
        check("no page errors (local)", not errs, errs)

        # ------------------------------------------------------------ tablet width
        group[0] = "tablet 1280x800"
        nrow(pg, "Loose two").click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(100)
        box = lambda sel: pg.locator(sel).bounding_box()
        d, tr, sh = box("#desk"), box("#tray"), box("#stack .sheet")
        check("stack and tray visible", tr["width"] == 56 and tr["x"] + 56 <= 1280.5 and d["width"] > 1100 and sh["width"] > 0, [d, tr])
        check("a portrait page fits at zoom 1", pg.evaluate("document.getElementById('stack').dataset.zoom") == "1.000"
              and sh["x"] - d["x"] >= 20 and (d["x"] + d["width"]) - (sh["x"] + sh["width"]) >= 20, [d, sh])
        check("counter sits bottom-right of the desk", box("#counter")["x"] > d["x"] + d["width"] - 140 and box("#counter")["y"] > d["y"] + d["height"] - 60)
        check("no horizontal scroll (tablet)", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        if SHOTS: pg.screenshot(path=str(SHOTS / "tablet-note.png"))
        group[0] = "no bookmark or ribbon"
        open_list(pg)
        found = pg.evaluate(NO_RIBBON_JS); back(pg); frow(pg, "Term 1").click(); found += pg.evaluate(NO_RIBBON_JS)
        check("nothing bookmark- or ribbon-named in the DOM (note, page list, grid)", not found, found)
        css = pg.evaluate("fetch('./css/app.css').then(r => r.text())")
        check("no clip-path ribbon shapes in the CSS", "clip-path" not in css and "--ribbon" not in css)
        ctx.close()

        # ------------------------------------------------------------ phone width
        group[0] = "phone 375x812"
        ctx = b.new_context(viewport={"width": 375, "height": 812}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("""() => { const t = '2026-10-23T10:00:00Z', P = (id, n, k, o) => ({ id, note_id: n, position: k, orientation: o || 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
          localStorage.setItem('penworks.local.v2', JSON.stringify({
            folders: [{ id: 'f1', parent_id: null, name: 'Uni 2026', colour: '#45A866', position: 0, deleted_at: null, created_at: t, updated_at: t }],
            notes: [{ id: 'n1', folder_id: 'f1', name: 'MATH121 limits', pinned: false, deleted_at: null, created_at: t, updated_at: t },
                    { id: 'n2', folder_id: 'f1', name: 'MATH121 series', pinned: false, deleted_at: null, created_at: t, updated_at: '2026-10-22T10:00:00Z' }],
            pages: [P('p1', 'n1', 0), P('p2', 'n1', 1, 'landscape'), P('p3', 'n1', 2), P('p4', 'n2', 0)] })); }""")
        pg.reload(); ready(pg)
        sd = pg.locator("#side").bounding_box()
        check("folder view is the whole screen", sd["x"] <= 0.5 and sd["width"] >= 374 and pg.locator("#main").is_hidden(), sd)
        check("note names show under the folder", side(pg)["folders"]["Uni 2026"]["notes"] == [["MATH121 limits", 3], ["MATH121 series", 1]])
        frow(pg, "Uni 2026").tap(); pg.wait_for_timeout(150)
        xs = pg.evaluate("[...document.querySelectorAll('#grid .card')].map(c => Math.round(c.getBoundingClientRect().x))")
        check("tap the folder: grid in one column (2 notes, New note, Open PDF)", pg.locator("#side").is_hidden() and len(xs) == 4 and len(set(xs)) == 1, xs)
        check("last edited shows as a date", pg.locator("#grid .card .when").all_inner_texts() == ["23 Oct", "22 Oct"], pg.locator("#grid .card .when").all_inner_texts())
        check("no horizontal scroll (phone grid)", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        card(pg, "MATH121 limits").tap(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(150)
        check("note view without the tray", not pg.locator("#tray").is_visible() and pg.locator("#desk").bounding_box()["width"] >= 374)
        check("counter and arrows in the header", pg.inner_text("#barCount") == "1 / 3" and pg.locator("#prevBtn").is_visible() and pg.locator("#nextBtn").is_visible())
        pg.tap("#nextBtn"); pg.wait_for_timeout(100); c2 = pg.inner_text("#barCount")
        pg.tap("#nextBtn"); pg.wait_for_timeout(100); c3 = pg.inner_text("#barCount")
        pg.tap("#prevBtn"); pg.wait_for_timeout(100); c4 = pg.inner_text("#barCount")
        check("next and prev move through the pages", [c2, c3, c4] == ["2 / 3", "3 / 3", "2 / 3"], [c2, c3, c4])
        check("no horizontal scroll (phone note)", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        if SHOTS: pg.screenshot(path=str(SHOTS / "phone-note.png"))
        pg.tap("#backBtn"); pg.wait_for_timeout(150)
        check("back returns to the grid", pg.locator("#grid").is_visible())
        pg.tap("#gridBack"); pg.wait_for_timeout(100)
        check("grid back returns to the folder view", pg.locator("#side").is_visible())
        check("no page errors (phone)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ PWA
        group[0] = "pwa"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        man = pg.evaluate("fetch('./manifest.json').then(r=>r.json())")
        check("manifest loads (pw-v7a: display fullscreen, standalone the fallback)", man.get("display") == "fullscreen" and "standalone" in man.get("display_override", [])
              and man.get("name") == "PenWorks" and len(man.get("icons", [])) == 3, man)
        for ic in man["icons"]:
            st = pg.evaluate("(u)=>fetch(u).then(r=>r.status+' '+r.headers.get('content-type'))", ic["src"])
            check("icon " + ic["src"], st.startswith("200 image/png"), st)
        check("service worker registers and is active", pg.evaluate("navigator.serviceWorker.ready.then(r=>!!r.active)"))
        check("cache is pw-v7d (share pages)", pg.evaluate("caches.keys()") == ["pw-v7d"] or "pw-v7d" in pg.evaluate("caches.keys()"), pg.evaluate("caches.keys()"))
        inst = ctx.new_cdp_session(pg).send("Page.getInstallabilityErrors")
        check("Chrome sees it as installable", not inst.get("installabilityErrors"), inst)
        pg.reload(); ready(pg); pg.wait_for_timeout(500)
        ctx.set_offline(True)
        pg.reload(); ready(pg)
        check("opens offline (local copy)", pg.title() == "PenWorks")
        ctx.set_offline(False)
        check("no page errors (pwa)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ live mode
        if LIVE:
            group[0] = "live"
            user, pwd = creds()
            if not user or not pwd:
                check("test login available (PW_TEST_USER / PW_TEST_PASS)", False, "not set")
            else:
                ctx = b.new_context(viewport={"width": 1280, "height": 800})
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE)
                pg.wait_for_selector("#login:not([hidden])")
                pg.fill("#lu", user); pg.fill("#lp", pwd); pg.click("#loginBtn"); ready(pg)
                rows = lambda: pg.evaluate("window.__pw.api.loadAll().then(d => [d.folders.length, d.notes.length, d.pages.length])")
                check("logged in, starts empty", rows() == [0, 0, 0], rows())
                try:
                    pg.click("#addFolder"); type_name(pg, "U1b test")
                    frow(pg, "U1b test").locator(".more").click(); menu(pg, "New note")
                    pg.wait_for_selector("#noteView:not([hidden])"); rename_open_note(pg, "U1b note"); pg.click("#addPageBtn"); pg.click("#menu button:text-is('Page')"); idle(pg)
                    back(pg); pg.reload(); ready(pg)
                    s = side(pg)
                    check("folder > note > 2 pages saved to Supabase", s["folders"].get("U1b test", {}).get("notes") == [["U1b note", 2]], s)
                    refused = pg.evaluate("""async () => {
                      const a = window.__pw.api, top = window.__pw.S.folders.find(f => f.name === 'U1b test'), sub = crypto.randomUUID(), out = [];
                      await a.createFolder({ id: sub, parent_id: top.id, name: 'U1b sub', position: 0 });
                      try { await a.createFolder({ id: crypto.randomUUID(), parent_id: sub, name: 'U1b too deep', position: 0 }); out.push('made'); }
                      catch (e) { out.push(e.message || String(e)); }
                      await a.remove('folders', [sub]);
                      return out; }""")
                    check("the database refuses a third level", "two levels" in str(refused[0]), refused)
                    frow(pg, "U1b test").locator(".more").click(); menu(pg, "Bin"); idle(pg)
                    pg.reload(); ready(pg)
                    s = side(pg)
                    pages_binned = pg.evaluate("window.__pw.api.loadAll().then(d => d.pages.map(p => !!p.deleted_at))")
                    check("binned (after reload), pages with it", s["bin"] == 1 and "U1b test" not in s["folders"] and pages_binned == [True, True], [s, pages_binned])
                    frow(pg, "Bin").click(); pg.click(".binItem button"); idle(pg)
                    pg.reload(); ready(pg)
                    s = side(pg)
                    check("restored with its note and pages (after reload)", s["bin"] == 0 and s["folders"].get("U1b test", {}).get("notes") == [["U1b note", 2]], s)
                    check("no failed writes", pg.evaluate("window.__pw.failed()") == 0)
                finally:
                    left = pg.evaluate("""async () => {
                      const a = window.__pw.api, d = await a.loadAll();
                      if (d.pages.length) await a.remove('pages', d.pages.map(r => r.id));
                      if (d.notes.length) await a.remove('notes', d.notes.map(r => r.id));
                      if (d.folders.length) await a.remove('folders', d.folders.map(r => r.id));
                      const e = await a.loadAll();
                      return [e.folders.length, e.notes.length, e.pages.length]; }""")
                    check("test rows deleted, empty again", left == [0, 0, 0], left)
                check("no page errors (live)", not errs, errs)
                pg.click("#logoutBtn"); pg.wait_for_selector("#login:not([hidden])")
                check("log out returns to the login screen", True)
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
