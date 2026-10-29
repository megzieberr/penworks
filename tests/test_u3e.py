# PenWorks U3e checks (tree writes offline-safe): headless Playwright (Python), same harness as tests/test_u3a.py.
# Run: python tests/test_u3e.py          (local mode only: ?local=1, the localStorage twin stands in for Supabase)
#      python tests/test_u3e.py --live   (adds the live group: the test login from PW_TEST_USER / PW_TEST_PASS or the
#                                         gitignored .env, never printed; it deletes every row it makes)
# Local groups: offline, a new note, a new page, two strokes, a rename and a bookmark are all on the screen and queued,
# and still there after an offline reload (the tree snapshot plus the queue); online, they reach the twin in order (note,
# page, strokes); a failed write retries with no toast; a refused write is dropped after the third try with one toast;
# a page made and deleted offline leaves nothing behind; the tree refresh keeps a row a queued change touches; idle()
# waits for both queues; the snapshot's size for her tree and for 50 notes x 20 pages.
import sys, os, subprocess, time, pathlib, re, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8785
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
LIVE = "--live" in sys.argv

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-26T10:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U3e', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Base', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [{ id: 'q1', note_id: 'n1', position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t }] }));
}"""
# the twin's tables read straight from localStorage (its loadAll answers nothing while the browser is offline)
TWIN_JS = "() => JSON.parse(localStorage.getItem('penworks.local.v2'))"
DOT_JS = "() => { const d = document.getElementById('saveDot'); return [d.dataset.state, d.title]; }"
PATHS_JS = "(i) => document.querySelectorAll(`#stack .sheet[data-index=\"${i}\"] svg.ink path`).length"
MARK_JS = "(i) => !!document.querySelector(`#stack .sheet[data-index=\"${i}\"] > .bookmarkTab`)"
LOGS_JS = """() => { window.__dotLog = []; window.__toastLog = [];
  if (window.__logsOn) return; window.__logsOn = true;            // one pair of observers per page load
  new MutationObserver(() => window.__dotLog.push(document.getElementById('saveDot').dataset.state))
    .observe(document.getElementById('saveDot'), { attributes: true, attributeFilter: ['data-state'] });
  new MutationObserver(() => window.__toastLog.push(document.getElementById('toast').textContent))
    .observe(document.getElementById('toast'), { childList: true, characterData: true, subtree: true }); }"""
# rows shaped like the live tables' answer (uuid ids, owner, microsecond stamps, picture paths)
SYNTH_JS = """([nf, nn, np]) => {
  const u = () => crypto.randomUUID(), owner = u(), ts = (k) => new Date(Date.UTC(2026, 9, 26, 10, 0, k)).toISOString().replace('Z', '123+00:00');
  const folders = [], notes = [], pages = [];
  for (let i = 0; i < nf; i++) folders.push({ id: u(), owner_id: owner, parent_id: i && i % 3 === 0 ? folders[0].id : null, name: 'Folder ' + i,
    colour: '#3A86D6', position: i, deleted_at: null, created_at: ts(i), updated_at: ts(i) });
  for (let i = 0; i < nn; i++) {
    const nid = u(), first = u();
    notes.push({ id: nid, owner_id: owner, folder_id: folders[i % nf].id, name: 'Note number ' + i, pinned: i === 0,
      cover_path: owner + '/' + first + '.webp', deleted_at: null, created_at: ts(i), updated_at: ts(i + 1) });
    for (let k = 0; k < np(i); k++) pages.push({ id: k ? u() : first, owner_id: owner, note_id: nid, position: k, orientation: 'portrait',
      background: 'grid', bookmark: k === 1, snapshot_path: owner + '/' + (k ? u() : first) + '.webp', snapshot_at: ts(k), flagged: false,
      deleted_at: null, created_at: ts(k), updated_at: ts(k + 2) });
  }
  return { folders, notes, pages };
}"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def twin(pg): return pg.evaluate(TWIN_JS)
def twin_strokes(pg, pid): return [s for s in twin(pg)["strokes"] if s["page_id"] == pid]
def tlen(pg): return pg.evaluate("window.__pw.treeq.length()")
def tqlen(pg): return pg.evaluate("window.__pw.treeq.queueLength()")
def tcalls(pg): return [o["call"] for o in pg.evaluate("window.__pw.treeq.queued()")]
def qlen(pg): return pg.evaluate("window.__pw.store.queueLength()")
def dot(pg): return pg.evaluate(DOT_JS)
def paths(pg, i): return pg.evaluate(PATHS_JS, i)
def marked(pg, i): return pg.evaluate(MARK_JS, i)
def failed(pg): return pg.evaluate("window.__pw.failed()")
def calllog(pg): return pg.evaluate("window.__pw.api.callLog()")
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name):
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose")
def thumb_menu(pg, i):
    open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(button="right")
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def go_page(pg, i):
    open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(120); close_list(pg)
