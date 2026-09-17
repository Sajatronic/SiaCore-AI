"""Tests for compact LLM entity linking."""

from models.schemas import EntityType, ExtractedEntity
from canonical.matchers import _get_compact_registry_summary, _extracted_covered, _truncate_text
from models.schemas import LinkedEntity


def test_compact_registry_summary_is_small():
    registry = {
        "manufacturers": {
            "Texas Instruments": {"aliases": ["TI"], "supplier_ids": ["SUP001"]},
            "Samsung": {"aliases": [], "supplier_ids": []},
        },
        "suppliers": {"SUP001": {}},
        "regions": ["Taiwan", "Germany"],
        "components": {"ADS1256": {}, "UNRELATED999": {}},
    }
    extracted = [
        ExtractedEntity(text="TI", entity_type=EntityType.MANUFACTURER, confidence=0.9),
        ExtractedEntity(text="Taiwan", entity_type=EntityType.LOCATION, confidence=0.9),
    ]
    text = "TI fab in Taiwan uses ADS1256"
    summary = _get_compact_registry_summary(extracted, text, registry)

    assert "Texas Instruments" in summary
    assert "Taiwan" in summary
    assert "ADS1256" in summary
    assert "UNRELATED999" not in summary
    assert "Samsung" not in summary
    assert len(summary) < 800


def test_extracted_covered():
    extracted = [ExtractedEntity(text="TI", entity_type=EntityType.MANUFACTURER, confidence=0.9)]
    linked = [
        LinkedEntity(
            canonical_id="MFR:Texas Instruments",
            canonical_name="Texas Instruments",
            entity_type=EntityType.MANUFACTURER,
            match_score=0.9,
            match_method="fuzzy",
            extracted_text="TI",
        )
    ]
    assert _extracted_covered(extracted, linked) is True
    assert _extracted_covered(extracted, []) is False


def test_truncate_text():
    assert _truncate_text("hello", 10) == "hello"
    assert _truncate_text("hello world", 8) == "hello..."
