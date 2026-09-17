"""Fuzzy entity linking against the canonical registry — DB-backed."""

from __future__ import annotations

import json
import logging
import re
import traceback
from functools import lru_cache
from typing import Any

from rapidfuzz import fuzz

from config.settings import settings
from config.strategic_locations import STRATEGIC_LOCATIONS
from db import get_session, query_manufacturers, query_parts, query_suppliers
from models.schemas import EntityType, ExtractedEntity, LinkedEntity
from services.display_format import expand_entity_labels

logger = logging.getLogger("news_agent.canonical.matchers")

SYSTEM_PROMPT = """You are an expert entity resolution (entity linking) assistant in a supply chain risk intelligence platform.
Your task is to resolve entity mentions extracted from a news article to their canonical entities in our registry.

We have four types of entities:
- SUPPLIER: Canonical IDs are like "SUP001", "SUP002", etc.
- MANUFACTURER: Canonical IDs are like "MFR:Texas Instruments" (prefixed with "MFR:").
- LOCATION: Canonical IDs are like "LOC:taiwan" (prefixed with "LOC:").
- COMPONENT: Canonical IDs are like "MPN:ADS1256" (prefixed with "MPN:").

You will be given:
1. The news article text.
2. The list of extracted entity mentions.
3. The canonical registry database.

For each extracted entity mention, determine if it matches a canonical entity in the registry (either exactly, by alias, or by close context/meaning).
Additionally, scan the news article text for any component part numbers (MPNs) listed under COMPONENTS in the registry. Link any matched component to its MPN canonical ID.

Your output MUST be a valid JSON object containing a "matches" key, which holds an array of matched entities in this exact format:
{
  "matches": [
    {
      "extracted_text": "mention text",
      "canonical_id": "canonical ID (e.g. MFR:Texas Instruments or SUP002 or LOC:taiwan or MPN:ADS1256)",
      "canonical_name": "canonical Name (e.g. Texas Instruments or SUP002 or Taiwan or ADS1256)",
      "entity_type": "MANUFACTURER" | "SUPPLIER" | "LOCATION" | "COMPONENT",
      "match_score": float,
      "requires_review": bool
    }
  ]
}

Only return matches that are valid canonical entities in the registry. If a mention cannot be mapped to any canonical entity in the registry, do NOT include a match for it.
Do not output any markdown formatting, only return the JSON object.
"""

# Fixed region list (not in DB)
_REGIONS = [
    "Europe",
    "Asia-Pacific",
    "Middle-East",
    "Africa",
    "Latin-America",
    "North-America",
]

@lru_cache(maxsize=1)
def _get_known_countries() -> dict[str, str]:
    """
    Every distinct, real country value found in the DB, keyed by lowercase
    for matching, valued by the original casing for display.

    Pulled straight from supplier (`distributer.D_country`) and manufacturer
    (`manufacturers.country`) rows — nothing hardcoded or guessed. If a
    country isn't in your data, it can't be extracted or matched.
    """
    registry = _load_registry()
    countries: dict[str, str] = {}

    for record in registry.get("suppliers", {}).values():
        country = (record.get("country") or "").strip()
        if country:
            countries[country.lower()] = country

    for record in registry.get("manufacturers", {}).values():
        country = (record.get("country") or "").strip()
        if country:
            countries[country.lower()] = country

    return countries


