"""시공사례 이미지들로 릴스용 세로 슬라이드 영상(mp4)을 만든다.

ffmpeg 필요(로컬에 설치 확인됨, 2026-08-19). 이미지 각각을
1080x1920(세로)에 맞춰 레터박스 처리하고, 정해진 시간만큼 보여준 뒤
다음 장으로 크로스페이드 전환한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.instagram.cases import Case
from scripts.common.logger import get_logger

_log = get_logger(__name__)

REEL_DIR = Path(__file__).resolve().parents[2] / "data" / "instagram_reels"
W, H = 1080, 1920


def build_slideshow(
    case: Case,
    seconds_per_image: float = 2.0,
    fade_seconds: float = 0.6,
    max_images: int = 10,
) -> Path:
    """case.images를 이어붙인 세로(9:16) 슬라이드 mp4를 만들어 경로를 반환한다."""
    images = case.images[:max_images]
    if not images:
        raise ValueError("이미지가 없습니다")

    REEL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REEL_DIR / f"{case.category}_{case.log_no}.mp4"

    n = len(images)
    inputs: list[str] = []
    for img in images:
        inputs += ["-loop", "1", "-t", str(seconds_per_image + fade_seconds), "-i", str(img)]

    # 각 입력을 세로 캔버스에 레터박스 → [v0][v1]...로 라벨링
    scale_filters = []
    for i in range(n):
        scale_filters.append(
            f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
        )

    # xfade로 순차 크로스페이드 연결
    xfade_parts = []
    cur = "v0"
    offset = seconds_per_image
    for i in range(1, n):
        nxt = f"x{i}"
        xfade_parts.append(f"[{cur}][v{i}]xfade=transition=fade:duration={fade_seconds}:offset={offset:.2f}[{nxt}]")
        cur = nxt
        offset += seconds_per_image

    filter_complex = ";".join(scale_filters + xfade_parts)

    # Instagram 릴스는 오디오 트랙이 없으면 처리 단계에서 거부될 수 있어
    # 무음 AAC 트랙을 함께 넣는다(anullsrc).
    total = seconds_per_image * n
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-f",
        "lavfi",
        "-t",
        f"{total:.2f}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex",
        filter_complex,
        "-map",
        f"[{cur}]",
        "-map",
        f"{n}:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(out_path),
    ]
    _log.info(f"[ig-reel] ffmpeg 슬라이드 생성: {case.case_id} ({n}장)")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        _log.error(f"[ig-reel] ffmpeg 실패: {proc.stderr[-2000:]}")
        raise RuntimeError(f"ffmpeg 실패 (exit {proc.returncode})")

    return out_path


def build_slideshow_from_frames(
    frames: list[Path],
    bgm_path: Path,
    out_path: Path,
    seconds_per_image: float = 1.8,
    fade_seconds: float = 0.5,
    bgm_volume: float = 0.5,
) -> Path:
    """이미 자막이 합성된 프레임들(reel_overlay.render_reel_slide 결과물)을
    배경음악과 함께 이어붙인다. 무음 anullsrc 대신 실제 bgm mp3를 믹싱한다.
    """
    if not frames:
        raise ValueError("프레임이 없습니다")

    n = len(frames)
    inputs: list[str] = []
    for f in frames:
        inputs += ["-loop", "1", "-t", str(seconds_per_image + fade_seconds), "-i", str(f)]

    scale_filters = [
        f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
        for i in range(n)
    ]

    xfade_parts = []
    cur = "v0"
    offset = seconds_per_image
    for i in range(1, n):
        nxt = f"x{i}"
        xfade_parts.append(f"[{cur}][v{i}]xfade=transition=fade:duration={fade_seconds}:offset={offset:.2f}[{nxt}]")
        cur = nxt
        offset += seconds_per_image

    filter_complex = ";".join(scale_filters + xfade_parts)
    total = seconds_per_image * n

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-i",
        str(bgm_path),
        "-filter_complex",
        filter_complex,
        "-map",
        f"[{cur}]",
        "-map",
        f"{n}:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-af",
        f"afade=t=out:st={total - 1:.2f}:d=1,volume={bgm_volume}",
        "-t",
        str(total),
        "-shortest",
        str(out_path),
    ]
    _log.info(f"[ig-reel] bgm 합성 슬라이드 생성: {out_path.name} ({n}장)")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        _log.error(f"[ig-reel] ffmpeg 실패: {proc.stderr[-2000:]}")
        raise RuntimeError(f"ffmpeg 실패 (exit {proc.returncode})")

    return out_path
