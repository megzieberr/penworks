# PenWorks pw-v8v checks: the calculator's face redrawn as her fx-991ZA, its colours hers (calculator item 3).
# Run: python tests/test_calcface.py        (local mode only: ?local=1, Supabase is never touched)
# The card head says fx-991ZA (no brand name anywhere on the card); the eight colour slots (--cf-*) have the same defaults in
# css/app.css and js/calcpanel.js; every key's own label reads against its face (4.5:1 or better) with the defaults and after
# a light number-key colour flips its ink; the small words above a key are print (a tap there is not that key) and never
# overlap, MODE and SETUP included; the colour panel opens and closes from the head (and does not drag the card); a change
# goes on #calcCard live, the body follows, pw.calcFace keeps it over a reload, and the reset clears it; a TABLE screen and the
# SETUP menu draw with the screen's own colours (none of calc.css's old green-grey left on the LCD).
# Screenshots of the card go to _build/face/ (face-1.0, face-1.6, face-2.5, face-table-1.6, face-menu-1.6, face-panel).
import sys, subprocess, time, pathlib, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8803
LOCAL = f"http://127.0.0.1:{PORT}/?local=1"
SHOTS = ROOT / "_build" / "face"

res = []
group = ["?"]
def check(n, ok, info=""):
    res.append((group[0], n, bool(ok), info))

DEFAULTS = {"body": "#ecedef", "lcd": "#cfd4cc", "lcdInk": "#1e2320", "fn": "#f8f8f9", "num": "#5b6066",
            "ac": "#9ccc3c", "shift": "#e8a21c", "alpha": "#d9484a"}
VARS = {"body": "--cf-body", "lcd": "--cf-lcd", "lcdInk": "--cf-lcd-ink", "fn": "--cf-fn", "num": "--cf-num",
        "ac": "--cf-ac", "shift": "--cf-shift", "alpha": "--cf-alpha"}
OLD = ["rgb(184, 198, 174)", "rgb(28, 36, 26)", "rgb(108, 122, 100)", "rgb(58, 68, 52)", "rgb(22, 26, 34)"]   # calc.css's LCD colours

SEED = """() => {
  localStorage.clear();
  const t = '2026-11-05T08:00:00Z';
  localStorage.setItem('penworks.local.v2', JSON.stringify({
    folders: [{ id: 'f1', parent_id: null, name: 'Calc', colour: null, position: 0, deleted_at: null, created_at: t, updated_at: t }],
    notes: [{ id: 'n1', folder_id: 'f1', name: 'Face', pinned: false, cover_path: null, deleted_at: null, created_at: t, updated_at: t }],
    pages: [{ id: 's0', note_id: 'n1', position: 0, orientation: 'portrait', background: 'grid', deleted_at: null, created_at: t, updated_at: t }] }));
}"""
# a colour as [r, g, b, a] (rgb(), rgba() or color(srgb ...) from a color-mix)
RGB_JS = """const rgb = (s) => { let m = s.match(/^rgba?\\(([^)]+)\\)/);
  if (m) { const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
  m = s.match(/^color\\(srgb ([^)]+)\\)/);
  if (m) { const p = m[1].split(/[ \\/]+/).filter(Boolean).map(Number); return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1]; }
  return null; };
const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };"""
CONTRAST_JS = "() => { " + RGB_JS + """
  const out = [];
  for (const k of document.querySelectorAll('#calcCard .calc-key, #calcCard .calc-dpad-btn')) {
    const m = k.querySelector('.kmain') || k;
    if (getComputedStyle(m).position === 'absolute') continue;   // a top-row pill: its word is print on the body, not on the key
    const fg = rgb(getComputedStyle(m).color), bg = rgb(getComputedStyle(k).backgroundColor);
    out.push([k.dataset.keyid, Math.round(ratio(fg, bg) * 100) / 100]);
  }
  return out; }"""
