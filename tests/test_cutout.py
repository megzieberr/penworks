# PenWorks Cut out checks (pw-v9e): tap a picture's background to take it away (_build/CUTOUT-BRIEF.md, the look
# _build/cutout/cutout-mock.png). No AI model, no service: a flood fill on the device.
# Run: python -E -P tests/test_cutout.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800, the way tests/test_u4c.py does. Every picture is made
# with Pillow in memory here (nothing is written to tests/fixtures/, no photos in the repo) and comes in through the + menu's
# Image input (#imgInput), the one way in. Pixels of the sheet's working picture are read through window.__pw.cutout.pixel,
# the kept PNGs by decoding the device copy, the PDF with PyMuPDF, the share image with Pillow.
# What it proves: the wand chip (Cut out, after Lock) for ONE unlocked picture only (not ink, not two records, not a locked
# picture, not ink on a sticky; a duplicated picture has it); the sheet (#cutout): the header word and hint, the picture on
# the checkerboard at its own pixel size, the bar's words, dark mode, the phone's three rows with Done on screen; a tap takes
# the connected background (a red ring's inside hole stays white), Everywhere takes the hole too; the feather leaves no
# near-white pixel at full alpha on a soft edge; the slider (0 keeps a 250 grey next to white, 30 takes it, live on the last
# tap without another tap); Undo, Reset, Cancel, Escape and Ctrl+Z in the sheet; pinch zoom and a tap under the zoom; Done:
# a NEW .png path, everything else on the record the same, the old file still on the device, one page undo step (Undo the old
# path, Redo the new), the thumb follows, the file uploads; Done with nothing removed changes nothing; a JPEG becomes a PNG
# with alpha; the PDF export, Share as images and the U3b page picture show the paper through the hole; the 10 MB cap's toast keeps the sheet open;
# a picture not on the device yet says so; a 2048 x 2048 tap under 300 ms. Screenshots go to _build/cutout/shots/.
import sys, subprocess, time, pathlib, math, base64, io, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from PIL import Image, ImageDraw, ImageFilter
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8828
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "cutout" / "shots"
W, H = 794, 1123
K = 595.28 / 794                       # PDF points per page px (A4 portrait)

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

# ------------------------------------------------------------ the pictures (Pillow, in memory)
def png(im): b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
def jpg(im): b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=92); return b.getvalue()
def ring_pic():                        # 400 x 300 white, a red ring (radius 120, band 60) round a white hole (radius 60)
    im = Image.new("RGB", (400, 300), (255, 255, 255)); d = ImageDraw.Draw(im)
    d.ellipse([80, 30, 320, 270], fill=(220, 30, 30)); d.ellipse([140, 90, 260, 210], fill=(255, 255, 255))
    return png(im)
def soft_pic():                        # 300 x 300 white, a blue disc blurred soft at its edge
    im = Image.new("RGB", (300, 300), (255, 255, 255)); ImageDraw.Draw(im).ellipse([70, 70, 230, 230], fill=(20, 40, 220))
    return png(im.filter(ImageFilter.GaussianBlur(4)))
def step_pic():                        # 300 x 200: the left half pure white, the right half (250, 250, 250), a black bar on the line
    im = Image.new("RGB", (300, 200), (255, 255, 255)); d = ImageDraw.Draw(im)
    d.rectangle([150, 0, 299, 199], fill=(250, 250, 250)); d.rectangle([140, 80, 160, 120], fill=(0, 0, 0))
    return png(im)
def cream_pic():                       # 400 x 300 cream (not the paper's white), a dark blue block in the middle
    im = Image.new("RGB", (400, 300), (255, 236, 150)); ImageDraw.Draw(im).rectangle([150, 100, 250, 200], fill=(20, 30, 120))
    return png(im)
def jpeg_pic():                        # 400 x 300 JPEG: white, a green square
    im = Image.new("RGB", (400, 300), (255, 255, 255)); ImageDraw.Draw(im).rectangle([120, 80, 280, 220], fill=(30, 150, 60))
    return jpg(im)
