"""Live no-final-submit input adapters for Google workflows."""
from __future__ import annotations

import json
import os
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from . import workflows

ROOT = Path(__file__).resolve().parents[2]
LIVE_INPUT_DIR = ROOT / "data" / "google_live_inputs"
LATEST_LIVE_INPUT = ROOT / "data" / "google_live_input_latest.json"
LIVE_INPUT_MANIFEST_DIR = ROOT / "data" / "google_live_input_manifests"
LATEST_LIVE_INPUT_MANIFEST = ROOT / "data" / "google_live_input_manifest_latest.json"
LIVE_INPUT_COVERAGE_DIR = ROOT / "data" / "google_live_input_coverage"
LATEST_LIVE_INPUT_COVERAGE = ROOT / "data" / "google_live_input_coverage_latest.json"
LIVE_INPUT_ADAPTERS = {
    action.key: "safe_generic_input_handoff" for action in workflows.WRITE_ACTIONS
}
LIVE_INPUT_ADAPTERS.update({
    "gmail_send_email": "safe_pre_final_input",
    "cloud_iam_change_role": "safe_pre_final_input",
    "search_console_submit_indexing": "safe_pre_final_input",
    "youtube_studio_upload_video": "safe_pre_final_input",
    "youtube_studio_edit_video_metadata": "safe_lookup_handoff",
    "search_console_submit_sitemap": "safe_pre_final_input",
    "ai_studio_create_api_key": "safe_secret_issue_final_click_ready",
    "cloud_create_api_credential": "safe_secret_issue_final_click_ready",
    "play_console_prepare_release": "safe_handoff_no_release",
})
DOMAIN_SPECIFIC_PREFILL_MODES = {
    "safe_pre_final_input",
    "safe_secret_issue_final_click_ready",
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


class _CDPSessionManager:
    def __init__(self, session: Any):
        self._session = session

    def __enter__(self) -> Any:
        return self._session

    def __exit__(self, *_: Any) -> None:
        self._session.close()


def _new_cdp_target_session(target_url: str) -> _CDPSessionManager:
    from scripts.cdp_console import CDPSession
    from scripts.config import CDP_HOST, CDP_PORT

    encoded_url = quote(target_url, safe=":/?&=%#")
    endpoint = f"http://{CDP_HOST}:{CDP_PORT}/json/new?{encoded_url}"
    timeout = min(max(5.0, _cdp_websocket_timeout()), 30.0)
    last_error: Exception | None = None
    for method in (requests.put, requests.get):
        try:
            response = method(endpoint, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            ws_url = payload.get("webSocketDebuggerUrl")
            if not ws_url:
                raise RuntimeError("CDP new target response did not include websocket URL")
            return _CDPSessionManager(CDPSession(ws_url, timeout=_cdp_websocket_timeout()))
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"CDP new target unavailable: {last_error}")


def _live_input_target_url(action: dict, values: dict) -> str:
    target = action.get("target_url", "")
    if action.get("key") == "cloud_iam_change_role" and values.get("project") and "project=" not in target:
        separator = "&" if "?" in target else "?"
        target = f"{target}{separator}project={quote(str(values['project']), safe='')}"
    return target


def _connect_live_input_cdp(action: dict, result: dict) -> Any:
    from scripts.cdp_console import connect

    target_url = action.get("target_url", "")
    try:
        return _new_cdp_target_session(target_url)
    except Exception as exc:
        result["warnings"].append(f"cdp_new_target_unavailable: {exc}")

    host = urlsplit(target_url).netloc
    for token in (host, "google", ""):
        try:
            return connect(url_contains=token, websocket_timeout=_cdp_websocket_timeout())
        except Exception as exc:
            result["warnings"].append(f"cdp_existing_tab_unavailable({token or 'any'}): {exc}")
    raise RuntimeError("no usable CDP tab")


def _safe_cdp_identity(session: Any, action: dict) -> dict:
    identity = {"current_url": "", "title": ""}
    if session is not None:
        try:
            identity["current_url"] = session.url
        except Exception:
            identity["current_url"] = ""
        try:
            identity["title"] = session.title
        except Exception:
            identity["title"] = ""
    if session is not None and not identity["current_url"] and action.get("target_url"):
        identity["current_url"] = action["target_url"]
    return identity


def _record_direct_cdp_incomplete(action: dict, result: dict, session: Any, exc: Exception) -> None:
    identity = _safe_cdp_identity(session, action)
    result.update(identity)
    current_url = identity.get("current_url", "")
    if current_url and current_url != "about:blank":
        result["status"] = "opened_no_final_submit"
        result["warnings"].append(f"direct_cdp_live_input_incomplete_after_open: {exc}")
    else:
        result["status"] = "blocked_browser_control_unavailable"
        result["warnings"].append(f"direct_cdp_live_input_blocked: {exc}")
    result["state_change_final_button_clicked"] = False


def build_live_input_coverage() -> dict:
    """Build live-fill support coverage against the Google work catalog."""
    actions = [item for item in workflows.build_action_catalog()["actions"] if item["requires_approval"]]
    supported: list[dict] = []
    unsupported: list[dict] = []
    domain_specific_prefill: list[dict] = []
    generic_handoff: list[dict] = []
    partial_handoff: list[dict] = []
    for action in actions:
        item = {
            "action_key": action["key"],
            "surface_key": action["surface_key"],
            "operation": action["operation"],
            "required_inputs": action["required_inputs"],
            "approval_required": action["requires_approval"],
        }
        mode = LIVE_INPUT_ADAPTERS.get(action["key"])
        if mode:
            item["live_input_mode"] = mode
            item["final_state_policy"] = "no_final_submit_only"
            supported.append(item)
            if mode in DOMAIN_SPECIFIC_PREFILL_MODES:
                item["prefill_maturity"] = "domain_specific_final_approval_ready"
                domain_specific_prefill.append(item)
            elif mode in GENERIC_HANDOFF_MODES:
                item["prefill_maturity"] = "generic_handoff_needs_domain_prefill"
                generic_handoff.append(item)
            elif mode in PARTIAL_HANDOFF_MODES:
                item["prefill_maturity"] = "partial_handoff_needs_domain_prefill"
                partial_handoff.append(item)
            else:
                item["prefill_maturity"] = "unknown_handoff_needs_review"
                partial_handoff.append(item)
        else:
            item["live_input_mode"] = "open_only_or_prepare_only"
            item["final_state_policy"] = "approval_handoff_required"
            item["prefill_maturity"] = "unsupported"
            unsupported.append(item)
    strict_prefill_gaps = generic_handoff + partial_handoff + unsupported
    coverage = {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "default": "prepare_all_actions_but_live_fill_only_supported_adapters",
            "strict_completion": "domain_specific_prefill_only_counts_as_final_approval_ready",
            "final_controls": list(FINAL_CONTROL_LABELS),
            "manifest_template": "configs/google_live_input_manifest_template.json",
        },
        "counts": {
            "approval_actions": len(actions),
            "live_input_supported": len(supported),
            "prepare_or_open_only": len(unsupported),
            "domain_specific_prefill": len(domain_specific_prefill),
            "generic_handoff": len(generic_handoff),
            "partial_handoff": len(partial_handoff),
            "strict_prefill_gaps": len(strict_prefill_gaps),
        },
        "supported": supported,
        "prepare_or_open_only": unsupported,
        "domain_specific_prefill": domain_specific_prefill,
        "generic_handoff": generic_handoff,
        "partial_handoff": partial_handoff,
        "strict_prefill_gaps": strict_prefill_gaps,
    }
    return coverage


