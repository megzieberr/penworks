# PenWorks Crop checks (pw-v9g, her ask 13 Nov "I want to be able to crop my images please"): a rectangle crop of a picture,
# on the page (js/crop.js).
# Run: python -E -P tests/test_crop.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800, the way tests/test_cutout.py does. Every picture is
# made with Pillow in memory here (nothing is written to tests/fixtures/) and comes in through the + menu's Image input.
# What it proves: the Crop chip (after the wand) for ONE unlocked picture only, a picture on a sticky too; crop mode: the
# layer, eight handles, 40 px targets at two zooms, the bar's words; a handle drag (mouse and finger) resizes, a drag inside
# moves, both kept on the picture and above the minimum; the pen draws nothing and a handle drag never scrolls; Done on a
# straight and on a turned picture keeps the kept part's corners where they were on the page (measured through the drawn
# <image>'s own matrix), a new file at full resolution with its see-through kept, ONE undo step, undo and redo, still
# selected; the whole box = Cancel; Enter, Escape, Ctrl+Z; the 10 MB toast; a JPEG stays a JPEG; the PDF export, the page
# list thumb, the U3b page picture and Share as images show the cropped picture. Pictures go to _build/v9g/.
import sys, subprocess, time, pathlib, math, base64, io, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8830
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "v9g"
W, H = 794, 1123
K = 595.28 / 794                       # PDF points per page px (A4 portrait)

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

# ------------------------------------------------------------ the pictures (Pillow, in memory)
RED, GREEN, BLUE, YELLOW = (220, 30, 30), (30, 160, 60), (30, 60, 200), (240, 200, 40)
def quad_pic():                        # 400 x 300 RGBA: four coloured quarters, a 50 x 50 see-through block top-left
    im = Image.new("RGBA", (400, 300), RED + (255,)); d = ImageDraw.Draw(im)
    d.rectangle([200, 0, 399, 149], fill=GREEN + (255,)); d.rectangle([0, 150, 199, 299], fill=BLUE + (255,))
    d.rectangle([200, 150, 399, 299], fill=YELLOW + (255,)); d.rectangle([0, 0, 49, 49], fill=(0, 0, 0, 0))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
def jpeg_pic():                        # 400 x 300 JPEG: green left half, blue right half
    im = Image.new("RGB", (400, 300), GREEN); ImageDraw.Draw(im).rectangle([200, 0, 399, 299], fill=BLUE)
    b = io.BytesIO(); im.save(b, "JPEG", quality=92); return b.getvalue()

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-13T08:00:00Z', pages = [];
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
  T.host = (id) => document.querySelector(`#stack .sheet[data-id="${id}"], #stack .sticky[data-id="${id}"]`);
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.imgs = (id) => T.recs(id).filter((r) => r.kind === 'image');
  T.chips = () => [...document.querySelectorAll('.selChips .chip')].map((c) => c.dataset.act);
  T.b64 = async (blob) => { const u = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
  T.kept = async (path, pts) => { const b = await window.__PI.bytesOf(path); if (!b) return null;
    const head = [...new Uint8Array(await b.slice(0, 4).arrayBuffer())], bm = await createImageBitmap(b, { premultiplyAlpha: 'none' });
    const c = document.createElement('canvas'); c.width = bm.width; c.height = bm.height; const g = c.getContext('2d'); g.drawImage(bm, 0, 0);
    return { type: b.type, w: bm.width, h: bm.height, head, px: pts.map((p) => [...g.getImageData(p[0], p[1], 1, 1).data]) }; };
  // the drawn <image> of picture rid on surface sid: its four corners (or the points (fu, fv) of its box) through its own
  // matrix, in the surface's px: what is really on the page
  T.drawn = (sid, rid, pts) => { const g = T.host(sid).querySelector(`svg.ink g.img > g[data-id="${rid}"]`), el = g && g.firstElementChild;
    if (!el || el.tagName !== 'image') return null;
    const m = el.getCTM(), x = +el.getAttribute('x'), y = +el.getAttribute('y'), w = +el.getAttribute('width'), h = +el.getAttribute('height');
    return (pts || [[0, 0], [1, 0], [1, 1], [0, 1]]).map(([u, v]) => { const p = new DOMPoint(x + u * w, y + v * h).matrixTransform(m); return [p.x, p.y]; }); };
  // a point (lx, ly) of the picture's own frame (unturned, from its box's top-left) mapped the same way: before a crop
  T.drawnAt = (sid, rid, lpts) => { const g = T.host(sid).querySelector(`svg.ink g.img > g[data-id="${rid}"]`), el = g.firstElementChild, m = el.getCTM();
    const x = +el.getAttribute('x'), y = +el.getAttribute('y');
    return lpts.map(([a, b]) => { const p = new DOMPoint(x + a, y + b).matrixTransform(m); return [p.x, p.y]; }); };
  T.hit = (k) => { const e = document.querySelector(`.cropLayer [data-k="${k}"]`); if (!e) return null; const c = e.querySelector('.cropHit') || e, r = c.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2, r.width, r.height]; };
  T.tptr = (el, type, id, x, y) => el.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch', isPrimary: true, bubbles: true, cancelable: true,
    button: type === 'pointermove' ? -1 : 0, buttons: type === 'pointerup' ? 0 : 1, clientX: x, clientY: y }));
  T.hist = () => { const h = window.__pw.S.hist[window.__pw.S.openNote]; return h && h.u ? h.u.length : -1; };
  T.thumbImg = (idx, rid) => { const e = document.querySelector(`#plThumbs .thumbP[data-index='${idx}'] svg.thumbInk g.img > g[data-id="${rid}"] > image`);
    return e ? [e.getAttribute('href'), +e.getAttribute('x'), +e.getAttribute('y'), +e.getAttribute('width'), +e.getAttribute('height')] : null; };
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
def sel_ids(pg): return (pg.evaluate("window.__pw.ink.selection()") or {}).get("ids")
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
def st(pg): return pg.evaluate("window.__pw.crop.state()")
def crop_open(pg):
    pg.click(".selChips .chip[data-act='crop']"); pg.wait_for_selector(".cropLayer", timeout=4000); pg.wait_for_timeout(80)
