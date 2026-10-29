/* ============================================================
   IN-APP CALCULATOR — Casio fx-991ZA Plus II (stats workflow +
   COMP-mode maths engine)
   ------------------------------------------------------------
   A faithful, interactive replica of the calculator's stats flow,
   built to the exact key sequences the class is taught:
     • clear:        SHIFT 9 → 3 (All) → = (then AC leaves "Press [AC] key", Build 8)
     • frequency:    SHIFT MODE (SETUP) → ▼ → 4 (STAT) → 1 ON / 2 OFF
     • enter data:   MODE → 3 (STAT) → 1 (1-VAR), type values, AC
     • read a value: SHIFT 1 (STAT) → 4 (Var) → n/x̄/σx/sx, then =
                     SHIFT 1 (STAT) → 6 (MinMax) → minX/maxX/Q1/med/Q3, =
                     SHIFT 1 (STAT) → 3 (Sum)   → 1:Σx² / 2:Σx, then =
     • edit a value: SHIFT 1 (STAT) → 2 (Data) reopens the table; ▲▼ move
                     between rows, typing REPLACES that row, = stores it

   Every menu order above was re-checked key by key on Megan's real
   fx-991ZA PLUS II emulator on 2026-08-28, not recalled:
     STAT   1:Type 2:Data 3:Sum 4:Var 5:Distr 6:MinMax
     Sum    1:Σx²  2:Σx                  ← Σx is TWO
     Var    1:n    2:x̄   3:σx  4:sx
     MinMax 1:minX 2:maxX 3:Q1 4:med 5:Q3
   Results are computed from the entered data via statlib, so they
   are real. The COMP screen also has a real 2-D maths engine (round
   2) — fractions, roots, powers, trig — evaluated exact-first with
   a decimal fallback (see the engine section below).

   NOTE: Q1/med/Q3 deliberately use quartilesExclusive — the method
   the real fx-991ZA Plus II uses — so the on-screen device always
   agrees with the learner's calculator. Do NOT "fix" this to the
   school (n+1)/4 position method.
   ============================================================ */
import { el } from "./ui.js";
import { mean, stdDev, sortAsc, quartilesExclusive } from "./statlib.js";

/* ============================================================
   KEYPAD LAYOUT — full fx-991ZA Plus II face, transcribed from the
   real device (round 1 rebuild, 2026-08-27). Two CSS grids:
     FUNC_KEYS  — 6 columns × 5 rows (top row + 4 function rows),
                  with a round 4-way d-pad spanning cols 3–4, rows 1–2.
     NUM_KEYS   — 5 wider columns × 4 rows (the number block).
   Each entry: { id, row, col, label, shift, red, cls, dead }.
     label = main (white) legend, shift = gold SHIFT legend,
     red = red ALPHA legend, dead:true = renders + depresses like a
     real key but has NO click handler (no key uses it any more).
   Ids already routed by press()/compKey()/statKey()/menuKey() below
   are UNCHANGED (shift alpha up down left right mode on del ac
   d0-d9 dot mult div plus minus neg eq) — only their grid position
   moved. Round 2 wires: frac sqrt x2 pow sin cos tan lparen rparen
   sd ans.
   Calculator rebuild Build 1 (2026-10-04, CASIO-CALCULATOR-SPEC.md
   sections 1 and 2): EVERY key now has a handler, because ALPHA and
   SHIFT are one-shot on the device: "ALPHA then a key with no red
   letter: nothing is typed, ALPHA switches off". A key with no click
   handler could never switch them off. Keys whose own function is a
   later build (calc intdx xinv logbox log ln dms hyp eng exp10) do
   nothing on a plain press; rcl (RCL / SHIFT = STO) and mplus (M+ /
   SHIFT = M−) are live. CALC's red "=" and ∫'s red ":" were missing
   from the key faces and are added (spec §2).
   Calculator rebuild Build 4 (2026-10-04, spec §6–§9, §16): log, log□,
   ln, 10^□, e^□, ×10^x, ALPHA ×10^x (e), x⁻¹, x!, nCr, nPr, %, Abs, °'",
   the mixed-fraction template, SHIFT S⇔D and Fix / Norm are live. Still
   doing nothing on purpose (her ruling, not school use): hyp, ENG, ∫,
   d/dx, Σ, FACT, and on the COMP screen SHIFT + − 7 8 0 , Ans DEL (Pol,
   Rec, CONST, CONV, Rnd, Ran#, DRG▶, INS).
   Calculator rebuild Build 5 (2026-10-04, spec §10, §11): CALC (X?
   prompts in the order the letters appear, = asks again) and SOLVE (SHIFT
   CALC: `Solve for X`, the three-line X= / L−R= answer, Can't Solve) are
   live, on ONE reusable prompt screen (openPrompt) that TABLE and EQN will
   use too. CALC and SOLVE work in COMP mode only.
   Calculator rebuild Build 6 (2026-10-04, spec §12): TABLE (MODE 7) is
   live: f(X)= and g(X)= typed with the normal keys, Start? End? Step? on
   the Build 5 prompt screen (remembered between tables), and a view-only
   grid of 3 rows drawn by the same gridHTML as the STAT data grid.
   Calculator rebuild Build 7 (2026-10-04, spec §13, §14, §16): EQN (MODE
   5: two or three unknowns, the quadratic, the cubic) on a coefficient
   grid drawn by gridHTML, answered exactly, one answer per screen; the
   MODE menu's two pages; INEQ (MODE ▼ 2) for a quadratic with two real
   roots (the cubic item and the unmeasured cases are left out on purpose).
   Calculator rebuild Build 8 (2026-10-04, spec §15, §16): a STAT read-off
   (x̄, σx, n, A, B, r ...) is PASTED as a token onto the ordinary editable
   line, = works it out like any calculation (Ans, history, S⇔D, ◀ all act
   on it) and it shows by the normal display rules (10 significant digits);
   the two-variable type A+BX (MODE 3 2) with its X | Y grid and the Reg
   menu (A, B, r, x̂, ŷ); the SETUP menu's two boxed pages with 5:TABLE
   (f(x) only, or f(x) and g(x)); the CLR screens Clear? / Reset …? /
   Reset … Press [AC] key, for Setup, Memory and All.
   Calculator rebuild Build 10 (2026-10-04, spec §19.1, §19.5, §19.6):
   GCD( (ALPHA ×) and LCM( (ALPHA ÷) with the ";" separator (SHIFT )) and
   the new Argument ERROR; a plain decimal shows at most 12 digits counting
   the leading 0, cut off (0,00000014285); DEL at the start of a template
   box moves to the box before it, or at the first box removes the frame
   and keeps what was inside.
   ============================================================ */
const FUNC_KEYS = [
  // top row
  { row: 1, col: 1, id: "shift", label: "SHIFT", cls: "k-shift" },
  { row: 1, col: 2, id: "alpha", label: "ALPHA", cls: "k-alpha" },
  { row: 1, col: 5, id: "mode", label: "MODE", shift: "SETUP", cls: "k-fn" },
  { row: 1, col: 6, id: "on", label: "ON", cls: "k-fn" },
  // function row 1 (flanks the d-pad)
  { row: 2, col: 1, id: "calc", label: "CALC", shift: "SOLVE=", red: "=", cls: "k-fn" },
  { row: 2, col: 2, id: "intdx", label: "∫□", shift: "d/dx", red: ":", cls: "k-fn" },
  { row: 2, col: 5, id: "xinv", label: "x⁻¹", shift: "x!", cls: "k-fn" },
  { row: 2, col: 6, id: "logbox", label: "log□", shift: "Σ□", cls: "k-fn" },
  // function row 2
  { row: 3, col: 1, id: "frac", label: "▫/▫", shift: "▫≡▫/▫", red: "÷R", cls: "k-fn" },
  { row: 3, col: 2, id: "sqrt", label: "√▫", shift: "³√▫", cls: "k-fn" },
  { row: 3, col: 3, id: "x2", label: "x²", shift: "x³", red: "DEC", cls: "k-fn" },
  { row: 3, col: 4, id: "pow", label: "x^▫", shift: "ˣ√▫", red: "HEX", cls: "k-fn" },
  { row: 3, col: 5, id: "log", label: "log", shift: "10^▫", red: "BIN", cls: "k-fn" },
  { row: 3, col: 6, id: "ln", label: "ln", shift: "e^▫", red: "OCT", cls: "k-fn" },
  // function row 3
  { row: 4, col: 1, id: "neg", label: "(−)", shift: "∠", red: "A", cls: "k-fn" },
  { row: 4, col: 2, id: "dms", label: "°'\"", shift: "FACT", red: "B", cls: "k-fn" },
  { row: 4, col: 3, id: "hyp", label: "hyp", shift: "Abs", red: "C", cls: "k-fn" },
  { row: 4, col: 4, id: "sin", label: "sin", shift: "sin⁻¹", red: "D", cls: "k-fn" },
  { row: 4, col: 5, id: "cos", label: "cos", shift: "cos⁻¹", red: "E", cls: "k-fn" },
  { row: 4, col: 6, id: "tan", label: "tan", shift: "tan⁻¹", red: "F", cls: "k-fn" },
  // function row 4
  { row: 5, col: 1, id: "rcl", label: "RCL", shift: "STO", cls: "k-fn" },
  { row: 5, col: 2, id: "eng", label: "ENG", shift: "←", red: "i", cls: "k-fn" },
  { row: 5, col: 3, id: "lparen", label: "(", shift: "%", cls: "k-fn" },
  { row: 5, col: 4, id: "rparen", label: ")", shift: ";", red: "X", cls: "k-fn" },
  { row: 5, col: 5, id: "sd", label: "S⇔D", shift: "a b/c⇔d/c", red: "Y", cls: "k-fn" },
  { row: 5, col: 6, id: "mplus", label: "M+", shift: "M−", red: "M", cls: "k-fn" },
];
/* the round 4-way d-pad, sitting between ALPHA and MODE, spanning the
   top row + function row 1 (cols 3–4, rows 1–2). Rendered separately
   below (buildDpad) — ids up/down/left/right are unchanged. */
const DPAD_POS = { row: 1, col: 3, rowSpan: 2, colSpan: 2 };
const DPAD_KEYS = [
  { id: "up", label: "▲" }, { id: "down", label: "▼" },
  { id: "left", label: "◀" }, { id: "right", label: "▶" },
];

const NUM_KEYS = [
  { row: 1, col: 1, id: "d7", label: "7", shift: "CONST", cls: "k-num" },
  { row: 1, col: 2, id: "d8", label: "8", shift: "CONV", cls: "k-num" },
  { row: 1, col: 3, id: "d9", label: "9", shift: "CLR", cls: "k-num" },
  { row: 1, col: 4, id: "del", label: "DEL", shift: "INS", cls: "k-del" },
  { row: 1, col: 5, id: "ac", label: "AC", shift: "OFF", cls: "k-ac" },
  { row: 2, col: 1, id: "d4", label: "4", shift: "MATRIX", cls: "k-num" },
  { row: 2, col: 2, id: "d5", label: "5", shift: "VECTOR", cls: "k-num" },
  { row: 2, col: 3, id: "d6", label: "6", cls: "k-num" },
  { row: 2, col: 4, id: "mult", label: "×", shift: "nPr", red: "GCD", cls: "k-op" },
  { row: 2, col: 5, id: "div", label: "÷", shift: "nCr", red: "LCM", cls: "k-op" },
  { row: 3, col: 1, id: "d1", label: "1", shift: "STAT/DIST", cls: "k-num" },
  { row: 3, col: 2, id: "d2", label: "2", shift: "CMPLX", cls: "k-num" },
  { row: 3, col: 3, id: "d3", label: "3", shift: "BASE", cls: "k-num" },
  { row: 3, col: 4, id: "plus", label: "+", shift: "Pol", cls: "k-op" },
  { row: 3, col: 5, id: "minus", label: "−", shift: "Rec", cls: "k-op" },
  { row: 4, col: 1, id: "d0", label: "0", shift: "Rnd", cls: "k-num" },
  { row: 4, col: 2, id: "dot", label: ",", shift: "Ran#", red: "RanInt", cls: "k-num" },
  { row: 4, col: 3, id: "exp10", label: "×10ˣ", shift: "π", red: "e", cls: "k-num" },
  { row: 4, col: 4, id: "ans", label: "Ans", shift: "DRG▶", red: "PreAns", cls: "k-num" },
  { row: 4, col: 5, id: "eq", label: "=", cls: "k-eq" },
];

/* exported for verify-calculator.html — the full spec the on-screen
   grid is rendered from, so the verify page can check the RENDER
   against an independently-typed copy of the brief's spec table. */
export const KEY_SPEC = [...FUNC_KEYS, ...NUM_KEYS, ...DPAD_KEYS.map(k => ({ ...k, group: "dpad" }))];

const escapeHtml = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const fmtNum = v => (v == null ? "" : String(Math.round(v * 1e8) / 1e8).replace(".", ","));   // comma decimal (ZA locale, verified on the device) — the STAT data grid's cells ONLY (Build 8: read-offs follow the normal display rules)
/* the mean symbol x̄ — drawn with the bar ABOVE the x (the LCD font won't
   stack the combining macron, so it lands beside it). Render as an overline. */
const MEAN_GLYPH = '<span class="lcd-ov">x</span>';
/* Build 8: x̂ and ŷ (the Reg menu), the hat drawn by CSS above the letter
   for the same reason (.lcd-hat) */
const HAT_GLYPH = c => `<span class="lcd-hat">${c}</span>`;
/* Build 9: ȳ (the two-variable Var menu, spec §19.3), its bar drawn the same
   way as x̄'s. Its token is the one character U+0233. */
const YBAR = "ȳ";
const STAT_GLYPH = { "x̄": MEAN_GLYPH, "x̂": HAT_GLYPH("x"), "ŷ": HAT_GLYPH("y"), [YBAR]: '<span class="lcd-ov">y</span>' };
const statGlyph = name => STAT_GLYPH[name] || escapeHtml(name);

/* ============================================================
   COMP-MODE MATHS ENGINE (round 2) — exact-first, decimal fallback.
   Pure, S-free helpers so they're easy to reason about / re-test.
   A "Value" is one of:
     { kind:'rat',   n: BigInt, d: BigInt }              — reduced, d>0
     { kind:'surd',  n: BigInt, d: BigInt, rad: BigInt }  — (n/d)·√rad, rad squarefree>1
     { kind:'surd2', terms: [t1, t2] }                    — t1 + t2, each { n, d, rad } = (n/d)·√rad
                                                            (Build 3; rad 1 = a plain rational term)
     { kind:'pi',    n: BigInt, d: BigInt }               — (n/d)·π, n ≠ 0 (Build 3)
     { kind:'float', v: number }                          — decimal fallback
     { kind:'error', msg: "Syntax ERROR" | "Math ERROR" | "Argument ERROR" (Build 10) }
   Calculator rebuild Build 5 (2026-10-04, spec §11): SOLVE's root finder,
   solveNewton, works on decimals (Newton from the starting guess); its
   answer is kept to 15 significant digits and stored in X as that exact
   decimal.
   Square roots of rationals are exact; a cube or other root is exact
   only when it is a rational number (³√27 = 3, ⁴√16 = 2), else float.
   Calculator rebuild Build 4 (2026-10-04, spec §6–§9): log, ln and log□
   give a WHOLE number exactly (log(100 = 2, log₂(8) = 3, ln(e = 1) and a
   decimal otherwise; x! nCr nPr are exact whole numbers (BigInt); % is
   ÷100 (20% = 1/5); ×10^x is part of the number it follows (2,5×10⁻³ =
   1/400); the constant e (ALPHA ×10^x) is a decimal; °'" entries (30°15')
   are exact degrees; a mixed number 1¾ is 1 + ¾.
   Calculator rebuild Build 3 (2026-10-04, CASIO-CALCULATOR-SPEC.md §5,
   §6, §7): exact sums of TWO unlike roots, (a√b + c√d)/e, one of which may
   be a plain number (√3+√2, −1+√2, (√6−√2)/4, 2−√3). The arithmetic is done
   on BigInt term lists (termsOf / fromTerms below), never by recognising a
   float afterwards; a result needing three or more unlike roots falls back
   to a decimal. Trig is exact for every multiple of 15° (the 15° family is
   COMPUTED from the 30°/45° tables with this arithmetic, sin(b+45°) =
   sin b cos 45° + cos b sin 45°, not typed in). Rational powers are exact
   when the answer is rational (8^⅔ = 4, 27^(−⅔) = 1/9), otherwise a
   decimal, never a surd (2^½ = 1,414213562); odd roots of negatives work
   ((−8)^⅓ = −2). Surds show exactly only while the simplified number under
   the root is below 1000 (√999 = 3√111, √1001 = 31,63858404). π (SHIFT
   ×10^x) is a constant; only rational multiples of π stay exact (2π, ½π).
   Calculator rebuild Build 2 (2026-10-04, CASIO-CALCULATOR-SPEC.md §1,
   §3, §4, §7, §8): a missing ")" at the end of a box is closed for you;
   ▫/▫ and ˣ√ grab the operand before the cursor; x² / x^ / x³ chain from
   Ans; three-line error screens with Goto; the fraction size limit; Norm 2
   decimals with 10 significant digits and the ×10 form; the long-line ◀.
   ============================================================ */
class SyntaxErr extends Error {}

function gcdBig(a, b) { a = a < 0n ? -a : a; b = b < 0n ? -b : b; while (b) { [a, b] = [b, a % b]; } return a || 1n; }
function VERR(msg) { return { kind: "error", msg }; }
function VFLOAT(v) { return Number.isFinite(v) ? { kind: "float", v } : VERR("Math ERROR"); }
function mkRat(n, d) {
  if (d === 0n) return VERR("Math ERROR");
  if (d < 0n) { n = -n; d = -d; }
  const g = gcdBig(n, d);
  return { kind: "rat", n: n / g, d: d / g };
}
function mkSurd(n, d, rad) {
  if (rad === 0n) return mkRat(0n, 1n);
  if (rad === 1n) return mkRat(n, d);
  const r = mkRat(n, d);
  if (r.kind === "error") return r;
  return { kind: "surd", n: r.n, d: r.d, rad };
}
function squarefreeSplit(k) {   // k: BigInt ≥ 0 → { sq, rest } with k = sq²·rest, rest squarefree
  if (k === 0n) return { sq: 0n, rest: 0n };
  let sq = 1n, rest = k, p = 2n;
  while (p * p <= rest) {
    while (rest % (p * p) === 0n) { rest /= (p * p); sq *= p; }
    p += (p === 2n ? 1n : 2n);
  }
  return { sq, rest };
}
const isErr = v => v.kind === "error";
const isZeroV = v => v.kind === "rat" && v.n === 0n;
const termFloat = t => (Number(t.n) / Number(t.d)) * (t.rad === 1n ? 1 : Math.sqrt(Number(t.rad)));
function toFloatV(v) {
  if (v.kind === "rat") return Number(v.n) / Number(v.d);
  if (v.kind === "surd") return termFloat(v);
  if (v.kind === "surd2") return termFloat(v.terms[0]) + termFloat(v.terms[1]);
  if (v.kind === "pi") return (Number(v.n) / Number(v.d)) * Math.PI;
  return v.v;
}
const asFloatVal = v => VFLOAT(toFloatV(v));

/* ---- Build 3: exact sums of roots, as BigInt term lists ----
   Every exact algebraic value (rat, surd, surd2) is a list of terms
   (n/d)·√rad with rad squarefree (rad 1 = a plain rational term). + − ×
   work on these lists and fromTerms() collects like roots back into the
   value kinds: no term → 0, one → rat or surd, two → surd2, three or more
   (e.g. √2+√3+√5) → a decimal, the spec's fallback ("anything that leaves
   the shape falls back to a decimal"). So (√6−√2)(√6+√2) really comes back
   as the whole number 4, by exact BigInt arithmetic. */
const isAlg = v => v.kind === "rat" || v.kind === "surd" || v.kind === "surd2";
function termsOf(v) {
  if (v.kind === "rat") return v.n === 0n ? [] : [{ n: v.n, d: v.d, rad: 1n }];
  if (v.kind === "surd") return [{ n: v.n, d: v.d, rad: v.rad }];
  return v.terms;   // surd2
}
/* The order the device shows two terms in (spec §7): a plain number FIRST
   (−1+√2, 2−√3), otherwise the bigger root first (√3+√2, (√6−√2)/4). Only
   these two cases were measured; "bigger root" is read as the bigger number
   under the root, whatever the coefficients and signs (Blipwork reading:
   √2−√3 shows −√3+√2, and 3√2+√3 shows √3+3√2). */
const termOrder = (a, b) => (a.rad === 1n ? -1 : b.rad === 1n ? 1 : a.rad > b.rad ? -1 : 1);
function fromTerms(list) {
  const byRad = new Map();
  for (const t of list) {
    if (t.n === 0n) continue;
    const key = t.rad.toString(), p = byRad.get(key);
    byRad.set(key, p ? { n: p.n * t.d + t.n * p.d, d: p.d * t.d, rad: t.rad } : { n: t.n, d: t.d, rad: t.rad });
  }
  const terms = [];
  for (const t of byRad.values()) { if (t.n === 0n) continue; const r = mkRat(t.n, t.d); terms.push({ n: r.n, d: r.d, rad: t.rad }); }
  if (terms.length === 0) return mkRat(0n, 1n);
  if (terms.length === 1) { const t = terms[0]; return t.rad === 1n ? mkRat(t.n, t.d) : mkSurd(t.n, t.d, t.rad); }
  if (terms.length === 2) return { kind: "surd2", terms: terms.sort(termOrder) };
  return VFLOAT(terms.reduce((s, t) => s + termFloat(t), 0));
}
const negTerm = t => ({ n: -t.n, d: t.d, rad: t.rad });
/* (n/d)·π (Build 3, spec §7/§9): only RATIONAL multiples of π stay exact.
   π + π = 2π and π÷2 = ½π stay exact; π + 1, π², √2·π are decimals. */
function mkPi(n, d) {
  const r = mkRat(n, d);
  if (isErr(r) || r.n === 0n) return r;
  return { kind: "pi", n: r.n, d: r.d };
}

function vAddSub(a, b, sign) {
  if (isErr(a)) return a; if (isErr(b)) return b;
  if (a.kind === "float" || b.kind === "float") return asFloatVal({ kind: "float", v: toFloatV(a) + sign * toFloatV(b) });
  if (a.kind === "pi" || b.kind === "pi") {
    if (isZeroV(b)) return a;
    if (isZeroV(a)) return sign === 1 ? b : vNeg(b);
    if (a.kind === "pi" && b.kind === "pi") return mkPi(a.n * b.d + BigInt(sign) * b.n * a.d, a.d * b.d);
    return asFloatVal({ kind: "float", v: toFloatV(a) + sign * toFloatV(b) });   // π + 1 = 4,141592654 (spec §7)
  }
  if (!isAlg(a) || !isAlg(b)) return asFloatVal({ kind: "float", v: toFloatV(a) + sign * toFloatV(b) });   // a kind a later build adds: decimal until it says otherwise
  return fromTerms([...termsOf(a), ...(sign === 1 ? termsOf(b) : termsOf(b).map(negTerm))]);
}
const vAdd = (a, b) => vAddSub(a, b, 1);
const vSub = (a, b) => vAddSub(a, b, -1);
function vNeg(a) {
  if (isErr(a)) return a;
  if (a.kind === "float") return VFLOAT(-a.v);
  if (a.kind === "rat") return mkRat(-a.n, a.d);
  if (a.kind === "pi") return mkPi(-a.n, a.d);
  if (a.kind === "surd2") return fromTerms(a.terms.map(negTerm));
  return mkSurd(-a.n, a.d, a.rad);
}
function vMul(a, b) {
  if (isErr(a)) return a; if (isErr(b)) return b;
  if (a.kind === "float" || b.kind === "float") return asFloatVal({ kind: "float", v: toFloatV(a) * toFloatV(b) });
  if (a.kind === "pi" || b.kind === "pi") {
    if (isZeroV(a) || isZeroV(b)) return mkRat(0n, 1n);
    if (a.kind === "pi" && b.kind === "rat") return mkPi(a.n * b.n, a.d * b.d);
    if (b.kind === "pi" && a.kind === "rat") return mkPi(a.n * b.n, a.d * b.d);
    return asFloatVal({ kind: "float", v: toFloatV(a) * toFloatV(b) });   // π², √2·π: not a rational multiple of π
  }
  if (a.kind === "rat" && b.kind === "rat") return mkRat(a.n * b.n, a.d * b.d);
  if (!isAlg(a) || !isAlg(b)) return asFloatVal({ kind: "float", v: toFloatV(a) * toFloatV(b) });   // a kind a later build adds
  const out = [];
  for (const p of termsOf(a)) for (const q of termsOf(b)) {
    const { sq, rest } = squarefreeSplit(p.rad * q.rad);   // √r·√s = sq·√rest
    out.push({ n: p.n * q.n * sq, d: p.d * q.d, rad: rest });
  }
  return fromTerms(out);
}
function vInv(a) {
  if (isErr(a)) return a;
  if (a.kind === "float") return a.v === 0 ? VERR("Math ERROR") : VFLOAT(1 / a.v);
  if (a.kind === "rat") return a.n === 0n ? VERR("Math ERROR") : mkRat(a.d, a.n);
  if (a.kind === "pi") return VFLOAT(1 / toFloatV(a));   // 1/π is not a rational multiple of π
  if (a.kind === "surd2") {
    /* 1/(p + q) = (p − q)/(p² − q²): p² and q² are rational, and they are
       never equal for two unlike squarefree roots, so this never divides by
       0. 1/(√2+1) = (√2−1)/(2−1) = −1+√2 (spec §7). */
    const [p, q] = a.terms;
    const sq = t => mkRat(t.n * t.n * t.rad, t.d * t.d);
    return vDiv(fromTerms([p, negTerm(q)]), vSub(sq(p), sq(q)));
  }
  if (a.n === 0n) return VERR("Math ERROR");
  return mkSurd(a.d, a.n * a.rad, a.rad);   // 1/((n/d)√rad) = (d/(n·rad))·√rad
}
function vDiv(a, b) { if (isErr(a)) return a; if (isErr(b)) return b; return vMul(a, vInv(b)); }
function vPowInt(a, nInt) {
  if (isErr(a)) return a;
  if (a.kind === "float") return VFLOAT(Math.pow(a.v, nInt));
  if (Math.abs(nInt) > 64) return VFLOAT(Math.pow(toFloatV(a), nInt));
  const neg = nInt < 0, n = Math.abs(nInt);
  let result = mkRat(1n, 1n), base = a, e = n;
  while (e > 0) { if (e & 1) result = vMul(result, base); if (isErr(result)) return result; e >>= 1; if (e > 0) { base = vMul(base, base); if (isErr(base)) return base; } }
  return neg ? vInv(result) : result;
}
/* x^ (Build 3, spec §6). A whole-number exponent keeps surds: (√2)³ = 2√2.
   A fraction or decimal exponent p/q on a RATIONAL base gives the exact
   answer only when it is rational, i.e. when top and bottom of the base are
   perfect q-th powers: 4^½ = 2, 4^0,5 = 2, 8^⅔ = 4, 4^(−½) = ½, 27^(−⅔) =
   1/9. Otherwise a DECIMAL, never a surd: 2^½ = 1,414213562. An odd root of
   a negative works ((−8)^⅓ = −2, and as a decimal when not exact); an even
   root of a negative is Math ERROR ((−4)^0,5). */
