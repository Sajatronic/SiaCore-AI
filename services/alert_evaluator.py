"""Config-only alert rule evaluation (no delivery channels in Phase 1)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config.settings import settings
from models.schemas import AlertRuleMatch, RiskEvent

logger = logging.getLogger("news_agent.services.alert_evaluator")


@lru_cache(maxsize=1)
def _load_alert_config() -> dict[str, Any]:
    path = settings.project_root / settings.alert_rules_path
    if not path.exists():
        return {"enabled": False, "rules": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"enabled": False, "rules": []}


def _rule_matches(rule: dict[str, Any], event: RiskEvent) -> bool:
    conditions = rule.get("conditions") or {}

    min_severity = conditions.get("min_severity")
    if min_severity is not None and event.severity_score < float(min_severity):
        return False

    min_source_count = conditions.get("min_source_count")
    if min_source_count is not None and event.source_count < int(min_source_count):
        return False

    min_verification = conditions.get("min_verification_score")
    if min_verification is not None and event.verification_score < float(min_verification):
        return False

    categories = conditions.get("event_categories")
    if categories and event.event_category.value not in categories:
        return False

    return True


def evaluate_alert_rules(event: RiskEvent) -> list[AlertRuleMatch]:
    """Evaluate config rules against an event. Returns matches only — no notifications."""
    config = _load_alert_config()
    if not config.get("enabled", False):
        return []

    matches: list[AlertRuleMatch] = []
    for rule in config.get("rules", []):
        if not rule.get("enabled", True):
            continue
        if _rule_matches(rule, event):
            matches.append(
                AlertRuleMatch(
                    rule_id=str(rule.get("id", "unknown")),
                    rule_name=str(rule.get("name", rule.get("id", "unknown"))),
                    match_metadata={
                        "description": rule.get("description", ""),
                        "conditions": rule.get("conditions", {}),
                        "severity_score": event.severity_score,
                        "source_count": event.source_count,
                        "verification_score": event.verification_score,
                    },
                )
            )
            logger.info(
                "Alert rule matched: rule_id=%s event_id=%s severity=%.1f",
                rule.get("id"),
                event.event_id,
                event.severity_score,
            )

    return matches


def invalidate_alert_config_cache() -> None:
    """Clear cached alert config (for tests)."""
    _load_alert_config.cache_clear()
