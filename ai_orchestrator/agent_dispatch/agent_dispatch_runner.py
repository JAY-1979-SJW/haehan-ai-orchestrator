"""L6 워크플로 — 승인된 작업 분배를 주기적으로 진행시키는 백그라운드 러너.

기준서: docs/specs/2026-10-02_app_agent_dispatch.md (P3). 진행 로직 자체는 services/agent_dispatch_service.tick.
실행 중인 분배안이 없으면 스레드는 스스로 끝난다(승인·조회·서버 시작 시 `ensure_running`/`resume_running` 이 다시 띄운다).
"""

from __future__ import annotations

import logging
import threading
import time

from ai_orchestrator.agent_dispatch import agent_dispatch_service as service
from ai_orchestrator.agent_dispatch import agent_dispatch_store as store

logger = logging.getLogger(__name__)

TICK_INTERVAL_SEC = 3.0
MAX_CONSECUTIVE_DB_ERRORS = 20  # 저장소 오류가 이만큼 연속되면 스레드를 끝낸다(다음 ensure_running 이 다시 시도)

_thread: threading.Thread | None = None
_guard = threading.Lock()


def _running_ids() -> list[str] | None:
    """실행 중인 분배안 id. 저장소 오류면 None(스레드를 죽이지 않고 재시도하기 위함)."""
    try:
        return store.running_dispatch_ids()
    except Exception as exc:  # noqa: BLE001 - 저장소 일시 오류(잠금 등)로 러너가 조용히 죽지 않게 기록 후 재시도
        logger.warning("분배 러너: 저장소 조회 오류: %s", type(exc).__name__)
        return None


def _loop() -> None:
    db_errors = 0
    while True:
        ids = _running_ids()
        if ids is None:
            db_errors += 1
            if db_errors >= MAX_CONSECUTIVE_DB_ERRORS:
                logger.error("분배 러너: 저장소 오류가 계속되어 중단합니다(다음 조회·승인 때 다시 시작)")
                return
            time.sleep(TICK_INTERVAL_SEC)
            continue
        db_errors = 0
        if not ids:
            return
        for did in ids:
            try:
                service.tick(did)
            except Exception as exc:  # noqa: BLE001 - 한 분배안의 진행 오류가 러너 전체를 멈추지 않게 기록만 하고 계속
                logger.warning("분배 진행 오류 (%s): %s", did[:8], type(exc).__name__)
        time.sleep(TICK_INTERVAL_SEC)


def ensure_running() -> bool:
    """러너 스레드가 없으면 띄운다. 새로 띄웠으면 True."""
    global _thread
    with _guard:
        if _thread is not None and _thread.is_alive():
            return False
        _thread = threading.Thread(target=_loop, name="agent-dispatch-runner", daemon=True)
        _thread.start()
        return True


def resume_running() -> bool:
    """서버 시작 시 호출: 승인된 채 끝나지 않은 분배안이 있으면 러너를 띄운다. 띄웠으면 True."""
    ids = _running_ids()
    return bool(ids) and ensure_running()
