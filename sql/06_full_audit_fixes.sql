-- =====================================================================
-- SiaCore — Patch: audit fixes (date-filter gaps, inventory KPIs, Extended Price)
-- =====================================================================
-- Run after siacore_stored_procedures.sql. Then: NOTIFY pgrst, 'reload schema';
--
-- 1. get_parts_with_stock — its inventory-risk lookup ignored p_start/p_end
--    entirely (every other lookup in the same function respects the date
--    range; this one was the one gap). Fixed by filtering on
--    inventory_risk."Last_Modified_Date", same pattern as the rest.
--
-- 2. get_part_details — "Current Inventory" / "Warehouse" came from a plain
--    unfiltered sum() over `inventory`, so those two fields never moved
--    when the calendar filter changed, unlike every risk card next to
--    them. Fixed by filtering on inventory.date.
--
-- 3. get_inventory_kpis — Total Available Stock / Minimum Stock /
--    Maximum Stock / Average Stock were never queried at all (not a bug
--    in existing logic, just never added). `inventory` already has
--    available_stock, min_stock, and max_stock columns, so these are
--    real aggregates, not calculated values.
--
-- 4. get_part_stock_suppliers / get_part_stock_summary — add
--    extended_price (stock."Extended_Price"), used directly rather than
--    recomputed, plus a real total_extended_value in the summary.
--
--    ASSUMPTION: "Extended_Price" is quoted/capitalized the same way as
--    its sibling stock columns ("Unit_Price", "Current_Stock", etc).
--    If your real column is cased differently, this is the one line to
--    adjust: st."Extended_Price" below.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. get_parts_with_stock — add missing date filter on inventory risk
-- ---------------------------------------------------------------------
do $$
declare r record;
begin
  for r in select oid::regprocedure as sig from pg_proc
    where proname = 'get_parts_with_stock' and pronamespace = 'public'::regnamespace
  loop execute format('drop function %s;', r.sig); end loop;
end $$;

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
      sr."Risk_Catagory"           as risk_category,
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
-- 2. get_part_details — filter current_inventory/warehouse by date too
-- ---------------------------------------------------------------------
do $$
declare r record;
begin
  for r in select oid::regprocedure as sig from pg_proc
    where proname = 'get_part_details' and pronamespace = 'public'::regnamespace
  loop execute format('drop function %s;', r.sig); end loop;
end $$;

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
  overall_part_score numeric
)
language sql
stable
as $$
  with latest_stock_risk as (
    select sr.mpn, sr."Risk_Catagory" as risk_category, sr."Final_Market_Risk_Score" as risk_score
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
  -- NOTE: now filtered by inventory.date, same range as everything else
  -- on this page. Previously this pulled ALL history for the mpn
  -- regardless of the selected date, so Current Inventory / Warehouse
  -- never changed when you moved the calendar filter.
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
    coalesce(lar.pars_category, 'Unknown')                                as alternative_risk_level,
    coalesce(lps.part_score, lsr.risk_score, 0)                           as overall_part_score
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

grant execute on function get_part_details(text, date, date) to anon, authenticated;

-- ---------------------------------------------------------------------
-- 3. get_inventory_kpis — add the missing stock statistics
-- ---------------------------------------------------------------------
do $$
declare r record;
begin
  for r in select oid::regprocedure as sig from pg_proc
    where proname = 'get_inventory_kpis' and pronamespace = 'public'::regnamespace
  loop execute format('drop function %s;', r.sig); end loop;
end $$;

create or replace function get_inventory_kpis(p_start date default null, p_end date default null)
returns table (
  total_qty_on_hand numeric,
  avg_stock_sufficiency_ratio numeric,
  avg_lead_time_days numeric,
  shortage_risk_sku_count integer,
  total_available_stock numeric,
  avg_available_stock numeric,
  min_stock numeric,
  max_stock numeric
)
language sql stable as $$
  select
    (select sum(qty_on_hand) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end)),
    round((select avg(stock_sufficiency_ratio) from inventory_risk k
       where (p_start is null or k."Last_Modified_Date"::date >= p_start) and (p_end is null or k."Last_Modified_Date"::date <= p_end))::numeric, 1),
    round((select avg(lead_time_days) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end))::numeric, 1),
    (select count(*) from inventory_risk k where k.risk_level in ('High', 'Critical')
       and (p_start is null or k."Last_Modified_Date"::date >= p_start) and (p_end is null or k."Last_Modified_Date"::date <= p_end))::int,
    -- NEW: real aggregates straight off inventory.available_stock/min_stock/max_stock —
    -- these columns already existed on the table but no function ever read them.
    (select sum(i.available_stock) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end)),
    round((select avg(i.available_stock) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end))::numeric, 1),
    round((select avg(i.min_stock) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end))::numeric, 1),
    round((select avg(i.max_stock) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end))::numeric, 1);
$$;

grant execute on function get_inventory_kpis(date, date) to anon, authenticated;

-- ---------------------------------------------------------------------
-- 4. get_part_stock_suppliers / get_part_stock_summary — Extended Price
-- ---------------------------------------------------------------------
do $$
declare r record;
begin
  for r in select oid::regprocedure as sig from pg_proc
    where proname = 'get_part_stock_suppliers' and pronamespace = 'public'::regnamespace
  loop execute format('drop function %s;', r.sig); end loop;
end $$;

create or replace function get_part_stock_suppliers(p_mpn text, p_start date default null, p_end date default null)
returns table (
  distributor_name text,
  distributor_code text,
  available_stock numeric,
  distributor_risk_level text,
  unit_price numeric,
  extended_price numeric,
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
    st."Extended_Price"                            as extended_price,
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
  order by coalesce(d."D_Name", st.distributer_code), st."Price_Break_Qty";
$$;

grant execute on function get_part_stock_suppliers(text, date, date) to anon, authenticated;

do $$
declare r record;
begin
  for r in select oid::regprocedure as sig from pg_proc
    where proname = 'get_part_stock_summary' and pronamespace = 'public'::regnamespace
  loop execute format('drop function %s;', r.sig); end loop;
end $$;

create or replace function get_part_stock_summary(p_mpn text, p_start date default null, p_end date default null)
returns table (
  total_stock numeric,
  supplier_count integer,
  lowest_price numeric,
  highest_price numeric,
  avg_price numeric,
  total_extended_value numeric
)
language sql
stable
as $$
  select
    sum(st."Current_Stock")::numeric,
    count(distinct st.distributer_code)::int,
    min(st."Unit_Price"),
    max(st."Unit_Price"),
    round(avg(st."Unit_Price")::numeric, 4),
    -- Real total, straight from Extended_Price — not recomputed as
    -- price * qty (that would double-count across price-break rows).
    sum(st."Extended_Price")::numeric
  from stock st
  where st.mpn = p_mpn
    and (p_start is null or st.scraped_at::date >= p_start)
    and (p_end is null or st.scraped_at::date <= p_end);
$$;

grant execute on function get_part_stock_summary(text, date, date) to anon, authenticated;
