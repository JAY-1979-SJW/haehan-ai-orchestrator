"""F-4S-11 영상 편집 큐 PoC — 합성 계획 큐 생성.

설계 원칙:
- 입력: F-4S-8 recording metadata / F-4S-9 subtitle queue / F-4S-10 TTS queue
- 출력: edit_queue JSON + Markdown (실제 영상 합성 미수행)
- 실제 ffmpeg 실행 없음
- 실제 영상/음성 파일 변환 없음
- output_video_path 는 계획 경로만 기록
- API key / client_secret 출력 금지
- 브라우저/Playwright/OAuth/upload 금지

[허용 step type]
- validate_assets       : 계획 파일 존재 여부 확인
- compose_video_plan    : 레이어 합성 계획 생성
- attach_subtitles      : SRT/VTT 자막 레이어 계획
- attach_voiceover_plan : TTS 음성 레이어 계획 (planned_only)
- export_plan           : 출력 경로/포맷 계획

[금지 step type]
- ffmpeg_run / render_video / upload / publish / delete / oauth / browser
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ALLOWED_STEP_TYPES = (
    "validate_assets",
    "compose_video_plan",
    "attach_subtitles",
    "attach_voiceover_plan",
    "export_plan",
)
FORBIDDEN_STEP_TYPES = (
    "ffmpeg_run",
    "render_video",
    "upload",
    "publish",
    "delete",
    "oauth",
    "browser",
    "click",
    "fill",
    "type",
    "press",
)

_REVIEW_KEYWORDS = (
    "법령", "단가", "안전기준", "법적", "규정", "시행령",
    "허가", "인증", "보장", "확정", "반드시", "절대",
)
_SECRET_KEYWORDS = ("api_key", "secret", "password", "token", "client_secret")


def _ensure_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _check_review(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _REVIEW_KEYWORDS)


def _check_secret(text: str) -> List[str]:
    lower = text.lower()
    return [kw for kw in _SECRET_KEYWORDS if kw in lower]


def load_json(path: Any) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Asset extraction
# ---------------------------------------------------------------------------


def extract_recording_assets(source: Any) -> List[Dict[str, Any]]:
    """worker result 또는 단일 metadata JSON에서 recording asset 목록 반환."""
    if not isinstance(source, dict):
        return []

    # single metadata
    if "recording_id" in source and "video_path" in source:
        return [{
            "recording_id": _ensure_str(source.get("recording_id")),
            "source_queue_id": _ensure_str(source.get("source_queue_id")),
            "video_path": _ensure_str(source.get("video_path")),
            "video_dir": _ensure_str(source.get("video_dir")),
            "duration_seconds": _infer_duration(source),
            "success": bool(source.get("success")),
            "planned_only": not bool(source.get("video_path")),
        }]

    # worker result with items list
    assets = []
    for it in source.get("items") or []:
        if not isinstance(it, dict):
            continue
        assets.append({
            "recording_id": _ensure_str(it.get("recording_id")),
            "source_queue_id": _ensure_str(it.get("source_queue_id")),
            "video_path": _ensure_str(it.get("video_path")),
            "video_dir": _ensure_str(it.get("video_dir")),
            "duration_seconds": _infer_duration(it),
            "success": bool(it.get("success")),
            "planned_only": not bool(it.get("video_path")),
        })
    return assets


def _infer_duration(item: Dict[str, Any]) -> int:
    dur = item.get("duration_seconds") or item.get("would_record_seconds")
    if dur:
        try:
            return int(dur)
        except (TypeError, ValueError):
            pass
    # started_at / finished_at 기반 추정
    try:
        from datetime import datetime as dt
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        s = dt.strptime(item["started_at"], fmt)
        e = dt.strptime(item["finished_at"], fmt)
        return max(1, int((e - s).total_seconds()))
    except Exception:
        return 30


def extract_subtitle_assets(subtitle_queue: Any) -> List[Dict[str, Any]]:
    """subtitle queue JSON에서 SRT/VTT asset 목록 반환."""
    if not isinstance(subtitle_queue, dict):
        return []
    assets = []
    for it in subtitle_queue.get("subtitle_items") or []:
        if not isinstance(it, dict):
            continue
        assets.append({
            "subtitle_id": _ensure_str(it.get("subtitle_id")),
            "source_queue_id": _ensure_str(it.get("source_queue_id")),
            "title": _ensure_str(it.get("title")),
            "srt_path": _ensure_str(it.get("srt_path")),
            "vtt_path": _ensure_str(it.get("vtt_path")),
            "duration_seconds": it.get("duration_seconds", 30),
            "review_required": bool(it.get("review_required")),
        })
    return assets


def extract_tts_assets(tts_queue: Any) -> List[Dict[str, Any]]:
    """tts queue JSON에서 expected_audio_path 목록 반환."""
    if not isinstance(tts_queue, dict):
        return []
    assets = []
    for it in tts_queue.get("tts_items") or []:
        if not isinstance(it, dict):
            continue
        assets.append({
            "tts_id": _ensure_str(it.get("tts_id")),
            "subtitle_id": _ensure_str(it.get("subtitle_id")),
            "source_queue_id": _ensure_str(it.get("source_queue_id")),
            "title": _ensure_str(it.get("title")),
            "expected_audio_path": _ensure_str(it.get("expected_audio_path")),
            "voice_profile": _ensure_str(it.get("voice_profile")),
            "review_required": bool(it.get("review_required")),
        })
    return assets


# ---------------------------------------------------------------------------
# Timeline / edit item build
# ---------------------------------------------------------------------------


def build_edit_timeline(
    duration: int,
    *,
    source_video_path: str,
    srt_path: str,
    tts_audio_path: str,
    planned_video: bool = False,
    planned_audio: bool = True,
) -> List[Dict[str, Any]]:
    timeline = [
        {
            "layer": "video",
            "start_seconds": 0,
            "end_seconds": duration,
            "asset": source_video_path or "(planned)",
            "planned_only": planned_video or not source_video_path,
        },
    ]
    if srt_path:
        timeline.append({
            "layer": "subtitle",
            "start_seconds": 0,
            "end_seconds": duration,
            "asset": srt_path,
            "planned_only": not Path(srt_path).exists(),
        })
    if tts_audio_path:
        timeline.append({
            "layer": "voiceover",
            "start_seconds": 0,
            "end_seconds": duration,
            "asset": tts_audio_path,
            "planned_only": True,  # TTS 음성 파일은 항상 planned_only
        })
    return timeline


def _build_edit_steps(
    has_video: bool, has_subtitle: bool, has_audio: bool
) -> List[Dict[str, Any]]:
    steps = [
        {
            "step_no": 1,
            "type": "validate_assets",
            "description": "영상/자막/음성 계획 파일 확인",
        },
        {
            "step_no": 2,
            "type": "compose_video_plan",
            "description": "영상+자막+음성 레이어 합성 계획 생성",
        },
    ]
    if has_subtitle:
        steps.append({
            "step_no": 3,
            "type": "attach_subtitles",
            "description": "SRT/VTT 자막 레이어 계획 연결",
        })
    if has_audio:
        steps.append({
            "step_no": 4,
            "type": "attach_voiceover_plan",
            "description": "TTS 음성 레이어 계획 연결 (planned_only)",
        })
    steps.append({
        "step_no": len(steps) + 1,
        "type": "export_plan",
        "description": "출력 경로/포맷 계획 생성",
    })
    return steps


def build_edit_queue(
    recording_assets: List[Dict[str, Any]],
    subtitle_assets: List[Dict[str, Any]],
    tts_assets: List[Dict[str, Any]],
    *,
    output_dir: Optional[Path] = None,
    max_items: int = 5,
) -> Dict[str, Any]:
    out_dir = Path(output_dir) if output_dir else Path("runs/video/edits")
    output_video_dir = out_dir / "output"

    # subtitle / tts 을 source_queue_id 또는 subtitle_id 기준으로 매핑
    sub_by_sqid: Dict[str, Dict[str, Any]] = {
        a["source_queue_id"]: a for a in subtitle_assets
    }
    sub_by_sid: Dict[str, Dict[str, Any]] = {
        a["subtitle_id"]: a for a in subtitle_assets
    }
    tts_by_sqid: Dict[str, Dict[str, Any]] = {
        a["source_queue_id"]: a for a in tts_assets
    }
    tts_by_sid: Dict[str, Dict[str, Any]] = {
        a["subtitle_id"]: a for a in tts_assets
    }

    # recording_assets 가 없으면 subtitle 기반으로 가상 item 생성
    if not recording_assets:
        source_list: List[Dict[str, Any]] = [
            {"recording_id": None, "source_queue_id": a["source_queue_id"],
             "video_path": "", "duration_seconds": a["duration_seconds"],
             "success": False, "planned_only": True}
            for a in subtitle_assets[:max_items]
        ]
    else:
        source_list = recording_assets[:max_items]

    edit_items: List[Dict[str, Any]] = []
    for i, rec in enumerate(source_list[:max_items], start=1):
        edit_id = f"edit_{i:03d}"
        sqid = _ensure_str(rec.get("source_queue_id"))
        rid = _ensure_str(rec.get("recording_id"))

        sub = sub_by_sqid.get(sqid) or sub_by_sid.get(sqid) or {}
        tts = tts_by_sqid.get(sqid) or tts_by_sid.get(
            sub.get("subtitle_id", "")
        ) or {}

        title = (
            sub.get("title")
            or tts.get("title")
            or (f"edit_{i:03d}")
        )
        duration = int(
            rec.get("duration_seconds")
            or sub.get("duration_seconds")
            or 30
        )
        video_path = _ensure_str(rec.get("video_path"))
        srt_path = _ensure_str(sub.get("srt_path"))
        vtt_path = _ensure_str(sub.get("vtt_path"))
        audio_path = _ensure_str(tts.get("expected_audio_path"))

        warnings: List[str] = []
        for field in _SECRET_KEYWORDS:
            if field in title.lower():
                warnings.append(f"title:secret_keyword:{field}")
        if not video_path:
            warnings.append("source_video_missing:planned_only")
        if not srt_path:
            warnings.append("subtitle_srt_missing:planned_only")
        if not audio_path:
            warnings.append("tts_audio_missing:planned_only")

        timeline = build_edit_timeline(
            duration,
            source_video_path=video_path,
            srt_path=srt_path,
            tts_audio_path=audio_path,
            planned_video=bool(rec.get("planned_only")),
        )
        steps = _build_edit_steps(
            has_video=bool(video_path),
            has_subtitle=bool(srt_path),
            has_audio=bool(audio_path),
        )

        review = (
            sub.get("review_required")
            or tts.get("review_required")
            or _check_review(title)
        )

        edit_items.append({
            "edit_id": edit_id,
            "status": "draft",
            "title": title,
            "recording_id": rid or None,
            "source_queue_id": sqid or None,
            "subtitle_id": sub.get("subtitle_id") or None,
            "tts_id": tts.get("tts_id") or None,
            "source_video_path": video_path or None,
            "subtitle_srt_path": srt_path or None,
            "subtitle_vtt_path": vtt_path or None,
            "tts_expected_audio_path": audio_path or None,
            "duration_seconds": duration,
            "output_video_path": str(output_video_dir / f"{edit_id}.mp4"),
            "timeline": timeline,
            "edit_steps": steps,
            "review_required": bool(review),
            "warnings": warnings,
        })

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_items": len(edit_items),
        "edit_items": edit_items,
        "notes": [
            "F-4S-11 영상 편집 큐 PoC",
            "실제 ffmpeg 실행 없음",
            "실제 영상/음성 합성 없음",
            "output_video_path 는 계획 경로만 기록",
            "법령·단가·안전기준 표현은 review_required=true 유지",
            "사람 검수 후 ffmpeg worker 단계에서 실제 합성",
        ],
    }


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def render_edit_queue_markdown(queue: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# 영상 편집 큐 PoC 리포트 (F-4S-11)")
    lines.append("")
    lines.append(f"- generated_at: {queue.get('generated_at')}")
    lines.append(f"- total_items: {queue.get('total_items')}")
    lines.append("- 실제 ffmpeg 실행 없음 / 실제 영상 합성 없음")
    lines.append("")

    for item in queue.get("edit_items") or []:
        lines.append(f"## {item['edit_id']} — {item['title'] or '(제목 없음)'}")
        lines.append(f"- status: {item['status']}")
        lines.append(f"- recording_id: {item['recording_id'] or '-'}")
        lines.append(f"- subtitle_id: {item['subtitle_id'] or '-'}")
        lines.append(f"- tts_id: {item['tts_id'] or '-'}")
        lines.append(f"- duration_seconds: {item['duration_seconds']}")
        lines.append(f"- source_video_path: {item['source_video_path'] or '(planned)'}")
        lines.append(f"- subtitle_srt_path: {item['subtitle_srt_path'] or '(planned)'}")
        lines.append(f"- tts_expected_audio_path: {item['tts_expected_audio_path'] or '(planned)'}")
        lines.append(f"- output_video_path: {item['output_video_path']}")
        lines.append(f"- review_required: {item['review_required']}")
        for w in item.get("warnings") or []:
            lines.append(f"- warning: {w}")
        lines.append("")
        lines.append("### timeline")
        for layer in item.get("timeline") or []:
            planned = " [planned_only]" if layer.get("planned_only") else ""
            lines.append(
                f"  [{layer['layer']}] {layer['start_seconds']}s→{layer['end_seconds']}s"
                f"  {layer['asset']}{planned}"
            )
        lines.append("")
        lines.append("### edit_steps")
        for step in item.get("edit_steps") or []:
            lines.append(f"  {step['step_no']}. [{step['type']}] {step['description']}")
        lines.append("")

    notes = queue.get("notes") or []
    if notes:
        lines.append("## 주의사항")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


def write_edit_queue_files(
    queue: Dict[str, Any],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"video_edit_queue_{ts}"
    json_path = out / f"{base}.json"
    md_path = out / f"{base}.md"
    json_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_edit_queue_markdown(queue), encoding="utf-8")
    return {"json": json_path, "md": md_path}
