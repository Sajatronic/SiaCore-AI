-- =====================================================================
-- SiaCore / NexusFlow AI — Supabase stored procedures (Postgres functions)
-- =====================================================================
-- Run this in the Supabase SQL editor (or via `supabase db push` / psql).
-- Every function is exposed automatically as a REST RPC endpoint at
--   POST /rest/v1/rpc/<function_name>
-- and is called from the frontend via supabase.rpc('<function_name>', {...}),
-- see src/lib/supabaseClient.js.
--
-- IMPORTANT — run this after ANY change to a function below:
--
--   NOTIFY pgrst, 'reload schema';
--
-- Supabase's REST layer (PostgREST) caches function signatures. After
-- `create or replace function` — especially switching `language sql` to
-- `language plpgsql`, like get_database_totals below — PostgREST can
-- keep serving the OLD cached version for up to ~60 seconds. That looks
-- exactly like "I fixed the bug and it's still returning nothing." The
-- NOTIFY forces an immediate reload. It's also at the bottom of this
-- file — run the whole script, including that line, every time.
--
-- NOTE ON IDENTIFIERS: your ERD shows several mixed-case column names
-- (e.g. "Current_Stock", "Unit_Price", "Mfr Part#"). Postgres only
-- preserves case/spaces on identifiers created with double quotes, so
-- those exact quoted names are used below. Adjust any name that differs
-- from your actual table definitions before running this file.
-- =====================================================================
 
 
-- ---------------------------------------------------------------------
-- 0. "DATABASE AT A GLANCE" — top-level counts across core tables.
-- Powers the row of totals (manufacturers, distributors, parts, etc.)
-- at the very top of the Overview screen.
--
-- Written defensively (plpgsql + per-table exception handling) rather
-- than a single flat SQL SELECT: if any ONE of these 8 tables doesn't
-- exist or is named differently than expected, a plain SQL function
-- would fail entirely and every field would come back null — exactly
-- the "every card shows —" symptom. This version isolates each count so
-- a bad table only nulls out its own field, and the other 7 still show
-- real numbers — which also makes it obvious which table is the
-- problem instead of an all-or-nothing failure.
-- ---------------------------------------------------------------------
create or replace function get_database_totals()
returns table (
  total_parts integer,
  total_manufacturers integer,
  total_distributors integer,
  total_warehouses integer,
  total_orders integer,
  total_inventory_records integer,
  total_risk_events integer,
  total_alerts integer
)
language plpgsql
stable
as $$
declare
  v_parts integer;
  v_manufacturers integer;
  v_distributors integer;
  v_warehouses integer;
  v_orders integer;
  v_inventory integer;
  v_risk_events integer;
  v_alerts integer;
begin
  begin select count(*) into v_parts from parts; exception when others then v_parts := null; end;
  begin select count(*) into v_manufacturers from manufacturers; exception when others then v_manufacturers := null; end;
  begin select count(*) into v_distributors from distributer; exception when others then v_distributors := null; end;
  begin select count(*) into v_warehouses from warehouses; exception when others then v_warehouses := null; end;
  begin select count(*) into v_orders from orders; exception when others then v_orders := null; end;
  begin select count(*) into v_inventory from inventory; exception when others then v_inventory := null; end;
  begin
    select count(*) into v_risk_events from risk_events where status::text is distinct from 'closed';
  exception when others then v_risk_events := null;
  end;
  begin select count(*) into v_alerts from alert_matches; exception when others then v_alerts := null; end;
 
  return query select v_parts, v_manufacturers, v_distributors, v_warehouses, v_orders, v_inventory, v_risk_events, v_alerts;
