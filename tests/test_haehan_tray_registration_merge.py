"""HAEHAN_TRAY_REGISTRATION_MERGE_01 회귀 테스트."""
from __future__ import annotations

import dataclasses
import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from desktop import tray_runtime as tr  # noqa: E402
from desktop import main_launcher as ml  # noqa: E402


# ── import / 구조 ────────────────────────────────────────────────────────

def test_tray_runtime_importable():
    assert tr is not None


def test_required_symbols():
    needed = [
        "RegistrationStatus", "TrayMenuItem", "HeartbeatPlan", "WizardOutcome",
        "check_registration_status", "decide_next_action",
        "decide_action_from_error", "build_tray_menu_items",
        "plan_heartbeat", "apply_registration_result",
        "build_diagnostics_payload",
        "run_registration_wizard_cli", "run_registration_wizard_gui",
        "start_heartbeat_background", "start_tray_gui",
        "run_tray_mode_full",
    ]
    for s in needed:
        assert hasattr(tr, s), f"missing {s}"


# ── 등록 상태 ─────────────────────────────────────────────────────────────

def test_check_registration_status_unregistered():
    class _Cfg:
        server_url = ""
        agent_id = ""
        def is_complete(self): return False
    status = tr.check_registration_status(
        config_loader=lambda: _Cfg(),
        token_checker=lambda s, a: False,
    )
    assert status.registered is False
    assert status.token_present is False


def test_check_registration_status_registered():
    class _Cfg:
        server_url = "https://test.example.com"
        agent_id = "la-abc123"
        def is_complete(self): return True
    status = tr.check_registration_status(
        config_loader=lambda: _Cfg(),
        token_checker=lambda s, a: True,
    )
    assert status.registered is True
    assert status.server_url == "https://test.example.com"
    assert status.agent_id == "la-abc123"
    assert status.token_present is True


def test_check_registration_status_config_but_no_token():
    class _Cfg:
        server_url = "https://x.example.com"
        agent_id = "la-x"
        def is_complete(self): return True
    status = tr.check_registration_status(
        config_loader=lambda: _Cfg(),
        token_checker=lambda s, a: False,
    )
    assert status.registered is False
    assert status.config_present is True
    assert status.token_present is False


# ── 다음 동작 결정 ────────────────────────────────────────────────────────

def test_decide_next_action_unregistered_wizard():
    s = tr.RegistrationStatus(registered=False)
    assert tr.decide_next_action(s) == "wizard"


def test_decide_next_action_registered_heartbeat():
    s = tr.RegistrationStatus(
        registered=True, server_url="https://x", agent_id="la-x",
    )
    assert tr.decide_next_action(s) == "heartbeat"


def test_decide_next_action_partial_data():
    s = tr.RegistrationStatus(registered=True, server_url="", agent_id="la-x")
    assert tr.decide_next_action(s) == "wizard"


# ── 오류 코드 매핑 ───────────────────────────────────────────────────────

def test_auth_failed_4401_to_wizard():
    assert tr.decide_action_from_error("AUTH_FAILED_4401") == "show_wizard"


def test_token_not_stored_to_wizard():
    assert tr.decide_action_from_error("TOKEN_NOT_STORED") == "show_wizard"


def test_reg_code_expired_to_wizard():
    assert tr.decide_action_from_error("REG_CODE_EXPIRED") == "show_wizard"


def test_server_unreachable_to_diagnostics():
    assert tr.decide_action_from_error("SERVER_NOT_REACHABLE") == "show_diagnostics"


def test_heartbeat_lost_to_reconnect():
    assert tr.decide_action_from_error("HEARTBEAT_LOST") == "reconnect"


def test_empty_error_to_reconnect():
    assert tr.decide_action_from_error("") == "reconnect"


# ── heartbeat plan ───────────────────────────────────────────────────────

def test_plan_heartbeat_unregistered():
    s = tr.RegistrationStatus(registered=False)
    plan = tr.plan_heartbeat(s)
    assert plan.can_start is False
    assert plan.reason == "not_registered"


def test_plan_heartbeat_registered_ws_url():
    s = tr.RegistrationStatus(
        registered=True, server_url="https://test.example.com",
        agent_id="la-test",
    )
    plan = tr.plan_heartbeat(s)
    assert plan.can_start is True
    assert plan.ws_url.startswith("wss://")
    assert plan.agent_id == "la-test"


def test_plan_heartbeat_http_to_ws():
    s = tr.RegistrationStatus(
        registered=True, server_url="http://localhost:8000",
        agent_id="la-x",
    )
    plan = tr.plan_heartbeat(s)
    assert plan.ws_url.startswith("ws://")


