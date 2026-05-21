"""Local status provider for tray app (DESK-3).

Reads state from local files and modules only.
NEVER exposes: approval_token, final_approval_token, token_hash,
typed_text, password, OTP, cookie, session, Authorization,
localStorage, sessionStorage, raw screenshot/base64.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Safe keys allowed in status output — never expose token/secret fields
_FORBIDDEN_STATUS_KEYS: frozenset[str] = frozenset({
    "approval_token", "final_approval_token", "token_hash",
    "typed_text", "password", "otp", "cookie", "session",
    "authorization", "localstorage", "sessionstorage",
    "raw_screenshot", "base64", "device_token",
})

# Default local admin mock UI URL (local only) — app_config 기반 동적 URL
try:
    from desktop.app_config import LOCAL_URL as _local_url
    ADMIN_MOCK_UI_URL = f"{_local_url}/browser-approvals"
except Exception:
    ADMIN_MOCK_UI_URL = "http://127.0.0.1:8765/browser-approvals"

# Module availability markers
_BROWSER_TASK_HANDLER_MODULE = "local_agent.browser_task_handler"
_APPROVAL_STORE_MODULE = "local_agent.browser_approval_persistent_store"
_WEBSOCKET_SCHEMA_MODULE = "local_agent.browser_websocket_schema"


@dataclass
class ServiceStatus:
    state: str  # starting / running / degraded / stopped / error
    last_heartbeat: Optional[str] = None
    pending_task_count: int = 0
    last_task_status: Optional[str] = None
    error_summary: Optional[str] = None
    approval_store_ready: bool = False
    websocket_schema_ready: bool = False
    browser_task_handler_ready: bool = False
    scheduler_autostart: bool = False
    # 작업 수신 분류 요약 (ops_router /ops/agents 와 맞물리는 필드)
    local_agent_task_count: int = 0
    user_direct_task_count: int = 0
    blocked_task_count: int = 0


@dataclass
class ApprovalStoreStatus:
    ready: bool = False
    pending_count: int = 0
    # safe summary only — no tokens


def _is_module_importable(module_name: str) -> bool:
    spec = importlib.util.find_spec(module_name)
    return spec is not None


def _safe_strip(value: str) -> str:
    """Remove any line containing forbidden keys from log/summary text."""
    safe_lines = []
    for line in value.splitlines():
        line_lower = line.lower()
        if not any(k in line_lower for k in _FORBIDDEN_STATUS_KEYS):
            safe_lines.append(line)
    return "\n".join(safe_lines)


class LocalStatusProvider:
    """Reads local-only status. Never contacts remote servers."""

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        admin_ui_url: str = ADMIN_MOCK_UI_URL,
    ) -> None:
        self._log_dir = log_dir or Path("logs")
        self._admin_ui_url = admin_ui_url

    # ------------------------------------------------------------------
    # Module availability

    def is_browser_task_handler_ready(self) -> bool:
        return _is_module_importable(_BROWSER_TASK_HANDLER_MODULE)

    def is_approval_store_ready(self) -> bool:
        return _is_module_importable(_APPROVAL_STORE_MODULE)

    def is_websocket_schema_ready(self) -> bool:
        return _is_module_importable(_WEBSOCKET_SCHEMA_MODULE)

    # ------------------------------------------------------------------
    # Approval store safe summary

    def get_approval_store_status(self) -> ApprovalStoreStatus:
        ready = self.is_approval_store_ready()
        if not ready:
            return ApprovalStoreStatus(ready=False, pending_count=0)
        try:
            mod = importlib.import_module(_APPROVAL_STORE_MODULE)
            # Try to instantiate a store and count pending
            store_cls = getattr(mod, "PersistentBrowserApprovalStore", None)
            if store_cls is None:
                return ApprovalStoreStatus(ready=True, pending_count=0)
            store = store_cls()
            pending = store.list_pending()
            return ApprovalStoreStatus(ready=True, pending_count=len(pending))
        except Exception as exc:
            logger.debug("approval store check failed: %s", exc)
            return ApprovalStoreStatus(ready=True, pending_count=0)

    # ------------------------------------------------------------------
    # Last error from logs

    def get_last_error_summary(self) -> Optional[str]:
        log_path = self._log_dir / "orchestrator.log"
        if not log_path.exists():
            return None
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            error_lines = [l for l in lines if "ERROR" in l or "CRITICAL" in l]
            if not error_lines:
                return None
            last = error_lines[-1][:200]
            return _safe_strip(last) or None
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Admin mock UI URL (local only)

    def get_admin_mock_ui_url(self) -> str:
        return self._admin_ui_url

    # ------------------------------------------------------------------
    # Local logs path

    def get_local_logs_path(self) -> Path:
        return self._log_dir.resolve()

    # ------------------------------------------------------------------
    # Aggregate service status

    def get_service_status(self, runner_state: str = "stopped") -> ServiceStatus:
        handler_ready = self.is_browser_task_handler_ready()
        store_ready = self.is_approval_store_ready()
        schema_ready = self.is_websocket_schema_ready()
        store_status = self.get_approval_store_status()
        error = self.get_last_error_summary()

        if runner_state == "running":
            state = "running" if handler_ready else "degraded"
        elif runner_state in ("starting",):
            state = "starting"
        elif runner_state == "error":
            state = "error"
        else:
            state = "stopped"

        # 작업 수신 분류 (실행 없음)
        task_queue = self.get_server_task_queue_status(source="local")
        local_agent_count = task_queue.local_agent_count if task_queue else 0
        user_direct_count = task_queue.user_direct_count if task_queue else 0
        blocked_count = task_queue.blocked_count if task_queue else 0

        return ServiceStatus(
            state=state,
            pending_task_count=store_status.pending_count,
            error_summary=error,
            approval_store_ready=store_ready,
            websocket_schema_ready=schema_ready,
            browser_task_handler_ready=handler_ready,
            local_agent_task_count=local_agent_count,
            user_direct_task_count=user_direct_count,
            blocked_task_count=blocked_count,
        )


    # ------------------------------------------------------------------
    # Server task queue status (via task_receiver, no execution)

    def get_server_task_queue_status(self, source: str = "local"):
        """서버/로컬 작업 큐 상태 조회 — 분류만, 실행 없음.

        source="local"  → in-memory 큐 (서버 미연결 안전)
        source="server" → localhost ops API (서버 연결 시)

        반환: TaskQueueStatus (민감 필드 없음)
        """
        try:
            from .task_receiver import poll_pending_tasks
            return poll_pending_tasks(source=source)
        except Exception as exc:
            logger.debug("task queue status 조회 실패: %s", exc)
            try:
                from .task_receiver import TaskQueueStatus
                return TaskQueueStatus()
            except Exception:
                return None

    # ------------------------------------------------------------------
    # Tray label for task queue

    def get_task_queue_tray_label(self, source: str = "local") -> str:
        """tray 메뉴에 표시할 작업 큐 요약 문자열."""
        status = self.get_server_task_queue_status(source=source)
        if status is None:
            return "수신 작업: -"
        return status.to_tray_label()


__all__ = [
    "LocalStatusProvider",
    "ServiceStatus",
    "ApprovalStoreStatus",
    "ADMIN_MOCK_UI_URL",
    "_FORBIDDEN_STATUS_KEYS",
]
