# PenWorks pw-v9c checks: sticky notes (her design 27 Oct, built 6 Nov; the look: _build/sticky/sticky-mock.png).
# Run: python tests/test_sticky.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one folder (Gr 7) and two notes into the localStorage twin: Note A (two portrait pages) and Note B (portrait,
# landscape, portrait), one stroke on every page. At 1280 x 800 (the tablet lying down): the + menu's Sticky and its four
# colours, a new sticky beside the page, its row (kind, anchor_id, sk_*, note_id), a pen stroke on it (page_id = the sticky,
# sticky px) that leaves the page's ink alone, undo and redo, a strip drag (moves, writes sk_x / sk_y, one undo step), a
# drag onto the other page (re-anchors) and back, the strip tap's menu (colours, Bring to front, Put in the Bin), the corner
# resize clamped at 113 and 454, the page list and prev / next blind to stickies, thumbSvg and pdfout.pageOps drawing the
# on-page sticky and not the margin one, Put in the Bin with its Undo and the Bin view after 8 s, the anchor page deleted
# (the sticky goes, undo brings both), Copy + Paste of the anchor page (a new sticky id with its stroke), the pan clamp
# reaching a far-margin sticky, a finger on the strip drags (zoom lock or not), a finger on the body pans, the twin's 0007
# checks. A note without stickies lays out exactly as before pw-v9c (numbers measured on 4aa943f). At 924 x 1480 (portrait):
# a new sticky hangs off the page's right edge. Dark mode keeps the four colours. Pictures: _build/sticky/shots/.
import sys, subprocess, time, pathlib, re, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8826
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "sticky" / "shots"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-01T08:00:00Z';
  const P = (id, note_id, position, orientation, background) => ({ id, note_id, position, orientation, background, bookmark: false,
    deleted_at: null, created_at: t, updated_at: t });
  const pages = [P('pA1', 'nA', 0, 'portrait', 'grid'), P('pA2', 'nA', 1, 'portrait', 'lined'),
                 P('pB1', 'nB', 0, 'portrait', 'grid'), P('pB2', 'nB', 1, 'landscape', 'grid'), P('pB3', 'nB', 2, 'portrait', 'lined')];
  const strokes = pages.map((p, i) => ({ id: 's' + p.id, page_id: p.id, seq: i + 1, kind: 'pen',
    style: { colour: '#2F4BB8', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[120, 220], [300, 330], [520, 260]] } }));
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Gr 7', colour: '#3A86D6', position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'nA', folder_id: 'f1', name: 'Note A', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-11-05T09:00:00Z' },
            { id: 'nB', folder_id: 'f1', name: 'Note B', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-11-04T09:00:00Z' }],
    pages, strokes }));
}"""

HELPERS = """async () => {
  window.__P = await import('./js/page.js');
  window.__O = await import('./js/pdfout.js');
  const T = window.__T = {};
  T.z = () => window.__P.view().z;
  T.sk = (id) => document.querySelector(`#stack .sticky[data-id="${id}"]`);
  T.skClient = (id, x, y) => { const r = T.sk(id).getBoundingClientRect(), z = T.z(); return [r.left + x * z, r.top + y * z]; };
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.ev = (type, id, kind, x, y) => document.getElementById('desk').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: kind,
    isPrimary: true, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0, buttons: type === 'pointerup' ? 0 : 1,
    clientX: x, clientY: y, screenX: x + 10, screenY: y + 80 }));
  // a path of client points; kind 'pen' or 'touch'
  T.path = (pts, kind = 'pen', pid = 31) => {
    T.ev('pointerdown', pid, kind, pts[0][0], pts[0][1]);
    for (const q of pts.slice(1)) T.ev('pointermove', pid, kind, q[0], q[1]);
    T.ev('pointerup', pid, kind, pts[pts.length - 1][0], pts[pts.length - 1][1]);
  };
  // a drag from sticky point (x, y) by (dx, dy) screen px, in n steps
  T.drag = (id, x, y, dx, dy, kind = 'pen', n = 6) => {
    const [cx, cy] = T.skClient(id, x, y), pts = [];
    for (let k = 0; k <= n; k++) pts.push([cx + dx * k / n, cy + dy * k / n]);
    T.path(pts, kind, kind === 'pen' ? 31 : 41);
  };
  T.row = (id) => { const p = window.__pw.S.pages.find((r) => r.id === id); return p ? JSON.parse(JSON.stringify(p)) : null; };
  T.sks = () => window.__pw.S.pages.filter((p) => p.kind === 'sticky').map((p) => p.id);
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  return 1;
}"""
TWIN = "() => JSON.parse(localStorage.getItem('penworks.local.v2'))"
TOAST = """() => { const t = document.getElementById('toast'); return { text: (t.firstChild && t.firstChild.nodeType === 3 ? t.firstChild.textContent : t.textContent),
  undo: !!t.querySelector('.toastAct'), shown: t.classList.contains('show') }; }"""
LAYOUT = """() => { const s = document.getElementById('stack'), v = window.__P.view();
  return { sheets: [...s.querySelectorAll('.sheet')].map((e) => [e.style.left, e.style.top, e.style.width, e.style.height]),
           w: s.style.width, h: s.style.height, x: v.x, y: v.y, z: v.z }; }"""
# measured on 4aa943f (pw-v9b, before any sticky code) with tests' seed Note B: portrait, landscape, portrait
BASE_SHEETS = [["164.5px", "0px", "794px", "1123px"], ["0px", "1147px", "1123px", "794px"], ["164.5px", "1965px", "794px", "1123px"]]
BASE = {(1280, 800): {"x": 50.5, "y": 24, "z": 1}, (924, 1480): {"x": -127.5, "y": 24, "z": 1}}

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def twin(pg): return pg.evaluate(TWIN)
def toast(pg): return pg.evaluate(TOAST)
def row(pg, id): return pg.evaluate("(id) => window.__T.row(id)", id)
def sks(pg): return pg.evaluate("window.__T.sks()")
def recs(pg, id): return pg.evaluate("(id) => window.__T.recs(id)", id)
def view(pg): return pg.evaluate("window.__P.view()")
def rect(pg, sel): return pg.evaluate("""(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
  return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; }""", sel)
def drag(pg, id, x, y, dx, dy, kind="pen"):
    pg.evaluate("([id, x, y, dx, dy, k]) => window.__T.drag(id, x, y, dx, dy, k)", [id, x, y, dx, dy, kind]); pg.wait_for_timeout(80)
def menu_items(pg): return [t_.strip() for t_ in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def menu_click(pg, label): pg.get_by_role("menuitem", name=label, exact=True).click(); pg.wait_for_timeout(80)
def open_note(pg, name):
    pg.evaluate("() => { const a = document.querySelector(\".frow[data-id='all']\"); if (a && !document.querySelector('#grid .card:not(.plus)')) a.click(); }"); pg.wait_for_timeout(60)
    pg.locator("#grid .card").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(250)
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(100)
def add_sticky(pg, colour):
    pg.click("#addPageBtn"); pg.wait_for_selector("#menu:not([hidden])"); menu_click(pg, "Sticky")
    pg.click(f"#menu .sw[data-colour='{colour}']"); pg.wait_for_timeout(120)
    return pg.evaluate("window.__P.stickyOrder().slice(-1)[0]")
def start(b, w, h, theme=None):
    ctx = b.new_context(viewport={"width": w, "height": h}, has_touch=True)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg); pg.evaluate(SEED)
    if theme: pg.evaluate("(t) => localStorage.setItem('penworks.theme', t)", theme)
    pg.reload(); ready(pg); pg.wait_for_timeout(200); pg.evaluate(HELPERS)
    return ctx, pg, errs
def rg(hexc):
    v = int(hexc[1:], 16); ch = lambda x: str(round(x / 255 * 1000) / 1000).rstrip("0").rstrip(".") if x not in (0, 255) else ("0" if x == 0 else "1")
    return f"{ch((v >> 16) & 255)} {ch((v >> 8) & 255)} {ch(v & 255)} rg"

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------ a note with no sticky lays out as before
        group[0] = "layout as before"
        for vp in [(1280, 800), (924, 1480)]:
            ctx, pg, errs = start(b, *vp)
            open_note(pg, "Note B"); L = pg.evaluate(LAYOUT)
            check(f"{vp[0]}x{vp[1]}: the sheets' lefts, tops and sizes as on 4aa943f", L["sheets"] == BASE_SHEETS, L["sheets"])
            check(f"{vp[0]}x{vp[1]}: the stack's size as on 4aa943f (1123 x 3178)", L["w"] == "1123px" and L["h"] == "3178px", [L["w"], L["h"]])
            check(f"{vp[0]}x{vp[1]}: the view (x, y, zoom) as on 4aa943f", {k: L[k] for k in ("x", "y", "z")} == BASE[vp], L)
            check(f"{vp[0]}x{vp[1]}: no sticky element, no page errors", pg.locator("#stack .sticky").count() == 0 and not errs, errs)
            ctx.close()

        # ------------------------------------------------------------ the tablet lying down
        group[0] = "tablet 1280x800"
        ctx, pg, errs = start(b, 1280, 800)
        open_note(pg, "Note A")
        pg.click("#addPageBtn"); pg.wait_for_selector("#menu:not([hidden])")
        check("the + menu: Page, PDF, Image, Sticky", menu_items(pg) == ["Page", "PDF", "Image", "Sticky"], menu_items(pg))
        pg.screenshot(path=str(SHOTS / "menu.png"))
        menu_click(pg, "Sticky")
        sw = pg.evaluate("""() => ({ hd: [...document.querySelectorAll('#menu .hd')].map((e) => e.textContent),
          sw: [...document.querySelectorAll('#menu .sw')].map((e) => [e.dataset.colour, getComputedStyle(e).backgroundColor]) })""")
        check("Sticky opens a second menu: the head 'Sticky' and her four colours in order",
              sw["hd"] == ["Sticky"] and sw["sw"] == [["yellow", "rgb(255, 232, 130)"], ["blue", "rgb(191, 221, 246)"],
                                                      ["green", "rgb(198, 235, 188)"], ["purple", "rgb(223, 205, 243)"]], sw)
        pg.click("#menu .sw[data-colour='yellow']"); pg.wait_for_timeout(150)
        A = pg.evaluate("window.__P.stickyOrder()[0]")
        r = row(pg, A)
        check("a new sticky: a yellow div.sticky in #stack after the sheets", pg.evaluate("""(id) => { const s = window.__T.sk(id), all = [...document.getElementById('stack').children];
          return s.classList.contains('yellow') && all.indexOf(s) > Math.max(...[...document.querySelectorAll('#stack .sheet')].map((e) => all.indexOf(e)))
            && !!s.querySelector('.strip > i') && !!s.querySelector('svg.ink') && !!s.querySelector('.corner'); }""", A))
        check("its row: kind sticky, anchored to the current page pA1, note nA, 227 square, yellow",
              r and r["kind"] == "sticky" and r["anchor_id"] == "pA1" and r["note_id"] == "nA" and r["sk_w"] == 227 and r["sk_colour"] == "yellow", r)
        check("it lands beside the page: sk_x = page width + 24 = 818, sk_y = 24 below the top she sees", r["sk_x"] == 818 and r["sk_y"] == 24, [r["sk_x"], r["sk_y"]])
        sr, pr, dr = rect(pg, f"#stack .sticky[data-id='{A}']"), rect(pg, "#stack .sheet[data-id='pA1']"), rect(pg, "#desk")
        check("on screen: right of the page and wholly on the desk (she SEES it land)", sr["l"] > pr["r"] and sr["r"] <= dr["r"] and sr["t"] >= dr["t"], [sr, pr, dr])
        check("the sticky's square is 227 px at zoom 1, its strip 30 px tall",
              abs(sr["w"] - 227 * view(pg)["z"]) < 0.6 and abs(rect(pg, f"#stack .sticky[data-id='{A}'] .strip")["h"] - 30 * view(pg)["z"]) < 0.6, sr)
        idle(pg); tw = next((p for p in twin(pg)["pages"] if p["id"] == A), None)
        check("the twin holds the row with the same columns", tw and tw["kind"] == "sticky" and tw["anchor_id"] == "pA1" and tw["sk_x"] == 818
              and tw["sk_y"] == 24 and tw["sk_w"] == 227 and tw["sk_colour"] == "yellow" and tw["note_id"] == "nA", tw)
        pg.screenshot(path=str(SHOTS / "tablet.png"))

        # the pen on its body: ink on the sticky's own layer, sticky px
        page_before = recs(pg, "pA1")
        pg.evaluate("""(id) => { const T = window.__T; T.path([[40, 60], [80, 90], [150, 120]].map((p) => T.skClient(id, p[0], p[1]))); }""", A)
        pg.wait_for_timeout(100)
        sr_ = recs(pg, A)
        check("a pen stroke on the body lands on the sticky (page_id = the sticky id)", len(sr_) == 1 and sr_[0]["page_id"] == A, sr_)
        p0 = sr_[0]["data"]["points"][0] if sr_ else [0, 0]
        check("its points are sticky px from the sticky's top-left", abs(p0[0] - 40) < 1 and abs(p0[1] - 60) < 1, p0)
        check("the page's own ink is untouched", recs(pg, "pA1") == page_before, len(recs(pg, "pA1")))
        idle(pg)
        check("the twin's strokes hold it under the sticky's id", any(s["page_id"] == A for s in twin(pg)["strokes"]))
        pg.evaluate("document.getElementById('undoBtn').click()"); pg.wait_for_timeout(80); u = len(recs(pg, A))
        pg.evaluate("document.getElementById('redoBtn').click()"); pg.wait_for_timeout(80)
        check("undo takes the stroke off the sticky, redo puts it back", u == 0 and len(recs(pg, A)) == 1, [u, len(recs(pg, A))])

        # a strip drag: moves, written on the lift, one undo step
        drag(pg, A, 100, 15, -300, 100)
        r = row(pg, A)
        check("a strip drag moves it: sk_x 818 - 300 = 518, sk_y 24 + 100 = 124, same anchor", r["sk_x"] == 518 and r["sk_y"] == 124 and r["anchor_id"] == "pA1", r)
        check("after the lift no transform is left on it", pg.evaluate("(id) => window.__T.sk(id).style.transform", A) == "")
        idle(pg); tw = next(p for p in twin(pg)["pages"] if p["id"] == A)
        check("the twin's sk_x, sk_y follow", tw["sk_x"] == 518 and tw["sk_y"] == 124, tw)
        pg.evaluate("document.getElementById('undoBtn').click()"); pg.wait_for_timeout(80); u = row(pg, A)
        pg.evaluate("document.getElementById('redoBtn').click()"); pg.wait_for_timeout(80)
        check("undo puts it back beside the page, redo onto the page again", u["sk_x"] == 818 and u["sk_y"] == 24 and row(pg, A)["sk_x"] == 518, [u["sk_x"], row(pg, A)["sk_x"]])
        # a second stroke while it lies over the page: still the sticky's
        pg.evaluate("""(id) => { const T = window.__T; T.path([[60, 150], [120, 170], [180, 160]].map((p) => T.skClient(id, p[0], p[1]))); }""", A)
        pg.wait_for_timeout(80)
        check("a stroke on the sticky OVER the page: the sticky's, the page's ink untouched", len(recs(pg, A)) == 2 and recs(pg, "pA1") == page_before)

        # re-anchor: dragged with its centre over page 2, then back over page 1
        drag(pg, A, 100, 15, 0, 1323 * view(pg)["z"])
        r = row(pg, A)
        check("dragged onto page 2: anchor pA2, sk_y measured from pA2's top (124 + 1323 - 1147 = 300)", r["anchor_id"] == "pA2" and r["sk_x"] == 518 and r["sk_y"] == 300, r)
        check("its element says so (data-anchor)", pg.evaluate("(id) => window.__T.sk(id).dataset.anchor", A) == "pA2")
        drag(pg, A, 100, 15, 0, -1323 * view(pg)["z"])
        r = row(pg, A)
        check("dragged back: anchor pA1 at 518, 124", r["anchor_id"] == "pA1" and r["sk_x"] == 518 and r["sk_y"] == 124, r)
        drag(pg, A, 100, 15, 0, 100000)
        r2 = row(pg, A)
        drag(pg, A, 100, 15, 0, -100000)
        check("dropped over no page: the anchor stays", r2["anchor_id"] == "pA1" and r2["sk_y"] == 124 + 100000, r2)

        # the strip tap: the sticky menu
        drag(pg, A, 100, 15, 2, 1)
        check("a tap on the strip (under 8 px) opens the menu, the sticky stays where it was",
              pg.locator("#menu").is_visible() and row(pg, A)["sk_x"] == 518, row(pg, A))
        m = pg.evaluate("""() => ({ hd: [...document.querySelectorAll('#menu .hd')].map((e) => e.textContent),
          sw: [...document.querySelectorAll('#menu .sw')].map((e) => [e.dataset.colour, e.classList.contains('on')]),
          items: [...document.querySelectorAll('#menu button[role=menuitem]')].map((e) => [e.textContent, getComputedStyle(e).color]) })""")
        check("the menu: 'Sticky', the four swatches with yellow on, Bring to front, Put in the Bin (red, last)",
              m["hd"] == ["Sticky"] and m["sw"] == [["yellow", True], ["blue", False], ["green", False], ["purple", False]]
              and [i[0] for i in m["items"]] == ["Bring to front", "Put in the Bin"] and m["items"][1][1] == "rgb(198, 40, 40)", m)
        pg.screenshot(path=str(SHOTS / "colours.png"))
        pg.click("#menu .sw[data-colour='green']"); pg.wait_for_timeout(80)
        idle(pg)
        check("a colour pick: the class flips to green, the row and the twin say green",
              pg.evaluate("(id) => window.__T.sk(id).className", A) == "sticky green" and row(pg, A)["sk_colour"] == "green"
              and next(p for p in twin(pg)["pages"] if p["id"] == A)["sk_colour"] == "green")

        # the corner: resize, clamped, the writing stays where it is
        w0 = row(pg, A)["sk_w"]
        drag(pg, A, w0 - 13, w0 - 13, 60, 60)
        check("a corner drag of 60 screen px grows it 60 page px (zoom 1), top-left fixed",
              abs(row(pg, A)["sk_w"] - (w0 + 60 / view(pg)["z"])) < 0.2 and row(pg, A)["sk_x"] == 518, row(pg, A))
        w1 = row(pg, A)["sk_w"]
        drag(pg, A, w1 - 13, w1 - 13, 2000, 2000)
        check("grown past 12 cm it stops at 454", row(pg, A)["sk_w"] == 454, row(pg, A)["sk_w"])
        check("the ink layer's room follows (viewBox 0 0 454 454), the strokes keep their points",
              pg.evaluate("(id) => window.__T.sk(id).querySelector('svg.ink').getAttribute('viewBox')", A) == "0 0 454 454"
              and recs(pg, A)[0]["data"]["points"][0] == p0)
        drag(pg, A, 454 - 13, 454 - 13, -3000, -3000)
        check("shrunk past 3 cm it stops at 113", row(pg, A)["sk_w"] == 113, row(pg, A)["sk_w"])
        drag(pg, A, 113 - 13, 113 - 13, 114 * view(pg)["z"], 114 * view(pg)["z"])
        check("back to 227", abs(row(pg, A)["sk_w"] - 227) < 0.2, row(pg, A)["sk_w"])
        idle(pg)
        check("the twin's sk_w follows", abs(next(p for p in twin(pg)["pages"] if p["id"] == A)["sk_w"] - 227) < 0.2)

        # a second sticky (blue, in the margin) and Bring to front
        Bk = add_sticky(pg, "blue")
        check("a second sticky lands on top (last in the order)", pg.evaluate("window.__P.stickyOrder()") == [A, Bk])
        pg.evaluate("(id) => window.__pw.sticky.menu(id)", A); pg.wait_for_timeout(60)
        menu_click(pg, "Bring to front")
        check("Bring to front: A last in the order and in the DOM",
              pg.evaluate("window.__P.stickyOrder()") == [Bk, A] and pg.evaluate("document.getElementById('stack').lastElementChild.dataset.id") == A)
        pg.evaluate("(id) => { const T = window.__T; const c = T.skClient(id, 60, 12); T.path([c, [c[0] + 1, c[1]]]); }", Bk)
        pg.wait_for_timeout(60); pg.keyboard.press("Escape")
        check("a press on B's strip brings B to the top", pg.evaluate("window.__P.stickyOrder()") == [A, Bk])

        # the pictures: the on-page sticky is in, the margin one is not
        th = pg.evaluate("""() => { const p = window.__pw.S.pages.find((r) => r.id === 'pA1'), svg = window.__pw.ink.thumbSvg('pA1', p);
          return [...svg.querySelectorAll('g.sticky')].map((g) => [g.dataset.id, g.querySelector('rect.skPaper').getAttribute('fill'),
            g.querySelectorAll('path').length]); }""")
        check("thumbSvg of pA1: the on-page sticky A (its colour, its two strokes) and NOT the margin sticky B",
              th == [[A, "#C6EBBC", 2]], th)
        check("on-page = the square overlaps the page (A yes, B no)", pg.evaluate("([a, b]) => { const S = window.__pw.sticky, P = window.__pw.S.pages; const f = (id) => S.onPage(P.find((r) => r.id === id)); return [f(a), f(b)]; }", [A, Bk]) == [True, False])
        ops = pg.evaluate("""() => { const O = window.__O, p = window.__pw.S.pages.find((r) => r.id === 'pA1');
          return O.pageOps({ w: 794, h: 1123 }, 'grid', window.__pw.ink.strokesOf('pA1'), 0.75, 842, () => '/GS1', () => null, O.stickiesFor(p)); }""")
        check("pdfout.pageOps: A's green fill and its strip's, clipped to the page", rg("#C6EBBC") in ops and rg("#A3D996") in ops and "re W n" in ops, ops[-400:])
        check("pdfout.pageOps: nothing of the margin sticky B (no blue)", rg("#BFDDF6") not in ops and rg("#9CC7EC") not in ops)
        made = pg.evaluate("""async () => { const p = window.__pw.S.pages.find((r) => r.id === 'pA1');
          try { const blob = await window.__O.buildPdf([p], 'Sticky test'); const t = new TextDecoder('latin1').decode(new Uint8Array(await blob.arrayBuffer()));
            return [blob.size, t.startsWith('%PDF')]; } catch (e) { return String(e); } }""")
        check("Share as PDF (buildPdf) of the page with an on-page sticky makes a PDF", isinstance(made, list) and made[0] > 500 and made[1], made)

        # the page list, prev / next and the counts know nothing of stickies
        check("the counter says 1 / 2", pg.evaluate("document.getElementById('counter').textContent") == "1 / 2", pg.evaluate("document.getElementById('counter').textContent"))
        pg.click("#listBtn"); pg.wait_for_timeout(150)
        check("the page list shows two pages, no sticky", pg.locator("#plThumbs .thumbP").count() == 2 and pg.locator("#plThumbs div.sticky").count() == 0)
        check("page 1's thumb shows A on it", pg.locator("#plThumbs .thumbP[data-index='1'] g.sticky").count() == 1)
        pg.screenshot(path=str(SHOTS / "tablet-list.png"))
        pg.click("#plClose"); pg.wait_for_timeout(80)
        pg.evaluate("document.getElementById('nextBtn').click()"); pg.wait_for_timeout(120)
        check("next: page 2 of 2, next is off (no third page)", pg.evaluate("document.getElementById('counter').textContent") == "2 / 2" and pg.locator("#nextBtn").is_disabled())
        pg.evaluate("document.getElementById('prevBtn').click()"); pg.wait_for_timeout(120)
        check("prev: page 1 of 2", pg.evaluate("document.getElementById('counter').textContent") == "1 / 2")
        check("the folder view's page count for Note A is still 2",
              pg.evaluate("document.querySelector('.nrow[data-id=nA] .pc').textContent") == "2")

        # Put in the Bin: toast with Undo; after 8 s the Bin view shows no sticky
        drag(pg, Bk, 60, 12, 1, 0); menu_click(pg, "Put in the Bin")
        t = toast(pg)
        check("Put in the Bin: B leaves the desk, its row is binned, the toast says so with Undo",
              pg.locator(f"#stack .sticky[data-id='{Bk}']").count() == 0 and row(pg, Bk)["deleted_at"] and t["text"] == "Sticky put in the Bin" and t["undo"], t)
        pg.click("#toast .toastAct"); pg.wait_for_timeout(100)
        check("Undo (within 8 s): B is back, not binned", pg.locator(f"#stack .sticky[data-id='{Bk}']").count() == 1 and not row(pg, Bk)["deleted_at"])
        drag(pg, Bk, 60, 12, 1, 0); menu_click(pg, "Put in the Bin")
        pg.wait_for_timeout(8600)
        check("after 8 s the toast and its Undo are gone", not toast(pg)["shown"])
        idle(pg)
        check("the twin's row stays binned", next(p for p in twin(pg)["pages"] if p["id"] == Bk)["deleted_at"])
        back(pg)
        pg.locator(".frow[data-id='bin']").click(); pg.wait_for_timeout(100)
        check("the Bin view shows no sticky (empty) and the Bin count is 0",
              pg.locator("#grid .binItem").count() == 0 and pg.locator(".frow.bin .count").inner_text() == "0", pg.locator("#grid").inner_text())
        open_note(pg, "Note A")
        check("the note opens with A only", pg.locator("#stack .sticky").count() == 1 and pg.locator(f"#stack .sticky[data-id='{A}']").count() == 1)

        # delete the anchor page: the sticky goes with it, undo brings both back
        pg.click("#listBtn"); pg.wait_for_timeout(150)
        pg.locator("#plThumbs .thumbP[data-index='1'] .more").click(); menu_click(pg, "Delete"); pg.wait_for_timeout(100)
        idle(pg); tw = twin(pg)
        check("Delete page 1: A leaves the desk and the tree", pg.locator("#stack .sticky").count() == 0 and row(pg, A) is None)
        check("the twin's cascade: A's row and strokes are gone (B's binned row too)",
              not any(p["id"] in (A, Bk, "pA1") for p in tw["pages"]) and not any(s["page_id"] == A for s in tw["strokes"]))
        pg.evaluate("document.getElementById('undoBtn').click()"); pg.wait_for_timeout(150); idle(pg); tw = twin(pg)
        check("undo: page 1 and A are back (same id, same place, green)", row(pg, "pA1") and row(pg, A) and row(pg, A)["anchor_id"] == "pA1"
              and row(pg, A)["sk_x"] == 518 and row(pg, A)["sk_colour"] == "green" and pg.locator(f"#stack .sticky[data-id='{A}']").count() == 1)
        check("the twin has A's row and its two strokes again", any(p["id"] == A for p in tw["pages"]) and sum(s["page_id"] == A for s in tw["strokes"]) == 2)

        # Copy + Paste the anchor page: a second sticky, new id, its strokes
        pg.locator("#plThumbs .thumbP[data-index='1'] .more").click(); menu_click(pg, "Copy")
        pg.locator("#plThumbs .thumbP[data-index='1'] .more").click(); menu_click(pg, "Paste"); pg.wait_for_timeout(150)
        new_page = pg.evaluate("window.__pw.sticky.pagesOf('nA')[1].id")
        cp = pg.evaluate("(pid) => window.__pw.sticky.stickiesOf(pid).map((s) => [s.id, s.sk_x, s.sk_y, s.sk_colour])", new_page)
        check("Paste: the pasted page carries a sticky with a NEW id, same place and colour", len(cp) == 1 and cp[0][0] != A and cp[0][1:] == [518, 124, "green"], cp)
        C = cp[0][0] if cp else ""
        check("its two strokes came with it, under the new id", len(recs(pg, C)) == 2 and all(r_["page_id"] == C for r_ in recs(pg, C)))
        check("the note has 3 pages, the counter knows only pages", pg.locator("#plThumbs .thumbP").count() == 3)
        idle(pg)
        check("the twin has the new sticky row and its strokes", any(p["id"] == C and p["anchor_id"] == new_page for p in twin(pg)["pages"])
              and sum(s["page_id"] == C for s in twin(pg)["strokes"]) == 2)
        pg.evaluate("document.getElementById('undoBtn').click()"); pg.wait_for_timeout(150)
        check("undo of the paste takes the page and its sticky away", row(pg, C) is None and pg.locator("#plThumbs .thumbP").count() == 2)
        pg.click("#plClose"); pg.wait_for_timeout(80)

        # the pan clamp: a far-margin sticky can be scrolled into view
        D = add_sticky(pg, "purple")
        drag(pg, D, 100, 15, 900, 0)
        check("D dragged far into the margin (over no page): anchor stays", row(pg, D)["anchor_id"] == "pA1" and row(pg, D)["sk_x"] == 818 + 900 / view(pg)["z"], row(pg, D))
        dr = rect(pg, "#desk")
        before = rect(pg, f"#stack .sticky[data-id='{D}']")
        pg.evaluate("""() => { const d = document.getElementById('desk'), b = d.getBoundingClientRect();
          d.dispatchEvent(new WheelEvent('wheel', { deltaY: 5000, shiftKey: true, clientX: b.left + 200, clientY: b.top + 200, bubbles: true, cancelable: true })); }""")
        pg.wait_for_timeout(150)
        after = rect(pg, f"#stack .sticky[data-id='{D}']")
        check("a sideways scroll brings it fully onto the desk (the clamp stops at its edge + 24)",
              before["r"] > dr["r"] and after["l"] >= dr["l"] and abs(after["r"] - (dr["r"] - 24)) < 1, [before, after, dr])
        pg.screenshot(path=str(SHOTS / "tablet-margin.png"))

        # fingers: the strip drags (zoom lock or not), the body pans
        pg.wait_for_timeout(700)
        v0 = view(pg); x0 = row(pg, D)["sk_x"]
        drag(pg, D, 100, 15, -150, 40, "touch")
        check("a finger on the strip drags the sticky, the stack does not pan",
              abs(row(pg, D)["sk_x"] - (x0 - 150 / v0["z"])) < 0.2 and view(pg)["x"] == v0["x"], [row(pg, D), view(pg), v0])
        x1 = row(pg, D)["sk_x"]; v1 = view(pg)
        drag(pg, D, 100, 150, 120, 0, "touch")
        check("a finger on the body pans as on a page; the sticky's row stays", row(pg, D)["sk_x"] == x1 and abs(view(pg)["x"] - (v1["x"] + 120)) < 1, [view(pg), v1])
        pg.click("#zoomLock"); pg.wait_for_timeout(60)
        drag(pg, D, 100, 15, -60, 0, "touch")
        check("zoom locked: a finger on the strip still drags it", abs(row(pg, D)["sk_x"] - (x1 - 60 / v1["z"])) < 0.2, row(pg, D))
        pg.click("#zoomLock"); pg.wait_for_timeout(60)

        # the twin's 0007 checks
        refused = pg.evaluate("""async () => { const api = window.__pw.api, out = {};
          const tryIns = async (k, r) => { try { await api.insert('pages', r); out[k] = 'ok'; } catch (e) { out[k] = (e.code || '') + ' ' + e.message; } };
          const base = { note_id: 'nA', position: 0, kind: 'sticky', anchor_id: 'pA1', sk_x: 0, sk_y: 0, sk_w: 227, sk_colour: 'yellow' };
          await tryIns('big', { ...base, id: crypto.randomUUID(), sk_w: 500 });
          await tryIns('colour', { ...base, id: crypto.randomUUID(), sk_colour: 'red' });
          await tryIns('kind', { ...base, id: crypto.randomUUID(), kind: 'note' });
          await tryIns('pagex', { note_id: 'nA', position: 9, id: crypto.randomUUID(), sk_x: 3 });
          await tryIns('anchor', { ...base, id: crypto.randomUUID(), anchor_id: crypto.randomUUID() });
          try { await api.setSticky('pA2', { sk_w: 200 }); out.upd = 'ok'; } catch (e) { out.upd = (e.code || '') + ' ' + e.message; }
          return out; }""")
        check("the twin refuses a 500 px sticky and a red one (pages_sticky_check)", "pages_sticky_check" in refused["big"] and "pages_sticky_check" in refused["colour"], refused)
        check("the twin refuses kind 'note' (pages_kind_check) and a page with sk_x (pages_sticky_check)",
              "pages_kind_check" in refused["kind"] and "pages_sticky_check" in refused["pagex"], refused)
        check("the twin refuses an anchor that is not a page (23503) and a page patched into a sticky size",
              refused["anchor"].startswith("23503") and "pages_sticky_check" in refused["upd"], refused)
        check("no page errors (tablet)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ the tablet upright
        group[0] = "portrait 924x1480"
        ctx, pg, errs = start(b, 924, 1480)
        open_note(pg, "Note A")
        E = add_sticky(pg, "yellow")
        r = row(pg, E)
        check("no room on the right on screen: its left third on the page (sk_x = 794 - 227/3 = 718.3)", r["sk_x"] == 718.3 and r["sk_y"] == 24, r)
        sr, pr, dr = rect(pg, f"#stack .sticky[data-id='{E}']"), rect(pg, "#stack .sheet[data-id='pA1']"), rect(pg, "#desk")
        check("on screen it hangs off the page's right edge and past the desk's", sr["l"] < pr["r"] < sr["r"] and sr["r"] > dr["r"], [sr, pr, dr])
        pg.screenshot(path=str(SHOTS / "portrait.png"))
        pg.evaluate("""() => { const d = document.getElementById('desk'), b = d.getBoundingClientRect();
          d.dispatchEvent(new WheelEvent('wheel', { deltaY: 3000, shiftKey: true, clientX: b.left + 200, clientY: b.top + 200, bubbles: true, cancelable: true })); }""")
        pg.wait_for_timeout(150); sr = rect(pg, f"#stack .sticky[data-id='{E}']")
        check("a sideways scroll reaches all of it", sr["r"] <= dr["r"] - 23, [sr, dr])
        check("it is on the page (overlaps): pA1's thumbSvg draws it", pg.evaluate("""() => window.__pw.ink.thumbSvg('pA1', window.__pw.S.pages.find((r) => r.id === 'pA1')).querySelectorAll('g.sticky').length""") == 1)
        check("no page errors (portrait)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ dark mode keeps the four colours
        group[0] = "dark"
        ctx, pg, errs = start(b, 1280, 800, theme="dark")
        open_note(pg, "Note A")
        for c in ["yellow", "blue", "green", "purple"]: pg.evaluate("(c) => window.__pw.sticky.add(c)", c); pg.wait_for_timeout(60)
        ids = pg.evaluate("window.__P.stickyOrder()")
        for k, i in reversed(list(enumerate(ids))): drag(pg, i, 100, 15, -260 * (k % 2) - 20, 250 * (k // 2) + 10 * k)
        cols = pg.evaluate("""() => [...document.querySelectorAll('#stack .sticky')].map((s) => [s.classList[1], getComputedStyle(s).backgroundColor,
          getComputedStyle(s.querySelector('.strip')).backgroundColor])""")
        want = {"yellow": ["rgb(255, 232, 130)", "rgb(240, 213, 90)"], "blue": ["rgb(191, 221, 246)", "rgb(156, 199, 236)"],
                "green": ["rgb(198, 235, 188)", "rgb(163, 217, 150)"], "purple": ["rgb(223, 205, 243)", "rgb(199, 172, 231)"]}
        check("dark mode: html[data-theme=dark]", pg.evaluate("document.documentElement.dataset.theme") == "dark")
        check("dark mode: the four stickies keep their colours and strips", len(cols) == 4 and all(want[c[0]] == c[1:] for c in cols), cols)
        drag(pg, ids[0], 100, 15, 1, 0)
        check("dark mode: the sticky menu's Bin word stays readable red", pg.evaluate("getComputedStyle([...document.querySelectorAll('#menu button.red')][0]).color") == "rgb(255, 138, 128)")
        pg.screenshot(path=str(SHOTS / "dark.png"))
        check("no page errors (dark)", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:500]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
