"""Execution Location Guard — 서버 측 외부 웹 실행 차단 강제."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# 실행 위치 enum
SERVER_INTERNAL_ONLY = "SERVER_INTERNAL_ONLY"
LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
USER_DIRECT_REQUIRED = "USER_DIRECT_REQUIRED"
BLOCKED = "BLOCKED"

# 차단 사유
BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION = "BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION"
BLOCKED_SERVER_PLAYWRIGHT_EXECUTION = "BLOCKED_SERVER_PLAYWRIGHT_EXECUTION"
BLOCKED_SERVER_BROWSER_LAUNCH = "BLOCKED_SERVER_BROWSER_LAUNCH"
BLOCKED_EXTERNAL_URL_FROM_SERVER = "BLOCKED_EXTERNAL_URL_FROM_SERVER"
BLOCKED_UNSAFE_EXECUTION_LOCATION = "BLOCKED_UNSAFE_EXECUTION_LOCATION"

# 내부 host (서버 실행 허용)
_INTERNAL_HOSTS = frozenset(
    (
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",  # noqa: S104 - 소켓 bind 코드가 아니라 내부 허용 host 판별용 문자열 상수 목록
    )
)

# 내부 docker service host suffix
_INTERNAL_DOMAIN_SUFFIX = (
    ".internal",
    ".local",
    ".svc.cluster.local",
)

# 외부 실행 작업 키워드 (action 분류)
_EXTERNAL_WEB_ACTIONS = frozenset(
    (
        "open_url",
        "read_page",
        "extract_text",
        "extract_tables",
        "download",
        "download_file",
        "screenshot",
        "fill_form",
        "form_fill",
        "click",
        "navigate",
        "search",
        "login",
        "selector_discovery",
        "page_observation",
    )
)

_USER_DIRECT_ACTIONS = frozenset(
    (
        "submit",
        "sign",
        "e_signature",
        "payment",
        "transfer",
        "bid",
        "final_submit",
        "결제",
        "송금",
        "투찰",
        "전자서명",
    )
)

_SAFE_FIELDS = (
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
)


def _is_internal_host(host: str) -> bool:
    """host가 서버 실행 허용 대상인지 확인."""
    if not host:
        return False
    h = host.lower().split(":")[0]
    if h in _INTERNAL_HOSTS:
        return True
    # docker compose service name (점 없음, 영문/숫자/하이픈)
    if "." not in h and all(c.isalnum() or c == "-" or c == "_" for c in h):
        return True
    if any(h.endswith(s) for s in _INTERNAL_DOMAIN_SUFFIX):
        return True
    # private IP 범위 (간단 체크)
    if h.startswith("10.") or h.startswith("192.168."):
        return True
    if h.startswith("172."):
        try:
            second = int(h.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (ValueError, IndexError):
            pass
    return False


def _extract_host(url: str) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001 - _extract_host: URL host 파싱 실패 시 빈 문자열 반환 - 빈 host는 _is_internal_host에서 False(내부 아님) 처리되어 이후 분류가 LOCAL_AGENT_REQUIRED(서버 직접실행 차단, handoff 필요)로 귀결되는 fail-closed 경로, 서버 외부실행 허용 방향 아님
        return ""


def classify_execution_location_for_server(task: dict[str, Any]) -> dict[str, Any]:
    """서버 관점에서 task의 실행 위치를 분류한다."""
    target_url = task.get("target_url", "") or task.get("url", "")
    action = (task.get("action") or "").lower()

    host = _extract_host(target_url)

    # URL 없는 task는 서버 내부 처리 가능
    if not target_url:
        return _result(SERVER_INTERNAL_ONLY, reason="target_url 없음 — 서버 내부 작업으로 처리", blocked=False)

    # 내부 host
    if _is_internal_host(host):
        return _result(SERVER_INTERNAL_ONLY, reason=f"내부 host: {host}", blocked=False, target_host=host)

    # 외부 host + 외부 웹 action → LOCAL_AGENT_REQUIRED
    if action in _EXTERNAL_WEB_ACTIONS or not action:
        return _result(
            LOCAL_AGENT_REQUIRED, reason="외부 URL — local agent로 handoff 필요", blocked=False, target_host=host
        )

    # 외부 host + 결제/송금/투찰 → USER_DIRECT
    if action in _USER_DIRECT_ACTIONS:
        return _result(
            USER_DIRECT_REQUIRED, reason="결제/송금/투찰/서명 — 사용자 직접 수행", blocked=False, target_host=host
        )

    # 그 외 외부 URL은 일단 LOCAL_AGENT_REQUIRED
    return _result(LOCAL_AGENT_REQUIRED, reason="외부 URL 기본 처리: local agent", blocked=False, target_host=host)


def assert_server_may_not_execute_external_web(task: dict[str, Any]) -> None:
    """서버가 외부 웹 실행을 시도하면 ValueError를 raise."""
    cls = classify_execution_location_for_server(task)
    if cls["execution_location"] == LOCAL_AGENT_REQUIRED:
        raise ValueError(
            f"BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION: "
            f"외부 URL '{cls.get('target_host')}'은 서버에서 실행할 수 없습니다. "
            f"local agent task로 handoff하세요."
        )
    if cls["execution_location"] == BLOCKED:
        raise ValueError(f"{cls.get('blocked_reason', BLOCKED_UNSAFE_EXECUTION_LOCATION)}")


def require_local_agent_for_external_url(url: str) -> dict[str, Any]:
    """외부 URL이면 local agent 필요 응답 반환."""
    host = _extract_host(url)
    if _is_internal_host(host):
        return {
            "requires_local_agent": False,
            "execution_location": SERVER_INTERNAL_ONLY,
            "target_host": host,
        }
    return {
        "requires_local_agent": True,
        "execution_location": LOCAL_AGENT_REQUIRED,
        "target_host": host,
        "blocked_reason": BLOCKED_EXTERNAL_URL_FROM_SERVER,
    }


def validate_task_execution_location(task: dict[str, Any]) -> dict[str, Any]:
    """task의 execution_location 필드 정합성 검증."""
    cls = classify_execution_location_for_server(task)
    declared = task.get("execution_location")
    expected = cls["execution_location"]

    if declared and declared != expected:
        # external URL인데 SERVER_INTERNAL로 선언하면 차단
        if expected == LOCAL_AGENT_REQUIRED and declared == SERVER_INTERNAL_ONLY:
            return {
                "valid": False,
                "expected": expected,
                "declared": declared,
                "blocked_reason": BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION,
            }

    if task.get("server_browser_used") is True:
        return {
            "valid": False,
            "expected": expected,
            "blocked_reason": BLOCKED_SERVER_BROWSER_LAUNCH,
        }

    return {"valid": True, "expected": expected, "declared": declared or expected}


def build_local_agent_handoff(task: dict[str, Any]) -> dict[str, Any]:
    """서버에서 외부 URL task를 받았을 때 local agent handoff payload 생성."""
    target_url = task.get("target_url", "") or task.get("url", "")
    host = _extract_host(target_url)
    action = task.get("action", "")
    task_id = task.get("task_id", "")

    handoff = {
        "task_id": task_id,
        "execution_location": LOCAL_AGENT_REQUIRED,
        "target_url": target_url,
        "target_host": host,
        "action": action,
        "status": "WAITING_LOCAL_AGENT",
        "message_ko": "외부 웹사이트 작업은 사용자 PC 로컬 에이전트에서 실행해야 합니다.",
        "local_agent_required": True,
    }
    for f in _SAFE_FIELDS:
        handoff[f] = False
    return handoff


def _result(execution_location: str, reason: str, blocked: bool, target_host: str = "") -> dict[str, Any]:
    r: dict[str, Any] = {
        "execution_location": execution_location,
        "reason": reason,
        "blocked": blocked,
    }
    if target_host:
        r["target_host"] = target_host
    if blocked:
        r["blocked_reason"] = BLOCKED_UNSAFE_EXECUTION_LOCATION
    for f in _SAFE_FIELDS:
        r[f] = False
    return r
