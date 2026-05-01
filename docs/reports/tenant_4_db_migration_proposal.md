# TENANT-4: Minimal Organization Scope Schema Migration Proposal

**Status**: Proposal only (not executed)  
**Date**: 2026-05-01  
**Basis**: TENANT-1 (design), TENANT-2 (contracts), TENANT-3 (runtime hooks)

---

## Executive Summary

This document proposes a database migration for minimal multi-tenant organization scope support. The migration introduces 7 core tables enforcing organization-level data partitioning while maintaining backward compatibility with existing code.

**Key Properties**:
- **Single Database**: No schema-per-tenant or db-per-tenant (future enhancement)
- **Partition Key**: All operational tables use `organization_id` as partition boundary
- **Backward Compatible**: No changes to existing tables; creates new scope structure only
- **Scope Validation**: Runtime enforcement of `task.org_id == approval.org_id == agent.org_id == result.org_id`
- **Security**: No plaintext tokens, passwords, or raw hostnames in schema

---

## Table Designs

### 1. app_users: Global User Registry

**Purpose**: Centralized user identity and profile (organization-agnostic)

```sql
CREATE TABLE IF NOT EXISTS app_users (
  user_id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  display_name TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'suspended', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT NULL
);
```

**Columns**:
- `user_id`: UUID, globally unique identifier
- `email`: Unique email for login and contact (indexed for lookups)
- `display_name`: User's display name (optional)
- `status`: Account status enum; supports lifecycle management (active → suspended → deleted)
- `created_at`, `updated_at`: Audit timestamps

**Indexes**:
- `idx_app_users_email`: ON (email) — fast email lookup for authentication
- `idx_app_users_status`: ON (status) — filter by account status

**Notes**:
- Password hashes managed by separate security system (not this table)
- Contains identity and profile only
- No organization affiliation (joins via `organization_memberships`)

---

### 2. organizations: Root Tenant Entity

**Purpose**: Organization/company root record (tenant boundary)

```sql
CREATE TABLE IF NOT EXISTS organizations (
  organization_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'suspended', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT NULL
);
```

**Columns**:
- `organization_id`: UUID, unique organization identifier
- `name`: Organization name
- `status`: Org status enum; controls access to all scoped resources
- `created_at`, `updated_at`: Audit timestamps

**Indexes**:
- `idx_organizations_status`: ON (status) — filter by org status
- `idx_organizations_name`: ON (name) — find org by name

**Notes**:
- Single business entity; users can belong to multiple orgs via `organization_memberships`
- Status changes (e.g., `active` → `suspended`) affect all scoped tables
- No direct user association (users join via memberships table)

---

### 3. organization_memberships: User ↔ Organization Binding

**Purpose**: Control how users access organizations (multi-org support)

```sql
CREATE TABLE IF NOT EXISTS organization_memberships (
  membership_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  role TEXT NOT NULL
    CHECK (role IN ('owner', 'admin', 'manager', 'operator', 'viewer', 'auditor', 'local_agent')),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'suspended', 'removed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT NULL,

  CONSTRAINT fk_memberships_user FOREIGN KEY (user_id)
    REFERENCES app_users(user_id) ON DELETE CASCADE,
  CONSTRAINT fk_memberships_org FOREIGN KEY (organization_id)
    REFERENCES organizations(organization_id) ON DELETE CASCADE,
  CONSTRAINT uniq_user_org UNIQUE (user_id, organization_id)
);
```

**Columns**:
- `membership_id`: UUID, unique membership record identifier
- `user_id`: FK to `app_users`; on delete CASCADE
- `organization_id`: FK to `organizations`; on delete CASCADE
- `role`: Role in organization (TENANT-2 permission matrix defines permissions)
  - `owner`: Full control
  - `admin`: Administrative access
  - `manager`: Team/resource management
  - `operator`: Execute browser tasks
  - `viewer`: Read-only access
  - `auditor`: Audit log access only
  - `local_agent`: Browser agent (limited scope)
- `status`: Membership status (allows soft deactivation without deletion)
- `created_at`, `updated_at`: Audit timestamps

