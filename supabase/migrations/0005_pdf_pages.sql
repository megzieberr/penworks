-- PenWorks · 0005_pdf_pages.sql · 26 Oct 2026 (U4a)
-- PDF in: a page made from a PDF page keeps that page's own shape (her ruling 26 Oct: no white bars, it just fits).
-- pdf_path (imports/<owner>/<uuid>.pdf, one object per opened file) and pdf_page exist since 0001. pdf_page is 1-BASED:
-- the PDF's first page is 1, as pdf.js counts. New here: that PDF page's size in PDF points (1/72 inch, as pdf.js reads
-- it at scale 1, after the page's own rotation). Both null on a normal page; the app draws the page 210 mm wide (297 mm
-- when it is wider than tall) and as tall as that size says.
-- Live rows when written: not counted (written by the U4a worker, which never touches the live database).

alter table public.pages
  add column pdf_w real,
  add column pdf_h real;

alter table public.pages
  add constraint pages_pdf_size_check
  check ((pdf_w is null and pdf_h is null) or (pdf_w > 0 and pdf_h > 0));
