# PenWorks login lock checks (pw-v9h, migration 0008, briefs/LOGIN-GATE-BRIEF.md): liveApi.signIn asks login_gate first.
# Run: python -E -P tests/test_gate.py                       (add --shots <folder> for the four login screen pictures)
# The app is opened WITHOUT ?local=1, so liveApi runs, with service workers blocked. EVERY request to the Supabase project
# is answered here by route handlers: nothing ever reaches the real project. A request this file did not plan for is
# recorded and fails the suite. The supabase-js library itself comes from its CDN as in the app (the internet must be on).
# Made-up names only: gatetest, code 13579, a made-up 64-hex secret. tools/arm_gate.py runs here with drop_pdf.call
# replaced and a temp env file; penworks\.env is never opened.
# What it proves: the gate's six answers (ok, wrong, locked today and tomorrow, none, missing, 500 and aborted), the
# token request carrying the secret and never the code, a 32-character password skipping the gate, the rpc body, the
# login form's lines, the SQL file's rules as text, arm_gate's runs (armed, twice, a race, four refusals, --check), sw.js.
import sys, subprocess, time, pathlib, json, re, tempfile, io, argparse
from datetime import datetime, timedelta, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8831
APP = f"http://127.0.0.1:{PORT}/"
BARE = f"http://127.0.0.1:{PORT}/__gate_test.html"      # an empty page on the app's origin (answered by a route below)
SB = re.compile(r"https://duibtdcxmnvsuczuceld\.supabase\.co/.*")
TZ = timezone(timedelta(hours=2))                         # the browser runs in Africa/Johannesburg (UTC+2, no summer time)
USER, CODE = "gatetest", "13579"
SECRET = "3f9a1c0b7e2d4a6f8c1b3e5d7f9a0c2e4b6d8f1a3c5e7b9d0f2a4c6e8b0d1f3a"

ap = argparse.ArgumentParser(); ap.add_argument("--shots"); ARGS = ap.parse_args()

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

# ------------------------------------------------------------ the pretend Supabase project
S = {"gate": None, "token": None, "log": [], "stray": []}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS"}
def session_json():
    now = int(time.time())
    return {"access_token": "fake-access", "token_type": "bearer", "expires_in": 3600, "expires_at": now + 3600,
            "refresh_token": "fake-refresh",
            "user": {"id": "00000000-0000-4000-8000-000000000001", "aud": "authenticated", "role": "authenticated",
                     "email": USER + "@penworks.app", "app_metadata": {}, "user_metadata": {}, "created_at": "2026-11-13T08:00:00Z"}}
def reply(route, spec):
    if spec == "abort": route.abort(); return
    st, body = spec
    route.fulfill(status=st, headers={**CORS, "Content-Type": "application/json"}, body=json.dumps(body))
def on_sb(route):
    rq = route.request
    if rq.method == "OPTIONS":
        route.fulfill(status=204, headers=CORS); return
    path = rq.url.split(".supabase.co", 1)[1]
    try: body = json.loads(rq.post_data or "null")
    except Exception: body = rq.post_data
    if rq.method == "POST" and path.startswith("/rest/v1/rpc/login_gate") and S["gate"] is not None:
        S["log"].append(("gate", body)); reply(route, S["gate"]); return
    if rq.method == "POST" and path.startswith("/auth/v1/token?grant_type=password") and S["token"] is not None:
        S["log"].append(("token", body)); reply(route, S["token"]); return
    S["stray"].append((rq.method, path)); route.abort()

def scene(gate, token=(200, None)):
    S["gate"] = gate
    S["token"] = (token[0], session_json() if token[1] is None else token[1])
    S["log"].clear()
def calls(kind): return [b for k, b in S["log"] if k == kind]

def hhmm(dt_utc):
    loc = dt_utc.astimezone(TZ); now = datetime.now(TZ)
    return ("" if loc.date() == now.date() else "tomorrow ") + "at " + loc.strftime("%H:%M")

SIGNIN = "([u, p]) => import('./js/api.js').then((m) => m.api.signIn(u, p))"
MISSING = {"code": "PGRST202", "details": "Searched for the function public.login_gate with parameters p_code, p_username",
           "hint": None, "message": "Could not find the function public.login_gate(p_code, p_username) in the schema cache"}