end;
$$;
 
 
-- Top at-risk parts watchlist — the "which MPN needs attention" list for
-- the Overview screen. Simplified to the minimum needed for a reliable
-- result: queries `stock_risk` directly (it already has the real
-- computed Risk_Category and Final_Market_Risk_Score per MPN) rather
-- than starting from `parts` and hoping every part has a matching row —
-- that way the table always shows real risk data, sorted by real score,
-- with just one simple lookup join to `manufacturers` for a readable name.
--
-- VERIFY: `parts.mfr_id` is assumed to reference `manufacturers.id` — if
-- the manufacturer column comes back "Unknown" for everything, that's
-- the join to check first.
--
-- p_start/p_end optional — null (default) means all data, no date filter
-- (filters on stock_risk."Last_Modified_Date").
create or replace function get_part_risk_insights(p_limit integer default 15, p_start date default null, p_end date default null)
returns table (
  mpn text,
  manufacturer text,
  stock_risk_level text,
  part_score numeric
)
language sql
stable
as $$
  with latest_per_mpn as (
    select distinct on (sr.mpn)
      sr.mpn,
      sr."Risk_Catagory"           as risk_category,
      sr."Final_Market_Risk_Score" as risk_score
    from stock_risk sr
    where (p_start is null or sr."Last_Modified_Date"::date >= p_start)
      and (p_end is null or sr."Last_Modified_Date"::date <= p_end)
    order by sr.mpn, sr."Last_Modified_Date" desc
  )
  select
    l.mpn,
    coalesce(m."Manufacturer", 'Unknown')   as manufacturer,
    coalesce(l.risk_category, 'Unknown')    as stock_risk_level,
    round(coalesce(l.risk_score, 0)::numeric, 1) as part_score
  from latest_per_mpn l
  left join parts p on p.mpn = l.mpn
  left join manufacturers m on m.id = p.mfr_id
  order by l.risk_score desc nulls last
  limit p_limit;
$$;
 
 
-- ---------------------------------------------------------------------
-- 1. OVERVIEW / LANDING SCREEN
-- ---------------------------------------------------------------------
 
-- Single-row KPI summary for the top of the dashboard.
-- p_start/p_end are optional — leave both null (the default) to include
-- all data with no date filtering at all.
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
       from "distributer_risk" dr
       where (p_start is null or dr."Last_Modified_Date"::date >= p_start)
         and (p_end is null or dr."Last_Modified_Date"::date <= p_end))          as overall_risk_score,

    (select round((
        (avg(dr.final_risk_score) filter (where dr."Last_Modified_Date" > now() - interval '30 days')
         - avg(dr.final_risk_score) filter (where dr."Last_Modified_Date" <= now() - interval '30 days'))
        / nullif(avg(dr.final_risk_score) filter (where dr."Last_Modified_Date" <= now() - interval '30 days'), 0) * 100
      )::numeric, 1)
       from "distributer_risk" dr
       where (p_start is null or dr."Last_Modified_Date"::date >= p_start)
         and (p_end is null or dr."Last_Modified_Date"::date <= p_end))          as risk_score_trend,

    -- Computed as its own uncorrelated subquery (not joined into the main
    -- FROM) so it can never turn into an accidental cross join against
    -- distributer_risk — that was the original bug that caused a full
    -- statement timeout on this screen.
    (select round((100.0 * count(*) filter (where cr."Compliance_Risk_Tier" = 'Low')
        / nullif(count(*), 0))::numeric, 1)
       from parts_compliance pc
       left join compliance_risk cr on pc.id = cr.compliance_id
       where (p_start is null or pc."Last_Modified_Date"::date >= p_start)
         and (p_end is null or pc."Last_Modified_Date"::date <= p_end))          as compliant_parts_pct,

    (select count(*) filter (where cr.hard_stop_flag is true)::int
       from parts_compliance pc
       left join compliance_risk cr on pc.id = cr.compliance_id
       where (p_start is null or pc."Last_Modified_Date"::date >= p_start)
         and (p_end is null or pc."Last_Modified_Date"::date <= p_end))          as non_compliant_count,

    coalesce((select round(avg(100 - kpi.risk_score)::numeric, 1) from inventory_risk kpi), 0) as optimization_score,

    (select count(distinct mpn) from stock
       where (p_start is null or "scraped_at"::date >= p_start)
         and (p_end is null or "scraped_at"::date <= p_end))::int               as tracked_sku_count,

    (select count(distinct mpn) from stock where "scraped_at" > now() - interval '30 days')::int as new_sku_count;
$$;


