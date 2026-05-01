-- LOG-2B-2C: app_audit_log table creation (PostgreSQL)
-- Forward-compatible with BROWSER-AUDIT-1 contract
-- Append-only audit log with chain-hashing support

BEGIN;

-- Status enum for audit events
CREATE TYPE app_audit_event_status AS ENUM (
    'PASS',
    'WARN',
    'FAIL',
    'SKIP',
    'ERROR'
);

-- Main audit log table
CREATE TABLE IF NOT EXISTS app_audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),

    -- Event metadata
    event_type TEXT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Actor context
    actor_user_id TEXT NULL,
    actor_role TEXT NULL,
    organization_id TEXT NULL,

    -- Target context
    target_type TEXT NULL,
    target_id TEXT NULL,
    request_id TEXT NULL,

    -- Session / request hashing
    session_hash TEXT NULL,
    ip_hash TEXT NULL,
    user_agent_hash TEXT NULL,

    -- Status and errors
    status app_audit_event_status NOT NULL,
    error_code TEXT NULL,
    error_message TEXT NULL,

    -- Performance
    elapsed_ms INTEGER NULL,

    -- Content hashing (for integrity chain)
    payload_hash TEXT NULL,
    prompt_hash TEXT NULL,
    response_hash TEXT NULL,
    event_hash TEXT NOT NULL,
    previous_event_hash TEXT NULL,

    -- Safe metadata (no secrets)
    metadata_json JSONB NULL,

    -- Schema versioning
    log_version TEXT NOT NULL DEFAULT 'browser-audit-1',
    source TEXT NOT NULL DEFAULT 'local_agent.browser',
    environment TEXT NULL,

    -- Indexes will be added separately
    CONSTRAINT event_at_not_future CHECK (event_at <= now()),
    CONSTRAINT event_type_not_empty CHECK (event_type <> '')
);

-- Append-only protection: prevent UPDATE
CREATE FUNCTION prevent_app_audit_log_update()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'app_audit_log is append-only: UPDATE not allowed';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER app_audit_log_no_update
BEFORE UPDATE ON app_audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_app_audit_log_update();

-- Append-only protection: prevent DELETE
CREATE FUNCTION prevent_app_audit_log_delete()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'app_audit_log is append-only: DELETE not allowed';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER app_audit_log_no_delete
BEFORE DELETE ON app_audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_app_audit_log_delete();

-- Indexes for query performance
CREATE INDEX idx_app_audit_log_event_at
    ON app_audit_log (event_at DESC);

CREATE INDEX idx_app_audit_log_event_type_event_at
    ON app_audit_log (event_type, event_at DESC);

CREATE INDEX idx_app_audit_log_actor_user_id_event_at
    ON app_audit_log (actor_user_id, event_at DESC)
    WHERE actor_user_id IS NOT NULL;

CREATE INDEX idx_app_audit_log_organization_id_event_at
    ON app_audit_log (organization_id, event_at DESC)
    WHERE organization_id IS NOT NULL;

CREATE INDEX idx_app_audit_log_target_type_target_id
    ON app_audit_log (target_type, target_id)
    WHERE target_type IS NOT NULL AND target_id IS NOT NULL;

CREATE INDEX idx_app_audit_log_request_id
    ON app_audit_log (request_id)
    WHERE request_id IS NOT NULL;

CREATE INDEX idx_app_audit_log_status_event_at
    ON app_audit_log (status, event_at DESC);

CREATE INDEX idx_app_audit_log_payload_hash
    ON app_audit_log (payload_hash)
    WHERE payload_hash IS NOT NULL;

CREATE INDEX idx_app_audit_log_event_hash
    ON app_audit_log (event_hash);

CREATE INDEX idx_app_audit_log_previous_event_hash
    ON app_audit_log (previous_event_hash)
    WHERE previous_event_hash IS NOT NULL;

-- Grant statements (uncomment and customize for your environment)
-- GRANT INSERT ON app_audit_log TO app_writer;
-- GRANT SELECT ON app_audit_log TO app_readonly;
-- GRANT SELECT ON app_audit_log TO app_admin;

COMMIT;
