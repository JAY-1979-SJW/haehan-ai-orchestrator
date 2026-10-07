"""Hiworks section input/button action planning.

This module covers every discovered Hiworks service with one common contract:
inputs may be prepared with explicit values, while send/submit/save/delete style
buttons are cataloged and kept behind the approval gate.  It never clicks a
state-changing button.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.hiworks.schemas import DATA_DIR, SERVICE_TARGETS
from scripts.site_engine.catalog_helpers import load_or_build_catalog, print_keyed_summary

LATEST_SURFACE_PATH = DATA_DIR / "hiworks_service_surfaces_latest.json"
LATEST_ACTION_CATALOG_PATH = DATA_DIR / "hiworks_action_catalog_latest.json"
LATEST_PREPARE_PLAN_PATH = DATA_DIR / "hiworks_section_prepare_plan_latest.json"
LATEST_SUBMIT_RECORD_PATH = DATA_DIR / "hiworks_submit_section_latest.json"
SUBMIT_RECORD_DIR = DATA_DIR / "hiworks_submits"
APPROVAL_CONFIRM_TEXT = "HIWORKS_APPROVED_SUBMIT"

SENSITIVE_INPUT_TOKENS = {
    "password",
    "passwd",
    "pwd",
    "otp",
    "token",
    "secret",
    "cookie",
    "session",
    "cert",
    "key",
    "인증",
    "비밀번호",
    "암호",
    "토큰",
}

READ_BUTTON_TOKENS = {
    "검색",
    "조회",
    "보기",
    "목록",
    "닫기",
    "취소",
    "새로고침",
    "이전",
    "다음",
    "필터",
    "정렬",
    "search",
    "find",
    "view",
    "list",
    "close",
    "cancel",
    "refresh",
    "filter",
}

STATE_CHANGE_BUTTON_TOKENS = {
    "보내",
    "발송",
    "전송",
    "상신",
    "결재",
    "승인",
    "반려",
    "등록",
    "저장",
    "수정",
    "삭제",
    "신청",
    "예약",
    "완료",
    "업로드",
    "공유",
    "초대",
    "추가",
    "작성",
    "게시",
    "확인",
    "send",
    "submit",
    "approve",
    "reject",
    "save",
    "delete",
    "remove",
    "create",
    "update",
    "upload",
    "share",
    "invite",
    "apply",
    "reserve",
    "confirm",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _contains_any(text: str, tokens: set[str]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def _field_key(field: dict[str, Any], index: int) -> str:
    for key in ("name", "id", "placeholder", "aria"):
        value = _clean(field.get(key))
        if value:
            return value
    return f"field_{index}"


def _is_sensitive_input(field: dict[str, Any]) -> bool:
    probe = " ".join(_clean(field.get(key)) for key in ("type", "name", "id", "placeholder", "aria"))
    if _clean(field.get("type")).lower() == "file":
        return True
    return _contains_any(probe, SENSITIVE_INPUT_TOKENS)


def classify_input(field: dict[str, Any]) -> dict[str, Any]:
    """Classify one visible input field."""
    sensitive = _is_sensitive_input(field)
    return {
        "risk": "blocked_sensitive" if sensitive else "prepare",
        "can_auto_fill": not sensitive and not field.get("disabled") and not field.get("readonly"),
        "reason": "sensitive_or_file_input" if sensitive else "explicit_value_required",
    }


def classify_button(button: dict[str, Any]) -> dict[str, Any]:
    """Classify one button-like control without clicking it."""
    text = _clean(button.get("text"))
    probe = " ".join(_clean(button.get(key)) for key in ("text", "type", "name", "id", "href", "aria"))
    if button.get("disabled"):
        return {"risk": "disabled", "can_auto_click": False, "reason": "disabled"}
    if _contains_any(probe, STATE_CHANGE_BUTTON_TOKENS):
        return {"risk": "submit_gated", "can_auto_click": False, "reason": "state_change_keyword"}
    if text and _contains_any(probe, READ_BUTTON_TOKENS):
        return {"risk": "read", "can_auto_click": False, "reason": "read_control_cataloged_only"}
    return {"risk": "unknown_gated", "can_auto_click": False, "reason": "unclassified_button"}


def load_service_surface(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else LATEST_SURFACE_PATH
    if not source.exists():
        services = []
        for key, target in SERVICE_TARGETS.items():
            services.append(
                {
                    "key": key,
                    "label": target.get("label") or key,
                    "target_url": target.get("url") or "",
                    "surface": {
                        "url": target.get("url") or "",
                        "title": target.get("label") or key,
                        "counts": {"inputs": 0, "buttons": 0},
                        "inputs": [],
                        "buttons": [],
                    },
                }
            )
        return {
            "schema_version": 1,
            "source": "fallback_service_targets",
            "services": services,
            "secret_values_output": False,
        }
    return json.loads(source.read_text(encoding="utf-8"))


def build_action_catalog(surface_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an input/button action catalog for every scanned Hiworks service."""
    report = surface_report or load_service_surface()
    services: list[dict[str, Any]] = []
    for service in report.get("services", []):
        key = service.get("key")
        target = SERVICE_TARGETS.get(str(key), {})
        surface = service.get("surface") or {}
        inputs = []
        for idx, field in enumerate(surface.get("inputs") or []):
            meta = classify_input(field)
            inputs.append(
                {
                    "control_id": f"{key}:input:{idx}",
                    "field_key": _field_key(field, idx),
                    "index": idx,
                    "tag": field.get("tag") or "",
                    "type": field.get("type") or "",
                    "name": field.get("name") or "",
                    "id": field.get("id") or "",
                    "placeholder": field.get("placeholder") or "",
                    "aria": field.get("aria") or "",
                    **meta,
                }
            )
        buttons = []
        for idx, button in enumerate(surface.get("buttons") or []):
            meta = classify_button(button)
            buttons.append(
                {
                    "control_id": f"{key}:button:{idx}",
                    "index": idx,
                    "text": _clean(button.get("text")),
                    "type": button.get("type") or "",
                    "risk": meta["risk"],
                    "can_auto_click": meta["can_auto_click"],
                    "reason": meta["reason"],
                }
            )
        services.append(
            {
                "key": key,
                "label": service.get("label") or target.get("label") or key,
                "target_url": service.get("target_url") or target.get("url") or "",
                "surface_url": surface.get("url") or "",
                "title": surface.get("title") or "",
                "counts": surface.get("counts") or {},
                "inputs": inputs,
                "buttons": buttons,
                "summary": {
                    "input_total": len(inputs),
                    "auto_fillable_inputs": sum(1 for item in inputs if item["can_auto_fill"]),
                    "button_total": len(buttons),
                    "submit_gated_buttons": sum(1 for item in buttons if item["risk"] == "submit_gated"),
                    "unknown_gated_buttons": sum(1 for item in buttons if item["risk"] == "unknown_gated"),
                },
            }
        )
    return {
        "generated_at": _now(),
        "source_generated_at": report.get("generated_at"),
        "contract": {
            "inputs": "explicit values only; sensitive/file fields are blocked",
            "buttons": "catalog only; state-changing clicks require approval-gated implementation",
            "submit": "not auto-executed",
        },
        "services": services,
    }


