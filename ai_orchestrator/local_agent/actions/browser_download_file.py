"""browser.download_file — 공개/비로그인 첨부파일 다운로드 (1차 구현).

- 사용자 승인 불필요 (AUTO_ALLOWED)
- 사후 evidence 저장 (saved_path, file_size, signature)
- 쿠키/session/storage_state 추출 안 함
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.local_agent.action_registry import register_handler
from ai_orchestrator.local_agent.action_evidence_collector import collect_evidence

ACTION_NAME = "browser.download_file"


def _file_signature(path: str) -> str:
    if not os.path.exists(path):
        return "MISSING"
    if os.path.getsize(path) == 0:
        return "EMPTY"
    with open(path, "rb") as f:
        head = f.read(8)
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "HWP_OLE2"
    if head[:4] == b"PK\x03\x04":
        return "ZIP_OR_HWPX"
    if head[:4] == b"%PDF":
        return "PDF"
    h = head.lower()
    if h.startswith(b"<!doc") or h.startswith(b"<html") or b"<html" in h:
        return "HTML_RESPONSE"
    return "UNKNOWN"


def execute(
    source_url: str,
    out_dir: str,
    expected_filename: str = "",
    timeout_seconds: int = 30,
    headless: bool = True,
) -> dict[str, Any]:
    """
    공개 URL을 headless Playwright로 다운로드.
    실패 시 verdict로 분류.
    """
    if not source_url:
        return {"ok": False, "verdict": "ERROR", "error": "source_url 필요"}
    os.makedirs(out_dir, exist_ok=True)

    started = datetime.now(timezone.utc)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "verdict": "PLAYWRIGHT_NOT_AVAILABLE"}

    raw: dict[str, Any] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            try:
                with page.expect_download(timeout=timeout_seconds * 1000) as dl_info:
                    try:
                        page.goto(source_url, timeout=timeout_seconds * 1000,
                                  wait_until="domcontentloaded")
                    except Exception:
                        pass
                download = dl_info.value
                fname = expected_filename or download.suggested_filename or "downloaded"
                fname = fname.replace("/", "_").replace("\\", "_")[:200]
                save_path = os.path.join(out_dir, fname)
                download.save_as(save_path)

                raw["saved_path"] = save_path
                raw["file_size"] = os.path.getsize(save_path) if os.path.exists(save_path) else 0
                raw["signature"] = _file_signature(save_path)
                raw["downloaded_at"] = datetime.now(timezone.utc).isoformat()
                raw["ok"] = True
                raw["verdict"] = "DOWNLOAD_SUCCESS"
            except Exception as e:
                raw["ok"] = False
                raw["verdict"] = "DOWNLOAD_FAILED"
                raw["error"] = f"{type(e).__name__}: {str(e)[:100]}"
            finally:
                # cookies/storage_state 절대 추출 안 함
                pass
        finally:
            browser.close()

    evidence = collect_evidence(ACTION_NAME, raw)
    raw["evidence"] = evidence
    return raw


# registry 등록
register_handler(ACTION_NAME, execute)
