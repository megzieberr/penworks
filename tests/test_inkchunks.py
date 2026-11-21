# PenWorks pw-v9s checks, only changed ink, in chunks (audit finding F). Headless Playwright (Python), local mode
# (?local=1). A note of 250 pages; the twin's page ids go 100 to a request (api.strokesPart / api.stampsPart are wrapped
# in the page to count and fail requests). "Another device" = the twin's rows changed directly with the page's
# updated_at moved, as the database trigger strokes_touch_page does, and no live event.
# Run: python -E -P tests\test_inkchunks.py
# Groups: chunks; a failed chunk; only changed pages (reopen, one page, liveGap, a missing stamp after a reload, a stamp
# equal to the millisecond, a failed light request); her own stroke; house rules.
import sys, time, re, pathlib, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); from swcache import SW_CACHE  # the cache name, read from sw.js
PORT = 8847
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
VERSION = SW_CACHE
N = 250

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

class AppHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

SEED_JS = """(n) => {
  localStorage.clear();
  const t = '2026-11-01T08:00:00.000Z';
  const pages = [], strokes = [];
  for (let k = 0; k < n; k++) {
    const id = 'L' + String(k).padStart(3, '0');
    pages.push({ id, note_id: 'nL', position: k, orientation: 'portrait', background: 'grid', bookmark: false, deleted_at: null, created_at: t, updated_at: t });
    const many = k === 7 ? 3 : 1;
    for (let j = 0; j < many; j++) strokes.push({ id: 's' + id + '_' + j, page_id: id, seq: 1000 + k * 10 + j, kind: 'pen',
      style: { colour: '#2F4BB8', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100 + j * 20, 200], [300, 320], [500, 260]] } });
  }
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Long', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'nL', folder_id: 'f1', name: 'Long PDF', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages, strokes }));
}"""

# the request spy: every strokesPart / stampsPart call's ids, and switches to make one fail
SPY_JS = """() => {
  const api = window.__pw.api;
  if (!api.__spied) {
    const s0 = api.strokesPart, a0 = api.stampsPart;
    api.strokesPart = async (part) => { const R = window.__R; R.s.push(part.slice()); if (R.failS && R.s.length === R.failS) throw new Error('chunk refused (test)');
      const got = await s0(part); if (R.holdS) { const ms = R.holdS; R.holdS = 0; await new Promise((r) => setTimeout(r, ms)); } return got; };
    api.stampsPart = async (part) => { const R = window.__R; R.a.push(part.slice()); if (R.failA) throw new Error('light read refused (test)'); return a0(part); };
    api.__spied = true;
  }
  window.__R = { s: [], a: [], failS: 0, failA: false };
  window.__W = window.__W || [];
  if (!console.__spied) { const w = console.warn; console.warn = (...a) => { window.__W.push(String(a[0])); w.apply(console, a); }; console.__spied = true; }
  return 1;
}"""
IDS = "(n) => Array.from({ length: n }, (_, k) => 'L' + String(k).padStart(3, '0'))"
TWIN = "() => JSON.parse(localStorage.getItem('penworks.local.v2'))"
# another device: a stroke lands on page pid in the twin and the page's updated_at moves (the database trigger)
OTHER_JS = """([pid, sid, stamp]) => { const d = JSON.parse(localStorage.getItem('penworks.local.v2'));
  d.strokes.push({ id: sid, page_id: pid, seq: 900000 + d.strokes.length, kind: 'pen', owner_id: 'local', created_at: new Date().toISOString(),
    style: { colour: '#C0392B', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[50, 50], [150, 150]] } });
  d.pages.find((p) => p.id === pid).updated_at = stamp || new Date().toISOString();
  localStorage.setItem('penworks.local.v2', JSON.stringify(d)); return d.pages.find((p) => p.id === pid).updated_at; }"""

