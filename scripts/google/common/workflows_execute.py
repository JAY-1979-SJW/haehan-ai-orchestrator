"""Prepare, execute, and verify Google work actions."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from scripts.google.common.workflows_common import EXECUTION_DIR, LATEST_PREPARE, PREPARE_DIR, VERIFICATION_DIR, _adapter_profile_for_action, _open_target_readonly, _redact_values
from scripts.google.common.workflows_actions import get_action


def prepare_action(action_key: str, values: dict[str, str] | None = None) -> tuple[dict, Path]:
    values = values or {}
    action = get_action(action_key)
    missing = [name for name in action.required_inputs if not values.get(name)]
    ready = not missing
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    PREPARE_DIR.mkdir(parents=True, exist_ok=True)
    path = PREPARE_DIR / f"google_prepare_{action.key}_{timestamp}.json"
    command_path = f'"{path}"' if " " in str(path) else str(path)
    plan = {
        "site_id": "google",
        "action": asdict(action),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "ready_for_approval": ready,
        "dry_run": True,
        "state_change": False,
        "provided_inputs": _redact_values(values),
        "missing_inputs": missing,
        "approval": {
            "required": action.requires_approval,
            "approved": False,
            "required_phrase": action.approval_phrase if action.requires_approval else "",
        },
        "execution_gate": {
            "status": "blocked_until_approved" if action.requires_approval else "read_only_ready",
            "execute_mode": action.execute_mode,
            "command": (
                f"python scripts\\entry\\cdp_cli.py google work execute {command_path} "
                f"--approved --confirm={action.approval_phrase}"
            ),
        },
        "verify_log": {
            "required": ["result_url_or_id", "visible_confirmation", "audit_record"],
            "artifact_dir": str(EXECUTION_DIR),
        },
    }
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LATEST_PREPARE.parent.mkdir(parents=True, exist_ok=True)
    LATEST_PREPARE.write_text(text, encoding="utf-8")
    return plan, path


def execute_prepared_action(
    plan_path: str | Path,
    *,
    approved: bool = False,
    confirm: str = "",
    live_open: bool = False,
) -> tuple[dict, Path]:
    path = Path(plan_path)
    plan = json.loads(path.read_text(encoding="utf-8"))
    action = plan["action"]
    missing = plan.get("missing_inputs", [])
    required_phrase = plan.get("approval", {}).get("required_phrase", "")
    allowed = bool(approved) and (not required_phrase or confirm == required_phrase) and not missing
    adapter = _adapter_profile_for_action(get_action(action["key"]))
    result = {
        "site_id": "google",
        "action_key": action["key"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "approved": bool(approved),
        "confirm_matched": confirm == required_phrase if required_phrase else True,
        "ready_for_approval": bool(plan.get("ready_for_approval")),
        "state_change": False,
        "status": "blocked",
        "reason": "",
        "target_url": action["target_url"],
        "execute_mode": action["execute_mode"],
        "adapter": asdict(adapter),
        "browser_navigation": {},
        "verification_required": adapter.verification_checks,
    }
    if not allowed:
        if missing:
            result["reason"] = f"missing inputs: {', '.join(missing)}"
        elif action["requires_approval"] and not approved:
            result["reason"] = "approval flag required"
        elif action["requires_approval"] and confirm != required_phrase:
            result["reason"] = "approval phrase mismatch"
        else:
            result["reason"] = "execution gate blocked"
    else:
        result["status"] = "approved_handoff_ready"
        result["reason"] = (
            "approval accepted; surface-specific adapter or manual final "
            "confirmation may now run under audit logging"
        )
        result["state_change"] = False
        result["next_step"] = action["target_url"]
        if live_open:
            result["browser_navigation"] = _open_target_readonly(action["target_url"])
    EXECUTION_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = EXECUTION_DIR / f"google_execute_{action['key']}_{timestamp}.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result, target


def verify_execution_result(result_path: str | Path) -> tuple[dict, Path]:
    path = Path(result_path)
    result = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "has_action_key": bool(result.get("action_key")),
        "has_status": bool(result.get("status")),
        "state_change_false_until_final_confirmation": result.get("state_change") is False,
        "adapter_profile_present": bool(result.get("adapter", {}).get("adapter_key")),
        "blocked_or_handoff_state": result.get("status") in {"blocked", "approved_handoff_ready"},
    }
    verification = {
        "site_id": "google",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "result_path": str(path),
        "action_key": result.get("action_key"),
        "status": "verified" if all(checks.values()) else "failed",
        "checks": checks,
        "next_required_evidence": result.get("verification_required", []),
    }
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = VERIFICATION_DIR / f"google_verify_{result.get('action_key', 'unknown')}_{timestamp}.json"
    target.write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    return verification, target
