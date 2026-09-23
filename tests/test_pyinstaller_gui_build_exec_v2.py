"""PYINSTALLER_BUILD_EXEC_V2_01 — 12+ 테스트."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

DIST_DIR = Path("dist/HaehanAI-Agent")
EXE = DIST_DIR / "HaehanAI-Agent.exe"
BUILD_REPORT = Path("data/inspection/local_agent_installer_package/build_report.json")

_REQUIRES_EXE = pytest.mark.skipif(not EXE.exists(), reason=f"exe not built: {EXE}")


def _run_exe(args, timeout=30):
    return subprocess.run([str(EXE), *args], capture_output=True, text=True, timeout=timeout, errors="replace")


# ── 1) build report — GUI hidden imports ─────────────────────────


@_REQUIRES_EXE
def test_build_report_includes_gui_hidden_imports():
    assert BUILD_REPORT.exists()
    br = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    cmd = br.get("cmd", "")
    for imp in ("tkinter", "pystray", "PIL"):
        assert imp in cmd, f"hidden import missing in build cmd: {imp}"


@_REQUIRES_EXE
def test_build_report_ok():
    br = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    assert br.get("ok") is True


# ── 2) exe metadata ─────────────────────────────────────────


@_REQUIRES_EXE
def test_exe_size_within_range_after_gui_imports():
    sz = EXE.stat().st_size
    # GUI 추가 후 약간 커짐 — 100KB ~ 50MB 범위
    assert 100_000 < sz < 50_000_000


@_REQUIRES_EXE
def test_exe_sha256_64_hex():
    import hashlib

    h = hashlib.sha256()
    with open(EXE, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    digest = h.hexdigest()
    assert len(digest) == 64


# ── 3) CLI 회귀 ─────────────────────────────────────────────


@_REQUIRES_EXE
def test_cli_self_test_passes_after_gui_rebuild():
    r = _run_exe(["--self-test"], timeout=30)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert data["checks"]["diagnostics_render_leaks"] == []


@_REQUIRES_EXE
def test_cli_diagnostics_passes_after_gui_rebuild():
    r = _run_exe(["--diagnostics"], timeout=15)
    assert r.returncode == 0


@_REQUIRES_EXE
def test_cli_default_without_agent_id_returns_2():
    r = _run_exe([])
    assert r.returncode == 2


# ── 4) leak 검사 ────────────────────────────────────────────


@_REQUIRES_EXE
def test_self_test_output_no_token_leak():
    r = _run_exe(["--self-test"], timeout=30)
    out = r.stdout + r.stderr
    import re

    assert not re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', out)
    assert not re.search(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"', out)


@_REQUIRES_EXE
def test_diagnostics_output_no_token_leak():
    r = _run_exe(["--diagnostics"], timeout=15)
    out = r.stdout + r.stderr
    import re

    assert not re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', out)


# ── 5) audit ────────────────────────────────────────────────


def test_audit_module_imports():
    from scripts.ops import audit_pyinstaller_gui_build_exec_v2 as a

    assert hasattr(a, "judge_gui_build")
    assert hasattr(a, "_gui_launch_smoke")


def test_audit_fail_dist_missing(monkeypatch, tmp_path):
    from scripts.ops import audit_pyinstaller_gui_build_exec_v2 as a

    monkeypatch.setattr(a, "EXE", tmp_path / "missing.exe")
    v = a.judge_gui_build(gui_smoke_ok=True)
    assert v.code == "FAIL_DIST_MISSING"


def test_audit_fail_cli_regression_signal():
    from scripts.ops import audit_pyinstaller_gui_build_exec_v2 as a

    # exe 존재 가정 — gui_smoke_ok True 로 GUI 부분 skip, cli_regression False
    if not EXE.exists():
        pytest.skip("exe not built")
    v = a.judge_gui_build(gui_smoke_ok=True, cli_regression_ok=False)
    assert v.code == "FAIL_CLI_REGRESSION"


@_REQUIRES_EXE
def test_audit_warn_unsigned_when_all_pass():
    from scripts.ops import audit_pyinstaller_gui_build_exec_v2 as a

    # GUI smoke 외부 신호로 True 주입 (실 5초 launch smoke 건너뜀)
    v = a.judge_gui_build(gui_smoke_ok=True, cli_regression_ok=True)
    assert v.code in ("PASS_PYINSTALLER_GUI_BUILD_EXEC_V2", "WARN_UNSIGNED_BINARY")


# ── 6) GUI 코드 회귀 가드 ───────────────────────────────────


def test_regression_gui_state_intact():
    from local_agent import gui_state as gs

    assert hasattr(gs, "GuiController")
    assert hasattr(gs, "transition")


def test_regression_gui_app_intact():
    from local_agent import gui_app

    for m in ("on_register", "on_connect", "on_diagnostics", "on_reset", "on_quit"):
        assert hasattr(gui_app.HaehanAgentGuiApp, m)


def test_regression_gui_tray_intact():
    from local_agent import gui_tray

    assert hasattr(gui_tray, "run_tray_with_app")


def test_regression_desktop_launcher_gui_flag_intact():
    text = Path("local_agent/desktop_launcher.py").read_text(encoding="utf-8")
    assert "--gui" in text and "gui_tray" in text


def test_regression_build_script_gui_hidden_imports():
    text = Path("scripts/build_desktop_agent_windows.py").read_text(encoding="utf-8")
    for imp in ("tkinter", "pystray", "PIL"):
        assert imp in text
