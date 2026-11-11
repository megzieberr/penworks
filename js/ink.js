// PenWorks ink: the stroke model, one SVG layer per page, pen and highlighter drawing, the two
// erasers, hit tests, and the ink operations that join the note's one undo stack (js/app.js).
// A stroke is one record, exactly the strokes table's shape:
//   { id, page_id, seq, kind, style: { colour, width, dash, opacity }, data }
//   pen / highlighter: data = { points: [[x, y], ...] } in page px at zoom 1 (A4 = 794 x 1123)
//   shape (Part B):    data = { type, ...params }; the stroke eraser removes a shape whole; the area eraser turns it into ink and cuts it
// Rendering: one <path> per stroke, so every stroke stays crisp at every zoom and can be hit on its own.
// Each page's SVG holds two groups: <g class="hl"> (bottom) and <g class="pen"> (top, pen and shapes).
// Inside .hl there is one <g class="hlo" data-opacity> per opacity used on the page; its paths are fully
// opaque and the group's opacity makes them see-through, so going over a spot again stays one flat colour.
// Storage goes through js/store.js only (the device cache, and the queue to the database).
// Part B: hold the pen still at the end of a pen stroke and it snaps into a line, arrow, arc, triangle, rect,
// circle or ellipse (SVG primitives); with the select tool a shape's handles can be grabbed and dragged; the restyle
// tool gives strokes the restyle colour and the pen's (or the highlighter's) width, dash or opacity; rectangle
// select moves, resizes, copies, deletes and (from the tray) recolours or restyles. Every one of these is one
// step on the note's undo stack.
// A held highlighter stroke snaps too (never to an arrow): a shape whose style.opacity is under 1 is a
// highlighter-born shape and lives in the highlighter layer (inHl below is that one rule).
// Shape handles (pw-v4v, her ruling 26 Oct: "I want the drag in the select button rather"): the plain pen never grabs,
// it always draws. With the SELECT tool, a pen landing within reach of an end point, corner or compass point of any shape
// on the page grabs it and drags it (after the selection's own turn ring and corners and a move inside the box, pw-v7m below); a grab
// that moves under 4 px on screen is a tap and selects as any select tap does (that shape when nothing else wins). The pen button (a contextmenu on the desk, page.js)
// flips between Select and the last ink tool.
// U5g (pw-v8q; pw-v8r dropped the parallel half): dragging a line's or an arrow's END (and a held stroke that becomes a line, snapNow) aligns it to exactly 90 degrees to a line it meets, within 2 degrees (js/align.js); a small square shows at the corner while it holds and fades 600 ms after the lift (never a record).
// Arc snap (pw-v4f): an open curve held still snaps into a circular arc, data { type: 'arc', x1, y1, xm, ym, x2, y2 }
// (start, the point half way round, end); its three handles move one point each, the arc is the circle through them.
// Select turns (pw-v4g): a ring above the selection box turns the selection about the box's centre (snapping to
// multiples of 15 degrees within 2.5); an ellipse keeps its turn in data.angle (degrees, absent = 0). A selection
// that is moved, resized or turned comes to the front (fresh seq values, its own order kept); a resize keeps the
// ink's width, only the shape grows or shrinks.
// Select polish (pw-v4j): a tap selects the topmost stroke under it, a drag selects everything in the box; a finger
// tap outside the selection clears it (any tool); a turn shows its degrees beside the ring; the chips are icons.
// Clipboard (pw-v4k): the Copy chip puts the selection on a clipboard (CLIP, kept while the app is open, across notes)
// and adds nothing; a finger held still on a page (page.js) opens a small menu with Paste, which puts a copy there,
// centred on the finger and kept inside the page, selected, as one undo step.
// Area eraser cuts shapes (pw-v4l): a shape the area eraser's ring touches turns into plain ink (shapeToInk: pen or
// highlighter records sampled every 3 px along its outline) and the ring cuts that ink like a stroke; one bite out of
// a closed shape leaves one open piece. The stroke eraser still removes a shape whole.
// Overlap tie-break (pw-v4m): a select tap where highlighter-layer and pen-layer records overlap picks from the layer
// of the last ink tool (T.lastInk); with no overlap across the layers it picks the topmost record, whatever is there.
// Last stroke (pw-v4n): LAST remembers the raw points of the last finished pen or highlighter stroke (before any snap) and
// lastStroke() returns it; ?dbg=1 shows and copies it (js/dbg.js), so a real pen stroke can be caught on the tablet.
// Duplicate chip (pw-v4o): a + chip between Copy and Delete puts a copy of the selection 24 px right and down (kept inside
// the page), selected, as one undo step; the clipboard is not touched.
// Cut chip (pw-v7l, her ask 29 Oct): a scissors chip after Copy (Copy, Cut, Duplicate, Delete) puts the selection on the
// clipboard as Copy does and takes its strokes off the page as Delete does, one undo step, toast "Cut."; Paste as before.
// The chips are kept inside the desk (a phone is 375 px wide, four chips are 170 px), still clear of the turn ring.
// Select all (pw-v4p): the finger hold menu has Select all above Paste; it selects every stroke on the page under the finger.
// Parabola snap (pw-v4s): an open curve with one turn whose arms straighten, held still, snaps into a parabola, data
// { type: 'parabola', x1, y1, cx, cy, x2, y2 }: a quadratic Bezier (start, control, end; drawn M x1 y1 Q cx cy x2 y2), which
// stays a parabola under every move, resize and turn. Its three handles are the ends and the curve's middle (t = 0.5). The
// fit runs after the line and before the arc, and wins only when it is under 0.6 of the arc's own fit (an even curve stays
// an arc); lastStroke().fit holds both numbers for ?dbg=1.
// Arrow tip = first corner (pw-v4w): the arrow's tip is the FIRST sharp corner of the stroke (tipIndex below), not the point
// farthest from the start. She rides the pen back along the first wing to the tip; passing the real corner by a hair on that
// return put the old "farthest point" tip on the return pass, and the snap did nothing. The tail may now be up to 1.2 x the
// shaft (her draw-back head path is nearly twice a plain V).
// Curved arrow (pw-v4x, her ask 26 Oct): a curved shaft with the arrow's head at its END, data { type: 'carrow', x1, y1, xm,
// ym, x2, y2 }: exactly an arc's data (start, a middle point on the arc, end = the tip). The head has no field of its own: it
// always points along the arc's direction of travel at its end (arcGeom's te), so a handle drag, a move, a resize or a turn
// re-aims it by itself. Classify runs it right after the straight arrow: the shaft (up to the first sharp corner) fits an
// arc (arcFit, the arc branch's own rules) and the tail passes the arrow's head rules measured against the arc's end tangent.
// Drawn as a <g> of the arc's path and the head's path (the head never dashed); three handles, the arc's; the area eraser
// turns it into the arc's ink plus the head's ink. A highlighter curved arrow becomes an arc (no highlighter arrows).
// Live mirror (U3d): applyRemote(pageId, removeIds, adds) puts a row another device wrote onto the page: apply() with the
// remote flag, so it goes to store.applyRemote (nothing queued), never joins the undo stack, and onChange is told
// { remote: true } (no page picture becomes due). A selection on that page clears first; while a gesture runs the rows
// wait for the lift. replace() (the reconcile's swap) tells onChange { remote: true } too: the database's set is not
// this device's ink, the device that wrote it makes the picture.
// Stroke quality (pw-v7i, her 29 Oct 15:17: "how washy my strokes still look" and short held lines that never snapped):
// the pen's samples go through a One Euro filter (oneEuro, OE: smooths a slow pen hard and a fast one hardly, so small
// writing stops wobbling and nothing trails the nib; ?oe=<mincutoff>,<beta> tunes it, ?dbg=1 shows the pair); on lift the
// kept points are tidied (tidy: the end hook dropped, RDP at 0.25 page px, sharp corners keep their neighbours, no gap
// over 6 page px); the drawing (pathD) and classify's raw path are as before. A held stroke snaps from 12 page px (SNAP_LEN) on; under
// SNAP_MIN (30) it can only become a line; straight() never asks for less than 1.5 page px; HOLD_MS is 350.
// Inside the box moves (pw-v7m, her ruling 29 Oct 15:10: "inside the box always moves; only the corner squares themselves
// resize"). With the select tool and a selection box up, a pen down is read in this order: (1) the turn ring above the box
// turns, as before; (2) a corner resizes only when the pen is within GRAB of it AND outside the box, so only the outer half
// of a corner square (and just past it) resizes; (3) anywhere inside the box MOVES the whole selection, the 12 px band
// inside each corner too, and no shape handle is grabbed from inside; (4) outside the box, a shape handle within
// HANDLE_REACH is grabbed (as with no box at all); (5) else a new box. Inside means the closed rectangle of the dashed box
// (SEL.box): a pen exactly on the dashed line counts as inside and moves. So what decides is where the PEN lands, never
// where the handle sits: a handle on or inside the box's edge is grabbed only by a pen landing outside the box (a shape
// selected alone has its handles 4 px plus half its width inside the box, so they are reached from outside). The hover
// ring follows the same rule. A resize keeps the pen's offset from the corner, so it does not jump at the first move.
// Axes stamp (U5e, pw-v8f; js/tools.js places it): kind 'axes', ONE record, style { colour (the pen's), width 1.5,
// dash solid, opacity 1 }, data { x0, y0, px, py, xs, xe, xd, ys, ye, yd, deg, line } (axesGeom below: the origin in page
// px; px and py the page px per x step and per y step, equal unless Degrees; the ranges and steps, the two ticks). Drawn
// as a <g> (makeEl, setAxes): the axis lines, a tick at every step, an arrow head on each positive end (both ends on a
// number line), the letters x and y, the numbers in the stroke's colour (filled text, 0.3 min(px, py)). Select picks it
// up by a tap on an axis line or a box over one; a move carries the origin, a resize scales the origin about the corner
// and px and py by s (the labels follow);
// a turn leaves it exactly as it was (no new seq); no reshape handles. Recolour and restyle change its colour only (it
// stays thin and opaque, never a highlighter). Both erasers remove it whole. The PDF (js/pdfout.js) strokes its lines and
// writes its labels as Helvetica text. Its ends, crossing and ticks are stick points in js/tools.js (derived, not stored).
// Regular shapes (pw-v8g, her ask 2 Nov 16:54: "squares and triangles to come out as proper shapes ... PERFECT equalateral
// triangles"). A held ring's corners are fitted, still a 'triangle' with 3 points or a 'rect' with 4 (fitTriangle, fitQuad):
// a triangle with exactly one angle within 12 degrees of 90 becomes a true right triangle (the right-angle corner stays, the
// legs keep their lengths and turn evenly to exactly 90, axis-true when within 15 degrees of the axes; a right triangle never
// becomes equilateral); one with every side within 25% of the mean and every angle within 15 degrees of 60 becomes a perfect
// equilateral (centre = the corners' mean, side = the mean side, turned to the corners' mean direction modulo 120, made
// upright when within 15 degrees of it); any other stays as drawn. Four corners all within 15 degrees of 90 become a true
// rectangle at its own turn (the sides' mean direction, opposite sides averaged), a perfect square when width and height
// are within 20%, today's upright box when within 15 degrees of the axes; any other four stay as drawn (still straightened
// when every side is within 15 degrees of the axes, as before). Her 2 Nov triangles (10 to 16 px a side) were all within 7%
// of the mean side, 53 to 65 degrees, 0.5 to 9 degrees off upright. The hook (unhook): a tick where the pen lands, or a
// flick just before the ring closes, within 12% of the size (4 page px at least) of the start is trimmed before the corners
// are found; on her small triangles a 3 px landing tick made a 4th corner.
// pw-v8h (her 3 Nov triangles): a BLUNT corner (destub): a polygon side under 40% of the mean of its long sides, whose two
// outer sides meet close by (within 2 x the stub of its middle), is the pen rounding a corner, not a side she drew; its two
// ends become that one corner, so a triangle with a rounded corner is a triangle, a square with one a square (her 3 Nov
// triangle: 12.8 / 3.7 / 10.4 / 13.3 px sides, saved as a 4-corner rect). A thin bar (10 x 40) keeps its 4 corners: its
// long sides are parallel and meet nowhere near. And the ring CLOSES within 10% of the size or 4 page px
// (CLOSE_PX), whichever is more, like the hook: her other 3 Nov triangle ended 3.1 px short on a 19 px shape and stayed ink.
// Pictures (U4c, pw-v8n; her ask 24 Oct: "images on a page: place, move, resize, lock and unlock, transparency kept").
// kind 'image', ONE record, style { colour '#000000', width 0, dash solid, opacity 1 } (the table's shape, unused), data
// { path, x, y, w, h, nw, nh, rot, locked }: path = the file in the `imports` bucket (<owner>/<uuid>.png or .jpg, kept on
// this device by js/pdfin.js keepImport, fetched by bytesOf on a device without it); x, y, w, h = the picture's box in page
// px BEFORE its turn; nw, nh = the stored file's pixel size; rot = degrees clockwise about the box's centre (absent = 0);
// locked (absent = false). Nothing else is stored: the drawing is worked out from data every time (the axes rule). The
// bottom layer: every page SVG (buildLayer, thumbSvg) holds <g class="img"> BELOW .hl and .pen, so a picture is always
// under all ink, whatever its seq (pictures among themselves: seq order). A picture is a <g data-type="image"> holding an
// SVG <image> (x, y, width, height, preserveAspectRatio none, rotate(rot cx cy) when turned) whose href is a Blob URL of
// the device copy (ONE per path while the app runs, URLS; never a data URL on screen), so a PNG's see-through shows the
// paper by itself. Bytes not on this device yet (the phone, before the download): a light grey dashed rectangle of the box
// (rect.imgWait) until they come (wantImg retries 2, 5, 10, 30 s and on `online`; bytesArrived swaps the <image> in and
// tells onChange, so the thumbs follow). Select: a TAP inside its turned box picks it when no ink is under the tap (ink is
// on top); a BOX picks it when it touches the turned rectangle (a box inside the picture too); move, resize (uniform,
// about the opposite corner; nw, nh untouched) and turn (rot += the turn, about the selection's centre) as every record;
// no reshape handles. Lock: a padlock chip after Delete whenever the selection holds a picture (Lock, or Unlock when any
// is locked), one undo step. A LOCKED picture is never taken by a box or Select all, never moves, resizes or turns; a tap
// on bare locked picture selects it alone with NO corners and NO turn ring, chips Delete and Unlock only, and a drag
// inside does nothing (a selection holding any locked picture behaves so). The erasers, restyle, the tray's recolour and
// restyle of a selection, shapeToInk and page Erase never touch a picture: she erases her ink off a photo without biting
// the photo. The data URL rule: a page drawn through an <img> (app.js renderPage: the share images, U3b's page picture)
// cannot reach a Blob URL from inside the SVG, so there thumbSvg is handed data URLs (imageHrefs, FileReader on the device
// copy, once per path per render), and it throws "The picture is not on this device yet" when the bytes are not here,
// exactly as a missing PDF does. The PDF export (js/pdfout.js) embeds each file once and draws it under the ink.
// Cut out (pw-v9e, her ask 7 Nov; the sheet and the fill: js/cutout.js): ONE unlocked picture selected (whatever it came in
// by: + Image, the share, Paste) has a wand chip after Lock; it opens the sheet (the cutOut hook from app.js). Done gives the
// picture a NEW file: setImagePath changes data.path only (id, seq, x, y, w, h, nw, nh, rot, locked kept), ONE undo step,
// the old file stays on this device so undo shows it again. A picture's bytes never change under a path.
// Sticky notes (pw-v9c; the anchor rule and the export rule: js/page.js's head). A sticky is a pages row with its own ink
// layer here, keyed by its row id like a page's, its strokes in sticky px from its top-left; the layer is the whole square
// (the strip is part of it and drawn above the ink). Every tool works on it as on a page: the pen's press is read by
// surfaceAt / surfacePoint (page.js), which put a sticky ahead of the page under it, so a stroke, an erase, a box or a
// hold lands on the sticky's own layer and the page's ink is never touched; the undo stack takes it like a page's.
// thumbSvg draws a page's ON-PAGE stickies over its ink (cfg stickiesOn, from app.js), clipped to the page: the rounded
// square in its colour, the strip a shade darker, its strokes; no grip bar, no corner mark. A sticky in the margin: nothing.

import * as store from './store.js';
import { pageAt, pagePoint, view, pageSize, CM, surfaceAt, surfacePoint, SK_COLOURS, SK_STRIP } from './page.js';
import { bytesOf } from './pdfin.js';
import { alignDir, segsOf, markOf, markPaths, roundAlong, lineCross, distToSeg as segGap, segCross, MEET, FADE_MS } from './align.js';

// snap: the pen held still this long (ms) at the end of a stroke; ?hold=400 in the address overrides it.
// 350 is her number (29 Oct 15:30; it was 500)
export const HOLD_MS = (() => { const v = +new URLSearchParams(location.search).get('hold'); return v >= 100 && v <= 3000 ? v : 350; })();
// pw-v7i: the One Euro filter on the pen's samples (page px, seconds). mincutoff (Hz) is how hard a slow pen is smoothed
// (lower = smoother, more lag), beta how fast that smoothing lets go as the pen speeds up (higher = less lag on fast
// strokes), dcutoff (Hz) smooths the speed estimate itself. ?oe=4,0.2 in the address overrides mincutoff and beta
// (?dbg=1 shows the pair), so she can tune it on the tablet. 4 and 0.2 come from tests/test_strokeq.py: the brief's
// starting values (1 and 0.007, the paper's, made for screen px at mouse speeds) lagged 1.6 px behind slow writing and
// cut the letter's turn by 2.5 px at 30 page px/s, and lagged 6 px behind a 600 page px/s line.
export const OE = (() => {
  const q = (new URLSearchParams(location.search).get('oe') || '').split(',').map(Number);
  const ok = q.length === 2 && q[0] > 0 && q[0] <= 100 && q[1] >= 0 && q[1] <= 10;
  return { mincutoff: ok ? q[0] : 4, beta: ok ? q[1] : 0.2, dcutoff: 1 };
})();
const SVGNS = 'http://www.w3.org/2000/svg';
export const ERASE_REACH = 6;    // stroke eraser: px on screen around the pen (6 px at zoom 1)
export const AREA_SIZE = 24;     // area eraser: circle diameter, px on screen (24 px at zoom 1)
const MIN_STEP = 0.4;            // page px; the floor: the live step is one SCREEN px (pw-v7e), never less than this
const TIDY_EPS = 0.25;           // pw-v7i: on lift the kept points are simplified (RDP) to within this many page px
const TIDY_GAP = 6;              // pw-v7i: ... but two kept points are never more than this far apart (page px) while a point between them exists
const HOLD_PX = 4;               // snap: "still" means within 4 px on screen of where the pen settled
const SNAP_MIN = 30;             // snap: a stroke shorter than this (page px) only ever snaps to a line; also the arrow's shortest shaft
const SNAP_LEN = 12;             // pw-v7i: a stroke shorter than this (page px, about 3 mm) never snaps (it was SNAP_MIN, 30)
const SNAP_ANIM = 150;           // snap: the soft cross-fade, ms
export const GRAB = 12;          // selection corners: px on screen (12 px at zoom 1)
export const HANDLE_REACH = 20;  // shape handles (select tool): px on screen (20 px at zoom 1), a pen tip needs room
const SEL_BLUE = '#2F4BB8';      // the selection box (the paper is white in both modes)

const P = new Map();             // page id -> { strokes (by seq), byId, svg, img, hl, pen, hlo (opacity -> group), els (id -> path), w, h }
const boxes = new WeakMap();     // record -> [x0, y0, x1, y1], its points' bounding box
const T = { tool: 'pen', lastInk: 'pen', style: { colour: '#000000', width: 2.5, dash: 'solid', opacity: 1 } };
// what restyle hands out: its own colour, and the pen's and the highlighter's current settings (the tray keeps these up to date)
const ST = { pen: { colour: '#000000', width: 2.5, dash: 'solid' }, highlighter: { colour: '#FFC107', width: 18, opacity: 0.4 }, restyle: null };
let doOp = (op) => op.redo();
let onChange = null;             // optional: told the page id after every stroke change (apply), the page list's thumbs
let G = null;                    // the gesture in progress
let LAST = null;                 // the last finished pen or highlighter stroke, raw: { points, pointerType, z, n, len, classify, snapped, at, fit? }
let FIT = null;                  // the last classify's parabola fit when it returned a parabola: { p, a } (its residual, the arc's), else null
let ring = null, hring = null, deskEl = null, deskBox = null;
let SEL = null;                  // the selection: { page, ids, g, chips, deg, z }
let CLIP = null;                 // the selection clipboard: { recs (deep copies, by seq), box (their selBox) }
let toast = null, openMenuAt = null, selectTool = null;   // optional, from app.js: a toast, the menu at a point, the tray's select tool
let stickiesOn = () => [];       // pw-v9c, from app.js: a page id -> its on-page stickies [{ id, x, y, w, colour }] (thumbSvg, pdfout)
let cutOut = null;               // pw-v9e, from app.js: (pageId, a copy of the picture's record) -> the Cut out sheet (js/cutout.js)
// the chips' four icons (the same drawing style as SVG_BIN in js/app.js)
const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">';
const SVG_COPY = ICON + '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>';
const SVG_CUT = ICON + '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.3 8L20 18M8.3 16L20 6"/></svg>';   // scissors: two loops, two crossed blades
const SVG_PLUS = ICON + '<path d="M12 5v14M5 12h14"/></svg>';
const SVG_BIN = ICON + '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/></svg>';
const SVG_LOCK = ICON + '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';     // U4c: a closed padlock (Lock)
const SVG_UNLOCK = ICON + '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/></svg>';  // an open one (Unlock)
const SVG_WAND = ICON + '<path d="M4 20 14 10"/><path d="M15 3v3M13.5 4.5h3M19 7v2M18 8h2M18 13l1.2 1.2M20 11l-1 1"/></svg>';   // pw-v9e: Cut out (the mock's wand)

