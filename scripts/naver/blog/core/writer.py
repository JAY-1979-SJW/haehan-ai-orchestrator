"""네이버 블로그 글쓰기 고도화 모듈 (기존 blog_mixin.blog_write_post 보존).

기존 한계 해결:
  - iframe(mainFrame) 진입 처리
  - 임시저장 복원 다이얼로그 자동 처리
  - SmartEditor 정확한 셀렉터
  - 카테고리/태그/공개설정/댓글허용 등 사이드 패널 완전 처리
  - 임시저장 / 즉시발행 / 예약발행
  - 본문에 단락/이미지/인용/구분선/링크 삽입
  - 발행 성공 검증 + 게시물 URL 정확 추출

핵심 클래스:
  BlogWriter — 글 작성 전체 워크플로우
    .open()                          # 편집기 열기 + 다이얼로그 처리
    .set_title(text)
    .write_body(text|paragraphs)
    .insert_image(path_or_url)
    .insert_quote(text), .insert_divider(), .insert_link(url, text)
    .set_category(name_or_no)
    .set_tags(["태그1", ...])
    .set_visibility("public" | "neighbors" | "mutual" | "private")
    .set_comments_allowed(bool)
    .set_likes_allowed(bool)
    .set_search_exposure(bool)
    .save_draft()                    # 임시저장
    .publish()                       # 즉시 발행
    .schedule_publish(when: datetime)
    .verify_published() -> dict      # 발행 검증 + URL 반환

사용 예:
  from scripts.naver.blog.writer import BlogWriter
  from scripts.browser.cdp.connection import get_page

  page = get_page()
  bw = BlogWriter(page)
  bw.open()
  bw.set_title("오늘의 일기")
  bw.write_body("안녕하세요...")
  bw.insert_image("data/images/photo1.jpg")
  bw.set_tags(["일상", "맛집"])
  bw.set_category("일상")
  bw.set_visibility("public")
  result = bw.publish()
  print(result)  # {"ok": True, "url": "...", "log_no": "..."}
"""

from __future__ import annotations

import contextlib
import difflib
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.blog.page_selectors import (
    EDITOR_BODY as BODY_SEL,
)
from scripts.naver.blog.page_selectors import (
    EDITOR_DRAFT_CANCEL,
    EDITOR_DRAFT_POPUP,
)
from scripts.naver.blog.page_selectors import (
    EDITOR_TITLE as TITLE_SEL,
)
from scripts.naver.blog.page_selectors import (
    EDITOR_VISIBILITY_MAP as VISIBILITY_MAP,
)

_log = get_logger(__name__)

WRITE_URL = "https://blog.naver.com/PostWriteForm.naver"


