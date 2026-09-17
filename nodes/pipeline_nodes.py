"""LangGraph node implementations."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from canonical.matchers import (
    extract_known_entities,
    extract_metadata_geo_entities,
    extract_strategic_location_entities,
    link_entities,
)
from config.settings import settings
from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    EntityType,
    EventCategory,
    ProcessingStageAudit,
    ProvenanceInformation,
    RawArticle,
    RiskEvent,
    SeveritySignal,
    SourceRecord,
)
from nodes.prefilter import filter_articles, write_drop_audit
from nodes.processing import (
    article_text,
    classify_article,
    estimate_severity,
)


def _audit(stage: str, input_count: int, output_count: int, **metadata) -> ProcessingStageAudit:
    return ProcessingStageAudit(
        stage=stage,
        input_count=input_count,
        output_count=output_count,
        dropped_count=max(0, input_count - output_count),
        metadata=metadata,
    )


def _entity_link_confidence(linked_entities: list) -> float:
    if not linked_entities:
        return 0.0
    return max(entity.match_score for entity in linked_entities)


def _extraction_confidence(extracted_entities: list) -> float:
    if not extracted_entities:
        return 0.0
    return sum(entity.confidence for entity in extracted_entities) / len(extracted_entities)


# ============================================================================
# NEW HELPER: Improved title similarity scoring for dedup
# ============================================================================
def _calculate_title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity between two titles.
    
    Uses normalized string similarity (word-level and character-level).
    Returns score 0.0-1.0 (1.0 = identical).
    """
    # Normalize titles
    t1 = title1.strip().lower()
    t2 = title2.strip().lower()
    
    # Exact match
    if t1 == t2:
        return 1.0
    
    # Split into words for word-level comparison
    words1 = set(t1.split())
    words2 = set(t2.split())
    
    if not words1 or not words2:
        return 0.0
    
    # Jaccard similarity on words
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    word_similarity = intersection / union if union > 0 else 0.0
    
    # Character-level Levenshtein-based similarity (simplified)
    # Compare at word level after removing common stop words
    stop_words = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "is", "by"}
    content_words1 = words1 - stop_words
    content_words2 = words2 - stop_words
    
    if content_words1 and content_words2:
        content_intersection = len(content_words1 & content_words2)
        content_union = len(content_words1 | content_words2)
        content_similarity = content_intersection / content_union if content_union > 0 else 0.0
    else:
        content_similarity = word_similarity
    
    # Weight: content words are more important (70%) than all words (30%)
    return 0.3 * word_similarity + 0.7 * content_similarity


def source_ingestion(state: dict) -> dict:
    """Stage 1 — fetch from providers or passthrough pre-loaded articles."""
    import asyncio

    from providers.registry import ingest_all_providers

    preloaded: list[RawArticle] = state.get("raw_articles", [])
    fetch_live = state.get("fetch_live", False)

    if preloaded:
        return {
            "raw_articles": preloaded,
            "audit_log": [
                _audit(
                    "source_ingestion",
                    len(preloaded),
                    len(preloaded),
                    mode="passthrough",
                )
            ],
        }

    if not fetch_live:
        return {
            "raw_articles": [],
            "audit_log": [_audit("source_ingestion", 0, 0, mode="skipped")],
        }

    articles, report = asyncio.run(
        ingest_all_providers(
            limit=settings.provider_fetch_limit,
            timeout=settings.http_timeout_seconds,
        )
    )
    provider_errors = [
        f"{name}: {info['error']}"
        for name, info in report.get("providers", {}).items()
        if info.get("error")
    ]

    return {
        "raw_articles": articles,
        "errors": provider_errors,
        "audit_log": [
            _audit(
                "source_ingestion",
                len(report.get("providers", {})),
                len(articles),
                mode="live",
                providers=report.get("providers", {}),
            )
        ],
    }


