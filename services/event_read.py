"""Read risk intelligence events for SiaEye (Supabase REST or local JSON fallback)."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import settings
from services.display_format import format_geo_label, sanitize_event_for_display
from services.event_dedup import dedupe_row_groups, fingerprint_for_row
from services.news_summary import summary_preview
from services.event_storage import resolve_stored_supply_chain_links
from services.supply_chain_links import link_names

logger = logging.getLogger("news_agent.services.event_read")


def _resolve_event_supply_chain(
    event: dict[str, Any],
    *,
    linked: dict[str, Any] | None = None,
    allow_catalog_enrich: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    linked_payload = linked or {
        "linked_components": event.get("linked_components"),
        "linked_suppliers": event.get("linked_suppliers"),
        "linked_manufacturers": event.get("linked_manufacturers"),
        "linked_locations": event.get("linked_locations"),
    }
    return resolve_stored_supply_chain_links(
        supply_chain_links=event.get("supply_chain_links"),
        linked=linked_payload,
        risk_analysis=event.get("risk_analysis"),
        allow_catalog_enrich=allow_catalog_enrich,
    )


def _fetch_related_event_ids(table: str) -> set[str]:
    """Load event_ids that have rows in event_analyses / event_predictions."""
    try:
        from db.persistence_backend import persistence_available, preferred_persistence_backend

        if not persistence_available():
            return set()

        if preferred_persistence_backend() == "supabase_rest":
            from db.supabase import get_client

            client = get_client()
            ids: set[str] = set()
            start = 0
            page_size = 1000
            while True:
                end = start + page_size - 1
                resp = client.table(table).select("event_id").range(start, end).execute()
                batch = resp.data or []
                ids.update(str(row["event_id"]) for row in batch if row.get("event_id"))
                if len(batch) < page_size:
                    break
                start += page_size
            return ids

        from db.postgres import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT event_id FROM {table}")
                return {str(row[0]) for row in cur.fetchall()}
    except Exception as exc:
        logger.debug("Could not load related ids from %s: %s", table, exc)
        return set()


def _intelligence_flags_for_events(
    events: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    analysis_ids = _fetch_related_event_ids("event_analyses")
    prediction_ids = _fetch_related_event_ids("event_predictions")
    if analysis_ids or prediction_ids:
        return analysis_ids, prediction_ids

    # Local JSON fallback — flags are inline on each event
    analysis_ids = {
        str(event["event_id"])
        for event in events
        if event.get("risk_analysis") and not (event.get("risk_analysis") or {}).get("skipped")
    }
    prediction_ids = {
        str(event["event_id"])
        for event in events
        if event.get("impact_prediction") and not (event.get("impact_prediction") or {}).get("skipped")
    }
    return analysis_ids, prediction_ids


def _severity_signal_from_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("severity_signal") or {})
    payload.pop("overall_confidence", None)
    payload.pop("explainability", None)
    if "severity_score" not in payload:
        payload["severity_score"] = row.get("severity_score", 0.0)
    return payload


def _explainability_from_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("severity_signal") or {}
    return dict(payload.get("explainability") or {})


def _overall_confidence_from_row(row: dict[str, Any]) -> float:
    payload = row.get("severity_signal") or {}
    value = payload.get("overall_confidence")
    if value is not None:
        return float(value)
    return 0.0


def _linked_entities_from_row(row: dict[str, Any]) -> dict[str, Any]:
    linked = row.get("linked_entities") or {}
    return {
        "extracted_entities": linked.get("extracted_entities") or [],
        "linked_manufacturers": linked.get("linked_manufacturers") or [],
        "linked_suppliers": linked.get("linked_suppliers") or [],
        "linked_locations": linked.get("linked_locations") or [],
        "linked_components": linked.get("linked_components") or [],
    }


def _ensure_supply_chain_links(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    linked_payload, links = _resolve_event_supply_chain(payload)
    for key in (
        "linked_components",
        "linked_suppliers",
        "linked_manufacturers",
        "linked_locations",
    ):
        payload[key] = linked_payload.get(key) or payload.get(key) or []
    payload["supply_chain_links"] = links
    return payload


def rehydrate_event_row(
    row: dict[str, Any],
    *,
    analysis: dict[str, Any] | None = None,
    prediction: dict[str, Any] | None = None,
    articles: list[dict[str, Any]] | None = None,
    alerts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert a persisted risk_events row into CLI / result.json shape."""
    linked = _linked_entities_from_row(row)
    supply_chain_links = row.get("supply_chain_links") or {}
    provenance = row.get("provenance") or {}
    article_rows = articles or []

    source_urls = [a.get("url") for a in article_rows if a.get("url")]
    if not source_urls:
        for source in provenance.get("sources") or []:
            url = source.get("url")
            if url:
                source_urls.append(url)

    article_ids = [a.get("article_id") for a in article_rows if a.get("article_id")]

    event: dict[str, Any] = {
        "event_id": row.get("event_id"),
        "title": row.get("title") or "",
        "summary": row.get("summary") or "",
        "event_type": row.get("event_type") or "unknown",
        "event_category": row.get("event_category") or "other",
        "classification_confidence": row.get("classification_confidence") or 0.0,
        "severity_signal": _severity_signal_from_row(row),
        "severity_score": row.get("severity_score") or 0.0,
        **linked,
        "supply_chain_links": supply_chain_links,
        "cluster_id": row.get("cluster_id"),
        "source_urls": source_urls,
        "source_count": row.get("source_count") or len(source_urls) or 1,
        "verification_score": row.get("verification_score") or 0.0,
        "article_ids": article_ids,
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "geo_country": row.get("geo_country"),
        "geo_region": row.get("geo_region"),
        "status": row.get("status") or "detected",
        "overall_confidence": _overall_confidence_from_row(row),
        "explainability": _explainability_from_row(row),
        "retrieval_timestamp": row.get("retrieval_timestamp"),
        "provenance_information": provenance,
        "run_id": row.get("run_id"),
        "pipeline_version": row.get("pipeline_version"),
    }

    if analysis:
        event["risk_analysis"] = analysis.get("analysis") or analysis
    else:
        event["risk_analysis"] = None

    if prediction:
        event["impact_prediction"] = prediction.get("prediction") or prediction
    else:
        event["impact_prediction"] = None

    if alerts:
        event["alert_matches"] = alerts

    enriched_linked, resolved_links = _resolve_event_supply_chain(
        event,
        linked=linked,
    )
    for key in (
        "linked_components",
        "linked_suppliers",
        "linked_manufacturers",
        "linked_locations",
    ):
        event[key] = enriched_linked.get(key) or []

    event["supply_chain_links"] = resolved_links

    return sanitize_event_for_display(event)


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate stories (defensive read-path dedup)."""
    if not events:
        return events
    keepers = dedupe_row_groups(events)
    deduped: list[dict[str, Any]] = []
    for keeper in keepers:
        item = {key: value for key, value in keeper.items() if not key.startswith("_")}
        item["event_fingerprint"] = keeper.get("event_fingerprint") or fingerprint_for_row(item)
        deduped.append(item)
    return deduped


def _list_item_from_event(
    event: dict[str, Any],
    *,
    analysis_ids: set[str] | None = None,
    prediction_ids: set[str] | None = None,
) -> dict[str, Any]:
    event_id = str(event.get("event_id") or "")
    risk_analysis = event.get("risk_analysis")
    impact_prediction = event.get("impact_prediction")
    has_analysis = bool(risk_analysis and not risk_analysis.get("skipped"))
    has_prediction = bool(impact_prediction and not impact_prediction.get("skipped"))
    if analysis_ids is not None:
        has_analysis = has_analysis or event_id in analysis_ids
    if prediction_ids is not None:
        has_prediction = has_prediction or event_id in prediction_ids

    _, links = _resolve_event_supply_chain(event)

    return {
        "event_id": event.get("event_id"),
        "title": event.get("title"),
        "summary": summary_preview(event.get("summary")),
        "event_type": event.get("event_type"),
        "event_category": event.get("event_category"),
        "severity_score": event.get("severity_score"),
        "status": event.get("status"),
        "overall_confidence": event.get("overall_confidence"),
        "geo_country": format_geo_label(event.get("geo_country")),
        "geo_region": format_geo_label(event.get("geo_region")),
        "latitude": event.get("latitude"),
        "longitude": event.get("longitude"),
        "source_count": event.get("source_count"),
        "retrieval_timestamp": event.get("retrieval_timestamp"),
        "run_id": event.get("run_id"),
        "has_risk_analysis": has_analysis,
        "has_impact_prediction": has_prediction,
        "supply_chain_links": links,
        "linked_components": link_names(links, "components"),
        "linked_suppliers": link_names(links, "distributors"),
        "linked_manufacturers": link_names(links, "manufacturers"),
        "affected_manufacturers": link_names(links, "affected_manufacturers"),
        "linked_locations": link_names(links, "locations"),
    }


def _matches_filters(
    event: dict[str, Any],
    *,
    category: str | None,
    min_severity: float | None,
    status: str | None,
    search: str | None,
    run_id: str | None,
) -> bool:
    if category and event.get("event_category") != category:
        return False
    if min_severity is not None and float(event.get("severity_score") or 0) < min_severity:
        return False
    if status and event.get("status") != status:
        return False
    if run_id and event.get("run_id") != run_id:
        return False
    if search:
        needle = search.lower()
        haystack = " ".join(
            [
                str(event.get("title") or ""),
                str(event.get("summary") or ""),
                str(event.get("geo_country") or ""),
                str(event.get("event_type") or ""),
            ]
        ).lower()
        if needle not in haystack:
            return False
    return True


def _empty_local_snapshot() -> dict[str, Any]:
    return {
        "run_id": None,
        "pipeline_version": settings.pipeline_version,
        "risk_events": [],
        "filtered_out_count": 0,
    }


@lru_cache(maxsize=1)
def _load_local_snapshot(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        return _empty_local_snapshot()
    try:
        raw = file_path.read_text(encoding="utf-8").strip()
        if not raw:
            logger.warning("Local snapshot %s is empty; using empty event list", file_path)
            return _empty_local_snapshot()
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Local snapshot %s is invalid JSON (%s); using empty event list",
            file_path,
            exc,
        )
        return _empty_local_snapshot()
    if not isinstance(payload, dict):
        logger.warning("Local snapshot %s is not a JSON object; using empty event list", file_path)
        return _empty_local_snapshot()
    events = payload.get("risk_events") or []
    run_id = payload.get("run_id")
    for event in events:
        if isinstance(event, dict):
            event.setdefault("run_id", run_id)
    return payload


class EventReadService:
    """Unified read path for SiaEye dashboards."""

    def __init__(self) -> None:
        path = settings.siaeye_result_json_path
        self._local_path = path if path.is_absolute() else settings.project_root / path

    @property
    def backend(self) -> str:
        if settings.supabase_url and settings.supabase_key:
            return "supabase_rest"
        return "local_json"

    def _supabase_client(self):
        from db.supabase import get_client

        return get_client()

    def _fetch_supabase_events(self) -> list[dict[str, Any]]:
        client = self._supabase_client()
        resp = (
            client.table("risk_events")
            .select("*")
            .order("severity_score", desc=True)
            .execute()
        )
        rows = resp.data or []
        events = _dedupe_events([rehydrate_event_row(row) for row in rows])
        return events

    def _fetch_supabase_event(self, event_id: str) -> dict[str, Any] | None:
        client = self._supabase_client()
        resp = (
            client.table("risk_events")
            .select("*")
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]

        analysis_resp = (
            client.table("event_analyses")
            .select("*")
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        prediction_resp = (
            client.table("event_predictions")
            .select("*")
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        articles_resp = (
            client.table("event_articles")
            .select("*")
            .eq("event_id", event_id)
            .execute()
        )
        alerts_resp = (
            client.table("alert_matches")
            .select("*")
            .eq("event_id", event_id)
            .execute()
        )

        analysis_row = (analysis_resp.data or [None])[0]
        prediction_row = (prediction_resp.data or [None])[0]

        return rehydrate_event_row(
            row,
            analysis=analysis_row,
            prediction=prediction_row,
            articles=articles_resp.data or [],
            alerts=alerts_resp.data or [],
        )

    def _local_events(self) -> list[dict[str, Any]]:
        snapshot = _load_local_snapshot(str(self._local_path.resolve()))
        return _dedupe_events(snapshot.get("risk_events") or [])

    def _local_snapshot_meta(self) -> dict[str, Any]:
        snapshot = _load_local_snapshot(str(self._local_path.resolve()))
        return {
            "run_id": snapshot.get("run_id"),
            "pipeline_version": snapshot.get("pipeline_version") or settings.pipeline_version,
            "filtered_out_count": snapshot.get("filtered_out_count", 0),
        }

    def list_events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        category: str | None = None,
        min_severity: float | None = None,
        status: str | None = None,
        search: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            if self.backend == "supabase_rest":
                events = self._fetch_supabase_events()
            else:
                events = self._local_events()
        except Exception as exc:
            logger.warning("Primary backend failed (%s); falling back to local JSON", exc)
            events = self._local_events()

        filtered = [
            event
            for event in events
            if _matches_filters(
                event,
                category=category,
                min_severity=min_severity,
                status=status,
                search=search,
                run_id=run_id,
            )
        ]
        filtered.sort(key=lambda item: float(item.get("severity_score") or 0), reverse=True)
        total = len(filtered)
        page = filtered[offset : offset + limit]
        analysis_ids, prediction_ids = _intelligence_flags_for_events(events)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "backend": self.backend,
            "items": [
                _list_item_from_event(
                    event,
                    analysis_ids=analysis_ids,
                    prediction_ids=prediction_ids,
                )
                for event in page
            ],
        }

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        try:
            if self.backend == "supabase_rest":
                event = self._fetch_supabase_event(event_id)
                if event:
                    return event
        except Exception as exc:
            logger.warning("Supabase detail fetch failed (%s); trying local JSON", exc)

        for event in self._local_events():
            if event.get("event_id") == event_id:
                return sanitize_event_for_display(_ensure_supply_chain_links(event))
        return None

    def list_runs(self) -> list[dict[str, Any]]:
        if self.backend == "supabase_rest":
            try:
                events = self._fetch_supabase_events()
            except Exception as exc:
                logger.warning("Supabase runs fetch failed (%s); falling back to local JSON", exc)
                events = self._local_events()
        else:
            events = self._local_events()

        runs: dict[str, dict[str, Any]] = {}
        for event in events:
            run = event.get("run_id") or "unknown"
            bucket = runs.setdefault(
                run,
                {"run_id": run, "event_count": 0, "max_severity": 0.0},
            )
            bucket["event_count"] += 1
            bucket["max_severity"] = max(
                bucket["max_severity"],
                float(event.get("severity_score") or 0),
            )
        return sorted(runs.values(), key=lambda item: item["run_id"], reverse=True)

    def summary_stats(self) -> dict[str, Any]:
        try:
            events = (
                self._fetch_supabase_events()
                if self.backend == "supabase_rest"
                else self._local_events()
            )
        except Exception:
            events = self._local_events()

        if not events:
            meta = self._local_snapshot_meta()
            return {
                "total_events": 0,
                "avg_severity": 0.0,
                "max_severity": 0.0,
                "categories": {},
                "statuses": {},
                "with_analysis": 0,
                "with_prediction": 0,
                "backend": self.backend,
                **meta,
            }

        categories: dict[str, int] = {}
        statuses: dict[str, int] = {}
        severities: list[float] = []
        analysis_ids, prediction_ids = _intelligence_flags_for_events(events)

        for event in events:
            cat = str(event.get("event_category") or "other")
            categories[cat] = categories.get(cat, 0) + 1
            st = str(event.get("status") or "detected")
            statuses[st] = statuses.get(st, 0) + 1
            severities.append(float(event.get("severity_score") or 0))

        event_ids = {str(event.get("event_id") or "") for event in events}
        with_analysis = len(event_ids & analysis_ids)
        with_prediction = len(event_ids & prediction_ids)

        meta = self._local_snapshot_meta()
        return {
            "total_events": len(events),
            "avg_severity": round(sum(severities) / len(severities), 1),
            "max_severity": max(severities),
            "categories": categories,
            "statuses": statuses,
            "with_analysis": with_analysis,
            "with_prediction": with_prediction,
            "backend": self.backend,
            **meta,
        }

    def geo_points(self, *, min_severity: float = 0.0) -> list[dict[str, Any]]:
        try:
            events = (
                self._fetch_supabase_events()
                if self.backend == "supabase_rest"
                else self._local_events()
            )
        except Exception:
            events = self._local_events()

        points = []
        for event in events:
            if float(event.get("severity_score") or 0) < min_severity:
                continue
            lat = event.get("latitude")
            lon = event.get("longitude")
            if lat is None or lon is None:
                continue
            points.append(
                {
                    "event_id": event.get("event_id"),
                    "title": event.get("title"),
                    "severity_score": event.get("severity_score"),
                    "latitude": lat,
                    "longitude": lon,
                    "geo_country": event.get("geo_country"),
                    "event_category": event.get("event_category"),
                }
            )
        return points
