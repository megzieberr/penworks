# PenWorks pw-v9v checks, refused changes (audit finding J): a stroke push the server refuses (HTTP 400 403 404 409 422)
# is parked, kept in the device's queue store with parked: true, so the ops behind it still land; no answer, 401, 408,
# 429 and 5xx are retried as before. Parked ops are tried again at every start and on `online`, and leave the list
# when they land; nothing parked is ever deleted. Two plain toasts, up until tapped: ink unsent 5 minutes while online
# (shortened here through localStorage penworks.local.slowms), and anything parked. navigator.storage.persist() is
# asked once per device. Headless Playwright (Python), local mode (?local=1); the twin's test hooks failStatus and
# penworks.local.refuseids stand in for the server's answers.
# Run: python -E -P tests\test_parked.py
# Groups: normal case; unsent while online; not refused; parked; each refusal; held behind; kept through a reload;
# tried on online; tried at start; persistent storage; house rules.
import sys, time, json, pathlib, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); from swcache import SW_CACHE  # the cache name, read from sw.js
PORT = 8850
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
VERSION = SW_CACHE
SLOW_WORDS = "Some ink has not saved for 5 minutes. It is safe on this tablet. Keep PenWorks open on wifi."
PARK_WORDS = "Some changes could not be saved yet. They are kept on this tablet and tried again."
DOT_WORDS = "Not saved yet. Your ink is kept on this tablet."

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

class AppHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

SEED_JS = """(slow) => {
  localStorage.clear();
  const t = '2026-11-20T08:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Ink', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Lesson', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [{ id: 'p1', note_id: 'n1', position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t },
            { id: 'p2', note_id: 'n1', position: 1, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t }] }));
  if (slow) localStorage.setItem('penworks.local.slowms', String(slow));
}"""
# every toast from the very start of the page (an init script: the start's toast comes before any evaluate could)
TOASTLOG_INIT = """(() => { window.__toastLog = [];
  new MutationObserver((ms) => { const t = document.getElementById('toast');
    if (!t || !ms.some((m) => m.target === t || t.contains(m.target))) return;
    const b = t.querySelector('.toastAct');
    window.__toastLog.push({ text: t.firstChild && t.firstChild.nodeType === 3 ? t.firstChild.textContent : t.textContent, button: b ? b.textContent : null });
  }).observe(document, { childList: true, subtree: true, characterData: true }); })()"""
# a stand-in StorageManager: persisted() reads t.persisted, persist() counts its calls in t.persist
PERSIST_INIT = """(() => { const s = navigator.storage; if (!s) return;
  s.persisted = () => Promise.resolve(localStorage.getItem('t.persisted') === '1');
  s.persist = () => { localStorage.setItem('t.persist', String(Number(localStorage.getItem('t.persist') || 0) + 1)); return Promise.resolve(true); };
})()"""
ADD_JS = """([pid, sid, seq]) => { window.__pw.store.change(pid, [], [{ id: sid, page_id: pid, seq, kind: 'pen',
  style: { colour: '#2F4BB8', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: [[100, 100], [200, 160], [300, 120]] } }]); return 1; }"""
TWIN_IDS = "() => JSON.parse(localStorage.getItem('penworks.local.v2')).strokes.map((s) => s.id)"
DOT_JS = "() => { const d = document.getElementById('saveDot'); return [d.dataset.state, d.title]; }"

seq = [1000]
def ready(pg, ms=20000): pg.wait_for_selector("body[data-ready='1']", timeout=ms)
def until(pg, fn, ms=4000, step=60):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def add(pg, pid, sid):
    seq[0] += 10
    pg.evaluate(ADD_JS, [pid, sid, seq[0]])
