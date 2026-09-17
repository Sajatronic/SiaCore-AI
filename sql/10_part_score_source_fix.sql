-- =====================================================================
-- SiaCore — Parts & Stock: Part Score sourced from part_score table
-- =====================================================================
-- FIX: get_parts_with_stock's "Part Score" column was computed from
-- stock_risk.risk_score (a copy-paste leftover from before "category"
-- was moved to part_score.part_category) instead of part_score.part_score
-- itself. Both values now come from the same latest_part_score CTE
-- (freshest row per mpn by Last_Modified_Date), so Part Risk and Part
-- Score are guaranteed to be from the same snapshot.
--
-- UPDATED: null fallback for the category/"Part Risk" column changed
-- from 'Uncategorized' to 'Unknown' — it's rendered as a RiskBadge now
-- (see PartsStock.jsx), and 'Uncategorized' doesn't match any of that
-- component's tones, so it fell back to the plain untoned gray style
-- instead of matching Inventory Risk / Stock Risk's "Unknown" look.
--
-- Also confirmed against your latest ERD: this file already joins
-- inventory_risk -> inventory on inventory_id (not mpn), which matches
-- the correction made in sql/11_inventory_table_names_fix.sql — no
-- change needed there.
--
-- UPDATED: default sort is now Part Risk ascending (Very Low first,
-- Critical last) instead of Part Score descending.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

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
      sr."risk_category"           as risk_category,
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
    from inventory_risk k
    join inventory i on i.inventory_id = k.inventory_id
    where (p_start is null or k."Last_Modified_Date"::date >= p_start)
      and (p_end is null or k."Last_Modified_Date"::date <= p_end)
    order by i.mpn, k."Last_Modified_Date" desc
  ),
  latest_stock as (
    select distinct on (s.mpn)
      s.mpn,
      s."Manufacturer_Lifecycle_Status" as lifecycle_status
    from stock s
    where (p_start is null or s.scraped_at::date >= p_start)
      and (p_end is null or s.scraped_at::date <= p_end)
    order by s.mpn, s.scraped_at desc
  ),
  latest_part_score as (
    -- FIXED: now selects part_score itself, not just part_category —
    -- Part Risk and Part Score both come from this one freshest row.
    select distinct on (ps.mpn)
      ps.mpn,
      ps.part_score,
      ps.part_category
    from part_score ps
    where (p_start is null or ps."Last_Modified_Date"::date >= p_start)
      and (p_end is null or ps."Last_Modified_Date"::date <= p_end)
    order by ps.mpn, ps."Last_Modified_Date" desc
  )
  select
    p.mpn,
    coalesce(m."Manufacturer", 'Unknown')          as manufacturer,
    coalesce(lps.part_category, 'Unknown')         as category,
    coalesce(lir.risk_level, 'Unknown')            as inventory_risk_level,
    lir.risk_score                                 as inventory_risk_score,
    coalesce(lsr.risk_category, 'Unknown')         as stock_risk_level,
    -- FIXED: was round(coalesce(lsr.risk_score, 0), 1) — stock_risk's
    -- score, not part_score's. Now reads from part_score directly.
    round(coalesce(lps.part_score, 0)::numeric, 1) as part_score,
    ls.lifecycle_status                            as lifecycle_status
  from parts p
  left join manufacturers m on m.id = p.mfr_id
  left join latest_stock_risk lsr on lsr.mpn = p.mpn
  left join latest_inventory_risk lir on lir.mpn = p.mpn
  left join latest_stock ls on ls.mpn = p.mpn
  left join latest_part_score lps on lps.mpn = p.mpn
  where (p_search is null or p.mpn ilike '%' || p_search || '%' or m."Manufacturer" ilike '%' || p_search || '%')
    and (p_lifecycle is null or ls.lifecycle_status = p_lifecycle)
  order by
    -- Very Low first, then Low, Medium, High, Critical, Unknown last.
    case coalesce(lps.part_category, 'Unknown')
      when 'Very Low' then 1
      when 'Low'      then 2
      when 'Medium'   then 3
      when 'High'     then 4
      when 'Critical' then 5
      else 6
    end,
    p.mpn
  limit p_limit offset p_offset;
$$;

grant execute on function get_parts_with_stock(text, text, date, date, integer, integer) to anon, authenticated;
