# PenWorks U3d checks (the live mirror): headless Playwright (Python), the harness of tests/test_u3a.py.
# Run: python tests/test_u3d.py          (local mode only: ?local=1, the localStorage twin stands in for Supabase, and the
#                                          twin's in-memory channel stands in for Realtime: api.emitStroke plays the tablet)
#      python tests/test_u3d.py --live   (adds the live group: two browsers on the test login from PW_TEST_USER /
#                                          PW_TEST_PASS or the gitignored .env, never printed; it deletes every row it makes)
# Local groups: a remote INSERT shows within 1 s with nothing queued, no undo step and no picture; a remote DELETE takes
# it away; this device's own push echoed back stays one copy; an unknown DELETE does nothing; a selection clears when a
# remote change hits its page; a stroke for a page this tree does not have yet waits for the tree refresh; the tree
# refresh (60 s rule, a new note, a rename, the open note renamed and binned upstream, never during tick mode); a dropped
# channel catches up on coming back to the front; the channel's state after login and logout.
import sys, os, subprocess, time, pathlib, re
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8784
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
LIVE = "--live" in sys.argv
TOAST = "This note was moved to the bin on another device"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-26T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', bookmark: false, deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U3d', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Live', '2026-10-26T10:02:00Z'), N('n2', 'Other', '2026-10-26T10:01:00Z')],
    pages: [P('r1', 'n1', 0), P('r2', 'n1', 1), P('o1', 'n2', 0)] }));
}"""
# a stroke row the way another device writes it
ROW_JS = """([pid, y]) => ({ id: crypto.randomUUID(), page_id: pid, seq: Date.now() + Math.random(), kind: 'pen',
  style: { colour: '#0D0DFF', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[120, y], [260, y + 10], [400, y]] } })"""
EMIT_JS = "([t, r]) => window.__pw.api.emitStroke(t, r)"
PATHS_JS = "(i) => document.querySelectorAll(`#stack .sheet[data-index=\"${i}\"] svg.ink path`).length"
HIST_JS = "(n) => { const H = window.__pw.S.hist[n]; return H ? [H.u.length, H.r.length] : [0, 0]; }"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def twin(pg, pid): return pg.evaluate("(pid) => window.__pw.api.strokesOf([pid])", pid)
def mine(pg, pid): return pg.evaluate("(id) => window.__pw.ink.strokesOf(id)", pid)
def ids(pg, pid): return [r["id"] for r in mine(pg, pid)]
def cached(pg, pid): return pg.evaluate("(id) => window.__pw.store.cached(id)", pid)
def qlen(pg): return pg.evaluate("window.__pw.store.queueLength()")
def paths(pg, i): return pg.evaluate(PATHS_JS, i)
def row(pg, pid, y): return pg.evaluate(ROW_JS, [pid, y])
def emit(pg, t, r): pg.evaluate(EMIT_JS, [t, r])
def hist(pg, n): return pg.evaluate(HIST_JS, n)
def state(pg): return pg.evaluate("window.__pw.live.state()")
def stats(pg): return pg.evaluate("window.__pw.live.stats()")
def renders(pg): return pg.evaluate("window.__pw.snap().renders")
def visible(pg): pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
def refresh(pg): return pg.evaluate("window.__pw.refreshTree()")
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name):
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose")
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def draw(pg, i, y, x0=100, x1=400):
    pts = [(x0 + (x1 - x0) * k / 4, y) for k in range(5)]
    sx, sy = screen(pg, i, *pts[0]); pg.mouse.move(sx, sy); pg.mouse.down()
    for x, yy in pts[1:]:
        tx, ty = screen(pg, i, x, yy); pg.mouse.move(tx, ty, steps=6)
    pg.mouse.up(); pg.wait_for_timeout(30)
def go_page(pg, i):
    open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120); close_list(pg)
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def timed(pg, fn, ms=1000):
    t0 = time.time(); ok = until(pg, fn, ms, 20); return ok, int((time.time() - t0) * 1000)

def creds():
    u, p = os.environ.get("PW_TEST_USER"), os.environ.get("PW_TEST_PASS")
    env = ROOT / ".env"
    if (not u or not p) and env.exists():
        kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        u, p = kv.get("PW_TEST_USER", "").strip(), kv.get("PW_TEST_PASS", "").strip()
    return u, p

live_note = "live group skipped (run with --live)"
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []; warns = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: warns.append(m.text) if m.type in ("warning", "error") else None)
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)

        # ------------------------------------------------------------ the channel
        group[0] = "channel"
        check("live.state() is 'subscribed' after login", until(pg, lambda: state(pg) == "subscribed", 2000), state(pg))
        check("one subscribe so far", stats(pg)["subscribes"] == 1, stats(pg))

        # ------------------------------------------------------------ a remote INSERT
        group[0] = "remote insert"
        open_note(pg, "Live")
        idle(pg)
        r0 = renders(pg)
        undo_off = pg.locator("#undoBtn").is_disabled()
        a = row(pg, "r1", 200)
        emit(pg, "INSERT", a)
        ok, ms = timed(pg, lambda: paths(pg, 1) == 1, 1000)
        check("within 1 s the page shows the stroke", ok, [paths(pg, 1), f"{ms} ms"])
        check("the mirror has it on page r1", pg.evaluate("(id) => window.__pw.store.pageOf(id)", a["id"]) == "r1")
        idle(pg)
        check("the device cache has it", [r["id"] for r in (cached(pg, "r1") or [])] == [a["id"]], cached(pg, "r1"))
        check("nothing queued: queueLength() is 0", qlen(pg) == 0 and pg.evaluate("window.__pw.store.queued()") == [])
        check("the undo button is still disabled (no undo step)", undo_off and pg.locator("#undoBtn").is_disabled() and hist(pg, "n1") == [0, 0], hist(pg, "n1"))
        open_list(pg)
        check("the page's thumb shows it", pg.locator("#plThumbs .thumbP[data-index='1'] .paper > svg.thumbInk path").count() == 1)
        b2 = row(pg, "r1", 320)
        emit(pg, "INSERT", b2)
        ok = until(pg, lambda: pg.locator("#plThumbs .thumbP[data-index='1'] .paper > svg.thumbInk path").count() == 2, 1000)
        check("a second one while the list is open: the thumb follows", ok)
        close_list(pg)
        check("no page picture becomes due from it", "r1" not in pg.evaluate("window.__pw.snap().due"), pg.evaluate("window.__pw.snap()"))
        pg.wait_for_timeout(4600)
        check("4.6 s later snapStats() shows no new render", renders(pg) == r0 and "r1" not in pg.evaluate("window.__pw.snap().due"), [r0, renders(pg)])
        check("no toast", not pg.locator("#toast.show").count())

        # ------------------------------------------------------------ a remote DELETE
        group[0] = "remote delete"
        emit(pg, "DELETE", {"id": b2["id"]})
        ok, ms = timed(pg, lambda: paths(pg, 1) == 1, 1000)
        check("within 1 s the stroke is gone", ok and b2["id"] not in ids(pg, "r1"), [paths(pg, 1), f"{ms} ms"])
        idle(pg)
        check("the mirror and the cache follow", pg.evaluate("(id) => window.__pw.store.pageOf(id)", b2["id"]) is None
              and [r["id"] for r in cached(pg, "r1")] == [a["id"]])
        check("the undo stack unchanged, nothing queued", hist(pg, "n1") == [0, 0] and pg.locator("#undoBtn").is_disabled() and qlen(pg) == 0)

        # ------------------------------------------------------------ this device's own push coming back
        group[0] = "own echo"
        draw(pg, 1, 500); idle(pg)
        own = mine(pg, "r1")[-1]
        check("drawn here: two strokes, one undo step, the twin has it", len(mine(pg, "r1")) == 2 and hist(pg, "n1") == [1, 0]
              and own["id"] in [r["id"] for r in twin(pg, "r1")])
        emit(pg, "INSERT", own); pg.wait_for_timeout(300)
        check("its own INSERT echoed back: the page still has ONE copy", paths(pg, 1) == 2 and ids(pg, "r1").count(own["id"]) == 1
              and len(twin(pg, "r1")) == 2, [paths(pg, 1), ids(pg, "r1")])
        pg.click("#undoBtn"); idle(pg)
        check("undo: gone here and in the twin", paths(pg, 1) == 1 and own["id"] not in [r["id"] for r in twin(pg, "r1")])
        emit(pg, "INSERT", own)                                                  # a late echo of the first push
        pg.wait_for_timeout(300)
        check("a late echo of the undone stroke's first push does not bring it back", paths(pg, 1) == 1 and own["id"] not in ids(pg, "r1"), ids(pg, "r1"))
        pg.evaluate("(id) => window.__pw.api.putStrokes([id], [])", own["id"])   # the twin as the undo left it
        pg.click("#redoBtn"); idle(pg)
        emit(pg, "DELETE", {"id": own["id"]}); pg.wait_for_timeout(300)
        check("redo, then a late echo of the undo's DELETE: the stroke stays", paths(pg, 1) == 2 and own["id"] in ids(pg, "r1"), ids(pg, "r1"))
        pg.evaluate("(r) => window.__pw.api.putStrokes([], [r])", own)          # the twin as the redo left it
        check("the twin and the page agree", sorted(ids(pg, "r1")) == sorted(r["id"] for r in twin(pg, "r1")))

        # ------------------------------------------------------------ a DELETE for an id this device never had
        group[0] = "unknown delete"
        before = ids(pg, "r1"); n_err = len(errs); n_warn = len(warns)
        emit(pg, "DELETE", {"id": "00000000-0000-4000-8000-000000000000"}); pg.wait_for_timeout(300)
        check("nothing happens: the page as it was, nothing queued", ids(pg, "r1") == before and qlen(pg) == 0)
        check("no error, no warning", len(errs) == n_err and len(warns) == n_warn, (errs + warns)[-2:])
        u_before = hist(pg, "n1")
        c = row(pg, "r1", 650); emit(pg, "INSERT", c); until(pg, lambda: paths(pg, 1) == 3, 1000)
        emit(pg, "DELETE", {"id": c["id"]}); until(pg, lambda: paths(pg, 1) == 2, 1000)
        check("with a step of hers on the stack, a remote INSERT and DELETE leave it as it was", hist(pg, "n1") == u_before, [u_before, hist(pg, "n1")])

        # ------------------------------------------------------------ a selection on the page
        group[0] = "selection"
        d1, d2 = row(pg, "r1", 800), row(pg, "r1", 900)
        emit(pg, "INSERT", d1); emit(pg, "INSERT", d2)
        until(pg, lambda: paths(pg, 1) == 4, 1000)
        pg.evaluate("window.__pw.ink.selectAll('r1')")
        sel = pg.evaluate("window.__pw.ink.selection()")
        check("a selection on page 1 holds the remote strokes", sel and d2["id"] in sel["ids"], sel)
        emit(pg, "DELETE", {"id": d2["id"]})
        ok = until(pg, lambda: pg.evaluate("window.__pw.ink.selection()") is None and paths(pg, 1) == 3, 1000)
        check("a remote DELETE of a selected stroke: the selection is cleared", ok, pg.evaluate("window.__pw.ink.selection()"))
        check("its box and chips are gone", pg.locator("#stack g.sel").count() == 0 and pg.locator(".selChips").count() == 0)
        pg.click("#tool-pen"); pg.wait_for_timeout(50)

        # ------------------------------------------------------------ a page this tree does not have yet
        group[0] = "page not in the tree"
        pg.evaluate("""() => window.__pw.api.insert('pages', { id: 'r9', note_id: 'n1', position: 2, orientation: 'portrait', background: 'lined' })""")
        e = row(pg, "r9", 300)
        n_err = len(errs)
        emit(pg, "INSERT", e); pg.wait_for_timeout(400)
        check("a remote INSERT for a page not in the tree: ignored, no error", pg.evaluate("(id) => window.__pw.store.pageOf(id)", e["id"]) is None
              and len(errs) == n_err and pg.locator("#stack .sheet").count() == 2)
        h_before = hist(pg, "n1")
        got = refresh(pg)
        check("__pw.refreshTree() runs", got is True, got)
        ok = until(pg, lambda: pg.locator("#stack .sheet").count() == 3 and paths(pg, 3) == 1, 2000)
        check("the page appears in the note and its stroke comes in", ok, [pg.locator("#stack .sheet").count(), paths(pg, 3)])
        check("the note stays open, its undo stack kept", pg.locator("#noteView").is_visible() and hist(pg, "n1") == h_before, hist(pg, "n1"))
        check("nothing queued for it", qlen(pg) == 0)

        # ------------------------------------------------------------ the tree from the database again
        group[0] = "tree refresh"
        go_page(pg, 2)
        cur = pg.evaluate("window.__pw.current()"); top = pg.evaluate("document.getElementById('stack').style.transform")
        h_before = hist(pg, "n1")
        pg.evaluate("() => window.__pw.api.update('notes', ['n1'], { name: 'Live renamed' })")
        refresh(pg)
        ok = until(pg, lambda: pg.inner_text("#noteName") == "Live renamed", 2000)
        check("the open note renamed upstream: the header follows", ok, pg.inner_text("#noteName"))
        check("still open, same page, same scroll, same undo stack", pg.locator("#noteView").is_visible() and pg.evaluate("window.__pw.current()") == cur
              and pg.evaluate("document.getElementById('stack').style.transform") == top and hist(pg, "n1") == h_before,
              [cur, pg.evaluate("window.__pw.current()"), hist(pg, "n1")])
        # tick mode holds the refresh off; it runs 5 s later
        open_list(pg); pg.click("#plSelect"); pg.wait_for_timeout(50)
        pg.evaluate("() => window.__pw.api.update('notes', ['n1'], { name: 'Live again' })")
        got = refresh(pg)
        check("during tick mode refreshTree() does nothing", got is False and pg.inner_text("#noteName") == "Live renamed", got)
        pg.click("#plDone"); close_list(pg)
        ok = until(pg, lambda: pg.inner_text("#noteName") == "Live again", 6500, 100)
        check("tried again 5 s later: it lands", ok, pg.inner_text("#noteName"))
        back(pg)
        frow(pg, "U3d").click(); pg.wait_for_timeout(80)
        pg.evaluate("() => window.__pw.api.insert('notes', { id: 'n3', folder_id: 'f1', name: 'Fresh' })")
        visible(pg); pg.wait_for_timeout(400)
        check("under a minute since the last read: coming to the front does not read the tree", pg.locator("#grid .card[data-id='n3']").count() == 0)
        pg.evaluate("window.__pw.lastLoad = Date.now() - 61000")
        visible(pg)
        ok = until(pg, lambda: pg.locator("#grid .card[data-id='n3']").count() == 1, 2000)
        check("61 s old, visibilitychange: the grid shows the new note", ok)
        check("its last read is fresh again", pg.evaluate("Date.now() - window.__pw.lastLoad") < 3000)
        pg.evaluate("() => window.__pw.api.update('notes', ['n3'], { name: 'Renamed' })")
        refresh(pg)
        ok = until(pg, lambda: pg.locator("#grid .card[data-id='n3'] .name").inner_text() == "Renamed", 2000)
        check("renamed in the twin, refresh: the card shows the new name", ok)
        open_note(pg, "Live again")
        pg.evaluate("() => window.__pw.api.update('notes', ['n1'], { deleted_at: new Date().toISOString() })")
        refresh(pg)
        ok = until(pg, lambda: pg.locator("#listView").is_visible() and pg.locator("#noteView").is_hidden(), 2000)
        check("the OPEN note binned upstream: back in the folder view", ok)
        check("with the one toast", pg.locator("#toast.show").count() == 1 and pg.inner_text("#toast") == TOAST, pg.inner_text("#toast"))
        check("the binned note is in the Bin, not in the grid", pg.locator("#grid .card[data-id='n1']").count() == 0
              and pg.evaluate("window.__pw.S.notes.find(n => n.id === 'n1').deleted_at") is not None)

        # ------------------------------------------------------------ a dropped channel catches up
        group[0] = "gaps"
        open_note(pg, "Other"); idle(pg)
        g0 = stats(pg)
        pg.evaluate("window.__pw.live.simulateDrop()")
        check("simulateDrop: live.state() is 'closed'", state(pg) == "closed")
        f = row(pg, "o1", 250)
        emit(pg, "INSERT", f); pg.wait_for_timeout(400)
        check("an event while it is closed is missed (the twin has the row)", paths(pg, 1) == 0 and len(twin(pg, "o1")) == 1)
        visible(pg)
        ok, ms = timed(pg, lambda: paths(pg, 1) == 1, 1500)
        check("visibilitychange: reconcile runs and the page catches up", ok, [paths(pg, 1), f"{ms} ms"])
        check("the channel is open again", until(pg, lambda: state(pg) == "subscribed", 1000) and stats(pg)["subscribes"] == g0["subscribes"] + 1, stats(pg))
        check("the gap check ran", stats(pg)["gaps"] > g0["gaps"], [g0, stats(pg)])
        idle(pg)
        check("caught up without a queue or an undo step", qlen(pg) == 0 and pg.locator("#undoBtn").is_disabled())
        g = row(pg, "o1", 400); emit(pg, "INSERT", g)
        check("live again: the next row shows within 1 s", until(pg, lambda: paths(pg, 1) == 2, 1000))
        pg.wait_for_timeout(4500)
        check("no picture from the caught-up rows", "o1" not in pg.evaluate("window.__pw.snap().due"), pg.evaluate("window.__pw.snap()"))

        # ------------------------------------------------------------ nothing new on the screen
        group[0] = "nothing on screen"
        check("no live badge, dot or text", pg.evaluate("""() => document.querySelectorAll('[id*="live" i], [class*="live" i]').length""") == 0
              and "live" not in pg.inner_text("#noteBar").lower())
        check("no sync button", pg.evaluate("""() => [...document.querySelectorAll('button')].filter(b =>
          /\\b(sync|refresh|live)\\b/i.test(b.textContent + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.title || ''))).length""") == 0)
        check("no page errors (local)", not errs, errs)
        back(pg)

        # ------------------------------------------------------------ logout
        group[0] = "logout"
        with pg.expect_navigation():
            st = pg.evaluate("() => { document.getElementById('logoutBtn').click(); return window.__pw.live.state(); }")
        check("live.state() is 'closed' after logout", st == "closed", st)
        ready(pg)
        check("after the reload (local twin: signed in again) it is 'subscribed'", until(pg, lambda: state(pg) == "subscribed", 2000), state(pg))

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7p" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7p", "pw-v7p" in keys, keys)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("the shell lists ./js/live.js", "./js/live.js" in swt)
        cdn = re.search(r"const CDN = \[(.*?)\];", swt)
        check("supabase.co is not a cached host: every Supabase request goes straight to the network",
              cdn and "supabase" not in cdn.group(1) and "if (url.origin !== location.origin) {" in swt, cdn.group(1) if cdn else swt[:200])
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in
                       ["./js/live.js", "./js/store.js", "./js/api.js", "./js/local-backend.js", "./js/ink.js", "./js/snap.js", "./js/app.js", "./sw.js"])
        srcs += (ROOT / "tests" / "test_u3d.py").read_text(encoding="utf-8")
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("app.js imports live.js", "from './live.js'" in srcs)
        ctx.close()

        # ------------------------------------------------------------ live (Supabase), --live only
        if LIVE:
            group[0] = "live"
            user, pwd = creds()
            if not user or not pwd:
                live_note = "live group SKIPPED: no test login (PW_TEST_USER / PW_TEST_PASS or .env)"
            else:
                live_note = "live group ran"
                ctx = b.new_context(viewport={"width": 1280, "height": 800})
                ctx2 = b.new_context(viewport={"width": 1280, "height": 800})
                pg = ctx.new_page(); pg2 = ctx2.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e))); pg2.on("pageerror", lambda e: errs.append(str(e)))
                for p_ in (pg, pg2):
                    p_.goto(BASE); p_.wait_for_selector("#login:not([hidden])")
                    p_.fill("#lu", user); p_.fill("#lp", pwd); p_.click("#loginBtn"); ready(p_)
                made = {}
                try:
                    check("A's channel is subscribed", until(pg, lambda: state(pg) == "subscribed", 10000), state(pg))
                    pg.click("#addFolder"); type_name(pg, "U3d test")
                    frow(pg, "U3d test").locator(".more").click(); menu(pg, "New note")
                    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
                    made = pg.evaluate("""() => { const S = window.__pw.S, n = S.notes.find(x => x.id === S.openNote);
                      return { f: n.folder_id, n: n.id, p: S.pages.find(x => x.note_id === n.id).id }; }""")
                    pg.click("#noteName .nn"); type_name(pg, "U3d note")
                    idle(pg)
                    # B is older than the folder and the note: its tree refresh brings them
                    pg2.evaluate("window.__pw.lastLoad = Date.now() - 61000"); visible(pg2)
                    until(pg2, lambda: frow(pg2, "U3d test").count() == 1, 8000)
                    frow(pg2, "U3d test").click(); open_note(pg2, "U3d note")
                    check("B's channel is subscribed", until(pg2, lambda: state(pg2) == "subscribed", 10000), state(pg2))
                    draw(pg, 1, 200)
                    sid = mine(pg, made["p"])[-1]["id"]
                    on_b = lambda: sid in [r["id"] for r in pg2.evaluate("(id) => window.__pw.ink.strokesOf(id)", made["p"])]
                    ok, ms = timed(pg2, on_b, 3000)
                    check("A draws one stroke: within 3 s B's page shows it", ok and paths(pg2, 1) == 1, [paths(pg2, 1), f"{ms} ms"])
                    check("B queued nothing for it", qlen(pg2) == 0)
                    pg.click("#undoBtn")
                    ok, ms = timed(pg2, lambda: not on_b(), 3000)
                    check("A undoes: within 3 s it is gone on B", ok and paths(pg2, 1) == 0, [paths(pg2, 1), f"{ms} ms"])
                finally:
                    if made:
                        idle(pg)
                        ctx2.close()
                        left = pg.evaluate("""async (ids) => {
                          const a = window.__pw.api;
                          await a.removeSnapshots([window.__pw.S.user.id + '/' + ids.p + '.webp']).catch(() => {});
                          await a.remove('pages', [ids.p]);
                          const strokes = (await a.strokesOf([ids.p])).length;
                          await a.remove('notes', [ids.n]); await a.remove('folders', [ids.f]);
                          const d = await a.loadAll();
                          return [strokes, d.folders.filter(r => r.id === ids.f).length, d.notes.filter(r => r.id === ids.n).length, d.pages.filter(r => r.id === ids.p).length]; }""", made)
                        check("clean-up: no strokes for the page, every row the test made is gone", left == [0, 0, 0, 0], left)
                    else:
                        ctx2.close()
                check("no page errors (live)", not errs, errs)
                ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g_, n, ok, info in res:
    if g_ not in groups: groups.append(g_)
    if not ok: print(f"FAIL [{g_}] {n}  -> {str(info)[:300]}")
print()
for g_ in groups:
    rs = [r for r in res if r[0] == g_]
    print(f"{g_}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
print(live_note)
sys.exit(0 if all(r[2] for r in res) else 1)
