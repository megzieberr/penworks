-- PenWorks · 0006_pdf_rot.sql · 30 Oct 2026 (pw-v7p)
-- Rotate a PDF page (her ask 30 Oct: scanned pages lying on their side). pdf_rot = how far she turned the page, clockwise,
-- on top of the file's own rotation. The PDF file in storage is never changed, and pdf_w / pdf_h stay the file's size:
-- the app swaps them on a quarter turn. 0 on every page until she turns one.
-- Apply BEFORE pushing the app: js/api.js names this column in every loadAll.

alter table public.pages
  add column pdf_rot smallint not null default 0;

alter table public.pages
  add constraint pages_pdf_rot_check
  check (pdf_rot in (0, 90, 180, 270));
