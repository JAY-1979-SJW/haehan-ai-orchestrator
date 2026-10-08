"""live_inputs 설정/상수/env 헬퍼 (공유 leaf).

경로 상수, 어댑터/모드 집합, env 기반 타임아웃 헬퍼. 다른 live_inputs 함수를
호출하지 않는 leaf. [docs/module_separation_standard.md]
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from scripts.google.common import workflows

ROOT = Path(__file__).resolve().parents[3]
LIVE_INPUT_DIR = ROOT / "data" / "google_live_inputs"
LATEST_LIVE_INPUT = ROOT / "data" / "google_live_input_latest.json"
LIVE_INPUT_MANIFEST_DIR = ROOT / "data" / "google_live_input_manifests"
LATEST_LIVE_INPUT_MANIFEST = ROOT / "data" / "google_live_input_manifest_latest.json"
LIVE_INPUT_COVERAGE_DIR = ROOT / "data" / "google_live_input_coverage"
LATEST_LIVE_INPUT_COVERAGE = ROOT / "data" / "google_live_input_coverage_latest.json"
LIVE_INPUT_ADAPTERS = {
    action.key: "safe_domain_specific_prefill" for action in workflows.WRITE_ACTIONS
}
LIVE_INPUT_ADAPTERS.update({
    "gmail_send_email": "safe_pre_final_input",
    "cloud_iam_change_role": "safe_pre_final_input",
    "search_console_submit_indexing": "safe_pre_final_input",
    "youtube_studio_upload_video": "safe_pre_final_input",
    "youtube_studio_edit_video_metadata": "safe_domain_specific_lookup_prefill",
    "search_console_submit_sitemap": "safe_pre_final_input",
    "ai_studio_create_api_key": "safe_secret_issue_final_click_ready",
    "cloud_create_api_credential": "safe_secret_issue_final_click_ready",
    "play_console_prepare_release": "safe_release_final_click_ready",
})
DOMAIN_SPECIFIC_PREFILL_MODES = {
    "safe_pre_final_input",
    "safe_secret_issue_final_click_ready",
    "safe_release_final_click_ready",
    "safe_domain_specific_prefill",
    "safe_domain_specific_lookup_prefill",
}
GENERIC_HANDOFF_MODES = {
    "safe_generic_input_handoff",
}
PARTIAL_HANDOFF_MODES = {
    "safe_handoff_no_create",
    "safe_handoff_no_release",
    "safe_lookup_handoff",
}
FINAL_CONTROL_LABELS = (
    "Send",
    "보내기",
    "Publish",
    "게시",
    "Next",
    "다음",
    "Submit",
    "제출",
    "Save",
    "저장",
    "Create",
    "만들기",
    "Grant",
    "Add",
    "Request indexing",
    "색인 생성 요청",
    "Release",
    "출시",
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.1, float(raw))
    except ValueError:
        return default


def _page_timeout(default_ms: int = 45000) -> int:
    return max(default_ms, _env_int("HAEHAN_GOOGLE_LIVE_INPUT_TIMEOUT_MS", 180000))


def _page_wait(page: Any, milliseconds: int) -> None:
    multiplier = _env_float("HAEHAN_GOOGLE_LIVE_INPUT_WAIT_MULTIPLIER", 1.5)
    page.wait_for_timeout(int(milliseconds * multiplier))


def _locator_timeout(default_ms: int) -> int:
    return max(default_ms, _env_int("HAEHAN_GOOGLE_LIVE_INPUT_LOCATOR_TIMEOUT_MS", 15000))


def _cdp_wait(session: Any, seconds: float) -> None:
    multiplier = _env_float("HAEHAN_GOOGLE_LIVE_INPUT_WAIT_MULTIPLIER", 1.5)
    session.wait(seconds * multiplier)


def _cdp_websocket_timeout() -> float:
    return _env_float("HAEHAN_GOOGLE_LIVE_INPUT_CDP_TIMEOUT_SEC", 60.0)


def _direct_cdp_first() -> bool:
    raw = os.environ.get("HAEHAN_GOOGLE_LIVE_INPUT_DIRECT_CDP_FIRST", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}
