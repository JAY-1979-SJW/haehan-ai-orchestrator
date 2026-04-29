"""WebSocket 기반 로컬 에이전트 클라이언트 (Stage 13F-2A).

이번 단계 범위:
  - 설정 로딩 (환경변수)
  - heartbeat payload 생성
  - task 메시지 handler 골격
  - low-risk dry-run 처리 (ping / system_info / list_allowed_apps)
  - result payload 생성
  - 민감정보 제거

이번 단계에서 구현하지 않는 것:
  - 실제 서버 WebSocket 연결 (dry_run=False 시에만 연결 허용 골격 제공)
  - 브라우저 제어 / screenshot / open_url 실제 실행
  - 파일 시스템 실제 조회
  - Windows 프로그램 실행
  - background service 등록

환경변수:
  LA_SERVER_URL       서버 base URL (예: http://localhost:8400)
  LA_AGENT_ID         등록된 agent_id
  LA_DEVICE_TOKEN     device_token 원문 — 로그 출력/hardcode 금지
  LA_HEARTBEAT_SEC    heartbeat 간격(초), 기본 30
  LA_DRY_RUN          1/true/yes → dry-run 모드 (기본 True)
"""
from __future__ import annotations

import logging
import os
import platform
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 민감 키 목록 ─────────────────────────────────────────────────────────────

_SENSITIVE_KEY_PARTS: frozenset[str] = frozenset({
    "token", "password", "secret", "cookie",
    "authorization", "raw_params", "params",
    "session", "api_key", "apikey", "access_token",
    "refresh_token", "device_token", "client_secret",
})


def _is_sensitive_key(key: str) -> bool:
    if not isinstance(key, str):
        return False
    low = key.lower()
    return any(s in low for s in _SENSITIVE_KEY_PARTS)


def strip_sensitive(payload: Any) -> Any:
    """민감 키를 재귀적으로 제거한 사본 반환 (원본 불변)."""
    if isinstance(payload, dict):
        return {
            k: strip_sensitive(v)
            for k, v in payload.items()
            if not _is_sensitive_key(k)
        }
    if isinstance(payload, list):
        return [strip_sensitive(v) for v in payload]
    return payload


# ── 설정 ─────────────────────────────────────────────────────────────────────

