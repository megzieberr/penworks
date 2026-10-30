# PenWorks round 5 checks (pw-v7j): Share as PDF writes VECTOR pages (js/pdfout.js, pdf-lib 1.17.1).
# Run: python tests/test_pdfout.py          (local mode only: ?local=1, the localStorage twin stands in for Supabase)
#      python tests/test_pdfout.py --old    (only the OLD export's time on the 200-page note: needs vendor/jspdf.umd.min.js,
#                                            so it ran once before jsPDF was removed; its numbers are in OLD below)
# What it proves, with numbers:
#  - fidelity: a page with every kind of record, on grid paper and on lined paper, exported and drawn by pdf.js at 2x,
#    against the screen's own picture of the page (the page SVG through an <img> at 2x, as the old export drew it):
#    the mean pixel difference, and the furthest any ink pixel sits from the other picture's ink (a shifted or flipped
#    page, a wrong line width, mitred corners or dashes out of step all push that past the limit);
#  - her strokes (tests/fixtures/her-short-lines-29oct.json) exported and drawn at 4x;
#  - speed: a 200-page note, 300 records a page, under 10 s and under 15 MB;
#  - PDF pages: scan20.pdf (20 scan pages) with ink on pages 1 and 20: time, every page at its size, the scan's own
#    JPEG bytes untouched, page 1's pixels equal pdf.js's render of the source page where there is no ink, the ink on
#    top; a PDF with text keeps its text (pdf.js getTextContent); u4a.pdf's vector pages stay vector; an encrypted PDF
#    falls back to a picture of the page; a PDF not on this device stops the export with its message;
#  - the highlighter: two crossing strokes, the crossing's pixel equals one stroke's pixel.
# PNGs for the foreman go to _build/out/pdfout-*.png. PDFs are read with PyMuPDF and pdf.js, never looked at by hand.
import sys, subprocess, time, pathlib, base64, io, json, tempfile, hashlib
import fitz
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8794
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
OUT = ROOT / "_build" / "out"; OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "fixtures"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="pw-pdfout-"))
OLD_MODE = "--old" in sys.argv
if OLD_MODE and not (ROOT / "vendor" / "jspdf.umd.min.js").exists():
    sys.exit("--old needs vendor/jspdf.umd.min.js, removed in round 5; the numbers it gave are in OLD")
# the OLD export (jsPDF, one JPEG per page), measured with --old on 29 Oct 2026 before jsPDF was removed, same note
OLD = {"ms": 25510, "bytes": 103320000}   # 25.51 s and 24.57 s on two runs, 103.32 MB both times

MEAN_MAX = 2.0     # fidelity: mean absolute difference per channel, 0 to 255
REACH_MAX = 3.0    # fidelity: no ink pixel further than this (px at 2x, so 1.5 page px) from the other picture's ink
FLAT_MAX = 2       # highlighter: the crossing's pixel within this many levels of one stroke's pixel

res = []
group = ["?"]
info_lines = []
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

# text PDF and its encrypted twin, made here with PyMuPDF
TEXTPDF = TMP / "text.pdf"; ENCPDF = TMP / "enc.pdf"
TEXT_LINE = "PenWorks keeps this text 29 Oct"
d_ = fitz.open(); p_ = d_.new_page(width=595.28, height=841.89)
p_.insert_text((72, 120), TEXT_LINE, fontsize=22)
p_.insert_text((72, 170), "Second line: vector, not a picture", fontsize=14)
p_.draw_rect(fitz.Rect(72, 220, 300, 320), color=(0, 0, 0), fill=(0.1, 0.1, 0.1))
d_.save(str(TEXTPDF))
d_.save(str(ENCPDF), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="", permissions=fitz.PDF_PERM_PRINT)
d_.close()
b64file = lambda path: base64.b64encode(pathlib.Path(path).read_bytes()).decode()