VARS_JS = """(names) => { const c = document.getElementById('calcCard'), s = getComputedStyle(c);
  return Object.fromEntries(names.map((n) => [n, s.getPropertyValue(n).trim().toLowerCase()])); }"""
BG = "(sel) => getComputedStyle(document.querySelector(sel)).backgroundColor"
COL = "(sel) => getComputedStyle(document.querySelector(sel)).color"
STORED = "() => localStorage.getItem('pw.calcFace')"
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect();
  return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; }"""
# every word printed above a key (shift, alpha, and the top row's own words): pairs of them that overlap or touch (< 1 px)
OVERLAP_JS = """() => { const sel = '#calcCard .calc-key .ksh, #calcCard .calc-key .kred, #calcCard .calc-key:is(.k-shift, .k-alpha, [data-keyid="mode"], [data-keyid="on"]) .kmain';
  const L = [...document.querySelectorAll(sel)].map((e) => ({ id: e.closest('.calc-key').dataset.keyid + ':' + e.textContent, r: e.getBoundingClientRect() }));
  const bad = [];
  for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
    const a = L[i].r, b = L[j].r;
    if (a.left < b.right + 1 && b.left < a.right + 1 && a.top < b.bottom && b.top < a.bottom) bad.push([L[i].id, L[j].id]);
  }
  return { n: L.length, bad }; }"""
# a tap on the middle of a printed word: which key (if any) it lands on
PRINT_HIT_JS = """() => { const out = [];
  for (const e of document.querySelectorAll('#calcCard .calc-key .ksh, #calcCard .calc-key .kred')) {
    const r = e.getBoundingClientRect(), hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    const k = hit && hit.closest('.calc-key');
    if (k && k === e.closest('.calc-key')) out.push(k.dataset.keyid + ':' + e.textContent);
  }
  return out; }"""
KEYHIT_JS = """() => [...document.querySelectorAll('#calcCard [data-keyid]')].filter((k) => {
  const r = k.getBoundingClientRect(), e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !e || e.closest('[data-keyid]') !== k; }).map((k) => k.dataset.keyid)"""
OLD_JS = "(old) => { const bad = [];" + """
  for (const e of document.querySelectorAll('#calcCard .calc-lcd, #calcCard .calc-lcd *')) {
    const s = getComputedStyle(e);
    const cs = [s.color, s.backgroundColor, s.borderTopColor, s.borderBottomColor, s.borderLeftColor, s.borderRightColor];
    const w = [1, 1, parseFloat(s.borderTopWidth), parseFloat(s.borderBottomWidth), parseFloat(s.borderLeftWidth), parseFloat(s.borderRightWidth)];
    cs.forEach((c, i) => { if (w[i] > 0 && old.includes(c)) bad.push([e.className || e.tagName, i, c]); });
  }
  return bad; }"""

def ready(pg): pg.wait_for_selector("body[data-ready='1']", timeout=20000)
def open_note(pg):
    pg.locator(".nrow").first.click(); pg.wait_for_selector("#noteView:not([hidden])"); pg.wait_for_timeout(250)
def open_calc(pg):
    pg.click("#toolsBtn"); pg.wait_for_selector("#calcCard:not([hidden])"); pg.wait_for_timeout(150)
def keys(pg, *ids):
    for k in ids: pg.click(f'#calcCard [data-keyid="{k}"]'); pg.wait_for_timeout(25)
def rect(pg, sel): return pg.evaluate(RECT, sel)
def shot(pg, name):
    pg.wait_for_timeout(250)                                              # the panel's slide-in and any key press are over
    r = rect(pg, "#calcCard")
    pg.screenshot(path=str(SHOTS / name), clip={"x": max(0, r["l"] - 12), "y": max(0, r["t"] - 12), "width": r["w"] + 24, "height": r["h"] + 24})
def set_input(pg, k, v):
    pg.evaluate("([k, v]) => { const i = document.querySelector(`#calcCard .calcFace input[data-slot='${k}']`); i.value = v;"
                " i.dispatchEvent(new Event('input', { bubbles: true })); }", [k, v])
def hexrgb(h): return f"rgb({int(h[1:3], 16)}, {int(h[3:5], 16)}, {int(h[5:7], 16)})"
def with_scale(b, s, h=1700):
    ctx = b.new_context(viewport={"width": 1400, "height": h})
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(LOCAL); ready(pg); pg.evaluate(SEED)
    pg.evaluate("(s) => localStorage.setItem('pw.calc', JSON.stringify({ scale: s, left: 40, top: 20 }))", s)
    pg.reload(); ready(pg); open_note(pg); open_calc(pg)
    return ctx, pg, errs

SHOTS.mkdir(parents=True, exist_ok=True)
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=str(ROOT),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # ------------------------------------------------------------ 1. the head and the fx-991ZA defaults, at 1.6x
        group[0] = "head + defaults"
        ctx, pg, errs = with_scale(b, 1.6)
        s = float(pg.evaluate("getComputedStyle(document.getElementById('calcCard')).getPropertyValue('--calc-s')"))
        check("the card opened at 1.6x", abs(s - 1.6) < 1e-6, s)
        name = pg.inner_text("#calcCard .calc-name").strip()
        check("the head says fx-991ZA", name == "fx-991ZA", name)
        text = pg.evaluate("document.getElementById('calcCard').textContent")
        check("no 'Casio' anywhere on the card (head, panel, reset)", "casio" not in text.lower(), text[:120])
        v = pg.evaluate(VARS_JS, list(VARS.values()))
        check("the eight --cf-* slots are the fx-991ZA defaults (css/app.css and FACE in calcpanel.js agree)",
              all(v[VARS[k]] == DEFAULTS[k] for k in DEFAULTS), v)
        inl = pg.evaluate("document.getElementById('calcCard').style.cssText")
        check("nothing changed yet: no slot is set inline on #calcCard (only the inks and the scale)",
              all(VARS[k] + ":" not in inl.replace(" ", "") for k in DEFAULTS), inl)
        check("pw.calcFace is not stored", pg.evaluate(STORED) is None, pg.evaluate(STORED))
        bodies = {sel: pg.evaluate(BG, sel) for sel in ["#calcCard .calc-wrap", "#calcCard .calc-lcd", '#calcCard [data-keyid="sin"]',
                                                         '#calcCard [data-keyid="d7"]', '#calcCard [data-keyid="mult"]', '#calcCard [data-keyid="eq"]',
                                                         '#calcCard [data-keyid="del"]', '#calcCard [data-keyid="ac"]', '#calcCard [data-keyid="shift"]',
                                                         '#calcCard [data-keyid="up"]']}
        want = [DEFAULTS[k] for k in ["body", "lcd", "fn", "num", "num", "num", "ac", "ac", "fn", "fn"]]
        check("each part is painted from its slot (body, screen, keys, number keys, DEL and AC, SHIFT pill, an arrow)",
              list(bodies.values()) == [hexrgb(h) for h in want], bodies)
        cols = [pg.evaluate(COL, '#calcCard [data-keyid="calc"] .ksh'), pg.evaluate(COL, '#calcCard [data-keyid="calc"] .kred'),
                pg.evaluate(COL, '#calcCard [data-keyid="shift"] .kmain'), pg.evaluate(COL, '#calcCard [data-keyid="alpha"] .kmain'),
                pg.evaluate(COL, "#calcCard .calc-lcd")]
        check("shift words and the SHIFT word in --cf-shift, alpha words and ALPHA in --cf-alpha, the LCD in --cf-lcd-ink",
              cols == [hexrgb(DEFAULTS[k]) for k in ["shift", "alpha", "shift", "alpha", "lcdInk"]], cols)
        ink = pg.evaluate(VARS_JS, ["--cf-body-ink", "--cf-fn-ink", "--cf-num-ink", "--cf-ac-ink"])
        check("the inks are worked out: near-black on the light body, keys and DEL/AC, white on the grey number keys",
              ink == {"--cf-body-ink": "#1b1e22", "--cf-fn-ink": "#1b1e22", "--cf-num-ink": "#ffffff", "--cf-ac-ink": "#1b1e22"}, ink)
        con = pg.evaluate(CONTRAST_JS)
        low = [c for c in con if c[1] < 4.5]
        check(f"every key label reads 4.5:1 or better against its face ({len(con)} labels; lowest {min(c[1] for c in con)})",
              len(con) >= 44 and not low, low or con[:6])
        ff = pg.evaluate("getComputedStyle(document.querySelector('#calcCard [data-keyid=\"sin\"]')).fontFamily")
        check("the keys use the app's own sans, not the mono", "Atkinson" in ff and "Mono" not in ff, ff)
        serif = [pg.evaluate("(k) => { const s = getComputedStyle(document.querySelector(`#calcCard [data-keyid='${k}'] .kmain`)); return s.fontStyle + '|' + s.fontFamily; }", k)
                 for k in ["x2", "xinv", "pow", "exp10"]]
        check("x², x⁻¹ and x^▫ in the italic serif; ×10ˣ stays plain", all(x.startswith("italic|") and "Cambria" in x for x in serif[:3])
              and serif[3].startswith("normal|"), serif)
        ov = pg.evaluate("() => [...document.querySelectorAll('#calcCard .calc-key')].map((k) => getComputedStyle(k).overflow).filter((o) => o !== 'visible')")
        check("no key clips its words (overflow visible on every .calc-key)", not ov, ov)
        shot(pg, "face-1.6.png")

        # ------------------------------------------------------------ 2. the words above the keys
        group[0] = "print above the keys"
        o = pg.evaluate(OVERLAP_JS)
        check(f"no two printed words overlap or touch ({o['n']} words)", o["n"] >= 60 and not o["bad"], o)
        m, st, on = rect(pg, '#calcCard [data-keyid="mode"] .kmain'), rect(pg, '#calcCard [data-keyid="mode"] .ksh'), rect(pg, '#calcCard [data-keyid="on"] .kmain')
        check("MODE and SETUP share the strip without touching (MODE left, SETUP right, a gap of 1 px or more)",
              m["r"] + 1 <= st["l"] and abs(m["t"] - st["t"]) < 2, [m, st])
        check("SETUP keeps clear of ON", st["r"] + 1 <= on["l"], [st, on])
        k5 = rect(pg, '#calcCard [data-keyid="mode"]')
        check("the words sit above their key, on the body", m["b"] <= k5["t"] + 0.5 and st["b"] <= k5["t"] + 0.5, [m, st, k5])
        hits = pg.evaluate(PRINT_HIT_JS)
        check("a tap on a printed word is not a tap on that key (the words are print, not buttons)", not hits, hits)
        miss = pg.evaluate(KEYHIT_JS)
        check("every key's centre still lands on that key (the tap areas are the keys calculator.js built)", not miss, miss)
        keys(pg, "ac", "d2", "plus", "d3", "eq")
        check("a tap still types: 2+3= gives 5", pg.inner_text("#calcCard .lcd-res").strip() == "5", pg.inner_text("#calcCard .lcd-res"))

        # ------------------------------------------------------------ 3. the colour panel
        group[0] = "colour panel"
        check("the panel is shut at first; the palette button sits left of the X, 40 x 32 or bigger at 1.0x",
              pg.locator("#calcCard .calcFace").is_hidden() and pg.evaluate(
                  "() => { const b = document.querySelector('#calcCard .calcFaceBtn'), x = document.querySelector('#calcCard .calc-close');"
                  " return b.nextElementSibling === x && b.offsetWidth >= 40 && b.offsetHeight >= 32; }"))
        c0 = rect(pg, "#calcCard")
        pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(200)
        c1 = rect(pg, "#calcCard")
        rows = pg.evaluate("() => [...document.querySelectorAll('#calcCard .calcFaceRow')].map((r) => [r.querySelector('span').textContent, r.querySelector('input').type, r.querySelector('input').value])")
        check("a tap opens it: eight rows, a colour swatch each, showing the fx-991ZA values",
              pg.locator("#calcCard .calcFace").is_visible() and [r[0] for r in rows] == ["Body", "Screen", "Screen ink", "Keys", "Number keys", "DEL and AC", "SHIFT labels", "ALPHA labels"]
              and all(r[1] == "color" for r in rows) and [r[2] for r in rows] == list(DEFAULTS.values()), rows)
        check("the button shows it is open (.on, aria-expanded true)", "on" in pg.get_attribute("#calcCard .calcFaceBtn", "class").split()
              and pg.get_attribute("#calcCard .calcFaceBtn", "aria-expanded") == "true")
        check("a tap on the palette button does not drag the card (its left edge stays)", abs(c1["l"] - c0["l"]) < 0.5, [c0, c1])
        check("the panel is inside the card, under the head, and scales with it",
              pg.evaluate("() => { const p = document.querySelector('#calcCard .calcFace'); return !!p.closest('.calc-wrap') && p.previousElementSibling.classList.contains('calc-head'); }"))
        check("the reset button says the fx-991ZA look", pg.inner_text("#calcCard .calcFaceReset").strip() == "fx-991ZA look", pg.inner_text("#calcCard .calcFaceReset"))
        shot(pg, "face-panel.png")
        set_input(pg, "body", "#f6d9e6"); pg.wait_for_timeout(60)
        check("changing Body puts --cf-body on #calcCard at once", pg.evaluate("document.getElementById('calcCard').style.getPropertyValue('--cf-body')") == "#f6d9e6")
        check("and the body follows (.calc-wrap's background)", pg.evaluate(BG, "#calcCard .calc-wrap") == hexrgb("#f6d9e6"), pg.evaluate(BG, "#calcCard .calc-wrap"))
        check("pw.calcFace keeps only that slot", json.loads(pg.evaluate(STORED) or "null") == {"body": "#f6d9e6"}, pg.evaluate(STORED))
        set_input(pg, "num", "#f2f2f2"); pg.wait_for_timeout(60)
        nk = pg.evaluate(COL, '#calcCard [data-keyid="d7"] .kmain')
        check("a light Number keys colour turns their labels near-black (not white on white)", nk == hexrgb("#1b1e22"), nk)
        con = pg.evaluate(CONTRAST_JS); low = [c for c in con if c[1] < 4.5]
        check("and every label still reads 4.5:1 or better", not low, low)
        set_input(pg, "num", DEFAULTS["num"]); pg.wait_for_timeout(60)
        check("picking the fx-991ZA value again drops it from pw.calcFace", json.loads(pg.evaluate(STORED) or "null") == {"body": "#f6d9e6"}, pg.evaluate(STORED))
        pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(100)
        check("a second tap shuts it (aria-expanded false)", pg.locator("#calcCard .calcFace").is_hidden()
              and pg.get_attribute("#calcCard .calcFaceBtn", "aria-expanded") == "false")
        c2 = rect(pg, "#calcCard")
        check("shut, the card is back where it was", abs(c2["l"] - c0["l"]) < 0.5 and abs(c2["t"] - c0["t"]) < 0.5 and abs(c2["h"] - c0["h"]) < 0.5, [c0, c2])
        pg.reload(); ready(pg)
        if not pg.locator("#noteView").is_visible(): open_note(pg)
        open_calc(pg)
        check("after a reload the card opens in her Body colour", pg.evaluate(BG, "#calcCard .calc-wrap") == hexrgb("#f6d9e6")
              and pg.evaluate("document.getElementById('calcCard').style.getPropertyValue('--cf-body')") == "#f6d9e6", pg.evaluate(BG, "#calcCard .calc-wrap"))
        pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(150)
        check("and its swatch shows it", pg.input_value("#calcCard .calcFace input[data-slot='body']") == "#f6d9e6")
        pg.click("#calcCard .calcFaceReset"); pg.wait_for_timeout(80)
        check("the reset clears pw.calcFace", pg.evaluate(STORED) is None, pg.evaluate(STORED))
        check("and the body is the fx-991ZA colour again, no slot left inline", pg.evaluate(BG, "#calcCard .calc-wrap") == hexrgb(DEFAULTS["body"])
              and pg.evaluate("document.getElementById('calcCard').style.getPropertyValue('--cf-body')") == "", pg.evaluate(BG, "#calcCard .calc-wrap"))
        check("the swatches show the fx-991ZA values", pg.evaluate("() => [...document.querySelectorAll('#calcCard .calcFace input')].map((i) => i.value)") == list(DEFAULTS.values()))
        pg.click("#calcCard .calc-close"); pg.wait_for_timeout(80); open_calc(pg)
        check("putting the calculator away shuts the panel", pg.locator("#calcCard .calcFace").is_hidden())
        pg.evaluate("localStorage.setItem('pw.calcFace', JSON.stringify({ body: 'red', lcd: '#ZZZZZZ', fn: 7 }))")
        pg.reload(); ready(pg)
        if not pg.locator("#noteView").is_visible(): open_note(pg)
        open_calc(pg)
        check("a broken pw.calcFace is ignored (the fx-991ZA look, no error)", pg.evaluate(BG, "#calcCard .calc-wrap") == hexrgb(DEFAULTS["body"]))
        pg.evaluate("localStorage.removeItem('pw.calcFace')")

        # ------------------------------------------------------------ 3b. pw-v8w: the body's pastel chips
        group[0] = "body chips (pw-v8w)"
        CHIPS = [["fx-991ZA grey", "#ecedef"], ["Blush", "#f6d9e0"], ["Peach", "#fbe3d0"], ["Butter", "#fbf1c7"],
                 ["Mint", "#d9efe0"], ["Sky", "#d6e6f5"], ["Lilac", "#e4dcf3"], ["Sand", "#efe6d8"]]
        RING = "() => [...document.querySelectorAll('#calcCard .calcChip.on')].map((c) => c.title)"
        pg.reload(); ready(pg)
        if not pg.locator("#noteView").is_visible(): open_note(pg)
        open_calc(pg); pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(150)
        chips = pg.evaluate("() => [...document.querySelectorAll('#calcCard .calcChip')].map((c) => [c.title, c.dataset.colour])")
        check("eight chips, the fx-991ZA grey first, then the seven pastels, each with its name as a title", chips == CHIPS, chips)
        where = pg.evaluate("() => { const r = document.querySelector('#calcCard .calcChips'); return [r.previousElementSibling.querySelector('input').dataset.slot,"
                            " r.nextElementSibling.querySelector('input').dataset.slot, document.querySelectorAll('#calcCard .calcChips').length]; }")
        check("they sit right under the Body row, and only there (Screen comes next)", where == ["body", "lcd", 1], where)
        cs = pg.evaluate("""() => { const c = document.querySelector('#calcCard .calcChip'), d = getComputedStyle(c, '::before'), s = parseFloat(getComputedStyle(document.getElementById('calcCard')).getPropertyValue('--calc-s'));
            const r = c.getBoundingClientRect(); return [parseFloat(d.width), parseFloat(d.height), r.height / s, r.width / s]; }""")
        check("each chip: a 22 px dot in a 44 px tall tap area at 1.0x (about 37 px wide, eight across)", abs(cs[0] - 22) < 0.1 and abs(cs[1] - 22) < 0.1 and abs(cs[2] - 44) < 0.5 and cs[3] >= 34, cs)
        check("the ring sits on the grey chip at first", pg.evaluate(RING) == ["fx-991ZA grey"], pg.evaluate(RING))
        pg.click('#calcCard .calcChip[title="Mint"]'); pg.wait_for_timeout(80)
        check("a tap on Mint: --cf-body is #d9efe0 on #calcCard and the body follows",
              pg.evaluate("document.getElementById('calcCard').style.getPropertyValue('--cf-body')") == "#d9efe0" and pg.evaluate(BG, "#calcCard .calc-wrap") == hexrgb("#d9efe0"),
              pg.evaluate(BG, "#calcCard .calc-wrap"))
        check("... the Body swatch shows it, pw.calcFace keeps it, the ring moved to Mint",
              pg.input_value("#calcCard .calcFace input[data-slot='body']") == "#d9efe0" and json.loads(pg.evaluate(STORED) or "null") == {"body": "#d9efe0"}
              and pg.evaluate(RING) == ["Mint"], [pg.evaluate(STORED), pg.evaluate(RING)])
        pg.reload(); ready(pg)
        if not pg.locator("#noteView").is_visible(): open_note(pg)
        open_calc(pg); pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(150)
        check("after a reload: still Mint, the ring on Mint", pg.evaluate(BG, "#calcCard .calc-wrap") == hexrgb("#d9efe0") and pg.evaluate(RING) == ["Mint"], pg.evaluate(RING))
        low_all = []
        for name, col in CHIPS:
            pg.click(f'#calcCard .calcChip[title="{name}"]'); pg.wait_for_timeout(40)
            low_all += [(name, c) for c in pg.evaluate(CONTRAST_JS) if c[1] < 4.5]
            if pg.evaluate("getComputedStyle(document.getElementById('calcCard')).getPropertyValue('--cf-body-ink').trim()") != "#1b1e22": low_all.append((name, "body ink"))
        check("every chip: the key labels still read 4.5:1 or better, the print on the body stays near-black", not low_all, low_all)
        set_input(pg, "body", "#123456"); pg.wait_for_timeout(40)
        check("a picker colour that is no chip: no ring", pg.evaluate(RING) == [], pg.evaluate(RING))
        pg.click("#calcCard .calcFaceReset"); pg.wait_for_timeout(60)
        check("the reset puts the ring back on the grey chip", pg.evaluate(RING) == ["fx-991ZA grey"] and pg.evaluate(STORED) is None, pg.evaluate(RING))
        pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(60)
        check("no page errors (1.6x)", not errs, errs)

        # ------------------------------------------------------------ 4. the LCD's inner colours: a TABLE and the menus
        group[0] = "LCD colours"
        keys(pg, "ac", "mode")
        shot(pg, "face-menu-1.6.png")
        bad = pg.evaluate(OLD_JS, OLD)
        check("the MODE menu: nothing on the LCD in calc.css's old colours", not bad, bad[:5])
        keys(pg, "d7", "alpha", "rparen", "x2", "minus", "d2", "alpha", "rparen", "minus", "d3", "eq", "eq", "neg", "d2", "eq", "d4", "eq", "d1", "eq")
        has = pg.locator("#calcCard .lcd-tbl").count() > 0
        check("MODE 7 X²−2X−3, Start −2, End 4, Step 1: the TABLE is on the LCD", has, pg.inner_text("#calcCard .calc-lcd"))
        sel = [pg.evaluate(BG, "#calcCard .lcd-tbl-sel"), pg.evaluate(COL, "#calcCard .lcd-tbl-sel"),
               pg.evaluate(BG, "#calcCard .lcd-tbl-lit"), pg.evaluate(COL, "#calcCard .lcd-tbl-lit")] if has else None
        check("its selected cell and lit heading are --cf-lcd-ink with --cf-lcd digits",
              sel == [hexrgb(DEFAULTS["lcdInk"]), hexrgb(DEFAULTS["lcd"])] * 2, sel)
        rule = pg.evaluate("getComputedStyle(document.querySelector('#calcCard .lcd-tbl th')).borderBottomColor") if has else None
        check("its lines are a mix of the screen's ink and pane (not calc.css's #6c7a64)", rule and rule not in OLD and rule.startswith(("rgb", "color(srgb")), rule)
        bad = pg.evaluate(OLD_JS, OLD)
        check("the TABLE: nothing on the LCD in calc.css's old colours", not bad, bad[:5])
        shot(pg, "face-table-1.6.png")
        keys(pg, "shift", "mode")
        mi = pg.locator("#calcCard .lcd-mi-n").count()
        mic = [pg.evaluate(BG, "#calcCard .lcd-mi-n"), pg.evaluate(COL, "#calcCard .lcd-mi-n")] if mi else None
        check("SETUP's boxed numbers are --cf-lcd-ink with --cf-lcd text", mic == [hexrgb(DEFAULTS["lcdInk"]), hexrgb(DEFAULTS["lcd"])], [mi, mic])
        bad = pg.evaluate(OLD_JS, OLD)
        check("the SETUP menu: nothing on the LCD in calc.css's old colours", not bad, bad[:5])
        pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(100)
        set_input(pg, "lcd", "#203040"); set_input(pg, "lcdInk", "#f0f4c0"); pg.wait_for_timeout(60)
        mic = [pg.evaluate(BG, "#calcCard .lcd-mi-n"), pg.evaluate(COL, "#calcCard .lcd-mi-n"), pg.evaluate(BG, "#calcCard .calc-lcd"), pg.evaluate(COL, "#calcCard .calc-ind")]
        check("a new Screen and Screen ink reach the boxed numbers, the pane and the indicators",
              mic[:3] == [hexrgb("#f0f4c0"), hexrgb("#203040"), hexrgb("#203040")] and mic[3] != hexrgb("#3a4434"), mic)
        pg.click("#calcCard .calcFaceReset"); pg.wait_for_timeout(60)
        pg.click("#calcCard .calcFaceBtn"); pg.wait_for_timeout(60)
        keys(pg, "ac")
        check("no page errors (LCD)", not errs, errs)
        ctx.close()

        # ------------------------------------------------------------ 5. the other two sizes
        group[0] = "sizes"
        for sc, fn in [(1.0, "face-1.0.png"), (2.5, "face-2.5.png")]:
            ctx, pg, errs = with_scale(b, sc)
            s = float(pg.evaluate("getComputedStyle(document.getElementById('calcCard')).getPropertyValue('--calc-s')"))
            r = rect(pg, "#calcCard")
            check(f"{sc}x: the card is {sc}x (344 x {sc} = {344 * sc:.0f} px wide) and fits the 1400 x 1700 screen",
                  abs(s - sc) < 1e-6 and abs(r["w"] - 344 * sc) < 1 and r["b"] <= 1700, [s, r])
            keys(pg, "ac", "d1", "d0", "d9", "d2", "eq", "shift", "dms")
            o = pg.evaluate(OVERLAP_JS)
            check(f"{sc}x: no two printed words overlap or touch", not o["bad"], o["bad"])
            miss = pg.evaluate(KEYHIT_JS)
            check(f"{sc}x: every key's centre lands on that key", not miss, miss)
            shot(pg, fn)
            if sc == 2.5:
                print(f"MEASURED card at 1.0x: {r['w'] / sc:.0f} x {r['h'] / sc:.0f} px")
            check(f"no page errors ({sc}x)", not errs, errs)
            ctx.close()
        b.close()
finally:
    srv.terminate()

groups = []
for g, n, ok, info in res:
    if g not in groups: groups.append(g)
    if not ok: print(f"FAIL [{g}] {n}  -> {str(info)[:500]}")
print()
for g in groups:
    rs = [r for r in res if r[0] == g]
    print(f"{g}: {sum(r[2] for r in rs)}/{len(rs)} passed")
print(f"\nTOTAL {sum(r[2] for r in res)}/{len(res)} passed")
sys.exit(0 if all(r[2] for r in res) else 1)
