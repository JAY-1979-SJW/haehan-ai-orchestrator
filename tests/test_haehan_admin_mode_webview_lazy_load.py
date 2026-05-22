"""HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 회귀 테스트."""
from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

ADMIN_MOD = ROOT / "desktop/admin_webview.py"


# ── 모듈 / 심볼 ───────────────────────────────────────────────────────────

def test_admin_webview_module_importable():
    from desktop import admin_webview  # noqa
    assert admin_webview is not None


def test_required_symbols():
    from desktop import admin_webview as aw
    needed = ["is_admin_role", "RoleGuardResult", "check_role_via_api",
              "resolve_current_role", "open_admin_window", "run_admin_mode_full",
              "is_admin_window_active", "ADMIN_ROLES", "KNOWN_ROLES"]
    for s in needed:
        assert hasattr(aw, s), f"missing {s}"


# ── lazy import (핵심) ──────────────────────────────────────────────────

def test_pywebview_not_imported_at_module_top_static():
    """AST 검사 — admin_webview 의 top-level 에 webview import 가 없어야 함."""
    src = ADMIN_MOD.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Import):
            for n in node.names:
                assert "webview" not in (n.name or "").lower(), \
                    f"top-level import: {n.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "webview" not in mod.lower(), f"top-level import from: {mod}"


def test_pywebview_imported_only_inside_functions():
    """소스 텍스트 검사 — 'import webview' 가 들여쓰기된 라인에만 등장."""
    src = ADMIN_MOD.read_text(encoding="utf-8")
    found_indented = False
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("import webview") or stripped.startswith("from webview"):
            # 들여쓰기 없는 = 0 칸 차이 = top-level
            assert line != stripped, f"top-level webview import: {line!r}"
            found_indented = True
    assert found_indented, "webview lazy import 가 admin_webview 안에 없음"


def test_admin_webview_load_does_not_import_webview():
    """admin_webview import 후 sys.modules 에 webview 가 없어야 함."""
    for mod_name in list(sys.modules.keys()):
        if mod_name == "webview" or mod_name.startswith("webview."):
            del sys.modules[mod_name]
    for mod_name in list(sys.modules.keys()):
        if mod_name == "desktop.admin_webview":
            del sys.modules[mod_name]
    from desktop import admin_webview  # noqa
    after = [m for m in sys.modules.keys()
             if m == "webview" or m.startswith("webview.")]
    assert not after, f"admin_webview import 후 webview 발견: {after}"


