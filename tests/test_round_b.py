# PenWorks round B checks (pw-v6c): undo under the highlighter, the page list opens at her page, a written-on page
# keeps its shape. Headless Playwright (Python), same harness as tests/test_pagelist.py.
# Run: python tests/test_round_b.py               (local mode only: ?local=1, Supabase is never touched)
# A note 'Twelve' (12 pages, pages 1-4 and 9-12 bookmarked, page 7 not) for the list; a note 'Shape' (4 pages, one
# stroke on pages 1 and 3, pages 2 and 4 blank) for the orientation lock. Strokes are seeded into the local store
# (pw.strokes.<page_id>, the pre-U3 keys js/store.js takes over). The desk moves by the mouse wheel (nextBtn is the
# phone's), the way her own scrolling moves S.cur.
import sys, subprocess, time, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8793
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-27T10:00:00Z', pg = (id, nid, k, bm) => ({ id, note_id: nid, position: k, orientation: 'portrait', background: 'grid',
    bookmark: !!bm, deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Round B', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Twelve', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-27T10:02:00Z' },
            { id: 'n2', folder_id: 'f1', name: 'Shape', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-27T10:01:00Z' }],
    pages: [...Array.from({ length: 12 }, (_, k) => pg('t' + (k + 1), 'n1', k, k < 4 || k >= 8)),
            ...[1, 2, 3, 4].map((k) => pg('s' + k, 'n2', k - 1))] }));
  for (const k of [1, 3]) localStorage.setItem('pw.strokes.s' + k, JSON.stringify([{ id: 's' + k + '-s', page_id: 's' + k, seq: 7000 + k, kind: 'pen',
    style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100, 200], [300, 260], [420, 240]] } }]));
}"""
ORDER_JS = """[...document.getElementById('tray').querySelectorAll(':scope > *, :scope > .tools > *')]
  .map(e => e.dataset.tool || e.dataset.slot || e.id || e.className)"""
# thumb i against #plThumbs' own visible box: fully inside, its centre's offset from the box's middle (px), its classes,
# the list's scrollTop, and whether the list is scrolled as far down as it goes
VIS_JS = """(i) => { const T = document.getElementById('plThumbs'), t = T.querySelector(`.thumbP[data-index="${i}"]`);
  if (!t) return null; const a = T.getBoundingClientRect(), b = t.getBoundingClientRect();
  return { inside: b.top >= a.top - 0.5 && b.bottom <= a.bottom + 0.5, off: Math.round((b.top + b.height / 2) - (a.top + a.height / 2)),
    cls: t.className, top: T.scrollTop, end: T.scrollTop >= T.scrollHeight - T.clientHeight - 1 }; }"""
CUR_JS = "() => [...document.querySelectorAll('#plThumbs .thumbP.cur')].map(t => t.dataset.index)"
SCROLLS_JS = "() => [document.getElementById('desk').scrollTop, document.getElementById('desk').scrollLeft, window.scrollY, document.scrollingElement.scrollTop]"
ORIENT_JS = "(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.orientation)"
PAPER_JS = "(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.background)"
MENU_DIS_JS = """() => Object.fromEntries([...document.querySelectorAll('#menu button')].filter(b => ['Portrait', 'Landscape', 'Blank', 'Grid, 1 cm squares', 'Lined']
  .includes(b.textContent)).map(b => [b.textContent, b.disabled]))"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def open_note(pg, name):
    if pg.locator("#noteView").is_visible(): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
    pg.locator(".nrow", has_text=name).first.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(120)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(260)      # the list slides in (0.18 s)
def close_list(pg):
    if pg.locator("#pageList").is_visible(): pg.click("#plClose")
    pg.wait_for_selector("#pageList", state="hidden")
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
# wheel over the desk's right part (clear of the list panel) until S.cur is the wanted index
def wheel_to(pg, idx, step=240):
    d = pg.locator("#desk").bounding_box(); pg.mouse.move(d["x"] + d["width"] - 120, d["y"] + d["height"] / 2)
    for _ in range(200):
        c = pg.evaluate("window.__pw.S.cur")
        if c == idx: break
        pg.mouse.wheel(0, step if c < idx else -step); pg.wait_for_timeout(50)
    pg.wait_for_timeout(250)
    return pg.evaluate("window.__pw.S.cur")
