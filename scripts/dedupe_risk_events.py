#!/usr/bin/env python3
"""Remove duplicate risk_events from Supabase/Postgres and set event_fingerprint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.event_dedup import compute_event_fingerprint, dedupe_row_groups
from services.event_dedup_store import load_all_risk_events_for_cleanup


def _merge_child_rows_supabase(client, keeper_id: str, duplicate_id: str) -> None:
    for table in ("event_articles", "event_analyses", "event_predictions", "alert_matches"):
        resp = client.table(table).select("*").eq("event_id", duplicate_id).execute()
        for row in resp.data or []:
            payload = dict(row)
            payload["event_id"] = keeper_id
            payload.pop("id", None)
            try:
                if table == "event_articles":
                    client.table(table).upsert(
                        payload,
                        on_conflict="event_id,article_id",
                        ignore_duplicates=True,
                    ).execute()
                elif table in {"event_analyses", "event_predictions"}:
                    client.table(table).upsert(payload, on_conflict="event_id").execute()
                else:
                    client.table(table).insert(payload).execute()
            except Exception:
                pass


def _delete_event_supabase(client, event_id: str) -> None:
    client.table("risk_events").delete().eq("event_id", event_id).execute()


def _update_keeper_supabase(client, keeper: dict) -> None:
    event_id = keeper["event_id"]
    payload = {"event_fingerprint": keeper["event_fingerprint"]}
    try:
        client.table("risk_events").update(payload).eq("event_id", event_id).execute()
    except Exception:
        pass


def run_cleanup(*, dry_run: bool = False) -> dict:
    from db.persistence_backend import persistence_available, preferred_persistence_backend

    if not persistence_available():
        raise RuntimeError("No persistence backend configured")

    rows = load_all_risk_events_for_cleanup()
    keepers = dedupe_row_groups(rows)
    duplicate_ids: list[str] = []
    for keeper in keepers:
        duplicate_ids.extend(keeper.get("_duplicate_ids") or [])

    summary = {
        "total_before": len(rows),
        "unique_after": len(keepers),
        "duplicates_removed": len(duplicate_ids),
        "dry_run": dry_run,
    }

    if dry_run or not duplicate_ids:
        return summary

    backend = preferred_persistence_backend()
    if backend == "supabase_rest":
        from db.supabase import get_client

        client = get_client()
        id_to_keeper = {}
        for keeper in keepers:
            for dup_id in keeper.get("_duplicate_ids") or []:
                id_to_keeper[dup_id] = str(keeper["event_id"])

        for dup_id, keeper_id in id_to_keeper.items():
            _merge_child_rows_supabase(client, keeper_id, dup_id)
            _delete_event_supabase(client, dup_id)

        for keeper in keepers:
            _update_keeper_supabase(client, keeper)
    else:
        from db.postgres import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                for keeper in keepers:
                    keeper_id = keeper["event_id"]
                    for dup_id in keeper.get("_duplicate_ids") or []:
                        for table in ("event_articles", "alert_matches"):
                            cur.execute(
                                f"UPDATE {table} SET event_id = %s WHERE event_id = %s",
                                (keeper_id, dup_id),
                            )
                        cur.execute(
                            """
                            UPDATE event_analyses SET event_id = %s
                            WHERE event_id = %s
                              AND NOT EXISTS (
                                  SELECT 1 FROM event_analyses ea WHERE ea.event_id = %s
                              )
                            """,
                            (keeper_id, dup_id, keeper_id),
                        )
                        cur.execute(
                            """
                            UPDATE event_predictions SET event_id = %s
                            WHERE event_id = %s
                              AND NOT EXISTS (
                                  SELECT 1 FROM event_predictions ep WHERE ep.event_id = %s
                              )
                            """,
                            (keeper_id, dup_id, keeper_id),
                        )
                        cur.execute("DELETE FROM risk_events WHERE event_id = %s", (dup_id,))

                    try:
                        cur.execute(
                            """
                            UPDATE risk_events
                            SET event_fingerprint = %s, updated_at = NOW()
                            WHERE event_id = %s
                            """,
                            (keeper["event_fingerprint"], keeper_id),
                        )
                    except Exception:
                        conn.rollback()

    return summary


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    result = run_cleanup(dry_run=dry_run)
    print(json.dumps(result, indent=2))
