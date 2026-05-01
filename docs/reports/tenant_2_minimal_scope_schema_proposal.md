# TENANT-2: Minimal Organization Scope Schema Proposal

**작성일**: 2026-05-01  
**기준 commit**: f389d46 (TENANT-1 완료)  
**상태**: Schema + Contract Proposal (DB migration 전)  
**목적**: TENANT-1 P1 Gap 대응 및 최소 schema/contract 정의

---

## 1. 목적 및 배경

### 1.1 TENANT-1 결과물

**설계 완료**:
- 조직별 데이터 분리 모델 정의
- 역할별 권한 매트릭스 정의
- WebSocket handshake organization_id 포함 설계
- P1 Gap 13개 식별

**문제점**: 아직 코드 구현 없음 → 계약과 검증 필요

### 1.2 TENANT-2 목표

**목표**:
1. TENANT-1 설계를 코드 계약으로 변환
2. 최소 schema proposal 정의 (DB는 아직 생성 X)
3. 타입 안전성 강화 (Python dataclass, TypeScript interfaces)
4. Scope check rule 정의 (auth context, organization validation)
5. 정적 검증 테스트 작성

**범위**:
- Contract definition (runtime enforcement 아님)
- Type proposal (실제 DB 변경 아님)
- Helper functions (validation logic)
- Tests (gap documentation)

---

## 2. TENANT-1 P1 Gap 대응표

| Gap | 설명 | TENANT-2 대응 | 구현 방식 |
|-----|------|-------------|---------|
| **G1** | User model에 user_id 필요 | tenant_scope_contract.py에 User contract 정의 | dataclass |
| **G2** | Organization model 필요 | tenant_scope_contract.py에 Organization contract 정의 | dataclass |
| **G3** | Membership model 필요 | tenant_scope_contract.py에 Membership contract 정의 | dataclass |
| **G4** | Auth에 organization_ids 반환 | AuthTenantContext contract 정의 | dataclass |
| **G5** | BrowserTask model 필요 | BrowserTaskScope contract 정의 | dataclass |
| **G6** | BrowserApproval model persistence | BrowserApprovalScope contract 정의 | dataclass |
| **G7** | BrowserResult model 필요 | BrowserResultScope contract 정의 | dataclass |
| **G8** | BrowserAuditEvent factory 필요 | BrowserAuditEventScope contract 정의 | dataclass |
| **G9** | WebSocket handshake org_id 추가 | AgentHelloMessage proposal 확장 | proposal doc |
| **G10** | LocalAgent model org_id 필수 | LocalAgentScope contract 정의 | dataclass |
| **G11** | AppAuditLog organization_id 확인 | AppAuditLogScope contract 정의 | dataclass |
| **G12** | Admin web browser-approval.ts type | BrowserApprovalUIType proposal | TypeScript |
| **G13** | API scope check 필요 | scope check helpers 정의 | functions |

---

## 3. 최소 Schema Proposal

### 3.1 User

```sql
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  display_name TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE users IS 'Global user records (organization-agnostic)';
COMMENT ON COLUMN users.user_id IS 'UUID, globally unique';
COMMENT ON COLUMN users.email IS 'Unique email for login and contact';
```

**특징**:
- Global entity (organization-free)
- 1명의 user는 1개 이상의 membership으로 복수 조직 소속 가능
- password_hash는 보안 key management system에서 별도 관리

### 3.2 Organization

```sql
CREATE TABLE IF NOT EXISTS organizations (
  organization_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE organizations IS 'Organization/company root records';
COMMENT ON COLUMN organizations.organization_id IS 'UUID, unique organization identifier';
```

**특징**:
- Root tenant entity
- 모든 업무 데이터의 organization_id는 여기 참조
- status로 soft delete 가능

### 3.3 Membership

```sql
CREATE TABLE IF NOT EXISTS memberships (
  membership_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  role TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  UNIQUE(user_id, organization_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (organization_id) REFERENCES organizations(organization_id)
);

COMMENT ON TABLE memberships IS 'User → Organization binding with role';
COMMENT ON COLUMN memberships.role IS 'owner|admin|manager|operator|viewer|auditor|local_agent';
```