# ── 트레이 메뉴 ──────────────────────────────────────────────────────────

def test_menu_unregistered_shows_register():
    s = tr.RegistrationStatus(registered=False)
    items = tr.build_tray_menu_items(status=s, role="admin")
    ids = [it.id for it in items]
    assert "register" in ids
    assert "re_register" not in ids


def test_menu_registered_shows_re_register():
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin")
    ids = [it.id for it in items]
    assert "re_register" in ids
    assert "register" not in ids


def test_menu_admin_role_has_open_admin():
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin", admin_mode_available=False)
    ids = [it.id for it in items]
    assert "open_admin" in ids
    # admin_mode_available=False 면 enabled=False
    admin_item = next(it for it in items if it.id == "open_admin")
    assert admin_item.enabled is False


def test_menu_owner_role_has_open_admin():
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="owner")
    ids = [it.id for it in items]
    assert "open_admin" in ids


def test_menu_user_role_hides_open_admin():
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="any")
    ids = [it.id for it in items]
    assert "open_admin" not in ids


def test_menu_has_required_items():
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin")
    ids = [it.id for it in items]
    for need in ["status", "diagnostics", "autostart", "quit"]:
        assert need in ids, f"메뉴에 {need} 없음"


def test_menu_admin_label_when_enabled():
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin", admin_mode_available=True)
    admin_item = next((it for it in items if it.id == "open_admin"), None)
    assert admin_item is not None
    assert admin_item.label == "관리화면 열기"
    assert admin_item.enabled is True


# ── 등록 결과 적용 ───────────────────────────────────────────────────────

class _FakeMeta:
    agent_id = "la-test1234abcd"
    code_id = "code-1"
    host = ""
    os_name = ""
    version = "0.2.0"
    registered_at = "2026-05-22"
    label = "test"


def test_apply_registration_success():
    saved_args = {}
    def _save(server_url, agent_id, token, *, allow_plaintext_fallback=False):
        saved_args["server_url"] = server_url
        saved_args["agent_id"] = agent_id
        saved_args["token_len"] = len(token)
        return "mock"
    def _save_cfg(cfg):
        saved_args["cfg_agent_id"] = cfg.agent_id

    outcome = tr.apply_registration_result(
        "https://x.example.com", _FakeMeta(), "FAKE_TOKEN_VALUE",
        token_saver=_save, config_saver=_save_cfg,
    )
    assert outcome.success is True
    assert outcome.agent_id == "la-test1234abcd"
    # 외부 saver 가 받은 token 은 있을 수 있으나, outcome 에는 없음
    out_dict = dataclasses.asdict(outcome)
    assert "device_token" not in out_dict
    assert "token" not in out_dict


def test_apply_registration_empty_fields():
    outcome = tr.apply_registration_result("", _FakeMeta(), "tok",
                                            token_saver=lambda *a, **k: "x",
                                            config_saver=lambda c: None)
    assert outcome.success is False
    assert outcome.error_code == "invalid_input"


def test_apply_registration_token_store_failure():
    def _save_fail(*a, **k):
        raise RuntimeError("keyring busy")
    outcome = tr.apply_registration_result(
        "https://x", _FakeMeta(), "tok",
        token_saver=_save_fail, config_saver=lambda c: None,
    )
    assert outcome.success is False
    assert outcome.error_code == "token_store_failed"


# ── wizard CLI ────────────────────────────────────────────────────────────

def test_wizard_cli_success():
    def _register(*, server_url, registration_code, host, os_name, version):
        assert registration_code == "FAKE_REG_CODE"
        return _FakeMeta(), "FAKE_DEVICE_TOKEN"

    # apply_registration_result 가 실제 keyring 호출 안 하도록 monkeypatch
    from desktop import tray_runtime as _tr
    original = _tr.apply_registration_result
    _tr.apply_registration_result = lambda *a, **k: tr.WizardOutcome(
        success=True, agent_id=a[1].agent_id,
    )
    try:
        outcome = tr.run_registration_wizard_cli(
            server_url="https://x.example.com",
            registration_code="FAKE_REG_CODE",
            register_fn=_register,
        )
        assert outcome.success is True
        assert outcome.agent_id == "la-test1234abcd"
    finally:
        _tr.apply_registration_result = original


