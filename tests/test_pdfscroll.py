# PenWorks PDF-note scroll checks (pw-v7n, round 4): one-finger scrolling through a note made from a PDF stops fighting her.
# Run: python tests/test_pdfscroll.py             (local mode only: ?local=1, Supabase is never touched)
#      python tests/test_pdfscroll.py --cpu 1     (Chrome's CPU at full speed; the default is slowed 4 times, nearer her tablet)
#      python tests/test_pdfscroll.py --soft      (headless Chrome's software GPU instead of the laptop's: see below)
#      python tests/test_pdfscroll.py --measure   (the measurement only, nothing checked)
#      python tests/test_pdfscroll.py --trace     (also a Chrome trace of each pan: the main thread's tasks over 30 ms)
#      python tests/test_pdfscroll.py --after     (skips the BEFORE run)
# THE MEASUREMENT, twice: BEFORE = js/pdfview.js and js/page.js as they were at pw-v7m (commit 5d9e61b, served from git in
# place of the files on disk), AFTER = the files on disk. Two notes, both opened through the + card: tests/fixtures/scan20.pdf
# (20 scanned pages, made by tests/measure_pdf.py) and a 130-page typeset PDF made here with PyMuPDF (a heading, text, a
# table and a few lines a page); a plain ink note of 20 grid pages is the control (she says those scroll fine). A one-finger
# pan (CDP touch: swipes of 20 moves over 0.5 s, each lifted into its glide, so 60 moves every 1.5 s) runs from page 1 to
# page 15, the zoom unlocked, while the page records every requestAnimationFrame gap, the long tasks, every pdf.js render
# (PDFPageProxy.render wrapped: thumb or sharp, and whether the stack was moving when it started), every pdf.js slice (its
# requestAnimationFrame callbacks) and every canvas drawImage / putImageData over 3 ms. A frame over 32 ms "has pdf work"
# when a pdf.js slice or a heavy canvas call ran in it (a render merely under way is counted apart: since pw-v7n a render
# waits, held, between its slices while the stack moves). Each note: the first pan right after it opens,
# a second pan (thumbs made), and a pan after a reload (a restart).
# The GPU: headless Chrome draws with a software GPU (SwiftShader) unless told otherwise, and there every canvas on screen
# costs a copy on each frame (20 to 45 ms at CPU x4, measured 29 Oct), PDF work or not, which her tablet's GPU never does.
# So this runs on the laptop's GPU (ANGLE on D3D11) by default; --soft shows the software numbers.
# Then the checks on AFTER: no pdf work in any frame over 32 ms; no pdf.js render starts while the stack moves; the thumbs
# kept on the device (IndexedDB, js/pdfin.js): all pages filled, read back as JPEGs, the cap, 0 thumb renders after a
# reload; the background fill waits while the stack moves and while the app is hidden.
import sys, subprocess, time, pathlib, re, json, tempfile
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8797
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SCAN = ROOT / "tests" / "fixtures" / "scan20.pdf"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="pw-pdfscroll-"))
BOOK = TMP / "book130.pdf"
FORTY = TMP / "fill40.pdf"
FORTY_B = TMP / "hidden40.pdf"
BEFORE_REV = "5d9e61b"                   # pw-v7m, the build before this round
CPU = float(sys.argv[sys.argv.index("--cpu") + 1]) if "--cpu" in sys.argv else 4
SOFT = "--soft" in sys.argv
MEASURE = "--measure" in sys.argv
TRACE = "--trace" in sys.argv
AFTER_ONLY = "--after" in sys.argv       # skip the BEFORE run (quicker while working; the side by side then shows AFTER twice)
QUIET = 180                              # js/pdfview.js: ms of a still stack before anything from pdf.js runs
if not SCAN.exists(): sys.exit("tests/fixtures/scan20.pdf is missing: run tests/measure_pdf.py once")

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

