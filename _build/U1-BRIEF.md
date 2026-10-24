# PenWorks U1 worker brief: scaffold, login, tree, empty A4 page

Written 24 Oct 2026 by Fable (foreman). One worker (Opus), one unit, fresh session. Done = you report
and stop. Do NOT start U2 (ink) or anything beyond this list, however tempting.

## What this app is (two sentences)

PenWorks is Megan's own replacement for Samsung Notes: she writes with the S Pen on her Samsung tablet, reads on her
Android phone and laptop, and Claude reads and tidies through the database. Fixed A4 pages inside
notebooks > sections > pages, OneNote-shaped, nothing she can click by accident.

Audience: Megan (and later one more person, Janko). UI language: **English only**.
Design in one sentence: white paper in the middle, a thin tree down the left, a thin pen tray down the
right, nothing else on screen.

## Read first (in this order, nothing else)

1. This brief.
2. `C:\Users\megzi\Desktop\Claude Code Projects\_docs\NOTES-APP-PLAN.md`, sections 2, 3, 6b, 9, 10 and
   the "Things she said NO to" list. The pen tray (section 4) and teaching tray (5) are LATER units;
   read them only to leave room for them.
3. `C:\Users\megzi\.claude\skills\new-quest-app\SKILL.md` (her canonical stack; follow it where this
   brief is silent).
4. `C:\Users\megzi\.claude\skills\frontend-design\SKILL.md`, then do its short day-one pass: pick the
   fonts and a signature colour system, name the theme, write it at the top of `css/app.css`. Calm,
   paper-first; the page is white, always.
5. `C:\Users\megzi\Desktop\Claude Code Projects\constructions\index.html`: read ONLY the pointer
   handling (pen vs finger split, two-finger zoom and pan) and the manifest/sw pattern. Lift that
   zoom/pan code; do not read the compass/ruler/protractor code (that is U5).
6. `C:\Users\megzi\Desktop\Claude Code Projects\penworks\supabase\migrations\0001_init.sql` and
   `0002_storage.sql`: the schema, already applied live. Do not change it. If U1 truly needs a column,
   write the SQL into `supabase/migrations/0003_<name>.sql` and STOP and report; Fable applies it.

## The database (already live, checked 24 Oct)

- Project `duibtdcxmnvsuczuceld`, URL `https://duibtdcxmnvsuczuceld.supabase.co`,
  publishable key `sb_publishable_bj2rpL9bwuYSrWCnZxkAuA_uIHYRVJR` (public, goes in the app).
- Login: username + password. The app turns the username into the email `<username>@penworks.app` and
  calls `signInWithPassword`. **No signup form** (accounts are made by SQL). Keep the session
  (supabase-js default persistSession). A logout button lives in the tree's footer, small.
- Tables (all RLS, owner_id = auth.uid(), authenticated has select/insert/update/delete; anon nothing):
  `profiles` (id, username, display_name, pen_colours, settings), `notebooks` (name, position,
  deleted_at), `sections` (notebook_id, name, position, background, deleted_at), `pages` (section_id
  nullable = Loose, title, position, orientation, background, snapshot_path, flagged, deleted_at,
  updated_at), `strokes` (U2/U3, leave alone), `comments`, `action_log`.
- `deleted_at` set = in the bin. Restore = set it null. `select purge_bin(30)` (rpc) empties the
  caller's bin of anything older than 30 days; call it once on app open and ignore the number.
- Realtime is on for strokes, pages, comments (used from U3; U1 only needs ordinary reads).
- Test login for your own checks: `C:\Users\megzi\Desktop\Claude Code Projects\penworks\LOGIN-LOCAL.md`
  (gitignored; never paste its contents into code, logs, commits or your report).

## Build this (and only this)