**특징**:
- (user_id, organization_id) unique constraint → 1 user는 1 org에 최대 1 role
- role은 organization별로 다를 수 있음 (user는 org-A에서 admin, org-B에서 viewer)
- status로 membership 비활성화 가능

### 3.4 LocalAgent

```sql
CREATE TABLE IF NOT EXISTS local_agents (
  agent_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  registered_by_user_id TEXT,
  host_name_hash TEXT,
  agent_version TEXT,
  capabilities JSONB,
  status TEXT NOT NULL DEFAULT 'ready',
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (organization_id) REFERENCES organizations(organization_id),
  FOREIGN KEY (registered_by_user_id) REFERENCES users(user_id)
);

COMMENT ON TABLE local_agents IS 'Local browser agent registry (organization-scoped)';
COMMENT ON COLUMN local_agents.organization_id IS 'Required: agent belongs to exactly one organization';
COMMENT ON COLUMN local_agents.host_name_hash IS 'SHA256(hostname)[:12] - never raw hostname';
COMMENT ON COLUMN local_agents.capabilities IS 'JSON array: ["browser.inspect", "browser.plan_click", ...]';
```

**특징**:
- organization_id NOT NULL → 각 agent는 정확히 1 org 소속
- host_name_hash만 저장 (raw hostname 금지)
- registered_by_user_id로 등록자 추적

### 3.5 BrowserTask

```sql
CREATE TABLE IF NOT EXISTS browser_tasks (
  task_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  requested_by_user_id TEXT NOT NULL,
  agent_id TEXT,
  action_type TEXT,
  target TEXT,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  risk_level TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (organization_id) REFERENCES organizations(organization_id),
  FOREIGN KEY (requested_by_user_id) REFERENCES users(user_id),
  FOREIGN KEY (agent_id) REFERENCES local_agents(agent_id)
);

COMMENT ON TABLE browser_tasks IS 'Browser task requests (organization-scoped)';
COMMENT ON COLUMN browser_tasks.organization_id IS 'Required: task belongs to exactly one organization';
COMMENT ON COLUMN browser_tasks.status IS 'pending|approved|rejected|running|completed|failed|cancelled';
```

**특징**:
- organization_id NOT NULL → task는 정확히 1 org 소속
- agent_id가 같은 org에 속하는지 validate 필수
- risk_level은 approval 필요 여부 결정

### 3.6 BrowserApproval

```sql
CREATE TABLE IF NOT EXISTS browser_approvals (
  approval_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  requested_by_user_id TEXT NOT NULL,
  approved_by_user_id TEXT,
  action_type TEXT,
  risk_level TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  approval_token_hash TEXT,
  expires_at TIMESTAMPTZ,
  used_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (task_id) REFERENCES browser_tasks(task_id),
  FOREIGN KEY (organization_id) REFERENCES organizations(organization_id),
  FOREIGN KEY (requested_by_user_id) REFERENCES users(user_id),
  FOREIGN KEY (approved_by_user_id) REFERENCES users(user_id)
);

COMMENT ON TABLE browser_approvals IS 'Approval records for browser tasks (organization-scoped)';
COMMENT ON COLUMN browser_approvals.organization_id IS 'Required: must match task.organization_id';
COMMENT ON COLUMN browser_approvals.approval_token_hash IS 'SHA256 hash only, never plaintext token';
COMMENT ON COLUMN browser_approvals.status IS 'pending|approved|rejected|expired|revoked';
```

**특징**:
- organization_id NOT NULL + unique constraint on (task_id, organization_id)
- approval_token 원문은 DB 저장 금지 (hash만 저장)
- task.organization_id == approval.organization_id 검증 필수

### 3.7 BrowserResult

```sql
CREATE TABLE IF NOT EXISTS browser_results (
  result_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  agent_id TEXT,
  status TEXT NOT NULL,
  safe_result_json JSONB,
  error_summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (task_id) REFERENCES browser_tasks(task_id),
  FOREIGN KEY (organization_id) REFERENCES organizations(organization_id),
  FOREIGN KEY (agent_id) REFERENCES local_agents(agent_id)
);

COMMENT ON TABLE browser_results IS 'Task execution results (organization-scoped)';
COMMENT ON COLUMN browser_results.organization_id IS 'Required: must match task.organization_id';
COMMENT ON COLUMN browser_results.safe_result_json IS 'Result data with secrets removed via safe_dict()';
```

