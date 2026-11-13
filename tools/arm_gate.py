# PenWorks login lock (pw-v9h, migration 0008): arm the lock for one person if it is not armed yet, then make the env
# file match. Safe to run twice: the second run finds the lock armed and the file already right, and changes nothing.
#
#   python tools/arm_gate.py                 (megan: PW_USER, PW_PASS, PW_CODE in penworks\.env)
#   python tools/arm_gate.py --test          (the throwaway login: PW_TEST_USER, PW_TEST_PASS, PW_TEST_CODE)
#   python tools/arm_gate.py --check         (changes nothing, never asks the lock with the code: a check costs no try)
#   python tools/arm_gate.py --env <path>    (another env file; the tests use a temp one)
#
# After arming, PASS = the long secret (the real Supabase password, the laptop tools sign in with it and never meet the
# lock) and CODE = the short code (what she types in the app). Every other line of the file stays byte for byte.
# It never prints the code or the secret, not in errors either. Exit codes: 0 done, 1 refused or network trouble,
# 2 bad arguments (no env file, no login in it).
# Standard library only; the web calls go through tools/drop_pdf.py's call and sign_in (a test swaps drop_pdf.call).
import sys, os, pathlib, argparse, tempfile
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drop_pdf as D
from drop_pdf import Stop

ENV = D.ENV
BOM = b"\xef\xbb\xbf"

# ---------------------------------------------------------------- the env file (the FILE only, never os.environ)
def read_env(path):
    kv = {}
    raw = pathlib.Path(path).read_bytes()
    text = raw[len(BOM):].decode("utf-8") if raw.startswith(BOM) else raw.decode("utf-8")
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1); kv[k.strip()] = v.strip()
    return raw, kv

def key_of(line):
    if "=" not in line or line.lstrip().startswith("#"): return None
    return line.split("=", 1)[0].strip()

def matched(raw, kp, kc, secret, code):
    # the file's bytes with PASS = secret and CODE = code; every other line exactly as it was, in the same order
    bom = BOM if raw.startswith(BOM) else b""
    text = raw[len(bom):].decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    def put(line, value):
        body = line.rstrip("\r\n"); end = line[len(body):]
        return body.split("=", 1)[0] + "=" + value + end
    has_code = any(key_of(l) == kc for l in lines)
    out, placed = [], False
    for line in lines:
        k = key_of(line)
        if k == kp:
            if not line.endswith(("\n", "\r")) and not has_code: line += nl
            out.append(put(line, secret))
            if not has_code and not placed:
                out.append(f"{kc}={code}" + nl); placed = True
        elif k == kc:
            out.append(put(line, code))
        else:
            out.append(line)
    if not any(key_of(l) == kp for l in lines):          # no PASS line at all: both go at the end
        if out and not out[-1].endswith(("\n", "\r")): out[-1] += nl
        out.append(f"{kp}={secret}" + nl)
        if not has_code: out.append(f"{kc}={code}" + nl)
    return bom + "".join(out).encode("utf-8")

def write_beside(path, data):
    # a temp file in the same folder, then one os.replace: the env file is never half written. No backup copy.
    p = pathlib.Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".env-", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
    except Exception:
        try: os.remove(tmp)
        except OSError: pass
        raise

# ---------------------------------------------------------------- the lock
def ask_gate(user, code):
    st, info = D.call("POST", "/rest/v1/rpc/login_gate", body={"p_username": user.strip().lower(), "p_code": code})
    if st == 404:
        raise Stop(1, "The lock is not in the database yet (migration 0008). Nothing changed.")
    if st != 200 or not isinstance(info, dict):
        raise Stop(1, f"The lock did not answer properly (HTTP {st}). Nothing changed.")
    return info

def clock(until):
    try:
        u = datetime.fromisoformat(str(until).replace("Z", "+00:00")).astimezone()
        return u.strftime("%H:%M") if u.date() == datetime.now().astimezone().date() else "tomorrow at " + u.strftime("%H:%M")
    except Exception:
        return "later"

