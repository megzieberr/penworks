# PenWorks pw-v9n checks, the sign-in check on a bad network: when supabase-js cannot answer getSession() within 3 s
# (an EXPIRED token whose refresh hangs or fails), the app opens on the sign-in kept on the device and the refresh goes
# on in the background; a data request that would go out WITHOUT a sign-in (the publishable key as Bearer) never leaves:
# it fails like no connection, so the queues wait instead of being refused. Headless Playwright (Python), LIVE mode with a
# FAKE session in localStorage: every *.supabase.co request is answered, failed or held by a page route here, and the
# Realtime websocket (a page route cannot see it) is pointed at a closed local port. Nothing reaches Supabase; no login.
# Run: python -E -P tests\test_signin.py
# Groups: the start (unexpired, dead wifi, offline, no session, a fresh refresh, a refusal, garbage); rule C (a change
# made while the token cannot be refreshed waits and lands later, never refused; a refusal later still drops nothing;
# an erase-only stroke op never "succeeds" without a sign-in); the login path untouched; house rules.
import sys, time, json, base64, pathlib, subprocess
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
import threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8795
BASE = f"http://127.0.0.1:{PORT}/"
VERSION = "pw-v9n"
KEY = "sb-duibtdcxmnvsuczuceld-auth-token"
SB = "**://duibtdcxmnvsuczuceld.supabase.co/**"
SB_KEY = "sb_publishable_bj2rpL9bwuYSrWCnZxkAuA_uIHYRVJR"     # the publishable key (public, in api.js)
UID = "00000000-0000-4000-8000-0000000dead1"
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*",
        "content-type": "application/json"}

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

class AppHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

# ---------------------------------------------------------------- the fake Supabase
def b64(o): return base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
def session(ahead, refresh="old-fake-token"):
    exp = int(time.time()) + ahead
    tok = b64({"alg": "HS256", "typ": "JWT"}) + "." + b64({"sub": UID, "exp": exp, "role": "authenticated", "aud": "authenticated"}) + ".x"
    return {"access_token": tok, "token_type": "bearer", "expires_in": 3600, "expires_at": exp, "refresh_token": refresh,
            "user": {"id": UID, "aud": "authenticated", "role": "authenticated", "email": "signin@penworks.app",
                     "app_metadata": {}, "user_metadata": {}, "created_at": "2026-01-01T00:00:00Z"}}
SNAP_JS = """(uid) => new Promise((ok, no) => {
  const r = indexedDB.open('penworks.live.' + uid + '.tree', 1);
  r.onupgradeneeded = () => { r.result.createObjectStore('queue'); r.result.createObjectStore('snapshot'); };
  r.onerror = () => no(r.error);
  r.onsuccess = () => { const db = r.result, t = db.transaction(['snapshot'], 'readwrite'), ts = '2026-11-19T08:00:00Z';
    t.objectStore('snapshot').put({ at: ts,
      folders: [{ id: 'f-si', owner_id: uid, parent_id: null, name: 'Sign-in', colour: null, position: 0, deleted_at: null, created_at: ts, updated_at: ts }],
      notes: [{ id: 'n-si', owner_id: uid, folder_id: 'f-si', name: 'Kept note', pinned: false, cover_path: null, deleted_at: null, created_at: ts, updated_at: ts }],
      pages: [{ id: 'p-si', owner_id: uid, note_id: 'n-si', position: 0, orientation: 'portrait', background: 'grid', bookmark: false, deleted_at: null, created_at: ts, updated_at: ts }] }, 'tree');
    t.oncomplete = () => { db.close(); ok(true); }; t.onerror = () => no(t.error); };
})"""
STORED_JS = f"""() => {{ const v = localStorage.getItem('{KEY}'); if (v == null) return null;
  try {{ const o = JSON.parse(v); return o.refresh_token === 'fresh-fake-token' ? 'fresh' : 'old'; }} catch (_) {{ return 'garbage'; }} }}"""
STATE_JS = "() => ({ login: !document.getElementById('login').hidden, app: !document.getElementById('app').hidden })"

