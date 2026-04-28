# Haehan AI Admin Web

Next.js 기반 관리자 UI (admin-web).

## 현재 운영 기준

- **master / server HEAD**: `7e21318`
- **기준일**: 2026-04-28
- **운영 기준선 문서**: [`docs/ops/admin_web_ops_baseline.md`](../docs/ops/admin_web_ops_baseline.md)

## 구현 단계 이력

- **Stage 11-UI-1A**: 골격(scaffold) 생성 완료
- **Stage 11-UI-1B**: 디자인 기반 이식 완료 (Tailwind v4 / Pretendard / 브랜드 토큰)
- **Stage 11-UI-1C**: 표준 UI 컴포넌트 세트 생성 완료
- **Stage 11-UI-1D**: `/local-agents` 정적 관리자 레이아웃 구성 완료
- **Stage 11-UI-2A**: Local Agent API 타입/클라이언트 레이어 추가 완료
- **Stage 11-UI-2B**: `/local-agents` 페이지 실제 API 연동 완료
- **Stage 11-UI-2C**: cancel modal 구현 및 POST /cancel API 연동 완료
- **Stage 11-UI-5B**: `/api/v1/auth/me` endpoint 신설 및 `getCurrentUser()` API client 추가 완료
- **Stage 11-UI-5C**: `LocalAgentsClient.tsx` role-aware UI 적용 완료 (getCurrentUser 연동, viewer/unknown → cancel/capture disabled)
- **Stage 11-UI-5D**: 401/403 오류 메시지 role-aware 개선 완료 (viewer/unknown 안내 문구 포함)
- Next.js 14 + TypeScript + Tailwind v4 기준

## Stage 11-UI-1D 내용

### 구현 완료

- `/local-agents` 페이지를 실제 관리자 화면 구조에 가깝게 정적 구성
- KPI 카드 4개 (전체 에이전트 / 대기 / 작업중 / 오프라인)
- Agent 상태 필터 UI (FilterBar + FilterSelect)
- Agent 목록 테이블 (9컬럼: Agent ID / Host / OS / Version / 상태 / 활성작업 / 현재작업 / 최근확인 / Actions)
- Task 목록 테이블 (9컬럼: Task ID / Action / Status / Risk / Requested By / Created / Updated / Failure Reason / Actions)
- StatusBadge: agent_status / task status / risk_level 모두 적용
- Task Actions 버튼 placeholder: 상태별 분기 (취소/취소 요청/취소 요청됨/취소됨/—)
- Agent Actions: 작업 보기 / 화면 캡처 버튼 placeholder (disabled)
- EmptyState / Error placeholder 섹션 추가
- 홈(`/`) Stage 진행 현황 카드 추가

### mock 데이터 구성

- `MOCK_AGENTS` 3건: idle / busy / stale 에이전트
- `MOCK_TASKS` 7건: queued / waiting_approval / completed / failed / running / cancel_requested / cancelled

### 미구현 (다음 단계)

- 실제 API fetch 없음 (`src/lib/api.ts` 미연동)
- 에이전트 클릭 → 작업 목록 연동 없음 (정적 고정)
- cancel / capture 실제 동작 없음 (버튼 disabled)
- 필터 상태 관리 없음 (FilterSelect 정적)
- 다음 단계: API 타입/클라이언트 설계 또는 API 연동 (Stage 11-UI-1E / 2)

## 디자인 기준 (Stage 11-UI-1B)

construction-attendance 표준 템플릿 기준:

| 토큰 | 값 |
|------|-----|
| 앱 배경 | `#F5F7FA` |
| 카드 배경 | `#FFFFFF` |
| 테이블 헤더 | `#F3F4F6` |
| border | `#E5E7EB` |
| hover row | `#F9FAFB` |
| 제목 텍스트 | `#0F172A` |
| 본문 텍스트 | `#374151` |
| muted 텍스트 | `#6B7280` |
| accent orange | `#F97316` |
| accent hover | `#EA580C` |
| danger | `#B91C1C` |
| success | `#059669` |
| 폰트 | Pretendard Variable (CDN) |
| 카드 radius | 12px |
| 셀 폰트 | 13px |
| 배지 폰트 | 11px |
| 여백 | px-5 md:px-6 py-5 md:py-6 |

