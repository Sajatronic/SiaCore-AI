import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from services.event_read import EventReadService, rehydrate_event_row


@pytest.fixture
def sample_row():
    return {
        "event_id": "evt-1",
        "run_id": "run-1",
        "title": "Port closure in Singapore",
        "summary": "Major port disruption reported.",
        "event_type": "port_closure",
        "event_category": "logistics_disruption",
        "classification_confidence": 0.9,
        "severity_score": 72.0,
        "severity_signal": {
            "raw_signal": {"base_rule_score": 70},
            "severity_score": 72.0,
            "scoring_method": "hybrid",
            "overall_confidence": 0.85,
            "explainability": {"severity_summary": "High severity"},
        },
        "status": "detected",
        "latitude": 1.29,
        "longitude": 103.85,
        "geo_country": "Singapore",
        "source_count": 2,
        "verification_score": 0.7,
        "linked_entities": {
            "extracted_entities": [],
            "linked_locations": [{"canonical_name": "Singapore"}],
        },
        "provenance": {"pipeline_version": "0.5.0", "sources": []},
        "retrieval_timestamp": "2026-07-18T12:00:00",
    }


def test_rehydrate_event_row(sample_row):
    event = rehydrate_event_row(sample_row)
    assert event["event_id"] == "evt-1"
    assert event["overall_confidence"] == 0.85
    assert event["explainability"]["severity_summary"] == "High severity"
    assert event["linked_locations"][0]["canonical_name"] == "Singapore"


def test_local_json_list_events(tmp_path, monkeypatch):
    payload = {
        "run_id": "run-local",
        "pipeline_version": "0.5.0",
        "risk_events": [
            {
                "event_id": "a",
                "title": "Alpha strike",
                "summary": "Labor action",
                "event_type": "strike",
                "event_category": "labor_action",
                "classification_confidence": 0.8,
                "severity_signal": {"raw_signal": {}, "severity_score": 55, "scoring_method": "hybrid"},
                "severity_score": 55,
                "status": "detected",
                "overall_confidence": 0.7,
                "linked_components": [{"canonical_name": "MPN:ADS1256", "canonical_id": "MPN:ADS1256"}],
                "linked_suppliers": [{"canonical_name": "LCSC", "canonical_id": "SUP016"}],
                "linked_manufacturers": [{"canonical_name": "TSMC", "canonical_id": "MFR:TSMC"}],
                "supply_chain_links": {
                    "components": [{"id": "MPN:ADS1256", "name": "MPN:ADS1256"}],
                    "distributors": [{"id": "SUP016", "name": "LCSC"}],
                    "manufacturers": [{"id": "MFR:TSMC", "name": "TSMC"}],
                    "affected_manufacturers": [{"id": "MFR:TSMC", "name": "TSMC"}],
                    "locations": [],
                },
            },
            {
                "event_id": "b",
                "title": "Beta flood",
                "summary": "Flooding",
                "event_type": "flood",
                "event_category": "natural_disaster",
                "classification_confidence": 0.9,
                "severity_signal": {"raw_signal": {}, "severity_score": 80, "scoring_method": "hybrid"},
                "severity_score": 80,
                "status": "detected",
                "overall_confidence": 0.9,
            },
        ],
    }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_key", "")
    monkeypatch.setattr(settings, "siaeye_result_json_path", result_path)
    monkeypatch.setattr(
        "services.supply_chain_links._component_catalog",
        lambda: {"ADS1256": {"description": "24-bit precision ADC"}},
    )

    service = EventReadService()
    listed = service.list_events(min_severity=60)
    assert listed["total"] == 1
    assert listed["items"][0]["event_id"] == "b"

    all_events = service.list_events()
    alpha = next(item for item in all_events["items"] if item["event_id"] == "a")
    assert alpha["linked_components"] == ["24-bit precision ADC"]
    assert alpha["linked_suppliers"] == ["LCSC"]
    assert alpha["affected_manufacturers"] == ["TSMC"]
    assert alpha["supply_chain_links"]["distributors"][0]["name"] == "LCSC"

    detail = service.get_event("a")
    assert detail["title"] == "Alpha strike"

    stats = service.summary_stats()
    assert stats["total_events"] == 2
    assert stats["max_severity"] == 80


def test_empty_result_json_does_not_crash(tmp_path, monkeypatch):
    result_path = tmp_path / "result.json"
    result_path.write_text("", encoding="utf-8")

    from services.event_read import _load_local_snapshot

    _load_local_snapshot.cache_clear()
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_key", "")
    monkeypatch.setattr(settings, "siaeye_result_json_path", result_path)

    service = EventReadService()
    assert service.summary_stats()["total_events"] == 0
    assert service.list_runs() == []

    from api.main import app

    client = TestClient(app)
    assert client.get("/api/stats/summary").status_code == 200
    assert client.get("/api/runs").status_code == 200


def test_siaeye_api_health(monkeypatch, tmp_path):
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps({"run_id": "r1", "risk_events": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_key", "")
    monkeypatch.setattr(settings, "siaeye_result_json_path", result_path)

    from api.main import app

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["product"] == "SiaEye"

    meta = client.get("/api/meta")
    assert meta.json()["platform"] == "SiaCore"

    events = client.get("/api/events")
    assert events.status_code == 200
    assert "items" in events.json()
