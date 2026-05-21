"""tests/test_desktop_webview_pyinstaller_package.py

DESKTOP_WEBVIEW_PYINSTALLER_PACKAGE_01 단위 테스트.
빌드 산출물 없어도 소스/스크립트/정책 검증 가능.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "inspection" / "desktop_webview_pyinstaller_package"
BUILD_REPORT = OUT_DIR / "build_report.json"
RUNTIME_REPORT = OUT_DIR / "runtime_smoke_report.json"

_SECRET_RE = re.compile(
    r"(device_token|registration_code|api[_\-]?key|authorization|cookie|session|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


# ── 1. build script 존재 ──────────────────────────────────────────────────────

def test_build_script_exists():
    p = ROOT / "scripts" / "build_desktop_webview_app_windows.py"
    assert p.exists(), "build_desktop_webview_app_windows.py 없음"


# ── 2. launcher 존재 ──────────────────────────────────────────────────────────

def test_launcher_exists():
    p = ROOT / "build" / "webview_launcher.py"
    assert p.exists(), "webview_launcher.py 없음"
    src = p.read_text(encoding="utf-8")
    assert "webview_app_pywebview" in src or "desktop.webview_app_pywebview" in src


# ── 3. pywebview entry 존재 ───────────────────────────────────────────────────

def test_webview_entry_exists():
    p = ROOT / "desktop" / "webview_app_pywebview.py"
    assert p.exists()
    src = p.read_text(encoding="utf-8")
    assert "_LOCAL_URL" in src or "127.0.0.1:8765" in src
    assert "ensure_server" in src or "_is_server_up" in src


# ── 4. ui_dist asset 포함 계획 ───────────────────────────────────────────────

def test_ui_dist_add_data_in_build_script():
    src = (ROOT / "scripts" / "build_desktop_webview_app_windows.py").read_text(encoding="utf-8")
    assert "add-data" in src, "--add-data 옵션 없음"
    assert "ui_dist" in src, "ui_dist 번들 설정 없음"


def test_ui_dist_assets_exist():
    dist = ROOT / "desktop" / "ui_dist"
    assert dist.exists()
    assert (dist / "index.html").exists()
    js = list((dist / "assets").glob("index-*.js"))
    css = list((dist / "assets").glob("index-*.css"))
    assert js, "JS asset 없음"
    assert css, "CSS asset 없음"


# ── 5. hidden imports 검증 ────────────────────────────────────────────────────

def test_hidden_imports_in_build_script():
    src = (ROOT / "scripts" / "build_desktop_webview_app_windows.py").read_text(encoding="utf-8")
    required = ["uvicorn", "fastapi", "starlette", "websockets", "webview",
                "local_agent", "desktop"]
    for imp in required:
        assert imp in src, f"hidden import '{imp}' 없음"


# ── 6. lifecycle 정책 검증 ────────────────────────────────────────────────────

def test_lifecycle_policy_in_webview_entry():
    src = (ROOT / "desktop" / "webview_app_pywebview.py").read_text(encoding="utf-8")
    assert "_is_server_up" in src or "_port_listening" in src or "ensure_server" in src
    assert "_server_owned" in src or "ensure_server" in src or "_start_embedded_server" in src
    assert "ensure_server" in src, "서버 재사용/기동 함수 없음"


# ── 7. local_server PyInstaller 경로 처리 ────────────────────────────────────

def test_local_server_frozen_path_handling():
    src = (ROOT / "desktop" / "local_server.py").read_text(encoding="utf-8")
    assert "frozen" in src or "_MEIPASS" in src, "PyInstaller frozen 경로 처리 없음"
    assert "_resolve_ui_dir" in src or "_UI_DIR" in src


# ── 8. report schema 검증 ────────────────────────────────────────────────────

def test_runtime_report_schema():
    if not RUNTIME_REPORT.exists():
        import pytest; pytest.skip("runtime_smoke_report 미생성")
    r = json.loads(RUNTIME_REPORT.read_text(encoding="utf-8"))
    required = ["run_at", "task_id", "source_artifacts", "build_script_content",
                "build_artifacts", "runtime_server", "runtime_ws", "runtime_ui",
                "runtime_admin_proxy", "pywebview", "final_verdict", "verdicts"]
    for k in required:
        assert k in r, f"'{k}' 누락"
    assert r["task_id"] == "DESKTOP_WEBVIEW_PYINSTALLER_PACKAGE_01"


# ── 9. secret leak detection ──────────────────────────────────────────────────

def test_no_secret_in_build_script():
    src = (ROOT / "scripts" / "build_desktop_webview_app_windows.py").read_text(encoding="utf-8")
    m = _SECRET_RE.search(src)
    assert not m, f"build script에 secret 패턴: {m.group()[:30] if m else ''}"


def test_no_secret_in_runtime_report():
    if not RUNTIME_REPORT.exists():
        import pytest; pytest.skip("runtime_smoke_report 미생성")
    text = RUNTIME_REPORT.read_text(encoding="utf-8")
    m = _SECRET_RE.search(text)
    assert not m, f"runtime_smoke_report에 secret 노출"


def test_no_secret_in_build_report():
    if not BUILD_REPORT.exists():
        import pytest; pytest.skip("build_report 미생성")
    text = BUILD_REPORT.read_text(encoding="utf-8")
    m = _SECRET_RE.search(text)
    assert not m, f"build_report에 secret 노출"


# ── 10. verdict logic ─────────────────────────────────────────────────────────

def test_verdict_fail_exe_missing():
    from scripts.ops.audit_desktop_webview_pyinstaller_package import check_build_artifacts
    with mock.patch("scripts.ops.audit_desktop_webview_pyinstaller_package.EXE_ONEDIR",
                    ROOT / "dist" / "__nonexistent__" / "X.exe"), \
         mock.patch("scripts.ops.audit_desktop_webview_pyinstaller_package.EXE_ONEFILE",
                    ROOT / "dist" / "__nonexistent__.exe"):
        r = check_build_artifacts()
    assert not r["ok"]
    assert r["verdict"] == "FAIL_EXE_MISSING"


def test_verdict_fail_secret_leak():
    from scripts.ops.audit_desktop_webview_pyinstaller_package import check_secret_leak
    r = check_secret_leak({"data": "device_token=abc123secret"})
    assert not r["ok"]
    assert r["verdict"] == "FAIL_SECRET_LEAK"


def test_verdict_ok_clean():
    from scripts.ops.audit_desktop_webview_pyinstaller_package import check_secret_leak
    r = check_secret_leak({"agent_id": "la-xxx", "connected": True})
    assert r["ok"]
    assert r["verdict"] == "OK"


# ── 11. dist commit 제외 검증 ────────────────────────────────────────────────

def test_dist_not_in_git_tracked():
    """dist/ 는 .gitignore 에 포함되어야 함."""
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        import pytest; pytest.skip(".gitignore 없음")
    content = gitignore.read_text(encoding="utf-8")
    assert "dist/" in content or "/dist" in content, "dist/ 가 .gitignore에 없음"


# ── 12. admin proxy path format ───────────────────────────────────────────────

def test_admin_proxy_paths():
    from scripts.ops.audit_desktop_webview_pyinstaller_package import check_runtime_admin_proxy
    with mock.patch("scripts.ops.audit_desktop_webview_pyinstaller_package._get",
                    return_value=(200, "")), \
         mock.patch("scripts.ops.audit_desktop_webview_pyinstaller_package._port_up", return_value=True):
        r = check_runtime_admin_proxy()
    expected = ["admin_dashboard", "admin_ops", "admin_approvals", "admin_agents", "admin_cad"]
    for k in expected:
        assert k in r, f"admin_proxy.{k} 누락"


# ── 13. 기존 local e2e smoke 회귀 ────────────────────────────────────────────

def test_regression_local_server_url():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import BASE_URL
    assert "127.0.0.1" in BASE_URL
    assert "8765" in BASE_URL


def test_regression_ui_assets():
    dist = ROOT / "desktop" / "ui_dist"
    assert (dist / "index.html").exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
