# Status Page 패턴

## 용도
게이트/공정/운영 상태 목록. PASS/WARN/FAIL 집계 뷰.

## 구성 요소
- PageContainer(variant=default)
- GateStatusCard × N
- StatusBadge
- Alert (FAIL 시 상단 경고)

## 레이아웃
- 카드 목록: 1열 또는 2열
- 각 카드: gateName + decision + count + reason

## 상태 배지 기준
- count=0 → PASS
- count>0 WARN → WARN
- count>0 FAIL → FAIL, Alert(type=error) 상단 표시

## 금지
- FAIL 항목 자동 수정 버튼 직접 노출
- secret/env 값 노출
