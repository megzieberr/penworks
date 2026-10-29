# PenWorks drop checks (round 6): tools/drop_pdf.py puts a PDF from the laptop into PenWorks as a new note.
# Run: python tests/test_drop.py          (no live project: the name rule against the app's own nameOf, PyMuPDF's page
#                                         sizes against pdf.js (the app's vendor/pdf.min.mjs, ?local=1), and the refusals
#                                         that happen before any sign-in: no file, not a PDF, over 50 MB)
#      python tests/test_drop.py --live   (adds the live group, ALWAYS the throwaway login droptest from PW_TEST_USER /
#                                         PW_TEST_PASS or the gitignored .env, never printed, never megan: drops into
#                                         Loose, a top folder and a Parent/Child folder, the unknown folder and the 60 MB
#                                         refusals write nothing, scan20.pdf in under 30 s, and the app (these files,
#                                         served on 127.0.0.1 in live mode, against the live project) shows the dropped
#                                         note's pages painted. Round 6b: an app left open on the Loose grid shows the
#                                         dropped note within 5 s by itself, and its cover_path is set within 15 s.
#                                         It starts and ends by removing every row and stored file droptest owns, and its
#                                         last lines prove droptest holds 0 notes, 0 pages, 0 folders, 0 stored files)
import sys, os, subprocess, time, pathlib, re, json, base64, tempfile, hashlib, shutil
import fitz
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import drop_pdf as D
for s_ in (sys.stdout, sys.stderr):
    try: s_.reconfigure(encoding="utf-8")
    except Exception: pass

PORT = 8800
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
# round 6b: the app from these files (no ?local=1, so the live project), not the published site, so a change not yet
# pushed is the one tested (as tests/test_u3d.py --live does)
APP = f"http://127.0.0.1:{PORT}/"
LIVE = "--live" in sys.argv
TOOL = ROOT / "tools" / "drop_pdf.py"
U4A = ROOT / "tests" / "fixtures" / "u4a.pdf"
SCAN = ROOT / "tests" / "fixtures" / "scan20.pdf"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="pw drop ê "))      # a folder name with a space and an Afrikaans letter
MARK = (0.3, 0.25)            # inside the black block on every page of the test PDFs
CLEAR = (0.7, 0.7)            # plain white paper
THREE = [(595.28, 841.89), (841.89, 595.28), (400.5, 655.25)]   # A4 portrait, A4 landscape, not A4

res = []
group = ["?"]
report = []
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

def make_pdf(path, sizes, rot=None, crop=None):
    doc = fitz.open()
    for i, (w, h) in enumerate(sizes):
        pg = doc.new_page(width=w, height=h)
        pg.draw_rect(fitz.Rect(0.2 * w, 0.2 * h, 0.4 * w, 0.3 * h), color=(0, 0, 0), fill=(0, 0, 0))
        if crop and crop[i]: pg.set_cropbox(fitz.Rect(*crop[i]))
        if rot and rot[i]: pg.set_rotation(rot[i])
    doc.save(str(path)); doc.close()
def mu_sizes(path):
    with fitz.open(str(path)) as d: return [[round(p.rect.width, 2), round(p.rect.height, 2)] for p in d]

THREE_PDF = TMP / "Vraestel één, Graad 12 ê ô.pdf"; make_pdf(THREE_PDF, THREE)
THREE_NAME = "Vraestel één, Graad 12 ê ô"
ROT_PDF = TMP / "rotated.pdf"
make_pdf(ROT_PDF, [(595.28, 841.89), (612, 792), (500, 700), (595.28, 841.89)],
         rot=[90, 0, 270, 180], crop=[None, (36, 50, 400, 520), (10, 10, 480, 650), None])
NOT_PDF = TMP / "not a pdf.pdf"; NOT_PDF.write_bytes(b"hello, this is not a PDF\n")
BIG = TMP / "big.pdf"                                            # a real small PDF padded past 60 MB (never committed)
make_pdf(BIG, THREE[:1])
with open(BIG, "ab") as f:
    f.write(b"\n%" + b"x" * (60 * 1024 * 1024) + b"\n")

