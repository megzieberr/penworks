# PenWorks nightly backup, which is also the archive: a note deleted in PenWorks stays readable here for ever.
#
#   python -E -P tools\backup.py                    the nightly run
#   python -E -P tools\backup.py --check            offline: is the archive whole?
#   python -E -P tools\backup.py --find "algebra"   where a note's pages, pictures and PDF pages are
#   python -E -P tools\backup.py --mirror "G:\My Drive\PenWorks backup"   nightly run, then copy into that folder
#
# Strictly read-only against PenWorks: the only requests it may send are GET, HEAD, the sign-in POST and the
# storage-list POST (read_only() below refuses anything else). Signs in with PW_USER / PW_PASS from penworks\.env.
# Exit codes: 0 good, 1 sign-in or network trouble, 3 the self-check found the archive does not match PenWorks.
# Standard library only, plus drop_pdf.py next to this file for the login.
import sys, os, json, gzip, hashlib, time, shutil, argparse, pathlib, tempfile, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

# -P keeps the script's own folder off the import path, so add it on purpose for drop_pdf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drop_pdf

ROOT = drop_pdf.ROOT
OUT = ROOT / "backup"
STATE = OUT / "state.json"
TABLES = ("folders", "notes", "pages", "profiles", "comments", "action_log")
BUCKETS = ("imports", "snapshots")
PAGE = 1000            # the API's row cap per request
IDS_PER_REQ = 100      # page ids per strokes request (600 still works, 700 is refused; stay well clear)
DL_TIMEOUT = 90        # seconds of SILENCE on the line before a download is given up (not the whole transfer): a
                       # stalled small file must not hold a download slot for ten minutes; it is fetched again next run
KEEP_DAYS = 30

Stop = drop_pdf.Stop

# ---------------------------------------------------------------- console that never crashes on a name
def out(*a):
    if sys.stdout is None: return                      # pythonw (the scheduled task) has no console
    print(*a)

def safe_console():
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(errors="replace")         # cp1252 cannot print every note name
        except Exception: pass

# ---------------------------------------------------------------- read-only guard
def read_only(method, path):
    # the one place that decides what may go upstream; a raise, not an assert, so python -O cannot switch it off
    if method in ("GET", "HEAD"): return
    if method == "POST" and (path == "/auth/v1/token?grant_type=password" or path.startswith("/storage/v1/object/list/")):
        return
    raise RuntimeError(f"backup.py refused to send {method} {path.split('?')[0]}: it is read-only")

_drop_call = drop_pdf.call
def _guarded_call(method, path, *a, **k):
    read_only(method, path)
    return _drop_call(method, path, *a, **k)
drop_pdf.call = _guarded_call                          # sign_in() goes through this too

def web(method, path, token, body=None, headers=None):
    """JSON request; returns (status, response headers, parsed body). Errors carry status + message only."""
    read_only(method, path)
    h = {"apikey": drop_pdf.SB_KEY, "Authorization": "Bearer " + token}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8"); h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(drop_pdf.SB_URL + path, data=data, method=method, headers=h)
    for attempt in range(3):                           # a nightly job should shrug off one dropped read
        if attempt: time.sleep(5 * attempt)
        try:
            with urllib.request.urlopen(req, timeout=drop_pdf.TIMEOUT) as r:
                text = r.read()
                return r.status, r.headers, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            text = e.read()
            try: info = json.loads(text)
            except Exception: info = text.decode("utf-8", "replace")
            err = Stop(1, f"HTTP {e.code} from PenWorks ({path.split('?')[0]}): {drop_pdf.why(info)}")
            if e.code < 500: raise err
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            err = Stop(1, f"Could not reach PenWorks (is the internet on?): {getattr(e, 'reason', e)}")
    raise err

def rows(token, table, filt=""):
    # keyset paging on id: offset paging skips or repeats rows when she writes during the run
    got, last = [], None
    while True:
        q = f"/rest/v1/{table}?select=*&order=id&limit={PAGE}" + filt + (f"&id=gt.{last}" if last else "")
        _, _, chunk = web("GET", q, token)
        got += chunk
        if len(chunk) < PAGE: return got
        last = chunk[-1]["id"]

