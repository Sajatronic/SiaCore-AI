"""Tests for human-readable news summaries."""

from services.news_summary import (
    build_gdacs_description,
    clean_summary_artifacts,
    humanize_event_summary,
    summary_preview,
)


def test_build_gdacs_earthquake_description():
    text = build_gdacs_description(
        event_type="EQ",
        alert_level="Green",
        country="Bolivia",
        severity_text="Magnitude 4.5M, Depth:203.556km",
    )
    assert "magnitude 4.5 earthquake" in text.lower()
    assert "Bolivia" in text
    assert "203.556 km" in text
    assert "Green alert" in text


def test_humanize_legacy_gdacs_summary():
    legacy = (
        "Event type: EQ. Alert level: Green. Country: Bolivia. "
        "Severity: Magnitude 4.5M, Depth:203.556km"
    )
    text = humanize_event_summary(legacy)
    assert text is not None
    assert "Event type:" not in text
    assert "Bolivia" in text
    assert "4.5" in text


def test_humanize_passes_through_normal_news():
    summary = "On 2026-07-18, China reportedly refused to supply critical equipment."
    assert humanize_event_summary(summary) == summary


def test_clean_summary_artifacts_strips_provider_truncation():
    text = "Official warns of closure of other straits and chokepoints [...]"
    assert clean_summary_artifacts(text) == "Official warns of closure of other straits and chokepoints"


def test_summary_preview_truncates_at_word_boundary():
    long_text = " ".join(["word"] * 80)
    preview = summary_preview(long_text, max_len=40)
    assert preview is not None
    assert len(preview) <= 40
    assert preview.endswith("…")
