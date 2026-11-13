# PenWorks pw-v9f checks: headless Playwright (Python), same style as tests/test_cut.py.
# Run: python -E -P tests/test_pw9f.py      (local mode only: ?local=1, Supabase is never touched)
# Her three asks, 11 Nov 2026:
#   1. the page number ON the page ("1 / 4", bottom-right, grows with the zoom, never printed); the desk's corner number gone
#   2. ink moves across pages: a selection dragged with the pen and lifted over another page goes to that page, one undo step
#   3. Copy clears the selection (the Samsung Notes way); the clipboard still holds it, "Copied." still shows
import sys, subprocess, time, pathlib, re, math
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8829
BASE = f"http://127.0.0.1:{PORT}/"
LOCAL = BASE + "?local=1"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

SEED_JS = """() => {
  localStorage.clear();
  const t = '2026-11-11T08:00:00Z', P = (id, n, k) => ({ id, note_id: n, position: k, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t });
  const N = (id, name, u) => ({ id, folder_id: 'f1', name, pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: u });
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'V9f', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [N('n1', 'Three', '2026-11-11T08:02:00Z')],
    pages: [P('p1', 'n1', 0), P('p2', 'n1', 1), P('p3', 'n1', 2)] }));
}"""
STROKES_JS = "(id) => window.__pw.ink.strokesOf(id)"
SEL_JS = "() => window.__pw.ink.selection()"
PUT_JS = "([pid, recs]) => import('./js/ink.js').then(m => m.put(pid, recs))"
NOS_JS = """() => [...document.querySelectorAll('#stack .sheet')].map(s => { const n = s.querySelector(':scope > .pageNo');
  if (!n) return null; const r = n.getBoundingClientRect(), b = s.getBoundingClientRect(), st = getComputedStyle(n);
  const kids = [...s.children], ni = kids.indexOf(n), ink = s.querySelector(':scope > svg.ink');
  return { text: n.textContent, inside: r.left >= b.left && r.right <= b.right && r.top >= b.top && r.bottom <= b.bottom,
           right: b.right - r.right, bottom: b.bottom - r.bottom, h: r.height, shown: r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden',
           under: ink ? kids.indexOf(ink) > ni : null, pe: st.pointerEvents }; })"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def strokes(pg, pid): return pg.evaluate(STROKES_JS, pid)
def ids(pg, pid): return sorted(s["id"] for s in strokes(pg, pid))
def sel(pg): return pg.evaluate(SEL_JS)
def nrow(pg, name): return pg.locator(".nrow").filter(has=pg.locator(".name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def open_note(pg, name):
    nrow(pg, name).click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(120)
def zoom(pg): return float(pg.evaluate("document.getElementById('stack').dataset.zoom"))
def screen(pg, i, x, y):
    b = pg.locator(f"#stack .sheet[data-index='{i}']").bounding_box(); z = zoom(pg)
    return b["x"] + x * z, b["y"] + y * z
def drag_page(pg, i, a, b, steps=10):
    sx, sy = screen(pg, i, *a); pg.mouse.move(sx, sy); pg.mouse.down()
    tx, ty = screen(pg, i, *b); pg.mouse.move(tx, ty, steps=steps); pg.mouse.up(); pg.wait_for_timeout(60)
def U(pg): return pg.evaluate("window.__pw.S.hist[window.__pw.S.openNote] ? window.__pw.S.hist[window.__pw.S.openNote].u.length : 0")
def undo(pg): pg.click("#undoBtn"); pg.wait_for_timeout(40)
def redo(pg): pg.click("#redoBtn"); pg.wait_for_timeout(40)
def tool(pg, t): pg.click(f"#tool-{t}"); pg.wait_for_timeout(20)
def fresh(b, w=700, h=1500, **kw):
    ctx = b.new_context(viewport={"width": w, "height": h}, **kw)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg)
    pg.evaluate(SEED_JS); pg.reload(); ready(pg)
    return ctx, pg, errs
ST = {"colour": "#000000", "width": 2, "dash": "solid", "opacity": 1}
def rec(rid, pid, pts, k=0): return {"id": rid, "page_id": pid, "seq": int(time.time() * 1000) + k, "kind": "pen", "style": dict(ST), "data": {"points": pts}}
def close(g, w, tol=1.0): return len(g) == len(w) and all(len(a) == len(c) and all(abs(p[0]-q[0]) <= tol and abs(p[1]-q[1]) <= tol for p, q in zip(a, c)) for a, c in zip(g, w))
def pts_of(pg, pid): return sorted(tuple(map(tuple, s["data"]["points"])) for s in strokes(pg, pid))

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # ------------------------------------------------------------ 1. the page number on the page
        group[0] = "page number"
        ctx, pg, errs = fresh(b)
        open_note(pg, "Three")
        nos = pg.evaluate(NOS_JS)
        check("every page has its number: 1 / 3, 2 / 3, 3 / 3", [n and n["text"] for n in nos] == ["1 / 3", "2 / 3", "3 / 3"], nos)
        check("each number is shown, inside its page, in the bottom-right corner (within 30 screen px of both edges)",
              all(n and n["shown"] and n["inside"] and 0 <= n["right"] <= 30 and 0 <= n["bottom"] <= 30 for n in nos), nos)
        check("each number sits UNDER the ink layer and never takes the pen", all(n["under"] is True and n["pe"] == "none" for n in nos), nos)
        h0 = nos[0]["h"]; z0 = zoom(pg)
        pg.evaluate("() => window.__pw.page && window.__pw.page.zoomBy ? window.__pw.page.zoomBy(2) : null")
        pg.mouse.move(350, 400); pg.keyboard.down("Control"); pg.mouse.wheel(0, -400); pg.keyboard.up("Control"); pg.wait_for_timeout(300)
        z1 = zoom(pg); h1 = pg.evaluate(NOS_JS)[0]["h"]
        check("zoomed in, the number grows with the page", z1 > z0 * 1.2 and h1 > h0 * 1.15, [z0, z1, h0, h1])
        cnt = pg.evaluate("() => { const c = document.getElementById('counter'); return c ? getComputedStyle(c).display : 'gone'; }")
        check("the desk's corner number is gone", cnt in ("none", "gone"), cnt)
        pdfsrc = (ROOT / "js" / "pdfout.js").read_text(encoding="utf-8")
        check("the PDF export never draws the screen's number (pdfout.js builds from the records, no .pageNo, no .sheet)",
              "pageNo" not in pdfsrc and ".sheet" not in pdfsrc)
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ 3. Copy clears the selection
        group[0] = "copy clears"
        ctx, pg, errs = fresh(b)
        open_note(pg, "Three")
        pg.evaluate(PUT_JS, ["p1", [rec("a", "p1", [[150, 200], [250, 220], [350, 200]], 1),
                                    rec("b", "p1", [[150, 280], [250, 300], [350, 280]], 2)]])
        tool(pg, "select")
        drag_page(pg, 1, (120, 170), (380, 330))
        check("a box around both: both selected", sel(pg) and sorted(sel(pg)["ids"]) == ["a", "b"], sel(pg))
        u0 = U(pg)
        pg.locator(".selChips .chip[data-act='copy']").click(); pg.wait_for_timeout(60)
        check("after Copy nothing is selected and the chips are gone",
              sel(pg) is None and pg.evaluate("() => !document.querySelector('.selChips') || !document.querySelector('.selChips').isConnected"), sel(pg))
        check("the clipboard holds it", pg.evaluate("window.__pw.ink.hasClip()") is True)
        toast = pg.evaluate("() => { const t = document.getElementById('toast'); return t ? t.textContent : ''; }")
        check("the toast still says Copied.", "Copied." in toast, toast)
        check("the page is unchanged and no undo step", ids(pg, "p1") == ["a", "b"] and U(pg) == u0, [ids(pg, "p1"), U(pg), u0])
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ 2. ink moves across pages
        group[0] = "across pages"
        ctx, pg, errs = fresh(b)
        open_note(pg, "Three")
        A = [[150, 1000], [250, 1020], [350, 1000]]; B = [[150, 1060], [250, 1080], [350, 1060]]; C = [[150, 200], [250, 220], [350, 200]]
        pg.evaluate(PUT_JS, ["p1", [rec("a", "p1", A, 1), rec("b", "p1", B, 2), rec("c", "p1", C, 3)]])
        pg.evaluate(PUT_JS, ["p2", [rec("d", "p2", [[500, 500], [600, 520]], 4)]])
        tool(pg, "select")
        drag_page(pg, 1, (120, 970), (380, 1100))
        check("a and b selected on page 1", sel(pg) and sel(pg)["page"] == "p1" and sorted(sel(pg)["ids"]) == ["a", "b"], sel(pg))
        u0 = U(pg)
        sx, sy = screen(pg, 1, 250, 1040); tx, ty = screen(pg, 2, 250, 200)
        check("page 2's drop spot is on screen", 0 < ty < 1500, ty)
        pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.move(tx, ty, steps=14); pg.wait_for_timeout(40)
        mv = pg.evaluate("""() => { const s = document.querySelector('#stack .sheet[data-id="p1"]'), v = s.querySelector('svg.ink');
          return { moving: s.classList.contains('moving'), ov: getComputedStyle(v).overflow, z: getComputedStyle(s).zIndex }; }""")
        check("while it moves, page 1 sits on top and its ink is not clipped", mv["moving"] and mv["ov"] == "visible" and mv["z"] == "3", mv)
        pg.mouse.up(); pg.wait_for_timeout(80)
        mv2 = pg.evaluate("""() => document.querySelector('#stack .sheet[data-id="p1"]').classList.contains('moving')""")
        check("after the lift page 1 is back to normal", mv2 is False)
        check("page 1 keeps only c", ids(pg, "p1") == ["c"], ids(pg, "p1"))
        p2 = strokes(pg, "p2")
        news = [s for s in p2 if s["id"] != "d"]
        check("page 2 has d plus two new strokes with fresh ids", len(p2) == 3 and len(news) == 2 and not {"a", "b"} & {s["id"] for s in news}, [s["id"] for s in p2])
        dy = 200 - 1040
        want = sorted(tuple((x, y + dy) for x, y in P) for P in (A, B))
        got = sorted(tuple(map(tuple, s["data"]["points"])) for s in news)
        check("they land where the pen took them (grab spot -> drop spot, same shape, within 1 page px)", close(got, want), [got, want])
        check("the new strokes carry page_id p2 and sit above d", all(s["page_id"] == "p2" for s in news) and min(s["seq"] for s in news) > [s for s in p2 if s["id"] == "d"][0]["seq"])
        check("they stay selected, now on page 2", sel(pg) and sel(pg)["page"] == "p2" and sorted(sel(pg)["ids"]) == sorted(s["id"] for s in news), sel(pg))
        check("ONE undo step", U(pg) == u0 + 1, [U(pg), u0])
        undo(pg)
        check("undo: a, b back on page 1, page 2 only d", ids(pg, "p1") == ["a", "b", "c"] and ids(pg, "p2") == ["d"], [ids(pg, "p1"), ids(pg, "p2")])
        check("undo: a and b exactly where they were", pts_of(pg, "p1") == sorted([tuple(map(tuple, A)), tuple(map(tuple, B)), tuple(map(tuple, C))]))
        redo(pg)
        check("redo: on page 2 again", ids(pg, "p1") == ["c"] and len(ids(pg, "p2")) == 3, [ids(pg, "p1"), ids(pg, "p2")])
        pg.wait_for_timeout(1500)
        pg.reload(); ready(pg); open_note(pg, "Three")
        check("after a reload page 1 has c only and page 2 has three strokes (it saved)", len(strokes(pg, "p1")) == 1 and len(strokes(pg, "p2")) == 3,
              [len(strokes(pg, "p1")), len(strokes(pg, "p2"))])
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ 2b. dropped in the gap or on its own page: stays on its own page
        group[0] = "stays home"
        ctx, pg, errs = fresh(b)
        open_note(pg, "Three")
        pg.evaluate(PUT_JS, ["p1", [rec("a", "p1", A, 1), rec("b", "p1", B, 2)]])
        tool(pg, "select")
        drag_page(pg, 1, (120, 970), (380, 1100))
        u0 = U(pg)
        b1 = pg.locator("#stack .sheet[data-index='1']").bounding_box(); b2 = pg.locator("#stack .sheet[data-index='2']").bounding_box()
        gy = (b1["y"] + b1["height"] + b2["y"]) / 2
        sx, sy = screen(pg, 1, 250, 1040)
        pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.move(sx, gy, steps=10); pg.mouse.up(); pg.wait_for_timeout(80)
        check("lifted in the gap between pages: a and b stay on page 1 (moved, same ids), page 2 empty, one step",
              ids(pg, "p1") == ["a", "b"] and ids(pg, "p2") == [] and U(pg) == u0 + 1, [ids(pg, "p1"), ids(pg, "p2"), U(pg)])
        undo(pg)
        drag_page(pg, 1, (120, 970), (380, 1100))
        u0 = U(pg)
        drag_page(pg, 1, (250, 1040), (250, 600))
        got = sorted(tuple(map(tuple, s["data"]["points"])) for s in strokes(pg, "p1"))
        want = sorted(tuple((x, y - 440) for x, y in P) for P in (A, B))
        check("moved within its own page: exactly as before (same ids, moved within 1 page px, one step)", ids(pg, "p1") == ["a", "b"] and close(got, want) and U(pg) == u0 + 1, [got, want])
        check("no page errors", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ the cache
        group[0] = "cache"
        swt = (ROOT / "sw.js").read_text(encoding="utf-8")
        check("sw.js: CACHE pw-v9g and the pw-v9f version line", 'const CACHE = "pw-v9g";' in swt and "   pw-v9f (11 Nov): " in swt)
        b.close()
finally:
    srv.terminate()

bad = [r for r in res if not r[2]]
cur = None
for g, n, ok, info in res:
    if g != cur: print(f"\n== {g}"); cur = g
    print(("  ok  " if ok else "  FAIL") + " " + n + ("" if ok else f"   [{info}]"))
print(f"\n{len(res) - len(bad)}/{len(res)} passed")
sys.exit(1 if bad else 0)
