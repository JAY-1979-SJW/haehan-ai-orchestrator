# TENANT-1: 조직별 데이터 분리 설계 보고서

**작성일**: 2026-05-01  
**상태**: 설계 제안 (운영 DB 변경 전)  
**범위**: 사용자/회사/조직별 데이터 접근 범위 설계

---

## 1. Executive Summary

현재 haehan-ai-orchestrator는:
- **기본 역할 기반 auth만 존재**: actor + role (owner/admin/manager/operator/viewer/auditor)
- **organization/tenant/membership 개념 전무**
- **Browser task, approval, local agent, audit log 코드 부분적 구현 상태**

본 보고서는 운영 WebSocket 연결 전에 조직별 데이터 범위를 명확히 고정하기 위한 설계안을 제시한다.

**주요 결정 사항:**
1. 단일 DB + organization_id 강제 (향후 schema-per-tenant, db-per-tenant 확장 가능)
2. user → organization membership으로 조직 소속 관리
3. task/approval/agent/audit 모두 organization_id 필수
4. API는 current_user의 organization_id 기준으로 scope 강제
5. admin UI는 조직별 데이터만 표시

---

## 2. 현황 분석

### 2.1 기존 Auth 구조

**파일**: `ai_orchestrator/auth.py`, `admin-web/src/types/auth.ts`

```python
# 반환값 구조
{
  "actor": "username",
  "role": "owner|admin|manager|operator|viewer|auditor"
}
```

**문제점**:
- organization_id 없음
- user_id (고유 식별자) 없음
- membership/tenant 정보 없음
- 조직 간 데이터 격리 불가능

### 2.2 Approval 관리 구조

**파일**: `approval_manager.py`

```python
_store[token_id] = {
  "task_id": task.task_id,
  "risk_level": risk.risk_level,
  "issued_at": time.time(),
  "approved": False,
  "rejected": False,
}
```

**문제점**:
- organization_id 없음
- approval_id 별도 구조 없음
- approval_token/final_approval_token 원문 저장 (향후 해시 필요)
- persistent store 없음 (메모리 기반)

### 2.3 Audit 로깅

**파일**: `ai_orchestrator/audit_logger.py`, `audit_logger.py`

현황:
- JSONL 파일 기반 append-only
- 기본 event_type 정의 있음
- organization_id 필드 없음
- browser task, local agent audit event type 부분 정의

**문제점**:
- organization_id 누락으로 multi-tenant 조회 불가능
- browser task audit factory 없음
- event_type에 "BROWSER_TASK_" prefix 관련 항목 부재

### 2.4 WebSocket Handshake

**파일**: `local_agent/browser_websocket_handshake.py`

```python
@dataclass
class AgentHelloMessage:
  agent_id: str
  host_name_hash: str  # SHA256 hash only
  capabilities: list[str]
  mode: str  # read_only
  audit_enabled: bool
  approval_required: bool
```

**문제점**:
- organization_id 없음
- registered_by_user_id 없음
- agent를 조직에 바인딩할 수 없음

### 2.5 Local Agent 구조

**파일**: `local_agent/agent.py`, `local_agent/config.py`

현황:
- agent_id로 고유성 보장
- hostname hash로 host 식별 (원문 제외)
- 기본 config 구조

**문제점**:
- organization_id 없음
- registration_user_id 없음
- agent → organization 매핑 없음

---

## 3. Tenant Scope Model 설계

### 3.1 기본 원칙

**P1: 조직 우선 (Organization First)**
- user는 organization에 membership으로 소속
- 모든 업무 객체(task/approval/agent/audit)는 organization_id 필수
- API는 current_user의 organization_id 기준으로 데이터 필터링

**P2: 역할 기반 권한 (Role-Based Access)**
- organization 내 역할 정의 (owner, admin, manager, operator, viewer, auditor)
- 역할별 권한 매트릭스로 명확히 정의

**P3: 감사 추적 (Audit Trail)**
- 모든 주요 작업 이벤트 기록
- organization_id + actor_user_id + timestamp로 추적 가능

### 3.2 Entity Model

