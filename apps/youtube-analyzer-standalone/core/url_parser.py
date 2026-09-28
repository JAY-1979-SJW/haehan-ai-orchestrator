"""YouTube URL 또는 video_id 문자열에서 video_id 를 추출."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(url_or_id: str) -> str:
    """이미 순수 video_id 면 그대로 반환. URL 이면 파싱해서 추출.

    지원 형식: youtube.com/watch?v=, youtu.be/, youtube.com/shorts/, m.youtube.com
    """
    candidate = url_or_id.strip()

    if _VIDEO_ID_RE.match(candidate):
        return candidate

    parsed = urlparse(candidate)
    if not parsed.netloc:
        raise ValueError(f"video_id 도 아니고 유효한 URL도 아닙니다: {url_or_id}")

    host = parsed.netloc.lower().replace("www.", "").replace("m.", "")

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com"):
        if parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/shorts/")[1].split("/")[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.split("/embed/")[1].split("/")[0]
        else:
            qs = parse_qs(parsed.query)
            video_id = qs.get("v", [""])[0]
    else:
        raise ValueError(f"YouTube URL이 아닙니다: {url_or_id}")

    if not _VIDEO_ID_RE.match(video_id):
        raise ValueError(f"URL에서 video_id 를 추출하지 못했습니다: {url_or_id}")
    return video_id