const uuid = () => crypto.randomUUID();
const r1 = (v) => Math.round(v * 10) / 10;
const bySeq = (a, b) => a.seq - b.seq;

export function initInk(o) {
  if (o.doOp) doOp = o.doOp;
  if (o.onChange) onChange = o.onChange;
  if (o.toast) toast = o.toast;
  if (o.openMenuAt) openMenuAt = o.openMenuAt;
  if (o.selectTool) selectTool = o.selectTool;
  if (o.stickiesOn) stickiesOn = o.stickiesOn;
  if (o.cutOut) cutOut = o.cutOut;
  deskEl = o.desk || document.getElementById('desk');
  deskEl.addEventListener('pointerleave', hideHandle);
  // the selection's handles and chips keep their size on screen: redraw them when the zoom changes
  const stack = deskEl.querySelector('#stack');
  if (stack) new MutationObserver(() => { if (SEL && SEL.z !== view().z) renderSel(); })
    .observe(stack, { attributes: true, attributeFilter: ['data-zoom', 'style'] });
}
export function setTool(tool, style) {
  if (tool !== T.tool) { clearSelection(); hideHandle(); }
  T.tool = tool; if (style) T.style = { ...style };
  if (tool === 'pen' || tool === 'highlighter') T.lastInk = tool;   // the overlap tie-break (topAt) follows it
}
export function setStyles(pen, highlighter, restyle) { ST.pen = { ...pen }; ST.highlighter = { ...highlighter }; ST.restyle = restyle ? { ...restyle } : null; }
export function tool() { return { tool: T.tool, lastInk: T.lastInk, style: { ...T.style } }; }
export function busy() { return !!G; }   // a gesture is running (the pen button flip waits for the lift)

// ---------------------------------------------------------------- the model
function data(id) {
  let d = P.get(id);
  if (!d) {
    const strokes = store.load(id).sort(bySeq);
    d = { strokes, byId: new Map(strokes.map((r) => [r.id, r])), svg: null, img: null, hl: null, pen: null, hlo: new Map(), els: new Map(), w: 0, h: 0 };
    P.set(id, d);
  }
  return d;
}
export function lastStroke() { return LAST; }
export function strokesOf(pageId) { return data(pageId).strokes.slice(); }
export function copyStrokes(pageId) { return JSON.parse(JSON.stringify(data(pageId).strokes)); }

// a shape's outline as a polyline (hit tests now; Part B draws shapes with SVG primitives); n: how many points a
// circle, ellipse, arc or parabola gets (48 for the hit tests, more when it turns into ink)
export function outline(rec, n = 48) {
  const d = rec.data || {};
  if (rec.kind === 'image') return imgCorners(rec);                // U4c: the turned box's four corners
  if (rec.kind === 'axes') {                                       // U5e: its box's four corners, then the axes' ends
    const a = axesGeom(rec), b = a && a.box;
    return a ? [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], ...a.ends] : [];
  }
  if (d.type === 'line' || d.type === 'arrow') return [[d.x1, d.y1], [d.x2, d.y2]];
  if ((d.type === 'rect' || d.type === 'triangle') && d.points && d.points.length) return [...d.points, d.points[0]];
  if (d.type === 'circle' || d.type === 'ellipse') {
    const rx = d.type === 'circle' ? d.r : d.rx, ry = d.type === 'circle' ? d.r : d.ry, out = [];
    const tu = d.type === 'ellipse' ? d.angle || 0 : 0, c = [d.cx, d.cy];
    for (let k = 0; k <= n; k++) { const a = (k / n) * 2 * Math.PI; out.push(turn([d.cx + rx * Math.cos(a), d.cy + ry * Math.sin(a)], c, tu)); }
    return out;
  }
  if (d.type === 'arc' || d.type === 'carrow') {                   // n points from the start to the end (a curved arrow: its shaft)
    const g = arcGeom(d);
    if (!g) return [[d.x1, d.y1], [d.xm, d.ym], [d.x2, d.y2]];
    const out = [[d.x1, d.y1]], m = n - 1;
    for (let k = 1; k < m; k++) { const a = g.t1 + (g.sweep * k) / m; out.push([g.ox + g.r * Math.cos(a), g.oy + g.r * Math.sin(a)]); }
    out.push([d.x2, d.y2]);
    return out;
  }
  if (d.type === 'parabola') {                                     // n points along the curve, t = 0 to 1
    const out = [];
    for (let k = 0; k < n; k++) out.push(qbez(d, k / (n - 1)));
    return out;
  }
  return [];
}
// a parabola's point at t (0 = the start, 1 = the end): the quadratic Bezier (1-t)^2 P0 + 2t(1-t) C + t^2 P2
function qbez(d, t) {
  const u = 1 - t;
  return [u * u * d.x1 + 2 * u * t * d.cx + t * t * d.x2, u * u * d.y1 + 2 * u * t * d.cy + t * t * d.y2];
}
// an arc's circle, through its start, middle and end: { ox, oy, r, t1 (the start's angle), sweep (signed, radians:
// plus is the way angles grow on the page, SVG's sweep flag 1), te (the unit tangent at the end, the way the arc
// travels from the start through the middle to the end: a curved arrow's head points along it) }; null when the three
// sit in a line (the middle under 0.5 px off the chord) or the ends meet
function arcGeom(d) {
  const ax = d.x1, ay = d.y1, bx = d.xm, by = d.ym, cx = d.x2, cy = d.y2, chord = Math.hypot(cx - ax, cy - ay);
  if (!chord || Math.abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / chord < 0.5) return null;
  const D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  const a2 = ax * ax + ay * ay, b2 = bx * bx + by * by, c2 = cx * cx + cy * cy;
  const ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / D, oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / D;
  const t1 = Math.atan2(ay - oy, ax - ox), tm = Math.atan2(by - oy, bx - ox), t2 = Math.atan2(cy - oy, cx - ox);
  const toEnd = nrmA(t2 - t1), sweep = nrmA(tm - t1) <= toEnd ? toEnd : toEnd - 2 * Math.PI, sg = sweep > 0 ? 1 : -1;
  return { ox, oy, r: Math.hypot(ax - ox, ay - oy), t1, sweep, te: [-sg * Math.sin(t2), sg * Math.cos(t2)] };
}
// a curved arrow's head direction (unit) and its shaft's length: the arc's end tangent and length; three points in a
// line: from the middle to the end, the two straight pieces' length
function carrowDir(d) {
  const g = arcGeom(d);
  if (g) return { u: g.te, L: g.r * Math.abs(g.sweep) };
  const dx = d.x2 - d.xm, dy = d.y2 - d.ym, l = Math.hypot(dx, dy) || 1;
  return { u: [dx / l, dy / l], L: Math.hypot(d.xm - d.x1, d.ym - d.y1) + Math.hypot(dx, dy) };
}
const nrmA = (t) => ((t % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);   // an angle in [0, 2 pi)
// a shape as plain ink (the area eraser, pw-v4l): one or two pen or highlighter records (the inHl rule picks the kind,
// so a highlighter-born shape's ink stays in its .hlo group), same page, seq and style, fresh ids, points every 3 px
// along the outline. Closed shapes give ONE closed polyline (its last point repeats the first); an arrow gives two,
// the shaft and the head (the head's two lines through the tip, where makeEl draws them, solid like the drawn head); a
// curved arrow too: the arc's ink and the head's.
const INK_STEP = 3;
function densify(poly, step) {                                     // every vertex kept, no gap over step
  if (!poly.length) return [];
  const out = [rp(poly[0])];
  for (let i = 1; i < poly.length; i++) {
    const a = poly[i - 1], b = poly[i], k = Math.max(1, Math.ceil(dist(a, b) / step));
    for (let j = 1; j < k; j++) out.push(rp([a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k]));
    out.push(rp(b));
  }
  return out;
}
function shapeToInk(rec) {
  const d = rec.data || {}, kind = inHl(rec) ? 'highlighter' : 'pen';
  const ink = (pts, style = rec.style) => ({ id: uuid(), page_id: rec.page_id, seq: rec.seq, kind, style: { ...style }, data: { points: pts } });
  const head = () => ink(densify(arrowHeadPts(d, (rec.style && rec.style.width) || 2.5), INK_STEP), { ...rec.style, dash: 'solid' });
  if (d.type === 'arrow') return [ink(densify([[d.x1, d.y1], [d.x2, d.y2]], INK_STEP)), head()];
  let len = 0;                                                     // curves: enough points for a 3 px step
  if (d.type === 'circle') len = 2 * Math.PI * d.r;
  else if (d.type === 'ellipse') { const a = d.rx, b = d.ry; len = Math.PI * (3 * (a + b) - Math.sqrt((3 * a + b) * (a + 3 * b))); }
  else if (d.type === 'arc' || d.type === 'carrow') { const g = arcGeom(d); len = g ? g.r * Math.abs(g.sweep) : 0; }
  else if (d.type === 'parabola') len = polyLen(outline(rec, 96));
  const o = outline(rec, Math.max(48, Math.ceil(len / INK_STEP)));
  if (o.length < 2) return [];
  const closed = d.type === 'rect' || d.type === 'triangle' || d.type === 'circle' || d.type === 'ellipse';
  const pts = densify(o, INK_STEP);
  if (closed) pts[pts.length - 1] = pts[0].slice();
  return d.type === 'carrow' ? [ink(pts), head()] : [ink(pts)];
}
// the point q turned deg degrees about c (plus = clockwise on the page, the way SVG's rotate() turns)
function turn(q, c, deg) {
  if (!deg) return q;
  const t = deg * Math.PI / 180, cs = Math.cos(t), sn = Math.sin(t), x = q[0] - c[0], y = q[1] - c[1];
  return [c[0] + x * cs - y * sn, c[1] + x * sn + y * cs];
}
const nrmDeg = (a) => { const v = ((a % 360) + 540) % 360 - 180; return v === -180 ? 180 : v; };   // degrees in (-180, 180]
const pointsOf = (rec) => (rec.kind === 'image' ? closedCorners(rec)            // U4c: the turned box, closed (its four sides are segments)
  : rec.kind === 'shape' || rec.kind === 'axes' ? outline(rec) : ((rec.data && rec.data.points) || []));
// ---------------------------------------------------------------- U4c: pictures (the head's "Pictures" block)
export const isImg = (rec) => !!rec && rec.kind === 'image';
const isLocked = (rec) => isImg(rec) && !!(rec.data && rec.data.locked);
const q2 = (v) => Math.round(v * 100) / 100;
// the box's corners (top-left, top-right, bottom-right, bottom-left before the turn), turned rot degrees about its centre
function imgCorners(rec) {
  const d = rec.data || {}, x = +d.x || 0, y = +d.y || 0, w = +d.w || 0, h = +d.h || 0, c = [x + w / 2, y + h / 2];
  return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map((q) => turn(q, c, +d.rot || 0));
}
function closedCorners(rec) { const q = imgCorners(rec); return [...q, q[0]]; }
// (x, y) inside the turned box, grown by pad page px on every side
function inImg(rec, x, y, pad = 0) {
  const d = rec.data || {}, w = +d.w || 0, h = +d.h || 0, c = [(+d.x || 0) + w / 2, (+d.y || 0) + h / 2];
  const [lx, ly] = turn([x, y], c, -(+d.rot || 0));
  return Math.abs(lx - c[0]) <= w / 2 + pad && Math.abs(ly - c[1]) <= h / 2 + pad;
}
// the matrix [a, b, c, d, e, f] (page px, y down) that puts the unit square of an image (PDF image space: v up) on the
// turned box: the u axis is the top edge turned (w cos, w sin), the v axis the left edge upwards turned (h sin, -h cos),
// the origin the box's bottom-left corner (x, y + h) turned about the centre. js/pdfout.js draws the picture with it.
export function imageMatrix(rec) {
  const d = rec.data || {}, w = +d.w || 0, h = +d.h || 0, x = +d.x || 0, y = +d.y || 0, t = (+d.rot || 0) * Math.PI / 180;
  const o = turn([x, y + h], [x + w / 2, y + h / 2], +d.rot || 0);
  return [w * Math.cos(t), w * Math.sin(t), h * Math.sin(t), -h * Math.cos(t), o[0], o[1]];
}
const mimeOf = (path) => (/\.jpe?g$/i.test(String(path)) ? 'image/jpeg' : 'image/png');
const URLS = new Map();          // path -> the Blob URL of the device copy (one per path while the app runs)
const WANT = new Map();          // path -> { busy, tries, t }: the bytes asked for, or a retry waiting
const IMG_BACK = [2000, 5000, 10000, 30000];
// the device copy of a picture's file as a Blob URL (a blob of the wrong type, as a bucket may hand back, is typed by the path)
export function keepUrl(path, blob) {
  if (!path || !blob || URLS.has(path)) return;
  const t = mimeOf(path);
  URLS.set(path, URL.createObjectURL(blob.type === t ? blob : new Blob([blob], { type: t })));
  const w = WANT.get(path);
  if (w) { clearTimeout(w.t); WANT.delete(path); }
}
const urlOf = (path) => { const u = URLS.get(path); if (!u) wantImg(path); return u || null; };
// ask for a picture's bytes (the device copy, else the bucket); none yet: again after 2, 5, 10, 30 s
function wantImg(path) {
  if (!path || URLS.has(path)) return;
  let w = WANT.get(path);
  if (w && (w.busy || w.t)) return;
  if (!w) { w = { busy: false, tries: 0, t: 0 }; WANT.set(path, w); }
  w.busy = true;
  const later = () => { w.busy = false; w.t = setTimeout(() => { w.t = 0; wantImg(path); }, IMG_BACK[Math.min(w.tries++, IMG_BACK.length - 1)]); };
  bytesOf(path).then((blob) => { if (!blob) { later(); return; } w.busy = false; gotImg(path, blob); }, later);
}
addEventListener('online', () => { for (const [p, w] of WANT) if (w.t) { clearTimeout(w.t); w.t = 0; w.tries = 0; wantImg(p); } });
// a picture's bytes are here now: every <g> of that path gets its <image>, and the pages holding it are told (their thumbs)
function gotImg(path, blob) {
  keepUrl(path, blob);
  for (const [pid, d] of P) {
    let hit = false;
    for (const r of d.strokes) {
      if (!isImg(r) || !r.data || r.data.path !== path) continue;
      hit = true;
      const el = d.els.get(r.id);
      if (el) setImg(el, r);
    }
    if (hit && onChange) onChange(pid, { remote: true });
  }
}
// js/pdfin.js onBytes: some file's bytes landed on this device (a download); a picture waiting for them draws now
export function bytesArrived(path) { if (WANT.has(path)) { const w = WANT.get(path); clearTimeout(w.t); w.t = 0; wantImg(path); } }
// the share images and the page picture (app.js renderPage): each picture's file as a data URL, once per path; throws
// when a file is not on this device yet (snap.js tries again later, the share says so)
export async function imageHrefs(recs) {
  const out = new Map();
  for (const r of recs || []) {
    const path = isImg(r) && r.data && r.data.path;
    if (!path || out.has(path)) continue;
    const blob = await bytesOf(path);
    if (!blob) throw new Error('The picture is not on this device yet');
    const typed = blob.type === mimeOf(path) ? blob : new Blob([blob], { type: mimeOf(path) });
    out.set(path, await new Promise((ok, no) => { const f = new FileReader(); f.onload = () => ok(f.result); f.onerror = () => no(f.error); f.readAsDataURL(typed); }));
  }
  return out;
}
// the picture's <g>: its <image> (or the wait rectangle) at the box, turned about the box's centre. hrefOf: the data
// URLs of a render (thumbSvg's hrefs); none = this device's Blob URLs (asked for when missing)
function setImg(g, rec, hrefOf) {
  const d = rec.data || {}, href = hrefOf ? hrefOf(d.path) : urlOf(d.path), tag = href ? 'image' : 'rect';
  let el = g.firstChild;
  if (!el || el.tagName !== tag) { el = document.createElementNS(SVGNS, tag); g.replaceChildren(el); }
  const x = +d.x || 0, y = +d.y || 0, w = Math.max(0, +d.w || 0), h = Math.max(0, +d.h || 0), a = +d.rot || 0;
  el.setAttribute('x', f2(x)); el.setAttribute('y', f2(y)); el.setAttribute('width', f2(w)); el.setAttribute('height', f2(h));
  if (a) el.setAttribute('transform', `rotate(${f2(a)} ${f2(x + w / 2)} ${f2(y + h / 2)})`); else el.removeAttribute('transform');
  if (href) {
    el.setAttribute('preserveAspectRatio', 'none');
    if (el.getAttribute('href') !== href) el.setAttribute('href', href);
  } else {
    el.setAttribute('class', 'imgWait'); el.setAttribute('fill', '#F1F3F5'); el.setAttribute('stroke', '#B8BEC6');
    el.setAttribute('stroke-width', '1.5'); el.setAttribute('stroke-dasharray', '6 4');
  }
}
function boxOf(rec) {
  let b = boxes.get(rec);
  if (!b) {
    b = [Infinity, Infinity, -Infinity, -Infinity];
    for (const [x, y] of pointsOf(rec)) { if (x < b[0]) b[0] = x; if (y < b[1]) b[1] = y; if (x > b[2]) b[2] = x; if (y > b[3]) b[3] = y; }
    boxes.set(rec, b);
  }
  return b;
}

// ---------------------------------------------------------------- rendering
const f1 = (v) => String(r1(v));
export function pathD(pts) {
  const n = pts.length;
  if (!n) return '';
  const p = (q) => f1(q[0]) + ' ' + f1(q[1]);
  if (n === 1) return 'M' + p(pts[0]) + 'h0.01';
  if (n === 2) return 'M' + p(pts[0]) + 'L' + p(pts[1]);
  // smooth: quadratic curves through the midpoints, each point a control point
  let d = 'M' + p(pts[0]);
  for (let i = 1; i < n - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    d += 'Q' + p(a) + ' ' + f1((a[0] + b[0]) / 2) + ' ' + f1((a[1] + b[1]) / 2);
  }
  return d + 'L' + p(pts[n - 1]);
}
function dOf(rec) {
  if (rec.kind !== 'shape') return pathD(pointsOf(rec));
  const o = outline(rec);
  return o.length ? 'M' + o.map((q) => f1(q[0]) + ' ' + f1(q[1])).join('L') : '';
}
export const dashOf = (w) => { const a = f1(Math.max(4, w * 3)); return a + ' ' + a; };
function styleEl(el, rec) {
  const s = rec.style || {}, w = s.width || 2.5;
  el.setAttribute('fill', 'none');
  el.setAttribute('stroke', s.colour || '#000000');
  el.setAttribute('stroke-width', String(w));
  el.setAttribute('stroke-linejoin', 'round');
  el.setAttribute('class', rec.kind);
  if (inHl(rec)) {
    el.setAttribute('stroke-linecap', 'round');             // fully opaque: its .hlo group does the see-through
    el.removeAttribute('stroke-opacity');
  } else {
    el.setAttribute('stroke-linecap', 'round');
    if (s.opacity !== undefined && s.opacity !== 1) el.setAttribute('stroke-opacity', String(s.opacity));
  }
  if (s.dash === 'dashed') el.setAttribute('stroke-dasharray', dashOf(w));
  else el.removeAttribute('stroke-dasharray');
}
// shapes are SVG primitives: line, polygon (rect, triangle), circle, ellipse, path (arc, parabola); an arrow is a <g> of its
// line and an open head, a curved arrow a <g> of its arc's path and the same head (the head never dashed, so every arrow
// ends the same way)
const SHAPE_TAG = { line: 'line', arrow: 'g', carrow: 'g', rect: 'polygon', triangle: 'polygon', circle: 'circle', ellipse: 'ellipse', arc: 'path', parabola: 'path' };
// U5c: a compass's shape (a FIXED arc or circle) has its needle mark, a filled dot at the centre of radius
// max(1.6, w * 0.55) page px in the shape's colour (the constructions app's drawStroke): it is a <g> of the arc's path
// (or the <circle>) and the dot (circle.needle). Derived from the record every time, never stored, so a move, a turn or a
// resize carries it. { cx, cy, r } or null (not fixed, not an arc or circle, or an arc whose three points lie in a line)
export function needleOf(rec) {
  const d = rec && rec.kind === 'shape' && rec.data;
  if (!d || !d.fixed || (d.type !== 'arc' && d.type !== 'circle')) return null;
  const r = Math.max(1.6, ((rec.style && rec.style.width) || 2.5) * 0.55);
  if (d.type === 'circle') return Number.isFinite(d.cx) && Number.isFinite(d.cy) ? { cx: d.cx, cy: d.cy, r } : null;
  const g = arcGeom(d);
  return g ? { cx: g.ox, cy: g.oy, r } : null;
}
const hasNeedle = (rec) => rec.kind === 'shape' && !!rec.data && !!rec.data.fixed && (rec.data.type === 'arc' || rec.data.type === 'circle');
function setNeedle(dot, rec) {
  const n = needleOf(rec), s = rec.style || {};
  if (!n) { dot.setAttribute('display', 'none'); return; }
  dot.removeAttribute('display');
  dot.setAttribute('cx', f1(n.cx)); dot.setAttribute('cy', f1(n.cy)); dot.setAttribute('r', f1(n.r));
  dot.setAttribute('fill', s.colour || '#000000');
  if (!inHl(rec) && s.opacity !== undefined && s.opacity !== 1) dot.setAttribute('fill-opacity', String(s.opacity));
  else dot.removeAttribute('fill-opacity');
}
// the head's three points [one barb's end, the tip, the other barb's end] for a tip, the unit direction the shaft arrives
// in (ux, uy), the shaft's length L (a short shaft gets a smaller head) and the ink width w; both arrow kinds use it
function headPts(tip, ux, uy, L, w) {
  const len = Math.min((L || 1) * 0.45, Math.max(14, w * 4)), a = 28 * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  const b1 = [tip[0] - len * (ux * c - uy * s), tip[1] - len * (uy * c + ux * s)];
  const b2 = [tip[0] - len * (ux * c + uy * s), tip[1] - len * (uy * c - ux * s)];
  return [b1, [tip[0], tip[1]], b2];
}
// U5e: an axes stamp's drawing, worked out from its record every time (nothing but data is stored). data =
// { x0, y0 (the page px where x = 0 and y = 0 would be), px, py (page px per x step and per y step: equal, square
// squares, unless deg), xs, xe, xd, ys, ye, yd (the ranges and steps), deg, line }. A value v sits at x0 + v / xd * px
// across and y0 - v / yd * py up. Ticks, fonts and the drop of the x labels under their axis go by m = min(px, py)
// (0.5 px would put the shared 0 on the -1 of a trig graph); the y labels sit 0.35 py left. Returns null
// for a record it cannot draw, else { lines (the axes, [a, b]), ticks ([a, b]), heads ([barb, tip, barb]), labels
// ({ t, x, y (the baseline), size, anchor, cls }), box [x0, y0, x1, y1], ends (the axes' ends), cross (where the axes
// meet), feet (each tick's point on its axis), outer (each tick's outer end) }
const AX_MAX = 60;
const fmtAx = (v) => { const r = Math.round(v * 100) / 100; return String(Object.is(r, -0) ? 0 : r); };
const onV = (a, b, step) => Math.abs(a - b) <= step * 1e-6;
export function axesGeom(rec) {
  const d = (rec && rec.data) || {}, px = +d.px, py = +d.py, m = Math.min(px, py), w = (rec.style && rec.style.width) || 1.5, line = !!d.line, deg = !!d.deg;
  const okR = (s, e, st) => [s, e, st].every(Number.isFinite) && st > 0 && e > s && (e - s) / st <= AX_MAX + 1e-6;
  if (![d.x0, d.y0, px, py].every(Number.isFinite) || px <= 0 || py <= 0 || !okR(d.xs, d.xe, d.xd) || (!line && !okR(d.ys, d.ye, d.yd))) return null;
  const X = (v) => d.x0 + (v / d.xd) * px, Y = (v) => d.y0 - (line ? 0 : (v / d.yd) * py);
  const nx = Math.floor((d.xe - d.xs) / d.xd + 1e-6), ny = line ? 0 : Math.floor((d.ye - d.ys) / d.yd + 1e-6);
  const ax = d.xs <= 0 && d.xe >= 0 ? 0 : d.xs;                   // the y-axis stands at x = 0, else at the left end
  const ay = line ? 0 : d.ys <= 0 && d.ye >= 0 ? 0 : d.ys;        // the x-axis lies at y = 0, else at the bottom
  const xA = X(ax), yA = Y(ay), t = Math.max(3, 0.14 * m);
  const xL = X(d.xs) - (line ? 0.6 * px : 0), xR = X(d.xs + nx * d.xd) + 0.6 * px;
  const lines = [[[xL, yA], [xR, yA]]], heads = [headPts([xR, yA], 1, 0, xR - xL, w)];
  if (line) heads.push(headPts([xL, yA], -1, 0, xR - xL, w));
  let yB = 0, yT = 0;
  if (!line) {
    yB = Y(d.ys); yT = Y(d.ys + ny * d.yd) - 0.6 * py;
    lines.push([[xA, yB], [xA, yT]]);
    heads.push(headPts([xA, yT], 0, -1, yB - yT, w));
  }
  const ticks = [], feet = [], outer = [], labels = [];
  const fs = 0.3 * m, fl = 0.32 * m, mid = 0.35 * fs;               // mid: the digits' half height
  const evOf = (q) => (q / CM < 0.35 ? 4 : q / CM < 0.7 ? 2 : 1), evX = evOf(px), evY = evOf(py);
  const pick = (k, kA, every) => (((k - kA) % every) + every) % every === 0;
  const both0 = !line && ax === 0 && ay === 0;
  const kx = Math.round((ax - d.xs) / d.xd);
  for (let k = 0; k <= nx; k++) {
    const v = d.xs + k * d.xd, x = X(v), atY = !line && onV(v, ax, d.xd);
    if (!atY) { ticks.push([[x, yA - t], [x, yA + t]]); feet.push([x, yA]); outer.push([x, yA + t]); }
    if (!pick(k, kx, evX)) continue;
    if (atY && (both0 || d.ys < ay)) continue;                     // the shared 0, or it would sit on the y-axis's line
    labels.push({ t: fmtAx(v) + (deg ? '°' : ''), x, y: yA + 0.5 * m + mid, size: fs, anchor: 'middle', cls: 'num' });
  }
  if (!line) {
    const ky = Math.round((ay - d.ys) / d.yd);
    for (let k = 0; k <= ny; k++) {
      const v = d.ys + k * d.yd, y = Y(v), atX = onV(v, ay, d.yd);
      if (!atX) { ticks.push([[xA - t, y], [xA + t, y]]); feet.push([xA, y]); outer.push([xA - t, y]); }
      if (!pick(k, ky, evY)) continue;
      if (atX && (both0 || d.xs < ax)) continue;                   // the shared 0, or it would sit on the x-axis's line
      labels.push({ t: fmtAx(v), x: xA - 0.35 * py, y: y + mid, size: fs, anchor: 'end', cls: 'num' });
    }
    if (both0) labels.push({ t: '0', x: xA - 0.35 * py, y: yA + 0.5 * m + mid, size: fs, anchor: 'end', cls: 'num zero' });
    labels.push({ t: 'x', x: xR + 0.08 * px, y: yA + 0.5 * m, size: fl, anchor: 'start', cls: 'letter' });
    labels.push({ t: 'y', x: xA - 0.15 * py, y: yT - 0.08 * py, size: fl, anchor: 'end', cls: 'letter' });
  }
  const b = [Infinity, Infinity, -Infinity, -Infinity], grow = (x, y) => { b[0] = Math.min(b[0], x); b[1] = Math.min(b[1], y); b[2] = Math.max(b[2], x); b[3] = Math.max(b[3], y); };
  for (const s of [...lines, ...ticks]) for (const q of s) grow(q[0], q[1]);
  for (const h of heads) for (const q of h) grow(q[0], q[1]);
  for (const l of labels) {                                        // a label's box: about 0.56 em a character, 0.72 em up, 0.2 down
    const wd = l.t.length * 0.56 * l.size, x0 = l.anchor === 'middle' ? l.x - wd / 2 : l.anchor === 'end' ? l.x - wd : l.x;
    grow(x0, l.y - 0.72 * l.size); grow(x0 + wd, l.y + 0.2 * l.size);
  }
  const ends = lines.flat().map((q) => q.slice());
  return { lines, ticks, heads, labels, box: b, ends, cross: line ? (d.xs <= 0 && d.xe >= 0 ? [X(0), yA] : null) : [xA, yA], feet, outer, px, py };
}
const f2 = (v) => String(Math.round(v * 100) / 100);
function setAxes(g, rec) {                                         // the stamp's lines, ticks, heads and labels, drawn again
  const a = axesGeom(rec), colour = (rec.style && rec.style.colour) || '#000000', kids = [];
  if (a) {
    const ln = (q, cls) => { const e = document.createElementNS(SVGNS, 'line'); e.setAttribute('class', cls);
      e.setAttribute('x1', f2(q[0][0])); e.setAttribute('y1', f2(q[0][1])); e.setAttribute('x2', f2(q[1][0])); e.setAttribute('y2', f2(q[1][1])); kids.push(e); };
    a.lines.forEach((q) => ln(q, 'axis'));
    a.ticks.forEach((q) => ln(q, 'tick'));
    for (const h of a.heads) {
      const e = document.createElementNS(SVGNS, 'path');
      e.setAttribute('class', 'head'); e.setAttribute('d', 'M' + h.map((q) => f2(q[0]) + ' ' + f2(q[1])).join('L'));
      kids.push(e);
    }
    for (const l of a.labels) {
      const e = document.createElementNS(SVGNS, 'text');
      e.setAttribute('class', l.cls); e.setAttribute('x', f2(l.x)); e.setAttribute('y', f2(l.y));
      e.setAttribute('font-size', f2(l.size)); e.setAttribute('text-anchor', l.anchor);
      e.setAttribute('font-family', 'Helvetica, Arial, sans-serif'); e.setAttribute('fill', colour); e.setAttribute('stroke', 'none');
      if (l.cls === 'letter') e.setAttribute('font-style', 'italic');
      e.textContent = l.t;
      kids.push(e);
    }
  }
  g.replaceChildren(...kids);
}
function arrowHeadPts(d, w) {                                    // an arrow along its chord, a curved arrow along its end tangent
  if (d.type === 'carrow') { const { u, L } = carrowDir(d); return headPts([d.x2, d.y2], u[0], u[1], L, w); }
  const dx = d.x2 - d.x1, dy = d.y2 - d.y1, L = Math.hypot(dx, dy) || 1;
  return headPts([d.x2, d.y2], dx / L, dy / L, L, w);
}
export function arrowHead(d, w) { return 'M' + arrowHeadPts(d, w).map((q) => f1(q[0]) + ' ' + f1(q[1])).join('L'); }
export function arcD(d) {                                             // M start A r r 0 large sweep end; in a line: straight
  const g = arcGeom(d), p = (x, y) => f1(x) + ' ' + f1(y);
  return g
    ? 'M' + p(d.x1, d.y1) + 'A' + f1(g.r) + ' ' + f1(g.r) + ' 0 ' + (Math.abs(g.sweep) > Math.PI ? 1 : 0) + ' ' + (g.sweep > 0 ? 1 : 0) + ' ' + p(d.x2, d.y2)
    : 'M' + p(d.x1, d.y1) + 'L' + p(d.xm, d.ym) + 'L' + p(d.x2, d.y2);
}
function setGeom(el, rec) {
  if (rec.kind === 'image') { setImg(el, rec); return; }          // U4c: the picture at its box
  if (rec.kind === 'axes') { setAxes(el, rec); return; }           // U5e: the stamp is drawn again whole
  const d = rec.data;
  if ((d.type === 'arc' || d.type === 'circle') && el.tagName === 'g') {   // U5c: a compass shape: the shape, then its needle mark
    const [sh, dot] = el.children;
    if (d.type === 'arc') sh.setAttribute('d', arcD(d));
    else for (const k of ['cx', 'cy', 'r']) sh.setAttribute(k, f1(d[k]));
    setNeedle(dot, rec);
    return;
  }
  const at = (k, v) => el.setAttribute(k, f1(v));
  if (d.type === 'line') { at('x1', d.x1); at('y1', d.y1); at('x2', d.x2); at('y2', d.y2); }
  else if (d.type === 'arrow') {
    const [ln, hd] = el.children;
    for (const k of ['x1', 'y1', 'x2', 'y2']) ln.setAttribute(k, f1(d[k]));
    hd.setAttribute('d', arrowHead(d, (rec.style && rec.style.width) || 2.5));
  } else if (d.type === 'carrow') {                                // the arc's path, then the head along its end tangent
    const [sh, hd] = el.children;
    sh.setAttribute('d', arcD(d));
    hd.setAttribute('d', arrowHead(d, (rec.style && rec.style.width) || 2.5));
  } else if (d.type === 'rect' || d.type === 'triangle') el.setAttribute('points', d.points.map((q) => f1(q[0]) + ',' + f1(q[1])).join(' '));
  else if (d.type === 'circle') { at('cx', d.cx); at('cy', d.cy); at('r', d.r); }
  else if (d.type === 'ellipse') {                                 // a turned ellipse: rotate(angle cx cy), none at 0
    at('cx', d.cx); at('cy', d.cy); at('rx', d.rx); at('ry', d.ry);
    if (d.angle) el.setAttribute('transform', `rotate(${f1(d.angle)} ${f1(d.cx)} ${f1(d.cy)})`); else el.removeAttribute('transform');
  }
  else if (d.type === 'arc') el.setAttribute('d', arcD(d));
  else if (d.type === 'parabola') {                                // M start Q control end
    const p = (x, y) => f1(x) + ' ' + f1(y);
    el.setAttribute('d', 'M' + p(d.x1, d.y1) + 'Q' + p(d.cx, d.cy) + ' ' + p(d.x2, d.y2));
  }
}
function makeEl(rec, hrefOf) {
  if (rec.kind === 'image') {                                      // U4c: a <g> holding the <image> (or the wait rectangle)
    const g = document.createElementNS(SVGNS, 'g');
    g.dataset.id = rec.id; g.dataset.type = 'image'; g.setAttribute('class', 'image');
    setImg(g, rec, hrefOf);
    return g;
  }
  if (rec.kind === 'axes') {                                       // U5e: a <g> of lines, ticks, heads and labels (never dashed)
    const g = document.createElementNS(SVGNS, 'g');
    g.dataset.id = rec.id; g.dataset.type = 'axes';
    styleEl(g, rec); g.removeAttribute('stroke-dasharray');
    setAxes(g, rec);
    return g;
  }
  const shape = rec.kind === 'shape' && rec.data && (hasNeedle(rec) ? 'g' : SHAPE_TAG[rec.data.type]);
  const el = document.createElementNS(SVGNS, shape || 'path');
  el.dataset.id = rec.id;
  styleEl(el, rec);
  if (shape) {
    el.dataset.type = rec.data.type;
    if (rec.data.type === 'arrow' || rec.data.type === 'carrow') {   // the shaft (a line, or the arc's path), then the head
      const hd = document.createElementNS(SVGNS, 'path');
      hd.setAttribute('class', 'head'); hd.setAttribute('stroke-dasharray', 'none');
      el.append(document.createElementNS(SVGNS, rec.data.type === 'arrow' ? 'line' : 'path'), hd);
    } else if (shape === 'g') {                                      // U5c: a compass shape, then its needle mark (filled, no stroke)
      const dot = document.createElementNS(SVGNS, 'circle');
      dot.setAttribute('class', 'needle'); dot.setAttribute('stroke', 'none'); dot.setAttribute('stroke-dasharray', 'none');
      el.append(document.createElementNS(SVGNS, rec.data.type === 'arc' ? 'path' : 'circle'), dot);
    }
    setGeom(el, rec);
  } else el.setAttribute('d', dOf(rec));
  return el;
}
// the layer groups: which group a record's path lives in, made on demand. THE one rule: a highlighter stroke,
// or a shape with opacity under 1 (a highlighter-born shape), lives in the highlighter layer
export const inHl = (rec) => rec.kind === 'highlighter' || (rec.kind === 'shape' && +((rec.style && rec.style.opacity) ?? 1) < 1);
export const opKey = (rec) => String(+((rec.style && rec.style.opacity) ?? 0.4));
const keyOf = (rec) => (rec.kind === 'image' ? 'img' : inHl(rec) ? 'hl' + opKey(rec) : 'pen');
function hloGroup(d, key) {
  let g = d.hlo.get(key);
  if (!g) {
    g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('class', 'hlo'); g.dataset.opacity = key; g.setAttribute('opacity', key);
    d.hlo.set(key, g);
    const after = [...d.hl.children].find((x) => +x.dataset.opacity > +key);   // ascending opacity
    d.hl.insertBefore(g, after || null);
  }
  return g;
}
function groupFor(d, rec) { return rec.kind === 'image' ? d.img : inHl(rec) ? hloGroup(d, opKey(rec)) : d.pen; }   // U4c: pictures in the bottom group
// put a record's path in its group, before the next record (by seq) that shares that group
function place(d, rec, el, idx) {
  const parent = groupFor(d, rec), k = keyOf(rec);
  let next = null;
  for (let j = idx + 1; j < d.strokes.length; j++) {
    const r = d.strokes[j];
    if (keyOf(r) === k) { const e = d.els.get(r.id); if (e && e.parentNode === parent) { next = e; break; } }
  }
  parent.insertBefore(el, next);
}
// take a path out; an opacity group left empty goes too
function unplace(d, el) {
  const g = el.parentNode;
  el.remove();
  if (g && g.classList && g.classList.contains('hlo') && !g.firstChild) { d.hlo.delete(g.dataset.opacity); g.remove(); }
}
function buildLayer(d, w, h) {
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'ink');
  d.img = document.createElementNS(SVGNS, 'g'); d.img.setAttribute('class', 'img');   // U4c: the pictures, under all ink
  d.hl = document.createElementNS(SVGNS, 'g'); d.hl.setAttribute('class', 'hl');
  d.pen = document.createElementNS(SVGNS, 'g'); d.pen.setAttribute('class', 'pen');
  d.hlo = new Map();
  for (const rec of d.strokes) { const el = makeEl(rec); d.els.set(rec.id, el); groupFor(d, rec).appendChild(el); }
  svg.append(d.img, d.hl, d.pen);
  d.svg = svg;
  sizeLayer(d, w, h);
}
function sizeLayer(d, w, h) {
  if (d.w === w && d.h === h) return;
  d.w = w; d.h = h;
  d.svg.setAttribute('width', w); d.svg.setAttribute('height', h);
  d.svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
}