class BlogWriter:
    """네이버 블로그 SmartEditor3 자동화 작성기.

    SE3는 iframe 없이 메인 페이지에 직접 렌더링.
    blogId 파라미터 필수 — 없으면 "유효하지 않은 요청" 오류 발생.
    """

    def __init__(self, page: Page):
        self.page = page
        self._draft_handled = False

    # ── 초기화 ──────────────────────────────────────────────────────────

    def open(
        self,
        blog_id: str | None = None,
        timeout_ms: int = 30000,
        auto_login: bool = True,
        naver_id: str | None = None,
        naver_pw: str | None = None,
        log_no: str | None = None,
    ) -> bool:
        """편집기 페이지 열기 + 자동 로그인 + 편집기 준비 대기.

        log_no 지정 시 신규 글이 아니라 해당 기존 글을 수정 모드로 연다
        (Naver PostWriteForm.naver 는 logNo 파라미터로 기존 글을 로드).
        """
        _log.info("[blog-writer] 편집기 열기 (blog_id=%s, log_no=%s)", blog_id, log_no)

        # blogId 없으면 로그인 사용자 ID 자동 감지
        if not blog_id:
            blog_id = self._detect_blog_id()

        if not blog_id:
            _log.error("[blog-writer] blog_id 확인 불가 — 로그인 필요")
            return False

        url = f"{WRITE_URL}?blogId={blog_id}"
        if log_no:
            url += f"&logNo={log_no}"
        self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        time.sleep(3)

        # 로그인 확인 — 글쓰기 페이지 접근 실패 시 자동 로그인
        if auto_login and "유효하지 않은" in (self.page.content() or ""):
            try:
                from scripts.naver.common.auth import ensure_naver_login

                result = ensure_naver_login(self.page)
                if not result.get("ok"):
                    _log.error("[blog-writer] 자동 로그인 실패: %s", result.get("reason"))
                    return False
                self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                time.sleep(3)
            except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                _log.warning("[blog-writer] 자동 로그인 처리 실패: %s", e)

        # 편집기 준비 대기 (SE3: .se-section-documentTitle)
        try:
            self.page.wait_for_selector(TITLE_SEL, timeout=15000, state="visible")
            _log.info("[blog-writer] 편집기 준비 완료")
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 편집기 로드 실패: %s", e)
            return False

        # 임시저장 복원 다이얼로그 처리
        self._handle_draft_dialog()
        return True

    def _detect_blog_id(self) -> str | None:
        """로그인된 세션에서 내 블로그 ID 추출.

        section.blog 의 내 블로그(admin) 링크를 우선 사용.
        """
        try:
            self.page.goto(
                "https://section.blog.naver.com/BlogHome.naver", wait_until="domcontentloaded", timeout=10000
            )
            time.sleep(1.5)
            href = self.page.evaluate("""() => {
                const a = document.querySelector('a[href*=\"admin.blog.naver.com/\"]');
                return a ? a.href : null;
            }""")
            if href:
                # 2026-08-24: 하이픈 있는 커스텀 공개 주소("beautiful-light")를
                # "beautiful"까지만 잘라 감지해 존재하지 않는 blogId로 편집기를
                # 열려다 타임아웃 난 사고 — 문자 클래스에 하이픈 추가.
                m = re.search(r"admin\.blog\.naver\.com/([a-zA-Z0-9_-]+)", href)
                if m:
                    _id = m.group(1)
                    if _id not in ("stat", "category", "manage"):
                        return _id
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] blog_id 자동 감지 실패: %s", e)
        return None

    def _handle_draft_dialog(self) -> None:
        """임시저장 복원 다이얼로그 처리 — 새 글로 시작 ('취소' 클릭).

        실검증 셀렉터 (2026-05-19):
          팝업: .se-popup-alert
          취소: .se-popup-button-cancel
        팝업 클릭 후 완전히 사라질 때까지 대기.
        """
        if self._draft_handled:
            return
        time.sleep(1.0)
        try:
            popup = self.page.locator(EDITOR_DRAFT_POPUP)
            if popup.is_visible(timeout=2000):
                cancel_btn = popup.locator(EDITOR_DRAFT_CANCEL).first
                cancel_btn.click(timeout=2000)
                # 팝업이 DOM에서 제거될 때까지 대기 (최대 3초)
                # 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                with contextlib.suppress(Exception):
                    popup.wait_for(state="hidden", timeout=3000)
                _log.info("[blog-writer] 임시저장 복원 다이얼로그 취소 완료")
                time.sleep(0.5)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 다이얼로그 없음 또는 처리 무시: %s", e)
        finally:
            self._draft_handled = True

    # ── 제목/본문 ────────────────────────────────────────────────────────

    def clear_title(self) -> bool:
        """기존 글 수정 시 제목 필드의 기존 텍스트를 전체 선택 후 삭제."""
        try:
            self.page.locator(TITLE_SEL).first.click(timeout=3000)
            time.sleep(0.2)
            self.page.keyboard.press("Control+a")
            time.sleep(0.1)
            self.page.keyboard.press("Delete")
            time.sleep(0.2)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 제목 초기화 실패: %s", e)
            return False

    def clear_body(self) -> bool:
        """기존 글 수정 시 본문 영역 전체(텍스트+이미지)를 선택 후 삭제."""
        try:
            self.page.locator(BODY_SEL).first.click(timeout=3000)
            time.sleep(0.2)
            self.page.keyboard.press("Control+a")
            time.sleep(0.1)
            self.page.keyboard.press("Delete")
            time.sleep(0.3)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 본문 초기화 실패: %s", e)
            return False

    def set_title(self, text: str) -> bool:
        """제목 입력 + 즉시 실제 DOM과 대조 (단계별 체크)."""
        try:
            self.page.locator(TITLE_SEL).first.click(timeout=3000)
            time.sleep(0.3)
            self.page.keyboard.type(text, delay=20)
            time.sleep(0.5)

            actual = self.get_title_text()
            if text.strip() and text.strip() not in actual:
                _log.error(
                    "[blog-writer] 제목 입력 검증 실패 — 요청 %r vs 실제 %r",
                    text[:40],
                    actual[:40],
                )
                return False

            _log.info("[blog-writer] 제목 입력: %s", text[:30])
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 제목 입력 실패: %s", e)
            return False

    def get_title_text(self) -> str:
        """현재 편집기 제목의 실제 텍스트를 읽어온다."""
        try:
            return self.page.locator(".se-title-text").first.inner_text(timeout=3000)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 제목 텍스트 조회 실패: %s", e)
            return ""

    def _type_paragraphs_fallback(self, full_text: str, paragraph_delay: float) -> None:
        """클립보드 실패 시 단락 단위 keyboard.type 폴백."""
        paragraphs = full_text.split("\n\n")
        for i, p in enumerate(paragraphs):
            lines = p.split("\n")
            for j, line in enumerate(lines):
                self.page.keyboard.type(line, delay=15)
                if j < len(lines) - 1:
                    self.page.keyboard.press("Shift+Enter")
            if i < len(paragraphs) - 1:
                self.page.keyboard.press("Enter")
                time.sleep(paragraph_delay)


    def write_body(
        self, text: str | list[str], paragraph_delay: float = 0.3, append: bool = False, verify: bool = True
    ) -> bool:
        """본문 입력. 클립보드 붙여넣기 방식 (빠르고 서식 오염 없음).

        text가 list면 단락 단위 순서 입력.
        \n\n = 단락 구분, \n = 줄바꿈 (SE3가 자동 처리).
        append=True: 이미지 삽입 후 커서 위치(맨 끝)에 이어쓰기 — BODY_SEL 클릭 생략.
        verify=False: 이번 호출분만 문서 전체 텍스트와 대조하면 항상 실패하는
        다중 블록 조합(write_mixed_content) 상황에서 개별 검증을 건너뛴다 —
        그런 경우 호출부가 전체 텍스트로 한 번에 verify_body()를 수행해야 한다.
        """
        try:
            if append:
                # 이미지 삽입 직후 호출 시: 커서가 이미 마지막 블록에 있으므로
                # End 키로 해당 블록 끝으로 이동 후 Enter로 새 단락 시작
                self.page.keyboard.press("End")
                time.sleep(0.2)
                self.page.keyboard.press("Enter")
                time.sleep(0.3)
            else:
                self.page.locator(BODY_SEL).first.click(timeout=3000)
                time.sleep(0.5)

            # 서식 초기화 — 취소선·굵게 등 오염 방지
            self.reset_formatting()

            # 단락 조합
            if isinstance(text, list):
                full_text = "\n".join(text)
            else:
                full_text = text

            # 클립보드 붙여넣기 (pyperclip 우선, 없으면 keyboard.type fallback)
            try:
                import pyperclip

                pyperclip.copy(full_text)
                self.page.keyboard.press("Control+v")
                time.sleep(1.0)
            except (ImportError, Exception):  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                # fallback: 단락 단위 keyboard.type
                self._type_paragraphs_fallback(full_text, paragraph_delay)

            _log.info("[blog-writer] 본문 입력 완료 (%d 자)", len(full_text))

            if not verify:
                return True

            verify_result = self.verify_body(full_text)
            if not verify_result["ok"]:
                _log.error(
                    "[blog-writer] 본문 입력 검증 실패 — 요청 %d자 vs 실제 %d자 (유사도 %.2f) 미리보기: %r",
                    verify_result["expected_len"],
                    verify_result["actual_len"],
                    verify_result["ratio"],
                    verify_result["actual_preview"],
                )
                return False
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 본문 입력 실패: %s", e)
            return False

    def write_mixed_content(self, blocks: list[dict[str, str]]) -> bool:
        """텍스트/이미지를 지정한 순서 그대로 섞어서 본문에 삽입 (섹션별 사진 배치).

        blocks: [{"type": "text", "value": "..."}, {"type": "image", "value": "경로"}, ...]
        순서대로 문서에 그대로 쓰인다 — "첫 사진만 위, 나머지는 맨 아래" 방식(write_body+
        insert_image 개별 호출)과 달리 사진을 원하는 문단 사이에 정확히 끼워 넣을 수 있다.

        전체 텍스트를 이어 붙인 뒤 verify_body()로 한 번에 검증한다.
        """
        full_text_parts: list[str] = []
        first_block = True
        for block in blocks:
            kind = block.get("type")
            value = block.get("value", "")
            if kind == "text":
                if not value.strip():
                    continue
                ok = self.write_body(value, append=not first_block, verify=False)
                full_text_parts.append(value)
            elif kind == "image":
                ok = self.insert_image(value)
            else:
                _log.warning("[blog-writer] write_mixed_content: 알 수 없는 block type %r", kind)
                continue

            if not ok:
                _log.error("[blog-writer] write_mixed_content 실패 — block=%s", kind)
                return False
            first_block = False

        full_text = "\n\n".join(full_text_parts)
        verify = self.verify_body(full_text)
        if not verify["ok"]:
            _log.error(
                "[blog-writer] write_mixed_content 최종 검증 실패 — 요청 %d자 vs 실제 %d자 (유사도 %.2f)",
                verify["expected_len"],
                verify["actual_len"],
                verify["ratio"],
            )
            return False
        return True

    def get_body_text(self) -> str:
        """현재 편집기 본문의 실제 텍스트를 읽어온다 (DOM 재조회, 캐시 없음)."""
        try:
            paragraphs = self.page.locator(".se-text-paragraph").all_inner_texts()
            return "\n".join(paragraphs)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 본문 텍스트 조회 실패: %s", e)
            return ""

    def verify_body(self, expected_text: str, min_ratio: float = 0.6) -> dict:
        """방금 입력한(또는 입력하려던) 본문이 실제로 DOM에 반영됐는지 대조.

        저장/발행 API가 {"ok": True}를 반환해도 클립보드 붙여넣기 실패·전체선택 후
        서식 변경 중 내용 소실 등으로 실제 화면에는 텍스트가 없을 수 있다.
        "성공 로그"를 그대로 믿지 않고 실제 DOM 텍스트와 대조해 조기에 잡아낸다.
        """
        actual = self.get_body_text()
        expected_compact = re.sub(r"\s+", "", expected_text or "")
        actual_compact = re.sub(r"\s+", "", actual or "")
        ratio = difflib.SequenceMatcher(None, expected_compact, actual_compact).ratio() if expected_compact else 1.0
        ok = ratio >= min_ratio
        return {
            "ok": ok,
            "ratio": ratio,
            "expected_len": len(expected_compact),
            "actual_len": len(actual_compact),
            "actual_preview": actual[:200],
        }

    # ── 편집 도구 연동 (SE3 data-name 기준, 2026-05-19 툴바 전수 검증) ──────

    def _toolbar_click(self, data_name: str, wait_s: float = 0.5) -> bool:
        """data-name 기준 툴바 버튼 클릭 공통 헬퍼."""
        try:
            self.page.locator(f'button[data-name="{data_name}"]').first.click(timeout=3000)
            time.sleep(wait_s)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] toolbar(%s) 클릭 실패: %s", data_name, e)
            return False

    def _is_toolbar_active(self, data_name: str) -> bool:
        """툴바 버튼의 현재 활성 상태 감지.

        SE3는 활성 버튼에 'se-is-selected' 클래스를 부여한다.
        aria-pressed="true" 속성도 함께 확인.
        """
        try:
            result = self.page.evaluate(f"""() => {{
                const btn = document.querySelector('button[data-name="{data_name}"]');
                if (!btn) return null;
                const cls = btn.className || '';
                const ariaPressed = btn.getAttribute('aria-pressed');
                return {{
                    selected: cls.includes('se-is-selected'),
                    ariaPressed: ariaPressed === 'true',
                    cls: cls,
                }};
            }}""")
            if result is None:
                return False
            return result.get("selected", False) or result.get("ariaPressed", False)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] _is_toolbar_active(%s) 실패: %s", data_name, e)
            return False

    def _toolbar_ensure(self, data_name: str, want_active: bool, wait_s: float = 0.2) -> bool:
        """툴바 버튼을 원하는 활성 상태로 맞춤.

        현재 상태가 want_active와 다를 때만 클릭한다.
        이미 원하는 상태면 클릭 없이 True 반환.
        """
        current = self._is_toolbar_active(data_name)
        if current == want_active:
            _log.debug("[blog-writer] toolbar(%s) 이미 %s — 클릭 생략", data_name, "활성" if want_active else "비활성")
            return True
        return self._toolbar_click(data_name, wait_s=wait_s)

    def get_editor_state(self) -> dict:
        """현재 에디터의 텍스트 서식 활성 상태를 반환.

        Returns:
            {
                "bold": bool,
                "italic": bool,
                "underline": bool,
                "strikethrough": bool,
                "found": dict[str, bool]  # 버튼 존재 여부
            }
        """
        toggle_buttons = ["bold", "italic", "underline", "strikethrough"]
        try:
            result = self.page.evaluate(
                """(names) => {
                const state = {};
                for (const name of names) {
                    const btn = document.querySelector(`button[data-name="${name}"]`);
                    if (!btn) {
                        state[name] = {found: false, active: false};
                        continue;
                    }
                    const cls = btn.className || '';
                    const ariaPressed = btn.getAttribute('aria-pressed') === 'true';
                    state[name] = {
                        found: true,
                        active: cls.includes('se-is-selected') || ariaPressed,
                        cls: cls,
                    };
                }
                return state;
            }""",
                toggle_buttons,
            )
            return {
                "bold": result.get("bold", {}).get("active", False),
                "italic": result.get("italic", {}).get("active", False),
                "underline": result.get("underline", {}).get("active", False),
                "strikethrough": result.get("strikethrough", {}).get("active", False),
                "detail": result,
            }
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] get_editor_state 실패: %s", e)
            return {"bold": False, "italic": False, "underline": False, "strikethrough": False}

    def get_image_count(self) -> int:
        """현재 편집기 본문에 삽입된 이미지 개수."""
        try:
            return self.page.locator(".se-image").count()
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 이미지 개수 조회 실패: %s", e)
            return -1

    def insert_image(self, path_or_url: str) -> bool:
        """사진 삽입 — 로컬 파일 또는 URL. 삽입 직후 실제 개수 증가를 대조 (단계별 체크)."""
        before = self.get_image_count()
        try:
            if Path(path_or_url).exists():
                # file_chooser 이벤트 가로채기 → OS 파일 다이얼로그 차단
                abs_path = str(Path(path_or_url).absolute())
                with self.page.expect_file_chooser(timeout=5000) as fc_info:
                    self._toolbar_click("image", wait_s=0.5)
                fc_info.value.set_files(abs_path)
                time.sleep(2.5)
                _log.info("[blog-writer] 사진 첨부: %s", abs_path)
            else:
                self._toolbar_click("image", wait_s=0.8)
                self.page.locator('input[placeholder*="URL"], input[type="url"]').first.fill(path_or_url, timeout=3000)
                self.page.keyboard.press("Enter")
                time.sleep(2)
                _log.info("[blog-writer] 사진 URL 삽입: %s", path_or_url[:60])

            after = self.get_image_count()
            if before >= 0 and after <= before:
                _log.error(
                    "[blog-writer] 사진 삽입 검증 실패 — 삽입 전 %d장, 삽입 후 %d장 (증가 없음)",
                    before,
                    after,
                )
                return False
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 사진 삽입 실패: %s", e)
            return False

    def insert_video(self, path: str, title: str = "", description: str = "") -> bool:
        """로컬 영상 파일 삽입 (네이버 동영상 업로더 경유).

        실검증 흐름 (2026-05-19):
          toolbar "video" 클릭 → file_chooser 감지 → 파일 설정 →
          제목 입력 (필수) → "완료" 버튼 클릭 → se-section-video 삽입 확인
        """
        try:
            abs_path = str(Path(path).absolute())
            if not Path(abs_path).exists():
                _log.error("[blog-writer] 영상 파일 없음: %s", abs_path)
                return False

            # file_chooser 이벤트 가로채기 + 툴바 클릭
            with self.page.expect_file_chooser(timeout=5000) as fc_info:
                self._toolbar_click("video", wait_s=1.0)
                # 업로더 팝업 내 로컬 파일 버튼 클릭
                self.page.locator(
                    "button.nvu_local, button.nvu_btn_append.nvu_local, button.nvu_btn_local"
                ).first.click(timeout=3000)

            fc_info.value.set_files(abs_path)
            _log.info("[blog-writer] 영상 파일 설정: %s", abs_path)

            # 업로드 완료 대기 (최대 30초)
            for _ in range(30):
                time.sleep(1.0)
                state = self.page.evaluate("""() => {
                    const s = document.querySelector('.nvu_state');
                    return s ? s.textContent.trim() : '';
                }""")
                if "업로드 완료" in state or "처리 완료" in state:
                    break
                if "오류" in state or "실패" in state:
                    _log.error("[blog-writer] 영상 업로드 오류: %s", state)
                    return False

            # 제목 입력 (필수)
            video_title = title or Path(path).stem
            try:
                self.page.locator("input.nvu_inp").first.fill(video_title, timeout=3000)
                time.sleep(0.3)
            except Exception:  # noqa: BLE001 - 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                pass

            if description:
                try:
                    self.page.locator("textarea.nvu_inp").first.fill(description, timeout=2000)
                    time.sleep(0.3)
                except Exception:  # noqa: BLE001 - 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                    pass

            # 완료 버튼 클릭 → 에디터 삽입
            self.page.locator("button.nvu_btn_submit").first.click(timeout=3000)
            time.sleep(3.0)

            _log.info("[blog-writer] 영상 삽입 완료: %s", video_title)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 영상 삽입 실패: %s", e)
            self.page.keyboard.press("Escape")
            return False

    def reset_formatting(self) -> None:
        """현재 활성화된 텍스트 서식(bold/italic/underline/strikethrough) 모두 해제.

        write_body() 전에 호출해 취소선·굵게 오염 방지.
        """
        for name in ("bold", "italic", "underline", "strikethrough"):
            if self._is_toolbar_active(name):
                self._toolbar_click(name, wait_s=0.1)
        _log.debug("[blog-writer] 서식 초기화 완료")

    def insert_quote(self, text: str, style: int = 0) -> bool:
        """인용구 삽입. style=0~2 (기본/스타일2/스타일3)."""
        try:
            # 인용구 선택 드롭다운 열기
            self._toolbar_click("quotation", wait_s=0.5)
            # 스타일 선택 (0=첫 번째, 기본값)
            opts = self.page.locator(".se-insert-quotation-option, [class*=quotation-option], [class*=select-option]")
            count = opts.count()
            if count > style:
                opts.nth(style).click(timeout=1500)
                time.sleep(0.3)
            self.page.keyboard.type(text, delay=15)
            _log.info("[blog-writer] 인용구 삽입")
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 인용구 실패: %s", e)
            return False

    def insert_divider(self, style: int = 0) -> bool:
        """구분선 삽입. style=0~N (종류 선택)."""
        try:
            self._toolbar_click("horizontal-line", wait_s=0.5)
            opts = self.page.locator("[class*=horizontal-line-option], [class*=select-option]")
            count = opts.count()
            if count > style:
                opts.nth(style).click(timeout=1500)
            _log.info("[blog-writer] 구분선 삽입")
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 구분선 실패: %s", e)
            return False

    def insert_link(self, url: str) -> bool:
        """OG 링크 카드 삽입 (data-name=oglink).

        클릭 후 나타나는 floating-search 입력창에 URL 입력.
        """
        try:
            self._toolbar_click("oglink", wait_s=1.0)
            inp = self.page.locator(
                'input[class*="floating-search"], input[placeholder*="검색"], input[placeholder*="URL"]'
            ).first
            inp.fill(url, timeout=3000)
            self.page.keyboard.press("Enter")
            time.sleep(2.5)
            _log.info("[blog-writer] 링크 카드 삽입: %s", url[:60])
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 링크 카드 실패: %s", e)
            return False

    def insert_text_link(self, url: str, text: str) -> bool:
        """텍스트에 하이퍼링크 삽입 (data-name=text-link). 선택된 텍스트에 적용."""
        try:
            self._toolbar_click("text-link", wait_s=0.5)
            self.page.locator('input[placeholder*="URL"], input[type="url"]').first.fill(url, timeout=3000)
            self.page.keyboard.press("Enter")
            time.sleep(1)
            _log.info("[blog-writer] 텍스트 링크 삽입")
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 텍스트 링크 실패: %s", e)
            return False

    # ── 텍스트 서식 ──────────────────────────────────────────────────────

    def set_bold(self, on: bool = True) -> bool:
        """굵게 (Bold).

        on=True  → 활성화 (이미 활성이면 클릭 생략)
        on=False → 비활성화 (이미 비활성이면 클릭 생략)
        on=None  → 무조건 토글 (이전 동작)
        """
        if on is None:
            return self._toolbar_click("bold", wait_s=0.2)
        return self._toolbar_ensure("bold", want_active=on, wait_s=0.2)

    def set_italic(self, on: bool = True) -> bool:
        """기울이기 (Italic).

        on=True/False → 상태 보장, on=None → 토글
        """
        if on is None:
            return self._toolbar_click("italic", wait_s=0.2)
        return self._toolbar_ensure("italic", want_active=on, wait_s=0.2)

    def set_underline(self, on: bool = True) -> bool:
        """밑줄.

        on=True/False → 상태 보장, on=None → 토글
        """
        if on is None:
            return self._toolbar_click("underline", wait_s=0.2)
        return self._toolbar_ensure("underline", want_active=on, wait_s=0.2)

    def set_strikethrough(self, on: bool = True) -> bool:
        """취소선.

        on=True/False → 상태 보장, on=None → 토글
        """
        if on is None:
            return self._toolbar_click("strikethrough", wait_s=0.2)
        return self._toolbar_ensure("strikethrough", want_active=on, wait_s=0.2)

    def set_font_size(self, size: int) -> bool:
        """글자 크기 변경.

        안전장치: 변경 전후 본문 텍스트 길이를 비교해 소실 여부를 감지한다.
        (Ctrl+A 전체선택 후 이 메서드를 호출하면 툴바 포커스 이동 중 선택 영역이
        삭제되는 사고가 재현된 바 있음 — 텍스트가 줄어들면 실패로 처리한다.)
        """
        before_len = len(self.get_body_text())
        try:
            self._toolbar_click("font-size", wait_s=0.4)
            inp = self.page.locator("input[class*=font-size], .se-font-size-input").first
            inp.fill(str(size), timeout=2000)
            self.page.keyboard.press("Enter")
            time.sleep(0.3)

            after_len = len(self.get_body_text())
            if before_len > 0 and after_len < before_len * 0.8:
                _log.error(
                    "[blog-writer] 글자 크기 변경 후 본문 소실 감지 (%d자 → %d자) — 실패 처리",
                    before_len,
                    after_len,
                )
                return False

            _log.info("[blog-writer] 글자 크기: %d", size)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 글자 크기 실패: %s", e)
            return False

    def set_text_format(self, format_name: str) -> bool:
        """문단 서식 변경. format_name: 본문/제목1/제목2/소제목 등."""
        try:
            self._toolbar_click("text-format", wait_s=0.4)
            self.page.get_by_text(format_name, exact=True).first.click(timeout=2000)
            time.sleep(0.3)
            _log.info("[blog-writer] 문단 서식: %s", format_name)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 문단 서식 실패: %s", e)
            return False

    def set_align(self, align: str = "left") -> bool:
        """정렬. align: left/center/right/justify."""
        label_map = {"left": "왼쪽", "center": "가운데", "right": "오른쪽", "justify": "양쪽"}
        try:
            self._toolbar_click("align-drop-down-with-justify", wait_s=0.4)
            label = label_map.get(align, align)
            self.page.get_by_text(label, exact=True).first.click(timeout=2000)
            time.sleep(0.2)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 정렬 실패: %s", e)
            return False

    def insert_code_block(self, code: str, language: str = "") -> bool:
        """소스코드 블록 삽입 (data-name=code)."""
        try:
            self._toolbar_click("code", wait_s=0.8)
            # 언어 선택 드롭다운
            if language:
                try:
                    self.page.get_by_text(language, exact=True).first.click(timeout=1500)
                    time.sleep(0.3)
                except Exception:  # noqa: BLE001 - 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                    pass
            self.page.keyboard.type(code, delay=10)
            _log.info("[blog-writer] 코드 블록 삽입")
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 코드 블록 실패: %s", e)
            return False

    def spellcheck(self) -> bool:
        """맞춤법 검사 실행 (data-name=speller)."""
        return self._toolbar_click("speller", wait_s=1.0)

    # ── 발행 패널 옵션 ────────────────────────────────────────────────────

    def get_selected_category_text(self) -> str:
        """현재 선택된 카테고리 표시 텍스트."""
        try:
            return self.page.locator('.category_select, button:has-text("카테고리")').first.inner_text(timeout=2000)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 카테고리 텍스트 조회 실패: %s", e)
            return ""

    def set_category(self, name_or_no: str) -> bool:
        """카테고리 선택 + 선택 후 실제 표시값 대조 (단계별 체크)."""
        try:
            self.page.locator('.category_select, button:has-text("카테고리")').first.click(timeout=2000)
            time.sleep(0.5)
            try:
                self.page.locator(f'[data-category-no="{name_or_no}"]').first.click(timeout=1500)
            except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                self.page.get_by_text(name_or_no, exact=True).first.click(timeout=2000)
            time.sleep(0.5)

            actual = self.get_selected_category_text()
            if name_or_no and name_or_no not in actual:
                _log.warning(
                    "[blog-writer] 카테고리 선택 검증 실패 — 요청 %r vs 실제 표시 %r",
                    name_or_no,
                    actual[:40],
                )
                return False

            _log.info("[blog-writer] 카테고리 선택: %s", name_or_no)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.warning("[blog-writer] 카테고리 선택 실패: %s", e)
            return False

    def _is_publish_panel_open(self) -> bool:
        """발행 옵션 패널(카테고리/태그/공개설정 등)이 열려있는지 확인."""
        try:
            return self.page.locator('.layer_popup__i0QOY.is_show__TMSLq, input[placeholder*="태그"]').first.is_visible(
                timeout=500
            )
        except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            return False

    def _open_publish_panel(self) -> bool:
        """발행 옵션 패널 열기 (태그/카테고리 입력창은 이 패널 안에만 존재).

        이미 열려있으면 재클릭하지 않는다 — 열린 패널 위에 재클릭하면
        오버레이가 포인터 이벤트를 가로채 TimeoutError가 발생한다.
        """
        if self._is_publish_panel_open():
            return True
        try:
            # class 셀렉터 우선 (정확) — CSS 콤마 셀렉터는 DOM 순서로 매칭되어
            # "예약 발행" 버튼(reserve_btn)이 먼저 잡히는 사고가 있었다(2026-08-14).
            btn = self.page.locator("button.publish_btn__m9KHH").first
            if not btn.is_visible(timeout=1500):
                btn = self.page.get_by_role("button", name="발행", exact=True).first
            btn.click(timeout=3000)
            time.sleep(1.0)
            return self._is_publish_panel_open()
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.warning("[blog-writer] 발행 패널 열기 실패: %s", e)
            return False

    def get_tags_text(self) -> str:
        """발행 패널의 태그 목록 표시 텍스트 (패널이 열려있을 때만 유효).

        (2026-08-14: 클래스명이 CSS 모듈 해시라 "tag_list"/"tagList" 문자열이
        그대로 안 남아있음 — 실검증 결과 `[class*="tag"]`가 정확히 매칭됨)
        """
        try:
            return self.page.locator('[class*="tag"]').first.inner_text(timeout=2000)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 태그 목록 조회 실패: %s", e)
            return ""

    def set_tags(self, tags: list[str]) -> bool:
        """태그 추가 + 입력 직후 실제 태그 목록과 대조 (단계별 체크).

        태그 입력창은 상단 편집 화면이 아니라 '발행' 버튼을 눌러 여는
        발행 옵션 패널 안에만 존재한다 — 패널을 먼저 연다.
        패널의 최종 '발행' 버튼은 누르지 않고 Escape로 닫아 발행 사고를 방지한다.
        """
        if not self._open_publish_panel():
            _log.warning("[blog-writer] 태그 추가 실패: 발행 패널을 열 수 없음")
            return False
        try:
            tag_input = self.page.locator('input[placeholder*="태그"]').first
            tag_input.click(timeout=2000)

            # 수정 발행 시 기존 태그가 남아있으면 재입력과 뒤섞여 태그가
            # 이어붙는 사고가 났다(2026-09-10 실측). 입력 전 기존 태그를
            # 전부 지운다 — 빈 입력에서 Backspace는 바로 앞 태그 pill을 지움.
            existing = self.get_tags_text()
            if existing.strip():
                for _ in range(40):
                    self.page.keyboard.press("Backspace")
                    time.sleep(0.05)
                    if not self.get_tags_text().strip():
                        break

            for t in tags:
                self.page.keyboard.type(t, delay=20)
                self.page.keyboard.press("Enter")
                time.sleep(0.2)

            actual = self.get_tags_text()
            missing = [t for t in tags if t not in actual]
            if missing:
                _log.warning("[blog-writer] 태그 검증 실패 — 반영 안 된 태그: %s (실제: %r)", missing, actual[:100])
                return False

            _log.info("[blog-writer] 태그 %d개 추가", len(tags))
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.warning("[blog-writer] 태그 추가 실패: %s", e)
            return False
        finally:
            self.page.keyboard.press("Escape")
            time.sleep(0.3)

    def set_visibility(self, level: str = "public") -> bool:
        """공개 설정."""
        if level not in VISIBILITY_MAP:
            _log.error("[blog-writer] 잘못된 공개설정: %s", level)
            return False
        try:
            value = VISIBILITY_MAP[level]
            try:
                self.page.locator(f'input[name="visibility"][value="{value}"]').first.click(timeout=1500)
            except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                label_map = {
                    "public": "전체공개",
                    "neighbors": "이웃공개",
                    "mutual": "서로이웃공개",
                    "private": "비공개",
                }
                self.page.get_by_text(label_map[level], exact=True).first.click(timeout=2000)
            _log.info("[blog-writer] 공개설정: %s", level)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.warning("[blog-writer] 공개설정 실패: %s", e)
            return False

    def set_comments_allowed(self, allowed: bool = True) -> bool:
        """댓글 허용 여부. 실검증 id: publish-option-comment (2026-05-19)."""
        return self._set_publish_checkbox("publish-option-comment", allowed, "댓글")

    def set_likes_allowed(self, allowed: bool = True) -> bool:
        """공감 허용 여부. 실검증 id: publish-option-sympathy (2026-05-19)."""
        return self._set_publish_checkbox("publish-option-sympathy", allowed, "공감")

    def set_search_exposure(self, allowed: bool = True) -> bool:
        """검색 노출 허용. 실검증 id: publish-option-search (2026-05-19)."""
        return self._set_publish_checkbox("publish-option-search", allowed, "검색노출")

    def _set_publish_checkbox(self, cb_id: str, want: bool, label: str) -> bool:
        """발행 패널 체크박스를 원하는 상태로 설정.

        네이버 SE3 발행 패널 체크박스는 name 없고 id로만 식별 (2026-05-19 확인).
        """
        try:
            cb = self.page.locator(f"#{cb_id}").first
            if cb.is_checked(timeout=1500) != want:
                cb.click(timeout=1500)
                time.sleep(0.2)
            _log.info("[blog-writer] %s %s", label, "허용" if want else "거부")
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] %s 설정 무시: %s", label, e)
            return False

    # ── 저장/발행 ────────────────────────────────────────────────────────

    def save_draft(self) -> dict:
        """임시저장."""
        try:
            self.page.locator('button:has-text("저장")').first.click(timeout=3000)
            time.sleep(2)
            _log.info("[blog-writer] 임시저장 완료")
            log_critical("OTHER", "블로그 임시저장", mode="blog_draft")
            return {"ok": True, "mode": "draft"}
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 임시저장 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def publish(self, wait_verify_s: int = 8) -> dict:
        """즉시 발행 + 검증. 상단 '발행' 버튼(exact) → 패널 내 confirm_btn 순서."""
        try:
            # 1) 발행 옵션 패널 열기 — 이미 열려있으면 재클릭하지 않는다.
            #    (열린 패널 위에 재클릭하면 오버레이가 포인터 이벤트를 가로채 실패한다.)
            self._open_publish_panel()

            # 2) 패널 내 최종 발행 버튼 (.confirm_btn 또는 .publish_btn 계열 fallback)
            try:
                self.page.locator('[class*="confirm_btn"]').click(timeout=3000)
            except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                # 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                with contextlib.suppress(Exception):
                    self.page.get_by_role("button", name="발행", exact=True).last.click(timeout=3000)

            # 3) URL이 PostWriteForm에서 벗어날 때까지 최대 30초 대기
            deadline = max(wait_verify_s, 30)
            try:
                self.page.wait_for_url(
                    lambda url: "PostWriteForm" not in url,
                    timeout=deadline * 1000,
                )
            except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                time.sleep(wait_verify_s)

            return self.verify_published()
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 발행 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def schedule_publish(self, when: datetime) -> dict:
        """예약 발행."""
        try:
            try:
                self.page.locator('button:has-text("발행")').first.click(timeout=3000)
                time.sleep(1.5)
            except Exception:  # noqa: BLE001 - 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                pass

            self.page.locator('input[type="radio"][value="reserve"], label:has-text("예약")').first.click(timeout=2000)
            time.sleep(0.5)

            self.page.locator('input[type="date"], input.date_input').first.fill(
                when.strftime("%Y-%m-%d"), timeout=2000
            )
            self.page.locator('input[type="time"], input.time_input').first.fill(when.strftime("%H:%M"), timeout=2000)
            time.sleep(0.5)

            self.page.locator('button:has-text("예약"), button.confirm:has-text("발행")').first.click(timeout=3000)
            time.sleep(5)

            _log.info("[blog-writer] 예약 발행: %s", when)
            log_critical("OTHER", "블로그 예약 발행", scheduled_at=when.isoformat(), mode="blog_schedule")
            return {"ok": True, "mode": "scheduled", "scheduled_at": when.isoformat()}
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 예약 발행 실패: %s", e)
            return {"ok": False, "error": str(e)}

    # ── 검증 ────────────────────────────────────────────────────────────

    def verify_published(self) -> dict:
        """발행 성공 검증 + 게시물 URL 반환."""
        current = self.page.url
        m = re.search(
            r"blog\.naver\.com/(?:PostView\.naver\?.*blogId=([^&]+).*[?&]logNo=(\d+)|([a-zA-Z0-9_-]+)/(\d{10,}))",
            current,
        )

        title_text = ""
        # 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
        with contextlib.suppress(Exception):
            title_text = self.page.title()

        result_text = ""
        # 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
        with contextlib.suppress(Exception):
            result_text = self.page.evaluate("() => (document.body?.innerText || '').substring(0, 500)")

        success = bool(m) or "발행" in result_text or "완료" in result_text

        log_no = ""
        blog_id = ""
        if m:
            if m.group(1):  # PostView.naver?blogId=X&logNo=Y
                blog_id = m.group(1)
                log_no = m.group(2)
            else:  # /blogId/logNo
                blog_id = m.group(3)
                log_no = m.group(4)

        result = {
            "ok": success,
            "url": current,
            "blog_id": blog_id,
            "log_no": log_no,
            "title": title_text[:80],
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        }
        if success:
            _log.info("[blog-writer] 발행 검증 성공: %s/%s", blog_id, log_no)
            log_critical("OTHER", "블로그 발행 완료", blog_id=blog_id, log_no=log_no, url=current, mode="blog_publish")
        else:
            _log.warning("[blog-writer] 발행 검증 실패 — URL: %s", current)
        return result


