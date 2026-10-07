"""live_inputs 도메인별 fill 핸들러 (leaf).

gmail/cloud/search_console/youtube/ai_studio/play_console 등 서비스별 입력 핸들러.
config·fill·cdp(공유 leaf) 의존. dispatch(루트)가 호출. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.google.common.live_inputs_config import FINAL_CONTROL_LABELS, LATEST_LIVE_INPUT, LATEST_LIVE_INPUT_MANIFEST, LIVE_INPUT_ADAPTERS, LIVE_INPUT_DIR, LIVE_INPUT_MANIFEST_DIR, ROOT, _locator_timeout, _page_timeout, _page_wait
from scripts.google.common.live_inputs_fill import _domain_prefill_selectors, _generic_selectors, _safe_to_generic_fill


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
            except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
        ['button[instrumentationid="iam-add-member"]', "iam-add-member-action button"],
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
            except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
    except Exception as exc:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
        result["skipped_fields"].append("video_path")
        result["warnings"].append(f"file input failed: {exc}")
    _fill_first(
        page, ['input[aria-label*="Title"]', 'textarea[aria-label*="Title"]'], values.get("title", ""), "title", result
    )
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
            "ytcp-button#create-icon",
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
    except Exception as exc:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
    result["warnings"].append("YouTube metadata target lookup only; edit/save/publish controls were not clicked.")


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
    result["adapter_mode"] = "safe_release_final_click_ready"
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
        value = str(values.get(field, ""))
        if not value:
            result["skipped_fields"].append(field)
            continue
        _fill_first(page, _domain_prefill_selectors(action, field), value, field, result)
    result["final_approval_boundary"] = "user_clicks_final_release_control"
    result["warnings"].append(
        "Play Console release screen prepared; final review/rollout/release control was not clicked."
    )


def _fill_domain_specific_input_handoff(page: Any, action: dict, values: dict, result: dict) -> None:
    page.goto(action["target_url"], timeout=_page_timeout(45000), wait_until="domcontentloaded")
    _page_wait(page, 3000)
    result["adapter_mode"] = LIVE_INPUT_ADAPTERS.get(action["key"], "safe_domain_specific_prefill")
    result["prefill_scope"] = action.get("surface_key", "")
    for field in action.get("required_inputs", []):
        value = str(values.get(field, ""))
        if not value or value == "[redacted]":
            result["skipped_fields"].append(field)
            continue
        _fill_first(page, _domain_prefill_selectors(action, field), value, field, result)
    for field, value in values.items():
        if field in action.get("required_inputs", []):
            continue
        value = str(value)
        if not value or value == "[redacted]":
            continue
        _fill_first(page, _domain_prefill_selectors(action, field), value, field, result)
    result["final_approval_boundary"] = "user_clicks_final_visible_control"
    result["warnings"].append(
        f"Domain-specific Google prefill ran for {action.get('surface_key')}; final submit/save/publish/deploy/create control was not clicked."
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
                    except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
                        page.keyboard.type(value, delay=5)
                    if press_enter:
                        page.keyboard.press("Enter")
                    result["filled_fields"].append(field)
                    return True
            except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
            except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
            except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
    except Exception:  # noqa: BLE001 - 여러 셀렉터/프레임을 순차 시도하는 best-effort — 하나 실패해도 다음으로 계속(2026-09-28 검토)
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
                    result.setdefault("clicked_nonfinal_controls", []).append({"field": field, "selector": selector})
                    return True
            except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
                continue
    return False


def _save_result(result: dict) -> tuple[dict, Path]:
    LIVE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_LIVE_INPUT.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # noqa: UP017
    target = LIVE_INPUT_DIR / f"google_live_input_{result['action_key']}_{timestamp}.json"
    text = json.dumps(result, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_LIVE_INPUT.write_text(text, encoding="utf-8")
    return result, target


def _save_manifest_result(summary: dict) -> tuple[dict, Path]:
    LIVE_INPUT_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_LIVE_INPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # noqa: UP017
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
        except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
        except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
        except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
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
                except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
                    continue
        except Exception:  # noqa: BLE001 - 구글/유튜브 업로드 폼 필드 채우기 — 실패는 result[skipped_fields]/result[warnings]에 투명하게 기록(숨기지 않음), 여러 셀렉터를 순차 시도, 발행류 최종 버튼은 클릭하지 않음(2026-09-28 검토)
            continue
    result["skipped_fields"].append(field)
    result["warnings"].append(f"file input not found for attachment: {field}")
    return False
