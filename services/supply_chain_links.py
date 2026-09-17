"""Structured supply chain link section for persistence and display."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from models.schemas import LinkedEntity, RiskAnalysis, RiskEvent
from services.display_format import expand_entity_labels


def _mpn_from_component_ref(canonical_id: str, canonical_name: str) -> str:
    raw = str(canonical_id or canonical_name or "").strip()
    if raw.upper().startswith("MPN:"):
        return raw[4:].strip()
    return raw


@lru_cache(maxsize=1)
def _component_catalog() -> dict[str, dict[str, Any]]:
    try:
        from canonical.matchers import _load_registry

        return dict(_load_registry().get("components") or {})
    except Exception:
        return {}


def _component_display_name(mpn: str) -> str:
    mpn = str(mpn or "").strip()
    if not mpn:
        return ""
    record = _component_catalog().get(mpn) or {}
    description = str(record.get("description") or "").strip()
    if description:
        return description
    return mpn


def _component_entries(entities: list[Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for entity in entities or []:
        if isinstance(entity, LinkedEntity):
            entity_id = str(entity.canonical_id or "").strip()
            raw_name = entity.canonical_name or entity.canonical_id
        elif isinstance(entity, dict):
            entity_id = str(entity.get("canonical_id") or entity.get("id") or "").strip()
            raw_name = entity.get("canonical_name") or entity.get("name") or entity_id
        else:
            continue

        mpn = _mpn_from_component_ref(entity_id, str(raw_name or ""))
        if not mpn:
            continue
        key = mpn.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "id": f"MPN:{mpn}",
                "name": _component_display_name(mpn),
                "mpn": mpn,
            }
        )
    return rows


def _refresh_component_entries(entries: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Resolve catalog descriptions for persisted component rows."""
    refreshed: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        mpn = str(entry.get("mpn") or "").strip()
        if not mpn:
            mpn = _mpn_from_component_ref(
                str(entry.get("id") or entry.get("canonical_id") or ""),
                str(entry.get("name") or entry.get("canonical_name") or ""),
            )
        if not mpn:
            continue
        key = mpn.lower()
        if key in seen:
            continue
        seen.add(key)
        stored_name = str(entry.get("name") or "").strip()
        catalog_name = _component_display_name(mpn)
        if (
            stored_name
            and stored_name.lower() != mpn.lower()
            and not stored_name.upper().startswith("MPN:")
        ):
            display = stored_name
        else:
            display = catalog_name
        refreshed.append(
            {
                "id": f"MPN:{mpn}",
                "name": display,
                "mpn": mpn,
            }
        )
    return refreshed


def _entries_from_strings(names: list[str] | None, *, id_prefix: str = "name") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in names or []:
        for label in expand_entity_labels(raw):
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            slug = key.replace(" ", "_")
            rows.append({"id": f"{id_prefix}:{slug}", "name": label})
    return rows


def _entries(entities: list[Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for entity in entities or []:
        if isinstance(entity, LinkedEntity):
            entity_id = str(entity.canonical_id or "").strip()
            raw_name = entity.canonical_name or entity.canonical_id
        elif isinstance(entity, dict):
            entity_id = str(entity.get("canonical_id") or "").strip()
            raw_name = entity.get("canonical_name") or entity.get("canonical_id")
        else:
            continue

        labels = expand_entity_labels(raw_name)
        if not labels and entity_id:
            labels = expand_entity_labels(entity_id)
        for label in labels:
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"id": entity_id or f"entity:{key.replace(' ', '_')}", "name": label})
    return rows


