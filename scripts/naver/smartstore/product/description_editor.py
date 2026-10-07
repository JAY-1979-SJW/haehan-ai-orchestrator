"""스마트스토어 상품 상세설명 에디터 모듈 (L3 Connector).

SmartEditor ONE (#/editor) 전체 기능 모듈화:
  - 텍스트 입력 / 서식 (굵게, 기울이기, 정렬, 글자색 등)
  - 콘텐츠 블록 (사진, 동영상, 표, HTML, 인용구, 구분선, 링크)
  - 도구 (템플릿, 글감검색, 라이브러리, 맞춤법)
  - AI 상품설명 작성
  - 저장 / 등록

사용:
    from scripts.naver.smartstore.product.description_editor import SmartEditorSession

    ed = SmartEditorSession(page)
    ed.open()                          # 에디터 진입
    ed.write_text("고품질 소재로 제작된...")
    ed.insert_image("/tmp/product.jpg")
    ed.apply_html("<h2>특징</h2><p>...</p>")
    ed.submit()                        # 등록 버튼
"""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.logger import get_logger

_log = get_logger(__name__)

EDITOR_URL = "https://sell.smartstore.naver.com/#/editor"

# ── 에디터 툴바 셀렉터 ─────────────────────────────────────────────────────────


class EditorSelectors:
    """SmartEditor ONE 툴바 버튼 셀렉터."""

    # ── 콘텐츠 블록 툴바 ────────────────────────────────────────────────────
    BTN_IMAGE = ".se-image-toolbar-button"
    BTN_VIDEO = ".se-video-toolbar-button"
    BTN_QUOTE = ".se-document-toolbar-icon-select-button"  # 인용구
    BTN_DIVIDER = "button[class*='se-document-toolbar-icon-select-button']:nth-of-type(3)"
    BTN_LOCATION = ".se-map-toolbar-button"
    BTN_LINK = ".se-oglink-toolbar-button"
    BTN_TABLE = ".se-table-toolbar-button"
    BTN_HTML = ".se-shopping-html-toolbar-button"

    # ── 텍스트 서식 툴바 ────────────────────────────────────────────────────
    BTN_BOLD = ".se-bold-toolbar-button"
    BTN_ITALIC = ".se-italic-toolbar-button"
    BTN_UNDERLINE = ".se-underline-toolbar-button"
    BTN_STRIKE = ".se-strikethrough-toolbar-button"
    BTN_TEXT_COLOR = "button[class*='se-property-toolbar-color-picker-button']:first-of-type"
    BTN_BG_COLOR = "button[class*='se-property-toolbar-color-picker-button']:last-of-type"
    BTN_ALIGN = "button[class*='se-property-toolbar-drop-down-button']:first-of-type"
    BTN_LINE_HEIGHT = "button[class*='se-property-toolbar-drop-down-button']:nth-of-type(2)"
    BTN_LIST = "button[class*='se-property-toolbar-drop-down-button']:last-of-type"
    BTN_SPECIAL = ".se-special-letter-toolbar-button"
    BTN_INLINE_LINK = ".se-link-toolbar-button"
    BTN_SPELL = ".se-speller-toolbar-button"
    BTN_FONT_SIZE = ".se-font-size-code-toolbar-button"
    BTN_FORMAT = ".se-text-format-toolbar-button"

    # ── 도구 ────────────────────────────────────────────────────────────────
    BTN_SEARCH = ".se-search-toolbar-button"  # 글감 검색
    BTN_LIBRARY = ".se-library-toolbar-button"  # 라이브러리
    BTN_TEMPLATE = ".se-template-toolbar-button"  # 템플릿

    # ── 저장 ────────────────────────────────────────────────────────────────
    BTN_SUBMIT = "button.btn-primary.progress-button"  # 등록
    BTN_VIEW_MODE = ".se-util-button.__mode-button"  # PC/모바일 전환

    # ── 에디터 본문 ─────────────────────────────────────────────────────────
    EDITOR_BODY = ".se-main-container .se-component-content"
    EDITOR_ROOT = ".se-main-container"
    CONTENT_AREA = "[contenteditable='true']"

    # ── HTML 붙여넣기 입력창 ────────────────────────────────────────────────
    HTML_TEXTAREA = "textarea[placeholder*='입력해주세요']"
    HTML_CONFIRM = "button:has-text('변환')"

    # ── 이미지 업로드 ─────────────────────────────────────────────────────
    IMAGE_FILE_INPUT = "input[type='file']"
    IMAGE_URL_INPUT = "input[placeholder*='URL']"

    # ── AI 작성 ────────────────────────────────────────────────────────────
    AI_BTN = "button:has-text('AI 상품설명 작성하기')"
    AI_KEYWORD_INPUT = "input[placeholder*='키워드'], textarea[placeholder*='키워드']"
    AI_GENERATE_BTN = "button:has-text('생성'), button:has-text('작성하기')"
    AI_APPLY_BTN = "button:has-text('적용'), button:has-text('사용하기')"