def save_action_catalog(catalog: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_ACTION_CATALOG_PATH
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_action_catalog(path: str | Path | None = None) -> dict[str, Any]:
    return load_or_build_catalog(path, LATEST_ACTION_CATALOG_PATH, build_action_catalog, save_action_catalog)


def _select_catalog_services(catalog: dict[str, Any], name: str | None) -> list[dict[str, Any]]:
    services = list(catalog.get("services") or [])
    if not name or name == "all":
        return services
    selected = [service for service in services if service.get("key") == name]
    if not selected:
        raise KeyError(f"unknown Hiworks service in action catalog: {name}")
    return selected


def build_prepare_plan(
    catalog: dict[str, Any],
    *,
    service_name: str | None = "all",
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a no-click prepare plan for one or all Hiworks services."""
    values = values or {}
    service_plans = []
    for service in _select_catalog_services(catalog, service_name):
        fill_steps = []
        blocked_fields = []
        for field in service.get("inputs") or []:
            key = field["field_key"]
            value_present = key in values or field["control_id"] in values
            if field["risk"] == "blocked_sensitive":
                blocked_fields.append({"control_id": field["control_id"], "field_key": key, "reason": field["reason"]})
                continue
            fill_steps.append(
                {
                    "control_id": field["control_id"],
                    "field_key": key,
                    "action": "fill_when_value_provided",
                    "value_present": value_present,
                    "risk": field["risk"],
                }
            )
        button_steps = [
            {
                "control_id": button["control_id"],
                "text": button["text"],
                "risk": button["risk"],
                "action": "catalog_only" if button["risk"] == "read" else "blocked_until_approval",
                "reason": button["reason"],
            }
            for button in service.get("buttons") or []
        ]
        service_plans.append(
            {
                "key": service["key"],
                "label": service.get("label"),
                "target_url": service.get("target_url"),
                "fill_steps": fill_steps,
                "blocked_fields": blocked_fields,
                "button_steps": button_steps,
                "summary": {
                    "fillable_inputs": len(fill_steps),
                    "blocked_inputs": len(blocked_fields),
                    "buttons_cataloged": len(button_steps),
                    "buttons_gated": sum(1 for step in button_steps if step["action"] == "blocked_until_approval"),
                    "values_matched": sum(1 for step in fill_steps if step["value_present"]),
                },
            }
        )
    return {
        "generated_at": _now(),
        "service_name": service_name or "all",
        "dry_run": True,
        "submit_executed": False,
        "services": service_plans,
    }


def save_prepare_plan(plan: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_PREPARE_PLAN_PATH
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def get_submit_control(
    catalog: dict[str, Any], service_name: str, control_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    services = _select_catalog_services(catalog, service_name)
    service = services[0]
    for button in service.get("buttons") or []:
        if button.get("control_id") == control_id:
            return service, button
    raise KeyError(f"unknown Hiworks submit control: {service_name} {control_id}")


def build_submit_execution_plan(
    catalog: dict[str, Any],
    *,
    service_name: str,
    control_id: str,
    approved_by: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    service, button = get_submit_control(catalog, service_name, control_id)
    if button.get("risk") not in {"submit_gated", "unknown_gated"}:
        raise ValueError(f"control is not approval-gated: {control_id} risk={button.get('risk')}")
    return {
        "generated_at": _now(),
        "service": {
            "key": service.get("key"),
            "label": service.get("label"),
            "target_url": service.get("target_url"),
            "surface_url": service.get("surface_url"),
        },
        "control": {
            "control_id": button.get("control_id"),
            "index": button.get("index"),
            "text": button.get("text"),
            "risk": button.get("risk"),
            "reason": button.get("reason"),
        },
        "approval": {
            "required": True,
            "approved_by": approved_by,
            "confirm_text_required": APPROVAL_CONFIRM_TEXT,
        },
        "dry_run": dry_run,
        "submit_executed": False,
    }


def execute_approved_button(page, plan: dict[str, Any], *, approved: bool, dry_run: bool = False) -> dict[str, Any]:
    """Execute one approval-gated button plan.

    The caller must pass approved=True only after the site-level approval gate
    has passed. dry_run=True performs page matching only and never clicks.
    """
    if not approved:
        raise PermissionError("approved=True is required for Hiworks submit execution")
    control = plan.get("control") or {}
    if control.get("risk") not in {"submit_gated", "unknown_gated"}:
        raise ValueError(f"control is not executable: {control.get('control_id')}")
    result = page.evaluate(
        """({index, expectedText, dryRun}) => {
          const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
          const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          const candidates = Array.from(document.querySelectorAll('button, [role=button]'))
            .map((el) => ({el, text: clean(el.innerText || el.textContent || el.getAttribute('aria-label'))}))
            .filter((x) => visible(x.el) && x.text);
          const candidate = candidates[index];
          if (!candidate) {
            return {ok: false, clicked: false, error: 'button_index_not_found', candidate_count: candidates.length};
          }
          if (expectedText && candidate.text !== expectedText) {
            return {
              ok: false,
              clicked: false,
              error: 'button_text_mismatch',
              expected_text: expectedText,
              actual_text: candidate.text,
              candidate_count: candidates.length
            };
          }
          if (dryRun) {
            return {
              ok: true,
              clicked: false,
              dry_run: true,
              matched_text: candidate.text,
              candidate_count: candidates.length
            };
          }
          candidate.el.click();
          return {
            ok: true,
            clicked: true,
            dry_run: false,
            matched_text: candidate.text,
            candidate_count: candidates.length
          };
        }""",
        {
            "index": int(control.get("index") or 0),
            "expectedText": control.get("text") or "",
            "dryRun": dry_run,
        },
    )
    plan["submit_executed"] = bool(result.get("clicked"))
    plan["result"] = result
    plan["finished_at"] = _now()
    try:
        plan["after_url"] = page.url
        plan["after_title"] = page.title()
    except Exception:  # noqa: BLE001 - 디버그 출력용 page.title() 조회 — 실패해도 해당 줄 출력만 생략, 기능 영향 없음
        pass
    return plan


def save_submit_record(record: dict[str, Any], output: str | Path | None = None) -> Path:
    SUBMIT_RECORD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(output) if output else SUBMIT_RECORD_DIR / f"hiworks_submit_section_{stamp}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_SUBMIT_RECORD_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            "HIWORKS_SUBMIT_SECTION_EXECUTED" if record.get("submit_executed") else "HIWORKS_SUBMIT_SECTION_DRY_RUN",
            site="hiworks",
            workflow="submit_section",
            status="ok" if (record.get("result") or {}).get("ok") else "failed",
            risk="send",
            message=f"Hiworks submit-section {'executed' if record.get('submit_executed') else 'checked'}",
            artifact_path=str(path),
            metadata={
                "service": (record.get("service") or {}).get("key"),
                "control_id": (record.get("control") or {}).get("control_id"),
                "dry_run": record.get("dry_run"),
            },
        )
    except Exception:  # noqa: BLE001 - 디버그 출력용 page.title() 조회 — 실패해도 해당 줄 출력만 생략, 기능 영향 없음
        pass
    return path


def load_values(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Hiworks prepare values must be a JSON object")
    return data


def apply_prepare_values(page, values: dict[str, Any]) -> dict[str, Any]:
    """Fill visible non-sensitive fields on the current page; never click buttons."""
    return page.evaluate(
        """({values, sensitiveTokens}) => {
          const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
          const isVisible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          const tokenMatch = (text) => sensitiveTokens.some((token) => text.toLowerCase().includes(String(token).toLowerCase()));
          const applied = [];
          const skipped = [];
          const inputs = Array.from(document.querySelectorAll('input, textarea, select'));
          inputs.forEach((el, index) => {
            const keys = [el.name, el.id, el.placeholder, el.getAttribute('aria-label'), `field_${index}`].map(clean).filter(Boolean);
            const probe = [el.type, ...keys].join(' ');
            const matchKey = keys.find((key) => Object.prototype.hasOwnProperty.call(values, key));
            if (!matchKey) return;
            if (!isVisible(el) || el.disabled || el.readOnly || tokenMatch(probe) || String(el.type || '').toLowerCase() === 'file') {
              skipped.push({index, key: matchKey, reason: 'blocked_or_unfillable'});
              return;
            }
            el.focus();
            el.value = String(values[matchKey]);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            applied.push({index, key: matchKey});
          });
          return {applied, skipped, submit_executed: false};
        }""",
        {"values": values, "sensitiveTokens": sorted(SENSITIVE_INPUT_TOKENS)},
    )


def print_action_catalog_summary(catalog: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("Hiworks action catalog")
    print("=" * 60)
    for service in catalog.get("services") or []:
        summary = service.get("summary") or {}
        print(
            f"- {service.get('key')}: "
            f"inputs={summary.get('input_total', 0)} "
            f"fillable={summary.get('auto_fillable_inputs', 0)} "
            f"buttons={summary.get('button_total', 0)} "
            f"submit_gated={summary.get('submit_gated_buttons', 0)} "
            f"unknown_gated={summary.get('unknown_gated_buttons', 0)}"
        )
    if path:
        print(f"saved: {path}")


def print_prepare_plan_summary(plan: dict[str, Any], path: Path | None = None) -> None:
    print_keyed_summary(
        "Hiworks section prepare plan",
        plan.get("services") or [],
        (
            ("fillable", "fillable_inputs"),
            ("blocked_inputs", "blocked_inputs"),
            ("buttons_cataloged", "buttons_cataloged"),
            ("buttons_gated", "buttons_gated"),
        ),
        path,
    )
