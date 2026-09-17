-- =====================================================================
-- SiaCore — News & Risk Events rebuild against the real event schema
-- =====================================================================
-- Your ERD screenshot shows the actual tables: risk_events,
-- event_analyses, event_predictions, alert_matches, event_status_history,
-- event_articles. Earlier files guessed at a simpler shape for
-- get_recent_events/get_recent_alerts that happened to have the right
-- column names for risk_events but never covered per-event detail,
-- stats, or a search/date-aware dedupe — this rewrites all of that.
--
-- On the garbled card in your screenshot: that raw
-- `{"raw_signal": {"hybrid_factors": [...` blob is a jsonb audit/scoring
-- column (looks like `provenance` or `severity_signal`) being rendered
-- directly as text somewhere upstream of these functions — none of the
-- queries below select or return that column, so once you're calling
-- get_recent_events for the card text, that specific bug goes away. If
-- it's still showing after wiring this in, it means something else in
-- the pipeline is writing that JSON into the `title`/`summary` columns
-- themselves, which would need to be fixed at ingestion, not display.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

-- ---------------------------------------------------------------------
-- get_recent_events — deduped, searchable, date-filterable event feed
-- ---------------------------------------------------------------------
create or replace function get_recent_events(
  p_severity_min integer default 0,
  p_limit integer default 50,
  p_start date default null,
  p_end date default null,
  p_search text default null
)
returns table (
  event_id uuid,
  title text,
  summary text,
  severity_score numeric,
  severity_level text,
  event_category text,
  geo_region text,
  geo_country text,
  source_count integer,
  retrieved_at timestamptz
)
language sql
stable
as $$
  select distinct on (coalesce(re.cluster_id::text, lower(trim(re.title))))
    re.event_id,
    re.title,
    re.summary,
    re.severity_score,
    case
      when re.severity_score >= 75 then 'Critical'
      when re.severity_score >= 50 then 'High'
      when re.severity_score >= 25 then 'Medium'
      else 'Low'
    end                                       as severity_level,
    re.event_category,
    coalesce(re.geo_region, re.geo_country, 'Global') as geo_region,
    re.geo_country,
    re.source_count,
    re.retrieval_timestamp                    as retrieved_at
  from risk_events re
  where re.status is distinct from 'closed'
    and coalesce(re.severity_score, 0) >= p_severity_min
    and (p_start is null or re.retrieval_timestamp::date >= p_start)
    and (p_end is null or re.retrieval_timestamp::date <= p_end)
    and (p_search is null or re.title ilike '%' || p_search || '%' or re.summary ilike '%' || p_search || '%')
  -- distinct on requires the cluster/title key first in ORDER BY, then
  -- the freshest copy of that cluster.
  order by coalesce(re.cluster_id::text, lower(trim(re.title))), re.retrieval_timestamp desc
  limit p_limit;
$$;


-- ---------------------------------------------------------------------
-- get_news_stats — the 4 header KPIs (Events / Avg Severity /
-- Peak Severity / AI Analysis), deduped the same way as the feed above
-- so the count matches what's actually shown on screen.
-- ---------------------------------------------------------------------
create or replace function get_news_stats(p_start date default null, p_end date default null)
returns table (
  event_count integer,
  avg_severity numeric,
  peak_severity numeric,
  ai_analysis_count integer
)
language sql
stable
as $$
  with deduped as (
    select distinct on (coalesce(re.cluster_id::text, lower(trim(re.title))))
      re.event_id, re.severity_score
    from risk_events re
    where re.status is distinct from 'closed'
      and (p_start is null or re.retrieval_timestamp::date >= p_start)
      and (p_end is null or re.retrieval_timestamp::date <= p_end)
    order by coalesce(re.cluster_id::text, lower(trim(re.title))), re.retrieval_timestamp desc
  )
  select
    count(*)::int                                    as event_count,
    round(avg(d.severity_score)::numeric, 1)          as avg_severity,
    round(max(d.severity_score)::numeric, 1)          as peak_severity,
    (select count(distinct ea.event_id) from event_analyses ea
       join deduped d2 on d2.event_id = ea.event_id)::int as ai_analysis_count
  from deduped d;
$$;


-- ---------------------------------------------------------------------
-- get_event_details — powers the click-through modal: full event plus
-- its latest AI analysis (executive summary / business impact) and the
-- source articles it was built from.
-- NOTE: `executive_summary` / `business_impact` are my best guess at
-- the keys inside event_analyses.analysis (jsonb) based on your
-- screenshot's modal headings — check these against a real row
-- (`select analysis from event_analyses limit 1`) and rename if needed.
-- ---------------------------------------------------------------------
create or replace function get_event_details(p_event_id uuid)
returns table (
  event_id uuid,
  title text,
  summary text,
  severity_score numeric,
  severity_level text,
  event_category text,
  geo_region text,
  geo_country text,
  status text,
  retrieved_at timestamptz,
  executive_summary text,
  business_impact text,
  analysis_model text,
  analysis_confidence numeric
)
language sql
stable
as $$
  with latest_analysis as (
    select ea.analysis, ea.model_used, ea.analysis_confidence
    from event_analyses ea
    where ea.event_id = p_event_id
    order by ea.generated_at desc nulls last, ea.created_at desc
    limit 1
  )
  select
    re.event_id,
    re.title,
    re.summary,
    re.severity_score,
    case
      when re.severity_score >= 75 then 'Critical'
      when re.severity_score >= 50 then 'High'
      when re.severity_score >= 25 then 'Medium'
      else 'Low'
    end                                             as severity_level,
    re.event_category,
    coalesce(re.geo_region, re.geo_country, 'Global') as geo_region,
    re.geo_country,
    re.status,
    re.retrieval_timestamp                          as retrieved_at,
    la.analysis ->> 'executive_summary'              as executive_summary,
    la.analysis ->> 'business_impact'                as business_impact,
    la.model_used                                    as analysis_model,
    la.analysis_confidence
  from risk_events re
  left join latest_analysis la on true
  where re.event_id = p_event_id
  limit 1;
$$;

create or replace function get_event_articles(p_event_id uuid)
returns table (
  title text,
  provider text,
  url text,
  reliability_tier text,
  retrieved_at timestamptz
)
language sql
stable
as $$
  select ea.title, ea.provider, ea.url, ea.reliability_tier, ea.retrieved_at
  from event_articles ea
  where ea.event_id = p_event_id
  order by ea.retrieved_at desc;
$$;


-- ---------------------------------------------------------------------
-- FIX: get_recent_alerts — the sidebar was showing the same rule fired
-- over and over a few seconds apart (same batch-duplicate pattern as
-- the stock scrapes). Now keeps one row per rule per day.
-- ---------------------------------------------------------------------
create or replace function get_recent_alerts(p_limit integer default 50, p_start date default null, p_end date default null)
returns table (
  id uuid,
  rule_name text,
  matched_at timestamptz
)
language sql
stable
as $$
  select distinct on (am.rule_name, am.matched_at::date)
    am.id,
    am.rule_name,
    am.matched_at
  from alert_matches am
  where (p_start is null or am.matched_at::date >= p_start)
    and (p_end is null or am.matched_at::date <= p_end)
  order by am.rule_name, am.matched_at::date, am.matched_at desc
  limit p_limit;
$$;

grant execute on function get_recent_events(integer, integer, date, date, text) to anon, authenticated;
grant execute on function get_news_stats(date, date) to anon, authenticated;
grant execute on function get_event_details(uuid) to anon, authenticated;
grant execute on function get_event_articles(uuid) to anon, authenticated;
grant execute on function get_recent_alerts(integer, date, date) to anon, authenticated;
