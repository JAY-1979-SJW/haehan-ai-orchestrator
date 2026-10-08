"""YouTube Studio upload pre-approval planning.

This module intentionally stops before selecting a file in YouTube Studio.
Selecting a file can create an upload draft, so the safe automation boundary is
local validation, metadata planning, page-tab labeling, and no-final-submit UI
inspection.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root
from scripts.google.common import workflows
from scripts.google.common.domain_taxonomy import build_google_page_tab_catalog

ROOT = repo_root()
REPORT_DIR = ROOT / "data" / "google_youtube_upload_plans"
LATEST_PLAN = ROOT / "data" / "google_youtube_upload_plan_latest.json"

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mpeg", ".mpg", ".avi"}
ALLOWED_VISIBILITY = {"private", "unlisted", "public"}
RECOMMENDED_TITLE_MAX = 100
RECOMMENDED_DESCRIPTION_MAX = 5000


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def build_youtube_upload_plan(values: dict[str, str]) -> dict[str, Any]:
    video_path = values.get("video_path", "").strip()
    title = values.get("title", "").strip()
    description = values.get("description", "").strip()
    visibility = values.get("visibility", "private").strip().lower()
    made_for_kids = values.get("made_for_kids", "").strip().lower()
    tags = values.get("tags", "").strip()

    resolved = _resolve_path(video_path) if video_path else Path()
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    checks.append({"key": "video_path_present", "ok": bool(video_path)})
    checks.append({"key": "video_file_exists", "ok": bool(video_path) and resolved.exists(), "path": str(resolved) if video_path else ""})
    checks.append({"key": "video_extension_allowed", "ok": bool(video_path) and resolved.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS, "extension": resolved.suffix.lower() if video_path else ""})
    checks.append({"key": "title_present", "ok": bool(title)})
    checks.append({"key": "title_length", "ok": bool(title) and len(title) <= RECOMMENDED_TITLE_MAX, "length": len(title)})
    checks.append({"key": "description_length", "ok": len(description) <= RECOMMENDED_DESCRIPTION_MAX, "length": len(description)})
    checks.append({"key": "visibility_allowed", "ok": visibility in ALLOWED_VISIBILITY, "visibility": visibility})
    checks.append({"key": "made_for_kids_declared", "ok": made_for_kids in {"yes", "no"}, "value": made_for_kids})

    if visibility == "public":
        warnings.append("public visibility requires an explicit final approval and should not be used for dry-run upload planning.")
    if not made_for_kids:
        warnings.append("made_for_kids must be declared before real upload handoff.")

    workflow_plan, workflow_path = workflows.prepare_action(
        "youtube_studio_upload_video",
        {
            "video_path": video_path,
            "title": title,
            "description": description,
            "visibility": visibility,
        },
    )

    ok = all(item["ok"] for item in checks)
    page_tabs = build_google_page_tab_catalog("youtube")["surfaces"]
    return {
        "site_id": "google",
        "surface_key": "youtube_studio",
        "action_key": "youtube_studio_upload_video",
        "generated_at": _utc(),
        "status": "ready_for_user_approval_handoff" if ok else "blocked_missing_or_invalid_inputs",
        "safe_automation_boundary": {
            "local_file_validation": "allowed",
            "metadata_validation": "allowed",
            "studio_page_read": "allowed",
            "file_select_upload_draft": "approval_required",
            "next_publish_or_visibility_submit": "blocked_without_approval_phrase",
            "final_publish": "blocked_without_approval_phrase",
        },
        "inputs": {
            "video_path": video_path,
            "resolved_video_path": str(resolved) if video_path else "",
            "title": title,
            "description": description,
            "visibility": visibility,
            "made_for_kids": made_for_kids,
            "tags": [item.strip() for item in tags.split(",") if item.strip()],
        },
        "checks": checks,
        "warnings": warnings,
        "workflow_prepare_path": str(workflow_path),
        "workflow_ready_for_approval": workflow_plan["ready_for_approval"],
        "workflow_missing_inputs": workflow_plan["missing_inputs"],
        "youtube_page_tabs": page_tabs,
        "commands": {
            "prepare": "python scripts/entry/cdp_cli.py google youtube upload-prepare video_path=... title=... description=... visibility=private",
            "preapproval_check": "python scripts/entry/cdp_cli.py google youtube upload-check video_path=... title=... description=... visibility=private made_for_kids=no",
            "live_no_final_submit": f"python scripts/entry/cdp_cli.py google youtube upload-live-fill {workflow_path} --no-final-submit",
        },
    }


def save_youtube_upload_plan(values: dict[str, str]) -> tuple[dict[str, Any], Path]:
    plan = build_youtube_upload_plan(values)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_PLAN.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"youtube_upload_plan_{timestamp}.json"
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LATEST_PLAN.write_text(text, encoding="utf-8")
    return plan, path


def print_youtube_upload_plan(plan: dict[str, Any], path: Path) -> None:
    print("=" * 60)
    print("YouTube upload pre-approval plan")
    print("=" * 60)
    print(f"status: {plan['status']}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_PLAN}")
    print(f"workflow_prepare_path: {plan['workflow_prepare_path']}")
    print(f"workflow_ready_for_approval: {plan['workflow_ready_for_approval']}")
    failed = [item["key"] for item in plan["checks"] if not item["ok"]]
    print(f"failed_checks: {', '.join(failed) if failed else '-'}")
    print("approval_boundary: file_select_upload_draft and publish remain approval-gated")


__all__ = [
    "ALLOWED_VIDEO_EXTENSIONS",
    "ALLOWED_VISIBILITY",
    "LATEST_PLAN",
    "build_youtube_upload_plan",
    "print_youtube_upload_plan",
    "save_youtube_upload_plan",
]
