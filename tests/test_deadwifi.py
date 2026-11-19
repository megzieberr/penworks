# PenWorks pw-v9n checks, the 3-second rule: on a wifi that is connected but dead (requests hang, they never fail) the app
# opens from what the device kept. Headless Playwright (Python), local mode (?local=1).
# Run: python -E -P tests\test_deadwifi.py
# The rig, in this file: the app server has a stall switch (it accepts and never answers), and Chromium sends every
# outside request (the service worker's own fetches too) through a small CONNECT proxy with its own switch for the CDN
# hosts. The local twin's purgeBin / loadAll / profile hang through its test hook (localStorage penworks.local.hang).
# Groups: the worker on a good network (as before); its 3-second timeout (the cached copy); slow mode (the cache at
# once); the late answer still kept; no cached copy (it waits); the CDN files (supabase-js and its sub-modules cost 3 s,
# not 3 s each); load() falls back to the snapshot after 3 s and merges the late read; a late read older than a change
# of hers is not kept and a fresh read follows by itself; no snapshot (it waits); a hung
# profile does not hold back ready and is applied when it lands; house rules.
import sys, time, json, re, socket, select, threading, pathlib, socketserver
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT, PROXY = 8793, 8794
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
SB_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm"
VERSION = "pw-v9n"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

# ---------------------------------------------------------------- the rig
STALL = {"app": False, "cdn": False, "other": False}
SHUT = [False]
CDN = ("cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com")
def wait_free(g):
    while STALL[g] and not SHUT[0]: time.sleep(0.05)
    return not SHUT[0]

class AppHandler(SimpleHTTPRequestHandler):
    probes = {}
    def log_message(self, *a): pass
    def do_GET(self):
        if not wait_free("app"): return
        if self.path.startswith("/__probe/"):          # a file whose answer changes on every request: name:count
            name = self.path.split("/")[2].split("?")[0]
            AppHandler.probes[name] = AppHandler.probes.get(name, 0) + 1
            body = f"{name}:{AppHandler.probes[name]}".encode()
            self.send_response(200); self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        super().do_GET()

class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        c = self.request; buf = b""
        while b"\r\n\r\n" not in buf:
            d = c.recv(4096)
            if not d: return
            buf += d
        line = buf.split(b"\r\n", 1)[0].decode("latin-1").split()
        if len(line) < 2 or line[0] != "CONNECT":
            c.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n"); return
        host, port = line[1].rsplit(":", 1)
        g = "cdn" if host in CDN else "other"
        if not wait_free(g): return
        try: u = socket.create_connection((host, int(port)), timeout=15)
        except OSError:
            c.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n"); return
        c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        try:
            while not SHUT[0]:
                if STALL[g]: time.sleep(0.05); continue
                r, _, x = select.select([c, u], [], [c, u], 0.2)
                if x: break
                for s in r:
                    d = s.recv(65536)
                    if not d: return
                    (u if s is c else c).sendall(d)
        except OSError: pass
        finally:
            try: u.close()
            except OSError: pass

