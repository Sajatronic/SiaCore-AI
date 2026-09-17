-- =====================================================================
-- FIX: "new row violates row-level security policy" on Add Data
-- =====================================================================
-- AddData.jsx inserts directly into these tables via
-- supabase.from(table).insert(...) — it does NOT go through one of the
-- SECURITY DEFINER functions this project uses elsewhere (like
-- sql/20's fix for Reports), so it runs as whatever role your anon key
-- resolves to. RLS is enabled on manufacturers (and almost certainly
-- parts / distributor / inventory too, same as manufacturers) with no
-- policy permitting that role to INSERT — Postgres correctly rejects
-- the row rather than silently dropping it, which is why you get an
-- explicit error here instead of the silent-empty-result pattern from
-- the Reports bug.
--
-- This adds a straightforward INSERT policy for anon + authenticated
-- on all four tables the Add Data page writes to.
--
-- CORRECTED: the previous version of this file used
-- `create policy if not exists` — that isn't valid PostgreSQL syntax
-- (CREATE POLICY has no IF NOT EXISTS clause, unlike CREATE TABLE /
-- CREATE INDEX) and would have failed with a syntax error immediately.
-- Fixed to the standard idempotent pattern: DROP POLICY IF EXISTS
-- followed by CREATE POLICY, so this is safe to re-run.
--
-- SECURITY NOTE: this makes these four tables insertable by anyone
-- holding your public anon key — which, for a client-side web app, is
-- effectively anyone who opens the page, since the anon key ships in
-- the browser bundle by design. That may be exactly the trust model
-- you want for an internal tool, but it's worth being deliberate about
-- rather than assuming: if you want this restricted to actually-
-- authenticated users only, drop `anon` from these policies below and
-- make sure your app requires login before AddData is reachable (I
-- haven't seen any auth/login flow anywhere in this project so far, so
-- right now "authenticated" and "anon" likely behave identically).
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

drop policy if exists "allow insert for anon and authenticated" on manufacturers;
create policy "allow insert for anon and authenticated"
  on manufacturers for insert
  to anon, authenticated
  with check (true);

drop policy if exists "allow insert for anon and authenticated" on parts;
create policy "allow insert for anon and authenticated"
  on parts for insert
  to anon, authenticated
  with check (true);

drop policy if exists "allow insert for anon and authenticated" on distributor;
create policy "allow insert for anon and authenticated"
  on distributor for insert
  to anon, authenticated
  with check (true);

drop policy if exists "allow insert for anon and authenticated" on inventory;
create policy "allow insert for anon and authenticated"
  on inventory for insert
  to anon, authenticated
  with check (true);

-- If any of these four errors with "row-level security is not
-- enabled" for a given table, that table doesn't have RLS on at all —
-- meaning it was never the source of the error you saw, and the DROP/
-- CREATE for it is harmless but unnecessary. If a DIFFERENT table not
-- listed here throws the same RLS error later, tell me its name and
-- I'll add the matching policy.
