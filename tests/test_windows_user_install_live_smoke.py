"""WINDOWS_USER_INSTALL_LIVE_SMOKE_01 — 12+ 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


USER_DOC = Path("docs/ops/local_agent_user_install_smoke.md")


# ── 1) 사용자 문서 ──────────────────────────────────────────────


def test_user_doc_exists():
    assert USER_DOC.exists()


def test_user_doc_has_install_section():
    text = USER_DOC.read_text(encoding="utf-8")
    for keyword in ("설치", "압축 해제", "환경 변수",
                    "registration_code", "--register",
                    "--diagnostics", "--self-test", "--agent-id",
                    "--reset", "Credential Manager", "SmartScreen",
                    "AUTH_FAILED_4401", "TOKEN_NOT_STORED"):
        assert keyword in text, f"missing: {keyword}"


def test_user_doc_has_error_code_table():
    text = USER_DOC.read_text(encoding="utf-8")
    for code in ("AUTH_FAILED_4401", "REG_CODE_EXPIRED",
                 "REG_CODE_INVALID", "REG_CODE_ALREADY_USED",
                 "SERVER_NOT_REACHABLE", "NETWORK_BLOCKED_PROXY",
                 "HEARTBEAT_LOST", "TOKEN_NOT_STORED"):
        assert code in text, f"error code not documented: {code}"


def test_user_doc_no_real_token_values():
    text = USER_DOC.read_text(encoding="utf-8")
    import re
    # raw long token-like values in quotes shouldn't exist
    matches = re.findall(r'"device_token"\s*:\s*"([^"]{20,})"', text)
    real = [m for m in matches if "<" not in m]
    assert real == [], f"raw token in doc: {real}"


# ── 2) audit ───────────────────────────────────────────────


def test_audit_module_imports():
    from scripts.ops import audit_windows_user_install_live_smoke as a
    assert hasattr(a, "judge_user_install")


def test_audit_fail_user_doc_missing(tmp_path, monkeypatch):
    from scripts.ops import audit_windows_user_install_live_smoke as a
    monkeypatch.setattr(a, "USER_DOC", tmp_path / "missing.md")
    v = a.judge_user_install()
    assert v.code == "FAIL_USER_DOC_MISSING"


def test_audit_fail_register_failed():
    from scripts.ops import audit_windows_user_install_live_smoke as a
    smoke = {"register_ok": False, "register_error": "401"}
    v = a.judge_user_install(smoke_results=smoke)
    assert v.code == "FAIL_REGISTER_FAILED"


def test_audit_fail_token_store_failed():
    from scripts.ops import audit_windows_user_install_live_smoke as a
    smoke = {"register_ok": True, "token_store_ok": False}
    v = a.judge_user_install(smoke_results=smoke)
    assert v.code == "FAIL_TOKEN_STORE_FAILED"


def test_audit_fail_wss_auth_failed():
    from scripts.ops import audit_windows_user_install_live_smoke as a
    smoke = {"register_ok": True, "token_store_ok": True,
             "wss_auth_ok": False}
    v = a.judge_user_install(smoke_results=smoke)
    assert v.code == "FAIL_WSS_AUTH_FAILED"


def test_audit_fail_heartbeat_failed():
    from scripts.ops import audit_windows_user_install_live_smoke as a
    smoke = {"register_ok": True, "token_store_ok": True,
             "wss_auth_ok": True, "heartbeat_ok": False}
    v = a.judge_user_install(smoke_results=smoke)
    assert v.code == "FAIL_HEARTBEAT_FAILED"


def test_audit_fail_token_leak_in_doc(tmp_path, monkeypatch):
    """문서에 token raw 값이 들어가면 FAIL."""
    from scripts.ops import audit_windows_user_install_live_smoke as a
    p = tmp_path / "doc.md"
    p.write_text(
        "## 설치\n압축 해제\n환경 변수\nregistration_code 사용 재등록\n"
        "--register --diagnostics --self-test --agent-id --reset\n"
        "Credential Manager / SmartScreen\n오류: AUTH_FAILED_4401 TOKEN_NOT_STORED 등록 재실행\n진단\n"
        '"device_token": "REAL_TOKEN_VALUE_LEAKED_8plus"\n',
        encoding="utf-8")
    monkeypatch.setattr(a, "USER_DOC", p)
    v = a.judge_user_install(smoke_results={"register_ok": True,
                                              "token_store_ok": True,
                                              "wss_auth_ok": True,
                                              "heartbeat_ok": True})
    assert v.code == "FAIL_TOKEN_LEAK"


def test_audit_warn_same_machine_test():
    from scripts.ops import audit_windows_user_install_live_smoke as a
    smoke = {"register_ok": True, "token_store_ok": True,
             "wss_auth_ok": True, "heartbeat_ok": True}
    v = a.judge_user_install(smoke_results=smoke, same_machine_test=True)
    assert v.code == "WARN_SAME_MACHINE_TEST_ONLY"


def test_audit_warn_unsigned_binary_on_clean_machine():
    from scripts.ops import audit_windows_user_install_live_smoke as a
    smoke = {"register_ok": True, "token_store_ok": True,
             "wss_auth_ok": True, "heartbeat_ok": True}
    v = a.judge_user_install(smoke_results=smoke, same_machine_test=False)
    assert v.code == "WARN_UNSIGNED_BINARY"


# ── 3) 회귀 가드 ───────────────────────────────────────────


def test_regression_pyinstaller_audit_imports():
    from scripts.ops import audit_pyinstaller_build_exec as a
    assert hasattr(a, "judge_build_exec")


def test_regression_installer_package_audit_imports():
    from scripts.ops import audit_local_agent_installer_package as a
    assert hasattr(a, "judge_package")


def test_regression_desktop_launcher_intact():
    from local_agent import desktop_launcher
    for sym in ("main", "self_test", "register_flow", "connect_flow"):
        assert hasattr(desktop_launcher, sym)
