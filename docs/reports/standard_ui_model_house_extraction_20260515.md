# 표준 UI 패키지 추출 보고서 (2026-05-15)

## 단계: UI_MODEL_HOUSE_TO_STANDARD_UI_PACKAGE_01

## 1. 모델하우스 원본

- source: `C:/Users/skyjw/OneDrive/03. PYTHON/23. 입찰 조회 및 분석/ui`
- framework: Next.js 16 + React 19 + Tailwind CSS v4 + TypeScript
- 원본 수정: 없음 (read-only 조사만)

## 2. 표준 UI 폴더

- target: `admin-web/src/standard-ui/`

```
admin-web/src/standard-ui/
├─ README.md
├─ index.ts
├─ tokens/           colors, spacing, typography, radius, shadows
├─ components/
│  ├─ layout/        TopAccentLine, AppShell, Sidebar, Header, PageContainer
│  ├─ status/        StatusBadge (PASS/WARN/FAIL/HOLD/BLOCKED/LOCAL_AGENT/USER_DIRECT 등)
│  ├─ cards/         MetricCard, DomainUnitCard, GateStatusCard, WarehouseCard
│  ├─ tables/        DataTable, ConstructionPhaseTable
│  ├─ lists/         ReportList, ApprovalQueueList
│  ├─ forms/         Button, Input, Select
│  └─ feedback/      Alert, EmptyState
├─ patterns/         dashboard, status, report, gate, construction-schedule, warehouse, approval
└─ docs/             design-system, usage-guide, do-dont, migration-guide
```

## 3. 디자인 토큰

| 항목 | 값 |
|------|----|
| primaryOrange | #F97316 |
| navyBase | #1E2D4A |
| bgBase | #F5F7FA |
| textPrimary | #0F172A |
| Top Accent Line | 4px fixed 상단 |
| Sidebar width | 224px |

## 4. 추출한 컴포넌트 (19개)

TopAccentLine, AppShell, Sidebar, Header, PageContainer,
StatusBadge, MetricCard, DomainUnitCard, GateStatusCard, WarehouseCard,
DataTable, ConstructionPhaseTable, ReportList, ApprovalQueueList,
Button, Input, Select, Alert, EmptyState

## 5. 제외한 항목

- G2B API 호출 코드 (G2B_API_BASE, fetch)
- 인증/세션 로직 (g2b_token, localStorage)
- DB 접근 코드
- 외부 사이트 자동화
- 입찰 도메인 특화 데이터 (소방공사, 낙찰업체 등)
- Next.js App Router 라우팅
- ImpersonationBanner, PremiumGate 등 서비스 특화 컴포넌트

## 6. 테스트/게이트 결과

| 항목 | 결과 |
|------|------|
| 표준 UI 테스트 | 38 passed |
| 표준 UI audit | PASS (24/24) |
| 기존 테스트 | 388 passed |
| layer audit | 10 passed |
| quality gate | errors=0, warnings=0 |

## 7. 판정: PASS
