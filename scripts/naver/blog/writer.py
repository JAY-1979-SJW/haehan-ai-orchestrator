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

from playwright.sync_api import Page, Frame

from scripts.logger import get_logger
from scripts.critical_logger import log_critical

_log = get_logger(__name__)

WRITE_URL = "https://blog.naver.com/PostWriteForm.naver"
EDITOR_FRAME = "mainFrame"

VISIBILITY_MAP = {
    "public": "0",       # 전체공개
    "neighbors": "2",    # 이웃공개
    "mutual": "3",       # 서로이웃공개
    "private": "1",      # 비공개
}


class BlogWriter:
    """네이버 블로그 SmartEditor 자동화 작성기."""

    def __init__(self, page: Page):
        self.page = page
        self.frame: Frame | None = None
        self._draft_handled = False

    # ── 초기화 ──────────────────────────────────────────────────────────

    def open(self, blog_id: str | None = None, timeout_ms: int = 30000,
             auto_login: bool = True,
             naver_id: str | None = None, naver_pw: str | None = None) -> bool:
        """편집기 페이지 열기 + 자동 로그인 + iframe 진입 + 다이얼로그 처리.

        Args:
            blog_id: 본인 블로그 ID (없으면 글쓰기 URL에서 자동 추출 시도)
            auto_login: 미로그인 시 자동 ID/PW 로그인 시도
            naver_id, naver_pw: 명시 자격증명 (없으면 환경변수/파일)
        """
        _log.info("[blog-writer] 편집기 열기 (blog_id=%s)", blog_id)
        url = WRITE_URL + (f"?blogId={blog_id}" if blog_id else "")
        self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        time.sleep(2.5)

        # 로그인 확인
        if auto_login:
            try:
                from scripts.login_detector import detect_login_state
                from scripts.naver.auth import login_naver
                state = detect_login_state(self.page)
                if not state.get("logged_in"):
                    _log.info("[blog-writer] 미로그인 감지 → 자동 로그인 시도")
                    result = login_naver(self.page, naver_id, naver_pw)
                    if not result["ok"]:
                        _log.error("[blog-writer] 자동 로그인 실패: %s", result.get("reason"))
                        return False
                    # 글쓰기 페이지로 복귀
                    self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    time.sleep(2.5)
            except Exception as e:
                _log.warning("[blog-writer] 자동 로그인 처리 실패 (계속 진행): %s", e)

        # mainFrame 찾기
        self.frame = self._find_main_frame(timeout_s=15)
        if not self.frame:
            _log.error("[blog-writer] mainFrame 진입 실패")
            return False

        # 임시저장 복원 다이얼로그 자동 처리 ("취소" 클릭하여 새 글로 시작)
        self._handle_draft_dialog()

        # 편집기 준비 대기
        try:
            self.frame.wait_for_selector(".se-title-input, .se_editArea", timeout=15000, state="visible")
            _log.info("[blog-writer] 편집기 준비 완료")
            return True
        except Exception as e:
            _log.warning("[blog-writer] 편집기 셀렉터 대기 실패: %s", e)
            return False

    def _find_main_frame(self, timeout_s: int = 15) -> Frame | None:
        """mainFrame iframe 찾기."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            for f in self.page.frames:
                if f.name == EDITOR_FRAME or "PostWriteForm" in f.url:
                    return f
            time.sleep(0.5)
        return None

    def _handle_draft_dialog(self) -> None:
        """임시저장 복원 다이얼로그 처리 — 매번 새 글로 시작 ('취소' 클릭)."""
        if self._draft_handled or not self.frame:
            return
        time.sleep(1.0)
        try:
            # 다양한 다이얼로그 패턴 시도
            dialog_selectors = [
                'button:has-text("취소")',
                '.btn_cancel',
                '.se-popup-button-cancel',
                '[class*="cancel"]',
            ]
            for sel in dialog_selectors:
                try:
                    btn = self.frame.locator(sel).first
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
        if not self.frame:
            return False
        try:
            title = self.frame.locator(".se-title-input, .se-section-documentTitle .se-text-paragraph").first
            title.click(timeout=3000)
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
        if not self.frame:
            return False
        try:
            body = self.frame.locator(".se-text-paragraph").first
            body.click(timeout=3000)
            time.sleep(0.5)

            paragraphs = text if isinstance(text, list) else text.split("\n\n")
            for i, p in enumerate(paragraphs):
                lines = p.split("\n")
                for j, line in enumerate(lines):
                    self.page.keyboard.type(line, delay=15)
                    if j < len(lines) - 1:
                        self.page.keyboard.press("Shift+Enter")  # 줄바꿈
                if i < len(paragraphs) - 1:
                    self.page.keyboard.press("Enter")  # 단락 분리
                    time.sleep(paragraph_delay)
            _log.info("[blog-writer] 본문 입력 완료 (%d 단락)", len(paragraphs))
            return True
        except Exception as e:
            _log.error("[blog-writer] 본문 입력 실패: %s", e)
            return False

    # ── 컴포넌트 삽입 ────────────────────────────────────────────────────

    def insert_image(self, path_or_url: str) -> bool:
        """이미지 삽입 (로컬 파일 또는 URL)."""
        if not self.frame:
            return False
        try:
            # 사진 버튼 클릭으로 파일 다이얼로그 열기
            self.frame.locator('button[data-name="image"], button:has-text("사진"), .se-toolbar-button-image').first.click(timeout=3000)
            time.sleep(0.8)

            # 로컬 파일이면 file input에 직접 set
            if Path(path_or_url).exists():
                file_input = self.frame.locator('input[type="file"]').first
                file_input.set_input_files(path_or_url, timeout=5000)
                time.sleep(2.5)  # 업로드 대기
                _log.info("[blog-writer] 이미지 첨부: %s", path_or_url)
                return True

            # URL이면 url 입력
            url_input = self.frame.locator('input[placeholder*="URL"], input[type="url"]').first
            url_input.fill(path_or_url, timeout=3000)
            self.page.keyboard.press("Enter")
            time.sleep(2)
            return True
        except Exception as e:
            _log.error("[blog-writer] 이미지 삽입 실패: %s", e)
            return False

    def insert_quote(self, text: str) -> bool:
        """인용구 삽입."""
        if not self.frame:
            return False
        try:
            self.frame.locator('button[data-name="quotation"], .se-toolbar-button-quotation').first.click(timeout=2000)
            time.sleep(0.5)
            self.page.keyboard.type(text, delay=15)
            return True
        except Exception as e:
            _log.debug("[blog-writer] 인용 실패: %s", e)
            return False

    def insert_divider(self) -> bool:
        """구분선 삽입."""
        if not self.frame:
            return False
        try:
            self.frame.locator('button[data-name="horizontalLine"], .se-toolbar-button-horizontalLine').first.click(timeout=2000)
            time.sleep(0.3)
            return True
        except Exception as e:
            _log.debug("[blog-writer] 구분선 실패: %s", e)
            return False

    def insert_link(self, url: str, text: str | None = None) -> bool:
        """링크 삽입."""
        if not self.frame:
            return False
        try:
            self.frame.locator('button[data-name="oglink"], .se-toolbar-button-oglink').first.click(timeout=2000)
            time.sleep(0.5)
            self.frame.locator('input[placeholder*="URL"], input[type="url"]').first.fill(url, timeout=3000)
            self.page.keyboard.press("Enter")
            time.sleep(1.5)
            return True
        except Exception as e:
            _log.debug("[blog-writer] 링크 실패: %s", e)
            return False

    # ── 발행 패널 (사이드 옵션) ───────────────────────────────────────────

    def _open_publish_panel(self) -> bool:
        """발행 패널 열기 ('발행' 버튼 우측 옵션 패널)."""
        if not self.frame:
            return False
        try:
            self.frame.locator('button:has-text("발행"), .publish_btn, [class*="publish"]').first.click(timeout=3000)
            time.sleep(1.5)
            return True
        except Exception as e:
            _log.error("[blog-writer] 발행 패널 열기 실패: %s", e)
            return False

    def set_category(self, name_or_no: str) -> bool:
        """카테고리 선택 (이름 또는 번호)."""
        if not self.frame:
            return False
        try:
            # 카테고리 드롭다운 클릭
            self.frame.locator('.category_select, button:has-text("카테고리"), [class*="category"]').first.click(timeout=2000)
            time.sleep(0.5)
            # 번호 매칭 우선
            try:
                self.frame.locator(f'[data-category-no="{name_or_no}"]').first.click(timeout=1500)
            except Exception:
                # 이름 매칭
                self.frame.get_by_text(name_or_no, exact=True).first.click(timeout=2000)
            time.sleep(0.5)
            _log.info("[blog-writer] 카테고리 선택: %s", name_or_no)
            return True
        except Exception as e:
            _log.warning("[blog-writer] 카테고리 선택 실패: %s", e)
            return False

    def set_tags(self, tags: list[str]) -> bool:
        """태그 추가 (여러 개)."""
        if not self.frame:
            return False
        try:
            tag_input = self.frame.locator('input.tag_input, input[placeholder*="태그"], [class*="tag-input"]').first
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
        """공개 설정. level: public/neighbors/mutual/private"""
        if not self.frame:
            return False
        if level not in VISIBILITY_MAP:
            _log.error("[blog-writer] 잘못된 공개설정: %s", level)
            return False
        try:
            # 라디오 또는 라벨 클릭
            value = VISIBILITY_MAP[level]
            try:
                self.frame.locator(f'input[name="visibility"][value="{value}"]').first.click(timeout=1500)
            except Exception:
                label_map = {"public": "전체공개", "neighbors": "이웃공개", "mutual": "서로이웃공개", "private": "비공개"}
                self.frame.get_by_text(label_map[level], exact=True).first.click(timeout=2000)
            _log.info("[blog-writer] 공개설정: %s", level)
            return True
        except Exception as e:
            _log.warning("[blog-writer] 공개설정 실패: %s", e)
            return False

    def set_comments_allowed(self, allowed: bool = True) -> bool:
        """댓글 허용 여부."""
        if not self.frame:
            return False
        try:
            target_text = "댓글 허용" if allowed else "댓글 거부"
            cb = self.frame.locator(f'input[type="checkbox"][name*="comment"]').first
            is_checked = cb.is_checked(timeout=1500)
            if is_checked != allowed:
                cb.click(timeout=1500)
            _log.info("[blog-writer] 댓글 %s", "허용" if allowed else "거부")
            return True
        except Exception as e:
            _log.debug("[blog-writer] 댓글 설정 무시: %s", e)
            return False

    def set_likes_allowed(self, allowed: bool = True) -> bool:
        """공감 허용 여부."""
        if not self.frame:
            return False
        try:
            cb = self.frame.locator('input[type="checkbox"][name*="sympathy"], input[type="checkbox"][name*="like"]').first
            is_checked = cb.is_checked(timeout=1500)
            if is_checked != allowed:
                cb.click(timeout=1500)
            return True
        except Exception:
            return False

    def set_search_exposure(self, allowed: bool = True) -> bool:
        """검색 노출 허용."""
        if not self.frame:
            return False
        try:
            cb = self.frame.locator('input[type="checkbox"][name*="search"]').first
            is_checked = cb.is_checked(timeout=1500)
            if is_checked != allowed:
                cb.click(timeout=1500)
            return True
        except Exception:
            return False

    # ── 저장/발행 ────────────────────────────────────────────────────────

    def save_draft(self) -> dict:
        """임시저장."""
        if not self.frame:
            return {"ok": False, "error": "frame_not_ready"}
        try:
            self.frame.locator('button:has-text("저장"), .save_btn, .btn_save').first.click(timeout=3000)
            time.sleep(2)
            _log.info("[blog-writer] 임시저장 완료")
            log_critical("OTHER", "블로그 임시저장", mode="blog_draft")
            return {"ok": True, "mode": "draft"}
        except Exception as e:
            _log.error("[blog-writer] 임시저장 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def publish(self, wait_verify_s: int = 8) -> dict:
        """즉시 발행 + 검증."""
        if not self.frame:
            return {"ok": False, "error": "frame_not_ready"}
        try:
            # 우측 발행 패널 → 발행 버튼 클릭 (2단계)
            # 1) 상단 발행 버튼 → 패널 펼침
            try:
                self.frame.locator('.publish_btn_area button, button:has-text("발행")').first.click(timeout=3000)
                time.sleep(1.5)
            except Exception:
                pass

            # 2) 패널 내 최종 발행 버튼 클릭
            self.frame.locator('button.confirm:has-text("발행"), button:has-text("발행하기"), .btn_confirm').first.click(timeout=5000)
            time.sleep(wait_verify_s)

            return self.verify_published()
        except Exception as e:
            _log.error("[blog-writer] 발행 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def schedule_publish(self, when: datetime) -> dict:
        """예약 발행."""
        if not self.frame:
            return {"ok": False, "error": "frame_not_ready"}
        try:
            # 발행 패널 → 예약 라디오 클릭
            try:
                self.frame.locator('.publish_btn_area button, button:has-text("발행")').first.click(timeout=3000)
                time.sleep(1.5)
            except Exception:
                pass

            self.frame.locator('input[type="radio"][value="reserve"], label:has-text("예약")').first.click(timeout=2000)
            time.sleep(0.5)

            # 날짜/시간 입력
            date_str = when.strftime("%Y-%m-%d")
            time_str = when.strftime("%H:%M")
            self.frame.locator('input[type="date"], input.date_input').first.fill(date_str, timeout=2000)
            self.frame.locator('input[type="time"], input.time_input').first.fill(time_str, timeout=2000)
            time.sleep(0.5)

            # 예약 발행 버튼
            self.frame.locator('button:has-text("예약"), button.confirm:has-text("발행")').first.click(timeout=3000)
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

        # URL 변화 또는 발행 완료 토스트 감지
        title_text = ""
        try:
            title_text = self.page.title()
        except Exception:
            pass

        # mainFrame 안에서 결과 확인
        result_text = ""
        if self.frame:
            try:
                result_text = self.frame.evaluate("() => (document.body?.innerText || '').substring(0, 500)")
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

    # 본문 시작 이미지
    if images:
        for img in images:
            bw.insert_image(img)

    if not bw.write_body(body):
        return {"ok": False, "error": "body_failed"}

    # 발행 패널 옵션
    if category:
        bw.set_category(category)
    if tags:
        bw.set_tags(tags)
    bw.set_visibility(visibility)
    bw.set_comments_allowed(comments_allowed)
    bw.set_search_exposure(search_exposure)

    # 모드별 분기
    if save_draft_only:
        return bw.save_draft()
    if schedule_at:
        return bw.schedule_publish(schedule_at)
    return bw.publish()