def menu_click(pg, label): pg.get_by_role("menuitem", name=label, exact=True).click(); pg.wait_for_timeout(80)
def toast(pg): return pg.evaluate("document.getElementById('toast').textContent")
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, pts, steps=6):
    sx, sy = screen(pg, i, *pts[0])
    pg.mouse.move(sx, sy); pg.mouse.down()
    for x, y in pts[1:]:
        tx, ty = screen(pg, i, x, y); pg.mouse.move(tx, ty, steps=steps)
    pg.mouse.up(); pg.wait_for_timeout(40)

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

        # ------------------------------------------------------------ (a) the tray: undo under the highlighter, redo last
        group[0] = "tray"
        open_note(pg, "Twelve")
        order = pg.evaluate(ORDER_JS)
        check("order (pw-v7e): calculator at the top, colours, pen, highlighter, UNDO, stroke eraser, area eraser, restyle, select, gap, redo",
              order == ["tools", "colours", "tools", "pen", "highlighter", "undoBtn", "eraser", "area", "restyle", "select", "gap", "redoBtn"], order)
        check("undo is inside .tools, redo is a child of #tray (after the gap)",
              pg.evaluate("document.getElementById('undoBtn').parentNode.classList.contains('tools') && document.getElementById('redoBtn').parentNode.id === 'tray'"))
        geo = pg.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
          const h = r('#tool-highlighter'), u = r('#undoBtn'), e = r('#tool-eraser'), rd = r('#redoBtn'), s = r('#toolsBtn');
          return { hu: Math.round(u.top - h.bottom), ue: Math.round(e.top - u.bottom), uw: u.width, uh: u.height, rw: rd.width, rh: rd.height,
                   redoLast: rd.top > e.bottom && s.bottom <= r('#tray .colours').top + 0.5, /* pw-v7e: the calculator moved to the top */ centred: Math.abs((u.left + u.width / 2) - (h.left + h.width / 2)) < 0.6 }; }""")
        check("undo sits straight under the highlighter (the tools' 2 px gap above and below)", geo["hu"] == 2 and geo["ue"] == 2, geo)
        check("undo keeps its size (40 x 40, the same as redo) and is centred in the column",
              geo["uw"] == 40 and geo["uh"] == 40 and geo["rw"] == 40 and geo["rh"] == 40 and geo["centred"], geo)
        check("redo is still at the bottom; the calculator button sits above the colours (pw-v7e)", geo["redoLast"], geo)
        icon = pg.evaluate("[document.getElementById('undoBtn').getAttribute('aria-label'), document.querySelectorAll('#undoBtn svg path').length]")
        check("undo keeps its label and icon", icon == ["Undo", 2], icon)
        for w, h_ in [(1600, 2560), (2560, 1600), (1280, 800), (1280, 760), (1280, 720)]:
            pg.set_viewport_size({"width": w, "height": h_}); pg.wait_for_timeout(120)
            fit = pg.evaluate("""() => { const t = document.getElementById('tray'), r = document.getElementById('redoBtn').getBoundingClientRect();
              return [t.scrollHeight, t.clientHeight, Math.round(r.bottom), innerHeight]; }""")
            check(f"{w} x {h_}: the tray fits without scrolling, redo on screen", fit[0] <= fit[1] and fit[2] <= fit[3], fit)
        pg.set_viewport_size({"width": 1280, "height": 740}); pg.wait_for_timeout(120)
        small = pg.evaluate("[...['#undoBtn', '#redoBtn', '#tool-pen']].map(s => document.querySelector(s).getBoundingClientRect().width)")
        check("at 740 px tall undo shrinks with the rest (38 px, the same as redo and the tools)", small == [38, 38, 38], small)
        pg.set_viewport_size({"width": 1280, "height": 800}); pg.wait_for_timeout(120)
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        dk = pg.evaluate("[getComputedStyle(document.getElementById('undoBtn')).color, getComputedStyle(document.getElementById('redoBtn')).color]")
        pg.evaluate("document.documentElement.removeAttribute('data-theme')")
        check("dark mode: undo and redo the same colour", dk[0] == dk[1], dk)

        # ------------------------------------------------------------ (b) undo from its new spot
        group[0] = "undo"
        check("undo starts disabled", pg.locator("#undoBtn").is_disabled())
        draw(pg, 1, [(120 + 20 * k, 300 + (10 if k % 2 else -10)) for k in range(10)]); idle(pg)
        n1 = len(pg.evaluate("window.__pw.ink.strokesOf('t1')"))
        check("a stroke on page 1 lights undo", n1 == 1 and pg.locator("#undoBtn").is_enabled(), n1)
        pg.click("#undoBtn"); idle(pg)
        check("undo (under the highlighter) takes it away and goes dark again; redo lights",
              len(pg.evaluate("window.__pw.ink.strokesOf('t1')")) == 0 and pg.locator("#undoBtn").is_disabled() and pg.locator("#redoBtn").is_enabled())
        pg.click("#redoBtn"); idle(pg)
        check("redo (at the bottom) puts it back", len(pg.evaluate("window.__pw.ink.strokesOf('t1')")) == 1 and pg.locator("#undoBtn").is_enabled())
        pg.click("#undoBtn"); idle(pg)
        check("and undo again leaves page 1 blank", len(pg.evaluate("window.__pw.ink.strokesOf('t1')")) == 0)

        # ------------------------------------------------------------ (c) the list opens at her page
        group[0] = "list opens at her page"
        open_list(pg)
        v1 = pg.evaluate(VIS_JS, 1)
        check("on page 1: thumb 1 shown and marked, the list at the top", v1["inside"] and v1["top"] == 0 and pg.evaluate(CUR_JS) == ["1"], v1)
        close_list(pg)
        wheel_to(pg, 6)
        check("the desk scrolled (wheel) to page 7 of 12", pg.evaluate("window.__pw.S.cur") == 6
              and pg.evaluate("document.getElementById('counter').textContent") == "7 / 12", pg.evaluate("window.__pw.S.cur"))
        s0 = pg.evaluate(SCROLLS_JS)
        open_list(pg)
        v7 = pg.evaluate(VIS_JS, 7)
        check("opening the list on page 7: thumb 7 inside #plThumbs' visible box", v7 and v7["inside"], v7)
        check("... centred (within 12 px of the box's middle), not left at the top", v7 and abs(v7["off"]) <= 12 and v7["top"] > 0, v7)
        check("... and marked .cur (only it)", pg.evaluate(CUR_JS) == ["7"], pg.evaluate(CUR_JS))
        check("thumb 1 is scrolled out of sight", not pg.evaluate(VIS_JS, 1)["inside"])
        check("the desk and the window did not scroll", pg.evaluate(SCROLLS_JS) == s0 == [0, 0, 0, 0], [s0, pg.evaluate(SCROLLS_JS)])
        look = pg.evaluate("""() => { const s = getComputedStyle(document.querySelector('#plThumbs .thumbP.cur .paper'));
          return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.backgroundColor]; }""")
        check("the mark: a thin graphite outline (1.5 px, one device pixel at this DPR), no colour fill",
              look[0] == "solid" and 0 < float(look[1][:-2]) <= 1.5 and look[2:] == ["rgb(38, 42, 48)", "rgb(255, 255, 255)"], look)
        wheel_to(pg, 7)
        check("the desk scrolls on with the list open (wheel): the mark moves to 8", pg.evaluate(CUR_JS) == ["8"] and pg.locator("#pageList").is_visible(),
              pg.evaluate(CUR_JS))
        wheel_to(pg, 6)
        check("... and back: the mark is on 7 again", pg.evaluate(CUR_JS) == ["7"], pg.evaluate(CUR_JS))
        thumb(pg, 10).click(); pg.wait_for_timeout(400)
        check("a thumb tap (10) still jumps the desk and moves the mark, the panel stays open",
              pg.evaluate("window.__pw.S.cur") == 9 and pg.evaluate(CUR_JS) == ["10"] and pg.locator("#pageList").is_visible(), pg.evaluate(CUR_JS))
        close_list(pg); open_list(pg)
        v10 = pg.evaluate(VIS_JS, 10)
        check("reopening on page 10 centres thumb 10", v10["inside"] and abs(v10["off"]) <= 12, v10)
        # tick mode still works from a list opened mid-note
        pg.click("#plSelect"); pg.wait_for_timeout(80)
        thumb(pg, 10).click(); thumb(pg, 9).click(); pg.wait_for_timeout(80)
        tk = pg.evaluate("window.__pw.tick()")
        check("tick mode: two taps tick pages 10 and 9, the desk stays", tk and tk["ids"] == ["t9", "t10"] and pg.evaluate("window.__pw.S.cur") == 9, tk)
        pg.click("#plDone"); pg.wait_for_timeout(80)
        check("Done ends tick mode", pg.evaluate("window.__pw.tick()") is None)
        close_list(pg)

        # ------------------------------------------------------------ (d) the Bookmarks filter
        group[0] = "bookmarks filter"
        open_list(pg); thumb(pg, 7).click(); pg.wait_for_timeout(300); close_list(pg)
        check("back on page 7 (not bookmarked)", pg.evaluate("window.__pw.S.cur") == 6)
        open_list(pg); pg.click("#plMarks"); pg.wait_for_timeout(120)
        shown = pg.evaluate("[...document.querySelectorAll('#plThumbs .thumbP')].map(t => t.dataset.index)")
        check("the filter shows the 8 bookmarked pages", shown == ["1", "2", "3", "4", "9", "10", "11", "12"], shown)
        close_list(pg); open_list(pg)
        top = pg.evaluate("document.getElementById('plThumbs').scrollTop")
        check("filter on, page 7 not shown: the list opens at the top", top == 0 and pg.evaluate(VIS_JS, 1)["inside"], top)
        check("... nothing marked .cur", pg.evaluate(CUR_JS) == [], pg.evaluate(CUR_JS))
        thumb(pg, 11).click(); pg.wait_for_timeout(300); close_list(pg)
        open_list(pg)
        v11 = pg.evaluate(VIS_JS, 11)
        check("filter on, on page 11 (bookmarked, the last row): thumb 11 in view, as near the middle as the list scrolls, and marked",
              v11["inside"] and v11["top"] > 0 and (abs(v11["off"]) <= 12 or v11["end"]) and pg.evaluate(CUR_JS) == ["11"], v11)
        pg.click("#plMarks"); pg.wait_for_timeout(120)
        check("the filter off again: all 12 thumbs", pg.locator("#plThumbs .thumbP").count() == 12)
        close_list(pg)

        # ------------------------------------------------------------ (e) and (f) a written-on page keeps its shape
        group[0] = "shape"
        open_note(pg, "Shape")
        pg.click("#noteMore"); pg.wait_for_timeout(80)
        d1 = pg.evaluate(MENU_DIS_JS)
        check("page 1 has one stroke: Portrait and Landscape disabled", d1.get("Portrait") is True and d1.get("Landscape") is True, d1)
        check("... the paper (Blank, Grid, Lined) still enabled", [d1.get(k) for k in ["Blank", "Grid, 1 cm squares", "Lined"]] == [False] * 3, d1)
        pg.get_by_role("menuitem", name="Landscape", exact=True).click(force=True); pg.wait_for_timeout(80)
        check("a tap on the greyed Landscape does nothing (no Change menu, page still portrait)",
              pg.locator("#menu button", has_text="All pages").count() == 0 and pg.evaluate(ORIENT_JS, "n2")[0] == "portrait")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(60)
        if pg.locator("#menu").is_visible(): pg.mouse.click(5, 5); pg.wait_for_timeout(60)
        open_list(pg); thumb(pg, 2).click(); pg.wait_for_timeout(300); close_list(pg)
        check("on page 2 (blank)", pg.evaluate("window.__pw.S.cur") == 1)
        pg.click("#noteMore"); pg.wait_for_timeout(80)
        d2 = pg.evaluate(MENU_DIS_JS)
        check("page 2 is blank: Portrait and Landscape enabled", d2.get("Portrait") is False and d2.get("Landscape") is False, d2)
        u0 = pg.evaluate("window.__pw.S.hist['n2'] ? window.__pw.S.hist['n2'].u.length : 0")
        menu_click(pg, "Landscape"); menu_click(pg, "All pages"); idle(pg)
        o = pg.evaluate(ORIENT_JS, "n2")
        check("All pages landscape from a blank page: only the blank pages (2 and 4) turn", o == ["portrait", "landscape", "portrait", "landscape"], o)
        check("toast: '2 pages with writing kept their shape'", toast(pg) == "2 pages with writing kept their shape", toast(pg))
        check("one undo step", pg.evaluate("window.__pw.S.hist['n2'].u.length") == u0 + 1)
        sheets = pg.evaluate("[...document.querySelectorAll('#stack .sheet')].map(s => s.getBoundingClientRect().width > s.getBoundingClientRect().height)")
        check("the desk shows it: sheets 2 and 4 wide, 1 and 3 tall", sheets == [False, True, False, True], sheets)
        pg.click("#undoBtn"); idle(pg)
        check("undo puts pages 2 and 4 back to portrait", pg.evaluate(ORIENT_JS, "n2") == ["portrait"] * 4, pg.evaluate(ORIENT_JS, "n2"))
        pg.click("#redoBtn"); idle(pg)
        check("redo turns only 2 and 4 again", pg.evaluate(ORIENT_JS, "n2") == ["portrait", "landscape", "portrait", "landscape"], pg.evaluate(ORIENT_JS, "n2"))
        pg.click("#noteMore"); pg.wait_for_timeout(80)
        menu_click(pg, "Portrait"); menu_click(pg, "Just this page"); idle(pg)
        check("Just this page on the blank page still turns it (back to portrait)", pg.evaluate(ORIENT_JS, "n2")[1] == "portrait", pg.evaluate(ORIENT_JS, "n2"))
        pg.click("#noteMore"); pg.wait_for_timeout(80)
        menu_click(pg, "Lined"); menu_click(pg, "All pages"); idle(pg)
        check("paper stays changeable on every page: All pages Lined reaches the written pages too", pg.evaluate(PAPER_JS, "n2") == ["lined"] * 4,
              pg.evaluate(PAPER_JS, "n2"))
        # one written page left to skip: the toast says it in the singular
        pg.evaluate("""() => window.__pw.ink.put('s4', [{ id: 's4-x', page_id: 's4', seq: 9100, kind: 'pen',
            style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100, 100], [300, 160]] } }])"""); idle(pg)
        pg.evaluate("document.getElementById('toast').textContent = ''")
        pg.click("#noteMore"); pg.wait_for_timeout(80)
        menu_click(pg, "Portrait"); menu_click(pg, "All pages"); idle(pg)
        o2 = pg.evaluate(ORIENT_JS, "n2")
        check("All pages portrait with page 4 now written (landscape): page 4 keeps its shape, one page said so",
              o2 == ["portrait", "portrait", "portrait", "landscape"] and toast(pg) == "1 page with writing kept its shape", [o2, toast(pg)])
        check("no page errors", not errs, errs)

        # ------------------------------------------------------------ the cache
        group[0] = "cache"
        pg.evaluate("navigator.serviceWorker.ready"); pg.wait_for_timeout(300)
        keys = pg.evaluate("caches.keys()")
        if "pw-v7i" not in keys:
            pg.reload(); ready(pg); pg.wait_for_timeout(600); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7i", "pw-v7i" in keys, keys)
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