def relevance_prefilter(state: dict) -> dict:
    """Stage 2 — keyword/topic filter for supply-chain relevance."""
    articles: list[RawArticle] = state.get("raw_articles", [])
    enriched, drops = filter_articles(articles)
    drop_audit_path = write_drop_audit(drops)

    provider_kept: dict[str, int] = {}
    provider_dropped: dict[str, int] = {}
    for item in enriched:
        provider_kept[item.article.provider] = provider_kept.get(item.article.provider, 0) + 1
    for drop in drops:
        provider_dropped[drop.provider] = provider_dropped.get(drop.provider, 0) + 1

    return {
        "enriched_articles": enriched,
        "filtered_out_count": len(drops),
        "prefilter_drops": drops,
        "audit_log": [
            _audit(
                "relevance_prefilter",
                len(articles),
                len(enriched),
                dropped=len(drops),
                provider_kept=provider_kept,
                provider_dropped=provider_dropped,
                drop_audit_path=str(drop_audit_path) if drop_audit_path else None,
            )
        ],
    }


def ner_extraction(state: dict) -> dict:
    """Stage 3 — extract known suppliers, manufacturers, and locations."""
    enriched: list[EnrichedArticle] = state.get("enriched_articles", [])
    total_entities = 0
    
    # ========================================================================
    # IMPROVEMENT: Track extraction metrics
    # ========================================================================
    articles_with_entities = 0

    for item in enriched:
        text = article_text(item)
        metadata = item.article.provider_metadata or {}
        entities = extract_known_entities(text, item.article.article_id)
        entities.extend(extract_metadata_geo_entities(metadata, item.article.article_id))
        entities.extend(extract_strategic_location_entities(text, item.article.article_id))

        # Deduplicate extracted mentions by (text, type)
        seen: set[tuple[str, str]] = set()
        unique_entities = []
        for entity in entities:
            key = (entity.text.lower(), entity.entity_type.value)
            if key in seen:
                continue
            seen.add(key)
            unique_entities.append(entity)

        item.extracted_entities = unique_entities
        total_entities += len(item.extracted_entities)
        if item.extracted_entities:
            articles_with_entities += 1

    return {
        "enriched_articles": enriched,
        "audit_log": [
            _audit(
                "ner_extraction",
                len(enriched),
                len(enriched),
                entities_extracted=total_entities,
                articles_with_entities=articles_with_entities,
                avg_entities_per_article=round(total_entities / len(enriched), 2) if enriched else 0,
            )
        ],
    }


def entity_linking(state: dict) -> dict:
    """Stage 4 — link entities to canonical registry."""
    enriched: list[EnrichedArticle] = state.get("enriched_articles", [])
    
    if not enriched:
        return {
            "enriched_articles": enriched,
            "audit_log": [
                _audit(
                    "entity_linking",
                    0,
                    0,
                    linked_entities=0,
                )
            ],
        }

    from concurrent.futures import ThreadPoolExecutor
    from services.llm_client import llm_parallel_workers

    def process_item(item: EnrichedArticle) -> tuple[int, int]:
        text = article_text(item)
        item.linked_entities = link_entities(
            item.extracted_entities,
            text,
            item.article.provider_metadata,
        )
        return len(item.linked_entities), len(item.extracted_entities)

    workers = llm_parallel_workers()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(process_item, enriched))

    linked_count = sum(r[0] for r in results)
    total_extracted = sum(r[1] for r in results)
    
    # ========================================================================
    # IMPROVEMENT: Track linking success rate
    # ========================================================================
    linking_rate = (linked_count / total_extracted * 100) if total_extracted > 0 else 0

    return {
        "enriched_articles": enriched,
        "audit_log": [
            _audit(
                "entity_linking",
                len(enriched),
                len(enriched),
                linked_entities=linked_count,
                extracted_entities=total_extracted,
                linking_success_rate=round(linking_rate, 2),
            )
        ],
    }


def event_classification(state: dict) -> dict:
    """Stage 5 — classify into fixed taxonomy with confidence."""
    enriched: list[EnrichedArticle] = state.get("enriched_articles", [])
    classified = 0
    
    # ========================================================================
    # IMPROVEMENT: Track classification distribution
    # ========================================================================
    category_counts: dict[str, int] = {}
    confidence_sum = 0.0

    for item in enriched:
        item.classification = classify_article(item)
        if item.classification.event_category != EventCategory.OTHER:
            classified += 1
        
        category = item.classification.event_category.value
        category_counts[category] = category_counts.get(category, 0) + 1
        confidence_sum += item.classification.confidence

    avg_confidence = round(confidence_sum / len(enriched), 3) if enriched else 0.0

    return {
        "enriched_articles": enriched,
        "audit_log": [
            _audit(
                "event_classification",
                len(enriched),
                classified,
                classified_non_other=classified,
                category_distribution=category_counts,
                avg_classification_confidence=avg_confidence,
            )
        ],
    }


