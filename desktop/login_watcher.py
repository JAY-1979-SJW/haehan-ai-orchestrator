"""로그인 watcher — CDP 탭 상태 폴링 + 로그인 자동 재개 엔진."""

from __future__ import annotations

import asyncio
import logging
import time

from . import browser_runtime_boundary
from ._broadcast import broadcast

logger = logging.getLogger(__name__)

_login_watcher_task: asyncio.Task | None = None
_login_watcher_state: dict = {
    "prev_targets": [],  # list[TargetSnapshot]
    "prev_login_states": {},  # target_id → state
    "engine": None,  # LoginAutoFlowEngine
}
_LOGIN_WATCHER_INTERVAL_SEC = 2.0

_LOGIN_BLOCKING_STATES = (
    "LOGIN_REQUIRED",
    "LOGIN_IN_PROGRESS",
    "LOGIN_ACTION_STARTED",
    "CHALLENGE_REQUIRED",
    "CONSENT_REQUIRED",
    "SESSION_EXPIRED",
)


# ── watcher start / stop ──────────────────────────────────────────────────────


async def start_login_watcher() -> None:
    global _login_watcher_task
    if _login_watcher_task is not None and not _login_watcher_task.done():
        return
    _ensure_engine()
    _login_watcher_task = asyncio.create_task(_watcher_loop())


async def stop_login_watcher() -> None:
    global _login_watcher_task
    if _login_watcher_task is None:
        return
    _login_watcher_task.cancel()
    try:
        await _login_watcher_task
    except (asyncio.CancelledError, Exception):  # noqa: S110
        pass
    _login_watcher_task = None


# ── watcher loop ──────────────────────────────────────────────────────────────


async def _watcher_loop() -> None:
    from .browser_routes import fetch_cdp_targets  # 순환 방지 — 런타임 import

    paths = browser_runtime_boundary.resolve_paths()
    _bs = browser_runtime_boundary.browser_session_store()
    while True:
        try:
            rows = await fetch_cdp_targets(paths.cdp_port)
            curr = browser_runtime_boundary.from_cdp_targets(rows)
            prev = _login_watcher_state["prev_targets"]
            for e in browser_runtime_boundary.compute_events(prev, curr):
                await broadcast(
                    {
                        "type": e.event_type,
                        "target_id": e.target_id,
                        "sanitized_url": e.sanitized_url,
                        "title": e.title,
                        "extra": e.extra,
                        "ts": time.time(),
                    }
                )
            login_states = browser_runtime_boundary.detect_login_states(
                curr,
                prev_states=_login_watcher_state["prev_login_states"],
            )
            engine = _login_watcher_state["engine"]
            for ev in browser_runtime_boundary.login_state_change_events(
                _login_watcher_state["prev_login_states"],
                login_states,
            ):
                await broadcast(
                    {
                        "type": ev.event_type,
                        "target_id": ev.target_id,
                        "sanitized_url": ev.sanitized_url,
                        "title": ev.title,
                        "extra": ev.extra,
                        "ts": time.time(),
                    }
                )
                det = login_states.get(ev.target_id)
                if det is None:
                    continue
                _bs.set_login_state(ev.target_id, det.state)
                for engine_ev in engine.on_target_state(ev.target_id, det):
                    await broadcast(
                        {
                            "type": engine_ev.type,
                            "target_id": engine_ev.target_id,
                            "sanitized_url": engine_ev.sanitized_url,
                            "title": engine_ev.title,
                            "extra": engine_ev.extra,
                            "ts": time.time(),
                        }
                    )
            _login_watcher_state["prev_targets"] = curr
            _login_watcher_state["prev_login_states"] = {tid: det.state for tid, det in login_states.items()}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("login_watcher loop exception: %s", exc)
        await asyncio.sleep(_LOGIN_WATCHER_INTERVAL_SEC)


# ── engine helpers ────────────────────────────────────────────────────────────


def _ensure_engine():
    from .blog_cafe_actions import default_resume_executor  # 런타임 import

    if _login_watcher_state.get("engine") is None:
        _login_watcher_state["engine"] = browser_runtime_boundary.create_login_auto_flow_engine(
            resume_executor=default_resume_executor,
        )
    elif getattr(_login_watcher_state["engine"], "_resume_executor", None) is None:
        _login_watcher_state["engine"]._resume_executor = default_resume_executor
    return _login_watcher_state["engine"]


def current_blocking_login() -> tuple[str, str]:
    """가장 우선순위 높은 차단 상태 (state, target_id) 또는 ('','')."""
    states: dict[str, str] = _login_watcher_state.get("prev_login_states") or {}
    for tid, st in states.items():
        if st in _LOGIN_BLOCKING_STATES:
            return st, tid
    return "", ""


async def login_precheck_and_enqueue(action_name: str, data: dict) -> bool:
    """차단 상태가 있으면 engine 에 pending command 등록 후 True 반환."""
    if data.get("_from_resume"):
        return False
    state, target_id = current_blocking_login()
    if not state:
        return False

    engine = _ensure_engine()
    snapshots = _login_watcher_state.get("prev_targets") or []
    selected = browser_runtime_boundary.choose_login_target(snapshots, work_target_id=target_id) or target_id
    cmd = browser_runtime_boundary.create_pending_command(
        command_id=f"cmd_{action_name}_{int(time.time() * 1000)}",
        action=action_name,
        source_action=action_name,
        target_id_hint=selected,
        enqueued_at=time.time(),
        original_payload=dict(data),
        login_state_at_enqueue=state,
        resume_status="pending",
    )
    engine.enqueue_work_command(cmd)
    await broadcast(
        {
            "type": "login_target_selected",
            "target_id": selected,
            "extra": {"reason": "precheck", "blocking_state": state},
            "ts": time.time(),
        }
    )
    await broadcast(
        {
            "type": "command_enqueued_pending_login",
            "command_id": cmd.command_id,
            "action": action_name,
            "blocking_state": state,
            "target_id": selected,
            "ts": time.time(),
        }
    )
    return True
