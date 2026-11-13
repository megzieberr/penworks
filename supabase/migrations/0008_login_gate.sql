-- PenWorks · 0008_login_gate.sql · 13 Nov 2026 (pw-v9h)
-- The login lock (Design B in _docs/PENWORKS-AUDIT-2026-11-13.md, her ruling 13 Nov). Her password is 5 digits and stays
-- 5 digits; until now anyone could try all 100 000 codes straight against Supabase's sign-in address. From now on a
-- person's REAL Supabase password is a long random secret (64 hex characters), and the short code is checked here, by
-- public.login_gate, which counts wrong tries: 5 wrong in a row lock the login for 10 minutes, and each lock after that
-- doubles the pause (20, 40, 80 minutes...), never more than a day. A right code hands back the secret and the app signs
-- in with it. The laptop tools keep the secret in .env (PW_PASS) and never go through the lock.
-- private.login_gate holds one row per armed person: code_hash is that person's OLD auth.users.encrypted_password,
-- copied as it was, so the undo at the foot can put it back without anyone knowing the code.
-- public.arm_login_gate arms the signed-in person (tools/arm_gate.py calls it); a person without a row is not locked at
-- all (status 'none': the app signs in the old way), so test logins keep working.
-- Order: applied AFTER the pw-v9h push (the app answers a missing function by signing in the old way) and BEFORE megan
-- is armed (tools/arm_gate.py stops with "not in the database yet" until then).
-- Rules: the wrong path RETURNS, never raises (a raise would roll the count back); the row is read FOR UPDATE so
-- parallel guesses queue; while locked even the right code answers 'locked' and nothing is counted.
-- Live rows when written: not counted (written by the pw-v9h worker, which never touches the live database).

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table private.login_gate (
  username     text primary key,                 -- lower case, the part before @penworks.app
  user_id      uuid not null unique references auth.users (id) on delete cascade,
  code_hash    text not null,                    -- the person's OLD auth.users.encrypted_password, as it was
  secret       text not null,                    -- the real Supabase password from now on, 64 hex characters
  fails        integer not null default 0,       -- wrong codes in a row since the last right one or the last lock
  locks        integer not null default 0,       -- locks in a row since the last right code (drives the doubling)
  locked_until timestamptz,
  armed_at     timestamptz not null default now()
);
alter table private.login_gate enable row level security;      -- and no policy at all
revoke all on private.login_gate from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- the gate: anyone may ask it (no login), it answers none / ok + secret / wrong + left / locked + until
-- ---------------------------------------------------------------------------

create or replace function public.login_gate(p_username text, p_code text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  n text := lower(btrim(coalesce(p_username, '')));
  g private.login_gate%rowtype;
  pause interval;
begin
  select * into g from private.login_gate where username = n for update;
  if not found then
    return jsonb_build_object('status', 'none');
  end if;
  if g.locked_until is not null and g.locked_until > now() then
    return jsonb_build_object('status', 'locked', 'until', g.locked_until);
  end if;
  if p_code is not null and length(p_code) between 1 and 72
     and g.code_hash = extensions.crypt(p_code, g.code_hash) then
    update private.login_gate set fails = 0, locks = 0, locked_until = null where username = n;
    return jsonb_build_object('status', 'ok', 'secret', g.secret);
  end if;
  if g.fails + 1 >= 5 then
    pause := least(interval '10 minutes' * power(2, least(g.locks, 10)), interval '1 day');
    update private.login_gate
       set fails = 0, locks = g.locks + 1, locked_until = now() + pause
     where username = n;
    return jsonb_build_object('status', 'locked', 'until', now() + pause);
  end if;
  update private.login_gate set fails = g.fails + 1 where username = n;
  return jsonb_build_object('status', 'wrong', 'left', 5 - (g.fails + 1));
end;
$$;
revoke execute on function public.login_gate(text, text) from public;
grant execute on function public.login_gate(text, text) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- arming: the signed-in person (signed in the old way, with the short code) swaps their password for the secret
-- ---------------------------------------------------------------------------

create or replace function public.arm_login_gate(p_code text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := auth.uid();
  u_email text;
  old_hash text;
  s text;
begin
  if uid is null then
    return jsonb_build_object('status', 'not_signed_in');
  end if;
  select email, encrypted_password into u_email, old_hash from auth.users where id = uid for update;
  if not found or u_email is null or u_email not like '%@penworks.app' then
    return jsonb_build_object('status', 'no_account');
  end if;
  if exists (select 1 from private.login_gate where user_id = uid) then
    return jsonb_build_object('status', 'armed_already');
  end if;
  if p_code is null or length(p_code) not between 1 and 72 or old_hash is null
     or old_hash <> extensions.crypt(p_code, old_hash) then
    return jsonb_build_object('status', 'wrong_code');
  end if;
  s := encode(extensions.gen_random_bytes(32), 'hex');
  insert into private.login_gate (username, user_id, code_hash, secret)
  values (lower(split_part(u_email, '@', 1)), uid, old_hash, s);
  update auth.users
     set encrypted_password = extensions.crypt(s, extensions.gen_salt('bf', 10)), updated_at = now()
   where id = uid;
  return jsonb_build_object('status', 'armed', 'secret', s);
end;
$$;
revoke execute on function public.arm_login_gate(text) from public, anon;
grant execute on function public.arm_login_gate(text) to authenticated;

-- ---------------------------------------------------------------------------
-- by hand only (commented out: this migration never runs them). 'someone' is a made-up name: put the real one in.
-- ---------------------------------------------------------------------------
--
-- UNLOCK one person (the wrong-try count and the doubling start again from nothing):
--   update private.login_gate set fails = 0, locks = 0, locked_until = null where username = 'someone';
--
-- UNDO one person (the short code is their real password again, their gate row goes):
--   with g as (delete from private.login_gate where username = 'someone' returning user_id, code_hash)
--   update auth.users u set encrypted_password = g.code_hash, updated_at = now() from g where u.id = g.user_id;
-- After an undo, PW_PASS in .env goes back to the PW_CODE value by hand.
--
-- UNDO the whole migration, only after every person is undone (the table must be empty first):
--   drop function if exists public.arm_login_gate(text);
--   drop function if exists public.login_gate(text, text);
--   drop table if exists private.login_gate;
