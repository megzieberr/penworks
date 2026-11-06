-- PenWorks · 0007_sticky.sql · 6 Nov 2026 (pw-v9c)
-- Sticky notes (her design 27 Oct, built 6 Nov): a small coloured square on the note's desk that she writes on and drags
-- into the margin beside a page ("the sidelines": quick things to show in class), between pages, or onto a page. A sticky
-- ON a page goes into that page's PDF and pictures as it looks; one in the margin simply is not there.
-- A sticky is a pages row (kind = 'sticky'), so every existing pipe carries it: its strokes hang on page_id = its row id
-- (in sticky px from its top-left), the Bin, Realtime, the tree queue and the cascades work as for a page.
-- anchor_id = the page it belongs with; it goes wherever that page goes (binned, restored, moved to another note, copied,
-- deleted: the cascade below). sk_x, sk_y = its top-left in page px RELATIVE TO the anchor page's top-left (negative or
-- past the page's edge = in the margin); sk_w = its side (square, 3 cm to 12 cm = 113 to 454 page px); sk_colour = one of
-- her four colours. A sticky row has its anchor's note_id; position = its anchor's position (never used for order);
-- orientation, background, bookmark and the pdf columns stay the defaults.
-- Apply BEFORE pushing the app: js/api.js names these columns in every loadAll.
-- Live rows when written: not counted (written by the pw-v9c worker, which never touches the live database).

alter table public.pages
  add column kind text not null default 'page',
  add column anchor_id uuid references public.pages(id) on delete cascade,
  add column sk_x real,
  add column sk_y real,
  add column sk_w real,
  add column sk_colour text;

alter table public.pages
  add constraint pages_kind_check
  check (kind in ('page', 'sticky'));

alter table public.pages
  add constraint pages_sticky_check
  check (
    (kind = 'page' and anchor_id is null and sk_x is null and sk_y is null and sk_w is null and sk_colour is null) or
    (kind = 'sticky' and anchor_id is not null and sk_x is not null and sk_y is not null and sk_w between 113 and 454
     and sk_colour in ('yellow', 'blue', 'green', 'purple')));

-- the cascade looks its rows up by anchor_id
create index if not exists pages_anchor_id_idx on public.pages (anchor_id) where anchor_id is not null;
