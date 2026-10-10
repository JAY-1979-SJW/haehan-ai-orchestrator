"""L1 Shared Contracts — 가입 카페 활동 분석 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_site_map_m9_precise_exploration.md §4-C

가입 카페 목록 API 의 활동 필드만으로 계산한다(외부 AI 미사용): 새 글 수·마지막 갱신/방문 시각·즐겨찾기·관리·휴면·파워.
날짜는 `YYYY-MM-DD HH:MM:SS`(시간대 표기 없음 → 한국 시간으로 간주)이고, 형식이 틀리거나 비어 있으면 "알 수 없음"으로 센다(추측하지 않는다).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
VISIT_STALE_DAYS = 30
UPDATE_STALE_DAYS = 90
TOP_N = 5


def parse_kst(value: Any) -> datetime | None:
    """`YYYY-MM-DD HH:MM:SS` → 한국 시간 datetime. 형식이 틀리면 None."""
    try:
        return datetime.strptime(str(value or "").strip(), DATE_FORMAT).replace(tzinfo=KST)
    except ValueError:
        return None


def _count(value: Any) -> int:
    """새 글 수 같은 건수: 정수로 바꿀 수 없거나 음수면 0."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _days_since(value: Any, now: datetime) -> int | None:
    when = parse_kst(value)
    return None if when is None else max(0, (now - when).days)


def analyze(entries: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """스냅샷 항목(`snapshot_entries` 결과)의 활동 요약. 결정적 계산이며 값(글 내용 등)은 다루지 않는다."""
    current = now or datetime.now(KST)
    with_new = [e for e in entries if _count(e.get("new_articles")) > 0]
    visit_days = [_days_since(e.get("last_visit"), current) for e in entries]
    update_days = [_days_since(e.get("last_update"), current) for e in entries]
    top = sorted(with_new, key=lambda e: (-_count(e.get("new_articles")), str(e.get("cafe_id"))))[:TOP_N]
    return {
        "total": len(entries),
        "with_new_articles": len(with_new),
        "new_articles_total": sum(_count(e.get("new_articles")) for e in entries),
        "top_new": [
            {"cafe_id": e.get("cafe_id", ""), "name": e.get("name", ""), "new_articles": _count(e.get("new_articles"))}
            for e in top
        ],
        "favorites": sum(1 for e in entries if e.get("favorite")),
        "managed": sum(1 for e in entries if e.get("manage")),
        "power": sum(1 for e in entries if e.get("power")),
        "dormant": sum(1 for e in entries if e.get("dormant")),
        "stale_visit": sum(1 for d in visit_days if d is not None and d > VISIT_STALE_DAYS),
        "stale_update": sum(1 for d in update_days if d is not None and d > UPDATE_STALE_DAYS),
        "unknown_dates": sum(1 for v, u in zip(visit_days, update_days, strict=True) if v is None or u is None),
        "visit_stale_days": VISIT_STALE_DAYS,
        "update_stale_days": UPDATE_STALE_DAYS,
    }
