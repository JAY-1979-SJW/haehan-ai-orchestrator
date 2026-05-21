"""tests/test_desktop_webview_release_install.py

DESKTOP_WEBVIEW_RELEASE_INSTALL_01 단위 테스트.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from unittest import mock
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "inspection" / "desktop_webview_release_install"
RUNTIME_REPORT = OUT_DIR / "runtime_smoke_report.json"
CHECKSUMS = OUT_DIR / "checksums.json"
DIST_DIR = ROOT / "dist" / "HaehanAI-Desktop"

_SECRET_RE = re.compile(
    r"(device_token|registration_code|api[_\-]?key|authorization|cookie|session|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


# ── 1. exe 존재 ───────────────────────────────────────────────────────────────

def test_exe_exists():
    exe = DIST_DIR / "HaehanAI-Desktop.exe"
    assert exe.exists(), "HaehanAI-Desktop.exe 없음"


def test_internal_exists():
    internal = DIST_DIR / "_internal"
    assert internal.exists(), "_internal 폴더 없음"


def test_ui_dist_bundled():
    ui = DIST_DIR / "_internal" / "desktop" / "ui_dist" / "index.html"
    assert ui.exists(), "번들된 ui_dist/index.html 없음"


# ── 2. zip 파일 존재 ──────────────────────────────────────────────────────────

def test_zip_exists():
    zips = list((ROOT / "dist").glob("HaehanAI-Desktop-*.zip"))
    assert zips, "배포 zip 없음 — audit 먼저 실행하세요"


def test_zip_contains_exe():
    zips = list((ROOT / "dist").glob("HaehanAI-Desktop-*.zip"))
    if not zips:
        import pytest; pytest.skip("zip 미생성")
    with zipfile.ZipFile(zips[-1]) as zf:
        names = zf.namelist()
    assert any("HaehanAI-Desktop.exe" in n for n in names), "zip에 exe 없음"


def test_zip_contains_internal():
    zips = list((ROOT / "dist").glob("HaehanAI-Desktop-*.zip"))
    if not zips:
        import pytest; pytest.skip("zip 미생성")
    with zipfile.ZipFile(zips[-1]) as zf:
        names = zf.namelist()
    assert any("_internal" in n for n in names), "zip에 _internal 없음"


def test_zip_no_env_file():
    zips = list((ROOT / "dist").glob("HaehanAI-Desktop-*.zip"))
    if not zips:
        import pytest; pytest.skip("zip 미생성")
    with zipfile.ZipFile(zips[-1]) as zf:
        names = zf.namelist()
    assert not any(".env" in n for n in names), "zip에 .env 포함됨"


def test_zip_no_source_code():
    zips = list((ROOT / "dist").glob("HaehanAI-Desktop-*.zip"))
    if not zips:
        import pytest; pytest.skip("zip 미생성")
    with zipfile.ZipFile(zips[-1]) as zf:
        names = zf.namelist()
    assert not any("node_modules" in n for n in names), "zip에 node_modules 포함됨"


# ── 3. checksum ───────────────────────────────────────────────────────────────

def test_checksums_exist():
    if not CHECKSUMS.exists():
        import pytest; pytest.skip("checksums 미생성")
    data = json.loads(CHECKSUMS.read_text(encoding="utf-8"))
    assert "exe_sha256" in data
    assert "zip_sha256" in data
    assert len(data["exe_sha256"]) == 64, "exe SHA256 형식 오류"
    assert len(data["zip_sha256"]) == 64, "zip SHA256 형식 오류"


# ── 4. report schema ──────────────────────────────────────────────────────────

def test_runtime_report_schema():
    if not RUNTIME_REPORT.exists():
        import pytest; pytest.skip("runtime_smoke_report 미생성")
    r = json.loads(RUNTIME_REPORT.read_text(encoding="utf-8"))
    required = ["run_at", "task_id", "exe_exists", "internal_exists",
                "zip", "runtime_smoke", "final_verdict", "verdicts"]
    for k in required:
        assert k in r, f"'{k}' 누락"
    assert r["task_id"] == "DESKTOP_WEBVIEW_RELEASE_INSTALL_01"


def test_zip_report_schema():
    if not RUNTIME_REPORT.exists():
        import pytest; pytest.skip("runtime_smoke_report 미생성")
    r = json.loads(RUNTIME_REPORT.read_text(encoding="utf-8"))
    zip_r = r["zip"]
    assert "ok" in zip_r
    assert "verdict" in zip_r
    if zip_r["ok"]:
        assert "zip_sha256" in zip_r
        assert "exe_sha256" in zip_r
        assert "zip_size_mb" in zip_r


def test_install_smoke_report_schema():
    if not RUNTIME_REPORT.exists():
        import pytest; pytest.skip("runtime_smoke_report 미생성")
    r = json.loads(RUNTIME_REPORT.read_text(encoding="utf-8"))
    smoke = r["runtime_smoke"]
    assert "ok" in smoke
    assert "verdict" in smoke


# ── 5. secret leak detection ──────────────────────────────────────────────────

def test_no_secret_in_runtime_report():
    if not RUNTIME_REPORT.exists():
        import pytest; pytest.skip("runtime_smoke_report 미생성")
    text = RUNTIME_REPORT.read_text(encoding="utf-8")
    m = _SECRET_RE.search(text)
    assert not m, f"runtime_smoke_report에 secret 노출"


def test_no_secret_in_checksums():
    if not CHECKSUMS.exists():
        import pytest; pytest.skip("checksums 미생성")
    text = CHECKSUMS.read_text(encoding="utf-8")
    m = _SECRET_RE.search(text)
    assert not m, f"checksums에 secret 노출"


def test_no_secret_in_install_doc():
    doc = ROOT / "docs" / "ops" / "desktop_webview_release_install.md"
    if not doc.exists():
        import pytest; pytest.skip("설치 문서 없음")
    text = doc.read_text(encoding="utf-8")
    m = _SECRET_RE.search(text)
    assert not m, f"설치 문서에 secret 노출"


# ── 6. audit verdict 분기 ────────────────────────────────────────────────────

def test_verdict_fail_exe_missing():
    from scripts.ops.audit_desktop_webview_release_install import build_zip
    with mock.patch("scripts.ops.audit_desktop_webview_release_install.DIST_DIR",
                    ROOT / "dist" / "__nonexistent__"):
        r = build_zip()
    assert not r["ok"]
    assert r["verdict"] == "FAIL_EXE_MISSING"


def test_verdict_fail_secret_leak():
    from scripts.ops.audit_desktop_webview_release_install import check_secret_leak
    r = check_secret_leak({"data": "device_token=abc123"})
    assert not r["ok"]
    assert r["verdict"] == "FAIL_SECRET_LEAK"


def test_verdict_ok_clean():
    from scripts.ops.audit_desktop_webview_release_install import check_secret_leak
    r = check_secret_leak({"agent_id": "la-xxx", "ok": True})
    assert r["ok"]
    assert r["verdict"] == "OK"


# ── 7. 설치 문서 존재 ─────────────────────────────────────────────────────────

def test_install_doc_exists():
    doc = ROOT / "docs" / "ops" / "desktop_webview_release_install.md"
    assert doc.exists(), "설치 문서 없음"
    text = doc.read_text(encoding="utf-8")
    assert "SmartScreen" in text
    assert "8765" in text
    assert "에이전트 등록" in text


# ── 8. approval 패널 UI 완성 확인 ─────────────────────────────────────────────

def test_approval_panel_has_actions():
    panels = ROOT / "desktop" / "ui" / "src" / "components" / "panels" / "Panels.tsx"
    src = panels.read_text(encoding="utf-8")
    assert "handleApprove" in src, "승인 핸들러 없음"
    assert "handleReject" in src, "거부 핸들러 없음"
    assert "showActions={true}" in src or "showActions" in src


# ── 9. 회귀 ──────────────────────────────────────────────────────────────────

def test_regression_ui_assets():
    dist = ROOT / "desktop" / "ui_dist"
    assert (dist / "index.html").exists()
    js = list((dist / "assets").glob("index-*.js"))
    assert js, "JS asset 없음"


def test_regression_local_server_url():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import BASE_URL
    assert "127.0.0.1" in BASE_URL and "8765" in BASE_URL


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
