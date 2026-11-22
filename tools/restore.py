# PenWorks restore: bring ONE note back from the nightly backup (penworks\backup\) as a NEW note, "<name> (restored)".
#
#   python -E -P tools\restore.py --list "algebra"                  offline: archived notes whose name has these words
#   python -E -P tools\restore.py "algebra"                         DRY RUN: says what it would make, changes nothing
#   python -E -P tools\restore.py "<note id>" --stamp 20261121T180012Z --folder "Grade 9/Term 1" --go
#
# Only --go writes, and then ONLY new rows (one note, its pages, every stroke, all with new ids) and new files. It never
# updates, deletes or overwrites anything: guarded() below refuses every other request, and it stops before writing if a
# new id somehow already exists. The archive in backup\ is only read.
# Folder: the note's own folder if it is still live, else --folder, else it refuses. Pages the note had in its Bin stay
# out unless --with-bin. A sticky comes only with its anchor page (the anchor rule). PDF pages and pictures reuse the
# stored file if it is still there, else the copy in backup\files\imports goes up as a new file.
# Login: penworks\.env (PW_USER / PW_PASS), or --env <file>. The password is never printed.
# Exit codes: 0 done (or a dry run), 1 sign-in or network trouble (or stopped part way), 2 refused (nothing written),
# 3 a new id already exists, or the read-back after --go did not match.
# Standard library only, plus drop_pdf.py next to this file for the sign-in.
import sys, json, gzip, uuid, argparse, pathlib, urllib.request, urllib.error, urllib.parse
from datetime import datetime

# -P keeps the script's own folder off the import path, so add it on purpose for drop_pdf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drop_pdf

ROOT = drop_pdf.ROOT
OUT = ROOT / "backup"
Stop = drop_pdf.Stop
SUFFIX = " (restored)"
IDS_PER_REQ = 100
PAGE = 1000
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

# ---------------------------------------------------------------- the insert-only guard
def guarded(method, path, headers=None):
    # the one place that decides what may go upstream; a raise, not an assert, so python -O cannot switch it off
    p = path.split("?")[0]
    if method in ("GET", "HEAD"): return
    if method == "POST":
        if path == "/auth/v1/token?grant_type=password" or p.startswith("/storage/v1/object/list/"): return
        prefer = (headers or {}).get("Prefer", "")
        if p in ("/rest/v1/notes", "/rest/v1/pages", "/rest/v1/strokes") and "on_conflict" not in path and "resolution" not in prefer:
            return                                     # a plain insert: a clash is refused by the database, never merged
        if p.startswith("/storage/v1/object/imports/") and (headers or {}).get("x-upsert") == "false":
            return                                     # a new file; storage refuses it if the name is taken
    raise RuntimeError(f"restore.py refused to send {method} {p}: it only ever adds new rows and files")

_drop_call = drop_pdf.call
def _guarded_call(method, path, *a, **k):
    guarded(method, path, k.get("headers"))
    return _drop_call(method, path, *a, **k)
drop_pdf.call = _guarded_call                          # sign_in() goes through this too

def web(method, path, token, body=None, raw=None, headers=None):
    """Returns (status, response headers, parsed body). Never retries a write."""
    h = {"apikey": drop_pdf.SB_KEY, "Authorization": "Bearer " + token}
    h.update(headers or {})
    guarded(method, path, h)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8"); h["Content-Type"] = "application/json"
    elif raw is not None:
        data = raw
    req = urllib.request.Request(drop_pdf.SB_URL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=drop_pdf.TIMEOUT) as r:
            text = r.read()
            try: info = json.loads(text) if text else None
            except ValueError: info = text
            return r.status, r.headers, info
    except urllib.error.HTTPError as e:
        text = e.read()
        try: info = json.loads(text)
        except Exception: info = text.decode("utf-8", "replace")
        return e.code, e.headers, info
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Stop(1, f"Could not reach PenWorks (is the internet on?): {getattr(e, 'reason', e)}")

def get(token, path):
    st, _, info = web("GET", path, token)
    if st != 200: raise Stop(1, f"Could not read from PenWorks ({path.split('?')[0]}): {drop_pdf.why(info)}")
    return info

def count(token, table, filt):
    st, hd, info = web("GET", f"/rest/v1/{table}?select=id&limit=1&{filt}", token, headers={"Prefer": "count=exact"})
    if st not in (200, 206): raise Stop(1, f"Could not count {table}: {drop_pdf.why(info)}")
    return int((hd.get("Content-Range") or "*/0").split("/")[-1])

