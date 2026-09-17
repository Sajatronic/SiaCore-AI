"""Rule-based relevance, classification, and severity helpers."""

from __future__ import annotations

import re
from typing import Any

from config.strategic_locations import STRATEGIC_LOCATIONS
from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    EventCategory,
    SeveritySignal,
)
from nodes.prefilter import score_article_relevance

NON_DISRUPTION_GDELT_CATEGORIES = {
    "CORPORATE",
    "CO04",
    "TECHNOLOGY DEVELOPMENT MILESTONE",
}

DISRUPTION_SIGNAL_KEYWORDS = {
    "shutdown", "closure", "strike", "disruption", "shortage", "sanction",
    "embargo", "fire", "outage", "bankruptcy", "delay", "blockade", "attack",
    "flood", "earthquake", "hurricane", "typhoon", "cyclone", "war", "conflict",
    "halt", "halted", "paused", "pause production", "production halt",
}

CLASSIFICATION_RULES: list[tuple[EventCategory, str, list[str], float]] = [
    (EventCategory.NATURAL_DISASTER, "earthquake", ["earthquake", "seismic", "magnitude"], 0.88),
    (EventCategory.NATURAL_DISASTER, "flood", ["flood", "flooding", "inundation"], 0.86),
    (EventCategory.NATURAL_DISASTER, "tropical_cyclone", ["cyclone", "hurricane", "typhoon"], 0.86),
    (EventCategory.FACTORY_SHUTDOWN, "plant_fire", ["factory fire", "plant fire", "fab fire"], 0.84),
    (EventCategory.FACTORY_SHUTDOWN, "power_outage", ["power outage", "blackout", "grid failure"], 0.82),
    (EventCategory.FACTORY_SHUTDOWN, "announced_closure", ["shutdown", "halt production", "suspend operations"], 0.8),
    (EventCategory.EXPORT_SANCTION, "export_control", ["export control", "export ban", "trade restriction"], 0.85),
    (EventCategory.EXPORT_SANCTION, "embargo", ["embargo", "sanction", "tariff"], 0.83),
    (EventCategory.LABOR_ACTION, "strike", ["strike", "walkout", "labor dispute"], 0.82),
    (EventCategory.LABOR_ACTION, "protest", ["protest", "demonstration"], 0.75),
    (EventCategory.LOGISTICS_DISRUPTION, "port_closure", ["port closure", "port shutdown", "canal"], 0.84),
    (EventCategory.LOGISTICS_DISRUPTION, "shipping_lane_disruption", [
        "strait of hormuz", "suez canal", "red sea", "shipping lane", "chokepoint",
    ], 0.86),
    (EventCategory.LOGISTICS_DISRUPTION, "route_blockage", ["route blockage", "shipping delay", "cargo"], 0.78),
    (EventCategory.FINANCIAL_DISTRESS, "bankruptcy", ["bankruptcy", "insolvency", "chapter 11"], 0.86),
    (EventCategory.FINANCIAL_DISTRESS, "credit_downgrade", ["credit downgrade", "liquidity crisis", "default"], 0.84),
    (EventCategory.GEOPOLITICAL_EVENT, "armed_conflict", ["armed conflict", "military escalation", "invasion", "war"], 0.86),
    (EventCategory.GEOPOLITICAL_EVENT, "regional_crisis", ["regional crisis", "political instability", "civil unrest"], 0.82),
    (EventCategory.CYBER_INCIDENT, "ransomware", ["ransomware", "cyberattack", "cyber attack", "data breach"], 0.84),
    (EventCategory.ENERGY_DISRUPTION, "grid_failure", ["grid failure", "rolling blackout", "fuel shortage"], 0.82),
    (EventCategory.REGULATORY_CHANGE, "export_license", ["export license", "compliance requirement", "import restriction"], 0.78),
    (EventCategory.PUBLIC_HEALTH_EVENT, "quarantine", ["quarantine", "pandemic", "epidemic", "lockdown"], 0.80),
    (EventCategory.MARKET_DISRUPTION, "semiconductor_shortage", ["semiconductor shortage", "raw material shortage", "commodity price shock"], 0.82),
]

GDACS_EVENT_MAP = {
    "EQ": (EventCategory.NATURAL_DISASTER, "earthquake", 0.92),
    "FL": (EventCategory.NATURAL_DISASTER, "flood", 0.92),
    "TC": (EventCategory.NATURAL_DISASTER, "tropical_cyclone", 0.92),
    "VO": (EventCategory.NATURAL_DISASTER, "other_natural_disaster", 0.85),
    "DR": (EventCategory.NATURAL_DISASTER, "other_natural_disaster", 0.85),
    "WF": (EventCategory.NATURAL_DISASTER, "wildfire", 0.88),
}