def save_live_input_coverage(coverage: dict | None = None, path: Path | None = None) -> Path:
    coverage = coverage or build_live_input_coverage()
    LIVE_INPUT_COVERAGE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_LIVE_INPUT_COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = path or LIVE_INPUT_COVERAGE_DIR / f"google_live_input_coverage_{timestamp}.json"
    text = json.dumps(coverage, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_LIVE_INPUT_COVERAGE.write_text(text, encoding="utf-8")
    return target


def print_live_input_coverage(coverage: dict, path: Path) -> None:
    print("=" * 60)
    print("Google live input coverage")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_LIVE_INPUT_COVERAGE}")
    print(f"approval_actions: {coverage['counts']['approval_actions']}")
    print(f"live_input_supported: {coverage['counts']['live_input_supported']}")
    print(f"prepare_or_open_only: {coverage['counts']['prepare_or_open_only']}")
    print(f"domain_specific_prefill: {coverage['counts']['domain_specific_prefill']}")
    print(f"generic_handoff: {coverage['counts']['generic_handoff']}")
    print(f"partial_handoff: {coverage['counts']['partial_handoff']}")
    print(f"strict_prefill_gaps: {coverage['counts']['strict_prefill_gaps']}")
    print("supported:")
    for item in coverage["supported"]:
        print(f"- {item['action_key']}: {item['live_input_mode']}")


