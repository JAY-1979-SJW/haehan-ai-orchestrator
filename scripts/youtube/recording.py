"""Local screen recording workflow for YouTube-ready evidence videos."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root
from scripts.common.realtime_audit import emit_event

ROOT = repo_root()
PLAN_DIR = ROOT / "data" / "youtube_recording_plans"
RESULT_DIR = ROOT / "data" / "youtube_recording_results"
LATEST_PLAN = ROOT / "data" / "youtube_recording_plan_latest.json"
LATEST_RESULT = ROOT / "data" / "youtube_recording_result_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "youtube_recordings"
APPROVAL_PHRASE = "YOUTUBE_APPROVED_RECORD"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _default_output_path() -> Path:
    return DEFAULT_OUTPUT_DIR / f"local_work_{_stamp()}.mp4"


def build_ffmpeg_command(
    *,
    output_path: Path,
    duration_seconds: int,
    framerate: int = 15,
    source: str = "desktop",
    include_audio: bool = False,
    ffmpeg_path: str = "ffmpeg",
) -> list[str]:
    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        str(framerate),
        "-i",
        source,
    ]
    if include_audio:
        command.extend(["-f", "dshow", "-i", "audio=virtual-audio-capturer"])
    command.extend(
        [
            "-t",
            str(duration_seconds),
            "-vf",
            "crop=trunc(iw/2)*2:trunc(ih/2)*2",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def prepare_recording_plan(values: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    duration = int(values.get("duration_seconds") or values.get("duration") or 60)
    framerate = int(values.get("framerate") or 15)
    source = str(values.get("source") or "desktop")
    include_audio = str(values.get("include_audio") or values.get("audio") or "false").lower() in {"1", "true", "yes"}
    output_path = Path(str(values.get("output_path") or values.get("output") or _default_output_path()))
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    ffmpeg_path = str(values.get("ffmpeg_path") or values.get("ffmpeg") or "ffmpeg")
    ffmpeg_found = shutil.which(ffmpeg_path) is not None or Path(ffmpeg_path).exists()

    plan = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_record_local_work",
        "risk": "local_screen_capture",
        "approval": {
            "required": True,
            "approved": False,
            "approval_phrase": APPROVAL_PHRASE,
        },
        "recording": {
            "duration_seconds": duration,
            "framerate": framerate,
            "source": source,
            "include_audio": include_audio,
            "output_path": str(output_path),
            "ffmpeg_path": ffmpeg_path,
            "ffmpeg_found": ffmpeg_found,
            "command": build_ffmpeg_command(
                output_path=output_path,
                duration_seconds=duration,
                framerate=framerate,
                source=source,
                include_audio=include_audio,
                ffmpeg_path=ffmpeg_path,
            ),
        },
        "safety_checklist": [
            "Close password, cookie, token, customer PII, billing, and account screens before recording.",
            "Use a clean browser profile or a dedicated app window when possible.",
            "Review the saved video before upload preparation.",
            "Upload and publish require separate approval gates.",
        ],
        "ready_for_approval": ffmpeg_found and duration > 0,
        "missing_requirements": [] if ffmpeg_found else ["ffmpeg"],
    }

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    path = PLAN_DIR / f"youtube_recording_plan_{_stamp()}.json"
    payload = json.dumps(plan, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    LATEST_PLAN.write_text(payload, encoding="utf-8")
    emit_event(
        "YOUTUBE_RECORDING_PLAN_PREPARED",
        site="youtube",
        workflow="recording_prepare",
        status="ok" if plan["ready_for_approval"] else "blocked",
        risk="local_screen_capture",
        artifact_path=str(path),
        metadata={"output_path": str(output_path), "duration_seconds": duration, "ffmpeg_found": ffmpeg_found},
    )
    return plan, path


def execute_recording_plan(plan_path: str | Path, *, approved: bool, confirm: str) -> tuple[dict[str, Any], Path]:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    recording = plan["recording"]
    allowed = approved and confirm == APPROVAL_PHRASE and plan.get("ready_for_approval")
    output_path = Path(recording["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_record_local_work",
        "plan_path": str(plan_path),
        "approved": approved,
        "confirm_ok": confirm == APPROVAL_PHRASE,
        "status": "blocked",
        "state_change": False,
        "output_path": str(output_path),
        "reason": "",
    }

    if not allowed:
        result["reason"] = "approval_required_or_plan_not_ready"
    else:
        command = list(recording["command"])
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(recording["duration_seconds"]) + 30,
            check=False,
            encoding="utf-8",
        )
        result.update(
            {
                "status": "ok" if completed.returncode == 0 and output_path.exists() else "failed",
                "state_change": output_path.exists(),
                "exit_code": completed.returncode,
                "output_tail": completed.stdout[-2000:],
                "file_size": output_path.stat().st_size if output_path.exists() else 0,
            }
        )
        if result["status"] != "ok":
            result["reason"] = "ffmpeg_failed"

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULT_DIR / f"youtube_recording_result_{_stamp()}.json"
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    LATEST_RESULT.write_text(payload, encoding="utf-8")
    emit_event(
        "YOUTUBE_RECORDING_EXECUTED",
        site="youtube",
        workflow="recording_execute",
        status=result["status"],
        risk="local_screen_capture",
        artifact_path=str(path),
        metadata={
            "state_change": result["state_change"],
            "output_path": result["output_path"],
            "reason": result["reason"],
        },
    )
    return result, path
