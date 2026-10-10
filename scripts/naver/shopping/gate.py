"""쇼핑 전용 게이트 — 모든 쇼핑 작업은 이 게이트를 통과해야 한다."""
from __future__ import annotations

from scripts.common.gate import check, GateBlocked, register
from scripts.common.schemas import RiskLevel
from . import policy

# 쇼핑 작업 위험 등급 사전 등록
register("shopping_search",         RiskLevel(policy.SEARCH_RISK))
register("shopping_competitor",     RiskLevel(policy.COMPETITOR_RISK))
register("shopping_dashboard_read", RiskLevel.AUTO)
register("shopping_inventory_read", RiskLevel.AUTO)
register("shopping_order_read",     RiskLevel.AUTO)
register("shopping_product_write",  RiskLevel(policy.PRODUCT_WRITE_RISK))
register("shopping_order_write",    RiskLevel(policy.ORDER_WRITE_RISK))
register("shopping_price_change",   RiskLevel(policy.PRICE_CHANGE_RISK))


def gate_search(query: str) -> None:
    """비로그인 검색 — AUTO."""
    check("shopping_search", risk=policy.SEARCH_RISK, query=query)


def gate_competitor(keyword: str) -> None:
    """경쟁사 조사 — NOTIFY (로그 기록)."""
    check("shopping_competitor", risk=policy.COMPETITOR_RISK, keyword=keyword)


def gate_product_write(action: str, *, confirm: str = "") -> None:
    """상품 등록/수정 — APPROVE 필수. confirm 토큰 없으면 차단."""
    if confirm != policy.PRODUCT_WRITE_CONFIRM:
        from scripts.common.schemas import GateResult, GateVerdict
        result = GateResult(
            verdict=GateVerdict.BLOCKED,
            risk=RiskLevel(policy.PRODUCT_WRITE_RISK),
            op_name="shopping_product_write",
            reason=(
                f"상품 쓰기 작업({action})은 승인 토큰 필요: "
                f"--confirm={policy.PRODUCT_WRITE_CONFIRM}"
            ),
            metadata={"action": action, "confirm": confirm},
        )
        raise GateBlocked(result)
    check("shopping_product_write", risk=policy.PRODUCT_WRITE_RISK,
          action=action, force=True)


def gate_order_write(action: str, *, confirm: str = "") -> None:
    """주문 처리 — APPROVE 필수."""
    if confirm != policy.ORDER_WRITE_CONFIRM:
        from scripts.common.schemas import GateResult, GateVerdict
        result = GateResult(
            verdict=GateVerdict.BLOCKED,
            risk=RiskLevel(policy.ORDER_WRITE_RISK),
            op_name="shopping_order_write",
            reason=(
                f"주문 처리({action})는 승인 토큰 필요: "
                f"--confirm={policy.ORDER_WRITE_CONFIRM}"
            ),
            metadata={"action": action, "confirm": confirm},
        )
        raise GateBlocked(result)
    check("shopping_order_write", risk=policy.ORDER_WRITE_RISK,
          action=action, force=True)


def gate_price_change(sku: str, new_price: int, *, confirm: str = "") -> None:
    """가격 변경 — APPROVE 필수."""
    if confirm != policy.PRICE_CHANGE_CONFIRM:
        from scripts.common.schemas import GateResult, GateVerdict
        result = GateResult(
            verdict=GateVerdict.BLOCKED,
            risk=RiskLevel(policy.PRICE_CHANGE_RISK),
            op_name="shopping_price_change",
            reason=(
                f"가격 변경({sku}: {new_price}원)은 승인 토큰 필요: "
                f"--confirm={policy.PRICE_CHANGE_CONFIRM}"
            ),
            metadata={"sku": sku, "new_price": new_price, "confirm": confirm},
        )
        raise GateBlocked(result)
    check("shopping_price_change", risk=policy.PRICE_CHANGE_RISK,
          sku=sku, new_price=new_price, force=True)


def assert_not_blocked(action: str) -> None:
    """절대 차단 목록 확인."""
    if action in policy.BLOCKED_ACTIONS:
        from scripts.common.schemas import GateResult, GateVerdict
        result = GateResult(
            verdict=GateVerdict.BLOCKED,
            risk=RiskLevel.BLOCK,
            op_name=f"shopping_blocked_{action}",
            reason=f"영구 차단 작업: {action}",
            metadata={"action": action},
        )
        raise GateBlocked(result)
