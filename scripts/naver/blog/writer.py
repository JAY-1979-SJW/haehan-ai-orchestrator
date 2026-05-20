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
  from scripts.web_connector import get_page

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

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from scripts.logger import get_logger
from scripts.critical_logger import log_critical

_log = get_logger(__name__)

WRITE_URL = "https://blog.naver.com/PostWriteForm.naver"

# SE3(SmartEditor One)는 iframe 없이 메인 페이지에 직접 렌더링.
# 제목: .se-section-documentTitle  본문: .se-section-text
TITLE_SEL = ".se-section-documentTitle"
BODY_SEL  = ".se-section-text"

VISIBILITY_MAP = {
    "public": "2",       # 전체공개 (실제 라디오 value 검증 완료 2026-05-19)
    "neighbors": "1",    # 이웃공개
    "mutual": "3",       # 서로이웃공개
    "private": "0",      # 비공개
}


class BlogWriter:
    """네이버 블로그 SmartEditor3 자동화 작성기.

    SE3는 iframe 없이 메인 페이지에 직접 렌더링.
    blogId 파라미터 필수 — 없으면 "유효하지 않은 요청" 오류 발생.
    """

    def __init__(self, page: Page):
        self.page = page
        self._draft_handled = False

    # ── 초기화 ──────────────────────────────────────────────────────────

    def open(self, blog_id: str | None = None, timeout_ms: int = 30000,
             auto_login: bool = True,
             naver_id: str | None = None, naver_pw: str | None = None) -> bool:
        """편집기 페이지 열기 + 자동 로그인 + 편집기 준비 대기."""
        _log.info("[blog-writer] 편집기 열기 (blog_id=%s)", blog_id)

        # blogId 없으면 로그인 사용자 ID 자동 감지
        if not blog_id:
            blog_id = self._detect_blog_id()

        if not blog_id:
            _log.error("[blog-writer] blog_id 확인 불가 — 로그인 필요")
            return False

        url = f"{WRITE_URL}?blogId={blog_id}"
        self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        time.sleep(3)

        # 로그인 확인 — 글쓰기 페이지 접근 실패 시 자동 로그인
        if auto_login and "유효하지 않은" in (self.page.content() or ""):
            try:
                from scripts.naver.auth import ensure_naver_login
                result = ensure_naver_login(self.page)
                if not result.get("ok"):
                    _log.error("[blog-writer] 자동 로그인 실패: %s", result.get("reason"))
                    return False
                self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                time.sleep(3)
            except Exception as e:
                _log.warning("[blog-writer] 자동 로그인 처리 실패: %s", e)

        # 편집기 준비 대기 (SE3: .se-section-documentTitle)
        try:
            self.page.wait_for_selector(TITLE_SEL, timeout=15000, state="visible")
            _log.info("[blog-writer] 편집기 준비 완료")
        except Exception as e:
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
            self.page.goto("https://section.blog.naver.com/BlogHome.naver",
                           wait_until="domcontentloaded", timeout=10000)
            time.sleep(1.5)
            href = self.page.evaluate("""() => {
                const a = document.querySelector('a[href*=\"admin.blog.naver.com/\"]');
                return a ? a.href : null;
            }""")
            if href:
                m = re.search(r"admin\.blog\.naver\.com/([a-zA-Z0-9_]+)", href)
                if m:
                    _id = m.group(1)
                    if _id not in ("stat", "category", "manage"):
                        return _id
        except Exception as e:
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
            popup = self.page.locator(".se-popup-alert")
            if popup.is_visible(timeout=2000):
                cancel_btn = popup.locator(".se-popup-button-cancel").first
                cancel_btn.click(timeout=2000)
                # 팝업이 DOM에서 제거될 때까지 대기 (최대 3초)
                try:
                    popup.wait_for(state="hidden", timeout=3000)
                except Exception:
                    pass
                _log.info("[blog-writer] 임시저장 복원 다이얼로그 취소 완료")
                time.sleep(0.5)
        except Exception as e:
            _log.debug("[blog-writer] 다이얼로그 없음 또는 처리 무시: %s", e)
        finally:
            self._draft_handled = True

    # ── 제목/본문 ────────────────────────────────────────────────────────

    def set_title(self, text: str) -> bool:
        """제목 입력."""
        try:
            self.page.locator(TITLE_SEL).first.click(timeout=3000)
            time.sleep(0.3)
            self.page.keyboard.type(text, delay=20)
            time.sleep(0.5)
            _log.info("[blog-writer] 제목 입력: %s", text[:30])
            return True
        except Exception as e:
            _log.error("[blog-writer] 제목 입력 실패: %s", e)
            return False

    def write_body(self, text: str | list[str], paragraph_delay: float = 0.3) -> bool:
        """본문 입력. 클립보드 붙여넣기 방식 (빠르고 서식 오염 없음).

        text가 list면 단락 단위 순서 입력.
        \n\n = 단락 구분, \n = 줄바꿈 (SE3가 자동 처리).
        """
        try:
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
            except (ImportError, Exception):
                # fallback: 단락 단위 keyboard.type
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

            _log.info("[blog-writer] 본문 입력 완료 (%d 자)", len(full_text))
            return True
        except Exception as e:
            _log.error("[blog-writer] 본문 입력 실패: %s", e)
            return False

    # ── 편집 도구 연동 (SE3 data-name 기준, 2026-05-19 툴바 전수 검증) ──────

    def _toolbar_click(self, data_name: str, wait_s: float = 0.5) -> bool:
        """data-name 기준 툴바 버튼 클릭 공통 헬퍼."""
        try:
            self.page.locator(f'button[data-name="{data_name}"]').first.click(timeout=3000)
            time.sleep(wait_s)
            return True
        except Exception as e:
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
        except Exception as e:
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
            result = self.page.evaluate("""(names) => {
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
            }""", toggle_buttons)
            return {
                "bold": result.get("bold", {}).get("active", False),
                "italic": result.get("italic", {}).get("active", False),
                "underline": result.get("underline", {}).get("active", False),
                "strikethrough": result.get("strikethrough", {}).get("active", False),
                "detail": result,
            }
        except Exception as e:
            _log.debug("[blog-writer] get_editor_state 실패: %s", e)
            return {"bold": False, "italic": False, "underline": False, "strikethrough": False}

    def insert_image(self, path_or_url: str) -> bool:
        """사진 삽입 — 로컬 파일 또는 URL.

        로컬 파일: expect_file_chooser로 OS 다이얼로그 가로채기 (화면에 열리지 않음).
        URL: oglink 방식 fallback.
        """
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
            return True
        except Exception as e:
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
                self.page.locator("button.nvu_local, button.nvu_btn_append.nvu_local, button.nvu_btn_local").first.click(timeout=3000)

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
            except Exception:
                pass

            if description:
                try:
                    self.page.locator("textarea.nvu_inp").first.fill(description, timeout=2000)
                    time.sleep(0.3)
                except Exception:
                    pass

            # 완료 버튼 클릭 → 에디터 삽입
            self.page.locator("button.nvu_btn_submit").first.click(timeout=3000)
            time.sleep(3.0)

            _log.info("[blog-writer] 영상 삽입 완료: %s", video_title)
            return True
        except Exception as e:
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
            opts = self.page.locator('.se-insert-quotation-option, [class*=quotation-option], [class*=select-option]')
            count = opts.count()
            if count > style:
                opts.nth(style).click(timeout=1500)
                time.sleep(0.3)
            self.page.keyboard.type(text, delay=15)
            _log.info("[blog-writer] 인용구 삽입")
            return True
        except Exception as e:
            _log.debug("[blog-writer] 인용구 실패: %s", e)
            return False

    def insert_divider(self, style: int = 0) -> bool:
        """구분선 삽입. style=0~N (종류 선택)."""
        try:
            self._toolbar_click("horizontal-line", wait_s=0.5)
            opts = self.page.locator('[class*=horizontal-line-option], [class*=select-option]')
            count = opts.count()
            if count > style:
                opts.nth(style).click(timeout=1500)
            _log.info("[blog-writer] 구분선 삽입")
            return True
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
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
        """글자 크기 변경."""
        try:
            self._toolbar_click("font-size", wait_s=0.4)
            inp = self.page.locator('input[class*=font-size], .se-font-size-input').first
            inp.fill(str(size), timeout=2000)
            self.page.keyboard.press("Enter")
            time.sleep(0.3)
            _log.info("[blog-writer] 글자 크기: %d", size)
            return True
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
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
                except Exception:
                    pass
            self.page.keyboard.type(code, delay=10)
            _log.info("[blog-writer] 코드 블록 삽입")
            return True
        except Exception as e:
            _log.debug("[blog-writer] 코드 블록 실패: %s", e)
            return False

    def spellcheck(self) -> bool:
        """맞춤법 검사 실행 (data-name=speller)."""
        return self._toolbar_click("speller", wait_s=1.0)

    # ── 발행 패널 옵션 ────────────────────────────────────────────────────

    def set_category(self, name_or_no: str) -> bool:
        """카테고리 선택."""
        try:
            self.page.locator('.category_select, button:has-text("카테고리")').first.click(timeout=2000)
            time.sleep(0.5)
            try:
                self.page.locator(f'[data-category-no="{name_or_no}"]').first.click(timeout=1500)
            except Exception:
                self.page.get_by_text(name_or_no, exact=True).first.click(timeout=2000)
            time.sleep(0.5)
            _log.info("[blog-writer] 카테고리 선택: %s", name_or_no)
            return True
        except Exception as e:
            _log.warning("[blog-writer] 카테고리 선택 실패: %s", e)
            return False

    def set_tags(self, tags: list[str]) -> bool:
        """태그 추가."""
        try:
            tag_input = self.page.locator('input[placeholder*="태그"]').first
            tag_input.click(timeout=2000)
            for t in tags:
                self.page.keyboard.type(t, delay=20)
                self.page.keyboard.press("Enter")
                time.sleep(0.2)
            _log.info("[blog-writer] 태그 %d개 추가", len(tags))
            return True
        except Exception as e:
            _log.warning("[blog-writer] 태그 추가 실패: %s", e)
            return False

    def set_visibility(self, level: str = "public") -> bool:
        """공개 설정."""
        if level not in VISIBILITY_MAP:
            _log.error("[blog-writer] 잘못된 공개설정: %s", level)
            return False
        try:
            value = VISIBILITY_MAP[level]
            try:
                self.page.locator(f'input[name="visibility"][value="{value}"]').first.click(timeout=1500)
            except Exception:
                label_map = {"public": "전체공개", "neighbors": "이웃공개", "mutual": "서로이웃공개", "private": "비공개"}
                self.page.get_by_text(label_map[level], exact=True).first.click(timeout=2000)
            _log.info("[blog-writer] 공개설정: %s", level)
            return True
        except Exception as e:
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
            cb = self.page.locator(f'#{cb_id}').first
            if cb.is_checked(timeout=1500) != want:
                cb.click(timeout=1500)
                time.sleep(0.2)
            _log.info("[blog-writer] %s %s", label, "허용" if want else "거부")
            return True
        except Exception as e:
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
        except Exception as e:
            _log.error("[blog-writer] 임시저장 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def publish(self, wait_verify_s: int = 8) -> dict:
        """즉시 발행 + 검증. 상단 '발행' 버튼(exact) → 패널 내 confirm_btn 순서."""
        try:
            # 1) 상단 발행 버튼 (exact=True: "예약 발행" 버튼과 구분)
            try:
                self.page.get_by_role("button", name="발행", exact=True).click(timeout=3000)
                time.sleep(1.5)
            except Exception:
                pass

            # 2) 패널 내 최종 발행 버튼 (.confirm_btn__WEaBq 또는 텍스트 fallback)
            try:
                self.page.locator('[class*="confirm_btn"]').click(timeout=3000)
            except Exception:
                self.page.get_by_role("button", name="발행", exact=True).last.click(timeout=3000)
            time.sleep(wait_verify_s)

            return self.verify_published()
        except Exception as e:
            _log.error("[blog-writer] 발행 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def schedule_publish(self, when: datetime) -> dict:
        """예약 발행."""
        try:
            try:
                self.page.locator('button:has-text("발행")').first.click(timeout=3000)
                time.sleep(1.5)
            except Exception:
                pass

            self.page.locator('input[type="radio"][value="reserve"], label:has-text("예약")').first.click(timeout=2000)
            time.sleep(0.5)

            self.page.locator('input[type="date"], input.date_input').first.fill(when.strftime("%Y-%m-%d"), timeout=2000)
            self.page.locator('input[type="time"], input.time_input').first.fill(when.strftime("%H:%M"), timeout=2000)
            time.sleep(0.5)

            self.page.locator('button:has-text("예약"), button.confirm:has-text("발행")').first.click(timeout=3000)
            time.sleep(5)

            _log.info("[blog-writer] 예약 발행: %s", when)
            log_critical("OTHER", "블로그 예약 발행", scheduled_at=when.isoformat(), mode="blog_schedule")
            return {"ok": True, "mode": "scheduled", "scheduled_at": when.isoformat()}
        except Exception as e:
            _log.error("[blog-writer] 예약 발행 실패: %s", e)
            return {"ok": False, "error": str(e)}

    # ── 검증 ────────────────────────────────────────────────────────────

    def verify_published(self) -> dict:
        """발행 성공 검증 + 게시물 URL 반환."""
        current = self.page.url
        m = re.search(r"blog\.naver\.com/(?:PostView\.naver\?blogId=([^&]+)&logNo=(\d+)|([a-zA-Z0-9_-]+)/(\d{10,}))", current)

        title_text = ""
        try:
            title_text = self.page.title()
        except Exception:
            pass

        result_text = ""
        try:
            result_text = self.page.evaluate("() => (document.body?.innerText || '').substring(0, 500)")
        except Exception:
            pass

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

def write_post(page: Page, *,
               title: str,
               body: str | list[str],
               category: str | None = None,
               tags: list[str] | None = None,
               auto_tags: bool = True,
               brand_tags: list[str] | None = None,
               images: list[str] | None = None,
               visibility: str = "public",
               comments_allowed: bool = True,
               search_exposure: bool = True,
               save_draft_only: bool = False,
               require_approval: bool = True,
               schedule_at: datetime | None = None) -> dict:
    """원샷 글 작성 + 발행/저장.

    Args:
        page: Playwright Page (CDP 연결된 로그인 상태)
        title: 제목
        body: 본문 (str 또는 단락 list)
        category: 카테고리 이름 또는 번호
        tags: 태그 리스트. None이고 auto_tags=True이면 자동 생성.
        auto_tags: True면 tags=None 일 때 suggest_tags() 자동 호출
        brand_tags: 브랜드 고정 태그 (suggest_tags에 전달)
        images: 본문 시작에 삽입할 이미지 경로/URL 리스트
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

    # Step 1: 로그인 확인
    from scripts.naver.auth import ensure_naver_login
    login_result = ensure_naver_login(page)
    if not login_result.get("ok"):
        return {"ok": False, "error": "login_failed", "reason": login_result.get("reason", "")}

    # Step 2: 태그 자동 생성 (tags 미지정 시)
    body_str = "\n\n".join(body) if isinstance(body, list) else body
    if tags is None and auto_tags:
        try:
            from scripts.naver.blog.tag_suggester import suggest_tags
            tags = suggest_tags(title, body_str, brand_tags=brand_tags)
            _log.info("[write_post] 태그 자동 생성: %s", tags)
        except Exception as e:
            _log.warning("[write_post] 태그 자동 생성 실패 (무시): %s", e)
            tags = []

    bw = BlogWriter(page)
    if not bw.open():
        return {"ok": False, "error": "editor_open_failed"}

    if not bw.set_title(title):
        return {"ok": False, "error": "title_failed"}

    if images:
        for img in images:
            bw.insert_image(img)

    if not bw.write_body(body):
        return {"ok": False, "error": "body_failed"}

    # 임시저장만
    if save_draft_only:
        result = bw.save_draft()
        result["tags_used"] = tags or []
        return result

    # 예약 발행
    if schedule_at:
        page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
        _t.sleep(1.5)
        if category:
            bw.set_category(category)
        if tags:
            bw.set_tags(tags)
        bw.set_visibility(visibility)
        return bw.schedule_publish(schedule_at)

    # 발행 패널 열기 + 옵션 세팅
    page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
    _t.sleep(1.5)

    if category:
        bw.set_category(category)
    if tags:
        bw.set_tags(tags)
    bw.set_visibility(visibility)
    bw.set_comments_allowed(comments_allowed)
    bw.set_search_exposure(search_exposure)

    # 승인 게이트 — 패널 열린 상태 유지, 사용자 승인 대기
    if require_approval:
        _log.info("[write_post] 발행 승인 대기 — confirm_publish(page) 호출로 발행")
        log_critical("OTHER", "블로그 발행 승인 요청",
                     title=title[:40], visibility=visibility,
                     tags=tags or [], mode="blog_awaiting_approval")
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

    # 즉시 발행 (require_approval=False)
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
