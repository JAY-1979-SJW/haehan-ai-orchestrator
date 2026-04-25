"""F-4S-9 subtitle queue PoC — SRT/VTT 자막 초안 생성.

설계 원칙:
- 입력: F-4S-6 video_queue JSON / F-4S-8 recording metadata JSON
- 출력: subtitle_queue JSON + Markdown 리포트 + .srt + .vtt 파일
- 실제 STT/TTS/영상 편집/업로드 없음
- 브라우저/Playwright 미사용
- OAuth/write-action/LTX API 미사용
- 법령·단가·안전 기준 표현은 review_required=True 유지

[segment 시간 배분]
- duration_type "short" → 30초 기준
- duration_type "long"  → 60초 기준
- scene_plan 개수에 따라 균등 분배, 최소 2.5초 최대 4.5초
- 초과 시 마지막 scene에 나머지 포함
"""
from __future__ import annotations

import json
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DURATION_MAP = {"short": 30, "long": 60, "medium": 45}
DEFAULT_DURATION = 30
SEG_MIN_SEC = 2.5
SEG_MAX_SEC = 4.5
MAX_CHARS_PER_LINE = 22
MAX_LINES = 2

_REVIEW_KEYWORDS = (
    "법령", "단가", "안전기준", "법적", "기준치", "규정", "조항", "시행령",
    "고시", "허가", "인증", "보장", "확정", "반드시", "절대",
)

_FORBIDDEN_FIELDS = ("api_key", "secret", "password", "token", "client_secret")


