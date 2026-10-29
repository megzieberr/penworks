# PenWorks U3b checks (page pictures): headless Playwright (Python), same harness as tests/test_u3a.py.
# Run: python tests/test_u3b.py          (local mode only: ?local=1, the twin's in-memory bucket stands in for Storage)
#      python tests/test_u3b.py --live   (adds the live group: the test login from PW_TEST_USER / PW_TEST_PASS or the
#                                         gitignored .env, never printed; it deletes the picture and every row it makes)
# Local groups: a page's picture lands a few seconds after the last stroke and becomes the note's cover; a second page
# does not move the cover; reordering and deleting pages make the cover follow the first page; a change inside the 4 s
# resets the wait; offline nothing goes up until the connection is back; a failed upload lands on the retry; the grid
# card shows the cover (from the device cache after a reload, no download); no render starts during a long gesture.
import sys, os, subprocess, time, pathlib, re, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8782
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
LIVE = "--live" in sys.argv

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-26T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', snapshot_path: null, snapshot_at: null, deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u, pinned) => ({ id, folder_id: 'f1', name, pinned: !!pinned, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U3b', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Cover', '2026-10-26T10:05:00Z', true), N('n2', 'Timer', '2026-10-26T10:04:00Z'), N('n3', 'Offline', '2026-10-26T10:03:00Z'),
            N('n4', 'Retry', '2026-10-26T10:02:00Z'), N('n5', 'Gesture', '2026-10-26T10:01:00Z'), N('n6', 'Thirty', '2026-10-26T10:00:30Z'),
            N('n7', 'Empty', '2026-10-26T10:00:10Z')],
    pages: [P('c1', 'n1', 0), P('c2', 'n1', 1), P('c3', 'n1', 2), P('t1', 'n2', 0), P('o1', 'n3', 0), P('r1', 'n4', 0), P('g1', 'n5', 0), P('s1', 'n6', 0), P('e1', 'n7', 0)] }));
}"""
ROW_JS = "async ([t, id]) => (await window.__pw.api.loadAll())[t].find(r => r.id === id) || null"

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def bucket(pg): return pg.evaluate("window.__pw.api.storageList()")
def has(pg, pid): return f"local/{pid}.webp" in bucket(pg)
def row(pg, t, id): return pg.evaluate(ROW_JS, [t, id])
def cover(pg, nid): return (row(pg, "notes", nid) or {}).get("cover_path")
def stats(pg): return pg.evaluate("window.__pw.snap()")
def reads(pg): return pg.evaluate("window.__pw.api.snapshotReads()")
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
def thumb(pg, i): return pg.locator(f"#plThumbs .thumbP[data-index='{i}']")
def thumb_menu(pg, i):
    open_list(pg); thumb(pg, i).click(button="right")
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def go_page(pg, i):
    open_list(pg); thumb(pg, i).click(); pg.wait_for_timeout(80); close_list(pg)
def draw(pg, i, y, x0=100, x1=400, wave=0):
    # a stroke of 13 points; wave > 0 makes it go up and down like handwriting
    pts = [(x0 + (x1 - x0) * k / 12, y + (wave if k % 2 else -wave)) for k in range(13)]
    sx, sy = screen(pg, i, *pts[0]); pg.mouse.move(sx, sy); pg.mouse.down()
    for x, yy in pts[1:]:
        tx, ty = screen(pg, i, x, yy); pg.mouse.move(tx, ty, steps=3)
    pg.mouse.up(); pg.wait_for_timeout(30)
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def online(pg): pg.context.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))")
def card(pg, nid): return pg.locator(f"#grid .card[data-id='{nid}']")
def to_grid(pg):
    if pg.locator("#noteView").is_visible(): back(pg)
    frow(pg, "U3b").click(); pg.wait_for_timeout(120)

def creds():
    u, p = os.environ.get("PW_TEST_USER"), os.environ.get("PW_TEST_PASS")
    env = ROOT / ".env"
    if (not u or not p) and env.exists():
        kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        u, p = kv.get("PW_TEST_USER", "").strip(), kv.get("PW_TEST_PASS", "").strip()
    return u, p

measure = []
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
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)

        # ------------------------------------------------------------ the first page's picture, and the cover
        group[0] = "first picture"
        check("the bucket starts empty", bucket(pg) == [], bucket(pg))
        open_note(pg, "Cover")
        for y in (150, 250, 350): draw(pg, 1, y, wave=12)
        idle(pg); t0 = time.time()
        ok = until(pg, lambda: has(pg, "c1"), 6000)
        dt = time.time() - t0
        check("draw on page 1, idle(): within 6 s the bucket has local/c1.webp", ok, [bucket(pg), round(dt, 2)])
        check("not before the 4 s quiet time", dt > 3.0, round(dt, 2))
        r = row(pg, "pages", "c1")
        check("the page row: snapshot_path local/c1.webp, snapshot_at set", r["snapshot_path"] == "local/c1.webp" and r["snapshot_at"], r)
        check("snapshot_at = updated_at (the database's clock pair says fresh)", r["snapshot_at"] == r["updated_at"], [r["snapshot_at"], r["updated_at"]])
        check("the note's cover_path is that path", until(pg, lambda: cover(pg, "n1") == "local/c1.webp", 2000), cover(pg, "n1"))
        check("the cover did not count as an edit (notes.updated_at unchanged)", row(pg, "notes", "n1")["updated_at"] == "2026-10-26T10:05:00Z", row(pg, "notes", "n1")["updated_at"])
        s = stats(pg)
        print(f"one picture (3 strokes): {s['bytes']:,} bytes, render {s['renderMs']} ms")
        check("the blob is WebP-sized (over 1 KB, under 200 KB)", 1024 < s["bytes"] < 200 * 1024, s["bytes"])
        check("no toast, the dot is saved", not pg.locator("#toast.show").count() and pg.evaluate("document.getElementById('saveDot').dataset.state") == "saved")
        mime = pg.evaluate("async () => { const a = window.__pw.api, b = await a.getSnapshot('local/c1.webp'); return [b.type, b.size]; }")
        check("the object is image/webp", mime[0] == "image/webp", mime)
        dims = pg.evaluate("""async () => { const b = await window.__pw.api.getSnapshot('local/c1.webp'), bm = await createImageBitmap(b); return [bm.width, bm.height]; }""")
        check("at 1x: 794 x 1123", dims == [794, 1123], dims)

        # ------------------------------------------------------------ page 2: a second picture, the cover stays
        group[0] = "second page"
        go_page(pg, 2)
        draw(pg, 2, 200, wave=10); idle(pg)
        ok = until(pg, lambda: has(pg, "c2"), 6500)
        check("draw on page 2: a second object, local/c2.webp", ok and len(bucket(pg)) == 2, bucket(pg))
        check("the cover is still page 1's", cover(pg, "n1") == "local/c1.webp", cover(pg, "n1"))

        # ------------------------------------------------------------ the cover follows the first page
        group[0] = "cover follows"
        open_list(pg)
        pg.click("#plSelect"); pg.wait_for_timeout(40)
        thumb(pg, 2).click(); pg.wait_for_timeout(30)
        pg.click("#plBar button[data-act='move']"); pg.wait_for_timeout(80)
        pg.click("#plThumbs .moveHere[data-gap='0']"); pg.wait_for_timeout(80); idle(pg)
        pg.keyboard.press("Escape"); close_list(pg)
        order = pg.evaluate("window.__pw.S.pages.filter(p => p.note_id === 'n1').sort((a, b) => a.position - b.position).map(p => p.id)")
        check("Move: page 2 is first now", order == ["c2", "c1", "c3"], order)
        check("cover_path follows: local/c2.webp", until(pg, lambda: cover(pg, "n1") == "local/c2.webp", 3000), cover(pg, "n1"))
        thumb_menu(pg, 2); menu(pg, "Delete"); close_list(pg); idle(pg)
        check("delete page 1 (now second) for good: its row is gone", row(pg, "pages", "c1") is None)
        check("its object is NOT deleted by the app", has(pg, "c1"), bucket(pg))
        check("the cover is page 2's", cover(pg, "n1") == "local/c2.webp", cover(pg, "n1"))
        thumb_menu(pg, 1); menu(pg, "Delete"); close_list(pg); idle(pg)
        check("delete the first page: the new first (no picture yet) makes the cover null",
              until(pg, lambda: cover(pg, "n1") is None, 3000), cover(pg, "n1"))
        pg.click("#undoBtn"); idle(pg)
        check("undo: page 2 is back on top; its picture is made again and the cover follows",
              until(pg, lambda: cover(pg, "n1") == "local/c2.webp", 7000), [cover(pg, "n1"), row(pg, "pages", "c2")])
        check("the restored row has its picture again", (row(pg, "pages", "c2") or {}).get("snapshot_path") == "local/c2.webp")
        back(pg)

        # ------------------------------------------------------------ the 4 s timer resets on a change
        group[0] = "quiet timer"
        open_note(pg, "Timer")
        draw(pg, 1, 150); t0 = time.time()
        pg.wait_for_timeout(2000)
        draw(pg, 1, 250)
        while time.time() - t0 < 5.0: pg.wait_for_timeout(50)
        check("draw, 2 s, draw: at 5 s there is still no object", not has(pg, "t1"), bucket(pg))
        ok = until(pg, lambda: has(pg, "t1"), max(100, int((t0 + 7.0 - time.time()) * 1000)))
        check("at 7 s there is one", ok, round(time.time() - t0, 2))
        back(pg)

        # ------------------------------------------------------------ offline
        group[0] = "offline"
        open_note(pg, "Offline")
        ctx.set_offline(True); pg.wait_for_timeout(50)
        draw(pg, 1, 200); idle(pg)
        pg.wait_for_timeout(6000)
        check("offline: draw, 6 s later no object", not has(pg, "o1"), bucket(pg))
        check("the page is still due", "o1" in stats(pg)["due"], stats(pg))
        online(pg); t0 = time.time()
        ok = until(pg, lambda: has(pg, "o1"), 4000)
        check("online + the online event: within 4 s it is there", ok, round(time.time() - t0, 2))
        back(pg)

        # ------------------------------------------------------------ a failed upload lands on the retry
        group[0] = "retry"
        open_note(pg, "Retry")
        draw(pg, 1, 200); idle(pg)
        pg.evaluate("""() => { window.__dotLog = [];
          new MutationObserver(() => window.__dotLog.push(document.getElementById('saveDot').dataset.state))
            .observe(document.getElementById('saveDot'), { attributes: true, attributeFilter: ['data-state'] }); }""")
        n_warn = len([w for w in warns if "could not be saved" in w])
        f0 = stats(pg)["failures"]
        pg.evaluate("window.__pw.api.failNext(1)")
        ok = until(pg, lambda: stats(pg)["failures"] > f0, 6000)
        check("failNext(1): the upload fails once", ok and not has(pg, "r1"), stats(pg))
        ok = until(pg, lambda: has(pg, "r1"), 5000)
        check("it lands on the retry (2 s later)", ok, bucket(pg))
        new = [w for w in warns if "could not be saved" in w][n_warn:]
        check("the console says why, once", len(new) == 1, new)
        check("the save dot was never touched", pg.evaluate("window.__dotLog") == [], pg.evaluate("window.__dotLog"))
        check("no toast", not pg.locator("#toast.show").count())
        back(pg)

        # ------------------------------------------------------------ no render while a gesture runs
        group[0] = "gesture"
        open_note(pg, "Gesture")
        draw(pg, 1, 150); idle(pg)
        r0 = stats(pg)["renders"]
        x, y = screen(pg, 1, 100, 400); pg.mouse.move(x, y); pg.mouse.down(); t0 = time.time()
        k = 0
        while time.time() - t0 < 5.5:
            k += 1; xx, yy = screen(pg, 1, 100 + k * 3, 400 + (k % 7)); pg.mouse.move(xx, yy); pg.wait_for_timeout(100)
        busy = pg.evaluate("window.__pw.ink.busy()")
        check("a 5.5 s gesture (pen down, moving slowly, no lift): ink.busy()", busy)
        check("no render started meanwhile, the page waits", stats(pg)["renders"] == r0 and not has(pg, "g1") and "g1" in stats(pg)["due"], stats(pg))
        pg.mouse.up(); t1 = time.time()
        ok = until(pg, lambda: has(pg, "g1"), 7000)
        dt = time.time() - t1
        check("after the lift: 4 s, then the picture", ok and dt > 3.0, round(dt, 2))
        back(pg)

        # ------------------------------------------------------------ one real page, about 30 strokes
        group[0] = "size"
        open_note(pg, "Thirty")
        for k in range(30): draw(pg, 1, 80 + k * 33, 60 + (k % 3) * 20, 600 + (k % 5) * 30, wave=9)
        idle(pg)
        ok = until(pg, lambda: has(pg, "s1"), 7000)
        s = stats(pg)
        size_info = f"one page, 30 handwriting-like strokes (13 points each): {s['bytes']:,} bytes WebP, render {s['renderMs']} ms"
        measure.append(size_info); print(size_info)
        check("the 30-stroke page's picture lands", ok)

        # ------------------------------------------------------------ a new paper is a new picture; landscape swaps
        group[0] = "paper change"
        # pw-v6c: a written page keeps its shape, so the writing comes off first (its own new picture lands), the page
        # turns (the picture this group checks), then the writing goes back
        keep1 = pg.evaluate("window.__pw.ink.copyStrokes('s1')"); at_w = row(pg, "pages", "s1")["snapshot_at"]
        pg.evaluate("() => window.__pw.ink.erasePageOp('s1').redo()"); idle(pg)
        until(pg, lambda: (row(pg, "pages", "s1") or {}).get("snapshot_at") != at_w, 7000)
        at0 = row(pg, "pages", "s1")["snapshot_at"]
        pg.click("#noteMore"); menu(pg, "Landscape"); menu(pg, "Just this page"); idle(pg)
        ok = until(pg, lambda: (row(pg, "pages", "s1") or {}).get("snapshot_at") != at0, 7000)
        check("Landscape for this page: a new picture within 7 s", ok, [at0, row(pg, "pages", "s1")["snapshot_at"]])
        at_l = row(pg, "pages", "s1")["snapshot_at"]
        pg.evaluate("(r) => window.__pw.ink.put('s1', r)", keep1); idle(pg)
        until(pg, lambda: (row(pg, "pages", "s1") or {}).get("snapshot_at") != at_l, 7000)   # the written page's picture lands too
        dims = pg.evaluate("""async () => { const b = await window.__pw.api.getSnapshot('local/s1.webp'), bm = await createImageBitmap(b); return [bm.width, bm.height]; }""")
        check("landscape at 1x: 1123 x 794", dims == [1123, 794], dims)
        back(pg)

        # ------------------------------------------------------------ the grid card
        group[0] = "card"
        rb = reads(pg)                                   # the checks above read two objects themselves
        to_grid(pg)
        c = card(pg, "n1")
        check("tablet width, the note opened this session: its first page's ink over the paper, no picture",
              c.locator(".thumb .paper > svg.thumbInk").count() == 1 and c.locator("img.cover").count() == 0)
        check("the pinned badge is there", c.locator(".pin").count() == 1)
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(150)
        if not card(pg, "n1").is_visible(): frow(pg, "U3b").click(); pg.wait_for_timeout(120)
        img = card(pg, "n1").locator("img.cover")
        ok = until(pg, lambda: img.count() == 1, 3000)
        src = img.get_attribute("src") if ok else None
        check("phone width: the card shows img.cover with a blob: URL", ok and src and src.startswith("blob:"), src)
        check("its alt is the note's name", ok and img.get_attribute("alt") == "Cover", img.get_attribute("alt") if ok else None)
        check("no download for it (the picture went into the device cache when it landed)", reads(pg) == rb, [reads(pg), rb])
        ent = pg.evaluate("async () => { const e = await window.__pw.store.coverGet('n1'); return e ? [e.path, e.at, e.blob.size] : null; }")
        first = row(pg, "pages", "c2")
        check("the cache entry: { path, at = the first page's snapshot_at, blob }", ent and ent[0] == "local/c2.webp" and ent[1] == first["snapshot_at"] and ent[2] > 1024, [ent, first["snapshot_at"]])
        geo = pg.evaluate("""() => { const c = document.querySelector("#grid .card[data-id='n1']"), t = c.querySelector('.thumb'), i = t.querySelector('img.cover'), p = t.querySelector('.pin');
          const a = t.getBoundingClientRect(), b = i.getBoundingClientRect(), q = p.getBoundingClientRect(), cs = getComputedStyle(i);
          const top = document.elementFromPoint(q.x + q.width / 2, q.y + q.height / 2);
          return [Math.abs(t.clientWidth - b.width) < 1 && Math.abs(t.clientHeight - b.height) < 1 && b.x >= a.x && b.y >= a.y, cs.objectFit, cs.borderRadius === getComputedStyle(t).borderRadius, !!(top && top.closest('.pin'))]; }""")
        check("the picture fills .thumb (object-fit cover, the same rounded corners)", geo[:3] == [True, "cover", True], geo)
        check("the pinned badge stays on top of it", geo[3], geo)
        th = card(pg, "n1").locator(".thumb").bounding_box()
        pg.mouse.move(th["x"] + th["width"] / 2, th["y"] + th["height"] / 2); pg.mouse.down(); pg.wait_for_timeout(700); pg.mouse.up()
        menu_open = pg.locator("#menu:not([hidden])").count() == 1
        check("a long press on the picture still opens the note menu", menu_open)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(50)
        # the download path: no cache entry and no memo, so the card asks the bucket once
        pg.evaluate("async () => { await window.__pw.store.coverDrop('n1'); window.__pw.covers.clear(); window.__pw.renderGrid(); }")
        ok = until(pg, lambda: card(pg, "n1").locator("img.cover").count() == 1, 3000)
        check("no cache entry: downloaded once through getSnapshot, then shown", ok and reads(pg) == rb + 1, [reads(pg), rb])
        check("and kept in the cache again", until(pg, lambda: pg.evaluate("window.__pw.store.coverGet('n1').then(e => !!e)"), 2000))
        check("the other pictured notes show theirs", until(pg, lambda: card(pg, "n6").locator("img.cover").count() == 1
              and card(pg, "n2").locator("img.cover").count() == 1, 2000))
        check("a note never written on: the paper only, no picture made for its empty page",
              card(pg, "n7").locator("img.cover, svg.thumbInk").count() == 0 and card(pg, "n7").locator(".paper").count() == 1 and not has(pg, "e1"))
        pg.reload(); ready(pg)
        if not card(pg, "n1").is_visible(): frow(pg, "U3b").click(); pg.wait_for_timeout(120)
        img = card(pg, "n1").locator("img.cover")
        ok = until(pg, lambda: img.count() == 1, 3000)
        check("reload: the card shows the cover from the device cache", ok and (img.get_attribute("src") or "").startswith("blob:"))
        check("without a getSnapshot call", reads(pg) == 0, reads(pg))
        pg.wait_for_timeout(1500)
        check("after the reload no page is drawn again (every picture is fresh)", stats(pg)["renders"] == 0 and stats(pg)["due"] == [], stats(pg))
        pg.set_viewport_size({"width": 1280, "height": 800}); pg.wait_for_timeout(100)
        check("tablet width after the reload (the note not opened): the picture, not ink", card(pg, "n1").locator("img.cover").count() == 1
              and card(pg, "n1").locator("svg.thumbInk").count() == 0)
        check("no page errors (local)", not errs, errs)

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7d" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7d", "pw-v7d" in keys, keys)
        swt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("the shell lists ./js/snap.js", "./js/snap.js" in swt)
        check("Supabase (its /storage/ too) is never cached: other origins go straight to the network", "url.origin !== location.origin" in swt)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in
                       ["./js/snap.js", "./js/store.js", "./js/api.js", "./js/local-backend.js", "./js/ink.js", "./js/app.js", "./css/app.css", "./sw.js"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        ctx.close()

        # ------------------------------------------------------------ live (Supabase), --live only
        if LIVE:
            group[0] = "live"
            user, pwd = creds()
            if not user or not pwd:
                live_note = "live group skipped: no test login (PW_TEST_USER / PW_TEST_PASS or .env)"
                print(live_note)
            else:
                ctx = b.new_context(viewport={"width": 1280, "height": 800})
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE); pg.wait_for_selector("#login:not([hidden])")
                pg.fill("#lu", user); pg.fill("#lp", pwd); pg.click("#loginBtn"); ready(pg)
                ids = {}
                try:
                    pg.click("#addFolder")
                    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill("U3b test"); inp.press("Enter")
                    frow(pg, "U3b test").locator(".more").click(); menu(pg, "New note")
                    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
                    ids = pg.evaluate("""() => { const S = window.__pw.S, n = S.notes.find(x => x.id === S.openNote);
                      return { f: n.folder_id, n: n.id, p: S.pages.find(x => x.note_id === n.id).id, u: S.user.id }; }""")
                    for y in (150, 250, 350): draw(pg, 1, y, wave=10)
                    idle(pg)
                    path = f"{ids['u']}/{ids['p']}.webp"
                    ok = until(pg, lambda: (row(pg, "pages", ids["p"]) or {}).get("snapshot_path") == path, 15000)
                    r = row(pg, "pages", ids["p"]) or {}
                    check("the page row names the picture, snapshot_at set", ok and r.get("snapshot_at"), r)
                    check("snapshot_at = updated_at on the live database ('now' and the trigger agree)", r.get("snapshot_at") == r.get("updated_at"),
                          [r.get("snapshot_at"), r.get("updated_at")])
                    blob = pg.evaluate("async (p) => { const b = await window.__pw.api.getSnapshot(p); return [b.type, b.size]; }", path)
                    check("getSnapshot: a Blob over 1 KB, image/webp", blob[0] == "image/webp" and blob[1] > 1024, blob)
                    check("the note's cover_path is that path", until(pg, lambda: cover(pg, ids["n"]) == path, 6000), cover(pg, ids["n"]))
                finally:
                    if ids:
                        idle(pg)
                        left = pg.evaluate("""async (ids) => {
                          const a = window.__pw.api, path = ids.u + '/' + ids.p + '.webp';
                          await a.removeSnapshots([path]);
                          // the storage edge can answer a download for a moment after the delete: give it up to 8 s
                          let gone = false;
                          for (let i = 0; i < 8 && !gone; i++) {
                            try { await a.getSnapshot(path); await new Promise((r) => setTimeout(r, 1000)); } catch (_) { gone = true; }
                          }
                          await a.remove('pages', [ids.p]); await a.remove('notes', [ids.n]); await a.remove('folders', [ids.f]);
                          const d = await a.loadAll();
                          return [gone, d.folders.filter(r => r.id === ids.f).length, d.notes.filter(r => r.id === ids.n).length, d.pages.filter(r => r.id === ids.p).length]; }""", ids)
                        # the storage edge keeps serving a deleted picture for a while (seen live 26 Oct: still there after 8 s,
                        # storage.objects already empty), so only the rows are asserted; the download state is reported
                        check("every row the test made is gone (download after delete: " + ("fails" if left[0] else "still cached") + ")", left[1:] == [0, 0, 0], left)
                check("no page errors (live)", not errs, errs)
                live_note = "live group ran"
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
for m in measure: print(m)
print(live_note)
sys.exit(0 if all(r[2] for r in res) else 1)