class Fake:
    """every Supabase call this page makes: token = 'hang' | 'offline' | 'fresh' | 'refuse' | '503'; rest = 'hang' | 'answer'"""
    def __init__(self, pg, token="hang", rest="hang"):
        self.token, self.rest, self.seen, self.held, self.t0 = token, rest, [], [], time.time()
        pg.route(SB, self.on_rest)
        pg.route("**/auth/v1/token**", self.on_token)
    def on_token(self, route):
        r = route.request
        if r.method == "OPTIONS": return route.fulfill(status=204, headers=CORS, body="")
        self.seen.append((round(time.time() - self.t0, 1), "TOKEN", self.token))
        if self.token == "hang": self.held.append(route); return
        if self.token == "offline": return route.abort("internetdisconnected")
        if self.token == "fresh": return route.fulfill(status=200, headers=CORS, body=json.dumps(session(3600, "fresh-fake-token")))
        if self.token == "refuse": return route.fulfill(status=400, headers=CORS, body=json.dumps(
            {"code": 400, "error_code": "refresh_token_not_found", "msg": "Invalid Refresh Token: Refresh Token Not Found"}))
        return route.fulfill(status=503, headers=CORS, body='{"message":"try later"}')
    def on_rest(self, route):
        r = route.request
        if r.method == "OPTIONS": return route.fulfill(status=204, headers=CORS, body="")
        a = r.headers.get("authorization", "")
        who = "anon" if a == "Bearer " + SB_KEY else "user"
        path = r.url.split(".supabase.co", 1)[1].split("?")[0]
        self.seen.append((round(time.time() - self.t0, 1), r.method + " " + path, who))
        if self.rest == "offline": return route.abort("internetdisconnected")
        if self.rest == "hang": self.held.append(route); return
        if path.endswith("/rpc/login_gate"):
            return route.fulfill(status=200, headers=CORS, body='{"status":"wrong","left":4}')
        if r.method == "PATCH":                       # RLS: a request with no sign-in sees no row
            return route.fulfill(status=200, headers=CORS, body="[]" if who == "anon" else '[{"id":"n-si"}]')
        if r.method == "GET" and "/rest/" in path: return route.fulfill(status=200, headers=CORS, body="[]")
        if r.method == "GET": return route.fulfill(status=404, headers=CORS, body='{"message":"not found"}')
        return route.fulfill(status=200 if r.method != "DELETE" else 204, headers=CORS, body="[]" if r.method != "DELETE" else "")
    def anon_writes(self): return [s for s in self.seen if s[2] == "anon" and not s[1].startswith("GET") and "login_gate" not in s[1]]

def shut(f, ctx):
    for r in f.held:
        try: r.abort()
        except Exception: pass
    f.held.clear(); ctx.close()

def fresh(b):
    """a new context, the app opened twice on a good network (the login screen: supabase-js and the worker's cache)"""
    ctx = b.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route(SB, lambda r: r.abort("internetdisconnected"))        # nothing on the warm-up either
    pg.goto(BASE); pg.wait_for_selector("#login:not([hidden])", timeout=30000)
    pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
    pg.reload(); pg.wait_for_selector("#login:not([hidden])", timeout=30000)
    pg.unroute(SB)
    return ctx, pg, errs

def seed(pg, how, ahead=-3600):
    if how == "session": pg.evaluate(f"(s) => localStorage.setItem('{KEY}', JSON.stringify(s))", session(ahead))
    elif how == "garbage": pg.evaluate(f"() => localStorage.setItem('{KEY}', 'not json {{')")
    else: pg.evaluate(f"() => localStorage.removeItem('{KEY}')")
    pg.evaluate(SNAP_JS, UID)
    pg.goto("about:blank")

def open_until(pg, cap=12.0):
    """seconds until the login or the app shows (None = neither within cap), and which"""
    t0 = time.time(); pg.goto(BASE, wait_until="commit")
    while time.time() - t0 < cap:
        try:
            s = pg.evaluate(STATE_JS)
            if s["login"] or s["app"]: return round(time.time() - t0, 2), ("app" if s["app"] else "login")
        except Exception: pass
        pg.wait_for_timeout(50)
    return None, None

def until(pg, fn, ms, step=200):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)

