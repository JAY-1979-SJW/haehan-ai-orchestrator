"""HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01 회귀 테스트."""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from desktop import main_launcher as ml  # noqa: E402


# ── import / 구조 ────────────────────────────────────────────────────────

def test_module_importable():
    assert ml is not None
    assert hasattr(ml, "__version__")


def test_version_string():
    assert isinstance(ml.__version__, str)
    assert len(ml.__version__) > 0


def test_app_mode_enum():
    for m in ["TRAY", "ADMIN", "DIAGNOSTICS", "VERSION", "RESET_LOCK"]:
        assert hasattr(ml.AppMode, m), f"AppMode.{m} 누락"


# ── CLI mode 분기 ────────────────────────────────────────────────────────

def test_default_mode_is_tray():
    assert ml.parse_mode([]) == ml.AppMode.TRAY


def test_tray_flag():
    assert ml.parse_mode(["--tray"]) == ml.AppMode.TRAY


def test_admin_flag():
    assert ml.parse_mode(["--admin"]) == ml.AppMode.ADMIN


def test_diagnostics_flag():
    assert ml.parse_mode(["--diagnostics"]) == ml.AppMode.DIAGNOSTICS


def test_version_flag():
    assert ml.parse_mode(["--version"]) == ml.AppMode.VERSION


def test_reset_lock_flag():
    assert ml.parse_mode(["--reset-lock"]) == ml.AppMode.RESET_LOCK


def test_mutually_exclusive_modes():
    """--tray와 --admin은 동시 불가."""
    with pytest.raises(SystemExit):
        ml.parse_mode(["--tray", "--admin"])


# ── 경로 ──────────────────────────────────────────────────────────────────

def test_app_root_exists():
    assert ml.app_root().exists()


def test_user_data_dir_has_haehan():
    p = ml.user_data_dir()
    assert "HaehanAI" in str(p)
    assert p.exists()


def test_lock_path_in_user_data():
    lp = ml.lock_path()
    assert "HaehanAI" in str(lp)
    assert lp.name == "app.lock"


def test_log_dir_writable():
    d = ml.log_dir()
    assert d.exists()


# ── 락 ────────────────────────────────────────────────────────────────────

def _clear_lock():
    p = ml.lock_path()
    p.unlink(missing_ok=True)


def test_acquire_lock_clean():
    _clear_lock()
    state = ml.acquire_lock()
    try:
        assert state.acquired is True
        assert state.pid == os.getpid()
        assert state.stale is False
    finally:
        ml.release_lock()


def test_stale_lock_auto_cleanup():
    _clear_lock()
    # 거의 확실히 죽은 PID 기록
    ml.lock_path().write_text(
        json.dumps({"pid": 9999999, "started_at": "2020-01-01"}),
        encoding="utf-8",
    )
    state = ml.acquire_lock()
    try:
        assert state.acquired is True
        assert state.stale is True
    finally:
        ml.release_lock()


def test_live_lock_preservation():
    _clear_lock()
    # 본 프로세스 PID 기록 — 살아있음
    ml.lock_path().write_text(
        json.dumps({"pid": os.getpid(), "started_at": "now"}),
        encoding="utf-8",
    )
    try:
        state = ml.acquire_lock()
        # 살아있는 PID이므로 락 획득 실패해야 함
        assert state.acquired is False
        assert state.pid == os.getpid()
        assert state.stale is False
    finally:
        _clear_lock()


def test_reset_lock_force():
    _clear_lock()
    ml.lock_path().write_text(
        json.dumps({"pid": os.getpid()}), encoding="utf-8"
    )
    r = ml.reset_lock()
    assert r.get("ok") is True
    assert not ml.lock_path().exists()


def test_reset_lock_no_existing():
    _clear_lock()
    r = ml.reset_lock()
    assert r.get("ok") is True
    assert r.get("existed") is False


def test_release_lock_only_own():
    """본 프로세스가 소유하지 않은 락은 release_lock으로 제거되지 않아야 함."""
    _clear_lock()
    other_pid = 9999998
    ml.lock_path().write_text(
        json.dumps({"pid": other_pid}), encoding="utf-8"
    )
    ml.release_lock()  # 본 PID 아니므로 무시
    assert ml.lock_path().exists()
    _clear_lock()


def test_pid_alive_self():
    assert ml._pid_alive(os.getpid()) is True


def test_pid_alive_dead():
    assert ml._pid_alive(9999999) is False


def test_pid_alive_invalid():
    assert ml._pid_alive(0) is False
    assert ml._pid_alive(-1) is False


# ── lock 파일 secret 없음 ───────────────────────────────────────────────

def test_lock_file_no_secret():
    _clear_lock()
    state = ml.acquire_lock()
    try:
        content = ml.lock_path().read_text(encoding="utf-8")
        forbidden = ["device_token", "registration_code", "sk-", "openai_api_key", "bearer"]
        for kw in forbidden:
            assert kw.lower() not in content.lower(), f"lock 파일에 {kw} 노출"
    finally:
        ml.release_lock()


# ── lifecycle hooks ──────────────────────────────────────────────────────

def test_check_consent_hook_returns_dict():
    r = ml.check_consent_hook()
    assert isinstance(r, dict)
    assert "agreed" in r
    assert "needs_prompt" in r


