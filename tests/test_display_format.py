"""Tests for SiaEye display formatting helpers."""

from services.display_format import entity_display_names, expand_entity_labels, format_geo_label, sanitize_event_for_display


def test_format_geo_label_from_python_list_string():
    assert format_geo_label("['united arab emirates']") == "United Arab Emirates"


def test_format_geo_label_from_list():
    assert format_geo_label(["oman", "united arab emirates"]) == "Oman, United Arab Emirates"


def test_expand_entity_labels_from_list_string():
    assert expand_entity_labels("['tajikistan']") == ["Tajikistan"]


def test_format_geo_label_plain_string():
    assert format_geo_label("Singapore") == "Singapore"


def test_sanitize_event_for_display():
    event = {"event_id": "1", "geo_country": "['united arab emirates']", "title": "Test"}
    cleaned = sanitize_event_for_display(event)
    assert cleaned["geo_country"] == "United Arab Emirates"
    assert cleaned["title"] == "Test"


def test_entity_display_names():
    entities = [
        {"canonical_name": "LCSC", "canonical_id": "SUP016"},
        {"canonical_name": "LCSC", "canonical_id": "SUP016"},
        {"canonical_name": "UnikeyIC", "canonical_id": "SUP042"},
    ]
    assert entity_display_names(entities) == ["LCSC", "UnikeyIC"]
