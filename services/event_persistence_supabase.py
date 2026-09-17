"""Persist risk events via Supabase REST (PostgREST over HTTPS)."""

from __future__ import annotations

import logging
from typing import Any

from db.supabase import get_client
from models.schemas import RiskEvent
from services.alert_evaluator import evaluate_alert_rules
from services.event_dedup import compute_event_fingerprint, resolve_events_for_persist
from services.event_dedup_store import load_existing_risk_event_index
from services.event_storage import (
    linked_entities_payload,
    persisted_supply_chain_links,
    prepare_risk_event_for_persistence,
)
from services.event_storage import (
    linked_entities_payload,
    persisted_supply_chain_links,
    prepare_risk_event_for_persistence,
)

logger = logging.getLogger("news_agent.services.event_persistence_supabase")

_INTELLIGENCE_TABLES = (
    "risk_events",
    "event_articles",
    "event_status_history",
    "alert_matches",
    "event_analyses",
    "event_predictions",
)


def _migration_file_for_missing(missing: list[str]) -> str:
    core = {"risk_events", "event_articles", "event_status_history", "alert_matches"}
    missing_set = set(missing)
    if missing_set == {"event_analyses"}:
        return "002_event_analyses.sql"
    if missing_set == {"event_predictions"}:
        return "003_event_predictions.sql"
    if missing_set <= {"event_analyses", "event_predictions"}:
        return "002_event_analyses.sql and 003_event_predictions.sql"
    if any(table in core for table in missing):
        return "001_risk_intelligence_schema.sql"
    return "001_risk_intelligence_schema.sql"


def verify_intelligence_schema() -> dict[str, Any]:
    """
    Check that intelligence tables exist by probing the REST API.

    DDL cannot run over PostgREST — if tables are missing, returns instructions
    to apply migrations/001_risk_intelligence_schema.sql in Supabase SQL Editor.
    """
    client = get_client()
    missing: list[str] = []

    for table in _INTELLIGENCE_TABLES:
        try:
            client.table(table).select("*").limit(1).execute()
        except Exception as exc:
            err = str(exc)
            if "PGRST205" in err or "does not exist" in err.lower():
                missing.append(table)
            else:
                raise

    if missing:
        migration_file = _migration_file_for_missing(missing)
        return {
            "schema_ready": False,
            "missing_tables": missing,
            "message": (
                "Some intelligence tables are missing. Open Supabase Dashboard -> "
                f"SQL Editor, paste migrations/{migration_file}, and run it."
            ),
            "migration_file": migration_file,
        }

    return {"schema_ready": True, "missing_tables": [], "backend": "supabase_rest"}


def _linked_entities_payload(event: RiskEvent) -> dict[str, Any]:
    return linked_entities_payload(event)


def _risk_event_row(event: RiskEvent, run_id: str) -> dict[str, Any]:
    event = prepare_risk_event_for_persistence(event)
    severity_payload = event.severity_signal.model_dump(mode="json")
    severity_payload["overall_confidence"] = event.overall_confidence
    severity_payload["explainability"] = event.explainability.model_dump(mode="json")
    category = (
        event.event_category.value
        if hasattr(event.event_category, "value")
        else str(event.event_category)
    )
    row = {
        "event_id": event.event_id,
        "run_id": run_id,
        "cluster_id": event.cluster_id,
        "title": event.title,
        "summary": event.summary,
        "event_type": event.event_type,
        "event_category": category,
        "classification_confidence": event.classification_confidence,
        "severity_score": event.severity_score,
        "severity_signal": severity_payload,
        "status": event.status.value,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "geo_country": event.geo_country,
        "geo_region": event.geo_region,
        "source_count": event.source_count,
        "verification_score": event.verification_score,
        "linked_entities": _linked_entities_payload(event),
        "supply_chain_links": persisted_supply_chain_links(event),
        "provenance": event.provenance_information.model_dump(mode="json"),
        "pipeline_version": event.provenance_information.pipeline_version,
        "retrieval_timestamp": event.retrieval_timestamp.isoformat(),
        "event_fingerprint": compute_event_fingerprint(
            event.title, category, event.geo_country
        ),
    }
    return row


def _article_id_from_source(event: RiskEvent, source_metadata: dict[str, Any]) -> str:
    article_id = source_metadata.get("article_id")
    if article_id:
        return str(article_id)
    if event.article_ids:
        return event.article_ids[0]
    return event.event_id