def test_tray_runtime_top_level_no_admin_webview():
    """tray_runtime 도 top-level 에 admin_webview import 하면 안 됨 (lazy 유지)."""
    src = (ROOT / "desktop/tray_runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for n in node.names:
                full = f"{mod}.{n.name}" if mod else n.name
                assert "admin_webview" not in full, \
                    f"tray_runtime top-level admin_webview import: {full}"


# ── role 판단 ─────────────────────────────────────────────────────────────

def test_is_admin_role_admin():
    from desktop.admin_webview import is_admin_role
    assert is_admin_role("admin") is True


def test_is_admin_role_owner():
    from desktop.admin_webview import is_admin_role
    assert is_admin_role("owner") is True


def test_is_admin_role_case_insensitive():
    from desktop.admin_webview import is_admin_role
    assert is_admin_role("ADMIN") is True
    assert is_admin_role("Owner") is True


def test_is_admin_role_any_rejected():
    from desktop.admin_webview import is_admin_role
    assert is_admin_role("any") is False


def test_is_admin_role_user_rejected():
    from desktop.admin_webview import is_admin_role
    assert is_admin_role("user") is False


def test_is_admin_role_viewer_rejected():
    from desktop.admin_webview import is_admin_role
    assert is_admin_role("viewer") is False


def test_is_admin_role_empty_rejected():
    from desktop.admin_webview import is_admin_role
    assert is_admin_role("") is False
    assert is_admin_role(None) is False  # type: ignore


# ── check_role_via_api ───────────────────────────────────────────────────

def test_check_role_explicit_admin():
    from desktop.admin_webview import check_role_via_api
    r = check_role_via_api(explicit_role="admin")
    assert r.passed is True
    assert r.role == "admin"
    assert r.source == "explicit"


def test_check_role_explicit_owner():
    from desktop.admin_webview import check_role_via_api
    r = check_role_via_api(explicit_role="owner")
    assert r.passed is True


def test_check_role_explicit_any_rejected():
    from desktop.admin_webview import check_role_via_api
    r = check_role_via_api(explicit_role="any")
    assert r.passed is False


def test_check_role_local_only_bypass_forbidden():
    """127.0.0.1 이라도 role 검사 통과해야 admin."""
    from desktop.admin_webview import check_role_via_api
    def _fake_any(server_url, timeout):
        return {"role": "any", "status": "ok"}
    r = check_role_via_api(
        server_url="http://127.0.0.1:8765",
        api_caller=_fake_any,
    )
    assert r.passed is False, "127.0.0.1 + role=any 인데 admin 통과"


def test_check_role_api_admin_passes():
    from desktop.admin_webview import check_role_via_api
    def _fake_admin(server_url, timeout):
        return {"role": "admin", "status": "ok"}
    r = check_role_via_api(api_caller=_fake_admin)
    assert r.passed is True
    assert r.role == "admin"
    assert r.source == "api"


def test_check_role_api_error():
    from desktop.admin_webview import check_role_via_api
    def _broken(server_url, timeout):
        raise ConnectionRefusedError("nope")
    r = check_role_via_api(api_caller=_broken)
    assert r.passed is False
    assert "api_error" in r.reason


# ── secret leak 차단 ─────────────────────────────────────────────────────

def test_whoami_response_with_device_token_rejected():
    from desktop.admin_webview import check_role_via_api
    def _leak(server_url, timeout):
        return {"role": "admin", "device_token": "BAD_LEAK"}
    r = check_role_via_api(api_caller=_leak)
    assert r.passed is False
    assert "secret" in r.reason.lower() or "forbidden" in r.reason.lower()


def test_whoami_response_with_registration_code_rejected():
    from desktop.admin_webview import check_role_via_api
    def _leak(server_url, timeout):
        return {"role": "owner", "registration_code": "REG_LEAK"}
    r = check_role_via_api(api_caller=_leak)
    assert r.passed is False


def test_whoami_response_with_bearer_rejected():
    from desktop.admin_webview import check_role_via_api
    def _leak(server_url, timeout):
        return {"role": "admin", "bearer_token": "eyJ_BAD"}
    r = check_role_via_api(api_caller=_leak)
    assert r.passed is False


def test_role_guard_result_no_token_field():
    from desktop.admin_webview import RoleGuardResult
    import dataclasses
    r = RoleGuardResult(passed=True, role="admin", source="explicit")
    d = dataclasses.asdict(r)
    assert "token" not in d
    assert "device_token" not in d
    assert "registration_code" not in d


# ── resolve_current_role ─────────────────────────────────────────────────

def test_resolve_explicit_priority():
    from desktop.admin_webview import resolve_current_role
    os.environ["HAEHAN_ROLE"] = "owner"
    try:
        # explicit 가 env 보다 우선
        assert resolve_current_role(explicit_role="admin") == "admin"
    finally:
        del os.environ["HAEHAN_ROLE"]


def test_resolve_env_role():
    from desktop.admin_webview import resolve_current_role
    os.environ["HAEHAN_ROLE"] = "viewer"
    try:
        assert resolve_current_role() == "viewer"
    finally:
        del os.environ["HAEHAN_ROLE"]


def test_resolve_env_invalid_falls_back():
    from desktop.admin_webview import resolve_current_role
    os.environ["HAEHAN_ROLE"] = "superuser"  # KNOWN_ROLES 외
    try:
        def _broken(server_url, timeout):
            raise ConnectionRefusedError()
        result = resolve_current_role(api_caller=_broken)
        assert result == "any"
    finally:
        del os.environ["HAEHAN_ROLE"]


def test_resolve_api_fallback():
    from desktop.admin_webview import resolve_current_role
    os.environ.pop("HAEHAN_ROLE", None)
    def _fake(server_url, timeout):
        return {"role": "admin", "status": "ok"}
    assert resolve_current_role(api_caller=_fake) == "admin"


def test_resolve_no_source_defaults_any():
    from desktop.admin_webview import resolve_current_role
    os.environ.pop("HAEHAN_ROLE", None)
    def _broken(server_url, timeout):
        raise ConnectionRefusedError()
    assert resolve_current_role(api_caller=_broken) == "any"


# ── open_admin_window ────────────────────────────────────────────────────

def test_open_admin_window_role_rejected():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    r = aw.open_admin_window(explicit_role="any", skip_gui=True)
    assert r["ok"] is False
    assert r["window_opened"] is False


def test_open_admin_window_admin_skip_gui():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    r = aw.open_admin_window(explicit_role="admin", skip_gui=True)
    assert r["ok"] is True
    assert r["window_opened"] is False
    assert r["skip_gui"] is True
    assert r["role"] == "admin"


def test_open_admin_window_owner_skip_gui():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    r = aw.open_admin_window(explicit_role="owner", skip_gui=True)
    assert r["ok"] is True


def test_open_admin_window_haehan_skip_gui_env():
    """HAEHAN_SKIP_GUI=1 env 가 skip_gui=None 인자 기본을 결정."""
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    os.environ["HAEHAN_SKIP_GUI"] = "1"
    try:
        r = aw.open_admin_window(explicit_role="admin")  # skip_gui=None
        assert r["ok"] is True
        assert r["window_opened"] is False
        assert r["skip_gui"] is True
    finally:
        del os.environ["HAEHAN_SKIP_GUI"]


def test_open_admin_window_single_instance():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    # 슬롯 점유
    aw._try_acquire_window()
    try:
        r = aw.open_admin_window(explicit_role="admin", skip_gui=True)
        assert r["ok"] is True
        assert r["reason"] == "already_open"
        assert r["window_opened"] is False
    finally:
        aw._reset_admin_window_state()


def test_open_admin_window_secret_leak_blocked():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    def _leak(server_url, timeout):
        return {"role": "admin", "device_token": "LEAK"}
    r = aw.open_admin_window(api_caller=_leak, skip_gui=True)
    assert r["ok"] is False


def test_open_admin_window_no_token_in_result():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    r = aw.open_admin_window(explicit_role="admin", skip_gui=True)
    full = json.dumps(r)
    for forbidden in ["device_token", "registration_code", "bearer", "sk-"]:
        assert forbidden not in full, f"{forbidden} in result: {r}"


# ── main_launcher.run_admin_mode ─────────────────────────────────────────

def test_run_admin_mode_admin_returns_zero():
    from desktop import main_launcher as ml
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    os.environ["HAEHAN_SKIP_GUI"] = "1"
    try:
        rc = ml.run_admin_mode(explicit_role="admin", skip_gui=True)
        assert rc == 0
    finally:
        del os.environ["HAEHAN_SKIP_GUI"]


def test_run_admin_mode_owner_returns_zero():
    from desktop import main_launcher as ml
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    rc = ml.run_admin_mode(explicit_role="owner", skip_gui=True)
    assert rc == 0


def test_run_admin_mode_any_returns_two():
    from desktop import main_launcher as ml
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    rc = ml.run_admin_mode(explicit_role="any", skip_gui=True)
    assert rc == 2


def test_run_admin_mode_user_returns_two():
    from desktop import main_launcher as ml
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    rc = ml.run_admin_mode(explicit_role="user", skip_gui=True)
    assert rc == 2


def test_run_admin_mode_signature_skip_gui():
    import inspect
    from desktop import main_launcher as ml
    sig = inspect.signature(ml.run_admin_mode)
    assert "skip_gui" in sig.parameters
    assert "explicit_role" in sig.parameters


# ── tray menu role guard ─────────────────────────────────────────────────

def test_tray_menu_role_any_no_admin_item():
    from desktop import tray_runtime as tr
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="any", admin_mode_available=True)
    ids = [it.id for it in items]
    assert "open_admin" not in ids