// page.js calls this after it (re)builds the stack: every sheet gets its page's ink layer back
export function attach(sheets) {
  clearSelection();
  for (const el of sheets) {
    const d = data(el.dataset.id), w = parseFloat(el.style.width), h = parseFloat(el.style.height);
    if (!d.svg) buildLayer(d, w, h); else sizeLayer(d, w, h);
    if (el.classList.contains('sticky')) el.insertBefore(d.svg, el.querySelector('.corner'));   // pw-v9c: under the corner mark
    else el.appendChild(d.svg);
  }
}
// pw-v9c: a sticky resized: its layer's room changes, the writing keeps its place and size (a shrink clips it, nothing goes)
export function fitLayer(id, w, h = w) {
  const d = P.get(id);
  if (d && d.svg) { sizeLayer(d, w, h); if (SEL && SEL.page === id) renderSel(); }
}
// pw-v9c: the on-page stickies of a page (app.js's rule: the sticky's square overlaps the page's), for js/pdfout.js too
export function stickiesOnPage(pageId) { try { return stickiesOn(pageId) || []; } catch (_) { return []; } }

// the page list (pw-v4i): a page's ink as its own small <svg>, built from the records with the same builders as the
// page (makeEl + groupFor, in seq order, highlighter groups below the pen group), so a thumb shows what the page
// shows. Never a clone of the live layer: a page that is not attached has none. viewBox = the page in page px
// (the attached size, else its orientation's size); the thumb's .paper already has the page's aspect ratio.
// U3b: `recs` given = draw those records instead (a page picture made from the database's copy of a page this device
// has not read); the page's own model is not touched then.
// U4a: `page` is the page row (a PDF page has its own shape, page.js pageSize) or, as before, just an orientation.
// U4c: pictures in a bottom <g class="img">; `hrefs` given (a Map path -> data URL, imageHrefs) = those instead of this
// device's Blob URLs (a serialised SVG drawn through an <img> cannot reach a Blob URL).
export function thumbSvg(pageId, page = 'portrait', recs = null, hrefs = null) {
  const d = recs ? { strokes: recs.slice().sort(bySeq), w: 0, h: 0 } : data(pageId), sz = d.w && d.h ? { w: d.w, h: d.h } : pageSize(page);
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'thumbInk');
  svg.setAttribute('viewBox', `0 0 ${sz.w} ${sz.h}`);
  svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('pointer-events', 'none');
  const t = { img: document.createElementNS(SVGNS, 'g'), hl: document.createElementNS(SVGNS, 'g'), pen: document.createElementNS(SVGNS, 'g'), hlo: new Map() };
  t.img.setAttribute('class', 'img'); t.hl.setAttribute('class', 'hl'); t.pen.setAttribute('class', 'pen');
  const hrefOf = hrefs ? (path) => hrefs.get(path) || null : null;
  for (const rec of d.strokes) groupFor(t, rec).appendChild(makeEl(rec, hrefOf));
  svg.append(t.img, t.hl, t.pen);
  const sk = stickiesOnPage(pageId);
  if (sk.length) svg.append(stickyGroup(sk, sz, hrefOf));                 // pw-v9c: on top of the page's ink
  return svg;
}
// pw-v9c: a page's on-page stickies as one <g>, clipped to the page; each a rounded square (radius 3) in its colour, the
// strip in the darker shade, then its strokes moved by its x, y, all clipped to the square. The ids are unique per call.
let skN = 0;
function stickyGroup(list, sz, hrefOf) {
  const el = (tag, at) => { const e = document.createElementNS(SVGNS, tag); for (const k in at) e.setAttribute(k, at[k]); return e; };
  const n = ++skN, defs = el('defs', {}), all = el('g', { class: 'stickies', 'clip-path': `url(#pwskp${n})` });
  const pc = el('clipPath', { id: `pwskp${n}` });
  pc.append(el('rect', { x: 0, y: 0, width: sz.w, height: sz.h }));
  defs.append(pc);
  list.forEach((s, j) => {
    const [c1, c2] = SK_COLOURS[s.colour] || SK_COLOURS.yellow, id = `pwsk${n}-${j}`;
    const cp = el('clipPath', { id });
    cp.append(el('rect', { x: 0, y: 0, width: s.w, height: s.w, rx: 3, ry: 3 }));
    defs.append(cp);
    const g = el('g', { class: 'sticky', 'data-id': s.id, transform: `translate(${r1(s.x)} ${r1(s.y)})` });
    const body = el('g', { 'clip-path': `url(#${id})` });
    body.append(el('rect', { class: 'skPaper', x: 0, y: 0, width: s.w, height: s.w, fill: c1 }),
                el('rect', { class: 'skStrip', x: 0, y: 0, width: s.w, height: SK_STRIP, fill: c2 }));
    const t = { img: el('g', { class: 'img' }), hl: el('g', { class: 'hl' }), pen: el('g', { class: 'pen' }), hlo: new Map() };
    for (const rec of data(s.id).strokes) groupFor(t, rec).appendChild(makeEl(rec, hrefOf));
    body.append(t.img, t.hl, t.pen);
    g.append(body);
    all.append(g);
  });
  const out = el('g', {});
  out.append(defs, all);
  return out;
}