def exact_count(token, table):
    _, hd, _ = web("GET", f"/rest/v1/{table}?select=id&limit=1", token, headers={"Prefer": "count=exact"})
    return int((hd.get("Content-Range") or "*/0").split("/")[-1])

# ---------------------------------------------------------------- small file helpers
def stamp_now():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def stamp_time(name):
    try: return datetime.strptime(name.split(".")[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError: return None

def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)                              # a crash leaves the old file, never half a file

def write_gz(path, obj):
    write_atomic(path, gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))

def read_gz(path):
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"notes": {}, "files": {}}

def rel(p):
    return p.relative_to(OUT).as_posix()

def newest(folder):
    fs = sorted(f for f in folder.glob("*.json.gz") if stamp_time(f.name))
    return fs[-1] if fs else None

def folder_paths(folders):
    by = {f["id"]: f for f in folders}
    def path(fid, depth=0):
        f = by.get(fid)
        if not f or depth > 10: return ""
        up = path(f.get("parent_id"), depth + 1)
        return (up + "/" if up else "") + f["name"]
    return {fid: path(fid) for fid in by}

# ---------------------------------------------------------------- rows: tree + one version file per changed note
def change_key(note, pages):
    h = hashlib.sha256(json.dumps(note, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(json.dumps(sorted((p["id"], p.get("updated_at") or "") for p in pages)).encode("utf-8"))
    return h.hexdigest()

def strokes_for(token, page_ids):
    got = []
    for i in range(0, len(page_ids), IDS_PER_REQ):
        got += rows(token, "strokes", "&page_id=in.(" + ",".join(page_ids[i:i + IDS_PER_REQ]) + ")")
    return got

def sync_rows(token, prev, stamp):
    """Read the tree and write a version for every note whose key moved since `prev`. Returns (tree, notes state, updated ids)."""
    tree = {t: rows(token, t) for t in TABLES}
    fpath = folder_paths(tree["folders"])
    by_note = {}
    for p in tree["pages"]:
        by_note.setdefault(p["note_id"], []).append(p)
    nstate, updated = {}, []
    for n in tree["notes"]:
        pages = sorted(by_note.get(n["id"], []), key=lambda p: (p.get("position") or 0, p["id"]))
        key = change_key(n, pages)
        old = prev.get(n["id"])
        if old and old.get("key") == key and (OUT / old["file"]).exists():
            nstate[n["id"]] = dict(old); continue
        strokes = strokes_for(token, [p["id"] for p in pages])
        order = {p["id"]: i for i, p in enumerate(pages)}
        strokes.sort(key=lambda s: (order.get(s["page_id"], 1 << 30), s.get("seq") or 0, s["id"]))
        f = OUT / "notes" / n["id"] / f"{stamp}.json.gz"
        write_gz(f, {"note": n, "folder_path": fpath.get(n.get("folder_id"), ""), "pages": pages, "strokes": strokes,
                     "counts": {"pages": len(pages), "strokes": len(strokes)}, "saved_at": datetime.now(timezone.utc).isoformat()})
        nstate[n["id"]] = {"key": key, "file": rel(f), "pages": len(pages), "strokes": len(strokes)}
        updated.append(n["id"])
    return tree, nstate, updated

def archive_counts(tree, nstate):
    # count from the files on disk, not from memory: this is what a restore would actually have
    pages = strokes = 0
    for n in tree["notes"]:
        v = read_gz(OUT / nstate[n["id"]]["file"])
        pages += len(v["pages"]); strokes += len(v["strokes"])
    return {"folders": len(tree["folders"]), "notes": len(tree["notes"]), "pages": pages, "strokes": strokes}

def upstream_counts(token):
    return {t: exact_count(token, t) for t in ("folders", "notes", "pages", "strokes")}

# ---------------------------------------------------------------- files
def list_bucket(token, bucket, prefix):
    got, off = [], 0
    while True:
        _, _, chunk = web("POST", f"/storage/v1/object/list/{bucket}", token,
                          body={"prefix": prefix, "limit": PAGE, "offset": off, "sortBy": {"column": "name", "order": "asc"}})
        for o in chunk:
            if o.get("id") is None:                    # a sub-folder, not a file
                got += list_bucket(token, bucket, prefix + "/" + o["name"])
            else:
                got.append({"path": prefix + "/" + o["name"], "size": (o.get("metadata") or {}).get("size"),
                            "updated_at": o.get("updated_at") or ""})
        if len(chunk) < PAGE: return got
        off += PAGE

def download(token, bucket, path, dest, size):
    read_only("GET", "/storage/")
    url = drop_pdf.SB_URL + f"/storage/v1/object/authenticated/{bucket}/" + urllib.parse.quote(path)
    req = urllib.request.Request(url, headers={"apikey": drop_pdf.SB_KEY, "Authorization": "Bearer " + token})
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(req, timeout=DL_TIMEOUT) as r, open(part, "wb") as fh:
            shutil.copyfileobj(r, fh, 1 << 20)
        got = part.stat().st_size
        if size is not None and got != size:
            raise OSError(f"got {got} bytes, expected {size}")
        os.replace(part, dest)                         # only a whole file ever takes the real name
        return got
    except urllib.error.HTTPError as e:
        part.unlink(missing_ok=True)
        raise OSError(f"HTTP {e.code}")
    except Exception:
        part.unlink(missing_ok=True)
        raise

def sync_files(token, uid, old_files):
    listed = {}
    for b in BUCKETS:
        for o in list_bucket(token, b, uid):
            listed[f"{b}/{o['path']}"] = o
    todo = []
    for k, o in listed.items():
        dest = OUT / "files" / k
        have = dest.stat().st_size if dest.exists() else None
        rec = old_files.get(k)
        need = have is None or have != o["size"]
        if k.startswith("snapshots/"):
            if rec is not None:
                if o["updated_at"] > (rec.get("updated_at") or ""): need = True   # same page, newer picture, same size can happen
            elif not need:
                # no record of this picture (a first run that died before state.json was written): a local copy made
                # after the picture last changed upstream is current, so a restarted run does not fetch them all again
                try: need = dest.stat().st_mtime < datetime.fromisoformat(o["updated_at"]).timestamp()
                except ValueError: need = True
        if need: todo.append(k)
    files, new_bytes, failed = {}, 0, []
    def one(k):
        b, p = k.split("/", 1)
        return k, download(token, b, p, OUT / "files" / k, listed[k]["size"])
    done = set()
    with ThreadPoolExecutor(4) as pool:
        for fut in [pool.submit(one, k) for k in todo]:
            try:
                k, n = fut.result(); new_bytes += n; done.add(k)
            except Exception as e:
                failed.append(str(e)[:120])
    for k, o in listed.items():
        if k in todo and k not in done:
            if k in old_files: files[k] = old_files[k]  # keep what the last good run knew; retried next run
            continue
        files[k] = {"size": o["size"], "updated_at": o["updated_at"]}
    # objects that vanished upstream keep their record (and their local file) for --check and the archive
    for k, rec in old_files.items():
        if k not in listed: files[k] = dict(rec, gone=True)
    return files, len(listed), len(done), new_bytes, failed

# ---------------------------------------------------------------- INDEX.md
def note_state(n, in_tree, last_seen):
    if not in_tree: return f"gone from PenWorks, last seen {last_seen[:10]}"
    if n.get("deleted_at"): return f"in the Bin since {n['deleted_at'][:10]}"
    return "live"

def cell(s):
    return str(s).replace("|", "/").replace("\n", " ")

def write_index(tree, nstate, last_seen):
    live_ids = {n["id"] for n in tree["notes"]}
    fpath = folder_paths(tree["folders"])
    lines, tot = [], {"live": 0, "bin": 0, "gone": 0}
    for d in sorted((OUT / "notes").glob("*")):
        f = OUT / nstate[d.name]["file"] if d.name in nstate else newest(d)
        if not f: continue
        v = read_gz(f)
        n = v["note"]
        if d.name in live_ids:
            n = next(x for x in tree["notes"] if x["id"] == d.name)
        st = note_state(n, d.name in live_ids, last_seen.get(d.name) or v.get("saved_at", ""))
        tot["live" if st == "live" else "bin" if st.startswith("in the Bin") else "gone"] += 1
        edited = max([n.get("updated_at") or ""] + [p.get("updated_at") or "" for p in v["pages"]])[:16].replace("T", " ")
        folder = fpath.get(n.get("folder_id"), v.get("folder_path", "")) if d.name in live_ids else v.get("folder_path", "")
        lines.append((n.get("name") or "", f"| {cell(n.get('name') or 'Untitled')} | {cell(folder or 'Loose')} | {len(v['pages'])} | "
                                           f"{len(v['strokes'])} | {edited} | {st} | {d.name} |"))
    lines.sort(key=lambda x: x[0].casefold())
    head = [f"# PenWorks archive index", "",
            f"{len(lines)} notes ever seen: {tot['live']} live, {tot['bin']} in the Bin, {tot['gone']} gone from PenWorks. "
            f"Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}. Pages and strokes count binned pages too.", "",
            "| Name | Folder | Pages | Strokes | Last edited (UTC) | State | Note id |", "|---|---|---|---|---|---|---|"]
    write_atomic(OUT / "INDEX.md", ("\n".join(head + [l for _, l in lines]) + "\n").encode("utf-8"))

# ---------------------------------------------------------------- retention
def prune(folder, keep_newest):
    fs = sorted((f for f in folder.glob("*.json.gz") if stamp_time(f.name)), key=lambda f: f.name)
    if not fs: return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    keep = {fs[-1]} if keep_newest else set()
    by_month = {}
    for f in fs:
        t = stamp_time(f.name)
        if t >= cutoff: keep.add(f)
        else: by_month[t.strftime("%Y-%m")] = f        # sorted ascending, so the last one wins: the newest of the month
    keep |= set(by_month.values())
    gone = 0
    for f in fs:
        if f not in keep:
            f.unlink(); gone += 1
    return gone

def retention():
    n = prune(OUT / "tree", keep_newest=True)
    for d in (OUT / "notes").glob("*"):
        if d.is_dir(): n += prune(d, keep_newest=True)   # the newest version of every note stays, whatever its age
    return n

# ---------------------------------------------------------------- mirror
def mirror_target(arg):
    if arg: return arg
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("PW_BACKUP_MIRROR="):
                return line.split("=", 1)[1].strip() or None
    return None

def mirror(dest):
    dest = pathlib.Path(dest)
    copied = 0
    for src in OUT.rglob("*"):
        if not src.is_file() or src.name.endswith((".tmp", ".part", ".lock")): continue
        to = dest / src.relative_to(OUT)
        s = src.stat()
        if to.exists():
            t = to.stat()
            if t.st_size == s.st_size and int(t.st_mtime) == int(s.st_mtime): continue
        to.parent.mkdir(parents=True, exist_ok=True)
        tmp = to.with_name(to.name + ".tmp")
        shutil.copy2(src, tmp); os.replace(tmp, to)    # never deletes anything in the mirror
        copied += 1
    return copied

# ---------------------------------------------------------------- the nightly run
def finish(line):
    write_atomic(OUT / "LAST-RUN.txt", (line + "\n").encode("utf-8"))
    with open(OUT / "backup.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    out(line)

def run(mirror_arg=None):
    t0 = time.monotonic()
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    OUT.mkdir(exist_ok=True)
    lock = OUT / "run.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < 3 * 3600:
            finish(f"{when} FAILED: another backup run is still busy (backup\\run.lock)"); return 1
        lock.touch()                                   # left behind by a crash hours ago
    try:
        return _run(t0, when, mirror_arg)
    except Stop as e:
        finish(f"{when} FAILED: {e.msg}"); return 1
    except Exception as e:
        finish(f"{when} FAILED: {type(e).__name__}: {str(e)[:200]}"); return 1
    finally:
        lock.unlink(missing_ok=True)

def _run(t0, when, mirror_arg):
    state = load_state()
    stamp = stamp_now()
    token, uid = drop_pdf.sign_in(*drop_pdf.login(False))

    tree, nstate, updated = sync_rows(token, state.get("notes", {}), stamp)
    have, want = archive_counts(tree, nstate), upstream_counts(token)
    if have != want:
        # she may have been writing during the run: re-read once, refetching only notes whose key moved
        tree, nstate, more = sync_rows(token, nstate, stamp)
        updated = sorted(set(updated) | set(more))
        have, want = archive_counts(tree, nstate), upstream_counts(token)
        if have != want:
            diff = ", ".join(f"{k} {have[k]} here vs {want[k]} in PenWorks" for k in want if have[k] != want[k])
            finish(f"{when} FAILED: self-check mismatch ({diff})"); return 3

    files, nfiles, nnew, nbytes, failed = sync_files(token, uid, state.get("files", {}))

    tree_out = dict(tree, versions={k: v["file"] for k, v in nstate.items()}, saved_at=datetime.now(timezone.utc).isoformat())
    write_gz(OUT / "tree" / f"{stamp}.json.gz", tree_out)
    last_seen = dict(state.get("last_seen", {}))
    now_iso = datetime.now(timezone.utc).isoformat()
    for n in tree["notes"]: last_seen[n["id"]] = now_iso
    # notes gone upstream keep their record, so the archive still knows their last version
    for k, v in state.get("notes", {}).items():
        if k not in nstate: nstate[k] = dict(v, gone=True)
    live = {k: v for k, v in nstate.items() if not v.get("gone")}
    write_index(tree, live, last_seen)
    retention()

    mtxt = ""
    target = mirror_target(mirror_arg)
    if target:
        try: mtxt = f" | mirror {mirror(target)} copied"
        except Exception as e: mtxt = f" | mirror FAILED: {type(e).__name__}"

    new_state = {"notes": nstate, "files": files, "last_seen": last_seen, "user_id": uid, "saved_at": now_iso}
    write_atomic(STATE, json.dumps(new_state, ensure_ascii=False, indent=1).encode("utf-8"))   # written last

    ftxt = f"files {nfiles} ({nnew} new, {nbytes / 1048576:.1f} MB" + (f", {len(failed)} could not download: {failed[0]}" if failed else "") + ")"
    finish(f"{when} OK | notes {want['notes']} ({len(updated)} updated) | pages {want['pages']} | strokes {want['strokes']} | "
           f"{ftxt} | {round(time.monotonic() - t0)} s{mtxt}")
    return 0

# ---------------------------------------------------------------- --check (offline)
def check():
    problems = []
    state = load_state()
    trees = sorted((OUT / "tree").glob("*.json.gz"))
    if not trees or not state.get("notes"):
        out("FAILED: no finished backup run yet."); return 3
    tree = read_gz(trees[-1])
    tnotes = {n["id"]: n for n in tree["notes"]}
    tpages = {}
    for p in tree["pages"]: tpages.setdefault(p["note_id"], set()).add(p["id"])
    files = state.get("files", {})
    seen_up = lambda k: k in files and not files[k].get("gone")
    nv = nst = 0
    paths = []
    for d in sorted((OUT / "notes").glob("*")):
        f = newest(d)
        if not f: problems.append(f"note {d.name}: no version file"); continue
        try: v = read_gz(f)
        except Exception as e: problems.append(f"{rel(f)} does not open: {type(e).__name__}"); continue
        nv += 1
        pids = {p["id"] for p in v["pages"]}
        bad = sum(1 for s in v["strokes"] if s["page_id"] not in pids)
        if bad: problems.append(f"note {d.name}: {bad} strokes point at a page not in the note")
        if any(p["note_id"] != d.name for p in v["pages"]): problems.append(f"note {d.name}: a page belongs to another note")
        if d.name in tnotes:
            if pids != tpages.get(d.name, set()): problems.append(f"note {d.name}: pages differ from the newest tree")
            nst += len(v["strokes"])
            for p in v["pages"]:
                if p.get("pdf_path"): paths.append("imports/" + p["pdf_path"])
                if p.get("snapshot_path"): paths.append("snapshots/" + p["snapshot_path"])
            for s in v["strokes"]:
                if s.get("kind") == "image" and isinstance(s.get("data"), dict) and s["data"].get("path"):
                    paths.append("imports/" + s["data"]["path"])
    orphans = set(tpages) - set(tnotes)
    if orphans: problems.append(f"{len(orphans)} pages' notes are missing from the newest tree")
    missing = [k for k in tnotes if k not in state["notes"] or not (OUT / state["notes"][k]["file"]).exists()]
    if missing: problems.append(f"{len(missing)} notes in the tree have no version file")
    want = sum(v.get("strokes", 0) for k, v in state["notes"].items() if k in tnotes)
    if nst != want: problems.append(f"strokes: {nst} in the newest versions vs {want} recorded")
    nfile = 0
    for k in sorted(set(paths)):
        if not seen_up(k): continue
        nfile += 1
        loc = OUT / "files" / k
        if not loc.exists(): problems.append(f"missing file {k}")
        elif files[k].get("size") is not None and loc.stat().st_size != files[k]["size"]: problems.append(f"wrong size {k}")
    if problems:
        out(f"FAILED: {len(problems)} problem(s)")
        for p in problems[:20]: out("  " + p)
        return 3
    out(f"OK: {nv} note versions open ({len(tnotes)} in the newest tree), {nst} strokes, {nfile} referenced files present")
    return 0

# ---------------------------------------------------------------- --find (offline)
def find(words):
    state = load_state()
    trees = sorted((OUT / "tree").glob("*.json.gz"))
    tree = read_gz(trees[-1]) if trees else {"notes": [], "folders": []}
    tnotes = {n["id"]: n for n in tree["notes"]}
    fpath = folder_paths(tree["folders"])
    last_seen = state.get("last_seen", {})
    w = words.casefold()
    hits = 0
    for d in sorted((OUT / "notes").glob("*")):
        f = newest(d)
        if not f: continue
        v = read_gz(f)
        n = tnotes.get(d.name, v["note"])
        if w not in (n.get("name") or "").casefold(): continue
        hits += 1
        folder = fpath.get(n.get("folder_id"), v.get("folder_path", "")) if d.name in tnotes else v.get("folder_path", "")
        out(f"{n.get('name')}  |  {folder or 'Loose'}  |  {note_state(n, d.name in tnotes, last_seen.get(d.name, v.get('saved_at', '')))}  |  {d.name}")
        out(f"  version file: {f}")
        per = {}
        for s in v["strokes"]: per[s["page_id"]] = per.get(s["page_id"], 0) + 1
        live = [p for p in v["pages"] if not p.get("deleted_at")]
        binned = [p for p in v["pages"] if p.get("deleted_at")]
        for i, p in enumerate(live + binned, 1):
            bits = [f"  p{i}" + (" (sticky)" if p.get("kind") == "sticky" else "") + (" (in Bin)" if p.get("deleted_at") else ""),
                    f"{per.get(p['id'], 0)} strokes"]
            if p.get("snapshot_path"):
                loc = OUT / "files" / "snapshots" / p["snapshot_path"]
                if loc.exists(): bits.append(f"picture {loc}")
            if p.get("pdf_path"):
                bits.append(f"PDF {OUT / 'files' / 'imports' / p['pdf_path']} page {p.get('pdf_page')}")
            out("  |  ".join(bits))
    if not hits: out(f'No note name contains "{words}".')
    return 0

def main(argv=None):
    safe_console()
    ap = argparse.ArgumentParser(description="PenWorks nightly backup and archive (read-only against PenWorks).")
    ap.add_argument("--check", action="store_true", help="offline: is the archive whole?")
    ap.add_argument("--find", metavar="WORDS", help="offline: list notes whose name contains WORDS")
    ap.add_argument("--mirror", metavar="FOLDER", help="after a good run, copy new and changed files there")
    a = ap.parse_args(argv)
    if a.check: return check()
    if a.find is not None: return find(a.find)
    return run(a.mirror)

if __name__ == "__main__":
    sys.exit(main())