# ---------------------------------------------------------------- the login
def login_from(path):
    f = pathlib.Path(path)
    if not f.is_file(): raise Stop(2, f"There is no login file at {f}.")
    kv = {}
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1); kv[k.strip()] = v.strip()
    if not kv.get("PW_USER") or not kv.get("PW_PASS"):
        raise Stop(2, f"No login found: PW_USER and PW_PASS are not both in {f}.")
    return kv["PW_USER"], kv["PW_PASS"]

# ---------------------------------------------------------------- the archive (read only)
def read_gz(path):
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))

def stamps(nid):
    return sorted(f.name[:-8] for f in (OUT / "notes" / nid).glob("*.json.gz") if f.name[:-8].endswith("Z"))

def nice(stamp):
    try: return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%d %H:%M UTC")
    except ValueError: return stamp

def folder_paths(folders):
    by = {f["id"]: f for f in folders}
    def path(fid, depth=0):
        f = by.get(fid)
        if not f or depth > 10: return ""
        up = path(f.get("parent_id"), depth + 1)
        return (up + "/" if up else "") + f["name"]
    return {fid: path(fid) for fid in by}

def archive():
    """Every archived note: id -> (name, folder, state, newest stamp, newest version)."""
    if not (OUT / "notes").is_dir(): raise Stop(2, f"There is no backup at {OUT}.")
    trees = sorted((OUT / "tree").glob("*.json.gz"))
    tree = read_gz(trees[-1]) if trees else {"notes": [], "folders": []}
    tnotes = {n["id"]: n for n in tree["notes"]}
    fpath = folder_paths(tree["folders"])
    try: last_seen = json.loads((OUT / "state.json").read_text(encoding="utf-8")).get("last_seen", {})
    except (OSError, ValueError): last_seen = {}
    got = {}
    for d in sorted((OUT / "notes").glob("*")):
        st = stamps(d.name)
        if not st: continue
        v = read_gz(d / f"{st[-1]}.json.gz")
        n = tnotes.get(d.name, v["note"])
        if d.name not in tnotes: state = f"gone from PenWorks, last seen {(last_seen.get(d.name) or v.get('saved_at', ''))[:10]}"
        elif n.get("deleted_at"): state = f"in the Bin since {n['deleted_at'][:10]}"
        else: state = "live"
        folder = fpath.get(n.get("folder_id"), v.get("folder_path", "")) if d.name in tnotes else v.get("folder_path", "")
        got[d.name] = {"name": n.get("name") or "Untitled", "folder": folder or "Loose", "state": state, "stamps": st}
    return got

def matches(notes, words):
    w = words.strip().casefold()
    if w in notes: return [w]
    return [k for k, n in notes.items() if w in n["name"].casefold()]

def list_notes(words):
    notes = archive()
    hits = matches(notes, words)
    if not hits:
        print(f'No archived note name contains "{words}".'); return 0
    for k in sorted(hits, key=lambda k: notes[k]["name"].casefold()):
        n = notes[k]
        print(f"{n['name']}  |  {n['folder']}  |  {n['state']}  |  newest backup {nice(n['stamps'][-1])}  |  {k}")
        for s in n["stamps"]:
            v = read_gz(OUT / "notes" / k / f"{s}.json.gz")
            print(f"    {s}  {len(v['pages'])} pages, {len(v['strokes'])} strokes")
    return 0

def pick(words):
    notes = archive()
    hits = matches(notes, words)
    if not hits: raise Stop(2, f'No archived note matches "{words}". Try --list with fewer words.')
    if len(hits) > 1:
        exact = [k for k in hits if notes[k]["name"].casefold() == words.strip().casefold()]
        if len(exact) != 1:
            lines = [f"  {notes[k]['name']}  |  {notes[k]['folder']}  |  {notes[k]['state']}  |  {k}" for k in sorted(hits, key=lambda k: notes[k]["name"].casefold())]
            raise Stop(2, f'{len(hits)} archived notes match "{words}". Nothing was restored. Give the note id instead:\n' + "\n".join(lines))
        hits = exact
    return hits[0], notes[hits[0]]

# ---------------------------------------------------------------- the plan (offline)
def when(s):
    try: return datetime.fromisoformat(s)
    except (TypeError, ValueError): return None