// ---------------------------------------------------------------- changes (every one is saved)
const dirty = new Set();
let saveT = null;
function schedule(id) { dirty.add(id); if (!saveT) saveT = setTimeout(flush, 0); }
export function flush() {
  clearTimeout(saveT); saveT = null;
  for (const id of dirty) { const d = P.get(id); if (d) store.save(id, d.strokes); }
  dirty.clear();
}
addEventListener('pagehide', flush);
document.addEventListener('visibilitychange', () => { if (document.hidden) flush(); });

function apply(pageId, removeIds, adds, remote = false) {
  const d = data(pageId), gone = [], added = [];
  if (removeIds.length) {
    const rm = new Set(removeIds.filter((id) => d.byId.has(id)));
    if (rm.size) {
      d.strokes = d.strokes.filter((r) => !rm.has(r.id));
      for (const id of rm) { d.byId.delete(id); gone.push(id); const el = d.els.get(id); if (el) { unplace(d, el); d.els.delete(id); } }
    }
  }
  for (const rec of adds) {
    if (d.byId.has(rec.id)) continue;
    added.push(rec);
    let lo = 0, hi = d.strokes.length;                     // after every stroke with the same or an earlier seq
    while (lo < hi) { const m = (lo + hi) >> 1; if (d.strokes[m].seq <= rec.seq) lo = m + 1; else hi = m; }
    d.strokes.splice(lo, 0, rec); d.byId.set(rec.id, rec);
    if (d.svg) {
      const el = d.els.get(rec.id) || makeEl(rec);
      d.els.set(rec.id, el);
      place(d, rec, el, lo);
    }
  }
  if (remote) store.applyRemote(pageId, gone, added);  // U3d: mirror and cache only, the database has it already
  else {
    schedule(pageId);
    store.change(pageId, gone, added);                 // U3a: the exact change joins the queue for the database
  }
  if (SEL && SEL.page === pageId) syncSel();          // an undo, redo or move: the box follows its strokes
  if (onChange) onChange(pageId, remote ? { remote: true } : undefined);   // the page list refreshes that page's thumb
}

// U3d: a change another device made (js/live.js). Not on this device's ink yet (the note was never opened here): the
// mirror takes it when it holds the page, otherwise nothing (the next ensure reads the database). Rows that arrive
// during a gesture wait for the lift, in order.
const held = [];
let heldT = 0;
export function applyRemote(pageId, removeIds, adds) {
  if (G || held.length) { held.push([pageId, removeIds, adds]); if (!heldT) heldT = setTimeout(drainHeld, 100); return; }
  remoteNow(pageId, removeIds, adds);
}
function drainHeld() {
  heldT = 0;
  if (G) { heldT = setTimeout(drainHeld, 100); return; }
  while (held.length) remoteNow(...held.shift());
}
function remoteNow(pageId, removeIds, adds) {
  if (!P.has(pageId)) {
    if (store.applyRemote(pageId, removeIds, adds) && onChange) onChange(pageId, { remote: true });
    return;
  }
  if (SEL && SEL.page === pageId) clearSelection();   // the box must not point at a stroke that is gone
  apply(pageId, removeIds, adds, true);
}

// one undo step: [{ page, removed: [records], added: [records] }]
function changeOp(changes) {
  return {
    pages: changes.map((c) => c.page),
    redo: () => changes.forEach((c) => apply(c.page, c.removed.map((r) => r.id), c.added)),
    undo: () => changes.slice().reverse().forEach((c) => apply(c.page, c.added.map((r) => r.id), c.removed)),
  };
}

// for the page menu (app.js): put records on a page, erase a page, forget a page that is gone for good
export function put(pageId, recs) { apply(pageId, [], recs); }
// U4c: page Erase takes the ink only; pictures stay (an axes stamp goes with the ink, as before)
export function erasePageOp(pageId) {
  const all = data(pageId).strokes.filter((r) => !isImg(r));
  return all.length ? changeOp([{ page: pageId, removed: all, added: [] }]) : null;
}
export function forget(pageId) { P.delete(pageId); dirty.delete(pageId); store.forget(pageId); }

// U3a: the database holds a different set of records for this page (js/store.js reconcile). Swap them in and redraw the
// page's layer; no undo step, nothing to save (they came from the store). An open selection on the page clears first.
export function replace(pageId, recs) {
  if (SEL && SEL.page === pageId) clearSelection();
  const d = P.get(pageId);
  if (!d) return;                                      // not read yet: the next data() reads the store
  const strokes = recs.slice().sort(bySeq);
  d.strokes = strokes; d.byId = new Map(strokes.map((r) => [r.id, r]));
  if (d.svg) {
    d.els.clear(); d.hlo = new Map(); d.img.replaceChildren(); d.hl.replaceChildren(); d.pen.replaceChildren();
    for (const rec of strokes) { const el = makeEl(rec); d.els.set(rec.id, el); groupFor(d, rec).appendChild(el); }
  }
  if (onChange) onChange(pageId, { remote: true });    // the page list's thumb follows; no picture (U3d)
}

// ---------------------------------------------------------------- geometry
function segDist2(px, py, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
  let t = L2 ? ((px - a[0]) * dx + (py - a[1]) * dy) / L2 : 0;
  t = Math.max(0, Math.min(1, t));
  const x = a[0] + t * dx - px, y = a[1] + t * dy - py;
  return x * x + y * y;
}
function near(rec, x, y, reach) {
  const b = boxOf(rec);
  if (x < b[0] - reach || x > b[2] + reach || y < b[1] - reach || y > b[3] + reach) return false;
  const r2 = reach * reach;
  if (rec.kind === 'image') return inImg(rec, x, y, reach);       // U4c: inside its turned box (grown by reach)
  if (rec.kind === 'axes') { const a = axesGeom(rec); return !!a && a.lines.some((s) => segDist2(x, y, s[0], s[1]) <= r2); }   // U5e: on an axis line
  const pts = pointsOf(rec);
  if (pts.length === 1) return (pts[0][0] - x) ** 2 + (pts[0][1] - y) ** 2 <= r2;
  for (let i = 1; i < pts.length; i++) if (segDist2(x, y, pts[i - 1], pts[i]) <= r2) return true;
  return false;
}
// where segment a-b crosses the circle (cx, cy, R): t values strictly inside (0, 1)
function crossings(a, b, cx, cy, R) {
  const dx = b[0] - a[0], dy = b[1] - a[1], fx = a[0] - cx, fy = a[1] - cy;
  const A = dx * dx + dy * dy, B = 2 * (fx * dx + fy * dy), C = fx * fx + fy * fy - R * R;
  const disc = B * B - 4 * A * C;
  if (!A || disc <= 1e-9) return [];
  const s = Math.sqrt(disc);
  return [(-B - s) / (2 * A), (-B + s) / (2 * A)].filter((t) => t > 0 && t < 1);
}
const polyLen = (pts) => { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; };
// cut a polyline with a circle: the runs left outside it, or null when the circle misses it
function cut(pts, cx, cy, R) {
  const inside = (q) => (q[0] - cx) ** 2 + (q[1] - cy) ** 2 < R * R;
  if (pts.length === 1) return inside(pts[0]) ? [] : null;
  const runs = [];
  let changed = false, cur = inside(pts[0]) ? null : [pts[0]];
  if (!cur) changed = true;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    for (const t of crossings(a, b, cx, cy, R)) {
      const q = [r1(a[0] + t * (b[0] - a[0])), r1(a[1] + t * (b[1] - a[1]))];
      if (cur) { cur.push(q); runs.push(cur); cur = null; } else cur = [q];
      changed = true;
    }
    if (inside(b)) { if (cur) { runs.push(cur); cur = null; changed = true; } }
    else if (cur) cur.push(b);
    else { cur = [b]; changed = true; }
  }
  if (cur) runs.push(cur);
  return changed ? runs.filter((r) => r.length > 1 && polyLen(r) >= 1) : null;
}
// cut a shape's ink (pw-v4l): for a closed loop whose first and last runs both survive (the bite missed the seam),
// the last run and the first run join into one piece, so one bite leaves one open piece
function cutInk(pts, cx, cy, R) {
  const runs = cut(pts, cx, cy, R), n = pts.length;
  if (!runs || runs.length < 2 || n < 3) return runs;
  const a = pts[0], z = pts[n - 1], first = runs[0], lastRun = runs[runs.length - 1];
  if (a[0] !== z[0] || a[1] !== z[1] || first[0] !== a || lastRun[lastRun.length - 1] !== z) return runs;
  return [[...lastRun, ...first.slice(1)], ...runs.slice(1, -1)];
}

