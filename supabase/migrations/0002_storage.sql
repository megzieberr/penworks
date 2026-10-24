-- PenWorks · 0002_storage.sql · 24 Oct 2026
-- Two private buckets. Every object lives under <owner uuid>/..., and the policies only let the
-- owner of that folder read or write it.
--   snapshots : page pictures (WebP), what Claude reads
--   imports   : PDFs and images she drops onto pages

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('snapshots', 'snapshots', false, 5242880,  array['image/webp','image/png','image/jpeg']),
  ('imports',   'imports',   false, 52428800, array['application/pdf','image/webp','image/png','image/jpeg'])
on conflict (id) do nothing;

create policy "own folder read" on storage.objects
  for select to authenticated
  using (bucket_id in ('snapshots','imports') and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "own folder insert" on storage.objects
  for insert to authenticated
  with check (bucket_id in ('snapshots','imports') and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "own folder update" on storage.objects
  for update to authenticated
  using (bucket_id in ('snapshots','imports') and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id in ('snapshots','imports') and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "own folder delete" on storage.objects
  for delete to authenticated
  using (bucket_id in ('snapshots','imports') and (storage.foldername(name))[1] = (select auth.uid())::text);