## 구조

- `src/app/globals.css` — Tailwind v4 + Pretendard + CSS 변수 토큰
- `src/app/layout.tsx` — root layout (globals.css import)
- `src/app/page.tsx` — 홈 (KPI 카드 + 메뉴 + Stage 진행 현황)
- `src/app/local-agents/page.tsx` — 로컬 에이전트 정적 관리 화면
- `src/components/ui/` — 공통 UI 컴포넌트 (Stage 11-UI-1C 구현 완료)
- `src/lib/api.ts` — API client (apiFetch / getLocalAgents / getAgentTasks / cancelTask)
- `src/types/local-agent.ts` — Local Agent API 타입 정의

## UI 컴포넌트 (Stage 11-UI-1C)

`src/components/ui/` 아래 생성된 표준 컴포넌트:

| 파일 | 설명 |
|------|------|
| `Btn.tsx` | 버튼 (orange/primary/secondary/danger/success/ghost × xs/sm/md) |
| `StatusBadge.tsx` | 상태 배지 (agent status / task status / risk level) |
| `AdminTable.tsx` | 테이블 세트 (AdminTable, AdminThead, AdminTbody, AdminTr, AdminTh, AdminTd, EmptyRow) |
| `PageShell.tsx` | 페이지 래퍼 (220px 사이드바 + sticky header + content area) |
| `FilterBar.tsx` | 필터 영역 (FilterBar, FilterSelect, FilterPill, FilterSpacer) |
| `Modal.tsx` | 기본 모달 (open/title/children/footer/onClose, max-w-[480px]) |
| `KpiCard.tsx` | KPI 카드 (title/value/description/accentColor) |
| `EmptyState.tsx` | 빈 상태 컴포넌트 (title/description) |
| `index.ts` | 전체 re-export |

## Stage 11-UI-2A 내용

### 추가된 파일

- `src/types/local-agent.ts` — Local Agent API TypeScript 타입 정의
- `src/lib/api.ts` — API client 함수 추가 (기존 buildApiUrl 유지)

### 추가된 타입

`AgentStatus` / `TaskStatus` / `RiskLevel` / `LocalAgent` / `LocalAgentTask` /
`LocalAgentsResponse` / `LocalAgentTasksResponse` / `CancelTaskRequest` /
`CancelTaskResponse` / `ApiErrorResponse`

### 추가된 API client 함수

| 함수 | 설명 |
|------|------|
| `apiFetch<T>` | 공통 fetch 래퍼 (ApiError throw) |
| `getLocalAgents()` | GET /api/v1/local-agents |
| `getAgentTasks(agentId, options?)` | GET /api/v1/local-agents/{id}/tasks |
| `cancelTask(agentId, taskId, reason?)` | POST /api/v1/local-agents/{id}/tasks/{id}/cancel |

### 보안 제외 필드

`token_hash` / `device_token` / `params` / raw result payload — 타입에 미포함

### 미구현 (다음 단계)

- 실제 화면 fetch 연동은 Stage 11-UI-2B 예정
- `/local-agents` 페이지는 아직 정적 mock 데이터 사용

## Stage 11-UI-2B 내용

### 구현 완료

- `page.tsx` → Server Component wrapper (단순 `<LocalAgentsClient />` 렌더)
- `LocalAgentsClient.tsx` 신규 생성 (`"use client"`)
- mount 시 `getLocalAgents()`로 실제 agent 목록 fetch
- 첫 번째 agent 자동 선택 (초기 selectedAgentId)
- agent 선택 변경 시 `getAgentTasks(agentId, { limit: 50, status })` 재조회
- `agentStatusFilter`: 프론트 배열 필터링 (API 재호출 없음)
- `taskStatusFilter` 변경 시 task API 재조회
- KPI 카드: 실제 `agents` 배열 기준 계산 (total / idle / busy / offline+stale)
- loading 상태: `LoadingRow` (colSpan spanning 셀)
- error 상태: `EmptyState` 컴포넌트 (ApiError 메시지 표시)
- empty 상태: `EmptyRow` 컴포넌트
- cancel/capture 버튼: disabled placeholder 유지
- 새로고침 버튼: `fetchAgents()` 재호출 (loading 중 disabled)

