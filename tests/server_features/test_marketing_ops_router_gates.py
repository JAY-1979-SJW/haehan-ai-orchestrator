"""마케팅 운영실(marketing_ops_router) 게이트 — 기능 스위치 + publish-blog R2 승인.

시험 범위(지휘창 지시, 2026-10-07): 꺼짐이면 403(스위치), 켜짐인데 승인 문구가
없으면 403(승인), 켜짐이고 문구가 맞으면 write_post 호출(mock)까지 통과.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.marketing import marketing_ops_router as M
from ai_orchestrator.marketing import marketing_ops_settings as S
from scripts.common.gate import CONFIRM_TEXTS
from tools.gates.auth import get_current_user

BLOG_PUBLISH_CONFIRM_TEXT = CONFIRM_TEXTS["blog_publish"]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "_FILE", tmp_path / "settings.json")
    app = FastAPI()
    app.include_router(M.marketing_ops_router)
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": "owner"}
    return TestClient(app)


def _toggle(api, enabled: bool):
    r = api.post("/naver/marketing-ops/settings/toggle", json={"enabled": enabled})
    assert r.status_code == 200


def test_switch_off_blocks_everything_but_state_and_toggle(api):
    assert S.is_enabled() is False  # 기본값 꺼짐
    r = api.post("/naver/marketing-ops/approve-channel", json={"package_id": "x", "channel": "youtube"})
    assert r.status_code == 403
    assert r.json()["detail"] == "설정에서 마케팅 운영을 켜세요"


def test_state_and_toggle_work_while_off(api):
    r = api.get("/naver/marketing-ops/state")
    assert r.status_code == 200
    r = api.get("/naver/marketing-ops/settings")
    assert r.status_code == 200 and r.json()["enabled"] is False
    _toggle(api, True)
    assert S.is_enabled() is True


def test_publish_blog_blocked_when_switch_off(api):
    r = api.post("/naver/marketing-ops/publish-blog", json={"package_id": "x", "confirmed": True})
    assert r.status_code == 403
    assert r.json()["detail"] == "설정에서 마케팅 운영을 켜세요"


def test_publish_blog_blocked_without_send_confirm_when_switch_on(api):
    _toggle(api, True)
    r = api.post("/naver/marketing-ops/publish-blog", json={"package_id": "x", "confirmed": True})
    assert r.status_code == 403


def test_publish_blog_blocked_response_does_not_leak_approval_phrase(api):
    # R2d-1(f2a72857)이 send_approval 어댑터의 차단 detail에서 승인 문구를 뺀 뒤
    # 일반 단언으로 전환(2026-10-07). 이전에는 detail에 문구가 그대로 노출돼 xfail이었음.
    _toggle(api, True)
    r = api.post("/naver/marketing-ops/publish-blog", json={"package_id": "x", "confirmed": True})
    assert r.status_code == 403
    assert BLOG_PUBLISH_CONFIRM_TEXT not in r.json()["detail"]


def test_publish_blog_blocked_with_wrong_send_confirm(api):
    _toggle(api, True)
    r = api.post(
        "/naver/marketing-ops/publish-blog",
        json={"package_id": "x", "confirmed": True, "send_confirm": "WRONG"},
    )
    assert r.status_code == 403


def test_publish_blog_confirmed_false_short_circuits_before_gate(api):
    _toggle(api, True)
    r = api.post("/naver/marketing-ops/publish-blog", json={"package_id": "x", "confirmed": False})
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "발행은 confirmed=true 확인이 필요합니다 (외부 공개)"}


def test_publish_blog_passes_gate_with_correct_send_confirm(api):
    _toggle(api, True)
    with patch("scripts.browser.cdp.connection.run_on_browser_thread", return_value={"ok": True, "log_no": "t1"}):
        r = api.post(
            "/naver/marketing-ops/publish-blog",
            json={"package_id": "nope", "confirmed": True, "send_confirm": BLOG_PUBLISH_CONFIRM_TEXT},
        )
    # 게이트를 통과해 다음 단계(패키지 조회)까지 도달 — 403이 아님이 핵심
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "패키지를 찾을 수 없습니다"}


def test_approve_channel_blocked_when_switch_off(api):
    r = api.post("/naver/marketing-ops/approve-channel", json={"package_id": "x", "channel": "youtube"})
    assert r.status_code == 403