const MAX_EXACT_ROOT = 64n;   // q-th roots tried exactly up to q = 64 (exponent 0,015625); past that, decimal
function vPow(base, exp) {
  if (isErr(base)) return base; if (isErr(exp)) return exp;
  if (exp.kind === "rat" && exp.d === 1n && exp.n >= -64n && exp.n <= 64n) return vPowInt(base, Number(exp.n));
  if (exp.kind === "rat" && exp.d > 1n) {
    const p = exp.n, q = exp.d, oddQ = q % 2n === 1n;
    if (base.kind === "rat" && q <= MAX_EXACT_ROOT && p >= -64n && p <= 64n) {
      const neg = base.n < 0n;
      if (neg && !oddQ) return VERR("Math ERROR");
      const rn = intRoot(neg ? -base.n : base.n, Number(q)), rd = intRoot(base.d, Number(q));
      if (rn !== null && rd !== null) return vPowInt(mkRat(neg ? -rn : rn, rd), Number(p));
    }
    const f = toFloatV(base);
    if (f < 0) {
      if (!oddQ) return VERR("Math ERROR");
      const m = Math.pow(-f, Number(p) / Number(q));
      return VFLOAT(p % 2n === 0n ? m : -m);   // a real odd root: (−x)^(p/q) = ±x^(p/q)
    }
    return VFLOAT(Math.pow(f, Number(p) / Number(q)));
  }
  return VFLOAT(Math.pow(toFloatV(base), toFloatV(exp)));
}
function vSqrt(a) {
  if (isErr(a)) return a;
  if (a.kind === "float") return a.v < 0 ? VERR("Math ERROR") : VFLOAT(Math.sqrt(a.v));
  if (a.kind !== "rat") { const f = toFloatV(a); return f < 0 ? VERR("Math ERROR") : VFLOAT(Math.sqrt(f)); }   // √ of a surd, a two-term sum or a π form: decimal (no exact type for it)
  if (a.n < 0n) return VERR("Math ERROR");
  if (a.n === 0n) return mkRat(0n, 1n);
  const num = a.n * a.d;
  const { sq, rest } = squarefreeSplit(num);
  return mkSurd(sq, a.d, rest);
}
/* ³√ (SHIFT √): exact when the answer is rational (³√27 = 3, spec §6;
   ³√(8/27) = ⅔, the same rule ˣ√ with index 3 already followed), else a
   decimal. A NEGATIVE radicand keeps its old behaviour (the real cube root
   as a decimal): the spec did not measure ³√ of a negative. */
function vCbrt(a) {
  if (isErr(a)) return a;
  if (a.kind === "rat" && a.n >= 0n) {
    const rn = intRoot(a.n, 3), rd = intRoot(a.d, 3);
    if (rn !== null && rd !== null) return mkRat(rn, rd);
  }
  return VFLOAT(Math.cbrt(toFloatV(a)));
}
/* exact k-th root of a BigInt a ≥ 0, or null when a is not a perfect k-th power */
function intRoot(a, k) {
  if (a < 2n) return a;
  const approx = Math.round(Math.pow(Number(a), 1 / k));
  if (!Number.isFinite(approx)) return null;
  const r = BigInt(approx), K = BigInt(k);
  for (const c of [r - 1n, r, r + 1n]) if (c >= 0n && c ** K === a) return c;
  return null;
}
/* ˣ√ (SHIFT x^, calculator Build 2, spec §6/§8): the index-th root of the
   radicand. Index 2 is exactly the √ key (exact surds); a whole-number
   index whose radicand is a perfect power of it gives the exact rational
   root (⁴√16 = 2); everything else is a decimal, the existing value rules.
   A NEGATIVE radicand stays Math ERROR here (Build 3 left it alone): the
   spec measured odd roots of negatives only through x^, (−8)^⅓ = −2, and
   not through ³√ or ˣ√, so this is kept until a probe says otherwise. */
function vXroot(idx, x) {
  if (isErr(idx)) return idx; if (isErr(x)) return x;
  if (idx.kind === "rat" && idx.d === 1n && idx.n === 2n) return vSqrt(x);
  if (idx.kind === "rat" && idx.d === 1n && idx.n > 0n && idx.n <= 64n && x.kind === "rat" && x.n >= 0n) {
    const k = Number(idx.n), rn = intRoot(x.n, k), rd = intRoot(x.d, k);
    if (rn !== null && rd !== null) return mkRat(rn, rd);
  }
  const n = toFloatV(idx);
  if (n === 0) return VERR("Math ERROR");
  return VFLOAT(Math.pow(toFloatV(x), 1 / n));
}
/* exact equality of two exact algebraic values (Build 3: by exact
   subtraction, so a two-term sum compares exactly too) */
function valuesEqual(a, b) {
  if (isErr(a) || isErr(b) || !isAlg(a) || !isAlg(b)) return false;
  return isZeroV(vSub(a, b));
}

/* ---- Build 4: more keys (spec §6–§9) ---- */
const TEN = mkRat(10n, 1n), HUNDRED = mkRat(100n, 1n), RT_ONE = mkRat(1n, 1n);
const E_VAL = VFLOAT(Math.E);   // the constant e (ALPHA ×10^x): a decimal, like e¹ = 2,718281828 (spec §6)
const pow10 = e => (e >= 0n ? mkRat(10n ** e, 1n) : mkRat(1n, 10n ** -e));
/* a value that is a whole number, as a BigInt (a decimal only when it is
   exactly whole), else null: what x!, nCr and nPr accept */
function wholeOf(v) {
  if (v.kind === "rat" && v.d === 1n) return v.n;
  if (v.kind === "float" && Number.isInteger(v.v) && Math.abs(v.v) <= Number.MAX_SAFE_INTEGER) return BigInt(v.v);
  return null;
}
/* the exact decimal a float shows at 15 significant digits, as a fraction:
   rounding for Fix and the °'" form is then done exactly, never on binary
   floats (1,005 with Fix 2 is 1,01, as a decimal machine would round it) */
function floatToRat(f) {
  const [m, ex] = Math.abs(f).toPrecision(15).split("e");
  const [ip, fp = ""] = m.split(".");
  let n = BigInt(ip + fp), d = 10n ** BigInt(fp.length);
  const e = ex ? Number(ex) : 0;
  if (e > 0) n *= 10n ** BigInt(e); else if (e < 0) d *= 10n ** BigInt(-e);
  return mkRat(f < 0 ? -n : n, d);
}
/* Foreman ruling: log and ln results are decimals unless they are whole
   numbers. For exact inputs that is decided exactly (base^k = x); a decimal
   input (the constant e, e^□ ...) has no exact form, so a result within
   10⁻¹² of a whole number is taken as that whole number (ln(e) = 1). */
function snapWhole(r) {
  if (!Number.isFinite(r)) return VERR("Math ERROR");
  const k = Math.round(r);
  return Math.abs(r - k) <= 1e-12 * Math.max(1, Math.abs(r)) ? mkRat(BigInt(k), 1n) : VFLOAT(r);
}
/* log□(base, x), and log( with base 10 (spec §9: log(100 = 2, log₂(8) = 3).
   A base or argument that is 0 or negative, or base 1, is Math ERROR. */
function vLogBase(base, x) {
  if (isErr(base)) return base; if (isErr(x)) return x;
  const fb = toFloatV(base), fx = toFloatV(x);
  if (!(fx > 0) || !(fb > 0) || fb === 1) return VERR("Math ERROR");
  const r = base === TEN ? Math.log10(fx) : Math.log(fx) / Math.log(fb);
  if (isAlg(base) && isAlg(x)) {
    const k = Math.round(r);
    if (Number.isFinite(r) && Math.abs(k) <= 64 && valuesEqual(vPowInt(base, k), x)) return mkRat(BigInt(k), 1n);
    return VFLOAT(r);
  }
  return snapWhole(r);
}
/* ln( (spec §9: ln(e = 1). ln of an exact number other than 1 is never
   whole, so only ln 1 = 0 is exact there. */
function vLn(x) {
  if (isErr(x)) return x;
  const fx = toFloatV(x);
  if (!(fx > 0)) return VERR("Math ERROR");
  if (isAlg(x)) return valuesEqual(x, RT_ONE) ? mkRat(0n, 1n) : VFLOAT(Math.log(fx));
  return snapWhole(Math.log(fx));
}
/* e^□ (SHIFT ln): a decimal (e¹ = 2,718281828, spec §6); e⁰ = 1 */
function vExp(e) {
  if (isErr(e)) return e;
  if (isZeroV(e)) return mkRat(1n, 1n);
  return VFLOAT(Math.exp(toFloatV(e)));
}
/* Abs (SHIFT hyp): |−5| = 5 (spec §9) */
function vAbs(a) { if (isErr(a)) return a; return toFloatV(a) < 0 ? vNeg(a) : a; }
/* x! (SHIFT x⁻¹): 5! = 120 (spec §9), exact BigInt. Only whole numbers
   0, 1, 2 ... ; anything else is Math ERROR. Past 170! no display could
   hold it (the same overflow every other result has), so it stops there. */
function vFact(a) {
  if (isErr(a)) return a;
  const n = wholeOf(a);
  if (n === null || n < 0n || n > 170n) return VERR("Math ERROR");
  let r = 1n; for (let k = 2n; k <= n; k++) r *= k;
  return mkRat(r, 1n);
}
/* nCr (SHIFT ÷) and nPr (SHIFT ×): 5C2 = 10, 5P2 = 20 (spec §9), exact
   BigInt. n and r whole, 0 ≤ r ≤ n, else Math ERROR. A result too big for
   any display (more than ~2000 factors) is Math ERROR, as an overflow. */
function vComb(nv, rv, kind) {
  if (isErr(nv)) return nv; if (isErr(rv)) return rv;
  const n = wholeOf(nv), r = wholeOf(rv);
  if (n === null || r === null || n < 0n || r < 0n || r > n) return VERR("Math ERROR");
  if (kind === "P") {
    if (r > 400n) return VERR("Math ERROR");
    let p = 1n; for (let k = n - r + 1n; k <= n; k++) p *= k;
    return mkRat(p, 1n);
  }
  const k = r < n - r ? r : n - r;
  if (k > 2000n) return VERR("Math ERROR");
  let c = 1n; for (let i = 1n; i <= k; i++) c = c * (n - k + i) / i;   // exact at every step
  return mkRat(c, 1n);
}
/* GCD( and LCM( (Build 10, spec §19.1): GCD(12;18 = 6, LCM(4;6 = 12,
   GCD(−12;18)+1 = 7 (a negative argument is fine, the answer is positive).
   An argument that is not a whole number is Argument ERROR (GCD(12,5;3).
   An error inside an argument (GCD(1÷0;3) stays that error. Not measured,
   Blipwork choice: a zero argument gives the plain maths answer, GCD(0;5)
   = 5, LCM(0;5) = 0, GCD(0;0) = 0. */
function vGcdLcm(name, av, bv) {
  if (isErr(av)) return av; if (isErr(bv)) return bv;
  let a = wholeOf(av), b = wholeOf(bv);
  if (a === null || b === null) return VERR("Argument ERROR");
  if (a < 0n) a = -a; if (b < 0n) b = -b;
  let g = a, r = b; while (r) [g, r] = [r, g % r];
  if (name === "GCD") return mkRat(g, 1n);
  return mkRat(g === 0n ? 0n : a / g * b, 1n);
}

/* ---- exact special-angle table, DEGREES ----
   The 30°/45° family is typed in; Build 3 (spec §5: exact for EVERY
   multiple of 15°) COMPUTES the other eight angles (15, 75, 105, …, 345)
   from it with the exact arithmetic above: θ − 45° is then a multiple of
   30°, and sin θ = sin(θ−45°)cos 45° + cos(θ−45°)sin 45°, cos θ =
   cos(θ−45°)cos 45° − sin(θ−45°)sin 45°. So sin 15° = (√6−√2)/4 comes out
   of BigInt arithmetic, not off a list, and tan = sin ÷ cos the same way
   (tan 15° = 2−√3). verify-calc-casio.html sweeps every entry against
   Math.sin/cos/tan. */
const RT = { half: mkRat(1n, 2n), nhalf: mkRat(-1n, 2n), one: mkRat(1n, 1n), none: mkRat(-1n, 1n), zero: mkRat(0n, 1n) };
const S2 = mkSurd(1n, 2n, 2n), nS2 = mkSurd(-1n, 2n, 2n), S3 = mkSurd(1n, 2n, 3n), nS3 = mkSurd(-1n, 2n, 3n);
const SIN_TABLE = { 0: RT.zero, 30: RT.half, 45: S2, 60: S3, 90: RT.one, 120: S3, 135: S2, 150: RT.half, 180: RT.zero, 210: RT.nhalf, 225: nS2, 240: nS3, 270: RT.none, 300: nS3, 315: nS2, 330: RT.nhalf };
const COS_TABLE = { 0: RT.one, 30: S3, 45: S2, 60: RT.half, 90: RT.zero, 120: RT.nhalf, 135: nS2, 150: nS3, 180: RT.none, 210: nS3, 225: nS2, 240: RT.nhalf, 270: RT.zero, 300: RT.half, 315: S2, 330: S3 };
function normDeg(d) { let x = d % 360; if (x < 0) x += 360; return x; }
for (let deg = 15; deg < 360; deg += 30) {
  if (SIN_TABLE[deg] !== undefined) continue;   // 45, 135, 225, 315 are in the typed table
  const b = normDeg(deg - 45);
  SIN_TABLE[deg] = vAdd(vMul(SIN_TABLE[b], S2), vMul(COS_TABLE[b], S2));
  COS_TABLE[deg] = vSub(vMul(COS_TABLE[b], S2), vMul(SIN_TABLE[b], S2));
}
const TAN_TABLE = {};   // null where cos = 0 (90°, 270°): Math ERROR
for (const k of Object.keys(SIN_TABLE)) TAN_TABLE[k] = isZeroV(COS_TABLE[k]) ? null : vDiv(SIN_TABLE[k], COS_TABLE[k]);
const TRIG_TABLE = { sin: SIN_TABLE, cos: COS_TABLE, tan: TAN_TABLE };
const degRange = (from, to) => { const a = []; for (let d = from; d <= to; d += 15) a.push(d); return a; };
const INV_RANGE = { asin: degRange(-90, 90), acos: degRange(0, 180), atan: degRange(-75, 75) };
const INV_OF = { asin: "sin", acos: "cos", atan: "tan" };
/* The angle in WHOLE degrees when it is exact, else null: a whole number in
   Deg mode; in Rad mode a rational multiple of π that is a whole number of
   degrees (π/6 → 30). The Rad case is a Blipwork choice (the spec only
   probed Deg): without it sin(π) would show 1,224646799×10⁻¹⁶. */
function exactDeg(argVal, drg) {
  if (drg === "D" && argVal.kind === "rat" && argVal.d === 1n) return argVal.n;
  if (drg === "R" && argVal.kind === "pi") { const m = mkRat(argVal.n * 180n, argVal.d); if (m.d === 1n) return m.n; }
  return null;
}

/* Build 3 also fixes tan: the old lookup answered Math ERROR for EVERY whole
   angle outside the 30°/45° table (tan(20 gave Math ERROR, not 0,3639702343). */
function evalTrigFn(name, argVal, drg) {
  if (isErr(argVal)) return argVal;
  const deg = exactDeg(argVal, drg);
  if (deg !== null) {
    const k = Number(((deg % 360n) + 360n) % 360n), table = TRIG_TABLE[name];
    if (table[k] !== undefined) return table[k] === null ? VERR("Math ERROR") : table[k];
  }
  const argDeg = toFloatV(argVal);
  const rad = drg === "R" ? argDeg : argDeg * Math.PI / 180;
  const fn = name === "sin" ? Math.sin : name === "cos" ? Math.cos : Math.tan;
  const v = fn(rad);
  return Number.isFinite(v) && Math.abs(v) < 1e15 ? VFLOAT(v) : VERR("Math ERROR");
}
/* sin⁻¹ / cos⁻¹ / tan⁻¹ of an exact value from the table give the whole
   angle (sin⁻¹(√3÷2) = 60, sin⁻¹ of sin 15° = 15), in Deg mode. Rad mode
   keeps its decimal answers (spec silent there). */
function evalInv(name, argVal, drg) {
  if (isErr(argVal)) return argVal;
  if (drg === "D" && isAlg(argVal)) {
    const table = TRIG_TABLE[INV_OF[name]];
    for (const deg of INV_RANGE[name]) {
      const tv = table[normDeg(deg)];
      if (tv && valuesEqual(tv, argVal)) return mkRat(BigInt(deg), 1n);
    }
  }
  const x = toFloatV(argVal);
  let rad;
  if (name === "asin") { if (x < -1 || x > 1) return VERR("Math ERROR"); rad = Math.asin(x); }
  else if (name === "acos") { if (x < -1 || x > 1) return VERR("Math ERROR"); rad = Math.acos(x); }
  else rad = Math.atan(x);
  return VFLOAT(drg === "R" ? rad : rad * 180 / Math.PI);
}
function applyFunc(name, inv, argVal, drg) {
  if (name === "log") return vLogBase(TEN, argVal);   // Build 4
  if (name === "ln") return vLn(argVal);
  return inv ? evalInv(name === "sin" ? "asin" : name === "cos" ? "acos" : "atan", argVal, drg) : evalTrigFn(name, argVal, drg);
}

/* ---- Build 5: SOLVE's root finder (spec §11) ----
   The device "finds the root reached from the starting guess (Newton-
   style)". This is Newton's method from the guess, the slope measured by a
   FORWARD difference (f(x+h) − f(x)) ÷ h with h = 10⁻⁶·max(1, |x|).
   Deterministic, no randomness. The forward difference is what reproduces
   the device's answer on X²−4 from 0: the true slope there is 0, but the
   forward difference is a tiny POSITIVE number, so the first step jumps far
   to the right and Newton walks back down onto +2 (spec: "From 0 on X²−4 it
   found +2"); from −5 it goes to −2. Measured device answers it must give:
   X²−4 from 0 → 2, from −5 → −2; 1000(1,08)^X = 2000 → 9,006468342;
   2X+1 = 7 → 3; X²+1 → Can't Solve.
   F(x) gives the two sides { l, r } as decimals, or null where the
   equation cannot be evaluated (a step that lands there is halved until it
   can be). It stops when a step is below 10⁻¹⁴ of X, and then only accepts
   X when L − R is tiny next to the size of the numbers involved; otherwise,
   or after 200 steps, it gives up (null = Can't Solve). */
const SOLVE_MAX_STEPS = 200;
function solveNewton(F, x0) {
  let x = x0, o = F(x);
  if (!o) return null;
  for (let it = 0; it < SOLVE_MAX_STEPS; it++) {
    const f = o.l - o.r;
    if (f === 0) return { x, l: o.l, r: o.r, scale: Math.max(1, Math.abs(o.l), Math.abs(o.r)) };
    let h = 1e-6 * Math.max(1, Math.abs(x)), oh = F(x + h);
    if (!oh) { h = -h; oh = F(x + h); }   // at the edge of where the equation is defined: measure the slope on the other side
    if (!oh) return null;
    const d = ((oh.l - oh.r) - f) / h;
    if (!Number.isFinite(d) || d === 0) return null;   // flat: no step to take
    let step = f / d, xn = x - step, on = Number.isFinite(xn) ? F(xn) : null;
    for (let k = 0; !on && k < 60; k++) { step /= 2; xn = x - step; on = Number.isFinite(xn) ? F(xn) : null; }
    if (!on) return null;
    x = xn; o = on;
    if (Math.abs(step) <= 1e-14 * Math.abs(x) || Math.abs(step) < 1e-300) {
      const scale = Math.max(1, Math.abs(o.l), Math.abs(o.r), Math.abs(x * d));
      return Math.abs(o.l - o.r) <= 1e-9 * scale ? { x, l: o.l, r: o.r, scale } : null;
    }
  }
  return null;
}

/* ---- display formatting ---- */
function fmtIntBig(b) { return b < 0n ? "−" + (-b).toString() : b.toString(); }
const fracHTML = (top, bottom) => `<span class="calc-frac"><span class="calc-frac-num">${top}</span><span class="calc-frac-bar"></span><span class="calc-frac-den">${bottom}</span></span>`;
const absBig = b => (b < 0n ? -b : b);
/* one term's text without its sign: 2 · √3 · 2√3 */
const termText = (k, rad) => (rad === 1n ? absBig(k).toString() : (absBig(k) === 1n ? "" : absBig(k).toString()) + "√" + rad);
const lcmBig = (a, b) => a / gcdBig(a, b) * b;
function formatExactHTML(v) {
  if (v.kind === "error") return escapeHtml(v.msg);
  if (v.kind === "float") return formatDecimal(v);
  if (v.kind === "rat") {
    if (v.n === 0n) return "0";
    if (v.d === 1n) return fmtIntBig(v.n);
    const neg = v.n < 0n, an = neg ? -v.n : v.n;
    return (neg ? "−" : "") + fracHTML(an, v.d);
  }
  if (v.kind === "pi") {
    /* spec §7: 2π shows 2π, π÷2 shows ½π (the stacked fraction FIRST, then π) */
    const neg = v.n < 0n, an = neg ? -v.n : v.n;
    return (neg ? "−" : "") + (v.d === 1n ? (an === 1n ? "" : an.toString()) : fracHTML(an, v.d)) + "π";
  }
  if (v.kind === "surd2") {
    /* (a√b + c√d)/e as ONE stacked fraction over the common denominator
       (spec §5: sin 15° = (√6−√2)/4), inline when e = 1 (√3+√2, −1+√2,
       2−√3). Terms come in termOrder. When BOTH tops are negative the minus
       goes in front of the whole fraction, as it does for −√3/2 (Blipwork
       choice: the device's form for e.g. sin(−105) was not probed). */
    const [p, q] = v.terms, e = lcmBig(p.d, q.d);
    const a = p.n * (e / p.d), c = q.n * (e / q.d);
    if (e === 1n) return (a < 0n ? "−" : "") + termText(a, p.rad) + (c < 0n ? "−" : "+") + termText(c, q.rad);
    if (a < 0n && c < 0n) return "−" + fracHTML(termText(a, p.rad) + "+" + termText(c, q.rad), e);
    return fracHTML((a < 0n ? "−" : "") + termText(a, p.rad) + (c < 0n ? "−" : "+") + termText(c, q.rad), e);
  }
  // surd
  const neg = v.n < 0n, an = neg ? -v.n : v.n;
  const radStr = `√${v.rad}`;
  if (v.d === 1n) return (neg ? "−" : "") + (an === 1n ? "" : an.toString()) + radStr;
  const numStr = (an === 1n ? "" : an.toString()) + radStr;
  return (neg ? "−" : "") + fracHTML(numStr, v.d);
}
/* Decimal display, calculator Build 2 (spec §7, Norm 2 = the factory
   setting): 10 significant digits, rounded (2/3 → 0,6666666667). A number
   with more than 10 digits switches to ×10 form, a small "×10" and a raised
   power (2^40 → 1,099511628×10¹²); small numbers stay plain decimals down
   to 10⁻⁹ (1/2000 → 0,0005, not 5×10⁻⁴) and only switch below that.
   Trailing zeros are dropped. Returns HTML (the ×10 form has markup).
   Build 8: STAT read-offs come through here too (foreman ruling: r =
   0,981155781 as on the device); before, they kept an 8-decimal text.
   Build 4: `fix` (0–9, or null for Norm) is the SETUP Fix setting. Fix only
   changes DECIMAL display (spec §7: 2÷3 stays ⅔, S⇔D → 0,67; sin(40 =
   0,64): exactly `fix` decimals, rounded half up. Past 10 digits before the
   comma the Norm ×10 form is kept (Fix there was not measured).
   Build 10 (spec §19.5): a plain decimal shows at most 12 digits counting
   the leading 0, so at most 11 decimal places, and the extra digits are CUT
   OFF, not rounded: the 10-significant-digit rounding happens first, then
   the cut (1÷7000000 = 0,00000014285, not ...86; 1÷3 = 0,3333333333 is
   untouched). Only numbers below 0,01 are long enough to be cut. The minus
   sign is not one of the 12 digits (not measured, Blipwork reading: the
   rule counts digits). Every Norm decimal on every screen comes through
   here, so the cut applies wherever such a decimal shows (Blipwork reading:
   the device was measured on the calculation line only). */
const DEC_MAX_DIGITS = 12;
function formatDecimal(v, fix = null) {
  if (v.kind === "error") return escapeHtml(v.msg);
  const f = toFloatV(v);
  if (!Number.isFinite(f)) return "Math ERROR";
  if (fix != null && Math.abs(f) < 1e10) return formatFix(v, fix);
  if (f === 0) return "0";
  const sign = f < 0 ? "−" : "";
  const [m, ex] = Math.abs(f).toExponential(9).split("e");   // ONE rounding, to 10 significant digits
  const e = Number(ex), digits = m.replace(".", "");
  if (e >= 10 || e < -9) {
    const tail = digits.slice(1).replace(/0+$/, "");
    return `${sign}${digits[0]}${tail ? "," + tail : ""}<span class="calc-x10">×10</span><sup class="calc-x10-exp">${e < 0 ? "−" : ""}${Math.abs(e)}</sup>`;
  }
  const ip = e >= 0 ? digits.slice(0, e + 1) : "0";
  const fp = (e >= 0 ? digits.slice(e + 1) : "0".repeat(-e - 1) + digits).slice(0, DEC_MAX_DIGITS - ip.length).replace(/0+$/, "");   // Build 10: the 12-digit cut
  return sign + ip + (fp ? "," + fp : "");
}
/* Fix n: exactly n decimals, rounded half up on the exact value (a decimal
   is first read at 15 significant digits). A value that rounds to 0 shows
   no minus sign (Blipwork choice, not measured). */
function formatFix(v, fix) {
  const r = v.kind === "rat" ? v : floatToRat(toFloatV(v));
  const neg = r.n < 0n, n = neg ? -r.n : r.n, scale = 10n ** BigInt(fix);
  const q = (2n * n * scale + r.d) / (2n * r.d);
  const s = q.toString().padStart(fix + 1, "0");
  return (neg && q !== 0n ? "−" : "") + s.slice(0, s.length - fix) + (fix ? "," + s.slice(s.length - fix) : "");
}
/* The °'" form of a result (spec §9: 30°15' = shows 30°15'0"). Seconds are
   rounded to hundredths, carrying into the minutes and degrees; how many
   decimals the device gives the seconds was not measured (Blipwork choice:
   at most 2, trailing zeros dropped). */
function formatDMS(v) {
  const r = v.kind === "rat" ? v : floatToRat(toFloatV(v));
  const neg = r.n < 0n, n = neg ? -r.n : r.n;
  const hs = (2n * n * 360000n + r.d) / (2n * r.d);   // hundredths of a second, rounded half up
  const deg = hs / 360000n, rest = hs % 360000n, min = rest / 6000n, sh = rest % 6000n;
  const frac = (sh % 100n).toString().padStart(2, "0").replace(/0+$/, "");
  return (neg && hs !== 0n ? "−" : "") + `${deg}°${min}'${sh / 100n}${frac ? "," + frac : ""}"`;
}
/* The mixed form (SHIFT S⇔D, spec §7/§8: 7/4 → 1¾, 100/3 → 33⅓): only an
   improper fraction that fits the display has one. */
