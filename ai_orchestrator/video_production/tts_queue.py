"""F-4S-10 TTS queue PoC — 음성 생성 계획 큐 생성.

설계 원칙:
- 입력: F-4S-9 subtitle queue JSON / SRT / VTT
- 출력: tts_queue JSON + Markdown (실제 음성 파일 미생성)
- 실제 TTS API 호출 없음
- 실제 음성 파일 생성 없음
- expected_audio_path 는 계획 경로만 기록
- API key / client_secret 출력 금지
- 브라우저/Playwright/OAuth/upload 금지
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VALID_VOICE_PROFILES = (
    "ko_male_neutral",
    "ko_female_neutral",
    "ko_male_energetic",
    "ko_female_friendly",
)
DEFAULT_VOICE_PROFILE = "ko_male_neutral"

TONE_RULES = {
    "hook": "informative",
    "scene_caption": "calm",
    "subtitle_point": "calm",
    "narration_point": "informative",
}
DEFAULT_TONE = "calm"

DEFAULT_SPEED = 1.0

_REVIEW_KEYWORDS = (
    "법령", "단가", "안전기준", "법적", "기준치", "규정", "조항", "시행령",
    "고시", "허가", "인증", "보장", "확정", "반드시", "절대",
)
_WARN_KEYWORDS = (
    "최고", "최저", "완전히", "무조건", "100%", "무료", "즉시", "보장됩니다",
)
_SECRET_KEYWORDS = (
    "api_key", "secret", "password", "token", "client_secret",
)
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?。！？\n])\s*')
MAX_SENTENCE_CHARS = 40


def _ensure_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _check_review(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _REVIEW_KEYWORDS)


def _check_warn(text: str) -> List[str]:
    return [kw for kw in _WARN_KEYWORDS if kw in text]


def _check_secret(text: str) -> List[str]:
    lower = text.lower()
    return [kw for kw in _SECRET_KEYWORDS if kw in lower]


def normalize_tts_text(text: str) -> str:
    """자막 텍스트를 TTS 읽기 적합한 형태로 정규화.

    - 줄바꿈 → 공백
    - 말줄임표 … → 마침표
    - 연속 공백 제거
    """
    t = text.replace("\n", " ").replace("…", ".").replace("·", " ")
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _split_long_sentence(text: str) -> List[str]:
    """긴 문장을 자연스럽게 분할 (MAX_SENTENCE_CHARS 기준)."""
    if len(text) <= MAX_SENTENCE_CHARS:
        return [text]
    parts = _SENTENCE_SPLIT_RE.split(text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        # 강제 분할: 앞 MAX_SENTENCE_CHARS까지
        return [text[:MAX_SENTENCE_CHARS].strip(), text[MAX_SENTENCE_CHARS:].strip()]
    return parts


# ---------------------------------------------------------------------------
# SRT / VTT 파서
# ---------------------------------------------------------------------------


def _parse_srt_timestamp(ts: str) -> float:
    """'HH:MM:SS,mmm' → seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


def parse_srt(path: Any) -> List[Dict[str, Any]]:
    """SRT 파일 파싱 → segment 목록."""
    text = Path(path).read_text(encoding="utf-8")
    blocks = re.split(r'\n\s*\n', text.strip())
    segments = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        arrow_line = lines[1].strip()
        if " --> " not in arrow_line:
            continue
        start_str, end_str = arrow_line.split(" --> ", 1)
        start = _parse_srt_timestamp(start_str)
        end = _parse_srt_timestamp(end_str)
        content = " ".join(l.strip() for l in lines[2:] if l.strip())
        segments.append({
            "index": idx,
            "start_seconds": start,
            "end_seconds": end,
            "text": content,
        })
    return segments


def _parse_vtt_timestamp(ts: str) -> float:
    """'HH:MM:SS.mmm' or 'MM:SS.mmm' → seconds."""
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    else:
        h, m, s = 0, int(parts[0]), float(parts[1])
    return h * 3600 + m * 60 + s


def parse_vtt(path: Any) -> List[Dict[str, Any]]:
    """VTT 파일 파싱 → segment 목록."""
    text = Path(path).read_text(encoding="utf-8")
    blocks = re.split(r'\n\s*\n', text.strip())
    segments = []
    idx = 1
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines or lines[0].strip() == "WEBVTT":
            continue
        arrow_line = None
        content_lines = []
        for line in lines:
            if " --> " in line and arrow_line is None:
                arrow_line = line.strip()
            elif arrow_line is not None:
                content_lines.append(line.strip())
        if not arrow_line:
            continue
        start_str, end_str = arrow_line.split(" --> ", 1)
        start = _parse_vtt_timestamp(start_str)
        end = _parse_vtt_timestamp(end_str)
        content = " ".join(l for l in content_lines if l)
        if content:
            segments.append({
                "index": idx,
                "start_seconds": start,
                "end_seconds": end,
                "text": content,
            })
            idx += 1
    return segments


# ---------------------------------------------------------------------------
# TTS segment 생성
# ---------------------------------------------------------------------------


