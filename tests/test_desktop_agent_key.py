"""데스크톱 로컬 에이전트 키 — 라이선스 없이 시작(대표님 결정 2026-10-08).

Electron 이 이 PC 전용 키를 HAEHAN_DESKTOP_AGENT_KEY 로 넘기면, 로컬 데스크톱 조건(AUTH_ENABLED=false +
HAEHAN_DESKTOP=1 + loopback)에서만 그 키로 에이전트 접속을 인정한다. 서버 모드에서는 열리지 않는다.
"""

import pytest

from ai_orchestrator.connectors.smartstore import license as lic

KEY = "desktop-" + "a" * 48


@pytest.fixture
def desktop_env(monkeypatch):
    monkeypatch.setenv("HAEHAN_DESKTOP_AGENT_KEY", KEY)
    monkeypatch.setattr(lic, "desktop_owner_bootstrap_allowed", lambda: True)
    monkeypatch.setattr(lic, "_load", lambda: {})


def test_desktop_key_is_accepted_in_desktop_mode(desktop_env):
    ok, rec, reason = lic.verify(KEY)
    assert ok and reason == "ok"
    assert rec is not None and rec["plan"] == "desktop"


def test_other_key_is_rejected_in_desktop_mode(desktop_env):
    ok, _rec, reason = lic.verify("desktop-" + "b" * 48)
    assert not ok and reason == "invalid_key"


def test_desktop_key_is_rejected_outside_desktop_mode(desktop_env, monkeypatch):
    monkeypatch.setattr(lic, "desktop_owner_bootstrap_allowed", lambda: False)
    ok, _rec, reason = lic.verify(KEY)
    assert not ok and reason == "invalid_key"


def test_short_or_missing_env_key_never_matches(monkeypatch):
    monkeypatch.setattr(lic, "desktop_owner_bootstrap_allowed", lambda: True)
    monkeypatch.setattr(lic, "_load", lambda: {})
    monkeypatch.setenv("HAEHAN_DESKTOP_AGENT_KEY", "short")
    assert lic.verify("short")[0] is False
    monkeypatch.delenv("HAEHAN_DESKTOP_AGENT_KEY")
    assert lic.verify("")[0] is False