### Client Component 구조

```
LocalAgentsClient (use client)
├── agents state (LocalAgent[])
├── agentsLoading / agentsError
├── selectedAgentId (string | null)
├── agentStatusFilter → filteredAgents (프론트 필터)
├── tasks state (LocalAgentTask[])
├── tasksLoading / tasksError / tasksTotal
├── taskStatusFilter → getAgentTasks 재조회
└── KPI: kpiTotal / kpiIdle / kpiBusy / kpiOffline
```

### 보안상 표시 제외 필드

`token_hash` / `device_token` / `params` / raw result payload — 타입에 미포함, 화면 미출력

## Stage 11-UI-2C 내용

### 구현 완료

- Cancel modal 추가 (`Modal` 컴포넌트 활용)
- 상태별 취소 버튼 활성화 정책:
  - `queued` / `waiting_approval` → 취소 (enabled, danger)
  - `delivered` / `running` → 취소 요청 (enabled, secondary)
  - `cancel_requested` → 취소 요청됨 (disabled, ghost)
  - `cancelled` → 취소됨 (disabled, ghost)
  - `completed` / `failed` / `rejected` → —
- `cancelTask(agentId, taskId, cancelReason)` 실제 호출
- 성공 시: modal 닫기 → cancelReason 초기화 → tasks + agents 재조회
- 실패 시: 상태코드별 메시지 표시 (400/403/404/409/기타)
- reason 200자 초과 시 확인 버튼 disabled + 글자수 빨간 표시
- modal 안에 민감정보 입력 경고 문구 표시

### 보안 처리

- `cancel_reason` 필드는 테이블에 표시하지 않음
- reason 원문 `console.log` 없음
- `token_hash` / `device_token` / `params` / raw payload 화면 미출력

### 미구현 (다음 단계)

- 화면 캡처 실제 동작 없음 (버튼 disabled placeholder 유지)

## Stage 11-UI-3B 내용

### 추가된 파일

- `Dockerfile` — Next.js standalone 기준 multi-stage Dockerfile
- `.dockerignore` — Docker build 제외 목록

### Dockerfile 구성

- **node:20-alpine** 기반 3-stage 빌드
- Stage 1 `deps`: `npm ci`로 의존성 설치
- Stage 2 `builder`: `npm run build` (standalone output)
- Stage 3 `runner`: `.next/standalone` + `.next/static` 복사, non-root(nextjs) 실행
- `FASTAPI_BASE_URL` 등 환경변수는 Dockerfile에 포함하지 않음 (compose 단계에서 주입)

### 빌드 방법

```bash
# 로컬 검증용
docker build -t haehan-ai-orchestrator-admin-web:test ./admin-web
```

### 미구현 (다음 단계)

- docker-compose.yml 연동: Stage 11-UI-3C 예정
- nginx reverse proxy 설정: Stage 11-UI-3D 예정
- 서버 배포 반영: Stage 11-UI-3C/3D 이후 처리

## Stage 11-UI-3F 내용

### API base path 보정

- 운영 기본 API 경로: `/orchestrator/api/v1`
- `src/lib/api.ts`의 `API_BASE_PATH` 기본값을 `/orchestrator/api/v1`으로 변경
- 로컬 개발에서 다른 경로를 사용하려면 `NEXT_PUBLIC_API_BASE_PATH` 환경변수 설정

```bash
# 로컬 개발 예시 (.env.local — 커밋하지 않음)
NEXT_PUBLIC_API_BASE_PATH=/api/v1
```

- `.env` / `.env.local` 파일은 커밋하지 않음 (`.gitignore` 적용)
- `.env.example`은 이번 단계에서 생성하지 않음

### buildApiUrl 동작

