"""cafe_mixin 활동 기능 (CafeActivityMixin).

cafe_attendance/greetings/levelup_status/photo_posts. CafeMixin 다중상속.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from scripts.naver.agent_mixins.cafe_mixin_common import _js

_ATTENDANCE_DATE_RE = r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})"


def _find_menu_id_by_link(links: list[dict]) -> str:
    """링크 목록에서 첫 menuid 를 찾는다 (없으면 빈 문자열)."""
    for lk in links:
        m = re.search(r"menuid=(\d+)", lk["href"])
        if m:
            return m.group(1)
    return ""


def _attendance_records_from_rows(rows: list, records: list[dict]) -> None:
    for row in rows:
        raw = row.inner_text(timeout=500).strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]  # noqa: E741
        if not lines:
            continue
        author = lines[0]
        date_m2 = re.search(_ATTENDANCE_DATE_RE, raw)
        written_at = date_m2.group(1).strip() if date_m2 else ""
        msg_lines = [
            l
            for l in lines[1:]  # noqa: E741
            if l != written_at and not re.match(r"\d{4}\.\d{2}\.\d{2}", l)
        ]
        records.append(
            {
                "author": author,
                "written_at": written_at,
                "message": " ".join(msg_lines).strip()[:200],
            }
        )


def _attendance_records_from_text(body_txt: str, records: list[dict]) -> None:
    """텍스트 파싱 폴백."""
    lines = [l.strip() for l in body_txt.splitlines() if l.strip()]  # noqa: E741
    i = 0
    while i < len(lines):
        date_m2 = re.search(_ATTENDANCE_DATE_RE, lines[i])
        if date_m2 and i > 0:
            records.append(
                {
                    "author": lines[i - 1],
                    "written_at": date_m2.group(1).strip(),
                    "message": lines[i + 1] if i + 1 < len(lines) else "",
                }
            )
        i += 1


def _parse_one_greeting(lines: list[str], i: int) -> tuple[dict | None, int]:
    """'작성자 정보' 줄(i)부터 가입인사 1건 파싱. (post|None, 다음 인덱스) 반환."""
    author = lines[i + 1] if i + 1 < len(lines) else ""
    # "작성일시" 스킵
    j = i + 2
    if j < len(lines) and lines[j] == "작성일시":
        j += 1
    written_at = ""
    if j < len(lines):
        date_m = re.search(_ATTENDANCE_DATE_RE, lines[j])
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
        return (
            {
                "author": author,
                "written_at": written_at,
                "preview": preview[:150],
                "comment_count": comment_count,
            },
            j,
        )
    return None, j


def _parse_greetings(lines: list[str], max_posts: int, posts: list[dict]) -> None:
    # MemoList DOM 구조:
    # "작성자 정보" → 닉네임 → "작성일시" → 날짜 → 내용 → "댓글 정보" → "댓글 N"
    i = 0
    while i < len(lines) and len(posts) < max_posts:
        if lines[i] == "작성자 정보":
            post, i = _parse_one_greeting(lines, i)
            if post is not None:
                posts.append(post)
        else:
            i += 1


_PHOTO_THUMBS_JS = """
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
                """


def _collect_photo_posts(result: list, thumbs: list, posts: list[dict]) -> None:
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


def _find_board_menu_id(links: list[dict], board: str) -> str:
    for lk in links:
        if board in lk["text"]:
            m = re.search(r"menuid=(\d+)", lk["href"])
            if m:
                return m.group(1)
    return ""


class CafeActivityMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

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

        url = f"https://cafe.naver.com/AttendanceView.nhn?search.clubid={club_id}&search.menuid={menu_id}"
        self.go(url)
        time.sleep(3)

        cafe_main = next((f for f in self._page.frames if f.name == "cafe_main"), None)
        frame = cafe_main or self._page

        def _safe(sel: str) -> str:
            try:
                return frame.locator(sel).first.inner_text(timeout=1500).strip()
            except Exception:  # noqa: BLE001 - 네이버 카페 활동내역 읽기 전용 파싱 - 실패 시 빈 dict/list 반환
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
                _attendance_records_from_rows(rows, records)
            else:
                _attendance_records_from_text(body_txt, records)
        except Exception:  # noqa: S110, BLE001
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
        menu_id = _find_menu_id_by_link(links)

        if not menu_id:
            return []

        url = f"https://cafe.naver.com/MemoList.nhn?search.clubid={club_id}&search.menuid={menu_id}&viewType=pc"
        self.go(url)
        time.sleep(3)

        cafe_main = next((f for f in self._page.frames if f.name == "cafe_main"), None)
        if not cafe_main:
            return []

        posts: list[dict] = []
        try:
            body_txt = cafe_main.inner_text("body")
            lines = [l.strip() for l in body_txt.splitlines() if l.strip()]  # noqa: E741
            _parse_greetings(lines, max_posts, posts)
        except Exception:  # noqa: S110, BLE001
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
        except Exception:  # noqa: BLE001 - 네이버 카페 활동내역 읽기 전용 파싱 - 실패 시 빈 dict/list 반환
            return {"my_stats": {}, "applications": [], "can_apply": False}

        # 내 활동 정보 파싱
        stats: dict = {}
        stat_m = re.search(
            r"게시글수\s*(\d+)개.*?댓글수\s*(\d+)개.*?좋아요수\s*(\d+)개.*?출석수\s*(\d+).*?가입일\s*([\d.]+)",
            body_txt,
            re.DOTALL,
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
        lines = [l.strip() for l in body_txt.splitlines() if l.strip()]  # noqa: E741
        header_idx = next(
            (i for i, l in enumerate(lines) if "신청자" in l and "신청등급" in l),  # noqa: E741
            None,
        )
        if header_idx is not None and not no_apply:
            for line in lines[header_idx + 1 :]:
                parts = line.split("\t") if "\t" in line else line.split()
                if len(parts) >= 3:
                    applications.append(
                        {
                            "applicant": parts[0],
                            "target_grade": parts[1] if len(parts) > 1 else "",
                            "current_grade": parts[2] if len(parts) > 2 else "",
                            "applied_at": parts[-1] if len(parts) > 3 else "",
                        }
                    )
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
            menu_id = _find_board_menu_id(links, board)

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
                thumbs = frame.evaluate(_PHOTO_THUMBS_JS)

                _collect_photo_posts(result, thumbs, posts)

                if posts:
                    break
            except Exception:  # noqa: BLE001, S112
                continue

        return posts[:max_posts]

    # ── 멤버 프로필 ─────────────────────────────────────────────────────────────
