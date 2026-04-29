# Stage 13E-1: Local Agent 운영 진단 보드 설계

## 1. 현재 상태 요약

### Stage 13B~13D 완료 상항

- **Stage 13B**: observe_summary (agent 상태/task 결과 요약) 운영 반영 완료
- **Stage 13C**: audit_summary (감사 이벤트 요약) 운영 반영 완료
- **Stage 13D**: 
  - approval task detail 검증 완료 (token_id, raw audit, raw HTML 미노출 보증)
  - Repo Boundary Lock 정책/스크립트 운영 반영 완료
  - 원격 접속 안전성(SSH alias support) 확보

### 현재 운영 환경 특성

- agents 수: 0~N (운영 시작 시점엔 0개 정상)
- task 수: 0~N (task 없을 때도 정상)
- approve/reject: waiting_approval 상태 존재 여부만 확인 (실제 POST 없음)
- summaries: observe_summary, audit_summary 저장 여부는 task별로 다름
- repo boundary: 서버 startup 또는 수동 점검 결과만 활용

### 현재 API 상황

| Endpoint | 메서드 | 용도 | 민감정보 노출 |
|----------|--------|------|------------|
| `/api/v1/local-agents` | GET | agent 목록 조회 | allowlist만 반환 |
| `/api/v1/local-agents/{agent_id}/tasks` | GET | agent별 task 목록 | 상태/counts만 |
| `/api/v1/local-agents/{agent_id}/tasks/{task_id}` | GET | task 상세 | observe/audit summary 포함 (sanitized) |
| (신규 후보) | GET | 운영 진단 aggregate | 아래 설계 참고 |

---

## 2. Stage 13E 목표

**운영자가 admin-web 한 화면에서 아래 상태를 read-only로 확인 가능하게:**

### 인프라 상태
- API health 상태 (200 OK 등)
- admin-web 상태 (up/down 등)
- Repo Boundary Lock 상태 (pass/fail/not_checked)

### Agent 상태
- 등록된 agent 수
- online 상태 agent 수
- offline/stale 상태 agent 수

### Task 상태
- 총 task 수
- pending/queued 상태 수
- running 상태 수
- 승인 대기(waiting_approval) 수
- 완료/실패 수

### Summary 상태
- observe_summary 보유 task 수
- audit_summary 보유 task 수
- 최근 요약 생성 시각

### 운영 편의
- 비정상(failed/waiting_approval) 강조 표시
- raw audit/token/HTML 미노출
- agents 0개 시에도 정상적인 empty state 표시 (오류처럼 보이지 않게)

---

## 3. 진단 보드 표시 항목

### A. [표시 가능] allowlist items

```
✓ api_health_status: "ok" | "warn" | "error"
✓ admin_web_status: "up" | "down"
✓ repo_boundary_status: "pass" | "fail" | "not_checked"
✓ repo_boundary_last_checked_at: ISO datetime | null

✓ registered_agent_count: int
✓ online_agent_count: int
✓ offline_agent_count: int
✓ stale_agent_count: int

✓ task_total_count: int
✓ task_pending_count: int (queued)
✓ task_running_count: int
✓ task_waiting_approval_count: int
✓ task_completed_count: int
✓ task_failed_count: int
✓ task_rejected_count: int

✓ with_result_summary_count: int
✓ with_observe_summary_count: int
✓ with_audit_summary_count: int

✓ latest_task_created_at: ISO datetime | null
✓ latest_task_updated_at: ISO datetime | null
✓ latest_summary_created_at: ISO datetime | null
✓ diagnostics_generated_at: ISO datetime

✓ warnings: string[] (e.g., ["too_many_failed", "approval_backlog"])
```

### B. [API only 또는 STORE only] 기술 정보

```
• internal_api_version: 운영 진단 endpoint 버전
• check_repo_boundary_version: script version hash
• diagnostic_schema_version: API schema version
• server_head_short: git short hash (if safe to expose)
```

### C. [절대 표시 금지] raw/민감 정보

```
✗ token_id (waiting_approval 승인/거부 판단은 count만 사용)
✗ approve/reject token
✗ raw task params
✗ raw audit JSONL / events 리스트
✗ raw observe_summary JSON
✗ raw audit_summary JSON
✗ raw HTML / page_structure
✗ current_url 원문
✗ URL query / fragment
✗ cookie / session / authorization header
✗ local file path
✗ PC username
✗ IP/host 원문
✗ raw docker logs
✗ raw stack trace
✗ secret-like strings (passwords, keys, etc.)
```

---

## 4. API 설계: 신규 진단 endpoint

### 4.1 설계 대안 비교

