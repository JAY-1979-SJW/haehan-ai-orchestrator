"""HAEHAN_CONSENT_DIALOG_01 회귀 테스트.

검증:
    - consent flow 파일 입출력
    - dialog runner 주입
    - HAEHAN_SKIP_GUI 동작
    - decline 시 진입 차단
    - secret leak 없음
    - main_launcher 연결
    - desktop.consent 공유 모듈 (legacy UI 제거 후 이전됨)
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
    from desktop import consent as con

    def _fake_path():
        return fake_data / "consent.json"

    monkeypatch.setattr(con, "_consent_file_path", _fake_path)

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
    allowed = {"agreed", "agreed_at", "version", "scope"}
    assert set(data.keys()).issubset(allowed)
    lowered = raw.lower()
    for sk in SECRET_KEYS:
        assert sk not in lowered, f"consent.json 에 금칙어 '{sk}' 발견"


def test_skip_gui_no_tkinter(isolated_consent, monkeypatch):
    """HAEHAN_SKIP_GUI=1 + runner 미주입 → 실제 tk 호출 없음, 거부 처리."""
    monkeypatch.setenv("HAEHAN_SKIP_GUI", "1")
    from desktop import consent as con

    called = {"tk": False}

    def _boom():
        called["tk"] = True
        raise AssertionError("tkinter should not be invoked under SKIP_GUI")

    monkeypatch.setattr(con, "_default_tk_dialog_runner", _boom)
    agreed = con.check_consent()
    assert agreed is False
    assert called["tk"] is False


def test_main_launcher_blocks_on_decline(isolated_consent, monkeypatch):
    """main() 흐름에서 동의 거부 시 진입 차단 코드 반환."""
    monkeypatch.setenv("HAEHAN_SKIP_GUI", "1")
    from desktop import main_launcher
    rc = main_launcher.main(["--tray"])
    assert rc == 4


def test_main_launcher_consent_linkage_source():
    """main_launcher 가 desktop.consent 를 사용하는지 확인."""
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    assert "from desktop.consent import check_consent" in src


def test_no_secret_in_consent_prompt():
    from desktop import consent as con
    txt = con.CONSENT_PROMPT_TEXT.lower()
    for sk in SECRET_KEYS:
        assert sk not in txt, f"prompt 에 금칙어 '{sk}' 포함"


def test_consent_module_exists():
    """desktop/consent.py 공유 모듈이 존재한다."""
    assert (ROOT / "desktop" / "consent.py").exists()


def test_legacy_webview_not_referenced_in_consent_flow():
    """main_launcher 의 consent flow 가 webview_app_pywebview 를 더 이상 참조하지 않는다."""
    src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
    # run_consent_flow 함수 부분만 확인
    in_func, lines = False, []
    for line in src.splitlines():
        if "def run_consent_flow" in line:
            in_func = True
        if in_func:
            lines.append(line)
            if line.strip() == "" and len(lines) > 3:
                break
    func_src = "\n".join(lines)
    assert "webview_app_pywebview" not in func_src