#### 3.2.1 User

```python
@dataclass
class User:
  user_id: str  # UUID
  username: str  # unique global
  email: str  # unique global
  password_hash: str
  created_at: datetime
  updated_at: datetime
```

**Scope**: Global (system-level)  
**Membership 필수**: User는 organization에 1개 이상 membership으로 소속

#### 3.2.2 Organization

```python
@dataclass
class Organization:
  organization_id: str  # UUID
  name: str
  created_at: datetime
  updated_at: datetime
```

**Scope**: Root  
**특징**:
- 사용자/회사/프로젝트별 데이터 경계
- 1개 이상의 membership 보유

#### 3.2.3 Membership

```python
@dataclass
class Membership:
  membership_id: str  # UUID
  user_id: str
  organization_id: str
  role: str  # owner, admin, manager, operator, viewer, auditor, local_agent
  created_at: datetime
  updated_at: datetime
  is_active: bool = True
```

**Scope**: Organization  
**특징**:
- user와 organization의 관계
- user_id는 global하지만 membership은 org별로 unique
- role은 membership 레벨에서 정의 (user가 여러 org에서 다른 role 가능)

#### 3.2.4 LocalAgent

```python
@dataclass
class LocalAgent:
  agent_id: str  # UUID
  organization_id: str  # 필수
  registered_by_user_id: str  # Membership 있는 user
  host_name_hash: str  # SHA256(hostname)[:12]
  agent_version: str
  capabilities: list[str]
  status: str  # ready, busy, offline, error
  last_seen_at: datetime
  created_at: datetime
  updated_at: datetime
```

**Scope**: Organization  
**특징**:
- 각 agent는 1개 organization에만 소속
- 다른 org의 task를 받을 수 없음
- registration_user_id로 등록자 추적

#### 3.2.5 BrowserTask

```python
@dataclass
class BrowserTask:
  task_id: str  # UUID
  organization_id: str  # 필수
  requested_by_user_id: str
  action_type: str
  target: str
  description: str
  status: str  # pending, approved, rejected, running, completed, failed
  risk_level: str  # low, medium, high, critical
  result: dict = None
  created_at: datetime
  updated_at: datetime
```

**Scope**: Organization  
**특징**:
- BrowserTask는 정확히 1개 organization 소속
- approval과 1:1 연계 (approval_id 필드 추가 가능)
- result는 task 완료 후 저장

#### 3.2.6 BrowserApproval

```python
@dataclass
class BrowserApproval:
  approval_id: str  # UUID
  task_id: str
  organization_id: str  # 필수 (task.organization_id와 동일)
  requested_by_user_id: str
  approved_by_user_id: Optional[str] = None
  action_type: str = ""
  risk_level: str = ""
  status: str = "pending"  # pending, approved, rejected, expired
  approval_token_hash: str = ""  # SHA256 hash, 원문 저장 금지
  expires_at: datetime = None
  used_at: datetime = None
  created_at: datetime = None
  updated_at: datetime = None
```

**Scope**: Organization  
**특징**:
- organization_id 필수 (task.organization_id와 동일해야 함)
- approval_token은 메모리에만 저장 (DB에는 hash만)
- final_approval_token도 hash로 저장
- expires_at로 만료 처리

#### 3.2.7 BrowserResult

```python
@dataclass
class BrowserResult:
  result_id: str  # UUID
  task_id: str
  organization_id: str  # 필수 (task.organization_id와 동일)
  status: str  # completed, failed, timeout
  output: dict = None
  error: Optional[str] = None
  captured_at: datetime = None
  created_at: datetime = None
```

**Scope**: Organization  
**특징**:
- task completion 후 저장
- organization_id 필수

#### 3.2.8 BrowserAuditEvent