REFUSED = {"code": "invalid_credentials", "error_code": "invalid_credentials", "msg": "Invalid login credentials"}

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, service_workers="block", timezone_id="Africa/Johannesburg")
        ctx.route(SB, on_sb)
        ctx.route(re.compile(r".*/__gate_test\.html$"), lambda r: r.fulfill(status=200, content_type="text/html", body="<!doctype html><title>gate</title>"))
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BARE)
        signin = lambda u, p: pg.evaluate(SIGNIN, [u, p])

        # ------------------------------------------------------------ the API, answer by answer
        group[0] = "A. signIn"
        scene((200, {"status": "ok", "secret": SECRET}))
        r = signin(USER, CODE); t = calls("token")
        check("1. gate ok: one token request, with the secret, never the code; signIn says ok",
              r.get("ok") is True and len(t) == 1 and t[0].get("password") == SECRET and CODE not in json.dumps(t), [r, t])

        scene((200, {"status": "wrong", "left": 3}))
        r3 = signin(USER, "11111")
        scene((200, {"status": "wrong", "left": 1}))
        r1 = signin(USER, "11112"); t = calls("token")
        check("2. gate wrong, left 3: the exact line", r3 == {"ok": False, "message": "That password is not right. 3 tries left."}, r3)
        check("2. gate wrong, left 1: the exact line, no token request", r1 == {"ok": False, "message": "That password is not right. 1 try left."} and not t, [r1, t])
        scene((200, {"status": "wrong"}))
        r = signin(USER, "11113")
        check("2. gate wrong without left: no count sentence", r == {"ok": False, "message": "That password is not right."}, r)

        until = datetime.now(timezone.utc) + timedelta(minutes=30)
        if until.astimezone(TZ).date() != datetime.now(TZ).date(): until = datetime.now(timezone.utc) + timedelta(seconds=30)
        scene((200, {"status": "locked", "until": until.isoformat()}))
        r = signin(USER, CODE); t = calls("token")
        want = "Too many wrong tries. Try again " + hhmm(until) + "."
        check("3. gate locked until today: the exact line with HH:MM, no token request", r == {"ok": False, "message": want} and not t, [r, want, t])
        tm = (datetime.now(TZ) + timedelta(days=1)).replace(hour=9, minute=10, second=0, microsecond=0)
        scene((200, {"status": "locked", "until": tm.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}))
        r = signin(USER, CODE)
        check("3. gate locked until tomorrow: the 'tomorrow at' line", r == {"ok": False, "message": "Too many wrong tries. Try again tomorrow at 09:10."}, r)

        scene((200, {"status": "none"}))
        r = signin("nogate", "24680"); t = calls("token")
        check("4. gate none: the old way, the token request carries the typed password",
              r.get("ok") is True and len(t) == 1 and t[0].get("password") == "24680" and t[0].get("email") == "nogate@penworks.app", [r, t])
        scene((200, {"status": "none"}), (400, REFUSED))
        r = signin("nogate", "24689")
        check("4. gate none, wrong password: today's line", r == {"ok": False, "message": "That username or password is not right."}, r)

        scene((404, MISSING))
        r = signin(USER, CODE); t = calls("token"); g = calls("gate")
        check("5. gate missing (404, PGRST202): the old way runs with the typed code", r.get("ok") is True and len(g) == 1 and len(t) == 1 and t[0].get("password") == CODE, [r, g, t])

        scene((500, {"code": "XX000", "message": "boom"}))
        r = signin(USER, CODE); t = calls("token")
        check("6. gate 500: the 'Could not reach' line, no token request", r == {"ok": False, "message": "Could not reach PenWorks. Check the connection."} and not t, [r, t])
        scene("abort")
        r = signin(USER, CODE); t = calls("token")
        check("6. gate request aborted: the 'Could not reach' line, no token request", r == {"ok": False, "message": "Could not reach PenWorks. Check the connection."} and not t, [r, t])

        scene((200, {"status": "ok", "secret": SECRET}), (400, REFUSED))
        r = signin(USER, CODE)
        check("7. gate ok but the secret refused: the 'do not match' line", r == {"ok": False, "message": "The login lock and the password do not match. Ask Claude to check it."}, r)

        long_pw = "a" * 32
        scene((200, {"status": "ok", "secret": SECRET}))
        r = signin(USER, long_pw); g = calls("gate"); t = calls("token")
        check("8. a 32-character password: the gate is NOT asked, the old way signs in with it", r.get("ok") is True and not g and len(t) == 1 and t[0].get("password") == long_pw, [r, g, t])
        scene((200, {"status": "wrong", "left": 4}))
        signin(USER, "a" * 31); g = calls("gate")
        check("8. a 31-character password still asks the gate", len(g) == 1, g)

        scene((200, {"status": "wrong", "left": 4}))
        signin("  GateTest ", CODE); g = calls("gate")
        check("9. the rpc body is exactly p_username (trimmed, lower case) and p_code", g == [{"p_username": "gatetest", "p_code": CODE}], g)
        check("no page errors (the API page)", not errs, errs)
        pg.close()

        # ------------------------------------------------------------ the login form in the app itself
        group[0] = "B. form"
        def open_app(p):
            p.goto(BARE); p.evaluate("localStorage.clear()")       # the API checks above left a signed-in session here
            p.goto(APP); p.wait_for_selector("#login:not([hidden])", timeout=20000)
        def submit(p, u, c):
            p.fill("#lu", u); p.fill("#lp", c); p.click("#loginBtn")
            p.wait_for_function("() => document.getElementById('loginMsg').textContent.length > 0 && !document.getElementById('loginBtn').disabled", timeout=10000)
            return p.locator("#loginMsg").text_content()
        ap_ = ctx.new_page(); aerr = []
        ap_.on("pageerror", lambda e: aerr.append(str(e)))
        open_app(ap_)
        scene((200, {"status": "wrong", "left": 3}))
        m = submit(ap_, USER, "11111"); t = calls("token")
        check("10. a wrong code: its line in #loginMsg, the button enabled again, no token request",
              m == "That password is not right. 3 tries left." and not ap_.locator("#loginBtn").is_disabled() and not t, [m, t])
        scene((200, {"status": "locked", "until": until.isoformat()}))
        ap_.evaluate("document.getElementById('loginMsg').textContent = ''")
        m = submit(ap_, USER, CODE); t = calls("token")
        check("10. locked: its line in #loginMsg, the button enabled again, no token request",
              m == want and not ap_.locator("#loginBtn").is_disabled() and not t, [m, want, t])
        ap_.wait_for_timeout(2000)
        m2 = ap_.locator("#loginMsg").text_content()
        check("3. locked: the same text 2 s later (a fixed line, no timer)", m2 == m, [m, m2])
        check("no page errors (the app)", not aerr, aerr)

        if ARGS.shots:
            out = pathlib.Path(ARGS.shots); out.mkdir(parents=True, exist_ok=True)
            for w, h in [(412, 915), (1280, 800)]:
                sp = ctx.new_page(); sp.set_viewport_size({"width": w, "height": h}); open_app(sp)
                scene((200, {"status": "wrong", "left": 3})); submit(sp, USER, "11111")
                sp.screenshot(path=str(out / f"gate-wrong-{w}x{h}.png"))
                scene((200, {"status": "locked", "until": until.isoformat()}))
                sp.evaluate("document.getElementById('loginMsg').textContent = ''"); submit(sp, USER, CODE)
                sp.screenshot(path=str(out / f"gate-locked-{w}x{h}.png"))
                sp.close()
            check("shots: four PNGs", len(list(out.glob("gate-*.png"))) >= 4, sorted(p.name for p in out.glob("gate-*.png")))

        group[0] = "C. no stray requests"
        check("no Supabase request this file did not plan for (none ever reached the real project)", not S["stray"], S["stray"])
        ctx.close()
        b.close()
