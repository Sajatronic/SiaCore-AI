-- =====================================================================
-- SiaCore — Patch: map + active-alerts fields on get_recent_events
-- =====================================================================
-- Adds latitude/longitude/severity_score/event_category/geo_region/
-- geo_country to the existing get_recent_events result, so the News
-- page can plot a map and build an "Active Alerts" panel from the same
-- single fetch already happening — no second round-trip needed.
--
-- Run this, then: NOTIFY pgrst, 'reload schema';
-- =====================================================================

do $$
declare r record;
begin
  for r in select oid::regprocedure as sig from pg_proc
    where proname = 'get_recent_events' and pronamespace = 'public'::regnamespace
  loop execute format('drop function %s;', r.sig); end loop;
end $$;

create or replace function get_recent_events(
  p_severity_min integer default 0,
  p_limit integer default 50,
  p_start date default null,
  p_end date default null,
  p_search text default null
)
returns table (
  event_id text,
  title text,
  summary text,
  severity_signal text,
  severity_score real,
  event_category text,
  geo_region text,
  geo_country text,
  latitude double precision,
  longitude double precision,
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
    re.severity_score,
    re.event_category,
    re.geo_region,
    re.geo_country,
    re.latitude,
    re.longitude,
    re.retrieval_timestamp                                 as retrieved_at
  from risk_events re
  where re.status::text is distinct from 'closed'
    and coalesce(re.severity_score, 0) >= p_severity_min
    and (p_start is null or re.retrieval_timestamp::date >= p_start)
    and (p_end is null or re.retrieval_timestamp::date <= p_end)
    and (p_search is null
      or re.title ilike '%' || p_search || '%'
      or re.summary ilike '%' || p_search || '%')
  order by re.title, re.retrieval_timestamp desc
  limit p_limit;
$$;

grant execute on function get_recent_events(integer, integer, date, date, text) to anon, authenticated;

NOTIFY pgrst, 'reload schema';
