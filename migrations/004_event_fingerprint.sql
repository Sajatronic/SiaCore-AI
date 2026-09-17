-- Cross-run deduplication: stable fingerprint per canonical story
ALTER TABLE risk_events
    ADD COLUMN IF NOT EXISTS event_fingerprint TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_events_event_fingerprint
    ON risk_events (event_fingerprint)
    WHERE event_fingerprint IS NOT NULL;