**Constraints**:
- `UNIQUE (user_id, organization_id)`: User can only have one role per org at a time
- `ON DELETE CASCADE`: If user or org deleted, membership deleted automatically

**Indexes**:
- `idx_memberships_user`: ON (user_id) — find all orgs for a user
- `idx_memberships_org`: ON (organization_id) — find all users in org
- `idx_memberships_org_role`: ON (organization_id, role) — find all users with specific role in org
- `idx_memberships_status`: ON (status) — filter by membership status

**Notes**:
- Implements TENANT-3 `organization_ids` and `active_organization_id` concept at database level
- Role is source of truth for authorization (see TENANT-2 PERMISSION_MATRIX)
- Membership status allows lifecycle management without data loss

---

### 4. local_agents: Local Browser Agent Registry

**Purpose**: Track browser agents deployed within organizations (organization-scoped)

```sql
CREATE TABLE IF NOT EXISTS local_agents (
  agent_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  registered_by_user_id TEXT,
  host_name_hash TEXT,
  agent_version TEXT,
  capabilities JSONB,
  status TEXT NOT NULL DEFAULT 'registered'
    CHECK (status IN ('registered', 'ready', 'busy', 'offline', 'error', 'disabled')),
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT NULL,

  CONSTRAINT fk_agents_org FOREIGN KEY (organization_id)
    REFERENCES organizations(organization_id) ON DELETE CASCADE,
  CONSTRAINT fk_agents_registered_by FOREIGN KEY (registered_by_user_id)
    REFERENCES app_users(user_id) ON DELETE SET NULL
);
```

**Columns**:
- `agent_id`: UUID, unique agent identifier
- `organization_id`: FK to `organizations` (REQUIRED) — agent strictly bound to single org
- `registered_by_user_id`: FK to `app_users`; user who registered the agent; ON DELETE SET NULL
- `host_name_hash`: SHA256(hostname)[:12] — NEVER raw hostname (security requirement)
- `agent_version`: Agent software version (e.g., "1.0.0")
- `capabilities`: JSONB array of capability strings (e.g., `["browser.inspect", "browser.plan_click"]`)
- `status`: Agent operational status
  - `registered`: Initial state after registration
  - `ready`: Heartbeat received, ready for tasks
  - `busy`: Currently executing task
  - `offline`: Heartbeat missing
  - `error`: Last heartbeat had error
  - `disabled`: Administratively disabled
- `last_seen_at`: Last heartbeat timestamp
- `created_at`, `updated_at`: Audit timestamps

**Indexes**:
- `idx_agents_org`: ON (organization_id) — find all agents in org
- `idx_agents_org_status`: ON (organization_id, status) — find ready agents in org
- `idx_agents_last_seen`: ON (last_seen_at) — identify stale agents

**Notes**:
- Scope boundary: Each agent belongs to exactly one organization
- Security: `host_name_hash` is stored; raw hostname never transmitted or stored
- Capabilities: JSONB allows flexible capability expression (future scalability)
- Status lifecycle: `registered` → `ready` → [busy] → `offline` or `error`

---

### 5. browser_tasks: Browser Task Requests

**Purpose**: User-requested browser automation tasks (organization-scoped)

```sql
CREATE TABLE IF NOT EXISTS browser_tasks (
  task_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  requested_by_user_id TEXT,
  agent_id TEXT,
  action_type TEXT NOT NULL,
  target_url_domain TEXT,
  selector_hash TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected', 'running', 'completed', 'failed', 'cancelled', 'timeout')),
  risk_level TEXT
    CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT NULL,

  CONSTRAINT fk_task_org FOREIGN KEY (organization_id)
    REFERENCES organizations(organization_id) ON DELETE CASCADE,
  CONSTRAINT fk_task_requester FOREIGN KEY (requested_by_user_id)
    REFERENCES app_users(user_id) ON DELETE SET NULL,
  CONSTRAINT fk_task_agent FOREIGN KEY (agent_id)
    REFERENCES local_agents(agent_id) ON DELETE SET NULL
);
```