HELPERS_JS = """async () => {
  const ink = await import('./js/ink.js'), pg = await import('./js/page.js'), out = await import('./js/pdfout.js');
  const pdfin = await import('./js/pdfin.js'), pdfview = await import('./js/pdfview.js');
  const NS = 'http://www.w3.org/2000/svg';
  // the screen's picture of a page: app.js pageSvgText + renderPage as they were at pw-v7i, with the records given
  const svgText = (p, recs, s) => {
    const { w, h } = pg.pageSize(p), svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', w * s); svg.setAttribute('height', h * s); svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    if (!p.pdf_path) {
      const r = document.createElementNS(NS, 'rect'); r.setAttribute('width', w); r.setAttribute('height', h); r.setAttribute('fill', '#FFFFFF');
      svg.append(r);
      const bg = pg.bgSvg(w, h, p.background); while (bg.firstChild) svg.append(bg.firstChild);
    }
    const layer = ink.thumbSvg(p.id, p, recs); while (layer.firstChild) svg.append(layer.firstChild);
    return new XMLSerializer().serializeToString(svg);
  };
  const screen = async (p, recs, s) => {
    const { w, h } = pg.pageSize(p), W = w * s, H = h * s;
    const url = URL.createObjectURL(new Blob([svgText(p, recs, s)], { type: 'image/svg+xml' }));
    try {
      const img = new Image(); img.src = url; await img.decode();
      const c = document.createElement('canvas'); c.width = W; c.height = H;
      const g = c.getContext('2d'); g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, W, H);
      if (p.pdf_path) await pdfview.paint(g, p, W, H);
      g.drawImage(img, 0, 0, W, H);
      return c;
    } finally { URL.revokeObjectURL(url); }
  };
  // page n of a PDF (Blob) through pdf.js onto a W x H canvas, white under it (the way pdfview.js fits a page)
  const render = async (blob, n, W, H) => {
    const m = await pdfin.loadLib();
    const doc = await m.getDocument({ data: new Uint8Array(await blob.arrayBuffer()), isEvalSupported: false }).promise;
    const page = await doc.getPage(n), v1 = page.getViewport({ scale: 1 }), vp = page.getViewport({ scale: W / v1.width });
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const g = c.getContext('2d'); g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, W, H);
    const sy = H / vp.height;
    await page.render({ canvasContext: g, viewport: vp, transform: sy !== 1 ? [1, 0, 0, sy, 0, 0] : undefined }).promise;
    await doc.destroy();
    return c;
  };
  const info = async (blob) => {
    const m = await pdfin.loadLib();
    const doc = await m.getDocument({ data: new Uint8Array(await blob.arrayBuffer()), isEvalSupported: false }).promise;
    const sizes = [];
    for (let k = 1; k <= doc.numPages; k++) { const v = (await doc.getPage(k)).getViewport({ scale: 1 }); sizes.push([v.width, v.height]); }
    const title = (await doc.getMetadata()).info.Title;
    await doc.destroy();
    return { pages: sizes.length, sizes, title };
  };
  const b64 = async (blob) => { const u = new Uint8Array(await blob.arrayBuffer()); let s = '';
    for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
  const fileOf = (b64s, name) => { const bin = atob(b64s), u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new File([u], name, { type: 'application/pdf' }); };
  const rowsOf = (nid) => window.__pw.S.pages.filter((p) => p.note_id === nid && !p.deleted_at).sort((a, b) => a.position - b.position);
  window.__t = { ink, pg, out, pdfin, pdfview, screen, render, info, b64, fileOf, rowsOf, png: (c) => c.toDataURL('image/png') };
  return 1;
}"""

