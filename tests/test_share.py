# PenWorks pw-v6b checks (Share that reaches WhatsApp): headless Playwright (Python), same harness as tests/test_u4a.py.
# Run: python tests/test_share.py        (local mode only: ?local=1, the localStorage twin stands in for Supabase)
# Android's Chrome lets navigator.share run only inside a tap (about 5 s of "transient activation"); rendering a real
# note takes longer, so the share sheet was refused and the file quietly downloaded. pw-v6b: Share as PDF / images
# makes the files, the dialog turns to "Ready: <name>.pdf" with Send and Save, and Send is its own tap. Share note
# (the note's menu) and Share page (the page's menu) open the same dialog without ticking.
# Headless Chromium has no share sheet: an init script stubs navigator.canShare / navigator.share (the files land in
# window.__shared; the stub notes whether it ran in the same task as the tap, and canShare notes how many files it was
# asked about). PDFs are read with PyMuPDF, never looked at.
import sys, subprocess, time, pathlib, re, base64, tempfile
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8792
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="pw-share-"))
MARK = (0.3, 0.25)            # inside the black block, as fractions of the page
SQUARE = TMP / "square.pdf"
d_ = fitz.open(); pg_ = d_.new_page(width=595.28, height=595.28)
pg_.draw_rect(fitz.Rect(0.2 * 595.28, 0.2 * 595.28, 0.4 * 595.28, 0.3 * 595.28), color=(0, 0, 0), fill=(0, 0, 0))
d_.save(str(SQUARE)); d_.close()

res = []
group = ["?"]
info_lines = []
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-27T10:00:00Z', P = (id, nid, k) => ({ id, note_id: nid, position: k, orientation: 'portrait', background: 'grid',
    deleted_at: null, created_at: t, updated_at: t });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Share', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Three', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-27T10:02:00Z' },
            { id: 'n2', folder_id: 'f1', name: 'Two', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: '2026-10-27T10:01:00Z' }],
    pages: [P('t1', 'n1', 0), P('t2', 'n1', 1), P('t3', 'n1', 2), P('w1', 'n2', 0)] }));
  const st = (pid, x, y) => ({ id: pid + '-s', page_id: pid, seq: 1, kind: 'pen', style: { colour: '#000000', width: 3, dash: 'solid', opacity: 1 },
    data: { points: Array.from({ length: 30 }, (_, j) => [x + j * 12, Math.round((y + 20 * Math.sin(j / 3)) * 10) / 10]) } });
  for (const id of ['t1', 't2', 't3', 'w1']) localStorage.setItem('pw.strokes.' + id, JSON.stringify([st(id, 100, 300)]));
}"""
STUB_JS = """
  document.addEventListener('click', () => { window.__inTap = true; setTimeout(() => { window.__inTap = false; }, 0); }, true);
  navigator.canShare = (d) => { (window.__canAsk ||= []).push(d && d.files ? d.files.length : -1); return true; };
  navigator.share = async (d) => { window.__sharedInTap = !!window.__inTap; window.__shared = d; };