ALERT_LEVEL_SCORES = {"green": 35.0, "orange": 65.0, "red": 85.0}

# ============================================================================
# Strategic location importance for logistics disruptions
# ============================================================================
# Imported from config.strategic_locations (STRATEGIC_LOCATIONS)

# ============================================================================
# NEW: Disruption intensity keywords for better severity assessment
# ============================================================================
DISRUPTION_INTENSITY = {
    "critical": 0.90,
    "major": 0.85,
    "indefinite": 0.85,
    "nationwide": 0.80,
    "widespread": 0.80,
    "complete": 0.80,
    "partial": 0.50,
    "minor": 0.40,
}


def article_text(item: EnrichedArticle) -> str:
    return f"{item.article.title} {item.article.body}".strip()


def extract_geo_from_article(item: EnrichedArticle) -> dict[str, float | str | None]:
    """Extract coordinates and geography from provider metadata when available."""
    metadata = item.article.provider_metadata or {}
    raw = metadata.get("raw") if isinstance(metadata.get("raw"), dict) else metadata
    geo = raw.get("geo") if isinstance(raw, dict) else None
    if not isinstance(geo, dict):
        geo = {}

    latitude = geo.get("latitude")
    longitude = geo.get("longitude")
    country = geo.get("country") or metadata.get("country")
    region = geo.get("region")

    try:
        lat = float(latitude) if latitude is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        lon = float(longitude) if longitude is not None else None
    except (TypeError, ValueError):
        lon = None

    from services.display_format import format_geo_label

    return {
        "latitude": lat,
        "longitude": lon,
        "geo_country": format_geo_label(country),
        "geo_region": format_geo_label(region),
    }


def is_actionable_disruption(item: EnrichedArticle) -> bool:
    """
    Return False for clearly non-disruptive articles (e.g. corporate milestones).

    Filters positive corporate news that lacks disruption signals.
    """
    metadata = item.article.provider_metadata or {}
    raw = metadata.get("raw") if isinstance(metadata.get("raw"), dict) else metadata
    text = article_text(item).lower()

    if any(kw in text for kw in DISRUPTION_SIGNAL_KEYWORDS):
        return True

    classification = item.classification
    if classification and classification.event_category != EventCategory.OTHER:
        if classification.confidence >= 0.6:
            return True

    if item.article.provider == "gdacs":
        return True

    if isinstance(raw, dict):
        category = str(raw.get("category") or raw.get("domain") or "").upper()
        event_code = str(raw.get("event_code") or "").upper()
        subcategory = str(raw.get("subcategory") or "").upper()

        if category in NON_DISRUPTION_GDELT_CATEGORIES or event_code.startswith("CO"):
            if not any(kw in text for kw in DISRUPTION_SIGNAL_KEYWORDS):
                return False

        if "MILESTONE" in subcategory or "DEVELOPMENT" in subcategory:
            if not any(kw in text for kw in DISRUPTION_SIGNAL_KEYWORDS):
                return False

        metrics = raw.get("metrics") or {}
        significance = metrics.get("significance")
        if significance is not None:
            try:
                if float(significance) < 0.4 and classification and classification.event_category == EventCategory.OTHER:
                    return False
            except (TypeError, ValueError):
                pass

    severity = item.severity.severity_score if item.severity else 0.0
    if severity >= 55.0:
        return True

    if item.linked_entities and classification and classification.event_category != EventCategory.OTHER:
        return True

    return False


def score_relevance(text: str, provider: str) -> float:
    """Backward-compatible relevance score for classification fallback."""
    from models.schemas import RawArticle

    score, _, _ = score_article_relevance(
        RawArticle(provider=provider, title=text, body="")
    )
    return score


# ============================================================================
# NEW HELPER: Check for multiple keyword signals in text
# ============================================================================
def _has_multiple_signals(text: str, keywords: list[str]) -> bool:
    """Check if text contains multiple keyword signals from the list.
    
    IMPROVEMENT: Stronger evidence when multiple keywords present.
    """
    count = sum(1 for kw in keywords if kw in text)
    return count >= 2


# ============================================================================
# NEW HELPER: Calculate entity presence boost
# ============================================================================
def _calculate_entity_boost(item: EnrichedArticle) -> float:
    """Boost classification confidence based on entity presence.
    
    IMPROVEMENT: More linked entities = more confidence that event is real.
    Returns confidence multiplier (0.0 to 0.15 boost).
    """
    boost = 0.0
    
    # Presence of linked entities increases confidence
    if item.linked_entities:
        entity_count = len(item.linked_entities)
        # 1-2 entities: +0.05, 3-5 entities: +0.10, 6+ entities: +0.15
        if entity_count >= 6:
            boost += 0.15
        elif entity_count >= 3:
            boost += 0.10
        else:
            boost += 0.05
    
    # Presence of extracted entities (before linking)
    if item.extracted_entities:
        if len(item.extracted_entities) >= 3:
            boost += 0.05
    
    return min(boost, 0.15)  # Cap at +0.15


