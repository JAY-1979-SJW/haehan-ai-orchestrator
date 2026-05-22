"""신규 Desktop Shell — 상태 대시보드 (Phase 1: 조회 전용).

실행/승인/CAD start/stop 버튼은 Phase 2 smoke 이후 연결.
이번 Phase는 API 호출 골조만.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from .api import url


def _get(key: str, timeout: int = 3) -> dict[str, Any]:
    try:
        req = urllib.request.urlopen(url(key), timeout=timeout)
        return json.loads(req.read())
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e), "_unreachable": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fetch_status() -> dict[str, Any]:
    """로컬 서버 상태 전체 조회. 모든 값은 읽기 전용."""
    health      = _get("health")
    agent       = _get("agent_status")
    la_health   = _get("la_health")
    la_preflight = _get("la_preflight")

    server_alive = health.get("ok", False) and not health.get("_unreachable")

    return {
        "server_alive":     server_alive,
        "server_connected": agent.get("server_connected", False),
        "agent_id":         agent.get("agent_id", ""),
        "role":             None,  # whoami는 별도 호출
        "la_available":     la_health.get("available", False),
        "can_run":          la_preflight.get("can_run", False),
        "user_message":     la_preflight.get("user_message", ""),
        "next_actions":     la_preflight.get("next_actions", []),
        "_raw": {
            "health":       health,
            "agent":        agent,
            "la_health":    la_health,
            "la_preflight": la_preflight,
        },
    }


def fetch_logs(n: int = 20) -> list[str]:
    data = _get("logs")
    return data.get("lines", [])[-n:]


def print_dashboard() -> None:
    """CLI 형태로 현재 상태 출력."""
    st = fetch_status()
    logs = fetch_logs()

    print("\n해한 AI 데스크톱 — 상태\n" + "─" * 40)
    print(f"  로컬 서버:   {'정상' if st['server_alive'] else '미연결'}")
    print(f"  서버 연결:   {'정상' if st['server_connected'] else '미연결'}")
    print(f"  Agent ID:    {st['agent_id'] or '(미등록)'}")
    print(f"  AI 가용:     {'가능' if st['la_available'] else '불가'}")
    print(f"  실행 가능:   {'예' if st['can_run'] else '아니오'}")
    if st["user_message"]:
        print(f"  안내:        {st['user_message']}")
    if st["next_actions"]:
        for act in st["next_actions"]:
            print(f"  조치:        {act}")

    if logs:
        print("\n최근 로그")
        for line in logs:
            print(f"  {line}")
    print("─" * 40)


if __name__ == "__main__":
    print_dashboard()
