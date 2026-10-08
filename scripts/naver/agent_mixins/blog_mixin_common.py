"""blog_mixin 공통 헬퍼 + 공유 leaf.

서브믹스인들이 공유하는 _js 로더와, 프레임/내 블로그 탐지 기본 능력(BlogCommonMixin).
메서드 간 호출은 인스턴스(self)/MRO 로 해결된다. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any


def _js(name: str) -> str:
    from scripts.common.browser_js_dir import JS_DIR

    return (JS_DIR / name).read_text(encoding="utf-8")


class BlogCommonMixin:
    """블로그 프레임 헬퍼 + 내 블로그 URL 탐지 (공유 기본 능력)."""

    if TYPE_CHECKING:
        # 다른 믹스인의 메서드를 self(MRO)로 호출한다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    # ── 프레임 헬퍼 ────────────────────────────────────────────────────────────

    def _blog_frame(self):
        """블로그 본문 iframe(mainFrame) 반환.

        blog.naver.com/ID/logNo 는 name='mainFrame' iframe 내부 렌더링.
        PostWriteForm.naver 등 iframe 미사용 페이지는 self._page 반환.

        실검증(2026-06-23): PostView.naver 는 mainFrame iframe 사용 확인.
        셀렉터 상수: scripts.naver.blog.page_selectors.MAINFRAME_NAME
        """
        fr = self._page.frame(name="mainFrame")
        return fr if fr else self._page

    def _get_blog_post_frame(self, blog_id: str):
        """PostList 프레임 반환 (실제 블로그 콘텐츠)."""
        return next(
            (f for f in self._page.frames if "PostList" in (f.url or "") and blog_id in (f.url or "")),
            None,
        )

    def _get_blog_widget_frame(self, blog_id: str):
        """WidgetView 프레임 반환 (이웃수 등)."""
        return next(
            (f for f in self._page.frames if "WidgetView" in (f.url or "") and blog_id in (f.url or "")),
            None,
        )

    # ── 내 블로그 URL 자동 탐지 ─────────────────────────────────────────────────

    def my_blog_url(self) -> str:
        """로그인된 사용자의 블로그 URL 자동 탐지.

        blog.naver.com/MyBlog.naver 리다이렉트 → 실제 블로그 URL 추출.
        로그인 안 된 경우 빈 문자열 반환.
        """
        result = self.go("https://blog.naver.com/MyBlog.naver", wait=3.0)
        if not result.ok:
            return ""

        current_url = self._page.url
        # 리다이렉트 후 blog.naver.com/{blog_id} 형태가 되면 성공
        m = re.search(r"blog\.naver\.com/([^/?#]+)", current_url)
        if m:
            blog_id = m.group(1)
            # 시스템 경로 제외 (MyBlog, PostList 등)
            skip = {"MyBlog.naver", "PostList.naver", "BlogHome.naver", "home", "market", "PostView.naver"}
            if blog_id not in skip and not blog_id.endswith(".naver"):
                return f"https://blog.naver.com/{blog_id}"

        # 폴백: 페이지 내 "내 블로그" 링크 탐색
        try:
            links = self.extract_links(filter_href="blog.naver.com/")
            for link in links:
                href = link.get("href", "")
                text = link.get("text", "")
                if "내 블로그" in text or "내블로그" in text:
                    m2 = re.search(r"blog\.naver\.com/([^/?#]+)", href)
                    if m2 and not m2.group(1).endswith(".naver"):
                        return f"https://blog.naver.com/{m2.group(1)}"
        except Exception:  # noqa: S110, BLE001
            pass

        return ""