| 대안 | 구현 위치 | 장점 | 단점 |
|-----|---------|------|------|
| **A. 기존 list 조합** | admin-web js | 백엔드 변경 최소 | agent/task 많을 때 성능 저하 |
| **B. 신규 read-only diagnostics endpoint** | backend | allowlist 집계 안전, 성능 | API 추가 필요 |
| **C. admin-web 클라이언트 집계** | admin-web js | API 변경 적음 | 민감 필터링 책임 증가, 중복 로직 |

**추천: B번 신규 read-only diagnostics endpoint**
- 서버에서 allowlist만 조합 반환 → admin-web에서 안전하게 표시 가능
- 민감정보 필터링을 서버에서 담당 → 신뢰도 높음
- 단일 요청으로 종합 진단 정보 조회 가능

### 4.2 신규 Endpoint 사양 (초안)

```
GET /api/v1/admin/local-agents/diagnostics

또는

GET /api/v1/local-agents/diagnostics
  ?include_warnings=true
  &include_schema_version=true

인증: 기존 local-agents API와 동일 (admin/owner/viewer 권한 필요)

응답:
{
  "status": "ok" | "warn" | "error",
  "diagnostics_generated_at": "2026-04-29T13:30:00Z",
  
  "infrastructure": {
    "api_health_status": "ok",
    "admin_web_status": "up",
    "repo_boundary_status": "pass" | "fail" | "not_checked",
    "repo_boundary_last_checked_at": "2026-04-29T13:00:00Z" | null
  },
  
  "agents": {
    "total": 0,
    "online": 0,
    "offline": 0,
    "stale": 0
  },
  
  "tasks": {
    "total": 0,
    "pending": 0,
    "running": 0,
    "waiting_approval": 0,
    "completed": 0,
    "failed": 0,
    "rejected": 0
  },
  
  "summaries": {
    "with_result_summary": 0,
    "with_observe_summary": 0,
    "with_audit_summary": 0
  },
  
  "latest": {
    "task_created_at": "2026-04-29T13:15:00Z" | null,
    "task_updated_at": "2026-04-29T13:20:00Z" | null,
    "summary_created_at": "2026-04-29T13:25:00Z" | null
  },
  
  "warnings": [
    "too_many_failed",
    "approval_backlog",
    "agents_offline"
  ],
  
  "schema_version": "1.0.0"
}
```

### 4.3 구현 원칙

- **GET only**: POST/상태 변경 없음
- **읽기 전용**: count/status/category 중심 반환
- **민감정보 차단**: token_id, params, raw logs, raw JSON 반환 금지
- **Allowlist 접근**: 정의되지 않은 필드는 drop
- **Unknown handling**: 새로운 필드는 schema_version 증가

---

## 5. Admin-Web UI 설계 (초안)

### 5.1 페이지 구조

```
[Local Agents] 메뉴
  ├─ 운영 진단 (신규 섹션)
  │  ├─ Summary Cards (4개)
  │  │  ├─ API & 저장소 상태
  │  │  ├─ Agents 상태
  │  │  ├─ Tasks 상태
  │  │  └─ Summaries 상태
  │  └─ Diagnostics Details (테이블/리스트)
  │     ├─ Agent 목록 (이름, 상태, 최근 task 수)
  │     └─ Task 목록 (ID, 상태, created/updated)
  │
  └─ Agents (기존)
     └─ ...
```

### 5.2 Summary Cards 설계

#### Card 1: API & 저장소
```
┌─────────────────────────────────┐
│ API 상태                        │
├─────────────────────────────────┤
│ health: ● OK                    │
│ admin-web: ● UP                 │
│ Repo Boundary: ✓ PASS           │
│ (last checked: 2시간 전)        │
└─────────────────────────────────┘
```

#### Card 2: Agents
```
┌─────────────────────────────────┐
│ 등록된 에이전트: 2              │
├─────────────────────────────────┤
│ ● Online: 1                     │
│ ○ Offline: 1                    │
│ ⚠ Stale: 0                      │
└─────────────────────────────────┘
```

#### Card 3: Tasks
```
┌─────────────────────────────────┐
│ Tasks: 10 건                    │
├─────────────────────────────────┤
│ ⏳ Pending: 2                   │
│ ▶ Running: 1                    │
│ ⚠ Waiting Approval: 3 ← highlight│
│ ✓ Completed: 3                  │
│ ✗ Failed: 1 ← highlight         │
└─────────────────────────────────┘
```

#### Card 4: Summaries
```
┌─────────────────────────────────┐
│ 요약 정보                       │
├─────────────────────────────────┤
│ Observe Summary: 8 tasks        │
│ Audit Summary: 6 tasks          │
│ Latest: 5분 전                  │
└─────────────────────────────────┘
```

### 5.3 Empty State 처리

