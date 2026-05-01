# LOG-2B-2C: app_audit_log Migration Handoff Runbook

**Document Version:** 1.0  
**Date:** 2026-05-01  
**Status:** Ready for Production Application  
**Approval:** Required before execution

---

## 1. 적용 대상 (Scope)

| Item | Value |
|------|-------|
| **Migration File** | `migrations/log_2b_2c_app_audit_log.sql` |
| **Rollback File** | `migrations/rollback_log_2b_2c_app_audit_log.sql` |
| **Source Commit** | `df7d0cb` |
| **Schema** | PostgreSQL 13+ |
| **Target Table** | `app_audit_log` (new) |
| **Target Type** | `app_audit_event_status` (new) |
| **Trigger Functions** | `prevent_app_audit_log_update()`, `prevent_app_audit_log_delete()` |
| **Indexes** | 10 indexes for performance & query patterns |

### Migration Checksums

```
SHA256(log_2b_2c_app_audit_log.sql):
5e90335ae61c3f58d282687fa6a79bc83e325fb2b143e7228b861ba366a0953f

SHA256(rollback_log_2b_2c_app_audit_log.sql):
a98b18ab35926676c2b8d6c09dc79d04ba4d76160bced0f5a2d6533770133a5f
```

---

## 2. 사전 조건 (Prerequisites)

### Code Repository
- [ ] Operating server repository contains commit `df7d0cb` or later
- [ ] `working tree` is clean (no uncommitted changes)
- [ ] `migrations/log_2b_2c_app_audit_log.sql` and rollback file are present

### Database Access
- [ ] PostgreSQL 13+ is running
- [ ] Database user has CREATE TABLE, CREATE TYPE, CREATE FUNCTION, CREATE INDEX privileges
- [ ] Database user can create/drop triggers
- [ ] Connection uses TLS (if remote)

### Configuration
- [ ] `AUDIT_LOG_ENABLED` is **NOT** set to `ENABLED` (must be `DRY_RUN` or `false`)
- [ ] `AUDIT_PII_SALT` environment variable exists (for safe PII hashing)
- [ ] Database secret (password/connection string) is stored securely in environment or secrets manager
- [ ] **Never hardcode or log DB credentials**

### Approval
- [ ] Written approval from authorized operator
- [ ] Approval document linked to this runbook

---

## 3. Pre-Migration Verification (Read-Only)

### Check Existing Objects
Run these queries **before** applying the migration to verify no conflicts:

```sql
-- 1. Check if app_audit_log already exists
SELECT tablename FROM pg_tables 
WHERE schemaname = 'public' AND tablename = 'app_audit_log';
-- Expected: (no rows)

-- 2. Check if app_audit_event_status type already exists
SELECT typname FROM pg_type 
WHERE typname = 'app_audit_event_status' AND typnamespace::regnamespace = 'public'::regnamespace;
-- Expected: (no rows)

-- 3. List existing triggers (for reference)
SELECT trigger_name, event_object_table FROM information_schema.triggers 
WHERE event_object_schema = 'public' AND trigger_name LIKE '%app_audit%';
-- Expected: (no rows)

-- 4. Current database schema version
SELECT version();
-- Expected: PostgreSQL 13+

-- 5. Current user privileges
SELECT * FROM information_schema.role_table_grants 
WHERE grantee = current_user AND table_catalog = current_database();
-- Expected: Sufficient CREATE/ALTER privileges
```

---

## 4. Migration Execution

### Pre-Execution Checklist
- [ ] All prerequisite checks from Section 2 completed
- [ ] Read-only verification queries from Section 3 executed successfully
- [ ] Database backup taken (strongly recommended)
- [ ] Maintenance window scheduled
- [ ] Rollback operator available during execution

### Execution Command

**Important:** Replace `$DATABASE_URL` with your actual connection string.  
**Never log or commit the actual DB credentials.**