finally:
    srv.terminate()

# ------------------------------------------------------------ the SQL file, as text
group[0] = "D. SQL"
sql = (ROOT / "supabase" / "migrations" / "0008_login_gate.sql").read_text(encoding="utf-8")
code_sql = "\n".join(l.split("--", 1)[0] for l in sql.splitlines())          # comments out
def fn(name):
    m = re.search(r"create or replace function public\." + name + r"\(.*?\n\$\$;", code_sql, re.S)
    return m.group(0) if m else ""
gate_fn, arm_fn = fn("login_gate"), fn("arm_login_gate")
for nm, f in [("login_gate", gate_fn), ("arm_login_gate", arm_fn)]:
    check(f"11. {nm}: security definer, set search_path = '', neither stable nor immutable",
          f and "security definer" in f and "set search_path = ''" in f and not re.search(r"\b(stable|immutable)\b", f), nm)
check("11. login_gate reads its row for update", "where username = n for update" in gate_fn)
check("11. least(g.locks, 10) inside power", "power(2, least(g.locks, 10))" in gate_fn)
check("11. no raise in login_gate", gate_fn and not re.search(r"\braise\b", gate_fn, re.I))
check("11. gate: execute revoked from public, granted to anon and authenticated",
      "revoke execute on function public.login_gate(text, text) from public;" in code_sql
      and "grant execute on function public.login_gate(text, text) to anon, authenticated;" in code_sql)