| 입력 경로 | 결과 |
|---|---|
| `/local-agents` | `/orchestrator/api/v1/local-agents` |
| `/api/v1/local-agents` | `/orchestrator/api/v1/local-agents` |
| `/orchestrator/api/v1/local-agents` | `/orchestrator/api/v1/local-agents` (중복 방지) |
| `https://...` | 그대로 반환 |

## 운영 접속 경로

| 용도 | 경로 |
|---|---|
| admin-web root | `/orchestrator/admin-web/` |
| 로컬 에이전트 관리 | `/orchestrator/admin-web/local-agents` |
| FastAPI API | `/orchestrator/api/v1/` |
| health check | `/orchestrator/api/v1/health` |
| legacy FastAPI admin | `/orchestrator/api/v1/admin/local-agents` |

### 배포 후 smoke 요약

```bash
# admin-web root
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/admin-web/ -k  # → 200

# local-agents page
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/admin-web/local-agents -k  # → 200

# FastAPI health
curl -fsS -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/health -k  # → {"status":"ok"}
```

### legacy route

기존 FastAPI admin 화면은 `/orchestrator/api/v1/admin/local-agents` 경로로 유지된다.
nginx rollback 시 이 경로를 fallback으로 사용한다.

## Stage 11-UI-4B 내용

### 추가된 타입 (src/types/local-agent.ts)

| 타입 | 설명 |
|------|------|
| `CaptureScreenshotRequest` | capture-screenshot POST body (`dry_run`, `reason?`, `note?`) |
| `CaptureScreenshotResponse` | capture-screenshot 응답 (`task_id`, `agent_id`, `action`, `status`, `dry_run`, `approval_required`) |

### 추가된 API client 함수 (src/lib/api.ts)

| 함수 | 설명 |
|------|------|
| `requestCaptureScreenshot(agentId, options?)` | POST /local-agents/{agent_id}/capture-screenshot |

### capture API 동작

- 단일 endpoint 사용: `POST /local-agents/{agent_id}/capture-screenshot`
- `dry_run=true`: 사전 점검 (실제 캡처 없음)
- `dry_run=false`: 실제 캡처 요청
- 실제 캡처(`dry_run=false`)도 `approval_required=true` 흐름으로 진행됨
- `agentId`는 `encodeURIComponent` 처리

### 보안 처리

- 이미지 raw payload 타입 미포함 (이미지 데이터 필드 타입 정의 제외)
- 민감값(`token_id`, `device_token`, `token_hash`) 타입 미포함
- reason/note 원문 `console.log` 없음
- raw response `console.log` 없음

### 미구현 (다음 단계)

- UI 버튼 활성화 및 Modal 연동은 Stage 11-UI-4C 예정
- `LocalAgentsClient.tsx` 이번 단계에서 미수정

## Stage 11-UI-4C 내용

### 구현 완료

- **사전 점검 버튼**: agent Actions 컬럼에 추가. `dry_run=true`로 즉시 `requestCaptureScreenshot` 호출. Confirm Modal 없이 실행.
- **화면 캡처 버튼**: Confirm Modal 필수. `dry_run=false`로 `requestCaptureScreenshot` 호출.
- **기존 작업 보기 버튼**: 그대로 유지.

### agent 상태별 버튼 정책

| agent_status | 사전 점검 | 화면 캡처 |
|---|---|---|
| idle | enabled | enabled |
| busy | enabled | enabled |
| offline | disabled | disabled |
| stale | disabled | disabled |
| unknown / 기타 | disabled | disabled |

### 사전 점검 동작

1. 사전 점검 버튼 클릭 → `requestCaptureScreenshot(agent_id, { dryRun: true, reason: "admin_web_dry_run_check" })`
2. 성공 시 `captureSuccess` 배너 표시: `task_id` / `status` / `dry_run` / `approval_required` 4개 필드만 표시
3. 실패 시 `captureError` 배너 표시

### 화면 캡처 Confirm Modal