def _metadata_geo_values(metadata: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract location strings from GDELT/GDACS-style provider metadata."""
    raw = metadata.get("raw") if isinstance(metadata.get("raw"), dict) else metadata
    geo = raw.get("geo") if isinstance(raw, dict) else {}
    if not isinstance(geo, dict):
        geo = {}

    values: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(value: Any, source: str) -> None:
        for text in expand_entity_labels(value):
            if len(text) < 2:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append((text, source))

    add(geo.get("country"), "geo.country")
    add(geo.get("admin1"), "geo.admin1")
    add(geo.get("location"), "geo.location")
    add(raw.get("country") if isinstance(raw, dict) else None, "raw.country")
    add(metadata.get("country"), "provider.country")

    affected = raw.get("affected_countries") if isinstance(raw, dict) else None
    if isinstance(affected, list):
        for entry in affected:
            if isinstance(entry, dict):
                add(entry.get("countryname") or entry.get("country"), "affected_countries")
            else:
                add(entry, "affected_countries")

    return values


def extract_metadata_geo_entities(
    metadata: dict[str, Any] | None,
    article_id: str | None = None,
) -> list[ExtractedEntity]:
    """Create location entities from structured geo fields when absent from article text."""
    if not metadata:
        return []

    entities: list[ExtractedEntity] = []
    for display, source in _metadata_geo_values(metadata):
        entities.append(
            ExtractedEntity(
                text=display,
                entity_type=EntityType.LOCATION,
                confidence=0.92,
                source_article_id=article_id,
            )
        )
    return entities


def extract_strategic_location_entities(
    text: str,
    article_id: str | None = None,
) -> list[ExtractedEntity]:
    """Match supply-chain chokepoints and strategic locations in text."""
    lowered = text.lower()
    entities: list[ExtractedEntity] = []
    seen: set[str] = set()

    for location in sorted(STRATEGIC_LOCATIONS, key=len, reverse=True):
        if location not in lowered:
            continue
        key = location.lower()
        if key in seen:
            continue
        seen.add(key)
        start, end = _find_spans(text, location)
        entities.append(
            ExtractedEntity(
                text=text[start:end] if start is not None else location,
                entity_type=EntityType.LOCATION,
                start_char=start,
                end_char=end,
                confidence=0.88,
                source_article_id=article_id,
            )
        )
    return entities


def _inject_geo_linked_entities(
    linked: list[LinkedEntity],
    metadata: dict[str, Any] | None,
) -> list[LinkedEntity]:
    """Add canonical location links from provider geo metadata."""
    if not metadata:
        return linked

    existing = {(item.canonical_id, item.entity_type) for item in linked}
    for display, source in _metadata_geo_values(metadata):
        canonical_id = f"LOC:{display.lower()}"
        key = (canonical_id, EntityType.LOCATION)
        if key in existing:
            continue
        linked.append(
            LinkedEntity(
                canonical_id=canonical_id,
                canonical_name=display,
                entity_type=EntityType.LOCATION,
                match_score=0.93,
                match_method=source,
                extracted_text=display,
            )
        )
        existing.add(key)
    return linked


def _dedupe_linked(linked: list[LinkedEntity]) -> list[LinkedEntity]:
    deduped: dict[tuple[str, EntityType], LinkedEntity] = {}
    for item in linked:
        key = (item.canonical_id, item.entity_type)
        existing = deduped.get(key)
        if existing is None or item.match_score > existing.match_score:
            deduped[key] = item
    return list(deduped.values())


def _finalize_linked_entities(
    linked: list[LinkedEntity],
    metadata: dict[str, Any] | None,
    registry: dict[str, Any],
) -> list[LinkedEntity]:
    linked = _inject_geo_linked_entities(linked, metadata)
    linked.extend(_expand_suppliers_by_location(linked, registry))
    linked.extend(_expand_manufacturers_by_location(linked, registry))
    linked.extend(_expand_manufacturers_by_supplier(linked, registry))
    linked.extend(_expand_components_by_catalog(linked, registry))
    return _dedupe_linked(linked)


def _location_matches_country(location: str, country: str) -> bool:
    """Exact/substring match between an extracted location and a supplier's
    real DB country value. No region-to-country guessing — if it's not in
    the data, it doesn't match."""
    if not location or not country:
        return False
    location = location.strip().lower()
    country = country.strip().lower()
    return location == country or location in country or country in location


# ── Registry loader ────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    """
    Build the in-memory registry dict from the Supply Chain DB.

    Uses lru_cache so the DB is only queried once per process lifetime.
    Call _invalidate_registry_cache() to force a refresh.
    """
    from canonical.entity_registry import build_canonical_entities
    return build_canonical_entities()


def _invalidate_registry_cache() -> None:
    """Clear the cached registry so the next call re-queries the DB."""
    _load_registry.cache_clear()
    _get_registry_summary.cache_clear()
    _get_known_countries.cache_clear()
    logger.info("Registry cache cleared — next access will re-query DB.")


# ── Registry summary for LLM prompt ──────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_registry_summary() -> str:
    registry = _load_registry()

    suppliers_lines = []
    for k, v in registry.get("suppliers", {}).items():
        suppliers_lines.append(
            f"- {k} (Supplier ID): linked to manufacturers: {v.get('linked_manufacturers', [])}"
        )

    mfrs_lines = []
    for k, v in registry.get("manufacturers", {}).items():
        mfrs_lines.append(f"- {k} (ID: MFR:{k}): aliases: {v.get('aliases', [])}")

    regions_str = ", ".join(registry.get("regions", []))
    components_str = ", ".join(registry.get("components", {}).keys())

    return (
        "=== CANONICAL REGISTRY ===\n\n"
        f"SUPPLIERS (IDs):\n{chr(10).join(suppliers_lines)}\n\n"
        f"MANUFACTURERS (Names & Aliases):\n{chr(10).join(mfrs_lines)}\n\n"
        f"REGIONS (LOCATIONS):\n{regions_str}\n\n"
        f"COMPONENTS (Manufacturer Part Numbers / MPNs):\n{components_str}\n"
    )


def _truncate_text(text: str, max_chars: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def _get_compact_registry_summary(
    extracted: list[ExtractedEntity],
    text: str,
    registry: dict[str, Any],
) -> str:
    """Send only fuzzy-matched candidates + in-text MPNs/locations (not the full catalog)."""
    mfr_lines: list[str] = []
    supplier_lines: list[str] = []
    loc_lines: list[str] = []
    component_lines: list[str] = []
    seen_mfr: set[str] = set()
    seen_supplier: set[str] = set()
    seen_loc: set[str] = set()
    seen_mpn: set[str] = set()

    for entity in extracted:
        if entity.entity_type == EntityType.MANUFACTURER:
            ranked: list[tuple[float, str, dict[str, Any]]] = []
            for name, data in registry.get("manufacturers", {}).items():
                score = fuzz.partial_ratio(entity.text.lower(), name.lower())
                ranked.append((score, name, data))
            ranked.sort(key=lambda item: item[0], reverse=True)
            for score, name, data in ranked[:5]:
                if score < 60 or name in seen_mfr:
                    continue
                seen_mfr.add(name)
                mfr_lines.append(f"- MFR:{name} (aliases: {data.get('aliases', [])})")
                for supplier_id in data.get("supplier_ids", [])[:3]:
                    sid = str(supplier_id)
                    if sid in seen_supplier:
                        continue
                    seen_supplier.add(sid)
                    supplier_lines.append(f"- {sid} (linked to {name})")

        elif entity.entity_type == EntityType.SUPPLIER:
            code = entity.text.upper()
            if code in registry.get("suppliers", {}) and code not in seen_supplier:
                seen_supplier.add(code)
                supplier_lines.append(f"- {code}")

    text_lower = text.lower()
    for region in registry.get("regions", []):
        key = region.lower()
        if key in text_lower and key not in seen_loc:
            seen_loc.add(key)
            loc_lines.append(f"- LOC:{region}")

    for location in STRATEGIC_LOCATIONS:
        key = location.lower()
        if key in text_lower and key not in seen_loc:
            seen_loc.add(key)
            loc_lines.append(f"- LOC:{location}")

    for match in re.finditer(r"\b[A-Z0-9]{3,}[A-Z0-9\-/_]{2,}\b", text.upper()):
        mpn = match.group(0)
        if mpn in registry.get("components", {}) and mpn not in seen_mpn:
            seen_mpn.add(mpn)
            component_lines.append(f"- MPN:{mpn}")

    sections = ["=== RELEVANT REGISTRY CANDIDATES ==="]
    if mfr_lines:
        sections.append("MANUFACTURERS:\n" + "\n".join(mfr_lines))
    if supplier_lines:
        sections.append("SUPPLIERS:\n" + "\n".join(supplier_lines))
    if loc_lines:
        sections.append("LOCATIONS:\n" + "\n".join(loc_lines))
    if component_lines:
        sections.append("COMPONENTS:\n" + "\n".join(component_lines))
    if len(sections) == 1:
        sections.append("(No strong candidates — resolve best-effort from mentions only.)")
    return "\n\n".join(sections)


def _extracted_covered(extracted: list[ExtractedEntity], linked: list[LinkedEntity]) -> bool:
    if not extracted:
        return True
    if not linked:
        return False
    for entity in extracted:
        if not any(
            link.extracted_text.lower() == entity.text.lower()
            for link in linked
        ):
            return False
    return True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):]
    if text.startswith("```"):
        text = text[len("```"):]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _find_spans(text: str, needle: str) -> tuple[int, int] | tuple[None, None]:
    if not needle:
        return None, None
    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None, None
    return match.start(), match.end()


def _text_blob(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part).lower()


def _expand_suppliers_by_location(
    linked: list[LinkedEntity], registry: dict[str, Any]
) -> list[LinkedEntity]:
    """
    Link suppliers via geography instead of manufacturer name / MPN text.

    Real news articles rarely name our exact manufacturers and never contain
    a literal MPN, but they very reliably mention a country/region. This
    matches any already-linked LOCATION against each supplier's registered
    country and adds a SUPPLIER link for every match.

    Deliberately lower confidence (0.6) and flagged for review, since a
    shared country is a much weaker signal than an exact manufacturer or
    MPN match.
    """
    location_names = {
        item.canonical_name for item in linked if item.entity_type == EntityType.LOCATION
    }
    if not location_names:
        return []

    additions: list[LinkedEntity] = []
    for code, record in registry.get("suppliers", {}).items():
        country = record.get("country") or ""
        if not country:
            continue
        for location in location_names:
            if _location_matches_country(location, country):
                additions.append(
                    LinkedEntity(
                        canonical_id=code,
                        canonical_name=record.get("name", code),
                        entity_type=EntityType.SUPPLIER,
                        match_score=0.6,
                        match_method="location_supplier_map",
                        extracted_text=location,
                        requires_review=True,
                    )
                )
                break  # one match per supplier is enough
    return additions


def _linked_supplier_codes(linked: list[LinkedEntity]) -> set[str]:
    return {
        item.canonical_id
        for item in linked
        if item.entity_type == EntityType.SUPPLIER and item.canonical_id
    }


def _linked_manufacturer_names(linked: list[LinkedEntity]) -> set[str]:
    names: set[str] = set()
    for item in linked:
        if item.entity_type != EntityType.MANUFACTURER:
            continue
        if item.canonical_id.startswith("MFR:"):
            names.add(item.canonical_id[4:])
        elif item.canonical_name:
            names.add(item.canonical_name)
    return names


def _expand_manufacturers_by_location(
    linked: list[LinkedEntity], registry: dict[str, Any]
) -> list[LinkedEntity]:
    """Join affected locations to manufacturers registered in the same country."""
    location_names = {
        item.canonical_name for item in linked if item.entity_type == EntityType.LOCATION
    }
    if not location_names:
        return []

    additions: list[LinkedEntity] = []
    for name, record in registry.get("manufacturers", {}).items():
        country = record.get("country") or ""
        if not country:
            continue
        for location in location_names:
            if _location_matches_country(location, country):
                additions.append(
                    LinkedEntity(
                        canonical_id=f"MFR:{name}",
                        canonical_name=name,
                        entity_type=EntityType.MANUFACTURER,
                        match_score=0.58,
                        match_method="location_manufacturer_map",
                        extracted_text=location,
                        requires_review=True,
                    )
                )
                break
    return additions


def _expand_manufacturers_by_supplier(
    linked: list[LinkedEntity], registry: dict[str, Any]
) -> list[LinkedEntity]:
    """Join linked distributors to their catalog manufacturers (inventory join)."""
    supplier_codes = _linked_supplier_codes(linked)
    if not supplier_codes:
        return []

    additions: list[LinkedEntity] = []
    suppliers = registry.get("suppliers", {})
    for code in supplier_codes:
        record = suppliers.get(code, {})
        for name in record.get("linked_manufacturers") or []:
            if not name:
                continue
            additions.append(
                LinkedEntity(
                    canonical_id=f"MFR:{name}",
                    canonical_name=name,
                    entity_type=EntityType.MANUFACTURER,
                    match_score=0.62,
                    match_method="supplier_manufacturer_map",
                    extracted_text=code,
                    requires_review=True,
                )
            )
    return additions


def _expand_components_by_catalog(
    linked: list[LinkedEntity], registry: dict[str, Any]
) -> list[LinkedEntity]:
    """
    Infer affected parts from linked distributors and manufacturers via catalog joins.

    Parts are sourced from inventory rows tied to each distributor, plus each
    manufacturer's catalog MPN list. No literal MPN mention in the article is required.
    """
    max_components = max(1, settings.catalog_inference_max_components)
    supplier_codes = _linked_supplier_codes(linked)
    manufacturer_names = _linked_manufacturer_names(linked)
    if not supplier_codes and not manufacturer_names:
        return []

    mpns: dict[str, tuple[str, str, float]] = {}
    suppliers = registry.get("suppliers", {})
    manufacturers = registry.get("manufacturers", {})

    for code in sorted(supplier_codes):
        for mpn in suppliers.get(code, {}).get("linked_mpns") or []:
            if mpn and mpn not in mpns:
                mpns[mpn] = (code, "supplier_inventory_map", 0.62)

    for name in sorted(manufacturer_names):
        for mpn in manufacturers.get(name, {}).get("mpns") or []:
            if mpn and mpn not in mpns:
                mpns[mpn] = (name, "manufacturer_catalog_map", 0.60)

    additions: list[LinkedEntity] = []
    for mpn in sorted(mpns.keys())[:max_components]:
        source, method, score = mpns[mpn]
        additions.append(
            LinkedEntity(
                canonical_id=f"MPN:{mpn}",
                canonical_name=mpn,
                entity_type=EntityType.COMPONENT,
                match_score=score,
                match_method=method,
                extracted_text=str(source),
                requires_review=True,
            )
        )
    return additions


# ── Entity extraction ─────────────────────────────────────────────────────────

def extract_known_entities(text: str, article_id: str | None = None) -> list[ExtractedEntity]:
    """
    Extract entities by matching known registry names, aliases, supplier codes,
    regions, and location keywords against the article text.

    Data comes from the DB-backed registry cache.
    """
    registry = _load_registry()
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, EntityType]] = set()

    # Build candidate list: (surface_form, entity_type, canonical_name)
    candidates: list[tuple[str, EntityType, str]] = []

    # Manufacturers + aliases
    for name, record in registry.get("manufacturers", {}).items():
        candidates.append((name, EntityType.MANUFACTURER, name))
        for alias in record.get("aliases", []):
            candidates.append((alias, EntityType.MANUFACTURER, name))

    # Supplier codes (e.g. "SUP002")
    for supplier_code in registry.get("suppliers", {}):
        candidates.append((supplier_code, EntityType.SUPPLIER, supplier_code))

    # Regions from registry
    for region in registry.get("regions", _REGIONS):
        candidates.append((region, EntityType.LOCATION, region))

    # Countries actually present in the DB (supplier/manufacturer country columns)
    for country_lower, country_display in _get_known_countries().items():
        candidates.append((country_display, EntityType.LOCATION, country_display))

    # Strategic supply-chain locations (ports, straits, manufacturing hubs)
    for location in sorted(STRATEGIC_LOCATIONS, key=len, reverse=True):
        candidates.append((location, EntityType.LOCATION, location))

    # Longest-first so more specific matches win
    candidates.sort(key=lambda item: len(item[0]), reverse=True)

    for surface, entity_type, canonical in candidates:
        if len(surface) < 3:
            continue
        start, end = _find_spans(text, surface)
        if start is None:
            continue
        key = (canonical.lower(), entity_type)
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            ExtractedEntity(
                text=text[start:end],
                entity_type=entity_type,
                start_char=start,
                end_char=end,
                confidence=0.85,
                source_article_id=article_id,
            )
        )

    return entities


# ── Fallback fuzzy linker ─────────────────────────────────────────────────────

def _link_entities_fallback(
    extracted: list[ExtractedEntity],
    text: str,
    provider_metadata: dict[str, Any] | None = None,
) -> list[LinkedEntity]:
    """
    Fallback entity linking using RapidFuzz + exact matching.
    Used when no OpenRouter API key is set, or when the LLM call fails.
    """
    registry = _load_registry()
    linked: list[LinkedEntity] = []
    metadata = provider_metadata or {}

    for entity in extracted:
        if entity.entity_type == EntityType.MANUFACTURER:
            best_name: str | None = None
            best_score = 0.0
            for name in registry.get("manufacturers", {}):
                score = fuzz.partial_ratio(entity.text.lower(), name.lower()) / 100.0
                if score > best_score:
                    best_score = score
                    best_name = name

            if best_name and best_score >= 0.75:
                linked.append(
                    LinkedEntity(
                        canonical_id=f"MFR:{best_name}",
                        canonical_name=best_name,
                        entity_type=EntityType.MANUFACTURER,
                        match_score=best_score,
                        match_method="fuzzy_manufacturer",
                        extracted_text=entity.text,
                        requires_review=best_score < settings.entity_link_confidence_threshold,
                    )
                )
                # Also link through to suppliers
                supplier_ids = registry["manufacturers"][best_name].get("supplier_ids", [])
                for supplier_id in supplier_ids[:3]:
                    linked.append(
                        LinkedEntity(
                            canonical_id=str(supplier_id),
                            canonical_name=str(supplier_id),
                            entity_type=EntityType.SUPPLIER,
                            match_score=min(best_score, 0.9),
                            match_method="manufacturer_supplier_map",
                            extracted_text=entity.text,
                        )
                    )

        elif entity.entity_type == EntityType.SUPPLIER:
            supplier_code = entity.text.upper()
            if supplier_code in registry.get("suppliers", {}):
                linked.append(
                    LinkedEntity(
                        canonical_id=supplier_code,
                        canonical_name=supplier_code,
                        entity_type=EntityType.SUPPLIER,
                        match_score=1.0,
                        match_method="exact_supplier_code",
                        extracted_text=entity.text,
                    )
                )

        elif entity.entity_type == EntityType.LOCATION:
            linked.append(
                LinkedEntity(
                    canonical_id=f"LOC:{entity.text.lower()}",
                    canonical_name=entity.text,
                    entity_type=EntityType.LOCATION,
                    match_score=0.8,
                    match_method="keyword_location",
                    extracted_text=entity.text,
                )
            )

    # MPN exact match against components from DB
    components = registry.get("components", {})
    for match in re.finditer(r"\b[A-Z0-9]{3,}[A-Z0-9\-/_]{2,}\b", text.upper()):
        mpn = match.group(0)
        if mpn in components:
            linked.append(
                LinkedEntity(
                    canonical_id=f"MPN:{mpn}",
                    canonical_name=mpn,
                    entity_type=EntityType.COMPONENT,
                    match_score=1.0,
                    match_method="exact_mpn",
                    extracted_text=mpn,
                )
            )

    return _finalize_linked_entities(linked, metadata, registry)


# ── LLM linker ────────────────────────────────────────────────────────────────

def link_entities(
    extracted: list[ExtractedEntity],
    text: str,
    provider_metadata: dict[str, Any] | None = None,
) -> list[LinkedEntity]:
    """
    Resolve extracted entities to canonical IDs.

    Primary path: LLM with compact registry candidates.
    Fallback: RapidFuzz fuzzy matching.
    On Groq (auto mode): fuzzy-first — LLM only when fuzzy linking misses mentions.
    """
    if not extracted:
        return _link_entities_fallback(extracted, text, provider_metadata)

    mode = settings.effective_llm_entity_linking_mode
    from services.llm_client import llm_configured

    if (
        not llm_configured()
        or not settings.llm_entity_linking_enabled
        or mode == "never"
    ):
        return _link_entities_fallback(extracted, text, provider_metadata)

    fuzzy_result: list[LinkedEntity] | None = None
    if mode == "fuzzy_first":
        fuzzy_result = _link_entities_fallback(extracted, text, provider_metadata)
        if _extracted_covered(extracted, fuzzy_result):
            return fuzzy_result

    try:
        registry = _load_registry()
        registry_summary = _get_compact_registry_summary(extracted, text, registry)
        article_text = _truncate_text(text, settings.llm_linking_max_article_chars)

        mentions = [
            {"text": ent.text, "entity_type": ent.entity_type.value}
            for ent in extracted
        ]
        mentions_json = json.dumps(mentions, indent=2)

        from services.llm_client import chat_completion_json

        parsed = chat_completion_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"ARTICLE TEXT:\n{article_text}\n\n"
                        f"EXTRACTED ENTITIES (MENTIONS):\n{mentions_json}\n\n"
                        f"{registry_summary}"
                    ),
                },
            ],
            max_tokens=1200,
            temperature=0.1,
            timeout=30.0,
        )
        matches = parsed.get("matches", [])

        linked: list[LinkedEntity] = []
        metadata = provider_metadata or {}

        for m in matches:
            canonical_id = m.get("canonical_id")
            canonical_name = m.get("canonical_name")
            entity_type_str = m.get("entity_type")
            match_score = m.get("match_score", 0.8)
            extracted_text = m.get("extracted_text")
            requires_review = m.get("requires_review", False)

            if not all([canonical_id, canonical_name, entity_type_str, extracted_text]):
                continue
            if canonical_id == "UNRESOLVED":
                continue

            try:
                entity_type = EntityType(entity_type_str)
            except ValueError:
                continue

            labels = expand_entity_labels(canonical_name) or [str(canonical_name).strip()]
            for label in labels:
                linked.append(
                    LinkedEntity(
                        canonical_id=canonical_id,
                        canonical_name=label,
                        entity_type=entity_type,
                        match_score=match_score,
                        match_method="llm_resolution",
                        extracted_text=extracted_text,
                        requires_review=requires_review
                        or (match_score < settings.entity_link_confidence_threshold),
                    )
                )

            # Expand manufacturer → its suppliers (from DB-backed registry)
            if entity_type == EntityType.MANUFACTURER:
                mfr_key = canonical_id[4:] if canonical_id.startswith("MFR:") else canonical_name
                mfr_record = registry.get("manufacturers", {}).get(mfr_key, {})
                for supplier_id in mfr_record.get("supplier_ids", [])[:3]:
                    linked.append(
                        LinkedEntity(
                            canonical_id=str(supplier_id),
                            canonical_name=str(supplier_id),
                            entity_type=EntityType.SUPPLIER,
                            match_score=min(match_score, 0.9),
                            match_method="manufacturer_supplier_map",
                            extracted_text=extracted_text,
                        )
                    )

        return _finalize_linked_entities(linked, metadata, registry)

    except Exception as exc:
        if "429" in str(exc) or "rate_limit" in str(exc).lower():
            logger.warning(
                "LLM entity linking rate limited — falling back to RapidFuzz: %s",
                exc,
            )
        else:
            logger.error("LLM entity linking failed: %s — falling back to RapidFuzz.", exc)
            logger.error(traceback.format_exc())
        if fuzzy_result is not None:
            return fuzzy_result
        return _link_entities_fallback(extracted, text, provider_metadata)


def _linked_entity_from_dict(item: dict[str, Any]) -> LinkedEntity | None:
    canonical_id = str(item.get("canonical_id") or item.get("id") or "").strip()
    if not canonical_id:
        return None
    entity_type = item.get("entity_type")
    if isinstance(entity_type, EntityType):
        parsed_type = entity_type
    else:
        try:
            parsed_type = EntityType(str(entity_type))
        except ValueError:
            return None
    return LinkedEntity(
        canonical_id=canonical_id,
        canonical_name=str(item.get("canonical_name") or canonical_id),
        entity_type=parsed_type,
        match_score=float(item.get("match_score") or 0.0),
        match_method=str(item.get("match_method") or "persisted"),
        extracted_text=str(item.get("extracted_text") or ""),
        requires_review=bool(item.get("requires_review", False)),
    )


def linked_entity_from_dict(item: dict[str, Any]) -> LinkedEntity | None:
    """Public wrapper for parsing persisted linked entity dicts."""
    return _linked_entity_from_dict(item)


def _linked_groups_from_entities(entities: list[LinkedEntity]) -> dict[str, list[dict[str, Any]]]:
    groups = {
        "linked_manufacturers": [],
        "linked_suppliers": [],
        "linked_locations": [],
        "linked_components": [],
    }
    key_by_type = {
        EntityType.MANUFACTURER: "linked_manufacturers",
        EntityType.SUPPLIER: "linked_suppliers",
        EntityType.LOCATION: "linked_locations",
        EntityType.COMPONENT: "linked_components",
    }
    for entity in entities:
        key = key_by_type.get(entity.entity_type)
        if key:
            groups[key].append(entity.model_dump(mode="json"))
    return groups


def enrich_linked_entities_with_catalog(linked: dict[str, Any] | None) -> dict[str, Any]:
    """
    Re-run catalog join inference on persisted linked entities (SiaEye read path).

    Ensures location → distributor → manufacturer → part links appear even for
    rows ingested before inference existed or when the ingest registry was broken.
    """
    payload = dict(linked or {})
    entities: list[LinkedEntity] = []
    for key in (
        "linked_manufacturers",
        "linked_suppliers",
        "linked_locations",
        "linked_components",
    ):
        for item in payload.get(key) or []:
            if isinstance(item, LinkedEntity):
                entities.append(item)
            elif isinstance(item, dict):
                parsed = _linked_entity_from_dict(item)
                if parsed is not None:
                    entities.append(parsed)

    if not entities:
        return payload

    registry = _load_registry()
    expanded = _finalize_linked_entities(entities, None, registry)
    groups = _linked_groups_from_entities(expanded)
    payload.update(groups)
    return payload