# PenWorks pw-v9u checks, page pictures less often (audit finding G): a page's picture is made 30 s after the last ink
# on it, or at once when she leaves the page (another page, or out of the note) or the app is hidden; a PDF page with no
# ink gets no picture, except a note's first page (the cover). Headless Playwright (Python), local mode (?local=1); the
# twin's in-memory bucket stands in for Storage, its page rows for pages.snapshot_path / snapshot_at.
# Run: python -E -P tests\test_snap30.py
# Groups: thirty seconds (none at 27 s, one by about 30 s, same WebP, same path); leaving the page (another page: at once,
# the page she is on waits; out of the note: at once); hidden (visibilitychange, pagehide); PDF pages (the first page's
# picture at once with no ink, an ink-free page gets none, a page with ink gets one); closed inside the 30 s (the next
# start's scan makes the missing picture: a page never pictured, and a pictured page with new ink); house rules.
import sys, time, pathlib, threading, re, tempfile
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); from swcache import SW_CACHE  # the cache name, read from sw.js
PORT = 8849
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
VERSION = SW_CACHE
TMP = pathlib.Path(tempfile.mkdtemp(prefix="pw-snap30-"))
PDF = TMP / "three.pdf"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

class AppHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def make_pdf(path, pages=3):
    doc = fitz.open()
    for k in range(pages):
        p = doc.new_page(width=595.28, height=841.89)
        p.insert_text((60, 80), f"Snap30 page {k + 1}", fontsize=20, fontname="helv")
        p.draw_rect(fitz.Rect(0.2 * 595, 0.2 * 842, 0.4 * 595, 0.3 * 842), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(str(path)); doc.close()

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-11-22T08:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', snapshot_path: null, snapshot_at: null, deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Snap30', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Quiet', '2026-11-22T08:05:00Z'), N('n2', 'Turn', '2026-11-22T08:04:00Z'), N('n3', 'Hide', '2026-11-22T08:03:00Z'),
            N('n4', 'Closed', '2026-11-22T08:02:00Z')],
    pages: [P('q1', 'n1', 0), P('a1', 'n2', 0), P('a2', 'n2', 1), P('a3', 'n2', 2), P('h1', 'n3', 0), P('k1', 'n4', 0), P('k2', 'n4', 1)] }));
}"""
ROW_JS = "() => JSON.parse(localStorage.getItem('penworks.local.v2')).pages"
HIDE_JS = """() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
  document.dispatchEvent(new Event('visibilitychange')); delete document.hidden; }"""

def ready(pg, ms=20000): pg.wait_for_selector("body[data-ready='1']", timeout=ms)
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def stats(pg): return pg.evaluate("window.__pw.snap()")
def row(pg, pid): return next((r for r in pg.evaluate(ROW_JS) if r["id"] == pid), None) or {}
def pic(pg, pid): return row(pg, pid).get("snapshot_path")
def pic_at(pg, pid): return row(pg, pid).get("snapshot_at")
def fresh(pg, pid):
    r = row(pg, pid); return bool(r.get("snapshot_path")) and r.get("snapshot_at") == r.get("updated_at")
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def open_note(pg, name):
    if pg.locator("#noteView").is_visible(): back(pg)
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']")
    pg.wait_for_timeout(120)
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose")
def go_page(pg, i):
    open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120); close_list(pg)
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, y, x0=100, x1=400, wave=10):
    pts = [(x0 + (x1 - x0) * k / 12, y + (wave if k % 2 else -wave)) for k in range(13)]
    sx, sy = screen(pg, i, *pts[0]); pg.mouse.move(sx, sy); pg.mouse.down()
    for x, yy in pts[1:]:
        tx, ty = screen(pg, i, x, yy); pg.mouse.move(tx, ty, steps=3)
    pg.mouse.up(); pg.wait_for_timeout(30)
def wait_to(pg, t_end):
    while time.time() < t_end: pg.wait_for_timeout(min(500, max(10, int((t_end - time.time()) * 1000))))

make_pdf(PDF)
app = ThreadingHTTPServer(("127.0.0.1", PORT), partial(AppHandler, directory=str(ROOT))); app.daemon_threads = True
threading.Thread(target=app.serve_forever, daemon=True).start()
time.sleep(0.5)
errs = []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)
        until(pg, lambda: frow(pg, "Snap30").count() == 1, 5000)
        frow(pg, "Snap30").click(); pg.wait_for_timeout(150)

        # ============================================================ thirty seconds of quiet
        group[0] = "thirty seconds"
        open_note(pg, "Quiet")
        r0 = stats(pg)["renders"]
        draw(pg, 1, 150); draw(pg, 1, 260); t0 = time.time(); idle(pg)
        check("1. two strokes on the page she stays on: the page is waiting (due)", "q1" in stats(pg)["due"], stats(pg))
        wait_to(pg, t0 + 27)
        check("2. 27 s later: still no picture, no render", not pic(pg, "q1") and stats(pg)["renders"] == r0, [pic(pg, "q1"), stats(pg)])
        ok = until(pg, lambda: fresh(pg, "q1"), int(max(0, t0 + 36 - time.time()) * 1000), 100)
        dt = time.time() - t0
        print(f"the quiet picture landed {dt:.1f} s after the last stroke")
        check("3. the picture lands at about 30 s (between 28 and 36 s after the last stroke)", ok and 28 <= dt <= 36, round(dt, 1))
        check("4. the same path as before: local/q1.webp", pic(pg, "q1") == "local/q1.webp", pic(pg, "q1"))
        got = pg.evaluate("""async () => { const b = await window.__pw.api.getSnapshot('local/q1.webp'), bm = await createImageBitmap(b);
          return [b.type, bm.width, bm.height]; }""")
        check("5. the same picture: image/webp, 794 x 1123 (1x)", got == ["image/webp", 794, 1123], got)

        # ============================================================ she leaves the page
        group[0] = "leaving the page"
        open_note(pg, "Turn")
        draw(pg, 1, 200); idle(pg); pg.wait_for_timeout(500)
        check("6. ink on page 1: no picture yet", not pic(pg, "a1"), pic(pg, "a1"))
        go_page(pg, 2); t1 = time.time()
        ok = until(pg, lambda: fresh(pg, "a1"), 4000)
        print(f"after the page change: {time.time() - t1:.2f} s")
        check("7. she turns to page 2: page 1's picture comes at once (within 4 s, not 30)", ok, [row(pg, "a1"), stats(pg)])
        draw(pg, 2, 200); idle(pg); pg.wait_for_timeout(3000)
        check("8. ink on page 2, she stays: 3 s later no picture of page 2 (it waits its 30 s)", not pic(pg, "a2") and "a2" in stats(pg)["due"],
              [pic(pg, "a2"), stats(pg)])
        back(pg); t1 = time.time()
        ok = until(pg, lambda: fresh(pg, "a2"), 4000)
        check("9. she leaves the note: page 2's picture comes at once (within 4 s)", ok, [row(pg, "a2"), stats(pg)])
        check("10. page 3, never written on: no picture", not pic(pg, "a3"), pic(pg, "a3"))

        # ============================================================ the app hidden
        group[0] = "hidden"
        open_note(pg, "Hide")
        draw(pg, 1, 200); idle(pg); pg.wait_for_timeout(1000)
        check("11. ink, 1 s: no picture yet", not pic(pg, "h1"), pic(pg, "h1"))
        pg.evaluate(HIDE_JS)
        ok = until(pg, lambda: fresh(pg, "h1"), 4000)
        check("12. the app hidden (visibilitychange): the picture comes at once (within 4 s)", ok, [row(pg, "h1"), stats(pg)])
        at1 = pic_at(pg, "h1")
        draw(pg, 1, 320); idle(pg); pg.wait_for_timeout(1000)
        check("13. more ink, 1 s: the picture is the old one", pic_at(pg, "h1") == at1, [pic_at(pg, "h1"), at1])
        pg.evaluate("window.dispatchEvent(new Event('pagehide'))")
        ok = until(pg, lambda: pic_at(pg, "h1") != at1 and fresh(pg, "h1"), 4000)
        check("14. pagehide: a new picture at once (within 4 s)", ok, [row(pg, "h1"), at1])
        back(pg)

        # ============================================================ PDF pages
        group[0] = "pdf pages"
        frow(pg, "Snap30").click(); pg.wait_for_timeout(100)
        before = pg.evaluate("window.__pw.S.notes.length")
        with pg.expect_file_chooser() as fc:
            pg.click("#openPdf")
        fc.value.set_files(str(PDF))
        pg.wait_for_function(f"window.__pw.S.notes.length > {before}", timeout=60000)
        pg.wait_for_selector("#noteView:not([hidden])")
        pg.wait_for_function("document.querySelector('#stack .sheet[data-index=\"1\"] > .pdfLayer > canvas')", timeout=20000)
        pids = pg.evaluate("() => { const S = window.__pw.S; return S.pages.filter(p => p.note_id === S.openNote).sort((a, b) => a.position - b.position).map(p => p.id); }")
        check("15. a three-page PDF is a note of three pages", len(pids) == 3, pids)
        p1, p2, p3 = (pids + [None, None, None])[:3]
        ok = until(pg, lambda: fresh(pg, p1), 8000, 100)
        check("16. its first page (no ink) gets its picture at once, while she is still on it (the note's cover)", ok, [row(pg, p1), stats(pg)])
        nid = pg.evaluate("window.__pw.S.openNote")
        check("17. ... and it is the note's cover", until(pg, lambda: pg.evaluate("(id) => (window.__pw.S.notes.find(n => n.id === id) || {}).cover_path", nid) == pic(pg, p1), 3000))
        sk0 = stats(pg)["skipped"]
        go_page(pg, 2)
        draw(pg, 2, 300); idle(pg)
        pg.click("#undoBtn"); idle(pg)
        n2 = pg.evaluate("(id) => window.__pw.ink.strokesOf(id).length", p2)
        check("18. page 2: a stroke drawn and undone, no ink left on it, and it is waiting", n2 == 0 and p2 in stats(pg)["due"], [n2, stats(pg)])
        go_page(pg, 3)
        draw(pg, 3, 300); idle(pg)
        back(pg)
        ok = until(pg, lambda: fresh(pg, p3), 6000)
        check("19. page 3 with ink: it gets its picture (at once, she left the note)", ok, [row(pg, p3), stats(pg)])
        until(pg, lambda: not stats(pg)["due"] and not stats(pg)["running"], 4000)
        pg.wait_for_timeout(1000)
        check("20. page 2, a PDF page with no ink: no picture made (skipped)", not pic(pg, p2) and stats(pg)["skipped"] > sk0, [row(pg, p2), stats(pg)])

        # ============================================================ closed inside the 30 s: the next start makes it
        group[0] = "closed inside the 30 s"
        # k2 gets a picture first, and the device's tree copy learns it (a reload reads the tree again)
        open_note(pg, "Closed")
        go_page(pg, 2); draw(pg, 2, 200); idle(pg); back(pg)
        until(pg, lambda: fresh(pg, "k2"), 5000)
        pg.reload(); ready(pg); pg.wait_for_timeout(1500)
        at_k2 = pic_at(pg, "k2")
        check("21. set-up: page 2 of 'Closed' has a picture, page 1 none", at_k2 and not pic(pg, "k1"), [row(pg, "k1"), row(pg, "k2")])
        if not nrow(pg, "Closed").is_visible(): frow(pg, "Snap30").click(); pg.wait_for_timeout(150)
        open_note(pg, "Closed"); go_page(pg, 1)
        pg.evaluate("async () => { window.__oldTree = await window.__pw.treeq.lastTree(); }")   # the device's tree copy before the ink
        # from here no picture lands on this page load: the app is gone (closed, killed) before any of them gets up
        pg.evaluate("() => { window.__pw.api.putSnapshot = () => Promise.reject(new Error('the app was closed')); }")
        draw(pg, 1, 200)                                    # page 1, never pictured
        go_page(pg, 2); pg.wait_for_timeout(200)
        draw(pg, 2, 400); idle(pg)                          # page 2, pictured before, new ink
        pg.wait_for_timeout(1500)
        k1, k2 = row(pg, "k1"), row(pg, "k2")
        check("22. before the close: page 1 has no picture, page 2's is older than its ink (both strokes are in the database)",
              not k1.get("snapshot_path") and k1.get("updated_at") != k1.get("created_at")
              and k2.get("snapshot_at") == at_k2 and k2.get("updated_at") > at_k2, [k1, k2])
        # no tree read since the ink (the usual case): the device's copy still has the old page stamps
        pg.evaluate("() => window.__pw.treeq.keepTree(window.__oldTree)"); pg.wait_for_timeout(500)
        pg.evaluate("localStorage.setItem('penworks.local.hang', JSON.stringify(['loadAll']))")   # the start's tree read lands late
        pg.reload(); ready(pg)                               # the app closed inside the 30 s and opened again
        pg.wait_for_timeout(1500)
        check("23. the next start draws from the device's copy (the read held back): neither page is waiting yet",
              not {"k1", "k2"} & set(stats(pg)["due"]) and not fresh(pg, "k1") and pic_at(pg, "k2") == at_k2, stats(pg))
        pg.evaluate("localStorage.removeItem('penworks.local.hang')")   # the read lands with the new page stamps
        ok1 = until(pg, lambda: fresh(pg, "k1"), 10000, 100)
        check("24. when the read lands, page 1's missing picture is made by itself (no ink, no visit)", ok1, [row(pg, "k1"), stats(pg)])
        ok2 = until(pg, lambda: fresh(pg, "k2") and pic_at(pg, "k2") != at_k2, 10000, 100)
        check("25. ... and page 2's new picture (the one it was closed on)", ok2, [row(pg, "k2"), at_k2, stats(pg)])
        # the same with the read on time (no hold): closed inside the 30 s again, the next start makes it
        pg.evaluate("() => { window.__pw.api.putSnapshot = () => Promise.reject(new Error('the app was closed')); }")
        at_k2 = pic_at(pg, "k2")
        open_note(pg, "Closed"); go_page(pg, 2); draw(pg, 2, 600); idle(pg); pg.wait_for_timeout(1000)
        pg.reload(); ready(pg)
        ok3 = until(pg, lambda: fresh(pg, "k2") and pic_at(pg, "k2") != at_k2, 10000, 100)
        check("26. closed again inside the 30 s, the read on time: the next start makes page 2's picture", ok3, [row(pg, "k2"), at_k2, stats(pg)])

        # ============================================================ house rules
        group[0] = "house rules"
        keys = pg.evaluate("caches.keys()")
        if VERSION not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check(f"27. cache is {VERSION}", VERSION in keys, keys)
        raw = (ROOT / "sw.js").read_bytes()
        check("28. sw.js has no BOM", not raw.startswith(b"\xef\xbb\xbf"))
        srcs = "".join((ROOT / p).read_text(encoding="utf-8") for p in ["sw.js", "js/app.js", "js/snap.js", "tests/test_snap30.py"])
        check("29. no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("30. no page errors", not errs, errs[:3])
        ctx.close()
        b.close()
finally:
    app.shutdown()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
