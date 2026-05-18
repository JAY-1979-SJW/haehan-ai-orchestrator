# 비서앱 MVP 전체 준공 설계서

**문서 코드:** APP_MVP_READONLY_FULL_DESIGN_01  
**작성일:** 2026-05-18  
**최종 갱신:** 2026-05-19  
**상태:** ✅ A~E 완료 / F 준공 대기  

---

## 1. 프로젝트 개요

### 목적

운영 중인 haehan-ai-orchestrator 백엔드를 **읽기 전용(Read-Only)** 으로 관찰하는 관리 웹 UI.  
실행·승인·삭제 등 상태 변경 동작은 일절 없으며, DRY_RUN 전용 · 실행 버튼 없음 원칙 준수.

### 핵심 제약

| 제약 | 내용 |
|------|------|
| 실행 금지 | execute / approve / reject / delete 버튼 없음 |
| mutation 금지 | POST/PUT/PATCH/DELETE 연결 없음 |
| 보안 금지선 | approval_token_raw · cookie_value · secret 원문 표시 금지 |
| 백엔드 불변 | router.py · docker-compose.yml 수정 없음 |
| 엔드포인트 고정 | 63개 고정, POST 27개 고정 |
| DRY_RUN 해제 금지 | B-2 미승인 상태 유지 |

---

## 2. 시스템 구성

### 기술 스택

```
Frontend  : Next.js 14 (App Router) — TypeScript
UI 경로   : admin-web/src/app/assistant/
컴포넌트  : admin-web/src/components/assistant/
타입      : admin-web/src/types/assistant.ts
API 클라이언트: admin-web/src/lib/assistant/api.ts
Mock 데이터: admin-web/src/lib/assistant/mock.ts

Backend   : FastAPI (Python)
API 서버  : ai_orchestrator/server.py
라우터    : ai_orchestrator/router.py
엔드포인트: 63개 (GET 전용 신규 추가)
```

### 레이어 위치

```
L8 Server API  — FastAPI 라우터 (ops_router, app_status_router)
L9 Admin UI    — Next.js 비서앱 MVP
L11 Tests      — pytest (tests/test_app_*.py)
L12 Docs       — 본 설계서, 감사 스크립트
```

---

## 3. 화면 구성 (7개 탭)

### 3-1. 대시보드 `/assistant`

