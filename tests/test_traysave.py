# PenWorks pw-v9t checks, the lazy tray save (audit finding H, the tray half): a tray change is kept on the device at
# once, and goes to the database 10 s after the last change, or at once when the app is hidden. Headless Playwright
# (Python), local mode (?local=1); the twin's profile row stands in for profiles.settings.
# Run: python -E -P tests\test_traysave.py
# Groups: five changes, one save (the device copy at once each time; nothing in the 9 s after the last change; exactly
# one save by 12 s, holding the last state); hidden (visibilitychange to hidden, and pagehide: the save goes at once, the
# 10 s timer is gone); closed inside the window (the hide save fails, the reload shows her tray from the device copy, the
# late profile does not overwrite it, and it reaches the database then); house rules.
import sys, time, pathlib, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); from swcache import SW_CACHE  # the cache name, read from sw.js
PORT = 8848
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
VERSION = SW_CACHE

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

class AppHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-11-20T08:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Tray', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Lesson', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [{ id: 'p1', note_id: 'n1', position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t }] }));
}"""
# every database save of the tray this page makes (api.setSettings is looked up at call time, so the spy sees each one)
SPY_JS = """() => { window.__saves = []; const a = window.__pw.api, f = a.setSettings; if (f.__spy) return;
  (a.setSettings = function (...x) { window.__saves.push({ width: x[0] && x[0].tray && x[0].tray.pen.width, at: x[0] && x[0].tray_at }); return f.apply(this, x); }).__spy = true; }"""
DB_JS = "() => { const d = JSON.parse(localStorage.getItem('penworks.local.v2') || '{}'); return (d.profile && d.profile.settings) || {}; }"
LOCALTRAY_JS = "() => JSON.parse(localStorage.getItem('pw.tools') || 'null')"
HIDE_JS = """() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
  document.dispatchEvent(new Event('visibilitychange')); delete document.hidden; }"""

def ready(pg, ms=20000): pg.wait_for_selector("body[data-ready='1']", timeout=ms)
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def hang(pg, calls): pg.evaluate("(c) => c.length ? localStorage.setItem('penworks.local.hang', JSON.stringify(c)) : localStorage.removeItem('penworks.local.hang')", calls)
def tray(pg): return pg.evaluate("window.__pw.tray()")
def width(pg): return tray(pg)["pen"]["width"]
def saves(pg): return pg.evaluate("window.__saves")
def db(pg): return pg.evaluate(DB_JS)
def db_width(pg): return ((db(pg).get("tray") or {}).get("pen") or {}).get("width")
def local(pg): return pg.evaluate(LOCALTRAY_JS) or {}
def pending(pg): return pg.evaluate("window.__pw.trayPending()")
def open_note(pg):
    pg.locator(".nrow").filter(has_text="Lesson").first.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(80)
def pen_panel(pg):
    if tray(pg)["tool"] != "pen": pg.click("#tool-pen"); pg.wait_for_timeout(40)
    if pg.locator("#toolPanel").is_hidden(): pg.click("#tool-pen"); pg.wait_for_timeout(40)
    pg.wait_for_selector("#toolPanel:not([hidden])")
def bigger(pg): pg.click("#toolPanel button[aria-label='Width bigger']")
def one_change(pg):
    pen_panel(pg); bigger(pg); pg.keyboard.press("Escape"); pg.wait_for_timeout(30)

app = ThreadingHTTPServer(("127.0.0.1", PORT), partial(AppHandler, directory=str(ROOT))); app.daemon_threads = True
threading.Thread(target=app.serve_forever, daemon=True).start()
time.sleep(0.5)
errs = []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.reload(); ready(pg)

        # ============================================================ five changes, one save
        group[0] = "five changes, one save"
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg)
        pg.evaluate(SPY_JS)
        check("1. set-up: a fresh device and database (no tray copy in either), pen width 2.5",
              not local(pg) and "tray" not in db(pg) and width(pg) == 2.5, [local(pg), db(pg), width(pg)])
        pen_panel(pg)
        kept_each, stamps = [], []
        t_first = time.time()
        for i in range(5):
            bigger(pg)
            want = 2.5 + 0.5 * (i + 1)
            loc = local(pg)                                  # read at once, no wait
            kept_each.append(loc.get("pen", {}).get("width") == want and width(pg) == want)
            stamps.append(loc.get("tray_at"))
            if i < 4: pg.wait_for_timeout(400)
        t_last = time.time()
        pg.keyboard.press("Escape")
        print(f"five changes in {t_last - t_first:.2f} s")
        check("2. the five changes took under 3 s", t_last - t_first < 3, round(t_last - t_first, 2))
        check("3. the device's copy (pw.tools) has each change at once (width 3, 3.5, 4, 4.5, 5), each with a new stamp",
              all(kept_each) and len(set(stamps)) == 5 and None not in stamps, [kept_each, stamps])
        pg.wait_for_timeout(max(0, int((t_last + 9 - time.time()) * 1000)))
        s9 = saves(pg)
        check("4. no database save in the 9 s after the last change (the database still has no tray)",
              s9 == [] and "tray" not in db(pg), [s9, db(pg)])
        one = until(pg, lambda: len(saves(pg)) >= 1, int(max(0, t_last + 12 - time.time()) * 1000) + 50, 50)
        t_save = time.time()
        print(f"the save went {t_save - t_last:.2f} s after the last change ({t_save - t_first:.2f} s after the first)")
        pg.wait_for_timeout(1000)
        s = saves(pg); d = db(pg)
        check("5. exactly one save by 12 s after the last change (and still one a second later)", one and len(s) == 1, s)
        check("6. ... holding the last state: width 5 in the database, the device copy's stamp",
              s and s[0]["width"] == 5 and db_width(pg) == 5 and d.get("tray_at") == local(pg).get("tray_at") == stamps[-1],
              [s, d.get("tray_at"), stamps[-1]])
        check("7. nothing left waiting", pending(pg) == {"next": False, "busy": False, "timer": False}, pending(pg))

        # ============================================================ hidden: the save goes at once
        group[0] = "hidden"
        pg.evaluate(SPY_JS)
        one_change(pg)                                       # width 5.5
        pg.wait_for_timeout(1000)
        check("8. a change, 1 s later: not saved yet, waiting on its timer", saves(pg) == [] and pending(pg)["timer"] and pending(pg)["next"],
              [saves(pg), pending(pg)])
        pg.evaluate(HIDE_JS)
        ok = until(pg, lambda: db_width(pg) == 5.5, 500, 20)
        check("9. the app hidden (visibilitychange): the save goes out at once (width 5.5 in the database within 0.5 s)",
              ok and len(saves(pg)) == 1, [db_width(pg), saves(pg)])
        check("10. ... and its 10 s timer is gone", pending(pg) == {"next": False, "busy": False, "timer": False}, pending(pg))
        one_change(pg)                                       # width 6
        pg.wait_for_timeout(1000)
        pg.evaluate("window.dispatchEvent(new Event('pagehide'))")
        ok = until(pg, lambda: db_width(pg) == 6, 500, 20)
        check("11. a change, then pagehide 1 s later: the save goes out at once (width 6)", ok and len(saves(pg)) == 2, [db_width(pg), saves(pg)])
        pg.wait_for_timeout(10500)
        check("12. no further save 10.5 s later (two changes, two hide saves, nothing else)", len(saves(pg)) == 2, saves(pg))
        pg.evaluate(HIDE_JS)
        check("13. hidden with nothing waiting: no save", len(saves(pg)) == 2, saves(pg))

        # ============================================================ closed inside the window, the hide save lost
        group[0] = "closed inside the window"
        one_change(pg)                                       # width 6.5
        pg.wait_for_timeout(1000)
        mine = local(pg)
        check("14. set-up: width 6.5 on the device, the database still has 6", mine.get("pen", {}).get("width") == 6.5 and db_width(pg) == 6,
              [mine.get("pen"), db_width(pg)])
        pg.evaluate("window.__pw.api.failNext(5)")          # every hide save on the way out fails, like a request that never lands
        hang(pg, ["profile"])                                # the next start's profile read waits, so the database can be looked at first
        pg.reload(); ready(pg)
        check("15. the hide save did not land: the database still says width 6", db_width(pg) == 6, db(pg))
        check("16. the next start shows the tray she left (width 6.5, from the device copy)", width(pg) == 6.5, tray(pg)["pen"])
        hang(pg, [])                                         # the profile lands late, with its older tray
        ok = until(pg, lambda: db_width(pg) == 6.5, 3000)
        check("17. the late profile does not overwrite her tray (still 6.5 on the screen)", width(pg) == 6.5, tray(pg)["pen"])
        check("18. ... and her tray reaches the database then, under the device copy's stamp",
              ok and db(pg).get("tray_at") == mine.get("tray_at") and local(pg).get("tray_at") == mine.get("tray_at"),
              [db_width(pg), db(pg).get("tray_at"), mine.get("tray_at")])

        # ============================================================ house rules
        group[0] = "house rules"
        keys = pg.evaluate("caches.keys()")
        check(f"19. cache is {VERSION}", VERSION in keys, keys)
        raw = (ROOT / "sw.js").read_bytes()
        check("20. sw.js has no BOM", not raw.startswith(b"\xef\xbb\xbf"))
        srcs = "".join((ROOT / p).read_text(encoding="utf-8") for p in ["sw.js", "js/app.js", "tests/test_traysave.py"])
        check("21. no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("22. no page errors", not errs, errs[:3])
        ctx.close()
        b.close()
finally:
    app.shutdown()

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