def _parse_bool_env(key: str, default: bool = True) -> bool:
    raw = os.environ.get(key, "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    return default


@dataclass(frozen=True)
class AgentConfig:
    server_base_url: str
    agent_id: str
    # device_token: 인스턴스에 저장하되, repr/str에서는 절대 노출 금지
    device_token: str = field(repr=False, compare=False)
    heartbeat_interval: float
    dry_run: bool

    def __str__(self) -> str:
        return (
            f"AgentConfig(server={self.server_base_url!r}, "
            f"agent_id={self.agent_id!r}, "
            f"heartbeat={self.heartbeat_interval}s, "
            f"dry_run={self.dry_run})"
        )


def load_config(
    *,
    server_base_url: Optional[str] = None,
    agent_id: Optional[str] = None,
    device_token: Optional[str] = None,
    heartbeat_interval: Optional[float] = None,
    dry_run: Optional[bool] = None,
) -> AgentConfig:
    """환경변수 우선, 파라미터로 오버라이드 가능.

    device_token 원문은 로그에 절대 출력하지 않는다.
    """
    url = (server_base_url or os.environ.get("LA_SERVER_URL", "")).strip()
    aid = (agent_id or os.environ.get("LA_AGENT_ID", "")).strip()
    tok = device_token if device_token is not None else os.environ.get("LA_DEVICE_TOKEN", "")
    try:
        hb = float(
            heartbeat_interval if heartbeat_interval is not None
            else os.environ.get("LA_HEARTBEAT_SEC", 30)
        )
    except (TypeError, ValueError):
        hb = 30.0
    dr = dry_run if dry_run is not None else _parse_bool_env("LA_DRY_RUN", default=True)

    return AgentConfig(
        server_base_url=url,
        agent_id=aid,
        device_token=tok,
        heartbeat_interval=hb,
        dry_run=dr,
    )


# ── 시각 유틸 ────────────────────────────────────────────────────────────────

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── heartbeat payload ────────────────────────────────────────────────────────

def build_heartbeat(agent_id: str) -> dict:
    """WS heartbeat 메시지 페이로드.

    token/device_token은 포함하지 않는다.
    """
    return {
        "type": "heartbeat",
        "agent_id": agent_id,
        "timestamp": _iso_now(),
    }


# ── auth payload ─────────────────────────────────────────────────────────────

def build_auth(agent_id: str, device_token: str) -> dict:
    """WS 첫 auth 메시지. device_token은 이 함수 외부로 노출하지 않는다."""
    return {
        "type": "auth",
        "agent_id": agent_id,
        "device_token": device_token,
    }


# ── low-risk dry-run handlers ────────────────────────────────────────────────

def _handle_ping(task: dict) -> dict:
    return {
        "success": True,
        "summary": "pong",
    }


def _handle_system_info(task: dict) -> dict:
    return {
        "success": True,
        "summary": (
            f"os={platform.system()} "
            f"release={platform.release()} "
            f"hostname={socket.gethostname()}"
        ),
    }


def _handle_list_allowed_apps(task: dict) -> dict:
    return {
        "success": True,
        "summary": "browser,excel,hwp,cad",
    }


_LOW_RISK_HANDLERS = {
    "ping": _handle_ping,
    "system_info": _handle_system_info,
    "list_allowed_apps": _handle_list_allowed_apps,
}

LOW_RISK_ACTIONS: frozenset[str] = frozenset(_LOW_RISK_HANDLERS)


# ── result payload ────────────────────────────────────────────────────────────

def build_result(
    task_id: str,
    success: bool,
    summary: str = "",
    error_code: str = "",
    error: str = "",
    observe_summary: Optional[dict] = None,
    audit_summary: Optional[dict] = None,
) -> dict:
    """WS result 메시지 페이로드.

    observe_summary / audit_summary는 민감정보 제거 후 포함.
    """
    payload: dict = {
        "type": "result",
        "task_id": task_id,
        "success": success,
        "summary": summary[:500] if summary else "",
    }
    if error_code:
        payload["error_code"] = error_code[:80]
    if error:
        payload["error"] = error[:500]
    if observe_summary is not None:
        payload["observe_summary"] = strip_sensitive(observe_summary)
    if audit_summary is not None:
        payload["audit_summary"] = strip_sensitive(audit_summary)
    return payload


# ── task handler 골격 ────────────────────────────────────────────────────────

class NotImplementedInThisStage(Exception):
    """이번 단계(13F-2A)에서 구현되지 않은 액션."""


def handle_task(task: dict, *, dry_run: bool = True) -> dict:
    """WS 수신 task 처리 골격.

    - low-risk 3종: dry_run 무관하게 서버 자동완료용 응답 반환
    - 그 외: NotImplementedInThisStage 발생 (이번 단계 미구현)

    반환값: build_result() 에 전달할 kwargs dict.
    """
    action = (task.get("action") or "").strip()
    task_id = (task.get("task_id") or task.get("id") or "").strip()

    if action in _LOW_RISK_HANDLERS:
        out = _LOW_RISK_HANDLERS[action](task)
        return build_result(
            task_id=task_id,
            success=out.get("success", True),
            summary=out.get("summary", ""),
        )

    # 이번 단계에서 구현하지 않는 액션
    raise NotImplementedInThisStage(
        f"action={action!r} is not implemented in Stage 13F-2A"
    )


# ── WebSocket 연결 골격 ───────────────────────────────────────────────────────

class LocalAgentClient:
    """WebSocket 기반 로컬 에이전트 클라이언트 골격.

    dry_run=True 일 때는 실제 WS 연결을 시도하지 않는다.
    실제 연결 로직은 Stage 13F-2B에서 구현 예정.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    @property
    def ws_url(self) -> str:
        base = self.config.server_base_url.rstrip("/")
        return f"{base}/api/v1/local-agents/ws"

    def _should_connect(self) -> bool:
        return bool(
            not self.config.dry_run
            and self.config.server_base_url
            and self.config.agent_id
            and self.config.device_token
        )

    def connect(self) -> None:
        """WebSocket 연결 진입점.

        dry_run=True 이면 연결하지 않는다 (운영 서버 접속 차단).
        """
        if not self._should_connect():
            logger.info(
                "dry_run=True or config incomplete — skipping WS connect "
                "(agent_id=%s)", self.config.agent_id
            )
            return
        # dry_run=False 실제 연결: Stage 13F-2B에서 구현
        raise NotImplementedError(
            "Real WS connection is not implemented in Stage 13F-2A. "
            "Set dry_run=True for testing."
        )

    def run_once_dry(self) -> dict:
        """dry_run 모드에서 1회 heartbeat + 상태 반환 (테스트용).

        실제 네트워크 연결 없음.
        """
        if not self.config.dry_run:
            raise RuntimeError("run_once_dry() is only for dry_run=True")
        hb = build_heartbeat(self.config.agent_id)
        return {
            "dry_run": True,
            "heartbeat_sent": hb,
            "ws_url": self.ws_url,
            "connected": False,
        }


__all__ = [
    "AgentConfig",
    "LocalAgentClient",
    "LOW_RISK_ACTIONS",
    "NotImplementedInThisStage",
    "build_auth",
    "build_heartbeat",
    "build_result",
    "handle_task",
    "load_config",
    "strip_sensitive",
]
