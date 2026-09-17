-- =====================================================================
-- SiaCore — Patch: Distributors list columns + sort order
-- =====================================================================
-- Replaces get_all_distributors from sql/08_distributors_page.sql —
-- run this whole file, then:
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

do $$
declare r record;
begin
  for r in select oid::regprocedure as sig from pg_proc
    where proname = 'get_all_distributors' and pronamespace = 'public'::regnamespace
  loop execute format('drop function %s;', r.sig); end loop;
end $$;

create or replace function get_all_distributors(
  p_search text default null,
  p_limit integer default 100,
  p_offset integer default 0
)
returns table (
  d_code text,
  d_name text,
  d_type text,
  d_country text,
  d_authorized text,
  relationship_risk_level text,
  relationship_risk_score numeric,
  last_modified_date timestamptz
)
language sql
stable
as $$
  select
    d."D_code",
    d."D_Name",
    d."D_Type",
    d."D_country",
    d."D_authorized",
    coalesce(d.relationship_risk_level, 'Unclassified'),
    d.relationship_risk_score,
    d."Last_Modified_Date"
  from distributer d
  where (p_search is null
    or d."D_Name" ilike '%' || p_search || '%'
    or d."D_code" ilike '%' || p_search || '%'
    or d."D_country" ilike '%' || p_search || '%')
  -- Low risk first, as asked — nulls (unscored) sort last either way.
  order by d.relationship_risk_score asc nulls last, d."D_Name"
  limit p_limit offset p_offset;
$$;

grant execute on function get_all_distributors(text, integer, integer) to anon, authenticated;

NOTIFY pgrst, 'reload schema';