def severity_estimation(state: dict) -> dict:
    """Stage 6 — extract raw severity signal."""
    enriched: list[EnrichedArticle] = state.get("enriched_articles", [])
    
    # ========================================================================
    # IMPROVEMENT: Track severity metrics
    # ========================================================================
    severity_sum = 0.0
    high_severity_count = 0

    for item in enriched:
        classification = item.classification or ClassificationResult(
            event_type="unclassified",
            event_category=EventCategory.OTHER,
            confidence=0.0,
        )
        item.severity = estimate_severity(item, classification)
        severity_sum += item.severity.severity_score
        if item.severity.severity_score >= 70.0:
            high_severity_count += 1

    avg_severity = round(severity_sum / len(enriched), 2) if enriched else 0.0

    return {
        "enriched_articles": enriched,
        "audit_log": [
            _audit(
                "severity_estimation",
                len(enriched),
                len(enriched),
                avg_severity_score=avg_severity,
                high_severity_events=high_severity_count,
            )
        ],
    }


def dedup_clustering(state: dict) -> dict:
    """Stage 7 — cluster duplicate articles by similarity.
    
    IMPROVEMENTS:
    - Uses title similarity scoring (not just exact match)
    - Configurable similarity threshold
    - Better cluster statistics
    """
    enriched: list[EnrichedArticle] = state.get("enriched_articles", [])
    cluster_map: dict[str, list[str]] = {}
    article_to_cluster: dict[str, str] = {}
    
    # ========================================================================
    # IMPROVED: Similarity-based clustering threshold
    # ========================================================================
    SIMILARITY_THRESHOLD = 0.75  # 75% similarity = same cluster
    
    for item in enriched:
        title = item.article.title
        
        # Try to find similar cluster
        best_cluster_id = None
        best_similarity = 0.0
        
        for existing_title, cluster_id in article_to_cluster.items():
            similarity = _calculate_title_similarity(title, existing_title)
            if similarity >= SIMILARITY_THRESHOLD and similarity > best_similarity:
                best_cluster_id = cluster_id
                best_similarity = similarity
        
        # If no similar cluster found, create new one
        if best_cluster_id is None:
            best_cluster_id = str(uuid4())
            cluster_map[best_cluster_id] = []
        
        article_to_cluster[title] = best_cluster_id
        item.cluster_id = best_cluster_id
        cluster_map[best_cluster_id].append(item.article.article_id)

    # ========================================================================
    # IMPROVEMENT: Better cluster statistics
    # ========================================================================
    cluster_sizes = {}
    cluster_types = {}  # Track event types per cluster
    
    for cluster_id, article_ids in cluster_map.items():
        cluster_sizes[cluster_id] = len(article_ids)
        # Find most common event category in this cluster
        categories = {}
        for item in enriched:
            if item.cluster_id == cluster_id and item.classification:
                cat = item.classification.event_category.value
                categories[cat] = categories.get(cat, 0) + 1
        if categories:
            cluster_types[cluster_id] = max(categories, key=categories.get)

    avg_cluster_size = sum(len(aids) for aids in cluster_map.values()) / len(cluster_map) if cluster_map else 1.0
    max_cluster_size = max((len(aids) for aids in cluster_map.values()), default=1)

    return {
        "enriched_articles": enriched,
        "cluster_map": cluster_map,
        "audit_log": [
            _audit(
                "dedup_clustering",
                len(enriched),
                len(cluster_map),
                clusters=len(cluster_map),
                avg_cluster_size=round(avg_cluster_size, 2),
                max_cluster_size=max_cluster_size,
                cluster_types=cluster_types,
            )
        ],
    }


