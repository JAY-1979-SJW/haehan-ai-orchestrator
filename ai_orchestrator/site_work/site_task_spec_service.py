"""L6 Business Workflows — 업무 후보 목록과 업무 명세(task spec) 생성·조회, 승인 가능 여부 판정 (HTTP/브라우저 모름).

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md (M12)

- 후보 목록은 지도의 업무마다 위험 등급·`never`·AI 실행 가능 여부를 보여 준다(`never` 는 '자동 실행 불가').
- 명세는 지도의 업무 항목 안 `spec` 키에 저장한다(입력 **값**은 없다 — 이름·종류·민감 여부만). 명세를 저장해도 지도 구조 지문은 바뀌지 않아 `map_rev` 가 오르지 않는다.
- `never` 업무는 명세·실행 계획·승인 요청을 만들 수 없다. `assert_approvable` 은 승인 기록·확정 카드를 만들기 전에 반드시 부르는 관문이다(M6-b 가 쓴다).
- 실행(클릭·제출)은 여기서 하지 않는다 — 계획(드라이런)만 돌려준다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import site_task_map as tm
from . import site_task_map_store as store
from . import site_task_spec as sts


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _find(site_map: dict[str, Any], task_key: str) -> dict[str, Any]:
    task = next((t for t in site_map["tasks"] if t["id"] == task_key), None)
    if task is None:
        raise ValueError("업무를 찾을 수 없습니다")
    return task


def candidates(host: str) -> dict[str, Any]:
    """'이 사이트에서 할 수 있는 일' 목록. 지도가 없으면 빈 목록."""
    site_map = store.load(host)
    items = [sts.candidate_view(t, tm.effective_risk(t)) for t in site_map["tasks"]]
    return {
        "host": site_map["host"],
        "map_rev": int(site_map.get("map_rev") or 0),
        "count": len(items),
        "ai_runnable": sum(1 for i in items if i["ai_runnable"]),
        "never": sum(1 for i in items if i["never"]),
        "items": items,
    }


def _plan(spec: dict[str, Any]) -> dict[str, Any]:
    """실행 계획(드라이런) — 실제로 아무것도 실행하지 않는다."""
    return {
        "executes": spec["risk"] == "read",
        "final_action": "지도 절차대로 자동 실행"
        if spec["risk"] == "read"
        else "최종 버튼은 누르지 않음 — 사람 확정 카드에서 승인한 뒤에만",
        "inputs": [i["name"] for i in spec["inputs"]],
        "step_types": spec["step_types"],
        "approval_points": spec["approval_points"],
    }


def create_spec(host: str, task_key: str) -> dict[str, Any]:
    """업무 명세 초안을 만들어 지도에 저장하고 실행 계획을 돌려준다. never·없는 업무는 ValueError."""
    site_map = store.load(host)
    task = _find(site_map, task_key)
    risk = tm.effective_risk(task)
    spec = sts.build_spec(
        task, risk, map_rev=int(site_map.get("map_rev") or 0), placeholders=tm.step_placeholders(task.get("steps", []))
    )
    sts.validate_spec(spec)
    tasks = [dict(t, spec=spec) if t["id"] == task_key else t for t in site_map["tasks"]]
    store.save(dict(site_map, tasks=tasks, updated_at=_now()))
    return {"host": site_map["host"], "spec": spec, "plan": _plan(spec)}


def get_spec(host: str, task_key: str) -> dict[str, Any]:
    site_map = store.load(host)
    task = _find(site_map, task_key)
    spec = task.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("업무 명세를 찾을 수 없습니다")
    out: dict[str, Any] = {"host": site_map["host"], "spec": sts.validate_spec(spec), "plan": _plan(spec)}
    out["map_changed"] = int(spec.get("map_rev") or 0) != int(
        site_map.get("map_rev") or 0
    )  # 명세를 만든 뒤 지도가 바뀌었다 — 실행 전에 다시 확인
    return out


def assert_approvable(host: str, task_key: str) -> None:
    """승인 기록·확정 카드를 만들기 전의 관문. never 는 승인으로 풀 수 없으므로 거부한다."""
    task = _find(store.load(host), task_key)
    kind = sts.effective_never(dict(task, risk=tm.effective_risk(task)))
    if kind:
        raise ValueError(f"자동 실행 불가 업무입니다(never:{kind}) — 승인 요청을 만들 수 없습니다")
