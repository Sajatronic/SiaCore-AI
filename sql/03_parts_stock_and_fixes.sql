-- =====================================================================
-- SiaCore — Phase 1: Parts & Stock / Part Details / Inventory / News
-- =====================================================================
-- Run this AFTER sql/01_stored_procedures.sql.
-- Then run: NOTIFY pgrst, 'reload schema';
-- =====================================================================

-- ---------------------------------------------------------------------
-- FIX: get_dashboard_summary
-- ---------------------------------------------------------------------
create or replace function get_dashboard_summary(p_start date default null, p_end date default null)
returns table (
  overall_risk_score numeric,
  risk_score_trend numeric,
  compliant_parts_pct numeric,
  non_compliant_count integer,
  optimization_score numeric,
  tracked_sku_count integer,
  new_sku_count integer
)
language sql
stable
as $$
  select
    (select round(avg(dr.final_risk_score)::numeric, 1)
       from "distribution_risk" dr
       where (p_start is null or dr."Last_Modified_Date"::date >= p_start)
         and (p_end is null or dr."Last_Modified_Date"::date <= p_end))          as overall_risk_score,

    (select round((
        (avg(dr.final_risk_score) filter (where dr."Last_Modified_Date" > now() - interval '30 days')
         - avg(dr.final_risk_score) filter (where dr."Last_Modified_Date" <= now() - interval '30 days'))
        / nullif(avg(dr.final_risk_score) filter (where dr."Last_Modified_Date" <= now() - interval '30 days'), 0) * 100
      )::numeric, 1)
       from "distribution_risk" dr
       where (p_start is null or dr."Last_Modified_Date"::date >= p_start)
         and (p_end is null or dr."Last_Modified_Date"::date <= p_end))          as risk_score_trend,

    (select round((100.0 * count(*) filter (where cr."Compliance_Risk_Tier" = 'Low')
        / nullif(count(*), 0))::numeric, 1)
       from parts_compliance pc
       left join compliance_risk cr on pc.id = cr.compliance_id
       where (p_start is null or pc."Last_Modified_Date"::date >= p_start)
         and (p_end is null or pc."Last_Modified_Date"::date <= p_end))                as compliant_parts_pct,

    (select count(*) filter (where cr.hard_stop_flag is true)::int
       from parts_compliance pc
       left join compliance_risk cr on pc.id = cr.compliance_id
       where (p_start is null or pc."Last_Modified_Date"::date >= p_start)
         and (p_end is null or pc."Last_Modified_Date"::date <= p_end))                as non_compliant_count,

    coalesce((select round(avg(100 - kpi.risk_score)::numeric, 1) from inventory_kpi kpi), 0) as optimization_score,

    (select count(distinct mpn) from stock
       where (p_start is null or "scraped_at"::date >= p_start)
         and (p_end is null or "scraped_at"::date <= p_end))::int               as tracked_sku_count,

    (select count(distinct mpn) from stock where "scraped_at" > now() - interval '30 days')::int as new_sku_count;
$$;

-- ---------------------------------------------------------------------
-- NEW: Parts & Stock table
-- ---------------------------------------------------------------------
create or replace function get_parts_with_stock(
  p_search text default null,
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
  part_score numeric
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
  )
  select
    p.mpn,
    coalesce(m."Manufacturer", 'Unknown')          as manufacturer,
    coalesce(pc."Name", 'Uncategorized')           as category, 
    coalesce(lir.risk_level, 'Unknown')            as inventory_risk_level,
    lir.risk_score                                 as inventory_risk_score,
    coalesce(lsr.risk_category, 'Unknown')         as stock_risk_level,
    round(coalesce(lsr.risk_score, 0)::numeric, 1) as part_score
  from parts p
  left join manufacturers m on m.id = p.mfr_id
  left join parts_category pc on pc.id = p."Mfr Category ID" 
  left join latest_stock_risk lsr on lsr.mpn = p.mpn
  left join latest_inventory_risk lir on lir.mpn = p.mpn
  where (p_search is null or p.mpn ilike '%' || p_search || '%' or m."Manufacturer" ilike '%' || p_search || '%')
  order by part_score desc nulls last, p.mpn
  limit p_limit offset p_offset;
$$;

