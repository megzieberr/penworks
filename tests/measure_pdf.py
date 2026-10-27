# PenWorks PDF speed (round C, pw-v6d): how long a PDF page takes to show, headless Playwright (Python), ?local=1 only.
# Run: python tests/measure_pdf.py          (prints one table; nothing is checked, these are the numbers behind the round)
# The context has devicePixelRatio 2 (her Tab S11 Ultra is about 2 or more). Two PDFs: tests/fixtures/u4a.pdf (4 small
# vector pages, made by test_u4a.py) and tests/fixtures/scan20.pdf, made here once with PyMuPDF: 20 pages, each a
# 1600 x 2200 JPEG at 150 dpi (grey paper, grain and lines of dark "words"), so it renders like her scanned papers.
# "anything" = the page's .pdfLayer shows a picture (a canvas, or a decoded <img>); "sharp" = a canvas at the resolution
# pdfview.js aims for (zoom x devicePixelRatio, under 12 Mpx, within its 1.2 slack). Times are ms, polled once a frame.
#      python tests/measure_pdf.py --cpu 4   (the same with Chrome's CPU slowed 4 times, nearer a tablet than a laptop)
import sys, time, pathlib, re, io, random, statistics, subprocess, tempfile
import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8793
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SMALL = ROOT / "tests" / "fixtures" / "u4a.pdf"
SCAN = ROOT / "tests" / "fixtures" / "scan20.pdf"

def make_scan(path, pages=20):
    rnd = random.Random(20261027)
    doc = fitz.open()
    for k in range(pages):
        im = Image.new("L", (1600, 2200), 232)
        d = ImageDraw.Draw(im)
        d.rectangle([150, 90, 1450, 150], fill=40)                       # a heading bar
        y = 220
        while y < 2080:
            x = 150 + (60 if rnd.random() < 0.15 else 0)
            while x < 1420:
                wl = rnd.randint(24, 150)
                d.rectangle([x, y, min(1450, x + wl), y + 20], fill=rnd.randint(25, 80))
                x += wl + rnd.randint(14, 28)
            y += rnd.randint(46, 72)
        d.rectangle([480, 550, 640, 600], fill=10)                       # the dark mark at 30 % across, 25 % down
        grain = Image.effect_noise((1600, 2200), 48)
        im = Image.blend(im, grain, 0.08).convert("RGB")
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=65, dpi=(150, 150))
        pg = doc.new_page(width=1600 * 72 / 150, height=2200 * 72 / 150)
        pg.insert_image(pg.rect, stream=buf.getvalue())
    doc.save(str(path)); doc.close()
