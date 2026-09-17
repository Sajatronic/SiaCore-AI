-- =====================================================================
-- SiaCore — Part Details fixes: category freshness, latest-scrape-only
-- distributor pricing, authorized-first ordering, correct extended price
-- =====================================================================
-- Run after your existing migrations. This CREATE OR REPLACEs two
-- functions by name/signature — it doesn't matter which earlier file
-- originally defined them.
--   NOTIFY pgrst, 'reload schema';
--
-- FIXES:
-- 1. get_part_details returned the freshest part_score row correctly
--    (order by "Last_Modified_Date" desc limit 1 was already right) but
--    aliased it `overall_risk_level` — the frontend's Overall Part Score
--    card reads `detail.part_category`, so the column never showed up.
--    Renamed to match.
-- 2. get_part_stock_suppliers returned every historical scrape row for
--    a part, not just the latest one — that's why the same "1+" tier
--    showed three different prices (Anlinkda screenshot) and why the
--    price range / extended price were wrong: they were being computed
--    across multiple scrape dates instead of one snapshot in time.
--    Fixed by pinning every row to MAX(scraped_at) per distributor.
-- 3. Authorized distributors weren't sorted first. Fixed with an
--    explicit ORDER BY on Authorized_Dist.
-- 4. Extended price is now always recomputed as unit_price × quantity
--    break instead of trusting the raw (sometimes stale/inconsistent)
--    Extended_Price column.
-- =====================================================================

