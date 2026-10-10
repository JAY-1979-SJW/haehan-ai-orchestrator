"""YouTube upload manifest, gate, and official API upload path."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.core.security_utils import safe_preview
from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import repo_root
from scripts.common.publish_guard import guarded
from scripts.common.realtime_audit import emit_event

ROOT = repo_root()
PLAN_DIR = data_dir() / "youtube_upload_plans"
RESULT_DIR = data_dir() / "youtube_upload_results"
LATEST_PLAN = data_dir() / "youtube_upload_plan_latest.json"
LATEST_RESULT = data_dir() / "youtube_upload_result_latest.json"
APPROVAL_PHRASE = "YOUTUBE_APPROVED_UPLOAD"
ALLOWED_PRIVACY = {"private", "unlisted", "public"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_kv_args(args: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in args:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        values[key.strip().lstrip("-")] = value.strip()
    return values


def _split_tags(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def scan_video_file(path: Path) -> dict[str, Any]:
    exists = path.exists()
    suffix_ok = path.suffix.lower() in VIDEO_EXTENSIONS
    size = path.stat().st_size if exists else 0
    suspicious_name_tokens = ("password", "secret", "token", "cookie", "session", "credential")
    suspicious_name = any(token in path.name.lower() for token in suspicious_name_tokens)
    return {
        "exists": exists,
        "suffix_ok": suffix_ok,
        "size_bytes": size,
        "suspicious_name": suspicious_name,
        "ok": exists and suffix_ok and size > 0 and not suspicious_name,
    }


def prepare_upload_plan(local_path: str | Path, values: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    video_path = Path(local_path)
    if not video_path.is_absolute():
        video_path = ROOT / video_path
    title = str(values.get("title") or video_path.stem)
    description = str(values.get("description") or "")
    privacy = str(values.get("privacy") or values.get("privacy_status") or "private").lower()
    category_id = str(values.get("category_id") or "22")
    tags = _split_tags(str(values.get("tags") or ""))
    thumbnail = str(values.get("thumbnail") or "")
    publish_at = str(values.get("publish_at") or "").strip()  # ISO 8601 예: 2026-06-01T09:00:00+09:00
    token_file = str(values.get("token_file") or values.get("youtube_token_file") or "")
    credentials_file = str(values.get("credentials_file") or values.get("client_secrets_file") or "")

    # 예약 게시: privacyStatus는 반드시 private이어야 함
    if publish_at and privacy != "private":
        privacy = "private"

    file_scan = scan_video_file(video_path)
    metadata_ok = bool(title.strip()) and privacy in ALLOWED_PRIVACY
    plan: dict[str, Any] = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_upload_video",
        "risk": "external_video_upload",
        "local_path": str(video_path),
        "file_scan": file_scan,
        "metadata": {
            "title": safe_preview(title, limit=120),
            "description": safe_preview(description, limit=500),
            "tags": [safe_preview(tag, limit=80) for tag in tags],
            "category_id": category_id,
            "privacy_status": privacy,
            "publish_at": publish_at,
            "thumbnail": thumbnail,
        },
        "auth": {
            "token_file": token_file,
            "credentials_file": credentials_file,
            "requires_oauth": True,
        },
        "approval": {
            "required": True,
            "approved": False,
            "approval_phrase": APPROVAL_PHRASE,
        },
        "ready_for_approval": file_scan["ok"] and metadata_ok,
        "missing_requirements": [],
        "safety_checklist": [
            "Review the video locally before upload.",
            "Confirm no password, token, customer PII, billing, or account screen is visible.",
            "Upload should default to private unless the user explicitly approves public or scheduled publishing.",
            "Public publish remains a separate final approval decision.",
        ],
    }
    if not file_scan["exists"]:
        plan["missing_requirements"].append("local_video_file")
    if not file_scan["suffix_ok"]:
        plan["missing_requirements"].append("supported_video_extension")
    if privacy not in ALLOWED_PRIVACY:
        plan["missing_requirements"].append("valid_privacy_status")

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    path = PLAN_DIR / f"youtube_upload_plan_{_stamp()}.json"
    payload = json.dumps(plan, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    LATEST_PLAN.write_text(payload, encoding="utf-8")
    emit_event(
        "YOUTUBE_UPLOAD_PLAN_PREPARED",
        site="youtube",
        workflow="upload_prepare",
        status="ok" if plan["ready_for_approval"] else "blocked",
        risk="external_video_upload",
        artifact_path=str(path),
        metadata={"local_path": str(video_path), "privacy_status": privacy, "ready": plan["ready_for_approval"]},
    )
    return plan, path


def _upload_with_official_api(plan: dict[str, Any]) -> dict[str, Any]:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except Exception as exc:  # pragma: no cover - depends on local installation  # noqa: BLE001 - 공식 YouTube API 업로드 경로에서 필요한 라이브러리 import 실패 시 ok=False, reason=youtube_api_dependencies_missing 을 반환하는 fail-closed 경로(업로드 진행 안 함).
        return {"ok": False, "reason": "youtube_api_dependencies_missing", "error": str(exc)[:300]}

    token_file = plan.get("auth", {}).get("token_file") or ""
    if not token_file:
        return {"ok": False, "reason": "oauth_token_file_required"}
    token_path = Path(token_file)
    if not token_path.is_absolute():
        token_path = ROOT / token_path
    if not token_path.exists():
        return {"ok": False, "reason": "oauth_token_file_not_found", "token_file": str(token_path)}

    creds = Credentials.from_authorized_user_file(
        str(token_path),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    youtube = build("youtube", "v3", credentials=creds)
    metadata = plan["metadata"]
    status_body: dict[str, Any] = {"privacyStatus": metadata["privacy_status"]}
    publish_at = metadata.get("publish_at", "")
    if publish_at:
        status_body["publishAt"] = publish_at  # ISO 8601, privacyStatus=private 필수
    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": metadata["category_id"],
        },
        "status": status_body,
    }
    media = MediaFileUpload(plan["local_path"], chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _status, response = request.next_chunk()
    return {"ok": True, "video_id": response.get("id", ""), "response": response}


@guarded("youtube_upload", ok_fn=lambda r: r[0]["status"] != "failed")
def execute_upload_plan(
    plan_path: str | Path,
    *,
    approved: bool,
    confirm: str,
    dry_run: bool = True,
) -> tuple[dict[str, Any], Path]:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    allowed = approved and confirm == APPROVAL_PHRASE and plan.get("ready_for_approval")
    result: dict[str, Any] = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_upload_video",
        "plan_path": str(plan_path),
        "approved": approved,
        "confirm_ok": confirm == APPROVAL_PHRASE,
        "dry_run": dry_run,
        "status": "blocked",
        "state_change": False,
        "reason": "",
        "video_id": "",
    }
    if not allowed:
        result["reason"] = "approval_required_or_plan_not_ready"
    elif dry_run:
        result.update({"status": "dry_run_ok", "reason": "dry_run_no_upload"})
    else:
        # 실제 업로드 직전 공통 게이트(승인 문구 대조 + 감사 기록). 문구는 사용자가 입력한 confirm 값이다.
        from scripts.common.gate import require_side_effect

        require_side_effect("youtube_upload", approval=confirm, expected=APPROVAL_PHRASE, plan=str(plan_path))
        upload = _upload_with_official_api(plan)
        result.update(
            {
                "status": "ok" if upload.get("ok") else "failed",
                "state_change": bool(upload.get("ok")),
                "reason": upload.get("reason", ""),
                "video_id": upload.get("video_id", ""),
                "api_result": upload,
            }
        )

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULT_DIR / f"youtube_upload_result_{_stamp()}.json"
    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    path.write_text(payload, encoding="utf-8")
    LATEST_RESULT.write_text(payload, encoding="utf-8")
    emit_event(
        "YOUTUBE_UPLOAD_EXECUTED",
        site="youtube",
        workflow="upload_execute",
        status=result["status"],
        risk="external_video_upload",
        artifact_path=str(path),
        metadata={
            "state_change": result["state_change"],
            "dry_run": dry_run,
            "video_id": result["video_id"],
            "reason": result["reason"],
        },
    )
    return result, path


def verify_upload_result(result_path: str | Path) -> tuple[dict[str, Any], Path]:
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    verification = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_upload_verify",
        "result_path": str(result_path),
        "status": "ok" if result.get("status") in {"ok", "dry_run_ok"} else "failed",
        "video_id": result.get("video_id", ""),
        "state_change": result.get("state_change", False),
    }
    path = RESULT_DIR / f"youtube_upload_verification_{_stamp()}.json"
    path.write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    emit_event(
        "YOUTUBE_UPLOAD_VERIFIED",
        site="youtube",
        workflow="upload_verify",
        status=verification["status"],
        risk="external_video_upload",
        artifact_path=str(path),
        metadata={"video_id": verification["video_id"], "state_change": verification["state_change"]},
    )
    return verification, path
