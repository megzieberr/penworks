# PenWorks page list checks (pw-v4i): the thumbnails draw the page's ink, and a thumb tap keeps the panel open.
# pw-v4q: tick mode (Select in the header): tick several pages, then Delete, Copy, Cut or Move them together.
# Run: python tests/test_pagelist.py              (local mode only: ?local=1, Supabase is never touched)
# Headless Playwright (Python), same harness as tests/test_pagedrag.py. Strokes are seeded straight into the
# local store (pw.strokes.<page_id>, the pre-U3 keys js/store.js takes over); the mouse draws the rest on the desk.
# A thumb's ink is one <svg class="thumbInk"> inside its .paper, always there (an empty page: an svg with no paths).
# A pen landing on the desk closes the panel (her "until I click on the page again"), so the live refresh is checked
# through the stroke funnel with the panel open: ink.put (the same apply every stroke lands through) and the tray's
# undo and redo buttons, which are not on the desk.
# Tick mode (pw-v4q): Select in the list header ticks several pages (a tap toggles, the desk stays put), then Delete,
# Copy, Cut or Move them together, each one undo step; the page clipboard is a list (Paste puts every page). A note
# 'Ticks' with 6 pages, one stroke each whose first point's x (110, 120, ... 160) names the page. The "tick mode (pw-v4q)" group.
# pw-v4r: page bookmarks. The page menu (the note header's dots) toggles a page's `bookmark` (not an undo step), a ribbon
# tab shows on the page and its thumb, and the list header's Bookmarks toggle shows only the bookmarked pages. A note
# 'Marks' with 4 pages, one stroke each (x 110 to 140 names the page). The "bookmarks (pw-v4r)" group.
# pw-v4t: tick mode's Share (a name box first, then one PDF or PNG images). Headless Chromium has no share sheet: an init
# script stubs navigator.canShare / navigator.share (the files land in window.__shared); a second context has no
# navigator.share and watches the downloads. PDFs are read with PyMuPDF, PNGs by their header and pixels (numpy), never
# looked at. A note 'Test note' with 4 pages (a stroke each) and 'Twelve' (12 pages) for the timing. The "share (pw-v4t)" group.
import sys, subprocess, time, pathlib, math, base64, struct
import fitz, numpy as np
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8780
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1&hold=100"     # a quick snap for the shape group

