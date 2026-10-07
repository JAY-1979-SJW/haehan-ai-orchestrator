"""네이버 블로그 글쓰기 — 독립 앱 전용 사본 (원본: scripts/naver/blog/core/writer.py).

원본 대비 변경점(전부 "고객 비밀번호를 저장하지 않는다"는 이 앱의 설계 원칙 때문):
  - get_logger: 회사 scripts.common.logger 대신 _bootstrap.get_logger 사용.
  - selectors: connectors.naver_selectors (사본, 0줄 변경) 사용.
  - log_critical(회사 내부 감사 DB 기록) 전부 제거 — 대신 _log.info 로만 남김.
  - ensure_naver_login(자동 재로그인, scripts.auth.credentials 저장 비밀번호로 로그인)
    → connectors.naver_login_check.check_login(로그인 여부만 확인, 자동 로그인
    시도 안 함 — 안 됐으면 "직접 로그인해주세요" 안내만 반환).
  - DOM 조작/발행 로직(BlogWriter 클래스, write_post/edit_post/confirm_publish
    함수 본문)은 원본과 동일 — 셀렉터가 하나라도 달라지면 실제 발행이 깨지므로
    임의로 손대지 않았다.

⚠️ 실제 배포 전 라이브 발행 1건으로 검증 필수(원본 README에 명시된 절차).
"""

from __future__ import annotations

import difflib
import re
import sys as _sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_APP_ROOT))