const hasMixedForm = v => !!v && v.kind === "rat" && v.d > 1n && (v.n < 0n ? -v.n : v.n) > v.d && exactFits(v);
function formatMixed(v) {
  const neg = v.n < 0n, n = neg ? -v.n : v.n;
  return `<span class="calc-mixed">${neg ? "−" : ""}<span class="calc-mixed-whole">${n / v.d}</span>${fracHTML(n % v.d, v.d)}</span>`;
}
/* Spec §7: a fraction shows only while digits(top) + digits(bottom) + 1 is
   10 or less (1234/56789 yes, 12345/67891 → 0,1818355894), and a whole
   number only while it has at most 10 digits. Past that the SAME exact
   value shows as a decimal, and S⇔D has nothing to toggle to.
   Build 3 (spec §7): a surd shows exactly only while the number under the
   root, after simplifying, is below 1000 (√999 = 3√111 yes, √1001 → 31,63858404),
   for one root or two; no other surd limit is applied (none was measured).
   A π form uses the fraction rule on its multiple (Blipwork choice). */
const digitCount = b => (b < 0n ? -b : b).toString().length;
const SURD_LIMIT = 1000n;
function exactFits(v) {
  if (v.kind === "surd") return v.rad < SURD_LIMIT;
  if (v.kind === "surd2") return v.terms.every(t => t.rad < SURD_LIMIT);
  if (v.kind !== "rat" && v.kind !== "pi") return false;
  return v.d === 1n ? digitCount(v.n) <= 10 : digitCount(v.n) + digitCount(v.d) + 1 <= 10;
}
const formatValue = (v, dec, fix = null) => (dec || !exactFits(v)) ? formatDecimal(v, fix) : formatExactHTML(v);

/* ---- Build 6: TABLE (MODE 7, spec §12) ----
   Cells show DECIMALS, CUT OFF (not rounded) to about 6 characters: ⅔ shows
   0,6666 while the bottom line shows the rounded 0,6666666667; 2^X from −2
   shows 0,25 / 0,5 / 1. The cut is done exactly on the value (a decimal is
   first read at 15 significant digits, as Fix does), so nothing is ever
   rounded up. Blipwork choices where the spec is silent: the minus sign
   counts as one of the 6 characters (−⅔ shows −0,666); a whole-number part
   too long for 6 characters, or a value so small that the cut leaves only
   zeros, shows the ×10 form with its mantissa cut to two decimals
   (2^20 = 1048576 shows 1,04×10⁶); a value that cannot be worked out shows
   ERROR (foreman ruling). */
const TBL_CELL_CHARS = 6;
const TBL_VISIBLE = 3;         // spec §12: 3 rows visible
/* Row limit 20 "with the f and g setting" (spec §12, 21 rows → Insufficient
   MEM). Build 8 added SETUP 5:TABLE (f only); the f-only limit was not
   measured, so the limit stays 20 for both settings (foreman ruling). */
const TABLE_MAX_ROWS = 20;
const freshRange = () => ({ start: mkRat(1n, 1n), end: mkRat(5n, 1n), step: mkRat(1n, 1n) });   // factory Start 1, End 5, Step 1
function tableCellText(v) {
  if (isErr(v)) return "ERROR";
  const f = toFloatV(v);
  if (!Number.isFinite(f)) return "ERROR";
  if (f === 0) return "0";
  const r = v.kind === "rat" ? v : floatToRat(f);
  const neg = r.n < 0n, n = neg ? -r.n : r.n, sign = neg ? "−" : "";
  const ip = (n / r.d).toString(), head = sign + ip;
  if (head.length <= TBL_CELL_CHARS) {
    const room = TBL_CELL_CHARS - head.length - 1;   // digits left after the comma
    const fd = room > 0 ? ((n % r.d) * 10n ** BigInt(room) / r.d).toString().padStart(room, "0").replace(/0+$/, "") : "";
    if (ip !== "0" || fd) return head + (fd ? "," + fd : "");
  }
  const [m, ex] = Math.abs(f).toExponential(14).split("e");
  const md = m.replace(".", ""), tail = md.slice(1, 3).replace(/0+$/, ""), e = Number(ex);
  return `${sign}${md[0]}${tail ? "," + tail : ""}<span class="calc-x10">×10</span><sup class="calc-x10-exp">${e < 0 ? "−" : ""}${Math.abs(e)}</sup>`;
}
/* ---- Build 7: EQN (MODE 5, spec §13) and INEQ (MODE ▼ 2, spec §14) ----
   The solvers work on the exact value types (rat, surd, surd2) wherever the
   coefficients are exact, so the answers come out of BigInt arithmetic and
   are never recognised from a float afterwards: x²−2x−1 gives 1+√2 because
   the discriminant 8 goes through vSqrt (2√2) and the exact + and ÷. A
   decimal coefficient (sin 40 ...) makes the arithmetic decimal, as in COMP.
   An answer is a Value, or a complex root { kind: "cplx", re, im } (spec:
   x²+x+1 → X₁= −½+(√3/2)i), or an INEQ answer { kind: "ineq", ... }. These
   two are display shapes for the answer screens only, never engine values. */
const TWO = mkRat(2n, 1n), FOUR = mkRat(4n, 1n);
const signOfV = v => (isZeroV(v) ? 0 : Math.sign(toFloatV(v)));
const mkCplx = (re, im) => ({ kind: "cplx", re, im });
/* The roots of aX²+bX+c (a ≠ 0) through the exact discriminant.
   { n: 2, x1, x2 } with X₁ the BIGGER root (spec §13: "The bigger root is
   X₁", also when a < 0: −x²+4x−3 → 3 then 1); { n: 1, x } for a double
   root; { n: 0, re, im } for a complex pair, im > 0. null on an error. */
function quadRoots(a, b, c) {
  const bb = vMul(b, b), ac4 = vMul(FOUR, vMul(a, c)), D = vSub(bb, ac4), a2 = vMul(TWO, a);
  if (isErr(D) || isErr(a2)) return null;
  let ds = signOfV(D);
  /* a decimal discriminant that is only rounding noise counts as 0 */
  if (D.kind === "float" && Math.abs(D.v) <= 1e-12 * Math.max(Math.abs(toFloatV(bb)), Math.abs(toFloatV(ac4)))) ds = 0;
  if (ds === 0) return { n: 1, x: vDiv(vNeg(b), a2) };
  if (ds > 0) {
    const r = vSqrt(D), s = signOfV(a) > 0 ? r : vNeg(r);   // (−b + s)/(2a) is the bigger root for either sign of a
    return { n: 2, x1: vDiv(vAdd(vNeg(b), s), a2), x2: vDiv(vSub(vNeg(b), s), a2) };
  }
  return { n: 0, re: vDiv(vNeg(b), a2), im: vDiv(vSqrt(vNeg(D)), vAbs(a2)) };
}
/* a value that is really there: not an error, finite (an overflow is Math ERROR) */
const okVal = v => (v.kind === "cplx" ? okVal(v.re) && okVal(v.im) : v.kind === "ineq" ? okVal(v.lo) && okVal(v.hi) : !isErr(v) && Number.isFinite(toFloatV(v)));
/* Systems of 2 or 3 equations by Cramer's rule, exact. A singular system
   (determinant 0) was not measured: Math ERROR (foreman ruling). */
function det2(m) { return vSub(vMul(m[0][0], m[1][1]), vMul(m[0][1], m[1][0])); }
function det3(m) {
  const minor = (c1, c2) => vSub(vMul(m[1][c1], m[2][c2]), vMul(m[1][c2], m[2][c1]));
  return vAdd(vSub(vMul(m[0][0], minor(1, 2)), vMul(m[0][1], minor(0, 2))), vMul(m[0][2], minor(0, 1)));
}
function solveSystem(coef) {
  const n = coef.length, A = coef.map(r => r.slice(0, n)), rhs = coef.map(r => r[n]), det = n === 2 ? det2 : det3;
  const D = det(A);
  if (isErr(D) || isZeroV(D)) return null;
  if (D.kind === "float") {
    const big = Math.max(...A.flat().map(v => Math.abs(toFloatV(v))));
    if (Math.abs(D.v) <= 1e-12 * big ** n) return null;   // singular up to rounding
  }
  return ["X=", "Y=", "Z="].slice(0, n).map((label, k) => ({ label, v: vDiv(det(A.map((row, i) => row.map((v, j) => (j === k ? rhs[i] : v)))), D) }));
}
/* The quadratic's screens (spec §13): X₁= X₂= (bigger first), or one X= for
   a double root, or the complex pair (+i first; no "no real roots" message),
   then X-Value and Y-Value of the turning point, Minimum when a > 0,
   Maximum when a < 0. a = 0 was not measured: Math ERROR (Blipwork choice). */
function solveQuadratic([a, b, c]) {
  if (isZeroAny(a)) return null;
  const q = quadRoots(a, b, c);
  if (!q) return null;
  const out = q.n === 2 ? [{ label: "X₁=", v: q.x1 }, { label: "X₂=", v: q.x2 }]
    : q.n === 1 ? [{ label: "X=", v: q.x }]
    : [{ label: "X₁=", v: mkCplx(q.re, q.im) }, { label: "X₂=", v: mkCplx(q.re, vNeg(q.im)) }];
  const mm = signOfV(a) > 0 ? "Minimum" : "Maximum";
  out.push({ label: `X-Value ${mm}=`, v: vDiv(vNeg(b), vMul(TWO, a)) },
    { label: `Y-Value ${mm}=`, v: vSub(c, vDiv(vMul(b, b), vMul(FOUR, a))) });
  return out;
}
/* CUBIC ROOT ORDER (open question: spec §13 measured ONE cubic,
   x³−6x²+11x−6 → X₁= 1, X₂= 3, X₃= 2, "it seems to find one root first,
   then the other two bigger first"). Blipwork's rule, reproducing that:
   X₁ is the SMALLEST real root; the others follow BIGGER first; a complex
   pair (not measured) comes after the real root, +i first, in the
   quadratic's a+bi format. A repeated root (not measured) is shown once,
   and when only one root is left it is a single "X=", as the quadratic's
   double root is. Change THIS function if a probe shows another order. */
function cubicOrder(reals, cplx) {
  const rs = reals.slice().sort((x, y) => toFloatV(x) - toFloatV(y));
  const list = [rs[0], ...rs.slice(1).reverse()];
  if (cplx) list.push(mkCplx(cplx.re, cplx.im), mkCplx(cplx.re, vNeg(cplx.im)));
  return list.length === 1 ? [{ label: "X=", v: list[0] }] : list.map((v, k) => ({ label: `X${"₁₂₃"[k]}=`, v }));
}
const polyAt = (cs, x) => cs.reduce((acc, k) => vAdd(vMul(acc, x), k), mkRat(0n, 1n));
/* one real root of a cubic with decimal coefficients (a ≠ 0), by halving
   [−B, B], B the Cauchy bound: the cubic changes sign there, so a root of
   odd multiplicity is always found */
function cubicRealRootF(a, b, c, d) {
  const p = x => ((a * x + b) * x + c) * x + d;
  const B = 1 + Math.max(Math.abs(b / a), Math.abs(c / a), Math.abs(d / a));
  let lo = -B, hi = B, plo = p(lo);
  if (plo === 0) return lo;
  for (let k = 0; k < 400; k++) {
    const mid = (lo + hi) / 2;
    if (mid === lo || mid === hi) break;
    const pm = p(mid);
    if (pm === 0) return mid;
    if ((pm < 0) === (plo < 0)) { lo = mid; plo = pm; } else hi = mid;
  }
  return (lo + hi) / 2;
}
/* The cubic. With rational coefficients the roots are EXACT whenever one of
   them is rational: a rational root p/q of the integer-scaled cubic has q
   dividing the leading coefficient A, so A·root is a whole number. Each
   decimal approximation is rounded that way and tested by exact arithmetic;
   the first that is truly a root is divided out exactly, and the quadratic
   left over goes through quadRoots (exact surds and complex pairs). With no
   rational root, or decimal coefficients, the roots are decimals. */
function solveCubic(cs) {
  const [a, b, c, d] = cs;
  if (isZeroAny(a)) return null;   // not measured: Math ERROR (Blipwork choice)
  const [fa, fb, fc, fd] = cs.map(toFloatV);
  if (![fa, fb, fc, fd].every(Number.isFinite)) return null;
  const r = cubicRealRootF(fa, fb, fc, fd);
  const fb1 = fb + fa * r, fc1 = fc + fb1 * r;
  const qf = quadRoots(VFLOAT(fa), VFLOAT(fb1), VFLOAT(fc1));
  if (!qf) return null;
  const gather = (x0, q) => {
    const reals = [x0];
    if (q.n === 2) reals.push(q.x1, q.x2); else if (q.n === 1) reals.push(q.x);
    const distinct = [];
    for (const x of reals) if (!distinct.some(y => sameRoot(x, y))) distinct.push(x);
    return cubicOrder(distinct, q.n === 0 ? q : null);
  };
  if (cs.every(v => v.kind === "rat")) {
    const L = cs.reduce((l, v) => lcmBig(l, v.d), 1n), A = a.n * (L / a.d);
    const approx = [r, ...(qf.n === 2 ? [qf.x1, qf.x2] : qf.n === 1 ? [qf.x] : []).map(toFloatV)];
    for (const f of approx) {
      const m = Math.round(Number(A) * f);
      if (!Number.isSafeInteger(m)) continue;
      const x0 = mkRat(BigInt(m), A);
      if (!isZeroV(polyAt(cs, x0))) continue;
      const b1 = vAdd(b, vMul(a, x0)), c1 = vAdd(c, vMul(b1, x0));   // cs ÷ (X − x0), exactly
      const q = quadRoots(a, b1, c1);
      if (q) return gather(x0, q);
    }
  }
  return gather(VFLOAT(r), qf);
}
function sameRoot(x, y) {
  if (isAlg(x) && isAlg(y)) return valuesEqual(x, y);
  const fx = toFloatV(x), fy = toFloatV(y);
  return Math.abs(fx - fy) <= 1e-9 * Math.max(1, Math.abs(fx));
}
/* INEQ (spec §14): aX²+bX+c with > < ≥ ≤ 0. Measured for a quadratic with
   two real roots only: x²−5x+6<0 → A<X<B / 2<X<3, >0 → X<A;B<X / X<2;3<X
   (a SEMICOLON: the comma is the decimal sign). ≥ and ≤ follow the same
   shape with ≤ (built as the brief asks, not measured). One or no real
   root, and a = 0, were not measured: Math ERROR (foreman ruling), so no
   answer format is invented. */
function solveIneq([a, b, c], sign) {
  if (isZeroAny(a)) return null;
  const q = quadRoots(a, b, c);
  if (!q || q.n !== 2) return null;
  const gt = sign === ">" || sign === "≥", op = sign === ">" || sign === "<" ? "<" : "≤";
  const outside = gt === (signOfV(a) > 0);   // a > 0: > 0 outside the roots, < 0 between them; a < 0 the other way round
  return [{ label: outside ? `X${op}A;B${op}X` : `A${op}X${op}B`, v: { kind: "ineq", outside, op, lo: q.x2, hi: q.x1 } }];
}
/* An answer as the LCD shows it. dec = S⇔D switched it to decimals. A
   complex root: the real part (left out when 0), then the imaginary part,
   in brackets when it is a fraction or a root (−½+(√3/2)i), plain when it
   is a whole number or a decimal (Blipwork choice: only the bracketed form
   was measured), "i" alone for 1. */
function answerHTML(v, dec, fix) {
  const num = x => formatValue(x, dec || !exactFits(x), fix);
  if (v.kind === "ineq") {
    const op = escapeHtml(v.op);   // "<" must not open a tag
    return v.outside ? `X${op}${num(v.lo)};${num(v.hi)}${op}X` : `${num(v.lo)}${op}X${op}${num(v.hi)}`;
  }
  if (v.kind !== "cplx") return num(v);
  const exact = !dec && exactFits(v.re) && exactFits(v.im);
  const re = isZeroAny(v.re) ? "" : num(v.re);
  const neg = toFloatV(v.im) < 0, im = neg ? vNeg(v.im) : v.im;
  let imHTML;
  if (!exact) imHTML = formatDecimal(im, fix);
  else if (im.kind === "rat" && im.d === 1n) imHTML = im.n === 1n ? "" : im.n.toString();
  else imHTML = "(" + formatExactHTML(im) + ")";
  return re + (neg ? "−" : re ? "+" : "") + imHTML + "i";
}
/* S⇔D has something to switch to only while the exact form can show */
const answerHasExact = v => (v.kind === "cplx" ? exactFits(v.re) && exactFits(v.im) : v.kind === "ineq" ? exactFits(v.lo) && exactFits(v.hi) : exactFits(v));
/* The EQN types (spec §13) and INEQ's one quadratic grid (spec §14) */
const EQN_TYPES = {
  1: { kind: "sys", rows: 2, cols: 3 }, 2: { kind: "sys", rows: 3, cols: 4 },
  3: { kind: "quad", rows: 1, cols: 3 }, 4: { kind: "cubic", rows: 1, cols: 4 },
  ineq: { kind: "ineq", rows: 1, cols: 3 },
};
const EQN_HEADS = ["a", "b", "c", "d"];
/* "Four columns do not fit: the view slides sideways" (spec §13): three
   columns show at a time (Blipwork reading: three is what fits for the
   three-column types). */
const EQN_VIS_COLS = 3;

/* ---- Build 8: two-variable STAT, A+BX (spec §15) ----
   The line of best fit y = A + Bx and r, from the X | Y pairs. Worked out
   EXACTLY on the numbers as typed (each cell read at 15 significant digits
   as a fraction, the way Fix reads a decimal), so A for X 1,2,3,4 / Y
   2,4,5,8 is exactly 0, never a rounding crumb like 8,9×10⁻¹⁶ (device: A =
   0, B = 1,9, r = 0,981155781). With n the number of pairs:
     B = (nΣxy − ΣxΣy) / (nΣx² − (Σx)²),   A = (Σy − BΣx) / n,
     r = (nΣxy − ΣxΣy) / √((nΣx² − (Σx)²)(nΣy² − (Σy)²)).
   null when there are no pairs or every X is the same (B has no value);
   r is null when every Y is the same. Those read-offs are Math ERROR (not
   measured: it is a division by 0).
   Build 9: a pair may carry a weight `w` (a whole number, its FREQ; 1 when
   absent), and it counts that many times, so n and every sum are weighted
   (not device-measured). With every w = 1 the sums are exactly as before. */
function regFit(pairs) {
  if (!pairs.length) return null;
  const Z = mkRat(0n, 1n);
  let n = Z, sx = Z, sy = Z, sxx = Z, sxy = Z, syy = Z;
  for (const p of pairs) {
    const w = mkRat(BigInt(p.w ?? 1), 1n);
    if (isZeroV(w)) continue;
    const x = floatToRat(p.x), y = floatToRat(p.y), wx = vMul(w, x), wy = vMul(w, y);
    n = vAdd(n, w); sx = vAdd(sx, wx); sy = vAdd(sy, wy);
    sxx = vAdd(sxx, vMul(wx, x)); sxy = vAdd(sxy, vMul(wx, y)); syy = vAdd(syy, vMul(wy, y));
  }
  if (isZeroV(n)) return null;
  const dxx = vSub(vMul(n, sxx), vMul(sx, sx)), dxy = vSub(vMul(n, sxy), vMul(sx, sy)), dyy = vSub(vMul(n, syy), vMul(sy, sy));
  if (isErr(dxx) || isZeroV(dxx)) return null;
  const B = vDiv(dxy, dxx), A = vDiv(vSub(sy, vMul(B, sx)), n);
  let r = null;
  if (!isZeroV(dyy)) {
    const r2 = vDiv(vMul(dxy, dxy), vMul(dxx, dyy));
    const m = r2.n === r2.d ? 1 : Math.sqrt(toFloatV(r2));   // r = ±1 exactly on a perfect line
    r = signOfV(dxy) < 0 ? -m : m;
  }
  return { A, B, r };
}
/* x̂ and ŷ come AFTER the number they act on (spec §15: `5ŷ` = 9,5, the
   predicted y when x = 5), like x² does; on their own they are Syntax ERROR
   (Blipwork reading: nothing for them to act on) */
const REG_POSTFIX = new Set(["x̂", "ŷ"]);
const isStatAtom = t => t && t.k === "stat" && !REG_POSTFIX.has(t.v);

/* One LCD grid as an HTML table (Build 6): the STAT data grid and the TABLE
   screen are both drawn by this. heads and every row are lists of cells
   { html, cls }; the first cell of each is the row-number column. */
function gridHTML(cls, heads, rows) {
  const cell = (tag, c) => `<${tag}${c.cls ? ` class="${c.cls}"` : ""}>${c.html}</${tag}>`;
  return `<table class="${cls}"><tr>${heads.map(c => cell("th", c)).join("")}</tr>`
    + rows.map(r => `<tr>${r.map(c => cell("td", c)).join("")}</tr>`).join("") + `</table>`;
}

/* ---- token box compile + recursive-descent parse (no implicit ×) ----
   Build 2: every compiled token remembers `src`, its index in the box the
   learner typed, so a Syntax ERROR can say WHERE it happened and ◀/▶
   (Goto) can put the cursor just before that token (spec §3). The copies
   share the template sub-box arrays, so a position inside a fraction or a
   root points at the live box on screen. */
/* Build 4: two kinds of number literal are folded here, because on the
   device they are part of the NUMBER, not operators:
   - ×10^x (spec §9): a number, the small ×10, an optional minus, digits:
     `3×10 5` = 300000, 2,5×10⁻³ = 1/400. A ×10 with no number before it
     or no digits after it is left alone, so it is a Syntax ERROR (and Goto
     lands just before it): neither case was measured.
   - °'" (spec §9): up to three "number °'"" pairs, degrees, minutes,
     seconds: 30°15' = 30 + 15/60, exact. */
const isNumTok = t => t && (t.k === "d" || t.k === "c");
function compileBox(box) {
  const out = [];
  let i = 0;
  const readNum = () => { let s = ""; while (i < box.length && isNumTok(box[i])) { s += box[i].k === "c" ? "." : box[i].v; i++; } return s; };
  while (i < box.length) {
    const t = box[i];
    if (isNumTok(t)) {
      const src = i, s = readNum();
      if (box[i] && box[i].k === "x10") {
        let j = i + 1, neg = false, e = "";
        if (box[j] && box[j].k === "op" && box[j].v === "−") { neg = true; j++; }
        while (j < box.length && box[j].k === "d") { e += box[j].v; j++; }
        if (e && e.length <= 3) { out.push({ k: "num", v: s, e10: BigInt(e) * (neg ? -1n : 1n), src }); i = j; continue; }
      }
      if (box[i] && box[i].k === "dms") {
        const parts = [s]; i++;
        while (parts.length < 3 && isNumTok(box[i])) {
          const back = i, p = readNum();
          if (box[i] && box[i].k === "dms") { parts.push(p); i++; } else { i = back; break; }
        }
        out.push({ k: "dmsv", parts, src });
        continue;
      }
      out.push({ k: "num", v: s, src });
      continue;
    }
    out.push({ ...t, src: i }); i++;
  }
  return out;
}
/* does a box (or any template box inside it) hold a °'" mark? */
const boxHasDMS = box => box.some(t => t.k === "dms" || SUB_KEYS.some(key => Array.isArray(t[key]) && boxHasDMS(t[key])));
/* a Syntax ERROR at the parser's current token (or at `at`, a box index);
   at the end of the box the position is the box's end */
function synErr(st, at) {
  const e = new SyntaxErr(), t = st.arr[st.pos];
  e.at = { box: st.box, i: at != null ? at : t ? t.src : st.box.length };
  return e;
}
/* in a malformed number like 1,2,3 the error sits at the second comma */
const badCommaAt = s => { const a = s.indexOf("."), b = a < 0 ? -1 : s.indexOf(".", a + 1); return b > a ? b : 0; };
function numToValue(str) {
  if (!str || str === ".") throw new SyntaxErr();
  const parts = str.split(".");
  if (parts.length > 2) throw new SyntaxErr();
  if (parts.length === 1) { if (!/^\d+$/.test(parts[0])) throw new SyntaxErr(); return mkRat(BigInt(parts[0]), 1n); }
  const [ip, fp] = parts;
  if (!/^\d*$/.test(ip) || !/^\d*$/.test(fp) || (!ip && !fp)) throw new SyntaxErr();
  const denom = 10n ** BigInt(fp.length);
  const numer = BigInt((ip || "0") + fp);
  return mkRat(numer, denom);
}
const peek = st => st.arr[st.pos];
const next = st => { st.pos++; };
function parseExpr(st, ctx) {
  let left = parseTerm(st, ctx);
  for (;;) {
    const t = peek(st);
    if (t && t.k === "op" && (t.v === "+" || t.v === "−")) { next(st); const right = parseTerm(st, ctx); left = t.v === "+" ? vAdd(left, right) : vSub(left, right); }
    else break;
  }
  return left;
}
function parseTerm(st, ctx) {
  let left = parseComb(st, ctx);
  for (;;) {
    const t = peek(st);
    if (t && t.k === "op" && (t.v === "×" || t.v === "÷")) { next(st); const right = parseComb(st, ctx); left = t.v === "×" ? vMul(left, right) : vDiv(left, right); }
    else break;
  }
  return left;
}
/* nCr / nPr (Build 4). Only 5C2 and 5P2 on their own were measured. They
   bind tighter than × and ÷ (2×5C2 = 2×10 = 20) and looser than implicit ×
   and the minus sign: a Blipwork choice, so `0,5^3×10C3` reads the way a
   learner means it. */
function parseComb(st, ctx) {
  let left = parseUnary(st, ctx);
  for (;;) {
    const t = peek(st);
    if (t && t.k === "comb") { next(st); const right = parseUnary(st, ctx); left = vComb(left, right, t.v); }
    else break;
  }
  return left;
}
function parseUnary(st, ctx) {
  const t = peek(st);
  if (t && t.k === "op" && t.v === "−") { next(st); return vNeg(parseUnary(st, ctx)); }
  return parseImplicit(st, ctx);
}
/* Implicit multiplication — device-verified: adjacency of a completed atom
   (number / closing-paren group / postfix ²³ / template / Ans — i.e. exactly
   what parsePower always returns) followed directly by another atom-opener
   (a function-open, "(", a template, or Ans — with NO explicit × ÷ between
   them) means MULTIPLY. It binds TIGHTER than explicit × ÷ (nested one level
   below parseTerm's ×÷ loop, same as the real device auto-bracketing
   "6÷2(1+2)" into "6÷(2(1+2))" = 1) but looser than postfix/power, which
   parsePower has already applied by the time we see it here.
   THIS is also the fix for the silent-wrong-answer bug: before this level
   existed, an atom directly followed by another atom (e.g. "19sin(77)" typed
   with no × key) had nothing that would ever consume the second atom — every
   caller of parseExpr/parseTerm only continues on an explicit + − × ÷, so the
   second atom was simply never parsed, its tokens quietly left unconsumed.
   Combined with FIX 2 below (every sub-parse now asserts full consumption),
   a token that isn't understood as +, ×, or (now) implicit-× can no longer
   vanish — it forces a Syntax ERROR instead of a silently wrong number. */
