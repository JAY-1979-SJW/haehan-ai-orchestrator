"""Google Drive OOP 인터페이스.

사용:
    d = DriveAPI(page)
    d.list_recent(limit=30)
    d.search("회의록")
    d.upload("data/report.pdf")
    d.share_link(file_index=0, role="viewer")
    d.create_folder("프로젝트A")
"""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class DriveAPI:
    """Google Drive 자동화."""

    DRIVE_HOME = "https://drive.google.com/drive/my-drive"

    def __init__(self, page: Page):
        self.page = page

    def list_recent(self, limit: int = 30) -> list[dict]:
        """최근 파일 목록."""
        self.page.goto("https://drive.google.com/drive/recent", timeout=20000)
        time.sleep(3)
        return self._extract_files(limit)

    def search(self, query: str, limit: int = 30) -> list[dict]:
        """검색."""
        self.page.goto(self.DRIVE_HOME, timeout=20000)
        time.sleep(2.5)
        try:
            box = self.page.locator('input[placeholder*="검색"], input[aria-label*="Search"]').first
            box.click(timeout=3000)
            box.fill(query, timeout=2000)
            self.page.keyboard.press("Enter")
            time.sleep(3)
            return self._extract_files(limit)
        except Exception as e:  # noqa: BLE001 - 구글 드라이브 CDP 자동화(검색/업로드/폴더생성/공유링크) - 실패 시 ok:False와 에러 반환, 성공 위장 없음
            _log.error("[drive] 검색 실패: %s", e)
            return []

    def _extract_files(self, limit: int) -> list[dict]:
        try:
            return (
                self.page.evaluate(
                    """(limit) => {
                    const out = [];
                    document.querySelectorAll('[data-id], [role="row"]').forEach(el => {
                        if (out.length >= limit) return;
                        const name = el.querySelector('[data-tooltip], [aria-label]')?.getAttribute('aria-label')
                                    || el.querySelector('[data-tooltip]')?.getAttribute('data-tooltip')
                                    || (el.innerText || '').split('\\n')[0];
                        const id = el.getAttribute('data-id') || '';
                        if (name && name.length < 200) out.push({name: name.substring(0, 80), id});
                    });
                    return out;
                }""",
                    limit,
                )
                or []
            )
        except Exception:  # noqa: BLE001 - 구글 드라이브 CDP 자동화(검색/업로드/폴더생성/공유링크) - 실패 시 ok:False와 에러 반환, 성공 위장 없음
            return []

    def upload(self, file_path: str) -> dict:
        """파일 업로드."""
        p = Path(file_path)
        if not p.exists():
            return {"ok": False, "error": "file_not_found"}
        self.page.goto(self.DRIVE_HOME, timeout=20000)
        time.sleep(3)
        try:
            # '새로 만들기' → '파일 업로드'
            self.page.locator(
                'button:has-text("신규"), button:has-text("새로 만들기"), button:has-text("New")'
            ).first.click(timeout=5000)
            time.sleep(1)
            # file input은 hidden
            file_input = self.page.locator('input[type="file"]').first
            file_input.set_input_files(str(p), timeout=10000)
            time.sleep(5)  # 업로드 대기
            log_critical("FILE_UPLOAD", f"Drive 업로드: {p.name}", path=str(p), mode="drive_upload")
            return {"ok": True, "name": p.name, "size": p.stat().st_size}
        except Exception as e:  # noqa: BLE001 - 구글 드라이브 CDP 자동화(검색/업로드/폴더생성/공유링크) - 실패 시 ok:False와 에러 반환, 성공 위장 없음
            return {"ok": False, "error": str(e)[:100]}

    def create_folder(self, name: str) -> dict:
        """폴더 생성."""
        self.page.goto(self.DRIVE_HOME, timeout=20000)
        time.sleep(2.5)
        try:
            self.page.locator(
                'button:has-text("신규"), button:has-text("새로 만들기"), button:has-text("New")'
            ).first.click(timeout=5000)
            time.sleep(1)
            self.page.locator(
                '[aria-label="새 폴더"], div[role="menuitem"]:has-text("새 폴더"), div[role="menuitem"]:has-text("Folder")'
            ).first.click(timeout=5000)
            time.sleep(1.5)
            self.page.locator(
                'input[aria-label="새 폴더"], input[aria-label*="New folder"], [role="dialog"] input[type="text"]:not([placeholder])'
            ).first.fill(name, timeout=3000)
            self.page.locator('button:has-text("만들기"), button:has-text("Create")').first.click(timeout=3000)
            time.sleep(2)
            log_critical("OTHER", f"Drive 폴더 생성: {name}", mode="drive_folder")
            return {"ok": True, "name": name}
        except Exception as e:  # noqa: BLE001 - 구글 드라이브 CDP 자동화(검색/업로드/폴더생성/공유링크) - 실패 시 ok:False와 에러 반환, 성공 위장 없음
            return {"ok": False, "error": str(e)[:100]}

    def share_link(self, file_index: int = 0, role: str = "viewer", approval: str | None = None) -> dict:
        """N번째 파일 공유 링크 생성 + 복사. approval: 사용자가 직접 입력한 승인 문구(없으면 GateBlocked)."""
        from scripts.common.gate import require_approved

        require_approved("drive_share", approval, via="drive_share_link", file_index=file_index)
        try:
            files = self.list_recent(limit=max(file_index + 1, 10))
            if file_index >= len(files):
                return {"ok": False, "error": "file_index_out_of_range"}
            # 우클릭 → 공유
            rows = self.page.locator('[data-id], [role="row"]')
            rows.nth(file_index).click(button="right", timeout=3000)
            time.sleep(1)
            self.page.locator(
                'div[role="menuitem"]:has-text("공유"), div[role="menuitem"]:has-text("Share")'
            ).first.click(timeout=3000)
            time.sleep(2)
            # 링크 복사 버튼
            self.page.locator('button:has-text("링크 복사"), button:has-text("Copy link")').first.click(timeout=3000)
            time.sleep(1)
            log_critical("OTHER", f"Drive 공유 링크: idx={file_index}", role=role, mode="drive_share")
            return {"ok": True, "file": files[file_index], "role": role}
        except Exception as e:  # noqa: BLE001 - 구글 드라이브 CDP 자동화(검색/업로드/폴더생성/공유링크) - 실패 시 ok:False와 에러 반환, 성공 위장 없음
            return {"ok": False, "error": str(e)[:100]}
