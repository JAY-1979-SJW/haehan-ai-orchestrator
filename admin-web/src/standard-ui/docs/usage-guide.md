# 표준 UI 사용 가이드

## import 방법

```ts
import { AppShell, Sidebar, StatusBadge, MetricCard } from '@/standard-ui';
// 또는
import { colors, spacing } from '@/standard-ui';
```

## AppShell 기본 사용

```tsx
<AppShell
  sidebar={<Sidebar groups={navGroups} />}
  header={<Header title="운영 대시보드" />}
>
  <PageContainer variant="dashboard">
    {/* 페이지 내용 */}
  </PageContainer>
</AppShell>
```

## StatusBadge

```tsx
<StatusBadge status="PASS" />
<StatusBadge status="FAIL" />
<StatusBadge status="LOCAL_AGENT_REQUIRED" />
```

## MetricCard

```tsx
<MetricCard
  label="활성 세대"
  value={22}
  sub="전체 도메인"
  accentColor="#F97316"
/>
```

## 주의사항

- 업무 API 호출 코드를 컴포넌트 안에 넣지 않는다.
- 상태값은 props로만 전달한다.
- 위험 작업(삭제, 배포, 전자서명) 버튼을 표준 UI에 직접 구현하지 않는다.
