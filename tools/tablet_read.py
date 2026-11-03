# PenWorks on her TABLET, read over the cable (3 Nov 2026, the washy-look investigation). How ANY session reads the
# app's own counters off her tablet with no code change:
#   1. tablet plugged in, USB debugging on (authorised since 1 Nov 2026), PenWorks open in Chrome / the installed app
#   2. adb forward tcp:9222 localabstract:chrome_devtools_remote      (adb: winget's Google.PlatformTools)
#   3. python tools/tablet_read.py        (Playwright connects over CDP; nothing is changed on the tablet)
#   4. adb forward --remove-all when done. The screen must be ON (a dozing tablet draws no frames).
# A real screen grab: adb exec-out screencap -p > screen.png (what the panel shows, canvases and all).
# Read PenWorks' own counters off the tablet's open tab (Chrome DevTools over adb forward tcp:9222). Read-only.
import json, sys, time
from playwright.sync_api import sync_playwright

JS = """async () => {
  const S = window.__pw.S, st = window.__pw.pdf.stats();
  const sheets = [...document.querySelectorAll('#stack .sheet')].map((s) => {
    const L = s.querySelector(':scope > .pdfLayer');
    return { i: s.dataset.index, pdf: !!s.dataset.pdf, w: s.style.width, h: s.style.height,
             kids: L ? [...L.children].map((c) => c.tagName.toLowerCase() + '.' + c.className + ':' + (c.width || c.naturalWidth) + 'x' + (c.height || c.naturalHeight)) : null };
  });
  const pages = S.openNote ? S.pages.filter((p) => p.note_id === S.openNote && !p.deleted_at).sort((a, b) => a.position - b.position) : [];
  const cur = pages[S.cur] || null;
  const cached = cur && cur.pdf_path ? await window.__pw.pdf.cached(cur.pdf_path) : null;
  const desk = document.getElementById('desk'), r = desk.getBoundingClientRect();
  return { t: Date.now(), note: S.openNote, noteName: (S.notes.find((n) => n.id === S.openNote) || {}).name, cur: S.cur, curPdf: cur ? { path: cur.pdf_path, page: cur.pdf_page, rot: cur.pdf_rot, cached } : null,
           zoom: document.getElementById('stack').dataset.zoom, transform: document.getElementById('stack').style.transform,
           desk: [Math.round(r.width), Math.round(r.height)], dpr: devicePixelRatio, vis: document.visibilityState, online: navigator.onLine,
           mem: performance.memory ? { usedMB: Math.round(performance.memory.usedJSHeapSize / 1048576), limitMB: Math.round(performance.memory.jsHeapSizeLimit / 1048576) } : null,
           ua: navigator.userAgent, st, sheets };
}"""

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://localhost:9222")
    pages = [pg for c in b.contexts for pg in c.pages if "penworks" in pg.url]
    if not pages:
        print("no PenWorks page found; urls:", [pg.url for c in b.contexts for pg in c.pages]); sys.exit(1)
    pg = pages[0]
    print("url:", pg.url)
    a = pg.evaluate(JS)
    time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 6)
    b2 = pg.evaluate(JS)
    for k in ("note", "noteName", "cur", "curPdf", "zoom", "transform", "desk", "dpr", "vis", "online", "mem", "ua"):
        print(f"{k}: {a[k]}")
    print("sheets:", json.dumps(a["sheets"]))
    sa, sb = a["st"], b2["st"]
    ev = sa.pop("events"); sb.pop("events")
    print("stats now:", json.dumps(sa))
    diff = {k: (sa.get(k), sb.get(k)) for k in sb if sa.get(k) != sb.get(k)}
    print(f"changed over {round((b2['t'] - a['t']) / 1000, 1)} s:", json.dumps(diff))
    print("events (last 60):", ev[-60:])
