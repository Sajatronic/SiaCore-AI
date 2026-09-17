"""Tests for Supabase storage preparation and read resolution."""

from models.schemas import (
    EntityType,
    EventCategory,
    EventLifecycleStatus,
    ExplainabilityLayer,
    LinkedEntity,
    ProvenanceInformation,
    RiskAnalysis,
    RiskEvent,
    SeveritySignal,
)
from services.event_storage import (
    STORAGE_VERSION,
    persisted_supply_chain_links,
    prepare_risk_event_for_persistence,
    resolve_stored_supply_chain_links,
    supply_chain_links_stored,
)


def _sample_event(**overrides) -> RiskEvent:
    base = RiskEvent(
        title="China supply disruption",
        summary="Test",
        event_type="sanction",
        event_category=EventCategory.EXPORT_SANCTION,
        classification_confidence=0.9,
        severity_signal=SeveritySignal(severity_score=70.0, scoring_method="hybrid"),
        severity_score=70.0,
        overall_confidence=0.8,
        explainability=ExplainabilityLayer(),
        provenance_information=ProvenanceInformation(),
        status=EventLifecycleStatus.DETECTED,
        linked_locations=[
            LinkedEntity(
                canonical_id="LOC:china",
                canonical_name="China",
                entity_type=EntityType.LOCATION,
                match_score=0.8,
                match_method="keyword_location",
                extracted_text="China",
            )
        ],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_persisted_supply_chain_links_includes_storage_version(monkeypatch):
    monkeypatch.setattr(
        "services.supply_chain_links._component_catalog",
        lambda: {"LM358": {"description": "Dual operational amplifier"}},
    )
    event = _sample_event(
        linked_components=[
            LinkedEntity(
                canonical_id="MPN:LM358",
                canonical_name="LM358",
                entity_type=EntityType.COMPONENT,
                match_score=0.62,
                match_method="supplier_inventory_map",
                extracted_text="SUP016",
            )
        ],
        risk_analysis=RiskAnalysis(
            executive_summary="Summary",
            business_impact="Impact",
            affected_manufacturers=["Texas Instruments"],
            analysis_confidence=0.9,
            model_used="test",
        ),
    )
    links = persisted_supply_chain_links(event)
    assert links["storage_version"] == STORAGE_VERSION
    assert links["components"][0]["name"] == "Dual operational amplifier"
    assert "Texas Instruments" in [entry["name"] for entry in links["affected_manufacturers"]]


def test_resolve_prefers_stored_links_without_catalog_enrich():
    stored_links = {
        "storage_version": STORAGE_VERSION,
        "components": [{"id": "MPN:LM358", "name": "Stored part name", "mpn": "LM358"}],
        "distributors": [{"id": "SUP016", "name": "LCSC"}],
        "manufacturers": [],
        "affected_manufacturers": [{"id": "MFR:TI", "name": "Texas Instruments"}],
        "locations": [{"id": "LOC:china", "name": "China"}],
    }
    linked, links = resolve_stored_supply_chain_links(
        supply_chain_links=stored_links,
        linked={"linked_locations": [{"canonical_id": "LOC:china", "canonical_name": "China", "entity_type": "LOCATION", "match_score": 0.8, "match_method": "x", "extracted_text": "China"}]},
        allow_catalog_enrich=False,
    )
    assert links["components"][0]["name"] == "Stored part name"
    assert supply_chain_links_stored(stored_links)


def test_prepare_risk_event_enriches_before_persist(monkeypatch):
    monkeypatch.setattr(
        "canonical.matchers._load_registry",
        lambda: {
            "suppliers": {
                "SUP016": {
                    "name": "LCSC",
                    "country": "China",
                    "linked_manufacturers": ["Texas Instruments"],
                    "linked_mpns": ["LM358"],
                }
            },
            "manufacturers": {
                "Texas Instruments": {"country": "United States", "mpns": ["LM358"]},
            },
            "components": {"LM358": {"description": "Dual operational amplifier"}},
        },
    )
    from services.event_storage import prepare_risk_event_for_persistence

    event = prepare_risk_event_for_persistence(_sample_event())
    assert event.linked_suppliers
    assert event.linked_components
