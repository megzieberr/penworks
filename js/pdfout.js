// PenWorks round 5 (pw-v7j): Share as PDF writes VECTOR pages. Her complaint (29 Oct): the export was slow and the ink
// was soft. Before this round every page went through a picture (SVG to <img> to a 2x canvas to a JPEG 0.92) and jsPDF
// packed one JPEG per page. Now (pdf-lib 1.17.1, vendor/pdf-lib.min.js, loaded the first time she shares a PDF):
//  - a plain page: its paper pattern as thin lines (page.js bgSvg's spacing and colour), then the ink as PDF paths;
//  - a page that came from a PDF: the ORIGINAL page embedded as it is (its text stays text, a scan stays the scan),
//    then the ink on top. One embedPages call per source file, so pages of one file share its fonts and images.
// The ink is drawn from the same path strings the screen uses (ink.js pathD, arcD, arrowHead), in the same order as
// ink.thumbSvg: the highlighter groups first (ascending opacity), then the pen layer, each in seq order.
// Highlighter see-through (her rule, 25 Oct: going over a spot again stays one flat colour): every highlighter stroke
// of one opacity, colour, width and dash on a page is ONE path (m ... m ...) stroked once, so its overlaps are painted
// once. Two different highlighter colours over each other mix a little here where the screen shows the top one.
// Sizes: A4 in points, landscape when wider than tall; a PDF page 595.28 pt across (841.89 when it is the A4 landscape
// width), its height by the source page's own aspect. k = PDF points per page px.
// The paper and the ink are written as the page's own PDF operators in one content stream (compressed with the
// browser's CompressionStream): "k/4 0 0 -k/4 0 H cm" puts quarter page px, y down, onto the page, so every number is a
// short whole number (decimals made the 200-page test note 18 MB, tenths 16 MB, quarters under 15) and widths and
// dashes are the screen's own page px times 4 (2.5 is 10, 18 is 72, exactly); round joins and caps. A point moves at
// most 1/8 page px (0.03 mm) from the screen's. pdf-lib's drawSvgPath was the first try: it draws an SVG 'Q' as PDF's
// 'v' curve (not the same curve: a parabola came out 9 page px off) and its operator objects took about 10 s for a
// heavy 200-page note, so the paths are written here instead (a Q becomes the cubic that IS that quadratic; an A
// becomes cubics, a quarter turn at most each). Proved in tests/test_pdfout.py against the screen's picture.
// A source PDF that pdf-lib cannot embed (encrypted, or it will not parse) falls back to a picture of that page at 2x
// (pdf.js, as before this round) with the ink still vector on top. Bytes not on this device: the export stops with
// "The PDF is not on this device yet", the same toast as before.
import * as ink from './ink.js';
import { pageSize, A4, CM, GRID, GRID_TOP, LINE_GAP, LINE_TOP } from './page.js';
import * as pdfin from './pdfin.js';
import * as pdfview from './pdfview.js';

const A4_PT = [595.28, 841.89];        // A4 in PDF points
const PAPER = '#D3D7DE';               // page.js bgSvg's line colour, 1 page px wide
const RASTER = 2;                      // the fallback picture of a PDF page: 2x page px, as the old export
const f1 = (v) => String(Math.round(v * 10) / 10);     // ink.js's own rounding for path numbers
const U = 4;                                          // content stream units per page px: quarter px
const n2 = (v) => String(Math.round(v * U));          // path numbers in the content stream: whole quarter px

let libLoad = null;
export function loadPdfLib() {
  if (window.PDFLib) return Promise.resolve(window.PDFLib);
  return (libLoad ||= new Promise((ok, no) => {
    const s = document.createElement('script');
    s.src = './vendor/pdf-lib.min.js';
    s.onload = () => (window.PDFLib ? ok(window.PDFLib) : no(new Error('the PDF maker did not load')));
    s.onerror = () => { libLoad = null; s.remove(); no(new Error('the PDF maker did not load')); };
    document.head.append(s);
  }));
}

// a page's size in PDF points, the rule the jsPDF export had
export function pdfSize(p) {
  const sz = pageSize(p), wpt = sz.w === A4.h ? A4_PT[1] : A4_PT[0];
  if (p.pdf_path) return [wpt, wpt * p.pdf_h / p.pdf_w];
  return sz.w > sz.h ? [A4_PT[1], A4_PT[0]] : [A4_PT[0], A4_PT[1]];
}

