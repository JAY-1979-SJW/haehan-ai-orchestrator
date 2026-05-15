# Dashboard 패턴

## 용도
운영 현황 한눈 요약. KPI 지표 + 도메인 상태 + 최근 활동.

## 구성 요소
- TopAccentLine (필수)
- AppShell > Sidebar + Header + PageContainer(variant=dashboard)
- MetricCard × N (KPI 행)
- DomainUnitCard × N (도메인 세대별)
- GateStatusCard × N (게이트 현황)
- ReportList (최근 보고서)

## 레이아웃 비율
- KPI 행: 3~4열 grid, gap 16px
- 도메인 카드: 2열 grid
- 게이트 카드: 2~3열 grid

## 상태 배지 기준
- 모든 집계 수치 0 → PASS
- 1개 이상 WARN → WARN
- 1개 이상 FAIL → FAIL

## 금지
- 실시간 API 폴링 (30초 이상 간격 유지)
- 위험 작업 버튼 직접 노출
- 개인정보 데이터 노출
