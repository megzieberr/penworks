# PenWorks U4c checks (pw-v8p): PICTURES on a page (_build/U4C-PICTURES-BRIEF.md). Place, move, resize, turn, lock,
# see-through kept.
# Run: python tests/test_u4c.py        (local mode only: ?local=1, Supabase is never touched)
# Seeds one note of 3 grid pages into the localStorage twin, 1280 x 800 (the tablet landscape size), the way tests/test_axes.py
# does. Pen gestures are PointerEvents (pointerType 'pen') fired on the desk. The fixtures are made with Pillow into
# tests/fixtures/ (u4c-ring.png: a thick red ring on a fully see-through 400 x 400; u4c-photo.jpg: 3000 x 2000, a blue block
# on white; u4c-small.webp: 200 x 120, its left half see-through; u4c-broken.png: a PNG signature and nonsense). Pixels are
# read from screenshots with Pillow, the PDF with PyMuPDF.
# What it proves: the + menu reads Page, PDF, Image; a picture lands as ONE 'image' record on the current page (the data of
# the brief's call 1), sized (w = min(nw, 0.8 x 794), the height under 0.8 x 1123) and centred in the part of the page she
# sees, selected with the Select tool on; a 3000 px photo is kept at 2048 px as a JPEG, a WebP as a PNG; it lives in g.img
# under g.hl and g.pen, so ink drawn over it shows on top, and its see-through hole shows the paper (screen, share image,
# PDF); move, corner resize (aspect kept), turn (15 degree snap) and a mixed turn (about the selection's centre), one undo
# step each; tap and box select; Copy, Paste, Duplicate, Cut, Delete and page Copy / Paste carry the same path; Lock and
# Unlock (the padlock chip, a box and Select all leave a locked picture, a tap selects it alone without corners or ring,
# Delete + Unlock only, a drag does nothing); the erasers, restyle, the tray's recolour and page Erase never touch it; the
# page list thumb, the note card, the U3b page picture and Share as images show it; the PDF puts it where the page shows it
# at 0, 90 and 30 degrees (within 1 pt) with its alpha; offline it lands, survives an offline reload and goes up when the
# wifi is back; the phone shows the wait rectangle, then the picture; a broken file is one toast and nothing; the frames
# stay smooth while a page with three pictures is panned at zoom 3. Screenshots go to _build/shots-u4c/.
import sys, subprocess, time, pathlib, math, base64, io, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8821
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "shots-u4c"
FIX = ROOT / "tests" / "fixtures"
RING, PHOTO, SMALL, BROKEN = FIX / "u4c-ring.png", FIX / "u4c-photo.jpg", FIX / "u4c-small.webp", FIX / "u4c-broken.png"
W, H = 794, 1123
K = 595.28 / 794                       # PDF points per page px (A4 portrait)
BLUE = "#0D0DFF"
FRAME_MS = 50                          # the pan's frame budget: no frame gap over this (3 frames at 60 Hz)

def fixtures():
    FIX.mkdir(exist_ok=True)
    if not RING.exists():
        im = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.ellipse([20, 20, 380, 380], fill=(220, 30, 30, 255)); d.ellipse([110, 110, 290, 290], fill=(0, 0, 0, 0))
        im.save(RING)
    if not PHOTO.exists():
        ph = Image.new("RGB", (3000, 2000), (255, 255, 255)); ImageDraw.Draw(ph).rectangle([600, 400, 1199, 999], fill=(20, 40, 220))
        ph.save(PHOTO, quality=92)
    if not SMALL.exists():
        sm = Image.new("RGBA", (200, 120), (40, 160, 60, 255)); ImageDraw.Draw(sm).rectangle([0, 0, 99, 119], fill=(40, 160, 60, 0))
        sm.save(SMALL, lossless=True)
    if not BROKEN.exists(): BROKEN.write_bytes(b"\x89PNG\r\n\x1a\n" + b"this is not a picture at all" * 20)