// '#RRGGBB' as "r g b RG" (the stroke colour)
function rgOf(c) {
  let s = String(c || '#000000').replace('#', '');
  if (s.length === 3 || s.length === 4) s = s.slice(0, 3).split('').map((x) => x + x).join('');
  let v = parseInt(s.slice(0, 6), 16);
  if (!(v >= 0)) v = 0;
  const ch = (x) => String(Math.round(x / 255 * 1000) / 1000);
  return ch((v >> 16) & 255) + ' ' + ch((v >> 8) & 255) + ' ' + ch(v & 255) + ' RG';
}

// ---------------------------------------------------------------- SVG path to PDF path operators
// the subset the app makes: M L H V C Q A Z (absolute) and the dot's relative h (ink.js pathD, one point)
const TOK = /[MLHVCQAZmlhvcqaz]|-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/g;
function pdfPath(d) {
  const tok = d.match(TOK) || [], out = [];
  let i = 0, cmd = '', x = 0, y = 0, sx = 0, sy = 0;
  const num = () => +tok[i++];
  const line = () => out.push(n2(x) + ' ' + n2(y) + ' l');
  while (i < tok.length) {
    const t = tok[i];
    if (t.length === 1 && t > '9') {
      cmd = t; i++;
      if (cmd === 'Z' || cmd === 'z') { out.push('h'); x = sx; y = sy; }
      continue;
    }
    switch (cmd) {
      case 'M': x = num(); y = num(); sx = x; sy = y; out.push(n2(x) + ' ' + n2(y) + ' m'); cmd = 'L'; break;
      case 'L': x = num(); y = num(); line(); break;
      case 'H': x = num(); line(); break;
      case 'h': x += num(); line(); break;
      case 'V': y = num(); line(); break;
      case 'v': y += num(); line(); break;
      case 'C': {
        const a = num(), b = num(), c = num(), e = num(); x = num(); y = num();
        out.push(n2(a) + ' ' + n2(b) + ' ' + n2(c) + ' ' + n2(e) + ' ' + n2(x) + ' ' + n2(y) + ' c'); break;
      }
      case 'Q': {                                                   // the cubic that is this quadratic
        const qx = num(), qy = num(), ex = num(), ey = num();
        out.push(n2(x + 2 / 3 * (qx - x)) + ' ' + n2(y + 2 / 3 * (qy - y)) + ' ' + n2(ex + 2 / 3 * (qx - ex)) + ' '
          + n2(ey + 2 / 3 * (qy - ey)) + ' ' + n2(ex) + ' ' + n2(ey) + ' c');
        x = ex; y = ey; break;
      }
      case 'A': {
        const rx = num(), ry = num(), rot = num(), large = num(), sweep = num(), ex = num(), ey = num();
        arcTo(out, x, y, rx, ry, rot, large, sweep, ex, ey); x = ex; y = ey; break;
      }
      default: return out.join('\n');                              // anything else: stop there
    }
  }
  return out.join('\n');
}
// an SVG arc (the endpoint form) as cubics, a quarter turn at most each (SVG 1.1 appendix F.6.5)
function arcTo(out, x1, y1, rx, ry, rotDeg, large, sweep, x2, y2) {
  if (x1 === x2 && y1 === y2) return;
  rx = Math.abs(rx); ry = Math.abs(ry);
  if (!rx || !ry) { out.push(n2(x2) + ' ' + n2(y2) + ' l'); return; }
  const phi = rotDeg * Math.PI / 180, cp = Math.cos(phi), sp = Math.sin(phi);
  const dx = (x1 - x2) / 2, dy = (y1 - y2) / 2, xp = cp * dx + sp * dy, yp = -sp * dx + cp * dy;
  const lam = (xp * xp) / (rx * rx) + (yp * yp) / (ry * ry);
  if (lam > 1) { const s = Math.sqrt(lam); rx *= s; ry *= s; }
  const num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp, den = rx * rx * yp * yp + ry * ry * xp * xp;
  let co = den ? Math.sqrt(Math.max(0, num / den)) : 0;
  if (!!large === !!sweep) co = -co;
  const cxp = co * rx * yp / ry, cyp = -co * ry * xp / rx;
  const cx = cp * cxp - sp * cyp + (x1 + x2) / 2, cy = sp * cxp + cp * cyp + (y1 + y2) / 2;
  const ang = (ux, uy, vx, vy) => Math.atan2(ux * vy - uy * vx, ux * vx + uy * vy);
  const t1 = ang(1, 0, (xp - cxp) / rx, (yp - cyp) / ry);
  let dt = ang((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry);
  if (!sweep && dt > 0) dt -= 2 * Math.PI; else if (sweep && dt < 0) dt += 2 * Math.PI;
  const n = Math.max(1, Math.ceil(Math.abs(dt) / (Math.PI / 2) - 1e-9)), step = dt / n, kk = 4 / 3 * Math.tan(step / 4);
  const P = (t) => [cx + rx * Math.cos(t) * cp - ry * Math.sin(t) * sp, cy + rx * Math.cos(t) * sp + ry * Math.sin(t) * cp];
  const D = (t) => [-rx * Math.sin(t) * cp - ry * Math.cos(t) * sp, -rx * Math.sin(t) * sp + ry * Math.cos(t) * cp];
  for (let j = 0; j < n; j++) {
    const a = t1 + j * step, b = a + step, pa = P(a), da = D(a), db = D(b), pb = j === n - 1 ? [x2, y2] : P(b);
    out.push(n2(pa[0] + kk * da[0]) + ' ' + n2(pa[1] + kk * da[1]) + ' ' + n2(pb[0] - kk * db[0]) + ' ' + n2(pb[1] - kk * db[1])
      + ' ' + n2(pb[0]) + ' ' + n2(pb[1]) + ' c');
  }
}

// ---------------------------------------------------------------- what a page draws, as SVG path strings (page px)
// the paper pattern as one path of thin lines, where bgSvg's patterns put them (a line half off the page edge too)
function paperD(w, h, kind) {
  const out = [];
  if (kind === 'grid') {
    for (let j = 0; j * GRID < w + 0.5; j++) out.push('M' + f1(j * GRID) + ' 0L' + f1(j * GRID) + ' ' + f1(h));
    for (let j = 0; GRID_TOP + j * GRID < h + 0.5; j++) {
      const y = GRID_TOP + j * GRID;
      out.push('M0 ' + f1(y) + 'L' + f1(w) + ' ' + f1(y));
    }
  } else if (kind === 'lined') {
    const n = Math.floor((h - CM - LINE_TOP) / LINE_GAP + 1e-6);
    for (let j = 0; j <= n; j++) {
      const y = LINE_TOP + j * LINE_GAP;
      out.push('M0 ' + f1(y) + 'L' + f1(w) + ' ' + f1(y));
    }
  }
  return out.join('');
}

// a record's paths as [d, dashed] pairs, the way ink.js makeEl and setGeom draw it (an arrow's head is never dashed)
function pathsOf(rec) {
  const st = rec.style || {}, dashed = st.dash === 'dashed', w = st.width || 2.5;
  if (rec.kind !== 'shape') return [[ink.pathD((rec.data && rec.data.points) || []), dashed]];
  const d = rec.data || {}, p = (x, y) => f1(x) + ' ' + f1(y);
  switch (d.type) {
    case 'line': return [['M' + p(d.x1, d.y1) + 'L' + p(d.x2, d.y2), dashed]];
    case 'arrow': return [['M' + p(d.x1, d.y1) + 'L' + p(d.x2, d.y2), dashed], [ink.arrowHead(d, w), false]];
    case 'carrow': return [[ink.arcD(d), dashed], [ink.arrowHead(d, w), false]];
    case 'rect': case 'triangle':
      return d.points && d.points.length ? [['M' + d.points.map((q) => p(q[0], q[1])).join('L') + 'Z', dashed]] : [];
    case 'circle': case 'ellipse': {
      // an SVG circle or ellipse starts at its 3 o'clock point and runs clockwise on the page, so a dashed one's dashes
      // start where the screen's do; a turned ellipse turns its points and its axes. Four quarter arcs: two half arcs
      // between rounded points are ambiguous and came out up to 3 px off.
      const rx = d.type === 'circle' ? d.r : d.rx, ry = d.type === 'circle' ? d.r : d.ry, deg = d.type === 'ellipse' ? d.angle || 0 : 0;
      const t = deg * Math.PI / 180, cs = Math.cos(t), sn = Math.sin(t);
      const at = (x, y) => p(d.cx + x * cs - y * sn, d.cy + x * sn + y * cs);
      const arc = (x, y) => 'A' + f1(rx) + ' ' + f1(ry) + ' ' + f1(deg) + ' 0 1 ' + at(x, y);
      return [['M' + at(rx, 0) + arc(0, ry) + arc(-rx, 0) + arc(0, -ry) + arc(rx, 0) + 'Z', dashed]];
    }
    case 'arc': return [[ink.arcD(d), dashed]];
    case 'parabola': return [['M' + p(d.x1, d.y1) + 'Q' + p(d.cx, d.cy) + ' ' + p(d.x2, d.y2), dashed]];
    default: return [];
  }
}

// one page's paper and ink as content stream text. gsOf(opacity) = the page's ExtGState name for that opacity
function pageOps(sz, background, recs, k, H, gsOf) {
  const kk = String(Math.round(k / U * 1e8) / 1e8);               // k / U: the numbers below are quarter page px
  const ops = ['q', kk + ' 0 0 -' + kk + ' 0 ' + String(Math.round(H * 100) / 100) + ' cm', '1 j'];
  const paper = background ? paperD(sz.w, sz.h, background) : '';
  if (paper) ops.push(rgOf(PAPER) + ' ' + n2(1) + ' w 0 J [] 0 d', pdfPath(paper), 'S');
  const stroke = (d, colour, w, dashed, opacity) => {
    const a = dashed ? n2(+ink.dashOf(w).split(' ')[0]) : '';
    const head = rgOf(colour) + ' ' + n2(w) + ' w 1 J ' + (dashed ? '[' + a + ' ' + a + '] 0 d' : '[] 0 d');
    if (opacity !== undefined) ops.push('q', gsOf(opacity) + ' gs', head, pdfPath(d), 'S', 'Q');
    else ops.push(head, pdfPath(d), 'S');
  };
  const hl = new Map(), pen = [];
  for (const rec of recs) {
    if (ink.inHl(rec)) {
      const st = rec.style || {}, op = +ink.opKey(rec), w = st.width || 2.5;
      for (const [d, dashed] of pathsOf(rec)) {
        if (!d) continue;
        const key = op + '|' + (st.colour || '#000000') + '|' + w + '|' + dashed;
        let g = hl.get(key);
        if (!g) hl.set(key, (g = { op, colour: st.colour, w, dashed, ds: [] }));
        g.ds.push(d);
      }
    } else pen.push(rec);
  }
  [...hl.values()].sort((a, b) => a.op - b.op).forEach((g) => stroke(g.ds.join(''), g.colour, g.w, g.dashed, g.op));
  // the pen layer in seq order; a run of opaque paths with the same colour, width and dash is one path (the same
  // opaque colour painted twice looks the same as once, and a dash pattern starts again on every m, as on every SVG path)
  let run = null;
  const end = () => { if (run) stroke(run.ds.join(''), run.colour, run.w, run.dashed, undefined); run = null; };
  for (const rec of pen) {
    const st = rec.style || {}, w = st.width || 2.5;
    const op = st.opacity !== undefined && +st.opacity !== 1 ? +st.opacity : undefined;
    for (const [d, dashed] of pathsOf(rec)) {
      if (!d) continue;
      if (op !== undefined) { end(); stroke(d, st.colour, w, dashed, op); continue; }
      const key = (st.colour || '#000000') + '|' + w + '|' + dashed;
      if (run && run.key !== key) end();
      if (!run) run = { key, colour: st.colour, w, dashed, ds: [] };
      run.ds.push(d);
    }
  }
  end();
  ops.push('Q');
  return ops.join('\n');
}

// the text as a FlateDecode stream (the browser's own deflate; pdf-lib's when the browser has none)
async function flate(doc, text) {
  if (typeof CompressionStream === 'function') {
    const z = new Blob([text]).stream().pipeThrough(new CompressionStream('deflate'));
    return doc.context.stream(new Uint8Array(await new Response(z).arrayBuffer()), { Filter: 'FlateDecode' });
  }
  return doc.context.flateStream(text);
}

// ---------------------------------------------------------------- PDF pages
// the source PDFs of the pages being exported, embedded once per file the first time one of its pages comes up
async function embedSource(L, doc, path, pages) {
  const blob = await pdfin.bytesOf(path);
  if (!blob) throw new Error('The PDF is not on this device yet');
  const want = [...new Set(pages.filter((p) => p.pdf_path === path).map((p) => p.pdf_page))].sort((a, b) => a - b);
  const out = new Map();
  let src = null;
  try {
    src = await L.PDFDocument.load(new Uint8Array(await blob.arrayBuffer()), { ignoreEncryption: true, updateMetadata: false });
  } catch (e) { console.warn('PenWorks: a PDF could not be embedded, its pages go as pictures:', (e && e.message) || e); }
  if (!src || src.isEncrypted) return out;                       // empty: these pages go as pictures
  const all = src.getPages(), list = [], boxes = [], rots = [];
  for (const n of want) {
    const sp = all[n - 1];
    if (!sp) continue;
    const c = sp.getCropBox(), m = sp.getMediaBox();          // pdf.js shows the crop box inside the media box
    const left = Math.max(c.x, m.x), bottom = Math.max(c.y, m.y);
    const right = Math.min(c.x + c.width, m.x + m.width), top = Math.min(c.y + c.height, m.y + m.height);
    list.push(sp); boxes.push(right > left && top > bottom ? { left, bottom, right, top } : undefined);
    rots.push((((sp.getRotation().angle || 0) % 360) + 360) % 360);
  }
  try {
    const emb = await doc.embedPages(list, boxes);
    let j = 0;
    for (const n of want) if (all[n - 1]) { out.set(n, { emb: emb[j], rot: rots[j] }); j++; }
  } catch (e) { console.warn('PenWorks: a PDF could not be embedded, its pages go as pictures:', (e && e.message) || e); out.clear(); }
  return out;
}

// an embedded source page drawn to fill the page W x H points, turned by its own /Rotate (clockwise, as pdf.js shows it)
function drawSource(L, page, e, W, H) {
  const bw = e.emb.width, bh = e.emb.height, r = e.rot;
  if (r === 90) page.drawPage(e.emb, { x: 0, y: H, xScale: H / bw, yScale: W / bh, rotate: L.degrees(-90) });
  else if (r === 180) page.drawPage(e.emb, { x: W, y: H, xScale: W / bw, yScale: H / bh, rotate: L.degrees(180) });
  else if (r === 270) page.drawPage(e.emb, { x: W, y: 0, xScale: H / bw, yScale: W / bh, rotate: L.degrees(90) });
  else page.drawPage(e.emb, { x: 0, y: 0, xScale: W / bw, yScale: H / bh });
}

// the fallback: the PDF page as a 2x JPEG (pdf.js), as the export was before this round
async function sourcePicture(doc, p) {
  const { w, h } = pageSize(p), c = document.createElement('canvas');
  c.width = w * RASTER; c.height = h * RASTER;
  const g = c.getContext('2d');
  g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, c.width, c.height);
  await pdfview.paint(g, p, c.width, c.height);                 // throws when the PDF is not here
  const b = await new Promise((ok, no) => c.toBlob((x) => (x ? ok(x) : no(new Error('a page could not be drawn'))), 'image/jpeg', 0.92));
  c.width = 0; c.height = 0;
  return doc.embedJpg(new Uint8Array(await b.arrayBuffer()));
}

