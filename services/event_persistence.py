"""Persist risk events — Supabase REST (primary) or direct Postgres (fallback)."""

from __future__ import annotations

import json
import logging
from typing import Any

from db.persistence_backend import (
    persistence_available,
    preferred_persistence_backend,
    supabase_rest_available,
)
from db.postgres import get_connection, postgres_available
from models.schemas import RiskEvent
from services.alert_evaluator import evaluate_alert_rules
from services.event_dedup import compute_event_fingerprint, resolve_events_for_persist
from services.event_dedup_store import load_existing_risk_event_index
from services.event_persistence_supabase import persist_risk_events_supabase
from services.event_storage import (
    linked_entities_payload,
    persisted_supply_chain_links,
    prepare_risk_event_for_persistence,
)

logger = logging.getLogger("news_agent.services.event_persistence")


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _linked_entities_payload(event: RiskEvent) -> dict[str, Any]:
    return linked_entities_payload(event)


def _article_id_from_source(event: RiskEvent, source_metadata: dict[str, Any]) -> str:
    article_id = source_metadata.get("article_id")
    if article_id:
        return str(article_id)
    if event.article_ids:
        return event.article_ids[0]
    return event.event_id


def _persist_event_analysis_postgres(cur, event: RiskEvent) -> bool:
    analysis = event.risk_analysis
    if not analysis or analysis.skipped:
        return False

    cur.execute(
        """
        INSERT INTO event_analyses (
            event_id, analysis, model_used, analysis_confidence, generated_at
        ) VALUES (%s, %s::jsonb, %s, %s, %s)
        ON CONFLICT (event_id) DO UPDATE SET
            analysis = EXCLUDED.analysis,
            model_used = EXCLUDED.model_used,
            analysis_confidence = EXCLUDED.analysis_confidence,
            generated_at = EXCLUDED.generated_at
        """,
        (
            event.event_id,
            _json(analysis.model_dump(mode="json")),
            analysis.model_used,
            analysis.analysis_confidence,
            analysis.generated_at,
        ),
    )
    return True


def _persist_event_prediction_postgres(cur, event: RiskEvent) -> bool:
    prediction = event.impact_prediction
    if not prediction or prediction.skipped:
        return False

    cur.execute(
        """
        INSERT INTO event_predictions (
            event_id, prediction, prediction_confidence, prediction_method, generated_at
        ) VALUES (%s, %s::jsonb, %s, %s, %s)
        ON CONFLICT (event_id) DO UPDATE SET
            prediction = EXCLUDED.prediction,
            prediction_confidence = EXCLUDED.prediction_confidence,
            prediction_method = EXCLUDED.prediction_method,
            generated_at = EXCLUDED.generated_at
        """,
        (
            event.event_id,
            _json(prediction.model_dump(mode="json")),
            prediction.prediction_confidence,
            prediction.prediction_method,
            prediction.generated_at,
        ),
    )
    return True


