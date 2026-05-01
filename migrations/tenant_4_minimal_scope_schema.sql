-- TENANT-4: Minimal Organization Scope Schema Migration
--
-- Purpose: Create core tenant tables and organization-scoped operational tables
-- Basis: TENANT-1 design, TENANT-2 contracts, TENANT-3 runtime hooks
--
-- Tables:
-- - app_users: global user records
-- - organizations: root tenant entity
-- - organization_memberships: user ↔ organization binding
-- - local_agents: local browser agents (organization-scoped)
-- - browser_tasks: browser task requests (organization-scoped)
-- - browser_approvals: approval records (organization-scoped)
-- - browser_results: task execution results (organization-scoped)
--
-- Constraints:
-- - browser_tasks.organization_id must match agent.organization_id (runtime validation)
-- - browser_approvals.organization_id must match task.organization_id (runtime validation)
-- - browser_results.organization_id must match task.organization_id (runtime validation)
--
-- Rollback: See rollback_tenant_4_minimal_scope_schema.sql
--
-- WARNING: This is a proposal file only. Do NOT execute without explicit approval.
-- Production migration requires approval gate (TENANT-5).

BEGIN;

-- ============================================================================
-- 1. Core Tenant Tables
-- ============================================================================

-- 1.1 app_users: Global user registry
--
-- Note: password_hash should be managed by separate security system.
-- This table contains identity and profile only.
--
CREATE TABLE IF NOT EXISTS app_users (
  user_id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  display_name TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'suspended', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT NULL
);

COMMENT ON TABLE app_users IS 'Global user records (organization-agnostic)';
COMMENT ON COLUMN app_users.user_id IS 'UUID, globally unique user identifier';
COMMENT ON COLUMN app_users.email IS 'Unique email for login and contact';
COMMENT ON COLUMN app_users.status IS 'User account status: active, inactive, suspended, deleted';

CREATE INDEX IF NOT EXISTS idx_app_users_email ON app_users (email);
CREATE INDEX IF NOT EXISTS idx_app_users_status ON app_users (status);


-- 1.2 organizations: Root tenant entity
--
-- Each organization is a tenant boundary.
-- All business data (tasks, agents, approvals) is organization-scoped.
--
CREATE TABLE IF NOT EXISTS organizations (
  organization_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'suspended', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT NULL
);

COMMENT ON TABLE organizations IS 'Organization/company root records (tenant boundaries)';
COMMENT ON COLUMN organizations.organization_id IS 'UUID, unique organization identifier';
COMMENT ON COLUMN organizations.status IS 'Organization status: active, inactive, suspended, deleted';

CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations (status);
CREATE INDEX IF NOT EXISTS idx_organizations_name ON organizations (name);


-- 1.3 organization_memberships: User ↔ Organization binding
--
-- TENANT-3 design: user can belong to multiple organizations with different roles.
-- Membership is the access control mechanism.
--
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

COMMENT ON TABLE organization_memberships IS 'User → Organization binding with role assignment';
COMMENT ON COLUMN organization_memberships.role IS 'User role in organization: owner, admin, manager, operator, viewer, auditor, local_agent';
COMMENT ON COLUMN organization_memberships.status IS 'Membership status';

