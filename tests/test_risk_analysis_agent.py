"""Tests for AI risk analysis agent."""

import json
from unittest.mock import patch

import httpx

from config.settings import settings
from models.schemas import (
    EventCategory,
    EventLifecycleStatus,
    ExplainabilityLayer,
    LinkedEntity,
    EntityType,
    ProvenanceInformation,
    RiskEvent,
    SeveritySignal,
)
from services.risk_analysis_agent import (
    analyze_event,
    analyze_events,
    build_event_context,
    should_analyze_event,
    _select_analysis_indices,
)


def _sample_event(
    *,
    severity: float = 75.0,
    confidence: float = 0.8,
) -> RiskEvent:
    return RiskEvent(
        title="Port closure disrupts semiconductor exports",
        summary="A major port closure is delaying container shipments.",
        event_type="port_closure",
        event_category=EventCategory.LOGISTICS_DISRUPTION,
        classification_confidence=0.85,
        severity_signal=SeveritySignal(severity_score=severity, scoring_method="hybrid"),
        severity_score=severity,
        linked_manufacturers=[
            LinkedEntity(
                canonical_id="mfr-1",
                canonical_name="TSMC",
                entity_type=EntityType.MANUFACTURER,
                match_score=0.9,
                match_method="llm",
                extracted_text="TSMC",
            )
        ],
        overall_confidence=confidence,
        explainability=ExplainabilityLayer(
            severity_summary="High logistics disruption severity.",
            confidence_explanation="Multiple corroborating signals.",
        ),
        status=EventLifecycleStatus.DETECTED,
        provenance_information=ProvenanceInformation(pipeline_version="0.4.0"),
    )


def test_should_analyze_event_below_severity():
    event = _sample_event(severity=30.0, confidence=0.9)
    ok, reason = should_analyze_event(event)
    assert ok is False
    assert reason == "below_severity_threshold"


def test_should_analyze_event_no_api_key():
    event = _sample_event()
    old_openrouter = settings.openrouter_api_key
    old_cerebras = settings.cerebras_api_key
    settings.openrouter_api_key = ""
    settings.cerebras_api_key = ""
    try:
        ok, reason = should_analyze_event(event)
        assert ok is False
        assert reason == "no_llm_api_key"
    finally:
        settings.openrouter_api_key = old_openrouter
        settings.cerebras_api_key = old_cerebras


def test_build_event_context_includes_linked_entities():
    event = _sample_event()
    context = json.loads(build_event_context(event))
    assert "TSMC" in context["linked_manufacturers"]
    assert context["severity_score"] == 75.0


def test_analyze_event_mock_llm():
    with patch("services.llm_client.chat_completion") as mock_completion:
        mock_completion.return_value = json.dumps(
            {
                "executive_summary": "Port closure delays chip exports.",
                "business_impact": "Manufacturers face extended lead times.",
                "affected_industries": ["semiconductors"],
                "affected_manufacturers": ["TSMC"],
                "possible_consequences": ["Shipment delays"],
                "supply_chain_implications": ["Backlog at port"],
                "short_term_impact": "Weeks of delay",
                "long_term_impact": "Potential inventory drawdown",
                "monitoring_actions": ["Track port reopening notices"],
                "confidence_explanation": "Based on linked entities and severity.",
                "analysis_confidence": 0.82,
            }
        )

        old_key = settings.openrouter_api_key
        settings.openrouter_api_key = "test-key"
        try:
            analysis = analyze_event(_sample_event())
        finally:
            settings.openrouter_api_key = old_key

    assert analysis.executive_summary.startswith("Port closure")
    assert analysis.monitoring_actions == ["Track port reopening notices"]
    assert analysis.analysis_confidence == 0.82
    assert analysis.skipped is False


def test_select_analysis_indices_priority_always_included():
    events = [
        _sample_event(severity=90.0),
        _sample_event(severity=80.0),
        _sample_event(severity=55.0),
        _sample_event(severity=52.0),
    ]
    eligible = list(range(len(events)))

    old_priority = settings.risk_analysis_priority_severity
    old_max = settings.risk_analysis_max_events
    settings.risk_analysis_priority_severity = 65.0
    settings.risk_analysis_max_events = 1
    try:
        selected, budget_limited = _select_analysis_indices(events, eligible)
    finally:
        settings.risk_analysis_priority_severity = old_priority
        settings.risk_analysis_max_events = old_max

    assert selected == {0, 1, 2}
    assert budget_limited == 1


def test_analyze_events_respects_medium_tier_budget():
    events = [
        _sample_event(severity=90.0),
        _sample_event(severity=55.0),
        _sample_event(severity=52.0),
    ]

    with patch("services.llm_client.chat_completion") as mock_completion:
        mock_completion.return_value = json.dumps(
            {"executive_summary": "x", "analysis_confidence": 0.7}
        )

        old_key = settings.openrouter_api_key
        old_max = settings.risk_analysis_max_events
        old_priority = settings.risk_analysis_priority_severity
        settings.openrouter_api_key = "test-key"
        settings.risk_analysis_max_events = 1
        settings.risk_analysis_priority_severity = 65.0
        try:
            updated, summary = analyze_events(events)
        finally:
            settings.openrouter_api_key = old_key
            settings.risk_analysis_max_events = old_max
            settings.risk_analysis_priority_severity = old_priority

    analyzed = [e for e in updated if e.risk_analysis and not e.risk_analysis.skipped]
    budget_skipped = [
        e for e in updated if e.risk_analysis and e.risk_analysis.skip_reason == "budget_limit"
    ]
    assert len(analyzed) == 2
    assert len(budget_skipped) == 1
    assert summary["budget_limited"] == 1


def test_analyze_events_priority_ignores_budget():
    events = [
        _sample_event(severity=90.0),
        _sample_event(severity=80.0),
        _sample_event(severity=75.0),
    ]

    with patch("services.llm_client.chat_completion") as mock_completion:
        mock_completion.return_value = json.dumps(
            {"executive_summary": "x", "analysis_confidence": 0.7}
        )

        old_key = settings.openrouter_api_key
        old_max = settings.risk_analysis_max_events
        old_priority = settings.risk_analysis_priority_severity
        settings.openrouter_api_key = "test-key"
        settings.risk_analysis_max_events = 1
        settings.risk_analysis_priority_severity = 65.0
        try:
            updated, summary = analyze_events(events)
        finally:
            settings.openrouter_api_key = old_key
            settings.risk_analysis_max_events = old_max
            settings.risk_analysis_priority_severity = old_priority

    analyzed = [e for e in updated if e.risk_analysis and not e.risk_analysis.skipped]
    assert len(analyzed) == 3
    assert summary["budget_limited"] == 0


def test_analyze_events_llm_failure_marks_skipped():
    with patch("services.llm_client.chat_completion", side_effect=httpx.ConnectError("failed")):
        old_key = settings.openrouter_api_key
        settings.openrouter_api_key = "test-key"
        try:
            updated, summary = analyze_events([_sample_event()])
        finally:
            settings.openrouter_api_key = old_key

    assert updated[0].risk_analysis is not None
    assert updated[0].risk_analysis.skipped is True
    assert updated[0].risk_analysis.skip_reason == "llm_error"
    assert summary["failed"] == 1
