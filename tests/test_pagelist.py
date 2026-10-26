# PenWorks page list checks (pw-v4i): the thumbnails draw the page's ink, and a thumb tap keeps the panel open.
# Run: python tests/test_pagelist.py              (local mode only: ?local=1, Supabase is never touched)
# Headless Playwright (Python), same harness as tests/test_pagedrag.py. Strokes are seeded straight into the
# local store (pw.strokes.<page_id>, the records store-local.js reads); the mouse draws the rest on the desk.
# A thumb's ink is one <svg class="thumbInk"> inside its .paper, always there (an empty page: an svg with no paths).
# A pen landing on the desk closes the panel (her "until I click on the page again"), so the live refresh is checked
# through the stroke funnel with the panel open: ink.put (the same apply every stroke lands through) and the tray's
# undo and redo buttons, which are not on the desk.
import sys, subprocess, time, pathlib, math
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
            { id: 'n2', folder_id: 'f1', name: 'Timing', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-25T10:01:00Z' }],
    pages: [...[1, 2, 3, 4].map((k) => pg('a' + k, 'n1', k - 1)), ...[1, 2, 3, 4, 5, 6, 7, 8].map((k) => pg('b' + k, 'n2', k - 1))] }));
  let seq = 0;
  const stroke = (pid, k, n) => ({ id: pid + '-s' + k, page_id: pid, seq: ++seq, kind: 'pen',
    style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 },
    data: { points: Array.from({ length: n }, (_, j) => [Math.round((80 + j * 12 + (k % 40) * 4) * 10) / 10,
                                                         Math.round((100 + (k % 50) * 19 + 8 * Math.sin(j)) * 10) / 10]) } });
  const put = (pid, count, n) => localStorage.setItem('pw.strokes.' + pid, JSON.stringify(Array.from({ length: count }, (_, k) => stroke(pid, k, n))));
  put('a1', 2, 20); put('a3', 3, 20);
  for (let k = 1; k <= 8; k++) put('b' + k, 300, 20);
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

        # ------------------------------------------------------------ 6. cache
        group[0] = "cache"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v4m" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v4m", "pw-v4m" in keys, keys)
        ctx.close()
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
