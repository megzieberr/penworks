# PenWorks pw-v9r checks, snapshot first (audit finding E): with a snapshot on the device the app draws it at once and
# the tree read lands later the lateTree way; the bin purge goes after the first draw. Headless Playwright (Python),
# local mode (?local=1). The local twin's purgeBin / loadAll / profile hang through its test hook
# (localStorage penworks.local.hang), as in tests/test_deadwifi.py.
# Run: python -E -P tests\test_snapfirst.py
# Groups: snapshot first (ready in under 1 s with the read held back 2 s, the other device's rename merged in with no
# reload); her rename while the read is held (the late read is dropped, a fresh read follows); no snapshot (it waits);
# the purge (after ready, never before; it still empties the bin); house rules.
import sys, time, re, pathlib, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); from swcache import SW_CACHE  # the cache name, read from sw.js
PORT = 8833
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
VERSION = SW_CACHE

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

class AppHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/__blank"):              # a page of the same origin that is not the app
            body = b"blank"
            self.send_response(200); self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        super().do_GET()

# every page: when body[data-ready] is set (ms from navigation start, and whether loadAll was still hung then), and
# each purgeBin call (its first look at the hang key) with whether the app was ready by then
SPY_JS = """(() => {
  window.__t = { ready: null, heldAtReady: null, purge: [] };
  const hangs = (c) => { try { return (Storage.prototype.getItem.__orig.call(localStorage, 'penworks.local.hang') || '').includes(c); } catch (_) { return false; } };
  const g = Storage.prototype.getItem;
  Storage.prototype.getItem = function (k) {
    if (k === 'penworks.local.hang' && (new Error().stack || '').includes('purgeBin'))
      window.__t.purge.push({ at: Math.round(performance.now()), ready: !!(document.body && document.body.dataset.ready === '1') });
    return g.call(this, k);
  };
  Storage.prototype.getItem.__orig = g;
  new MutationObserver(() => {
    if (window.__t.ready == null && document.body && document.body.dataset.ready === '1') {
      window.__t.ready = Math.round(performance.now()); window.__t.heldAtReady = hangs('loadAll');
    }
  }).observe(document, { attributes: true, subtree: true, attributeFilter: ['data-ready'] });
})();"""

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-11-19T08:00:00Z', old = '2026-09-01T08:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Snap first', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Snapshot name', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t },
            { id: 'n9', folder_id: 'f1', name: 'Old bin note', pinned: false, cover_path: null, deleted_at: old, created_at: old, updated_at: old }],
    pages: [{ id: 'q1', note_id: 'n1', position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t }] }));
}"""
RENAME_TWIN_JS = """(name) => { const d = JSON.parse(localStorage.getItem('penworks.local.v2'));
  d.notes.find(n => n.id === 'n1').name = name; d.notes.find(n => n.id === 'n1').updated_at = new Date().toISOString();
  localStorage.setItem('penworks.local.v2', JSON.stringify(d)); }"""
def hang(pg, calls): pg.evaluate("(c) => c.length ? localStorage.setItem('penworks.local.hang', JSON.stringify(c)) : localStorage.removeItem('penworks.local.hang')", calls)
def ready(pg, ms=20000): pg.wait_for_selector("body[data-ready='1']", timeout=ms)
def is_ready(pg): return pg.evaluate("document.body && document.body.dataset.ready === '1'")
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def spy(pg): return pg.evaluate("window.__t")
def note_name(pg): return pg.evaluate("(window.__pw.S.notes.find(n => n.id === 'n1') || {}).name")
def grid_has(pg, txt): return pg.evaluate("(t) => (document.getElementById('grid') || document.body).textContent.includes(t)", txt)
def toast_text(pg): return pg.evaluate("document.getElementById('toast').textContent")
def last_load(pg): return pg.evaluate("window.__pw.lastLoad")
def snap_names(pg): return pg.evaluate("window.__pw.treeq.lastTree().then(d => d && [d.folders.find(f => f.id === 'f1').name, d.notes.find(n => n.id === 'n1').name])")
def twin_folder(pg): return pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).folders.find(f => f.id === 'f1').name")
def twin_has_n9(pg): return pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).notes.some(n => n.id === 'n9')")
def folder_name(pg): return pg.evaluate("(window.__pw.S.folders.find(f => f.id === 'f1') || {}).name")
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")
def controlled(pg): return until(pg, lambda: pg.evaluate("!!navigator.serviceWorker.controller"), 5000)
def purge_ok(t): return bool(t["purge"]) and all(p["ready"] for p in t["purge"])

app = ThreadingHTTPServer(("127.0.0.1", PORT), partial(AppHandler, directory=str(ROOT))); app.daemon_threads = True
threading.Thread(target=app.serve_forever, daemon=True).start()
time.sleep(0.5)
errs = []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(SPY_JS)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.reload(); ready(pg); controlled(pg)

        # ============================================================ a fresh device (no snapshot): the read, then the purge
        group[0] = "first start"
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)
        check("1. a fresh twin, no snapshot: the read is waited for (lastLoad set), the note shows",
              last_load(pg) > 0 and note_name(pg) == "Snapshot name" and grid_has(pg, "Snapshot name"), [last_load(pg), note_name(pg)])
        gone = until(pg, lambda: not twin_has_n9(pg), 3000)
        t = spy(pg)
        check("2. purgeBin is called after ready, not before, and still empties the bin (the 40-day-old note is gone)",
              purge_ok(t) and gone, t["purge"])
        pg.wait_for_timeout(300)                           # the snapshot written
        check("3. the read is kept as the device's snapshot", snap_names(pg) == ["Snap first", "Snapshot name"], snap_names(pg))

        # ============================================================ snapshot first
        group[0] = "snapshot first"
        pg.evaluate(RENAME_TWIN_JS, "Twin name")           # the database changes meanwhile (another device)
        hang(pg, ["loadAll", "profile"])
        t0 = time.time()
        pg.goto(LOCAL, wait_until="commit", timeout=20000); ready(pg)
        pg.evaluate("window.__mark = 1")                   # gone if the page reloads
        t = spy(pg)
        dcl = pg.evaluate("Math.round(performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd)")
        print(f"snapshot first: ready at {t['ready']} ms from navigation start (DOMContentLoaded at {dcl} ms)")
        check("4. the read held back 2 s: ready in well under 1 s from navigation start, while the read is still held",
              t["ready"] is not None and t["ready"] < 1000 and t["heldAtReady"] is True, [t["ready"], t["heldAtReady"]])
        check("5. the notes are on screen at once, from the snapshot ('Snapshot name'), lastLoad 0",
              note_name(pg) == "Snapshot name" and grid_has(pg, "Snapshot name") and last_load(pg) == 0, [note_name(pg), last_load(pg)])
        check("6. no purgeBin call before ready", all(p["ready"] for p in t["purge"]), t["purge"])
        check("7. no 'Could not load' toast", "Could not load" not in toast_text(pg), toast_text(pg))
        pg.wait_for_timeout(max(0, int((t0 + 2 - time.time()) * 1000)))
        hang(pg, [])                                       # the read lands, 2 s after the start
        ok = until(pg, lambda: note_name(pg) == "Twin name" and grid_has(pg, "Twin name"), 3000)
        check("8. the read lands: the other device's name ('Twin name') on the screen, lastLoad set, no reload",
              ok and last_load(pg) > 0 and pg.evaluate("window.__mark") == 1, [note_name(pg), last_load(pg)])
        check("9. ... and kept as the device's snapshot", snap_names(pg) == ["Snap first", "Twin name"], snap_names(pg))
        ok = until(pg, lambda: len(spy(pg)["purge"]) > 0, 3000)
        t = spy(pg)
        check("10. purgeBin ran after ready (after the read landed)", ok and purge_ok(t), t["purge"])

        # ============================================================ her rename while the read is held
        group[0] = "her rename while held"
        pg.evaluate(RENAME_TWIN_JS, "Other device")        # the database changes again (another device)
        hang(pg, ["loadAll"])
        pg.goto(LOCAL, wait_until="commit", timeout=20000); ready(pg)
        pg.evaluate("window.__mark = 1")
        check("11. ready from the snapshot ('Twin name') while the read is held", note_name(pg) == "Twin name" and last_load(pg) == 0,
              [note_name(pg), last_load(pg)])
        frow(pg, "Snap first").locator(".more").click(); menu(pg, "Rename"); type_name(pg, "Her folder")
        landed = until(pg, lambda: pg.evaluate("window.__pw.treeq.length()") == 0 and twin_folder(pg) == "Her folder", 3000)
        check("12. while the read is held she renames the folder; it lands (queue empty, the database has it)",
              landed and last_load(pg) == 0, [twin_folder(pg), last_load(pg)])
        hang(pg, [])                                       # the stale read (asked before her rename) lands now
        pg.wait_for_timeout(1000)
        sf = snap_names(pg)
        check("13. the stale read is dropped, not merged over her change: snapshot and screen keep 'Her folder', lastLoad 0",
              sf[0] == "Her folder" and folder_name(pg) == "Her folder" and frow(pg, "Her folder").count() == 1 and last_load(pg) == 0,
              [sf, folder_name(pg), last_load(pg)])
        ok = until(pg, lambda: last_load(pg) > 0, 6500, 100)
        check("14. a fresh read follows by itself: 'Other device' and 'Her folder' on the screen, no reload",
              ok and note_name(pg) == "Other device" and grid_has(pg, "Other device") and folder_name(pg) == "Her folder"
              and pg.evaluate("window.__mark") == 1, [last_load(pg), note_name(pg), folder_name(pg)])
        check("15. ... and that fresh read is the device snapshot now", snap_names(pg) == ["Her folder", "Other device"], snap_names(pg))

        # ============================================================ no snapshot: it waits, as before
        group[0] = "no snapshot"
        pg.goto(BASE + "__blank")
        pg.evaluate("() => new Promise(r => { const q = indexedDB.deleteDatabase('penworks.local.local.tree'); q.onsuccess = q.onerror = q.onblocked = () => r(1); })")
        hang(pg, ["loadAll"])
        pg.goto(LOCAL, wait_until="commit")
        pg.wait_for_timeout(2500)
        check("16. no snapshot on the device: after 2.5 s still waiting for the read (not ready)", not is_ready(pg), is_ready(pg))
        check("17. ... no purgeBin call yet, no 'Could not load' toast",
              not spy(pg)["purge"] and "Could not load" not in toast_text(pg), [spy(pg)["purge"], toast_text(pg)])
        hang(pg, [])
        ok = until(pg, lambda: is_ready(pg), 3000)
        check("18. the read lands: ready, the notes on the screen, lastLoad set", ok and grid_has(pg, "Other device") and last_load(pg) > 0,
              [ok, last_load(pg)])
        ok = until(pg, lambda: len(spy(pg)["purge"]) > 0, 3000)
        check("19. purgeBin after ready", ok and purge_ok(spy(pg)), spy(pg)["purge"])

        # ============================================================ house rules
        group[0] = "house rules"
        keys = pg.evaluate("caches.keys()")
        check(f"20. cache is {VERSION}", VERSION in keys, keys)
        raw = (ROOT / "sw.js").read_bytes()
        check("21. sw.js has no BOM", not raw.startswith(b"\xef\xbb\xbf"))
        srcs = "".join((ROOT / p).read_text(encoding="utf-8") for p in ["sw.js", "js/app.js", "tests/test_snapfirst.py"])
        check("22. no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("23. no page errors", not errs, errs[:3])
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
