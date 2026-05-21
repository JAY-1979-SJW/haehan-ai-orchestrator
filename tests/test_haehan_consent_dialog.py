"""HAEHAN_CONSENT_DIALOG_01 회귀 테스트.

검증:
    - consent flow 파일 입출력
    - dialog runner 주입
    - HAEHAN_SKIP_GUI 동작
    - decline 시 진입 차단
    - secret leak 없음
    - main_launcher 연결
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


SECRET_KEYS = (
    "token", "device_token", "registration_code", "bearer",
    "cookie", "authorization", "api_key", "password", "secret",
)


@pytest.fixture
def isolated_consent(tmp_path, monkeypatch):
    """consent.json 을 임시 경로로 분리."""
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    from desktop import webview_app_pywebview as web

    def _fake_path():
        return fake_data / "consent.json"

    monkeypatch.setattr(web, "_consent_file_path", _fake_path)

    # main_launcher 의 app_root 도 임시로 → check_consent_hook 동기화
    from desktop import main_launcher
    monkeypatch.setattr(main_launcher, "app_root", lambda: tmp_path)

    yield fake_data / "consent.json"


def test_consent_missing_needs_prompt(isolated_consent):
    from desktop import main_launcher
    state = main_launcher.check_consent_hook()
    assert state["agreed"] is False
    assert state["needs_prompt"] is True
    assert state["source"] == "missing"


def test_consent_agreed_true_passes(isolated_consent):
    isolated_consent.write_text(json.dumps(
        {"agreed": True, "agreed_at": "2026-05-22T00:00:00",
         "version": "1", "scope": "haehan-desktop-default"}
    ), encoding="utf-8")
    from desktop import main_launcher
    state = main_launcher.check_consent_hook()
    assert state["agreed"] is True
    assert state["needs_prompt"] is False


def test_consent_agreed_false_blocks(isolated_consent, monkeypatch):
    isolated_consent.write_text(json.dumps(
        {"agreed": False, "agreed_at": "x", "version": "1", "scope": "x"}
    ), encoding="utf-8")
    from desktop import main_launcher
    state = main_launcher.check_consent_hook()
    assert state["agreed"] is False


def test_consent_corrupted_json_safely_blocks(isolated_consent):
    isolated_consent.write_text("{not valid json", encoding="utf-8")
    from desktop import main_launcher
    state = main_launcher.check_consent_hook()
    assert state["agreed"] is False
    assert state["needs_prompt"] is True


def test_consent_dialog_runner_inject_agree(isolated_consent):
    from desktop import main_launcher
    result = main_launcher.run_consent_flow(dialog_runner=lambda: True)
    assert result is True
    saved = json.loads(isolated_consent.read_text(encoding="utf-8"))
    assert saved["agreed"] is True
    assert "agreed_at" in saved
    assert saved.get("version") == "1"
    assert saved.get("scope")


def test_consent_dialog_runner_inject_decline(isolated_consent):
    from desktop import main_launcher
    result = main_launcher.run_consent_flow(dialog_runner=lambda: False)
    assert result is False
    saved = json.loads(isolated_consent.read_text(encoding="utf-8"))
    assert saved["agreed"] is False


def test_consent_saved_schema_safe(isolated_consent):
    from desktop import main_launcher
    main_launcher.run_consent_flow(dialog_runner=lambda: True)
    raw = isolated_consent.read_text(encoding="utf-8")
    data = json.loads(raw)
    # 허용 키만 존재
    allowed = {"agreed", "agreed_at", "version", "scope"}
    assert set(data.keys()).issubset(allowed)
    # secret 키 절대 금지
    lowered = raw.lower()
    for sk in SECRET_KEYS:
        assert sk not in lowered, f"consent.json 에 금칙어 '{sk}' 발견"


def test_skip_gui_no_tkinter(isolated_consent, monkeypatch):
    """HAEHAN_SKIP_GUI=1 + runner 미주입 → 실제 tk 호출 없음, 거부 처리."""
    monkeypatch.setenv("HAEHAN_SKIP_GUI", "1")
    from desktop import webview_app_pywebview as web

    called = {"tk": False}

    def _boom():
        called["tk"] = True
        raise AssertionError("tkinter should not be invoked under SKIP_GUI")

    monkeypatch.setattr(web, "_default_tk_dialog_runner", _boom)
    agreed = web._check_consent()
    assert agreed is False
    assert called["tk"] is False


def test_main_launcher_blocks_on_decline(isolated_consent, monkeypatch):
    """main() 흐름에서 동의 거부 시 진입 차단 코드 반환."""
    monkeypatch.setenv("HAEHAN_SKIP_GUI", "1")
    from desktop import main_launcher
    # consent.json 없음 + SKIP_GUI=1 → 차단 코드 4
    rc = main_launcher.main(["--tray"])
    assert rc == 4


def test_main_launcher_consent_linkage_source():
    """audit 가 검사하는 import 라인이 main_launcher 에 실제 존재."""
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    assert "from desktop.webview_app_pywebview import _check_consent" in src


def test_no_secret_in_consent_prompt():
    from desktop import webview_app_pywebview as web
    txt = web.CONSENT_PROMPT_TEXT.lower()
    for sk in SECRET_KEYS:
        assert sk not in txt, f"prompt 에 금칙어 '{sk}' 포함"


def test_protected_files_untouched():
    """tray_app.py / user_settings.py 미수정 확인."""
    import subprocess
    res = subprocess.run(
        ["git", "diff", "--name-only", "HEAD",
         "desktop/tray_app.py", "desktop/user_settings.py"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    changed = [l for l in res.stdout.splitlines() if l.strip()]
    assert changed == [], f"보호 파일 수정 감지: {changed}"
