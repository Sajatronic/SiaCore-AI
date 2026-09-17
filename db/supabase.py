"""
Supabase REST access layer for the supply chain catalog.

Uses PostgREST over HTTPS for catalog reads (suppliers, parts, inventory).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from config.settings import settings

logger = logging.getLogger("news_agent.db.supabase")

_PAGE_SIZE = 1000


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return a cached Supabase client."""
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "settings.supabase_url / settings.supabase_key are empty. "
            "Set SUPABASE_URL and SUPABASE_KEY in your .env "
            "(Project Settings -> API)."
        )
    client = create_client(settings.supabase_url, settings.supabase_key)
    logger.info("Supabase REST client created.")
    return client


class _SessionWrapper:
    """Compatibility wrapper so callers can call session.close()."""

    def __init__(self, client: Client):
        self._client = client

    def close(self) -> None:
        pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def get_session():
    """Return a Supabase client wrapper (close is a no-op)."""
    return _SessionWrapper(get_client())


def _fetch_all(client: Client, table: str, columns: str = "*") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + _PAGE_SIZE - 1
        resp = client.table(table).select(columns).range(start, end).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE
    return rows


_MANUFACTURER_ALIASES: dict[str, list[str]] = {
    "Texas Instruments": ["TI", "Texas Instruments Inc."],
    "Analog Devices": ["ADI", "Analog Devices Inc."],
    "Microchip Technology": ["Microchip", "MCHP"],
    "NXP Semiconductors": ["NXP"],
    "STMicroelectronics": ["ST", "STMicro"],
    "Renesas Electronics Corporation": ["Renesas"],
    "Infineon Technologies": ["Infineon"],
    "onsemi": ["ON Semiconductor", "ON Semi"],
}


def get_manufacturer_aliases(name: str) -> list[str]:
    return _MANUFACTURER_ALIASES.get(name, [])


def _is_dealt_with(row: dict[str, Any]) -> bool:
    value = str(row.get("dealt_with") or "").strip().lower()
    return value in {"yes", "y", "true", "1"}


@lru_cache(maxsize=1)
def _catalog_table_names() -> dict[str, str]:
    """Resolve live Supabase table names (schema evolved from legacy names)."""
    client = get_client()
    resolved: dict[str, str] = {}
    candidates = {
        "distributor": ("distributor", "distributer"),
        "manufacturer": ("manufacturers", "manufactures"),
    }
    for logical, options in candidates.items():
        for table in options:
            try:
                client.table(table).select("*").limit(1).execute()
                resolved[logical] = table
                break
            except Exception:
                continue
        if logical not in resolved:
            raise RuntimeError(
                f"Could not resolve Supabase catalog table for {logical!r} "
                f"(tried {options})."
            )
    return resolved


def _normalize_manufacturer_row(row: dict[str, Any], *, table: str) -> dict[str, Any]:
    if table == "manufacturers":
        name = row.get("Manufacturer") or ""
        return {
            "id": row.get("id"),
            "name": name,
            "country": row.get("HQ Country") or row.get("Mfg Country Count") or "",
            "headquarters": row.get("HQ Country") or "",
            "status": row.get("Status") or "",
            "aliases": get_manufacturer_aliases(name),
        }
    name = row.get("mfr") or ""
    return {
        "id": row.get("id"),
        "name": name,
        "country": row.get("country") or "",
        "headquarters": row.get("headquarters") or "",
        "status": row.get("status") or "",
        "aliases": get_manufacturer_aliases(name),
    }


def _fetch_active_distributer_rows(session: Client) -> list[dict[str, Any]]:
    table = _catalog_table_names()["distributor"]
    rows = _fetch_all(session, table)
    return [r for r in rows if _is_dealt_with(r)]


