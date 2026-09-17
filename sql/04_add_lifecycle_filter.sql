-- =====================================================================
-- SiaCore — Patch: add lifecycle filtering to get_parts_with_stock
-- =====================================================================
-- Lifecycle_Status lives on the `stock` table (not on `parts`), so we
-- pull the most recent stock row per mpn (by scraped_at) the same way
-- latest_stock_risk / latest_inventory_risk already do, and filter on
-- that.
-- Run this AFTER sql/03_parts_stock_and_fixes.sql.
-- Then run: NOTIFY pgrst, 'reload schema';
-- =====================================================================

drop function if exists get_parts_with_stock(text, date, date, integer, integer);

create or replace function get_parts_with_stock(
  p_search text default null,
  p_lifecycle text default null,
  p_start date default null,
  p_end date default null,
  p_limit integer default 50,
  p_offset integer default 0
)
returns table (
  mpn text,
  manufacturer text,
  category text,
  inventory_risk_level text,
  inventory_risk_score numeric,
  stock_risk_level text,
  part_score numeric,
  lifecycle_status text
)
language sql
stable
as $$
  with latest_stock_risk as (
    select distinct on (sr.mpn)
      sr.mpn,
      sr."Risk_Category"           as risk_category,
      sr."Final_Market_Risk_Score" as risk_score,
      sr."Last_Modified_Date"      as last_modified
    from stock_risk sr
    where (p_start is null or sr."Last_Modified_Date"::date >= p_start)
      and (p_end is null or sr."Last_Modified_Date"::date <= p_end)
    order by sr.mpn, sr."Last_Modified_Date" desc
  ),
  latest_inventory_risk as (
    select distinct on (i.mpn)
      i.mpn,
      k.risk_level,
      k.risk_score
    from inventory_kpi k
    join inventory_forecast f on f.forecast_id = k.forecast_id
    join inventory i on i.inventory_id = f.inventory_id
    order by i.mpn, k."Last_Modified_Date" desc
  ),
  latest_stock as (
    select distinct on (s.mpn)
      s.mpn,
      s."M_Lifecycle_Status" as lifecycle_status
    from stock s
    where (p_start is null or s.scraped_at::date >= p_start)
      and (p_end is null or s.scraped_at::date <= p_end)
    order by s.mpn, s.scraped_at desc
  )
  select
    p.mpn,
    coalesce(m."Manufacturer", 'Unknown')          as manufacturer,
    coalesce(pc."Name", 'Uncategorized')           as category,
    coalesce(lir.risk_level, 'Unknown')            as inventory_risk_level,
    lir.risk_score                                 as inventory_risk_score,
    coalesce(lsr.risk_category, 'Unknown')         as stock_risk_level,
    round(coalesce(lsr.risk_score, 0)::numeric, 1) as part_score,
    ls.lifecycle_status                            as lifecycle_status
  from parts p
  left join manufacturers m on m.id = p.mfr_id
  left join parts_category pc on pc.id = p."Mfr Category ID"
  left join latest_stock_risk lsr on lsr.mpn = p.mpn
  left join latest_inventory_risk lir on lir.mpn = p.mpn
  left join latest_stock ls on ls.mpn = p.mpn
  where (p_search is null or p.mpn ilike '%' || p_search || '%' or m."Manufacturer" ilike '%' || p_search || '%')
    and (p_lifecycle is null or ls.lifecycle_status = p_lifecycle)
  order by part_score desc nulls last, p.mpn
  limit p_limit offset p_offset;
$$;

grant execute on function get_parts_with_stock(text, text, date, date, integer, integer) to anon, authenticated;

-- ---------------------------------------------------------------------
-- NEW: distinct lifecycle statuses, for populating a filter dropdown
-- ---------------------------------------------------------------------
create or replace function get_lifecycle_statuses()
returns table (lifecycle_status text)
language sql
stable
as $$
  select distinct s."M_Lifecycle_Status"
  from stock s
  where s."M_Lifecycle_Status" is not null
  order by 1;
$$;

grant execute on function get_lifecycle_statuses() to anon, authenticated;