# ── 편의 함수 ──────────────────────────────────────────────────────────────


def _set_category_and_tags(bw: BlogWriter, category: str | None, tags: list[str] | None) -> None:
    """발행 패널의 카테고리/태그 설정."""
    if category:
        bw.set_category(category)
    if tags:
        bw.set_tags(tags)


def _install_dialog_handler(page: Page) -> None:
    """페이지당 1회 dialog dismiss 핸들러 등록."""
    # 명시적 dialog 핸들러 등록 — 미등록 상태로 두면 Playwright 드라이버가 자체
    # 타이밍으로 자동 해제를 시도하다 "No dialog is showing" ProtocolError로
    # Node 프로세스 전체가 죽는 경쟁 상태가 실측 확인됨(2026-08-17, 3번째 포스트
    # 발행 중 크래시). 리스너를 걸어두면 Playwright가 우리 처리를 기다리므로
    # 그 경쟁이 사라진다. 페이지 이동 중 뜨는 beforeunload 등은 무조건 dismiss
    # (변경사항 저장 확인창에서 "취소" = 이동 유지) — 새 다이얼로그를 만들어내는
    # 게 아니라 브라우저가 이미 띄운 것을 처리만 하므로 no-dialog 원칙과 무관.
    if not getattr(page, "_haehan_dialog_handler_installed", False):
        page.on("dialog", lambda d: d.dismiss())
        # 선택적 UI 처리 — 없거나 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
        with contextlib.suppress(Exception):
            page._haehan_dialog_handler_installed = True