// ---------------------------------------------------------------- hold-to-snap: which shape is this stroke?
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
function bbox(pts) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of pts) { if (x < b[0]) b[0] = x; if (y < b[1]) b[1] = y; if (x > b[2]) b[2] = x; if (y > b[3]) b[3] = y; }
  return b;
}
// Ramer-Douglas-Peucker: the few points that keep the stroke's shape within eps (rdpMask: which ones, 1 = kept)
function rdpMask(pts, eps) {
  const keep = new Uint8Array(pts.length).fill(pts.length < 3 ? 1 : 0); keep[0] = keep[pts.length - 1] = 1;
  if (pts.length < 3) return keep;
  const todo = [[0, pts.length - 1]], e2 = eps * eps;
  while (todo.length) {
    const [i, j] = todo.pop();
    let best = -1, bd = e2;
    for (let k = i + 1; k < j; k++) { const d2 = segDist2(pts[k][0], pts[k][1], pts[i], pts[j]); if (d2 > bd) { bd = d2; best = k; } }
    if (best > 0) { keep[best] = 1; todo.push([i, best], [best, j]); }
  }
  return keep;
}
function rdp(pts, eps) {
  if (pts.length < 3) return pts.slice();
  const keep = rdpMask(pts, eps);
  return pts.filter((_, k) => keep[k]);
}
// how far the path turns at b (a to b, then b to c), degrees 0 to 180
function turnAt(a, b, c) {
  const ax = b[0] - a[0], ay = b[1] - a[1], bx = c[0] - b[0], by = c[1] - b[1];
  return Math.abs(Math.atan2(ax * by - ay * bx, ax * bx + ay * by)) * 180 / Math.PI;
}
// every point within frac x the chord's length of the chord a-b, and never less than 1.5 page px (pw-v7i: on a 15 px
// line 6% is under 1 px, tighter than any hand; from 25 px on, 6% is the larger, so long strokes and arrow shafts,
// which are at least SNAP_MIN, test exactly as before)
function straight(pts, a, b, frac) {
  const L = dist(a, b), lim = Math.max(frac * L, 1.5) ** 2;
  return L > 0 && pts.every((q) => segDist2(q[0], q[1], a, b) <= lim);
}
// a closed polygon's corners: near points merged, nearly straight corners dropped
function corners(poly, size) {
  let v = poly.slice();
  if (v.length > 1 && dist(v[0], v[v.length - 1]) < 1e-6) v.pop();
  const near = 0.12 * size;
  for (let changed = true; changed && v.length > 2;) {
    changed = false;
    for (let i = 0; i < v.length; i++) {
      const j = (i + 1) % v.length;
      if (dist(v[i], v[j]) < near) { v[i] = [(v[i][0] + v[j][0]) / 2, (v[i][1] + v[j][1]) / 2]; v.splice(j, 1); changed = true; break; }
    }
  }
  const turn = (a, b, c) => {
    const a1 = Math.atan2(b[1] - a[1], b[0] - a[0]), a2 = Math.atan2(c[1] - b[1], c[0] - b[0]);
    let t = Math.abs(a2 - a1) % (2 * Math.PI); if (t > Math.PI) t = 2 * Math.PI - t;
    return t * 180 / Math.PI;
  };
  while (v.length > 2) {
    let lo = -1, lt = 30;
    for (let i = 0; i < v.length; i++) { const t = turn(v[(i - 1 + v.length) % v.length], v[i], v[(i + 1) % v.length]); if (t < lt) { lt = t; lo = i; } }
    if (lo < 0) break;
    v.splice(lo, 1);
  }
  return v;
}
// how far the stroke strays from the polygon's sides, at most
function strays(pts, v) {
  let worst = 0;
  for (const q of pts) {
    let m = Infinity;
    for (let i = 0; i < v.length; i++) m = Math.min(m, segDist2(q[0], q[1], v[i], v[(i + 1) % v.length]));
    worst = Math.max(worst, m);
  }
  return Math.sqrt(worst);
}
const rp = (q) => [r1(q[0]), r1(q[1])];
// the Kasa circle fit (least squares on x^2 + y^2 + a x + b y + c = 0, the points centred on their mean first so the
// sums stay small): { ox, oy, r, res (the largest distance of a point from the circle) }; null when there is no circle
function kasa(raw) {
  const n = raw.length;
  let mx = 0, my = 0;
  for (const q of raw) { mx += q[0]; my += q[1]; }
  mx /= n; my /= n;
  let sxx = 0, sxy = 0, syy = 0, sx = 0, sy = 0, sxz = 0, syz = 0, sz = 0;
  for (const q of raw) {
    const x = q[0] - mx, y = q[1] - my, z = x * x + y * y;
    sxx += x * x; sxy += x * y; syy += y * y; sx += x; sy += y; sxz += x * z; syz += y * z; sz += z;
  }
  // the normal equations [sxx sxy sx; sxy syy sy; sx sy n] [a b c] = -[sxz syz sz], by Cramer's rule
  const M = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]], R = [-sxz, -syz, -sz];
  const det3 = (m) => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
    + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const D = det3(M);
  if (!(Math.abs(D) > 1e-12 * n * sxx * syy)) return null;        // all in a line: no circle
  const col = (i) => M.map((row, k) => row.map((v, j) => (j === i ? R[k] : v)));
  const a = det3(col(0)) / D, b = det3(col(1)) / D, c = det3(col(2)) / D;
  const ox = mx - a / 2, oy = my - b / 2, r2 = (a * a + b * b) / 4 - c;
  if (!(r2 > 0)) return null;
  const r = Math.sqrt(r2);
  let res = 0;
  for (const q of raw) res = Math.max(res, Math.abs(Math.hypot(q[0] - ox, q[1] - oy) - r));
  return { ox, oy, r, res };
}
// arc: an open stroke that sits on one circle (the Kasa fit above, k): every point within 6% of the size from the
// circle, the radius at most 3 x the size, the end further than 10% of the size from the start, and 25 to 330 degrees
// swept the way the stroke travels (the raw point half way along its length, against the chord, gives that way).
// arcFit (pw-v4x): the arc branch's whole fit on any run of points (the whole stroke, or a curved arrow's shaft), the
// size being that run's own box diagonal; the arc's data with the ends and the middle moved onto the circle, or null.
// k: the run's Kasa fit when the caller has it already
export function arcFit(raw, k) {
  if (!raw || raw.length < 3) return null;
  const bb = bbox(raw), size = Math.hypot(bb[2] - bb[0], bb[3] - bb[1]), A = raw[0], Z = raw[raw.length - 1];
  if (!(size > 0) || dist(A, Z) <= Math.max(0.1 * size, CLOSE_PX)) return null;   // closed: the closed test's (pw-v8h: its CLOSE_PX floor too)
  if (k === undefined) k = kasa(raw);
  if (!k) return null;
  const n = raw.length, { ox, oy, r } = k;
  if (r > 3 * size) return null;                                   // flatter: a line or freehand
  if (k.res > 0.06 * size) return null;                            // every point within 6% of the size from the circle
  const half = polyLen(raw) / 2;
  let walked = 0, mid = raw[n - 1];
  for (let i = 1; i < n; i++) { walked += dist(raw[i - 1], raw[i]); if (walked >= half) { mid = raw[i]; break; } }
  const cross = (mid[0] - A[0]) * (Z[1] - A[1]) - (mid[1] - A[1]) * (Z[0] - A[0]);
  if (!cross) return null;
  const t1 = Math.atan2(A[1] - oy, A[0] - ox), t2 = Math.atan2(Z[1] - oy, Z[0] - ox);
  const sweep = cross > 0 ? nrmA(t2 - t1) : -nrmA(t1 - t2), deg = (Math.abs(sweep) * 180) / Math.PI;
  if (deg < 25 || deg > 330) return null;
  const on = (t) => [r1(ox + r * Math.cos(t)), r1(oy + r * Math.sin(t))];  // the ends and middle ON the fitted circle
  const [x1, y1] = on(t1), [xm, ym] = on(t1 + sweep / 2), [x2, y2] = on(t2);
  return { type: 'arc', x1, y1, xm, ym, x2, y2 };
}
// parabola (pw-v4s): an open stroke on one quadratic Bezier from its first raw point to its last. It works on the stroke
// as drawn: its raw points and the line between them, every 3 px (so a sparse 5 point tick cannot slip a curve between
// its points). The control point C by closed-form least squares (B0 = (1-t)^2, B1 = 2t(1-t), B2 = t^2: C = sum(B1 (p - B0 P0 - B2 P2)) / sum(B1^2)),
// first on chord-length t, then refined: each point's t moves to its nearest point on the curve and C is solved
// again (up to 12 rounds; chord-length t alone runs too fast along the steep arms and leaves the fit 2 to 15 x worse
// than the curve really is); every point within 5% of the size from the curve (the curve as 96 points,
// distance to its polyline); one turn only (rdp's points change their turning direction at most once, turns
// under 5 degrees not counted); and it must beat the arc: its residual under 0.6 x the circle fit's (k.res), so an
// even curve stays an arc. { shape, p, a } (p, a: the two residuals, px) or null
function parabolaOf(stroke, A, Z, size, k) {
  if (dist(A, Z) <= Math.max(0.1 * size, CLOSE_PX)) return null;   // closed: the closed test's (pw-v8h: its CLOSE_PX floor too)
  const raw = densify(stroke, INK_STEP), n = raw.length, cum = [0];
  for (let i = 1; i < n; i++) cum.push(cum[i - 1] + dist(raw[i - 1], raw[i]));
  const L = cum[n - 1];
  if (!(L > 0)) return null;
  const ts = cum.map((c) => c / L), d = { x1: A[0], y1: A[1], cx: 0, cy: 0, x2: Z[0], y2: Z[1] };
  const solve = () => {                                            // C for the current ts; false when it has none
    let sx = 0, sy = 0, den = 0;
    for (let i = 0; i < n; i++) {
      const t = ts[i], u = 1 - t, b0 = u * u, b1 = 2 * t * u, b2 = t * t;
      sx += b1 * (raw[i][0] - b0 * A[0] - b2 * Z[0]); sy += b1 * (raw[i][1] - b0 * A[1] - b2 * Z[1]); den += b1 * b1;
    }
    if (!(den > 0)) return false;
    d.cx = sx / den; d.cy = sy / den;
    return true;
  };
  if (!solve()) return null;
  let curve = [];
  const sample = () => { curve = []; for (let j = 0; j < 96; j++) curve.push(qbez(d, j / 95)); };
  for (let round = 0; round < 12; round++) {                       // each t to its nearest point on the curve, C again
    sample();
    const ddx = 2 * (d.x2 - 2 * d.cx + d.x1), ddy = 2 * (d.y2 - 2 * d.cy + d.y1);   // B'' (the same at every t)
    for (let i = 1; i < n - 1; i++) {
      const q = raw[i];
      let bj = 0, bd = Infinity;
      for (let j = 0; j < 96; j++) { const e = (curve[j][0] - q[0]) ** 2 + (curve[j][1] - q[1]) ** 2; if (e < bd) { bd = e; bj = j; } }
      let t = bj / 95;
      for (let it = 0; it < 3; it++) {                             // Newton on (B(t) - q) . B'(t) = 0
        const b = qbez(d, t), dx = 2 * (1 - t) * (d.cx - d.x1) + 2 * t * (d.x2 - d.cx), dy = 2 * (1 - t) * (d.cy - d.y1) + 2 * t * (d.y2 - d.cy);
        const f = (b[0] - q[0]) * dx + (b[1] - q[1]) * dy, fp = dx * dx + dy * dy + (b[0] - q[0]) * ddx + (b[1] - q[1]) * ddy;
        if (!(fp > 0)) break;
        t = Math.min(1, Math.max(0, t - f / fp));
      }
      ts[i] = t;
    }
    const ox = d.cx, oy = d.cy;
    if (!solve()) return null;
    if (Math.hypot(d.cx - ox, d.cy - oy) < 0.01) break;
  }
  sample();
  let worst = 0;
  for (const q of raw) {
    let m = Infinity;
    for (let j = 1; j < curve.length; j++) m = Math.min(m, segDist2(q[0], q[1], curve[j - 1], curve[j]));
    worst = Math.max(worst, m);
  }
  const p = Math.sqrt(worst);
  if (p > 0.05 * size) return null;
  const v = rdp(raw, Math.max(0.75, 0.02 * size));                 // one turn: the sign of the turns flips at most once
  let sign = 0, flips = 0;
  for (let i = 1; i < v.length - 1; i++) {
    const ax = v[i][0] - v[i - 1][0], ay = v[i][1] - v[i - 1][1], bx = v[i + 1][0] - v[i][0], by = v[i + 1][1] - v[i][1];
    const cr = ax * by - ay * bx;
    if (Math.abs(Math.atan2(cr, ax * bx + ay * by)) < 5 * Math.PI / 180) continue;
    const sg = Math.sign(cr);
    if (sign && sg !== sign) flips++;
    sign = sg;
  }
  if (flips > 1) return null;
  const a = k ? k.res : Infinity;
  if (!(p < 0.6 * a)) return null;                                 // the arc fits about as well: the arc branch has it
  return { shape: { type: 'parabola', x1: r1(A[0]), y1: r1(A[1]), cx: r1(d.cx), cy: r1(d.cy), x2: r1(Z[0]), y2: r1(Z[1]) }, p, a };
}
// the arrow's tip (pw-v4w): the index of the FIRST raw point where the pen's direction reverses sharply, or -1.
// The direction before a point runs from the point at least TIP_REACH px back (walking back along the stroke until the
// straight distance is that far) to it, the direction after from it to the point at least TIP_REACH px ahead: travel
// distance, not a point count, since pen points sit 0.3 to 1.2 px apart and mouse points much further. A corner turns
// more than TIP_TURN degrees. The first SNAP_MIN px of travel (a start wobble) and the last 3 points are never a corner.
// A corner spans a few samples: qualifying points within TIP_GAP px of travel of each other are one cluster, and the
// first cluster's point with the largest turn is the tip. Exported for the curved arrow (round 3).
const TIP_REACH = 3, TIP_TURN = 110, TIP_GAP = 6;
export function tipIndex(raw) {
  const n = raw ? raw.length : 0;
  if (n < 5) return -1;
  const cum = [0];
  for (let i = 1; i < n; i++) cum.push(cum[i - 1] + dist(raw[i - 1], raw[i]));
  let best = -1, bt = 0, lastC = -1;
  for (let i = 1; i < n - 3; i++) {
    if (cum[i] < SNAP_MIN) continue;
    if (lastC >= 0 && cum[i] - lastC > TIP_GAP) break;            // the first cluster is over
    let j = i - 1, k = i + 1;
    while (j > 0 && dist(raw[j], raw[i]) < TIP_REACH) j--;
    while (k < n - 1 && dist(raw[k], raw[i]) < TIP_REACH) k++;
    if (dist(raw[j], raw[i]) < TIP_REACH || dist(raw[k], raw[i]) < TIP_REACH) continue;
    const ax = raw[i][0] - raw[j][0], ay = raw[i][1] - raw[j][1], bx = raw[k][0] - raw[i][0], by = raw[k][1] - raw[i][1];
    const t = Math.abs(Math.atan2(ax * by - ay * bx, ax * bx + ay * by)) * 180 / Math.PI;
    if (t > TIP_TURN) {
      if (t > bt) { bt = t; best = i; }
      lastC = cum[i];
    }
  }
  return best;
}
// the arrow's head rules (round 2, shared with the curved arrow): the tail (the stroke from the tip on) measured from the tip
// against the unit direction u the shaft arrives in; L = the shaft's chord. Its path 0.08 to 1.2 x L, it comes back on BOTH
// sides of u by need = max(3, 4% of L) at least, and back along u by need to 0.6 x L
function headOk(tail, tip, u, L) {
  const tl = polyLen(tail);
  if (tl < 0.08 * L || tl > 1.2 * L) return false;
  let left = 0, right = 0, backMax = 0;
  for (const q of tail) {
    const qx = q[0] - tip[0], qy = q[1] - tip[1], lat = u[0] * qy - u[1] * qx, along = u[0] * qx + u[1] * qy;
    left = Math.max(left, lat); right = Math.max(right, -lat); backMax = Math.max(backMax, -along);
  }
  const need = Math.max(3, 0.04 * L);
  return left >= need && right >= need && backMax >= need && backMax <= 0.6 * L;
}
// pw-v8g: regular shapes (the tolerances, measured on her 2 Nov triangles and squares, see the header)
const EQ_SIDE = 0.25;            // equilateral: every side within 25% of the mean side ...
const EQ_ANG = 15;               // ... and every angle within 15 degrees of 60 (so a 3-4-5 never passes)
const EQ_UP = 15;                // an equilateral within 15 degrees of upright (a side level) is made upright
const RT_ANG = 12;               // right triangle: exactly one angle within 12 degrees of 90
const AX_ANG = 15;               // legs or sides within 15 degrees of the axes are made axis-true
const RECT_ANG = 15;             // four corners: every angle within 15 degrees of 90 is a true rectangle ...
const SQ_RATIO = 0.2;            // ... and width and height within 20% of each other is a perfect square
const HOOK = 0.12;               // the hook: a turn-back within 12% of the size (and never less than HOOK_PX) of the closing point is trimmed
const HOOK_PX = 4;               // page px: her triangles are small (10 to 16 px a side), where a 3 px landing tick is over 12%
const STUB = 0.4;                // pw-v8h: a side under 40% of every other side is a blunt corner, not a side (destub)
const CLOSE_PX = 4;              // pw-v8h: a ring closes within 10% of the size, and never less than this (page px)
const RAD = Math.PI / 180;
// the inside angle at b of the corner a, b, c (degrees, 0 to 180)
function angAt(a, b, c) {
  const ux = a[0] - b[0], uy = a[1] - b[1], vx = c[0] - b[0], vy = c[1] - b[1];
  return Math.abs(Math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)) / RAD;
}
// how far a direction (radians) lies from the nearest axis, degrees 0 to 45
function offAxis(t) { const a = ((t / RAD) % 90 + 90) % 90; return Math.min(a, 90 - a); }
const toAxis = (t) => Math.round(t / (Math.PI / 2)) * (Math.PI / 2);
// a triangle's 3 corners as drawn -> the shape to keep: a perfect equilateral, a true right triangle, or the corners as drawn
function fitTriangle(v) {
  const s = [0, 1, 2].map((i) => dist(v[i], v[(i + 1) % 3])), m = (s[0] + s[1] + s[2]) / 3;
  const an = [0, 1, 2].map((i) => angAt(v[(i + 2) % 3], v[i], v[(i + 1) % 3]));
  const rt = [0, 1, 2].filter((i) => Math.abs(an[i] - 90) <= RT_ANG);
  if (rt.length === 1) {
    // right angle at P: P stays, both legs keep their lengths, the legs turn evenly about their bisector to exactly 90
    const k = rt[0], P = v[k], Q = v[(k + 1) % 3], R = v[(k + 2) % 3];
    const a = dist(P, Q), b = dist(P, R), tq = Math.atan2(Q[1] - P[1], Q[0] - P[0]), tr = Math.atan2(R[1] - P[1], R[0] - P[0]);
    const bis = Math.atan2(Math.sin(tq) + Math.sin(tr), Math.cos(tq) + Math.cos(tr));
    const sg = (Q[0] - P[0]) * (R[1] - P[1]) - (Q[1] - P[1]) * (R[0] - P[0]) > 0 ? 1 : -1;
    let nq = bis - sg * Math.PI / 4, nr = bis + sg * Math.PI / 4;
    if (offAxis(nq) <= AX_ANG) { const d = toAxis(nq) - nq; nq += d; nr += d; }     // both legs near the axes: axis-true
    const out = [];
    out[k] = P; out[(k + 1) % 3] = [P[0] + a * Math.cos(nq), P[1] + a * Math.sin(nq)]; out[(k + 2) % 3] = [P[0] + b * Math.cos(nr), P[1] + b * Math.sin(nr)];
    return out;
  }
  if (s.every((x) => Math.abs(x / m - 1) <= EQ_SIDE) && an.every((x) => Math.abs(x - 60) <= EQ_ANG)) {
    // equilateral: centre = the corners' mean, side = the mean side, turned to the mean corner direction (modulo 120)
    const cx = (v[0][0] + v[1][0] + v[2][0]) / 3, cy = (v[0][1] + v[1][1] + v[2][1]) / 3, th = v.map((q) => Math.atan2(q[1] - cy, q[0] - cx));
    let phi = Math.atan2(th.reduce((t, x) => t + Math.sin(3 * x), 0), th.reduce((t, x) => t + Math.cos(3 * x), 0)) / 3;
    const up = Math.round((phi / RAD - 30) / 60) * 60 + 30;                          // upright: a corner straight up or down
    if (Math.abs(phi / RAD - up) <= EQ_UP) phi = up * RAD;
    const R = m / Math.sqrt(3), step = 2 * Math.PI / 3;
    const sg = (v[1][0] - v[0][0]) * (v[2][1] - v[0][1]) - (v[1][1] - v[0][1]) * (v[2][0] - v[0][0]) > 0 ? 1 : -1;
    const k0 = Math.round((th[0] - phi) / step);                                     // the drawn order and winding kept
    return [0, 1, 2].map((i) => { const t = phi + (k0 + sg * i) * step; return [cx + R * Math.cos(t), cy + R * Math.sin(t)]; });
  }
  return v;                                                        // a tall isosceles, a scalene: as drawn
}
// 4 corners as drawn -> the rect's 4 points: a true rectangle or square (at its own turn, axis-true near the axes),
// today's straightened box (sides near the axes), or the corners as drawn (a parallelogram, a trapezium)
function fitQuad(v) {
  const box = () => {                                              // the upright box through the corners (today's rule)
    const xs = v.map((q) => q[0]).sort((m, n) => m - n), ys = v.map((q) => q[1]).sort((m, n) => m - n);
    return [(xs[0] + xs[1]) / 2, (ys[0] + ys[1]) / 2, (xs[2] + xs[3]) / 2, (ys[2] + ys[3]) / 2];
  };
  const an = [0, 1, 2, 3].map((i) => angAt(v[(i + 3) % 4], v[i], v[(i + 1) % 4]));
  if (an.every((x) => Math.abs(x - 90) <= RECT_ANG)) {
    const e = [0, 1, 2, 3].map((i) => [v[(i + 1) % 4][0] - v[i][0], v[(i + 1) % 4][1] - v[i][1]]), L = e.map((q) => Math.hypot(q[0], q[1]));
    // the turn: every side's direction modulo 180 (doubled angles), sides 1 and 3 turned back by 90, the long sides weigh more
    let sx = 0, sy = 0;
    e.forEach((q, i) => { const t = 2 * Math.atan2(q[1], q[0]) + (i % 2 ? Math.PI : 0); sx += L[i] * Math.cos(t); sy += L[i] * Math.sin(t); });
    const th = Math.atan2(sy, sx) / 2;
    if (offAxis(th) <= AX_ANG) {                                   // near the axes: today's upright box, squared when near square
      let [l, t, r, b] = box();
      const w = r - l, h = b - t;
      if (Math.abs(w - h) <= SQ_RATIO * Math.max(w, h)) { const cx = (l + r) / 2, cy = (t + b) / 2, s2 = (w + h) / 4; l = cx - s2; r = cx + s2; t = cy - s2; b = cy + s2; }
      return [[l, t], [r, t], [r, b], [l, b]];
    }
    let w = (L[0] + L[2]) / 2, h = (L[1] + L[3]) / 2;
    if (Math.abs(w - h) <= SQ_RATIO * Math.max(w, h)) w = h = (w + h) / 2;
    const cx = (v[0][0] + v[1][0] + v[2][0] + v[3][0]) / 4, cy = (v[0][1] + v[1][1] + v[2][1] + v[3][1]) / 4;
    const u = [Math.cos(th), Math.sin(th)], n = [-u[1], u[0]];
    return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([p, q]) => [cx + p * w / 2 * u[0] + q * h / 2 * n[0], cy + p * w / 2 * u[1] + q * h / 2 * n[1]]);
  }
  const axis = v.every((q, i) => {                                 // today's rule: every side within 15 degrees of the axes
    const n = v[(i + 1) % 4];
    return offAxis(Math.atan2(n[1] - q[1], n[0] - q[0])) <= 15;
  });
  if (axis) { const [l, t, r, b] = box(); return [[l, t], [r, t], [r, b], [l, b]]; }
  return v;                                                        // a parallelogram or trapezium drawn on purpose: as drawn
}
// the hook: the pen landing with a tick (out and back) at the start of the ring, or a flick just before it closes.
// A tick is a vertex T of the simplified ring within HOOK x size (HOOK_PX at least) of the closing point A where the path
// turns back by more than 135 degrees and then passes A again closer than 0.4 x |AT| (a real corner near the start never
// comes back that close: a 30 degree apex comes back to 0.5). The start loses everything up to where the path comes back
// nearest A, the end everything after the point nearest A before the flick. Anything else: the ring as it is.
function unhook(ring, size) {
  const A = ring[0], r = Math.max(HOOK * size, HOOK_PX), keep = rdpMask(ring, Math.max(0.75, 0.02 * size)), ix = [];
  for (let k = 0; k < ring.length; k++) if (keep[k]) ix.push(k);
  if (ix.length < 5) return ring;
  let from = 0, to = ring.length - 1;
  // the point nearest A walking from T (step +1 or -1) while within r of A: [index, distance]
  const back = (t, step, stop) => {
    let best = t, bd = Infinity;
    for (let k = t + step; k !== stop && dist(ring[k], A) < r; k += step) { const d = dist(ring[k], A); if (d < bd) { bd = d; best = k; } }
    return [best, bd];
  };
  const t1 = ix[1], d1 = dist(ring[t1], A);
  if (d1 < r && turnAt(ring[0], ring[t1], ring[ix[2]]) > 135) {
    const [k, d] = back(t1, 1, ring.length);
    if (d < 0.4 * d1) from = k;
  }
  const t2 = ix[ix.length - 2], d2 = dist(ring[t2], A);
  if (t2 > from + 1 && d2 < r && turnAt(ring[ix[ix.length - 3]], ring[t2], ring[to]) > 135) {
    const [k, d] = back(t2, -1, from);
    if (d < 0.4 * d2) to = k;
  }
  return from === 0 && to === ring.length - 1 ? ring : ring.slice(from, to + 1);
}
// where the lines through a-b and c-d meet, or null when they are within 10 degrees of parallel
function meet(a, b, c, d) {
  const ux = b[0] - a[0], uy = b[1] - a[1], vx = d[0] - c[0], vy = d[1] - c[1], den = ux * vy - uy * vx;
  if (Math.abs(den) <= Math.sin(10 * RAD) * Math.hypot(ux, uy) * Math.hypot(vx, vy)) return null;
  const t = ((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / den;
  return [a[0] + t * ux, a[1] + t * uy];
}
// pw-v8h: a blunt corner. A stub is a side under STUB x the mean of the polygon's long sides (the sides at least STUB x
// the longest, so two stubs on one ring, a rounded corner and the closing gap, never shield each other) whose two outer
// sides meet within 2 x the stub of its middle: the pen rounded a corner (on her 3 Nov triangle a 3.7 px side next to 10 to
// 13 px ones). Its two ends become that ONE corner. Again while the polygon has more than 3 corners and a stub. A thin
// bar (10 x 40) keeps its 4 corners: its long sides are parallel, they meet nowhere near. A trapezium keeps its top down
// to about 40% of its other sides.
function destub(v) {
  for (;;) {
    const n = v.length;
    if (n <= 3) return v;
    const L = v.map((q, i) => dist(q, v[(i + 1) % n])), top = Math.max(...L), long = L.filter((x) => x >= STUB * top);
    const m = long.reduce((t, x) => t + x, 0) / long.length;
    let k = -1;
    for (let i = 0; i < n; i++) {
      if (L[i] >= STUB * m || (k >= 0 && L[i] >= L[k])) continue;
      const P = v[(i - 1 + n) % n], Q = v[i], R = v[(i + 1) % n], S = v[(i + 2) % n];
      const X = meet(P, Q, S, R);
      if (X && dist(X, [(Q[0] + R[0]) / 2, (Q[1] + R[1]) / 2]) <= 2 * L[i]) k = i;
    }
    if (k < 0) return v;
    const P = v[(k - 1 + n) % n], Q = v[k], R = v[(k + 1) % n], S = v[(k + 2) % n], C = meet(P, Q, S, R), out = [];
    for (let i = 0; i < n; i++) { if (i === k) out.push(C); else if (i !== (k + 1) % n) out.push(v[i]); }
    v = out;
  }
}
// in this order: arrow, curved arrow, line, parabola, arc, then closed: triangle, rect, circle or ellipse; null = stays freehand.
// A parabola leaves its two fit numbers in FIT (lastStroke().fit); every other answer leaves FIT null
export function classify(raw) {
  FIT = null;
  const len = raw && raw.length >= 3 ? polyLen(raw) : 0;
  if (len < SNAP_LEN) return null;                                // pw-v7i: from 12 page px on (it was 30)
  const b = bbox(raw), W = b[2] - b[0], H = b[3] - b[1], size = Math.hypot(W, H);
  if (size < 8) return null;                                       // pw-v7i: 8 (it was 10)
  const pts = rdp(raw, Math.max(0.75, 0.02 * size)), A = raw[0], Z = raw[raw.length - 1];
  // pw-v7i: a short stroke (under SNAP_MIN) only ever becomes a line, so a small letter held still at its end stays ink
  if (len < SNAP_MIN) return straight(raw, A, Z, 0.06) ? { type: 'line', x1: r1(A[0]), y1: r1(A[1]), x2: r1(Z[0]), y2: r1(Z[1]) } : null;
  // arrow: a straight shaft to the tip (the stroke's first sharp corner, tipIndex above), then a short tail that comes
  // back on both sides of the shaft (the V of the head)
  const ti = tipIndex(raw), shaft = ti < 0 ? 0 : dist(A, raw[ti]);
  if (ti >= 0 && shaft >= SNAP_MIN) {
    const tip = raw[ti], tail = raw.slice(ti);
    if (straight(raw.slice(0, ti + 1), A, tip, 0.06) && headOk(tail, tip, [(tip[0] - A[0]) / shaft, (tip[1] - A[1]) / shaft], shaft)) {
      return { type: 'arrow', x1: r1(A[0]), y1: r1(A[1]), x2: r1(tip[0]), y2: r1(tip[1]) };
    }
    // curved arrow (pw-v4x): the shaft up to the tip fits an arc (arcFit, the arc's own rules) and the tail passes the same
    // head rules, measured from the arc's end against its end tangent (the fitted arc's own, not the last raw points,
    // which bend into the head); the arc's end is the tip
    const a = arcFit(raw.slice(0, ti + 1)), g = a && arcGeom(a);
    if (g && headOk(tail, [a.x2, a.y2], g.te, shaft)) return { ...a, type: 'carrow' };
  }
  // line: every point close to the chord
  if (straight(raw, A, Z, 0.06)) return { type: 'line', x1: r1(A[0]), y1: r1(A[1]), x2: r1(Z[0]), y2: r1(Z[1]) };
  // parabola: open, one turn, and a better fit than the arc's (parabolaOf above)
  const k = kasa(raw), par = parabolaOf(raw, A, Z, size, k);
  if (par) { FIT = { p: r1(par.p), a: Number.isFinite(par.a) ? r1(par.a) : null }; return par.shape; }
  // arc: open, and on one circle (arcFit above)
  const arc = arcFit(raw, k);
  if (arc) return arc;
  // closed: the end (or, for an overshoot, the point nearest the start in the last 30%) within 10% of the size
  let ci = raw.length - 1, cd = Infinity;
  for (let i = Math.floor(raw.length * 0.7); i < raw.length; i++) { const dd = dist(A, raw[i]); if (dd < cd) { cd = dd; ci = i; } }
  if (cd > Math.max(0.1 * size, CLOSE_PX)) return null;             // pw-v8h: never less than CLOSE_PX (her 19 px triangle ended 3 px short)
  const ring = raw.slice(0, ci + 1), poly = unhook(ring, size);     // pw-v8g: a landing tick or a closing flick trimmed first
  const v0 = corners(rdp(poly, Math.max(0.75, 0.02 * size)).concat([poly[0]]), size);
  if (v0.length >= 3 && v0.length <= 6 && strays(poly, v0) <= 0.07 * size) {   // the ink follows a polygon (its corners as found) ...
    const v = destub(v0);                                                          // ... pw-v8h: a blunt corner's stub side collapsed
    if (v.length === 3) return { type: 'triangle', points: fitTriangle(v).map(rp) };
    if (v.length === 4) return { type: 'rect', points: fitQuad(v).map(rp) };
  }
  // circle or ellipse: an upright ellipse through the box; every point's distance from the centre (measured
  // on that ellipse, so a round one is a circle) within 15% of the mean
  const rb = bbox(ring), cx = (rb[0] + rb[2]) / 2, cy = (rb[1] + rb[3]) / 2, rx = (rb[2] - rb[0]) / 2, ry = (rb[3] - rb[1]) / 2;
  if (rx < 3 || ry < 3) return null;
  const nd = ring.map((q) => Math.hypot((q[0] - cx) / rx, (q[1] - cy) / ry)), m = nd.reduce((s, x) => s + x, 0) / nd.length;
  if (!nd.every((x) => Math.abs(x - m) <= 0.15 * m)) return null;
  const RX = rx * m, RY = ry * m;
  if (Math.abs(RX - RY) / Math.max(RX, RY) > 0.2) return { type: 'ellipse', cx: r1(cx), cy: r1(cy), rx: r1(RX), ry: r1(RY) };
  return { type: 'circle', cx: r1(cx), cy: r1(cy), r: r1((RX + RY) / 2) };
}

// ---------------------------------------------------------------- shape handles (grab with the select tool)
export function handles(rec) {
  const d = rec.data || {};
  if (rec.kind === 'axes' || rec.kind === 'image') return [];     // U5e, U4c: an axes stamp and a picture have no reshape handles                              // U5e: an axes stamp has no reshape handles
  if (d.fixed) return [];                                          // U5a: a ruler line (fixed) moves whole, its ends are never reshaped
  if (d.type === 'line' || d.type === 'arrow') return [[d.x1, d.y1], [d.x2, d.y2]];
  if (d.type === 'rect' || d.type === 'triangle') return d.points.map((q) => [q[0], q[1]]);
  if (d.type === 'circle' || d.type === 'ellipse') {
    const rx = d.type === 'circle' ? d.r : d.rx, ry = d.type === 'circle' ? d.r : d.ry, c = [d.cx, d.cy];
    const tu = d.type === 'ellipse' ? d.angle || 0 : 0;                                     // a turned ellipse: turned too
    return [[d.cx, d.cy - ry], [d.cx + rx, d.cy], [d.cx, d.cy + ry], [d.cx - rx, d.cy]].map((q) => turn(q, c, tu));   // N, E, S, W
  }
  if (d.type === 'arc' || d.type === 'carrow') return [[d.x1, d.y1], [d.xm, d.ym], [d.x2, d.y2]];   // start, middle, end (a curved arrow's end: its tip)
  if (d.type === 'parabola') return [[d.x1, d.y1], qbez(d, 0.5), [d.x2, d.y2]];           // start, the curve's middle M, end
  return [];
}
// the handle nearest (x, y) on page `id`, within reach: { rec, h, at }
function handleAt(id, x, y, reach) {
  let best = null, bd = reach;
  for (const r of data(id).strokes) {
    if (r.kind !== 'shape') continue;
    handles(r).forEach((q, h) => { const dd = Math.hypot(q[0] - x, q[1] - y); if (dd <= bd) { bd = dd; best = { rec: r, h, at: q }; } });
  }
  return best;
}
// the shape with handle h dragged to (x, y)
function dragHandle(rec, h, x, y) {
  const d = { ...rec.data };
  if (d.type === 'line' || d.type === 'arrow') { if (h === 0) { d.x1 = r1(x); d.y1 = r1(y); } else { d.x2 = r1(x); d.y2 = r1(y); } }
  else if (d.type === 'triangle') d.points = d.points.map((q, k) => (k === h ? [r1(x), r1(y)] : q));
  else if (d.type === 'rect') {
    const p = d.points, upright = p.every((q, k) => { const n = p[(k + 1) % 4]; return Math.abs(q[0] - n[0]) < 0.5 || Math.abs(q[1] - n[1]) < 0.5; });
    if (upright) {                                                 // an upright rect stays upright: the opposite corner holds
      const o = p[(h + 2) % 4];
      d.points = p.map((q, k) => (k === h ? [r1(x), r1(y)] : k === (h + 2) % 4 ? q
        : (Math.abs(q[0] - o[0]) < 0.5 ? [q[0], r1(y)] : [r1(x), q[1]])));
    } else d.points = p.map((q, k) => (k === h ? [r1(x), r1(y)] : q));
  } else if (d.type === 'circle') d.r = r1(Math.max(2, Math.hypot(x - d.cx, y - d.cy)));
  else if (d.type === 'ellipse') {                                 // the centre holds; N and S set the height, E and W the width
    const [lx, ly] = turn([x, y], [d.cx, d.cy], -(d.angle || 0));   // a turned ellipse: in its own frame
    if (h % 2) d.rx = r1(Math.max(2, Math.abs(lx - d.cx))); else d.ry = r1(Math.max(2, Math.abs(ly - d.cy)));
  } else if (d.type === 'arc' || d.type === 'carrow') {           // only that point moves: the arc is the circle through the three (a head re-aims itself)
    const k = ['1', 'm', '2'][h];
    d['x' + k] = r1(x); d['y' + k] = r1(y);
  } else if (d.type === 'parabola') {                              // an end moves alone (the control holds); the middle M' sets
    if (h === 1) { d.cx = r1(2 * x - (d.x1 + d.x2) / 2); d.cy = r1(2 * y - (d.y1 + d.y2) / 2); }   // C = 2 M' - (P0 + P2) / 2
    else if (h === 0) { d.x1 = r1(x); d.y1 = r1(y); } else { d.x2 = r1(x); d.y2 = r1(y); }
  }
  return { ...rec, data: d };
}
function showHandle(cx, cy) {
  if (!hring) { hring = document.createElement('div'); hring.id = 'handleRing'; deskEl.appendChild(hring); }
  const r = deskEl.getBoundingClientRect();
  hring.hidden = false;
  hring.style.transform = `translate(${cx - r.left}px, ${cy - r.top}px)`;
}
function hideHandle() { if (hring) hring.hidden = true; }
// the S Pen's side button (the barrel button) or the right mouse button: bit 2 in buttons, button 2 on a press
const barrel = (e) => !!(e.buttons & 2) || e.button === 2;
// pw-v7m: page point `at` is inside the selection box (the closed rectangle: on the dashed line counts as inside)
function inSel(at) {
  if (!SEL || SEL.page !== at.id || !SEL.box) return false;
  const b = SEL.box;
  return at.x >= b[0] && at.x <= b[2] && at.y >= b[1] && at.y <= b[3];
}
// the selection's own grips at page point `at` (page at.id): 'rot' on its turn ring, a corner index 0..3, else null.
// pw-v7m: a corner only from OUTSIDE the box (within GRAB of it); inside the box is always a move
function selGrip(at, z) {
  if (!SEL || SEL.page !== at.id || !SEL.box || SEL.locked) return null;   // U4c: a locked picture has no grips
  const reach = GRAB / z;
  if (SEL.rot && Math.hypot(SEL.rot[0] - at.x, SEL.rot[1] - at.y) <= reach) return 'rot';
  if (inSel(at)) return null;
  const k = selCorners(SEL.box).findIndex((q) => Math.hypot(q[0] - at.x, q[1] - at.y) <= reach);
  return k >= 0 ? k : null;
}
// the pen hovering (or a mouse moving), button or not, with the select tool: a small ring on a handle within reach,
// meaning "a touch here grabs this point"; out of reach, where the selection's ring or a corner would win, or inside the
// selection box (pw-v7m: a touch there moves), no ring. The pen tool shows nothing: it only draws
function hover(e) {
  if (T.tool !== 'select' || G) { hideHandle(); return; }
  const at = surfaceAt(e.clientX, e.clientY), z = view().z;
  const h = at && selGrip(at, z) === null && !inSel(at) && handleAt(at.id, at.x, at.y, HANDLE_REACH / z);
  if (!h) { hideHandle(); return; }
  showHandle(e.clientX + (h.at[0] - at.x) * z, e.clientY + (h.at[1] - at.y) * z);
}

// ---------------------------------------------------------------- moving, scaling and turning records (selection)
// f maps a point; s is the scale (circle and ellipse radii follow it, the ink's width never does); rot is the
// turn in degrees, added to an ellipse's own angle (every other shape turns through its points)
function xform(rec, f, s, rot) {
  const d = rec.data, P = (q) => rp(f(q));
  let nd;
  if (rec.kind === 'image') {                                      // U4c: the box's centre through f, w and h x s (nw, nh stay), rot + the turn
    const c = f([d.x + d.w / 2, d.y + d.h / 2]), w = d.w * s, h = d.h * s;
    nd = { ...d, x: q2(c[0] - w / 2), y: q2(c[1] - h / 2), w: q2(w), h: q2(h) };
    if (rot) nd.rot = nrmDeg(r1((+d.rot || 0) + rot)) || 0;
    return { ...rec, style: { ...rec.style }, data: nd };
  }
  if (rec.kind === 'axes') {                                       // U5e: the origin through f, px and py x s; it never turns (rot: left as it was)
    if (rot) return { ...rec, style: { ...rec.style }, data: { ...d } };
    const o = f([d.x0, d.y0]), q2 = (v) => Math.round(v * 100) / 100;
    nd = { ...d, x0: q2(o[0]), y0: q2(o[1]), px: q2(d.px * s), py: q2(d.py * s) };
  } else if (rec.kind !== 'shape') nd = { ...d, points: d.points.map(P) };
  else if (d.type === 'line' || d.type === 'arrow') { const a = P([d.x1, d.y1]), b = P([d.x2, d.y2]); nd = { ...d, x1: a[0], y1: a[1], x2: b[0], y2: b[1] }; }
  else if (d.type === 'rect' || d.type === 'triangle') nd = { ...d, points: d.points.map(P) };
  else if (d.type === 'arc' || d.type === 'carrow') {              // a curved arrow's head follows its new end tangent
    const a = P([d.x1, d.y1]), m = P([d.xm, d.ym]), z = P([d.x2, d.y2]);
    nd = { ...d, x1: a[0], y1: a[1], xm: m[0], ym: m[1], x2: z[0], y2: z[1] };
  } else if (d.type === 'parabola') {                              // a Bezier maps through its three points
    const a = P([d.x1, d.y1]), c = P([d.cx, d.cy]), z = P([d.x2, d.y2]);
    nd = { ...d, x1: a[0], y1: a[1], cx: c[0], cy: c[1], x2: z[0], y2: z[1] };
  } else if (d.type === 'circle') { const c = P([d.cx, d.cy]); nd = { ...d, cx: c[0], cy: c[1], r: r1(d.r * s) }; }
  else if (d.type === 'ellipse') {
    const c = P([d.cx, d.cy]);
    nd = { ...d, cx: c[0], cy: c[1], rx: r1(d.rx * s), ry: r1(d.ry * s) };
    if (rot) { const a = r1(nrmDeg((d.angle || 0) + rot)); if (a) nd.angle = a; else delete nd.angle; }
  } else nd = { ...d };
  return { ...rec, style: { ...rec.style }, data: nd };
}
// what a selection gesture does to a point: [f, s, rot] for a move, a resize or a turn
function selXf(g) {
  if (g.kind === 'smove') { const { dx, dy } = g; return [(q) => [q[0] + dx, q[1] + dy], 1, 0]; }
  if (g.kind === 'sresize') { const { o, s } = g; return [(q) => [o[0] + (q[0] - o[0]) * s, o[1] + (q[1] - o[1]) * s], s, 0]; }
  const { c, a } = g;
  return [(q) => turn(q, c, a), 1, a];
}

// ---------------------------------------------------------------- the selection: dashed box, corners, Copy, Duplicate and Delete
const selRecs = () => { const d = data(SEL.page); return [...SEL.ids].map((id) => d.byId.get(id)).filter(Boolean); };
function selBox(recs) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const r of recs) {
    const q = boxOf(r), w = (r.style.width || 0) / 2;
    b[0] = Math.min(b[0], q[0] - w); b[1] = Math.min(b[1], q[1] - w); b[2] = Math.max(b[2], q[2] + w); b[3] = Math.max(b[3], q[3] + w);
  }
  return b;
}
const selCorners = (b) => [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
export function clearSelection() {
  if (!SEL) return;
  SEL.g.remove(); SEL.chips.remove(); SEL.deg.remove();
  SEL = null;
}
export function selection() { return SEL ? { page: SEL.page, ids: [...SEL.ids], box: selBox(selRecs()) } : null; }
function setAttrs(el, at) { for (const k in at) el.setAttribute(k, typeof at[k] === 'number' ? f1(at[k]) : at[k]); }
function renderSel(t) {                          // t: a live transform while dragging the selection
  const d = data(SEL.page), z = view().z, b = selBox(selRecs());
  SEL.z = z;
  if (!SEL.g.parentNode) d.svg.appendChild(SEL.g);
  if (!SEL.chips.parentNode) d.svg.parentNode.appendChild(SEL.chips);
  if (!SEL.deg.parentNode) d.svg.parentNode.appendChild(SEL.deg);
  const pad = 4 / z, x0 = b[0] - pad, y0 = b[1] - pad, x1 = b[2] + pad, y1 = b[3] + pad;
  SEL.g.textContent = '';
  const box = document.createElementNS(SVGNS, 'rect');
  setAttrs(box, { class: 'selbox', x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: 'none', stroke: SEL_BLUE,
    'stroke-width': 1.5 / z, 'stroke-dasharray': f1(6 / z) + ' ' + f1(4 / z) });
  SEL.g.appendChild(box);
  fillChips();
  if (SEL.locked) {                              // U4c: a locked picture: the dashed box only, no corners, no turn ring
    SEL.rot = null;
    if (t) SEL.g.setAttribute('transform', t); else SEL.g.removeAttribute('transform');
    SEL.box = [x0, y0, x1, y1];
    placeChips(t ? SEL.live : null);
    return;
  }
  selCorners([x0, y0, x1, y1]).forEach((q, k) => {
    const c = document.createElementNS(SVGNS, 'circle');
    setAttrs(c, { class: 'selh', 'data-corner': String(k), cx: q[0], cy: q[1], r: 6 / z, fill: '#FFFFFF', stroke: SEL_BLUE, 'stroke-width': 1.5 / z });
    SEL.g.appendChild(c);
  });
  // the turn handle: a ring 28 px (on screen) above the top edge's middle, on a thin stem;
  // when that would pass the page's top edge, the ring goes 28 px BELOW the bottom edge instead
  const cx = (x0 + x1) / 2, below = y0 - 28 / z - 6 / z < 0, ry = below ? y1 + 28 / z : y0 - 28 / z;
  const stem = document.createElementNS(SVGNS, 'line');
  setAttrs(stem, below
    ? { class: 'selstem', x1: cx, y1: y1, x2: cx, y2: ry - 6 / z, stroke: SEL_BLUE, 'stroke-width': 1.2 / z }
    : { class: 'selstem', x1: cx, y1: y0, x2: cx, y2: ry + 6 / z, stroke: SEL_BLUE, 'stroke-width': 1.2 / z });
  const knob = document.createElementNS(SVGNS, 'circle');
  setAttrs(knob, { class: 'selrot', cx, cy: ry, r: 6 / z, fill: '#FFFFFF', stroke: SEL_BLUE, 'stroke-width': 1.5 / z });
  SEL.g.append(stem, knob);
  SEL.rot = [cx, ry];
  if (t) SEL.g.setAttribute('transform', t); else SEL.g.removeAttribute('transform');
  SEL.box = [x0, y0, x1, y1];
  placeChips(t ? SEL.live : null);
}
function placeChips(m) {                         // m: [s, ox, oy, dx, dy] while dragging, so the chips ride along
  let [x0, y0] = SEL.box, rx = SEL.rot && SEL.rot[1] < SEL.box[1] ? SEL.rot[0] : Infinity;   // only a ring ABOVE the box crowds the chips (Infinity: nothing to dodge)
  if (m) { const [s, ox, oy, dx, dy] = m; x0 = ox + (x0 - ox) * s + dx; y0 = oy + (y0 - oy) * s + dy; rx = ox + (rx - ox) * s + dx; }
  const c = SEL.chips, z = SEL.z, gap = 14 / z, w = c.offsetWidth / z;
  if (x0 + w > rx - gap) x0 = rx + gap;      // they would cover the turn ring: they start just right of it
  c.style.left = f1(x0) + 'px'; c.style.top = f1(y0) + 'px';
  c.style.transform = `scale(${1 / z}) translateY(calc(-100% - 8px))`;
  // pw-v7l: the four chips are 170 px wide on screen, so on a phone they would run off the desk beside a selection near the
  // page's right edge: they are pulled back inside the desk (8 px in); pulled back over the ring, they sit just left of it
  // (or, with no room there, just right of it)
  if (!deskEl || !c.isConnected) return;
  const d = deskEl.getBoundingClientRect(), r = c.getBoundingClientRect(), M = 8;
  const lo = x0 + (d.left + M - r.left) / z, hi = x0 + (d.right - M - r.right) / z;   // where x0 may go, the chips inside the desk
  let nx = Math.max(Math.min(x0, hi), lo);
  if (nx === x0) return;
  if (nx < rx + gap && nx + w > rx - gap) nx = rx - gap - w >= lo ? rx - gap - w : rx + gap;
  c.style.left = f1(nx) + 'px';
}
function syncSel() {
  const d = data(SEL.page);
  for (const id of [...SEL.ids]) if (!d.byId.has(id)) SEL.ids.delete(id);
  if (!SEL.ids.size || !d.svg) { clearSelection(); return; }
  renderSel();
}
function makeSel(page, ids) {
  clearSelection();
  const g = document.createElementNS(SVGNS, 'g'); g.setAttribute('class', 'sel');
  const chips = document.createElement('div'); chips.className = 'selChips';
  const deg = document.createElement('div'); deg.className = 'selDeg';   // the turn's degrees, shown only while turning
  SEL = { page, ids: new Set(ids), g, chips, deg, z: 0, box: null, rot: null, live: null, locked: false, ckey: null };
  renderSel();
}
// the chips for what is selected now (renderSel calls it; they are made again only when that changes): Copy, Cut, Duplicate,
// Delete, and U4c's padlock after Delete when a picture is selected (Lock; Unlock when any selected picture is locked).
// A selection holding a locked picture has Delete and Unlock only. pw-v9e: exactly ONE picture, unlocked: the wand after
// Lock, Cut out (js/cutout.js); ink, several records or a locked picture: none.
function fillChips() {
  const recs = selRecs(), pic = recs.some(isImg), locked = recs.some(isLocked), one = recs.length === 1 && pic && !locked && !!cutOut;
  const key = (pic ? 'p' : '-') + (locked ? 'l' : '-') + (one ? 'c' : '-');
  SEL.locked = locked;
  if (SEL.ckey === key) return;
  SEL.ckey = key;
  const chips = SEL.chips;
  chips.replaceChildren();
  const chip = (act, label, icon, fn) => {        // an icon only: the word lives in aria-label and title
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'chip'; btn.dataset.act = act; btn.innerHTML = icon;
    btn.setAttribute('aria-label', label); btn.title = label;
    btn.addEventListener('click', (e) => { e.stopPropagation(); fn(); });
    chips.appendChild(btn);
  };
  if (!locked) { chip('copy', 'Copy', SVG_COPY, copySel); chip('cut', 'Cut', SVG_CUT, cutSel); chip('duplicate', 'Duplicate', SVG_PLUS, duplicateSel); }
  chip('delete', 'Delete', SVG_BIN, deleteSel);
  if (pic) chip('lock', locked ? 'Unlock' : 'Lock', locked ? SVG_UNLOCK : SVG_LOCK, lockSel);
  if (one) chip('cutout', 'Cut out', SVG_WAND, cutoutSel);
}
// pw-v9e: the wand chip: the Cut out sheet on the one selected picture (a copy of its record; the selection stays)
function cutoutSel() {
  if (!SEL || !cutOut) return;
  const recs = selRecs();
  if (recs.length !== 1 || !isImg(recs[0]) || isLocked(recs[0])) return;
  cutOut(SEL.page, JSON.parse(JSON.stringify(recs[0])));
}
// pw-v9e, Cut out's Done: the picture `id` on page pageId gets the file at `path` (blob: its bytes, kept on this device
// already; drawn at once). Only data.path changes; ONE undo step, which puts the old record (the old path) back. False
// when the picture is not on the page any more, or is that file already.
export function setImagePath(pageId, id, path, blob) {
  const d = data(pageId), old = d.byId.get(id);
  if (!isImg(old) || !old.data || !path || old.data.path === path) return false;
  if (blob) keepUrl(path, blob);
  const rec = { ...old, style: { ...old.style }, data: { ...old.data, path } };
  doOp(changeOp([{ page: pageId, removed: [old], added: [rec] }]));
  return true;
}
// U4c: the padlock chip: every selected picture locked (none was) or unlocked (any was), one undo step; the selection stays
function lockSel() {
  if (!SEL) return;
  const to = !selRecs().some(isLocked);
  changeSel((r) => (isImg(r) && !!(r.data && r.data.locked) !== to ? { ...r, style: { ...r.style }, data: { ...r.data, locked: to } } : null));
}
// Copy: the selection goes on the clipboard; nothing is added, no undo step. pw-v9f (her ask 11 Nov, the Samsung Notes
// way): the selection clears, so the box going away says it is copied
function copySel() {
  if (!SEL) return;
  const recs = selRecs().sort(bySeq);
  if (!recs.length) return;
  CLIP = { recs: JSON.parse(JSON.stringify(recs)), box: selBox(recs) };
  clearSelection();
  if (toast) toast('Copied.');
}
// Cut (pw-v7l): Copy, then Delete. The selection goes on the clipboard exactly as Copy puts it there, then its strokes
// come off the page as one undo step (undo brings them back, the clipboard keeps them); Paste puts them anywhere after
function cutSel() {
  if (!SEL) return;
  const page = SEL.page, recs = selRecs().sort(bySeq);
  if (!recs.length) return;
  CLIP = { recs: JSON.parse(JSON.stringify(recs)), box: selBox(recs) };
  clearSelection();
  doOp(changeOp([{ page, removed: recs, added: [] }]));
  if (toast) toast('Cut.');
}
export function hasClip() { return !!CLIP; }
// Paste: the clipboard's strokes on page pageId, the box's centre on (x, y) (page px), nudged inside the page where
// it fits (a box bigger than the page is centred on it); fresh ids, seq values above every stroke on the page in the
// copied order; one undo step; the pasted strokes become the selection with the select tool on. The clipboard stays.
export function pasteAt(pageId, x, y) {
  if (!CLIP) return false;
  const d = data(pageId), b = CLIP.box;
  const fit = (lo, hi, at, W) => keepIn(lo, hi, at - (lo + hi) / 2, W, W / 2 - (lo + hi) / 2);   // centre on at, kept on the page
  addCopies(pageId, CLIP.recs, fit(b[0], b[2], x, d.w), fit(b[1], b[3], y, d.h));
  return true;
}
// the shift v along one axis, cut back so [lo, hi] stays on [0, W]; a span wider than W gets big instead (no page size: v)
function keepIn(lo, hi, v, W, big) {
  if (!W) return v;
  if (hi - lo > W) return big;
  return Math.min(W - hi, Math.max(-lo, v));
}
// Paste and Duplicate: copies of recs (by seq) on page pageId moved by (dx, dy), fresh ids, seq values above every stroke
// on the page in the same order, one undo step; the copies become the selection with the select tool on
function addCopies(pageId, recs, dx, dy) {
  const d = data(pageId);
  const top = d.strokes.length ? d.strokes[d.strokes.length - 1].seq : 0, base = Math.max(Date.now(), top + 1);
  const news = recs.map((r, k) => ({ ...xform(r, (q) => [q[0] + dx, q[1] + dy], 1, 0), id: uuid(), page_id: pageId, seq: base + k }));
  doOp(changeOp([{ page: pageId, removed: [], added: news }]));
  if (T.tool !== 'select') { if (selectTool) selectTool(); else setTool('select'); }
  if (d.svg) makeSel(pageId, news.map((r) => r.id));
  return news;
}
// U4c: a new picture on page pageId (js/pdfin.js importImage, the + menu's Image): w = min(nw, 0.8 x the page's width),
// scaled down further when its height would pass 0.8 x the page's height; centred in the part of the page she sees (the
// axes stamp's rule) and kept on the page; rot 0, unlocked; ONE undo step; it lands selected with the select tool on, so
// the next pen touch moves it. blob: the device copy, so it draws at once. Returns the record, or null (no page on screen)
// pw-v9d, a picture shared to PenWorks (how.landing, from js/app.js landShared through importImage): its page is new and
// not on screen, so there is no view to centre on: the same size rule, centred across, its top the same gap from the
// page's top as its sides (less when it would pass the bottom); the page's size is how.size while it has no layer. NOT an
// undo step (a shared PDF's pages are not one either) and not selected here: app.js selects it (selectRecs) once the note
// is open on that page.
export function placeImage(pageId, { path, nw, nh, blob }, how = {}) {
  const land = !!(how && how.landing), d = data(pageId), sheet = document.querySelector(`#stack .sheet[data-id="${CSS.escape(pageId)}"]`);
  const sz = d.svg ? { w: d.w, h: d.h } : land && how.size ? how.size : { w: 0, h: 0 };
  if ((!land && (!d.svg || !sheet)) || !(sz.w > 0 && sz.h > 0) || !path || !(nw > 0) || !(nh > 0)) return null;
  if (blob) keepUrl(path, blob);
  const W = sz.w, H = sz.h, cl = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  let w = Math.min(nw, 0.8 * W), h = w * nh / nw;
  if (h > 0.8 * H) { h = 0.8 * H; w = h * nw / nh; }
  let x, y;
  if (land) { x = (W - w) / 2; y = Math.min(x, H - h); }
  else {
    const idx = +sheet.dataset.index - 1, db = deskEl.getBoundingClientRect();
    const a = pagePoint(idx, db.left, db.top), b = pagePoint(idx, db.right, db.bottom);
    const cx = (cl(a[0], 0, W) + cl(b[0], 0, W)) / 2, cy = (cl(a[1], 0, H) + cl(b[1], 0, H)) / 2;
    x = cl(cx - w / 2, 0, W - w); y = cl(cy - h / 2, 0, H - h);
  }
  const top = d.strokes.length ? d.strokes[d.strokes.length - 1].seq : 0;
  const rec = { id: uuid(), page_id: pageId, seq: Math.max(Date.now(), top + 1), kind: 'image',
                style: { colour: '#000000', width: 0, dash: 'solid', opacity: 1 },
                data: { path, x: q2(x), y: q2(y), w: q2(w), h: q2(h), nw, nh, rot: 0, locked: false } };
  if (land) { apply(pageId, [], [rec]); return rec; }
  doOp(changeOp([{ page: pageId, removed: [], added: [rec] }]));
  selectRecs(pageId, [rec.id]);
  return rec;
}
// records on page pageId become the selection with the select tool on (a new picture; pw-v9d: a shared one once its note is
// open on that page). No undo step. False when the page has no layer on screen or none of the ids is on it
export function selectRecs(pageId, ids) {
  const d = data(pageId), on = ids.filter((id) => d.byId.has(id));
  if (!d.svg || !on.length) return false;
  if (T.tool !== 'select') { if (selectTool) selectTool(); else setTool('select'); }
  makeSel(pageId, on);
  return true;
}
// Duplicate (pw-v4o): a copy of the selection 24 px right and down, pulled back inside the page where it would leave it
// (along an axis where the box is wider than the page it keeps the plain 24 px); the copy is selected; CLIP stays as it was
const DUP_STEP = 24;
function duplicateSel() {
  if (!SEL) return;
  const page = SEL.page, d = data(page), recs = selRecs().sort(bySeq);
  if (!recs.length) return;
  const b = selBox(recs);
  // right and down, or where that is pulled back (the box sits at the edge) the other way, so the copy never lands on itself
  const step = (lo, hi, W) => { const v = keepIn(lo, hi, DUP_STEP, W, DUP_STEP), u = keepIn(lo, hi, -DUP_STEP, W, -DUP_STEP); return Math.abs(v) >= Math.abs(u) ? v : u; };
  addCopies(page, recs, step(b[0], b[2], d.w), step(b[1], b[3], d.h));
}
// Select all (pw-v4p): every stroke on page pageId (pen, highlighter and shapes, both layers) becomes the selection with
// the select tool on, the way a paste does; no undo step (a selection is not a change). False when the page is empty.
export function selectAll(pageId) {
  const d = data(pageId);
  const ids = d.strokes.filter((r) => !isLocked(r)).map((r) => r.id);   // U4c: a locked picture stays out
  if (!ids.length || !d.svg) return false;
  if (T.tool !== 'select') { if (selectTool) selectTool(); else setTool('select'); }
  makeSel(pageId, ids);
  return true;
}
// a finger held still on the desk (page.js): over a page, a small menu with Select all (disabled on an empty page)
// and Paste (disabled with nothing copied)
function holdMenu(cx, cy) {
  if (G || !openMenuAt) return;
  const at = surfaceAt(cx, cy);
  if (!at) return;                                 // off every page: nothing opens
  const pageId = at.id, x = at.x, y = at.y;
  openMenuAt(cx, cy, [data(pageId).strokes.some((r) => !isLocked(r)) ? { label: 'Select all', fn: () => selectAll(pageId) }   // U4c: a locked picture alone is nothing to select
                                                  : { label: 'Nothing to select', disabled: true, fn: () => {} },
                      CLIP ? { label: 'Paste', fn: () => pasteAt(pageId, x, y) }
                           : { label: 'Nothing to paste', disabled: true, fn: () => {} }]);
}
function deleteSel() {
  if (!SEL) return;
  const page = SEL.page, recs = selRecs();
  clearSelection();
  if (recs.length) doOp(changeOp([{ page, removed: recs, added: [] }]));
}
// does segment a-b touch the box B (inside it or crossing an edge)? Liang-Barsky clipping
function segInBox(a, b, B) {
  let t0 = 0, t1 = 1;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  for (const [p, q] of [[-dx, a[0] - B[0]], [dx, B[2] - a[0]], [-dy, a[1] - B[1]], [dy, B[3] - a[1]]]) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return true;
}
// strokes that touch the box b anywhere: a point inside, or a segment (of the stroke, or of a shape's outline)
// crossing its edge; the ink's half width counts as part of the stroke
function inBox(id, b) {
  const out = [];
  for (const r of data(id).strokes) {
    const q = boxOf(r), w = Math.max(1, (r.style.width || 0) / 2), B = [b[0] - w, b[1] - w, b[2] + w, b[3] + w];
    if (q[2] < B[0] || q[0] > B[2] || q[3] < B[1] || q[1] > B[3]) continue;   // nowhere near
    if (isImg(r)) {                                                // U4c: an unlocked picture whose turned box the box touches (or holds the box)
      if (isLocked(r)) continue;
      const pts = pointsOf(r);
      let hit = inImg(r, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2) || pts.some(([x, y]) => x >= B[0] && x <= B[2] && y >= B[1] && y <= B[3]);
      for (let i = 1; !hit && i < pts.length; i++) hit = segInBox(pts[i - 1], pts[i], B);
      if (hit) out.push(r.id);
      continue;
    }
    if (r.kind === 'axes') {                                       // U5e: an axis's end inside, or an axis line crossing the box
      const a = axesGeom(r);
      if (a && a.lines.some((s) => segInBox(s[0], s[1], B))) out.push(r.id);
      continue;
    }
    const pts = pointsOf(r);
    let hit = pts.some(([x, y]) => x >= B[0] && x <= B[2] && y >= B[1] && y <= B[3]);
    for (let i = 1; !hit && i < pts.length; i++) hit = segInBox(pts[i - 1], pts[i], B);
    if (hit) out.push(r.id);
  }
  return out;
}
// the stroke a tap lands on: every record within reach; when the hits hold both a highlighter-layer and a pen-layer
// record, only the layer of the last ink tool counts (pw-v4m); the topmost of what counts (highest seq) wins
// U4c: pictures are under all ink, so one counts only when no ink is in reach: the topmost picture whose turned box holds the tap
function topAt(id, x, y, reach) {
  const all = data(id).strokes, hits = [];
  for (let i = all.length - 1; i >= 0; i--) if (!isImg(all[i]) && near(all[i], x, y, reach)) hits.push(all[i]);   // top of the stack first
  if (!hits.length) { for (let i = all.length - 1; i >= 0; i--) if (isImg(all[i]) && inImg(all[i], x, y)) return all[i].id; return null; }
  if (hits.some(inHl) && hits.some((r) => !inHl(r))) {
    const wantHl = T.lastInk === 'highlighter';
    return hits.find((r) => inHl(r) === wantHl).id;
  }
  return hits[0].id;
}
// a finger tap (page.js: a touch that lifted within 6 px of where it landed): outside the selection's box it clears
function fingerTap(cx, cy) {
  if (!SEL || G) return;
  const at = surfaceAt(cx, cy), b = SEL.box;
  if (at && b && at.id === SEL.page && at.x >= b[0] && at.x <= b[2] && at.y >= b[1] && at.y <= b[3]) return;   // inside: the pen moves it
  clearSelection();
}
// the tray's colour tap and Restyle tap while a selection exists: one undo step each, the selection stays
export function hasSelection() { return !!SEL; }
function changeSel(fn) {
  if (!SEL) return false;
  const olds = [], news = [];
  for (const r of selRecs()) { const n = fn(r); if (n) { olds.push(r); news.push(n); } }
  if (olds.length) doOp(changeOp([{ page: SEL.page, removed: olds, added: news }]));
  return true;
}
export function recolourSelection(c) {          // colour only: width, dash, opacity and geometry stay (U4c: never a picture)
  return changeSel((r) => (isImg(r) || same((r.style || {}).colour, c) ? null : { ...r, style: { ...r.style, colour: c } }));
}
export function restyleSelection() { return changeSel(restyled); }   // the full restyle rule

// ---------------------------------------------------------------- restyle: its own colour, the matching tool's width and opacity; restyle never changes the dash
function restyled(r) {
  if (isImg(r)) return null;                                       // U4c: restyle never touches a picture
  if (r.kind === 'axes') {                                         // U5e: colour only; an axes stays thin, solid and opaque
    const c2 = (ST.restyle && ST.restyle.colour) || ST.pen.colour;
    return same((r.style || {}).colour, c2) ? null : { ...r, style: { ...r.style, colour: c2 } };
  }
  const p = ST.pen, h = ST.highlighter, hl = inHl(r), c = ST.restyle && ST.restyle.colour;
  const style = hl                                                 // a highlight (stroke or shape) stays a highlight
    ? { colour: c || h.colour, width: h.width, dash: 'solid', opacity: h.opacity }
    : { colour: c || p.colour, width: p.width, dash: (r.style && r.style.dash) || 'solid', opacity: 1 };
  const s = r.style || {};
  if (same(s.colour, style.colour) && +s.width === +style.width && (s.dash || 'solid') === style.dash && +(s.opacity ?? 1) === +style.opacity) return null;
  return { ...r, style };
}
const same = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();

// ---------------------------------------------------------------- the pen on the page (page.js hands events here)
function showRing(cx, cy) {
  if (!ring) {
    ring = document.createElement('div'); ring.id = 'eraserRing';
    ring.style.width = ring.style.height = AREA_SIZE + 'px';
    deskEl.appendChild(ring);
  }
  ring.hidden = false;
  ring.style.transform = `translate(${cx - deskBox.left - AREA_SIZE / 2}px, ${cy - deskBox.top - AREA_SIZE / 2}px)`;
}
function hideRing() { if (ring) ring.hidden = true; }

function note(page, removed, added) {
  let c = G.changes.get(page);
  if (!c) { c = { removed: new Map(), added: new Map() }; G.changes.set(page, c); }
  for (const r of removed) { if (c.added.has(r.id)) c.added.delete(r.id); else c.removed.set(r.id, r); }
  for (const r of added) c.added.set(r.id, r);
}
function eraseHere(cx, cy) {
  const at = surfaceAt(cx, cy);
  if (!at) return;
  const d = data(at.id);
  if (G.kind === 'eraser') {
    const reach = ERASE_REACH / G.z;
    const hits = d.strokes.filter((r) => !isImg(r) && near(r, at.x, at.y, reach + (r.style.width || 0) / 2));   // U4c: never a picture
    if (!hits.length) return;
    note(at.id, hits, []);
    apply(at.id, hits.map((r) => r.id), []);
    return;
  }
  if (G.kind === 'restyle') {                                      // each stroke it touches, once per drag
    const reach = ERASE_REACH / G.z, olds = [], news = [];
    for (const r of d.strokes) {
      if (isImg(r) || G.done.has(r.id) || !near(r, at.x, at.y, reach + (r.style.width || 0) / 2)) continue;
      G.done.add(r.id);
      const n = restyled(r);
      if (n) { olds.push(r); news.push(n); }
    }
    if (!olds.length) return;
    note(at.id, olds, news);
    apply(at.id, olds.map((r) => r.id), news);
    return;
  }
  const rad = AREA_SIZE / 2 / G.z, gone = [], pieces = [];
  for (const r of d.strokes) {
    if (isImg(r)) continue;                                        // U4c: the ring never bites a picture (not "later kinds go whole")
    const R = rad + (r.style.width || 0) / 2;
    if (r.kind === 'shape') {                                      // the stroke eraser removes a shape whole; this ring turns it into ink and cuts it
      if (!near(r, at.x, at.y, R)) continue;
      const out = [];
      let hit = false;
      for (const k of shapeToInk(r)) {
        const runs = cutInk(k.data.points, at.x, at.y, R);
        if (!runs) { out.push(k); continue; }                      // a part the ring misses stays whole, as ink
        hit = true;
        for (const pts of runs) out.push({ ...k, id: uuid(), style: { ...k.style }, data: { points: pts } });
      }
      if (!hit) continue;
      gone.push(r); pieces.push(...out);
      continue;
    }
    if (r.kind !== 'pen' && r.kind !== 'highlighter') {          // later kinds go whole
      if (near(r, at.x, at.y, R)) gone.push(r);
      continue;
    }
    const b = boxOf(r);
    if (at.x < b[0] - R || at.x > b[2] + R || at.y < b[1] - R || at.y > b[3] + R) continue;
    const runs = cut(r.data.points, at.x, at.y, R);
    if (!runs) continue;
    gone.push(r);
    for (const pts of runs) pieces.push({ ...r, id: uuid(), style: { ...r.style }, data: { ...r.data, points: pts } });
  }
  if (!gone.length) return;
  note(at.id, gone, pieces);
  apply(at.id, gone.map((r) => r.id), pieces);
}
function eraseTo(cx, cy) {
  const step = G.kind === 'area' ? AREA_SIZE / 4 : 3;               // stroke eraser and restyle: every 3 px
  const [lx, ly] = G.last || [cx, cy], n = Math.max(1, Math.ceil(Math.hypot(cx - lx, cy - ly) / step));
  for (let k = G.last ? 1 : n; k <= n; k++) eraseHere(lx + (cx - lx) * k / n, ly + (cy - ly) * k / n);
  G.last = [cx, cy];
  if (G.kind === 'area') showRing(cx, cy);
}

// pw-v7i: one pen sample through the One Euro filter (Casiez, Roussel and Vogel, CHI 2012). A low-pass filter whose
// cutoff rises with the pen's speed: a slow pen (small writing, where the wobble lives) is smoothed hard, a fast one
// hardly at all, so nothing trails behind the nib. f = { x, y, dx, dy, t }: the filtered point, its speed, the last time
// (ms, the event's timeStamp). Two events with the same time (synthetic ones) count as one 240 Hz tick apart.
const oeAlpha = (cutoff, dt) => 1 / (1 + 1 / (2 * Math.PI * cutoff * dt));
function oneEuro(f, x, y, ts) {
  const now = Number.isFinite(ts) ? ts : f.t + 1000 / 240;
  let dt = (now - f.t) / 1000;
  if (!(dt > 0.0005)) dt = 1 / 240;
  f.t = now;
  const ad = oeAlpha(OE.dcutoff, dt);                              // the speed, itself smoothed
  f.dx += ad * ((x - f.x) / dt - f.dx); f.dy += ad * ((y - f.y) / dt - f.dy);
  const a = oeAlpha(OE.mincutoff + OE.beta * Math.hypot(f.dx, f.dy), dt);
  f.x += a * (x - f.x); f.y += a * (y - f.y);
  return f;
}
// pw-v7i: a finished stroke's kept points, tidied. (1) The end hook goes: while the last point turns back by more than
// 120 degrees and lies within 1 page px of the point before it, it is dropped (the lift sample lands behind the nib).
// (2) RDP at TIDY_EPS drops the near-straight stair of points 0.5 px apart, rounded to 0.1 px, that made a slow line look
// washy. (3) A corner that RDP keeps and that turns more than 90 degrees keeps its two neighbours too: pathD draws
// through the midpoints, so with far neighbours it would cut the corner (a letter's turn lost up to 1 px in the test).
// (4) Kept points stay at most TIDY_GAP apart (the middle point of a longer gap is kept, again and again): the same
// midpoint drawing cut a gentle bend between two long straight runs by 1.7 px (tests/test_u2b.py, select all).
function tidy(pts) {
  const p = pts.slice();
  while (p.length >= 3 && dist(p[p.length - 1], p[p.length - 2]) <= 1 && turnAt(p[p.length - 3], p[p.length - 2], p[p.length - 1]) > 120) p.pop();
  if (p.length < 3) return p;
  const keep = rdpMask(p, TIDY_EPS), idx = [];
  for (let k = 0; k < p.length; k++) if (keep[k]) idx.push(k);
  for (let i = 1; i < idx.length - 1; i++) {
    if (turnAt(p[idx[i - 1]], p[idx[i]], p[idx[i + 1]]) > 90) keep[idx[i] - 1] = keep[idx[i] + 1] = 1;
  }
  const gaps = [];
  for (let k = 0, last = 0; k < p.length; k++) if (keep[k] && k > last) { gaps.push([last, k]); last = k; }
  while (gaps.length) {
    const [i, j] = gaps.pop();
    if (j - i > 1 && dist(p[i], p[j]) > TIDY_GAP) { const m = (i + j) >> 1; keep[m] = 1; gaps.push([i, m], [m, j]); }
  }
  return p.filter((_, k) => keep[k]);
}
// the pen held still: rearm the snap timer whenever the pen settles somewhere new
function armHold(cx, cy) {
  clearTimeout(G.holdT);
  G.anchor = [cx, cy];
  G.holdT = setTimeout(snapNow, HOLD_MS);
}
function snapNow() {
  const g = G;
  if (!g || g.kind !== 'draw') return;
  let shape = classify(g.rawPts);                                 // pw-v7e: shapes are read from the pen's own path, not the smoothed ink
  if (!shape) return;                                              // stays freehand
  const held = shape.type === 'line' ? alignHeld(shape, g.page, g.z, g.rec.id) : null;   // U5g: a held line lands exactly perpendicular
  if (held) shape = held.shape;
  const hl = g.rec.kind === 'highlighter';
  if (hl && shape.type === 'arrow') shape = { type: 'line', x1: shape.x1, y1: shape.y1, x2: shape.x2, y2: shape.y2 };   // no highlighter arrows
  if (hl && shape.type === 'carrow') shape = { ...shape, type: 'arc' };                    // ... curved ones neither: the shaft's arc
  // a highlighter shape keeps the highlighter's look (opacity under 1: it stays in its .hlo group)
  const style = hl ? { colour: g.rec.style.colour, width: g.rec.style.width, dash: 'solid', opacity: g.rec.style.opacity } : g.rec.style;
  const d = data(g.page), rec = { ...g.rec, kind: 'shape', style, data: shape }, el = makeEl(rec);
  g.el.after(el);
  const old = g.el;                                                // the soft cross-fade, then the freehand goes
  try {
    old.animate([{ opacity: 1 }, { opacity: 0 }], { duration: SNAP_ANIM, easing: 'ease-out', fill: 'forwards' });
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: SNAP_ANIM, easing: 'ease-out' });
  } catch (_) { /* no animations: it just swaps */ }
  setTimeout(() => old.remove(), SNAP_ANIM);
  G = { kind: 'snapped', page: g.page, rec, el, d, raw: g.rawPts.slice(), pt: g.pt, z: g.z, align: held ? held.hit : null };   // raw: the freehand (pen) points, kept for lastStroke
  if (held) {                                                      // the mark shows for the fade time and goes
    const mk = drawAlignMark(d.svg, markOf(held.hit, held.A, held.P, g.z), g.z);
    if (mk) setTimeout(() => fadeAlignMark(mk), 30);
  }
}

