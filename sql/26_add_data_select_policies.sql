-- =====================================================================
-- FIX: SELECT policies for the four Add Data tables
-- =====================================================================
-- api.insertRow does `.insert(row).select()` — the trailing .select()
-- asks Postgres to hand back the row it just wrote, which needs its
-- own SELECT permission under RLS, separate from the INSERT policies
-- added in sql/24. Without it, an insert can succeed at the database
-- level while the API call still surfaces as an error to the frontend,
-- because the read-back half of the request gets rejected.
--
-- This closes that gap the same way sql/24 did for INSERT: a
-- permissive SELECT policy for anon + authenticated on all four
-- tables. Same security note as sql/24 applies — this makes these
-- tables readable by anyone holding your public anon key, which is
-- normal for an app with no login screen, but worth being deliberate
-- about.
--
-- NOTE: if any of these tables can already be read elsewhere in the
-- app (e.g. Parts & Stock search already shows parts data), they
-- likely already HAVE a working SELECT policy, and this is a no-op for
-- those specific tables — safe to run regardless.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

drop policy if exists "allow select for anon and authenticated" on manufacturers;
create policy "allow select for anon and authenticated"
  on manufacturers for select
  to anon, authenticated
  using (true);

drop policy if exists "allow select for anon and authenticated" on parts;
create policy "allow select for anon and authenticated"
  on parts for select
  to anon, authenticated
  using (true);

drop policy if exists "allow select for anon and authenticated" on distributor;
create policy "allow select for anon and authenticated"
  on distributor for select
  to anon, authenticated
  using (true);

drop policy if exists "allow select for anon and authenticated" on inventory;
create policy "allow select for anon and authenticated"
  on inventory for select
  to anon, authenticated
  using (true);