if not SCAN.exists(): make_scan(SCAN)
if not SMALL.exists(): sys.exit("tests/fixtures/u4a.pdf is missing: run tests/test_u4a.py once")

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-27T10:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Scans', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [], pages: [] }));
}"""
# a watcher on sheet i (1-based): ms from now to the layer showing anything, and to it being sharp
WATCH_JS = """(i) => {
  const m = { i, t0: performance.now(), any: null, sharp: null, had: null, done: false }; window.__m = m;
  const mine = (s) => { const S = window.__pw.S, p = S.pages.find((x) => x.id === s.dataset.id);   // a sheet of the note now open
    return p && S.openNote && p.note_id === S.openNote && !document.getElementById('noteView').hidden; };
  const tick = () => {
    const s = document.querySelector(`#stack .sheet[data-index="${i}"]`), L = s && mine(s) && s.querySelector(':scope > .pdfLayer');
    const now = performance.now() - m.t0;
    if (L) {
      const cs = [...L.querySelectorAll('canvas')].filter((c) => c.width > 0), im = L.querySelector('img');
      const vis = cs.length > 0 || !!(im && im.complete && im.naturalWidth > 0);
      if (m.had === null) m.had = vis;
      if (vis && m.any === null) m.any = now;
      const z = +document.getElementById('stack').dataset.zoom, w = parseFloat(s.style.width), h = parseFloat(s.style.height);
      const t = Math.max(0.2, Math.min(z * devicePixelRatio, Math.sqrt(12e6 / (w * h))));
      if (m.sharp === null && cs.some((c) => c.width >= w * t / 1.2)) m.sharp = now;
    }
    if (m.sharp === null && now < 20000) requestAnimationFrame(tick); else m.done = true;
  };
  tick(); return 1; }"""
# one wheel gesture over n frames that moves the stack down by `pages` pages (or up, negative): lands on sheet `to`
WHEEL_JS = """async ([to, frames]) => {
  const desk = document.getElementById('desk'), r = desk.getBoundingClientRect();
  const sh = document.querySelector(`#stack .sheet[data-index="${to}"]`).getBoundingClientRect();
  const dy = sh.top - (r.top + 24), step = dy / frames;
  for (let k = 0; k < frames; k++) {
    desk.dispatchEvent(new WheelEvent('wheel', { deltaY: step, clientX: r.left + 300, clientY: r.top + 300, bubbles: true, cancelable: true }));
    await new Promise((ok) => requestAnimationFrame(ok));
  }
  return 1; }"""

# a long wheel scroll to sheet `to` over n frames, then `after` ms still: of every frame's on-screen PDF pages, how many
# showed no picture at all (white paper)
BLANK_JS = """async ([to, frames, after]) => {
  const desk = document.getElementById('desk'), r = desk.getBoundingClientRect();
  const sh = document.querySelector(`#stack .sheet[data-index="${to}"]`).getBoundingClientRect();
  const step = (sh.top - (r.top + 24)) / frames;
  let seen = 0, blank = 0, landBlank = 0, landSeen = 0;
  const look = (landing) => {
    for (const s of document.querySelectorAll('#stack .sheet[data-pdf]')) {
      const b = s.getBoundingClientRect(); if (b.bottom <= r.top || b.top >= r.bottom) continue;
      const L = s.querySelector(':scope > .pdfLayer'), im = L && L.querySelector('img');
      const vis = !!L && ([...L.querySelectorAll('canvas')].some((c) => c.width > 0) || !!(im && im.complete && im.naturalWidth > 0));
      if (landing) { landSeen++; if (!vis) landBlank++; } else { seen++; if (!vis) blank++; }
    }
  };
  let last = performance.now(), gap = 0;
  for (let k = 0; k < frames; k++) {
    desk.dispatchEvent(new WheelEvent('wheel', { deltaY: step, clientX: r.left + 300, clientY: r.top + 300, bubbles: true, cancelable: true }));
    await new Promise((ok) => requestAnimationFrame(ok)); look(false);
    const t = performance.now(); if (k > 1) gap = Math.max(gap, t - last); last = t;
  }
  const t0 = performance.now();
  while (performance.now() - t0 < after) { await new Promise((ok) => requestAnimationFrame(ok)); look(true); }
  return { seen, blank, landSeen, landBlank, gap }; }"""
# what one PDF page costs to render, straight through pdf.js (no app code): a thumb, a half and a full sharp render, and a
# thumb then a full render on one page object (the JPEG decoded once)
COST_JS = """async ([path, n, W, H]) => {
  const m = await import('./js/pdfin.js'), lib = await m.loadLib(), blob = await m.bytesOf(path);
  const t0 = performance.now();
  const doc = await lib.getDocument({ data: new Uint8Array(await blob.arrayBuffer()), isEvalSupported: false }).promise;
  const open = performance.now() - t0, out = { open };
  const one = async (pg, w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h;
    const v1 = pg.getViewport({ scale: 1 }); await pg.render({ canvasContext: c.getContext('2d', { alpha: false }), viewport: pg.getViewport({ scale: w / v1.width }) }).promise;
    c.width = 0; c.height = 0; };
  const time = async (label, fn) => { const t = performance.now(); await fn(); out[label] = performance.now() - t; };
  const tw = 240, th = Math.round(240 * H / W);
  await time('thumb', async () => { const pg = await doc.getPage(n); await one(pg, tw, th); pg.cleanup(); });
  await time('half', async () => { const pg = await doc.getPage(n + 1); await one(pg, Math.round(W / 2), Math.round(H / 2)); pg.cleanup(); });
  await time('full', async () => { const pg = await doc.getPage(n + 2); await one(pg, W, H); pg.cleanup(); });
  await time('thumbThenFull', async () => { const pg = await doc.getPage(n + 3); await one(pg, tw, th); await one(pg, W, H); pg.cleanup(); });
  await doc.destroy();
  return out; }"""
CPU = float(sys.argv[sys.argv.index("--cpu") + 1]) if "--cpu" in sys.argv else 1

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def stats(pg): return pg.evaluate("window.__pw.pdf.stats()")
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def watch(pg, i): pg.evaluate(WATCH_JS, i)
def result(pg, ms=20000):
    pg.wait_for_function("window.__m && window.__m.done", timeout=ms + 2000)
    m = pg.evaluate("window.__m")
    return m
def wheel_to(pg, to, frames=12):
    pg.evaluate(WHEEL_JS, [to, frames])
def import_pdf(pg, path):
    frow(pg, "Scans").click(); pg.wait_for_timeout(80)
    before = pg.evaluate("window.__pw.S.notes.length")
    watch(pg, 1)
    with pg.expect_file_chooser() as fc:
        pg.click("#openPdf")
    fc.value.set_files(str(path))
    pg.wait_for_function(f"window.__pw.S.notes.length > {before}", timeout=30000)
    m = result(pg)
    return pg.evaluate("window.__pw.S.openNote"), m

rows = []
def row(name, m, extra=""):
    rows.append((name, m.get("any"), m.get("sharp"), extra))
    print(f"  {name:<58} anything {fmt(m.get('any')):>7}  sharp {fmt(m.get('sharp')):>7}  {extra}")
def fmt(v): return "-" if v is None else f"{v:.0f}"

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(150)
        if CPU > 1: ctx.new_cdp_session(pg).send("Emulation.setCPUThrottlingRate", {"rate": CPU})
        print(f"scan20.pdf: {SCAN.stat().st_size / 1048576:.2f} MB, devicePixelRatio {pg.evaluate('devicePixelRatio')}, CPU slowed x{CPU:g}")

        # ---------------------------------------------------------------- the small vector PDF (the test fixture)
        nid_s, m = import_pdf(pg, SMALL)
        row("u4a.pdf: import -> page 1 (doc kept from the import)", m)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")

        # ---------------------------------------------------------------- the 20-page scan
        nid, m = import_pdf(pg, SCAN)
        row("scan20: import -> page 1 (doc kept from the import)", m)
        z = float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
        sz = pg.evaluate("(() => { const s = document.querySelector('#stack .sheet'); return [parseFloat(s.style.width), parseFloat(s.style.height)]; })()")
        pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(1500)
        path = pg.evaluate("(id) => window.__pw.S.pages.find(p => p.note_id === id).pdf_path", nid)
        s0 = stats(pg)

        # read through: one page at a time, 1.2 s on each (she reads)
        for k in range(2, 6):
            wheel_to(pg, k); watch(pg, k); m = result(pg)
            row(f"read: flick to page {k}, after 1.2 s on page {k - 1}", m, "had a picture at landing" if m["had"] else "blank at landing")
            pg.wait_for_timeout(1200)
        # a quick read: 400 ms on each page
        for k in range(6, 10):
            wheel_to(pg, k); watch(pg, k); pg.wait_for_timeout(400)
            m = pg.evaluate("window.__m")
            row(f"quick: flick to page {k}, after 0.4 s on page {k - 1} (at 400 ms)", m, "had a picture at landing" if m["had"] else "blank at landing")
        m = result(pg); pg.wait_for_timeout(1500)
        # a fast flick of three pages
        wheel_to(pg, 12, 15); watch(pg, 12); m = result(pg)
        row("fast flick 9 -> 12 (three pages)", m, "had a picture at landing" if m["had"] else "blank at landing")
        pg.wait_for_timeout(1500)
        # three pages back and on again: what was seen a moment ago
        r0 = stats(pg)["renders"]
        wheel_to(pg, 9, 15); watch(pg, 9); m = result(pg)
        row("back 12 -> 9 (seen 2 s ago)", m, "had a picture at landing" if m["had"] else "blank at landing")
        pg.wait_for_timeout(1500)
        wheel_to(pg, 12, 15); watch(pg, 12); m = result(pg)
        row("on again 9 -> 12 (seen 2 s ago)", m, "had a picture at landing" if m["had"] else "blank at landing")
        pg.wait_for_timeout(1500)
        back_renders = stats(pg)["renders"] - r0
        # a jump through the page list's code path (scrollToPage)
        pg.evaluate("import('./js/page.js').then((m) => m.scrollToPage(18))"); watch(pg, 19); m = result(pg)
        row("jump 12 -> 19 (scrollToPage, the page list's tap)", m, "had a picture at landing" if m["had"] else "blank at landing")
        pg.wait_for_timeout(1500)
        # a long scroll back up, six pages in 40 frames, then 0.6 s still
        bl = pg.evaluate(BLANK_JS, [13, 40, 600])
        blank_line = (f"scroll 19 -> 13 in 40 frames: {bl['blank']} of {bl['seen']} on-screen page-frames white while moving, "
                      f"{bl['landBlank']} of {bl['landSeen']} in the 0.6 s after; longest frame while moving {bl['gap']:.0f} ms")
        print("  " + blank_line)
        pg.wait_for_timeout(1500)
        s1 = stats(pg)

        # ---------------------------------------------------------------- what a render costs, and the cold open
        cost = pg.evaluate(COST_JS, [path, 3, round(sz[0] * z * 2), round(sz[1] * z * 2)])
        cost_line = (f"pdf.js alone on scan20: getDocument {cost['open']:.0f} ms, a thumb {cost['thumb']:.0f}, a half render {cost['half']:.0f}, "
                     f"a sharp render {cost['full']:.0f}, a thumb then a sharp on one page object {cost['thumbThenFull']:.0f}")
        print("  " + cost_line)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
        pg.reload(); ready(pg); pg.wait_for_timeout(200)
        frow(pg, "Scans").click()
        card = pg.locator(f"#grid .card[data-id='{nid}']"); card.wait_for()
        watch(pg, 1); card.click()
        m = result(pg)
        row("cold open: fresh app, tap the folder then the note at once", m)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
        pg.reload(); ready(pg); pg.wait_for_timeout(200)
        frow(pg, "Scans").click()
        card = pg.locator(f"#grid .card[data-id='{nid}']"); card.wait_for(); pg.wait_for_timeout(1500)
        watch(pg, 1); card.click()
        m = result(pg)
        row("warm open: fresh app, the folder open 1.5 s first", m)

        print()
        print(f"zoom {z}, page {sz[0]:.0f} x {sz[1]:.0f} css px; a sharp canvas = {sz[0] * z * 2:.0f} x {sz[1] * z * 2:.0f} = {sz[0] * sz[1] * z * z * 4 / 1e6:.2f} Mpx")
        print(f"scan20 session (import to the long scroll): renders {s1['renders'] - s0['renders']}, freed {s1['freed'] - s0['freed']}, "
              f"peak canvases {s1['peak']}, live now {s1['canvases']} ({s1['pixels'] / 1e6:.1f} Mpx), re-renders for back-and-on {back_renders}")
        for k_ in ("placeholders", "ahead", "budget"):
            if k_ in s1: print(f"  {k_}: {s1[k_]}")
        print(f"page errors: {errs or 'none'}")
        b.close()
finally:
    srv.terminate()