def _login_failure(page: Page) -> dict | None:
    """네이버 로그인 확인. 실패하면 오류 dict, 성공이면 None."""
    from scripts.naver.common.auth import ensure_naver_login

    login_result = ensure_naver_login(page)
    if not login_result.get("ok"):
        return {"ok": False, "error": "login_failed", "reason": login_result.get("reason", "")}
    return None


def _resolve_tags(
    tags: list[str] | None, auto_tags: bool, title: str, body_str: str, brand_tags: list[str] | None
) -> list[str] | None:
    """tags 미지정이고 auto_tags 이면 suggest_tags 로 자동 생성."""
    if tags is None and auto_tags:
        try:
            from scripts.naver.blog.tag_suggester import suggest_tags

            tags = suggest_tags(title, body_str, brand_tags=brand_tags)
            _log.info("[write_post] 태그 자동 생성: %s", tags)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.warning("[write_post] 태그 자동 생성 실패 (무시): %s", e)
            tags = []
    return tags


def _write_content(
    bw: BlogWriter, body: str | list[str], images: list[str] | None, body_segments: list[str] | None
) -> dict | None:
    """본문/이미지 입력(write_post·edit_post 공통). 실패하면 오류 dict, 성공이면 None."""
    if body_segments and images:
        # 인터리브 삽입: 세그먼트1 → 이미지1 → 세그먼트2 → 이미지2 → ...
        # write_mixed_content() 사용 — 개별 write_body(verify=True) 루프는 append
        # 플래그 누락으로 커서가 매번 본문 맨 앞으로 돌아가고, 완성되지 않은
        # 구간 텍스트를 전체 문서와 비교해 검증이 항상 실패하는 버그가 있었다.
        blocks: list[dict[str, str]] = []
        for i, seg in enumerate(body_segments):
            blocks.append({"type": "text", "value": seg})
            if i < len(images):
                blocks.append({"type": "image", "value": images[i]})
        if not bw.write_mixed_content(blocks):
            return {"ok": False, "error": "body_segments_failed"}
    elif images:
        # 기존 방식: 이미지 전부 앞에, 본문 뒤
        for img in images:
            bw.insert_image(img)
        if not bw.write_body(body):
            return {"ok": False, "error": "body_failed"}
    else:
        if not bw.write_body(body):
            return {"ok": False, "error": "body_failed"}
    return None


