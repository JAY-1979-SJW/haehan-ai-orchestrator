"""Dry-run planning for approval/action EUM workflows."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()
PLANS_DIR = ROOT / "data" / "eum_plans"

_DEVICE_RE = re.compile(r"^[A-Za-z0-9_.:-]{2,80}$")
_PROJECT_RE = re.compile(r"^[A-Za-z0-9_.:-]{2,80}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value).strip("_") or "unknown"


def _validate_registration(args: list[str]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    project_code = args[0] if len(args) >= 1 else ""
    device_id = args[1] if len(args) >= 2 else ""
    location = args[2] if len(args) >= 3 else ""

    if not project_code:
        errors.append("project_code is required")
    elif not _PROJECT_RE.match(project_code):
        errors.append("project_code contains unsupported characters")

    if not device_id:
        errors.append("device_id is required")
    elif not _DEVICE_RE.match(device_id):
        errors.append("device_id contains unsupported characters")

    if not location:
        errors.append("location is required")

    return {
        "project_code": project_code,
        "device_id": device_id,
        "location": location,
    }, errors


def _validate_deregistration(args: list[str]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    device_id = args[0] if len(args) >= 1 else ""
    date = args[1] if len(args) >= 2 else ""

    if not device_id:
        errors.append("device_id is required")
    elif not _DEVICE_RE.match(device_id):
        errors.append("device_id contains unsupported characters")

    if date and not _DATE_RE.match(date):
        errors.append("date must use YYYY-MM-DD")

    return {
        "device_id": device_id,
        "date": date or None,
    }, errors


def build_action_plan(workflow: dict[str, Any], args: list[str], *, mode: str = "dry_run_plan") -> dict[str, Any]:
    """Build a dry-run plan for an approval workflow without touching EUM."""
    key = str(workflow.get("key") or "")
    if key == "device_registration":
        inputs, errors = _validate_registration(args)
        steps = [
            "Open EUM and ensure login",
            "Navigate to WEBMAN381M00",
            "Fill project code, device id, and location",
            "Stop before final submit until approval gate passes",
        ]
    elif key == "device_deregistration":
        inputs, errors = _validate_deregistration(args)
        steps = [
            "Open EUM and ensure login",
            "Navigate to WEBMAN382M00",
            "Fill device id and optional removal date",
            "Stop before final submit until approval gate passes",
        ]
    else:
        inputs, errors = {"args": args}, ["unsupported approval workflow"]
        steps = []

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow_key": workflow.get("key"),
        "workflow_title": workflow.get("title"),
        "risk": workflow.get("risk"),
        "code": workflow.get("code"),
        "command": workflow.get("command"),
        "mode": mode,
        "valid": not errors,
        "errors": errors,
        "inputs": inputs,
        "steps": steps,
        "will_submit": False,
    }


def save_action_plan(plan: dict[str, Any], path: Path | None = None) -> Path:
    key = _safe_name(str(plan.get("workflow_key") or "unknown"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = path or (PLANS_DIR / key / f"{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def print_action_plan(plan: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("EUM approval dry-run plan")
    print("=" * 60)
    print(f"workflow: {plan.get('workflow_key')}")
    print(f"code: {plan.get('code') or '-'}")
    print(f"valid: {plan.get('valid')}")
    print(f"will_submit: {plan.get('will_submit')}")
    if plan.get("errors"):
        print("errors:")
        for error in plan["errors"]:
            print(f"  - {error}")
    if path:
        print(f"saved: {path}")
