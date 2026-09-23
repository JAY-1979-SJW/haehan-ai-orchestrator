# Stage 11-UI-9A admin-web layout audit

## 1. 목적

admin-web을 운영 기준 관리자 UI로 확정한 이후, 전체 메뉴/라우트/레이아웃/디자인 일관성을 감사한다.
코드 수정 없이 read-only 정적 분석만 수행한다.

---

## 2. route/page 구조

| route 또는 파일 | 역할 | 판정 | 비고 |
|---|---|---|---|
| `src/app/layout.tsx` | Root layout — `<html><body>{children}</body></html>` | REFACTOR_CANDIDATE | 공통 레이아웃 없음. body에 sidebar/nav 없이 children만 렌더. PageShell이 각 페이지에서 레이아웃을 직접 담당 |
| `src/app/page.tsx` | 홈 대시보드 (`/`) | CLEANUP | KPI 카드 값 모두 `"—"` (미연동). Stage 진행 현황 목록의 done 플래그가 실제 완료 상태와 불일치 |
| `src/app/local-agents/page.tsx` | 로컬 에이전트 관리 (`/local-agents`) | OK | 운영 기준 화면, `LocalAgentsClient` 위임 구조로 명확 |
| `src/app/local-agents/LocalAgentsClient.tsx` | 로컬 에이전트 클라이언트 컴포넌트 | OK | API 연동, 폴링, 취소/캡처 Modal 완비 |
| `src/app/globals.css` | 전역 CSS 토큰 정의 | OK | Tailwind v4 `@theme` 기반, CSS 변수로 색상/폰트 정의 |

현재 구현된 route: `/` (홈), `/local-agents` — **총 2개**

---

## 3. 공통 레이아웃/메뉴 구조

| 항목 | 위치 | 현재 상태 | 판정 |
|---|---|---|---|
| Root layout | `src/app/layout.tsx` | `<html><body>{children}</body></html>` 최소 구조 — sidebar/nav 없음 | REFACTOR_CANDIDATE |
| Sidebar | `src/components/ui/PageShell.tsx:15` | `<aside>` 내 하드코딩 — `홈`, `로컬 에이전트` 2개 링크 | REFACTOR_CANDIDATE |
| 메뉴 항목 정의 | `PageShell.tsx` 내 인라인 JSX | 별도 메뉴 설정 파일 없음. 신규 라우트 추가 시 직접 수정 필요 | REFACTOR_CANDIDATE |
| Active route 처리 | `PageShell.tsx` | 현재 route에 대한 active 표시(굵기/색상 강조) 없음 | CLEANUP |
| Header (topbar) | `PageShell.tsx:43` | sticky header, 페이지 title + description + headerRight slot | OK |
| Mobile nav | `PageShell.tsx` | `hidden md:flex` — 모바일에서 sidebar 숨김, 모바일용 hamburger/drawer 없음 | UNKNOWN |
| Orange accent bar | `PageShell.tsx:17,40` | sidebar 상단 + main 상단 2곳에 `h-[4px] bg-[#F97316]` — 일관됨 | OK |
| 브랜드명 | `PageShell.tsx:19` | "Haehan AI Admin" 하드코딩 | OK (현재 단일 앱) |

---

## 4. 디자인 시스템 적용 상태

| 항목 | 현재 상태 | 판정 | 권장 방향 |
|---|---|---|---|
| CSS 토큰 정의 | `globals.css` `@theme` — orange(`#F97316`), danger(`#B91C1C`), success(`#059669`), neutral 계열 정의됨 | OK | 현행 유지 |
| 컴포넌트의 토큰 사용 | 대부분 컴포넌트가 `var()` 대신 `#F97316` 등 리터럴 hex 직접 사용 | CLEANUP | `globals.css` 토큰을 Tailwind 커스텀 색상 또는 CSS 변수로 일관 참조하도록 점진 정리 권장 |
| Btn 컴포넌트 | `orange`, `primary`, `secondary`, `danger`, `success`, `ghost` 6종 variants, `xs/sm/md` sizes — 충분한 범위 | OK | 현행 유지 |
| StatusBadge 컴포넌트 | agent 상태 4종, task 상태 9종, risk 3종 완비 | OK | 현행 유지 |
| AdminTable 컴포넌트 | `AdminTable/Thead/Tbody/Tr/Th/Td/EmptyRow` 분리 | OK | 현행 유지 |
| KpiCard 컴포넌트 | 타이틀/값/accentColor/description | OK | 현행 유지 |
| Modal 컴포넌트 | open/title/onClose/footer slot | OK | 현행 유지 |
| FilterBar 컴포넌트 | `FilterBar/FilterSelect/FilterPill/FilterSpacer` | OK | 현행 유지 |
| 홈(`/`) 스타일 | `page.tsx` 내 KPI/메뉴/stage 목록이 `PageShell` + 인라인 Tailwind로 구현 | CLEANUP | KPI 값 미연동 상태 — `"—"` placeholder가 운영자 혼란 가능 |
| 폰트 | Pretendard Variable CDN 로드 (`globals.css:1`) | OK | 현행 유지. CDN 의존 허용 범위 내 |

