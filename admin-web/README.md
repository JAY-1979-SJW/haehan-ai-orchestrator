# Haehan AI Admin Web

Next.js 기반 관리자 UI (admin-web).

## 현재 단계

- **Stage 11-UI-1A**: 골격(scaffold) 생성 완료
- **Stage 11-UI-1B**: 디자인 기반 이식 완료 (Tailwind v4 / Pretendard / 브랜드 토큰)
- **Stage 11-UI-1C**: 표준 UI 컴포넌트 세트 생성 완료
- **Stage 11-UI-1D**: `/local-agents` 정적 관리자 레이아웃 구성 완료
- **Stage 11-UI-2A**: Local Agent API 타입/클라이언트 레이어 추가 완료
- **Stage 11-UI-2B**: `/local-agents` 페이지 실제 API 연동 완료
- **Stage 11-UI-2C**: cancel modal 구현 및 POST /cancel API 연동 완료
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