def _persist_event_analysis_supabase(client, event: RiskEvent) -> bool:
    analysis = event.risk_analysis
    if not analysis or analysis.skipped:
        return False

    client.table("event_analyses").upsert(
        {
            "event_id": event.event_id,
            "analysis": analysis.model_dump(mode="json"),
            "model_used": analysis.model_used,
            "analysis_confidence": analysis.analysis_confidence,
            "generated_at": analysis.generated_at.isoformat(),
        },
        on_conflict="event_id",
    ).execute()
    return True


def _persist_event_prediction_supabase(client, event: RiskEvent) -> bool:
    prediction = event.impact_prediction
    if not prediction or prediction.skipped:
        return False

    client.table("event_predictions").upsert(
        {
            "event_id": event.event_id,
            "prediction": prediction.model_dump(mode="json"),
            "prediction_confidence": prediction.prediction_confidence,
            "prediction_method": prediction.prediction_method,
            "generated_at": prediction.generated_at.isoformat(),
        },
        on_conflict="event_id",
    ).execute()
    return True


def persist_risk_events_supabase(
    run_id: str,
    events: list[RiskEvent],
    *,
    evaluate_alerts: bool = True,
) -> dict[str, Any]:
    """Write risk events and related rows through Supabase REST."""
    schema = verify_intelligence_schema()
    if not schema.get("schema_ready"):
        raise RuntimeError(schema.get("message", "Intelligence schema not ready"))

    client = get_client()
    existing_rows = load_existing_risk_event_index()
    events, dedup_stats = resolve_events_for_persist(events, existing_rows)

    persisted = 0
    alert_match_count = 0
    analyses_persisted = 0
    predictions_persisted = 0

    for event in events:
        row = _risk_event_row(event, run_id)
        try:
            client.table("risk_events").upsert(row, on_conflict="event_id").execute()
        except Exception as exc:
            if "event_fingerprint" in str(exc):
                row.pop("event_fingerprint", None)
                client.table("risk_events").upsert(row, on_conflict="event_id").execute()
            else:
                raise

        client.table("event_status_history").insert(
            {
                "event_id": event.event_id,
                "status": event.status.value,
                "metadata": {
                    "run_id": run_id,
                    "action": "updated" if event.status.value == "updated" else "persisted",
                },
            }
        ).execute()

        article_rows = []
        for source in event.provenance_information.sources:
            retrieved = source.retrieved_at.isoformat() if source.retrieved_at else None
            article_rows.append(
                {
                    "event_id": event.event_id,
                    "article_id": _article_id_from_source(event, source.raw_metadata),
                    "provider": source.provider,
                    "title": event.title,
                    "url": source.url,
                    "reliability_tier": source.reliability_tier,
                    "provider_metadata": source.raw_metadata,
                    "retrieved_at": retrieved,
                }
            )
        if article_rows:
            client.table("event_articles").upsert(
                article_rows,
                on_conflict="event_id,article_id",
                ignore_duplicates=True,
            ).execute()

        if evaluate_alerts:
            alert_rows = []
            for match in evaluate_alert_rules(event):
                alert_rows.append(
                    {
                        "event_id": event.event_id,
                        "rule_id": match.rule_id,
                        "rule_name": match.rule_name,
                        "match_metadata": match.match_metadata,
                    }
                )
                alert_match_count += 1
            if alert_rows:
                client.table("alert_matches").insert(alert_rows).execute()

        if _persist_event_analysis_supabase(client, event):
            analyses_persisted += 1

        if _persist_event_prediction_supabase(client, event):
            predictions_persisted += 1

        persisted += 1

    logger.info(
        "Persisted %d risk events via Supabase REST (run_id=%s, created=%d, updated=%d, "
        "batch_deduped=%d, alert_matches=%d, analyses=%d, predictions=%d)",
        persisted,
        run_id,
        dedup_stats.get("created", 0),
        dedup_stats.get("updated", 0),
        dedup_stats.get("deduplicated_in_batch", 0),
        alert_match_count,
        analyses_persisted,
        predictions_persisted,
    )
    return {
        "persisted": persisted,
        "skipped": 0,
        "created": dedup_stats.get("created", 0),
        "updated": dedup_stats.get("updated", 0),
        "deduplicated_in_batch": dedup_stats.get("deduplicated_in_batch", 0),
        "alert_matches": alert_match_count,
        "analyses_persisted": analyses_persisted,
        "predictions_persisted": predictions_persisted,
        "database": "supabase_rest",
    }
