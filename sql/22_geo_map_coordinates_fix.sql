-- =====================================================================
-- FIX: Geo Intelligence map showing "0 points"
-- =====================================================================
-- GeoIntelligenceMap in News.jsx is entirely client-side: it filters
-- the `events` array (already fetched via get_recent_events) for rows
-- where latitude/longitude aren't null. get_recent_events never
-- selected those two columns at all — so every event object had
-- `latitude: undefined, longitude: undefined`, the filter correctly
-- excluded all of them, and you got 0 points regardless of what's
-- actually in risk_events.latitude / risk_events.longitude.
--
-- This is a confirmed fix, not a guess like the severity_level one —
-- the missing columns are directly visible in the previous file's
-- RETURNS TABLE list. Adds latitude/longitude, keeps everything else
-- (including the severity_level COALESCE fix from
-- 21_severity_level_from_db.sql) unchanged.
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
  latitude numeric,
  longitude numeric,
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
    -- FIXED: were missing entirely — this is the actual "0 points" bug.
    re.latitude,
    re.longitude,
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

grant execute on function get_recent_events(integer, integer, date, date, text) to anon, authenticated;