# every kind of record on one page (page px), the page's id given
FID_JS = """(pid) => {
  const S = (seq, kind, style, data) => ({ id: pid + '-' + seq, page_id: pid, seq, kind,
    style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1, ...style }, data });
  const wig = (x, y, n, dx, amp, per) => Array.from({ length: n }, (_, j) => [x + j * dx, Math.round((y + amp * Math.sin(j / per)) * 10) / 10]);
  const HL = { colour: '#FFC107', width: 18, opacity: 0.4 };
  return [
    S(1, 'highlighter', HL, { points: wig(440, 900, 30, 9, 1.5, 6) }),                                   // across
    S(2, 'highlighter', HL, { points: Array.from({ length: 24 }, (_, j) => [560 + Math.sin(j / 5), 800 + j * 9]) }),   // down, crossing it
    S(3, 'pen', {}, { points: wig(80, 120, 40, 8, 14, 3) }),
    S(4, 'pen', { dash: 'dashed', colour: '#1E5BD8', width: 3 }, { points: wig(80, 210, 40, 8, 10, 4) }),
    S(5, 'pen', { width: 6, colour: '#D32F2F' }, { points: [[60, 60]] }),                                // a dot, top left
    S(6, 'shape', {}, { type: 'line', x1: 80, y1: 300, x2: 360, y2: 340 }),
    S(7, 'shape', { width: 4 }, { type: 'rect', points: [[420, 280], [700, 300], [690, 420], [410, 400]] }),
    S(8, 'shape', { width: 8, colour: '#2E7D32' }, { type: 'triangle', points: [[100, 420], [360, 440], [150, 560]] }),
    S(9, 'shape', {}, { type: 'circle', cx: 200, cy: 680, r: 70 }),
    S(10, 'shape', { dash: 'dashed', width: 3 }, { type: 'ellipse', cx: 520, cy: 680, rx: 150, ry: 60, angle: 25 }),
    S(11, 'shape', {}, { type: 'arc', x1: 90, y1: 850, xm: 200, ym: 780, x2: 330, y2: 860 }),
    S(12, 'shape', { colour: '#6A1B9A', width: 3 }, { type: 'parabola', x1: 80, y1: 1060, cx: 200, cy: 900, x2: 330, y2: 1060 }),
    S(13, 'shape', { width: 3 }, { type: 'arrow', x1: 420, y1: 1070, x2: 720, y2: 1050 }),
    S(14, 'shape', { width: 3, dash: 'dashed' }, { type: 'carrow', x1: 440, y1: 520, xm: 580, ym: 470, x2: 720, y2: 540 }),
    S(15, 'shape', { dash: 'dashed' }, { type: 'circle', cx: 690, cy: 150, r: 50 }),
    S(16, 'shape', { colour: '#00ACC1', width: 14, opacity: 0.4 }, { type: 'rect', points: [[620, 960], [770, 960], [770, 1010], [620, 1010]] }),
  ];
}"""

# a synthetic note: N pages, `per` records a page (80 % handwriting, 10 % highlighter, 10 % shapes), seeded
GEN_JS = """(N, per) => {
  let s = 20261029;
  const rnd = () => { s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const r1 = (v) => Math.round(v * 10) / 10, cols = ['#000000', '#000000', '#000000', '#1E5BD8', '#D32F2F'];
  const types = ['line', 'rect', 'triangle', 'circle', 'ellipse', 'arc', 'parabola', 'arrow', 'carrow'];
  const pages = [], recs = new Map();
  for (let i = 0; i < N; i++) {
    const land = i % 10 === 9, w = land ? 1123 : 794, h = land ? 794 : 1123;
    const p = { id: 'g' + i, note_id: 'gen', position: i, orientation: land ? 'landscape' : 'portrait',
      background: ['grid', 'lined', 'grid', 'blank'][i % 4], pdf_path: null };
    pages.push(p);
    const list = [];
    for (let j = 0; j < per; j++) {
      const seq = j + 1, id = p.id + '-' + j, x = 40 + rnd() * (w - 140), y = 40 + rnd() * (h - 140), u = rnd();
      if (u < 0.8) {
        const n = 8 + Math.floor(rnd() * 33), pts = []; let a = rnd() * 6.28, px = x, py = y;
        for (let k = 0; k < n; k++) { a += (rnd() - 0.5) * 1.2; px += 3 * Math.cos(a); py += 3 * Math.sin(a); pts.push([r1(px), r1(py)]); }
        list.push({ id, page_id: p.id, seq, kind: 'pen', style: { colour: cols[j % 5], width: 2.5, dash: j % 23 === 0 ? 'dashed' : 'solid', opacity: 1 }, data: { points: pts } });
      } else if (u < 0.9) {
        const n = 10 + Math.floor(rnd() * 20), pts = [];
        for (let k = 0; k < n; k++) pts.push([r1(x + k * 6), r1(y + Math.sin(k / 4) * 2)]);
        list.push({ id, page_id: p.id, seq, kind: 'highlighter', style: { colour: j % 2 ? '#FFC107' : '#7CFC00', width: 18, opacity: 0.4 }, data: { points: pts } });
      } else {
        const t = types[j % 9], q = 20 + rnd() * 60, d = { type: t };
        if (t === 'line' || t === 'arrow') Object.assign(d, { x1: x, y1: y, x2: x + q, y2: y + q / 2 });
        else if (t === 'rect') d.points = [[x, y], [x + q, y], [x + q, y + q], [x, y + q]];
        else if (t === 'triangle') d.points = [[x, y], [x + q, y + q / 3], [x + q / 3, y + q]];
        else if (t === 'circle') Object.assign(d, { cx: x, cy: y, r: q / 2 });
        else if (t === 'ellipse') Object.assign(d, { cx: x, cy: y, rx: q, ry: q / 2, angle: 30 });
        else if (t === 'arc' || t === 'carrow') Object.assign(d, { x1: x, y1: y, xm: x + q / 2, ym: y - q / 3, x2: x + q, y2: y });
        else Object.assign(d, { x1: x, y1: y, cx: x + q / 2, cy: y - q, x2: x + q, y2: y });
        list.push({ id, page_id: p.id, seq, kind: 'shape', style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: d });
      }
    }
    recs.set(p.id, list);
  }
  return { pages, recs };
}"""

