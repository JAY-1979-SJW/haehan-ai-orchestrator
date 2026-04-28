# Stage 11-UI-9C home dashboard cleanup report

## 1. 목적
Stage 11-UI-9A WARN 항목 중 홈 화면 KPI 미연동·stale stage 표현 정리

## 2. 참조 UI 폴더

- 경로: `C:\Users\skyjw\OneDrive\03. PYTHON\31. construction-attendance`
- 확인한 주요 파일:
  - `components/admin/ui/PageShell.tsx` — SectionCard, PageShell 패턴
  - `components/admin/ui/StatusBadge.tsx` — 배지 색상/라운드 패턴
  - `components/admin/ui/KpiCard.tsx` — KPI 카드 구조
  - `components/admin/AdminSidebar.tsx` — 사이드바 참조

## 3. 기존 홈 화면 문제

| 항목 | 기존 상태 | 처리 방향 | 판정 |
|---|---|---|---|
| KPI 미연동 | KpiCard 4개 표시, description에 "Stage 11-UI-2에서 연동" 문구 | KpiCard 완전 제거, 운영 카드로 대체 | FIXED |
| stale stage 문구 | STAGES 배열 (Stage 11-UI-1A~2) 하드코딩, done/not done 표시 | STAGES 배열 전체 제거 | FIXED |
| 운영 기준 설명 | 없음 — 개발 진행 현황만 표시 | 현재 운영 기준 테이블로 대체 | FIXED |
| local-agents 진입 | 버튼 1개만 있음 | 운영 카드에 통합 유지 | FIXED |

## 4. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `admin-web/src/app/page.tsx` | STAGES 배열 제거, KpiCard 제거, 운영 대시보드 구조로 재작성 | PASS |

## 5. 반영 내용

| 항목 | 반영 내용 | 판정 |
|---|---|---|
| 홈 대시보드 구조 | 주요 작업 카드 3개 (로컬 에이전트 / 승인·감사로그 준비 중 / 시스템 문서) | PASS |
| 운영 기준 카드 | 현재 운영 기준 테이블 — 기능·위치·상태 3열 | PASS |
| local-agents 링크 | 운영 카드에서 /local-agents 바로 가기 버튼 유지 | PASS |
| legacy fallback 설명 | 운영 기준 테이블에 "legacy FastAPI admin: deprecated fallback" 명시 | PASS |
| 미연동 KPI 제거 | KpiCard 4개 완전 제거 (숫자 "—", stale description 없음) | PASS |
| stale 문구 제거 | STAGES 배열 및 Stage 11-UI-x 하드코딩 전부 제거 | PASS |

## 6. 기존 기능 유지 확인

| 항목 | 결과 |
|---|---|
| /local-agents 기능 미변경 | 확인 — LocalAgentsClient.tsx 미수정 |
| API 경로 변경 없음 | 확인 — api.ts 미수정 |
| capture-screenshot/cancel 변경 없음 | 확인 — local-agents/ 하위 파일 미수정 |
| legacy URL 신규 노출 없음 | 확인 — 홈에 legacy URL 링크 없음 |
| sidebar active route 유지 | 확인 — PageShell/nav 구조 미수정 |
| package/lockfile 변경 없음 | 확인 — package.json/lockfile 미수정 |

## 7. 검증 결과

| 검증 | 결과 |
|---|---|
| lint | PASS (next lint 무출력) |
| typecheck | PASS (tsc --noEmit 무출력) |
| git diff 파일 범위 | admin-web/src/app/page.tsx, docs/reports/stage11_ui9c_home_dashboard_cleanup_report.md |
| secret 출력 여부 | 없음 |

## 8. 다음 단계 제안

권장 다음 단계:
- Stage 11-UI-9D: admin-web 공통 컴포넌트 / 디자인 토큰 정리, 또는
- Stage 12: local-agent 실제 제어 기능 안정화

## 9. 금지 작업 준수 확인

- 서버 접속: 없음
- docker 실행: 없음
- legacy 수정: 없음
- API 경로 변경: 없음
- package/lockfile 변경: 없음
- npm install: 없음
- secret 출력: 없음
