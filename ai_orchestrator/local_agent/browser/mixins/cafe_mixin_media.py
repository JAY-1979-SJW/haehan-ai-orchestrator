"""cafe_mixin 미디어/일정/이웃 기능 (CafeMediaMixin).

album/polls/calendar/neighbors. CafeMixin 이 다중상속. 메서드 간 호출은
인스턴스(self)/MRO 로 해결. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any


class CafeMediaMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def cafe_album(self, cafe_url: str, menu_id: str = "", page: int = 1, per_page: int = 30) -> dict:
        """카페 앨범(사진 게시판) 목록 조회 — GraphQL BFF 직접 호출.

        반환:
            total_count - 전체 사진 게시글 수
            items       - list[dict]: article_id / title / author / written_at /
                          views / comments / likes / thumb_url
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return {"total_count": 0, "items": []}

        resp = self._fetch_graphql_bff(
            self._GQL_PHOTO_ARTICLES,
            {"cafeId": club_id, "menuId": menu_id or None, "page": page, "perPage": per_page},
            "CafePhotoArticles",
        )

        data = (resp.get("data") or {}).get("cafePhotoArticles") or {}
        raw_items = data.get("items") or []
        items = []
        for it in raw_items:
            thumb = it.get("thumbnail") or {}
            items.append(
                {
                    "article_id": str(it.get("articleId", "")),
                    "title": it.get("subject", ""),
                    "author": it.get("writerNickname", ""),
                    "written_at": it.get("writeDate", ""),
                    "views": it.get("readCount", 0),
                    "comments": it.get("commentCount", 0),
                    "likes": it.get("likeCount", 0),
                    "thumb_url": thumb.get("url", ""),
                }
            )

        # GraphQL 실패 시 f-e 프레임 폴백
        if not items:
            items = self._cafe_album_fallback(cafe_url, menu_id, per_page)

        return {"total_count": data.get("totalCount", len(items)), "items": items}

    def _cafe_album_fallback(self, cafe_url: str, menu_id: str, max_posts: int = 30) -> list[dict]:
        """GraphQL 실패 시 f-e 프레임 폴백."""
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        if menu_id:
            url = f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/{menu_id}?viewType=I"
        else:
            url = f"https://cafe.naver.com/f-e/cafes/{club_id}?viewType=I"

        self.go(url)
        time.sleep(3)
        return self._extract_fe_article_list(max_posts=max_posts)

    # ── 투표 (GraphQL BFF) ────────────────────────────────────────────────────────

    _GQL_POLLS = """
    query CafePolls($cafeId: String!, $page: Int, $perPage: Int) {
      cafePolls(cafeId: $cafeId, page: $page, perPage: $perPage) {
        totalCount
        items {
          pollId
          title
          writerNickname
          writeDate
          endDate
          status
          participantCount
          options { optionId text voteCount }
        }
      }
    }
    """

    def cafe_polls(self, cafe_url: str, page: int = 1, per_page: int = 20) -> dict:
        """카페 투표 목록 조회 — GraphQL BFF 직접 호출.

        반환:
            total_count - 전체 투표 수
            items       - list[dict]: poll_id / title / author / write_date /
                          end_date / status / participants / options
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return {"total_count": 0, "items": []}

        resp = self._fetch_graphql_bff(
            self._GQL_POLLS,
            {"cafeId": club_id, "page": page, "perPage": per_page},
            "CafePolls",
        )

        data = (resp.get("data") or {}).get("cafePolls") or {}
        raw_items = data.get("items") or []
        items = []
        for it in raw_items:
            items.append(
                {
                    "poll_id": str(it.get("pollId", "")),
                    "title": it.get("title", ""),
                    "author": it.get("writerNickname", ""),
                    "write_date": it.get("writeDate", ""),
                    "end_date": it.get("endDate", ""),
                    "status": it.get("status", ""),
                    "participants": it.get("participantCount", 0),
                    "options": [
                        {"id": str(o.get("optionId", "")), "text": o.get("text", ""), "votes": o.get("voteCount", 0)}
                        for o in (it.get("options") or [])
                    ],
                }
            )

        # GraphQL 실패 시 f-e 페이지 텍스트 폴백
        if not items:
            items = self._cafe_polls_fallback(cafe_url, per_page)

        return {"total_count": data.get("totalCount", len(items)), "items": items}

    def _cafe_polls_fallback(self, cafe_url: str, max_polls: int = 20) -> list[dict]:
        """GraphQL 실패 시 f-e 투표 페이지 폴백."""
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        url = f"https://cafe.naver.com/f-e/cafes/{club_id}/polls"
        self.go(url)
        time.sleep(3)

        polls: list[dict] = []
        try:
            body_txt = self._page.inner_text("body")
            lines = [l.strip() for l in body_txt.splitlines() if l.strip()]  # noqa: E741
            for i, line in enumerate(lines):
                if re.search(r"\d{4}\.\d{2}\.\d{2}", line):
                    title = lines[i - 1] if i > 0 else ""
                    if title and len(title) > 4:
                        polls.append(
                            {
                                "poll_id": "",
                                "title": title,
                                "author": "",
                                "write_date": line,
                                "end_date": "",
                                "status": "",
                                "participants": 0,
                                "options": [],
                            }
                        )
                    if len(polls) >= max_polls:
                        break
        except Exception:  # noqa: S110, BLE001
            pass
        return polls

    # ── 캘린더 (GraphQL BFF) ──────────────────────────────────────────────────────

    _GQL_CALENDAR = """
    query CafeCalendarEvents($cafeId: String!, $year: Int!, $month: Int!) {
      cafeCalendarEvents(cafeId: $cafeId, year: $year, month: $month) {
        eventId
        title
        startDate
        endDate
        writerNickname
        description
        isAllDay
      }
    }
    """

    def cafe_calendar(self, cafe_url: str, year: int = 0, month: int = 0) -> list[dict]:
        """카페 캘린더 일정 조회 — GraphQL BFF 직접 호출.

        year/month 미지정 시 현재 월 사용.

        반환 list[dict]:
            event_id / title / start_date / end_date / author / description / is_all_day
        """
        import datetime as _dt

        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        now = _dt.date.today()
        y = year or now.year
        m = month or now.month

        resp = self._fetch_graphql_bff(
            self._GQL_CALENDAR,
            {"cafeId": club_id, "year": y, "month": m},
            "CafeCalendarEvents",
        )

        raw = (resp.get("data") or {}).get("cafeCalendarEvents") or []
        events = []
        for ev in raw:
            events.append(
                {
                    "event_id": str(ev.get("eventId", "")),
                    "title": ev.get("title", ""),
                    "start_date": ev.get("startDate", ""),
                    "end_date": ev.get("endDate", ""),
                    "author": ev.get("writerNickname", ""),
                    "description": ev.get("description", ""),
                    "is_all_day": ev.get("isAllDay", False),
                }
            )

        # GraphQL 실패 시 f-e 폴백
        if not events:
            events = self._cafe_calendar_fallback(cafe_url, y, m)

        return events

    def _cafe_calendar_fallback(self, cafe_url: str, year: int, month: int) -> list[dict]:
        """GraphQL 실패 시 f-e 캘린더 페이지 폴백."""
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        url = f"https://cafe.naver.com/f-e/cafes/{club_id}/calendar?year={year}&month={month}"
        self.go(url)
        time.sleep(3)

        events: list[dict] = []
        try:
            body_txt = self._page.inner_text("body")
            lines = [l.strip() for l in body_txt.splitlines() if l.strip()]  # noqa: E741
            for i, line in enumerate(lines):
                date_m = re.search(r"(\d{4}[-./]\d{2}[-./]\d{2})", line)
                if date_m and i > 0:
                    title = lines[i - 1]
                    if title and not re.search(r"^\d", title):
                        events.append(
                            {
                                "event_id": "",
                                "title": title,
                                "start_date": date_m.group(1),
                                "end_date": "",
                                "author": "",
                                "description": "",
                                "is_all_day": False,
                            }
                        )
        except Exception:  # noqa: S110, BLE001
            pass
        return events

    # ── 이웃 (카페 구독자/팔로워 목록, GraphQL BFF) ───────────────────────────────

    _GQL_NEIGHBORS = """
    query CafeNeighbors($cafeId: String!, $page: Int, $perPage: Int) {
      cafeNeighbors(cafeId: $cafeId, page: $page, perPage: $perPage) {
        totalCount
        items {
          memberId
          nickname
          grade
          joinDate
          articleCount
          visitCount
        }
      }
    }
    """

    def cafe_neighbors(self, cafe_url: str, page: int = 1, per_page: int = 50) -> dict:
        """카페 이웃(구독) 멤버 목록 조회 — GraphQL BFF 직접 호출.

        반환:
            total_count - 전체 이웃 수
            items       - list[dict]: member_id / nickname / grade / join_date /
                          article_count / visit_count
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return {"total_count": 0, "items": []}

        resp = self._fetch_graphql_bff(
            self._GQL_NEIGHBORS,
            {"cafeId": club_id, "page": page, "perPage": per_page},
            "CafeNeighbors",
        )

        data = (resp.get("data") or {}).get("cafeNeighbors") or {}
        raw_items = data.get("items") or []
        items = []
        for it in raw_items:
            items.append(
                {
                    "member_id": str(it.get("memberId", "")),
                    "nickname": it.get("nickname", ""),
                    "grade": it.get("grade", ""),
                    "join_date": it.get("joinDate", ""),
                    "article_count": it.get("articleCount", 0),
                    "visit_count": it.get("visitCount", 0),
                }
            )

        # GraphQL 실패 시 f-e 멤버 목록 폴백
        if not items:
            fallback = self.cafe_members(cafe_url, max_members=per_page)
            return {
                "total_count": len(fallback),
                "items": [
                    {
                        "member_id": "",
                        "nickname": m.get("nickname", ""),
                        "grade": m.get("grade", ""),
                        "join_date": "",
                        "article_count": 0,
                        "visit_count": 0,
                    }
                    for m in fallback
                ],
            }

        return {"total_count": data.get("totalCount", len(items)), "items": items}