def _request_approval(
    title: str,
    tags: list[str] | None,
    visibility: str,
    body_str: str,
    images: list[str] | None,
    category: str | None,
) -> dict:
    """발행 승인 대기 응답 생성(패널은 열린 채 유지)."""
    _log.info("[write_post] 발행 승인 대기 — confirm_publish(page) 호출로 발행")
    log_critical(
        "OTHER",
        "블로그 발행 승인 요청",
        title=title[:40],
        visibility=visibility,
        tags=tags or [],
        mode="blog_awaiting_approval",
    )
    return {
        "ok": True,
        "mode": "awaiting_approval",
        "approval_required": True,
        "summary": {
            "title": title,
            "tags": tags or [],
            "visibility": visibility,
            "body_preview": body_str[:120].strip(),
            "images": images or [],
            "category": category,
        },
        "next_step": "confirm_publish(page) 호출 시 발행 완료",
    }


def write_post(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    page: Page,
    *,
    title: str,
    body: str | list[str],
    category: str | None = None,
    tags: list[str] | None = None,
    auto_tags: bool = True,
    brand_tags: list[str] | None = None,
    images: list[str] | None = None,
    body_segments: list[str] | None = None,
    visibility: str = "public",
    comments_allowed: bool = True,
    search_exposure: bool = True,
    save_draft_only: bool = False,
    require_approval: bool = True,
    schedule_at: datetime | None = None,
) -> dict:
    """원샷 글 작성 + 발행/저장.

    Args:
        page: Playwright Page (CDP 연결된 로그인 상태)
        title: 제목
        body: 본문 (str 또는 단락 list). body_segments 미지정 시 사용.
        category: 카테고리 이름 또는 번호
        tags: 태그 리스트. None이고 auto_tags=True이면 자동 생성.
        auto_tags: True면 tags=None 일 때 suggest_tags() 자동 호출
        brand_tags: 브랜드 고정 태그 (suggest_tags에 전달)
        images: 이미지 경로/URL 리스트.
                body_segments 지정 시 각 세그먼트 사이에 끼워 넣음(인터리브).
                body_segments 미지정 시 본문 앞에 일괄 삽입.
        body_segments: 본문을 N개 구간으로 나눈 리스트. images와 함께 쓰면
                       세그먼트1 → 이미지1 → 세그먼트2 → 이미지2 → ... 순서로 삽입.
        visibility: public/neighbors/mutual/private
        comments_allowed: 댓글 허용
        search_exposure: 검색 노출
        save_draft_only: True면 임시저장만 (require_approval 무시)
        require_approval: True(기본)면 발행 직전 패널 열어둔 채로
                          awaiting_approval 반환 → confirm_publish() 별도 호출 필요.
                          False면 패널 옵션 설정 후 즉시 발행.
        schedule_at: 지정 시 예약 발행 (require_approval 무시)
    """
    import time as _t

    _install_dialog_handler(page)

    # Step 1: 로그인 확인
    login_error = _login_failure(page)
    if login_error is not None:
        return login_error

    # Step 2: 태그 자동 생성 (tags 미지정 시)
    body_str = "\n\n".join(body) if isinstance(body, list) else body
    tags = _resolve_tags(tags, auto_tags, title, body_str, brand_tags)

    bw = BlogWriter(page)
    if not bw.open():
        return {"ok": False, "error": "editor_open_failed"}

    if not bw.set_title(title):
        return {"ok": False, "error": "title_failed"}

    content_error = _write_content(bw, body, images, body_segments)
    if content_error is not None:
        return content_error

    # 임시저장만
    if save_draft_only:
        result = bw.save_draft()
        result["tags_used"] = tags or []
        return result

    # 예약 발행
    if schedule_at:
        page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
        _t.sleep(1.5)
        _set_category_and_tags(bw, category, tags)
        bw.set_visibility(visibility)
        return bw.schedule_publish(schedule_at)

    # 발행 패널 열기 + 옵션 세팅
    page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
    _t.sleep(1.5)

    _set_category_and_tags(bw, category, tags)
    bw.set_visibility(visibility)
    bw.set_comments_allowed(comments_allowed)
    bw.set_search_exposure(search_exposure)

    # 승인 게이트 — 패널 열린 상태 유지, 사용자 승인 대기
    if require_approval:
        return _request_approval(title, tags, visibility, body_str, images, category)

    # 즉시 발행 (require_approval=False)
    result = bw.publish()
    result["tags_used"] = tags or []
    return result


