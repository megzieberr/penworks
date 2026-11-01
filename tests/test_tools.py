# PenWorks U5a checks (pw-v8a, tools round 1): the Tools button under the calculator, its little panel, and the sticky
# RULER on the paper (the constructions app's ruler, ported to the page; briefs/U5-TOOLS-DESIGN.md).
# Run: python tests/test_tools.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800 (the tablet landscape size). Pen gestures are
# PointerEvents (pointerType 'pen') fired on the desk, as page.js reads them; one move runs on the real mouse; fingers are
# touch PointerEvents on the desk (test_scroll.py's way). The PDF is read with PyMuPDF.
# What it proves: the button sits straight under the calculator on both tray sides; the panel opens and closes by the pen
# panel's rule and only Ruler is live; the ruler comes out on the current page in page px (the zoom scales it), never a
# record, never in a thumb or the PDF; body moves, knobs turn (a 46 degree turn lands on 45, U5c: within 1.2 degrees), the edge band draws ONE fixed
# line record in the current ink style (highlighter lines in their group), short drags land nothing, undo and redo; a
# finger pans and two fingers pinch even on the ruler; stick points (an end, a crossing) catch the edge, the line's start
# and a turn; Select moves a fixed line whole with no end handles, Copy and Paste keep fixed; it may hang off the page;
# closing the note puts it away. Screenshots go to _build/shots-tools/.
import sys, subprocess, time, pathlib, re, math, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8801
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-tools"
CM = 96 / 2.54

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-01T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Tools', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
HELP = """async () => {
  window.__P = await import('./js/page.js');
  window.__TL = await import('./js/tools.js');
  window.__I = await import('./js/ink.js');
  const T = window.__T = {};
  T.z = () => window.__P.view().z;
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.client = (id, x, y) => { const r = T.sheet(id).getBoundingClientRect(), z = T.z(); return [r.left + x * z, r.top + y * z]; };
  T.ev = (type, id, kind, x, y) => document.getElementById('desk').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: kind,
    isPrimary: true, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0, buttons: type === 'pointerup' ? 0 : 1, clientX: x, clientY: y }));
  T.R = () => window.__TL.rulerState();
  // a point on the ruler in its own frame (lx along edge A from its 0 mark, ly into the ruler), as page px
  T.local = (lx, ly) => { const s = T.R(), u = [Math.cos(s.ang), Math.sin(s.ang)], n = [-u[1], u[0]];
    return [s.o[0] + u[0] * lx + n[0] * ly, s.o[1] + u[1] * lx + n[1] * ly]; };
  // a pen path through page points of page `id` (client points when id is null); up = false leaves the pen down
  T.pen = (id, pts, up = true, pid = 31, kind = 'pen') => {
    const c = pts.map((p) => (id ? T.client(id, p[0], p[1]) : p));
    T.ev('pointerdown', pid, kind, c[0][0], c[0][1]);
    for (const q of c.slice(1)) T.ev('pointermove', pid, kind, q[0], q[1]);
    if (up) T.ev('pointerup', pid, kind, c[c.length - 1][0], c[c.length - 1][1]);
  };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.line = (id, x1, y1, x2, y2, extra = {}) => { const r = { id: crypto.randomUUID(), page_id: id, seq: Date.now() + Math.floor(Math.random() * 1000), kind: 'shape',
    style: { colour: '#FF0C84', width: 2.5, dash: 'solid', opacity: 1 }, data: { type: 'line', x1, y1, x2, y2, ...extra } };
    window.__pw.ink.put(id, [r]); return r.id; };
  T.clear = (id) => { const op = window.__pw.ink.erasePageOp(id); if (op) op.redo(); };
  T.box = (sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
    return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; };
  return 1;
}"""
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
  return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height, shown: !e.hidden && b.width > 0 }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def rect(pg, sel): return pg.evaluate(RECT, sel)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def menu_flip(pg):
    pg.click("#noteMore"); pg.wait_for_selector("#menu:not([hidden])")
    pg.locator("#menu button[role='menuitem']", has_text=re.compile(r"^Tray to the ")).first.click()
    pg.wait_for_timeout(200)
def R(pg): return pg.evaluate("window.__T.R()")
def z(pg): return pg.evaluate("window.__T.z()")
def recs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.recs(id)", pid)
def ids(pg, pid="s0"): return [r["id"] for r in recs(pg, pid)]
def local(pg, lx, ly): return pg.evaluate("([a, b]) => window.__T.local(a, b)", [lx, ly])
def pen(pg, pts, up=True, page="s0", kind="pen"): pg.evaluate("([id, p, up, k]) => window.__T.pen(id, p, up, 31, k)", [page, pts, up, kind])
def pen_up(pg, p, page="s0"):
    pg.evaluate("([id, p]) => { const c = window.__T.client(id, p[0], p[1]); window.__T.ev('pointerup', 31, 'pen', c[0], c[1]); }", [page, p])
def edge_perp(r, q, edge):
    """q's distance from ruler r's edge A (edge 'A') or edge B line, page px"""
    u = (math.cos(r["ang"]), math.sin(r["ang"])); n = (-u[1], u[0])
    v = (q[0] - r["o"][0], q[1] - r["o"][1]); y = v[0] * n[0] + v[1] * n[1]
    return abs(y - (0 if edge == "A" else r["w"]))
def along(r, q):
    u = (math.cos(r["ang"]), math.sin(r["ang"])); return (q[0] - r["o"][0]) * u[0] + (q[1] - r["o"][1]) * u[1]
def rotate(p, c, deg):
    a = math.radians(deg); dx, dy = p[0] - c[0], p[1] - c[1]
    return [c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a)]
def turn_path(c, k, deg, steps=None):
    steps = steps or max(2, int(abs(deg) / 2.5))
    return [rotate(k, c, deg * i / steps) for i in range(steps + 1)]
