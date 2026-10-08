"""L6 Business Workflows — 사이트 탐색 요청: AI 는 요청만 만들고, 승인·실행은 사람이 한다.

기준서: docs/specs/2026-10-03_site_task_map.md (M3)

상태: pending(승인 대기) → running → done | failed,  pending → cancelled.  한 번 정해진 상태는 되돌리지 않는다.
- 실행기는 주입한다(`configure`). 이 모듈은 브라우저·scripts 를 모른다(계층 방향 유지, 시험은 가짜 실행기).
- 동시에 하나만 실행한다(브라우저 탭·사이트 부담 제한). 서버가 재시작되면 running 은 interrupted 로 보인다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from . import site_task_map as tm
from . import site_task_map_request_store as store

PENDING, RUNNING, DONE, FAILED, CANCELLED = "pending", "running", "done", "failed", "cancelled"
STATUSES = (PENDING, RUNNING, DONE, FAILED, CANCELLED)

# 실행기: (요청 dict) -> {"pages": int, "tasks": int, "aborted_reason": str}
Executor = Callable[[dict[str, Any]], dict[str, Any]]

_lock = threading.Lock()
_active: set[str] = set()
_executor: Executor | None = None
_run_async = True  # 시험에서는 False 로 바꿔 동기 실행


def configure(executor: Executor | None, *, run_async: bool = True) -> None:
    global _executor, _run_async  # 라우터가 한 번 주입하는 실행기 설정
    _executor, _run_async = executor, run_async


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _view(request: dict[str, Any]) -> dict[str, Any]:
    if request["status"] == RUNNING and request["id"] not in _active:
        return dict(request, status="interrupted")  # 서버가 다시 켜져 실행이 끊긴 요청
    return request


def create_request(raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """탐색 요청을 승인 대기로 만든다(실행하지 않는다)."""
    norm = tm.validate_explore_request(raw)
    request = {
        "id": store.new_id(),
        **norm,
        "reason": str(raw.get("reason") or "")[:200],
        "status": PENDING,
        "created_by": actor,
        "created_at": _now(),
        "decided_by": "",
        "decided_at": "",
        "result": {},
        "error": "",
    }
    store.save(request)
    return request


def get_request(request_id: str) -> dict[str, Any]:
    request = store.load(request_id)
    if request is None:
        raise ValueError("탐색 요청을 찾을 수 없습니다")
    return _view(request)


def list_requests(status: str | None = None) -> list[dict[str, Any]]:
    if status and status not in STATUSES:
        raise ValueError(f"상태는 {', '.join(STATUSES)} 중 하나여야 합니다")
    return [_view(r) for r in store.list_all(status)]


def cancel_request(request_id: str, *, actor: str) -> dict[str, Any]:
    with _lock:
        request = get_request(request_id)
        if request["status"] != PENDING:
            raise ValueError("승인 대기 중인 요청만 취소할 수 있습니다")
        done = dict(request, status=CANCELLED, decided_by=actor, decided_at=_now())
        store.save(done)
        return done


def approve_request(request_id: str, *, actor: str) -> dict[str, Any]:
    """사람이 승인 → 실행 시작. 다른 탐색이 실행 중이면 거부한다."""
    if _executor is None:
        raise ValueError("탐색 실행기가 연결되지 않았습니다")
    with _lock:
        request = get_request(request_id)
        if request["status"] != PENDING:
            raise ValueError("이미 처리된 요청입니다")
        if _active:
            raise ValueError("다른 사이트 탐색이 실행 중입니다. 끝난 뒤 다시 승인해 주세요")
        running = dict(request, status=RUNNING, decided_by=actor, decided_at=_now())
        store.save(running)
        _active.add(request_id)
    if _run_async:
        threading.Thread(target=_run, args=(running,), name=f"sitemap-explore-{request_id[:8]}", daemon=True).start()
    else:
        _run(running)
    return running


def _run(request: dict[str, Any]) -> None:
    try:
        assert _executor is not None  # approve_request 가 보장
        result = _executor(request)
        final = dict(request, status=DONE, result=result, finished_at=_now())
    except Exception as e:  # noqa: BLE001 - 실행 실패는 요청에 기록해 화면에 보인다(조용히 삼키지 않음)
        final = dict(request, status=FAILED, error=f"{type(e).__name__}: {str(e)[:300]}", finished_at=_now())
    finally:
        with _lock:
            _active.discard(request["id"])
    store.save(final)