def erase(pg, pid, sid): pg.evaluate("([p, s]) => window.__pw.store.change(p, [s], [])", [pid, sid])
def settle(pg): pg.evaluate("window.__pw.store.settled()")
def twin(pg): return pg.evaluate(TWIN_IDS)
def parked(pg): return pg.evaluate("window.__pw.store.parkedOps()")
def queued(pg): return pg.evaluate("window.__pw.store.queued()")
def kept(pg): return pg.evaluate("window.__pw.store.keptOps()")
def notices(pg): return pg.evaluate("window.__pw.store.notices()")
def dot(pg): return pg.evaluate(DOT_JS)
def toasts(pg, words=None):
    log = pg.evaluate("window.__toastLog")
    return [t for t in log if words is None or t["text"] == words]
def showing(pg): return pg.evaluate("document.getElementById('toast').classList.contains('show')")
def refuse_ids(pg, ids, status=400):
    pg.evaluate("(v) => v ? localStorage.setItem('penworks.local.refuseids', v) : localStorage.removeItem('penworks.local.refuseids')",
                json.dumps({"ids": ids, "status": status}) if ids else "")
def offline(pg): pg.context.set_offline(True); pg.evaluate("window.dispatchEvent(new Event('offline'))"); pg.wait_for_timeout(50)
def online(pg): pg.context.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))")
def ids_of(op): return [r["id"] for r in op["added"]] + list(op["removed"])