```python
@dataclass
class BrowserAuditEvent:
  event_id: str  # UUID
  organization_id: str  # 필수
  task_id: Optional[str] = None
  approval_id: Optional[str] = None
  actor_user_id: Optional[str] = None
  actor_role: Optional[str] = None  # membership.role from organization
  event_type: str = ""  # BROWSER_TASK_CREATED, BROWSER_APPROVAL_REQUESTED, etc.
  risk_level: Optional[str] = None
  action_type: Optional[str] = None
  decision: Optional[str] = None  # approved, rejected, auto-allowed, blocked
  note: str = ""
  target_type: str = ""  # BrowserTask, BrowserApproval, etc.
  target_id: str = ""  # task_id, approval_id
  timestamp: datetime = None
```

**Scope**: Organization  
**특징**:
- organization_id 필수
- 다른 org의 actor는 절대 이 event에 접근 불가
- system event는 organization_id=None 허용 (서비스 간 호출)

#### 3.2.9 AppAuditLog

```python
# 기존 migration에 organization_id가 이미 있다고 가정
@dataclass
class AppAuditLog:
  log_id: str  # UUID
  organization_id: Optional[str] = None  # system event는 None
  event_type: str = ""
  actor_user_id: Optional[str] = None
  actor_role: Optional[str] = None
  target_type: str = ""  # BrowserTask, LocalAgent, etc.
  target_id: str = ""
  payload: dict = None
  created_at: datetime = None
```

**Scope**: Organizational or System  
**특징**:
- organization_id: browser task, local agent 이벤트는 필수
- organization_id: None: system/infra 이벤트만 (WebSocket lifecycle, agent lifecycle 등)

---

## 4. Permission Matrix

### 4.1 Role 정의

| Role | 설명 | 주요 용도 |
|------|------|---------|
| **owner** | 조직 소유자 | 조직 설정, user 초대, 감사 조회, DB migration 승인 |
| **admin** | 조직 관리자 | task 생성/승인/거부, agent 등록, 결과 조회, 감사 조회 |
| **manager** | 프로젝트 관리자 | task 생성, 부분 승인, 결과 조회 |
| **operator** | 작업 담당자 | task 요청, 결과 조회 |
| **viewer** | 읽기 전용 | task/result/audit read-only |
| **auditor** | 감사 담당자 | audit read-only (다른 데이터 접근 불가) |
| **local_agent** | 로컬 에이전트 | assigned task 수신, result callback, approval token 검증 |

### 4.2 Action별 필요 Role

| Action | owner | admin | manager | operator | viewer | auditor | local_agent |
|--------|-------|-------|---------|----------|--------|---------|-------------|
| **Task 생성** | ✓ | ✓ | ✓ | - | - | - | - |
| Task 승인 | ✓ | ✓ | △ | - | - | - | - |
| Task 거부 | ✓ | ✓ | △ | - | - | - | - |
| Task 조회 (모든) | ✓ | ✓ | - | - | - | - | - |
| Task 조회 (자신) | ✓ | ✓ | ✓ | ✓ | - | - | - |
| **Result 조회** | ✓ | ✓ | ✓ | ✓ | ✓ | - | - |
| **Agent 조회** | ✓ | ✓ | - | - | - | - | - |
| Agent 등록 | ✓ | ✓ | - | - | - | - | - |
| Agent 비활성화 | ✓ | ✓ | - | - | - | - | - |
| **Audit 조회** | ✓ | ✓ | - | - | - | ✓ | - |
| **User 초대** | ✓ | - | - | - | - | - | - |
| User 삭제 | ✓ | - | - | - | - | - | - |
| **Org 설정** | ✓ | - | - | - | - | - | - |
| Task 수신 (assigned) | - | - | - | - | - | - | ✓ |
| Result callback | - | - | - | - | - | - | ✓ |
| Approval token 검증 | - | - | - | - | - | - | ✓ |

**범례**: ✓ = 허용, △ = 조건부 (e.g., 자신이 생성한 task만), - = 불허

### 4.3 Scope Rule

**기본 규칙**:
1. 모든 조회는 `user.memberships` 에 포함된 organization만 접근 가능
2. 다른 organization의 데이터는 절대 노출 금지
3. Audit log는 자신의 organization 내 이벤트만 조회

