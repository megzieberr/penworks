# PenWorks on her TABLET, read over the cable (3 Nov 2026, the washy-look investigation). How ANY session reads the
# app's own counters off her tablet with no code change:
#   1. tablet plugged in, USB debugging on (authorised since 1 Nov 2026), PenWorks open in Chrome / the installed app
#   2. adb forward tcp:9222 localabstract:chrome_devtools_remote      (adb: winget's Google.PlatformTools)
#   3. python tools/tablet_watch.py        (Playwright connects over CDP; nothing is changed on the tablet)
#   4. adb forward --remove-all when done. The screen must be ON (a dozing tablet draws no frames).
# A real screen grab: adb exec-out screencap -p > screen.png (what the panel shows, canvases and all).
# Watch PenWorks on the tablet for N seconds (default 60): once a second, which note and page are open, the zoom,
# what each PDF layer near the screen holds (thumb img / canvas and its size), and the PDF layer's counters as they change.
import json, sys, time
from playwright.sync_api import sync_playwright

JS = """() => {
  const S = window.__pw.S, st = window.__pw.pdf.stats();
  const sheets = [...document.querySelectorAll('#stack .sheet')].map((s) => {
    const L = s.querySelector(':scope > .pdfLayer');
    return s.dataset.index + ':' + (L ? [...L.children].map((c) => (c.tagName === 'IMG' ? 'thumb' : 'canvas') + (c.width || c.naturalWidth) + 'x' + (c.height || c.naturalHeight)).join('+') || '-' : 'noPdf');
  });
  const [a, b] = st.range;
  return { t: Date.now(), name: (S.notes.find((n) => n.id === S.openNote) || {}).name || null, cur: S.cur, zoom: document.getElementById('stack').dataset.zoom,
           range: st.range, near: sheets.filter((x) => { const i = +x.split(':')[0] - 1; return i >= a - 1 && i <= b + 1; }),
           c: { renders: st.renders, fails: st.fails, held: st.held, cancelled: st.cancelled, ph: st.placeholders, phLive: st.placeholdersLive, canvases: st.canvases, evN: st.evN },
           events: st.events };
}"""

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://localhost:9222")
    pg = [pg for c in b.contexts for pg in c.pages if "penworks" in pg.url][0]
    last, evN, t0 = None, None, time.time()
    while time.time() - t0 < secs:
        d = pg.evaluate(JS)
        new = d["events"][-(d["c"]["evN"] - evN):] if evN is not None and d["c"]["evN"] > evN else ([] if evN is not None else d["events"][-5:])
        evN = d["c"]["evN"]
        line = {k: d[k] for k in ("name", "cur", "zoom", "range", "near", "c")}
        if line != last or new:
            print(f"{time.strftime('%H:%M:%S')} {json.dumps(line, ensure_ascii=False)} new={new}", flush=True)
            last = line
        time.sleep(1)