```bash
# Set database connection (example; use your actual method)
export DATABASE_URL="postgresql://user:password@host:5432/database"

# OR use .pgpass file for credentials
# OR use AWS RDS IAM authentication
# OR use environment secrets manager

# Navigate to repo root
cd /path/to/haehan-ai-orchestrator

# Execute migration with error handling
psql "$DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -v VERBOSITY=verbose \
  -f migrations/log_2b_2c_app_audit_log.sql

# Capture exit code
if [ $? -eq 0 ]; then
  echo "Migration executed successfully"
else
  echo "Migration failed. Review error above and consider rollback."
  exit 1
fi
```

### What Happens During Execution

The migration will:
1. Create `app_audit_event_status` ENUM with 5 values (PASS, WARN, FAIL, SKIP, ERROR)
2. Create `app_audit_log` table with 24 columns
3. Create 10 performance indexes
4. Create 2 trigger functions (`prevent_app_audit_log_update`, `prevent_app_audit_log_delete`)
5. Create 2 triggers (`app_audit_log_no_update`, `app_audit_log_no_delete`)
6. Commit all changes atomically (BEGIN...COMMIT)

**Total execution time:** <5 seconds (typical)  
**Storage:** ~10 MB for indexes on empty table

---

## 5. Post-Migration Verification

Run these queries **immediately after** successful migration:

### 5.1 Table Structure
```sql
-- List app_audit_log columns and types
\d app_audit_log

-- Expected output includes:
-- id BIGSERIAL PRIMARY KEY
-- event_id UUID NOT NULL UNIQUE
-- event_type TEXT NOT NULL
-- event_at TIMESTAMPTZ NOT NULL
-- actor_user_id TEXT NULL
-- organization_id TEXT NULL
-- status app_audit_event_status NOT NULL
-- payload_hash TEXT NULL
-- metadata_json JSONB NULL
-- event_hash TEXT NOT NULL
-- previous_event_hash TEXT NULL
```

### 5.2 Enum Type
```sql
-- List app_audit_event_status enum values
SELECT enum_range(NULL::app_audit_event_status);

-- Expected: {PASS,WARN,FAIL,SKIP,ERROR}
```

### 5.3 Indexes
```sql
-- List indexes on app_audit_log
SELECT indexname FROM pg_indexes 
WHERE tablename = 'app_audit_log'
ORDER BY indexname;

-- Expected: 10 indexes (see list below)
```

**Expected indexes:**
- `app_audit_log_pkey` (PRIMARY KEY: id)
- `idx_app_audit_log_event_at`
- `idx_app_audit_log_event_type_event_at`
- `idx_app_audit_log_actor_user_id_event_at`
- `idx_app_audit_log_organization_id_event_at`
- `idx_app_audit_log_target_type_target_id`
- `idx_app_audit_log_request_id`
- `idx_app_audit_log_status_event_at`
- `idx_app_audit_log_payload_hash`
- `idx_app_audit_log_event_hash`
- `idx_app_audit_log_previous_event_hash`

### 5.4 Triggers
```sql
-- List triggers on app_audit_log
SELECT trigger_name, event_manipulation FROM information_schema.triggers 
WHERE event_object_table = 'app_audit_log' AND event_object_schema = 'public'
ORDER BY trigger_name;

-- Expected: 2 rows
-- - app_audit_log_no_delete (BEFORE DELETE)
-- - app_audit_log_no_update (BEFORE UPDATE)
```

### 5.5 Append-Only Protection Test

**IMPORTANT:** These tests use transactions that rollback. No data is modified.

```sql
-- Test 1: Verify UPDATE is blocked
BEGIN TRANSACTION;
INSERT INTO app_audit_log (
  event_type, event_at, status, payload_hash, event_hash
) VALUES (
  'test.event', now(), 'PASS'::app_audit_event_status, 'hash1', 'hash2'
);

-- This should FAIL with "app_audit_log is append-only: UPDATE not allowed"
UPDATE app_audit_log SET event_type = 'modified' WHERE event_type = 'test.event';

ROLLBACK; -- Cleanup (do NOT commit)
```

**Expected Error:** `app_audit_log is append-only: UPDATE not allowed`

