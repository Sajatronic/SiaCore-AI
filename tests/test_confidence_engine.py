"""Tests for confidence calibration."""

from datetime import datetime

from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    EventCategory,
    RawArticle,
    SeveritySignal,
    SourceRecord,
)
from services.confidence_engine import calibrate_confidence


def test_low_classification_adds_uncertainty():
    severity = SeveritySignal(severity_score=55.0, scoring_method="hybrid")
    overall, explainability = calibrate_confidence(
        classification=ClassificationResult(
            event_type="unclassified",
            event_category=EventCategory.OTHER,
            confidence=0.45,
            rationale="supply_chain_relevant_but_unmatched",
        ),
        linked_entities=[],
        extracted_entities=[],
        sources=[
            SourceRecord(
                provider="gdelt",
                reliability_tier=1,
                url="https://example.com",
                retrieved_at=datetime.utcnow(),
            )
        ],
        verification_score=0.0,
        severity_signal=severity,
    )
    assert overall < 0.6
    assert any(u["source"] == "low_classification_confidence" for u in explainability.uncertainty_sources)
    assert explainability.confidence_score == overall


def test_multi_source_increases_confidence():
    severity = SeveritySignal(severity_score=70.0, scoring_method="hybrid")
    sources = [
        SourceRecord(provider="gdacs", reliability_tier=1, url="https://a.com", retrieved_at=datetime.utcnow()),
        SourceRecord(provider="gdelt", reliability_tier=1, url="https://b.com", retrieved_at=datetime.utcnow()),
    ]
    overall, explainability = calibrate_confidence(
        classification=ClassificationResult(
            event_type="earthquake",
            event_category=EventCategory.NATURAL_DISASTER,
            confidence=0.9,
        ),
        linked_entities=[],
        extracted_entities=[],
        sources=sources,
        verification_score=0.75,
        severity_signal=severity,
    )
    assert overall >= 0.5
    assert not any(u["source"] == "few_sources" for u in explainability.uncertainty_sources)
