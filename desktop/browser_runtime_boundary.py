"""Boundary adapter for desktop browser runtime dependencies.

``desktop.local_server`` owns the local HTTP/WebSocket surface. Browser guard,
session, realtime watcher, login resume, and action executor implementations
live under ``local_agent`` and are reached through this adapter only.
"""
from __future__ import annotations

from typing import Any

ACTION_START_NEW = "start_new"
ACTION_ATTACH_EXISTING = "attach_existing"
ACTION_ATTACH_ORPHAN_CDP = "attach_orphan_cdp"
ACTION_BLOCKED_BY_LOCK = "blocked_by_lock"
ACTION_ERROR_MULTIPLE = "error_multiple"

TAB_CLOSED = "TAB_CLOSED"

ERR_TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
ERR_TARGET_CLOSED = "TARGET_CLOSED"


def resolve_paths() -> Any:
    from local_agent.browser_instance_guard import resolve_paths as _resolve_paths

    return _resolve_paths()


def decide_browser_start(paths: Any) -> Any:
    from local_agent.browser_instance_guard import decide_browser_start as _decide_browser_start

    return _decide_browser_start(paths)


def write_lock_file(paths: Any, pid: int) -> Any:
    from local_agent.browser_instance_guard import write_lock_file as _write_lock_file

    return _write_lock_file(paths, pid)


def clear_lock_file(paths: Any) -> Any:
    from local_agent.browser_instance_guard import clear_lock_file as _clear_lock_file

    return _clear_lock_file(paths)


def quit_automation_browsers(paths: Any) -> dict:
    from local_agent.browser_instance_guard import quit_automation_browsers

    return quit_automation_browsers(paths)


def browser_session_store() -> Any:
    from local_agent.browser_session_store import default_store

    return default_store


def from_cdp_targets(rows: list[dict]) -> Any:
    from local_agent.browser_realtime_watcher import from_cdp_targets as _from_cdp_targets

    return _from_cdp_targets(rows)


def compute_events(prev: Any, curr: Any) -> Any:
    from local_agent.browser_realtime_watcher import compute_events as _compute_events

    return _compute_events(prev, curr)


def detect_login_states(curr: Any, *, prev_states: dict[str, str]) -> Any:
    from local_agent.browser_realtime_watcher import detect_login_states as _detect_login_states

    return _detect_login_states(curr, prev_states=prev_states)


def login_state_change_events(prev_states: dict[str, str], login_states: Any) -> Any:
    from local_agent.browser_realtime_watcher import login_state_change_events as _events

    return _events(prev_states, login_states)


def choose_login_target(snapshots: Any, *, work_target_id: str) -> str:
    from local_agent.browser_realtime_watcher import choose_login_target as _choose_login_target

    return _choose_login_target(snapshots, work_target_id=work_target_id)


def create_login_auto_flow_engine(*, resume_executor: Any) -> Any:
    from local_agent.login_auto_flow import LoginAutoFlowEngine

    return LoginAutoFlowEngine(resume_executor=resume_executor)


def create_pending_command(**kwargs: Any) -> Any:
    from local_agent.login_auto_flow import PendingCommand

    return PendingCommand(**kwargs)


def build_browser_action_request(payload: dict) -> Any:
    from local_agent.browser_action_executor import build_request_from_payload

    return build_request_from_payload(payload)


def execute_browser_action(request: Any) -> Any:
    from local_agent.browser_action_executor import execute

    return execute(request)