// ---------------------------------------------------------------- the export
// the pages (page rows, note order) as one PDF Blob; progress(k, n) before page k of n. recsOf(p) = that page's
// records (default: the page's own, from ink.js)
export async function buildPdf(pages, name, progress = () => {}, recsOf = (p) => ink.strokesOf(p.id)) {
  const L = await loadPdfLib();
  const doc = await L.PDFDocument.create();
  const sources = new Map();                                     // pdf_path -> Map(pdf_page -> { emb, rot })
  const gsRefs = new Map();                                      // opacity -> one ExtGState for the whole file
  const n = pages.length;
  for (let i = 0; i < n; i++) {
    progress(i + 1, n);
    await new Promise((r) => setTimeout(r, 0));                 // a yield between pages: the screen stays alive
    const p = pages[i], [W, H] = pdfSize(p), sz = pageSize(p), k = W / sz.w;
    const page = doc.addPage([W, H]);
    if (p.pdf_path) {
      if (!sources.has(p.pdf_path)) sources.set(p.pdf_path, await embedSource(L, doc, p.pdf_path, pages));
      const e = sources.get(p.pdf_path).get(p.pdf_page);
      if (e) drawSource(L, page, e, W, H);
      else page.drawImage(await sourcePicture(doc, p), { x: 0, y: 0, width: W, height: H });
    }
    const names = new Map();
    const gsOf = (op) => {
      if (!names.has(op)) {
        if (!gsRefs.has(op)) gsRefs.set(op, doc.context.register(doc.context.obj({ Type: 'ExtGState', CA: op, ca: op })));
        names.set(op, page.node.newExtGState('GS', gsRefs.get(op)).toString());
      }
      return names.get(op);
    };
    const text = pageOps(sz, p.pdf_path ? '' : p.background, (recsOf(p) || []).slice().sort((a, b) => a.seq - b.seq), k, H, gsOf);
    page.node.addContentStream(doc.context.register(await flate(doc, text)));
  }
  doc.setTitle(name);
  const bytes = await doc.save({ useObjectStreams: true });
  return new Blob([bytes], { type: 'application/pdf' });
}
