"""스마트스토어 주문 자동 처리.

자동화 범위:
  - 주문 목록 자동 조회
  - 발송 처리 (운송장 등록)
  - 구매확정 대기 모니터링
  - 취소/반품 자동 알림
  - CS 응답 템플릿
"""

from __future__ import annotations

import time

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class OrderAutomation:
    """주문/배송/취소/반품 자동 처리."""

    def __init__(self, page: Page):
        self.page = page
        from scripts.naver.smartstore import NaverSmartStore

        self.store = NaverSmartStore(page)

    # ── 신규 주문 자동 조회 ──────────────────────────────────────────────

    def fetch_new_orders(self, limit: int = 50) -> dict:
        """미발송 신규 주문 조회."""
        r = self.store.list_orders(limit=limit)
        if not r.get("ok"):
            return r
        # 발송대기 상태만 필터링 (테이블 헤더에서 상태 컬럼 찾기)
        headers = r.get("headers", [])
        rows = r.get("rows", [])
        status_idx = next((i for i, h in enumerate(headers) if "상태" in h or "처리" in h), None)
        if status_idx is None:
            return {"ok": True, "all_rows": rows, "new_count": None}
        new_orders = [
            row for row in rows if status_idx < len(row) and ("발송" in row[status_idx] or "신규" in row[status_idx])
        ]
        log_critical(
            "OTHER", f"신규 주문 조회: {len(new_orders)}건", total=len(rows), new=len(new_orders), mode="order_fetch"
        )
        return {
            "ok": True,
            "total": len(rows),
            "new_count": len(new_orders),
            "new_orders": new_orders,
            "headers": headers,
        }

    # ── 발송 처리 (운송장 등록) ──────────────────────────────────────────

    def register_tracking(self, order_id: str, courier: str, tracking_no: str, confirm: bool = False) -> dict:
        """운송장 번호 등록 (★ confirm=True 시에만 실제 등록)."""
        if not confirm:
            return {
                "ok": False,
                "dry_run": True,
                "reason": "confirm=False (안전)",
                "would_register": {"order": order_id, "courier": courier, "no": tracking_no},
            }

        # 발송 관리 페이지로
        if not self.store._ensure_section("orders"):
            return {"ok": False, "error": "section_open_failed"}

        try:
            # 주문 검색
            search = self.page.locator('input[placeholder*="주문"]').first
            search.fill(order_id, timeout=3000, force=True)
            self.page.keyboard.press("Enter")
            time.sleep(2)

            # 운송장 입력 (UI 분석 후 정확한 셀렉터 필요)
            tracking_input = self.page.locator('input[name*="tracking"], input[placeholder*="운송장"]').first
            tracking_input.fill(tracking_no, timeout=3000, force=True)
            time.sleep(0.5)

            # 택배사 선택
            courier_sel = self.page.locator('select[name*="courier"], select[placeholder*="택배"]').first
            courier_sel.select_option(label=courier, timeout=3000)
            time.sleep(0.5)

            # 등록 버튼
            self.page.locator('button:has-text("등록"), button:has-text("발송")').first.click(timeout=3000, force=True)
            time.sleep(3)

            log_critical(
                "OTHER",
                f"운송장 등록: {order_id}",
                order_id=order_id,
                courier=courier,
                tracking_no=tracking_no,
                mode="tracking_register",
            )
            return {"ok": True, "order_id": order_id, "tracking_no": tracking_no}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 운송장 등록 자동화(register_tracking) - confirm=True 명시 인자가 없으면 dry_run만 수행하고 실제 등록을 시도하지 않으며, confirm=True로 실제 등록 시도 시 실패하면 ok:False 반환(fail-closed), 구매확정/결제 등은 다루지 않음
            return {"ok": False, "error": str(e)[:80]}

    # ── 일괄 발송 처리 ───────────────────────────────────────────────────

    def bulk_register_tracking(self, items: list[dict], confirm: bool = False) -> dict:
        """일괄 운송장 등록.

        items: [{"order_id": "...", "courier": "CJ대한통운", "tracking_no": "1234..."}, ...]
        """
        results = []
        for item in items:
            r = self.register_tracking(
                item["order_id"],
                item.get("courier", ""),
                item["tracking_no"],
                confirm=confirm,
            )
            results.append({"order_id": item["order_id"], **r})
            time.sleep(1.5)
        ok = sum(1 for r in results if r.get("ok"))
        return {"ok": ok == len(items), "total": len(items), "success": ok, "results": results}

    # ── 취소/반품 모니터링 ───────────────────────────────────────────────

    def monitor_cancellations(self) -> dict:
        """취소/반품 요청 모니터링."""
        # 취소 관리 페이지
        # scripts.naver.smartstore.bulk 는 product/bulk.py 로 옮겨진 뒤 남은 `import *` shim
        # 이라 __all__ 없이는 밑줄시작 이름(_init_db)을 재노출 못 함(2026-09-29 defect_index
        # #39, #32/#38 과 동일한 패턴) — 실제 모듈에서 바로 가져온다.
        from scripts.naver.smartstore.product.bulk import _init_db

        _init_db()  # DB 활성화 (필요시)
        # 추후 구현: 취소 요청 자동 알림 / DB 기록
        return {"ok": True, "note": "취소 관리 페이지 진입 + 추출 로직 보강 예정"}
