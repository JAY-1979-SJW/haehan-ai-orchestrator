# Approval Queue Page 패턴

## 용도
승인 대기 항목 목록 조회 및 처리.

## 구성 요소
- PageContainer(variant=default)
- ApprovalQueueList
- Alert (긴급 항목 있을 때)

## 데이터 구조
```ts
interface ApprovalQueueItem {
  id: string;
  title: string;
  status: StatusValue;
  requestedAt: string;
  requester: string;
  description?: string;
}
```

## 금지
- 자동 일괄 승인 버튼
- 사용자 확인 없이 DB write 트리거