def make_book(path, pages=130):
    words = ("die funksie het n draaipunt waar die gradient nul is en die grafiek verander van rigting so ons "
             "bereken eers die afgeleide en stel dit gelyk aan nul dan los ons op vir x en vervang terug").split()
    doc = fitz.open()
    for k in range(pages):
        pg = doc.new_page(width=595.28, height=841.89)
        pg.insert_text((56, 70), f"Hoofstuk {k // 10 + 1}.{k % 10 + 1}  Calculus and its uses", fontsize=16, fontname="hebo")
        txt = " ".join(words[(k + j) % len(words)] for j in range(260))
        pg.insert_textbox(fitz.Rect(56, 90, 540, 330), txt, fontsize=10.5, fontname="helv")
        x0, y0, cw, rh = 56, 350, 121, 22
        for r in range(7):
            for c in range(4):
                pg.draw_rect(fitz.Rect(x0 + c * cw, y0 + r * rh, x0 + (c + 1) * cw, y0 + (r + 1) * rh), color=(0, 0, 0), width=0.6)
                pg.insert_text((x0 + c * cw + 6, y0 + r * rh + 15), f"x = {r * 4 + c - 3}" if r else ["x", "f(x)", "f'(x)", "f''(x)"][c],
                               fontsize=9.5, fontname="helv")
        for j in range(6):
            pg.draw_line((56, 540 + j * 34), (540, 540 + j * 34), color=(0.4, 0.4, 0.4), width=0.5)
        pg.insert_textbox(fitz.Rect(56, 760, 540, 820), " ".join(words[::-1]), fontsize=9, fontname="tiro")
    doc.save(str(path)); doc.close()
def make_plain(path, pages, tag):
    doc = fitz.open()
    for k in range(pages):
        pg = doc.new_page(width=595.28, height=841.89)
        pg.insert_text((60, 80), f"{tag} page {k + 1}", fontsize=20, fontname="helv")
        pg.draw_rect(fitz.Rect(0.2 * 595, 0.2 * 842, 0.4 * 595, 0.3 * 842), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(str(path)); doc.close()
make_book(BOOK); make_plain(FORTY, 40, "Fill"); make_plain(FORTY_B, 40, "Hidden")
OLD = {f: subprocess.run(["git", "show", f"{BEFORE_REV}:js/{f}"], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8").stdout
       for f in ("pdfview.js", "page.js")}

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-29T10:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Scans', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n0', folder_id: 'f1', name: 'Plain', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: Array.from({ length: 20 }, (_, k) => ({ id: 'q' + k, note_id: 'n0', position: k, orientation: 'portrait', background: 'grid',
      deleted_at: null, created_at: t, updated_at: t })) }));
}"""
# the recorder (window.__P): pdf.js renders (and whether the stack moved when each started), pdf.js slices, heavy canvas
# calls, long tasks and every frame gap
INSTR_JS = """async (path) => {
  const P = window.__P = window.__P || { renders: [], slices: [], ops: [], long: [], frames: [], rec: false };
  const pm = await import('./js/page.js'), since = () => pm.sinceMove();
  const m = await import('./js/pdfin.js'), d = path && await m.docOf(path), pg = d && await d.getPage(1), proto = pg && Object.getPrototypeOf(pg);
  if (pg) pg.cleanup();
  if (proto && !proto.__pwWrapped) {
    proto.__pwWrapped = true;
    const orig = proto.render;
    proto.render = function (params) {
      const c = params.canvasContext.canvas;
      const st = new Error().stack || '', who = (/at (?:async )?(?:Module.)?(draw|paint|makeThumb) /.exec(st) || [])[1] || st.split('\\n').slice(2, 5).map(l => l.trim()).join(' | ');
      const r = { kind: c.width === 240 ? 'thumb' : 'sharp', page: this.pageNumber, t0: performance.now(), t1: null, mv: since(), w: c.width, who };
      window.__P.renders.push(r);
      const task = orig.call(this, params);
      task.promise.then(() => { r.t1 = performance.now(); }, () => { r.t1 = performance.now(); r.cancelled = true; });
      return task;
    };
  }
  if (!window.__pwOps) {
    window.__pwOps = true;
    const C = CanvasRenderingContext2D.prototype;
    for (const name of ['drawImage', 'putImageData']) {
      const o = C[name];
      C[name] = function (...a) { const t = performance.now(); const v = o.apply(this, a); const dt = performance.now() - t;
        if (dt > 3) window.__P.ops.push({ op: name, t0: t, dt, w: this.canvas.width }); return v; };
    }
    const raf = window.requestAnimationFrame.bind(window);      // a pdf.js slice is a frame callback scheduled from pdf.min.mjs
    window.requestAnimationFrame = (cb) => {
      if (!/pdf\\.min\\.mjs/.test(new Error().stack || '')) return raf(cb);
      return raf((t) => { const t0 = performance.now(), mv = since(); try { return cb(t); }
        finally { window.__P.slices.push({ t0, dt: performance.now() - t0, mv }); } });
    };
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__P.long.push([e.startTime, e.duration]); }).observe({ type: 'longtask' });
    let last = 0;
    const loop = (t) => { if (window.__P.rec && last) window.__P.frames.push([last, t]); last = t; raf(loop); };
    raf(loop);
  }
  return 1; }"""
REC_ON = "() => { const P = window.__P; P.renders = []; P.slices = []; P.ops = []; P.long = []; P.frames = []; P.rec = true; P.t0 = performance.now(); }"
REC_OFF = """async () => { const P = window.__P; P.rec = false; P.t1 = performance.now();
  P.still = P.t1 - (await import('./js/page.js')).sinceMove(); return JSON.parse(JSON.stringify(P)); }"""
CUR = "() => +document.getElementById('counter').textContent.split('/')[0]"
STORE_JS = """async () => { const m = await import('./js/pdfin.js'); return { count: await m.thumbCount(), keys: [...await m.thumbKeys()] }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def stats(pg): return pg.evaluate("window.__pw.pdf.stats()")
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def touch(cdp, kind, x=None, y=None):
    cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}]})