- 대상 agent `host` / `agent_id` 표시
- 안내 문구: "승인 후 로컬 PC에서 1회 화면 캡처가 실행됩니다. 서버에는 이미지가 업로드되지 않습니다."
- 경고 문구(빨간): "비밀번호, OTP, 인증서, 카드정보 화면에서는 캡처하지 마세요."
- reason optional textarea (최대 200자, 글자수 표시)
- 버튼: 닫기 / 캡처 요청

### 실제 캡처 API 호출 흐름

1. 캡처 요청 클릭 → `requestCaptureScreenshot(agent_id, { dryRun: false, reason })`
2. 성공: modal 닫기 → captureSuccess 배너 표시 → agents/tasks 재조회
3. 실패: captureError 표시, modal 유지

### approval_required 흐름

- `dry_run=false` 요청도 `approval_required=true`로 응답됨
- 성공 메시지: "화면 캡처 요청이 생성되었습니다. 텔레그램 승인 후 실행됩니다."

### 오류 메시지 (HTTP status별)

| status | 메시지 |
|---|---|
| 403 | 권한이 없습니다. |
| 404 | 에이전트를 찾을 수 없습니다. |
| 기타 | 캡처 요청에 실패했습니다. (HTTP N) |

### 성공 메시지 표시 필드

`task_id` / `status` / `dry_run` / `approval_required` — 이 4개 필드만 표시.

raw payload (이미지 데이터, token_id, device_token, token_hash 등) 미표시.

### 보안 처리

- 비밀번호/OTP/인증서/카드정보 화면 캡처 금지 안내를 Confirm Modal에 명시
- capture result raw payload UI 미노출
- `token_id` / `device_token` / `token_hash` / 이미지 raw payload 표시 없음
- `console.log(result)` 없음
- 자동/주기 캡처 없음 — 사용자 명시 클릭으로만 실행
- 쿠키/세션/토큰 추출 없음

### capture 상태 관리 (LocalAgentsClient)

```
captureTargetAgent: LocalAgent | null  — 캡처 대상 agent
captureMode: "dry_run" | "real" | null — 현재 capture 모드
captureLoading: boolean                — API 호출 중
captureError: string | null            — 오류 메시지
captureSuccess: CaptureSuccessInfo | null — 성공 결과 (4개 필드)
captureReason: string                  — 실제 캡처 요청 사유
```

## 참고

- 운영 기준선 문서: [`docs/ops/admin_web_ops_baseline.md`](../docs/ops/admin_web_ops_baseline.md)
- FastAPI API 서버(`ai_orchestrator/`)는 기존 그대로 유지
- 기존 FastAPI admin 화면은 legacy fallback으로 보존
- 운영 nginx route: `/orchestrator/admin-web/` → admin-web, `/orchestrator/api/` → FastAPI

## Stage 11-UI-5B: auth/me endpoint 및 getCurrentUser() 추가

### FastAPI 변경

- `ai_orchestrator/auth_router.py` 신설
- `GET /api/v1/auth/me` endpoint 추가
- 반환 필드: `actor` (string), `role` (string)
- 반환하지 않는 필드: password, password_hash, token, session, cookie, secret, hash
- `Depends(get_current_user)` 사용 — `require_role` 미사용이므로 viewer도 접근 가능
- AUTH_ENABLED=False: `{actor: "system", role: "owner"}` 반환
- AUTH_ENABLED=True 인증 없음: 401 반환

### admin-web 변경

- `src/types/auth.ts` 신설 — `UserRole`, `CurrentUser` 타입
- `src/lib/api.ts` — `getCurrentUser(): Promise<CurrentUser>` 추가 (GET /auth/me)
- `LocalAgentsClient.tsx` 미수정 (버튼 visibility 제어는 Stage 11-UI-5C 예정)

### 보안 기준

- UI role 표시는 UX 보조이며 최종 권한은 FastAPI `require_role`이 강제
- auth/me는 자기 role 조회 전용 read-only endpoint

## Stage 11-UI-5C: role-aware UI 적용 (LocalAgentsClient)

### 구현 완료