create or replace function get_risk_trend(p_months integer default 12)
returns table (
  period text,
  risk_score numeric
)
language sql
stable
as $$
  select
    to_char(date_trunc('month', dr."Last_Modified_Date"), 'Mon YY') as period,
    round(avg(dr.final_risk_score)::numeric, 1)                    as risk_score
  from "distributer_risk" dr
  where dr."Last_Modified_Date" > now() - (p_months || ' months')::interval
  group by date_trunc('month', dr."Last_Modified_Date")
  order by date_trunc('month', dr."Last_Modified_Date");
$$;
 
 
-- Top risk categories by share of open risk events.
-- Optional p_start/p_end — null (default) means all data, no date filter.
create or replace function get_top_risk_categories(p_limit integer default 5, p_start date default null, p_end date default null)
returns table (
  category text,
  pct numeric
)
language sql
stable
as $$
  select
    event_category                                                   as category,
    round((100.0 * count(*) / sum(count(*)) over ())::numeric, 1)     as pct
  from risk_events
  where status::text is distinct from 'closed'
    and (p_start is null or retrieval_timestamp::date >= p_start)
    and (p_end is null or retrieval_timestamp::date <= p_end)
  group by event_category
  order by count(*) desc
  limit p_limit;
$$;
 
 
-- Same as get_risk_trend, but for an explicit calendar date range.
-- Both p_start and p_end are optional — leave either/both null to mean
-- "no lower/upper bound", so leaving both null (the DateFilter's default)
-- returns the trend across all data with no date filtering at all.
create or replace function get_risk_trend_range(p_start date default null, p_end date default null)
returns table (
  period text,
  risk_score numeric
)
language sql
stable
as $$
  select
    to_char(date_trunc('week', dr."Last_Modified_Date"), 'Mon DD') as period,
    round(avg(dr.final_risk_score)::numeric, 1)                    as risk_score
  from "distributer_risk" dr
  where (p_start is null or dr."Last_Modified_Date"::date >= p_start)
    and (p_end is null or dr."Last_Modified_Date"::date <= p_end)
  group by date_trunc('week', dr."Last_Modified_Date")
  order by date_trunc('week', dr."Last_Modified_Date");
$$;
 
 
-- ---------------------------------------------------------------------
-- 1b. DATABASE ANALYSIS WIDGETS (Overview screen, lower section)
-- These pull directly from tables that aren't otherwise summarized above:
-- compliance_risk, manufacturers_risk, distributer, orders, order_items,
-- inventory, agent_logs, risk_events.
-- ---------------------------------------------------------------------
 
-- Compliance risk tier breakdown (pie/donut on the Overview screen).
-- p_start/p_end optional — null (default) = all data, no date filter.
create or replace function get_compliance_breakdown(p_start date default null, p_end date default null)
returns table (
  tier text,
  count integer
)
language sql
stable
as $$
  select
    coalesce(cr."Compliance_Risk_Tier", 'Unclassified') as tier,
    count(*)::int                                        as count
  from compliance_risk cr
  where (p_start is null or cr.last_modified::date >= p_start)
    and (p_end is null or cr.last_modified::date <= p_end)
  group by coalesce(cr."Compliance_Risk_Tier", 'Unclassified')
  order by count desc;
$$;
 
 
-- Manufacturer risk levels — how many manufacturers fall in each bucket,
-- and their average risk score. p_start/p_end optional, default = all data.
create or replace function get_manufacturer_risk_distribution(p_start date default null, p_end date default null)
returns table (
  risk_level text,
  count integer,
  avg_score numeric
)
language sql
stable
as $$
  select
    coalesce(mr.risk_level, 'Unclassified')      as risk_level,
    count(*)::int                                as count,
    round(avg(mr.risk_score)::numeric, 1)        as avg_score
  from "manufacturers_risk" mr
  where (p_start is null or mr."Last_Modified_Date"::date >= p_start)
    and (p_end is null or mr."Last_Modified_Date"::date <= p_end)
  group by coalesce(mr.risk_level, 'Unclassified')
  order by count desc;
$$;
 
 
-- Distributor relationship risk levels + average on-time delivery per
-- bucket. p_start/p_end optional, default = all data.
create or replace function get_distributor_risk_distribution(p_start date default null, p_end date default null)
returns table (
  risk_level text,
  count integer,
  avg_on_time_rate numeric
)
language sql
stable
as $$
  select
    coalesce(d.relationship_risk_level, 'Unclassified') as risk_level,
    count(*)::int                                       as count,
    round(avg(d.on_time_delivery_rate)::numeric, 1)      as avg_on_time_rate
  from distributer d
  where (p_start is null or d."Last_Modified_Date"::date >= p_start)
    and (p_end is null or d."Last_Modified_Date"::date <= p_end)
  group by coalesce(d.relationship_risk_level, 'Unclassified')
  order by count desc;
$$;
 
 
-- Order & supplier performance summary, joining orders + order_items.
-- Filters by orders.order_date. p_start/p_end optional, default = all data.
create or replace function get_order_performance_summary(p_start date default null, p_end date default null)
returns table (
  open_orders integer,
  avg_supplier_on_time_rate numeric,
  avg_order_risk_score numeric,
  late_delivery_rate_pct numeric
)
language sql
stable
as $$
  select
    (
      select count(*) from orders
      where status::text not in ('Delivered', 'Cancelled')
        and (p_start is null or order_date::date >= p_start)
        and (p_end is null or order_date::date <= p_end)
    )::int as open_orders,
    round((
      select avg(supplier_on_time_rate) from orders
      where (p_start is null or order_date::date >= p_start)
        and (p_end is null or order_date::date <= p_end)
    )::numeric, 1) as avg_supplier_on_time_rate,
    round((
      select avg(order_risk_score) from orders
      where (p_start is null or order_date::date >= p_start)
        and (p_end is null or order_date::date <= p_end)
    )::numeric, 1) as avg_order_risk_score,
    round((
      100.0 * (
        select count(*) from order_items oi
        join orders o on o.order_id = oi.order_id
        where oi.late_delivery_flag = 1
          and (p_start is null or o.order_date::date >= p_start)
          and (p_end is null or o.order_date::date <= p_end)
      )
      / nullif((
        select count(*) from order_items oi
        join orders o on o.order_id = oi.order_id
        where (p_start is null or o.order_date::date >= p_start)
          and (p_end is null or o.order_date::date <= p_end)
      ), 0)
    )::numeric, 1) as late_delivery_rate_pct;
$$;
 
 
-- Inventory stock-status breakdown (OK / Low / Shortage etc).
-- Filters by inventory.date. p_start/p_end optional, default = all data.
create or replace function get_inventory_health_breakdown(p_start date default null, p_end date default null)
returns table (
  stock_status text,
  count integer
)
language sql
stable
as $$
  select
    coalesce(i.stock_status, 'Out of Stock') as stock_status,
    count(*)::int                            as count
  from inventory i
  where (p_start is null or i.date::date >= p_start)
    and (p_end is null or i.date::date <= p_end)
  group by coalesce(i.stock_status, 'Out of Stock')
  order by count desc;
$$;
 
 
-- Latest data-pipeline / scraper agent runs, from agent_logs.
-- p_start/p_end optional, default = all data (still capped by p_limit).
create or replace function get_pipeline_health(p_limit integer default 8, p_start date default null, p_end date default null)
returns table (
  source_name text,
  run_timestamp timestamptz,
  status text,
  records_fetched integer,
  records_updated integer,
  records_skipped integer,
  error_message text
)
language sql
stable
as $$
  select
    al.source_name,
    al.run_timestamp,
    al.status,
    al.records_fetched,
    al.records_updated,
    al.records_skipped,
    al.error_message
  from agent_logs al
  where (p_start is null or al.run_timestamp::date >= p_start)
    and (p_end is null or al.run_timestamp::date <= p_end)
  order by al.run_timestamp desc
  limit p_limit;
$$;
 
 
-- Open risk events grouped by severity signal (donut chart).
-- p_start/p_end optional, default = all data.
create or replace function get_events_by_severity(p_start date default null, p_end date default null)
returns table (
  severity_signal text,
  count integer
)
language sql
stable
as $$
  select
    coalesce(re.severity_signal #>> '{}', 'Unclassified') as severity_signal,
    count(*)::int                                as count
  from risk_events re
  where re.status::text is distinct from 'closed'
    and (p_start is null or re.retrieval_timestamp::date >= p_start)
    and (p_end is null or re.retrieval_timestamp::date <= p_end)
  group by coalesce(re.severity_signal #>> '{}', 'Unclassified')
  order by count desc;
$$;
-- ---------------------------------------------------------------------
-- Parts & Stock table — MPN / Manufacturer / Category / Inventory Risk /
--      Stock Risk / Part Score / Lifecycle status, with search + date +
--      lifecycle filtering.
-- ---------------------------------------------------------------------
-- Drop EVERY existing overload of this function, whatever its exact old
-- signature was — guessing specific old parameter lists (as the two
-- commented-out lines below did) misses anything with a different
-- parameter ORDER, even with identical types, which Postgres treats as a
-- distinct overload. Leaving even one stray overload around is exactly
-- what causes PostgREST to report "could not find the function" even
-- though a correct version clearly exists — it can't disambiguate.
-- drop function if exists get_parts_with_stock(text, text, integer, integer);
-- drop function if exists get_parts_with_stock(text, date, date, integer, integer);
do $$
declare
  r record;
begin
  for r in
    select oid::regprocedure as sig
    from pg_proc
    where proname = 'get_parts_with_stock'
      and pronamespace = 'public'::regnamespace
  loop
    execute format('drop function %s;', r.sig);
  end loop;
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


create or replace function get_part_alternatives(p_mpn text)
returns table (
  alternative_part text,
  manufacturer text,
  relationship text,
  description text
)
language sql
stable
as $$
  select
    pa."Alternative Part" as alternative_part,
    pa.manufacturer,
    pa.relationship,
    pa.description
  from "Parts_Alternative" pa
  where pa."Mfr Part #" = p_mpn;
$$;
-- ---------------------------------------------------------------------
-- Part Details page — single-MPN summary combining manufacturer,
--      inventory, compliance, alternative, and stock risk.
-- ---------------------------------------------------------------------
-- Drop every existing overload of get_part_details, whatever its old
-- signature was, rather than guessing one specific old parameter list.
-- drop function if exists get_part_details(text, date, date);
do $$
declare
  r record;
begin
  for r in
    select oid::regprocedure as sig
    from pg_proc
    where proname = 'get_part_details'
      and pronamespace = 'public'::regnamespace
  loop
    execute format('drop function %s;', r.sig);
  end loop;
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


-- Return type changed (added extended_price) — CREATE OR REPLACE cannot
-- change a function's return columns, so drop every existing overload
-- first, the same way get_parts_with_stock/get_part_details do above.
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


-- Return type changed (added total_extended_value) — same reasoning as
-- get_part_stock_suppliers above.
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
    i.reorder_point,
    w.warehouse_name,
    i.stock_status
  from inventory i
  left join warehouses w on w.warehouse_id = i.warehouse_id
  left join lateral (
    select ik.risk_level
    from inventory_risk ik
    where ik.inventory_id = i.inventory_id
    order by ik."Last_Modified_Date" desc limit 1
  ) k on true
  where (p_warehouse_id is null or i.warehouse_id = p_warehouse_id)
    and (p_start is null or i.date::date >= p_start)
    and (p_end is null or i.date::date <= p_end)
  order by i.date desc nulls last, i."Last_Modified_Date" desc nulls last
  limit p_limit offset p_offset;
$$;


-- Drop every existing overload of get_inventory_kpis, whatever its old
-- signature was, rather than guessing one specific old parameter list.
-- drop function if exists get_inventory_kpis();
do $$
declare
  r record;
begin
  for r in
    select oid::regprocedure as sig
    from pg_proc
    where proname = 'get_inventory_kpis'
      and pronamespace = 'public'::regnamespace
  loop
    execute format('drop function %s;', r.sig);
  end loop;
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


-- NOTE: there is no separate time-series "inventory_forecast" table —
-- forecast_demand/safety_stock/reorder_point/min_stock/max_stock are all
-- columns directly on `inventory` itself (one current snapshot per
-- inventory_id, not a history of dated forecast points). This function
-- is currently unused by the frontend (not called anywhere in
-- supabaseClient.js), kept only in case something wires it back in —
-- adapted to return that single snapshot as one row instead of an
-- imaginary date-series.
create or replace function get_inventory_forecast(p_inventory_id text)
returns table (
  forecast_date date,
  forecast_demand numeric,
  safety_stock numeric,
  reorder_point numeric,
  min_stock numeric,
  max_stock numeric
)
language sql
stable
as $$
  select i.date::date as forecast_date, i.forecast_demand, i.safety_stock,
         i.reorder_point, i.min_stock, i.max_stock
  from inventory i
  where i.inventory_id = p_inventory_id
  order by i.date desc
  limit 1;
$$;


-- ---------------------------------------------------------------------
-- 4. COMPLIANCE / MANUFACTURER & DISTRIBUTOR RISK
-- ---------------------------------------------------------------------

create or replace function get_compliance_summary()
returns table (
  total_parts integer,
  compliant integer,
  non_compliant integer,
  unknown integer
)
language sql
stable
as $$
  select
    count(*)::int                                                     as total_parts,
    count(*) filter (where "Compliance_Risk_Tier" = 'Low')::int       as compliant,
    count(*) filter (where hard_stop_flag is true)::int                as non_compliant,
    count(*) filter (where "Compliance_Risk_Tier" is null)::int       as unknown
  from compliance_risk;
$$;
 
 
create or replace function get_manufacturer_risk(p_limit integer default 50)
returns table (
  manufacturer text,
  risk_score numeric,
  risk_level text,
  confidence_score numeric,
  is_acquired boolean
)
language sql
stable
as $$
  select
    m."Manufacturer",
    mr.risk_score,
    mr.risk_level,
    mr.confidence_score,
    mr.is_acquired
  from "manufacturers_risk" mr
  join manufacturers m on m.id = mr."M_ID"
  order by mr.risk_score desc nulls last
  limit p_limit;
$$;
 
 
create or replace function get_distributor_risk(p_limit integer default 50)
returns table (
  distributor_name text,
  relationship_tier text,
  relationship_risk_score numeric,
  relationship_risk_level text,
  on_time_delivery_rate numeric
)
language sql
stable
as $$
  select
    d."D_Name"                as distributor_name,
    d.relationship_tier,
    d.relationship_risk_score,
    d.relationship_risk_level,
    d.on_time_delivery_rate
  from distributer d
  order by d.relationship_risk_score desc nulls last
  limit p_limit;
$$;
-- ---------------------------------------------------------------------
-- 5. NEWS & RISK EVENTS SCREEN
-- ---------------------------------------------------------------------
-- Drop every existing overload of get_recent_events, whatever its old
-- signature was, rather than guessing one specific old parameter list.
-- drop function if exists get_recent_events(integer, integer);
do $$
declare
  r record;
begin
  for r in
    select oid::regprocedure as sig
    from pg_proc
    where proname = 'get_recent_events'
      and pronamespace = 'public'::regnamespace
  loop
    execute format('drop function %s;', r.sig);
  end loop;
end $$;

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
  -- distinct on (title) drops duplicate re-scrapes of the same story,
  -- keeping only the most recently retrieved copy.
  select distinct on (re.title)
    re.event_id::text,
    re.title,
    re.summary,
    coalesce(re.severity_signal #>> '{}', 'Unclassified') as severity_signal,
    re.retrieval_timestamp                                 as retrieved_at
  from risk_events re
  where re.status::text is distinct from 'closed'
    and coalesce(re.severity_score, 0) >= p_severity_min
    and (p_start is null or re.retrieval_timestamp::date >= p_start)
    and (p_end is null or re.retrieval_timestamp::date <= p_end)
  order by re.title, re.retrieval_timestamp desc
  limit p_limit;
$$;


-- Drop every existing overload of get_recent_alerts, whatever its old
-- signature was, rather than guessing one specific old parameter list.
-- drop function if exists get_recent_alerts(integer);
do $$
declare
  r record;
begin
  for r in
    select oid::regprocedure as sig
    from pg_proc
    where proname = 'get_recent_alerts'
      and pronamespace = 'public'::regnamespace
  loop
    execute format('drop function %s;', r.sig);
  end loop;
end $$;

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
-- 6. REPORTS SCREEN
-- ---------------------------------------------------------------------

create or replace function get_reports(p_limit integer default 50)
returns table (
  id text,
  datetime timestamptz,
  report text
)
language sql
stable
as $$
  select r.id, r.datetime, r.report
  from reports r
  order by r.datetime desc
  limit p_limit;
$$;
-- =====================================================================
-- Grants — allow the anon/authenticated roles used by supabase-js to
-- execute these RPCs. Row Level Security on the underlying tables still
-- applies, so add policies on each table as needed (see the RLS block
-- below — it already covers everything these functions touch).
-- =====================================================================
grant execute on function
  get_database_totals(),
  get_part_risk_insights(integer, date, date),
  get_dashboard_summary(date, date),
  get_risk_trend(integer),
  get_risk_trend_range(date, date),
  get_top_risk_categories(integer, date, date),
  get_compliance_breakdown(date, date),
  get_manufacturer_risk_distribution(date, date),
  get_distributor_risk_distribution(date, date),
  get_order_performance_summary(date, date),
  get_inventory_health_breakdown(date, date),
  get_pipeline_health(integer, date, date),
  get_events_by_severity(date, date),
  get_parts_with_stock(text, text, date, date, integer, integer),
  get_lifecycle_statuses(),
  get_part_alternatives(text),
  get_part_details(text, date, date),
  get_part_stock_suppliers(text, date, date),
  get_part_stock_summary(text, date, date),
  get_inventory_records(text, date, date, integer, integer),
  get_inventory_kpis(date, date),
  get_inventory_forecast(text),
  get_compliance_summary(),
  get_manufacturer_risk(integer),
  get_distributor_risk(integer),
  get_recent_events(integer, integer, date, date),
  get_recent_alerts(integer, date, date),
  get_reports(integer)
to anon, authenticated;


-- =====================================================================
-- REALTIME SETUP — required for the notification bell
-- =====================================================================
-- The bell (src/lib/useNotifications.js) subscribes to Postgres Realtime
-- change events on `reports` and `inventory` — it does NOT poll. For that
-- subscription to actually receive anything, both tables need Realtime
-- turned on and a SELECT policy the anon/authenticated role can use.

alter publication supabase_realtime add table reports;
alter publication supabase_realtime add table inventory;

-- =====================================================================
-- RLS — read policies for every table any function above queries
-- =====================================================================
-- Written as DROP POLICY IF EXISTS + CREATE POLICY for every table, so
-- this whole block can be re-run any number of times without ever
-- failing on "policy already exists" — that failure is exactly what can
-- silently abort an entire multi-statement script in the SQL editor
-- (Postgres runs a pasted multi-statement script as one implicit
-- transaction: one failing statement rolls back everything else in the
-- same run, including function updates earlier in the file that looked
-- like they succeeded).
--
-- `using (true)` = readable by anyone with the anon/publishable key.
-- That's appropriate here since every one of these tables is only ever
-- exposed through read-only aggregate functions anyway, never raw rows
-- directly to end users. Tighten later if you add real user accounts.

do $$
declare
  t text;
  tables text[] := array[
    'reports', 'inventory', 'compliance_risk', 'manufacturers_risk',
    'risk_events', 'manufacturers', 'distributer_risk', 'alert_matches',
    'parts', 'distributer', 'warehouses', 'orders', 'order_items',
    'stock', 'inventory_risk', 'agent_logs',
    'stock_risk', 'part_score', 'parts_compliance', 'mounting_type',
    'parts_category', 'Parts_Alternative', 'alternatives_risk'
  ];
begin
  foreach t in array tables loop
    -- Wrapped per-table: if any one name in this list has since been
    -- renamed or dropped (as happened with inventory_kpi -> inventory_risk),
    -- that single table logs an error and the loop continues — instead of
    -- one bad name aborting RLS setup for every other table in the list.
    begin
      execute format('alter table public.%I enable row level security;', t);
      execute format('drop policy if exists "Allow read access" on public.%I;', t);
      execute format(
        'create policy "Allow read access" on public.%I for select to anon, authenticated using (true);',
        t
      );
    exception when others then
      raise notice 'RLS setup skipped for %: % (table may not exist under this name)', t, sqlerrm;
    end;
  end loop;
end $$;

-- Force PostgREST to pick up every change above immediately, rather
-- than serving cached function signatures for up to ~60 seconds.
NOTIFY pgrst, 'reload schema';