def run_live_input(plan_path: str | Path, *, no_final_submit: bool = True) -> tuple[dict, Path]:
    """Open the target workflow and fill available inputs without final submit."""
    path = Path(plan_path)
    plan = json.loads(path.read_text(encoding="utf-8"))
    action = plan["action"]
    values = plan.get("provided_inputs", {})
    result = {
        "site_id": "google",
        "action_key": action["key"],
        "started_at": datetime.now(timezone.utc).isoformat(),
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
            result["warnings"].append("Playwright path did not verify upload input; retrying direct CDP read-only detection.")
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
        "started_at": datetime.now(timezone.utc).isoformat(),
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


def print_live_input_summary(result: dict, path: Path) -> None:
    print("=" * 60)
    print("Google live input")
    print("=" * 60)
    print(f"action: {result['action_key']}")
    print(f"status: {result['status']}")
    print(f"no_final_submit: {result['no_final_submit']}")
    print(f"final_clicked: {result['state_change_final_button_clicked']}")
    print(f"filled_fields: {', '.join(result['filled_fields']) if result['filled_fields'] else '-'}")
    if result["skipped_fields"]:
        print(f"skipped_fields: {', '.join(result['skipped_fields'])}")
    if result["warnings"]:
        print("warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    print(f"url: {result.get('current_url', '')}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_LIVE_INPUT}")


def print_live_manifest_summary(summary: dict, path: Path) -> None:
    print("=" * 60)
    print("Google live input manifest")
    print("=" * 60)
    print(f"status: {summary['status']}")
    print(f"no_final_submit: {summary['no_final_submit']}")
    print(f"final_clicked: {summary['state_change_final_button_clicked']}")
    print(
        "counts: "
        f"total={summary['counts']['total']} "
        f"filled={summary['counts']['filled']} "
        f"blocked={summary['counts']['blocked']} "
        f"failed={summary['counts']['failed']}"
    )
    for item in summary["items"]:
        print(f"- {item['action_key']}: {item['status']} -> {item.get('result_path', '-')}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_LIVE_INPUT_MANIFEST}")


def _dispatch_live_input(page: Any, action: dict, values: dict, result: dict) -> None:
    key = action["key"]
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
            _cdp_fill_first(session, ['input[aria-label*="Title"]', 'textarea[aria-label*="Title"]'], values.get("title", ""), "title", result)
            _cdp_fill_first(session, ['textarea[aria-label*="Description"]'], values.get("description", ""), "description", result)
            result["warnings"].append("CDP fallback verified upload controls but did not publish.")
        elif key == "youtube_studio_edit_video_metadata":
            _cdp_fill_first(session, [
                'input[aria-label*="Search"]',
                'input[placeholder*="Search"]',
                'input[type="search"]',
            ], values.get("video_id_or_url", "") or values.get("video_id", ""), "video_lookup", result, press_enter=True)
            for field in ("title", "description", "visibility"):
                if values.get(field):
                    result["skipped_fields"].append(field)
            result["warnings"].append("CDP fallback performed lookup only; metadata save was not clicked.")
        elif key in ("search_console_submit_indexing", "search_console_submit_sitemap"):
            field = "url" if key == "search_console_submit_indexing" else "sitemap_url"
            _cdp_fill_first(session, [
                'input[aria-label*="URL"]',
                'input[aria-label*="Sitemap"]',
                'input[placeholder*="sitemap"]',
                'input[type="url"]',
                'input[type="text"]',
            ], values.get(field, ""), field, result, press_enter=False)
            if values.get("property"):
                result["filled_fields"].append("property")
            result["warnings"].append("CDP fallback did not click Request indexing/Submit.")
        elif key == "cloud_iam_change_role":
            opened_panel = _cdp_click_first_selector(session, [
                'button[instrumentationid="iam-add-member"]',
                'iam-add-member-action button',
                'button[aria-label*="Grant access"]',
                'button[aria-label*="권한"]',
            ], result, "grant_access_panel")
            if not opened_panel:
                opened_panel = _cdp_click_text(session, ["Grant access", "권한 부여", "Add"], result, "grant_access_panel")
            _cdp_wait(session, 2.0)
            principal_filled = _cdp_fill_first(session, [
                'input[aria-label*="principal"]',
                'input[aria-label*="Principal"]',
                'input[id*="add-member-bar-input"]',
                'input[type="email"]',
                'input[type="text"]',
            ], values.get("principal", ""), "principal", result, press_enter=True)
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
                _cdp_fill_first(session, [
                    'input[aria-label*="Search"]',
                    'input[placeholder*="Search"]',
                    'input[aria-label*="project"]',
                    'input[aria-label*="Project"]',
                    'input[type="search"]',
                    'input[type="text"]',
                ], str(value), field, result)
            result["warnings"].append("CDP fallback did not click Create/Get key/Release.")
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


def _safe_to_generic_fill(field: str, value: str) -> bool:
    if not value or value == "[redacted]":
        return False
    lowered = field.lower()
    blocked_markers = ("password", "token", "secret", "cookie", "key")
    file_markers = ("path", "file", "artifact", "media", "video", "photo")
    return not any(marker in lowered for marker in blocked_markers + file_markers)


def _generic_selectors(field: str) -> list[str]:
    token = field.replace("_", " ").replace("-", " ")
    compact = field.replace("_", "-")
    return [
        f'input[name="{field}"]',
        f'textarea[name="{field}"]',
        f'input[id*="{field}"]',
        f'textarea[id*="{field}"]',
        f'input[id*="{compact}"]',
        f'textarea[id*="{compact}"]',
        f'input[aria-label*="{token}" i]',
        f'textarea[aria-label*="{token}" i]',
        f'input[placeholder*="{token}" i]',
        f'textarea[placeholder*="{token}" i]',
        'input[type="search"]',
        'input[type="url"]',
        'input[type="email"]',
        'input[type="text"]',
        "textarea",
    ]


def _cdp_fill_first(
    session: Any,
    selectors: list[str],
    value: str,
    field: str,
    result: dict,
    *,
    press_enter: bool = False,
    contenteditable: bool = False,
) -> bool:
    if not value:
        result["skipped_fields"].append(field)
        return False
    data, err = session.js_json(
        """(function(selectors, value, pressEnter, contenteditable) {
            function shown(el) {
                var s = getComputedStyle(el);
                var r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            }
            for (var selector of selectors) {
                var matches = Array.from(document.querySelectorAll(selector)).filter(shown);
                var el = matches[matches.length - 1];
                if (!el) continue;
                el.focus();
                el.click();
                if (contenteditable || el.isContentEditable) {
                    el.textContent = value;
                } else {
                    el.value = value;
                }
                el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                if (pressEnter) {
                    el.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, key: 'Enter'}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: 'Enter'}));
                }
                return {ok: true, selector: selector};
            }
            return {ok: false};
        })(""" + json.dumps(selectors) + ", " + json.dumps(value) + ", " + json.dumps(press_enter) + ", " + json.dumps(contenteditable) + ")"
    )
    if not err and isinstance(data, dict) and data.get("ok"):
        result["filled_fields"].append(field)
        return True
    result["skipped_fields"].append(field)
    result["warnings"].append(f"field not found by CDP: {field}")
    return False


def _cdp_click_first_selector(session: Any, selectors: list[str], result: dict, field: str) -> bool:
    data, err = session.js_json(
        """(function(selectors) {
            function shown(el) {
                var s = getComputedStyle(el);
                var r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            }
            for (var selector of selectors) {
                var el = Array.from(document.querySelectorAll(selector)).find(shown);
                if (!el) continue;
                el.click();
                return {ok: true, selector: selector};
            }
            return {ok: false};
        })(""" + json.dumps(selectors) + ")"
    )
    if not err and isinstance(data, dict) and data.get("ok"):
        result.setdefault("clicked_nonfinal_controls", []).append({"field": field, **data})
        return True
    result["warnings"].append(f"button selector not found by CDP: {field}")
    return False


def _cdp_click_text(session: Any, labels: list[str], result: dict, field: str) -> bool:
    data, err = session.js_json(
        """(function(labels) {
            function norm(v) { return (v || '').replace(/\\s+/g, ' ').trim(); }
            function shown(el) {
                var s = getComputedStyle(el);
                var r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            }
            var controls = Array.from(document.querySelectorAll('button,[role="button"],a,div[aria-label],span[aria-label]')).filter(shown);
            for (var label of labels) {
                for (var el of controls) {
                    var text = norm(el.innerText || el.value);
                    var aria = norm(el.getAttribute('aria-label'));
                    var title = norm(el.getAttribute('title'));
                    if (text.includes(label) || aria.includes(label) || title.includes(label)) {
                        el.click();
                        return {ok: true, label: label, text: text.slice(0, 80), aria: aria.slice(0, 80)};
                    }
                }
            }
            return {ok: false};
        })(""" + json.dumps(labels) + ")"
    )
    if not err and isinstance(data, dict) and data.get("ok"):
        result.setdefault("clicked_nonfinal_controls", []).append({"field": field, **data})
        return True
    result["warnings"].append(f"button not found by CDP: {field}")
    return False


def _cdp_fill_generic_input_handoff(session: Any, action: dict, values: dict, result: dict) -> None:
    result["adapter_mode"] = "safe_generic_input_handoff"
    for field in action.get("required_inputs", []):
        value = str(values.get(field, ""))
        if not _safe_to_generic_fill(field, value):
            result["skipped_fields"].append(field)
            continue
        _cdp_fill_first(session, _generic_selectors(field), value, field, result)
    for field, value in values.items():
        if field in action.get("required_inputs", []):
            continue
        value = str(value)
        if not _safe_to_generic_fill(field, value):
            continue
        _cdp_fill_first(session, _generic_selectors(field), value, field, result)
    result["warnings"].append(
        "Generic CDP handoff adapter ran with no final submit; final state-changing controls were not clicked."
    )


def _cdp_detect_file_input(session: Any, file_path: str, field: str, result: dict) -> bool:
    if not file_path:
        result["skipped_fields"].append(field)
        return False
    path = Path(file_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        result["skipped_fields"].append(field)
        result["warnings"].append(f"file not found: {file_path}")
        return False
    data, err = session.js_json(
        """(function() {
            return Array.from(document.querySelectorAll('input[type="file"]')).map(function(el) {
                var r = el.getBoundingClientRect();
                return {visible: r.width > 0 && r.height > 0, accept: el.accept || '', multiple: !!el.multiple};
            });
        })()"""
    )
    if not err and isinstance(data, list) and data:
        result["filled_fields"].append(field)
        result["warnings"].append(f"file input verified by CDP, file not uploaded: {path}")
        return True
    result["skipped_fields"].append(field)
    result["warnings"].append(f"file input not found by CDP: {field}")
    return False


def _cdp_verify_gmail_compose_values(session: Any, values: dict, result: dict) -> None:
    data, err = session.js_json(
        """(function(expected) {
            function text(el) { return ((el && (el.innerText || el.textContent || el.value)) || '').trim(); }
            var bodyText = document.body ? document.body.innerText : '';
            var subject = '';
            var subjectInput = document.querySelector('input[name="subjectbox"]');
            if (subjectInput) subject = subjectInput.value || '';
            var recipientVisible = bodyText.includes(expected.to);
            var subjectVisible = subject.includes(expected.subject) || bodyText.includes(expected.subject);
            var bodyVisible = bodyText.includes(expected.body);
            var composeOpen = !!document.querySelector('input[name="subjectbox"], textarea[name="to"], div[role="dialog"]');
            return {
                composeOpen: composeOpen,
                recipientVisible: recipientVisible,
                subjectVisible: subjectVisible,
                bodyVisible: bodyVisible,
                url: location.href,
                title: document.title
            };
        })(""" + json.dumps(
            {
                "to": values.get("to", ""),
                "subject": values.get("subject", ""),
                "body": values.get("body", ""),
            }
        ) + ")"
    )
    if err or not isinstance(data, dict):
        for field in ("to", "subject", "body"):
            if values.get(field):
                result["skipped_fields"].append(field)
        result["warnings"].append("Gmail compose value verification failed by CDP.")
        return
    checks = {
        "to": data.get("recipientVisible"),
        "subject": data.get("subjectVisible"),
        "body": data.get("bodyVisible"),
    }
    for field, ok in checks.items():
        if not values.get(field):
            result["skipped_fields"].append(field)
        elif ok:
            result["filled_fields"].append(field)
        else:
            result["skipped_fields"].append(field)
            result["warnings"].append(f"Gmail compose value not visible: {field}")
    if not data.get("composeOpen"):
        result["warnings"].append("Gmail compose window was not detected.")


def _detect_final_controls_cdp(session: Any) -> list[dict]:
    data, err = session.js_json(
        """(function(labels) {
            function norm(value) { return (value || '').replace(/\\s+/g, ' ').trim(); }
            function shown(el) {
                var s = getComputedStyle(el);
                var r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            }
            var controls = Array.from(document.querySelectorAll('button,[role="button"],input[type="button"],input[type="submit"],a')).filter(shown);
            var results = [];
            for (var el of controls) {
                var text = norm(el.innerText || el.value);
                var aria = norm(el.getAttribute('aria-label'));
                var title = norm(el.getAttribute('title'));
                var matched = labels.find(function(label) { return text.includes(label) || aria.includes(label) || title.includes(label); });
                if (matched) results.push({label: matched, text: text.slice(0, 80), aria: aria.slice(0, 80), title: title.slice(0, 80)});
            }
            return results.slice(0, 25);
        })(""" + json.dumps(list(FINAL_CONTROL_LABELS)) + ")"
    )
    return data if not err and isinstance(data, list) else []


def _fill_gmail_send(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(30000), wait_until="domcontentloaded")
    _page_wait(page, 2500)
    _click_text(page, ["Compose", "편지쓰기", "작성"], result, optional=True)
    _page_wait(page, 1500)
    _fill_first(
        page,
        [
            'textarea[name="to"]',
            'div[name="to"] input[type="text"]',
            'div[aria-label*="받는사람"] input[type="text"]',
            'input[aria-label*="To"]',
            'input[aria-label*="Recipient"]',
            'input[aria-label*="수신자"]',
            'input[aria-label*="받는"]',
            'input.agP.aFw[role="combobox"]',
            'input[type="text"]:not([name="q"]):not([name="subjectbox"])',
        ],
        values.get("to", ""),
        "to",
        result,
    ) or _fill_gmail_recipient_js(page, values.get("to", ""), "to", result)
    subject_filled = _fill_first(
        page,
        ['input[name="subjectbox"]', 'input[aria-label*="Subject"]', 'input[aria-label*="제목"]'],
        values.get("subject", ""),
        "subject",
        result,
    )
    if not subject_filled:
        _fill_visible_input_js(page, 'input[name="subjectbox"]', values.get("subject", ""), "subject", result)
    _fill_contenteditable(page, values.get("body", ""), "body", result)
    attachment_path = values.get("attachment_path", "")
    if attachment_path:
        _attach_file_input(page, attachment_path, "attachment_path", result)
    result["warnings"].append("Gmail may autosave a draft; Send was not clicked.")


def _fill_gmail_send_v2(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(30000), wait_until="domcontentloaded")
    _page_wait(page, 3500)
    _ensure_gmail_compose_open(page, result)
    _fill_first(
        page,
        [
            'textarea[name="to"]',
            'div[name="to"] input[type="text"]',
            'div[aria-label*="받는사람"] input[type="text"]',
            'input[aria-label*="To"]',
            'input[aria-label*="Recipient"]',
            'input[aria-label*="수신자"]',
            'input[aria-label*="받는"]',
            'input.agP.aFw[role="combobox"]',
            'input[type="text"]:not([name="q"]):not([name="subjectbox"])',
        ],
        values.get("to", ""),
        "to",
        result,
        press_enter=True,
    ) or _fill_gmail_recipient_js(page, values.get("to", ""), "to", result)
    _page_wait(page, 800)
    if not _fill_first(
        page,
        [
            'input[name="subjectbox"]',
            'input[aria-label*="Subject"]',
            'input[aria-label*="제목"]',
            'input[placeholder*="제목"]',
        ],
        values.get("subject", ""),
        "subject",
        result,
    ):
        _fill_visible_input_js(page, 'input[name="subjectbox"]', values.get("subject", ""), "subject", result)
    _fill_contenteditable(page, values.get("body", ""), "body", result)
    attachment_path = values.get("attachment_path", "")
    if attachment_path:
        _attach_file_input(page, attachment_path, "attachment_path", result)
    result["warnings"].append("Gmail may autosave a draft; Send was not clicked.")


def _ensure_gmail_compose_open(page: Any, result: dict) -> None:
    for _ in range(3):
        if _gmail_compose_visible(page):
            return
        if not _click_text(page, ["Compose", "편지쓰기", "작성"], result, optional=True):
            _click_first_selector(
                page,
                ['div[role="button"][gh="cm"]', 'div[aria-label*="Compose"]', 'div[aria-label*="편지쓰기"]'],
                "gmail_compose",
                result,
            )
        _page_wait(page, 2000)
    if not _gmail_compose_visible(page):
        result["warnings"].append("Gmail compose window did not stay open.")


def _gmail_compose_visible(page: Any) -> bool:
    selectors = [
        'input[name="subjectbox"]',
        'textarea[name="to"]',
        'div[contenteditable="true"][aria-label*="메일 본문"]',
        'div[contenteditable="true"][aria-label*="Message Body"]',
    ]
    for frame in page.frames:
        for selector in selectors:
            try:
                matches = frame.locator(selector)
                for index in range(min(matches.count(), 8)):
                    if matches.nth(index).bounding_box(timeout=_locator_timeout(500)) is not None:
                        return True
            except Exception:
                continue
    return False


def _fill_cloud_iam_change(page: Any, action: dict, values: dict, result: dict) -> None:
    project = values.get("project", "")
    target = action["target_url"]
    if project and "project=" not in target:
        target = f"{target}?project={project}"
    page.goto(target, timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 5000)
    if not _click_first_selector(
        page,
        ['button[instrumentationid="iam-add-member"]', 'iam-add-member-action button'],
        "grant_access_panel",
        result,
    ):
        _click_text(page, ["Grant access", "액세스 권한 부여", "권한 부여"], result, optional=True)
    _page_wait(page, 2500)
    _fill_first(
        page,
        [
            'input[id*="add-member-bar-input"]',
            'input[aria-label*="principal"]',
            'input[aria-label*="Principal"]',
            'input[aria-label*="주 구성원"]',
            'input[placeholder*="principal"]',
            'input[type="email"]',
        ],
        values.get("principal", ""),
        "principal",
        result,
        press_enter=True,
    )
    _page_wait(page, 1200)
    role = values.get("role", "")
    if role and _click_first_selector(
        page,
        [
            'cfc-select-dual-column[name="selectedRole"]',
            'cfc-select-dual-column[aria-label*="역할"]',
            'cfc-select-dual-column[aria-label*="role"]',
            '[id*="cfc-select-dual-column"]',
        ],
        "role_picker",
        result,
    ):
        _page_wait(page, 1500)
        if _fill_first(
            page,
            [
                'input[aria-label*="필터"]',
                'input[aria-label*="Filter"]',
                'input[placeholder*="필터"]',
                'input[placeholder*="Filter"]',
                'input[aria-label*="검색"]',
                'input[type="search"]',
            ],
            role,
            "role",
            result,
            press_enter=True,
        ):
            _page_wait(page, 800)
        else:
            try:
                page.keyboard.type(role, delay=5)
                page.keyboard.press("Enter")
                if "role" in result["skipped_fields"]:
                    result["skipped_fields"].remove("role")
                result["filled_fields"].append("role")
                result["warnings"].append("role typed through open role picker; visual selection should be checked.")
            except Exception:
                result["skipped_fields"].append("role")
                result["warnings"].append("field not found: role")
    else:
        if role:
            result["skipped_fields"].append("role")
            result["warnings"].append("field not found: role")
        else:
            result["skipped_fields"].append("role")
    result["filled_fields"].append("project") if project else result["skipped_fields"].append("project")
    result["warnings"].append("IAM final Grant/Save/Add button was not clicked.")


def _fill_search_console_url_inspection(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 4000)
    _fill_first(
        page,
        [
            'input[aria-label*="Inspect"]',
            'input[aria-label*="URL"]',
            'input[placeholder*="Inspect"]',
            'input[type="text"]',
        ],
        values.get("url", ""),
        "url",
        result,
    )
    result["warnings"].append("URL inspection input only; Request indexing was not clicked.")


def _fill_search_console_sitemap(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 4000)
    sitemap = values.get("sitemap_url", "") or values.get("sitemap", "")
    _fill_first(
        page,
        [
            'input[aria-label*="Sitemap"]',
            'input[placeholder*="sitemap"]',
            'input[aria-label*="사이트맵"]',
            'input[type="url"]',
            'input[type="text"]',
        ],
        sitemap,
        "sitemap_url",
        result,
    )
    if values.get("property"):
        result["filled_fields"].append("property")
        result["warnings"].append("Search Console property was recorded in plan; property switch was not submitted.")
    result["warnings"].append("Sitemap input only; Submit was not clicked.")


def _fill_youtube_studio_upload(page: Any, action: dict, values: dict, result: dict) -> None:
    video_path = values.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        result["status"] = "blocked_missing_file"
        result["skipped_fields"].append("video_path")
        result["warnings"].append(f"video file not found: {video_path}")
        return
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 4000)
    _click_text(page, ["Create", "만들기", "Upload videos", "동영상 업로드"], result, optional=True)
    _page_wait(page, 2000)
    try:
        page.set_input_files('input[type="file"]', video_path)
        result["filled_fields"].append("video_path")
    except Exception as exc:
        result["skipped_fields"].append("video_path")
        result["warnings"].append(f"file input failed: {exc}")
    _fill_first(page, ['input[aria-label*="Title"]', 'textarea[aria-label*="Title"]'], values.get("title", ""), "title", result)
    _fill_first(page, ['textarea[aria-label*="Description"]'], values.get("description", ""), "description", result)
    result["warnings"].append("YouTube final Next/Publish buttons were not clicked.")


def _fill_youtube_studio_upload_v2(page: Any, action: dict, values: dict, result: dict) -> None:
    video_path = values.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        result["status"] = "blocked_missing_file"
        result["skipped_fields"].append("video_path")
        result["warnings"].append(f"video file not found: {video_path}")
        return
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 5000)
    _click_first_selector(
        page,
        [
            'ytcp-button#create-icon',
            'button[aria-label*="Create"]',
            'tp-yt-paper-icon-button[aria-label*="Create"]',
            'button[aria-label*="만들기"]',
            'tp-yt-paper-icon-button[aria-label*="만들기"]',
        ],
        "youtube_create_menu",
        result,
    )
    _click_text(page, ["Create", "Upload videos", "만들기", "동영상 업로드"], result, optional=True)
    _page_wait(page, 2500)
    _click_text(page, ["Upload videos", "동영상 업로드"], result, optional=True)
    _page_wait(page, 2500)
    try:
        page.set_input_files('input[type="file"]', video_path)
        result["filled_fields"].append("video_path")
        result["warnings"].append("video file selected/upload draft may be created; Publish was not clicked.")
    except Exception as exc:
        result["skipped_fields"].append("video_path")
        result["warnings"].append(f"file input failed: {exc}")
        return
    _page_wait(page, 5000)
    _fill_first(
        page,
        ['input[aria-label*="Title"]', 'textarea[aria-label*="Title"]', '#textbox[aria-label*="Title"]'],
        values.get("title", ""),
        "title",
        result,
    )
    _fill_first(
        page,
        ['textarea[aria-label*="Description"]', '#textbox[aria-label*="Description"]'],
        values.get("description", ""),
        "description",
        result,
    )
    result["warnings"].append("YouTube final Next/Publish buttons were not clicked.")