def draw(pg, i, y, x0=100, x1=400):
    pts = [(x0 + (x1 - x0) * k / 4, y) for k in range(5)]
    sx, sy = screen(pg, i, *pts[0]); pg.mouse.move(sx, sy); pg.mouse.down()
    for x, yy in pts[1:]:
        tx, ty = screen(pg, i, x, yy); pg.mouse.move(tx, ty, steps=6)
    pg.mouse.up(); pg.wait_for_timeout(30)
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")
def offline(pg): pg.context.set_offline(True); pg.evaluate("window.dispatchEvent(new Event('offline'))"); pg.wait_for_timeout(50)
def online(pg): pg.context.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))")
def seed(pg): pg.evaluate(SEED_JS); pg.reload(); ready(pg); pg.wait_for_timeout(100)
def note_name(pg, nid): return pg.evaluate("(id) => (window.__pw.S.notes.find(n => n.id === id) || {}).name", nid)
def first_index(log, call, table, rid):
    for k, e in enumerate(log):
        if e["call"] == call and e["table"] == table and rid in e["ids"]: return k
    return -1

def creds():
    u, p = os.environ.get("PW_TEST_USER"), os.environ.get("PW_TEST_PASS")
    env = ROOT / ".env"
    if (not u or not p) and env.exists():
        kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        u, p = kv.get("PW_TEST_USER", "").strip(), kv.get("PW_TEST_PASS", "").strip()
    return u, p

