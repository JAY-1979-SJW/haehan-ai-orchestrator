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
        """임시저장 복원 다이얼로그 처리 — 새 글로 시작 ('취소' 클릭)."""
        if self._draft_handled:
            return
        time.sleep(1.0)
        try:
            for sel in ['button:has-text("취소")', '.btn_cancel', '.se-popup-button-cancel']:
                try:
                    btn = self.page.locator(sel).first
                    if btn.is_visible(timeout=500):
                        btn.click(timeout=1500)
                        _log.info("[blog-writer] 임시저장 복원 다이얼로그 취소")
                        time.sleep(1)
                        break
                except Exception:
                    continue
            self._draft_handled = True
        except Exception as e:
            _log.debug("[blog-writer] 다이얼로그 처리 무시: %s", e)

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
        """본문 입력. text가 list면 단락 단위로 처리."""
        try:
            self.page.locator(BODY_SEL).first.click(timeout=3000)
            time.sleep(0.5)

            paragraphs = text if isinstance(text, list) else text.split("\n\n")
            for i, p in enumerate(paragraphs):
                lines = p.split("\n")
                for j, line in enumerate(lines):
                    self.page.keyboard.type(line, delay=15)
                    if j < len(lines) - 1:
                        self.page.keyboard.press("Shift+Enter")
                if i < len(paragraphs) - 1:
                    self.page.keyboard.press("Enter")
                    time.sleep(paragraph_delay)
            _log.info("[blog-writer] 본문 입력 완료 (%d 단락)", len(paragraphs))
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

    def insert_image(self, path_or_url: str) -> bool:
        """사진 삽입 — 로컬 파일 또는 URL."""
        try:
            self._toolbar_click("image", wait_s=0.8)
            if Path(path_or_url).exists():
                self.page.locator('input[type="file"]').first.set_input_files(path_or_url, timeout=5000)
                time.sleep(2.5)
                _log.info("[blog-writer] 사진 첨부: %s", path_or_url)
            else:
                self.page.locator('input[placeholder*="URL"], input[type="url"]').first.fill(path_or_url, timeout=3000)
                self.page.keyboard.press("Enter")
                time.sleep(2)
            return True
        except Exception as e:
            _log.error("[blog-writer] 사진 삽입 실패: %s", e)
            return False

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

    def set_bold(self) -> bool:
        """굵게 (Bold) 토글."""
        return self._toolbar_click("bold", wait_s=0.2)

    def set_italic(self) -> bool:
        """기울이기 (Italic) 토글."""
        return self._toolbar_click("italic", wait_s=0.2)

    def set_underline(self) -> bool:
        """밑줄 토글."""
        return self._toolbar_click("underline", wait_s=0.2)

    def set_strikethrough(self) -> bool:
        """취소선 토글."""
        return self._toolbar_click("strikethrough", wait_s=0.2)

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
        """댓글 허용 여부."""
        try:
            cb = self.page.locator('input[type="checkbox"][name*="comment"]').first
            if cb.is_checked(timeout=1500) != allowed:
                cb.click(timeout=1500)
            _log.info("[blog-writer] 댓글 %s", "허용" if allowed else "거부")
            return True
        except Exception as e:
            _log.debug("[blog-writer] 댓글 설정 무시: %s", e)
            return False

    def set_likes_allowed(self, allowed: bool = True) -> bool:
        """공감 허용 여부."""
        try:
            cb = self.page.locator('input[type="checkbox"][name*="sympathy"], input[type="checkbox"][name*="like"]').first
            if cb.is_checked(timeout=1500) != allowed:
                cb.click(timeout=1500)
            return True
        except Exception:
            return False

    def set_search_exposure(self, allowed: bool = True) -> bool:
        """검색 노출 허용."""
        try:
            cb = self.page.locator('input[type="checkbox"][name*="search"]').first
            if cb.is_checked(timeout=1500) != allowed:
                cb.click(timeout=1500)
            return True
        except Exception:
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
               images: list[str] | None = None,
               visibility: str = "public",
               comments_allowed: bool = True,
               search_exposure: bool = True,
               save_draft_only: bool = False,
               schedule_at: datetime | None = None) -> dict:
    """원샷 글 작성 + 발행/저장.

    Args:
        page: Playwright Page (CDP 연결된 로그인 상태)
        title: 제목
        body: 본문 (str 또는 단락 list)
        category: 카테고리 이름 또는 번호
        tags: 태그 리스트
        images: 본문 시작에 삽입할 이미지 경로/URL 리스트
        visibility: public/neighbors/mutual/private
        comments_allowed: 댓글 허용
        search_exposure: 검색 노출
        save_draft_only: True면 임시저장만
        schedule_at: 지정 시 예약 발행
    """
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

    # 임시저장만 할 경우 패널 열기 전에 저장
    if save_draft_only:
        return bw.save_draft()

    # 발행 패널 열기 (태그/공개설정은 패널 안에 있음)
    page.get_by_role("button", name="발행", exact=True).click(timeout=5000)
    import time as _t; _t.sleep(1.5)

    if category:
        bw.set_category(category)
    if tags:
        bw.set_tags(tags)
    bw.set_visibility(visibility)
    bw.set_comments_allowed(comments_allowed)
    bw.set_search_exposure(search_exposure)

    if schedule_at:
        return bw.schedule_publish(schedule_at)
    return bw.publish()
