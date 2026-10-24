# Project status: updated 2026-10-24 (U1 built, not shipped)

## Where we are
**PenWorks** (her pick 24 Oct 19:20; repo will be megzieberr/penworks). Her Samsung Notes replacement; the full spec
is `..\_docs\NOTES-APP-PLAN.md`. **U1 is BUILT and committed locally. Not pushed, no GitHub repo yet, not on her tablet yet.**

U1 (Opus worker, 24 Oct, from `_build\U1-BRIEF.md`):
- Static ES-module PWA, no build step: `index.html`, `css/app.css` (theme "Desk and Ribbon" written at the top),
  `js/app.js` (tree, menus, autosave), `js/page.js` (A4 page, backgrounds, finger zoom and pan),
  `js/api.js` (every Supabase call), `js/local-backend.js` (localStorage twin, `?local=1`), `manifest.json`,
  `sw.js` (network-first, cache `pw-v1`), `.nojekyll`, placeholder `icons/` (made by `_build\make_icons.py`).
- Login: username + password, no signup, session kept. Wrong password = one line: "That username or password is not right."
- Tree: Loose at the top, every notebook open with sections and pages, counts, + Notebook, + Section, Bin at the
  bottom with restore only. Long-press, right-click or the small dots: Rename, Move to..., Move up, Move down,
  Put in the Bin. Binning a notebook or section takes its pages with it (same timestamp) and restore brings them back.
- Page area: A4 794 x 1123 at zoom 1, portrait/landscape toggle, Blank / Grid 1 cm / Lined 8 mm per page, prev/next,
  + Page, Add a page below. One finger moves the page, two fingers zoom; wheel scrolls, Ctrl + wheel zooms. Pen and
  mouse draw nothing yet.
- Tray strip on the right: empty except undo and redo, greyed out.
- Autosave: every tree change writes straight away; a failed write shows "Not saved, trying again" and retries once.
- Checks: `python tests/test_u1.py` (add `--no-live` to skip Supabase). Last run 24 Oct: **53/53 passed**
  (local 19, backgrounds 6, tablet 5, phone 6, pwa 8, live 9). The live group left the database at 0 notebooks,
  0 sections, 0 pages (confirmed with select count(*)).

## Decisions
- 2026-10-24: Database lives on the fourth-shift account, org "Claude Code Projects". ALDE122 stays paused there.
- 2026-10-24: Name = PenWorks. Login email = `<username>@penworks.app`. Supabase dashboard label still "notes-app" (cosmetic).
- 2026-10-24: UI language English only.
- 2026-10-24: Claude's tidying guardrails stay as proposed in the plan (never touch ink, bin first, 30 days, action log).
- 2026-10-24 (U1): the tree becomes a slide-in drawer below 900 px wide (so tablet portrait too); the pen tray is
  hidden below 600 px (the phone reads, it does not write). Easy to change in `css/app.css`.
- 2026-10-24 (U1): one finger moves the page as well as two (plan section 4: "finger scrolls and pinch-zooms").
- 2026-10-24 (U1): the open page and section are remembered per device (localStorage), not in the database.
- 2026-10-24 (U1): a new page copies the open page's paper and orientation; the Bin shows only the top thing binned
  (a binned notebook, not each of its pages), with the date it goes for good.
- 2026-10-24 (U1): supabase-js is loaded from jsDelivr, pinned to 2.45.4.

## Pending on Megan
- 💻 1 min [whenever]: once U1 is live, sign in as `megan` with the password in `LOGIN-LOCAL.md` and ask for a new one (SQL reset, Fable runs it).
- 📱 10 min [after ship]: open it on the tablet (landscape and portrait) and the phone, make a notebook, try long-press and two-finger zoom.

## Next up
1. Fable reviews U1 (code + this file), then ships with her yes: create the public repo megzieberr/penworks, push, Pages from main.
2. Her tablet and phone test, then brief U2 (ink engine) from plan section 4.
3. Not done in U1 (left for later on purpose): no preview entry in the nested launch.json, no memory note; the icon is a placeholder (U7).
