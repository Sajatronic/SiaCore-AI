-- =====================================================================
-- SiaCore — Patch: overall risk category on Part Details + distributor
-- detail lookup
-- =====================================================================
-- Run after your current 01_stored_procedures.sql. Then:
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. get_part_details — add overall_risk_level, sourced from the real
--    part_score.part_category column (already in your schema, unused
--    until now) instead of leaving the "Overall Part Score" card
--    without a badge like the other five risk cards have.
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
  overall_part_score numeric,
  overall_part_category text
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
    coalesce(lps.part_score, lsr.risk_score, 0)                           as overall_part_score,
    coalesce(lps.part_category, 'Unknown')                                as overall_part_category
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
-- 2. get_distributor_details — full distributer row for one distributor,
--    for the click-to-expand panel. Looked up by D_code, which is what
--    get_part_stock_suppliers already exposes as distributor_code, so
--    the frontend can pass straight through without an extra lookup.
-- ---------------------------------------------------------------------
create or replace function get_distributor_details(p_distributor_code text)
returns table (
  d_id text,
  d_name text,
  d_type text,
  d_country text,
  d_headquarters text,
  d_authorized text,
  d_website text,
  d_status text,
  d_code text,
  dealt_with text,
  relationship_tier text,
  vetting_status text,
  years_relationship numeric,
  total_orders_placed numeric,
  on_time_delivery_rate numeric,
  quality_issues_12m numeric,
  relationship_risk_score numeric,
  relationship_risk_level text,
  company_founded_year text,
  public_profile_strength text,
  research_notes text,
  data_source text,
  verification_status text,
  last_modified_date timestamptz
)
language sql
stable
as $$
  select
    d."D_id"::text,
    d."D_Name",
    d."D_Type",
    d."D_country",
    d."D_headquarters",
    d."D_authorized",
    d."D_website",
    d."D_status",
    d."D_code",
    d.dealt_with,
    d.relationship_tier,
    d.vetting_status,
    d.years_relationship,
    d.total_orders_placed,
    d.on_time_delivery_rate,
    d.quality_issues_12m,
    d.relationship_risk_score,
    d.relationship_risk_level,
    d.company_founded_year,
    d.public_profile_strength,
    d.research_notes,
    d.data_source,
    d.verification_status,
    d."Last_Modified_Date"
  from distributer d
  where d."D_code" = p_distributor_code
  limit 1;
$$;

grant execute on function get_distributor_details(text) to anon, authenticated;

NOTIFY pgrst, 'reload schema';