**특징**:
- organization_id NOT NULL
- task.organization_id == result.organization_id 검증 필수
- safe_result_json: safe_dict() 함수로 민감정보 제거 후 저장

### 3.8 AppAuditLog (기존, organization_id 확인)

```sql
CREATE TABLE IF NOT EXISTS app_audit_log (
  log_id TEXT PRIMARY KEY,
  organization_id TEXT,
  event_type TEXT NOT NULL,
  actor_user_id TEXT,
  actor_role TEXT,
  target_type TEXT,
  target_id TEXT,
  payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE app_audit_log IS 'Centralized audit log (org-scoped + system events)';
COMMENT ON COLUMN app_audit_log.organization_id IS 'NULL for system events, required for user/task events';
```

**규칙**:
- organization_id NOT NULL: user/task/approval events
- organization_id IS NULL: system/infra events (WebSocket lifecycle, agent registration, DB migration)

### 3.9 BrowserAuditEvent (기존 app_audit_log 내 특화)

```
event_type 전용 prefix:
  BROWSER_TASK_CREATED
  BROWSER_TASK_APPROVED
  BROWSER_TASK_REJECTED
  BROWSER_TASK_COMPLETED
  BROWSER_TASK_FAILED
  BROWSER_TASK_CANCELLED
  
  BROWSER_APPROVAL_REQUESTED
  BROWSER_APPROVAL_GRANTED
  BROWSER_APPROVAL_DENIED
  BROWSER_APPROVAL_EXPIRED
  BROWSER_APPROVAL_REVOKED
  
  BROWSER_RESULT_RECORDED
  BROWSER_RESULT_FAILED

payload structure:
{
  "actor_user_id": "user-id",
  "actor_role": "admin",
  "organization_id": "org-id",
  "task_id": "task-id",
  "approval_id": "approval-id",
  "agent_id": "agent-id",
  "risk_level": "high",
  "action_type": "click",
  "decision": "approved" | "rejected" | "auto-allowed" | "blocked",
  "note": "user-provided reason"
}
```

**규칙**:
- organization_id 필수 (browser task 관련)
- system event (AGENT_REGISTERED, AGENT_DISCONNECTED)는 organization_id nullable
- event_type이 BROWSER_로 시작하면 organization_id 검증 필수

---

## 4. Auth Tenant Context Contract

### 4.1 AuthTenantContext

현재:
```python
# ai_orchestrator/auth.py
{
  "actor": "username",
  "role": "owner|admin|..."
}
```

제안:
```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class AuthTenantContext:
  """인증된 사용자의 조직별 권한 정보"""
  
  actor_user_id: str  # G1: User model에 user_id 필요
  actor_email: str  # optional but recommended
  actor_role: str  # membership 레벨의 role (org-specific)
  
  organization_ids: List[str]  # G4: 사용자가 소속된 모든 org
  active_organization_id: str  # 현재 활성 org (필수, organization_ids에 포함되어야 함)
  
  is_local_agent: bool = False  # agent로 접속한 경우
  agent_id: Optional[str] = None  # agent 접속 시에만 유입
  
  def has_access_to_organization(self, org_id: str) -> bool:
    """해당 조직에 접근 권한이 있는지 확인"""
    return org_id in self.organization_ids
  
  def require_access_to_organization(self, org_id: str) -> None:
    """해당 조직 접근 권한 필수, 없으면 raise"""
    if not self.has_access_to_organization(org_id):
      raise ValueError(f"No access to organization {org_id}")
  
  def can_perform_action(self, action: str, org_id: str) -> bool:
    """특정 조직에서 action 가능 여부"""
    # 향후 permission matrix로 확장
    return self.has_access_to_organization(org_id)
```

**규칙**:
- active_organization_id가 없으면 조직별 데이터 조회 금지
- active_organization_id는 organization_ids에 반드시 포함
- 다른 org의 데이터 접근 시도 → 403 Forbidden

### 4.2 Scope Validation Helpers

