"""browser.download_file — 공개/비로그인 첨부파일 다운로드 (1차 구현).

- 사용자 승인 불필요 (AUTO_ALLOWED)
- 사후 evidence 저장 (saved_path, file_size, signature)
- 쿠키/session/storage_state 추출 안 함
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.agent_hub.action_evidence_collector import collect_evidence
from ai_orchestrator.agent_hub.action_registry import register_handler

ACTION_NAME = "browser.download_file"


def _file_signature(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return "MISSING"
    if p.stat().st_size == 0:
        return "EMPTY"
    with p.open("rb") as f:
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
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    started = datetime.now(UTC)  # noqa: F841

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
                    # goto 실패(리다이렉트 등)는 무시 - 다운로드 이벤트 대기를 계속 진행
                    with contextlib.suppress(Exception):
                        page.goto(source_url, timeout=timeout_seconds * 1000, wait_until="domcontentloaded")
                download = dl_info.value
                fname = expected_filename or download.suggested_filename or "downloaded"
                fname = fname.replace("/", "_").replace("\\", "_")[:200]
                save_path = str(Path(out_dir) / fname)
                download.save_as(save_path)

                raw["saved_path"] = save_path
                raw["file_size"] = Path(save_path).stat().st_size if Path(save_path).exists() else 0
                raw["signature"] = _file_signature(save_path)
                raw["downloaded_at"] = datetime.now(UTC).isoformat()
                raw["ok"] = True
                raw["verdict"] = "DOWNLOAD_SUCCESS"
            except Exception as e:  # noqa: BLE001 - 브라우저 파일 다운로드 액션 -- 리다이렉트 goto 실패는 무시하고 다운로드 이벤트 대기를 계속 진행, 최종 실패는 DOWNLOAD_FAILED로 결과에 기록(쿠키/세션 추출 없음)
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