def test_tray_menu_role_user_no_admin_item():
    from desktop import tray_runtime as tr
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="user", admin_mode_available=True)
    ids = [it.id for it in items]
    assert "open_admin" not in ids


def test_tray_menu_role_admin_has_admin_item():
    from desktop import tray_runtime as tr
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin", admin_mode_available=True)
    ids = [it.id for it in items]
    assert "open_admin" in ids
    admin_item = next(it for it in items if it.id == "open_admin")
    assert admin_item.enabled is True


def test_tray_menu_role_owner_has_admin_item():
    from desktop import tray_runtime as tr
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="owner", admin_mode_available=True)
    ids = [it.id for it in items]
    assert "open_admin" in ids


def test_tray_menu_admin_mode_unavailable_disabled():
    from desktop import tray_runtime as tr
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin", admin_mode_available=False)
    admin_item = next(it for it in items if it.id == "open_admin")
    assert admin_item.enabled is False


# ── tray_runtime.open_admin_handler ──────────────────────────────────────

def test_tray_open_admin_handler_exists():
    from desktop import tray_runtime as tr
    assert hasattr(tr, "open_admin_handler")


def test_tray_open_admin_handler_admin_skip_gui():
    from desktop import tray_runtime as tr
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    r = tr.open_admin_handler(explicit_role="admin", skip_gui=True)
    assert r["ok"] is True


