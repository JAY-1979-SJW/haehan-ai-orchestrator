"""F-4S-12 render plan — ffmpeg 명령 계획 생성 (실제 실행 없음).

설계 원칙:
- 입력: F-4S-11 edit_queue JSON
- 출력: render_plan JSON + Markdown (실제 ffmpeg 미실행)
- shutil.which("ffmpeg") 로 availability 확인 (--version 실행 금지)
- Path.exists() 로 asset 파일 존재 확인
- subprocess.run / os.system / shell=True 금지
- 실제 영상 합성 / 파일 변환 금지
- API key / secret 출력 금지
- 브라우저/Playwright/OAuth/upload 금지
- command_plan 은 문자열 계획만 생성 (실행 금지)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SECRET_KEYWORDS = ("api_key", "secret", "password", "token", "client_secret", "bearer")


def _ensure_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _has_secret(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _SECRET_KEYWORDS)


def load_json(path: Any) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# ffmpeg availability
# ---------------------------------------------------------------------------


def check_ffmpeg_available() -> bool:
    """shutil.which 로만 ffmpeg 존재 확인. --version 실행 금지."""
    return shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# Edit queue extraction
# ---------------------------------------------------------------------------


def extract_edit_items(edit_queue: Any) -> List[Dict[str, Any]]:
    if not isinstance(edit_queue, dict):
        return []
    return [it for it in (edit_queue.get("edit_items") or []) if isinstance(it, dict)]


# ---------------------------------------------------------------------------
# Asset validation
# ---------------------------------------------------------------------------


def validate_render_assets(edit_item: Dict[str, Any]) -> Dict[str, Any]:
    """edit item 의 입력 파일 존재 여부 확인 (Path.exists 만 허용)."""
    video_path = _ensure_str(edit_item.get("source_video_path"))
    srt_path = _ensure_str(edit_item.get("subtitle_srt_path"))
    audio_path = _ensure_str(edit_item.get("tts_expected_audio_path"))
    output_path = _ensure_str(edit_item.get("output_video_path"))

    video_exists = bool(video_path) and Path(video_path).exists()
    subtitle_exists = bool(srt_path) and Path(srt_path).exists()
    audio_exists = bool(audio_path) and Path(audio_path).exists()

    return {
        "video_path": video_path or None,
        "video_exists": video_exists,
        "subtitle_path": srt_path or None,
        "subtitle_exists": subtitle_exists,
        "audio_path": audio_path or None,
        "audio_exists": audio_exists,
        "output_path": output_path or None,
    }


# ---------------------------------------------------------------------------
# ffmpeg command plan builder
# ---------------------------------------------------------------------------


def build_ffmpeg_command_plan(edit_item: Dict[str, Any]) -> Dict[str, Any]:
    """ffmpeg 명령 계획 문자열 생성. 실제 실행 없음, shell=True 금지."""
    assets = validate_render_assets(edit_item)
    input_video = assets["video_path"] or "<input_video_planned>"
    output_video = assets["output_path"] or "<output_video_planned>"
    srt_path = assets["subtitle_path"]
    audio_path = assets["audio_path"]

    args: List[str] = ["-i", input_video]

    # subtitle filter
    vf_parts: List[str] = []
    if srt_path:
        # path는 표시용 — 실행 시 플랫폼별 이스케이프 필요
        vf_parts.append(f"subtitles={srt_path}")

    if vf_parts:
        args += ["-vf", ",".join(vf_parts)]

    # audio input
    if audio_path and assets["audio_exists"]:
        args += ["-i", audio_path, "-map", "0:v:0", "-map", "1:a:0"]
    elif audio_path and not assets["audio_exists"]:
        # planned audio — no -i for now
        pass

    args += ["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart"]
    args.append(output_video)

    # secret check
    warnings: List[str] = []
    for arg in args:
        if _has_secret(arg):
            warnings.append(f"secret_like_arg_blocked:{arg[:20]}")

    # redacted display string (safe for logs)
    display_args = []
    for arg in args:
        if _has_secret(arg):
            display_args.append("<redacted>")
        else:
            display_args.append(arg)
    display = "ffmpeg " + " ".join(display_args)

    return {
        "program": "ffmpeg",
        "args": args,
        "display": display,
        "shell": False,  # shell=True 금지
        "planned_only": True,  # 실행 금지 플래그
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Render plan build
# ---------------------------------------------------------------------------


def build_render_plan(
    edit_queue: Any,
    *,
    out_dir: Path,
    require_assets: bool = False,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    ffmpeg_available = check_ffmpeg_available()
    edit_items = extract_edit_items(edit_queue)
    if isinstance(max_items, int) and max_items > 0:
        edit_items = edit_items[:max_items]

    render_items: List[Dict[str, Any]] = []
    out_path = Path(out_dir)

    for i, edit_item in enumerate(edit_items, start=1):
        render_id = f"render_{i:03d}"
        assets = validate_render_assets(edit_item)
        cmd_plan = build_ffmpeg_command_plan(edit_item)

        warnings: List[str] = list(cmd_plan["warnings"])
        missing: List[str] = []
        if not assets["video_exists"]:
            missing.append("input_video")
            warnings.append("input_video_missing:planned_only")
        if not assets["subtitle_exists"]:
            missing.append("subtitle_srt")
            warnings.append("subtitle_srt_missing:planned_only")
        if not assets["audio_exists"]:
            missing.append("tts_audio")
            warnings.append("tts_audio_missing:planned_only")

        if require_assets and missing:
            status = "blocked"
        else:
            status = "planned"

        render_items.append({
            "render_id": render_id,
            "source_edit_id": _ensure_str(edit_item.get("edit_id")),
            "status": status,
            "title": _ensure_str(edit_item.get("title")),
            "input_video_path": assets["video_path"],
            "subtitle_srt_path": assets["subtitle_path"],
            "planned_audio_path": assets["audio_path"],
            "output_video_path": assets["output_path"],
            "ffmpeg_available": ffmpeg_available,
            "assets": {
                "video_exists": assets["video_exists"],
                "subtitle_exists": assets["subtitle_exists"],
                "audio_exists": assets["audio_exists"],
            },
            "command_plan": cmd_plan,
            "warnings": warnings,
            "review_required": bool(edit_item.get("review_required")),
        })

    planned_count = sum(1 for r in render_items if r["status"] == "planned")
    blocked_count = sum(1 for r in render_items if r["status"] == "blocked")

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ffmpeg_available": ffmpeg_available,
        "out_dir": str(out_path),
        "total_items": len(render_items),
        "planned_count": planned_count,
        "blocked_count": blocked_count,
        "render_items": render_items,
        "notes": [
            "F-4S-12 render plan dry-run",
            "실제 ffmpeg 실행 없음",
            "실제 영상 합성 없음",
            "command_plan 은 계획 문자열만 — 실행 금지",
            "shell=True 금지 / subprocess.run 금지",
            "사람 검수 후 F-4S-13 restricted ffmpeg worker에서 실제 실행",
        ],
    }


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def render_render_plan_markdown(plan: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Render Plan Dry-run 리포트 (F-4S-12)")
    lines.append("")
    lines.append(f"- generated_at: {plan.get('generated_at')}")
    lines.append(f"- ffmpeg_available: {plan.get('ffmpeg_available')}")
    lines.append(f"- total_items: {plan.get('total_items')}")
    lines.append(f"- planned_count: {plan.get('planned_count')}")
    lines.append(f"- blocked_count: {plan.get('blocked_count')}")
    lines.append("- 실제 ffmpeg 실행 없음 / shell=True 금지")
    lines.append("")

    for item in plan.get("render_items") or []:
        lines.append(f"## {item['render_id']} — {item['title'] or '(제목 없음)'}")
        lines.append(f"- status: {item['status']}")
        lines.append(f"- ffmpeg_available: {item['ffmpeg_available']}")
        lines.append(f"- input_video: {item['input_video_path'] or '(planned)'}")
        lines.append(f"- subtitle_srt: {item['subtitle_srt_path'] or '(planned)'}")
        lines.append(f"- planned_audio: {item['planned_audio_path'] or '(planned)'}")
        lines.append(f"- output_video: {item['output_video_path'] or '(planned)'}")
        a = item.get("assets", {})
        lines.append(
            f"- assets: video_exists={a.get('video_exists')} "
            f"subtitle_exists={a.get('subtitle_exists')} "
            f"audio_exists={a.get('audio_exists')}"
        )
        lines.append(f"- review_required: {item['review_required']}")
        for w in item.get("warnings") or []:
            lines.append(f"- warning: {w}")
        cmd = item.get("command_plan", {})
        lines.append(f"- command_plan (display): `{cmd.get('display', '')}`")
        lines.append("")

    notes = plan.get("notes") or []
    if notes:
        lines.append("## 주의사항")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


def write_render_plan_files(
    plan: Dict[str, Any],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"render_plan_{ts}"
    json_path = out / f"{base}.json"
    md_path = out / f"{base}.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_render_plan_markdown(plan), encoding="utf-8")
    return {"json": json_path, "md": md_path}
