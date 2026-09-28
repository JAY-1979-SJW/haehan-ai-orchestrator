"""yt-dlp 로 영상/오디오 다운로드. 자막이 있으면 자막(.vtt)도 함께 받는다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yt_dlp

_DOWNLOAD_DIR = Path(__file__).parent.parent / "data" / "downloads"


def download_video(video_id: str, audio_only: bool = True) -> dict[str, Any]:
    """video_id 다운로드. 자막이 있으면 subtitle_path 를, 없으면 None 을 반환.

    audio_only=True 면 오디오 트랙만 받아 Whisper 전사 속도를 높인다(전사만 필요한 2단계 목적에 맞춤).
    """
    _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_template = str(_DOWNLOAD_DIR / f"{video_id}.%(ext)s")

    base_opts: dict[str, Any] = {
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "skip_download": False,
    }
    if audio_only:
        base_opts["format"] = "bestaudio/best"
        base_opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
        ]
    else:
        base_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        base_opts["merge_output_format"] = "mp4"

    # 자막 다운로드는 미디어 다운로드와 별개 시도로 분리한다.
    # (자막 서버 429/일시 오류로 실패해도 미디어 자체 다운로드는 성공해야 함 — 실제로 이 실패가
    #  섞여 있으면 yt-dlp 가 미디어까지 통째로 DownloadError 로 실패시켰다.)
    with yt_dlp.YoutubeDL(base_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    try:
        subtitle_opts = {
            **base_opts,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ko", "en"],
            "subtitlesformat": "vtt",
        }
        with yt_dlp.YoutubeDL(subtitle_opts) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError:
        pass

    media_ext = "mp3" if audio_only else info.get("ext", "mp4")
    media_path = _DOWNLOAD_DIR / f"{video_id}.{media_ext}"

    subtitle_path = None
    for lang in ("ko", "en"):
        candidate = _DOWNLOAD_DIR / f"{video_id}.{lang}.vtt"
        if candidate.exists():
            subtitle_path = str(candidate)
            break

    return {
        "video_id": video_id,
        "media_path": str(media_path) if media_path.exists() else None,
        "subtitle_path": subtitle_path,
        "title": info.get("title", ""),
        "duration_seconds": info.get("duration"),
    }