**구현 예시** (FastAPI):
```python
async def get_browser_tasks(
    user: dict = Depends(get_current_user),
    org_id: str = Query(...),
):
    # user의 memberships에 org_id가 있는지 확인
    if org_id not in user.get("organization_ids", []):
        raise HTTPException(status_code=403, detail="No access to this organization")
    
    # 쿼리 필터: organization_id == org_id
    tasks = db.query(BrowserTask).filter(BrowserTask.organization_id == org_id).all()
    return tasks
```

---

## 5. WebSocket Handshake Scope Rule

### 5.1 Agent Hello Message에 포함할 field

```python
@dataclass
class AgentHelloMessage:
  agent_id: str  # UUID
  organization_id: str  # 필수: 이 agent가 속한 조직
  agent_version: str
  host_name_hash: str  # SHA256(hostname)[:12]
  registration_user_id: Optional[str] = None  # agent 등록한 user
  capabilities: list[str]
  mode: str  # read_only
  audit_enabled: bool
  approval_required: bool
  timestamp: str
```

**변경점**:
- `organization_id` 추가 (필수)
- `registration_user_id` 추가 (optional, agent 등록자 추적용)

### 5.2 금지 사항

다음은 절대 handshake에 포함하면 안 됨:
- Raw hostname (host_name_hash만 허용)
- Raw username (registration_user_id만 허용, ID는 허용)
- Raw IP address
- approval_token, final_approval_token (절대 금지)
- token_hash (절대 금지)
- password, OTP
- cookie, session, authorization header
- localStorage, sessionStorage contents

### 5.3 Server Policy Message with Organization Scope

```python
@dataclass
class ServerPolicyMessage:
  organization_id: str  # agent가 속한 조직
  agent_id: str
  mode: str  # read_only
  allow_execute: bool  # False (항상)
  allow_submit: bool  # False (항상)
  allow_password_input: bool  # False (항상)
  allow_otp_input: bool  # False (항상)
  require_approval: bool  # True (항상)
  heartbeat_interval_sec: int
  timestamp: str
```

---

## 6. Admin Web UI Scope

### 6.1 Browser Approvals Page

**현재 상태**: 미구현 또는 부분 구현

**요구사항**:
- 조직별 필터링 (current_user의 organizations만 표시)
- 각 organization의 pending/approved/rejected approval만 표시
- approval_token 원문 절대 노출 금지
- approval_id만 표시

**TypeScript Type** (필요):
```typescript
export interface BrowserApproval {
  approval_id: string;  // UUID
  task_id: string;
  organization_id: string;  // 표시 안 함 (internal only)
  requested_by_user_id: string;
  action_type: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  expires_at?: string;  // ISO 8601
  created_at: string;
}
```

### 6.2 Local Agents Page

**요구사항**:
- 조직별 agent 목록만 표시
- host_name_hash만 표시 (raw hostname 금지)
- agent status, last_seen_at, capabilities 표시
- 조직의 admin 이상만 agent 등록/비활성화 가능

### 6.3 Audit Log Page

**요구사항**:
- 조직별 audit 이벤트만 조회
- auditor role은 audit 이벤트만, 다른 데이터 접근 불가
- actor_user_id는 표시하되 password/token은 절대 노출 금지
- organization_id는 internal field (UI에 표시 안 함)

---

## 7. Gap 분석

### 7.1 P1 Gap (운영 WebSocket 연결 전 반드시 필요)