def _fill_youtube_studio_metadata(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 5000)
    query = values.get("video_id", "") or values.get("title", "")
    _fill_first(
        page,
        [
            'input[aria-label*="Search"]',
            'input[placeholder*="Search"]',
            'input[aria-label*="검색"]',
            'input[type="search"]',
        ],
        query,
        "video_lookup",
        result,
        press_enter=True,
    )
    _page_wait(page, 2000)
    if values.get("title"):
        result["skipped_fields"].append("title")
    if values.get("description"):
        result["skipped_fields"].append("description")
    result["warnings"].append(
        "YouTube metadata target lookup only; edit/save/publish controls were not clicked."
    )


def _fill_ai_studio_api_key(page: Any, action: dict, values: dict, result: dict) -> None:
    result["adapter_mode"] = "safe_secret_issue_final_click_ready"
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 4000)
    project = values.get("project", "")
    if project:
        _fill_first(
            page,
            [
                'input[aria-label*="project"]',
                'input[aria-label*="Project"]',
                'input[placeholder*="project"]',
                'input[type="text"]',
            ],
            project,
            "project",
            result,
        )
    else:
        result["skipped_fields"].append("project")
    result["final_approval_boundary"] = "user_clicks_final_secret_issue_control"
    result["warnings"].append(
        "AI Studio API key page prepared; final Create/Get key secret-issuing control was not clicked."
    )


