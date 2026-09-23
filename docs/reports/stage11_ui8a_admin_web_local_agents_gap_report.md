# Stage 11-UI-8A admin-web local-agents gap report

## 1. 확인 대상

- legacy route: `GET /api/v1/admin/local-agents` → `ai_orchestrator/routers/admin_ui_router.py:695`
- admin-web route: `/local-agents` → `admin-web/src/app/local-agents/page.tsx`
- 확인한 파일:
  - `admin-web/src/app/local-agents/LocalAgentsClient.tsx`
  - `admin-web/src/app/local-agents/page.tsx`
  - `admin-web/src/lib/api.ts`
  - `admin-web/src/types/local-agent.ts`
  - `ai_orchestrator/routers/admin_ui_router.py`
  - `ai_orchestrator/local_agent_router.py`

---

## 2. 기능 비교표

| 항목 | legacy FastAPI admin | admin-web | 판정 | 비고 |
|---|---|---|---|---|
| 로컬 에이전트 목록 | ✅ 카드형 렌더링 | ✅ 테이블형 렌더링 | OK | 표현 방식만 다름 |
| agent_id 표시 | ✅ 두 번째 줄 텍스트 | ✅ 전용 컬럼 (font-mono) | OK | |
| host 표시 | ✅ 첫 번째 줄 infoText | ✅ 전용 컬럼 | OK | |
| os 표시 | ✅ 두 번째 줄 텍스트 (`os_name`) | ✅ OS 컬럼 (`agent.os_name`) | OK | |
| version 표시 | ✅ 두 번째 줄 `v{version}` | ✅ Version 컬럼 | OK | |
| agent 연결 상태 표시 | ✅ agentStatusBadge | ✅ StatusBadge 컴포넌트 | OK | |
| active_task_count 표시 | ❌ 없음 | ✅ 활성작업 컬럼 | DIFFERENT | admin-web이 추가 정보 제공 |
| current_task_id 표시 | ❌ 없음 | ✅ 현재작업 컬럼 | DIFFERENT | admin-web이 추가 정보 제공 |
| last_seen_at 표시 | ❌ 없음 | ✅ 최근확인 컬럼 | DIFFERENT | admin-web이 추가 정보 제공 |
| 화면 캡처 사전 점검 버튼 | ✅ `dry-run-btn` (dry_run=true) | ✅ `사전 점검` Btn (dryRun: true) | OK | |
| 실제 1회 화면 캡처 버튼 | ✅ `real-capture-btn` (dry_run=false) | ✅ `화면 캡처` Btn + 확인 Modal | OK | admin-web은 reason 입력 Modal 추가 |
| 취소/중단 버튼 | ❌ 없음 (legacy에 cancel 버튼 없음) | ✅ 취소/취소 요청 Btn + Modal | DIFFERENT | admin-web이 기능 추가 |
| 역할 표시 (role) | ❌ 없음 | ✅ RoleBadge (owner/admin/viewer) | DIFFERENT | admin-web이 기능 추가 |
| 작업 목록 (tasks) | ✅ 인라인 task 테이블 | ✅ 별도 섹션 task 테이블 | OK | |
| task status 필터 | ✅ status-filter select | ✅ FilterSelect (태스크 상태) | OK | |
| agent status 필터 | ❌ 없음 | ✅ FilterSelect (에이전트 상태) | DIFFERENT | admin-web이 기능 추가 |
| 폴링(자동 갱신) | ❌ 없음 | ✅ 15초 interval + ON/OFF 토글 | DIFFERENT | admin-web이 기능 추가 |
| KPI 카드 | ❌ 없음 | ✅ 전체/대기/작업중/오프라인 | DIFFERENT | admin-web이 기능 추가 |

---

## 3. API 연동 확인

| API | admin-web 참조 여부 | 파일 위치 | 판정 |
|---|---|---|---|
| GET /api/v1/local-agents | ✅ `getLocalAgents()` | `admin-web/src/lib/api.ts:55-57` | OK |
| GET /api/v1/local-agents/{id}/tasks | ✅ `getAgentTasks()` | `admin-web/src/lib/api.ts:59-68` | OK |
| POST /api/v1/local-agents/{id}/capture-screenshot | ✅ `requestCaptureScreenshot()` | `admin-web/src/lib/api.ts:90-110` | OK |
| POST /api/v1/local-agents/{id}/tasks/{task_id}/cancel | ✅ `cancelTask()` | `admin-web/src/lib/api.ts:71-84` | OK |
| GET /api/v1/auth/me | ✅ `getCurrentUser()` | `admin-web/src/lib/api.ts:86-88` | OK (legacy 없는 추가 기능) |

API Base Path: `NEXT_PUBLIC_API_BASE_PATH` 환경변수 → 기본값 `/orchestrator/api/v1` (edge nginx 경로와 일치)

---

## 4. 발견된 GAP

legacy FastAPI admin에는 있으나 admin-web에 없는 기능: **없음**

admin-web이 legacy 대비 추가 제공하는 기능:
- active_task_count, current_task_id, last_seen_at 컬럼 추가
- 취소/중단 버튼 및 Modal (legacy에는 없었음)
- 역할 기반 접근 제어 표시 (RoleBadge)
- 에이전트 상태 필터
- 자동 폴링 (15초 interval, ON/OFF 토글)
- KPI 카드 (전체/대기/작업중/오프라인 집계)
- 화면 캡처 요청 시 reason 입력 Modal

---

## 5. 다음 단계 제안

**판정: PASS**

admin-web `/local-agents`는 legacy FastAPI admin의 모든 핵심 기능(에이전트 목록, 각 필드 표시, 사전 점검 버튼, 실제 캡처 버튼, 작업 목록, 상태 필터)을 포함하며, 역할 기반 접근 제어·자동 폴링·취소 기능까지 추가되어 있다.

legacy 대비 누락된 기능 없음. admin-web이 운영 기준 화면으로 충분하다.

---

## 6. 금지 작업 준수 확인

- 서버 접속: 없음
- docker 실행: 없음
- git push: 없음
- POST 실행: 없음
- secret 출력: 없음
- legacy 삭제: 없음
- 코드 수정: 없음 (보고서 파일 1개만 신규 작성)