res = []
group = ["?"]
info_lines = []
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-25T10:00:00Z', pg = (id, nid, k) => ({ id, note_id: nid, position: k, orientation: 'portrait', background: 'grid',
    deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Lists', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Thumbs', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-25T10:02:00Z' },
            { id: 'n2', folder_id: 'f1', name: 'Timing', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-25T10:01:00Z' },
            { id: 'n3', folder_id: 'f1', name: 'Ticks', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-25T10:00:30Z' },
            { id: 'n4', folder_id: 'f1', name: 'Marks', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-25T10:00:10Z' }],
    pages: [...[1, 2, 3, 4].map((k) => pg('a' + k, 'n1', k - 1)), ...[1, 2, 3, 4, 5, 6, 7, 8].map((k) => pg('b' + k, 'n2', k - 1)),
            ...[1, 2, 3, 4, 5, 6].map((k) => pg('c' + k, 'n3', k - 1)), ...[1, 2, 3, 4].map((k) => pg('m' + k, 'n4', k - 1))] }));
  let seq = 0;
  const stroke = (pid, k, n) => ({ id: pid + '-s' + k, page_id: pid, seq: ++seq, kind: 'pen',
    style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 },
    data: { points: Array.from({ length: n }, (_, j) => [Math.round((80 + j * 12 + (k % 40) * 4) * 10) / 10,
                                                         Math.round((100 + (k % 50) * 19 + 8 * Math.sin(j)) * 10) / 10]) } });
  const put = (pid, count, n) => localStorage.setItem('pw.strokes.' + pid, JSON.stringify(Array.from({ length: count }, (_, k) => stroke(pid, k, n))));
  put('a1', 2, 20); put('a3', 3, 20);
  for (let k = 1; k <= 8; k++) put('b' + k, 300, 20);
  for (let k = 1; k <= 6; k++) localStorage.setItem('pw.strokes.c' + k, JSON.stringify([{ id: 'c' + k + '-s', page_id: 'c' + k, seq: 5000 + k, kind: 'pen',
    style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100 + 10 * k, 200], [300, 260], [420, 240]] } }]));
  for (let k = 1; k <= 4; k++) localStorage.setItem('pw.strokes.m' + k, JSON.stringify([{ id: 'm' + k + '-s', page_id: 'm' + k, seq: 6000 + k, kind: 'pen',
    style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100 + 10 * k, 200], [300, 260], [420, 240]] } }]));
}"""
THUMB_JS = """(i) => { const t = document.querySelector(`#plThumbs .thumbP[data-index="${i}"]`);
  const svgs = t ? [...t.querySelectorAll('.paper > svg')] : [], s = svgs[0];
  return { svgs: svgs.length, viewBox: s ? s.getAttribute('viewBox') : null, paths: s ? s.querySelectorAll('path').length : -1,
    lines: s ? s.querySelectorAll('line').length : -1, polygons: s ? s.querySelectorAll('polygon').length : -1,
    par: s ? s.getAttribute('preserveAspectRatio') : null, pe: s ? s.getAttribute('pointer-events') : null,
    pos: s ? getComputedStyle(s).position : null, id: t ? t.dataset.id : null }; }"""
# wait (rAF polling, up to `ms`) until thumb i's path count is n; returns the ms it took, or -1
WAIT_JS = """async ([i, n, ms]) => { const t0 = performance.now();
  const count = () => { const s = document.querySelector(`#plThumbs .thumbP[data-index="${i}"] .paper > svg`); return s ? s.querySelectorAll('path').length : -1; };
  while (performance.now() - t0 <= ms) { if (count() === n) return Math.round(performance.now() - t0); await new Promise((r) => requestAnimationFrame(r)); }
  return -1; }"""
COUNTERS_JS = "() => ['plCount', 'counter', 'barCount'].map(id => document.getElementById(id).textContent)"
CUR_JS = "() => [...document.querySelectorAll('#plThumbs .thumbP.cur')].map(t => t.dataset.index)"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def open_note(pg, name):
    if pg.locator("#noteView").is_visible(): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
    pg.locator(".nrow", has_text=name).first.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(260)      # the list slides in (0.18 s)
def close_list(pg):
    if pg.locator("#pageList").is_visible(): pg.click("#plClose")
    pg.wait_for_selector("#pageList", state="hidden")
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def centre(pg, i):
    b = thumb(pg, i).bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
def tinfo(pg, i): return pg.evaluate(THUMB_JS, i)
def nstrokes(pg, pid): return len(pg.evaluate("(id) => window.__pw.ink.strokesOf(id)", pid))
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, pts, steps=6, hold=0):
    sx, sy = screen(pg, i, *pts[0])
    pg.mouse.move(sx, sy); pg.mouse.down()
    for x, y in pts[1:]:
        tx, ty = screen(pg, i, x, y); pg.mouse.move(tx, ty, steps=steps)
    if hold: pg.wait_for_timeout(hold)
    pg.mouse.up(); pg.wait_for_timeout(40)
def go_page(pg, i):
    open_list(pg); thumb(pg, i).click(); pg.wait_for_timeout(120); close_list(pg)
def menu_items(pg): return [t_.strip() for t_ in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def menu_click(pg, label): pg.get_by_role("menuitem", name=label, exact=True).click(); pg.wait_for_timeout(80)
def wobble(k, amp=2.0): return amp * math.sin(k * 1.7) * math.cos(k * 0.6)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 1300})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)

        # ------------------------------------------------------------ 1. the thumbs draw the ink
        group[0] = "thumbs"
        open_note(pg, "Thumbs"); open_list(pg)
        t = [tinfo(pg, i) for i in range(1, 5)]
        n1, n3 = nstrokes(pg, "a1"), nstrokes(pg, "a3")
        check("the seeded pages hold 2 and 3 strokes", n1 == 2 and n3 == 3, [n1, n3])
        check("every thumb holds exactly one ink svg (an empty page too)", [x["svgs"] for x in t] == [1, 1, 1, 1], [x["svgs"] for x in t])
        check("the svg's viewBox is the page size in page px (A4 portrait 794 x 1123)", all(x["viewBox"] == "0 0 794 1123" for x in t), [x["viewBox"] for x in t])
        check("it stretches over the paper: preserveAspectRatio none, no pointer events, absolutely placed",
              all(x["par"] == "none" and x["pe"] == "none" and x["pos"] == "absolute" for x in t), t[0])
        check("thumb 1: one path per stroke (2)", t[0]["paths"] == n1, t[0])
        check("thumb 3: one path per stroke (3)", t[2]["paths"] == n3, t[2])
        check("thumbs 2 and 4: an svg with no paths", t[1]["paths"] == 0 and t[3]["paths"] == 0, [t[1], t[3]])
        same = pg.evaluate("""() => { const a = document.querySelector('#plThumbs .thumbP[data-index="1"] .paper > svg path'),
            b = document.querySelector('#stack .sheet[data-index="1"] svg.ink path');
            return a && b ? ['d', 'stroke', 'stroke-width'].every(k => a.getAttribute(k) === b.getAttribute(k)) : false; }""")
        check("a thumb's path is the page's path (same d, colour, width)", same)
        paper = pg.evaluate("""() => { const p = document.querySelector('#plThumbs .thumbP .paper'), s = getComputedStyle(p);
            return [s.position, s.overflow, s.backgroundColor]; }""")
        check("the thumb's paper: relative, overflow hidden, white", paper == ["relative", "hidden", "rgb(255, 255, 255)"], paper)
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        dark = pg.evaluate("getComputedStyle(document.querySelector('#plThumbs .thumbP .paper')).backgroundColor")
        pg.evaluate("document.documentElement.removeAttribute('data-theme')")
        check("dark mode: the thumb's paper stays white", dark == "rgb(255, 255, 255)", dark)

        # ------------------------------------------------------------ 2. the open list refreshes a page's thumb
        group[0] = "refresh"
        rec = """() => window.__pw.ink.put('a2', [{ id: 'a2-put', page_id: 'a2', seq: 999, kind: 'pen',
            style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100, 100], [300, 160], [420, 120]] } }])"""
        pg.evaluate(rec)
        ms = pg.evaluate(WAIT_JS, [2, 1, 300])
        check("a stroke lands on page 2 (the apply funnel) with the list open: thumb 2 shows 1 path within 300 ms", ms >= 0, ms)
        pg.evaluate("() => window.__pw.ink.erasePageOp('a2').redo()"); idle(pg)
        check("and it goes again when the page is erased (0 paths)", pg.evaluate(WAIT_JS, [2, 0, 300]) >= 0, tinfo(pg, 2))
        close_list(pg)
        go_page(pg, 2)
        u0 = pg.evaluate("window.__pw.S.hist['n1'].u.length")
        draw(pg, 2, [(120 + 20 * k, 400 + (14 if k % 2 else -14)) for k in range(14)], steps=3); idle(pg)
        check("the mouse drew one stroke on page 2 (one undo step)", nstrokes(pg, "a2") == 1 and pg.evaluate("window.__pw.S.hist['n1'].u.length") == u0 + 1,
              nstrokes(pg, "a2"))
        open_list(pg)
        check("the list opens on it: thumb 2 has 1 path", tinfo(pg, 2)["paths"] == 1, tinfo(pg, 2))
        pg.click("#undoBtn"); ms_u = pg.evaluate(WAIT_JS, [2, 0, 300])
        check("undo with the list open: thumb 2 has 0 paths within 300 ms", ms_u >= 0 and pg.locator("#pageList").is_visible(), [ms_u, tinfo(pg, 2)])
        pg.click("#redoBtn"); ms_r = pg.evaluate(WAIT_JS, [2, 1, 300])
        check("redo: 1 path again within 300 ms", ms_r >= 0, [ms_r, tinfo(pg, 2)])
        check("the other thumbs keep their ink", [tinfo(pg, i)["paths"] for i in (1, 3, 4)] == [2, 3, 0], [tinfo(pg, i)["paths"] for i in (1, 3, 4)])
        rebuilt = pg.evaluate("""async () => { const s = document.querySelector('#plThumbs .thumbP[data-index="1"] .paper > svg');
            window.__pw.ink.put('a2', [{ id: 'a2-x', page_id: 'a2', seq: 1000, kind: 'pen', style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 },
              data: { points: [[10, 10], [60, 60]] } }]);
            await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
            return document.querySelector('#plThumbs .thumbP[data-index="1"] .paper > svg') === s; }""")
        check("a change on page 2 rebuilds only thumb 2 (thumb 1's svg is the same element)", rebuilt)
        coalesce = pg.evaluate("""async () => {
            let n = 0; const T = document.getElementById('plThumbs'); const mo = new MutationObserver((ms) => { for (const m of ms) n += [...m.addedNodes].filter(x => x.tagName === 'svg').length; });
            mo.observe(T, { childList: true, subtree: true });
            for (let k = 0; k < 50; k++) window.__pw.ink.put('a2', [{ id: 'a2-c' + k, page_id: 'a2', seq: 1100 + k, kind: 'pen',
              style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[10 + k, 10], [60 + k, 60]] } }]);
            await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
            mo.disconnect(); return n; }""")
        check("50 changes in one go rebuild thumb 2 once", coalesce == 1, coalesce)

        # ------------------------------------------------------------ 3. a snapped shape shows as its element
        group[0] = "shape"
        close_list(pg)
        go_page(pg, 4)
        draw(pg, 4, [(100 + 320 * k / 12, 300 + wobble(k, 2.5) + k * 0.4) for k in range(13)], steps=6, hold=350); idle(pg)
        s4 = pg.evaluate("(id) => window.__pw.ink.strokesOf(id)", "a4")
        check("a held stroke on page 4 snapped to a line", len(s4) == 1 and s4[0]["kind"] == "shape" and s4[0]["data"]["type"] == "line",
              [(r["kind"], r["data"].get("type")) for r in s4])
        open_list(pg)
        t4 = tinfo(pg, 4)
        check("thumb 4 shows it as a <line>, not a path", t4["lines"] == 1 and t4["paths"] == 0, t4)
        pg.click("#undoBtn"); pg.wait_for_timeout(120)
        t4u = tinfo(pg, 4)
        pg.click("#redoBtn"); pg.wait_for_timeout(120)
        t4r = tinfo(pg, 4)
        check("undo takes the line out of the thumb, redo puts it back", t4u["lines"] == 0 and t4r["lines"] == 1, [t4u, t4r])

        # ------------------------------------------------------------ 4. a thumb tap keeps the panel open
        group[0] = "tap"
        open_list(pg)
        thumb(pg, 1).click(); pg.wait_for_timeout(120)
        thumb(pg, 3).click(); pg.wait_for_timeout(120)
        check("tap thumb 3: the list stays open", pg.locator("#pageList").is_visible() and pg.evaluate("document.getElementById('pageList').hidden") is False)
        check("the outline moves to thumb 3", pg.evaluate(CUR_JS) == ["3"], pg.evaluate(CUR_JS))
        check("the desk went to page 3 (S.cur 2, current() 2, 3 / 4 on the counters)",
              pg.evaluate("window.__pw.S.cur") == 2 and pg.evaluate("window.__pw.current()") == 2 and pg.evaluate(COUNTERS_JS)[:2] == ["3 / 4", "3 / 4"],
              [pg.evaluate("window.__pw.S.cur"), pg.evaluate("window.__pw.current()"), pg.evaluate(COUNTERS_JS)])
        sheet3 = pg.locator("#stack .sheet[data-index='3']").bounding_box()
        check("page 3 is at the top of the desk", sheet3 and abs(sheet3["y"] - pg.locator("#desk").bounding_box()["y"]) < 60, sheet3)
        thumb(pg, 2).click(); pg.wait_for_timeout(120)
        check("a second tap (thumb 2): still open, outline on 2, S.cur 1", pg.locator("#pageList").is_visible() and pg.evaluate(CUR_JS) == ["2"]
              and pg.evaluate("window.__pw.S.cur") == 1, [pg.evaluate(CUR_JS), pg.evaluate("window.__pw.S.cur")])
        d = pg.locator("#desk").bounding_box()
        pg.mouse.move(d["x"] + d["width"] - 20, d["y"] + d["height"] / 2); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(80)
        check("a pointer down on the desk (away from the list) closes it", pg.locator("#pageList").is_hidden())
        open_list(pg); pg.click("#plClose"); pg.wait_for_timeout(60)
        check("the X closes it", pg.locator("#pageList").is_hidden())
        pg.click("#listBtn"); pg.wait_for_timeout(260)
        on = pg.locator("#pageList").is_visible()
        pg.click("#listBtn"); pg.wait_for_timeout(60)
        check("the list button toggles it (open, then closed)", on and pg.locator("#pageList").is_hidden())
        open_list(pg); pg.keyboard.press("Escape"); pg.wait_for_timeout(60)
        check("Escape closes it", pg.locator("#pageList").is_hidden())
        check("no page errors", not errs, errs)

        # ------------------------------------------------------------ 5. timing: 8 pages, 300 strokes each
        group[0] = "timing"
        open_note(pg, "Timing")
        close_list(pg)
        ms1 = pg.evaluate("() => { const t0 = performance.now(); document.getElementById('listBtn').click(); return performance.now() - t0; }")
        pg.wait_for_timeout(300)
        counts = [tinfo(pg, i)["paths"] for i in range(1, 9)]
        pg.click("#plClose"); pg.wait_for_timeout(60)
        ms2 = pg.evaluate("() => { const t0 = performance.now(); document.getElementById('listBtn').click(); return performance.now() - t0; }")
        info_lines.append(f"renderPageList, 8 pages x 300 strokes (20 points each): first open {ms1:.1f} ms, second open {ms2:.1f} ms")
        check("all 8 thumbs drawn, 300 paths each", counts == [300] * 8, counts)
        check("no page errors (timing)", not errs, errs)

        # ------------------------------------------------------------ 6. tick mode (pw-v4q)
        group[0] = "tick mode (pw-v4q)"
        open_note(pg, "Ticks"); open_list(pg)
        ORIG = [110, 120, 130, 140, 150, 160]
        KEYS_JS = """() => window.__pw.S.pages.filter(p => p.note_id === 'n3' && !p.deleted_at).sort((a, b) => a.position - b.position)
            .map(p => { const s = window.__pw.ink.strokesOf(p.id); return s.length ? s[0].data.points[0][0] : null; })"""
        IDS3_JS = "() => window.__pw.S.pages.filter(p => p.note_id === 'n3' && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id)"
        STORED3_JS = """async () => { const d = await window.__pw.api.loadAll();
            return d.pages.filter(p => p.note_id === 'n3' && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id); }"""
        BAR_JS = "() => [...document.querySelectorAll('#plBar button')].map(b => [b.textContent, b.disabled])"
        UI_JS = """() => ({ sel: document.getElementById('plSel').textContent, selShown: !document.getElementById('plSel').hidden,
            done: !document.getElementById('plDone').hidden, all: !document.getElementById('plAll').hidden, select: !document.getElementById('plSelect').hidden,
            bar: !document.getElementById('plBar').hidden, ticks: [...document.querySelectorAll('#plThumbs .thumbP .tick')].filter(t => t.offsetParent).length,
            ticked: [...document.querySelectorAll('#plThumbs .thumbP.ticked')].map(t => +t.dataset.index),
            bars: [...document.querySelectorAll('#plThumbs .moveHere')].length, toast: document.getElementById('toast').textContent })"""
        keys = lambda: pg.evaluate(KEYS_JS)
        ui = lambda: pg.evaluate(UI_JS)
        U3 = lambda: pg.evaluate("(window.__pw.S.hist['n3'] || { u: [] }).u.length")
        tick = lambda: pg.evaluate("window.__pw.tick()")
        def tap(*ks):
            for k in ks: thumb(pg, k).click(); pg.wait_for_timeout(30)
        def select(): pg.click("#plSelect"); pg.wait_for_timeout(40)
        def act(name): pg.click(f"#plBar button[data-act='{name}']"); pg.wait_for_timeout(80); idle(pg)
        def undo(): pg.click("#undoBtn"); pg.wait_for_timeout(60); idle(pg)
        def redo(): pg.click("#redoBtn"); pg.wait_for_timeout(60); idle(pg)
        ids0 = pg.evaluate(IDS3_JS)
        check("set-up: 6 pages, one stroke each, told apart by x 110 to 160", keys() == ORIG, keys())
        u0 = U3(); cur0 = pg.evaluate("window.__pw.S.cur")

        # 1. Select: tick boxes, header, bar; a tap toggles and does not jump
        select(); q = ui()
        check("Select: 6 tick boxes, '0 selected', All and Done shown, Select hidden", q["ticks"] == 6 and q["sel"] == "0 selected" and q["selShown"]
              and q["done"] and q["all"] and not q["select"], q)
        check("the bar: Delete, Copy, Cut, Move, Share, all disabled", pg.evaluate(BAR_JS) == [["Delete", True], ["Copy", True], ["Cut", True], ["Move", True], ["Share", True]], pg.evaluate(BAR_JS))
        box = pg.evaluate("""() => { const t = document.querySelector('#plThumbs .thumbP .tick'), b = t.getBoundingClientRect(), s = getComputedStyle(t, '::before');
            return [Math.round(b.width), Math.round(b.height), parseFloat(s.width) + parseFloat(s.borderLeftWidth) + parseFloat(s.borderRightWidth), s.borderRadius]; }""")
        check("a tick box: 28 px round ring, 44 px hit area", box[:3] == [44, 44, 28] and box[3] == "50%", box)
        check("the page menu dots are hidden in tick mode", pg.evaluate("[...document.querySelectorAll('#plThumbs .thumbP .more')].every(m => !m.offsetParent)"))
        tap(3); q = ui()
        check("tap thumb 3: '1 selected', thumb 3 ticked, the buttons enabled", q["sel"] == "1 selected" and q["ticked"] == [3]
              and all(not d_ for _, d_ in pg.evaluate(BAR_JS)), [q, pg.evaluate(BAR_JS)])
        check("the tap does NOT jump the desk (S.cur, current() unchanged)", pg.evaluate("window.__pw.S.cur") == cur0 and pg.evaluate("window.__pw.current()") == cur0,
              [pg.evaluate("window.__pw.S.cur"), cur0])
        on = pg.evaluate("() => document.querySelector('#plThumbs .thumbP[data-index=\"3\"] .tick').getAttribute('aria-pressed')")
        pg.evaluate("() => document.querySelector('#plThumbs .thumbP[data-index=\"5\"] .tick').click()"); pg.wait_for_timeout(30)
        check("the tick box itself toggles too (aria-pressed follows)", on == "true" and ui()["ticked"] == [3, 5], ui())
        tap(3, 5)
        check("tapping again clears them: '0 selected', buttons disabled", ui()["sel"] == "0 selected" and all(d_ for _, d_ in pg.evaluate(BAR_JS)), ui())
        # 7. hold-and-drag is off in tick mode; right-click opens no page menu
        x, y = centre(pg, 2); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(450)
        held = pg.evaluate("window.__pw.pageDrag()")
        x2, y2 = centre(pg, 5); pg.mouse.move(x2, y2, steps=8); pg.mouse.up(); pg.wait_for_timeout(80); idle(pg)
        check("a hold on a thumb in tick mode lifts nothing, the drag moves nothing", held is None and keys() == ORIG and U3() == u0, [held, keys()])
        if ui()["ticked"]: tap(*ui()["ticked"])                             # a press and release can land as a click: clear it
        thumb(pg, 4).click(button="right"); pg.wait_for_timeout(60)
        check("right-click on a thumb in tick mode: no page menu", pg.locator("#menu").is_hidden())
        check("still 0 selected after that", ui()["sel"] == "0 selected", ui())

        # 2. tick 2 and 4, Delete
        tap(2, 4); act("delete"); q = ui()
        check("Delete pages 2 and 4: pages 1, 3, 5, 6 left in that order", keys() == [110, 130, 150, 160], keys())
        check("stored too", pg.evaluate(STORED3_JS) == [ids0[0], ids0[2], ids0[4], ids0[5]], pg.evaluate(STORED3_JS))
        check("one undo step, toast '2 pages deleted'", U3() == u0 + 1 and q["toast"] == "2 pages deleted", [U3() - u0, q["toast"]])
        check("the list stays open in tick mode, nothing ticked", pg.locator("#pageList").is_visible() and tick() == {"ids": [], "moving": False} and q["sel"] == "0 selected", [tick(), q])
        undo()
        check("undo: six pages in the original order with their strokes", keys() == ORIG and pg.evaluate(STORED3_JS) == ids0, keys())
        redo()
        check("redo: four again", keys() == [110, 130, 150, 160], keys())
        undo()

        # 3. tick 2 and 4, Copy; Paste after page 6
        u1 = U3()
        tap(2, 4); act("copy")
        check("Copy: the page clipboard holds 2 entries, tick mode is off, no undo step", pg.evaluate("window.__pw.S.clip.length") == 2 and tick() is None
              and U3() == u1 and ui()["toast"] == "2 pages copied", [pg.evaluate("window.__pw.S.clip.length"), tick(), ui()["toast"]])
        check("Select is back in the header, the bar is gone", ui()["select"] and not ui()["bar"] and not ui()["selShown"], ui())
        thumb(pg, 6).click(button="right"); pg.wait_for_timeout(60)
        items = [t_.strip() for t_ in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
        check("page 6's menu offers 'Paste 2 pages'", "Paste 2 pages" in items, items)
        pg.locator("#menu button", has_text="Paste 2 pages").click(); pg.wait_for_timeout(80); idle(pg)
        ids8 = pg.evaluate(IDS3_JS)
        check("Paste: 8 pages, the two new ones after page 6 carrying 2's and 4's strokes", keys() == ORIG + [120, 140], keys())
        newr = pg.evaluate("(id) => window.__pw.ink.strokesOf(id)", ids8[6])
        check("the pasted strokes are copies (new ids, on the new page)", len(newr) == 1 and newr[0]["id"] != "c2-s" and newr[0]["page_id"] == ids8[6], newr)
        check("Paste is one undo step", U3() == u1 + 1, U3() - u1)
        undo()
        check("undo: six again", keys() == ORIG, keys())

        # 4. tick 1 and 2, Cut; Paste after the last page
        u2 = U3()
        select(); tap(1, 2); act("cut")
        check("Cut pages 1 and 2: four pages left (3 to 6), one undo step, toast '2 pages cut', tick mode off", keys() == [130, 140, 150, 160] and U3() == u2 + 1
              and ui()["toast"] == "2 pages cut" and tick() is None, [keys(), U3() - u2, ui()["toast"]])
        thumb(pg, 4).click(button="right"); pg.wait_for_timeout(60)
        pg.locator("#menu button", has_text="Paste 2 pages").click(); pg.wait_for_timeout(80); idle(pg)
        check("Paste after the last page: six pages, the cut two at the end", keys() == [130, 140, 150, 160, 110, 120], keys())
        undo(); undo()
        check("undo twice: 1 to 6 again", keys() == ORIG and pg.evaluate(STORED3_JS) == ids0, keys())

        # 5. Move
        u3 = U3()
        select(); tap(5, 6); act("move"); q = ui()
        lbl = pg.evaluate("document.querySelector('#plBar .moveLbl').textContent")
        check("Move: the bar reads 'Move 2 pages: tap where they go' with Cancel", lbl == "Move 2 pages: tap where they go"
              and pg.evaluate(BAR_JS) == [["Cancel", False]], [lbl, pg.evaluate(BAR_JS)])
        info_lines.append(f"Move with pages 5 and 6 ticked: {q['bars']} 'Move here' bars (4 unticked pages give 5 gaps; the gap below page 4 is a no-op)")
        check("pages 5, 6 ticked: 4 bars (4 unticked + 1 = 5 gaps, minus the no-op gap below page 4)", q["bars"] == 4, q["bars"])
        first = pg.evaluate("""() => { const b = document.querySelector('#plThumbs .moveHere');
            return [b.dataset.gap, b.previousElementSibling ? 'x' : null, b.nextElementSibling.dataset.id, getComputedStyle(b).height, getComputedStyle(b).borderTopStyle]; }""")
        check("the first bar sits above page 1 (36 px, dashed)", first == ["0", None, ids0[0], "36px", "dashed"], first)
        nxt = pg.evaluate("() => [...document.querySelectorAll('#plThumbs .moveHere')].map(b => b.previousElementSibling && b.previousElementSibling.dataset.index)")
        check("the others sit below pages 1, 2 and 3 (none beside the ticked 5 and 6)", nxt == [None, "1", "2", "3"], nxt)
        bw = pg.evaluate("() => { const b = document.querySelector('#plThumbs .moveHere').getBoundingClientRect(), T = document.getElementById('plThumbs'); return [b.width, T.clientWidth - 28]; }")
        check("a bar is full width", abs(bw[0] - bw[1]) < 2, bw)
        pg.click("#plThumbs .moveHere[data-gap='0']"); pg.wait_for_timeout(80); idle(pg)
        check("tap the bar above page 1: order 5, 6, 1, 2, 3, 4", keys() == [150, 160, 110, 120, 130, 140], keys())
        check("stored too", pg.evaluate(STORED3_JS) == [ids0[4], ids0[5], ids0[0], ids0[1], ids0[2], ids0[3]], pg.evaluate(STORED3_JS))
        check("one undo step; tick mode ends, the list stays open, no bars left", U3() == u3 + 1 and tick() is None and pg.locator("#pageList").is_visible()
              and ui()["bars"] == 0, [U3() - u3, tick(), ui()])
        check("the first moved page is current (desk and list)", pg.evaluate("window.__pw.current()") == 0 and pg.evaluate(CUR_JS) == ["1"], pg.evaluate(CUR_JS))
        undo()
        check("undo restores 1 to 6", keys() == ORIG and pg.evaluate(STORED3_JS) == ids0, keys())
        select(); tap(1, 3); act("move"); q = ui()
        info_lines.append(f"Move with pages 1 and 3 ticked: {q['bars']} 'Move here' bars (4 unticked pages give 5 gaps; 1 and 3 are not side by side, so no gap is a no-op)")
        check("pages 1, 3 ticked: 5 bars (4 unticked + 1 = 5 gaps, no no-op gap: 1 and 3 are not together)", q["bars"] == 5, q["bars"])
        pg.click("#plBar button[data-act='cancel']"); pg.wait_for_timeout(40)
        check("Cancel: back to the ticks (1 and 3 still ticked), no bars", ui()["ticked"] == [1, 3] and ui()["bars"] == 0 and tick()["moving"] is False, ui())
        act("move")
        pg.click("#plThumbs .moveHere[data-gap='2']"); pg.wait_for_timeout(120); idle(pg)
        check("move them below page 4: order 2, 4, 1, 3, 5, 6", keys() == [120, 140, 110, 130, 150, 160], keys())
        sheet = pg.locator("#stack .sheet[data-index='3']").bounding_box()
        check("the desk jumped to the first moved page (page 3 now, current() 2, at the top)", pg.evaluate("window.__pw.current()") == 2 and pg.evaluate(CUR_JS) == ["3"]
              and sheet and abs(sheet["y"] - pg.locator("#desk").bounding_box()["y"]) < 60, [pg.evaluate("window.__pw.current()"), pg.evaluate(CUR_JS), sheet])
        undo()
        check("undo: 1 to 6", keys() == ORIG, keys())
        select(); tap(1, 2, 3, 4, 5, 6)
        check("Move is disabled with every page ticked (moving all changes nothing)", dict(map(tuple, pg.evaluate(BAR_JS)))["Move"] is True, pg.evaluate(BAR_JS))
        tap(1, 2, 3, 4, 5, 6)

        # 6. All, then Delete everything
        u4 = U3()
        pg.click("#plAll"); pg.wait_for_timeout(30); a1 = [ui()["sel"], pg.get_attribute("#plAll", "aria-pressed")]
        pg.click("#plAll"); pg.wait_for_timeout(30); a2 = [ui()["sel"], pg.get_attribute("#plAll", "aria-pressed")]
        check("All ticks every page; again clears them", a1 == ["6 selected", "true"] and a2 == ["0 selected", "false"], [a1, a2])
        pg.click("#plAll"); pg.wait_for_timeout(30)
        act("delete")
        idsF = pg.evaluate(IDS3_JS)
        check("tick everything, Delete: exactly one fresh empty page", len(idsF) == 1 and idsF[0] not in ids0 and keys() == [None]
              and pg.evaluate(STORED3_JS) == idsF, [idsF, keys()])
        check("one undo step, toast '6 pages deleted', still in tick mode", U3() == u4 + 1 and ui()["toast"] == "6 pages deleted" and ui()["sel"] == "0 selected", [U3() - u4, ui()])
        undo()
        check("undo brings the six back (the fresh page goes)", keys() == ORIG and pg.evaluate(STORED3_JS) == ids0, [keys(), pg.evaluate(STORED3_JS)])

        # 8. leaving tick mode
        tap(2); pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
        check("Escape leaves tick mode, the list stays open", tick() is None and pg.locator("#pageList").is_visible() and ui()["ticks"] == 0 and ui()["select"], ui())
        thumb(pg, 2).click(); pg.wait_for_timeout(100)
        check("out of tick mode a thumb tap goes to the page again", pg.evaluate("window.__pw.current()") == 1 and ui()["ticked"] == [], pg.evaluate("window.__pw.current()"))
        select(); tap(3); pg.click("#plDone"); pg.wait_for_timeout(40)
        check("Done leaves tick mode", tick() is None and ui()["ticks"] == 0 and not ui()["bar"], ui())
        select(); tap(4); pg.click("#plClose"); pg.wait_for_timeout(60)
        check("the X closes the panel and ends tick mode", pg.locator("#pageList").is_hidden() and tick() is None)
        open_list(pg)
        check("reopened: no ticks, Select in the header", tick() is None and ui()["ticked"] == [] and ui()["ticks"] == 0 and ui()["select"], ui())
        select(); tap(5)
        d = pg.locator("#desk").bounding_box()
        pg.mouse.move(d["x"] + d["width"] - 20, d["y"] + d["height"] / 2); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(80)
        check("closing the panel from the desk ends tick mode too", pg.locator("#pageList").is_hidden() and tick() is None)
        check("no page errors (tick mode)", not errs, errs)

        # ------------------------------------------------------------ 7. bookmarks (pw-v4r)
        group[0] = "bookmarks (pw-v4r)"
        MK_JS = """() => window.__pw.S.pages.filter(p => p.note_id === 'n4' && !p.deleted_at).sort((a, b) => a.position - b.position)
            .map(p => { const s = window.__pw.ink.strokesOf(p.id); return [s.length ? s[0].data.points[0][0] : null, p.bookmark === true]; })"""
        KEYS4_JS = """() => window.__pw.S.pages.filter(p => p.note_id === 'n4' && !p.deleted_at).sort((a, b) => a.position - b.position)
            .map(p => localStorage.getItem('pw.bookmark.' + p.id) === '1')"""
        SHEETS_JS = "() => [...document.querySelectorAll('#stack .sheet')].map(s => !!s.querySelector(':scope > .bookmarkTab'))"
        THUMBS_JS = "() => [...document.querySelectorAll('#plThumbs .thumbP')].map(t => [+t.dataset.index, !!t.querySelector('.paper > .bookmarkTab')])"
        EMPTY_JS = "() => [...document.querySelectorAll('#plThumbs .plEmpty')].map(e => e.textContent)"
        mk = lambda: pg.evaluate(MK_JS)
        U4 = lambda: pg.evaluate("(window.__pw.S.hist['n4'] || { u: [] }).u.length")
        R4 = lambda: pg.evaluate("(window.__pw.S.hist['n4'] || { r: [] }).r.length")
        toast_ = lambda: pg.evaluate("document.getElementById('toast').textContent")
        pressed = lambda: pg.get_attribute("#plMarks", "aria-pressed")
        def marks_toggle(): pg.click("#plMarks"); pg.wait_for_timeout(60)
        def page_menu(i):
            go_page(pg, i); pg.click("#noteMore"); pg.wait_for_timeout(40); return menu_items(pg)
        close_list(pg)
        open_note(pg, "Marks")
        check("set-up: 4 pages, none bookmarked (the record says bookmark: false)", mk() == [[110, False], [120, False], [130, False], [140, False]], mk())

        # 1. page 2's menu: Bookmark, right after the paper items; tap it
        items = page_menu(2)
        check("page 2's menu has 'Bookmark' right after the paper items (Lined), before 'Bin this note'",
              "Bookmark" in items and items.index("Bookmark") == items.index("Lined") + 1 and items.index("Bin this note") == items.index("Bookmark") + 1
              and "Remove bookmark" not in items, items)
        u0, r0 = U4(), R4()
        menu_click(pg, "Bookmark"); idle(pg)
        check("tap it: toast 'Bookmarked', page 2's record has bookmark: true", toast_() == "Bookmarked" and mk()[1] == [120, True]
              and [m[1] for m in mk()] == [False, True, False, False], [toast_(), mk()])
        check("kept on the device (pw.bookmark.m2)", pg.evaluate(KEYS4_JS) == [False, True, False, False], pg.evaluate(KEYS4_JS))
        check("the sheet shows the tab (page 2 only)", pg.evaluate(SHEETS_JS) == [False, True, False, False], pg.evaluate(SHEETS_JS))
        check("not an undo step (undo and redo counts unchanged)", U4() == u0 and R4() == r0, [U4() - u0, R4() - r0])
        tab = pg.evaluate("""() => { const s = document.querySelector('#stack .sheet[data-index="2"]'), t = s.querySelector(':scope > .bookmarkTab'),
            a = s.getBoundingClientRect(), b = t.getBoundingClientRect(), z = +document.getElementById('stack').dataset.zoom, path = t.querySelector('path'),
            ink = s.querySelector('svg.ink');
            return { z, w: b.width / z, h: b.height / z, top: (b.top - a.top) / z, right: (a.right - b.right) / z, pe: getComputedStyle(t).pointerEvents,
              fill: path && path.getAttribute('fill'), d: path && path.getAttribute('d'), zi: getComputedStyle(t).zIndex,
              above: !!ink && getComputedStyle(ink).zIndex === 'auto' && +getComputedStyle(t).zIndex > 0 }; }""")
        check("the tab: 16 x 26 page px, touching the top edge, 12 px in from the right", abs(tab["w"] - 16) < 0.5 and abs(tab["h"] - 26) < 0.5
              and abs(tab["top"]) < 0.5 and abs(tab["right"] - 12) < 0.5, tab)
        check("a V-notched ribbon, filled #3A4250, no pointer events, above the ink", tab["fill"] == "#3A4250" and tab["d"] == "M0 0H16V26L8 19L0 26Z"
              and tab["pe"] == "none" and tab["above"], tab)
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        fill_dark = pg.evaluate("getComputedStyle(document.querySelector('#stack .sheet[data-index=\"2\"] .bookmarkTab path')).fill")
        pg.evaluate("document.documentElement.removeAttribute('data-theme')")
        check("dark mode: the same colour (the paper is white)", fill_dark == "rgb(58, 66, 80)", fill_dark)
        pg.click("#noteMore"); pg.wait_for_timeout(40); items = menu_items(pg); pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
        check("the menu now says 'Remove bookmark' (no 'Bookmark')", "Remove bookmark" in items and "Bookmark" not in items, items)

        # 2. reload
        pg.reload(); ready(pg)
        if not pg.locator("#noteView").is_visible(): open_note(pg, "Marks")
        pg.wait_for_selector("#stack .sheet[data-index='4']"); pg.wait_for_timeout(80)
        check("reload: page 2 still bookmarked, the tab on its sheet", [m[1] for m in mk()] == [False, True, False, False]
              and pg.evaluate(SHEETS_JS) == [False, True, False, False], [mk(), pg.evaluate(SHEETS_JS)])

        # 3. the list: thumb 2 carries the tab; the Bookmarks toggle is off
        open_list(pg)
        check("the list: thumb 2 carries the tab, the others do not", pg.evaluate(THUMBS_JS) == [[1, False], [2, True], [3, False], [4, False]], pg.evaluate(THUMBS_JS))
        tt = pg.evaluate("""() => { const t = document.querySelector('#plThumbs .thumbP[data-index="2"] .paper > .bookmarkTab'), b = t.getBoundingClientRect(),
            p = t.parentElement.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height), Math.round(b.top - p.top), Math.round(p.right - b.right)]; }""")
        check("the thumb's tab: about 10 x 16, at the top right", tt[0] == 10 and tt[1] == 16 and abs(tt[2]) <= 1 and 0 <= tt[3] <= 10, tt)
        check("the Bookmarks toggle: in the header, off (aria-pressed false), labelled", pg.locator("#plMarks").is_visible() and pressed() == "false"
              and pg.get_attribute("#plMarks", "aria-label") == "Show bookmarked pages only", [pressed(), pg.get_attribute("#plMarks", "aria-label")])

        # 4. toggle on: only page 2; a tap jumps, the panel stays open; toggle off: four
        thumb(pg, 1).click(); pg.wait_for_timeout(100)
        marks_toggle()
        check("toggle on: one thumb (page 2), header '1 bookmarked', aria-pressed true", pg.evaluate(THUMBS_JS) == [[2, True]]
              and pg.inner_text("#plCount") == "1 bookmarked" and pressed() == "true", [pg.evaluate(THUMBS_JS), pg.inner_text("#plCount"), pressed()])
        thumb(pg, 2).click(); pg.wait_for_timeout(120)
        check("tap it: the desk jumps to page 2, the panel stays open", pg.evaluate("window.__pw.current()") == 1 and pg.evaluate(COUNTERS_JS)[1] == "2 / 4"
              and pg.locator("#pageList").is_visible() and pg.evaluate(CUR_JS) == ["2"], [pg.evaluate("window.__pw.current()"), pg.evaluate(COUNTERS_JS)])
        x, y = centre(pg, 2); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(450)
        held = pg.evaluate("window.__pw.pageDrag()"); pg.mouse.up(); pg.wait_for_timeout(80)
        check("hold-and-drag is off while the filter is on (nothing lifts)", held is None, held)
        pg.click("#plClose"); pg.wait_for_timeout(60); open_list(pg)
        check("the toggle is remembered while the app is open (close and reopen the list: still on)", pressed() == "true" and len(pg.evaluate(THUMBS_JS)) == 1, pressed())
        marks_toggle()
        check("toggle off: four thumbs, aria-pressed false, '2 / 4'", len(pg.evaluate(THUMBS_JS)) == 4 and pressed() == "false"
              and pg.inner_text("#plCount") == "2 / 4", [pg.evaluate(THUMBS_JS), pg.inner_text("#plCount")])

        # 5. bookmark page 4; copy it and paste: the copy is bookmarked; move page 2 to the end; delete it and undo
        close_list(pg)
        page_menu(4); menu_click(pg, "Bookmark"); idle(pg)
        check("page 4 bookmarked too", [m[1] for m in mk()] == [False, True, False, True], mk())
        open_list(pg)
        thumb(pg, 4).click(button="right"); pg.wait_for_timeout(60); menu_click(pg, "Copy")
        thumb(pg, 4).click(button="right"); pg.wait_for_timeout(60); menu_click(pg, "Paste"); idle(pg)
        check("copy page 4, paste: the pasted page is bookmarked (record, device, sheet, thumb)",
              mk() == [[110, False], [120, True], [130, False], [140, True], [140, True]] and pg.evaluate(KEYS4_JS) == [False, True, False, True, True]
              and pg.evaluate(SHEETS_JS) == [False, True, False, True, True] and [t_[1] for t_ in pg.evaluate(THUMBS_JS)] == [False, True, False, True, True],
              [mk(), pg.evaluate(KEYS4_JS), pg.evaluate(SHEETS_JS)])
        select(); tap(2); act("move"); pg.click("#plThumbs .moveHere[data-gap='4']"); pg.wait_for_timeout(80); idle(pg)
        check("move page 2 to the end (tick Move): it stays bookmarked", mk() == [[110, False], [130, False], [140, True], [140, True], [120, True]]
              and pg.evaluate(SHEETS_JS) == [False, False, True, True, True], [mk(), pg.evaluate(SHEETS_JS)])
        thumb(pg, 5).click(button="right"); pg.wait_for_timeout(60); menu_click(pg, "Delete"); idle(pg)
        gone = [mk(), pg.evaluate("localStorage.getItem('pw.bookmark.m2')")]
        check("delete it: gone, its device key too", gone[0] == [[110, False], [130, False], [140, True], [140, True]] and gone[1] is None, gone)
        undo()
        check("undo the delete: back at the end, bookmarked (record, device, sheet)", mk() == [[110, False], [130, False], [140, True], [140, True], [120, True]]
              and pg.evaluate("localStorage.getItem('pw.bookmark.m2')") == "1" and pg.evaluate(SHEETS_JS)[4] is True, [mk(), pg.evaluate(SHEETS_JS)])
        undo(); undo()
        check("undo the move and the paste: 4 pages, 2 and 4 still bookmarked (undo never touches a bookmark)",
              mk() == [[110, False], [120, True], [130, False], [140, True]], mk())

        # 6. remove both bookmarks, toggle on: 'No bookmarks yet'
        close_list(pg)
        page_menu(2); menu_click(pg, "Remove bookmark"); idle(pg); t2 = toast_()
        page_menu(4); menu_click(pg, "Remove bookmark"); idle(pg)
        check("Remove bookmark (pages 2 and 4): toast 'Bookmark removed', none left, no tabs, no device keys", t2 == "Bookmark removed"
              and [m[1] for m in mk()] == [False] * 4 and pg.evaluate(SHEETS_JS) == [False] * 4 and pg.evaluate(KEYS4_JS) == [False] * 4, [t2, mk()])
        open_list(pg); marks_toggle()
        empty = pg.evaluate(EMPTY_JS)
        check("toggle on with none: one line 'No bookmarks yet', no thumbs, '0 bookmarked'", empty == ["No bookmarks yet"]
              and pg.evaluate(THUMBS_JS) == [] and pg.inner_text("#plCount") == "0 bookmarked", [empty, pg.inner_text("#plCount")])
        marks_toggle()

        # 7. tick mode inside the filter: 2 and 3 bookmarked, toggle on, Select, tick both, Delete, undo
        close_list(pg)
        page_menu(2); menu_click(pg, "Bookmark"); idle(pg)
        page_menu(3); menu_click(pg, "Bookmark"); idle(pg)
        open_list(pg); marks_toggle()
        u7 = U4()
        select()
        check("Select in the filter: two tick boxes (the shown pages), the toggle hidden", ui()["ticks"] == 2 and pg.locator("#plMarks").is_hidden(), ui())
        pg.click("#plAll"); pg.wait_for_timeout(30); a_ = ui()["sel"]; pg.click("#plAll"); pg.wait_for_timeout(30)
        check("All ticks the shown pages only ('2 selected')", a_ == "2 selected", a_)
        tap(2, 3)
        check("tick both: '2 selected'; Move is off in the filter", ui()["sel"] == "2 selected" and dict(map(tuple, pg.evaluate(BAR_JS)))["Move"] is True,
              [ui(), pg.evaluate(BAR_JS)])
        act("delete")
        check("Delete: both gone, one undo step, toast '2 pages deleted'", mk() == [[110, False], [140, False]] and U4() == u7 + 1
              and ui()["toast"] == "2 pages deleted", [mk(), U4() - u7, ui()["toast"]])
        check("the filtered list now says 'No bookmarks yet'", pg.evaluate(EMPTY_JS) == ["No bookmarks yet"], pg.evaluate(EMPTY_JS))
        undo()
        check("undo brings them back bookmarked (record, device, sheets, the filtered list)", mk() == [[110, False], [120, True], [130, True], [140, False]]
              and pg.evaluate(KEYS4_JS) == [False, True, True, False] and pg.evaluate(SHEETS_JS) == [False, True, True, False]
              and pg.evaluate(THUMBS_JS) == [[2, True], [3, True]], [mk(), pg.evaluate(THUMBS_JS)])
        pg.click("#plDone"); pg.wait_for_timeout(40)
        check("Done: the toggle is back in the header, still on", pg.locator("#plMarks").is_visible() and pressed() == "true", pressed())
        pg.reload(); ready(pg)
        if not pg.locator("#noteView").is_visible(): open_note(pg, "Marks")
        open_list(pg)
        check("after a reload the toggle starts off (four thumbs), the bookmarks stay", pressed() == "false" and len(pg.evaluate(THUMBS_JS)) == 4
              and [m[1] for m in mk()] == [False, True, True, False], [pressed(), mk()])
        close_list(pg)
        check("no page errors (bookmarks)", not errs, errs)

        # ------------------------------------------------------------ 8. cache
        group[0] = "cache"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v5b" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v5b", "pw-v5b" in keys, keys)
        sw_src = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("sw.js lists vendor/jspdf.umd.min.js", "./vendor/jspdf.umd.min.js" in sw_src)
        ctx.close()

        # ------------------------------------------------------------ 9. share (pw-v4t)
        group[0] = "share (pw-v4t)"
        SHARE_SEED_JS = """() => {
          localStorage.clear();
          const t = '2026-10-26T10:00:00Z', P = (id, nid, k) => ({ id, note_id: nid, position: k, orientation: 'portrait', background: 'grid',
            deleted_at: null, created_at: t, updated_at: t });
          localStorage.setItem('penworks.local.v2', JSON.stringify({
            folders: [{ id: 'f1', parent_id: null, name: 'Share', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
            notes: [{ id: 'n1', folder_id: 'f1', name: 'Test note', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-26T10:02:00Z' },
                    { id: 'n2', folder_id: 'f1', name: 'Twelve', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-26T10:01:00Z' }],
            pages: [...[1, 2, 3, 4].map((k) => P('t' + k, 'n1', k - 1)), ...Array.from({ length: 12 }, (_, k) => P('w' + (k + 1), 'n2', k))] }));
          const st = (pid, k, x, y) => ({ id: pid + '-s' + k, page_id: pid, seq: k + 1, kind: 'pen', style: { colour: '#000000', width: 3, dash: 'solid', opacity: 1 },
            data: { points: Array.from({ length: 30 }, (_, j) => [x + j * 12, Math.round((y + 20 * Math.sin(j / 3)) * 10) / 10]) } });
          const hl = { id: 't2-hl', page_id: 't2', seq: 50, kind: 'highlighter', style: { colour: '#FFD400', width: 24, dash: 'solid', opacity: 0.4 },
            data: { points: [[100, 700], [600, 700]] } };
          for (let k = 1; k <= 4; k++) localStorage.setItem('pw.strokes.t' + k, JSON.stringify([st('t' + k, 0, 100, 200 + 60 * k), ...(k === 2 ? [hl] : [])]));
          for (let k = 1; k <= 12; k++) localStorage.setItem('pw.strokes.w' + k, JSON.stringify(Array.from({ length: 60 }, (_, j) => st('w' + k, j, 60 + (j % 3) * 30, 80 + j * 16))));
        }"""
        STUB_JS = "navigator.canShare = () => true; navigator.share = async (d) => { window.__shared = d; window.__sharedAt = performance.now(); };"
        NOSHARE_JS = "navigator.canShare = () => true; Object.defineProperty(navigator, 'share', { value: undefined, configurable: true, writable: true });"
        SHARED_JS = """async () => { const d = window.__shared; if (!d) return null;
            const b64 = async (f) => { const u = new Uint8Array(await f.arrayBuffer()); let s = '';
              for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
            return { title: d.title, files: await Promise.all(d.files.map(async (f) => ({ name: f.name, type: f.type, size: f.size, b64: await b64(f) }))) }; }"""
        DLG_JS = """() => { const d = document.getElementById('shareDlg'), i = document.getElementById('shareName');
            if (!d) return { open: false };
            const r = d.querySelector('.dlg').getBoundingClientRect();
            return { open: true, value: i.value, selAll: i.selectionStart === 0 && i.selectionEnd === i.value.length && i.value.length > 0,
              focused: document.activeElement === i, buttons: [...d.querySelectorAll('button')].map(b => b.textContent),
              centred: Math.abs(r.left + r.width / 2 - innerWidth / 2) < 2 && Math.abs(r.top + r.height / 2 - innerHeight / 2) < 2 }; }"""
        STATE_JS = """() => ({ strokes: ['t1', 't2', 't3', 't4'].map(id => window.__pw.ink.strokesOf(id).length),
            undo: (window.__pw.S.hist['n1'] || { u: [] }).u.length, redo: (window.__pw.S.hist['n1'] || { r: [] }).r.length,
            pages: window.__pw.S.pages.filter(p => p.note_id === 'n1' && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id + p.orientation + p.background) })"""
        brief = lambda sh: None if not sh else {"title": sh["title"], "files": [[f["name"], f["type"], f["size"]] for f in sh["files"]]}
        def dark_count(pix):
            a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            return int((a[:, :, :3].max(axis=2) < 100).sum())
        def pdf_info(f):
            doc = fitz.open(stream=base64.b64decode(f["b64"]), filetype="pdf")
            out = {"pages": doc.page_count, "sizes": [(round(p_.rect.width, 2), round(p_.rect.height, 2)) for p_ in doc],
                   "dark1": dark_count(doc[0].get_pixmap(dpi=200))}
            doc.close(); return out
        def png_info(f):
            data = base64.b64decode(f["b64"])
            head = data[:8] == b"\x89PNG\r\n\x1a\n"
            w_, h_ = struct.unpack(">II", data[16:24])
            pix = fitz.Pixmap(data)
            a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            return {"png": head, "size": (w_, h_), "dark": int((a[:, :, :3].max(axis=2) < 100).sum()), "px": a}
        A4P, A4L = (595.28, 841.89), (841.89, 595.28)
        near = lambda s_, t_: abs(s_[0] - t_[0]) <= 1 and abs(s_[1] - t_[1]) <= 1
        def fresh_share(init_js):
            c = b.new_context(viewport={"width": 1280, "height": 1300}, accept_downloads=True)
            c.add_init_script(init_js)
            p = c.new_page(); e = []
            p.on("pageerror", lambda x: e.append(str(x)))
            p.goto(LOCAL); ready(p); p.evaluate(SHARE_SEED_JS); p.reload(); ready(p)
            if p.locator("#noteView").is_visible(): p.click("#backBtn"); p.wait_for_selector("#listView:not([hidden])")
            p.locator(".frow", has_text="Share").first.click(); p.wait_for_timeout(60)
            return c, p, e
        def share_start(p, ticks=(), all_=False):
            open_list(p)
            if p.evaluate("window.__pw.tick()") is not None: p.click("#plDone"); p.wait_for_timeout(40)
            p.click("#plSelect"); p.wait_for_timeout(40)
            if all_: p.click("#plAll"); p.wait_for_timeout(40)
            for k in ticks: thumb(p, k).click(); p.wait_for_timeout(30)
            p.click("#plBar button[data-act='share']"); p.wait_for_selector("#shareDlg")
        def share_go(p, kind, name=None):
            if name is not None: p.fill("#shareName", name)
            p.evaluate("window.__shared = null")
            t0 = p.evaluate("performance.now()")
            p.click(f"#shareDlg button[data-share='{kind}']")
            p.wait_for_function("window.__shared", timeout=30000)
            ms = p.evaluate("window.__sharedAt") - t0
            p.wait_for_selector("#shareDlg", state="detached"); p.wait_for_timeout(40)
            return p.evaluate(SHARED_JS), ms

        c2, p2, e2 = fresh_share(STUB_JS)
        open_note(p2, "Test note")
        st0 = p2.evaluate(STATE_JS)
        check("set-up: 'Test note' with 4 pages, a stroke each (page 2 a highlighter stroke too)", st0["strokes"] == [1, 2, 1, 1] and len(st0["pages"]) == 4, st0)
        # 1. tick 2 and 3, Share: the dialog
        open_list(p2); p2.click("#plSelect"); p2.wait_for_timeout(40)
        fits = p2.evaluate("""() => { const B = document.getElementById('plBar');
            return [...B.querySelectorAll('.plAct')].every(x => x.scrollWidth <= x.clientWidth) && B.scrollWidth <= B.clientWidth; }""")
        check("the five bar words fit the list (no button or bar overflows)", fits)
        share_start(p2, (2, 3)); q = p2.evaluate(DLG_JS)
        check("tick 2 and 3, Share: a dialog, the name box holds 'Test note p2-3', all of it selected, focused", q.get("value") == "Test note p2-3"
              and q["selAll"] and q["focused"], q)
        check("the dialog: Share as PDF, Share as images, Cancel; centred", q.get("buttons") == ["Share as PDF", "Share as images", "Cancel"] and q["centred"], q)
        p2.keyboard.press("Escape"); p2.wait_for_timeout(40)
        check("Escape closes it (the ticks stay)", not p2.evaluate(DLG_JS)["open"] and p2.evaluate("window.__pw.tick()") == {"ids": ["t2", "t3"], "moving": False},
              p2.evaluate("window.__pw.tick()"))
        p2.click("#plBar button[data-act='share']"); p2.wait_for_selector("#shareDlg"); p2.click("#shareDlg button[data-share='cancel']"); p2.wait_for_timeout(40)
        ok_cancel = not p2.evaluate(DLG_JS)["open"]
        p2.click("#plBar button[data-act='share']"); p2.wait_for_selector("#shareDlg"); p2.mouse.click(1270, 1290); p2.wait_for_timeout(40)
        check("Cancel closes it, and so does a tap outside", ok_cancel and not p2.evaluate(DLG_JS)["open"])
        # 2. Share as PDF
        p2.click("#plBar button[data-act='share']"); p2.wait_for_selector("#shareDlg")
        typed = p2.evaluate("document.getElementById('shareName').value")
        p2.keyboard.type("Homework week 3"); p2.wait_for_timeout(20)
        check("typing replaces the selected name", p2.evaluate("document.getElementById('shareName').value") == "Homework week 3", typed)
        sh, ms = share_go(p2, "pdf")
        fs = sh["files"] if sh else []
        check("Share as PDF: one file 'Homework week 3.pdf', application/pdf, over 10 KB, title = the name",
              len(fs) == 1 and fs[0]["name"] == "Homework week 3.pdf" and fs[0]["type"] == "application/pdf" and fs[0]["size"] > 10240
              and sh["title"] == "Homework week 3", brief(sh))
        pi = pdf_info(fs[0]) if fs else {}
        check("the PDF: 2 pages, both A4 portrait within 1 pt", pi.get("pages") == 2 and all(near(s_, A4P) for s_ in pi["sizes"]), pi)
        check("PDF page 1 is not blank (over 50 dark pixels at 200 dpi)", pi.get("dark1", 0) > 50, pi.get("dark1"))
        st1 = p2.evaluate(STATE_JS)
        check("after the share: tick mode is off, toast 'Shared'", p2.evaluate("window.__pw.tick()") is None
              and p2.evaluate("document.getElementById('toast').textContent") == "Shared", p2.evaluate("document.getElementById('toast').textContent"))
        check("nothing on the page changed (strokes, undo and redo counts, pages)", st1 == st0, [st0, st1])
        # 3. Share as images
        share_start(p2, (2, 3)); sh, ms = share_go(p2, "images", "Homework week 3")
        fs = sh["files"] if sh else []
        check("Share as images: 'Homework week 3-1.png' and '-2.png', image/png",
              [f["name"] for f in fs] == ["Homework week 3-1.png", "Homework week 3-2.png"] and all(f["type"] == "image/png" for f in fs), brief(sh))
        pis = [png_info(f) for f in fs]
        check("each is a 1588 x 2246 PNG (header), not blank", len(pis) == 2 and all(x["png"] and x["size"] == (1588, 2246) and x["dark"] > 50 for x in pis),
              [(x["png"], x["size"], x["dark"]) for x in pis])
        if pis:
            px = [int(v) for v in pis[0]["px"][1400, 700, :3]]; grid = [int(v) for v in pis[0]["px"][100, 0, :3]]
        else: px, grid = [], []
        check("page 2's highlighter keeps its opacity: #FFD400 at 0.4 over white is about (255, 238, 153)",
              len(px) == 3 and abs(px[0] - 255) <= 8 and abs(px[1] - 238) <= 8 and abs(px[2] - 153) <= 8, px)
        check("the paper pattern is drawn (a grid line at the page's left edge, not white)", len(grid) == 3 and max(grid) < 245 and min(grid) > 180, grid)
        check("still nothing changed on the page", p2.evaluate(STATE_JS) == st0, p2.evaluate(STATE_JS))
        # 7. a name of only punctuation, and one with a few banned characters
        share_start(p2, (1,)); sh, _ = share_go(p2, "pdf", "???")
        check("the name '???' gives 'PenWorks.pdf'", sh and [f["name"] for f in sh["files"]] == ["PenWorks.pdf"], brief(sh))
        share_start(p2, (1,)); sh, _ = share_go(p2, "images", " Wiskunde/ê-toets: (V1) [b]? ")
        check("'Wiskunde/ê-toets: (V1) [b]?' keeps letters, digits, spaces, dashes, brackets: 'Wiskundeê-toets (V1) [b].png'",
              sh and [f["name"] for f in sh["files"]] == ["Wiskundeê-toets (V1) [b].png"], brief(sh))
        # a cancelled share sheet says nothing; any other refusal downloads
        p2.evaluate("() => { navigator.share = async () => { throw new DOMException('cancelled', 'AbortError'); }; }")
        dls = []; p2.on("download", lambda d: dls.append(d))
        p2.evaluate("document.getElementById('toast').textContent = 'x'")
        share_start(p2, (1,)); p2.click("#shareDlg button[data-share='pdf']"); p2.wait_for_selector("#shareDlg", state="detached"); p2.wait_for_timeout(400)
        check("a cancelled share sheet (AbortError): no toast, no download", p2.evaluate("document.getElementById('toast').textContent") == "x" and not dls,
              [p2.evaluate("document.getElementById('toast').textContent"), len(dls)])
        p2.evaluate("() => { navigator.share = async () => { throw new DOMException('no gesture', 'NotAllowedError'); }; }")
        share_start(p2, (1,))
        with p2.expect_download() as dl: p2.click("#shareDlg button[data-share='pdf']")
        p2.wait_for_selector("#shareDlg", state="detached"); p2.wait_for_timeout(60)
        check("any other refusal (NotAllowedError): the file downloads, toast 'Saved to downloads'", dl.value.suggested_filename == "Test note p1.pdf"
              and p2.evaluate("document.getElementById('toast').textContent") == "Saved to downloads", [dl.value.suggested_filename])
        p2.evaluate("() => { navigator.share = async (d) => { window.__shared = d; window.__sharedAt = performance.now(); }; }")
        # 4. one landscape page
        go_page(p2, 4); p2.click("#noteMore"); p2.wait_for_timeout(40); menu_click(p2, "Landscape"); menu_click(p2, "Just this page"); idle(p2)
        check("set-up: page 4 is landscape (page menu)", p2.evaluate("window.__pw.S.pages.find(p => p.id === 't4').orientation") == "landscape")
        share_start(p2, (4,)); q = p2.evaluate(DLG_JS)
        check("one page ticked: the name box says 'Test note p4'", q.get("value") == "Test note p4", q)
        sh, _ = share_go(p2, "pdf")
        pi = pdf_info(sh["files"][0]) if sh else {}
        check("its PDF: 1 page, A4 landscape within 1 pt, not blank", sh and sh["files"][0]["name"] == "Test note p4.pdf" and pi.get("pages") == 1
              and near(pi["sizes"][0], A4L) and pi["dark1"] > 50, [brief(sh), pi])
        share_start(p2, (4,)); sh, _ = share_go(p2, "images")
        pis = [png_info(f) for f in sh["files"]] if sh else []
        check("its image: one 'Test note p4.png', 2246 x 1588", sh and [f["name"] for f in sh["files"]] == ["Test note p4.png"] and pis[0]["size"] == (2246, 1588),
              [brief(sh), [x["size"] for x in pis]])
        # 5. all four
        share_start(p2, all_=True); q = p2.evaluate(DLG_JS)
        check("All four ticked: the name box says 'Test note' (no page suffix)", q.get("value") == "Test note", q)
        sh, _ = share_go(p2, "pdf")
        pi = pdf_info(sh["files"][0]) if sh else {}
        check("the PDF: 4 pages, 1 to 3 portrait, 4 landscape", sh and sh["files"][0]["name"] == "Test note.pdf" and pi.get("pages") == 4
              and all(near(s_, A4P) for s_ in pi["sizes"][:3]) and near(pi["sizes"][3], A4L), pi)
        # 6. twelve pages: progress and time
        close_list(p2); open_note(p2, "Twelve"); share_start(p2, all_=True)
        p2.evaluate("""() => { window.__prog = []; const d = document.getElementById('shareDlg'), b = d.querySelector("button[data-share='pdf']");
            new MutationObserver(() => window.__prog.push([b.textContent, [...d.querySelectorAll('button')].every(x => x.disabled)]))
              .observe(b, { childList: true, characterData: true, subtree: true }); }""")
        sh, ms12 = share_go(p2, "pdf", "Twelve pages")
        prog = p2.evaluate("window.__prog")
        texts = [t_ for t_, _ in prog]
        check("12 pages: the button counts 'Rendering 1 / 12' to 'Rendering 12 / 12', every button disabled meanwhile",
              "Rendering 1 / 12" in texts and "Rendering 12 / 12" in texts and all(d_ for t_, d_ in prog if t_.startswith("Rendering")), texts)
        pi = pdf_info(sh["files"][0]) if sh else {}
        check("the 12-page PDF has 12 pages", pi.get("pages") == 12, pi)
        check("12 A4 pages at 2x render and share in under 6 s", 0 < ms12 < 6000, round(ms12))
        info_lines.append(f"share: 12 A4 pages (60 strokes each) at 2x to one PDF in {round(ms12)} ms, {round(sh['files'][0]['size'] / 1024) if sh else '?'} KB")
        share_start(p2, all_=True); sh, msi = share_go(p2, "images", "Twelve pages")
        info_lines.append(f"share: the same 12 pages as PNGs in {round(msi)} ms")
        check("no page errors (share)", not e2, e2)
        c2.close()

        # 6. no navigator.share: downloads
        c3, p3, e3 = fresh_share(NOSHARE_JS)
        open_note(p3, "Test note")
        dl3 = []; p3.on("download", lambda d: dl3.append(d))
        def wait_dl(n, ms=15000):
            t0 = time.time()
            while len(dl3) < n and (time.time() - t0) * 1000 < ms: p3.wait_for_timeout(50)
        share_start(p3, (2, 3)); p3.fill("#shareName", "Homework week 3"); p3.click("#shareDlg button[data-share='pdf']"); wait_dl(1); p3.wait_for_timeout(300)
        check("no navigator.share: Share as PDF downloads one file 'Homework week 3.pdf'", [d.suggested_filename for d in dl3] == ["Homework week 3.pdf"],
              [d.suggested_filename for d in dl3])
        check("toast 'Saved to downloads', tick mode off", p3.evaluate("document.getElementById('toast').textContent") == "Saved to downloads"
              and p3.evaluate("window.__pw.tick()") is None, p3.evaluate("document.getElementById('toast').textContent"))
        dl3.clear()
        share_start(p3, (2, 3)); p3.fill("#shareName", "Homework week 3"); p3.click("#shareDlg button[data-share='images']"); wait_dl(2); p3.wait_for_timeout(400)
        check("and Share as images downloads two: '-1.png', '-2.png'", [d.suggested_filename for d in dl3] == ["Homework week 3-1.png", "Homework week 3-2.png"],
              [d.suggested_filename for d in dl3])
        check("no page errors (downloads)", not e3, e3)
        c3.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for line in info_lines: print(line)
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