def query_suppliers(session: Client) -> list[dict[str, Any]]:
    rows = _fetch_active_distributer_rows(session)
    return [
        {
            "supplier_code": r.get("D_code"),
            "name": r.get("D_Name") or r.get("D_code"),
            "supplier_type": r.get("D_Type"),
            "country": r.get("D_country"),
            "headquarters": r.get("D_headquarters"),
            "authorized": r.get("D_authorized"),
            "status": r.get("D_status"),
            "website": r.get("D_website"),
            "dealt_with": r.get("dealt_with"),
            "relationship_risk_score": r.get("relationship_risk_score"),
            "relationship_risk_level": r.get("relationship_risk_level"),
            "relationship_tier": r.get("relationship_tier"),
        }
        for r in rows
    ]


def query_manufacturers(session: Client) -> list[dict[str, Any]]:
    table = _catalog_table_names()["manufacturer"]
    rows = _fetch_all(session, table)
    result: list[dict[str, Any]] = []
    for row in rows:
        normalized = _normalize_manufacturer_row(row, table=table)
        if normalized.get("name"):
            result.append(normalized)
    return result


def query_parts(session: Client) -> list[dict[str, Any]]:
    part_rows = _fetch_all(session, "parts")
    mfr_table = _catalog_table_names()["manufacturer"]
    mfr_rows = _fetch_all(session, mfr_table)
    cat_rows = _fetch_all(session, "parts_category")

    mfr_by_id = {
        r.get("id"): _normalize_manufacturer_row(r, table=mfr_table)["name"]
        for r in mfr_rows
    }
    cat_by_id = {r.get("id"): r.get("Name") or "" for r in cat_rows}

    result = []
    for row in part_rows:
        mpn = row.get("mpn")
        if not mpn:
            continue
        result.append(
            {
                "mpn": mpn,
                "manufacturer": mfr_by_id.get(row.get("mfr_id"), ""),
                "category_name": cat_by_id.get(row.get("Mfr Category ID")) or "catalog",
                "description": row.get("description") or "",
                "package": row.get("package") or "",
            }
        )
    return result


def query_inventory_supplier_map(session: Client) -> list[dict[str, Any]]:
    inv_rows = _fetch_all(session, "inventory")
    supplier_rows = _fetch_active_distributer_rows(session)
    part_rows = _fetch_all(session, "parts")
    mfr_table = _catalog_table_names()["manufacturer"]
    mfr_rows = _fetch_all(session, mfr_table)
    cat_rows = _fetch_all(session, "parts_category")

    valid_supplier_codes = {r.get("D_code") for r in supplier_rows if r.get("D_code")}
    mfr_by_id = {
        r.get("id"): _normalize_manufacturer_row(r, table=mfr_table)["name"]
        for r in mfr_rows
    }
    cat_by_id = {r.get("id"): r.get("Name") or "" for r in cat_rows}
    part_by_mpn = {r.get("mpn"): r for r in part_rows if r.get("mpn")}

    result = []
    for row in inv_rows:
        supplier_code = row.get("supplier_id")
        if supplier_code not in valid_supplier_codes:
            continue
        mpn = row.get("mpn") or ""
        part = part_by_mpn.get(mpn, {})
        manufacturer = mfr_by_id.get(part.get("mfr_id"), "") if part else ""
        category_name = cat_by_id.get(part.get("Mfr Category ID")) if part else None

        result.append(
            {
                "supplier_code": supplier_code,
                "manufacturer": manufacturer,
                "category_name": category_name or "catalog",
                "mpn": mpn,
                "lead_time_days": row.get("lead_time_days") or row.get("lead_time"),
                "quantity": row.get("quantity") or row.get("qty"),
            }
        )
    return result


def query_inventory_lead_times(session: Client) -> list[dict[str, Any]]:
    """Inventory rows with optional lead-time fields for impact forecasting."""
    return query_inventory_supplier_map(session)


def query_categories(session: Client) -> list[str]:
    rows = _fetch_all(session, "parts_category")
    return [r.get("Name") for r in rows if r.get("Name")]
