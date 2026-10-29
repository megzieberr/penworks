# PenWorks Cut chip checks (pw-v7l): headless Playwright (Python), same style as tests/test_u2b.py.
# Run: python tests/test_cut.py               (local mode only: ?local=1, Supabase is never touched)
# Her ask (29 Oct): "I want a cut, not just a copy." A fourth selection chip, Cut (scissors), in the order Copy, Cut,
# Duplicate, Delete: the selection goes on the clipboard as Copy puts it there, then its strokes come off the page as
# Delete takes them, ONE undo step (undo brings them back, the clipboard keeps them), toast "Cut."; a finger hold and
# Paste puts them on another page. With nothing selected Cut does nothing. On a phone (375 px wide) all four chips stay
# inside the desk, also beside a small selection near the page's right edge, and they never cover the turn ring.
import sys, subprocess, time, pathlib, re, math
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8815
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-29T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Cut', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Scissors', '2026-10-29T10:02:00Z'), N('n2', 'Other', '2026-10-29T10:01:00Z')],
    pages: [P('p1', 'n1', 0), P('p2', 'n1', 1), P('p3', 'n2', 0)] }));
}"""
STROKES_JS = "(id) => window.__pw.ink.strokesOf(id)"
SEL_JS = "() => window.__pw.ink.selection()"
PUT_JS = "([pid, recs]) => import('./js/ink.js').then(m => m.put(pid, recs))"
CHIPS_JS = """() => { const c = document.querySelector('.selChips'); if (!c || !c.isConnected) return null; const r = c.getBoundingClientRect(), d = document.getElementById('desk').getBoundingClientRect();
  return { n: c.querySelectorAll('button').length, acts: [...c.querySelectorAll('button')].map(b => b.dataset.act),
           labels: [...c.querySelectorAll('button')].map(b => b.getAttribute('aria-label')), titles: [...c.querySelectorAll('button')].map(b => b.title),
           left: r.left, top: r.top, right: r.right, bottom: r.bottom, desk: [d.left, d.top, d.right, d.bottom], shown: r.height > 0 }; }"""
CUTSTYLE_JS = """() => { const d = document.querySelector('.selChips .chip[data-act="cut"]'), c = document.querySelector('.selChips .chip[data-act="copy"]');
  const k = (e) => { const s = getComputedStyle(e), v = e.querySelector('svg'); return [s.backgroundColor, s.color, s.width, s.height, s.borderRadius,
    v.getAttribute('stroke-width'), v.getAttribute('viewBox'), getComputedStyle(v).width]; };
  return d && c ? { cut: k(d), copy: k(c), svgs: d.querySelectorAll('svg').length, text: d.textContent.trim() } : null; }"""
RING_JS = """() => { const c = document.querySelector('svg.ink g.sel circle.selrot'); return c ? [+c.getAttribute('cx'), +c.getAttribute('cy')] : null; }"""
MENU_JS = """() => { const m = document.getElementById('menu'), r = m.getBoundingClientRect();
  return { shown: !m.hidden && r.height > 0, items: [...m.querySelectorAll('button')].map(b => ({ label: b.textContent.trim(), disabled: b.disabled })) }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def strokes(pg, pid): return pg.evaluate(STROKES_JS, pid)
def ids(pg, pid): return sorted(s["id"] for s in strokes(pg, pid))
def sel(pg): return pg.evaluate(SEL_JS)
def chips(pg): return pg.evaluate(CHIPS_JS)
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name):
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def go_page(pg, i):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
    pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120)
    if pg.locator("#pageList").is_visible(): pg.click("#plClose"); pg.wait_for_timeout(60)
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def tap_page(pg, i, x, y):
    sx, sy = screen(pg, i, x, y); pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(40)
def drag_page(pg, i, a, b, steps=10):
    sx, sy = screen(pg, i, *a); pg.mouse.move(sx, sy); pg.mouse.down()
    tx, ty = screen(pg, i, *b); pg.mouse.move(tx, ty, steps=steps); pg.mouse.up(); pg.wait_for_timeout(40)
