"""cafe_mixin 회원/통계 기능 (CafeMemberMixin).

cafe_member_profile/cafe_members/cafe_stats. CafeMixin 다중상속.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any


def _parse_member_counts(lines: list[str]) -> tuple[str, str, int, int, int]:
    """프로필 본문 줄에서 (nickname, masked_id, visit, article, subscriber) 추출."""
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
    return nickname, masked_id, visit_count, article_count, subscriber_count


def _parse_recent_articles(lines: list[str]) -> list[dict]:
    """최근 게시글 파싱 (제목 / 작성일 / 조회)."""
    recent_articles: list[dict] = []
    header_idx = next(
        (i for i, l in enumerate(lines) if "제목" in l and "작성일" in l and "조회" in l),  # noqa: E741
        None,
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
                recent_articles.append(
                    {
                        "title": title,
                        "written_at": written_at,
                        "views": views,
                    }
                )
                i += 3
            else:
                i += 1
    return recent_articles


class CafeMemberMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

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
        except Exception:  # noqa: BLE001 - 네이버 카페 회원 프로필/목록 조회(읽기전용) — 페이지 텍스트 추출 실패 시 빈 기본값을 반환, 멤버목록 JS평가/텍스트폴백 실패는 빈 리스트로 안전 처리(이미 noqa: S110 존재).
            return {
                "nickname": "",
                "masked_id": "",
                "visit_count": 0,
                "article_count": 0,
                "subscriber_count": 0,
                "recent_articles": [],
            }

        lines = [l.strip() for l in body_txt.splitlines() if l.strip()]  # noqa: E741

        nickname, masked_id, visit_count, article_count, subscriber_count = _parse_member_counts(lines)
        recent_articles = _parse_recent_articles(lines)

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
        except Exception:  # noqa: S110, BLE001
            pass

        # 텍스트 폴백
        if not members:
            try:
                body_txt = self._page.inner_text("body")  # noqa: F841
                links = self.extract_links(filter_href="members/")
                for lk in links:
                    nick = lk.get("text", "").strip()
                    if nick and not any(kw in nick for kw in ("카페홈", "전체글보기", "인기글")):
                        members.append(
                            {
                                "nickname": nick,
                                "grade": "",
                                "member_url": lk.get("href", ""),
                            }
                        )
                        if len(members) >= max_members:
                            break
            except Exception:  # noqa: S110, BLE001
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
