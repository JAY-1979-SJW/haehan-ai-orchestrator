"""WebSocket 기반 양방향 에이전트 클라이언트 (Stage 2).

서버(`/api/v1/local-agents/ws`)에 연결해
  - auth 로 agent_id + device_token 제출
  - 서버가 push 한 task 를 actions.execute_action() 로 실행
  - 결과를 result 메시지로 회신
  - 연결 끊김 시 지수 backoff 로 재연결

원칙 (Stage 2):
  - 사용자가 명시적으로 `config.WEBSOCKET_ENABLED=True` 로 바꾸고 CLI 로 기동한 경우에만 동작.
  - risk_level=high 작업은 서버가 승인하더라도 본 클라이언트에서는 실행하지 않는다.
    → 즉시 `NOT_IMPLEMENTED_STAGE2` 실패 응답으로 회신.
  - FORBIDDEN_ACTIONS (delete_file/upload_file/modify_file/execute_shell) 은 절대 실행 안 됨
    (actions.execute_action 자체가 ACTION_FORBIDDEN 로 거절).
  - device_token 원문은 auth 메시지에만 쓰고 어느 로그에도 기록하지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from . import __version__, config
from .actions import execute_action, FORBIDDEN_ACTIONS
from .audit import log_local_event

try:
    from ai_orchestrator.local_agent_actions import AUTO_EXECUTE_VIA_AGENT as _AUTO_EXECUTE_VIA_AGENT
except ImportError:
    # Fallback for environments where ai_orchestrator cannot be imported.
    # This maintains consistency with ai_orchestrator.local_agent_actions.
    _AUTO_EXECUTE_VIA_AGENT: frozenset[str] = frozenset({
        "ping", "system_info", "list_allowed_apps",
        "open_url", "list_files_readonly",
        "capture_screenshot",
        "ws_noop",
        "open_url_execute",
        # browser automation actions (BROWSER-4E)
        "browser.inspect",
        "browser.plan_click",
        "browser.plan_type",
        "browser.plan_submit",
        "browser.execute_click",
        "browser.execute_type",
    })

logger = logging.getLogger(__name__)

# 승인 없이도 high risk 경로로 실행 가능한 액션 — 현재 없음.
# 승인 후(approved=True) 에만 허용되는 액션 목록.
_APPROVAL_REQUIRED_ACTIONS: frozenset[str] = frozenset({
    "capture_screenshot",
    "open_url_execute",
})


def _server_ws_url() -> str:
    """config.SERVER_BASE_URL 을 ws:// 또는 wss:// 로 치환해 /api/v1/local-agents/ws 생성."""
    parsed = urlparse(config.SERVER_BASE_URL)
    scheme = parsed.scheme.lower()
    if scheme == "https":
        ws_scheme = "wss"
    elif scheme == "http":
        ws_scheme = "ws"
    else:
        # 이미 ws/wss 로 지정된 경우 그대로 존중
        ws_scheme = scheme or "ws"
    path = (parsed.path.rstrip("/") + "/api/v1/local-agents/ws")
    return urlunparse((
        ws_scheme, parsed.netloc, path, "", "", "",
    ))


def _build_result_message(task: dict, result) -> dict:
    """actions.ActionResult → 서버 result 메시지 페이로드.

    ActionResult.data 가 dict 인 경우 그대로 "data" 필드로 포함한다.
    서버는 _strip_result_data() allowlist 로 다시 필터링하므로 client 가
    완전한 보안 필터를 부담하지 않는다 — 단, raw payload/params 는 절대
    포함하지 않고 ActionResult.data 만 전달한다 (action handler 가 이미
    safe key 만 채워 둔 dict).
    """
    msg: dict = {
        "type": "result",
        "task_id": task.get("task_id", ""),
        "success": bool(getattr(result, "success", False)),
        "summary": str(getattr(result, "summary", ""))[:500],
        "error": str(getattr(result, "error", ""))[:500],
        "error_code": str(getattr(result, "error_code", ""))[:80],
    }
    data = getattr(result, "data", None)
    if isinstance(data, dict) and data:
        msg["data"] = data
    return msg