**상태:** ✅ 완료 (APP_UI_READONLY_BACKEND_STATUS_CARDS_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/page.tsx` |
| API 연결 | `getAppHealthSummary()` → `/api/v1/app/health/summary` |
| 컴포넌트 | BackendStatusCard × 3 (헬스·공급자·스토리지) |
| 상태 관리 | idle → loading → success \| mock_fallback \| error |
| 배너 | ReadOnlyModeBanner, FutureEndpointNotice |

### 3-2. 작업 큐 `/assistant/tasks`

**상태:** ✅ 완료 (APP_TASK_QUEUE_READONLY_LIST_POLISH_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/tasks/page.tsx` |
| API 연결 | `/api/v1/tasks` (GET) |
| 컴포넌트 | TaskTable (필터·정렬·모달) |
| 특이사항 | execute_btn · approve_btn 없음. DryRunInfo 배지 표시 |

### 3-3. 작업 상세 `/assistant/tasks/[id]`

**상태:** ✅ 완료 (APP_TASK_DETAIL_READONLY_POLISH_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/tasks/[id]/page.tsx` |
| 컴포넌트 | TaskDetailPanel (5섹션: 기본정보·요약·차단사유·오류·JSON뷰어) |
| 특이사항 | taskQueueMock에서 id 조회, 미발견 시 mock_fallback |

### 3-4. 승인 게이트 `/assistant/approval`

**상태:** ✅ 완료 (APP_APPROVAL_GATE_READONLY_POLISH_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/approval/page.tsx` |
| 컴포넌트 | GateBadge, RiskBadge |
| Mock 데이터 | approvalGatesMock (6개 게이트), knownBacklogMock |
| 요약 카드 | 전체 게이트 / BLOCKED / 미연결 |
| 특이사항 | B-1 안내 패널 (approve→execute 미연결 의도적 미완) |

### 3-5. 외부 사이트 `/assistant/external-sites`

**상태:** ✅ 완료 (APP_EXTERNAL_SITES_READONLY_POLISH_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/external-sites/page.tsx` |
| API 연결 | `getAppProviders()` → `/api/v1/app/providers` |
| 컴포넌트 | ProviderCard 그리드 |
| 요약 카드 | 전체 공급자 / HIGH+ 위험 / 인증 필요 |
| 특이사항 | login_btn 없음 · session 추출 없음 · cookie 없음 |

### 3-6. 로그·감사 `/assistant/logs`

**상태:** ✅ 완료 (APP_LOGS_AUDIT_READONLY_VIEW_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/logs/page.tsx` |
| API 연결 | `getOpsAuditEvents()` → `/api/v1/ops/audit-events` |
| 컴포넌트 | AuditLogList (SummaryCards + 필터바 + 7열 테이블) |
| 정규화 | `normalizeOpsEvents()` · `normalizeMockLogs()` → UnifiedLogEntry |
| 보안 | redacted: true 강제. token 원문 표시 금지 |
| 필터 | 상태(INFO/WARN/ERROR/BLOCKED) × 소스(ops-api/app-mock) |

### 3-7. 스토리지 `/assistant/storage`

**상태:** ✅ 완료 (APP_STORAGE_READONLY_POLISH_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/storage/page.tsx` |
| API 연결 | `getAppStorageStatus()` → `/api/v1/app/storage/status` |
| 컴포넌트 | StorageStatusCard |
| 요약 카드 | 마운트 수 / PERSISTENT / DISPOSABLE |
| 특이사항 | B-3 안내 (approval_tokens 금고 잠금 상태) |

### 3-8. 배포 상태 `/assistant/deployment`

**상태:** ✅ 완료 (APP_DEPLOYMENT_READONLY_POLISH_01)

| 항목 | 내용 |
|------|------|
| 파일 | `app/assistant/deployment/page.tsx` |
| 컴포넌트 | DeploymentSopPanel |
| Mock 데이터 | deploymentStatusMock |
| 요약 카드 | 서버 HEAD / 동기화 상태 / 빌드 필요 |
| SOP 안내 | git pull → docker compose build → up -d (restart 단독 금지) |
| 배지 | server_apply_allowed=false · BAKED_IN_IMAGE · RESTART_ALONE_FORBIDDEN |

---

## 4. 공통 컴포넌트

| 컴포넌트 | 역할 |
|---------|------|
| `AssistantNavBar` | usePathname 기반 활성 탭 하이라이트 (exact/prefix 매칭) |
| `ReadOnlyModeBanner` | 읽기 전용 안내 배너 |
| `ForbiddenActionBanner` | 금지 동작 안내 배너 (reason 표시) |
| `ApiConnectionStateBadge` | API 연결 상태 배지 (loading/success/mock_fallback/error) |
| `EmptyStatePanel` | 빈 데이터 상태 패널 |
| `BackendStatusCard` | 백엔드 상태 카드 |
| `TaskTable` | 작업 큐 테이블 (필터·정렬) |
| `TaskDetailPanel` | 작업 상세 5섹션 |
| `AuditLogList` | 로그·감사 통합 뷰 |
| `ProviderCard` | 외부 공급자 카드 |
| `StorageStatusCard` | 스토리지 마운트 카드 |
| `DeploymentSopPanel` | 배포 SOP 패널 |
| `GateBadge` | 게이트 상태 배지 |

---

## 5. API 연결 계약

### Frontend → Backend 연결 함수

```typescript
// api.ts (GET 전용)
getAssistantHealth()        → GET /api/v1/health
getAssistantInbox()         → GET /api/v1/inbox
getAppHealthSummary()       → GET /api/v1/app/health/summary
getAppProviders()           → GET /api/v1/app/providers
getAppStorageStatus()       → GET /api/v1/app/storage/status
getOpsAuditEvents()         → GET /api/v1/ops/audit-events
getOpsSummary()             → GET /api/v1/ops/summary
```

### 상태 타입 패턴

```typescript
type ApiState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T; meta: ApiConnectionMeta }
  | { status: "empty"; meta: ApiConnectionMeta }
  | { status: "error"; message: string; meta: ApiConnectionMeta }
  | { status: "mock_fallback"; data: T; meta: ApiConnectionMeta };
```

모든 `ApiConnectionMeta`는 `is_read_only: true`, `mutation_allowed: false` 고정.

---

## 6. 백엔드 엔드포인트 현황

| 분류 | 라우터 | 개수 |
|------|--------|------|
| 기존 엔드포인트 | (각 도메인 라우터) | 53개 |
| ops_router | GET /api/v1/ops/* | 7개 |
| app_status_router | GET /api/v1/app/* | 3개 |
| **합계** | | **63개** |
| POST 엔드포인트 | (기존 전부) | **27개** (고정) |

**신규 엔드포인트 (비서앱용)**

```
GET /api/v1/ops/audit-events     → OpsAuditEventsResponse
GET /api/v1/ops/summary          → OpsSummaryResponse
GET /api/v1/ops/tasks            → 작업 목록
GET /api/v1/ops/tasks/{id}       → 작업 상세
GET /api/v1/ops/providers        → 외부 공급자
GET /api/v1/ops/storage          → 스토리지 상태
GET /api/v1/ops/approvals        → 승인 게이트
GET /api/v1/app/health/summary   → 앱 헬스 요약
GET /api/v1/app/providers        → 앱 공급자
GET /api/v1/app/storage/status   → 앱 스토리지
```

---

## 7. 보안 경계

### 절대 금지 (코드 어디서도 불가)

```
approval_token_raw  — 원문 출력 금지
cookie_value        — 원문 출력 금지
secret / password   — 원문 출력 금지
.env 값             — 원문 출력 금지
method: "POST"      — 신규 연결 금지
execute_btn         — 구현 금지
approve_btn         — 구현 금지
delete_btn          — 구현 금지
```

### 의도적 미완 항목 (Intentional Incomplete)

| 코드 | 내용 | 사유 |
|------|------|------|
| B-1 | approve→execute 연결 | 별도 승인 공정 필요 |
| B-2 | DRY_RUN=True 해제 | 미승인 상태 유지 |
| B-3 | approval_tokens 금고 감사 | 감사 공정 미착수 |
| KW-1 | chrome_ui_monitor_state.json dirty | 런타임 캐시 — 오류 아님 |

---

## 8. 전체 공정 이력

| 공정 코드 | 내용 | 커밋 | 상태 |
|---------|------|------|------|
| APP_UI_SHELL_READONLY_API_WIRING_01 | 레이아웃·API 기반 | - | ✅ |
| APP_UI_READONLY_BACKEND_STATUS_CARDS_01 | 대시보드 3카드 | - | ✅ |
| APP_TASK_QUEUE_READONLY_LIST_POLISH_01 | 작업큐 | `396ffef` | ✅ |
| APP_TEST_BASELINE_CURRENT_CONTRACT_SYNC_01 | 회귀 테스트 동기화 | `8ca7b27` | ✅ |
| APP_TASK_DETAIL_READONLY_POLISH_01 | 작업 상세 5섹션 | `a0ec54b` | ✅ |
| APP_LOGS_AUDIT_READONLY_VIEW_01 | 로그·감사 통합 뷰 | `a9e3f45` | ✅ |
| APP_FULL_POLISH_A_E_01 | 나머지 5탭 + 네비 | `73b9dd9` | ✅ |
| **APP_FULL_REGRESSION_CLOSE_01** | **준공** | **-** | **⬜ 대기** |

---

## 9. 테스트 커버리지

| 테스트 파일 | 공정 | 테스트 수 |
|------------|------|---------|
| test_app_ui_readonly_backend_status_cards_20260518.py | 대시보드 | - |
| test_app_task_queue_readonly_list_polish_20260518.py | 작업큐 | 58개 |
| test_app_test_baseline_current_contract_sync_20260518.py | 동기화 | 31개 |
| test_app_task_detail_readonly_polish_20260518.py | 작업 상세 | 46개 |
| test_app_logs_audit_readonly_view_20260518.py | 로그·감사 | 62개 |
| test_app_approval_gate_readonly_polish_20260518.py | 승인 게이트 | 22개 |
| test_app_external_sites_readonly_polish_20260518.py | 외부 사이트 | 18개 |
| test_app_storage_readonly_polish_20260518.py | 스토리지 | 19개 |
| test_app_deployment_readonly_polish_20260518.py | 배포 상태 | 19개 |
| test_app_nav_active_state_polish_20260518.py | 네비 활성 탭 | 17개 |
| **전체** | | **10,121 PASS** (HEAD 73b9dd9) |

---

## 10. 준공 체크리스트 (APP_FULL_REGRESSION_CLOSE_01)

```
[ ] 레이어 감사
    python scripts/ops/codebase_layer_audit.py
    → FORBIDDEN_IMPORT=0, SECURITY_PATTERN=0, CIRCULAR=0

[ ] 품질 게이트
    python scripts/quality_gate.py --staged --enforce --allow-existing-code-change
    → errors=0

[ ] 전체 테스트
    pytest tests/ -q
    → 0 failures, 0 errors

[ ] 각 공정 감사 스크립트
    python scripts/ops/audit_app_approval_gate_readonly_polish.py     → READY
    python scripts/ops/audit_app_external_sites_readonly_polish.py    → READY
    python scripts/ops/audit_app_storage_readonly_polish.py           → READY
    python scripts/ops/audit_app_deployment_readonly_polish.py        → READY
    python scripts/ops/audit_app_nav_active_state_polish.py           → READY
    python scripts/ops/audit_app_logs_audit_readonly_view.py          → READY

[ ] 보안 최종 확인
    approval_token_raw: 0건
    cookie_value: 0건
    method: "POST" 신규: 0건
    execute_btn: 0건

[ ] 백엔드 불변
    엔드포인트: 63개
    POST: 27개
    router.py 수정: 0건

[ ] KW-1 커밋 제외
    scripts/archive/data/chrome_ui_monitor_state.json — 스테이징 제외

[ ] 준공 커밋
    git commit: "feat(app): 비서앱 MVP 준공 — APP_FULL_REGRESSION_CLOSE_01"
    git push origin master
```

---

## 11. 배포 SOP

```
1. git pull origin master
2. docker compose build
3. docker compose up -d
```

> `docker compose restart` 단독 사용 금지 — baked-in 이미지이므로 반드시 build 후 up.

---

*본 설계서는 준공 완료 후 상태(✅)로 갱신 예정.*
