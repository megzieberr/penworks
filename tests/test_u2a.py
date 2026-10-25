# PenWorks U2 A checks (ink): headless Playwright (Python), same style as tests/test_u1b.py.
# Run: python tests/test_u2a.py               (local mode only: ?local=1, Supabase is never touched)
#      add --shots <folder> for two small screenshots
# Every group seeds its own folder > notes > pages into the localStorage twin, draws with the mouse
# (and one finger, which must never draw), and reads the SVG layers and the stored stroke records.
import sys, subprocess, time, pathlib, re, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8774
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None

res = []
group = ["?"]
info_lines = []
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """(big) => {
  localStorage.clear();
  const t = '2026-10-24T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U2', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Ink test', '2026-10-24T10:04:00Z'), N('n2', 'Erasers', '2026-10-24T10:03:00Z'),
            N('n3', 'Panel', '2026-10-24T10:02:00Z'), N('n4', 'Big', '2026-10-24T10:01:00Z')],
    pages: [P('p1', 'n1', 0), P('p2', 'n1', 1), P('p3', 'n1', 2), P('p4', 'n2', 0), P('p6', 'n3', 0), P('p5', 'n4', 0)] }));
  if (big) {
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    const out = [], base = Date.now() - 1e7;
    for (let i = 0; i < 1500; i++) {
      let x = 40 + rnd() * 700, y = 40 + rnd() * 1040; const pts = [];
      for (let k = 0; k < 16; k++) { pts.push([Math.round(x * 10) / 10, Math.round(y * 10) / 10]); x += rnd() * 8 - 2; y += rnd() * 6 - 3; }
      out.push({ id: 'big' + i, page_id: 'p5', seq: base + i, kind: 'pen', style: { colour: '#1F2328', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: pts } });
    }
    localStorage.setItem('pw.strokes.p5', JSON.stringify(out));
  }
}"""
PATHS_JS = """(i) => [...document.querySelectorAll(`#stack .sheet[data-index="${i}"] svg.ink path`)].map(p => ({
  id: p.dataset.id, stroke: p.getAttribute('stroke'), width: p.getAttribute('stroke-width'), dash: p.getAttribute('stroke-dasharray'),
  opacity: p.getAttribute('stroke-opacity'), blend: p.style.mixBlendMode, cap: p.getAttribute('stroke-linecap'), join: p.getAttribute('stroke-linejoin'), d: p.getAttribute('d'), cls: p.getAttribute('class') }))"""