fixtures()

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-03T08:00:00Z', pages = [];
  for (let k = 0; k < 3; k++) pages.push({ id: 's' + k, note_id: 'n1', position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Pictures', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three pages', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages }));
}"""
INIT = """
  document.addEventListener('click', () => { window.__inTap = true; setTimeout(() => { window.__inTap = false; }, 0); }, true);
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
  T.z = () => window.__P.view().z;
  T.sheet = (id) => document.querySelector(`#stack .sheet[data-id="${id}"]`);
  T.client = (id, x, y) => { const r = T.sheet(id).getBoundingClientRect(), z = T.z(); return [r.left + x * z, r.top + y * z]; };
  T.ev = (type, id, kind, x, y, buttons) => document.getElementById('desk').dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: kind,
    isPrimary: true, bubbles: true, cancelable: true, button: type === 'pointermove' ? -1 : 0,
    buttons: buttons !== undefined ? buttons : type === 'pointerup' ? 0 : 1, clientX: x, clientY: y, screenX: x + 10, screenY: y + 80 }));
  T.pen = (id, pts) => {
    const c = pts.map((p) => T.client(id, p[0], p[1]));
    T.ev('pointerdown', 31, 'pen', c[0][0], c[0][1]);
    for (const q of c.slice(1)) T.ev('pointermove', 31, 'pen', q[0], q[1]);
    T.ev('pointerup', 31, 'pen', c[c.length - 1][0], c[c.length - 1][1]);
  };
  T.recs = (id) => window.__pw.ink.strokesOf(id);
  T.imgs = (id) => T.recs(id).filter((r) => r.kind === 'image');
  T.vis = (idx) => { const b = document.getElementById('desk').getBoundingClientRect(), a = window.__P.pagePoint(idx, b.left, b.top), c = window.__P.pagePoint(idx, b.right, b.bottom);
    const cx = (v) => Math.max(0, Math.min(794, v)), cy = (v) => Math.max(0, Math.min(1123, v));
    return [cx(a[0]), cy(a[1]), cx(c[0]), cy(c[1])]; };
  T.chips = () => [...document.querySelectorAll('.selChips .chip')].map((c) => [c.dataset.act, c.getAttribute('aria-label')]);
  T.selParts = () => { const g = document.querySelector('#stack svg.ink g.sel'); return g ? [g.querySelectorAll('.selh').length, g.querySelectorAll('.selrot').length] : null; };
  T.layer = (sid) => [...T.sheet(sid).querySelector('svg.ink').children].map((c) => c.getAttribute('class'));
  T.imgEl = (sid, rid) => { const g = T.sheet(sid).querySelector(`svg.ink > g.img > g[data-id="${rid}"]`); if (!g) return null;
    const e = g.firstElementChild;
    return { tag: e.tagName, cls: e.getAttribute('class'), href: (e.getAttribute('href') || '').slice(0, 5), par: e.getAttribute('preserveAspectRatio'),
      x: +e.getAttribute('x'), y: +e.getAttribute('y'), w: +e.getAttribute('width'), h: +e.getAttribute('height'), tr: e.getAttribute('transform') }; };
  T.dev = async (path) => { const b = await window.__PI.bytesOf(path); if (!b) return null; const bm = await createImageBitmap(b); return [b.type, bm.width, bm.height]; };
  T.twinType = async (path) => { try { return (await window.__pw.api.getImport(path)).type; } catch (e) { return null; } };
  T.b64 = async (blob) => { const u = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
  T.knob = () => { const k = document.querySelector('#stack svg.ink circle.selrot'); return k ? [+k.getAttribute('cx'), +k.getAttribute('cy')] : null; };
  return 1;
}"""
TWIN_JS = "() => JSON.parse(localStorage.getItem('penworks.local.v2'))"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def z(pg): return pg.evaluate("window.__T.z()")
def recs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.recs(id)", pid)
def imgs(pg, pid="s0"): return pg.evaluate("(id) => window.__T.imgs(id)", pid)
def ink_recs(pg, pid="s0"): return [r for r in recs(pg, pid) if r["kind"] != "image"]
def pen(pg, pts, page="s0"): pg.evaluate("([id, p]) => window.__T.pen(id, p)", [page, pts]); pg.wait_for_timeout(40)
def sel(pg): return pg.evaluate("window.__pw.ink.selection()")
def clear_sel(pg): pg.evaluate("window.__pw.ink.clearSelection()")
def chips(pg): return pg.evaluate("window.__T.chips()")
def parts(pg): return pg.evaluate("window.__T.selParts()")
def tool(pg, t): pg.click(f"#tool-{t}"); pg.wait_for_timeout(40)
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(60)
def redo(pg): pg.click("#redoBtn"); pg.wait_for_timeout(60)
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def menu_items(pg): return [t_.strip() for t_ in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def toasts(pg): return [t for t in pg.evaluate("window.__toastLog") if t]
def until(pg, fn, ms=4000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def add_img(pg, path, pid="s0"):
    n = len(imgs(pg, pid))
    pg.set_input_files("#imgInput", str(path))
    until(pg, lambda: len(imgs(pg, pid)) > n, 8000)
    pg.wait_for_timeout(60)
    got = imgs(pg, pid)
    return got[-1] if len(got) > n else None
def centre(d): return [d["x"] + d["w"] / 2, d["y"] + d["h"] / 2]
def addv(a, b): return [a[0] + b[0], a[1] + b[1]]
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def rotate(p, c, deg):
    a = math.radians(deg); dx, dy = p[0] - c[0], p[1] - c[1]
    return [c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a)]
def shot(pg):
    return Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
def spix(pg, pts, page="s0"):
    im = shot(pg); out = []
    for p in pts:
        cx, cy = pg.evaluate("([id, x, y]) => window.__T.client(id, x, y)", [page, p[0], p[1]])
        out.append(im.getpixel((int(round(cx)), int(round(cy)))))
    return out
def is_red(c): return c[0] > 150 and c[1] < 110 and c[2] < 110
def is_blue(c): return c[2] > 150 and c[0] < 120 and c[1] < 120
def is_paper(c): return min(c) > 185 and max(c) - min(c) < 40          # white, or the grid's light grey line
def red_count(im):
    by = im.tobytes(); return sum(1 for i in range(0, len(by), 3) if is_red(by[i:i + 3]))
def turn_sel(pg, deg, steps=10):
    """drag the selection's turn ring by deg degrees about the selection's centre"""
    k = pg.evaluate("window.__T.knob()"); sb = sel(pg)["box"]; cc = [(sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2]
    pen(pg, [rotate(k, cc, deg * j / steps) for j in range(steps + 1)]); pg.wait_for_timeout(40)
    return cc
def pdf_of(pg):
    b64 = pg.evaluate("""async () => { const m = await import('./js/pdfout.js');
      const blob = await m.buildPdf([{ id: 's0', orientation: 'portrait', background: 'grid', pdf_path: null }], 'u4c');
      return window.__T.b64(blob); }""")
    return fitz.open(stream=base64.b64decode(b64), filetype="pdf")
def pdf_img_bbox(doc):
    info = [i for i in doc[0].get_image_info() if i["width"] == 400 and i["height"] == 400]
    return fitz.Rect(info[0]["bbox"]) if info else None
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])"); pg.wait_for_timeout(120)
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose"); pg.wait_for_timeout(60)
def thumb_menu(pg, i, label):
    open_list(pg); thumb(pg, i).click(button="right"); pg.wait_for_timeout(60); menu(pg, label); pg.wait_for_timeout(120)
def offline(pg): pg.context.set_offline(True); pg.evaluate("window.dispatchEvent(new Event('offline'))"); pg.wait_for_timeout(50)
def online(pg): pg.context.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))")
def b64file(p): return base64.b64encode(pathlib.Path(p).read_bytes()).decode()

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
        pg.click(f'#tray .sw[data-colour="{BLUE}"]'); pg.wait_for_timeout(40)   # the pen in Blue

        # ------------------------------------------------------------ A: the way in
        group[0] = "A. the way in"
        pg.click("#addPageBtn"); pg.wait_for_timeout(60)
        items = menu_items(pg)
        check("the note's + menu reads Page, PDF, Image, Sticky (pw-v9c)", items == ["Page", "PDF", "Image", "Sticky"], items)
        acc = pg.get_attribute("#imgInput", "accept")
        check("#imgInput takes PNG, JPEG and WebP (one file)", acc == "image/png,image/jpeg,image/webp" and pg.get_attribute("#imgInput", "multiple") is None, acc)
        vis = pg.evaluate("window.__T.vis(0)")
        with pg.expect_file_chooser() as fc:
            menu(pg, "Image")
        fc.value.set_files(str(RING))
        until(pg, lambda: len(imgs(pg)) == 1, 8000); pg.wait_for_timeout(80)
        ring = imgs(pg)[0] if imgs(pg) else {}
        d0 = dict(ring.get("data", {}))
        check("Image picks a file and ONE 'image' record lands on the current page", len(imgs(pg)) == 1 and len(recs(pg)) == 1, recs(pg))
        check("its style is the table's shape, unused ({ #000000, 0, solid, 1 })", ring.get("style") == {"colour": "#000000", "width": 0, "dash": "solid", "opacity": 1}, ring.get("style"))
        check("data has exactly path, x, y, w, h, nw, nh, rot, locked", sorted(d0) == sorted(["path", "x", "y", "w", "h", "nw", "nh", "rot", "locked"]), sorted(d0))
        check("path = local/<uuid>.png, nw = nh = 400, w = h = 400 (400 < 0.8 x 794), rot 0, unlocked",
              re.fullmatch(r"local/[0-9a-f-]{36}\.png", d0.get("path", "")) and d0.get("nw") == 400 and d0.get("nh") == 400
              and d0.get("w") == 400 and d0.get("h") == 400 and d0.get("rot") == 0 and d0.get("locked") is False, d0)
        ex = [min(max((vis[0] + vis[2]) / 2 - 200, 0), W - 400), min(max((vis[1] + vis[3]) / 2 - 200, 0), H - 400)]
        check("centred in the part of the page she sees (the axes stamp's rule)", abs(d0["x"] - ex[0]) < 0.02 and abs(d0["y"] - ex[1]) < 0.02, [d0, vis])
        st = pg.evaluate("[window.__pw.ink.tool().tool, document.getElementById('tool-select').classList.contains('on') || document.getElementById('tool-select').getAttribute('aria-pressed')]")
        s = sel(pg)
        check("it lands selected and the tool is Select", s and s["ids"] == [ring["id"]] and st[0] == "select", [s, st])
        check("the device keeps the file at once", pg.evaluate("(p) => window.__pw.pdf.cached(p)", d0["path"]))
        ie = pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s0", ring["id"]])
        check("an SVG <image> (a Blob URL, preserveAspectRatio none) at the box, no transform at rot 0",
              ie and ie["tag"] == "image" and ie["href"] == "blob:" and ie["par"] == "none" and [ie["x"], ie["y"], ie["w"], ie["h"]] == [d0["x"], d0["y"], 400, 400] and ie["tr"] is None, ie)
        lay = pg.evaluate("window.__T.layer('s0')")
        check("the page SVG's groups: img, hl, pen (pictures at the bottom)", lay[:3] == ["img", "hl", "pen"], lay)
        undo(pg)
        check("one undo step: undo takes it off", len(imgs(pg)) == 0)
        redo(pg)
        check("redo puts it back exactly", len(imgs(pg)) == 1 and imgs(pg)[0]["data"] == d0 and imgs(pg)[0]["id"] == ring["id"])
        RID, PATH = ring["id"], d0["path"]

        # the photo: 3000 x 2000 kept at 2048 x 1365 as a JPEG; w = 0.8 x 794
        ph = add_img(pg, PHOTO) or {}; pd = ph.get("data", {})
        check("a 3000 x 2000 photo: nw 2048, nh 1365, w 635.2 (0.8 x 794), h by aspect, .jpg",
              pd.get("nw") == 2048 and pd.get("nh") == 1365 and abs(pd.get("w", 0) - 635.2) < 0.011 and abs(pd.get("h", 0) - 635.2 * 1365 / 2048) < 0.011
              and pd.get("path", "").endswith(".jpg"), pd)
        dv = pg.evaluate("(p) => window.__T.dev(p)", pd.get("path"))
        check("... the device copy is an image/jpeg of 2048 x 1365", dv == ["image/jpeg", 2048, 1365], dv)
        check("... it lands selected (alone)", sel(pg) and sel(pg)["ids"] == [ph.get("id")], sel(pg))
        undo(pg)
        sm = add_img(pg, SMALL) or {}; sd = sm.get("data", {})
        check("a 200 x 120 WebP: stored as PNG (path .png), nw 200, nh 120, w 200, h 120",
              sd.get("path", "").endswith(".png") and [sd.get(k) for k in ["nw", "nh", "w", "h"]] == [200, 120, 200, 120], sd)
        dv = pg.evaluate("(p) => window.__T.dev(p)", sd.get("path"))
        check("... the device copy is image/png", dv and dv[0] == "image/png", dv)
        check("... the twin's bucket gets it as image/png (the background upload)",
              until(pg, lambda: pg.evaluate("(p) => window.__T.twinType(p)", sd.get("path")) == "image/png", 8000))
        undo(pg)
        n0 = len(recs(pg)); pg.evaluate("window.__toastLog = []")
        pg.set_input_files("#imgInput", str(BROKEN)); pg.wait_for_timeout(600)
        tl = toasts(pg)
        check("a broken file: ONE toast 'This picture could not be opened.', no record", tl == ["This picture could not be opened."] and len(recs(pg)) == n0, [tl, len(recs(pg))])
        idle(pg)
        tw = pg.evaluate("() => window.__pw.api.strokesOf(['s0'])")
        check("the twin takes the 'image' row (it has no kind check; the database's check allows 'image')", any(r["kind"] == "image" and r["id"] == RID for r in tw), [r["kind"] for r in tw])

        # ------------------------------------------------------------ B: under the ink, see-through
        group[0] = "B. layer + see-through"
        c0 = centre(d0); band = [c0[0] - 135, c0[1]]; top = [c0[0], c0[1] - 135]; hole = [c0[0] + 30, c0[1] + 20]
        clear_sel(pg)
        tool(pg, "pen")
        zig = []
        for j in range(13):
            y = top[1] - 9 + j * 1.5
            zig += [[top[0] - 9, y], [top[0] + 9, y]] if j % 2 == 0 else [[top[0] + 9, y], [top[0] - 9, y]]
        pen(pg, zig)
        ink0 = ink_recs(pg)
        check("set-up: one pen stroke drawn over the ring's top", len(ink0) == 1 and ink0[0]["kind"] == "pen", [r["kind"] for r in recs(pg)])
        sk = ink0[0]["seq"] if ink0 else 0
        check("the picture's seq is below the stroke's here, but the group decides: the <image> is in g.img, the stroke in g.pen",
              pg.evaluate("([r, s]) => { const g = window.__T.sheet('s0').querySelector(`svg.ink [data-id='${s}']`); return !!g && g.parentNode.getAttribute('class') === 'pen' && !!window.__T.sheet('s0').querySelector(`svg.ink > g.img > g[data-id='${r}']`); }", [RID, ink0[0]["id"] if ink0 else ""]))
        px = spix(pg, [top, band, hole])
        check("on screen: the stroke's colour at a point on the ring (ink on top)", is_blue(px[0]), px[0])
        check("on screen: the ring's band is red", is_red(px[1]), px[1])
        check("on screen: SEE-THROUGH, the hole shows the paper (white or the grid line), not black or grey", is_paper(px[2]), px[2])
        until(pg, lambda: not pg.evaluate("document.getElementById('toast').classList.contains('show')"), 4000)
        pen(pg, [[d0["x"] - 30 + k * 12, c0[1] + 40 * math.sin(k / 3)] for k in range(40)])   # a wave of ink across the ring for the picture
        pg.screenshot(path=str(SHOTS / "u4c-tablet.png"))
        undo(pg)

        # ------------------------------------------------------------ C: select, move, resize, turn
        group[0] = "C. select + move + resize + turn"
        tool(pg, "select")
        pen(pg, [band]); s = sel(pg)
        check("a tap on bare picture picks it", s and s["ids"] == [RID], s)
        clear_sel(pg); pen(pg, [top]); s = sel(pg)
        check("a tap on the ink over it picks the ink (ink is on top)", s and s["ids"] == [ink0[0]["id"]], s)
        clear_sel(pg)
        pen(pg, [[d0["x"] - 30, c0[1] - 20], [d0["x"] + 30, c0[1] + 20]]); s = sel(pg)
        check("a box across its left edge picks it", s and s["ids"] == [RID], s)
        clear_sel(pg)
        pen(pg, [[c0[0] - 40, c0[1] + 40], [c0[0] + 40, c0[1] + 80]]); s = sel(pg)
        check("a box inside the picture (its hole, no edge) picks it too: the box touches the picture", s and s["ids"] == [RID], s)
        pen(pg, [band]); before = imgs(pg)[0]
        mv = addv(band, [0, 50])
        pen(pg, [mv, addv(mv, [20, 15]), addv(mv, [40, 30])])
        a1 = imgs(pg)[0]; d1 = a1["data"]
        check("a pen drag inside the box moves it: x + 40, y + 30; w, h, rot, nw, nh, path the same",
              abs(d1["x"] - d0["x"] - 40) < 0.011 and abs(d1["y"] - d0["y"] - 30) < 0.011 and [d1[k] for k in ["w", "h", "rot", "nw", "nh", "path", "locked"]]
              == [d0[k] for k in ["w", "h", "rot", "nw", "nh", "path", "locked"]], [d0, d1])
        ie = pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s0", RID])
        check("... the <image> follows", ie and abs(ie["x"] - d1["x"]) < 0.01 and abs(ie["y"] - d1["y"]) < 0.01, ie)
        undo(pg)
        check("one undo step: undo restores the exact data", imgs(pg)[0]["data"] == d0, imgs(pg)[0]["data"])
        redo(pg)
        check("redo moves it again", imgs(pg)[0]["data"] == d1)
        if not sel(pg): pen(pg, [addv(band, [40, 30])])
        zz = z(pg); sb = sel(pg)["box"]; pad = 4 / zz
        o, c = [sb[0] - pad, sb[1] - pad], [sb[2] + pad, sb[3] + pad]
        u = [c[0] - o[0], c[1] - o[1]]; L = math.hypot(*u); u = [u[0] / L, u[1] / L]
        stp = addv(c, [u[0] * 5 / zz, u[1] * 5 / zz]); sc = 1.25
        pen(pg, [stp, addv(stp, [(c[0] - o[0]) * (sc - 1) / 2, (c[1] - o[1]) * (sc - 1) / 2]), addv(stp, [(c[0] - o[0]) * (sc - 1), (c[1] - o[1]) * (sc - 1)])])
        d2 = imgs(pg)[0]["data"]
        check("a corner drag scales it: w / h ratio kept within 0.5 %, w about 1.25 x, nw and nh untouched",
              abs((d2["w"] / d2["h"]) / (d1["w"] / d1["h"]) - 1) < 0.005 and abs(d2["w"] / d1["w"] - sc) < 0.02 and d2["nw"] == 400 and d2["nh"] == 400, [d1, d2])
        undo(pg)
        check("one undo step: undo restores the exact data", imgs(pg)[0]["data"] == d1, imgs(pg)[0]["data"])
        redo(pg); check("redo scales it again", imgs(pg)[0]["data"] == d2)
        undo(pg)
        if not sel(pg): pen(pg, [addv(band, [40, 30])])
        turn_sel(pg, 52)
        d3 = imgs(pg)[0]["data"]
        check("the ring turns it: 52 degrees on the ring (7 off 45, no snap) is rot 52, about the box's centre",
              abs(d3["rot"] - 52) < 0.6 and abs(centre(d3)[0] - centre(d1)[0]) < 0.05 and abs(centre(d3)[1] - centre(d1)[1]) < 0.05, d3)
        undo(pg)
        if not sel(pg): pen(pg, [addv(band, [40, 30])])
        turn_sel(pg, 61)
        d3 = imgs(pg)[0]["data"]
        check("the ring turns it: 61 degrees snaps to rot 60; the box's centre stays; w, h kept", d3["rot"] == 60 and d3["w"] == d1["w"] and d3["h"] == d1["h"]
              and dist(centre(d3), centre(d1)) < 0.05, d3)
        ie = pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s0", RID])
        check("... drawn as rotate(60 cx cy) on the <image>", ie and ie["tr"] and ie["tr"].startswith("rotate(60 "), ie)
        undo(pg)
        check("one undo step: undo restores the exact data", imgs(pg)[0]["data"] == d1, imgs(pg)[0]["data"])
        # a mixed selection (the stroke and the picture): the picture turns about the SELECTION's centre
        pg.evaluate("window.__pw.ink.selectAll('s0')"); pg.wait_for_timeout(40)
        check("set-up: Select all takes the stroke and the picture", sorted(sel(pg)["ids"]) == sorted([RID, ink0[0]["id"]]), sel(pg))
        cc = turn_sel(pg, 90)
        d4 = imgs(pg)[0]["data"]
        check("a mixed turn of 90: rot 90 and the picture's centre turned about the selection's centre", d4["rot"] == 90
              and dist(centre(d4), rotate(centre(d1), cc, 90)) < 0.1, [d4, rotate(centre(d1), cc, 90)])
        undo(pg)
        check("undo: the exact data again", imgs(pg)[0]["data"] == d1, imgs(pg)[0]["data"])
        check("handles(): none for a picture", pg.evaluate("(r) => window.__pw.ink.handles(r).length", imgs(pg)[0]) == 0)

        # ------------------------------------------------------------ D: the clipboards carry the same path
        group[0] = "D. copy, cut, paste, delete"
        clear_sel(pg)
        c1 = centre(d1); band1 = [c1[0] - 135, c1[1]]
        pen(pg, [band1])
        check("set-up: the picture alone is selected; chips Copy, Cut, Duplicate, Delete, Lock (pw-v9e: then Cut out)",
              [x[0] for x in chips(pg)] == ["copy", "cut", "duplicate", "delete", "lock", "cutout", "crop"] and chips(pg)[-3][1] == "Lock", chips(pg))
        pg.click(".selChips .chip[data-act='copy']"); pg.wait_for_timeout(40)
        pg.evaluate("window.__pw.ink.pasteAt('s1', 397, 500)"); pg.wait_for_timeout(60)
        p1 = imgs(pg, "s1")
        check("Copy, then Paste on page 2: a picture there with the same path, a new id, its size kept",
              len(p1) == 1 and p1[0]["data"]["path"] == PATH and p1[0]["id"] != RID and p1[0]["data"]["w"] == 400, p1)
        undo(pg)
        check("undo takes the paste away", imgs(pg, "s1") == [])
        clear_sel(pg); pen(pg, [band1])
        pg.click(".selChips .chip[data-act='duplicate']"); pg.wait_for_timeout(60)
        two = imgs(pg)
        check("Duplicate: two pictures with the same path, the copy 24 px right and down, selected", len(two) == 2 and all(r["data"]["path"] == PATH for r in two)
              and sel(pg)["ids"] == [two[-1]["id"]] and abs(two[-1]["data"]["x"] - d1["x"] - 24) < 0.02, [r["data"] for r in two])
        undo(pg)
        clear_sel(pg); pen(pg, [band1])
        pg.click(".selChips .chip[data-act='cut']"); pg.wait_for_timeout(60)
        check("Cut: the picture comes off the page", imgs(pg) == [])
        pg.evaluate("([x, y]) => window.__pw.ink.pasteAt('s0', x, y)", c1); pg.wait_for_timeout(60)
        pc = imgs(pg)
        check("... Paste puts it back with the same path and data (a new id)", len(pc) == 1 and pc[0]["data"]["path"] == PATH and pc[0]["id"] != RID
              and abs(pc[0]["data"]["x"] - d1["x"]) < 0.02 and abs(pc[0]["data"]["y"] - d1["y"]) < 0.02, pc)
        undo(pg); undo(pg)
        check("two undos: the original record is back", len(imgs(pg)) == 1 and imgs(pg)[0]["id"] == RID and imgs(pg)[0]["data"] == d1, imgs(pg))
        until(pg, lambda: pg.evaluate("window.__pw.pdf.uploadsPending()") == 0, 8000)
        clear_sel(pg); pen(pg, [band1])
        pg.click(".selChips .chip[data-act='delete']"); pg.wait_for_timeout(60)
        lst = pg.evaluate("window.__pw.api.importsList()")
        check("Delete removes the record only: the page has no picture, the twin's bucket still has the file",
              imgs(pg) == [] and PATH in lst and len(ink_recs(pg)) == 1, [len(imgs(pg)), PATH in lst])
        undo(pg)
        check("undo brings it back", len(imgs(pg)) == 1 and imgs(pg)[0]["id"] == RID)
        thumb_menu(pg, 1, "Copy"); thumb_menu(pg, 1, "Paste")
        pages = pg.evaluate("window.__pw.S.pages.filter(p => p.note_id === 'n1' && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => p.id)")
        np_ = pages[1] if len(pages) == 4 else None
        pi = imgs(pg, np_) if np_ else []
        check("page Copy, then Paste: the new page 2 carries the picture, same path and box", len(pages) == 4 and len(pi) == 1 and pi[0]["data"]["path"] == PATH
              and pi[0]["data"]["x"] == d1["x"], [pages, pi])
        close_list(pg); undo(pg)
        check("undo takes the pasted page away", len(pg.evaluate("window.__pw.S.pages.filter(p => p.note_id === 'n1' && !p.deleted_at)")) == 3)

        # ------------------------------------------------------------ E: lock
        group[0] = "E. lock"
        tool(pg, "select"); clear_sel(pg)
        pen(pg, [top]); s = sel(pg)
        check("the padlock chip shows only with a picture in the selection (the stroke alone: no padlock)", s and s["ids"] == [ink0[0]["id"]] and "lock" not in [x[0] for x in chips(pg)], [s, chips(pg)])
        clear_sel(pg); pen(pg, [band1])
        check("with the picture selected it reads Lock", ["lock", "Lock"] in chips(pg), chips(pg))
        pg.click(".selChips .chip[data-act='lock']"); pg.wait_for_timeout(60)
        check("a tap locks it (locked true, nothing else changes)", imgs(pg)[0]["data"] == {**d1, "locked": True}, imgs(pg)[0]["data"])
        check("the chip now reads Unlock; the chips are Delete and Unlock only", chips(pg) == [["delete", "Delete"], ["lock", "Unlock"]], chips(pg))
        check("no corner handles and no turn ring while locked", parts(pg) == [0, 0], parts(pg))
        undo(pg)
        check("lock is one undo step (undo: unlocked)", imgs(pg)[0]["data"]["locked"] is False)
        redo(pg)
        check("redo: locked again", imgs(pg)[0]["data"]["locked"] is True)
        clear_sel(pg)
        pen(pg, [[d1["x"] - 30, d1["y"] - 30], [d1["x"] + d1["w"] + 30, d1["y"] + d1["h"] + 30]]); s = sel(pg)
        check("locked: a box over the whole picture selects only the ink on it", s and s["ids"] == [ink0[0]["id"]], s)
        clear_sel(pg)
        pg.evaluate("window.__pw.ink.selectAll('s0')"); s = sel(pg)
        check("locked: Select all takes the ink and leaves the picture", s and s["ids"] == [ink0[0]["id"]], s)
        clear_sel(pg)
        pen(pg, [band1]); s = sel(pg)
        check("locked: a tap on bare picture selects it alone", s and s["ids"] == [RID], s)
        check("... no .selh corners, no .selrot ring; chips Delete + Unlock", parts(pg) == [0, 0] and [x[0] for x in chips(pg)] == ["delete", "lock"], [parts(pg), chips(pg)])
        lk = imgs(pg)[0]
        pen(pg, [addv(band1, [10, 40]), addv(band1, [40, 60]), addv(band1, [80, 90])])
        check("locked: a drag inside does not move it (data and seq the same)", imgs(pg)[0] == lk, imgs(pg)[0]["data"])
        check("... and it stays selected", sel(pg) and sel(pg)["ids"] == [RID], sel(pg))
        pg.click(".selChips .chip[data-act='lock']"); pg.wait_for_timeout(60)
        check("Unlock: locked false, the corners and the ring come back at once, the five chips (pw-v9e: and Cut out)", imgs(pg)[0]["data"]["locked"] is False and parts(pg) == [4, 1]
              and [x[0] for x in chips(pg)] == ["copy", "cut", "duplicate", "delete", "lock", "cutout", "crop"] and chips(pg)[-3][1] == "Lock", [parts(pg), chips(pg)])
        undo(pg)
        check("unlock is one undo step (undo: locked again)", imgs(pg)[0]["data"]["locked"] is True)
        redo(pg)
        check("redo: unlocked", imgs(pg)[0]["data"] == d1, imgs(pg)[0]["data"])

        # ------------------------------------------------------------ F: erasers and restyle never touch it
        group[0] = "F. erasers + restyle"
        clear_sel(pg)
        pic = imgs(pg)[0]; stk = ink_recs(pg)
        line = [[d1["x"] - 20, top[1] + 30], [d1["x"] + d1["w"] / 2, top[1] + 30], [d1["x"] + d1["w"] + 20, top[1] + 30]]
        line = [[x, top[1]] for x, _ in line]
        tool(pg, "eraser"); pen(pg, line)
        check("the stroke eraser dragged across the picture removes the stroke on it and leaves the picture", ink_recs(pg) == [] and imgs(pg) == [pic], [len(ink_recs(pg)), len(imgs(pg))])
        undo(pg); check("undo: the stroke is back", ink_recs(pg) == stk)
        tool(pg, "area"); pen(pg, line)
        ia = ink_recs(pg)
        check("the area eraser cuts the stroke and leaves the picture whole", stk[0]["id"] not in [r["id"] for r in ia] and imgs(pg) == [pic], [len(ia), imgs(pg) == [pic]])
        undo(pg); check("undo: the stroke is back", ink_recs(pg) == stk)
        cols = pg.evaluate("[...document.querySelectorAll('#tray .sw')].map(b => b.dataset.colour)")
        other = next((c_ for c_ in cols if c_.upper() not in (BLUE, "#000000") and c_.upper()[1:3] < "80"), cols[-1])
        tool(pg, "restyle"); pg.click(f'#tray .sw[data-colour="{other}"]'); pg.wait_for_timeout(40)
        pen(pg, line)
        rs = ink_recs(pg)
        check("restyle changes the stroke's colour and leaves the picture", rs and rs[0]["style"]["colour"].lower() == other.lower() and imgs(pg) == [pic], [rs[0]["style"] if rs else None, other])
        undo(pg); check("undo: the stroke's own colour", ink_recs(pg) == stk)
        tool(pg, "select"); pg.evaluate("window.__pw.ink.selectAll('s0')"); pg.wait_for_timeout(40)
        pg.click(f'#tray .sw[data-colour="{other}"]'); pg.wait_for_timeout(60)
        check("Select all + the tray's recolour: the stroke recoloured, the picture untouched (style and data)",
              ink_recs(pg)[0]["style"]["colour"].lower() == other.lower() and imgs(pg)[0]["style"] == pic["style"] and imgs(pg)[0]["data"] == pic["data"], [ink_recs(pg)[0]["style"], imgs(pg)[0]["style"]])
        undo(pg); clear_sel(pg)
        check("set-up back: the stroke blue again", ink_recs(pg) == stk)
        pg.evaluate("window.__pw.ink.restyleSelection && 0")
        thumb_menu(pg, 1, "Erase page")
        check("page Erase takes the ink and leaves the picture", ink_recs(pg) == [] and imgs(pg) == [pic], [len(ink_recs(pg)), len(imgs(pg))])
        close_list(pg); undo(pg)
        check("undo: the ink is back", ink_recs(pg) == stk)
        tool(pg, "pen"); pg.click(f'#tray .sw[data-colour="{BLUE}"]'); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ G: everywhere a page is pictured
        group[0] = "G. thumbs, card, picture, share"
        c1 = centre(d1); band1 = [c1[0] - 135, c1[1]]; top1 = [c1[0], c1[1] - 135]; hole1 = [c1[0] + 30, c1[1] + 20]
        open_list(pg)
        th = pg.evaluate("() => { const t = document.querySelector(`#plThumbs .thumbP[data-index='1'] .paper > svg.thumbInk`); if (!t) return null; return [...t.children].map((c) => c.getAttribute('class')).concat([t.querySelector('g.img > g > image') ? t.querySelector('g.img > g > image').getAttribute('href').slice(0, 5) : null]); }")
        check("the page list thumb: g.img, hl, pen, the <image> with a Blob URL", th == ["img", "hl", "pen", "blob:"], th)
        pg.wait_for_timeout(500)                                   # the list's slide-in is over
        bb = thumb(pg, 1).locator(".paper").bounding_box()
        tim = shot(pg).crop((int(bb["x"]), int(bb["y"]), int(bb["x"] + bb["width"]), int(bb["y"] + bb["height"])))
        fx = lambda p: (int(p[0] / W * bb["width"]), int(p[1] / H * bb["height"]))
        check("... pixels: red inside the thumb's paper where the ring's band is", red_count(tim) > 30 and is_red(tim.getpixel(fx(band1))), [red_count(tim), tim.getpixel(fx(band1))])
        tim.save(str(SHOTS / "u4c-thumb.png"))
        close_list(pg)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(150)
        pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^Pictures$"))).first.click(); pg.wait_for_timeout(250)
        cd = pg.locator("#grid .card[data-id='n1'] .paper")
        cb = cd.bounding_box()
        cim = shot(pg).crop((int(cb["x"]), int(cb["y"]), int(cb["x"] + cb["width"]), int(cb["y"] + cb["height"])))
        has_img = pg.evaluate("!!document.querySelector(`#grid .card[data-id='n1'] .paper svg.thumbInk g.img image`)")
        check("the note card shows it (its <image>, red pixels inside the card's paper)", has_img and red_count(cim) > 30, [has_img, red_count(cim)])
        pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
        pg.evaluate(HELP)
        ok = until(pg, lambda: "local/s0.webp" in pg.evaluate("window.__pw.api.storageList()") and not pg.evaluate("window.__pw.snap()")["due"]
                   and not pg.evaluate("window.__pw.snap()")["running"], 15000)
        pp = pg.evaluate("""async ([b, h]) => { const blob = await window.__pw.api.getSnapshot('local/s0.webp'), bm = await createImageBitmap(blob);
          const c = document.createElement('canvas'); c.width = bm.width; c.height = bm.height; const g = c.getContext('2d'); g.drawImage(bm, 0, 0);
          const at = (p) => [...g.getImageData(Math.round(p[0]), Math.round(p[1]), 1, 1).data.slice(0, 3)]; return [bm.width, at(b), at(h)]; }""", [band1, hole1])
        check("the U3b page picture (snap.js, 1x) contains it: red on the band, the paper in the hole", ok and pp[0] == W and is_red(pp[1]) and is_paper(pp[2]), [ok, pp])
        thumb_menu(pg, 1, "Share page"); pg.wait_for_selector("#shareDlg")
        pg.click("#shareDlg button[data-share='images']"); pg.wait_for_selector("#shareReady", timeout=30000)
        pg.evaluate("window.__shared = null"); pg.click("#shareDlg button[data-share='send']")
        pg.wait_for_function("window.__shared", timeout=10000); pg.wait_for_timeout(60)
        sh = pg.evaluate("async () => { const f = window.__shared.files[0]; return [f.type, await window.__T.b64(f)]; }")
        sim = Image.open(io.BytesIO(base64.b64decode(sh[1]))).convert("RGB")
        g2 = lambda p: sim.getpixel((int(p[0] * 2), int(p[1] * 2)))
        check("Share as images: the PNG (2x) has the ring (red band), the ink over it (blue) and the paper in its hole (see-through)",
              sh[0] == "image/png" and sim.size == (W * 2, H * 2) and is_red(g2(band1)) and is_blue(g2(top)) and is_paper(g2(hole1)), [sim.size, g2(band1), g2(top), g2(hole1)])
        close_list(pg)

        # ------------------------------------------------------------ H: the PDF export
        group[0] = "H. PDF"
        def pdf_case(rot):
            doc = pdf_of(pg); r = pdf_img_bbox(doc); d_ = imgs(pg)[0]["data"]; cx, cy = centre(d_)
            t = math.radians(rot); bw = abs(d_["w"] * math.cos(t)) + abs(d_["h"] * math.sin(t)); bh = abs(d_["w"] * math.sin(t)) + abs(d_["h"] * math.cos(t))
            ok_ = r is not None and abs((r.x0 + r.x1) / 2 - cx * K) < 1 and abs((r.y0 + r.y1) / 2 - cy * K) < 1 and abs(r.width - bw * K) < 1 and abs(r.height - bh * K) < 1
            return ok_, doc, [list(r) if r else None, [cx * K, cy * K, bw * K, bh * K]]
        ok, doc, info = pdf_case(0)
        check("rot 0: the picture's bbox in the PDF is the box (centre and size within 1 pt)", ok, info)
        pm = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2)); pim = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
        f2 = lambda p: pim.getpixel((int(p[0] * K * 2), int(p[1] * K * 2)))
        check("rot 0: the PDF keeps the PNG's alpha (the hole shows the paper), the band is red, the ink sits on top (blue)",
              is_paper(f2(hole1)) and is_red(f2(band1)) and is_blue(f2(top)), [f2(hole1), f2(band1), f2(top)])
        smask = [i for i in doc[0].get_images(full=True) if i[2] == 400]
        check("... the image has an SMask (pdf-lib's alpha)", smask and smask[0][1] > 0, smask)
        tool(pg, "select"); clear_sel(pg); pen(pg, [band1])
        turn_sel(pg, 90)
        ok, doc, info = pdf_case(90)
        check("rot 90: the bbox centre is where the page shows it, its size turned (within 1 pt)", imgs(pg)[0]["data"]["rot"] == 90 and ok, info)
        undo(pg); clear_sel(pg); pen(pg, [band1])
        turn_sel(pg, 30)
        ok, doc, info = pdf_case(30)
        check("rot 30: the bbox centre is where the page shows it, its turned bbox's size (within 1 pt)", imgs(pg)[0]["data"]["rot"] == 30 and ok, info)
        pm = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2)); pim = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
        b30 = rotate(band1, c1, 30)
        check("rot 30: the band's turned point is red in the PDF, the hole still the paper", is_red(f2(b30)) and is_paper(f2(hole1)), [f2(b30), f2(hole1)])
        undo(pg); clear_sel(pg)
        check("undo: rot 0 again", imgs(pg)[0]["data"] == d1)

        # ------------------------------------------------------------ I: zoom 3, three pictures, the frames
        group[0] = "I. zoom + frames"
        tool(pg, "pen")
        add_img(pg, PHOTO); clear_sel(pg)
        add_img(pg, RING); clear_sel(pg)
        tool(pg, "pen")
        check("set-up: three pictures on page 1 (one a 2048 px photo)", len(imgs(pg)) == 3, len(imgs(pg)))
        phd = next((r["data"] for r in imgs(pg) if r["data"]["path"].endswith(".jpg")), None)
        doc = pdf_of(pg)
        jinfo = [i for i in doc[0].get_image_info() if i["width"] == 2048 and i["height"] == 1365]
        jr = fitz.Rect(jinfo[0]["bbox"]) if jinfo else None
        pm = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2)); pim = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
        jb = [phd["x"] + 0.22 * phd["w"], phd["y"] + 0.22 * phd["h"]] if phd else [0, 0]
        check("the PDF takes the JPEG photo too (embedJpg, 2048 x 1365) at its box, its blue block where the page has it",
              jr is not None and abs(jr.x0 - phd["x"] * K) < 1 and abs(jr.y0 - phd["y"] * K) < 1 and abs(jr.width - phd["w"] * K) < 1
              and is_blue(pim.getpixel((int(jb[0] * K * 2), int(jb[1] * K * 2)))), [list(jr) if jr else None, phd])
        pg.evaluate("""() => { const d = document.getElementById('desk'), r = d.getBoundingClientRect(), z = window.__T.z();
          d.dispatchEvent(new WheelEvent('wheel', { deltaY: -Math.log(3 / z) / 0.0025, ctrlKey: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, bubbles: true, cancelable: true })); }""")
        pg.wait_for_timeout(300)
        zz = z(pg)
        fr = pg.evaluate("""async (n) => { const d = document.getElementById('desk'), r = d.getBoundingClientRect(), ts = [];
          for (let k = 0; k < n; k++) { await new Promise(requestAnimationFrame); ts.push(performance.now());
            d.dispatchEvent(new WheelEvent('wheel', { deltaY: k < n / 2 ? 30 : -30, deltaX: k % 20 < 10 ? 12 : -12, clientX: r.left + 300, clientY: r.top + 300, bubbles: true, cancelable: true })); }
          return ts; }""", 120)
        gaps = [round(fr[i] - fr[i - 1], 1) for i in range(2, len(fr))]
        check(f"zoom 3 (got {zz:.2f}): panning a page with three pictures, no frame gap over {FRAME_MS} ms", abs(zz - 3) < 0.05 and gaps and max(gaps) < FRAME_MS, [zz, max(gaps) if gaps else None, sorted(gaps)[-5:]])
        pg.screenshot(path=str(SHOTS / "u4c-zoom3.png"))
        rnid = pg.evaluate("window.__pw.S.openNote")
        pg.reload(); ready(pg)                              # pw-v8y: a reload opens on All notes; the note opens from its card
        pg.locator(f"#grid .card[data-id='{rnid}']").click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(300); pg.evaluate(HELP)
        ies = [pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s0", r["id"]]) for r in imgs(pg)]
        check("after a reload: all three pictures drawn from the device copy (Blob URLs)", len(ies) == 3 and all(e and e["tag"] == "image" and e["href"] == "blob:" for e in ies), ies)
        check("no page errors (tablet)", not errs, errs)

        # ------------------------------------------------------------ J: offline, then the phone
        group[0] = "J. offline + phone"
        pg.evaluate("window.__P.scrollToPage(2)"); pg.wait_for_timeout(400)
        check("set-up: page 3 is the current page", pg.evaluate("window.__pw.S.cur") == 2, pg.evaluate("window.__pw.S.cur"))
        idle(pg)
        offline(pg)
        off = add_img(pg, SMALL, "s2") or {}; op = off.get("data", {}).get("path")
        check("offline: the picture lands on page 3 and shows (its <image>)", op and (pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s2", off.get("id")]) or {}).get("tag") == "image", off)
        check("offline: its file waits to upload", pg.evaluate("window.__pw.pdf.uploadsPending()") == 1, pg.evaluate("window.__pw.pdf.uploadsPending()"))
        pg.wait_for_timeout(300)
        rnid = pg.evaluate("window.__pw.S.openNote")
        pg.reload(); ready(pg)                              # pw-v8y: a reload opens on All notes; the note opens from its card
        pg.locator(f"#grid .card[data-id='{rnid}']").click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(400); pg.evaluate(HELP)
        ie = pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s2", off.get("id")])
        check("offline reload: the picture is still there and shows (the device copy)", until(pg, lambda: (pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s2", off.get("id")]) or {}).get("tag") == "image", 4000),
              pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s2", off.get("id")]))
        online(pg)
        def landed():
            tw_ = pg.evaluate("() => window.__pw.api.strokesOf(['s2'])")
            return pg.evaluate("window.__pw.pdf.uploadsPending()") == 0 and op in pg.evaluate("window.__pw.api.importsList()") and any(r["id"] == off.get("id") for r in tw_)
        check("online again: the twin has the file (uploaded) and the record", until(pg, landed, 10000))
        check("... as image/png", pg.evaluate("(p) => window.__T.twinType(p)", op) == "image/png")
        tw_all = pg.evaluate(TWIN_JS)
        blob64 = b64file(SMALL)
        ctx2 = b.new_context(viewport={"width": 1280, "height": 800})
        p2 = ctx2.new_page(); e2 = []
        p2.on("pageerror", lambda e: e2.append(str(e)))
        p2.goto(LOCAL); ready(p2)
        p2.evaluate("(d) => { localStorage.clear(); localStorage.setItem('penworks.local.v2', JSON.stringify(d)); }", tw_all)
        p2.reload(); ready(p2); open_note(p2); p2.evaluate(HELP)
        w0 = p2.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s2", off.get("id")])
        check("the phone (no device copy, the bucket does not have it yet): the wait rectangle (rect.imgWait) at the box",
              w0 and w0["tag"] == "rect" and w0["cls"] == "imgWait" and abs(w0["w"] - off["data"]["w"]) < 0.01, w0)
        # the tablet's copy of the file reaches the phone's bucket (the twin is per browser): the bytes as they were kept
        dev = pg.evaluate("async (p) => window.__T.b64(await window.__PI.bytesOf(p))", op)
        p2.evaluate("async ([p, b]) => { const s = atob(b), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); await window.__pw.api.putImport(p, new Blob([u], { type: 'image/png' })); }", [op, dev])
        check("... then the picture once getImport answers (the retry, 2 to 5 s)", until(p2, lambda: (p2.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s2", off.get("id")]) or {}).get("tag") == "image", 15000),
              p2.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s2", off.get("id")]))
        check("... and keeps it", p2.evaluate("(p) => window.__pw.pdf.cached(p)", op))
        # the live mirror: a picture row from the other device (the tablet's ring, a path the phone has not got) arrives
        row = {**imgs(pg)[0], "id": "live-pic-1", "page_id": "s1", "seq": 99}
        p2.evaluate("(r) => window.__pw.api.emitStroke('INSERT', r)", row); p2.wait_for_timeout(300)
        lw = p2.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s1", "live-pic-1"])
        check("the live mirror: a picture row from the other device appears with the wait rectangle", lw and lw["tag"] == "rect", lw)
        ring64 = pg.evaluate("async (p) => window.__T.b64(await window.__PI.bytesOf(p))", PATH)
        p2.evaluate("async ([p, b]) => { const s = atob(b), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); await window.__pw.api.putImport(p, new Blob([u], { type: 'image/png' })); }", [PATH, ring64])
        check("... then the picture", until(p2, lambda: (p2.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s1", "live-pic-1"]) or {}).get("tag") == "image", 15000),
              p2.evaluate("([s, r]) => window.__T.imgEl(s, r)", ["s1", "live-pic-1"]))
        check("no page errors (phone)", not e2, e2)
        ctx2.close()
        check("no page errors (the whole run)", not errs, errs)
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        check("cache is pw-v9g", "pw-v9g" in keys, keys)

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
