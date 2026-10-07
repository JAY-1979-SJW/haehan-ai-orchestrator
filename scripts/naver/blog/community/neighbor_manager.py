"""블로그 이웃 자동 관리.

기능:
  - 이웃 목록 자동 추출
  - 활동 빈도별 분류 (활성/휴면)
  - 휴면 이웃 자동 정리 제안
  - 추천 이웃 자동 추가 (★ confirm 필수)
"""

from __future__ import annotations

import re
import time
from typing import Any

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)

# admin.blog.naver.com 이웃목록 페이지는 iframe 없이 메인 문서에 직접 렌더링되고,
# 표는 탭/개행이 섞인 텍스트로 나온다(2026-08-18 실측 — stat/* 페이지와 같은 패턴).
# 한 행: "그룹\t관계\t\n닉네임|블로그타이틀\n\t\nON/OFF\n\t최근글\t이웃추가일"
_ROW_RE = re.compile(
    r"(\S+)\n\t(이웃|서로이웃|이웃\(RSS\))\t\n([^\n|]+)\|([^\n]+)\n\t\n(ON|OFF)\n\t([\d.\-]+)\t([\d.\-]+)"
)


class BlogNeighborManager:
    """이웃 자동 관리."""

    # 검증된 어드민 URL (admin.blog.naver.com)
    URL_MY_BUDDIES = "https://admin.blog.naver.com/BuddyListManage.naver"
    URL_THEY_ADDED_ME = "https://admin.blog.naver.com/BuddyMeManage.naver"
    URL_MUTUAL_REQUEST = "https://admin.blog.naver.com/BuddyInviteReceivedManage.naver"

    def __init__(self, page: Page, blog_id: str):
        self.page = page
        self.blog_id = blog_id

    def list_neighbors(self, limit: int = 500, source: str = "my") -> list[dict]:
        """이웃 목록 — 텍스트 파싱(탭/개행) + 페이지네이션(goPage) 순회.

        Args:
            source: 'my' (내가 추가) | 'they' (나를 추가) | 'mutual_request' (서로이웃 신청)
        """
        url_map = {
            "my": self.URL_MY_BUDDIES,
            "they": self.URL_THEY_ADDED_ME,
            "mutual_request": self.URL_MUTUAL_REQUEST,
        }
        url = f"{url_map.get(source, self.URL_MY_BUDDIES)}?blogId={self.blog_id}"
        self.page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2.5)

        results: list[dict] = []
        seen_keys: set[tuple[str, str]] = set()
        page_no = 1
        while len(results) < limit:
            text = self.page.inner_text("body")
            links = self.page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href*="blog.naver.com/"]'))
                       .map(a => (a.href.match(/blog\\.naver\\.com\\/([^\\/?#]+)/) || [])[1] || '')"""
            )
            rows = _ROW_RE.findall(text)
            for i, (group, relation, nick, title, onoff, last_post, added_at) in enumerate(rows):
                key = (nick.strip(), added_at)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                results.append(
                    {
                        "nickname": nick.strip()[:40],
                        "blog_title": title.strip()[:80],
                        "blog_id": links[i] if i < len(links) else "",
                        "group": group,
                        "is_mutual": relation == "서로이웃",
                        "new_post_alert": onoff == "ON",
                        "last_post": last_post,
                        "added_at": added_at,
                    }
                )
                if len(results) >= limit:
                    break

            page_no += 1
            has_next = self.page.evaluate(
                f"typeof goPage === 'function' && !!document.querySelector('a[href*=\"goPage({page_no})\"]')"
            )
            if not has_next or len(results) >= limit:
                break
            try:
                self.page.evaluate(f"goPage({page_no})")
                time.sleep(2)
            except Exception:  # noqa: BLE001 - 이웃목록 페이지네이션 종료 감지(break)로 안전 종료, 이웃추가 실패는 ok:False로 반환 — 성공 위장 없음
                break

        if not results:
            _log.warning("[neighbor] 이웃 목록 미발견 — 페이지 구조 변경 가능")
        return results

    def classify_activity(self, days_threshold: int = 90) -> dict:
        """활동 빈도별 분류 — 활성 vs 휴면.

        list_neighbors()가 이미 목록 페이지에서 "최근 글" 날짜를 함께 가져오므로
        (2026-08-18 재작성) 이웃마다 개별 블로그를 방문할 필요가 없어졌다 —
        107명 기준 기존 방식은 왕복 100회+로 몇 분씩 걸렸음.
        """
        from datetime import datetime

        neighbors = self.list_neighbors()
        active: list[Any] = []
        dormant: list[Any] = []
        now = datetime.now()
        for n in neighbors:
            last_post = n.get("last_post", "")
            is_active = False
            try:
                if last_post and last_post != "-":
                    dt = datetime.strptime(last_post.rstrip("."), "%y.%m.%d")
                    is_active = (now - dt).days <= days_threshold
            except ValueError:
                pass
            (active if is_active else dormant).append(n)

        log_critical(
            "OTHER",
            f"이웃 활동 분류: 활성 {len(active)}, 휴면 {len(dormant)}",
            active=len(active),
            dormant=len(dormant),
            mode="neighbor_classify",
        )
        return {"ok": True, "active": active, "dormant": dormant, "total": len(neighbors)}

    def add_neighbor(self, target_blog_id: str, mutual: bool = False, confirm: bool = False) -> dict:
        """이웃 추가 (★ confirm 필수)."""
        if not confirm:
            return {"ok": False, "dry_run": True, "would_add": target_blog_id}
        # UI 진입 + 이웃추가 클릭
        url = f"https://blog.naver.com/{target_blog_id}"
        self.page.goto(url, timeout=15000)
        time.sleep(2)
        try:
            btn = self.page.locator('button:has-text("이웃추가"), a:has-text("이웃추가")').first
            btn.click(timeout=3000)
            time.sleep(2)
            log_critical("OTHER", f"이웃 추가: {target_blog_id}", target=target_blog_id, mode="neighbor_add")
            return {"ok": True, "target": target_blog_id}
        except Exception as e:  # noqa: BLE001 - 이웃목록 페이지네이션 종료 감지(break)로 안전 종료, 이웃추가 실패는 ok:False로 반환 — 성공 위장 없음
            return {"ok": False, "error": str(e)[:80]}