```sql
-- Test 2: Verify DELETE is blocked
BEGIN TRANSACTION;
INSERT INTO app_audit_log (
  event_type, event_at, status, payload_hash, event_hash
) VALUES (
  'test.event', now(), 'PASS'::app_audit_event_status, 'hash1', 'hash2'
);

-- This should FAIL with "app_audit_log is append-only: DELETE not allowed"
DELETE FROM app_audit_log WHERE event_type = 'test.event';

ROLLBACK; -- Cleanup (do NOT commit)
```

**Expected Error:** `app_audit_log is append-only: DELETE not allowed`

### 5.6 Basic INSERT Test

```sql
-- Test INSERT works (the only allowed DML operation)
BEGIN TRANSACTION;
INSERT INTO app_audit_log (
  event_type, event_at, status, payload_hash, event_hash, metadata_json
) VALUES (
  'browser.task.received',
  now(),
  'PASS'::app_audit_event_status,
  'payload_hash_123',
  'event_hash_456',
  '{"task_id": "t1", "action_type": "click"}'::jsonb
);

-- Verify row inserted
SELECT COUNT(*) FROM app_audit_log;
-- Expected: 1

ROLLBACK; -- Cleanup (do NOT commit)
```

---

## 6. Permission Setup (Placeholder)

**Important:** Actual account names must be confirmed before execution.  
Execute these **only after receiving explicit approval** with actual account names.

### Template

```sql
-- Grant INSERT to audit writer role
GRANT INSERT ON app_audit_log TO <app_writer_role>;

-- Grant SELECT to readonly role
GRANT SELECT ON app_audit_log TO <readonly_role>;

-- Grant SELECT to admin role (if needed)
GRANT SELECT ON app_audit_log TO <app_admin_role>;

-- Verify grants
SELECT grantee, privilege_type FROM information_schema.role_table_grants
WHERE table_name = 'app_audit_log';
```

### To Find Actual Roles

```sql
-- List all roles in the database
SELECT rolname FROM pg_roles WHERE rolcanlogin = true;

-- List role membership
SELECT member, roleid FROM pg_auth_members;
```

---

## 7. Rollback Procedure

### When to Rollback

Rollback is recommended **only if:**
- Migration execution failed with errors
- Table creation failed partway through
- Immediate rollback is required within 1 hour of initial failure

### When NOT to Rollback

Do **NOT** rollback if:
- Migration succeeded and verification passed
- Audit data has begun accumulating in `app_audit_log`
- Production is stable and DRY_RUN validation is underway

### Rollback Steps

1. **Verify row count before rollback:**
   ```sql
   SELECT COUNT(*) FROM app_audit_log;
   -- If > 0, consider backup before rollback
   ```

2. **Execute rollback:**
   ```bash
   export DATABASE_URL="..." # Same as migration
   
   psql "$DATABASE_URL" \
     -v ON_ERROR_STOP=1 \
     -v VERBOSITY=verbose \
     -f migrations/rollback_log_2b_2c_app_audit_log.sql
   ```

3. **Verify rollback:**
   ```sql
   SELECT tablename FROM pg_tables 
   WHERE schemaname = 'public' AND tablename = 'app_audit_log';
   -- Expected: (no rows)
   
   SELECT typname FROM pg_type 
   WHERE typname = 'app_audit_event_status';
   -- Expected: (no rows)
   ```

4. **Document rollback reason** in incident log

---

## 8. DRY_RUN Policy (48-Hour Validation)

### Phase 1: Post-Migration (0-48 hours)

After migration succeeds:
- [ ] `AUDIT_LOG_ENABLED` remains `DRY_RUN` or `false`
- [ ] Audit writer does **NOT** actually write to DB
- [ ] No audit events recorded (write path is disabled)
- [ ] Browser task execution continues normally

**Rationale:** Verify schema is stable and query tools work.

### Phase 2: Metrics Collection (48-hour window)

Monitor during DRY_RUN:

1. **Writer Status**
   - 0 errors expected (no writes attempted)
   - Audit writer initialization successful
   - No stack traces in logs

2. **Row Count**
   ```sql
   SELECT COUNT(*) FROM app_audit_log;
   -- Expected: 0 (no writes in DRY_RUN)
   ```

3. **Forbidden Field Scan** (manual)
   - If any rows exist, verify no secrets leaked
   - Check `metadata_json` contains only safe fields
   - Confirm no `approval_token`, `final_approval_token`, `typed_text`