SEL = EditorSelectors()


# ── 에디터 세션 ───────────────────────────────────────────────────────────────


class SmartEditorSession:
    """SmartEditor ONE 전체 기능 통합 세션.

    에디터가 열려 있는 상태 (URL: #/editor) 에서 동작합니다.
    open()을 호출하면 등록 폼에서 에디터를 열고 진입합니다.
    """

    def __init__(self, page: Page):
        self.page = page
        self.text = TextToolbar(page)
        self.block = BlockToolbar(page)
        self.tool = ToolToolbar(page)
        self.ai = AIWriter(page)
        self._opened = False

    # ── 진입 ─────────────────────────────────────────────────────────────────

    def open(self, from_register_form: bool = True) -> bool:
        """에디터 열기.

        Args:
            from_register_form: True면 등록 폼에서 '스마트에디터' 버튼 클릭
                                 False면 현재 URL이 #/editor인지만 확인
        """
        if "#/editor" in self.page.url:
            self._opened = True
            return True

        if from_register_form:
            return self._click_editor_btn()
        return False

    def _click_editor_btn(self) -> bool:
        """등록 폼에서 '스마트 에디터 ONE 으로 작성' 클릭.

        2026-08-26 실측 확정: 이 버튼은 **같은 탭에서 라우트 전환되지 않고
        새 탭(팝업)을 연다.** 예전 코드는 `self.page.url`이 바뀌길 폴링했는데,
        실제 전환은 원래 탭이 아니라 새로 열린 탭에서 일어나므로 항상
        "에디터 URL 전환 타임아웃"으로 실패했다(원본 폼 탭과 에디터 탭이
        서로 다른 탭으로 쪼개져 이후 "등록" 시 "화면이 종료됨" 에러로 이어짐).

        `context.expect_page()`로 새 탭을 확실히 캡처하고, 이 세션이 다루는
        `self.page`/toolbar 들을 **새 탭으로 교체**한다.
        """
        coords = self.page.evaluate("""
        () => {
            for (const el of document.querySelectorAll("button")) {
                const txt = (el.innerText||"").trim();
                if (txt.includes("스마트 에디터") || txt.includes("스마트에디터")) {
                    el.scrollIntoView({block: 'center'});
                    const r = el.getBoundingClientRect();
                    if (r.width > 0)
                        return { x: Math.round(r.x + r.width/2),
                                 y: Math.round(r.y + r.height/2) };
                }
            }
            return null;
        }
        """)
        if not coords:
            _log.error("[editor] 스마트에디터 버튼 없음")
            return False

        try:
            with self.page.context.expect_page(timeout=10000) as new_page_info:
                self.page.mouse.click(coords["x"], coords["y"])
            new_page = new_page_info.value
            new_page.wait_for_load_state()
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            _log.error("[editor] 새 탭 캡처 실패: %s", str(e)[:120])
            return False

        deadline = time.time() + 10
        while time.time() < deadline:
            if "#/editor" in new_page.url:
                self.page = new_page
                self.text = TextToolbar(new_page)
                self.block = BlockToolbar(new_page)
                self.tool = ToolToolbar(new_page)
                self.ai = AIWriter(new_page)
                _log.info("[editor] 에디터 진입 완료 (새 탭으로 전환됨)")
                self._opened = True
                return True
            time.sleep(0.5)
        _log.error("[editor] 새 탭은 열렸으나 #/editor 전환 타임아웃: %s", new_page.url)
        return False

    def _ensure_open(self) -> bool:
        if not self._opened:
            return self.open()
        return "#/editor" in self.page.url

    # ── 본문 텍스트 입력 ──────────────────────────────────────────────────────

    def write_text(self, text: str) -> dict:
        """에디터 본문에 텍스트 입력."""
        if not self._ensure_open():
            return {"ok": False, "error": "에디터 미진입"}
        try:
            # contenteditable 영역 클릭 후 타이핑
            body = self.page.locator(SEL.CONTENT_AREA).first
            if body.count() == 0:
                body = self.page.locator(SEL.EDITOR_BODY).first
            body.click(timeout=5000)
            time.sleep(0.3)
            self.page.keyboard.type(text, delay=30)
            _log.info("[editor] 텍스트 입력: %d자", len(text))
            return {"ok": True, "chars": len(text)}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}

    def write_paragraph(self, text: str) -> dict:
        """텍스트 입력 후 단락 구분 (Enter)."""
        r = self.write_text(text)
        if r["ok"]:
            self.page.keyboard.press("Enter")
        return r

    # ── 저장 ─────────────────────────────────────────────────────────────────

    def submit(self, require_confirm: bool = True) -> dict:
        """등록 버튼 클릭 (에디터 → 등록 폼으로 저장 후 복귀)."""
        if require_confirm:
            ans = input("[SmartEditorSession] 상세설명을 저장하겠습니까? (yes 입력): ").strip()
            if ans.lower() != "yes":
                return {"ok": False, "reason": "사용자 취소"}
        try:
            btn = self.page.locator(SEL.BTN_SUBMIT).first
            if btn.count() > 0 and btn.is_visible(timeout=3000):
                btn.click(timeout=5000)
                time.sleep(2)
                _log.info("[editor] 등록 버튼 클릭")
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "등록 버튼 없음"}

    def toggle_view_mode(self) -> dict:
        """PC/모바일 화면 전환."""
        try:
            btn = self.page.locator(SEL.BTN_VIEW_MODE).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "뷰모드 버튼 없음"}