def U(pg): return pg.evaluate("window.__pw.S.hist[window.__pw.S.openNote] ? window.__pw.S.hist[window.__pw.S.openNote].u.length : 0")
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(30)
def redo(pg): pg.click("#redoBtn"); pg.wait_for_timeout(30)
def tool(pg, t): pg.click(f"#tool-{t}"); pg.wait_for_timeout(20)
def near(a, b, tol): return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
def fresh(b, w=1280, h=1300, **kw):
    ctx = b.new_context(viewport={"width": w, "height": h}, **kw)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg)
    pg.evaluate(SEED_JS); pg.reload(); ready(pg)
    return ctx, pg, errs
ST = {"colour": "#000000", "width": 2, "dash": "solid", "opacity": 1}
def rec(rid, pid, pts, k=0): return {"id": rid, "page_id": pid, "seq": int(time.time() * 1000) + k, "kind": "pen", "style": dict(ST), "data": {"points": pts}}
def pbox(recs):
    b_ = [1e9, 1e9, -1e9, -1e9]
    for r in recs:
        w = r["style"]["width"] / 2
        for x, y in r["data"]["points"]: b_ = [min(b_[0], x - w), min(b_[1], y - w), max(b_[2], x + w), max(b_[3], y + w)]
    return b_
def ctr(b_): return ((b_[0] + b_[2]) / 2, (b_[1] + b_[3]) / 2)
def inside(c_): return c_ and c_["n"] == 4 and c_["shown"] and c_["left"] >= c_["desk"][0] - 0.5 and c_["top"] >= c_["desk"][1] - 0.5 and c_["right"] <= c_["desk"][2] + 0.5 and c_["bottom"] <= c_["desk"][3] + 0.5
def ring_free(pg, i):
    rg = pg.evaluate(RING_JS)
    if not rg: return False
    rx_, ry_ = screen(pg, i, rg[0], rg[1])
    return not pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e ? !!e.closest('button') : true; }", [rx_, ry_])

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # ------------------------------------------------------------ the Cut chip on a desktop screen
        group[0] = "cut chip"
        ctx, pg, errs = fresh(b, has_touch=True)
        open_note(pg, "Scissors")
        cdp = ctx.new_cdp_session(pg)
        def touch(kind, pts=()): cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y, "id": k} for k, (x, y) in enumerate(pts)]})
        def hold(i, px, py, ms=600):
            x, y = screen(pg, i, px, py); touch("touchStart", [(x, y)]); pg.wait_for_timeout(ms); return x, y
        def lift(): touch("touchEnd"); pg.wait_for_timeout(60)
        def menu(): return pg.evaluate(MENU_JS)
        def paste_btn(): return pg.locator("#menu button").filter(has_text=re.compile("^Paste$"))
        def cut(): pg.locator(".selChips .chip[data-act='cut']").click(); pg.wait_for_timeout(40)

        pg.evaluate(PUT_JS, ["p1", [rec("a", "p1", [[150, 200], [250, 220], [350, 200]], 1),
                                    rec("b", "p1", [[150, 280], [250, 300], [350, 280]], 2),
                                    rec("c", "p1", [[150, 600], [250, 620], [350, 600]], 3)]])
        before = {s["id"]: s for s in strokes(pg, "p1")}
        tool(pg, "select")

        # 1: nothing selected: no chips at all, and a Cut chip kept from an old selection does nothing
        check("nothing selected: no chips on the desk", chips(pg) is None, chips(pg))
        drag_page(pg, 1, (120, 170), (380, 330))
        check("a box around two of three: those two are selected", sel(pg) and sorted(sel(pg)["ids"]) == ["a", "b"], sel(pg))
        pg.evaluate("() => { window.__oldCut = document.querySelector('.selChips .chip[data-act=\"cut\"]'); }")
        tap_page(pg, 1, 600, 1000)
        u0, clip0 = U(pg), pg.evaluate("window.__pw.ink.hasClip()")
        check("a tap on empty paper clears the selection (no chips)", sel(pg) is None and chips(pg) is None, sel(pg))
        pg.evaluate("() => window.__oldCut.click()"); pg.wait_for_timeout(40)
        check("Cut with nothing selected does nothing: the same three strokes, no undo step, the clipboard still empty",
              ids(pg, "p1") == ["a", "b", "c"] and U(pg) == u0 and clip0 is False and pg.evaluate("window.__pw.ink.hasClip()") is False, [ids(pg, "p1"), U(pg), u0])

        # 2: four chips in the order Copy, Cut, Duplicate, Delete; Cut looks like Copy
        drag_page(pg, 1, (120, 170), (380, 330))
        ch = chips(pg)
        check("four chips in the order Copy, Cut, Duplicate, Delete (aria-label and title)",
              ch and ch["acts"] == ["copy", "cut", "duplicate", "delete"] and ch["labels"] == ["Copy", "Cut", "Duplicate", "Delete"] and ch["titles"] == ch["labels"], ch)
        cs = pg.evaluate(CUTSTYLE_JS)
        check("the Cut chip looks like the Copy chip (colours, 38 px round, icon stroke and size), one svg, no words",
              cs and cs["cut"] == cs["copy"] and cs["svgs"] == 1 and cs["text"] == "" and cs["cut"][2] == "38px", cs)
        check("the four chips do not cover the turn ring", ring_free(pg, 1))

        # 3: Cut: the two come off the page, the clipboard holds them, one undo step, toast Cut.
        u1 = U(pg)
        cut()
        check("Cut: the two selected strokes are gone, the third stays", ids(pg, "p1") == ["c"], ids(pg, "p1"))
        check("Cut: the selection and its chips are cleared", sel(pg) is None and chips(pg) is None, sel(pg))
        check("Cut: one undo step", U(pg) == u1 + 1, [U(pg), u1])
        check("Cut: the clipboard holds them (hasClip)", pg.evaluate("window.__pw.ink.hasClip()") is True)
        check("Cut: the toast says Cut.", pg.evaluate("document.getElementById('toast').textContent") == "Cut." and pg.evaluate("document.getElementById('toast').classList.contains('show')"))

        # 4: undo brings them back exactly; the clipboard keeps them; redo cuts again
        undo(pg)
        now_ = {s["id"]: s for s in strokes(pg, "p1")}
        check("undo: the two are back, unchanged", sorted(now_) == ["a", "b", "c"] and all(now_[k] == before[k] for k in before), sorted(now_))
        check("undo: the clipboard keeps them", pg.evaluate("window.__pw.ink.hasClip()") is True)
        redo(pg)
        check("redo: they come off again", ids(pg, "p1") == ["c"], ids(pg, "p1"))

        # 5: a finger hold on page 2 and Paste puts them there, centred on the hold, selected, one undo step
        tool(pg, "pen")
        go_page(pg, 2)
        hold(2, 400, 500); m = menu(); lift()
        check("a hold on the empty page 2: Paste is there and enabled", m["shown"] and {"label": "Paste", "disabled": False} in m["items"], m)
        u2 = U(pg)
        paste_btn().tap(); pg.wait_for_timeout(60)
        p2 = sorted(strokes(pg, "p2"), key=lambda r: r["seq"])
        orig = [before["a"], before["b"]]
        check("Paste on page 2: two strokes land there with fresh ids, centred on the hold",
              len(p2) == 2 and all(s["page_id"] == "p2" and s["id"] not in ("a", "b", "c") for s in p2) and near(ctr(pbox(p2)), (400, 500), 2),
              [len(p2), ctr(pbox(p2)) if p2 else None])
        if len(p2) == 2:
            dx, dy = p2[0]["data"]["points"][0][0] - orig[0]["data"]["points"][0][0], p2[0]["data"]["points"][0][1] - orig[0]["data"]["points"][0][1]
            check("Paste: they are the cut strokes, moved as one (same shape, style and order)",
                  all(len(o["data"]["points"]) == len(n["data"]["points"]) and o["style"] == n["style"] and o["kind"] == n["kind"]
                      and all(abs(q[0] - (p_[0] + dx)) < 0.11 and abs(q[1] - (p_[1] + dy)) < 0.11 for p_, q in zip(o["data"]["points"], n["data"]["points"])) for o, n in zip(orig, p2)))
        check("Paste: one undo step, the pasted two selected", U(pg) == u2 + 1 and sel(pg) and sorted(sel(pg)["ids"]) == sorted(s["id"] for s in p2), [U(pg), u2, sel(pg)])
        check("page 1 still holds only the third stroke", ids(pg, "p1") == ["c"])

        # 6: Cut also carries over to another note
        back(pg); open_note(pg, "Other")
        hold(1, 300, 400); lift()
        paste_btn().tap(); pg.wait_for_timeout(60)
        check("Paste in another note: the two land there too", len(strokes(pg, "p3")) == 2, len(strokes(pg, "p3")))
        check("no page errors in the cut chip group", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ a phone (375 px wide): four chips inside the desk
        group[0] = "phone width (375 px)"
        ctx, pg, errs = fresh(b, w=375, h=812, has_touch=True, is_mobile=True)
        # the phone way in: the folder view, then the grid's card (a phone note view has no tray)
        pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^Cut$"))).first.tap(); pg.wait_for_timeout(150)
        pg.locator("#grid .card").filter(has=pg.locator(".name", has_text=re.compile("^Scissors$"))).first.tap()
        pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(150)
        check("the phone note view: no tray, the desk is the screen's width", not pg.locator("#tray").is_visible() and pg.locator("#desk").bounding_box()["width"] >= 374)
        pg.evaluate(PUT_JS, ["p1", [rec("m1", "p1", [[380, 500], [400, 520], [420, 505]], 1),      # small, mid page
                                    rec("r1", "p1", [[760, 300], [775, 320], [790, 310]], 2),      # small, at the right edge
                                    rec("l1", "p1", [[6, 700], [20, 720], [34, 705]], 3),          # small, at the left edge
                                    rec("w1", "p1", [[200, 900], [400, 905], [600, 900]], 4)]])    # wide
        # the phone's own way to a selection: a finger hold and Select all (here on page 2, one small stroke at its right edge)
        pg.evaluate(PUT_JS, ["p2", [rec("s1", "p2", [[765, 200], [778, 215], [790, 205]], 5)]])
        cdp = ctx.new_cdp_session(pg)
        def touch(kind, pts=()): cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y, "id": k} for k, (x, y) in enumerate(pts)]})
        pg.locator("#nextBtn").tap(); pg.wait_for_timeout(200)
        hx, hy = screen(pg, 2, 400, 400); touch("touchStart", [(hx, hy)]); pg.wait_for_timeout(600); touch("touchEnd"); pg.wait_for_timeout(60)
        pg.locator("#menu button").filter(has_text=re.compile("^Select all$")).tap(); pg.wait_for_timeout(60)
        c_ = chips(pg)
        check("phone, a hold and Select all on a small stroke at the right edge: selected, all four chips inside the desk",
              sel(pg) and sel(pg)["ids"] == ["s1"] and inside(c_), [sel(pg), c_])
        check("... the chips do not cover the turn ring", ring_free(pg, 2))
        pg.locator("#prevBtn").tap(); pg.wait_for_timeout(200)
        pg.evaluate("() => window.__pw.ink.setTool('select')")
        z = zoom(pg)
        for name, rid, a, b_ in [("a small selection mid page", "m1", (360, 480), (440, 540)),
                                 ("a small selection at the page's right edge", "r1", (740, 280), (793, 340)),
                                 ("a small selection at the page's left edge", "l1", (1, 680), (50, 740)),
                                 ("a wide selection", "w1", (180, 880), (620, 925))]:
            tap_page(pg, 1, 400, 1080)
            drag_page(pg, 1, a, b_)
            c_ = chips(pg)
            check(f"{name}: selected, all four chips inside the desk", sel(pg) and sel(pg)["ids"] == [rid] and inside(c_), [sel(pg), c_, z])
            check(f"{name}: the chips do not cover the turn ring", ring_free(pg, 1))
            w_ = pg.evaluate("() => [...document.querySelectorAll('.selChips .chip')].map(b => Math.round(b.getBoundingClientRect().width))")
            check(f"{name}: each chip keeps its 38 px on screen", w_ == [38, 38, 38, 38], w_)
        # the Cut chip works on the phone too
        tap_page(pg, 1, 400, 1080)
        drag_page(pg, 1, (740, 280), (793, 340))
        try: pg.locator(".selChips .chip[data-act='cut']").tap(timeout=3000)
        except Exception as e_: check("the Cut chip can be tapped at the right edge", False, str(e_)[:200])
        pg.wait_for_timeout(40)
        check("a tap on Cut at the right edge: the stroke is cut", "r1" not in ids(pg, "p1") and pg.evaluate("window.__pw.ink.hasClip()") is True, ids(pg, "p1"))
        check("no page errors in the phone group", not errs, errs)
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