| Gap | 현황 | 필요 작업 | 파일 |
|-----|------|---------|------|
| **G1: User model에 user_id 필요** | 현재 actor(username)만 있음 | User 모델 추가, username → user_id 매핑 | `ai_orchestrator/models.py` |
| **G2: Organization model 필요** | 전무 | Organization 모델 추가 | `ai_orchestrator/models.py` |
| **G3: Membership model 필요** | 전무 | Membership 모델 추가, user_id + org_id 바인딩 | `ai_orchestrator/models.py` |
| **G4: Auth에 organization_id 추가** | 현재 {actor, role}만 반환 | Auth 함수 확장: {actor, user_id, role, organization_ids: str[]} | `ai_orchestrator/auth.py` |
| **G5: BrowserTask model 필요** | 전무 | BrowserTask 모델 추가, organization_id 필수 | `local_agent/browser_task.py` |
| **G6: BrowserApproval model 필요** | 부분 (approval_manager) | BrowserApproval 모델 추가, approval_store에 persistence | `local_agent/browser_approval.py` |
| **G7: BrowserResult model 필요** | 전무 | BrowserResult 모델 추가 | `local_agent/browser_result.py` |
| **G8: BrowserAuditEvent factory 필요** | audit_logger.py는 generic | browser_audit_contract.py 추가, organization_id propagation | `local_agent/browser_audit_contract.py` |
| **G9: WebSocket handshake organization_id 추가** | 현재 없음 | AgentHelloMessage에 organization_id, registration_user_id 추가 | `local_agent/browser_websocket_handshake.py` |
| **G10: LocalAgent model organization_id 필수** | 현재 agent_id만 있음 | LocalAgent 모델 정의, organization_id 필수 | `local_agent/local_agent_model.py` |
| **G11: AppAuditLog organization_id 확인** | migration 완료했다고 가정 | 기존 migration 파일 확인, organization_id 없으면 추가 migration | `migrations/*.sql` |
| **G12: Admin approval UI 타입 정의** | `browser-approval.ts` 없음 | admin-web/src/types/browser-approval.ts 추가 | `admin-web/src/types/browser-approval.ts` |
| **G13: API scope check 필요** | 현재 없음 | 모든 task/approval/agent 조회 API에 organization_id 필터 추가 | `ai_orchestrator/routers/*.py` |

### 7.2 P2 Gap (Schema migration 또는 테스트)

| Gap | 설명 | 파일 |
|-----|------|------|
| **G14: DB schema migration** | user_id, organization_id, membership 테이블 생성 | `migrations/` |
| **G15: Tenant-aware repository helpers** | organization_id 자동 필터링 | `ai_orchestrator/db_helpers.py` |
| **G16: Permission matrix tests** | role별 action 권한 테스트 | `tests/test_permission_matrix.py` |
| **G17: BrowserTask scope tests** | task.org_id == approval.org_id == result.org_id == audit.org_id | `tests/test_browser_task_scope.py` |
| **G18: WebSocket organization_id validation** | handshake에서 org_id 검증 | `tests/test_browser_websocket_org_scope.py` |

### 7.3 P3 Gap (향후 확장)

| Gap | 설명 |
|-----|------|
| **G19: Schema-per-tenant design** | 같은 DB 내 schema 분리 (org별) |
| **G20: DB-per-tenant design** | organization별 별도 DB 연결 |
| **G21: Billing/subscription integration** | organization 별 과금, 기능 제한 |
| **G22: Cross-org audit admin** | 슈퍼 관리자용 전체 감사 로그 조회 |

---

## 8. 현재 구현 상태 Matrix

| Entity | 모델 정의 | organization_id | 저장소 | API | Tests |
|--------|---------|-----------------|------|-----|-------|
| **User** | △ (actor만) | ✗ | json | ✗ | △ |
| **Organization** | ✗ | - | - | - | - |
| **Membership** | ✗ | - | - | - | - |
| **LocalAgent** | △ | ✗ | memory | △ | ✓ |
| **BrowserTask** | ✗ | - | - | - | - |
| **BrowserApproval** | △ | ✗ | memory | ✗ | ✗ |
| **BrowserResult** | ✗ | - | - | - | - |
| **BrowserAuditEvent** | ✗ | - | - | - | - |
| **AppAuditLog** | △ | ? | JSONL | ✗ | △ |
| **Admin ApprovalUI** | ✗ | - | - | ✗ | - |

**범례**: ✓ = 완료, △ = 부분, ✗ = 없음

---

## 9. 검증 결과

### 9.1 정적 분석

**파일 컴파일 확인**:
```bash
python -m py_compile local_agent/browser_websocket_handshake.py  # PASS
python -m py_compile ai_orchestrator/auth.py  # PASS
```

**주요 발견**:
- handshake schema는 good (safe_dict 함수로 민감정보 제거)
- auth는 basic (organization_id 확장 필요)
- approval_manager는 in-memory (persistence 필요)

