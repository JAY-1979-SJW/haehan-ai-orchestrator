-- Rollback for LOG-2B-2C: app_audit_log table removal
-- This is a destructive operation - use only with explicit approval

BEGIN;

-- Drop triggers first (protections must be removed before table operations)
DROP TRIGGER IF EXISTS app_audit_log_no_delete ON app_audit_log;
DROP TRIGGER IF EXISTS app_audit_log_no_update ON app_audit_log;

-- Drop trigger functions
DROP FUNCTION IF EXISTS prevent_app_audit_log_delete();
DROP FUNCTION IF EXISTS prevent_app_audit_log_update();

-- Drop all indexes
DROP INDEX IF EXISTS idx_app_audit_log_previous_event_hash;
DROP INDEX IF EXISTS idx_app_audit_log_event_hash;
DROP INDEX IF EXISTS idx_app_audit_log_payload_hash;
DROP INDEX IF EXISTS idx_app_audit_log_status_event_at;
DROP INDEX IF EXISTS idx_app_audit_log_request_id;
DROP INDEX IF EXISTS idx_app_audit_log_target_type_target_id;
DROP INDEX IF EXISTS idx_app_audit_log_organization_id_event_at;
DROP INDEX IF EXISTS idx_app_audit_log_actor_user_id_event_at;
DROP INDEX IF EXISTS idx_app_audit_log_event_type_event_at;
DROP INDEX IF EXISTS idx_app_audit_log_event_at;

-- Drop table
DROP TABLE IF EXISTS app_audit_log;

-- Drop enum type
DROP TYPE IF EXISTS app_audit_event_status;

COMMIT;
