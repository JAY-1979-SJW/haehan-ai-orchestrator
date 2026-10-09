"""tests/test_session_monitor.py — 세션 감시 모듈 계약 테스트."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.login_session_monitor import (  # noqa: E402
    _ALERT_STATUSES,
    SITES,
    SessionState,
    _report,
    check_site,
)

# ── 기본 계약 ──────────────────────────────────────────────────────────────────


def test_sites_define_required_keys() -> None:
    required = {"key", "label", "url_hints", "logged_in_js", "login_url"}
    for site in SITES:
        assert required <= set(site), f"{site['key']} missing keys"


def test_sites_cover_naver_google_smartstore() -> None:
    keys = {s["key"] for s in SITES}
    assert "naver" in keys
    assert "google" in keys
    assert "smartstore" in keys


def test_alert_statuses_cover_session_expired_and_login_required() -> None:
    assert "SESSION_EXPIRED" in _ALERT_STATUSES
    assert "LOGIN_REQUIRED" in _ALERT_STATUSES
    assert "CHALLENGE" in _ALERT_STATUSES


def test_session_state_to_dict_has_no_cookie_value() -> None:
    s = SessionState(
        key="naver",
        label="네이버",
        status="LOGGED_IN",
        detail="세션 정상",
        href="https://www.naver.com",
        title="네이버",
        has_session_cookie=True,
        checked_at="2026-01-01T00:00:00Z",
    )
    d = s.to_dict()
    # 쿠키 값 원문 없음 — bool만 있어야 함
    assert isinstance(d["has_session_cookie"], bool)
    for v in d.values():
        if isinstance(v, str):
            assert "NID_SES=" not in v
            assert "Bearer " not in v


# ── check_site: NO_TAB ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_site_returns_no_tab_when_no_matching_target() -> None:
    site = next(s for s in SITES if s["key"] == "naver")
    result = await check_site(site, targets=[])
    assert result.status == "NO_TAB"
    assert result.has_session_cookie is False


# ── check_site: LOGGED_IN ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_site_logged_in_when_session_cookie_and_logout_link() -> None:
    site = next(s for s in SITES if s["key"] == "naver")
    fake_tab = {
        "type": "page",
        "url": "https://www.naver.com/",
        "title": "네이버",
        "id": "abc123",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/abc123",
    }
    fake_data = {
        "href": "https://www.naver.com/",
        "title": "네이버",
        "has_session_cookie": True,
        "has_logout_link": True,
        "has_mypage": True,
        "has_login_form": False,
        "challenge": False,
        "login_error": False,
    }
    with patch("tools.login_session_monitor._eval_js", AsyncMock(return_value=fake_data)):
        result = await check_site(site, targets=[fake_tab])
    assert result.status == "LOGGED_IN"
    assert result.has_session_cookie is True


# ── check_site: SESSION_EXPIRED ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_site_session_expired_when_no_cookie() -> None:
    site = next(s for s in SITES if s["key"] == "google")
    fake_tab = {
        "type": "page",
        "url": "https://www.google.com/",
        "title": "Google",
        "id": "def456",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/def456",
    }
    fake_data = {
        "href": "https://www.google.com/",
        "title": "Google",
        "has_session_cookie": False,
        "has_account_menu": False,
        "has_login_form": False,
        "has_pw_form": False,
        "challenge": False,
        "login_error": False,
    }
    with patch("tools.login_session_monitor._eval_js", AsyncMock(return_value=fake_data)):
        result = await check_site(site, targets=[fake_tab])
    assert result.status == "SESSION_EXPIRED"
    assert result.status in _ALERT_STATUSES


# ── check_site: LOGIN_REQUIRED ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_site_login_required_when_login_form_detected() -> None:
    site = next(s for s in SITES if s["key"] == "smartstore")
    fake_tab = {
        "type": "page",
        "url": "https://sell.smartstore.naver.com/",
        "title": "스마트스토어",
        "id": "ghi789",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/ghi789",
    }
    fake_data = {
        "href": "https://sell.smartstore.naver.com/",
        "title": "로그인",
        "has_session_cookie": False,
        "has_logout_link": False,
        "has_dashboard": False,
        "has_login_form": True,
        "challenge": False,
    }
    with patch("tools.login_session_monitor._eval_js", AsyncMock(return_value=fake_data)):
        result = await check_site(site, targets=[fake_tab])
    assert result.status == "LOGIN_REQUIRED"
    assert result.status in _ALERT_STATUSES


# ── check_site: CHALLENGE ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_site_challenge_when_2fa_detected() -> None:
    site = next(s for s in SITES if s["key"] == "naver")
    fake_tab = {
        "type": "page",
        "url": "https://nid.naver.com/login/sso/finalize.nhn",
        "title": "추가 인증",
        "id": "jkl000",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/jkl000",
    }
    fake_data = {
        "href": "https://nid.naver.com/login/sso/finalize.nhn",
        "title": "추가 인증",
        "has_session_cookie": False,
        "has_logout_link": False,
        "has_mypage": False,
        "has_login_form": False,
        "challenge": True,
        "login_error": False,
    }
    with patch("tools.login_session_monitor._eval_js", AsyncMock(return_value=fake_data)):
        result = await check_site(site, targets=[fake_tab])
    assert result.status == "CHALLENGE"
    assert result.status in _ALERT_STATUSES


# ── _report: 파일 저장 + 민감정보 미포함 ────────────────────────────────────────


def test_report_writes_json_without_cookie_values(tmp_path, monkeypatch) -> None:
    import tools.login_session_monitor as mod

    monkeypatch.setattr(mod, "OUTPUT_PATH", tmp_path / "out.json")

    states = [
        SessionState(
            key="naver",
            label="네이버",
            status="LOGGED_IN",
            detail="세션 정상",
            href="https://www.naver.com",
            title="네이버",
            has_session_cookie=True,
            checked_at="2026-01-01T00:00:00Z",
        ),
        SessionState(
            key="google",
            label="Google",
            status="SESSION_EXPIRED",
            detail="세션 쿠키 없음",
            href="https://www.google.com",
            title="Google",
            has_session_cookie=False,
            checked_at="2026-01-01T00:00:00Z",
        ),
    ]
    _report(states, elapsed=0.5)

    raw = (tmp_path / "out.json").read_text(encoding="utf-8")
    assert "NID_SES=" not in raw
    assert "Bearer " not in raw
    d = json.loads(raw)
    assert d["alert"] is True  # SESSION_EXPIRED 때문에
    assert len(d["sites"]) == 2


def test_report_alert_false_when_all_logged_in(tmp_path, monkeypatch) -> None:
    import tools.login_session_monitor as mod

    monkeypatch.setattr(mod, "OUTPUT_PATH", tmp_path / "out.json")

    states = [
        SessionState(
            key=s["key"],
            label=s["label"],
            status="LOGGED_IN",
            detail="세션 정상",
            href="https://example.com",
            title="OK",
            has_session_cookie=True,
            checked_at="2026-01-01T00:00:00Z",
        )
        for s in SITES
    ]
    _report(states, elapsed=0.1)
    d = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert d["alert"] is False
