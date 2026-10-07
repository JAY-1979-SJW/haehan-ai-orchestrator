"""live_inputs CDP fill 프리미티브 (공유 leaf).

셀렉터/클릭/입력/검증 등 저수준 fill 동작. config·cdp(공유 leaf) 의존,
도메인 filler 들이 공유한다. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.google.common.live_inputs_config import FINAL_CONTROL_LABELS, LIVE_INPUT_ADAPTERS, ROOT


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


def _domain_prefill_selectors(action: dict, field: str) -> list[str]:
    selectors = _generic_selectors(field)
    surface = action.get("surface_key", "")
    operation = action.get("operation", "")
    field_key = field.lower()
    if surface in {"drive", "photos", "youtube_studio", "play_console"} and any(
        token in field_key for token in ("path", "file", "artifact", "media", "video", "photo")
    ):
        return ['input[type="file"]'] + selectors
    if surface in {"chat", "gemini", "keep"} or field_key in {"body", "message", "prompt", "content", "release_notes"}:
        return selectors + ['[contenteditable="true"]', '[role="textbox"]']
    if "url" in field_key:
        return ['input[type="url"]'] + selectors
    if "email" in field_key or "attendees" in field_key or "share_target" in field_key:
        return ['input[type="email"]'] + selectors
    if operation in {"deploy", "release", "create", "change", "publish"}:
        return selectors + ['[role="textbox"]']
    return selectors


def _cdp_fill_first(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
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
        })("""
        + json.dumps(selectors)
        + ", "
        + json.dumps(value)
        + ", "
        + json.dumps(press_enter)
        + ", "
        + json.dumps(contenteditable)
        + ")"
    )
    if not err and isinstance(data, dict) and data.get("ok"):
        result["filled_fields"].append(field)
        return True
    result["skipped_fields"].append(field)
    result["warnings"].append(f"field not found by CDP: {field}")
    return False


def _record_cdp_click(data: Any, err: Any, result: dict, field: str, warning: str) -> bool:
    """CDP 클릭 JS 결과를 result 에 기록한다 — 성공이면 clicked_nonfinal_controls 에 추가, 실패면 warning 을 남긴다."""
    if not err and isinstance(data, dict) and data.get("ok"):
        result.setdefault("clicked_nonfinal_controls", []).append({"field": field, **data})
        return True
    result["warnings"].append(warning)
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
        })("""
        + json.dumps(selectors)
        + ")"
    )
    return _record_cdp_click(data, err, result, field, f"button selector not found by CDP: {field}")


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
        })("""
        + json.dumps(labels)
        + ")"
    )
    return _record_cdp_click(data, err, result, field, f"button not found by CDP: {field}")


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


def _cdp_fill_domain_specific_input_handoff(session: Any, action: dict, values: dict, result: dict) -> None:
    result["adapter_mode"] = LIVE_INPUT_ADAPTERS.get(action["key"], "safe_domain_specific_prefill")
    result["prefill_scope"] = action.get("surface_key", "")
    for field in action.get("required_inputs", []):
        value = str(values.get(field, ""))
        if not value or value == "[redacted]":
            result["skipped_fields"].append(field)
            continue
        _cdp_fill_first(session, _domain_prefill_selectors(action, field), value, field, result)
    for field, value in values.items():
        if field in action.get("required_inputs", []):
            continue
        value = str(value)
        if not value or value == "[redacted]":
            continue
        _cdp_fill_first(session, _domain_prefill_selectors(action, field), value, field, result)
    result["final_approval_boundary"] = "user_clicks_final_visible_control"
    result["warnings"].append(
        f"Domain-specific CDP prefill ran for {action.get('surface_key')}; final submit/save/publish/deploy/create control was not clicked."
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
        })("""
        + json.dumps(
            {
                "to": values.get("to", ""),
                "subject": values.get("subject", ""),
                "body": values.get("body", ""),
            }
        )
        + ")"
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
        })("""
        + json.dumps(list(FINAL_CONTROL_LABELS))
        + ")"
    )
    return data if not err and isinstance(data, list) else []
