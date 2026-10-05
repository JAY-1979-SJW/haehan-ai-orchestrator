"""L1 Shared Contracts — 가입 카페 목록의 신규 가입·탈퇴·이름 변경 비교 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_cafe_membership_changes.md

핵심은 **잘못된 결과로 비교하지 않는 것**이다. 로그인이 풀려 API 가 빈 목록을 주거나, 화면 읽기로 대신해 추천·최근 방문 카페가 섞이면
비교 결과가 전부 "탈퇴"·"신규"로 오판된다. 그래서 아래 경우는 비교하지 않고 경고만 낸다(저장도 하지 않는다).

- 빈 결과(로그인 만료 의심)  - 화면 읽기로 대신한 결과(`source != "api"`)  - 카페 id 중복
- 이전 대비 절반 이상 감소(대량 탈퇴로 단정하지 않는다 — 사용자가 확인한 경우에만 반영)
첫 수집(이전 이력 없음)은 기준선으로만 기록하고 신규·탈퇴를 만들지 않는다.
"""

from __future__ import annotations

import math
from typing import Any

STATUS_BASELINE = "baseline"
STATUS_OK = "ok"
STATUS_BLOCKED = "blocked"
STATUS_NEEDS_CONFIRMATION = "needs_confirmation"

API_SOURCE = "api"
MASS_DROP_RATIO = 0.5
MASS_DROP_MIN_PREVIOUS = 4  # 이전 목록이 이보다 작으면 "절반 감소"를 대량 변동으로 보지 않는다(카페 1~2개 변동일 뿐)
NAME_MAX = 80

REASONS = {
    "empty_result": "수집된 가입 카페가 0개입니다 — 네이버 로그인이 풀렸을 수 있어 비교하지 않았습니다.",
    "non_api_source": "가입 카페 전용 API 가 아니라 화면 읽기로 대신한 결과라(추천·최근 방문 카페가 섞일 수 있음) 비교하지 않았습니다.",
    "duplicate_ids": "같은 카페 id 가 중복돼 비교하지 않았습니다.",
    "mass_drop": "이전보다 가입 카페가 절반 이상 줄었습니다 — 대량 탈퇴가 아니라 수집 오류일 수 있어 확인 전에는 반영하지 않습니다.",
}


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())[:NAME_MAX]


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _entry(raw: dict[str, Any]) -> dict[str, Any]:
    """저장용 항목: 카페 id·이름·clubid 와 활동 필드(새 글 수·마지막 갱신/방문·즐겨찾기·관리·휴면·파워·공개 형태)만. 그 밖의 값은 담지 않는다."""
    return {
        "cafe_id": str(raw.get("cafe_id") or "").strip(),
        "name": _clean(raw.get("cafe_name") or raw.get("name")),
        "clubid": str(raw.get("clubid") or ""),
        "new_articles": _count(raw.get("new_articles")),
        "last_update": str(raw.get("last_update") or "")[:19],
        "last_visit": str(raw.get("last_visit") or "")[:19],
        "favorite": bool(raw.get("favorite")),
        "manage": bool(raw.get("manage")),
        "dormant": bool(raw.get("dormant")),
        "power": bool(raw.get("power")),
        "open_type": str(raw.get("open_type") or "")[:4],
    }


def snapshot_entries(cafes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """저장용 항목 목록(`_entry` 참고). id 가 없는 항목은 버린다."""
    return [e for e in (_entry(c) for c in cafes) if e["cafe_id"]]


def _blocked(reason: str, *, total: int, previous_total: int) -> dict[str, Any]:
    return {
        "status": STATUS_BLOCKED,
        "reason": reason,
        "warning": REASONS[reason],
        "baseline": False,
        "new": [],
        "left": [],
        "renamed": [],
        "total": total,
        "previous_total": previous_total,
        "persist": False,
    }


def compute_changes(
    previous: list[dict[str, Any]] | None,
    current: list[dict[str, Any]],
    *,
    source: str,
    confirm_mass_change: bool = False,
) -> dict[str, Any]:
    """이전 스냅샷과 이번 수집을 비교한다 → 상태·변동 목록·`persist`(이력과 저장본에 반영해도 되는가).

    `previous` 가 None 이면 첫 수집(기준선). 반환 키: status·reason·warning·baseline·new·left·renamed·total·previous_total·persist.
    """
    entries = snapshot_entries(current)
    prev_entries = snapshot_entries(previous or [])
    total, previous_total = len(entries), len(prev_entries)
    if total == 0:
        return _blocked("empty_result", total=0, previous_total=previous_total)
    if source != API_SOURCE:
        return _blocked("non_api_source", total=total, previous_total=previous_total)
    if len({e["cafe_id"] for e in entries}) != total:
        return _blocked("duplicate_ids", total=total, previous_total=previous_total)
    base = {
        "status": STATUS_OK,
        "reason": "",
        "warning": "",
        "baseline": False,
        "new": [],
        "left": [],
        "renamed": [],
        "total": total,
        "previous_total": previous_total,
        "persist": True,
    }
    if previous is None:
        return {**base, "status": STATUS_BASELINE, "baseline": True}
    by_prev = {e["cafe_id"]: e for e in prev_entries}
    by_now = {e["cafe_id"]: e for e in entries}
    new = [e for cid, e in by_now.items() if cid not in by_prev]
    left = [e for cid, e in by_prev.items() if cid not in by_now]
    renamed = [
        {"cafe_id": cid, "from": by_prev[cid]["name"], "to": e["name"]}
        for cid, e in by_now.items()
        if cid in by_prev and e["name"] and by_prev[cid]["name"] != e["name"]
    ]
    result = {**base, "new": new, "left": left, "renamed": renamed}
    dropped = previous_total - total
    if (
        previous_total >= MASS_DROP_MIN_PREVIOUS
        and dropped >= math.ceil(previous_total * MASS_DROP_RATIO)
        and not confirm_mass_change
    ):
        return {
            **result,
            "status": STATUS_NEEDS_CONFIRMATION,
            "reason": "mass_drop",
            "warning": REASONS["mass_drop"],
            "persist": False,
        }
    return result