// ---------------------------------------------------------------- U5g: the perpendicular snap (js/align.js)
// the mark (the small square at the corner), an SVG <g class="alignMark"> in a page's ink svg; never a record
export function drawAlignMark(host, mk, z, el) {
  const paths = markPaths(mk);
  if (!host || !paths.length) { if (el) el.remove(); return null; }
  if (!el || el.parentNode !== host) { if (el) el.remove(); el = document.createElementNS(SVGNS, 'g'); el.setAttribute('class', 'alignMark'); host.appendChild(el); }
  el.classList.remove('fade');
  el.setAttribute('data-kind', mk.kind);
  if (mk.kind === 'perp') { el.setAttribute('data-x', String(mk.corner[0])); el.setAttribute('data-y', String(mk.corner[1])); el.setAttribute('data-side', String(mk.side)); }
  el.replaceChildren(...paths.map((q) => {
    const e = document.createElementNS(SVGNS, 'path');
    setAttrs(e, { class: q.cls, d: q.d, fill: 'none', stroke: SEL_BLUE, 'stroke-width': String(1.5 / z), 'stroke-linejoin': 'miter', 'stroke-linecap': 'round' });
    return e;
  }));
  return el;
}
// the lift: it fades out over FADE_MS (css .alignMark.fade), then goes; a prefers-reduced-motion user just sees it go
export function fadeAlignMark(el) {
  if (!el || el.dataset.fading) return;
  el.dataset.fading = '1';
  const still = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) { el.remove(); return; }
  el.classList.add('fade');
  setTimeout(() => el.remove(), FADE_MS);
}
const alignSegs = (pageId, id) => segsOf(data(pageId).strokes, axesGeom).filter((s) => s.id !== id);
// the Select tool dragging a line's or an arrow's end: the other end holds, the dragged end turns onto the exact direction
function alignGrab(g, pen) {
  const d = g.now.data, ty = d.type;
  if (ty !== 'line' && ty !== 'arrow') return;
  const A = g.h === 0 ? [d.x2, d.y2] : [d.x1, d.y1], v = [pen[0] - A[0], pen[1] - A[1]], l = Math.hypot(v[0], v[1]);
  let hit = null;
  if (l >= CM) hit = alignDir([v[0] / l, v[1] / l], alignSegs(g.page, g.rec.id), { A, P: pen, id: g.rec.id }, g.z, CM);
  g.align = hit;
  if (hit) {
    const k = Math.max(v[0] * hit.u2[0] + v[1] * hit.u2[1], CM), E = roundAlong(A, [A[0] + hit.u2[0] * k, A[1] + hit.u2[1] * k], hit.u2);
    const nd = { ...d };
    if (g.h === 0) { nd.x1 = E[0]; nd.y1 = E[1]; } else { nd.x2 = E[0]; nd.y2 = E[1]; }
    g.now = { ...g.now, data: nd };
    g.mark = drawAlignMark(data(g.page).svg, markOf(hit, A, E, g.z), g.z, g.mark);
  } else if (g.mark) { fadeAlignMark(g.mark); g.mark = null; }    // the hit let go mid-gesture
}
// a held stroke that became a line: the end nearer the target holds (a crossing with neither end near: the middle), the
// line turns about it, its length kept. Returns { shape, hit, A, P } or null
function alignHeld(shape, pageId, z, id) {
  const A = [shape.x1, shape.y1], P = [shape.x2, shape.y2], v = [P[0] - A[0], P[1] - A[1]], l = Math.hypot(v[0], v[1]);
  if (!(l > 0)) return null;
  const u = [v[0] / l, v[1] / l], hit = alignDir(u, alignSegs(pageId, id), { A, P, id }, z, CM);
  if (!hit) return null;
  const s = hit.seg, dA = segGap(A, s.a, s.b), dP = segGap(P, s.a, s.b), u2 = hit.u2, near = MEET / z;
  let a, b;
  if (Math.min(dA, dP) > near && segCross(A, P, s.a, s.b)) {      // a crossing with neither end near: about the middle
    const m = [(A[0] + P[0]) / 2, (A[1] + P[1]) / 2], h = l / 2;
    a = [r1(m[0] - u2[0] * h), r1(m[1] - u2[1] * h)];
    b = roundAlong(a, [m[0] + u2[0] * h, m[1] + u2[1] * h], u2);
  } else if (dA <= dP) { a = A; b = roundAlong(A, [A[0] + u2[0] * l, A[1] + u2[1] * l], u2); }
  else { b = P; a = roundAlong(P, [P[0] - u2[0] * l, P[1] - u2[1] * l], u2); }
  const fixed = { ...hit, corner: hit.kind === 'perp' ? lineCross(a, u2, s.a, s.b) : null };
  return { shape: { ...shape, x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, hit: fixed, A: a, P: b };
}
// for the checks: the gesture's hit while a drag or a held line holds one
export function alignNow() { return G && G.align ? JSON.parse(JSON.stringify(G.align)) : null; }

// U5a: a tool's shape (js/tools.js, the ruler's line), made and committed the way snapNow and up() do it: makeEl, in its
// group (a highlighter shape in its .hlo group) while it is drawn, then d.els and ONE doOp step. drop() takes an unfinished
// one off the page with nothing saved.
export function liveShape(pageId, rec) {
  const d = data(pageId);
  if (!d.svg) return null;
  const el = makeEl(rec);
  groupFor(d, rec).appendChild(el);
  return {
    el,
    set(r) { setGeom(el, r); },
    drop() { unplace(d, el); },
    commit(r) { setGeom(el, r); r.seq = Date.now(); d.els.set(r.id, el); doOp(changeOp([{ page: pageId, removed: [], added: [r] }])); },
  };
}

function down(e) {
  if (e.button === 2) return false;                               // the right button / pen button press: never a gesture (page.js flips the tool on its contextmenu)
  if (T.tool === 'pen' && barrel(e)) return false;                 // the pen tip down with the button held: a harmless miss, as before
  const at = surfaceAt(e.clientX, e.clientY);
  if (!at) { if (T.tool === 'select') clearSelection(); return false; }
  const d = data(at.id);
  if (!d.svg) return false;
  hideHandle();
  const z = view().z;
  if (T.tool === 'pen' || T.tool === 'highlighter') {              // the pen and the highlighter always draw, even on a shape's end
    const s = T.style;
    const style = T.tool === 'pen'
      ? { colour: s.colour, width: s.width, dash: s.dash || 'solid', opacity: 1 }
      : { colour: s.colour, width: s.width, dash: 'solid', opacity: s.opacity };
    const rec = { id: uuid(), page_id: at.id, seq: 0, kind: T.tool, style, data: { points: [[r1(at.x), r1(at.y)]] } };
    const el = makeEl(rec);
    groupFor(d, rec).appendChild(el);                              // newest, so last in its group
    G = { kind: 'draw', index: at.index, page: at.id, rec, el, holdT: 0, anchor: null, pt: e.pointerType || 'mouse', z: view().z,
          oe: { x: at.x, y: at.y, dx: 0, dy: 0, t: e.timeStamp }, lastRaw: null, rawPts: [[r1(at.x), r1(at.y)]] };
    // pw-v7i: oe is the One Euro filter's state (the filtered pen point, unrounded, its speed in page px/s, the last event's
    // time); lastRaw the last raw pen point; rawPts the raw path as before (MIN_STEP apart) for the snap
    armHold(e.clientX, e.clientY);                                 // pen and highlighter both snap when held
    return true;
  }
  if (T.tool === 'eraser' || T.tool === 'area' || T.tool === 'restyle') {
    deskBox = deskEl.getBoundingClientRect();
    G = { kind: T.tool, z, changes: new Map(), last: null, done: new Set() };
    eraseTo(e.clientX, e.clientY);
    return true;
  }
  if (T.tool === 'select') {                                       // first match wins (pw-v7m): ring, corner (from outside), inside the box, shape handle, a new box
    const grip = selGrip(at, z);
    if (grip === 'rot') {                                          // the ring: turn about the box's centre
      const b = SEL.box, c = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
      G = { kind: 'srotate', index: at.index, page: at.id, c, a0: Math.atan2(at.y - c[1], at.x - c[0]), a: 0, recs: selRecs() };
      return true;
    }
    if (grip !== null) {                                           // a corner: scale about the opposite one
      const q = selCorners(SEL.box), o = q[(grip + 2) % 4], c = q[grip];
      G = { kind: 'sresize', index: at.index, page: at.id, o, c, s: 1, recs: selRecs(), off: [c[0] - at.x, c[1] - at.y] };   // pw-v7m: off, no jump
      return true;
    }
    if (inSel(at) && SEL.locked) { G = { kind: 'still' }; return true; }   // U4c: a locked picture: a drag inside does nothing
    if (inSel(at)) {                                               // pw-v7m: inside the box (corner bands and handles too): move
      G = { kind: 'smove', index: at.index, page: at.id, p0: [at.x, at.y], dx: 0, dy: 0, recs: selRecs() };
      return true;
    }
    const h = handleAt(at.id, at.x, at.y, HANDLE_REACH / z);       // outside the box: a shape's handle within reach, on any shape of the page
    if (h) {
      clearSelection();                                            // no box or chips on a shape being reshaped
      G = { kind: 'grab', page: at.id, index: at.index, rec: h.rec, h: h.h, el: d.els.get(h.rec.id), now: h.rec, z,
            off: [h.at[0] - at.x, h.at[1] - at.y], p0: [at.x, at.y], far: 0 };   // the handle keeps its offset from the pen: no jump
      showHandle(e.clientX + (h.at[0] - at.x) * z, e.clientY + (h.at[1] - at.y) * z);
      return true;
    }
    clearSelection();                                              // outside (or another page): a new box
    const band = document.createElementNS(SVGNS, 'rect');
    setAttrs(band, { class: 'selband', x: at.x, y: at.y, width: 0, height: 0, fill: 'rgba(47,75,184,.06)', stroke: SEL_BLUE,
      'stroke-width': 1.2 / z, 'stroke-dasharray': f1(5 / z) + ' ' + f1(4 / z) });
    d.svg.appendChild(band);
    G = { kind: 'box', index: at.index, page: at.id, p0: [at.x, at.y], p1: [at.x, at.y], band, z };
    return true;
  }
  return false;
}
// the live preview while the selection is dragged: each selected path is redrawn from its record put through the
// gesture (no transform on the ink, so its width never changes); the records change on lift. The box and its
// handles ride a transform; the chips ride a move or a resize and hide during a turn
function redraw(el, rec) { if (rec.kind === 'shape' || rec.kind === 'axes' || rec.kind === 'image') setGeom(el, rec); else el.setAttribute('d', dOf(rec)); }
function liveSel(g) {
  const d = data(g.page), [f, s, rot] = selXf(g);
  for (const r of g.recs) { const el = d.els.get(r.id); if (el) redraw(el, xform(r, f, s, rot)); }
  if (g.kind === 'srotate') {
    SEL.live = null;
    SEL.g.setAttribute('transform', `rotate(${f1(g.a)} ${f1(g.c[0])} ${f1(g.c[1])})`);
    SEL.chips.style.visibility = 'hidden';
    const z = SEL.z || view().z, dg = SEL.deg;                     // the degrees just right of the ring (where it was drawn)
    dg.textContent = Math.round(g.a) + '°';
    dg.style.left = f1(SEL.rot[0] + 14 / z) + 'px'; dg.style.top = f1(SEL.rot[1]) + 'px';
    dg.style.transform = `scale(${1 / z}) translateY(-50%)`;
    dg.classList.add('on');
    return;
  }
  if (g.kind === 'smove') movingSheet(g.page, true);               // pw-v9f: the ink shows past the page's edge while it moves
  const ox = g.kind === 'sresize' ? g.o[0] : 0, oy = g.kind === 'sresize' ? g.o[1] : 0, dx = g.dx || 0, dy = g.dy || 0;
  SEL.live = [s, ox, oy, dx, dy];
  SEL.g.setAttribute('transform', `matrix(${s} 0 0 ${s} ${ox * (1 - s) + dx} ${oy * (1 - s) + dy})`);
  placeChips(SEL.live);
}
// pw-v9f: a page whose selection is being moved sits above the other pages and stops clipping its ink, so the moving ink
// stays in sight over the gap and over the next page (css .sheet.moving)
function movingSheet(pageId, on) {
  const el = document.querySelector(`#stack .sheet[data-id="${CSS.escape(pageId)}"]`);
  if (el) el.classList.toggle('moving', on);
}
function unliveSel(g) {
  movingSheet(g.page, false);
  const d = data(g.page);
  for (const r of g.recs) { const el = d.els.get(r.id); if (el) redraw(el, r); }
  if (SEL) { SEL.live = null; SEL.g.removeAttribute('transform'); SEL.chips.style.visibility = ''; SEL.deg.classList.remove('on'); placeChips(null); }
}
function move(events) {
  if (!G) return;
  const ev = events[events.length - 1];
  if (G.kind === 'draw') {
    const pts = G.rec.data.points, step = Math.max(MIN_STEP, 1 / G.z);   // pw-v7e: one screen px, never under the floor
    for (const e of events) {
      const [x, y] = surfacePoint(G.index, e.clientX, e.clientY), l = pts[pts.length - 1];
      G.lastRaw = [x, y];
      const lr = G.rawPts[G.rawPts.length - 1];                    // pw-v7e: the raw path, kept exactly as before, for classify
      if (Math.hypot(x - lr[0], y - lr[1]) >= MIN_STEP) G.rawPts.push([r1(x), r1(y)]);
      const f = oneEuro(G.oe, x, y, e.timeStamp);                  // pw-v7i: the filtered point is what is kept
      if (Math.hypot(f.x - l[0], f.y - l[1]) >= step) pts.push([r1(f.x), r1(f.y)]);
      if (G.anchor && Math.hypot(e.clientX - G.anchor[0], e.clientY - G.anchor[1]) > HOLD_PX) armHold(e.clientX, e.clientY);
    }
    G.el.setAttribute('d', pathD(pts));
    return;
  }
  if (G.kind === 'snapped' || G.kind === 'still') return;         // a snapped shape stays put until the pen lifts (U4c: 'still', a locked picture)
  if (G.kind === 'grab') {
    const [x, y] = surfacePoint(G.index, ev.clientX, ev.clientY);
    for (const e of events) {                                      // how far the pen ever got from where it landed (the tap rule)
      const [qx, qy] = surfacePoint(G.index, e.clientX, e.clientY);
      G.far = Math.max(G.far, Math.hypot(qx - G.p0[0], qy - G.p0[1]));
    }
    G.now = dragHandle(G.rec, G.h, x + G.off[0], y + G.off[1]);
    alignGrab(G, [x + G.off[0], y + G.off[1]]);                    // U5g: exactly 90 degrees to a line it meets
    if (G.el) setGeom(G.el, G.now);
    showHandle(ev.clientX + G.off[0] * G.z, ev.clientY + G.off[1] * G.z);
    return;
  }
  if (G.kind === 'box') {
    const [x, y] = surfacePoint(G.index, ev.clientX, ev.clientY);
    G.p1 = [x, y];
    setAttrs(G.band, { x: Math.min(G.p0[0], x), y: Math.min(G.p0[1], y), width: Math.abs(x - G.p0[0]), height: Math.abs(y - G.p0[1]) });
    return;
  }
  if (G.kind === 'smove') {
    const [x, y] = surfacePoint(G.index, ev.clientX, ev.clientY);
    G.dx = x - G.p0[0]; G.dy = y - G.p0[1];
    liveSel(G);
    return;
  }
  if (G.kind === 'srotate') {                                      // the pen's angle about the centre, less where it started
    const [x, y] = surfacePoint(G.index, ev.clientX, ev.clientY), c = G.c;
    let a = nrmDeg((Math.atan2(y - c[1], x - c[0]) - G.a0) * 180 / Math.PI);
    const n = Math.round(a / 15) * 15;
    if (Math.abs(a - n) <= 2.5) a = n;                             // near a multiple of 15: exactly that
    G.a = nrmDeg(r1(a)) || 0;
    liveSel(G);
    return;
  }
  if (G.kind === 'sresize') {
    const [px, py] = surfacePoint(G.index, ev.clientX, ev.clientY), { o, c } = G, x = px + G.off[0], y = py + G.off[1];   // pw-v7m: the pen's offset kept
    const vx = c[0] - o[0], vy = c[1] - o[1], L2 = vx * vx + vy * vy || 1;
    G.s = Math.max(0.05, ((x - o[0]) * vx + (y - o[1]) * vy) / L2);   // along the diagonal, so the aspect holds
    liveSel(G);
    return;
  }
  for (const e of events) eraseTo(e.clientX, e.clientY);
}
function up(e, cancelled) {
  const g = G; G = null;
  if (!g || g.kind === 'still') return;
  if (g.kind === 'draw' || g.kind === 'snapped') {
    clearTimeout(g.holdT);
    let lag = null;
    if (g.kind === 'draw' && g.lastRaw) {                          // pw-v7e: the stroke reaches where the pen lifted (a tap keeps its one point)
      const pts = g.rec.data.points, l = pts[pts.length - 1], step = Math.max(MIN_STEP, 1 / g.z);
      lag = Math.round(Math.hypot(g.lastRaw[0] - g.oe.x, g.lastRaw[1] - g.oe.y) * 100) / 100;   // pw-v7i: how far the filter trailed the pen
      if (Math.hypot(g.lastRaw[0] - l[0], g.lastRaw[1] - l[1]) > step) pts.push([r1(g.lastRaw[0]), r1(g.lastRaw[1])]);
      g.rec.data.points = tidy(pts);                               // pw-v7i: the end hook goes, the near-straight stair goes
      g.el.setAttribute('d', pathD(g.rec.data.points));
    }
    const points = (g.raw || g.rawPts).map((p) => [p[0], p[1]]), c = classify(points);   // a snapped stroke keeps its freehand points in g.raw; pw-v7e: the pen's raw path
    LAST = { points, pointerType: g.pt || 'mouse', z: g.z, n: points.length, len: Math.round(polyLen(points) * 10) / 10,
      classify: c ? c.type : null, snapped: g.kind === 'snapped', at: Date.now(), lag };
    if (FIT) LAST.fit = { ...FIT };                                 // a parabola: its fit and the arc's (pw-v4s)
    g.rec.seq = Date.now();
    data(g.page).els.set(g.rec.id, g.el);
    doOp(changeOp([{ page: g.page, removed: [], added: [g.rec] }]));   // a snap is one step: the shape
    return;
  }
  if (g.kind === 'grab') {
    hideHandle();
    if (g.mark) { fadeAlignMark(g.mark); g.mark = null; }          // U5g: the square fades out
    const moved = JSON.stringify(g.now.data) !== JSON.stringify(g.rec.data);
    if (e && Number.isFinite(e.clientX)) { const [qx, qy] = surfacePoint(g.index, e.clientX, e.clientY); g.far = Math.max(g.far, Math.hypot(qx - g.p0[0], qy - g.p0[1])); }
    if (!cancelled && g.far * g.z < 4) {                           // a tap on a handle (under 4 px on screen): no change, no undo step; it
      if (g.el) setGeom(g.el, g.rec);                              // selects as any select tap does (topAt, so the pw-v4m tie-break holds),
      makeSel(g.page, [topAt(g.page, g.p0[0], g.p0[1], GRAB / g.z) || g.rec.id]);   // else the shape whose handle it was
      return;
    }
    if (cancelled || !moved) { if (g.el) setGeom(g.el, g.rec); return; }
    doOp(changeOp([{ page: g.page, removed: [g.rec], added: [g.now] }]));
    return;
  }
  if (g.kind === 'box') {
    g.band.remove();
    const b = [Math.min(g.p0[0], g.p1[0]), Math.min(g.p0[1], g.p1[1]), Math.max(g.p0[0], g.p1[0]), Math.max(g.p0[1], g.p1[1])];
    if (cancelled) return;
    if ((b[2] - b[0]) * g.z < 4 || (b[3] - b[1]) * g.z < 4) {     // a tap: the topmost stroke under it, alone
      const id = topAt(g.page, g.p0[0], g.p0[1], GRAB / g.z);
      if (id) makeSel(g.page, [id]);
      return;
    }
    const ids = inBox(g.page, b);
    if (ids.length) makeSel(g.page, ids);
    return;
  }
  if (g.kind === 'smove' || g.kind === 'sresize' || g.kind === 'srotate') {
    unliveSel(g);
    const same = g.kind === 'smove' ? Math.hypot(g.dx, g.dy) < 0.5 : g.kind === 'sresize' ? Math.abs(g.s - 1) < 1e-3 : !g.a;
    if (cancelled || same) return;                                 // a tap or a 0 px drag: nothing changes, no reorder
    // the changed selection comes to the front: fresh seq values after every stroke on the page, in its own order
    // U5e: a turn leaves an axes stamp exactly as it was (no new seq either)
    const recs = (g.kind === 'srotate' ? g.recs.filter((r) => r.kind !== 'axes') : g.recs).filter((r) => !isLocked(r));   // U4c: a locked picture never moves
    if (!recs.length) return;
    if (g.kind === 'smove' && toOtherPage(g, e, recs)) return;
    const [f, s, rot] = selXf(g), all = data(g.page).strokes, top = all.length ? all[all.length - 1].seq : 0;
    const base = Math.max(Date.now(), top + 1);
    const news = recs.slice().sort(bySeq).map((r, k) => ({ ...xform(r, f, s, rot), seq: base + k }));
    doOp(changeOp([{ page: g.page, removed: recs, added: news }]));
    return;
  }
  hideRing();
  const changes = [];
  g.changes.forEach((c, page) => { if (c.removed.size || c.added.size) changes.push({ page, removed: [...c.removed.values()], added: [...c.added.values()] }); });
  if (changes.length) doOp(changeOp(changes));
}
// pw-v9f (her ask 11 Nov: "move ink across pages"): a moved selection lifted with the pen over ANOTHER page of the note
// goes to that page: the pen's spot on the new page is where it grabbed (the same offset as on its own page), fresh ids
// and seq values above that page's strokes in their own order, off the old page, ONE undo step for both pages; it stays
// selected on its new page. Lifted in the gap, off the pages, or on a sticky (or moved from a sticky): false, and the
// move stays on its own page as before.
function toOtherPage(g, e, recs) {
  if (typeof g.index !== 'number' || !e || !Number.isFinite(e.clientX)) return false;
  const at = surfaceAt(e.clientX, e.clientY);
  if (!at || at.sticky || at.id === g.page) return false;
  const d = data(at.id);
  if (!d.svg) return false;
  const dx = at.x - g.p0[0], dy = at.y - g.p0[1];
  const top = d.strokes.length ? d.strokes[d.strokes.length - 1].seq : 0, base = Math.max(Date.now(), top + 1);
  const news = recs.slice().sort(bySeq).map((r, k) => ({ ...xform(r, (q) => [q[0] + dx, q[1] + dy], 1, 0), id: uuid(), page_id: at.id, seq: base + k }));
  clearSelection();
  doOp(changeOp([{ page: g.page, removed: recs, added: [] }, { page: at.id, removed: [], added: news }]));
  makeSel(at.id, news.map((r) => r.id));
  return true;
}
export const hook = { down, move, up, hover, fingerTap, holdMenu };
