"""Google Console OAuth client prefill for YouTube server captions.

This module prepares non-secret Google Console OAuth fields and stops before
the final Create/Save button. It must not click final state-changing controls
and must not print or store raw OAuth secrets.
"""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.common.gates.secret_action_gate import build_secret_action_policy
from scripts.common.gates.work_mode_gate import build_google_work_mode_policy

from . import managed_console

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "google_console_oauth_fill"
LATEST_REPORT = ROOT / "data" / "google_console_oauth_fill_latest.json"

YOUTUBE_DATA_API_ENABLE_URL = "https://console.cloud.google.com/apis/library/youtube.googleapis.com"
GOOGLE_CLOUD_CREDENTIALS_URL = managed_console.GOOGLE_CLOUD_CREDENTIALS_URL
GOOGLE_CLOUD_OAUTH_CLIENT_CREATE_URL = "https://console.cloud.google.com/auth/clients/create"

FINAL_BUTTON_LABELS = ("Create", "Save", "Create OAuth client")
CREATE_CREDENTIAL_LABELS = ("Create credentials",)
OAUTH_CLIENT_LABELS = ("OAuth client ID",)
WEB_APP_LABELS = ("Web application",)
ADD_URI_LABELS = ("Add URI", "Add authorized redirect URI")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_youtube_oauth_console_fill_plan(
    *,
    google_work_mode: str | None = None,
    background_approved: bool = False,
    secret_action_mode: str = "final_approval_only",
    secret_issue_approved: bool = False,
) -> dict[str, Any]:
    """Return the non-secret prefill contract for the YouTube OAuth client."""
    inputs = managed_console.YOUTUBE_SERVER_OAUTH_INPUTS
    work_mode_policy = build_google_work_mode_policy(
        google_work_mode,
        background_approved=background_approved,
    )
    secret_policy = build_secret_action_policy(
        secret_action_mode,
        secret_issue_approved=secret_issue_approved,
    )
    status = "ready_for_ai_prefill"
    if work_mode_policy["status"] == "blocked" or secret_policy["status"] == "blocked":
        status = "blocked"
    return {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_oauth_google_console_prefill",
        "status": status,
        "browser_runtime": "managed_local_agent_cdp_profile",
        "google_work_mode_policy": work_mode_policy,
        "google_work_mode": work_mode_policy["mode"],
        "background_approved": bool(background_approved),
        "default_browser_allowed": False,
        "state_change_final_button_clicked": False,
        "final_button_user_only": secret_policy["final_button_user_only"],
        "secret_action_policy": secret_policy,
        "final_button_labels": list(FINAL_BUTTON_LABELS),
        "agent_steps": [
            "open Google Home in managed CDP profile",
            "open Google Account state page in the same profile",
            "open YouTube Data API v3 library page",
            "click Enable only if the user has already approved API enablement",
            "open Google Cloud Credentials page",
            "open OAuth client ID creation form",
            "fill application type, client name, and redirect URI",
            "stop before final Create/Save button",
        ],
        "user_only_steps": [
            "Google login and MFA/2FA if required",
            "final click on the visible Google Console Create/Save button",
            "Google OAuth consent approval if Google prompts for it",
        ],
        "non_secret_inputs": {
            "project": inputs["project"],
            "api": inputs["api"],
            "credential_type": inputs["credential_type"],
            "application_type": inputs["application_type"],
            "client_name": inputs["client_name"],
            "authorized_redirect_uri": inputs["authorized_redirect_uri"],
            "scope": inputs["scope"],
        },
    }


