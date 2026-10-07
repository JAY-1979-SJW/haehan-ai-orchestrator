"""Shared constants, dataclasses, and private helpers for workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.google.common import surfaces

ROOT = Path(__file__).resolve().parents[3]
LATEST_ACTION_CATALOG = ROOT / "data" / "google_work_action_catalog_latest.json"
ACTION_CATALOG_DIR = ROOT / "data" / "google_work_action_catalogs"
LATEST_PREPARE = ROOT / "data" / "google_prepare_latest.json"
PREPARE_DIR = ROOT / "data" / "google_prepares"
EXECUTION_DIR = ROOT / "data" / "google_execution_results"
LATEST_ADAPTER_CATALOG = ROOT / "data" / "google_execution_adapter_catalog_latest.json"
ADAPTER_CATALOG_DIR = ROOT / "data" / "google_execution_adapter_catalogs"
VERIFICATION_DIR = ROOT / "data" / "google_execution_verifications"
LATEST_UNDEVELOPED_REPORT = ROOT / "data" / "google_work_undeveloped_latest.json"
UNDEVELOPED_REPORT_DIR = ROOT / "data" / "google_work_undeveloped_reports"

APPROVAL_PHRASE = "GOOGLE_APPROVED_EXECUTE"


@dataclass(frozen=True)
class GoogleWorkAction:
    key: str
    surface_key: str
    label: str
    operation: str
    target_url: str
    risk: str
    requires_approval: bool
    required_inputs: list[str]
    prepare_outputs: list[str]
    execute_mode: str
    status: str
    approval_phrase: str = APPROVAL_PHRASE


@dataclass(frozen=True)
class GoogleExecutionAdapter:
    action_key: str
    adapter_key: str
    adapter_type: str
    execute_mode: str
    implementation_status: str
    final_state_policy: str
    browser_target_url: str
    evidence_required: list[str]
    verification_checks: list[str]
    rollback_notes: list[str]


def _surface_map() -> dict[str, dict]:
    return {item["key"]: item for item in surfaces.build_surface_catalog()["surfaces"]}


def _redact_values(values: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    secret_markers = ("password", "token", "secret", "cookie", "key")
    for key, value in values.items():
        if any(marker in key.lower() for marker in secret_markers):
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted


def _adapter_key(action: GoogleWorkAction) -> str:
    explicit = {
        "gmail_send_email": "gmail_send_adapter",
        "youtube_studio_upload_video": "youtube_studio_upload_adapter",
        "youtube_studio_edit_video_metadata": "youtube_studio_metadata_adapter",
        "cloud_iam_change_role": "google_cloud_iam_adapter",
        "cloud_create_api_credential": "google_cloud_credentials_adapter",
        "play_console_prepare_release": "google_play_release_adapter",
        "search_console_submit_indexing": "search_console_indexing_adapter",
        "ai_studio_create_api_key": "ai_studio_key_adapter",
    }
    return explicit.get(action.key, f"{action.surface_key}_{action.operation}_adapter")


def _adapter_type(execute_mode: str) -> str:
    if execute_mode.startswith("cli_or_api"):
        return "cli_or_api_approval_adapter"
    if execute_mode.startswith("cli_or_browser"):
        return "cli_or_browser_approval_adapter"
    if execute_mode.startswith("api_preferred"):
        return "api_preferred_browser_handoff_adapter"
    return "browser_handoff_adapter"


def _adapter_profile_for_action(action: GoogleWorkAction) -> GoogleExecutionAdapter:
    if not action.requires_approval:
        return GoogleExecutionAdapter(
            action_key=action.key,
            adapter_key="google_read_surface_adapter",
            adapter_type="browser_readonly",
            execute_mode=action.execute_mode,
            implementation_status="complete",
            final_state_policy="read_only",
            browser_target_url=action.target_url,
            evidence_required=["current_url", "page_title", "visible_surface_marker"],
            verification_checks=["target_url_reached", "no_state_change", "audit_record_saved"],
            rollback_notes=["no rollback required for read-only navigation"],
        )
    adapter_key = _adapter_key(action)
    final_policy = (
        "approval_handoff_final_click_required"
        if "browser" in action.execute_mode or "handoff" in action.execute_mode
        else "approval_required_before_cli_or_api_execution"
    )
    return GoogleExecutionAdapter(
        action_key=action.key,
        adapter_key=adapter_key,
        adapter_type=_adapter_type(action.execute_mode),
        execute_mode=action.execute_mode,
        implementation_status="complete_gated_contract",
        final_state_policy=final_policy,
        browser_target_url=action.target_url,
        evidence_required=[
            "prepared_payload",
            "approval_phrase",
            "account_or_project_context",
            "final_confirmation_marker",
            "audit_record_saved",
        ],
        verification_checks=[
            "approved_flag_present",
            "approval_phrase_matched",
            "missing_inputs_empty",
            "state_change_false_until_final_confirmation",
            "result_artifact_saved",
        ],
        rollback_notes=[
            "record target surface before final confirmation",
            "capture confirmation result after final click/API call",
            "use surface rollback plan from prepare_outputs when supported",
        ],
    )


def _open_target_readonly(url: str) -> dict:
    try:
        from scripts.browser.cdp.connection import get_page

        page = get_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        title = ""
        try:
            title = page.title()
        except Exception:  # noqa: BLE001 - 구글 워크플로우 공통 유틸(읽기 전용 타겟 오픈) -- 제목 조회 실패는 빈 문자열로 폴백, 오픈 자체 실패는 ok=False 결과로 반환(fail-closed)
            title = ""
        return {
            "attempted": True,
            "ok": True,
            "url": page.url,
            "title": title,
            "mode": "readonly_target_open",
        }
    except Exception as exc:  # noqa: BLE001 - 구글 워크플로우 공통 유틸(읽기 전용 타겟 오픈) -- 제목 조회 실패는 빈 문자열로 폴백, 오픈 자체 실패는 ok=False 결과로 반환(fail-closed)
        return {
            "attempted": True,
            "ok": False,
            "error": str(exc),
            "mode": "readonly_target_open",
        }
