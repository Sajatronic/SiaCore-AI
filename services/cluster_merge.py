"""Merge clustered articles into canonical risk events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    EntityType,
    EventCategory,
    EventLifecycleStatus,
    LinkedEntity,
    ProcessingStageAudit,
    ProvenanceInformation,
    RiskEvent,
    SeveritySignal,
    SourceRecord,
)
from nodes.processing import extract_geo_from_article, is_actionable_disruption
from config.settings import settings
from services.confidence_engine import calibrate_confidence
from services.event_dedup import assign_stable_identity
from services.severity_engine import enhance_cluster_severity


def _entity_link_confidence(linked_entities: list[LinkedEntity]) -> float:
    if not linked_entities:
        return 0.0
    return max(entity.match_score for entity in linked_entities)


def _extraction_confidence(extracted_entities: list) -> float:
    if not extracted_entities:
        return 0.0
    return sum(entity.confidence for entity in extracted_entities) / len(extracted_entities)


def _dedupe_linked(entities: list[LinkedEntity]) -> list[LinkedEntity]:
    best: dict[tuple[str, EntityType], LinkedEntity] = {}
    for item in entities:
        key = (item.canonical_id, item.entity_type)
        existing = best.get(key)
        if existing is None or item.match_score > existing.match_score:
            best[key] = item
    return list(best.values())


def _compute_verification_score(sources: list[SourceRecord]) -> float:
    """Score multi-source confirmation using count and reliability tiers."""
    if not sources:
        return 0.0
    unique_providers = {s.provider for s in sources}
    tier_weights = {1: 1.0, 2: 0.85, 3: 0.65}
    tier_sum = sum(tier_weights.get(s.reliability_tier, 0.5) for s in sources)
    count_factor = min(1.0, 0.35 + 0.25 * len(unique_providers))
    tier_factor = min(1.0, tier_sum / max(len(sources), 1))
    return round(min(1.0, count_factor * tier_factor), 3)


def _review_reasons_for_item(
    item: EnrichedArticle,
    classification: ClassificationResult,
    severity: SeveritySignal,
    entity_link_confidence: float,
) -> list[str]:
    reasons: list[str] = []

    if classification.confidence < settings.classification_confidence_threshold:
        reasons.append("low_classification_confidence")

    if entity_link_confidence < settings.entity_link_confidence_threshold and item.extracted_entities:
        reasons.append("low_entity_link_confidence")

    if (
        not item.extracted_entities
        and classification.event_category not in {EventCategory.NATURAL_DISASTER}
        and classification.event_category != EventCategory.OTHER
    ):
        reasons.append("no_entities_for_event_type")

    if severity.severity_score >= 70.0 and classification.confidence < 0.70:
        reasons.append("high_severity_low_confidence_mismatch")

    if (
        classification.event_category
        in {
            EventCategory.FACTORY_SHUTDOWN,
            EventCategory.LOGISTICS_DISRUPTION,
            EventCategory.EXPORT_SANCTION,
        }
        and len(item.linked_entities) < 1
    ):
        reasons.append("supply_chain_event_no_entities")

    return reasons


def _pick_primary(items: list[EnrichedArticle]) -> EnrichedArticle:
    """Select the representative article for a cluster."""

    def sort_key(item: EnrichedArticle) -> tuple[float, float]:
        severity = item.severity.severity_score if item.severity else 0.0
        confidence = item.classification.confidence if item.classification else 0.0
        return (severity, confidence)

    return max(items, key=sort_key)


def _linked_by_type(
    linked: list[LinkedEntity],
) -> dict[str, list[LinkedEntity]]:
    return {
        "linked_manufacturers": [
            e for e in linked if e.entity_type == EntityType.MANUFACTURER and e.canonical_id
        ],
        "linked_suppliers": [
            e for e in linked if e.entity_type == EntityType.SUPPLIER and e.canonical_id
        ],
        "linked_locations": [
            e for e in linked if e.entity_type == EntityType.LOCATION and e.canonical_id
        ],
        "linked_components": [
            e for e in linked if e.entity_type == EntityType.COMPONENT and e.canonical_id
        ],
    }


def build_risk_events_from_clusters(
    enriched: list[EnrichedArticle],
    audit_log: list[ProcessingStageAudit],
    pipeline_version: str,
) -> tuple[list[RiskEvent], list[RiskEvent], int]:
    """
    Build one RiskEvent per cluster (deduplicated), skipping non-actionable articles.

    Returns (risk_events, review_queue, skipped_non_disruption_count).
    """
    clusters: dict[str, list[EnrichedArticle]] = {}
    for item in enriched:
        if not is_actionable_disruption(item):
            continue
        cluster_key = item.cluster_id or item.article.article_id
        clusters.setdefault(cluster_key, []).append(item)

    risk_events: list[RiskEvent] = []
    review_queue: list[RiskEvent] = []
    skipped = len(enriched) - sum(len(v) for v in clusters.values())

    for cluster_id, items in clusters.items():
        primary = _pick_primary(items)

        classification = primary.classification or ClassificationResult(
            event_type="unclassified",
            event_category=EventCategory.OTHER,
            confidence=0.0,
        )
        severity = primary.severity or SeveritySignal()

        all_linked: list[LinkedEntity] = []
        all_extracted = []
        all_sources: list[SourceRecord] = []
        all_urls: list[str] = []
        review_reasons: set[str] = set()

        for item in items:
            all_linked.extend(item.linked_entities)
            all_extracted.extend(item.extracted_entities)
            review_reasons.update(
                _review_reasons_for_item(
                    item,
                    item.classification or classification,
                    item.severity or severity,
                    _entity_link_confidence(item.linked_entities),
                )
            )
            all_sources.append(
                SourceRecord(
                    provider=item.article.provider,
                    reliability_tier=item.article.reliability_tier,
                    url=item.article.url,
                    retrieved_at=item.article.retrieved_at,
                    raw_metadata={
                        **(item.article.provider_metadata or {}),
                        "article_id": item.article.article_id,
                    },
                )
            )
            if item.article.url:
                all_urls.append(item.article.url)

        deduped_linked = _dedupe_linked(all_linked)
        linked_groups = _linked_by_type(deduped_linked)

        entity_link_confidence = _entity_link_confidence(deduped_linked)
        extraction_confidence = _extraction_confidence(all_extracted)
        verification_score = _compute_verification_score(all_sources)

        severity = enhance_cluster_severity(
            primary,
            classification,
            deduped_linked,
            all_sources,
            verification_score,
        )
        overall_confidence, explainability = calibrate_confidence(
            classification=classification,
            linked_entities=deduped_linked,
            extracted_entities=all_extracted,
            sources=all_sources,
            verification_score=verification_score,
            severity_signal=severity,
        )

        if len(items) >= 2 and verification_score >= 0.6:
            review_reasons.discard("low_classification_confidence")

        provenance = ProvenanceInformation(
            sources=all_sources,
            processing_stages=audit_log,
            extraction_confidence=extraction_confidence,
            classification_confidence=classification.confidence,
            entity_link_confidence=entity_link_confidence,
            requires_human_review=bool(review_reasons),
            review_reasons=sorted(review_reasons),
            pipeline_version=pipeline_version,
        )

        summary = primary.article.body.strip()

        geo = extract_geo_from_article(primary)

        event = RiskEvent(
            event_id="",  # assigned below via stable fingerprint
            title=primary.article.title,
            summary=summary,
            event_type=classification.event_type,
            event_category=classification.event_category,
            classification_confidence=classification.confidence,
            severity_signal=severity,
            severity_score=severity.severity_score,
            extracted_entities=all_extracted,
            linked_manufacturers=linked_groups["linked_manufacturers"],
            linked_suppliers=linked_groups["linked_suppliers"],
            linked_locations=linked_groups["linked_locations"],
            linked_components=linked_groups["linked_components"],
            cluster_id=cluster_id,
            source_urls=sorted(set(all_urls)),
            source_count=len(items),
            verification_score=verification_score,
            article_ids=[item.article.article_id for item in items],
            latitude=geo.get("latitude"),
            longitude=geo.get("longitude"),
            geo_country=geo.get("geo_country"),
            geo_region=geo.get("geo_region"),
            status=EventLifecycleStatus.DETECTED,
            overall_confidence=overall_confidence,
            explainability=explainability,
            retrieval_timestamp=primary.article.retrieved_at or datetime.utcnow(),
            provenance_information=provenance,
        )
        assign_stable_identity(event)
        risk_events.append(event)
        if provenance.requires_human_review:
            review_queue.append(event)

    return risk_events, review_queue, skipped