OLD_JS = """async () => {
  const { pages, recs } = window.__gen(200, 300), t = window.__t;
  await new Promise((ok, no) => { const s = document.createElement('script'); s.src = './vendor/jspdf.umd.min.js'; s.onload = ok; s.onerror = no; document.head.append(s); });
  const A4_PT = [595.28, 841.89], t0 = performance.now(), blobs = [];
  for (const p of pages) {
    await new Promise((r) => setTimeout(r, 0));
    const c = await t.screen(p, recs.get(p.id), 2);
    blobs.push(await new Promise((ok) => c.toBlob(ok, 'image/jpeg', 0.92)));
    c.width = 0; c.height = 0;
  }
  const { jsPDF } = window.jspdf; let doc = null;
  for (let k = 0; k < pages.length; k++) {
    const p = pages[k], sz = t.pg.pageSize(p), o = sz.w > sz.h ? 'landscape' : 'portrait';
    if (!doc) doc = new jsPDF({ orientation: o, unit: 'pt', format: 'a4', compress: true }); else doc.addPage('a4', o);
    const pw = doc.internal.pageSize.getWidth(), ph = doc.internal.pageSize.getHeight();
    doc.addImage(new Uint8Array(await blobs[k].arrayBuffer()), 'JPEG', 0, 0, pw, ph, undefined, 'NONE');
  }
  const blob = doc.output('blob');
  return { ms: performance.now() - t0, bytes: blob.size, records: [...recs.values()].reduce((a, l) => a + l.length, 0) };
}"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def img(data_url): return np.asarray(Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))).convert("RGB")).astype(np.int16)
def save(a, name): Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(OUT / name)
def inkmask(a): return a.min(axis=2) < 200
def reach(a, b):
    """the furthest any ink pixel of one picture sits from the other picture's ink, px"""
    ma, mb = inkmask(a), inkmask(b)
    if not ma.any() or not mb.any(): return 1e9
    return float(max(distance_transform_edt(~mb)[ma].max(), distance_transform_edt(~ma)[mb].max()))
def diffpng(a, b): return 255 - np.clip(np.abs(a - b).max(axis=2, keepdims=True) * 4, 0, 255).repeat(3, axis=2)

srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 1000})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LOCAL); ready(pg)
        pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
        pg.evaluate(HELPERS_JS)
        pg.evaluate(f"window.__gen = {GEN_JS}")

        if OLD_MODE:
            r = pg.evaluate(OLD_JS)
            print(f"OLD export (jsPDF, JPEG 0.92 per page), 200 pages, {r['records']} records: {r['ms'] / 1000:.2f} s, {r['bytes'] / 1e6:.2f} MB")
            sys.exit(0)

        # ------------------------------------------------------------ fidelity (grid, lined)
        group[0] = "fidelity"
        pg.evaluate(f"window.__fid = {FID_JS}")
        for bg in ["grid", "lined"]:
            r = pg.evaluate("""async (bg) => { const t = window.__t, p = { id: 'fid-' + bg, orientation: 'portrait', background: bg, pdf_path: null };
              const recs = window.__fid(p.id); const blob = await t.out.buildPdf([p], 'Fidelity', () => {}, () => recs);
              const scr = await t.screen(p, recs, 2), pdf = await t.render(blob, 1, scr.width, scr.height);
              return { scr: t.png(scr), pdf: t.png(pdf), bytes: blob.size, info: await t.info(blob) }; }""", bg)
            A, B = img(r["scr"]), img(r["pdf"])
            save(A, f"pdfout-{bg}-screen.png"); save(B, f"pdfout-{bg}-pdf.png"); save(diffpng(A, B), f"pdfout-{bg}-diff.png")
            mean = float(np.abs(A - B).mean()); far = reach(A, B); big = float((np.abs(A - B).max(axis=2) > 96).mean() * 100)
            info_lines.append(f"fidelity {bg}: mean abs diff {mean:.3f} (limit {MEAN_MAX}), furthest ink {far:.2f} px at 2x (limit {REACH_MAX}), "
                              f"pixels off by more than 96 levels {big:.3f} %, page {r['bytes'] / 1e3:.1f} KB")
            check(f"{bg}: one A4 page, 595.28 x 841.89 pt, title 'Fidelity'", r["info"]["pages"] == 1 and abs(r["info"]["sizes"][0][0] - 595.28) < 0.01
                  and abs(r["info"]["sizes"][0][1] - 841.89) < 0.01 and r["info"]["title"] == "Fidelity", r["info"])
            check(f"{bg}: mean pixel difference under {MEAN_MAX}", mean < MEAN_MAX, mean)
            check(f"{bg}: every ink pixel within {REACH_MAX} px of the other picture's ink (no shift, flip, fat line, mitre or dash out of step)",
                  far <= REACH_MAX, far)
            dot = B[120, 120]; flip = B[B.shape[0] - 120, 120]
            check(f"{bg}: orientation: the red dot at page (60, 60) is red at the PDF's top left, white where a flip would put it",
                  dot[0] > 170 and dot[1] < 90 and dot[2] < 90 and flip.min() > 230, [dot.tolist(), flip.tolist()])
            if bg == "grid":
                group[0] = "highlighter"
                cross, one, two = B[900 * 2, 560 * 2], B[900 * 2, 480 * 2], B[840 * 2, 560 * 2]
                scross = A[900 * 2, 560 * 2]
                d1 = int(np.abs(cross - one).max()); d2 = int(np.abs(cross - two).max())
                info_lines.append(f"highlighter (PDF render): crossing {cross.tolist()}, stroke 1 alone {one.tolist()}, stroke 2 alone {two.tolist()}; "
                                  f"screen's crossing {scross.tolist()}")
                check(f"two crossing highlighter strokes: the crossing equals one stroke (within {FLAT_MAX} levels)", d1 <= FLAT_MAX and d2 <= FLAT_MAX, [d1, d2])
                check("... and it is the screen's colour (within 3 levels)", int(np.abs(cross - scross).max()) <= 3, [cross.tolist(), scross.tolist()])
                check("... and it is see-through (not the full yellow, not white)", 150 < cross[2] < 175 and cross[0] > 240, cross.tolist())
                group[0] = "fidelity"

        # ------------------------------------------------------------ her strokes, 4x
        group[0] = "her strokes"
        her = json.loads((FIX / "her-short-lines-29oct.json").read_text(encoding="utf-8"))
        strokes = [s_["points"] for s_ in her["stayed_pen"]] + [s_["points"] for s_ in her["handwriting_12_45"]]
        xs = [q[0] for s_ in strokes for q in s_]; ys = [q[1] for s_ in strokes for q in s_]
        box = [min(xs) - 12, min(ys) - 12, max(xs) + 12, max(ys) + 12]
        r = pg.evaluate("""async (strokes) => { const t = window.__t, p = { id: 'her', orientation: 'portrait', background: 'grid', pdf_path: null };
          const recs = strokes.map((pts, k) => ({ id: 'her-' + k, page_id: 'her', seq: k + 1, kind: 'pen', style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 }, data: { points: pts } }));
          const blob = await t.out.buildPdf([p], 'Her lines', () => {}, () => recs);
          const scr = await t.screen(p, recs, 4), pdf = await t.render(blob, 1, scr.width, scr.height);
          return { scr: t.png(scr), pdf: t.png(pdf) }; }""", strokes)
        A, B = img(r["scr"]), img(r["pdf"])
        x0, y0, x1, y1 = [int(round(v * 4)) for v in box]
        A, B = A[y0:y1, x0:x1], B[y0:y1, x0:x1]
        save(B, "pdfout-her-lines.png"); save(A, "pdfout-her-lines-screen.png")
        far = reach(A, B); mean = float(np.abs(A - B).mean())
        info_lines.append(f"her strokes ({len(strokes)} strokes, {sum(len(s_) for s_ in strokes)} points) at 4x, cropped to page px {[round(v) for v in box]}: "
                          f"mean diff {mean:.3f}, furthest ink {far:.2f} px at 4x")
        check("her strokes: the PDF's ink is where the screen's is (within 2 x the 2x limit at 4x)", far <= 2 * REACH_MAX and inkmask(B).sum() > 1000, far)

        # ------------------------------------------------------------ speed: 200 pages
        group[0] = "speed"
        r = pg.evaluate("""async () => { const t = window.__t, { pages, recs } = window.__gen(200, 300);
          const t0 = performance.now(); let seen = 0;
          const blob = await t.out.buildPdf(pages, 'Speed', (k) => { seen = k; }, (p) => recs.get(p.id));
          const ms = performance.now() - t0, info = await t.info(blob);
          return { ms, bytes: blob.size, seen, info: { pages: info.pages, first: info.sizes[0], tenth: info.sizes[9] },
                   records: [...recs.values()].reduce((a, l) => a + l.length, 0) }; }""")
        new_s, new_mb = r["ms"] / 1000, r["bytes"] / 1e6
        info_lines.append(f"speed: 200 pages, {r['records']} records: NEW {new_s:.2f} s, {new_mb:.2f} MB ({r['bytes'] / 200 / 1e3:.1f} KB a page)"
                          + (f"; OLD (jsPDF, measured before removal) {OLD['ms'] / 1000:.2f} s, {OLD['bytes'] / 1e6:.2f} MB" if OLD["ms"] else ""))
        check("200 pages export in under 10 s", new_s < 10, round(new_s, 2))
        check("... and the file is under 15 MB", new_mb < 15, round(new_mb, 2))
        check("200 pages in the file, A4 portrait first, page 10 A4 landscape; progress reached 200", r["info"]["pages"] == 200
              and abs(r["info"]["first"][0] - 595.28) < 0.01 and abs(r["info"]["tenth"][0] - 841.89) < 0.01 and r["seen"] == 200, r["info"])

        # ------------------------------------------------------------ PDF pages: scan20
        group[0] = "PDF pages"
        INK1 = [[100 + j * 10, 400 + (j % 2) * 4] for j in range(51)]
        r = pg.evaluate("""async (a) => { const t = window.__t;
          const f = new File([await (await fetch('./tests/fixtures/scan20.pdf')).blob()], 'scan20.pdf', { type: 'application/pdf' });
          const im = await window.__pw.pdf.importPdf(f, {}), rows = t.rowsOf(im.noteId);
          t.ink.put(rows[0].id, [{ id: 's1', page_id: rows[0].id, seq: 1, kind: 'pen', style: { colour: '#D32F2F', width: 6, dash: 'solid', opacity: 1 }, data: { points: a } },
                                 { id: 's2', page_id: rows[0].id, seq: 2, kind: 'highlighter', style: { colour: '#FFC107', width: 18, opacity: 0.4 }, data: { points: [[100, 500], [600, 500]] } }]);
          t.ink.put(rows[19].id, [{ id: 's3', page_id: rows[19].id, seq: 1, kind: 'pen', style: { colour: '#1E5BD8', width: 6, dash: 'solid', opacity: 1 }, data: { points: [[100, 300], [600, 300]] } }]);
          const t0 = performance.now(), blob = await t.out.buildPdf(rows, 'Scan', () => {});
          const ms = performance.now() - t0, { w, h } = t.pg.pageSize(rows[0]), W = w * 2, H = h * 2;
          const out = await t.render(blob, 1, W, H), out20 = await t.render(blob, 20, W, H);
          const src = document.createElement('canvas'); src.width = W; src.height = H;
          const g = src.getContext('2d'); g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, W, H); await t.pdfview.paint(g, rows[0], W, H);
          return { ms, bytes: blob.size, n: rows.length, size: [w, h], out: t.png(out), out20: t.png(out20), src: t.png(src), b64: await t.b64(blob) }; }""", INK1)
        doc = fitz.open(stream=base64.b64decode(r["b64"]), filetype="pdf"); srcdoc = fitz.open(str(FIX / "scan20.pdf"))
        want = (595.28, 595.28 * 1056 / 768)
        sizes = [(p_.rect.width, p_.rect.height) for p_ in doc]
        info_lines.append(f"scan20: 20 scan pages, ink on pages 1 and 20: export {r['ms'] / 1000:.2f} s, {r['bytes'] / 1e6:.2f} MB "
                          f"(the source is {(FIX / 'scan20.pdf').stat().st_size / 1e6:.2f} MB)")
        check("scan20: exports in under 15 s", r["ms"] < 15000, round(r["ms"]))
        check("scan20: 20 pages, each 595.28 x 818.5 pt", doc.page_count == 20 and all(abs(s_[0] - want[0]) < 0.05 and abs(s_[1] - want[1]) < 0.05 for s_ in sizes), sizes[:3])
        def jpegs(d):
            out = []
            for p_ in d:
                for im_ in p_.get_images(full=True): out.append(hashlib.sha256(d.extract_image(im_[0])["image"]).hexdigest())
            return out
        js, jsrc = jpegs(doc), jpegs(srcdoc)
        check("scan20: the scans are the ORIGINAL JPEG bytes (no second JPEG), one per page", len(js) == 20 and js == jsrc, [len(js), len(jsrc)])
        A, B = img(r["src"]), img(r["out"])
        save(B, "pdfout-scan-p1.png")
        mask = np.ones(A.shape[:2], bool); mask[(400 - 30) * 2:(500 + 30) * 2, (100 - 30) * 2:(600 + 30) * 2] = False   # away from the ink
        dm = float(np.abs(A - B)[mask].mean()); dx = int(np.abs(A - B)[mask].max())
        info_lines.append(f"scan20 page 1 against pdf.js's own render of the source page (no ink there): mean diff {dm:.3f}, max {dx}")
        check("scan20 page 1: where there is no ink, the pixels equal pdf.js's render of the source page (mean under 1, max under 40)", dm < 1 and dx < 40, [dm, dx])
        red = B[400 * 2 + 2, 350 * 2]; blue = img(r["out20"])[300 * 2, 350 * 2]
        check("scan20: the ink is on top (red on page 1, blue on page 20)", red[0] > 170 and red[1] < 90 and blue[2] > 170 and blue[0] < 90, [red.tolist(), blue.tolist()])
        doc.close(); srcdoc.close()

        # text stays text; u4a's vector pages stay vector
        r = pg.evaluate("""async (b) => { const t = window.__t;
          const im = await window.__pw.pdf.importPdf(t.fileOf(b, 'text.pdf'), {}), rows = t.rowsOf(im.noteId);
          t.ink.put(rows[0].id, [{ id: 'tx1', page_id: rows[0].id, seq: 1, kind: 'pen', style: { colour: '#D32F2F', width: 3, dash: 'solid', opacity: 1 }, data: { points: [[100, 600], [500, 650]] } }]);
          const blob = await t.out.buildPdf(rows, 'Text', () => {});
          const m = await t.pdfin.loadLib(), doc = await m.getDocument({ data: new Uint8Array(await blob.arrayBuffer()), isEvalSupported: false }).promise;
          const tc = await (await doc.getPage(1)).getTextContent(); await doc.destroy();
          return { text: tc.items.map((x) => x.str).join(' '), bytes: blob.size }; }""", b64file(TEXTPDF))
        check("a PDF with text: pdf.js getTextContent on the exported page finds the source's text (the page is embedded, not pictured)",
              TEXT_LINE in r["text"] and "Second line" in r["text"], r["text"][:120])
        r = pg.evaluate("""async () => { const t = window.__t;
          const f = new File([await (await fetch('./tests/fixtures/u4a.pdf')).blob()], 'u4a.pdf', { type: 'application/pdf' });
          const im = await window.__pw.pdf.importPdf(f, {}), rows = t.rowsOf(im.noteId);
          const blob = await t.out.buildPdf(rows, 'U4a', () => {});
          return { b64: await t.b64(blob) }; }""")
        doc = fitz.open(stream=base64.b64decode(r["b64"]), filetype="pdf")
        sizes = [(round(p_.rect.width, 2), round(p_.rect.height, 2)) for p_ in doc]
        wantu = [(595.28, 841.89), (841.89, 595.28), (595.28, 595.28), (595.28, round(595.28 * 780 / 360, 2))]
        check("u4a.pdf: 4 pages in their own shapes (A4, A4 landscape, square, tall)", doc.page_count == 4
              and all(abs(a_[0] - b_[0]) < 0.05 and abs(a_[1] - b_[1]) < 0.05 for a_, b_ in zip(sizes, wantu)), sizes)
        check("u4a.pdf: the pages stay vector (no pictures, their drawings are there)", all(len(p_.get_images()) == 0 and len(p_.get_drawings()) >= 1 for p_ in doc),
              [(len(p_.get_images()), len(p_.get_drawings())) for p_ in doc])
        doc.close()

        # an encrypted PDF (owner password only) falls back to a picture; a PDF not on this device stops the export
        r = pg.evaluate("""async (a) => { const t = window.__t;
          const im = await window.__pw.pdf.importPdf(t.fileOf(a[0], 'enc.pdf'), {}), rows = t.rowsOf(im.noteId);
          const blob = await t.out.buildPdf(rows, 'Enc', () => {});
          const { w, h } = t.pg.pageSize(rows[0]), W = w * 2, H = h * 2;
          const out = await t.render(blob, 1, W, H), src = await t.render(t.fileOf(a[1], 'text.pdf'), 1, W, H);
          return { b64: await t.b64(blob), out: t.png(out), src: t.png(src) }; }""", [b64file(ENCPDF), b64file(TEXTPDF)])
        doc = fitz.open(stream=base64.b64decode(r["b64"]), filetype="pdf")
        dm = float(np.abs(img(r["out"]) - img(r["src"])).mean())
        check("an encrypted PDF: its page goes as a picture (one image), the right size, and looks like the source (mean diff under 3)",
              doc.page_count == 1 and len(doc[0].get_images()) == 1 and abs(doc[0].rect.height - 841.89) < 0.05 and dm < 3, [doc.page_count, len(doc[0].get_images()), dm])
        doc.close()
        r = pg.evaluate("""async () => { try { await window.__t.out.buildPdf([{ id: 'gone', orientation: 'portrait', background: 'blank', pdf_path: 'nobody/none.pdf',
            pdf_page: 1, pdf_w: 595, pdf_h: 842 }], 'Gone', () => {}, () => []); return 'made'; } catch (e) { return e.message; } }""")
        check("a PDF not on this device: the export stops with 'The PDF is not on this device yet'", r == "The PDF is not on this device yet", r)

        # ------------------------------------------------------------ house rules
        group[0] = "house rules"
        keys = pg.evaluate("navigator.serviceWorker.ready.then(() => caches.keys())")
        if "pw-v7p" not in keys:
            pg.wait_for_timeout(1500); keys = pg.evaluate("caches.keys()")
        check("cache is pw-v7p", "pw-v7p" in keys, keys)
        sw = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check("sw.js keeps vendor/pdf-lib.min.js and js/pdfout.js for offline, and no jsPDF", "./vendor/pdf-lib.min.js" in sw and "./js/pdfout.js" in sw and "jspdf" not in sw)
        st = pg.evaluate("Promise.all(['./vendor/pdf-lib.min.js', './vendor/jspdf.umd.min.js'].map(u => fetch(u, { cache: 'no-store' }).then(r => r.status)))")
        check("vendor/pdf-lib.min.js is served, vendor/jspdf.umd.min.js is gone", st == [200, 404], st)
        srcs = "".join(pg.evaluate("(u) => fetch(u).then(r => r.text())", u) for u in ["./js/app.js", "./js/pdfout.js", "./sw.js", "./vendor/README.md", "./tests/test_pdfout.py"])
        check("no em-dashes in the changed files", chr(0x2014) not in srcs)
        check("no page errors", not errs, errs)
        ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:300]}")
print()
for line in info_lines: print(line)
print(f"PNGs: {OUT}\\pdfout-*.png")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"TOTAL: {sum(r[2] for r in res)}/{len(res)} passed")
