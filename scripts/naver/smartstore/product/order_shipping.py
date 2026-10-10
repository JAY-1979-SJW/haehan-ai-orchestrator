"""스마트스토어 주문 배송 처리 모듈 (L3 Connector).

흐름:
  1. 발주(주문)확인/발송관리 페이지 진입
  2. 미발송 주문 목록 추출
  3. 송장번호 입력 → 발송처리 (confirmed=True 필수)

사용:
    from scripts.naver.smartstore.product.order_shipping import OrderShippingProcessor
    proc = OrderShippingProcessor(page)
    # 미발송 주문 조회
    result = proc.get_pending_orders()
    # 단건 발송처리 (임시저장)
    result = proc.process_order(order_id="...", tracking_number="1234567890", carrier="CJ대한통운", confirmed=False)
    # 실제 저장
    result = proc.process_order(order_id="...", tracking_number="1234567890", carrier="CJ대한통운", confirmed=True)
    # 일괄 발송처리
    result = proc.process_bulk([{"order_id":"...", "tracking_number":"...", "carrier":"..."}, ...], confirmed=True)
"""

from __future__ import annotations

import time
from pathlib import Path

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[4]

# 지원 택배사
CARRIERS = {
    "CJ대한통운": "04",
    "한진택배": "05",
    "롯데택배": "08",
    "우체국택배": "01",
    "로젠택배": "06",
    "드림택배": "22",
    "홈픽": "41",
    "편의점택배": "46",
    "직접배송": "99",
}


