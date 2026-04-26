"""KAKAO-DEV-3R 테스트 — observe_kakao_apps.py 검증."""
from __future__ import annotations

import ast
import importlib
import json
import re
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

_MODULE_PATH = REPO_ROOT / "scripts" / "observe_kakao_apps.py"

# ---------------------------------------------------------------------------
# source-level safety assertions (no runtime import needed)
# ---------------------------------------------------------------------------

_SOURCE = _MODULE_PATH.read_text(encoding="utf-8")
_SECRET_PATTERN = re.compile(r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)


def _executable_lines(source: str) -> str:
    """Strip docstrings and comments, return only executable code lines."""
    tree = ast.parse(source)
    # Collect line ranges of string constants used as docstrings
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ds = body[0]
                for ln in range(ds.lineno, ds.end_lineno + 1):
                    docstring_lines.add(ln)

    result_lines = []
    for i, line in enumerate(source.splitlines(), start=1):
        if i in docstring_lines:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        result_lines.append(line)
    return "\n".join(result_lines)


_EXEC_SOURCE = _executable_lines(_SOURCE)


def test_no_password_input_read():
    assert "input_value" not in _EXEC_SOURCE
    assert 'type="password"' not in _EXEC_SOURCE
    assert ".fill(" not in _EXEC_SOURCE or "password" not in _EXEC_SOURCE


def test_no_cookie_session_export():
    for bad in ("storage_state", "cookies()", "export_storage", "get_cookies"):
        assert bad not in _EXEC_SOURCE, f"forbidden in executable code: {bad}"


def test_no_app_delete_or_secret_reissue():
    for bad in ("delete_app", "reissue_secret", "revoke_secret", "discard_secret"):
        assert bad not in _EXEC_SOURCE, f"forbidden in executable code: {bad}"


def test_no_submit_click():
    for bad in ("submit()", ".submit(", "click_submit"):
        assert bad not in _EXEC_SOURCE, f"forbidden in executable code: {bad}"


def test_mask_secrets_function_exists():
    assert "_mask_secrets" in _SOURCE


def test_source_has_no_raw_secret_string():
    for line in _SOURCE.splitlines():
        if line.strip().startswith("#"):
            continue
        if '"""' in line or "'''" in line:
            continue
        m = _SECRET_PATTERN.search(line)
        if m:
            pytest.fail(f"raw secret-like string in source: {line!r}")


# ---------------------------------------------------------------------------
# functional tests (mock browser + session health)
# ---------------------------------------------------------------------------

spec = importlib.util.spec_from_file_location("observe_kakao_apps", _MODULE_PATH)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)


def test_ready_logged_in_result_structure(tmp_path):
    fake_raw = {
        "success": True,
        "status_code": 200,
        "title": "내 애플리케이션 - Kakao Developers",
        "text_excerpt": "로그아웃 내 애플리케이션 앱 만들기 카카오 로그인 동의항목 플랫폼",
        "links": [],
        "buttons": [],
        "warnings": [],
    }
    with (
        patch.object(_mod, "_check_session_health", return_value="READY_LOGGED_IN"),
        patch("local_agent.browser_observer.observe_public_browser_page", return_value=fake_raw),
    ):
        result = _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert result["session_status"] == "READY_LOGGED_IN"
    assert result["pending_task_created"] is False
    assert result["pending_task_path"] is None
    assert result["apps_visible"] is True
    assert result["kakao_login_menu_found"] is True
    assert result["consent_items_menu_found"] is True
    assert result["platform_menu_found"] is True
    assert result["secret_like_values_captured"] is False
    apps_json = tmp_path / next(tmp_path.iterdir()).name / "apps.json"
    assert apps_json.exists()
    data = json.loads(apps_json.read_text(encoding="utf-8"))
    assert data["session_status"] == "READY_LOGGED_IN"


def test_needs_reauth_creates_pending_task(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="NEEDS_REAUTH"):
        result = _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert result["session_status"] == "NEEDS_REAUTH"
    assert result["pending_task_created"] is True
    assert result["pending_task_path"] is not None
    pt = Path(result["pending_task_path"])
    assert pt.exists()
    task = json.loads(pt.read_text(encoding="utf-8"))
    assert task["status"] == "PENDING"
    assert task["auth_principal_required"] == "developer_console_operator"
    assert task["resume_script"] == "scripts/observe_kakao_apps.py"


def test_unknown_session_creates_pending_task(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="UNKNOWN"):
        result = _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert result["pending_task_created"] is True


def test_secret_masking():
    raw_with_secret = {
        "text_excerpt": "key=abcdef1234567890abcdef1234567890",
        "links": [],
        "buttons": [],
    }
    safe = _mod._sanitize(raw_with_secret)
    assert "[MASKED]" in safe["text_excerpt"]
    assert "abcdef1234567890abcdef1234567890" not in safe["text_excerpt"]
    assert safe["secret_like_detected"] is True


def test_no_raw_key_in_output(tmp_path):
    raw_key = "a" * 32
    fake_raw = {
        "success": True,
        "status_code": 200,
        "title": "내 애플리케이션",
        "text_excerpt": f"로그아웃 앱 목록 key={raw_key}",
        "links": [],
        "buttons": [],
        "warnings": [],
    }
    with (
        patch.object(_mod, "_check_session_health", return_value="READY_LOGGED_IN"),
        patch("local_agent.browser_observer.observe_public_browser_page", return_value=fake_raw),
    ):
        result = _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    run_dir = tmp_path / sorted(tmp_path.iterdir())[-1].name
    apps_json_text = (run_dir / "apps.json").read_text(encoding="utf-8")
    assert raw_key not in apps_json_text


def test_next_actions_generated(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="NEEDS_REAUTH"):
        result = _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert len(result["next_actions"]) >= 1
    keys = [a["task_key"] for a in result["next_actions"]]
    assert "KAKAO-DEV-3R-REAUTH" in keys
