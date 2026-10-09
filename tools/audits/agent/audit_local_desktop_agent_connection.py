"""LOCAL-DESKTOP-AGENT-CONNECTION-REPAIR-01 audit.

서버 ↔ 로컬 에이전트 연결 흐름의 핵심 가용성 + 정책 준수 자기검증.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field


@dataclass
class ConnectionVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


# 핵심 서버 모듈/심볼
_SERVER_REQUIRED = [
    ("ai_orchestrator.agent_hub.router.root", "local_agent_router"),
    # 라우터 분할 후 등록 핸들러는 registration leaf 모듈에 있다(local_agent_router 는 조립만 함)
    ("ai_orchestrator.agent_hub.router.registration", "register_local_agent"),
    ("ai_orchestrator.agent_hub.router.registration", "register_with_code"),
    ("ai_orchestrator.agent_hub.registry.facade", "register_agent"),
    ("ai_orchestrator.agent_hub.registry.facade", "authenticate_agent"),
    ("ai_orchestrator.agent_hub.registry.facade", "set_agent_connected"),
    ("ai_orchestrator.agent_hub.registry.facade", "set_agent_last_seen"),
    ("ai_orchestrator.agent_hub.registry.facade", "set_agent_disconnected"),
    ("ai_orchestrator.agent_hub.registry.facade", "get_agent_status"),
    ("ai_orchestrator.auth.registration_codes", "issue_code"),
    ("ai_orchestrator.auth.registration_codes", "consume_code"),
]

# 클라이언트 모듈
_CLIENT_REQUIRED = [
    ("core.agent_runtime.connection.websocket_client", "run_forever"),
    ("core.agent_runtime.connection.registration_client", "register_with_code"),
    ("core.agent_runtime.connection.connection_diagnostics", "build_diagnostics"),
    ("core.agent_runtime.connection.connection_diagnostics", "normalize_ws_url"),
    ("core.agent_runtime.connection.connection_diagnostics", "explain_error"),
]


def _resolve(modname: str, sym: str):
    try:
        m = importlib.import_module(modname)
        return getattr(m, sym, None)
    except Exception:  # noqa: BLE001 - 서버↔로컬 에이전트 연결 자기검증 — _resolve 는 심볼 import 실패 시 None 을 반환하고, 호출부(judge_connection)는 None 을 '심볼 누락'으로 간주해 FAIL 판정하는 fail-closed 헬퍼.
        return None


def _check_token_leak(token_leak_detected: bool, metrics: dict) -> ConnectionVerdict | None:
    if token_leak_detected:
        return ConnectionVerdict(
            False, "FAIL_DEVICE_TOKEN_LEAK", reasons=["device_token surface detected"], metrics=metrics
        )
    return None


def _check_server_symbols(metrics: dict) -> ConnectionVerdict | None:
    # 서버 심볼 누락 → FAIL_REGISTRATION_FLOW_BROKEN
    missing_server = [f"{m}.{s}" for m, s in _SERVER_REQUIRED if _resolve(m, s) is None]
    if missing_server:
        return ConnectionVerdict(
            False,
            "FAIL_REGISTRATION_FLOW_BROKEN",
            reasons=[f"missing_server_symbols:{missing_server[:5]}"],
            metrics=metrics,
        )
    return None


def _check_client_symbols(metrics: dict) -> ConnectionVerdict | None:
    missing_client = [f"{m}.{s}" for m, s in _CLIENT_REQUIRED if _resolve(m, s) is None]
    if missing_client:
        return ConnectionVerdict(
            False,
            "FAIL_WS_AUTH_BROKEN",
            reasons=[f"missing_client_symbols:{missing_client[:5]}"],
            metrics=metrics,
        )
    return None


def _check_e2e_results(e2e: dict, metrics: dict) -> ConnectionVerdict | None:
    if e2e.get("register_ok") is False:
        return ConnectionVerdict(False, "FAIL_REGISTRATION_FLOW_BROKEN", reasons=["register_ok=False"], metrics=metrics)
    if e2e.get("auth_ok") is False:
        return ConnectionVerdict(False, "FAIL_WS_AUTH_BROKEN", reasons=["auth_ok=False"], metrics=metrics)
    if e2e.get("heartbeat_ok") is False:
        return ConnectionVerdict(False, "FAIL_HEARTBEAT_BROKEN", reasons=["heartbeat_ok=False"], metrics=metrics)
    if e2e.get("reconnect_ok") is False:
        return ConnectionVerdict(False, "FAIL_RECONNECT_BROKEN", reasons=["reconnect_ok=False"], metrics=metrics)
    return None


def _check_warnings(
    e2e: dict, desktop_client_detected: bool, proxy_doc_present: bool, metrics: dict
) -> ConnectionVerdict | None:
    if not desktop_client_detected:
        return ConnectionVerdict(
            False, "WARN_DESKTOP_CLIENT_NOT_FOUND", reasons=["desktop installer code not located"], metrics=metrics
        )
    if not proxy_doc_present:
        return ConnectionVerdict(
            False, "WARN_PROXY_CONFIG_UNVERIFIED", reasons=["nginx/proxy checklist 미작성"], metrics=metrics
        )
    if e2e.get("register_ok") is None or e2e.get("auth_ok") is None or e2e.get("heartbeat_ok") is None:
        return ConnectionVerdict(
            False, "WARN_INSTALLER_FLOW_INCOMPLETE", reasons=["e2e results partial"], metrics=metrics
        )
    return None


def judge_connection(
    *,
    e2e_results: dict | None = None,  # {register_ok, auth_ok, heartbeat_ok, bad_token_4401, reconnect_ok, ...}
    token_leak_detected: bool = False,
    proxy_doc_present: bool = False,
    desktop_client_detected: bool = True,
) -> ConnectionVerdict:
    # 2026-09-29 STD-08(복잡도) 리팩터: 각 FAIL/WARN 게이트를 _check_*(...) -> Verdict|None
    # 함수로 분리 — 첫 실패에서 즉시 반환하는 원본 의미론 그대로(#64 와 동일 패턴).
    e2e = dict(e2e_results or {})
    metrics = {
        "e2e": e2e,
        "token_leak_detected": token_leak_detected,
        "proxy_doc_present": proxy_doc_present,
        "desktop_client_detected": desktop_client_detected,
    }

    result = _check_token_leak(token_leak_detected, metrics)
    if result:
        return result
    result = _check_server_symbols(metrics)
    if result:
        return result
    result = _check_client_symbols(metrics)
    if result:
        return result
    result = _check_e2e_results(e2e, metrics)
    if result:
        return result
    result = _check_warnings(e2e, desktop_client_detected, proxy_doc_present, metrics)
    if result:
        return result

    return ConnectionVerdict(True, "PASS_LOCAL_DESKTOP_AGENT_CONNECTION_REPAIR", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("e2e_json", type=Path, nargs="?")
    args = ap.parse_args(argv)
    e2e = {}
    if args.e2e_json and args.e2e_json.exists():
        e2e = json.loads(args.e2e_json.read_text(encoding="utf-8"))
    v = judge_connection(
        e2e_results=e2e,
        proxy_doc_present=Path("docs/ops/local_agent_proxy_checklist.md").exists(),
    )
    print(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
