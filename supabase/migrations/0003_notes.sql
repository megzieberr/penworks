-- PenWorks · 0003_notes.sql · 24 Oct 2026 (U1b)
-- Samsung Notes shape: folder > sub-folder > note (named) > pages (numbered, no names).
-- Replaces U1's notebooks + sections with ONE folders table (two levels, hard stop) and moves
-- pages under notes. Live had 0 rows in notebooks, sections and pages (checked 24 Oct), so
-- nothing moves; the "not null" on pages.note_id fails loudly if that is no longer true.

-- ---------------------------------------------------------------------------
-- folders: a top folder holds sub-folders and notes; a sub-folder holds notes only
-- ---------------------------------------------------------------------------

create table public.folders (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  parent_id   uuid references public.folders(id) on delete cascade,   -- null = top folder
  name        text not null,
  colour      text check (colour is null or colour ~ '^#[0-9a-fA-F]{6}$'),  -- folder icon colour
  position    integer not null default 0,
  deleted_at  timestamptz,                -- bin: set = in the bin, null = live
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint folders_not_own_parent check (parent_id is null or parent_id <> id)
);
create index folders_owner_idx on public.folders (owner_id, position);
create index folders_parent_idx on public.folders (parent_id, position);
create trigger folders_updated_at before update on public.folders
  for each row execute function public.set_updated_at();

-- two levels, hard stop (her ruling 24 Oct 20:39): the parent must be a top folder of the same
-- owner, and a folder that already holds folders cannot itself go inside another folder
create or replace function public.folders_two_levels()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  grand uuid;
  parent_owner uuid;
begin
  if new.parent_id is null then
    return new;
  end if;
  select f.parent_id, f.owner_id into grand, parent_owner
    from public.folders f where f.id = new.parent_id;
  if not found or parent_owner is distinct from new.owner_id then
    raise exception 'That folder does not exist.' using errcode = 'foreign_key_violation';
  end if;
  if grand is not null then
    raise exception 'Folders go two levels deep, no further.' using errcode = 'check_violation';
  end if;
  if exists (select 1 from public.folders c where c.parent_id = new.id) then
    raise exception 'A folder with folders inside it cannot go inside another folder.'
      using errcode = 'check_violation';
  end if;
  return new;
end $$;
revoke execute on function public.folders_two_levels() from public, anon, authenticated;
create trigger folders_two_levels before insert or update of parent_id on public.folders
  for each row execute function public.folders_two_levels();

-- ---------------------------------------------------------------------------
-- notes: the named thing she opens; no position, the grid orders itself
-- (pinned first, then last edited first)
-- ---------------------------------------------------------------------------

create table public.notes (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  folder_id   uuid references public.folders(id) on delete set null,   -- null = Loose
  name        text not null default 'Untitled',
  pinned      boolean not null default false,
  cover_path  text,                       -- storage: first-page thumbnail, filled by U3
  deleted_at  timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index notes_owner_idx on public.notes (owner_id, pinned desc, updated_at desc);
create index notes_folder_idx on public.notes (folder_id, pinned desc, updated_at desc);
-- "last edited" = renamed or its pages changed (see touch_note below); pinning, moving, binning
-- and the U3 cover picture do NOT count, so Pin / Unpin does not reshuffle the grid
create trigger notes_updated_at before update of name on public.notes
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- pages move under notes: numbered by position, no names
-- ---------------------------------------------------------------------------

alter table public.pages add column note_id uuid not null references public.notes(id) on delete cascade;
alter table public.pages drop column section_id;   -- takes pages_section_idx with it
alter table public.pages drop column title;
alter table public.pages alter column background set default 'grid';   -- new pages: portrait, 1 cm grid
create index pages_note_idx on public.pages (note_id, position);

-- a page added, deleted, moved, re-papered or inked (touch_page bumps pages.updated_at)
-- counts as editing its note; binning and snapshot refreshes do not
create or replace function public.touch_note()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  update public.notes set updated_at = now()
    where id = coalesce(new.note_id, old.note_id);
  return coalesce(new, old);
end $$;
revoke execute on function public.touch_note() from public, anon, authenticated;
create trigger pages_touch_note
  after insert or delete or update of position, orientation, background, updated_at on public.pages
  for each row execute function public.touch_note();

-- ---------------------------------------------------------------------------
-- notebooks and sections go (empty, checked 24 Oct)
-- ---------------------------------------------------------------------------

drop table public.sections;
drop table public.notebooks;

-- ---------------------------------------------------------------------------
-- bin purge now covers pages, notes and folders (security invoker, as live since
-- purge_bin_invoker; RLS keeps it to the caller's own rows)
-- ---------------------------------------------------------------------------

create or replace function public.purge_bin(days integer default 30)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare n integer := 0; m integer;
begin
  delete from public.pages where owner_id = auth.uid()
    and deleted_at is not null and deleted_at < now() - make_interval(days => days);
  get diagnostics m = row_count; n := n + m;
  delete from public.notes where owner_id = auth.uid()
    and deleted_at is not null and deleted_at < now() - make_interval(days => days);
  get diagnostics m = row_count; n := n + m;
  delete from public.folders where owner_id = auth.uid()
    and deleted_at is not null and deleted_at < now() - make_interval(days => days);
  get diagnostics m = row_count; n := n + m;
  return n;
end $$;
revoke execute on function public.purge_bin(integer) from public, anon;
grant execute on function public.purge_bin(integer) to authenticated;

-- ---------------------------------------------------------------------------
-- row-level security: you see and touch only your own rows
-- ---------------------------------------------------------------------------

alter table public.folders enable row level security;
alter table public.notes   enable row level security;

create policy folders_own on public.folders
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy notes_own on public.notes
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- grants: nothing for anon; authenticated gets the four verbs and nothing else
-- (as tidy_grants did for the U1 tables)
-- ---------------------------------------------------------------------------

revoke all on public.folders, public.notes from anon;
grant select, insert, update, delete on public.folders, public.notes to authenticated;
revoke truncate, references, trigger on public.folders, public.notes from authenticated;

-- ---------------------------------------------------------------------------
-- realtime: the note list on the other device updates as notes change
-- ---------------------------------------------------------------------------

alter publication supabase_realtime add table public.notes;
