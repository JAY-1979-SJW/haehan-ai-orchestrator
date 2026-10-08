"""live_inputs CDP 폴백 채우기 (leaf): action key 별 _cdp_fill_* 분기.

config·cdp·fill(공유 leaf) 의존. 파사드(live_inputs)를 import 하지 않는다.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from scripts.google.common.live_inputs_config import DOMAIN_SPECIFIC_PREFILL_MODES, LIVE_INPUT_ADAPTERS, _cdp_wait
from scripts.google.common.live_inputs_fill import _cdp_click_first_selector, _cdp_click_text, _cdp_detect_file_input, _cdp_fill_domain_specific_input_handoff, _cdp_fill_first, _cdp_fill_generic_input_handoff, _cdp_verify_gmail_compose_values


def _cdp_fill_gmail_send(session: Any, values: dict, result: dict) -> None:
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
    result.setdefault("clicked_nonfinal_controls", []).append({"field": "compose", "method": "gmail_compose_url"})
    _cdp_wait(session, 2.0)
    _cdp_verify_gmail_compose_values(session, values, result)
    _cdp_detect_file_input(session, values.get("attachment_path", ""), "attachment_path", result)
    result["warnings"].append("CDP fallback did not click Send.")


def _cdp_fill_youtube_upload(session: Any, values: dict, result: dict) -> None:
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


def _cdp_fill_youtube_metadata(session: Any, values: dict, result: dict) -> None:
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


def _cdp_fill_search_console(session: Any, key: str, values: dict, result: dict) -> None:
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


def _cdp_fill_iam_change_role(session: Any, values: dict, result: dict) -> None:
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
        opened_panel = _cdp_click_text(session, ["Grant access", "권한 부여", "Add"], result, "grant_access_panel")
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


def _cdp_fill_credential_fields(session: Any, values: dict, result: dict) -> None:
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


def _cdp_fill_by_key(session: Any, action: dict, values: dict, result: dict) -> None:
    """action key 별 CDP 폴백 채우기 분기."""
    key = action["key"]
    if key == "gmail_send_email":
        _cdp_fill_gmail_send(session, values, result)
    elif key == "youtube_studio_upload_video":
        _cdp_fill_youtube_upload(session, values, result)
    elif key == "youtube_studio_edit_video_metadata":
        _cdp_fill_youtube_metadata(session, values, result)
    elif key in ("search_console_submit_indexing", "search_console_submit_sitemap"):
        _cdp_fill_search_console(session, key, values, result)
    elif key == "cloud_iam_change_role":
        _cdp_fill_iam_change_role(session, values, result)
    elif key in ("cloud_create_api_credential", "ai_studio_create_api_key", "play_console_prepare_release"):
        _cdp_fill_credential_fields(session, values, result)
    elif LIVE_INPUT_ADAPTERS.get(key) in DOMAIN_SPECIFIC_PREFILL_MODES:
        _cdp_fill_domain_specific_input_handoff(session, action, values, result)
    else:
        _cdp_fill_generic_input_handoff(session, action, values, result)
