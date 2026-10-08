"""instagram_dm_router 계약 스모크 — 외부 호출 0, DB는 tmp_path."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.instagram import instagram_dm_db as db
from ai_orchestrator.connectors.instagram import instagram_dm_router as mod
from ai_orchestrator.connectors.instagram import instagram_dm_rule_engine as engine


def _rule(**kw):
    base = {
        "id": "r1",
        "name": "n",
        "scope_type": "ALL_MEDIA",
        "media_id": None,
        "keywords": ["가격"],
        "exclusion_keywords": [],
        "priority": 100,
        "enabled": True,
        "reply_message": "안녕 {{username}} {{keyword}} {{other}}",
    }
    return {**base, **kw}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "ig.db")
    db.init_db()
    app = FastAPI()
    app.include_router(mod.instagram_dm_router)
    return TestClient(app)


@pytest.fixture()
def account_id(client):
    return db.upsert_account(
        instagram_user_id="u1", username="acc", account_type="BUSINESS", encrypted_access_token="keyring"
    )


def _ev(text, rules, enabled=True, media_id=None):
    return engine.evaluate(account_automation_enabled=enabled, comment_text=text, media_id=media_id, rules=rules)


def test_engine_match_and_nomatch():
    r = _ev("가격 문의", [_rule()])
    assert r.matched and r.matched_keyword == "가격" and r.reason == "MATCHED"
    r = _ev("hello", [_rule()])
    assert not r.matched and r.reason == "NO_MATCH"
    assert not _ev("가격 광고", [_rule(exclusion_keywords=["광고"])]).matched


def test_engine_disabled_and_empty():
    assert _ev("가격", [_rule()], enabled=False).reason == "ACCOUNT_DISABLED"
    assert _ev("  ", [_rule()]).reason == "EMPTY_TEXT"


def test_render_template_allowed_and_unknown_vars():
    out = engine.render_template("{{username}}/{{ keyword }}/{{other}}", username="kim", keyword="가격")
    assert out == "kim/가격/{{other}}"


def test_simulate_response_keys(client, account_id):
    db.create_rule(
        instagram_account_id=account_id,
        name="r",
        scope_type="ALL_MEDIA",
        media_id=None,
        reply_message="{{username}}님 {{keyword}}",
        keywords=["가격"],
        exclusion_keywords=[],
        priority=1,
        enabled=True,
    )
    res = client.post(
        "/instagram-dm/rules/simulate", json={"instagram_account_id": account_id, "comment_text": "가격?"}
    )
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"matched", "reason", "matched_rule", "matched_keyword", "preview_dm"}
    assert body["matched"] is True and body["preview_dm"] == "테스트유저님 가격"
    res = client.post("/instagram-dm/rules/simulate", json={"instagram_account_id": account_id, "comment_text": "zzz"})
    assert res.json()["matched"] is False and res.json()["preview_dm"] is None


def test_simulate_unknown_account_404(client):
    res = client.post("/instagram-dm/rules/simulate", json={"instagram_account_id": "nope", "comment_text": "x"})
    assert res.status_code == 404


def test_automation_toggle(client, account_id):
    res = client.post(f"/instagram-dm/accounts/{account_id}/automation", json={"enabled": True})
    assert res.json() == {"automation_enabled": True}
    assert client.post("/instagram-dm/accounts/nope/automation", json={"enabled": True}).status_code == 404


def test_webhook_verify_token(client, monkeypatch):
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "tok")
    q = "/instagram-dm/webhooks/instagram?hub.mode=subscribe&hub.challenge=abc&hub.verify_token="
    assert client.get(q + "bad").status_code == 403
    ok = client.get(q + "tok")
    assert ok.status_code == 200 and ok.text == "abc"


def test_webhook_verify_rejects_when_env_unset(client, monkeypatch):
    monkeypatch.delenv("META_WEBHOOK_VERIFY_TOKEN", raising=False)
    res = client.get("/instagram-dm/webhooks/instagram?hub.mode=subscribe&hub.challenge=abc&hub.verify_token=")
    assert res.status_code == 403


def test_webhook_receive_bad_signature_401(client, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "s")
    res = client.post("/instagram-dm/webhooks/instagram", content=b"{}", headers={"X-Hub-Signature-256": "sha256=00"})
    assert res.status_code == 401