**agents 0개 시:**
```
┌─────────────────────────────────┐
│ 운영 진단                       │
├─────────────────────────────────┤
│                                 │
│  [ℹ] 등록된 에이전트 없음      │
│                                 │
│  시스템은 정상 작동 중입니다.  │
│  처음 에이전트를 등록하려면   │
│  [Register Agent] 버튼을      │
│  클릭하세요.                   │
│                                 │
└─────────────────────────────────┘
```

**tasks 0개 시:**
```
tasks: 0 건
├─ Pending: 0
├─ Running: 0
├─ Waiting Approval: 0
├─ Completed: 0
└─ Failed: 0
```

### 5.4 UI 원칙

- **색상**: ok(green), warn(yellow), error(red)
- **강조**: waiting_approval, failed는 주의색으로 표시
- **count 중심**: raw data/JSON dump 없음
- **read-only**: 이 화면에서 approve/reject 버튼 없음 (task detail로 유도)
- **responsive**: 모바일/태블릿에서도 카드 레이아웃 유지

---

## 6. Repo Boundary Lock 진단

### 6.1 Status 정의

```
"pass"       → scripts/check_repo_boundary.sh 최종 PASS 확인됨
"fail"       → 최종 FAIL 상태 (git pull 불가, 위험)
"not_checked" → 서버 시작 후 아직 점검하지 않음
"unknown"    → 점검 중, 결과 불명확
```

### 6.2 표시 방식

**admin-web 진단 보드:**
```
Repo Boundary: ✓ PASS
(또는)
Repo Boundary: ✗ FAIL - Manual check required
(또는)
Repo Boundary: ? Not checked yet
```

**상세 정보 (상시 표시):**
```
✓ PASS → 원격 repo slug 정규화 안전 (SSH alias 지원)
✗ FAIL → 브랜치/경로/remote URL 불일치 → 즉시 수동 점검 필요
? Not checked → 서버 시작 후 첫 진단 대기
```

### 6.3 구현 고려사항

- 매 요청마다 `scripts/check_repo_boundary.sh` 실행 vs 서버 시작 시만 실행
  - **추천**: 서버 시작 시만 실행 (성능, 빈도 낮음)
  - 상태 변경 시 수동 점검 권유
- git remote URL 정규화: 서버 remote slug만 표시 (HTTPS 원문 미노출)
- branch name 표시: 'master' 등 public 정보만 표시

---

## 7. 보안 & Sanitize 기준

### 7.1 Allowlist 접근

**반환하는 필드: count, status, category, timestamp만**
```python
{
  "agent_count": 5,              ✓ count
  "agent_status": "mixed",        ✓ status category
  "task_status_breakdown": {      ✓ counts per status
    "running": 2,
    "waiting_approval": 1
  },
  "latest_activity": "2026-04-29T13:20:00Z"  ✓ timestamp
}
```

**절대 반환 금지**
```python
{
  "agent_id": "...",              ✗ raw ID (다르면 이 필드만 포함 허용)
  "task_params": {...},           ✗ raw params
  "audit_events": [...],          ✗ raw events
  "html_content": "...",          ✗ raw HTML
  "current_url": "https://...",   ✗ raw URL
  "session_token": "...",         ✗ token
  "server_ip": "10.0.0.1"         ✗ 원문 IP
}
```

### 7.2 Unknown Field Drop

```python
# 새로운 필드가 없으면 그냥 무시
if field not in ALLOWED_DIAGNOSTICS_FIELDS:
    drop(field)
```

### 7.3 Token/Approval 처리

- **waiting_approval count**: 승인 대기 task 개수만 반환
- **token_id**: 절대 반환 금지
- **approve/reject**: endpoint에서 지원 금지 (read-only만)

### 7.4 Timestamp 처리

```python
# 안전한 timestamp 예시
"diagnostics_generated_at": "2026-04-29T13:30:00Z",  ✓ 생성 시각
"latest_task_updated_at": "2026-04-29T13:20:00Z",     ✓ 최신 업데이트
"repo_boundary_last_checked_at": "2026-04-29T13:00:00Z"  ✓ 마지막 점검
```

---

## 8. 테스트 계획 (Stage 13E-2 후보)

### 8.1 Diagnostics Endpoint 테스트

```python
tests/test_local_agent_diagnostics.py

[그룹 A: 기본 상황]
- ✓ agents 0, tasks 0 → counts 모두 0 반환
- ✓ agents 1, tasks 5 → 정확한 counts
- ✓ health OK, boundary PASS → status="ok"

[그룹 B: Count 정확성]
- ✓ task status별 count 정확
- ✓ waiting_approval count
- ✓ failed count
- ✓ observe_summary/audit_summary count

[그룹 C: 보안 검증]
- ✓ token_id 미포함
- ✓ raw params 미포함
- ✓ raw audit JSONL 미포함
- ✓ raw HTML 미포함
- ✓ current_url 원문 미포함

[그룹 D: Repo Boundary]
- ✓ PASS 상태 정확 표시
- ✓ FAIL 상태 정확 표시
- ✓ NOT_CHECKED 상태 정확 표시
- ✓ remote slug만 표시 (HTTPS URL 미노출)

[그룹 E: 유효성]
- ✓ GET only (POST 거부)
- ✓ schema_version 포함
- ✓ diagnostics_generated_at 정확
- ✓ 기존 local-agents API 회귀 없음
```