def _build_tts_segment(
    seg: Dict[str, Any],
    *,
    subtitle_id: str,
    seg_seq: int,
    voice_profile: str,
) -> Dict[str, Any]:
    raw_text = normalize_tts_text(_ensure_str(seg.get("text")))
    source = _ensure_str(seg.get("source", "scene_caption"))
    tone = TONE_RULES.get(source, DEFAULT_TONE)
    duration = seg.get("end_seconds", 0.0) - seg.get("start_seconds", 0.0)
    speed = round(max(0.8, min(1.3, len(raw_text) / max(duration * 7, 1))), 2) if duration > 0 else DEFAULT_SPEED

    warnings: List[str] = []
    for kw in _check_warn(raw_text):
        warnings.append(f"exaggerated_expression:{kw}")
    for kw in _check_secret(raw_text):
        warnings.append(f"secret_keyword_detected:{kw}")

    # 긴 문장 분할 정보 (실제 분할은 TTS 엔진에 위임)
    parts = _split_long_sentence(raw_text)
    if len(parts) > 1:
        warnings.append(f"long_sentence_split_recommended:{len(parts)}_parts")

    return {
        "segment_id": f"{subtitle_id.replace('subtitle_', 'tts_')}_{seg_seq:03d}",
        "source_subtitle_id": subtitle_id,
        "index": seg.get("index", seg_seq),
        "start_seconds": seg.get("start_seconds", 0.0),
        "end_seconds": seg.get("end_seconds", 0.0),
        "text": raw_text,
        "voice_profile": voice_profile,
        "speed": speed,
        "tone": tone,
        "review_required": _check_review(raw_text) or bool(seg.get("review_required")),
        "warnings": warnings,
    }


def extract_tts_segments(
    subtitle_item: Dict[str, Any],
    *,
    voice_profile: str = DEFAULT_VOICE_PROFILE,
) -> List[Dict[str, Any]]:
    sid = _ensure_str(subtitle_item.get("subtitle_id", "subtitle_001"))
    raw_segs = subtitle_item.get("segments") or []
    return [
        _build_tts_segment(seg, subtitle_id=sid, seg_seq=i, voice_profile=voice_profile)
        for i, seg in enumerate(raw_segs, start=1)
    ]


# ---------------------------------------------------------------------------
# TTS queue build
# ---------------------------------------------------------------------------


def build_tts_queue(
    subtitle_items: List[Dict[str, Any]],
    *,
    voice_profile: str = DEFAULT_VOICE_PROFILE,
    output_dir: Optional[Path] = None,
    max_items: int = 5,
) -> Dict[str, Any]:
    if voice_profile not in VALID_VOICE_PROFILES:
        voice_profile = DEFAULT_VOICE_PROFILE

    out_dir = Path(output_dir) if output_dir else Path("runs/video/tts")
    audio_dir = out_dir / "audio"
    items_to_process = subtitle_items[:max_items]
    tts_items: List[Dict[str, Any]] = []

    for i, sub_item in enumerate(items_to_process, start=1):
        tts_id = f"tts_{i:03d}"
        sid = _ensure_str(sub_item.get("subtitle_id", f"subtitle_{i:03d}"))
        segments = extract_tts_segments(sub_item, voice_profile=voice_profile)

        item_warnings: List[str] = []
        if not segments:
            item_warnings.append("no_segments_generated")

        any_review = any(s["review_required"] for s in segments)
        if sub_item.get("review_required") or any_review:
            item_warnings.append("review_required:legal_or_safety_expression")

        tts_items.append({
            "tts_id": tts_id,
            "source_queue_id": _ensure_str(sub_item.get("source_queue_id")),
            "subtitle_id": sid,
            "title": _ensure_str(sub_item.get("title")),
            "language": _ensure_str(sub_item.get("language", "ko")),
            "voice_profile": voice_profile,
            "segments": segments,
            "segments_count": len(segments),
            "expected_audio_path": str(audio_dir / f"{tts_id}.wav"),
            "manifest_path": str(out_dir / f"{tts_id}_manifest.json"),
            "review_required": bool(sub_item.get("review_required") or any_review),
            "warnings": item_warnings,
        })

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "voice_profile": voice_profile,
        "total_items": len(tts_items),
        "tts_items": tts_items,
        "notes": [
            "F-4S-10 TTS queue PoC",
            "실제 TTS API 호출 없음",
            "실제 음성 파일 생성 없음",
            "expected_audio_path 는 계획 경로만 기록",
            "법령·단가·안전기준 표현은 review_required=true 유지",
            "사람 검수 후 TTS API 연동 단계에서 실제 생성",
        ],
    }


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def render_tts_queue_markdown(queue: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# TTS 큐 PoC 리포트 (F-4S-10)")
    lines.append("")
    lines.append(f"- generated_at: {queue.get('generated_at')}")
    lines.append(f"- voice_profile: {queue.get('voice_profile')}")
    lines.append(f"- total_items: {queue.get('total_items')}")
    lines.append("- 실제 TTS API 호출 없음 / 실제 음성 파일 생성 없음")
    lines.append("")

    for item in queue.get("tts_items") or []:
        lines.append(f"## {item['tts_id']} — {item['title'] or '(제목 없음)'}")
        lines.append(f"- subtitle_id: {item['subtitle_id']}")
        lines.append(f"- voice_profile: {item['voice_profile']}")
        lines.append(f"- language: {item['language']}")
        lines.append(f"- segments_count: {item['segments_count']}")
        lines.append(f"- expected_audio_path: {item['expected_audio_path']}")
        lines.append(f"- review_required: {item['review_required']}")
        for w in item.get("warnings") or []:
            lines.append(f"- warning: {w}")
        lines.append("")
        lines.append("### segments")
        for seg in item.get("segments") or []:
            lines.append(
                f"  [{seg['index']}] {seg['start_seconds']:.1f}s→{seg['end_seconds']:.1f}s "
                f"speed={seg['speed']} tone={seg['tone']} review={seg['review_required']}"
            )
            lines.append(f"  > {seg['text'][:60]}{'…' if len(seg['text'])>60 else ''}")
        lines.append("")

    notes = queue.get("notes") or []
    if notes:
        lines.append("## 주의사항")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


def write_tts_queue_files(
    queue: Dict[str, Any],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"tts_queue_{ts}"
    json_path = out / f"{base}.json"
    md_path = out / f"{base}.md"
    json_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_tts_queue_markdown(queue), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def load_json(path: Any) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
