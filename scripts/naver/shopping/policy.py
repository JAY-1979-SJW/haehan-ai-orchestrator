"""쇼핑 모듈 정책 상수 — 변경 시 gate.py도 함께 수정."""
from __future__ import annotations

# 비로그인 검색 (OpenAPI) — 즉시 허용
SEARCH_RISK = "auto"
SEARCH_DAILY_LIMIT = 25_000

# 경쟁사 조사 (읽기 전용 수집) — 자동 허용, 로그 기록
COMPETITOR_RISK = "notify"

# 재고 조회 — 자동
INVENTORY_READ_RISK = "auto"

# 주문 조회 — 자동
ORDER_READ_RISK = "auto"

# 상품 등록/수정 — 승인 필수
PRODUCT_WRITE_RISK = "approve"
PRODUCT_WRITE_CONFIRM = "SMARTSTORE_APPROVED_SUBMIT"

# 주문 처리 (발송/취소) — 승인 필수
ORDER_WRITE_RISK = "approve"
ORDER_WRITE_CONFIRM = "SMARTSTORE_ORDER_APPROVED"

# 가격 변경 — 승인 필수
PRICE_CHANGE_RISK = "approve"
PRICE_CHANGE_CONFIRM = "SMARTSTORE_PRICE_APPROVED"

# 절대 차단
BLOCKED_ACTIONS = [
    "payment_method_register",
    "ad_campaign_create",
    "ad_budget_update",
    "paid_api_key_issue",
    "bulk_delete_products",
]
