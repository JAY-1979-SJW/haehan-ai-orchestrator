"""WebSocket 기반 로컬 에이전트 클라이언트 (Stage 13F-2D).

이번 단계 범위:
  - 설정 로딩 (환경변수)
  - heartbeat payload 생성
  - running payload 생성
  - task 메시지 handler 골격
  - low-risk dry-run 처리 (ping / system_info / list_allowed_apps)
  - open_url / list_files_readonly dry-run skeleton (DRY_RUN_ONLY)
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

import asyncio
import json
import logging
import os
import platform
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)

# ── 민감 키 목록 ─────────────────────────────────────────────────────────────

_SENSITIVE_KEY_PARTS: frozenset[str] = frozenset({
    "token", "password", "passwd", "pwd", "secret", "cookie",
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


# ── known path 상수 (safe_app_presence_known_paths 용) ───────────────────────

_KNOWN_PATHS: dict[str, list[str]] = {
    "browser": [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
        "C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe",
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ],
    "office": [
        "C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE",
        "C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\WINWORD.EXE",
        "C:\\Program Files\\Microsoft Office\\Office16\\WINWORD.EXE",
    ],
    "cad": [
        "C:\\Program Files\\Autodesk\\AutoCAD 2024\\acad.exe",
        "C:\\Program Files\\Autodesk\\AutoCAD 2023\\acad.exe",
        "C:\\Program Files\\Autodesk\\AutoCAD 2022\\acad.exe",
    ],
}


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


# ── running payload ───────────────────────────────────────────────────────────

def build_running(task_id: str) -> dict:
    """WS running 메시지 페이로드.

    token/device_token/params/raw_params는 포함하지 않는다.
    서버 수신 형식: {type: "running", task_id: "..."}
    """
    return {
        "type": "running",
        "task_id": task_id,
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


def _handle_ws_noop(task: dict) -> dict:
    """ws_noop: no-op task for WS dispatch smoke testing.

    실제 시스템 접근 없이 안전한 응답만 반환한다.
    """
    return {
        "success": True,
        "summary": "ws_noop_ok",
    }


def _handle_safe_echo(task: dict) -> dict:
    """safe_echo: safe echo action for agent capability validation.

    params 원문 echo 금지. PC/env/file/network 접근 금지.
    고정된 응답만 반환한다.
    """
    return {
        "success": True,
        "summary": "safe_echo_ok",
        "data": {
            "action": "safe_echo",
            "status": "ok",
        },
    }


def _handle_safe_desktop_capability(task: dict) -> dict:
    """safe_desktop_capability: desktop capability probe (boolean only).

    파일/경로/사용자명/호스트명/환경변수 접근 금지.
    고정된 capability boolean만 반환한다.
    """
    return {
        "success": True,
        "summary": "safe_desktop_capability_ok",
        "data": {
            "action": "safe_desktop_capability",
            "status": "ok",
            "capabilities": {
                "browser_supported": True,
                "office_supported": False,
                "cad_supported": False,
            },
        },
    }


def _path_exists(path: str) -> bool:
    """경로 존재 여부 확인 (테스트 mock 가능)."""
    try:
        import os as os_module
        return os_module.path.exists(path)
    except Exception:
        return False


def _detect_app_presence() -> list[dict]:
    """known paths를 확인하여 app presence boolean 계산.

    - _KNOWN_PATHS에 정의된 경로만 확인
    - 경로 자체는 result에 절대 포함하지 않음
    - 각 app_id별로 하나 이상의 경로가 존재하면 supported=True
    """
    apps_list: list[dict] = []
    for app_id, paths in _KNOWN_PATHS.items():
        supported = any(_path_exists(p) for p in paths)
        apps_list.append({"app_id": app_id, "supported": supported})
    return apps_list


def _handle_safe_app_presence_known_paths(task: dict) -> dict:
    """safe_app_presence_known_paths: app presence via known path detection.

    실제 경로는 내부에서만 사용, 결과에는 절대 포함 금지.
    각 app_id별 supported boolean만 반환한다.
    """
    apps = _detect_app_presence()
    return {
        "success": True,
        "summary": "safe_app_presence_ok",
        "data": {
            "action": "safe_app_presence_known_paths",
            "status": "ok",
            "detection_mode": "known_path_boolean",
            "apps": apps,
        },
    }


def _handle_safe_app_capability_matrix(task: dict) -> dict:
    """safe_app_capability_matrix: capability matrix with next safe actions.

    현재 browser/office/cad 지원 여부를 바탕으로 다음 가능한 safe action을 안내한다.
    실제 앱 실행/URL 열기/파일 접근 없음.
    """
    apps = _detect_app_presence()

    # next_actions mapping (고정 allowlist)
    next_actions_map = {
        "browser": ["browser_plan_open_url", "browser_inspect"],
        "office": ["excel_plan_open_workbook"],
        "cad": ["cad_plan_open_file"],
    }

    # apps에 next_actions 추가
    for app in apps:
        app_id = app.get("app_id")
        supported = app.get("supported", False)
        if supported and app_id in next_actions_map:
            app["next_actions"] = next_actions_map[app_id]
        else:
            app["next_actions"] = []

    return {
        "success": True,
        "summary": "safe_app_capability_matrix_ok",
        "data": {
            "action": "safe_app_capability_matrix",
            "status": "ok",
            "detection_mode": "known_path_boolean",
            "apps": apps,
        },
    }


def _classify_host(hostname: str) -> str:
    """URL hostname을 보안 분류 (raw hostname 미반환).

    - public: public domain (일반적인 인터넷 도메인)
    - private_or_local: localhost, 127.0.0.1, 192.168.*, 10.*, 172.16-31.*, 또는 .local
    - sample: example.com, example.org, example.net, test.com, localhost
    - blocked: 내부 서버 또는 차단 목록
    - invalid: 파싱 실패 또는 unknown
    """
    if not hostname:
        return "invalid"

    hostname_lower = hostname.lower()

    # sample domains (테스트 목적)
    if hostname_lower in ("example.com", "example.org", "example.net", "test.com", "localhost"):
        return "sample"

    # private/local addresses
    if hostname_lower == "localhost" or hostname_lower.startswith("127."):
        return "private_or_local"
    if hostname_lower.startswith("192.168.") or hostname_lower.startswith("10.") or hostname_lower.startswith("172."):
        return "private_or_local"
    if hostname_lower.endswith(".local"):
        return "private_or_local"

    # 보안: 내부 서버/차단 목록 (아직 비어있음)
    # blocked_hosts = {"internal.server", "blocked.host"}
    # if hostname_lower in blocked_hosts:
    #     return "blocked"

    # default: public
    return "public"


def _handle_browser_plan_open_url(task: dict) -> dict:
    """browser.plan_open_url: plan to open URL in browser (plan-only, no execution).

    - URL을 파싱/검증하되 실제 실행 금지
    - scheme은 http/https만 허용
    - username/password가 URL에 있으면 거부
    - result에는 plan/target 메타데이터만 반환
    - raw URL/normalized_url/host 원문 반환 금지
    """
    params = task.get("params", {})
    target_url = (params.get("target_url") or params.get("url") or "").strip()

    if not target_url:
        return {
            "success": False,
            "summary": "browser_plan_open_url_invalid_url",
            "data": {
                "action": "browser.plan_open_url",
                "status": "error_invalid_url",
            },
        }

    from urllib.parse import urlparse
    try:
        parsed = urlparse(target_url)
        scheme = (parsed.scheme or "").lower()
        hostname = (parsed.hostname or "").lower() if parsed.hostname else ""

        # scheme 검증 (http/https만 허용)
        if scheme not in ("http", "https"):
            return {
                "success": False,
                "summary": "browser_plan_open_url_invalid_scheme",
                "data": {
                    "action": "browser.plan_open_url",
                    "status": "error_invalid_scheme",
                },
            }

        # username/password 검증
        if parsed.username or parsed.password:
            return {
                "success": False,
                "summary": "browser_plan_open_url_credentials_in_url",
                "data": {
                    "action": "browser.plan_open_url",
                    "status": "error_credentials_in_url",
                },
            }

        # host_class 분류
        host_class = _classify_host(hostname)
        if host_class == "blocked":
            return {
                "success": False,
                "summary": "browser_plan_open_url_blocked_target",
                "data": {
                    "action": "browser.plan_open_url",
                    "status": "error_blocked_target",
                    "target": {
                        "scheme": scheme,
                        "host_class": host_class,
                        "url_redacted": True,
                    },
                },
            }

        return {
            "success": True,
            "summary": "browser_plan_open_url_ok",
            "data": {
                "action": "browser.plan_open_url",
                "status": "ok",
                "plan": {
                    "action_id": "browser.plan_open_url",
                    "will_open_browser": False,
                    "will_navigate": False,
                    "requires_approval": True,
                },
                "target": {
                    "scheme": scheme,
                    "host_class": host_class,
                    "url_redacted": True,
                },
            },
        }
    except Exception:
        return {
            "success": False,
            "summary": "browser_plan_open_url_parse_error",
            "data": {
                "action": "browser.plan_open_url",
                "status": "error_parse_error",
            },
        }


def _handle_browser_inspect(task: dict) -> dict:
    """browser.inspect: plan page inspection (plan-only, no actual browser/DOM access).

    - params는 {}만 허용 (사용자 입력 거부)
    - 실제 브라우저 실행/DOM 접근/screenshot 금지
    - inspection_mode는 고정 enum값 (page_layout 권장)
    - plan/capabilities boolean만 반환
    - will_access_dom=false, will_capture_screenshot=false, actual_inspection_enabled=false 필수
    """
    params = task.get("params", {})

    # params는 {}만 허용, 키가 있으면 invalid_params
    if params and not isinstance(params, dict):
        return {
            "success": False,
            "summary": "browser_inspect_invalid_params",
            "data": {
                "action": "browser.inspect",
                "status": "error_invalid_params",
            },
        }

    # params에 키가 있으면 거부
    if params:
        return {
            "success": False,
            "summary": "browser_inspect_invalid_params",
            "data": {
                "action": "browser.inspect",
                "status": "error_invalid_params",
            },
        }

    return {
        "success": True,
        "summary": "browser_inspect_ok",
        "data": {
            "action": "browser.inspect",
            "status": "ok",
            "inspection_mode": "page_layout",
            "plan": {
                "action_id": "browser.inspect",
                "will_open_browser": False,
                "will_access_dom": False,
                "will_capture_screenshot": False,
                "requires_approval": True,
            },
            "capabilities": {
                "can_plan_inspection": True,
                "actual_inspection_enabled": False,
            },
        },
    }


_LOW_RISK_HANDLERS = {
    "ping": _handle_ping,
    "system_info": _handle_system_info,
    "list_allowed_apps": _handle_list_allowed_apps,
    "ws_noop": _handle_ws_noop,
    "safe_echo": _handle_safe_echo,
    "safe_desktop_capability": _handle_safe_desktop_capability,
    "safe_app_presence_known_paths": _handle_safe_app_presence_known_paths,
    "safe_app_capability_matrix": _handle_safe_app_capability_matrix,
    "browser.plan_open_url": _handle_browser_plan_open_url,
    "browser.inspect": _handle_browser_inspect,
}

LOW_RISK_ACTIONS: frozenset[str] = frozenset(_LOW_RISK_HANDLERS)


# ── dry-run blocked handlers ──────────────────────────────────────────────────

def _handle_open_url(task: dict) -> dict:
    """open_url dry-run skeleton.

    실제 브라우저 실행 금지, 외부 URL 접속 금지.
    raw URL/query/fragment는 result에 포함하지 않는다.
    """
    return build_result(
        task_id=(task.get("task_id") or task.get("id") or "").strip(),
        success=False,
        summary="open_url is in dry-run mode; browser not launched",
        error_code="DRY_RUN_ONLY",
    )


def _handle_list_files_readonly(task: dict) -> dict:
    """list_files_readonly dry-run skeleton.

    실제 파일 시스템 접근 금지.
    path/raw_path/absolute_path는 result에 포함하지 않는다.
    """
    return build_result(
        task_id=(task.get("task_id") or task.get("id") or "").strip(),
        success=False,
        summary="list_files_readonly is in dry-run mode; filesystem not accessed",
        error_code="DRY_RUN_ONLY",
    )


_DRY_RUN_HANDLERS = {
    "open_url": _handle_open_url,
    "list_files_readonly": _handle_list_files_readonly,
}

DRY_RUN_ACTIONS: frozenset[str] = frozenset(_DRY_RUN_HANDLERS)


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
    """이번 단계(13F-2A/2B)에서 구현되지 않은 액션."""


class BlockedAction(Exception):
    """이번 단계에서 실행이 차단된 액션 (high-risk 등)."""


def handle_task(task: dict, *, dry_run: bool = True) -> dict:
    """WS 수신 task 처리 골격.

    - low-risk 3종: dry_run 무관하게 completed result 반환
    - dry-run 2종(open_url/list_files_readonly): DRY_RUN_ONLY result 반환
    - high-risk(capture_screenshot): BlockedAction 발생
    - 그 외: NotImplementedInThisStage 발생

    반환값: build_result() 페이로드 dict.
    """
    action = (task.get("action") or "").strip()
    task_id = (task.get("task_id") or task.get("id") or "").strip()

    if action in _LOW_RISK_HANDLERS:
        out = _LOW_RISK_HANDLERS[action](task)
        result = build_result(
            task_id=task_id,
            success=out.get("success", True),
            summary=out.get("summary", ""),
        )
        if "data" in out:
            result["data"] = out["data"]
        return result

    if action in _DRY_RUN_HANDLERS:
        return _DRY_RUN_HANDLERS[action](task)

    # high-risk 액션은 명시적으로 차단
    _HIGH_RISK = {"capture_screenshot"}
    if action in _HIGH_RISK:
        raise BlockedAction(
            f"action={action!r} is high-risk and blocked"
        )

    raise NotImplementedInThisStage(
        f"action={action!r} is not implemented in this stage"
    )


# ── URL 안전 검증 ─────────────────────────────────────────────────────────────

class ExternalUrlBlocked(Exception):
    """localhost/127.0.0.1 외 WebSocket URL 연결 시도 차단."""


def _http_to_ws_url(http_url: str) -> str:
    """http://example.com → ws://example.com, https://example.com → wss://example.com"""
    import urllib.parse
    parsed = urllib.parse.urlparse(http_url)
    scheme = parsed.scheme.lower()

    if scheme == "http":
        new_scheme = "ws"
    elif scheme == "https":
        new_scheme = "wss"
    else:
        new_scheme = scheme

    # Reconstruct URL with new scheme
    return urllib.parse.urlunparse((
        new_scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))


