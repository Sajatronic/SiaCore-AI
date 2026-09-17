"""Tests for supply chain links persistence section."""

from services.display_format import expand_entity_labels
from services.supply_chain_links import (
    build_supply_chain_links_from_linked_entities,
    build_supply_chain_links_from_parts,
    finalize_supply_chain_links,
    link_names,
)


def test_build_supply_chain_links_from_parts(monkeypatch):
    monkeypatch.setattr(
        "services.supply_chain_links._component_catalog",
        lambda: {"ADS1256": {"description": "24-bit precision ADC"}},
    )
    links = build_supply_chain_links_from_parts(
        components=[{"canonical_id": "MPN:ADS1256", "canonical_name": "ADS1256"}],
        distributors=[{"canonical_id": "SUP016", "canonical_name": "LCSC"}],
        manufacturers=[{"canonical_id": "MFR:TSMC", "canonical_name": "TSMC"}],
    )
    assert links["components"] == [
        {"id": "MPN:ADS1256", "name": "24-bit precision ADC", "mpn": "ADS1256"}
    ]
    assert links["distributors"] == [{"id": "SUP016", "name": "LCSC"}]
    assert links["manufacturers"] == [{"id": "MFR:TSMC", "name": "TSMC"}]
    assert links["affected_manufacturers"] == [{"id": "MFR:TSMC", "name": "TSMC"}]


def test_finalize_supply_chain_links_merges_ai_manufacturers():
    links = finalize_supply_chain_links(
        build_supply_chain_links_from_parts(
            manufacturers=[{"canonical_id": "MFR:TSMC", "canonical_name": "TSMC"}],
        ),
        risk_analysis={
            "skipped": False,
            "affected_manufacturers": ["Samsung", "TSMC"],
        },
    )
    assert link_names(links, "manufacturers") == ["TSMC"]
    assert link_names(links, "affected_manufacturers") == ["TSMC", "Samsung"]


def test_build_supply_chain_links_splits_list_string_location():
    links = build_supply_chain_links_from_parts(
        locations=[{"canonical_id": "LOC:tajikistan", "canonical_name": "['tajikistan']"}],
    )
    assert links["locations"] == [{"id": "LOC:tajikistan", "name": "Tajikistan"}]

    links = build_supply_chain_links_from_linked_entities(
        {
            "linked_suppliers": [{"canonical_id": "SUP016", "canonical_name": "LCSC"}],
            "linked_locations": [{"canonical_id": "LOC:china", "canonical_name": "China"}],
        }
    )
    assert link_names(links, "distributors") == ["LCSC"]
    assert link_names(links, "locations") == ["China"]


def test_refresh_component_entries_uses_catalog_description(monkeypatch):
    monkeypatch.setattr(
        "services.supply_chain_links._component_catalog",
        lambda: {"LM358": {"description": "Dual operational amplifier"}},
    )
    links = finalize_supply_chain_links(
        {
            "components": [{"id": "MPN:LM358", "name": "LM358"}],
            "distributors": [],
            "manufacturers": [],
            "affected_manufacturers": [],
            "locations": [],
        }
    )
    assert links["components"] == [
        {"id": "MPN:LM358", "name": "Dual operational amplifier", "mpn": "LM358"}
    ]


def test_expand_entity_labels_from_list_string():
    assert expand_entity_labels("['tajikistan']") == ["Tajikistan"]