```python
def validate_auth_context(ctx: AuthTenantContext) -> None:
  """Auth context 최소 요구사항 검증"""
  if not ctx.actor_user_id:
    raise ValueError("actor_user_id required")
  if not ctx.organization_ids:
    raise ValueError("organization_ids required (at least 1)")
  if not ctx.active_organization_id:
    raise ValueError("active_organization_id required")
  if ctx.active_organization_id not in ctx.organization_ids:
    raise ValueError("active_organization_id not in organization_ids")

def require_active_organization(ctx: AuthTenantContext) -> str:
  """active_organization_id 필수"""
  validate_auth_context(ctx)
  return ctx.active_organization_id

def require_membership(ctx: AuthTenantContext, org_id: str) -> None:
  """특정 조직 membership 필수"""
  if not ctx.has_access_to_organization(org_id):
    raise ValueError(f"User {ctx.actor_user_id} not member of {org_id}")

def require_role(ctx: AuthTenantContext, org_id: str, allowed_roles: List[str]) -> None:
  """특정 조직에서 특정 role 필수 (향후 membership.role 조회)"""
  require_membership(ctx, org_id)
  # TODO: DB에서 user의 actual role 조회 후 검증
  # if ctx.actor_role not in allowed_roles:
  #   raise ValueError(f"User {ctx.actor_user_id} role {ctx.actor_role} not in {allowed_roles}")
```

---

## 5. Organization Scope Contracts

### 5.1 LocalAgentScope (G10)

```python
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class LocalAgentScope:
  """로컬 에이전트 조직 범위 계약"""
  
  agent_id: str
  organization_id: str  # G10: required
  registered_by_user_id: Optional[str] = None
  host_name_hash: str = ""  # SHA256 hash only
  agent_version: str = ""
  capabilities: List[str] = None
  status: str = "ready"
  
  def __post_init__(self):
    if not self.organization_id:
      raise ValueError("LocalAgent requires organization_id (G10)")
    if self.host_name_hash and "hostname=" in self.host_name_hash.lower():
      raise ValueError("raw hostname not allowed; use host_name_hash")
    if not self.capabilities:
      self.capabilities = []
  
  def safe_dict(self):
    """Safe representation (no secrets)"""
    return {
      "agent_id": self.agent_id,
      "organization_id": self.organization_id,
      "host_name_hash": self.host_name_hash,
      "agent_version": self.agent_version,
      "capabilities": self.capabilities,
      "status": self.status,
    }
```

### 5.2 BrowserTaskScope (G5)

```python
@dataclass
class BrowserTaskScope:
  """브라우저 태스크 조직 범위 계약"""
  
  task_id: str
  organization_id: str  # G5: required
  requested_by_user_id: str
  agent_id: Optional[str] = None
  action_type: str = ""
  risk_level: str = "low"
  status: str = "pending"
  
  def __post_init__(self):
    if not self.organization_id:
      raise ValueError("BrowserTask requires organization_id (G5)")
    if not self.requested_by_user_id:
      raise ValueError("BrowserTask requires requested_by_user_id")
```

### 5.3 BrowserApprovalScope (G6)

```python
@dataclass
class BrowserApprovalScope:
  """브라우저 승인 조직 범위 계약"""
  
  approval_id: str
  task_id: str
  organization_id: str  # G6: required
  requested_by_user_id: str
  approved_by_user_id: Optional[str] = None
  risk_level: str = ""
  status: str = "pending"
  approval_token_hash: str = ""  # SHA256 hash, never plaintext
  
  def __post_init__(self):
    if not self.organization_id:
      raise ValueError("BrowserApproval requires organization_id (G6)")
    if not self.approval_token_hash:
      raise ValueError("BrowserApproval requires approval_token_hash (not plaintext)")
    if "approval_token=" in self.approval_token_hash or self.approval_token_hash.startswith("token:"):
      raise ValueError("plaintext approval_token not allowed; use SHA256 hash")
```

### 5.4 BrowserResultScope (G7)

```python
@dataclass
class BrowserResultScope:
  """브라우저 결과 조직 범위 계약"""
  
  result_id: str
  task_id: str
  organization_id: str  # G7: required
  agent_id: Optional[str] = None
  status: str = "completed"
  
  def __post_init__(self):
    if not self.organization_id:
      raise ValueError("BrowserResult requires organization_id (G7)")
    if not self.task_id:
      raise ValueError("BrowserResult requires task_id")
```

