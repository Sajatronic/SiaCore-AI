-- =====================================================================
-- FIX: severity_level sourced from the database, not invented thresholds
-- =====================================================================
-- Previously severity_level was computed purely from severity_score
-- with hardcoded cutoffs (>=75 Critical, >=50 High, etc.) — that's a
-- guess I made, not something backed by real classification data.
--
-- risk_events.severity_signal is jsonb and, based on the very first
-- garbled screenshot in this project (a raw dump of
-- {"raw_signal": {"hybrid_factors": [...]}}), it looks like it already
-- holds a scoring breakdown from the pipeline — which may include an
-- actual severity classification, not just component scores.
--
-- This tries several plausible key names for that classification
-- (level / severity_level / category / label / tier / severity) via
-- COALESCE, and only falls back to the score-based bands if NONE of
-- them are present. That means:
--   - If your real key is one of these, this is already correct.
--   - If it's something else, or lives in a different table entirely,
--     tell me the real key/table and this becomes a one-line change —
--     delete the guessed COALESCE branches, keep just the real one.
--
-- Run `select severity_signal from risk_events limit 5;` to see which
-- (if any) of these guesses is right, and paste the result back.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

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
    -- FIXED: was a pure score-threshold guess. Now tries real
    -- classification keys inside severity_signal first.
    coalesce(
      nullif(re.severity_signal ->> 'level', ''),
      nullif(re.severity_signal ->> 'severity_level', ''),
      nullif(re.severity_signal ->> 'category', ''),
      nullif(re.severity_signal ->> 'label', ''),
      nullif(re.severity_signal ->> 'tier', ''),
      nullif(re.severity_signal ->> 'severity', ''),
      case
        when re.severity_score >= 75 then 'Critical'
        when re.severity_score >= 50 then 'High'
        when re.severity_score >= 25 then 'Medium'
        when re.severity_score > 0   then 'Low'
        else 'Unknown'
      end
    )                                         as severity_level,
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
  order by coalesce(re.cluster_id::text, lower(trim(re.title))), re.retrieval_timestamp desc
  limit p_limit;
$$;

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
    coalesce(
      nullif(re.severity_signal ->> 'level', ''),
      nullif(re.severity_signal ->> 'severity_level', ''),
      nullif(re.severity_signal ->> 'category', ''),
      nullif(re.severity_signal ->> 'label', ''),
      nullif(re.severity_signal ->> 'tier', ''),
      nullif(re.severity_signal ->> 'severity', ''),
      case
        when re.severity_score >= 75 then 'Critical'
        when re.severity_score >= 50 then 'High'
        when re.severity_score >= 25 then 'Medium'
        when re.severity_score > 0   then 'Low'
        else 'Unknown'
      end
    )                                               as severity_level,
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

grant execute on function get_recent_events(integer, integer, date, date, text) to anon, authenticated;
grant execute on function get_event_details(uuid) to anon, authenticated;