def _fill_cloud_api_credential(page: Any, action: dict, values: dict, result: dict) -> None:
    result["adapter_mode"] = "safe_secret_issue_final_click_ready"
    project = values.get("project", "")
    target = action["target_url"]
    if project and "project=" not in target:
        target = f"{target}?project={project}"
    page.goto(target, timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 5000)
    if project:
        result["filled_fields"].append("project")
    credential_type = values.get("credential_type", "")
    if credential_type:
        result["filled_fields"].append("credential_type")
        result["warnings"].append(
            "Credential type recorded in plan; final secret-issuing credential menu item was not clicked."
        )
    label = values.get("label", "")
    if label:
        result["filled_fields"].append("label")
    result["final_approval_boundary"] = "user_clicks_final_secret_issue_control"
    result["warnings"].append(
        "Cloud credential screen prepared; Create/API key/OAuth final secret-issuing control was not clicked."
    )


def _fill_play_console_release_handoff(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 5000)
    app = values.get("app", "") or values.get("package", "")
    _fill_first(
        page,
        [
            'input[aria-label*="Search"]',
            'input[placeholder*="Search"]',
            'input[aria-label*="검색"]',
            'input[type="search"]',
            'input[type="text"]',
        ],
        app,
        "app_lookup",
        result,
        press_enter=True,
    )
    for field in ("track", "artifact_path", "release_notes"):
        if values.get(field):
            result["skipped_fields"].append(field)
    result["warnings"].append(
        "Play Console app lookup only; release upload/review/rollout controls were not clicked."
    )