-- ---------------------------------------------------------------------
-- FIX: get_part_details — part_category now aliased correctly
-- ---------------------------------------------------------------------
create or replace function get_part_details(p_mpn text, p_start date default null, p_end date default null)
returns table (
  mpn text,
  manufacturer text,
  category text,
  description text,
  image_url text,
  lifecycle_status text,
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
  alternative_risk_level text,
  overall_part_score numeric,
  part_category text
)
language sql
stable
as $$
  with latest_stock_risk as (
    select sr.mpn, sr."risk_category" as risk_category, sr."Final_Market_Risk_Score" as risk_score
    from stock_risk sr
    where sr.mpn = p_mpn
      and (p_start is null or sr."Last_Modified_Date"::date >= p_start)
      and (p_end is null or sr."Last_Modified_Date"::date <= p_end)
    order by sr."Last_Modified_Date" desc limit 1
  ),
  latest_part_score as (
    -- max(Last_Modified_Date) per mpn — this already picked the freshest
    -- row; the only bug was the column alias below, not this ordering.
    select ps.part_score, ps.part_category
    from part_score ps
    where ps.mpn = p_mpn
      and (p_start is null or ps."Last_Modified_Date"::date >= p_start)
      and (p_end is null or ps."Last_Modified_Date"::date <= p_end)
    order by ps."Last_Modified_Date" desc limit 1
  ),
  latest_stock_row as (
    select st."Manufacturer_Lifecycle_Status" as lifecycle_status
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
      and (p_start is null or i.date::date >= p_start)
      and (p_end is null or i.date::date <= p_end)
    group by i.mpn
  ),
  latest_inventory_risk as (
    select k.risk_level, k.risk_score
    from inventory_risk k
    join inventory i on i.inventory_id = k.inventory_id
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
  latest_alt_risk as (
    select ar.n_real_alts, ar."best_ASR" as best_asr, ar.redundancy_credit,
           ar."PARS" as pars, ar."PARS_category" as pars_category
    from alternatives_risk ar
    where ar.mpn = p_mpn
      and (p_start is null or ar."Last_Modified_Date"::date >= p_start)
      and (p_end is null or ar."Last_Modified_Date"::date <= p_end)
    order by ar."Last_Modified_Date" desc limit 1
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
    li.qty_on_hand                                                        as current_inventory,
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
    coalesce(lar.pars_category, 'Unknown')                                as alternative_risk_level,
    coalesce(lps.part_score, lsr.risk_score, 0)                           as overall_part_score,
    -- FIXED: was aliased `overall_risk_level` — frontend reads
    -- `detail.part_category` (see RiskCard "Overall Part Score" in
    -- PartDetails.jsx), so it always rendered "Unknown".
    coalesce(lps.part_category, 'Unknown')                                as part_category
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
  left join latest_alt_risk lar on true
  left join alt_count ac on true
  where p.mpn = p_mpn
  limit 1;
$$;


-- ---------------------------------------------------------------------
-- FIX: get_part_stock_suppliers — latest scrape batch only, authorized
--      distributors first, extended price recomputed correctly.
-- ---------------------------------------------------------------------
create or replace function get_part_stock_suppliers(p_mpn text, p_start date default null, p_end date default null)
returns table (
  distributor_code text,
  distributor_name text,
  distributor_risk_level text,
  available_stock numeric,
  authorized text,
  buy_link text,
  scraped_at timestamptz,
  packaging_type text,
  package_qty numeric,
  unit_price numeric,
  extended_price numeric
)
language sql
stable
as $$
  with latest_scrape as (
    -- The exact max(scraped_at) timestamp per distributor for this part.
    -- FIXED (again): exact-timestamp equality dropped every row but one
    -- (each price-break row in a scrape run lands a few seconds apart),
    -- and matching on calendar date alone was too loose (it could pull
    -- in an entirely separate scrape run from earlier the same day, or
    -- split one run that crosses midnight into two "different" days).
    -- The real signal that two rows belong to the same scrape run is
    -- that their timestamps are only seconds apart — so instead we take
    -- the true max timestamp, then match every row within a few seconds
    -- of it, in either direction.
    select st.distributor_code, max(st.scraped_at) as max_scraped_at
    from stock st
    where st.mpn = p_mpn
      and (p_start is null or st.scraped_at::date >= p_start)
      and (p_end is null or st.scraped_at::date <= p_end)
    group by st.distributor_code
  ),
  latest_distributor_risk as (
    select distinct on (dr.d_code) dr.d_code, dr.risk_level
    from distribution_risk dr
    order by dr.d_code, dr."Last_Modified_Date" desc
  )
  select
    st.distributor_code,
    coalesce(d."D_Name", st.distributor_code)            as distributor_name,
    coalesce(ldr.risk_level, 'Unknown')                  as distributor_risk_level,
    st."Current_Stock"                                   as available_stock,
    st."Authorized_Dist"                                 as authorized,
    st.product_url                                       as buy_link,
    st.scraped_at,
    st.packaging                                         as packaging_type,
    st."Price_Break_Qty"                                 as package_qty,
    st."Unit_Price"                                      as unit_price,
    -- FIXED: recompute rather than trust the raw Extended_Price column,
    -- which disagreed with unit_price * qty on stale/bad scrape rows
    -- (see the Anlinkda "1,000+" tier in the screenshot: $0.451 x 1,000
    -- should be $451, and the raw column matched here but not on every
    -- row — recomputing guarantees it's always internally consistent).
    round((st."Unit_Price" * coalesce(st."Price_Break_Qty", 1))::numeric, 4) as extended_price
  from stock st
  join latest_scrape ls
    on ls.distributor_code = st.distributor_code
   -- within 5 seconds of the batch's max timestamp, either side
   and st.scraped_at between ls.max_scraped_at - interval '5 seconds'
                          and ls.max_scraped_at + interval '5 seconds'
  left join distributor d on d.d_code = st.distributor_code
  left join latest_distributor_risk ldr on ldr.d_code = st.distributor_code
  where st.mpn = p_mpn
  order by
    -- Authorized distributors first...
    case
      when lower(coalesce(st."Authorized_Dist", '')) like 'auth%'
        or lower(coalesce(st."Authorized_Dist", '')) in ('yes', 'y', 'true', '1')
      then 0 else 1
    end,
    -- ...then group each distributor's own tiers together, cheapest first.
    st.distributor_code,
    st."Price_Break_Qty" asc nulls last;
$$;

grant execute on function get_part_details(text, date, date) to anon, authenticated;
grant execute on function get_part_stock_suppliers(text, date, date) to anon, authenticated;

-- NOTE: this assumes your distributor table is named `distributor`
-- (matching the ERD). An earlier file in this project (03) referenced
-- `distributer` (typo) for the same join — if that's actually the real
-- table name in your DB, swap it back here too.


-- ---------------------------------------------------------------------
-- FIX: get_parts_with_stock — "Category" now comes from part_score's
-- freshest row (part_score.part_category, max Last_Modified_Date),
-- not the static parts_category lookup (which has no timestamp, so it
-- can't be what you meant by "the category where the max of
-- Last_Modified_Date"). Keeps the distinct-on structure you already
-- built for stock_risk / inventory_risk / lifecycle — this only swaps
-- the category source.
-- ---------------------------------------------------------------------
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
    -- FIXED: category now sourced here (max Last_Modified_Date per mpn)
    -- instead of the static parts_category join.
    select distinct on (ps.mpn)
      ps.mpn,
      ps.part_category
    from part_score ps
    where (p_start is null or ps."Last_Modified_Date"::date >= p_start)
      and (p_end is null or ps."Last_Modified_Date"::date <= p_end)
    order by ps.mpn, ps."Last_Modified_Date" desc
  )
  select
    p.mpn,
    coalesce(m."Manufacturer", 'Unknown')          as manufacturer,
    coalesce(lps.part_category, 'Uncategorized')   as category,
    coalesce(lir.risk_level, 'Unknown')            as inventory_risk_level,
    lir.risk_score                                 as inventory_risk_score,
    coalesce(lsr.risk_category, 'Unknown')         as stock_risk_level,
    round(coalesce(lsr.risk_score, 0)::numeric, 1) as part_score,
    ls.lifecycle_status                            as lifecycle_status
  from parts p
  left join manufacturers m on m.id = p.mfr_id
  left join latest_stock_risk lsr on lsr.mpn = p.mpn
  left join latest_inventory_risk lir on lir.mpn = p.mpn
  left join latest_stock ls on ls.mpn = p.mpn
  left join latest_part_score lps on lps.mpn = p.mpn
  where (p_search is null or p.mpn ilike '%' || p_search || '%' or m."Manufacturer" ilike '%' || p_search || '%')
    and (p_lifecycle is null or ls.lifecycle_status = p_lifecycle)
  order by part_score desc nulls last, p.mpn
  limit p_limit offset p_offset;
$$;

grant execute on function get_parts_with_stock(text, text, date, date, integer, integer) to anon, authenticated;
