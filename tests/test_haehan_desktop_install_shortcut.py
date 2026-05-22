"""HAEHAN_DESKTOP_INSTALL_SHORTCUT_01 회귀 테스트."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.haehan import create_desktop_shortcut as shortcut  # noqa: E402


SECRET_TOKENS = ("device_token", "registration_code", "bearer", "cookie",
                 "authorization", "api_key", "password", "secret")


def test_official_exe_detection():
    v = shortcut.verify_official_exe(ROOT)
    assert v.ok, f"공식 exe 검증 실패: {v.reason}"
    assert v.exe_path.endswith("HaehanAI-Desktop.exe")
    assert v.sha256_actual == v.sha256_expected
    assert len(v.sha256_actual) == 64


def test_official_exe_sha_matches_baseline():
    expected = shortcut.baseline_sha256(ROOT)
    assert expected and len(expected) == 64
    exe = ROOT / shortcut.OFFICIAL_EXE_REL
    actual = shortcut.file_sha256(exe)
    assert actual == expected


def test_sha_mismatch_blocks(tmp_path, monkeypatch):
    """exe 가 baseline SHA 와 다르면 verify 가 sha_mismatch 반환."""
    # 가짜 root 구성: 베이스라인 문서는 진짜 ROOT 의 SHA, exe 는 깨뜨림
    fake_exe_dir = tmp_path / "dist" / "HaehanAI-Desktop"
    fake_exe_dir.mkdir(parents=True)
    fake_exe = fake_exe_dir / "HaehanAI-Desktop.exe"
    fake_exe.write_bytes(b"tampered")

    fake_doc = tmp_path / "docs" / "release"
    fake_doc.mkdir(parents=True)
    real_sha = shortcut.baseline_sha256(ROOT)
    (fake_doc / "HAEHAN_DESKTOP_RELEASE_BASELINE_01.md").write_text(
        f"SHA-256\n`{real_sha}`\n", encoding="utf-8")

    v = shortcut.verify_official_exe(tmp_path)
    assert not v.ok
    assert v.reason == "sha_mismatch"


def test_legacy_agent_target_rejected():
    assert shortcut.is_legacy_target(r"C:\foo\dist\HaehanAI-Agent\HaehanAI-Agent.exe")
    assert shortcut.is_legacy_target("dist/HaehanAI-Agent/HaehanAI-Agent.exe")


def test_legacy_electron_target_rejected():
    assert shortcut.is_legacy_target(r"C:\repo\desktop\electron\main.js")
    assert shortcut.is_legacy_target("desktop/electron/HaehanAI Agent.exe")


def test_legacy_webview_app_target_rejected():
    assert shortcut.is_legacy_target("desktop/webview_app.py")
    assert shortcut.is_legacy_target(r"C:\repo\desktop\webview_app.py")


def test_official_target_not_legacy():
    assert not shortcut.is_legacy_target(
        "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe")
    assert not shortcut.is_legacy_target(
        r"C:\repo\dist\HaehanAI-Desktop\HaehanAI-Desktop.exe")


def test_create_shortcut_blocks_legacy(tmp_path):
    fake_legacy = tmp_path / "HaehanAI-Agent.exe"
    fake_legacy.write_bytes(b"x")
    r = shortcut.create_shortcut(
        target_exe=fake_legacy, lnk_path=tmp_path / "x.lnk", dry_run=True,
    )
    assert not r["ok"]
    assert r["reason"] == "legacy_target_rejected"
    assert not r["created"]


def test_desktop_dry_run(monkeypatch, tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr(shortcut, "desktop_dir", lambda: desktop)
    rc = shortcut.main(["--desktop", "--dry-run"])
    assert rc == 0
    assert not (desktop / shortcut.SHORTCUT_NAME).exists()


def test_start_menu_dry_run(monkeypatch, tmp_path):
    sm = tmp_path / "StartMenu" / "HaehanAI"
    monkeypatch.setattr(shortcut, "start_menu_dir", lambda: sm)
    rc = shortcut.main(["--start-menu", "--dry-run"])
    assert rc == 0
    assert not sm.exists() or not (sm / shortcut.SHORTCUT_NAME).exists()


def test_main_no_option_errors():
    rc = shortcut.main([])
    assert rc == 1


def test_main_exe_override_rejects_legacy(tmp_path, capsys):
    fake = tmp_path / "dist" / "HaehanAI-Agent" / "HaehanAI-Agent.exe"
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"x")
    rc = shortcut.main(["--desktop", "--exe", str(fake), "--dry-run"])
    assert rc == 2
    out = capsys.readouterr()
    assert "legacy" in (out.err + out.out).lower()


def test_no_secret_in_source():
    src = (ROOT / "scripts/haehan/create_desktop_shortcut.py").read_text(encoding="utf-8")
    low = src.lower()
    import re
    leaks = [t for t in SECRET_TOKENS
             if re.search(rf"\b{t}\s*[=:]\s*['\"][^'\"\n]+['\"]", low)]
    assert leaks == [], f"shortcut 스크립트에 secret 값 노출: {leaks}"


def test_detect_legacy_runs():
    """탐지 함수가 예외 없이 list 반환."""
    items = shortcut.detect_legacy_shortcuts()
    assert isinstance(items, list)
