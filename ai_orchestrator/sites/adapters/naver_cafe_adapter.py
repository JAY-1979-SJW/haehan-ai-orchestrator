"""네이버 카페 전용 SiteAdapter — 세션 재사용 중심.

이 어댑터의 핵심 원칙은 아래 순서다 (절대 뒤집지 말 것):

    1. persistent 프로필에 저장된 기존 세션을 최우선으로 사용한다.
    2. 세션이 ACTIVE 라고 판정되면 아이디/비밀번호 입력 로직은 **실행하지 않는다**.
       (애초에 이 어댑터는 입력 로직 자체를 구현하지 않는다.)
    3. 세션이 명확하지 않거나 2차 인증 페이지로 튕기면 보수적으로 REAUTH_REQUIRED.
    4. 사용자가 브라우저에서 직접 로그인/2차 인증을 완료할 때까지 대기한다.

의도적으로 구현하지 않는 것:
    - 아이디/비밀번호 자동 입력
    - CAPTCHA/OTP/2차 인증 자동화
    - anti-bot 우회 / fingerprint 조작
    - 글쓰기/삭제/가입/댓글 등 변경 작업
    - 본문/댓글/좋아요/멤버 정보 수집

이번 단계에서 허용되는 동작:
    - 홈/게시판 1페이지 URL 로 이동 (읽기 전용)
    - 공개 필드 최소 세트 파싱: post_id, title, author, date, url
"""
from __future__ import annotations

import logging
import re
from typing import Any, ClassVar
from urllib.parse import parse_qs, urljoin, urlparse

from ..site_adapter import LoginCheckResult, SiteAdapter

logger = logging.getLogger(__name__)


# ── 어댑터 외부에서 참조 가능한 상태 코드 ──────────────────────────
# 이 문자열은 사용자/대시보드에 그대로 노출되어도 안전하다(민감 원문 없음).
STATUS_SESSION_ACTIVE = "SESSION_ACTIVE"
STATUS_SESSION_EXPIRED = "SESSION_EXPIRED"
STATUS_REAUTH_REQUIRED = "REAUTH_REQUIRED"
STATUS_REAUTH_IN_PROGRESS = "REAUTH_IN_PROGRESS"
STATUS_REAUTH_SUCCESS_RESUMING = "REAUTH_SUCCESS_RESUMING"
STATUS_JOB_RESUMED = "JOB_RESUMED"
STATUS_LOGIN_CHECK_FAILED = "LOGIN_CHECK_FAILED"
STATUS_LIST_PAGE_READY = "LIST_PAGE_READY"
STATUS_LIST_PARSE_OK = "LIST_PARSE_OK"