-- ---------------------------------------------------------------------
-- NEW: Part Details page
-- ---------------------------------------------------------------------
create or replace function get_part_details(p_mpn text, p_start date default null, p_end date default null)
returns table (
  mpn text,
  manufacturer text,
  category text,
  description text,
  lead_time_days integer,
  current_inventory numeric,
  warehouse_name text,
  part_score numeric,
  manufacturer_risk_score numeric,
  manufacturer_risk_level text,
  inventory_risk_score numeric,
  inventory_risk_level text,
  compliance_risk_score numeric,
  compliance_risk_level text,
  alternative_count integer,
  alternative_risk_level text,
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
  alt_count as (
    select count(*)::int as n from "Parts_Alternative" where "Mfr Part #" = p_mpn
  )
  select
    p.mpn,
    coalesce(m."Manufacturer", 'Unknown'),
    coalesce(pc."Name", 'Uncategorized'), 
    coalesce(p.description, 'No description available'),
    s.lead_time_days,
    li.qty_on_hand,
    li.warehouse_name,
    round(coalesce(lsr.risk_score, 0)::numeric, 1)                          as part_score,
    mr.risk_score                                                          as manufacturer_risk_score,
    coalesce(mr.risk_level, 'Unknown')                                     as manufacturer_risk_level,
    lir.risk_score                                                        as inventory_risk_score,
    coalesce(lir.risk_level, 'Unknown')                                   as inventory_risk_level,
    lc.risk_score                                                         as compliance_risk_score,
    coalesce(lc.risk_tier, 'Unknown')                                     as compliance_risk_level,
    coalesce(ac.n, 0)                                                     as alternative_count,
    case when coalesce(ac.n, 0) = 0 then 'High' when ac.n = 1 then 'Medium' else 'Low' end as alternative_risk_level,
    round((
      coalesce(lsr.risk_score, 0) * 0.35
      + coalesce(mr.risk_score, 0) * 0.25
      + coalesce(lir.risk_score, 0) * 0.2
      + coalesce(lc.risk_score, 0) * 0.2
    )::numeric, 1)                                                        as overall_part_score
  from parts p
  left join manufacturers m on m.id = p.mfr_id
  left join parts_category pc on pc.id= p."Mfr Category ID" 
  left join manufacturers_risk mr on mr."M_ID" = m.id
  left join latest_stock_risk lsr on true
  left join latest_inventory li on true
  left join latest_inventory_risk lir on true
  left join latest_compliance lc on true
  left join alt_count ac on true
  left join lateral (
    select st.lead_time_days from stock st where st.mpn = p.mpn order by st.scraped_at desc limit 1
  ) s on true
  where p.mpn = p_mpn
  limit 1;
$$;

-- ---------------------------------------------------------------------
-- NEW: Part Details — per-distributor stock table + rollup summary
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
  moq integer,
  last_updated timestamptz
)
language sql
stable
as $$
  select
    coalesce(d."D_Name", st.distributer_code)  as distributor_name,
    st.distributer_code,
    st."Current_Stock"                         as available_stock,
    coalesce(d.relationship_risk_level, 'Unknown') as distributor_risk_level,
    st."Unit_Price"                            as unit_price,
    st.packaging                               as packaging_type,
    st."Price_Break_Qty"                       as package_qty,
    st.moq,
    st.scraped_at                              as last_updated
  from stock st
  left join distributer d on d."D_code" = st."distributer_code"
  where st.mpn = p_mpn
    and (p_start is null or st.scraped_at::date >= p_start)
    and (p_end is null or st.scraped_at::date <= p_end)
  order by st.scraped_at desc;
$$;

create or replace function get_part_stock_summary(p_mpn text, p_start date default null, p_end date default null)
returns table (
  total_stock numeric,
  supplier_count integer,
  lowest_price numeric,
  highest_price numeric,
  avg_price numeric
)
language sql
stable
as $$
  select
    sum(st."Current_Stock")::numeric,
    count(distinct st.distributer_code)::int,
    min(st."Unit_Price"),
    max(st."Unit_Price"),
    round(avg(st."Unit_Price")::numeric, 4)
  from stock st
  where st.mpn = p_mpn
    and (p_start is null or st.scraped_at::date >= p_start)
    and (p_end is null or st.scraped_at::date <= p_end);
$$;

