# Standard UI Package

비서앱(haehan-ai-orchestrator) 전용 표준 UI 패키지.  
모든 웹/관리자 UI가 이 패키지를 기준으로 시공한다.

## 모델하우스 출처

- `C:/Users/skyjw/OneDrive/03. PYTHON/23. 입찰 조회 및 분석/ui`
- Framework: Next.js 16 + React 19 + Tailwind CSS v4

## 폴더 구조

```
standard-ui/
├─ tokens/          디자인 토큰 (color, spacing, typography, radius, shadows)
├─ components/
│  ├─ layout/       AppShell, TopAccentLine, Sidebar, Header, PageContainer
│  ├─ status/       StatusBadge
│  ├─ cards/        MetricCard, DomainUnitCard, GateStatusCard, WarehouseCard
│  ├─ tables/       DataTable, ConstructionPhaseTable
│  ├─ lists/        ReportList, ApprovalQueueList
│  ├─ forms/        Button, Input, Select
│  └─ feedback/     Alert, EmptyState
├─ patterns/        페이지 패턴 문서
├─ docs/            디자인 시스템 문서
└─ index.ts         진입점
```

## 브랜드 원칙

- Orange #F97316 — accent (5% 이하)
- Navy #1E2D4A — 사이드바 (10~20%)
- Neutral — 나머지 (70~80%)
- Top Accent Line — 4px 주황색 상단 고정선 필수

## 금지 사항

- 업무 API 호출
- auth/session/cookie/token 접근
- DB 접근
- 외부 사이트 자동화
- 모델하우스 원본 파일 직접 수정
