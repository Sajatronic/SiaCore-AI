"""
Canonical entity registry builder.

Queries the Supply Chain SQL Server database directly via SQLAlchemy.
CSV files and pandas are no longer required.

Public API (unchanged):
    build_canonical_entities() -> dict
    write_canonical_entities(output_path=None) -> Path   # optional JSON cache
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from config.settings import settings
from db import (
    get_session,
    query_inventory_supplier_map,
    query_manufacturers,
    query_parts,
    query_suppliers,
)

logger = logging.getLogger("news_agent.canonical.entity_registry")

# Fixed region list — not stored in the DB
_REGIONS = [
    "Europe",
    "Asia-Pacific",
    "Middle-East",
    "Africa",
    "Latin-America",
    "North-America",
]


def build_canonical_entities() -> dict[str, Any]:
    """
    Build the canonical entity registry by querying the Supply Chain DB.

    Returns a dict with the same structure as the old canonical_entities.json
    so that all downstream consumers (matchers, prefilter) work without change.
    """
    session = get_session()
    try:
        return _build(session)
    except Exception:
        logger.exception("Failed to build canonical entities from DB")
        return _load_registry_snapshot_fallback()
    finally:
        session.close()


def _augment_supplier_mpns(registry: dict[str, Any]) -> dict[str, Any]:
    """Ensure each supplier has linked_mpns (from components when missing)."""
    components = registry.get("components") or {}
    for code, record in (registry.get("suppliers") or {}).items():
        if record.get("linked_mpns"):
            continue
        mpns = sorted(
            mpn
            for mpn, comp in components.items()
            if isinstance(comp, dict) and comp.get("supplier_id") == code
        )
        record["linked_mpns"] = mpns
    return registry


def _load_registry_snapshot_fallback() -> dict[str, Any]:
    """Load cached canonical_entities.json when live catalog queries fail."""
    path = settings.project_root / settings.canonical_entities_path
    if not path.is_file():
        raise RuntimeError(
            f"Catalog DB unavailable and no snapshot at {path}. "
            "Run `python main.py --export-entities` when the DB is reachable."
        )
    logger.warning("Loading canonical entity snapshot from %s", path)
    registry = json.loads(path.read_text(encoding="utf-8"))
    return _augment_supplier_mpns(registry)


def _build(session) -> dict[str, Any]:
    # ── 1. Raw DB rows ────────────────────────────────────────────────────────
    supplier_rows = query_suppliers(session)
    manufacturer_rows = query_manufacturers(session)
    part_rows = query_parts(session)
    inv_rows = query_inventory_supplier_map(session)

    # ── 2. Build lookup: supplier_code → {manufacturers, categories} ──────────
    # Derived from the Inventory table which links supplier_id → MPN → Mfr/Category
    sup_mfrs: dict[str, set[str]] = defaultdict(set)
    sup_cats: dict[str, set[str]] = defaultdict(set)
    sup_mpns: dict[str, set[str]] = defaultdict(set)
    for row in inv_rows:
        sc = row["supplier_code"]
        if row["manufacturer"]:
            sup_mfrs[sc].add(row["manufacturer"])
        if row["category_name"]:
            sup_cats[sc].add(row["category_name"])
        if row["mpn"]:
            sup_mpns[sc].add(row["mpn"])

    # ── 3. Suppliers ──────────────────────────────────────────────────────────
    suppliers: dict[str, dict[str, Any]] = {}
    for row in supplier_rows:
        code = row["supplier_code"]
        suppliers[code] = {
            "canonical_id": code,
            "name": row["name"] or code,
            "entity_type": "SUPPLIER",
            "linked_manufacturers": sorted(sup_mfrs.get(code, [])),
            "linked_mpns": sorted(sup_mpns.get(code, [])),
            "categories": sorted(sup_cats.get(code, [])),
            # Extra fields from DB (not in old JSON but harmless to include)
            "country": row["country"],
            "supplier_type": row["supplier_type"],
            "authorized": row["authorized"],
            "status": row["status"],
            "relationship_risk_score": row.get("relationship_risk_score"),
            "relationship_risk_level": row.get("relationship_risk_level"),
            "relationship_tier": row.get("relationship_tier"),
        }

    # ── 4. Build lookup: manufacturer name → supplier_codes ──────────────────
    mfr_suppliers: dict[str, set[str]] = defaultdict(set)
    for row in inv_rows:
        if row["manufacturer"] and row["supplier_code"]:
            mfr_suppliers[row["manufacturer"]].add(row["supplier_code"])

    # Build lookup: manufacturer name → MPNs (from inventory rows)
    mfr_mpns: dict[str, set[str]] = defaultdict(set)
    for row in inv_rows:
        if row["manufacturer"] and row["mpn"]:
            mfr_mpns[row["manufacturer"]].add(row["mpn"])

    # ── 5. Manufacturers ──────────────────────────────────────────────────────
    manufacturers: dict[str, dict[str, Any]] = {}
    for row in manufacturer_rows:
        name = row["name"]
        manufacturers[name] = {
            "canonical_id": f"MFR:{name}",
            "name": name,
            "entity_type": "MANUFACTURER",
            "aliases": row["aliases"],
            "mpns": sorted(mfr_mpns.get(name, []))[:500],
            "supplier_ids": sorted(mfr_suppliers.get(name, [])),
            # Extra DB fields
            "country": row["country"],
            "headquarters": row["headquarters"],
            "status": row["status"],
        }

    # ── 6. Components (Parts) ─────────────────────────────────────────────────
    # Primary source: Parts table (full catalog).
    # Supplier ID is resolved via the Inventory rows.
    mpn_supplier: dict[str, str] = {}
    for row in inv_rows:
        mpn = row["mpn"]
        if mpn and mpn not in mpn_supplier:
            mpn_supplier[mpn] = row["supplier_code"]

    components: dict[str, dict[str, Any]] = {}
    for row in part_rows:
        mpn = row["mpn"]
        if not mpn:
            continue
        components[mpn] = {
            "canonical_id": f"MPN:{mpn}",
            "name": mpn,
            "entity_type": "COMPONENT",
            "manufacturer": row["manufacturer"],
            "category_name": row["category_name"],
            "supplier_id": mpn_supplier.get(mpn),
            "description": row["description"],
            "package": row["package"],
        }

    # ── 7. Assemble ───────────────────────────────────────────────────────────
    return {
        "version": "1.0.0",
        "suppliers": suppliers,
        "manufacturers": manufacturers,
        "components": components,
        "regions": _REGIONS,
        "stats": {
            "supplier_count": len(suppliers),
            "manufacturer_count": len(manufacturers),
            "component_count": len(components),
        },
    }


def write_canonical_entities(output_path: Path | None = None) -> Path:
    """
    Build registry from DB and write a JSON snapshot to disk.

    This is now optional — the pipeline reads from the DB directly.
    The snapshot is useful for debugging, auditing, or offline use.
    """
    output = output_path or (settings.project_root / settings.canonical_entities_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    entities = build_canonical_entities()
    output.write_text(json.dumps(entities, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote canonical entities snapshot to %s", output)
    return output


if __name__ == "__main__":
    path = write_canonical_entities()
    print(f"Wrote canonical entities to {path}")