# PenWorks pw-v7p checks (her asks 30 Oct): rotate a PDF page, a note opens on its last page, Bookmark under Page.
# Run: python tests/test_rotate.py      (local mode only: ?local=1, the localStorage twin stands in for Supabase)
# The fixture is made here with PyMuPDF: each page has a black block at 20 to 40 % across and 20 to 30 % down, so a turn
# moves that block to a known place. Pixel checks read the rendered canvases, the thumbs and the shared PDF, no screenshots.
import sys, subprocess, time, pathlib, re, base64, tempfile
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8793
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="pw-rotate-"))
FIX = TMP / "rotate.pdf"
A4P = (595.28, 841.89)
# page 1 + 2 + 3 A4 portrait, 4 narrow, 5 A4 with its own /Rotate 90, 6 A4 landscape
doc = fitz.open()
for w, h in [A4P, A4P, A4P, (400.0, 700.0), A4P, (841.89, 595.28)]:
    p_ = doc.new_page(width=w, height=h)
    p_.draw_rect(fitz.Rect(0.2 * w, 0.2 * h, 0.4 * w, 0.3 * h), color=(0, 0, 0), fill=(0, 0, 0))
doc[4].set_rotation(90)
doc.save(str(FIX)); doc.close()

# the block's middle (0.3, 0.25) after t degrees clockwise, as fractions of the page shown
def mark(t):
    x, y = 0.3, 0.25
    for _ in range(t // 90): x, y = 1 - y, x
    return x, y

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-30T10:00:00Z', P = (id, pos) => ({ id, note_id: 'n1', position: pos, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Rot', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Plain', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [P('q1', 0), P('q2', 1), P('q3', 2)] }));
}"""
TWIN_JS = "() => JSON.parse(localStorage.getItem('penworks.local.v2'))"
PIX_JS = """([i, fx, fy]) => { const c = document.querySelector(`#stack .sheet[data-index="${i}"] > .pdfLayer > canvas`);
  if (!c || !c.width) return null;
  const d = c.getContext('2d').getImageData(Math.floor(fx * c.width), Math.floor(fy * c.height), 1, 1).data; return [d[0], d[1], d[2]]; }"""
IMGPIX_JS = """async ([sel, fx, fy]) => { const im = document.querySelector(sel); if (!im || !im.getAttribute('src')) return null;
  try { await im.decode(); } catch (_) { return null; }
  const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
  const g = c.getContext('2d'); g.drawImage(im, 0, 0);
  const d = g.getImageData(Math.floor(fx * c.width), Math.floor(fy * c.height), 1, 1).data; return [d[0], d[1], d[2]]; }"""
SIZE_JS = "(i) => { const s = document.querySelector(`#stack .sheet[data-index='${i}']`); return [parseFloat(s.style.width), parseFloat(s.style.height)]; }"
ROWS_JS = """(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position)
  .map(p => ({ id: p.id, rot: p.pdf_rot || 0, orientation: p.orientation, pdf_w: p.pdf_w, pdf_h: p.pdf_h }))"""
TOASTS_JS = """() => { window.__toastLog = [];
  if (window.__toastOn) return; window.__toastOn = true;
  new MutationObserver(() => window.__toastLog.push(document.getElementById('toast').textContent))
    .observe(document.getElementById('toast'), { childList: true, characterData: true, subtree: true }); }"""
PDF_JS = """async (nid) => { const out = await import('./js/pdfout.js');
  const rows = window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position);
  const blob = await out.buildPdf(rows, 'Turned'); const u = new Uint8Array(await blob.arrayBuffer()); let s = '';
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); }"""

dark = lambda c: c is not None and max(c) < 90
white = lambda c: c is not None and min(c) > 225
def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def twin(pg): return pg.evaluate(TWIN_JS)
def tp(pg, pid): return next(x for x in twin(pg)["pages"] if x["id"] == pid)
def pix(pg, i, f): return pg.evaluate(PIX_JS, [i, f[0], f[1]])
def rows(pg, nid): return pg.evaluate(ROWS_JS, nid)
def size(pg, i): return pg.evaluate(SIZE_JS, i)
def opened(pg): return pg.evaluate("window.__pw.S.openNote")
def cur(pg): return pg.evaluate("window.__pw.current()")
def until(pg, fn, ms=6000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name): nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose")
def go_page(pg, i): open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(200); close_list(pg)
def more(pg): pg.click("#noteMore"); pg.wait_for_selector("#menu:not([hidden])")
def menu_lines(pg): return [t.strip() for t in pg.locator("#menu > *").all_inner_texts()]
def menu_tap(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click(); pg.wait_for_timeout(60)
def menu_shut(pg): pg.mouse.click(640, 700); pg.wait_for_timeout(60)   # a tap on the desk, as she would
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def stroke(pg, i):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    pg.mouse.move(b["x"] + 200 * z, b["y"] + 200 * z); pg.mouse.down()
    pg.mouse.move(b["x"] + 320 * z, b["y"] + 260 * z, steps=8); pg.mouse.up(); pg.wait_for_timeout(60)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(100)
        pg.evaluate(TOASTS_JS)

        # ------------------------------------------------------------ the menu
        group[0] = "menu"
        frow(pg, "Rot").click(); pg.wait_for_timeout(60)
        open_note(pg, "Plain")
        more(pg)
        ml = menu_lines(pg)
        check("a plain page has no Rotate page", "Rotate page" not in ml, ml)
        check("Bookmark sits under Page, above Paper", ml.index("Bookmark") < ml.index("Paper") and ml.index("Page") < ml.index("Bookmark"), ml)
        menu_shut(pg)
        back(pg)
        with pg.expect_file_chooser() as fc:
            pg.click("#openPdf")
        fc.value.set_files(str(FIX))
        check("the PDF opens as a note", until(pg, lambda: opened(pg) not in (None, "n1") and pg.locator("#noteView:not([hidden])").count() == 1, 15000))
        pg.wait_for_timeout(200)
        nid = opened(pg); r0 = rows(pg, nid); ids = [x["id"] for x in r0]
        check("six pages, none turned", len(r0) == 6 and all(x["rot"] == 0 for x in r0), r0)
        more(pg)
        ml = menu_lines(pg)
        check("a PDF page has Rotate page, with Bookmark, both under Page",
              ml.index("Page") < ml.index("Rotate page") < ml.index("Bookmark") < ml.index("Paper"), ml)

        # ------------------------------------------------------------ one page, every turn
        group[0] = "one page"
        check("before: the block where the file has it", until(pg, lambda: dark(pix(pg, 1, mark(0)))), pix(pg, 1, mark(0)))
        menu_tap(pg, "Rotate page")
        check("the menu stays open for another tap", pg.locator("#menu:not([hidden])").count() == 1)
        check("90: the page is wide now", size(pg, 1) == [1123, 794], size(pg, 1))
        check("90: the block has turned", until(pg, lambda: dark(pix(pg, 1, mark(90)))), pix(pg, 1, mark(90)))
        check("90: the old place is white", white(pix(pg, 1, mark(0))), pix(pg, 1, mark(0)))
        r = rows(pg, nid)[0]
        check("90: pdf_rot 90, orientation landscape, the file's own size untouched",
              r["rot"] == 90 and r["orientation"] == "landscape" and r["pdf_w"] == r0[0]["pdf_w"], r)
        idle(pg)
        t = tp(pg, ids[0])
        check("90: saved (the twin's row)", t["pdf_rot"] == 90 and t["orientation"] == "landscape", t)
        menu_tap(pg, "Rotate page")
        check("180: tall again", size(pg, 1) == [794, 1123], size(pg, 1))
        check("180: the picture turned although the size is the same", until(pg, lambda: dark(pix(pg, 1, mark(180)))), pix(pg, 1, mark(180)))
        check("180: nothing left of the old picture", white(pix(pg, 1, mark(0))), pix(pg, 1, mark(0)))
        menu_tap(pg, "Rotate page")
        check("270: the block has turned", until(pg, lambda: dark(pix(pg, 1, mark(270)))), pix(pg, 1, mark(270)))
        menu_tap(pg, "Rotate page")
        check("360 = back to the start", until(pg, lambda: dark(pix(pg, 1, mark(0)))) and rows(pg, nid)[0]["rot"] == 0, rows(pg, nid)[0])
        menu_shut(pg)
        check("the tap that closes the menu draws nothing on the page", pg.evaluate("(id) => window.__pw.ink.strokesOf(id).length", ids[0]) == 0 and pg.locator("#menu").is_hidden())
        pg.click("#undoBtn"); pg.wait_for_timeout(100)
        check("undo: one turn back (270)", rows(pg, nid)[0]["rot"] == 270 and until(pg, lambda: dark(pix(pg, 1, mark(270)))), rows(pg, nid)[0])
        pg.click("#redoBtn"); pg.wait_for_timeout(100)
        check("redo", rows(pg, nid)[0]["rot"] == 0, rows(pg, nid)[0])
        pg.click("#undoBtn"); pg.wait_for_timeout(100)
        pg.click("#undoBtn"); pg.wait_for_timeout(100)
        pg.click("#undoBtn"); pg.wait_for_timeout(100)      # 90 degrees, kept for the next checks
        check("back to 90", rows(pg, nid)[0]["rot"] == 90 and until(pg, lambda: dark(pix(pg, 1, mark(90)))), rows(pg, nid)[0])

        group[0] = "thumbs + other shapes"
        open_list(pg)
        sel = "#plThumbs .thumbP[data-index='1'] img.pdfThumb"
        check("the page list's thumb shows the turn", until(pg, lambda: dark(pg.evaluate(IMGPIX_JS, [sel, *mark(90)]))), pg.evaluate(IMGPIX_JS, [sel, *mark(90)]))
        ar = pg.evaluate("document.querySelector('#plThumbs .thumbP[data-index=\"1\"] .paper').style.aspectRatio")
        check("the thumb is wide", ar.replace(" ", "") == "1123/794", ar)
        close_list(pg)
        go_page(pg, 4)
        more(pg); menu_tap(pg, "Rotate page"); menu_shut(pg)
        s = size(pg, 4)
        check("a narrow page turns wide, the same picture aspect", s[0] == 1123 and abs(s[1] - 1123 * 400 / 700) < 1, s)
        check("a narrow page's block has turned", until(pg, lambda: dark(pix(pg, 4, mark(90)))), pix(pg, 4, mark(90)))
        go_page(pg, 5)
        pg.wait_for_timeout(300)
        own = mark(90)
        check("a page with its own /Rotate 90 shows that first", until(pg, lambda: dark(pix(pg, 5, own))), pix(pg, 5, own))
        more(pg); menu_tap(pg, "Rotate page"); menu_shut(pg)
        check("her turn goes on top of the file's own", until(pg, lambda: dark(pix(pg, 5, mark(180)))) and white(pix(pg, 5, own)), pix(pg, 5, mark(180)))

        # ------------------------------------------------------------ writing locks the turn
        group[0] = "writing"
        go_page(pg, 2)
        pg.evaluate("window.__toastLog = []")
        stroke(pg, 2)
        check("the stroke landed", pg.evaluate("(id) => window.__pw.ink.strokesOf(id).length", ids[1]) == 1)
        more(pg); menu_tap(pg, "Rotate page"); menu_shut(pg)
        check("a page with writing does not turn", rows(pg, nid)[1]["rot"] == 0 and size(pg, 2) == [794, 1123], rows(pg, nid)[1])
        check("she is told why", any("writing" in t_ for t_ in pg.evaluate("window.__toastLog")), pg.evaluate("window.__toastLog"))

        # ------------------------------------------------------------ the page list's Rotate
        group[0] = "tick mode"
        open_list(pg)
        pg.click("#plSelect"); pg.wait_for_timeout(60)
        rb = pg.locator("#plBar .plAct[data-act='rotate']")
        check("Rotate is in the bar, off while nothing is ticked", rb.count() == 1 and rb.is_disabled())
        fits = pg.evaluate("[...document.querySelectorAll('#plBar .plAct')].every(b => b.scrollWidth <= b.clientWidth + 1)")
        words = pg.evaluate("[...document.querySelectorAll('#plBar .plAct')].map(b => [b.textContent, b.clientWidth, b.scrollWidth])")
        check("six words fit the bar", fits, words)
        pg.locator("#plThumbs .thumbP[data-index='3']").click()
        pg.locator("#plThumbs .thumbP[data-index='6']").click()
        pg.locator("#plThumbs .thumbP[data-index='2']").click()
        pg.wait_for_timeout(60)
        pg.evaluate("window.__toastLog = []")
        rb.click(); pg.wait_for_timeout(200)
        rr = rows(pg, nid)
        check("the ticked pages turn, the written one stays", rr[2]["rot"] == 90 and rr[5]["rot"] == 90 and rr[1]["rot"] == 0, rr)
        check("page 6 (wide) is tall now, a turned orientation", rr[5]["orientation"] == "portrait" and rr[2]["orientation"] == "landscape", rr)
        check("she is told about the written one", any("writing" in t_ for t_ in pg.evaluate("window.__toastLog")), pg.evaluate("window.__toastLog"))
        check("the ticks stay", pg.evaluate("window.__pw.S.tick.ids.size") == 3)
        rb.click(); pg.wait_for_timeout(200)
        rr = rows(pg, nid)
        check("a second tap turns them again", rr[2]["rot"] == 180 and rr[5]["rot"] == 180, rr)
        pg.click("#plDone"); pg.wait_for_timeout(60)
        close_list(pg)
        pg.click("#undoBtn"); pg.wait_for_timeout(150)
        rr = rows(pg, nid)
        check("undo = both pages together, ONE step", rr[2]["rot"] == 90 and rr[5]["rot"] == 90, rr)
        idle(pg)
        check("saved", tp(pg, ids[2])["pdf_rot"] == 90 and tp(pg, ids[5])["pdf_rot"] == 90)

        group[0] = "copy + reload + Share"
        go_page(pg, 3)
        open_list(pg)
        pg.locator("#plThumbs .thumbP[data-index='3'] .more").click(); pg.wait_for_timeout(60)
        menu_tap(pg, "Copy")
        pg.locator("#plThumbs .thumbP[data-index='3'] .more").click(); pg.wait_for_timeout(60)
        menu_tap(pg, "Paste"); pg.wait_for_timeout(200)
        close_list(pg)
        rr = rows(pg, nid)
        check("a pasted page keeps the turn", len(rr) == 7 and rr[3]["rot"] == 90 and rr[3]["id"] not in ids, rr[3])
        idle(pg)
        check("the pasted row is saved with the turn", tp(pg, rr[3]["id"])["pdf_rot"] == 90)
        at = cur(pg)
        pg.reload(); ready(pg); pg.wait_for_timeout(300)
        rr = rows(pg, nid)
        check("after a reload the turns are all there", [x["rot"] for x in rr] == [90, 0, 90, 90, 90, 90, 90], [x["rot"] for x in rr])
        data = pg.evaluate(PDF_JS, nid)
        out = TMP / "turned.pdf"; out.write_bytes(base64.b64decode(data))
        d = fitz.open(str(out))
        check("Share as PDF: a turned page is wide", d[0].rect.width > d[0].rect.height, d[0].rect)
        check("Share as PDF: a page not turned stays tall", d[1].rect.width < d[1].rect.height, d[1].rect)
        check("Share as PDF: the own-rotate page at 180 is tall", d[5].rect.width < d[5].rect.height, d[5].rect)
        def pdfpix(page, f):
            px = page.get_pixmap(dpi=40); x, y = int(f[0] * px.width), int(f[1] * px.height)
            return px.pixel(x, y)
        check("Share as PDF: the block is where the screen has it (90)", dark(pdfpix(d[0], mark(90))) and white(pdfpix(d[0], mark(0))), pdfpix(d[0], mark(90)))
        check("Share as PDF: own /Rotate + her turn (180)", dark(pdfpix(d[5], mark(180))), pdfpix(d[5], mark(180)))
        d.close()

        # ------------------------------------------------------------ opens on the last page
        group[0] = "last page"
        check("a reload lands on the page she was on", at > 0 and cur(pg) == at, [at, cur(pg)])
        go_page(pg, 5)
        back(pg)
        open_note(pg, "rotate")
        check("reopening a note lands on her page", cur(pg) == 4, cur(pg))
        check("the count says so", pg.locator("#counter").inner_text().strip().startswith("5"), pg.locator("#counter").inner_text())
        check("that page is sharp too", until(pg, lambda: pix(pg, 5, mark(180)) is not None), None)
        back(pg)
        open_note(pg, "Plain")
        check("another note keeps its own place (the first page)", cur(pg) == 0, cur(pg))
        go_page(pg, 3)
        back(pg)
        open_note(pg, "rotate")
        check("the first note still has its page", cur(pg) == 4, cur(pg))
        KEY = "(v) => localStorage.setItem('penworks.local.page.' + v[0], v[1])"
        CUR_ID = "(n) => window.__pw.S.pages.filter(p => p.note_id === n && !p.deleted_at).sort((a, b) => a.position - b.position)[window.__pw.current()].id"
        back(pg)
        pg.evaluate(KEY, [nid, rr[2]["id"]])
        open_note(pg, "rotate")
        check("kept as a page id, not a number", pg.evaluate(CUR_ID, nid) == rr[2]["id"], cur(pg))
        back(pg)
        pg.evaluate(KEY, [nid, "a-page-that-is-gone"])
        open_note(pg, "rotate")
        check("a page that is gone: the first page", cur(pg) == 0, cur(pg))
        cnt = pg.evaluate("Object.keys(localStorage).filter(k => k.startsWith('penworks.local.page.')).length")
        check("one small entry per note, on this device", cnt == 2, cnt)

        group[0] = "plain note bar + shell"
        back(pg)
        open_note(pg, "Plain")
        open_list(pg)
        pg.click("#plSelect"); pg.wait_for_timeout(60)
        check("no Rotate in the bar of a note with no PDF page", pg.locator("#plBar .plAct[data-act='rotate']").count() == 0)
        pg.click("#plDone"); close_list(pg)
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7p" not in keys:
            pg.wait_for_timeout(800); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7p", "pw-v7p" in keys, keys)
        check("no page errors", not errs, errs)
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