def big_pic():                         # 2048 x 2048 white with a few shapes: the worst case for the fill
    im = Image.new("RGB", (2048, 2048), (255, 255, 255)); d = ImageDraw.Draw(im)
    d.ellipse([400, 400, 1000, 1000], fill=(200, 40, 40)); d.rectangle([1200, 1300, 1800, 1700], fill=(30, 60, 200))
    d.line([0, 2047, 2047, 1500], fill=(10, 10, 10), width=9)
    return png(im)

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-07T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Pictures', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
INIT = """
  navigator.canShare = () => true;
  navigator.share = async (d) => { window.__shared = d; };
  window.__toastLog = [];
  addEventListener('DOMContentLoaded', () => { const t = document.getElementById('toast');
    if (t) new MutationObserver(() => window.__toastLog.push(t.textContent)).observe(t, { childList: true, characterData: true, subtree: true }); });
"""
HELP = """async () => {
  window.__P = await import('./js/page.js');
  window.__PI = await import('./js/pdfin.js');
  const T = window.__T = {};
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.client = (id, x, y) => { const r = T.sheet(id).getBoundingClientRect(), z = window.__P.view().z; return [r.left + x * z, r.top + y * z]; };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.imgs = (id) => T.recs(id).filter((r) => r.kind === 'image');
  T.chips = () => [...document.querySelectorAll('.selChips .chip')].map((c) => c.dataset.act);
  T.b64 = async (blob) => { const u = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
  // the device copy of a path, decoded: its type, size, the first bytes, and the RGBA at each point asked
  T.kept = async (path, pts) => { const b = await window.__PI.bytesOf(path); if (!b) return null;
    const head = [...new Uint8Array(await b.slice(0, 4).arrayBuffer())], bm = await createImageBitmap(b, { premultiplyAlpha: 'none' });
    const c = document.createElement('canvas'); c.width = bm.width; c.height = bm.height; const g = c.getContext('2d'); g.drawImage(bm, 0, 0);
    return { type: b.type, w: bm.width, h: bm.height, head, px: pts.map((p) => [...g.getImageData(p[0], p[1], 1, 1).data]) }; };
  // the client point of pixel (x, y) of the sheet's picture (its canvas box, the zoom included)
  T.cpt = (x, y) => { const c = document.querySelector('#cutout canvas'), r = c.getBoundingClientRect();
    return [r.left + (x + 0.5) / c.width * r.width, r.top + (y + 0.5) / c.height * r.height]; };
  T.fuss = (v) => { const i = document.getElementById('cutFuss'); i.value = String(v); i.dispatchEvent(new Event('input', { bubbles: true })); };
  T.ptr = (type, id, x, y) => document.querySelector('#cutout .cutStage').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch',
    isPrimary: id === 1, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0, buttons: type === 'pointerup' ? 0 : 1, clientX: x, clientY: y }));
  T.thumbHref = (idx, rid) => { const e = document.querySelector(`#plThumbs .thumbP[data-index='${idx}'] svg.thumbInk g.img > g[data-id="${rid}"] > image`); return e ? e.getAttribute('href') : null; };
  T.pageHref = (sid, rid) => { const g = T.sheet(sid).querySelector(`svg.ink > g.img > g[data-id="${rid}"]`); return g && g.firstElementChild ? g.firstElementChild.getAttribute('href') : null; };
  return 1;
}"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def imgs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.imgs(id)", pid)
def rec_of(pg, pid, rid):
    for r in pg.evaluate("(id) => window.__T.recs(id)", pid):
        if r["id"] == rid: return r
    return None
def chips(pg): return pg.evaluate("window.__T.chips()")
def select(pg, pid, ids): return pg.evaluate("([p, i]) => window.__pw.ink.selectRecs(p, i)", [pid, ids])
def clear_sel(pg): pg.evaluate("window.__pw.ink.clearSelection()")
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(80)
def redo(pg): pg.click("#redoBtn"); pg.wait_for_timeout(80)
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def toasts(pg): return [t for t in pg.evaluate("window.__toastLog") if t]
def until(pg, fn, ms=4000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def add_img(pg, data, name, mime, pid):
    n = len(imgs(pg, pid))
    pg.set_input_files("#imgInput", files=[{"name": name, "mimeType": mime, "buffer": data}])
    until(pg, lambda: len(imgs(pg, pid)) > n, 8000)
    pg.wait_for_timeout(80)
    got = imgs(pg, pid)
    return got[-1] if len(got) > n else None
def go_page(pg, idx): pg.evaluate("(i) => window.__P.scrollToPage(i)", idx); pg.wait_for_timeout(400)
def state(pg): return pg.evaluate("window.__pw.cutout.state()")
def px(pg, x, y): return pg.evaluate("([x, y]) => window.__pw.cutout.pixel(x, y)", [x, y])
def cut_open(pg):
    pg.click(".selChips .chip[data-act='cutout']")
    pg.wait_for_selector("#cutout .cutBoard:not([hidden])", timeout=8000); pg.wait_for_timeout(120)
def cut_tap(pg, x, y):
    cx, cy = pg.evaluate("([x, y]) => window.__T.cpt(x, y)", [x, y]); pg.mouse.click(cx, cy); pg.wait_for_timeout(60)
def fuss(pg, v): pg.evaluate("(v) => window.__T.fuss(v)", v); pg.wait_for_timeout(120)
def bar(pg, act): pg.click(f"#cutout [data-cut='{act}']"); pg.wait_for_timeout(80)
def is_open(pg): return pg.evaluate("!!document.getElementById('cutout')")
def shot(pg, name): pg.screenshot(path=str(SHOTS / name))
def is_paper(c): return min(c[:3]) > 185 and max(c[:3]) - min(c[:3]) < 40          # white, or the grid's light grey line
def is_cream(c): return c[0] > 235 and c[1] > 215 and c[2] < 175
def pdf_page(pg, sid):
    b64 = pg.evaluate("""async (sid) => { const m = await import('./js/pdfout.js');
      const blob = await m.buildPdf([{ id: sid, orientation: 'portrait', background: 'grid', pdf_path: null }], 'cutout');
      return window.__T.b64(blob); }""", sid)
    doc = fitz.open(stream=base64.b64decode(b64), filetype="pdf")
    pm = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    return Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
def on_page(d, x, y): return [d["x"] + (x + 0.5) * d["w"] / d["nw"], d["y"] + (y + 0.5) * d["h"] / d["nh"]]
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")      # the page's place in the note, 1-based
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(150)
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose"); pg.wait_for_timeout(60)
def d_white(c): return math.sqrt(sum((255 - v) ** 2 for v in c[:3]))

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
FILL = {}
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(INIT)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg); pg.evaluate(SEED); pg.reload(); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        open_note(pg); pg.evaluate(HELP)

        # ------------------------------------------------------------ A: the chip
        group[0] = "A. the chip"
        ring = add_img(pg, ring_pic(), "ring.png", "image/png", "s0") or {}
        RID, RPATH = ring.get("id"), ring.get("data", {}).get("path")
        check("set-up: the ring lands on page 1 as a picture, selected", RID and RPATH and (pg.evaluate("window.__pw.ink.selection()") or {}).get("ids") == [RID], ring)
        ch = chips(pg)
        check("one unlocked picture: Copy, Cut, Duplicate, Delete, Lock, then Cut out (the wand)", ch == ["copy", "cut", "duplicate", "delete", "lock", "cutout"], ch)
        lab = pg.evaluate("(() => { const c = document.querySelector(\".selChips .chip[data-act='cutout']\"); return c ? [c.getAttribute('aria-label'), c.title, !!c.querySelector('svg')] : null; })()")
        check("... its word is Cut out (aria-label and title), an icon", lab == ["Cut out", "Cut out", True], lab)
        pg.wait_for_timeout(100)
        bb = pg.locator(".selChips").bounding_box()
        pg.screenshot(path=str(SHOTS / "chips-cut-out.png"), clip={"x": max(0, bb["x"] - 120), "y": max(0, bb["y"] - 40), "width": bb["width"] + 240, "height": 360})
        ink = {"id": "ink-1", "page_id": "s0", "seq": 5, "kind": "pen", "style": {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1},
               "data": {"points": [[60, 60], [120, 70], [180, 64]]}}
        pg.evaluate("(r) => window.__pw.ink.put('s0', [r])", ink); pg.wait_for_timeout(60)
        select(pg, "s0", ["ink-1"]); ch = chips(pg)
        check("ink alone: no Cut out", "cutout" not in ch and ch[:4] == ["copy", "cut", "duplicate", "delete"], ch)
        select(pg, "s0", [RID, "ink-1"]); ch = chips(pg)
        check("the picture and a stroke (two records): no Cut out (Lock stays)", "cutout" not in ch and "lock" in ch, ch)
        select(pg, "s0", [RID]); pg.click(".selChips .chip[data-act='lock']"); pg.wait_for_timeout(80)
        ch = chips(pg)
        check("a locked picture: Delete and Unlock only, no Cut out", ch == ["delete", "lock"] and pg.evaluate("document.querySelector(\".selChips .chip[data-act='lock']\").getAttribute('aria-label')") == "Unlock", ch)
        pg.click(".selChips .chip[data-act='lock']"); pg.wait_for_timeout(80)
        check("unlocked again: Cut out is back", "cutout" in chips(pg) and not rec_of(pg, "s0", RID)["data"]["locked"], chips(pg))
        pg.click(".selChips .chip[data-act='duplicate']"); pg.wait_for_timeout(100)
        dup = pg.evaluate("window.__pw.ink.selection()") or {}
        check("a duplicated picture (a copy, same file) has Cut out too", len(dup.get("ids", [])) == 1 and dup["ids"][0] != RID and "cutout" in chips(pg), [dup, chips(pg)])
        pg.click(".selChips .chip[data-act='delete']"); pg.wait_for_timeout(80)
        pg.evaluate("window.__pw.sticky.add('yellow')"); pg.wait_for_timeout(200)
        sk = pg.evaluate("window.__pw.sticky.stickiesOf('s0').map((s) => s.id)")
        skr = {**ink, "id": "ink-sk", "page_id": sk[0] if sk else None, "data": {"points": [[30, 60], [90, 70]]}}
        if sk: pg.evaluate("([s, r]) => window.__pw.ink.put(s, [r])", [sk[0], skr]); pg.wait_for_timeout(60)
        ok_sk = bool(sk) and select(pg, sk[0], ["ink-sk"])
        check("ink on a sticky: selected, no Cut out", ok_sk and "cutout" not in chips(pg), [sk, chips(pg)])
        clear_sel(pg)

        # ------------------------------------------------------------ B: the sheet
        group[0] = "B. the sheet"
        select(pg, "s0", [RID]); cut_open(pg)
        st = state(pg)
        check("Cut out opens #cutout with the picture loaded at its own pixel size (400 x 300)", st["open"] and st["loaded"] and st["w"] == 400 and st["h"] == 300, st)
        look = pg.evaluate("""(() => { const v = document.getElementById('cutout'), b = v.querySelector('.cutBoard'), cs = getComputedStyle(b), r = b.getBoundingClientRect(),
            st = v.querySelector('.cutStage').getBoundingClientRect(), c = v.querySelector('canvas');
          return { head: v.querySelector('.cutHead b').textContent, hint: v.querySelector('.cutHead span').textContent, bg: cs.backgroundImage, bgc: cs.backgroundColor,
            size: cs.backgroundSize, aspect: r.width / r.height, inside: r.left >= st.left - 1 && r.right <= st.right + 1 && r.top >= st.top - 1 && r.bottom <= st.bottom + 1,
            cw: c.width, ch: c.height, words: [...v.querySelectorAll('.cutBar button, .cutBar label')].map((e) => e.textContent.trim()),
            full: (() => { const q = v.getBoundingClientRect(); return [q.width, q.height]; })(), role: v.querySelector('[role=dialog]') ? 1 : 0 }; })()""")
        check("the header word Cut out and the hint", look["head"] == "Cut out" and look["hint"] == "Tap the background to take it away", look)
        check("the board is a checkerboard: white, #DCDCDC squares, 24 px tiles (12 px squares)",
              "linear-gradient" in look["bg"] and "220, 220, 220" in look["bg"] and look["bgc"] == "rgb(255, 255, 255)" and look["size"].startswith("24px 24px"), [look["bg"][:120], look["bgc"], look["size"]])
        check("... fitted inside the stage, the picture's aspect kept (4:3)", look["inside"] and abs(look["aspect"] - 4 / 3) < 0.01, look)
        check("the bar: Undo, Reset, Fussiness, Everywhere, Cancel, Done", look["words"] == ["Undo", "Reset", "Fussiness", "Everywhere", "Cancel", "Done"], look["words"])
        check("full screen (1280 x 800), a dialog", look["full"] == [1280, 800] and look["role"] == 1, look["full"])
        sl = pg.evaluate("(() => { const i = document.getElementById('cutFuss'); return [i.min, i.max, i.value, document.querySelector('#cutout .cutVal').textContent]; })()")
        check("the Fussiness slider: 0 to 100, 30 to start", sl == ["0", "100", "30", "30"], sl)
        btn = pg.evaluate("[...document.querySelectorAll('#cutout [data-cut]')].map((e) => [e.dataset.cut, e.disabled, e.classList.contains('main')])")
        check("Undo and Reset off until a tap; Done is the main button", ["undo", True, False] in btn and ["reset", True, False] in btn and ["done", False, True] in btn, btn)
        shot(pg, "sheet-before.png")

        # ------------------------------------------------------------ C: a tap, connected and everywhere
        group[0] = "C. tap"
        check("set-up: the corner, the ring and the hole all start opaque", px(pg, 5, 5) == [255, 255, 255, 255] and px(pg, 200, 60)[3] == 255 and px(pg, 200, 150) == [255, 255, 255, 255],
              [px(pg, 5, 5), px(pg, 200, 60), px(pg, 200, 150)])
        cut_tap(pg, 5, 5)
        st = state(pg)
        check("a tap on the corner: the corner goes see-through (alpha 0)", px(pg, 5, 5)[3] == 0 and px(pg, 395, 295)[3] == 0 and st["steps"] == 1, [px(pg, 5, 5), px(pg, 395, 295), st])
        check("... the ring is untouched", px(pg, 200, 60) == [220, 30, 30, 255] and px(pg, 200, 240) == [220, 30, 30, 255], [px(pg, 200, 60), px(pg, 200, 240)])
        check("... the hole inside the ring is STILL white (connected only)", px(pg, 200, 150) == [255, 255, 255, 255], px(pg, 200, 150))
        mk = pg.evaluate("(() => { const m = document.querySelector('#cutout .cutMark'); return m && !m.hidden ? [m.style.left, m.style.top] : null; })()")
        check("the ring marks where the tap landed", mk is not None and abs(float(mk[0][:-1]) - 5.5 / 4) < 0.1, mk)
        check("Undo and Reset are on after a tap", pg.evaluate("[...document.querySelectorAll('#cutout [data-cut=undo], #cutout [data-cut=reset]')].every((e) => !e.disabled)"))
        shot(pg, "sheet-after-tap.png")
        bar(pg, "undo")
        check("set-up: back to the original", px(pg, 5, 5)[3] == 255 and state(pg)["steps"] == 0)
        pg.click("#cutout [data-cut='everywhere']"); pg.wait_for_timeout(60)
        sw = pg.evaluate("(() => { const e = document.querySelector('#cutout [data-cut=everywhere]'); return [e.getAttribute('role'), e.getAttribute('aria-checked'), e.classList.contains('on')]; })()")
        check("the Everywhere switch turns on (role switch, aria-checked)", sw == ["switch", "true", True], sw)
        cut_tap(pg, 5, 5)
        check("Everywhere on: the corner AND the hole go", px(pg, 5, 5)[3] == 0 and px(pg, 200, 150)[3] == 0, [px(pg, 5, 5), px(pg, 200, 150)])
        check("... the ring stays", px(pg, 200, 60) == [220, 30, 30, 255], px(pg, 200, 60))
        shot(pg, "sheet-everywhere.png")
        bar(pg, "undo"); pg.click("#cutout [data-cut='everywhere']"); pg.wait_for_timeout(40)
        check("set-up: Everywhere off, nothing removed", state(pg)["everywhere"] is False and state(pg)["steps"] == 0 and px(pg, 200, 150)[3] == 255)
        cut_tap(pg, 200, 150)
        check("a tap in the hole takes the hole only (the outside stays)", px(pg, 200, 150)[3] == 0 and px(pg, 5, 5)[3] == 255, [px(pg, 200, 150), px(pg, 5, 5)])
        cut_tap(pg, 200, 150)
        check("a tap on a see-through pixel does nothing (a wall): still one step", state(pg)["steps"] == 1, state(pg))

        # ------------------------------------------------------------ D: Undo, Reset, Cancel, Escape, Ctrl+Z
        group[0] = "D. undo, reset, cancel"
        cut_tap(pg, 5, 5)
        check("two taps: two steps, both areas gone", state(pg)["steps"] == 2 and px(pg, 5, 5)[3] == 0 and px(pg, 200, 150)[3] == 0, state(pg))
        bar(pg, "undo")
        check("Undo steps back one tap: the outside is back, the hole still gone", px(pg, 5, 5)[3] == 255 and px(pg, 200, 150)[3] == 0 and state(pg)["steps"] == 1)
        bar(pg, "undo")
        check("Undo again: the hole is back, no steps, Undo off", px(pg, 200, 150)[3] == 255 and state(pg)["steps"] == 0 and pg.evaluate("document.querySelector('#cutout [data-cut=undo]').disabled"))
        cut_tap(pg, 5, 5); cut_tap(pg, 200, 150)
        bar(pg, "reset")
        check("Reset: the original picture, no steps", px(pg, 5, 5) == [255, 255, 255, 255] and px(pg, 200, 150) == [255, 255, 255, 255] and state(pg)["steps"] == 0, state(pg))
        cut_tap(pg, 5, 5)
        pg.keyboard.press("Control+z"); pg.wait_for_timeout(80)
        check("Ctrl+Z in the sheet undoes the sheet's tap", state(pg)["steps"] == 0 and px(pg, 5, 5)[3] == 255, state(pg))
        check("... and not the note: the picture is still on the page with its path", (rec_of(pg, "s0", RID) or {}).get("data", {}).get("path") == RPATH)
        cut_tap(pg, 5, 5)
        bar(pg, "cancel")
        check("Cancel closes the sheet", not is_open(pg))
        check("... the record's path is unchanged", (rec_of(pg, "s0", RID) or {}).get("data", {}).get("path") == RPATH, rec_of(pg, "s0", RID))
        kp = pg.evaluate("([p, q]) => window.__T.kept(p, q)", [RPATH, [[5, 5], [200, 150]]])
        check("... and its pixels as they were (the device copy: the corner opaque white)", kp and kp["px"][0] == [255, 255, 255, 255], kp)
        select(pg, "s0", [RID]); cut_open(pg)
        check("opened again: the picture as it came, no steps", state(pg)["steps"] == 0 and px(pg, 5, 5)[3] == 255)
        cut_tap(pg, 5, 5)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(80)
        check("Escape is Cancel: closed, the path unchanged", not is_open(pg) and rec_of(pg, "s0", RID)["data"]["path"] == RPATH)

        # ------------------------------------------------------------ E: the feather
        group[0] = "E. feather"
        clear_sel(pg)
        soft = add_img(pg, soft_pic(), "soft.png", "image/png", "s0") or {}
        cut_open(pg)
        cut_tap(pg, 3, 3)
        a = pg.evaluate("""() => { const out = []; for (let y = 0; y < 300; y++) for (let x = 0; x < 300; x++) out.push(window.__pw.cutout.pixel(x, y)); return out; }""")
        near = [p for p in a if p[3] == 255 and d_white(p) < 81]
        part = [p for p in a if 0 < p[3] < 255]
        check("a soft blue disc on white, a tap outside: no near-white pixel (within 1.5 x 54 of white) left at full alpha", not near, [len(near), near[:5]])
        check("... the edge is feathered: some pixels keep a share of their alpha", len(part) > 100, len(part))
        check("... the disc's middle is untouched", px(pg, 150, 150)[3] == 255 and px(pg, 150, 150)[2] > 180, px(pg, 150, 150))
        mono = [p for p in part if d_white(p) <= 54]
        check("... feathered pixels are all between 1 and 1.5 x the distance (54 to 81 from white)", not mono and all(54 < d_white(p) < 81 for p in part), [len(mono), mono[:3]])
        bar(pg, "cancel")

        # ------------------------------------------------------------ F: the slider, live on the last tap
        group[0] = "F. slider"
        clear_sel(pg)
        step = add_img(pg, step_pic(), "step.png", "image/png", "s0") or {}
        cut_open(pg)
        fuss(pg, 0)
        check("set-up: the slider at 0 (the number follows)", pg.evaluate("document.querySelector('#cutout .cutVal').textContent") == "0" and state(pg)["fuss"] == 0)
        cut_tap(pg, 20, 100)
        check("fussiness 0, a tap on the pure white: the white goes", px(pg, 20, 100)[3] == 0 and px(pg, 140, 10)[3] == 0, [px(pg, 20, 100), px(pg, 140, 10)])
        check("... the (250, 250, 250) next to it stays", px(pg, 250, 100) == [250, 250, 250, 255], px(pg, 250, 100))
        fuss(pg, 30)
        check("the slider moved to 30 (no other tap): the (250, 250, 250) goes too", px(pg, 250, 100)[3] == 0 and px(pg, 20, 100)[3] == 0, px(pg, 250, 100))
        check("... still ONE step (the slider re-ran the last tap)", state(pg)["steps"] == 1, state(pg))
        check("... the black bar stays", px(pg, 150, 100) == [0, 0, 0, 255], px(pg, 150, 100))
        fuss(pg, 0)
        check("back to 0: the (250, 250, 250) is back, the white still gone", px(pg, 250, 100) == [250, 250, 250, 255] and px(pg, 20, 100)[3] == 0, px(pg, 250, 100))
        bar(pg, "undo")
        check("Undo after the slider: the original", px(pg, 20, 100)[3] == 255 and state(pg)["steps"] == 0)
        fuss(pg, 30)
        cut_tap(pg, 250, 100)
        check("a tap after the slider uses its value (30 from the 250 grey takes the white too)", px(pg, 250, 100)[3] == 0 and px(pg, 20, 100)[3] == 0, [px(pg, 250, 100), px(pg, 20, 100)])
        bar(pg, "cancel")

        # ------------------------------------------------------------ G: pinch zoom, and a tap under the zoom
        group[0] = "G. pinch"
        select(pg, "s0", [RID]); cut_open(pg)
        sb = pg.evaluate("(() => { const r = document.querySelector('#cutout .cutStage').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        cx, cy = sb
        pg.evaluate("([x, y]) => { window.__T.ptr('pointerdown', 1, x - 40, y); window.__T.ptr('pointerdown', 2, x + 40, y); }", [cx, cy])
        for k in range(1, 9):
            pg.evaluate("([x, y, k]) => { window.__T.ptr('pointermove', 1, x - 40 - 10 * k, y); window.__T.ptr('pointermove', 2, x + 40 + 10 * k, y + 4 * k); }", [cx, cy, k])
        pg.evaluate("([x, y]) => { window.__T.ptr('pointerup', 2, x + 120, y + 32); window.__T.ptr('pointerup', 1, x - 120, y); }", [cx, cy])
        pg.wait_for_timeout(60)
        st = state(pg)
        check("two fingers apart: the picture zooms (about 2.5 x)", 2.0 < st["zoom"] < 3.2, st["zoom"])
        check("... and a pinch is never a tap (no step)", st["steps"] == 0, st)
        tf = pg.evaluate("document.querySelector('#cutout .cutBoard').style.transform")
        check("... the board carries the zoom as a transform", "scale(" in tf, tf)
        cut_tap(pg, 200, 150)
        check("a tap under the zoom lands on the right pixel (the hole goes, the outside stays)", px(pg, 200, 150)[3] == 0 and px(pg, 5, 5)[3] == 255, [px(pg, 200, 150), px(pg, 5, 5)])
        bar(pg, "cancel")

        # ------------------------------------------------------------ H: Done
        group[0] = "H. done"
        select(pg, "s0", [RID]); cut_open(pg)
        bar(pg, "done")
        check("Done with nothing removed is Cancel: closed, the path unchanged", not is_open(pg) and rec_of(pg, "s0", RID)["data"]["path"] == RPATH)
        before = rec_of(pg, "s0", RID)
        open_list(pg); pg.wait_for_timeout(400)
        th0 = pg.evaluate("([i, r]) => window.__T.thumbHref(i, r)", [1, RID])
        close_list(pg)
        hist0 = pg.evaluate("(window.__pw.S.hist[window.__pw.S.openNote] || {}).u ? window.__pw.S.hist[window.__pw.S.openNote].u.length : -1")
        select(pg, "s0", [RID]); cut_open(pg)
        cut_tap(pg, 5, 5)
        bar(pg, "done")
        until(pg, lambda: not is_open(pg), 4000)
        after = rec_of(pg, "s0", RID) or {}
        NPATH = after.get("data", {}).get("path")
        check("Done: the sheet closes", not is_open(pg))
        check("the record's data.path is a NEW .png path (<owner>/<uuid>.png)", NPATH and NPATH != RPATH and re.match(r"^local/[0-9a-f-]{36}\.png$", NPATH), [RPATH, NPATH])
        same = all(after.get(k) == before.get(k) for k in ["id", "page_id", "seq", "kind", "style"]) and \
               all(after["data"].get(k) == before["data"].get(k) for k in ["x", "y", "w", "h", "nw", "nh", "rot", "locked"])
        check("... id, seq, x, y, w, h, nw, nh, rot, locked and the style unchanged", same, [before, after])
        check("... the old file is still on this device", pg.evaluate("(p) => window.__pw.pdf.cached(p)", RPATH))
        kp = pg.evaluate("([p, q]) => window.__T.kept(p, q)", [NPATH, [[5, 5], [200, 60], [200, 150]]]) or {}
        check("the new file: a PNG (89 50 4E 47), 400 x 300 (the picture's own size), image/png", kp.get("head") == [0x89, 0x50, 0x4E, 0x47] and kp.get("w") == 400 and kp.get("h") == 300 and kp.get("type") == "image/png", kp)
        check("... the corner see-through, the ring red, the hole white (as edited)", kp and kp["px"][0][3] == 0 and kp["px"][1] == [220, 30, 30, 255] and kp["px"][2] == [255, 255, 255, 255], kp.get("px"))
        hist1 = pg.evaluate("(window.__pw.S.hist[window.__pw.S.openNote] || {}).u ? window.__pw.S.hist[window.__pw.S.openNote].u.length : -1")
        check("ONE undo step on the note", hist0 >= 0 and hist1 == hist0 + 1, [hist0, hist1])
        h_new = pg.evaluate("([s, r]) => window.__T.pageHref(s, r)", ["s0", RID])
        check("the page draws the new file (a Blob URL)", h_new and h_new.startswith("blob:"), h_new)
        sel_ = pg.evaluate("window.__pw.ink.selection()")
        check("the picture stays selected", sel_ and sel_["ids"] == [RID], sel_)
        idle(pg)
        tw = [r for r in pg.evaluate("() => window.__pw.api.strokesOf(['s0'])") if r["id"] == RID]
        check("the twin has the record with the new path (saved)", tw and tw[0]["data"]["path"] == NPATH, tw)
        check("the new file goes up the ladder (in the twin's bucket)", until(pg, lambda: NPATH in pg.evaluate("window.__pw.api.importsList()") and pg.evaluate("window.__pw.pdf.uploadsPending()") == 0, 8000))
        open_list(pg); pg.wait_for_timeout(400)
        th1 = pg.evaluate("([i, r]) => window.__T.thumbHref(i, r)", [1, RID])
        check("the page list thumb changed to the new file", th0 and th1 and th1 != th0, [th0, th1])
        close_list(pg)
        undo(pg)
        check("page Undo: the old path back, its bytes drawn (the old Blob URL)", rec_of(pg, "s0", RID)["data"]["path"] == RPATH and pg.evaluate("([s, r]) => window.__T.pageHref(s, r)", ["s0", RID]) != h_new,
              rec_of(pg, "s0", RID)["data"]["path"])
        redo(pg)
        check("Redo: the new path again", rec_of(pg, "s0", RID)["data"]["path"] == NPATH and pg.evaluate("([s, r]) => window.__T.pageHref(s, r)", ["s0", RID]) == h_new)
        select(pg, "s0", [RID]); cut_open(pg)
        check("Cut out again starts from the edited picture (the corner already see-through)", px(pg, 5, 5)[3] == 0 and state(pg)["steps"] == 0, px(pg, 5, 5))
        bar(pg, "cancel")

        # ------------------------------------------------------------ I: a JPEG
        group[0] = "I. jpeg"
        go_page(pg, 2)
        jp = add_img(pg, jpeg_pic(), "photo.jpg", "image/jpeg", "s2") or {}
        JPATH = jp.get("data", {}).get("path", "")
        check("set-up: a JPEG picture (.jpg) on page 3", JPATH.endswith(".jpg"), JPATH)
        cut_open(pg); cut_tap(pg, 5, 5); bar(pg, "done")
        until(pg, lambda: not is_open(pg), 4000)
        jn = (rec_of(pg, "s2", jp.get("id")) or {}).get("data", {}).get("path", "")
        kj = pg.evaluate("([p, q]) => window.__T.kept(p, q)", [jn, [[5, 5], [200, 150]]]) or {}
        check("Done on a JPEG: the new path is a .png", jn.endswith(".png") and jn != JPATH, jn)
        check("... a PNG with alpha: the corner see-through, the green square opaque", kj.get("head") == [0x89, 0x50, 0x4E, 0x47] and kj["px"][0][3] == 0 and kj["px"][1][3] == 255 and kj["px"][1][1] > 120, kj)

        # ------------------------------------------------------------ J: the PDF export and the share image
        group[0] = "J. pdf + share"
        go_page(pg, 1)
        cr = add_img(pg, cream_pic(), "cream.png", "image/png", "s1") or {}
        cd = cr.get("data", {})
        out_pt, blk_pt = on_page(cd, 40, 40), on_page(cd, 200, 150)
        p0 = pdf_page(pg, "s1")
        g2 = lambda im, p: im.getpixel((int(p[0] * K * 2), int(p[1] * K * 2)))
        check("set-up: the PDF before: cream where the picture's background is", is_cream(g2(p0, out_pt)), g2(p0, out_pt))
        cut_open(pg); cut_tap(pg, 5, 5); bar(pg, "done")
        until(pg, lambda: not is_open(pg), 4000)
        cp = (rec_of(pg, "s1", cr.get("id")) or {}).get("data", {}).get("path", "")
        check("set-up: the cream picture has its new .png", cp.endswith(".png") and cp != cd.get("path"), cp)
        p1 = pdf_page(pg, "s1")
        p1.save(str(SHOTS / "pdf-page-after.png"))
        check("the PDF export after Done: the paper shows through where the cream was (not cream)", is_paper(g2(p1, out_pt)) and not is_cream(g2(p1, out_pt)), g2(p1, out_pt))
        check("... the dark block is still there", max(g2(p1, blk_pt)) < 140, g2(p1, blk_pt))
        def snap_px():
            if "local/s1.webp" not in pg.evaluate("window.__pw.api.storageList()"): return None
            sn = pg.evaluate("window.__pw.snap()")
            if sn["due"] or sn["running"]: return None
            got = pg.evaluate("""async (pts) => { const blob = await window.__pw.api.getSnapshot('local/s1.webp'), bm = await createImageBitmap(blob);
              const c = document.createElement('canvas'); c.width = bm.width; c.height = bm.height; const g = c.getContext('2d'); g.drawImage(bm, 0, 0);
              return [bm.width, ...pts.map((p) => [...g.getImageData(Math.round(p[0]), Math.round(p[1]), 1, 1).data.slice(0, 3)])]; }""", [out_pt, blk_pt])
            return got if got[0] == W and is_paper(got[1]) and max(got[2]) < 140 else None
        sp = until(pg, snap_px, 25000, 300)
        check("the U3b page picture (snap.js, the one Claude reads) after Done: the paper through the hole, the block there", sp, sp)
        open_list(pg)
        thumb(pg, 2).click(button="right"); pg.wait_for_timeout(80); menu(pg, "Share page"); pg.wait_for_selector("#shareDlg")   # data-index is 1-based: page 2 = s1
        pg.click("#shareDlg button[data-share='images']"); pg.wait_for_selector("#shareReady", timeout=30000)
        pg.evaluate("window.__shared = null"); pg.click("#shareDlg button[data-share='send']")
        pg.wait_for_function("window.__shared", timeout=10000); pg.wait_for_timeout(60)
        shr = pg.evaluate("async () => { const f = window.__shared.files[0]; return [f.type, await window.__T.b64(f)]; }")
        sim = Image.open(io.BytesIO(base64.b64decode(shr[1]))).convert("RGB")
        s2 = lambda p: sim.getpixel((int(p[0] * 2), int(p[1] * 2)))
        check("Share as images: the paper shows through where the cream was, the block is there", shr[0] == "image/png" and is_paper(s2(out_pt)) and not is_cream(s2(out_pt)) and max(s2(blk_pt)) < 140,
              [sim.size, s2(out_pt), s2(blk_pt)])
        close_list(pg)

        # ------------------------------------------------------------ K: the 10 MB cap, a picture not here yet
        group[0] = "K. too big, not here"
        select(pg, "s1", [cr.get("id")]); cut_open(pg); cut_tap(pg, 200, 150)
        pg.evaluate("""() => { const o = HTMLCanvasElement.prototype.toBlob; window.__toBlob = o;
          HTMLCanvasElement.prototype.toBlob = function (cb, t, q) { if (this.closest && this.closest('#cutout')) cb(new Blob([new Uint8Array(10485761)], { type: 'image/png' })); else o.call(this, cb, t, q); }; }""")
        pg.evaluate("window.__toastLog = []")
        bar(pg, "done"); pg.wait_for_timeout(200)
        check("a PNG over 10 MB: the toast says so", "This picture is too big (over 10 MB)." in toasts(pg), toasts(pg))
        check("... the sheet stays open, its tap kept, the path unchanged", is_open(pg) and state(pg)["steps"] == 1 and rec_of(pg, "s1", cr.get("id"))["data"]["path"] == cp, state(pg))
        shot(pg, "sheet-too-big.png")
        pg.evaluate("() => { HTMLCanvasElement.prototype.toBlob = window.__toBlob; }")
        bar(pg, "cancel")
        ghost = {"id": "ghost-1", "page_id": "s1", "seq": 999999999999999, "kind": "image", "style": {"colour": "#000000", "width": 0, "dash": "solid", "opacity": 1},
                 "data": {"path": "local/00000000-0000-4000-8000-000000000000.png", "x": 100, "y": 700, "w": 200, "h": 150, "nw": 400, "nh": 300, "rot": 0, "locked": False}}
        pg.evaluate("(r) => window.__pw.ink.put('s1', [r])", ghost); pg.wait_for_timeout(60)
        select(pg, "s1", ["ghost-1"])
        check("a picture whose bytes are not on this device: the chip is there", "cutout" in chips(pg), chips(pg))
        pg.evaluate("document.getElementById('toast').classList.remove('show')")     # the too-big toast, out of the picture
        pg.click(".selChips .chip[data-act='cutout']"); pg.wait_for_selector("#cutout"); pg.wait_for_timeout(400)
        gs = state(pg)
        check("... the sheet says This picture has not downloaded yet, Done is off", gs["msg"] == "This picture has not downloaded yet" and not gs["loaded"]
              and pg.evaluate("document.querySelector('#cutout [data-cut=done]').disabled"), gs)
        shot(pg, "sheet-not-downloaded.png")
        bar(pg, "cancel")
        check("... Cancel is the way out", not is_open(pg))
        select(pg, "s1", ["ghost-1"]); pg.click(".selChips .chip[data-act='delete']"); pg.wait_for_timeout(80)
        check("set-up: the picture that never downloaded is deleted again", rec_of(pg, "s1", "ghost-1") is None)

        # ------------------------------------------------------------ L: dark mode, the phone
        group[0] = "L. dark, phone"
        go_page(pg, 0)
        pg.evaluate("document.getElementById('toast').classList.remove('show')")     # K's toast, out of the pictures
        select(pg, "s0", [RID]); cut_open(pg)
        cut_tap(pg, 200, 150)                                                          # the hole (the corner went at Done)
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')"); pg.wait_for_timeout(100)
        dk = pg.evaluate("""(() => { const v = document.getElementById('cutout'); return [getComputedStyle(v.querySelector('.cut')).backgroundColor,
          getComputedStyle(v.querySelector('.cutBoard')).backgroundColor, getComputedStyle(v.querySelector('.cutBoard')).backgroundImage.includes('220, 220, 220'),
          getComputedStyle(v.querySelector('.cutHead b')).color]; })()""")
        check("dark mode: the sheet takes the dialogs' dark card (#2A2E34), the checkerboard stays white and light grey",
              dk[0] == "rgb(42, 46, 52)" and dk[1] == "rgb(255, 255, 255)" and dk[2] and dk[3] == "rgb(231, 229, 224)", dk)
        shot(pg, "sheet-dark.png")
        pg.evaluate("document.documentElement.removeAttribute('data-theme')"); pg.wait_for_timeout(60)
        pg.set_viewport_size({"width": 375, "height": 740}); pg.wait_for_timeout(400)
        ph = pg.evaluate("""(() => { const v = document.getElementById('cutout'), q = (s) => v.querySelector(s).getBoundingClientRect();
          const d = q('[data-cut=done]'), c = q('[data-cut=cancel]'), u = q('[data-cut=undo]'), r = q('[data-cut=reset]'), e = q('[data-cut=everywhere]'),
            g = q('.cutGrow'), s = q('#cutFuss'), bar = q('.cutBar'), st = q('.cutStage'), bd = q('.cutBoard');
          const R = (b) => [Math.round(b.left), Math.round(b.top), Math.round(b.right), Math.round(b.bottom)];
          return { done: R(d), cancel: R(c), undo: R(u), reset: R(r), every: R(e), grow: R(g), slider: R(s), bar: R(bar), stage: R(st), board: R(bd) }; })()""")
        vw, vh = 375, 740
        check("the phone (375 x 740): Done's box is inside the viewport", ph["done"][0] >= 0 and ph["done"][1] >= 0 and ph["done"][2] <= vw and ph["done"][3] <= vh, ph["done"])
        check("... the slider has its own row, the first (full width, above Undo)", ph["grow"][3] <= ph["undo"][1] and ph["grow"][2] - ph["grow"][0] > 300, [ph["grow"], ph["undo"]])
        check("... then Undo / Reset / Everywhere on one row", abs(ph["undo"][1] - ph["reset"][1]) <= 4 and abs((ph["undo"][1] + ph["undo"][3]) / 2 - (ph["every"][1] + ph["every"][3]) / 2) <= 4, [ph["undo"], ph["reset"], ph["every"]])
        check("... then Cancel / Done on the last row, at the right", ph["cancel"][1] >= ph["undo"][3] and abs(ph["cancel"][1] - ph["done"][1]) <= 4 and ph["done"][2] >= vw - 20, [ph["cancel"], ph["done"]])
        check("... the whole bar is on screen and the stage shrank above it", ph["bar"][3] <= vh and ph["stage"][3] <= ph["bar"][1] + 1, [ph["bar"], ph["stage"]])
        check("... the picture is fitted inside the stage", ph["board"][0] >= ph["stage"][0] - 1 and ph["board"][2] <= ph["stage"][2] + 1, [ph["board"], ph["stage"]])
        check("... the tap is still there after the resize (Undo on, the hole see-through)", state(pg)["steps"] == 1 and px(pg, 200, 150)[3] == 0
              and not pg.evaluate("document.querySelector('#cutout [data-cut=undo]').disabled"), state(pg))
        shot(pg, "phone-sheet.png")
        pg.set_viewport_size({"width": 1280, "height": 800}); pg.wait_for_timeout(400)
        bar(pg, "cancel")

        # ------------------------------------------------------------ M: the 2048 x 2048 worst case
        group[0] = "M. 2048 speed"
        go_page(pg, 2)
        bg = add_img(pg, big_pic(), "big.png", "image/png", "s2") or {}
        check("set-up: a 2048 x 2048 picture (kept at 2048)", bg.get("data", {}).get("nw") == 2048 and bg.get("data", {}).get("nh") == 2048, bg.get("data"))
        cut_open(pg)
        cut_tap(pg, 5, 5)
        s1_ = state(pg); FILL["connected"] = (s1_["fillMs"], s1_["tapMs"])
        check(f"a tap on the 2048 x 2048 background: the fill under 300 ms ({s1_['fillMs']:.0f} ms; the whole tap {s1_['tapMs']:.0f} ms)",
              s1_["steps"] == 1 and s1_["fillMs"] < 300, s1_)
        check("... the background went, the shapes stayed", px(pg, 2040, 10)[3] == 0 and px(pg, 700, 700)[3] == 255 and px(pg, 1500, 1500)[3] == 255, [px(pg, 2040, 10), px(pg, 700, 700)])
        fuss(pg, 60); s2_ = state(pg); FILL["slider"] = (s2_["fillMs"], s2_["tapMs"])
        check(f"the slider's re-run on 2048 x 2048 under 300 ms ({s2_['fillMs']:.0f} ms; with the restore and draw {s2_['tapMs']:.0f} ms)", s2_["fillMs"] < 300 and s2_["steps"] == 1, s2_)
        bar(pg, "undo"); pg.click("#cutout [data-cut='everywhere']"); cut_tap(pg, 5, 5)
        s3_ = state(pg); FILL["everywhere"] = (s3_["fillMs"], s3_["tapMs"])
        check(f"Everywhere on 2048 x 2048 under 300 ms ({s3_['fillMs']:.0f} ms; the whole tap {s3_['tapMs']:.0f} ms)", s3_["fillMs"] < 300 and s3_["steps"] == 1, s3_)
        bar(pg, "cancel")

        # ------------------------------------------------------------ N: the files
        group[0] = "N. files"
        check("no page errors", not errs, errs)
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        check("cache is pw-v9f", "pw-v9f" in keys, keys)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("sw.js: CACHE pw-v9f, its version line, and js/cutout.js in the shell", 'const CACHE = "pw-v9f";' in swt and "   pw-v9e (7 Nov): " in swt and '"./js/cutout.js"' in swt)
        src = pg.evaluate("fetch('./js/cutout.js').then(r => r.text())")
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))
        check("js/cutout.js asks nothing of the network (no fetch, no http, no XMLHttpRequest, no WebSocket, no import())",
              not re.search(r"fetch\(|https?:|XMLHttpRequest|WebSocket|import\(", code))
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/cutout.js", "./js/ink.js", "./js/app.js", "./js/pdfin.js", "./css/app.css", "./sw.js", "./tests/test_cutout.py"])
        check("no em-dashes in the files this round touched", chr(0x2014) not in srcs)

        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g_, n, ok, info in res:
    if g_ not in groups: groups.append(g_)
    if not ok: print(f"FAIL [{g_}] {n}  -> {str(info)[:700]}")
print()
for g_ in groups:
    rs_ = [r for r in res if r[0] == g_]
    print(f"{g_}: {sum(r[2] for r in rs_)}/{len(rs_)} passed")
for k_, v_ in FILL.items():
    print(f"2048 x 2048 {k_}: fill {v_[0]:.1f} ms, whole step {v_[1]:.1f} ms")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
