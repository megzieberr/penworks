# PenWorks U3a checks (saving strokes): headless Playwright (Python), same style as tests/test_u2a.py.
# Run: python tests/test_u3a.py          (local mode only: ?local=1, the localStorage twin stands in for Supabase)
#      python tests/test_u3a.py --live   (adds the live group: the test login from PW_TEST_USER / PW_TEST_PASS or the
#                                         gitignored .env, never printed; it deletes every row it makes)
# Local groups: strokes reach the twin through the queue; offline they wait and go up when the connection is back; a
# failed push is retried; a refused push stays queued and lands once the refusal stops; undo, Erase page and Delete
# page make the right round trips; a stroke added upstream shows after reopening; the 1500-stroke page is measured.
import sys, os, subprocess, time, pathlib, re, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8781
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
LIVE = "--live" in sys.argv

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-26T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U3', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Sync', '2026-10-26T10:02:00Z'), N('n2', 'Big', '2026-10-26T10:01:00Z')],
    pages: [P('q1', 'n1', 0), P('q2', 'n1', 1), P('q3', 'n1', 2), P('b1', 'n2', 0)] }));
}"""
TWIN_JS = "(pid) => window.__pw.api.strokesOf([pid])"
DOT_JS = "() => { const d = document.getElementById('saveDot'); return [d.dataset.state, d.title]; }"
PATHS_JS = "(i) => document.querySelectorAll(`#stack .sheet[data-index=\"${i}\"] svg.ink path`).length"
DOTLOG_JS = """() => { window.__dotLog = [];
  new MutationObserver(() => window.__dotLog.push(document.getElementById('saveDot').dataset.state))
    .observe(document.getElementById('saveDot'), { attributes: true, attributeFilter: ['data-state'] }); }"""
# 1500 records with 60 points each, the shape ink.js writes (points rounded to 0.1 page px)
BIG_JS = """(pid) => {
  let seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const out = [], base = Date.now() - 1e7;
  for (let i = 0; i < 1500; i++) {
    let x = 40 + rnd() * 700, y = 40 + rnd() * 1040; const pts = [];
    for (let k = 0; k < 60; k++) { pts.push([Math.round(x * 10) / 10, Math.round(y * 10) / 10]); x += rnd() * 6 - 2; y += rnd() * 4 - 2; }
    out.push({ id: crypto.randomUUID(), page_id: pid, seq: base + i, kind: 'pen', style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: pts } });
  }
  return out;
}"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def twin(pg, pid): return pg.evaluate(TWIN_JS, pid)
def mine(pg, pid): return pg.evaluate("(id) => window.__pw.ink.strokesOf(id)", pid)
def cached(pg, pid): return pg.evaluate("(id) => window.__pw.store.cached(id)", pid)
def qlen(pg): return pg.evaluate("window.__pw.store.queueLength()")
def dot(pg): return pg.evaluate(DOT_JS)
def paths(pg, i): return pg.evaluate(PATHS_JS, i)
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
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
    open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(80); close_list(pg)
def draw(pg, i, y, x0=100, x1=400):
    pts = [(x0 + (x1 - x0) * k / 4, y) for k in range(5)]
    sx, sy = screen(pg, i, *pts[0]); pg.mouse.move(sx, sy); pg.mouse.down()
    for x, yy in pts[1:]:
        tx, ty = screen(pg, i, x, yy); pg.mouse.move(tx, ty, steps=6)
    pg.mouse.up(); pg.wait_for_timeout(30)
def quick_pair(pg, i, y1, y2, x0=100, x1=200):
    # two short strokes back to back, the screen points worked out first (so both lifts fall inside 300 ms)
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    for y in (y1, y2):
        pg.mouse.move(b["x"] + x0 * z, b["y"] + y * z); pg.mouse.down()
        pg.mouse.move(b["x"] + x1 * z, b["y"] + y * z, steps=3); pg.mouse.up()
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def seq_ok(rows): return all(rows[k]["seq"] <= rows[k + 1]["seq"] for k in range(len(rows) - 1))
def same_set(pg, pid): return sorted(r["id"] for r in twin(pg, pid)) == sorted(r["id"] for r in mine(pg, pid))
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")
def online(pg): pg.context.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))")