def edit_post(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    page: Page,
    *,
    blog_id: str,
    log_no: str,
    title: str,
    body: str | list[str],
    tags: list[str] | None = None,
    images: list[str] | None = None,
    body_segments: list[str] | None = None,
    visibility: str = "public",
) -> dict:
    """이미 발행된 기존 글(log_no)을 새 제목/본문으로 덮어써 재발행.

    write_post()와 달리 신규 글을 만들지 않고 PostWriteForm.naver?...&logNo=
    로 기존 글을 로드한 뒤 제목/본문을 전체 삭제하고 새로 채운다. 발행 버튼은
    write_post()와 동일 — Naver 에디터가 logNo 존재 여부로 자동으로
    "수정 저장"인지 "신규 발행"인지 판단한다.
    """
    _install_dialog_handler(page)

    login_error = _login_failure(page)
    if login_error is not None:
        return login_error

    bw = BlogWriter(page)
    if not bw.open(blog_id=blog_id, log_no=log_no):
        return {"ok": False, "error": "editor_open_failed"}

    if not bw.clear_title():
        return {"ok": False, "error": "clear_title_failed"}
    if not bw.set_title(title):
        return {"ok": False, "error": "title_failed"}

    if not bw.clear_body():
        return {"ok": False, "error": "clear_body_failed"}

    content_error = _write_content(bw, body, images, body_segments)
    if content_error is not None:
        return content_error

    page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
    time.sleep(1.5)

    if tags:
        bw.set_tags(tags)
    bw.set_visibility(visibility)

    result = bw.publish()
    result["tags_used"] = tags or []
    return result


def confirm_publish(page: Page, wait_verify_s: int = 8) -> dict:
    """발행 패널이 열린 상태에서 최종 발행 버튼을 클릭한다.

    write_post(..., require_approval=True) 호출 후 사용자 승인이 완료되면
    이 함수를 호출해 발행을 확정한다.

    Args:
        page: write_post() 에 전달한 동일 Page (발행 패널 열린 상태)
        wait_verify_s: 발행 후 검증 대기 시간(초)

    Returns:
        {"ok": True, "url": ..., "blog_id": ..., "log_no": ...}
    """
    bw = BlogWriter(page)
    result = bw.publish(wait_verify_s=wait_verify_s)
    if result.get("ok"):
        _log.info("[confirm_publish] 발행 완료: %s", result.get("url"))
    else:
        _log.error("[confirm_publish] 발행 실패: %s", result.get("error"))
    return result
