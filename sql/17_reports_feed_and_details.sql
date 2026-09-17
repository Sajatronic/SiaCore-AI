-- =====================================================================
-- SiaCore — Reports: unified feed + detail views
-- =====================================================================
-- Per your ERD, there are two distinct report tables — inventory_report
-- (one row per inventory risk report) and part_report (one row per
-- part risk report) — each with dozens of columns (supplier_*, buy_*,
-- alt_*, ltb_*, plus free-text explanation/recommendation fields).
--
-- get_reports below merges both into one list. The two detail
-- functions return the FULL row as jsonb rather than enumerating every
-- column by name — several of your column names were truncated in the
-- screenshot (supplier_distributor_ris..., supplier_has_authorized_...)
-- and guessing at the exact name would just break on a typo. Returning
-- the whole row sidesteps that: the frontend renders known fields by
-- name and falls back to a generic key/value grid for anything else,
-- so nothing is silently dropped even where I couldn't read the full
-- column name.
--
-- NOTE: an earlier, lower-resolution screenshot led me to read
-- part_report's date column as `Last_Modified_by` — a clearer version
-- confirms it's actually `Last_Modified_Date`, same as inventory_report.
-- Fixed below.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

create or replace function get_reports(p_limit integer default 50, p_start date default null, p_end date default null)
returns table (
  report_id text,
  report_type text,
  mpn text,
  summary text,
  score_label text,
  priority text,
  created_at timestamptz
)
language sql
stable
as $$
  select ir.id::text, 'inventory', ir."MPN",
         coalesce(ir."Executive Summary", 'Inventory report'),
         coalesce(ir."Risk Level", 'Unknown'),
         coalesce(ir."Priority", 'Unknown'),
         ir."Last_Modified_Date"
  from inventory_report ir
  where (p_start is null or ir."Last_Modified_Date"::date >= p_start)
    and (p_end is null or ir."Last_Modified_Date"::date <= p_end)
  union all
  select pr.id::text, 'part', pr."MPN",
         coalesce(pr."Executive Summary", 'Part report'),
         coalesce(pr."Stock Band", 'Unknown'),
         coalesce(pr."Priority", 'Unknown'),
         pr."Last_Modified_Date"
  from part_report pr
  where (p_start is null or pr."Last_Modified_Date"::date >= p_start)
    and (p_end is null or pr."Last_Modified_Date"::date <= p_end)
  order by created_at desc nulls last
  limit p_limit;
$$;

-- Full row as jsonb — see note above on why this isn't column-enumerated.
create or replace function get_inventory_report(p_id bigint)
returns jsonb
language sql
stable
as $$
  select to_jsonb(t) from inventory_report t where t.id = p_id;
$$;

create or replace function get_part_report(p_id bigint)
returns jsonb
language sql
stable
as $$
  select to_jsonb(t) from part_report t where t.id = p_id;
$$;

grant execute on function get_reports(integer, date, date) to anon, authenticated;
grant execute on function get_inventory_report(bigint) to anon, authenticated;
grant execute on function get_part_report(bigint) to anon, authenticated;
