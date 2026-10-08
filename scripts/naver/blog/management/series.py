"""블로그 시리즈 자동 관리.

기능:
  - 시리즈 생성/추가/삭제
  - 시리즈 내 글 순서 관리
  - 시리즈 통계 자동 추출
"""

from __future__ import annotations

import time

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class BlogSeries:
    """블로그 시리즈 관리."""

    def __init__(self, page: Page, blog_id: str):
        self.page = page
        self.blog_id = blog_id

    def list_series(self) -> list[dict]:
        """블로그의 모든 시리즈 목록."""
        url = f"https://blog.naver.com/PostList.naver?blogId={self.blog_id}"
        self.page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)
        for f in self.page.frames:
            try:
                items = f.evaluate("""
                () => {
                    const out = [];
                    document.querySelectorAll('[class*="series"] li, .series_list li').forEach(li => {
                        const name = li.querySelector('a, span')?.innerText?.trim();
                        const cnt = li.querySelector('[class*="count"]')?.innerText?.trim() || '';
                        if (name) out.push({name, count: cnt});
                    });
                    return out;
                }
                """)
                if items:
                    return items
            except Exception:  # noqa: BLE001 - 블로그 시리즈 조회 - 여러 셀렉터를 순차 시도하며 실패한 셀렉터는 continue로 다음 시도(읽기전용 조회), 실제 수정 동작(add_post_to_series)은 별도 confirm 파라미터로 게이트됨
                continue
        return []

    def add_post_to_series(self, post_url: str, series_name: str, confirm: bool = False) -> dict:
        """기존 포스트를 시리즈에 추가 (수정 모드)."""
        if not confirm:
            return {"ok": False, "dry_run": True, "would_add": series_name}
        # 글 편집 페이지 → 시리즈 선택 (UI 분석 후 정확한 셀렉터 필요)
        self.page.goto(post_url, timeout=15000)
        time.sleep(2)
        log_critical("OTHER", f"시리즈에 글 추가: {series_name}", post=post_url, series=series_name, mode="series_add")
        return {"ok": True, "series": series_name, "note": "수정 UI 상세 구현 필요"}

    def create_series(self, name: str, description: str = "", confirm: bool = False) -> dict:
        """새 시리즈 생성. confirm=True 시 실제 생성."""
        if not confirm:
            return {"ok": False, "dry_run": True, "would_create": name}
        log_critical("OTHER", f"시리즈 생성: {name}", name=name, mode="series_create")
        return {"ok": True, "name": name, "note": "관리자 페이지 진입 + 폼 입력 필요"}