from _bootstrap import get_logger  # noqa: E402
from connectors.naver_login_check import check_login  # noqa: E402
from connectors.naver_selectors import (  # noqa: E402
    EDITOR_BODY as BODY_SEL,
)
from connectors.naver_selectors import (  # noqa: E402
    EDITOR_DRAFT_CANCEL,
    EDITOR_DRAFT_POPUP,
)
from connectors.naver_selectors import (  # noqa: E402
    EDITOR_TITLE as TITLE_SEL,
)
from connectors.naver_selectors import (  # noqa: E402
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
        log_no: str | None = None,
    ) -> bool:
        """편집기 페이지 열기 + 편집기 준비 대기.

        log_no 지정 시 신규 글이 아니라 해당 기존 글을 수정 모드로 연다
        (Naver PostWriteForm.naver 는 logNo 파라미터로 기존 글을 로드).
        """
        _log.info("[blog-writer] 편집기 열기 (blog_id=%s, log_no=%s)", blog_id, log_no)

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

        # 로그인 확인 — 자동 재로그인은 시도하지 않는다(비밀번호 미보관).
        if "유효하지 않은" in (self.page.content() or ""):
            _log.error("[blog-writer] 편집기 접근 실패 — 로그인 상태를 확인해주세요")
            return False

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
        """로그인된 세션에서 내 블로그 ID 추출. section.blog 의 내 블로그(admin) 링크를 우선 사용."""
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
                m = re.search(r"admin\.blog\.naver\.com/([a-zA-Z0-9_-]+)", href)
                if m:
                    _id = m.group(1)
                    if _id not in ("stat", "category", "manage"):
                        return _id
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] blog_id 자동 감지 실패: %s", e)
        return None

    def _handle_draft_dialog(self) -> None:
        """임시저장 복원 다이얼로그 처리 — 새 글로 시작 ('취소' 클릭)."""
        if self._draft_handled:
            return
        time.sleep(1.0)
        try:
            popup = self.page.locator(EDITOR_DRAFT_POPUP)
            if popup.is_visible(timeout=2000):
                cancel_btn = popup.locator(EDITOR_DRAFT_CANCEL).first
                cancel_btn.click(timeout=2000)
                try:
                    popup.wait_for(state="hidden", timeout=3000)
                except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                    _log.debug("팝업 hidden 대기 실패(무시): %s", e)
                _log.info("[blog-writer] 임시저장 복원 다이얼로그 취소 완료")
                time.sleep(0.5)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 다이얼로그 없음 또는 처리 무시: %s", e)
        finally:
            self._draft_handled = True

    # ── 제목/본문 ────────────────────────────────────────────────────────

    def clear_title(self) -> bool:
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
        try:
            return self.page.locator(".se-title-text").first.inner_text(timeout=3000)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 제목 텍스트 조회 실패: %s", e)
            return ""

    def _type_body_paragraphs(self, full_text: str, paragraph_delay: float) -> None:
        """문단 단위로 직접 타이핑(클립보드 붙여넣기 실패 시 폴백)."""
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
        try:
            if append:
                self.page.keyboard.press("End")
                time.sleep(0.2)
                self.page.keyboard.press("Enter")
                time.sleep(0.3)
            else:
                self.page.locator(BODY_SEL).first.click(timeout=3000)
                time.sleep(0.5)

            self.reset_formatting()

            if isinstance(text, list):
                full_text = "\n".join(text)
            else:
                full_text = text

            try:
                import pyperclip

                pyperclip.copy(full_text)
                self.page.keyboard.press("Control+v")
                time.sleep(1.0)
            except (ImportError, Exception):  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                self._type_body_paragraphs(full_text, paragraph_delay)

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
        try:
            paragraphs = self.page.locator(".se-text-paragraph").all_inner_texts()
            return "\n".join(paragraphs)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 본문 텍스트 조회 실패: %s", e)
            return ""

    def verify_body(self, expected_text: str, min_ratio: float = 0.6) -> dict:
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

    # ── 편집 도구 연동 ──────────────────────────────────────────────────

    def _toolbar_click(self, data_name: str, wait_s: float = 0.5) -> bool:
        try:
            self.page.locator(f'button[data-name="{data_name}"]').first.click(timeout=3000)
            time.sleep(wait_s)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] toolbar(%s) 클릭 실패: %s", data_name, e)
            return False

    def _is_toolbar_active(self, data_name: str) -> bool:
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
        current = self._is_toolbar_active(data_name)
        if current == want_active:
            return True
        return self._toolbar_click(data_name, wait_s=wait_s)

    def get_image_count(self) -> int:
        try:
            return self.page.locator(".se-image").count()
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 이미지 개수 조회 실패: %s", e)
            return -1

    def insert_image(self, path_or_url: str) -> bool:
        before = self.get_image_count()
        try:
            if Path(path_or_url).exists():
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

    def reset_formatting(self) -> None:
        for name in ("bold", "italic", "underline", "strikethrough"):
            if self._is_toolbar_active(name):
                self._toolbar_click(name, wait_s=0.1)

    def set_category(self, name_or_no: str) -> bool:
        try:
            self.page.locator('.category_select, button:has-text("카테고리")').first.click(timeout=2000)
            time.sleep(0.5)
            try:
                self.page.locator(f'[data-category-no="{name_or_no}"]').first.click(timeout=1500)
            except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                self.page.get_by_text(name_or_no, exact=True).first.click(timeout=2000)
            time.sleep(0.5)
            _log.info("[blog-writer] 카테고리 선택: %s", name_or_no)
            return True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.warning("[blog-writer] 카테고리 선택 실패: %s", e)
            return False

    def _is_publish_panel_open(self) -> bool:
        try:
            return self.page.locator('.layer_popup__i0QOY.is_show__TMSLq, input[placeholder*="태그"]').first.is_visible(
                timeout=500
            )
        except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            return False

    def _open_publish_panel(self) -> bool:
        if self._is_publish_panel_open():
            return True
        try:
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
        try:
            return self.page.locator('[class*="tag"]').first.inner_text(timeout=2000)
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("[blog-writer] 태그 목록 조회 실패: %s", e)
            return ""

    def set_tags(self, tags: list[str]) -> bool:
        if not self._open_publish_panel():
            _log.warning("[blog-writer] 태그 추가 실패: 발행 패널을 열 수 없음")
            return False
        try:
            tag_input = self.page.locator('input[placeholder*="태그"]').first
            tag_input.click(timeout=2000)

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
        return self._set_publish_checkbox("publish-option-comment", allowed, "댓글")

    def set_search_exposure(self, allowed: bool = True) -> bool:
        return self._set_publish_checkbox("publish-option-search", allowed, "검색노출")

    def _set_publish_checkbox(self, cb_id: str, want: bool, label: str) -> bool:
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
        try:
            self.page.locator('button:has-text("저장")').first.click(timeout=3000)
            time.sleep(2)
            _log.info("[blog-writer] 임시저장 완료")
            return {"ok": True, "mode": "draft"}
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.error("[blog-writer] 임시저장 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def publish(self, wait_verify_s: int = 8) -> dict:
        try:
            self._open_publish_panel()

            try:
                self.page.locator('[class*="confirm_btn"]').click(timeout=3000)
            except Exception:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                try:
                    self.page.get_by_role("button", name="발행", exact=True).last.click(timeout=3000)
                except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
                    _log.debug("발행 버튼(fallback) 클릭 실패(무시): %s", e)

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

    # ── 검증 ────────────────────────────────────────────────────────────

    def verify_published(self) -> dict:
        current = self.page.url
        m = re.search(
            r"blog\.naver\.com/(?:PostView\.naver\?.*blogId=([^&]+).*[?&]logNo=(\d+)|([a-zA-Z0-9_-]+)/(\d{10,}))",
            current,
        )

        title_text = ""
        try:
            title_text = self.page.title()
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("페이지 타이틀 조회 실패(무시): %s", e)

        result_text = ""
        try:
            result_text = self.page.evaluate("() => (document.body?.innerText || '').substring(0, 500)")
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("본문 텍스트 조회 실패(무시): %s", e)

        success = bool(m) or "발행" in result_text or "완료" in result_text

        log_no = ""
        blog_id = ""
        if m:
            if m.group(1):
                blog_id = m.group(1)
                log_no = m.group(2)
            else:
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
        else:
            _log.warning("[blog-writer] 발행 검증 실패 — URL: %s", current)
        return result


# ── 편의 함수 ──────────────────────────────────────────────────────────────


def _install_dialog_handler(page: Page) -> None:
    """네이버 에디터 dialog 를 자동 dismiss 하는 핸들러를 페이지당 1회 설치."""
    if not getattr(page, "_haehan_dialog_handler_installed", False):
        page.on("dialog", lambda d: d.dismiss())
        try:
            page._haehan_dialog_handler_installed = True
        except Exception as e:  # noqa: BLE001 - 브라우저 자동화 — Playwright 실패는 원인이 다양해(타임아웃/요소없음/네비게이션 등) 종류를 좁히지 않고 일괄 로그 후 폴백, 결제·인증·DB삭제 등 위험 조작 없음(2026-09-28 검토)
            _log.debug("dialog handler 플래그 설정 실패(무시): %s", e)


def _write_post_content(
    bw: BlogWriter, body: str | list[str], images: list[str] | None, body_segments: list[str] | None
) -> dict | None:
    """본문(+이미지) 입력. 실패하면 오류 dict, 성공이면 None."""
    if body_segments and images:
        blocks: list[dict[str, str]] = []
        for i, seg in enumerate(body_segments):
            blocks.append({"type": "text", "value": seg})
            if i < len(images):
                blocks.append({"type": "image", "value": images[i]})
        if not bw.write_mixed_content(blocks):
            return {"ok": False, "error": "body_segments_failed"}
    elif images:
        for img in images:
            bw.insert_image(img)
        if not bw.write_body(body):
            return {"ok": False, "error": "body_failed"}
    else:
        if not bw.write_body(body):
            return {"ok": False, "error": "body_failed"}
    return None


def write_post(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    page: Page,
    *,
    title: str,
    body: str | list[str],
    category: str | None = None,
    tags: list[str] | None = None,
    images: list[str] | None = None,
    body_segments: list[str] | None = None,
    visibility: str = "public",
    comments_allowed: bool = True,
    search_exposure: bool = True,
    save_draft_only: bool = False,
    require_approval: bool = False,
) -> dict:
    """원샷 글 작성 + 발행/저장.

    require_approval 기본값을 원본(True)에서 False로 바꿨다 — 이 앱은 사람이
    옆에서 지켜보는 회사 내부 자동화가 아니라, 고객이 프로그램에 예약을 걸어두면
    무인으로 발행되는 걸 기대하는 제품이라 승인 대기 모드가 기본이면 안 된다.
    """
    _install_dialog_handler(page)

    # Step 1: 로그인 확인 — 자동 로그인 시도 없음(비밀번호 미보관)
    login_result = check_login(page)
    if not login_result.get("ok"):
        return {"ok": False, "error": "login_required", "reason": login_result.get("hint", "")}

    body_str = "\n\n".join(body) if isinstance(body, list) else body
    tags = tags or []

    bw = BlogWriter(page)
    if not bw.open():
        return {"ok": False, "error": "editor_open_failed"}

    if not bw.set_title(title):
        return {"ok": False, "error": "title_failed"}

    content_error = _write_post_content(bw, body, images, body_segments)
    if content_error is not None:
        return content_error

    if save_draft_only:
        result = bw.save_draft()
        result["tags_used"] = tags
        return result

    page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
    time.sleep(1.5)

    if category:
        bw.set_category(category)
    if tags:
        bw.set_tags(tags)
    bw.set_visibility(visibility)
    bw.set_comments_allowed(comments_allowed)
    bw.set_search_exposure(search_exposure)

    if require_approval:
        _log.info("[write_post] 발행 승인 대기 — confirm_publish(page) 호출로 발행")
        return {
            "ok": True,
            "mode": "awaiting_approval",
            "approval_required": True,
            "summary": {
                "title": title,
                "tags": tags,
                "visibility": visibility,
                "body_preview": body_str[:120].strip(),
                "images": images or [],
                "category": category,
            },
            "next_step": "confirm_publish(page) 호출 시 발행 완료",
        }

    result = bw.publish()
    result["tags_used"] = tags
    return result


def confirm_publish(page: Page, wait_verify_s: int = 8) -> dict:
    """발행 패널이 열린 상태에서 최종 발행 버튼을 클릭한다(require_approval=True로 쓴 경우)."""
    bw = BlogWriter(page)
    result = bw.publish(wait_verify_s=wait_verify_s)
    if result.get("ok"):
        _log.info("[confirm_publish] 발행 완료: %s", result.get("url"))
    else:
        _log.error("[confirm_publish] 발행 실패: %s", result.get("error"))
    return result