def assert_local_ws_url(url: str) -> None:
    """ws:// URL이 localhost 또는 127.0.0.1을 가리키는지 검증.

    그 외 모든 host(운영 서버, 외부 URL 등)는 ExternalUrlBlocked를 발생시킨다.
    """
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    if scheme not in ("ws", "wss"):
        raise ExternalUrlBlocked(
            f"url scheme {scheme!r} is not allowed for local smoke; "
            f"only ws:// or wss:// on localhost/127.0.0.1 are permitted"
        )
    if host not in ("localhost", "127.0.0.1"):
        raise ExternalUrlBlocked(
            f"host {host!r} is not localhost/127.0.0.1 — "
            "external WebSocket connections are blocked"
        )


# ── WS 연결 Protocol (structural subtyping) ───────────────────────────────────

class WsConnection(Protocol):
    """테스트용 WebSocket 연결 객체 인터페이스."""

    def send_json(self, data: dict) -> None: ...
    def receive_json(self) -> dict: ...


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

    def connect(
        self,
        heartbeat_count: int = 1,
        allow_task_action: str = "",
        max_tasks: int = 0,
        listen_seconds: float = 0,
        heartbeat_interval_seconds: float = 1.0,
    ) -> dict:
        """WebSocket 연결 진입점 (dry_run=False에서 실제 연결).

        dry_run=True 이면 연결하지 않는다 (운영 서버 접속 차단).
        heartbeat_count: 송수신할 heartbeat 횟수 (기본 1).
        allow_task_action: 허용할 task action (기본 "", 즉 task 처리 안 함).
        max_tasks: 처리할 최대 task 수 (기본 0, 최대 1).
        listen_seconds: heartbeat 완료 후 추가 task 대기 시간 (기본 0 = 비활성).
        heartbeat_interval_seconds: listen 중 heartbeat 송신 간격 (기본 1.0초).
        반환값: {status, agent_id, heartbeat_count, ...} (dry_run 또는 실제 연결 결과).
        """
        if not self._should_connect():
            logger.info(
                "dry_run=True or config incomplete — skipping WS connect "
                "(agent_id=%s)", self.config.agent_id
            )
            return {
                "status": "skipped",
                "dry_run": self.config.dry_run,
                "agent_id": self.config.agent_id,
            }

        # 실제 WebSocket 연결 (localhost only)
        ws_url = _http_to_ws_url(self.ws_url)
        try:
            assert_local_ws_url(ws_url)
        except ExternalUrlBlocked as e:
            logger.error("WebSocket URL validation failed: %s", e)
            return {"status": "error", "error": str(e)}

        try:
            result = asyncio.run(
                self._connect_async(
                    ws_url,
                    heartbeat_count,
                    allow_task_action=allow_task_action,
                    max_tasks=max_tasks,
                    listen_seconds=listen_seconds,
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                )
            )
            return result
        except Exception as e:
            logger.error("WebSocket connection failed: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "agent_id": self.config.agent_id,
            }

    async def _connect_async(
        self,
        ws_url: str,
        heartbeat_count: int,
        allow_task_action: str = "",
        max_tasks: int = 0,
        listen_seconds: float = 0,
        heartbeat_interval_seconds: float = 1.0,
    ) -> dict:
        """실제 WebSocket 비동기 연결."""
        try:
            import websockets
        except ImportError:
            return {
                "status": "error",
                "error": "websockets library not installed",
                "agent_id": self.config.agent_id,
            }

        try:
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as ws:
                result = await self._run_ws_protocol_async(
                    ws,
                    heartbeat_count,
                    allow_task_action=allow_task_action,
                    max_tasks=max_tasks,
                    listen_seconds=listen_seconds,
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                )
                return result
        except Exception as e:
            logger.error("WebSocket async connection error: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "agent_id": self.config.agent_id,
            }

    async def _run_ws_protocol_async(
        self,
        ws: Any,
        heartbeat_count: int,
        allow_task_action: str = "",
        max_tasks: int = 0,
        listen_seconds: float = 0,
        heartbeat_interval_seconds: float = 1.0,
    ) -> dict:
        """WebSocket 프로토콜 실행 (auth → heartbeat 반복 → [listen mode] → close).

        allow_task_action: 허용할 task action (기본 "").
        max_tasks: 처리할 최대 task 수 (기본 0).
        listen_seconds: heartbeat 완료 후 추가 task 대기 시간 (기본 0 = 비활성).
        heartbeat_interval_seconds: listen 중 heartbeat 송신 간격 (기본 1.0초).
        task 메시지 수신 시 blocked_task_dispatch 또는 safe dispatch 처리.
        """
        sent: list[dict] = []
        received: list[dict] = []
        tasks_processed: int = 0

        try:
            # 1. auth 메시지 송신
            auth = build_auth(self.config.agent_id, self.config.device_token)
            await ws.send(json.dumps(auth))
            sent.append({"type": "auth"})  # 기록에는 token 제외

            # 2. auth_ok 수신
            msg_text = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(msg_text)
            received.append(msg)
            if msg.get("type") != "auth_ok":
                logger.warning("expected auth_ok, got %r", msg.get("type"))

            # 3-4. heartbeat 반복
            for i in range(heartbeat_count):
                hb = build_heartbeat(self.config.agent_id)
                await ws.send(json.dumps(hb))
                sent.append(hb)

                # heartbeat_ack 또는 task 수신
                msg_text = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(msg_text)
                received.append(msg)

                if msg.get("type") == "task":
                    # task 처리 결정
                    task = msg.get("task", {})
                    action = (task.get("action") or "").strip()

                    # allow_task_action이 설정되어 있고 max_tasks 미도달 시만 처리
                    if (
                        allow_task_action
                        and action == allow_task_action
                        and tasks_processed < max_tasks
                    ):
                        logger.info(
                            "Processing task: action=%r (task_id=%s)",
                            action, task.get("task_id")
                        )
                        try:
                            task_id = task.get("task_id", "")
                            # Send "running" message to mark task as running (delivered → running)
                            await ws.send(json.dumps({
                                "type": "running",
                                "task_id": task_id,
                            }))
                            logger.info("Sent running message for task_id=%s", task_id)

                            # Wait for running_ack
                            try:
                                running_ack_text = await asyncio.wait_for(ws.recv(), timeout=3.0)
                                running_ack = json.loads(running_ack_text)
                                if running_ack.get("type") != "running_ack":
                                    logger.warning("unexpected message instead of running_ack: %s", running_ack.get("type"))
                            except asyncio.TimeoutError:
                                logger.warning("running_ack timeout")

                            result = handle_task(task, dry_run=self.config.dry_run)
                            current_task_id = task_id
                            await ws.send(json.dumps(result))
                            sent.append(result)
                            tasks_processed += 1
                            logger.info("Task result sent (tasks_processed=%d)", tasks_processed)

                            # Wait for result_ack before proceeding
                            logger.info("Waiting for result_ack...")
                            ack_timeout = 3.0
                            try:
                                ack_msg_text = await asyncio.wait_for(ws.recv(), timeout=ack_timeout)
                                ack_msg = json.loads(ack_msg_text)
                                if ack_msg.get("type") == "result_ack":
                                    logger.info("result_ack received: status=%s", ack_msg.get("status"))
                                else:
                                    logger.warning("unexpected message instead of result_ack: %s", ack_msg.get("type"))
                            except asyncio.TimeoutError:
                                logger.warning("result_ack timeout")
                        except (BlockedAction, NotImplementedInThisStage) as e:
                            logger.warning("Task processing failed: %s", e)
                            result = build_result(
                                task_id=task.get("task_id", ""),
                                success=False,
                                error_code="TASK_ERROR",
                                error=str(e),
                            )
                            current_task_id = task.get("task_id", "")
                            await ws.send(json.dumps(result))
                            sent.append(result)

                            # Wait for result_ack after error
                            logger.info("Waiting for result_ack after error...")
                            ack_timeout = 3.0
                            try:
                                ack_msg_text = await asyncio.wait_for(ws.recv(), timeout=ack_timeout)
                                ack_msg = json.loads(ack_msg_text)
                                if ack_msg.get("type") == "result_ack":
                                    logger.info("result_ack received: status=%s", ack_msg.get("status"))
                            except asyncio.TimeoutError:
                                logger.warning("result_ack timeout after error")
                    else:
                        # blocked 처리
                        if not allow_task_action:
                            logger.warning(
                                "task received but no action allowed (no-task mode)"
                            )
                        elif action != allow_task_action:
                            logger.warning(
                                "task action %r not allowed (expected %r)",
                                action, allow_task_action
                            )
                        else:
                            logger.warning(
                                "max_tasks (%d) reached", max_tasks
                            )
                    # task 처리 후 break (1개만 처리)
                    break

            # 5. listen mode: heartbeat 완료 후 추가 대기
            if listen_seconds > 0 and allow_task_action and tasks_processed == 0:
                logger.info("Entering listen mode for %gs (heartbeat interval=%gs)",
                           listen_seconds, heartbeat_interval_seconds)
                start_time = asyncio.get_event_loop().time()
                hb_timer = asyncio.get_event_loop().time()

                while asyncio.get_event_loop().time() - start_time < listen_seconds:
                    # 주기적 heartbeat 송신
                    now = asyncio.get_event_loop().time()
                    if now - hb_timer >= heartbeat_interval_seconds:
                        hb = build_heartbeat(self.config.agent_id)
                        await ws.send(json.dumps(hb))
                        sent.append(hb)
                        hb_timer = now

                    # recv 대기 (남은 시간 만큼)
                    remaining = listen_seconds - (now - start_time)
                    try:
                        msg_text = await asyncio.wait_for(ws.recv(), timeout=min(remaining, heartbeat_interval_seconds))
                        msg = json.loads(msg_text)
                        received.append(msg)

                        if msg.get("type") == "task":
                            task = msg.get("task", {})
                            action = (task.get("action") or "").strip()

                            if (
                                action == allow_task_action
                                and tasks_processed < max_tasks
                            ):
                                logger.info(
                                    "Processing task in listen mode: action=%r (task_id=%s)",
                                    action, task.get("task_id")
                                )
                                try:
                                    task_id = task.get("task_id", "")
                                    # Send "running" message to mark task as running (delivered → running)
                                    await ws.send(json.dumps({
                                        "type": "running",
                                        "task_id": task_id,
                                    }))
                                    logger.info("Sent running message for task_id=%s in listen mode", task_id)

                                    # Wait for running_ack
                                    try:
                                        running_ack_text = await asyncio.wait_for(ws.recv(), timeout=3.0)
                                        running_ack = json.loads(running_ack_text)
                                        if running_ack.get("type") != "running_ack":
                                            logger.warning("unexpected message instead of running_ack in listen mode: %s", running_ack.get("type"))
                                    except asyncio.TimeoutError:
                                        logger.warning("running_ack timeout in listen mode")

                                    result = handle_task(task, dry_run=self.config.dry_run)
                                    current_task_id = task_id
                                    await ws.send(json.dumps(result))
                                    sent.append(result)
                                    tasks_processed += 1
                                    logger.info("Task result sent in listen mode (tasks_processed=%d)", tasks_processed)

                                    # Wait for result_ack before closing
                                    logger.info("Waiting for result_ack...")
                                    ack_timeout = 3.0
                                    try:
                                        ack_msg_text = await asyncio.wait_for(ws.recv(), timeout=ack_timeout)
                                        ack_msg = json.loads(ack_msg_text)
                                        if ack_msg.get("type") == "result_ack":
                                            ack_task_id = ack_msg.get("task_id")
                                            if ack_task_id == current_task_id:
                                                logger.info("result_ack received: status=%s", ack_msg.get("status"))
                                            else:
                                                logger.warning("result_ack task_id mismatch: expected=%s, got=%s", current_task_id, ack_task_id)
                                        else:
                                            logger.warning("unexpected message type instead of result_ack: %s", ack_msg.get("type"))
                                    except asyncio.TimeoutError:
                                        logger.warning("result_ack timeout after %fs", ack_timeout)

                                    break  # listen mode 종료
                                except (BlockedAction, NotImplementedInThisStage) as e:
                                    logger.warning("Task processing failed in listen mode: %s", e)
                                    result = build_result(
                                        task_id=task.get("task_id", ""),
                                        success=False,
                                        error_code="TASK_ERROR",
                                        error=str(e),
                                    )
                                    current_task_id = task.get("task_id", "")
                                    await ws.send(json.dumps(result))
                                    sent.append(result)

                                    # Wait for result_ack after error result too
                                    logger.info("Waiting for result_ack after error...")
                                    ack_timeout = 3.0
                                    try:
                                        ack_msg_text = await asyncio.wait_for(ws.recv(), timeout=ack_timeout)
                                        ack_msg = json.loads(ack_msg_text)
                                        if ack_msg.get("type") == "result_ack":
                                            logger.info("result_ack received for error: status=%s", ack_msg.get("status"))
                                    except asyncio.TimeoutError:
                                        logger.warning("result_ack timeout after error")

                                    break  # listen mode 종료
                            else:
                                logger.warning("task in listen mode not allowed or max_tasks reached")
                    except asyncio.TimeoutError:
                        # recv timeout — heartbeat interval으로 재시도
                        continue

                if tasks_processed == 0:
                    logger.info("No task received during listen mode")

            return {
                "status": "ok",
                "agent_id": self.config.agent_id,
                "heartbeat_count": heartbeat_count,
                "sent": len(sent),
                "received": len(received),
                "tasks_processed": tasks_processed,
                "task_action": allow_task_action if allow_task_action else None,
                "no_task_received": tasks_processed == 0 and listen_seconds > 0,
            }

        except asyncio.TimeoutError:
            logger.error("WebSocket timeout")
            return {
                "status": "timeout",
                "agent_id": self.config.agent_id,
                "heartbeat_count": heartbeat_count,
                "sent": len(sent),
                "received": len(received),
                "tasks_processed": tasks_processed,
            }
        except Exception as e:
            logger.error("WebSocket protocol error: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "agent_id": self.config.agent_id,
            }

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


    def process_server_message(self, msg: dict) -> Optional[dict]:
        """서버에서 수신한 단일 메시지를 처리하고 응답 페이로드를 반환.

        - auth_ok: 인증 성공 수신 → None (응답 없음)
        - heartbeat_ack: heartbeat 확인 수신 → None
        - idle: keepalive → None
        - task: 작업 처리 → result 페이로드 또는 blocked result
        - error: 서버 오류 → None (로그만)
        - 알 수 없는 type: None

        실제 WS 전송은 하지 않고 페이로드만 반환한다.
        """
        mtype = (msg.get("type") or "").strip()

        if mtype == "auth_ok":
            logger.info("auth_ok received for agent_id=%s", msg.get("agent_id"))
            return None

        if mtype in ("heartbeat_ack", "idle", "running_ack", "result_ack"):
            return None

        if mtype == "task":
            task = msg.get("task")
            if not isinstance(task, dict):
                logger.warning("task message missing task field")
                return None
            task_id = (task.get("task_id") or task.get("id") or "").strip()
            try:
                return handle_task(task, dry_run=self.config.dry_run)
            except BlockedAction as e:
                logger.warning("blocked action: %s", e)
                return build_result(
                    task_id=task_id,
                    success=False,
                    error_code="BLOCKED",
                    error=str(e),
                )
            except NotImplementedInThisStage as e:
                logger.warning("not implemented: %s", e)
                return build_result(
                    task_id=task_id,
                    success=False,
                    error_code="NOT_IMPLEMENTED",
                    error=str(e),
                )

        if mtype == "error":
            logger.warning("server error: %s", msg.get("error"))
            return None

        if mtype:
            logger.debug("unknown server message type=%r", mtype)
        return None

    def process_server_message_with_running(self, msg: dict) -> list[dict]:
        """task 메시지 처리 시 running payload를 먼저 생성하고, result payload를 이어서 반환.

        task 이외의 메시지는 빈 리스트 반환.
        실제 WS 전송은 하지 않고 페이로드 목록만 반환한다.
        """
        mtype = (msg.get("type") or "").strip()
        if mtype != "task":
            return []

        task = msg.get("task")
        if not isinstance(task, dict):
            return []

        task_id = (task.get("task_id") or task.get("id") or "").strip()
        running = build_running(task_id)

        try:
            result = handle_task(task, dry_run=self.config.dry_run)
        except BlockedAction as e:
            logger.warning("blocked action: %s", e)
            result = build_result(
                task_id=task_id,
                success=False,
                error_code="BLOCKED",
                error=str(e),
            )
        except NotImplementedInThisStage as e:
            logger.warning("not implemented: %s", e)
            result = build_result(
                task_id=task_id,
                success=False,
                error_code="NOT_IMPLEMENTED",
                error=str(e),
            )

        return [running, result]

    def run_mock_loop(self, server_messages: list[dict]) -> list[dict]:
        """in-memory mock WebSocket 루프 (테스트 전용).

        server_messages: 서버가 순서대로 보내는 메시지 목록.
        반환값: client가 생성한 응답 페이로드 목록 (None 제외).

        실제 네트워크 연결 없음. dry_run 여부와 무관하게 동작.
        """
        sent: list[dict] = []

        # 1) auth 페이로드 생성 (token은 build_auth 내부에서만 사용)
        auth = build_auth(self.config.agent_id, self.config.device_token)
        sent.append(auth)

        # 2) 서버 메시지 순서대로 처리
        for msg in server_messages:
            response = self.process_server_message(msg)
            if response is not None:
                sent.append(response)

        return sent

    def run_ws_protocol(self, ws: "WsConnection", num_tasks: int = 0) -> dict:
        """실제 WebSocket 연결 객체를 통해 프로토콜 실행 (smoke 전용).

        흐름: auth → auth_ok → heartbeat → heartbeat_ack
              → (recv task → send running → send result → recv result_ack) * num_tasks

        ws: Starlette TestClient WebSocketTestSession 또는 동일 인터페이스 객체.
        num_tasks: 서버로부터 수신할 task 수 (서버 설계에 맞게 전달).
        반환값: {sent: [...], received: [...]} — 검증용 기록.

        URL 안전 검증은 호출 전 assert_local_ws_url()로 수행해야 한다.
        device_token은 auth payload에만 포함; 이후 메시지에는 포함하지 않는다.
        """
        sent: list[dict] = []
        received: list[dict] = []

        # 1. auth — device_token은 여기서만 포함
        auth = build_auth(self.config.agent_id, self.config.device_token)
        ws.send_json(auth)
        sent.append({"type": "auth"})  # 기록에는 token 제외

        # 2. auth_ok
        msg = ws.receive_json()
        received.append(msg)
        if msg.get("type") != "auth_ok":
            logger.warning("expected auth_ok, got %r", msg.get("type"))

        # 3. heartbeat
        hb = build_heartbeat(self.config.agent_id)
        ws.send_json(hb)
        sent.append(hb)

        # 4. heartbeat_ack
        msg = ws.receive_json()
        received.append(msg)

        # 5. task 목록 처리 — 서버에서 task를 수신하고 처리
        for _ in range(num_tasks):
            task_msg = ws.receive_json()  # 서버가 보내는 task 수신
            received.append(task_msg)
            payloads = self.process_server_message_with_running(task_msg)
            for payload in payloads:
                ws.send_json(payload)
                sent.append(strip_sensitive(payload))  # 기록 시 민감정보 제거
            if payloads:
                ack = ws.receive_json()
                received.append(ack)

        return {"sent": sent, "received": received}


__all__ = [
    "AgentConfig",
    "BlockedAction",
    "DRY_RUN_ACTIONS",
    "ExternalUrlBlocked",
    "LocalAgentClient",
    "LOW_RISK_ACTIONS",
    "NotImplementedInThisStage",
    "WsConnection",
    "assert_local_ws_url",
    "build_auth",
    "build_heartbeat",
    "build_result",
    "build_running",
    "handle_task",
    "load_config",
    "strip_sensitive",
]
