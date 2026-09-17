-- =====================================================================
-- SiaCore — Patch: Part Details page overhaul
-- =====================================================================
-- Run after 03_parts_stock_and_fixes.sql (and 04_add_lifecycle_filter.sql
-- if you applied it). Then: NOTIFY pgrst, 'reload schema';
--
-- Changes:
--  1. get_part_details
--     - lifecycle_status now comes from stock."Lifecycle_Status" (latest
--       row within the selected date range), not a fabricated/absent field
--     - lead_time_days removed entirely
--     - image_url added, sourced from parts.image
--     - part_score now comes from the real part_score table instead of
--       being derived from stock_risk
--     - overall_part_score = same part_score value (single real source,
--       no manual weighted formula)
--     - stock_risk_score / stock_risk_level exposed as their own fields
--       (previously only folded into part_score, with no dedicated card)
--     - alternative_risk_level (fabricated from a row count) is REMOVED.
--       alternative_count is kept as a factual field; there is no
--       dedicated "alternative risk" table in the schema to source a
--       severity from, so the UI should show an empty state for it.
--     - manufacturer_risk / inventory_risk / compliance_risk now also
--       respect the selected date range (previously only compliance did)
--
--  2. get_part_stock_suppliers
--     - moq removed
--     - authorized added, from stock."Authorized_Dist"
--     - buy_link added, from stock.product_url
--     - last_updated renamed to scraped_at (same underlying column)
-- =====================================================================

create or replace function get_part_details(p_mpn text, p_start date default null, p_end date default null)
returns table (
  mpn text,
  manufacturer text,
  category text,
  description text,
  image_url text,
  M_Lifecycle_Status text,
  current_inventory numeric,
  warehouse_name text,
  part_score numeric,
  manufacturer_risk_score numeric,
  manufacturer_risk_level text,
  inventory_risk_score numeric,
  inventory_risk_level text,
  compliance_risk_score numeric,
  compliance_risk_level text,
  stock_risk_score numeric,
  stock_risk_level text,
  alternative_count integer,
  overall_part_score numeric
)
language sql
stable
as $$
  with latest_stock_risk as (
    select sr.mpn, sr."Risk_Category" as risk_category, sr."Final_Market_Risk_Score" as risk_score
    from stock_risk sr
    where sr.mpn = p_mpn
      and (p_start is null or sr."Last_Modified_Date"::date >= p_start)
      and (p_end is null or sr."Last_Modified_Date"::date <= p_end)
    order by sr."Last_Modified_Date" desc limit 1
  ),
  latest_part_score as (
    select ps.part_score
    from part_score ps
    where ps.mpn = p_mpn
      and (p_start is null or ps."Last_Modified_Date"::date >= p_start)
      and (p_end is null or ps."Last_Modified_Date"::date <= p_end)
    order by ps."Last_Modified_Date" desc limit 1
  ),
  latest_stock_row as (
    select st."M_Lifecycle_Status" as lifecycle_status
    from stock st
    where st.mpn = p_mpn
      and (p_start is null or st.scraped_at::date >= p_start)
      and (p_end is null or st.scraped_at::date <= p_end)
    order by st.scraped_at desc limit 1
  ),
  latest_inventory as (
    select i.mpn, sum(i.qty_on_hand) as qty_on_hand, max(w.warehouse_name) as warehouse_name
    from inventory i
    left join warehouses w on w.warehouse_id = i.warehouse_id
    where i.mpn = p_mpn
    group by i.mpn
  ),
  latest_inventory_risk as (
    select k.risk_level, k.risk_score
    from inventory_kpi k
    join inventory_forecast f on f.forecast_id = k.forecast_id
    join inventory i on i.inventory_id = f.inventory_id
    where i.mpn = p_mpn
      and (p_start is null or k."Last_Modified_Date"::date >= p_start)
      and (p_end is null or k."Last_Modified_Date"::date <= p_end)
    order by k."Last_Modified_Date" desc limit 1
  ),
  latest_compliance as (
    select
      pc."Mfr Part #",
      cr."Compliance_Risk_Tier" as risk_tier,
      cr.compliance_risk_score as risk_score
    from parts_compliance pc
    left join compliance_risk cr on pc.id = cr.compliance_id
    where pc."Mfr Part #" = p_mpn
      and (p_start is null or pc."Last_Modified_Date"::date >= p_start)
      and (p_end is null or pc."Last_Modified_Date"::date <= p_end)
    order by pc."Last_Modified_Date" desc
    limit 1
  ),
  latest_manufacturer_risk as (
    select mr.risk_score, mr.risk_level
    from manufacturers m
    join manufacturers_risk mr on mr."M_ID" = m.id
    where m.id = (select mfr_id from parts where mpn = p_mpn limit 1)
      and (p_start is null or mr."Last_Modified_Date"::date >= p_start)
      and (p_end is null or mr."Last_Modified_Date"::date <= p_end)
    order by mr."Last_Modified_Date" desc limit 1
  ),
  alt_count as (
    select count(*)::int as n from "Parts_Alternative" where "Mfr Part #" = p_mpn
  )
  select
    p.mpn,
    coalesce(m."Manufacturer", 'Unknown'),
    coalesce(pc."Name", 'Uncategorized'),
    coalesce(p.description, 'No description available'),
    p.image                                                               as image_url,
    lsw.lifecycle_status,
    li.qty_on_hand,
    li.warehouse_name,
    lps.part_score                                                        as part_score,
    mr.risk_score                                                         as manufacturer_risk_score,
    coalesce(mr.risk_level, 'Unknown')                                    as manufacturer_risk_level,
    lir.risk_score                                                        as inventory_risk_score,
    coalesce(lir.risk_level, 'Unknown')                                   as inventory_risk_level,
    lc.risk_score                                                         as compliance_risk_score,
    coalesce(lc.risk_tier, 'Unknown')                                     as compliance_risk_level,
    lsr.risk_score                                                        as stock_risk_score,
    coalesce(lsr.risk_category, 'Unknown')                                as stock_risk_level,
    coalesce(ac.n, 0)                                                     as alternative_count,
    lps.part_score                                                        as overall_part_score
  from parts p
  left join manufacturers m on m.id = p.mfr_id
  left join parts_category pc on pc.id = p."Mfr Category ID"
  left join latest_manufacturer_risk mr on true
  left join latest_stock_risk lsr on true
  left join latest_part_score lps on true
  left join latest_stock_row lsw on true
  left join latest_inventory li on true
  left join latest_inventory_risk lir on true
  left join latest_compliance lc on true
  left join alt_count ac on true
  where p.mpn = p_mpn
  limit 1;