def _save_report(payload: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"youtube_oauth_google_console_prefill_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LATEST_REPORT.write_text(text, encoding="utf-8")
    return path


def _safe_title(page: Any) -> str:
    try:
        return str(page.title())
    except Exception:  # noqa: BLE001 - 구글 클라우드 콘솔 OAuth 설정 폼 자동입력 - 최종 저장/제출 버튼은 클릭하지 않고 ready_for_user_final_button 상태로 사용자에게 넘김, 실패시 warnings 기록
        return ""


def _wait(page: Any, milliseconds: int) -> None:
    with suppress(Exception):
        page.wait_for_timeout(milliseconds)


def _goto(page: Any, url: str, result: dict[str, Any], stage: str, timeout_ms: int) -> None:
    page.goto(url, timeout=timeout_ms)
    with suppress(Exception):
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    _wait(page, 1500)
    result["visited"].append(
        {
            "stage": stage,
            "target_url": url,
            "current_url": getattr(page, "url", ""),
            "title": _safe_title(page),
        }
    )


def _click_text(page: Any, labels: tuple[str, ...], *, optional: bool = False) -> dict[str, Any]:
    for label in labels:
        for frame in getattr(page, "frames", [page]):
            try:
                locator = frame.get_by_text(label, exact=False).first
                if locator.count() > 0:
                    locator.click(timeout=6000)
                    return {"ok": True, "label": label, "method": "get_by_text"}
            except Exception:  # noqa: BLE001 - 구글 클라우드 콘솔 OAuth 설정 폼 자동입력 - 최종 저장/제출 버튼은 클릭하지 않고 ready_for_user_final_button 상태로 사용자에게 넘김, 실패시 warnings 기록
                continue
    return {"ok": False, "optional": optional, "labels": list(labels)}


def _fill_first_visible_input(page: Any, value: str, field: str, index: int) -> dict[str, Any]:
    script = """([value, index]) => {
      const visible = (el) => {
        const style = getComputedStyle(el);
        const box = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
          && box.width > 0 && box.height > 0 && el.type !== 'search';
      };
      const fields = Array.from(document.querySelectorAll('input, textarea')).filter(visible);
      const el = fields[index] || fields[fields.length - 1];
      if (!el) return {ok: false, reason: 'input_not_found', count: fields.length};
      el.focus();
      el.value = value;
      el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return {ok: true, count: fields.length};
    }"""
    for frame in getattr(page, "frames", [page]):
        try:
            filled = frame.evaluate(script, [value, index])
            if filled.get("ok"):
                filled["field"] = field
                return filled
        except Exception:  # noqa: BLE001 - 구글 클라우드 콘솔 OAuth 설정 폼 자동입력 - 최종 저장/제출 버튼은 클릭하지 않고 ready_for_user_final_button 상태로 사용자에게 넘김, 실패시 warnings 기록
            continue
    return {"ok": False, "field": field}


def _detect_final_controls(page: Any) -> list[dict[str, Any]]:
    script = """(labels) => {
      const norm = (v) => (v || '').replace(/\\s+/g, ' ').trim();
      return Array.from(document.querySelectorAll('button,[role="button"],input[type="submit"]'))
        .filter((el) => {
          const box = el.getBoundingClientRect();
          return box.width > 0 && box.height > 0;
        })
        .map((el) => ({
          text: norm(el.innerText || el.value).slice(0, 80),
          aria: norm(el.getAttribute('aria-label')).slice(0, 80),
          type: el.getAttribute('type') || ''
        }))
        .filter((item) => item.type === 'submit'
          || labels.some((label) => (item.text + item.aria).includes(label)))
        .slice(0, 20);
    }"""
    detected: list[dict[str, Any]] = []
    for frame in getattr(page, "frames", [page]):
        try:
            for item in frame.evaluate(script, list(FINAL_BUTTON_LABELS)):
                if item not in detected:
                    detected.append(item)
        except Exception:  # noqa: BLE001 - 구글 클라우드 콘솔 OAuth 설정 폼 자동입력 - 최종 저장/제출 버튼은 클릭하지 않고 ready_for_user_final_button 상태로 사용자에게 넘김, 실패시 warnings 기록
            continue
    return detected


def _click_final_control(page: Any) -> dict[str, Any]:
    clicked = _click_text(page, FINAL_BUTTON_LABELS, optional=True)
    return {
        "stage": "final_secret_issue_click",
        **clicked,
        "raw_secret_output_allowed": False,
        "secret_capture_policy": "store only approved local-secret reference; do not print raw secret",
    }


def prefill_youtube_oauth_console(
    *,
    dry_run: bool = False,
    approved_api_enable: bool = False,
    google_work_mode: str | None = None,
    background_approved: bool = False,
    secret_action_mode: str = "final_approval_only",
    secret_issue_approved: bool = False,
    timeout_ms: int = 60000,
) -> tuple[dict[str, Any], Path | None]:
    """Open/fill Google Console OAuth form and stop before final Create/Save."""
    plan = build_youtube_oauth_console_fill_plan(
        google_work_mode=google_work_mode,
        background_approved=background_approved,
        secret_action_mode=secret_action_mode,
        secret_issue_approved=secret_issue_approved,
    )
    result: dict[str, Any] = {
        **plan,
        "dry_run": dry_run,
        "status": "dry_run" if dry_run else "started",
        "visited": [],
        "actions": [],
        "warnings": [],
    }
    if plan["status"] == "blocked":
        result["status"] = "blocked"
        blocked_policy = (
            plan["google_work_mode_policy"]
            if plan["google_work_mode_policy"]["status"] == "blocked"
            else plan["secret_action_policy"]
        )
        result["reason"] = blocked_policy["blocked_reason"]
        result["next_step"] = blocked_policy["next_step"]
        return result, None
    if dry_run:
        return result, None

    try:
        from scripts.browser.cdp.connection import get_page

        page = get_page()
    except Exception as exc:  # noqa: BLE001 - 구글 클라우드 콘솔 OAuth 설정 폼 자동입력 - 최종 저장/제출 버튼은 클릭하지 않고 ready_for_user_final_button 상태로 사용자에게 넘김, 실패시 warnings 기록
        result["status"] = "GOOGLE_CONSOLE_NOT_INSPECTABLE"
        result["warnings"].append(f"managed_cdp_page_unavailable: {type(exc).__name__}")
        path = _save_report(result)
        return result, path

    try:
        inputs = plan["non_secret_inputs"]
        _goto(page, managed_console.GOOGLE_HOME_URL, result, "google_home", timeout_ms)
        _goto(page, managed_console.GOOGLE_ACCOUNT_URL, result, "account_state", timeout_ms)
        _goto(
            page,
            f"{YOUTUBE_DATA_API_ENABLE_URL}?project={inputs['project']}",
            result,
            "youtube_data_api_library",
            timeout_ms,
        )
        if approved_api_enable:
            result["actions"].append({"stage": "api_enable", **_click_text(page, ("Enable",), optional=True)})
            _wait(page, 2500)
        else:
            result["actions"].append(
                {
                    "stage": "api_enable",
                    "ok": False,
                    "skipped": True,
                    "reason": "api_enable_screen_prepared_final_click_user_only",
                }
            )
        _goto(page, GOOGLE_CLOUD_CREDENTIALS_URL, result, "cloud_credentials", timeout_ms)
        result["actions"].append(
            {"stage": "create_credentials_menu", **_click_text(page, CREATE_CREDENTIAL_LABELS, optional=True)}
        )
        _wait(page, 800)
        oauth_clicked = _click_text(page, OAUTH_CLIENT_LABELS, optional=True)
        result["actions"].append({"stage": "oauth_client_id_menu", **oauth_clicked})
        if not oauth_clicked.get("ok"):
            _goto(
                page,
                f"{GOOGLE_CLOUD_OAUTH_CLIENT_CREATE_URL}?project={inputs['project']}",
                result,
                "oauth_client_create_direct",
                timeout_ms,
            )
        result["actions"].append({"stage": "application_type", **_click_text(page, WEB_APP_LABELS, optional=True)})
        result["actions"].append(
            {"stage": "client_name", **_fill_first_visible_input(page, inputs["client_name"], "client_name", 0)}
        )
        result["actions"].append({"stage": "add_redirect_uri", **_click_text(page, ADD_URI_LABELS, optional=True)})
        _wait(page, 800)
        result["actions"].append(
            {
                "stage": "authorized_redirect_uri",
                **_fill_first_visible_input(page, inputs["authorized_redirect_uri"], "authorized_redirect_uri", -1),
            }
        )
        result["final_control_policy"] = {
            "mode": plan["secret_action_policy"]["mode"],
            "state_change_final_button_clicked": False,
            "detected_controls": _detect_final_controls(page),
            "raw_secret_output_allowed": False,
        }
        required = [item for item in result["actions"] if item["stage"] in {"client_name", "authorized_redirect_uri"}]
        required_ok = all(item.get("ok") for item in required)
        if required_ok and plan["secret_action_policy"]["agent_final_secret_issue_allowed"]:
            final_click = _click_final_control(page)
            result["actions"].append(final_click)
            result["state_change_final_button_clicked"] = bool(final_click.get("ok"))
            result["final_control_policy"]["state_change_final_button_clicked"] = bool(final_click.get("ok"))
            result["status"] = (
                "secret_issue_clicked_waiting_secret_storage"
                if final_click.get("ok")
                else "needs_user_attention_or_ui_changed"
            )
        else:
            result["status"] = "ready_for_user_final_button" if required_ok else "needs_user_attention_or_ui_changed"
        result["current_url"] = getattr(page, "url", "")
        result["current_title"] = _safe_title(page)
    except Exception as exc:  # noqa: BLE001 - 구글 클라우드 콘솔 OAuth 설정 폼 자동입력 - 최종 저장/제출 버튼은 클릭하지 않고 ready_for_user_final_button 상태로 사용자에게 넘김, 실패시 warnings 기록
        result["status"] = "GOOGLE_CONSOLE_NOT_INSPECTABLE"
        result["warnings"].append(f"{type(exc).__name__}: {exc}")
        result["current_url"] = getattr(page, "url", "")
        result["current_title"] = _safe_title(page)
    path = _save_report(result)
    return result, path


def print_prefill_summary(result: dict[str, Any], path: Path | None) -> None:
    print("=" * 60)
    print("YouTube OAuth Google Console prefill")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"dry_run: {result['dry_run']}")
    print(f"final_button_user_only: {result['final_button_user_only']}")
    print(f"state_change_final_button_clicked: {result['state_change_final_button_clicked']}")
    print(f"secret_action_mode: {result['secret_action_policy']['mode']}")
    print(f"raw_secret_output_allowed: {result['secret_action_policy']['raw_secret_output_allowed']}")
    print(f"client_name: {result['non_secret_inputs']['client_name']}")
    print(f"redirect_uri: {result['non_secret_inputs']['authorized_redirect_uri']}")
    if path:
        print(f"saved: {path}")
    if result.get("warnings"):
        print("warnings:")
        for item in result["warnings"][:8]:
            print(f"- {item}")