app = ThreadingHTTPServer(("127.0.0.1", PORT), partial(AppHandler, directory=str(ROOT))); app.daemon_threads = True
threading.Thread(target=app.serve_forever, daemon=True).start()
time.sleep(0.5)
errs_all = []
try:
    with sync_playwright() as pw:
        # the Realtime websocket cannot be routed in the page: its host goes to a closed local port (fails at once)
        b = pw.chromium.launch(args=["--host-resolver-rules=MAP duibtdcxmnvsuczuceld.supabase.co 127.0.0.1:9"])

        # ============================================================ the start
        group[0] = "the start"
        ctx, pg, errs = fresh(b); seed(pg, "session", ahead=3600); f = Fake(pg)
        t, what = open_until(pg)
        check("1. a token still good, Supabase silent: the app at once (no 3 s wait)", what == "app" and t < 2.5, [t, what])
        errs_all += errs; shut(f, ctx)

        ctx, pg, errs = fresh(b); seed(pg, "session"); f = Fake(pg)
        t, what = open_until(pg)
        check("2. C: token EXPIRED, Supabase silent (dead wifi): the app opens after about 3 s, not the login", what == "app" and 2.8 < t < 5.5, [t, what])
        ok = until(pg, lambda: pg.evaluate("document.body.dataset.ready === '1' && document.body.textContent.includes('Kept note')"), 5000)
        check("3. ... her kept notes on the screen, ready (3 s more: the tree read hangs too, the 3-second rule)", ok)
        check("4. ... the sign-in is still on the device, and the refresh was asked (it carries on in the background)",
              pg.evaluate(STORED_JS) == "old" and any(s[1] == "TOKEN" for s in f.seen), [pg.evaluate(STORED_JS), f.seen[:3]])
        errs_all += errs; shut(f, ctx)

        ctx, pg, errs = fresh(b); seed(pg, "session"); f = Fake(pg, token="offline", rest="offline")
        t, what = open_until(pg)
        check("5. D: token EXPIRED, the refresh fails at once (offline): the app after about 3 s, not the login", what == "app" and t < 5.5, [t, what])
        check("6. ... the sign-in is still on the device", pg.evaluate(STORED_JS) == "old")
        errs_all += errs; shut(f, ctx)

        ctx, pg, errs = fresh(b); seed(pg, "none"); f = Fake(pg)
        t, what = open_until(pg)
        check("7. E: no sign-in on the device, Supabase silent: the login screen at once", what == "login" and t < 2.0, [t, what])
        errs_all += errs; shut(f, ctx)

        ctx, pg, errs = fresh(b); seed(pg, "session"); f = Fake(pg, token="fresh")
        t, what = open_until(pg)
        check("8. F: the refresh answers a fresh session: the app at once", what == "app" and t < 2.5, [t, what])
        check("9. ... the fresh sign-in is saved on the device", until(pg, lambda: pg.evaluate(STORED_JS) == "fresh", 3000))
        errs_all += errs; shut(f, ctx)

        ctx, pg, errs = fresh(b); seed(pg, "session"); f = Fake(pg, token="refuse")
        t, what = open_until(pg)
        check("10. G: the refresh is REFUSED (refresh_token_not_found): the login screen", what == "login" and t < 2.5, [t, what])
        check("11. ... and the kept sign-in is gone from the device", pg.evaluate(STORED_JS) is None, pg.evaluate(STORED_JS))
        errs_all += errs; shut(f, ctx)

        ctx, pg, errs = fresh(b); seed(pg, "garbage"); f = Fake(pg)
        t, what = open_until(pg)
        check("12. H: the kept sign-in is garbage: the login screen (as before)", what == "login" and t < 2.0, [t, what])
        errs_all += errs; shut(f, ctx)

        # ============================================================ rule C: no change of hers refused for want of a refresh
        group[0] = "rule C"
        ctx, pg, errs = fresh(b); seed(pg, "session"); f = Fake(pg, token="503", rest="answer")
        t, what = open_until(pg)
        pg.wait_for_function("document.body.dataset.ready === '1'", timeout=15000)
        pg.evaluate("() => { window.__rv = undefined; __pw.treeq.push('renameNote', ['n-si', 'Renamed without a refresh']).then((v) => { window.__rv = v; }); }")
        # supabase-js retries a 503 for about 25 s, then gives up with the session KEPT: before pw-v9n the next request
        # went out with no sign-in (the publishable key as Bearer) and RLS refused it; the tree queue drops a refusal
        pg.wait_for_timeout(65000)
        st = pg.evaluate("() => ({ dropped: __pw.failed(), queued: __pw.treeq.queued().length, landed: window.__rv === undefined ? 'not yet' : window.__rv, dot: __pw.treeq.saveState().state })")
        check("13. the app opened on the kept sign-in (refresh answering 503)", what == "app", [t, what])
        check("14. 65 s of failed refreshes: no write left without a sign-in", not f.anon_writes(), f.anon_writes()[:4])
        check("15. ... the rename is still queued, nothing dropped, the dot never says refused",
              st["dropped"] == 0 and st["queued"] == 1 and st["landed"] == "not yet" and st["dot"] in ("waiting", "saving"), st)
        f.token = "fresh"
        ok = until(pg, lambda: pg.evaluate("window.__rv !== undefined"), 60000)
        st = pg.evaluate("() => ({ dropped: __pw.failed(), queued: __pw.treeq.queued().length, landed: window.__rv })")
        pw_ok = [s for s in f.seen if s[1].startswith("PATCH /rest/v1/notes")]
        check("16. the refresh answers: the rename lands, with her sign-in", ok and st["landed"] is True and st["queued"] == 0
              and pw_ok and pw_ok[-1][2] == "user", [st, pw_ok[-2:]])
        check("17. ... still no write without a sign-in, nothing dropped", not f.anon_writes() and st["dropped"] == 0, f.anon_writes()[:4])
        errs_all += errs; shut(f, ctx)

        ctx, pg, errs = fresh(b); seed(pg, "session"); f = Fake(pg, token="hang", rest="answer")
        t, what = open_until(pg)
        pg.wait_for_function("document.body.dataset.ready === '1'", timeout=15000)
        pg.evaluate("() => { window.__rv = undefined; __pw.treeq.push('renameNote', ['n-si', 'Renamed, then refused']).then((v) => { window.__rv = v; }); }")
        pg.wait_for_timeout(1000)
        f.token = "refuse"
        for r in f.held: r.fulfill(status=400, headers=CORS, body=json.dumps(
            {"code": 400, "error_code": "refresh_token_not_found", "msg": "Invalid Refresh Token: Refresh Token Not Found"}))
        f.held.clear()
        pg.wait_for_timeout(20000)
        st = pg.evaluate("() => ({ dropped: __pw.failed(), queued: __pw.treeq.queued().length, landed: window.__rv === undefined ? 'not yet' : window.__rv })")
        check("18. a refusal that lands AFTER the app opened: the sign-in is gone from the device", pg.evaluate(STORED_JS) is None)
        check("19. ... no write left without a sign-in, the rename still queued, nothing dropped",
              not f.anon_writes() and st["dropped"] == 0 and st["queued"] == 1, [st, f.anon_writes()[:3]])
        # an erase-only stroke op: an anonymous DELETE meets no row and answers no error, so it would count as done
        e = pg.evaluate("""async () => { try { await __pw.api.putStrokes(['00000000-0000-4000-8000-00000000e4a5'], []); return 'resolved'; }
                           catch (x) { return 'threw code=' + (x && x.code ? x.code : '') + ' ' + ((x && x.message) || ''); } }""")
        check("20. with no sign-in an erase-only stroke op fails like no connection (no code), it never counts as done",
              e.startswith("threw code= ") and not f.anon_writes(), [e, f.anon_writes()[:3]])
        errs_all += errs; shut(f, ctx)

        # ============================================================ the login path untouched
        group[0] = "the login"
        ctx, pg, errs = fresh(b); seed(pg, "none"); f = Fake(pg, rest="answer")
        t, what = open_until(pg)
        pg.fill("#lu", "nobody"); pg.fill("#lp", "12345"); pg.press("#lp", "Enter")
        msg = until(pg, lambda: pg.evaluate("document.getElementById('loginMsg').textContent"), 8000)
        gate = [s for s in f.seen if "login_gate" in s[1]]
        check("21. the login lock's question still goes out before any sign-in (login_gate, no sign-in yet)", gate and gate[0][2] == "anon", gate)
        check("22. ... and its answer reaches the screen ('4 tries left')", "4 tries left" in (msg or ""), msg)
        errs_all += errs; shut(f, ctx)

        # ============================================================ house rules
        group[0] = "house rules"
        sw = (ROOT / "sw.js").read_bytes()
        check(f"23. sw.js is still {VERSION}, no BOM, and its pw-v9n line names the sign-in check",
              f'const CACHE = "{VERSION}"'.encode() in sw and not sw.startswith(b"\xef\xbb\xbf")
              and any(b"pw-v9n" in l and b"sign-in" in l for l in sw.splitlines()))
        head = subprocess.run(["git", "show", "HEAD:js/api.js"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
        now = (ROOT / "js" / "api.js").read_text(encoding="utf-8")
        def part(src, a, z): i = src.find(a); return src[i:src.find(z, i)] if i >= 0 else None
        same = all(part(head, a, z) and part(head, a, z) == part(now, a, z) for a, z in
                   [("async signIn(", "async signOut()"), ("async signOut()", "\n"), ("async function me(", "\n}")])
        check("24. signIn, signOut and me() are word for word as before", same)
        check("25. no em-dashes in the changed files", chr(0x2014) not in now + (ROOT / "tests" / "test_signin.py").read_text(encoding="utf-8"))
        check("26. no page errors", not errs_all, errs_all[:3])
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
