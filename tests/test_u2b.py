# PenWorks U2 B checks (shapes and selection): headless Playwright (Python), same style as tests/test_u2a.py.
# Run: python tests/test_u2b.py               (local mode only: ?local=1, Supabase is never touched)
#      add --shots <folder> for small screenshots
# Every group seeds its own folder > notes > pages into the localStorage twin, draws with the mouse, and reads
# the stroke records and the SVG layers: hold-to-snap, grabbable handles, restyle, rectangle select, erasers.
# U2 B fix round (pw-v4a): real pen events on a handle (20 px reach), touch-any-part select, highlighter snap,
# restyle's own colour, colour tap and Restyle tap on a selection.
# Pen button round (pw-v4b): the plain pen always draws; a handle is grabbed only with the S Pen's side button
# (buttons & 2) or the right mouse button; the ?dbg=1 pointer readout.
# Pen button 2 round (pw-v4c): her tablet sends the button only as one contextmenu per press, so a press near a
# handle picks it up, the pen's moves carry it, a touch and lift (or a second press, a tool change, Escape, undo) drops it.
# Desk scroll fix (pw-v4d): #desk is overflow: clip, never a scroll container (her tablet: ink landed a fixed distance
# above the pen after a button press / long hold until a reopen); the proof test lives in tests/test_scroll.py.
# Plain pen grabs again (pw-v4e): her S Pen button can never hold, and the one-press pick-up did not work for her,
# so the pw-v4a rule is back: with the pen tool, any pen or mouse down within 20 px of a shape handle grabs it,
# button or not, anywhere else it draws; the hover ring shows within reach, button or not; a contextmenu changes
# nothing and the pick-up code is gone. The pw-v4b and pw-v4c groups are rewritten to this rule.
# Arc snap (pw-v4f): an open curve held still snaps to { type: 'arc', x1, y1, xm, ym, x2, y2 }, an SVG path with an A;
# three handles (start, middle, end); the "arc snap" group. The old "a half circle stays freehand" check now expects arc.
# Select turns (pw-v4g): a turn ring above the selection box (28 px on screen, on a stem) turns the selection about the
# box's centre, snapping to multiples of 15 degrees within 2.5; an ellipse keeps data.angle and rotate(angle cx cy);
# a moved, resized or turned selection comes to the front (fresh seq, last in its own layer group); a resize keeps
# the ink's width (the old "the ink width scales" check now asserts it stays). The "rotate, front, width" group.
# Restyle keeps the dash, ring flips (pw-v4h): a restyle (tap, drag, or the Restyle tap on a selection) takes the
# pen's colour and width but keeps the stroke's OWN dash (the old "takes dashed" checks are flipped); a selection
# whose turn ring would pass the page's top edge puts the ring below the box, stem from the bottom edge, chips
# unmoved at the box's top-left. The end of the "restyle" group and the "ring flips near the page top" group.
# Page list (pw-v4i): the page list thumbs draw the ink, a thumb tap keeps the panel open; checks in tests/test_pagelist.py.
# Select polish (pw-v4j): a tap with the select tool selects the topmost stroke under it (12 px reach), a drag box still
# takes everything it touches; a finger tap outside the selection clears it (a pan keeps it); a turn shows its degrees
# (.selDeg) beside the ring; the Copy and Delete chips are round icon buttons (the word in aria-label and title), so
# SELUI_JS now reads the chips' aria-label instead of their text. The "select polish (pw-v4j)" group.
# Clipboard (pw-v4k): the Copy chip puts the selection on a clipboard and adds nothing (the two old "Copy duplicates on
# the spot" checks, in "select" and "select polish (pw-v4j)", are flipped); a finger held still 500 ms on a page opens a
# small menu with Paste (disabled "Nothing to paste" while the clipboard is empty), which pastes there, centred on the
# finger, kept inside the page, selected, select tool on, one undo step, across pages and notes. The "clipboard (pw-v4k)" group.
# Area eraser cuts shapes (pw-v4l): a shape the area eraser touches turns into pen or highlighter ink and is cut like a
# stroke (one bite out of a closed shape leaves one open piece; an arrow becomes shaft and head ink); the stroke eraser
# still removes a shape whole. The erasers group's "removes the whole circle" check is flipped; the "area eraser cuts shapes (pw-v4l)" group.
# Overlap tie-break (pw-v4m): a select tap where a highlighter-layer and a pen-layer record overlap picks the one in the
# layer of the last ink tool (pen or highlighter, restored after a reload); with no overlap across the layers, the
# topmost record under the tap, whatever it is. The "overlap pick (pw-v4m)" group.
# Duplicate chip (pw-v4o): a third chip (+, aria-label Duplicate) between Copy and Delete copies the selection 24 px right
# and down, kept inside the page, selected, one undo step, the clipboard untouched; the "two chips" checks in "select" and
# "select polish (pw-v4j)" now expect Copy, Duplicate, Delete. The "duplicate chip (pw-v4o)" group.
# Select all (pw-v4p): the finger hold menu has two items, Select all (disabled "Nothing to select" on an empty page)
# then Paste; Select all selects every record on that page, select tool on, no undo step. The clipboard group's menu
# checks now expect two items (and tap Paste by its label). The "select all (pw-v4p)" group.
# Parabola snap (pw-v4s): an open curve with one turn whose arms straighten, held still, snaps to { type: 'parabola', x1, y1,
# cx, cy, x2, y2 } (a quadratic Bezier, an SVG path M Q); an even curve (a semicircle, a 120 degree arc) stays an arc, an S
# stays freehand; three handles (start, M, end); move, resize, turn, the area eraser, restyle, Copy / Paste and Duplicate
# keep it a parabola; the ?dbg=1 line shows both fits. The "parabola snap (pw-v4s)" group (rough_parabola below).
# Select drags an end (pw-v4v): the plain pen never grabs (it draws, even on a shape's end) and shows no ring; the SELECT tool
# grabs a shape's handle (after the selection's ring and corners, before a move inside the box; a tap on a handle selects the
# shape); the pen button (one contextmenu on the desk) flips between Select and the last ink tool through the tray. The
# "plain pen grabs" and "pen button press" groups are rewritten as "select drags an end (pw-v4v)"; grab_page now grabs with
# the select tool, rdrag_page is the old right-button drag (whose release now flips the tool).
# Arrow tip = first corner (pw-v4w): classify takes the arrow's tip from tipIndex (ink.js), the stroke's FIRST sharp corner,
# not the point farthest from the start; the tail may be up to 1.2 x the shaft. Her real pen strokes live in tests/fixtures
# (arrow-pen-fail, arrow-pen-ok, curved-arrow-pen; never edited). The "arrow tip = first corner (pw-v4w)" group.
# Curved arrow (pw-v4x): a curved shaft with the arrow's head at its end snaps to { type: 'carrow', x1, y1, xm, ym, x2, y2 }
# (the arc's data, the head along the arc's end tangent), a <g> of two paths; her curved-arrow-pen fixture is one; three
# handles, move, resize, turn, the erasers, restyle, Duplicate and Paste keep the head on the end. A snap's undo takes the
# shape away as every snap's does. The "curved arrow (pw-v4x)" group.
import sys, subprocess, time, pathlib, re, json, math, random
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8779
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None

res = []
group = ["?"]
info_lines = []
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-25T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U2B', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Snap', '2026-10-25T10:06:00Z'), N('n2', 'Handles', '2026-10-25T10:05:00Z'), N('n3', 'Restyle', '2026-10-25T10:04:00Z'),
            N('n4', 'Select', '2026-10-25T10:03:00Z'), N('n5', 'Erase', '2026-10-25T10:02:00Z')],
    pages: [P('p1', 'n1', 0), P('p2', 'n2', 0), P('p3', 'n3', 0), P('p4', 'n4', 0), P('p4b', 'n4', 1), P('p5', 'n5', 0)] }));
}"""
STROKES_JS = "(id) => window.__pw.ink.strokesOf(id)"
STORED_JS = "(id) => window.__pw.store.cached(id)"   # U3a: the device cache (IndexedDB), null when the page has none
EL_JS = """([i, id]) => { const e = document.querySelector(`#stack .sheet[data-index="${i}"] svg.ink [data-id="${id}"]`);
  if (!e) return null;
  const a = (k) => e.getAttribute(k);
  return { tag: e.tagName, parent: e.parentNode.getAttribute('class'), gp: e.parentNode.parentNode.getAttribute('class'), stroke: a('stroke'),
    width: a('stroke-width'), dash: a('stroke-dasharray'), fill: a('fill'), type: e.dataset.type, transform: a('transform'),
    opacity: e.parentNode.getAttribute('opacity'), kids: [...e.children].map(c => c.tagName) }; }"""
SEL_JS = "() => window.__pw.ink.selection()"
SELUI_JS = """() => { const g = document.querySelector('svg.ink g.sel'), c = document.querySelector('.selChips');
  return { g: !!g, box: g ? !!g.querySelector('rect.selbox') : false, dash: g && g.querySelector('rect.selbox') ? g.querySelector('rect.selbox').getAttribute('stroke-dasharray') : null,
    corners: g ? g.querySelectorAll('circle.selh').length : 0,
    chips: c ? [...c.querySelectorAll('button')].map(b => b.getAttribute('aria-label')) : [], chipsShown: c ? c.getBoundingClientRect().height > 0 : false }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def strokes(pg, pid): return pg.evaluate(STROKES_JS, pid)
def stored(pg, pid): return pg.evaluate(STORED_JS, pid)
def elinfo(pg, i, sid): return pg.evaluate(EL_JS, [i, sid])
def sel(pg): return pg.evaluate(SEL_JS)
def selui(pg): return pg.evaluate(SELUI_JS)
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name):
    if pg.locator("#noteView").is_visible(): return          # a reload reopens the note she was in
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def go_page(pg, i):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
    pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120)
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
def tap_page(pg, i, x, y):
    sx, sy = screen(pg, i, x, y); pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(40)
def drag_page(pg, i, a, b, steps=10):
    sx, sy = screen(pg, i, *a); pg.mouse.move(sx, sy); pg.mouse.down()
    tx, ty = screen(pg, i, *b); pg.mouse.move(tx, ty, steps=steps); pg.mouse.up(); pg.wait_for_timeout(40)
def grab_page(pg, i, a, b, steps=10):          # a handle grab (pw-v4v): the SELECT tool's pen down on the handle and drag, then back to the tool it was
    was = pg.evaluate("window.__pw.ink.tool().tool")
    if was != "select": tool(pg, "select")
    drag_page(pg, i, a, b, steps)
    if was != "select": tool(pg, was)
def rdrag_page(pg, i, a, b, steps=10):         # the right mouse button held and dragged (its contextmenu comes on the release and flips the tool, pw-v4v)
    sx, sy = screen(pg, i, *a); pg.mouse.move(sx, sy); pg.mouse.down(button="right")
    tx, ty = screen(pg, i, *b); pg.mouse.move(tx, ty, steps=steps); pg.mouse.up(button="right"); pg.wait_for_timeout(40)
def tool_is(pg): return pg.evaluate("window.__pw.ink.tool().tool")
def lit(pg): return pg.evaluate("[...document.querySelectorAll('#tray .tool.on')].map(e => e.dataset.tool)")
def last(pg, pid): s = strokes(pg, pid); return s[-1] if s else None
def U(pg): return pg.evaluate("window.__pw.S.hist[window.__pw.S.openNote] ? window.__pw.S.hist[window.__pw.S.openNote].u.length : 0")
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(30)
def redo(pg): pg.click("#redoBtn"); pg.wait_for_timeout(30)
def tool(pg, t): pg.click(f"#tool-{t}"); pg.wait_for_timeout(20)
def near(a, b, tol): return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
def wobble(k, amp=2.0): return amp * math.sin(k * 1.7) * math.cos(k * 0.6)
def fresh(b, url=LOCAL, **kw):
    ctx = b.new_context(viewport={"width": 1280, "height": 1300}, **kw)   # tall: the whole A4 page on screen
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url); ready(pg)
    pg.evaluate(SEED_JS); pg.reload(); ready(pg)
    return ctx, pg, errs

# rough shapes, in page px (zoom 1)
def rough_line(y=200, x0=100, x1=420): return [(x0 + (x1 - x0) * k / 12, y + wobble(k, 2.5) + k * 0.4) for k in range(13)]
def rough_square(x0=150, y0=380, s=200):
    pts = []
    for (ax, ay), (bx, by) in [((x0, y0), (x0 + s, y0)), ((x0 + s, y0), (x0 + s, y0 + s)), ((x0 + s, y0 + s), (x0, y0 + s)), ((x0, y0 + s), (x0, y0))]:
        for k in range(8): pts.append((ax + (bx - ax) * k / 8 + wobble(len(pts), 2.2), ay + (by - ay) * k / 8 + wobble(len(pts) + 3, 2.2)))
    pts.append((x0 + 3, y0 + 2)); return pts
def rough_circle(cx=560, cy=480, rx=90, ry=None, n=36):
    ry = ry or rx
    return [(cx + rx * (1 + wobble(k, 0.04)) * math.cos(2 * math.pi * k / n - math.pi / 2), cy + ry * (1 + wobble(k + 2, 0.04)) * math.sin(2 * math.pi * k / n - math.pi / 2)) for k in range(n + 1)]
def rough_triangle():
    A, B, C = (150, 700), (350, 700), (250, 880)
    pts = []
    for (ax, ay), (bx, by) in [(A, B), (B, C), (C, A)]:
        for k in range(8): pts.append((ax + (bx - ax) * k / 8 + wobble(len(pts), 1.8), ay + (by - ay) * k / 8 + wobble(len(pts) + 1, 1.8)))
    pts.append((A[0] + 2, A[1] + 1)); return pts
def rough_arrow(y=980, x0=120, x1=420):
    return [(x0 + (x1 - x0) * k / 8, y + wobble(k, 1.5)) for k in range(9)] + [(x1 - 24, y - 20), (x1, y), (x1 - 24, y + 20)]
def squiggle(): return [(100 + 20 * k, 1060 + (18 if k % 2 else -18)) for k in range(12)]
# a hand arc: angles a0 to a1 in degrees (page px, y down, so growing angles go clockwise on screen), every point
# nudged up to amp px each way
def rough_arc(cx, cy, r, a0, a1, n=24, amp=1.5):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)) + wobble(k, amp), cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)) + wobble(k + 3, amp)) for k in range(n + 1)]
# a hand parabola (pw-v4s): y = vy + a (x - vx)^2 for x from vx - half_width to vx + half_width (side=True: x and y swapped,
# x = vx + a (y - vy)^2), every point nudged up to jitter px each way (seeded, so every run draws the same stroke)
def rough_parabola(vx, vy, a, half_width, n=40, jitter=1.5, side=False, seed=7):
    rnd = random.Random(seed); out = []
    for k in range(n + 1):
        u = -half_width + 2 * half_width * k / n; w = a * u * u
        jx, jy = rnd.uniform(-jitter, jitter), rnd.uniform(-jitter, jitter)
        out.append((vx + w + jx, vy + u + jy) if side else (vx + u + jx, vy + w + jy))
    return out

# real pen input: Chromium's own input pipeline (CDP Input.dispatchMouseEvent with pointerType 'pen'), so the
# browser hit-tests, fires pointerdown / pointermove / pointerup with pointerType 'pen' and page.js sees a pen
# bb=2: the pen's side button held (bit 2 in buttons) on every event, hover included
class Pen:
    def __init__(self, ctx, pg): self.pg = pg; self.cdp = ctx.new_cdp_session(pg)
    def ev(self, t, x, y, down, bb=0, button=None):
        self.cdp.send("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "pointerType": "pen",
                                                   "button": button or ("left" if t != "mouseMoved" or down else "none"),
                                                   "buttons": (1 if down else 0) | bb, "clickCount": 0 if t == "mouseMoved" else 1})
    def hover(self, x, y, bb=0): self.ev("mouseMoved", x, y, False, bb); self.pg.wait_for_timeout(15)
    # the tip down and along: with bb=2 the button is held from the hover on, so (as the spec says) the touch
    # arrives as a move with button 0, buttons 3, not a pointerdown; the tip lifts with the button still held
    def stroke(self, pts, hold=0, steps=6, bb=0):
        (x, y) = pts[0]; self.ev("mouseMoved", x, y, False, bb); self.ev("mousePressed", x, y, True, bb)
        for (tx, ty) in pts[1:]:
            for k in range(1, steps + 1): self.ev("mouseMoved", x + (tx - x) * k / steps, y + (ty - y) * k / steps, True, bb)
            x, y = tx, ty
            self.pg.wait_for_timeout(5)
        if hold: self.pg.wait_for_timeout(hold)
        self.ev("mouseReleased", x, y, False, bb); self.pg.wait_for_timeout(20)
        if bb: self.ev("mouseMoved", x, y, False); self.pg.wait_for_timeout(20)    # the button let go in the air
        self.pg.wait_for_timeout(20)
    # a press of the side button itself: pointerdown pen, button 2, buttons 2, then the drag and the release
    def bstroke(self, pts, steps=6):
        (x, y) = pts[0]; self.ev("mouseMoved", x, y, False); self.ev("mousePressed", x, y, False, 2, "right")
        for (tx, ty) in pts[1:]:
            for k in range(1, steps + 1): self.ev("mouseMoved", x + (tx - x) * k / steps, y + (ty - y) * k / steps, False, 2, "right")
            x, y = tx, ty
            self.pg.wait_for_timeout(5)
        self.ev("mouseReleased", x, y, False, 0, "right"); self.pg.wait_for_timeout(40)