def merge_link_entries(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for entry in group:
            name = str(entry.get("name") or entry.get("id") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append({"id": str(entry.get("id") or f"name:{key.replace(' ', '_')}"), "name": name})
    return merged


def affected_manufacturers_from_analysis(risk_analysis: dict[str, Any] | RiskAnalysis | None) -> list[str]:
    if not risk_analysis:
        return []
    if isinstance(risk_analysis, RiskAnalysis):
        if risk_analysis.skipped:
            return []
        return list(risk_analysis.affected_manufacturers or [])
    if risk_analysis.get("skipped"):
        return []
    values = risk_analysis.get("affected_manufacturers") or []
    return [str(value).strip() for value in values if str(value).strip()]


def finalize_supply_chain_links(
    links: dict[str, Any] | None,
    *,
    linked: dict[str, Any] | None = None,
    risk_analysis: dict[str, Any] | RiskAnalysis | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Ensure manufacturers and affected_manufacturers are populated for display."""
    payload = dict(links or {})
    if not payload and linked:
        payload = build_supply_chain_links_from_linked_entities(linked)

    linked_payload = linked or {}
    manufacturers = payload.get("manufacturers") or _entries(linked_payload.get("linked_manufacturers"))
    ai_entries = _entries_from_strings(
        affected_manufacturers_from_analysis(risk_analysis),
        id_prefix="ai_mfr",
    )

    payload["manufacturers"] = manufacturers
    payload["affected_manufacturers"] = merge_link_entries(
        payload.get("affected_manufacturers") or [],
        manufacturers,
        ai_entries,
    )
    components = _refresh_component_entries(payload.get("components") or [])
    if not components and linked_payload.get("linked_components"):
        components = _component_entries(linked_payload.get("linked_components"))
    distributors = payload.get("distributors") or _entries(linked_payload.get("linked_suppliers"))
    locations = payload.get("locations") or _entries(linked_payload.get("linked_locations"))
    result = {
        "components": components,
        "distributors": distributors,
        "manufacturers": payload.get("manufacturers") or [],
        "affected_manufacturers": payload.get("affected_manufacturers") or [],
        "locations": locations,
    }
    if payload.get("storage_version"):
        result["storage_version"] = payload["storage_version"]
    if payload.get("persisted_at"):
        result["persisted_at"] = payload["persisted_at"]
    return result


def build_supply_chain_links(event: RiskEvent) -> dict[str, list[dict[str, str]]]:
    """Build the supply chain links section saved on each risk event."""
    links = build_supply_chain_links_from_parts(
        components=event.linked_components,
        distributors=event.linked_suppliers,
        manufacturers=event.linked_manufacturers,
        locations=event.linked_locations,
    )
    return finalize_supply_chain_links(
        links,
        linked={
            "linked_components": event.linked_components,
            "linked_suppliers": event.linked_suppliers,
            "linked_manufacturers": event.linked_manufacturers,
            "linked_locations": event.linked_locations,
        },
        risk_analysis=event.risk_analysis,
    )


def build_supply_chain_links_from_parts(
    *,
    components: list[Any] | None = None,
    distributors: list[Any] | None = None,
    manufacturers: list[Any] | None = None,
    locations: list[Any] | None = None,
) -> dict[str, list[dict[str, str]]]:
    return {
        "components": _component_entries(components),
        "distributors": _entries(distributors),
        "manufacturers": _entries(manufacturers),
        "affected_manufacturers": _entries(manufacturers),
        "locations": _entries(locations),
    }


def build_supply_chain_links_from_linked_entities(
    linked: dict[str, Any] | None,
) -> dict[str, list[dict[str, str]]]:
    payload = linked or {}
    return build_supply_chain_links_from_parts(
        components=payload.get("linked_components"),
        distributors=payload.get("linked_suppliers"),
        manufacturers=payload.get("linked_manufacturers"),
        locations=payload.get("linked_locations"),
    )


def link_names(links: dict[str, Any] | None, key: str) -> list[str]:
    names: list[str] = []
    for entry in (links or {}).get(key) or []:
        if not isinstance(entry, dict):
            continue
        for label in expand_entity_labels(entry.get("name") or entry.get("id")):
            if label not in names:
                names.append(label)
    return names
