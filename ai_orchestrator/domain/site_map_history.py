"""L1 Shared Contracts — 사이트 지도 이력 규칙: 구조 요약·지문(fingerprint)·지도 버전(`map_rev`)·변경 감지(diff) (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md (M11)

- 구조만 다룬다(업무 식별자·이름·위험 등급·업무 지문·메뉴 주소·데이터 소스 경로). 값·시각·검증 상태는 지문에 넣지 않는다 —
  검증 상태나 관찰 시각만 바뀐 저장은 버전을 올리지 않는다.
- 업무 지문은 기존 `site_task_map` 이 업무마다 계산해 둔 것을 그대로 쓴다(새 해시 규칙을 만들지 않는다).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

RETENTION = 20  # 이력 보존 개수(기준서 Q4)
LIST_CAP = 50  # diff 목록 상한(응답 크기 제한)


def structure(site_map: dict[str, Any]) -> dict[str, Any]:
    """지도에서 구조만 뽑은 요약. 같은 구조면 항상 같은 값(정렬 고정)."""
    tasks = {
        str(t["id"]): {
            "name": str(t.get("name") or ""),
            "risk": str(t.get("risk") or ""),
            "fp": str(t.get("fingerprint") or ""),
            **({"never": str(t["never"])} if t.get("never") else {}),  # 있을 때만 넣는다 — 표시가 없는 기존 지도의 지문은 그대로
        }
        for t in site_map.get("tasks", [])
        if isinstance(t, dict) and t.get("id")
    }
    menu = sorted({str(m.get("href") or "") for m in site_map.get("menu", []) if isinstance(m, dict) and m.get("href")})
    sources = sorted(
        {f"{s.get('host', '')}{s.get('path', '')}" for s in site_map.get("data_sources", []) if isinstance(s, dict)}
    )
    return {"tasks": dict(sorted(tasks.items())), "menu": menu, "sources": sources}


def fingerprint(struct: dict[str, Any]) -> str:
    """구조 요약의 짧은 해시(12자). 검증 상태·시각처럼 자주 바뀌는 값은 구조에 없으므로 지문도 흔들리지 않는다."""
    raw = json.dumps(struct, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def next_rev(prev_rev: int, prev_fingerprint: str, new_fingerprint: str) -> tuple[int, bool]:
    """(새 버전, 구조가 바뀌었나). 처음 저장은 1, 구조가 같으면 그대로, 다르면 +1."""
    if prev_rev <= 0 or not prev_fingerprint:
        return 1, True
    if prev_fingerprint == new_fingerprint:
        return prev_rev, False
    return prev_rev + 1, True


def _changed_tasks(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    return [k for k in a if k in b and (a[k]["fp"] != b[k]["fp"] or a[k]["risk"] != b[k]["risk"] or a[k].get("never", "") != b[k].get("never", ""))]


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """두 구조 요약의 차이. `stale_candidates` 는 구조가 바뀌었거나 사라진 업무(다시 검증이 필요한 후보)."""
    old_tasks, new_tasks = old.get("tasks", {}), new.get("tasks", {})
    added = [k for k in new_tasks if k not in old_tasks]
    removed = [k for k in old_tasks if k not in new_tasks]
    changed = _changed_tasks(old_tasks, new_tasks)
    menu_added = [m for m in new.get("menu", []) if m not in old.get("menu", [])]
    menu_removed = [m for m in old.get("menu", []) if m not in new.get("menu", [])]
    src_added = [s for s in new.get("sources", []) if s not in old.get("sources", [])]
    src_removed = [s for s in old.get("sources", []) if s not in new.get("sources", [])]
    return {
        "same": not (added or removed or changed or menu_added or menu_removed or src_added or src_removed),
        "tasks_added": added[:LIST_CAP],
        "tasks_removed": removed[:LIST_CAP],
        "tasks_changed": changed[:LIST_CAP],
        "menu_added": menu_added[:LIST_CAP],
        "menu_removed": menu_removed[:LIST_CAP],
        "sources_added": src_added[:LIST_CAP],
        "sources_removed": src_removed[:LIST_CAP],
        "never_removed": [k for k in old_tasks if old_tasks[k].get("never") and k in new_tasks and not new_tasks[k].get("never")][:LIST_CAP],  # 자동 실행 불가 표시가 사라진 업무 — 사람이 확인해야 한다
        "stale_candidates": (changed + removed)[:LIST_CAP],
        "counts": {
            "tasks": [len(old_tasks), len(new_tasks)],
            "menu": [len(old.get("menu", [])), len(new.get("menu", []))],
            "sources": [len(old.get("sources", [])), len(new.get("sources", []))],
        },
    }


def pin_check(
    requested_rev: int | None, current_rev: int, current_fingerprint: str, pinned_fingerprint: str = ""
) -> dict[str, Any] | None:
    """실행 때 기준 지도 버전 확인. 어긋나면 사람에게 물을 내용을, 맞거나 지정이 없으면 None.

    버전 번호가 달라도 지문이 같으면(구조 동일) 통과한다 — 번호만 오른 경우를 막지 않는다.
    """
    if requested_rev is None or requested_rev == current_rev:
        return None
    if pinned_fingerprint and pinned_fingerprint == current_fingerprint:
        return None
    return {
        "ok": False,
        "state": "map_changed",
        "requested_rev": requested_rev,
        "current_rev": current_rev,
        "message": "기준으로 삼은 지도가 바뀌었습니다 — 재탐색 후 진행할지 사람에게 확인하세요(자동으로 최신 지도를 쓰지 않습니다)",
    }