---

## 5. legacy/FastAPI admin 의존성

| 항목 | 위치 | 현재 상태 | 판정 |
|---|---|---|---|
| sidebar 메뉴 legacy 링크 | `PageShell.tsx` | `/local-agents`(admin-web)만 연결, legacy URL 없음 | OK |
| 홈 메뉴 버튼 legacy 링크 | `src/app/page.tsx` | `/local-agents`(admin-web)만 연결, legacy URL 없음 | OK |
| README legacy 섹션 | `admin-web/README.md:278` | 8D에서 `deprecated fallback` 명시로 정리 완료 | OK |
| FastAPI HTML 화면 확장 흔적 | `ai_orchestrator/routers/admin_ui_router.py` | 8D 이후 코드 추가 없음, deprecated banner 존재 | OK |

---

## 6. 개선 후보 분류

### OK
- `src/app/local-agents/` — 운영 기준 화면 완비
- `src/components/ui/Btn`, `StatusBadge`, `AdminTable`, `KpiCard`, `Modal`, `FilterBar` — 디자인 시스템 컴포넌트 충분
- `globals.css` `@theme` 토큰 정의
- sidebar/menu에서 legacy URL 미노출
- Orange accent bar 일관 적용

### CLEANUP
- `src/app/page.tsx` — KPI 값 `"—"` 미연동 + Stage 진행 현황 done 플래그 stale
- `PageShell.tsx` sidebar — active route 미표시 (현재 route와 메뉴 항목이 시각적으로 구분되지 않음)
- 컴포넌트들의 hex 리터럴 색상 → CSS 변수/Tailwind 토큰 참조 통일 (선택적)

### UI_STANDARDIZE
- 현재 구현된 화면이 `/local-agents` 1개뿐이므로 화면 간 스타일 불일치 없음
- 신규 화면 추가 시 `PageShell` + `AdminTable` + `KpiCard` 패턴 그대로 적용할 것

### REFACTOR_CANDIDATE
- `src/app/layout.tsx` — Root layout이 shell을 포함하지 않아 각 page가 `PageShell`을 직접 렌더. 화면 수 증가 시 공통 레이아웃을 Root layout으로 올리는 것이 유지보수에 유리
- `PageShell.tsx` 내 메뉴 하드코딩 — 신규 route 추가 시 `PageShell.tsx`를 직접 수정해야 함. `NAV_ITEMS` 배열 추출 또는 별도 `nav.config.ts` 분리 권장
- 모바일 sidebar 없음 — 운영 환경이 데스크탑 전용이면 현행 유지 가능, 모바일 접근이 필요하면 drawer/hamburger 추가 필요

### UNKNOWN
- 모바일 환경 사용 여부 — `hidden md:flex` sidebar가 모바일에서 완전히 숨겨짐. 운영자가 모바일로 접근하는지 확인 필요
- `src/types/auth.ts` `CurrentUser` 타입이 실제 서버 `/api/v1/auth/me` 응답과 100% 일치하는지 — 정적 검사만으로 서버 응답 스키마 확인 불가

---

## 7. 다음 단계 제안

**판정: WARN**

운영 기준 화면(`/local-agents`)은 충분히 구현되어 있고 디자인 시스템 컴포넌트도 갖춰져 있다.
단, 아래 2가지가 운영 관리자 UI 완성도를 낮추는 요소로 남아 있다:

1. **홈(`/`) 미완성**: KPI 값 미연동, Stage 진행 현황 stale
2. **Sidebar active route 미표시**: 현재 위치를 메뉴에서 시각적으로 구분하지 못함

권장 다음 단계:

| 단계 | 내용 | 우선순위 |
|---|---|---|
| Stage 11-UI-9B | `PageShell` sidebar — active route 강조 + 메뉴 항목 설정 분리 | 높음 |
| Stage 11-UI-9C | 홈(`/`) 화면 개선 — KPI 실연동 또는 `/local-agents`로 redirect | 높음 |
| Stage 11-UI-9D | Root layout 공통화 — `src/app/layout.tsx`에 `PageShell` 또는 공통 nav 올리기 | 중간 |
| Stage 11-UI-9E | 컴포넌트 hex 리터럴 → CSS 변수 토큰 정리 | 낮음 (선택) |

---

## 8. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- npm build: 없음
- npm test: 없음
- git push: 없음
- legacy 삭제: 없음
- secret 출력: 없음
