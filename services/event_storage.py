"""Prepare and backfill fully denormalized event payloads for Supabase storage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from models.schemas import LinkedEntity, RiskEvent
from services.supply_chain_links import build_supply_chain_links, finalize_supply_chain_links

logger = logging.getLogger("news_agent.services.event_storage")

STORAGE_VERSION = "1"

_LINKED_KEYS = (
    "linked_components",
    "linked_suppliers",
    "linked_manufacturers",
    "linked_locations",
)


def _linked_dict_from_event(event: RiskEvent) -> dict[str, list[dict[str, Any]]]:
    return {
        "linked_components": [e.model_dump(mode="json") for e in event.linked_components],
        "linked_suppliers": [e.model_dump(mode="json") for e in event.linked_suppliers],
        "linked_manufacturers": [e.model_dump(mode="json") for e in event.linked_manufacturers],
        "linked_locations": [e.model_dump(mode="json") for e in event.linked_locations],
    }


def _entities_from_linked_dict(linked: dict[str, Any]) -> dict[str, list[LinkedEntity]]:
    from canonical.matchers import linked_entity_from_dict

    groups: dict[str, list[LinkedEntity]] = {}
    for key in _LINKED_KEYS:
        parsed: list[LinkedEntity] = []
        for item in linked.get(key) or []:
            if isinstance(item, LinkedEntity):
                parsed.append(item)
                continue
            if isinstance(item, dict):
                entity = linked_entity_from_dict(item)
                if entity is not None:
                    parsed.append(entity)
        groups[key] = parsed
    return groups


def prepare_risk_event_for_persistence(event: RiskEvent) -> RiskEvent:
    """
    Expand catalog joins and sync linked entity fields before writing to Supabase.

    Ensures inferred distributors, manufacturers, and parts are stored on the row,
    not recomputed when SiaEye reads the event.
    """
    from canonical.matchers import enrich_linked_entities_with_catalog

    linked = enrich_linked_entities_with_catalog(_linked_dict_from_event(event))
    groups = _entities_from_linked_dict(linked)

    event.linked_components = groups["linked_components"]
    event.linked_suppliers = groups["linked_suppliers"]
    event.linked_manufacturers = groups["linked_manufacturers"]
    event.linked_locations = groups["linked_locations"]
    return event


def persisted_supply_chain_links(event: RiskEvent) -> dict[str, Any]:
    """Build the denormalized supply chain section saved on risk_events."""
    links = dict(build_supply_chain_links(event))
    links["storage_version"] = STORAGE_VERSION
    links["persisted_at"] = datetime.now(timezone.utc).isoformat()
    return links


def linked_entities_payload(event: RiskEvent) -> dict[str, Any]:
    """JSON payload for risk_events.linked_entities after catalog enrichment."""
    return {
        "extracted_entities": [e.model_dump(mode="json") for e in event.extracted_entities],
        "linked_manufacturers": [e.model_dump(mode="json") for e in event.linked_manufacturers],
        "linked_suppliers": [e.model_dump(mode="json") for e in event.linked_suppliers],
        "linked_locations": [e.model_dump(mode="json") for e in event.linked_locations],
        "linked_components": [e.model_dump(mode="json") for e in event.linked_components],
    }


def supply_chain_links_stored(links: dict[str, Any] | None) -> bool:
    """True when the row already has a persisted supply chain section."""
    if not links:
        return False
    return bool(links.get("storage_version"))


def resolve_stored_supply_chain_links(
    *,
    supply_chain_links: dict[str, Any] | None,
    linked: dict[str, Any] | None,
    risk_analysis: dict[str, Any] | None = None,
    allow_catalog_enrich: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Resolve linked entities + supply chain links for API output.

    Prefer data stored on risk_events; only run catalog joins for legacy rows.
    """
    linked_payload = dict(linked or {})
    links_payload = dict(supply_chain_links or {})

    if allow_catalog_enrich and not supply_chain_links_stored(links_payload):
        from canonical.matchers import enrich_linked_entities_with_catalog

        linked_payload = enrich_linked_entities_with_catalog(
            {
                "linked_components": linked_payload.get("linked_components"),
                "linked_suppliers": linked_payload.get("linked_suppliers"),
                "linked_manufacturers": linked_payload.get("linked_manufacturers"),
                "linked_locations": linked_payload.get("linked_locations"),
            }
        )

    resolved_links = finalize_supply_chain_links(
        links_payload,
        linked=linked_payload,
        risk_analysis=risk_analysis,
    )
    return linked_payload, resolved_links


def backfill_supabase_events(*, dry_run: bool = False) -> dict[str, Any]:
    """
    Recompute and persist linked_entities + supply_chain_links for all risk_events.

    Loads event_analyses so affected manufacturers are merged into stored links.
    """
    from db.supabase import get_client

    client = get_client()

    analyses_by_event: dict[str, dict[str, Any]] = {}
    start = 0
    page_size = 1000
    while True:
        end = start + page_size - 1
        resp = client.table("event_analyses").select("event_id,analysis").range(start, end).execute()
        batch = resp.data or []
        for row in batch:
            event_id = str(row.get("event_id") or "")
            if event_id:
                analyses_by_event[event_id] = row.get("analysis") or {}
        if len(batch) < page_size:
            break
        start += page_size

    updated = 0
    skipped = 0
    start = 0
    while True:
        end = start + page_size - 1
        resp = client.table("risk_events").select("*").range(start, end).execute()
        rows = resp.data or []
        for row in rows:
            event_id = str(row.get("event_id") or "")
            linked = row.get("linked_entities") or {}
            analysis = analyses_by_event.get(event_id)
            linked_payload, links = resolve_stored_supply_chain_links(
                supply_chain_links=row.get("supply_chain_links"),
                linked={
                    "linked_components": linked.get("linked_components"),
                    "linked_suppliers": linked.get("linked_suppliers"),
                    "linked_manufacturers": linked.get("linked_manufacturers"),
                    "linked_locations": linked.get("linked_locations"),
                },
                risk_analysis=analysis,
                allow_catalog_enrich=True,
            )
            links["storage_version"] = STORAGE_VERSION
            links["persisted_at"] = datetime.now(timezone.utc).isoformat()

            payload = {
                "linked_entities": {
                    **linked,
                    "linked_components": linked_payload.get("linked_components") or [],
                    "linked_suppliers": linked_payload.get("linked_suppliers") or [],
                    "linked_manufacturers": linked_payload.get("linked_manufacturers") or [],
                    "linked_locations": linked_payload.get("linked_locations") or [],
                },
                "supply_chain_links": links,
            }

            if dry_run:
                updated += 1
                continue

            try:
                client.table("risk_events").update(payload).eq("event_id", event_id).execute()
                updated += 1
            except Exception as exc:
                logger.warning("Backfill failed for %s: %s", event_id, exc)
                skipped += 1

        if len(rows) < page_size:
            break
        start += page_size

    return {
        "status": "ok",
        "updated": updated,
        "skipped": skipped,
        "dry_run": dry_run,
        "storage_version": STORAGE_VERSION,
    }
