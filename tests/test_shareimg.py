# PenWorks pw-v9d checks: a picture shared to PenWorks (WhatsApp's share button) lands the way a shared PDF does
# (_build/SHAREIMG-BRIEF.md). Headless Playwright (Python), the harness of tests/test_u4b.py: a share is a real multipart
# POST to ./share-target/?local=1 sent by a form in the app's page, so it goes through the registered service worker
# exactly as Android's share sheet does. The pictures and the PDF are made here (Pillow, PyMuPDF): no photo is committed.
# Run: python -E -P tests/test_shareimg.py     (local mode only: ?local=1, the localStorage twin stands in for Supabase)
# What it proves: the manifest's second files entry (image) with the pdf entry untouched; sw.js keeps every shared PDF and
# picture as a list in the form's order (one, three, a PDF, a mix; a text-only or other-file share keeps nothing and the app
# says so); one picture, New note in Loose: ONE new note with New note's name, one page, its picture at most 0.8 of the
# page's width, centred across with its top the same gap as its sides, the note open on it, the picture selected with the
# Select tool on, not an undo step; three pictures, Add to a note: three pages at the END in share order, the note open on
# the first; a PDF through the new code as before; a mix in form order; Cancel and Escape drop the whole list, ?share=1
# leaves the address; the PDF export of a new picture page carries the picture; a JPEG with an EXIF turn is stored upright
# and a WebP as a PNG; a value from before pw-v9d is read as a list of one; the ten-minute rule drops an old list.
# Screenshots go to _build/shareimg/shots/.
import sys, subprocess, time, pathlib, re, json, base64, io
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8827
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = ROOT / "_build" / "shareimg" / "shots"
W, H = 794, 1123
PDF_ENTRY = '{ "name": "pdf", "accept": ["application/pdf", ".pdf"] }'
IMG_ENTRY = {"name": "image", "accept": ["image/png", "image/jpeg", "image/webp", ".png", ".jpg", ".jpeg", ".webp"]}
# the manifest as it was at pw-v9c, its share_target's files list aside: nothing else may change
OLD_MANIFEST = {
    "name": "PenWorks", "short_name": "PenWorks", "description": "Folders, notes and A4 pages for the S Pen", "start_url": "./", "scope": "./",
    "display": "fullscreen", "display_override": ["fullscreen", "standalone"], "orientation": "any", "background_color": "#E8E6E1",
    "theme_color": "#262A30",
    "share_target": {"action": "./share-target/", "method": "POST", "enctype": "multipart/form-data", "params": {"title": "title", "text": "text"}},
    "icons": [{"src": "./icons/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "./icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
              {"src": "./icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}

# ---------------------------------------------------------------- the files, made here
def enc(im, fmt, **kw):
    b = io.BytesIO(); im.save(b, fmt, **kw); return b.getvalue()
def block(w, h, bg, fg, box):
    im = Image.new("RGB", (w, h), bg); ImageDraw.Draw(im).rectangle(box, fill=fg); return im
BIG = enc(block(1600, 1200, (240, 240, 240), (30, 60, 200), [200, 150, 799, 599]), "PNG")       # wider than 0.8 x the page
P1 = enc(block(300, 200, (255, 255, 255), (220, 30, 30), [0, 0, 99, 79]), "PNG")
P2 = enc(block(200, 300, (255, 255, 255), (30, 160, 60), [0, 0, 79, 99]), "JPEG", quality=92)
P3 = enc(Image.new("RGBA", (400, 100), (40, 80, 220, 255)), "WEBP", lossless=True)
SMALL_WEBP = enc(Image.new("RGBA", (200, 120), (40, 160, 60, 255)), "WEBP", lossless=True)
# a phone photo stored on its side: 300 x 200 as stored, EXIF orientation 6 (turn 90 degrees clockwise to view); the red
# block at the stored top-left is at the TOP-RIGHT once upright
_raw = block(300, 200, (255, 255, 255), (220, 30, 30), [0, 0, 59, 39]); _ex = Image.Exif(); _ex[0x0112] = 6
EXIF_JPG = enc(_raw, "JPEG", quality=95, exif=_ex.tobytes())
def make_pdf(n):
    d = fitz.open()
    for k in range(n):
        p = d.new_page(width=595.28, height=841.89); p.insert_text((72, 100), f"Shared page {k + 1}", fontsize=24)
    return d.tobytes()
PDF2 = make_pdf(2)
b64 = lambda by: base64.b64encode(by).decode()

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

INIT = """
  window.__toastLog = [];
  addEventListener('DOMContentLoaded', () => { const t = document.getElementById('toast');
    if (t) new MutationObserver(() => window.__toastLog.push(t.textContent)).observe(t, { childList: true, characterData: true, subtree: true }); });
"""
SEED_JS = """() => {
  localStorage.clear();
  const P = (id, nid, pos, t) => ({ id, note_id: nid, position: pos, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Maths', colour: null, position: 0, deleted_at: null, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-01T10:00:00Z' }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Base', pinned: false, cover_path: null, deleted_at: null, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-05T10:00:00Z' },
            { id: 'n2', folder_id: null, name: 'Older', pinned: false, cover_path: null, deleted_at: null, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-02T10:00:00Z' }],
    pages: [P('q1', 'n1', 0, '2026-11-05T10:00:00Z'), P('q2', 'n1', 1, '2026-11-05T10:00:00Z'), P('q3', 'n2', 0, '2026-11-02T10:00:00Z')] }));
}"""
# a real share: a multipart POST to the share-target action. items = [[field, name, type, b64], ...] in form order; a run of
# the same field is ONE file input holding several files (as Chrome sends a multi-picture share); a caption as WhatsApp may
SHARE_JS = """(items) => {
  const f = document.createElement('form');
  f.method = 'POST'; f.enctype = 'multipart/form-data'; f.action = './share-target/?local=1';
  let inp = null, dt = null, field = null;
  const done = () => { if (inp) { inp.files = dt.files; f.append(inp); } };
  for (const [fld, name, type, b] of items) {
    if (fld !== field) { done(); inp = document.createElement('input'); inp.type = 'file'; inp.name = fld; inp.multiple = true; dt = new DataTransfer(); field = fld; }
    const s = atob(b), u = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    dt.items.add(new File([u], name, { type }));
  }
  done();
  const t = document.createElement('input'); t.name = 'title'; t.value = 'From WhatsApp';
  const x = document.createElement('input'); x.name = 'text'; x.value = 'a caption';
  f.append(t, x); document.body.append(f); f.submit(); return 1; }"""
HELP = """() => {
  const T = window.__T = {};
  T.b64 = async (blob) => { const u = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
  T.dev = async (path) => { const m = await import('./js/pdfin.js'), b = await m.bytesOf(path); return b ? { type: b.type, b64: await T.b64(b) } : null; };
  T.imgs = (id) => window.__pw.ink.strokesOf(id).filter((r) => r.kind === 'image');
  T.imgEl = (sid, rid) => { const g = document.querySelector(`#stack .sheet[data-id="${sid}"] svg.ink > g.img > g[data-id="${rid}"]`);
    const e = g && g.firstElementChild; return e ? { tag: e.tagName, href: (e.getAttribute('href') || '').slice(0, 5) } : null; };
  T.pdf = async (pid) => { const m = await import('./js/pdfout.js'), p = window.__pw.S.pages.find((x) => x.id === pid);
    return T.b64(await m.buildPdf([p], 'shareimg')); };
  T.put = async (v) => { const db = await new Promise((ok, bad) => { const r = indexedDB.open('penworks.share', 1);
      r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains('files')) r.result.createObjectStore('files'); };
      r.onsuccess = () => ok(r.result); r.onerror = () => bad(r.error); });
    await new Promise((ok, bad) => { const t = db.transaction(['files'], 'readwrite'); t.objectStore('files').put(v, 'pending'); t.oncomplete = ok; t.onerror = () => bad(t.error); });
    db.close(); return 1; };
  T.blob = (b, type) => { const s = atob(b), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return new Blob([u], { type }); };
  return 1;
}"""
ROWS_JS = """(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at && p.kind !== 'sticky').sort((a, b) => a.position - b.position)
  .map(p => ({ id: p.id, position: p.position, pdf_path: p.pdf_path || null, pdf_page: p.pdf_page ?? null, background: p.background, orientation: p.orientation }))"""
COUNTS_JS = "[window.__pw.S.notes.length, window.__pw.S.pages.length, window.__pw.treeq.length()]"
# the twin's notes, pages and strokes without the page pictures' stamps (js/snap.js writes those in the background, a few
# seconds after a page changes or at a start: they are not what a Cancel could change)
TWIN_JS = """() => { const t = JSON.parse(localStorage.getItem('penworks.local.v2')), drop = ['snapshot_path', 'snapshot_at', 'cover_path', 'updated_at'];
  const bare = (rows) => rows.map((r) => Object.fromEntries(Object.entries(r).filter(([k]) => !drop.includes(k))));
  return JSON.stringify([bare(t.notes), bare(t.pages), t.strokes]); }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def helpers(pg): pg.evaluate(HELP)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def rows(pg, nid): return pg.evaluate(ROWS_JS, nid)
def opened(pg): return pg.evaluate("window.__pw.S.openNote")
def shared(pg): return pg.evaluate("window.__pw.pdf.shared()")
def imgs(pg, pid): return pg.evaluate("(id) => window.__T.imgs(id)", pid)
def sel(pg): return pg.evaluate("window.__pw.ink.selection()")
def tool(pg): return pg.evaluate("window.__pw.ink.tool().tool")
def undo_len(pg, nid): return pg.evaluate("(id) => { const h = window.__pw.S.hist[id]; return h ? h.u.length : 0; }", nid)
def toasts(pg): return [t for t in pg.evaluate("window.__toastLog") if t]
def title(pg): return pg.locator("#shareInTitle").inner_text()
def until(pg, fn, ms=4000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def share(pg, items):
    pg.evaluate(SHARE_JS, [[f, n, t, b64(by)] for f, n, t, by in items])
    pg.wait_for_url(re.compile(r"[?&]share=1"), timeout=15000)
    ready(pg); helpers(pg)
def sheet(pg): pg.wait_for_selector("#shareIn .dlg", timeout=15000)
def no_share_in_url(pg): return "share=" not in pg.url and "local=1" in pg.url
def quiet(pg, ms=15000):
    """no page picture due or being made (js/snap.js), then both queues settled"""
    until(pg, lambda: (lambda s_: not s_["due"] and not s_["running"] and not s_["covers"])(pg.evaluate("window.__pw.snap()")), ms, 200)
    idle(pg)
def placed(d):
    """the landing rule: w = min(nw, 0.8 W), cut to 0.8 H; centred across, its top the gap of its sides (less near the bottom)"""
    w = min(d["nw"], 0.8 * W); h = w * d["nh"] / d["nw"]
    if h > 0.8 * H: h = 0.8 * H; w = h * d["nw"] / d["nh"]
    x = (W - w) / 2; y = min(x, H - h)
    return abs(d["w"] - w) < 0.02 and abs(d["h"] - h) < 0.02 and abs(d["x"] - x) < 0.02 and abs(d["y"] - y) < 0.02
def pil(b): return Image.open(io.BytesIO(base64.b64decode(b)))
def back_to_list(pg):
    if opened(pg):
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(100)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_init_script(INIT)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        posts = []
        pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(100)
        until(pg, lambda: pg.evaluate("!!navigator.serviceWorker.controller"), 5000)
        helpers(pg)

        # ------------------------------------------------------------ the manifest and the worker
        group[0] = "manifest and worker"
        raw = pg.evaluate("fetch('./manifest.json').then(r => r.text())")
        man = json.loads(raw)
        fl = ((man.get("share_target") or {}).get("params") or {}).get("files") or []
        check("share_target has two files entries: pdf first, image second", [e.get("name") for e in fl] == ["pdf", "image"], fl)
        check("the pdf entry is byte-identical to before", PDF_ENTRY in raw and fl[:1] == [{"name": "pdf", "accept": ["application/pdf", ".pdf"]}], fl[:1])
        check("the image entry accepts PNG, JPEG and WebP by type and by name", fl[1:2] == [IMG_ENTRY], fl[1:2])
        rest = json.loads(raw); rest["share_target"]["params"].pop("files", None)
        check("nothing else in the manifest changed", rest == OLD_MANIFEST, rest)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("sw.js CACHE is pw-v9d, with its version line in the head", 'const CACHE = "pw-v9d";' in swt and "   pw-v9d (7 Nov): " in swt)
        check("the page is controlled by the service worker", pg.evaluate("!!navigator.serviceWorker.controller"))

        # ------------------------------------------------------------ (a) one picture: the list of one, the sheet
        group[0] = "(a) one picture, the sheet"
        share(pg, [["image", "IMG-20261107-WA0012.png", "image/png", BIG]])
        check("the POST ends on ./?share=1 (local=1 carried over)", re.search(r"/\?share=1&local=1$", pg.url), pg.url)
        w = shared(pg)
        check("one picture under `image` waits as a list of one, its name, size and type kept",
              w and w["count"] == 1 and w["files"] == [{"name": "IMG-20261107-WA0012.png", "size": len(BIG), "type": "image/png"}], w)
        sheet(pg)
        check("the sheet says 'Open picture as' (no WhatsApp file name)", title(pg) == "Open picture as", title(pg))
        btns = pg.evaluate("[...document.querySelectorAll('#shareIn button')].map(b => [b.dataset.shareIn, b.textContent, b.classList.contains('main')])")
        check("New note in Loose (main), Add to a note, Cancel: the U4b sheet", btns == [["new", "New note in Loose", True], ["add", "Add to a note", False], ["cancel", "Cancel", False]], btns)
        pg.screenshot(path=str(SHOTS / "dialog-one-picture.png"))
        pg.click("#shareIn button[data-share-in='add']"); pg.wait_for_selector("#shareInGrid")
        check("Add to a note: 'Add picture to'", title(pg) == "Add picture to", title(pg))
        pg.click("#shareIn button[data-share-in='back']"); pg.wait_for_timeout(60)
        check("Back: 'Open picture as' again", title(pg) == "Open picture as", title(pg))

        # ------------------------------------------------------------ (b) New note in Loose
        group[0] = "(b) one picture, New note in Loose"
        c0 = pg.evaluate(COUNTS_JS)
        pg.click("#shareIn button[data-share-in='new']")
        ok = until(pg, lambda: pg.locator("#noteView:not([hidden])").count() == 1 and opened(pg) not in (None, "n1", "n2"), 15000)
        until(pg, lambda: sel(pg), 3000); pg.wait_for_timeout(150)
        nid = opened(pg)
        n = pg.evaluate("(id) => window.__pw.S.notes.find(x => x.id === id)", nid) or {}
        check("ONE new note, in Loose, with New note's usual name ('Untitled'), open", ok and n.get("name") == "Untitled" and n.get("folder_id") is None
              and pg.evaluate("window.__pw.S.notes.length") == c0[0] + 1, n)
        r = rows(pg, nid)
        check("it has one page, a plain portrait grid page (New note's paper)", len(r) == 1 and r[0]["orientation"] == "portrait"
              and r[0]["background"] == "grid" and r[0]["pdf_path"] is None, r)
        pid = r[0]["id"] if r else None
        im = imgs(pg, pid)
        d0 = im[0]["data"] if im else {}
        check("ONE 'image' record on it, kept at 1600 x 1200", len(im) == 1 and len(pg.evaluate("(id) => window.__pw.ink.strokesOf(id)", pid)) == 1
              and d0.get("nw") == 1600 and d0.get("nh") == 1200 and re.fullmatch(r"local/[0-9a-f-]{36}\.png", d0.get("path", "")), im)
        check("w <= 0.8 x the page's width, horizontally centred", d0 and d0["w"] <= 0.8 * W + 0.01 and abs(d0["x"] + d0["w"] / 2 - W / 2) < 0.02, d0)
        check("its top is the same gap from the page's top as its sides (the landing rule), rot 0, unlocked",
              d0 and placed(d0) and abs(d0["y"] - d0["x"]) < 0.02 and d0["rot"] == 0 and d0["locked"] is False, d0)
        check("the note opens on that page", pg.evaluate("window.__pw.current()") == 0 and pg.evaluate("window.__pw.S.cur") == 0)
        s = sel(pg)
        check("the picture is selected and the tool is Select (like + Image)", s and s["page"] == pid and s["ids"] == [im[0]["id"]] and tool(pg) == "select", [s, tool(pg)])
        ie = pg.evaluate("([s, r]) => window.__T.imgEl(s, r)", [pid, im[0]["id"]]) if im else None
        check("it draws on the page (an SVG <image>, a Blob URL)", ie and ie["tag"] == "image" and ie["href"] == "blob:", ie)
        check("the sheet is gone, ?share=1 left the address (?local=1 kept)", pg.locator("#shareIn").count() == 0 and no_share_in_url(pg), pg.url)
        check("the shared list no longer waits", until(pg, lambda: shared(pg) is None, 3000))
        check("the folder view is on Loose (Back lands where the note lives)", pg.evaluate("window.__pw.S.sel") == "loose")
        check("landing is not an undo step (the note's undo stack is empty)", undo_len(pg, nid) == 0, undo_len(pg, nid))
        pg.screenshot(path=str(SHOTS / "landed-one-picture.png"))
        pg.keyboard.press("Control+z"); pg.wait_for_timeout(100)
        check("... and Undo (Ctrl+Z) leaves the picture where it is", len(imgs(pg, pid)) == 1 and len(rows(pg, nid)) == 1)
        idle(pg)
        tw = pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2'))")
        check("the twin has the note in Loose, its page and the picture's record",
              [x for x in tw["notes"] if x["id"] == nid and x["folder_id"] is None and x["name"] == "Untitled"]
              and [p for p in tw["pages"] if p["note_id"] == nid] and [x for x in tw["strokes"] if x["page_id"] == pid and x["kind"] == "image"], [len(tw["strokes"])])
        check("the picture's file went to the twin's imports", until(pg, lambda: pg.evaluate("(p) => window.__pw.api.getImport(p).then(b => !!b, () => false)", d0["path"]), 5000))
        doc = fitz.open(stream=base64.b64decode(pg.evaluate("(id) => window.__T.pdf(id)", pid)), filetype="pdf")
        info = doc[0].get_image_info()
        check("Share as PDF of the new picture page carries the picture (PyMuPDF: an image on the page, at the box)",
              len(doc) == 1 and len(info) >= 1 and abs(fitz.Rect(info[0]["bbox"]).width - d0["w"] * 595.28 / W) < 1
              and abs(fitz.Rect(info[0]["bbox"]).x0 - d0["x"] * 595.28 / W) < 1, info)
        back_to_list(pg)
        check("after Back: the folder view shows the new note in Loose", pg.locator(f"#grid .card[data-id='{nid}']").count() == 1)
        check("... its card shows the picture (the first page's ink layer, its <image>)",
              until(pg, lambda: pg.locator(f"#grid .card[data-id='{nid}'] .paper svg image").count() == 1, 5000))

        # ------------------------------------------------------------ (c) three pictures, Add to a note
        group[0] = "(c) three pictures, Add to a note"
        share(pg, [["image", "IMG-20261107-WA0001.png", "image/png", P1], ["image", "IMG-20261107-WA0002.jpg", "image/jpeg", P2],
                   ["image", "IMG-20261107-WA0003.webp", "image/webp", P3]])
        w = shared(pg)
        check("three pictures wait as a list of three, in order", w and w["count"] == 3 and [f["name"] for f in w["files"]]
              == ["IMG-20261107-WA0001.png", "IMG-20261107-WA0002.jpg", "IMG-20261107-WA0003.webp"]
              and [f["type"] for f in w["files"]] == ["image/png", "image/jpeg", "image/webp"], w)
        sheet(pg)
        check("the sheet says 'Open 3 pictures as'", title(pg) == "Open 3 pictures as", title(pg))
        pg.screenshot(path=str(SHOTS / "dialog-three-pictures.png"))
        pg.click("#shareIn button[data-share-in='add']"); pg.wait_for_selector("#shareInGrid")
        check("Add to a note: 'Add 3 pictures to'", title(pg) == "Add 3 pictures to", title(pg))
        cards = pg.evaluate("[...document.querySelectorAll('#shareInGrid .card')].map(c => c.dataset.id)")
        check("the same note picker grid (every live note, last edited first)", cards == [nid, "n1", "n2"], cards)
        pg.screenshot(path=str(SHOTS / "dialog-three-pictures-add.png"))
        c0 = pg.evaluate(COUNTS_JS)
        before = [x["id"] for x in rows(pg, "n1")]
        pg.locator("#shareInGrid .card[data-id='n1']").click()
        ok = until(pg, lambda: len(rows(pg, "n1")) == 5 and opened(pg) == "n1", 15000)
        until(pg, lambda: sel(pg), 3000); pg.wait_for_timeout(150)
        rn = rows(pg, "n1")
        check("three new pages at the END of Base, positions 0..4", ok and [x["id"] for x in rn[:2]] == before and [x["position"] for x in rn] == [0, 1, 2, 3, 4], rn)
        ims = [imgs(pg, x["id"]) for x in rn[2:]]
        check("one picture each, in share order (300 x 200, 200 x 300, 400 x 100)", [len(i) for i in ims] == [1, 1, 1]
              and [(i[0]["data"]["nw"], i[0]["data"]["nh"]) for i in ims] == [(300, 200), (200, 300), (400, 100)], [[x["data"] for x in i] for i in ims])
        check("each placed by the landing rule (small ones keep their size, centred across, top gap = side gap)", all(placed(i[0]["data"]) for i in ims),
              [i[0]["data"] for i in ims])
        check("the PNG and the WebP are stored as PNG, the JPEG as JPEG", [i[0]["data"]["path"].rsplit(".", 1)[1] for i in ims] == ["png", "jpg", "png"],
              [i[0]["data"]["path"] for i in ims])
        check("Base opens on the first new page", opened(pg) == "n1" and pg.evaluate("window.__pw.current()") == 2, pg.evaluate("window.__pw.current()"))
        s = sel(pg)
        check("... its picture selected, the tool Select", s and s["page"] == rn[2]["id"] and s["ids"] == [ims[0][0]["id"]] and tool(pg) == "select", s)
        check("no new note, not an undo step", pg.evaluate("window.__pw.S.notes.length") == c0[0] and undo_len(pg, "n1") == 0)
        check("the sheet is gone, ?share=1 left the address, the list no longer waits", pg.locator("#shareIn").count() == 0 and no_share_in_url(pg)
              and until(pg, lambda: shared(pg) is None, 3000), pg.url)
        check("the folder view is on Base's folder", pg.evaluate("window.__pw.S.sel") == "f1")
        pg.screenshot(path=str(SHOTS / "landed-three-pictures.png"))
        pg.evaluate("window.__pw.ink.clearSelection()")
        idle(pg)
        back_to_list(pg)

        # ------------------------------------------------------------ (d) a PDF through the new code
        group[0] = "(d) a PDF, as before"
        share(pg, [["pdf", "Week 3 notes.pdf", "application/pdf", PDF2]])
        w = shared(pg)
        check("a PDF under `pdf` still lands, as a list of one", w and w["count"] == 1 and w["files"] == [{"name": "Week 3 notes.pdf", "size": len(PDF2), "type": "application/pdf"}], w)
        sheet(pg)
        check("the sheet still says 'Open Week 3 notes.pdf as'", title(pg) == "Open Week 3 notes.pdf as", title(pg))
        pg.click("#shareIn button[data-share-in='new']")
        ok = until(pg, lambda: (opened(pg) or "") not in ("", "n1", "n2", nid) and len(rows(pg, opened(pg))) == 2, 15000)
        pg.wait_for_timeout(200)
        pn = opened(pg)
        n = pg.evaluate("(id) => window.__pw.S.notes.find(x => x.id === id)", pn) or {}
        r = rows(pg, pn)
        check("a new note named 'Week 3 notes' in Loose, its 2 pages the PDF's, open on the first", ok and n.get("name") == "Week 3 notes" and n.get("folder_id") is None
              and [x["pdf_page"] for x in r] == [1, 2] and pg.evaluate("window.__pw.current()") == 0, [n, r])
        check("nothing selected, no picture on it", sel(pg) is None and not any(imgs(pg, x["id"]) for x in r))
        check("?share=1 gone, the list dropped", no_share_in_url(pg) and until(pg, lambda: shared(pg) is None, 3000))
        back_to_list(pg)

        # ------------------------------------------------------------ (e) a mix, in form order
        group[0] = "(e) a picture, a PDF, a picture"
        share(pg, [["image", "IMG-A.png", "image/png", P1], ["pdf", "Mixed.pdf", "application/pdf", PDF2], ["image", "IMG-B.jpg", "image/jpeg", P2]])
        w = shared(pg)
        check("the list keeps the form's order across both fields", w and [f["name"] for f in w["files"]] == ["IMG-A.png", "Mixed.pdf", "IMG-B.jpg"]
              and [f["type"] for f in w["files"]] == ["image/png", "application/pdf", "image/jpeg"], w)
        sheet(pg)
        check("the sheet says 'Open 3 files as'", title(pg) == "Open 3 files as", title(pg))
        pg.click("#shareIn button[data-share-in='new']")
        ok = until(pg, lambda: (opened(pg) or "") not in ("", "n1", "n2", nid, pn) and len(rows(pg, opened(pg))) == 4, 15000)
        until(pg, lambda: sel(pg), 3000); pg.wait_for_timeout(150)
        mn = opened(pg)
        n = pg.evaluate("(id) => window.__pw.S.notes.find(x => x.id === id)", mn) or {}
        r = rows(pg, mn)
        kinds = [("pdf", x["pdf_page"]) if x["pdf_path"] else ("pic", [(i["data"]["nw"], i["data"]["nh"]) for i in imgs(pg, x["id"])]) for x in r]
        check("ONE new note ('Untitled': the first file is a picture), 4 pages in form order", ok and n.get("name") == "Untitled"
              and kinds == [("pic", [(300, 200)]), ("pdf", 1), ("pdf", 2), ("pic", [(200, 300)])], [n.get("name"), kinds])
        s = sel(pg)
        check("open on the first page, its picture selected", pg.evaluate("window.__pw.current()") == 0 and s and s["page"] == r[0]["id"], s)
        back_to_list(pg)

        # ------------------------------------------------------------ (f) Cancel and Escape drop the whole list
        group[0] = "(f) Cancel and Escape"
        idle(pg)
        share(pg, [["image", "IMG-C.png", "image/png", P1], ["image", "IMG-D.png", "image/png", P1]]); sheet(pg)
        quiet(pg); c0 = pg.evaluate(COUNTS_JS); tw0 = pg.evaluate(TWIN_JS)
        check("two pictures wait", (shared(pg) or {}).get("count") == 2)
        pg.click("#shareIn button[data-share-in='cancel']"); pg.wait_for_timeout(300)
        check("Cancel: the sheet goes, no note, no page, nothing queued", pg.locator("#shareIn").count() == 0 and pg.evaluate(COUNTS_JS) == c0, [pg.evaluate(COUNTS_JS), c0])
        check("... the whole list is dropped, ?share=1 left the address", until(pg, lambda: shared(pg) is None, 3000) and no_share_in_url(pg), pg.url)
        quiet(pg)
        check("... and the twin's notes, pages and strokes are untouched", pg.evaluate(TWIN_JS) == tw0)
        share(pg, [["image", "IMG-E.png", "image/png", P1]]); sheet(pg)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        check("Escape is Cancel too", pg.locator("#shareIn").count() == 0 and pg.evaluate(COUNTS_JS) == c0 and until(pg, lambda: shared(pg) is None, 3000)
              and no_share_in_url(pg))

        # ------------------------------------------------------------ (g) nothing usable
        group[0] = "(g) nothing to open"
        share(pg, [])
        pg.wait_for_timeout(500)
        check("a text-only share: nothing waits, no sheet", shared(pg) is None and pg.locator("#shareIn").count() == 0)
        check("... the app toasts 'Nothing to open: share a PDF or a picture to PenWorks'", "Nothing to open: share a PDF or a picture to PenWorks" in toasts(pg), toasts(pg))
        check("... ?share=1 left the address", no_share_in_url(pg), pg.url)
        share(pg, [["image", "notes.txt", "text/plain", b"just some words"]])
        pg.wait_for_timeout(500)
        check("a file that is neither a PDF nor a picture: nothing kept, the same toast", shared(pg) is None and pg.locator("#shareIn").count() == 0
              and "Nothing to open: share a PDF or a picture to PenWorks" in toasts(pg), toasts(pg))

        # ------------------------------------------------------------ (h) the + Image conversions
        group[0] = "(h) EXIF turn and WebP"
        share(pg, [["image", "IMG-TURNED.jpg", "image/jpeg", EXIF_JPG], ["image", "IMG-SMALL.webp", "image/webp", SMALL_WEBP]]); sheet(pg)
        pg.click("#shareIn button[data-share-in='add']"); pg.wait_for_selector("#shareInGrid")
        pg.locator("#shareInGrid .card[data-id='n2']").click()
        ok = until(pg, lambda: len(rows(pg, "n2")) == 3 and opened(pg) == "n2", 15000)
        pg.wait_for_timeout(200)
        r = rows(pg, "n2")
        a = imgs(pg, r[1]["id"]) if ok else []
        c = imgs(pg, r[2]["id"]) if ok else []
        da = a[0]["data"] if a else {}; dc = c[0]["data"] if c else {}
        check("the turned JPEG lands upright: 200 x 300 (stored 300 x 200 on its side), a .jpg", da.get("nw") == 200 and da.get("nh") == 300
              and da.get("path", "").endswith(".jpg") and placed(da), da)
        dev = pg.evaluate("(p) => window.__T.dev(p)", da["path"]) if da else None
        jp = pil(dev["b64"]) if dev else None
        orient = jp.getexif().get(0x0112) if jp else None
        px = jp.convert("RGB") if jp else None
        check("... its stored file is a JPEG of 200 x 300 with no turn left in it", dev and dev["type"] == "image/jpeg" and jp.format == "JPEG"
              and jp.size == (200, 300) and orient in (None, 1), [dev and dev["type"], jp and jp.size, orient])
        check("... drawn upright: the red corner is at the TOP-RIGHT, the top-left is white",
              px and px.getpixel((190, 10))[0] > 180 and px.getpixel((190, 10))[1] < 90 and min(px.getpixel((10, 10))) > 220,
              px and [px.getpixel((190, 10)), px.getpixel((10, 10))])
        dvc = pg.evaluate("(p) => window.__T.dev(p)", dc["path"]) if dc else None
        wp = pil(dvc["b64"]) if dvc else None
        check("the WebP is stored as a PNG (200 x 120)", dc.get("path", "").endswith(".png") and dvc and dvc["type"] == "image/png" and wp.format == "PNG"
              and wp.size == (200, 120) and (dc.get("nw"), dc.get("nh")) == (200, 120), [dc, dvc and dvc["type"], wp and wp.format])
        pg.screenshot(path=str(SHOTS / "landed-turned-jpeg.png"))
        back_to_list(pg)

        # ------------------------------------------------------------ (i) a value from before pw-v9d, the ten-minute rule
        group[0] = "(i) old value, leftover rule"
        pg.evaluate("(b) => window.__T.put({ blob: window.__T.blob(b, 'application/pdf'), name: 'Legacy.pdf', at: new Date().toISOString() })", b64(PDF2))
        pg.goto(BASE + "?share=1&local=1"); ready(pg); helpers(pg); sheet(pg)
        w = shared(pg)
        check("a single-file value from before pw-v9d is read as a list of one PDF", w and w["count"] == 1 and w["files"] == [{"name": "Legacy.pdf", "size": len(PDF2), "type": "application/pdf"}], w)
        check("... and its sheet names it", title(pg) == "Open Legacy.pdf as", title(pg))
        pg.click("#shareIn button[data-share-in='cancel']"); pg.wait_for_timeout(200)
        old = "new Date(Date.now() - 11 * 60e3).toISOString()"
        pg.evaluate(f"(b) => window.__T.put({{ files: [{{ blob: window.__T.blob(b, 'image/png'), name: 'Old.png', type: 'image/png' }}], at: {old} }})", b64(P1))
        pg.goto(LOCAL); ready(pg); helpers(pg); pg.wait_for_timeout(600)
        check("a normal start drops a list nobody answered for over ten minutes", until(pg, lambda: shared(pg) is None, 3000) and pg.locator("#shareIn").count() == 0)
        pg.evaluate("(b) => window.__T.put({ files: [{ blob: window.__T.blob(b, 'image/png'), name: 'Fresh.png', type: 'image/png' }], at: new Date().toISOString() })", b64(P1))
        pg.goto(LOCAL); ready(pg); helpers(pg); pg.wait_for_timeout(600)
        check("... and keeps a fresh one (no sheet without ?share=1)", (shared(pg) or {}).get("name") == "Fresh.png" and pg.locator("#shareIn").count() == 0)
        pg.evaluate("import('./js/pdfin.js').then(m => m.dropShared())")

        # ------------------------------------------------------------ (j) the phone (375 x 812)
        group[0] = "(j) the phone"
        ctx2 = b.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
        ctx2.add_init_script(INIT)
        ph = ctx2.new_page(); e2 = []
        ph.on("pageerror", lambda e: e2.append(str(e)))
        ph.goto(LOCAL); ready(ph); ph.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        ph.evaluate(SEED_JS); ph.reload(); ready(ph)
        until(ph, lambda: ph.evaluate("!!navigator.serviceWorker.controller"), 5000); helpers(ph)
        share(ph, [["image", "IMG-PHONE.png", "image/png", BIG]]); sheet(ph)
        bb = ph.locator("#shareIn .dlg").bounding_box()
        check("the sheet fits the phone's width, 'Open picture as'", title(ph) == "Open picture as" and bb and bb["x"] >= 0 and bb["x"] + bb["width"] <= 375, bb)
        ph.screenshot(path=str(SHOTS / "phone-dialog-one-picture.png"))
        ph.click("#shareIn button[data-share-in='new']")
        ok = until(ph, lambda: (opened(ph) or "") not in ("", "n1", "n2") and sel(ph), 15000)
        ph.wait_for_timeout(200)
        pn2 = opened(ph); pr = rows(ph, pn2) if pn2 else []
        pim = imgs(ph, pr[0]["id"]) if pr else []
        check("New note in Loose on the phone: one page, its picture placed by the landing rule, selected, Select on",
              ok and len(pr) == 1 and len(pim) == 1 and placed(pim[0]["data"]) and sel(ph)["ids"] == [pim[0]["id"]] and tool(ph) == "select", [pr, pim, sel(ph)])
        ph.screenshot(path=str(SHOTS / "phone-landed-one-picture.png"))
        check("no page errors (phone)", not e2, e2)
        ctx2.close()

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v9d" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v9d", "pw-v9d" in keys, keys)
        check("the only POSTs were the shares, all to the share-target action", posts and all("/share-target/" in u for u in posts), posts)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in
                       ["./js/app.js", "./js/pdfin.js", "./js/ink.js", "./sw.js", "./manifest.json", "./tests/test_shareimg.py", "./tests/test_u4b.py"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        swb = pg.evaluate("fetch('./sw.js').then(r => r.arrayBuffer()).then(b => [...new Uint8Array(b).slice(0, 3)])")
        check("sw.js has no BOM", swb != [0xEF, 0xBB, 0xBF], swb)
        check("no page errors", not errs, errs)
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
sys.exit(0 if all(r[2] for r in res) else 1)