/* Build 1 (spec §2): a variable letter is an implicit-× trigger too, so
   `2A²` with A = 5 gives 50 (the ² binds to A inside parsePower first,
   then the 2 multiplies) and `AB` is A×B. */
/* Build 3: π multiplies implicitly the same way (2π, Aπ, sin(30)π). Like a
   letter, π followed directly by a NUMBER (π2) is not a product: Syntax
   ERROR, as (2+3)4 is on the device (π2 itself was not probed). */
/* Build 4: the constant e multiplies implicitly like π (spec §9), and so do
   the new templates (log□(), |□|, 10^□, e^□, a mixed number): 2e, 3|−2|. */
/* Build 8: a pasted STAT value (x̄, σx, A ...) multiplies the same way (2x̄);
   x̂ and ŷ do not, they act on what is before them (parsePower). */
const IMPLICIT_TRIGGER = t => t && (t.k === "func" || t.k === "(" || t.k === "frac" || t.k === "rad" || t.k === "xrt" || t.k === "ans" || t.k === "var" || t.k === "pi"
  || t.k === "econst" || t.k === "logb" || t.k === "abs" || t.k === "tenpow" || t.k === "epow" || t.k === "mixed" || isStatAtom(t));
const PI_VAL = mkPi(1n, 1n);
function parseImplicit(st, ctx) {
  let left = parsePower(st, ctx);
  for (;;) {
    if (IMPLICIT_TRIGGER(peek(st))) { const right = parsePower(st, ctx); left = vMul(left, right); }
    else break;
  }
  return left;
}
function parsePower(st, ctx) {
  let base = parseAtom(st, ctx);
  for (;;) {
    const t = peek(st);
    if (t && t.k === "sq") { next(st); base = vPowInt(base, 2); }
    else if (t && t.k === "cb") { next(st); base = vPowInt(base, 3); }
    else if (t && t.k === "pow") { next(st); const e = parseSubExpr(t.exp, ctx); base = vPow(base, e); }
    else if (t && t.k === "inv") { next(st); base = vInv(base); }          // x⁻¹ (Build 4)
    else if (t && t.k === "fact") { next(st); base = vFact(base); }        // x!
    else if (t && t.k === "pct") { next(st); base = vDiv(base, HUNDRED); } // %: ÷100 (20% = 1/5)
    else if (t && t.k === "stat" && REG_POSTFIX.has(t.v)) { next(st); base = ctx.statPost ? ctx.statPost(t.v, base) : VERR("Math ERROR"); }   // 5ŷ (Build 8)
    else break;
  }
  return base;
}
function parseAtom(st, ctx) {
  const t = peek(st);
  if (!t) throw synErr(st);
  if (t.k === "num") { let v; try { v = numToValue(t.v); } catch { throw synErr(st, t.src + badCommaAt(t.v)); } next(st); return t.e10 != null ? vMul(v, pow10(t.e10)) : v; }
  if (t.k === "dmsv") {   // 30°15'20" = 30 + 15/60 + 20/3600 (Build 4)
    let v = mkRat(0n, 1n);
    for (const [k, p] of t.parts.entries()) {
      let pv; try { pv = numToValue(p); } catch { throw synErr(st, t.src); }
      v = vAdd(v, vDiv(pv, mkRat([1n, 60n, 3600n][k], 1n)));
    }
    next(st); return v;
  }
  if (t.k === "econst") { next(st); return E_VAL; }
  if (t.k === "logb") { next(st); const b = parseSubExpr(t.base, ctx); const x = parseSubExpr(t.body, ctx); return vLogBase(b, x); }
  if (t.k === "abs") { next(st); return vAbs(parseSubExpr(t.body, ctx)); }
  if (t.k === "tenpow") { next(st); return vPow(TEN, parseSubExpr(t.exp, ctx)); }
  if (t.k === "epow") { next(st); return vExp(parseSubExpr(t.exp, ctx)); }
  /* 1¾ = 1 + ¾ (spec §8). A negative whole box was not measured: Blipwork
     adds the parts as typed, (−1)¾ = −¼; −1¾ is typed as − then 1¾. */
  if (t.k === "mixed") { next(st); const w = parseSubExpr(t.whole, ctx); const n = parseSubExpr(t.num, ctx); const d = parseSubExpr(t.den, ctx); return vAdd(w, vDiv(n, d)); }
  if (t.k === "(") { next(st); const v = parseExpr(st, ctx); closeBracket(st); return v; }
  /* GCD( and LCM( (Build 10, spec §19.1): EXACTLY two arguments split by
     ";" (SHIFT )), so GCD(12;18;24 is Syntax ERROR at the second ";". The
     ")" closes itself at the end of a box like every bracket (GCD(12;18 =
     6). Not measured, Blipwork reading: one argument only (GCD(12) is
     Syntax ERROR too, and a ";" anywhere else is a token nothing reads, so
     Syntax ERROR (2;3). */
  if (t.k === "func" && (t.name === "GCD" || t.name === "LCM")) {
    next(st);
    const a = parseExpr(st, ctx);
    const s = peek(st);
    if (!s || s.k !== "sep") throw synErr(st);
    next(st);
    const b = parseExpr(st, ctx);
    closeBracket(st);
    return vGcdLcm(t.name, a, b);
  }
  if (t.k === "func") { next(st); const inner = parseExpr(st, ctx); closeBracket(st); return applyFunc(t.name, t.inv, inner, ctx.drg); }
  if (t.k === "ans") { next(st); return ctx.ans; }
  if (t.k === "var") { next(st); return (ctx.vars && ctx.vars[t.name]) || mkRat(0n, 1n); }   // A–F, X, Y, M (spec §2: all start at 0)
  if (t.k === "pi") { next(st); return PI_VAL; }   // the constant π (SHIFT ×10^x, Build 3)
  /* a pasted STAT value (Build 8): worked out from the data at the moment
     = is pressed; a line evaluated with no STAT data hook gives Math ERROR */
  if (isStatAtom(t)) { next(st); return ctx.stat ? ctx.stat(t.v) : VERR("Math ERROR"); }
  if (t.k === "frac") { next(st); const num = parseSubExpr(t.num, ctx); const den = parseSubExpr(t.den, ctx); return vDiv(num, den); }
  if (t.k === "rad") { next(st); const body = parseSubExpr(t.body, ctx); return t.deg === 3 ? vCbrt(body) : vSqrt(body); }
  if (t.k === "xrt") { next(st); const idx = parseSubExpr(t.idx, ctx); const body = parseSubExpr(t.body, ctx); return vXroot(idx, body); }
  throw synErr(st);
}
/* Build 2 (spec §4, "very important"): a missing ")" at the END of a box
   counts as closed, because the device closes every open bracket: sin(30 = ½,
   (2+3 = 5, and sin(30+1 = sin(31), the open bracket swallowing the rest.
   "The end of a box" is the end of the line or of a template box (a
   fraction's top, a root's body, an exponent). Anything else where the ")"
   should be is still a Syntax ERROR, and so are 2+3) and (2+3)4. */
function closeBracket(st) {
  const c = peek(st);
  if (!c) return;
  if (c.k !== ")") throw synErr(st);
  next(st);
}
/* FIX 2 (audit result below) — parse a BOUNDED token box (a frac num/den, a
   rad body, a pow exp, or the whole top-level entry line) and require that
   parseExpr consumed every token assigned to it. Before this fix, the three
   template sub-parses (frac num/den, rad body, pow exp) called parseExpr
   directly and threw away its own leftover-token check — only the top-level
   evalBox had one. That gap is exactly how "19sin(77)" in a numerator lost
   its sin(77) factor: parseExpr correctly stopped once no + − × operator
   followed the "19", the frac/rad/pow callers never checked whether
   anything was left over in that sub-box, so the unconsumed sin(77) tokens
   were discarded with no error at all. Every caller below now goes through
   this one function, so a leftover/un-understood token ALWAYS surfaces as
   Syntax ERROR instead of silently vanishing. */
function parseSubExpr(box, ctx) {
  const st = { arr: compileBox(box), pos: 0, box };
  const v = parseExpr(st, ctx);
  if (st.pos !== st.arr.length) throw synErr(st);
  return v;
}
/* A Syntax ERROR value carries `at` = { box, i }: the cursor position just
   BEFORE the token that caused it (Build 2, spec §3 Goto). */
function evalBox(box, ctx) {
  try { return parseSubExpr(box, ctx); }
  catch (e) { const r = VERR("Syntax ERROR"); r.at = (e && e.at) || null; return r; }
}

/* ---- Build 1: variables and history helpers ---- */
const VAR_NAMES = ["A", "B", "C", "D", "E", "F", "X", "Y", "M"];
const freshVars = () => Object.fromEntries(VAR_NAMES.map(n => [n, mkRat(0n, 1n)]));
const isZeroAny = v => !isErr(v) && toFloatV(v) === 0;
/* The red ALPHA letter on each key face (spec §2, read off the device). The
   same keys pick the variable after STO and RCL, where no ALPHA is needed. */
const LETTER_OF = { neg: "A", dms: "B", hyp: "C", sin: "D", cos: "E", tan: "F", rparen: "X", sd: "Y", mplus: "M" };
/* ALPHA CALC types "=" and ALPHA ∫ types ":" as plain tokens. SOLVE (Build
   5) reads the "=" as the two sides of an equation. Pressing the = KEY on a
   line that holds "=" or ":" is still a Syntax ERROR: the spec does not
   measure that case, so Build 1's behaviour is kept. */
const ALPHA_TOKEN = { calc: "eqs", intdx: "colon", exp10: "econst",   // Build 4: ALPHA ×10^x = the constant e (spec §2, §9)
  mult: "gcd", div: "lcm" };   // Build 10 (spec §19.1): ALPHA × = GCD(, ALPHA ÷ = LCM(
/* The device's history limit is by bytes and was not measured; a few dozen
   entries is plenty for a learner, and keeps the memory bounded. */
const MAX_HISTORY = 30;
/* Deep copy of an entry box, re-linking every template sub-box to its new
   parent (same __parent/__owner/__pkey linkage insertTemplate sets up), so a
   history entry can be shown and edited without the edit touching history. */
const SUB_KEYS = ["num", "den", "body", "exp", "idx", "base", "whole"];   // every template sub-box key (idx = the ˣ√ index, Build 2; base = log□'s base, whole = a mixed number's whole part, Build 4)
function cloneBox(box) {
  const out = [];
  for (const t of box) {
    const c = { ...t };
    for (const key of SUB_KEYS) {
      if (Array.isArray(t[key])) { const sub = cloneBox(t[key]); sub.__parent = out; sub.__owner = c; sub.__pkey = key; c[key] = sub; }
    }
    out.push(c);
  }
  return out;
}
/* ---- Build 2: what ▫/▫ (and ˣ√) "grab" (spec §8) ----
   ▫/▫ typed after an operand takes that operand as its numerator; ˣ√ takes
   it as its index. This finds where the ONE operand just left of `end`
   starts: a number (only the last number of 2+3), a letter, Ans or π, a
   finished fraction or root, a whole bracket or function group ((2+3),
   sin(30)), and any of these carrying its ², ³ or x^ exponent (2²).
   Returns `end` when there is no operand (start of the box, or right after
   an operator or an open bracket): the template then goes in empty. */
function operandStart(box, end) {
  if (end <= 0) return end;
  const t = box[end - 1];
  if (t.k === "d" || t.k === "c") { let j = end - 1; while (j > 0 && (box[j - 1].k === "d" || box[j - 1].k === "c")) j--; return j; }
  if (t.k === "var" || t.k === "ans" || t.k === "pi" || t.k === "frac" || t.k === "rad" || t.k === "xrt"
    || t.k === "econst" || t.k === "logb" || t.k === "abs" || t.k === "tenpow" || t.k === "epow" || t.k === "mixed" || isStatAtom(t)) return end - 1;   // Build 4 operands; Build 8 a STAT value
  if (t.k === "sq" || t.k === "cb" || t.k === "pow" || t.k === "inv" || t.k === "fact" || t.k === "pct" || (t.k === "stat" && REG_POSTFIX.has(t.v))) { const j = operandStart(box, end - 1); return j === end - 1 ? end : j; }
  if (t.k === ")") {
    let depth = 0;
    for (let j = end - 1; j >= 0; j--) {
      const k = box[j].k;
      if (k === ")") depth++;
      else if ((k === "(" || k === "func") && --depth === 0) return j;
    }
  }
  return end;
}