check("11. arm: revoked from public and anon, granted to authenticated only",
      "revoke execute on function public.arm_login_gate(text) from public, anon;" in code_sql
      and "grant execute on function public.arm_login_gate(text) to authenticated;" in code_sql
      and not re.search(r"grant execute on function public\.arm_login_gate\(text\) to [^;]*anon", code_sql))
check("11. the table: row level security on, revoked from anon and authenticated",
      "alter table private.login_gate enable row level security;" in code_sql
      and "revoke all on private.login_gate from public, anon, authenticated;" in code_sql and "create policy" not in code_sql)
foot = sql.split("by hand only", 1)[-1]
check("11. the foot: unlock, undo one, undo all, all commented out",
      all(l.startswith("--") or not l.strip() for l in foot.splitlines()[1:]) and "set fails = 0, locks = 0, locked_until = null where username = 'someone'" in foot
      and "returning user_id, code_hash" in foot and "drop table if exists private.login_gate" in foot)

# ------------------------------------------------------------ tools/arm_gate.py with every web call replaced
group[0] = "E. arm_gate"
sys.path.insert(0, str(ROOT / "tools"))
import drop_pdf as D
import arm_gate as A
REAL_CALL = D.call
class Fake:
    def __init__(self, armed=False, gate=None, race=False, refuse_secret=False):
        self.armed, self.gate, self.race, self.refuse_secret, self.log = armed, gate, race, refuse_secret, []
    def __call__(self, method, path, token=None, body=None, raw=None, headers=None):
        self.log.append((path, body))
        if path == "/rest/v1/rpc/login_gate":
            if self.gate: return self.gate
            if not self.armed: return 200, {"status": "none"}
            return (200, {"status": "ok", "secret": SECRET}) if body.get("p_code") == CODE else (200, {"status": "wrong", "left": 4})
        if path == "/auth/v1/token?grant_type=password":
            good = SECRET if self.armed else CODE
            if body.get("password") == good and not (self.refuse_secret and good == SECRET):
                return 200, {"access_token": "tok", "user": {"id": "u1"}}
            return 400, {"msg": "Invalid login credentials"}
        if path == "/rest/v1/rpc/arm_login_gate":
            if token != "tok": return 401, {"message": "no"}
            if self.race:
                self.armed = True; return 200, {"status": "armed_already"}
            if self.armed: return 200, {"status": "armed_already"}
            self.armed = True; return 200, {"status": "armed", "secret": SECRET}
        raise AssertionError("unplanned call " + path)
    def paths(self): return [p for p, _ in self.log]

ENV0 = (b"# PenWorks laptop login (made-up values for the test)\n"
        b"PW_USER=gatetest\n"
        b"PW_PASS=13579\n"
        b"PW_TEST_USER=throwaway\n"
        b"PW_TEST_PASS=86420\n"
        b"OTHER = keep me = exactly\n")
ARMED = (b"# PenWorks laptop login (made-up values for the test)\n"
         b"PW_USER=gatetest\n"
         b"PW_PASS=" + SECRET.encode() + b"\n"
         b"PW_CODE=13579\n"
         b"PW_TEST_USER=throwaway\n"
         b"PW_TEST_PASS=86420\n"
         b"OTHER = keep me = exactly\n")
tmpd = pathlib.Path(tempfile.mkdtemp(prefix="pw-gate-"))
def run(fake, env_bytes, *extra):
    p = tmpd / ".env"; p.write_bytes(env_bytes)
    D.call = fake; out = []
    try: rc = A.main(["--env", str(p), *extra], say=out.append)
    finally: D.call = REAL_CALL
    text = "\n".join(out)
    return rc, p.read_bytes(), text
def clean(text): return CODE not in text and SECRET not in text

