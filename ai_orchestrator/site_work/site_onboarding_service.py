"""L6 Business Workflows — 사이트 등록(온보딩): 로그인한 사이트를 호스트로 등록하고 최초 탐색으로 업무 지도를 만든다.

기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md (F1)

- 사람이 호스트를 명시해 등록한다. 브라우저 탭을 훑어 새 사이트를 찾지 않는다.
- 이 모듈은 브라우저·scripts 를 모른다. 탐색은 기존 `site_task_map_explore_service`(실행기는 라우터가 주입)를 그대로 쓴다.
- 등록 호출이 곧 사람의 승인이다: 최초 탐색 요청을 만들고 같은 호출자가 바로 승인한다(AI 에는 등록 도구가 없다).
- 상태는 요청을 읽을 때 지연 평가한다(새 백그라운드 루프 없음). 자동 탐색(auto)은 다음 단계에서 지원한다.
- 공식 API 확인(프로젝트 규칙 [0])은 안내만 한다 — 등록을 막지 않는다(사용자가 명시한 사이트).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from ..vendor_directory import vendor_directory_service as vendors
from . import site_preflight_service as preflight
from . import site_registry as sr
from . import site_registry_store as store
from . import site_task_map as tm
from . import site_task_map_explore_service as explore
from . import site_task_map_store as map_store


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _official_api(host: str) -> dict[str, Any]:
    """벤더 공식 API 안내(읽기 전용). 목록을 못 읽어도 등록은 계속하되 확인하지 못했다고 알린다."""
    try:
        found = vendors.lookup(host)
    except ValueError as e:
        return {"checked": False, "error": str(e)}
    items = [{k: v.get(k) for k in ("name", "status", "docs", "cost")} for v in found.get("vendors", [])]
    live = [i for i in items if i.get("status") in ("available", "registered")]
    if live:
        advice = "공식 API 가 이미 연결돼 있습니다 — 화면 조작보다 API 를 먼저 쓰세요."
    elif items:
        advice = "공식 API 가 있지만 아직 연결되지 않았습니다 — 신청·등록을 먼저 검토하세요."
    else:
        advice = "목록에 없습니다(공식 API 가 없다는 뜻은 아님, 미조사)."
    return {"checked": True, "found": bool(items), "vendors": items, "advice": advice}


def _map_summary(host: str) -> dict[str, Any]:
    try:
        site_map = map_store.load(host)
    except ValueError:
        return {"tasks": 0, "verified": 0, "stale": 0, "auth": tm.AUTH_PUBLIC, "login_only": False, "error": "지도 파일을 읽을 수 없습니다"}
    tasks = site_map.get("tasks", [])
    return {
        "tasks": len(tasks),
        "login_only": bool(tasks) and all(t.get("category") == "login" for t in tasks),
        "verified": sum(1 for t in tasks if t.get("state") == "verified"),
        "stale": sum(1 for t in tasks if t.get("state") == "stale"),
        "auth": site_map.get("auth", tm.AUTH_PUBLIC),
    }


def _refresh(record: dict[str, Any]) -> dict[str, Any]:
    """탐색이 끝났으면 등록 상태에 반영한다(지연 평가). 진행 중이면 그대로."""
    if record["state"] != sr.EXPLORING:
        return record
    try:
        request = explore.get_request(record.get("explore_request_id", ""))
    except ValueError:
        return record
    status, now = request["status"], _now()
    if status == explore.DONE:
        result = request.get("result") or {}
        # 사이트가 다른 호스트로 넘기면(예: cafe.naver.com → section.cafe.naver.com) 업무는 넘어간 호스트의 지도에 쌓인다.
        # 등록 호스트의 옛 지도를 보고 "사용 가능"이라고 하면 안 되므로 실제로 탐색한 호스트 기준으로 판정한다.
        explored = str(result.get("host") or record["host"])
        summary = _map_summary(explored)
        state, note = sr.state_after_exploration(result, tasks=summary["tasks"], login_only=summary["login_only"])
        if explored != record["host"]:
            note = f"{record['host']} 는 {explored} 로 이동합니다. {note}"
        updated = sr.transition(record, state, now=now, by="system", note=note)
        updated = {**updated, "last_explored_at": str(request.get("finished_at") or now), "explored_host": explored}
    elif status in (explore.FAILED, "interrupted", explore.CANCELLED):
        reason = {"failed": f"탐색 실패: {request.get('error', '')[:100]}", "cancelled": "탐색이 취소됨"}.get(
            status, "서버가 다시 켜져 탐색이 끊김"
        )
        updated = sr.transition(record, sr.REGISTERED, now=now, by="system", note=reason)
    else:
        return record
    return store.put(updated)


def _view(record: dict[str, Any]) -> dict[str, Any]:
    view = {**record, "map": _map_summary(record["host"])}
    explored = record.get("explored_host") or ""
    if explored and explored != record["host"]:  # 넘어간 호스트의 지도도 함께 보여 준다(업무는 거기에 있다)
        view["explored"] = {"host": explored, **_map_summary(explored)}
    return view


def list_sites() -> list[dict[str, Any]]:
    return [_view(_refresh(r)) for r in store.load_all()]


def get_site(host: str) -> dict[str, Any]:
    host = sr.normalize_host(host)
    record = store.get(host)
    if record is None:
        raise ValueError("등록되지 않은 사이트를 찾을 수 없습니다")
    return _view(_refresh(record))


def register(raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """사이트를 등록하고 최초 탐색을 시작한다. 이미 등록된 사이트(해제 제외)는 거부."""
    typed = str(raw.get("host") or raw.get("start_url") or "").strip()
    host = sr.normalize_host(typed)
    existing = store.get(host)
    if existing is not None and existing["state"] != sr.DEREGISTERED:
        raise ValueError("이미 등록된 사이트입니다")
    policy = sr.validate_policy(raw.get("policy") or {})
    if policy["auto_explore"] == sr.AUTO:
        raise ValueError("자동 탐색(auto)은 아직 지원하지 않습니다(다음 단계) — ask 로 등록해 주세요")
    # 입력창은 "호스트 또는 사이트 주소"를 받는다 — 경로가 있는 주소(예: https://cafe.naver.com/0moo)는 그 경로에서 탐색을 시작한다
    typed_url = typed if "://" in typed else f"https://{typed}"
    has_path = urlparse(typed_url).path not in ("", "/")
    start_url = str(raw.get("start_url") or (typed_url if has_path else f"https://{host}/"))
    if (urlparse(start_url).hostname or "").lower() != host:
        raise ValueError("시작 주소의 호스트가 등록 호스트와 다릅니다")

    now = _now()
    record = sr.new_record(host, actor=actor, now=now, policy=policy)
    if existing is not None:  # 해제했던 사이트를 다시 등록 — 이전 이력은 보존
        record["history"] = (existing.get("history") or [])[-40:] + record["history"]
    checked = preflight.run_for_registration(host)  # 사전 조사(실행기가 없으면 None) — 등록 직전 한 번, 읽기 전용
    if checked is not None:
        record["preflight"] = checked
        if checked["verdict"] == "blocked":  # 탐색을 시작하지 않는다 — 사람이 이유를 보고 다시 판단
            record = sr.transition(record, sr.BLOCKED, now=now, by=actor, note="사전 조사에서 차단: " + "; ".join(checked["reasons"])[:150])
            store.put(record)
            return {"site": _view(record), "explore_request": None, "official_api": _official_api(host), "preflight": checked}
    options = {"start_url": start_url, "max_pages": policy["max_pages"], "reason": "사이트 등록 최초 탐색"}
    for key in ("depth", "auth"):
        if raw.get(key) is not None:
            options[key] = raw[key]
    request = explore.create_request(options, actor=actor)
    record["explore_request_id"] = request["id"]
    try:
        request = explore.approve_request(request["id"], actor=actor)  # 등록한 사람이 곧 승인자
        record = sr.transition(record, sr.EXPLORING, now=_now(), by=actor, note="최초 탐색 시작")
    except ValueError as e:  # 다른 탐색이 실행 중 등 — 요청은 승인 대기로 남기고 나중에 사람이 승인
        record["note"] = f"최초 탐색은 승인 대기: {e}"[:200]
    store.put(record)
    return {"site": _view(record), "explore_request": request, "official_api": _official_api(host), "preflight": checked}


def set_policy(host: str, raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    host = sr.normalize_host(host)
    record = store.get(host)
    if record is None or record["state"] == sr.DEREGISTERED:
        raise ValueError("등록되지 않은 사이트를 찾을 수 없습니다")
    policy = sr.validate_policy({**record["policy"], **{k: v for k, v in raw.items() if v is not None}})
    if policy["auto_explore"] == sr.AUTO:
        raise ValueError("자동 탐색(auto)은 아직 지원하지 않습니다(다음 단계)")
    now = _now()
    history = [*(record.get("history") or [])[-49:], {"at": now, "state": record["state"], "by": actor, "note": "정책 변경"}]
    return _view(store.put({**record, "policy": policy, "updated_at": now, "history": history}))


def deregister(host: str, *, actor: str) -> dict[str, Any]:
    """등록을 해제한다. 저장된 업무 지도는 지우지 않는다(삭제는 별도 사람 작업)."""
    host = sr.normalize_host(host)
    record = store.get(host)
    if record is None:
        raise ValueError("등록되지 않은 사이트를 찾을 수 없습니다")
    record = _refresh(record)  # 이미 끝난 탐색은 먼저 반영한 뒤 해제한다(진행 중이면 그대로 두고 해제 — 끝나도 상태를 되돌리지 않는다)
    updated = sr.transition(record, sr.DEREGISTERED, now=_now(), by=actor, note="등록 해제 — 지도는 보존")
    return _view(store.put(updated))
