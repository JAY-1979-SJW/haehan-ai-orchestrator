"""네이버 블로그 에디터(SE3) 셀렉터 헬스체크 명세.

2026-08-14~15 실측으로 확인한 사실을 그대로 반영:
  - 태그 입력창은 상단 편집화면에 없고 **'발행' 패널 안에만** 존재한다.
  - 발행 패널은 열려 있을 때 재클릭하면 오버레이가 포인터를 가로챈다.
"""

from __future__ import annotations

import time
from typing import Any

from tools.selector_health.core import SelectorCheck, SiteSpec

WRITE_URL = "https://blog.naver.com/PostWriteForm.naver?blogId=skyjwsin"


# ── 선행조건 ────────────────────────────────────────────────────────
def _open_publish_panel(page: Any) -> bool:
    """발행 옵션 패널 열기 (태그/카테고리 입력창이 이 안에만 있음)."""

    def _is_open() -> bool:
        try:
            return page.locator('.layer_popup__i0QOY.is_show__TMSLq, input[placeholder*="태그"]').first.is_visible(
                timeout=800
            )
        except Exception:  # noqa: BLE001 - 네이버 블로그 셀렉터 헬스체크(읽기전용, 발행상태 존재여부만 확인) — 발행상태 확인/버튼클릭 시도 실패 시 False 반환할 뿐 실제 발행을 수행하지 않음
            return False

    if _is_open():
        return True
    try:
        page.locator("button.publish_btn__m9KHH").first.click(timeout=4000)
    except Exception:  # noqa: BLE001 - 네이버 블로그 셀렉터 헬스체크(읽기전용, 발행상태 존재여부만 확인) — 발행상태 확인/버튼클릭 시도 실패 시 False 반환할 뿐 실제 발행을 수행하지 않음
        try:
            page.get_by_role("button", name="발행", exact=True).first.click(timeout=4000)
        except Exception:  # noqa: BLE001 - 네이버 블로그 셀렉터 헬스체크(읽기전용, 발행상태 존재여부만 확인) — 발행상태 확인/버튼클릭 시도 실패 시 False 반환할 뿐 실제 발행을 수행하지 않음
            return False
    time.sleep(1.2)
    return _is_open()


CHECKS = [
    SelectorCheck("EDITOR_TITLE", ".se-section-documentTitle", note="제목 입력 영역. 죽으면 set_title 실패"),
    SelectorCheck("EDITOR_BODY", ".se-section-text", note="본문 입력 영역. 죽으면 write_body 실패"),
    SelectorCheck("TOOLBAR_IMAGE", 'button[data-name="image"]', note="사진 삽입 툴바. 죽으면 insert_image 실패"),
    SelectorCheck(
        "BODY_TEXT_PARAGRAPH",
        ".se-text-paragraph",
        expect="present",
        note="본문 검증(verify_body)이 읽는 단위. 죽으면 검증이 항상 실패",
    ),
    SelectorCheck(
        "PUBLISH_PANEL_BTN",
        "button.publish_btn__m9KHH",
        note="발행 패널 여는 버튼. CSS 콤마 셀렉터 쓰면 '예약 발행'이 먼저 잡힘",
    ),
    SelectorCheck("SAVE_DRAFT_BTN", 'button:has-text("저장")', note="임시저장 버튼"),
    # ── 발행 패널을 열어야만 존재하는 것들 ──
    SelectorCheck(
        "TAG_INPUT",
        'input[placeholder*="태그"]',
        requires="publish_panel",
        note="상단 화면엔 없음. 발행 패널 안에만 존재(2026-08-14 확인)",
    ),
    SelectorCheck(
        "TAG_LIST",
        '[class*="tag"]',
        requires="publish_panel",
        expect="present",
        note="태그 반영 검증용. tag_list/tagList 는 해시 때문에 안 잡힘",
    ),
]

SPEC = SiteSpec(
    key="naver_blog",
    title="네이버 블로그 에디터(SE3)",
    url=WRITE_URL,
    checks=CHECKS,
    preconditions={"publish_panel": _open_publish_panel},
    settle_s=5.0,
)
