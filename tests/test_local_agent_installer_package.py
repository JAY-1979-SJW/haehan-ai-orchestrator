"""LOCAL_AGENT_INSTALLER_PACKAGE_01 — 14+ 테스트."""
from __future__ import annotations

import os
import json
from pathlib import Path
from unittest import mock

import pytest


# ── 1) entrypoint 존재 ──────────────────────────────────────────────


def test_entrypoint_module_imports():
    from local_agent import desktop_launcher
    assert hasattr(desktop_launcher, "main")
    assert hasattr(desktop_launcher, "self_test")
    assert hasattr(desktop_launcher, "register_flow")
    assert hasattr(desktop_launcher, "connect_flow")
    assert hasattr(desktop_launcher, "show_diagnostics")


def test_entrypoint_main_callable():
    from local_agent import desktop_launcher
    assert callable(desktop_launcher.main)


# ── 2) build script 존재 ───────────────────────────────────────────


def test_build_script_exists():
    p = Path("scripts/build_desktop_agent_windows.py")
    assert p.exists()


def test_build_script_imports():
    from scripts import build_desktop_agent_windows as b
    assert hasattr(b, "build")
    assert hasattr(b, "main")


# ── 3) doc 존재 ────────────────────────────────────────────────────


def test_doc_exists():
    p = Path("docs/ops/local_agent_installer_package.md")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    for keyword in ("PyInstaller", "registration_code", "device_token",
                    "keyring", "self-test", "diagnostics", "AUTH_FAILED_4401"):
        assert keyword in text, f"missing in doc: {keyword}"


# ── 4) config path 테스트 ──────────────────────────────────────────


def test_token_store_describe_backend():
    from local_agent import token_store as ts
    available, name = ts.describe_backend()
    assert isinstance(available, bool)
    assert isinstance(name, str)


def test_token_save_load_roundtrip(tmp_path, monkeypatch):
    from local_agent import token_store as ts
    monkeypatch.setenv("HAEHAN_AGENT_TOKEN_DIR", str(tmp_path))
    # plaintext fallback 강제 (keyring 없는 테스트 환경)
    ts.save_device_token(server_url="https://x.example", agent_id="la-test",
                         token="tok_secret_value",
                         allow_plaintext_fallback=True)
    loaded = ts.load_device_token(server_url="https://x.example",
                                   agent_id="la-test",
                                   allow_plaintext_fallback=True)
    assert loaded == "tok_secret_value"
    # delete
    ts.delete_device_token(server_url="https://x.example",
                            agent_id="la-test",
                            allow_plaintext_fallback=True)
    assert ts.load_device_token(server_url="https://x.example",
                                 agent_id="la-test",
                                 allow_plaintext_fallback=True) is None


# ── 5) token leak 방지 ────────────────────────────────────────────


def test_doc_has_no_real_token_values():
    text = Path("docs/ops/local_agent_installer_package.md").read_text(encoding="utf-8")
    # 'device_token' 키워드는 있어도 됨. 다만 raw 값은 없어야.
    import re
    # "device_token": "..." 형태의 long token 값이 없어야
    matches = re.findall(r'"device_token"\s*:\s*"([^"]{8,})"', text)
    # 예시로 short placeholder ('...', '<token>' 등) 만 허용
    real_token_like = [m for m in matches if len(m) >= 20 and "<" not in m
                       and m not in ("AUTH_FAILED_4401",)]
    assert real_token_like == []


def test_token_store_module_does_not_log_raw_token():
    """token_store.py 소스에 token 변수 (token, device_token) 값을 직접
    로깅하는 호출이 없는지. '평문 fallback' 같은 키워드 언급은 허용."""
    src = Path("local_agent/token_store.py").read_text(encoding="utf-8")
    import re
    # logger.X(...token_var_name...) 형태로 변수가 인자로 들어가는 패턴 (위험)
    # 예: logger.info("got %s", token)  ← 위험
    bad = re.findall(
        r'log(?:ger)?\.(info|debug|warning|error)\([^)]*%[sr][^)]*,\s*token\b',
        src,
    )
    assert bad == [], f"token value possibly logged: {bad}"


# ── 6) ws URL normalize ─────────────────────────────────────────


def test_ws_url_normalize_with_orchestrator_prefix():
    from local_agent.connection_diagnostics import normalize_ws_url
    assert normalize_ws_url("https://haehan-ai.kr/orchestrator") == \
           "wss://haehan-ai.kr/orchestrator/api/v1/local-agents/ws"


def test_ws_url_normalize_without_orchestrator():
    from local_agent.connection_diagnostics import normalize_ws_url
    assert normalize_ws_url("https://api.example.com") == \
           "wss://api.example.com/api/v1/local-agents/ws"


# ── 7) diagnostics message ─────────────────────────────────────