def plan(version, with_bin):
    note, pages = version["note"], version["pages"]
    binned_with_note = when(note.get("deleted_at"))
    def keep(p):
        if with_bin or not p.get("deleted_at"): return True
        # a note put in the Bin takes its live pages with it, all with the note's own time (js/app.js binThing)
        return binned_with_note is not None and when(p["deleted_at"]) == binned_with_note
    plain = sorted((p for p in pages if (p.get("kind") or "page") != "sticky" and keep(p)), key=lambda p: (p.get("position") or 0, p["id"]))
    ids = {p["id"]: str(uuid.uuid4()) for p in plain}
    pos = {p["id"]: i for i, p in enumerate(plain)}
    # THE ANCHOR RULE: a sticky goes with its anchor page, or not at all
    stickies = [p for p in pages if p.get("kind") == "sticky" and keep(p) and p.get("anchor_id") in ids]
    for s in stickies: ids[s["id"]] = str(uuid.uuid4())
    left_out = len(pages) - len(plain) - len(stickies)
    copy_cols = ("orientation", "background", "bookmark", "pdf_path", "pdf_page", "pdf_w", "pdf_h", "pdf_rot",
                 "transcript", "flagged", "flag_note", "sk_x", "sk_y", "sk_w", "sk_colour")
    def row(p, kind):
        r = {k: p.get(k) for k in copy_cols if k in p}
        r.update(id=ids[p["id"]], kind=kind, deleted_at=None, snapshot_path=None, snapshot_at=None)
        if kind == "sticky":
            r.update(anchor_id=ids[p["anchor_id"]], position=pos[p["anchor_id"]], pdf_path=None, pdf_page=None)
        else:
            r.update(anchor_id=None, position=pos[p["id"]])
        return r
    page_rows = [row(p, "page") for p in plain]
    sticky_rows = [row(s, "sticky") for s in stickies]
    strokes = [s for s in version["strokes"] if s["page_id"] in ids]
    order = {p["id"]: i for i, p in enumerate(plain + stickies)}
    strokes.sort(key=lambda s: (order[s["page_id"]], s.get("seq") or 0, s["id"]))
    stroke_rows = [{"id": str(uuid.uuid4()), "page_id": ids[s["page_id"]], "seq": s["seq"], "kind": s["kind"],
                    "style": s.get("style") if s.get("style") is not None else {}, "data": s["data"]} for s in strokes]
    files = sorted({r["pdf_path"] for r in page_rows if r.get("pdf_path")} |
                   {s["data"]["path"] for s in stroke_rows if s["kind"] == "image" and isinstance(s["data"], dict) and s["data"].get("path")})
    return {"note": note, "pages": page_rows, "stickies": sticky_rows, "strokes": stroke_rows, "files": files,
            "left_out": left_out, "pdf_pages": sum(1 for r in page_rows if r.get("pdf_path"))}

def new_name(old):
    base = drop_pdf.clean_name(old)
    return drop_pdf.js_slice(base, 120 - len(SUFFIX)).rstrip(drop_pdf.JS_SPACE) + SUFFIX

# ---------------------------------------------------------------- PenWorks (read, then insert only)
def live_folders(token):
    rows = get(token, "/rest/v1/folders?select=id,name,parent_id,position,deleted_at&limit=1000")
    by = {f["id"]: f for f in rows}
    def live(f, depth=0):
        return bool(f) and not f.get("deleted_at") and depth < 10 and (not f.get("parent_id") or live(by.get(f["parent_id"]), depth + 1))
    return [f for f in rows if live(f)]

def choose_folder(token, note, old_folder, wanted):
    folders = live_folders(token)
    paths = folder_paths(folders)
    fid = note.get("folder_id")
    if not fid:
        return None, "Loose (its own place)"
    if fid in paths:
        return fid, f"{paths[fid]} (its own folder)"
    if wanted is not None and wanted.strip(drop_pdf.JS_SPACE):
        got = drop_pdf.find_folder(folders, wanted)
        if got is None:
            lines = drop_pdf.folder_lines(folders)
            raise Stop(2, f'There is no folder called "{wanted.strip()}". Nothing was restored. The folders are:\n'
                          + ("\n".join("  " + l for l in lines) if lines else "  (no folders yet)") + "\n  Loose")
        return got[0], got[1]
    raise Stop(2, f'Its folder "{old_folder}" is not in PenWorks any more (or it is in the Bin). Nothing was restored.\n'
                  f'Say where it should go with --folder "<Folder/Sub>", or --folder Loose.')