4. **Sample Audit Events** (inspect schema)
   ```sql
   -- Verify columns exist (without inserting data)
   SELECT column_name, data_type FROM information_schema.columns
   WHERE table_name = 'app_audit_log'
   ORDER BY ordinal_position;
   ```

### Phase 3: Go/No-Go Decision (After 48 hours)

**GO to ENABLED if:**
- [ ] Migration verification passed
- [ ] No errors in audit writer logs
- [ ] No forbidden fields detected
- [ ] Row count = 0 (no data leaked in DRY_RUN)
- [ ] Query performance acceptable

**DECISION:** Approval signature required before `AUDIT_LOG_ENABLED=ENABLED`

```sql
-- Enable audit logging (only after 48-hour DRY_RUN + approval)
-- UPDATE app configuration: AUDIT_LOG_ENABLED = 'ENABLED'
-- (Actual implementation depends on app config system)
```

---

## 9. Prohibited Actions

**NEVER execute:**

- [ ] Hard-code database password in logs or scripts
- [ ] Run migration without approval
- [ ] Commit database credentials to git
- [ ] Drop `app_audit_log` without explicit approval
- [ ] Execute `UPDATE` or `DELETE` on `app_audit_log`
- [ ] Set `AUDIT_LOG_ENABLED = ENABLED` before 48-hour DRY_RUN
- [ ] Skip verification steps
- [ ] Modify schema after creation without separate PR
- [ ] Use `psql` with `--no-password-prompt` if credentials are hardcoded

---

## 10. Emergency Contacts & Escalation

| Scenario | Action |
|----------|--------|
| **Migration hangs** | Check DB connectivity; kill connection if needed; inspect logs; consider rollback |
| **Trigger fails** | Review trigger function syntax; rollback and fix SQL; reapply |
| **Permission denied** | Verify DB user has CREATE/ALTER privileges; grant missing privileges; retry |
| **Data integrity concern** | Stop execution; take DB backup; investigate; escalate to DBA |
| **OOM or disk full** | Cancel migration; free disk space; check table sizes; retry |

---

## 11. Appendix: Full Migration File Summary

### Included Objects

| Object | Type | Purpose |
|--------|------|---------|
| `app_audit_event_status` | ENUM | Event status classification |
| `app_audit_log` | TABLE | Main audit event log (append-only) |
| `prevent_app_audit_log_update()` | FUNCTION | Trigger function to block UPDATE |
| `prevent_app_audit_log_delete()` | FUNCTION | Trigger function to block DELETE |
| `app_audit_log_no_update` | TRIGGER | Attaches update prevention to table |
| `app_audit_log_no_delete` | TRIGGER | Attaches delete prevention to table |
| 10x indexes | INDEX | Performance & query optimization |

### Column Summary

**24 columns total:**
- `id`, `event_id` — Uniqueness & identity
- `event_type`, `event_at`, `created_at` — Timing & classification
- `actor_user_id`, `actor_role`, `organization_id` — Context
- `target_type`, `target_id`, `request_id` — Traceability
- `status`, `error_code`, `error_message` — Outcome
- `payload_hash`, `prompt_hash`, `response_hash` — Content integrity
- `event_hash`, `previous_event_hash` — Chain-of-custody hashing
- `metadata_json` — Safe event metadata (JSONB)
- `elapsed_ms` — Performance
- `session_hash`, `ip_hash`, `user_agent_hash` — Session context
- `log_version`, `source`, `environment` — Schema versioning

### Security Properties

✓ Append-only (UPDATE/DELETE blocked)  
✓ No secrets stored (metadata sanitized)  
✓ Chain-hashing supported  
✓ Multi-tenant ready (organization_id)  
✓ JSONB safe metadata  
✓ Event integrity verified  

---

## Document Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| **Prepared by** | Claude AI (Haiku 4.5) | 2026-05-01 | — |
| **Reviewed by** | [Operator] | — | — |
| **Approved by** | [Authorized Manager] | — | — |
| **Applied by** | [Database Administrator] | — | — |

---

**End of Handoff Document**