**Columns**:
- `task_id`: UUID, unique task identifier
- `organization_id`: FK to `organizations` (REQUIRED) — task strictly bound to single org
- `requested_by_user_id`: FK to `app_users`; who requested task; ON DELETE SET NULL
- `agent_id`: FK to `local_agents`; which agent will execute; ON DELETE SET NULL; optional until assigned
- `action_type`: Type of action (e.g., "inspect_page", "click", "fill_form")
- `target_url_domain`: Domain only (never full URL with secrets, e.g., "example.com")
- `selector_hash`: SHA256(selector)[:12] — NEVER plaintext selector (security requirement)
- `status`: Task lifecycle
  - `pending`: Created, awaiting approval
  - `approved`: Approved by reviewer
  - `rejected`: Rejected by reviewer
  - `running`: Currently executing on agent
  - `completed`: Finished successfully
  - `failed`: Execution error
  - `cancelled`: User cancelled
  - `timeout`: Execution timeout
- `risk_level`: Risk assessment (triggers approval requirement)
  - NULL: Not assessed yet
  - `low`: May not require approval (depends on permission)
  - `medium`: Requires approval
  - `high`: Requires approval + audit
  - `critical`: Requires approval + multi-reviewer
- `created_at`, `updated_at`: Audit timestamps

**Indexes**:
- `idx_tasks_org`: ON (organization_id) — list all tasks in org
- `idx_tasks_org_status`: ON (organization_id, status) — filter by status
- `idx_tasks_org_created`: ON (organization_id, created_at DESC) — recent tasks first
- `idx_tasks_agent`: ON (agent_id) — find tasks for agent
- `idx_tasks_requester`: ON (requested_by_user_id) — find user's tasks

**Scope Rules** (validated at runtime):
- `task.organization_id == approval.organization_id` (if approval exists)
- `task.organization_id == agent.organization_id` (if agent assigned)
- `task.organization_id == result.organization_id` (if result exists)

**Notes**:
- Scope boundary: Each task belongs to exactly one organization
- Security: `selector_hash` prevents selector exfiltration; `target_url_domain` prevents secret leakage
- Approval model: High-risk tasks require approval before execution
- Audit trail: All state transitions (pending → approved → running → completed) logged

---

### 6. browser_approvals: Approval Records for Browser Tasks

**Purpose**: Approval workflow for high-risk browser tasks (organization-scoped)

```sql
CREATE TABLE IF NOT EXISTS browser_approvals (
  approval_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  requested_by_user_id TEXT,
  approved_by_user_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'revoked')),
  risk_level TEXT
    CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical')),
  token_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,

  CONSTRAINT fk_approval_task FOREIGN KEY (task_id)
    REFERENCES browser_tasks(task_id) ON DELETE CASCADE,
  CONSTRAINT fk_approval_org FOREIGN KEY (organization_id)
    REFERENCES organizations(organization_id) ON DELETE CASCADE,
  CONSTRAINT fk_approval_requester FOREIGN KEY (requested_by_user_id)
    REFERENCES app_users(user_id) ON DELETE SET NULL,
  CONSTRAINT fk_approval_approver FOREIGN KEY (approved_by_user_id)
    REFERENCES app_users(user_id) ON DELETE SET NULL
);
```

**Columns**:
- `approval_id`: UUID, unique approval record identifier
- `task_id`: FK to `browser_tasks`; the task being approved; ON DELETE CASCADE
- `organization_id`: FK to `organizations` (REQUIRED) — MUST match task.organization_id (runtime validation)
- `requested_by_user_id`: FK to `app_users`; who requested approval; ON DELETE SET NULL
- `approved_by_user_id`: FK to `app_users`; who approved (NULL until approval given); ON DELETE SET NULL
- `status`: Approval lifecycle
  - `pending`: Awaiting reviewer decision
  - `approved`: Approved by reviewer
  - `rejected`: Rejected by reviewer
  - `expired`: Expiration time reached without approval
  - `revoked`: Approval revoked after approval given