def test_load_token_status_hook_no_token_value():
    r = ml.load_token_status_hook()
    assert isinstance(r, dict)
    assert "present" in r
    # 절대 원문 또는 해시가 들어있으면 안 됨
    assert "token" not in r or r["token"] is None or r["token"] == ""
    assert "value" not in r


def test_role_check_hook_admin_deferred():
    r = ml.role_check_hook(ml.AppMode.ADMIN)
    assert r.get("required") is True
    assert r.get("deferred") is True


def test_role_check_hook_tray_not_required():
    r = ml.role_check_hook(ml.AppMode.TRAY)
    assert r.get("required") is False
    assert r.get("passed") is True


def test_start_local_server_hook_deferred():
    r = ml.start_local_server_hook()
    assert r.get("deferred") is True


def test_start_tray_hook_deferred():
    r = ml.start_tray_hook()
    assert r.get("deferred") is True


def test_start_admin_webview_hook_deferred():
    r = ml.start_admin_webview_hook()
    assert r.get("deferred") is True


def test_graceful_shutdown_hook():
    r = ml.graceful_shutdown_hook()
    assert r.get("shutdown") is True


# ── diagnostics ──────────────────────────────────────────────────────────

def test_build_diagnostics_dict():
    d = ml.build_diagnostics()
    assert d["app"] == "HaehanAI"
    assert d["version"] == ml.__version__
    assert "lock" in d
    assert "consent" in d
    assert "token" in d
    assert "role" in d
    assert d["agent_id_masked"]  # 빈 문자열도 안 됨, 최소 "—"


def test_diagnostics_token_value_not_present():
    d = ml.build_diagnostics()
    # token 섹션에 원문/해시 절대 금지
    assert "value" not in d["token"]
    assert "raw" not in d["token"]
    assert "hash" not in d["token"]


def test_print_diagnostics_redacted():
    buf = io.StringIO()
    with redirect_stdout(buf):
        ml.print_diagnostics(ml.AppMode.DIAGNOSTICS)
    output = buf.getvalue()
    # 실제 secret 패턴 없어야 함
    for pat in ["sk-proj-", "sk-ant-", "Bearer eyJ"]:
        assert pat not in output


def test_diagnostics_agent_id_masked():
    masked = ml.mask_agent_id("la-1234567890abcdef")
    assert "***" in masked
    assert "1234567890abcdef" not in masked


def test_diagnostics_agent_id_short():
    assert ml.mask_agent_id("") == "—"
    assert ml.mask_agent_id("la") == "—"


def test_redact_function():
    assert "[REDACTED]" in ml._redact("device_token=abc123def456")
    assert "[REDACTED]" in ml._redact("registration_code=xyz789")
    assert "[REDACTED_API_KEY]" in ml._redact("API key: sk-proj-abc12345xyz")
    assert "abc123def456" not in ml._redact("device_token=abc123def456")


# ── 기존 entrypoint 회귀 ────────────────────────────────────────────────

def test_consent_module_importable():
    """desktop.consent 공유 모듈 (legacy UI 제거 후 webview_app_pywebview에서 이전)."""
    import importlib
    mod = importlib.import_module("desktop.consent")
    assert mod is not None
    assert hasattr(mod, "check_consent")


def test_existing_local_agent_launcher_importable():
    """기존 local_agent/desktop_launcher 깨지지 않았는지."""
    import importlib
    mod = importlib.import_module("local_agent.desktop_launcher")
    assert mod is not None


def test_existing_local_server_importable():
    import importlib
    mod = importlib.import_module("desktop.local_server")
    assert mod is not None


def test_existing_local_agent_init_importable():
    import importlib
    mod = importlib.import_module("local_agent")
    assert mod is not None


# ── main() ────────────────────────────────────────────────────────────────

def test_main_version_zero_exit():
    rc = ml.main(["--version"])
    assert rc == 0


def test_main_reset_lock_zero_exit():
    rc = ml.main(["--reset-lock"])
    assert rc == 0


def test_main_diagnostics_zero_exit():
    rc = ml.main(["--diagnostics"])
    assert rc == 0


# ── 소스 자체 secret 없음 ────────────────────────────────────────────────

def test_launcher_source_no_secret():
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    forbidden = ["sk-proj-", "sk-ant-", "Bearer eyJ"]
    for pat in forbidden:
        assert pat not in src, f"launcher 소스에 {pat}"


def test_launcher_source_has_no_real_token():
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    # device_token 값 패턴 (실제 토큰처럼 보이는 긴 문자열)
    import re
    # device_token = "어떤_긴_문자열"
    matches = re.findall(r'device_token\s*=\s*[\'"][a-zA-Z0-9_-]{20,}[\'"]', src)
    assert not matches


# ── local-only bypass 금지 명시 ──────────────────────────────────────────

def test_local_only_bypass_forbidden_doc():
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    assert "local-only bypass" in src or "bypass 금지" in src


# ── 후속 공정 deferred 표시 ──────────────────────────────────────────────

def test_tray_implementation_deferred():
    r = ml.start_tray_hook()
    assert "pending" in r.get("reason", "").lower() or r.get("deferred")


def test_admin_webview_implementation_deferred():
    r = ml.start_admin_webview_hook()
    assert "pending" in r.get("reason", "").lower() or r.get("deferred")


def test_server_implementation_deferred():
    r = ml.start_local_server_hook()
    assert r.get("deferred")
    assert r.get("port") == 8765