def refused(user, a):
    s = a.get("status")
    if s == "wrong":
        return Stop(1, f"The lock says the code in the env file is not right for {user}. Nothing changed.")
    if s == "locked":
        t = clock(a.get("until"))
        return Stop(1, f"The lock is locked for {user} (too many wrong tries), try again {t if t.startswith('tomorrow') or t == 'later' else 'at ' + t}. Nothing changed.")
    return Stop(1, f"The lock gave an answer this tool does not know ({s!r}). Nothing changed.")

def get_secret(user, code):
    # returns (secret, armed_now)
    a = ask_gate(user, code)
    s = a.get("status")
    if s == "ok" and a.get("secret"):
        return a["secret"], False
    if s != "none":
        raise refused(user, a)
    token, _ = D.sign_in(user, code)                     # not armed yet: the code is still the real password
    st, info = D.call("POST", "/rest/v1/rpc/arm_login_gate", token=token, body={"p_code": code})
    if st == 404:
        raise Stop(1, "The lock is not in the database yet (migration 0008). Nothing changed.")
    r = info.get("status") if isinstance(info, dict) else None
    if st == 200 and r == "armed" and info.get("secret"):
        return info["secret"], True
    if st == 200 and r == "armed_already":               # armed by someone else in between: the gate has the secret
        a = ask_gate(user, code)
        if a.get("status") == "ok" and a.get("secret"):
            return a["secret"], False
        raise refused(user, a)
    raise Stop(1, f"Could not arm the lock for {user} ({r or 'HTTP ' + str(st)}). Nothing changed.")

# ---------------------------------------------------------------- the two jobs
def check(path, test, say):
    raw, kv = read_env(path)
    ku, kp, kc = keys(test)
    user, pwd = kv.get(ku, ""), kv.get(kp, "")
    if not user or not pwd:
        raise Stop(2, f"No login found: {ku} and {kp} are not in {path}.")
    has_code = bool(kv.get(kc))
    try:
        D.sign_in(user, pwd); direct = True
    except Stop as e:
        if "refused" not in e.msg: raise
        direct = False
    say(f"Check for {user}: {kc} is {'in' if has_code else 'NOT in'} the env file; "
        f"{kp} {'signs in directly' if direct else 'does NOT sign in directly'}. Nothing changed.")
    return 0 if (has_code and direct) else 1

def arm(path, test, say):
    raw, kv = read_env(path)
    ku, kp, kc = keys(test)
    user = kv.get(ku, "")
    code = kv.get(kc) or kv.get(kp, "")
    if not user or not code:
        raise Stop(2, f"No login found: {ku} and {kp} (or {kc}) are not in {path}.")
    secret, armed_now = get_secret(user, code)
    try:
        D.sign_in(user, secret)                          # prove the secret BEFORE the file is touched
    except Stop:
        raise Stop(1, f"The lock's secret did not sign in for {user}. The env file was not changed; run this again, "
                      "or ask Claude to check the lock.")
    new = matched(raw, kp, kc, secret, code)
    name = pathlib.Path(path).name
    if new == raw:
        say(f"Already armed for {user}. {name} already matches, nothing changed.")
        return 0
    write_beside(path, new)
    head = f"Armed the login lock for {user}." if armed_now else f"Already armed for {user}."
    say(f"{head} {name} now holds the long secret ({kp}) and the short code ({kc}).")
    return 0

def keys(test):
    return ("PW_TEST_USER", "PW_TEST_PASS", "PW_TEST_CODE") if test else ("PW_USER", "PW_PASS", "PW_CODE")

def main(argv=None, say=print):
    ap = argparse.ArgumentParser(description="Arm the PenWorks login lock if needed, then make the env file match.")
    ap.add_argument("--test", action="store_true", help="the throwaway login (PW_TEST_USER, PW_TEST_PASS, PW_TEST_CODE)")
    ap.add_argument("--check", action="store_true", help="change nothing, make no lock call with the code")
    ap.add_argument("--env", default=str(ENV), help="the env file (default penworks\\.env)")
    a = ap.parse_args(argv)
    if not pathlib.Path(a.env).is_file():
        say(f"There is no env file at {a.env}."); return 2
    try:
        return check(a.env, a.test, say) if a.check else arm(a.env, a.test, say)
    except Stop as e:
        say(e.msg); return e.code

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