def _fill_generic_input_handoff(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 3000)
    result["adapter_mode"] = "safe_generic_input_handoff"
    for field in action.get("required_inputs", []):
        value = str(values.get(field, ""))
        if not _safe_to_generic_fill(field, value):
            result["skipped_fields"].append(field)
            continue
        _fill_first(page, _generic_selectors(field), value, field, result)
    for field, value in values.items():
        if field in action.get("required_inputs", []):
            continue
        value = str(value)
        if not _safe_to_generic_fill(field, value):
            continue
        _fill_first(page, _generic_selectors(field), value, field, result)
    result["warnings"].append(
        "Generic Google handoff adapter ran with no final submit; file, secret, publish, deploy, send, save, grant, "
        "or create controls were not clicked."
    )


def _open_only(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 2500)
    for key, value in values.items():
        if value:
            result["skipped_fields"].append(key)
    result["status"] = "opened_only_no_adapter"
    result["warnings"].append("No live input adapter for this action yet; target opened only.")


def _fill_first(
    page: Any,
    selectors: list[str],
    value: str,
    field: str,
    result: dict,
    *,
    press_enter: bool = False,
) -> bool:
    if not value:
        result["skipped_fields"].append(field)
        return False
    for selector in selectors:
        for frame in page.frames:
            try:
                matches = frame.locator(selector)
                count = min(matches.count(), 12)
                for index in range(count):
                    locator = matches.nth(index)
                    if locator.bounding_box(timeout=_locator_timeout(1000)) is None:
                        continue
                    locator.click(timeout=_locator_timeout(3000))
                    try:
                        locator.fill(value, timeout=_locator_timeout(5000))
                    except Exception:
                        page.keyboard.type(value, delay=5)
                    if press_enter:
                        page.keyboard.press("Enter")
                    result["filled_fields"].append(field)
                    return True
            except Exception:
                continue
    result["skipped_fields"].append(field)
    result["warnings"].append(f"field not found: {field}")
    return False