$$;

grant execute on function get_part_details(text, date, date) to anon, authenticated;

-- ---------------------------------------------------------------------
-- get_part_stock_suppliers — authorized flag + buy link, drop MOQ
-- ---------------------------------------------------------------------
create or replace function get_part_stock_suppliers(p_mpn text, p_start date default null, p_end date default null)
returns table (
  distributor_name text,
  distributor_code text,
  available_stock numeric,
  distributor_risk_level text,
  unit_price numeric,
  packaging_type text,
  package_qty integer,
  authorized text,
  buy_link text,
  scraped_at timestamptz
)
language sql
stable
as $$
  select
    coalesce(d."D_Name", st.distributer_code)      as distributor_name,
    st.distributer_code,
    st."Current_Stock"                             as available_stock,
    coalesce(d.relationship_risk_level, 'Unknown') as distributor_risk_level,
    st."Unit_Price"                                as unit_price,
    st.packaging                                   as packaging_type,
    st."Price_Break_Qty"                           as package_qty,
    st."Authorized_Dist"                           as authorized,
    st.product_url                                 as buy_link,
    st.scraped_at
  from stock st
  left join distributer d on d."D_code" = st."distributer_code"
  where st.mpn = p_mpn
    and (p_start is null or st.scraped_at::date >= p_start)
    and (p_end is null or st.scraped_at::date <= p_end)
  order by st.scraped_at desc;
$$;

grant execute on function get_part_stock_suppliers(text, date, date) to anon, authenticated;
