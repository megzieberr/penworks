# PenWorks U1 checks: headless Playwright (Python), same style as constructions/tests/test_pwa.py.
# Run: python tests/test_u1.py            (local + layout + backgrounds + PWA + live)
#      python tests/test_u1.py --no-live  (skip the live Supabase group)
# The live group logs in with the account in LOGIN-LOCAL.md (read here, never printed), makes a
# "U1 test" notebook, bins and restores it, then deletes every row it made.
import sys, subprocess, time, pathlib, re, datetime
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8771
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SHOTS = pathlib.Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
LIVE = "--no-live" not in sys.argv

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

COUNTS_JS = """() => {
  const c = (el) => el ? +el.querySelector('.count').textContent : null;
  const rows = (sel) => [...document.querySelectorAll(sel)].map(r => [r.querySelector('.name').textContent, c(r)]);
  return { loose: c(document.querySelector('.row.loose')), bin: c(document.querySelector('.row.bin')),
           nb: rows('.row.nb'), sec: rows('.row.sec'),
           pages: [...document.querySelectorAll('.row.pg .name')].map(e => e.textContent) };
}"""

def counts(pg): return pg.evaluate(COUNTS_JS)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(60)
def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def menu(pg, label): pg.locator("#menu button", has_text=label).first.click()
def more(pg, kind, name=None, nth=0):
    loc = pg.locator(f".row.{kind}", has_text=name) if name else pg.locator(f".row.{kind}")
    loc.nth(nth).locator(".more").click()
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")