- `getCurrentUser()` mount 시 호출 (fetchAgents와 병렬)
- `currentUser` / `userLoading` / `userError` state 추가
- `canMutate = !userLoading && (role === "admin" || role === "owner")`
- 권한 안내 배지 (`RoleBadge`) — 필터 상단 표시
  - owner: 소유자 권한 (amber 배지)
  - admin: 관리자 권한 (blue 배지)
  - viewer: 조회 전용 권한 (gray 배지)
  - unknown/error: 권한 확인 실패 (red 배지)
- cancel 버튼: `canMutate=false`이면 disabled + `title="admin/owner 권한 필요"`
- 사전 점검 / 화면 캡처 버튼: `canMutate=false`이면 disabled + title 안내
- `userLoading` 중에는 canMutate=false → 위험 버튼 disabled
- 조회 기능(에이전트 목록, 작업 목록)은 role 무관하게 유지

### UI 권한 정책

| 역할 | cancel | capture |
|------|--------|---------|
| owner / admin | 상태 조건 충족 시 enabled | agent idle/busy 시 enabled |
| viewer | disabled (title 안내) | disabled (title 안내) |
| unknown / error / loading | disabled | disabled |

### 보안 기준

- **서버 `require_role`이 최종 보안 기준**이다. UI disabled는 UX 보조일 뿐이며 서버 403 응답은 기존대로 처리된다.
- `currentUser` raw dump / console.log 없음
- token/hash/session/cookie 표시 없음
- actor는 짧게 표시하되 민감한 값 없음

### 미구현 (다음 단계)

- 403/401 UX 개선: Stage 11-UI-5D 예정

## Stage 11-UI-5D: 401/403 오류 메시지 role-aware 개선

### 구현 완료

- `roleAwareAuthMessage(status, role)` helper 추가
  - 401: "로그인이 필요합니다. 브라우저 인증 상태를 확인하세요."
  - 403 + viewer: "조회 전용 권한입니다. admin/owner 권한이 필요합니다."
  - 403 + unknown: "권한 확인이 필요합니다. admin/owner 권한이 필요합니다."
  - 403 + admin/owner: "권한이 없습니다. 서버 권한 정책을 확인하세요."
- `fetchErrorMessage(err, fallback, role)` helper — 조회 API 오류용
- cancel 오류: 401/403 → roleAwareAuthMessage 적용 (400/404/409 기존 유지)
- capture 오류: 401/403 → roleAwareAuthMessage 적용 (404 기존 유지)
- agents/tasks 조회 오류: 401/403 → roleAwareAuthMessage 적용
- `RoleBadge` 안내 문구 보강
  - viewer: "조회 전용입니다. 취소·캡처는 admin/owner 권한이 필요합니다."
  - unknown/error: "권한 확인 실패 시 위험 작업은 비활성화됩니다."

### 보안 기준

- **서버 `require_role`이 최종 보안 기준**. 버튼 disabled는 UX 보조.
- Authorization/Cookie/session/token 표시 없음
- console.log 없음
- secret/env 값 표시 없음

## 운영 접속 경로

| 용도 | 경로 |
|---|---|
| admin-web root | `/orchestrator/admin-web/` |
| 로컬 에이전트 관리 | `/orchestrator/admin-web/local-agents` |
| FastAPI API | `/orchestrator/api/v1/` |
| auth/me | `/orchestrator/api/v1/auth/me` |
| health check | `/orchestrator/api/v1/health` |
| legacy FastAPI admin | `/orchestrator/api/v1/admin/local-agents` |

## 권한 정책 요약

| 역할 | 조회 | cancel | capture |
|---|---|---|---|
| owner / admin | 가능 | 상태 조건 충족 시 활성 | agent idle/busy 시 활성 |
| viewer | 가능 | disabled | disabled |
| unknown / error / loading | 가능 | disabled | disabled |

**서버 `require_role`이 최종 보안 기준이다. UI 버튼 disabled는 UX 보조.**

## Stage 11-UI-6B: background polling 구현

### 구현 완료

- `POLLING_INTERVAL_MS = 15_000` (15초 주기)
- `backgroundFetchAgents()` / `backgroundFetchTasks()` — polling 전용 background fetch
  - `agentsLoading` / `tasksLoading` 변경 없음 → loading skeleton 깜빡임 없음
  - 최초 로딩 / 수동 새로고침의 loading UX 기존 그대로 유지
