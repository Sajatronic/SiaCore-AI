-- =====================================================================
-- SiaCore — Patch: full Distributors list page
-- =====================================================================
-- Run after your current 01_stored_procedures.sql (and
-- 07_part_details_distributor_patch.sql, if not already applied — this
-- reuses get_distributor_details from that file for the click-to-expand
-- modal). Then:
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

create or replace function get_all_distributors(
  p_search text default null,
  p_limit integer default 100,
  p_offset integer default 0
)
returns table (
  d_code text,
  d_name text,
  d_type text,
  d_country text,
  relationship_risk_level text,
  relationship_risk_score numeric,
  on_time_delivery_rate numeric,
  total_orders_placed numeric,
  last_modified_date timestamptz
)
language sql
stable
as $$
  select
    d."D_code",
    d."D_Name",
    d."D_Type",
    d."D_country",
    coalesce(d.relationship_risk_level, 'Unclassified'),
    d.relationship_risk_score,
    d.on_time_delivery_rate,
    d.total_orders_placed,
    d."Last_Modified_Date"
  from distributer d
  where (p_search is null
    or d."D_Name" ilike '%' || p_search || '%'
    or d."D_code" ilike '%' || p_search || '%'
    or d."D_country" ilike '%' || p_search || '%')
  order by d.relationship_risk_score desc nulls last, d."D_Name"
  limit p_limit offset p_offset;
$$;

grant execute on function get_all_distributors(text, integer, integer) to anon, authenticated;

NOTIFY pgrst, 'reload schema';
