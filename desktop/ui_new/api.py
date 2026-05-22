"""신규 Desktop Shell — API 호출 레지스트리.

새 shell은 이 모듈의 상수만 사용하여 endpoint를 참조한다.
endpoint 이름을 직접 하드코딩하지 않는다.
"""
from __future__ import annotations

BASE_URL = "http://127.0.0.1:8765"

ENDPOINTS = {
    "health":           f"{BASE_URL}/health",
    "agent_status":     f"{BASE_URL}/agent/status",
    "agent_register":   f"{BASE_URL}/agent/register",
    "la_health":        f"{BASE_URL}/local-agent/health",
    "la_preflight":     f"{BASE_URL}/local-agent/preflight",
    "la_run":           f"{BASE_URL}/local-agent/run",
    "cad_status":       f"{BASE_URL}/cad/bridge/status",
    "cad_start":        f"{BASE_URL}/cad/bridge/start",
    "cad_stop":         f"{BASE_URL}/cad/bridge/stop",
    "cad_restart":      f"{BASE_URL}/cad/bridge/restart",
    "whoami":           f"{BASE_URL}/api/v1/whoami",
    "logs":             f"{BASE_URL}/logs",
    "ws_ui":            f"ws://127.0.0.1:8765/ws/ui",
}


def url(key: str) -> str:
    """엔드포인트 키로 URL 반환. 없으면 KeyError."""
    return ENDPOINTS[key]
