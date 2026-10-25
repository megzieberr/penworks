# PenWorks page list checks: hold a page thumbnail (350 ms, still) and drag it to its place.
# Run: python tests/test_pagedrag.py              (local mode only: ?local=1, Supabase is never touched)
#      add --shots <folder> for one shot of a lifted thumbnail with the gap open
# Headless Playwright (Python), same style as tests/test_colours.py. The mouse stands in for the finger and
# the S Pen (the drag listens to pointer events); one group uses real touch events (CDP) for the scroll.
import sys, subprocess, time, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8778
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
if SHOTS: SHOTS.mkdir(parents=True, exist_ok=True)

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

PIDS = [f"p{k}" for k in range(1, 9)]
SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-25T10:00:00Z', pg = (id, nid, k) => ({ id, note_id: nid, position: k, orientation: 'portrait', background: 'grid',
    deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'First', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t },
              { id: 'f2', parent_id: null, name: 'Second', colour: null, position: 1, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Drag test', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t },
            { id: 'n2', folder_id: 'f1', name: 'One page', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [...[1, 2, 3, 4, 5, 6, 7, 8].map((k) => pg('p' + k, 'n1', k - 1)), pg('q1', 'n2', 0)] }));
}"""
DOM_JS = "() => [...document.querySelectorAll('#plThumbs .thumbP')].map(t => t.dataset.id)"
NUMS_JS = "() => [...document.querySelectorAll('#plThumbs .thumbP .num')].map(n => n.textContent)"
STORED_JS = """async (nid) => { const d = await window.__pw.api.loadAll();
  return d.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id); }"""
MEM_JS = """(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id)"""
LOOK_JS = """() => { const T = document.getElementById('plThumbs'), l = T.querySelector('.thumbP.lift');
  return { dragging: T.classList.contains('dragging'), lifted: l ? l.dataset.id : null, opacity: l ? +getComputedStyle(l).opacity : null,
    tf: l ? l.style.transform : '', moved: [...T.querySelectorAll('.thumbP:not(.lift)')].filter(t => t.style.transform).map(t => t.dataset.id) }; }"""
COUNTERS_JS = "() => ['plCount', 'counter', 'barCount'].map(id => document.getElementById(id).textContent)"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def menu_items(pg): return [t.strip() for t in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def open_note(pg, name):
    if pg.locator("#noteView").is_visible(): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
    pg.locator(".nrow", has_text=name).first.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(260)      # the list slides in (0.18 s)
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def centre(pg, i):
    b = thumb(pg, i).bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
def U(pg): return pg.evaluate("(window.__pw.S.hist['n1'] || { u: [] }).u.length")
def drag(pg): return pg.evaluate("window.__pw.pageDrag()")
def hold(pg, i, ms=450):
    x, y = centre(pg, i); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(ms); return x, y
def to_slot(pg, j, slots):
    pg.mouse.move(*slots[j - 1], steps=8); pg.wait_for_timeout(40)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)
        pg.evaluate("addEventListener('pointerdown', (e) => { window.__pid = e.pointerId; }, true)")

        # ------------------------------------------------------------ a quick tap still goes to the page
        group[0] = "tap"
        open_note(pg, "Drag test"); open_list(pg)
        u0 = U(pg)
        thumb(pg, 3).click(); pg.wait_for_timeout(80)
        check("tap thumb 3: page 3 is current, the list closes", pg.evaluate(COUNTERS_JS)[1] == "3 / 8" and pg.locator("#pageList").is_hidden(),
              pg.evaluate(COUNTERS_JS))
        check("the tap moved nothing and added no undo step", pg.evaluate(MEM_JS, "n1") == PIDS and U(pg) == u0, [pg.evaluate(MEM_JS, "n1"), U(pg)])

        # ------------------------------------------------------------ hold and drag
        group[0] = "drag"
        open_list(pg)
        slots = [centre(pg, k) for k in range(1, 9)]
        hold(pg, 1)
        d = drag(pg)
        check("held 350 ms still: page 1 lifts", d and d["lifted"] and d["from"] == 0, d)
        to_slot(pg, 4, slots)
        look = pg.evaluate(LOOK_JS)
        check("lifted look: see-through, scaled 1.06, the list marked dragging", look["dragging"] and look["lifted"] == "p1"
              and 0.7 < look["opacity"] < 1 and "scale(1.06)" in look["tf"], look)
        check("the gap: pages 2 to 4 slide back one slot, 5 to 8 stay", sorted(look["moved"]) == ["p2", "p3", "p4"], look["moved"])
        check("the gap follows the pointer: slot 4", drag(pg)["to"] == 3, drag(pg))
        if SHOTS:
            box = pg.locator("#pageList").bounding_box()
            pg.screenshot(path=str(SHOTS / "page-drag-lifted.png"), clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": min(box["height"], 640)})
        pg.mouse.up(); pg.wait_for_timeout(80); idle(pg)
        moved = ["p2", "p3", "p4", "p1", "p5", "p6", "p7", "p8"]
        check("dropped in slot 4: DOM order", pg.evaluate(DOM_JS) == moved, pg.evaluate(DOM_JS))
        check("the numbers under the thumbs renumber 1 to 8", pg.evaluate(NUMS_JS) == [str(k) for k in range(1, 9)], pg.evaluate(NUMS_JS))
        check("stored positions follow", pg.evaluate(STORED_JS, "n1") == moved and pg.evaluate(MEM_JS, "n1") == moved, pg.evaluate(STORED_JS, "n1"))
        check("the dropped page is current: 4 / 8 on every counter", pg.evaluate(COUNTERS_JS)[:2] == ["4 / 8", "4 / 8"]
              and pg.evaluate("window.__pw.current()") == 3 and "cur" in thumb(pg, 4).get_attribute("class").split(), pg.evaluate(COUNTERS_JS))
        check("the list stays open, nothing left lifted", pg.locator("#pageList").is_visible() and not pg.evaluate(LOOK_JS)["dragging"]
              and drag(pg) is None and not pg.evaluate(LOOK_JS)["moved"])
        check("one undo step", U(pg) == u0 + 1, U(pg) - u0)
        pg.click("#undoBtn"); idle(pg)
        check("undo puts page 1 back first (stored too), page 1 current", pg.evaluate(DOM_JS) == PIDS and pg.evaluate(STORED_JS, "n1") == PIDS
              and pg.evaluate(COUNTERS_JS)[0] == "1 / 8", [pg.evaluate(DOM_JS), pg.evaluate(COUNTERS_JS)])
        pg.click("#redoBtn"); idle(pg)
        check("redo moves it to slot 4 again", pg.evaluate(DOM_JS) == moved and pg.evaluate(STORED_JS, "n1") == moved and pg.evaluate(COUNTERS_JS)[0] == "4 / 8")
        pg.click("#undoBtn"); idle(pg)
        u1 = U(pg)

        # the same slot: nothing
        x, y = hold(pg, 2)
        pg.mouse.move(x + 12, y + 10, steps=4); pg.wait_for_timeout(40)
        same_to = drag(pg)["to"]
        pg.mouse.up(); pg.wait_for_timeout(80); idle(pg)
        check("a drag to its own slot changes nothing, no undo step", same_to == 1 and pg.evaluate(DOM_JS) == PIDS and U(pg) == u1
              and pg.evaluate(STORED_JS, "n1") == PIDS, [same_to, U(pg) - u1])
        check("and the list stays open (the drop is not a tap)", pg.locator("#pageList").is_visible())

        # pointercancel mid-drag: back where it was
        hold(pg, 1); to_slot(pg, 6, slots)
        mid = drag(pg)
        pg.evaluate("window.dispatchEvent(new PointerEvent('pointercancel', { pointerId: window.__pid, bubbles: true }))")
        pg.wait_for_timeout(40)
        look = pg.evaluate(LOOK_JS)
        pg.mouse.up(); pg.wait_for_timeout(80); idle(pg)
        check("pointercancel mid-drag: it was lifted over slot 6", mid and mid["lifted"] and mid["to"] == 5, mid)
        check("pointercancel: drops back, nothing moves, no undo step", look["lifted"] is None and not look["moved"] and not look["dragging"]
              and pg.evaluate(DOM_JS) == PIDS and pg.evaluate(STORED_JS, "n1") == PIDS and U(pg) == u1, [look, U(pg) - u1])

        # a move before the hold time lifts nothing
        x, y = centre(pg, 3); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(60)
        pg.mouse.move(x, y + 40, steps=3); pg.wait_for_timeout(450)
        early = [drag(pg), pg.evaluate(LOOK_JS)]
        pg.mouse.move(*slots[6], steps=4); pg.mouse.up(); pg.wait_for_timeout(80); idle(pg)
        check("moved before 350 ms: nothing lifts", early[0] is None and early[1]["lifted"] is None and not early[1]["dragging"], early)
        check("and nothing reorders", pg.evaluate(MEM_JS, "n1") == PIDS and U(pg) == u1)

        # auto-scroll near the bottom edge
        open_list(pg)
        T = pg.locator("#plThumbs").bounding_box()
        st0 = pg.evaluate("document.getElementById('plThumbs').scrollTop")
        hold(pg, 1)
        pg.mouse.move(T["x"] + T["width"] / 2, T["y"] + T["height"] - 12, steps=8); pg.wait_for_timeout(500)
        st1 = pg.evaluate("document.getElementById('plThumbs').scrollTop")
        mx = pg.evaluate("(() => { const T = document.getElementById('plThumbs'); return T.scrollHeight - T.clientHeight; })()")
        pg.mouse.move(T["x"] + T["width"] / 2, T["y"] + 12, steps=8); pg.wait_for_timeout(900)
        st2 = pg.evaluate("document.getElementById('plThumbs').scrollTop")
        pg.evaluate("window.dispatchEvent(new PointerEvent('pointercancel', { pointerId: window.__pid, bubbles: true }))")
        pg.mouse.up(); pg.wait_for_timeout(60)
        check("lifted near the bottom edge: the list scrolls down", mx > 0 and st1 > st0, [st0, st1, mx])
        check("near the top edge: it scrolls back up", st2 < st1, [st1, st2])
        check("auto-scroll never goes past the end of the list", st1 <= mx + 1, [st1, mx])

        # ------------------------------------------------------------ menus
        group[0] = "menus"
        open_list(pg)
        thumb(pg, 2).click(button="right"); items = menu_items(pg); pg.keyboard.press("Escape")
        check("page menu: no Move up, no Move down", items == ["Add page", "Copy", "Cut", "Delete", "Erase page"], items)
        thumb(pg, 2).locator(".more").click(); items2 = menu_items(pg); pg.keyboard.press("Escape")
        check("the dots under a thumb open the same menu", items2 == items, items2)
        check("the dots do not go to the page", pg.locator("#pageList").is_visible() and pg.evaluate(COUNTERS_JS)[0] == "1 / 8")
        open_list(pg)
        x, y = hold(pg, 2, 750)
        lifted_long = drag(pg)
        menu_open = pg.locator("#menu").is_visible()
        pg.mouse.up(); pg.wait_for_timeout(60)
        check("a long press lifts the page and opens no menu", lifted_long and lifted_long["lifted"] and not menu_open, [lifted_long, menu_open])
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
        pg.locator(".frow", has_text="First").first.locator(".more").click(); f1 = menu_items(pg); pg.keyboard.press("Escape")
        pg.locator(".frow", has_text="Second").first.locator(".more").click(); f2 = menu_items(pg); pg.keyboard.press("Escape")
        check("folders keep Move down / Move up", "Move down" in f1 and "Move up" in f2, [f1, f2])

        # ------------------------------------------------------------ a one-page note
        group[0] = "one page"
        open_note(pg, "One page"); open_list(pg)
        hold(pg, 1, 600)
        one = [drag(pg), pg.evaluate(LOOK_JS)]
        pg.mouse.up(); pg.wait_for_timeout(60)
        check("a one-page note: nothing lifts", one[0] is None and one[1]["lifted"] is None and not one[1]["dragging"], one)
        open_list(pg); thumb(pg, 1).click(button="right"); items = menu_items(pg); pg.keyboard.press("Escape")
        check("its menu still opens (right-click)", "Add page" in items and "Delete" not in items, items)
        check("no page errors (mouse)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ touch: a swipe scrolls, a hold lifts
        group[0] = "touch"
        ctx = b.new_context(viewport={"width": 1100, "height": 700}, has_touch=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)
        open_note(pg, "Drag test"); open_list(pg)
        cdp = ctx.new_cdp_session(pg)
        def touch(kind, x, y):
            cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}]})
        ST = "document.getElementById('plThumbs').scrollTop"
        x, y = centre(pg, 5)
        touch("touchStart", x, y)
        for k in range(1, 9): touch("touchMove", x, y - 25 * k); pg.wait_for_timeout(16)
        swipe = [drag(pg), pg.evaluate(LOOK_JS)["lifted"]]
        touch("touchEnd", 0, 0); pg.wait_for_timeout(300)
        st_swipe = pg.evaluate(ST)
        check("a quick swipe scrolls the list", st_swipe > 50, st_swipe)
        check("and lifts nothing", swipe == [None, None] and pg.evaluate(MEM_JS, "n1") == PIDS, swipe)
        pg.evaluate(f"{ST} = 0"); pg.wait_for_timeout(60)
        slots = [centre(pg, k) for k in range(1, 9)]
        x, y = slots[0]
        touch("touchStart", x, y); pg.wait_for_timeout(450)
        held = drag(pg)
        tx, ty = slots[3]
        for k in range(1, 9): touch("touchMove", x + (tx - x) * k / 8, y + (ty - y) * k / 8); pg.wait_for_timeout(16)
        st_drag = pg.evaluate(ST); to = drag(pg)
        touch("touchEnd", 0, 0); pg.wait_for_timeout(120); idle(pg)
        check("held still with a finger: the page lifts", held and held["lifted"], held)
        check("dragging a lifted page does not scroll the list", st_drag == 0, st_drag)
        check("finger drop in slot 4 reorders", to and to["to"] == 3 and pg.evaluate(MEM_JS, "n1") == ["p2", "p3", "p4", "p1", "p5", "p6", "p7", "p8"],
              [to, pg.evaluate(MEM_JS, "n1")])
        check("no page errors (touch)", not errs, errs)
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
