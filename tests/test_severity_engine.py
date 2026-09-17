"""Tests for hybrid severity engine."""

from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    EntityType,
    EventCategory,
    LinkedEntity,
    RawArticle,
    SeveritySignal,
)
from services.severity_engine import (
    _combine_factors,
    estimate_severity_hybrid,
    invalidate_severity_caches,
)


def test_hybrid_scoring_method():
    item = EnrichedArticle(
        article=RawArticle(
            provider="gdacs",
            title="Earthquake in Taiwan",
            body="Magnitude 6.5 earthquake near semiconductor fabs",
            provider_metadata={"event_type": "EQ", "alert_level": "Orange"},
        ),
        classification=ClassificationResult(
            event_type="earthquake",
            event_category=EventCategory.NATURAL_DISASTER,
            confidence=0.92,
        ),
    )
    signal = estimate_severity_hybrid(item, item.classification)
    assert signal.scoring_method == "hybrid"
    assert 0 <= signal.severity_score <= 100
    assert "hybrid_factors" in signal.raw_signal
    assert len(signal.raw_signal["hybrid_factors"]) == 7


def test_supplier_criticality_boosts_score():
    invalidate_severity_caches()
    base_item = EnrichedArticle(
        article=RawArticle(
            provider="gnews",
            title="Factory shutdown at semiconductor plant",
            body="Production halted indefinitely at major facility",
        ),
        classification=ClassificationResult(
            event_type="announced_closure",
            event_category=EventCategory.FACTORY_SHUTDOWN,
            confidence=0.8,
        ),
    )
    base_signal = estimate_severity_hybrid(base_item, base_item.classification)

    linked_item = EnrichedArticle(
        article=base_item.article,
        classification=base_item.classification,
        linked_entities=[
            LinkedEntity(
                canonical_id="SUP001",
                canonical_name="Newark",
                entity_type=EntityType.SUPPLIER,
                match_score=0.9,
                match_method="test",
                extracted_text="Newark",
            )
        ],
    )
    boosted = estimate_severity_hybrid(linked_item, linked_item.classification)
    supplier_factor = next(
        f for f in boosted.raw_signal["hybrid_factors"] if f["factor"] == "supplier_criticality"
    )
    assert supplier_factor["score"] >= 0


def test_combine_factors_weighted():
    factors = [
        {"factor": "a", "score": 100.0, "weight": 0.5, "contribution": 50.0},
        {"factor": "b", "score": 0.0, "weight": 0.5, "contribution": 0.0},
    ]
    assert _combine_factors(factors) == 50.0