def until(pg, fn, ms=8000, step=100):
    t0 = time.time()
    while time.time() - t0 < ms / 1000:
        v = fn()
        if v: return v
        pg.wait_for_timeout(step)
    return fn()

def pan(pg, cdp, to=15, limit=40):
    """swipes of 20 moves (35 px each, 25 ms apart) lifted into their glide, until page `to` is current; then until still"""
    n = 0
    while pg.evaluate(CUR) < to and n < limit:
        n += 1
        touch(cdp, "touchStart", 640, 720)
        for k in range(1, 21):
            time.sleep(0.025); touch(cdp, "touchMove", 640, 720 - 35 * k)
        touch(cdp, "touchEnd"); time.sleep(0.2)
    t0, last, still = time.time(), None, 0                              # let the glide end (the stack still for 250 ms)
    while time.time() - t0 < 6 and still < 250:
        y = pg.evaluate("document.getElementById('stack').style.transform"); still = still + 50 if y == last else 0; last = y
        pg.wait_for_timeout(50)
    return n

WRAPPERS = {"ProxyMain::BeginMainFrame", "WebFrameWidgetImpl::BeginMainFrame", "Blink.Animate.UpdateTime", "PageAnimator::serviceScriptedAnimations",
            "FrameRequestCallbackCollection::ExecuteFrameCallbacks", "v8.callFunction", "EventDispatch", "ThreadControllerImpl::RunTask",
            "WebFrameWidgetImpl::UpdateLifecycle", "LayerTreeHost::DoUpdateLayers", "Commit"}
def trace_top(raw):
    ev = json.loads(raw)
    ev = ev["traceEvents"] if isinstance(ev, dict) else ev
    main = {(e["pid"], e["tid"]) for e in ev if e.get("name") == "thread_name" and e.get("args", {}).get("name") == "CrRendererMain"}
    xs = [e for e in ev if e.get("ph") == "X" and (e["pid"], e["tid"]) in main and "dur" in e]
    lines = []
    for t in sorted([e for e in xs if e["name"] == "RunTask" and e["dur"] > 30000], key=lambda e: -e["dur"])[:12]:
        inside = {}
        for e in xs:
            if e is not t and e["ts"] >= t["ts"] and e["ts"] + e["dur"] <= t["ts"] + t["dur"] and e["dur"] > 4000 and e["name"] not in WRAPPERS:
                d = e.get("args", {}).get("data", {}) or {}
                k = e["name"] + ((" " + (d.get("url") or "").split("/")[-1]) if d.get("url") else "")
                inside[k] = max(inside.get(k, 0), e["dur"] / 1000)
        lines.append(f"      task {t['dur'] / 1000:.0f} ms: " + ", ".join(f"{k} {v:.0f}" for k, v in sorted(inside.items(), key=lambda kv: -kv[1])[:5]))
    return lines

