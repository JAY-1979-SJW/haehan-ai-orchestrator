# Approval Warehouse (W2)
경로: data/approvals/{domain}/{task_id}/
정책: APPROVAL_REQUIRED, 불변
역할: 승인 요청·기록·범위·만료
필수필드: approver/timestamp/scope/expiry/decision
금지: 임의 수정, session/cookie 승인 증거 사용
참조: docs/architecture/shared_warehouse_model.md#W2