- `risk_level`: Risk level (echo from task.risk_level)
- `token_hash`: SHA256(approval_token) — NEVER plaintext token (security requirement)
  - Used to validate approval in browser agent communication
  - Hash-only prevents token leakage in logs, caches, error messages
- `created_at`: Approval request timestamp
- `expires_at`: Approval validity deadline (e.g., 1 hour after creation)
- `used_at`: When approval was used (timestamp of task execution start)
- `revoked_at`: When approval was revoked (if status == 'revoked')

**Indexes**:
- `idx_approvals_org`: ON (organization_id) — list all approvals in org
- `idx_approvals_task`: ON (task_id) — find approval for task
- `idx_approvals_status`: ON (status) — filter by status
- `idx_approvals_expires`: ON (expires_at) — find expired approvals for cleanup
- `idx_approvals_org_status`: ON (organization_id, status) — filter by org and status

**Scope Rules** (validated at runtime):
- `approval.organization_id == task.organization_id` (same org required)
- `expires_at > NOW()` for approval to be valid
- Approval valid only after status == 'approved' and used_at is NULL

**Notes**:
- Scope boundary: Approval strictly tied to task's organization
- Security: Token stored as hash only; plaintext token discarded after hash creation
- Expiration: Approval expires after specified time (prevents replay)
- Revocation: Admin can revoke approval even after approval given
- Audit: All timestamps and user references enable full audit trail

---

### 7. browser_results: Task Execution Results

**Purpose**: Results of executed browser tasks (organization-scoped)

```sql
CREATE TABLE IF NOT EXISTS browser_results (
  result_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  agent_id TEXT,
  status TEXT NOT NULL DEFAULT 'completed'
    CHECK (status IN ('completed', 'failed', 'timeout', 'cancelled')),
  safe_result_json JSONB,
  error_code TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_result_task FOREIGN KEY (task_id)
    REFERENCES browser_tasks(task_id) ON DELETE CASCADE,
  CONSTRAINT fk_result_org FOREIGN KEY (organization_id)
    REFERENCES organizations(organization_id) ON DELETE CASCADE,
  CONSTRAINT fk_result_agent FOREIGN KEY (agent_id)
    REFERENCES local_agents(agent_id) ON DELETE SET NULL
);
```

**Columns**:
- `result_id`: UUID, unique result record identifier
- `task_id`: FK to `browser_tasks`; the task that produced result; ON DELETE CASCADE
- `organization_id`: FK to `organizations` (REQUIRED) — MUST match task.organization_id (runtime validation)
- `agent_id`: FK to `local_agents`; which agent executed; ON DELETE SET NULL
- `status`: Result status
  - `completed`: Task completed successfully (check error_code for business-level failures)
  - `failed`: Execution error (agent crash, network error, etc.)
  - `timeout`: Task execution timeout
  - `cancelled`: Task cancelled by user
- `safe_result_json`: JSONB result data with secrets removed
  - Safe-dict applied: no passwords, tokens, cookies, raw hostnames, IP addresses
  - Contains only business-relevant output (page content, form data, etc.)
  - Audit: approved for logging and external APIs
- `error_code`: Machine-readable error code (e.g., "AGENT_TIMEOUT", "NETWORK_ERROR")
- `error_message`: Human-readable error message (must not contain secrets)
- `created_at`: Result timestamp

**Indexes**:
- `idx_results_org`: ON (organization_id) — list all results in org
- `idx_results_task`: ON (task_id) — find result for task
- `idx_results_status`: ON (status) — filter by status
- `idx_results_created`: ON (created_at DESC) — recent results first

**Scope Rules** (validated at runtime):
- `result.organization_id == task.organization_id` (same org required)
- `result.agent_id.organization_id == result.organization_id` (if agent_id present)

**Notes**:
- Scope boundary: Result strictly tied to task's organization
- Security: `safe_result_json` has secrets removed via safe_dict() (no passwords, tokens, cookies, raw hostnames, IP addresses)
- One result per task: Each task can have at most one result (FK cascade on task delete)
- Immutable: Results are append-only; no updates after creation
- Audit trail: Status and timestamps enable full execution history

