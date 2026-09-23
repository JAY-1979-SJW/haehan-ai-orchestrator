"""Live no-final-submit input adapters for Google workflows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from . import workflows

# CDP 세션/연결은 live_inputs_cdp(공유 leaf)로 분리. 재노출(파사드+내부용).
from .live_inputs_cdp import (  # noqa: F401
    _CDPSessionManager,
    _connect_live_input_cdp,
    _live_input_target_url,
    _new_cdp_target_session,
    _record_direct_cdp_incomplete,
    _safe_cdp_identity,
)

# 설정/상수/env 헬퍼는 live_inputs_config(공유 leaf)로 분리. 전체 재노출(파사드+내부용).
from .live_inputs_config import (  # noqa: F401
    DOMAIN_SPECIFIC_PREFILL_MODES,
    FINAL_CONTROL_LABELS,
    GENERIC_HANDOFF_MODES,
    LATEST_LIVE_INPUT,
    LATEST_LIVE_INPUT_COVERAGE,
    LATEST_LIVE_INPUT_MANIFEST,
    LIVE_INPUT_ADAPTERS,
    LIVE_INPUT_COVERAGE_DIR,
    LIVE_INPUT_DIR,
    LIVE_INPUT_MANIFEST_DIR,
    PARTIAL_HANDOFF_MODES,
    ROOT,
    _cdp_wait,
    _cdp_websocket_timeout,
    _direct_cdp_first,
    _env_float,
    _env_int,
    _locator_timeout,
    _page_timeout,
    _page_wait,
)

# 커버리지 리포트는 live_inputs_coverage(leaf)로 분리. 재노출(파사드).
from .live_inputs_coverage import (  # noqa: F401
    build_live_input_coverage,
    print_live_input_coverage,
    save_live_input_coverage,
)


def run_live_input(plan_path: str | Path, *, no_final_submit: bool = True) -> tuple[dict, Path]:
    """Open the target workflow and fill available inputs without final submit."""
    path = Path(plan_path)
    plan = json.loads(path.read_text(encoding="utf-8"))
    action = plan["action"]
    values = plan.get("provided_inputs", {})
    result = {
        "site_id": "google",
        "action_key": action["key"],
        "started_at": datetime.now(UTC).isoformat(),
        "plan_path": str(path),
        "no_final_submit": no_final_submit,
        "state_change_final_button_clicked": False,
        "status": "started",
        "filled_fields": [],
        "skipped_fields": [],
        "warnings": [],
        "current_url": "",
        "title": "",
    }
    if not no_final_submit:
        result["status"] = "blocked"
        result["warnings"].append("live input requires no_final_submit=True")
        return _save_result(result)
    if plan.get("missing_inputs"):
        result["status"] = "blocked_missing_inputs"
        result["warnings"].append("missing inputs: " + ", ".join(plan["missing_inputs"]))
        return _save_result(result)

    if _direct_cdp_first():
        _dispatch_live_input_direct_cdp(action, values, result)
        if not result["status"].startswith("blocked") and result["status"] != "failed":
            return _save_result(result)
        result["warnings"].append("direct CDP first path was unavailable; retrying Playwright path.")

    try:
        from scripts.web_connector import get_page

        page = get_page()
        _dispatch_live_input(page, action, values, result)
        if _needs_direct_cdp_retry(action, result):
            result["warnings"].append(
                "Playwright path did not verify upload input; retrying direct CDP read-only detection."
            )
            _dispatch_live_input_direct_cdp(action, values, result)
        result["final_control_policy"] = {
            "mode": "no_final_submit",
            "blocked_labels": list(FINAL_CONTROL_LABELS),
            "detected_controls": _detect_final_controls(page),
        }
        try:
            result["current_url"] = page.url
            result["title"] = page.title()
        except Exception:
            pass
        if result["status"] == "started":
            result["status"] = "filled_no_final_submit"
        if action["key"] == "youtube_studio_upload_video" and "video_path" not in result["filled_fields"]:
            result["status"] = "opened_no_upload_input"
            result["warnings"].append("YouTube upload input was not verified; no video was uploaded or published.")
    except Exception as exc:
        result["warnings"].append(f"playwright_live_input_unavailable: {exc}")
        _dispatch_live_input_direct_cdp(action, values, result)
        if action["key"] == "youtube_studio_upload_video" and "video_path" not in result["filled_fields"]:
            result["status"] = "opened_no_upload_input"
            result["warnings"].append("YouTube upload input was not verified; no video was uploaded or published.")
    return _save_result(result)


def run_live_input_manifest(
    manifest_path: str | Path,
    *,
    no_final_submit: bool = True,
) -> tuple[dict, Path]:
    """Run a no-final-submit live-fill manifest and save a combined audit."""
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = manifest.get("items", [])
    summary = {
        "site_id": "google",
        "manifest_path": str(path),
        "started_at": datetime.now(UTC).isoformat(),
        "no_final_submit": no_final_submit,
        "state_change_final_button_clicked": False,
        "items": [],
        "counts": {"total": len(entries), "filled": 0, "blocked": 0, "failed": 0},
        "warnings": [],
    }
    if not no_final_submit:
        summary["status"] = "blocked"
        summary["warnings"].append("manifest live-fill requires no_final_submit=True")
        return _save_manifest_result(summary)
    for index, entry in enumerate(entries, 1):
        item = {"index": index, "status": "started", "action_key": entry.get("action_key", "")}
        try:
            plan_path = entry.get("plan_path")
            if not plan_path:
                action_key = entry["action_key"]
                values = entry.get("values", {})
                _, prepared_path = workflows.prepare_action(action_key, values)
                plan_path = str(prepared_path)
            result, result_path = run_live_input(plan_path, no_final_submit=True)
            item.update(
                {
                    "status": result["status"],
                    "action_key": result["action_key"],
                    "result_path": str(result_path),
                    "filled_fields": result.get("filled_fields", []),
                    "skipped_fields": result.get("skipped_fields", []),
                    "warnings": result.get("warnings", []),
                    "final_clicked": result.get("state_change_final_button_clicked", False),
                }
            )
            if result["status"] in ("filled_no_final_submit", "opened_no_final_submit"):
                summary["counts"]["filled"] += 1
            elif result["status"].startswith("blocked"):
                summary["counts"]["blocked"] += 1
            else:
                summary["counts"]["failed"] += 1
        except Exception as exc:
            item["status"] = "failed"
            item["warnings"] = [str(exc)]
            summary["counts"]["failed"] += 1
        summary["items"].append(item)
    summary["status"] = "completed"
    return _save_manifest_result(summary)


# 실행 결과 요약 출력은 live_inputs_report(leaf)로 분리. 재노출(파사드).
from .live_inputs_report import (  # noqa: F401,E402
    print_live_input_summary,
    print_live_manifest_summary,
)


def _dispatch_live_input(page: Any, action: dict, values: dict, result: dict) -> None:
    key = action["key"]
    mode = LIVE_INPUT_ADAPTERS.get(key, "")
    if key == "gmail_send_email":
        _fill_gmail_send_v2(page, action, values, result)
    elif key == "cloud_iam_change_role":
        _fill_cloud_iam_change(page, action, values, result)
    elif key == "search_console_submit_indexing":
        _fill_search_console_url_inspection(page, action, values, result)
    elif key == "youtube_studio_upload_video":
        _fill_youtube_studio_upload_v2(page, action, values, result)
    elif key == "youtube_studio_edit_video_metadata":
        _fill_youtube_studio_metadata(page, action, values, result)
    elif key == "search_console_submit_sitemap":
        _fill_search_console_sitemap(page, action, values, result)
    elif key == "ai_studio_create_api_key":
        _fill_ai_studio_api_key(page, action, values, result)
    elif key == "cloud_create_api_credential":
        _fill_cloud_api_credential(page, action, values, result)
    elif key == "play_console_prepare_release":
        _fill_play_console_release_handoff(page, action, values, result)
    elif mode in DOMAIN_SPECIFIC_PREFILL_MODES:
        _fill_domain_specific_input_handoff(page, action, values, result)
    elif key in LIVE_INPUT_ADAPTERS:
        _fill_generic_input_handoff(page, action, values, result)
    else:
        _open_only(page, action, values, result)


def _dispatch_live_input_direct_cdp(action: dict, values: dict, result: dict) -> None:
    """Fallback live input path that uses the existing CDP browser directly."""
    session_manager = None
    session = None
    target_action = {**action, "target_url": _live_input_target_url(action, values)}
    try:
        session_manager = _connect_live_input_cdp(target_action, result)
        session = session_manager.__enter__()
        session.goto(target_action["target_url"], wait_idle=False)
        _cdp_wait(session, 4.0)
        key = action["key"]
        if key == "gmail_send_email":
            compose_values = {
                "view": "cm",
                "fs": "1",
                "to": values.get("to", ""),
                "su": values.get("subject", ""),
                "body": values.get("body", ""),
            }
            compose_url = "https://mail.google.com/mail/u/0/?" + urlencode(compose_values)
            session.goto(compose_url, wait_idle=False)
            _cdp_wait(session, 4.0)
            result.setdefault("clicked_nonfinal_controls", []).append(
                {"field": "compose", "method": "gmail_compose_url"}
            )
            _cdp_wait(session, 2.0)
            _cdp_verify_gmail_compose_values(session, values, result)
            _cdp_detect_file_input(session, values.get("attachment_path", ""), "attachment_path", result)
            result["warnings"].append("CDP fallback did not click Send.")
        elif key == "youtube_studio_upload_video":
            _cdp_click_text(session, ["Create", "Upload videos", "만들기", "업로드"], result, "youtube_upload_open")
            _cdp_wait(session, 2.0)
            _cdp_detect_file_input(session, values.get("video_path", ""), "video_path", result)
            _cdp_fill_first(
                session,
                ['input[aria-label*="Title"]', 'textarea[aria-label*="Title"]'],
                values.get("title", ""),
                "title",
                result,
            )
            _cdp_fill_first(
                session, ['textarea[aria-label*="Description"]'], values.get("description", ""), "description", result
            )
            result["warnings"].append("CDP fallback verified upload controls but did not publish.")
        elif key == "youtube_studio_edit_video_metadata":
            _cdp_fill_first(
                session,
                [
                    'input[aria-label*="Search"]',
                    'input[placeholder*="Search"]',
                    'input[type="search"]',
                ],
                values.get("video_id_or_url", "") or values.get("video_id", ""),
                "video_lookup",
                result,
                press_enter=True,
            )
            for field in ("title", "description", "visibility"):
                if values.get(field):
                    result["skipped_fields"].append(field)
            result["warnings"].append("CDP fallback performed lookup only; metadata save was not clicked.")
        elif key in ("search_console_submit_indexing", "search_console_submit_sitemap"):
            field = "url" if key == "search_console_submit_indexing" else "sitemap_url"
            _cdp_fill_first(
                session,
                [
                    'input[aria-label*="URL"]',
                    'input[aria-label*="Sitemap"]',
                    'input[placeholder*="sitemap"]',
                    'input[type="url"]',
                    'input[type="text"]',
                ],
                values.get(field, ""),
                field,
                result,
                press_enter=False,
            )
            if values.get("property"):
                result["filled_fields"].append("property")
            result["warnings"].append("CDP fallback did not click Request indexing/Submit.")
        elif key == "cloud_iam_change_role":
            opened_panel = _cdp_click_first_selector(
                session,
                [
                    'button[instrumentationid="iam-add-member"]',
                    "iam-add-member-action button",
                    'button[aria-label*="Grant access"]',
                    'button[aria-label*="권한"]',
                ],
                result,
                "grant_access_panel",
            )
            if not opened_panel:
                opened_panel = _cdp_click_text(
                    session, ["Grant access", "권한 부여", "Add"], result, "grant_access_panel"
                )
            _cdp_wait(session, 2.0)
            principal_filled = _cdp_fill_first(
                session,
                [
                    'input[aria-label*="principal"]',
                    'input[aria-label*="Principal"]',
                    'input[id*="add-member-bar-input"]',
                    'input[type="email"]',
                    'input[type="text"]',
                ],
                values.get("principal", ""),
                "principal",
                result,
                press_enter=True,
            )
            if values.get("project"):
                result["filled_fields"].append("project")
            if not opened_panel:
                result["status"] = "opened_no_final_submit"
                result["warnings"].append("IAM Grant access panel was not opened; role/change were not entered.")
                for field in ("role", "change"):
                    if values.get(field):
                        result["skipped_fields"].append(field)
            elif principal_filled:
                for field in ("role", "change"):
                    if values.get(field):
                        result["skipped_fields"].append(field)
                result["warnings"].append("IAM principal was entered; role/change require visual picker confirmation.")
                result["status"] = "opened_no_final_submit"
            else:
                result["status"] = "opened_no_final_submit"
                result["warnings"].append("IAM Grant access panel opened, but principal input was not verified.")
            result["warnings"].append("CDP fallback did not click final Grant/Save.")
        elif key in ("cloud_create_api_credential", "ai_studio_create_api_key", "play_console_prepare_release"):
            for field, value in values.items():
                if not value:
                    result["skipped_fields"].append(field)
                    continue
                _cdp_fill_first(
                    session,
                    [
                        'input[aria-label*="Search"]',
                        'input[placeholder*="Search"]',
                        'input[aria-label*="project"]',
                        'input[aria-label*="Project"]',
                        'input[type="search"]',
                        'input[type="text"]',
                    ],
                    str(value),
                    field,
                    result,
                )
            result["warnings"].append("CDP fallback did not click Create/Get key/Release.")
        elif LIVE_INPUT_ADAPTERS.get(key) in DOMAIN_SPECIFIC_PREFILL_MODES:
            _cdp_fill_domain_specific_input_handoff(session, action, values, result)
        else:
            _cdp_fill_generic_input_handoff(session, action, values, result)
        result["final_control_policy"] = {
            "mode": "no_final_submit",
            "blocked_labels": list(FINAL_CONTROL_LABELS),
            "detected_controls": _detect_final_controls_cdp(session),
        }
        result["current_url"] = session.url
        result["title"] = session.title
        if result["status"] == "started":
            result["status"] = "filled_no_final_submit"
    except Exception as exc:
        _record_direct_cdp_incomplete(target_action, result, session, exc)
    finally:
        if session_manager is not None:
            session_manager.__exit__(None, None, None)


def _needs_direct_cdp_retry(action: dict, result: dict) -> bool:
    return (
        action["key"] == "youtube_studio_upload_video"
        and "video_path" not in result.get("filled_fields", [])
        and "video_path" in result.get("skipped_fields", [])
    )


# CDP fill 프리미티브는 live_inputs_fill(공유 leaf)로 분리. 재노출(파사드+내부용).
# 도메인별 fill 핸들러는 live_inputs_domain_fillers(leaf)로 분리. 재노출(파사드+내부용).
from .live_inputs_domain_fillers import (  # noqa: F401,E402
    _attach_file_input,
    _click_first_selector,
    _click_text,
    _detect_final_controls,
    _ensure_gmail_compose_open,
    _fill_ai_studio_api_key,
    _fill_cloud_api_credential,
    _fill_cloud_iam_change,
    _fill_contenteditable,
    _fill_domain_specific_input_handoff,
    _fill_first,
    _fill_generic_input_handoff,
    _fill_gmail_recipient_js,
    _fill_gmail_send,
    _fill_gmail_send_v2,
    _fill_play_console_release_handoff,
    _fill_search_console_sitemap,
    _fill_search_console_url_inspection,
    _fill_visible_input_js,
    _fill_youtube_studio_metadata,
    _fill_youtube_studio_upload,
    _fill_youtube_studio_upload_v2,
    _gmail_compose_visible,
    _open_only,
    _save_manifest_result,
    _save_result,
)
from .live_inputs_fill import (  # noqa: F401,E402
    _cdp_click_first_selector,
    _cdp_click_text,
    _cdp_detect_file_input,
    _cdp_fill_domain_specific_input_handoff,
    _cdp_fill_first,
    _cdp_fill_generic_input_handoff,
    _cdp_verify_gmail_compose_values,
    _detect_final_controls_cdp,
    _domain_prefill_selectors,
    _generic_selectors,
    _safe_to_generic_fill,
)
