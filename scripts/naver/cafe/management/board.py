"""네이버 카페 게시판(메뉴) 관리 자동화.

레거시 관리자 화면(ManageMenu.nhn, 내부 iframe: ca-fe/admin/cafes/{clubid}/menu-management)을
CDP로 직접 조작한다. 기존 구현(collection/write) 대비 신규 영역 — capability_check 결과 없음 확인 후 작성.

범위(승인됨): 게시판 목록 조회 + 신규 게시판 추가만. 이름변경·순서변경·삭제는 범위 밖(향후 확장).

사용:
    from scripts.browser.cdp.connection import get_page
    from scripts.naver.cafe.management.board import list_boards, add_board

    page = get_page()
    boards = list_boards(page, "https://cafe.naver.com/haehan")
    result = add_board(page, "https://cafe.naver.com/haehan", "시공사례")
"""

from __future__ import annotations

import re
import time

from playwright.sync_api import Frame, Page

from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login

_log = get_logger(__name__)

_MANAGE_MENU_URL = "https://cafe.naver.com/ManageMenu.nhn?clubid={clubid}"

# 팔레트 게시판 종류 → CSS 클래스 (add_lst 내 <a class="...">)
BOARD_TYPES: dict[str, str] = {
    "통합게시판": "ge_v1",
    "상품등록게시판": "ge_v3",
    "스탭게시판": "ge_v6",
    "메모게시판": "ge_v8",
    "출석부": "ge_v9",
    "카페북": "ge_v10",
}


def _get_clubid(page: Page, cafe_url: str) -> str | None:
    page.goto(cafe_url, timeout=20000, wait_until="domcontentloaded")
    time.sleep(2)
    for f in page.frames:
        m = re.search(r"clubid=(\d+)", f.url)
        if m:
            return m.group(1)
    try:
        html = page.content()
        m = re.search(r'"clubid"\s*:\s*"?(\d+)"?', html) or re.search(r"clubid=(\d+)", html)
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001 - 정규식 매칭 실패는 무시하고 None 반환 — 다음 폴백 로직으로 이어짐
        pass
    return None


def _goto_menu_management(page: Page, clubid: str) -> Frame:
    page.goto(_MANAGE_MENU_URL.format(clubid=clubid), timeout=25000, wait_until="load")
    page.wait_for_timeout(1200)
    for f in page.frames:
        if "menu-management" in f.url:
            return f
    raise RuntimeError("메뉴관리 iframe을 찾을 수 없습니다 (menu-management)")


def list_boards(page: Page, cafe_url: str) -> dict:
    """현재 게시판(메뉴) 목록 조회. '전체글보기'/'인기글' 등 기본메뉴도 함께 반환."""
    if not ensure_naver_login(page).get("ok"):
        return {"ok": False, "error": "login_failed"}

    clubid = _get_clubid(page, cafe_url)
    if not clubid:
        return {"ok": False, "error": f"clubid 추출 실패: {cafe_url}"}

    try:
        frame = _goto_menu_management(page, clubid)
        names = frame.eval_on_selector_all(".edit_lst_box .menu_name", "els => els.map(e => e.textContent.trim())")
    except Exception as e:  # noqa: BLE001 - 네이버 카페 게시판 관리 자동화 — URL 파싱 실패는 None 반환, 목록조회/게시판추가 실패는 ok=False 에러 결과 반환할 뿐 삭제 동작 없음
        _log.error("[cafe-board] 목록 조회 실패: %s", e)
        return {"ok": False, "error": str(e)}

    _log.info("[cafe-board] clubid=%s 게시판 %d개: %s", clubid, len(names), names)
    return {"ok": True, "clubid": clubid, "menus": names}


def add_board(
    page: Page,
    cafe_url: str,
    name: str,
    *,
    board_type: str = "통합게시판",
) -> dict:
    """신규 게시판 추가 (팔레트에서 유형 선택 → 추가 → 이름 지정 → 저장).

    board_type: BOARD_TYPES 키 중 하나 (기본: 통합게시판/일반 게시판 형태).
    """
    if board_type not in BOARD_TYPES:
        return {"ok": False, "error": f"알 수 없는 board_type: {board_type}", "hint": list(BOARD_TYPES)}

    if not ensure_naver_login(page).get("ok"):
        return {"ok": False, "error": "login_failed"}

    clubid = _get_clubid(page, cafe_url)
    if not clubid:
        return {"ok": False, "error": f"clubid 추출 실패: {cafe_url}"}

    try:
        frame = _goto_menu_management(page, clubid)

        css_class = BOARD_TYPES[board_type]
        frame.click(f"a.{css_class}")
        frame.wait_for_timeout(400)
        frame.click(".btn_add a")
        frame.wait_for_timeout(800)

        if board_type == "상품등록게시판":
            # 상품등록게시판은 거래종류(개인거래/공동구매) 선택이 추가로 필수 — 없으면 저장 거부됨.
            frame.get_by_text("공동구매", exact=True).first.click(timeout=5000)
            frame.wait_for_timeout(300)

        name_input = frame.locator("input.ipt_type").first
        name_input.click(timeout=5000)
        name_input.fill(name)
        frame.wait_for_timeout(300)

        frame.locator(".edit_btn_box a.btn_type_edt").first.click(timeout=5000)
        frame.wait_for_timeout(1500)
    except Exception as e:  # noqa: BLE001 - 네이버 카페 게시판 관리 자동화 — URL 파싱 실패는 None 반환, 목록조회/게시판추가 실패는 ok=False 에러 결과 반환할 뿐 삭제 동작 없음
        _log.error("[cafe-board] 게시판 추가 실패 (%s): %s", name, e)
        return {"ok": False, "error": str(e)}

    # 저장 확인 — 재조회
    result = list_boards(page, cafe_url)
    ok = result.get("ok") and name in result.get("menus", [])
    _log.info("[cafe-board] 게시판 추가 %s: %s", "성공" if ok else "확인 실패", name)
    return {"ok": ok, "name": name, "board_type": board_type, "menus": result.get("menus", [])}