"""
SHARED_JS = """async () => { const d = window.__shared; if (!d) return null;
  const b64 = async (f) => { const u = new Uint8Array(await f.arrayBuffer()); let s = '';
    for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
  return { title: d.title, inTap: window.__sharedInTap, files: await Promise.all(d.files.map(async (f) => ({ name: f.name, type: f.type, size: f.size, b64: await b64(f) }))) }; }"""
DLG_JS = """() => { const d = document.getElementById('shareDlg'); if (!d) return { open: false };
  const i = document.getElementById('shareName'), r = document.getElementById('shareReady');
  return { open: true, title: document.getElementById('shareTitle').textContent, name: i ? i.value : null, ready: r ? r.textContent : null,
           buttons: [...d.querySelectorAll('button')].map(b => [b.textContent, b.classList.contains('main')]),
           focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.share || null : null }; }"""
TOAST_JS = "() => document.getElementById('toast').textContent"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def dlg(pg): return pg.evaluate(DLG_JS)
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def menu_items(pg): return [t_.strip() for t_ in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name): nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose")
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def rows(pg, nid): return pg.evaluate("(nid) => window.__pw.S.pages.filter(p => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position).map(p => ({ id: p.id, pdf_path: p.pdf_path || null }))", nid)
def until(pg, fn, ms=4000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def make_ready(pg, kind="pdf"):
    """tap Share as PDF / images; the ms from the tap to the ready panel (measured in the page)"""
    pg.evaluate("""() => { window.__readyAt = 0; const d = document.getElementById('shareDlg');
      new MutationObserver((_, o) => { if (document.getElementById('shareReady')) { window.__readyAt = performance.now(); o.disconnect(); } })
        .observe(d, { childList: true, subtree: true }); }""")
    t0 = pg.evaluate("performance.now()")
    pg.click(f"#shareDlg button[data-share='{kind}']")
    pg.wait_for_selector("#shareReady", timeout=30000)
    return pg.evaluate("window.__readyAt") - t0
def send(pg):
    pg.evaluate("window.__shared = null")
    pg.click("#shareDlg button[data-share='send']")
    pg.wait_for_function("window.__shared", timeout=10000)
    pg.wait_for_selector("#shareDlg", state="detached", timeout=5000); pg.wait_for_timeout(40)
    return pg.evaluate(SHARED_JS)
def pdf_info(f):
    doc = fitz.open(stream=base64.b64decode(f["b64"]), filetype="pdf")
    out = {"pages": doc.page_count, "sizes": [(round(p_.rect.width, 2), round(p_.rect.height, 2)) for p_ in doc], "marks": []}
    for p_ in doc:
        px = p_.get_pixmap(dpi=72)
        out["marks"].append(max(px.pixel(int(MARK[0] * px.width), int(MARK[1] * px.height))[:3]) < 90)
    doc.close(); return out
near = lambda s_, t_: abs(s_[0] - t_[0]) <= 1 and abs(s_[1] - t_[1]) <= 1
A4P, SQ = (595.28, 841.89), (595.28, 595.28)
brief = lambda sh: None if not sh else {"title": sh["title"], "inTap": sh["inTap"], "files": [[f["name"], f["type"], f["size"]] for f in sh["files"]]}

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
        ctx.add_init_script(STUB_JS)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(100)
        if pg.locator("#noteView").is_visible(): back(pg)
        frow(pg, "Share").click(); pg.wait_for_timeout(60)

        # ------------------------------------------------------------ (g) a PDF page, and the timing
        group[0] = "a PDF page + timing"
        open_note(pg, "Two")
        with pg.expect_file_chooser() as fc:
            pg.click("#addPageBtn"); menu(pg, "PDF")
        fc.value.set_files(str(SQUARE))
        ok = until(pg, lambda: len(rows(pg, "n2")) == 2, 15000)
        r2 = rows(pg, "n2")
        check("set-up: 'Two' = one A4 grid page with ink + one square PDF page", ok and r2[0]["pdf_path"] is None and r2[1]["pdf_path"], r2)
        idle(pg)
        pg.click("#noteMore"); pg.wait_for_timeout(40); menu(pg, "Share note"); pg.wait_for_selector("#shareDlg")
        ms_cold = make_ready(pg)
        q = dlg(pg)
        check("Share note on 'Two': ready line 'Ready: Two.pdf, 2 pages'", q["ready"] == "Ready: Two.pdf, 2 pages", q)
        sh = send(pg)
        pi = pdf_info(sh["files"][0]) if sh and sh["files"] else {}
        check("the PDF: 2 pages, A4 then the PDF page in its own shape (square)", pi.get("pages") == 2 and near(pi["sizes"][0], A4P) and near(pi["sizes"][1], SQ), pi)
        check("the PDF page's own picture (its dark block) is in the file", pi.get("marks", [None, None])[1] is True, pi.get("marks"))
        pg.click("#noteMore"); pg.wait_for_timeout(40); menu(pg, "Share note"); pg.wait_for_selector("#shareDlg")
        ms_warm = make_ready(pg)
        send(pg)
        info_lines.append(f"timing: 'Share as PDF' tap to ready, 2-page note (A4 grid + one PDF page), headless Chromium: "
                          f"{round(ms_cold)} ms the first time (jsPDF loads), {round(ms_warm)} ms the second")
        check("tap to ready under 5 s here (the tablet is slower; Send no longer depends on it)", 0 < ms_cold < 5000 and 0 < ms_warm < 5000, [ms_cold, ms_warm])
        back(pg)

        # ------------------------------------------------------------ (a) (b) tick mode: the ready step, Send
        group[0] = "tick mode: ready + Send"
        open_note(pg, "Three")
        open_list(pg); pg.click("#plSelect"); pg.wait_for_timeout(40)
        thumb(pg, 1).click(); thumb(pg, 2).click(); pg.wait_for_timeout(30)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg")
        q = dlg(pg)
        check("step one as before: 'Share 2 pages', name 'Three p1-2', Share as PDF / Share as images / Cancel",
              q["title"] == "Share 2 pages" and q["name"] == "Three p1-2" and [x[0] for x in q["buttons"]] == ["Share as PDF", "Share as images", "Cancel"], q)
        pg.evaluate("window.__canAsk = []; window.__shared = null")
        make_ready(pg)
        q = dlg(pg)
        check("(a) ready: the title stays, 'Ready: Three p1-2.pdf, 2 pages', the name box is gone", q["title"] == "Share 2 pages"
              and q["ready"] == "Ready: Three p1-2.pdf, 2 pages" and q["name"] is None, q)
        check("(a) buttons: Send (main), Save, Cancel; Send has the focus", q["buttons"] == [["Send", True], ["Save", False], ["Cancel", False]]
              and q["focus"] == "send", q)
        asked = pg.evaluate("window.__canAsk")
        check("canShare was asked with the real file (1 file, never an empty list)", asked and all(a == 1 for a in asked), asked)
        check("nothing was shared or downloaded before Send", pg.evaluate("window.__shared") is None)
        sh = send(pg)
        fs = sh["files"] if sh else []
        check("(b) Send: navigator.share gets one application/pdf File 'Three p1-2.pdf', title 'Three p1-2'",
              len(fs) == 1 and fs[0]["name"] == "Three p1-2.pdf" and fs[0]["type"] == "application/pdf" and fs[0]["size"] > 5000 and sh["title"] == "Three p1-2", brief(sh))
        check("(b) ... called in the same task as the Send tap (no await before it)", sh and sh["inTap"] is True, brief(sh))
        check("(b) the dialog closed, tick mode ended, toast 'Shared'", pg.locator("#shareDlg").count() == 0 and pg.evaluate("window.__pw.tick()") is None
              and pg.evaluate(TOAST_JS) == "Shared", pg.evaluate(TOAST_JS))
        pi = pdf_info(fs[0]) if fs else {}
        check("(b) the PDF has 2 A4 pages", pi.get("pages") == 2 and all(near(s_, A4P) for s_ in pi["sizes"]), pi)

        # ------------------------------------------------------------ (c) cancel the share sheet, other refusals
        group[0] = "Send refused"
        pg.click("#plSelect"); pg.wait_for_timeout(40); thumb(pg, 3).click(); pg.wait_for_timeout(30)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg"); make_ready(pg)
        pg.evaluate("() => { navigator.share = async () => { throw new DOMException('cancelled', 'AbortError'); }; }")
        dls = []; pg.on("download", lambda d: dls.append(d))
        pg.evaluate("document.getElementById('toast').textContent = 'x'")
        pg.click("#shareDlg button[data-share='send']"); pg.wait_for_timeout(300)
        q = dlg(pg)
        check("(c) AbortError: the ready panel stays (Send, Save, Cancel), no toast, no download, tick mode still on",
              q["open"] and q["ready"] == "Ready: Three p3.pdf" and [x[0] for x in q["buttons"]] == ["Send", "Save", "Cancel"]
              and pg.evaluate(TOAST_JS) == "x" and not dls and pg.evaluate("window.__pw.tick()") is not None, [q, pg.evaluate(TOAST_JS), len(dls)])
        pg.evaluate("() => { navigator.share = async () => { throw new DOMException('no gesture', 'NotAllowedError'); }; }")
        pg.click("#shareDlg button[data-share='send']"); pg.wait_for_timeout(300)
        check("NotAllowedError: toast 'Could not open the share sheet, Save instead', the ready panel stays, no download",
              pg.evaluate(TOAST_JS) == "Could not open the share sheet, Save instead" and dlg(pg)["ready"] and not dls, [pg.evaluate(TOAST_JS), len(dls)])
        pg.evaluate("() => { navigator.share = () => { throw new TypeError('bad data'); }; }")
        pg.evaluate("document.getElementById('toast').textContent = 'x'")
        pg.click("#shareDlg button[data-share='send']"); pg.wait_for_timeout(300)
        check("a share call that throws at once: the same toast, the panel stays", pg.evaluate(TOAST_JS) == "Could not open the share sheet, Save instead"
              and dlg(pg)["ready"] and not dls, pg.evaluate(TOAST_JS))
        with pg.expect_download() as dl: pg.click("#shareDlg button[data-share='save']")
        pg.wait_for_selector("#shareDlg", state="detached"); pg.wait_for_timeout(60)
        check("Save after a refusal: 'Three p3.pdf' downloads, toast 'Saved to downloads', tick mode off", dl.value.suggested_filename == "Three p3.pdf"
              and pg.evaluate(TOAST_JS) == "Saved to downloads" and pg.evaluate("window.__pw.tick()") is None, dl.value.suggested_filename)
        pg.evaluate("() => { navigator.share = async (d) => { window.__sharedInTap = !!window.__inTap; window.__shared = d; }; window.__shared = null; }")
        # Escape and a tap outside on the ready panel = Cancel, nothing kept
        pg.click("#plSelect"); pg.wait_for_timeout(40); thumb(pg, 1).click(); pg.wait_for_timeout(30)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg"); make_ready(pg)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
        esc = pg.locator("#shareDlg").count() == 0
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg"); make_ready(pg)
        pg.mouse.click(1270, 990); pg.wait_for_timeout(40)
        check("ready panel: Escape closes it, so does a tap outside; nothing shared, the ticks stay", esc and pg.locator("#shareDlg").count() == 0
              and pg.evaluate("window.__shared") is None and pg.evaluate("window.__pw.tick()") == {"ids": ["t1"], "moving": False}, pg.evaluate("window.__pw.tick()"))
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg"); make_ready(pg)
        pg.click("#shareDlg button[data-share='cancel']"); pg.wait_for_timeout(40)
        check("ready panel: Cancel closes it", pg.locator("#shareDlg").count() == 0 and pg.evaluate("window.__shared") is None)
        # images
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg"); make_ready(pg, "images")
        check("Share as images, one page: 'Ready: Three p1.png'", dlg(pg)["ready"] == "Ready: Three p1.png", dlg(pg))
        sh = send(pg)
        check("Send gives one image/png 'Three p1.png'", sh and [[f["name"], f["type"]] for f in sh["files"]] == [["Three p1.png", "image/png"]], brief(sh))
        pg.click("#plSelect"); pg.wait_for_timeout(40); pg.click("#plAll"); pg.wait_for_timeout(40)
        pg.click("#plBar button[data-act='share']"); pg.wait_for_selector("#shareDlg"); make_ready(pg, "images")
        check("Share as images, every page: 'Ready: 3 images'", dlg(pg)["ready"] == "Ready: 3 images", dlg(pg))
        pg.click("#shareDlg button[data-share='cancel']"); pg.wait_for_timeout(40)
        if pg.evaluate("window.__pw.tick()") is not None: pg.click("#plDone"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ (f) Share page, from the page's menu
        group[0] = "Share page"
        thumb(pg, 2).locator(".more").click(); pg.wait_for_timeout(40)
        items = menu_items(pg)
        check("(f) the page menu (the dots) ends with 'Share page'", items and items[-1] == "Share page", items)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
        thumb(pg, 2).click(button="right"); pg.wait_for_timeout(40)
        items2 = menu_items(pg)
        check("(f) the right-click (long-press) menu is the same", items2 == items, items2)
        menu(pg, "Share page"); pg.wait_for_selector("#shareDlg")
        q = dlg(pg)
        check("(f) the dialog: title 'Share page 2', name 'Three p2'", q["title"] == "Share page 2" and q["name"] == "Three p2", q)
        make_ready(pg); q = dlg(pg)
        check("(f) ready: 'Ready: Three p2.pdf' (one page: no page count)", q["ready"] == "Ready: Three p2.pdf", q)
        sh = send(pg)
        pi = pdf_info(sh["files"][0]) if sh and sh["files"] else {}
        check("(f) Send: one 'Three p2.pdf' of 1 A4 page; toast 'Shared'", sh and sh["files"][0]["name"] == "Three p2.pdf" and pi.get("pages") == 1
              and pg.evaluate(TOAST_JS) == "Shared", [brief(sh), pi])
        close_list(pg)

        # ------------------------------------------------------------ (e) Share note, from the note's menu
        group[0] = "Share note"
        pg.click("#noteMore"); pg.wait_for_timeout(40)
        items = menu_items(pg)
        check("(e) the note's menu has 'Share note' just above 'Bin this note' (Bin stays last)",
          items and items[-1] == "Bin this note" and items[-2] == "Share note", items)
        menu(pg, "Share note"); pg.wait_for_selector("#shareDlg")
        q = dlg(pg)
        check("(e) the dialog: title 'Share note', name 'Three' (the note's name)", q["title"] == "Share note" and q["name"] == "Three", q)
        make_ready(pg); q = dlg(pg)
        check("(e) ready: 'Ready: Three.pdf, 3 pages'", q["ready"] == "Ready: Three.pdf, 3 pages", q)
        sh = send(pg)
        pi = pdf_info(sh["files"][0]) if sh and sh["files"] else {}
        check("(e) Send: one 'Three.pdf' with every page (3), in order", sh and sh["files"][0]["name"] == "Three.pdf" and pi.get("pages") == 3, [brief(sh), pi])
        check("(e) nothing on the note changed", [x["id"] for x in rows(pg, "n1")] == ["t1", "t2", "t3"])

        # ------------------------------------------------------------ (d) no navigator.share: Save only
        group[0] = "no share sheet"
        pg.evaluate("() => { navigator.share = undefined; }")
        dls.clear()
        pg.click("#noteMore"); pg.wait_for_timeout(40); menu(pg, "Share note"); pg.wait_for_selector("#shareDlg"); make_ready(pg)
        q = dlg(pg)
        check("(d) no navigator.share: Save is the main button, no Send (Save, Cancel); Save has the focus",
              q["buttons"] == [["Save", True], ["Cancel", False]] and q["focus"] == "save", q)
        with pg.expect_download() as dl: pg.click("#shareDlg button[data-share='save']")
        pg.wait_for_selector("#shareDlg", state="detached"); pg.wait_for_timeout(60)
        check("(d) Save: a download of 'Three.pdf', toast 'Saved to downloads'", dl.value.suggested_filename == "Three.pdf"
              and pg.evaluate(TOAST_JS) == "Saved to downloads", dl.value.suggested_filename)
        pg.evaluate("() => { navigator.share = async (d) => { window.__shared = d; }; navigator.canShare = () => false; }")
        pg.click("#noteMore"); pg.wait_for_timeout(40); menu(pg, "Share note"); pg.wait_for_selector("#shareDlg"); make_ready(pg)
        q = dlg(pg)
        check("canShare says no to the files: no Send either", q["buttons"] == [["Save", True], ["Cancel", False]], q)
        pg.click("#shareDlg button[data-share='cancel']"); pg.wait_for_timeout(40)

        # ------------------------------------------------------------ house rules
        group[0] = "house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7c" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7c", "pw-v7c" in keys, keys)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/app.js", "./css/app.css", "./sw.js", "./tests/test_share.py"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        labels = ["Send", "Save", "Share note", "Share page", "Shared", "Could not open the share sheet, Save instead", "Ready: "]
        check("no emoji in the new words", all(ord(ch) < 0x2190 for w in labels for ch in w))
        check("no page errors", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for line in info_lines: print(line)
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"TOTAL: {sum(r[2] for r in res)}/{len(res)} passed")