class NaverCafeAdapter(SiteAdapter):
    """네이버 카페 세션 재사용 어댑터."""

    site_id: ClassVar[str] = "naver_cafe"
    display_name: ClassVar[str] = "Naver Cafe"

    # ── 진입점 URL ─────────────────────────────────────────────
    HOME_URL: ClassVar[str] = "https://cafe.naver.com/"
    LOGIN_URL: ClassVar[str] = "https://www.naver.com/"

    # ── URL 힌트 (소문자 기준으로 비교) ────────────────────────
    # 일반 로그인 페이지로 리다이렉트됨 → 세션 없음.
    LOGIN_URL_HINTS: ClassVar[tuple[str, ...]] = (
        "nid.naver.com/nidlogin",
        "nid.naver.com/login?",
        "nid.naver.com/login/",
    )

    # 2차 인증 / 추가 확인 / 새로운 기기 감지 페이지 → 보수적으로 REAUTH_REQUIRED.
    # 일반 로그인 URL 힌트보다 먼저 검사되어야 한다 (더 구체적인 분류가 우선).
    REAUTH_URL_HINTS: ClassVar[tuple[str, ...]] = (
        "nid.naver.com/login2",
        "nid.naver.com/otp",
        "nid.naver.com/nidotp",
        "nid.naver.com/push/nidlogin_otp",
        "nid.naver.com/user2/help",
        "nid.naver.com/user2/verify",
        "nid.naver.com/user2/api/login_otp",
        "nid.naver.com/login/ext/device",
        "nid.naver.com/ivp",
    )

    # 로그인 상태 신호 (네이버 GNB / 카페 상단). 이 중 하나라도 존재하면 logged_in 판정.
    LOGGED_IN_SELECTORS: ClassVar[tuple[str, ...]] = (
        "a#gnb_logout_button",
        "a[href*='nid.naver.com/nidlogout']",
        "#gnb_my_layer",
        ".MyView-module__link_logout",
    )

    # ── 게시글 목록 파서 셀렉터 (사이트별 튜닝 가능) ──────────
    ROW_SELECTOR: ClassVar[str] = ".article-board table tbody tr"
    LINK_SELECTOR: ClassVar[str] = "a.article"
    AUTHOR_SELECTOR: ClassVar[str] = "td.td_name a, td.p-nick a"
    DATE_SELECTOR: ClassVar[str] = "td.td_date"

    # 2차 인증은 사람이 처리하므로 여유 있게. 운영 단계에서 조정.
    default_reauth_timeout_sec: ClassVar[int] = 300
    default_reauth_poll_interval_sec: ClassVar[float] = 5.0

    # ── 진입 ──────────────────────────────────────────────────
    def open_home(self, page: Any) -> None:
        """네이버 카페 홈으로 이동. 자격증명 입력은 하지 않는다."""
        logger.info("[NAVER-CAFE-OPEN-HOME] url=%s", self.HOME_URL)
        page.goto(self.HOME_URL)

    def open_login_page(self, page: Any) -> None:
        """로그인 페이지로 이동만 수행. 자동 입력 금지 — 사용자가 직접 로그인한다."""
        logger.info("[NAVER-CAFE-OPEN-LOGIN] url=%s", self.LOGIN_URL)
        page.goto(self.LOGIN_URL)

    # ── 로그인 상태 판정 ─────────────────────────────────────
    def check_logged_in(self, page: Any) -> LoginCheckResult:
        """URL + DOM 신호 조합으로 로그인 여부 판정.

        판정 순서 (우선순위):
            1) REAUTH_URL_HINTS 일치 → is_logged_in=False, reason="reauth_required"
            2) LOGIN_URL_HINTS  일치 → is_logged_in=False, reason="redirected_to_login"
            3) LOGGED_IN_SELECTORS 중 하나라도 존재 → is_logged_in=True
            4) 아무 신호도 없음 → is_logged_in=False, reason="no_user_menu"
               (쿠키/호스트만 맞는다고 True 로 판정하지 않는다.)
        """
        current_url = self._safe_url(page)
        lowered = current_url.lower()

        # 1) 2차 인증/추가 확인 — 보수적 우선 분류
        for hint in self.REAUTH_URL_HINTS:
            if hint in lowered:
                return LoginCheckResult(
                    is_logged_in=False,
                    reason="reauth_required",
                    detected_url=current_url,
                    matched_signals=[f"reauth_url_hint:{hint}"],
                )

        # 2) 일반 로그인 페이지로 튕김
        for hint in self.LOGIN_URL_HINTS:
            if hint in lowered:
                return LoginCheckResult(
                    is_logged_in=False,
                    reason="redirected_to_login",
                    detected_url=current_url,
                    matched_signals=[f"login_url_hint:{hint}"],
                )

        # 3) DOM 신호
        matched: list[str] = []
        for selector in self.LOGGED_IN_SELECTORS:
            if self._has_selector(page, selector):
                matched.append(f"selector:{selector}")

        if matched:
            return LoginCheckResult(
                is_logged_in=True,
                reason="logged_in_signals_matched",
                detected_url=current_url,
                matched_signals=matched,
            )

        # 4) 신호 없음 — 보수적으로 False
        return LoginCheckResult(
            is_logged_in=False,
            reason="no_user_menu",
            detected_url=current_url,
            matched_signals=[],
        )

    # ── 목록 수집 (읽기 전용 최소 필드) ───────────────────────
    # 1페이지 단위 수집을 기본으로 한다. max_pages 를 1 로 제한해 대량 스크래핑을 방지한다.
    DEFAULT_MAX_PAGES: ClassVar[int] = 1
    HARD_MAX_PAGES: ClassVar[int] = 5  # 안전 상한. 넘어도 여기서 강제로 잘라낸다.

    def collect_list(
        self,
        page: Any,
        *,
        cursor: str = "",
        page_num: int = 1,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> dict[str, Any]:
        """카페 메인 또는 특정 게시판의 공개 목록을 최소 필드로 수집.

        Args:
            cursor: 이동할 URL. 생략 시 HOME_URL 사용. 상세/본문/댓글 이동은 하지 않는다.
                호출자가 `<board_url>&page={n}` 같은 페이지별 URL 을 주면 page_num 가 무시된다.
            page_num: 시작 페이지 번호 (1-based).
            max_pages: 이번 호출에서 순회할 최대 페이지 수. HARD_MAX_PAGES 로 상한 강제.

        Returns:
            {"items": [...], "cursor": <원래 cursor>, "page_num": n, "pages_read": k,
             "done": bool, "status": <STATUS_*>}

        수집 필드(항목):
            post_id, title, author, date, url
        """
        # 안전 상한 강제 — 무한 페이지 순회 금지.
        bounded_max = max(1, min(int(max_pages), self.HARD_MAX_PAGES))
        target = cursor or self.HOME_URL
        logger.info(
            "[NAVER-CAFE-LIST-GOTO] url=%s page_num=%d max_pages=%d",
            target, page_num, bounded_max,
        )
        page.goto(target)

        check = self.check_logged_in(page)
        if not check.is_logged_in:
            logger.info(
                "[NAVER-CAFE-LIST-BLOCKED] reason=%s detected_path=%s",
                check.reason, self._safe_path(check.detected_url),
            )
            return {
                "items": [],
                "cursor": cursor,
                "page_num": page_num,
                "pages_read": 0,
                "done": False,
                "status": STATUS_LOGIN_CHECK_FAILED,
                "reason": check.reason,
            }

        items = self._parse_article_list(page)
        logger.info(
            "[NAVER-CAFE-LIST-PARSED] page_num=%d count=%d", page_num, len(items),
        )
        return {
            "items": items,
            "cursor": cursor,
            "page_num": page_num,
            "pages_read": 1,   # 1페이지만 순회 (bounded_max 보호)
            "done": True,
            "status": STATUS_LIST_PARSE_OK,
        }

    def _parse_article_list(self, page: Any) -> list[dict[str, str]]:
        try:
            rows = page.query_selector_all(self.ROW_SELECTOR) or []
        except Exception:  # noqa: BLE001 — 선택자 실패/페이지 이탈
            return []

        out: list[dict[str, str]] = []
        for row in rows:
            try:
                link_el = row.query_selector(self.LINK_SELECTOR)
                if link_el is None:
                    continue
                href = self._safe_attr(link_el, "href")
                title = self._safe_text(link_el)
                if not href or not title:
                    continue

                author = self._safe_text(row.query_selector(self.AUTHOR_SELECTOR))
                date = self._safe_text(row.query_selector(self.DATE_SELECTOR))
                post_id = self._extract_post_id(href)
                url = urljoin(self.HOME_URL, href)

                out.append({
                    "post_id": post_id,
                    "title": title,
                    "author": author,
                    "date": date,
                    "url": url,
                })
            except Exception:  # noqa: BLE001 — 단일 행 파싱 실패는 전체 실패가 아님
                continue
        return out

    # ── 내부 헬퍼 (예외 안전, 민감 원문 로깅 없음) ────────────
    def _safe_url(self, page: Any) -> str:
        try:
            u = page.url
            return u if isinstance(u, str) else ""
        except Exception:  # noqa: BLE001
            return ""

    def _safe_path(self, url: str) -> str:
        try:
            return urlparse(url).path or "/"
        except Exception:  # noqa: BLE001
            return ""

    def _has_selector(self, page: Any, selector: str) -> bool:
        try:
            return page.query_selector(selector) is not None
        except Exception:  # noqa: BLE001
            return False

    def _safe_text(self, el: Any) -> str:
        if el is None:
            return ""
        try:
            txt = el.inner_text()
            return (txt or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _safe_attr(self, el: Any, name: str) -> str:
        if el is None:
            return ""
        try:
            v = el.get_attribute(name)
            return v or ""
        except Exception:  # noqa: BLE001
            return ""

    _POST_ID_RE = re.compile(r"/articles/(\d+)")

    def _extract_post_id(self, href: str) -> str:
        """현대 라우팅 '/articles/<id>' 또는 레거시 'articleid=<id>' 에서 추출."""
        if not href:
            return ""
        m = self._POST_ID_RE.search(href)
        if m:
            return m.group(1)
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            for key in ("articleid", "articleId", "ARTICLEID"):
                if key in qs and qs[key]:
                    return qs[key][0]
        except Exception:  # noqa: BLE001
            pass
        return ""


__all__ = [
    "NaverCafeAdapter",
    "STATUS_SESSION_ACTIVE",
    "STATUS_SESSION_EXPIRED",
    "STATUS_REAUTH_REQUIRED",
    "STATUS_REAUTH_IN_PROGRESS",
    "STATUS_REAUTH_SUCCESS_RESUMING",
    "STATUS_JOB_RESUMED",
    "STATUS_LOGIN_CHECK_FAILED",
    "STATUS_LIST_PAGE_READY",
    "STATUS_LIST_PARSE_OK",
]
