-- Supply chain links section (components, distributors, manufacturers, locations)
-- Denormalized for display and querying; built from entity linking at persist time.

ALTER TABLE risk_events
    ADD COLUMN IF NOT EXISTS supply_chain_links JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_risk_events_supply_chain_links
    ON risk_events USING gin (supply_chain_links);

COMMENT ON COLUMN risk_events.supply_chain_links IS
    'Structured supply chain context: components, distributors, manufacturers, affected_manufacturers, locations';
