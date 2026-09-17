-- =====================================================================
-- SiaCore — Dashboard data diagnostics (resilient, single-run version)
-- =====================================================================
create temporary table if not exists diagnostic_results (
  seq serial,
  check_name text,
  result jsonb,
  error text
);
truncate diagnostic_results;

do $$
declare
  v jsonb;
begin

  -- -------------------- row counts --------------------
  begin select jsonb_build_object('count', count(*)) into v from manufacturers;
    insert into diagnostic_results(check_name, result) values ('row_count: manufacturers', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: manufacturers', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from "manufacturers_risk";
    insert into diagnostic_results(check_name, result) values ('row_count: manufacturers_risk', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: manufacturers_risk', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from distributer;
    insert into diagnostic_results(check_name, result) values ('row_count: distributer', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: distributer', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from parts_compliance;
    insert into diagnostic_results(check_name, result) values ('row_count: parts_compliance', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: parts_compliance', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from compliance_risk;
    insert into diagnostic_results(check_name, result) values ('row_count: compliance_risk', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: compliance_risk', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from "distributer_risk";
    insert into diagnostic_results(check_name, result) values ('row_count: distributer_risk', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: distributer_risk', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from risk_events;
    insert into diagnostic_results(check_name, result) values ('row_count: risk_events (all)', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: risk_events (all)', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from risk_events where status::text is distinct from 'closed';
    insert into diagnostic_results(check_name, result) values ('row_count: risk_events (open)', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: risk_events (open)', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from alert_matches;
    insert into diagnostic_results(check_name, result) values ('row_count: alert_matches', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: alert_matches', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from parts;
    insert into diagnostic_results(check_name, result) values ('row_count: parts', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: parts', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from stock;
    insert into diagnostic_results(check_name, result) values ('row_count: stock', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: stock', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from inventory;
    insert into diagnostic_results(check_name, result) values ('row_count: inventory', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: inventory', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from inventory_forecast;
    insert into diagnostic_results(check_name, result) values ('row_count: inventory_forecast', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: inventory_forecast', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from inventory_kpi;
    insert into diagnostic_results(check_name, result) values ('row_count: inventory_kpi', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: inventory_kpi', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from orders;
    insert into diagnostic_results(check_name, result) values ('row_count: orders', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: orders', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from order_items;
    insert into diagnostic_results(check_name, result) values ('row_count: order_items', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: order_items', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from agent_logs;
    insert into diagnostic_results(check_name, result) values ('row_count: agent_logs', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: agent_logs', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from stock_risk;
    insert into diagnostic_results(check_name, result) values ('row_count: stock_risk', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: stock_risk', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from part_score;
    insert into diagnostic_results(check_name, result) values ('row_count: part_score', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: part_score', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from mounting_type;
    insert into diagnostic_results(check_name, result) values ('row_count: mounting_type', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: mounting_type', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from parts_category;
    insert into diagnostic_results(check_name, result) values ('row_count: parts_category', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: parts_category', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from "Parts_Alternative";
    insert into diagnostic_results(check_name, result) values ('row_count: Parts_Alternative', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: Parts_Alternative', sqlerrm); end;

  begin select jsonb_build_object('count', count(*)) into v from alternatives_risk;
    insert into diagnostic_results(check_name, result) values ('row_count: alternatives_risk', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('row_count: alternatives_risk', sqlerrm); end;

  -- -------------------- RLS status --------------------
  begin
    select jsonb_agg(to_jsonb(t)) into v from (
      select tablename, rowsecurity
      from pg_tables
      where schemaname = 'public'
        and tablename in (
          'manufacturers', 'manufacturers_risk', 'parts_compliance', 'compliance_risk',
          'distributer_risk', 'risk_events', 'alert_matches', 'distributer',
          'inventory_kpi', 'inventory_forecast', 'warehouses'
        )
    ) t;
    insert into diagnostic_results(check_name, result) values ('rls: table flags', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rls: table flags', sqlerrm); end;

  begin
    select jsonb_agg(to_jsonb(t)) into v from (
      select tablename, policyname, roles, cmd
      from pg_policies
      where schemaname = 'public'
      order by tablename
    ) t;
    insert into diagnostic_results(check_name, result) values ('rls: policies', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rls: policies', sqlerrm); end;

  -- -------------------- RPC calls --------------------
  begin select to_jsonb(t) into v from get_database_totals() t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_database_totals', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_database_totals', sqlerrm); end;

  begin select to_jsonb(t) into v from get_dashboard_summary(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_dashboard_summary', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_dashboard_summary', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_compliance_breakdown(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_compliance_breakdown', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_compliance_breakdown', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_manufacturer_risk_distribution(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_manufacturer_risk_distribution', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_manufacturer_risk_distribution', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_distributor_risk_distribution(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_distributor_risk_distribution', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_distributor_risk_distribution', sqlerrm); end;

  begin select to_jsonb(t) into v from get_order_performance_summary(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_order_performance_summary', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_order_performance_summary', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_inventory_health_breakdown(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_inventory_health_breakdown', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_inventory_health_breakdown', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_events_by_severity(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_events_by_severity', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_events_by_severity', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_top_risk_categories(5, null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_top_risk_categories', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_top_risk_categories', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_risk_trend_range(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_risk_trend_range', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_risk_trend_range', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_part_risk_insights(12, null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_part_risk_insights', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_part_risk_insights', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_parts_with_stock(null, null, null, null, 5, 0) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_parts_with_stock', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_parts_with_stock', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_lifecycle_statuses() t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_lifecycle_statuses', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_lifecycle_statuses', sqlerrm); end;

  -- part-details checks need one real mpn to test against; grabs
  -- whichever mpn sorts first rather than hardcoding one that may not
  -- exist in your data.
  begin
    select jsonb_agg(to_jsonb(t)) into v
    from get_part_details((select mpn from parts order by mpn limit 1), null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_part_details', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_part_details', sqlerrm); end;

  begin
    select jsonb_agg(to_jsonb(t)) into v
    from get_part_stock_suppliers((select mpn from parts order by mpn limit 1), null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_part_stock_suppliers', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_part_stock_suppliers', sqlerrm); end;

  begin
    select to_jsonb(t) into v
    from get_part_stock_summary((select mpn from parts order by mpn limit 1), null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_part_stock_summary', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_part_stock_summary', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_inventory_records(null, null, null, 5, 0) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_inventory_records', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_inventory_records', sqlerrm); end;

  begin select to_jsonb(t) into v from get_inventory_kpis(null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_inventory_kpis', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_inventory_kpis', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_recent_events(0, 5, null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_recent_events', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_recent_events', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_recent_alerts(5, null, null) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_recent_alerts', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_recent_alerts', sqlerrm); end;

  begin select jsonb_agg(to_jsonb(t)) into v from get_reports(5) t;
    insert into diagnostic_results(check_name, result) values ('rpc: get_reports', v);
  exception when others then insert into diagnostic_results(check_name, error) values ('rpc: get_reports', sqlerrm); end;

end $$;

select seq, check_name, result, error from diagnostic_results order by seq;