### 5.5 BrowserAuditEventScope (G8)

```python
@dataclass
class BrowserAuditEventScope:
  """브라우저 감사 이벤트 조직 범위 계약"""
  
  event_id: str
  event_type: str  # BROWSER_TASK_*, BROWSER_APPROVAL_*, etc.
  task_id: Optional[str] = None
  approval_id: Optional[str] = None
  organization_id: Optional[str] = None  # G8: required for browser tasks, None for system
  actor_user_id: Optional[str] = None
  actor_role: Optional[str] = None
  
  def __post_init__(self):
    # G8: browser task event는 organization_id 필수
    if self.event_type.startswith("BROWSER_") and not self.organization_id:
      raise ValueError(
        f"BrowserAuditEvent {self.event_type} requires organization_id (G8)"
      )
    # system event (AGENT_*, etc.)는 organization_id nullable
```

---

## 6. Cross-Organization Scope Rules

### 6.1 Task / Approval / Agent Same Org Rule

```python
def assert_task_approval_agent_same_org(
    task: BrowserTaskScope,
    approval: BrowserApprovalScope,
    agent: LocalAgentScope
) -> None:
  """
  RULE: task.org_id == approval.org_id == agent.org_id
  
  위반 시: ValueError 발생 → task dispatch 거부
  """
  if task.organization_id != approval.organization_id:
    raise ValueError(
      f"task.org={task.organization_id} != approval.org={approval.organization_id}"
    )
  if task.organization_id != agent.organization_id:
    raise ValueError(
      f"task.org={task.organization_id} != agent.org={agent.organization_id}"
    )
  # all match: OK
```

### 6.2 Result / Task Same Org Rule

```python
def assert_result_task_same_org(
    result: BrowserResultScope,
    task: BrowserTaskScope
) -> None:
  """
  RULE: result.org_id == task.org_id
  
  위반 시: ValueError 발생 → result 저장 거부
  """
  if result.organization_id != task.organization_id:
    raise ValueError(
      f"result.org={result.organization_id} != task.org={task.organization_id}"
    )
```

### 6.3 Audit / Task Same Org Rule

```python
def assert_audit_task_same_org(
    audit_event: BrowserAuditEventScope,
    task: BrowserTaskScope
) -> None:
  """
  RULE: audit.org_id == task.org_id
  
  위반 시: WARNING log → audit에 SCOPE_MISMATCH event 기록
  """
  if audit_event.organization_id and task.organization_id:
    if audit_event.organization_id != task.organization_id:
      logger.warning(
        f"audit.org={audit_event.organization_id} != task.org={task.organization_id} "
        f"(audit_id={audit_event.event_id}, task_id={task.task_id})"
      )
      # 로그만 하고 진행 (복구 불가능하므로 blocking 아님)
```

---

## 7. WebSocket Handshake Proposal (G9)

### 7.1 현재 AgentHelloMessage

```python
@dataclass
class AgentHelloMessage:
  message_type: str = "agent.hello"
  agent_id: str = ""
  agent_version: str = ""
  host_name_hash: str = ""
  capabilities: list[str] = field(default_factory=...)
  mode: str = "read_only"
  audit_enabled: bool = True
  approval_required: bool = True
  timestamp: str = field(default_factory=_iso8601_now)
```

**문제**: organization_id 없음

### 7.2 제안: organization_id + registration_user_id 추가

```python
@dataclass
class AgentHelloMessage:
  message_type: str = "agent.hello"
  agent_id: str = ""
  agent_version: str = ""
  
  # G9: 추가 필드
  organization_id: str = ""  # agent 소속 조직 (필수)
  registration_user_id: Optional[str] = None  # agent 등록자 (선택)
  
  host_name_hash: str = ""  # SHA256 hash only
  capabilities: list[str] = field(default_factory=...)
  mode: str = "read_only"
  audit_enabled: bool = True
  approval_required: bool = True
  timestamp: str = field(default_factory=_iso8601_now)
  
  def __post_init__(self):
    if not self.organization_id:
      raise ValueError("AgentHelloMessage requires organization_id (G9)")
    if not self.agent_id:
      raise ValueError("AgentHelloMessage requires agent_id")
```