export function mountCalculator(host, opts = {}) {
  // Optional milestone signal — lets the quest engine see when a learner
  // actually performs a step (cleared, freq on, entered stat mode, captured
  // data, computed a value). Fire-and-forget; never throws into the calc.
  const emit = (t, p) => { try { opts.onEvent && opts.onEvent(t, p); } catch { /* ignore */ } };

  const S = {
    shift: false, mode: "COMP", screen: "comp", freqOn: false,
    result: null,
    data: [], cell: "", row: 0, col: 0, menu: null,
    // ---- COMP-mode maths engine state (round 2) ----
    box: [], cur: null, exactVal: null, showDecimal: false, drg: "D", ansVal: mkRat(0n, 1n),
    // ---- calculator rebuild Build 1 (spec §1, §2) ----
    alpha: false,          // ALPHA lit (one-shot, boxed A in the status line)
    memPending: null,      // "sto" | "rcl": STO/RCL shown in the status line, waiting for a letter key
    vars: freshVars(),     // A–F, X, Y, M — Value objects, all 0 at the start
    history: [],           // [{ box, val, showDecimal }], newest last, MAX_HISTORY entries at most
    histPos: 0,            // index of the history entry on screen; history.length = "below the newest"
    browsing: false,       // true while ▲/▼ show a history entry (indicator then ▲ / ▼ / ▲▼)
    afterAC: false,        // the line is empty because of AC: ◀/▶ recall the last expression
    err: false,            // the result line holds an error message
    // ---- calculator rebuild Build 2 (spec §3) ----
    errAt: null,           // { box, i }: where ◀/▶ (Goto) put the cursor after a Syntax ERROR
    // ---- calculator rebuild Build 4 (spec §7, §8, §9, §16) ----
    fix: null,             // SETUP Fix: 0–9 decimals, or null = Norm (the FIX tag shows while it is set)
    norm: 2,               // SETUP Norm 1 or 2; factory Norm 2. Norm 1 is accepted and shows like Norm 2 (not measured)
    form: null,            // how the result is shown: null (exact / decimal, see showDecimal), "mixed" (1¾) or "dms" (30°15'0")
    // ---- calculator rebuild Build 5 (spec §10, §11) ----
    prompt: null,          // the open prompt screen (screen "prompt"): { label, value, box, onAccept, onCancel, err, errAt }
    calcRun: null,         // { letters }: the result on screen came from CALC, so = (or CALC) asks again from the first letter
    solve: null,           // the SOLVE answer screen (screen "solved"): { x, lr }
    // ---- calculator rebuild Build 6 (spec §12) ----
    tbl: null,             // TABLE mode (screens "tblF", "table", "tblErr"): { f, g, which, rows, hasG, r, c, top, back, err }
    tblRange: freshRange(),   // Start / End / Step: remembered from one table to the next (spec §12)
    // ---- calculator rebuild Build 7 (spec §13, §14) ----
    eqn: null,             // EQN / INEQ (screens "eqnGrid", "eqnAns", "eqnErr"): { kind, type, rows, cols, coef, r, c, left, box, answers, ai, dec, back, err, sign }
    // ---- calculator rebuild Build 8 (spec §15, §16) ----
    /* mode "REG" = STAT type A+BX (MODE 3 2). It is kept apart from "STAT"
       (1-VAR), and its X | Y pairs apart from S.data, on purpose: the calcdo
       questions read state().mode === "STAT" and state().data for their
       1-VAR goals, so a two-variable entry must never count as the 1-VAR one
       they ask for. The status line shows STAT for both. */
    pairs: [],             // A+BX data: [{ x, y }]
    held: null,            // a STAT value was pasted after a result: that previous answer (HTML) stays bottom right until = (spec §15)
    tblType: "fg",         // SETUP 5:TABLE: "fg" = f(x),g(x) (factory) or "f" = f(x) only
    // ---- calculator rebuild Build 9 (spec §19.2, §19.3) ----
    gridTop: 0,            // the STAT data editor shows three rows: the first one on show (index)
    statBack: false,       // the open menu was opened FROM the data editor, so AC / a choice goes back there
  };
  S.cur = { box: S.box, i: 0 };

  // Optional pre-load: start a read-off task with the data already captured
  // in 1-VAR STAT mode (so the learner focuses on the read-off sequence).
  if (opts.setup) {
    const su = opts.setup;
    /* setup.data takes either plain numbers (frequency 1 each, the original
       form — every existing quest still passes this) or {x, f} pairs, so a
       question can start with a FREQUENCY TABLE already captured instead of a
       flat list. Added 2026-08-28 for the grouped-data round, where retyping
       the same table before every read-off would be all tedium and no skill. */
    if (su.data && su.data.length) {
      S.mode = "STAT"; S.freqOn = !!su.freq;
      S.data = su.data.map(d => (d && typeof d === "object")
        ? { x: Number(d.x), f: Number(d.f ?? 1) }
        : { x: d, f: 1 });
      S.screen = "comp";
    }
    else if (su.statMode) { S.mode = "STAT"; S.screen = "comp"; }
  }

  // ---- scaffold ----
  const wrap = el("div", "calc");
  const lcd = el("div", "calc-lcd");
  const ind = el("div", "calc-ind");
  const main = el("div", "calc-main");
  lcd.appendChild(ind); lcd.appendChild(main);
  wrap.appendChild(lcd);
  const buildKey = k => {
    const html = `${k.shift ? `<span class="ksh">${escapeHtml(k.shift)}</span>` : ""}`
      + `${k.red ? `<span class="kred">${escapeHtml(k.red)}</span>` : ""}`
      + `<span class="kmain">${escapeHtml(k.label)}</span>`;
    const b = el("button", "calc-key " + (k.cls || ""), html);
    b.dataset.keyid = k.id;
    b.style.gridColumn = String(k.col);
    b.style.gridRow = String(k.row);
    if (k.dead) b.dataset.dead = "1";      // visual-only: no click handler (round 2 wires it up)
    else b.addEventListener("click", () => press(k.id));
    return b;
  };
  const buildDpad = () => {
    const holder = el("div", "calc-dpad");
    holder.style.gridColumn = `${DPAD_POS.col} / span ${DPAD_POS.colSpan}`;
    holder.style.gridRow = `${DPAD_POS.row} / span ${DPAD_POS.rowSpan}`;
    const ring = el("div", "calc-dpad-ring");
    DPAD_KEYS.forEach(k => {
      const b = el("button", `calc-dpad-btn k-${k.id}`, k.label);
      b.dataset.keyid = k.id;
      b.addEventListener("click", () => press(k.id));
      ring.appendChild(b);
    });
    holder.appendChild(ring);
    return holder;
  };

  const pad = el("div", "calc-pad");
  const fngrid = el("div", "calc-fngrid");
  FUNC_KEYS.forEach(k => fngrid.appendChild(buildKey(k)));
  fngrid.appendChild(buildDpad());
  pad.appendChild(fngrid);
  const numgrid = el("div", "calc-numgrid");
  NUM_KEYS.forEach(k => numgrid.appendChild(buildKey(k)));
  pad.appendChild(numgrid);
  wrap.appendChild(pad);
  host.appendChild(wrap);

  // ---- stats ----
  function expanded() {
    const a = [];
    S.data.forEach(d => { const f = S.freqOn ? (d.f ?? 1) : 1; for (let i = 0; i < (f || 0); i++) a.push(d.x); });
    return a;
  }
  function statValue(tok) {
    const a = expanded(); if (!a.length) return null;
    const s = sortAsc(a), n = a.length, m = mean(a);
    switch (tok) {
      case "n": return n;
      case "x̄": return m;
      case "σx": return stdDev(a);
      case "sx": return n > 1 ? Math.sqrt(a.reduce((q, x) => q + (x - m) ** 2, 0) / (n - 1)) : 0;
      case "minX": return s[0];
      case "maxX": return s[n - 1];
      case "Q1": return quartilesExclusive(s).q1;
      case "med": return quartilesExclusive(s).med;
      case "Q3": return quartilesExclusive(s).q3;
      case "Σx": return a.reduce((q, x) => q + x, 0);
      case "Σx²": return a.reduce((q, x) => q + x * x, 0);
    }
    return null;
  }
  /* Build 9 (spec §19.2 "A+BX with FREQ on"): the A+BX pairs, each with the
     number of times it counts. With FREQ on that is its FREQ, read exactly
     the way expanded() reads a 1-VAR FREQ (a row counts as often as
     `for (i = 0; i < f; i++)` runs, so 0 or less drops it); with FREQ off,
     once. The weighting itself is not device-measured. */
  const reps = f => (f > 0 ? Math.ceil(f) : 0);
  const regRows = () => S.pairs.map(p => ({ x: p.x, y: p.y, w: S.freqOn ? reps(p.f ?? 1) : 1 }));
  /* Build 9 (spec §19.3): the two-variable Sum / Var / MinMax read-offs on
     A+BX, as decimals like 1-VAR's (the same formulas as statValue, with each
     pair counted w times; sx and sy are 0 for one value, as 1-VAR's sx is).
     null (Math ERROR) when no pair counts. Device check values, X 1,2,3,4 /
     Y 2,4,5,8: maxY = 8, σy = 2,165063509. */
  function regValue(tok) {
    const rows = regRows().filter(p => p.w > 0);
    if (!rows.length) return null;
    const sum = f => rows.reduce((q, p) => q + p.w * f(p), 0);
    const n = sum(() => 1), mx = sum(p => p.x) / n, my = sum(p => p.y) / n;
    const ssx = sum(p => (p.x - mx) ** 2), ssy = sum(p => (p.y - my) ** 2);
    const xs = rows.map(p => p.x), ys = rows.map(p => p.y);
    switch (tok) {
      case "n": return n;
      case "x̄": return mx;
      case "σx": return Math.sqrt(ssx / n);
      case "sx": return n > 1 ? Math.sqrt(ssx / (n - 1)) : 0;
      case YBAR: return my;
      case "σy": return Math.sqrt(ssy / n);
      case "sy": return n > 1 ? Math.sqrt(ssy / (n - 1)) : 0;
      case "Σx²": return sum(p => p.x * p.x);
      case "Σx": return sum(p => p.x);
      case "Σy²": return sum(p => p.y * p.y);
      case "Σy": return sum(p => p.y);
      case "Σxy": return sum(p => p.x * p.y);
      case "Σx³": return sum(p => p.x ** 3);
      case "Σx²y": return sum(p => p.x * p.x * p.y);
      case "Σx⁴": return sum(p => p.x ** 4);
      case "minX": return Math.min(...xs);
      case "maxX": return Math.max(...xs);
      case "minY": return Math.min(...ys);
      case "maxY": return Math.max(...ys);
    }
    return null;
  }
  /* Build 8: what a pasted STAT token is worth when = is pressed. The 1-VAR
     values are exactly statValue's numbers (unchanged); A, B and r come from
     regFit. All are DECIMALS (spec §15: "A = 0, B = 1,9, r = 0,981155781
     (decimals)"), so they show by the normal decimal rules and S⇔D has no
     fraction to switch to. No data: Math ERROR, as before.
     Build 9: in A+BX every other token is a two-variable read-off (regValue),
     and A, B, r, x̂, ŷ count each pair by its FREQ (regRows). */
  const REG_TOKS = new Set(["A", "B", "r"]);
  function statTok(name) {
    if (REG_TOKS.has(name)) {
      const fit = regFit(regRows()), v = fit && (name === "A" ? fit.A : name === "B" ? fit.B : fit.r);
      if (v == null || (typeof v === "object" && isErr(v))) return VERR("Math ERROR");
      return VFLOAT(typeof v === "number" ? v : toFloatV(v));
    }
    const v = S.mode === "REG" ? regValue(name) : statValue(name);
    return v == null ? VERR("Math ERROR") : VFLOAT(v);
  }
  /* ŷ = A + B·x and x̂ = (y − A) ÷ B, exact on an exact operand, then shown
     as a decimal like the other read-offs (spec §15: 5ŷ = 9,5) */
  function statPost(name, x) {
    if (isErr(x)) return x;
    const fit = regFit(regRows());
    if (!fit) return VERR("Math ERROR");
    const out = name === "ŷ" ? vAdd(fit.A, vMul(fit.B, x)) : vDiv(vSub(x, fit.A), fit.B);
    return isErr(out) ? out : VFLOAT(toFloatV(out));
  }
  const evalCtx = () => ({ ans: S.ansVal, drg: S.drg, vars: S.vars, stat: statTok, statPost });

  // ---- menus ----
  /* Build 6: a menu opened from a TABLE screen goes back to that screen
     (the f(X)= line or the table itself), not to a COMP line TABLE mode does
     not have. In COMP and STAT mode home() is "comp", exactly as before. */
  /* Build 7: the same for EQN and INEQ: back to the grid or the answer on
     screen. */
  /* Build 9 (spec §19.2): and a menu opened from the STAT data editor (MODE,
     SETUP, CLR, the short SHIFT 1 menu) goes back to the editor. */
  const eqnMode = () => (S.mode === "EQN" || S.mode === "INEQ") && !!S.eqn;
  const home = () => (S.mode === "TABLE" && S.tbl ? S.tbl.back || "tblF" : eqnMode() ? S.eqn.back || "eqnGrid" : statMode() && S.statBack ? "statInput" : "comp");
  const openMenu = m => {
    if (S.screen !== "menu") { if (S.mode === "TABLE" && S.tbl) S.tbl.back = S.screen; if (eqnMode()) S.eqn.back = S.screen; S.statBack = S.screen === "statInput"; }
    S.menu = m; S.screen = "menu";
  };
  const closeMenu = () => { if (S.menu && S.menu.parent) S.menu = S.menu.parent; else { const ret = S.menu && S.menu.ret; S.screen = !ret || ret === "comp" ? home() : ret; S.menu = null; } };
  const leaveMenu = () => { S.menu = null; S.screen = home(); };

  /* Build 7 (spec §16): MODE is two pages, two columns, digits in reversed
     boxes: page 1 `1:COMP 2:CMPLX / 3:STAT 4:BASE-N / 5:EQN 6:MATRIX /
     7:TABLE 8:VECTOR` with ▼, page 2 `1:DIST 2:INEQ / 3:RATIO` with ▲.
     The items Blipwork does not build (CMPLX, BASE-N, MATRIX, VECTOR, DIST,
     RATIO: her ruling, not school use) do nothing when picked. */
  function modeMenu() {
    const p1 = [["1", "COMP"], ["2", "CMPLX"], ["3", "STAT"], ["4", "BASE-N"], ["5", "EQN"], ["6", "MATRIX"], ["7", "TABLE"], ["8", "VECTOR"]];
    const p2 = [["1", "DIST"], ["2", "INEQ"], ["3", "RATIO"]];
    openMenu({ items: p1, page: 0, pages: 2, boxed: true, upMark: true, ret: "comp",
      onDown() { if (this.page === 0) { this.page = 1; this.items = p2; } },
      onUp() { if (this.page === 1) { this.page = 0; this.items = p1; } },
      onNum(n) {
        if (this.page === 1) { if (n === 2) ineqTypeMenu(); return; }
        if (n === 1) { S.mode = "COMP"; resetEntry(); S.menu = null; S.screen = "comp"; } else if (n === 3) statTypeMenu(); else if (n === 5) eqnTypeMenu(); else if (n === 7) startTable();
      } });
  }
  /* Build 7 (spec §14): INEQ asks the type, then the sign. Only the
     quadratic is built: the cubic item does nothing (its answers were not
     measured). The sign lines are written out in full (spec shorthand
     `1:aX²+bX+c>0 / 2:<0 / 3:≥0 / 4:≤0`, read as four full lines). */
  function ineqTypeMenu() {
    openMenu({ items: [["1", "aX²+bX+c"], ["2", "aX³+bX²+cX+d"]], list: true, ret: "comp",
      onNum(n) { if (n === 1) ineqSignMenu(); } });
  }
  function ineqSignMenu() {
    const signs = [">", "<", "≥", "≤"];
    openMenu({ items: signs.map((s, k) => [String(k + 1), `aX²+bX+c${escapeHtml(s)}0`]), list: true, ret: "comp",
      onNum(n) { if (n >= 1 && n <= 4) startEqn("ineq", signs[n - 1]); } });
  }
  /* Build 7 (spec §13): MODE 5 lists the four types as four plain lines */
  function eqnTypeMenu() {
    openMenu({ items: [["1", "anX+bnY=cn"], ["2", "anX+bnY+cnZ=dn"], ["3", "aX²+bX+c=0"], ["4", "aX³+bX²+cX+d=0"]], list: true, ret: "comp",
      onNum(n) { if (n >= 1 && n <= 4) startEqn(n); } });
  }
  /* Build 8 (spec §15): two columns `1:1-VAR 2:A+BX / 3:_+CX² 4:ln X /
     5:e^X 6:A·B^X / 7:A·X^B 8:1/X`, rows packed so the LCD keeps its plain
     height. 2 opens A+BX; 3 to 8 were not measured and are not school use:
     they do nothing. */
  function statTypeMenu() {
    openMenu({ items: [["1", "1-VAR"], ["2", "A+BX"], ["3", "_+CX²"], ["4", "ln X"], ["5", "e^X"], ["6", "A·B^X"], ["7", "A·X^B"], ["8", "1/X"]], packed: true, ret: "comp",
      onNum(n) { if (n === 1) startStat(); else if (n === 2) startReg(); } });
  }
  /* Build 7: coming from TABLE or EQN, the cursor still points into the
     f(X)= line or the coefficient being typed; it is put back on the
     (empty) calculation line, or the COMP line under STAT would type into a
     box that is not on screen. From COMP nothing changes. */
  /* Build 8: picking a STAT type clears ALL the STAT data, both kinds (one
     data area, as on the device). */
  function startStat() {
    if (S.mode === "TABLE" || S.mode === "EQN" || S.mode === "INEQ") resetEntry();
    S.mode = "STAT"; S.data = []; S.pairs = []; S.cell = ""; S.row = 0; S.col = 0; S.menu = null; S.screen = "statInput"; emit("statMode");
  }
  /* A+BX (spec §15): the X | Y grid. No "statMode" milestone: the calcdo
     questions that listen for it ask for 1-VAR. */
  function startReg() {
    if (S.mode === "TABLE" || S.mode === "EQN" || S.mode === "INEQ") resetEntry();
    S.mode = "REG"; S.data = []; S.pairs = []; S.cell = ""; S.row = 0; S.col = 0; S.menu = null; S.screen = "statInput";
  }
  const statMode = () => S.mode === "STAT" || S.mode === "REG";

  /* Build 8 (spec §16): two pages in the MODE menu's look (two columns,
     digits in reversed boxes, rows packed so the LCD keeps its plain height):
     page 1 `1:MthIO 2:LineIO / 3:Deg 4:Rad / 5:Gra 6:Fix / 7:Sci 8:Norm`
     with ▼, page 2 `1:ab/c 2:d/c / 3:CMPLX 4:STAT / 5:TABLE 6:APO /
     7:◀CONT▶`. Working: Deg, Rad, Fix, Norm, 4:STAT (the FREQ switch) and
     5:TABLE; everything else does nothing when picked. Page 2 shows no ▲:
     the spec gives MODE's page 2 a ▲ but says nothing for SETUP's, so it is
     left as it was. */
  function setupMenu() {
    const p1 = [["1", "MthIO"], ["2", "LineIO"], ["3", "Deg"], ["4", "Rad"], ["5", "Gra"], ["6", "Fix"], ["7", "Sci"], ["8", "Norm"]];   // 8:Norm added in Build 4 (spec §16)
    const p2 = [["1", "ab/c"], ["2", "d/c"], ["3", "CMPLX"], ["4", "STAT"], ["5", "TABLE"], ["6", "APO"], ["7", "◀CONT▶"]];
    openMenu({ items: p1, page: 0, pages: 2, boxed: true, ret: "comp",
      onDown() { if (this.page === 0) { this.page = 1; this.items = p2; } },
      onUp() { if (this.page === 1) { this.page = 0; this.items = p1; } },
      onNum(n) {
        if (this.page === 0 && n === 3) { S.drg = "D"; leaveMenu(); }
        else if (this.page === 0 && n === 4) { S.drg = "R"; leaveMenu(); }
        else if (this.page === 0 && n === 6) fixPrompt();
        else if (this.page === 0 && n === 8) normPrompt();
        else if (this.page === 1 && n === 4) freqMenu();
        else if (this.page === 1 && n === 5) tableTypeMenu();
      } });
  }
  /* SETUP ▼ 5:TABLE (spec §16): `Select Type?` / `1:f(x)` / `2:f(x),g(x)`.
     1 makes TABLE ask for f only. The current choice is not shown; AC
     cancels without changing (back to the calculation, like Fix 0~9?). */
  function tableTypeMenu() {
    openMenu({ title: "Select Type?", items: [["1", "f(x)"], ["2", "f(x),g(x)"]], list: true, ret: "comp",
      onNum(n) { if (n !== 1 && n !== 2) return; S.tblType = n === 1 ? "f" : "fg"; leaveMenu(); } });
  }
  /* Build 4 (spec §7, §16): SETUP 6 asks `Fix 0~9?` and a digit sets it (the
     FIX tag lights); SETUP 8 asks `Norm 1~2?` and 1 or 2 leaves Fix. Neither
     prompt shows the current choice; AC cancels without changing anything
     (no parent menu, so AC goes straight back to the calculation, as the
     Frequency? prompt already did). A result on screen is redrawn at once. */
  function fixPrompt() {
    openMenu({ title: "Fix 0~9?", items: [], ret: "comp",
      onNum(n) { S.fix = n; leaveMenu(); refreshResult(); } });
  }
  function normPrompt() {
    openMenu({ title: "Norm 1~2?", items: [], ret: "comp",
      onNum(n) { if (n !== 1 && n !== 2) return; S.fix = null; S.norm = n; leaveMenu(); refreshResult(); } });
  }
  function freqMenu() {
    openMenu({ title: "Frequency?", items: [["1", "ON"], ["2", "OFF"]], ret: "comp",
      onNum(n) { if (n !== 1 && n !== 2) return; S.freqOn = (n === 1); leaveMenu(); emit("freq", n === 1); } });
  }
  /* Build 8 (spec §16): SHIFT 9 shows the title `Clear?` over `1:Setup
     2:Memory / 3:All`. 3 → `Reset All?` / `[=] :Yes` / `[AC] :Cancel`; = does
     the reset and shows `Reset All` / `Press [AC] key`, centred; AC then goes
     back to COMP. 1 and 2 have the same two steps with their own words
     (Build 8 copied All's shape for them; Build 9 and the third probe below
     replaced those guesses with the measured words). AC on a Reset …? screen cancels without
     changing anything. On the last screen only AC (or ON) does anything.
     Build 9 (spec §19.2, measured from the STAT data editor): 2 is `Clear
     Memory?` / `[=] :Yes` / `[AC] :Cancel`, then `Complete!` / `Press [AC]
     key`. These replace Build 8's copied guess (Reset Memory? / Reset
     Memory) wherever CLR is opened: it is one CLR.
     Third probe (spec §19.8, measured): 1 is `Clear Setup?`, then
     `Complete!` / `Press [AC] key`, and every last screen writes "key" in
     lower case, All's too (`Reset All` / `Press [AC] key`).
     Opened from the data editor, AC on the last screen goes back to the
     editor, cursor on row 1 (spec §19.2, measured for Memory; Setup does the
     same, not device-measured); All leaves STAT, so it goes to COMP. */
  const CLR_WORDS = { 1: "Setup", 2: "Memory", 3: "All" };
  const CLR_SCREENS = {
    1: { ask: "Clear Setup?", done: ["Complete!", "Press [AC] key"] },
    2: { ask: "Clear Memory?", done: ["Complete!", "Press [AC] key"] },
    3: { ask: "Reset All?", done: ["Reset All", "Press [AC] key"] },
  };
  function clrMenu() {
    openMenu({ title: "Clear?", items: [["1", "Setup"], ["2", "Memory"], ["3", "All"]], ret: "comp",
      onNum(n) { if (CLR_WORDS[n]) clrConfirm(n); } });
  }
  function clrConfirm(n) {
    const w = CLR_SCREENS[n];
    openMenu({ title: w.ask, items: [], notes: ["[=] :Yes", "[AC] :Cancel"], ret: "comp",
      onEq() {
        clrReset(n);
        if (S.statBack && statMode()) { S.row = 0; S.col = 0; S.cell = ""; S.gridTop = 0; }   // Build 9: back to the editor's row 1
        S.menu = { done: w.done, items: [], ret: "comp" }; S.screen = "menu";
      } });
  }
  /* What each reset puts back (factory settings, spec intro: Norm 2, Deg,
     TABLE asks f(X) and g(X), STAT FREQ off):
     1 Setup (Build 4): Fix → Norm 2, Deg, FREQ off, TABLE f and g. It does
       NOT fire the "clear" milestone, which belongs to CLR All.
     2 Memory (Blipwork reading, not measured; Build 1 already read the
       history as memory): the variables A–F, X, Y and M to 0, Ans to 0, the
       history emptied. The screen is cleared too, as All does, except in
       TABLE / EQN / INEQ, which keep their screen. Build 9: the device keeps
       the STAT data through it (spec §19.2, measured), as this always did.
     3 All: everything above, plus the mode back to COMP, the STAT data
       (both kinds) emptied, TABLE's function and Start/End/Step (1/5/1)
       and the EQN grid gone (Build 6/7 reading of "everything"). */
  function clrReset(n) {
    if (n === 1 || n === 3) { S.fix = null; S.norm = 2; S.drg = "D"; S.freqOn = false; S.tblType = "fg"; }
    if (n === 2 || n === 3) {
      S.vars = freshVars(); S.ansVal = mkRat(0n, 1n); S.history = []; S.histPos = 0; S.browsing = false;
      if (S.mode !== "TABLE" && !eqnMode()) resetEntry();
    }
    if (n === 3) {
      resetEntry(); S.data = []; S.pairs = []; S.cell = ""; S.row = 0; S.col = 0; S.mode = "COMP";
      S.tbl = null; S.tblRange = freshRange(); S.eqn = null; S.memPending = null;
      emit("clear");
    }
    refreshResult();
  }
  /* SHIFT 1. 1-VAR (unchanged): 1:Type 2:Data 3:Sum 4:Var 5:Distr 6:MinMax.
     A+BX (Build 8, spec §15): 1:Type 2:Data / 3:Sum 4:Var / 5:Reg 6:MinMax.
     Build 9 (spec §19.3): in A+BX 3:Sum, 4:Var and 6:MinMax open the
     measured two-variable lists. 1:Type does nothing in either, as before.
     `fromGrid`: opened on the data grid, so a pasted value starts a fresh line
     (the grid has no calculation line). Build 9: on the grid SHIFT 1 opens the
     short menu (statEditMenu) instead, so this menu is only opened from the
     calculation screen now. */
  function statMenu() {
    const reg = S.mode === "REG", fromGrid = S.screen === "statInput";
    openMenu({ items: [["1", "Type"], ["2", "Data"], ["3", "Sum"], ["4", "Var"], ["5", reg ? "Reg" : "Distr"], ["6", "MinMax"]], ret: "comp", fromGrid,
      onNum(n) {
        if (n === 2) { S.menu = null; S.screen = "statInput"; return; }
        if (reg) { if (n === 3) sum2Menu(); else if (n === 4) var2Menu(); else if (n === 5) regMenu(); else if (n === 6) minMax2Menu(); return; }
        if (n === 3) sumMenu(); else if (n === 4) varMenu(); else if (n === 6) minMaxMenu();
      } });
  }
  /* Build 9 (spec §19.3): the two-variable lists, measured on A+BX:
     Sum `1:Σx² 2:Σx / 3:Σy² 4:Σy / 5:Σxy 6:Σx³ / 7:Σx²y 8:Σx⁴` (one screen,
     four lines), Var `1:n 2:x̄ / 3:σx 4:sx / 5:ȳ 6:σy / 7:sy`, MinMax
     `1:minX 2:maxX / 3:minY 4:maxY`. Picking pastes the token, as Reg does.
     No title line: Sum and Var fill the device's four lines, so there is no
     room for one (MinMax follows them, not device-measured); the rows are
     packed like MODE 3's so the LCD keeps its plain height. A digit with no
     item does nothing. */
  const SUM2_TOKS = ["Σx²", "Σx", "Σy²", "Σy", "Σxy", "Σx³", "Σx²y", "Σx⁴"];
  const VAR2_TOKS = ["n", "x̄", "σx", "sx", YBAR, "σy", "sy"];
  const MINMAX2_TOKS = ["minX", "maxX", "minY", "maxY"];
  function tokMenu(toks) {
    const parent = S.menu;
    openMenu({ parent, packed: true, items: toks.map((t, k) => [String(k + 1), statGlyph(t)]), onNum(n) { pasteStat(toks[n - 1]); } });
  }
  const sum2Menu = () => tokMenu(SUM2_TOKS), var2Menu = () => tokMenu(VAR2_TOKS), minMax2Menu = () => tokMenu(MINMAX2_TOKS);
  /* Build 9 (spec §19.2): SHIFT 1 INSIDE the data editor is a short menu,
     `1:Type 2:Data / 3:Edit`; 3 → `1:Ins 2:Del-A`. Ins puts a new row at the
     cursor holding 0 (FREQ 1; in A+BX X 0, Y 0) and pushes the rest down;
     Del-A empties the table at once, no question, cursor on row 1. Both go
     back to the editor. 2:Data goes back to the editor as it was; 1:Type does
     nothing (as on the calculation screen). AC goes back to the editor (the
     Edit list: back to the short menu). Blipwork choices, not
     device-measured: no titles; the cursor stays on the new row after Ins, in
     the same column; Del-A puts it in the X column; Ins on the open row adds
     a 0 row there; a half-typed number is dropped by Ins and Del-A. */
  function statEditMenu() {
    openMenu({ items: [["1", "Type"], ["2", "Data"], ["3", "Edit"]], ret: "comp",
      onNum(n) {
        if (n === 2) { S.menu = null; S.screen = "statInput"; }
        else if (n === 3) {
          const parent = S.menu;
          openMenu({ parent, items: [["1", "Ins"], ["2", "Del-A"]],
            onNum(k) { if (k === 1) gridInsert(); else if (k === 2) gridClear(); else return; S.menu = null; S.screen = "statInput"; } });
        }
      } });
  }
  /* 5:Reg → `1:A 2:B / 3:r 4:x̂ / 5:ŷ` (spec §15); no title (none measured) */
  function regMenu() {
    const parent = S.menu;
    openMenu({ parent, items: [["1", "A"], ["2", "B"], ["3", "r"], ["4", STAT_GLYPH["x̂"]], ["5", STAT_GLYPH["ŷ"]]], onNum(n) { const t = ["A", "B", "r", "x̂", "ŷ"][n - 1]; if (t) pasteStat(t); } });
  }
  // STAT menu labels match the device (1:Type 2:Data 3:Sum 4:Var 5:Distr 6:MinMax)
  /* Sum: 1:Sigma-x-squared  2:Sigma-x  — the ORDER is the device's, verified on
     Megan's fx-991ZA PLUS II emulator 2026-08-28 (entering 2;4;6 then
     SHIFT 1 -> 3 -> 2 -> = showed 12). Sigma-x is option TWO, not one. */
  function sumMenu() {
    const parent = S.menu;
    openMenu({ title: "Sum", parent, items: [["1", "Σx²"], ["2", "Σx"]], onNum(n) { pasteStat(["Σx²", "Σx"][n - 1]); } });
  }
  function varMenu() {
    const parent = S.menu;
    openMenu({ title: "Var", parent, items: [["1", "n"], ["2", MEAN_GLYPH], ["3", "σx"], ["4", "sx"]], onNum(n) { pasteStat(["n", "x̄", "σx", "sx"][n - 1]); } });
  }
  function minMaxMenu() {
    const parent = S.menu;
    openMenu({ title: "MinMax", parent, items: [["1", "minX"], ["2", "maxX"], ["3", "Q1"], ["4", "med"], ["5", "Q3"]], onNum(n) { pasteStat(["minX", "maxX", "Q1", "med", "Q3"][n - 1]); } });
  }
  /* Build 8 (spec §15): picking a STAT value PASTES its token onto the
     editable calculation line, cursor after it; the learner can keep typing
     and = works the line out (Ans, history, S⇔D and ◀ then act on it as on
     any answer). Before, it showed a fixed line that only = could use.
     - Typing a line: the token goes in at the cursor (`5` then ŷ → `5ŷ`).
     - A result on screen: a fresh line, and that previous answer STAYS bottom
       right until = (spec §15). x̂ / ŷ chain from Ans there (`Ansŷ`), as every
       postfix key does after a result (spec §1); not measured for x̂ / ŷ.
     - Opened on the data grid: a fresh line (the grid has no line to add to).
     A digit with no item in the menu does nothing (it used to leave the
     menu with an empty line). */
  function pasteStat(tok) {
    if (!tok) return;
    let root = S.menu; while (root && root.parent) root = root.parent;
    const fromGrid = !!(root && root.fromGrid);
    S.menu = null; S.screen = "comp";
    if (fromGrid) resetEntry();
    else if (S.result != null) {
      const prev = S.err ? null : S.result;
      resetEntry();
      S.held = prev;
      if (REG_POSTFIX.has(tok)) insertBoxToken({ k: "ans" });
    }
    insertBoxToken({ k: "stat", v: tok });
  }

  // ---- data table ----
  /* Write whatever has been typed into the CURRENT cell. Does not move.
     Returns true if something was written.

     Verified on Megan's fx-991ZA PLUS II emulator, 2026-08-28: typing over a
     row that already holds a value REPLACES it (2;4;6 -> row 1 set to 9 gives
     Sigma-x = 19, not 21), and the row count does not grow. That is exactly
     what the assignment below already did; it is now separated from the
     cursor movement so the arrow keys can reuse it. */
  /* Build 8 (spec §15): in A+BX the grid is X | Y. An X fills its Y with 0
     on a new row; a Y on the open row (no X yet) is dropped, as a FREQ there
     is. No milestones: they belong to the 1-VAR questions.
     Build 9 (spec §19.2): with FREQ on the grid is X | Y | FREQ; a new row's
     FREQ is 1, like 1-VAR's, and column 2 is that FREQ. */
  const gridRows = () => (S.mode === "REG" ? S.pairs : S.data);
  const gridCols = () => (S.mode === "REG" ? 2 : 1) + (S.freqOn ? 1 : 0);   // Build 9: how many value columns the grid has
  function writeCell() {
    if (S.cell === "" || S.cell === "-") return false;
    const v = Number(S.cell.replace(",", "."));
    if (!Number.isFinite(v)) { S.cell = ""; return false; }
    if (S.mode === "REG") {
      const p = S.pairs[S.row];
      if (S.col === 0) S.pairs[S.row] = { x: v, y: p ? p.y : 0, f: p ? (p.f ?? 1) : 1 };
      else if (p && S.col === 1) p.y = v;
      else if (p) p.f = v;
      S.cell = "";
      return true;
    }
    const oorskryf = S.data[S.row] != null;          // was there already a value here?
    if (!S.freqOn) S.data[S.row] = { x: v, f: 1 };
    else if (S.col === 0) S.data[S.row] = { x: v, f: (S.data[S.row] && S.data[S.row].f) ?? 1 };
    else if (S.data[S.row]) S.data[S.row].f = v;
    S.cell = "";
    /* An EDIT milestone, distinct from "data". A quest that asks the learner to
       CHANGE a captured value cannot check the end state alone — wiping the
       table and retyping it reaches the same end state without ever using the
       skill. This fires only when an existing cell was overwritten. */
    if (oorskryf) emit("edit", { row: S.row, col: S.col, value: v });
    emit("data", S.data.map(d => d.x));
    return true;
  }

  /* = and the down arrow: write, then step DOWN — staying in the column you
     are in, whether FREQ is on or off.

     Corrected 2026-08-28 from four photos of Megan's fx-991ZA PLUS II with
     FREQ on: pressing = walks the cursor down the X column (row 1 → 2 → 3),
     it does NOT hop across to the FREQ column. The machine fills the whole X
     column first; FREQ is a separate trip with the ▶ key. We had it doing the
     hop, and round 2's hint taught that wrong sequence along with it. */
  function commitCell() {
    if (!writeCell()) return;
    S.row++;
    if (S.row > gridRows().length) S.row = gridRows().length;   // never past the one open row
  }

  /* Arrow keys INSIDE the data table. Without these a learner can only ever
     append — there is no way back up to row 3 to correct it, which is the
     whole "change a value" skill. Movement is clamped to the rows that exist
     plus the one open row at the bottom. */
  /* Build 8: A+BX's X | Y grid moves exactly like the 1-VAR X | FREQ grid
     (spec §15: ▶ goes to Y on the same row, ▲ back up the Y column; ◀ and ▶
     at the column edges were not measured for A+BX, so FREQ's rules are
     kept). */
  /* Build 9 (spec §19.2): ▼ and ▲ WRAP. The rows are 1…n plus ONE open row;
     ▼ on the open row goes to row 1 and ▲ on row 1 to the open row, in every
     column (X, FREQ, Y). The A+BX grid with FREQ on (X | Y | FREQ) moves
     with the same ◀ ▶ rules over three columns: ◀ steps left, and from X to
     the last column of the row above; ▶ steps right, and from the last
     column to the next row's X (not device-measured for three columns). */
  function statNav(dir) {
    writeCell();                                  // typed digits are stored first
    const oop = gridRows().length;                // the open row at the very bottom
    if (dir === "up")   S.row = S.row > 0 ? S.row - 1 : oop;
    if (dir === "down") S.row = S.row < oop ? S.row + 1 : 0;
    const last = gridCols() - 1;
    if (last > 0) {
      if (dir === "left") {
        if (S.col > 0) S.col--;
        else if (S.row > 0) { S.row--; S.col = last; }
      }
      /* ▶ vanuit die FREQ-kolom spring terug na die VOLGENDE ry se X-kolom.
         Dit lyk vreemd, maar Megan het dit op 2026-08-28 teen haar regte
         fx-991ZA bevestig: "that's how the real calculator works as well."
         Moenie dit "regmaak" nie. */
      if (dir === "right") {
        if (S.col < last) S.col++;
        else if (S.row < oop) { S.row++; S.col = 0; }
      }
    }
    if (S.row > gridRows().length) S.row = gridRows().length;
  }
  /* Build 9 (spec §19.2): DEL with nothing typed deletes the whole row the
     cursor is on; the rows below move up and the cursor keeps its row number
     (on the open row there is nothing to delete). Ins and Del-A (SHIFT 1 3).
     In 1-VAR each reports the new data, as typing a value does. */
  function gridChanged() { if (S.mode !== "REG") emit("data", S.data.map(d => d.x)); }
  function gridDeleteRow() {
    const rows = gridRows();
    if (S.row >= rows.length) return;
    rows.splice(S.row, 1);
    gridChanged();
  }
  function gridInsert() {
    S.cell = "";
    gridRows().splice(S.row, 0, S.mode === "REG" ? { x: 0, y: 0, f: 1 } : { x: 0, f: 1 });
    gridChanged();
  }
  function gridClear() {
    S.cell = "";
    if (S.mode === "REG") S.pairs = []; else S.data = [];
    S.row = 0; S.col = 0; S.gridTop = 0;
    gridChanged();
  }

  // ---- COMP-mode entry model: box tree + cursor ----
  // A "box" is a plain JS array of token nodes. Template nodes (frac/rad/pow)
  // hold their own sub-boxes as num/den/body/exp. A sub-box carries live
  // parent linkage as extra properties on the array (__parent = the owning
  // box, __owner = the template token object, __pkey = 'num'|'den'|'body'|
  // 'exp') so navigation always finds the template's CURRENT index via
  // parent.indexOf(owner) rather than a cached index that could go stale
  // after edits earlier in the box.
  function isBoxEmpty(box) { return box.length === 0; }
  function resetEntry() {
    S.box = []; S.cur = { box: S.box, i: 0 };
    S.result = null; S.exactVal = null; S.showDecimal = false; S.held = null;
    S.err = false; S.browsing = false; S.afterAC = false;
    S.histPos = S.history.length; S.errAt = null; S.form = null;
    S.prompt = null; S.calcRun = null; S.solve = null;   // Build 5: leaves CALC / SOLVE
    if (S.screen === "prompt" || S.screen === "solved") S.screen = "comp";
  }
  function linkSub(sub, parentBox, owner, pkey) { sub.__parent = parentBox; sub.__owner = owner; sub.__pkey = pkey; }
  function insertBoxToken(tok) { S.afterAC = false; S.cur.box.splice(S.cur.i, 0, tok); S.cur.i++; }
  /* `grab` (Build 2, spec §8): { into, enter }. When an operand sits just
     left of the cursor it MOVES into the `into` box (▫/▫: the numerator;
     ˣ√: the index) and the cursor lands in the `enter` box (the denominator
     / the radicand). With no operand the template goes in empty and the
     cursor lands in `enterKey`, as before. */
  function insertTemplate(tmpl, enterKey, grab = null) {
    S.afterAC = false;
    const parentBox = S.cur.box;
    let at = S.cur.i;
    if (grab) {
      const j = operandStart(parentBox, at);
      if (j < at) {
        const taken = parentBox.splice(j, at - j);
        for (const t of taken) for (const key of SUB_KEYS) if (Array.isArray(t[key])) t[key].__parent = tmpl[grab.into];   // a grabbed template's boxes now live one level down
        tmpl[grab.into].push(...taken);
        at = j; enterKey = grab.enter;
      }
    }
    parentBox.splice(at, 0, tmpl);
    for (const key of SUB_KEYS) if (Array.isArray(tmpl[key])) linkSub(tmpl[key], parentBox, tmpl, key);
    S.cur = { box: tmpl[enterKey], i: 0 };
  }
  /* a template's boxes in the order ▶ walks them (the ˣ√ index comes FIRST,
     spec §6: "the INDEX box first (small, upper left), then the radicand") */
  /* Build 4: log□ walks base → inside the bracket (spec §9: "BASE box first
     (low, small), then into the bracket"); a mixed number walks whole → top
     → bottom (spec §8); |□|, 10^□ and e^□ have one box each. */
  const TMPL_BOXES = { frac: ["num", "den"], rad: ["body"], pow: ["exp"], xrt: ["idx", "body"],
    logb: ["base", "body"], abs: ["body"], tenpow: ["exp"], epow: ["exp"], mixed: ["whole", "num", "den"] };
  function exitOrAdvanceRight(box) {
    if (!box.__parent) return;   // root, at end: no-op
    const owner = box.__owner, parent = box.__parent;
    const order = TMPL_BOXES[owner.k], k = order.indexOf(box.__pkey);
    if (k < order.length - 1) { S.cur = { box: owner[order[k + 1]], i: 0 }; return; }   // frac top → bottom, ˣ√ index → radicand
    const pidx = parent.indexOf(owner);
    S.cur = { box: parent, i: pidx + 1 };   // exits: den / body / exp → right after the template token
  }
  function exitOrAdvanceLeft(box) {
    if (!box.__parent) return;
    const owner = box.__owner, parent = box.__parent;
    const order = TMPL_BOXES[owner.k], k = order.indexOf(box.__pkey);
    if (k > 0) { const b = owner[order[k - 1]]; S.cur = { box: b, i: b.length }; return; }   // frac bottom → top, ˣ√ radicand → index
    const pidx = parent.indexOf(owner);
    S.cur = { box: parent, i: pidx };   // exits backward: before the template token
  }
  const isTmpl = t => !!TMPL_BOXES[t.k];
  function enterTemplateForward(tmpl) {   // ▶ landing on a template from outside: step INTO its first box
    S.cur = { box: tmpl[TMPL_BOXES[tmpl.k][0]], i: 0 };
  }
  function enterTemplateBackward(tmpl) {   // ◀ landing on a template from outside: step INTO its last box, at its end
    const order = TMPL_BOXES[tmpl.k], b = tmpl[order[order.length - 1]];
    S.cur = { box: b, i: b.length };
  }
  /* ---- Build 1: editing after a result, history, AC recall (spec §1) ----
     The device FORGETS the answer the moment ◀ or ▶ is pressed and lets you
     fix the sum: ◀ puts the cursor at the END of the expression, ▶ at the
     START, the result disappears and typing inserts at the cursor. Before
     this, the result stayed "on screen" in our state, so the next digit
     wiped the line: Megan's "arrowing back to fix a typo wipes the screen". */
  function editFromResult(dir) {
    /* Build 8: a STAT read-off is an ordinary line now, so ◀ / ▶ edit it too
       (before, they did nothing on it). */
    /* Build 2 (spec §3, Goto): on an error screen ◀ and ▶ BOTH return to the
       expression with the cursor just before the token that caused a Syntax
       ERROR (2+×3+4 → between + and ×). For a Math ERROR the spec does not
       say where the cursor lands: Blipwork puts it at the end of the line. */
    const goto = S.err ? (S.errAt || { box: S.box, i: S.box.length }) : null;
    S.result = null; S.exactVal = null; S.showDecimal = false; S.err = false; S.errAt = null; S.form = null;
    S.browsing = false; S.histPos = S.history.length;
    if (goto) S.cur = { box: goto.box, i: Math.min(goto.i, goto.box.length) };
    else S.cur = dir < 0 ? { box: S.box, i: S.box.length } : { box: S.box, i: 0 };
  }
  /* After AC, ◀ or ▶ recalls the LAST expression in edit mode (no result). */
  function recallLast(dir) {
    const e = S.history[S.history.length - 1];
    S.box = cloneBox(e.box);
    S.cur = dir < 0 ? { box: S.box, i: S.box.length } : { box: S.box, i: 0 };
    S.result = null; S.exactVal = null; S.showDecimal = false; S.err = false; S.form = null;
    S.afterAC = false; S.browsing = false; S.histPos = S.history.length;
  }
  /* Show history entry idx WITH its result, as the device's ▲/▼ replay does.
     The box is a copy, so editing it (◀/▶) never changes the history. */
  function showEntry(idx) {
    const e = S.history[idx];
    S.box = cloneBox(e.box); S.cur = { box: S.box, i: S.box.length };
    S.exactVal = e.val; S.showDecimal = e.showDecimal; S.form = e.form || null;
    S.result = shownHTML();
    S.err = false; S.held = null;
    S.browsing = true; S.afterAC = false; S.histPos = idx;
  }
  /* ▲ (dir −1) = older, ▼ (dir +1) = newer. After = the result on screen IS
     the newest entry (histPos = newest), so ▲ shows the one before it ("the
     previous calculation"); after AC histPos sits below the newest, so ▲
     shows the last calculation itself. Past either end: nothing happens. */
  function histNav(dir) {
    const target = S.histPos + dir;
    if (target < 0 || target > S.history.length - 1) return;
    showEntry(target);
  }
  /* The status-line history arrow (spec §1/§16): ▲ after any =; inside the
     history ▲ when something older exists, ▼ when something newer does
     (▲▼ for both). Hidden on an error screen (spec §3) and while typing. */
  function histIndicator() {
    /* Build 7 (spec §13): on an EQN / INEQ answer the same arrows show what
       is above and below: ▼ on the first, ▲▼ in between, ▲ on the last */
    if (S.screen === "eqnAns" && S.eqn && S.eqn.answers) { const k = S.eqn.ai; return (k > 0 ? "▲" : "") + (k < S.eqn.answers.length - 1 ? "▼" : ""); }
    if (S.screen !== "comp" || S.err || S.result == null || !S.history.length) return "";
    if (!S.browsing) return "▲";
    return (S.histPos > 0 ? "▲" : "") + (S.histPos < S.history.length - 1 ? "▼" : "");
  }
  function moveHoriz(dir) {
    if (S.result != null) return editFromResult(dir);
    if (S.afterAC && isBoxEmpty(S.box) && S.history.length) return recallLast(dir);
    const box = S.cur.box, i = S.cur.i;
    if (dir > 0) {
      if (i < box.length) { const t = box[i]; if (isTmpl(t)) enterTemplateForward(t); else S.cur.i = i + 1; }
      else exitOrAdvanceRight(box);
    } else {
      if (i > 0) { const t = box[i - 1]; if (isTmpl(t)) enterTemplateBackward(t); else S.cur.i = i - 1; }
      else exitOrAdvanceLeft(box);
    }
  }
  function moveVert(dir) {
    // a result (or a history entry) on screen, or the empty AC screen: ▲▼ walk the history
    if (S.result != null || (S.afterAC && isBoxEmpty(S.box))) { if (!S.err) histNav(dir); return; }
    const box = S.cur.box;
    if (!box.__parent || (box.__owner.k !== "frac" && box.__owner.k !== "mixed")) return;   // ▲▼ only meaningful inside a fraction (or a mixed number's top/bottom, Build 4)
    const owner = box.__owner;
    if (dir > 0 && box.__pkey === "num") S.cur = { box: owner.den, i: Math.min(S.cur.i, owner.den.length) };
    else if (dir < 0 && box.__pkey === "den") S.cur = { box: owner.num, i: Math.min(S.cur.i, owner.num.length) };
  }
  /* Build 10 (spec §19.6): DEL deletes what is LEFT of the cursor. At the
     start of a template box nothing is left of the cursor inside that box:
     - at the start of a LATER box (a fraction's bottom, the ˣ√ radicand, a
       mixed number's top or bottom, log□'s bracket) DEL deletes nothing and
       only moves the cursor to the END of the box before it (3/4 with the
       cursor before the 4: the cursor goes after the 3, typing 7 gives 37/4);
     - at the start of the FIRST box DEL removes the frame and its contents
       stay inline, every box in walking order, the cursor where the frame
       began (2+3/4 from the start of the top: 2+34; 2√9: 29; an empty □/□
       or √□ simply goes).
     Measured on the device for ▫/▫ and √ only; x^□, log□, Abs, ˣ√, 10^□,
     e^□ and the mixed number follow the same rule (not measured). Before
     Build 10, DEL there deleted the whole template. */
  function doDelBox() {
    const box = S.cur.box;
    if (S.cur.i > 0) { box.splice(S.cur.i - 1, 1); S.cur.i--; return; }
    if (!box.__parent) return;   // at the very start of the root: no-op
    const parent = box.__parent, owner = box.__owner, pidx = parent.indexOf(owner);
    if (pidx < 0) return;
    const order = TMPL_BOXES[owner.k], k = order.indexOf(box.__pkey);
    if (k > 0) { const b = owner[order[k - 1]]; S.cur = { box: b, i: b.length }; return; }
    const spill = order.flatMap(key => owner[key]);
    for (const t of spill) for (const key of SUB_KEYS) if (Array.isArray(t[key])) t[key].__parent = parent;   // a spilled template's boxes now live one level up
    parent.splice(pidx, 1, ...spill);
    S.cur = { box: parent, i: pidx };
  }
  /* The result as it should look now: its form (Build 4: mixed 1¾ or °'"),
     else exact or decimal, decimals following Fix. */
  function shownHTML() {
    if (S.form === "dms") return formatDMS(S.exactVal);
    if (S.form === "mixed") return formatMixed(S.exactVal);
    return formatValue(S.exactVal, S.showDecimal, S.fix);
  }
  /* redraw the result on screen after a SETUP change (Fix / Norm / CLR Setup) */
  function refreshResult() {
    if (S.result == null || S.err || !S.exactVal || isErr(S.exactVal)) return;
    S.result = shownHTML();
  }
  function toggleSD() {
    // nothing to toggle to: a decimal answer, or a fraction / whole number too long to show exactly (spec §7)
    if (!S.exactVal || isErr(S.exactVal) || !exactFits(S.exactVal)) return;
    /* Build 4: S⇔D on the °'" form does nothing (not measured); from the
       mixed form it goes to the decimal (1¾ → 1,75), and the next S⇔D
       back to the improper fraction, the factory d/c form. */
    if (S.form === "dms") return;
    if (S.form === "mixed") { S.form = null; S.showDecimal = true; }
    else S.showDecimal = !S.showDecimal;
    S.result = shownHTML();
  }
  /* SHIFT S⇔D (Build 4, spec §7/§8): improper ↔ mixed (100/3 ↔ 33⅓). The
     spec's "1¾ = 7/4, S⇔D → 1,75, SHIFT S⇔D → 1¾" may be read as a
     sequence, so from the decimal it goes to the mixed form too. A value
     with no mixed form (⅔, 5, √2, a decimal answer): nothing happens. */
  function toggleMixed() {
    if (S.result == null || S.err || S.form === "dms" || !hasMixedForm(S.exactVal)) return;
    S.form = S.form === "mixed" ? null : "mixed";
    S.showDecimal = false;
    S.result = shownHTML();
  }
  /* °'" on a result (Build 4, spec §1, §9): it acts ON the result, it does
     not start a new line. The °'" form goes to the decimal (30°15'0" →
     30,25) and any other form goes to °'" (and back). Past 10 digits before
     the comma there is no °'" form (Blipwork choice, not measured). */
  function dmsToggle() {
    if (S.err || !S.exactVal || isErr(S.exactVal)) return;
    if (S.form === "dms") { S.form = null; S.showDecimal = true; }
    else if (Math.abs(toFloatV(S.exactVal)) < 1e10) S.form = "dms";
    else return;
    S.result = shownHTML();
  }
  /* Build 8: the "stat" milestone the calcdo questions mark (questions.js
     compares its tok and its NUMBER, never the text). A line that is ONE
     STAT value (x̄ =) reports that token with statValue's exact number, as
     before; a line that does more with it (x̄+1, 5ŷ) reports tok null and
     its answer, so it never counts as the plain read-off a question asks
     for. A line with no STAT value reports nothing. */
  function statMilestone(target, v) {
    const toks = [];
    (function walk(box) { for (const t of box) { if (t.k === "stat") toks.push(t.v); const order = TMPL_BOXES[t.k]; if (order) for (const key of order) walk(t[key]); } })(target);
    if (!toks.length) return;
    const lone = target.length === 1 && isStatAtom(target[0]) ? target[0].v : null;
    /* Build 9: in A+BX a lone x̄ (n, Σx …) is a two-variable read-off, so it
       reports the number shown, never statValue's 1-VAR one */
    const value = isErr(v) ? null : lone && S.mode !== "REG" && !REG_TOKS.has(lone) ? statValue(lone) : toFloatV(v);
    emit("stat", { tok: lone, value });
  }
  function doEquals() {
    S.held = null;   // a pasted read-off's previous answer goes at = (spec §15)
    if (isBoxEmpty(S.box)) return;
    /* A trailing →A (STO), M+ or M− token: evaluate the rest, then store /
       add to M. These lines are shown with their result but are NOT added to
       the history: spec §1 lists what the history holds (= results, CALC
       results, RCL lines) and STO / M± are not among them. */
    const last = S.box[S.box.length - 1];
    const effect = last && (last.k === "sto" || last.k === "mplus" || last.k === "mminus") ? last : null;
    const target = effect ? S.box.slice(0, -1) : S.box;
    let v = evalBox(target, evalCtx());
    if (!isErr(v) && !Number.isFinite(toFloatV(v))) v = VERR("Math ERROR");   // an exact value too big for any display, same as a float overflow
    S.browsing = false; S.afterAC = false;
    statMilestone(target, v);
    if (isErr(v)) {
      S.result = v.msg; S.err = true; S.exactVal = null; S.showDecimal = false; S.form = null; S.histPos = S.history.length;
      // where Goto (◀/▶) will put the cursor; `target` may be a copy of the line without its →A / M+ token
      S.errAt = v.at ? { box: v.at.box === target ? S.box : v.at.box, i: v.at.i } : null;
      return;
    }
    if (effect) {
      if (effect.k === "sto") S.vars[effect.name] = v;
      else S.vars.M = effect.k === "mplus" ? vAdd(S.vars.M, v) : vSub(S.vars.M, v);
    }
    S.err = false; S.errAt = null;
    S.exactVal = v; S.showDecimal = !exactFits(v);   // floats, and fractions past the size limit, show as decimals (spec §7)
    /* Build 4 (spec §9): a line that is ONE °'" entry (30°15') shows its
       result in the °'" form, 30°15'0". °'" mixed with any other operation
       was not measured: Blipwork shows that result as a plain decimal. */
    S.form = null;
    if (boxHasDMS(target)) {
      const arr = compileBox(target);
      const lone = arr.length === 1 ? arr[0] : arr.length === 2 && arr[0].k === "op" && arr[0].v === "−" ? arr[1] : null;
      if (lone && lone.k === "dmsv" && Math.abs(toFloatV(v)) < 1e10) S.form = "dms"; else S.showDecimal = true;
    }
    S.result = shownHTML();
    S.ansVal = v;
    if (effect) { S.histPos = S.history.length; return; }
    S.history.push({ box: cloneBox(S.box), val: v, showDecimal: S.showDecimal, form: S.form });
    if (S.history.length > MAX_HISTORY) S.history.shift();
    S.histPos = S.history.length - 1;
  }
  /* STO → letter, M+ and M− act at once, no = needed (spec §2): `5 M+` shows
     `5M+` with the result 5; `5 SHIFT RCL (−)` shows `5→A` and 5. With a
     result already on screen the value stored is Ans (the line reads
     `Ans→A` / `AnsM+`): the spec does not cover this case, it is the same
     chaining from Ans that + − × ÷ already do. Nothing typed: nothing happens. */
  function memKey(tok) {
    if (S.result != null) { if (S.err) return; S.box = [{ k: "ans" }]; }
    else if (isBoxEmpty(S.box)) return;
    S.box.push(tok); S.cur = { box: S.box, i: S.box.length };
    doEquals();
  }
  /* RCL then a letter: the line shows the letter, the result its value, and
     it goes into the history (spec §2) — exactly "type A, press =". */
  function rclKey(letter) {
    resetEntry();
    S.box.push({ k: "var", name: letter }); S.cur = { box: S.box, i: S.box.length };
    doEquals();
  }

  /* ---- Build 5: the PROMPT screen (spec §10, §11; reused by TABLE §12
     and EQN §13 in later builds) ----
     One piece for every "type a value" screen: the label at the top left
     (`X?`, `Solve for X`, later `Start?`), the current value at the bottom
     right. Typing shows the entry BIG at the top left, in place of the
     label (spec §10: "Typing a number shows it big at top left (the old
     value stays bottom right until =)"). = with nothing typed keeps the
     shown value; = with something typed evaluates it (a whole expression
     may be typed: −5, ½, √2 ...) and hands the Value to onAccept. AC calls
     onCancel (default: the blank screen, as AC always gives).
     A Syntax / Math ERROR in the typed entry shows the usual three-line
     error screen; ◀ / ▶ (Goto) go back to the typed entry, AC cancels (the
     spec does not cover an error at a prompt: Blipwork choice).
     The typed entry is an ordinary box: S.cur points into it while the
     prompt is open, so every entry key, ◀ ▶ ▲ ▼ and DEL work in it exactly
     as on the calculation line. The calculation line (S.box) is untouched.
     p = { label, value, onAccept(value, typed), onCancel? } */
  function openPrompt(p) {
    S.prompt = { label: p.label, value: p.value, onAccept: p.onAccept, onCancel: p.onCancel || null, box: [], err: null, errAt: null };
    S.cur = { box: S.prompt.box, i: 0 };
    S.result = null; S.exactVal = null; S.showDecimal = false; S.err = false; S.errAt = null; S.form = null;
    S.browsing = false; S.afterAC = false; S.histPos = S.history.length;
    S.screen = "prompt";
  }
  function closePrompt() {
    S.prompt = null; S.screen = "comp";
    S.cur = { box: S.box, i: S.box.length };
  }
  function promptCancel() {
    const p = S.prompt;
    closePrompt();
    if (p && p.onCancel) p.onCancel();
    else { resetEntry(); S.afterAC = true; }   // AC: the blank screen, history kept (spec §1)
  }
  function promptKey(key) {
    const p = S.prompt;
    if (key === "ac") return promptCancel();
    if (p.err) {   // only AC, ◀ and ▶ do anything on an error screen (spec §3)
      if (key === "left" || key === "right") {
        const at = p.errAt || { box: p.box, i: p.box.length };
        p.err = null; p.errAt = null;
        S.cur = { box: at.box, i: Math.min(at.i, at.box.length) };
      }
      return;
    }
    if (key === "eq") {
      const typed = !isBoxEmpty(p.box);
      let v = p.value;
      if (typed) {
        v = evalBox(p.box, { ans: S.ansVal, drg: S.drg, vars: S.vars });
        if (!isErr(v) && !Number.isFinite(toFloatV(v))) v = VERR("Math ERROR");
        if (isErr(v)) { p.err = v.msg; p.errAt = v.at || null; return; }
      }
      closePrompt();
      return p.onAccept(v, typed);
    }
    if (key === "left" || key === "right") return moveHoriz(key === "left" ? -1 : 1);
    if (key === "up" || key === "down") return moveVert(key === "up" ? -1 : 1);
    if (key === "del") return doDelBox();
    if (key === "eqs" || key === "colon") return;   // an "=" or ":" is not a value
    if (isEntryKey(key)) typeKey(key);
  }
  function promptHTML(p) {
    const typing = !isBoxEmpty(p.box);
    cursorOn = typing;
    const top = typing ? renderBox(p.box) : `<span class="lcd-pr-label">${escapeHtml(p.label)}</span>`;
    return `<div class="lcd-line lcd-pr${typing ? " lcd-pr-typing" : ""}"><span class="lcd-lmark" hidden>◀</span><div class="lcd-expr">${top}</div></div>`
      + `<div class="lcd-res">${formatValue(p.value, !exactFits(p.value), S.fix)}</div>`;
  }

  /* ---- Build 5: CALC (spec §10) ----
     CALC on a line with letters asks for each letter in the ORDER THEY
     APPEAR (AX+B: A?, then X?, then B?), each prompt showing the letter's
     current value; the values are stored in the letters, then the line is
     worked out exactly as = does, so the answer goes into the history and
     into Ans (spec §10: "CALC answers ARE added to the history"). After the
     answer, = or CALC asks again from the first letter; AC leaves.
     Not measured, Blipwork choices: a line with no letters is worked out at
     once, like =; a line holding "=" is asked for its letters and then gives
     the = key's Syntax ERROR; AC on a prompt gives the blank screen, as AC
     after the answer does; CALC and SOLVE work in COMP mode only (STAT mode
     behaves exactly as before). */
  function lettersIn(box, out = []) {
    for (const t of box) {
      if (t.k === "var" && !out.includes(t.name)) out.push(t.name);
      const order = TMPL_BOXES[t.k];
      if (order) for (const key of order) lettersIn(t[key], out);   // a template's boxes in the order ▶ walks them
    }
    return out;
  }
  const canCalc = () => S.mode === "COMP" && !isBoxEmpty(S.box);
  function startCalc() {
    if (!canCalc()) return;
    const letters = lettersIn(S.box);
    if (!letters.length) { S.calcRun = null; return doEquals(); }
    S.calcRun = { letters };
    calcAsk(0);
  }
  function calcAsk(k) {
    const run = S.calcRun, letters = run.letters;
    if (k >= letters.length) {
      doEquals();
      S.calcRun = S.err ? null : run;
      return;
    }
    const L = letters[k];
    openPrompt({ label: L + "?", value: S.vars[L], onAccept: v => { S.vars[L] = v; S.calcRun = run; calcAsk(k + 1); } });
    S.calcRun = run;
  }

  /* ---- Build 5: SOLVE = SHIFT CALC (spec §11) ----
     The line may hold one "=" (ALPHA CALC); without it SOLVE solves
     line = 0. `Solve for X` asks for the starting guess, X's current value;
     a typed guess replaces it (and is stored in X, as CALC stores a typed
     value: Blipwork reading). = solves with solveNewton (above). The answer
     screen shows three small lines: the equation, X= and L−R=. X keeps the
     answer, so the next SOLVE starts from it. SOLVE runs are NOT added to
     the history and do not change Ans (spec §1 / §11; Ans not measured).
     Other letters in the equation (AX+B=0) use their stored values and are
     not asked for (foreman ruling: the spec measured only X). */
  function startSolve() {
    if (!canCalc()) return;
    S.calcRun = null; S.solve = null;
    openPrompt({ label: "Solve for X", value: S.vars.X, onAccept: v => { S.vars.X = v; runSolve(toFloatV(v)); } });
  }
  /* the two sides of the line: split at the first "=" in the line itself
     (an "=" inside a fraction or root, or a second "=", is a Syntax ERROR
     where it stands, like any other stray token) */
  function splitEquation(box) {
    const k = box.findIndex(t => t.k === "eqs");
    return k < 0 ? { L: box, R: null, k } : { L: box.slice(0, k), R: box.slice(k + 1), k };
  }
  function solveError(msg, at) {
    S.screen = "comp"; S.solve = null;
    S.result = msg; S.err = true; S.exactVal = null; S.showDecimal = false; S.form = null;
    S.errAt = at; S.histPos = S.history.length;
  }
  function runSolve(x0) {
    const { L, R, k } = splitEquation(S.box);
    const ctxAt = x => ({ ans: S.ansVal, drg: S.drg, vars: { ...S.vars, X: VFLOAT(x) } });
    const sides = x => {
      const c = ctxAt(x), l = evalBox(L, c), r = R ? evalBox(R, c) : mkRat(0n, 1n);
      return { l, r };
    };
    /* a Syntax ERROR is a Syntax ERROR whatever X is: show it, with Goto
       just before the token that caused it (spec §3) */
    const first = sides(Number.isFinite(x0) ? x0 : 0);
    for (const [v, part, off] of [[first.l, L, 0], [first.r, R, k + 1]]) {
      if (v && isErr(v) && v.msg === "Syntax ERROR") {
        const at = v.at ? (v.at.box === part ? { box: S.box, i: v.at.i + off } : v.at) : null;
        return solveError("Syntax ERROR", at);
      }
    }
    /* the equation cannot be worked out at the starting guess (log(X) from
       X = 0): Math ERROR. Not measured (Blipwork choice). */
    if (!Number.isFinite(x0) || isErr(first.l) || isErr(first.r) || !Number.isFinite(toFloatV(first.l)) || !Number.isFinite(toFloatV(first.r))) return solveError("Math ERROR", null);
    const F = x => {
      const s = sides(x);
      if (isErr(s.l) || isErr(s.r)) return null;
      const l = toFloatV(s.l), r = toFloatV(s.r);
      return Number.isFinite(l) && Number.isFinite(r) ? { l, r } : null;
    };
    const root = solveNewton(F, x0);
    if (!root) return solveError("Can't Solve", null);   // spec §11: X²+1 → Can't Solve; ◀ returns to the equation (end of the line, as for Math ERROR)
    /* X is kept to 15 significant digits, the device's working precision,
       and stored as that exact decimal (RCL X shows it, spec §11). L−R is
       shown as 0 when it is below 10⁻¹³ of the size of the numbers in the
       equation (rounding noise; the device shows 0 for 1000(1,08)^X=2000). */
    let x = Number(root.x.toPrecision(15));
    if (Object.is(x, -0)) x = 0;
    const o = F(x) || root;
    const lr = o.l - o.r;
    S.vars.X = floatToRat(x);
    S.solve = { x, lr: Math.abs(lr) <= 1e-13 * root.scale ? 0 : lr };
    S.screen = "solved";
  }
  /* keys on the SOLVE answer screen (spec §11): = (or SOLVE) asks
     `Solve for X` again with the new X as the guess; ◀ goes back to the
     equation, editable, cursor at the end; AC gives the blank screen. ▶ puts
     the cursor at the START (spec silent: the §1 rule for results). Every
     other key does nothing (spec silent). */
  function solvedKey(key) {
    if (key === "eq" || key === "solve") return startSolve();
    if (key === "left" || key === "right") {
      S.screen = "comp"; S.solve = null; S.result = null; S.err = false;
      S.cur = key === "left" ? { box: S.box, i: S.box.length } : { box: S.box, i: 0 };
      return;
    }
    if (key === "ac") { resetEntry(); S.afterAC = true; }
  }
  function solvedHTML() {
    cursorOn = false;
    const num = v => formatDecimal(VFLOAT(v), S.fix);
    return `<div class="lcd-solve"><div class="lcd-expr lcd-sv-eq">${renderBox(S.box)}</div>`
      + `<div class="lcd-sv-row"><span class="lcd-sv-lab">X=</span><span class="lcd-sv-val">${num(S.solve.x)}</span></div>`
      + `<div class="lcd-sv-row"><span class="lcd-sv-lab">L−R=</span><span class="lcd-sv-val">${num(S.solve.lr)}</span></div></div>`;
  }

  /* ---- Build 6: TABLE = MODE 7 (spec §12) ----
     Measured on the device and built as measured:
     - MODE 7 opens `f(X)=` with the cursor; the function is typed with the
       normal keys (X is ALPHA )). = → `g(X)=` (factory setting: both); g
       left empty and = skips it. Then Start? (1), End? (5), Step? (1) on
       the Build 5 prompt screen; the three REMEMBER the last values used.
     - The table: row numbers, X | F(X) (| G(X) when g was given), 3 rows
       visible, the selected cell and its column heading reversed, the
       selected value big and right-aligned underneath (always a decimal:
       2^X at −2 shows 0,25, not ¼). Starts on row 1, column X; ▶ / ◀ move
       across, ▼ / ▲ move down / up, the view scrolling one row at a time;
       ▼ past the last row shows an empty lit row. View only: typing does
       nothing anywhere in the table.
     - 21 rows or more → Insufficient MEM (three-line screen); ◀ goes back to
       f(X)= with the function kept.
     - AC in the table → f(X)=<function> with the cursor at the START; AC
       again clears it to an empty f(X)=.
     Blipwork choices where the spec is silent (each listed in the Build 6
     report): MODE 7 always opens an EMPTY f(X)= (g is emptied too); = on an
     empty f(X)= does nothing; on g(X)= the cursor starts at the END of g;
     AC on g(X)= clears g; AC on Start? / End? / Step?, AC on the Insufficient
     MEM screen and ON all go back to f(X)= like AC in the table (cursor at
     the start); Goto (◀ or ▶) from Insufficient MEM puts the cursor at the
     END of f; a Syntax ERROR in f or g shows after Step?, like Insufficient
     MEM, and Goto puts the cursor just before the bad token in that line;
     Step 0, or a Start/End/Step that gives no row at all, is Math ERROR;
     ▶ on the last column and ◀ on X stay put (no wrap); ▼ on the empty row
     and ▲ on row 1 stay put; MODE, SETUP and CLR work on the f(X)= line and
     the table, and a menu left with AC (or a SETUP choice) returns there;
     the table does not change X, Ans or the history; a SETUP change made
     while the table is showing does not recompute it; Fix rounds the bottom
     line but not the cut-off cells. */
  function startTable() {
    resetEntry();
    S.mode = "TABLE"; S.menu = null;
    S.tbl = { f: [], g: [], which: "f", rows: null, hasG: false, r: 0, c: 0, top: 0, back: null, err: null };
    openTblFn("f", "end");
  }
  /* the f(X)= or g(X)= line, its box the one S.cur types into (as the
     Build 5 prompt does), cursor at the start or the end */
  function openTblFn(which, at) {
    const T = S.tbl, box = T[which];
    T.which = which; T.err = null;
    S.cur = { box, i: at === "start" ? 0 : box.length };
    S.result = null; S.err = false; S.errAt = null; S.afterAC = false; S.browsing = false;
    S.screen = "tblF";
  }
  function tblFnKey(key) {
    const T = S.tbl;
    if (key === "mode") return modeMenu();
    if (key === "setup") return setupMenu();
    if (key === "clr") return clrMenu();
    if (key === "ac") { T[T.which] = []; return openTblFn(T.which, "start"); }   // spec §12: AC clears the line to an empty f(X)=
    if (key === "eq") {
      if (T.which === "g") return askRange(0);   // g given or left empty (spec §12: an empty g is skipped)
      if (!isBoxEmpty(T.f)) { if (S.tblType === "f") askRange(0); else openTblFn("g", "end"); }   // Build 8: SETUP TABLE 1:f(x) asks for f only (spec §16)
      return;
    }
    if (key === "left" || key === "right") return moveHoriz(key === "left" ? -1 : 1);
    if (key === "up" || key === "down") return moveVert(key === "up" ? -1 : 1);
    if (key === "del") return doDelBox();
    if (key === "eqs" || key === "colon") return;   // an "=" or ":" has no place in a function (as at a prompt)
    if (isEntryKey(key)) typeKey(key);
  }
  function tblFnHTML() {
    const T = S.tbl;
    cursorOn = true;
    return `<div class="lcd-line"><span class="lcd-lmark" hidden>◀</span><div class="lcd-expr"><span class="lcd-tbl-fn">${T.which}(X)=</span>${renderBox(T[T.which])}</div></div><div class="lcd-res"></div>`;
  }
  const RANGE_KEYS = ["start", "end", "step"], RANGE_LABELS = ["Start?", "End?", "Step?"];
  function askRange(k) {
    if (k >= RANGE_KEYS.length) return buildTable();
    const key = RANGE_KEYS[k];
    openPrompt({ label: RANGE_LABELS[k], value: S.tblRange[key],
      onAccept: v => { S.tblRange[key] = v; askRange(k + 1); },
      onCancel: () => openTblFn("f", "start") });
  }
  /* how many rows Start, End and Step give: Start, Start+Step, … up to End */
  function tblRowCount() {
    const { start, end, step } = S.tblRange;
    const span = vDiv(vSub(end, start), step);
    if (isErr(span)) return 0;   // Step 0
    if (span.kind === "rat") return span.n < 0n ? 0 : Number(span.n / span.d) + 1;
    const q = toFloatV(span);
    return Number.isFinite(q) && q > -1e-9 ? Math.floor(q + 1e-9) + 1 : 0;
  }
  function tblEval(box, x) {
    let v = evalBox(box, { ans: S.ansVal, drg: S.drg, vars: { ...S.vars, X: x } });
    if (!isErr(v) && !Number.isFinite(toFloatV(v))) v = VERR("Math ERROR");
    return v;
  }
  function tblError(msg, which, at) { S.tbl.err = { msg, which, at }; S.screen = "tblErr"; }
  function buildTable() {
    const T = S.tbl, n = tblRowCount();
    if (n < 1) return tblError("Math ERROR", "f", null);
    if (n > TABLE_MAX_ROWS) return tblError("Insufficient MEM", "f", null);
    const hasG = S.tblType !== "f" && !isBoxEmpty(T.g), { start, step } = S.tblRange, rows = [];   // Build 8: with f(x) only, a g typed earlier is not used
    for (let k = 0; k < n; k++) {
      const x = vAdd(start, vMul(mkRat(BigInt(k), 1n), step));   // exact: 0,25 steps stay 0,25 steps
      rows.push({ x, f: tblEval(T.f, x), g: hasG ? tblEval(T.g, x) : null });
    }
    /* a Syntax ERROR does not depend on X, so the first row shows it */
    for (const which of hasG ? ["f", "g"] : ["f"]) {
      const v = rows[0][which];
      if (isErr(v) && v.msg === "Syntax ERROR") return tblError("Syntax ERROR", which, v.at || null);
    }
    Object.assign(T, { rows, hasG, r: 0, c: 0, top: 0 });
    S.screen = "table";
  }
  /* only AC, ◀ and ▶ reach here (spec §3: everything else is ignored) */
  function tblErrKey(key) {
    const e = S.tbl.err;
    if (key === "ac") return openTblFn("f", "start");
    if (key === "left" || key === "right") {
      openTblFn(e.which, "end");
      if (e.at) S.cur = { box: e.at.box, i: Math.min(e.at.i, e.at.box.length) };
    }
  }
  function tblViewKey(key) {
    const T = S.tbl, ncol = T.hasG ? 3 : 2;
    if (key === "mode") return modeMenu();
    if (key === "setup") return setupMenu();
    if (key === "clr") return clrMenu();
    if (key === "ac") return openTblFn("f", "start");   // spec §12: back to f(X)=<function>, cursor at the START
    if (key === "down" && T.r < T.rows.length) { T.r++; if (T.r > T.top + TBL_VISIBLE - 1) T.top = T.r - TBL_VISIBLE + 1; }
    else if (key === "up" && T.r > 0) { T.r--; if (T.r < T.top) T.top = T.r; }
    else if (key === "right" && T.c < ncol - 1) T.c++;
    else if (key === "left" && T.c > 0) T.c--;
    // every other key: nothing (spec §12: the table is view only)
  }
  function tblHTML() {
    const T = S.tbl, heads = T.hasG ? ["X", "F(X)", "G(X)"] : ["X", "F(X)"];
    const head = [{ html: "", cls: "lcd-tbl-n" }, ...heads.map((h, c) => ({ html: h, cls: c === T.c ? "lcd-tbl-lit" : "" }))];
    const body = [];
    for (let r = T.top; r < T.top + TBL_VISIBLE; r++) {
      const row = T.rows[r], open = !row && r === T.r;   // the empty lit row past the end
      const vals = row ? [row.x, row.f, row.g] : [];
      body.push([{ html: row || open ? String(r + 1) : "", cls: "lcd-tbl-n" },
        ...heads.map((_, c) => ({ html: row ? tableCellText(vals[c]) : "", cls: r === T.r && c === T.c ? "lcd-tbl-sel" : "" }))]);
    }
    const sel = T.rows[T.r], v = sel ? [sel.x, sel.f, sel.g][T.c] : null;
    const bottom = v == null ? "" : isErr(v) ? "ERROR" : formatDecimal(v, S.fix);
    return gridHTML("lcd-tab lcd-tbl", head, body) + `<div class="lcd-res lcd-tbl-val">${bottom}</div>`;
  }

  /* ---- Build 7: EQN = MODE 5 (spec §13), INEQ = MODE ▼ 2 (spec §14) ----
     Measured on the device and built as measured:
     - Picking a type opens the coefficient grid with EVERY coefficient 0;
       picking the mode again always resets them. Headings a b c (a b c d),
       matrix brackets, row numbers at the far left for the systems only.
       The selected cell is reversed, its value big at the bottom right. Four
       columns do not fit: the view slides sideways (three show at a time).
     - Typing shows the entry at the BOTTOM LEFT; the cell keeps its old
       value until =. = with something typed stores it and moves RIGHT
       (a → b → c), wrapping to the next row's a; on the very last cell it
       stores and stays. = with NOTHING typed, on any cell, SOLVES. The
       arrows move without changing a cell.
     - Answers one per screen: the label top left, the value big bottom
       right, ▼ / ▲▼ / ▲ in the status line for what is above and below.
       = steps forward, ▲ steps back; after the last answer = goes back to
       the grid (cell a, numbers kept); AC too. Digits do nothing there;
       S⇔D switches the answer between exact and decimal.
     Blipwork choices where the spec is silent (each in the Build 7 report):
     a typed entry is an ordinary box (any expression, as at a prompt), so
     while something is typed ◀ ▶ ▲ ▼ DEL edit THAT entry, and the arrows
     move between cells only when nothing is typed (no wrap at the edges);
     AC while typing drops the entry, AC on the grid with nothing typed does
     nothing; DEL with nothing typed does nothing; the cells show the TABLE's
     cut-off decimals and the bottom line a decimal (TABLE's measured rule);
     ▼ on an answer steps forward like = but not past the last answer; ◀ ▶
     and every other key on an answer do nothing; a Syntax / Math ERROR in
     a typed entry shows the three-line screen, Goto returns to the entry,
     AC drops it; an error from solving (a = 0, a singular system, an INEQ
     with one or no real root) shows Math ERROR, and AC or Goto go back to
     the grid with the numbers and the selected cell kept; ON goes back to
     the grid at cell a, numbers kept; EQN changes neither X, Ans nor the
     history; MODE, SETUP and CLR work on the grid and the answers and come
     back to them. */
  function startEqn(type, sign = null) {
    resetEntry();
    const T = EQN_TYPES[type];
    S.mode = type === "ineq" ? "INEQ" : "EQN"; S.menu = null;
    S.eqn = { kind: T.kind, type, rows: T.rows, cols: T.cols, sign,
      coef: Array.from({ length: T.rows }, () => Array.from({ length: T.cols }, () => mkRat(0n, 1n))),
      r: 0, c: 0, left: 0, box: [], answers: null, ai: 0, dec: false, back: null, err: null };
    eqnToGrid(false);
  }
  /* back to the grid, nothing typed (atA: on cell a) */
  function eqnToGrid(atA) {
    const E = S.eqn;
    E.answers = null; E.err = null; E.dec = false; E.box = [];
    if (atA) { E.r = 0; E.c = 0; }
    eqnSlide();
    S.cur = { box: E.box, i: 0 };
    S.result = null; S.err = false; S.errAt = null; S.afterAC = false; S.browsing = false;
    S.screen = "eqnGrid";
  }
  /* keep the selected column among the three on show */
  function eqnSlide() {
    const E = S.eqn, vis = Math.min(E.cols, EQN_VIS_COLS);
    if (E.c < E.left) E.left = E.c;
    else if (E.c > E.left + vis - 1) E.left = E.c - vis + 1;
  }
  function eqnGridKey(key) {
    const E = S.eqn, typing = !isBoxEmpty(E.box);
    if (key === "mode") return modeMenu();
    if (key === "setup") return setupMenu();
    if (key === "clr") return clrMenu();
    if (key === "ac") { if (typing) { E.box = []; S.cur = { box: E.box, i: 0 }; } return; }
    if (key === "eq") return typing ? eqnStore() : eqnSolve();
    if (key === "left" || key === "right" || key === "up" || key === "down") {
      if (typing) return key === "left" || key === "right" ? moveHoriz(key === "left" ? -1 : 1) : moveVert(key === "up" ? -1 : 1);
      if (key === "left" && E.c > 0) E.c--;
      else if (key === "right" && E.c < E.cols - 1) E.c++;
      else if (key === "up" && E.r > 0) E.r--;
      else if (key === "down" && E.r < E.rows - 1) E.r++;
      return eqnSlide();
    }
    if (key === "del") { if (typing) doDelBox(); return; }
    if (key === "eqs" || key === "colon") return;   // an "=" or ":" is not a value (as at a prompt)
    if (isEntryKey(key)) typeKey(key);
  }
  /* = with something typed: work it out, store it, move right (spec §13) */
  function eqnStore() {
    const E = S.eqn;
    let v = evalBox(E.box, { ans: S.ansVal, drg: S.drg, vars: S.vars });
    if (!isErr(v) && !Number.isFinite(toFloatV(v))) v = VERR("Math ERROR");
    if (isErr(v)) { E.err = { msg: v.msg, at: v.at || null, entry: true }; S.screen = "eqnErr"; return; }
    E.coef[E.r][E.c] = v;
    if (E.c < E.cols - 1) E.c++;
    else if (E.r < E.rows - 1) { E.r++; E.c = 0; }   // wrap to the next row's a; on the very last cell: stay
    E.box = []; S.cur = { box: E.box, i: 0 };
    eqnSlide();
  }
  /* = with nothing typed: SOLVE (spec §13, §14) */
  function eqnSolve() {
    const E = S.eqn, row0 = E.coef[0];
    const answers = E.kind === "sys" ? solveSystem(E.coef) : E.kind === "quad" ? solveQuadratic(row0)
      : E.kind === "cubic" ? solveCubic(row0) : solveIneq(row0, E.sign);
    if (!answers || !answers.every(a => okVal(a.v))) { E.err = { msg: "Math ERROR", at: null, entry: false }; S.screen = "eqnErr"; return; }
    E.answers = answers; E.ai = 0; E.dec = false;
    S.screen = "eqnAns";
  }
  function eqnAnsKey(key) {
    const E = S.eqn, last = E.answers.length - 1;
    if (key === "mode") return modeMenu();
    if (key === "setup") return setupMenu();
    if (key === "clr") return clrMenu();
    if (key === "ac") return eqnToGrid(true);
    if (key === "eq") { if (E.ai < last) { E.ai++; E.dec = false; } else eqnToGrid(true); return; }
    if (key === "down" && E.ai < last) { E.ai++; E.dec = false; }
    else if (key === "up" && E.ai > 0) { E.ai--; E.dec = false; }
    else if (key === "sd" && answerHasExact(E.answers[E.ai].v)) E.dec = !E.dec;
    // every other key, digits included: nothing (spec §13)
  }
  /* only AC, ◀ and ▶ reach here (spec §3) */
  function eqnErrKey(key) {
    const E = S.eqn, e = E.err;
    if (key !== "ac" && key !== "left" && key !== "right") return;
    if (e.entry && key !== "ac") {   // Goto: back to the typed entry, cursor just before the bad token
      E.err = null; S.screen = "eqnGrid";
      const at = e.at || { box: E.box, i: E.box.length };
      S.cur = { box: at.box, i: Math.min(at.i, at.box.length) };
      return;
    }
    eqnToGrid(false);   // AC drops a bad entry; after an error from solving, the grid as it was
  }
  function eqnGridHTML() {
    const E = S.eqn, vis = Math.min(E.cols, EQN_VIS_COLS), cols = [];
    for (let k = E.left; k < E.left + vis; k++) cols.push(k);
    const lb = E.left === 0, rb = E.left + vis === E.cols, nums = E.rows > 1;
    const numCell = html => (nums ? [{ html, cls: "lcd-tbl-n" }] : []);
    const heads = [...numCell(""), { html: "", cls: "lcd-eqn-bk" }, ...cols.map(k => ({ html: EQN_HEADS[k], cls: "" })), { html: "", cls: "lcd-eqn-bk" }];
    const body = [];
    for (let r = 0; r < E.rows; r++) {
      const edge = (r === 0 ? " lcd-eqn-t" : "") + (r === E.rows - 1 ? " lcd-eqn-b" : "");
      body.push([...numCell(String(r + 1)), { html: "", cls: "lcd-eqn-bk" + (lb ? " lcd-eqn-bl" + edge : "") },
        ...cols.map(k => ({ html: tableCellText(E.coef[r][k]), cls: r === E.r && k === E.c ? "lcd-tbl-sel" : "" })),
        { html: "", cls: "lcd-eqn-bk" + (rb ? " lcd-eqn-br" + edge : "") }]);
    }
    let html = gridHTML("lcd-tab lcd-tbl lcd-eqn", heads, body);
    if (E.kind === "ineq") html += `<div class="lcd-ineq">aX²+bX+c${escapeHtml(E.sign)}0</div>`;   // spec §14: the chosen inequality under the grid
    const typing = !isBoxEmpty(E.box);
    cursorOn = typing;
    html += typing
      ? `<div class="lcd-line lcd-eqn-in"><span class="lcd-lmark" hidden>◀</span><div class="lcd-expr">${renderBox(E.box)}</div></div>`
      : `<div class="lcd-res lcd-tbl-val">${formatDecimal(E.coef[E.r][E.c], S.fix)}</div>`;
    return html;
  }
  function eqnAnsHTML() {
    const E = S.eqn, a = E.answers[E.ai];
    cursorOn = false;
    return `<div class="lcd-line lcd-pr"><div class="lcd-expr"><span class="lcd-pr-label">${escapeHtml(a.label)}</span></div></div>`
      + `<div class="lcd-res lcd-eqn-val">${answerHTML(a.v, E.dec, S.fix)}</div>`;
  }
  /* a long answer (a decimal complex root) steps its font down until it fits */
  function fitAnswer() {
    const r = main.querySelector(".lcd-eqn-val");
    if (!r) return;
    for (let f = 22; r.scrollWidth > r.clientWidth + 0.5 && f >= 12; f -= 2) r.style.fontSize = f + "px";
  }

  // ---- key dispatch ----
  // SHIFT functions that do nothing: the ones skipped as not school use
  // (d/dx, Σ, FACT, ←). SHIFT is still consumed, as on the device. (SHIFT
  // x^ = ˣ√ is live since Build 2; SHIFT ×10^x = π since Build 3; Build 4
  // made SHIFT log, ln, x⁻¹, ÷, ×, (, hyp, ▫/▫ and S⇔D live; Build 5 made
  // SHIFT CALC = SOLVE live; Build 10 made SHIFT ) = ";" live.)
  const NOOP_SHIFT = new Set(["intdx", "logbox", "dms", "eng"]);
  /* Build 4, her ruling "not school use, leave those keys doing nothing":
     Pol (SHIFT +), Rec (SHIFT −), CONST (SHIFT 7), CONV (SHIFT 8), Rnd
     (SHIFT 0), Ran# (SHIFT ,), DRG▶ (SHIFT Ans) and INS (SHIFT DEL). Before
     this they typed the plain key. Only on the COMP screen: in the STAT data
     grid and the menus they pass through exactly as before. */
  const SKIP_SHIFT_COMP = new Set(["plus", "minus", "d7", "d8", "d0", "dot", "ans", "del"]);
  /* The three-line error screen (Build 2, spec §3) is up: a COMP-engine
     error on the COMP screen. Build 8: a STAT read-off with no data is an
     ordinary Math ERROR on this screen now (it had a one-line look before). */
  const onErrScreen = () => (S.screen === "comp" && S.err && S.result != null)
    || (S.screen === "prompt" && !!S.prompt && !!S.prompt.err)   // Build 5: an error in a value typed at a prompt
    || (S.screen === "tblErr" && !!S.tbl && !!S.tbl.err)         // Build 6: Insufficient MEM (and Syntax / Math ERROR) when the table is made
    || (S.screen === "eqnErr" && !!S.eqn && !!S.eqn.err);        // Build 7: an error in a typed coefficient, or Math ERROR from solving
  /* the screens a function or value is typed on: ALPHA types its letter
     and the skipped SHIFT keys type nothing there (Build 6 adds f(X)=,
     Build 7 the EQN / INEQ coefficient grid) */
  const typingScreen = () => S.screen === "comp" || S.screen === "prompt" || S.screen === "tblF" || S.screen === "eqnGrid";
  function press(id) {
    /* On an error screen ONLY AC, ◀ and ▶ do anything; every other key is
       ignored (spec §3), including SHIFT, ALPHA, ON, DEL and the digits. */
    if (onErrScreen() && id !== "ac" && id !== "left" && id !== "right") return;
    /* SHIFT and ALPHA share one spot at the far left of the status line
       (boxed S / boxed A, spec §2). SHIFT then ALPHA = ALPHA on, SHIFT off;
       ALPHA ALPHA = off. SHIFT after ALPHA switching ALPHA off is the mirror
       of that (the spec does not cover it). */
    if (id === "shift") { S.shift = !S.shift; if (S.shift) S.alpha = false; return render(); }
    if (id === "alpha") { if (S.shift) { S.shift = false; S.alpha = true; } else S.alpha = !S.alpha; return render(); }
    if (id === "on") {
      resetEntry(); S.menu = null; S.screen = "comp"; S.shift = false; S.alpha = false; S.memPending = null;
      if (S.mode === "TABLE" && S.tbl) openTblFn("f", "start");   // Build 6: TABLE has no COMP line; ON goes back to f(X)= (Blipwork choice)
      else if (eqnMode()) eqnToGrid(true);                         // Build 7: and EQN / INEQ to the grid, cell a, numbers kept (Blipwork choice)
      return render();
    }

    /* STO / RCL waiting for a letter: the letter KEY picks the variable, no
       ALPHA needed (spec §2). Any other key cancels the STO/RCL and is then
       handled as an ordinary key (the spec does not cover that case). */
    if (S.memPending) {
      const p = S.memPending; S.memPending = null;
      if (S.screen === "comp" && LETTER_OF[id]) {
        S.shift = false; S.alpha = false;
        if (p === "sto") memKey({ k: "sto", name: LETTER_OF[id] }); else rclKey(LETTER_OF[id]);
        return render();
      }
    }

    let key = id;
    if (S.alpha) {
      /* ALPHA is ONE-SHOT: the next key types its red letter, then ALPHA is
         off. A key with no red letter types nothing (spec §2). ALPHA ×10^x
         types the constant e (Build 4, spec §9). Off the COMP screen (menus,
         the STAT data grid) the key passes through untouched, exactly as
         before ALPHA was wired. */
      S.alpha = false; S.shift = false;
      if (typingScreen()) key = LETTER_OF[id] ? "var_" + LETTER_OF[id] : (ALPHA_TOKEN[id] || "noop");   // Build 5: a letter can be typed as a prompt value too; Build 6: and into f(X)= (X is ALPHA ))
    } else if (S.shift) {
      if (id === "d9") key = "clr";
      else if (id === "d1") key = "stat";
      else if (id === "mode") key = "setup";
      else if (id === "sqrt") key = "cbrt";
      else if (id === "x2") key = "cube";
      else if (id === "pow") key = "xroot";     // SHIFT x^ = ˣ√ (Build 2)
      else if (id === "sin") key = "asin";
      else if (id === "cos") key = "acos";
      else if (id === "tan") key = "atan";
      else if (id === "rcl") key = "sto";       // SHIFT RCL = STO
      else if (id === "mplus") key = "mminus";  // SHIFT M+ = M−
      else if (id === "exp10") key = "pi";      // SHIFT ×10^x = π (Build 3, spec §9)
      else if (id === "log") key = "tenpow";    // Build 4 (spec §6, §9): SHIFT log = 10^□
      else if (id === "ln") key = "epow";       //   SHIFT ln = e^□
      else if (id === "xinv") key = "fact";     //   SHIFT x⁻¹ = x!
      else if (id === "div") key = "ncr";       //   SHIFT ÷ = nCr
      else if (id === "mult") key = "npr";      //   SHIFT × = nPr
      else if (id === "lparen") key = "pct";    //   SHIFT ( = %
      else if (id === "hyp") key = "abs";       //   SHIFT hyp = Abs
      else if (id === "frac") key = "mixed";    //   SHIFT ▫/▫ = the mixed-number template
      else if (id === "sd") key = "mixtog";     //   SHIFT S⇔D = improper ↔ mixed
      else if (id === "calc") key = "solve";    // Build 5 (spec §11): SHIFT CALC = SOLVE
      else if (id === "rparen") key = typingScreen() ? "sep" : "noop";   // Build 10 (spec §19.1): SHIFT ) = the ";" of GCD( / LCM(; off the typing screens it does nothing, as before
      else if (NOOP_SHIFT.has(id)) key = "noop";
      else if (typingScreen() && SKIP_SHIFT_COMP.has(id)) key = "noop";   // Build 5: on a prompt too; Build 6: and on f(X)=
      S.shift = false;
    }

    if (S.screen === "comp") compKey(key);
    else if (S.screen === "menu") menuKey(key);
    else if (S.screen === "statInput") statKey(key);
    else if (S.screen === "prompt") promptKey(key);   // Build 5
    else if (S.screen === "solved") solvedKey(key);
    else if (S.screen === "tblF") tblFnKey(key);      // Build 6: f(X)= / g(X)=
    else if (S.screen === "table") tblViewKey(key);
    else if (S.screen === "tblErr") tblErrKey(key);
    else if (S.screen === "eqnGrid") eqnGridKey(key);  // Build 7: EQN / INEQ
    else if (S.screen === "eqnAns") eqnAnsKey(key);
    else if (S.screen === "eqnErr") eqnErrKey(key);
    render();
  }

  const digit = id => (/^d[0-9]$/.test(id) ? +id[1] : null);
  const opChar = { plus: "+", minus: "−", mult: "×", div: "÷" };
  const ENTRY_KEYS = new Set(["dot", "neg", "plus", "minus", "mult", "div", "frac", "sqrt", "cbrt", "xroot", "x2", "cube", "pow", "sin", "cos", "tan", "asin", "acos", "atan", "lparen", "rparen", "ans", "eqs", "colon", "pi",
    "log", "ln", "logbox", "tenpow", "epow", "exp10", "econst", "xinv", "fact", "pct", "ncr", "npr", "abs", "mixed", "dms",   // second row: Build 4
    "gcd", "lcm", "sep"]);   // Build 10: GCD( and LCM( start a fresh line after a result like sin( does, and so does ";" (not measured, Blipwork choice)
  const isEntryKey = k => digit(k) != null || ENTRY_KEYS.has(k) || k.startsWith("var_");
  /* POSTFIX keys act on what is before them, so after a result they chain
     from Ans exactly like + − × ÷ do (Build 2, spec §1): x² → Ans², x^ →
     Ans^□ (cursor in the exponent), x³ → Ans³. Build 4 adds x⁻¹ (spec §9:
     2 = x⁻¹ shows Ans⁻¹ = ½), x! and % (spec §1: "postfix too and should
     chain the same way"). */
  const POSTFIX_KEYS = new Set(["x2", "cube", "pow", "xinv", "fact", "pct"]);
  /* nCr and nPr sit between two numbers like × and ÷, so after a result they
     chain from Ans the same way (AnsC): not measured, the + − × ÷ rule. */
  const BINARY_KEYS = new Set(["ncr", "npr"]);

  /* Build 5: after a CALC answer, = or CALC asks again from the first
     letter (spec §10). Keys that only change how the answer is shown keep
     that; any other key leaves CALC and then does its usual job. */
  const CALC_KEEP = new Set(["sd", "mixtog", "dms", "noop"]);
  function compKey(key) {
    if (S.calcRun) {
      if ((key === "eq" || key === "calc") && S.result != null && !S.err) return calcAsk(0);
      if (!CALC_KEEP.has(key)) S.calcRun = null;
    }
    if (key === "calc") return startCalc();
    if (key === "solve") return startSolve();
    if (key === "mode") return modeMenu();
    if (key === "setup") return setupMenu();
    if (key === "clr") return clrMenu();
    if (key === "stat") { if (statMode()) statMenu(); return; }   // Build 8: and in A+BX
    if (key === "ac") { resetEntry(); S.afterAC = true; return; }   // AC clears the screen but KEEPS the history (spec §1)
    if (key === "sd") return toggleSD();
    if (key === "mixtog") return toggleMixed();
    if (key === "dms" && S.result != null) return dmsToggle();   // °'" acts ON a result (spec §1, §9); with no result it types the mark (below)
    if (key === "eq") return doEquals();
    if (key === "up") return moveVert(-1);
    if (key === "down") return moveVert(1);
    if (key === "left") return moveHoriz(-1);
    if (key === "right") return moveHoriz(1);
    if (key === "sto" || key === "rcl") { S.memPending = key; return; }   // the word STO / RCL shows; the next letter key finishes it
    if (key === "mplus") return memKey({ k: "mplus" });
    if (key === "mminus") return memKey({ k: "mminus" });
    if (key === "noop") return;

    /* DEL after a result does NOTHING at all, the screen is unchanged (spec
       §1; it used to clear the line). Build 8: a pasted STAT token is an
       ordinary token, so DEL deletes it like any other (before, DEL cleared
       the fixed read-off line). */
    if (key === "del") {
      if (S.result != null) return;
      doDelBox(); return;
    }

    // device-verified: pressing any entry key after a result (or a pasted
    // stat token) replaces the line with a fresh one — EXCEPT a binary
    // operator (+ − × ÷), which chains from the answer instead: the fresh
    // line starts "Ans" followed by that operator (device-verified: after
    // 3+4=, pressing + shows "Ans+"). Build 2: a POSTFIX key chains the same
    // way after a COMP result (spec §1). Digits, ALPHA letters, prefix keys
    // (√, sin, (, (−) ...) and the ▫/▫ and ˣ√ templates keep the full reset.
    // Build 8: a STAT read-off is an ordinary answer in Ans now, so postfix
    // keys chain from it too (x̄ = then x² gives Ans², the read-off squared).
    if (S.result != null && isEntryKey(key)) {
      const chain = !!opChar[key] || BINARY_KEYS.has(key) || POSTFIX_KEYS.has(key);
      resetEntry();
      if (chain) insertBoxToken({ k: "ans" });   // the key itself goes in below, right after "Ans"
    }
    return typeKey(key);
  }
  /* Type one entry key at the cursor (S.cur). Shared by the calculation
     line and the Build 5 prompt screen, whose typed value is a box too. */
  function typeKey(key) {
    if (key.startsWith("var_")) return insertBoxToken({ k: "var", name: key.slice(4) });
    if (key === "eqs") return insertBoxToken({ k: "eqs" });
    if (key === "colon") return insertBoxToken({ k: "colon" });

    const d = digit(key);
    if (d != null) return insertBoxToken({ k: "d", v: String(d) });
    if (key === "dot") return insertBoxToken({ k: "c" });
    if (key === "neg") return insertBoxToken({ k: "op", v: "−" });
    if (opChar[key]) return insertBoxToken({ k: "op", v: opChar[key] });
    // ▫/▫ grabs the operand before the cursor as its numerator (spec §8); √ and ³√ do NOT grab (9 √ → 9√□)
    if (key === "frac") return insertTemplate({ k: "frac", num: [], den: [] }, "num", { into: "num", enter: "den" });
    if (key === "sqrt") return insertTemplate({ k: "rad", deg: 2, body: [] }, "body");
    if (key === "cbrt") return insertTemplate({ k: "rad", deg: 3, body: [] }, "body");
    // ˣ√ (SHIFT x^): index box first; an operand before the cursor becomes the INDEX (5 SHIFT x^ → ⁵√□)
    if (key === "xroot") return insertTemplate({ k: "xrt", idx: [], body: [] }, "idx", { into: "idx", enter: "body" });
    if (key === "x2") return insertBoxToken({ k: "sq" });
    if (key === "cube") return insertBoxToken({ k: "cb" });
    if (key === "pow") return insertTemplate({ k: "pow", exp: [] }, "exp");
    if (key === "sin" || key === "cos" || key === "tan") return insertBoxToken({ k: "func", name: key, inv: false });
    if (key === "asin") return insertBoxToken({ k: "func", name: "sin", inv: true });
    if (key === "acos") return insertBoxToken({ k: "func", name: "cos", inv: true });
    if (key === "atan") return insertBoxToken({ k: "func", name: "tan", inv: true });
    if (key === "lparen") return insertBoxToken({ k: "(" });
    if (key === "rparen") return insertBoxToken({ k: ")" });
    if (key === "ans") return insertBoxToken({ k: "ans" });
    if (key === "pi") return insertBoxToken({ k: "pi" });
    /* ---- Build 4 (spec §6–§9). Prefix keys and templates do not grab what
       is before them (only ▫/▫ and ˣ√ were measured grabbing): 2 log(100 is
       2 × log(100. The mixed-number template does not grab either (spec §8
       does not say it does): its whole box comes first, empty. */
    if (key === "log" || key === "ln") return insertBoxToken({ k: "func", name: key, inv: false });
    if (key === "logbox") return insertTemplate({ k: "logb", base: [], body: [] }, "base");
    if (key === "tenpow") return insertTemplate({ k: "tenpow", exp: [] }, "exp");
    if (key === "epow") return insertTemplate({ k: "epow", exp: [] }, "exp");
    if (key === "exp10") return insertBoxToken({ k: "x10" });   // ONE small "×10" glyph; the power digits are typed inline after it
    if (key === "econst") return insertBoxToken({ k: "econst" });
    if (key === "xinv") return insertBoxToken({ k: "inv" });
    if (key === "fact") return insertBoxToken({ k: "fact" });
    if (key === "pct") return insertBoxToken({ k: "pct" });
    if (key === "ncr") return insertBoxToken({ k: "comb", v: "C" });
    if (key === "npr") return insertBoxToken({ k: "comb", v: "P" });
    if (key === "abs") return insertTemplate({ k: "abs", body: [] }, "body");
    if (key === "mixed") return insertTemplate({ k: "mixed", whole: [], num: [], den: [] }, "whole");
    if (key === "dms") return insertBoxToken({ k: "dms" });
    /* ---- Build 10 (spec §19.1): GCD( and LCM( are function openers like
       sin( (they multiply implicitly the same way, 2GCD(4;6 = 4: not
       measured); ";" is its own token, read only inside them ---- */
    if (key === "gcd" || key === "lcm") return insertBoxToken({ k: "func", name: key.toUpperCase(), inv: false });
    if (key === "sep") return insertBoxToken({ k: "sep" });
  }

  function menuKey(key) {
    const m = S.menu;
    if (key === "ac") return closeMenu();
    if (key === "down" && m.onDown) return m.onDown();
    if (key === "up" && m.onUp) return m.onUp();
    if (key === "eq" && m.onEq) return m.onEq();
    const d = digit(key);
    if (d != null && m.onNum) m.onNum(d);
  }

  function statKey(key) {
    /* Build 9 (spec §19.2): SHIFT 1 here is the short menu (1:Type 2:Data /
       3:Edit). MODE, SETUP and CLR open from the editor too and come back to
       it; they drop a half-typed number first, as AC does (Blipwork choice,
       not device-measured). SHIFT 1 leaves it alone, as before. */
    if (key === "stat") return statEditMenu();
    if (key === "mode" || key === "setup" || key === "clr") {
      S.cell = "";
      return key === "mode" ? modeMenu() : key === "setup" ? setupMenu() : clrMenu();
    }
    /* AC: go to the calculation screen. Build 8: that screen is EMPTY
       (resetEntry), as it was meant to be; before, a line typed before MODE 3
       could still be sitting under it. Build 9 (spec §19.2): AC while typing
       CANCELS the typing (the cell keeps its old value, the editor stays);
       before, AC stored the typed digits and left. */
    if (key === "ac") {
      if (S.cell !== "") { S.cell = ""; return; }
      resetEntry(); S.screen = "comp"; return;
    }
    if (key === "eq" || key === "down") {
      // with something typed: store it and step on. With nothing typed: just move.
      /* Build 9: ▼ wraps from the open row to row 1 (statNav); = with nothing
         typed on the open row stays put, as it always did (the wrap was
         measured for ▼ only). */
      if (S.cell !== "" && S.cell !== "-") commitCell();
      else if (key === "eq" && S.row >= gridRows().length) return;
      else statNav("down");
      return;
    }
    if (key === "up" || key === "left" || key === "right") return statNav(key);
    /* DEL while typing removes the last typed character (as before; DEL while
       typing was not measured). Build 9 (spec §19.2): DEL with nothing typed
       deletes the whole row. */
    if (key === "del") { if (S.cell !== "") S.cell = S.cell.slice(0, -1); else gridDeleteRow(); return; }
    if (key === "neg") { S.cell = S.cell.startsWith("-") ? S.cell.slice(1) : "-" + S.cell; return; }
    if (key === "dot") { S.cell += ","; return; }
    const d = digit(key);
    if (d != null) S.cell += d;
  }

  // ---- render ----
  function renderNode(node) {
    switch (node.k) {
      case "d": return escapeHtml(node.v);
      case "c": return ",";
      case "op": return escapeHtml(node.v);
      case "(": return "(";
      case ")": return ")";
      case "sq": return "²";
      case "cb": return "³";
      case "ans": return "Ans";
      case "pi": return "π";
      case "var": return escapeHtml(node.name);
      case "eqs": return "=";
      case "colon": return ":";
      case "sep": return ";";   // Build 10: the GCD( / LCM( separator (SHIFT ))
      case "sto": return "→" + escapeHtml(node.name);
      case "mplus": return "M+";
      case "mminus": return "M−";
      case "stat": return statGlyph(node.v);   // a pasted STAT value (Build 8): x̄ overlined, x̂ ŷ with a hat
      case "func": return escapeHtml(node.name) + (node.inv ? "⁻¹" : "") + "(";
      case "frac": return `<span class="calc-frac"><span class="calc-frac-num">${renderBox(node.num)}</span><span class="calc-frac-bar"></span><span class="calc-frac-den">${renderBox(node.den)}</span></span>`;
      case "rad": return `<span class="calc-rad">${node.deg === 3 ? '<sup class="calc-rad-deg">3</sup>' : ""}<span class="calc-rad-sign">√</span><span class="calc-rad-body">${renderBox(node.body)}</span></span>`;
      case "xrt": return `<span class="calc-rad calc-xrt"><sup class="calc-rad-deg calc-rad-idx">${renderBox(node.idx)}</sup><span class="calc-rad-sign">√</span><span class="calc-rad-body">${renderBox(node.body)}</span></span>`;
      case "pow": return `<sup class="calc-pow-exp">${renderBox(node.exp)}</sup>`;
      // ---- Build 4 ----
      case "econst": return "e";
      case "x10": return '<span class="calc-x10">×10</span>';
      case "inv": return "⁻¹";
      case "fact": return "!";
      case "pct": return "%";
      case "comb": return `<span class="calc-comb">${node.v}</span>`;   // the special C / P sign of nCr / nPr
      case "logb": return `<span class="calc-logb">log<span class="calc-logb-base">${renderBox(node.base)}</span>(<span class="calc-logb-body">${renderBox(node.body)}</span>)</span>`;
      case "abs": return `<span class="calc-abs"><span class="calc-abs-body">${renderBox(node.body)}</span></span>`;   // straight bars = the body's left and right borders, so they grow with what is inside
      case "tenpow": return `<span class="calc-tenpow">10<sup class="calc-pow-exp">${renderBox(node.exp)}</sup></span>`;
      case "epow": return `<span class="calc-tenpow">e<sup class="calc-pow-exp">${renderBox(node.exp)}</sup></span>`;
      case "mixed": return `<span class="calc-mixed"><span class="calc-mixed-whole">${renderBox(node.whole)}</span><span class="calc-frac"><span class="calc-frac-num">${renderBox(node.num)}</span><span class="calc-frac-bar"></span><span class="calc-frac-den">${renderBox(node.den)}</span></span></span>`;
      default: return "";
    }
  }
  let cursorOn = true;   // the cursor hides while a result is on screen; ◀/▶ bring it back (Build 1)
  /* Build 4: one °'" key types every mark; what it SHOWS depends on its
     place in the number: 30 °'" 15 °'" shows 30°15' (spec §9), a third mark
     shows ". */
  const DMS_MARKS = ["°", "'", "\""];
  function renderBox(box) {
    let html = "", dmsN = 0;
    for (let idx = 0; idx <= box.length; idx++) {
      if (cursorOn && box === S.cur.box && idx === S.cur.i) html += '<span class="calc-cursor"></span>';
      if (idx >= box.length) continue;
      const node = box[idx];
      if (node.k === "dms") { html += DMS_MARKS[Math.min(dmsN, 2)]; dmsN++; continue; }
      if (node.k !== "d" && node.k !== "c") dmsN = 0;
      html += renderNode(node);
    }
    if (box.length === 0 && box.__parent) html += '<span class="calc-slot"></span>';   // empty template box: dotted placeholder
    return html;
  }

  /* Status line (spec §16, last bullet): boxed S / A at the far left, then
     M, STO, RCL, STAT (FREQ is Blipwork's own STAT tag), FIX, and on the right D
     next to Math, with the ▲ / ▼ / ▲▼ history arrow at the far right. Every
     mark has its OWN fixed-width slot, like the segments of the real LCD, so
     a mark switching on or off never shifts any other mark sideways. */
  function renderInd() {
    const comp = S.screen === "comp" || S.screen === "prompt" || S.screen === "solved"   // Build 5: D and Math stay lit on the CALC / SOLVE screens
      || S.screen === "tblF" || S.screen === "tblErr"    // Build 6: and on f(X)= and its error screen; the table grid, like the STAT grid, shows neither (spec silent)
      || S.screen === "eqnAns" || S.screen === "eqnErr"; // Build 7: and on an EQN / INEQ answer and its error screen; the coefficient grid shows neither, like the other grids (spec silent)
    const sa = S.shift ? "S" : S.alpha ? "A" : "";
    const slot = (name, txt) => `<span class="ind-${name}">${txt}</span>`;
    ind.innerHTML =
      slot("sa", sa ? `<b>${sa}</b>` : "") +
      slot("m", isZeroAny(S.vars.M) ? "" : "M") +
      slot("sto", S.memPending === "sto" ? "STO" : "") +
      slot("rcl", S.memPending === "rcl" ? "RCL" : "") +
      slot("stat", statMode() ? "STAT" : "") +   // Build 8: A+BX is STAT too
      slot("freq", S.mode === "STAT" && S.freqOn ? "FREQ" : "") +
      slot("fix", S.fix != null ? "FIX" : "") +   // Build 4 (spec §7, §16)
      `<span class="ind-gap"></span>` +
      slot("drg", comp ? S.drg : "") +
      slot("math", comp ? "Math" : "") +
      slot("hist", histIndicator());
  }

  function render() {
    renderInd();

    if (onErrScreen()) {
      /* Build 2 (spec §3): exactly three lines, and nothing else on screen.
         The message keeps the .lcd-res class it always had, so anything
         that reads the result line still reads "Syntax ERROR". Build 5: the
         same screen for Can't Solve and for an error in a prompt value. */
      const msg = S.screen === "prompt" ? S.prompt.err : S.screen === "tblErr" ? S.tbl.err.msg : S.screen === "eqnErr" ? S.eqn.err.msg : S.result;   // Build 6: Insufficient MEM; Build 7: EQN
      main.innerHTML = `<div class="lcd-err"><div class="lcd-res lcd-err-msg">${escapeHtml(msg)}</div>`
        + `<div class="lcd-err-line">[AC] :Cancel</div><div class="lcd-err-line">[◀][▶]:Goto</div></div>`;
      exprScroll = 0;
    } else if (S.screen === "prompt") {   // Build 5: X?, Solve for X (and later Start?, End?, Step?)
      main.innerHTML = promptHTML(S.prompt);
      keepCursorInView();
    } else if (S.screen === "solved") {   // Build 5: the three-line SOLVE answer
      main.innerHTML = solvedHTML();
      exprScroll = 0;
    } else if (S.screen === "comp") {
      cursorOn = S.result == null;
      const exprHTML = renderBox(S.box);
      // AC / empty screen = an empty line plus the cursor, NO "0" anywhere (spec §1)
      // Build 8: after a STAT value is pasted, the previous answer stays until = (S.held)
      const resHTML = S.result != null ? S.result : (S.held || "");
      main.innerHTML = `<div class="lcd-line"><span class="lcd-lmark" hidden>◀</span><div class="lcd-expr">${exprHTML}</div></div><div class="lcd-res">${resHTML}</div>`;
      keepCursorInView();
    } else if (S.screen === "menu") {
      const m = S.menu;
      let html = m.title ? `<div class="lcd-title">${m.title}</div>` : "";
      // Build 7: list = one item per line (the EQN types, spec §13 "four plain lines")
      // boxed = the digits in reversed boxes (the MODE menu, spec §16; Build 8: SETUP too)
      // Build 8: packed = two plain columns with the rows packed (MODE 3's eight STAT types)
      if (m.items && m.items.length) html += `<div class="lcd-menu${m.list ? " lcd-menu-list" : ""}${m.boxed ? " lcd-menu-boxed" : ""}${m.packed ? " lcd-menu-packed" : ""}">` + m.items.map(([n, l]) => `<span class="lcd-mi">${m.boxed ? `<span class="lcd-mi-n">${n}</span>` : n}:${l}</span>`).join("") + `</div>`;
      if (m.note) html += `<div class="lcd-note">${m.note}</div>`;
      if (m.notes) html += `<div class="lcd-note">${m.notes.map(t => `<div>${escapeHtml(t)}</div>`).join("")}</div>`;   // Build 8: Reset …? / [=] :Yes / [AC] :Cancel (spec §16), one per line
      if (m.done) html += `<div class="lcd-done">${m.done.map(t => `<div>${escapeHtml(t)}</div>`).join("")}</div>`;      // Build 8: Reset All / Press [AC] key, centred (spec §16)
      if (m.pages && m.page < m.pages - 1) html += `<div class="lcd-more">▼</div>`;
      if (m.upMark && m.page > 0) html += `<div class="lcd-more">▲</div>`;   // Build 7: MODE page 2 shows ▲ (spec §16; SETUP's page 2 was not described, so unchanged)
      main.innerHTML = html;
    } else if (S.screen === "statInput") {
      main.innerHTML = renderTable();
      if (S.cell !== "") keepCursorInView(); else exprScroll = 0;   // Build 9: the typed number, bottom left
    } else if (S.screen === "tblF") {   // Build 6: f(X)= / g(X)=
      main.innerHTML = tblFnHTML();
      keepCursorInView();
    } else if (S.screen === "table") {
      main.innerHTML = tblHTML();
    } else if (S.screen === "eqnGrid") {   // Build 7: EQN / INEQ coefficients
      main.innerHTML = eqnGridHTML();
      if (!isBoxEmpty(S.eqn.box)) keepCursorInView(); else exprScroll = 0;
    } else if (S.screen === "eqnAns") {
      main.innerHTML = eqnAnsHTML();
      fitAnswer();
    }
  }
  /* Long input (Build 2, spec §1): the entry line scrolls left so the
     cursor stays in view, and a ◀ marker at the left edge shows that
     content is hidden. The line is redrawn on every key, so the scroll
     offset is kept here between draws. With a result on screen (no
     cursor) the line shows from its start, as it always did. */
  let exprScroll = 0;
  function keepCursorInView() {
    const ex = main.querySelector(".lcd-expr"), mark = main.querySelector(".lcd-lmark");
    const cur = ex.querySelector(".calc-cursor");
    if (!cur || ex.scrollWidth <= ex.clientWidth) exprScroll = 0;
    else {
      ex.scrollLeft = exprScroll;
      mark.hidden = false;
      const room = mark.offsetWidth + 1;   // keep the cursor clear of the ◀ marker
      const er = ex.getBoundingClientRect(), cr = cur.getBoundingClientRect();
      if (cr.right > er.right - 1) ex.scrollLeft += cr.right - er.right + 1;
      else if (ex.scrollLeft > 0 && cr.left < er.left + room) ex.scrollLeft -= er.left + room - cr.left;
      exprScroll = ex.scrollLeft;
    }
    ex.scrollLeft = exprScroll;
    mark.hidden = !(exprScroll > 0.5);
  }
  /* the STAT data grid. Build 6: drawn by gridHTML (shared with TABLE); the
     HTML it gives is exactly what this function built by hand before.
     Build 9 (spec §19.2): drawn like the TABLE screen (Build 6's small
     .lcd-tbl cells, so the LCD keeps its plain height): THREE rows on show,
     scrolled to keep the cursor row in view; the selected cell INVERTED
     (.lcd-tbl-sel: a solid dark cell with light digits, steady); its full
     value bottom RIGHT (the TABLE's bottom line; Fix applies there as it does
     on the TABLE, not device-measured for STAT). While a number is being
     typed the bottom right is empty and the number shows bottom LEFT with a
     blinking cursor after it (the EQN grid's .lcd-eqn-in line). The selected
     cell KEEPS its old value until = stores the new one (spec §19.8,
     measured: the typed number shows bottom left only). Row
     numbers in the TABLE's narrow column; rows past the open row are blank.
     Negative numbers show the real minus sign. */
  function renderTable() {
    if (S.mode === "REG") return renderRegTable();
    const freq = S.freqOn;
    return statGridHTML(freq ? ["X", "FREQ"] : ["X"], d => (freq ? [d.x, d.f] : [d.x]));
  }
  /* Build 8 (spec §15): the A+BX grid, X | Y, in the 1-VAR grid's look.
     Build 9 (spec §19.2): with FREQ on it is X | Y | FREQ (measured); each
     pair then counts FREQ times (regRows, not device-measured). */
  function renderRegTable() {
    const freq = S.freqOn;
    return statGridHTML(freq ? ["X", "Y", "FREQ"] : ["X", "Y"], d => (freq ? [d.x, d.y, d.f ?? 1] : [d.x, d.y]));
  }
  const STAT_VISIBLE = 3;   // spec §19.2: "the screen shows three data rows"
  const statCellText = v => (v == null ? "" : fmtNum(v).replace("-", "−"));
  function statGridHTML(heads, valsOf) {
    const rows = gridRows(), open = rows.length;
    /* keep the cursor on the grid (a SETUP FREQ change made from the editor
       can take a column away), and its row among the three on show */
    if (S.col > heads.length - 1) S.col = heads.length - 1;
    if (S.row > open) S.row = open;
    let top = Math.min(S.gridTop, Math.max(0, open - STAT_VISIBLE + 1));
    if (S.row < top) top = S.row;
    if (S.row > top + STAT_VISIBLE - 1) top = S.row - STAT_VISIBLE + 1;
    S.gridTop = top;
    const typing = S.cell !== "", typed = escapeHtml(S.cell.replace("-", "−"));
    const body = [];
    for (let r = top; r < top + STAT_VISIBLE; r++) {
      const d = rows[r], vals = d ? valsOf(d) : [];
      body.push([{ html: r <= open ? String(r + 1) : "", cls: "lcd-tbl-n" },
        ...heads.map((_, c) => {
          const sel = r === S.row && c === S.col;
          /* The selected cell shows the value ALREADY in that cell, also while a
             new number is being typed (spec §19.8, measured), so the learner can
             see which value they are about to replace. */
          return { html: statCellText(vals[c]), cls: sel ? "lcd-tbl-sel" : "" };
        })]);
    }
    const html = gridHTML("lcd-tab lcd-tbl lcd-stat", [{ html: "", cls: "lcd-tbl-n" }, ...heads.map(h => ({ html: h }))], body);
    if (typing) return html + `<div class="lcd-line lcd-eqn-in"><span class="lcd-lmark" hidden>◀</span><div class="lcd-expr">${typed}<span class="calc-cursor"></span></div></div>`;
    const d = rows[S.row], v = d ? valsOf(d)[S.col] : null;
    return html + `<div class="lcd-res lcd-tbl-val">${v == null ? "" : formatDecimal(VFLOAT(v), S.fix)}</div>`;
  }

  render();
  const api = { press, state: () => S };
  host.__CALC__ = api;
  return api;
}

