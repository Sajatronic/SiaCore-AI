from models.schemas import (
    ClassificationResult,
    EventCategory,
    EventLifecycleStatus,
    RiskEvent,
    SeveritySignal,
)
from services.event_dedup import (
    assign_stable_identity,
    compute_event_fingerprint,
    dedupe_row_groups,
    normalize_title,
    resolve_events_for_persist,
    stable_event_id,
)


def _event(title: str, category: EventCategory = EventCategory.LOGISTICS_DISRUPTION) -> RiskEvent:
    return RiskEvent(
        event_id="placeholder",
        title=title,
        summary="summary",
        event_type="shipping_lane_disruption",
        event_category=category,
        classification_confidence=0.9,
        severity_signal=SeveritySignal(severity_score=70.0),
        severity_score=70.0,
        geo_country="Oman",
    )


def test_stable_event_id_is_deterministic():
    fp = compute_event_fingerprint("Strait of Hormuz closure", "logistics_disruption", "Oman")
    assert stable_event_id(fp) == stable_event_id(fp)


def test_same_title_gets_same_event_id():
    a = _event("Some ships refuse US-guided transits through Strait of Hormuz")
    b = _event("Some ships refuse US-guided transits through Strait of Hormuz")
    assign_stable_identity(a)
    assign_stable_identity(b)
    assert a.event_id == b.event_id


def test_resolve_marks_existing_as_updated():
    existing = [
        {
            "event_id": "existing-1",
            "title": "Some ships refuse US-guided transits through Strait of Hormuz",
            "event_category": "logistics_disruption",
            "geo_country": "Oman",
        }
    ]
    incoming = [_event("Some ships refuse US-guided transits through Strait of Hormuz")]
    resolved, stats = resolve_events_for_persist(incoming, existing)
    assert resolved[0].event_id == "existing-1"
    assert resolved[0].status == EventLifecycleStatus.UPDATED
    assert stats["updated"] == 1


def test_dedupe_row_groups_keeps_highest_severity():
    rows = [
        {
            "event_id": "a",
            "title": "Same story",
            "event_category": "logistics_disruption",
            "geo_country": "Oman",
            "severity_score": 60,
            "retrieval_timestamp": "2026-07-18T10:00:00",
        },
        {
            "event_id": "b",
            "title": "Same story",
            "event_category": "logistics_disruption",
            "geo_country": "Oman",
            "severity_score": 73,
            "retrieval_timestamp": "2026-07-18T09:00:00",
        },
    ]
    keepers = dedupe_row_groups(rows)
    assert len(keepers) == 1
    assert keepers[0]["event_id"] == "b"
    assert keepers[0]["_duplicate_ids"] == ["a"]


def test_normalize_title_strips_punctuation():
    assert normalize_title("Hello, World!") == "hello world"
