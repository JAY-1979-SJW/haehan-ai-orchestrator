# Haehan AI Admin Web

Next.js 기반 관리자 UI (admin-web).

## 현재 단계

- **Stage 11-UI-1A**: 골격(scaffold) 생성 완료
- **Stage 11-UI-1B**: 디자인 기반 이식 완료 (Tailwind v4 / Pretendard / 브랜드 토큰)
- **Stage 11-UI-1C**: 표준 UI 컴포넌트 세트 생성 완료
- **Stage 11-UI-1D**: `/local-agents` 정적 관리자 레이아웃 구성 완료
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
- `src/lib/api.ts` — API helper (Stage 11-UI-1E/2에서 구현)

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

## 참고

- FastAPI API 서버(`ai_orchestrator/`)는 기존 그대로 유지
- 기존 FastAPI admin 화면은 legacy로 보존
- Docker/compose/nginx 연동은 미구현 (이후 단계에서 처리)
- npm install은 아직 수행하지 않음 (Stage 11-UI-2 이후 처리)