# ============================================================================
# NEW HELPER: Check for recency/urgency language
# ============================================================================
def _has_urgency_language(text: str) -> bool:
    """Check if text contains urgent/current event language."""
    urgency_keywords = {
        "today", "now", "just", "breaking", "emergency", "alert",
        "reports", "confirmed", "announced", "revealed", "found",
        "happening", "ongoing", "in progress"
    }
    return any(kw in text for kw in urgency_keywords)


def classify_article(item: EnrichedArticle) -> ClassificationResult:
    """Classify article with improved context-aware scoring.
    
    IMPROVEMENTS:
    - Entity presence boosting
    - Multi-signal validation
    - Better rationale tracking
    - Context-aware confidence adjustment
    """
    metadata = item.article.provider_metadata or {}
    provider = item.article.provider

    # ========================================================================
    # GDACS: Structured data always has highest confidence
    # ========================================================================
    if provider == "gdacs":
        event_code = str(metadata.get("event_type", "")).upper()
        if event_code in GDACS_EVENT_MAP:
            category, event_type, confidence = GDACS_EVENT_MAP[event_code]
            return ClassificationResult(
                event_type=event_type,
                event_category=category,
                confidence=confidence,
                rationale=f"gdacs_event_type:{event_code}",
            )

    text = article_text(item).lower()
    best: ClassificationResult | None = None

    # ========================================================================
    # IMPROVED: Rule-based classification with entity boost
    # ========================================================================
    for category, event_type, keywords, confidence in CLASSIFICATION_RULES:
        if any(keyword in text for keyword in keywords):
            # IMPROVEMENT: Boost confidence if multiple keyword signals present
            if _has_multiple_signals(text, keywords):
                confidence = min(confidence + 0.05, 1.0)
            
            candidate = ClassificationResult(
                event_type=event_type,
                event_category=category,
                confidence=confidence,
                rationale=f"keyword_match:{keywords[0]}",
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate

    # ========================================================================
    # IMPROVED: Provider-specific signals with entity consideration
    # ========================================================================
    if provider == "marketaux":
        sentiment = metadata.get("sentiment")
        if sentiment is not None and float(sentiment) <= -0.2:
            # IMPROVEMENT: Boost if linked to companies (manufacturers/suppliers)
            sentiment_confidence = 0.72
            if item.linked_entities:
                sentiment_confidence = min(sentiment_confidence + 0.08, 0.90)
            
            candidate = ClassificationResult(
                event_type="credit_downgrade",
                event_category=EventCategory.FINANCIAL_DISTRESS,
                confidence=sentiment_confidence,
                rationale="marketaux_negative_sentiment",
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate

    # ========================================================================
    # IMPROVEMENT: If a match was found, boost with entity presence
    # ========================================================================
    if best is not None:
        entity_boost = _calculate_entity_boost(item)
        if entity_boost > 0:
            best.confidence = min(best.confidence + entity_boost, 1.0)
            best.rationale = f"{best.rationale}+entity_boost"
        return best

    # ========================================================================
    # IMPROVEMENT: Better fallback classification
    # Use entity presence + relevance for better heuristic
    # ========================================================================
    relevance_score = score_relevance(text, provider)
    
    # IMPROVEMENT: Entity presence indicates real supply-chain event
    entity_count = len(item.linked_entities) + len(item.extracted_entities)
    
    if relevance_score >= 0.5 or entity_count >= 2:
        fallback_confidence = 0.45
        # Boost fallback confidence if entities present
        if entity_count >= 3:
            fallback_confidence = 0.55
        elif entity_count >= 1:
            fallback_confidence = 0.50
        
        return ClassificationResult(
            event_type="unclassified",
            event_category=EventCategory.OTHER,
            confidence=fallback_confidence,
            rationale=f"supply_chain_relevant_but_unmatched(entities:{entity_count})",
        )

    return ClassificationResult(
        event_type="unclassified",
        event_category=EventCategory.OTHER,
        confidence=0.25,
        rationale="low_relevance_no_rule_match",
    )


def estimate_severity(item: EnrichedArticle, classification: ClassificationResult) -> SeveritySignal:
    """Estimate severity using the hybrid severity engine."""
    from services.severity_engine import estimate_severity_hybrid

    return estimate_severity_hybrid(item, classification)