def test_tray_open_admin_handler_role_rejected():
    from desktop import tray_runtime as tr
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    r = tr.open_admin_handler(explicit_role="any", skip_gui=True)
    assert r["ok"] is False


# ── launcher run_tray_mode admin_mode_available=True ────────────────────

def test_launcher_run_tray_mode_passes_admin_mode_available_true():
    """소스 수준 — admin_mode_available=True 가 run_tray_mode 에 등장."""
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    assert "admin_mode_available=True" in src


def test_launcher_run_tray_mode_skip_gui_still_zero():
    from desktop import main_launcher as ml
    rc = ml.run_tray_mode(skip_gui=True, role="any")
    assert rc == 0


def test_launcher_run_tray_mode_admin_role_skip_gui():
    from desktop import main_launcher as ml
    rc = ml.run_tray_mode(skip_gui=True, role="admin")
    assert rc == 0


# ── 기존 entrypoint 회귀 ────────────────────────────────────────────────

def test_consent_module_importable():
    """legacy UI 제거 후 consent 로직은 desktop.consent 에 존재."""
    mod = importlib.import_module("desktop.consent")
    assert hasattr(mod, "check_consent")


def test_existing_local_server_importable():
    importlib.import_module("desktop.local_server")


def test_existing_desktop_launcher_importable():
    importlib.import_module("local_agent.desktop_launcher")


def test_existing_token_store_importable():
    importlib.import_module("local_agent.token_store")


def test_existing_registration_client_importable():
    importlib.import_module("local_agent.registration_client")


def test_existing_connection_diagnostics_importable():
    importlib.import_module("local_agent.connection_diagnostics")


def test_existing_tray_runtime_importable():
    importlib.import_module("desktop.tray_runtime")


# ── 소스 secret 없음 ────────────────────────────────────────────────────

def test_admin_webview_source_no_real_secret():
    src = ADMIN_MOD.read_text(encoding="utf-8")
    for pat in ["sk-proj-", "sk-ant-", "Bearer eyJ"]:
        assert pat not in src


def test_admin_webview_source_has_local_only_bypass_note():
    src = ADMIN_MOD.read_text(encoding="utf-8")
    assert "local-only bypass" in src.lower() or "bypass" in src.lower()


def test_admin_webview_source_lazy_import_doc():
    src = ADMIN_MOD.read_text(encoding="utf-8")
    assert "lazy" in src.lower()


# ── server kill 방지 ────────────────────────────────────────────────────

def test_admin_window_close_does_not_call_shutdown():
    """admin_webview 가 local_server 종료 함수를 호출하지 않음 (소스 검사)."""
    src = ADMIN_MOD.read_text(encoding="utf-8")
    forbidden = ["graceful_shutdown_hook(", "shutdown_server",
                 "local_server.shutdown", "release_lock("]
    for pat in forbidden:
        assert pat not in src, f"admin_webview 에 {pat} 호출 — local_server 종료시킬 위험"


def test_admin_run_does_not_release_global_lock():
    """run_admin_mode 가 main_launcher.release_lock 을 호출하지 않음."""
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    # run_admin_mode 함수 내부에서 release_lock 호출 없는지
    # — graceful_shutdown_hook 은 main() 의 finally 에서만
    import re
    func_match = re.search(r"def run_admin_mode\(.*?\n(.*?)\n(?=def |\Z)",
                           src, re.DOTALL)
    if func_match:
        body = func_match.group(1)
        assert "release_lock(" not in body
        assert "graceful_shutdown_hook(" not in body


# ── 중복 호출 안전 ─────────────────────────────────────────────────────

def test_open_admin_window_can_reset_and_reopen():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    r1 = aw.open_admin_window(explicit_role="admin", skip_gui=True)
    assert r1["ok"] is True
    # skip_gui 일 때는 자동 _release 됐으므로 즉시 다시 가능
    r2 = aw.open_admin_window(explicit_role="admin", skip_gui=True)
    assert r2["ok"] is True


def test_is_admin_window_active_initially_false():
    from desktop import admin_webview as aw
    aw._reset_admin_window_state()
    assert aw.is_admin_window_active() is False
