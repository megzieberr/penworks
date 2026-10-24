-- PenWorks · 0001_init.sql · 24 Oct 2026
-- Schema for the notes app (working name). Applied to Supabase project duibtdcxmnvsuczuceld
-- (fourth-shift account, org "Claude Code Projects"). Every table is owned by one person
-- (owner_id = auth.uid()); row-level security keeps people apart. Login = username + password
-- with a synthetic email <username>@penworks.app.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------

create or replace function public.keepalive()
returns text
language sql
stable
set search_path = ''
as $$ select 'ok ' || now()::text $$;
revoke execute on function public.keepalive() from public;
grant execute on function public.keepalive() to anon, authenticated;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end $$;

-- ---------------------------------------------------------------------------
-- profiles (one per login)
-- ---------------------------------------------------------------------------

create table public.profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  username      text not null unique check (username ~ '^[a-z0-9_]{2,24}$'),
  display_name  text not null default '',
  pen_colours   jsonb not null default '[]'::jsonb,   -- her 12 colours, hex strings
  settings      jsonb not null default '{}'::jsonb,   -- each tool's last width/dash/opacity etc.
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create trigger profiles_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();

-- new auth user -> profile row (username comes from signUp metadata or the email's local part)
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, username, display_name)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'username', split_part(new.email, '@', 1)),
    coalesce(new.raw_user_meta_data->>'display_name', '')
  );
  return new;
end $$;
revoke execute on function public.handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- notebooks > sections > pages
-- ---------------------------------------------------------------------------

