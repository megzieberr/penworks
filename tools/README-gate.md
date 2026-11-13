# The login lock (pw-v9h, migration 0008)

**What it does.** Your password stays your 5-digit code. But the app no longer sends the code straight to Supabase.
It asks the database first (`login_gate`). A right code hands back a long secret, and the app signs in with that.
5 wrong codes in a row lock the login for 10 minutes. Each lock after that doubles the wait (20, 40, 80 minutes),
never more than a day. While it is locked, even the right code waits. A right code resets everything.

**Arm it** (once, after migration 0008 is in the database and pw-v9h is live):

    python tools/arm_gate.py

It signs in with your code, swaps your real Supabase password for a long secret, checks that the secret signs in,
and only then rewrites `.env`: `PW_PASS` becomes the secret, `PW_CODE` keeps your code. Nothing else in `.env`
changes. Running it again is safe: it says "already matches" and changes nothing. `--test` does the same for the
throwaway login (`PW_TEST_USER`, `PW_TEST_PASS`, `PW_TEST_CODE`).

**Check it** (changes nothing, never costs a try):

    python tools/arm_gate.py --check

It says whether `.env` has `PW_CODE`, and whether `PW_PASS` signs in directly.

**Unlock** someone who locked themselves out (Supabase SQL editor; put the real name in place of `someone`):

    update private.login_gate set fails = 0, locks = 0, locked_until = null where username = 'someone';

**Undo** for one person (the short code becomes their real password again):

    with g as (delete from private.login_gate where username = 'someone' returning user_id, code_hash)
    update auth.users u set encrypted_password = g.code_hash, updated_at = now() from g where u.id = g.user_id;

Then, by hand, set `PW_PASS` in `.env` back to the `PW_CODE` value. To remove the whole lock, undo every person
first, then run the three `drop` lines at the foot of `supabase/migrations/0008_login_gate.sql`.

**The one trap.** The laptop tools (`drop_pdf.py`, the backup) sign in with `PW_PASS`, the long secret, straight to
Supabase. They never touch the lock, so a lockout on the tablet cannot stop the backup. It also means: never
type the secret anywhere public, and never put the short code back into `PW_PASS` unless you have done the undo.