f = Fake()
rc, after, out = run(f, ENV0)
check("12. none then armed: PASS = the secret, CODE right under it, every other line byte-identical", rc == 0 and after == ARMED, [rc, after, out])
check("12. armed: the one printed line names the lock, neither value in it", out.startswith("Armed the login lock for gatetest.") and "\n" not in out and clean(out), out)
check("12. armed: gate, old sign-in, arm, the secret proved", f.paths() == ["/rest/v1/rpc/login_gate", "/auth/v1/token?grant_type=password", "/rest/v1/rpc/arm_login_gate", "/auth/v1/token?grant_type=password"], f.paths())
check("12. no temp file left beside the env file", sorted(x.name for x in tmpd.iterdir()) == [".env"], sorted(x.name for x in tmpd.iterdir()))
f2 = Fake(armed=True)
rc, after2, out = run(f2, ARMED)
check("12. a second run changes nothing and says so", rc == 0 and after2 == ARMED and out.startswith("Already armed for gatetest.") and "already matches" in out and clean(out), [rc, out])
check("12. a second run never calls arm_login_gate", "/rest/v1/rpc/arm_login_gate" not in f2.paths(), f2.paths())
f3 = Fake(race=True)
rc, after3, out = run(f3, ENV0)
check("12. armed_already (a race) recovers through the gate", rc == 0 and after3 == ARMED and f3.paths().count("/rest/v1/rpc/login_gate") == 2 and clean(out), [rc, f3.paths(), out])
crlf = b"\xef\xbb\xbf" + ENV0.replace(b"\n", b"\r\n")
rc, after4, out = run(Fake(), crlf)
check("12. a file with a BOM and CRLF lines keeps both", rc == 0 and after4 == b"\xef\xbb\xbf" + ARMED.replace(b"\n", b"\r\n"), after4)
for label, fake in [("404 (no migration yet)", Fake(gate=(404, MISSING))),
                    ("wrong", Fake(gate=(200, {"status": "wrong", "left": 2}))),
                    ("locked", Fake(gate=(200, {"status": "locked", "until": until.isoformat()}))),
                    ("a failed secret sign-in", Fake(armed=True, refuse_secret=True))]:
    rc, a_, out = run(fake, ENV0)
    check(f"12. {label}: exit 1, the file byte-identical, neither value printed", rc == 1 and a_ == ENV0 and clean(out), [rc, out])
rc, a_, out = run(Fake(gate=(404, MISSING)), ENV0)
check("12. 404: the brief's line", out == "The lock is not in the database yet (migration 0008). Nothing changed.", out)
f5 = Fake(armed=True)
rc, a_, out = run(f5, ARMED, "--check")
check("12. --check makes NO login_gate call and changes nothing", "/rest/v1/rpc/login_gate" not in f5.paths() and a_ == ARMED and rc == 0 and clean(out), [f5.paths(), out])
f6 = Fake()
rc, a_, out = run(f6, ENV0, "--check")
check("12. --check before arming: says PW_CODE is not in the file, no gate call", "/rest/v1/rpc/login_gate" not in f6.paths() and "PW_CODE is NOT in" in out and a_ == ENV0 and rc == 1, [f6.paths(), out])
for x in tmpd.iterdir(): x.unlink()
tmpd.rmdir()

# ------------------------------------------------------------ sw.js and the files
group[0] = "F. files"
swt = (ROOT / "sw.js").read_text(encoding="utf-8")
check("13. sw.js: CACHE pw-v9h and its version line", 'const CACHE = "pw-v9h";' in swt and "   pw-v9h (13 Nov): " in swt)
check("sw.js has no BOM", not (ROOT / "sw.js").read_bytes().startswith(b"\xef\xbb\xbf"))
touched = ["js/api.js", "sw.js", "supabase/migrations/0008_login_gate.sql", "tools/arm_gate.py", "tools/README-gate.md", "tests/test_gate.py"]
check("no em-dashes in the files this round touched", all(chr(0x2014) not in (ROOT / f_).read_text(encoding="utf-8") for f_ in touched))

groups = []
for g_, n, ok, info in res:
    if g_ not in groups: groups.append(g_)
    if not ok: print(f"FAIL [{g_}] {n}  -> {str(info)[:700]}")
print()
for g_ in groups:
    rs_ = [r for r in res if r[0] == g_]
    print(f"{g_}: {sum(r[2] for r in rs_)}/{len(rs_)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
