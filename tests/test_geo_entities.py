"""Tests for geo metadata and strategic location entity extraction."""

from canonical.matchers import (
    _inject_geo_linked_entities,
    _link_entities_fallback,
    extract_metadata_geo_entities,
    extract_strategic_location_entities,
)
from models.schemas import EntityType


def test_extract_metadata_geo_entities_from_gdelt():
    metadata = {
        "raw": {
            "geo": {
                "country": "Oman",
                "region": "Middle East",
                "location": "Muscat",
            }
        }
    }
    entities = extract_metadata_geo_entities(metadata, "article-1")
    assert len(entities) >= 2
    assert all(e.entity_type == EntityType.LOCATION for e in entities)
    assert any(e.text == "Oman" for e in entities)


def test_extract_strategic_location_from_text():
    text = "Some ships refuse US-guided transits through Strait of Hormuz"
    entities = extract_strategic_location_entities(text, "article-2")
    assert any("hormuz" in e.text.lower() for e in entities)


def test_inject_geo_linked_entities():
    metadata = {"raw": {"geo": {"country": "Iran"}}}
    linked = _inject_geo_linked_entities([], metadata)
    assert len(linked) == 1
    assert linked[0].canonical_id == "LOC:iran"
    assert linked[0].entity_type == EntityType.LOCATION


def test_fallback_links_location_entities():
    from models.schemas import ExtractedEntity

    extracted = [
        ExtractedEntity(text="Strait of Hormuz", entity_type=EntityType.LOCATION, confidence=0.88)
    ]
    metadata = {"raw": {"geo": {"country": "Oman"}}}
    linked = _link_entities_fallback(extracted, "Transit through Strait of Hormuz", metadata)
    location_ids = {item.canonical_id for item in linked if item.entity_type == EntityType.LOCATION}
    assert "LOC:strait of hormuz" in location_ids or any("hormuz" in cid for cid in location_ids)
    assert "LOC:oman" in location_ids
