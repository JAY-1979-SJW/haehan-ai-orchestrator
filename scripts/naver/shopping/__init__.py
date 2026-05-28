"""네이버 쇼핑 통합 모듈.

모든 쇼핑 관련 작업은 이 패키지를 통해 접근한다.
게이트 없이 하위 모듈을 직접 호출하는 것은 금지.

사용:
    from scripts.naver.shopping import search_shopping, analyze_competitor, price_summary
    from scripts.naver.shopping.gate import gate_product_write, GateBlocked

읽기 (자동 허용):
    search_shopping("LED 무드등")
    analyze_competitor("인테리어 조명")
    price_summary("LED 무드등")

쓰기 (승인 필수):
    from scripts.naver.shopping.gate import gate_product_write
    gate_product_write("product.save", confirm="SMARTSTORE_APPROVED_SUBMIT")
"""
from __future__ import annotations

from .search import search_shopping
from .competitor import analyze_competitor, price_summary
from .analytics import dashboard_summary, inventory_status
from . import gate, policy

__all__ = [
    "search_shopping",
    "analyze_competitor",
    "price_summary",
    "dashboard_summary",
    "inventory_status",
    "gate",
    "policy",
]
