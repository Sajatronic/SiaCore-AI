-- Impact prediction persistence (Phase 4)
-- Stores hybrid rule/LLM impact forecasts per risk event.

CREATE TABLE IF NOT EXISTS event_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES risk_events (event_id) ON DELETE CASCADE,
    prediction JSONB NOT NULL DEFAULT '{}'::jsonb,
    prediction_confidence REAL,
    prediction_method TEXT,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS idx_event_predictions_event_id ON event_predictions (event_id);
CREATE INDEX IF NOT EXISTS idx_event_predictions_generated_at ON event_predictions (generated_at DESC);
