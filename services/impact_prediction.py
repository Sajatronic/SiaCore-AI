"""Hybrid impact prediction engine — rule-based priors with optional LLM refinement."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from typing import Any

import yaml

from config.settings import settings
from models.schemas import ImpactMetric, ImpactPrediction, RiskEvent

logger = logging.getLogger("news_agent.services.impact_prediction")

LLM_REFINE_PROMPT = """You are a supply chain impact forecasting analyst.

Given rule-based impact predictions and event context, return ONLY valid JSON:
{
  "supply_delay_probability": 0.0,
  "manufacturing_disruption_probability": 0.0,
  "logistics_disruption_probability": 0.0,
  "inventory_shortage_probability": 0.0,
  "price_increase_probability": 0.0,
  "expected_recovery_days_min": 0,
  "expected_recovery_days_max": 0,
  "prediction_confidence": 0.0,
  "explanation": "Brief rationale for adjustments"
}

RULES:
- Adjust probabilities only within ±0.15 of the rule-based values provided.
- All probabilities must stay between 0.0 and 1.0.
- Recovery day bounds must be positive integers with min <= max.
- Do NOT recommend suppliers, routes, or mitigation actions.
- prediction_confidence reflects forecast reliability (0.0-1.0).
- Return JSON only, no markdown fences."""


@lru_cache(maxsize=1)
def _load_baselines() -> dict[str, Any]:
    path = settings.project_root / settings.impact_baselines_path
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _clamp_prob(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _baseline_for_category(category: str) -> dict[str, Any]:
    config = _load_baselines()
    defaults = config.get("default", {})
    category_cfg = config.get("categories", {}).get(category, {})
    merged = {**defaults, **category_cfg}
    return merged


@lru_cache(maxsize=1)
def _inventory_lead_time_lookup() -> dict[str, list[int]]:
    """Map supplier_code -> lead times (days) from catalog inventory when available."""
    lookup: dict[str, list[int]] = {}
    try:
        from db.supabase import get_session, query_inventory_lead_times

        session = get_session()
        try:
            for row in query_inventory_lead_times(session):
                supplier_code = str(row.get("supplier_code") or "")
                lead_time = row.get("lead_time_days")
                if not supplier_code or lead_time is None:
                    continue
                try:
                    days = int(float(lead_time))
                except (TypeError, ValueError):
                    continue
                lookup.setdefault(supplier_code, []).append(days)
        finally:
            session.close()
    except Exception as exc:
        logger.debug("Inventory lead time lookup unavailable: %s", exc)
    return lookup


def _linked_supplier_codes(event: RiskEvent) -> list[str]:
    codes: list[str] = []
    for supplier in event.linked_suppliers:
        code = supplier.canonical_id.replace("SUP:", "").replace("sup:", "")
        if code:
            codes.append(code)
    return sorted(set(codes))


def _inventory_context(event: RiskEvent) -> dict[str, Any]:
    lookup = _inventory_lead_time_lookup()
    supplier_codes = _linked_supplier_codes(event)
    lead_times: list[int] = []
    for code in supplier_codes:
        lead_times.extend(lookup.get(code, []))

    avg_lead_time = (
        round(sum(lead_times) / len(lead_times), 1) if lead_times else settings.default_lead_time_days
    )
    return {
        "linked_supplier_count": len(event.linked_suppliers),
        "linked_component_count": len(event.linked_components),
        "linked_manufacturer_count": len(event.linked_manufacturers),
        "avg_lead_time_days": avg_lead_time,
        "lead_time_samples": len(lead_times),
    }


def _severity_multiplier(severity_score: float) -> float:
    return 0.55 + (severity_score / 100.0) * 0.55


def _confidence_from_event(event: RiskEvent, evidence_count: int) -> float:
    base = 0.35 + event.overall_confidence * 0.35 + event.verification_score * 0.15
    base += min(0.15, evidence_count * 0.02)
    if event.risk_analysis and not event.risk_analysis.skipped:
        base += 0.1
    return _clamp_prob(base)


def compute_rule_based_prediction(event: RiskEvent) -> ImpactPrediction:
    """Generate baseline impact forecast from category, severity, and catalog context."""
    baseline = _baseline_for_category(event.event_category.value)
    inv_ctx = _inventory_context(event)
    severity_mult = _severity_multiplier(event.severity_score)
    factors: list[dict[str, Any]] = []

    def metric(key: str, label: str, extra_evidence: list[str] | None = None) -> ImpactMetric:
        prior = float(baseline.get(key, 0.25))
        adjusted = _clamp_prob(prior * severity_mult)
        evidence = [
            f"category_baseline={prior:.2f}",
            f"severity_multiplier={severity_mult:.2f}",
            f"severity_score={event.severity_score:.1f}",
        ]
        if extra_evidence:
            evidence.extend(extra_evidence)
        factors.append({"factor": label, "prior": prior, "adjusted": adjusted})
        conf = _clamp_prob(0.45 + event.classification_confidence * 0.25)
        return ImpactMetric(probability=adjusted, confidence=conf, evidence=evidence)

    supplier_evidence: list[str] = []
    if inv_ctx["linked_supplier_count"]:
        supplier_evidence.append(f"linked_suppliers={inv_ctx['linked_supplier_count']}")
    if inv_ctx["lead_time_samples"]:
        supplier_evidence.append(f"avg_lead_time_days={inv_ctx['avg_lead_time_days']}")

    supply_delay = metric("supply_delay_probability", "supply_delay", supplier_evidence)
    manufacturing = metric("manufacturing_disruption_probability", "manufacturing_disruption")
    logistics = metric("logistics_disruption_probability", "logistics_disruption")
    inventory = metric("inventory_shortage_probability", "inventory_shortage", supplier_evidence)
    price = metric("price_increase_probability", "price_increase")

    if inv_ctx["linked_component_count"] >= 3:
        inventory = ImpactMetric(
            probability=_clamp_prob(inventory.probability + 0.08),
            confidence=inventory.confidence,
            evidence=inventory.evidence + [f"linked_components={inv_ctx['linked_component_count']}"],
        )

    if event.source_count >= 2:
        boost = min(0.05, 0.02 * (event.source_count - 1))
        logistics = ImpactMetric(
            probability=_clamp_prob(logistics.probability + boost),
            confidence=_clamp_prob(logistics.confidence + 0.05),
            evidence=logistics.evidence + [f"multi_source_count={event.source_count}"],
        )

    recovery_min = int(baseline.get("recovery_days_min", 7))
    recovery_max = int(baseline.get("recovery_days_max", 45))
    lead_time = int(inv_ctx["avg_lead_time_days"])
    recovery_min = max(recovery_min, int(lead_time * 0.5))
    recovery_max = max(recovery_max, lead_time, recovery_min)

    if severity_mult >= 0.95:
        recovery_max = int(recovery_max * 1.25)

    evidence_count = len(factors) + len(supplier_evidence)
    prediction_confidence = _confidence_from_event(event, evidence_count)

    return ImpactPrediction(
        supply_delay=supply_delay,
        manufacturing_disruption=manufacturing,
        logistics_disruption=logistics,
        inventory_shortage=inventory,
        price_increase=price,
        expected_recovery_days_min=recovery_min,
        expected_recovery_days_max=recovery_max,
        prediction_confidence=prediction_confidence,
        prediction_method="rule_based",
        explanation=(
            f"Rule-based forecast from {event.event_category.value} baseline, "
            f"severity {event.severity_score:.0f}, and catalog lead-time context."
        ),
        contributing_factors=factors,
        generated_at=datetime.utcnow(),
    )


def _prediction_payload(prediction: ImpactPrediction) -> dict[str, Any]:
    return {
        "supply_delay_probability": prediction.supply_delay.probability,
        "manufacturing_disruption_probability": prediction.manufacturing_disruption.probability,
        "logistics_disruption_probability": prediction.logistics_disruption.probability,
        "inventory_shortage_probability": prediction.inventory_shortage.probability,
        "price_increase_probability": prediction.price_increase.probability,
        "expected_recovery_days_min": prediction.expected_recovery_days_min,
        "expected_recovery_days_max": prediction.expected_recovery_days_max,
        "prediction_confidence": prediction.prediction_confidence,
        "prediction_method": prediction.prediction_method,
        "explanation": prediction.explanation,
    }


def _apply_llm_adjustments(
    rule_prediction: ImpactPrediction,
    adjustments: dict[str, Any],
) -> ImpactPrediction:
    def blend(metric: ImpactMetric, key: str) -> ImpactMetric:
        raw = adjustments.get(key)
        if raw is None:
            return metric
        try:
            target = float(raw)
        except (TypeError, ValueError):
            return metric
        target = _clamp_prob(target)
        lower = _clamp_prob(metric.probability - 0.15)
        upper = _clamp_prob(metric.probability + 0.15)
        blended = _clamp_prob(max(lower, min(upper, target)))
        evidence = metric.evidence + [f"llm_adjusted={blended:.2f}"]
        return ImpactMetric(
            probability=blended,
            confidence=_clamp_prob(metric.confidence + 0.05),
            evidence=evidence,
        )

    recovery_min = rule_prediction.expected_recovery_days_min or 7
    recovery_max = rule_prediction.expected_recovery_days_max or recovery_min
    try:
        llm_min = int(adjustments.get("expected_recovery_days_min", recovery_min))
        llm_max = int(adjustments.get("expected_recovery_days_max", recovery_max))
        if llm_min > 0 and llm_max >= llm_min:
            recovery_min, recovery_max = llm_min, llm_max
    except (TypeError, ValueError):
        pass

    try:
        llm_conf = float(adjustments.get("prediction_confidence", rule_prediction.prediction_confidence))
    except (TypeError, ValueError):
        llm_conf = rule_prediction.prediction_confidence

    explanation = str(adjustments.get("explanation", rule_prediction.explanation)).strip()

    return ImpactPrediction(
        supply_delay=blend(rule_prediction.supply_delay, "supply_delay_probability"),
        manufacturing_disruption=blend(
            rule_prediction.manufacturing_disruption, "manufacturing_disruption_probability"
        ),
        logistics_disruption=blend(
            rule_prediction.logistics_disruption, "logistics_disruption_probability"
        ),
        inventory_shortage=blend(rule_prediction.inventory_shortage, "inventory_shortage_probability"),
        price_increase=blend(rule_prediction.price_increase, "price_increase_probability"),
        expected_recovery_days_min=recovery_min,
        expected_recovery_days_max=recovery_max,
        prediction_confidence=_clamp_prob(llm_conf),
        prediction_method="hybrid",
        explanation=explanation or rule_prediction.explanation,
        contributing_factors=rule_prediction.contributing_factors
        + [{"factor": "llm_refinement", "method": "hybrid"}],
        generated_at=datetime.utcnow(),
    )


def _llm_refine_prediction(event: RiskEvent, rule_prediction: ImpactPrediction) -> ImpactPrediction:
    from services.llm_client import chat_completion_json

    context = {
        "event": {
            "title": event.title,
            "summary": event.summary,
            "event_category": event.event_category.value,
            "severity_score": event.severity_score,
            "overall_confidence": event.overall_confidence,
        },
        "rule_prediction": _prediction_payload(rule_prediction),
        "risk_analysis_summary": (
            event.risk_analysis.executive_summary if event.risk_analysis else ""
        ),
    }

    parsed = chat_completion_json(
        messages=[
            {"role": "system", "content": LLM_REFINE_PROMPT},
            {"role": "user", "content": json.dumps(context, indent=2, default=str)},
        ],
        max_tokens=1200,
        temperature=0.15,
        timeout=25.0,
    )
    return _apply_llm_adjustments(rule_prediction, parsed)


def should_predict_event(event: RiskEvent) -> tuple[bool, str | None]:
    if not settings.impact_prediction_enabled:
        return False, "prediction_disabled"
    if event.severity_score < settings.impact_prediction_min_severity:
        return False, "below_severity_threshold"
    return True, None


def should_llm_refine(event: RiskEvent) -> bool:
    if not settings.impact_prediction_llm_refine:
        return False
    if not settings.openrouter_api_key:
        return False
    if event.risk_analysis and event.risk_analysis.skipped:
        return False
    return True


def predict_event_impacts(event: RiskEvent, *, llm_refine: bool = False) -> ImpactPrediction:
    rule_prediction = compute_rule_based_prediction(event)
    if not llm_refine or not should_llm_refine(event):
        return rule_prediction
    try:
        return _llm_refine_prediction(event, rule_prediction)
    except Exception as exc:
        logger.warning("LLM impact refinement failed for event %s: %s", event.event_id, exc)
        fallback = rule_prediction.model_copy(deep=True)
        fallback.explanation = f"{fallback.explanation} (LLM refinement unavailable)"
        return fallback


def predict_impacts(events: list[RiskEvent]) -> tuple[list[RiskEvent], dict[str, Any]]:
    """Attach impact predictions to qualifying events."""
    if not events:
        return [], {"predicted": 0, "skipped": 0, "llm_refined": 0, "failed": 0}

    eligible_indices: list[int] = []
    skip_reasons: dict[str, int] = {}
    for index, event in enumerate(events):
        ok, reason = should_predict_event(event)
        if ok:
            eligible_indices.append(index)
        elif reason:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    refine_candidates = sorted(
        [
            i
            for i in eligible_indices
            if should_llm_refine(events[i])
        ],
        key=lambda i: events[i].severity_score,
        reverse=True,
    )
    refine_set = set(refine_candidates[: max(0, settings.impact_prediction_max_llm_refines)])

    updated = list(events)
    predicted = 0
    llm_refined = 0
    failed = 0

    def process_index(index: int) -> tuple[int, ImpactPrediction | None]:
        event = events[index]
        ok, reason = should_predict_event(event)
        if not ok:
            if reason:
                return index, ImpactPrediction(skipped=True, skip_reason=reason)
            return index, None

        use_llm = index in refine_set
        try:
            prediction = predict_event_impacts(event, llm_refine=use_llm)
            return index, prediction
        except Exception as exc:
            logger.warning("Impact prediction failed for event %s: %s", event.event_id, exc)
            return index, ImpactPrediction(skipped=True, skip_reason="prediction_error")

    from services.llm_client import llm_parallel_workers

    worker_count = min(llm_parallel_workers(), max(1, len(eligible_indices)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(process_index, range(len(events))))

    for index, prediction in results:
        if prediction is None:
            continue
        updated[index] = events[index].model_copy(update={"impact_prediction": prediction})
        if prediction.skipped:
            if prediction.skip_reason == "prediction_error":
                failed += 1
        else:
            predicted += 1
            if prediction.prediction_method == "hybrid":
                llm_refined += 1

    skipped = len(events) - predicted - failed
    return updated, {
        "predicted": predicted,
        "skipped": skipped,
        "llm_refined": llm_refined,
        "failed": failed,
        "eligible": len(eligible_indices),
        "skip_reasons": skip_reasons,
    }