### 9.2 Code Pattern 확인

**검색 결과**:
- `organization_id`: gpt_planner.py 외 거의 없음
- `membership`: 0건 (새로 추가 필요)
- `tenant`: 0건 (새로 추가 필요)
- `approved_by_user_id`: 0건 (approval model 확장 필요)

### 9.3 감사 로그 Event Types

**기존**: 70+ event types 정의됨 (기본 task, CAD proxy, web task, local agent)

**누락**: 
- BROWSER_TASK_CREATED
- BROWSER_TASK_APPROVED
- BROWSER_TASK_REJECTED
- BROWSER_TASK_COMPLETED
- BROWSER_APPROVAL_REQUESTED
- BROWSER_APPROVAL_EXPIRED

---

## 10. 권장 구현 순서

### Phase 1: Model 정의 (로컬, no DB)
1. `ai_orchestrator/models.py`: User, Organization, Membership 모델
2. `local_agent/browser_task.py`: BrowserTask 모델
3. `local_agent/browser_approval.py`: BrowserApproval 개선
4. `local_agent/browser_result.py`: BrowserResult 모델
5. `local_agent/local_agent_model.py`: LocalAgent 모델 (organization_id 포함)

### Phase 2: Type 정의 (Admin Web)
6. `admin-web/src/types/browser-approval.ts`: UI types
7. `admin-web/src/types/local-agent.ts`: 기존 파일 확장

### Phase 3: Handshake 확장
8. `local_agent/browser_websocket_handshake.py`: organization_id, registration_user_id 추가

### Phase 4: Audit Contract
9. `local_agent/browser_audit_contract.py`: BrowserAuditEvent factory

### Phase 5: Auth 확장
10. `ai_orchestrator/auth.py`: organization_ids 반환

### Phase 6: API 추가 (먼저 스켈레톤)
11. `ai_orchestrator/routers/browser_tasks.py` (신규)
12. `ai_orchestrator/routers/browser_approvals.py` (신규)

### Phase 7: Tests
13. `tests/test_browser_task_scope.py`
14. `tests/test_browser_websocket_org_scope.py`

---

## 11. 다음 단계

### PASS 시 (현재)
1. 이 보고서 내용으로 TENANT-2 (Minimal Organization Scope Schema Proposal) 진행
2. DB schema 설계 확정
3. Migration SQL 작성

### 또는 직진
- BROWSER-6C: 운영 WebSocket read-only 실제 연결 게이트

### 병행
- AUDIT-DRYRUN: 48시간 모니터링 계속 (2026-05-01 ~ 2026-05-03)

---

## 12. Reference

### 기존 문서
- `docs/ops/stage13f3c_operational_ws_smoke_plan.md`: WebSocket smoke test plan
- `docs/ops/stage13f3a_operational_connection_plan.md`: Connection plan

### 관련 코드
- `local_agent/browser_websocket_handshake.py`: Schema definition
- `ai_orchestrator/auth.py`: Current auth implementation
- `approval_manager.py`: Token management (개선 필요)
- `ai_orchestrator/audit_logger.py`: Event logging

---

## Appendix A: Safe_dict Validation

**현재 구현** (`local_agent/browser_websocket_handshake.py` lines 64-97):

```python
def safe_dict(data: dict) -> dict:
  forbidden_patterns = {
    "approval_token", "final_approval_token", "token_hash",
    "password", "otp", "cookie", "session", "authorization",
    "localstorage", "sessionstorage", "typed_text",
    "base64", "full_dom", "raw_html", "raw_dom",
    "hostname", "username", "user_name", "ip_address",
    "machine_id", "device_id",
  }
```

**검증 결과**: ✓ GOOD
- approval_token, final_approval_token 제거
- password, OTP 제거
- raw hostname, username, IP 제거

**추가 필요**:
- BrowserAuditEvent factory에서 organization_id 전파
- approval_token_hash 필드는 safe_dict에 추가 고려

---

**최종 판정**: PASS (설계 단계)

다음 단계: TENANT-2 Schema Proposal → TENANT-3 Migration → 운영 배포