def _persist_risk_events_postgres(
    run_id: str,
    events: list[RiskEvent],
    *,
    evaluate_alerts: bool = True,
) -> dict[str, Any]:
    """Direct Postgres persistence (when DATABASE_URL is reachable)."""
    persisted = 0
    alert_match_count = 0
    analyses_persisted = 0
    predictions_persisted = 0

    existing_rows = load_existing_risk_event_index()
    events, dedup_stats = resolve_events_for_persist(events, existing_rows)

    with get_connection() as conn:
        with conn.cursor() as cur:
            for event in events:
                event = prepare_risk_event_for_persistence(event)
                category = event.event_category.value
                fingerprint = compute_event_fingerprint(
                    event.title, category, event.geo_country
                )
                cur.execute(
                    """
                    INSERT INTO risk_events (
                        event_id, run_id, cluster_id, title, summary,
                        event_type, event_category, classification_confidence,
                        severity_score, severity_signal, status,
                        latitude, longitude, geo_country, geo_region,
                        source_count, verification_score,
                        linked_entities, supply_chain_links, provenance, pipeline_version,
                        retrieval_timestamp, event_fingerprint, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s::jsonb, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s,
                        %s, %s, NOW()
                    )
                    ON CONFLICT (event_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        severity_score = EXCLUDED.severity_score,
                        severity_signal = EXCLUDED.severity_signal,
                        status = EXCLUDED.status,
                        source_count = EXCLUDED.source_count,
                        verification_score = EXCLUDED.verification_score,
                        linked_entities = EXCLUDED.linked_entities,
                        supply_chain_links = EXCLUDED.supply_chain_links,
                        provenance = EXCLUDED.provenance,
                        run_id = EXCLUDED.run_id,
                        event_fingerprint = EXCLUDED.event_fingerprint,
                        updated_at = NOW()
                    """,
                    (
                        event.event_id,
                        run_id,
                        event.cluster_id,
                        event.title,
                        event.summary,
                        event.event_type,
                        category,
                        event.classification_confidence,
                        event.severity_score,
                        _json(event.severity_signal.model_dump(mode="json")),
                        event.status.value,
                        event.latitude,
                        event.longitude,
                        event.geo_country,
                        event.geo_region,
                        event.source_count,
                        event.verification_score,
                        _json(_linked_entities_payload(event)),
                        _json(persisted_supply_chain_links(event)),
                        _json(event.provenance_information.model_dump(mode="json")),
                        event.provenance_information.pipeline_version,
                        event.retrieval_timestamp,
                        fingerprint,
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO event_status_history (event_id, status, metadata)
                    VALUES (%s, %s, %s::jsonb)
                    """,
                    (
                        event.event_id,
                        event.status.value,
                        _json(
                            {
                                "run_id": run_id,
                                "action": "updated"
                                if event.status.value == "updated"
                                else "persisted",
                            }
                        ),
                    ),
                )

                for source in event.provenance_information.sources:
                    article_id = _article_id_from_source(event, source.raw_metadata)
                    cur.execute(
                        """
                        INSERT INTO event_articles (
                            event_id, article_id, provider, title, url,
                            reliability_tier, provider_metadata, retrieved_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        ON CONFLICT (event_id, article_id) DO NOTHING
                        """,
                        (
                            event.event_id,
                            article_id,
                            source.provider,
                            event.title,
                            source.url,
                            source.reliability_tier,
                            _json(source.raw_metadata),
                            source.retrieved_at,
                        ),
                    )

                if evaluate_alerts:
                    for match in evaluate_alert_rules(event):
                        cur.execute(
                            """
                            INSERT INTO alert_matches (
                                event_id, rule_id, rule_name, match_metadata
                            ) VALUES (%s, %s, %s, %s::jsonb)
                            """,
                            (
                                event.event_id,
                                match.rule_id,
                                match.rule_name,
                                _json(match.match_metadata),
                            ),
                        )
                        alert_match_count += 1

                if _persist_event_analysis_postgres(cur, event):
                    analyses_persisted += 1

                if _persist_event_prediction_postgres(cur, event):
                    predictions_persisted += 1

                persisted += 1

    return {
        "persisted": persisted,
        "skipped": 0,
        "created": dedup_stats.get("created", 0),
        "updated": dedup_stats.get("updated", 0),
        "deduplicated_in_batch": dedup_stats.get("deduplicated_in_batch", 0),
        "alert_matches": alert_match_count,
        "analyses_persisted": analyses_persisted,
        "predictions_persisted": predictions_persisted,
        "database": "postgres",
    }


def persist_risk_events(
    run_id: str,
    events: list[RiskEvent],
    *,
    evaluate_alerts: bool = True,
) -> dict[str, Any]:
    """
    Persist risk events using Supabase REST when configured, else direct Postgres.

    Supabase REST uses HTTPS (port 443) and works when Postgres ports are blocked.
    """
    from config.settings import settings

    if not events:
        return {"persisted": 0, "skipped": 0, "alert_matches": 0, "database": "empty"}

    if not persistence_available():
        message = (
            "No persistence backend configured. Set SUPABASE_URL + SUPABASE_KEY "
            "or DATABASE_URL in .env"
        )
        if settings.persist_require_db:
            raise RuntimeError(message)
        logger.warning(message)
        return {"persisted": 0, "skipped": len(events), "alert_matches": 0, "database": "unavailable"}

    backend = preferred_persistence_backend()
    if backend == "supabase_rest":
        try:
            return persist_risk_events_supabase(
                run_id, events, evaluate_alerts=evaluate_alerts
            )
        except Exception as exc:
            if settings.persist_require_db:
                raise
            logger.warning("Supabase REST persistence failed: %s", exc)
            if postgres_available() and settings.persist_fallback_postgres:
                logger.info("Falling back to direct Postgres persistence")
                try:
                    return _persist_risk_events_postgres(
                        run_id, events, evaluate_alerts=evaluate_alerts
                    )
                except Exception as pg_exc:
                    logger.warning("Postgres fallback also failed: %s", pg_exc)
            return {
                "persisted": 0,
                "skipped": len(events),
                "alert_matches": 0,
                "database": "supabase_rest",
                "error": str(exc),
            }

    return _persist_risk_events_postgres(run_id, events, evaluate_alerts=evaluate_alerts)