def load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _ensure_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _duration_seconds(item: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> int:
    if metadata:
        dur = metadata.get("duration_seconds") or metadata.get("would_record_seconds")
        if dur:
            try:
                return int(dur)
            except (TypeError, ValueError):
                pass
    dtype = _ensure_str(item.get("duration_type")).strip().lower()
    return DURATION_MAP.get(dtype, DEFAULT_DURATION)


def _check_review(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _REVIEW_KEYWORDS)


def _truncate_text(text: str) -> str:
    text = text.strip()
    lines = textwrap.wrap(text, width=MAX_CHARS_PER_LINE)
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines[-1] = lines[-1].rstrip() + "…"
    return "\n".join(lines)


def _collect_scene_texts(item: Dict[str, Any]) -> List[str]:
    """scene_plan 각 장면의 caption + narration 에서 자막 텍스트 추출."""
    texts: List[str] = []
    hook = _ensure_str(item.get("hook")).strip()
    if hook:
        texts.append(hook)

    scene_plan = item.get("scene_plan") or []
    for scene in scene_plan:
        if not isinstance(scene, dict):
            continue
        caption = _ensure_str(scene.get("caption")).strip()
        narration = _ensure_str(scene.get("narration")).strip()
        # caption 우선, 없으면 narration
        chosen = caption or narration
        if chosen:
            texts.append(chosen)

    # subtitle_points 추가 (중복 제거)
    for sp in item.get("subtitle_points") or []:
        t = _ensure_str(sp).strip()
        if t and t not in texts:
            texts.append(t)

    return texts


def _distribute_times(n: int, total: float) -> List[tuple[float, float]]:
    """n개 segment를 total 초에 균등 분배. 각 최소 SEG_MIN_SEC 보장."""
    if n == 0:
        return []
    ideal = total / n
    dur = max(SEG_MIN_SEC, min(SEG_MAX_SEC, ideal))
    slots: List[tuple[float, float]] = []
    t = 0.0
    for i in range(n):
        if i == n - 1:
            end = total
        else:
            end = min(t + dur, total - SEG_MIN_SEC * (n - i - 1))
        slots.append((round(t, 3), round(end, 3)))
        t = end
    return slots


def build_subtitle_segments(
    video_item: Dict[str, Any],
    recording_metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """video queue item 하나에서 subtitle segment 목록 생성."""
    total = float(_duration_seconds(video_item, recording_metadata))
    texts = _collect_scene_texts(video_item)
    if not texts:
        texts = [_ensure_str(video_item.get("title", "")) or "(제목 없음)"]

    slots = _distribute_times(len(texts), total)
    segments: List[Dict[str, Any]] = []
    for i, (text, (start, end)) in enumerate(zip(texts, slots), start=1):
        trunc = _truncate_text(text)
        source = "hook" if i == 1 else ("subtitle_point" if i > len(
            (video_item.get("scene_plan") or [])) + 1 else "scene_caption")
        segments.append({
            "index": i,
            "start_seconds": start,
            "end_seconds": end,
            "text": trunc,
            "source": source,
            "review_required": _check_review(trunc),
        })
    return segments


# ---------------------------------------------------------------------------
# SRT / VTT formatting
# ---------------------------------------------------------------------------


def format_srt_timestamp(seconds: float) -> str:
    """초 → SRT 타임스탬프 'HH:MM:SS,mmm'"""
    s = max(0.0, seconds)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int(round((s - int(s)) * 1000))
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    """초 → VTT 타임스탬프 'HH:MM:SS.mmm'"""
    return format_srt_timestamp(seconds).replace(",", ".")


def render_srt(segments: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for seg in segments:
        lines.append(str(seg["index"]))
        lines.append(
            f"{format_srt_timestamp(seg['start_seconds'])} --> "
            f"{format_srt_timestamp(seg['end_seconds'])}"
        )
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def render_vtt(segments: List[Dict[str, Any]]) -> str:
    lines: List[str] = ["WEBVTT", ""]
    for seg in segments:
        lines.append(
            f"{format_vtt_timestamp(seg['start_seconds'])} --> "
            f"{format_vtt_timestamp(seg['end_seconds'])}"
        )
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Queue build
# ---------------------------------------------------------------------------


def extract_video_queue_items(video_queue: Any) -> List[Dict[str, Any]]:
    if isinstance(video_queue, dict):
        raw = video_queue.get("queue") or video_queue.get("items") or []
    elif isinstance(video_queue, list):
        raw = video_queue
    else:
        return []
    return [it for it in raw if isinstance(it, dict)]


def extract_recording_metadata(source: Any) -> Dict[str, Dict[str, Any]]:
    """worker result 또는 metadata JSON에서 recording_id → metadata 매핑 반환."""
    mapping: Dict[str, Dict[str, Any]] = {}
    if not isinstance(source, dict):
        return mapping

    # single metadata
    if "recording_id" in source:
        rid = _ensure_str(source["recording_id"])
        if rid:
            mapping[rid] = source
        return mapping

    # worker result with items list
    for it in source.get("items") or []:
        if isinstance(it, dict):
            rid = _ensure_str(it.get("recording_id"))
            if rid:
                mapping[rid] = it
    return mapping


def build_subtitle_queue(
    video_items: List[Dict[str, Any]],
    recording_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    max_items: int = 5,
    language: str = "ko",
) -> Dict[str, Any]:
    meta_map = recording_metadata or {}
    items_to_process = video_items[:max_items]
    subtitle_items: List[Dict[str, Any]] = []
    warnings_global: List[str] = []

    for i, vitem in enumerate(items_to_process, start=1):
        subtitle_id = f"subtitle_{i:03d}"
        queue_id = _ensure_str(vitem.get("queue_id") or vitem.get("id") or f"item_{i}")
        rec_id = _ensure_str(vitem.get("recording_id") or "")
        rec_meta = meta_map.get(rec_id) if rec_id else None

        segments = build_subtitle_segments(vitem, rec_meta)
        item_warnings: List[str] = []

        # title / segments 에서 secret 키워드 감지
        title_lower = _ensure_str(vitem.get("title")).lower()
        for field in _FORBIDDEN_FIELDS:
            if field in title_lower:
                item_warnings.append(f"title:secret_keyword_detected:{field}")
        for seg in segments:
            for field in _FORBIDDEN_FIELDS:
                if field in seg["text"].lower():
                    item_warnings.append(f"seg_{seg['index']}:secret_keyword_detected:{field}")

        if not segments:
            item_warnings.append("no_segments_generated")

        any_review = any(seg["review_required"] for seg in segments)
        if vitem.get("review_required") or any_review:
            item_warnings.append("review_required:legal_or_safety_expression_detected")

        risk_notes = vitem.get("risk_notes") or []
        if isinstance(risk_notes, list) and risk_notes:
            item_warnings.extend([f"risk_note:{rn[:60]}" for rn in risk_notes[:2]])

        subtitle_items.append({
            "subtitle_id": subtitle_id,
            "source_queue_id": queue_id,
            "recording_id": rec_id or None,
            "title": _ensure_str(vitem.get("title")),
            "duration_seconds": _duration_seconds(vitem, rec_meta),
            "language": language,
            "segments": segments,
            "segments_count": len(segments),
            "srt_path": None,
            "vtt_path": None,
            "review_required": bool(vitem.get("review_required") or any_review),
            "warnings": item_warnings,
        })

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "language": language,
        "total_items": len(subtitle_items),
        "subtitle_items": subtitle_items,
        "global_warnings": warnings_global,
        "notes": [
            "F-4S-9 subtitle queue PoC",
            "실제 STT/TTS/영상 편집/업로드 없음",
            "자막 문구는 사람이 검수 필요",
            "법령·단가·안전기준 표현은 review_required=true 유지",
        ],
    }


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def render_subtitle_queue_markdown(queue: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# 자막 큐 PoC 리포트 (F-4S-9)")
    lines.append("")
    lines.append(f"- generated_at: {queue.get('generated_at')}")
    lines.append(f"- language: {queue.get('language')}")
    lines.append(f"- total_items: {queue.get('total_items')}")
    lines.append("- 실제 STT/TTS/영상 편집/업로드 없음")
    lines.append("")

    for item in queue.get("subtitle_items") or []:
        lines.append(f"## {item['subtitle_id']} — {item['title'] or '(제목 없음)'}")
        lines.append(f"- source_queue_id: {item['source_queue_id']}")
        lines.append(f"- recording_id: {item['recording_id'] or '-'}")
        lines.append(f"- duration_seconds: {item['duration_seconds']}")
        lines.append(f"- segments_count: {item['segments_count']}")
        lines.append(f"- review_required: {item['review_required']}")
        lines.append(f"- srt_path: {item.get('srt_path') or '-'}")
        lines.append(f"- vtt_path: {item.get('vtt_path') or '-'}")
        for w in item.get("warnings") or []:
            lines.append(f"- warning: {w}")
        lines.append("")
        lines.append("### segments")
        for seg in item.get("segments") or []:
            lines.append(
                f"  [{seg['index']}] {format_srt_timestamp(seg['start_seconds'])} → "
                f"{format_srt_timestamp(seg['end_seconds'])}  "
                f"`{seg['source']}`  review={seg['review_required']}"
            )
            lines.append(f"  > {seg['text'].replace(chr(10), ' / ')}")
        lines.append("")

    notes = queue.get("notes") or []
    if notes:
        lines.append("## 주의사항")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


def write_subtitle_queue_files(
    queue: Dict[str, Any],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """queue JSON + Markdown + 각 item 별 SRT/VTT 파일 저장."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"subtitle_queue_{ts}"

    # update srt/vtt paths in items before serialising
    srt_files: List[str] = []
    vtt_files: List[str] = []
    for item in queue.get("subtitle_items") or []:
        sid = item["subtitle_id"]
        srt_path = out / f"{sid}.srt"
        vtt_path = out / f"{sid}.vtt"
        srt_path.write_text(render_srt(item["segments"]), encoding="utf-8")
        vtt_path.write_text(render_vtt(item["segments"]), encoding="utf-8")
        item["srt_path"] = str(srt_path)
        item["vtt_path"] = str(vtt_path)
        srt_files.append(str(srt_path))
        vtt_files.append(str(vtt_path))

    json_path = out / f"{base}.json"
    md_path = out / f"{base}.md"
    json_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_subtitle_queue_markdown(queue), encoding="utf-8")

    return {
        "json": json_path,
        "md": md_path,
        "srt_files": srt_files,
        "vtt_files": vtt_files,
    }