def test_diagnostics_block_includes_state_and_no_leak():
    from local_agent import connection_diagnostics as cd
    d = cd.build_diagnostics(
        server_base_url="https://haehan-ai.kr/orchestrator?device_token=SECRET",
        agent_id="la-abc123def456",
        state=cd.STATE_AUTH_FAILED,
        last_error_code="AUTH_FAILED_4401",
    )
    block = cd.render_user_block(d)
    assert "AUTH_FAILED" in block
    assert "AUTH_FAILED_4401" in block
    assert "재등록" in block
    assert "SECRET" not in block
    assert "la-abc***f456" in block
    assert "abc123def456" not in block


# ── 8) bad token 사용자 안내 ──────────────────────────────────


def test_explain_error_auth_failed_includes_action():
    from local_agent.connection_diagnostics import explain_error
    msg = explain_error("AUTH_FAILED_4401")
    assert "4401" in msg
    assert "재등록" in msg


# ── 9) self_test 실행 ────────────────────────────────────────


def test_self_test_runs_and_reports_ok():
    from local_agent import desktop_launcher
    r = desktop_launcher.self_test()
    # 핵심 import 체크 모두 ok
    for key in ("local_agent.token_store",
                "local_agent.registration_client",
                "local_agent.connection_diagnostics"):
        assert r["checks"][key] == "ok", f"{key}={r['checks'][key]}"
    # diagnostics render 누수 없음
    assert r["checks"]["diagnostics_render_leaks"] == []


# ── 10) connect_flow 토큰 없으면 안내 ─────────────────────────


def test_connect_flow_without_token_returns_2(monkeypatch, capsys, tmp_path):
    from local_agent import desktop_launcher
    from local_agent import token_store as ts
    monkeypatch.setenv("HAEHAN_AGENT_TOKEN_DIR", str(tmp_path))
    # 보장: 저장된 토큰 없음
    rc = desktop_launcher.connect_flow(
        server_url="https://haehan-ai.kr/orchestrator",
        agent_id="la-no-token",
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "TOKEN_NOT_STORED" in captured.out or "재등록" in captured.out


# ── 11) audit verdict ───────────────────────────────────────


def test_audit_pass_or_warn_unsigned():
    from scripts.ops import audit_local_agent_installer_package as audit
    v = audit.judge_package(run_self_test=True)
    # PyInstaller 미설치 → WARN_ONE_FILE_NOT_BUILT 또는 WARN_UNSIGNED_BINARY
    # 모두 spec 허용 WARN
    assert v.code in (
        "PASS_LOCAL_AGENT_INSTALLER_PACKAGE",
        "WARN_ONE_FILE_NOT_BUILT",
        "WARN_UNSIGNED_BINARY",
    ), v.reasons


def test_audit_fail_entrypoint_missing(monkeypatch):
    from scripts.ops import audit_local_agent_installer_package as audit
    # main 심볼 사라진 척
    monkeypatch.setattr(audit, "_resolve_symbol",
                        lambda m, s: None if s == "main" else (lambda: None))
    v = audit.judge_package(run_self_test=False)
    assert v.code == "FAIL_ENTRYPOINT_MISSING"


# ── 12) 회귀 가드 ───────────────────────────────────────────


def test_regression_connection_diagnostics_intact():
    from local_agent import connection_diagnostics as cd
    assert hasattr(cd, "normalize_ws_url")
    assert hasattr(cd, "build_diagnostics")
    assert hasattr(cd, "explain_error")
    assert hasattr(cd, "mask_agent_id")
    assert hasattr(cd, "find_token_leaks")


def test_regression_token_store_api_intact():
    from local_agent import token_store as ts
    for sym in ("save_device_token", "load_device_token",
                "delete_device_token", "has_device_token",
                "describe_backend", "keyring_available"):
        assert hasattr(ts, sym), f"missing: {sym}"


def test_regression_registration_client_intact():
    from local_agent import registration_client as rc
    assert hasattr(rc, "register_with_code")
    assert hasattr(rc, "RegistrationError")


def test_regression_websocket_client_intact():
    from local_agent import websocket_client
    assert hasattr(websocket_client, "connect")
    assert hasattr(websocket_client, "run_forever")


# ── 13) CLI 옵션 ───────────────────────────────────────────


def test_main_self_test_returns_zero(monkeypatch, capsys):
    from local_agent import desktop_launcher
    rc = desktop_launcher.main(["--self-test"])
    assert rc == 0


def test_main_diagnostics_returns_zero(monkeypatch, capsys):
    from local_agent import desktop_launcher
    rc = desktop_launcher.main(["--diagnostics",
                                 "--server", "https://haehan-ai.kr/orchestrator"])
    assert rc == 0


def test_main_register_requires_env(monkeypatch, capsys):
    from local_agent import desktop_launcher
    monkeypatch.delenv("HAEHAN_AGENT_CODE", raising=False)
    rc = desktop_launcher.main(["--register",
                                 "--server", "https://haehan-ai.kr/orchestrator"])
    assert rc == 2


def test_main_default_requires_agent_id(monkeypatch, capsys):
    from local_agent import desktop_launcher
    rc = desktop_launcher.main(["--server", "https://haehan-ai.kr/orchestrator"])
    assert rc == 2