app = ThreadingHTTPServer(("127.0.0.1", PORT), partial(AppHandler, directory=str(ROOT))); app.daemon_threads = True
threading.Thread(target=app.serve_forever, daemon=True).start()
time.sleep(0.5)
errs, cons = [], []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_init_script(TOASTLOG_INIT)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: cons.append(m.text) if m.type == "warning" else None)
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.reload(); ready(pg)

        # ============================================================ normal case (the unsent wait shortened to 1.5 s)
        group[0] = "normal case"
        pg.evaluate(SEED_JS, 1500); pg.reload(); ready(pg); pg.wait_for_timeout(300)
        add(pg, "p1", "n1")
        ok = until(pg, lambda: "n1" in twin(pg), 3000)
        check("1. a stroke lands at once", ok, twin(pg))
        pg.wait_for_timeout(2500)
        check("2. no toast at all in the 2.5 s after (longer than the 1.5 s wait)", toasts(pg) == [], toasts(pg))
        check("3. nothing parked, no notice up, the dot saved", parked(pg) == [] and notices(pg) == {"slow": False, "parked": False} and dot(pg)[0] == "saved",
              [parked(pg), notices(pg), dot(pg)])

        # ============================================================ unsent while online
        group[0] = "unsent while online"
        offline(pg)
        add(pg, "p1", "n2")
        pg.wait_for_timeout(2500)
        check("4. offline 2.5 s with a change waiting: no toast (offline time does not count)", toasts(pg) == [] and not notices(pg)["slow"], toasts(pg))
        online(pg)
        check("5. back online: it lands", until(pg, lambda: "n2" in twin(pg), 3000), twin(pg))
        pg.evaluate("window.__pw.api.failStatus([503, 503])")   # lands on the third try, about 7 s on
        add(pg, "p2", "s1")
        ok = until(pg, lambda: toasts(pg, SLOW_WORDS), 4000)
        sl = toasts(pg, SLOW_WORDS)
        check("6. a change unsent 1.5 s while online: the toast, word for word, with one button 'OK'",
              ok and len(sl) == 1 and sl[0]["button"] == "OK" and showing(pg), toasts(pg))
        check("7. ... while it still waits in the queue, not parked (503 is tried again)",
              [ids_of(o) for o in queued(pg)] == [["s1"]] and parked(pg) == [], [queued(pg), parked(pg)])
        pg.wait_for_timeout(3200)
        check("8. still up 3.2 s later (it stays until tapped), and shown once", showing(pg) and len(toasts(pg, SLOW_WORDS)) == 1, toasts(pg))
        ok = until(pg, lambda: "s1" in twin(pg), 9000)
        check("9. it lands on a retry", ok, twin(pg))
        check("10. the notice clears once the queue is empty", until(pg, lambda: not notices(pg)["slow"], 1500), notices(pg))
        pg.click("#toast .toastAct")
        check("11. a tap on OK hides it", until(pg, lambda: not showing(pg), 1000))
        pg.evaluate("window.__pw.api.failStatus([500, 500])")
        add(pg, "p2", "s2")
        ok = until(pg, lambda: len(toasts(pg, SLOW_WORDS)) == 2, 4000)
        check("12. cleared and come back: shown once more (two in all)", ok, toasts(pg))
        until(pg, lambda: "s2" in twin(pg), 9000)
        check("13. ... and that change lands too", "s2" in twin(pg), twin(pg))
        check("14. no parked toast in this group", toasts(pg, PARK_WORDS) == [], toasts(pg))

        # ============================================================ not refused: tried again, never parked
        group[0] = "not refused"
        pg.evaluate(SEED_JS, 0); pg.reload(); ready(pg); pg.wait_for_timeout(300)
        n0 = len(toasts(pg))
        for s in [0, 401, 408, 429, 500, 503]:
            sid = f"x{s}"
            pg.evaluate(f"window.__pw.api.failStatus([{s}])")
            add(pg, "p2", sid)
            pg.wait_for_timeout(400)
            mid = [queued(pg), parked(pg)]
            ok = until(pg, lambda: sid in twin(pg), 5000)
            label = "no answer (0, as the not-signed-in guard and a lost connection give)" if s == 0 else f"HTTP {s}"
            check(f"15. {label}: still queued (not parked) after the failure, then lands on the retry",
                  [ids_of(o) for o in mid[0]] == [[sid]] and mid[1] == [] and ok, mid)
        pg.evaluate("window.__pw.api.failNext(1)")             # the twin's plain dropped connection (no status at all)
        add(pg, "p2", "xf")
        ok = until(pg, lambda: "xf" in twin(pg), 5000)
        check("16. a failed write with no status at all: retried, lands", ok and parked(pg) == [], parked(pg))
        check("17. nothing kept on the device, no parked notice, no toast", kept(pg) == [] and not notices(pg)["parked"] and len(toasts(pg)) == n0,
              [kept(pg), notices(pg), toasts(pg)[n0:]])

        # ============================================================ parked
        group[0] = "parked"
        pg.evaluate(SEED_JS, 0); pg.reload(); ready(pg); pg.wait_for_timeout(300)
        cons.clear()
        offline(pg)
        add(pg, "p1", "a1"); pg.wait_for_timeout(350)
        add(pg, "p2", "a2"); pg.wait_for_timeout(350)
        add(pg, "p2", "a3"); pg.wait_for_timeout(100)
        check("18. set-up: three changes queued offline (a1 on page 1 first)", [ids_of(o) for o in queued(pg)] == [["a1"], ["a2"], ["a3"]], queued(pg))
        refuse_ids(pg, ["a1"], 400)
        online(pg)
        ok = until(pg, lambda: "a2" in twin(pg) and "a3" in twin(pg), 4000)
        settle(pg)
        check("19. the head (a1) is refused with 400: the two behind it land", ok and "a1" not in twin(pg), twin(pg))
        p = parked(pg)
        check("20. a1 is parked, the queue is empty", [ids_of(o) for o in p] == [["a1"]] and p[0]["page_id"] == "p1" and queued(pg) == [], [p, queued(pg)])
        k = kept(pg)
        check("21. it is kept on the device: one queue record, parked: true, holding a1",
              len(k) == 1 and k[0].get("parked") is True and ids_of(k[0]) == ["a1"], k)
        check("22. the dot is red, its title the plain words", dot(pg) == ["refused", DOT_WORDS], dot(pg))
        pt = toasts(pg, PARK_WORDS)
        check("23. the parked toast, word for word, with one button 'OK', up", len(pt) == 1 and pt[0]["button"] == "OK" and showing(pg), toasts(pg))
        w = [c for c in cons if "refused a change to page p1" in c]
        check("24. one console line, with the status", len(w) == 1 and "HTTP 400" in w[0], w)
        pg.evaluate("window.__pw.store.reconcile(['p1'])"); settle(pg); pg.wait_for_timeout(200)
        check("25. a read of page 1 from the database keeps her parked stroke on the device",
              pg.evaluate("window.__pw.store.load('p1').some((r) => r.id === 'a1')"), pg.evaluate("window.__pw.store.load('p1')"))

        # ============================================================ each refusal parks
        group[0] = "each refusal"
        refused = ["a1"]
        for s in [403, 404, 409, 422]:
            sid = f"b{s}"
            refused.append(sid)
            refuse_ids(pg, refused, s)
            add(pg, "p2", sid)
            ok = until(pg, lambda: any(ids_of(o) == [sid] for o in parked(pg)), 3000)
            check(f"26. HTTP {s}: parked at once, not in the database", ok and sid not in twin(pg), [parked(pg), twin(pg)])
        pg.evaluate("window.__pw.api.refuseNext(1)")            # the twin's own row-level security refusal (42501, 403)
        add(pg, "p2", "r1")
        ok = until(pg, lambda: any(ids_of(o) == ["r1"] for o in parked(pg)), 3000)
        check("27. the twin's RLS refusal (42501, HTTP 403): parked", ok, parked(pg))
        pg.wait_for_timeout(350)
        add(pg, "p2", "ok1")
        check("28. a change after them all lands", until(pg, lambda: "ok1" in twin(pg), 3000), twin(pg))
        check("29. six parked, the parked toast still shown only once", len(parked(pg)) == 6 and len(toasts(pg, PARK_WORDS)) == 1,
              [len(parked(pg)), toasts(pg)])
        refuse_ids(pg, refused, 400)

        # ============================================================ held behind a parked change
        group[0] = "held behind"
        cons.clear()
        erase(pg, "p1", "a1")
        settle(pg)
        p = parked(pg)
        check("30. erasing the parked stroke a1: that change waits with it (parked, not sent)",
              p and p[-1]["removed"] == ["a1"] and p[-1]["added"] == [] and len(p) == 7, p)
        check("31. ... with one console line saying why", len([c for c in cons if "touches a refused change" in c]) == 1, cons[-2:])
        pg.wait_for_timeout(350)
        add(pg, "p1", "d1")
        check("32. a new stroke on the same page that does not touch a1 still lands", until(pg, lambda: "d1" in twin(pg), 3000), twin(pg))
        k0 = kept(pg)
        pg.evaluate("window.__pw.store.unqueue('p1')"); settle(pg)
        check("33. unqueue of page 1 (a page deleted on the server) leaves every parked change kept", kept(pg) == k0, [len(kept(pg)), len(k0)])
        check("34. seven kept on the device, all parked, in the order they were made",
              len(k0) == 7 and all(r.get("parked") for r in k0) and [r["key"] for r in k0] == sorted(r["key"] for r in k0), k0)

        # ============================================================ kept through a reload, tried again at start
        group[0] = "kept through a reload"
        before = {r["key"]: r for r in k0}
        cons.clear()
        pg.evaluate("window.__pw.api.refuseNext(0)")
        pg.reload(); ready(pg)
        ok = until(pg, lambda: "r1" in twin(pg) and len(parked(pg)) == 6, 6000)
        settle(pg)
        check("35. at start every parked change is tried: r1 (refused only once) lands now", ok, [twin(pg), len(parked(pg))])
        check("36. the other six are tried and parked again, oldest first",
              [ids_of(o) for o in parked(pg)] == [["a1"], ["b403"], ["b404"], ["b409"], ["b422"], ["a1"]], parked(pg))
        k1 = kept(pg)
        r1key = [key for key, r in before.items() if ids_of(r) == ["r1"]]
        check("37. the device keeps exactly what it kept before, less the one that landed (same keys, same contents)",
              {r["key"]: r for r in k1} == {key: r for key, r in before.items() if key not in r1key}, [len(k1), len(before)])
        check("38. console: the refused ones were tried at this start", len([c for c in cons if "refused a change to page" in c]) == 5, len(cons))
        check("39. the parked toast once at this start, the dot red", len(toasts(pg, PARK_WORDS)) == 1 and dot(pg)[0] == "refused", [toasts(pg), dot(pg)])
        pg.evaluate("window.dispatchEvent(new Event('focus'))"); pg.wait_for_timeout(400)
        check("40. focus alone does not try them again (still six)", len(parked(pg)) == 6)

        # ============================================================ tried again on online
        group[0] = "tried on online"
        refuse_ids(pg, [x for x in refused if x != "b403"], 400)
        offline(pg); online(pg)
        ok = until(pg, lambda: "b403" in twin(pg), 4000)
        settle(pg)
        check("41. back online: the parked ones are tried; b403 (no longer refused) lands", ok, twin(pg))
        check("42. it leaves the parked list; the other five stay", [ids_of(o) for o in parked(pg)] == [["a1"], ["b404"], ["b409"], ["b422"], ["a1"]], parked(pg))
        k2 = kept(pg)
        check("43. the device lost only b403's record", {r["key"] for r in k2} == {r["key"] for r in k1 if ids_of(r) != ["b403"]}, [len(k2), len(k1)])
        check("44. no second parked toast (the list never cleared)", len(toasts(pg, PARK_WORDS)) == 1, toasts(pg))

        # ============================================================ tried at start: all land, in order
        group[0] = "tried at start"
        refuse_ids(pg, [])
        pg.reload(); ready(pg)
        ok = until(pg, lambda: parked(pg) == [] and queued(pg) == [] and all(x in twin(pg) for x in ["b404", "b409", "b422"]), 6000)
        settle(pg)
        check("45. the next start: every parked change lands, the list is empty", ok, [parked(pg), queued(pg)])
        check("46. ... in her order: a1 went up, then her erase of a1 (a1 not in the database, d1 still is)",
              "a1" not in twin(pg) and "d1" in twin(pg), twin(pg))
        check("47. nothing kept on the device any more, no notice up, the dot saved",
              kept(pg) == [] and notices(pg) == {"slow": False, "parked": False} and dot(pg)[0] == "saved", [kept(pg), notices(pg), dot(pg)])
        check("48. no parked toast at this start", toasts(pg, PARK_WORDS) == [], toasts(pg))
        ctx.close()

        # ============================================================ persistent storage, asked once per device
        group[0] = "persistent storage"
        for persisted, want in [(False, 1), (True, 0)]:
            c2 = b.new_context(viewport={"width": 1280, "height": 800})
            c2.add_init_script(PERSIST_INIT)
            if persisted: c2.add_init_script("localStorage.setItem('t.persisted', '1')")
            p2 = c2.new_page()
            p2.on("pageerror", lambda e: errs.append(str(e)))
            p2.goto(LOCAL); ready(p2); p2.wait_for_timeout(500)
            n1 = p2.evaluate("Number(localStorage.getItem('t.persist') || 0)")
            p2.reload(); ready(p2); p2.wait_for_timeout(500)
            p2.reload(); ready(p2); p2.wait_for_timeout(500)
            n3 = p2.evaluate("Number(localStorage.getItem('t.persist') || 0)")
            flag = p2.evaluate("localStorage.getItem('pw.persist.asked')")
            if not persisted:
                check("49. not yet persisted: persist() asked at the first start, not at the next two", n1 == 1 and n3 == 1 and flag == "1", [n1, n3, flag])
            else:
                check("50. already persisted: persist() never asked", n1 == 0 and n3 == 0, [n1, n3, flag])
            c2.close()

        # ============================================================ house rules
        group[0] = "house rules"
        c3 = b.new_context(); p3 = c3.new_page(); p3.goto(LOCAL); ready(p3)
        p3.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        keys = p3.evaluate("caches.keys()")
        check(f"51. cache is {VERSION}", VERSION in keys, keys)
        c3.close()
        raw = (ROOT / "sw.js").read_bytes()
        check("52. sw.js has no BOM", not raw.startswith(b"\xef\xbb\xbf"))
        srcs = "".join((ROOT / p).read_text(encoding="utf-8") for p in
                       ["sw.js", "js/store.js", "js/app.js", "js/api.js", "js/local-backend.js", "tests/test_parked.py"])
        check("53. no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("54. no page errors", not errs, errs[:3])
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