# ── 텍스트 서식 툴바 ─────────────────────────────────────────────────────────


class TextToolbar:
    """텍스트 서식 기능 모음."""

    def __init__(self, page: Page):
        self.page = page

    def _click(self, sel: str, label: str = "") -> dict:
        try:
            el = self.page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=2000):
                el.click(timeout=3000)
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": f"{label or sel} 버튼 없음"}

    def bold(self) -> dict:
        return self._click(SEL.BTN_BOLD, "굵게")

    def italic(self) -> dict:
        return self._click(SEL.BTN_ITALIC, "기울이기")

    def underline(self) -> dict:
        return self._click(SEL.BTN_UNDERLINE, "밑줄")

    def strikethrough(self) -> dict:
        return self._click(SEL.BTN_STRIKE, "취소선")

    def spellcheck(self) -> dict:
        return self._click(SEL.BTN_SPELL, "맞춤법")

    def font_size(self, size: int) -> dict:
        """글자 크기 변경."""
        try:
            btn = self.page.locator(SEL.BTN_FONT_SIZE).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                time.sleep(0.3)
                # 드롭다운에서 size 선택
                opt = self.page.get_by_text(str(size), exact=True).first
                if opt.count() > 0:
                    opt.click(timeout=3000)
                    return {"ok": True, "size": size}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "글자크기 변경 실패"}

    def align(self, direction: str = "left") -> dict:
        """정렬 설정 (left/center/right/justify)."""
        label_map = {"left": "왼쪽", "center": "가운데", "right": "오른쪽", "justify": "양쪽"}
        label = label_map.get(direction, direction)
        try:
            btn = self.page.locator(SEL.BTN_ALIGN).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                time.sleep(0.3)
                opt = self.page.get_by_text(label).first
                if opt.count() > 0:
                    opt.click(timeout=3000)
                    return {"ok": True, "align": direction}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "정렬 변경 실패"}

    def set_format(self, fmt: str = "본문") -> dict:
        """문단 서식 (본문/제목1/제목2/소제목)."""
        try:
            btn = self.page.locator(SEL.BTN_FORMAT).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                time.sleep(0.3)
                opt = self.page.get_by_text(fmt).first
                if opt.count() > 0:
                    opt.click(timeout=3000)
                    return {"ok": True, "format": fmt}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": f"서식 {fmt} 적용 실패"}


# ── 콘텐츠 블록 툴바 ─────────────────────────────────────────────────────────