- `isPollingAgentsRef` / `isPollingTasksRef` — in-flight guard (중복 요청 방지)
- `pollingIntervalRef` — `setInterval` 관리, unmount 시 `clearInterval`
- `lastRefreshedAt` — 마지막 갱신 시각 (`HH:mm:ss`) 헤더 우측 표시
- `pollingError` — 자동 새로고침 실패 시 작은 경고 텍스트 표시

### polling 대상

| 대상 | 주기 |
|---|---|
| GET /local-agents | 15초 |
| GET /local-agents/{id}/tasks | 15초 |
| GET /auth/me | 최초 1회만 (polling 제외) |
| POST /cancel | polling 절대 불가 (사용자 명시 클릭만) |
| POST /capture-screenshot | polling 절대 불가 (사용자 명시 클릭만) |

### 중지/보호 조건

- `document.hidden === true` → polling skip (탭 최소화/전환 시)
- capture modal open (`captureMode === "real" && captureTargetAgent !== null`) → agents/tasks polling skip
- cancel modal open (`cancelTargetTask !== null`) → tasks polling skip
- in-flight guard → 이전 요청 완료 전 중복 요청 방지
- visibilitychange → 탭 복귀 시 즉시 background refresh 1회 수행
- component unmount → `clearInterval` + event listener 제거

### 미구현 (다음 단계)

- ON/OFF 토글: Stage 11-UI-6C 예정
- polling 상태 배지 / 연속 실패 카운트: Stage 11-UI-6C 예정
- polling timer reset (수동 새로고침 후): Stage 11-UI-6C 예정

## Stage 11-UI-6C: 자동 새로고침 ON/OFF 토글 및 polling 상태 배지

### 구현 완료

- **자동 새로고침 토글**: 헤더 우측에 `Btn variant="ghost" size="xs"` 버튼 추가
  - ON 상태: "자동 새로고침 ON" 표시
  - OFF 상태: "자동 새로고침 OFF" 표시
- **polling 상태 배지**: 토글 버튼 좌측에 인라인 배지 표시

| 상태 | 문구 | 색상 |
|---|---|---|
| active | 자동 갱신 중 | 초록 (D1FAE5 / 065F46) |
| paused | 일시중지 | 앰버 (FEF3C7 / 92400E) |
| off | 자동 갱신 꺼짐 | 회색 (F3F4F6 / 6B7280) |
| error | 자동 갱신 오류 | 빨강 (FEE2E2 / B91C1C) |

### 상태 판정 기준

- `pollingEnabled=false` → off
- `pollingError` 존재 → error
- `document.hidden` 또는 capture modal open → paused
- 그 외 → active

### polling ON/OFF 동작

- OFF 시: `setInterval` 미생성 (interval 자체 없음)
- ON 복귀 시: 즉시 background refresh 1회 수행 후 15초 주기 재개
- 수동 새로고침 버튼은 OFF 상태에서도 동작
- polling timer reset (수동 새로고침 후): 미구현 (6D에서 재검토 예정)

### GET polling 전용 보장

- polling interval은 GET /local-agents, GET /local-agents/{id}/tasks만 호출
- POST /cancel, POST /capture-screenshot 자동 호출 없음
- 사용자 명시 클릭으로만 POST 작업 실행

### 보안

- `pollingEnabled` state 자체는 UI 제어 전용, 서버 권한 미변경
- console.log, secret, token 표시 없음
- Authorization/Cookie 출력 없음

### 미구현 (다음 단계)

- 수동 새로고침 후 polling timer reset: 6D에서 재검토
- 커밋/PR/서버 반영/smoke: Stage 11-UI-6D 예정

## 후속 작업

| 단계 | 내용 |
|---|---|
| Stage 11-UI-6D | 커밋/PR/서버 반영/smoke |
| Stage 11-UI-7 | legacy FastAPI admin deprecated 계획 |
| Stage 12-GABIA-1 | 가비아 자동화 설계 |
