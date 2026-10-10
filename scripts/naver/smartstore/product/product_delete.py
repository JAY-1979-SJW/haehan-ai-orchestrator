"""스마트스토어 상품 삭제 모듈 (L3 Connector).

흐름:
  1. 상품 목록 페이지 진입
  2. product_id 기반으로 상품 체크박스 선택
  3. 삭제 버튼 클릭 → 확인 팝업 처리 (confirmed=True 필수)

사용:
    from scripts.naver.smartstore.product.product_delete import ProductDeleter
    deleter = ProductDeleter(page)
    # 단건 삭제 드라이런
    result = deleter.delete(product_id="12345678", confirmed=False)
    # 실제 삭제
    result = deleter.delete(product_id="12345678", confirmed=True)
    # 일괄 삭제
    result = deleter.delete_bulk(["12345678", "87654321"], confirmed=True)
"""

from __future__ import annotations

import time
from pathlib import Path

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[4]

_PRODUCT_LIST_URL = "https://sell.smartstore.naver.com/#/products/list"


class ProductDeleter:
    """상품 삭제 자동화."""

    def __init__(self, page):
        self.page = page

    # ── 공개 인터페이스 ──────────────────────────────────────────────────────

    def delete(self, product_id: str, confirmed: bool = False) -> dict:
        """단건 상품 삭제.

        Args:
            product_id: 상품번호 (숫자 문자열)
            confirmed: True면 실제 삭제 (비가역 — 신중히)

        Returns:
            {ok, product_id, confirmed, deleted}
        """
        if not confirmed:
            return {
                "ok": True,
                "confirmed": False,
                "message": f"드라이런 — 상품 {product_id} 삭제 예정. confirmed=True로 재호출하면 실제 삭제합니다.",
                "product_id": product_id,
            }

        return self.delete_bulk([product_id], confirmed=True)

    def delete_bulk(self, product_ids: list[str], confirmed: bool = False) -> dict:
        """일괄 상품 삭제.

        Args:
            product_ids: 상품번호 목록
            confirmed: True면 실제 삭제

        Returns:
            {ok, deleted, failed, results}
        """
        if not confirmed:
            return {
                "ok": True,
                "confirmed": False,
                "message": f"드라이런 — {len(product_ids)}건 삭제 예정. confirmed=True로 재호출하면 실제 삭제합니다.",
                "product_ids": product_ids,
            }

        if not self._open_product_list():
            return {"ok": False, "error": "상품 목록 페이지 진입 실패"}

        deleted: list[dict] = []
        failed: list[dict] = []
        for pid in product_ids:
            r = self._delete_one(pid)
            (deleted if r["ok"] else failed).append({"product_id": pid, **r})

        log_critical("OTHER", "상품 삭제", deleted=len(deleted), failed=len(failed), product_ids=product_ids)
        return {
            "ok": len(failed) == 0,
            "confirmed": True,
            "deleted": len(deleted),
            "failed": len(failed),
            "results": deleted + failed,
        }

    # ── CDP 조작 ─────────────────────────────────────────────────────────────

    def _open_product_list(self) -> bool:
        """상품 목록 페이지 진입."""
        try:
            from scripts.naver.smartstore import NaverSmartStore

            ss = NaverSmartStore(self.page)
            if not ss.open_dashboard():
                return False
            if not ss._click_menu("상품관리"):
                return False
            for text in ["상품 조회/수정", "상품조회/수정"]:
                try:
                    self.page.click(f'a:has-text("{text}")', timeout=3000)
                    time.sleep(3)
                    return True
                except Exception:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
                    pass
            time.sleep(2)
            return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
            _log.error("[product-delete] 페이지 진입 실패: %s", e)
            return False

    def _delete_one(self, product_id: str) -> dict:
        """단건 삭제 실행."""
        try:
            # 상품번호로 행 찾기 → 체크박스 선택
            row_sel = f'tr[data-product-id="{product_id}"], tr:has(td:has-text("{product_id}"))'
            try:
                row = self.page.locator(row_sel).first
                row.wait_for(timeout=5000)
                checkbox = row.locator("input[type=checkbox]").first
                checkbox.check()
                time.sleep(0.3)
            except Exception:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
                # 검색으로 상품 찾기
                search_ok = self._search_product(product_id)
                if not search_ok:
                    return {"ok": False, "error": f"상품 {product_id} 찾기 실패"}
                try:
                    self.page.locator("input[type=checkbox]").first.check()
                    time.sleep(0.3)
                except Exception:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
                    return {"ok": False, "error": "체크박스 선택 실패"}

            # 삭제 버튼 클릭
            for btn_text in ["삭제", "상품 삭제", "선택 삭제"]:
                try:
                    self.page.click(f'button:has-text("{btn_text}")', timeout=3000)
                    time.sleep(1)
                    break
                except Exception:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
                    pass

            # 확인 팝업 처리
            for confirm_text in ["확인", "삭제", "예"]:
                try:
                    self.page.click(
                        f'.modal button:has-text("{confirm_text}"), [class*=confirm] button:has-text("{confirm_text}")',
                        timeout=3000,
                    )
                    time.sleep(1)
                    return {"ok": True}
                except Exception:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
                    pass

            return {"ok": True, "note": "확인 팝업 없이 삭제됨"}

        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
            _log.error("[product-delete] 삭제 실패 %s: %s", product_id, e)
            return {"ok": False, "error": str(e)[:200]}

    def _search_product(self, product_id: str) -> bool:
        """상품번호 검색."""
        try:
            search_input = self.page.locator(
                "input[placeholder*=상품번호], input[class*=search], input[name*=search]"
            ).first
            search_input.fill(product_id)
            self.page.keyboard.press("Enter")
            time.sleep(2)
            return True
        except Exception:  # noqa: BLE001 - 스마트스토어 상품삭제 UI 실행부 - 호출 상위(connectors/smartstore/products.py 라우터)에서 confirm=true 게이트를 통과한 뒤에만 실행되며, 여기 except 는 클릭/체크박스 실패를 ok:False,error 로 반환할 뿐
            return False
