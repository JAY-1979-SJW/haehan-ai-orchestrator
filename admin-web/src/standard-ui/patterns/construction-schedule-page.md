# Construction Schedule Page 패턴

## 용도
앱 건축 공정표 단계별 현황 조회.

## 구성 요소
- PageContainer(variant=default)
- ConstructionPhaseTable
- StatusBadge (각 단계)
- Alert (미완료 단계 안내)

## 데이터 구조
```ts
interface ConstructionPhaseRow {
  phase: string;     // 단계명
  code: string;      // 예: FOUNDATION_01
  status: StatusValue;
  completedAt?: string;
  notes?: string;
}
```

## 금지
- 공정 단계 직접 수정 UI (조회 전용)
