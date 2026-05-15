# Warehouse Page 패턴

## 용도
공유 창고(Shared Warehouse) 구조 및 파일 현황 조회.

## 구성 요소
- PageContainer(variant=default)
- WarehouseCard × 각 창고 영역
- DataTable (파일 목록, 선택)

## 데이터 구조
```ts
interface WarehouseArea {
  title: string;
  path: string;      // 예: data/g2b/
  status: StatusValue;
  fileCount?: number;
  description?: string;
}
```

## 금지
- 파일 삭제/이동 버튼 노출
- 서버 쓰기 작업 트리거
