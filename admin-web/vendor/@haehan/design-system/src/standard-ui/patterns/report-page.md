# Report Page 패턴

## 용도
보고서 목록 조회 및 상세 열람.

## 구성 요소
- PageContainer(variant=default)
- ReportList
- 상세: 마크다운 렌더링 영역 (별도)

## 데이터 구조
```ts
interface ReportListItem {
  title: string;
  path: string;      // docs/reports/ 상대 경로
  date: string;      // YYYY-MM-DD
  category: string;  // 예: g2b, governance, architecture
}
```

## 금지
- 보고서 내 secret/env 값 렌더링
- 보고서 삭제/수정 UI (read-only)
