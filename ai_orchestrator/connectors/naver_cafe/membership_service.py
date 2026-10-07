"""L6 Business Workflows — 가입 카페 수집 결과를 이력과 비교해 반영하고 분석한다.

기준서: docs/specs/2026-10-05_cafe_membership_changes.md

브라우저·HTTP·scripts 를 모른다(수집은 라우터가 하고 결과 목록과 출처만 넘긴다). 보호 규칙은 domain.cafe_membership_diff 가 정한다.
- 비교가 막히면(빈 결과·화면 읽기·중복·대량 감소) 이력도 현재 목록도 덮어쓰지 않는다 → `persist_current=False`.
- 분석은 외부 AI 없이 결정적 계산(총 가입 수 추이·기간 내 신규·탈퇴 개수)만 한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_orchestrator.connectors.naver_cafe import activity
from ai_orchestrator.connectors.naver_cafe import membership_diff as diff
from ai_orchestrator.connectors.naver_cafe import membership_store as store

CHANGES_LIMIT_MAX = 100


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def apply_collection(
    cafes: list[dict[str, Any]], *, source: str, confirm_mass_change: bool = False, now: str | None = None
) -> dict[str, Any]:
    """수집 결과를 이전 스냅샷과 비교하고, 반영해도 되면 이력(스냅샷·변동 기록)에 남긴다.

    반환: `changes`(비교 결과 — status·reason·warning·baseline·new·left·renamed·total·previous_total)와
    `persist_current`(호출자가 현재 목록 파일 `my_cafes.json` 도 갱신해도 되는가).
    """
    at = now or _now()
    result = diff.compute_changes(
        store.latest_snapshot(), cafes, source=source, confirm_mass_change=confirm_mass_change
    )
    if result["persist"]:
        store.save_snapshot(diff.snapshot_entries(cafes), now_iso=at)
        if result["new"] or result["left"] or result["renamed"]:
            store.append_change(
                {
                    "at": at,
                    "new": result["new"],
                    "left": result["left"],
                    "renamed": result["renamed"],
                    "total": result["total"],
                    "previous_total": result["previous_total"],
                    "confirmed_mass_change": bool(
                        confirm_mass_change
                        and result["previous_total"]
                        and result["total"] < result["previous_total"] / 2
                    ),
                }
            )
    return {
        "changes": {k: v for k, v in result.items() if k != "persist"},
        "persist_current": bool(result["persist"]),
        "activity": activity.analyze(diff.snapshot_entries(cafes)) if result["persist"] else None,  # 막힌 수집(빈 결과·화면 읽기 대체)으로는 분석하지 않는다
    }


def recent(limit: int = 20) -> dict[str, Any]:
    """최근 변동 기록과 가입 수 추이, 기간 요약(결정적 계산)."""
    limit = max(1, min(int(limit), CHANGES_LIMIT_MAX))
    changes = store.recent_changes(limit)
    trend = store.history_totals(30)
    first, last = (trend[0]["total"], trend[-1]["total"]) if trend else (0, 0)
    latest = store.latest_snapshot()
    return {
        "changes": changes,
        "activity": activity.analyze(latest) if latest else None,
        "trend": trend,
        "summary": {
            "snapshots": len(trend),
            "current_total": last,
            "net_change_since_first": last - first if trend else 0,
            "joined_in_log": sum(len(c.get("new", [])) for c in changes),
            "left_in_log": sum(len(c.get("left", [])) for c in changes),
        },
    }
