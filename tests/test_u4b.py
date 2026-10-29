# PenWorks U4b checks (pw-v7a: a PDF shared to PenWorks, the app always full screen): headless Playwright (Python),
# same harness as tests/test_u4a.py.
# Run: python tests/test_u4b.py     (local mode only: ?local=1, the localStorage twin stands in for Supabase)
# A share is a real multipart POST to ./share-target/?local=1, sent by a form in the app's page, so it goes through the
# registered service worker exactly as Android's share sheet does (the test server never sees it: python's http.server
# would answer a POST with 501). The fixture is tests/fixtures/u4a.pdf (4 pages, made by test_u4a.py).
import sys, subprocess, time, pathlib, re, json, base64
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8792
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
FIX = ROOT / "tests" / "fixtures" / "u4a.pdf"
if not FIX.exists(): sys.exit("tests/fixtures/u4a.pdf is missing: run tests/test_u4a.py once first")
FIX_B64 = base64.b64encode(FIX.read_bytes()).decode()
FIX_SIZE = FIX.stat().st_size

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const P = (id, nid, pos, t) => ({ id, note_id: nid, position: pos, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Maths', colour: null, position: 0, deleted_at: null, created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-20T10:00:00Z' },
              { id: 'f2', parent_id: 'f1', name: 'Gr11', colour: null, position: 0, deleted_at: null, created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-20T10:00:00Z' }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Base', pinned: false, cover_path: null, deleted_at: null, created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-24T10:00:00Z' },
            { id: 'n2', folder_id: null, name: 'Older', pinned: true, cover_path: null, deleted_at: null, created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-21T10:00:00Z' },
            { id: 'n3', folder_id: 'f2', name: 'Newest', pinned: false, cover_path: null, deleted_at: null, created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-26T10:00:00Z' },
            { id: 'n4', folder_id: null, name: 'Gone', pinned: false, cover_path: null, deleted_at: '2026-10-25T10:00:00Z', created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-27T10:00:00Z' }],
    pages: [P('q1', 'n1', 0, '2026-10-24T10:00:00Z'), P('q2', 'n1', 1, '2026-10-24T10:00:00Z'), P('q3', 'n2', 0, '2026-10-21T10:00:00Z'),
            P('q4', 'n3', 0, '2026-10-26T10:00:00Z'), { ...P('q5', 'n4', 0, '2026-10-25T10:00:00Z'), deleted_at: '2026-10-25T10:00:00Z' }] }));
}"""
# a real share: a multipart POST of one PDF (plus a caption, as WhatsApp may send) to the share-target action
SHARE_JS = """([name, b64]) => {
  const s = atob(b64), u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  const f = document.createElement('form');
  f.method = 'POST'; f.enctype = 'multipart/form-data'; f.action = './share-target/?local=1';
  const inp = document.createElement('input'); inp.type = 'file'; inp.name = 'pdf';
  const dt = new DataTransfer(); dt.items.add(new File([u], name, { type: 'application/pdf' })); inp.files = dt.files;
  const t = document.createElement('input'); t.name = 'title'; t.value = 'From WhatsApp';
  const x = document.createElement('input'); x.name = 'text'; x.value = 'a caption';
  f.append(inp, t, x); document.body.append(f); f.submit(); return 1; }"""
ROWS_JS = """(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position)
  .map(p => ({ id: p.id, position: p.position, pdf_path: p.pdf_path || null, pdf_page: p.pdf_page ?? null, background: p.background }))"""
COUNTS_JS = "[window.__pw.S.notes.length, window.__pw.S.pages.length, window.__pw.treeq.length()]"
# requestFullscreen stubbed; only the app's own calls count (Playwright's click machinery calls it once itself)
RF_JS = """() => { window.__rf = 0; Element.prototype.requestFullscreen = function () {
  if (String(new Error().stack).includes('/js/app.js')) window.__rf++; return Promise.resolve(); }; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def rows(pg, nid): return pg.evaluate(ROWS_JS, nid)
def opened(pg): return pg.evaluate("window.__pw.S.openNote")
def shared(pg): return pg.evaluate("window.__pw.pdf.shared()")
def until(pg, fn, ms=4000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def share(pg, name):
    pg.evaluate(SHARE_JS, [name, FIX_B64])
    pg.wait_for_url(re.compile(r"[?&]share=1"), timeout=15000)
def sheet(pg): pg.wait_for_selector("#shareIn .dlg", timeout=15000)
def no_share_in_url(pg): return "share=" not in pg.url and "local=1" in pg.url

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        posts = []
        pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(100)
        until(pg, lambda: pg.evaluate("!!navigator.serviceWorker.controller"), 5000)

        # ------------------------------------------------------------ the manifest and the worker
        group[0] = "manifest and worker"
        man = pg.evaluate("fetch('./manifest.json').then(r => r.json())")
        st = man.get("share_target") or {}
        check("display is fullscreen, standalone second in display_override", man.get("display") == "fullscreen"
              and man.get("display_override") == ["fullscreen", "standalone"], [man.get("display"), man.get("display_override")])
        check("share_target: POST, multipart, ./share-target/ under the scope", st.get("method") == "POST" and st.get("enctype") == "multipart/form-data"
              and st.get("action") == "./share-target/" and man.get("scope") == "./", st)
        fl = (st.get("params") or {}).get("files") or [{}]
        check("share_target files: one param accepting application/pdf and .pdf, title and text params too",
              len(fl) == 1 and fl[0].get("name") == "pdf" and set(fl[0].get("accept", [])) == {"application/pdf", ".pdf"}
              and st["params"].get("title") and st["params"].get("text"), st.get("params"))
        check("the page is controlled by the service worker", pg.evaluate("!!navigator.serviceWorker.controller"))

        # ------------------------------------------------------------ (a) the POST through the service worker
        group[0] = "(a) the share POST"
        share(pg, "Week 3 notes.pdf"); ready(pg)
        check("the POST ends on ./?share=1 (local=1 carried over)", re.search(r"/\?share=1&local=1$", pg.url), pg.url)
        w = shared(pg)
        check("the file waits on the device, its name and size as shared", w and w["name"] == "Week 3 notes.pdf" and w["size"] == FIX_SIZE, [w, FIX_SIZE])
        nav = pg.evaluate("performance.getEntriesByType('navigation')[0].name")
        check("the landing page itself is a GET of ./?share=1 (the worker's 303; http.server would have answered the POST with 501)", "share=1" in nav, nav)
        keys = pg.evaluate("""async () => { const out = []; for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(r.url); return out; }""")
        check("no cache holds the share-target address", not [k for k in keys if "share-target" in k], [k for k in keys if "share-target" in k])
        check("the share-target address is not in the shell list", "share-target" not in pg.evaluate("fetch('./sw.js').then(r => r.text())").split("const CDN")[0].split("const SHELL")[1])

        # ------------------------------------------------------------ (b) the landing sheet
        group[0] = "(b) the sheet"
        sheet(pg)
        t = pg.locator("#shareInTitle").inner_text()
        check("the sheet says 'Open Week 3 notes.pdf as'", t == "Open Week 3 notes.pdf as", t)
        btns = pg.evaluate("[...document.querySelectorAll('#shareIn button')].map(b => [b.dataset.shareIn, b.textContent, b.classList.contains('main')])")
        check("New note in Loose (main), Add to a note, Cancel", btns == [["new", "New note in Loose", True], ["add", "Add to a note", False], ["cancel", "Cancel", False]], btns)
        check("in the app's dialog look (.dlgVeil > .dlg, a dialog role)", pg.evaluate("""() => { const v = document.getElementById('shareIn');
          return v.classList.contains('dlgVeil') && v.firstElementChild.classList.contains('dlg') && v.firstElementChild.getAttribute('role') === 'dialog'; }"""))
        vb = pg.locator("#shareIn").bounding_box()
        pg.mouse.click(vb["x"] + 20, vb["y"] + 20); pg.wait_for_timeout(100)
        check("a tap outside the sheet does nothing (the share is not lost)", pg.locator("#shareIn").count() == 1 and shared(pg))

        # ------------------------------------------------------------ (c) New note in Loose
        group[0] = "(c) New note in Loose"
        c0 = pg.evaluate(COUNTS_JS)
        pg.click("#shareIn button[data-share-in='new']")
        ok = until(pg, lambda: pg.locator("#noteView:not([hidden])").count() == 1 and opened(pg) not in (None, "n1", "n2", "n3"), 15000)
        pg.wait_for_timeout(150)
        nid = opened(pg)
        n = pg.evaluate("(id) => window.__pw.S.notes.find(x => x.id === id)", nid)
        check("a new note named 'Week 3 notes' in Loose, opened", ok and n and n["name"] == "Week 3 notes" and n["folder_id"] is None, n)
        r = rows(pg, nid)
        check("its 4 pages are the PDF's pages, in order", [x["pdf_page"] for x in r] == [1, 2, 3, 4] and len({x["pdf_path"] for x in r}) == 1, r)
        check("it opens on its first page", pg.evaluate("window.__pw.current()") == 0)
        check("the sheet is gone, ?share=1 left the address (?local=1 kept)", pg.locator("#shareIn").count() == 0 and no_share_in_url(pg), pg.url)
        check("the shared file no longer waits", until(pg, lambda: shared(pg) is None, 3000))
        check("the folder view is on Loose (Back lands where the note lives)", pg.evaluate("window.__pw.S.sel") == "loose")
        idle(pg)
        check("the twin has the note in Loose and its 4 rows", [x for x in pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).notes") if x["id"] == nid and x["folder_id"] is None]
              and len([p for p in pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).pages") if p["note_id"] == nid]) == 4)
        pg.reload(); ready(pg); pg.wait_for_timeout(300)
        check("a reload after: no sheet again", pg.locator("#shareIn").count() == 0)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")

        # ------------------------------------------------------------ (d) Add to a note
        group[0] = "(d) Add to a note"
        share(pg, "Extra.pdf"); ready(pg); sheet(pg)
        pg.click("#shareIn button[data-share-in='add']"); pg.wait_for_selector("#shareInGrid")
        t = pg.locator("#shareInTitle").inner_text()
        check("the title says 'Add Extra.pdf to'", t == "Add Extra.pdf to", t)
        cards = pg.evaluate("""() => [...document.querySelectorAll('#shareInGrid .card')].map(c => ({ id: c.dataset.id, name: c.querySelector('.name').textContent,
          where: c.querySelector('.where').textContent, paper: !!c.querySelector('.thumb .paper') }))""")
        check("every live note across folders, last edited first (the binned note left out)", [c["id"] for c in cards] == [nid, "n3", "n1", "n2"], cards)
        check("each card: its cover (the paper of its first page) and its folder's name as a caption",
              all(c["paper"] for c in cards) and [c["where"] for c in cards] == ["Loose", "Maths / Gr11", "Maths", "Loose"], cards)
        check("the grid is the folder view's card look (.card > .thumb, .meta)", pg.evaluate("""() => { const c = document.querySelector('#shareInGrid .card');
          return !!(c && c.querySelector(':scope > .thumb') && c.querySelector(':scope > .meta')); }"""))
        check("the new note's card shows the PDF's first page", until(pg, lambda: pg.evaluate(f"!!document.querySelector(\"#shareInGrid .card[data-id='{nid}'] .paper > img.pdfThumb\")"), 6000))
        pg.click("#shareIn button[data-share-in='back']"); pg.wait_for_timeout(60)
        check("Back returns to the first step", pg.locator("#shareInTitle").inner_text() == "Open Extra.pdf as")
        pg.click("#shareIn button[data-share-in='add']"); pg.wait_for_selector("#shareInGrid")
        before = [x["id"] for x in rows(pg, "n1")]
        pg.locator("#shareInGrid .card[data-id='n1']").click()
        ok = until(pg, lambda: len(rows(pg, "n1")) == 6 and opened(pg) == "n1", 15000)
        pg.wait_for_timeout(200)
        rn = rows(pg, "n1")
        check("a tap: the 4 PDF pages go at the END of Base", ok and [x["id"] for x in rn[:2]] == before and [x["pdf_page"] for x in rn[2:]] == [1, 2, 3, 4]
              and [x["position"] for x in rn] == [0, 1, 2, 3, 4, 5], [(x["position"], x["pdf_page"]) for x in rn])
        check("Base opens there, on the first new page", opened(pg) == "n1" and pg.evaluate("window.__pw.current()") == 2, pg.evaluate("window.__pw.current()"))
        check("the sheet is gone, ?share=1 left the address, the file no longer waits", pg.locator("#shareIn").count() == 0 and no_share_in_url(pg)
              and until(pg, lambda: shared(pg) is None, 3000), pg.url)
        check("no new note made", pg.evaluate("window.__pw.S.notes.length") == 5)
        check("the folder view is on Base's folder", pg.evaluate("window.__pw.S.sel") == "f1")
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")

        # ------------------------------------------------------------ (e) Cancel leaves nothing
        group[0] = "(e) Cancel"
        idle(pg)
        share(pg, "Nope.pdf"); ready(pg); sheet(pg)
        c0 = pg.evaluate(COUNTS_JS); tw0 = pg.evaluate("localStorage.getItem('penworks.local.v2')")
        pg.click("#shareIn button[data-share-in='cancel']"); pg.wait_for_timeout(300)
        check("Cancel: the sheet goes, no note, no page, nothing queued", pg.locator("#shareIn").count() == 0 and pg.evaluate(COUNTS_JS) == c0, [pg.evaluate(COUNTS_JS), c0])
        check("... the file is dropped, ?share=1 left the address", until(pg, lambda: shared(pg) is None, 3000) and no_share_in_url(pg), pg.url)
        idle(pg)
        check("... and the twin is untouched", pg.evaluate("localStorage.getItem('penworks.local.v2')") == tw0)
        share(pg, "Escaped.pdf"); ready(pg); sheet(pg)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        check("Escape is Cancel too", pg.locator("#shareIn").count() == 0 and pg.evaluate(COUNTS_JS) == c0 and until(pg, lambda: shared(pg) is None, 3000))

        # ------------------------------------------------------------ (f) logged out: the login first, then the sheet
        group[0] = "(f) logged out"
        pg.evaluate("localStorage.setItem('penworks.local.out', '1')")
        share(pg, "After login.pdf")
        pg.wait_for_selector("#login:not([hidden])", timeout=15000); pg.wait_for_timeout(300)
        check("logged out: the login shows, no sheet yet", pg.locator("#shareIn").count() == 0 and pg.locator("#app").is_hidden())
        w = shared(pg)
        check("... the file waits meanwhile", w and w["name"] == "After login.pdf", w)
        pg.fill("#lu", "local"); pg.fill("#lp", "local-test"); pg.click("#loginBtn")
        ready(pg); sheet(pg)
        check("after the login: the sheet, with the file's name", pg.locator("#shareInTitle").inner_text() == "Open After login.pdf as")
        pg.click("#shareIn button[data-share-in='new']")
        ok = until(pg, lambda: (opened(pg) or "") and pg.evaluate("(id) => (window.__pw.S.notes.find(x => x.id === id) || {}).name", opened(pg)) == "After login", 15000)
        check("New note in Loose works after the login", ok and len(rows(pg, opened(pg))) == 4)
        pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")

        # ------------------------------------------------------------ nothing waiting
        group[0] = "nothing waiting"
        pg.goto(BASE + "?share=1&local=1"); ready(pg); pg.wait_for_timeout(400)
        check("?share=1 with no file: no sheet, ?share=1 leaves the address", pg.locator("#shareIn").count() == 0 and no_share_in_url(pg), pg.url)

        # ------------------------------------------------------------ (g) full screen in the installed app
        group[0] = "(g) full screen"
        pg.evaluate(RF_JS)
        pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^Base$"))).first.click()
        pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(100)
        cdp = ctx.new_cdp_session(pg)
        how = "CDP Emulation.setEmulatedMedia"
        try: cdp.send("Emulation.setEmulatedMedia", {"features": [{"name": "display-mode", "value": "fullscreen"}]})
        except Exception as e: how = f"CDP refused ({e})"
        if not pg.evaluate("matchMedia('(display-mode: fullscreen)').matches"):
            how += ", matchMedia stub"
            pg.evaluate("""() => { const real = window.matchMedia.bind(window);
              window.matchMedia = (q) => /display-mode:\\s*fullscreen/.test(q) ? { matches: true, media: q, addEventListener() {}, removeEventListener() {} } : real(q); }""")
        check("display-mode: fullscreen is emulated", pg.evaluate("matchMedia('(display-mode: fullscreen)').matches"), how)
        pg.click("#fsBtn"); pg.wait_for_timeout(150)
        check("the full-screen button does NOT call requestFullscreen", pg.evaluate("window.__rf") == 0, pg.evaluate("window.__rf"))
        check("... and still hides PenWorks' header, the exit button shows", pg.locator("#noteBar").is_hidden() and pg.locator("#exitFs").is_visible()
              and pg.evaluate("document.body.classList.contains('full')"))
        pg.click("#exitFs"); pg.wait_for_timeout(100)
        check("the exit button brings the header back", pg.locator("#noteBar").is_visible() and pg.locator("#exitFs").is_hidden())
        try: cdp.send("Emulation.setEmulatedMedia", {"features": []})
        except Exception: pass
        pg.reload(); ready(pg); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(100)
        pg.evaluate(RF_JS)
        check("a browser tab is not display-mode fullscreen", not pg.evaluate("matchMedia('(display-mode: fullscreen)').matches"))
        pg.click("#fsBtn"); pg.wait_for_timeout(150)
        check("in a browser tab the button still calls requestFullscreen (today's behaviour)", pg.evaluate("window.__rf") == 1 and pg.locator("#noteBar").is_hidden(),
              pg.evaluate("window.__rf"))
        pg.click("#exitFs"); pg.wait_for_timeout(100)

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7e" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7e", "pw-v7e" in keys, keys)
        check("the only POSTs were the shares, all to the share-target action", posts and all("/share-target/" in u for u in posts), posts)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in
                       ["./js/app.js", "./js/pdfin.js", "./js/local-backend.js", "./css/app.css", "./sw.js", "./manifest.json", "./tests/test_u4b.py"])
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
