/* trimmed copy of Blipwork js/statlib.js: the six functions the calculator uses */

export function sortAsc(a) { return a.slice().sort((x, y) => x - y); }
export function sum(a) { return a.reduce((s, v) => s + v, 0); }
export function mean(a) { return sum(a) / a.length; }

/* Casio "exclusive" quartiles — VERIFIED on the real fx-991ZA PLUS II
   emulator: the median splits the data; for odd n the middle value is
   EXCLUDED from both halves; Q1/Q3 are the medians of the halves. This
   differs from the (n+1)/4 school method above (e.g. 1..8 → Q1 2,5 vs 2).
   Use this ONLY for the on-screen calculator, so it matches the device. */
export function quartilesExclusive(sorted) {
  const medOf = a => a.length ? (a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2) : null;
  const n = sorted.length, med = medOf(sorted);
  const lower = n % 2 === 0 ? sorted.slice(0, n / 2) : sorted.slice(0, (n - 1) / 2);
  const upper = n % 2 === 0 ? sorted.slice(n / 2) : sorted.slice((n + 1) / 2);
  return { q1: medOf(lower) ?? med, med, q3: medOf(upper) ?? med };
}

/* ---------- standard deviation & variance (population) ---------- */
export function variance(arr) { const m = mean(arr); return arr.reduce((s, x) => s + (x - m) * (x - m), 0) / arr.length; }
export function stdDev(arr) { return Math.sqrt(variance(arr)); }