def process_task(task: dict) -> dict:
    """서버에서 받은 task 를 로컬에서 실행하고 result 메시지 dict 를 반환.

    - FORBIDDEN_ACTIONS → 즉시 ACTION_FORBIDDEN 실패 응답.
    - risk_level=high 이고 approved 플래그 없음 → NOT_IMPLEMENTED_STAGE2 실패 응답.
    - risk_level=high 이고 approved=True 이고 action 이 _APPROVAL_REQUIRED_ACTIONS 에
      포함 → execute_action() 호출. (서버가 이미 승인 게이트 통과 후에만 dispatch 하므로
      approved 플래그는 서버의 명시적 표식.)
    - 그 외 AUTO_EXECUTE_VIA_AGENT 에 포함된 action 만 execute_action() 호출.
    - 그 외는 ACTION_NOT_AUTO_EXECUTABLE 로 실패 응답.
    """
    action = str(task.get("action", "")).strip().lower()
    params = task.get("params") or {}
    risk_level = str(task.get("risk_level", "")).lower()
    task_id = str(task.get("task_id", ""))
    approved = bool(task.get("approved", False))

    if action in FORBIDDEN_ACTIONS:
        log_local_event("ws_task_forbidden", task_id=task_id, action=action)
        return {
            "type": "result", "task_id": task_id,
            "success": False, "summary": f"{action} 거절",
            "error_code": "ACTION_FORBIDDEN",
            "error": "금지 액션 (파일 수정/삭제/전송/shell)",
        }

    if risk_level == "high":
        if not (approved and action in _APPROVAL_REQUIRED_ACTIONS):
            log_local_event(
                "ws_task_high_risk_refused",
                task_id=task_id, action=action, approved=approved,
            )
            return {
                "type": "result", "task_id": task_id,
                "success": False, "summary": f"{action} 승인 필요",
                "error_code": "NOT_IMPLEMENTED_STAGE2",
                "error": "high risk 작업은 승인 게이트 통과 후에만 실행된다",
            }

    if action not in _AUTO_EXECUTE_VIA_AGENT:
        log_local_event("ws_task_not_auto_executable",
                        task_id=task_id, action=action)
        return {
            "type": "result", "task_id": task_id,
            "success": False, "summary": f"{action} 자동 실행 불가",
            "error_code": "ACTION_NOT_AUTO_EXECUTABLE",
            "error": "본 에이전트에서 자동 실행 대상 액션이 아님",
        }

    # task_id / 승인 여부를 액션에 전달 (파일명 태깅 + 액션 단계 이중 방어).
    # 서버가 보낸 params 는 이미 민감값이 제거돼 있으므로 shallow copy + 내부
    # 키 추가가 안전하다. `_` prefix 는 액션 내부 전용 표식 — 사용자 입력이
    # 이 키를 섞어 보내더라도 여기서 덮어쓰므로 spoofing 불가.
    enriched_params: dict[str, Any] = dict(params)
    if task_id:
        enriched_params["_task_id"] = task_id
    enriched_params["_approved"] = approved
    # approval_id 는 서버가 task params 에 포함해 전달한다. 사용자 조작 불가
    # (_task_id / _approved 와 동일하게 여기서 덮어쓰지 않고 params 에서 읽음).
    # open_url_execute 의 audit trail 을 위해 _approval_id 로 노출.
    # Stage 13H-2E: 서버는 dispatch payload 에 public approval_id 만 포함한다.
    # token_id 는 서버 내부 검증용이라 더 이상 dispatch 에 들어오지 않으나,
    # 1릴리즈 backward compat 을 위해 legacy "token_id" 키 fallback 을 유지한다.
    approval_id = str(
        task.get("approval_id")
        or task.get("approval_public_id")
        or params.get("_approval_id")
        or task.get("token_id")
        or ""
    )
    if approval_id:
        enriched_params["_approval_id"] = approval_id
    # capture_screenshot 의 storage_ref 생성을 위해 agent_id 도 노출.
    # 서버가 dispatch 시 task.agent_id 로 전달하므로 사용자 spoofing 불가.
    agent_id_inner = str(task.get("agent_id") or "")
    if agent_id_inner:
        enriched_params["_agent_id"] = agent_id_inner

    log_local_event("ws_task_execute", task_id=task_id, action=action,
                    approved=approved)
    result = execute_action(action, enriched_params)
    log_local_event(
        "ws_task_result", task_id=task_id, action=action,
        success=result.success, error_code=result.error_code,
    )
    return _build_result_message(task, result)


# ── 연결 루프 ────────────────────────────────────────────────────────────

def _load_websockets_module():
    """`websockets` 라이브러리를 지연 임포트. 미설치 시 명시적 에러."""
    try:
        import websockets  # type: ignore
        return websockets
    except ImportError as e:  # pragma: no cover
        raise WebSocketDependencyMissing(
            "Stage 2 WebSocket 활성화에는 `websockets` 패키지가 필요하다. "
            "`pip install websockets` 후 다시 실행하라."
        ) from e