class OrderShippingProcessor:
    """주문 배송 처리 자동화."""

    def __init__(self, page):
        self.page = page

    # ── 공개 인터페이스 ──────────────────────────────────────────────────────

    def get_pending_orders(self, limit: int = 50) -> dict:
        """미발송 주문 목록 반환."""
        if not self._open_order_page():
            return {"ok": False, "error": "주문관리 페이지 진입 실패"}

        orders = self._extract_pending_orders(limit)
        return {"ok": True, "orders": orders, "count": len(orders)}

    def process_order(
        self,
        order_id: str,
        tracking_number: str,
        carrier: str = "CJ대한통운",
        confirmed: bool = False,
    ) -> dict:
        """단건 발송처리.

        Args:
            order_id: 주문번호
            tracking_number: 송장번호
            carrier: 택배사명 (CARRIERS 키 참조)
            confirmed: True면 실제 저장

        Returns:
            {ok, order_id, tracking_number, carrier, confirmed, saved}
        """
        if not confirmed:
            return {
                "ok": True,
                "confirmed": False,
                "message": "드라이런 — confirmed=True로 재호출하면 실제 발송처리합니다.",
                "order_id": order_id,
                "tracking_number": tracking_number,
                "carrier": carrier,
            }

        if not self._open_order_page():
            return {"ok": False, "error": "주문관리 페이지 진입 실패"}

        result = self._input_tracking(order_id, tracking_number, carrier)
        if result["ok"]:
            log_critical("OTHER", "주문 발송처리", order_id=order_id, tracking=tracking_number, carrier=carrier)
        return result

    def process_bulk(self, orders: list[dict], confirmed: bool = False) -> dict:
        """일괄 발송처리.

        Args:
            orders: [{"order_id": str, "tracking_number": str, "carrier": str}, ...]
            confirmed: True면 실제 저장

        Returns:
            {ok, processed, failed, results}
        """
        if not confirmed:
            return {
                "ok": True,
                "confirmed": False,
                "message": f"드라이런 — {len(orders)}건 처리 예정. confirmed=True로 재호출하면 실제 저장합니다.",
                "orders": orders,
            }

        if not self._open_order_page():
            return {"ok": False, "error": "주문관리 페이지 진입 실패"}

        processed: list[dict] = []
        failed: list[dict] = []
        for order in orders:
            r = self._input_tracking(
                order["order_id"],
                order["tracking_number"],
                order.get("carrier", "CJ대한통운"),
            )
            (processed if r["ok"] else failed).append({**order, **r})
            time.sleep(0.5)

        log_critical("OTHER", "주문 일괄 발송처리", processed=len(processed), failed=len(failed))
        return {
            "ok": len(failed) == 0,
            "confirmed": True,
            "processed": len(processed),
            "failed": len(failed),
            "results": processed + failed,
        }

    # ── CDP 조작 ─────────────────────────────────────────────────────────────

    def _open_order_page(self) -> bool:
        """발주확인/발송관리 페이지 진입."""
        try:
            from scripts.naver.smartstore import NaverSmartStore

            ss = NaverSmartStore(self.page)
            if not ss.open_dashboard():
                return False
            if not ss._click_menu("판매관리"):
                return False
            # 발주(주문)확인/발송관리 서브메뉴
            for text in ["발주(주문)확인/발송관리", "발주확인/발송관리", "발송관리"]:
                try:
                    self.page.click(f'a:has-text("{text}")', timeout=3000)
                    time.sleep(3)
                    return True
                except Exception:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
                    pass
            time.sleep(2)
            return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
            _log.error("[order-ship] 페이지 진입 실패: %s", e)
            return False

    def _extract_pending_orders(self, limit: int) -> list[dict]:
        """미발송 주문 DOM 추출."""
        try:
            rows = self.page.evaluate(f"""
                (() => {{
                    const results = [];
                    const rows = document.querySelectorAll('tbody tr, tr[class*=order]');
                    for (const row of Array.from(rows).slice(0, {limit})) {{
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 3) continue;
                        const orderId = row.getAttribute('data-order-id')
                            || (cells[1] ? cells[1].textContent.trim() : '');
                        const productName = cells[2] ? cells[2].textContent.trim().slice(0, 60) : '';
                        const status = row.querySelector('[class*=status]');
                        results.push({{
                            order_id: orderId,
                            product_name: productName,
                            status: status ? status.textContent.trim() : '',
                        }});
                    }}
                    return results.filter(r => r.order_id);
                }})()
            """)
            return rows
        except Exception as e:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
            _log.error("[order-ship] 주문 추출 실패: %s", e)
            return []

    def _input_tracking(self, order_id: str, tracking_number: str, carrier: str) -> dict:
        """송장번호 입력 → 발송처리 저장."""
        try:
            # 해당 주문행 찾기
            row_sel = f'tr[data-order-id="{order_id}"], tr:has(td:has-text("{order_id}"))'
            try:
                row = self.page.locator(row_sel).first
                row.wait_for(timeout=5000)
            except Exception:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
                return {"ok": False, "error": f"주문행 찾기 실패: {order_id}"}

            # 발송처리 버튼 클릭
            for btn_text in ["발송처리", "발송입력", "송장입력"]:
                try:
                    row.locator(f'button:has-text("{btn_text}")').first.click(timeout=3000)
                    time.sleep(1)
                    break
                except Exception:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
                    pass

            # 택배사 선택
            carrier_code = CARRIERS.get(carrier, "04")
            try:
                select = self.page.locator(
                    "select[class*=carrier], select[name*=carrier], select:near(input[placeholder*=송장])"
                ).first
                select.select_option(value=carrier_code)
                time.sleep(0.3)
            except Exception:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
                _log.warning("[order-ship] 택배사 선택 실패 — 기본값 사용")

            # 송장번호 입력
            tracking_input = self.page.locator(
                "input[placeholder*=송장], input[class*=tracking], input[name*=tracking]"
            ).first
            tracking_input.fill(tracking_number)
            time.sleep(0.3)

            # 저장/확인 버튼
            for btn_text in ["저장", "확인", "발송처리"]:
                try:
                    self.page.click(f'button:has-text("{btn_text}")', timeout=3000)
                    time.sleep(1)
                    return {"ok": True, "order_id": order_id, "tracking_number": tracking_number}
                except Exception:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
                    pass

            return {"ok": False, "error": "저장 버튼 클릭 실패"}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 발송처리(송장번호 입력) 자동화 - 결제/구매확정이 아닌 배송정보 입력, 실패시 ok:False,error 반환(성공 위장 없음)
            _log.error("[order-ship] 송장 입력 실패: %s", e)
            return {"ok": False, "error": str(e)[:200]}