def summary(P, s0, s1, swipes):
    """the frames while the stack moved: over 32 ms, the longest, and which had pdf work in them"""
    end, still = P["t1"], P["still"]
    gaps = [(b - a, a, b) for a, b in P["frames"] if a >= P["t0"] and a < still]
    long = [g for g in gaps if g[0] > 32]
    pdf_long, flight = [], 0
    for g, a, b in long:
        if [s for s in P["slices"] if s["t0"] < b and s["t0"] + s["dt"] > a] or [o for o in P["ops"] if o["t0"] < b and o["t0"] + o["dt"] > a]:
            pdf_long.append(g)
        if [r for r in P["renders"] if r["t0"] < b and (r["t1"] or end) > a]: flight += 1
    started = {}
    for r in P["renders"]:
        if r["mv"] < QUIET: started[r["kind"] + " (" + r["who"] + ")"] = started.get(r["kind"] + " (" + r["who"] + ")", 0) + 1
    mv_slices = [s for s in P["slices"] if s["mv"] < QUIET and s["t0"] < still]
    return {
        "swipes": swipes, "frames": len(gaps), "over32": len(long), "longest": max([g[0] for g in gaps], default=0),
        "over32_pdf": len(pdf_long), "longest_pdf": max(pdf_long, default=0), "over32_in_flight": flight,
        "started_moving": started, "slices_moving": len(mv_slices), "slices_moving_ms": sum(s["dt"] for s in mv_slices),
        "thumb_renders_all": len([r for r in P["renders"] if r["kind"] == "thumb"]),
        "longest_task": max([d for t, d in P["long"] if t < still], default=0),
        "from_store": s1.get("fromStore", 0) - s0.get("fromStore", 0),
    }

def line(label, m):
    return (f"  {label:<28} over 32 ms {m['over32']:>3} (pdf work in {m['over32_pdf']:>3}) | longest {m['longest']:>4.0f} ms "
            f"(pdf {m['longest_pdf']:>4.0f}) | pdf.js renders started moving {sum(m['started_moving'].values()):>2} {m['started_moving'] or ''} | "
            f"slices moving {m['slices_moving']:>3} ({m['slices_moving_ms']:.0f} ms) | thumb renders {m['thumb_renders_all']:>2} | "
            f"from the device {m['from_store']:>2} | a render under way (maybe held) in {m['over32_in_flight']} of them | longest task {m['longest_task']:.0f} ms | {m['frames']} frames")

def import_pdf(pg, path):
    """opens the PDF through the + card; returns as soon as the note is on screen (the first pan starts at once)"""
    frow(pg, "Scans").click(); pg.wait_for_timeout(80)
    before = pg.evaluate("window.__pw.S.notes.length")
    with pg.expect_file_chooser() as fc:
        pg.click("#openPdf")
    fc.value.set_files(str(path))
    pg.wait_for_function(f"window.__pw.S.notes.length > {before}", timeout=60000)
    pg.wait_for_selector("#noteView:not([hidden])")
    pg.wait_for_function("document.querySelector('#stack .sheet[data-index=\"1\"] > .pdfLayer > canvas')", timeout=20000)
    nid = pg.evaluate("window.__pw.S.openNote")
    return nid, pg.evaluate("(id) => window.__pw.S.pages.find(p => p.note_id === id).pdf_path", nid)

def open_card(pg, nid):
    frow(pg, "Scans").click()
    card = pg.locator(f"#grid .card[data-id='{nid}']"); card.wait_for(); card.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(1500)
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def fill_done(pg, ms=60000):
    return until(pg, lambda: stats(pg).get("fillLeft") == 0 and not stats(pg).get("filling"), ms, 250)

def measure(pg, cdp, label, path):
    pg.evaluate(INSTR_JS, path)
    s0 = stats(pg)
    if TRACE: pg.context.browser.start_tracing(page=pg, categories=["devtools.timeline", "disabled-by-default-devtools.timeline", "v8.execute", "blink", "cc"])
    pg.evaluate(REC_ON)
    n = pan(pg, cdp)
    P = pg.evaluate(REC_OFF); s1 = stats(pg)
    if TRACE: print("\n".join(trace_top(pg.context.browser.stop_tracing())), flush=True)
    m = summary(P, s0, s1, n); m["page"] = pg.evaluate(CUR)
    print(line(label, m), flush=True)
    return m

def session(b, before):
    """one browser context; before: pdfview.js and page.js as they were at pw-v7m"""
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2, has_touch=True, service_workers="block")
    if before:
        def serve(body): return lambda route, request: route.fulfill(status=200, body=body, content_type="text/javascript")
        for f, body in OLD.items():
            ctx.route(re.compile(r".*/js/" + re.escape(f) + r"(\?.*)?$"), serve(body))
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg)
    pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(150)
    cdp = ctx.new_cdp_session(pg)
    if CPU > 1: cdp.send("Emulation.setCPUThrottlingRate", {"rate": CPU})
    return ctx, pg, cdp, errs

