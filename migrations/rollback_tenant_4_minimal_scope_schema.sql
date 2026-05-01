-- TENANT-4 Rollback: Minimal Organization Scope Schema Migration
--
-- Purpose: Drop all tables created by tenant_4_minimal_scope_schema.sql
-- Basis: Reverse dependency order (FKs dropped before referenced tables)
--
-- Rollback order (reverse of creation, respecting FK constraints):
-- 1. browser_results → task_id, agent_id FKs
-- 2. browser_approvals → task_id FKs
-- 3. browser_tasks → organization_id, agent_id FKs
-- 4. local_agents → organization_id FK
-- 5. organization_memberships → user_id, organization_id FKs
-- 6. organizations → root entity
-- 7. app_users → global user registry
--
-- Status: Proposal only (not executed)
-- WARNING: Do NOT execute without explicit approval.
-- Production rollback requires approval gate (TENANT-5).

BEGIN;

-- ============================================================================
-- Rollback Tables (reverse dependency order)
-- ============================================================================

-- 1. browser_results: Task execution results
-- FK references: task_id → browser_tasks, organization_id → organizations, agent_id → local_agents
DROP TABLE IF EXISTS browser_results;

-- 2. browser_approvals: Approval records
-- FK references: task_id → browser_tasks, organization_id → organizations, user_id FKs
DROP TABLE IF EXISTS browser_approvals;

-- 3. browser_tasks: Browser task requests
-- FK references: organization_id → organizations, agent_id → local_agents, user_id FKs
DROP TABLE IF EXISTS browser_tasks;

-- 4. local_agents: Local browser agent registry
-- FK references: organization_id → organizations, user_id FK
DROP TABLE IF EXISTS local_agents;

-- 5. organization_memberships: User ↔ Organization binding
-- FK references: user_id → app_users, organization_id → organizations
DROP TABLE IF EXISTS organization_memberships;

-- 6. organizations: Root tenant entity
-- Referenced by: organization_memberships, local_agents, browser_tasks, browser_approvals, browser_results
DROP TABLE IF EXISTS organizations;

-- 7. app_users: Global user registry
-- Referenced by: organization_memberships, local_agents, browser_tasks, browser_approvals
DROP TABLE IF EXISTS app_users;

COMMIT;

-- ============================================================================
-- Rollback Completion Note
-- ============================================================================
--
-- Status: Proposal only (not executed)
--
-- Post-rollback Verification (TENANT-5):
-- [ ] Table drops verified (SELECT FROM information_schema.tables)
-- [ ] No orphaned FKs
-- [ ] Application handles gracefully
-- [ ] Data export completed (if needed for recovery)
--
-- Recovery (if needed):
-- - Restore from backup (preferred)
-- - Re-run tenant_4_minimal_scope_schema.sql if rollback was premature
-- - Notify DBA team of any integrity issues
--

-- End of file