/* full-screen overlay wrapper.
   The calculator is a module-level singleton: closing it detaches the
   scrim from the DOM instead of destroying it, so the whole closure state
   (S, the COMP engine, the stats table, listeners) survives a close —
   reopening re-attaches the SAME element and the screen is exactly as the
   learner left it. State only resets on a page reload (that's deliberate:
   a real fx-991ZA remembers its screen when you put it down). */
let calcScrim = null;
export function openCalculator() {
  if (calcScrim) {
    if (!calcScrim.isConnected) document.body.appendChild(calcScrim);   // foreman review fix: the floating calc button (z 75) sits above this scrim (z 50), so without this re-attach guard a second tap would stack a second calculator
    return;
  }
  const scrim = el("div", "modal-scrim calc-scrim");
  const box = el("div", "calc-wrap");
  const head = el("div", "calc-head");
  head.innerHTML = `<span class="calc-name">CASIO fx-991ZA Plus II</span>`;
  const close = el("button", "calc-close", "✕");
  head.appendChild(close);
  box.appendChild(head);
  const host = el("div", "");
  box.appendChild(host);
  mountCalculator(host);
  scrim.appendChild(box);
  const dismiss = () => scrim.remove();   // detach only — the singleton keeps its state, remove() here means "hide"
  close.addEventListener("click", dismiss);
  scrim.addEventListener("click", e => { if (e.target === scrim) dismiss(); });
  document.body.appendChild(scrim);
  calcScrim = scrim;
}
