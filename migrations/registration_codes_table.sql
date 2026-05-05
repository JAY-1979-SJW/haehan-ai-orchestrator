-- REGISTRATION-CODES-1: Registration Code Persistent Store Migration
--
-- Purpose: Move registration_codes storage from in-memory to PostgreSQL
-- Basis: REGCODE-1 security design (code_hash, code_salt, 1회용)
--
-- Tables:
-- - registration_codes: registration code records (no organization scope initially)
--
-- Security:
-- - registration_code 원문 저장 금지 (code_hash+salt만 저장)
-- - code_hash = SHA-256(salt + normalized_code)
-- - allowed_actions stored as JSONB
-- - used_at / revoked_at 기록으로 1회용, 폐기 강제
-- - expires_at 지난 code 자동 거부
--
-- WARNING: This is a migration file. Do NOT execute without explicit approval.
-- Do NOT apply to production database without migration review and sign-off.
--
-- Rollback: See rollback_registration_codes_table.sql
--

BEGIN;

-- ============================================================================
-- 1. registration_codes: Registration Code Registry
-- ============================================================================

-- DO NOT EXECUTE BEFORE APPROVAL
-- This table stores hashed registration codes only.
-- The plaintext code is NEVER stored here.

CREATE TABLE IF NOT EXISTS registration_codes (
  id BIGSERIAL PRIMARY KEY,
  code_id TEXT NOT NULL UNIQUE,
  code_hash TEXT NOT NULL,
  code_salt TEXT NOT NULL,
  label TEXT,
  note TEXT,
  allowed_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ NULL,
  revoked_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by TEXT NULL,
  last_error TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE registration_codes IS 'Registration code records for local agent registration (one-time use)';
COMMENT ON COLUMN registration_codes.code_id IS 'Unique code identifier (rc-<hex12>)';
COMMENT ON COLUMN registration_codes.code_hash IS 'SHA-256(salt + normalized_code) - NEVER plaintext';
COMMENT ON COLUMN registration_codes.code_salt IS 'Random salt for hash (hex16)';
COMMENT ON COLUMN registration_codes.allowed_actions IS 'JSON array of allowed actions for this code';
COMMENT ON COLUMN registration_codes.expires_at IS 'Code expiration timestamp';
COMMENT ON COLUMN registration_codes.used_at IS 'When code was successfully consumed (NULL if unused)';
COMMENT ON COLUMN registration_codes.revoked_at IS 'When code was revoked (NULL if not revoked)';
COMMENT ON COLUMN registration_codes.created_by IS 'Admin user who issued this code';
COMMENT ON COLUMN registration_codes.last_error IS 'Last exchange error reason (audit only)';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_registration_codes_code_id ON registration_codes (code_id);
CREATE INDEX IF NOT EXISTS idx_registration_codes_code_hash ON registration_codes (code_hash);
CREATE INDEX IF NOT EXISTS idx_registration_codes_expires_at ON registration_codes (expires_at);
CREATE INDEX IF NOT EXISTS idx_registration_codes_used_at ON registration_codes (used_at);
CREATE INDEX IF NOT EXISTS idx_registration_codes_revoked_at ON registration_codes (revoked_at);
CREATE INDEX IF NOT EXISTS idx_registration_codes_created_at ON registration_codes (created_at);

COMMIT;