sizes = ""
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
        pg.on("console", lambda m: warns.append(m.text) if m.type == "warning" else None)
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        seed(pg)

        # ------------------------------------------------------------ offline: all of it on the screen, all of it queued
        group[0] = "offline"
        check("the dot starts saved, the tree queue is empty", dot(pg)[0] == "saved" and tlen(pg) == 0, [dot(pg), tlen(pg)])
        offline(pg)
        frow(pg, "U3e").click(); pg.click("#newNote"); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
        nid = pg.evaluate("window.__pw.S.openNote")
        pg.click("#addPageBtn"); pg.click("#menu button:text-is('Page')"); pg.wait_for_timeout(150)
        pids = pg.evaluate("(n) => window.__pw.S.pages.filter(p => p.note_id === n).sort((a, b) => a.position - b.position).map(p => p.id)", nid)
        go_page(pg, 2)
        draw(pg, 2, 200); pg.wait_for_timeout(400); draw(pg, 2, 320)
        pg.click("#noteName .nn"); type_name(pg, "Offline note")
        pg.click("#noteMore"); menu(pg, "Bookmark"); pg.wait_for_timeout(100)
        pg.wait_for_timeout(200)
        check("a new note with two pages", len(pids) == 2, pids)
        check("the screen: the note in the side list, its 2 pages, 2 strokes on page 2, the bookmark tab on page 2",
              nrow(pg, "Offline note").count() == 1 and pg.locator("#stack .sheet").count() == 2 and paths(pg, 2) == 2 and marked(pg, 2),
              [nrow(pg, "Offline note").count(), pg.locator("#stack .sheet").count(), paths(pg, 2), marked(pg, 2)])
        calls = tcalls(pg)
        check("the tree queue holds 5 ops: createNote, createPage, createPage, renameNote, setBookmark (no coalescing)",
              tlen(pg) == 5 and calls == ["createNote", "createPage", "createPage", "renameNote", "setBookmark"], calls)
        check("kept on the device: 5 in its IndexedDB queue", tqlen(pg) == 5, tqlen(pg))
        sq = qlen(pg); st = dot(pg)
        check("the dot is waiting, the title counts both queues", st[0] == "waiting" and f"{5 + sq} changes to send" in st[1], [st, sq])
        tw = twin(pg)
        check("the twin has none of it (no note, no page, no strokes)", not [n for n in tw["notes"] if n["id"] == nid]
              and not [p for p in tw["pages"] if p["id"] in pids] and not twin_strokes(pg, pids[1]), [len(tw["notes"]), len(tw["pages"])])
        check("no toast about saving", not [t for t in pg.evaluate("[document.getElementById('toast').textContent]") if "saved" in t.lower()])
        pg.reload(); ready(pg); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
        check("offline reload: the app opens on the note (the tree snapshot plus the queue)",
              pg.evaluate("window.__pw.S.openNote") == nid and pg.inner_text("#noteName") == "Offline note", [pg.evaluate("window.__pw.S.openNote"), pg.inner_text("#noteName")])
        check("offline reload: 2 pages, 2 strokes on page 2, the bookmark tab on page 2",
              pg.locator("#stack .sheet").count() == 2 and until(pg, lambda: paths(pg, 2) == 2, 2000) and marked(pg, 2),
              [pg.locator("#stack .sheet").count(), paths(pg, 2), marked(pg, 2)])
        check("offline reload: still 5 queued, the dot still waiting", tlen(pg) == 5 and tqlen(pg) == 5 and dot(pg)[0] == "waiting", [tlen(pg), dot(pg)])
        check("offline reload: the side list shows it under U3e", nrow(pg, "Offline note").count() == 1)

        # ------------------------------------------------------------ online: it all goes up, in order
        group[0] = "online"
        mark = len(calllog(pg))
        online(pg); t0 = time.time()
        def landed():
            tw = twin(pg)
            n = [x for x in tw["notes"] if x["id"] == nid]
            p2 = [x for x in tw["pages"] if x["id"] == pids[1]]
            return (n and n[0]["name"] == "Offline note" and p2 and p2[0]["bookmark"] is True
                    and len([x for x in tw["pages"] if x["id"] == pids[0]]) == 1 and len(twin_strokes(pg, pids[1])) == 2 and dot(pg)[0] == "saved")
        ok = until(pg, landed, 4000)
        check("within 4 s the twin has the note (its name), both pages (page 2 bookmarked), the 2 strokes, the dot saved",
              ok, [round(time.time() - t0, 2), dot(pg)])
        log = calllog(pg)[mark:]
        i_n, i_p1, i_p2, i_s = (first_index(log, "insert", "notes", nid), first_index(log, "insert", "pages", pids[0]),
                                first_index(log, "insert", "pages", pids[1]), first_index(log, "putStrokes", "strokes", pids[1]))
        check("in order: createNote, then createPage, then createPage, then putStrokes", -1 < i_n < i_p1 < i_p2 < i_s, [i_n, i_p1, i_p2, i_s])
        check("both queues empty on the device", tqlen(pg) == 0 and qlen(pg) == 0, [tqlen(pg), qlen(pg)])
        check("nothing dropped", failed(pg) == 0)
        back(pg)

        # ------------------------------------------------------------ a failed write: the dot, never a toast
        group[0] = "retry"
        seed(pg)
        pg.evaluate(LOGS_JS)
        pg.evaluate("window.__pw.api.failNext(1)")
        nrow(pg, "Base").locator(".more").click(); menu(pg, "Rename"); type_name(pg, "Retry name")
        ok = until(pg, lambda: [n for n in twin(pg)["notes"] if n["id"] == "n1"][0]["name"] == "Retry name" and dot(pg)[0] == "saved", 6000)
        dl, tl = pg.evaluate("window.__dotLog"), pg.evaluate("window.__toastLog")
        check("failNext(1) on a rename: it lands on the retry", ok, dl)
        check("the dot passed waiting on the way", "waiting" in dl and dl[-1] == "saved", dl)
        check("no toast at all", tl == [], tl)
        check("__pw.failed() is 0", failed(pg) == 0)

        # ------------------------------------------------------------ a refused write: dropped after the third try
        group[0] = "refused"
        pg.evaluate(LOGS_JS)
        n_warn = len([w for w in warns if "42501" in w])
        pg.evaluate("window.__pw.api.refuseNext(3)")
        nrow(pg, "Retry name").locator(".more").click(); menu(pg, "Rename"); type_name(pg, "Refused name")
        check("on the screen at once", note_name(pg, "n1") == "Refused name")
        ok = until(pg, lambda: failed(pg) == 1, 12000)
        tl = [t for t in pg.evaluate("window.__toastLog") if t]
        check("after the third try the op is dropped: __pw.failed() = 1, the queue empty", ok and tlen(pg) == 0 and tqlen(pg) == 0, [failed(pg), tlen(pg)])
        check("exactly one toast: 'A change could not be saved: a rename'", tl == ["A change could not be saved: a rename"], tl)
        check("the dot was red while it was refused", "refused" in pg.evaluate("window.__dotLog"), pg.evaluate("window.__dotLog"))
        check("one console line with the code (42501)", len([w for w in warns if "42501" in w]) - n_warn == 1, warns[-2:])
        check("the twin kept the server's name", [n for n in twin(pg)["notes"] if n["id"] == "n1"][0]["name"] == "Retry name")
        pg.evaluate("window.__pw.refreshTree()")
        ok = until(pg, lambda: note_name(pg, "n1") == "Retry name" and nrow(pg, "Retry name").count() == 1, 3000)
        check("after __pw.refreshTree() the screen shows the server's name", ok, note_name(pg, "n1"))
        check("the dot is saved again", until(pg, lambda: dot(pg)[0] == "saved", 2000), dot(pg))
        pg.evaluate("window.__pw.api.refuseNext(0)")

        # ------------------------------------------------------------ a page made and deleted for good while offline
        group[0] = "made and deleted offline"
        open_note(pg, "Retry name")
        offline(pg)
        pg.click("#addPageBtn"); pg.click("#menu button:text-is('Page')"); pg.wait_for_timeout(150)
        pid = pg.evaluate("() => window.__pw.S.pages.filter(p => p.note_id === 'n1').sort((a, b) => a.position - b.position)[1].id")
        thumb_menu(pg, 2); menu(pg, "Delete"); close_list(pg); pg.wait_for_timeout(100)
        calls = tcalls(pg)
        check("both queued: createPage, then deletePage", "createPage" in calls and "deletePage" in calls
              and calls.index("createPage") < calls.index("deletePage"), calls)
        mark = len(calllog(pg))
        online(pg)
        ok = until(pg, lambda: tqlen(pg) == 0 and not [p for p in twin(pg)["pages"] if p["id"] == pid], 4000)
        log = calllog(pg)[mark:]
        check("online: the twin ends with no such page, queueLength() 0", ok, [tqlen(pg), [p["id"] for p in twin(pg)["pages"]]])
        check("the insert and then the delete both landed", -1 < first_index(log, "insert", "pages", pid) < first_index(log, "remove", "pages", pid), log)
        check("no error: nothing more dropped (still the 1 refused rename), the stroke queue empty, the dot saved", failed(pg) == 1 and qlen(pg) == 0
              and until(pg, lambda: dot(pg)[0] == "saved", 2000), [failed(pg), qlen(pg), dot(pg)])
        back(pg)

        # ------------------------------------------------------------ the tree refresh while an op is pending
        group[0] = "refresh while pending"
        pg.evaluate("window.__pw.treeq.hold(true)")
        frow(pg, "U3e").click(); pg.click("#newNote"); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(100)
        held_note = pg.evaluate("window.__pw.S.openNote")
        back(pg)
        check("held: 2 ops queued, the twin lacks the note", tlen(pg) == 2 and not [n for n in twin(pg)["notes"] if n["id"] == held_note], tlen(pg))
        pg.evaluate("window.__pw.api.renameNote('n1', 'Other device')")       # another device renames a note meanwhile
        got = pg.evaluate("window.__pw.refreshTree()")
        check("__pw.refreshTree() with the queue holding changes: does nothing (false), the note stays",
              got is False and nrow(pg, "Untitled").count() == 1, got)
        pg.evaluate("async () => window.__pw.mergeTree(await window.__pw.api.loadAll())")
        on_screen = pg.evaluate("(id) => [!!window.__pw.S.notes.find(n => n.id === id), window.__pw.S.pages.filter(p => p.note_id === id).length]", held_note)
        check("mergeTree with the twin's tree (which lacks it): the pending note and its page stay", on_screen == [True, 1], on_screen)
        check("... and the merge did run: the other device's rename shows", note_name(pg, "n1") == "Other device" and nrow(pg, "Other device").count() == 1,
              note_name(pg, "n1"))
        pg.evaluate("window.__pw.treeq.hold(false)")
        ok = until(pg, lambda: tlen(pg) == 0 and [n for n in twin(pg)["notes"] if n["id"] == held_note], 3000)
        check("released: it lands", ok, tlen(pg))
        pg.wait_for_timeout(200)
        check("after the refresh that follows, it is still on the screen", nrow(pg, "Untitled").count() == 1)

        # ------------------------------------------------------------ __pw.idle() waits for both queues
        group[0] = "idle"
        pg.evaluate("window.__pw.api.failNext(1)")
        frow(pg, "U3e").locator(".more").click(); menu(pg, "Rename"); type_name(pg, "Idle folder")
        t0 = time.time(); pg.evaluate("window.__pw.idle()"); dt = time.time() - t0
        tw = twin(pg)
        check("a write that failed once: idle() waits through its retry, then both queues are empty and the twin has it",
              tlen(pg) == 0 and qlen(pg) == 0 and [f for f in tw["folders"] if f["id"] == "f1"][0]["name"] == "Idle folder" and dt > 1.0,
              [tlen(pg), qlen(pg), round(dt, 2)])
        open_note(pg, "Other device")
        mark = len(calllog(pg))
        pg.click("#addPageBtn"); pg.click("#menu button:text-is('Page')"); pg.wait_for_timeout(60)
        pid = pg.evaluate("() => window.__pw.S.pages.filter(p => p.note_id === 'n1').sort((a, b) => a.position - b.position)[1].id")
        go_page(pg, 2); draw(pg, 2, 200)
        idle(pg)
        log = calllog(pg)[mark:]
        check("a new page and a stroke: after idle() both queues are empty, the page row before its stroke",
              tlen(pg) == 0 and qlen(pg) == 0 and -1 < first_index(log, "insert", "pages", pid) < first_index(log, "putStrokes", "strokes", pid),
              [tlen(pg), qlen(pg), log[-3:]])
        offline(pg)
        pg.click("#noteName .nn"); type_name(pg, "Idle offline")
        t0 = time.time(); pg.evaluate("window.__pw.idle()"); dt = time.time() - t0
        check("offline, idle() does not hang: it returns with the op kept", dt < 2.0 and tlen(pg) == 1, [round(dt, 2), tlen(pg)])
        online(pg)
        check("online again: it lands", until(pg, lambda: tlen(pg) == 0 and [n for n in twin(pg)["notes"] if n["id"] == "n1"][0]["name"] == "Idle offline", 3000))
        back(pg)

        # ------------------------------------------------------------ the tree snapshot's size
        group[0] = "snapshot"
        info = pg.evaluate("window.__pw.treeq.snapshotInfo()")
        check("the device keeps a snapshot of the last tree read", info and info["notes"] >= 2 and info["bytes"] > 0, info)
        out = {}
        for label, arg in (("her tree (2 folders, 3 notes, 7 pages)", [2, 3, None]), ("50 notes x 20 pages (8 folders)", [8, 50, 20])):
            nf, nn, np = arg
            js = SYNTH_JS.replace("np(i)", "(" + ("[3, 2, 2][i]" if np is None else str(np)) + ")").replace("[nf, nn, np]", "[nf, nn]")
            tree = pg.evaluate(js, [nf, nn])
            pg.evaluate("(d) => window.__pw.treeq.keepTree(d)", tree)
            got = pg.evaluate("window.__pw.treeq.snapshotInfo()")
            out[label] = got
        her, big = out["her tree (2 folders, 3 notes, 7 pages)"], out["50 notes x 20 pages (8 folders)"]
        check("her tree's record: 3 notes, 7 pages", her["notes"] == 3 and her["pages"] == 7, her)
        check("50 x 20: 50 notes, 1000 pages, under 1 MB", big["notes"] == 50 and big["pages"] == 1000 and big["bytes"] < 1048576, big)
        sizes = (f"Tree snapshot record: her tree (2 folders, 3 notes, 7 pages) = {her['bytes']:,} bytes of JSON ({her['bytes'] / 1024:.1f} KB); "
                 f"50 notes x 20 pages (8 folders, 1000 pages) = {big['bytes']:,} bytes ({big['bytes'] / 1024:.0f} KB).")
        print(sizes)
        pg.reload(); ready(pg)                                    # the real snapshot again (from the twin)
        info = pg.evaluate("window.__pw.treeq.snapshotInfo()")
        check("a fresh load replaces the snapshot", info and info["pages"] < 20, info)

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7l" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7l", "pw-v7l" in keys, keys)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("the shell lists ./js/treeq.js", "./js/treeq.js" in swt)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in
                       ["./js/treeq.js", "./js/store.js", "./js/api.js", "./js/local-backend.js", "./js/app.js", "./sw.js", "./tests/test_u3e.py"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        app = pg.evaluate("fetch('./js/app.js').then(r => r.text())")
        check("the old toasts are gone ('Not saved, trying again', 'Still not saved')", "Not saved, trying again" not in app and "Still not saved" not in app)
        check("no save or sync button anywhere", pg.evaluate("""() => [...document.querySelectorAll('button')].filter(b =>
          /\\b(save|sync)\\b/i.test(b.textContent + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.title || ''))).length""") == 0)
        check("no page errors (local)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ live (Supabase), --live only
        if LIVE:
            user, pwd = creds()
            if not user or not pwd:
                live_note = "live group SKIPPED: no test login (PW_TEST_USER / PW_TEST_PASS or .env) on this machine"
            else:
                group[0] = "live"
                live_note = ""
                ctx = b.new_context(viewport={"width": 1280, "height": 800})
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE); pg.wait_for_selector("#login:not([hidden])")
                pg.fill("#lu", user); pg.fill("#lp", pwd); pg.click("#loginBtn"); ready(pg)
                ids = {}
                try:
                    offline(pg)
                    pg.click("#addFolder"); type_name(pg, "U3e test")
                    frow(pg, "U3e test").locator(".more").click(); menu(pg, "New note")
                    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
                    ids = pg.evaluate("""() => { const S = window.__pw.S, n = S.notes.find(x => x.id === S.openNote);
                      return { f: n.folder_id, n: n.id, p: S.pages.find(x => x.note_id === n.id).id }; }""")
                    draw(pg, 1, 200); pg.wait_for_timeout(400); draw(pg, 1, 320)
                    check("offline: folder, note, page queued", tlen(pg) >= 3, tcalls(pg))
                    online(pg); t0 = time.time()
                    def up():
                        r = pg.evaluate("""async (ids) => { const a = window.__pw.api, d = await a.loadAll(), s = await a.strokesOf([ids.p]);
                          const f = d.folders.find(x => x.id === ids.f), n = d.notes.find(x => x.id === ids.n), p = d.pages.find(x => x.id === ids.p);
                          return f && n && p ? [f.created_at, n.created_at, p.created_at, s.length] : null; }""", ids)
                        return r if r and r[3] == 2 else None
                    got = until(pg, up, 5000, 250)
                    check("within 5 s the live tables hold the folder, the note, the page and both strokes", got, round(time.time() - t0, 2))
                    if got:
                        check("in order: folder before note before page (created_at, the database's clock; the strokes need the page row)",
                              got[0] <= got[1] <= got[2], got[:3])
                finally:
                    if ids:
                        idle(pg)
                        left = pg.evaluate("""async (ids) => {
                          const a = window.__pw.api;
                          await a.removeSnapshots([window.__pw.S.user.id + '/' + ids.p + '.webp']).catch(() => {});
                          await a.remove('pages', [ids.p]);
                          const strokes = (await a.strokesOf([ids.p])).length;
                          await a.remove('notes', [ids.n]); await a.remove('folders', [ids.f]);
                          const d = await a.loadAll();
                          return [strokes, d.folders.filter(r => r.id === ids.f).length, d.notes.filter(r => r.id === ids.n).length, d.pages.filter(r => r.id === ids.p).length]; }""", ids)
                        check("clean-up: every row the test made is gone", left == [0, 0, 0, 0], left)
                check("no page errors (live)", not errs, errs)
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
if live_note: print(live_note)
sys.exit(0 if all(r[2] for r in res) else 1)
