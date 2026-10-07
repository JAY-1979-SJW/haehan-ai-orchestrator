"""네이버 스마트플레이스 자동화 — 매장 관리 / 리뷰 / 예약.

URL: https://new.smartplace.naver.com/
"""

from __future__ import annotations

from playwright.sync_api import Page

from scripts.common.logger import get_logger
from scripts.naver.common.auth import open_logged_in_page

_log = get_logger(__name__)
PLACE_URL = "https://new.smartplace.naver.com/"


class NaverPlace:
    def __init__(self, page: Page):
        self.page = page

    def open(self) -> bool:
        return open_logged_in_page(self.page, PLACE_URL)

    def list_places(self) -> list[dict]:
        """내가 관리하는 매장 목록."""
        if not self.open():
            return []
        try:
            return self.page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('[class*="PlaceItem"], .place_item, .business-item').forEach(el => {
                    const name = el.querySelector('.name, .title')?.innerText?.trim() || '';
                    const cat = el.querySelector('.category, .type')?.innerText?.trim() || '';
                    const status = el.querySelector('.status')?.innerText?.trim() || '';
                    if (name) out.push({name, category: cat, status});
                });
                return out;
            }
            """)
        except Exception as e:  # noqa: BLE001 - 네이버 플레이스 목록/리뷰 읽기전용 조회 — 팝업처리 실패는 무시, 조회 실패는 에러 로그 남기고 빈 리스트 반환, 쓰기 없음
            _log.error("[naver-place] list 실패: %s", e)
            return []

    def reviews(self, limit: int = 30) -> list[dict]:
        """최근 리뷰."""
        if not self.open():
            return []
        try:
            return self.page.evaluate(
                """
            (limit) => {
                const out = [];
                document.querySelectorAll('[class*="Review"], .review_item').forEach((el, i) => {
                    if (i >= limit) return;
                    const author = el.querySelector('.author, .name')?.innerText?.trim() || '';
                    const content = el.querySelector('.content, .text')?.innerText?.trim().substring(0, 200) || '';
                    const rating = el.querySelector('.rating, .stars')?.innerText?.trim() || '';
                    const date = el.querySelector('.date')?.innerText?.trim() || '';
                    if (author || content) out.push({author, content, rating, date});
                });
                return out;
            }
            """,
                limit,
            )
        except Exception as e:  # noqa: BLE001 - 네이버 플레이스 목록/리뷰 읽기전용 조회 — 팝업처리 실패는 무시, 조회 실패는 에러 로그 남기고 빈 리스트 반환, 쓰기 없음
            _log.error("[naver-place] reviews 실패: %s", e)
            return []
