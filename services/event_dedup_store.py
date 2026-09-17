"""Load existing risk events for dedup resolution."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("news_agent.services.event_dedup_store")


def load_existing_risk_event_index() -> list[dict[str, Any]]:
    """Fetch minimal fields needed for cross-run deduplication."""
    from db.persistence_backend import persistence_available, preferred_persistence_backend

    if not persistence_available():
        return []

    backend = preferred_persistence_backend()
    if backend == "supabase_rest":
        return _load_index_supabase()
    return _load_index_postgres()


def _load_index_supabase() -> list[dict[str, Any]]:
    from db.supabase import get_client

    client = get_client()
    columns = "event_id,title,event_category,geo_country,event_fingerprint,severity_score,retrieval_timestamp"
    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 1000

    while True:
        end = start + page_size - 1
        try:
            resp = (
                client.table("risk_events")
                .select(columns)
                .range(start, end)
                .execute()
            )
        except Exception as exc:
            if "event_fingerprint" in str(exc):
                resp = (
                    client.table("risk_events")
                    .select("event_id,title,event_category,geo_country,severity_score,retrieval_timestamp")
                    .range(start, end)
                    .execute()
                )
            else:
                raise

        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    logger.info("Loaded %d existing risk events for dedup index", len(rows))
    return rows


def _load_index_postgres() -> list[dict[str, Any]]:
    from db.postgres import get_connection

    rows: list[dict[str, Any]] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT event_id, title, event_category, geo_country,
                           event_fingerprint, severity_score, retrieval_timestamp
                    FROM risk_events
                    """
                )
            except Exception:
                conn.rollback()
                cur.execute(
                    """
                    SELECT event_id, title, event_category, geo_country,
                           severity_score, retrieval_timestamp
                    FROM risk_events
                    """
                )
            columns = [desc[0] for desc in cur.description]
            for record in cur.fetchall():
                rows.append(dict(zip(columns, record)))
    logger.info("Loaded %d existing risk events for dedup index", len(rows))
    return rows


def load_all_risk_events_for_cleanup() -> list[dict[str, Any]]:
    from db.persistence_backend import persistence_available, preferred_persistence_backend

    if not persistence_available():
        return []

    if preferred_persistence_backend() == "supabase_rest":
        from db.supabase import get_client

        client = get_client()
        rows: list[dict[str, Any]] = []
        start = 0
        page_size = 1000
        while True:
            end = start + page_size - 1
            resp = client.table("risk_events").select("*").range(start, end).execute()
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size
        return rows

    from db.postgres import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM risk_events")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
