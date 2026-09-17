"""Hybrid severity engine — rule-based base plus supply-chain context factors."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from config.settings import settings
from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    EntityType,
    EventCategory,
    LinkedEntity,
    SeveritySignal,
    SourceRecord,
)
from config.strategic_locations import STRATEGIC_LOCATIONS
from nodes.processing import (
    ALERT_LEVEL_SCORES,
    DISRUPTION_INTENSITY,
    _has_urgency_language,
    article_text,
    extract_geo_from_article,
)

# Factor weights for hybrid scoring (must sum to 1.0)
_HYBRID_WEIGHTS: dict[str, float] = {
    "base_rule_score": 0.40,
    "supplier_criticality": 0.15,
    "source_reliability": 0.10,
    "entity_impact": 0.10,
    "geographic_importance": 0.10,
    "market_sensitivity": 0.10,
    "multi_source_confirmation": 0.05,
}


@lru_cache(maxsize=1)
def _load_source_reliability() -> dict[str, float]:
    path = settings.project_root / "config" / "source_reliability.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    weights: dict[str, float] = {}
    for tier in config.get("tiers", {}).values():
        weight = float(tier.get("default_weight", 0.65))
        for provider in tier.get("providers", []):
            weights[provider.lower()] = weight
    return weights


@lru_cache(maxsize=1)
def _supplier_risk_lookup() -> dict[str, dict[str, Any]]:
    from canonical.entity_registry import build_canonical_entities

    registry = build_canonical_entities()
    lookup: dict[str, dict[str, Any]] = {}
    for code, record in registry.get("suppliers", {}).items():
        score = record.get("relationship_risk_score")
        try:
            numeric = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            numeric = 0.0
        lookup[code] = {
            "relationship_risk_score": numeric,
            "relationship_risk_level": record.get("relationship_risk_level"),
        }
    return lookup


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _rule_based_base(item: EnrichedArticle, classification: ClassificationResult) -> tuple[float, dict[str, Any], str]:
    """Original rule-based severity (Phase 0/1 logic)."""
    import re

    metadata = item.article.provider_metadata or {}
    text = article_text(item).lower()
    raw_signal: dict[str, Any] = {}
    score = 30.0
    method = "rule_based"

    if item.article.provider == "gdacs":
        alert_level = str(metadata.get("alert_level", "")).lower()
        raw_signal["alert_level"] = alert_level
        score = ALERT_LEVEL_SCORES.get(alert_level, score)
        severity_data = metadata.get("severity_data") or {}
        magnitude = severity_data.get("severity")
        if magnitude is not None:
            raw_signal["magnitude"] = magnitude
            try:
                score = max(score, min(100.0, float(magnitude) * 12))
            except (TypeError, ValueError):
                pass
        method = "gdacs_alert_and_magnitude"

    elif classification.event_category == EventCategory.FINANCIAL_DISTRESS:
        sentiment = metadata.get("sentiment")
        if sentiment is not None:
            raw_signal["sentiment"] = sentiment
            score = min(100.0, 40.0 + abs(float(sentiment)) * 60.0)
        elif any(word in text for word in ("bankruptcy", "default", "crisis")):
            score = 75.0
        if item.linked_entities and len(item.linked_entities) >= 2:
            score = min(score + 10.0, 100.0)
            raw_signal["has_linked_entities"] = True
        method = "financial_keyword_or_sentiment"

    elif classification.event_category == EventCategory.NATURAL_DISASTER:
        magnitude_match = re.search(r"magnitude\s*([0-9.]+)", text)
        if magnitude_match:
            magnitude = float(magnitude_match.group(1))
            raw_signal["magnitude"] = magnitude
            score = min(100.0, magnitude * 12)
        location_boost = 0.0
        for location, importance in STRATEGIC_LOCATIONS.items():
            if location in text:
                location_boost = max(location_boost, importance)
        if location_boost > 0:
            score = min(score + (location_boost * 15), 100.0)
            raw_signal["critical_location"] = location_boost
        method = "natural_disaster_magnitude"

    elif classification.event_category in {
        EventCategory.FACTORY_SHUTDOWN,
        EventCategory.LOGISTICS_DISRUPTION,
        EventCategory.LABOR_ACTION,
    }:
        score = 55.0
        intensity_boost = 0.0
        for keyword, intensity in DISRUPTION_INTENSITY.items():
            if keyword in text:
                intensity_boost = max(intensity_boost, intensity)
        if intensity_boost > 0:
            score = 55.0 + (intensity_boost * 30)
            raw_signal["disruption_intensity"] = intensity_boost
        elif any(word in text for word in ("major", "indefinite", "nationwide", "critical")):
            score = 70.0
        if classification.event_category == EventCategory.LOGISTICS_DISRUPTION:
            location_boost = 0.0
            for location, importance in STRATEGIC_LOCATIONS.items():
                if location in text:
                    location_boost = max(location_boost, importance)
            if location_boost > 0:
                score = min(score + (location_boost * 20), 100.0)
                raw_signal["strategic_location"] = location_boost
        entity_count = len(item.linked_entities)
        if entity_count >= 5:
            score = min(score + 15.0, 100.0)
            raw_signal["many_entities_affected"] = entity_count
        elif entity_count >= 2:
            score = min(score + 8.0, 100.0)
            raw_signal["entities_affected"] = entity_count
        if _has_urgency_language(text):
            score = min(score + 5.0, 100.0)
            raw_signal["urgent_language"] = True
        method = "disruption_context_and_location"

    elif classification.event_category == EventCategory.EXPORT_SANCTION:
        score = 60.0
        if any(word in text for word in ("ban", "embargo", "restrict", "comprehensive")):
            score = 72.0
        if any(word in text for word in ("comprehensive", "all", "entire", "full")):
            score = min(score + 10.0, 100.0)
            raw_signal["comprehensive_scope"] = True
        if item.linked_entities and len(item.linked_entities) >= 3:
            score = min(score + 10.0, 100.0)
            raw_signal["multiple_entities_affected"] = True
        method = "sanction_keyword_and_scope"

    return round(score, 1), raw_signal, method


def _supplier_criticality_score(linked_entities: list[LinkedEntity]) -> tuple[float, dict[str, Any]]:
    lookup = _supplier_risk_lookup()
    supplier_scores: list[float] = []
    suppliers_found: list[str] = []

    for entity in linked_entities:
        if entity.entity_type != EntityType.SUPPLIER:
            continue
        record = lookup.get(entity.canonical_id, {})
        risk = record.get("relationship_risk_score", 0.0)
        if risk > 0:
            supplier_scores.append(float(risk) * 100.0)
            suppliers_found.append(entity.canonical_id)

    if not supplier_scores:
        return 0.0, {"linked_suppliers": 0}

    return max(supplier_scores), {
        "max_supplier_risk_score": max(supplier_scores),
        "affected_suppliers": suppliers_found[:5],
    }


def _source_reliability_score(provider: str, reliability_tier: int) -> tuple[float, dict[str, Any]]:
    weights = _load_source_reliability()
    weight = weights.get(provider.lower())
    if weight is None:
        tier_defaults = {1: 1.0, 2: 0.85, 3: 0.65}
        weight = tier_defaults.get(reliability_tier, 0.5)
    return weight * 100.0, {"provider": provider, "reliability_tier": reliability_tier, "weight": weight}


def _entity_impact_score(linked_entities: list[LinkedEntity]) -> tuple[float, dict[str, Any]]:
    count = len(linked_entities)
    if count == 0:
        return 10.0, {"linked_entity_count": 0}
    if count >= 6:
        return 90.0, {"linked_entity_count": count}
    if count >= 3:
        return 65.0, {"linked_entity_count": count}
    return 40.0, {"linked_entity_count": count}


def _geographic_importance_score(item: EnrichedArticle) -> tuple[float, dict[str, Any]]:
    text = article_text(item).lower()
    geo = extract_geo_from_article(item)
    boost = 0.0
    for location, importance in STRATEGIC_LOCATIONS.items():
        if location in text:
            boost = max(boost, importance)
    if geo.get("geo_country"):
        boost = max(boost, 0.55)
    return boost * 100.0, {"strategic_location_score": boost, "geo_country": geo.get("geo_country")}


def _market_sensitivity_score(item: EnrichedArticle, classification: ClassificationResult) -> tuple[float, dict[str, Any]]:
    metadata = item.article.provider_metadata or {}
    raw = metadata.get("raw") if isinstance(metadata.get("raw"), dict) else metadata
    metrics = raw.get("metrics") if isinstance(raw, dict) else {}
    if isinstance(metrics, dict):
        for key in ("market_sensitivity", "systemic_importance", "propagation_potential"):
            value = metrics.get(key)
            if value is not None:
                try:
                    score = float(value) * 100.0
                    return score, {key: float(value)}
                except (TypeError, ValueError):
                    pass

    category_defaults = {
        EventCategory.EXPORT_SANCTION: 75.0,
        EventCategory.LOGISTICS_DISRUPTION: 70.0,
        EventCategory.FACTORY_SHUTDOWN: 65.0,
        EventCategory.NATURAL_DISASTER: 60.0,
        EventCategory.GEOPOLITICAL_EVENT: 70.0,
        EventCategory.MARKET_DISRUPTION: 80.0,
    }
    default = category_defaults.get(classification.event_category, 35.0)
    return default, {"event_category_default": classification.event_category.value}


def _multi_source_score(source_count: int, verification_score: float) -> tuple[float, dict[str, Any]]:
    if source_count <= 1:
        return verification_score * 50.0, {"source_count": source_count}
    return _clamp(50.0 + verification_score * 50.0 + (source_count - 1) * 10.0), {
        "source_count": source_count,
        "verification_score": verification_score,
    }


def _build_hybrid_factors(
    *,
    base_score: float,
    supplier_score: float,
    source_score: float,
    entity_score: float,
    geo_score: float,
    market_score: float,
    multi_source_score: float,
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    components = {
        "base_rule_score": (base_score, evidence.get("base", {})),
        "supplier_criticality": (supplier_score, evidence.get("supplier", {})),
        "source_reliability": (source_score, evidence.get("source", {})),
        "entity_impact": (entity_score, evidence.get("entity", {})),
        "geographic_importance": (geo_score, evidence.get("geo", {})),
        "market_sensitivity": (market_score, evidence.get("market", {})),
        "multi_source_confirmation": (multi_source_score, evidence.get("multi_source", {})),
    }

    factors: list[dict[str, Any]] = []
    for name, (score, meta) in components.items():
        weight = _HYBRID_WEIGHTS[name]
        contribution = round(score * weight, 2)
        factors.append(
            {
                "factor": name,
                "score": round(score, 1),
                "weight": weight,
                "contribution": contribution,
                "evidence": meta,
            }
        )
    return factors


def _combine_factors(factors: list[dict[str, Any]]) -> float:
    total = sum(f["contribution"] for f in factors)
    return round(_clamp(total), 1)


def estimate_severity_hybrid(
    item: EnrichedArticle,
    classification: ClassificationResult,
    *,
    linked_entities: list[LinkedEntity] | None = None,
    source_count: int = 1,
    verification_score: float = 0.0,
) -> SeveritySignal:
    """Compute hybrid severity for a single article or cluster context."""
    linked = linked_entities if linked_entities is not None else item.linked_entities

    base_score, base_raw, base_method = _rule_based_base(item, classification)
    supplier_score, supplier_meta = _supplier_criticality_score(linked)
    source_score, source_meta = _source_reliability_score(
        item.article.provider, item.article.reliability_tier
    )
    entity_score, entity_meta = _entity_impact_score(linked)
    geo_score, geo_meta = _geographic_importance_score(item)
    market_score, market_meta = _market_sensitivity_score(item, classification)
    multi_score, multi_meta = _multi_source_score(source_count, verification_score)

    factors = _build_hybrid_factors(
        base_score=base_score,
        supplier_score=supplier_score,
        source_score=source_score,
        entity_score=entity_score,
        geo_score=geo_score,
        market_score=market_score,
        multi_source_score=multi_score,
        evidence={
            "base": {"method": base_method, **base_raw},
            "supplier": supplier_meta,
            "source": source_meta,
            "entity": entity_meta,
            "geo": geo_meta,
            "market": market_meta,
            "multi_source": multi_meta,
        },
    )
    final_score = _combine_factors(factors)

    raw_signal = {
        **base_raw,
        "base_rule_score": base_score,
        "hybrid_factors": factors,
        "hybrid_final_score": final_score,
        "severity_summary": _severity_summary(factors, final_score),
    }

    return SeveritySignal(
        raw_signal=raw_signal,
        severity_score=final_score,
        scoring_method="hybrid",
    )


def enhance_cluster_severity(
    primary: EnrichedArticle,
    classification: ClassificationResult,
    linked_entities: list[LinkedEntity],
    sources: list[SourceRecord],
    verification_score: float,
) -> SeveritySignal:
    """Re-score severity using full cluster context (multi-source + merged entities)."""
    return estimate_severity_hybrid(
        primary,
        classification,
        linked_entities=linked_entities,
        source_count=len(sources),
        verification_score=verification_score,
    )


def _severity_summary(factors: list[dict[str, Any]], final_score: float) -> str:
    top = sorted(factors, key=lambda f: f["contribution"], reverse=True)[:3]
    parts = [f"{f['factor']} ({f['contribution']:.1f})" for f in top]
    return f"Severity {final_score}/100 driven by: {', '.join(parts)}"


def invalidate_severity_caches() -> None:
    """Clear cached lookups (for tests)."""
    _load_source_reliability.cache_clear()
    _supplier_risk_lookup.cache_clear()
