"""Tests for hybrid impact prediction engine."""

from unittest.mock import patch

from config.settings import settings
from models.schemas import (
    EntityType,
    EventCategory,
    EventLifecycleStatus,
    LinkedEntity,
    ProvenanceInformation,
    RiskAnalysis,
    RiskEvent,
    SeveritySignal,
)
from services.impact_prediction import (
    compute_rule_based_prediction,
    predict_impacts,
    should_predict_event,
)


def _sample_event(
    *,
    category: EventCategory = EventCategory.LOGISTICS_DISRUPTION,
    severity: float = 72.0,
    confidence: float = 0.75,
    with_suppliers: bool = False,
) -> RiskEvent:
    linked_suppliers = []
    if with_suppliers:
        linked_suppliers = [
            LinkedEntity(
                canonical_id="SUP:DIST001",
                canonical_name="Arrow",
                entity_type=EntityType.SUPPLIER,
                match_score=0.88,
                match_method="fuzzy",
                extracted_text="Arrow",
            )
        ]

    return RiskEvent(
        title="Port closure delays semiconductor shipments",
        summary="Container backlog at major export hub.",
        event_type="port_closure",
        event_category=category,
        classification_confidence=0.82,
        severity_signal=SeveritySignal(severity_score=severity, scoring_method="hybrid"),
        severity_score=severity,
        linked_suppliers=linked_suppliers,
        overall_confidence=confidence,
        verification_score=0.6,
        source_count=2,
        status=EventLifecycleStatus.DETECTED,
        provenance_information=ProvenanceInformation(pipeline_version="0.5.0"),
    )


def test_should_predict_event_below_severity():
    event = _sample_event(severity=20.0)
    ok, reason = should_predict_event(event)
    assert ok is False
    assert reason == "below_severity_threshold"


def test_rule_based_prediction_uses_category_baseline():
    event = _sample_event(category=EventCategory.LOGISTICS_DISRUPTION, severity=80.0)
    prediction = compute_rule_based_prediction(event)

    assert prediction.prediction_method == "rule_based"
    assert prediction.logistics_disruption.probability >= prediction.manufacturing_disruption.probability
    assert prediction.expected_recovery_days_min is not None
    assert prediction.expected_recovery_days_max >= prediction.expected_recovery_days_min
    assert prediction.prediction_confidence > 0.0


def test_higher_severity_increases_probabilities():
    low = compute_rule_based_prediction(_sample_event(severity=40.0))
    high = compute_rule_based_prediction(_sample_event(severity=85.0))
    assert high.supply_delay.probability >= low.supply_delay.probability


def test_predict_impacts_skips_low_severity():
    events = [_sample_event(severity=20.0), _sample_event(severity=70.0)]
    updated, summary = predict_impacts(events)

    assert summary["predicted"] == 1
    assert updated[0].impact_prediction is not None
    assert updated[0].impact_prediction.skipped is True
    assert updated[1].impact_prediction is not None
    assert updated[1].impact_prediction.skipped is False


def test_llm_refine_produces_hybrid_prediction():
    event = _sample_event(severity=88.0)
    event = event.model_copy(
        update={
            "risk_analysis": RiskAnalysis(
                executive_summary="Major logistics bottleneck expected.",
                analysis_confidence=0.8,
            )
        }
    )

    with patch("services.llm_client.chat_completion_json") as mock_json:
        mock_json.return_value = {
            "supply_delay_probability": 0.82,
            "manufacturing_disruption_probability": 0.45,
            "logistics_disruption_probability": 0.90,
            "inventory_shortage_probability": 0.55,
            "price_increase_probability": 0.40,
            "expected_recovery_days_min": 14,
            "expected_recovery_days_max": 75,
            "prediction_confidence": 0.78,
            "explanation": "Elevated logistics risk from multi-source confirmation.",
        }

        old_key = settings.openrouter_api_key
        old_refine = settings.impact_prediction_llm_refine
        settings.openrouter_api_key = "test-key"
        settings.impact_prediction_llm_refine = True
        try:
            updated, summary = predict_impacts([event])
        finally:
            settings.openrouter_api_key = old_key
            settings.impact_prediction_llm_refine = old_refine

    prediction = updated[0].impact_prediction
    assert prediction is not None
    assert prediction.prediction_method == "hybrid"
    assert prediction.logistics_disruption.probability == 0.9
    assert summary["llm_refined"] == 1
