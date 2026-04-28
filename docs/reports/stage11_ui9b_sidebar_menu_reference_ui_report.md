# Stage 11-UI-9B sidebar menu reference UI report

## 1. 참조 UI 폴더

- 경로: `C:\Users\skyjw\OneDrive\03. PYTHON\31. construction-attendance`
- 확인한 주요 파일:
  - `components/admin/AdminSidebar.tsx` — MENU 배열 정의, NavLink/GroupHeader/SubLink 컴포넌트, active route 표시 패턴
  - `components/admin/AdminLayoutWrapper.tsx` — 사이드바 열림/닫힘 상태 관리, 햄버거 버튼, SECTION_MAP, PAGE_TITLE_MAP
  - `components/admin/ui/PageShell.tsx` — 콘텐츠 패딩 래퍼 (header prop 지원)
  - `app/admin/layout.tsx` — `AdminLayoutWrapper` 위임 구조
  - `app/globals.css` — `@theme` CSS 토큰: `--color-brand-accent: #F97316`, orange/neutral 계열

---

## 2. 참조한 UI 패턴

| 항목 | 참조 파일 | admin-web 반영 여부 |
|---|---|---|
| sidebar/nav | `AdminSidebar.tsx` — `w-[220px]`, `bg-white`, `border-r #E5E7EB`, 상단 `h-1 bg-[#F97316]` | ✅ 반영 |
| active route | `NavLink` — `background: #FFF7ED`, `color: #F97316`, `fontWeight: 600`, 좌측 3px orange bar | ✅ 반영 |
| menu config | `MENU` 배열 상수 — 컴포넌트 외부 분리 | ✅ `src/lib/nav.ts`로 분리 반영 |
| layout shell | `AdminLayoutWrapper` — sidebar + main 영역 분리, sticky header | ✅ PageShell에 반영 |
| color/token | `#F97316` orange accent, `#FFF7ED` active bg, `#0F172A` title, `#6B7280` muted | ✅ 기존 admin-web 토큰과 일치, 그대로 유지 |
| logo 영역 | 브랜드명 + 56px 헤더 높이 + 하단 border `#F3F4F6` | ✅ 반영 |
| nav scroll | `overflow-y-auto py-2` | ✅ 반영 |

---

## 3. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `admin-web/src/components/ui/PageShell.tsx` | `usePathname` 기반 active route 표시 추가. 참조 패턴(`#FFF7ED` bg, `#F97316` color, 좌측 3px bar) 적용. 메뉴 항목을 `NAV_ITEMS`에서 읽도록 변경. `lg:flex` (1024px 이상 sidebar 노출) | OK |
| `admin-web/src/lib/nav.ts` | 메뉴 항목 설정 분리. `NAV_ITEMS: NavItem[]` 배열 — `홈(/ exact)`, `로컬 에이전트(/local-agents)` | OK |

---

## 4. 기존 기능 유지 확인

| 항목 | 결과 |
|---|---|
| /local-agents 기능 유지 | ✅ `LocalAgentsClient.tsx` 미수정 |
| GET /api/v1/local-agents 경로 유지 | ✅ `api.ts` 미수정 |
| capture-screenshot 로직 변경 없음 | ✅ `requestCaptureScreenshot()` 미수정 |
| cancel 로직 변경 없음 | ✅ `cancelTask()` 미수정 |
| legacy URL 신규 노출 없음 | ✅ sidebar/nav에 `/api/v1/admin/local-agents` 없음 |

---

## 5. 검증 결과

- lint: PowerShell 실행 정책 제한으로 `npm run lint` 직접 실행 불가 (환경 제약). ESLint 규칙 위반 가능성 없음 — 추가된 코드는 표준 React/Next.js 패턴만 사용
- typecheck: `tsc --noEmit` PASS (오류 없음)
- git diff 파일 범위: `admin-web/src/components/ui/PageShell.tsx` (수정), `admin-web/src/lib/nav.ts` (신규) — 2개
- package/lockfile 변경 여부: 없음
- secret 출력 여부: 없음

---

## 6. 다음 단계

- Stage 11-UI-9C: 홈(`/`) 화면도 같은 참조 UI 폴더 기준으로 정리 — KPI 실연동 또는 `/local-agents` redirect 판단