STROKES_JS = "(id) => window.__pw.ink.strokesOf(id)"
# the ink layer's groups, checked against the records: .hl first, .pen second; every highlighter path in
# .hl > .hlo[data-opacity] matching its record, no stroke-opacity on it; pen paths in .pen; seq order inside
# each group; no empty .hlo; .hlo groups in ascending opacity
LAYER_JS = """([i, pid]) => {
  const svg = document.querySelector(`#stack .sheet[data-index="${i}"] svg.ink`), bad = [];
  const recs = window.__pw.ink.strokesOf(pid), byId = new Map(recs.map(r => [r.id, r]));
  const kids = [...svg.children].map(c => c.getAttribute('class'));
  if (kids.join() !== 'hl,pen') bad.push('children ' + kids.join());
  const hl = svg.querySelector(':scope > g.hl'), pen = svg.querySelector(':scope > g.pen');
  const groups = [...hl.children].map(g => [g.getAttribute('class'), g.dataset.opacity, g.getAttribute('opacity'), g.children.length]);
  for (const [c, o, a, n] of groups) { if (c !== 'hlo' || o !== a || !n) bad.push('group ' + [c, o, a, n].join('/')); }
  const ops = groups.map(g => +g[1]); if (ops.some((v, k) => k && v <= ops[k - 1])) bad.push('order ' + ops.join());
  const all = [...svg.querySelectorAll('path')];
  if (all.length !== recs.length) bad.push('count ' + all.length + ' vs ' + recs.length);
  for (const el of all) {
    const r = byId.get(el.dataset.id); if (!r) { bad.push('no record ' + el.dataset.id); continue; }
    if (r.kind === 'highlighter') {
      const g = el.parentNode;
      if (!(g.matches('g.hlo') && g.parentNode === hl && g.dataset.opacity === String(r.style.opacity))) bad.push('hl parent ' + r.id);
      if (el.hasAttribute('stroke-opacity') || el.style.mixBlendMode) bad.push('hl own opacity ' + r.id);
    } else if (el.parentNode !== pen) bad.push('pen parent ' + r.id);
  }
  for (const g of [pen, ...hl.children]) {
    const seqs = [...g.children].map(e => byId.get(e.dataset.id)).filter(Boolean).map(r => r.seq);
    if (seqs.some((s, k) => k && s < seqs[k - 1])) bad.push('seq order');
  }
  return { bad, groups, hl: recs.filter(r => r.kind === 'highlighter').length, pen: recs.filter(r => r.kind !== 'highlighter').length };
}"""
STORED_JS = "(id) => JSON.parse(localStorage.getItem('pw.strokes.' + id) || 'null')"
PAGES_JS = "() => [...document.querySelectorAll('#stack .sheet')].map(s => s.dataset.id)"
NO_RIBBON_JS = """() => [...document.querySelectorAll('*')].filter(e =>
  /ribbon|bookmark/i.test((typeof e.className === 'string' ? e.className : (e.className && e.className.baseVal) || '') + ' ' + e.id + ' '
    + (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || ''))).map(e => e.tagName + '#' + e.id)"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def paths(pg, i): return pg.evaluate(PATHS_JS, i)
def layer(pg, i, pid): return pg.evaluate(LAYER_JS, [i, pid])
def strokes(pg, pid): return pg.evaluate(STROKES_JS, pid)
def stored(pg, pid): return pg.evaluate(STORED_JS, pid)
def menu_items(pg): return [t.strip() for t in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name):
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def go_page(pg, i):
    open_list(pg); thumb(pg, i).click(); pg.wait_for_timeout(80)
def thumb_menu(pg, i):
    open_list(pg); thumb(pg, i).click(button="right"); return menu_items(pg)
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, pts, steps=6):
    sx, sy = screen(pg, i, *pts[0])
    pg.mouse.move(sx, sy); pg.mouse.down()
    for x, y in pts[1:]:
        tx, ty = screen(pg, i, x, y); pg.mouse.move(tx, ty, steps=steps)
    pg.mouse.up(); pg.wait_for_timeout(30)
def tap_page(pg, i, x, y):
    sx, sy = screen(pg, i, x, y); pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(30)
def line(y, x0=100, x1=400, n=4): return [(x0 + (x1 - x0) * k / n, y) for k in range(n + 1)]
def bg(pg, sel): return pg.evaluate("(s) => getComputedStyle(document.querySelector(s)).backgroundColor", sel)
def fresh(b, **kw):
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, **kw)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg)
    return ctx, pg, errs

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx, pg, errs = fresh(b)
        pg.evaluate(SEED_JS, False); pg.reload(); ready(pg)

        # ------------------------------------------------------------ the tray
        group[0] = "tray"
        open_note(pg, "Ink test")
        sw = pg.evaluate("[...document.querySelectorAll('#tray .colours .sw')].map(s => [s.dataset.colour, s.getAttribute('aria-label')])")
        check("her 13 colours in her order, with her names", sw == [["#2CB05F", "Green"], ["#37D366", "Light green"], ["#0D0DFF", "Blue"], ["#FF0C84", "Pink"],
              ["#FF7043", "Orange"], ["#A83AFF", "Purple"], ["#FFC107", "Amber"], ["#00BCD5", "Cyan"], ["#04878F", "Teal"], ["#FF00FF", "Magenta"],
              ["#FF3636", "Red"], ["#000000", "Black"], ["#808080", "Grey"]], sw)
        st0 = pg.evaluate("window.__pw.tray()")
        check("defaults: pen Black #000000, highlighter Amber #FFC107", st0["pen"]["colour"] == "#000000" and st0["highlighter"]["colour"] == "#FFC107", [st0["pen"], st0["highlighter"]])
        order = pg.evaluate("""[...document.getElementById('tray').querySelectorAll(':scope > *, :scope > .tools > *')]
          .map(e => e.dataset.tool || e.dataset.slot || e.id || e.className)""")
        check("order: colours, pen, highlighter, stroke eraser, area eraser, 2 empty slots, gap, undo, redo, Tools slot",
              order == ["colours", "tools", "pen", "highlighter", "eraser", "area", "restyle", "select", "gap", "undoBtn", "redoBtn", "tools"], order)
        check("the slots are empty (no visible button)", pg.evaluate("[...document.querySelectorAll('#tray .slot')].every(s => !s.children.length)"))
        check("pen selected by default, soft tint", "on" in pg.get_attribute("#tool-pen", "class") and pg.locator("#tray .tool.on").count() == 1)
        check("Black swatch marked current", pg.get_attribute("#tray .sw[data-colour='#000000']", "class").split().count("on") == 1)
        ring = pg.evaluate("getComputedStyle(document.querySelector(\"#tray .sw[data-colour='#808080']\")).boxShadow")
        check("light mode: the Grey swatch has a dark ring on the light tray", "rgba(38, 42, 48, 0.45)" in ring and "inset" in ring, ring)
        cs = pg.evaluate("(() => { const s = getComputedStyle(document.getElementById('counter')); return [s.backgroundColor, s.color, s.fontWeight, s.fontSize, s.borderRadius, s.paddingTop]; })()")
        check("page number: plain grey text, no pill (transparent, #808080, 600, 13 px)", cs == ["rgba(0, 0, 0, 0)", "rgb(128, 128, 128)", "600", "13px", "0px", "0px"], cs)
        tb = pg.locator("#tray").bounding_box()
        check("tray 56 px wide, nothing overflows at 1280x800", tb["width"] == 56 and pg.evaluate("(() => { const t = document.getElementById('tray'); return t.scrollHeight <= t.clientHeight; })()"), tb)
        check("no tool labels in the tray (icons only)", pg.evaluate("[...document.querySelectorAll('#tray button')].every(b => !b.innerText.trim())"))

        # ------------------------------------------------------------ pen strokes, undo, redo, reload
        group[0] = "ink"
        go_page(pg, 2)
        for k in range(3): draw(pg, 2, line(120 + 70 * k))
        p2 = paths(pg, 2)
        check("page 2 has three paths", len(p2) == 3, len(p2))
        check("black, width 2.5, round caps, solid", all(p["stroke"] == "#000000" and p["width"] == "2.5" and p["cap"] == "round" and not p["dash"] for p in p2), p2[:1])
        check("pages 1 and 3 have none", len(paths(pg, 1)) == 0 and len(paths(pg, 3)) == 0)
        rec = strokes(pg, "p2")
        first = rec[0]["data"]["points"][0] if rec else None
        check("record shape: page_id, seq, kind pen, style, points in page px", rec and rec[0]["page_id"] == "p2" and rec[0]["kind"] == "pen"
              and rec[0]["style"] == {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1} and rec[0]["seq"] > 1.7e12, rec[:1])
        check("first point lands where the mouse went down (100, 120)", first and abs(first[0] - 100) < 1 and abs(first[1] - 120) < 1, first)
        check("smoothed: quadratic curves", "Q" in p2[0]["d"], p2[0]["d"][:60])
        check("kept on the device on every change", len(stored(pg, "p2") or []) == 3)
        pg.click("#undoBtn"); idle(pg)
        check("undo removes one", len(paths(pg, 2)) == 2 and len(stored(pg, "p2")) == 2)
        pg.click("#redoBtn"); idle(pg)
        check("redo brings it back", len(paths(pg, 2)) == 3 and len(stored(pg, "p2")) == 3)
        pg.keyboard.press("Control+z"); pg.wait_for_timeout(30); a = len(paths(pg, 2))
        pg.keyboard.press("Control+y"); pg.wait_for_timeout(30); c = len(paths(pg, 2))
        check("Ctrl+Z and Ctrl+Y", a == 2 and c == 3, [a, c])
        pg.reload(); ready(pg); pg.wait_for_timeout(80)
        check("reload keeps all three", len(paths(pg, 2)) == 3 and len(paths(pg, 1)) == 0 and len(paths(pg, 3)) == 0, len(paths(pg, 2)))
        check("undo is empty after a reload", pg.locator("#undoBtn").is_disabled())
        go_page(pg, 2)
        pg.click("#addPageBtn"); pg.wait_for_timeout(80)
        new_id = pg.evaluate(PAGES_JS)[2]
        draw(pg, 3, line(200))
        check("add a page below 2, draw on it", len(pg.evaluate(PAGES_JS)) == 4 and len(paths(pg, 3)) == 1 and strokes(pg, new_id)[0]["page_id"] == new_id)
        pg.click("#undoBtn"); pg.wait_for_timeout(40); a = [len(pg.evaluate(PAGES_JS)), len(paths(pg, 3))]
        pg.click("#undoBtn"); idle(pg); c = pg.evaluate(PAGES_JS)
        check("undo twice: first the stroke, then the page", a == [4, 0] and c == ["p1", "p2", "p3"], [a, c])
        pg.click("#redoBtn"); pg.click("#redoBtn"); idle(pg)
        check("redo twice: the page comes back with its ink", len(pg.evaluate(PAGES_JS)) == 4 and len(paths(pg, 3)) == 1)
        pg.click("#undoBtn"); pg.click("#undoBtn"); idle(pg)

        # ------------------------------------------------------------ page menu: Copy, Cut, Paste, Erase page
        group[0] = "page menu"
        go_page(pg, 1); draw(pg, 1, line(300, 150, 450))
        items = thumb_menu(pg, 2); pg.keyboard.press("Escape")
        check("Samsung's order, no Paste before a copy", items == ["Add page", "Copy", "Cut", "Delete", "Erase page"], items)
        thumb_menu(pg, 2); menu(pg, "Copy")
        items = thumb_menu(pg, 3)
        check("after Copy: Paste appears in its place", items == ["Add page", "Copy", "Cut", "Paste", "Delete", "Erase page"], items)
        U = lambda: pg.evaluate("window.__pw.S.hist['n1'].u.length")
        u_paste = U(); menu(pg, "Paste"); idle(pg); u_paste = U() - u_paste
        ids = pg.evaluate(PAGES_JS)
        p4, p2 = paths(pg, 4), paths(pg, 2)
        check("paste below page 3: four pages", len(ids) == 4 and ids[:3] == ["p1", "p2", "p3"], ids)
        check("the new page has the same three paths (new ids)", [p["d"] for p in p4] == [p["d"] for p in p2]
              and not set(p["id"] for p in p4) & set(p["id"] for p in p2) and len(stored(pg, ids[3]) or []) == 3, [len(p4), len(p2)])
        p1_before = strokes(pg, "p1")
        u_cut = U(); thumb_menu(pg, 1); menu(pg, "Cut"); idle(pg); u_cut = U() - u_cut
        check("Cut page 1: three pages", pg.evaluate(PAGES_JS) == ["p2", "p3", ids[3]], pg.evaluate(PAGES_JS))
        check("its strokes wait on the device while undo can bring it back", len(stored(pg, "p1") or []) == 1)
        pg.click("#undoBtn"); idle(pg)
        check("undo brings page 1 back with its ink", pg.evaluate(PAGES_JS) == ids and strokes(pg, "p1") == p1_before and len(paths(pg, 1)) == 1)
        u_erase = U(); thumb_menu(pg, 2); menu(pg, "Erase page"); idle(pg); u_erase = U() - u_erase
        check("Erase page 2: zero paths, the page stays", len(paths(pg, 2)) == 0 and pg.evaluate(PAGES_JS) == ids and stored(pg, "p2") is None)
        pg.click("#undoBtn"); idle(pg)
        check("undo brings the three back", len(paths(pg, 2)) == 3 and len(stored(pg, "p2")) == 3)
        check("Paste, Cut and Erase page are one undo step each", [u_paste, u_cut, u_erase] == [1, 1, 1], [u_paste, u_cut, u_erase])
        thumb_menu(pg, 1); menu(pg, "Cut"); idle(pg)
        back(pg); idle(pg)
        check("closing the note clears the strokes of a page cut for good", stored(pg, "p1") is None)
        open_note(pg, "Ink test")
        check("reopened: three pages, page 1 = the old page 2 with its ink", pg.evaluate(PAGES_JS) == ["p2", "p3", ids[3]] and len(paths(pg, 1)) == 3)
        check("no page errors (ink, menu)", not errs, errs)
        back(pg)

        # ------------------------------------------------------------ the pen panel
        group[0] = "pen panel"
        open_note(pg, "Panel")
        pg.click("#tool-pen"); pg.wait_for_timeout(40)
        vis = pg.locator("#toolPanel").is_visible()
        pb, tb, bb = pg.locator("#toolPanel").bounding_box(), pg.locator("#tray").bounding_box(), pg.locator("#tool-pen").bounding_box()
        check("tap the pen again: its panel opens left of the tray, next to the pen", vis and pb["x"] + pb["width"] <= tb["x"] and pb["y"] <= bb["y"] + bb["height"] and pb["y"] + pb["height"] >= bb["y"], [pb, bb])
        sl = pg.evaluate("(() => { const s = document.querySelector('#toolPanel input[type=range]'); return [s.min, s.max, s.step, document.querySelector('#toolPanel .num').textContent]; })()")
        check("width 1 to 12 in 0.5 steps, number showing 2.5", sl == ["1", "12", "0.5", "2.5"], sl)
        check("Solid / Dashed pair, Solid on", pg.locator("#toolPanel .dash").all_inner_texts() == ["Solid", "Dashed"] and "on" in pg.get_attribute("#toolPanel .dash[data-dash='solid']", "class"))
        check("big finger-sized buttons", pg.locator("#toolPanel .step").first.bounding_box()["height"] >= 44)
        pg.click("#tray .sw[data-colour='#FF3636']")
        pg.click("#toolPanel [aria-label='Width bigger']"); pg.click("#toolPanel [aria-label='Width bigger']")
        n1 = pg.inner_text("#toolPanel .num")
        pg.evaluate("(() => { const s = document.querySelector('#toolPanel input[type=range]'); s.value = '6'; s.dispatchEvent(new Event('input', { bubbles: true })); })()")
        n2 = pg.inner_text("#toolPanel .num")
        pg.click("#toolPanel [aria-label='Width smaller']"); n3 = pg.inner_text("#toolPanel .num")
        pg.click("#toolPanel .dash[data-dash='dashed']")
        check("+ twice 3.5, slider 6, minus 5.5", [n1, n2, n3] == ["3.5", "6", "5.5"], [n1, n2, n3])
        draw(pg, 1, line(150))
        check("a stroke start closes the panel", pg.locator("#toolPanel").is_hidden())
        r = strokes(pg, "p6")[-1]
        p = paths(pg, 1)[-1]
        check("the next stroke carries red, 5.5, dashed", r["style"] == {"colour": "#FF3636", "width": 5.5, "dash": "dashed", "opacity": 1}
              and p["stroke"] == "#FF3636" and p["width"] == "5.5" and p["dash"] == "16.5 16.5", [r["style"], p["dash"]])
        pg.click("#tool-highlighter"); pg.click("#tool-pen")
        draw(pg, 1, line(250))
        r = strokes(pg, "p6")[-1]
        check("highlighter and back: the pen's settings come back", r["kind"] == "pen" and r["style"] == {"colour": "#FF3636", "width": 5.5, "dash": "dashed", "opacity": 1}, r["style"])
        pg.click("#tool-pen"); n4 = pg.inner_text("#toolPanel .num"); dash_on = "on" in pg.get_attribute("#toolPanel .dash[data-dash='dashed']", "class")
        pg.click("#noteName"); pg.wait_for_timeout(30)
        check("the panel shows them too; a tap outside closes it", n4 == "5.5" and dash_on and pg.locator("#toolPanel").is_hidden(), [n4, dash_on])
        pg.keyboard.press("Escape")
        pg.reload(); ready(pg)
        st = pg.evaluate("window.__pw.tray()")
        check("remembered after a reload", st["pen"] == {"colour": "#FF3636", "width": 5.5, "dash": "dashed"}, st["pen"])

        # ------------------------------------------------------------ highlighter
        group[0] = "highlighter"
        pg.click("#tool-highlighter"); pg.click("#tool-highlighter"); pg.wait_for_timeout(30)
        rows = pg.evaluate("[...document.querySelectorAll('#toolPanel .pgroup')].map(g => [g.querySelector('.phd').textContent, g.querySelector('.num').textContent, ...['min','max','step'].map(k => g.querySelector('input').getAttribute(k))])")
        check("panel: width 18 (6 to 40, steps of 2), opacity 40% (20 to 80, steps of 10)",
              rows == [["Width", "18", "6", "40", "2"], ["Opacity", "40%", "20", "80", "10"]], rows)
        pg.click("#toolPanel [aria-label='Opacity bigger']"); pg.click("#toolPanel [aria-label='Opacity bigger']")
        pg.click("#toolPanel [aria-label='Width smaller']")
        draw(pg, 1, line(400))
        p = [q for q in paths(pg, 1) if q["cls"] == "highlighter"][-1]; r = strokes(pg, "p6")[-1]
        grp = pg.evaluate("(id) => { const g = document.querySelector(`svg.ink path[data-id='${id}']`).parentNode; return [g.getAttribute('class'), g.dataset.opacity, g.getAttribute('opacity'), g.parentNode.getAttribute('class')]; }", r["id"])
        check("highlighter path: no stroke-opacity, no blend, round caps and joins, amber, width 16",
              p["opacity"] is None and not p["blend"] and p["cap"] == "round" and p["join"] == "round" and p["stroke"] == "#FFC107" and p["width"] == "16", p)
        check("it sits in .hl > .hlo[data-opacity=0.6] with group opacity 0.6", grp == ["hlo", "0.6", "0.6", "hl"], grp)
        check("its record: kind highlighter, opacity kept", r["kind"] == "highlighter" and r["style"] == {"colour": "#FFC107", "width": 16, "dash": "solid", "opacity": 0.6}, r["style"])
        pg.click("#tool-pen")
        check("the pen's red is back on the swatches", pg.get_attribute("#tray .sw[data-colour='#FF3636']", "class").split().count("on") == 1)
        back(pg)

        # ------------------------------------------------------------ the two erasers
        group[0] = "erasers"
        open_note(pg, "Erasers")
        pg.click("#tool-pen"); pg.click("#tray .sw[data-colour='#000000']")
        pg.click("#toolPanel .dash[data-dash='solid']"); pg.click("#noteName"); pg.keyboard.press("Escape")
        for y in (150, 250, 350): draw(pg, 1, line(y, 100, 500, 8))
        three = [r["id"] for r in strokes(pg, "p4")]
        style1 = strokes(pg, "p4")[0]["style"]
        pg.click("#tool-eraser"); tap_page(pg, 1, 300, 252)
        left = [r["id"] for r in strokes(pg, "p4")]
        check("stroke eraser removes exactly the stroke it touches", left == [three[0], three[2]], [len(left)])
        pg.click("#undoBtn"); pg.wait_for_timeout(30)
        check("undo puts it back", [r["id"] for r in strokes(pg, "p4")] == three)
        tap_page(pg, 1, 300, 262)
        check("12 px away (past the 6 px reach): nothing erased", [r["id"] for r in strokes(pg, "p4")] == three)
        u0 = pg.evaluate("window.__pw.S.hist['n2'].u.length")
        draw(pg, 1, [(200, 110), (200, 390)])
        u1 = pg.evaluate("window.__pw.S.hist['n2'].u.length")
        check("drag across all three: they all go, one undo step", strokes(pg, "p4") == [] and u1 == u0 + 1, [len(strokes(pg, "p4")), u0, u1])
        pg.click("#undoBtn"); pg.wait_for_timeout(30)
        check("one undo brings all three back", [r["id"] for r in strokes(pg, "p4")] == three)
        pg.click("#tool-area")
        sx, sy = screen(pg, 1, 300, 120); pg.mouse.move(sx, sy); pg.mouse.down()
        tx, ty = screen(pg, 1, 300, 165); pg.mouse.move(tx, ty, steps=6)
        ring = pg.evaluate("(() => { const r = document.getElementById('eraserRing'); return r && !r.hidden ? [r.offsetWidth, getComputedStyle(r).borderRadius] : null; })()")
        tx, ty = screen(pg, 1, 300, 180); pg.mouse.move(tx, ty, steps=3); pg.mouse.up(); pg.wait_for_timeout(30)
        check("a faint 24 px circle shows while erasing", ring and ring[0] == 24 and ring[1] == "50%", ring)
        check("the circle goes when the pen lifts", pg.evaluate("document.getElementById('eraserRing').hidden"))
        after = strokes(pg, "p4")
        cut = [r for r in after if r["id"] not in three]
        xs = [[pt[0] for pt in r["data"]["points"]] for r in cut]
        check("area eraser across the middle of a stroke: two strokes", len(after) == 4 and len(cut) == 2, len(after))
        check("same style, new ids, the cut part gone", all(r["style"] == style1 and r["kind"] == "pen" for r in cut) and style1["dash"] == "solid"
              and len(xs) == 2 and max(xs[0]) < 290 and min(xs[1]) > 310 and min(xs[0]) < 101 and max(xs[1]) > 499, [[min(x), max(x)] for x in xs])
        pg.click("#undoBtn"); pg.wait_for_timeout(30)
        check("undo restores the one", [r["id"] for r in strokes(pg, "p4")] == three)
        pg.evaluate("""() => window.__pw.ink.put('p4', [{ id: 'shape1', page_id: 'p4', seq: Date.now(), kind: 'shape',
          style: { colour: '#1F2328', width: 2.5, dash: 'solid', opacity: 1 }, data: { type: 'line', x1: 100, y1: 450, x2: 500, y2: 450 } }])""")
        draw(pg, 1, [(300, 430), (300, 470)])
        ks = [r["kind"] for r in strokes(pg, "p4")]
        check("a shape record is removed whole, not cut", "shape" not in ks and len(ks) == 3, ks)
        pg.click("#tool-pen")
        check("no page errors (panel, highlighter, erasers)", not errs, errs)
        if SHOTS: pg.screenshot(path=str(SHOTS / "u2a-ink.png"))
        ctx.close()

        # ------------------------------------------------------------ flat highlighter (fix 2)
        group[0] = "flat highlighter"
        ctx, pg, errs = fresh(b)
        pg.evaluate(SEED_JS, False)
        pg.evaluate("""() => localStorage.setItem('pw.tools', JSON.stringify({ tool: 'pen',
          pen: { colour: '#1F2328', width: 4, dash: 'dashed' }, highlighter: { colour: '#F9A825', width: 20, opacity: 0.5 } }))""")
        pg.reload(); ready(pg)
        st1 = pg.evaluate("window.__pw.tray()")
        check("an old saved colour falls back to the tool's default; width, dash, opacity stay",
              st1["pen"] == {"colour": "#000000", "width": 4, "dash": "dashed"} and st1["highlighter"] == {"colour": "#FFC107", "width": 20, "opacity": 0.5}, [st1["pen"], st1["highlighter"]])
        pg.evaluate("localStorage.removeItem('pw.tools')"); pg.reload(); ready(pg)
        open_note(pg, "Erasers")
        pg.click("#tool-highlighter")
        draw(pg, 1, line(300, 100, 500, 8)); draw(pg, 1, line(305, 120, 480, 8))
        L = layer(pg, 1, "p4")
        check("two overlapping highlighter strokes: ONE .hlo group at 0.4, both inside", L["groups"] == [["hlo", "0.4", "0.4", 2]] and not L["bad"], L)
        own = pg.evaluate("[...document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink [opacity], #stack .sheet[data-index=\"1\"] svg.ink [stroke-opacity]')].map(e => e.tagName + '.' + e.getAttribute('class'))")
        check("no extra opacity anywhere: only the group carries it", own == ["g.hlo"], own)
        kids = pg.evaluate("[...document.querySelector('#stack .sheet[data-index=\"1\"] svg.ink').children].map(c => c.tagName + '.' + c.getAttribute('class'))")
        check(".hl comes before .pen", kids == ["g.hl", "g.pen"], kids)
        pg.click("#tool-pen"); draw(pg, 1, [(300, 260), (300, 340)])
        last = strokes(pg, "p4")[-1]
        par = pg.evaluate("(id) => document.querySelector(`svg.ink path[data-id='${id}']`).parentNode.getAttribute('class')", last["id"])
        check("a pen stroke after the highlighter lands in .pen (on top)", last["kind"] == "pen" and par == "pen" and not layer(pg, 1, "p4")["bad"], par)
        pg.click("#tool-highlighter"); pg.click("#tool-highlighter"); pg.click("#toolPanel [aria-label='Opacity bigger']"); pg.keyboard.press("Escape")
        draw(pg, 1, line(500, 100, 500, 8))
        L = layer(pg, 1, "p4")
        check("a new opacity (50%) gets its own group, after 0.4", [g[1] for g in L["groups"]] == ["0.4", "0.5"] and not L["bad"], L)
        pg.click("#undoBtn"); idle(pg); L = layer(pg, 1, "p4")
        check("undo a highlighter stroke: its empty group goes, the rest stays", [g[1] for g in L["groups"]] == ["0.4"] and L["hl"] == 2 and not L["bad"], L)
        pg.click("#redoBtn"); idle(pg); L = layer(pg, 1, "p4")
        check("redo: it comes back into its own group", [g[1] for g in L["groups"]] == ["0.4", "0.5"] and L["hl"] == 3 and not L["bad"], L)
        pg.click("#tool-area"); draw(pg, 1, [(300, 280), (300, 325)])
        L = layer(pg, 1, "p4")
        check("area eraser across the highlighter: the pieces stay in the 0.4 group", L["hl"] == 5 and L["groups"][0][:3] == ["hlo", "0.4", "0.4"] and L["groups"][0][3] == 4 and not L["bad"], L)
        pg.click("#undoBtn"); idle(pg); L = layer(pg, 1, "p4")
        check("undo the area erase: structure intact", L["hl"] == 3 and L["groups"][0][3] == 2 and not L["bad"], L)
        pg.click("#redoBtn"); idle(pg); L = layer(pg, 1, "p4")
        check("redo the area erase: structure intact", L["hl"] == 5 and not L["bad"], L)
        pg.click("#tool-eraser"); tap_page(pg, 1, 300, 500); L = layer(pg, 1, "p4")
        check("stroke eraser on the 50% stroke: its group goes", [g[1] for g in L["groups"]] == ["0.4"] and not L["bad"], L)
        pg.click("#undoBtn"); idle(pg)
        thumb_menu(pg, 1); menu(pg, "Erase page"); idle(pg)
        e0 = pg.evaluate("document.querySelector('#stack .sheet[data-index=\"1\"] svg.ink').innerHTML")
        pg.click("#undoBtn"); idle(pg); L = layer(pg, 1, "p4")
        check("Erase page, then undo: back in the right groups", e0 == '<g class="hl"></g><g class="pen"></g>' and L["hl"] == 5 and L["pen"] == 2 and not L["bad"], [e0, L])
        pg.evaluate("""() => window.__pw.ink.put('p4', [{ id: 'hlput', page_id: 'p4', seq: 1, kind: 'highlighter',
          style: { colour: '#2CB05F', width: 18, dash: 'solid', opacity: 0.3 }, data: { points: [[100, 700], [400, 700]] } }])""")
        L = layer(pg, 1, "p4")
        check("put a highlighter record: it lands in a 0.3 group, first in order", [g[1] for g in L["groups"]] == ["0.3", "0.4", "0.5"] and not L["bad"], L)
        idle(pg); pg.reload(); ready(pg); pg.wait_for_timeout(80); L = layer(pg, 1, "p4")
        check("reload: the stored strokes open in the same groups", [g[1] for g in L["groups"]] == ["0.3", "0.4", "0.5"] and L["hl"] == 6 and not L["bad"], L)
        check("no page errors (flat highlighter)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ one finger pans, never draws
        group[0] = "touch"
        ctx, pg, errs = fresh(b, has_touch=True)
        pg.evaluate(SEED_JS, False); pg.reload(); ready(pg)
        open_note(pg, "Ink test")
        cdp = ctx.new_cdp_session(pg)
        t0 = pg.evaluate("document.getElementById('stack').style.transform")
        pts = [(640, 560 - 40 * k) for k in range(8)]
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": pts[0][0], "y": pts[0][1]}]})
        for x, y in pts[1:]:
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]}); pg.wait_for_timeout(16)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); pg.wait_for_timeout(60)
        t1 = pg.evaluate("document.getElementById('stack').style.transform")
        y0 = float(re.search(r"translate\([^,]+, ([-\d.]+)px", t0).group(1)); y1 = float(re.search(r"translate\([^,]+, ([-\d.]+)px", t1).group(1))
        total = pg.evaluate("['p1','p2','p3'].reduce((k, id) => k + window.__pw.ink.strokesOf(id).length, 0)")
        check("a one-finger drag pans the stack", y1 < y0 - 200, [y0, y1])
        check("and adds no stroke", total == 0 and pg.locator("#stack svg.ink path").count() == 0, total)
        check("no page errors (touch)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ 1500 strokes on one page
        group[0] = "1500 strokes"
        ctx, pg, errs = fresh(b)
        pg.evaluate(SEED_JS, True); pg.reload(); ready(pg)
        t = time.perf_counter(); open_note(pg, "Big")
        pg.wait_for_function("document.querySelectorAll('#stack .sheet[data-index=\"1\"] svg.ink path').length === 1500")
        open_ms = (time.perf_counter() - t) * 1000
        check("the page opens with all 1500 paths", pg.locator("#stack .sheet[data-index='1'] svg.ink path").count() == 1500)
        timing = pg.evaluate("""async () => {
          const sh = document.querySelector('#stack .sheet[data-index="1"]'), r = sh.getBoundingClientRect(), z = +document.getElementById('stack').dataset.zoom;
          const ev = (type, x, y) => new PointerEvent(type, { pointerId: 7, pointerType: 'mouse', isPrimary: true, button: 0, buttons: type === 'pointerup' ? 0 : 1,
            clientX: r.left + x * z, clientY: r.top + y * z, bubbles: true, cancelable: true });
          sh.dispatchEvent(ev('pointerdown', 120, 200));
          let maxMove = 0;
          for (let k = 1; k <= 40; k++) { const a = performance.now(); sh.dispatchEvent(ev('pointermove', 120 + k * 7, 200 + Math.sin(k / 3) * 20)); maxMove = Math.max(maxMove, performance.now() - a); }
          const t0 = performance.now();
          sh.dispatchEvent(ev('pointerup', 400, 200));
          const t1 = performance.now();
          const t2 = await new Promise((res) => requestAnimationFrame(() => res(performance.now())));
          return { up: t1 - t0, frame: t2 - t0, move: maxMove, count: sh.querySelectorAll('svg.ink path').length }; }""")
        info_lines.append(f"1500 strokes: open {open_ms:.0f} ms (click to 1500 paths); pointerup handler {timing['up']:.2f} ms; "
                          f"pointerup to next frame {timing['frame']:.1f} ms; slowest pointermove {timing['move']:.2f} ms")
        check("a new stroke is on the page within one frame (pointerup handler under 16 ms)", timing["count"] == 1501 and timing["up"] < 16, timing)
        check("drawing stays instant (each pointermove under 8 ms)", timing["move"] < 8, timing)
        draw(pg, 1, line(600))
        check("a real mouse stroke adds the 1502nd path", pg.locator("#stack .sheet[data-index='1'] svg.ink path").count() == 1502)
        pg.evaluate("""() => { const sh = document.querySelector('#stack .sheet[data-index="1"]'), r = sh.getBoundingClientRect();
          const ev = (type, x, y) => new PointerEvent(type, { pointerId: 9, pointerType: 'mouse', isPrimary: true, button: 0, clientX: r.left + x, clientY: r.top + y, bubbles: true });
          for (let i = 0; i < 105; i++) { sh.dispatchEvent(ev('pointerdown', 100, 300 + i)); sh.dispatchEvent(ev('pointermove', 200, 300 + i)); sh.dispatchEvent(ev('pointerup', 300, 300 + i)); } }""")
        check("the undo stack keeps 100 steps", pg.evaluate("window.__pw.S.hist['n4'].u.length") == 100)
        idle(pg); pg.reload(); ready(pg)
        check("all 1607 kept after a reload", len(stored(pg, "p5")) == 1607)
        check("no page errors (1500)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ dark mode
        group[0] = "dark mode"
        ctx, pg, errs = fresh(b, color_scheme="dark")
        pg.evaluate(SEED_JS, False); pg.reload(); ready(pg)
        open_note(pg, "Ink test")
        d_desk, d_sheet, d_tray = bg(pg, "#desk"), bg(pg, "#stack .sheet"), bg(pg, "#tray")
        check("system dark: the desk inside a note stays light (Samsung style)", d_desk == "rgb(232, 230, 225)", d_desk)
        check("the paper stays #FFFFFF", d_sheet == "rgb(255, 255, 255)", d_sheet)
        check("the tray goes dark", d_tray == "rgb(42, 46, 52)", d_tray)
        d_bar, d_add = bg(pg, "#noteBar"), pg.evaluate("getComputedStyle(document.getElementById('addBelow')).color")
        check("the header bar stays dark", d_bar == "rgb(28, 31, 35)", d_bar)
        check("Add a page below is dark text on the light desk", d_add == "rgb(74, 79, 87)", d_add)
        icons = pg.evaluate("['undoBtn','redoBtn'].map(i => { const s = document.querySelector('#' + i + ' svg'); return [document.getElementById(i).getAttribute('aria-label'), s.getAttribute('stroke-width'), s.getAttribute('stroke-linecap'), s.getAttribute('stroke-linejoin'), s.getAttribute('fill'), s.querySelectorAll('path').length]; })")
        check("undo and redo are curved arrows in the tray icon style", icons == [["Undo", "1.8", "round", "round", "none", 2], ["Redo", "1.8", "round", "round", "none", 2]], icons)
        go_page(pg, 2); draw(pg, 2, line(200))
        p = paths(pg, 2)
        check("ink keeps its colour in dark mode", len(p) == 1 and p[0]["stroke"] == "#000000" and p[0]["width"] == "2.5", p)
        ring = pg.evaluate("getComputedStyle(document.querySelector(\"#tray .sw[data-colour='#000000']\")).boxShadow")
        check("dark mode: the Black swatch has a light ring on the dark tray", "rgba(255, 255, 255, 0.6)" in ring and "inset" in ring, ring)
        cs = pg.evaluate("(() => { const s = getComputedStyle(document.getElementById('counter')); return [s.backgroundColor, s.color]; })()")
        check("dark mode: page number still plain grey on the light desk", cs == ["rgba(0, 0, 0, 0)", "rgb(128, 128, 128)"] and bg(pg, "#desk") == "rgb(232, 230, 225)", cs)
        pg.click("#tool-pen"); pg.click("#tool-pen"); pg.wait_for_timeout(30)
        panel_bg = bg(pg, "#toolPanel"); pg.keyboard.press("Escape")
        open_list(pg); pl_bg = bg(pg, "#pageList"); pl_paper = bg(pg, "#plThumbs .thumbP .paper"); pg.click("#plClose")
        check("panel and page list go dark, their paper stays white", panel_bg == "rgb(42, 46, 52)" and pl_bg == "rgb(34, 38, 43)" and pl_paper == "rgb(255, 255, 255)", [panel_bg, pl_bg, pl_paper])
        back(pg)
        check("the folder view goes dark", bg(pg, "#side") == "rgb(34, 38, 43)" and bg(pg, "#listView .bar") == "rgb(28, 31, 35)", [bg(pg, "#side"), bg(pg, "#listView .bar")])
        check("toggle sits next to Log out in the footer", pg.locator("#side .foot #themeBtn").count() == 1 and pg.get_attribute("#themeBtn", "aria-label") == "Light mode")
        pg.click("#themeBtn")
        l_desk = bg(pg, "#desk") if pg.locator("#desk").is_visible() else None
        open_note(pg, "Ink test")
        l_desk, l_sheet = bg(pg, "#desk"), bg(pg, "#stack .sheet")
        check("toggle to light: desk light, paper white", l_desk == "rgb(232, 230, 225)" and l_sheet == "rgb(255, 255, 255)", [l_desk, l_sheet])
        check("ink the same in light mode", paths(pg, 2)[0]["stroke"] == "#000000")
        back(pg); pg.reload(); ready(pg)
        check("the choice is remembered over the system setting", pg.evaluate("localStorage.getItem('penworks.theme')") == "light" and bg(pg, "#side") == "rgb(245, 244, 240)")
        pg.click("#themeBtn")
        check("toggle back to dark", bg(pg, "#side") == "rgb(34, 38, 43)" and pg.evaluate("document.documentElement.dataset.theme") == "dark")
        check("no page errors (dark)", not errs, errs)
        if SHOTS:
            open_note(pg, "Ink test"); pg.click("#tool-pen"); pg.click("#tool-pen"); pg.wait_for_timeout(50)
            pg.screenshot(path=str(SHOTS / "u2a-dark.png"))
        ctx.close()

        # ------------------------------------------------------------ show-password eye, PWA, nothing bookmark-shaped
        group[0] = "login eye"
        ctx, pg, errs = fresh(b)
        pg.evaluate("document.getElementById('login').hidden = false")
        a = pg.get_attribute("#lp", "type")
        pg.click("#eyeBtn"); c = [pg.get_attribute("#lp", "type"), pg.get_attribute("#eyeBtn", "aria-label")]
        pg.click("#eyeBtn"); d = pg.get_attribute("#lp", "type")
        eb, lb = pg.locator("#eyeBtn").bounding_box(), pg.locator("#lp").bounding_box()
        check("the eye toggles password to text and back", a == "password" and c == ["text", "Hide password"] and d == "password", [a, c, d])
        check("the eye sits inside the field", eb["x"] >= lb["x"] and eb["x"] + eb["width"] <= lb["x"] + lb["width"] and eb["y"] >= lb["y"] - 1 and eb["y"] + eb["height"] <= lb["y"] + lb["height"] + 1, [eb, lb])
        group[0] = "pwa and house rules"
        check("cache is pw-v4h", pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())") == ["pw-v4h"] or "pw-v4h" in pg.evaluate("caches.keys()"), pg.evaluate("caches.keys()"))
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("the new files are in the offline shell", all(f in swt for f in ("./js/ink.js", "./js/store-local.js", "./js/tray.js")))
        pg.evaluate(SEED_JS, False); pg.reload(); ready(pg)
        open_note(pg, "Ink test"); pg.click("#tool-pen"); pg.click("#tool-pen")
        found = pg.evaluate(NO_RIBBON_JS)
        check("nothing bookmark- or ribbon-named (tray, panel)", not found, found)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/ink.js", "./js/tray.js", "./js/store-local.js", "./css/app.css", "./index.html", "./js/app.js", "./js/page.js"])
        check("no em-dashes in the code", "\u2014" not in srcs)
        check("no clip-path ribbon shapes in the CSS", "clip-path" not in pg.evaluate("fetch('./css/app.css').then(r => r.text())"))
        check("no page errors (eye, pwa)", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for line_ in info_lines: print(line_)
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
