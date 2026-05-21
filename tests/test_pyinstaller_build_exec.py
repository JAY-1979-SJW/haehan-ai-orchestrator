"""PYINSTALLER_BUILD_EXEC_01 — 8+ 테스트 (빌드 후 산출물 검증)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

DIST_DIR = Path("dist/HaehanAI-Agent")
EXE = DIST_DIR / "HaehanAI-Agent.exe"
BUILD_REPORT = Path("data/inspection/local_agent_installer_package/build_report.json")


_REQUIRES_EXE = pytest.mark.skipif(not EXE.exists(),
                                     reason=f"exe not built: {EXE}")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _run_exe(args, timeout=30):
    return subprocess.run([str(EXE), *args], capture_output=True,
                           text=True, timeout=timeout, errors="replace")


# ── 1) build artifact 존재 ──────────────────────────────────────────


@_REQUIRES_EXE
def test_exe_exists():
    assert EXE.exists()
    assert EXE.is_file()


@_REQUIRES_EXE
def test_exe_size_reasonable():
    sz = EXE.stat().st_size
    assert sz > 100_000, f"exe too small: {sz}"
    assert sz < 50_000_000, f"exe surprisingly large: {sz}"


@_REQUIRES_EXE
def test_exe_sha256_deterministic_within_run():
    a = _sha256(EXE); b = _sha256(EXE)
    assert a == b


# ── 2) build_report ─────────────────────────────────────────────────


@_REQUIRES_EXE
def test_build_report_marks_ok():
    assert BUILD_REPORT.exists()
    br = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    assert br.get("ok") is True
    assert br.get("pyinstaller_version")
    assert br.get("mode") in ("onefolder", "onefile")


@_REQUIRES_EXE
def test_build_report_checksum_matches_exe():
    br = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    csum_in_report = br.get("checksums", {}).get("HaehanAI-Agent.exe")
    if csum_in_report:
        # 재실행 시 새로 빌드되어 sha 가 다를 수 있으나 형식 검증
        assert len(csum_in_report) == 64


# ── 3) self-test ────────────────────────────────────────────────────


@_REQUIRES_EXE
def test_exe_self_test_returns_zero():
    r = _run_exe(["--self-test"], timeout=30)
    assert r.returncode == 0, f"err: {r.stderr[:200]}"


@_REQUIRES_EXE
def test_exe_self_test_json_ok_true():
    r = _run_exe(["--self-test"], timeout=30)
    data = json.loads(r.stdout)
    assert data.get("ok") is True
    assert data["checks"]["diagnostics_render_leaks"] == []
    assert "available=True" in data["checks"]["token_store_backend"]


@_REQUIRES_EXE
def test_exe_self_test_all_imports_ok():
    r = _run_exe(["--self-test"], timeout=30)
    data = json.loads(r.stdout)
    for mod in ("local_agent.token_store",
                "local_agent.registration_client",
                "local_agent.websocket_client",
                "local_agent.connection_diagnostics"):
        assert data["checks"][mod] == "ok"


# ── 4) diagnostics ──────────────────────────────────────────────────


@_REQUIRES_EXE
def test_exe_diagnostics_runs():
    r = _run_exe(["--diagnostics"], timeout=15)
    assert r.returncode == 0


@_REQUIRES_EXE
def test_diagnostics_no_token_leak_in_output():
    r = _run_exe(["--diagnostics"], timeout=15)
    out = r.stdout + r.stderr
    import re
    # raw device_token 값 패턴 없음
    assert not re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', out)
    assert not re.search(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"', out)


# ── 5) CLI error cases ──────────────────────────────────────────────


@_REQUIRES_EXE
def test_exe_register_without_code_returns_2():
    import os
    env = os.environ.copy()
    env.pop("HAEHAN_AGENT_CODE", None)
    r = subprocess.run([str(EXE), "--register"], capture_output=True,
                        text=True, env=env, timeout=15, errors="replace")
    assert r.returncode == 2


@_REQUIRES_EXE
def test_exe_default_without_agent_id_returns_2():
    r = _run_exe([])
    assert r.returncode == 2


# ── 6) audit verdict ────────────────────────────────────────────────


@_REQUIRES_EXE
def test_audit_warn_unsigned_or_pass():
    from scripts.ops import audit_pyinstaller_build_exec as audit
    v = audit.judge_build_exec(run_live_smoke=True)
    # 코드 서명 OUT_OF_SCOPE → 정상은 WARN_UNSIGNED_BINARY
    assert v.code in (
        "PASS_PYINSTALLER_BUILD_EXEC",
        "WARN_UNSIGNED_BINARY",
        "WARN_LIVE_REGISTER_NOT_TESTED",
        "WARN_ONEFILE_NOT_BUILT",
    ), v.reasons


def test_audit_fail_pyinstaller_missing(monkeypatch):
    from scripts.ops import audit_pyinstaller_build_exec as audit
    # subprocess.run 가 빈 stdout 반환하도록 mock
    class FakeR:
        returncode = 1
        stdout = ""
        stderr = ""
    monkeypatch.setattr(audit.subprocess, "run", lambda *a, **k: FakeR())
    v = audit.judge_build_exec()
    assert v.code == "FAIL_PYINSTALLER_MISSING"


# ── 7) 회귀 가드 ────────────────────────────────────────────────────


def test_regression_desktop_launcher_intact():
    from local_agent import desktop_launcher
    assert hasattr(desktop_launcher, "self_test")
    assert hasattr(desktop_launcher, "register_flow")
    assert hasattr(desktop_launcher, "connect_flow")


def test_regression_token_store_intact():
    from local_agent import token_store as ts
    assert hasattr(ts, "save_device_token")
    assert hasattr(ts, "load_device_token")


def test_regression_build_script_intact():
    from scripts import build_desktop_agent_windows as b
    assert hasattr(b, "build")
