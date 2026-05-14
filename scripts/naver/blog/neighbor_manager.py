"""블로그 이웃 자동 관리.

기능:
  - 이웃 목록 자동 추출
  - 활동 빈도별 분류 (활성/휴면)
  - 휴면 이웃 자동 정리 제안
  - 추천 이웃 자동 추가 (★ confirm 필수)
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from playwright.sync_api import Page

from scripts.logger import get_logger
from scripts.critical_logger import log_critical

_log = get_logger(__name__)


class BlogNeighborManager:
    """이웃 자동 관리."""

    # 검증된 어드민 URL (admin.blog.naver.com)
    URL_MY_BUDDIES = "https://admin.blog.naver.com/BuddyListManage.naver"
    URL_THEY_ADDED_ME = "https://admin.blog.naver.com/BuddyMeManage.naver"
    URL_MUTUAL_REQUEST = "https://admin.blog.naver.com/BuddyInviteReceivedManage.naver"

    def __init__(self, page: Page, blog_id: str):
        self.page = page
        self.blog_id = blog_id

    def list_neighbors(self, limit: int = 100, source: str = "my") -> list[dict]:
        """이웃 목록 — 메인 프레임 + iframe 모두 검색.

        Args:
            source: 'my' (내가 추가) | 'they' (나를 추가) | 'mutual_request' (서로이웃 신청)
        """
        url_map = {
            "my": self.URL_MY_BUDDIES,
            "they": self.URL_THEY_ADDED_ME,
            "mutual_request": self.URL_MUTUAL_REQUEST,
        }
        url = url_map.get(source, self.URL_MY_BUDDIES)
        self.page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(3)

        # 메인 프레임 + iframe 순회
        extract_js = """
        (limit) => {
            const out = [];
            // 다양한 셀렉터 시도
            const sels = [
                '.buddy_list li', '[class*="neighbor"] li', 'table tbody tr',
                '[class*="Buddy"] li', '.list_item li', 'ul.list li',
                '.lst_thmb_buddy li', '.lst_buddy li',
            ];
            for (const sel of sels) {
                const items = document.querySelectorAll(sel);
                if (items.length < 2) continue;
                items.forEach((el, i) => {
                    if (i >= limit) return;
                    const nick = el.querySelector('.nick_name, [class*="nick"], .name, .author')?.innerText?.trim()
                                  || (el.querySelector('a')?.innerText || '').trim();
                    let blogId = '';
                    const link = el.querySelector('a[href*="blog.naver.com/"]');
                    if (link) {
                        const m = link.href.match(/blog\\.naver\\.com\\/([^\\/\\?#]+)/);
                        if (m) blogId = m[1];
                    }
                    const mutual = !!el.querySelector('[class*="mutual"]') ||
                                   (el.innerText || '').includes('서로이웃');
                    const date = el.querySelector('[class*="date"], .date, .day')?.innerText?.trim() || '';
                    if (nick && nick.length < 50) {
                        out.push({nickname: nick.substring(0, 40),
                                  blog_id: blogId, is_mutual: mutual, date,
                                  selector: sel});
                    }
                });
                if (out.length > 0) break;
            }
            return out;
        }
        """
        # 메인 프레임 시도
        try:
            r = self.page.evaluate(extract_js, limit)
            if r:
                return r
        except Exception:
            pass

        # iframe 순회
        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            try:
                r = frame.evaluate(extract_js, limit)
                if r:
                    _log.info("[neighbor] iframe에서 발견: %s", frame.url[:60])
                    return r
            except Exception:
                continue

        _log.warning("[neighbor] 이웃 목록 미발견 — 페이지 구조 변경 가능")
        return []

    def classify_activity(self, days_threshold: int = 90) -> dict:
        """활동 빈도별 분류 — 활성 vs 휴면."""
        neighbors = self.list_neighbors()
        active = []
        dormant = []
        for n in neighbors:
            blog_id = n.get("blog_id")
            if not blog_id:
                continue
            # 최근 글 확인 (간단화: 블로그 메인 방문 → 최근 글 날짜 추출)
            try:
                self.page.goto(f"https://blog.naver.com/{blog_id}",
                               timeout=10000, wait_until="domcontentloaded")
                time.sleep(1.5)
                last_post_date = self.page.evaluate("""
                () => {
                    const dateEl = document.querySelector('[class*="se-publishDate"], .date, [class*="date"]');
                    return dateEl?.innerText?.trim() || null;
                }
                """)
                n["last_post"] = last_post_date
                # 단순 텍스트 분석
                if last_post_date and any(s in last_post_date for s in [str(datetime.now().year)]):
                    active.append(n)
                else:
                    dormant.append(n)
            except Exception:
                dormant.append(n)
            time.sleep(0.5)

        log_critical("OTHER", f"이웃 활동 분류: 활성 {len(active)}, 휴면 {len(dormant)}",
                     active=len(active), dormant=len(dormant), mode="neighbor_classify")
        return {"ok": True, "active": active, "dormant": dormant,
                "total": len(neighbors)}

    def add_neighbor(self, target_blog_id: str, mutual: bool = False,
                      confirm: bool = False) -> dict:
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
            log_critical("OTHER", f"이웃 추가: {target_blog_id}",
                         target=target_blog_id, mode="neighbor_add")
            return {"ok": True, "target": target_blog_id}
        except Exception as e:
            return {"ok": False, "error": str(e)[:80]}