def _fill_contenteditable(page: Any, value: str, field: str, result: dict) -> bool:
    if not value:
        result["skipped_fields"].append(field)
        return False
    selectors = ['div[contenteditable="true"][role="textbox"]', 'div[contenteditable="true"]']
    for selector in selectors:
        for frame in page.frames:
            try:
                locator = frame.locator(selector).last
                if locator.count() > 0:
                    locator.click(timeout=_locator_timeout(3000))
                    page.keyboard.type(value, delay=5)
                    result["filled_fields"].append(field)
                    return True
            except Exception:
                continue
    result["skipped_fields"].append(field)
    result["warnings"].append(f"contenteditable not found: {field}")
    return False


def _click_text(page: Any, labels: list[str], result: dict, *, optional: bool = False) -> bool:
    for label in labels:
        for frame in page.frames:
            try:
                locator = frame.get_by_text(label, exact=False).first
                if locator.count() > 0:
                    locator.click(timeout=_locator_timeout(4000))
                    return True
            except Exception:
                continue
    try:
        for frame in page.frames:
            clicked = frame.evaluate(
                """(labels) => {
                const norm = (v) => (v || '').replace(/\\s+/g, ' ').trim();
                const candidates = Array.from(document.querySelectorAll(
                  'button, [role="button"], a, div[aria-label], span[aria-label]'
                ));
                for (const label of labels) {
                  for (const el of candidates) {
                    const text = norm(el.innerText);
                    const aria = norm(el.getAttribute('aria-label'));
                    if (!text.includes(label) && !aria.includes(label)) continue;
                    const box = el.getBoundingClientRect();
                    if (box.width <= 0 || box.height <= 0) continue;
                    el.click();
                    return {ok: true, label, text, aria};
                  }
                }
                return {ok: false};
            }""",
                labels,
            )
            if clicked.get("ok"):
                result.setdefault("clicked_nonfinal_controls", []).append(clicked)
                return True
    except Exception:
        pass
    if not optional:
        result["warnings"].append("button not found: " + " / ".join(labels))
    return False