def ready(pg, ms=30000): pg.wait_for_selector("body[data-ready='1']", timeout=ms)
def until(pg, fn, ms=8000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def R(pg): return pg.evaluate("window.__R")
def ids(pg, n=N): return pg.evaluate(IDS, n)
def has(pg, pid, sid): return pg.evaluate("([p, s]) => window.__pw.store.load(p).some((r) => r.id === s) && window.__pw.ink.strokesOf(p).some((r) => r.id === s)", [pid, sid])
def stamp(pg, pid): return pg.evaluate("(p) => window.__pw.store.stampOf(p)", pid)
def kept_stamp(pg, pid): return pg.evaluate("(p) => window.__pw.store.cachedStamp(p)", pid)
def twin_stamp(pg, pid): return pg.evaluate("(p) => JSON.parse(localStorage.getItem('penworks.local.v2')).pages.find((r) => r.id === p).updated_at", pid)
def reconcile(pg, n=N): pg.evaluate("async (n) => { const ids = Array.from({ length: n }, (_, k) => 'L' + String(k).padStart(3, '0')); await window.__pw.store.reconcile(ids); await window.__pw.store.settled(); }", n)
def all_stamped(pg): return pg.evaluate("(ids) => ids.every((id) => window.__pw.store.stampOf(id) === JSON.parse(localStorage.getItem('penworks.local.v2')).pages.find((p) => p.id === id).updated_at)", ids(pg))
def open_note(pg):
    pg.evaluate("() => { const a = document.querySelector(\".frow[data-id='all']\"); if (a && !document.querySelector('#grid .card:not(.plus)')) a.click(); }"); pg.wait_for_timeout(60)
    pg.locator("#grid .card").filter(has=pg.locator(".name", has_text=re.compile("^Long PDF$"))).first.click()
    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']", timeout=30000); pg.wait_for_timeout(250)
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])"); pg.wait_for_timeout(150)
def lens(parts): return [len(p) for p in parts]

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
        pg.evaluate(SEED_JS, N); pg.reload(); ready(pg)
        pg.evaluate(SPY_JS)
        ALL = ids(pg)

        # ============================================================ chunks
        group[0] = "chunks"
        rows = pg.evaluate("async (ids) => (await window.__pw.api.strokesOf(ids)).map((r) => [r.id, r.page_id, r.seq])", ALL)
        r = R(pg)
        want = pg.evaluate("() => JSON.parse(localStorage.getItem('penworks.local.v2')).strokes.slice().sort((a, b) => (a.seq - b.seq) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)).map((s) => [s.id, s.page_id, s.seq])")
        check("1. api.strokesOf of 250 pages goes out as 3 requests of 100, 100 and 50 ids, every id once",
              lens(r["s"]) == [100, 100, 50] and sorted(sum(r["s"], [])) == sorted(ALL), lens(r["s"]))
        check("2. ... and the joined answer is every stroke, in seq order, as one request gave it before", rows == want and len(rows) == N + 2, [len(rows), len(want)])
        pg.evaluate(SPY_JS)
        t0 = time.time()
        open_note(pg)
        ok = until(pg, lambda: all_stamped(pg), 15000)
        print(f"first open of 250 pages: all stamped after {time.time() - t0:.1f} s")
        r = R(pg)
        check("3. first open on a fresh device: the light read goes out as 100, 100, 50 ids", lens(r["a"]) == [100, 100, 50], lens(r["a"]))
        check("4. ... the ink read as 3 requests of at most 100 ids (100, 100, 50), all 250 pages", lens(r["s"]) == [100, 100, 50] and sorted(sum(r["s"], [])) == sorted(ALL), lens(r["s"]))
        full = pg.evaluate("(ids) => { const d = JSON.parse(localStorage.getItem('penworks.local.v2')); return ids.every((id) => { const a = window.__pw.store.load(id).map((r) => r.id).sort(), b = d.strokes.filter((s) => s.page_id === id).map((s) => s.id).sort(); return a.length && JSON.stringify(a) === JSON.stringify(b); }); }", ALL)
        check("5. every page's ink is on the device (page L007's three strokes too)", full and len(pg.evaluate("window.__pw.store.load('L007')")) == 3)
        check("6. every page's stamp is the database's updated_at, word for word", ok)
        check("7. ... and kept on the device", kept_stamp(pg, "L000") == twin_stamp(pg, "L000") and kept_stamp(pg, "L249") == twin_stamp(pg, "L249"),
              [kept_stamp(pg, "L249"), twin_stamp(pg, "L249")])

        # ============================================================ a failed chunk
        group[0] = "a failed chunk"
        pg.evaluate(SPY_JS)
        pg.evaluate("window.__R.failS = 2")
        err = pg.evaluate("async (ids) => { try { await window.__pw.api.strokesOf(ids); return null; } catch (e) { return String(e.message); } }", ALL)
        check("8. the second of three requests fails: api.strokesOf fails as a whole", err and "chunk refused" in err, err)
        pg.wait_for_timeout(20)
        s10 = pg.evaluate(OTHER_JS, ["L010", "sX10", None]); s150 = pg.evaluate(OTHER_JS, ["L150", "sX150", None])
        before = [stamp(pg, "L010"), stamp(pg, "L150"), kept_stamp(pg, "L010")]
        pg.evaluate(SPY_JS)
        pg.evaluate("window.__R.failA = true; window.__R.failS = 2; window.__W.length = 0")
        reconcile(pg)
        r = R(pg)
        check("9. light read failed too: the reconcile reads every page, chunk 2 of 3 fails", lens(r["s"]) == [100, 100], lens(r["s"]))
        check("10. nothing half-read is kept: page L010 (in the chunk that came back) does not have the new stroke",
              not has(pg, "L010", "sX10") and not has(pg, "L150", "sX150"))
        check("11. ... no stamp moved, in memory or on the device", [stamp(pg, "L010"), stamp(pg, "L150"), kept_stamp(pg, "L010")] == before, before)
        w = pg.evaluate("window.__W")
        check("12. ... and it is not silent: a console warning names the 250 pages", any("250 pages" in x for x in w), w[-2:])
        pg.evaluate(SPY_JS)
        reconcile(pg)
        r = R(pg)
        check("13. next time (all well): the two changed pages alone are read, in one request", r["s"] == [["L010", "L150"]], r["s"])
        check("14. ... their new strokes show, and their stamps are the database's new ones",
              has(pg, "L010", "sX10") and has(pg, "L150", "sX150") and stamp(pg, "L010") == s10 and stamp(pg, "L150") == s150, [stamp(pg, "L010"), s10])

        # ============================================================ only changed pages
        group[0] = "only changed pages"
        back(pg); pg.evaluate(SPY_JS)
        open_note(pg); pg.wait_for_timeout(600)
        r = R(pg)
        check("15. reopen with nothing changed: the light read only (3 requests), no ink request", lens(r["a"]) == [100, 100, 50] and r["s"] == [], [lens(r["a"]), lens(r["s"])])
        pg.wait_for_timeout(20)
        s123 = pg.evaluate(OTHER_JS, ["L123", "sX123", None])
        pg.evaluate(SPY_JS)
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")      # back to the front: liveGap
        ok = until(pg, lambda: has(pg, "L123", "sX123"), 5000)
        pg.wait_for_timeout(300)
        r = R(pg)
        check("16. another device inks page L123; the app comes back to the front (liveGap): page L123 alone is read", r["s"] == [["L123"]], r["s"])
        check("17. ... and the new stroke shows on it", ok and pg.evaluate("!!document.querySelector('#stack [data-id=\"sX123\"], #stack [id=\"sX123\"]') || window.__pw.ink.strokesOf('L123').some((r) => r.id === 'sX123')"))
        check("18. ... its stamp is the database's new updated_at, not this device's clock", stamp(pg, "L123") == s123 and kept_stamp(pg, "L123") == s123, [stamp(pg, "L123"), s123])

        # a stamp that looks equal to the millisecond, but is not the same text: read
        k = twin_stamp(pg, "L077")
        alike = k[:-1] + "4Z" if k.endswith("Z") else k + "4"
        pg.evaluate(OTHER_JS, ["L077", "sX77", alike])
        pg.evaluate(SPY_JS)
        reconcile(pg)
        r = R(pg)
        check("19. a stamp equal to the millisecond but not the same text ('...000Z' then '...0004Z'): the page is read",
              r["s"] == [["L077"]] and has(pg, "L077", "sX77"), [k, alike, r["s"]])

        # a failed light request: everything is read
        pg.evaluate(SPY_JS); pg.evaluate("window.__R.failA = true")
        reconcile(pg)
        r = R(pg)
        check("20. the light read fails: every page is read, 100, 100, 50", lens(r["s"]) == [100, 100, 50], lens(r["s"]))
        check("21. ... and the ink is still all there", pg.evaluate("(ids) => ids.every((id) => window.__pw.store.load(id).length > 0)", ALL))

        # a missing stamp after a reload: that page is read; the rest come from the device. A page picture moves
        # updated_at too (setSnapshot; the pictures of the pages inked above are made at start-up), so those pages may be
        # read once more: never fewer pages than changed.
        back(pg)
        pg.wait_for_timeout(1000)
        until(pg, lambda: pg.evaluate("(() => { const s = window.__pw.snap(); return !s.running && !s.due.length; })()"), 15000)
        pg.wait_for_timeout(500)
        pg.evaluate(SPY_JS); reconcile(pg)
        TW = "() => Object.fromEntries(JSON.parse(localStorage.getItem('penworks.local.v2')).pages.map((p) => [p.id, [p.updated_at, p.snapshot_at]]))"
        pre = pg.evaluate(TW)
        pg.evaluate("""() => new Promise((ok) => { const q = indexedDB.open('penworks.local.local', 1);
          q.onsuccess = () => { const t = q.result.transaction(['strokes'], 'readwrite'); t.objectStore('strokes').delete('at:L050');
            t.oncomplete = () => { q.result.close(); ok(1); }; }; })""")
        pg.reload(); ready(pg); pg.evaluate(SPY_JS)
        open_note(pg)
        ok = until(pg, lambda: stamp(pg, "L050") is not None, 5000)
        pg.wait_for_timeout(1500)
        r = R(pg)
        post = pg.evaluate(TW)
        moved = sorted(p for p in post if post[p][0] != pre[p][0])
        print("after the reload, pages whose updated_at moved (their picture made at start-up):", moved,
              "snapshot_at:", [post[p][1] for p in moved])
        got = sorted(sum(r["s"], []))
        check("22. after a reload, page L050's stamp gone from the device: L050 is read, and besides it only pages whose updated_at moved meanwhile",
              "L050" in got and set(got) <= set(moved + ["L050"]) and all(len(p) <= 100 for p in r["s"]), [r["s"], moved])
        pg.wait_for_timeout(1500); reconcile(pg)
        check("22b. a picture made after that light read moves updated_at: the next reconcile reads that page, and then every stamp is the database's",
              all_stamped(pg), [p for p in ALL if stamp(pg, p) != twin_stamp(pg, p)][:5])
        check("23. ... it gets its stamp back; the other pages kept theirs through the reload",
              ok and stamp(pg, "L050") == twin_stamp(pg, "L050") and stamp(pg, "L077") == alike and stamp(pg, "L249") == pre["L249"][0],
              [stamp(pg, "L050"), stamp(pg, "L077"), alike])
        check("24. ... and the other device's strokes from before the reload still show", has(pg, "L123", "sX123") and has(pg, "L010", "sX10"))

        # ============================================================ her own stroke
        group[0] = "her own stroke"
        pg.evaluate(SPY_JS)
        mine = pg.evaluate("""() => { const rec = { id: 'mine1', page_id: 'L200', seq: Date.now(), kind: 'pen',
          style: { colour: '#2F4BB8', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[60, 60], [260, 90]] } };
          window.__pw.ink.put('L200', [rec]); return window.__pw.store.stampOf('L200'); }""")
        check("25. her stroke on this device drops the page's stamp at once", mine is None, mine)
        reconcile(pg)
        check("26. the next reconcile keeps her stroke (on the page, and it reached the database)",
              has(pg, "L200", "mine1") and pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).strokes.some((s) => s.id === 'mine1')"))
        pg.wait_for_timeout(20)
        pg.evaluate(OTHER_JS, ["L200", "sX200", None])
        pg.evaluate("""() => window.__pw.ink.put('L200', [{ id: 'mine2', page_id: 'L200', seq: Date.now(), kind: 'pen',
          style: { colour: '#2F4BB8', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[60, 160], [260, 190]] } }])""")
        reconcile(pg); reconcile(pg)
        check("27. her second stroke while another device inks the same page: both strokes stay, both in the database",
              has(pg, "L200", "mine1") and has(pg, "L200", "mine2") and has(pg, "L200", "sX200")
              and pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).strokes.filter((s) => ['mine1', 'mine2', 'sX200'].includes(s.id)).length") == 3)
        pg.evaluate(SPY_JS)
        reconcile(pg)
        check("28. once it all settled, a reconcile reads nothing", R(pg)["s"] == [], R(pg)["s"])

        # her stroke's push lands while a reconcile is between its read and its check (the read has the page without it).
        # The push waits at a gate; the reconcile reads (no mine3 yet) and is held 1.5 s; the gate opens after 0.3 s, so
        # the push lands inside the hold and its op leaves the queue before the reconcile looks.
        pg.evaluate(SPY_JS)
        pg.evaluate("""async () => { const api = window.__pw.api, store = window.__pw.store, p0 = api.putStrokes;
          let open; const gate = new Promise((r) => { open = r; });
          api.putStrokes = async (...a) => { await gate; return p0(...a); };
          window.__pw.ink.put('L201', [{ id: 'mine3', page_id: 'L201', seq: Date.now(), kind: 'pen',
            style: { colour: '#2F4BB8', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[60, 260], [260, 290]] } }]);
          await new Promise((r) => setTimeout(r, 50));
          window.__R.holdS = 1500;
          const rc = store.reconcile(['L201']);
          setTimeout(open, 300);
          await rc; await new Promise((r) => setTimeout(r, 300)); await store.settled(); api.putStrokes = p0; }""")
        check("28-. (the set-up: the read was held while the push landed)", R(pg)["s"][:1] == [["L201"]], R(pg)["s"])
        check("28a. her push lands while a reconcile holds an older read: her stroke stays on the page and on the device",
              has(pg, "L201", "mine3") and pg.evaluate("window.__pw.store.cached('L201').then((r) => (r || []).some((x) => x.id === 'mine3'))"),
              pg.evaluate("window.__pw.store.load('L201').map((r) => r.id)"))
        check("28b. ... and it is in the database", pg.evaluate("JSON.parse(localStorage.getItem('penworks.local.v2')).strokes.some((s) => s.id === 'mine3')"))

        # ============================================================ house rules
        group[0] = "house rules"
        keys = pg.evaluate("caches.keys()")
        check(f"29. cache is {VERSION}", VERSION in keys, keys)
        raw = (ROOT / "sw.js").read_bytes()
        check("30. sw.js has no BOM", not raw.startswith(b"\xef\xbb\xbf"))
        srcs = "".join((ROOT / p).read_text(encoding="utf-8") for p in ["sw.js", "js/api.js", "js/store.js", "js/local-backend.js", "tests/test_inkchunks.py"])
        check("31. no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("32. no page errors", not errs, errs[:3])
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