### 7.3 ServerPolicyMessage 확장

```python
@dataclass
class ServerPolicyMessage:
  message_type: str = "server.policy"
  
  # G9: 추가 필드
  organization_id: str = ""  # agent 소속 조직
  agent_id: str = ""
  
  mode: str = "read_only"
  allow_execute: bool = False
  allow_submit: bool = False
  allow_password_input: bool = False
  allow_otp_input: bool = False
  require_approval: bool = True
  heartbeat_interval_sec: int = 30
  timestamp: str = field(default_factory=_iso8601_now)
```

**규칙**:
- client와 server의 organization_id는 일치해야 함
- 불일치 시: connection reject

---

## 8. Admin Web Type Proposal (G12)

### 8.1 현재 상태

```typescript
// admin-web/src/types/auth.ts
export type UserRole = "viewer" | "admin" | "owner" | (string & {});
export interface CurrentUser {
  actor: string;
  role: UserRole;
}
```

**문제**: organization_id 없음, browser-approval.ts 타입 없음

### 8.2 제안: browser-approval.ts

```typescript
// admin-web/src/types/browser-approval.ts

export type BrowserApprovalStatus = 
  | 'pending' 
  | 'approved' 
  | 'rejected' 
  | 'expired' 
  | 'revoked';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface BrowserApproval {
  approval_id: string;
  task_id: string;
  
  // G12: organization scope
  organization_id: string;  // internal only, don't display
  
  requested_by_user_id: string;
  approved_by_user_id?: string | null;
  
  action_type: string;
  risk_level: RiskLevel;
  status: BrowserApprovalStatus;
  
  // token management
  approval_token_hash?: string;  // hash only, never plaintext
  expires_at?: string;  // ISO 8601
  used_at?: string | null;
  
  // timestamps
  created_at: string;  // ISO 8601
  updated_at: string;
}

export interface BrowserApprovalListItem {
  approval_id: string;
  task_id: string;
  requested_by_user_id: string;
  action_type: string;
  risk_level: RiskLevel;
  status: BrowserApprovalStatus;
  expires_at?: string;
  created_at: string;
}

export interface BrowserTask {
  task_id: string;
  organization_id: string;  // internal only
  requested_by_user_id: string;
  action_type: string;
  target: string;
  description: string;
  status: 'pending' | 'approved' | 'rejected' | 'running' | 'completed' | 'failed';
  risk_level: RiskLevel;
  created_at: string;
}
```

### 8.3 확장: AuthTenantContext

```typescript
// admin-web/src/types/auth.ts

export interface AuthTenantContext {
  actor_user_id: string;
  actor_role: 'owner' | 'admin' | 'manager' | 'operator' | 'viewer' | 'auditor';
  
  // G4: organization scope
  organization_ids: string[];
  active_organization_id: string;
}

export const useAuthContext = (): AuthTenantContext => {
  // implementation
};
```

---

## 9. Permission Matrix 확정

### 9.1 Role 정의

| Role | 설명 | User 관리 | Task/Approval | Agent | Audit |
|------|------|---------|---------------|-------|-------|
| **owner** | 조직 소유자 | ✓ full | ✓ full | ✓ full | ✓ full |
| **admin** | 조직 관리자 | ✗ | ✓ full | ✓ full | ✓ full |
| **manager** | 프로젝트 관리자 | ✗ | ✓ partial | ✗ | △ own |
| **operator** | 작업 담당자 | ✗ | △ own | ✗ | △ own |
| **viewer** | 읽기 전용 | ✗ | △ read | ✗ | △ read |
| **auditor** | 감사 담당자 | ✗ | ✗ | ✗ | ✓ full |
| **local_agent** | 로컬 에이전트 | ✗ | △ assigned | ✗ | ✗ |

### 9.2 Action별 Role 필요 조건

