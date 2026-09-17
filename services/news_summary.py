"""Human-readable news summaries for providers and API display."""

from __future__ import annotations

import re

EVENT_TYPE_LABELS = {
    "EQ": "earthquake",
    "FL": "flood",
    "TC": "tropical cyclone",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
}


def _parse_kv_summary(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in re.split(r"\.\s+", text.strip()):
        part = part.strip().rstrip(".")
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def build_gdacs_description(
    *,
    event_type: str,
    alert_level: str = "",
    country: str = "",
    severity_text: str = "",
) -> str:
    """Turn GDACS metadata into a readable news-style sentence."""
    event_code = (event_type or "UNKNOWN").upper()
    event_label = EVENT_TYPE_LABELS.get(event_code, event_code.lower().replace("_", " "))
    alert = alert_level.strip().capitalize() if alert_level else ""
    location = country.strip()

    if event_code == "EQ":
        magnitude = None
        depth_km = None
        severity_blob = severity_text or ""
        mag_match = re.search(r"magnitude\s+([\d.]+)M?", severity_blob, re.IGNORECASE)
        if mag_match:
            magnitude = mag_match.group(1)
        else:
            plain_mag = re.search(r"\b([\d.]+)\b", severity_blob)
            if plain_mag:
                magnitude = plain_mag.group(1)
        depth_match = re.search(r"depth[:\s]*([\d.]+)\s*km?", severity_blob, re.IGNORECASE)
        if depth_match:
            depth_km = depth_match.group(1)

        if magnitude:
            sentence = f"A magnitude {magnitude} earthquake was detected"
        else:
            sentence = "An earthquake was detected"
        if location:
            sentence += f" in {location}"
        if depth_km:
            sentence += f" at a depth of {depth_km} km"
        sentence += "."
        if alert:
            sentence += f" GDACS has issued a {alert} alert."
        return sentence

    sentence = f"A {event_label} event was reported"
    if location:
        sentence += f" in {location}"
    if severity_text:
        sentence += f" with severity {severity_text.strip()}"
    sentence += "."
    if alert:
        sentence += f" GDACS has issued a {alert} alert."
    return sentence


def clean_summary_artifacts(summary: str | None) -> str | None:
    """Remove provider truncation markers and dangling ellipses."""
    if not summary:
        return summary
    text = summary.strip()
    text = re.sub(r"\s*\[\.\.\.\]\s*$", "", text)
    text = re.sub(r"\s*\.{3,}\s*$", "", text)
    return text.strip() or None


def summary_preview(summary: str | None, *, max_len: int = 320) -> str | None:
    """Short card-friendly summary; detail views should use the full text."""
    text = humanize_event_summary(summary)
    if not text or len(text) <= max_len:
        return text
    clipped = text[: max_len - 1].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{clipped}…"


def humanize_event_summary(summary: str | None) -> str | None:
    """Rewrite legacy provider key-value summaries into readable prose."""
    if not summary:
        return summary
    summary = clean_summary_artifacts(summary) or summary
    if "Event type:" not in summary and "event type:" not in summary.lower():
        return summary

    fields = _parse_kv_summary(summary)
    if "event type" not in fields:
        return summary

    return build_gdacs_description(
        event_type=fields.get("event type", ""),
        alert_level=fields.get("alert level", ""),
        country=fields.get("country", ""),
        severity_text=fields.get("severity", ""),
    )
