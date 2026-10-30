# PenWorks U4a checks (PDF in): headless Playwright (Python), same harness as tests/test_u3e.py.
# Run: python tests/test_u4a.py          (local mode only: ?local=1, the localStorage twin stands in for Supabase and its
#                                         `imports` bucket is the browser's IndexedDB penworks.twin.imports)
#      python tests/test_u4a.py --live   (adds the live group: the test login from PW_TEST_USER / PW_TEST_PASS or the
#                                         gitignored .env, never printed; it removes every row and file it makes. It needs
#                                         migration 0005: without the pdf_w / pdf_h columns it is skipped, never applied)
# The fixture tests/fixtures/u4a.pdf is made here with PyMuPDF: 4 pages, A4 portrait, A4 landscape, a square, a tall
# narrow one (a phone screenshot), each with a black block at 20 to 40 % across and 20 to 30 % down. Pixel checks read
# the rendered canvases, the thumbs' images and the shared PDF (PyMuPDF), never a screenshot.
import sys, os, subprocess, time, pathlib, re, json, base64, tempfile
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
LIVE = "--live" in sys.argv
FIX = ROOT / "tests" / "fixtures" / "u4a.pdf"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="pw-u4a-"))
SIZES = [(595.28, 841.89), (841.89, 595.28), (595.28, 595.28), (360.0, 780.0)]
MARK = (0.3, 0.25)            # inside the black block, as fractions of the page
CLEAR = (0.7, 0.7)            # plain white paper

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