---

## Cross-Organization Validation Rules

These rules are enforced at **runtime** (not database level):

### Rule 1: Task-Approval-Agent Scope Match
When a task transitions to `running`, validate:
```
task.organization_id == approval.organization_id
task.organization_id == agent.organization_id
```
**Implementation**: `assert_task_approval_agent_same_org()` in TENANT-2 contract

### Rule 2: Result-Task Scope Match
When creating a result, validate:
```
result.organization_id == task.organization_id
```
**Implementation**: `assert_result_task_same_org()` in TENANT-2 contract

### Rule 3: Audit-Task Scope Match
When logging audit event for task, validate:
```
audit.organization_id == task.organization_id
```
**Implementation**: `assert_audit_task_same_org()` in TENANT-2 contract

---

## Backward Compatibility

**No Breaking Changes**:
- New tables only; no modifications to existing tables
- Existing APIs can continue operating without organization_id (TENANT-3 build_tenant_context provides fallback: `["default-org"]`)
- All foreign keys respect cascade/set-null semantics
- No data loss; additive schema only

**Migration Path**:
1. Execute forward migration (tenant_4_minimal_scope_schema.sql)
2. TENANT-3 runtime hooks automatically provide `default-org` for unauthenticated requests
3. Gradually migrate API endpoints to populate organization_id from auth context
4. No data re-backfill needed (new data uses org scope from creation onwards)

---

## Security Considerations

### 1. No Plaintext Sensitive Data
- Tokens: Stored as `token_hash` (SHA256)
- Selectors: Stored as `selector_hash` (SHA256)
- Hostnames: Stored as `host_name_hash` (SHA256)
- Passwords: Never stored in any table (managed by separate auth system)
- OTP: Never stored

### 2. Organization Isolation
- All operational tables have `organization_id NOT NULL`
- API scopes: Users can only access resources in their `organization_ids`
- DB level: No foreign keys across orgs (enforced by design)

### 3. Audit Trail
- All tables have `created_at` and `updated_at`
- User references (`requested_by_user_id`, `approved_by_user_id`, `registered_by_user_id`) enable audit
- Approval workflow: approval_token used by browser agents (token hash prevents replay)

### 4. Secrets Management
- `safe_result_json`: Secrets removed via safe_dict() before storage
- `target_url_domain`: Domain only (no query params with secrets)
- Logs: Safe-dict applied before logging any message containing user data

---

## Indexes and Performance

### Partition Keys
- `organization_id` is implicit partition key
- Most queries should filter by `organization_id` first

### Common Query Patterns

**Pattern 1: List tasks in org**
```sql
SELECT * FROM browser_tasks WHERE organization_id = ? ORDER BY created_at DESC LIMIT 10;
```
Optimized by: `idx_tasks_org_created` (organization_id, created_at DESC)

**Pattern 2: Find pending tasks for agent**
```sql
SELECT * FROM browser_tasks WHERE organization_id = ? AND agent_id = ? AND status = 'pending';
```
Optimized by: `idx_tasks_org_status` (organization_id, status) or `idx_tasks_agent`

**Pattern 3: Find all users in org with role**
```sql
SELECT * FROM organization_memberships WHERE organization_id = ? AND role = 'operator';
```
Optimized by: `idx_memberships_org_role` (organization_id, role)

**Pattern 4: Expire old approvals**
```sql
DELETE FROM browser_approvals WHERE expires_at < NOW();
```
Optimized by: `idx_approvals_expires` (expires_at)

---

## Rollback Policy

If migration fails or rollback is needed:

1. **Immediate Rollback** (within 1 hour):
   - Execute rollback_tenant_4_minimal_scope_schema.sql
   - Restores database to pre-migration state
   - Verifies with SELECT from information_schema.tables

2. **Data Recovery** (after rollback):
   - If data written to new tables, export and archive
   - Restore application from snapshot (if needed)

3. **Root Cause Analysis**:
   - Review migration logs
   - Check FK constraint violations
   - Verify index creation succeeded