def creds():
    rows = [l for l in (ROOT / "LOGIN-LOCAL.md").read_text(encoding="utf-8").splitlines() if l.strip().startswith("|")]
    data = [r for r in rows[2:] if r.strip("| -")]
    cols = [c.strip().strip("`") for c in data[0].strip().strip("|").split("|")]
    return cols[1], cols[2]

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # ------------------------------------------------------------ local mode: the tree
        group[0] = "local"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        c = counts(pg)
        check("starts empty: Loose 0, Bin 0, no notebooks", c["loose"] == 0 and c["bin"] == 0 and not c["nb"], c)
        pg.click("#addNotebook"); type_name(pg, "Maths")
        pg.click(".secAdd"); type_name(pg, "Algebra")
        pg.click("#newPageBtn"); pg.click("#newPageBtn"); idle(pg)
        c = counts(pg)
        check("notebook, section, two pages made", c["nb"] == [["Maths", 2]] and c["sec"] == [["Algebra", 2]] and len(c["pages"]) == 2, c)
        check("untitled page shows Page + date", all(re.match(r"^Page \d{1,2} \w{3}$", p) for p in c["pages"]), c["pages"])
        more(pg, "nb", "Maths"); menu(pg, "Rename"); type_name(pg, "Maths 2026")
        more(pg, "sec", "Algebra"); menu(pg, "Rename"); type_name(pg, "Algebra 1")
        more(pg, "pg", nth=0); menu(pg, "Rename"); type_name(pg, "First")
        more(pg, "pg", nth=1); menu(pg, "Rename"); type_name(pg, "Second"); idle(pg)
        c = counts(pg)
        check("rename each", c["nb"] == [["Maths 2026", 2]] and c["sec"] == [["Algebra 1", 2]] and c["pages"] == ["First", "Second"], c)
        more(pg, "pg", "Second"); menu(pg, "Move to"); menu(pg, "Loose"); idle(pg)
        c = counts(pg)
        check("page 2 moved to Loose: counts", c["loose"] == 1 and c["sec"] == [["Algebra 1", 1]] and c["nb"] == [["Maths 2026", 1]], c)
        more(pg, "pg", "Second"); menu(pg, "Move to"); menu(pg, "Maths 2026 / Algebra 1"); idle(pg)
        c = counts(pg)
        check("moved back: counts", c["loose"] == 0 and c["sec"] == [["Algebra 1", 2]] and c["pages"] == ["First", "Second"], c)
        more(pg, "pg", "Second"); menu(pg, "Move up"); idle(pg)
        check("move up reorders", counts(pg)["pages"] == ["Second", "First"], counts(pg))
        more(pg, "pg", "Second"); menu(pg, "Move down"); idle(pg)
        more(pg, "pg", "Second"); menu(pg, "Bin"); idle(pg)
        c = counts(pg)
        check("binned: counts", c["bin"] == 1 and c["sec"] == [["Algebra 1", 1]] and c["pages"] == ["First"], c)
        pg.click(".row.bin")
        check("bin offers restore only", pg.locator(".binItem button").all_inner_texts() == ["Restore"], pg.locator(".binItem button").all_inner_texts())
        pg.click(".binItem button"); idle(pg)
        c = counts(pg)
        check("restored: counts", c["bin"] == 0 and c["sec"] == [["Algebra 1", 2]] and c["pages"] == ["First", "Second"], c)
        more(pg, "nb", "Maths 2026"); menu(pg, "Bin"); idle(pg)
        c = counts(pg)
        check("notebook binned with its pages", c["bin"] == 1 and not c["nb"] and not c["pages"], c)
        pg.click(".binItem button"); idle(pg)
        c = counts(pg)
        check("notebook restored with its pages", c["bin"] == 0 and c["nb"] == [["Maths 2026", 2]] and c["pages"] == ["First", "Second"], c)
        pg.locator(".row.pg", has_text="Second").click()
        before = counts(pg)
        pg.reload(); ready(pg)
        check("reload keeps it all", counts(pg) == before, [before, counts(pg)])
        check("open page remembered", pg.locator(".row.pg.open .name").inner_text() == "Second" and "Second" in pg.locator("#pageTitle b").inner_text())
        pg.evaluate("window.__pw.api.failNext(1)")
        more(pg, "pg", "First"); menu(pg, "Rename"); type_name(pg, "First again")
        pg.wait_for_timeout(400)
        check("failed write shows the toast", pg.locator("#toast.show").inner_text() == "Not saved, trying again")
        idle(pg); pg.reload(); ready(pg)
        check("retry saved it", "First again" in counts(pg)["pages"] and pg.evaluate("window.__pw.failed()") == 0)
        more(pg, "pg", "First again"); menu(pg, "Move to"); menu(pg, "Loose"); idle(pg)
        pg.click(".row.loose"); pg.click("#newPageBtn"); idle(pg)
        c = counts(pg)
        check("+ Page with Loose open lands in Loose", c["loose"] == 2, c)
        pg.click(".row.sec"); pg.click("#addBelow"); idle(pg)
        c = counts(pg)
        check("Add a page below lands in the open section", c["sec"] == [["Algebra 1", 2]] and c["loose"] == 2, c)
        check("no page errors (local)", not errs, errs)

        # ------------------------------------------------------------ backgrounds
        group[0] = "backgrounds"
        pg.locator(".row.pg").first.click()
        pg.click("#bgBtn"); menu(pg, "Grid"); idle(pg)
        xs = pg.evaluate("[...document.querySelectorAll('#sheet line.gv')].map(l => +l.getAttribute('x1'))")
        gaps = [round(xs[i + 1] - xs[i], 2) for i in range(len(xs) - 1)]
        check("grid: 21 squares across a portrait page", len(gaps) == 21, len(gaps))
        check("grid squares are 1 cm (37.80 px)", all(abs(g - 96 / 2.54) < 0.02 for g in gaps), set(gaps))
        pg.click("#bgBtn"); menu(pg, "Lined"); idle(pg)
        ys = pg.evaluate("[...document.querySelectorAll('#sheet line.ln')].map(l => +l.getAttribute('y1'))")
        check("lined draws lines 8 mm apart", len(ys) > 25 and all(abs(ys[i + 1] - ys[i] - 0.8 * 96 / 2.54) < 0.02 for i in range(len(ys) - 1)), len(ys))
        pg.click("#orientBtn"); idle(pg)
        sz = pg.evaluate("[document.getElementById('sheet').offsetWidth, document.getElementById('sheet').offsetHeight]")
        check("landscape toggle turns the page", sz == [1123, 794], sz)
        pg.reload(); ready(pg)
        check("background and orientation saved", pg.evaluate("document.getElementById('sheet').dataset.bg") == "lined"
              and pg.evaluate("document.getElementById('sheet').dataset.orientation") == "landscape")
        pg.click("#bgBtn"); menu(pg, "Blank"); pg.click("#orientBtn"); idle(pg)
        check("blank draws nothing", pg.evaluate("document.querySelectorAll('#sheet line').length") == 0)

        # ------------------------------------------------------------ tablet width
        group[0] = "tablet 1280x800"
        box = lambda s: pg.locator(s).bounding_box()
        t, d, tr, sh = box("#tree"), box("#desk"), box("#tray"), box("#sheet")
        check("tree, page and tray all visible", t["x"] >= 0 and 240 <= t["width"] <= 280 and tr["width"] == 56 and tr["x"] + 56 <= 1280.5 and sh["width"] > 0, [t, tr])
        check("page at zoom 1", pg.evaluate("document.getElementById('sheetWrap').dataset.zoom") == "1.000")
        check("page fits across with margins", sh["x"] - d["x"] >= 20 and (d["x"] + d["width"]) - (sh["x"] + sh["width"]) >= 20, [d, sh])
        check("undo and redo there, disabled", pg.evaluate("[...document.querySelectorAll('#tray button')].map(b => b.disabled)") == [True, True])
        check("no horizontal scroll (tablet)", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        ctx.close()

        # ------------------------------------------------------------ phone width
        group[0] = "phone 375x812"
        ctx = b.new_context(viewport={"width": 375, "height": 812}, has_touch=True, is_mobile=True)
        pg = ctx.new_page()
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("""() => { localStorage.setItem('penworks.local.v1', JSON.stringify({notebooks:[{id:'n1',name:'Uni 2026',position:0,deleted_at:null,created_at:'2026-10-24T10:00:00Z'}],
          sections:[{id:'s1',notebook_id:'n1',name:'MATH121',position:0,background:'grid',deleted_at:null,created_at:'2026-10-24T10:00:00Z'}],
          pages:[{id:'p1',section_id:'s1',title:'Limits',position:0,orientation:'portrait',background:'grid',deleted_at:null,created_at:'2026-10-24T10:00:00Z'},
                 {id:'p2',section_id:null,title:'',position:0,orientation:'portrait',background:'lined',deleted_at:null,created_at:'2026-10-24T10:00:00Z'}]})); }""")
        pg.reload(); ready(pg)
        t = pg.locator("#tree").bounding_box()
        check("tree is a drawer, closed", t["x"] + t["width"] <= 1, t)
        check("tray hidden on the phone", not pg.locator("#tray").is_visible())
        pg.tap("#menuBtn"); pg.wait_for_timeout(350)
        t = pg.locator("#tree").bounding_box()
        check("menu button slides the drawer in", t["x"] >= -1 and t["width"] > 200, t)
        if SHOTS: pg.screenshot(path=str(SHOTS / "phone-drawer.png"))
        pg.locator(".row.pg", has_text="Limits").tap(); pg.wait_for_timeout(350)
        t = pg.locator("#tree").bounding_box(); sh = pg.locator("#sheet").bounding_box()
        check("tapping a page opens it and closes the drawer", t["x"] + t["width"] <= 1 and pg.locator("#pageTitle b").inner_text() == "Limits", t)
        check("the page is visible", sh["x"] >= 0 and sh["x"] + sh["width"] <= 375 and sh["width"] > 300, sh)
        check("no horizontal scroll (phone)", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        if SHOTS: pg.screenshot(path=str(SHOTS / "phone-page.png"))
        ctx.close()

        # ------------------------------------------------------------ PWA
        group[0] = "pwa"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        man = pg.evaluate("fetch('./manifest.json').then(r=>r.json())")
        check("manifest loads", man.get("display") == "standalone" and man.get("name") == "PenWorks" and len(man.get("icons", [])) == 3, man)
        for ic in man["icons"]:
            st = pg.evaluate("(u)=>fetch(u).then(r=>r.status+' '+r.headers.get('content-type'))", ic["src"])
            check("icon " + ic["src"], st.startswith("200 image/png"), st)
        check("service worker active", pg.evaluate("navigator.serviceWorker.ready.then(r=>!!r.active)"))
        inst = ctx.new_cdp_session(pg).send("Page.getInstallabilityErrors")
        check("Chrome sees it as installable", not inst.get("installabilityErrors"), inst)
        pg.reload(); ready(pg); pg.wait_for_timeout(500)
        ctx.set_offline(True)
        pg.reload(); ready(pg)
        check("opens offline (local copy)", pg.title() == "PenWorks")
        ctx.set_offline(False)
        check("no page errors (pwa)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ live mode
        if LIVE:
            group[0] = "live"
            user, pwd = creds()
            start = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)).isoformat()
            ctx = b.new_context(viewport={"width": 1280, "height": 800})
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(BASE)
            pg.wait_for_selector("#login:not([hidden])")
            pg.fill("#lu", user); pg.fill("#lp", "not-the-password-123"); pg.click("#loginBtn")
            pg.wait_for_function("document.getElementById('loginMsg').textContent.length > 0", timeout=20000)
            check("wrong password: one plain line", pg.inner_text("#loginMsg") == "That username or password is not right."
                  and pg.locator("#app").is_hidden())
            pg.fill("#lp", pwd); pg.click("#loginBtn"); ready(pg)
            base_rows = pg.evaluate("window.__pw.api.loadAll().then(d => [d.notebooks.length, d.sections.length, d.pages.length])")
            check("logged in, database starts empty", base_rows == [0, 0, 0], base_rows)
            try:
                pg.click("#addNotebook"); type_name(pg, "U1 test")
                pg.click(".secAdd"); type_name(pg, "U1 section")
                pg.click("#newPageBtn"); idle(pg)
                pg.reload(); ready(pg)
                c = counts(pg)
                check("session kept; notebook, section, page saved to Supabase", c["nb"] == [["U1 test", 1]] and c["sec"] == [["U1 section", 1]], c)
                more(pg, "nb", "U1 test"); menu(pg, "Bin"); idle(pg)
                pg.reload(); ready(pg)
                c = counts(pg)
                check("notebook binned (after reload)", c["bin"] == 1 and not c["nb"], c)
                pg.click(".row.bin"); pg.click(".binItem button"); idle(pg)
                pg.reload(); ready(pg)
                c = counts(pg)
                check("notebook restored with its page (after reload)", c["bin"] == 0 and c["nb"] == [["U1 test", 1]], c)
                check("no failed writes", pg.evaluate("window.__pw.failed()") == 0)
            finally:
                left = pg.evaluate("""async (start) => {
                  const a = window.__pw.api, d = await a.loadAll(), mine = (r) => r.created_at >= start;
                  const ids = (rows) => rows.filter(mine).map(r => r.id);
                  for (const t of ['pages', 'sections', 'notebooks']) { const x = ids(d[t]); if (x.length) await a.remove(t, x); }
                  const e = await a.loadAll();
                  return [e.notebooks.length, e.sections.length, e.pages.length];
                }""", start)
                check("test rows deleted, database empty again", left == [0, 0, 0], left)
            check("no page errors (live)", not errs, errs)
            pg.click("#logoutBtn"); pg.wait_for_selector("#login:not([hidden])")
            check("log out returns to the login screen", True)
            ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