### 8.2 Admin-Web UI 테스트 (Stage 13E-3)

```typescript
tests/LocalAgentsDiagnosticsBoard.test.tsx

[그룹 A: Card Rendering]
- ✓ 4개 Summary Card 렌더
- ✓ counts 정확 표시
- ✓ status badge 정확 표시

[그룹 B: Empty State]
- ✓ agents 0일 때 empty message 표시
- ✓ tasks 0일 때 empty state UI
- ✓ no error appearance

[그룹 C: Highlight]
- ✓ waiting_approval > 0 → 강조색
- ✓ failed > 0 → 강조색
- ✓ offline > 0 → 경고색

[그룹 D: 보안 (정적)]
- ✓ token_id 텍스트 렌더 없음
- ✓ raw JSON dump 없음
- ✓ dangerouslySetInnerHTML 없음
- ✓ raw audit/events 표시 없음
```

---

## 9. Stage 13E-2 최소 구현 제안

### 9.1 변경 범위

**추가:**
- `ai_orchestrator/local_agent_diagnostics.py` (신규 helper)
- `ai_orchestrator/local_agent_router.py` 에서 diagnostics endpoint 추가
- `tests/test_local_agent_diagnostics.py` (신규 테스트)

**수정 금지:**
- 기존 local-agents API 변경 없음
- admin-web 코드 아직 수정 금지 (Stage 13E-3)
- 기존 테스트 회귀 방지

### 9.2 구현 체크리스트

- [ ] diagnostics helper 함수 작성
  - agent count/status 집계
  - task count/status 집계
  - summary count 집계
  - repo boundary status (not_checked로 초기화)
- [ ] endpoint 추가
  - GET /api/v1/local-agents/diagnostics
  - allowlist 필터링
  - error handling
- [ ] 테스트 작성
  - 8.1 테스트 계획 참고
  - 기존 API 회귀 확인

### 9.3 배포 계획

1. Stage 13E-2: Backend diagnostics endpoint 구현 + 배포
2. Stage 13E-3: Admin-web UI 구현 + 배포
3. Stage 13E-4: 최종 운영 검증

---

## 10. 중단 조건 & 위험 신호

### 10.1 구현 중단 조건 (STOP)

```
❌ diagnostics를 위해 실제 task 생성이 필요함
❌ diagnostics를 위해 approve/reject POST 필요
❌ diagnostics를 위해 local-agent 실행 필요
❌ raw audit JSONL / logs를 반환해야 함
❌ token_id를 response에 포함해야 함
❌ raw HTML / page_structure 필드 필요
❌ current_url 원문 필드 필요
❌ 다른 앱 접근 필요
❌ repo 밖 탐색 필요
❌ DB/schema 변경 필요 (approve/reject 등)
```

### 10.2 설계 위험 신호

```
⚠ admin-web에 JSON.stringify 추가하려는 경우
⚠ raw task detail을 diagnostics 화면에 표시하려는 경우
⚠ token_id를 UI에 표시하려는 경우
⚠ endpoint POST/상태 변경 추가하려는 경우
⚠ Repo Boundary status를 매 요청마다 확인하려는 경우
```

---

## 11. 참고 문서

- Stage 13B: observe_summary 설계
- Stage 13C: audit_summary 설계
- Stage 13D-1: approval task detail 검증 설계
- Stage 13D-2: approval task detail 검증 결과
- `scripts/check_repo_boundary.sh`: repo boundary check 구현
- `ai_orchestrator/local_agent_registry.py`: agent/task 상태 정의
- `admin-web/src/types/local-agent.ts`: 타입 정의

---

## 12. 다음 단계

### Stage 13E-2: Backend 구현
- diagnostics endpoint 구현 (제안 7~9 참고)
- 백엔드 테스트 작성
- 서버 배포

### Stage 13E-3: Frontend 구현
- admin-web 운영 진단 보드 UI 추가
- admin-web 테스트 작성
- admin-web 배포

### Stage 13E-4: 최종 검증
- 통합 테스트 (backend + frontend)
- 운영 환경에서 실제 동작 확인
- 보안 검증 재확인

---

**작성일**: 2026-04-29  
**Stage**: 13E-1 설계 완료  
**상태**: 리뷰 대기
