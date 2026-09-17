-- =====================================================================
-- SiaCore — Inventory table name corrections
-- =====================================================================
-- Per your ERD screenshot, two assumptions in earlier files were wrong:
--
-- 1. There is no `inventory_forecast` table. `reorder_point` (and
--    safety_stock/max_stock/min_stock) live directly on `inventory`
--    itself — stored as `text`, so cast to numeric when used.
-- 2. There is no `inventory_kpi` table. The real table is
--    `inventory_risk`, and it's keyed by `inventory_id` (FK into
--    `inventory`), not by `mpn` directly — every join needs to go
--    through `inventory` first.
--
-- This replaces get_dashboard_summary's optimization_score subquery,
-- get_inventory_records, and get_inventory_kpis accordingly.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

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
    coalesce(ir.risk_level, 'Unknown')          as risk_level,
    i.qty_on_hand,
    i.available_stock,
    -- FIXED: reorder_point lives on `inventory` itself (stored as text)
    -- — there is no separate inventory_forecast table.
    nullif(i.reorder_point, '')::numeric        as reorder_point,
    w.warehouse_name,
    i.stock_status
  from inventory i
  left join warehouses w on w.warehouse_id = i.warehouse_id
  -- FIXED: inventory_risk joins to inventory via inventory_id, not mpn —
  -- and the table is `inventory_risk`, not `inventory_kpi`.
  left join lateral (
    select k.risk_level from inventory_risk k
    where k.inventory_id = i.inventory_id
    order by k."Last_Modified_Date" desc limit 1
  ) ir on true
  where (p_warehouse_id is null or i.warehouse_id = p_warehouse_id)
    and (p_start is null or i.date::date >= p_start)
    and (p_end is null or i.date::date <= p_end)
  order by i.date desc nulls last, i."Last_Modified_Date" desc nulls last
  limit p_limit offset p_offset;
$$;

create or replace function get_inventory_kpis(p_start date default null, p_end date default null)
returns table (
  total_qty_on_hand numeric,
  avg_stock_sufficiency_ratio numeric,
  avg_lead_time_days numeric,
  shortage_risk_sku_count integer
)
language sql
stable
as $$
  select
    (select sum(i.qty_on_hand) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end)),

    round((
      select avg(k.stock_sufficiency_ratio)
      from inventory_risk k
      join inventory i on i.inventory_id = k.inventory_id
      where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end)
    )::numeric, 1),

    round((select avg(i.lead_time_days) from inventory i
       where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end))::numeric, 1),

    (
      select count(distinct i.mpn)
      from inventory_risk k
      join inventory i on i.inventory_id = k.inventory_id
      where k.risk_level in ('High', 'Critical')
        and (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end)
    )::int;
$$;

-- FIX: get_dashboard_summary's optimization_score referenced inventory_kpi
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
       from compliance_risk cr
       where (p_start is null or cr.last_modified::date >= p_start)
         and (p_end is null or cr.last_modified::date <= p_end))                as compliant_parts_pct,

    (select count(*) filter (where cr.hard_stop_flag is true)::int
       from compliance_risk cr
       where (p_start is null or cr.last_modified::date >= p_start)
         and (p_end is null or cr.last_modified::date <= p_end))                as non_compliant_count,

    -- FIXED: inventory_kpi -> inventory_risk, joined via inventory_id
    coalesce((
      select round(avg(100 - k.risk_score)::numeric, 1)
      from inventory_risk k
      join inventory i on i.inventory_id = k.inventory_id
      where (p_start is null or i.date::date >= p_start) and (p_end is null or i.date::date <= p_end)
    ), 0)                                                                       as optimization_score,

    (select count(distinct mpn) from stock
       where (p_start is null or "scraped_at"::date >= p_start)
         and (p_end is null or "scraped_at"::date <= p_end))::int               as tracked_sku_count,

    (select count(distinct mpn) from stock where "scraped_at" > now() - interval '30 days')::int as new_sku_count;
$$;

grant execute on function get_inventory_records(text, date, date, integer, integer) to anon, authenticated;
grant execute on function get_inventory_kpis(date, date) to anon, authenticated;
grant execute on function get_dashboard_summary(date, date) to anon, authenticated;
