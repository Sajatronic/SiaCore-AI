"""Tests for catalog join inference (location → distributor → manufacturer → part)."""

from canonical.matchers import (
    _expand_components_by_catalog,
    _expand_manufacturers_by_location,
    _expand_manufacturers_by_supplier,
    _expand_suppliers_by_location,
    _finalize_linked_entities,
)
from models.schemas import EntityType, LinkedEntity


def _sample_registry() -> dict:
    return {
        "suppliers": {
            "SUP016": {
                "name": "LCSC",
                "country": "China",
                "linked_manufacturers": ["Texas Instruments", "NXP Semiconductors"],
                "linked_mpns": ["ADS1256", "LM358", "NE555"],
            },
            "SUP028": {
                "name": "ODG",
                "country": "China",
                "linked_manufacturers": ["Texas Instruments"],
                "linked_mpns": ["LM358"],
            },
        },
        "manufacturers": {
            "Texas Instruments": {
                "country": "United States",
                "mpns": ["ADS1256", "LM358", "TL072"],
            },
            "NXP Semiconductors": {
                "country": "Netherlands",
                "mpns": ["NE555"],
            },
        },
        "components": {
            "ADS1256": {"manufacturer": "Texas Instruments", "supplier_id": "SUP016"},
            "LM358": {"manufacturer": "Texas Instruments", "supplier_id": "SUP016"},
            "NE555": {"manufacturer": "NXP Semiconductors", "supplier_id": "SUP016"},
        },
    }


def test_location_expands_to_suppliers():
    linked = [
        LinkedEntity(
            canonical_id="LOC:china",
            canonical_name="China",
            entity_type=EntityType.LOCATION,
            match_score=0.8,
            match_method="keyword_location",
            extracted_text="China",
        )
    ]
    additions = _expand_suppliers_by_location(linked, _sample_registry())
    codes = {item.canonical_id for item in additions}
    assert "SUP016" in codes
    assert "SUP028" in codes


def test_supplier_expands_to_manufacturers():
    linked = [
        LinkedEntity(
            canonical_id="SUP016",
            canonical_name="LCSC",
            entity_type=EntityType.SUPPLIER,
            match_score=0.6,
            match_method="location_supplier_map",
            extracted_text="China",
        )
    ]
    additions = _expand_manufacturers_by_supplier(linked, _sample_registry())
    names = {item.canonical_name for item in additions}
    assert "Texas Instruments" in names
    assert "NXP Semiconductors" in names
    assert all(item.match_method == "supplier_manufacturer_map" for item in additions)


def test_supplier_and_manufacturer_expand_to_components():
    linked = [
        LinkedEntity(
            canonical_id="SUP016",
            canonical_name="LCSC",
            entity_type=EntityType.SUPPLIER,
            match_score=0.6,
            match_method="location_supplier_map",
            extracted_text="China",
        ),
        LinkedEntity(
            canonical_id="MFR:Texas Instruments",
            canonical_name="Texas Instruments",
            entity_type=EntityType.MANUFACTURER,
            match_score=0.62,
            match_method="supplier_manufacturer_map",
            extracted_text="SUP016",
        ),
    ]
    additions = _expand_components_by_catalog(linked, _sample_registry())
    mpns = {item.canonical_name for item in additions}
    assert "ADS1256" in mpns
    assert "LM358" in mpns
    assert "NE555" in mpns
    assert all(item.entity_type == EntityType.COMPONENT for item in additions)


def test_finalize_chains_location_to_parts_without_text_mpn():
    location = LinkedEntity(
        canonical_id="LOC:china",
        canonical_name="China",
        entity_type=EntityType.LOCATION,
        match_score=0.8,
        match_method="keyword_location",
        extracted_text="China",
    )
    linked = _finalize_linked_entities([location], None, _sample_registry())

    suppliers = [item for item in linked if item.entity_type == EntityType.SUPPLIER]
    manufacturers = [item for item in linked if item.entity_type == EntityType.MANUFACTURER]
    components = [item for item in linked if item.entity_type == EntityType.COMPONENT]

    assert suppliers
    assert manufacturers
    assert components
    assert any(item.canonical_name == "ADS1256" for item in components)


def test_location_expands_to_manufacturers_in_same_country():
    registry = _sample_registry()
    registry["manufacturers"]["SMIC"] = {
        "country": "China",
        "mpns": ["SMIC-001"],
    }
    linked = [
        LinkedEntity(
            canonical_id="LOC:china",
            canonical_name="China",
            entity_type=EntityType.LOCATION,
            match_score=0.8,
            match_method="keyword_location",
            extracted_text="China",
        )
    ]
    additions = _expand_manufacturers_by_location(linked, registry)
    assert any(item.canonical_name == "SMIC" for item in additions)


def test_enrich_linked_entities_with_catalog_from_location_only():
    from canonical.matchers import enrich_linked_entities_with_catalog

    enriched = enrich_linked_entities_with_catalog(
        {
            "linked_locations": [
                {
                    "canonical_id": "LOC:china",
                    "canonical_name": "China",
                    "entity_type": "LOCATION",
                    "match_score": 0.8,
                    "match_method": "keyword_location",
                    "extracted_text": "China",
                    "requires_review": False,
                }
            ],
            "linked_suppliers": [],
            "linked_manufacturers": [],
            "linked_components": [],
        }
    )
    assert enriched["linked_suppliers"]
    assert enriched["linked_manufacturers"]
    assert enriched["linked_components"]
