# PenWorks pw-v7c checks: the pen tray on the RIGHT or the LEFT (her switch, 29 Oct, the big tablet).
# Run: python tests/test_trayside.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin. At the tablet landscape size (1280 x 800) and at
# 800 x 1280 portrait: the default (tray right-most), the footer's #trayBtn and the note menu's "Tray to the left / right"
# flip it (body.trayLeft, localStorage pw.traySide, the toast, kept over a reload), the chips mirror, a mouse stroke lands
# under the pointer on both sides (after a reload and after a flip without one), the pen panel opens on the tray's desk
# side, the zoom, the place and the lock survive a flip. At phone width (390 x 844): no tray and one column, either side.
# Screenshots of both sides (landscape, the pen panel open) go to _build/shots-trayside/.
import sys, subprocess, time, pathlib, re, math
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8794
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-trayside"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-10-29T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Tray', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
GEO = """() => {
  const r = (id) => { const e = document.getElementById(id); if (!e) return null; const b = e.getBoundingClientRect();
    return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; };
  const tr = getComputedStyle(document.getElementById('tray'));
  return { left: document.body.classList.contains('trayLeft'), tray: r('tray'), desk: r('desk'), body: r('noteBody'),
           lock: r('zoomLock'), exit: r('exitFs'), counter: r('counter'), panel: r('toolPanel'), picker: r('specPicker'),
           trayShown: tr.display !== 'none', bl: tr.borderLeftWidth, br: tr.borderRightWidth,
           cols: getComputedStyle(document.getElementById('app')).gridTemplateColumns.trim().split(/\\s+/).length,
           domAfter: document.getElementById('main').nextElementSibling.id,
           side: (() => { try { return localStorage.getItem('pw.traySide'); } catch (_) { return 'ERR'; } })(),
           toast: document.getElementById('toast').textContent, btn: document.getElementById('trayBtn').getAttribute('aria-label'),
           btnTitle: document.getElementById('trayBtn').title, panelOpen: !document.getElementById('toolPanel').hidden };
}"""
VIEW = """() => import('./js/page.js').then((m) => ({ ...m.view(), lock: m.locked() }))"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def geo(pg): return pg.evaluate(GEO)
def vw(pg): return pg.evaluate(VIEW)
def menu_items(pg): return [t.strip() for t in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(200)
def back(pg):
    pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
def note_menu(pg):
    pg.click("#noteMore"); pg.wait_for_selector("#menu:not([hidden])"); return menu_items(pg)
def menu_flip(pg, js=False):
    """the note menu's tray item; js=True opens and taps it by element.click() (no pointerdown), so an open panel is
    closed by the flip itself and not by the outside press"""
    if js:
        pg.evaluate("document.getElementById('noteMore').click()"); pg.wait_for_selector("#menu:not([hidden])")
        pg.evaluate("""() => [...document.querySelectorAll('#menu button[role="menuitem"]')].find((b) => /^Tray to the /.test(b.textContent.trim())).click()""")
    else:
        note_menu(pg)
        pg.locator("#menu button[role='menuitem']", has_text=re.compile(r"^Tray to the ")).first.click()
    pg.wait_for_timeout(150)
def tray_left_of_desk(g): return g["tray"]["r"] <= g["desk"]["l"] + 1 and g["tray"]["l"] <= 1
def tray_right_of_desk(g): return g["tray"]["l"] > g["desk"]["r"] - 1
def mid_x(g): return g["body"]["l"] + g["body"]["w"] / 2
def cx(box): return (box["l"] + box["r"]) / 2
def pen_panel(pg):
    """the pen tool chosen and its panel open (a second tap on the chosen pen opens it)"""
    pg.click("#tool-pen"); pg.wait_for_timeout(60)
    if pg.locator("#toolPanel").is_hidden(): pg.click("#tool-pen"); pg.wait_for_timeout(60)
    return geo(pg)
def close_panel(pg):
    pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
def stroke_lands(pg, x0, y0):
    """a mouse stroke from client (x0, y0); the new record's first point, mapped through the page's place and the zoom,
    against the pointer (the test_u2a screen() mapping, run backwards)"""
    pg.click("#tool-pen"); pg.wait_for_timeout(40); close_panel(pg)
    before = pg.evaluate("() => ['s0','s1','s2'].flatMap((id) => window.__pw.ink.strokesOf(id).map((r) => r.id))")
    pg.mouse.move(x0, y0); pg.mouse.down()
    for k in range(1, 7): pg.mouse.move(x0 + 20 * k, y0 + 6 * k, steps=3)
    pg.mouse.up(); pg.wait_for_timeout(80)
    got = pg.evaluate("""(before) => {
      const z = +document.getElementById('stack').dataset.zoom;
      for (const id of ['s0', 's1', 's2']) for (const r of window.__pw.ink.strokesOf(id)) {
        if (before.includes(r.id)) continue;
        const sh = document.querySelector(`#stack .sheet[data-id="${id}"]`).getBoundingClientRect(), p = r.data.points[0];
        return { page: id, x: sh.left + p[0] * z, y: sh.top + p[1] * z, n: r.data.points.length, z };
      }
      return null; }""", before)
    if not got: return False, None
    return math.hypot(got["x"] - x0, got["y"] - y0) <= 1.5, got

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)
        for W, H, tag in ((1280, 800, "landscape"), (800, 1280, "portrait")):
            group[0] = f"{tag} {W}x{H}"
            ctx = b.new_context(viewport={"width": W, "height": H})
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
            px, py = W * 0.5, H * 0.35                                   # a point on page 1 at both sizes

            # default: right
            open_note(pg); g = geo(pg)
            check("default: no body.trayLeft, no pw.traySide, the tray is the right-most column", not g["left"] and g["side"] is None and tray_right_of_desk(g), g)
            check("default: the tray's hairline on its left (1px), none on its right", g["bl"] == "1px" and g["br"] == "0px", [g["bl"], g["br"]])
            check("default: the padlock bottom-left, the counter bottom-right of the note", cx(g["lock"]) < mid_x(g) and cx(g["counter"]) > mid_x(g), g)
            pg.evaluate("document.getElementById('exitFs').hidden = false"); g = geo(pg)
            check("default: the full-screen exit top-right", cx(g["exit"]) > mid_x(g) and g["exit"]["t"] - g["body"]["t"] < 20, g["exit"])
            pg.evaluate("document.getElementById('exitFs').hidden = true")
            gp = pen_panel(pg)
            check("default: the pen panel opens to the LEFT of the tray", gp["panelOpen"] and gp["panel"]["r"] <= gp["tray"]["l"] + 0.5, [gp["panel"], gp["tray"]])
            if tag == "landscape": pg.screenshot(path=str(SHOTS / "right-pen-panel.png"))
            close_panel(pg)

            # the footer button flips it
            back(pg); g = geo(pg)
            check("the footer's tray button sits between the save dot and the dark-mode button, named for what a tap does",
                  pg.evaluate("[...document.querySelector('#side .foot .footR').children].map((e) => e.id).join()") == "saveDot,trayBtn,themeBtn"
                  and g["btn"] == "Move tray to the left" and g["btnTitle"] == "Move tray to the left", g["btn"])
            pg.click("#trayBtn"); pg.wait_for_timeout(120); g = geo(pg)
            check("a tap: body.trayLeft, pw.traySide 'left', the toast 'Tray on the left', the button now 'Move tray to the right'",
                  g["left"] and g["side"] == "left" and g["toast"] == "Tray on the left" and g["btn"] == "Move tray to the right", g)
            open_note(pg); g = geo(pg)
            check("left: the tray is the left-most column, the desk to its right", tray_left_of_desk(g), [g["tray"], g["desk"]])
            check("left: the DOM is unchanged (#tray still right after #main)", g["domAfter"] == "tray", g["domAfter"])
            check("left: the hairline moves to the tray's right (1px), none on its left", g["br"] == "1px" and g["bl"] == "0px", [g["bl"], g["br"]])

            # reload keeps it, and it never jumps sides
            pg.reload(); ready(pg); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250); g = geo(pg)
            check("a reload keeps it: the note reopens with the tray on the left", g["left"] and tray_left_of_desk(g) and g["side"] == "left", g["tray"])
            # the chips mirrored
            check("left: the padlock in the RIGHT half of the note, bottom", cx(g["lock"]) > mid_x(g) and g["body"]["b"] - g["lock"]["b"] < 20, g["lock"])
            check("left: the page counter in the LEFT half, bottom", cx(g["counter"]) < mid_x(g) and g["body"]["b"] - g["counter"]["b"] < 20, g["counter"])
            pg.evaluate("document.getElementById('exitFs').hidden = false"); g = geo(pg)
            check("left: the full-screen exit in the LEFT half, top", cx(g["exit"]) < mid_x(g) and g["exit"]["t"] - g["body"]["t"] < 20, g["exit"])
            hit = pg.evaluate("""() => ['zoomLock', 'exitFs'].every((id) => { const r = document.getElementById(id).getBoundingClientRect();
              return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2).closest('#' + id); })""")
            check("left: both chips are tappable where they sit", hit)
            pg.evaluate("document.getElementById('exitFs').hidden = true")

            # THE ONE THAT MATTERS: the stroke lands under the pointer
            ok, got = stroke_lands(pg, px, py)
            check("left (after a reload): a mouse stroke's first point lands within 1.5 px of the pointer", ok, [px, py, got])

            # the pen panel on the left side
            gp = pen_panel(pg)
            check("left: the pen panel opens to the RIGHT of the tray", gp["panelOpen"] and gp["panel"]["l"] >= gp["tray"]["r"] - 0.5, [gp["panel"], gp["tray"]])
            if tag == "landscape": pg.screenshot(path=str(SHOTS / "left-pen-panel.png"))

            # the note menu: the item names what a tap does, above Share note, Bin last; a flip closes the open panel
            close_panel(pg)
            items = note_menu(pg)
            check("the note menu reads 'Tray to the right', directly above 'Share note', 'Bin this note' last",
                  "Tray to the right" in items and items.index("Share note") == items.index("Tray to the right") + 1 and items[-1] == "Bin this note", items)
            pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
            pen_panel(pg)
            menu_flip(pg, js=True); g = geo(pg)
            check("the menu item flips it back: no trayLeft, pw.traySide 'right', the toast 'Tray on the right', the tray right-most",
                  not g["left"] and g["side"] == "right" and g["toast"] == "Tray on the right" and tray_right_of_desk(g), g)
            check("a flip closes the open pen panel", not g["panelOpen"], g["panelOpen"])
            items = note_menu(pg); pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
            check("and the item now reads 'Tray to the left' (still above 'Share note')",
                  "Tray to the left" in items and "Tray to the right" not in items and items.index("Share note") == items.index("Tray to the left") + 1, items)
            ok, got = stroke_lands(pg, px, py + 40)
            check("right (after a flip, no reload): the stroke lands within 1.5 px of the pointer", ok, [px, py + 40, got])
            menu_flip(pg); g = geo(pg)
            check("flipped to the left again from the menu, no reload", g["left"] and tray_left_of_desk(g) and g["side"] == "left", g["tray"])
            ok, got = stroke_lands(pg, px, py + 80)
            check("left (after a flip, no reload): the stroke lands within 1.5 px of the pointer", ok, [px, py + 80, got])

            # the zoom, the place and the lock survive a flip
            v0 = vw(pg)
            dy = -math.log(1.6 / v0["z"]) / 0.0025
            pg.evaluate("""(dy) => document.getElementById('desk').dispatchEvent(new WheelEvent('wheel',
              { deltaY: dy, ctrlKey: true, clientX: innerWidth / 2, clientY: innerHeight / 2, bubbles: true, cancelable: true }))""", dy)
            pg.wait_for_timeout(150); v1 = vw(pg)
            check("set-up: Ctrl + wheel zooms to 1.6", abs(v1["z"] - 1.6) < 0.01, [v0, v1])
            menu_flip(pg); v2 = vw(pg)
            check("a flip keeps the zoom (1.6) and the place exactly", v2["z"] == v1["z"] and abs(v2["x"] - v1["x"]) < 0.01 and abs(v2["y"] - v1["y"]) < 0.01, [v1, v2])
            pg.click("#zoomLock"); pg.wait_for_timeout(60); v3 = vw(pg)
            menu_flip(pg); v4 = vw(pg)
            check("locked, a flip leaves the lock on (aria-pressed true), the zoom and the place unchanged",
                  v3["lock"] and v4["lock"] and pg.get_attribute("#zoomLock", "aria-pressed") == "true" and v4["z"] == v3["z"]
                  and abs(v4["x"] - v3["x"]) < 0.01 and abs(v4["y"] - v3["y"]) < 0.01, [v3, v4])
            ok, got = stroke_lands(pg, px, py + 120)
            check("zoomed 1.6 and flipped: the stroke still lands within 1.5 px of the pointer", ok, [px, py + 120, got])
            check("no page errors", not errs, errs)
            ctx.close()

        # ?dbg=1 with the tray on the left: the readout boxes clear the mirrored chips
        group[0] = "dbg boxes, left"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL + "&dbg=1"); ready(pg); pg.evaluate(SEED); pg.evaluate("localStorage.setItem('pw.traySide', 'left')"); pg.reload(); ready(pg)
        open_note(pg); pg.wait_for_timeout(300)
        pg.evaluate("document.getElementById('exitFs').hidden = false")
        clash = pg.evaluate("""() => { const r = (id) => document.getElementById(id).getBoundingClientRect(), out = [];
          for (const a of ['dbg', 'dbgView', 'dbgCopy']) for (const c of ['zoomLock', 'counter', 'exitFs']) {
            const p = r(a), q = r(c);
            if (p.left < q.right && q.left < p.right && p.top < q.bottom && q.top < p.bottom) out.push(a + '/' + c); }
          return out; }""")
        check("the dbg boxes overlap none of the padlock, the counter and the exit chip", clash == [], clash)
        check("no page errors (dbg)", not errs, errs)
        ctx.close()

        # the phone: no tray, one column, either side
        group[0] = "phone 390x844"
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        for side in ("right", "left"):
            pg.evaluate("(s) => localStorage.setItem('pw.traySide', s)", side); pg.reload(); ready(pg)
            if pg.locator("#noteView").is_hidden():
                if pg.locator(".nrow").first.is_hidden(): pg.locator(".frow").first.click(); pg.wait_for_timeout(100)
                pg.locator(".card:not(.plus)").first.click() if pg.locator(".card:not(.plus)").count() else pg.locator(".nrow").first.click()
                pg.wait_for_selector("#noteView:not([hidden])")
            pg.wait_for_timeout(200); g = geo(pg)
            check(f"{side}: no tray, one column, the desk the full width", not g["trayShown"] and g["cols"] == 1 and abs(g["desk"]["w"] - 390) < 1
                  and g["left"] == (side == "left"), g)
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
