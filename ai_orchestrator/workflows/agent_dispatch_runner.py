"""L6 워크플로 — 승인된 작업 분배를 주기적으로 진행시키는 백그라운드 러너.

기준서: docs/specs/2026-10-02_app_agent_dispatch.md (P3). 진행 로직 자체는 services/agent_dispatch_service.tick.
실행 중인 분배안이 없으면 스레드는 스스로 끝난다(승인·조회 시 `ensure_running` 이 다시 띄운다).
"""

from __future__ import annotations

import logging
import threading
import time

from ai_orchestrator.persistence import agent_dispatch_store as store
from ai_orchestrator.services import agent_dispatch_service as service

logger = logging.getLogger(__name__)

TICK_INTERVAL_SEC = 3.0

_thread: threading.Thread | None = None
_guard = threading.Lock()


def _loop() -> None:
    while True:
        ids = store.running_dispatch_ids()
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