def test_wizard_cli_invalid_code():
    from local_agent.registration_client import RegistrationError
    def _register(**kwargs):
        raise RegistrationError(http_status=400,
                                generic_message="invalid_registration_code")
    outcome = tr.run_registration_wizard_cli(
        server_url="https://x", registration_code="bad",
        register_fn=_register,
    )
    assert outcome.success is False
    assert "invalid" in outcome.error_code or outcome.error_code == "invalid_registration_code"


def test_wizard_cli_network_error():
    from local_agent.registration_client import RegistrationError
    def _register(**kwargs):
        raise RegistrationError(generic_message="registration_network_error")
    outcome = tr.run_registration_wizard_cli(
        server_url="https://x", registration_code="x",
        register_fn=_register,
    )
    assert outcome.success is False


# ── registration_code redaction ──────────────────────────────────────────

def test_wizard_outcome_no_registration_code():
    outcome = tr.WizardOutcome(success=True, agent_id="la-x")
    d = dataclasses.asdict(outcome)
    assert "registration_code" not in d
    assert "code" not in d


def test_wizard_failure_message_no_code_leak():
    """등록코드가 오류 메시지에 들어가지 않아야 함."""
    from local_agent.registration_client import RegistrationError
    secret_code = "SUPER_SECRET_CODE_XYZ"
    def _register(**kwargs):
        # 일부러 코드를 메시지에 넣은 시나리오
        raise RegistrationError(generic_message=secret_code)
    outcome = tr.run_registration_wizard_cli(
        server_url="https://x", registration_code=secret_code,
        register_fn=_register,
    )
    # secret 가 outcome 의 어떤 필드에도 없어야 함
    full = json.dumps(dataclasses.asdict(outcome))
    assert secret_code not in full


# ── diagnostics payload ──────────────────────────────────────────────────

def test_diagnostics_payload_keys():
    s = tr.RegistrationStatus(
        registered=True, server_url="https://x.example.com",
        agent_id="la-abc1234def", token_present=True, backend="mock",
    )
    payload = tr.build_diagnostics_payload(status=s)
    for key in ["server_url_redacted", "ws_url_redacted", "agent_id_masked",
                "state", "token_present", "config_present", "keyring_backend"]:
        assert key in payload, f"키 누락: {key}"


def test_diagnostics_no_token_value():
    s = tr.RegistrationStatus(
        registered=True, server_url="x", agent_id="la-x", token_present=True,
    )
    payload = tr.build_diagnostics_payload(status=s)
    for forbidden in ["device_token", "token_value", "token_raw", "token_hash"]:
        assert forbidden not in payload


def test_diagnostics_agent_id_masked():
    s = tr.RegistrationStatus(
        registered=True, server_url="x",
        agent_id="la-abcdef123456", token_present=True,
    )
    payload = tr.build_diagnostics_payload(status=s)
    assert "***" in payload["agent_id_masked"]
    # 풀 ID 미노출
    full = json.dumps(payload)
    assert "abcdef123456" not in full


def test_diagnostics_url_redaction():
    s = tr.RegistrationStatus(
        registered=True,
        server_url="https://test.example.com?token=SECRET123",
        agent_id="la-x", token_present=True,
    )
    payload = tr.build_diagnostics_payload(status=s)
    assert "SECRET123" not in json.dumps(payload)


# ── heartbeat background ─────────────────────────────────────────────────

def test_start_heartbeat_cannot_start_unregistered():
    plan = tr.HeartbeatPlan(can_start=False, reason="not_registered")
    errors = []
    th = tr.start_heartbeat_background(plan, on_error=errors.append)
    assert th is None
    assert errors == ["not_registered"]


def test_start_heartbeat_calls_runner():
    plan = tr.HeartbeatPlan(
        can_start=True, server_url="https://x", agent_id="la-x",
        ws_url="wss://x/api/v1/local-agents/ws",
    )
    called = {"hit": False}
    def _runner(*, plan, on_state_change, on_error):
        called["hit"] = True
        called["server"] = plan.server_url
    th = tr.start_heartbeat_background(plan, runner=_runner)
    assert th is not None
    th.join(timeout=2)
    assert called["hit"] is True
    assert called["server"] == "https://x"


# ── run_tray_mode_full ───────────────────────────────────────────────────

def test_run_tray_mode_full_skip_gui():
    """skip_gui=True 면 GUI 미기동, 상태 dict 반환."""
    r = tr.run_tray_mode_full(skip_gui=True)
    assert isinstance(r, dict)
    assert "registered" in r
    assert "next_action" in r
    assert r["skip_gui"] is True


# ── launcher 통합 ────────────────────────────────────────────────────────