-- ---------------------------------------------------------------------
-- UPDATED: Inventory Records
-- ---------------------------------------------------------------------
create or replace function get_inventory_records(
  p_warehouse_id text default null,
  p_start date default null,
  p_end date default null,
  p_limit integer default 100,
  p_offset integer default 0
)
returns table (
  inventory_id text,
  record_date date,
  mpn text,
  risk_level text,
  qty_on_hand numeric,
  available_stock numeric,
  reorder_point numeric,
  warehouse_name text,
  stock_status text
)
language sql
stable
as $$
  select
    i.inventory_id::text,
    i.date::date                                as record_date,
    i.mpn,
    coalesce(k.risk_level, 'Unknown')           as risk_level,
    i.qty_on_hand,
    i.available_stock,
    fc.reorder_point,
    w.warehouse_name,
    i.stock_status
  from inventory i
  left join warehouses w on w.warehouse_id = i.warehouse_id
  left join lateral (
    select f.reorder_point from inventory_forecast f
    where f.inventory_id = i.inventory_id order by f.forecast_date desc limit 1
  ) fc on true
  left join lateral (
    select ik.risk_level 
    from inventory_kpi ik
    join inventory_forecast f on f.forecast_id = ik.forecast_id
    where f.inventory_id = i.inventory_id 
    order by ik."Last_Modified_Date" desc limit 1
  ) k on true
  where (p_warehouse_id is null or i.warehouse_id = p_warehouse_id)
    and (p_start is null or i.date::date >= p_start)
    and (p_end is null or i.date::date <= p_end)
  order by i.date desc nulls last, i."Last_Modified_Date" desc nulls last
  limit p_limit offset p_offset;
$$;

create or replace function get_inventory_kpis(p_start date default null, p_end date default null)
returns table (total_qty_on_hand numeric, avg_stock_sufficiency_ratio numeric, avg_lead_time_days numeric, shortage_risk_sku_count integer)
language sql stable as $$
  select
    (select sum(qty_on_hand) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end)),
    round((select avg(stock_sufficiency_ratio) from inventory_kpi k
       where (p_start is null or k."Last_Modified_Date"::date >= p_start) and (p_end is null or k."Last_Modified_Date"::date <= p_end))::numeric, 1),
    round((select avg(lead_time_days) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end))::numeric, 1),
    (select count(*) from inventory_kpi k where k.risk_level in ('High', 'Critical')
       and (p_start is null or k."Last_Modified_Date"::date >= p_start) and (p_end is null or k."Last_Modified_Date"::date <= p_end))::int;
$$;

-- ---------------------------------------------------------------------
-- NEW: News & Risk Events screen
-- ---------------------------------------------------------------------
create or replace function get_recent_events(
  p_severity_min integer default 0,
  p_limit integer default 50,
  p_start date default null,
  p_end date default null
)
returns table (
  event_id text,
  title text,
  summary text,
  severity_signal text,
  retrieved_at timestamptz
)
language sql
stable
as $$
  select distinct on (re.title)
    re.event_id::text,
    re.title,
    re.summary,
    coalesce(re.severity_signal #>> '{}', 'Unclassified') as severity_signal,
    re.retrieval_timestamp                                 as retrieved_at
  from risk_events re
  where re.status::text is distinct from 'closed'
    and (p_start is null or re.retrieval_timestamp::date >= p_start)
    and (p_end is null or re.retrieval_timestamp::date <= p_end)
  order by re.title, re.retrieval_timestamp desc
  limit p_limit;
$$;

create or replace function get_recent_alerts(p_limit integer default 50, p_start date default null, p_end date default null)
returns table (
  id text,
  rule_name text,
  matched_at timestamptz
)
language sql
stable
as $$
  select distinct on (am.rule_name, am.matched_at)
    am.id::text,
    am.rule_name,
    am.matched_at
  from alert_matches am
  where (p_start is null or am.matched_at::date >= p_start)
    and (p_end is null or am.matched_at::date <= p_end)
  order by am.rule_name, am.matched_at desc
  limit p_limit;
$$;

-- ---------------------------------------------------------------------
-- NEW: Reports screen
-- ---------------------------------------------------------------------
-- create or replace function get_reports(p_limit integer default 50)
-- returns table (
--   id text,
--   title text,
--   report_type text,
--   created_at timestamptz
-- )
-- language sql
-- stable
-- as $$
--   select r.id::text, r.title, r.report_type, r."Last_Modified_Date"
--   from reports r
--   order by r."Last_Modified_Date" desc
--   limit p_limit;
-- $$;

-- ---------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------
grant execute on function
  get_dashboard_summary(date, date),
  get_parts_with_stock(text, date, date, integer, integer),
  get_part_details(text, date, date),
  get_part_stock_suppliers(text, date, date),
  get_part_stock_summary(text, date, date),
  get_inventory_records(text, date, date, integer, integer),
  get_inventory_kpis(date, date),
  get_recent_events(integer, integer, date, date),
  get_recent_alerts(integer, date, date)
  -- get_reports(integer)
to anon, authenticated;