class BlockToolbar:
    """콘텐츠 블록 삽입 기능 모음."""

    def __init__(self, page: Page):
        self.page = page

    def _click_btn(self, sel: str, label: str = "") -> dict:
        try:
            el = self.page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=2000):
                el.click(timeout=3000)
                time.sleep(0.5)
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": f"{label} 버튼 없음"}

    def insert_image_file(self, image_path: str) -> dict:
        """사진 블록 → 파일 업로드."""
        p = Path(image_path)
        if not p.exists():
            return {"ok": False, "error": f"파일 없음: {image_path}"}

        r = self._click_btn(SEL.BTN_IMAGE, "사진 추가")
        if not r["ok"]:
            return r
        time.sleep(1)

        try:
            file_input = self.page.locator(SEL.IMAGE_FILE_INPUT).first
            if file_input.count() > 0:
                file_input.set_input_files(str(p), timeout=10000)
                time.sleep(3)
                _log.info("[editor] 이미지 업로드: %s", p.name)
                return {"ok": True, "filename": p.name}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "파일 input 없음"}

    def insert_image_url(self, url: str) -> dict:
        """사진 블록 → URL 입력."""
        r = self._click_btn(SEL.BTN_IMAGE, "사진 추가")
        if not r["ok"]:
            return r
        time.sleep(1)

        try:
            inp = self.page.locator(SEL.IMAGE_URL_INPUT).first
            if inp.count() > 0:
                inp.fill(url, timeout=5000)
                self.page.keyboard.press("Enter")
                time.sleep(1)
                return {"ok": True, "url": url}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "URL 입력창 없음"}

    def insert_html(self, html: str) -> dict:
        """HTML 블록 삽입 (HTML 첨부 버튼)."""
        r = self._click_btn(SEL.BTN_HTML, "HTML 첨부")
        if not r["ok"]:
            return r
        time.sleep(1)

        try:
            ta = self.page.locator(SEL.HTML_TEXTAREA).first
            if ta.count() > 0:
                ta.fill(html, timeout=5000)
                confirm = self.page.locator(SEL.HTML_CONFIRM).first
                if confirm.count() > 0:
                    confirm.click(timeout=3000)
                    time.sleep(0.5)
                    _log.info("[editor] HTML 삽입: %d자", len(html))
                    return {"ok": True, "html_length": len(html)}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "HTML 입력창 없음"}

    def insert_divider(self) -> dict:
        """구분선 삽입."""
        return self._click_btn(SEL.BTN_DIVIDER, "구분선")

    def insert_table(self, rows: int = 3, cols: int = 3) -> dict:
        """표 삽입 (기본 3×3)."""
        r = self._click_btn(SEL.BTN_TABLE, "표 추가")
        if not r["ok"]:
            return r
        time.sleep(0.5)
        # 표 크기 선택 (그리드 클릭) — 셀렉터가 동적이므로 좌표 기반
        try:
            grid = self.page.locator(".se-table-grid-item").nth((rows - 1) * 10 + (cols - 1))
            if grid.count() > 0:
                grid.click(timeout=3000)
                return {"ok": True, "rows": rows, "cols": cols}
        except Exception:  # noqa: BLE001 - 표 크기 등 부가 옵션 자동 선택 실패 — 기본값으로 진행 가능(2026-09-28 검토)
            pass
        return {"ok": True, "note": "표 크기 자동 선택 실패 — 직접 선택 필요"}

    def insert_link(self, url: str, text: str = "") -> dict:
        """링크(OG) 블록 삽입."""
        r = self._click_btn(SEL.BTN_LINK, "링크 추가")
        if not r["ok"]:
            return r
        time.sleep(0.5)
        try:
            inp = self.page.locator("input[placeholder*='URL'], input[placeholder*='주소']").first
            if inp.count() > 0:
                inp.fill(url, timeout=5000)
                self.page.keyboard.press("Enter")
                time.sleep(1)
                return {"ok": True, "url": url}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "URL 입력창 없음"}

    def insert_video(self, url: str) -> dict:
        """동영상 블록 삽입 (YouTube/Naver TV URL)."""
        r = self._click_btn(SEL.BTN_VIDEO, "동영상 추가")
        if not r["ok"]:
            return r
        time.sleep(0.5)
        try:
            inp = self.page.locator("input[placeholder*='URL'], input[placeholder*='주소']").first
            if inp.count() > 0:
                inp.fill(url, timeout=5000)
                self.page.keyboard.press("Enter")
                time.sleep(1)
                return {"ok": True, "url": url}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "동영상 URL 입력창 없음"}

    def insert_quote(self, text: str = "") -> dict:
        """인용구 블록 삽입."""
        r = self._click_btn(SEL.BTN_QUOTE, "인용구")
        if not r["ok"]:
            return r
        if text:
            time.sleep(0.3)
            self.page.keyboard.type(text, delay=20)
        return {"ok": True}