create table public.notebooks (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  name        text not null,
  position    integer not null default 0,
  deleted_at  timestamptz,                -- bin: set = in the bin, null = live
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index notebooks_owner_idx on public.notebooks (owner_id, position);
create trigger notebooks_updated_at before update on public.notebooks
  for each row execute function public.set_updated_at();

create table public.sections (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  notebook_id  uuid not null references public.notebooks(id) on delete cascade,
  name         text not null,
  position     integer not null default 0,
  background   text not null default 'blank' check (background in ('blank','grid','lined')),
  deleted_at   timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index sections_notebook_idx on public.sections (notebook_id, position);
create index sections_owner_idx on public.sections (owner_id);
create trigger sections_updated_at before update on public.sections
  for each row execute function public.set_updated_at();

create table public.pages (
  id             uuid primary key default gen_random_uuid(),
  owner_id       uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  section_id     uuid references public.sections(id) on delete set null,   -- null = Loose
  title          text not null default '',
  position       integer not null default 0,
  orientation    text not null default 'portrait' check (orientation in ('portrait','landscape')),
  background     text not null default 'blank' check (background in ('blank','grid','lined')),
  pdf_path       text,          -- storage: imports/<owner>/... rendered under the ink (one PDF page)
  pdf_page       integer,       -- which page of that PDF
  snapshot_path  text,          -- storage: snapshots/<owner>/<page id>.webp, the picture Claude reads
  snapshot_at    timestamptz,
  transcript     text,          -- version two: typed transcript of the handwriting
  flagged        boolean not null default false,   -- "flag for Claude"
  flag_note      text,
  deleted_at     timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index pages_section_idx on public.pages (section_id, position);
create index pages_owner_idx on public.pages (owner_id, updated_at desc);
create index pages_flagged_idx on public.pages (owner_id) where flagged and deleted_at is null;
create trigger pages_updated_at before update on public.pages
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- strokes: everything drawn or placed on a page, one row each
-- ---------------------------------------------------------------------------

create table public.strokes (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  page_id     uuid not null references public.pages(id) on delete cascade,
  seq         bigint not null,      -- client clock in ms; draw order on the page
  kind        text not null check (kind in ('pen','highlighter','shape','image','axes','graph')),
  style       jsonb not null default '{}'::jsonb,   -- colour, width, dash, opacity
  data        jsonb not null,                       -- points for ink; params for shapes/axes; path+box for images
  created_at  timestamptz not null default now()
);
create index strokes_page_idx on public.strokes (page_id, seq);
create index strokes_owner_idx on public.strokes (owner_id);

-- a stroke added or removed bumps its page's updated_at (snapshot refresh watches this)
create or replace function public.touch_page()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  update public.pages set updated_at = now()
    where id = coalesce(new.page_id, old.page_id);
  return coalesce(new, old);
end $$;
revoke execute on function public.touch_page() from public, anon, authenticated;
create trigger strokes_touch_page after insert or update or delete on public.strokes
  for each row execute function public.touch_page();

-- ---------------------------------------------------------------------------
-- comments (Claude's margin notes), action log (what Claude did)
-- ---------------------------------------------------------------------------

create table public.comments (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  page_id     uuid not null references public.pages(id) on delete cascade,
  author      text not null default 'claude' check (author in ('claude','owner')),
  body        text not null,
  x           real,                -- page units, null = top of the margin
  y           real,
  hidden      boolean not null default false,
  created_at  timestamptz not null default now()
);
create index comments_page_idx on public.comments (page_id, created_at);

create table public.action_log (
  id           bigint generated always as identity primary key,
  owner_id     uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  actor        text not null default 'claude',      -- 'claude' | 'owner' | 'script'
  session      text,                                -- which Claude session, free text
  action       text not null,                       -- 'move_page', 'rename', 'bin', 'restore', 'comment', ...
  target_kind  text,                                -- 'notebook' | 'section' | 'page' | 'comment'
  target_id    uuid,
  details      jsonb not null default '{}'::jsonb,  -- enough to undo: old values
  undone_at    timestamptz,
  created_at   timestamptz not null default now()
);
create index action_log_owner_idx on public.action_log (owner_id, created_at desc);

-- ---------------------------------------------------------------------------
-- bin: empties itself after 30 days (called by the app on open, by notes.py, by the nightly script)
-- ---------------------------------------------------------------------------

create or replace function public.purge_bin(days integer default 30)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare n integer := 0; m integer;
begin
  delete from public.pages where owner_id = auth.uid()
    and deleted_at is not null and deleted_at < now() - make_interval(days => days);
  get diagnostics m = row_count; n := n + m;
  delete from public.sections where owner_id = auth.uid()
    and deleted_at is not null and deleted_at < now() - make_interval(days => days);
  get diagnostics m = row_count; n := n + m;
  delete from public.notebooks where owner_id = auth.uid()
    and deleted_at is not null and deleted_at < now() - make_interval(days => days);
  get diagnostics m = row_count; n := n + m;
  return n;
end $$;
revoke execute on function public.purge_bin(integer) from public, anon;
grant execute on function public.purge_bin(integer) to authenticated;

-- ---------------------------------------------------------------------------
-- row-level security: you see and touch only your own rows
-- ---------------------------------------------------------------------------

alter table public.profiles   enable row level security;
alter table public.notebooks  enable row level security;
alter table public.sections   enable row level security;
alter table public.pages      enable row level security;
alter table public.strokes    enable row level security;
alter table public.comments   enable row level security;
alter table public.action_log enable row level security;

create policy profiles_own on public.profiles
  for all to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));
create policy notebooks_own on public.notebooks
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy sections_own on public.sections
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy pages_own on public.pages
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy strokes_own on public.strokes
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy comments_own on public.comments
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy action_log_own on public.action_log
  for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- grants: nothing for anon; authenticated reaches every table through supabase-js
-- (explicit, because Supabase stops auto-granting new public tables from 30 Oct 2026)
-- ---------------------------------------------------------------------------

revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;

grant select, insert, update, delete on public.notebooks, public.sections, public.pages,
  public.strokes, public.comments, public.action_log to authenticated;
grant usage, select on all sequences in schema public to authenticated;

-- profiles: the id and username are not the user's to change from the app
revoke all on public.profiles from authenticated;
grant select, insert on public.profiles to authenticated;
grant update (display_name, pen_colours, settings) on public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- realtime: phone and laptop redraw a page as strokes land
-- ---------------------------------------------------------------------------

alter publication supabase_realtime add table public.strokes, public.pages, public.comments;