def crop_set(pg, l, t, r, b): pg.evaluate("(a) => window.__pw.crop.set(...a)", [l, t, r, b]); pg.wait_for_timeout(30)
def crop_done(pg):
    pg.click(".cropBar button[data-crop='done']")
    until(pg, lambda: not st(pg)["active"], 5000); pg.wait_for_timeout(80)
def is_on(pg): return st(pg)["active"]
def hit(pg, k): return pg.evaluate("(k) => window.__T.hit(k)", k)
def zoom(pg): return pg.evaluate("window.__P.view().z")
def view(pg): return pg.evaluate("(() => { const v = window.__P.view(); return [v.x, v.y, v.z]; })()")
def mdrag(pg, a, b, steps=6):
    pg.mouse.move(a[0], a[1]); pg.mouse.down(); pg.mouse.move(b[0], b[1], steps=steps); pg.mouse.up(); pg.wait_for_timeout(60)
def near(a, b, tol): return all(abs(p - q) <= tol for p, q in zip(a, b))
def corners_close(A, B, tol=0.05): return A and B and len(A) == len(B) and max(max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(A, B)) <= tol
def max_err(A, B): return round(max(max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(A, B)), 4) if A and B else None
def is_paper(c): return min(c[:3]) > 185 and max(c[:3]) - min(c[:3]) < 40
def col_near(c, ref, tol=40): return all(abs(c[i] - ref[i]) <= tol for i in range(3))
def pdf_page(pg, sid):
    b64 = pg.evaluate("""async (sid) => { const m = await import('./js/pdfout.js');
      const blob = await m.buildPdf([{ id: sid, orientation: 'portrait', background: 'grid', pdf_path: null }], 'crop');
      return window.__T.b64(blob); }""", sid)
    doc = fitz.open(stream=base64.b64decode(b64), filetype="pdf")
    pm = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    return Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(150)
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose"); pg.wait_for_timeout(60)
def hide_toast(pg): pg.evaluate("document.getElementById('toast').classList.remove('show')")

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
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
        q = add_img(pg, quad_pic(), "quad.png", "image/png", "s0") or {}
        QID, QPATH, QD = q.get("id"), q.get("data", {}).get("path"), q.get("data", {})
        check("set-up: the picture lands on page 1, 400 x 300 page px, selected", QID and QD.get("w") == 400 and QD.get("h") == 300 and sel_ids(pg) == [QID], QD)
        ch = chips(pg)
        check("one unlocked picture: ... Lock, Cut out, then Crop", ch == ["copy", "cut", "duplicate", "delete", "lock", "cutout", "crop"], ch)
        lab = pg.evaluate("(() => { const c = document.querySelector(\".selChips .chip[data-act='crop']\"); return c ? [c.getAttribute('aria-label'), c.title, !!c.querySelector('svg')] : null; })()")
        check("... its word is Crop (aria-label and title), an icon", lab == ["Crop", "Crop", True], lab)
        bb = pg.locator(".selChips").bounding_box()
        pg.screenshot(path=str(SHOTS / "chips-crop.png"), clip={"x": max(0, bb["x"] - 40), "y": max(0, bb["y"] - 20), "width": bb["width"] + 80, "height": 80})
        ink = {"id": "ink-1", "page_id": "s0", "seq": 5, "kind": "pen", "style": {"colour": "#000000", "width": 2.5, "dash": "solid", "opacity": 1},
               "data": {"points": [[60, 900], [120, 910], [180, 904]]}}
        pg.evaluate("(r) => window.__pw.ink.put('s0', [r])", ink); pg.wait_for_timeout(60)
        select(pg, "s0", ["ink-1"])
        check("ink alone: no Crop", "crop" not in chips(pg), chips(pg))
        select(pg, "s0", [QID, "ink-1"])
        check("the picture and a stroke: no Crop", "crop" not in chips(pg) and "lock" in chips(pg), chips(pg))
        select(pg, "s0", [QID]); pg.click(".selChips .chip[data-act='lock']"); pg.wait_for_timeout(80)
        check("a locked picture: no Crop (Delete and Unlock only)", chips(pg) == ["delete", "lock"], chips(pg))
        pg.click(".selChips .chip[data-act='lock']"); pg.wait_for_timeout(80)
        check("unlocked again: Crop is back", "crop" in chips(pg), chips(pg))
        clear_sel(pg)

        # ------------------------------------------------------------ B: crop mode
        group[0] = "B. crop mode"
        hist0 = pg.evaluate("window.__T.hist()")
        select(pg, "s0", [QID]); crop_open(pg)
        s = st(pg)
        check("Crop starts crop mode on that picture, the rectangle the whole picture", s["active"] and s["id"] == QID and s["rect"] == {"l": 0, "t": 0, "r": 400, "b": 300}, s)
        check("... the selection clears (no chips, no selection box)", sel_ids(pg) is None and not pg.evaluate("document.querySelector('.selChips')"))
        lay = pg.evaluate("""(() => { const L = document.querySelector('.cropLayer');
          return { inSheet: L.parentElement.matches('.sheet[data-id="s0"]'), ks: [...L.querySelectorAll('[data-k]')].map((e) => e.dataset.k),
            dim: !!L.querySelector('.cropDim'), ov: getComputedStyle(L).overflow,
            bar: [...document.querySelectorAll('.cropBar button')].map((e) => e.textContent) }; })()""")
        check("the layer sits in page 1's sheet, never clipped (overflow visible), with the dimmed outside", lay["inSheet"] and lay["ov"] == "visible" and lay["dim"], lay)
        check("... the inside and eight handles (four sides, four corners)", sorted(lay["ks"]) == sorted(["move", "n", "s", "w", "e", "nw", "ne", "se", "sw"]), lay["ks"])
        check("the bar: Cancel and Done", lay["bar"] == ["Cancel", "Done"], lay["bar"])
        z1 = zoom(pg); h1 = hit(pg, "se")
        check(f"a handle's target is about 40 screen px across (zoom {z1:.2f})", h1 and 38 <= h1[2] <= 42 and 38 <= h1[3] <= 42, h1)
        bbar = pg.locator(".cropBar").bounding_box(); nwh = hit(pg, "nw")
        check("the bar sits clear of the top handles' targets", bbar["y"] + bbar["height"] <= nwh[1] - nwh[3] / 2 + 1, [bbar, nwh])
        pg.screenshot(path=str(SHOTS / "crop-mode-tablet.png"))

        # ------------------------------------------------------------ C: handles, clamping, the pen, the scroll
        group[0] = "C. handles"
        v0 = view(pg); z = v0[2]
        a = hit(pg, "se"); mdrag(pg, a, (a[0] - 100 * z, a[1] - 60 * z))
        s = st(pg)["rect"]
        check("the se corner dragged 100 left, 60 up (page px): the rectangle follows", near([s["r"], s["b"]], [300, 240], 0.6) and s["l"] == 0 and s["t"] == 0, s)
        check("... a handle drag never scrolls the page", view(pg) == v0, [v0, view(pg)])
        a = hit(pg, "nw"); mdrag(pg, a, (a[0] - 300, a[1] - 300))
        s = st(pg)["rect"]
        check("nw dragged far outside the picture: clamped at the picture's corner", s["l"] == 0 and s["t"] == 0, s)
        a = hit(pg, "e"); mdrag(pg, a, (a[0] - 600, a[1]))
        s = st(pg)["rect"]
        check("e dragged past the left side: the rectangle stops at the minimum (20 page px)", abs(s["r"] - s["l"] - 20) < 0.01, s)
        crop_set(pg, 50, 40, 250, 200)
        a = hit(pg, "move"); mdrag(pg, a, (a[0] + 600, a[1] + 400))
        s = st(pg)["rect"]
        check("a drag inside moves it; it stops at the picture's edge, its size kept", near([s["l"], s["t"], s["r"], s["b"]], [200, 140, 400, 300], 0.01), s)
        a = hit(pg, "s")
        check("the s handle is in the middle of the bottom edge", a and abs(a[0] - (hit(pg, "sw")[0] + hit(pg, "se")[0]) / 2) < 0.6, a)
        crop_set(pg, 50, 40, 250, 200)
        n0 = len(pg.evaluate("(id) => window.__T.recs(id)", "s0"))
        sh = pg.evaluate("window.__T.host('s0').getBoundingClientRect().toJSON()")
        mdrag(pg, (sh["x"] + 600 * z, sh["y"] + 700 * z), (sh["x"] + 700 * z, sh["y"] + 760 * z))
        check("the mouse (the pen's way in) on the page outside the picture: no ink drawn, crop mode stays", len(pg.evaluate("(id) => window.__T.recs(id)", "s0")) == n0 and is_on(pg) and st(pg)["rect"] == {"l": 50, "t": 40, "r": 250, "b": 200})
        a = hit(pg, "e")
        pg.evaluate("""([x, y]) => { const el = document.querySelector('.cropLayer [data-k="e"] .cropHit');
          window.__T.tptr(el, 'pointerdown', 7, x, y); for (let k = 1; k <= 5; k++) window.__T.tptr(el, 'pointermove', 7, x + 8 * k, y);
          window.__T.tptr(el, 'pointerup', 7, x + 40, y); }""", [a[0], a[1]])
        pg.wait_for_timeout(60)
        s = st(pg)["rect"]
        check("a finger on the e handle drags it (40 screen px right)", abs(s["r"] - (250 + 40 / z)) < 0.6, s)
        check("... and the page did not scroll under it", view(pg) == v0, [v0, view(pg)])
        pg.evaluate("""([x, y]) => { const d = document.getElementById('desk');
          window.__T.tptr(d, 'pointerdown', 9, x, y); for (let k = 1; k <= 6; k++) window.__T.tptr(d, 'pointermove', 9, x, y - 15 * k);
          window.__T.tptr(d, 'pointerup', 9, x, y - 90); }""", [sh["x"] + 650 * z, sh["y"] + 700 * z])
        pg.wait_for_timeout(300)
        v1 = view(pg)
        check("a finger off the rectangle still scrolls the page (one finger pans)", v1[1] != v0[1] and is_on(pg), [v0, v1])
        pg.keyboard.down("Control"); pg.mouse.move(640, 400); pg.mouse.wheel(0, -300); pg.keyboard.up("Control"); pg.wait_for_timeout(300)
        z2 = zoom(pg); h2 = hit(pg, "se")
        check(f"zoomed (Ctrl + wheel, zoom {z2:.2f}): still crop mode, the targets still about 40 screen px", abs(z2 - z) > 0.05 and is_on(pg) and h2 and 38 <= h2[2] <= 42, [z, z2, h2])
        pg.keyboard.down("Control"); pg.mouse.wheel(0, 300); pg.keyboard.up("Control"); pg.wait_for_timeout(300)
        go_page(pg, 0)
        pg.keyboard.press("Control+z"); pg.wait_for_timeout(80)
        check("Ctrl+Z in crop mode does nothing to the note (held back)", pg.evaluate("window.__T.hist()") == hist0 and is_on(pg) and rec_of(pg, "s0", QID)["data"]["path"] == QPATH)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(80)
        check("Escape is Cancel: crop mode ends, the picture unchanged and selected again", not is_on(pg) and rec_of(pg, "s0", QID)["data"] == QD and sel_ids(pg) == [QID],
              [st(pg), sel_ids(pg)])
        check("... no layer, no bar left behind", not pg.evaluate("document.querySelector('.cropLayer, .cropBar')"))
        crop_open(pg); pg.click(".cropBar button[data-crop='cancel']"); pg.wait_for_timeout(80)
        check("the Cancel button: the same", not is_on(pg) and rec_of(pg, "s0", QID)["data"] == QD and sel_ids(pg) == [QID])

        # ------------------------------------------------------------ D: Done on a straight picture
        group[0] = "D. done straight"
        crop_open(pg); crop_done(pg)
        check("Done with the rectangle still the whole picture is Cancel: nothing changes, no undo step",
              rec_of(pg, "s0", QID)["data"] == QD and pg.evaluate("window.__T.hist()") == hist0 and sel_ids(pg) == [QID])
        crop_open(pg); crop_set(pg, 30, 20, 330, 250)
        want = pg.evaluate("([s, r, p]) => window.__T.drawnAt(s, r, p)", ["s0", QID, [[30, 20], [330, 20], [330, 250], [30, 250]]])
        crop_done(pg)
        after = rec_of(pg, "s0", QID) or {}; AD = after.get("data", {}); NPATH = AD.get("path")
        check("Done: a NEW .png path", NPATH and NPATH != QPATH and re.match(r"^local/[0-9a-f-]{36}\.png$", NPATH), [QPATH, NPATH])
        check("... the box is the kept part: x 30 + its old x, w 300, h 230, nw 300, nh 230",
              abs(AD["x"] - (QD["x"] + 30)) < 0.002 and abs(AD["y"] - (QD["y"] + 20)) < 0.002 and AD["w"] == 300 and AD["h"] == 230 and AD["nw"] == 300 and AD["nh"] == 230, AD)
        check("... id, seq, rot, locked and the style kept", all(after.get(k) == q.get(k) for k in ["id", "page_id", "seq", "kind", "style"]) and AD.get("rot") == QD.get("rot") and AD.get("locked") == QD.get("locked"), after)
        got = pg.evaluate("([s, r]) => window.__T.drawn(s, r)", ["s0", QID])
        check(f"the kept part's four corners stay put on the page (drawn, max error {max_err(want, got)} page px)", corners_close(want, got), [want, got])
        kp = pg.evaluate("([p, q]) => window.__T.kept(p, q)", [NPATH, [[0, 0], [100, 100], [250, 100], [100, 200], [250, 200], [19, 29], [20, 30]]]) or {}
        check("the new file: a PNG at full resolution (300 x 230 of the 400 x 300)", kp.get("head") == [0x89, 0x50, 0x4E, 0x47] and kp.get("w") == 300 and kp.get("h") == 230, kp)
        px_ = kp.get("px", [])
        check("... its pixels are the original's: see-through kept (the block), red, green, blue, yellow",
              len(px_) == 7 and px_[0][3] == 0 and px_[5][3] == 0 and px_[6][3] == 255 and px_[1][:3] == list(RED) and px_[2][:3] == list(GREEN) and px_[3][:3] == list(BLUE) and px_[4][:3] == list(YELLOW), px_)
        check("ONE undo step on the note", pg.evaluate("window.__T.hist()") == hist0 + 1)
        check("the picture stays selected", sel_ids(pg) == [QID], sel_ids(pg))
        check("the old file is still on this device", pg.evaluate("(p) => window.__pw.pdf.cached(p)", QPATH))
        pg.screenshot(path=str(SHOTS / "after-done-tablet.png"))
        undo(pg)
        check("Undo: the whole picture back (its path and box)", rec_of(pg, "s0", QID)["data"] == QD, rec_of(pg, "s0", QID)["data"])
        full = pg.evaluate("([s, r]) => window.__T.drawn(s, r)", ["s0", QID])
        check("... drawn at its old place", corners_close(full, [[QD["x"], QD["y"]], [QD["x"] + 400, QD["y"]], [QD["x"] + 400, QD["y"] + 300], [QD["x"], QD["y"] + 300]]), full)
        redo(pg)
        check("Redo: cropped again, the same box", rec_of(pg, "s0", QID)["data"] == AD and corners_close(want, pg.evaluate("([s, r]) => window.__T.drawn(s, r)", ["s0", QID])))
        idle(pg)
        tw = [r for r in pg.evaluate("() => window.__pw.api.strokesOf(['s0'])") if r["id"] == QID]
        check("the twin has the cropped record (saved)", tw and tw[0]["data"]["path"] == NPATH and tw[0]["data"]["w"] == 300, tw)
        check("the new file goes up the ladder", until(pg, lambda: NPATH in pg.evaluate("window.__pw.api.importsList()") and pg.evaluate("window.__pw.pdf.uploadsPending()") == 0, 8000))
        select(pg, "s0", [QID]); crop_open(pg)
        check("Crop again starts from the cropped picture (300 x 230)", st(pg)["w"] == 300 and st(pg)["h"] == 230)
        crop_set(pg, 0, 0, 150, 230); pg.keyboard.press("Enter"); until(pg, lambda: not is_on(pg), 5000); pg.wait_for_timeout(80)
        d2 = rec_of(pg, "s0", QID)["data"]
        check("Enter is Done: cropped again (150 x 230, nw 150)", d2["w"] == 150 and d2["nw"] == 150 and d2["path"] != NPATH, d2)
        undo(pg)
        check("set-up: undone to the first crop", rec_of(pg, "s0", QID)["data"] == AD)

        # ------------------------------------------------------------ E: a turned picture
        group[0] = "E. turned"
        go_page(pg, 1)
        tq = {**q, "id": "turned-1", "page_id": "s1", "data": {**QD, "x": 200, "y": 300, "rot": 30}}
        pg.evaluate("(r) => window.__pw.ink.put('s1', [r])", tq); pg.wait_for_timeout(100)
        select(pg, "s1", ["turned-1"]); crop_open(pg)
        tr = pg.evaluate("document.querySelector('.cropLayer > g').getAttribute('transform')")
        check("crop mode on a turned picture (rot 30): its rectangle and handles turn with it", tr and tr.replace(" ", "") == "rotate(30400450)", tr)
        z = zoom(pg)
        a = hit(pg, "e"); t30 = math.radians(30)
        mdrag(pg, a, (a[0] - 60 * z * math.cos(t30), a[1] - 60 * z * math.sin(t30)))
        s = st(pg)["rect"]
        check("the e handle dragged 60 page px along the turned edge: the right side moves in by 60", abs(s["r"] - 340) < 0.6 and s["t"] == 0 and s["b"] == 300, s)
        pg.screenshot(path=str(SHOTS / "crop-mode-turned.png"))
        crop_set(pg, 60, 40, 300, 280)
        want = pg.evaluate("([s, r, p]) => window.__T.drawnAt(s, r, p)", ["s1", "turned-1", [[60, 40], [300, 40], [300, 280], [60, 280]]])
        crop_done(pg)
        td = rec_of(pg, "s1", "turned-1")["data"]
        got = pg.evaluate("([s, r]) => window.__T.drawn(s, r)", ["s1", "turned-1"])
        check(f"Done: the kept part's corners stay put on the turned page (max error {max_err(want, got)} page px)", corners_close(want, got), [want, got, td])
        check("... rot kept (30), box 240 x 240, nw 240", td["rot"] == 30 and td["w"] == 240 and td["h"] == 240 and td["nw"] == 240 and td["nh"] == 240, td)
        undo(pg)
        check("Undo: the turned picture whole again", rec_of(pg, "s1", "turned-1")["data"] == tq["data"])
        redo(pg)
        check("Redo: cropped again", rec_of(pg, "s1", "turned-1")["data"] == td)

        # ------------------------------------------------------------ F: a picture on a sticky
        group[0] = "F. sticky"
        go_page(pg, 0)
        pg.evaluate("window.__pw.sticky.add('yellow')"); pg.wait_for_timeout(200)
        sk = pg.evaluate("window.__pw.sticky.stickiesOf('s0').map((s) => s.id)")
        SK = sk[0] if sk else None
        skp = {**q, "id": "sk-pic", "page_id": SK, "data": {**QD, "path": QPATH, "x": 20, "y": 40, "w": 160, "h": 120, "rot": 0}}
        if SK: pg.evaluate("([s, r]) => window.__pw.ink.put(s, [r])", [SK, skp]); pg.wait_for_timeout(100)
        ok_sel = bool(SK) and select(pg, SK, ["sk-pic"])
        check("a picture on a sticky: the Crop chip is there", ok_sel and "crop" in chips(pg), [SK, chips(pg)])
        if ok_sel:
            crop_open(pg)
            check("... crop mode on the sticky's own layer", st(pg)["page"] == SK and pg.evaluate("document.querySelector('.cropLayer').parentElement.classList.contains('sticky')"))
            crop_set(pg, 40, 30, 120, 90)
            want = pg.evaluate("([s, r, p]) => window.__T.drawnAt(s, r, p)", [SK, "sk-pic", [[40, 30], [120, 30], [120, 90], [40, 90]]])
            crop_done(pg)
            sd = rec_of(pg, SK, "sk-pic")["data"]
            got = pg.evaluate("([s, r]) => window.__T.drawn(s, r)", [SK, "sk-pic"])
            check(f"... Done: the kept part stays put on the sticky (max error {max_err(want, got)})", corners_close(want, got) and sd["path"] != QPATH, [want, got, sd])
            check("... full resolution: 80 x 60 sticky px of a 400 x 300 file shown at 160 x 120 = 200 x 150 file px", sd["nw"] == 200 and sd["nh"] == 150 and sd["w"] == 80 and sd["h"] == 60, sd)
            check("... still selected on the sticky", (pg.evaluate("window.__pw.ink.selection()") or {}).get("page") == SK and sel_ids(pg) == ["sk-pic"])
        clear_sel(pg)

        # ------------------------------------------------------------ G: a JPEG, the 10 MB cap
        group[0] = "G. jpeg, too big"
        go_page(pg, 2)
        jp = add_img(pg, jpeg_pic(), "photo.jpg", "image/jpeg", "s2") or {}
        JPATH = jp.get("data", {}).get("path", "")
        check("set-up: a JPEG picture (.jpg) on page 3", JPATH.endswith(".jpg"), JPATH)
        crop_open(pg); crop_set(pg, 100, 0, 300, 300); crop_done(pg)
        jn = (rec_of(pg, "s2", jp.get("id")) or {}).get("data", {})
        kj = pg.evaluate("([p, q]) => window.__T.kept(p, q)", [jn.get("path"), [[10, 150], [190, 150]]]) or {}
        check("Done on a JPEG keeps a JPEG (.jpg, FF D8 FF), 200 x 300", jn.get("path", "").endswith(".jpg") and jn.get("path") != JPATH and kj.get("head", [])[:3] == [0xFF, 0xD8, 0xFF] and kj.get("w") == 200 and kj.get("h") == 300, [jn, kj])
        check("... green on its left, blue on its right", kj and col_near(kj["px"][0], GREEN, 20) and col_near(kj["px"][1], BLUE, 20), kj.get("px"))
        select(pg, "s2", [jp.get("id")]); crop_open(pg); crop_set(pg, 10, 10, 150, 150)
        pg.evaluate("""() => { const o = HTMLCanvasElement.prototype.toBlob; window.__toBlob = o;
          HTMLCanvasElement.prototype.toBlob = function (cb, t, q) { if (!this.isConnected && this.width === 140 && this.height === 140) cb(new Blob([new Uint8Array(10485761)], { type: t })); else o.call(this, cb, t, q); }; }""")
        pg.evaluate("window.__toastLog = []")
        h0 = pg.evaluate("window.__T.hist()")
        pg.click(".cropBar button[data-crop='done']"); pg.wait_for_timeout(300)
        check("a crop over 10 MB: the toast says so", "This picture is too big (over 10 MB)." in toasts(pg), toasts(pg))
        check("... crop mode stays, its rectangle kept, the picture unchanged", is_on(pg) and st(pg)["rect"] == {"l": 10, "t": 10, "r": 150, "b": 150} and rec_of(pg, "s2", jp.get("id"))["data"] == jn and pg.evaluate("window.__T.hist()") == h0, st(pg))
        pg.evaluate("() => { HTMLCanvasElement.prototype.toBlob = window.__toBlob; }")
        pg.click(".cropBar button[data-crop='cancel']"); pg.wait_for_timeout(60); hide_toast(pg)
        check("set-up: cancelled", not is_on(pg))

        # ------------------------------------------------------------ H: the PDF, the thumb, the page picture, the share
        group[0] = "H. pdf, thumb, snapshot, share"
        go_page(pg, 1)
        open_list(pg); pg.wait_for_timeout(400)
        th0 = pg.evaluate("([i, r]) => window.__T.thumbImg(i, r)", [2, "turned-1"])
        close_list(pg)
        tr2 = rec_of(pg, "s1", "turned-1")
        pg.evaluate("(r) => window.__pw.ink.put('s1', [r])", {**q, "id": "plain-2", "page_id": "s1", "seq": tr2["seq"] + 1, "data": {**QD, "x": 150, "y": 700, "rot": 0}}); pg.wait_for_timeout(100)
        cut_pt, keep_pt, red_pt = [150 + 380, 700 + 280], [150 + 300, 700 + 200], [150 + 120, 700 + 100]
        p0 = pdf_page(pg, "s1"); g2 = lambda im, p: im.getpixel((int(p[0] * K * 2), int(p[1] * K * 2)))
        check("set-up: the PDF before: yellow where the crop will take it away", col_near(g2(p0, cut_pt), YELLOW), g2(p0, cut_pt))
        select(pg, "s1", ["plain-2"]); crop_open(pg); crop_set(pg, 50, 50, 350, 250); crop_done(pg)
        p1 = pdf_page(pg, "s1")
        p1.save(str(SHOTS / "pdf-page-after.png"))
        check("the PDF export after the crop: paper where the cut-away part was", is_paper(g2(p1, cut_pt)), g2(p1, cut_pt))
        check("... the kept part where it was: yellow, red", col_near(g2(p1, keep_pt), YELLOW) and col_near(g2(p1, red_pt), RED), [g2(p1, keep_pt), g2(p1, red_pt)])
        open_list(pg); pg.wait_for_timeout(500)
        th1 = pg.evaluate("([i, r]) => window.__T.thumbImg(i, r)", [2, "plain-2"])
        nd = rec_of(pg, "s1", "plain-2")["data"]
        check("the page list thumb draws the cropped picture: the new file at the new box", th1 and th1[0] and th1[0].startswith("blob:") and near(th1[1:], [nd["x"], nd["y"], nd["w"], nd["h"]], 0.01), [th1, nd])
        thT = pg.evaluate("([i, r]) => window.__T.thumbImg(i, r)", [2, "turned-1"])
        check("... and the turned one's thumb at its cropped box", thT and near(thT[1:], [td["x"], td["y"], td["w"], td["h"]], 0.01) and th0 and thT[0] == th0[0], [th0, thT, td])
        close_list(pg)
        def snap_px():
            if "local/s1.webp" not in pg.evaluate("window.__pw.api.storageList()"): return None
            sn = pg.evaluate("window.__pw.snap()")
            if sn["due"] or sn["running"]: return None
            got_ = pg.evaluate("""async (pts) => { const blob = await window.__pw.api.getSnapshot('local/s1.webp'), bm = await createImageBitmap(blob);
              const c = document.createElement('canvas'); c.width = bm.width; c.height = bm.height; const g = c.getContext('2d'); g.drawImage(bm, 0, 0);
              return [bm.width, ...pts.map((p) => [...g.getImageData(Math.round(p[0]), Math.round(p[1]), 1, 1).data.slice(0, 3)])]; }""", [cut_pt, keep_pt])
            return got_ if got_[0] == W and is_paper(got_[1]) and col_near(got_[2], YELLOW) else None
        sp = until(pg, snap_px, 25000, 300)
        check("the U3b page picture after the crop: paper where it was cut, yellow where kept", sp, sp)
        open_list(pg)
        thumb(pg, 2).click(button="right"); pg.wait_for_timeout(80); menu(pg, "Share page"); pg.wait_for_selector("#shareDlg")
        pg.click("#shareDlg button[data-share='images']"); pg.wait_for_selector("#shareReady", timeout=30000)
        pg.evaluate("window.__shared = null"); pg.click("#shareDlg button[data-share='send']")
        pg.wait_for_function("window.__shared", timeout=10000); pg.wait_for_timeout(60)
        shr = pg.evaluate("async () => { const f = window.__shared.files[0]; return [f.type, await window.__T.b64(f)]; }")
        sim = Image.open(io.BytesIO(base64.b64decode(shr[1]))).convert("RGB")
        s2 = lambda p: sim.getpixel((int(p[0] * 2), int(p[1] * 2)))
        check("Share as images: paper where it was cut, yellow and red where kept", is_paper(s2(cut_pt)) and col_near(s2(keep_pt), YELLOW) and col_near(s2(red_pt), RED), [sim.size, s2(cut_pt), s2(keep_pt)])
        close_list(pg)

        # ------------------------------------------------------------ I: the phone, the files
        group[0] = "I. phone, files"
        go_page(pg, 0)
        select(pg, "s0", [QID]); crop_open(pg)
        pg.set_viewport_size({"width": 375, "height": 740}); pg.wait_for_timeout(400)
        check("the phone width: crop mode still on, a target still about 40 screen px", is_on(pg) and 38 <= (hit(pg, "se") or [0, 0, 0])[2] <= 42, hit(pg, "se"))
        pg.set_viewport_size({"width": 1280, "height": 800}); pg.wait_for_timeout(400)
        pg.click("#backBtn"); pg.wait_for_timeout(300)
        check("closing the note ends crop mode, nothing left behind", not is_on(pg) and not pg.evaluate("document.querySelector('.cropLayer, .cropBar')"))
        check("no page errors", not errs, errs)
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        check("cache is pw-v9g", "pw-v9g" in keys, keys)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("sw.js: CACHE pw-v9g, its version line, js/crop.js in the shell", 'const CACHE = "pw-v9g";' in swt and "   pw-v9g (13 Nov): " in swt and '"./js/crop.js"' in swt)
        src = pg.evaluate("fetch('./js/crop.js').then(r => r.text())")
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//")).replace("'http://www.w3.org/2000/svg'", "SVG")   # the SVG namespace is a name, not a call
        check("js/crop.js asks nothing of the network (the SVG namespace aside)", not re.search(r"fetch\(|https?:|XMLHttpRequest|WebSocket|import\(", code))
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/crop.js", "./js/ink.js", "./js/app.js", "./js/pdfin.js", "./css/app.css", "./sw.js", "./tests/test_crop.py"])
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
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
