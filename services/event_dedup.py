"""Cross-run event deduplication — stable fingerprints and identity resolution."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from rapidfuzz import fuzz

from models.schemas import EventLifecycleStatus, RiskEvent

_DEDUP_NAMESPACE = NAMESPACE_URL
_TITLE_FUZZ_THRESHOLD = 88.0


def normalize_title(title: str) -> str:
    text = (title or "").lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_geo(geo_country: str | None) -> str:
    if not geo_country:
        return ""
    text = str(geo_country).lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_event_fingerprint(
    title: str,
    event_category: str,
    geo_country: str | None = None,
) -> str:
    """Stable hash for the same story across ingest runs."""
    parts = [
        normalize_title(title),
        (event_category or "other").lower().strip(),
        _normalize_geo(geo_country),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_event_id(fingerprint: str) -> str:
    """Deterministic event_id so upserts merge instead of duplicating."""
    return str(uuid5(_DEDUP_NAMESPACE, fingerprint))


def assign_stable_identity(event: RiskEvent) -> str:
    """Set event_id from title/category/geo fingerprint."""
    category = (
        event.event_category.value
        if hasattr(event.event_category, "value")
        else str(event.event_category)
    )
    fingerprint = compute_event_fingerprint(event.title, category, event.geo_country)
    event.event_id = stable_event_id(fingerprint)
    return fingerprint


def fingerprint_for_row(row: dict[str, Any]) -> str:
    stored = row.get("event_fingerprint")
    if stored:
        return str(stored)
    return compute_event_fingerprint(
        str(row.get("title") or ""),
        str(row.get("event_category") or "other"),
        row.get("geo_country"),
    )


def find_matching_row(
    event: RiskEvent,
    existing_rows: list[dict[str, Any]],
    *,
    fuzzy_threshold: float = _TITLE_FUZZ_THRESHOLD,
) -> dict[str, Any] | None:
    """Find an existing persisted row for the same story."""
    category = (
        event.event_category.value
        if hasattr(event.event_category, "value")
        else str(event.event_category)
    )
    target_fp = compute_event_fingerprint(event.title, category, event.geo_country)
    target_title = normalize_title(event.title)

    for row in existing_rows:
        if fingerprint_for_row(row) == target_fp:
            return row

    for row in existing_rows:
        if str(row.get("event_category") or "") != category:
            continue
        existing_title = normalize_title(str(row.get("title") or ""))
        if not existing_title or not target_title:
            continue
        if fuzz.ratio(existing_title, target_title) >= fuzzy_threshold:
            return row

    return None


def resolve_events_for_persist(
    events: list[RiskEvent],
    existing_rows: list[dict[str, Any]],
) -> tuple[list[RiskEvent], dict[str, int]]:
    """
    Assign stable IDs and mark UPDATED when a matching event already exists.

    Returns (events, stats) with keys: created, updated, deduplicated_in_batch.
    """
    stats = {"created": 0, "updated": 0, "deduplicated_in_batch": 0}
    working_index = list(existing_rows)
    seen_ids: set[str] = set()

    for event in events:
        fingerprint = assign_stable_identity(event)
        match = find_matching_row(event, working_index)

        if match:
            event.event_id = str(match["event_id"])
            fingerprint = fingerprint_for_row(match)
            event.status = EventLifecycleStatus.UPDATED
            stats["updated"] += 1
        elif event.event_id in seen_ids:
            event.status = EventLifecycleStatus.UPDATED
            stats["deduplicated_in_batch"] += 1
        else:
            event.status = EventLifecycleStatus.DETECTED
            stats["created"] += 1

        seen_ids.add(event.event_id)
        working_index.append(
            {
                "event_id": event.event_id,
                "title": event.title,
                "event_category": (
                    event.event_category.value
                    if hasattr(event.event_category, "value")
                    else str(event.event_category)
                ),
                "geo_country": event.geo_country,
                "event_fingerprint": fingerprint,
            }
        )

    return events, stats


def dedupe_row_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Group rows by fingerprint and pick one keeper per group.

    Keeper preference: highest severity, then latest retrieval_timestamp.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        fp = fingerprint_for_row(row)
        groups.setdefault(fp, []).append(row)

    keepers: list[dict[str, Any]] = []
    for fp, group in groups.items():
        group.sort(
            key=lambda row: (
                float(row.get("severity_score") or 0),
                str(row.get("retrieval_timestamp") or ""),
            ),
            reverse=True,
        )
        keeper = dict(group[0])
        keeper["event_fingerprint"] = fp
        keeper["_duplicate_ids"] = [str(row["event_id"]) for row in group[1:]]
        keepers.append(keeper)
    return keepers
