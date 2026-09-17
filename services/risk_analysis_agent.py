"""LLM-powered risk impact analysis for detected supply chain events."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from config.settings import settings
from models.schemas import RiskAnalysis, RiskEvent

logger = logging.getLogger("news_agent.services.risk_analysis_agent")

SYSTEM_PROMPT = """You are a supply chain risk intelligence analyst.

Analyze the provided risk event and return ONLY valid JSON matching this schema:
{
  "executive_summary": "2-3 sentence executive summary",
  "business_impact": "Paragraph on operational and commercial impact",
  "affected_industries": ["industry1", "industry2"],
  "affected_manufacturers": ["manufacturer1"],
  "possible_consequences": ["consequence1", "consequence2"],
  "supply_chain_implications": ["implication1", "implication2"],
  "short_term_impact": "Impact over days to weeks",
  "long_term_impact": "Impact over months",
  "monitoring_actions": ["action1", "action2"],
  "confidence_explanation": "Why this assessment is reliable or uncertain",
  "analysis_confidence": 0.0
}

STRICT RULES:
- Focus on factual supply chain and business impact analysis.
- Do NOT recommend specific suppliers, alternate routes, inventory purchases, or mitigation vendors.
- monitoring_actions must be intelligence-gathering and monitoring steps only (e.g. track port status, monitor lead times, watch regulatory filings).
- Use linked entities and severity signals when available; note uncertainty when data is sparse.
- analysis_confidence is 0.0-1.0 reflecting your confidence in the analysis (not event severity).
- Return JSON only, no markdown fences."""


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json") :]
    if text.startswith("```"):
        text = text[len("```") :]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def should_analyze_event(event: RiskEvent) -> tuple[bool, str | None]:
    """Return whether an event qualifies for LLM analysis and skip reason if not."""
    if not settings.risk_analysis_enabled:
        return False, "analysis_disabled"
    from services.llm_client import llm_configured

    if not llm_configured():
        return False, "no_llm_api_key"
    if event.severity_score < settings.risk_analysis_min_severity:
        return False, "below_severity_threshold"
    if event.overall_confidence < settings.risk_analysis_min_confidence:
        return False, "below_confidence_threshold"
    return True, None


def _linked_entity_names(event: RiskEvent, entity_type: str) -> list[str]:
    mapping = {
        "manufacturer": event.linked_manufacturers,
        "supplier": event.linked_suppliers,
        "location": event.linked_locations,
        "component": event.linked_components,
    }
    entities = mapping.get(entity_type, [])
    return sorted({e.canonical_name for e in entities if e.canonical_name})


def build_event_context(event: RiskEvent) -> str:
    """Serialize event fields for the LLM prompt."""
    context: dict[str, Any] = {
        "title": event.title,
        "summary": event.summary,
        "event_type": event.event_type,
        "event_category": event.event_category.value,
        "severity_score": event.severity_score,
        "overall_confidence": event.overall_confidence,
        "classification_confidence": event.classification_confidence,
        "source_count": event.source_count,
        "verification_score": event.verification_score,
        "geo_country": event.geo_country,
        "geo_region": event.geo_region,
        "linked_manufacturers": _linked_entity_names(event, "manufacturer"),
        "linked_suppliers": _linked_entity_names(event, "supplier"),
        "linked_locations": _linked_entity_names(event, "location"),
        "linked_components": _linked_entity_names(event, "component"),
        "severity_summary": event.explainability.severity_summary,
        "confidence_explanation": event.explainability.confidence_explanation,
        "uncertainty_sources": event.explainability.uncertainty_sources,
        "source_urls": event.source_urls[:5],
    }
    return json.dumps(context, indent=2, default=str)


def _parse_analysis_response(content: str, model_used: str) -> RiskAnalysis:
    parsed = json.loads(_clean_json_response(content))

    confidence = parsed.get("analysis_confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    def _str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return RiskAnalysis(
        executive_summary=str(parsed.get("executive_summary", "")).strip(),
        business_impact=str(parsed.get("business_impact", "")).strip(),
        affected_industries=_str_list(parsed.get("affected_industries")),
        affected_manufacturers=_str_list(parsed.get("affected_manufacturers")),
        possible_consequences=_str_list(parsed.get("possible_consequences")),
        supply_chain_implications=_str_list(parsed.get("supply_chain_implications")),
        short_term_impact=str(parsed.get("short_term_impact", "")).strip(),
        long_term_impact=str(parsed.get("long_term_impact", "")).strip(),
        monitoring_actions=_str_list(parsed.get("monitoring_actions")),
        confidence_explanation=str(parsed.get("confidence_explanation", "")).strip(),
        analysis_confidence=confidence,
        model_used=model_used,
        generated_at=datetime.utcnow(),
    )


def _call_openrouter(context_json: str) -> str:
    from services.llm_client import chat_completion

    return chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"RISK EVENT CONTEXT:\n{context_json}",
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=2000,
        temperature=0.2,
        timeout=30.0,
    )


def analyze_event(event: RiskEvent) -> RiskAnalysis:
    """Run LLM analysis for a single event. Raises on API/parse failure."""
    context_json = build_event_context(event)
    content = _call_openrouter(context_json)
    return _parse_analysis_response(content, settings.openrouter_model)


def _skipped_analysis(reason: str) -> RiskAnalysis:
    return RiskAnalysis(skipped=True, skip_reason=reason)


def _select_analysis_indices(
    events: list[RiskEvent],
    eligible_indices: list[int],
) -> tuple[set[int], int]:
    """
    Select events for LLM analysis using severity tiers.

    - Events at or above ``risk_analysis_priority_severity`` are always analyzed.
    - Events between min severity and priority are analyzed when budget allows.
    - ``risk_analysis_max_events`` caps only the medium tier (0 = unlimited).
    """
    priority_floor = settings.risk_analysis_priority_severity
    max_events = settings.risk_analysis_max_events

    priority_indices = [
        index for index in eligible_indices if events[index].severity_score >= priority_floor
    ]
    medium_indices = [
        index for index in eligible_indices if events[index].severity_score < priority_floor
    ]
    medium_indices.sort(key=lambda index: events[index].severity_score, reverse=True)

    selected = set(priority_indices)
    budget_limited = 0

    if max_events <= 0:
        selected.update(medium_indices)
    else:
        selected_medium = medium_indices[:max_events]
        selected.update(selected_medium)
        budget_limited = max(0, len(medium_indices) - len(selected_medium))

    return selected, budget_limited


def analyze_events(events: list[RiskEvent]) -> tuple[list[RiskEvent], dict[str, Any]]:
    """
    Attach risk analysis to qualifying events (severity/confidence gated).

    Returns updated events and stage summary metadata.
    """
    if not events:
        return [], {
            "analyzed": 0,
            "skipped": 0,
            "failed": 0,
            "eligible": 0,
            "budget_limited": 0,
        }

    eligible_indices: list[int] = []
    skip_reasons: dict[str, int] = {}

    for index, event in enumerate(events):
        ok, reason = should_analyze_event(event)
        if ok:
            eligible_indices.append(index)
        elif reason:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    eligible_indices.sort(
        key=lambda i: events[i].severity_score,
        reverse=True,
    )
    selected, budget_limited = _select_analysis_indices(events, eligible_indices)

    updated = list(events)
    analyzed = 0
    failed = 0
    skipped = len(events) - len(eligible_indices) + budget_limited

    def process_index(index: int) -> tuple[int, RiskAnalysis | None, str | None]:
        if index not in selected:
            if index in eligible_indices:
                return index, _skipped_analysis("budget_limit"), None
            ok, reason = should_analyze_event(events[index])
            if not ok and reason:
                return index, _skipped_analysis(reason), None
            return index, None, None

        try:
            return index, analyze_event(events[index]), None
        except Exception as exc:
            logger.warning(
                "Risk analysis failed for event %s: %s",
                events[index].event_id,
                exc,
            )
            return index, _skipped_analysis("llm_error"), str(exc)

    from services.llm_client import llm_parallel_workers

    worker_count = min(llm_parallel_workers(), max(1, len(selected)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(process_index, range(len(events))))

    errors: list[str] = []
    for index, analysis, error in results:
        if analysis is None:
            continue
        updated[index] = events[index].model_copy(update={"risk_analysis": analysis})
        if analysis.skipped:
            if analysis.skip_reason == "llm_error":
                failed += 1
                if error:
                    errors.append(error)
        else:
            analyzed += 1

    summary = {
        "analyzed": analyzed,
        "skipped": skipped,
        "failed": failed,
        "eligible": len(eligible_indices),
        "budget_limited": budget_limited,
        "skip_reasons": skip_reasons,
        "errors": errors[:5],
    }
    return updated, summary