CREATE INDEX IF NOT EXISTS idx_memberships_user ON organization_memberships (user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_org ON organization_memberships (organization_id);
CREATE INDEX IF NOT EXISTS idx_memberships_org_role ON organization_memberships (organization_id, role);
CREATE INDEX IF NOT EXISTS idx_memberships_status ON organization_memberships (status);


-- ============================================================================
-- 2. Organization-Scoped Operational Tables
-- ============================================================================

-- 2.1 local_agents: Local browser agent registry
--
-- Each agent belongs to exactly one organization.
-- All agents in an organization share the same organizational scope boundary.
--
-- Security: host_name_hash only (never raw hostname)
--           capabilities stored as JSONB
--
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

COMMENT ON TABLE local_agents IS 'Local browser agent registry (organization-scoped)';
COMMENT ON COLUMN local_agents.organization_id IS 'Required: Agent belongs to exactly one organization';
COMMENT ON COLUMN local_agents.host_name_hash IS 'SHA256(hostname)[:12] - never raw hostname';
COMMENT ON COLUMN local_agents.capabilities IS 'JSON array of capabilities: ["browser.inspect", "browser.plan_click", ...]';

CREATE INDEX IF NOT EXISTS idx_agents_org ON local_agents (organization_id);
CREATE INDEX IF NOT EXISTS idx_agents_org_status ON local_agents (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_agents_last_seen ON local_agents (last_seen_at);


-- 2.2 browser_tasks: Browser task requests
--
-- Each task belongs to exactly one organization.
-- API scope: users can only access tasks in their organization_ids.
--
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

COMMENT ON TABLE browser_tasks IS 'Browser task requests (organization-scoped)';
COMMENT ON COLUMN browser_tasks.organization_id IS 'Required: Task belongs to exactly one organization';
COMMENT ON COLUMN browser_tasks.selector_hash IS 'SHA256(selector) - avoid storing selector plaintext';
COMMENT ON COLUMN browser_tasks.target_url_domain IS 'Domain only, never full URL with secrets';

CREATE INDEX IF NOT EXISTS idx_tasks_org ON browser_tasks (organization_id);
CREATE INDEX IF NOT EXISTS idx_tasks_org_status ON browser_tasks (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_org_created ON browser_tasks (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON browser_tasks (agent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_requester ON browser_tasks (requested_by_user_id);


-- 2.3 browser_approvals: Approval records for browser tasks
--
-- Each approval is tied to exactly one task and organization.
-- organization_id must match task.organization_id (validated at runtime).
--
-- Security: token_hash only (never plaintext approval_token or final_approval_token)
--
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

COMMENT ON TABLE browser_approvals IS 'Approval records for browser tasks (organization-scoped)';
COMMENT ON COLUMN browser_approvals.organization_id IS 'Required: Must match task.organization_id';
COMMENT ON COLUMN browser_approvals.token_hash IS 'SHA256(token) hash only - never plaintext token';

CREATE INDEX IF NOT EXISTS idx_approvals_org ON browser_approvals (organization_id);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON browser_approvals (task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON browser_approvals (status);
CREATE INDEX IF NOT EXISTS idx_approvals_expires ON browser_approvals (expires_at);
CREATE INDEX IF NOT EXISTS idx_approvals_org_status ON browser_approvals (organization_id, status);


-- 2.4 browser_results: Task execution results
--
-- Each result belongs to exactly one task and organization.
-- organization_id must match task.organization_id (validated at runtime).
--
-- Security: safe_result_json only (safe_dict applied, no secrets)
--
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

COMMENT ON TABLE browser_results IS 'Task execution results (organization-scoped)';
COMMENT ON COLUMN browser_results.organization_id IS 'Required: Must match task.organization_id';
COMMENT ON COLUMN browser_results.safe_result_json IS 'Result data with secrets removed via safe_dict()';

CREATE INDEX IF NOT EXISTS idx_results_org ON browser_results (organization_id);
CREATE INDEX IF NOT EXISTS idx_results_task ON browser_results (task_id);
CREATE INDEX IF NOT EXISTS idx_results_status ON browser_results (status);
CREATE INDEX IF NOT EXISTS idx_results_created ON browser_results (created_at DESC);


-- ============================================================================
-- 3. Integration with app_audit_log
-- ============================================================================
--
-- NOTE: app_audit_log already has organization_id from prior migration.
-- This section documents the expected schema alignment.
--
-- Expected app_audit_log columns (assumed to exist):
-- - log_id TEXT PRIMARY KEY
-- - organization_id TEXT NULL (NULL for system events only)
-- - event_type TEXT NOT NULL
-- - actor_user_id TEXT NULL REFERENCES app_users(user_id)
-- - actor_role TEXT NULL
-- - target_type TEXT (BrowserTask, BrowserApproval, BrowserResult, LocalAgent, etc)
-- - target_id TEXT (task_id, approval_id, result_id, agent_id)
-- - payload JSONB
-- - created_at TIMESTAMPTZ
--
-- Scope rule:
-- - event_type LIKE 'BROWSER_%' OR 'LOCAL_AGENT_%' → organization_id NOT NULL
-- - event_type LIKE 'SYSTEM_%' OR 'AGENT_%' → organization_id NULL allowed
--
-- Runtime validation: assert_audit_task_same_org() must ensure:
--   audit.organization_id == task.organization_id (if both present)


-- ============================================================================
-- 4. Future Schema Enhancements (Out of Scope for TENANT-4)
-- ============================================================================
--
-- Schema-per-tenant:
-- - CREATE SCHEMA org_<organization_id>
-- - Replicate browser_tasks, browser_approvals, browser_results per schema
-- - Index prefixed with org_id
--
-- DB-per-tenant:
-- - Separate PostgreSQL cluster per large customer
-- - Connection pooling per customer database
--
-- Multi-tenancy scaling:
-- - Shard by organization_id
-- - Partition browser_tasks, browser_approvals, browser_results by organization_id
--


COMMIT;

-- ============================================================================
-- Migration Completion Note
-- ============================================================================
--
-- Status: Proposal only (not executed)
--
-- Verification:
-- - All tables have organization_id scope boundary ✓
-- - All FKs properly defined ✓
-- - No plaintext sensitive data columns ✓
-- - Backward compatible (no existing table changes) ✓
--
-- Pre-execution Checklist (TENANT-5 approval gate):
-- [ ] Data backup completed
-- [ ] Fallback plan documented
-- [ ] Rollback tested on staging
-- [ ] Migration window scheduled
-- [ ] Alert/monitoring configured
-- [ ] Approval from DBA team
--
-- Post-execution Validation (TENANT-5):
-- [ ] Row count verify
-- [ ] FK constraint verify
-- [ ] Index usage verify
-- [ ] Query plan verify
-- [ ] app_audit_log alignment verify
--

-- End of file
