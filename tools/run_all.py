# PenWorks: run every tests\test_*.py one at a time and print one table (audit finding K).
# Run from anywhere:  python -E -P tools\run_all.py              (all suites)
#                     python -E -P tools\run_all.py --only u2a,tools,graph
#                     python -E -P tools\run_all.py --timeout 1200
# Each suite runs as `python -E -X utf8 -P tests\<suite>` from the project folder, exactly as a person would
# (-X utf8 so the piped output cannot crash on a character the Windows code page lacks; -u so a timed-out
# suite still leaves what it printed).
# Full output per suite: _build\out\runall\<suite>.txt. The table also goes to tests\LAST-RUN.md.
# A red is "known" when its FAIL line contains a "match" text from tests\known_reds.json for that suite.
# A suite that dies before its totals is a "known crash" when its output contains a "crash" text listed for it.
# Exit code: 0 when every red is known, 1 when any red is new (or a suite timed out or crashed).
import argparse, json, pathlib, re, subprocess, sys, time, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
OUT = ROOT / "_build" / "out" / "runall"
KNOWN = TESTS / "known_reds.json"
LAST = TESTS / "LAST-RUN.md"
DEFAULT_TIMEOUT = 900   # seconds per suite; the slowest measured on 21 Nov is in tests\LAST-RUN.md

TOTAL_RX = re.compile(r"^\s*TOTAL:?\s+(\d+)/(\d+) passed", re.M)
PLAIN_RX = re.compile(r"^\s*(\d+)/(\d+) passed\s*$", re.M)      # test_pdfscroll, test_pw9f
FAIL_RX = re.compile(r"^\s*FAIL\b(.*)$", re.M)


def kill_tree(p):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)


def parse(text):
    m = TOTAL_RX.findall(text) or PLAIN_RX.findall(text)
    if not m:
        return None, None, []
    passed, total = map(int, m[-1])
    return total, total - passed, [f.strip() for f in FAIL_RX.findall(text)]


def run_one(suite, timeout, known):
    OUT.mkdir(parents=True, exist_ok=True)
    out_file = OUT / (suite + ".txt")
    t0 = time.time()
    with open(out_file, "wb") as fh:
        p = subprocess.Popen([sys.executable, "-E", "-X", "utf8", "-u", "-P", str(pathlib.Path("tests") / (suite + ".py"))],
                             cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
        try:
            code = p.wait(timeout=timeout); timed_out = False
        except subprocess.TimeoutExpired:
            kill_tree(p); p.wait(); code = None; timed_out = True
    secs = time.time() - t0
    text = out_file.read_text(encoding="utf-8", errors="replace")
    checks, red, fails = parse(text)
    pats = [k["match"] for k in known if k["suite"] == suite and "match" in k]
    crash_known = any(k["crash"] in text for k in known if k["suite"] == suite and "crash" in k)
    known_n = sum(1 for f in fails if any(pt in f for pt in pats))
    new = [f for f in fails if not any(pt in f for pt in pats)]
    if timed_out:
        verdict = "TIMEOUT"
    elif checks is None:
        verdict = "known crash" if crash_known else "CRASH"
    elif red == 0:
        verdict = "ok" if code == 0 else "CRASH"
    elif red - known_n <= 0:
        verdict = "known"
    else:
        verdict = "RED"
    return {"suite": suite, "checks": checks, "red": red, "known": known_n if checks is not None else None,
            "secs": secs, "verdict": verdict, "new": new}


def table(rows, wall):
    def c(v): return "-" if v is None else str(v)
    lines = ["| suite | checks | red | known red | seconds | verdict |", "|---|---:|---:|---:|---:|---|"]
    for r in rows:
        lines.append(f"| {r['suite']} | {c(r['checks'])} | {c(r['red'])} | {c(r['known'])} | {r['secs']:.0f} | {r['verdict']} |")
    checks = sum(r["checks"] or 0 for r in rows); red = sum(r["red"] or 0 for r in rows)
    kn = sum(r["known"] or 0 for r in rows); bad = sum(r["verdict"] in ("RED", "TIMEOUT", "CRASH") for r in rows)
    total = (f"TOTAL {len(rows)} suites, {checks} checks, {red} red, {kn} known red, {red - kn} new red, "
             f"{bad} suites not clean, {wall:.0f} s")
    return lines, total, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma list, e.g. u2a,tools or test_u2a")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    a = ap.parse_args()
    suites = sorted(p.stem for p in TESTS.glob("test_*.py"))
    if a.only:
        want = [w.strip() for w in a.only.split(",") if w.strip()]
        want = [w if w.startswith("test_") else "test_" + w for w in want]
        missing = [w for w in want if w not in suites]
        if missing:
            print("no such suite: " + ", ".join(missing)); sys.exit(2)
        suites = [s for s in suites if s in want]
    known = json.loads(KNOWN.read_text(encoding="utf-8")) if KNOWN.exists() else []
    t0 = time.time()
    rows = [run_one(s, a.timeout, known) for s in suites]
    lines, total, bad = table(rows, time.time() - t0)
    print("\n".join(lines)); print(); print(total)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    head = [f"# Last test run ({stamp})", "", "Written by `tools/run_all.py`. Known reds: `tests/known_reds.json`.", ""]
    if a.only:
        head += [f"Only: {', '.join(suites)}", ""]
    LAST.write_text("\n".join(head + lines + ["", total, ""]), encoding="utf-8")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