def _click_first_selector(page: Any, selectors: list[str], field: str, result: dict) -> bool:
    for selector in selectors:
        for frame in page.frames:
            try:
                locator = frame.locator(selector).first
                if locator.count() > 0:
                    locator.click(timeout=_locator_timeout(5000))
                    result.setdefault("clicked_nonfinal_controls", []).append(
                        {"field": field, "selector": selector}
                    )
                    return True
            except Exception:
                continue
    return False


def _save_result(result: dict) -> tuple[dict, Path]:
    LIVE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_LIVE_INPUT.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = LIVE_INPUT_DIR / f"google_live_input_{result['action_key']}_{timestamp}.json"
    text = json.dumps(result, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_LIVE_INPUT.write_text(text, encoding="utf-8")
    return result, target


def _save_manifest_result(summary: dict) -> tuple[dict, Path]:
    LIVE_INPUT_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_LIVE_INPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = LIVE_INPUT_MANIFEST_DIR / f"google_live_input_manifest_{timestamp}.json"
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_LIVE_INPUT_MANIFEST.write_text(text, encoding="utf-8")
    return summary, target


def _detect_final_controls(page: Any) -> list[dict]:
    detected: list[dict] = []
    script = """(labels) => {
        const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
        const controls = Array.from(document.querySelectorAll(
          'button, [role="button"], input[type="button"], input[type="submit"], a'
        ));
        const results = [];
        for (const el of controls) {
          const box = el.getBoundingClientRect();
          if (box.width <= 0 || box.height <= 0) continue;
          const text = norm(el.innerText || el.value);
          const aria = norm(el.getAttribute('aria-label'));
          const title = norm(el.getAttribute('title'));
          const matched = labels.find((label) => text.includes(label) || aria.includes(label) || title.includes(label));
          if (matched) {
            results.push({
              label: matched,
              text: text.slice(0, 80),
              aria: aria.slice(0, 80),
              title: title.slice(0, 80)
            });
          }
        }
        return results.slice(0, 25);
    }"""
    for frame in page.frames:
        try:
            for item in frame.evaluate(script, list(FINAL_CONTROL_LABELS)):
                if item not in detected:
                    detected.append(item)
        except Exception:
            continue
    return detected


def _fill_visible_input_js(page: Any, selector: str, value: str, field: str, result: dict) -> bool:
    if not value:
        return False
    for frame in page.frames:
        try:
            filled = frame.evaluate(
                """([selector, value]) => {
                    const shown = (el) => {
                      const s = getComputedStyle(el);
                      const r = el.getBoundingClientRect();
                      return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                    };
                    const els = Array.from(document.querySelectorAll(selector)).filter(shown);
                    const el = els[els.length - 1];
                    if (!el) return false;
                    el.focus();
                    el.value = value;
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return true;
                }""",
                [selector, value],
            )
            if filled:
                if field in result["skipped_fields"]:
                    result["skipped_fields"].remove(field)
                result["filled_fields"].append(field)
                return True
        except Exception:
            continue
    return False


def _fill_gmail_recipient_js(page: Any, value: str, field: str, result: dict) -> bool:
    if not value:
        return False
    script = """() => {
        const shown = (el) => {
          const s = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        };
        const selectors = [
          'div[name="to"] input[type="text"]',
          'div[aria-label*="받는사람"] input[type="text"]',
          'input[aria-label*="수신자"]',
          'input[aria-label*="Recipient"]',
          'input.agP.aFw[role="combobox"]',
          'textarea[name="to"]'
        ];
        const candidates = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
        const el = candidates.filter(shown).pop();
        if (!el) return false;
        el.focus();
        el.click();
        return true;
    }"""
    for frame in page.frames:
        try:
            focused = frame.evaluate(script)
            if not focused:
                continue
            page.keyboard.type(value, delay=5)
            page.keyboard.press("Enter")
            if field in result["skipped_fields"]:
                result["skipped_fields"].remove(field)
            result["filled_fields"].append(field)
            return True
        except Exception:
            continue
    return False


def _attach_file_input(page: Any, file_path: str, field: str, result: dict) -> bool:
    path = Path(file_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        result["skipped_fields"].append(field)
        result["warnings"].append(f"attachment file not found: {file_path}")
        return False
    for frame in page.frames:
        try:
            inputs = frame.locator('input[type="file"]')
            count = inputs.count()
            for index in range(count - 1, -1, -1):
                try:
                    inputs.nth(index).set_input_files(str(path), timeout=_locator_timeout(5000))
                    result["filled_fields"].append(field)
                    result["warnings"].append(f"local file attached: {path}")
                    return True
                except Exception:
                    continue
        except Exception:
            continue
    result["skipped_fields"].append(field)
    result["warnings"].append(f"file input not found for attachment: {field}")
    return False