def run_measure(b, before):
    tag = "BEFORE (pw-v7m)" if before else "AFTER (pw-v7n)"
    print(f"{tag}:", flush=True)
    ctx, pg, cdp, errs = session(b, before)
    out, notes = {}, {}
    open_card(pg, "n0")
    out["plain"] = measure(pg, cdp, "plain ink note (control)", None)
    back(pg)
    for name, path in (("scan20", SCAN), ("book130", BOOK)):
        nid, pp = import_pdf(pg, path); notes[name] = (nid, pp)
        out[name + " first"] = measure(pg, cdp, f"{name} first pan", pp)
        pg.evaluate("import('./js/page.js').then((m) => m.scrollToPage(0))"); pg.wait_for_timeout(1500)
        out[name + " second"] = measure(pg, cdp, f"{name} second pan", pp)
        if not before: out[name + " filled"] = bool(fill_done(pg))
        back(pg)
    for name in ("scan20", "book130"):
        nid, pp = notes[name]
        pg.reload(); ready(pg); pg.wait_for_timeout(200)
        open_card(pg, nid)
        out[name + " reload"] = measure(pg, cdp, f"{name} after a reload", pp)
        back(pg)
    return ctx, pg, cdp, errs, out, notes

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=[] if SOFT else ["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        print(f"CPU slowed x{CPU:g}, {'software GPU' if SOFT else 'laptop GPU'}, devicePixelRatio 2, scan20 {SCAN.stat().st_size / 1048576:.1f} MB, "
              f"book130 {BOOK.stat().st_size / 1048576:.1f} MB; a pan = page 1 to 15, swipes of 20 moves in 0.5 s", flush=True)

        # ---------------------------------------------------------------- the measurement, before and after
        eb, before = [], None
        if not AFTER_ONLY:
            cb, _, _, eb, before, _ = run_measure(b, True)
            cb.close()
        ctx, pg, cdp, errs, after, notes = run_measure(b, False)
        print("\nside by side (frames over 32 ms with pdf work in them / longest frame ms / pdf.js renders started while moving):")
        for k in ("plain", "scan20 first", "scan20 second", "scan20 reload", "book130 first", "book130 second", "book130 reload"):
            x, y = before[k] if before else after[k], after[k]
            print(f"  {k:<16} before {x['over32_pdf']:>3} / {x['longest']:>4.0f} / {sum(x['started_moving'].values()):>2}"
                  f"    after {y['over32_pdf']:>3} / {y['longest']:>4.0f} / {sum(y['started_moving'].values()):>2}", flush=True)

        if not MEASURE:
            # ------------------------------------------------------------ the pans, after
            group[0] = "the pans (pw-v7n)"
            for k in ("scan20 first", "scan20 second", "scan20 reload", "book130 first", "book130 second", "book130 reload"):
                m = after[k]
                check(f"{k}: no frame over 32 ms has pdf work in it (longest frame {m['longest']:.0f} ms)", m["over32_pdf"] == 0, m)
                check(f"{k}: no pdf.js render starts while the stack moves", not m["started_moving"], m["started_moving"])
                check(f"{k}: at most one pdf.js slice runs while the stack moves (the frame she starts moving in)", m["slices_moving"] <= 1, m["slices_moving"])
            check("the plain ink note (control): no frame over 32 ms", after["plain"]["over32"] == 0, after["plain"])

            # ------------------------------------------------------------ the thumbs kept on the device
            group[0] = "thumbs kept on the device (pw-v7n)"
            for name in ("scan20", "book130"):
                m = after[name + " reload"]
                check(f"{name} after a reload: 0 pdf.js thumb renders (from IndexedDB instead: {m['from_store']})",
                      m["thumb_renders_all"] == 0 and m["from_store"] >= 10, m)
            st = pg.evaluate(STORE_JS)
            for name, n in (("scan20", 20), ("book130", 130)):
                pp = notes[name][1]
                have = [k for k in st["keys"] if k.startswith(pp + "#")]
                check(f"{name}: the background fill kept a thumb for every page ({n})", after[name + " filled"] and len(have) == n, [len(have), after[name + " filled"]])
            rb = pg.evaluate("""async (k) => { const m = await import('./js/pdfin.js'), blob = await m.thumbGet(k);
              if (!blob) return null; const bm = await createImageBitmap(blob), c = document.createElement('canvas');
              c.width = bm.width; c.height = bm.height; const g = c.getContext('2d'); g.drawImage(bm, 0, 0);
              const d = g.getImageData(Math.floor(0.35 * bm.width), Math.floor(0.262 * bm.height), 1, 1).data;
              return { type: blob.type, size: blob.size, w: bm.width, h: bm.height, mark: [d[0], d[1], d[2]] }; }""", notes["scan20"][1] + "#1")
            check("read back: scan20 page 1's thumb is a 240 px JPEG with the page's dark mark (35 % across, 26 % down)",
                  rb and rb["type"] == "image/jpeg" and rb["w"] == 240 and rb["size"] > 1000 and max(rb["mark"]) < 90, rb)
            cap = pg.evaluate("""async () => { const m = await import('./js/pdfin.js');
              const all = async () => { const dbs = await indexedDB.databases(), name = dbs.map(d => d.name).find(n => n.endsWith('.thumbs'));
                const db = await new Promise((ok, no) => { const r = indexedDB.open(name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
                const v = await new Promise((ok) => { const q = db.transaction('thumbs').objectStore('thumbs').getAll(); q.onsuccess = () => ok(q.result); });
                db.close(); return v.sort((a, b) => a.at - b.at).map(r => r.k); };
              const before = await all(), n = before.length;
              m.setThumbCap(n - 5);
              await m.thumbPut('test/new.pdf#1', new Blob([new Uint8Array(2000)], { type: 'image/jpeg' }));
              const after = await all();
              m.setThumbCap(0);
              return { n, after: after.length, newKept: after.includes('test/new.pdf#1'), oldestGone: before.slice(0, 6).every(k => !after.includes(k)),
                       nextKept: after.includes(before[6]) }; }""")
            check("the cap: past it the oldest made go (6 out for one in, the new one kept)",
                  cap["after"] == cap["n"] - 5 and cap["newKept"] and cap["oldestGone"] and cap["nextKept"], cap)

            # ------------------------------------------------------------ the background fill
            group[0] = "background fill (pw-v7n)"
            nid, pp = import_pdf(pg, FORTY)
            pg.evaluate(INSTR_JS, pp)
            s0 = stats(pg); pg.evaluate(REC_ON)
            pan(pg, cdp, to=12)
            P = pg.evaluate(REC_OFF); s1 = stats(pg)
            th = [r for r in P["renders"] if r["kind"] == "thumb"]
            check("a new 40-page note, panned at once: no thumb render starts while the stack moves", not [r for r in th if r["mv"] < QUIET], th[:5])
            check("... and no pdf.js slice runs while it moves (at most the frame she starts moving in)",
                  len([s for s in P["slices"] if s["mv"] < QUIET and s["t0"] < P["still"]]) <= 1, len(P["slices"]))
            pg.evaluate("window.__P.renders = []; window.__P.rec = false")
            check("then, still, the fill makes the rest: every page kept", fill_done(pg, 30000), stats(pg).get("fillLeft"))
            here = pg.evaluate(CUR)                                       # the desk's own asks (the pages near it) go first
            order = [r["page"] for r in pg.evaluate("window.__P.renders") if r["kind"] == "thumb" and abs(r["page"] - here) > 3]
            check("... lowest page first (the fill's thumb renders in page order, past the pages near the screen)", len(order) > 5 and order == sorted(order), order[:20])
            back(pg)
            # hidden: the fill waits; visible again: it goes on
            pg.evaluate("Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })")
            f0 = stats(pg)["filled"]
            nid_h, pp_h = import_pdf(pg, FORTY_B)
            pg.wait_for_timeout(2000)
            f1 = stats(pg)["filled"]
            check("the app hidden: the fill makes nothing (2 s still)", f1 == f0, [f0, f1])
            pg.evaluate("delete document.visibilityState")
            check("visible again: it goes on and keeps every page", fill_done(pg, 30000) and stats(pg)["filled"] >= f0 + 30, [f0, stats(pg)["filled"]])
            back(pg)
            check("no page errors (after)", not errs, errs)
            check("no page errors (before)", not eb, eb)
        b.close()
finally:
    srv.terminate()

if not MEASURE:
    print()
    cur = None
    for g, n, ok, info in res:
        if g != cur: print(f"[{g}]"); cur = g
        print(f"  {'PASS' if ok else 'FAIL'}  {n}" + ("" if ok else f"   -> {str(info)[:400]}"))
    fails = sum(1 for r in res if not r[2])
    print(f"\n{len(res) - fails}/{len(res)} passed")
    sys.exit(1 if fails else 0)
