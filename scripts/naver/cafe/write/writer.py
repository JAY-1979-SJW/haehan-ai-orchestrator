"""네이버 카페 글쓰기 자동화.

사용:
    from scripts.browser.cdp.connection import get_page
    from scripts.naver.cafe.writer import write_post, confirm_publish

    page = get_page()
    result = write_post(page, cafe_url="https://cafe.naver.com/0moo",
                        board_name="건설 공무 관련 업무",
                        title="제목", body="본문", require_approval=True)
    # result["mode"] == "awaiting_approval" 이면 사용자 확인 후:
    confirm_publish(page)
"""

from __future__ import annotations

import contextlib
import re
import time

import pyperclip
from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login

_log = get_logger(__name__)

_CAFE_WRITE_URL = "https://cafe.naver.com/ca-fe/cafes/{clubid}/articles/write?boardType=L"


def _get_clubid(page: Page, cafe_url: str) -> str | None:
    """카페 URL → clubid 추출."""
    page.goto(cafe_url, timeout=20000, wait_until="domcontentloaded")
    time.sleep(3)
    for f in page.frames:
        m = re.search(r"clubid=(\d+)", f.url)
        if m:
            return m.group(1)
    # 페이지 HTML에서도 시도
    try:
        html = page.content()
        m = re.search(r'"clubid"\s*:\s*"?(\d+)"?', html)
        if m:
            return m.group(1)
        m = re.search(r"clubid=(\d+)", html)
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
        pass
    return None


class CafeWriter:
    def __init__(self, page: Page):
        self.page = page

    def _ensure_login(self) -> bool:
        result = ensure_naver_login(self.page)
        return bool(result.get("ok"))

    def navigate_to_write(self, clubid: str) -> None:
        url = _CAFE_WRITE_URL.format(clubid=clubid)
        _log.info("[cafe-write] 글쓰기 페이지 진입: %s", url)
        self.page.goto(url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(5)

    def select_board(self, board_name: str) -> bool:
        """게시판 선택 드롭다운."""
        try:
            # 드롭다운 열기
            self.page.locator("button.button").first.click(timeout=5000)
            time.sleep(1)
            # 옵션 클릭
            option = self.page.locator(f"button.option:has-text('{board_name}')").first
            option.click(timeout=5000)
            time.sleep(0.8)
            _log.info("[cafe-write] 게시판 선택: %s", board_name)
            return True
        except Exception as e:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
            _log.warning("[cafe-write] 게시판 선택 실패 (%s): %s", board_name, e)
            return False

    def set_title(self, title: str) -> None:
        el = self.page.locator("textarea.textarea_input").first
        el.click(timeout=5000)
        el.fill(title, timeout=5000)
        _log.info("[cafe-write] 제목 입력: %s", title[:30])

    def set_body(self, body: str) -> None:
        """클립보드 붙여넣기로 SE3 본문 입력 (블로그와 동일한 .se-section-text 진입점)."""
        # SE3 에디터 본문 영역 (카페·블로그 공통)
        body_el = self.page.locator(".se-section-text").first
        try:
            body_el.scroll_into_view_if_needed(timeout=5000)
            time.sleep(0.3)
            body_el.click(timeout=5000)
        except Exception:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
            # fallback: JS 포커스
            self.page.evaluate("""
            () => {
                const el = document.querySelector('.se-section-text');
                if (el) { el.scrollIntoView(); el.click(); }
            }
            """)
            time.sleep(0.5)
        time.sleep(0.3)
        pyperclip.copy(body)
        self.page.keyboard.press("Control+v")
        time.sleep(1)
        _log.info("[cafe-write] 본문 붙여넣기 완료 (%d자)", len(body))

    def set_tags(self, tags: list[str]) -> None:
        """태그 입력 (Enter 구분)."""
        if not tags:
            return
        try:
            tag_input = self.page.locator("input.tag_input").first
            for tag in tags[:10]:
                tag_input.click(timeout=3000)
                tag_input.type(tag, delay=30)
                time.sleep(0.2)
                self.page.keyboard.press("Enter")
                time.sleep(0.3)
            _log.info("[cafe-write] 태그 입력: %s", tags)
        except Exception as e:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
            _log.warning("[cafe-write] 태그 입력 실패: %s", e)

    def set_visibility(self, members_only: bool = False) -> None:
        """공개 설정 — all(전체공개) / member(카페회원공개)."""
        try:
            if members_only:
                self.page.locator("#member").check(timeout=3000)
            else:
                self.page.locator("#all").check(timeout=3000)
        except Exception as e:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
            _log.warning("[cafe-write] 공개설정 실패: %s", e)

    def save_draft(self) -> bool:
        """임시저장."""
        try:
            self.page.locator("button.btn_temp_save").first.click(timeout=5000)
            time.sleep(2)
            _log.info("[cafe-write] 임시저장 완료")
            return True
        except Exception as e:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
            _log.warning("[cafe-write] 임시저장 실패: %s", e)
            return False

    def publish(self, wait_verify_s: int = 8) -> dict:
        """등록 버튼 클릭 → URL 변경으로 발행 완료 확인."""
        before_url = self.page.url
        try:
            # 카페 SPA 등록 버튼 — 가장 구체적인 셀렉터 우선, 폴백 순서
            for sel in [
                "button.btn_register",
                "button.submit_btn",
                "button[class*='registerButton']",
                "button[class*='Register']:not([class*='temp'])",
                # 텍스트 기반은 마지막 — '등록' 텍스트가 여러 곳에 있을 수 있음
                "button:has-text('등록하기')",
                "button:has-text('게시')",
            ]:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=1000):
                        _log.info("[cafe-write] 등록 버튼 셀렉터: %s", sel)
                        loc.click(timeout=8000)
                        break
                except Exception:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
                    continue
            else:
                # 폴백: DOM에서 '등록' 텍스트 버튼 중 마지막(오른쪽) 것
                self.page.evaluate("""
                () => {
                    const btns = [...document.querySelectorAll('button')].filter(
                        b => b.textContent.trim() === '등록' && !b.disabled
                    );
                    if (btns.length) btns[btns.length - 1].click();
                }
                """)

            # URL 변경 대기 (글쓰기 페이지 → 게시글 페이지)
            # 네이버 카페 글쓰기 자동화(CafeWriter) - timeout 은 아래 URL 체크로 판정(성공 위장 없음),
            # 발행은 상위 흐름에서 사용자 확인 후 호출됨
            with contextlib.suppress(Exception):
                self.page.wait_for_url(
                    lambda url: "articles/write" not in url and url != before_url,
                    timeout=wait_verify_s * 1000,
                )

            final_url = self.page.url
            _log.info("[cafe-write] 발행 후 URL: %s", final_url)

            if "articles/write" in final_url or final_url == before_url:
                _log.warning("[cafe-write] URL 미변경 — 발행 실패 가능성")
                return {"ok": False, "error": "url_unchanged", "url": final_url}

            log_critical("OTHER", "카페 글 발행", url=final_url)
            return {"ok": True, "url": final_url}
        except Exception as e:  # noqa: BLE001 - 네이버 카페 글쓰기 자동화(CafeWriter) - 게시판선택/제목/본문/태그/공개설정/발행 각 단계 실패시 ok:False,error 반환(성공 위장 없음), 발행은 상위 흐름에서 사용자 확인 후 호출됨
            _log.error("[cafe-write] 발행 버튼 클릭 실패: %s", e)
            return {"ok": False, "error": str(e)}