| Action | owner | admin | manager | operator | viewer | auditor | agent |
|--------|-------|-------|---------|----------|--------|---------|-------|
| task 생성 | ✓ | ✓ | ✓ | - | - | - | - |
| task 승인 | ✓ | ✓ | △ | - | - | - | - |
| task 거부 | ✓ | ✓ | △ | - | - | - | - |
| task 조회 (all) | ✓ | ✓ | - | - | - | - | - |
| task 조회 (own) | ✓ | ✓ | ✓ | ✓ | - | - | - |
| approval 조회 | ✓ | ✓ | △ | - | - | - | - |
| agent 조회 | ✓ | ✓ | - | - | - | - | - |
| agent 등록 | ✓ | ✓ | - | - | - | - | - |
| audit 조회 (all) | ✓ | ✓ | - | - | - | ✓ | - |
| audit 조회 (own) | ✓ | ✓ | - | - | - | ✓ | - |
| user 초대 | ✓ | - | - | - | - | - | - |
| user 삭제 | ✓ | - | - | - | - | - | - |
| org 설정 | ✓ | - | - | - | - | - | - |
| task 수신 (assigned) | - | - | - | - | - | - | ✓ |
| result callback | - | - | - | - | - | - | ✓ |

---

## 10. Gap 대응 완료 체크리스트

- ✅ **G1**: User model에 user_id 필요 → AuthTenantContext에 actor_user_id 포함
- ✅ **G2**: Organization model 필요 → schema proposal
- ✅ **G3**: Membership model 필요 → schema proposal
- ✅ **G4**: Auth에 organization_ids 반환 → AuthTenantContext 정의
- ✅ **G5**: BrowserTask model 필요 → BrowserTaskScope contract + schema
- ✅ **G6**: BrowserApproval persistence → BrowserApprovalScope contract + schema
- ✅ **G7**: BrowserResult model 필요 → BrowserResultScope contract + schema
- ✅ **G8**: BrowserAuditEvent factory → BrowserAuditEventScope contract
- ✅ **G9**: WebSocket org_id + registration_user_id → proposal
- ✅ **G10**: LocalAgent org_id 필수 → LocalAgentScope contract + schema
- ✅ **G11**: AppAuditLog organization_id 확인 → schema proposal
- ✅ **G12**: Admin browser-approval.ts type → TypeScript proposal
- ✅ **G13**: API scope check rule → helper functions + validation rules

---

## 11. 다음 단계 (TENANT-3)

### 11.1 Minimal Implementation

1. **Auth 확장** → organization_ids 반환
2. **DataClass 추가** → tenant_scope_contract.py
3. **Helper 함수** → scope check validators
4. **WebSocket 확장** → AgentHelloMessage.organization_id
5. **Admin type** → browser-approval.ts
6. **API scope** → 모든 query에 organization_id 필터

### 11.2 Test 추가

1. AuthTenantContext 검증
2. scope mismatch detection
3. organization access control
4. audit event scope
5. WebSocket handshake org_id

### 11.3 불가능한 것들 (TENANT-4+)

- DB migration 생성/실행 (TENANT-3에서)
- 운영 연결
- schema-per-tenant
- db-per-tenant

---

## 12. 현재 Gaps

### Open Questions

1. **Password management**: user password_hash는 어디에?
   - 제안: 별도 security key management system (현재 scope 밖)

2. **API client auth**: 기존 BasicAuth 유지?
   - 제안: email + password_hash 검증 후 AuthTenantContext 반환

3. **admin-web 접속 flow**: organization selector 필요?
   - 제안: login 후 기본 조직 선택 flow 또는 context switching

4. **Multi-org user**: 여러 조직의 member인 user UI?
   - 제안: sidebar에 조직 목록 + switch

---

## 13. Reference

### TENANT-1 Output
- `docs/reports/tenant_1_scope_design_report.md`
- `tests/test_tenant_scope_design.py`

### Existing Code
- `ai_orchestrator/auth.py`: Current auth
- `local_agent/browser_websocket_handshake.py`: WebSocket schema
- `admin-web/src/types/auth.ts`: Current types

### Next Steps
- TENANT-3: Implementation (auth, dataclass, helpers, tests)
- TENANT-4: DB migration (schema creation)
- TENANT-5: Schema-per-tenant (future)

---

**최종 판정**: PROPOSAL (Schema + Contract 정의 완료, DB migration 전)

다음: TENANT-3 Minimal Implementation Hooks