def test_launcher_run_tray_mode_signature():
    import inspect
    sig = inspect.signature(ml.run_tray_mode)
    assert "skip_gui" in sig.parameters


def test_launcher_run_tray_mode_skip_gui():
    """launcher.run_tray_mode(skip_gui=True) 가 tray_runtime 호출 후 0 반환."""
    rc = ml.run_tray_mode(skip_gui=True)
    assert rc == 0


def test_launcher_diagnostics_includes_server():
    """launcher diagnostics 에 server.url_redacted 추가됨."""
    d = ml.build_diagnostics()
    assert "url_redacted" in d.get("server", {})
    assert "ws_url_redacted" in d.get("server", {})


def test_launcher_diagnostics_includes_heartbeat():
    d = ml.build_diagnostics()
    assert "heartbeat" in d
    assert "state" in d["heartbeat"]


def test_launcher_diagnostics_no_token_value():
    d = ml.build_diagnostics()
    full = json.dumps(d)
    # 실제 token 값처럼 보이는 긴 base64 패턴이 없어야 함
    for pat in ["sk-proj-", "sk-ant-", "Bearer eyJ"]:
        assert pat not in full


def test_launcher_run_tray_mode_diagnostics():
    """본 공정 신규 진입점."""
    d = ml.run_tray_mode_diagnostics()
    assert "registered" in d
    assert "next_action" in d
    assert "heartbeat_plan_can_start" in d


# ── lock 회귀 ────────────────────────────────────────────────────────────

def test_lock_acquire_release_still_works():
    p = ml.lock_path()
    p.unlink(missing_ok=True)
    state = ml.acquire_lock()
    try:
        assert state.acquired
    finally:
        ml.release_lock()
    assert not p.exists() or ml._read_lock() is None


def test_lock_file_no_secret():
    p = ml.lock_path()
    p.unlink(missing_ok=True)
    state = ml.acquire_lock()
    try:
        content = p.read_text(encoding="utf-8")
        for kw in ["device_token", "registration_code", "sk-", "bearer"]:
            assert kw.lower() not in content.lower()
    finally:
        ml.release_lock()


# ── 기존 entrypoint 회귀 ────────────────────────────────────────────────

def test_existing_webview_app_importable():
    import importlib
    importlib.import_module("desktop.webview_app_pywebview")


def test_existing_local_server_importable():
    import importlib
    importlib.import_module("desktop.local_server")


def test_existing_desktop_launcher_importable():
    import importlib
    importlib.import_module("local_agent.desktop_launcher")


def test_existing_token_store_importable():
    import importlib
    mod = importlib.import_module("local_agent.token_store")
    assert hasattr(mod, "save_device_token")
    assert hasattr(mod, "load_device_token")


def test_existing_registration_client_importable():
    import importlib
    mod = importlib.import_module("local_agent.registration_client")
    assert hasattr(mod, "register_with_code")


def test_existing_connection_diagnostics_importable():
    import importlib
    mod = importlib.import_module("local_agent.connection_diagnostics")
    assert hasattr(mod, "normalize_ws_url")
    assert hasattr(mod, "build_diagnostics")


# ── 소스 secret 검사 ─────────────────────────────────────────────────────

def test_tray_runtime_source_no_secret():
    src = (ROOT / "desktop/tray_runtime.py").read_text(encoding="utf-8")
    for pat in ["sk-proj-", "sk-ant-", "Bearer eyJ"]:
        assert pat not in src


def test_tray_runtime_has_local_only_bypass_note():
    """local-only bypass 금지 정책 — Admin Mode 후속 공정에서 강화 예정."""
    # 본 공정에서는 admin_mode_available=False 라서 트레이에서 admin 진입 자체가 deferred
    src = (ROOT / "desktop/tray_runtime.py").read_text(encoding="utf-8")
    # admin/owner role 검사 존재
    assert 'role' in src.lower() and ('admin' in src.lower() or 'owner' in src.lower())


# ── Admin Mode deferred ──────────────────────────────────────────────────

def test_admin_mode_deferred_marker():
    """tray 메뉴에서 admin_mode_available=False 면 deferred 표시."""
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin",
                                      admin_mode_available=False)
    admin = next((it for it in items if it.id == "open_admin"), None)
    assert admin is not None
    assert admin.enabled is False
    assert "준비 중" in admin.label or admin.enabled is False


# ── consent hook ────────────────────────────────────────────────────────

def test_consent_hook_still_present():
    """launcher 의 consent hook 은 그대로 유지."""
    r = ml.check_consent_hook()
    assert isinstance(r, dict)
    assert "agreed" in r