def stored_files(token, uid):
    have, off = set(), 0
    while True:
        st, _, chunk = web("POST", "/storage/v1/object/list/imports", token,
                           body={"prefix": uid, "limit": PAGE, "offset": off, "sortBy": {"column": "name", "order": "asc"}})
        if st != 200: raise Stop(1, f"Could not list the stored files: {drop_pdf.why(chunk)}")
        have |= {f"{uid}/{o['name']}" for o in chunk if o.get("id") is not None}
        if len(chunk) < PAGE: return have
        off += PAGE

def file_plan(token, uid, files):
    have = stored_files(token, uid)
    reuse, upload = [], {}
    for path in files:
        if path.startswith(uid + "/") and path in have:
            reuse.append(path); continue
        local = OUT / "files" / "imports" / path
        if not local.is_file():
            raise Stop(2, f"The file {path} is not in PenWorks any more and not in the backup either. Nothing was restored.")
        ext = pathlib.Path(path).suffix.lower()
        upload[path] = (local, f"{uid}/{uuid.uuid4()}{ext}", MIME.get(ext, "application/octet-stream"))
    return reuse, upload

def taken(token, table, ids):
    for i in range(0, len(ids), IDS_PER_REQ):
        part = ids[i:i + IDS_PER_REQ]
        if get(token, f"/rest/v1/{table}?select=id&id=in.({','.join(part)})"):
            return True
    return False

def insert(token, table, rows, chunk_bytes=900_000):
    batch, size = [], 0
    def send(b):
        st, _, info = web("POST", f"/rest/v1/{table}", token, body=b, headers={"Prefer": "return=minimal"})
        if st not in (200, 201, 204): raise Stop(1, f"The {table} were not all made: {drop_pdf.why(info)}")
    for r in rows:
        n = len(json.dumps(r, ensure_ascii=False))
        if batch and (size + n > chunk_bytes or len(batch) >= 500):
            send(batch); batch, size = [], 0
        batch.append(r); size += n
    if batch: send(batch)

