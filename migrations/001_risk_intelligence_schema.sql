-- Risk intelligence persistence schema (Phase 1)
-- Backward compatible: does not modify existing supply-chain catalog tables.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Canonical risk events (one row per cluster after merge)
CREATE TABLE IF NOT EXISTS risk_events (
    event_id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    cluster_id UUID,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    event_category TEXT NOT NULL,
    classification_confidence REAL NOT NULL DEFAULT 0,
    severity_score REAL NOT NULL DEFAULT 0,
    severity_signal JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'detected'
        CHECK (status IN ('detected', 'updated', 'escalated', 'resolved')),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    geo_country TEXT,
    geo_region TEXT,
    source_count INTEGER NOT NULL DEFAULT 1,
    verification_score REAL NOT NULL DEFAULT 0,
    linked_entities JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    pipeline_version TEXT NOT NULL DEFAULT '0.1.0',
    retrieval_timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_events_run_id ON risk_events (run_id);
CREATE INDEX IF NOT EXISTS idx_risk_events_cluster_id ON risk_events (cluster_id);
CREATE INDEX IF NOT EXISTS idx_risk_events_category ON risk_events (event_category);
CREATE INDEX IF NOT EXISTS idx_risk_events_status ON risk_events (status);
CREATE INDEX IF NOT EXISTS idx_risk_events_created_at ON risk_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_geo_country ON risk_events (geo_country);

-- Source articles linked to a canonical event (multi-source verification)
CREATE TABLE IF NOT EXISTS event_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES risk_events (event_id) ON DELETE CASCADE,
    article_id UUID NOT NULL,
    provider TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    url TEXT,
    reliability_tier INTEGER NOT NULL DEFAULT 3,
    provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_event_articles_event_id ON event_articles (event_id);
CREATE INDEX IF NOT EXISTS idx_event_articles_provider ON event_articles (provider);

-- Event lifecycle audit trail
CREATE TABLE IF NOT EXISTS event_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES risk_events (event_id) ON DELETE CASCADE,
    status TEXT NOT NULL
        CHECK (status IN ('detected', 'updated', 'escalated', 'resolved')),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_event_status_history_event_id ON event_status_history (event_id);

-- Config-driven alert rule matches (delivery is config-only in Phase 1)
CREATE TABLE IF NOT EXISTS alert_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES risk_events (event_id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    matched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    match_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_alert_matches_event_id ON alert_matches (event_id);
CREATE INDEX IF NOT EXISTS idx_alert_matches_rule_id ON alert_matches (rule_id);