def creds():
    u, p = os.environ.get("PW_TEST_USER"), os.environ.get("PW_TEST_PASS")
    env = ROOT / ".env"
    if (not u or not p) and env.exists():
        kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        u, p = kv.get("PW_TEST_USER", "").strip(), kv.get("PW_TEST_PASS", "").strip()
    return u, p

measure = ""
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
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)

        # ------------------------------------------------------------ strokes reach the database (the twin)
        group[0] = "push"
        check("the dot starts grey: saved, 'All saved'", dot(pg) == ["saved", "All saved"], dot(pg))
        open_note(pg, "Sync")
        for y in (150, 250, 350): draw(pg, 1, y)
        idle(pg)
        t = twin(pg, "q1")
        check("three strokes in the twin after idle()", len(t) == 3, len(t))
        check("in seq order, the same records ink holds", seq_ok(t) and [r["id"] for r in t] == [r["id"] for r in mine(pg, "q1")], [r["seq"] for r in t])
        check("the row shape: id, page_id, seq, kind, style, data (no owner_id sent back)", t and sorted(t[0].keys()) == ["data", "id", "kind", "page_id", "seq", "style"], t[:1])
        check("the queue is empty, the dot saved", qlen(pg) == 0 and dot(pg)[0] == "saved", [qlen(pg), dot(pg)])
        pg.reload(); ready(pg); pg.wait_for_timeout(120)
        check("after a reload the page shows three strokes (from the device cache)", paths(pg, 1) == 3, paths(pg, 1))
        check("the cache holds three, the dot is saved", len(cached(pg, "q1") or []) == 3 and dot(pg)[0] == "saved", dot(pg))

        # ------------------------------------------------------------ offline: the queue waits, then goes up
        group[0] = "offline"
        ctx.set_offline(True); pg.wait_for_timeout(50)
        draw(pg, 1, 450); pg.wait_for_timeout(350); draw(pg, 1, 550)
        idle(pg)
        st = dot(pg)
        check("offline: the dot is amber (waiting)", st[0] == "waiting", st)
        check("the title counts the changes to send", re.search(r"Waiting for a connection, \d+ changes? to send", st[1]) is not None, st[1])
        check("the title says 2 (drawn 350 ms apart, not merged)", "2 changes" in st[1], st[1])
        check("the queue holds them, the twin still has 3", qlen(pg) == 2 and len(twin(pg, "q1")) == 3, [qlen(pg), len(twin(pg, "q1"))])
        check("the page shows all five meanwhile", paths(pg, 1) == 5)
        online(pg)
        ok = until(pg, lambda: len(twin(pg, "q1")) == 5 and dot(pg)[0] == "saved", 3000)
        t = twin(pg, "q1")
        check("back online: within 3 s the twin has five, in seq order, the dot saved", ok and seq_ok(t), [len(t), dot(pg)])
        check("the queue is empty", qlen(pg) == 0)
        ctx.set_offline(True); pg.wait_for_timeout(50)
        quick_pair(pg, 1, 600, 640); idle(pg)
        check("two strokes inside 300 ms merge into one op", qlen(pg) == 1 and "1 change to send" in dot(pg)[1], [qlen(pg), dot(pg)])
        online(pg)
        check("the merged op lands: seven", until(pg, lambda: len(twin(pg, "q1")) == 7 and dot(pg)[0] == "saved", 3000), len(twin(pg, "q1")))

        # ------------------------------------------------------------ a failed push is retried
        group[0] = "retry"
        pg.evaluate(DOTLOG_JS)
        pg.evaluate("window.__pw.api.failNext(1)")
        draw(pg, 1, 120, 450, 700)
        ok = until(pg, lambda: len(twin(pg, "q1")) == 8 and dot(pg)[0] == "saved", 6000)
        log = pg.evaluate("window.__dotLog")
        check("the failed push waits, then lands on the retry (2 s)", ok, [len(twin(pg, "q1")), dot(pg)])
        check("the dot went saving > waiting > saving > saved", "waiting" in log and log[-1] == "saved" and log.index("waiting") > log.index("saving"), log)

        # ------------------------------------------------------------ a refused push stays queued
        group[0] = "refused"
        n_warn = len([w for w in warns if "refused" in w])
        pg.evaluate("window.__pw.api.refuseNext(3)")
        draw(pg, 1, 220, 450, 700)
        ok = until(pg, lambda: dot(pg)[0] == "refused", 3000)
        check("RLS refuses (42501): within 3 s the dot is red", ok, dot(pg))
        check("its title: 'A change was refused, see the console'", dot(pg)[1] == "A change was refused, see the console", dot(pg))
        check("the op is still in the queue, the twin still has 8", qlen(pg) == 1 and len(twin(pg, "q1")) == 8, [qlen(pg), len(twin(pg, "q1"))])
        check("the console says why, once", len([w for w in warns if "refused" in w]) - n_warn == 1 and "42501" in [w for w in warns if "refused" in w][-1], warns[-1:])
        pg.evaluate("window.__pw.api.refuseNext(0)")
        pg.evaluate("window.dispatchEvent(new Event('focus'))")
        ok = until(pg, lambda: len(twin(pg, "q1")) == 9 and dot(pg)[0] == "saved", 3000)
        check("refusals stop, focus: it lands, the dot is saved", ok, [len(twin(pg, "q1")), dot(pg)])
        check("the queue is empty", qlen(pg) == 0)

        # ------------------------------------------------------------ undo, Erase page
        group[0] = "undo and erase"
        last = mine(pg, "q1")[-1]["id"]
        ctx.set_offline(True); pg.wait_for_timeout(50)
        pg.click("#undoBtn"); idle(pg)
        q = pg.evaluate("window.__pw.store.queued()")
        check("undo of a stroke = a queued op with that id in removed", len(q) == 1 and q[0]["removed"] == [last] and q[0]["added"] == [], q)
        online(pg)
        ok = until(pg, lambda: len(twin(pg, "q1")) == 8, 3000)
        check("after the push the twin has it gone", ok and last not in [r["id"] for r in twin(pg, "q1")], len(twin(pg, "q1")))
        thumb_menu(pg, 1); menu(pg, "Erase page"); close_list(pg); idle(pg)
        check("Erase page: the twin has none for the page", twin(pg, "q1") == [] and paths(pg, 1) == 0, len(twin(pg, "q1")))
        pg.click("#undoBtn"); idle(pg)
        check("undo: all eight back in the twin", len(twin(pg, "q1")) == 8 and paths(pg, 1) == 8, len(twin(pg, "q1")))
        check("the final twin set equals the mirror (and the cache)", same_set(pg, "q1") and sorted(r["id"] for r in cached(pg, "q1")) == sorted(r["id"] for r in mine(pg, "q1")))

        # ------------------------------------------------------------ Delete page (gone for good)
        group[0] = "delete page"
        go_page(pg, 2)
        draw(pg, 2, 200); idle(pg)
        check("a stroke on page 2 reaches the twin", len(twin(pg, "q2")) == 1)
        ctx.set_offline(True); pg.wait_for_timeout(50)
        draw(pg, 2, 300); idle(pg)
        check("offline, one more on page 2 waits in the queue", qlen(pg) == 1)
        thumb_menu(pg, 2); menu(pg, "Delete"); close_list(pg); idle(pg)
        # U3e: the page delete itself now waits in the tree queue while offline, so the dot counts only those tree changes
        tn = pg.evaluate("window.__pw.treeq.length()")
        check("Delete page 2: its queued op goes with it (it could never land)", qlen(pg) == 0 and tn >= 1
              and dot(pg)[0] == "waiting" and f"{tn} change" in dot(pg)[1], [qlen(pg), tn, dot(pg)])
        online(pg); idle(pg)
        check("the twin cascaded its strokes", twin(pg, "q2") == [])
        pg.click("#undoBtn"); idle(pg)
        check("undo: the page comes back and both its strokes go up again", len(twin(pg, "q2")) == 2 and same_set(pg, "q2"), len(twin(pg, "q2")))
        pg.click("#redoBtn"); idle(pg)
        check("redo: deleted again, cascaded again", twin(pg, "q2") == [] and qlen(pg) == 0)
        back(pg); idle(pg)
        check("closing the note forgets it: twin empty, queue 0, no cache entry", twin(pg, "q2") == [] and qlen(pg) == 0 and cached(pg, "q2") is None,
              [len(twin(pg, "q2")), qlen(pg)])

        # ------------------------------------------------------------ the database has a different set (another device)
        group[0] = "reconcile"
        added = pg.evaluate("""async () => { const r = { id: crypto.randomUUID(), page_id: 'q3', seq: Date.now(), kind: 'pen',
          style: { colour: '#0D0DFF', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100, 100], [300, 140]] } };
          await window.__pw.api.putStrokes([], [r]); return r.id; }""")
        gone = twin(pg, "q1")[0]["id"]
        pg.evaluate("(id) => window.__pw.api.putStrokes([id], [])", gone)
        open_note(pg, "Sync")
        ok = until(pg, lambda: paths(pg, 2) == 1 and paths(pg, 1) == 7, 3000)
        check("reopened: the stroke added upstream shows, the one removed upstream goes", ok, [paths(pg, 1), paths(pg, 2)])
        check("no undo step for it, nothing queued, the cache follows", pg.locator("#undoBtn").is_disabled() and qlen(pg) == 0
              and [r["id"] for r in cached(pg, "q3")] == [added] and len(cached(pg, "q1")) == 7)
        back(pg)

        # ------------------------------------------------------------ the 1500-stroke page
        group[0] = "1500 strokes"
        open_note(pg, "Big")
        recs = pg.evaluate(BIG_JS, "b1")
        size = len(json.dumps(recs, separators=(",", ":")).encode("utf-8"))
        per = int(5 * 1024 * 1024 // size)
        measure = (f"A 1500-stroke page (60 points per stroke) is {size:,} bytes of JSON ({size / 1048576:.2f} MB); "
                   f"localStorage's 5 MB ceiling holds about {per} such pages.")
        print(measure)
        pg.evaluate("(r) => window.__pw.ink.put('b1', r)", recs)
        t0 = time.time(); idle(pg); dt = time.time() - t0
        check("all 1500 reach the twin", len(twin(pg, "b1")) == 1500, len(twin(pg, "b1")))
        check("all 1500 in the device cache", len(cached(pg, "b1") or []) == 1500)
        pg.reload(); ready(pg); pg.wait_for_timeout(150)
        check("after a reload the page shows 1500", paths(pg, 1) == 1500, paths(pg, 1))
        check("the dot is saved", dot(pg)[0] == "saved", dot(pg))
        info = f"push + cache of the 1500-stroke page: {dt * 1000:.0f} ms"
        print(info)
        back(pg)

        # ------------------------------------------------------------ the dot itself
        group[0] = "the dot"
        sel = "#side .foot #saveDot"
        box = pg.locator(sel).bounding_box()
        tb = pg.locator("#themeBtn").bounding_box()
        check("one 10 px round dot beside the dark-mode toggle", pg.locator("#saveDot").count() == 1 and box and abs(box["width"] - 10) < 0.5
              and abs(box["height"] - 10) < 0.5 and abs((box["x"] + 10) - tb["x"]) < 12, [box, tb])
        # the folder view's footer is hidden while she writes: the note bar carries a second dot with the same state
        bar = pg.evaluate("""() => { const d = document.querySelector('#noteBar .saveDot'), f = document.getElementById('saveDot');
          return d ? [d.dataset.state === f.dataset.state, d.title === f.title, getComputedStyle(d).width] : null; }""")
        check("a second dot in the note bar mirrors the footer dot's state and title", bar and bar[0] and bar[1] and bar[2] == "10px", bar)
        bgc = lambda: pg.evaluate("getComputedStyle(document.getElementById('saveDot')).backgroundColor")
        light = bgc()
        pg.click("#themeBtn"); pg.wait_for_timeout(50)
        dark = bgc(); is_dark = pg.evaluate("document.documentElement.dataset.theme")
        pg.click("#themeBtn"); pg.wait_for_timeout(50)
        check("grey #9a9a9a, the same in dark mode", light == "rgb(154, 154, 154)" and dark == light and is_dark == "dark", [light, dark, is_dark])
        cols = pg.evaluate("""() => { const d = document.getElementById('saveDot'), keep = d.dataset.state, out = {};
          for (const s of ['saving', 'waiting', 'refused']) { d.dataset.state = s; out[s] = getComputedStyle(d).backgroundColor; }
          d.dataset.state = keep; return out; }""")
        check("blue #2F4BB8, amber #e0a100, red #c0392b", cols == {"saving": "rgb(47, 75, 184)", "waiting": "rgb(224, 161, 0)", "refused": "rgb(192, 57, 43)"}, cols)
        check("no text in it", pg.inner_text("#saveDot") == "")
        check("no save or sync button anywhere", pg.evaluate("""() => [...document.querySelectorAll('button')].filter(b =>
          /\\b(save|sync)\\b/i.test(b.textContent + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.title || ''))).length""") == 0)
        check("no toast after the saves", not pg.locator("#toast.show").count())
        pg.set_viewport_size({"width": 375, "height": 760}); pg.wait_for_timeout(80)
        box = pg.locator("#saveDot").bounding_box()
        check("phone width: the dot stays visible", pg.locator("#saveDot").is_visible() and box and box["x"] + box["width"] <= 375, box)
        pg.set_viewport_size({"width": 1280, "height": 800})
        check("no page errors (local)", not errs, errs)

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v6a" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v6a", "pw-v6a" in keys, keys)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("the shell lists ./js/store.js, not store-local.js", "./js/store.js" in swt and "store-local" not in swt)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in
                       ["./js/store.js", "./js/api.js", "./js/local-backend.js", "./js/ink.js", "./js/app.js", "./css/app.css", "./index.html"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("no file imports store-local.js", "./store-local.js" not in srcs)
        ctx.close()

        # ------------------------------------------------------------ live (Supabase), --live only
        if LIVE:
            group[0] = "live"
            user, pwd = creds()
            if not user or not pwd:
                check("test login available (PW_TEST_USER / PW_TEST_PASS)", False, "not set")
            else:
                ctx = b.new_context(viewport={"width": 1280, "height": 800})
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE); pg.wait_for_selector("#login:not([hidden])")
                pg.fill("#lu", user); pg.fill("#lp", pwd); pg.click("#loginBtn"); ready(pg)
                ids = {}
                try:
                    # folder > note > page through the app, the way she makes them
                    pg.click("#addFolder"); type_name(pg, "U3a test")
                    frow(pg, "U3a test").locator(".more").click(); menu(pg, "New note")
                    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
                    ids = pg.evaluate("""() => { const S = window.__pw.S, n = S.notes.find(x => x.id === S.openNote);
                      return { f: n.folder_id, n: n.id, p: S.pages.find(x => x.note_id === n.id).id }; }""")
                    pg.click("#noteName .nn"); type_name(pg, "U3a note")
                    for y in (150, 250, 350): draw(pg, 1, y)
                    idle(pg)
                    ok = until(pg, lambda: dot(pg)[0] == "saved", 8000)
                    up = pg.evaluate("(p) => window.__pw.api.strokesOf([p])", ids["p"])
                    check("three strokes in Supabase, the dot saved", ok and len(up) == 3 and seq_ok(up), [len(up), dot(pg)])
                    ctx2 = b.new_context(viewport={"width": 1280, "height": 800})
                    pg2 = ctx2.new_page()
                    pg2.goto(BASE); pg2.wait_for_selector("#login:not([hidden])")
                    pg2.fill("#lu", user); pg2.fill("#lp", pwd); pg2.click("#loginBtn"); ready(pg2)
                    frow(pg2, "U3a test").click()
                    open_note(pg2, "U3a note")
                    ok = until(pg2, lambda: paths(pg2, 1) == 3, 8000)
                    check("a second browser, same login: the page shows the three", ok, paths(pg2, 1))
                    ctx2.close()
                finally:
                    if ids:
                        idle(pg)
                        left = pg.evaluate("""async (ids) => {
                          const a = window.__pw.api;
                          await a.removeSnapshots([window.__pw.S.user.id + '/' + ids.p + '.webp']).catch(() => {});   // U3b: its picture, if one was made
                          await a.remove('pages', [ids.p]);                     // its strokes cascade with it
                          const strokes = (await a.strokesOf([ids.p])).length;
                          await a.remove('notes', [ids.n]); await a.remove('folders', [ids.f]);
                          const d = await a.loadAll();
                          return [strokes, d.folders.filter(r => r.id === ids.f).length, d.notes.filter(r => r.id === ids.n).length, d.pages.filter(r => r.id === ids.p).length]; }""", ids)
                        check("the page's strokes cascade with it; every row the test made is gone", left == [0, 0, 0, 0], left)
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
if not LIVE: print("live group skipped (run with --live)")
sys.exit(0 if all(r[2] for r in res) else 1)