# ---------------------------------------------------------------- the restore
def restore(what, stamp=None, folder=None, env=None, go=False, with_bin=False):
    nid, info = pick(what)
    st = stamp or info["stamps"][-1]
    if st not in info["stamps"]:
        raise Stop(2, f"Note {nid} has no backup {st}. Its backups are: " + ", ".join(info["stamps"]))
    v = read_gz(OUT / "notes" / nid / f"{st}.json.gz")
    p = plan(v, with_bin)
    name = new_name(v["note"].get("name") or "Untitled")
    if not p["pages"]:
        raise Stop(2, f'"{info["name"]}" has no pages to bring back in backup {st}' +
                      ("" if with_bin else " (its pages are all in its Bin; add --with-bin to bring those back)") + ". Nothing was restored.")

    user, pwd = login_from(env or ROOT / ".env")
    token, uid = drop_pdf.sign_in(user, pwd)
    fid, where = choose_folder(token, v["note"], v.get("folder_path") or info["folder"], folder)
    reuse, upload = file_plan(token, uid, p["files"])
    mb = sum(l.stat().st_size for l, _, _ in upload.values()) / 1048576

    print(f'{"Restoring" if go else "DRY RUN, nothing changes"}: "{info["name"]}" ({info["state"]}), backup of {nice(st)}')
    print(f'  new note:  "{name}"  in {where}, signed in as {user}')
    print(f'  pages:     {len(p["pages"])} ({p["pdf_pages"]} on a PDF), {sum(1 for r in p["pages"] if r.get("bookmark"))} bookmarked, '
          f'{len(p["stickies"])} ' + ("sticky" if len(p["stickies"]) == 1 else "stickies"))
    if p["left_out"]:
        print(f'  left out:  {p["left_out"]} page(s) or sticky(s) that were in the note\'s Bin' + ("" if with_bin else " (--with-bin brings them back)"))
    print(f'  strokes:   {len(p["strokes"])}')
    print(f'  files:     {len(reuse)} still in PenWorks (used as they are), {len(upload)} to upload from the backup ({mb:.1f} MB)')
    if not go:
        print("Nothing was changed. Add --go to make it.")
        return 0

    # safety: every new id must be new
    new_nid = str(uuid.uuid4())
    page_ids = [r["id"] for r in p["pages"] + p["stickies"]]
    if taken(token, "notes", [new_nid]) or taken(token, "pages", page_ids) or taken(token, "strokes", [s["id"] for s in p["strokes"]]):
        raise Stop(3, "A new id is already in use, which should never happen. Nothing was written.")

    # 1) files, each as a NEW object (x-upsert false: a taken name is refused, never overwritten)
    new_path = {pth: pth for pth in reuse}
    for old, (local, dest, mime) in upload.items():
        st_, _, inf = web("POST", "/storage/v1/object/imports/" + urllib.parse.quote(dest), token, raw=local.read_bytes(),
                          headers={"Content-Type": mime, "x-upsert": "false", "cache-control": "3600"})
        if st_ not in (200, 201):
            raise Stop(1, f"A file did not upload ({drop_pdf.why(inf)}). No note was made"
                          + (f"; {len(new_path) - len(reuse)} file(s) already uploaded are unused." if len(new_path) > len(reuse) else "."))
        new_path[old] = dest
    for r in p["pages"]:
        if r.get("pdf_path"): r["pdf_path"] = new_path[r["pdf_path"]]
    for s in p["strokes"]:
        if s["kind"] == "image" and isinstance(s["data"], dict) and s["data"].get("path"):
            s["data"] = dict(s["data"], path=new_path[s["data"]["path"]])

    # 2) the note, 3) its pages, 4) its stickies (after their anchors), 5) every stroke
    st_, _, inf = web("POST", "/rest/v1/notes", token, body={"id": new_nid, "folder_id": fid, "name": name, "pinned": False},
                      headers={"Prefer": "return=minimal"})
    if st_ not in (200, 201, 204): raise Stop(1, f"The note was not made: {drop_pdf.why(inf)}. Nothing else was written.")
    try:
        for r in p["pages"] + p["stickies"]: r["note_id"] = new_nid
        insert(token, "pages", p["pages"])
        if p["stickies"]: insert(token, "pages", p["stickies"])
        insert(token, "strokes", p["strokes"])
    except Stop as e:
        raise Stop(1, f'{e.msg}\nThe restore stopped part way: the new note "{name}" ({new_nid}) is not whole. '
                      "Put it in the Bin in PenWorks and run the restore again. Nothing that was there before was changed.")

    # read it back
    want_pages, want_strokes = len(page_ids), len(p["strokes"])
    got_pages = count(token, "pages", f"note_id=eq.{new_nid}")
    got_strokes = sum(count(token, "strokes", "page_id=in.(" + ",".join(page_ids[i:i + IDS_PER_REQ]) + ")")
                      for i in range(0, len(page_ids), IDS_PER_REQ))
    if (got_pages, got_strokes) != (want_pages, want_strokes):
        print(f"CHECK FAILED: PenWorks has {got_pages} pages and {got_strokes} strokes for the new note; expected {want_pages} and {want_strokes}.")
        return 3
    print(f'Done: "{name}" is in {where} as note {new_nid}: {got_pages} pages and stickies, {got_strokes} strokes (read back).')
    return 0

def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    ap = argparse.ArgumentParser(description="Bring one note back from the PenWorks backup as a NEW note. A dry run unless --go.")
    ap.add_argument("note", nargs="?", help="the note's id, or words from its name")
    ap.add_argument("--list", metavar="WORDS", help="offline: list archived notes whose name has these words, with every backup")
    ap.add_argument("--stamp", help="which backup of the note (default: the newest); --list shows them")
    ap.add_argument("--folder", help='where it goes if its own folder is gone: "Grade 12", "Grade 9/Term 1" or "Loose"')
    ap.add_argument("--with-bin", action="store_true", help="also bring back pages that were in the note's Bin")
    ap.add_argument("--env", help="the login file (default: penworks\\.env, PW_USER and PW_PASS)")
    ap.add_argument("--go", action="store_true", help="really make the new note (without it nothing changes)")
    a = ap.parse_args(argv)
    try:
        if a.list is not None: return list_notes(a.list)
        if not a.note: ap.error("give a note id or words from its name, or --list")
        return restore(a.note, a.stamp, a.folder, a.env, a.go, a.with_bin)
    except Stop as e:
        print(e.msg, file=sys.stderr if e.code else sys.stdout)
        return e.code

if __name__ == "__main__":
    sys.exit(main())