def make_pdf(path, sizes):
    doc = fitz.open()
    for w, h in sizes:
        pg = doc.new_page(width=w, height=h)
        pg.draw_rect(fitz.Rect(0.2 * w, 0.2 * h, 0.4 * w, 0.3 * h), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(str(path)); doc.close()
if not FIX.exists(): make_pdf(FIX, SIZES)      # kept as made once (PyMuPDF stamps a date, a rewrite would dirty the repo)
FORTY = TMP / "u4a-40.pdf"; make_pdf(FORTY, [SIZES[0]] * 40)
BROKEN = TMP / "broken.pdf"; BROKEN.write_bytes(b"%PDF-1.7\nthis is not really a pdf at all\n%%EOF\n")
LOCKED = TMP / "locked.pdf"
d_ = fitz.open(); d_.new_page(); d_.save(str(LOCKED), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"); d_.close()
FIX_B64 = base64.b64encode(FIX.read_bytes()).decode()

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-26T10:00:00Z', P = (id, pos) => ({ id, note_id: 'n1', position: pos, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U4a', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Base', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [P('q1', 0), P('q2', 1)] }));
}"""
TWIN_JS = "() => JSON.parse(localStorage.getItem('penworks.local.v2'))"
DOT_JS = "() => document.getElementById('saveDot').dataset.state"
TOASTS_JS = """() => { window.__toastLog = [];
  if (window.__toastOn) return; window.__toastOn = true;
  new MutationObserver(() => window.__toastLog.push(document.getElementById('toast').textContent))
    .observe(document.getElementById('toast'), { childList: true, characterData: true, subtree: true }); }"""
# the on-screen PDF canvas of sheet i: the colour at a fraction of the page (null: no canvas)
PIX_JS = """([i, fx, fy]) => { const c = document.querySelector(`#stack .sheet[data-index="${i}"] > .pdfLayer > canvas`);
  if (!c || !c.width) return null;
  const d = c.getContext('2d').getImageData(Math.floor(fx * c.width), Math.floor(fy * c.height), 1, 1).data; return [d[0], d[1], d[2]]; }"""
# an <img> (a thumb): the colour at a fraction of its picture
IMGPIX_JS = """async ([sel, fx, fy]) => { const im = document.querySelector(sel); if (!im || !im.getAttribute('src')) return null;
  try { await im.decode(); } catch (_) { return null; }
  const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
  const g = c.getContext('2d'); g.drawImage(im, 0, 0);
  const d = g.getImageData(Math.floor(fx * c.width), Math.floor(fy * c.height), 1, 1).data; return [d[0], d[1], d[2]]; }"""
SIZE_JS = "() => [...document.querySelectorAll('#stack .sheet')].map(s => [parseFloat(s.style.width), parseFloat(s.style.height)])"
ROWS_JS = """(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position)
  .map(p => ({ id: p.id, position: p.position, pdf_path: p.pdf_path || null, pdf_page: p.pdf_page ?? null, pdf_w: p.pdf_w ?? null, pdf_h: p.pdf_h ?? null,
               orientation: p.orientation, background: p.background }))"""
B64_PUT_JS = """async ([path, b64]) => { const s = atob(b64), u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  await window.__pw.api.putImport(path, new Blob([u], { type: 'application/pdf' })); }"""
# pw-v6d: one wheel gesture over n frames that lands sheet `to` just past the top of the desk (40 px of it scrolled off,
# so it is the only page on screen)
WHEEL_JS = """async ([to, frames]) => {
  const desk = document.getElementById('desk'), r = desk.getBoundingClientRect();
  const step = (document.querySelector(`#stack .sheet[data-index="${to}"]`).getBoundingClientRect().top - (r.top - 40)) / frames;
  for (let k = 0; k < frames; k++) {
    desk.dispatchEvent(new WheelEvent('wheel', { deltaY: step, clientX: r.left + 300, clientY: r.top + 300, bubbles: true, cancelable: true }));
    await new Promise((ok) => requestAnimationFrame(ok));
  }
  return 1; }"""
# pw-v6d: the same gesture, watching sheet `to` every frame: the frame its thumb showed (a decoded img.pdfPh), the sharp
# renders by then, the frame its canvas came, and what its layer holds at the end
PH_JS = """async ([to, frames]) => {
  const desk = document.getElementById('desk'), r = desk.getBoundingClientRect();
  const sheet = () => document.querySelector(`#stack .sheet[data-index="${to}"]`), st = () => window.__pw.pdf.stats();
  const step = (sheet().getBoundingClientRect().top - (r.top - 40)) / frames, r0 = st().renders;
  let ph = null, cv = null, rph = null;
  const look = (k) => { const L = sheet().querySelector(':scope > .pdfLayer'), im = L.querySelector('img.pdfPh'), c = L.querySelector('canvas');
    if (ph === null && im && im.complete && im.naturalWidth > 0) { ph = k; rph = st().renders - r0; }
    if (cv === null && c && c.width > 0) cv = k; };
  for (let k = 0; k < frames; k++) {
    desk.dispatchEvent(new WheelEvent('wheel', { deltaY: step, clientX: r.left + 300, clientY: r.top + 300, bubbles: true, cancelable: true }));
    await new Promise((ok) => requestAnimationFrame(ok)); look(k);
  }
  const t0 = performance.now(); let k = frames;
  while (cv === null && performance.now() - t0 < 4000) { await new Promise((ok) => requestAnimationFrame(ok)); look(k++); }
  await new Promise((ok) => setTimeout(ok, 50));
  return { ph, cv, rph, frames, after: [...sheet().querySelector(':scope > .pdfLayer').children].map((c) => c.tagName.toLowerCase()) }; }"""
STUB_JS = "navigator.canShare = () => true; navigator.share = async (d) => { window.__shared = d; };"
SHARED_JS = """async () => { const d = window.__shared; if (!d) return null;
  const b64 = async (f) => { const u = new Uint8Array(await f.arrayBuffer()); let s = '';
    for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
  return { files: await Promise.all(d.files.map(async (f) => ({ name: f.name, type: f.type, b64: await b64(f) }))) }; }"""

dark = lambda c: c is not None and max(c) < 90
white = lambda c: c is not None and min(c) > 225
def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def twin(pg): return pg.evaluate(TWIN_JS)
def tlen(pg): return pg.evaluate("window.__pw.treeq.length()")
def stats(pg): return pg.evaluate("window.__pw.pdf.stats()")
def pix(pg, i, f=MARK): return pg.evaluate(PIX_JS, [i, f[0], f[1]])
def imgpix(pg, sel, f=MARK): return pg.evaluate(IMGPIX_JS, [sel, f[0], f[1]])
def rows(pg, nid): return pg.evaluate(ROWS_JS, nid)
def opened(pg): return pg.evaluate("window.__pw.S.openNote")
def strokes(pg, pid): return pg.evaluate("(id) => window.__pw.ink.strokesOf(id).length", pid)
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name): nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose")
def thumb_menu(pg, i): open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}'] .more").click()
def go_page(pg, i): open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(150); close_list(pg)
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def stroke(pg, i, pts):
    sx, sy = screen(pg, i, *pts[0]); pg.mouse.move(sx, sy); pg.mouse.down()
    for x, y in pts[1:]:
        tx, ty = screen(pg, i, x, y); pg.mouse.move(tx, ty, steps=6)
    pg.mouse.up(); pg.wait_for_timeout(40)
def tool(pg, t): pg.click(f"#tool-{t}"); pg.wait_for_timeout(20)
def until(pg, fn, ms=4000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def offline(pg): pg.context.set_offline(True); pg.evaluate("window.dispatchEvent(new Event('offline'))"); pg.wait_for_timeout(50)
def online(pg): pg.context.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))")
def seed(pg): pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(100)
def choose(pg, click, path):
    with pg.expect_file_chooser() as fc:
        click()
    fc.value.set_files(str(path))
def from_folder(pg, folder, path):
    frow(pg, folder).click(); pg.wait_for_timeout(60)
    before = pg.evaluate("window.__pw.S.notes.length")
    choose(pg, lambda: pg.click("#openPdf"), path)
    ok = until(pg, lambda: pg.evaluate("window.__pw.S.notes.length") > before and pg.locator("#noteView:not([hidden])").count() == 1, 15000)
    pg.wait_for_timeout(150)
    return ok
def into_note(pg, path):
    def go():
        pg.click("#addPageBtn"); menu(pg, "PDF")
    choose(pg, go, path)
def toast_texts(pg): return [t for t in pg.evaluate("window.__toastLog") if t]
def a4(): return [794, 1123]

def creds():
    u, p = os.environ.get("PW_TEST_USER"), os.environ.get("PW_TEST_PASS")
    env = ROOT / ".env"
    if (not u or not p) and env.exists():
        kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        u, p = kv.get("PW_TEST_USER", "").strip(), kv.get("PW_TEST_PASS", "").strip()
    return u, p

report = []
live_note = "live group skipped (run with --live)"
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_init_script(STUB_JS)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        seed(pg)
        pg.evaluate(TOASTS_JS)

        # ------------------------------------------------------------ the + tiles
        group[0] = "the + tiles"
        res_js = "() => performance.getEntriesByType('resource').map(e => e.name).filter(n => /pdf(\\.worker)?\\.min\\.mjs/.test(n))"
        check("pdf.js is not loaded on app start", pg.evaluate(res_js) == [], pg.evaluate(res_js))
        frow(pg, "U4a").click(); pg.wait_for_timeout(60)
        tiles = pg.evaluate("""() => { const a = document.getElementById('newNote'), b = document.getElementById('openPdf');
          return b ? { next: a.nextElementSibling === b, same: a.className === b.className, text: b.textContent, label: b.getAttribute('aria-label'),
                       icon: !!b.querySelector('.thumb svg'), ribbon: !!b.querySelector('.bookmarkTab') } : null; }""")
        check("the Open PDF tile sits right after New note, same card style, a document icon, no ribbon",
              tiles and tiles["next"] and tiles["same"] and tiles["text"] == "Open PDF" and tiles["icon"] and not tiles["ribbon"], tiles)
        check("no emoji in the tile", tiles and all(ord(ch) < 0x2190 for ch in tiles["text"]), tiles)
        pg.click("#newNote"); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(100)
        blank = opened(pg); rb = rows(pg, blank)
        check("New note: one tap, a blank note with one A4 grid page", len(rb) == 1 and rb[0]["background"] == "grid" and rb[0]["pdf_path"] is None
              and pg.evaluate(SIZE_JS) == [a4()], [rb, pg.evaluate(SIZE_JS)])
        pg.click("#addPageBtn"); pg.wait_for_timeout(60)
        items = pg.evaluate("[...document.querySelectorAll('#menu button')].map(b => b.textContent)")
        check("in a note the bar's + opens Page and PDF", items == ["Page", "PDF"], items)
        menu(pg, "Page"); pg.wait_for_timeout(80)
        check("Page adds a page below, as before", len(rows(pg, blank)) == 2)
        back(pg)

        # ------------------------------------------------------------ import from the folder view
        group[0] = "import from the folder view"
        ok = from_folder(pg, "U4a", FIX)
        nid = opened(pg)
        n = pg.evaluate("(id) => window.__pw.S.notes.find(x => x.id === id)", nid)
        check("a new note named u4a in the folder, opened", ok and n and n["name"] == "u4a" and n["folder_id"] == "f1", n)
        r = rows(pg, nid)
        check("4 pages", len(r) == 4, len(r))
        want = [(1, 595.28, 841.89, "portrait"), (2, 841.89, 595.28, "landscape"), (3, 595.28, 595.28, "portrait"), (4, 360.0, 780.0, "portrait")]
        got = [(x["pdf_page"], x["pdf_w"], x["pdf_h"], x["orientation"]) for x in r]
        check("each row: pdf_page 1-based, pdf_w / pdf_h in points, orientation", all(g[0] == w_[0] and abs(g[1] - w_[1]) < 0.02 and abs(g[2] - w_[2]) < 0.02 and g[3] == w_[3]
              for g, w_ in zip(got, want)), got)
        check("each row: background blank, one pdf_path in imports/<owner>/<uuid>.pdf", all(x["background"] == "blank" for x in r)
              and len({x["pdf_path"] for x in r}) == 1 and re.match(r"^local/[0-9a-f-]{36}\.pdf$", r[0]["pdf_path"] or ""), [x["pdf_path"] for x in r])
        path = r[0]["pdf_path"]
        sz = pg.evaluate(SIZE_JS)
        check("on screen: A4 portrait = today's A4 portrait size (794 x 1123)", sz[0] == a4(), sz)
        check("A4 landscape = today's landscape size (1123 x 794)", sz[1] == [1123, 794], sz)
        check("square = 210 x 210 mm (794 x 794)", sz[2] == [794, 794], sz)
        check("tall = 210 mm wide, taller by its aspect (794 x 1720)", sz[3] == [794, round(794 * 780 / 360)], sz)
        check("the note opens on its first page", pg.evaluate("window.__pw.current()") == 0)
        idle(pg)
        tw = [p for p in twin(pg)["pages"] if p["note_id"] == nid]
        check("the twin has the 4 rows with their pdf fields", sorted((p["pdf_page"], p["pdf_path"] == path, p["pdf_w"] is not None) for p in tw)
              == [(1, True, True), (2, True, True), (3, True, True), (4, True, True)], [(p["pdf_page"], p["pdf_w"]) for p in tw])
        check("the bytes reached the twin's imports bucket", until(pg, lambda: path in pg.evaluate("window.__pw.api.importsList()"), 5000))

        # ------------------------------------------------------------ the PDF shows
        group[0] = "the PDF shows"
        check("page 1 in view: its canvas shows the dark mark", until(pg, lambda: dark(pix(pg, 1)), 8000), pix(pg, 1))
        check("... and white paper where the PDF is white", white(pix(pg, 1, CLEAR)), pix(pg, 1, CLEAR))
        check("the PDF sits under the ink layer (the ink svg comes after it in the sheet)", pg.evaluate("""() => {
          const s = document.querySelector('#stack .sheet[data-index="1"]'), k = [...s.children];
          return k.indexOf(s.querySelector('.pdfLayer')) < k.indexOf(s.querySelector('svg.ink')) && k.indexOf(s.querySelector('.pdfLayer')) > 0; }"""))
        check("pdf.js loaded now (the first PDF)", len(pg.evaluate(res_js)) >= 1, pg.evaluate(res_js))
        open_list(pg)
        sel1 = "#plThumbs .thumbP[data-index='1'] .paper > img.pdfThumb"
        check("the page list thumbnail shows the mark", until(pg, lambda: dark(imgpix(pg, sel1)), 6000), imgpix(pg, sel1))
        ar = pg.evaluate("() => { const p = document.querySelector(\"#plThumbs .thumbP[data-index='4'] .paper\").getBoundingClientRect(); return p.height / p.width; }")
        check("the tall page's thumb has the tall page's shape", abs(ar - 1720 / 794) < 0.05, ar)
        close_list(pg); back(pg)
        sel_card = f"#grid .card[data-id='{nid}'] .paper > img.pdfThumb"
        check("the new note is first in the grid (last edited first)", pg.evaluate("() => document.querySelector('#grid .card:not(.plus)').dataset.id") == nid)
        check("the note card shows the PDF's first page", until(pg, lambda: dark(imgpix(pg, sel_card)), 6000), imgpix(pg, sel_card))

        # ------------------------------------------------------------ the ink never touches the PDF
        group[0] = "ink never touches the PDF"
        pg.click("#themeBtn"); pg.wait_for_timeout(40)                 # dark mode
        frow(pg, "U4a").click(); pg.locator(f"#grid .card[data-id='{nid}']").click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(200)
        pid1 = r[0]["id"]
        until(pg, lambda: dark(pix(pg, 1)), 4000)
        check("dark mode: the PDF shows as it is (white paper, the dark mark)", pg.evaluate("document.documentElement.dataset.theme") == "dark"
              and white(pix(pg, 1, CLEAR)) and dark(pix(pg, 1)), [pix(pg, 1, CLEAR), pix(pg, 1)])
        y_mark = 0.25 * 1123
        line = [(100 + 75 * k, y_mark) for k in range(5)]
        tool(pg, "pen"); stroke(pg, 1, line)
        check("a stroke across the mark: 1 stroke, the mark still there", strokes(pg, pid1) == 1 and dark(pix(pg, 1)), [strokes(pg, pid1), pix(pg, 1)])
        tool(pg, "eraser"); stroke(pg, 1, [(250, y_mark - 30), (250, y_mark + 30)])
        check("stroke eraser: the stroke gone, the PDF still there", strokes(pg, pid1) == 0 and dark(pix(pg, 1)), [strokes(pg, pid1), pix(pg, 1)])
        pg.click("#undoBtn"); pg.wait_for_timeout(60)
        check("undo: the stroke back, the PDF unchanged", strokes(pg, pid1) == 1 and dark(pix(pg, 1)))
        pg.click("#redoBtn"); pg.wait_for_timeout(60)
        check("redo: the stroke gone again, the PDF unchanged", strokes(pg, pid1) == 0 and dark(pix(pg, 1)))
        tool(pg, "pen"); stroke(pg, 1, line)
        tool(pg, "area"); stroke(pg, 1, [(260, y_mark - 20), (260, y_mark + 20)])
        check("area eraser: the stroke cut in two, the PDF still there", strokes(pg, pid1) == 2 and dark(pix(pg, 1)), [strokes(pg, pid1), pix(pg, 1)])
        pg.evaluate("(id) => window.__pw.ink.selectAll(id)", pid1); pg.wait_for_timeout(60)
        pg.locator(".selChips .chip[data-act='delete']").click(); pg.wait_for_timeout(60)
        check("select all + delete: no strokes, the PDF still there", strokes(pg, pid1) == 0 and dark(pix(pg, 1)), [strokes(pg, pid1), pix(pg, 1)])
        tool(pg, "pen"); stroke(pg, 1, line); stroke(pg, 1, [(x, y_mark + 40) for x, _ in line])
        thumb_menu(pg, 1); menu(pg, "Erase page"); close_list(pg); pg.wait_for_timeout(60)
        check("page Erase: no strokes, the PDF still there", strokes(pg, pid1) == 0 and dark(pix(pg, 1)), [strokes(pg, pid1), pix(pg, 1)])
        k = 0
        while not pg.locator("#undoBtn").is_disabled() and k < 30: pg.click("#undoBtn"); k += 1
        pg.wait_for_timeout(80)
        check("undo all the way back: the 4 PDF pages stay, the PDF still there", len(rows(pg, nid)) == 4 and dark(pix(pg, 1)) and strokes(pg, pid1) == 0,
              [k, len(rows(pg, nid)), strokes(pg, pid1)])
        k = 0
        while not pg.locator("#redoBtn").is_disabled() and k < 30: pg.click("#redoBtn"); k += 1
        pg.wait_for_timeout(80)
        check("redo all the way: still 4 PDF pages, the PDF still there", len(rows(pg, nid)) == 4 and dark(pix(pg, 1)), [k, len(rows(pg, nid))])
        pg.click("#noteMore"); pg.wait_for_timeout(40)
        greys = pg.evaluate("""() => [...document.querySelectorAll('#menu button')].filter(b => ['Portrait', 'Landscape', 'Blank', 'Grid, 1 cm squares', 'Lined'].includes(b.textContent)).map(b => b.disabled)""")
        check("on a PDF page the Portrait / Landscape and paper choices are greyed out", greys == [True] * 5, greys)
        pg.keyboard.press("Escape")
        back(pg)
        pg.click("#themeBtn"); pg.wait_for_timeout(40)                 # light mode again

        # ------------------------------------------------------------ import into an open note
        group[0] = "import into an open note"
        open_note(pg, "Base")
        before = [x["id"] for x in rows(pg, "n1")]
        into_note(pg, FIX)
        ok = until(pg, lambda: len(rows(pg, "n1")) == 6, 15000)
        rn = rows(pg, "n1")
        check("4 pages added AT THE END after the existing pages", ok and [x["id"] for x in rn[:2]] == before
              and [x["pdf_page"] for x in rn[2:]] == [1, 2, 3, 4] and [x["position"] for x in rn] == [0, 1, 2, 3, 4, 5], [(x["position"], x["pdf_page"]) for x in rn])
        check("the existing pages keep their paper", [x["background"] for x in rn[:2]] == ["grid", "grid"] and rn[0]["pdf_path"] is None)
        check("a second PDF file, its own path", rn[2]["pdf_path"] != path and rn[2]["pdf_path"])
        check("the stack goes to the first new page, and it shows the PDF", pg.evaluate("window.__pw.current()") == 2 and until(pg, lambda: dark(pix(pg, 3)), 6000), pix(pg, 3))
        check("not an undo step: undo is still empty", pg.locator("#undoBtn").is_disabled())
        # Add page next to a PDF page: a normal A4 grid page
        pg.click("#addPageBtn"); menu(pg, "Page"); pg.wait_for_timeout(100)
        rn = rows(pg, "n1"); add = rn[3]
        check("Add page next to a PDF page makes a normal A4 grid page", len(rn) == 7 and add["pdf_path"] is None and add["background"] == "grid"
              and add["orientation"] == "portrait" and pg.evaluate(SIZE_JS)[3] == a4(), add)

        # ------------------------------------------------------------ copy, paste, bin and restore keep the PDF
        group[0] = "page operations keep the PDF"
        src = rows(pg, "n1")[2]
        thumb_menu(pg, 3); menu(pg, "Copy"); close_list(pg)
        back(pg); open_note(pg, "Untitled")
        thumb_menu(pg, 1); menu(pg, "Paste"); close_list(pg); pg.wait_for_timeout(150)
        rp = rows(pg, blank)
        pasted = rp[1]
        check("Copy then Paste into another note: the pasted page has the same pdf fields", len(rp) == 3 and all(pasted[k_] == src[k_] for k_ in ("pdf_path", "pdf_page", "pdf_w", "pdf_h")), [pasted, src])
        check("... a page of its own (a new id), and it shows the PDF", pasted["id"] != src["id"] and until(pg, lambda: dark(pix(pg, 2)), 6000), pix(pg, 2))
        idle(pg)
        tp = [p for p in twin(pg)["pages"] if p["id"] == pasted["id"]]
        check("the twin's row for the pasted page carries the pdf fields", tp and tp[0]["pdf_path"] == src["pdf_path"] and tp[0]["pdf_page"] == src["pdf_page"], tp)
        thumb_menu(pg, 2); menu(pg, "Cut"); close_list(pg); pg.wait_for_timeout(80)
        thumb_menu(pg, 1); menu(pg, "Paste"); close_list(pg); pg.wait_for_timeout(150)
        rp = rows(pg, blank)
        check("Cut then Paste: still a PDF page with the same fields", len(rp) == 3 and rp[1]["pdf_path"] == src["pdf_path"] and rp[1]["pdf_page"] == src["pdf_page"], rp)
        back(pg)
        pg.locator(f"#grid .card[data-id='{blank}']").click(button="right"); menu(pg, "Put in the Bin"); pg.wait_for_timeout(60)
        frow(pg, "Bin").click(); pg.locator(f".binItem[data-id='{blank}'] button").click(); pg.wait_for_timeout(80)
        rp = rows(pg, blank)
        check("bin and restore: the PDF page comes back with its fields", len(rp) == 3 and rp[1]["pdf_path"] == src["pdf_path"], rp)
        imp = pg.evaluate("window.__pw.api.importsList()")
        check("no PDF file is ever deleted from storage (both still there)", path in imp and src["pdf_path"] in imp, imp)

        # ------------------------------------------------------------ share as PDF, each page its own shape
        group[0] = "share"
        frow(pg, "U4a").click(); pg.locator(f"#grid .card[data-id='{nid}']").click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(150)
        go_page(pg, 3); tool(pg, "pen"); stroke(pg, 3, [(500, 600), (700, 650)])
        open_list(pg); pg.click("#plSelect"); pg.wait_for_timeout(40)
        pg.locator("#plThumbs .thumbP[data-index='1']").click(); pg.locator("#plThumbs .thumbP[data-index='3']").click()
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg")
        pg.evaluate("window.__shared = null"); pg.click("#shareDlg button[data-share='pdf']")
        pg.wait_for_selector("#shareDlg button[data-share='send']", timeout=30000); pg.click("#shareDlg button[data-share='send']")   # pw-v6b: Send is its own tap
        pg.wait_for_function("window.__shared", timeout=30000)
        sh = pg.evaluate(SHARED_JS)
        f0 = sh["files"][0] if sh and sh["files"] else None
        info = None
        if f0:
            doc = fitz.open(stream=base64.b64decode(f0["b64"]), filetype="pdf")
            info = {"pages": doc.page_count, "sizes": [(round(p_.rect.width, 2), round(p_.rect.height, 2)) for p_ in doc], "marks": []}
            for p_ in doc:
                px = p_.get_pixmap(dpi=72)
                c = px.pixel(int(MARK[0] * px.width), int(MARK[1] * px.height)); w_ = px.pixel(int(CLEAR[0] * px.width), int(0.35 * px.height))
                info["marks"].append((max(c[:3]) < 90, min(w_[:3]) > 225))
            ink_px = doc[1].get_pixmap(dpi=72)
            info["ink"] = max(ink_px.pixel(int(600 / 794 * ink_px.width), int(625 / 794 * ink_px.height))[:3]) < 120
            doc.close()
        near = lambda s_, t_: abs(s_[0] - t_[0]) <= 1 and abs(s_[1] - t_[1]) <= 1
        check("Share as PDF of two pages: the PDF has 2 pages", info and info["pages"] == 2, info)
        check("sizes: A4 (595 x 842 pt) and square (595 x 595 pt), not forced A4", info and near(info["sizes"][0], (595.28, 841.89)) and near(info["sizes"][1], (595.28, 595.28)), info and info["sizes"])
        check("the dark mark is in the picture on both pages, the paper white", info and info["marks"] == [(True, True), (True, True)], info and info["marks"])
        check("her ink is on top of the PDF in the export", info and info["ink"], info)
        pg.wait_for_selector("#shareDlg", state="detached")
        close_list(pg)

        # ------------------------------------------------------------ the page picture (U3b) shows the PDF
        group[0] = "page picture"
        idle(pg)
        def pic_ok():
            p1 = pg.evaluate("(id) => window.__pw.S.pages.find(p => p.id === id)", pid1)
            return p1 and p1["snapshot_path"]
        okp = until(pg, pic_ok, 12000, 200)
        check("the first PDF page gets its picture (the note's cover)", okp, pg.evaluate("window.__pw.snap()"))
        if okp:
            got = pg.evaluate("""async (path) => { const b = await window.__pw.api.getSnapshot(path), im = await createImageBitmap(b);
              const c = new OffscreenCanvas(im.width, im.height), g = c.getContext('2d'); g.drawImage(im, 0, 0);
              const d = g.getImageData(Math.floor(0.3 * im.width), Math.floor(0.25 * im.height), 1, 1).data; return [im.width, im.height, d[0], d[1], d[2]]; }""", okp)
            check("the WebP picture is 794 x 1123 and shows the PDF's mark", got[:2] == [794, 1123] and max(got[2:]) < 90, got)

        # ------------------------------------------------------------ too big, broken, locked: one toast, no rows
        group[0] = "too big and broken"
        back(pg)
        counts = lambda: pg.evaluate("[window.__pw.S.notes.length, window.__pw.S.pages.length, window.__pw.treeq.length()]")
        c0 = counts(); pg.evaluate(TOASTS_JS)
        out = pg.evaluate("""async () => { const f = new File([new Uint8Array(52428801)], 'big.pdf', { type: 'application/pdf' });
          return await window.__pw.pdf.importPdf(f, { folderId: 'f1' }); }""")
        pg.wait_for_timeout(100)
        check("over 50 MB: exactly one toast, 'This PDF is too big to open (over 50 MB).'", toast_texts(pg) == ["This PDF is too big to open (over 50 MB)."], toast_texts(pg))
        check("... and no rows", out is None and counts() == c0, [out, counts(), c0])
        for label, fpath in (("a broken file", BROKEN), ("a password-protected file", LOCKED)):
            pg.evaluate(TOASTS_JS)
            frow(pg, "U4a").click(); pg.wait_for_timeout(40)
            choose(pg, lambda: pg.click("#openPdf"), fpath)
            until(pg, lambda: toast_texts(pg), 6000); pg.wait_for_timeout(300)
            check(f"{label}: exactly one toast, 'This PDF could not be opened.'", toast_texts(pg) == ["This PDF could not be opened."], toast_texts(pg))
            check(f"... and no rows, still the folder view", counts() == c0 and pg.locator("#listView:not([hidden])").count() == 1, [counts(), c0])

        # ------------------------------------------------------------ offline
        group[0] = "offline"
        idle(pg)
        offline(pg)
        ok = from_folder(pg, "U4a", FIX)
        off_nid = opened(pg); ro = rows(pg, off_nid); off_path = ro[0]["pdf_path"] if ro else None
        check("offline: the import works, a note with 4 pages", ok and len(ro) == 4, len(ro))
        check("offline: page 1 shows the PDF", until(pg, lambda: dark(pix(pg, 1)), 8000), pix(pg, 1))
        check("offline: queued, createNote then 4 createPage, the file waits to upload", [o["call"] for o in pg.evaluate("window.__pw.treeq.queued()")]
              == ["createNote"] + ["createPage"] * 4 and pg.evaluate("window.__pw.pdf.uploadsPending()") == 1, [tlen(pg), pg.evaluate("window.__pw.pdf.uploadsPending()")])
        check("the twin has none of it yet", not [x for x in twin(pg)["notes"] if x["id"] == off_nid] and off_path not in pg.evaluate("window.__pw.api.importsList()"))
        pg.reload(); ready(pg); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(300)
        check("offline reload: the note opens again with its 4 pages", opened(pg) == off_nid and pg.locator("#stack .sheet").count() == 4)
        check("offline reload: page 1 still shows the PDF (from the device)", until(pg, lambda: dark(pix(pg, 1)), 8000), pix(pg, 1))
        online(pg)
        def landed():
            tw = [x for x in twin(pg)["pages"] if x["note_id"] == off_nid]
            return (len(tw) == 4 and sorted((x["position"], x["pdf_page"]) for x in tw) == [(0, 1), (1, 2), (2, 3), (3, 4)]
                    and [x for x in twin(pg)["notes"] if x["id"] == off_nid] and off_path in pg.evaluate("window.__pw.api.importsList()")
                    and pg.evaluate("window.__pw.pdf.uploadsPending()") == 0 and pg.evaluate(DOT_JS) == "saved")
        check("online: the twin has the note and the 4 rows in order, the bytes in its imports store, the dot saved", until(pg, landed, 8000),
              [pg.evaluate(DOT_JS), pg.evaluate("window.__pw.pdf.uploadsPending()")])
        check("the bytes stay on the device after the upload", pg.evaluate("(p) => window.__pw.pdf.cached(p)", off_path))
        back(pg)

        # ------------------------------------------------------------ the phone: no bytes on the device, fetched from the bucket
        group[0] = "the phone"
        tw_all = twin(pg)
        ctx2 = b.new_context(viewport={"width": 1280, "height": 900})
        p2 = ctx2.new_page(); e2 = []
        p2.on("pageerror", lambda e: e2.append(str(e)))
        p2.goto(LOCAL); ready(p2)
        p2.evaluate("(d) => { localStorage.clear(); localStorage.setItem('penworks.local.v2', JSON.stringify(d)); }", tw_all)
        p2.evaluate(B64_PUT_JS, [off_path, FIX_B64])          # the bucket holds the file (the tablet uploaded it)
        p2.reload(); ready(p2)
        check("the phone's device has no copy of the bytes", not p2.evaluate("(p) => window.__pw.pdf.cached(p)", off_path))
        r0 = p2.evaluate("window.__pw.api.importReads()")
        frow(p2, "U4a").click(); p2.locator(f"#grid .card[data-id='{off_nid}']").click(); p2.wait_for_selector("#noteView:not([hidden])")
        check("the phone draws the page after fetching the PDF from the bucket", until(p2, lambda: dark(pix(p2, 1)), 10000), pix(p2, 1))
        check("... it read the bucket, and keeps the bytes now", p2.evaluate("window.__pw.api.importReads()") > r0 and p2.evaluate("(p) => window.__pw.pdf.cached(p)", off_path))
        check("no page errors (phone)", not e2, e2)
        ctx2.close()

        # ------------------------------------------------------------ lazy rendering: a 40-page PDF
        group[0] = "40 pages, lazy"
        ok = from_folder(pg, "U4a", FORTY)
        big = opened(pg)
        check("the 40-page PDF opens as a note of 40 pages", ok and len(rows(pg, big)) == 40 and pg.evaluate(
              "(id) => window.__pw.S.notes.find(n => n.id === id).name", big) == "u4a-40", len(rows(pg, big)))
        until(pg, lambda: dark(pix(pg, 1)), 8000)
        until(pg, lambda: pix(pg, 3) is not None, 3000); pg.wait_for_timeout(200)
        s0 = stats(pg)
        check("at the top: the page in view, the one after it and the page ahead (3) have a canvas, nothing else",
              s0["canvases"] == 3 and all(pix(pg, i) is not None for i in (1, 2, 3)), s0)
        sharp_ev = lambda evs: [e for e in evs if e.split()[0] in ("sharp", "ahead")]
        check("... the page in view first, the page ahead last", sharp_ev(s0["events"])[-3:] == ["sharp 1", "sharp 2", "ahead 3"], s0["events"][-6:])

        # ------------------------------------------------------------ pw-v6d: the thumb first, render ahead, keep more
        group[0] = "thumb first, render ahead (pw-v6d)"
        since = lambda s_a, s_b: s_b["events"][len(s_b["events"]) - (s_b["evN"] - s_a["evN"]):] if s_b["evN"] > s_a["evN"] else []
        until(pg, lambda: stats(pg).get("fillLeft") == 0, 20000)       # pw-v7n: the background fill has kept every page's thumb
        th0 = stats(pg)
        m = pg.evaluate(PH_JS, [8, 60])
        th1 = stats(pg)
        check("a long scroll down to page 8: page 8 shows its thumb while the stack still moves", m["ph"] is not None and m["ph"] < m["frames"], m)
        check("... before any sharp render (none while moving)", m["rph"] == 0, m)
        # pw-v7n: nothing from pdf.js while the stack moves; the thumb is the one the background fill kept on the device
        check("... read from the device (kept by the background fill), no pdf.js thumb render while moving (pw-v7n)",
              th1["fromStore"] > th0["fromStore"] and th1["thumbRenders"] == th0["thumbRenders"] and th1["placeholders"] > th0["placeholders"],
              {k: [th0[k], th1[k]] for k in ("fromStore", "thumbRenders", "placeholders")})
        check("then the sharp canvas lands and replaces it (only the canvas in the layer)", m["cv"] is not None and m["cv"] > m["ph"] and m["after"] == ["canvas"], m)
        ev = since(th0, stats(pg))
        check("events: 'ph 8' before 'sharp 8'", "ph 8" in ev and "sharp 8" in ev and ev.index("ph 8") < ev.index("sharp 8"), ev)
        until(pg, lambda: pix(pg, 10) is not None, 3000); pg.wait_for_timeout(200)
        ev = sharp_ev(since(th0, stats(pg)))
        check("landed on 8 going down: page 8 sharp first, page 10 (the page ahead) last", ev[:1] == ["sharp 8"] and ev[-1:] == ["ahead 10"], ev)
        th2 = stats(pg)
        pg.evaluate(WHEEL_JS, [7, 12])
        until(pg, lambda: pix(pg, 5) is not None, 3000); pg.wait_for_timeout(200)
        th3 = stats(pg); ev = sharp_ev(since(th2, th3))
        check("one page back up to 7: the page ahead is now page 5 (the way she moved)", th3["dir"] == -1 and ev[-1:] == ["ahead 5"], [th3["dir"], ev])
        check("nothing seen a moment ago rendered again (8, 9, 10 kept)", not [e for e in ev if e in ("sharp 8", "sharp 9", "sharp 10")], ev)

        pg.evaluate("window.__pw.pdf.budget(5e6)")    # about 5.6 of these pages (794 x 1123 at 1 device px), so the budget bites
        peak = stats(pg)["canvases"]
        desk = pg.locator("#desk").bounding_box()
        pg.mouse.move(desk["x"] + desk["width"] / 2, desk["y"] + desk["height"] / 2)
        for step in range(36):
            pg.mouse.wheel(0, 1300); pg.wait_for_timeout(260)
            peak = max(peak, stats(pg)["canvases"])
        pg.wait_for_timeout(500)
        s1 = stats(pg)
        check("scrolling through all 40 with a 5 Mpx budget: never more than 7 live canvases", peak <= 7, [peak, s1])
        check("further down: page 1's canvas is freed (least recently seen first)", pix(pg, 1) is None and s1["freed"] > 0, s1)
        go_page(pg, 40)
        check("page 40 draws when it comes into view", until(pg, lambda: dark(pix(pg, 40)), 8000), pix(pg, 40))
        pg.wait_for_timeout(300)
        s2 = stats(pg)
        check("at the end: the kept pages and what fits the budget, at most 6 canvases", s2["canvases"] <= 6 and pix(pg, 39) is not None, s2)
        pg.evaluate("window.__pw.pdf.budget(0)")      # the real budget again (60 Mpx: all 40 of these would fit)
        go_page(pg, 20); until(pg, lambda: dark(pix(pg, 20)), 6000); pg.wait_for_timeout(300)
        go_page(pg, 27); until(pg, lambda: dark(pix(pg, 27)), 6000); pg.wait_for_timeout(300)
        k0 = stats(pg)
        check("past the two each side, page 20 (seen a moment ago) keeps its canvas under the budget", pix(pg, 20) is not None, k0)
        go_page(pg, 20); pg.wait_for_timeout(300)
        ev = since(k0, stats(pg))
        check("back to page 20: it shows at once, never rendered again", dark(pix(pg, 20)) and "sharp 20" not in ev, ev)
        pg.evaluate("window.__pw.pdf.budget(2e6)")
        s4 = stats(pg)
        check("a smaller budget: the far pages go (27 freed), the kept pages stay even past it (19 to 21)",
              pix(pg, 27) is None and all(pix(pg, i) is not None for i in (19, 20, 21)) and s4["pixels"] > 2e6, s4)
        pg.evaluate("window.__pw.pdf.budget(0)")
        check("a page seen once leaves its thumb behind (a scaled copy of the sharp canvas, no second render)", s4["seeded"] > 0, s4)
        group[0] = "40 pages, lazy"
        # nothing renders while the stack moves: a 1 s burst of wheel steps, one per frame
        go_page(pg, 10); pg.wait_for_timeout(900)
        m = pg.evaluate("""async () => {
          const desk = document.getElementById('desk'), r = desk.getBoundingClientRect(), s0 = window.__pw.pdf.stats().renders;
          const gaps = []; let last = performance.now(), on = true;
          const tick = (t) => { gaps.push(t - last); last = t; if (on) requestAnimationFrame(tick); };
          requestAnimationFrame(tick);
          for (let k = 0; k < 60; k++) {
            desk.dispatchEvent(new WheelEvent('wheel', { deltaY: 40, clientX: r.left + 300, clientY: r.top + 300, bubbles: true, cancelable: true }));
            await new Promise((ok) => requestAnimationFrame(ok));
          }
          const during = window.__pw.pdf.stats().renders - s0;
          on = false;
          await new Promise((ok) => setTimeout(ok, 900));
          return { during, after: window.__pw.pdf.stats().renders - s0, maxGap: Math.max(...gaps.slice(2)), frames: gaps.length }; }""")
        check("no PDF render while the stack moves (60 frames of wheel)", m["during"] == 0, m)
        check("once it is still, the pages in view render", m["after"] > 0, m)
        check("frames stay smooth while scrolling a PDF note (longest gap under 100 ms)", m["maxGap"] < 100, m)
        s3 = stats(pg)
        report.append(f"40-page fixture: peak live canvases {max(peak, s3['peak'])}, at the end {s2['canvases']}, now {s3['canvases']} "
                      f"({s3['pixels']:,} canvas pixels = {s3['pixels'] * 4 / 1048576:.1f} MB), {s3['renders']} renders, {s3['freed']} freed, "
                      f"{s3['thumbsCached']} thumbs cached, {s3['docs']} open documents; scroll burst {m}")
        print(report[-1])
        back(pg)

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7p" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7p", "pw-v7p" in keys, keys)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("the shell lists pdfin.js, pdfview.js and both pdf.js files", all(x in swt for x in ["./js/pdfin.js", "./js/pdfview.js", "./vendor/pdf.min.mjs", "./vendor/pdf.worker.min.mjs"]))
        shell = pg.evaluate("""async () => { const c = await caches.open('pw-v7p'); const out = [];
          for (const u of ['./vendor/pdf.min.mjs', './vendor/pdf.worker.min.mjs', './js/pdfin.js', './js/pdfview.js']) out.push(!!(await c.match(u))); return out; }""")
        check("... and they are in the cache (PDF pages draw offline)", shell == [True] * 4, shell)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in
                       ["./js/pdfin.js", "./js/pdfview.js", "./js/page.js", "./js/app.js", "./js/api.js", "./js/local-backend.js", "./js/snap.js",
                        "./js/treeq.js", "./js/ink.js", "./css/app.css", "./sw.js", "./index.html", "./vendor/README.md",
                        "./supabase/migrations/0005_pdf_pages.sql", "./tests/test_u4a.py", "./tests/measure_pdf.py"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        mig = pg.evaluate("fetch('./supabase/migrations/0005_pdf_pages.sql').then(r => r.text())")
        check("0005 adds pdf_w, pdf_h (real) and the both-null-or-both-positive check, and says pdf_page is 1-based",
              "add column pdf_w real" in mig and "add column pdf_h real" in mig and "pdf_w > 0 and pdf_h > 0" in mig and "1-BASED" in mig)
        check("no page errors (local)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ live (Supabase), --live only
        if LIVE:
            user, pwd = creds()
            if not user or not pwd:
                live_note = "live group SKIPPED: no test login (PW_TEST_USER / PW_TEST_PASS or .env) on this machine"
            else:
                ctx = b.new_context(viewport={"width": 1280, "height": 900})
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE); pg.wait_for_selector("#login:not([hidden])")
                signed = pg.evaluate("([u, p]) => window.__pw.api.signIn(u, p).then(r => r.ok)", [user, pwd])
                cols = pg.evaluate("window.__pw.api.pdfColumns()") if signed else None
                if not signed:
                    live_note = "live group SKIPPED: the test login was refused"
                elif not cols:
                    live_note = "live group SKIPPED: migration 0005 is not applied (pages.pdf_w / pdf_h missing); it was NOT applied by this test"
                else:
                    group[0] = "live"
                    live_note = ""
                    pg.reload(); ready(pg)
                    ids = {}
                    try:
                        pg.click("#addFolder"); inp = pg.locator("input.rename"); inp.wait_for(); inp.fill("U4a test"); inp.press("Enter")
                        ok = from_folder(pg, "U4a test", FIX)
                        nid_l = opened(pg); rl = rows(pg, nid_l)
                        ids = {"f": pg.evaluate("(id) => window.__pw.S.notes.find(n => n.id === id).folder_id", nid_l), "n": nid_l,
                               "p": [x["id"] for x in rl], "path": rl[0]["pdf_path"] if rl else None, "uid": pg.evaluate("window.__pw.S.user.id")}
                        check("live: the import makes a note of 4 pages", ok and len(rl) == 4, len(rl))
                        idle(pg)
                        def up():
                            d = pg.evaluate("async (ids) => { const d = await window.__pw.api.loadAll(); return d.pages.filter(p => ids.p.includes(p.id)).map(p => [p.pdf_page, p.pdf_w, p.pdf_h, p.pdf_path]); }", ids)
                            return d if len(d) == 4 else None
                        got = until(pg, up, 8000, 300)
                        check("live: the 4 pages rows landed with pdf_page, pdf_w, pdf_h, pdf_path",
                              got and sorted(g_[0] for g_ in got) == [1, 2, 3, 4] and all(g_[1] and g_[2] and g_[3] == ids["path"] for g_ in got), got)
                        check("live: the path is under her own folder", ids["path"] and ids["path"].startswith(ids["uid"] + "/"), ids["path"])
                        okf = until(pg, lambda: pg.evaluate("(p) => window.__pw.api.getImport(p).then(b => b.size, () => 0)", ids["path"]) > 0, 15000, 500)
                        check("live: the imports object landed (downloads)", okf)
                    finally:
                        if ids:
                            idle(pg)
                            left = pg.evaluate("""async (ids) => {
                              const a = window.__pw.api;
                              await a.removeSnapshots(ids.p.map(p => ids.uid + '/' + p + '.webp')).catch(() => {});
                              if (ids.path) await a.removeImports([ids.path]).catch(() => {});
                              await a.remove('pages', ids.p); await a.remove('notes', [ids.n]); await a.remove('folders', [ids.f]);
                              const d = await a.loadAll();
                              return [d.folders.filter(r => r.id === ids.f).length, d.notes.filter(r => r.id === ids.n).length, d.pages.filter(r => ids.p.includes(r.id)).length]; }""", ids)
                            check("clean-up: every row the test made is gone (the storage object removed through the API)", left == [0, 0, 0], left)
                    check("no page errors (live)", not errs, errs)
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
for line_ in report: print(line_)
if live_note: print(live_note)
sys.exit(0 if all(r[2] for r in res) else 1)
