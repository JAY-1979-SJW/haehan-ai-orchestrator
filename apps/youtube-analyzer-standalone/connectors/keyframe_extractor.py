"""FFmpeg 장면전환 감지로 키프레임 추출. 별도 비전모델 없이 이미지 파일만 만들고,
실제 장면 판독은 Claude Code 가 Read 도구로 이미지를 직접 읽어 수행한다."""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path
from typing import Any

_FRAME_DIR = Path(__file__).parent.parent / "data" / "frames"

_MAX_FRAMES = 12  # 기본 상한(과도한 이미지 판독 비용을 막기 위함). max_frames 인자로 상향 가능.


def extract_keyframes(
    video_id: str, media_path: str, scene_threshold: float = 0.3, max_frames: int = _MAX_FRAMES
) -> list[dict[str, Any]]:
    """장면전환 시점 프레임을 jpg 로 추출. 반환: [{index, timestamp, path}, ...]

    media_path 가 오디오 전용(mp3)이면 프레임 추출이 불가능하므로 RuntimeError.
    """
    if Path(media_path).suffix.lower() in (".mp3", ".m4a", ".wav"):
        raise RuntimeError(
            "오디오 전용 파일에는 영상 프레임이 없습니다. "
            "download_video(audio_only=False) 로 영상을 다시 받아야 합니다."
        )

    out_dir = _FRAME_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()

    out_pattern = str(out_dir / "frame_%03d.jpg")
    cmd = [
        "ffmpeg",
        "-i",
        media_path,
        "-vf",
        f"select='gt(scene,{scene_threshold})',showinfo",
        "-vsync",
        "vfr",
        "-frames:v",
        str(max_frames),
        "-y",
        out_pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    timestamps = _parse_showinfo_timestamps(result.stderr)
    frames = sorted(out_dir.glob("frame_*.jpg"))

    # 단일 샷 영상 등 장면전환이 감지되지 않으면 위 명령이 프레임 0개로 실패(nonzero exit)한다.
    # 이 경우 시간 균등 간격 샘플링으로 폴백해 최소한의 키프레임은 확보한다.
    if result.returncode != 0 or not frames:
        duration = _get_duration_seconds(media_path)
        timestamps = _evenly_spaced_timestamps(duration, count=max_frames)
        for old in out_dir.glob("*.jpg"):
            old.unlink()
        for i, ts in enumerate(timestamps):
            frame_path = out_dir / f"frame_{i + 1:03d}.jpg"
            fallback_cmd = ["ffmpeg", "-ss", str(ts), "-i", media_path, "-frames:v", "1", "-y", str(frame_path)]
            fb_result = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=60)
            if fb_result.returncode != 0:
                raise RuntimeError(f"ffmpeg 균등 샘플링 폴백도 실패: {fb_result.stderr[-500:]}")
        frames = sorted(out_dir.glob("frame_*.jpg"))

    return [
        {
            "index": i,
            "timestamp": timestamps[i] if i < len(timestamps) else None,
            "path": str(frame_path),
        }
        for i, frame_path in enumerate(frames)
    ]


def _get_duration_seconds(media_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", media_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float(result.stdout.strip())


def _evenly_spaced_timestamps(duration: float, count: int) -> list[float]:
    if duration <= 0:
        return [0.0]
    step = duration / (count + 1)
    return [round(step * (i + 1), 1) for i in range(count)]


def _parse_showinfo_timestamps(stderr: str) -> list[float]:
    """ffmpeg showinfo 필터 로그에서 각 프레임의 pts_time 을 추출."""
    timestamps = []
    for line in stderr.splitlines():
        if "pts_time:" in line:
            part = line.split("pts_time:")[1].split()[0]
            with contextlib.suppress(ValueError):
                timestamps.append(float(part))
    return timestamps


def find_transcript_context(timestamp: float, segments: list[dict[str, Any]], window: float = 5.0) -> str:
    """프레임 시각 기준 앞뒤 window초 이내 전사 텍스트를 모아 반환."""
    nearby = [
        seg["text"] for seg in segments if seg["start"] <= timestamp + window and seg["end"] >= timestamp - window
    ]
    return " ".join(nearby)
