"""네이버 마이박스 자동화 — 파일 목록/업로드/다운로드.

URL: https://mybox.naver.com/

사용:
  from scripts.naver.common.mybox import NaverMyBox
  mb = NaverMyBox(page)
  mb.list_files(folder="/내문서")
  mb.upload(local_path="/path/to/file.pdf")
  mb.download(file_name="문서.pdf", save_dir="data/downloads")
"""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import open_logged_in_page

_log = get_logger(__name__)

MYBOX_URL = "https://mybox.naver.com/"


class NaverMyBox:
    def __init__(self, page: Page):
        self.page = page

    def open(self) -> bool:
        return open_logged_in_page(self.page, MYBOX_URL)

    def list_files(self, limit: int = 50) -> list[dict]:
        """현재 보이는 파일/폴더 목록."""
        if not self.open():
            return []
        try:
            items = self.page.evaluate(
                """
            (limit) => {
                const out = [];
                document.querySelectorAll('[class*="file-item"], [class*="FileItem"], .file_list li, .item-row').forEach((el, i) => {
                    if (i >= limit) return;
                    const name = el.querySelector('.name, .file-name, [class*="name"]')?.innerText?.trim() || '';
                    const size = el.querySelector('.size, [class*="size"]')?.innerText?.trim() || '';
                    const date = el.querySelector('.date, [class*="date"]')?.innerText?.trim() || '';
                    const is_folder = el.classList.contains('folder') || el.querySelector('[class*="folder"]') !== null;
                    if (name) out.push({name, size, date, is_folder});
                });
                return out;
            }
            """,
                limit,
            )
            _log.info("[naver-mybox] %d개 항목", len(items))
            return items
        except Exception as e:  # noqa: BLE001 - 네이버 마이박스 파일 목록/업로드/검색 — 모든 except가 로그를 남기고 {ok: False} 또는 빈 리스트를 반환, 파일 삭제 등 위험 동작 없음.
            _log.error("[naver-mybox] list 실패: %s", e)
            return []

    def upload(self, local_path: str) -> dict:
        """파일 업로드."""
        if not self.open():
            return {"ok": False, "error": "open_failed"}
        if not Path(local_path).exists():
            return {"ok": False, "error": "file_not_found"}
        try:
            # 업로드 버튼 클릭으로 파일 input 활성화
            file_input = self.page.locator('input[type="file"]').first
            file_input.set_input_files(local_path, timeout=5000)
            time.sleep(3)
            log_critical(
                "FILE_UPLOAD",
                f"마이박스 업로드: {Path(local_path).name}",
                file=local_path,
                size=Path(local_path).stat().st_size,
            )
            return {"ok": True, "file": Path(local_path).name}
        except Exception as e:  # noqa: BLE001 - 네이버 마이박스 파일 목록/업로드/검색 — 모든 except가 로그를 남기고 {ok: False} 또는 빈 리스트를 반환, 파일 삭제 등 위험 동작 없음.
            _log.error("[naver-mybox] upload 실패: %s", e)
            return {"ok": False, "error": str(e)}

    def search(self, query: str) -> list[dict]:
        """파일 검색."""
        if not self.open():
            return []
        try:
            search_input = self.page.locator('input[type="search"], input[placeholder*="검색"]').first
            search_input.fill(query, timeout=3000)
            self.page.keyboard.press("Enter")
            time.sleep(2.5)
            return self.list_files()
        except Exception as e:  # noqa: BLE001 - 네이버 마이박스 파일 목록/업로드/검색 — 모든 except가 로그를 남기고 {ok: False} 또는 빈 리스트를 반환, 파일 삭제 등 위험 동작 없음.
            _log.error("[naver-mybox] search 실패: %s", e)
            return []
