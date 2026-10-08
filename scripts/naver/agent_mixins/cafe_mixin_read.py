"""cafe_mixin 카페/게시판/글 탐색 기능 (CafeReadMixin).

cafe_info/boards/posts/popular/search/new_posts + _get_club_id/_board_url.
CafeMixin 다중상속의 기본 읽기 능력. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from scripts.naver.agent_mixins.cafe_mixin_common import _js


class CafeReadMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def cafe_info(self, cafe_url: str) -> dict:
        """카페 기본 정보 반환.

        반환:
            name         - 카페명
            url          - 카페 URL
            club_id      - 클럽 ID (숫자 문자열)
            manager      - 운영자 닉네임
            opened_at    - 개설일 (예: '2004.04.12')
            grade        - 카페 등급 (예: '나무3단계')
            member_count - 멤버 수 (문자열, 예: '242,106')
            description  - 카페 소개
            boards       - 게시판 목록 (list[dict])
        """
        self.go(cafe_url)
        time.sleep(3)

        def _s(sel: str, timeout: int = 800) -> str:
            try:
                return self._page.locator(sel).first.inner_text(timeout=timeout).strip()
            except Exception:  # noqa: BLE001 - 네이버 카페 게시글 읽기 전용 파싱 mixin - 텍스트 추출/게시글 목록 수집 실패 시 빈 문자열 또는 continue로 스킵, 쓰기 없음
                return ""

        raw = self._page.inner_text("body")

        # 메인 프레임 사이드바에서 카페 정보 파싱
        name_m = re.search(r"^(.+?)\n", raw)
        name = name_m.group(1).strip() if name_m else ""

        manager_m = re.search(r"\n(.+?)\s*\n\s*매니저", raw)
        manager = manager_m.group(1).strip() if manager_m else ""

        opened_m = re.search(r"(\d{4}\.\d{2}\.\d{2})\.\s*개설", raw)
        opened_at = opened_m.group(1) if opened_m else ""

        grade_m = re.search(r"카페등급\s*\n(.+?)\n", raw)
        grade = grade_m.group(1).strip() if grade_m else ""

        member_m = re.search(r"카페멤버수\s*\n\s*([\d,]+)", raw)
        member_count = member_m.group(1).strip() if member_m else ""

        # 클럽 ID 추출
        club_id = ""
        for link in self.extract_links(filter_href="clubid="):
            m = re.search(r"clubid=(\d+)", link["href"])
            if m:
                club_id = m.group(1)
                break
        if not club_id:
            m = re.search(r"/cafes/(\d+)", cafe_url)
            if m:
                club_id = m.group(1)

        # 게시판 목록
        boards = self.cafe_boards(cafe_url, _skip_goto=True)

        return {
            "name": name,
            "url": cafe_url,
            "club_id": club_id,
            "manager": manager,
            "opened_at": opened_at,
            "grade": grade,
            "member_count": member_count,
            "description": "",
            "boards": boards,
        }

    def cafe_boards(self, cafe_url: str, _skip_goto: bool = False) -> list[dict]:
        """카페 게시판 목록 반환.

        반환: list[dict]
            name  - 게시판명
            href  - 게시판 URL
            count - 게시글 수 (문자열)
        """
        if not _skip_goto:
            self.go(cafe_url)
            time.sleep(3)

        links = self.extract_links()
        boards = []
        seen: set[str] = set()
        for l in links:  # noqa: E741
            href = l["href"]
            name = l["text"]
            is_board = "ArticleList" in href or "search.boardtype" in href
            if not is_board or href in seen or not name or len(name) < 2:
                continue
            seen.add(href)
            # href에서 menuid 추출
            mid_m = re.search(r"menuid=(\d+)", href)
            menu_id = mid_m.group(1) if mid_m else ""
            # clubid 추출
            cid_m = re.search(r"clubid=(\d+)", href)
            club_id = cid_m.group(1) if cid_m else ""
            boards.append(
                {
                    "name": name,
                    "href": href,
                    "menu_id": menu_id,
                    "club_id": club_id,
                    "count": "",
                }
            )
        return boards

    def _get_club_id(self, cafe_url: str) -> str:
        """카페 URL 또는 사이드바 링크에서 clubid 추출."""
        # URL 자체에서 추출
        m = re.search(r"clubid=(\d+)", cafe_url)
        if m:
            return m.group(1)
        m = re.search(r"/cafes/(\d+)", cafe_url)
        if m:
            return m.group(1)
        # 사이드바 링크에서 추출
        for l in self.extract_links(filter_href="ArticleList"):  # noqa: E741
            cm = re.search(r"clubid=(\d+)", l["href"])
            if cm:
                return cm.group(1)
        return ""

    def _board_url(self, cafe_url: str, board: str, page: int = 1) -> str:
        """게시판명/URL에서 ArticleList URL 생성."""
        if board.startswith("http"):
            url = board
            sep = "&" if "?" in url else "?"
            if page > 1:
                url += f"{sep}search.page={page}"
            return url
        # 사이드바에서 게시판명 링크 찾기
        for l in self.extract_links(filter_href="ArticleList"):  # noqa: E741
            if board in l["text"]:
                url = l["href"]
                sep = "&" if "?" in url else "?"
                if page > 1:
                    url += f"{sep}search.page={page}"
                return url
        # 전체글보기 기본
        club_id = self._get_club_id(cafe_url)
        base = f"https://cafe.naver.com/ArticleList.nhn?search.clubid={club_id}&search.boardtype=L"
        if page > 1:
            base += f"&search.page={page}"
        return base

    def cafe_posts(self, cafe_url: str, board: str = "전체글보기", page: int = 1, max_posts: int = 30) -> list[dict]:
        """카페 게시판 게시글 목록 (메타 포함, 페이지 지정 가능).

        Args:
            cafe_url  - 카페 URL (예: https://cafe.naver.com/0moo)
            board     - 게시판명 또는 게시판 URL (기본: 전체글보기)
            page      - 페이지 번호 (기본: 1)
            max_posts - 최대 수집 수

        반환: list[dict]
            title    - 게시글 제목
            href     - 게시글 URL
            author   - 작성자
            date     - 작성일
            views    - 조회수
            comments - 댓글 수
        """
        # 카페 홈으로 이동해 사이드바 링크 확보
        self.go(cafe_url)
        time.sleep(2)

        # 목표 게시판 URL 결정
        target_url = self._board_url(cafe_url, board, page)
        self.go(target_url)
        time.sleep(2)

        all_posts: list[dict] = []
        seen: set[str] = set()

        for frame in self._page.frames:
            try:
                posts = frame.evaluate(_js("extract_cafe_posts.js"))
                for p in posts:
                    href = p.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        all_posts.append(p)
            except Exception:  # noqa: BLE001, S112
                continue

        return all_posts[:max_posts]

    def cafe_posts_all_pages(self, cafe_url: str, board: str = "전체글보기", max_pages: int = 5) -> list[dict]:
        """여러 페이지에 걸쳐 게시글 목록 수집.

        Args:
            max_pages - 최대 페이지 수 (기본: 5)
        """
        self.go(cafe_url)
        time.sleep(2)
        if board != "전체글보기":
            self.click_text(board)
            time.sleep(2)

        all_posts: list[dict] = []
        seen: set[str] = set()

        for page_num in range(1, max_pages + 1):
            if page_num > 1:
                clicked = self._page.evaluate(f"""
() => {{
    for (const el of document.querySelectorAll('a.page_item, span.page_item, a[class*=page]')) {{
        if ((el.innerText || '').trim() === '{page_num}') {{
            el.click(); return true;
        }}
    }}
    return false;
}}""")
                if not clicked:
                    break
                time.sleep(2.5)

            for frame in self._page.frames:
                try:
                    posts = frame.evaluate(_js("extract_cafe_posts.js"))
                    for p in posts:
                        href = p.get("href", "")
                        if href and href not in seen:
                            seen.add(href)
                            all_posts.append(p)
                except Exception:  # noqa: BLE001, S112
                    continue

            if not all_posts and page_num == 1:
                break

        return all_posts

    def cafe_popular(self, cafe_url: str, max_posts: int = 30) -> list[dict]:
        """카페 인기글 목록 반환.

        Args:
            cafe_url - 카페 URL (예: https://cafe.naver.com/0moo)
        """
        # clubid 추출
        club_id = ""
        m = re.search(r"clubid=(\d+)", cafe_url)
        if m:
            club_id = m.group(1)
        if not club_id:
            # cafe slug → clubid 추출 (사이드바 링크에서)
            self.go(cafe_url)
            time.sleep(2)
            for l in self.extract_links(filter_href="ArticleList"):  # noqa: E741
                cm = re.search(r"clubid=(\d+)", l["href"])
                if cm:
                    club_id = cm.group(1)
                    break

        pop_url = f"https://cafe.naver.com/f-e/cafes/{club_id}/popular" if club_id else ""
        if not pop_url:
            return []

        self.go(pop_url)
        time.sleep(3)

        all_posts: list[dict] = []
        seen: set[str] = set()
        for frame in self._page.frames:
            try:
                posts = frame.evaluate(_js("extract_cafe_posts.js"))
                for p in posts:
                    href = p.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        all_posts.append(p)
            except Exception:  # noqa: BLE001, S112
                continue

        return all_posts[:max_posts]

    def _club_id_for_search(self, cafe_url: str) -> str:
        """clubid 추출 (URL에 없으면 카페 홈의 ArticleList 링크에서 탐색)."""
        club_id = ""
        m = re.search(r"clubid=(\d+)", cafe_url)
        if not m:
            self.go(cafe_url)
            time.sleep(2)
            for l in self.extract_links(filter_href="ArticleList"):  # noqa: E741
                cm = re.search(r"clubid=(\d+)", l["href"])
                if cm:
                    club_id = cm.group(1)
                    break
        else:
            club_id = m.group(1)
        return club_id

    def cafe_search(self, cafe_url: str, query: str, page: int = 1, max_posts: int = 30) -> list[dict]:
        """카페 내 키워드 검색.

        Args:
            cafe_url - 카페 URL
            query    - 검색어
            page     - 페이지 번호
        """
        import urllib.parse

        club_id = self._club_id_for_search(cafe_url)

        q = urllib.parse.quote(query)
        search_url = (
            f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/0?viewType=L&ta=ARTICLE_COMMENT&page={page}&q={q}"
        )
        self.go(search_url)
        time.sleep(3)

        all_posts: list[dict] = []
        seen: set[str] = set()
        for frame in self._page.frames:
            try:
                posts = frame.evaluate(_js("extract_cafe_posts.js"))
                for p in posts:
                    href = p.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        all_posts.append(p)
            except Exception:  # noqa: BLE001, S112
                continue

        # 폴백: 일반 extract_posts.js
        if not all_posts:
            for frame in self._page.frames:
                try:
                    posts = frame.evaluate(_js("extract_posts.js"))
                    for p in posts:
                        href = p.get("href", "")
                        if href and href not in seen:
                            seen.add(href)
                            all_posts.append(
                                {
                                    "title": p.get("title", ""),
                                    "href": href,
                                    "author": "",
                                    "date": "",
                                    "views": "",
                                    "comments": "",
                                }
                            )
                except Exception:  # noqa: BLE001, S112
                    continue

        return all_posts[:max_posts]

    def cafe_new_posts(self, cafe_url: str, max_posts: int = 30) -> list[dict]:
        """새 글 (최신 전체글) 목록 반환."""
        return self.cafe_posts(cafe_url, board="전체글보기", max_posts=max_posts)

    # ── 출석체크 ────────────────────────────────────────────────────────────────
