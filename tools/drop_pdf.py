# PenWorks drop: put a PDF from this laptop into PenWorks as a new note, the same rows the app's own PDF button makes
# (js/pdfin.js doImport, js/app.js makePdfNote + addPdfPages). Her tablet and phone show it within seconds (the app's
# Realtime channel refreshes the tree, the pages draw once the app has fetched the PDF from storage).
#
#   python tools/drop_pdf.py "C:\Users\megzi\Desktop\Some sheet.pdf"
#   python tools/drop_pdf.py "C:\...\x.pdf" --folder "Grade 12"
#   python tools/drop_pdf.py "C:\...\x.pdf" --folder "Grade 9/Term 1" --name "Michaela G1 to G8"
#   python tools/drop_pdf.py "C:\...\x.pdf" --test        (the throwaway login droptest, for tests)
#
# The login comes from penworks\.env (gitignored): PW_USER / PW_PASS, or PW_TEST_USER / PW_TEST_PASS with --test.
# Writes, in the app's order: 1) the PDF into the `imports` bucket at <user id>/<uuid>.pdf, 2) the note row, 3) one page
# row per PDF page. A failed step undoes the earlier ones (the note goes to the Bin, the stored PDF is removed).
# Exit codes: 0 done, 1 sign-in or network trouble, 2 bad arguments (no such file, not a PDF, too big, unknown folder).
# Standard library plus PyMuPDF only.
import sys, os, json, uuid, argparse, pathlib, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
SB_URL = "https://duibtdcxmnvsuczuceld.supabase.co"          # js/api.js
SB_KEY = "sb_publishable_bj2rpL9bwuYSrWCnZxkAuA_uIHYRVJR"     # the publishable key, safe in the app (js/api.js)
EMAIL_DOMAIN = "@penworks.app"
IMPORT_BUCKET = "imports"
MAX_BYTES = 52428800                                           # 50 MB, the bucket's limit (MAX_BYTES in js/pdfin.js)
TIMEOUT = 120

class Stop(Exception):
    def __init__(self, code, msg):
        super().__init__(msg); self.code = code; self.msg = msg

# ---------------------------------------------------------------- names, as js/pdfin.js nameOf does
# JavaScript's String.prototype.trim() strips exactly these characters (Python's strip() knows a slightly different set)
JS_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
def js_slice(s, n):
    # .slice(0, n) counts UTF-16 units, as JavaScript does; half of a split emoji is dropped (it cannot be stored)
    u = s.encode("utf-16-le")
    if len(u) <= 2 * n: return s
    u = u[:2 * n]
    if 0xD8 <= u[-1] <= 0xDB: u = u[:-2]
    return u.decode("utf-16-le")
def name_of(filename):
    import re
    return js_slice(re.sub(r"\.pdf$", "", str(filename or ""), flags=re.I).strip(JS_SPACE), 120) or "Untitled"
def clean_name(given):
    return js_slice(str(given or "").strip(JS_SPACE), 120) or "Untitled"

# ---------------------------------------------------------------- the login
def login(test):
    kv = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1); kv[k.strip()] = v.strip()
    ku, kp = ("PW_TEST_USER", "PW_TEST_PASS") if test else ("PW_USER", "PW_PASS")
    u, p = os.environ.get(ku) or kv.get(ku, ""), os.environ.get(kp) or kv.get(kp, "")
    if not u or not p:
        raise Stop(1, f"No login found: {ku} and {kp} are not in {ENV}.")
    return u, p

