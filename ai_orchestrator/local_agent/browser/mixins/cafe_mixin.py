from __future__ import annotations
import re
import time
from pathlib import Path
from typing import Optional

from .cafe_mixin_media import CafeMediaMixin
from .cafe_mixin_article import CafeArticleMixin
from .cafe_mixin_common import _js  # noqa: F401

class CafeMixin(CafeMediaMixin, CafeArticleMixin):
    """네이버 카페 기능 Mixin."""
    # ── 카페 전체 탐색 기능 ───────────────────────────────────────────────────

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
            except Exception:
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
        for l in links:
            href = l["href"]
            name = l["text"]
            is_board = ("ArticleList" in href or "search.boardtype" in href)
            if not is_board or href in seen or not name or len(name) < 2:
                continue
            seen.add(href)
            # href에서 menuid 추출
            mid_m = re.search(r"menuid=(\d+)", href)
            menu_id = mid_m.group(1) if mid_m else ""
            # clubid 추출
            cid_m = re.search(r"clubid=(\d+)", href)
            club_id = cid_m.group(1) if cid_m else ""
            boards.append({
                "name": name,
                "href": href,
                "menu_id": menu_id,
                "club_id": club_id,
                "count": "",
            })
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
        for l in self.extract_links(filter_href="ArticleList"):
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
        for l in self.extract_links(filter_href="ArticleList"):
            if board in l["text"]:
                url = l["href"]
                sep = "&" if "?" in url else "?"
                if page > 1:
                    url += f"{sep}search.page={page}"
                return url
        # 전체글보기 기본
        club_id = self._get_club_id(cafe_url)
        base = (f"https://cafe.naver.com/ArticleList.nhn"
                f"?search.clubid={club_id}&search.boardtype=L")
        if page > 1:
            base += f"&search.page={page}"
        return base

    def cafe_posts(self, cafe_url: str,
                   board: str = "전체글보기",
                   page: int = 1,
                   max_posts: int = 30) -> list[dict]:
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
            except Exception:
                continue

        return all_posts[:max_posts]

    def cafe_posts_all_pages(self, cafe_url: str,
                             board: str = "전체글보기",
                             max_pages: int = 5) -> list[dict]:
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
                except Exception:
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
            for l in self.extract_links(filter_href="ArticleList"):
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
            except Exception:
                continue

        return all_posts[:max_posts]

    def cafe_search(self, cafe_url: str, query: str,
                    page: int = 1, max_posts: int = 30) -> list[dict]:
        """카페 내 키워드 검색.

        Args:
            cafe_url - 카페 URL
            query    - 검색어
            page     - 페이지 번호
        """
        import urllib.parse

        # clubid 추출
        club_id = ""
        m = re.search(r"clubid=(\d+)", cafe_url)
        if not m:
            self.go(cafe_url)
            time.sleep(2)
            for l in self.extract_links(filter_href="ArticleList"):
                cm = re.search(r"clubid=(\d+)", l["href"])
                if cm:
                    club_id = cm.group(1)
                    break
        else:
            club_id = m.group(1)

        q = urllib.parse.quote(query)
        search_url = (
            f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/0"
            f"?viewType=L&ta=ARTICLE_COMMENT&page={page}&q={q}"
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
            except Exception:
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
                            all_posts.append({"title": p.get("title", ""), "href": href,
                                              "author": "", "date": "", "views": "", "comments": ""})
                except Exception:
                    continue

        return all_posts[:max_posts]

    def cafe_new_posts(self, cafe_url: str, max_posts: int = 30) -> list[dict]:
        """새 글 (최신 전체글) 목록 반환."""
        return self.cafe_posts(cafe_url, board="전체글보기", max_posts=max_posts)

    # ── 출석체크 ────────────────────────────────────────────────────────────────

    def cafe_attendance(self, cafe_url: str, menu_id: str = "") -> dict:
        """출석체크 게시판 정보 조회.

        반환:
            date        - 현재 날짜 (예: '2026년 05월')
            today_count - 오늘 출석 멤버 수
            records     - list[dict]: author / written_at / message
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return {"date": "", "today_count": 0, "records": []}

        # menuid가 없으면 사이드바에서 출석 게시판 탐색
        if not menu_id:
            self.go(cafe_url)
            time.sleep(2)
            links = self.extract_links(filter_href="AttendanceView")
            if links:
                m = re.search(r"menuid=(\d+)", links[0]["href"])
                if m:
                    menu_id = m.group(1)

        url = (f"https://cafe.naver.com/AttendanceView.nhn"
               f"?search.clubid={club_id}&search.menuid={menu_id}")
        self.go(url)
        time.sleep(3)

        cafe_main = next((f for f in self._page.frames if f.name == "cafe_main"), None)
        frame = cafe_main or self._page

        def _safe(sel: str) -> str:
            try:
                return frame.locator(sel).first.inner_text(timeout=1500).strip()
            except Exception:
                return ""

        date_txt = _safe(".month_tit") or _safe(".date_area") or _safe("h4")
        today_raw = _safe(".today_num") or _safe(".today_cnt") or ""
        today_m = re.search(r"(\d+)", today_raw)
        today_count = int(today_m.group(1)) if today_m else 0

        # 출석 멤버 목록 파싱
        records: list[dict] = []
        try:
            body_txt = frame.inner_text("body")
            # 패턴: 닉네임 → 날짜 → 메시지 반복
            # 실제 DOM에서 row 단위로 읽기
            rows = frame.locator(".attendance_item, .item, li.AttList").all()
            if rows:
                for row in rows:
                    raw = row.inner_text(timeout=500).strip()
                    lines = [l.strip() for l in raw.splitlines() if l.strip()]
                    if not lines:
                        continue
                    author = lines[0]
                    date_m2 = re.search(r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})", raw)
                    written_at = date_m2.group(1).strip() if date_m2 else ""
                    msg_lines = [l for l in lines[1:] if l != written_at
                                 and not re.match(r"\d{4}\.\d{2}\.\d{2}", l)]
                    records.append({
                        "author": author,
                        "written_at": written_at,
                        "message": " ".join(msg_lines).strip()[:200],
                    })
            else:
                # 텍스트 파싱 폴백
                lines = [l.strip() for l in body_txt.splitlines() if l.strip()]
                i = 0
                while i < len(lines):
                    date_m2 = re.search(r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})", lines[i])
                    if date_m2 and i > 0:
                        records.append({
                            "author": lines[i - 1],
                            "written_at": date_m2.group(1).strip(),
                            "message": lines[i + 1] if i + 1 < len(lines) else "",
                        })
                    i += 1
        except Exception:
            pass

        return {"date": date_txt, "today_count": today_count, "records": records}

    # ── 가입인사 ────────────────────────────────────────────────────────────────

    def cafe_greetings(self, cafe_url: str, max_posts: int = 20) -> list[dict]:
        """신입회원 가입인사 목록 조회.

        반환 list[dict]:
            author / written_at / preview / comment_count
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        # 사이드바에서 MemoList menuid 탐색
        self.go(cafe_url)
        time.sleep(2)
        links = self.extract_links(filter_href="MemoList")
        menu_id = ""
        for lk in links:
            m = re.search(r"menuid=(\d+)", lk["href"])
            if m:
                menu_id = m.group(1)
                break

        if not menu_id:
            return []

        url = (f"https://cafe.naver.com/MemoList.nhn"
               f"?search.clubid={club_id}&search.menuid={menu_id}&viewType=pc")
        self.go(url)
        time.sleep(3)

        cafe_main = next((f for f in self._page.frames if f.name == "cafe_main"), None)
        if not cafe_main:
            return []

        # MemoList DOM 구조:
        # "작성자 정보" → 닉네임 → "작성일시" → 날짜 → 내용 → "댓글 정보" → "댓글 N"
        posts: list[dict] = []
        try:
            body_txt = cafe_main.inner_text("body")
            lines = [l.strip() for l in body_txt.splitlines() if l.strip()]
            i = 0
            while i < len(lines) and len(posts) < max_posts:
                if lines[i] == "작성자 정보":
                    author = lines[i + 1] if i + 1 < len(lines) else ""
                    # "작성일시" 스킵
                    j = i + 2
                    if j < len(lines) and lines[j] == "작성일시":
                        j += 1
                    written_at = ""
                    if j < len(lines):
                        date_m = re.search(r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})", lines[j])
                        if date_m:
                            written_at = date_m.group(1).strip()
                            j += 1
                    # 내용 (날짜 다음 줄, "댓글 정보" 전까지)
                    preview_lines = []
                    while j < len(lines) and lines[j] != "댓글 정보":
                        preview_lines.append(lines[j])
                        j += 1
                    preview = " ".join(preview_lines).strip()
                    # 댓글수
                    comment_count = 0
                    if j < len(lines) and lines[j] == "댓글 정보":
                        j += 1
                        if j < len(lines):
                            cm = re.search(r"댓글\s*(\d+)", lines[j])
                            if cm:
                                comment_count = int(cm.group(1))
                    if author and written_at:
                        posts.append({
                            "author": author,
                            "written_at": written_at,
                            "preview": preview[:150],
                            "comment_count": comment_count,
                        })
                    i = j
                else:
                    i += 1
        except Exception:
            pass

        return posts[:max_posts]

    # ── 등업신청 ────────────────────────────────────────────────────────────────

    def cafe_levelup_status(self, cafe_url: str) -> dict:
        """내 등업신청 현황 및 활동 정보 조회.

        반환:
            my_stats    - dict: article_count / comment_count / like_count / attend_count / joined_at
            applications - list[dict]: applicant / target_grade / current_grade / applied_at
            can_apply   - bool
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return {"my_stats": {}, "applications": [], "can_apply": False}

        url = f"https://cafe.naver.com/LevelUpApplyList.nhn?search.clubid={club_id}"
        self.go(url)
        time.sleep(3)

        cafe_main = next((f for f in self._page.frames if f.name == "cafe_main"), None)
        if not cafe_main:
            return {"my_stats": {}, "applications": [], "can_apply": False}

        body_txt = ""
        try:
            body_txt = cafe_main.inner_text("body")
        except Exception:
            return {"my_stats": {}, "applications": [], "can_apply": False}

        # 내 활동 정보 파싱
        stats: dict = {}
        stat_m = re.search(
            r"게시글수\s*(\d+)개.*?댓글수\s*(\d+)개.*?좋아요수\s*(\d+)개.*?출석수\s*(\d+).*?가입일\s*([\d.]+)",
            body_txt, re.DOTALL,
        )
        if stat_m:
            stats = {
                "article_count": int(stat_m.group(1)),
                "comment_count": int(stat_m.group(2)),
                "like_count": int(stat_m.group(3)),
                "attend_count": int(stat_m.group(4)),
                "joined_at": stat_m.group(5),
            }

        can_apply = "등업 신청하기" in body_txt
        no_apply = "등업 신청글이 없습니다" in body_txt

        # 신청 목록 파싱 (테이블 헤더: 신청자 신청등급 현재등급 방문수 게시글수 댓글수 ...)
        applications: list[dict] = []
        lines = [l.strip() for l in body_txt.splitlines() if l.strip()]
        header_idx = next(
            (i for i, l in enumerate(lines) if "신청자" in l and "신청등급" in l), None
        )
        if header_idx is not None and not no_apply:
            for line in lines[header_idx + 1:]:
                parts = line.split("\t") if "\t" in line else line.split()
                if len(parts) >= 3:
                    applications.append({
                        "applicant": parts[0],
                        "target_grade": parts[1] if len(parts) > 1 else "",
                        "current_grade": parts[2] if len(parts) > 2 else "",
                        "applied_at": parts[-1] if len(parts) > 3 else "",
                    })
                    if len(applications) >= 20:
                        break

        return {"my_stats": stats, "applications": applications, "can_apply": can_apply}

    # ── 사진 게시판 ──────────────────────────────────────────────────────────────

    def cafe_photo_posts(self, cafe_url: str, board: str = "", max_posts: int = 30) -> list[dict]:
        """사진 게시판 목록 조회 (boardtype=I).

        반환 list[dict]:
            article_id / title / author / date / views / comments
            thumb_url  - 썸네일 이미지 URL
            href       - 게시글 URL
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        menu_id = ""
        if board:
            self.go(cafe_url)
            time.sleep(2)
            links = self.extract_links(filter_href="ArticleList")
            for lk in links:
                if board in lk["text"]:
                    m = re.search(r"menuid=(\d+)", lk["href"])
                    if m:
                        menu_id = m.group(1)
                        break

        # f-e URL로 사진 게시판 접근
        if menu_id:
            url = f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/{menu_id}?viewType=I"
        else:
            url = f"https://cafe.naver.com/f-e/cafes/{club_id}?viewType=I"

        self.go(url)
        time.sleep(3)

        # f-e 프레임에서 게시글 + 썸네일 추출
        posts: list[dict] = []
        for frame in self._page.frames:
            if "about:blank" in (frame.url or ""):
                continue
            try:
                result = frame.evaluate(_js("extract_cafe_posts.js"))
                if not result:
                    continue

                # 썸네일은 별도 추출
                thumbs = frame.evaluate("""
                (() => {
                    const res = [];
                    for (const el of document.querySelectorAll(
                        '.photo_area img, .thumb img, [class*=\"thumb\"] img, .image_area img'
                    )) {
                        const src = el.src || el.getAttribute('data-src') || '';
                        if (src && !src.includes('default_thumb'))
                            res.push(src);
                    }
                    return res;
                })()
                """)

                seen: set[str] = set()
                for idx, p in enumerate(result):
                    aid_m = re.search(r"articles/(\d+)|articleid=(\d+)", p.get("href", ""))
                    aid = (aid_m.group(1) or aid_m.group(2)) if aid_m else ""
                    if not aid or aid in seen:
                        continue
                    seen.add(aid)
                    p["article_id"] = aid
                    p["thumb_url"] = thumbs[idx] if idx < len(thumbs) else ""
                    posts.append(p)

                if posts:
                    break
            except Exception:
                continue

        return posts[:max_posts]

    # ── 멤버 프로필 ─────────────────────────────────────────────────────────────

    def cafe_member_profile(self, member_url: str) -> dict:
        """카페 멤버 프로필 조회.

        member_url 예:
          https://cafe.naver.com/ca-fe/cafes/{club_id}/members/{member_id}
          https://cafe.naver.com/f-e/cafes/{club_id}/members/{member_id}

        반환:
            nickname        - 닉네임
            masked_id       - 마스킹된 아이디 (예: fond****)
            visit_count     - 방문수
            article_count   - 작성글 수
            subscriber_count - 구독멤버 수
            recent_articles - list[dict]: title / written_at / views
        """
        # ca-fe URL로 통일 (f-e URL은 내용 없음)
        url = member_url.replace("/f-e/cafes/", "/ca-fe/cafes/")
        self.go(url)
        time.sleep(3)

        body_txt = ""
        try:
            body_txt = self._page.inner_text("body")
        except Exception:
            return {"nickname": "", "masked_id": "", "visit_count": 0,
                    "article_count": 0, "subscriber_count": 0, "recent_articles": []}

        lines = [l.strip() for l in body_txt.splitlines() if l.strip()]

        # DOM 구조:
        # 닉네임 / masked_id / 방문 N / 작성글 N / 구독멤버 N
        nickname = ""
        masked_id = ""
        visit_count = 0
        article_count = 0
        subscriber_count = 0

        # DOM 구조: 이주의 인기멤버 / 닉네임 / 등급 / masked_id / 방문 N / 작성글 N / 구독멤버 N
        for i, line in enumerate(lines):
            m_visit = re.search(r"^방문\s*([\d,]+)$", line)
            if m_visit:
                visit_count = int(m_visit.group(1).replace(",", ""))
                # 역방향으로 닉네임, masked_id 탐색
                if i >= 1:
                    masked_id = lines[i - 1]
                if i >= 3:
                    nickname = lines[i - 3]
                elif i >= 2:
                    nickname = lines[i - 2]
                continue
            m_art = re.search(r"^작성글\s*([\d,]+)$", line)
            if m_art:
                article_count = int(m_art.group(1).replace(",", ""))
                continue
            m_sub = re.search(r"^구독멤버\s*([\d,]+)$", line)
            if m_sub:
                subscriber_count = int(m_sub.group(1).replace(",", ""))

        # 최근 게시글 파싱 (제목 / 작성일 / 조회)
        recent_articles: list[dict] = []
        header_idx = next(
            (i for i, l in enumerate(lines) if "제목" in l and "작성일" in l and "조회" in l), None
        )
        if header_idx is not None:
            i = header_idx + 1
            while i < len(lines) and len(recent_articles) < 10:
                title = lines[i]
                if not title or "작성하신 게시글이 없습니다" in title:
                    break
                written_at = lines[i + 1] if i + 1 < len(lines) else ""
                views = lines[i + 2] if i + 2 < len(lines) else ""
                if re.search(r"\d{4}\.\d{2}\.\d{2}", written_at):
                    recent_articles.append({
                        "title": title,
                        "written_at": written_at,
                        "views": views,
                    })
                    i += 3
                else:
                    i += 1

        return {
            "nickname": nickname,
            "masked_id": masked_id,
            "visit_count": visit_count,
            "article_count": article_count,
            "subscriber_count": subscriber_count,
            "recent_articles": recent_articles,
        }

    # ── 카페 멤버 목록 ───────────────────────────────────────────────────────────

    def cafe_members(self, cafe_url: str, max_members: int = 50) -> list[dict]:
        """카페 멤버 목록 조회.

        반환 list[dict]:
            nickname / grade / joined_at / member_url
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        url = f"https://cafe.naver.com/f-e/cafes/{club_id}/members"
        self.go(url)
        time.sleep(3)

        members: list[dict] = []
        try:
            result = self._page.evaluate("""
            (() => {
                const res = [];
                const sels = [
                    '.member-item', '.MemberItem', '[class*="member-list"] li',
                    '[class*="MemberList"] li', 'li[class*="member"]',
                ];
                for (const sel of sels) {
                    const els = document.querySelectorAll(sel);
                    if (!els.length) continue;
                    for (const el of els) {
                        const nick = (el.querySelector('.nick, .nickname, [class*=nick]')
                                      || el).innerText.trim().split('\\n')[0];
                        const grade = (el.querySelector('.grade, [class*=grade]') || {}).innerText || '';
                        const link = (el.querySelector('a') || {}).href || '';
                        res.push({nickname: nick, grade: grade.trim(), member_url: link});
                    }
                    break;
                }
                return res;
            })()
            """)
            members = result[:max_members]
        except Exception:
            pass

        # 텍스트 폴백
        if not members:
            try:
                body_txt = self._page.inner_text("body")
                links = self.extract_links(filter_href="members/")
                for lk in links:
                    nick = lk.get("text", "").strip()
                    if nick and not any(kw in nick for kw in ("카페홈", "전체글보기", "인기글")):
                        members.append({
                            "nickname": nick,
                            "grade": "",
                            "member_url": lk.get("href", ""),
                        })
                        if len(members) >= max_members:
                            break
            except Exception:
                pass

        return members

    # ── 카페 통계 ────────────────────────────────────────────────────────────────

    def cafe_stats(self, cafe_url: str) -> dict:
        """카페 통계 요약 조회 (게시글 수, 멤버 수, 가입일 등).

        반환:
            name / manager / member_count / total_articles / opened_at / grade / club_id
        """
        return self.cafe_info(cafe_url)

    # ── 좋아요한 글 ──────────────────────────────────────────────────────────────

