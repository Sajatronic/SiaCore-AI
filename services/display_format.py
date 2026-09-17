"""Display helpers for SiaEye API responses."""

from __future__ import annotations

import ast
import re
from typing import Any

from services.news_summary import humanize_event_summary


def format_geo_label(value: Any) -> str | None:
    """Normalize geo country/region values for UI display."""
    if value is None:
        return None

    if isinstance(value, list):
        parts = [_clean_geo_part(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None

    text = str(value).strip()
    if not text:
        return None

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            parts = [_clean_geo_part(item) for item in parsed]
            parts = [part for part in parts if part]
            return ", ".join(parts) if parts else _clean_geo_part(text)

    return _clean_geo_part(text)


def _clean_geo_part(value: Any) -> str:
    text = str(value).strip().strip("'\"")
    text = re.sub(r"\s+", " ", text)
    return text.title() if text.islower() else text


def expand_entity_labels(value: Any) -> list[str]:
    """Normalize entity labels that may be plain text, lists, or list-strings."""
    if value is None:
        return []

    if isinstance(value, list):
        labels: list[str] = []
        for item in value:
            labels.extend(expand_entity_labels(item))
        return _dedupe_labels(labels)

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            labels = []
            for item in parsed:
                labels.extend(expand_entity_labels(item))
            return _dedupe_labels(labels)

    cleaned = _clean_geo_part(text)
    return [cleaned] if cleaned else []


def format_entity_label(value: Any) -> str | None:
    labels = expand_entity_labels(value)
    if not labels:
        return None
    return ", ".join(labels)


def _dedupe_labels(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for label in labels:
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(label)
    return deduped


def sanitize_event_for_display(event: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with normalized geo fields and readable summaries."""
    payload = dict(event)
    for key in ("geo_country", "geo_region"):
        if key in payload:
            payload[key] = format_geo_label(payload.get(key))
    if "summary" in payload:
        payload["summary"] = humanize_event_summary(payload.get("summary"))
    return payload


def entity_display_names(entities: Any, *, limit: int = 8) -> list[str]:
    """Extract unique canonical names from linked entity records."""
    names: list[str] = []
    if not isinstance(entities, list):
        return names
    for item in entities:
        if isinstance(item, dict):
            raw = item.get("canonical_name") or item.get("canonical_id")
        else:
            raw = item
        for name in expand_entity_labels(raw):
            if name in names:
                continue
            names.append(name)
            if len(names) >= limit:
                return names
    return names