# a synthetic pen gesture: PointerEvents with pointerType 'pen' fired on whatever element is under the point
# (bubbling to the desk), the way the S Pen's own events arrive
SYNTH_JS = """([pts, bb]) => { const fire = (t, [x, y], b) => { const el = document.elementFromPoint(x, y) || document.getElementById('desk');
    el.dispatchEvent(new PointerEvent(t, { bubbles: true, cancelable: true, composed: true, pointerId: 7, pointerType: 'pen', isPrimary: true,
      clientX: x, clientY: y, button: t === 'pointermove' ? -1 : 0, buttons: b, pressure: b ? 0.5 : 0 })); return el; };
  const first = fire('pointerdown', pts[0], 1 | (bb || 0));
  for (const q of pts.slice(1)) fire('pointermove', q, 1 | (bb || 0));
  fire('pointerup', pts[pts.length - 1], 0);
  return first.closest('svg.ink') ? 'svg' : (first.id || first.className || first.tagName); }"""

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
shots = 0
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx, pg, errs = fresh(b)

        # ------------------------------------------------------------ the tray: the two new tools
        group[0] = "tray"
        open_note(pg, "Snap")
        order = pg.evaluate("""[...document.getElementById('tray').querySelectorAll(':scope > *, :scope > .tools > *')]
          .map(e => e.dataset.tool || e.dataset.slot || e.id || e.className)""")
        check("order: colours, pen, highlighter, undo (pw-v6c), stroke eraser, area eraser, restyle, select, gap, redo, Tools slot",
              order == ["colours", "tools", "pen", "highlighter", "undoBtn", "eraser", "area", "restyle", "select", "gap", "redoBtn", "tools"], order)
        tb = pg.evaluate("""['restyle', 'select'].map(t => { const e = document.getElementById('tool-' + t), r = e.getBoundingClientRect();
          return [e.tagName, e.className, e.title, e.getAttribute('aria-label'), Math.round(r.width), Math.round(r.height), !!e.querySelector('svg'), e.textContent.trim()]; })""")
        pen_r = pg.evaluate("(() => { const r = document.getElementById('tool-pen').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })()")
        check("restyle and select are real tool buttons: icon only, a title each, the pen's size",
              all(t[0] == "BUTTON" and "tool" in t[1] and t[2] and t[3] and [t[4], t[5]] == pen_r and t[6] and t[7] == "" for t in tb), [tb, pen_r])
        check("their titles: Restyle, Select", [t[2] for t in tb] == ["Restyle", "Select"], tb)
        check("only the Tools slot is still an empty slot", pg.evaluate("[...document.querySelectorAll('#tray .slot')].map(s => s.dataset.slot + ':' + s.children.length)") == ["tools:0"])
        tool(pg, "restyle")
        on = pg.evaluate("[...document.querySelectorAll('#tray .tool.on')].map(e => e.dataset.tool)")
        tint = pg.evaluate("getComputedStyle(document.getElementById('tool-restyle')).backgroundColor")
        pen_tint = pg.evaluate("(() => { document.getElementById('tool-pen').click(); return getComputedStyle(document.getElementById('tool-pen')).backgroundColor; })()")
        check("restyle selected shows the same soft tint as the pen", on == ["restyle"] and tint == pen_tint and tint != "rgba(0, 0, 0, 0)", [on, tint, pen_tint])
        check("tray still fits (no tray scroll)", pg.evaluate("(() => { const t = document.getElementById('tray'); return t.scrollHeight <= t.clientHeight; })()"))
        check("HOLD_MS default is 500", pg.evaluate("import('./js/ink.js').then(m => m.HOLD_MS)") == 500)

        # ------------------------------------------------------------ hold-to-snap
        group[0] = "snap"
        tool(pg, "pen")
        u0 = U(pg)
        L0 = rough_line()
        draw(pg, 1, L0, hold=650)
        r = last(pg, "p1")
        check("a nearly straight stroke held 600+ ms becomes shape/line", r and r["kind"] == "shape" and r["data"]["type"] == "line", r and [r["kind"], r["data"]])
        if r and r["kind"] == "shape":
            d = r["data"]
            check("the line's ends sit near the stroke's ends", near((d["x1"], d["y1"]), L0[0], 6) and near((d["x2"], d["y2"]), L0[-1], 6), [d, L0[0], L0[-1]])
            check("same colour, width and dash as the pen", r["style"] == {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1}, r["style"])
            e = elinfo(pg, 1, r["id"])
            check("drawn as an SVG <line> inside g.pen", e and e["tag"] == "line" and e["parent"] == "pen" and e["stroke"] == "#000000" and e["width"] == "2.5" and e["fill"] == "none", e)
            check("one stroke on the page (the freehand is gone)", len(strokes(pg, "p1")) == 1)
            pg.wait_for_timeout(200)
            check("after the 150 ms fade only the shape is in the layer", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 1)
        check("a snap is ONE undo step", U(pg) == u0 + 1, [u0, U(pg)])
        undo(pg)
        check("undo takes the shape away", len(strokes(pg, "p1")) == 0)
        redo(pg)
        check("redo brings it back", len(strokes(pg, "p1")) == 1 and last(pg, "p1")["kind"] == "shape")

        draw(pg, 1, rough_square(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a rough square held: shape/rect with 4 points", r["kind"] == "shape" and r["data"]["type"] == "rect" and len(r["data"]["points"]) == 4, [r["kind"], r["data"]])
        if r["data"].get("type") == "rect":
            P = r["data"]["points"]
            check("the square is straightened (sides upright) and near its corners", P[0][1] == P[1][1] and P[1][0] == P[2][0] and P[2][1] == P[3][1] and P[3][0] == P[0][0]
                  and near(P[0], (150, 380), 8) and near(P[2], (350, 580), 8), P)
            check("drawn as an SVG <polygon>", elinfo(pg, 1, r["id"])["tag"] == "polygon")
        draw(pg, 1, rough_circle(), steps=2, hold=650)
        r = last(pg, "p1")
        check("a rough circle held: circle", r["kind"] == "shape" and r["data"]["type"] == "circle", [r["kind"], r["data"]])
        if r["data"].get("type") == "circle":
            check("centre and radius close", near((r["data"]["cx"], r["data"]["cy"]), (560, 480), 6) and abs(r["data"]["r"] - 90) <= 8, r["data"])
            check("drawn as an SVG <circle>", elinfo(pg, 1, r["id"])["tag"] == "circle")
        draw(pg, 1, rough_circle(560, 760, 130, 65), steps=2, hold=650)
        r = last(pg, "p1")
        check("a long oval held: ellipse", r["kind"] == "shape" and r["data"]["type"] == "ellipse", [r["kind"], r["data"]])
        draw(pg, 1, rough_triangle(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a rough triangle held: triangle with 3 points", r["kind"] == "shape" and r["data"]["type"] == "triangle" and len(r["data"]["points"]) == 3, [r["kind"], r["data"]])
        draw(pg, 1, rough_arrow(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a line with a V at the end held: arrow", r["kind"] == "shape" and r["data"]["type"] == "arrow", [r["kind"], r["data"]])
        if r["data"].get("type") == "arrow":
            check("the arrow runs from the start to the V's tip", near((r["data"]["x1"], r["data"]["y1"]), (120, 980), 6) and near((r["data"]["x2"], r["data"]["y2"]), (420, 980), 6), r["data"])
            e = elinfo(pg, 1, r["id"])
            check("an arrow is a <g> with its line and an open head", e["tag"] == "g" and e["kids"] == ["line", "path"], e)
        n = len(strokes(pg, "p1"))
        draw(pg, 1, squiggle(), steps=3, hold=650)
        r = last(pg, "p1")
        check("a squiggle held: stays pen", len(strokes(pg, "p1")) == n + 1 and r["kind"] == "pen", r["kind"])
        draw(pg, 1, [(450, 1080), (700, 1082)], steps=8, hold=0)
        r = last(pg, "p1")
        check("a straight stroke lifted at once: stays pen", r["kind"] == "pen", r["kind"])
        draw(pg, 1, [(450, 1040), (700, 1042)], steps=8, hold=250)
        check("a straight stroke held only 250 ms: stays pen", last(pg, "p1")["kind"] == "pen")
        draw(pg, 1, [(30, 60), (40, 62)], steps=4, hold=650)
        check("a short stroke (under 30 px) held: stays pen", last(pg, "p1")["kind"] == "pen")
        tool(pg, "highlighter")
        draw(pg, 1, [(450, 120), (720, 124)], steps=8, hold=650)
        check("a highlighter stroke held: snaps too now (fix round point 3)", last(pg, "p1")["kind"] == "shape" and last(pg, "p1")["style"]["opacity"] < 1, last(pg, "p1"))
        tool(pg, "pen"); pg.click("#tool-pen")
        pg.locator("#toolPanel .dash[data-dash='dashed']").click(); pg.mouse.click(400, 10)
        draw(pg, 1, [(450, 300), (600, 302), (720, 303)], steps=6, hold=650)
        r = last(pg, "p1")
        e = elinfo(pg, 1, r["id"])
        check("a dashed pen line snaps dashed (dasharray on the <line>)", r["kind"] == "shape" and r["style"]["dash"] == "dashed" and e["dash"], [r["style"], e])
        pg.click("#tool-pen"); pg.locator("#toolPanel .dash[data-dash='solid']").click(); pg.mouse.click(400, 10)
        idle(pg)
        kinds = [(s["kind"], s["data"].get("type")) for s in stored(pg, "p1")]
        pg.reload(); ready(pg); open_note(pg, "Snap")
        k2 = [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p1")]
        tags = pg.evaluate("[...document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink [data-type]')].map(e => e.dataset.type)")
        check("reload keeps every shape and redraws it (pen and highlighter layers)", k2 == kinds and sorted(tags) == sorted(t for k, t in kinds if k == "shape"), [kinds, tags])
        if SHOTS and shots < 3:
            SHOTS.mkdir(parents=True, exist_ok=True); pg.screenshot(path=str(SHOTS / "u2b-snap.png")); shots += 1
        # the classifier on harder hand shapes (straight from ink.js, no drawing)
        def cls(pts): r = pg.evaluate("(p) => import('./js/ink.js').then(m => m.classify(p))", [list(q) for q in pts]); return r and r["type"]
        def turn(pts, a, c=(300, 300)):
            ca, sa = math.cos(a), math.sin(a)
            return [(c[0] + (x - c[0]) * ca - (y - c[1]) * sa, c[1] + (x - c[0]) * sa + (y - c[1]) * ca) for x, y in pts]
        sq = rough_square(200, 200, 200)
        tsq = turn(sq, math.radians(35))
        check("a square turned 35 degrees: rect", cls(tsq) == "rect", cls(tsq))
        r = pg.evaluate("(p) => import('./js/ink.js').then(m => m.classify(p))", [list(q) for q in tsq])
        check("... stored as its 4 turned corners (not straightened)", r and len(r["points"]) == 4 and r["points"][0][1] != r["points"][1][1], r)
        over = sq[:-1] + [(200 + 10 * k, 200 + wobble(k)) for k in range(1, 5)]
        check("a square closed with an overshoot past the start: rect", cls(over) == "rect", cls(over))
        ccw = [(300 + 70 * math.cos(-2 * math.pi * k / 30), 300 + 70 * math.sin(-2 * math.pi * k / 30)) for k in range(31)]
        check("a circle started at 3 o'clock, drawn the other way: circle", cls(ccw) == "circle", cls(ccw))
        check("an L stays freehand", cls([(100, 100), (100, 160), (100, 220), (140, 220), (180, 220)]) is None)
        check("a tick (V) stays freehand", cls([(100, 200), (120, 220), (140, 240), (180, 180), (220, 120)]) is None)
        check("a zigzag stays freehand", cls(squiggle()) is None)
        hc = [(300 + 80 * math.cos(math.pi * k / 20), 300 - 80 * math.sin(math.pi * k / 20)) for k in range(21)]
        check("a half circle is an arc now (pw-v4f; it stayed freehand before)", cls(hc) == "arc", cls(hc))
        bow = [(100 + 15 * k, 300 + 6 * math.sin(math.pi * k / 20)) for k in range(21)]
        check("a line with a slight bow (2% of its length): line", cls(bow) == "line", cls(bow))

        ctx.close()

        # the hold override
        ctx, pg, errs2 = fresh(b, LOCAL + "&hold=1500")
        check("?hold=1500 sets HOLD_MS", pg.evaluate("import('./js/ink.js').then(m => m.HOLD_MS)") == 1500)
        open_note(pg, "Snap")
        draw(pg, 1, rough_line(), hold=650)
        check("with ?hold=1500 a 650 ms hold stays pen", last(pg, "p1")["kind"] == "pen")
        draw(pg, 1, rough_line(400), hold=1650)
        check("and a 1650 ms hold snaps", last(pg, "p1")["kind"] == "shape")
        errs += errs2
        ctx.close()

        # ------------------------------------------------------------ grabbable handles
        group[0] = "handles"
        ctx, pg, e3 = fresh(b); errs += e3
        open_note(pg, "Handles")
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2")
        check("a line to grab", ln["kind"] == "shape" and ln["data"]["type"] == "line", ln["data"])
        d0 = dict(ln["data"]); u0 = U(pg)
        hx, hy = screen(pg, 1, d0["x2"], d0["y2"])
        ring_xy = "(() => { const r = document.getElementById('handleRing'); if (!r || r.hidden) return null; const b = r.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })()"
        pg.mouse.move(hx + 6, hy + 4); pg.wait_for_timeout(20)
        pen_plain = pg.evaluate(ring_xy)
        check("pen tool near a handle: no ring (pw-v4v, flipped: the plain pen never grabs)", pen_plain is None, pen_plain)
        tool(pg, "select")
        pg.mouse.move(hx + 6, hy + 4); pg.wait_for_timeout(20)
        plain = pg.evaluate(ring_xy)
        pg.mouse.move(hx + 300, hy + 200); pg.mouse.down(button="right"); pg.wait_for_timeout(20)   # the right button held, away from any handle
        far = pg.evaluate(ring_xy)
        pg.mouse.move(hx + 6, hy + 4); pg.wait_for_timeout(20)
        ring = pg.evaluate(ring_xy)
        check("handles are invisible until the pen is near", not far)
        check("select tool near a handle without the button: the ring shows on the handle (pw-v4v)", plain and near(plain, (hx, hy), 2), [plain, hx, hy])
        check("select tool within 12 px, the right button held: a small ring shows on the handle", ring and near(ring, (hx, hy), 2), [ring, hx, hy])
        pg.mouse.move(hx + 40, hy + 40); pg.wait_for_timeout(20)
        check("the ring hides when the pen moves away", pg.evaluate("document.getElementById('handleRing').hidden"))
        pg.mouse.up(button="right"); pg.wait_for_timeout(20)
        check("the right-button miss drew nothing and changed nothing", len(strokes(pg, "p2")) == 1 and last(pg, "p2")["data"] == d0 and U(pg) == u0)
        check("... and its contextmenu (on the release) flipped Select back to the pen (pw-v4v)", tool_is(pg) == "pen" and lit(pg) == ["pen"], [tool_is(pg), lit(pg)])
        grab_page(pg, 1, (d0["x2"] + 5, d0["y2"] + 3), (d0["x2"] + 105, d0["y2"] + 3))
        d1 = last(pg, "p2")["data"]
        check("dragging the end 100 px moves x2 by 100, y2 stays", abs(d1["x2"] - (d0["x2"] + 100)) <= 1.5 and abs(d1["y2"] - d0["y2"]) <= 1.5 and d1["x1"] == d0["x1"] and d1["y1"] == d0["y1"], [d0, d1])
        check("no new stroke drawn by the grab", len(strokes(pg, "p2")) == 1)
        check("one undo step per drag", U(pg) == u0 + 1)
        check("the <line> follows", elinfo(pg, 1, ln["id"]) and abs(float(pg.evaluate(f"document.querySelector('[data-id=\"{ln['id']}\"]').getAttribute('x2')")) - d1["x2"]) < 0.2)
        undo(pg)
        check("undo puts the end back", last(pg, "p2")["data"] == d0, [last(pg, "p2")["data"], d0])
        redo(pg)
        check("redo moves it again", last(pg, "p2")["data"] == d1)
        draw(pg, 1, [(200, 280), (260, 330), (330, 290)], steps=5)
        check("pen-down on the shape's middle (no handle) draws as normal", len(strokes(pg, "p2")) == 2 and last(pg, "p2")["kind"] == "pen")
        draw(pg, 1, rough_circle(500, 650, 80), steps=2, hold=650)
        c0 = last(pg, "p2")["data"]
        grab_page(pg, 1, (c0["cx"] + c0["r"], c0["cy"]), (c0["cx"] + c0["r"] + 40, c0["cy"]))
        c1 = last(pg, "p2")["data"]
        check("a circle's E handle changes its radius (centre stays)", c1["type"] == "circle" and abs(c1["r"] - (c0["r"] + 40)) <= 1.5 and c1["cx"] == c0["cx"] and c1["cy"] == c0["cy"], [c0, c1])
        draw(pg, 1, rough_square(150, 800, 160), steps=3, hold=650)
        q0 = last(pg, "p2")
        check("a rough square to grab", q0["kind"] == "shape" and q0["data"]["type"] == "rect", [q0["kind"], q0["data"]])
        q0 = q0["data"].get("points") or [[0, 0]] * 4
        grab_page(pg, 1, tuple(q0[2]), (q0[2][0] + 50, q0[2][1] + 30))
        q1 = last(pg, "p2")["data"]["points"]
        check("a rect's corner: the rect grows and stays upright, the opposite corner holds",
              q1[0] == q0[0] and abs(q1[2][0] - (q0[2][0] + 50)) <= 1.5 and abs(q1[2][1] - (q0[2][1] + 30)) <= 1.5 and q1[1][0] == q1[2][0] and q1[3][1] == q1[2][1] and q1[1][1] == q1[0][1], [q0, q1])
        tool(pg, "highlighter")
        n = len(strokes(pg, "p2"))
        drag_page(pg, 1, (c1["cx"], c1["cy"] - c1["r"]), (c1["cx"] + 60, c1["cy"] - c1["r"] - 40))
        check("the highlighter never grabs: it draws", len(strokes(pg, "p2")) == n + 1 and last(pg, "p2")["kind"] == "highlighter")
        top = last(pg, "p2")["data"]
        rdrag_page(pg, 1, (c1["cx"], c1["cy"] - c1["r"]), (c1["cx"] + 60, c1["cy"] - c1["r"] - 40))
        check("the highlighter with the right button: nothing at all (no stroke, no grab)", len(strokes(pg, "p2")) == n + 1 and last(pg, "p2")["data"] == top)
        check("... its contextmenu flips the highlighter to Select (pw-v4v)", tool_is(pg) == "select" and lit(pg) == ["select"], [tool_is(pg), lit(pg)])
        ctx.close()

        # ------------------------------------------------------------ restyle
        group[0] = "restyle"
        ctx, pg, e4 = fresh(b); errs += e4
        open_note(pg, "Restyle")
        draw(pg, 1, [(100, 200), (250, 210), (400, 200)])
        draw(pg, 1, [(100, 300), (250, 310), (400, 300)])
        draw(pg, 1, [(100, 400), (250, 410), (400, 400)])
        A, B, C = [s["id"] for s in strokes(pg, "p3")]
        old = strokes(pg, "p3")[0]["style"]
        pg.click("#tray .sw[data-colour='#FF3636']")
        pg.click("#tool-pen")                                  # already selected: the panel opens
        for _ in range(7): pg.locator("#toolPanel [aria-label='Width bigger']").click()
        pg.locator("#toolPanel .dash[data-dash='dashed']").click()
        pg.mouse.click(400, 10)
        st = pg.evaluate("window.__pw.tray()")["pen"]
        check("the pen is set to red, width 6, dashed", st == {"colour": "#FF3636", "width": 6, "dash": "dashed"}, st)
        tool(pg, "restyle")
        u0 = U(pg)
        tap_page(pg, 1, 250, 211)
        s = {x["id"]: x for x in strokes(pg, "p3")}
        check("a tap on a stroke: it takes red and 6, and keeps its own dash (solid stays solid under a dashed pen, pw-v4h)", s[A]["style"] == {"colour": "#FF3636", "width": 6, "dash": "solid", "opacity": 1}, s[A]["style"])
        check("the others are untouched", s[B]["style"] == old and s[C]["style"] == old)
        e = elinfo(pg, 1, A)
        check("its path shows it (stroke, width, and no dasharray: still solid)", e["stroke"] == "#FF3636" and e["width"] == "6" and e["dash"] is None, e)
        check("the points did not change", s[A]["data"]["points"][0] == [100, 200])
        check("one undo step per tap", U(pg) == u0 + 1)
        undo(pg)
        check("undo restores the old style", {x["id"]: x for x in strokes(pg, "p3")}[A]["style"] == old)
        redo(pg)
        check("redo restyles again", {x["id"]: x for x in strokes(pg, "p3")}[A]["style"]["colour"] == "#FF3636")
        u1 = U(pg)
        tap_page(pg, 1, 250, 211)
        check("restyling an already restyled stroke adds no step", U(pg) == u1)
        tap_page(pg, 1, 600, 800)
        check("a tap on empty paper adds no step", U(pg) == u1)
        pg.click("#tray .sw[data-colour='#2CB05F']")
        on = pg.evaluate("[...document.querySelectorAll('#tray .tool.on')].map(e => e.dataset.tool)")
        ts = pg.evaluate("window.__pw.tray()")
        check("a colour tap with restyle on: restyle stays, restyle's own colour changes, the pen's does not (fix round point 4)",
              on == ["restyle"] and ts["restyle"]["colour"] == "#2CB05F" and ts["pen"]["colour"] == "#FF3636", [on, ts["restyle"], ts["pen"]])
        drag_page(pg, 1, (250, 280), (250, 430), steps=12)
        s = {x["id"]: x for x in strokes(pg, "p3")}
        check("a drag across two strokes restyles both", s[B]["style"]["colour"] == "#2CB05F" and s[C]["style"]["colour"] == "#2CB05F" and s[A]["style"]["colour"] == "#FF3636")
        check("... in one undo step", U(pg) == u1 + 1)
        undo(pg)
        s = {x["id"]: x for x in strokes(pg, "p3")}
        check("one undo puts both back", s[B]["style"] == old and s[C]["style"] == old)
        # a highlighter stroke takes the highlighter's settings and moves to its opacity group
        tool(pg, "highlighter")
        draw(pg, 1, [(100, 600), (400, 604)])
        H = last(pg, "p3")["id"]
        pg.click("#tool-highlighter")
        pg.locator("#toolPanel [aria-label='Opacity bigger']").click(); pg.locator("#toolPanel [aria-label='Opacity bigger']").click()
        pg.mouse.click(400, 10)
        pg.click("#tray .sw[data-colour='#0D0DFF']")
        tool(pg, "restyle")
        tap_page(pg, 1, 250, 602)
        h = {x["id"]: x for x in strokes(pg, "p3")}[H]
        e = elinfo(pg, 1, H)
        check("a highlighter stroke takes the highlighter's colour, width and opacity", h["style"] == {"colour": "#0D0DFF", "width": 18, "dash": "solid", "opacity": 0.6}, h["style"])
        check("... and sits in the 0.6 .hlo group with no own opacity", e["parent"] == "hlo" and e["gp"] == "hl" and e["opacity"] == "0.6", e)
        check("the empty 0.4 group went", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.hlo[data-opacity=\"0.4\"]').length") == 0)
        undo(pg)
        check("undo puts it back in the 0.4 group", elinfo(pg, 1, H)["opacity"] == "0.4")
        tool(pg, "pen")
        draw(pg, 1, rough_circle(560, 850, 70), steps=2, hold=650)
        S_ = last(pg, "p3")
        tool(pg, "restyle")
        pg.click("#tray .sw[data-colour='#2CB05F']")           # restyle starts in the pen's red: green is a change
        tap_page(pg, 1, 560 + 70, 850)
        s2 = {x["id"]: x for x in strokes(pg, "p3")}[S_["id"]]
        check("a shape restyles too (pen colour and width, its own dash: drawn dashed, stays dashed)", S_["kind"] == "shape" and s2["style"]["colour"] == "#2CB05F" and s2["style"]["width"] == 6 and s2["style"]["dash"] == "dashed", s2["style"])
        check("... and stays the same shape", s2["data"] == S_["data"] and elinfo(pg, 1, S_["id"])["tag"] == "circle")
        # pw-v4h: restyle never changes the dash. The pen is red, 6, dashed here.
        tool(pg, "pen")
        draw(pg, 1, [(100, 500), (250, 510), (400, 500)])
        D = last(pg, "p3")["id"]
        draw(pg, 1, rough_line(560, 100, 400), hold=650)
        DL = last(pg, "p3")
        pg.click("#tool-pen")
        pg.locator("#toolPanel .dash[data-dash='solid']").click()
        for _ in range(2): pg.locator("#toolPanel [aria-label='Width bigger']").click()
        pg.mouse.click(400, 10)
        W = pg.evaluate("window.__pw.tray()")["pen"]["width"]
        draw(pg, 1, rough_line(700, 100, 400), hold=650)
        SL = last(pg, "p3")
        check("set up: a dashed freehand stroke, a dashed snapped line, a solid snapped line; the pen is now solid and wider",
              last(pg, "p3")["kind"] == "shape" and SL["style"]["dash"] == "solid" and DL["kind"] == "shape" and DL["style"]["dash"] == "dashed"
              and {x["id"]: x for x in strokes(pg, "p3")}[D]["style"]["dash"] == "dashed" and W > 6, [SL["style"], DL["style"], W])
        tool(pg, "restyle")
        pg.click("#tray .sw[data-colour='#2CB05F']")           # restyle starts in the pen's colour again: green is a change
        tap_page(pg, 1, 250, 510)
        tap_page(pg, 1, 250, 564)
        s3 = {x["id"]: x for x in strokes(pg, "p3")}
        check("a dashed stroke restyled with a solid pen panel stays dashed; colour and width still change",
              s3[D]["style"] == {"colour": "#2CB05F", "width": W, "dash": "dashed", "opacity": 1} and elinfo(pg, 1, D)["dash"] is not None, [s3[D]["style"], elinfo(pg, 1, D)])
        check("a dashed snapped line restyled with a solid pen panel stays dashed; colour and width still change, geometry too",
              s3[DL["id"]]["style"] == {"colour": "#2CB05F", "width": W, "dash": "dashed", "opacity": 1} and s3[DL["id"]]["data"] == DL["data"]
              and elinfo(pg, 1, DL["id"])["dash"] is not None, [s3[DL["id"]]["style"], elinfo(pg, 1, DL["id"])])
        tool(pg, "pen"); pg.click("#tool-pen")
        pg.locator("#toolPanel .dash[data-dash='dashed']").click(); pg.mouse.click(400, 10)
        tool(pg, "restyle")
        pg.click("#tray .sw[data-colour='#2CB05F']")
        tap_page(pg, 1, 250, 704)
        s4 = {x["id"]: x for x in strokes(pg, "p3")}
        check("a solid snapped line restyled with a dashed pen panel stays solid; colour and width still change",
              s4[SL["id"]]["style"] == {"colour": "#2CB05F", "width": W, "dash": "solid", "opacity": 1} and s4[SL["id"]]["data"] == SL["data"]
              and elinfo(pg, 1, SL["id"])["dash"] is None, [s4[SL["id"]]["style"], elinfo(pg, 1, SL["id"])])
        u2 = U(pg)
        tap_page(pg, 1, 250, 704)
        check("restyling again with the same settings adds no step (a dash-only difference no longer counts as a change)", U(pg) == u2)
        ctx.close()

        # ------------------------------------------------------------ rectangle select
        group[0] = "select"
        ctx, pg, e5 = fresh(b); errs += e5
        open_note(pg, "Select")
        draw(pg, 1, [(150, 200), (250, 220), (350, 200)])
        draw(pg, 1, [(150, 280), (250, 300), (350, 280)])
        draw(pg, 1, [(150, 600), (250, 620), (350, 600)])
        A, B, C = [s["id"] for s in strokes(pg, "p4")]
        P0 = {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")}
        tool(pg, "select")
        u0 = U(pg)
        drag_page(pg, 1, (120, 170), (380, 330))
        sl = sel(pg)
        check("a box around two of three: those two are selected", sl and sorted(sl["ids"]) == sorted([A, B]), sl)
        ui = selui(pg)
        check("a dashed blue box with four corner handles", ui["box"] and ui["dash"] and ui["corners"] == 4, ui)
        check("three chips above it: Copy, Duplicate and Delete (pw-v4o)", ui["chips"] == ["Copy", "Duplicate", "Delete"] and ui["chipsShown"], ui)
        cb = pg.locator(".selChips").bounding_box(); bb = pg.locator("svg.ink g.sel rect.selbox").bounding_box()
        check("the chips sit above the box", cb["y"] + cb["height"] <= bb["y"] + 1, [cb, bb])
        check("selecting is not an undo step", U(pg) == u0)
        if SHOTS and shots < 3:
            pg.screenshot(path=str(SHOTS / "u2b-select.png")); shots += 1
        drag_page(pg, 1, (250, 250), (300, 300))
        S1 = {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")}
        mv = lambda pts, dx, dy: [[round(x + dx, 1), round(y + dy, 1)] for x, y in pts]
        check("drag inside 50 px: the two move by 50, 50", S1[A] == mv(P0[A], 50, 50) and S1[B] == mv(P0[B], 50, 50), [S1[A][:2], P0[A][:2]])
        check("the third does not move", S1[C] == P0[C])
        check("one undo step for the move", U(pg) == u0 + 1)
        check("the selection stays on the moved strokes", sorted(sel(pg)["ids"]) == sorted([A, B]))
        check("no transform left on the paths", elinfo(pg, 1, A)["transform"] is None)
        undo(pg)
        check("undo puts them back", {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")} == P0)
        sb = sel(pg)
        check("the box follows the undo", sb and abs(sb["box"][0] - (150 - 1.25)) < 0.5, sb)
        redo(pg)
        check("redo moves them again", {s["id"]: s["data"]["points"] for s in strokes(pg, "p4")} == S1)
        u1 = U(pg)
        pg.locator(".selChips .chip[data-act='copy']").click(); pg.wait_for_timeout(30)
        all_ = strokes(pg, "p4")
        # pw-v4k: Copy fills the clipboard; it no longer duplicates on the spot (these checks are flipped)
        check("Copy adds nothing to the page (still the same three)", len(all_) == 3 and sorted(s["id"] for s in all_) == sorted([A, B, C]))
        check("Copy moves nothing", {s["id"]: s["data"]["points"] for s in all_} == S1)
        check("the selection stays on the same two", sorted(sel(pg)["ids"]) == sorted([A, B]))
        check("Copy is not an undo step", U(pg) == u1)
        check("the clipboard holds them (hasClip)", pg.evaluate("window.__pw.ink.hasClip()") is True)
        pg.locator(".selChips .chip[data-act='delete']").click(); pg.wait_for_timeout(30)
        check("Delete removes the selection (the two)", [s["id"] for s in strokes(pg, "p4")] == [C])
        check("Delete clears the selection and its chips", sel(pg) is None and not selui(pg)["g"] and not selui(pg)["chips"])
        check("Delete is one undo step", U(pg) == u1 + 1)
        undo(pg)
        check("undo Delete: the two are back", len(strokes(pg, "p4")) == 3)
        redo(pg)
        check("redo Delete: one left", len(strokes(pg, "p4")) == 1 and U(pg) == u1 + 1)
        undo(pg)
        check("undo again: three", len(strokes(pg, "p4")) == 3)
        # resize: scale about the opposite corner, aspect kept
        drag_page(pg, 1, (120, 570), (380, 650))
        check("box around the third only", sel(pg)["ids"] == [C])
        bx = sel(pg)["box"]
        q = pg.evaluate("(() => { const c = [...document.querySelectorAll('svg.ink g.sel circle.selh')].map(e => [+e.getAttribute('cx'), +e.getAttribute('cy')]); return c; })()")
        c2 = q[2]
        drag_page(pg, 1, (c2[0], c2[1]), (c2[0] + 100, c2[1] + 20), steps=12)
        rc = {s["id"]: s for s in strokes(pg, "p4")}[C]
        b0 = [min(p[0] for p in P0[C]), min(p[1] for p in P0[C]), max(p[0] for p in P0[C]), max(p[1] for p in P0[C])]
        b1 = [min(p[0] for p in rc["data"]["points"]), min(p[1] for p in rc["data"]["points"]), max(p[0] for p in rc["data"]["points"]), max(p[1] for p in rc["data"]["points"])]
        sx = (b1[2] - b1[0]) / (b0[2] - b0[0]); sy = (b1[3] - b1[1]) / (b0[3] - b0[1])
        check("a corner drag scales the stroke up", sx > 1.2, [sx, b0, b1])
        check("the aspect is kept", abs(sx - sy) < 0.03, [sx, sy])
        check("the opposite (top-left) corner holds", abs(b1[0] - b0[0]) < 3 and abs(b1[1] - b0[1]) < 3, [b0, b1])
        check("the ink width stays as it was (pw-v4g: a resize never thickens the line)", rc["style"]["width"] == 2.5 and elinfo(pg, 1, C)["width"] == "2.5", rc["style"])
        undo(pg)
        check("undo puts its size back", {s["id"]: s for s in strokes(pg, "p4")}[C]["data"]["points"] == P0[C])
        # touch any part (fix round point 2: the old "half inside" checks now follow the new rule)
        tap_page(pg, 1, 700, 1000)
        check("a tap outside clears the selection", sel(pg) is None and not selui(pg)["g"])
        drag_page(pg, 1, (140, 170), (290, 250))      # A spans x 150..350 (+50 moved): 200..400, so this box holds a quarter of it
        check("a stroke only a quarter inside is selected now (touch any part)", sel(pg) is not None and A in sel(pg)["ids"], sel(pg))
        tap_page(pg, 1, 700, 1000)
        drag_page(pg, 1, (500, 170), (700, 330))
        check("a box that touches nothing selects nothing", sel(pg) is None, sel(pg))
        drag_page(pg, 1, (190, 170), (330, 330))      # A after the move: x 200..400; 190..330 holds 65% of it
        sl = sel(pg)
        check("a stroke mostly inside is selected", sl and A in sl["ids"], sl)
        tool(pg, "pen")
        check("a tool change clears the selection", sel(pg) is None and not selui(pg)["g"])
        tool(pg, "select")
        drag_page(pg, 1, (120, 170), (420, 360))
        check("selected again", sel(pg) is not None)
        go_page(pg, 2)
        check("a page change clears the selection", sel(pg) is None and not selui(pg)["g"], pg.evaluate("window.__pw.current()"))
        go_page(pg, 1)
        if pg.locator("#pageList").is_visible(): pg.click("#plClose")
        drag_page(pg, 1, (120, 170), (420, 360))
        z0 = zoom(pg)
        r0 = float(pg.evaluate("document.querySelector('svg.ink g.sel circle.selh').getAttribute('r')"))
        pg.mouse.move(640, 400); pg.keyboard.down("Control"); pg.mouse.wheel(0, -200); pg.keyboard.up("Control"); pg.wait_for_timeout(120)
        z1 = zoom(pg)
        r1_ = float(pg.evaluate("document.querySelector('svg.ink g.sel circle.selh') ? document.querySelector('svg.ink g.sel circle.selh').getAttribute('r') : 0"))
        check("zooming keeps the corner handles the same size on screen", z1 != z0 and abs(r1_ * z1 - r0 * z0) < 0.2, [z0, z1, r0, r1_])
        tool(pg, "pen")
        check("the layer has only hl and pen again after the selection", pg.evaluate("[...document.querySelector('#stack .sheet[data-index=\"1\"] svg.ink').children].map(c => c.getAttribute('class')).join()") == "hl,pen")
        ctx.close()

        # ------------------------------------------------------------ erasers on shapes
        group[0] = "erasers"
        ctx, pg, e6 = fresh(b); errs += e6
        open_note(pg, "Erase")
        draw(pg, 1, rough_circle(300, 300, 90), steps=2, hold=650)
        draw(pg, 1, rough_line(600, 100, 500), hold=650)
        kinds = [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")]
        check("a circle and a line to erase", kinds == [("shape", "circle"), ("shape", "line")], kinds)
        u0 = U(pg)
        tool(pg, "area")
        drag_page(pg, 1, (300 + 90, 280), (300 + 90, 320), steps=4)
        kinds = [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")]
        # pw-v4l: flipped, the area eraser cuts a piece out of the circle and the rest stays as pen ink
        check("the area eraser over the circle cuts it: the circle turns into one pen piece, the line stays", kinds == [("pen", None), ("shape", "line")], kinds)
        check("one undo step", U(pg) == u0 + 1)
        undo(pg)
        check("undo brings the circle back whole", [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")] == [("shape", "circle"), ("shape", "line")])
        tool(pg, "eraser")
        tap_page(pg, 1, 300, 600 + 2)
        check("the stroke eraser removes the line whole", [(s["kind"], s["data"].get("type")) for s in strokes(pg, "p5")] == [("shape", "circle")])
        ctx.close()

        # ------------------------------------------------------------ pw-v4l: the area eraser cuts a piece out of a shape
        group[0] = "area eraser cuts shapes (pw-v4l)"
        ctx, pg, e30 = fresh(b); errs += e30
        open_note(pg, "Erase")
        def ids(pid): return {s["id"] for s in strokes(pg, pid)}
        def pbb(pts): xs = [q[0] for q in pts]; ys = [q[1] for q in pts]; return [min(xs), min(ys), max(xs), max(ys)]
        def plen(pts): return sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts)))
        info_lines.append(f"area eraser cuts shapes: zoom {zoom(pg)}")
        # 1. a pen circle bitten once on its right edge: one open piece, joined across the seam
        draw(pg, 1, rough_circle(300, 300, 90), steps=2, hold=650)
        draw(pg, 1, rough_line(600, 100, 500), hold=650)
        s0 = strokes(pg, "p5")
        check("a circle and a line to bite", [(s["kind"], s["data"].get("type")) for s in s0] == [("shape", "circle"), ("shape", "line")], [(s["kind"], s["data"].get("type")) for s in s0])
        circ, ln = s0[0], s0[1]
        cx, cy, r = circ["data"]["cx"], circ["data"]["cy"], circ["data"]["r"]
        u0 = U(pg); before = ids("p5")
        tool(pg, "area")
        drag_page(pg, 1, (cx + r, cy - 40), (cx + r, cy + 40), steps=8)
        s1 = strokes(pg, "p5"); new = [s for s in s1 if s["id"] not in before]
        check("the circle shape is gone", not any(s["kind"] == "shape" and s["data"].get("type") == "circle" for s in s1), [(s["kind"], s["data"].get("type")) for s in s1])
        pc = new[0] if len(new) == 1 else None
        check("exactly ONE new record, kind pen, over 100 points", pc is not None and pc["kind"] == "pen" and len(pc["data"]["points"]) > 100,
              [(s["kind"], len(s["data"].get("points", []))) for s in new])
        if pc:
            pts = pc["data"]["points"]
            check("the piece is open: its ends are more than 3 px apart (joined across the seam)", not near(pts[0], pts[-1], 3), [pts[0], pts[-1]])
            check("the bite: the piece's right edge is at least 8 px left of cx + r", pbb(pts)[2] <= cx + r - 8, [pbb(pts)[2], cx + r])
            check("the piece keeps the circle's page, seq and style", pc["page_id"] == "p5" and pc["seq"] == circ["seq"] and pc["style"] == circ["style"], [pc["seq"], circ["seq"], pc["style"], circ["style"]])
            on = all(abs(math.hypot(q[0] - cx, q[1] - cy) - r) < 0.6 for q in pts)
            gaps = max(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts)))
            check("its points sit on the circle, no gap over 3 px (plus the 0.1 px rounding)", on and gaps <= 3.15, gaps)
        lnow = [s for s in s1 if s["id"] == ln["id"]]
        check("the line is untouched", len(lnow) == 1 and lnow[0] == ln)
        check("exactly one undo step", U(pg) == u0 + 1, [u0, U(pg)])
        e = elinfo(pg, 1, pc["id"]) if pc else None
        check("the piece is a <path> in g.pen", e and e["tag"] == "path" and e["parent"] == "pen", e)
        undo(pg)
        s2 = strokes(pg, "p5")
        check("undo: the circle is back as a shape with the same data", [(s["kind"], s["data"].get("type")) for s in s2] == [("shape", "circle"), ("shape", "line")] and s2[0]["data"] == circ["data"] and s2[0]["id"] == circ["id"],
              [(s["kind"], s["data"].get("type")) for s in s2])
        check("undo: its circle element is drawn again", (elinfo(pg, 1, circ["id"]) or {}).get("tag") == "circle")
        redo(pg)
        s3 = strokes(pg, "p5")
        check("redo: the piece again", pc is not None and [s["id"] for s in s3] == [pc["id"], ln["id"]] and s3[0]["data"] == pc["data"], [s["id"] for s in s3])
        check("the stored page matches", [s["id"] for s in (idle(pg) or stored(pg, "p5"))] == [s["id"] for s in s3])

        # 2. a line bitten in its middle: two pen pieces, each shorter, both ends kept
        u0 = U(pg); before = ids("p5")
        mx = (ln["data"]["x1"] + ln["data"]["x2"]) / 2; my = (ln["data"]["y1"] + ln["data"]["y2"]) / 2
        drag_page(pg, 1, (mx, my - 30), (mx, my + 30), steps=6)
        s4 = strokes(pg, "p5"); new = [s for s in s4 if s["id"] not in before]
        L0 = math.hypot(ln["data"]["x2"] - ln["data"]["x1"], ln["data"]["y2"] - ln["data"]["y1"])
        check("the line shape is gone, two pen pieces in its place", not any(s["id"] == ln["id"] for s in s4) and len(new) == 2 and all(s["kind"] == "pen" for s in new),
              [(s["kind"], s["data"].get("type")) for s in new])
        if len(new) == 2:
            check("each piece is shorter than the line", all(plen(s["data"]["points"]) < L0 - 10 for s in new), [plen(s["data"]["points"]) for s in new] + [L0])
            ends = [s["data"]["points"][0] for s in new] + [s["data"]["points"][-1] for s in new]
            check("both ends of the line are kept", any(near(q, (ln["data"]["x1"], ln["data"]["y1"]), 0.2) for q in ends) and any(near(q, (ln["data"]["x2"], ln["data"]["y2"]), 0.2) for q in ends), ends)
        check("one undo step for the line", U(pg) == u0 + 1)

        # 7. rubbing INSIDE a circle: nothing changes, no undo step
        tool(pg, "pen")
        draw(pg, 1, rough_circle(560, 860, 90), steps=2, hold=650)
        c2 = last(pg, "p5")
        check("a second circle to rub inside", c2["kind"] == "shape" and c2["data"]["type"] == "circle", [c2["kind"], c2["data"]])
        u0 = U(pg); snap0 = strokes(pg, "p5")
        tool(pg, "area")
        drag_page(pg, 1, (c2["data"]["cx"] - 30, c2["data"]["cy"]), (c2["data"]["cx"] + 30, c2["data"]["cy"] + 10), steps=6)
        check("rubbing inside the circle changes nothing", strokes(pg, "p5") == snap0)
        check("and adds no undo step", U(pg) == u0, [u0, U(pg)])

        # 6. the stroke eraser on a circle still removes it whole
        tool(pg, "eraser")
        u0 = U(pg); n0 = len(strokes(pg, "p5"))
        tap_page(pg, 1, c2["data"]["cx"] + c2["data"]["r"], c2["data"]["cy"])
        s5 = strokes(pg, "p5")
        check("the stroke eraser removes the circle whole (one record gone, nothing added)", len(s5) == n0 - 1 and not any(s["id"] == c2["id"] for s in s5) and {s["id"] for s in s5} <= {s["id"] for s in snap0}, len(s5))
        check("one undo step for the stroke eraser", U(pg) == u0 + 1)
        check("no page errors in the pen part", not e30, e30)
        ctx.close()

        # 3. a highlighter circle: its piece is highlighter ink in the .hlo group
        ctx, pg, e31 = fresh(b); errs += e31
        open_note(pg, "Erase")
        tool(pg, "highlighter")
        draw(pg, 1, rough_circle(300, 300, 90), steps=2, hold=650)
        h = last(pg, "p5")
        check("a highlighter circle", h["kind"] == "shape" and h["data"]["type"] == "circle" and h["style"]["opacity"] < 1, [h["kind"], h["data"], h["style"]])
        tool(pg, "area")
        drag_page(pg, 1, (h["data"]["cx"] + h["data"]["r"], h["data"]["cy"] - 40), (h["data"]["cx"] + h["data"]["r"], h["data"]["cy"] + 40), steps=8)
        s6 = strokes(pg, "p5")
        hp = s6[0] if len(s6) == 1 else None
        check("one piece, kind highlighter, same opacity and style", hp is not None and hp["kind"] == "highlighter" and hp["style"]["opacity"] == h["style"]["opacity"] and hp["style"] == h["style"],
              [(s["kind"], s["style"]) for s in s6])
        e = elinfo(pg, 1, hp["id"]) if hp else None
        check("its path sits in the page's .hl .hlo group", e and e["tag"] == "path" and e["parent"] == "hlo" and e["gp"] == "hl" and e["opacity"] == str(h["style"]["opacity"]), e)
        check("the .hlo path is in .hl .hlo (DOM query)", hp is not None and pg.evaluate(f"!!document.querySelector('#stack .sheet[data-index=\"1\"] svg.ink g.hl g.hlo path[data-id=\"{hp['id'] if hp else ''}\"]')"))

        # 4. a dashed pen circle: the piece keeps the dash
        pg.click("#tool-pen")
        if pg.locator("#toolPanel").is_hidden(): pg.click("#tool-pen")
        pg.click("#toolPanel .dash[data-dash='dashed']"); pg.click("#noteName"); pg.keyboard.press("Escape")
        draw(pg, 1, rough_circle(560, 860, 90), steps=2, hold=650)
        dc = last(pg, "p5")
        check("a dashed pen circle", dc["kind"] == "shape" and dc["data"]["type"] == "circle" and dc["style"]["dash"] == "dashed", [dc["kind"], dc["data"], dc["style"]])
        before = ids("p5")
        tool(pg, "area")
        drag_page(pg, 1, (dc["data"]["cx"] + dc["data"]["r"], dc["data"]["cy"] - 40), (dc["data"]["cx"] + dc["data"]["r"], dc["data"]["cy"] + 40), steps=8)
        new = [s for s in strokes(pg, "p5") if s["id"] not in before]
        check("its piece keeps style.dash (dashed), kind pen", len(new) == 1 and new[0]["kind"] == "pen" and new[0]["style"]["dash"] == "dashed", [(s["kind"], s["style"]) for s in new])
        e = elinfo(pg, 1, new[0]["id"]) if len(new) == 1 else None
        check("and draws dashed", e and e["dash"] not in (None, "none"), e)
        pg.click("#tool-pen")
        if pg.locator("#toolPanel").is_hidden(): pg.click("#tool-pen")
        pg.click("#toolPanel .dash[data-dash='solid']"); pg.click("#noteName"); pg.keyboard.press("Escape")

        # 5. an arrow bitten on its shaft: no shape left, shaft pieces plus the head as ink, through the tip
        tool(pg, "pen")
        draw(pg, 1, rough_arrow(), steps=3, hold=650)
        ar = last(pg, "p5")
        check("an arrow to bite", ar["kind"] == "shape" and ar["data"]["type"] == "arrow", [ar["kind"], ar["data"]])
        u0 = U(pg); before = ids("p5")
        tool(pg, "area")
        ax = (ar["data"]["x1"] + ar["data"]["x2"]) / 2; ay = (ar["data"]["y1"] + ar["data"]["y2"]) / 2
        drag_page(pg, 1, (ax, ay - 30), (ax, ay + 30), steps=6)
        s7 = strokes(pg, "p5"); new = [s for s in s7 if s["id"] not in before]
        check("the arrow shape is gone, no record of kind shape left", not any(s["kind"] == "shape" for s in s7), [(s["kind"], s["data"].get("type")) for s in s7])
        check("at least 3 new records (two shaft pieces and the head), all pen", len(new) >= 3 and all(s["kind"] == "pen" for s in new), [(s["kind"], len(s["data"]["points"])) for s in new])
        tip = (ar["data"]["x2"], ar["data"]["y2"])
        heads = [s for s in new if any(near(q, tip, 1) for q in s["data"]["points"][1:-1])]
        check("the head piece's points pass through the arrow's tip (within 1 px)", len(heads) == 1, [len(heads)])
        check("one undo step for the arrow", U(pg) == u0 + 1)
        undo(pg)
        check("undo: the arrow is back as a shape", any(s["id"] == ar["id"] and s["data"] == ar["data"] for s in strokes(pg, "p5")))
        check("no page errors in the highlighter, dash and arrow part", not e31, e31)
        ctx.close()



        # ------------------------------------------------------------ fix round point 1: real pen events on a handle
        group[0] = "pen handles (fix 1)"
        ctx, pg, e8 = fresh(b); errs += e8
        open_note(pg, "Handles")
        pen = Pen(ctx, pg)
        check("the ink layer lets the pen through (svg.ink pointer-events: none)",
              pg.evaluate("getComputedStyle(document.querySelector('#stack .sheet svg.ink')).pointerEvents") == "none")
        check("the shape handle reach is 20 px, selection corners 12 px",
              pg.evaluate("import('./js/ink.js').then(m => [m.HANDLE_REACH, m.GRAB])") == [20, 12])
        pg.evaluate("""() => { window.__pl = []; const d = document.getElementById('desk');
          for (const t of ['pointerdown', 'pointerup']) d.addEventListener(t, (e) => window.__pl.push(t + ':' + e.pointerType), true); }""")
        pen.stroke([screen(pg, 1, *q) for q in rough_line(300, 150, 450)], hold=650)
        ln = last(pg, "p2")
        check("a line drawn and held with the PEN snaps", ln and ln["kind"] == "shape" and ln["data"]["type"] == "line", ln)
        check("the desk saw pen events (pointerType pen)", pg.evaluate("window.__pl").count("pointerdown:pen") == 1, pg.evaluate("window.__pl"))
        d0 = dict(ln["data"]); u0 = U(pg)
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        hit = pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e.closest('svg.ink') ? 'svg.ink' : (e.id || e.className); }", [ex, ey])
        check("the element under the line's end is not the ink layer (the desk gets the pen)", hit != "svg.ink", hit)
        ring_on = lambda: pg.evaluate("(() => { const r = document.getElementById('handleRing'); return !!r && !r.hidden; })()")
        pen.hover(ex + 16, ey, 2); pen16b = ring_on()
        pen.hover(ex + 16, ey); pen16 = ring_on()
        check("pen tool hovering 16 px from the end, button held or not: no ring (pw-v4v, flipped)", not pen16b and not pen16, [pen16b, pen16])
        tool(pg, "select")
        pen.hover(ex + 26, ey, 2); off26 = ring_on()
        pen.hover(ex + 16, ey, 2); on16 = ring_on()
        pen.hover(ex + 16, ey); bare16 = ring_on()
        check("select tool, pen hovering 16 px from the end, button held: the ring shows", on16)
        check("select tool, pen hovering 26 px away, button held: no ring", not off26)
        check("select tool, pen hovering 16 px from the end, no button: the ring shows too", bare16)
        pen.stroke([(ex + 16, ey + 2), (ex + 116, ey + 2)])
        d1 = last(pg, "p2")["data"]
        check("select tool, pen down 16 px from the end grabs it: x2 moves 100, y2 stays (pw-v4v: was the pen button)", abs(d1["x2"] - (d0["x2"] + 100)) <= 1.5 and abs(d1["y2"] - d0["y2"]) <= 1.5, [d0, d1])
        check("the other end stays put (the gradient changes)", d1["x1"] == d0["x1"] and d1["y1"] == d0["y1"], d1)
        check("no stroke drawn by the grab, one undo step", len(strokes(pg, "p2")) == 1 and U(pg) == u0 + 1, [len(strokes(pg, "p2")), U(pg), u0])
        sx, sy = screen(pg, 1, d1["x1"], d1["y1"])
        first = pg.evaluate(SYNTH_JS, [[[sx - 8, sy + 6], [sx - 8, sy + 46], [sx - 8, sy + 86]], 0])
        d2 = last(pg, "p2")["data"]
        check("select tool, synthetic pen PointerEvents on the start end: x1 y1 move, x2 y2 stay", abs(d2["y1"] - (d1["y1"] + 80)) <= 1.5 and d2["x2"] == d1["x2"] and d2["y2"] == d1["y2"], [first, d1, d2])
        tool(pg, "pen")
        n = len(strokes(pg, "p2"))
        ex, ey = screen(pg, 1, d2["x2"], d2["y2"])
        pen.stroke([(ex + 30, ey + 30), (ex + 90, ey + 60)])
        check("pen down 30 px from any handle draws as normal", len(strokes(pg, "p2")) == n + 1 and last(pg, "p2")["kind"] == "pen")
        pen.stroke([(ex + 10, ey + 2), (ex + 70, ey + 2)])
        check("pen tool, pen down 10 px from the end draws too (pw-v4v), the line unchanged", len(strokes(pg, "p2")) == n + 2 and last(pg, "p2")["kind"] == "pen"
              and [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"] == d2)
        ctx.close()

        # ------------------------------------------------------------ fix round point 2: touch any part
        group[0] = "touch any part (fix 2)"
        ctx, pg, e9 = fresh(b); errs += e9
        open_note(pg, "Select")
        draw(pg, 1, [(100, 150), (250, 152), (400, 150)])
        draw(pg, 1, [(100, 300), (300, 300)])
        draw(pg, 1, [(450, 340), (560, 230)], steps=1)              # a diagonal: its two points stay outside the box below
        draw(pg, 1, rough_circle(300, 800, 90), steps=2, hold=650)
        S1, S2, D, CI = [s["id"] for s in strokes(pg, "p4")]
        check("a diagonal of just two points, and a circle", len(strokes(pg, "p4")[2]["data"]["points"]) == 2 and strokes(pg, "p4")[3]["data"]["type"] == "circle",
              [strokes(pg, "p4")[2]["data"], strokes(pg, "p4")[3]["data"].get("type")])
        tool(pg, "select")
        drag_page(pg, 1, (370, 100), (520, 200))                     # holds x 370..400 of 100..400: 10%
        check("a stroke 10% inside the box is taken (whole)", sel(pg) and sel(pg)["ids"] == [S1], sel(pg))
        tap_page(pg, 1, 700, 1050)
        drag_page(pg, 1, (520, 250), (650, 350))                     # only the diagonal's middle crosses this box's corner
        check("a diagonal that only crosses the box's corner is taken", sel(pg) and sel(pg)["ids"] == [D], sel(pg))
        tap_page(pg, 1, 700, 1050)
        drag_page(pg, 1, (330, 260), (450, 290))                     # S2 ends at x 300, y 300: fully outside
        check("a stroke fully outside is not taken", sel(pg) is None, sel(pg))
        drag_page(pg, 1, (370, 700), (500, 900))                     # catches the circle's right side
        check("a box over part of a circle's outline takes the circle", sel(pg) and sel(pg)["ids"] == [CI], sel(pg))
        tap_page(pg, 1, 700, 1050)
        drag_page(pg, 1, (260, 760), (340, 840))                     # inside the circle, touching no ink
        check("a box inside the circle that touches no outline takes nothing", sel(pg) is None, sel(pg))
        drag_page(pg, 1, (50, 100), (700, 1000))
        check("a box round everything takes all four", sel(pg) and sorted(sel(pg)["ids"]) == sorted([S1, S2, D, CI]), sel(pg))
        src = pg.evaluate("(u) => fetch(u).then(r => r.text())", "./js/ink.js")
        check("no half rule left in inBox", "0.5 * (x1 - x0)" not in src)
        ctx.close()

        # ------------------------------------------------------------ fix round point 3: the highlighter snaps too
        group[0] = "highlighter snap (fix 3)"
        ctx, pg, e10 = fresh(b); errs += e10
        open_note(pg, "Snap")
        tool(pg, "highlighter")
        u0 = U(pg)
        draw(pg, 1, rough_line(), hold=650)
        r = last(pg, "p1")
        check("a held highlighter line becomes shape/line", r["kind"] == "shape" and r["data"]["type"] == "line", [r["kind"], r["data"]])
        check("it keeps the highlighter's look (colour, width, solid, opacity)", r["style"] == {"colour": "#FFC107", "width": 18, "dash": "solid", "opacity": 0.4}, r["style"])
        e = elinfo(pg, 1, r["id"])
        check("it renders inside the highlighter layer: g.hlo (0.4) under g.hl", e["tag"] == "line" and e["parent"] == "hlo" and e["gp"] == "hl" and e["opacity"] == "0.4", e)
        own = pg.evaluate(f"(() => {{ const e = document.querySelector('[data-id=\"{r['id']}\"]'); return [e.getAttribute('stroke-opacity'), e.getAttribute('stroke-linecap')]; }})()")
        check("no own opacity on it (the group does it), round ends", own == [None, "round"], own)
        check("nothing in g.pen", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 0)
        pg.wait_for_timeout(200)
        check("after the fade only the shape is in its .hlo group", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.hlo > *').length") == 1)
        check("a highlighter snap is ONE undo step", U(pg) == u0 + 1, [u0, U(pg)])
        undo(pg)
        check("undo takes it away (and its empty group)", len(strokes(pg, "p1")) == 0 and pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.hlo').length") == 0)
        redo(pg)
        check("redo brings it back in its .hlo group", elinfo(pg, 1, r["id"])["parent"] == "hlo")
        draw(pg, 1, rough_arrow(), steps=3, hold=650)
        a = last(pg, "p1")
        check("a highlighter arrow is stored as a line", a["kind"] == "shape" and a["data"]["type"] == "line", a["data"])
        if a["data"].get("type") == "line":
            check("... from the start to the V's tip", near((a["data"]["x1"], a["data"]["y1"]), (120, 980), 6) and near((a["data"]["x2"], a["data"]["y2"]), (420, 980), 6), a["data"])
        draw(pg, 1, rough_square(), steps=3, hold=650)
        q = last(pg, "p1")
        check("a held highlighter square: rect in the .hlo group", q["kind"] == "shape" and q["data"]["type"] == "rect" and elinfo(pg, 1, q["id"])["parent"] == "hlo", [q["kind"], q["data"]])
        draw(pg, 1, rough_circle(), steps=2, hold=650)
        c = last(pg, "p1")
        check("a held highlighter circle: circle in the .hlo group", c["kind"] == "shape" and c["data"]["type"] == "circle" and elinfo(pg, 1, c["id"])["parent"] == "hlo", [c["kind"], c["data"]])
        draw(pg, 1, [(450, 1080), (700, 1082)], steps=8, hold=0)
        check("a highlighter stroke lifted at once stays a highlighter stroke", last(pg, "p1")["kind"] == "highlighter")
        idle(pg)
        pg.reload(); ready(pg); open_note(pg, "Snap")
        check("after a reload the highlighter shapes are still in the .hlo group",
              all(elinfo(pg, 1, x)["parent"] == "hlo" for x in (r["id"], q["id"], c["id"])) and pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 0)
        # its handles: the select tool grabs a highlighter line's end like any shape's (pw-v4v: was the pen tool)
        tool(pg, "pen")
        L = {x["id"]: x for x in strokes(pg, "p1")}[r["id"]]["data"]
        grab_page(pg, 1, (L["x2"] + 4, L["y2"]), (L["x2"] + 64, L["y2"] + 30))
        L2 = {x["id"]: x for x in strokes(pg, "p1")}[r["id"]]["data"]
        check("the select tool grabs a highlighter line's end: only that end moves", abs(L2["x2"] - (L["x2"] + 60)) <= 1.5 and L2["x1"] == L["x1"] and elinfo(pg, 1, r["id"])["parent"] == "hlo", [L, L2])
        # restyle: the highlighter's settings, and it may change opacity group
        pg.click("#tool-highlighter"); pg.click("#tool-highlighter")
        pg.locator("#toolPanel [aria-label='Opacity bigger']").click(); pg.locator("#toolPanel [aria-label='Opacity bigger']").click()
        pg.mouse.click(400, 10)
        tool(pg, "restyle")
        pg.click("#tray .sw[data-colour='#FF3636']")
        cx_, cy_ = {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]["data"]["cx"], {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]["data"]["cy"]
        rr = {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]["data"]["r"]
        tap_page(pg, 1, cx_ + rr, cy_)
        c2 = {x["id"]: x for x in strokes(pg, "p1")}[c["id"]]
        e = elinfo(pg, 1, c["id"])
        check("restyle on a highlighter circle: red, the highlighter's width and new opacity, still a circle",
              c2["style"] == {"colour": "#FF3636", "width": 18, "dash": "solid", "opacity": 0.6} and c2["data"]["type"] == "circle", c2["style"])
        check("... and it moved to the 0.6 .hlo group", e["parent"] == "hlo" and e["opacity"] == "0.6" and e["tag"] == "circle", e)
        tool(pg, "eraser")
        n = len(strokes(pg, "p1"))
        P0 = q["data"]["points"][0]
        tap_page(pg, 1, P0[0] + 40, P0[1])
        check("the stroke eraser takes a highlighter rect whole", len(strokes(pg, "p1")) == n - 1 and q["id"] not in [x["id"] for x in strokes(pg, "p1")])
        ctx.close()

        # ------------------------------------------------------------ fix round point 4: restyle has its own colour
        group[0] = "restyle colour (fix 4)"
        ctx, pg, e11 = fresh(b); errs += e11
        open_note(pg, "Restyle")
        draw(pg, 1, [(100, 200), (250, 210), (400, 200)])
        PS = last(pg, "p3")["id"]
        tool(pg, "highlighter")
        draw(pg, 1, [(100, 400), (400, 404)])
        HS = last(pg, "p3")["id"]
        tool(pg, "restyle")
        ts = pg.evaluate("window.__pw.tray()")
        check("restyle picked after the highlighter: its colour starts as the highlighter's", ts["restyle"]["colour"] == "#FFC107", ts.get("restyle"))
        pg.click("#tray .sw[data-colour='#FF3636']")
        ts = pg.evaluate("window.__pw.tray()")
        check("a colour tap with restyle on: only restyle's colour changes", ts["restyle"]["colour"] == "#FF3636" and ts["pen"]["colour"] == "#000000" and ts["highlighter"]["colour"] == "#FFC107", [ts["restyle"], ts["pen"], ts["highlighter"]])
        check("the swatch ring shows the restyle colour", pg.evaluate("[...document.querySelectorAll('#tray .sw.on')].map(e => e.dataset.colour)") == ["#FF3636"])
        u0 = U(pg)
        tap_page(pg, 1, 250, 211)
        p_ = {x["id"]: x for x in strokes(pg, "p3")}[PS]
        check("a tap on a PEN stroke: red at the pen's width and dash", p_["style"] == {"colour": "#FF3636", "width": 2.5, "dash": "solid", "opacity": 1}, p_["style"])
        tap_page(pg, 1, 250, 402)
        h_ = {x["id"]: x for x in strokes(pg, "p3")}[HS]
        check("a tap on a highlight: red, still a highlight (width 18, opacity 0.4, in .hlo)",
              h_["style"] == {"colour": "#FF3636", "width": 18, "dash": "solid", "opacity": 0.4} and elinfo(pg, 1, HS)["parent"] == "hlo", h_["style"])
        check("two taps, two undo steps", U(pg) == u0 + 2)
        ts = pg.evaluate("window.__pw.tray()")
        check("the pen's and the highlighter's own colours did not move", ts["pen"]["colour"] == "#000000" and ts["highlighter"]["colour"] == "#FFC107", [ts["pen"], ts["highlighter"]])
        # the spare slot while restyle is on: it sets the restyle colour
        pg.click("#tray .spec")
        pg.wait_for_selector("#specPicker:not([hidden])")
        cell = pg.locator("#specPicker polygon[data-cell='4-0']")
        cc = cell.get_attribute("data-colour")
        bb = cell.bounding_box(); pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        pg.click("#specPicker .done")
        ts = pg.evaluate("window.__pw.tray()")
        check("the spare slot's pick with restyle on sets the restyle colour (pen unchanged)", ts["restyle"]["colour"] == cc and ts["pen"]["colour"] == "#000000" and ts["tool"] == "restyle", [cc, ts["restyle"], ts["pen"], ts["tool"]])
        tap_page(pg, 1, 250, 211)
        check("... and a tap gives the stroke that colour", {x["id"]: x for x in strokes(pg, "p3")}[PS]["style"]["colour"] == cc)
        idle(pg)
        check("restyle's colour is saved with the tray", json.loads(pg.evaluate("localStorage.getItem('pw.tools')")).get("restyle", {}).get("colour") == cc)
        tool(pg, "pen")
        check("back to the pen: the ring shows the pen's own black", pg.evaluate("[...document.querySelectorAll('#tray .sw.on')].map(e => e.dataset.colour)") == ["#000000"])
        draw(pg, 1, [(100, 600), (400, 610)])
        check("the pen draws in its own colour, unchanged", last(pg, "p3")["style"]["colour"] == "#000000")
        ctx.close()

        # ------------------------------------------------------------ fix round point 5: restyle on a selection
        group[0] = "selection restyle (fix 5)"
        ctx, pg, e12 = fresh(b); errs += e12
        open_note(pg, "Select")
        pg.click("#tool-pen")                                    # pen dashed for one stroke, then back to solid
        pg.locator("#toolPanel .dash[data-dash='dashed']").click(); pg.mouse.click(400, 10)
        draw(pg, 1, [(150, 200), (250, 220), (350, 200)])
        A = last(pg, "p4")["id"]
        pg.click("#tool-pen"); pg.locator("#toolPanel .dash[data-dash='solid']").click(); pg.mouse.click(400, 10)
        tool(pg, "highlighter")
        draw(pg, 1, [(150, 300), (350, 304)])
        H = last(pg, "p4")["id"]
        draw(pg, 1, rough_line(400, 150, 350), hold=650)
        S = last(pg, "p4")["id"]
        tool(pg, "pen")
        draw(pg, 1, [(150, 800), (250, 820), (350, 800)])
        C = last(pg, "p4")["id"]
        before = {x["id"]: x for x in strokes(pg, "p4")}
        check("set up: a dashed pen stroke, a highlight, a highlighter shape, one more pen stroke",
              before[A]["style"]["dash"] == "dashed" and before[H]["kind"] == "highlighter" and before[S]["kind"] == "shape" and before[S]["style"]["opacity"] == 0.4, [before[A]["style"], before[S]["kind"]])
        tool(pg, "select")
        drag_page(pg, 1, (120, 170), (380, 430))
        check("the box takes the three", sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, H, S]), sel(pg))
        u0 = U(pg)
        pg.click("#tray .sw[data-colour='#FF0C84']")
        now = {x["id"]: x for x in strokes(pg, "p4")}
        check("a colour tap recolours every selected stroke", all(now[i]["style"]["colour"] == "#FF0C84" for i in (A, H, S)), [now[i]["style"] for i in (A, H, S)])
        check("... keeping width, dash, opacity and geometry", all({**before[i]["style"], "colour": "#FF0C84"} == now[i]["style"] and before[i]["data"] == now[i]["data"] for i in (A, H, S)))
        check("the highlight and the highlighter shape stay in the .hlo group", elinfo(pg, 1, H)["parent"] == "hlo" and elinfo(pg, 1, S)["parent"] == "hlo")
        check("the stroke outside the selection is untouched", now[C]["style"] == before[C]["style"])
        check("ONE undo step", U(pg) == u0 + 1, [u0, U(pg)])
        ts = pg.evaluate("window.__pw.tray()")
        check("select stays the tool, the selection and its box stay", ts["tool"] == "select" and sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, H, S]) and selui(pg)["box"], [ts["tool"], sel(pg)])
        check("the pen's colour did not become pink", ts["pen"]["colour"] == "#000000" and ts["highlighter"]["colour"] == "#FFC107", [ts["pen"], ts["highlighter"]])
        undo(pg)
        check("undo puts every colour back (the selection follows)", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"] == before[i]["style"] for i in (A, H, S)) and sel(pg) is not None)
        redo(pg)
        check("redo recolours again", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"]["colour"] == "#FF0C84" for i in (A, H, S)))
        # the full restyle: tap Restyle while the selection exists (the pen is black 2.5 solid, the highlighter amber 18 at 0.4)
        u1 = U(pg)
        tool(pg, "restyle")
        now = {x["id"]: x for x in strokes(pg, "p4")}
        check("tapping Restyle restyles the selection: pen colour and width for the pen stroke, its dash stays dashed (pw-v4h)", now[A]["style"] == {"colour": "#000000", "width": 2.5, "dash": "dashed", "opacity": 1}, now[A]["style"])
        check("... and the dashed stroke still draws dashed", elinfo(pg, 1, A)["dash"] is not None, elinfo(pg, 1, A))
        check("... highlighter settings for the highlight and the highlighter shape (colour from restyle)",
              all(now[i]["style"] == {"colour": "#000000", "width": 18, "dash": "solid", "opacity": 0.4} for i in (H, S)), [now[H]["style"], now[S]["style"]])
        check("one undo step, the selection kept, select still the tool, restyle not entered",
              U(pg) == u1 + 1 and sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, H, S]) and pg.evaluate("window.__pw.tray()")["tool"] == "select"
              and pg.evaluate("[...document.querySelectorAll('#tray .tool.on')].map(e => e.dataset.tool)") == ["select"], [U(pg), u1, sel(pg)])
        undo(pg)
        check("undo restores the pink", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"]["colour"] == "#FF0C84" for i in (A, H, S)) and sel(pg) is not None)
        # the spare slot on a selection
        pg.click("#tray .spec"); pg.wait_for_selector("#specPicker:not([hidden])")
        cell = pg.locator("#specPicker polygon[data-cell='3-2']"); cc = cell.get_attribute("data-colour")
        bb = cell.bounding_box(); pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        pg.click("#specPicker .done")
        check("the spare slot's pick recolours the selection too", all({x["id"]: x for x in strokes(pg, "p4")}[i]["style"]["colour"] == cc for i in (A, H, S))
              and pg.evaluate("window.__pw.tray()")["tool"] == "select" and sel(pg) is not None, cc)
        tool(pg, "eraser")
        check("any other tool change still clears the selection", sel(pg) is None)
        tool(pg, "select")
        pg.click("#tray .sw[data-colour='#2CB05F']")
        ts = pg.evaluate("window.__pw.tray()")
        check("a colour tap with select on and NO selection hands back the last ink tool (as before)", ts["tool"] == "pen" and ts["pen"]["colour"] == "#2CB05F", [ts["tool"], ts["pen"]])
        ctx.close()

        # ------------------------------------------------------------ pw-v4v: the plain pen never grabs; the SELECT tool drags a shape's end
        # This group rewrites the pw-v4e "plain pen grabs" and "pen button press" groups. Every old scenario is still here,
        # flipped where the plain pen (or the right button) used to grab: the pen tool now draws there, the select tool grabs.
        group[0] = "select drags an end (pw-v4v)"
        ctx, pg, e9 = fresh(b); errs += e9
        open_note(pg, "Handles")
        pen = Pen(ctx, pg)
        z = zoom(pg)
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2"); d0 = dict(ln["data"]); u0 = U(pg)
        check("a line to work with", ln["kind"] == "shape" and ln["data"]["type"] == "line", ln["data"])
        L = lambda: [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"]
        ring_on = lambda: pg.evaluate("(() => { const r = document.getElementById('handleRing'); return !!r && !r.hidden; })()")
        n = len(strokes(pg, "p2"))
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        # the pen tool: it always draws, and shows no ring
        pen.hover(ex + 10, ey); pring = ring_on()
        pen.hover(ex + 10, ey, 2); pringb = ring_on()
        check("pen tool, hovering 10 px from the end (button or not): no ring", not pring and not pringb, [pring, pringb])
        pen.stroke([(ex + 10, ey), (ex + 40, ey), (ex + 70, ey)])
        s0 = strokes(pg, "p2")
        check("pen tool, pen down 10 px from the end and 60 px along: a NEW stroke, the line unchanged",
              len(s0) == n + 1 and s0[-1]["kind"] == "pen" and L() == d0 and U(pg) == u0 + 1, [[x["kind"] for x in s0], U(pg) - u0])
        check("... the new stroke starts where the pen came down", near(s0[-1]["data"]["points"][0], (d0["x2"] + 10 / z, d0["y2"]), 1.5), s0[-1]["data"]["points"][:2])
        pen.stroke([(ex, ey), (ex + 40, ey + 20), (ex + 80, ey + 40)])
        check("pen tool, pen down ON the end (flipped: it grabbed in pw-v4e): a new stroke, the line unchanged",
              len(strokes(pg, "p2")) == n + 2 and last(pg, "p2")["kind"] == "pen" and L() == d0 and U(pg) == u0 + 2)
        draw(pg, 1, [(d0["x2"] - 4, d0["y2"] + 3), (d0["x2"] - 4, d0["y2"] + 53)], steps=4)
        check("pen tool, the left mouse button on the end (flipped): a new stroke, the line unchanged",
              len(strokes(pg, "p2")) == n + 3 and last(pg, "p2")["kind"] == "pen" and L() == d0 and U(pg) == u0 + 3)
        pen.stroke([(ex + 4, ey + 2), (ex + 64, ey + 42)], bb=2)
        check("pen tool, the button held and the tip down on the end (flipped): a harmless miss, nothing drawn, nothing moved",
              len(strokes(pg, "p2")) == n + 3 and L() == d0 and U(pg) == u0 + 3)
        undo(pg); undo(pg); undo(pg)
        check("three undos take the three new strokes away", len(strokes(pg, "p2")) == n and U(pg) == u0, [len(strokes(pg, "p2")), n, U(pg), u0])
        # the select tool: its ring, then the grab
        tool(pg, "select")
        pen.hover(ex + 10, ey); r10 = ring_on()
        pen.hover(ex + 30, ey); r30 = ring_on()
        pen.hover(ex + 10, ey, 2); rb = ring_on()
        pen.hover(ex + 10, ey)
        check("select tool, hovering 10 px from the end: the ring shows", r10)
        check("select tool, hovering 30 px away: no ring", not r30)
        check("select tool, hovering near the end with the button held: the ring shows too", rb)
        pg.evaluate("() => document.getElementById('desk').dispatchEvent(new PointerEvent('pointerleave', { pointerId: 1, pointerType: 'pen' }))")
        check("the pen leaving the desk hides the ring", not ring_on())
        pen.stroke([(ex + 10, ey), (ex + 40, ey), (ex + 70, ey)])
        g1 = L()
        check("select tool, pen down 10 px from the end and 60 px along: the end moved with the pen, its offset kept (within 0.5 px)",
              abs(g1["x2"] - (d0["x2"] + 60 / z)) <= 0.5 and abs(g1["y2"] - d0["y2"]) <= 0.5 and g1["x1"] == d0["x1"] and g1["y1"] == d0["y1"], [d0, g1])
        check("... no new stroke, ONE undo step", len(strokes(pg, "p2")) == n and U(pg) == u0 + 1, [len(strokes(pg, "p2")), n, U(pg), u0])
        check("... the line is NOT selected afterwards (a grab is not a selection)", sel(pg) is None, sel(pg))
        check("... and the ring is gone after the lift", not ring_on())
        idle(pg)
        check("... and it is saved", [x for x in stored(pg, "p2") if x["id"] == ln["id"]][0]["data"] == g1)
        undo(pg)
        check("undo puts the end back", L() == d0, [L(), d0])
        redo(pg)
        check("redo moves it again", L() == g1)
        sx0, sy0 = screen(pg, 1, d0["x1"], d0["y1"])
        pen.stroke([(sx0 + 12, sy0 + 9), (sx0 + 12, sy0 + 39), (sx0 + 12, sy0 + 69)])
        g2 = L()
        check("select tool, pen down 15 px from the start end grabs that end, offset kept (y1 +60), the other end stays",
              near((g2["x1"], g2["y1"]), (d0["x1"], d0["y1"] + 60), 1.5) and g2["x2"] == g1["x2"] and g2["y2"] == g1["y2"] and len(strokes(pg, "p2")) == n, [g1, g2])
        ex, ey = screen(pg, 1, g2["x2"], g2["y2"])
        pen.stroke([(ex + 17, ey), (ex + 37, ey + 20), (ex + 57, ey + 40)])
        g3 = L()
        check("select tool, pen down 17 px from the end (inside the 20 px reach) grabs it (x2 +40, y2 +40)",
              near((g3["x2"], g3["y2"]), (g2["x2"] + 40, g2["y2"] + 40), 1.5) and len(strokes(pg, "p2")) == n, [g2, g3])
        ex, ey = screen(pg, 1, g3["x2"], g3["y2"])
        pen.stroke([(ex + 23, ey), (ex + 53, ey + 15), (ex + 83, ey + 30)])
        check("select tool, pen down 23 px from the end (outside the reach): no grab, a selection box that takes nothing, nothing drawn",
              L() == g3 and len(strokes(pg, "p2")) == n and sel(pg) is None, [L(), g3, sel(pg)])
        u1 = U(pg)
        draw(pg, 1, [(g3["x2"] - 4, g3["y2"] + 3), (g3["x2"] - 4, g3["y2"] + 53)], steps=4)
        g4 = L()
        check("select tool, the plain left mouse button on an end grabs it as well (y2 +50)",
              near((g4["x2"], g4["y2"]), (g3["x2"], g3["y2"] + 50), 1.5) and len(strokes(pg, "p2")) == n and U(pg) == u1 + 1, [g3, g4])
        # the button held from the hover on, then the tip touches the end: the spec's chorded move (button 0, buttons 3)
        ex, ey = screen(pg, 1, g4["x2"], g4["y2"])
        pen.stroke([(ex + 4, ey + 2), (ex + 64, ey + 42)], bb=2)
        g5 = L()
        check("select tool, pen button held, tip down on the end: the same grab (x2 +60, y2 +40)",
              near((g5["x2"], g5["y2"]), (g4["x2"] + 60, g4["y2"] + 40), 1.5) and g5["x1"] == g4["x1"], [g4, g5])
        check("... no new stroke, one undo step", len(strokes(pg, "p2")) == n and U(pg) == u1 + 2, [len(strokes(pg, "p2")), n, U(pg), u1])
        # a press of the button itself (pointerdown pen, button 2, buttons 2) on the end: no grab; its contextmenu flips the tool
        ex, ey = screen(pg, 1, g5["x2"], g5["y2"])
        pen.bstroke([(ex - 3, ey + 2), (ex - 53, ey + 2)])
        check("select tool, pointerdown pen with button 2 on the end: no grab (flipped), nothing drawn, no undo step",
              L() == g5 and len(strokes(pg, "p2")) == n and U(pg) == u1 + 2, [g5, L(), U(pg) - u1])
        check("... its contextmenu on the release flips Select back to the pen, the tray's pen lit", tool_is(pg) == "pen" and lit(pg) == ["pen"], [tool_is(pg), lit(pg)])
        # away from any handle with the button, the pen tool: a harmless miss, both ways
        fx, fy = screen(pg, 1, 600, 900)
        pen.bstroke([(fx, fy), (fx + 80, fy + 30)])
        check("pen tool, pen button down away from any handle: nothing (no stroke, no change, no undo step)", len(strokes(pg, "p2")) == n and L() == g5 and U(pg) == u1 + 2)
        check("... and its contextmenu flips the pen to Select", tool_is(pg) == "select" and lit(pg) == ["select"], [tool_is(pg), lit(pg)])
        tool(pg, "pen")
        pen.stroke([(fx, fy + 60), (fx + 80, fy + 90)], bb=2)
        check("pen tool, pen button held, tip down away from any handle: nothing either", len(strokes(pg, "p2")) == n and L() == g5 and U(pg) == u1 + 2)
        # a tool change hides the ring; the highlighter never shows one and never grabs
        tool(pg, "select")
        ex, ey = screen(pg, 1, g5["x2"], g5["y2"])
        pen.hover(ex + 10, ey); was = ring_on()
        tool(pg, "highlighter")
        check("a tool change hides the ring", was and not ring_on())
        pen.hover(ex + 10, ey)
        check("with the highlighter, hovering near a handle: no ring", not ring_on())
        pen.stroke([(ex, ey), (ex + 30, ey + 15), (ex + 60, ey + 30)])
        s2 = strokes(pg, "p2")
        check("the highlighter down ON the end never grabs: a new highlighter stroke, the line unchanged",
              len(s2) == n + 1 and s2[-1]["kind"] == "highlighter" and L() == g5, [x["kind"] for x in s2])
        n += 1
        tool(pg, "pen")
        # the right mouse button no longer grabs (flipped): its release flips the tool instead; the select tool's left button grabs
        u2 = U(pg)
        rdrag_page(pg, 1, (g5["x2"] + 3, g5["y2"] - 2), (g5["x2"] + 3, g5["y2"] + 58))
        check("the right mouse button on the end no longer grabs (flipped): the end stays, nothing drawn, no undo step",
              L() == g5 and len(strokes(pg, "p2")) == n and U(pg) == u2, [g5, L(), U(pg) - u2])
        check("... and its release (a contextmenu) flips the pen to Select", tool_is(pg) == "select", tool_is(pg))
        tool(pg, "pen")
        grab_page(pg, 1, (g5["x2"] + 3, g5["y2"] - 2), (g5["x2"] + 3, g5["y2"] + 58))
        g6 = L()
        check("the select tool's left button grabs the end instead (y2 +60), and the tool goes back to the pen",
              abs(g6["y2"] - (g5["y2"] + 60)) <= 1.5 and abs(g6["x2"] - g5["x2"]) <= 1.5 and len(strokes(pg, "p2")) == n and tool_is(pg) == "pen", [g5, g6])
        # the button let go mid-drag: the drag runs on until the pen lifts
        tool(pg, "select")
        ex, ey = screen(pg, 1, g6["x2"], g6["y2"])
        pg.evaluate("""([x, y]) => { const fire = (t, x, y, b) => (document.elementFromPoint(x, y) || document.getElementById('desk')).dispatchEvent(new PointerEvent(t,
            { bubbles: true, cancelable: true, composed: true, pointerId: 9, pointerType: 'pen', isPrimary: true, clientX: x, clientY: y,
              button: t === 'pointermove' ? -1 : 0, buttons: b, pressure: b ? 0.5 : 0 }));
          fire('pointerdown', x, y, 3); fire('pointermove', x + 20, y, 3); fire('pointermove', x + 40, y, 1); fire('pointermove', x + 70, y, 1); fire('pointerup', x + 70, y, 0); }""", [ex, ey])
        g7 = L()
        check("select tool, button let go mid-drag: the end follows the pen to the lift (x2 +70)", abs(g7["x2"] - (g6["x2"] + 70)) <= 1.5 and len(strokes(pg, "p2")) == n, [g6, g7])
        # the CDP version: tip lifted while the button is still held ends the grab there
        pen.stroke([(screen(pg, 1, g7["x2"], g7["y2"])), (screen(pg, 1, g7["x2"], g7["y2"] - 30))], bb=2)
        g8 = L()
        check("select tool, button held, tip lifted: the grab ends at the lift (y2 -30)", abs(g8["y2"] - (g7["y2"] - 30)) <= 1.5 and len(strokes(pg, "p2")) == n, [g7, g8])
        # other tools ignore the button itself
        tool(pg, "eraser")
        a5, b5 = screen(pg, 1, 100, 550), screen(pg, 1, 700, 550)
        pg.mouse.move(*a5); pg.mouse.down(button="right"); pg.mouse.move(b5[0], b5[1], steps=12); pg.mouse.up(button="right"); pg.wait_for_timeout(40)
        check("the stroke eraser with the right button erases nothing (as before)", len(strokes(pg, "p2")) == n)
        check("... and the release flips the eraser to Select (pw-v4v)", tool_is(pg) == "select", tool_is(pg))
        tool(pg, "pen")
        # no context menu on the desk
        cm = pg.evaluate("""() => { const d = document.getElementById('desk'), s = d.querySelector('#stack .sheet');
          const fire = (el) => el.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, button: 2 }));
          return [fire(d), fire(s)]; }""")
        check("contextmenu on the desk and on a page is default-prevented", cm == [False, False], cm)
        check("... and the two flipped pen, Select, pen", tool_is(pg) == "pen", tool_is(pg))
        pg.evaluate("() => { window.__cm = []; document.addEventListener('contextmenu', (e) => window.__cm.push(e.defaultPrevented)); }")
        rdrag_page(pg, 1, (600, 900), (610, 900))
        check("a real right click on the page: its contextmenu is default-prevented", pg.evaluate("window.__cm") == [True], pg.evaluate("window.__cm"))
        cmo = pg.evaluate("() => document.getElementById('backBtn').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }))")
        t_after = tool_is(pg)
        check("contextmenu outside the desk is left alone (and flips nothing)", cmo is True and t_after == "select", [cmo, t_after])
        check("no #dbg and no readout without ?dbg=1", pg.locator("#dbg").count() == 0 and pg.locator("#dbgCss").count() == 0)
        check("no page errors in this group", not e9, e9)
        ctx.close()

        # the readout: off without the flag (no request at all), on with it
        ctx = b.new_context(viewport={"width": 1280, "height": 1300}); pg = ctx.new_page(); reqs = []; e10 = []
        pg.on("pageerror", lambda e: e10.append(str(e))); pg.on("request", lambda r: reqs.append(r.url))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg, "Handles")
        draw(pg, 1, [(200, 200), (300, 260)], steps=4); pg.wait_for_timeout(100)
        res_dbg = pg.evaluate("performance.getEntriesByType('resource').filter(e => e.name.includes('dbg')).length")
        check("no ?dbg=1: no #dbg element, no dbg.js request", pg.locator("#dbg").count() == 0 and not [u for u in reqs if "dbg.js" in u] and res_dbg == 0, [u for u in reqs if "dbg" in u])
        ctx.close(); errs += e10
        ctx, pg, e11 = fresh(b, url=LOCAL + "&dbg=1"); errs += e11
        open_note(pg, "Handles")
        pg.wait_for_selector("#dbg", state="attached", timeout=5000)
        info = pg.evaluate("""() => { const e = document.getElementById('dbg'), c = getComputedStyle(e), r = e.getBoundingClientRect(), d = document.getElementById('desk').getBoundingClientRect();
          return { pe: c.pointerEvents, font: c.fontSize, fam: c.fontFamily, left: r.left - d.left, bottom: d.bottom - r.bottom, parent: e.parentNode.id, bg: c.backgroundColor }; }""")
        check("?dbg=1: the #dbg box is on the desk, bottom-left (64 px in, clear of the zoom lock chip, pw-v7b), 11 px monospace, pointer-events none",
              info["parent"] == "desk" and info["pe"] == "none" and info["font"] == "11px" and "monospace" in info["fam"] and abs(info["left"] - 64) < 1 and info["bottom"] < 20, info)
        pen = Pen(ctx, pg)
        n0 = len(strokes(pg, "p2"))
        a, b2 = screen(pg, 1, 200, 400), screen(pg, 1, 400, 480)
        pen.stroke([a, b2], steps=12)
        txt = pg.evaluate("document.getElementById('dbg').textContent").split("\n")
        lastln = txt.pop()                          # pw-v4n: the box ends with the 'last: ...' line; the rest are event lines
        check("the readout's bottom line is the last-stroke line (pw-v4n)", re.fullmatch(r"last: \d+ pts, \d+(\.\d)? px, pen, classify: \w+, (snapped|freehand)", lastln) is not None, lastln)
        check("a pen stroke still draws with the readout on", len(strokes(pg, "p2")) == n0 + 1)
        check("the readout shows at most 4 lines, the newest first: 'pointerup pen 0 0 0'", len(txt) <= 4 and txt[0] == "pointerup pen 0 0 0", txt)
        check("every line is 'type pointerType button buttons pressure'", all(re.fullmatch(r"(pointer\w+|contextmenu) \w+ -?\d+ \d+ (-|\d+(\.\d\d)?)", t) for t in txt), txt)
        check("a stroke's moves are collapsed (only a move whose buttons changed is shown)", sum(t.startswith("pointermove") for t in txt) <= 2, txt)
        pen.bstroke([b2, (b2[0] + 30, b2[1])])
        txt = pg.evaluate("document.getElementById('dbg').textContent").split("\n")
        check("the pen button shows: 'pointerdown pen 2 2 ...' then 'pointerup pen 2 0 ...'", any(t.startswith("pointerdown pen 2 2 ") for t in txt) and any(t.startswith("pointerup pen 2 0 ") for t in txt), txt)
        theme = pg.evaluate("""() => { const e = document.getElementById('dbg'), h = document.documentElement, o = h.dataset.theme;
          h.dataset.theme = 'light'; const l = getComputedStyle(e).color; h.dataset.theme = 'dark'; const d = getComputedStyle(e).color;
          if (o === undefined) delete h.dataset.theme; else h.dataset.theme = o; return [l, d]; }""")
        check("light text on the light theme's dark box, dark text on the dark theme's light box", theme[0] != theme[1] and theme[0] == "rgb(255, 255, 255)", theme)
        check("dbg.js is in the service worker shell list", "./js/dbg.js" in pg.evaluate("fetch('./sw.js').then(r => r.text())"))
        ctx.close()

        # ------------------------------------------------------------ pw-v4v: select grab rules, and the pen button (contextmenu) flips Pen and Select
        group[0] = "select drags an end (pw-v4v)"
        ctx, pg, e12 = fresh(b); errs += e12
        open_note(pg, "Handles")
        z = zoom(pg)
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2"); d0 = dict(ln["data"])
        check("a line to work with", ln["kind"] == "shape" and ln["data"]["type"] == "line", ln["data"])
        L = lambda: [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"]
        CM = """([x, y, pt]) => { const el = document.elementFromPoint(x, y) || document.getElementById('desk');
          const o = { clientX: x, clientY: y, bubbles: true, cancelable: true };
          return el.dispatchEvent(pt ? new PointerEvent('contextmenu', { ...o, pointerType: pt }) : new MouseEvent('contextmenu', o)); }"""
        PE = """([t, x, y, b]) => (document.elementFromPoint(x, y) || document.getElementById('desk')).dispatchEvent(new PointerEvent(t,
          { bubbles: true, cancelable: true, composed: true, pointerId: 11, pointerType: 'pen', isPrimary: true, clientX: x, clientY: y,
            button: t === 'pointermove' ? -1 : 0, buttons: b, pressure: b ? 0.5 : 0 }))"""
        DESK_CM = "() => document.getElementById('desk').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 600, clientY: 600 }))"
        cmx = lambda x, y, pt=None: pg.evaluate(CM, [x, y, pt])
        pe = lambda t, x, y, bt=0: pg.evaluate(PE, [t, x, y, bt])
        desk_cm = lambda: pg.evaluate(DESK_CM)
        ring = lambda: pg.evaluate("""(() => { const r = document.getElementById('handleRing'); if (!r || r.hidden) return null;
          const b = r.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; })()""")
        ex2 = lambda: pg.evaluate("""(id) => { const e = document.querySelector(`svg.ink [data-id="${id}"]`); return [+e.getAttribute('x2'), +e.getAttribute('y2')]; }""", ln["id"])
        selids = lambda: (sel(pg) or {}).get("ids")
        gone = pg.evaluate("(() => { const k = window.__pw.ink; return [typeof k.floating, typeof k.dropFloat, typeof k.hook.press, typeof k.hook.drop]; })()")
        check("the one-press pick-up is gone: no ink.floating, ink.dropFloat, hook.press or hook.drop", gone == ["undefined"] * 4, gone)
        n = len(strokes(pg, "p2")); u0 = U(pg)
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        fx, fy = screen(pg, 1, 600, 900)
        # a tap on an end selects the shape
        tool(pg, "select")
        pe("pointerdown", ex + 2, ey, 1); pe("pointermove", ex + 3, ey + 1, 1); pe("pointerup", ex + 3, ey + 1, 0)
        check("select tool, a tap (under 4 px) on the end: the line becomes the selection, nothing moves, no undo step",
              selids() == [ln["id"]] and L() == d0 and U(pg) == u0 and ex2() == [d0["x2"], d0["y2"]], [sel(pg), L(), U(pg) - u0])
        # shapes to work with: a rect and an arc
        tool(pg, "pen")
        draw(pg, 1, rough_square(150, 760, 160), steps=3, hold=650)
        rc = last(pg, "p2")
        check("a rough square snaps to a rect", rc["kind"] == "shape" and rc["data"]["type"] == "rect", [rc["kind"], rc["data"]])
        draw(pg, 1, rough_arc(560, 560, 120, -150, -30), steps=2, hold=650)
        ar = last(pg, "p2")
        check("a rough arc snaps to an arc", ar["kind"] == "shape" and ar["data"]["type"] == "arc", [ar["kind"], ar["data"]])
        R = lambda sid: [x for x in strokes(pg, "p2") if x["id"] == sid][0]
        n = len(strokes(pg, "p2"))
        # the rect selected: a box corner wins over the rect's own corner (a resize, not a grab)
        tool(pg, "select")
        q0 = rc["data"]["points"]
        tap_page(pg, 1, (q0[0][0] + q0[1][0]) / 2, q0[0][1])
        check("a tap on the rect's top edge selects the rect", selids() == [rc["id"]], sel(pg))
        bx = sel(pg)["box"]; pad = 4 / z
        cx0, cy0 = bx[0] - pad, bx[1] - pad                              # the box's top-left corner (the dashed box sits 4 px outside)
        pen_pt = screen(pg, 1, cx0, cy0)
        pg.mouse.move(*pen_pt); pg.wait_for_timeout(20)
        check("hovering on the selection's corner (the rect's own corner inside reach too): no handle ring, the corner wins", ring() is None, ring())
        u1 = U(pg)
        drag_page(pg, 1, (cx0, cy0), (cx0 - 40, cy0 - 10))
        q1 = R(rc["id"])["data"]["points"]
        w1, h1 = q1[1][0] - q1[0][0], q1[2][1] - q1[1][1]
        w0, h0 = q0[1][0] - q0[0][0], q0[2][1] - q0[1][1]
        check("pen down on the box's corner with the rect selected: a resize (the aspect holds, the far corner holds), not a grab",
              abs(w1 / h1 - w0 / h0) < 0.02 and w1 > w0 and near(q1[2], q0[2], 1.5) and U(pg) == u1 + 1, [q0, q1])
        check("... and the rect is still selected", selids() == [rc["id"]], sel(pg))
        # the arc selected: its middle handle (on the box's top edge, away from the corners and the ring) is a grab
        tap_page(pg, 1, 700, 1050)
        drag_page(pg, 1, (420, 420), (700, 560))
        check("a box round the arc selects it alone", selids() == [ar["id"]], sel(pg))
        a0 = R(ar["id"])["data"]
        mx, my = screen(pg, 1, a0["xm"], a0["ym"])
        pg.mouse.move(mx + 5, my + 3); pg.wait_for_timeout(20)
        check("hovering on the selected arc's middle handle: the ring shows (a grab would win there)", ring() is not None and near(ring(), (mx, my), 2), [ring(), mx, my])
        u2 = U(pg)
        drag_page(pg, 1, (a0["xm"] + 5, a0["ym"] + 3), (a0["xm"] + 5, a0["ym"] - 27))
        a1 = R(ar["id"])["data"]
        check("pen down on the selected arc's middle handle: a grab (ym -30, the ends stay, one undo step)",
              abs(a1["ym"] - (a0["ym"] - 30)) <= 1.0 and abs(a1["xm"] - a0["xm"]) <= 1.0 and a1["x1"] == a0["x1"] and a1["x2"] == a0["x2"] and U(pg) == u2 + 1, [a0, a1])
        check("... and the selection is cleared", sel(pg) is None and pg.evaluate("document.querySelectorAll('svg.ink g.sel').length") == 0, sel(pg))
        # a selection exists, a grab on ANOTHER shape's end: the selection clears and the end moves
        q2 = R(rc["id"])["data"]["points"]
        tap_page(pg, 1, (q2[0][0] + q2[1][0]) / 2, q2[0][1])
        check("the rect is selected again", selids() == [rc["id"]], sel(pg))
        u3 = U(pg)
        drag_page(pg, 1, (d0["x2"] + 6, d0["y2"]), (d0["x2"] + 6, d0["y2"] + 40))
        g1 = L()
        check("with the rect selected, a grab on the line's end: the end moves (y2 +40)", abs(g1["y2"] - (d0["y2"] + 40)) <= 1.5 and abs(g1["x2"] - d0["x2"]) <= 1.5 and U(pg) == u3 + 1, [d0, g1])
        check("... and the rect's selection is cleared", sel(pg) is None, sel(pg))
        check("... nothing new drawn", len(strokes(pg, "p2")) == n)
        # the pen button: one contextmenu on the desk flips the tool
        tool(pg, "pen")
        ok = desk_cm()
        check("a contextmenu on the desk with the pen tool (her pen button): default-prevented, the tool is Select, the tray's Select lit",
              ok is False and tool_is(pg) == "select" and lit(pg) == ["select"] and pg.evaluate("window.__pw.tray().tool") == "select", [ok, tool_is(pg), lit(pg)])
        desk_cm()
        check("again: back to the pen, the tray's pen lit", tool_is(pg) == "pen" and lit(pg) == ["pen"] and pg.evaluate("window.__pw.tray().tool") == "pen", [tool_is(pg), lit(pg)])
        tool(pg, "highlighter")
        desk_cm(); t1 = tool_is(pg)
        desk_cm()
        check("with the highlighter as the last ink tool: Select, then back to the highlighter", t1 == "select" and tool_is(pg) == "highlighter" and lit(pg) == ["highlighter"], [t1, tool_is(pg), lit(pg)])
        saved = pg.evaluate("JSON.parse(localStorage.getItem('pw.tools') || '{}').tool")
        check("... and the tray's own state (pw.tools) follows: the highlighter", saved == "highlighter", saved)
        tool(pg, "eraser")
        desk_cm(); t1 = tool_is(pg)
        desk_cm()
        check("from the eraser: Select, then the last ink tool (the highlighter)", t1 == "select" and tool_is(pg) == "highlighter", [t1, tool_is(pg)])
        tool(pg, "pen")
        pe("pointerdown", fx, fy, 1); pe("pointermove", fx + 20, fy + 10, 1)
        desk_cm(); mid = tool_is(pg)
        pe("pointermove", fx + 40, fy + 20, 1); pe("pointerup", fx + 40, fy + 20, 0)
        check("a press while a pen stroke is in progress: no flip, and the stroke still lands", mid == "pen" and tool_is(pg) == "pen" and len(strokes(pg, "p2")) == n + 1 and last(pg, "p2")["kind"] == "pen", [mid, tool_is(pg)])
        n += 1
        pg.click("#listBtn"); pg.wait_for_selector("#pageList:not([hidden])")
        desk_cm()
        check("with the page list open: no flip (and the list stays open)", tool_is(pg) == "pen" and pg.locator("#pageList").is_visible(), tool_is(pg))
        pg.click("#plClose"); pg.wait_for_timeout(30)
        cmx(fx, fy, "touch")
        check("a finger's long press (contextmenu, pointerType touch): no flip", tool_is(pg) == "pen", tool_is(pg))
        pg.evaluate("([x, y]) => window.__pw.ink.hook.holdMenu(x, y)", [fx, fy]); pg.wait_for_timeout(30)
        menu_on = pg.locator("#menu").is_visible()
        desk_cm()
        check("with the finger hold menu (Paste) open: no flip", menu_on and tool_is(pg) == "pen", [menu_on, tool_is(pg)])
        pg.keyboard.press("Escape"); pg.wait_for_timeout(20)
        pg.click("#tool-pen"); pg.wait_for_timeout(20)                   # a second tap on the pen opens its panel
        panel_on = pg.locator("#toolPanel").is_visible()
        desk_cm()
        check("with the pen's tool panel open: no flip", panel_on and tool_is(pg) == "pen", [panel_on, tool_is(pg)])
        pg.keyboard.press("Escape"); pg.wait_for_timeout(20)
        desk_cm()
        check("everything closed again: the press flips to Select", tool_is(pg) == "select", tool_is(pg))
        tap_page(pg, 1, (q2[0][0] + q2[1][0]) / 2, q2[0][1])
        had = selids()
        desk_cm()
        check("flipping away from Select clears the selection", had == [rc["id"]] and tool_is(pg) == "pen" and sel(pg) is None, [had, sel(pg)])
        # her flow (flipped from pw-v4e's "press then touch"): a press near the end flips to Select, the touch grabs it
        g1 = L(); ex, ey = screen(pg, 1, g1["x2"], g1["y2"]); u4 = U(pg)
        pe("pointermove", fx, fy)                                          # the pen hovering far away: no ring to start
        ok = cmx(ex + 6, ey + 4)
        check("a press 7 px from the line's end: its contextmenu is default-prevented, the tool flips to Select", ok is False and tool_is(pg) == "select", [ok, tool_is(pg)])
        check("... no stroke, the shape unchanged, no undo step", len(strokes(pg, "p2")) == n and L() == g1 and U(pg) == u4, [len(strokes(pg, "p2")), U(pg)])
        pe("pointermove", ex + 36, ey + 24); pe("pointermove", ex + 66, ey + 44)
        g = ex2()
        check("... hover moves after it leave the end alone (nothing floats) and show no ring out of reach", near(g, (g1["x2"], g1["y2"]), 0.2) and L() == g1 and ring() is None, [g1, g])
        pe("pointermove", ex + 2, ey)
        pg.evaluate(SYNTH_JS, [[(ex + 2, ey), (ex + 22, ey + 10), (ex + 42, ey + 20)], 0])
        g2 = L()
        check("... then a plain touch on the end: the touch grabs and drags it (x2 +40, y2 +20)",
              near((g2["x2"], g2["y2"]), (g1["x2"] + 40 / z, g1["y2"] + 20 / z), 1.0) and g2["x1"] == g1["x1"] and len(strokes(pg, "p2")) == n and U(pg) == u4 + 1, [g1, g2, U(pg)])
        cmx(ex, ey)
        check("a second press flips back to the pen", tool_is(pg) == "pen", tool_is(pg))
        pg.evaluate(SYNTH_JS, [[(fx, fy), (fx + 40, fy + 20), (fx + 80, fy + 30)], 0])
        s3 = strokes(pg, "p2")
        check("... and the next plain touch draws (count +1)", len(s3) == n + 1 and s3[-1]["kind"] == "pen" and L() == g2, [x["kind"] for x in s3])
        n += 1
        undo(pg); undo(pg)
        check("undo takes back the stroke, then the grab (a press is never an undo step)", L() == g1 and len(strokes(pg, "p2")) == n - 1, [L(), g1])
        redo(pg); redo(pg)
        check("... and redo puts both back", L() == g2 and len(strokes(pg, "p2")) == n)
        tool(pg, "eraser")
        ex, ey = screen(pg, 1, g2["x2"], g2["y2"])
        cmx(ex, ey)
        check("with the eraser on, a press near the end changes no ink (it flips to Select)", L() == g2 and len(strokes(pg, "p2")) == n and tool_is(pg) == "select", tool_is(pg))
        # the laptop: a right-mouse drag on the end grabs nothing (flipped); its contextmenu is prevented and flips the tool
        tool(pg, "pen")
        pg.evaluate("() => { window.__cm = []; document.addEventListener('contextmenu', (e) => window.__cm.push(e.defaultPrevented)); }")
        u5 = U(pg)
        rdrag_page(pg, 1, (g2["x2"] + 3, g2["y2"] - 2), (g2["x2"] + 3, g2["y2"] + 48))
        check("a right-mouse drag on the end: no grab (flipped), no undo step", L() == g2 and U(pg) == u5, [g2, L(), U(pg) - u5])
        check("... its contextmenu fired once, was prevented, flipped the pen to Select, and left no ring", pg.evaluate("window.__cm") == [True] and tool_is(pg) == "select" and ring() is None,
              [pg.evaluate("window.__cm"), tool_is(pg), ring()])
        px, py = screen(pg, 1, g2["x2"] + 40, g2["y2"] + 40)
        pe("pointermove", px, py); pg.mouse.move(px, py)
        check("... and later moves leave the end alone", L() == g2 and len(strokes(pg, "p2")) == n)
        check("no page errors in this group", not e12, e12)
        ctx.close()
        # the readout stays and logs the press
        ctx, pg, e13 = fresh(b, url=LOCAL + "&dbg=1"); errs += e13
        open_note(pg, "Handles")
        pg.wait_for_selector("#dbg", state="attached", timeout=5000)
        draw(pg, 1, rough_line(300, 150, 450), hold=650)
        ln = last(pg, "p2"); d0 = dict(ln["data"]); u0 = U(pg)
        ex, ey = screen(pg, 1, d0["x2"], d0["y2"])
        cmx(ex, ey)
        txt = pg.evaluate("document.getElementById('dbg').textContent").split("\n")
        check("?dbg=1: the box is there and logs the press as a contextmenu line", txt[0].startswith("contextmenu "), txt)
        check("... and the press flipped the pen to Select with the readout on (pw-v4v)", tool_is(pg) == "select", tool_is(pg))
        pe("pointerdown", ex, ey, 1); pe("pointermove", ex + 15, ey, 1); pe("pointermove", ex + 30, ey, 1); pe("pointerup", ex + 30, ey, 0)
        g = [x for x in strokes(pg, "p2") if x["id"] == ln["id"]][0]["data"]
        check("... so a plain touch on the end grabs it with the readout on (x2 +30)", abs(g["x2"] - (d0["x2"] + 30 / zoom(pg))) <= 1.0 and U(pg) == u0 + 1, [d0, g])
        ctx.close()

        # ------------------------------------------------------------ pw-v4f: hold-to-snap makes an arc
        group[0] = "arc snap"
        ctx, pg, e14 = fresh(b); errs += e14
        open_note(pg, "Snap")
        tool(pg, "pen")
        ARC_JS = """(id) => { const e = document.querySelector(`svg.ink [data-id="${id}"]`); if (!e) return null;
          const L = e.getTotalLength(), h = e.getPointAtLength(L / 2); return { d: e.getAttribute('d'), mid: [h.x, h.y] }; }"""
        ON_JS = """([id, x, y]) => { const e = document.querySelector(`svg.ink [data-id="${id}"]`); return !!e && e.isPointInStroke(new DOMPoint(x, y)); }"""
        def arcinfo(sid): return pg.evaluate(ARC_JS, sid)
        def on_stroke(sid, x, y): return pg.evaluate(ON_JS, [sid, x, y])
        def flags(dd):                                  # (large-arc, sweep) from "A r r 0 L S"
            m = re.search(r"A([\d.]+) ([\d.]+) 0 ([01]) ([01]) ", dd or "")
            return m and (int(m.group(3)), int(m.group(4)))
        ARCK = ("x1", "y1", "xm", "ym", "x2", "y2")
        u0 = U(pg)
        A1 = rough_arc(300, 300, 120, -150, -30)
        draw(pg, 1, A1, hold=650)
        r = last(pg, "p1")
        check("a 120 degree arc with a little wobble, held: shape/arc", r["kind"] == "shape" and r["data"]["type"] == "arc", [r["kind"], r["data"]])
        ids = []
        if r["data"].get("type") == "arc":
            d = r["data"]; ids.append(r["id"])
            check("its ends within 3 px of the stroke's first and last points", near((d["x1"], d["y1"]), A1[0], 3) and near((d["x2"], d["y2"]), A1[-1], 3), [d, A1[0], A1[-1]])
            check("its middle point within 4 px of the circle", abs(math.hypot(d["xm"] - 300, d["ym"] - 300) - 120) <= 4, d)
            check("... and half way round (near 12 o'clock)", near((d["xm"], d["ym"]), (300, 180), 6), d)
            check("stored to 0.1 px", all(round(d[k], 1) == d[k] for k in ARCK), d)
            check("same colour, width and dash as the pen", r["style"] == {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1}, r["style"])
            e = elinfo(pg, 1, r["id"]); ai = arcinfo(r["id"])
            check("drawn as an SVG <path> in g.pen, stroke only", e["tag"] == "path" and e["type"] == "arc" and e["parent"] == "pen" and e["fill"] == "none"
                  and e["stroke"] == "#000000" and e["width"] == "2.5", e)
            check("its d starts with M and has an A, small-arc flag 0 (120 degrees)", ai["d"].startswith("M") and "A" in ai["d"] and flags(ai["d"]) and flags(ai["d"])[0] == 0, ai)
            check("the drawn path's half-length point is the arc's middle point", near(ai["mid"], (d["xm"], d["ym"]), 1.5), [ai, d])
        check("an arc snap is ONE undo step, one stroke on the page", U(pg) == u0 + 1 and len(strokes(pg, "p1")) == 1, [u0, U(pg)])
        pg.wait_for_timeout(200)
        check("after the fade only the arc is in the layer", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 1)
        # 270 degrees, both ways round
        for name, pts, mid_at, want in [("clockwise", rough_arc(300, 650, 120, 0, 270, n=40), (300 - 84.9, 650 + 84.9), (1, 1)),
                                        ("anticlockwise", rough_arc(600, 650, 120, 0, -270, n=40), (600 - 84.9, 650 - 84.9), (1, 0))]:
            draw(pg, 1, pts, hold=650)
            r = last(pg, "p1")
            ok = r["kind"] == "shape" and r["data"]["type"] == "arc"
            check(f"a 270 degree arc drawn {name}: arc", ok, [r["kind"], r["data"]])
            if ok:
                d = r["data"]; ai = arcinfo(r["id"]); ids.append(r["id"])
                check(f"... large-arc flag 1, sweep flag {want[1]} (it goes the way it was drawn)", flags(ai["d"]) == want, ai["d"])
                check(f"... its middle point is the drawn stroke's middle (the {name} side)", near((d["xm"], d["ym"]), mid_at, 6), [d, mid_at])
                check(f"... and the rendered path runs through it", near(ai["mid"], mid_at, 6), [ai, mid_at])
                check(f"... ends near the stroke's ends", near((d["x1"], d["y1"]), pts[0], 3) and near((d["x2"], d["y2"]), pts[-1], 3), [d, pts[0], pts[-1]])
        ring_ = rough_arc(600, 300, 90, -90, 260, n=36)              # ends 16 px apart: inside 10% of the size
        draw(pg, 1, ring_, steps=2, hold=650)
        check("a near-full ring (end within 10% of the start) still snaps to circle, not arc", last(pg, "p1")["data"].get("type") == "circle", last(pg, "p1")["data"])
        draw(pg, 1, rough_line(1000, 100, 420), hold=650)
        check("a line still snaps to line (never arc)", last(pg, "p1")["data"].get("type") == "line", last(pg, "p1")["data"])
        S = [(100 + 300 * k / 24, 850 + 35 * math.sin(2 * math.pi * k / 24)) for k in range(25)]
        n = len(strokes(pg, "p1"))
        draw(pg, 1, S, steps=3, hold=650)
        check("an S-curve held stays freehand", len(strokes(pg, "p1")) == n + 1 and last(pg, "p1")["kind"] == "pen", last(pg, "p1")["kind"])
        check("classify: the S-curve is not a shape", cls(S) is None, cls(S))
        loop = [(100 + 5 * k, 500) for k in range(21)] + [(200 + 40 * math.cos(math.radians(90 + 15 * k)), 460 + 40 * math.sin(math.radians(90 + 15 * k))) for k in range(1, 25)] \
            + [(200 + 5 * k, 500) for k in range(1, 21)]
        check("classify: a loop (line, a full turn, line) stays freehand", cls(loop) is None, cls(loop))
        V = [(100 + 5 * k, 600 + 10 * k) for k in range(11)] + [(150 + 5 * k, 700 - 10 * k) for k in range(1, 11)]
        check("classify: a sharp V stays freehand", cls(V) is None, cls(V))
        sliver = [(300 + 300 * math.cos(math.radians(-100 + k)), 400 + 300 * math.sin(math.radians(-100 + k))) for k in range(21)]
        check("classify: a 20 degree sliver of a circle is a line, not an arc (the line test runs first)", cls(sliver) == "line", cls(sliver))
        tool(pg, "highlighter")
        draw(pg, 1, rough_arc(600, 1050, 100, -160, -20), hold=650)
        h = last(pg, "p1")
        check("a highlighter arc held: shape/arc", h["kind"] == "shape" and h["data"]["type"] == "arc", [h["kind"], h["data"]])
        check("... with the highlighter's look", h["style"] == {"colour": "#FFC107", "width": 18, "dash": "solid", "opacity": 0.4}, h["style"])
        e = elinfo(pg, 1, h["id"])
        check("... a <path> in its g.hlo (0.4) group under g.hl", e["tag"] == "path" and e["parent"] == "hlo" and e["gp"] == "hl" and e["opacity"] == "0.4", e)
        ids.append(h["id"])
        tool(pg, "pen")
        before = {i: arcinfo(i)["d"] for i in ids}
        idle(pg); pg.reload(); ready(pg); open_note(pg, "Snap")
        after = {i: (arcinfo(i) or {}).get("d") for i in ids}
        check("after a reload every arc is redrawn the same", before == after, [before, after])
        ctx.close()

        # the arc's handles, eraser and selection
        ctx, pg, e15 = fresh(b); errs += e15
        open_note(pg, "Handles")
        pen = Pen(ctx, pg)
        draw(pg, 1, rough_arc(400, 500, 150, -150, -30), hold=650)
        a = last(pg, "p2")
        check("an arc to grab", a["kind"] == "shape" and a["data"]["type"] == "arc", a["data"])
        if a["data"].get("type") == "arc":
            d0 = dict(a["data"]); u0 = U(pg)
            hs = pg.evaluate("(id) => import('./js/ink.js').then(m => m.handles(m.strokesOf('p2').find(r => r.id === id)))", a["id"])
            check("handles gives 3: start, middle, end", hs == [[d0["x1"], d0["y1"]], [d0["xm"], d0["ym"]], [d0["x2"], d0["y2"]]], hs)
            tool(pg, "select")                                    # pw-v4v: the select tool grabs a handle, the pen only draws
            pen.stroke([screen(pg, 1, d0["xm"], d0["ym"]), screen(pg, 1, d0["xm"], d0["ym"] - 40)])
            d1 = last(pg, "p2")["data"]
            check("the select tool's pen on the middle handle drags it: the new middle is where it was dragged to", abs(d1["xm"] - d0["xm"]) <= 1.5 and abs(d1["ym"] - (d0["ym"] - 40)) <= 1.5, [d0, d1])
            check("... the ends unchanged", all(d1[k] == d0[k] for k in ("x1", "y1", "x2", "y2")), [d0, d1])
            check("... no stroke drawn, one undo step", len(strokes(pg, "p2")) == 1 and U(pg) == u0 + 1, [len(strokes(pg, "p2")), U(pg), u0])
            check("... the bulge changed: the path now runs through the new middle and the ends",
                  on_stroke(a["id"], d1["xm"], d1["ym"]) and on_stroke(a["id"], d1["x1"], d1["y1"]) and on_stroke(a["id"], d1["x2"], d1["y2"])
                  and not on_stroke(a["id"], d0["xm"], d0["ym"]), arcinfo(a["id"]))
            undo(pg)
            check("undo puts the middle back", last(pg, "p2")["data"] == d0, [last(pg, "p2")["data"], d0])
            redo(pg)
            check("redo drags it again", last(pg, "p2")["data"] == d1)
            pen.stroke([screen(pg, 1, d1["x2"], d1["y2"]), screen(pg, 1, d1["x2"] + 30, d1["y2"] + 40)])
            d2 = last(pg, "p2")["data"]
            check("dragging an end moves only that end, the middle (and the start) stay",
                  abs(d2["x2"] - (d1["x2"] + 30)) <= 1.5 and abs(d2["y2"] - (d1["y2"] + 40)) <= 1.5 and all(d2[k] == d1[k] for k in ("x1", "y1", "xm", "ym")), [d1, d2])
            check("... and the path goes through the new end", on_stroke(a["id"], d2["x2"], d2["y2"]))
        ctx.close()
        ctx, pg, e16 = fresh(b); errs += e16
        open_note(pg, "Erase")
        draw(pg, 1, rough_arc(400, 400, 150, -150, -30), hold=650)
        a = last(pg, "p5")
        check("an arc to erase", a["kind"] == "shape" and a["data"]["type"] == "arc", a["data"])
        tool(pg, "eraser")
        u0 = U(pg)
        tap_page(pg, 1, 400, 300)                                     # inside the bow: 50 px under the curve, above the chord (y 325)
        check("the stroke eraser inside the chord's bow leaves the arc alone", len(strokes(pg, "p5")) == 1 and U(pg) == u0)
        q = pg.evaluate("(id) => import('./js/ink.js').then(m => m.outline(m.strokesOf('p5').find(r => r.id === id))[12])", a["id"])
        tap_page(pg, 1, q[0] + 2, q[1] + 2)
        check("the stroke eraser on the curve removes the arc, one undo step", len(strokes(pg, "p5")) == 0 and U(pg) == u0 + 1, [q, strokes(pg, "p5")])
        ctx.close()
        ctx, pg, e17 = fresh(b); errs += e17
        open_note(pg, "Select")
        draw(pg, 1, rough_arc(400, 400, 150, -150, -30), hold=650)
        a = last(pg, "p4")
        check("an arc to select", a["kind"] == "shape" and a["data"]["type"] == "arc", a["data"])
        if a["data"].get("type") == "arc":
            d0 = dict(a["data"])
            tool(pg, "select")
            drag_page(pg, 1, (230, 230), (570, 345))
            check("a select box around it selects it", sel(pg) and sel(pg)["ids"] == [a["id"]], sel(pg))
            u0 = U(pg)
            drag_page(pg, 1, (400, 300), (450, 340))
            d1 = last(pg, "p4")["data"]
            check("a selection move moves all three points by (50, 40)",
                  all(abs(d1[k] - (d0[k] + (50 if k[0] == "x" else 40))) <= 0.11 for k in ARCK), [d0, d1])
            check("... one undo step, and the path follows", U(pg) == u0 + 1 and on_stroke(a["id"], d1["xm"], d1["ym"]), [U(pg), u0])
        check("no page errors in the arc groups", not (e14 or e15 or e16 or e17), [e14, e15, e16, e17])
        ctx.close()

        # ------------------------------------------------------------ pw-v4g: the select tool turns, brings to the front, keeps the width
        group[0] = "rotate, front, width"
        ctx, pg, e18 = fresh(b); errs += e18
        open_note(pg, "Select")
        PUT_JS = "([pid, recs]) => import('./js/ink.js').then(m => m.put(pid, recs))"
        HND_JS = "(id) => import('./js/ink.js').then(m => m.handles(m.strokesOf('p4').find(r => r.id === id)))"
        RING_JS = """() => { const c = document.querySelector('svg.ink g.sel circle.selrot'); return c ? [+c.getAttribute('cx'), +c.getAttribute('cy'), +c.getAttribute('r')] : null; }"""
        CORN_JS = "() => [...document.querySelectorAll('svg.ink g.sel circle.selh')].map(e => [+e.getAttribute('cx'), +e.getAttribute('cy'), +e.getAttribute('r')])"
        ORDER_JS = """(id) => { const e = document.querySelector(`svg.ink [data-id="${id}"]`);
          return e ? { group: e.parentNode.getAttribute('class'), ids: [...e.parentNode.children].map(c => c.dataset.id) } : null; }"""
        BBW_JS = """(id) => document.querySelector(`svg.ink [data-id="${id}"]`).getBBox().width"""
        now0 = int(time.time() * 1000)
        def rec(rid, kind, d, width=2.5, k=0):
            return {"id": rid, "page_id": "p4", "seq": now0 + k, "kind": kind, "style": {"colour": "#000000", "width": width, "dash": "solid", "opacity": 1}, "data": d}
        def rot_about(q, c, deg):
            t = math.radians(deg); x, y = q[0] - c[0], q[1] - c[1]
            return (c[0] + x * math.cos(t) - y * math.sin(t), c[1] + x * math.sin(t) + y * math.cos(t))
        def by_id(): return {s["id"]: s for s in strokes(pg, "p4")}
        def box_centre(): bx = sel(pg)["box"]; return ((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2)
        def ring_target(deg):              # where the pen ends for a turn of deg degrees (the ring's own angle plus deg)
            c = box_centre(); r = pg.evaluate(RING_JS)
            a = math.atan2(r[1] - c[1], r[0] - c[0]) + math.radians(deg); R = math.hypot(r[0] - c[0], r[1] - c[1]) * 1.4
            return c, (r[0], r[1]), (c[0] + R * math.cos(a), c[1] + R * math.sin(a))
        def turn_sel(deg):
            c, r, t = ring_target(deg); drag_page(pg, 1, r, t, steps=12); return c
        def select_box(a, b_):
            tap_page(pg, 1, 760, 1100)                               # a tap on empty paper clears any selection first
            drag_page(pg, 1, a, b_)

        R0 = [[200, 300], [400, 300], [400, 420], [200, 420]]
        pg.evaluate(PUT_JS, ["p4", [rec("r1", "shape", {"type": "rect", "points": R0}, k=0)]])
        tool(pg, "select")
        select_box((180, 280), (420, 440))
        rg = pg.evaluate(RING_JS); bx = sel(pg)["box"] if sel(pg) else None; z = zoom(pg); cr = pg.evaluate(CORN_JS)
        check("the rect is selected; one turn ring and its stem, the four corners still four",
              sel(pg) and sel(pg)["ids"] == ["r1"] and rg is not None and pg.locator("svg.ink g.sel line.selstem").count() == 1 and len(cr) == 4, [sel(pg), rg])
        if rg and bx:
            check("the ring: centred above the top edge, 28 px above it on screen, a corner handle's size",
                  abs(rg[0] - (bx[0] + bx[2]) / 2) < 0.2 and abs(((bx[1] - 4 / z) - rg[1]) * z - 28) < 0.3 and abs(rg[2] - cr[0][2]) < 1e-6, [rg, bx, z, cr[0]])
            rx_, ry_ = screen(pg, 1, rg[0], rg[1])
            hit = pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e ? !!e.closest('button') : true; }", [rx_, ry_])
            check("the Copy and Delete chips never cover the ring (they move right of it on a narrow box)", not hit)
        u0 = U(pg)
        c = turn_sel(40)
        P1 = by_id()["r1"]["data"]["points"]; exp = [rot_about(q, c, 40) for q in R0]
        check("a drag of the ring through 40 degrees turns the rect: its four points turned about the box centre (1 px)",
              all(near(p, e, 1) for p, e in zip(P1, exp)), [P1, exp])
        check("one undo step, the rect stays selected, no transform left on it", U(pg) == u0 + 1 and sel(pg) and sel(pg)["ids"] == ["r1"] and elinfo(pg, 1, "r1")["transform"] is None, [U(pg), u0])
        sb = sel(pg)["box"]
        check("the box afterwards is the upright box around the turned rect", abs(sb[0] - (min(p[0] for p in P1) - 1.25)) < 0.2 and abs(sb[3] - (max(p[1] for p in P1) + 1.25)) < 0.2, [sb, P1])
        undo(pg)
        check("undo puts it back", by_id()["r1"]["data"]["points"] == R0, by_id()["r1"]["data"]["points"])
        c = turn_sel(88.5)
        P2 = by_id()["r1"]["data"]["points"]; exp = [rot_about(q, c, 90) for q in R0]
        check("a drag ending 1.5 degrees short of 90 snaps to exactly 90", all(near(p, e, 0.11) for p, e in zip(P2, exp)), [P2, exp])
        undo(pg)
        u1 = U(pg)
        turn_sel(1)
        check("a drag ending at 1 degree: no change, no undo step", by_id()["r1"]["data"]["points"] == R0 and U(pg) == u1, [U(pg), u1])

        # an ellipse: data.angle, rotate(angle cx cy), turned handles, the E handle still sets rx only
        pg.evaluate(PUT_JS, ["p4", [rec("e1", "shape", {"type": "ellipse", "cx": 560, "cy": 700, "rx": 110, "ry": 50}, k=1)]])
        select_box((430, 630), (690, 770))
        check("the ellipse alone is selected", sel(pg) and sel(pg)["ids"] == ["e1"], sel(pg))
        turn_sel(30)
        e = by_id()["e1"]["data"]
        check("an ellipse turned 30 degrees has angle 30, its centre and radii kept", e.get("angle") == 30 and e["cx"] == 560 and e["cy"] == 700 and e["rx"] == 110 and e["ry"] == 50, e)
        tr = elinfo(pg, 1, "e1")["transform"]
        check("its element carries rotate(30 560 700)", tr == "rotate(30 560 700)", tr)
        H = pg.evaluate(HND_JS, "e1")
        expH = [rot_about(q, (560, 700), 30) for q in [(560, 650), (670, 700), (560, 750), (450, 700)]]
        check("its handles are turned with it (N, E, S, W)", all(near(h, x, 0.01) for h, x in zip(H, expH)), [H, expH])
        tool(pg, "pen")
        t30 = math.radians(30)
        grab_page(pg, 1, (H[1][0], H[1][1]), (H[1][0] + 30 * math.cos(t30), H[1][1] + 30 * math.sin(t30)), steps=8)   # pw-v4v: a select-tool grab
        e2 = by_id()["e1"]["data"]
        check("dragging its E handle afterwards changes only rx (+30, in its own frame)",
              abs(e2["rx"] - 140) <= 0.2 and e2["ry"] == 50 and e2["cx"] == 560 and e2["cy"] == 700 and e2.get("angle") == 30, e2)
        tr = elinfo(pg, 1, "e1")["transform"]
        check("... and it is still drawn turned", tr == "rotate(30 560 700)", tr)

        # two freehand strokes turn together (real pen events this time)
        F1 = [[150, 900], [200, 920], [250, 900]]; F2 = [[150, 960], [200, 980], [250, 960]]
        pg.evaluate(PUT_JS, ["p4", [rec("f1", "pen", {"points": F1}, k=2), rec("f2", "pen", {"points": F2}, k=3)]])
        tool(pg, "select")
        select_box((130, 880), (270, 1000))
        check("both freehand strokes selected", sel(pg) and sorted(sel(pg)["ids"]) == ["f1", "f2"], sel(pg))
        c, r, t = ring_target(60)
        pen = Pen(ctx, pg)
        pen.stroke([screen(pg, 1, *r), screen(pg, 1, *t)], steps=10)
        G2 = by_id()
        ok = all(near(p, rot_about(q, c, 60), 1) for sid, Q in (("f1", F1), ("f2", F2)) for p, q in zip(G2[sid]["data"]["points"], Q))
        check("a selection of two freehand strokes turns both (60 degrees, about the box centre)", ok, [G2["f1"]["data"]["points"], G2["f2"]["data"]["points"], c])
        ctx.close()

        # FRONT: a moved selection comes to the front of its own layer group
        ctx, pg, e19 = fresh(b); errs += e19
        open_note(pg, "Select")
        draw(pg, 1, [(150, 200), (250, 220), (350, 200)])
        draw(pg, 1, [(150, 280), (250, 300), (350, 280)])
        draw(pg, 1, [(150, 360), (250, 380), (350, 360)])
        A, B, C = [s["id"] for s in strokes(pg, "p4")]
        tool(pg, "select")
        select_box((130, 185), (370, 235))
        check("A alone selected", sel(pg) and sel(pg)["ids"] == [A], sel(pg))
        u0 = U(pg)
        drag_page(pg, 1, (250, 212), (290, 212))
        so, dom = [s["id"] for s in strokes(pg, "p4")], pg.evaluate(ORDER_JS, A)
        check("A moved 40 px is now last: in seq order and in the DOM (g.pen), which agree", so == [B, C, A] and dom["ids"] == [B, C, A] and dom["group"] == "pen", [so, dom, [A, B, C]])
        check("the move is one undo step, A still selected", U(pg) == u0 + 1 and sel(pg)["ids"] == [A])
        undo(pg)
        so, dom = [s["id"] for s in strokes(pg, "p4")], pg.evaluate(ORDER_JS, A)
        check("undo puts A back first, in both orders", so == [A, B, C] and dom["ids"] == [A, B, C], [so, dom])
        u1 = U(pg)
        drag_page(pg, 1, (250, 212), (250, 212), steps=2)
        so, dom = [s["id"] for s in strokes(pg, "p4")], pg.evaluate(ORDER_JS, A)
        check("a selection tapped and not moved keeps its order (and is no undo step)", so == [A, B, C] and dom["ids"] == [A, B, C] and U(pg) == u1, [so, dom])
        tool(pg, "highlighter")
        draw(pg, 1, [(450, 600), (650, 600)])
        draw(pg, 1, [(450, 680), (650, 680)])
        draw(pg, 1, [(450, 760), (650, 760)])
        H1, H2, H3 = [s["id"] for s in strokes(pg, "p4")][3:]
        check("three highlighter strokes", all(by_id()[h]["kind"] == "highlighter" for h in (H1, H2, H3)))
        tool(pg, "select")
        select_box((430, 585), (670, 615))
        check("H1 alone selected", sel(pg) and sel(pg)["ids"] == [H1], sel(pg))
        drag_page(pg, 1, (550, 600), (550, 640))
        dom = pg.evaluate(ORDER_JS, H1); so = [s["id"] for s in strokes(pg, "p4")]
        check("a moved highlighter stroke stays in its highlighter group, last there", dom["group"] == "hlo" and dom["ids"] == [H2, H3, H1] and so[-1] == H1, [dom, so])
        check("the pen strokes are not touched by it", pg.evaluate(ORDER_JS, A)["ids"] == [A, B, C])
        ctx.close()

        # WIDTH: a resize keeps the line width (the record, the drawn stroke-width, and mid-drag)
        ctx, pg, e20 = fresh(b); errs += e20
        open_note(pg, "Select")
        pg.evaluate(PUT_JS, ["p4", [rec("w1", "shape", {"type": "rect", "points": [[200, 300], [300, 300], [300, 380], [200, 380]]}, width=4, k=0),
                                    rec("w2", "pen", {"points": [[200, 600], [260, 640], [320, 600]]}, width=4, k=1)]])
        tool(pg, "select")
        def resize_twice():                    # the bottom-right corner along the diagonal to twice the size; returns the mid-drag look
            q = pg.evaluate(CORN_JS); o, c2 = q[0], q[2]
            at = lambda s: (o[0] + s * (c2[0] - o[0]), o[1] + s * (c2[1] - o[1]))
            sx, sy = screen(pg, 1, c2[0], c2[1]); pg.mouse.move(sx, sy); pg.mouse.down()
            mx, my = screen(pg, 1, *at(1.5)); pg.mouse.move(mx, my, steps=8); pg.wait_for_timeout(40)
            sid = sel(pg)["ids"][0]; mid = (elinfo(pg, 1, sid), pg.evaluate(BBW_JS, sid))
            tx, ty = screen(pg, 1, *at(2)); pg.mouse.move(tx, ty, steps=8); pg.mouse.up(); pg.wait_for_timeout(40)
            return mid
        for sid, a_, b_, w0, what in (("w1", (180, 280), (320, 400), 100, "a rect"), ("w2", (180, 580), (340, 660), 120, "a freehand stroke")):
            select_box(a_, b_)
            if not (sel(pg) and sel(pg)["ids"] == [sid]): check(f"{what} alone selected", False, sel(pg)); continue
            bw0 = pg.evaluate(BBW_JS, sid)
            mid, bwm = resize_twice()
            check(f"{what}: mid-drag it already shows bigger, its stroke-width still 4, no transform on it",
                  mid["width"] == "4" and mid["transform"] is None and bwm > bw0 * 1.3, [mid, bw0, bwm])
            r_ = by_id()[sid]; pts = r_["data"]["points"]; w = max(p[0] for p in pts) - min(p[0] for p in pts)
            check(f"{what} resized to twice its size still has width 4 (the record and the drawn stroke-width)",
                  abs(w - 2 * w0) < 1.5 and r_["style"]["width"] == 4 and elinfo(pg, 1, sid)["width"] == "4", [w, r_["style"], elinfo(pg, 1, sid)])
        check("no page errors in the rotate, front, width group", not (e18 or e19 or e20), [e18, e19, e20])
        ctx.close()

        # ------------------------------------------------------------ pw-v4h: the turn ring flips below the box near the page top
        group[0] = "ring flips near the page top"
        ctx, pg, e21 = fresh(b); errs += e21
        open_note(pg, "Select")
        RB_JS = """() => { const g = document.querySelector('svg.ink g.sel'); if (!g) return null;
          const k = g.querySelector('circle.selrot'), b = g.querySelector('rect.selbox'), s = g.querySelector('line.selstem');
          const c = document.querySelector('.selChips');
          return { ring: [+k.getAttribute('cx'), +k.getAttribute('cy'), +k.getAttribute('r')], top: +b.getAttribute('y'), bottom: +b.getAttribute('y') + +b.getAttribute('height'),
            left: +b.getAttribute('x'), stem: [+s.getAttribute('y1'), +s.getAttribute('y2')], chipsLeft: c ? c.getBoundingClientRect().left : null,
            boxLeft: b.getBoundingClientRect().left, rot: window.__pw.ink.selection() && true }; }"""
        T0 = [[200, 10], [400, 10], [400, 130], [200, 130]]
        M0 = [[200, 500], [400, 500], [400, 620], [200, 620]]
        pg.evaluate(PUT_JS, ["p4", [rec("t1", "shape", {"type": "rect", "points": T0}, k=0), rec("m1", "shape", {"type": "rect", "points": M0}, k=1)]])
        tool(pg, "select")
        select_box((180, 2), (420, 150))
        z = zoom(pg); rb = pg.evaluate(RB_JS)
        check("the rect 10 px from the page top is selected", sel(pg) and sel(pg)["ids"] == ["t1"], sel(pg))
        if rb:
            check("its ring is BELOW the box: the ring's cy is greater than the box's bottom, 28 px on screen under it",
                  rb["ring"][1] > rb["bottom"] and abs((rb["ring"][1] - rb["bottom"]) * z - 28) < 0.3, [rb, z])
            check("the stem runs from the bottom edge to the ring's top", abs(rb["stem"][0] - rb["bottom"]) < 0.01 and abs(rb["stem"][1] - (rb["ring"][1] - rb["ring"][2])) < 0.01, rb)
            check("the ring is centred under the box and no part of the selection UI is above the page's top edge", abs(rb["ring"][0] - 300) < 0.2 and rb["top"] > -0.5, rb)
            check("the Copy and Delete chips sit at the box's top-left (not pushed right of a ring)", abs(rb["chipsLeft"] - rb["boxLeft"]) < 3, rb)
        u0 = U(pg)
        c = turn_sel(40)
        P1 = by_id()["t1"]["data"]["points"]; exp = [rot_about(q, c, 40) for q in T0]
        check("dragging the lower ring still turns the rect through 40 degrees about its centre (1 px)", all(near(p, e, 1) for p, e in zip(P1, exp)) and U(pg) == u0 + 1, [P1, exp, U(pg), u0])
        undo(pg)
        select_box((180, 480), (420, 640))
        rb2 = pg.evaluate(RB_JS)
        check("a rect in the middle of the page keeps its ring above the box", sel(pg) and sel(pg)["ids"] == ["m1"] and rb2 and rb2["ring"][1] < rb2["top"] and abs(rb2["stem"][0] - rb2["top"]) < 0.01, [sel(pg), rb2])
        check("no page errors in the ring flip group", not e21, e21)
        ctx.close()

        # ------------------------------------------------------------ pw-v4j: tap selects one stroke, finger tap deselects, degrees, icon chips
        group[0] = "select polish (pw-v4j)"
        ctx, pg, e22 = fresh(b, has_touch=True); errs += e22
        open_note(pg, "Select")
        RING_JS = """() => { const c = document.querySelector('svg.ink g.sel circle.selrot'); return c ? [+c.getAttribute('cx'), +c.getAttribute('cy'), +c.getAttribute('r')] : null; }"""
        DEG_JS = """() => { const d = document.querySelector('.selDeg'); if (!d) return null; const r = d.getBoundingClientRect();
          return { text: d.textContent, shown: getComputedStyle(d).display !== 'none' && r.width > 0, left: r.left, cy: r.top + r.height / 2, h: Math.round(r.height) }; }"""
        CHIP_JS = """() => [...document.querySelectorAll('.selChips .chip')].map(b => ({ act: b.dataset.act, text: b.textContent.trim(), svgs: b.querySelectorAll('svg').length,
          label: b.getAttribute('aria-label'), title: b.title, w: Math.round(b.getBoundingClientRect().width), h: Math.round(b.getBoundingClientRect().height),
          round: getComputedStyle(b).borderRadius }))"""
        def by_id(): return {s["id"]: s for s in strokes(pg, "p4")}
        def seg_d(p, a, c):
            dx, dy = c[0] - a[0], c[1] - a[1]; L2 = dx * dx + dy * dy or 1
            t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            return math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1])
        def rect_d(p, pts): return min(seg_d(p, pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts)))
        draw(pg, 1, [(450, 200), (550, 220), (650, 200)])                                   # a freehand stroke
        draw(pg, 1, rough_square(150, 380, 200), steps=3, hold=650)                         # the first rect
        draw(pg, 1, rough_square(250, 480, 200), steps=3, hold=650)                         # the second, drawn over it
        FH, R1, R2 = [s["id"] for s in strokes(pg, "p4")]
        d1, d2 = by_id()[R1]["data"], by_id()[R2]["data"]
        check("a freehand stroke and two overlapping snapped rects", d1.get("type") == "rect" and d2.get("type") == "rect" and by_id()[R2]["seq"] > by_id()[R1]["seq"], [d1.get("type"), d2.get("type")])
        if d1.get("type") == "rect" and d2.get("type") == "rect":
            P1, P2 = d1["points"], d2["points"]
            X = (max(p[0] for p in P1), min(p[1] for p in P2))                              # the first's right edge meets the second's top edge
            check("the overlap tap point is on both outlines (within 3 px)", rect_d(X, P1) < 3 and rect_d(X, P2) < 3, [X, rect_d(X, P1), rect_d(X, P2)])
            tool(pg, "select")
            u0 = U(pg)
            tap_page(pg, 1, *X)
            check("a tap on the overlap selects ONLY the second rect (the higher seq)", sel(pg) and sel(pg)["ids"] == [R2], sel(pg))
            check("the tap is not an undo step", U(pg) == u0)
            bx = sel(pg)["box"]
            drag_page(pg, 1, (bx[2] - 20, bx[3] - 20), (bx[2] - 20, bx[3] + 80))           # move the second 100 px down
            P2m = by_id()[R2]["data"]["points"]
            check("the second moved 100 px down", abs(min(p[1] for p in P2m) - (min(p[1] for p in P2) + 100)) < 0.6, [P2, P2m])
            tap_page(pg, 1, *X)
            check("a tap where the first now shows selects only the first", sel(pg) and sel(pg)["ids"] == [R1], sel(pg))
            tap_page(pg, 1, 700, 1050)
            check("a tap on empty paper: no selection", sel(pg) is None and not selui(pg)["g"], sel(pg))
            tap_page(pg, 1, 550, 220)
            check("a tap on a freehand stroke selects it alone", sel(pg) and sel(pg)["ids"] == [FH], sel(pg))
            tap_page(pg, 1, 700, 1050)
            drag_page(pg, 1, (130, 360), (480, 800))
            check("a drag box over both rects still selects both", sel(pg) and sorted(sel(pg)["ids"]) == sorted([R1, R2]), sel(pg))
            check("no page errors so far (tap select)", not e22, e22)

            # finger taps: real touches through CDP
            cdp = ctx.new_cdp_session(pg)
            def touch(kind, x=0, y=0): cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}]})
            def ftap(px, py):
                x, y = screen(pg, 1, px, py); touch("touchStart", x, y); pg.wait_for_timeout(30); touch("touchEnd"); pg.wait_for_timeout(60)
            def fpan(px, py, dy, n=8):
                x, y = screen(pg, 1, px, py); touch("touchStart", x, y)
                for k in range(1, n + 1): touch("touchMove", x, y + dy * k / n); pg.wait_for_timeout(16)
                touch("touchEnd"); pg.wait_for_timeout(300)
            n0, u1 = len(strokes(pg, "p4")), U(pg)
            ftap(300, 600)
            check("a finger tap inside the selection's box keeps it", sel(pg) and sorted(sel(pg)["ids"]) == sorted([R1, R2]), sel(pg))
            y0 = pg.locator("#stack .sheet[data-index='1']").bounding_box()["y"]
            fpan(650, 950, -80)
            y1 = pg.locator("#stack .sheet[data-index='1']").bounding_box()["y"]
            check("a finger pan of 80 px (outside the box) pans (at least 60 px: a quick swipe may glide further) and keeps the selection", (y0 - y1) >= 60 and sel(pg) and sorted(sel(pg)["ids"]) == sorted([R1, R2]), [y0, y1, sel(pg)])
            ftap(650, 1000)
            check("a finger tap outside the selection clears it", sel(pg) is None and not selui(pg)["g"] and not selui(pg)["chips"], sel(pg))
            check("the finger taps drew nothing and made no undo step", len(strokes(pg, "p4")) == n0 and U(pg) == u1, [len(strokes(pg, "p4")), n0, U(pg), u1])
            drag_page(pg, 1, (130, 360), (480, 800))
            check("selected again (both)", sel(pg) and len(sel(pg)["ids"]) == 2, sel(pg))
            tool(pg, "pen")
            P1now = by_id()[R1]["data"]["points"]
            ftap(*P1now[0])                                                                 # on a rect corner: a pen there would grab it
            check("with the pen tool on, a finger tap leaves no selection, grabs no handle, draws nothing",
                  sel(pg) is None and by_id()[R1]["data"]["points"] == P1now and len(strokes(pg, "p4")) == n0 and U(pg) == u1, [sel(pg), len(strokes(pg, "p4")), U(pg)])
            tool(pg, "select")

            # the turn shows its degrees
            tap_page(pg, 1, 700, 1050)
            tap_page(pg, 1, *P1now[0])
            check("the first rect selected by a tap on its corner", sel(pg) and sel(pg)["ids"] == [R1], sel(pg))
            dg = pg.evaluate(DEG_JS)
            check("the degrees label exists and is hidden while not turning", dg is not None and not dg["shown"], dg)
            def turn_live(deg):
                bx_ = sel(pg)["box"]; c = ((bx_[0] + bx_[2]) / 2, (bx_[1] + bx_[3]) / 2); r = pg.evaluate(RING_JS)
                a = math.atan2(r[1] - c[1], r[0] - c[0]) + math.radians(deg); R = math.hypot(r[0] - c[0], r[1] - c[1]) * 1.4
                t = (c[0] + R * math.cos(a), c[1] + R * math.sin(a))
                sx, sy = screen(pg, 1, r[0], r[1]); pg.mouse.move(sx, sy); pg.mouse.down()
                tx, ty = screen(pg, 1, *t); pg.mouse.move(tx, ty, steps=12); pg.wait_for_timeout(40)
                mid = pg.evaluate(DEG_JS)
                pg.mouse.up(); pg.wait_for_timeout(40)
                return mid, (sx, sy), pg.evaluate(DEG_JS)
            mid, rs, after = turn_live(45)
            check("during a 45 degree turn .selDeg shows and reads 45°", mid and mid["shown"] and mid["text"] == "45°", mid)
            check("... a 28 px pill just right of the ring", mid and mid["h"] == 28 and 0 < mid["left"] - rs[0] < 30 and abs(mid["cy"] - rs[1]) < 3, [mid, rs])
            check("after the lift it is hidden", after and not after["shown"], after)
            mid, rs, after = turn_live(-30)
            check("during a -30 degree turn it reads -30°", mid and mid["shown"] and mid["text"] == "-30°", mid)
            check("... and hides again after the lift", after and not after["shown"], after)

            # the chips are icons
            cs = pg.evaluate(CHIP_JS)
            check("three chips, copy, duplicate, delete, no words, one svg each, aria-label and title Copy / Duplicate / Delete (pw-v4o)",
                  [c_["act"] for c_ in cs] == ["copy", "duplicate", "delete"] and all(c_["text"] == "" and c_["svgs"] == 1 for c_ in cs)
                  and [c_["label"] for c_ in cs] == ["Copy", "Duplicate", "Delete"] and [c_["title"] for c_ in cs] == ["Copy", "Duplicate", "Delete"], cs)
            check("each chip is a 38 px round button", all(c_["w"] == 38 and c_["h"] == 38 and c_["round"] == "50%" for c_ in cs), cs)
            n1 = len(strokes(pg, "p4"))
            pg.locator(".selChips .chip[aria-label='Copy']").click(); pg.wait_for_timeout(30)
            # pw-v4k: flipped, the Copy icon fills the clipboard (no duplicate on the spot, the selection stays)
            check("the Copy icon copies to the clipboard (nothing added, the selection stays)", len(strokes(pg, "p4")) == n1 and sel(pg) and sel(pg)["ids"] == [R1]
                  and pg.evaluate("window.__pw.ink.hasClip()") is True, sel(pg))
            pg.locator(".selChips .chip[aria-label='Delete']").click(); pg.wait_for_timeout(30)
            check("the Delete icon still deletes (the rect goes, the selection clears)", len(strokes(pg, "p4")) == n1 - 1 and sel(pg) is None and R1 not in by_id(), sel(pg))
        check("no page errors in the select polish group", not e22, e22)
        ctx.close()

        # ------------------------------------------------------------ pw-v4m: a tap on an overlap picks the last ink tool's layer
        group[0] = "overlap pick (pw-v4m)"
        ctx, pg, e24 = fresh(b); errs += e24
        open_note(pg, "Select")
        def selids(): s_ = sel(pg); return s_["ids"] if s_ else None
        def line_at(y): return [(200 + 25 * k, y) for k in range(13)]          # (200, y) to (500, y), freehand
        def pick(*ts):
            for t in ts: tool(pg, t)
        tool(pg, "pen"); draw(pg, 1, line_at(400))
        tool(pg, "highlighter"); draw(pg, 1, line_at(400))
        PEN1, HL1 = [s_["id"] for s_ in strokes(pg, "p4")]
        r_ = {s_["id"]: s_ for s_ in strokes(pg, "p4")}
        check("set-up: a pen stroke, then a highlighter stroke over it (the highlighter last-drawn)",
              r_[PEN1]["kind"] == "pen" and r_[HL1]["kind"] == "highlighter" and r_[HL1]["seq"] > r_[PEN1]["seq"], [r_[PEN1]["kind"], r_[HL1]["kind"]])
        pick("pen", "select"); u0 = U(pg); tap_page(pg, 1, 350, 400)
        check("pen, then select: a tap on the overlap selects the PEN stroke", selids() == [PEN1], sel(pg))
        check("the tap is not an undo step", U(pg) == u0)
        pick("highlighter", "select"); tap_page(pg, 1, 350, 400)
        check("highlighter, then select: a tap on the overlap selects the HIGHLIGHTER stroke", selids() == [HL1], sel(pg))
        tool(pg, "pen"); draw(pg, 1, line_at(700)); PEN2 = last(pg, "p4")["id"]
        pick("highlighter", "select"); tap_page(pg, 1, 350, 700)
        check("highlighter last, a tap where only a pen stroke is: that pen stroke", selids() == [PEN2], sel(pg))
        tool(pg, "highlighter"); draw(pg, 1, line_at(900)); HL2 = last(pg, "p4")["id"]
        pick("pen", "select"); tap_page(pg, 1, 350, 900)
        check("pen last, a tap on a lone highlighter stroke: it is selected", selids() == [HL2], sel(pg))
        tool(pg, "pen"); draw(pg, 1, line_at(600)); PEN3 = last(pg, "p4")["id"]
        draw(pg, 1, line_at(600)); PEN4 = last(pg, "p4")["id"]
        pick("highlighter", "select"); tap_page(pg, 1, 350, 600)
        check("two pen strokes overlapping, highlighter last: the topmost pen stroke (highest seq)", PEN3 != PEN4 and selids() == [PEN4], sel(pg))
        pick("pen", "select"); tap_page(pg, 1, 350, 600)
        check("... and with the pen last too", selids() == [PEN4], sel(pg))
        pick("pen", "select"); tap_page(pg, 1, 700, 1050)
        check("a tap on empty paper: no selection", sel(pg) is None, sel(pg))
        check("no page errors so far (overlap pick)", not e24, e24)

        back(pg); open_note(pg, "Snap")
        tool(pg, "pen"); draw(pg, 1, [(350, 250 + 25 * k) for k in range(13)])     # a vertical pen stroke through the circle's top
        LN = last(pg, "p1")["id"]
        tool(pg, "highlighter"); draw(pg, 1, rough_circle(350, 400, 90), steps=3, hold=650)
        C = last(pg, "p1")
        check("set-up: a highlighter-born circle (opacity under 1) over the pen stroke",
              C["kind"] == "shape" and C["data"].get("type") == "circle" and C["style"].get("opacity", 1) < 1 and C["id"] != LN, [C["kind"], C["data"], C["style"]])
        pick("pen", "select"); tap_page(pg, 1, 350, 310)
        check("a shape over a pen stroke, pen last: the pen stroke", selids() == [LN], sel(pg))
        pick("highlighter", "select"); tap_page(pg, 1, 350, 310)
        check("a shape over a pen stroke, highlighter last: the shape", selids() == [C["id"]], sel(pg))
        pick("pen", "highlighter"); pg.reload(); ready(pg); open_note(pg, "Snap")
        check("after a reload the tray shows the highlighter", pg.locator("#tool-highlighter.on").count() == 1)
        tool(pg, "select"); tap_page(pg, 1, 350, 310)
        check("after a reload (highlighter picked) a tap on the overlap still picks the highlighter shape", selids() == [C["id"]], sel(pg))
        pick("pen"); pg.reload(); ready(pg); open_note(pg, "Snap")
        tool(pg, "select"); tap_page(pg, 1, 350, 310)
        check("after a reload (pen picked) a tap on the overlap picks the pen stroke", selids() == [LN], sel(pg))
        check("no page errors in the overlap pick group", not e24, e24)
        ctx.close()

        # ------------------------------------------------------------ pw-v4k: the selection clipboard, hold a finger to paste
        group[0] = "clipboard (pw-v4k)"
        ctx, pg, e23 = fresh(b, has_touch=True); errs += e23
        open_note(pg, "Select")
        cdp = ctx.new_cdp_session(pg)
        def touch(kind, pts=()): cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y, "id": k} for k, (x, y) in enumerate(pts)]})
        def hold(i, px, py, ms=600):                     # one finger down and still for ms; returns the screen point
            x, y = screen(pg, i, px, py); touch("touchStart", [(x, y)]); pg.wait_for_timeout(ms); return x, y
        def lift(): touch("touchEnd"); pg.wait_for_timeout(60)
        MENU_JS = """() => { const m = document.getElementById('menu'), r = m.getBoundingClientRect();
          return { shown: !m.hidden && r.height > 0, left: r.left, top: r.top,
                   items: [...m.querySelectorAll('button')].map(b => ({ label: b.textContent.trim(), disabled: b.disabled })) }; }"""
        def menu(): return pg.evaluate(MENU_JS)
        def paste_btn(): return pg.locator("#menu button").filter(has_text=re.compile("^Paste$"))   # pw-v4p: Select all sits above it
        def sheet_y(i): return pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box()["y"]
        def ids(pid): return [s["id"] for s in strokes(pg, pid)]
        def pbox(recs):                                  # the strokes' box with half the ink width, the way selBox measures
            b_ = [1e9, 1e9, -1e9, -1e9]
            for r in recs:
                w = r["style"]["width"] / 2
                for x, y in r["data"]["points"]: b_ = [min(b_[0], x - w), min(b_[1], y - w), max(b_[2], x + w), max(b_[3], y + w)]
            return b_
        def ctr(b_): return ((b_[0] + b_[2]) / 2, (b_[1] + b_[3]) / 2)
        def tool_now(): return pg.evaluate("window.__pw.ink.tool().tool")
        def tray_on(t): return pg.evaluate(f"document.getElementById('tool-{t}').classList.contains('on')")

        # 6: nothing copied yet: the hold still answers, with a disabled item
        check("a fresh app has an empty clipboard", pg.evaluate("window.__pw.ink.hasClip()") is False)
        hx, hy = hold(1, 400, 500); m0 = menu(); lift()
        check("nothing copied, an empty page: a finger hold opens the menu with two disabled items, 'Nothing to select' then 'Nothing to paste' (pw-v4p)",
              m0["shown"] and m0["items"] == [{"label": "Nothing to select", "disabled": True}, {"label": "Nothing to paste", "disabled": True}], m0)
        check("the menu's top-left sits 8 px down and right of the finger", abs(m0["left"] - (hx + 8)) < 1.5 and abs(m0["top"] - (hy + 8)) < 1.5, [m0, hx, hy])
        check("it stays open after the finger lifts", menu()["shown"])
        pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
        check("Escape closes it", not menu()["shown"])
        pg.evaluate("() => document.getElementById('desk').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 600, clientY: 600 }))")
        pg.wait_for_timeout(30)
        check("a contextmenu on the desk (the pen button) opens no menu", not menu()["shown"])
        check("... it flips the pen to Select instead (pw-v4v)", tool_now() == "select", tool_now())
        pg.evaluate("() => document.getElementById('desk').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 600, clientY: 600 }))")
        check("... and a second press flips back to the pen", tool_now() == "pen" and not menu()["shown"], tool_now())
        ox, oy = screen(pg, 1, -14, 400)
        off = pg.evaluate(f"(() => {{ const e = document.elementFromPoint({ox}, {oy}); return e ? (e.closest('#desk') && !e.closest('.sheet') ? 'desk' : e.tagName) : null; }})()")
        touch("touchStart", [(ox, oy)]); pg.wait_for_timeout(600); m_off = menu(); lift()
        check("a hold off every page (on the desk beside the page) opens nothing", off == "desk" and not m_off["shown"], [off, m_off])

        # 1: Copy puts the selection on the clipboard and adds nothing
        draw(pg, 1, [(150, 200), (250, 220), (350, 200)])
        draw(pg, 1, [(150, 280), (250, 300), (350, 280)])
        draw(pg, 1, [(150, 600), (250, 620), (350, 600)])
        A, B, C = ids("p4")
        tool(pg, "select")
        drag_page(pg, 1, (120, 170), (380, 330))
        check("two of three selected", sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, B]), sel(pg))
        u0, before = U(pg), {s["id"]: s for s in strokes(pg, "p4")}
        pg.locator(".selChips .chip[data-act='copy']").click(); pg.wait_for_timeout(30)
        check("Copy: the page's stroke count is unchanged", len(strokes(pg, "p4")) == 3)
        check("Copy: the selection is still those two", sel(pg) and sorted(sel(pg)["ids"]) == sorted([A, B]), sel(pg))
        check("Copy: hasClip() is true", pg.evaluate("window.__pw.ink.hasClip()") is True)
        check("Copy: no undo step", U(pg) == u0, [U(pg), u0])
        check("Copy: the toast says Copied.", pg.evaluate("document.getElementById('toast').textContent") == "Copied." and pg.evaluate("document.getElementById('toast').classList.contains('show')"))
        tool(pg, "pen")                                    # the paste must turn select on by itself
        check("the pen tool is on before the paste", tool_now() == "pen" and tray_on("pen"))

        # 2: hold on page 1 and paste
        y_before = sheet_y(1)
        hx, hy = hold(1, 500, 760); m1 = menu(); lift()
        check("a finger held still 600 ms: the menu shows two items, Select all then Paste (pw-v4p)", m1["shown"] and m1["items"] == [{"label": "Select all", "disabled": False}, {"label": "Paste", "disabled": False}], m1)
        check("the hold did not pan the page", abs(sheet_y(1) - y_before) < 0.5, [sheet_y(1), y_before])
        check("the hold drew nothing", len(strokes(pg, "p4")) == 3)
        u1 = U(pg)
        paste_btn().tap(); pg.wait_for_timeout(60)
        all_ = strokes(pg, "p4"); news = [s for s in all_ if s["id"] not in (A, B, C)]
        check("Paste: the menu closes", not menu()["shown"])
        check("Paste: the page gains two strokes, with new ids", len(all_) == 5 and len(news) == 2, [len(all_), len(news)])
        if len(news) == 2:
            c_ = ctr(pbox(news))
            check("Paste: the new box's centre is on the hold point (2 px)", near(c_, (500, 760), 2), c_)
            check("Paste: their seq values are above every old one", min(s["seq"] for s in news) > max(before[k]["seq"] for k in before), [s["seq"] for s in news])
            c0 = ctr(pbox([before[A], before[B]])); dx_, dy_ = c_[0] - c0[0], c_[1] - c0[1]
            first = sorted(news, key=lambda s: s["seq"])
            check("Paste: in the copied order, each a moved copy (A first, then B)",
                  near(first[0]["data"]["points"][0], (before[A]["data"]["points"][0][0] + dx_, before[A]["data"]["points"][0][1] + dy_), 0.3)
                  and near(first[1]["data"]["points"][0], (before[B]["data"]["points"][0][0] + dx_, before[B]["data"]["points"][0][1] + dy_), 0.3)
                  and first[0]["style"] == before[A]["style"] and first[0]["page_id"] == "p4", [first[0]["data"]["points"][0], before[A]["data"]["points"][0], dx_, dy_])
            check("Paste: the originals are untouched", all(next(s for s in all_ if s["id"] == k) == before[k] for k in before))
            check("Paste: the pasted two are selected", sel(pg) and sorted(sel(pg)["ids"]) == sorted(s["id"] for s in news), sel(pg))
            check("Paste: the tool is select, and the tray's select button is lit", tool_now() == "select" and tray_on("select") and not tray_on("pen"))
            check("Paste: one undo step", U(pg) == u1 + 1, [U(pg), u1])
            undo(pg)
            check("undo removes both", ids("p4") == [A, B, C] and sel(pg) is None, [ids("p4"), sel(pg)])
            redo(pg)
            check("redo brings them back", sorted(ids("p4")) == sorted([A, B, C] + [s["id"] for s in news]))
            check("the clipboard keeps its contents after a paste", pg.evaluate("window.__pw.ink.hasClip()") is True)
            hold(1, 600, 950); lift()
            paste_btn().tap(); pg.wait_for_timeout(60)
            check("paste twice: two more copies (seven strokes)", len(strokes(pg, "p4")) == 7)

        # 5: a moving finger, two fingers: no menu (here, in a two page note, where the desk has room to pan)
        pg.keyboard.press("Escape")
        n5, y0 = len(strokes(pg, "p4")), sheet_y(1)
        x, y = screen(pg, 1, 400, 700); touch("touchStart", [(x, y)])
        for k in range(1, 11): touch("touchMove", [(x, y - 2 * k)]); pg.wait_for_timeout(16)
        pg.wait_for_timeout(600); m5 = menu(); touch("touchEnd"); pg.wait_for_timeout(300)
        check("a finger that moves 20 px during the hold: no menu", not m5["shown"], m5)
        check("... and the desk panned 20 px", abs((y0 - sheet_y(1)) - 20) < 2, [y0, sheet_y(1)])
        x, y = screen(pg, 1, 300, 500)
        touch("touchStart", [(x, y), (x + 120, y + 60)]); pg.wait_for_timeout(700); m6 = menu(); touch("touchEnd"); pg.wait_for_timeout(100)
        check("two fingers held still: no menu", not m6["shown"], m6)
        check("the fingers drew and pasted nothing", len(strokes(pg, "p4")) == n5)
        # 3: page 2, then another note
        go_page(pg, 2)
        if pg.locator("#pageList").is_visible(): pg.click("#plClose"); pg.wait_for_timeout(60)
        hold(2, 400, 500); m2 = menu(); lift()
        check("a hold on the empty page 2 opens 'Nothing to select' (disabled) then Paste (pw-v4p)", m2["shown"] and m2["items"] == [{"label": "Nothing to select", "disabled": True}, {"label": "Paste", "disabled": False}], m2)
        paste_btn().tap(); pg.wait_for_timeout(60)
        p2 = strokes(pg, "p4b")
        check("pasted on page 2: the two land there, centred on the hold", len(p2) == 2 and all(s["page_id"] == "p4b" for s in p2) and near(ctr(pbox(p2)), (400, 500), 2),
              [len(p2), ctr(pbox(p2)) if p2 else None])
        check("page 1 is unchanged by the page 2 paste", len(strokes(pg, "p4")) == n5)
        back(pg)
        open_note(pg, "Erase")
        check("the clipboard survives closing the note", pg.evaluate("window.__pw.ink.hasClip()") is True)
        hold(1, 300, 400); lift()
        paste_btn().tap(); pg.wait_for_timeout(60)
        p5 = strokes(pg, "p5")
        check("another note: the paste lands there (the clipboard crossed notes)", len(p5) == 2 and all(s["page_id"] == "p5" for s in p5) and near(ctr(pbox(p5)), (300, 400), 2),
              [len(p5), ctr(pbox(p5)) if p5 else None])

        # 4: near a page edge the box is kept inside the page
        W, H = 794, 1123
        seen = {r["id"] for r in strokes(pg, "p5")}
        hold(1, 785, 1110); lift()
        paste_btn().tap(); pg.wait_for_timeout(60)
        e1 = [s for s in strokes(pg, "p5") if s["id"] not in seen]
        bb_ = pbox(e1) if e1 else None
        check("a hold near the bottom-right corner: the pasted box stays inside the page, against both edges",
              len(e1) == 2 and bb_[2] <= W + 0.11 and bb_[3] <= H + 0.11 and abs(bb_[2] - W) < 0.6 and abs(bb_[3] - H) < 0.6 and bb_[0] >= 0 and bb_[1] >= 0, bb_)
        seen = {r["id"] for r in strokes(pg, "p5")}
        hold(1, 6, 8); lift()
        paste_btn().tap(); pg.wait_for_timeout(60)
        e2 = [s for s in strokes(pg, "p5") if s["id"] not in seen]
        bb2 = pbox(e2) if e2 else None
        check("a hold near the top-left corner: the box is kept inside, against the top and left edges",
              len(e2) == 2 and bb2[0] >= -0.11 and bb2[1] >= -0.11 and abs(bb2[0]) < 0.6 and abs(bb2[1]) < 0.6, bb2)

        # 5 (the pen): a pen held still opens no menu
        pg.keyboard.press("Escape")
        n5 = len(strokes(pg, "p5"))
        tool(pg, "pen")
        pen = Pen(ctx, pg)
        pen.stroke([screen(pg, 1, *q) for q in rough_line(300, 100, 420)], hold=700)
        lp = last(pg, "p5")
        check("a pen held still: no menu, and its hold still snaps (a line)", not menu()["shown"] and lp and lp["kind"] == "shape" and lp["data"].get("type") == "line" and len(strokes(pg, "p5")) == n5 + 1,
              [menu(), lp and lp["kind"], lp and lp["data"].get("type")])
        check("no page errors in the clipboard group", not e23, e23)
        ctx.close()

        # ------------------------------------------------------------ pw-v4o: the Duplicate chip
        group[0] = "duplicate chip (pw-v4o)"
        ctx, pg, e25 = fresh(b); errs += e25
        open_note(pg, "Select")
        PUTD_JS = "([pid, recs]) => import('./js/ink.js').then(m => m.put(pid, recs))"
        CHIPS_JS = """() => { const c = document.querySelector('.selChips'); if (!c) return null; const r = c.getBoundingClientRect();
          return { n: c.querySelectorAll('button').length, labels: [...c.querySelectorAll('button')].map(b => b.getAttribute('aria-label')),
                   acts: [...c.querySelectorAll('button')].map(b => b.dataset.act), left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                   vw: window.innerWidth, vh: window.innerHeight }; }"""
        DUPSTYLE_JS = """() => { const d = document.querySelector('.selChips .chip[data-act="duplicate"]'), c = document.querySelector('.selChips .chip[data-act="copy"]');
          const k = (e) => { const s = getComputedStyle(e), v = e.querySelector('svg'); return [s.backgroundColor, s.color, s.width, s.height, s.borderRadius,
            v.getAttribute('stroke-width'), v.getAttribute('viewBox'), getComputedStyle(v).width]; };
          return d && c ? { dup: k(d), copy: k(c), title: d.title, svgs: d.querySelectorAll('svg').length, text: d.textContent.trim() } : null; }"""
        RINGD_JS = """() => { const c = document.querySelector('svg.ink g.sel circle.selrot'); return c ? [+c.getAttribute('cx'), +c.getAttribute('cy')] : null; }"""
        def byid(): return {s_["id"]: s_ for s_ in strokes(pg, "p4")}
        def dup(): pg.locator(".selChips .chip[data-act='duplicate']").click(); pg.wait_for_timeout(40)
        def selids(): s_ = sel(pg); return sorted(s_["ids"]) if s_ else None
        def moved(o, n, d=24): return len(o) == len(n) and all(abs(q[0] - (p_[0] + d)) < 1e-6 and abs(q[1] - (p_[1] + d)) < 1e-6 for p_, q in zip(o, n))
        def dbox(recs):
            b_ = [1e9, 1e9, -1e9, -1e9]
            for r in recs:
                w = r["style"]["width"] / 2
                for x, y in r["data"]["points"]: b_ = [min(b_[0], x - w), min(b_[1], y - w), max(b_[2], x + w), max(b_[3], y + w)]
            return b_

        # 1: three chips, Copy, Duplicate, Delete
        draw(pg, 1, [(150, 200), (250, 220), (350, 200)])
        draw(pg, 1, [(150, 280), (250, 300), (350, 280)])
        draw(pg, 1, [(150, 600), (250, 620), (350, 600)])
        A, B, C = [s_["id"] for s_ in strokes(pg, "p4")]
        tool(pg, "select")
        drag_page(pg, 1, (120, 170), (380, 330))
        ch = pg.evaluate(CHIPS_JS)
        check("two strokes selected: three chips, aria-labels in order Copy, Duplicate, Delete",
              selids() == sorted([A, B]) and ch and ch["n"] == 3 and ch["labels"] == ["Copy", "Duplicate", "Delete"] and ch["acts"] == ["copy", "duplicate", "delete"], [sel(pg), ch])
        ds = pg.evaluate(DUPSTYLE_JS)
        check("the Duplicate chip looks like the Copy chip (colours, size, round, icon stroke and size), one svg, no words, title Duplicate",
              ds and ds["dup"] == ds["copy"] and ds["svgs"] == 1 and ds["text"] == "" and ds["title"] == "Duplicate", ds)

        # 2: Duplicate adds two copies 24 px right and down, selected, one undo step, the clipboard untouched
        old = byid(); u0 = U(pg); clip0 = pg.evaluate("window.__pw.ink.hasClip()")
        dup()
        now_ = byid(); new_ids = [k for k in now_ if k not in old]
        news = sorted([now_[k] for k in new_ids], key=lambda r: r["seq"]); origs = sorted([old[A], old[B]], key=lambda r: r["seq"])
        check("Duplicate: the page has two more records with new ids", len(now_) == 5 and len(new_ids) == 2 and all(k in now_ for k in old), [len(now_), new_ids])
        check("Duplicate: the copies' seq values are above every old one, in the originals' order",
              len(news) == 2 and min(r["seq"] for r in news) > max(r["seq"] for r in old.values()) and news[0]["seq"] < news[1]["seq"], [r["seq"] for r in news])
        check("Duplicate: each copy is its original with every point moved by exactly (+24, +24), same kind and style",
              len(news) == 2 and all(moved(o["data"]["points"], n["data"]["points"]) and o["kind"] == n["kind"] and o["style"] == n["style"] and n["page_id"] == "p4" for o, n in zip(origs, news)),
              [(o["data"]["points"][:2], n["data"]["points"][:2]) for o, n in zip(origs, news)])
        check("Duplicate: the originals are unchanged", all(now_[k] == old[k] for k in old))
        check("Duplicate: the selection is the two NEW ids, the tool stays select", selids() == sorted(new_ids) and pg.evaluate("window.__pw.ink.tool().tool") == "select", [sel(pg), new_ids])
        check("Duplicate: one undo step", U(pg) == u0 + 1, [U(pg), u0])
        check("Duplicate: hasClip() unchanged (false, nothing was copied)", clip0 is False and pg.evaluate("window.__pw.ink.hasClip()") is False)

        # 3: undo takes the copies away (the selection clears), redo brings them back
        undo(pg)
        check("undo: the two copies are gone, the originals stay", sorted(byid()) == sorted(old), sorted(byid()))
        check("undo: the selection is cleared (its strokes are gone)", sel(pg) is None and not selui(pg)["chips"], sel(pg))
        redo(pg)
        rd = byid()
        check("redo: the two copies are back, same ids and points", len(rd) == 5 and all(r["id"] in rd and moved(r["data"]["points"], rd[r["id"]]["data"]["points"], 0) for r in news), sorted(rd))
        undo(pg)

        # 4: Duplicate twice in a row copies the copies (another +24, +24), four records added in all
        drag_page(pg, 1, (120, 170), (380, 330))
        check("the originals selected again", selids() == sorted([A, B]), sel(pg))
        u1 = U(pg)
        dup(); first = byid(); f_ids = [k for k in first if k not in old]
        dup(); second = byid(); s_ids = [k for k in second if k not in first]
        f_recs = sorted([first[k] for k in f_ids], key=lambda r: r["seq"]); s_recs = sorted([second[k] for k in s_ids], key=lambda r: r["seq"])
        check("twice: four records added in all, two undo steps", len(second) == 7 and len(f_ids) == 2 and len(s_ids) == 2 and U(pg) == u1 + 2, [len(second), U(pg), u1])
        check("twice: the second copies are the first copies moved by another (+24, +24)", len(s_recs) == 2 and all(moved(f["data"]["points"], s2["data"]["points"]) for f, s2 in zip(f_recs, s_recs)))
        check("twice: the selection is the second copies", selids() == sorted(s_ids), [sel(pg), s_ids])
        undo(pg); undo(pg)
        check("two undos: back to the three strokes", sorted(byid()) == sorted(old))

        # 5: a box touching the page's bottom-right corner: the duplicate stays inside the page
        W, H = 794, 1123
        st2 = {"colour": "#000000", "width": 2, "dash": "solid", "opacity": 1}
        pg.evaluate(PUTD_JS, ["p4", [{"id": "dc1", "page_id": "p4", "seq": int(time.time() * 1000) + 5, "kind": "pen", "style": st2,
                                      "data": {"points": [[700, 1040], [750, 1080], [793, 1122]]}}]])
        tap_page(pg, 1, 400, 900)
        drag_page(pg, 1, (680, 1020), (790, 1110))
        bx0 = sel(pg)["box"] if sel(pg) else None
        check("the corner stroke is selected, its box touches the page's bottom-right corner", selids() == ["dc1"] and bx0 and abs(bx0[2] - W) < 1e-6 and abs(bx0[3] - H) < 1e-6, [sel(pg)])
        pre = byid(); dup(); cn = [r for k, r in byid().items() if k not in pre]
        cb_ = dbox(cn) if cn else None
        check("the duplicate of a corner box stays inside the page (right edge <= page width, bottom edge <= page height)",
              len(cn) == 1 and cb_[2] <= W + 1e-6 and cb_[3] <= H + 1e-6 and cb_[0] >= 0 and cb_[1] >= 0, cb_)
        check("... moved 24 px up and left instead (the plain +24 would leave the page; a copy never lands on itself), selected", len(cn) == 1 and moved(pre["dc1"]["data"]["points"], cn[0]["data"]["points"], -24) and selids() == [cn[0]["id"]], [cn and cn[0]["data"]["points"]])
        undo(pg)

        # 6: three chips stay inside the viewport near the right edge and near the page top (the ring flip case)
        pg.evaluate(PUTD_JS, ["p4", [{"id": "dr1", "page_id": "p4", "seq": int(time.time() * 1000) + 6, "kind": "pen", "style": st2, "data": {"points": [[780, 480], [782, 540], [784, 600]]}},
                                     {"id": "dt1", "page_id": "p4", "seq": int(time.time() * 1000) + 7, "kind": "pen", "style": st2, "data": {"points": [[200, 8], [300, 30], [400, 12]]}}]])
        def inside(c_): return c_ and c_["n"] == 3 and c_["left"] >= 0 and c_["top"] >= 0 and c_["right"] <= c_["vw"] and c_["bottom"] <= c_["vh"]
        def ring_free():
            rg = pg.evaluate(RINGD_JS)
            if not rg: return False
            rx_, ry_ = screen(pg, 1, rg[0], rg[1])
            return not pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e ? !!e.closest('button') : true; }", [rx_, ry_])
        tap_page(pg, 1, 400, 900)
        drag_page(pg, 1, (770, 470), (792, 610))
        c6 = pg.evaluate(CHIPS_JS)
        check("near the right edge: the narrow stroke is selected, three chips inside the viewport", selids() == ["dr1"] and inside(c6), [sel(pg), c6])
        check("near the right edge: the three chips do not cover the turn ring", ring_free())
        tap_page(pg, 1, 400, 900)
        drag_page(pg, 1, (180, 2), (420, 60))
        c7 = pg.evaluate(CHIPS_JS); rg7 = pg.evaluate(RINGD_JS); bx7 = sel(pg)["box"] if sel(pg) else None
        check("near the page top: the ring flips below the box, three chips inside the viewport",
              selids() == ["dt1"] and rg7 and bx7 and rg7[1] > bx7[3] and inside(c7), [sel(pg), c7, rg7, bx7])
        check("no page errors in the duplicate chip group", not e25, e25)
        ctx.close()

        # ------------------------------------------------------------ pw-v4p: Select all in the finger hold menu
        group[0] = "select all (pw-v4p)"
        ctx, pg, e26 = fresh(b, has_touch=True); errs += e26
        open_note(pg, "Select")
        cdp = ctx.new_cdp_session(pg)
        def touch(kind, pts=()): cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y, "id": k} for k, (x, y) in enumerate(pts)]})
        def hold(i, px, py, ms=600):
            x, y = screen(pg, i, px, py); touch("touchStart", [(x, y)]); pg.wait_for_timeout(ms); return x, y
        def lift(): touch("touchEnd"); pg.wait_for_timeout(60)
        MENU_JS = """() => { const m = document.getElementById('menu'), r = m.getBoundingClientRect();
          return { shown: !m.hidden && r.height > 0, items: [...m.querySelectorAll('button')].map(b => ({ label: b.textContent.trim(), disabled: b.disabled })) }; }"""
        def menu(): return pg.evaluate(MENU_JS)
        def item(label): return pg.locator("#menu button").filter(has_text=re.compile("^" + re.escape(label) + "$"))
        def ids(pid): return sorted(s_["id"] for s_ in strokes(pg, pid))
        def selids(): s_ = sel(pg); return sorted(s_["ids"]) if s_ else None
        def tool_now(): return pg.evaluate("window.__pw.ink.tool().tool")
        def tray_on(t): return pg.evaluate(f"document.getElementById('tool-{t}').classList.contains('on')")
        # every drawn element's own box (page px), so the selection box can be checked against each record
        ELBOX_JS = """(i) => [...document.querySelectorAll(`#stack .sheet[data-index="${i}"] svg.ink [data-id]`)].filter(e => !e.closest('g.sel'))
          .map(e => { const b = e.getBBox(); return { id: e.dataset.id, b: [b.x, b.y, b.x + b.width, b.y + b.height] }; })"""
        RING_JS = "() => document.querySelectorAll('svg.ink g.sel circle.selrot').length"
        NSEL_JS = "() => document.querySelectorAll('svg.ink g.sel').length"

        # 1: three strokes (two pen, one highlighter) and one shape on page 1; a finger hold shows Select all, then Paste
        draw(pg, 1, [(120, 150), (220, 170), (320, 150)])
        draw(pg, 1, [(420, 700), (520, 720), (620, 700)])
        tool(pg, "highlighter")
        draw(pg, 1, [(130, 900), (300, 905), (470, 900)])
        tool(pg, "pen")
        draw(pg, 1, rough_square(), steps=3, hold=650)
        recs = strokes(pg, "p4"); four = sorted(r["id"] for r in recs)
        check("page 1 holds four records: two pen, one highlighter, one shape",
              len(recs) == 4 and sorted(r["kind"] for r in recs) == ["highlighter", "pen", "pen", "shape"], [r["kind"] for r in recs])
        check("the pen tool is on and nothing is selected before the hold", tool_now() == "pen" and tray_on("pen") and sel(pg) is None)
        hold(1, 650, 300); m1 = menu(); lift()
        check("a finger held 600 ms: #menu shows two items in order, Select all then Paste, Paste disabled (empty clipboard)",
              m1["shown"] and m1["items"] == [{"label": "Select all", "disabled": False}, {"label": "Nothing to paste", "disabled": True}], m1)
        check("the hold drew nothing and selected nothing", len(strokes(pg, "p4")) == 4 and sel(pg) is None)

        # 2: tap Select all
        u0 = U(pg)
        item("Select all").tap(); pg.wait_for_timeout(60)
        s1 = sel(pg); ui1 = selui(pg)
        check("Select all: the selection holds all four ids, on page 1", s1 and s1["page"] == "p4" and selids() == four, s1)
        check("Select all: the tool is select and the tray's select button is lit", tool_now() == "select" and tray_on("select") and not tray_on("pen"))
        check("Select all: the menu is closed", not menu()["shown"])
        check("Select all: no undo step", U(pg) == u0, [U(pg), u0])
        check("Select all: the box, its corners, the three chips (Copy, Duplicate, Delete) and the turn ring are shown",
              ui1["box"] and ui1["corners"] == 4 and ui1["chips"] == ["Copy", "Duplicate", "Delete"] and ui1["chipsShown"] and pg.evaluate(RING_JS) == 1, ui1)
        bx = s1["box"] if s1 else None
        wd = {r["id"]: r["style"]["width"] / 2 for r in strokes(pg, "p4")}
        eb = [[e["b"][0] - wd[e["id"]], e["b"][1] - wd[e["id"]], e["b"][2] + wd[e["id"]], e["b"][3] + wd[e["id"]]] for e in pg.evaluate(ELBOX_JS, 1) if e["id"] in wd]
        check("Select all: every record's drawn box (plus half its ink width) lies inside the selection box", bx and len(eb) == 4 and
              all(e[0] >= bx[0] - 0.5 and e[1] >= bx[1] - 0.5 and e[2] <= bx[2] + 0.5 and e[3] <= bx[3] + 0.5 for e in eb), [bx, eb])
        check("Select all: the box spans them (each edge within 1.5 px of the outermost record's edge)", bx and len(eb) == 4 and
              abs(bx[0] - min(e[0] for e in eb)) < 1.5 and abs(bx[1] - min(e[1] for e in eb)) < 1.5 and
              abs(bx[2] - max(e[2] for e in eb)) < 1.5 and abs(bx[3] - max(e[3] for e in eb)) < 1.5, [bx, eb])
        tap_page(pg, 1, 700, 1050)
        check("a tap on an empty spot clears it", sel(pg) is None)
        drag_page(pg, 1, (2, 2), (792, 1120))
        s_drag = sel(pg)
        check("the union: a drag box over the whole page selects the same four with exactly the same box",
              s_drag and sorted(s_drag["ids"]) == four and bx and all(abs(p_ - q_) < 1e-6 for p_, q_ in zip(s_drag["box"], bx)), [s_drag, bx])

        # 3: the Delete chip after Select all empties the page as one undo step; undo brings all four back
        tap_page(pg, 1, 700, 1050)
        hold(1, 650, 300); lift()
        item("Select all").tap(); pg.wait_for_timeout(60)
        u1 = U(pg)
        check("Select all again: four selected", selids() == four, sel(pg))
        pg.locator(".selChips .chip[data-act='delete']").click(); pg.wait_for_timeout(40)
        check("Delete: the page is empty", strokes(pg, "p4") == [], len(strokes(pg, "p4")))
        check("Delete: one undo step", U(pg) == u1 + 1, [U(pg), u1])
        check("Delete: the selection is gone", sel(pg) is None and not selui(pg)["chips"])
        undo(pg)
        check("undo brings all four back, the same ids", ids("p4") == four, ids("p4"))

        # 4: an empty page (page 2): both items disabled
        go_page(pg, 2)
        if pg.locator("#pageList").is_visible(): pg.click("#plClose"); pg.wait_for_timeout(60)
        hold(2, 400, 300); m4 = menu(); lift()
        check("an empty page: the hold menu shows 'Nothing to select' and 'Nothing to paste', both disabled",
              m4["shown"] and m4["items"] == [{"label": "Nothing to select", "disabled": True}, {"label": "Nothing to paste", "disabled": True}], m4)
        u4, n4 = U(pg), len(strokes(pg, "p4b"))
        item("Nothing to select").click(force=True); pg.wait_for_timeout(40)
        check("tapping the disabled item does nothing (no selection, no undo step, nothing added)", sel(pg) is None and U(pg) == u4 and len(strokes(pg, "p4b")) == n4)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(30)

        # 5: one selection at a time: Select all on page 1, then on page 2 selects page 2's strokes only
        tool(pg, "pen")
        draw(pg, 2, [(150, 200), (250, 220), (350, 200)])
        draw(pg, 2, [(150, 400), (250, 420), (350, 400)])
        two = ids("p4b")
        check("page 2 now holds two strokes", len(two) == 2, two)
        go_page(pg, 1)
        if pg.locator("#pageList").is_visible(): pg.click("#plClose"); pg.wait_for_timeout(60)
        hold(1, 650, 300); lift()
        item("Select all").tap(); pg.wait_for_timeout(60)
        check("Select all on page 1: its four", sel(pg) and sel(pg)["page"] == "p4" and selids() == four, sel(pg))
        go_page(pg, 2)
        if pg.locator("#pageList").is_visible(): pg.click("#plClose"); pg.wait_for_timeout(60)
        u5 = U(pg)
        hold(2, 600, 700); m5 = menu(); lift()
        check("page 2's hold menu: Select all then Nothing to paste", m5["items"] == [{"label": "Select all", "disabled": False}, {"label": "Nothing to paste", "disabled": True}], m5)
        item("Select all").tap(); pg.wait_for_timeout(60)
        check("Select all on page 2: the selection is page 2's two strokes only", sel(pg) and sel(pg)["page"] == "p4b" and selids() == two, sel(pg))
        check("one selection at a time: one selection box in the note", pg.evaluate(NSEL_JS) == 1)
        check("no undo step for either Select all", U(pg) == u5, [U(pg), u5])
        check("no page errors in the select all group", not e26, e26)
        ctx.close()

        # ------------------------------------------------------------ pw-v4s: hold-to-snap makes a parabola
        group[0] = "parabola snap (pw-v4s)"
        ctx, pg, ep1 = fresh(b); errs += ep1
        open_note(pg, "Snap")
        tool(pg, "pen")
        PARK = ("x1", "y1", "cx", "cy", "x2", "y2")
        def qmid(d): return ((d["x1"] + 2 * d["cx"] + d["x2"]) / 4, (d["y1"] + 2 * d["cy"] + d["y2"]) / 4)   # M, the curve at t = 0.5
        def kinds(pid): return [(s["kind"], s["data"].get("type")) for s in strokes(pg, pid)]
        def lastfit(): return pg.evaluate("window.__pw.ink.lastStroke()")
        def snap_case(name, pts, vertex):
            u0 = U(pg)
            draw(pg, 1, pts, hold=650)
            k = kinds("p1"); r = last(pg, "p1")
            check(f"{name}: the page has one ('shape', 'parabola'), no arc", k == [("shape", "parabola")], k)
            if r and r["data"].get("type") == "parabola":
                d = r["data"]
                check(f"{name}: its ends within 6 px of the drawn ends", near((d["x1"], d["y1"]), pts[0], 6) and near((d["x2"], d["y2"]), pts[-1], 6), [d, pts[0], pts[-1]])
                check(f"{name}: its midpoint M within 8 px of the true vertex", near(qmid(d), vertex, 8), [qmid(d), vertex])
                L = lastfit() or {}
                f = L.get("fit") or {}
                check(f"{name}: lastStroke() says parabola, its fit under 0.6 of the arc's", L.get("classify") == "parabola" and f.get("p") is not None
                      and (f.get("a") is None or f["p"] < 0.6 * f["a"]), L.get("fit"))
            check(f"{name}: one undo step", U(pg) == u0 + 1, [u0, U(pg)])
            undo(pg)
            return r
        # 1. a = 0.004, half width 150 (the vertex at the top on the page, the arms going down)
        P1 = rough_parabola(400, 300, 0.004, 150)
        r = snap_case("a rough parabola (a = 0.004, half width 150)", P1, (400, 300))
        if r and r["data"].get("type") == "parabola":
            d = r["data"]
            check("stored as { type, x1, y1, cx, cy, x2, y2 }, to 0.1 px", sorted(d) == sorted(("type",) + PARK) and all(round(d[k], 1) == d[k] for k in PARK), d)
            check("same colour, width and dash as the pen", r["style"] == {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1}, r["style"])
            check("classify on the same points: parabola", cls(P1) == "parabola", cls(P1))
        # 2. the other way, and narrow
        snap_case("the same the other way (a = -0.004)", rough_parabola(400, 500, -0.004, 150, seed=8), (400, 500))
        snap_case("a narrow one (a = 0.012, half width 150)", rough_parabola(400, 300, 0.012, 150, seed=9), (400, 300))
        # 4. sideways: x = vx + a (y - vy)^2
        snap_case("a sideways parabola (x = vx + a (y - vy)^2)", rough_parabola(300, 500, 0.004, 150, side=True, seed=10), (300, 500))
        # 3. even curvature stays an arc
        for name, pts in [("a rough semicircle (radius 90, 180 degrees)", rough_arc(400, 400, 90, 180, 360, n=30)),
                          ("a rough 120 degree arc (radius 90)", rough_arc(400, 400, 90, 210, 330))]:
            draw(pg, 1, pts, hold=650)
            k = kinds("p1")
            check(f"{name}: STILL an arc, not a parabola", k == [("shape", "arc")], k)
            check(f"{name}: classify agrees", cls(pts) == "arc", cls(pts))
            undo(pg)
        # 5. an S wiggle (two bends): freehand
        rs = random.Random(11)
        Sw = [(100 + 300 * k / 40 + rs.uniform(-1.5, 1.5), 500 + 60 * math.sin(2 * math.pi * k / 40) + rs.uniform(-1.5, 1.5)) for k in range(41)]
        draw(pg, 1, Sw, hold=650)
        check("an S wiggle held: freehand, no snap", kinds("p1") == [("pen", None)], kinds("p1"))
        check("classify: the S wiggle is not a shape", cls(Sw) is None, cls(Sw))
        undo(pg)
        # the kept one: how it is drawn, and a reload
        draw(pg, 1, P1, hold=650)
        r = last(pg, "p1")
        e = elinfo(pg, 1, r["id"]) if r else None
        ai = arcinfo(r["id"]) if r else None
        check("drawn as an SVG <path> in g.pen, stroke only, data-type parabola", e and e["tag"] == "path" and e["type"] == "parabola" and e["parent"] == "pen" and e["fill"] == "none", e)
        if r and ai and r["data"].get("type") == "parabola":
            d = r["data"]
            def js1(v): v = round(v, 1); return str(int(v)) if v == int(v) else repr(v)
            want = f"M{js1(d['x1'])} {js1(d['y1'])}Q{js1(d['cx'])} {js1(d['cy'])} {js1(d['x2'])} {js1(d['y2'])}"
            check("its d is M x1 y1 Q cx cy x2 y2", ai["d"] == want, [ai["d"], want])
            check("the drawn path runs through M and both ends", on_stroke(r["id"], *qmid(d)) and on_stroke(r["id"], d["x1"], d["y1"]) and on_stroke(r["id"], d["x2"], d["y2"]))
            ol = pg.evaluate("(id) => import('./js/ink.js').then(m => m.outline(m.strokesOf('p1').find(r => r.id === id)))", r["id"])
            check("outline: 48 points along the curve, from the start to the end", len(ol) == 48 and near(ol[0], (d["x1"], d["y1"]), 0.01) and near(ol[-1], (d["x2"], d["y2"]), 0.01), [len(ol), ol[:1], ol[-1:]])
        pg.wait_for_timeout(200)
        check("after the fade only the parabola is in the layer", pg.evaluate("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink g.pen > *').length") == 1)
        before = ai and ai["d"]
        idle(pg); pg.reload(); ready(pg); open_note(pg, "Snap")
        check("after a reload the parabola is redrawn the same", r and (arcinfo(r["id"]) or {}).get("d") == before, [before, r and arcinfo(r["id"])])
        # a highlighter parabola is allowed (a highlighter-born shape)
        tool(pg, "highlighter")
        draw(pg, 1, rough_parabola(400, 700, 0.004, 150, seed=12), hold=650)
        h = last(pg, "p1")
        check("a highlighter parabola held: shape/parabola with the highlighter's look", h and h["kind"] == "shape" and h["data"].get("type") == "parabola"
              and h["style"] == {"colour": "#FFC107", "width": 18, "dash": "solid", "opacity": 0.4}, h and [h["kind"], h["data"], h["style"]])
        e = elinfo(pg, 1, h["id"]) if h else None
        check("... a <path> in its g.hlo (0.4) group under g.hl", e and e["tag"] == "path" and e["parent"] == "hlo" and e["gp"] == "hl" and e["opacity"] == "0.4", e)
        tool(pg, "pen")
        ctx.close()

        # the ?dbg=1 readout shows both fit numbers
        ctx, pg, ep2 = fresh(b, url=LOCAL + "&dbg=1"); errs += ep2
        open_note(pg, "Snap")
        pg.wait_for_selector("#dbg", state="attached", timeout=5000)
        tool(pg, "pen")
        draw(pg, 1, rough_parabola(400, 300, 0.004, 150), hold=650)
        pg.wait_for_timeout(300)
        lastln = pg.evaluate("document.getElementById('dbg').textContent").split("\n")[-1]
        m = re.fullmatch(r"last: \d+ pts, \d+(\.\d)? px, mouse, classify: parabola \(p (\d+\.\d) / a (\d+\.\d)\), snapped", lastln)
        check("?dbg=1: the last-stroke line reads 'classify: parabola (p X.X / a Y.Y), snapped'", m is not None, lastln)
        if m: check("... and p is under 0.6 of a", float(m.group(2)) < 0.6 * float(m.group(3)), lastln)
        ctx.close()

        # 6. handles: three; the middle drags M, an end moves alone
        ctx, pg, ep3 = fresh(b); errs += ep3
        open_note(pg, "Handles")
        pen = Pen(ctx, pg)
        draw(pg, 1, rough_parabola(400, 400, 0.004, 150), hold=650)
        a = last(pg, "p2")
        check("a parabola to grab", a and a["kind"] == "shape" and a["data"].get("type") == "parabola", a and a["data"])
        if a and a["data"].get("type") == "parabola":
            d0 = dict(a["data"]); u0 = U(pg); M0 = qmid(d0)
            hs = pg.evaluate("(id) => import('./js/ink.js').then(m => m.handles(m.strokesOf('p2').find(r => r.id === id)))", a["id"])
            check("handles gives 3: start, M, end", len(hs) == 3 and near(hs[0], (d0["x1"], d0["y1"]), 1e-6) and near(hs[1], M0, 1e-6) and near(hs[2], (d0["x2"], d0["y2"]), 1e-6), [hs, M0])
            tool(pg, "select")                                    # pw-v4v: the select tool grabs a handle, the pen only draws
            pen.stroke([screen(pg, 1, *M0), screen(pg, 1, M0[0], M0[1] + 30)])
            d1 = last(pg, "p2")["data"]
            check("the middle handle dragged 30 px down (select tool): M follows within 1 px", d1.get("type") == "parabola" and near(qmid(d1), (M0[0], M0[1] + 30), 1), [qmid(d1), M0])
            check("... the ends stay", all(d1[k] == d0[k] for k in ("x1", "y1", "x2", "y2")), [d0, d1])
            check("... no stroke drawn, one undo step, and the path runs through the new M", len(strokes(pg, "p2")) == 1 and U(pg) == u0 + 1 and on_stroke(a["id"], *qmid(d1)), [len(strokes(pg, "p2")), U(pg), u0])
            undo(pg)
            check("undo puts the curve back", last(pg, "p2")["data"] == d0, [last(pg, "p2")["data"], d0])
            redo(pg)
            pen.stroke([screen(pg, 1, d1["x2"], d1["y2"]), screen(pg, 1, d1["x2"] + 30, d1["y2"] + 20)])
            d2 = last(pg, "p2")["data"]
            check("dragging an end: only that end moves (the start and the control point stay)",
                  abs(d2["x2"] - (d1["x2"] + 30)) <= 1.5 and abs(d2["y2"] - (d1["y2"] + 20)) <= 1.5 and all(d2[k] == d1[k] for k in ("x1", "y1", "cx", "cy")), [d1, d2])
            check("... and the path goes through the new end", on_stroke(a["id"], d2["x2"], d2["y2"]))
        ctx.close()

        # 6. move, resize and turn with the select tool map the three points
        ctx, pg, ep4 = fresh(b); errs += ep4
        open_note(pg, "Select")
        PB = {"type": "parabola", "x1": 250, "y1": 390, "cx": 400, "cy": 210, "x2": 550, "y2": 390}   # y = 300 + 0.004 (x - 400)^2, M = (400, 300)
        def put_par(pid, rid="pb", style=None):
            pg.evaluate(PUT_JS, [pid, [{"id": rid, "page_id": pid, "seq": int(time.time() * 1000), "kind": "shape",
                                         "style": style or {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1}, "data": dict(PB)}]])
        def pts3(d): return [(d["x1"], d["y1"]), (d["cx"], d["cy"]), (d["x2"], d["y2"])]
        put_par("p4")
        tool(pg, "select")
        select_box((230, 190), (570, 410))
        check("the parabola is selected", sel(pg) and sel(pg)["ids"] == ["pb"], sel(pg))
        u0 = U(pg)
        drag_page(pg, 1, (330, 360), (380, 400))                  # pw-v4v: inside the box away from M (a pen down on M is a handle grab now)
        d1 = by_id()["pb"]["data"]
        check("a move keeps it a parabola and moves all three points by (50, 40)", d1["type"] == "parabola"
              and all(abs(d1[k] - (PB[k] + (50 if "x" in k else 40))) <= 0.11 for k in PARK), [PB, d1])
        check("... one undo step, the path follows", U(pg) == u0 + 1 and on_stroke("pb", *qmid(d1)), [U(pg), u0])
        undo(pg)
        check("undo puts it back", by_id()["pb"]["data"] == PB, by_id()["pb"]["data"])
        select_box((230, 190), (570, 410))
        q = pg.evaluate(CORN_JS); o, c2 = q[0], q[2]
        drag_page(pg, 1, (c2[0], c2[1]), (o[0] + 2 * (c2[0] - o[0]), o[1] + 2 * (c2[1] - o[1])), steps=12)
        d2 = by_id()["pb"]["data"]
        P, Q = pts3(PB), pts3(d2)
        s_ = math.hypot(Q[2][0] - Q[0][0], Q[2][1] - Q[0][1]) / math.hypot(P[2][0] - P[0][0], P[2][1] - P[0][1])
        similar = all(abs((Q[i][j] - Q[0][j]) - s_ * (P[i][j] - P[0][j])) <= 0.3 for i in (1, 2) for j in (0, 1))
        check("a resize to twice the size keeps it a parabola and scales all three points (one scale, about one point)",
              d2["type"] == "parabola" and abs(s_ - 2) < 0.08 and similar, [s_, PB, d2])
        undo(pg)
        select_box((230, 190), (570, 410))
        RINGP_JS = """() => { const c = document.querySelector('svg.ink g.sel circle.selrot'); return c ? [+c.getAttribute('cx'), +c.getAttribute('cy')] : null; }"""
        def pturn(deg):                    # the ring dragged through deg degrees about the box centre (as turn_sel, with its own ring read)
            c_ = box_centre(); r_ = pg.evaluate(RINGP_JS)
            a_ = math.atan2(r_[1] - c_[1], r_[0] - c_[0]) + math.radians(deg); R_ = math.hypot(r_[0] - c_[0], r_[1] - c_[1]) * 1.4
            drag_page(pg, 1, (r_[0], r_[1]), (c_[0] + R_ * math.cos(a_), c_[1] + R_ * math.sin(a_)), steps=12); return c_
        c = pturn(40)
        d3 = by_id()["pb"]["data"]; exp = [rot_about(p_, c, 40) for p_ in pts3(PB)]
        check("a turn of 40 degrees keeps it a parabola and turns all three points about the box centre (1 px)",
              d3["type"] == "parabola" and all(near(p_, e_, 1) for p_, e_ in zip(pts3(d3), exp)), [pts3(d3), exp])
        check("... and the drawn path still runs through its turned M", on_stroke("pb", *qmid(d3)))
        ctx.close()

        # 7. the area eraser across one arm: two pen pieces; undo brings the parabola back
        ctx, pg, ep5 = fresh(b); errs += ep5
        open_note(pg, "Erase")
        put_par("p5")
        r0 = strokes(pg, "p5")[0]
        u0 = U(pg)
        tool(pg, "area")
        drag_page(pg, 1, (325, 295), (325, 350), steps=10)                # across the left arm at x 325 (y 322.5 there)
        k = kinds("p5")
        check("the area eraser across one arm: the parabola becomes two pen pieces", k == [("pen", None), ("pen", None)], k)
        s1 = strokes(pg, "p5")
        check("... both pieces keep its page, seq and style, one undo step", all(s["page_id"] == "p5" and s["seq"] == r0["seq"] and s["style"] == r0["style"] for s in s1) and U(pg) == u0 + 1, [U(pg), u0])
        if len(s1) == 2:
            ends = sorted([s1[0]["data"]["points"][0], s1[0]["data"]["points"][-1], s1[1]["data"]["points"][0], s1[1]["data"]["points"][-1]])
            check("... the pieces keep the parabola's two ends", any(near(p_, (250, 390), 0.2) for p_ in ends) and any(near(p_, (550, 390), 0.2) for p_ in ends), ends)
        undo(pg)
        s2 = strokes(pg, "p5")
        check("undo: the parabola is back, the same id and data, drawn as its path",
              len(s2) == 1 and s2[0]["id"] == "pb" and s2[0]["data"] == PB and (elinfo(pg, 1, "pb") or {}).get("type") == "parabola", [kinds("p5")])
        ctx.close()

        # 8. restyle, Copy / Paste and Duplicate: still a parabola with the right style
        ctx, pg, ep6 = fresh(b, has_touch=True); errs += ep6
        open_note(pg, "Select")
        cdp_p = ctx.new_cdp_session(pg)
        def ptouch(kind, pts=()): cdp_p.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y, "id": k} for k, (x, y) in enumerate(pts)]})
        put_par("p4")
        pg.click("#tray .sw[data-colour='#FF3636']")
        tool(pg, "restyle")
        u0 = U(pg)
        tap_page(pg, 1, 400, 300)                                         # on M
        r1_ = by_id()["pb"]
        check("restyle on it: still a parabola with the same points, now red", r1_["data"] == PB and r1_["style"]["colour"] == "#FF3636" and U(pg) == u0 + 1, [r1_["style"], U(pg), u0])
        red = r1_["style"]
        tool(pg, "select")
        select_box((230, 190), (570, 410))
        pg.locator(".selChips .chip[data-act='copy']").click(); pg.wait_for_timeout(40)
        x_, y_ = screen(pg, 1, 400, 800); ptouch("touchStart", [(x_, y_)]); pg.wait_for_timeout(600); ptouch("touchEnd"); pg.wait_for_timeout(60)
        pg.locator("#menu button").filter(has_text=re.compile("^Paste$")).click(); pg.wait_for_timeout(60)
        now_ = by_id(); pasted = [v for k_, v in now_.items() if k_ != "pb"]
        pd = pasted[0]["data"] if len(pasted) == 1 else {}
        def rel(d): return (d["cx"] - d["x1"], d["cy"] - d["y1"], d["x2"] - d["x1"], d["y2"] - d["y1"])
        def same_shape(d, e_): return bool(d and e_) and all(abs(u_ - v_) <= 0.11 for u_, v_ in zip(rel(d), rel(e_)))
        check("Copy then Paste: one new record, a parabola of the same shape, red like the original",
              len(pasted) == 1 and pasted[0]["kind"] == "shape" and pd.get("type") == "parabola" and same_shape(pd, PB) and pasted[0]["style"] == red, [pasted])
        sel_now = sel(pg)
        if len(pasted) == 1 and sel_now and sel_now["ids"] == [pasted[0]["id"]]:
            pg.locator(".selChips .chip[data-act='duplicate']").click(); pg.wait_for_timeout(40)
            now2 = by_id(); dups = [v for k_, v in now2.items() if k_ not in now_]
            dd = dups[0]["data"] if len(dups) == 1 else {}
            check("Duplicate: one more parabola, every point moved by (+24, +24), the same red style",
                  len(dups) == 1 and dd.get("type") == "parabola" and all(abs(dd[k_] - (pd[k_] + 24)) < 1e-6 for k_ in PARK) and dups[0]["style"] == red, [dups, pd])
        else:
            check("the pasted parabola is selected (for Duplicate)", False, sel_now)
        check("no page errors in the parabola groups", not (ep1 or ep2 or ep3 or ep4 or ep5 or ep6), [ep1, ep2, ep3, ep4, ep5, ep6])
        ctx.close()

        # ------------------------------------------------------------ pw-v4w: the arrow's tip is the stroke's first sharp corner
        group[0] = "arrow tip = first corner (pw-v4w)"
        ctx, pg, ea = fresh(b); errs += ea
        FIX = ROOT / "tests" / "fixtures"
        def fixture(name): return json.load(open(FIX / name, encoding="utf-8"))["points"]
        def classify_(pts): return pg.evaluate("(p) => import('./js/ink.js').then(m => m.classify(p))", [list(q) for q in pts])
        def tip_(pts): return pg.evaluate("(p) => import('./js/ink.js').then(m => m.tipIndex(p))", [list(q) for q in pts])
        FAIL, OK, CURVED = fixture("arrow-pen-fail.json"), fixture("arrow-pen-ok.json"), fixture("curved-arrow-pen.json")
        for name, pts, ref in [("arrow-pen-fail", FAIL, (233.4, 317.3)), ("arrow-pen-ok", OK, (390.2, 358.3)), ("curved-arrow-pen", CURVED, (163.9, 95.9))]:
            ti = tip_(pts)
            info_lines.append(f"tipIndex {name}: {ti} {pts[ti] if 0 <= ti < len(pts) else None} (reference {ref})")
            check(f"tipIndex on {name}: within 2 px of the reference corner {ref}", 0 <= ti < len(pts) and near(pts[ti], ref, 2), [ti, pts[ti] if 0 <= ti < len(pts) else None])
        r = classify_(FAIL)
        check("her failing pen arrow (overshoot on the return): arrow", bool(r) and r["type"] == "arrow", r)
        if r and r["type"] == "arrow":
            check("... its tip within 2 px of (233.4, 317.3), its start within 2 px of (141.5, 371.5)",
                  near((r["x2"], r["y2"]), (233.4, 317.3), 2) and near((r["x1"], r["y1"]), (141.5, 371.5), 2), r)
        r = classify_(OK)
        check("her working pen arrow: still an arrow", bool(r) and r["type"] == "arrow", r)
        if r and r["type"] == "arrow":
            check("... its tip within 2 px of (390.2, 358.3)", near((r["x2"], r["y2"]), (390.2, 358.3), 2), r)
        r = classify_(CURVED)
        info_lines.append(f"curved-arrow-pen classifies as: {r and r['type']}")
        check("her curved pen arrow: not an arrow and not a line (round 3 makes it a curved arrow)", not (r and r["type"] in ("arrow", "line")), r)
        check("tipIndex on a plain straight stroke (mouse, wobbly): -1", tip_(rough_line()) == -1, tip_(rough_line()))
        dense = [(100 + 0.7 * k, 300 + 0.6 * math.sin(k * 0.3)) for k in range(400)]
        check("tipIndex on a plain straight stroke (pen-dense points): -1", tip_(dense) == -1, tip_(dense))
        Vm = [(100, 600), (130, 660), (160, 720), (190, 780), (220, 720), (250, 660), (280, 600)]
        check("tipIndex on a V drawn with the mouse (sparse points): the corner (index 3)", tip_(Vm) == 3, tip_(Vm))
        ra = rough_arrow()
        check("tipIndex on the mouse arrow (tip, wing, back, wing): the tip (index 8)", tip_(ra) == 8, tip_(ra))
        r = classify_(ra)
        check("classify on the mouse arrow: arrow from (120, 980) to the tip (420, 980)", bool(r) and r["type"] == "arrow"
              and near((r["x1"], r["y1"]), (120, 980), 3) and near((r["x2"], r["y2"]), (420, 980), 3), r)
        loopy = [(100 + 10 * k, 500) for k in range(31)] + [(400 + 20 * math.sin(math.radians(a)), 480 + 20 * math.cos(math.radians(a))) for a in range(15, 361, 15)]
        r = classify_(loopy)
        check("a stroke that ends in a soft loop (no corner): not an arrow", tip_(loopy) == -1 and not (r and r["type"] == "arrow"), [tip_(loopy), r])
        check("no page errors in the arrow tip group", not ea, ea)
        ctx.close()

        # ------------------------------------------------------------ pw-v4x: the curved arrow (an arc shaft, the arrow's head at its end)
        group[0] = "curved arrow (pw-v4x)"
        ctx, pg, ec1 = fresh(b); errs += ec1
        open_note(pg, "Snap")
        CK = ("x1", "y1", "xm", "ym", "x2", "y2")
        CAR_JS = """(id) => { const e = document.querySelector(`svg.ink [data-id="${id}"]`); if (!e) return null;
          const k = [...e.children], cs = (c) => c ? getComputedStyle(c).strokeDasharray : null;
          return { tag: e.tagName, type: e.dataset.type, parent: e.parentNode.getAttribute('class'), kids: k.map(c => c.tagName),
            sd: k[0] ? k[0].getAttribute('d') : null, hd: k[1] ? k[1].getAttribute('d') : null, hcls: k[1] ? k[1].getAttribute('class') : null,
            shaftDash: cs(k[0]), headDash: cs(k[1]) }; }"""
        SHAFT_ON_JS = """([id, x, y]) => { const e = document.querySelector(`svg.ink [data-id="${id}"]`);
          return !!e && !!e.children[0] && e.children[0].isPointInStroke(new DOMPoint(x, y)); }"""
        def car(rid): return pg.evaluate(CAR_JS, rid)
        def head3(rid):                                  # the drawn head: [barb, tip, barb]
            i_ = car(rid); n_ = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", (i_ or {}).get("hd") or "")]
            return [(n_[0], n_[1]), (n_[2], n_[3]), (n_[4], n_[5])] if len(n_) == 6 else None
        def head_dir(rid):                               # the way the head points: from the barbs' middle to the tip
            h_ = head3(rid)
            if not h_: return None
            vx, vy = h_[1][0] - (h_[0][0] + h_[2][0]) / 2, h_[1][1] - (h_[0][1] + h_[2][1]) / 2; L_ = math.hypot(vx, vy) or 1
            return (vx / L_, vy / L_)
        def circ3(d):                                    # the circle through start, middle, end: (ox, oy, r)
            ax, ay, bx, by, cx_, cy_ = (d[k] for k in CK)
            D = 2 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
            a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx_ * cx_ + cy_ * cy_
            ox = (a2 * (by - cy_) + b2 * (cy_ - ay) + c2 * (ay - by)) / D; oy = (a2 * (cx_ - bx) + b2 * (ax - cx_) + c2 * (bx - ax)) / D
            return ox, oy, math.hypot(ax - ox, ay - oy)
        def tan_end(d):                                  # the arc's unit tangent at its end, the way it travels (start, middle, end)
            ox, oy, _ = circ3(d); vx, vy = d["x2"] - ox, d["y2"] - oy; L_ = math.hypot(vx, vy); t_ = (-vy / L_, vx / L_)
            return t_ if t_[0] * (d["x2"] - d["xm"]) + t_[1] * (d["y2"] - d["ym"]) > 0 else (-t_[0], -t_[1])
        def ang(u, v): return math.degrees(math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))))
        def curved_arrow(cx, cy, r, a0, a1, wing=28, spread=35):   # rough_arc, then a V at its end (one wing, back to the tip, the other)
            pts = rough_arc(cx, cy, r, a0, a1); t_ = math.radians(a1); sg = 1 if a1 > a0 else -1
            u = (-sg * math.sin(t_), sg * math.cos(t_)); tip = pts[-1]
            def w(deg):
                c_, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
                return (tip[0] - wing * (u[0] * c_ - u[1] * s_), tip[1] - wing * (u[1] * c_ + u[0] * s_))
            return pts + [w(spread), tip, w(-spread)]
        # 1. her pen stroke (the fixture)
        CURVED = fixture("curved-arrow-pen.json")
        r = classify_(CURVED)
        check("her curved pen arrow (fixture): carrow", bool(r) and r["type"] == "carrow", r)
        if r and r["type"] == "carrow":
            check("... stored as { type, x1, y1, xm, ym, x2, y2 } to 0.1 px, nothing else", sorted(r) == sorted(("type",) + CK) and all(round(r[k], 1) == r[k] for k in CK), r)
            check("... its start within 3 px of (67.6, 174.2)", near((r["x1"], r["y1"]), (67.6, 174.2), 3), r)
            check("... its end (the tip) within 3 px of (165, 96)", near((r["x2"], r["y2"]), (165, 96), 3), r)
            ti = tip_(CURVED); sh = CURVED[:ti + 1]            # the shaft's own least squares circle (x^2 + y^2 + a x + b y + c = 0)
            M_ = [[sum(p_[0] * p_[0] for p_ in sh), sum(p_[0] * p_[1] for p_ in sh), sum(p_[0] for p_ in sh)],
                  [sum(p_[0] * p_[1] for p_ in sh), sum(p_[1] * p_[1] for p_ in sh), sum(p_[1] for p_ in sh)],
                  [sum(p_[0] for p_ in sh), sum(p_[1] for p_ in sh), len(sh)]]
            R_ = [-sum(p_[0] * (p_[0] ** 2 + p_[1] ** 2) for p_ in sh), -sum(p_[1] * (p_[0] ** 2 + p_[1] ** 2) for p_ in sh), -sum(p_[0] ** 2 + p_[1] ** 2 for p_ in sh)]
            def det3(m): return m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
            sol = [det3([[R_[k] if j == i else M_[k][j] for j in range(3)] for k in range(3)]) / det3(M_) for i in range(3)]
            kox, koy = -sol[0] / 2, -sol[1] / 2; kr = math.sqrt(kox ** 2 + koy ** 2 - sol[2])
            check("... its middle point on the shaft's fitted circle (within 0.5 px)", abs(math.hypot(r["xm"] - kox, r["ym"] - koy) - kr) <= 0.5, [r, kox, koy, kr])
            te = tan_end(r)
            info_lines.append(f"curved-arrow-pen: {r}, end tangent ({te[0]:.3f}, {te[1]:.3f}), {math.degrees(math.atan2(te[1], te[0])):.1f} degrees from +x (y down)")
            check("... its end tangent within 15 degrees of +x", ang(te, (1, 0)) <= 15, te)
        r = classify_(FAIL); r2 = classify_(OK); r3 = classify_(rough_arrow())
        check("the straight fixtures and the mouse arrow are still arrows (not carrow)", [x and x["type"] for x in (r, r2, r3)] == ["arrow"] * 3, [r, r2, r3])
        HA = rough_arc(400, 500, 150, -150, -30)
        check("a hand arc with NO head: still arc (classify)", (classify_(HA) or {}).get("type") == "arc", classify_(HA))
        tool(pg, "pen")
        draw(pg, 1, HA, hold=650)
        check("... and drawn and held: arc", (last(pg, "p1") or {}).get("data", {}).get("type") == "arc", last(pg, "p1"))
        undo(pg)
        # 2. a mouse-drawn curved arrow snaps
        CA = curved_arrow(400, 500, 150, -150, -30)
        check("classify on the mouse curved arrow: carrow", (classify_(CA) or {}).get("type") == "carrow", classify_(CA))
        u0 = U(pg)
        draw(pg, 1, CA, hold=650)
        r = last(pg, "p1")
        ok = r and r["kind"] == "shape" and r["data"].get("type") == "carrow"
        check("a mouse curved arrow (arc + a V at its end) held: shape/carrow", ok, r and [r["kind"], r["data"]])
        check("... one stroke on the page, ONE undo step", len(strokes(pg, "p1")) == 1 and U(pg) == u0 + 1, [len(strokes(pg, "p1")), U(pg), u0])
        check("... lastStroke() reports carrow", (pg.evaluate("window.__pw.ink.lastStroke()") or {}).get("classify") == "carrow")
        if ok:
            d = r["data"]; e = car(r["id"]); h = head3(r["id"])
            check("... its start near the stroke's start, its end near the V's tip", near((d["x1"], d["y1"]), CA[0], 3) and near((d["x2"], d["y2"]), CA[-2], 3), [d, CA[0], CA[-2]])
            check("... on the page as a <g> in g.pen with two paths (shaft, head)", e and e["tag"] == "g" and e["type"] == "carrow" and e["parent"] == "pen" and e["kids"] == ["path", "path"] and e["hcls"] == "head", e)
            check("... the shaft's d is the arc's (M .. A ..)", e and e["sd"].startswith("M") and "A" in e["sd"], e)
            check("... the head's three points sit at the end, its middle point = the end point", h is not None and near(h[1], (d["x2"], d["y2"]), 0.1)
                  and all(near(q, (d["x2"], d["y2"]), 40) for q in h), [h, d])
            check("... the head points along the arc's end tangent (within 1 degree)", h is not None and ang(head_dir(r["id"]), tan_end(d)) <= 1, [head_dir(r["id"]), tan_end(d)])
            check("... the head is never dashed, the shaft is solid", e["headDash"] == "none" and e["shaftDash"] == "none", e)
            thumb = pg.evaluate("""(id) => import('./js/ink.js').then(m => { const s = m.thumbSvg('p1'), g = s.querySelector(`[data-id="${id}"]`);
              return g ? [g.tagName, g.dataset.type, [...g.children].map(c => c.tagName), !!g.children[1] && !!g.children[1].getAttribute('d')] : null; })""", r["id"])
            check("the page list thumb (and so Share, which draws thumbSvg) has the curved arrow: a <g> with shaft and head", thumb == ["g", "carrow", ["path", "path"], True], thumb)
        undo(pg)
        check("undo of the snap takes the curved arrow away (as every snap: the snap is the one step)", len(strokes(pg, "p1")) == 0, strokes(pg, "p1"))
        redo(pg)
        check("redo brings it back as a carrow", (last(pg, "p1") or {}).get("data", {}).get("type") == "carrow")
        # highlighter: an arc, never a curved arrow
        tool(pg, "highlighter")
        draw(pg, 1, curved_arrow(400, 900, 150, -150, -30), hold=650)
        hl = last(pg, "p1")
        check("a highlighter curved arrow held: shape/arc (no highlighter arrows) with the highlighter's look",
              hl and hl["kind"] == "shape" and hl["data"].get("type") == "arc" and hl["style"]["opacity"] < 1, hl and [hl["kind"], hl["data"], hl["style"]])
        tool(pg, "pen")
        # a dashed pen: the shaft dashed, the head not
        pg.click("#tool-pen"); pg.locator("#toolPanel .dash[data-dash='dashed']").click(); pg.mouse.click(400, 10)
        draw(pg, 1, curved_arrow(400, 1050, 120, -150, -30), hold=650)
        dr = last(pg, "p1"); e = car(dr["id"]) if dr else None
        check("a dashed pen curved arrow: carrow, the shaft path dashed, the head not", dr and dr["data"].get("type") == "carrow" and dr["style"]["dash"] == "dashed"
              and e and e["shaftDash"] not in ("none", None) and e["headDash"] == "none", [dr and dr["data"], e])
        pg.click("#tool-pen"); pg.locator("#toolPanel .dash[data-dash='solid']").click(); pg.mouse.click(400, 10)
        if dr and dr["data"].get("type") == "carrow":
            pg.click("#tray .sw[data-colour='#FF3636']")
            tool(pg, "restyle")
            u0 = U(pg)
            q = pg.evaluate("(id) => import('./js/ink.js').then(m => m.outline(m.strokesOf('p1').find(r => r.id === id))[24])", dr["id"])
            tap_page(pg, 1, q[0], q[1])
            rr = [s for s in strokes(pg, "p1") if s["id"] == dr["id"]]; e = car(dr["id"])
            check("restyle on it: still a carrow with the same points, red, still dashed, one undo step", len(rr) == 1 and rr[0]["data"] == dr["data"]
                  and rr[0]["style"]["colour"] == "#FF3636" and rr[0]["style"]["dash"] == "dashed" and U(pg) == u0 + 1, [rr and rr[0]["style"], U(pg), u0])
            check("... the shaft dashed and the head still not", e and e["shaftDash"] not in ("none", None) and e["headDash"] == "none", e)
            tool(pg, "pen")
        ctx.close()

        # 3. handles: three; the end drags the tip and the head turns with it, the middle bends it
        ctx, pg, ec2 = fresh(b); errs += ec2
        open_note(pg, "Handles")
        pen = Pen(ctx, pg)
        draw(pg, 1, curved_arrow(400, 500, 150, -150, -30), hold=650)
        a = last(pg, "p2")
        check("a curved arrow to grab", a and a["kind"] == "shape" and a["data"].get("type") == "carrow", a and a["data"])
        if a and a["data"].get("type") == "carrow":
            d0 = dict(a["data"]); u0 = U(pg); hd0 = head_dir(a["id"])
            hs = pg.evaluate("(id) => import('./js/ink.js').then(m => m.handles(m.strokesOf('p2').find(r => r.id === id)))", a["id"])
            check("handles gives 3: start, middle, end", hs == [[d0["x1"], d0["y1"]], [d0["xm"], d0["ym"]], [d0["x2"], d0["y2"]]], hs)
            tool(pg, "select")
            pen.stroke([screen(pg, 1, d0["x2"], d0["y2"]), screen(pg, 1, d0["x2"] + 30, d0["y2"] + 40)])
            d1 = last(pg, "p2")["data"]; hd1 = head_dir(a["id"]); h1 = head3(a["id"])
            check("the select tool on the end handle moves the tip: only the end moves", d1.get("type") == "carrow" and abs(d1["x2"] - (d0["x2"] + 30)) <= 1.5
                  and abs(d1["y2"] - (d0["y2"] + 40)) <= 1.5 and all(d1[k] == d0[k] for k in ("x1", "y1", "xm", "ym")), [d0, d1])
            check("... one undo step, no stroke drawn", len(strokes(pg, "p2")) == 1 and U(pg) == u0 + 1, [len(strokes(pg, "p2")), U(pg), u0])
            check("... the head sits on the new tip", h1 is not None and near(h1[1], (d1["x2"], d1["y2"]), 0.1), [h1, d1])
            check("... and turned with the new tangent (moved over 3 degrees, along the new tangent within 1)", hd0 and hd1 and ang(hd0, hd1) > 3 and ang(hd1, tan_end(d1)) <= 1,
                  [hd0, hd1, tan_end(d1)])
            r0 = circ3(d1)[2]
            pen.stroke([screen(pg, 1, d1["xm"], d1["ym"]), screen(pg, 1, d1["xm"], d1["ym"] - 40)])
            d2 = last(pg, "p2")["data"]; r2_ = circ3(d2)[2]
            check("the middle handle changes the curvature: the radius changes, the ends stay", d2.get("type") == "carrow" and abs(r2_ - r0) > 0.05 * r0
                  and all(d2[k] == d1[k] for k in ("x1", "y1", "x2", "y2")), [d1, d2, r0, r2_])
            check("... the shaft runs through the new middle, the head follows the new end tangent", pg.evaluate(SHAFT_ON_JS, [a["id"], d2["xm"], d2["ym"]])
                  and ang(head_dir(a["id"]), tan_end(d2)) <= 1, [head_dir(a["id"]), tan_end(d2)])
            undo(pg); undo(pg)
            check("undo twice puts it back", last(pg, "p2")["data"] == d0, [last(pg, "p2")["data"], d0])
        ctx.close()

        # 4. move, resize and turn with the select tool keep it a curved arrow with the head on its end
        ctx, pg, ec3 = fresh(b); errs += ec3
        open_note(pg, "Select")
        CAD = {"type": "carrow", "x1": 270.1, "y1": 375, "xm": 400, "ym": 300, "x2": 529.9, "y2": 375}   # centre (400, 450), r 150, -150 to -30 degrees
        def put_car(pid, rid="ca", style=None):
            pg.evaluate(PUT_JS, [pid, [{"id": rid, "page_id": pid, "seq": int(time.time() * 1000), "kind": "shape",
                                         "style": style or {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1}, "data": dict(CAD)}]])
        def head_ok(rid, d):
            h_ = head3(rid)
            return h_ is not None and near(h_[1], (d["x2"], d["y2"]), 0.5) and ang(head_dir(rid), tan_end(d)) <= 1
        put_car("p4")
        check("a curved arrow put on the page is drawn with its head at the end", head_ok("ca", CAD), [head3("ca"), tan_end(CAD)])
        tool(pg, "select")
        select_box((250, 280), (550, 395))
        check("the curved arrow is selected", sel(pg) and sel(pg)["ids"] == ["ca"], sel(pg))
        u0 = U(pg)
        drag_page(pg, 1, (330, 335), (380, 375))                  # inside the box, away from the three handles
        d1 = by_id()["ca"]["data"]
        check("a move keeps the type and moves all three points by (50, 40)", d1["type"] == "carrow"
              and all(abs(d1[k] - (CAD[k] + (50 if "x" in k else 40))) <= 0.11 for k in CK), [CAD, d1])
        check("... one undo step, the head's tip = (x2, y2) within 0.5 px, along the tangent", U(pg) == u0 + 1 and head_ok("ca", d1), [U(pg), u0, head3("ca"), d1])
        undo(pg)
        select_box((250, 280), (550, 395))
        q = pg.evaluate(CORN_JS); o, c2 = q[0], q[2]
        drag_page(pg, 1, (c2[0], c2[1]), (o[0] + 2 * (c2[0] - o[0]), o[1] + 2 * (c2[1] - o[1])), steps=12)
        d2 = by_id()["ca"]["data"]
        s_ = math.hypot(d2["x2"] - d2["x1"], d2["y2"] - d2["y1"]) / math.hypot(CAD["x2"] - CAD["x1"], CAD["y2"] - CAD["y1"])
        check("a resize to twice the size keeps the type and scales the points", d2["type"] == "carrow" and abs(s_ - 2) < 0.08, [s_, d2])
        check("... the head's tip = (x2, y2) within 0.5 px, along the tangent", head_ok("ca", d2), [head3("ca"), d2])
        undo(pg)
        select_box((250, 280), (550, 395))
        c = pturn(40)
        d3 = by_id()["ca"]["data"]; exp = [rot_about((CAD["x" + k], CAD["y" + k]), c, 40) for k in ("1", "m", "2")]
        check("a turn of 40 degrees keeps the type and turns all three points about the box centre (1 px)", d3["type"] == "carrow"
              and all(near((d3["x" + k], d3["y" + k]), e_, 1) for k, e_ in zip(("1", "m", "2"), exp)), [d3, exp])
        check("... the head's tip = (x2, y2) within 0.5 px, re-aimed along the turned tangent", head_ok("ca", d3) and ang(tan_end(d3), tan_end(CAD)) > 35, [head3("ca"), d3])
        undo(pg)
        # Duplicate and paste keep the type
        select_box((250, 280), (550, 395))
        pg.locator(".selChips .chip[data-act='duplicate']").click(); pg.wait_for_timeout(40)
        dups = [v for k_, v in by_id().items() if k_ != "ca"]
        check("Duplicate: one more carrow, every point moved by (+24, +24)", len(dups) == 1 and dups[0]["data"]["type"] == "carrow"
              and all(abs(dups[0]["data"][k] - (CAD[k] + 24)) < 1e-6 for k in CK), dups)
        pg.locator(".selChips .chip[data-act='copy']").click(); pg.wait_for_timeout(40)
        before = set(by_id())
        pg.evaluate("import('./js/ink.js').then(m => m.pasteAt('p4', 400, 800))"); pg.wait_for_timeout(60)
        pasted = [v for k_, v in by_id().items() if k_ not in before]
        check("Copy then Paste: one more carrow with its head drawn on its end", len(pasted) == 1 and pasted[0]["data"]["type"] == "carrow"
              and head_ok(pasted[0]["id"], pasted[0]["data"]), pasted)
        ctx.close()

        # 5. erasers: the area eraser bites it into ink (the head's ink too), the stroke eraser takes it whole
        ctx, pg, ec4 = fresh(b); errs += ec4
        open_note(pg, "Erase")
        put_car("p5")
        r0 = strokes(pg, "p5")[0]; u0 = U(pg)
        tool(pg, "area")
        drag_page(pg, 1, (400, 270), (400, 330), steps=8)                 # across the shaft's middle (400, 300)
        s1 = strokes(pg, "p5")
        check("the area eraser across the shaft: no shape left, only pen ink", s1 and all(s["kind"] == "pen" for s in s1), [(s["kind"], s["data"].get("type")) for s in s1])
        heads = [s for s in s1 if near(s["data"]["points"][0], (CAD["x2"], CAD["y2"]), 20) and all(near(p_, (CAD["x2"], CAD["y2"]), 20) for p_ in s["data"]["points"])
                 and any(near(p_, (CAD["x2"], CAD["y2"]), 0.2) for p_ in s["data"]["points"])]
        shafts = [s for s in s1 if s not in heads]
        check("... two shaft pieces and the head's ink piece, solid", len(shafts) == 2 and len(heads) == 1 and heads[0]["style"]["dash"] == "solid", [len(shafts), len(heads)])
        check("... every piece keeps its page and seq, one undo step", all(s["page_id"] == "p5" and s["seq"] == r0["seq"] for s in s1) and U(pg) == u0 + 1, [U(pg), u0])
        undo(pg)
        s2 = strokes(pg, "p5")
        check("undo: the curved arrow is back, the same id and data", len(s2) == 1 and s2[0]["id"] == "ca" and s2[0]["data"] == CAD and (car("ca") or {}).get("type") == "carrow", s2)
        tool(pg, "eraser")
        u0 = U(pg)
        tap_page(pg, 1, 400, 300)
        check("the stroke eraser on the shaft removes it whole, one undo step", len(strokes(pg, "p5")) == 0 and U(pg) == u0 + 1, [strokes(pg, "p5"), U(pg), u0])
        check("no page errors in the curved arrow group", not (ec1 or ec2 or ec3 or ec4), [ec1, ec2, ec3, ec4])
        ctx.close()

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        ctx, pg, e7 = fresh(b); errs += e7
        check("cache is pw-v7c", "pw-v7c" in pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())"), pg.evaluate("caches.keys()"))
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/ink.js", "./js/tray.js", "./js/page.js", "./js/app.js", "./js/dbg.js", "./css/app.css", "./sw.js"])
        check("no em-dashes in the code", chr(0x2014) not in srcs)
        check("no shape menu or shape tool in the tray", pg.locator("#tray [data-tool='shape'], #tray [data-tool='shapes']").count() == 0)
        check("no page errors", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:400]}")
print()
for line_ in info_lines: print(line_)
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
