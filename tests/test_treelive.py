# PenWorks round 6b checks (pw-v7h): the tree live. Notes and pages rows come over the one Realtime channel, so a note
# dropped from the laptop (tools/drop_pdf.py) or made on another device shows on an open tablet within seconds, without
# switching away and back. Headless Playwright (Python), local twin only (?local=1 with penworks.local.livetree = '1':
# the twin then sends every notes and pages write on its channel, as the database's publication does; a write made
# straight through window.__pw.api plays the other device, and the app's own writes come back as echoes).
# Run: python tests/test_treelive.py
# Groups: a note and 3 PDF pages from outside appear in the open folder within 2 s (one tree read, no visibility
# change); the dropped note's cover is asked for once and lands; an open note shows a page added from outside; this
# device's own new page, stroke and rename read nothing; a page binned and a note deleted upstream go; a dropped channel
# catches up on its next subscribe; house rules.
import sys, subprocess, time, pathlib, re
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8792
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  localStorage.setItem('penworks.local.livetree', '1');
  const t = '2026-10-29T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', bookmark: false, deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Tree', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Class', '2026-10-29T10:02:00Z'), N('n2', 'Other', '2026-10-29T10:01:00Z')],
    pages: [P('r1', 'n1', 0), P('r2', 'n1', 1), P('o1', 'n2', 0)] }));
}"""
# another device (or drop_pdf.py): the PDF into the imports bucket, then one note row and one row per PDF page
DROP_JS = """async ([nid, name]) => {
  const api = window.__pw.api, path = 'local/' + crypto.randomUUID() + '.pdf';
  const blob = await (await fetch('./tests/fixtures/u4a.pdf')).blob();
  const m = await import('./js/pdfin.js'), lib = await m.loadLib();
  const doc = await lib.getDocument({ data: new Uint8Array(await blob.arrayBuffer()), isEvalSupported: false }).promise, sizes = [];
  for (let k = 1; k <= Math.min(3, doc.numPages); k++) { const v = (await doc.getPage(k)).getViewport({ scale: 1 }); sizes.push([v.width, v.height]); }
  await doc.destroy();
  await api.putImport(path, blob);
  await api.insert('notes', { id: nid, folder_id: 'f1', name, pinned: false });
  for (let k = 0; k < sizes.length; k++) {
    const [w, h] = sizes[k];
    await api.insert('pages', { id: nid + '-p' + k, note_id: nid, position: k, orientation: w > h ? 'landscape' : 'portrait',
      background: 'blank', bookmark: false, pdf_path: path, pdf_page: k + 1, pdf_w: w, pdf_h: h });
  }
  return sizes.length;
}"""
TWIN_NOTE_JS = "async (id) => (await window.__pw.api.loadAll()).notes.find((n) => n.id === id) || null"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def tl(pg): return pg.evaluate("window.__pw.treeLive()")
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def timed(pg, fn, ms):
    t0 = time.time(); ok = until(pg, fn, ms, 20); return ok, int((time.time() - t0) * 1000)
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def sheets(pg): return pg.locator("#stack .sheet").count()
def card(pg, nid): return pg.locator(f"#grid .card[data-id='{nid}']").count()
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, y, x0=100, x1=400):
    pts = [(x0 + (x1 - x0) * k / 4, y) for k in range(5)]
    sx, sy = screen(pg, i, *pts[0]); pg.mouse.move(sx, sy); pg.mouse.down()
    for x, yy in pts[1:]:
        tx, ty = screen(pg, i, x, yy); pg.mouse.move(tx, ty, steps=6)
    pg.mouse.up(); pg.wait_for_timeout(30)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
timing = []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)
        until(pg, lambda: pg.evaluate("window.__pw.live.state()") == "subscribed", 2000)
        frow(pg, "Tree").click(); pg.wait_for_timeout(200)

        # ------------------------------------------------------------ a dropped note while the folder view is open
        group[0] = "dropped note"
        pg.wait_for_timeout(1500)                       # the seed's own start is over
        s0, last0 = tl(pg), pg.evaluate("window.__pw.lastLoad")
        n_pages = pg.evaluate(DROP_JS, ["nd", "Dropped paper"])
        ok, ms = timed(pg, lambda: card(pg, "nd") == 1, 2000)
        timing.append(f"  local: the dropped note's card showed {ms} ms after the last row was written")
        check(f"a note + {n_pages} PDF pages from outside: its card is in the open folder within 2 s ({ms} ms)", ok and n_pages == 3, [ms, n_pages])
        check("no visibilitychange was needed: the 60 s rule did not read (lastLoad was fresh before)",
              last0 and pg.evaluate("Date.now()") - last0 < 60000)
        s1 = tl(pg)
        check("the channel carried the rows (4 inserts at least) and the tree was read ONCE", s1["events"] - s0["events"] >= 4
              and s1["reads"] - s0["reads"] == 1, [s0, s1])
        check("this device's tree has the note and its 3 pages", pg.evaluate(
            "() => window.__pw.S.notes.some(n => n.id === 'nd') && window.__pw.S.pages.filter(p => p.note_id === 'nd').length === 3"))

        # ------------------------------------------------------------ its cover
        group[0] = "cover"
        check("a cover was asked for once (the first page's picture)", s1["covers"] - s0["covers"] == 1, [s0, s1])
        cov = until(pg, lambda: (pg.evaluate(TWIN_NOTE_JS, "nd") or {}).get("cover_path"), 15000, 200)
        check("within 15 s the note's cover_path is set in the database (the first page's picture)",
              cov == "local/nd-p0.webp", cov)
        pg.wait_for_timeout(2500)                       # the picture's and the cover's own echoes come back
        s2 = tl(pg)
        check("the picture's and cover's echoes read nothing more, and no second cover was asked for",
              s2["reads"] == s1["reads"] and s2["covers"] == s1["covers"], [s1, s2])
        img = until(pg, lambda: pg.evaluate("() => { const im = document.querySelector(\"#grid .card[data-id='nd'] img\"); return im && im.getAttribute('src'); }"), 4000)
        check("the card shows a picture", bool(img), img)

        # ------------------------------------------------------------ the open note
        group[0] = "open note"
        nrow(pg, "Class").click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(300)
        check("the note opens with its 2 pages", sheets(pg) == 2, sheets(pg))
        pg.evaluate("() => window.__pw.api.insert('pages', { id: 'r3', note_id: 'n1', position: 2, orientation: 'portrait', background: 'lined' })")
        ok, ms = timed(pg, lambda: sheets(pg) == 3, 2000)
        timing.append(f"  local: a page added from outside showed in the open note after {ms} ms")
        check(f"a page added from outside shows in the open note within 2 s ({ms} ms)", ok, [sheets(pg), ms])
        check("the note stays open", pg.locator("#noteView").is_visible())

        # ------------------------------------------------------------ this device's own writes
        group[0] = "own writes"
        pg.wait_for_timeout(1500)
        s3 = tl(pg)
        pg.click("#addPageBtn"); menu(pg, "Page"); pg.wait_for_timeout(100)
        check("her own new page is there", sheets(pg) == 4, sheets(pg))
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(2500)
        s4 = tl(pg)
        check("its row came back on the channel (an echo) but refreshTree read NOTHING", s4["events"] > s3["events"]
              and s4["reads"] == s3["reads"] and s4["news"] == s3["news"], [s3, s4])
        cur = pg.evaluate("window.__pw.current()")
        idx = (cur if isinstance(cur, int) else 0) + 1             # data-index counts from 1
        pid = pg.evaluate("(i) => document.querySelector(`#stack .sheet[data-index=\"${i}\"]`).dataset.id || null", idx)
        draw(pg, idx, 200)
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(2500)
        drawn = pg.evaluate("(id) => id ? window.__pw.api.strokesOf([id]).then(r => r.length) : -1", pid)
        check("her stroke reached the twin", drawn and drawn > 0, [idx, pid, drawn])
        s5 = tl(pg)
        check("a stroke of hers (the page and note touched upstream): echoes, no read", s5["events"] > s4["events"]
              and s5["reads"] == s4["reads"], [s4, s5])
        pg.click("#noteName .nn"); inp = pg.locator("input.rename"); inp.wait_for(timeout=3000)
        inp.fill("Class renamed"); inp.press("Enter")
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(2500)
        s6 = tl(pg)
        check("her own rename: it lands, its echo comes back, no read", pg.evaluate(TWIN_NOTE_JS, "n1")["name"] == "Class renamed"
              and s6["events"] > s5["events"] and s6["reads"] == s5["reads"], [s5, s6])
        # the picture of her stroke lands after its quiet time; its echo reads nothing either
        until(pg, lambda: pg.evaluate("window.__pw.snap().uploads") > 1, 9000, 200)
        pg.wait_for_timeout(2000)
        s7 = tl(pg)
        check("her page picture and cover going up: no read", s7["reads"] == s6["reads"], [s6, s7])

        # ------------------------------------------------------------ gone upstream
        group[0] = "gone upstream"
        pg.evaluate("() => window.__pw.api.update('pages', ['r3'], { deleted_at: new Date().toISOString() })")
        ok, ms = timed(pg, lambda: sheets(pg) == 3, 2500)
        check(f"a page binned on another device leaves the open note within 2.5 s ({ms} ms)", ok, [sheets(pg), ms])
        back(pg)
        pg.evaluate("() => window.__pw.api.remove('notes', ['nd'])")
        ok, ms = timed(pg, lambda: card(pg, "nd") == 0, 2500)
        check(f"a note deleted for good upstream leaves the grid within 2.5 s ({ms} ms)", ok, ms)

        # ------------------------------------------------------------ a dropped channel
        group[0] = "dropped channel"
        pg.evaluate("window.__pw.live.simulateDrop()")
        pg.evaluate("() => window.__pw.api.insert('notes', { id: 'nm', folder_id: 'f1', name: 'Missed', pinned: false })")
        pg.wait_for_timeout(1800)
        check("while the channel is down the event is missed", card(pg, "nm") == 0)
        pg.evaluate("window.__pw.lastLoad = Date.now()")          # under a minute old: only the channel's catch-up can bring it
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        ok, ms = timed(pg, lambda: card(pg, "nm") == 1, 2500)
        check(f"its next subscribe reads the tree once: the missed note shows ({ms} ms)", ok, ms)

        # ------------------------------------------------------------ house rules
        group[0] = "house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7h" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7h", "pw-v7h" in keys, keys)
        srcs = "".join((ROOT / f).read_text(encoding="utf-8") for f in
                       ["js/live.js", "js/api.js", "js/local-backend.js", "js/app.js", "sw.js", "tests/test_treelive.py"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("no page errors", not errs, errs)
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:600]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
for t in timing: print(t)
sys.exit(0 if all(r[2] for r in res) else 1)
