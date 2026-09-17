"""Tests for cluster merge and non-disruption filtering."""

from datetime import datetime

from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    EventCategory,
    RawArticle,
    SeveritySignal,
)
from nodes.processing import is_actionable_disruption
from services.cluster_merge import build_risk_events_from_clusters


def _article(title: str, body: str = "", url: str | None = None, **metadata) -> EnrichedArticle:
    return EnrichedArticle(
        article=RawArticle(
            provider="gdelt",
            title=title,
            body=body,
            url=url or f"https://example.com/{title[:20].replace(' ', '-').lower()}",
            provider_metadata=metadata,
            retrieved_at=datetime.utcnow(),
        ),
        classification=ClassificationResult(
            event_type="unclassified",
            event_category=EventCategory.OTHER,
            confidence=0.5,
        ),
        severity=SeveritySignal(severity_score=30.0),
    )


def test_non_disruption_corporate_news_filtered():
    item = _article(
        "TSMC posts revenue jump on AI chip demand",
        "Strong demand for advanced chips.",
        raw={
            "category": "CORPORATE",
            "event_code": "CO04",
            "subcategory": "Technology Development Milestone",
            "metrics": {"significance": 0.34},
        },
    )
    assert is_actionable_disruption(item) is False


def test_disruption_keywords_pass_filter():
    item = _article(
        "Factory shutdown at semiconductor plant",
        "Production halted due to fire.",
    )
    item.classification = ClassificationResult(
        event_type="announced_closure",
        event_category=EventCategory.FACTORY_SHUTDOWN,
        confidence=0.8,
    )
    assert is_actionable_disruption(item) is True


def test_cluster_merge_produces_one_event():
    cluster_id = "cluster-1"
    a1 = _article(
        "Port closure disrupts shipments",
        "Major port shutdown in Asia.",
        url="https://example.com/port-closure-1",
    )
    a1.cluster_id = cluster_id
    a1.classification = ClassificationResult(
        event_type="port_closure",
        event_category=EventCategory.LOGISTICS_DISRUPTION,
        confidence=0.84,
    )
    a1.severity = SeveritySignal(severity_score=70.0)

    a2 = _article(
        "Port closure disrupts chip logistics",
        "Shipping delay expected.",
        url="https://example.com/port-closure-2",
    )
    a2.cluster_id = cluster_id
    a2.classification = a1.classification
    a2.severity = SeveritySignal(severity_score=55.0)

    events, review, skipped = build_risk_events_from_clusters([a1, a2], [], "0.2.0")

    assert skipped == 0
    assert len(events) == 1
    assert events[0].source_count == 2
    assert events[0].verification_score > 0
    assert len(events[0].source_urls) == 2