# ── 도구 툴바 ─────────────────────────────────────────────────────────────────


class ToolToolbar:
    """에디터 도구 모음 (템플릿, 글감검색, 라이브러리)."""

    def __init__(self, page: Page):
        self.page = page

    def open_template(self) -> dict:
        """템플릿 패널 열기."""
        try:
            btn = self.page.locator(SEL.BTN_TEMPLATE).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                time.sleep(0.5)
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "템플릿 버튼 없음"}

    def select_template(self, idx: int = 0) -> dict:
        """템플릿 패널에서 n번째 템플릿 선택."""
        r = self.open_template()
        if not r["ok"]:
            return r
        time.sleep(1)
        try:
            items = self.page.locator("[class*='template-item'], [class*='se-template']")
            if items.count() > idx:
                items.nth(idx).click(timeout=3000)
                time.sleep(1)
                return {"ok": True, "template_idx": idx}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "템플릿 항목 없음"}

    def search_content(self, keyword: str) -> dict:
        """글감 검색."""
        try:
            btn = self.page.locator(SEL.BTN_SEARCH).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                time.sleep(0.5)
                inp = self.page.locator("input[placeholder*='검색']").first
                if inp.count() > 0:
                    inp.fill(keyword, timeout=5000)
                    self.page.keyboard.press("Enter")
                    time.sleep(1)
                    return {"ok": True, "keyword": keyword}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "글감 검색 실패"}

    def open_library(self) -> dict:
        """라이브러리(내 이미지) 패널 열기."""
        try:
            btn = self.page.locator(SEL.BTN_LIBRARY).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                time.sleep(0.5)
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "라이브러리 버튼 없음"}


# ── AI 상품설명 작성기 ────────────────────────────────────────────────────────


class AIWriter:
    """네이버 AI 상품설명 작성하기 Beta.

    사용:
        ai = AIWriter(page)
        ai.generate(keywords=["LED 조명", "무드등"])
        ai.apply()
    """

    def __init__(self, page: Page):
        self.page = page

    def open(self) -> dict:
        """AI 작성 패널 열기."""
        try:
            btn = self.page.locator(SEL.AI_BTN).first
            if btn.count() > 0 and btn.is_visible(timeout=3000):
                btn.click(timeout=5000)
                time.sleep(1)
                _log.info("[editor-ai] AI 작성 패널 열림")
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "AI 버튼 없음"}

    def generate(self, keywords: list[str]) -> dict:
        """키워드 입력 후 AI 생성 실행."""
        r = self.open()
        if not r["ok"]:
            return r
        time.sleep(0.5)

        # 키워드 입력
        try:
            inp = self.page.locator(SEL.AI_KEYWORD_INPUT).first
            if inp.count() > 0:
                inp.fill(", ".join(keywords), timeout=5000)
                time.sleep(0.3)
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"키워드 입력 실패: {e}"}

        # 생성 버튼 클릭
        try:
            btn = self.page.locator(SEL.AI_GENERATE_BTN).first
            if btn.count() > 0:
                btn.click(timeout=5000)
                _log.info("[editor-ai] AI 생성 시작: %s", keywords)
                # 생성 대기 (최대 30초)
                deadline = time.time() + 30
                while time.time() < deadline:
                    apply_btn = self.page.locator(SEL.AI_APPLY_BTN).first
                    if apply_btn.count() > 0 and apply_btn.is_visible(timeout=500):
                        return {"ok": True, "status": "generated"}
                    time.sleep(1)
                return {"ok": False, "error": "AI 생성 타임아웃"}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"생성 버튼 클릭 실패: {e}"}
        return {"ok": False, "error": "생성 버튼 없음"}

    def apply(self) -> dict:
        """생성된 AI 내용 적용."""
        try:
            btn = self.page.locator(SEL.AI_APPLY_BTN).first
            if btn.count() > 0 and btn.is_visible(timeout=3000):
                btn.click(timeout=5000)
                time.sleep(1)
                _log.info("[editor-ai] AI 내용 적용 완료")
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트에디터 툴바/콘텐츠 조작 — 각 동작 실패는 항상 {ok: False, error} 로 반환해 호출부가 판단, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "적용 버튼 없음"}

    def generate_and_apply(self, keywords: list[str]) -> dict:
        """생성 + 적용 원샷."""
        r = self.generate(keywords)
        if not r["ok"]:
            return r
        return self.apply()
