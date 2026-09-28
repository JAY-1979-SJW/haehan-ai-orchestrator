"""전사: 자막(.vtt)이 있으면 파싱해서 재사용, 없으면 로컬 faster-whisper 로 음성 전사."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

_TRANSCRIPT_DIR = Path(__file__).parent.parent / "data" / "transcripts"

_VTT_TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})")


def _vtt_time_to_seconds(t: str) -> float:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _dedupe_rolling_words(prev_words: list[str], new_words: list[str]) -> list[str]:
    """YouTube 자동자막은 캡션마다 이전 캡션 끝부분 단어를 반복하며 새 단어를 덧붙이는
    '롤링' 방식이라, 줄 단위 비교로는 중복이 제거되지 않는다. prev_words 끝부분과
    new_words 앞부분의 최장 겹침을 찾아 겹치지 않는 새 단어만 반환한다."""
    max_overlap = min(len(prev_words), len(new_words))
    for overlap in range(max_overlap, 0, -1):
        if prev_words[-overlap:] == new_words[:overlap]:
            return new_words[overlap:]
    return new_words


def parse_vtt(vtt_path: str) -> list[dict[str, Any]]:
    """VTT 자막 파일을 [{start, end, text}, ...] 로 파싱. 자동자막 롤링 중복을 단어 단위로 제거."""
    text = Path(vtt_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    segments: list[dict[str, Any]] = []
    i = 0
    accumulated_words: list[str] = []
    while i < len(lines):
        match = _VTT_TIME_RE.search(lines[i])
        if match:
            start = _vtt_time_to_seconds(match.group(1))
            end = _vtt_time_to_seconds(match.group(2))
            i += 1
            caption_lines = []
            while i < len(lines) and lines[i].strip():
                caption_lines.append(html.unescape(re.sub(r"<[^>]+>", "", lines[i])).strip())
                i += 1
            caption_text = " ".join(caption_lines).strip()
            new_words = caption_text.split()
            incremental = _dedupe_rolling_words(accumulated_words, new_words)
            if incremental:
                segments.append({"start": round(start, 1), "end": round(end, 1), "text": " ".join(incremental)})
                accumulated_words = new_words
        i += 1
    return segments


def transcribe_audio(audio_path: str, model_size: str = "base") -> list[dict[str, Any]]:
    """faster-whisper 로 로컬 음성 전사. [{start, end, text}, ...] 반환."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(audio_path, language=None, vad_filter=True)
    return [{"start": round(seg.start, 1), "end": round(seg.end, 1), "text": seg.text.strip()} for seg in segments]


def get_transcript(
    video_id: str, subtitle_path: str | None, audio_path: str | None, model_size: str = "base"
) -> dict[str, Any]:
    """자막 우선, 없으면 whisper 전사. 결과를 data/transcripts/<video_id>.json 저장 경로와 함께 반환."""
    if subtitle_path and Path(subtitle_path).exists():
        segments = parse_vtt(subtitle_path)
        source = "subtitle"
    elif audio_path and Path(audio_path).exists():
        segments = transcribe_audio(audio_path, model_size=model_size)
        source = f"whisper:{model_size}"
    else:
        raise RuntimeError("자막도 오디오 파일도 없습니다 (다운로드 먼저 실행 필요)")

    full_text = " ".join(seg["text"] for seg in segments)
    return {"video_id": video_id, "source": source, "segments": segments, "full_text": full_text}