# ---------------------------------------------------------------- the web calls
def call(method, path, token=None, body=None, raw=None, headers=None):
    h = {"apikey": SB_KEY}
    if token: h["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8"); h["Content-Type"] = "application/json"
    elif raw is not None:
        data = raw
    h.update(headers or {})
    req = urllib.request.Request(SB_URL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            text = r.read()
            return r.status, (json.loads(text) if text and "json" in (r.headers.get("Content-Type") or "") else text)
    except urllib.error.HTTPError as e:
        text = e.read()
        try: info = json.loads(text)
        except Exception: info = text.decode("utf-8", "replace")
        return e.code, info
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Stop(1, f"Could not reach PenWorks (is the internet on?): {getattr(e, 'reason', e)}")

def why(info):
    if isinstance(info, dict):
        return info.get("message") or info.get("msg") or info.get("error_description") or info.get("error") or json.dumps(info)
    return str(info)[:300]

def sign_in(user, pwd):
    st, info = call("POST", "/auth/v1/token?grant_type=password", body={"email": user + EMAIL_DOMAIN, "password": pwd})
    if st != 200 or not isinstance(info, dict) or not info.get("access_token"):
        if st in (400, 401):
            raise Stop(1, f"Could not sign in as {user}: the username or password was refused.")
        raise Stop(1, f"Could not sign in as {user}: {why(info)}")
    return info["access_token"], info["user"]["id"]

# ---------------------------------------------------------------- folders
def folder_lines(folders):
    tops = sorted([f for f in folders if not f["parent_id"]], key=lambda f: (f.get("position") or 0, f["name"].casefold()))
    out = []
    for t in tops:
        out.append(t["name"])
        kids = sorted([f for f in folders if f["parent_id"] == t["id"]], key=lambda f: (f.get("position") or 0, f["name"].casefold()))
        out += [t["name"] + "/" + k["name"] for k in kids]
    return out

def find_folder(folders, wanted):
    # a top folder by name, or Parent/Child for a second-level one; case does not matter, spaces at the ends do not count.
    # Returns (folder id or None for Loose, the label to print), or None when nothing matches.
    key = lambda s: s.strip(JS_SPACE).casefold()
    live = {f["id"]: f for f in folders}
    tops = sorted([f for f in folders if not f["parent_id"]], key=lambda f: f.get("position") or 0)
    hit = [f for f in tops if key(f["name"]) == key(wanted)]
    if hit: return hit[0]["id"], hit[0]["name"]
    for i, ch in enumerate(wanted):                    # every "/" could be the one between parent and child
        if ch != "/": continue
        a, b = wanted[:i], wanted[i + 1:]
        for t in [f for f in tops if key(f["name"]) == key(a)]:
            kids = sorted([f for f in folders if f["parent_id"] == t["id"] and f["parent_id"] in live], key=lambda f: f.get("position") or 0)
            hit = [k for k in kids if key(k["name"]) == key(b)]
            if hit: return hit[0]["id"], t["name"] + "/" + hit[0]["name"]
    if key(wanted) == "loose": return None, "Loose"
    return None

# ---------------------------------------------------------------- the drop
def drop(pdf, folder=None, name=None, test=False, say=print):
    p = pathlib.Path(pdf)
    if not p.is_file():
        raise Stop(2, f"There is no file at {pdf}.")
    size = p.stat().st_size
    if size > MAX_BYTES:
        raise Stop(2, f"This PDF is too big to drop (over 50 MB): it is {size / 1048576:.1f} MB.")
    import fitz
    try:
        doc = fitz.open(str(p))
    except Exception:
        raise Stop(2, f"This PDF could not be opened: {p.name}")
    try:
        if doc.needs_pass:
            raise Stop(2, f"This PDF has a password, so PenWorks cannot open it: {p.name}")
        if not doc.is_pdf or doc.page_count < 1:
            raise Stop(2, f"This PDF could not be opened: {p.name}")
        # the page size after its own rotation, as pdf.js getViewport({ scale: 1 }) reads it, rounded to 2 decimals
        sizes = [(round(pg.rect.width, 2), round(pg.rect.height, 2)) for pg in doc]
    finally:
        doc.close()
    data = p.read_bytes()
    note_name = clean_name(name) if name is not None else name_of(p.name)

    token, uid = sign_in(*login(test))
    fid, where = None, "Loose"
    if folder is not None and folder.strip(JS_SPACE):
        st, rows = call("GET", "/rest/v1/folders?select=id,name,parent_id,position&deleted_at=is.null", token)
        if st != 200: raise Stop(1, f"Could not read the folders: {why(rows)}")
        got = find_folder(rows, folder)
        if got is None:
            lines = folder_lines(rows)
            raise Stop(2, f'There is no folder called "{folder.strip()}". Nothing was dropped. The folders are:\n'
                          + ("\n".join("  " + l for l in lines) if lines else "  (no folders yet)")
                          + "\nLeave out --folder to drop it into Loose.")
        fid, where = got

    # 1) the PDF into storage
    path = f"{uid}/{uuid.uuid4()}.pdf"                 # stored on the page rows with NO bucket in front (as doImport)
    st, info = call("POST", f"/storage/v1/object/{IMPORT_BUCKET}/{path}", token, raw=data,
                    headers={"Content-Type": "application/pdf", "x-upsert": "true", "cache-control": "3600"})
    if st not in (200, 201): raise Stop(1, f"The PDF did not upload: {why(info)}")
    def unstore():
        call("DELETE", f"/storage/v1/object/{IMPORT_BUCKET}/{path}", token)

    # 2) the note row (owner_id is filled in by the database)
    nid = str(uuid.uuid4())
    try:
        st, info = call("POST", "/rest/v1/notes", token, body={"id": nid, "folder_id": fid, "name": note_name, "pinned": False},
                        headers={"Prefer": "return=representation"})
    except Stop:
        unstore(); raise
    if st not in (200, 201) or not info:
        unstore(); raise Stop(1, f"The note was not made: {why(info)}")

    # 3) one page row per PDF page, in order, in one go
    rows = [{"id": str(uuid.uuid4()), "note_id": nid, "position": k, "orientation": "landscape" if w > h else "portrait",
             "background": "blank", "bookmark": False, "pdf_path": path, "pdf_page": k + 1, "pdf_w": w, "pdf_h": h}
            for k, (w, h) in enumerate(sizes)]
    err = None
    try:
        st, info = call("POST", "/rest/v1/pages", token, body=rows, headers={"Prefer": "return=representation"})
        if st not in (200, 201) or not isinstance(info, list) or len(info) != len(rows): err = why(info)
    except Stop as e:
        err = e.msg
    if err is not None:
        try:
            call("PATCH", f"/rest/v1/notes?id=eq.{nid}", token, body={"deleted_at": datetime.now(timezone.utc).isoformat()})
            unstore()
        except Stop:
            pass
        raise Stop(1, f"The pages were not made, so the note went to the Bin: {err}")

    n = len(rows)
    say(f'Dropped "{note_name}" ({n} page{"" if n == 1 else "s"}) into {where} as note {nid}')
    return {"note_id": nid, "path": path, "pages": n, "folder_id": fid, "name": note_name, "user_id": uid}

def main(argv=None):
    for s in (sys.stdout, sys.stderr):                 # Afrikaans and other letters print whole, also into a pipe
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass
    ap = argparse.ArgumentParser(description="Put a PDF from this laptop into PenWorks as a new note.")
    ap.add_argument("pdf", help="the PDF file")
    ap.add_argument("--folder", help='a top folder ("Grade 12") or a sub-folder ("Grade 9/Term 1"); leave out for Loose')
    ap.add_argument("--name", help="the note's name (default: the file's name without .pdf)")
    ap.add_argument("--test", action="store_true", help="use the throwaway test login (PW_TEST_USER / PW_TEST_PASS)")
    a = ap.parse_args(argv)
    try:
        drop(a.pdf, a.folder, a.name, a.test)
        return 0
    except Stop as e:
        print(e.msg, file=sys.stderr if e.code else sys.stdout)
        return e.code

if __name__ == "__main__":
    sys.exit(main())
