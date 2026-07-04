-- API keys schema for long-lived credentials
-- Used for Yoru CLI init and programmatic access

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    user TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    label TEXT,
    scopes TEXT,  -- JSON string: ['events:write', ...]
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    revoked_at TIMESTAMP,
    expires_at TIMESTAMP
);

-- Indexes for lookups
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_prefix ON api_keys(key_prefix);