def run(args, env_extra=None):
    env = dict(os.environ); env.update(env_extra or {})
    t = time.time()
    p = subprocess.run([sys.executable, str(TOOL)] + [str(a) for a in args], capture_output=True, encoding="utf-8",
                       errors="replace", cwd=str(TMP), env=env)
    return p.returncode, (p.stdout + p.stderr).strip(), time.time() - t
def note_of(out):
    m = re.search(r"as note ([0-9a-f-]{36})$", out)
    return m.group(1) if m else None

# the app's own nameOf line, read from js/pdfin.js, run in the browser against ours
NAME_LINE = next(l for l in (ROOT / "js" / "pdfin.js").read_text(encoding="utf-8").splitlines() if l.startswith("const nameOf"))
NAME_CASES = ["Some sheet.pdf", "  Some sheet.PDF  ", ".pdf", "a.pdf.pdf", "x" * 130 + ".pdf", " Wiskunde﻿.pdf",
              "Graad 9 ê ô ë.Pdf", "notes.pdfx", "   .pdf", "Vraestel één, Graad 12 ê ô.pdf", "y" * 119 + "zz.pdf"]
NAME_JS = "(names) => { " + NAME_LINE + " return names.map((n) => nameOf({ name: n })); }"
SIZE_JS = """async ([src, b64]) => {
  const m = await import('./js/pdfin.js'), lib = await m.loadLib();
  let u;
  if (b64) { const s = atob(b64); u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); }
  else u = new Uint8Array(await (await fetch(src)).arrayBuffer());
  const doc = await lib.getDocument({ data: u, isEvalSupported: false }).promise, out = [];
  for (let k = 1; k <= doc.numPages; k++) { const pg = await doc.getPage(k), v = pg.getViewport({ scale: 1 });
    out.push([Math.round(v.width * 100) / 100, Math.round(v.height * 100) / 100]); pg.cleanup(); }
  await doc.destroy(); return out; }"""
PIX_JS = """([i, fx, fy]) => { const c = document.querySelector(`#stack .sheet[data-index="${i}"] > .pdfLayer > canvas`);
  if (!c || !c.width) return null;
  const d = c.getContext('2d').getImageData(Math.floor(fx * c.width), Math.floor(fy * c.height), 1, 1).data; return [d[0], d[1], d[2]]; }"""
SHEETS_JS = "() => [...document.querySelectorAll('#stack .sheet')].map(s => [parseFloat(s.style.width), parseFloat(s.style.height)])"
dark = lambda c: c is not None and max(c) < 90
white = lambda c: c is not None and min(c) > 225
def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=30000)
def until(fn, ms, step=0.25):
    t = time.time()
    while True:
        v = fn()
        if v or (time.time() - t) * 1000 > ms: return v
        time.sleep(step)

# ---------------------------------------------------------------- the live project, through the REST API
def rows(tok, table, q="select=id"):
    st, r = D.call("GET", f"/rest/v1/{table}?{q}", tok)
    if st != 200: raise RuntimeError(f"{table}: {st} {r}")
    return r
def objects(tok, uid, bucket):
    st, r = D.call("POST", f"/storage/v1/object/list/{bucket}", tok, body={"prefix": uid, "limit": 1000})
    if st != 200: raise RuntimeError(f"list {bucket}: {st} {r}")
    return [uid + "/" + o["name"] for o in r if o.get("name")]
def counts(tok, uid):
    return {"notes": len(rows(tok, "notes")), "pages": len(rows(tok, "pages")), "folders": len(rows(tok, "folders")),
            "imports": len(objects(tok, uid, "imports")), "snapshots": len(objects(tok, uid, "snapshots"))}