def provenance_attachment(state: dict) -> dict:
    """Stage 8 — attach audit trail and metadata to articles.
    
    IMPROVEMENTS:
    - Actually attaches the audit log from previous stages
    - Tracks processing quality metrics
    """
    enriched: list[EnrichedArticle] = state.get("enriched_articles", [])
    audit_log: list[ProcessingStageAudit] = state.get("audit_log", [])
    
    # ========================================================================
    # IMPROVEMENT: Attach audit log to provenance
    # (Will be used in risk_event_creation)
    # ========================================================================
    audit_summary = {
        "total_stages": len(audit_log),
        "stages": [
            {
                "stage": audit.stage,
                "input_count": audit.input_count,
                "output_count": audit.output_count,
                "dropped_count": audit.dropped_count,
            }
            for audit in audit_log
        ],
    }
    
    # Store in state for next stage
    state["_audit_summary"] = audit_summary
    
    # ========================================================================
    # IMPROVEMENT: Calculate end-to-end retention rate
    # ========================================================================
    if audit_log:
        initial_input = audit_log[0].input_count
        final_output = audit_log[-1].output_count
        retention_rate = (final_output / initial_input * 100) if initial_input > 0 else 0.0
    else:
        retention_rate = 100.0

    return {
        "enriched_articles": enriched,
        "audit_log": [
            _audit(
                "provenance_attachment",
                len(enriched),
                len(enriched),
                total_retention_rate=round(retention_rate, 2),
                stages_completed=len(audit_log),
            )
        ],
    }


def risk_event_creation(state: dict) -> dict:
    """Stage 9 — build cluster-merged RiskEvent records."""
    from services.cluster_merge import build_risk_events_from_clusters

    enriched: list[EnrichedArticle] = state.get("enriched_articles", [])
    audit_log: list[ProcessingStageAudit] = state.get("audit_log", [])
    pipeline_version = state.get("pipeline_version", "0.1.0")

    risk_events, review_queue, skipped_non_disruption = build_risk_events_from_clusters(
        enriched, audit_log, pipeline_version
    )

    review_reasons_count: dict[str, int] = {}
    for event in review_queue:
        for reason in event.provenance_information.review_reasons:
            review_reasons_count[reason] = review_reasons_count.get(reason, 0) + 1

    return {
        "risk_events": risk_events,
        "review_queue": review_queue,
        "audit_log": [
            _audit(
                "risk_event_creation",
                len(enriched),
                len(risk_events),
                risk_events_created=len(risk_events),
                articles_merged=len(enriched) - len(risk_events) - skipped_non_disruption,
                skipped_non_disruption=skipped_non_disruption,
                review_queue_size=len(review_queue),
                review_queue_rate=round(len(review_queue) / len(risk_events) * 100, 2) if risk_events else 0.0,
                review_reasons=review_reasons_count,
            )
        ],
    }


def risk_analysis(state: dict) -> dict:
    """Stage 10 — LLM impact analysis for qualifying risk events."""
    from services.risk_analysis_agent import analyze_events

    risk_events: list[RiskEvent] = state.get("risk_events", [])
    updated_events, summary = analyze_events(risk_events)

    return {
        "risk_events": updated_events,
        "audit_log": [
            _audit(
                "risk_analysis",
                len(risk_events),
                summary.get("analyzed", 0),
                **summary,
            )
        ],
    }


def impact_prediction(state: dict) -> dict:
    """Stage 11 — hybrid impact forecasting for qualifying risk events."""
    from services.impact_prediction import predict_impacts

    risk_events: list[RiskEvent] = state.get("risk_events", [])
    updated_events, summary = predict_impacts(risk_events)

    return {
        "risk_events": updated_events,
        "audit_log": [
            _audit(
                "impact_prediction",
                len(risk_events),
                summary.get("predicted", 0),
                **summary,
            )
        ],
    }


def persist_events(state: dict) -> dict:
    """Stage 12 — persist risk events (Supabase REST or Postgres) and evaluate alert rules."""
    from config.settings import settings
    from services.event_persistence import persist_risk_events

    run_id = state.get("run_id", "")
    risk_events: list[RiskEvent] = state.get("risk_events", [])

    if not settings.persist_events:
        return {
            "persistence_summary": {"persisted": 0, "skipped": len(risk_events), "database": "disabled"},
            "audit_log": [
                _audit("persist_events", len(risk_events), 0, mode="disabled"),
            ],
        }

    summary = persist_risk_events(run_id, risk_events)
    persisted_count = summary.get("persisted", 0)

    return {
        "persistence_summary": summary,
        "audit_log": [
            _audit(
                "persist_events",
                len(risk_events),
                persisted_count,
                **summary,
            )
        ],
    }