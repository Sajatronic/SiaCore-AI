-- AI risk analysis persistence (Phase 3)
-- Stores structured LLM-generated impact analysis per risk event.

CREATE TABLE IF NOT EXISTS event_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES risk_events (event_id) ON DELETE CASCADE,
    analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_used TEXT,
    analysis_confidence REAL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS idx_event_analyses_event_id ON event_analyses (event_id);
CREATE INDEX IF NOT EXISTS idx_event_analyses_generated_at ON event_analyses (generated_at DESC);