class TProxy(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

# ---------------------------------------------------------------- helpers
SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-11-19T08:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Dead wifi', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Snapshot name', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [{ id: 'q1', note_id: 'n1', position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t }] }));
}"""
RENAME_TWIN_JS = """(name) => { const d = JSON.parse(localStorage.getItem('penworks.local.v2'));
  d.notes.find(n => n.id === 'n1').name = name; d.notes.find(n => n.id === 'n1').updated_at = new Date().toISOString();
  localStorage.setItem('penworks.local.v2', JSON.stringify(d)); }"""
FETCH_JS = """async ([u, o]) => { const t = performance.now(); const r = await fetch(u, o || {});
  const txt = r.type === 'opaque' ? '' : await r.text(); return [txt, Math.round(performance.now() - t), r.type, r.ok]; }"""
CACHED_JS = "async (u) => { const r = await caches.match(u, { ignoreSearch: true }); return r ? r.text() : null; }"
KEYS_JS = "caches.keys().then(ks => Promise.all(ks.map(k => caches.open(k).then(c => c.keys()).then(rs => rs.map(r => r.url))))).then(a => a.flat())"
def hang(pg, calls): pg.evaluate("(c) => c.length ? localStorage.setItem('penworks.local.hang', JSON.stringify(c)) : localStorage.removeItem('penworks.local.hang')", calls)
def ready(pg, ms=20000): pg.wait_for_selector("body[data-ready='1']", timeout=ms)
def is_ready(pg): return pg.evaluate("document.body && document.body.dataset.ready === '1'")
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def note_name(pg): return pg.evaluate("(window.__pw.S.notes.find(n => n.id === 'n1') || {}).name")
def grid_has(pg, txt): return pg.evaluate("(t) => (document.getElementById('grid') || document.body).textContent.includes(t)", txt)
def toast_text(pg): return pg.evaluate("document.getElementById('toast').textContent")
def last_load(pg): return pg.evaluate("window.__pw.lastLoad")
def twin_folder(pg): return pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).folders.find(f => f.id === 'f1').name")
def folder_name(pg): return pg.evaluate("(window.__pw.S.folders.find(f => f.id === 'f1') || {}).name")
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")
def controlled(pg): return until(pg, lambda: pg.evaluate("!!navigator.serviceWorker.controller"), 5000)
def warm(ctx):
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg)
    pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
    pg.reload(); ready(pg); controlled(pg)
    return pg, errs
def stall(on, *g):
    for k in (g or STALL.keys()): STALL[k] = on
def open_timed(pg, url):
    t0 = time.time(); pg.goto(url, wait_until="commit", timeout=20000); ready(pg); return round(time.time() - t0, 2)

app = ThreadingHTTPServer(("127.0.0.1", PORT), partial(AppHandler, directory=str(ROOT))); app.daemon_threads = True
prx = TProxy(("127.0.0.1", PROXY), ProxyHandler)
for s in (app, prx): threading.Thread(target=s.serve_forever, daemon=True).start()
time.sleep(0.5)
errs_all = []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=[f"--proxy-server=http://127.0.0.1:{PROXY}"])

        # ============================================================ the worker, the app's own files
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg, errs = warm(ctx)
        group[0] = "good network"
        a1 = pg.evaluate(FETCH_JS, ["./__probe/a", None]); c1 = until(pg, lambda: pg.evaluate(CACHED_JS, "./__probe/a") == a1[0], 1500) and a1[0]
        a2 = pg.evaluate(FETCH_JS, ["./__probe/a", None]); c2 = until(pg, lambda: pg.evaluate(CACHED_JS, "./__probe/a") == a2[0], 1500) and a2[0]
        check("1. each fetch is the network's answer (a:1, then a:2), each under 1 s", a1[0] == "a:1" and a2[0] == "a:2" and a1[1] < 1000 and a2[1] < 1000, [a1, a2])
        check("2. the cache follows the network (a:1, then a:2)", c1 == "a:1" and c2 == "a:2", [c1, c2])

        group[0] = "timeout"
        stall(True, "app")
        a3 = pg.evaluate(FETCH_JS, ["./__probe/a", None])
        check("3. network silent: the cached copy (a:2) after about 3 s", a3[0] == "a:2" and 2800 <= a3[1] <= 4500, a3)

        group[0] = "slow mode"
        a4 = pg.evaluate(FETCH_JS, ["./__probe/a", None])
        js = pg.evaluate(FETCH_JS, ["./js/app.js", None])
        check("4. right after: the cached copy at once (under 0.8 s)", a4[0] == "a:2" and a4[1] < 800, a4)
        check("5. another app file (js/app.js) at once from the cache too", len(js[0]) > 100000 and js[1] < 800, js[1:])
        t = time.time(); pg.reload(wait_until="commit", timeout=20000); ready(pg); dt = round(time.time() - t, 2)
        check("6. a whole reload on the dead network while slow: ready in under 2.5 s (not 3 s a link)", dt < 2.5, dt)

        group[0] = "late answer kept"
        stall(False, "app")
        got = until(pg, lambda: pg.evaluate(CACHED_JS, "./__probe/a") in ("a:3", "a:4", "a:5"), 4000)
        check("7. the network lets go: the held fetches land and the cache has the newer answer", got, pg.evaluate(CACHED_JS, "./__probe/a"))

        group[0] = "no cached copy"
        stall(True, "app")
        pg.evaluate("() => { window.__b = null; fetch('./__probe/b').then(r => r.text()).then(t => { window.__b = t; }); }")
        pg.wait_for_timeout(5500)
        check("8. a file never cached: still waiting after 5.5 s (no error, no stand-in)", pg.evaluate("window.__b") is None, pg.evaluate("window.__b"))
        stall(False, "app")
        check("9. the network lets go: it gets the network's answer (b:1)", until(pg, lambda: pg.evaluate("window.__b") == "b:1", 4000), pg.evaluate("window.__b"))
        errs_all += errs
        ctx.close()

        # ============================================================ the worker, the CDN files (a new context: a fresh worker)
        group[0] = "cdn"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg, errs = warm(ctx)
        pg.evaluate(f"import('{SB_JS}').then(() => 1)")
        pg.wait_for_timeout(1500)
        keys = pg.evaluate(KEYS_JS)
        jsd = sorted({k for k in keys if k.startswith("https://cdn.jsdelivr.net/")})
        font_css = next((k for k in keys if k.startswith("https://fonts.googleapis.com/")), None)
        woff = next((k for k in keys if k.startswith("https://fonts.gstatic.com/")), None)
        check("10. warm: supabase-js and its sub-modules (7 files), the fonts' css and a font file are in the cache",
              len(jsd) >= 7 and font_css and woff, [len(jsd), font_css, woff])
        cdp = ctx.new_cdp_session(pg)
        cdp.send("Network.clearBrowserCache")              # the browser's own http cache gone: the worker must ask the network
        pg.reload(); ready(pg)
        cdp.send("Network.clearBrowserCache")
        stall(True, "cdn")
        t0 = time.time()
        ok = pg.evaluate(f"import('{SB_JS}').then(m => typeof m.createClient)")
        dt = round(time.time() - t0, 2)
        check("11. CDN silent: supabase-js and all its sub-modules load from the cache in about 3 s in all (not 3 s each)",
              ok == "function" and 2.8 <= dt <= 5.0, [ok, dt])
        f = pg.evaluate(FETCH_JS, [font_css, {"mode": "no-cors"}])
        w = pg.evaluate(FETCH_JS, [woff, None])
        check("12. while slow: the fonts' css and a font file from the cache at once", f[1] < 800 and f[2] == "opaque" and w[1] < 800 and w[3], [f[1:], w[1:]])
        stall(False, "cdn")
        errs_all += errs
        ctx.close()

        # ============================================================ load(): the 3-second budget
        group[0] = "load() falls back"
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg, errs = warm(ctx)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)
        check("13. a good network: the tree read is fresh (lastLoad set), the note shows", last_load(pg) > 0 and note_name(pg) == "Snapshot name", [last_load(pg), note_name(pg)])
        pg.wait_for_timeout(300)                           # the snapshot written
        pg.evaluate(RENAME_TWIN_JS, "Twin name")           # the database changes meanwhile (another device)
        hang(pg, ["purgeBin", "loadAll", "profile"])
        dt = open_timed(pg, LOCAL)
        check("14. purgeBin, loadAll and profile all hung: ready after about 3 s", 2.7 <= dt <= 5.0, dt)
        check("15. the screen is the device's snapshot ('Snapshot name'), lastLoad 0 (read again at the next chance)",
              note_name(pg) == "Snapshot name" and grid_has(pg, "Snapshot name") and last_load(pg) == 0, [note_name(pg), last_load(pg)])
        check("16. no 'Could not load' toast", "Could not load" not in toast_text(pg), toast_text(pg))
        hang(pg, [])
        ok = until(pg, lambda: note_name(pg) == "Twin name" and grid_has(pg, "Twin name"), 3000)
        check("17. the late read lands: merged in ('Twin name' on the screen), lastLoad set", ok and last_load(pg) > 0, [note_name(pg), last_load(pg)])
        snap = pg.evaluate("window.__pw.treeq.lastTree().then(d => d.notes.find(n => n.id === 'n1').name)")
        check("18. ... and kept as the device's snapshot", snap == "Twin name", snap)

        group[0] = "late read after her change"
        pg.evaluate(RENAME_TWIN_JS, "Other device")        # the database changes again (another device)
        hang(pg, ["purgeBin", "loadAll", "profile"])
        dt = open_timed(pg, LOCAL)
        frow(pg, "Dead wifi").locator(".more").click(); menu(pg, "Rename"); type_name(pg, "Her folder")
        landed = until(pg, lambda: pg.evaluate("window.__pw.treeq.length()") == 0 and twin_folder(pg) == "Her folder", 3000)
        check("19. while the read hangs she renames the folder; it lands (queue empty, the database has it)", landed and last_load(pg) == 0, [dt, twin_folder(pg), last_load(pg)])
        hang(pg, [])                                       # the stale read (asked before her rename) lands now
        pg.wait_for_timeout(1000)
        sf = pg.evaluate("window.__pw.treeq.lastTree().then(d => [d.folders.find(f => f.id === 'f1').name, d.notes.find(n => n.id === 'n1').name])")
        check("20. the stale read is not kept: the device snapshot still has her folder name, lastLoad still 0",
              sf[0] == "Her folder" and last_load(pg) == 0, [sf, last_load(pg)])
        check("21. her change is still on the screen", folder_name(pg) == "Her folder" and frow(pg, "Her folder").count() == 1, folder_name(pg))
        ok = until(pg, lambda: last_load(pg) > 0, 6500, 100)
        check("22. a fresh read follows by itself within about 6 s: lastLoad set, the database's note name plus her folder name",
              ok and note_name(pg) == "Other device" and grid_has(pg, "Other device") and folder_name(pg) == "Her folder", [last_load(pg), note_name(pg), folder_name(pg)])
        sf = pg.evaluate("window.__pw.treeq.lastTree().then(d => [d.folders.find(f => f.id === 'f1').name, d.notes.find(n => n.id === 'n1').name])")
        check("23. ... and that fresh read is the device snapshot now", sf == ["Her folder", "Other device"], sf)

        group[0] = "hung profile"
        tray0 = pg.evaluate("window.__pw.tray()")
        theirs = {"tool": tray0["lastInk"], "pen": tray0["pen"], "highlighter": tray0["highlighter"], "restyle": tray0["restyle"],
                  "order": list(reversed(tray0["order"])), "spec": tray0["spec"]}
        pg.evaluate("(t) => window.__pw.api.setSettings({ tray: t, tray_at: '2030-01-01T00:00:00.000Z' })", theirs)
        hang(pg, ["profile"])
        dt = open_timed(pg, LOCAL)
        check("24. only the profile hung: ready after about 3 s, not held back", 2.7 <= dt <= 5.0, dt)
        check("25. the tree read was on time (lastLoad set), the tray still this device's",
              last_load(pg) > 0 and pg.evaluate("window.__pw.tray().order") == tray0["order"], last_load(pg))
        hang(pg, [])
        ok = until(pg, lambda: pg.evaluate("window.__pw.tray().order") == theirs["order"], 3000)
        check("26. the profile lands late: its newer tray is applied then", ok, pg.evaluate("window.__pw.tray().order")[:3])

        group[0] = "no snapshot"
        pg.goto(BASE + "__probe/blank")
        pg.evaluate("() => new Promise(r => { const q = indexedDB.deleteDatabase('penworks.local.local.tree'); q.onsuccess = q.onerror = q.onblocked = () => r(1); })")
        hang(pg, ["loadAll"])
        pg.goto(LOCAL, wait_until="commit")
        pg.wait_for_timeout(6000)
        check("27. no snapshot on the device: after 6 s still waiting for the read (not ready)", not is_ready(pg), is_ready(pg))
        check("28. ... and no 'Could not load' toast", "Could not load" not in toast_text(pg), toast_text(pg))
        hang(pg, [])
        ok = until(pg, lambda: is_ready(pg), 3000)
        check("29. the read lands: ready, the notes on the screen", ok and grid_has(pg, "Other device") and last_load(pg) > 0, [ok, last_load(pg)])

        # ============================================================ house rules
        group[0] = "house rules"
        keys = pg.evaluate("caches.keys()")
        check(f"30. cache is {VERSION}", VERSION in keys, keys)
        raw = (ROOT / "sw.js").read_bytes()
        check("31. sw.js has no BOM", not raw.startswith(b"\xef\xbb\xbf"))
        srcs = "".join((ROOT / p).read_text(encoding="utf-8") for p in ["sw.js", "js/app.js", "js/local-backend.js", "tests/test_deadwifi.py"])
        check("32. no em-dashes in the changed files", chr(0x2014) not in srcs)
        errs_all += errs
        check("33. no page errors", not errs_all, errs_all[:3])
        ctx.close()
        b.close()
finally:
    SHUT[0] = True; stall(False)
    app.shutdown(); prx.shutdown()

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
