"""HAEHAN_LEGACY_ENTRYPOINT_GUARD_01 회귀 테스트.

정식 entrypoint = desktop.main_launcher.main 만 인정한다.
legacy Agent/Electron/webview 직접 경로의 재출현·재안내를 차단한다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _code_only(src: str) -> str:
    out, in_doc = [], False
    for line in src.splitlines():
        s = line.lstrip()
        if s.startswith('"""') or s.startswith("'''"):
            cnt = line.count('"""') + line.count("'''")
            if cnt == 2:
                continue
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def test_official_entrypoint_uses_main_launcher():
    src = (ROOT / "scripts/build_desktop_webview_app_windows.py").read_text(encoding="utf-8")
    assert "from desktop.main_launcher import main" in src


def test_official_entrypoint_no_webview_direct():
    code = _code_only(
        (ROOT / "scripts/build_desktop_webview_app_windows.py").read_text(encoding="utf-8")
    )
    assert "from desktop.webview_app_pywebview import main" not in code
    assert "webview_app_pywebview.main(" not in code


def test_no_legacy_dist_resurrected():
    assert not (ROOT / "dist" / "HaehanAI-Agent").exists()


def test_no_legacy_electron_resurrected():
    assert not (ROOT / "desktop" / "electron").exists()


def test_no_ui_dist_backup_resurrected():
    backups = list((ROOT / "desktop").glob("ui_dist_backup_*"))
    assert backups == [], f"ui_dist_backup_* 재출현: {[d.name for d in backups]}"


def test_legacy_webview_app_removed():
    """desktop/webview_app.py 는 legacy UI 제거로 삭제됐다 (HAEHAN-DESKTOP-LEGACY-UI-REMOVAL-01)."""
    assert not (ROOT / "desktop" / "webview_app.py").exists()


def test_legacy_tray_app_removed():
    """desktop/tray_app.py 는 legacy UI 제거로 삭제됐다."""
    assert not (ROOT / "desktop" / "tray_app.py").exists()


def test_legacy_webview_app_pywebview_removed():
    """desktop/webview_app_pywebview.py 는 legacy UI 제거로 삭제됐다."""
    assert not (ROOT / "desktop" / "webview_app_pywebview.py").exists()


def test_legacy_ui_dir_removed():
    """desktop/ui/ React SPA 소스는 legacy UI 제거로 삭제됐다."""
    assert not (ROOT / "desktop" / "ui").exists()


def test_baseline_doc_has_official_exe_and_sha256():
    doc = (ROOT / "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md").read_text(encoding="utf-8")
    assert "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe" in doc
    assert "SHA-256" in doc
    assert re.search(r"[0-9a-f]{64}", doc), "SHA-256 hex 누락"


def test_no_agent_spec_build_guidance_in_ops_docs():
    """ops 문서/스크립트가 HaehanAI-Agent.spec 빌드 명령을 안내하지 않는다."""
    allow = {
        ROOT / "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md",
        ROOT / "scripts/ops/audit_haehan_legacy_entrypoint_guard.py",
        ROOT / "tests/test_haehan_legacy_entrypoint_guard.py",
    }
    pattern = re.compile(
        r"(pyinstaller|PyInstaller)[^\n]{0,80}HaehanAI-Agent\.spec",
        re.IGNORECASE,
    )
    bad = []
    for d in ("docs", "scripts/ops"):
        for p in (ROOT / d).rglob("*"):
            if p in allow or not p.is_file():
                continue
            if p.suffix not in (".md", ".py", ".txt"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if pattern.search(text):
                bad.append(p.relative_to(ROOT).as_posix())
    assert bad == [], f"HaehanAI-Agent.spec 빌드 안내 잔존: {bad}"


def test_no_baseline_secret_value_leak():
    """baseline 문서에 secret 키의 실제 값이 노출되지 않는다."""
    doc = (ROOT / "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md").read_text(encoding="utf-8")
    low = doc.lower()
    tokens = ("device_token", "registration_code", "bearer",
              "cookie", "authorization", "api_key", "password")
    leaks = [
        t for t in tokens
        if re.search(rf"\b{t}\s*[=:]\s*['\"][^'\"\n]+['\"]", low)
    ]
    assert leaks == [], f"baseline 문서 secret 값 노출: {leaks}"
