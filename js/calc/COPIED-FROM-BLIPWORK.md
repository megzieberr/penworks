# js/calc: copied from Blipwork, NEVER edit here

Source: `C:\Users\megzi\Desktop\Claude Code Projects\maths-homework-quest` (Blipwork), git head `afe14af`.
Copied: 29 Oct 2026 (PenWorks pw-v7d).

Blipwork is the master. A fix to the calculator is made in Blipwork and copied out again; if something about the
copy does not fit PenWorks, change the HOST side (js/calcpanel.js, css/app.css, the css/calc.css script), never this file.

## calculator.js: byte-identical (3314 lines)

```
0383ec615a7611798dba82ee2ebfd596 *../maths-homework-quest/js/calculator.js
0383ec615a7611798dba82ee2ebfd596 *js/calc/calculator.js
```

Check for drift any time: `md5sum ../maths-homework-quest/js/calculator.js js/calc/calculator.js` (run from the penworks folder).
The two lines must be identical. To refresh after a Blipwork fix: copy the file over, update this page's head and md5 lines,
re-run `python tests/test_calc.py`.

## The two helper files are TRIMMED copies (calculator.js imports `./ui.js` and `./statlib.js`)

- `ui.js`: Blipwork `js/ui.js` lines 4 to 9, the `el(tag, cls, html)` helper only (Blipwork's file also imports rng.js for a
  shuffle the calculator never uses).
- `statlib.js`: the six functions the calculator imports or needs, each verbatim: `sortAsc`, `sum`, `mean` (Blipwork
  `js/statlib.js` lines 8 to 10), `quartilesExclusive` with its comment (lines 30 to 41: the Casio's own quartile rule, deliberately
  not the school (n+1)/4 rule), `variance` and `stdDev` (lines 96 and 97). No `lang.js` import (that is Blipwork's language layer).

## The stylesheet is generated, not copied by hand

`css/calc.css` is lifted out of Blipwork's `css/styles.css` by `_build/extract_calc_css.py` (run it again after a Blipwork change).