4. **Re-execution**:
   - Apply fixes
   - Test on staging
   - Execute on production with human witness

---

## Approval Gate (TENANT-5)

This migration requires explicit approval before execution in production.

### Pre-Execution Checklist
- [ ] Data backup completed
- [ ] Fallback plan documented
- [ ] Rollback tested on staging
- [ ] Migration window scheduled
- [ ] Alert/monitoring configured
- [ ] Approval from DBA team
- [ ] Approval from security team

### Post-Execution Validation
- [ ] Row count verify (should be 0 on new tables)
- [ ] FK constraint verify (SELECT constraint_name FROM information_schema.referential_constraints)
- [ ] Index usage verify (SELECT * FROM pg_indexes WHERE schemaname='public')
- [ ] Query plan verify (EXPLAIN SELECT on sample queries)
- [ ] app_audit_log alignment verify (organization_id present)
- [ ] Application health check (POST /health, verify 200 OK)

---

## Timeline and Risk Assessment

### Risk Level: **LOW**

**Why Low Risk**:
- Additive schema only (no destructive changes)
- Backward compatible (no mandatory org_id on old data)
- No locking on existing tables (new tables only)
- Rollback is straightforward (DROP TABLE)
- Test coverage: 33+ validation tests in test_tenant4_migration_sql.py

### Estimated Execution Time: **5-10 minutes**

- Forward migration: 2-3 minutes (7 CREATE TABLE + 19 indexes)
- Validation: 2-3 minutes (row count, FK, index checks)
- Monitoring: 2-5 minutes (post-execution health checks)

### Staging Requirement: **Required**

Before production execution:
1. Execute on staging database (same version, ~same data size)
2. Run all 33+ validation tests
3. Verify application startup and basic operations
4. Load test: Verify no index creation locking

---

## Dependencies and Prerequisites

### Database Requirements
- PostgreSQL 12+
- TIMESTAMPTZ support (UTC)
- JSONB support (for capabilities, safe_result_json)
- Foreign key constraints enabled

### Schema Alignment
- app_audit_log must have organization_id column (from prior migration)
- Event types documented in TENANT-2 design:
  - `BROWSER_*` events: organization_id NOT NULL
  - `SYSTEM_*` / `AGENT_*` events: organization_id NULL allowed

### Application Requirements
- TENANT-3 runtime hooks deployed (auth.py, browser_websocket_handshake.py)
- build_tenant_context() and require_membership() imported and used
- safe_dict() applied before storing results

---

## Future Enhancements (Out of Scope for TENANT-4)

### Schema-Per-Tenant (TENANT-4B)
- CREATE SCHEMA org_<organization_id>
- Replicate operational tables per schema
- Index prefixed with org_id
- Benefit: Stricter isolation, easier sharding

### DB-Per-Tenant (TENANT-4C)
- Separate PostgreSQL cluster per large customer
- Connection pooling per customer database
- Benefit: Maximum isolation, independent scaling

### Partitioning (TENANT-4D)
- Partition browser_tasks, browser_approvals, browser_results by organization_id
- Range partitioning by created_at
- Benefit: Massive scale (billions of rows), faster queries on old data

---

## Document References

- **TENANT-1 Design**: docs/reports/tenant_1_scope_design_report.md
- **TENANT-2 Contracts**: docs/reports/tenant_2_minimal_scope_schema_proposal.md + local_agent/tenant_scope_contract.py
- **TENANT-3 Runtime Hooks**: ai_orchestrator/auth.py + local_agent/browser_websocket_handshake.py
- **TENANT-4 Migration**: migrations/tenant_4_minimal_scope_schema.sql + rollback_tenant_4_minimal_scope_schema.sql
- **TENANT-4 Tests**: tests/test_tenant4_migration_sql.py

---

## Sign-Off

This proposal is ready for TENANT-5 approval gate review.

**Prepared by**: Claude Code  
**Date**: 2026-05-01  
**Status**: Proposal only — Do NOT execute without explicit approval