def knob(pg, side=1):
    r = R(pg); return local(pg, r["len"] + r["pad"] + r["knobOff"], r["w"] / 2) if side else local(pg, -r["pad"] - r["knobOff"], r["w"] / 2)
def toggle_ruler(pg):
    if pg.locator("#toolsPanel").is_hidden(): pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
    pg.click("#trow-ruler"); pg.wait_for_timeout(60)
def finger(pg, kind, pid, x, y):
    pg.evaluate("([t, i, x, y]) => window.__T.ev(t, i, 'touch', x, y)", [kind, pid, x, y])
def close_panel(pg): pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
def pressed(pg, sel): return pg.get_attribute(sel, "aria-pressed")
def show_ruler(pg):
    """scroll the stack (a plain wheel) so the ruler's middle sits in the middle of the desk: the real mouse and the
    screenshots need it on screen"""
    pg.evaluate("""() => { const s = window.__T.R(), c = window.__T.client(s.page, ...window.__T.local(s.len / 2, s.w / 2));
      const d = document.getElementById('desk'), b = d.getBoundingClientRect();
      d.dispatchEvent(new WheelEvent('wheel', { deltaY: c[1] - (b.top + b.height / 2), clientX: b.left + 200, clientY: b.top + 200, bubbles: true, cancelable: true })); }""")
    pg.wait_for_timeout(80)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        open_note(pg); pg.evaluate(HELP)

        # ------------------------------------------------------------ A: the button and its panel
        group[0] = "A. button + panel"
        kids = pg.evaluate("[...document.getElementById('tray').children].map((e) => e.id || e.className)")
        cb, tb, cl = rect(pg, "#toolsBtn"), rect(pg, "#drawToolsBtn"), rect(pg, "#tray .colours")
        check("#drawToolsBtn exists: class 'ib tool', aria-label and title 'Tools'",
              tb is not None and pg.get_attribute("#drawToolsBtn", "aria-label") == "Tools" and pg.get_attribute("#drawToolsBtn", "title") == "Tools"
              and {"ib", "tool"} <= set(pg.get_attribute("#drawToolsBtn", "class").split()), tb)
        check("tray order: calculator, Tools, then the colours", kids[:3] == ["toolsBtn", "drawToolsBtn", "colours"], kids)
        check("right tray: Tools sits directly below the calculator (2 px gap, same centre, same size)",
              abs(tb["t"] - cb["b"] - 2) < 0.6 and abs((tb["l"] + tb["r"]) / 2 - (cb["l"] + cb["r"]) / 2) < 0.6 and abs(tb["w"] - cb["w"]) < 0.6, [cb, tb])
        check("the 6 px breathing room is under the Tools button now: the pair is one block above the colours",
              abs(cl["t"] - tb["b"] - 8) < 0.6 and pg.evaluate("getComputedStyle(document.getElementById('drawToolsBtn')).marginBottom") == "6px"
              and pg.evaluate("getComputedStyle(document.getElementById('toolsBtn')).marginBottom") == "0px", [tb, cl])
        icon = pg.evaluate("""() => { const s = document.querySelector('#drawToolsBtn svg'); return s ? [s.getAttribute('stroke-width'), !!s.querySelector('rect'), !!s.querySelector('circle')] : null; }""")
        check("one icon in the house line style (1.8 stroke): a ruler (rect) and a compass (hinge circle)", icon == ["1.8", True, True], icon)
        check("not pressed while no tool is out; no panel shown yet", pressed(pg, "#drawToolsBtn") == "false" and pg.locator("#toolsPanel").is_hidden())
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(80)
        p, tray = rect(pg, "#toolsPanel"), rect(pg, "#tray")
        rows = pg.evaluate("[...document.querySelectorAll('#toolsPanel .trow')].map((b) => [b.textContent.trim(), b.disabled, b.title, b.getAttribute('aria-pressed')])")
        check("a tap opens the panel", p and p["shown"], p)
        check("the panel is role=group (not a dialog: overlayOpen must not see it), aria-label 'Tools'",
              pg.get_attribute("#toolsPanel", "role") == "group" and pg.get_attribute("#toolsPanel", "aria-label") == "Tools")
        check("four rows in order: Ruler, Compass, Protractor, Axes", [r[0] for r in rows] == ["Ruler", "Compass", "Protractor", "Axes"], rows)
        check("Ruler and Compass are live (U5b); Protractor and Axes are disabled, title 'Next round'; none pressed",
              rows[0][1] is False and rows[1][1] is False and all(r[1] is True and r[2] == "Next round" for r in rows[2:]) and all(r[3] == "false" for r in rows), rows)
        check("right tray: the panel sits on the desk side, 8 px left of the tray, level with its button",
              abs(p["r"] - (tray["l"] - 8)) < 1 and p["t"] <= tb["t"] + tb["h"] / 2 <= p["b"], [p, tray, tb])
        pg.click("#trow-protractor", force=True); pg.wait_for_timeout(50)
        pg.mouse.click(p["l"] + 6, p["t"] + 4); pg.wait_for_timeout(50)
        check("a tap inside it (a disabled row, its padding) keeps it open and brings nothing out",
              pg.locator("#toolsPanel").is_visible() and R(pg) is None)
        d = rect(pg, "#desk")
        finger(pg, "pointerdown", 61, d["l"] + 300, d["t"] + 300); finger(pg, "pointerup", 61, d["l"] + 300, d["t"] + 300); pg.wait_for_timeout(50)
        check("a tap on the desk closes it", pg.locator("#toolsPanel").is_hidden())
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(50); open1 = pg.locator("#toolsPanel").is_visible()
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(50)
        check("its own button toggles it (open, then closed)", open1 and pg.locator("#toolsPanel").is_hidden())
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(50); pg.click("#tool-pen"); pg.wait_for_timeout(50)
        check("a tap on another tray button closes it", pg.locator("#toolsPanel").is_hidden())
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(50); close_panel(pg)
        check("Escape closes it", pg.locator("#toolsPanel").is_hidden())
        menu_flip(pg)
        cb, tb, cl, tray = rect(pg, "#toolsBtn"), rect(pg, "#drawToolsBtn"), rect(pg, "#tray .colours"), rect(pg, "#tray")
        check("left tray: Tools still directly below the calculator, the room above the colours kept",
              pg.evaluate("document.body.classList.contains('trayLeft')") and tray["l"] <= 1
              and abs(tb["t"] - cb["b"] - 2) < 0.6 and abs(cl["t"] - tb["b"] - 8) < 0.6, [cb, tb, cl, tray])
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(80); p = rect(pg, "#toolsPanel")
        check("left tray: the panel mirrors, 8 px right of the tray", p["shown"] and abs(p["l"] - (tray["r"] + 8)) < 1, [p, tray])
        pg.screenshot(path=str(SHOTS / "panel-left.png"))
        close_panel(pg); menu_flip(pg)
        check("back on the right", not pg.evaluate("document.body.classList.contains('trayLeft')"))
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(80)
        pg.screenshot(path=str(SHOTS / "panel-right.png")); close_panel(pg)

        # ------------------------------------------------------------ B: the ruler comes out
        group[0] = "B. ruler out"
        pg.click('#tray .sw[data-colour="#0D0DFF"]'); pg.wait_for_timeout(40)   # the pen in Blue (not the default Black)
        cur = pg.evaluate("window.__P.current()")
        toggle_ruler(pg)
        r = R(pg)
        check("Ruler comes out on the current page (page 1), level", r is not None and cur == 0 and r["page"] == "s0" and r["ang"] == 0, [cur, r])
        check("the row shows pressed, the Tools button aria-pressed true, the panel stays open",
              pressed(pg, "#trow-ruler") == "true" and pressed(pg, "#drawToolsBtn") == "true" and pg.locator("#toolsPanel").is_visible())
        check("one fixed size: 20 cm long, 2.2 cm wide, in page px", abs(r["len"] - 20 * CM) < 1e-6 and abs(r["w"] - 2.2 * CM) < 1e-6, r)
        check("it lies across the lower third of the page, centred across it",
              2 / 3 * 1123 <= r["o"][1] + r["w"] / 2 <= 1123 and abs(r["o"][0] + r["len"] / 2 - 794 / 2) < 0.01, r)
        lay = pg.evaluate("""() => { const s = window.__T.sheet('s0'), l = s.querySelector(':scope > svg.toolLayer'), ink = s.querySelector(':scope > svg.ink');
          if (!l) return null; const t = [...l.querySelectorAll('text')].map((e) => e.textContent);
          return { inSheet: true, after: !!ink && !!(ink.compareDocumentPosition(l) & 4), overflow: getComputedStyle(l).overflow, z: getComputedStyle(l).zIndex,
                   pe: getComputedStyle(l).pointerEvents, view: l.getAttribute('viewBox'), knobs: l.querySelectorAll('circle.knob').length,
                   ticks: l.querySelectorAll('path.ticks').length, mm: (l.querySelector('path.ticks:not(.cm)').getAttribute('d').match(/M/g) || []).length,
                   cm: (l.querySelector('path.ticks.cm').getAttribute('d').match(/M/g) || []).length, nums: t }; }""")
        check("its layer is an svg on page 1's sheet, after (over) the ink layer, page px viewBox, no pointer events",
              lay and lay["after"] and lay["view"] == "0 0 794 1123" and lay["pe"] == "none", lay)
        check("the layer never clips (overflow visible) and sits above the next page (z-index 2)", lay and lay["overflow"] == "visible" and lay["z"] == "2", lay)
        check("mm and cm ticks on BOTH long edges (2 x 180 mm, 2 x 21 cm), cm numbers 0 to 20, two knobs, no length readout",
              lay and lay["mm"] == 360 and lay["cm"] == 42 and lay["knobs"] == 2 and lay["nums"] == [str(c) for c in range(21)] + ["cm"], lay)
        check("the ruler is not a record: strokesOf(page 1) is empty", recs(pg) == [])
        th = pg.evaluate("() => { const s = window.__pw.ink.thumbSvg('s0'); return [s.querySelectorAll('*').length, s.querySelectorAll('text, .ruler').length]; }")
        check("... and not in the page's thumb (thumbSvg holds only its two empty groups)", th == [2, 0], th)
        z1 = z(pg); w1 = rect(pg, "#stack svg.toolLayer rect.body")["w"]
        check("on screen the body is (20 cm + 2 pads) x zoom wide", abs(w1 - (r["len"] + 2 * r["pad"]) * z1) < 0.5, [w1, z1, r])
        pg.evaluate("""() => { const d = document.getElementById('desk'), b = d.getBoundingClientRect();
          d.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: -Math.log(2) / 0.0025, clientX: b.left + 400, clientY: b.top + 300, bubbles: true, cancelable: true })); }""")
        pg.wait_for_timeout(80); z2 = z(pg); w2 = rect(pg, "#stack svg.toolLayer rect.body")["w"]; r2 = R(pg)
        check("a zoom to 2x doubles its screen box, and its page px do not change (paper, ink and ruler scale together)",
              abs(z2 / z1 - 2) < 1e-6 and abs(w2 / w1 - 2) < 0.002 and r2["o"] == r["o"] and r2["ang"] == r["ang"], [z1, z2, w1, w2])
        pg.evaluate("""() => { const d = document.getElementById('desk'), b = d.getBoundingClientRect();
          d.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: Math.log(2) / 0.0025, clientX: b.left + 400, clientY: b.top + 300, bubbles: true, cancelable: true })); }""")
        pg.wait_for_timeout(80)
        check("zoomed back to 1x", abs(z(pg) - z1) < 1e-6, z(pg))
        pg.click("#trow-ruler"); pg.wait_for_timeout(50)
        check("the row again: the ruler goes away (no layer anywhere), row and button unpressed",
              R(pg) is None and pg.locator("#stack svg.toolLayer").count() == 0 and pressed(pg, "#trow-ruler") == "false" and pressed(pg, "#drawToolsBtn") == "false")
        pg.evaluate("window.__P.scrollToPage(1)"); pg.wait_for_timeout(80)
        pg.click("#trow-ruler"); pg.wait_for_timeout(50)
        check("brought out while page 2 is current, it lands on page 2", R(pg) and R(pg)["page"] == "s1"
              and pg.evaluate("!!window.__T.sheet('s1').querySelector(':scope > svg.toolLayer')"), R(pg))
        pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)
        check("scrolled back to page 1, it stays on page 2 (a real desk), the row still pressed",
              pg.evaluate("window.__P.current()") == 0 and R(pg)["page"] == "s1" and pressed(pg, "#trow-ruler") == "true")
        pg.click("#trow-ruler"); pg.wait_for_timeout(50); a1 = R(pg) is None
        pg.click("#trow-ruler"); pg.wait_for_timeout(50)
        check("tapping the row puts it away from there, tapping again brings it out on the current page 1", a1 and R(pg)["page"] == "s0", R(pg))
        close_panel(pg)

        # ------------------------------------------------------------ C: the pen moves and turns it
        group[0] = "C. move + turn"
        show_ruler(pg)
        r0 = R(pg); zz = z(pg)
        b0 = local(pg, 300, r0["w"] / 2)
        pen(pg, [b0, [b0[0] + 20 / zz, b0[1] - 10 / zz], [b0[0] + 60 / zz, b0[1] - 40 / zz]])
        r1 = R(pg)
        check("a pen drag on the body moves it by the drag (page px), still level, nothing stuck",
              abs(r1["o"][0] - r0["o"][0] - 60 / zz) < 1e-6 and abs(r1["o"][1] - r0["o"][1] + 40 / zz) < 1e-6 and r1["ang"] == 0 and r1["stuck"] is None, [r0, r1])
        check("... and the pen wrote nothing under the body", recs(pg) == [])
        c = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", local(pg, 400, r1["w"] / 2))
        pg.mouse.move(c[0], c[1]); pg.mouse.down(); pg.mouse.move(c[0] + 15, c[1] + 10, steps=3); pg.mouse.move(c[0] + 30, c[1] + 20, steps=3); pg.mouse.up()
        r2 = R(pg)
        check("the mouse (real pointer events) moves it too", abs(r2["o"][0] - r1["o"][0] - 30 / zz) < 1e-6 and abs(r2["o"][1] - r1["o"][1] - 20 / zz) < 1e-6 and recs(pg) == [], [r1, r2])
        ctr = local(pg, r2["len"] / 2, r2["w"] / 2); k1 = knob(pg, 1)
        pen(pg, turn_path(ctr, k1, -46), up=False)                  # U5c: the 45 degree click is 1.2 degrees wide
        mid = R(pg)
        deg = pg.evaluate("() => { const e = document.querySelector('#stack .sheet .toolDeg'); return e ? [e.textContent, e.classList.contains('on'), e.classList.contains('selDeg')] : null; }")
        pen_up(pg, turn_path(ctr, k1, -46)[-1])
        r3 = R(pg); ctr3 = local(pg, r3["len"] / 2, r3["w"] / 2)
        check("a pen drag on the right knob turns it: a 46 degree raw turn lands on 45", abs(r3["ang"] + math.pi / 4) < 1e-9, r3["ang"])
        check("... about its centre (unstuck: the centre stays put)", math.hypot(ctr3[0] - ctr[0], ctr3[1] - ctr[1]) < 1e-6, [ctr, ctr3])
        check("while turning, the selection's degree pill shows '45°'", mid["gesture"] == "turn" and deg == ["45°", True, True], deg)
        check("after the lift the pill is gone", not pg.evaluate("() => { const e = document.querySelector('#stack .toolDeg'); return !!e && e.classList.contains('on'); }"))
        k0 = knob(pg, 0)
        pen(pg, turn_path(ctr3, k0, 46))
        r4 = R(pg)
        check("the left knob turns it too: 46 degrees back from 45 lands on 0 (1 degree from the step)", abs(r4["ang"]) < 1e-9, r4["ang"])
        pen(pg, turn_path(ctr3, knob(pg, 1), 20))
        r5 = R(pg)
        check("a 20 degree turn stays at 20 (no step near it)", abs(math.degrees(r5["ang"]) - 20) < 0.05, math.degrees(r5["ang"]))
        pen(pg, turn_path(ctr3, knob(pg, 1), -20))
        check("and back to level", abs(R(pg)["ang"]) < 1e-9, R(pg)["ang"])
        check("no records from any of it", recs(pg) == [])

        # ------------------------------------------------------------ D: the pen draws along an edge
        group[0] = "D. drawing"
        r = R(pg); zz = z(pg)
        tr = pg.evaluate("window.__pw.tray()")
        s0 = local(pg, 100, -10 / zz); s1 = local(pg, 200, 4 / zz); s2 = local(pg, 300.4, 5 / zz)
        n_el = pg.evaluate("window.__T.sheet('s0').querySelectorAll('svg.ink g.pen > *').length")
        pen(pg, [s0, s1, s2], up=False)
        live = pg.evaluate("""() => { const l = [...window.__T.sheet('s0').querySelectorAll('svg.ink g.pen > line')]; const e = l[l.length - 1];
          return e ? [l.length, e.getAttribute('stroke'), e.getAttribute('stroke-width')] : null; }""")
        pen_up(pg, s2)
        rs = recs(pg)
        check("while drawing, a live preview line shows in the pen's colour and width", live and live[0] == 1 and live[1] == "#0D0DFF" and live[2] == "2.5", live)
        check("a pen drag in edge A's band lands exactly ONE record: kind 'shape', data.type 'line', data.fixed true",
              len(rs) == 1 and rs[0]["kind"] == "shape" and rs[0]["data"]["type"] == "line" and rs[0]["data"].get("fixed") is True, rs)
        L = rs[0]["data"] if rs else {}
        e1, e2 = [L.get("x1"), L.get("y1")], [L.get("x2"), L.get("y2")]
        check("both ends lie on the edge line (within 0.5 page px)", rs and edge_perp(r, e1, "A") < 0.5 and edge_perp(r, e2, "A") < 0.5, [edge_perp(r, e1, "A"), edge_perp(r, e2, "A")])
        check("it runs from where the pen landed to where it lifted, both projected onto the edge", rs and abs(along(r, e1) - 100) < 0.02 and abs(along(r, e2) - 300.4) < 0.02, [along(r, e1), along(r, e2)])
        check("colour and width of the current pen (Blue, 2.5), solid, opacity 1",
              rs and rs[0]["style"] == {"colour": tr["pen"]["colour"], "width": tr["pen"]["width"], "dash": "solid", "opacity": 1} and tr["pen"]["colour"] == "#0D0DFF", [rs and rs[0]["style"], tr["pen"]])
        n_el2 = pg.evaluate("window.__T.sheet('s0').querySelectorAll('svg.ink g.pen > *').length")
        check("one element on the page for it (the preview became the line)", n_el2 == n_el + 1, [n_el, n_el2])
        line_id = rs[0]["id"] if rs else None
        a = local(pg, 500, -6 / zz); bb = local(pg, 500 + 1 / zz, -6 / zz)
        pen(pg, [a, bb])
        check("a drag under 1.5 page px lands nothing (and leaves no preview behind)",
              ids(pg) == [line_id] and pg.evaluate("window.__T.sheet('s0').querySelectorAll('svg.ink g.pen > *').length") == n_el2)
        pg.click("#undoBtn"); pg.wait_for_timeout(50); after_undo = ids(pg)
        pg.click("#redoBtn"); pg.wait_for_timeout(50)
        check("undo takes the line away (one step), redo brings it back", after_undo == [] and ids(pg) == [line_id], [after_undo, ids(pg)])
        b1 = local(pg, 50, r["w"] + 8 / zz); b2 = local(pg, 250, r["w"] - 6 / zz)
        pen(pg, [b1, b2])
        rb = [x for x in recs(pg) if x["id"] != line_id]
        LB = rb[0]["data"] if rb else {}
        check("edge B's band draws along edge B (both ends on it)", len(rb) == 1 and edge_perp(r, [LB["x1"], LB["y1"]], "B") < 0.5 and edge_perp(r, [LB["x2"], LB["y2"]], "B") < 0.5
              and LB.get("fixed") is True, LB)
        pg.click("#tool-highlighter"); pg.wait_for_timeout(40); close_panel(pg)
        tr = pg.evaluate("window.__pw.tray()")
        before = set(ids(pg)); pen(pg, [local(pg, 400, -4 / zz), local(pg, 600, -4 / zz)])
        hl = [x for x in recs(pg) if x["id"] not in before]
        where = pg.evaluate("""(id) => { const e = window.__T.sheet('s0').querySelector(`svg.ink [data-id="${id}"]`);
          return e ? [e.parentNode.getAttribute('class'), e.parentNode.parentNode.getAttribute('class'), e.parentNode.getAttribute('opacity')] : null; }""", hl[0]["id"] if hl else "")
        check("with the highlighter on, the line takes the highlighter's style (its width, opacity, solid)",
              len(hl) == 1 and hl[0]["style"] == {"colour": tr["highlighter"]["colour"], "width": tr["highlighter"]["width"], "dash": "solid", "opacity": tr["highlighter"]["opacity"]}
              and hl[0]["data"].get("fixed") is True, [hl, tr["highlighter"]])
        check("... and lands in the highlighter group (g.hlo in g.hl, under the pen group)", where and where[0] == "hlo" and where[1] == "hl", where)
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        before = set(ids(pg)); pen(pg, [local(pg, 620, -4 / zz), local(pg, 700, -4 / zz)])
        sl = [x for x in recs(pg) if x["id"] not in before]
        check("with Select on, the line takes the PEN's style", len(sl) == 1 and sl[0]["style"]["colour"] == tr["pen"]["colour"] and sl[0]["style"]["width"] == tr["pen"]["width"]
              and sl[0]["style"]["opacity"] == 1, sl)
        pg.click("#tool-pen"); pg.wait_for_timeout(40); close_panel(pg)
        pg.screenshot(path=str(SHOTS / "ruler-lines.png"))

        # ------------------------------------------------------------ E: fingers are never the ruler's
        group[0] = "E. fingers"
        pg.wait_for_timeout(700)                                   # page.js ignores a finger for 600 ms after the pen (palm)
        r0 = R(pg); v0 = pg.evaluate("window.__P.view()")
        cpt = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", local(pg, 380, r0["w"] / 2))
        finger(pg, "pointerdown", 71, cpt[0], cpt[1])
        for k in range(1, 7): finger(pg, "pointermove", 71, cpt[0], cpt[1] - 15 * k); pg.wait_for_timeout(16)
        finger(pg, "pointerup", 71, cpt[0], cpt[1] - 90); pg.wait_for_timeout(120)
        v1 = pg.evaluate("window.__P.view()"); r1 = R(pg)
        check("a finger drag starting on the ruler pans the page", v1["y"] < v0["y"] - 50, [v0, v1])
        check("... and the ruler stays where it was on the paper (page px unchanged), no records", r1["o"] == r0["o"] and r1["ang"] == r0["ang"] and len(recs(pg)) == 4, [r0, r1])
        pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)
        z0 = z(pg); c1 = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", local(pg, 300, r0["w"] / 2))
        c2 = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", local(pg, 420, r0["w"] / 2))
        finger(pg, "pointerdown", 81, c1[0], c1[1]); finger(pg, "pointerdown", 82, c2[0], c2[1])
        for k in range(1, 7):
            finger(pg, "pointermove", 81, c1[0] - 15 * k, c1[1]); finger(pg, "pointermove", 82, c2[0] + 15 * k, c2[1]); pg.wait_for_timeout(16)
        finger(pg, "pointerup", 81, c1[0] - 90, c1[1]); finger(pg, "pointerup", 82, c2[0] + 90, c2[1]); pg.wait_for_timeout(120)
        z1 = z(pg); r2 = R(pg)
        check("two fingers starting on the ruler pinch: the zoom grows", z1 > z0 * 1.3, [z0, z1])
        check("... and the ruler keeps its place on the paper", r2["o"] == r0["o"] and r2["ang"] == r0["ang"], [r0, r2])
        pg.evaluate("""() => { const d = document.getElementById('desk'), b = d.getBoundingClientRect(), z0 = window.__T.z();
          d.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: Math.log(window.__T.z() / 1) / 0.0025, clientX: b.left + 400, clientY: b.top + 300, bubbles: true, cancelable: true })); }""")
        pg.wait_for_timeout(80); pg.evaluate("window.__P.scrollToPage(0)"); pg.wait_for_timeout(80)
        check("zoom back at 1x for the stick checks", abs(z(pg) - 1) < 1e-6, z(pg))

        # ------------------------------------------------------------ F: stick points
        group[0] = "F. stick points"
        pg.evaluate("window.__T.clear('s0')"); pg.wait_for_timeout(40)
        zz = z(pg)
        end_id = pg.evaluate("window.__T.line('s0', 450, 100, 450, 300)")      # a snapped line: its end (450, 300) is a stick point
        r0 = R(pg)
        g0 = local(pg, 300, r0["w"] / 2)
        dy = (300 + 13 / zz) - r0["o"][1]                           # edge A to 13 screen px below the end (U5c: the reach is 14)
        pen(pg, [g0, [g0[0], g0[1] + dy / 2], [g0[0], g0[1] + dy]])
        r1 = R(pg)
        check("a ruler edge released 13 px (screen) from a line's end sticks: edge A runs exactly through the end",
              r1["stuck"] is not None and r1["stuck"]["edge"] == "A" and edge_perp(r1, [450, 300], "A") < 1e-6 and r1["stuck"]["p"] == [450, 300], r1)
        ring = pg.evaluate("""() => [...document.querySelectorAll('#stack svg.toolLayer circle.stickRing')].filter((c) => c.getAttribute('display') !== 'none')
          .map((c) => [+c.getAttribute('cx'), +c.getAttribute('cy'), +c.getAttribute('r')])""")
        check("... and a small ring marks the stuck point", len(ring) == 1 and abs(ring[0][0] - 450) < 0.01 and abs(ring[0][1] - 300) < 0.01 and ring[0][2] > 0, ring)
        pen(pg, [local(pg, 300, r1["w"] / 2), local(pg, 300, r1["w"] / 2 + 60 / zz)])
        r2 = R(pg)
        check("moved 60 px away (past the 14 px reach) it lets go, the ring goes",
              r2["stuck"] is None and pg.evaluate("[...document.querySelectorAll('#stack circle.stickRing')].every((c) => c.getAttribute('display') === 'none')"), r2)
        pg.evaluate("window.__T.clear('s0')")
        la = pg.evaluate("window.__T.line('s0', 250, 350, 550, 650)"); lb = pg.evaluate("window.__T.line('s0', 250, 650, 550, 350)")   # crossing at (400, 500)
        r0 = R(pg); g0 = local(pg, 300, r0["w"] / 2); dy = (500 + 10 / zz) - r0["o"][1]
        pen(pg, [g0, [g0[0], g0[1] + dy]])
        r1 = R(pg)
        check("the crossing of two lines is a stick point: the edge sticks through (400, 500)",
              r1["stuck"] is not None and abs(r1["stuck"]["p"][0] - 400) < 1e-9 and abs(r1["stuck"]["p"][1] - 500) < 1e-9 and edge_perp(r1, [400, 500], "A") < 1e-6, r1)
        before = set(ids(pg))
        st = local(pg, along(r1, [400, 500]) + 12 / zz, -5 / zz); en = local(pg, along(r1, [400, 500]) + 200, -5 / zz)
        pen(pg, [st, en])
        nl = [x for x in recs(pg) if x["id"] not in before]
        check("a ruler line started 12 px (screen) from the crossing starts exactly at the crossing",
              len(nl) == 1 and abs(nl[0]["data"]["x1"] - 400) < 0.006 and abs(nl[0]["data"]["y1"] - 500) < 0.006 and nl[0]["data"]["fixed"] is True, nl)
        before = set(ids(pg))
        st = local(pg, along(r1, [400, 500]) - 100, -5 / zz); en = local(pg, along(r1, [400, 500]) - 14 / zz, -5 / zz)
        pen(pg, [st, en])
        nl2 = [x for x in recs(pg) if x["id"] not in before]
        check("... and one drawn up to it ends exactly there", len(nl2) == 1 and abs(nl2[0]["data"]["x2"] - 400) < 0.006 and abs(nl2[0]["data"]["y2"] - 500) < 0.006, nl2)
        check("the new ruler lines are stick points too (ends of every line): stuck still holds", R(pg)["stuck"] is not None)
        far = pg.evaluate("window.__T.line('s0', 700, 560, 700, 760)")          # an end at (700, 560): 11.3 degrees about the crossing (the other end at 41)
        rr = R(pg); k1 = knob(pg, 1); piv = rr["stuck"]["p"]
        pen(pg, turn_path(piv, k1, 10))
        r3 = R(pg)
        check("stuck, a knob turns it about the stuck point, and the edge snaps through a stick point within reach",
              r3["stuck"] is not None and r3["stuck"]["p"] == piv and edge_perp(r3, [700, 560], "A") < 1e-6 and edge_perp(r3, piv, "A") < 1e-6
              and abs(r3["ang"] - math.atan2(60, 300)) < 1e-9, [r3, math.atan2(60, 300)])
        pen(pg, turn_path(piv, knob(pg, 1), -11.31))
        check("turned back it is level again (0 is a 45 degree step)", abs(R(pg)["ang"]) < 1e-9, R(pg)["ang"])
        n_before = len(recs(pg))
        pg.evaluate("window.__T.clear('s0')"); pg.wait_for_timeout(40)
        check("the stuck point's lines erased: the ruler lets go (stick points read again on every change)", R(pg)["stuck"] is None and n_before >= 5, [R(pg), n_before])
        pg.evaluate("""() => window.__pw.ink.put('s0', [{ id: crypto.randomUUID(), page_id: 's0', seq: Date.now() + 5, kind: 'pen',
          style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[600, 700], [640, 720], [680, 700]] } }])""")
        r0 = R(pg); g0 = local(pg, 300, r0["w"] / 2); dy = (700 + 12 / zz) - r0["o"][1]
        pen(pg, [g0, [g0[0], g0[1] + dy]])
        check("freehand ink is never a stick point (an edge 12 px from a pen stroke's end does not stick)", R(pg)["stuck"] is None, R(pg))
        pg.screenshot(path=str(SHOTS / "stick.png"))

        # ------------------------------------------------------------ G: fixed lines and the Select tool
        group[0] = "G. fixed + select"
        pg.evaluate("window.__T.clear('s0')")
        r0 = R(pg)
        pen(pg, [local(pg, 100, -5), local(pg, 400, -5)])
        fx = recs(pg)[0]
        check("handles() of a fixed line: none (no reshaping an end); a plain line keeps its two",
              pg.evaluate("(r) => window.__I.handles(r).length", fx) == 0
              and pg.evaluate("(r) => window.__I.handles({ ...r, data: { ...r.data, fixed: undefined } }).length", fx) == 2)
        toggle_ruler(pg); close_panel(pg)                          # the ruler away: a press on the line is the line's, not the edge band's
        check("the ruler away", R(pg) is None)
        pg.click("#tool-select"); pg.wait_for_timeout(40)
        d0 = fx["data"]; mx, my = (d0["x1"] + d0["x2"]) / 2, (d0["y1"] + d0["y2"]) / 2
        cm_ = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [mx, my])
        pg.mouse.click(cm_[0], cm_[1]); pg.wait_for_timeout(60)
        sel = pg.evaluate("window.__pw.ink.selection()")
        check("Select taps the fixed line: it alone is selected", sel and sel["ids"] == [fx["id"]], sel)
        pg.evaluate("window.__pw.ink.clearSelection()")
        ce = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", [d0["x2"] + 4, d0["y2"]])
        pg.mouse.move(ce[0] - 20, ce[1] - 20); pg.mouse.move(ce[0], ce[1]); pg.wait_for_timeout(40)
        hr = pg.evaluate("() => { const h = document.getElementById('handleRing'); return !!h && !h.hidden; }")
        check("the pen hovering on its end shows no handle ring", hr is False, hr)
        pg.mouse.down(); pg.mouse.move(ce[0] + 20, ce[1] + 15, steps=3); pg.mouse.move(ce[0] + 40, ce[1] + 30, steps=3); pg.mouse.up(); pg.wait_for_timeout(60)
        fx_now = [x for x in recs(pg)]
        check("a Select press-drag from its end grabs no end: the line is unchanged (no reshaping)",
              len(fx_now) == 1 and fx_now[0]["data"] == d0, [fx_now, d0])
        pg.evaluate("window.__pw.ink.clearSelection()")
        pg.mouse.click(cm_[0], cm_[1]); pg.wait_for_timeout(60)
        pg.mouse.move(cm_[0], cm_[1]); pg.mouse.down(); pg.mouse.move(cm_[0] + 20, cm_[1] + 15, steps=3); pg.mouse.move(cm_[0] + 40, cm_[1] + 30, steps=3); pg.mouse.up(); pg.wait_for_timeout(60)
        mv = recs(pg)
        dd = mv[0]["data"] if mv else {}
        check("Select drags it whole: both ends move by the same 40, 30, still a fixed line",
              len(mv) == 1 and abs(dd["x1"] - d0["x1"] - 40) < 0.11 and abs(dd["y1"] - d0["y1"] - 30) < 0.11 and abs(dd["x2"] - d0["x2"] - 40) < 0.11
              and abs(dd["y2"] - d0["y2"] - 30) < 0.11 and dd.get("fixed") is True and dd["type"] == "line", [d0, dd])
        pg.evaluate("document.querySelector('.selChips .chip[data-act=\"copy\"]').click()"); pg.wait_for_timeout(40)
        pg.evaluate("window.__pw.ink.pasteAt('s0', 400, 900)"); pg.wait_for_timeout(60)
        ps = recs(pg)
        check("Copy then Paste: the pasted copy is still fixed", len(ps) == 2 and all(x["data"].get("fixed") is True for x in ps) and ps[0]["id"] != ps[1]["id"], ps)
        pg.evaluate("document.querySelector('.selChips .chip[data-act=\"duplicate\"]').click()"); pg.wait_for_timeout(60)
        dp = recs(pg)
        check("Duplicate keeps fixed too", len(dp) == 3 and all(x["data"].get("fixed") is True for x in dp), dp)
        pg.click("#tool-pen"); pg.wait_for_timeout(40); close_panel(pg)

        # ------------------------------------------------------------ H: what is saved, thumbs and the PDF
        group[0] = "H. records, thumb, PDF"
        toggle_ruler(pg); close_panel(pg)
        rs = recs(pg)
        check("strokesOf carries the fixed lines and nothing else (3 records, all 'shape' lines)",
              len(rs) == 3 and all(x["kind"] == "shape" and x["data"]["type"] == "line" for x in rs) and R(pg) is not None, rs)
        th = pg.evaluate("""() => { const s = window.__pw.ink.thumbSvg('s0'); return { lines: s.querySelectorAll('g.pen > line').length,
          ruler: s.querySelectorAll('text, .ruler, .toolLayer, circle').length }; }""")
        check("the thumb draws the 3 lines and no ruler", th == {"lines": 3, "ruler": 0}, th)
        pdf64 = pg.evaluate("""async () => { const m = await import('./js/pdfout.js');
          const blob = await m.buildPdf([{ id: 's0', orientation: 'portrait', background: 'blank', pdf_path: null }], 'Tools');
          const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode(...b.subarray(i, i + 8192));
          return btoa(s); }""")
        doc = fitz.open(stream=base64.b64decode(pdf64), filetype="pdf"); page = doc[0]
        items = [it for dr in page.get_drawings() for it in dr["items"] if it[0] == "l"]
        kpt = 595.28 / 794                                           # page px to PDF pt (A4 across)
        want = [(x["data"]["x1"] * kpt, x["data"]["y1"] * kpt, x["data"]["x2"] * kpt, x["data"]["y2"] * kpt) for x in rs]
        def has(w): return any(math.hypot(it[1].x - w[0], it[1].y - w[1]) < 0.2 and math.hypot(it[2].x - w[2], it[2].y - w[3]) < 0.2 for it in items)
        check("Share as PDF (buildPdf) draws every ruler line at its place (vector, in pt)", all(has(w) for w in want), [want, [(round(i[1].x, 2), round(i[1].y, 2), round(i[2].x, 2), round(i[2].y, 2)) for i in items][:8]])
        txt = page.get_text().strip()
        check("... and not the ruler (no ticks: only the 3 lines, no numbers)", len(items) == 3 and txt == "", [len(items), txt])
        doc.close()

        # ------------------------------------------------------------ I: hanging off the page
        group[0] = "I. off the page"
        show_ruler(pg)
        r0 = R(pg); zz = z(pg); sh = rect(pg, "#stack .sheet[data-id='s0']")
        g0 = local(pg, 300, r0["w"] / 2)
        probe_page = [794 + 30, r0["o"][1] + r0["w"] / 2]                   # 30 page px right of the page, through the body's middle
        pc = pg.evaluate("([x, y]) => window.__T.client('s0', x, y)", probe_page)
        clipbox = {"x": pc[0] - 3, "y": pc[1] - 3, "width": 6, "height": 6}
        toggle_ruler(pg); close_panel(pg); bare = pg.screenshot(clip=clipbox)
        toggle_ruler(pg); close_panel(pg)
        pen(pg, [g0, [g0[0] + 200, g0[1]], [g0[0] + 400, g0[1]]])
        r1 = R(pg); bx = rect(pg, "#stack svg.toolLayer rect.body")
        lit = pg.screenshot(clip=clipbox)
        pg.screenshot(path=str(SHOTS / "half-off.png"))
        check("moved half off the page: its body reaches 400 page px past the right edge",
              abs(r1["o"][0] - r0["o"][0] - 400) < 1e-6 and bx["r"] > sh["r"] + 300 * zz, [r1, bx, sh])
        check("... and it is drawn there, not clipped (the desk beside the page looks different with the ruler over it)", bare != lit)
        before = len(recs(pg))
        pen(pg, [local(pg, 700, -5), local(pg, 760, -5)])
        hang = recs(pg)[before:] if len(recs(pg)) > before else []
        check("the part off the page still draws along its edge (a line past the page edge, on page 1)",
              len(recs(pg)) == before + 1 and recs(pg)[-1]["page_id"] == "s0", recs(pg)[-1] if recs(pg) else None)
        pg.click("#undoBtn"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ J: closing the note
        group[0] = "J. close + reopen"
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(50)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(80)
        check("closing the note puts the ruler away (no layer in the page), the panel closes, the button unpressed",
              R(pg) is None and pg.locator("svg.toolLayer").count() == 0 and pg.locator("#toolsPanel").is_hidden() and pressed(pg, "#drawToolsBtn") == "false")
        open_note(pg)
        pg.click("#drawToolsBtn"); pg.wait_for_timeout(60)
        rows = pg.evaluate("[...document.querySelectorAll('#toolsPanel .trow')].map((b) => b.getAttribute('aria-pressed'))")
        check("reopened: no tool out, every row unpressed", R(pg) is None and pg.locator("svg.toolLayer").count() == 0 and rows == ["false"] * 4, rows)
        close_panel(pg)
        check("the fixed lines are still there after the reopen (saved like any ink)", len(recs(pg)) == 3, len(recs(pg)))
        check("no page errors", not errs, errs)
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