Folder: `C:\Users\megzi\Desktop\Claude Code Projects\penworks\`. The app is called **PenWorks** (her pick,
24 Oct); the public repo will be `megzieberr/penworks` and the address megzieberr.github.io/penworks, so use
relative paths everywhere. `git init` there, commit at the end, **do not create the GitHub repo and do not
push**: shipping is a separate step Fable runs with her yes.

Static ES-module site, no build step: `index.html`, `css/app.css`, `js/` modules, `manifest.json`,
`sw.js` (network-first, versioned cache name, same shape as constructions), `.nojekyll`, `icons/`
(a plain placeholder icon is fine; she picks the real one in U7).

1. **`js/api.js`** with every database call in one place, and **`js/local-backend.js`**, a twin that
   keeps the same data in localStorage, switched on with `?local=1`. Build and test against local
   first, then live.
2. **Login screen**: username, password, one button. Wrong password = one plain line, no red wall.
3. **The tree** (left, about 260 px on tablet and laptop; a slide-in drawer behind a ☰ button at phone
   width): every notebook open with its sections and pages visible at once, page counts next to each
   notebook and section, **Loose** at the top with its count, **Bin** at the bottom with its count.
   Tap a page to open it; the open section is remembered. Long-press (or a small ⋯) on a notebook,
   section or page gives: rename, move (to another section or to Loose), move up / move down, bin.
   In the Bin: restore, and nothing else (no "delete forever"; the 30 days do that).
   "+ Notebook" at the bottom of the tree, "+ Section" inside each notebook, "+ Page" at the top of
   the page area. A new page lands in the open section, or in Loose if none is open.
   Names are edited in place; the untitled page shows "Page" plus its date. The app title in the header and manifest is "PenWorks".
4. **The page area** (centre): one fixed A4 page, white, with a soft shadow on a light neutral
   workspace, portrait by default, a portrait/landscape toggle in the page header, and a background
   choice per page: blank, grid (1 cm squares, drawn as SVG or CSS, light grey) or lined (8 mm). Page
   size: A4 at 96 px per 2.54 cm, i.e. 794 × 1123 px at zoom 1. Two fingers pan and zoom the page
   (lifted from constructions); the S Pen and the mouse do nothing yet (U2). Pages in a section are
   reached by the tree or by two small prev/next arrows in the page header; no endless scroll.
   "Add a page below" at the bottom of the page.
5. **The tray strip** (right edge, about 56 px wide, full height, slightly darker than the workspace):
   EMPTY in U1 except a greyed undo and redo at the bottom, disabled. It exists so the layout is final
   before the ink unit fills it.
6. **Autosave**: every change in the tree writes straight to Supabase (or local) with no save button;
   a failed write shows a small toast "Not saved, trying again" and retries once.
7. **PWA**: installable, works at phone width (375 px, drawer tree) and tablet width (landscape
   1280 × 800 is her tablet in landscape).

## Not in U1 (do not build, do not stub with visible buttons)

Ink, pen tray contents, erasers, select, hold-to-snap, images, PDF, share, export, comments layer,
flags, search, Janko's account, settings screen, dark mode, typed text on pages. And nothing from her
NO list: board mode, page history, shape menus, text tool, pressure, dotted lines, endless scroll,
coloured paper, lasso.

## Check it (headless, no screenshots into the Claude browser pane: they crash the app)

Write `tests/test_u1.py` (Playwright, Python, same style as `constructions/tests/test_pwa.py`) and run
it; paste the pass/fail summary into your report, not the whole log.

- Local mode (`?local=1`): create a notebook, a section, two pages; rename each; move page 2 to Loose;
  move it back; bin it; restore it; counts in the tree are right after every step; reload keeps it all.
- Live mode: log in with the LOGIN-LOCAL account (read the file in the test, never print it), create a
  notebook called "U1 test", a section, a page; bin the notebook; restore it; then delete the test rows
  through the API so the database is left empty again. A wrong password shows the one-line message.
- Phone width (375 × 812): the tree is a drawer, the page is visible, no horizontal scroll.
- Tablet width (1280 × 800): tree, page and tray all visible, the page fits at zoom 1 with margins.
- Backgrounds: grid draws 1 cm squares (count them: 21 across a portrait page), lined draws lines.
- `sw.js` registers, manifest validates (reuse the checks from constructions `test_pwa.py`).

Playwright's own screenshots for YOUR eyes are allowed at phone width, at most two, small.

## Budget and conduct

- One unit, fresh context, aim under 250k tokens. Never read your own screenshots at full size, never
  read whole logs (tail / grep). Do not open the Samsung Notes folder or anything outside the paths above.
- No em-dashes anywhere (UI text, comments, commit). Plain English in the UI.
- Finish with `PROJECT-STATUS.md` in the app folder updated (catchup format: Where we are, Decisions,
  Pending on Megan, Next up) and ONE commit.
- Report back in plain words: what is built, which checks passed (with the summary line), what you
  could not do and why. No "should work".
