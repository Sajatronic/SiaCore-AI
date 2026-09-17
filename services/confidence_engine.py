"""Confidence calibration and explainability for risk events."""

from __future__ import annotations

from models.schemas import (
    ClassificationResult,
    EnrichedArticle,
    ExplainabilityLayer,
    LinkedEntity,
    SeveritySignal,
    SourceRecord,
)
from services.severity_engine import _severity_summary


def _entity_link_confidence(linked_entities: list[LinkedEntity]) -> float:
    if not linked_entities:
        return 0.0
    return max(entity.match_score for entity in linked_entities)


def _extraction_confidence(extracted_entities: list) -> float:
    if not extracted_entities:
        return 0.0
    return sum(entity.confidence for entity in extracted_entities) / len(extracted_entities)


def _source_reliability_component(sources: list[SourceRecord]) -> float:
    if not sources:
        return 0.5
    tier_weights = {1: 1.0, 2: 0.85, 3: 0.65}
    scores = [tier_weights.get(s.reliability_tier, 0.5) for s in sources]
    return sum(scores) / len(scores)


def calibrate_confidence(
    *,
    classification: ClassificationResult,
    linked_entities: list[LinkedEntity],
    extracted_entities: list,
    sources: list[SourceRecord],
    verification_score: float,
    severity_signal: SeveritySignal,
) -> tuple[float, ExplainabilityLayer]:
    """
    Produce an overall confidence score (0–1) with explicit uncertainty sources.

    Weights:
    - classification confidence: 35%
    - entity linking: 25%
    - extraction: 15%
    - source reliability: 15%
    - multi-source verification: 10%
    """
    entity_link = _entity_link_confidence(linked_entities)
    extraction = _extraction_confidence(extracted_entities)
    source_rel = _source_reliability_component(sources)

    overall = (
        classification.confidence * 0.35
        + entity_link * 0.25
        + extraction * 0.15
        + source_rel * 0.15
        + verification_score * 0.10
    )
    overall = round(min(1.0, max(0.0, overall)), 3)

    uncertainties: list[dict[str, str]] = []
    contributing: list[str] = []

    if len(sources) < 2:
        uncertainties.append(
            {
                "source": "few_sources",
                "impact": "medium",
                "explanation": "Only one source reported this event; cross-source confirmation is limited.",
            }
        )
    else:
        contributing.append(f"Confirmed by {len(sources)} independent sources")

    if classification.confidence < 0.6:
        uncertainties.append(
            {
                "source": "low_classification_confidence",
                "impact": "high",
                "explanation": (
                    f"Event type classification confidence is {classification.confidence:.2f} "
                    f"({classification.rationale})."
                ),
            }
        )
    else:
        contributing.append(f"Strong classification signal ({classification.confidence:.2f})")

    if extracted_entities and entity_link < 0.7:
        uncertainties.append(
            {
                "source": "weak_entity_matching",
                "impact": "medium",
                "explanation": (
                    f"Entity linking confidence is {entity_link:.2f}; "
                    "canonical matches may be uncertain."
                ),
            }
        )
    elif linked_entities:
        contributing.append(f"Entities linked with confidence up to {entity_link:.2f}")

    if not linked_entities and classification.event_category.value not in {
        "natural_disaster",
        "other",
    }:
        uncertainties.append(
            {
                "source": "missing_entity_links",
                "impact": "high",
                "explanation": "No supply-chain entities were linked for this event category.",
            }
        )

    if verification_score < 0.5 and len(sources) >= 2:
        uncertainties.append(
            {
                "source": "weak_multi_source_agreement",
                "impact": "low",
                "explanation": "Multiple sources present but verification score remains low.",
            }
        )

    factors = severity_signal.raw_signal.get("hybrid_factors", [])
    severity_summary = severity_signal.raw_signal.get(
        "severity_summary",
        _severity_summary(factors, severity_signal.severity_score) if factors else "",
    )

    if uncertainties:
        confidence_explanation = (
            f"Overall confidence {overall:.0%}. "
            f"{len(uncertainties)} uncertainty source(s) identified."
        )
    else:
        confidence_explanation = f"Overall confidence {overall:.0%}. No major uncertainty flags."

    explainability = ExplainabilityLayer(
        severity_factors=factors,
        severity_summary=severity_summary,
        confidence_score=overall,
        confidence_explanation=confidence_explanation,
        uncertainty_sources=uncertainties,
        contributing_factors=contributing,
    )
    return overall, explainability


def calibrate_article_confidence(
    item: EnrichedArticle,
    classification: ClassificationResult,
    severity_signal: SeveritySignal,
) -> tuple[float, ExplainabilityLayer]:
    """Calibrate confidence for a single article before cluster merge."""
    source = SourceRecord(
        provider=item.article.provider,
        reliability_tier=item.article.reliability_tier,
        url=item.article.url,
        retrieved_at=item.article.retrieved_at,
        raw_metadata=item.article.provider_metadata,
    )
    return calibrate_confidence(
        classification=classification,
        linked_entities=item.linked_entities,
        extracted_entities=item.extracted_entities,
        sources=[source],
        verification_score=0.0,
        severity_signal=severity_signal,
    )
