from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

class EntityType(str, Enum):
    SUPPLIER = "SUPPLIER"
    MANUFACTURER = "MANUFACTURER"
    COMPONENT = "COMPONENT"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    FACILITY = "FACILITY"
    EVENT_PHRASE = "EVENT_PHRASE"


class EventCategory(str, Enum):
    NATURAL_DISASTER = "natural_disaster"
    FACTORY_SHUTDOWN = "factory_shutdown"
    EXPORT_SANCTION = "export_sanction"
    LABOR_ACTION = "labor_action"
    LOGISTICS_DISRUPTION = "logistics_disruption"
    FINANCIAL_DISTRESS = "financial_distress"
    GEOPOLITICAL_EVENT = "geopolitical_event"
    CYBER_INCIDENT = "cyber_incident"
    ENERGY_DISRUPTION = "energy_disruption"
    REGULATORY_CHANGE = "regulatory_change"
    PUBLIC_HEALTH_EVENT = "public_health_event"
    MARKET_DISRUPTION = "market_disruption"
    OTHER = "other"


class EventLifecycleStatus(str, Enum):
    DETECTED = "detected"
    UPDATED = "updated"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class SourceRecord(BaseModel):
    provider: str
    reliability_tier: int = 3
    url: str | None = None
    retrieved_at: datetime
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class RawArticle(BaseModel):
    """Normalized record from any external news/event provider."""

    article_id: str = Field(default_factory=lambda: str(uuid4()))
    provider: str
    title: str
    body: str = ""
    published_at: datetime | None = None
    url: str | None = None
    language: str = "en"
    reliability_tier: int = 3
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)


class ExtractedEntity(BaseModel):
    text: str
    entity_type: EntityType
    start_char: int | None = None
    end_char: int | None = None
    confidence: float = 0.0
    source_article_id: str | None = None


class LinkedEntity(BaseModel):
    canonical_id: str
    canonical_name: str
    entity_type: EntityType
    match_score: float
    match_method: str
    extracted_text: str
    requires_review: bool = False


class ClassificationResult(BaseModel):
    event_type: str
    event_category: EventCategory
    confidence: float
    rationale: str = ""


class SeveritySignal(BaseModel):
    raw_signal: dict[str, Any] = Field(default_factory=dict)
    severity_score: float = 0.0
    scoring_method: str = "rule_based"


class ExplainabilityLayer(BaseModel):
    """Structured reasoning, evidence, and confidence for a risk event."""

    severity_factors: list[dict[str, Any]] = Field(default_factory=list)
    severity_summary: str = ""
    confidence_score: float = 0.0
    confidence_explanation: str = ""
    uncertainty_sources: list[dict[str, Any]] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)


class ProcessingStageAudit(BaseModel):
    stage: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input_count: int = 0
    output_count: int = 0
    dropped_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PrefilterDropRecord(BaseModel):
    """Audit record for articles dropped by relevance pre-filter."""

    article_id: str
    provider: str
    title: str
    url: str | None = None
    relevance_score: float
    min_score_required: float
    matched_terms: list[str] = Field(default_factory=list)
    drop_reason: str
    dropped_at: datetime = Field(default_factory=datetime.utcnow)


class ProvenanceInformation(BaseModel):
    sources: list[SourceRecord] = Field(default_factory=list)
    processing_stages: list[ProcessingStageAudit] = Field(default_factory=list)
    extraction_confidence: float = 0.0
    classification_confidence: float = 0.0
    entity_link_confidence: float = 0.0
    requires_human_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    pipeline_version: str = "0.1.0"


class AlertRuleMatch(BaseModel):
    """Record of a config rule matching an event (no delivery in Phase 1)."""

    rule_id: str
    rule_name: str
    match_metadata: dict[str, Any] = Field(default_factory=dict)


class RiskAnalysis(BaseModel):
    """Structured LLM impact analysis for a risk event (monitoring actions only)."""

    executive_summary: str = ""
    business_impact: str = ""
    affected_industries: list[str] = Field(default_factory=list)
    affected_manufacturers: list[str] = Field(default_factory=list)
    possible_consequences: list[str] = Field(default_factory=list)
    supply_chain_implications: list[str] = Field(default_factory=list)
    short_term_impact: str = ""
    long_term_impact: str = ""
    monitoring_actions: list[str] = Field(default_factory=list)
    confidence_explanation: str = ""
    analysis_confidence: float = 0.0
    model_used: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    skipped: bool = False
    skip_reason: str | None = None


class ImpactMetric(BaseModel):
    """Single impact dimension with probability and supporting evidence."""

    probability: float = 0.0
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ImpactPrediction(BaseModel):
    """Hybrid impact forecast for a supply chain risk event."""

    supply_delay: ImpactMetric = Field(default_factory=ImpactMetric)
    manufacturing_disruption: ImpactMetric = Field(default_factory=ImpactMetric)
    logistics_disruption: ImpactMetric = Field(default_factory=ImpactMetric)
    inventory_shortage: ImpactMetric = Field(default_factory=ImpactMetric)
    price_increase: ImpactMetric = Field(default_factory=ImpactMetric)
    expected_recovery_days_min: int | None = None
    expected_recovery_days_max: int | None = None
    prediction_confidence: float = 0.0
    prediction_method: str = "rule_based"
    explanation: str = ""
    contributing_factors: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    skipped: bool = False
    skip_reason: str | None = None


class RiskEvent(BaseModel):
    """Structured output consumed by downstream intelligence engines."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    summary: str = ""
    event_type: str
    event_category: EventCategory
    classification_confidence: float
    severity_signal: SeveritySignal
    severity_score: float
    extracted_entities: list[ExtractedEntity] = Field(default_factory=list)
    linked_manufacturers: list[LinkedEntity] = Field(default_factory=list)
    linked_suppliers: list[LinkedEntity] = Field(default_factory=list)
    linked_locations: list[LinkedEntity] = Field(default_factory=list)
    linked_components: list[LinkedEntity] = Field(default_factory=list)
    cluster_id: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    source_count: int = 1
    verification_score: float = 0.0
    article_ids: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    geo_country: str | None = None
    geo_region: str | None = None
    status: EventLifecycleStatus = EventLifecycleStatus.DETECTED
    overall_confidence: float = 0.0
    explainability: ExplainabilityLayer = Field(default_factory=ExplainabilityLayer)
    risk_analysis: RiskAnalysis | None = None
    impact_prediction: ImpactPrediction | None = None
    retrieval_timestamp: datetime = Field(default_factory=datetime.utcnow)
    provenance_information: ProvenanceInformation = Field(
        default_factory=ProvenanceInformation
    )

    def to_machine_output(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EnrichedArticle(BaseModel):
    """Article progressing through the pipeline with accumulated enrichments."""

    article: RawArticle
    is_relevant: bool = True
    relevance_score: float = 1.0
    extracted_entities: list[ExtractedEntity] = Field(default_factory=list)
    linked_entities: list[LinkedEntity] = Field(default_factory=list)
    classification: ClassificationResult | None = None
    severity: SeveritySignal | None = None
    cluster_id: str | None = None