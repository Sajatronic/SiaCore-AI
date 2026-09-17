-- =====================================================================
-- SiaCore — Drop stale function overloads (the real Reports bug)
-- =====================================================================
-- Root cause: in Postgres, CREATE OR REPLACE FUNCTION only replaces an
-- existing function if the parameter list is IDENTICAL (same count and
-- types). Adding a new parameter — even with a default — creates a
-- SEPARATE, ADDITIONAL overloaded function; it does not replace the
-- old one. Several earlier files in this project added date-range (or
-- search) parameters to functions that already existed with fewer
-- parameters, which silently left the OLD version behind:
--
--   get_reports            1-arg (sql/03) survives next to 3-arg (sql/17)
--   get_recent_events       4-arg (sql/03) survives next to 5-arg (sql/12)
--   get_inventory_kpis      0-arg (sql/01) survives next to 2-arg (sql/03)
--   get_inventory_records   3-arg, no dates (sql/01) survives next to
--                           5-arg with dates (sql/03)
--
-- Depending on exactly which named parameters a given RPC call
-- includes, PostgREST can resolve to either overload — which is
-- exactly why `select * from get_reports(50, null, null)` worked fine
-- in the SQL editor (an unambiguous 3-arg positional call) while the
-- app, calling by named JSON parameters, could still be routed to the
-- old 1-arg version that knows nothing about date filtering and reads
-- from a different/empty source.
--
-- This drops every old-signature version so each function name maps
-- to exactly one implementation, with no ambiguity possible.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

drop function if exists get_reports(integer);
drop function if exists get_recent_events(integer, integer, date, date);
drop function if exists get_inventory_kpis();
drop function if exists get_inventory_records(text, integer, integer);

-- Sanity check — each of these should return exactly 1 row after
-- running this file. If any return 2+, there's still another stale
-- overload somewhere this file didn't account for; paste the output
-- and I'll add the matching DROP.
select 'get_reports' as fn, count(*) from pg_proc where proname = 'get_reports'
union all
select 'get_recent_events', count(*) from pg_proc where proname = 'get_recent_events'
union all
select 'get_inventory_kpis', count(*) from pg_proc where proname = 'get_inventory_kpis'
union all
select 'get_inventory_records', count(*) from pg_proc where proname = 'get_inventory_records';