async def _run_session(agent_id: str, device_token: str) -> None:
    """한 번의 WebSocket 세션 실행. 종료 시 재접속은 호출자가 담당."""
    websockets = _load_websockets_module()
    url = _server_ws_url()
    logger.info("WebSocket 연결 시도 | url=%s | agent_id=%s", url, agent_id)

    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        # 1) 인증
        await ws.send(json.dumps({
            "type": "auth",
            "agent_id": agent_id,
            "device_token": device_token,
            "version": __version__,
        }))

        # 첫 응답 — auth_ok 또는 close
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.error("auth 응답 없음")
            return

        try:
            first = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            logger.error("auth 응답 파싱 실패")
            return

        if first.get("type") != "auth_ok":
            logger.error("auth 실패: %s", first.get("type"))
            log_local_event("ws_auth_failed", reason=first.get("type", "unknown"))
            return

        log_local_event("ws_connected", agent_id=agent_id)
        logger.info("WebSocket auth_ok (agent_id=%s)", agent_id)

        # 2) 메시지 루프
        heartbeat_interval = max(5, getattr(config, "POLL_INTERVAL_SEC", 10))
        last_heartbeat = time.monotonic()

        while True:
            try:
                raw = await asyncio.wait_for(
                    ws.recv(), timeout=heartbeat_interval,
                )
            except asyncio.TimeoutError:
                # 주기적 heartbeat 로 서버에 pull 기회 부여
                await ws.send(json.dumps({
                    "type": "heartbeat", "agent_id": agent_id,
                }))
                last_heartbeat = time.monotonic()
                continue

            try:
                msg = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                logger.warning("서버 메시지 파싱 실패")
                continue

            mtype = str(msg.get("type", ""))
            if mtype == "task":
                task = msg.get("task") or {}
                task_id_inner = task.get("task_id", "")

                # 1) running 전송 후 running_ack 대기
                # 서버 상태 기계 요구사항: delivered → running → completed
                # running_ack 없이 result 를 보내면 delivered → completed 가
                # InvalidTaskTransitionError 를 일으키므로 반드시 대기한다.
                run_ok = False
                try:
                    await ws.send(json.dumps({
                        "type": "running",
                        "agent_id": agent_id,
                        "task_id": task_id_inner,
                    }))
                    try:
                        ack_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        ack = json.loads(ack_raw)
                        run_ok = ack.get("type") == "running_ack"
                        if not run_ok:
                            logger.warning(
                                "running_ack 대신 %s 수신 — 실행 포기 (task_id=%s)",
                                ack.get("type"), task_id_inner,
                            )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "running_ack timeout — 실행 포기 (task_id=%s)",
                            task_id_inner,
                        )
                    except (TypeError, json.JSONDecodeError):
                        logger.warning(
                            "running_ack 파싱 실패 — 실행 포기 (task_id=%s)",
                            task_id_inner,
                        )
                except Exception:
                    logger.warning(
                        "running 전송 실패 — 실행 포기 (task_id=%s)", task_id_inner,
                    )

                if not run_ok:
                    # running 상태로 전환됐을 수 있으므로 서버 timeout 에 맡긴다.
                    continue

                # 2) 로컬 실행 후 result 회신 (서버 상태: running → completed/failed)
                result_msg = process_task(task)
                result_msg["agent_id"] = agent_id
                await ws.send(json.dumps(result_msg))
            elif mtype in ("idle", "heartbeat_ack", "result_ack",
                           "running_ack", "auth_ok"):
                # 제어 응답 — 별도 처리 없음
                continue
            elif mtype == "error":
                logger.warning("서버 에러 메시지: %s", msg.get("error"))
            else:
                logger.debug("알 수 없는 서버 메시지 타입: %s", mtype)


async def run_forever(agent_id: str, device_token: str) -> None:
    """연결 유지 + 재접속 backoff 루프.

    - 지수 backoff: 1s → 2s → 4s → ... → 60s (상한). 10% jitter 추가.
    - 정상 세션 종료 후에도 재연결 (서버 재시작 / 네트워크 일시 단절 대응).
    - Ctrl+C / asyncio.CancelledError 에서만 중단.
    """
    if not config.WEBSOCKET_ENABLED:
        raise WebSocketDisabled(
            "WebSocket 비활성 — config.WEBSOCKET_ENABLED=True 로 설정 후 실행"
        )
    if not agent_id or not device_token:
        raise ValueError("agent_id / device_token 이 필요합니다")

    backoff = 1.0
    max_backoff = 60.0
    while True:
        try:
            await _run_session(agent_id, device_token)
            # 정상 종료 — 짧은 대기 후 재연결
            backoff = 1.0
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
        except WebSocketDependencyMissing:
            raise
        except Exception as e:
            logger.warning("WebSocket 세션 실패: %s | backoff=%.1fs", e, backoff)
            log_local_event("ws_session_error", error=str(e)[:200])
            jitter = random.uniform(0.0, backoff * 0.1)
            await asyncio.sleep(backoff + jitter)
            backoff = min(max_backoff, backoff * 2)


def connect(agent_id: str, device_token: str) -> None:
    """sync 엔트리 — asyncio.run(run_forever(...)) 호출."""
    if not config.WEBSOCKET_ENABLED:
        logger.info("WebSocket 비활성 — config.WEBSOCKET_ENABLED=True 필요")
        raise WebSocketDisabled(
            "WebSocket 푸시가 비활성 상태. config.WEBSOCKET_ENABLED=True 후 재실행"
        )
    try:
        asyncio.run(run_forever(agent_id, device_token))
    except KeyboardInterrupt:
        logger.info("사용자 중단")


__all__ = [
    "connect", "run_forever", "process_task",
    "WebSocketDisabled", "WebSocketDependencyMissing",
]
