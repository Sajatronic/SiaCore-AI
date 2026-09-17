-- =====================================================================
-- SiaCore — Patch: sort Latest Stock Information, authorized first
-- =====================================================================
-- Replaces get_part_stock_suppliers's ORDER BY only — run this whole
-- file, then:
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

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
  order by
    -- Authorized rows first, regardless of the exact stored text —
    -- case-insensitive so it still works if the source data varies
    -- between 'Authorized', 'authorized', etc.
    case when lower(st."Authorized_Dist") = 'authorized' then 0 else 1 end,
    coalesce(d."D_Name", st.distributer_code),
    st."Price_Break_Qty";
$$;

grant execute on function get_part_stock_suppliers(text, date, date) to anon, authenticated;

NOTIFY pgrst, 'reload schema';
