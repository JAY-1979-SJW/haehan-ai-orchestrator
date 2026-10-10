"""네이버 페이 자동화 — 결제 내역 / 포인트 / 마이비즈.

URL: https://pay.naver.com/
주의: 실제 결제는 자동화 금지. 조회만.
"""

from __future__ import annotations

import contextlib
import time

from playwright.sync_api import Page

from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login
from scripts.browser.popup.popup_detector import handle_page_popups

_log = get_logger(__name__)


class NaverPay:
    def __init__(self, page: Page):
        self.page = page

    def open_home(self) -> bool:
        result = ensure_naver_login(self.page)
        if not result.get("ok"):
            return False
        self.page.goto("https://pay.naver.com/", timeout=20000, wait_until="domcontentloaded")
        time.sleep(3)
        # 네이버페이 — 문서에 '실제 결제는 자동화 금지. 조회만.' 이라고 명시된 조회전용 모듈, 팝업처리 실패는 무시(결제 동작 없음)
        with contextlib.suppress(Exception):
            handle_page_popups(self.page, timeout_s=1.5)
        return True

    def list_orders(self, limit: int = 30) -> list[dict]:
        """결제 내역 조회 (자동 결제 금지 — 조회 전용)."""
        result = ensure_naver_login(self.page)
        if not result.get("ok"):
            return []
        self.page.goto("https://order.pay.naver.com/home", timeout=20000, wait_until="domcontentloaded")
        time.sleep(3)
        # 네이버페이 — 문서에 '실제 결제는 자동화 금지. 조회만.' 이라고 명시된 조회전용 모듈, 팝업처리 실패는 무시(결제 동작 없음)
        with contextlib.suppress(Exception):
            handle_page_popups(self.page, timeout_s=1.5)

        try:
            orders = self.page.evaluate(
                """
            (limit) => {
                const out = [];
                document.querySelectorAll('[class*="order-item"], [class*="OrderItem"], .order-list li, .item-row').forEach((el, i) => {
                    if (i >= limit) return;
                    const merchant = el.querySelector('.merchant, .seller, [class*="store"]')?.innerText?.trim() || '';
                    const product = el.querySelector('.product, .item-name, [class*="product"]')?.innerText?.trim() || '';
                    const amount = el.querySelector('.amount, .price, [class*="price"]')?.innerText?.trim() || '';
                    const date = el.querySelector('.date, .order-date, [class*="date"]')?.innerText?.trim() || '';
                    const status = el.querySelector('.status, [class*="status"]')?.innerText?.trim() || '';
                    if (merchant || product) out.push({merchant, product, amount, date, status});
                });
                return out;
            }
            """,
                limit,
            )
            _log.info("[naver-pay] 결제 내역 %d건", len(orders))
            return orders
        except Exception as e:  # noqa: BLE001 - 네이버페이 — 문서에 '실제 결제는 자동화 금지. 조회만.' 이라고 명시된 조회전용 모듈, except는 팝업처리 무시 및 조회 실패 시 로그와 빈 결과 반환뿐 결제 동작 없음.
            _log.error("[naver-pay] list_orders 실패: %s", e)
            return []

    def points(self) -> dict:
        """포인트 잔액 / 적립 내역."""
        if not self.open_home():
            return {}
        try:
            info = self.page.evaluate("""
            () => {
                const txt = document.body?.innerText || '';
                const points = /포인트[\\s:]*([\\d,]+)\\s*P/.exec(txt)?.[1]?.replace(/,/g, '') || '';
                const cash = /네이버페이?\\s*머니[\\s:]*([\\d,]+)/.exec(txt)?.[1]?.replace(/,/g, '') || '';
                return {points: points ? parseInt(points) : null,
                        cash: cash ? parseInt(cash) : null};
            }
            """)
            return info
        except Exception as e:  # noqa: BLE001 - 네이버페이 — 문서에 '실제 결제는 자동화 금지. 조회만.' 이라고 명시된 조회전용 모듈, except는 팝업처리 무시 및 조회 실패 시 로그와 빈 결과 반환뿐 결제 동작 없음.
            _log.error("[naver-pay] points 실패: %s", e)
            return {}
