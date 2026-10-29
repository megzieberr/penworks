# PenWorks U3c checks: page bookmarks in the pages.bookmark column (migration 0004), and the tray state following her
# across devices through profiles.settings (newer wins, by its tray_at stamp). Headless Playwright (Python), the
# harness of tests/test_u3a.py.
# Run: python tests/test_u3c.py          (local mode only: ?local=1, the localStorage twin stands in for Supabase)
#      python tests/test_u3c.py --live   (adds the live group: the test login from PW_TEST_USER / PW_TEST_PASS or the
#                                         gitignored .env, never printed; it deletes every row it makes and puts the
#                                         profile's settings back as it found them)
# Local groups: a bookmark from the page menu reaches the row and survives a reload, never moving the note's "last
# edited"; the one-time take-over of the pw-v4r device keys; a copied bookmarked page pastes bookmarked; undo of a
# delete brings the bookmark back; the tray state goes up a second after a change and the newer copy wins at start;
# a failed tray save lands on the retry; the twin's "last edited" rules for bookmark, snapshot and binning patches.
import sys, os, subprocess, time, pathlib, re, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8783
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"
LIVE = "--live" in sys.argv

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

NOTE_AT = "2026-10-26T10:02:00Z"
SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-10-26T10:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'U3c', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Marks', '2026-10-26T10:02:00Z'), N('n2', 'Other', '2026-10-26T10:01:00Z')],
    pages: [P('a1', 'n1', 0), P('a2', 'n1', 1), P('a3', 'n1', 2), P('o1', 'n2', 0)] }));
}"""
ROW_JS = "async (id) => { await window.__pw.idle(); const r = (await window.__pw.api.loadAll()).pages.find(p => p.id === id); return r ? r.bookmark : null; }"
NOTE_JS = "async (id) => { await window.__pw.idle(); const r = (await window.__pw.api.loadAll()).notes.find(n => n.id === id); return r ? r.updated_at : null; }"
PAGES_JS = """async (nid) => { await window.__pw.idle(); return (await window.__pw.api.loadAll()).pages.filter(p => p.note_id === nid && !p.deleted_at)
  .sort((a, b) => a.position - b.position).map(p => [p.id, p.bookmark]); }"""
KEYS_JS = "() => Object.keys(localStorage).filter(k => k.startsWith('pw.bookmark.')).sort()"
SHEETS_JS = "() => [...document.querySelectorAll('#stack .sheet')].map(s => !!s.querySelector(':scope > .bookmarkTab'))"
THUMBS_JS = "() => [...document.querySelectorAll('#plThumbs .thumbP')].map(t => [+t.dataset.index, !!t.querySelector('.paper > .bookmarkTab')])"
PROFILE_JS = "() => window.__pw.api.profile()"
LOCALTRAY_JS = "() => JSON.parse(localStorage.getItem('pw.tools') || 'null')"
SW_JS = "() => [...document.querySelectorAll('#tray .colours .sw')].map(s => s.dataset.colour)"
HERS = ["#2CB05F", "#37D366", "#0D0DFF", "#FF0C84", "#FF7043", "#A83AFF", "#FFC107", "#00BCD5", "#04878F", "#FF00FF", "#FF3636", "#000000", "#808080"]

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def idle(pg): pg.evaluate("window.__pw.idle()"); pg.wait_for_timeout(40)
def row(pg, pid): return pg.evaluate(ROW_JS, pid)
def note_at(pg, nid): return pg.evaluate(NOTE_JS, nid)
def menu_items(pg): return [t_.strip() for t_ in pg.locator("#menu button[role='menuitem']").all_inner_texts()]
def menu_click(pg, label): pg.get_by_role("menuitem", name=label, exact=True).click(); pg.wait_for_timeout(80)
def menu(pg, label): pg.locator("#menu button", has_text=re.compile("^" + re.escape(label) + "$")).first.click()
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def frow(pg, name): return pg.locator(".frow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def type_name(pg, text):
    inp = pg.locator("input.rename"); inp.wait_for(); inp.fill(text); inp.press("Enter")
def back(pg): pg.click("#backBtn"); pg.wait_for_selector("#listView:not([hidden])")
def open_note(pg, name):
    if pg.locator("#noteView").is_visible():
        if pg.evaluate("(window.__pw.S.notes.find(n => n.id === window.__pw.S.openNote) || {}).name") == name: return
        back(pg)
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_selector("#stack .sheet[data-index='1']"); pg.wait_for_timeout(80)
def open_list(pg):
    if pg.locator("#pageList").is_hidden(): pg.click("#listBtn")
    pg.wait_for_selector("#pageList:not([hidden])")
def close_list(pg):
    if not pg.locator("#pageList").is_hidden(): pg.click("#plClose")
def go_page(pg, i):
    open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(); pg.wait_for_timeout(80); close_list(pg)
def page_menu(pg, i):
    go_page(pg, i); pg.click("#noteMore"); pg.wait_for_timeout(40); return menu_items(pg)
def thumb_menu(pg, i, label):
    open_list(pg); pg.locator(f"#plThumbs .thumbP[data-index='{i}']").click(button="right"); pg.wait_for_timeout(60); menu_click(pg, label)
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(60); idle(pg)
def tray(pg): return pg.evaluate("window.__pw.tray()")
def centre(pg, sel):
    b = pg.locator(sel).first.bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
def sw_sel(c): return f"#tray .sw[data-colour='{c}']"
def pitch(pg):
    a, b = pg.locator("#tray .colours .sw").nth(0).bounding_box(), pg.locator("#tray .colours .sw").nth(1).bounding_box()
    return b["y"] - a["y"]
def pen_panel(pg):
    if tray(pg)["tool"] != "pen": pg.click("#tool-pen"); pg.wait_for_timeout(40)
    if pg.locator("#toolPanel").is_hidden(): pg.click("#tool-pen"); pg.wait_for_timeout(40)
    pg.wait_for_selector("#toolPanel:not([hidden])")
def width_bigger(pg, n=1):
    pen_panel(pg)
    for _ in range(n): pg.click("#toolPanel button[aria-label='Width bigger']"); pg.wait_for_timeout(30)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(30)
def until(pg, fn, ms=3000, step=50):
    t = time.time() + ms / 1000
    while True:
        v = fn()
        if v or time.time() > t: return v
        pg.wait_for_timeout(step)
def tray_obj(width, order, colour="#000000"):
    return {"tool": "pen", "pen": {"colour": colour, "width": width, "dash": "solid"},
            "highlighter": {"colour": "#FFC107", "width": 18, "opacity": 0.4}, "restyle": {"colour": colour}, "order": order, "spec": None}
def set_db(pg, tray_, at): pg.evaluate("([t, at]) => window.__pw.api.setSettings({ tray: t, tray_at: at })", [tray_, at])
def set_local(pg, tray_, at=None):
    v = dict(tray_)
    if at: v["tray_at"] = at
    pg.evaluate("(v) => localStorage.setItem('pw.tools', JSON.stringify(v))", v)

def creds():
    u, p = os.environ.get("PW_TEST_USER"), os.environ.get("PW_TEST_PASS")
    env = ROOT / ".env"
    if (not u or not p) and env.exists():
        kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        u, p = kv.get("PW_TEST_USER", "").strip(), kv.get("PW_TEST_PASS", "").strip()
    return u, p

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate(SEED_JS); pg.reload(); ready(pg)

        # ------------------------------------------------------------ the bookmark is the row's column
        group[0] = "bookmark row"
        open_note(pg, "Marks")
        check("set-up: every row says bookmark false (the twin's default), the note's last edited is the seed's",
              pg.evaluate(PAGES_JS, "n1") == [["a1", None], ["a2", None], ["a3", None]] or pg.evaluate(PAGES_JS, "n1") == [["a1", False], ["a2", False], ["a3", False]],
              pg.evaluate(PAGES_JS, "n1"))
        check("the page records in memory say bookmark: false (a row without the field reads false)",
              pg.evaluate("window.__pw.S.pages.filter(p => p.note_id === 'n1').map(p => p.bookmark)") == [False, False, False])
        u0 = note_at(pg, "n1")
        items = page_menu(pg, 2); menu_click(pg, "Bookmark"); idle(pg)
        check("page 2's menu: Bookmark; tapped, the row says true", "Bookmark" in items and row(pg, "a2") is True, [items, row(pg, "a2")])
        check("the note's updated_at did not move (a bookmark is not an edit)", note_at(pg, "n1") == u0 == NOTE_AT, [u0, note_at(pg, "n1")])
        check("no pw.bookmark.* key on the device", pg.evaluate(KEYS_JS) == [], pg.evaluate(KEYS_JS))
        check("not an undo step", pg.evaluate("(window.__pw.S.hist['n1'] || { u: [] }).u.length") == 0)
        pg.reload(); ready(pg); open_note(pg, "Marks")
        check("reload: the ribbon tab is on page 2 (from the row)", pg.evaluate(SHEETS_JS) == [False, True, False], pg.evaluate(SHEETS_JS))
        open_list(pg); pg.click("#plMarks"); pg.wait_for_timeout(60)
        check("the Bookmarks filter lists page 2 only", pg.evaluate(THUMBS_JS) == [[2, True]] and pg.inner_text("#plCount") == "1 bookmarked",
              [pg.evaluate(THUMBS_JS), pg.inner_text("#plCount")])
        pg.click("#plMarks"); pg.wait_for_timeout(40); close_list(pg)
        page_menu(pg, 2); menu_click(pg, "Remove bookmark"); idle(pg)
        check("Remove bookmark: the row says false", row(pg, "a2") is False, row(pg, "a2"))
        check("the note's updated_at still did not move", note_at(pg, "n1") == NOTE_AT, note_at(pg, "n1"))
        pg.reload(); ready(pg); open_note(pg, "Marks")
        check("reload: no tab anywhere", pg.evaluate(SHEETS_JS) == [False, False, False], pg.evaluate(SHEETS_JS))
        check("no page errors (bookmark row)", not errs, errs)

        # ------------------------------------------------------------ the one-time take-over of the pw-v4r keys
        group[0] = "take-over"
        pg.evaluate("() => { localStorage.setItem('pw.bookmark.a3', '1'); localStorage.setItem('pw.bookmark.nope', '1'); }")
        pg.reload(); ready(pg); open_note(pg, "Marks"); idle(pg)
        taken = pg.evaluate("window.__pw.bookmarksTaken()")
        check("two keys handled, one bookmark set", taken == {"keys": 2, "set": 1}, taken)
        check("the live page's row is true (a3)", row(pg, "a3") is True, row(pg, "a3"))
        check("both keys are gone", pg.evaluate(KEYS_JS) == [], pg.evaluate(KEYS_JS))
        check("page 3 shows the tab", pg.evaluate(SHEETS_JS) == [False, False, True], pg.evaluate(SHEETS_JS))
        check("the note's updated_at did not move", note_at(pg, "n1") == NOTE_AT, note_at(pg, "n1"))
        pg.reload(); ready(pg); idle(pg)
        check("the next start finds nothing to take over", pg.evaluate("window.__pw.bookmarksTaken()") == {"keys": 0, "set": 0})
        check("no page errors (take-over)", not errs, errs)

        # ------------------------------------------------------------ the clipboard and undo carry the bookmark
        group[0] = "clipboard and undo"
        open_note(pg, "Marks")
        thumb_menu(pg, 3, "Copy"); close_list(pg)
        open_note(pg, "Other")
        thumb_menu(pg, 1, "Paste"); idle(pg); close_list(pg)
        rows = pg.evaluate(PAGES_JS, "n2")
        check("pasted into another note: the new page's row is bookmarked", len(rows) == 2 and rows[0][0] == "o1" and rows[1][1] is True, rows)
        check("its sheet shows the tab", pg.evaluate(SHEETS_JS) == [False, True], pg.evaluate(SHEETS_JS))
        pasted = rows[1][0] if len(rows) == 2 else None
        thumb_menu(pg, 2, "Delete"); idle(pg); close_list(pg)
        check("delete it: the row is gone", row(pg, pasted) is None, row(pg, pasted))
        undo(pg)
        check("undo: the row is back, bookmarked (the same id)", row(pg, pasted) is True, row(pg, pasted))
        check("no pw.bookmark.* key appeared", pg.evaluate(KEYS_JS) == [], pg.evaluate(KEYS_JS))
        check("no page errors (clipboard and undo)", not errs, errs)

        # ------------------------------------------------------------ the twin: what counts as an edit to the note
        group[0] = "twin last edited"
        def patch_page(patch):
            return pg.evaluate("""async (patch) => { await window.__pw.api.update('pages', ['a1'], patch); await window.__pw.idle();
              return (await window.__pw.api.loadAll()).notes.find(n => n.id === 'n1').updated_at; }""", patch)
        check("bookmark patch: note unchanged", patch_page({"bookmark": True}) == NOTE_AT)
        check("snapshot_path / snapshot_at patch: note unchanged", patch_page({"snapshot_path": "x/a1.webp", "snapshot_at": "2026-10-26T11:00:00Z"}) == NOTE_AT)
        check("deleted_at patch (binned, then back): note unchanged", patch_page({"deleted_at": "2026-10-26T11:00:00Z"}) == NOTE_AT
              and patch_page({"deleted_at": None}) == NOTE_AT)
        check("flagged patch: note unchanged", patch_page({"flagged": True}) == NOTE_AT)
        pu = pg.evaluate("async () => (await window.__pw.api.loadAll()).pages.find(p => p.id === 'a1').updated_at")
        check("the page's own updated_at did move (the row was updated)", pu != "2026-10-26T10:00:00Z", pu)
        check("background patch: the note's updated_at moves (a real edit)", patch_page({"background": "lined"}) != NOTE_AT)

        # ------------------------------------------------------------ the tray state follows her
        group[0] = "tray across devices"
        pg.evaluate(SEED_JS); pg.reload(); ready(pg); open_note(pg, "Marks")
        p0 = pg.evaluate(PROFILE_JS)
        check("the twin has a profile row: id, username, display_name, pen_colours, settings {}",
              sorted(p0.keys()) == ["display_name", "id", "pen_colours", "settings", "username"] and p0["settings"] == {}, p0)
        width_bigger(pg, 2)
        x, y = centre(pg, sw_sel("#2CB05F")); p = pitch(pg)
        pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(450); pg.mouse.move(x, y + 2 * p + 4, steps=10); pg.mouse.up(); pg.wait_for_timeout(60)
        want = [HERS[1], HERS[2], HERS[0]] + HERS[3:]
        check("set-up: pen width 3.5, Green two places down", tray(pg)["pen"]["width"] == 3.5 and pg.evaluate(SW_JS) == want, [tray(pg)["pen"], pg.evaluate(SW_JS)])
        early = pg.evaluate(PROFILE_JS)["settings"]
        pg.wait_for_timeout(2000)
        s = pg.evaluate(PROFILE_JS)["settings"]; loc = pg.evaluate(LOCALTRAY_JS)
        check("not sent at once (the second after the last change)", "tray" not in early or early["tray"]["order"] != want, early)
        check("2 s later the profile's settings.tray holds the width and the order", s.get("tray", {}).get("pen", {}).get("width") == 3.5
              and s.get("tray", {}).get("order") == want, s)
        check("settings.tray is exactly what keep() writes (tool, pen, highlighter, restyle, order, spec)",
              sorted(s.get("tray", {}).keys()) == ["highlighter", "order", "pen", "restyle", "spec", "tool"], sorted(s.get("tray", {}).keys()))
        check("settings.tray_at is set, the same stamp as the device copy", isinstance(s.get("tray_at"), str) and s.get("tray_at") == (loc or {}).get("tray_at"),
              [s.get("tray_at"), (loc or {}).get("tray_at")])
        check("no toast for the tray save", not pg.evaluate("document.getElementById('toast').classList.contains('show')"))

        # the device copy cleared: the database's state comes back
        pg.evaluate("localStorage.removeItem('pw.tools')"); pg.reload(); ready(pg)
        check("tray key cleared, reload: the tray shows the database's state (width 3.5, her order, in the DOM)",
              tray(pg)["pen"]["width"] == 3.5 and tray(pg)["order"] == want and pg.evaluate(SW_JS) == want, [tray(pg)["pen"], pg.evaluate(SW_JS)])
        loc = pg.evaluate(LOCALTRAY_JS)
        check("the device keeps it under the database's stamp", loc and loc.get("tray_at") == s.get("tray_at"), loc and loc.get("tray_at"))

        # a newer device copy against an older database copy: the device wins (and goes up)
        rev = list(reversed(HERS))
        set_db(pg, tray_obj(6, rev), "2026-10-01T00:00:00.000Z")
        set_local(pg, tray_obj(8, HERS, "#FF0C84"), "2026-10-20T00:00:00.000Z")
        pg.reload(); ready(pg)
        check("newer on the device, older in the database: the device wins (width 8, her default order, Pink)",
              tray(pg)["pen"]["width"] == 8 and tray(pg)["pen"]["colour"] == "#FF0C84" and pg.evaluate(SW_JS) == HERS, [tray(pg)["pen"], pg.evaluate(SW_JS)])
        s2 = until(pg, lambda: (lambda v: v if v.get("tray_at") == "2026-10-20T00:00:00.000Z" else None)(pg.evaluate(PROFILE_JS)["settings"]), 3000)
        check("... and the device's copy goes up under its own stamp", bool(s2) and s2["tray"]["pen"]["width"] == 8, s2)

        # a newer database copy: the database wins
        set_db(pg, tray_obj(10, rev, "#0D0DFF"), "2026-10-25T00:00:00.000Z")
        set_local(pg, tray_obj(8, HERS, "#FF0C84"), "2026-10-20T00:00:00.000Z")
        pg.reload(); ready(pg)
        check("newer in the database: the database wins (width 10, Blue, the reversed order in the DOM)",
              tray(pg)["pen"]["width"] == 10 and tray(pg)["pen"]["colour"] == "#0D0DFF" and pg.evaluate(SW_JS) == rev, [tray(pg)["pen"], pg.evaluate(SW_JS)])
        check("the pen tool carries it (ink.js got the adopted style)", pg.evaluate("window.__pw.ink.tool().tool") == "pen")

        # equal stamps: the device copy stays
        set_db(pg, tray_obj(12, HERS), "2026-10-25T00:00:00.000Z")
        pg.reload(); ready(pg)
        check("equal stamps: the device's copy stays (width 10)", tray(pg)["pen"]["width"] == 10, tray(pg)["pen"])

        # a stamp-less seed (a test's, or a copy from before U3c) beats the database
        set_db(pg, tray_obj(11, rev), "2026-10-26T00:00:00.000Z")
        set_local(pg, tray_obj(5, HERS))
        pg.reload(); ready(pg)
        check("a device copy without a stamp plus a database copy: the seed wins (width 5, her order)",
              tray(pg)["pen"]["width"] == 5 and pg.evaluate(SW_JS) == HERS, [tray(pg)["pen"], pg.evaluate(SW_JS)])
        pg.wait_for_timeout(300)
        check("... and nothing went up (the database still says width 11)", pg.evaluate(PROFILE_JS)["settings"]["tray"]["pen"]["width"] == 11)

        # a bad database copy is sanitised like a bad device copy
        pg.evaluate("localStorage.removeItem('pw.tools')")
        set_db(pg, {"tool": "eraser", "pen": {"colour": "#123456", "width": 4, "dash": "dashed"}, "order": ["#000000"], "spec": "red"}, "2026-10-26T01:00:00.000Z")
        pg.reload(); ready(pg)
        t_ = tray(pg)
        check("a bad database copy: unknown colour falls back, a bad order is ignored, width and dash stay",
              t_["tool"] == "pen" and t_["pen"] == {"colour": "#000000", "width": 4, "dash": "dashed"} and t_["order"] == HERS and t_["spec"] is None, t_)
        check("no page errors (tray)", not errs, errs)

        # ------------------------------------------------------------ a failed tray save lands on the retry
        group[0] = "tray retry"
        before = pg.evaluate(PROFILE_JS)["settings"]["tray_at"]
        pg.evaluate("window.__pw.api.failNext(1)")
        open_note(pg, "Marks")
        width_bigger(pg, 1)
        pg.wait_for_timeout(1500)
        s = pg.evaluate(PROFILE_JS)["settings"]; pend = pg.evaluate("window.__pw.trayPending()")
        check("the first try failed: the database still has the old copy, the change waits", s["tray_at"] == before and pend["next"] and pend["timer"], [s, pend])
        check("no toast, the save dot untouched (saved)", not pg.evaluate("document.getElementById('toast').classList.contains('show')")
              and pg.evaluate("document.getElementById('saveDot').dataset.state") == "saved")
        ok = until(pg, lambda: pg.evaluate(PROFILE_JS)["settings"]["tray"]["pen"]["width"] == 4.5, 4000)
        check("it lands on the retry (width 4.5)", ok, pg.evaluate(PROFILE_JS)["settings"]["tray"]["pen"])
        check("nothing left pending", pg.evaluate("window.__pw.trayPending()") == {"next": False, "busy": False, "timer": False}, pg.evaluate("window.__pw.trayPending()"))
        # offline: the retry also goes on `online`
        pg.evaluate("window.__pw.api.failNext(1)")
        width_bigger(pg, 1); pg.wait_for_timeout(1300)
        pg.evaluate("window.dispatchEvent(new Event('online'))")
        ok = until(pg, lambda: pg.evaluate(PROFILE_JS)["settings"]["tray"]["pen"]["width"] == 5, 600)
        check("a failed save goes again on `online` (before the 2 s retry)", ok, pg.evaluate(PROFILE_JS)["settings"]["tray"]["pen"])
        check("no page errors (tray retry)", not errs, errs)

        # ------------------------------------------------------------ house rules
        group[0] = "pwa and house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7c" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7c", "pw-v7c" in keys, keys)
        files = ["./js/store.js", "./js/api.js", "./js/local-backend.js", "./js/tray.js", "./js/app.js", "./sw.js"]
        srcs = {u: pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in files}
        check("no em-dashes in the changed files", all(chr(0x2014) not in v for v in srcs.values()))
        check("store.js has no bookmark helpers left", "bookmarked" not in srcs["./js/store.js"] and "keepBookmark" not in srcs["./js/store.js"]
              and "keepBookmark" not in srcs["./js/app.js"] and "store.bookmarked" not in srcs["./js/app.js"])
        check("no 'synced' wording anywhere", all("synced" not in v.lower() for v in srcs.values())
              and "synced" not in pg.evaluate("document.body.innerText").lower())
        check("nothing new in the tray (13 swatches, the spare slot, six tools and undo (pw-v6c), redo, the empty slot)",
              pg.evaluate("[...document.querySelectorAll('#tray > *')].map(e => e.className || e.id)") == ["colours", "tools", "gap", "ib", "slot"]
              and pg.locator("#tray .colours > *").count() == 14 and pg.locator("#tray .tools > *").count() == 7,
              pg.evaluate("[...document.querySelectorAll('#tray > *')].map(e => e.className || e.id)"))
        ctx.close()

        # ------------------------------------------------------------ live (Supabase), --live only
        if LIVE:
            group[0] = "live"
            user, pwd = creds()
            if not user or not pwd:
                check("test login available (PW_TEST_USER / PW_TEST_PASS)", False, "not set")
            else:
                ctx = b.new_context(viewport={"width": 1280, "height": 800})
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE); pg.wait_for_selector("#login:not([hidden])")
                pg.fill("#lu", user); pg.fill("#lp", pwd); pg.click("#loginBtn"); ready(pg)
                ids = {}; orig = None
                try:
                    prof = pg.evaluate(PROFILE_JS)
                    orig = prof and prof.get("settings")
                    check("api.profile() returns her own row", prof and prof["id"] == pg.evaluate("window.__pw.S.user.id")
                          and sorted(prof.keys()) == ["display_name", "id", "pen_colours", "settings", "username"], prof and sorted(prof.keys()))
                    at = "2026-10-26T12:00:00.000Z"
                    got = pg.evaluate("(at) => window.__pw.api.setSettings({ tray: { order: [] }, tray_at: at })", at)
                    back_ = pg.evaluate(PROFILE_JS)["settings"]
                    check("setSettings round-trips settings.tray_at", got.get("tray_at") == at and back_.get("tray_at") == at, back_)
                    pg.click("#addFolder"); type_name(pg, "U3c test")
                    frow(pg, "U3c test").locator(".more").click(); menu(pg, "New note")
                    pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
                    ids = pg.evaluate("""() => { const S = window.__pw.S, n = S.notes.find(x => x.id === S.openNote);
                      return { f: n.folder_id, n: n.id, p: S.pages.find(x => x.note_id === n.id).id }; }""")
                    idle(pg)
                    n0 = note_at(pg, ids["n"])
                    pg.evaluate("(p) => window.__pw.api.setBookmark(p, true)", ids["p"])
                    check("a page made through the app takes setBookmark(true) and reads back true", row(pg, ids["p"]) is True, row(pg, ids["p"]))
                    check("the note's updated_at did not move (0004's trigger)", note_at(pg, ids["n"]) == n0, [n0, note_at(pg, ids["n"])])
                finally:
                    idle(pg)
                    if ids:
                        left = pg.evaluate("""async (ids) => {
                          const a = window.__pw.api;
                          await a.removeSnapshots([window.__pw.S.user.id + '/' + ids.p + '.webp']).catch(() => {});
                          await a.remove('pages', [ids.p]); await a.remove('notes', [ids.n]); await a.remove('folders', [ids.f]);
                          const d = await a.loadAll();
                          return [d.folders.filter(r => r.id === ids.f).length, d.notes.filter(r => r.id === ids.n).length, d.pages.filter(r => r.id === ids.p).length]; }""", ids)
                        check("every row the test made is gone", left == [0, 0, 0], left)
                    if orig is not None:
                        put = pg.evaluate("(o) => window.__pw.api.setSettings(o, true)", orig)
                        check("the profile's settings are back as the test found them", put == orig, [put, orig])
                check("no page errors (live)", not errs, errs)
                ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
if not LIVE: print("live group skipped (run with --live)")
sys.exit(0 if all(r[2] for r in res) else 1)