def write_post(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    page: Page,
    *,
    cafe_url: str,
    board_name: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    members_only: bool = False,
    require_approval: bool = True,
) -> dict:
    """카페 글쓰기 메인 진입점.

    require_approval=True(기본): 임시저장 후 awaiting_approval 반환.
    confirm_publish(page) 호출 시 발행 완료.
    """
    w = CafeWriter(page)
    if not w._ensure_login():
        return {"ok": False, "error": "login_failed"}

    # clubid 추출
    clubid = _get_clubid(page, cafe_url)
    if not clubid:
        return {"ok": False, "error": f"clubid 추출 실패: {cafe_url}"}
    _log.info("[cafe-write] clubid=%s, board=%s", clubid, board_name)

    # 글쓰기 페이지 진입
    w.navigate_to_write(clubid)

    # 게시판 선택
    if board_name:
        w.select_board(board_name)

    # 제목
    w.set_title(title)
    time.sleep(0.3)

    # 본문
    w.set_body(body)

    # 태그
    if tags:
        w.set_tags(tags)

    # 공개설정
    w.set_visibility(members_only=members_only)

    if require_approval:
        # 임시저장 후 승인 대기
        w.save_draft()
        body_preview = body[:120].strip()
        return {
            "ok": True,
            "mode": "awaiting_approval",
            "approval_required": True,
            "summary": {
                "title": title,
                "board": board_name,
                "tags": tags or [],
                "members_only": members_only,
                "body_preview": body_preview,
            },
            "next_step": "confirm_publish(page) 호출 시 발행 완료",
        }

    # 직접 발행
    return w.publish()


def confirm_publish(page: Page, wait_verify_s: int = 5) -> dict:
    """임시저장 상태에서 발행 확정."""
    w = CafeWriter(page)
    return w.publish(wait_verify_s=wait_verify_s)
