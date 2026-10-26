-- PenWorks · 0004_bookmark.sql · 26 Oct 2026 (U3c)
-- The page bookmark (pw-v4r, kept on the device until now) becomes a column, and "last edited" on a note stops
-- counting the things her Samsung Notes does not count: a bookmark, a snapshot refresh, a binning.
-- profiles.settings and profiles.pen_colours exist since 0001 and carry the tray state from U3c on; no change here.
-- Live rows when written: 1 profile, 2 folders, 2 notes, 6 pages, 0 strokes (counted 26 Oct 14:07).

alter table public.pages add column bookmark boolean not null default false;
create index pages_bookmark_idx on public.pages (owner_id) where bookmark and deleted_at is null;

-- pages_updated_at (0001) bumps updated_at on EVERY page update, and pages_touch_note (0003) fires on an updated_at
-- change, so today a bookmark, a snapshot or a binning would move the note to the top of the list. From now on only
-- a real edit counts: a page added, deleted, moved, re-papered or inked (the strokes trigger bumps updated_at alone).
drop trigger pages_touch_note on public.pages;

create trigger pages_touch_note_rows
  after insert or delete on public.pages
  for each row execute function public.touch_note();

-- an update counts unless ONLY bookmark, snapshot_path, snapshot_at, deleted_at, flagged or flag_note moved
-- (set_updated_at bumps updated_at on every one of those too, so updated_at alone cannot tell them apart)
create trigger pages_touch_note_edit
  after update on public.pages
  for each row
  when (old.position is distinct from new.position
     or old.orientation is distinct from new.orientation
     or old.background is distinct from new.background
     or old.note_id is distinct from new.note_id
     or (old.updated_at is distinct from new.updated_at
         and old.bookmark is not distinct from new.bookmark
         and old.snapshot_path is not distinct from new.snapshot_path
         and old.snapshot_at is not distinct from new.snapshot_at
         and old.deleted_at is not distinct from new.deleted_at
         and old.flagged is not distinct from new.flagged
         and old.flag_note is not distinct from new.flag_note))
  execute function public.touch_note();
