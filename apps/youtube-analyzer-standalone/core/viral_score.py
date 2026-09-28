"""바이럴 스크리닝 점수 계산: VPH(시간당 조회수), 참여율."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _hours_since_published(published_at: str) -> float:
    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    delta = datetime.now(UTC) - published
    return max(delta.total_seconds() / 3600, 1.0)


_VPH_RELIABLE_MAX_HOURS = 24 * 30  # VPH는 게시 후 누적치라 오래된 영상일수록 왜곡됨(30일 초과 시 신뢰 불가)


def compute_scores(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """videos: search_videos() + statistics 병합된 리스트. VPH·참여율 필드 추가 후 정렬.

    published_after 필터 없이(오래된 영상 포함) 호출하면 VPH가 "최근 급상승"이 아니라
    "역대 누적 인기"를 반영해 왜곡되므로, 게시 30일 초과 영상이 섞여 있으면
    view_count 기준으로 정렬하고 각 항목에 vph_reliable=False 를 표시한다.
    """
    scored = []
    for video in videos:
        hours = _hours_since_published(video["published_at"])
        views = video.get("view_count", 0)
        likes = video.get("like_count", 0)
        comments = video.get("comment_count", 0)

        vph = views / hours
        engagement_rate = ((likes + comments) / views * 100) if views > 0 else 0.0

        scored.append(
            {
                **video,
                "hours_since_published": round(hours, 1),
                "vph": round(vph, 1),
                "vph_reliable": hours <= _VPH_RELIABLE_MAX_HOURS,
                "engagement_rate": round(engagement_rate, 2),
            }
        )

    if any(not v["vph_reliable"] for v in scored):
        return sorted(scored, key=lambda v: v.get("view_count", 0), reverse=True)
    return sorted(scored, key=lambda v: v["vph"], reverse=True)