def wipe(tok, uid):
    # every row and stored file of the throwaway login: notes (their pages go with them), folders, both buckets
    gone = {}
    n = [r["id"] for r in rows(tok, "notes")]
    if n: D.call("DELETE", "/rest/v1/notes?id=in.(" + ",".join(n) + ")", tok)
    p = [r["id"] for r in rows(tok, "pages")]
    if p: D.call("DELETE", "/rest/v1/pages?id=in.(" + ",".join(p) + ")", tok)
    f = rows(tok, "folders", "select=id,parent_id")
    kids = [r["id"] for r in f if r["parent_id"]]; tops = [r["id"] for r in f if not r["parent_id"]]
    if kids: D.call("DELETE", "/rest/v1/folders?id=in.(" + ",".join(kids) + ")", tok)
    if tops: D.call("DELETE", "/rest/v1/folders?id=in.(" + ",".join(tops) + ")", tok)
    gone.update(notes=len(n), folders=len(f))
    for b in ("imports", "snapshots"):
        objs = objects(tok, uid, b)
        for o in objs: D.call("DELETE", f"/storage/v1/object/{b}/{o}", tok)
        gone[b] = len(objs)
    return gone

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
pdfjs = {}
live_note = "live group skipped (run with --live)"
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # ------------------------------------------------------------ local: the name rule and the page sizes
        group[0] = "local"
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        js_names = pg.evaluate(NAME_JS, NAME_CASES)
        py_names = [D.name_of(n) for n in NAME_CASES]
        check("the note name follows the app's nameOf exactly (11 file names, Afrikaans letters, odd spaces, 120 letters)",
              js_names == py_names, list(zip(NAME_CASES, js_names, py_names)))
        for label, path, b64 in [("u4a.pdf", U4A, None), ("scan20.pdf", SCAN, None),
                                 ("the 3-page test PDF", THREE_PDF, base64.b64encode(THREE_PDF.read_bytes()).decode()),
                                 ("a PDF with turned and cropped pages", ROT_PDF, base64.b64encode(ROT_PDF.read_bytes()).decode())]:
            js = pg.evaluate(SIZE_JS, ["./tests/fixtures/" + path.name if not b64 else "", b64])
            mu = mu_sizes(path)
            pdfjs[path.name] = js
            check(f"PyMuPDF's page sizes match pdf.js page for page: {label} ({len(mu)} pages)", js == mu,
                  [(i + 1, a, c) for i, (a, c) in enumerate(zip(mu, js)) if a != c] or (len(mu), len(js)))
            report.append(f"  sizes, {label}: PyMuPDF {mu[:4]}{' ...' if len(mu) > 4 else ''} | pdf.js {js[:4]}{' ...' if len(js) > 4 else ''}")
        check("no page errors (local)", not errs, errs)
        ctx.close()

        # the refusals before any sign-in: a login that cannot exist is given, so a sign-in attempt would show as exit 1
        nobody = {"PW_TEST_USER": "nobody-drop-check", "PW_TEST_PASS": "not-a-password"}
        code, out, _ = run([TMP / "no such file.pdf", "--test"], nobody)
        check("a missing file: exit 2 and one plain sentence", code == 2 and out.startswith("There is no file at"), (code, out))
        code, out, _ = run([NOT_PDF, "--test"], nobody)
        check("a file that is not a PDF: exit 2", code == 2 and "could not be opened" in out, (code, out))
        code, out, _ = run([BIG, "--test"], nobody)
        check(f"a {BIG.stat().st_size / 1048576:.0f} MB file is refused before any sign-in or write: exit 2",
              code == 2 and "too big" in out and "50 MB" in out, (code, out))
        report.append(f"  60 MB refusal says: {out}")
        srcs = "".join(p.read_text(encoding="utf-8") for p in [TOOL, ROOT / "tools" / "README-drop.md", pathlib.Path(__file__)]
                       if p.exists())
        check("no em-dashes in tools/drop_pdf.py, tools/README-drop.md, tests/test_drop.py", chr(0x2014) not in srcs)
        check("tools/README-drop.md exists", (ROOT / "tools" / "README-drop.md").exists())

        # ------------------------------------------------------------ live: droptest only
        if LIVE:
            try:
                user, pwd = D.login(True)
            except D.Stop:
                user = pwd = None
            if not user or not pwd:
                live_note = "live group SKIPPED: no test login (PW_TEST_USER / PW_TEST_PASS or .env) on this machine"
            elif user.casefold() == "megan":
                live_note = "live group SKIPPED: the test login is the same as her own login"
            else:
                group[0] = "live"; live_note = ""
                tok, uid = D.sign_in(user, pwd)
                left = wipe(tok, uid)
                report.append(f"  start: removed what an earlier run left behind: {left}")
                c0 = counts(tok, uid)
                check("droptest starts empty", all(v == 0 for v in c0.values()), c0)
                ctx = None
                try:
                    # the live app, signed in as droptest, open BEFORE the drop: the note must arrive by itself
                    ctx = b.new_context(viewport={"width": 1280, "height": 900})
                    pg = ctx.new_page(); errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    pg.goto(APP); pg.wait_for_selector("#login:not([hidden])", timeout=30000)
                    pg.fill("#lu", user); pg.fill("#lp", pwd); pg.click("#loginBtn"); ready(pg); t_ready = time.time()
                    check("the live app signs in as droptest", pg.evaluate("window.__pw.S.user && window.__pw.S.user.id") == uid)
                    pg.click(".frow[data-id='loose']"); pg.wait_for_timeout(300)        # the folder view she left open: Loose
                    check("the live channel is subscribed before the drop",
                          until(lambda: pg.evaluate("window.__pw.live.state()") == "subscribed", 10000))

                    # ---- 1. three pages into Loose
                    code, out, secs = run([THREE_PDF, "--test"])
                    nid = note_of(out)
                    check("a 3-page PDF drops into Loose: exit 0 and the one line",
                          code == 0 and out == f'Dropped "{THREE_NAME}" (3 pages) into Loose as note {nid}', (code, out))
                    report.append(f"  drop line: {out}  ({secs:.1f} s)")
                    t_drop = time.time()
                    n = rows(tok, "notes", f"select=id,name,folder_id,pinned,owner_id,deleted_at&id=eq.{nid}") if nid else []
                    check("the note row: the file's name, Loose, not pinned, owned by droptest",
                          len(n) == 1 and n[0]["name"] == THREE_NAME and n[0]["folder_id"] is None and n[0]["pinned"] is False
                          and n[0]["owner_id"] == uid and n[0]["deleted_at"] is None, n)
                    ps = rows(tok, "pages", f"select=id,position,orientation,background,bookmark,pdf_path,pdf_page,pdf_w,pdf_h&note_id=eq.{nid}&order=position") if nid else []
                    want = [[0, "portrait", 1, 595.28, 841.89], [1, "landscape", 2, 841.89, 595.28], [2, "portrait", 3, 400.5, 655.25]]
                    check("3 page rows in order: position 0 to 2, pdf_page 1 to 3, the right sizes and orientations",
                          [[p["position"], p["orientation"], p["pdf_page"], p["pdf_w"], p["pdf_h"]] for p in ps] == want, ps)
                    check("the page sizes are pdf.js's own", [[p["pdf_w"], p["pdf_h"]] for p in ps] == pdfjs.get(THREE_PDF.name), ps)
                    path = ps[0]["pdf_path"] if ps else ""
                    check("every page: blank paper, no bookmark, one shared pdf_path <user id>/<uuid>.pdf (no bucket in front)",
                          ps and all(p["background"] == "blank" and p["bookmark"] is False and p["pdf_path"] == path for p in ps)
                          and re.fullmatch(uid + r"/[0-9a-f-]{36}\.pdf", path or ""), ps)
                    st, got = D.call("GET", f"/storage/v1/object/imports/{path}", tok)
                    check("the stored PDF downloads back byte-identical", st == 200 and isinstance(got, bytes)
                          and hashlib.sha256(got).hexdigest() == hashlib.sha256(THREE_PDF.read_bytes()).hexdigest(), (st, len(got or b"")))

                    # ---- 2. the app shows it. Round 6b: the channel carries notes and pages rows too (js/live.js, app.js
                    # remoteTree), so the app left open on the Loose grid shows the card by itself, no visibility change. The
                    # 5 s count starts when drop_pdf.py has written its last row (it has exited).
                    has = lambda: pg.evaluate("(id) => window.__pw.S.pages.filter(p => p.note_id === id && !p.deleted_at).length === 3"
                                              " && window.__pw.S.notes.some(n => n.id === id)", nid)
                    on_screen = lambda: has() and pg.locator(f"#grid .card[data-id='{nid}']").count() == 1
                    by_itself = until(on_screen, max(0.0, 5000 - (time.time() - t_drop) * 1000), 0.1)
                    t_seen = time.time() - t_drop
                    check(f"an app left open on the Loose grid shows the dropped note and its 3 pages within 5 s by itself ({t_seen:.1f} s)",
                          by_itself, t_seen)
                    report.append(f"  an app left open on screen: the note {'arrived by itself' if by_itself else 'did NOT arrive by itself'} "
                                  f"{t_seen:.1f} s after drop_pdf.py finished (5 s allowed)")
                    cov0 = until(lambda: rows(tok, "notes", f"select=cover_path&id=eq.{nid}")[0]["cover_path"],
                                 max(0.0, 15000 - (time.time() - t_drop) * 1000), 0.5)
                    t_cov = time.time() - t_drop
                    check(f"the open app gives the dropped note its cover: cover_path set within 15 s ({t_cov:.1f} s)",
                          bool(ps) and cov0 == f"{uid}/{ps[0]['id']}.webp", (cov0, t_cov))
                    report.append(f"  the open app's cover for it: cover_path = {cov0!r}, {t_cov:.1f} s after drop_pdf.py finished (15 s allowed)")
                    if not by_itself:
                        wait = 62 - (time.time() - t_ready)
                        if wait > 0: time.sleep(wait)
                        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
                        back = until(has, 10000)
                        check("switching back to the app after a minute brings the note and its 3 pages in (no reload)", back)
                        if not back:
                            pg.reload(); ready(pg)
                    pg2 = ctx.new_page(); pg2.goto(APP); ready(pg2)
                    check("an app opened fresh (her tablet starting PenWorks) has the note at once",
                          until(lambda: pg2.evaluate("(id) => window.__pw.S.pages.filter(p => p.note_id === id).length === 3", nid), 10000))
                    pg2.close()
                    pg.click(".frow[data-id='loose']"); card = pg.locator(f"#grid .card[data-id='{nid}']")
                    card.wait_for(timeout=10000)
                    check("the note's card is in the Loose grid with its name", THREE_NAME in card.inner_text(), card.inner_text())
                    card.click(); pg.wait_for_selector("#noteView:not([hidden])", timeout=10000)
                    pg.wait_for_function("document.querySelectorAll('#stack .sheet').length === 3", timeout=10000)
                    sz = pg.evaluate(SHEETS_JS)
                    check("the note opens with 3 pages, each the PDF page's own shape",
                          len(sz) == 3 and all(abs(s[1] / s[0] - h / w) < 0.01 for s, (w, h) in zip(sz, THREE)), sz)
                    painted = []
                    for i in range(3):
                        if i: pg.evaluate("(i) => import('./js/page.js').then((m) => m.scrollToPage(i))", i)
                        ok = until(lambda: dark(pg.evaluate(PIX_JS, [i + 1, MARK[0], MARK[1]])), 20000)    # data-index counts from 1
                        painted.append([i + 1, pg.evaluate(PIX_JS, [i + 1, MARK[0], MARK[1]]), pg.evaluate(PIX_JS, [i + 1, CLEAR[0], CLEAR[1]])])
                    check("every PDF page's canvas is painted (the black mark dark, the paper white)",
                          all(dark(p[1]) and white(p[2]) for p in painted), painted)

                    # ---- 3. the cover picture: open and idle, then back to the grid
                    pg.evaluate("(i) => import('./js/page.js').then((m) => m.scrollToPage(0))", 0)
                    pg.evaluate("window.__pw.idle()")
                    cov = until(lambda: rows(tok, "notes", f"select=cover_path&id=eq.{nid}")[0]["cover_path"], 10000, 1)
                    snaps = [p["snapshot_path"] for p in rows(tok, "pages", f"select=snapshot_path&note_id=eq.{nid}&order=position")]
                    report.append(f"  cover after 10 s open and idle: cover_path = {cov!r}; page pictures: {snaps}")
                    pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])", timeout=10000)
                    cov2 = cov or until(lambda: rows(tok, "notes", f"select=cover_path&id=eq.{nid}")[0]["cover_path"], 6000, 1)
                    img = pg.evaluate("(id) => { const im = document.querySelector(`#grid .card[data-id='${id}'] img`); return im ? (im.getAttribute('src') || '').slice(0, 30) : null; }", nid)
                    report.append(f"  cover after going back to the grid (6 s more): cover_path = {cov2!r}; the card's picture: {img!r}")

                    # ---- 4. folders: a top one and a Parent/Child one, made through the REST API
                    st, top = D.call("POST", "/rest/v1/folders", tok, body={"name": "Drop Top", "parent_id": None, "position": 0},
                                     headers={"Prefer": "return=representation"})
                    st2, kid = D.call("POST", "/rest/v1/folders", tok, body={"name": "Drop Child ê", "parent_id": top[0]["id"], "position": 0},
                                      headers={"Prefer": "return=representation"})
                    check("two folders made for droptest (a top one and one inside it)", st == 201 and st2 == 201, (st, st2))
                    st3, deep = D.call("POST", "/rest/v1/folders", tok, body={"name": "Too deep", "parent_id": kid[0]["id"], "position": 0},
                                       headers={"Prefer": "return=representation"})
                    check("the database refuses a third level by itself", st3 >= 400, (st3, deep))
                    code, out, _ = run([THREE_PDF, "--test", "--folder", "  drop top "])
                    nt = note_of(out)
                    ft = rows(tok, "notes", f"select=folder_id,name&id=eq.{nt}") if nt else []
                    check("--folder finds a top folder (any case, spaces round it)",
                          code == 0 and out.endswith(f"into Drop Top as note {nt}") and ft and ft[0]["folder_id"] == top[0]["id"], (code, out, ft))
                    code, out, _ = run([THREE_PDF, "--test", "--folder", "DROP TOP / drop child Ê", "--name", "  Michaela G1 to G8  "])
                    nc = note_of(out)
                    fc = rows(tok, "notes", f"select=folder_id,name&id=eq.{nc}") if nc else []
                    check("--folder Parent/Child finds the sub-folder, --name names the note",
                          code == 0 and out == f'Dropped "Michaela G1 to G8" (3 pages) into Drop Top/Drop Child ê as note {nc}'
                          and fc and fc[0]["folder_id"] == kid[0]["id"] and fc[0]["name"] == "Michaela G1 to G8", (code, out, fc))
                    before = counts(tok, uid)
                    code, out, _ = run([THREE_PDF, "--test", "--folder", "Drop Top/Nope"])
                    after = counts(tok, uid)
                    check("an unknown folder: exit 2, the folders listed as Parent/Child lines, nothing written",
                          code == 2 and "Drop Top/Drop Child ê" in out and "\n  Drop Top\n" in out + "\n" and before == after, (code, out, before, after))
                    report.append("  unknown folder says: " + out.replace("\n", " | "))
                    code, out, _ = run([BIG, "--test"])
                    after2 = counts(tok, uid)
                    check("the 60 MB file with the real login: exit 2 and nothing written", code == 2 and "too big" in out and after2 == after,
                          (code, out, after2))

                    # ---- 5. the 20-page scan
                    code, out, secs = run([SCAN, "--test"])
                    ns = note_of(out)
                    check("scan20.pdf (6 MB, 20 pages) drops in under 30 s", code == 0 and secs < 30 and "(20 pages)" in out, (code, out, secs))
                    report.append(f"  scan20 drop: {secs:.1f} s")
                    pss = rows(tok, "pages", f"select=position,pdf_page,pdf_w,pdf_h&note_id=eq.{ns}&order=position") if ns else []
                    check("scan20's 20 rows: in order, sizes equal to pdf.js's",
                          [p["position"] for p in pss] == list(range(20)) and [p["pdf_page"] for p in pss] == list(range(1, 21))
                          and [[p["pdf_w"], p["pdf_h"]] for p in pss] == pdfjs.get(SCAN.name), pss[:2])
                    check("no page errors (live app)", not errs, errs)
                finally:
                    if ctx: ctx.close()          # the app closes first, so nothing it still saves lands after the clean-up
                    time.sleep(1)
                    gone = wipe(tok, uid)
                    report.append(f"  clean-up removed: {gone}")
                    c9 = counts(tok, uid)
                    check("clean-up: droptest ends with 0 notes, 0 pages, 0 folders, 0 stored files", all(v == 0 for v in c9.values()), c9)
                    report.append(f"  droptest now holds: {c9['notes']} notes, {c9['pages']} pages, {c9['folders']} folders, "
                                  f"{c9['imports']} files in imports, {c9['snapshots']} files in snapshots")
        b.close()
finally:
    srv.terminate()
    shutil.rmtree(TMP, ignore_errors=True)      # the 60 MB file and the test PDFs go

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:600]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
for line_ in report: print(line_)
if live_note: print(live_note)
sys.exit(0 if all(r[2] for r in res) else 1)
