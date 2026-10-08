"""Instagram DM None 가드(mypy B 결정표 O1-5/9/10) — 가짜 객체만 사용, Meta 호출·실발송 없음."""

from __future__ import annotations

import pytest

from ai_orchestrator.connectors.instagram import instagram_dm_db as db
from ai_orchestrator.connectors.instagram import instagram_dm_router as igmod
from ai_orchestrator.connectors.instagram import instagram_dm_rule_engine as rule_engine
from ai_orchestrator.connectors.instagram import instagram_dm_service as service


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "instagram_dm_guard.db")
    db.init_db()
    return db


def _seed(tmp_db):
    acc = tmp_db.upsert_account(
        instagram_user_id="ig123",
        username="tester",
        account_type="BUSINESS",
        encrypted_access_token="keyring-ref",  # 참조 마커
    )
    tmp_db.set_account_automation_enabled(acc, True)
    tmp_db.create_rule(
        instagram_account_id=acc,
        name="r",
        scope_type="ALL_MEDIA",
        media_id=None,
        reply_message="hi {{username}}",
        keywords=["자료"],
    )
    eid, _ = tmp_db.insert_comment_event_if_new(
        instagram_account_id=acc,
        comment_id="c1",
        media_id=None,
        media_product_type=None,
        commenter_ig_scoped_id="u1",
        commenter_username="user1",
        comment_text="자료 주세요",
        normalized_text="자료 주세요",
        comment_created_at=None,
        raw_payload={},
    )
    return acc, eid


def _matched_without_rule(**_kw):
    return rule_engine.RuleMatchResult(matched=True, rule=None, matched_keyword="k", reason="NO_MATCH")


def test_process_comment_event_rule_none_does_not_send(tmp_db, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_DM_ENABLED", "true")
    monkeypatch.setenv("INSTAGRAM_DM_DRY_RUN", "false")
    acc, eid = _seed(tmp_db)
    calls = []
    monkeypatch.setattr(service, "send_private_reply", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(service.token_store, "load_token", lambda _uid: "fake-token")
    monkeypatch.setattr(service.rule_engine, "evaluate", _matched_without_rule)

    service.process_comment_event(eid, instagram_account_id=acc)  # TypeError 없이 반환

    assert calls == []
    assert tmp_db.list_reply_logs(acc) == []
    ev = next(e for e in tmp_db.list_comment_events(acc, limit=10) if e["id"] == eid)
    assert ev["processing_status"] in ("NO_MATCH", "IGNORED")


def test_process_comment_event_normal_path_still_dry_runs(tmp_db, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_DM_ENABLED", "true")
    monkeypatch.setenv("INSTAGRAM_DM_DRY_RUN", "true")
    acc, eid = _seed(tmp_db)
    calls = []
    monkeypatch.setattr(service, "send_private_reply", lambda *a, **k: calls.append(a))
    service.process_comment_event(eid, instagram_account_id=acc)
    assert calls == []
    assert tmp_db.list_reply_logs(acc)[0]["status"] == "DRY_RUN"


def _client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(igmod.instagram_dm_router)
    monkeypatch.setattr(igmod, "_app_id", lambda: "app")
    monkeypatch.setattr(igmod, "_app_secret", lambda: "secret")
    monkeypatch.setattr(igmod, "_redirect_uri", lambda: "http://localhost/cb")
    monkeypatch.setattr(igmod.time, "time", lambda: 1000.0)
    igmod._oauth_state_add("st-guard")
    return TestClient(app)


def test_oauth_callback_without_short_token_returns_502(monkeypatch):
    client = _client(monkeypatch)
    saved = []

    def _no_long(**_kw):
        raise AssertionError("단기 토큰이 없으면 장기 토큰 교환을 호출하면 안 된다")

    monkeypatch.setattr(igmod, "exchange_code_for_short_lived_token", lambda **_kw: {"user_id": "u1"})
    monkeypatch.setattr(igmod, "exchange_for_long_lived_token", _no_long)
    monkeypatch.setattr(igmod.token_store, "save_token", lambda *a: saved.append(a))
    r = client.get("/instagram-dm/oauth/callback", params={"state": "st-guard", "code": "c"})
    assert r.status_code == 502, r.text
    assert saved == []


def test_oauth_callback_normal_path_unchanged(monkeypatch):
    client = _client(monkeypatch)
    saved = []
    monkeypatch.setattr(
        igmod, "exchange_code_for_short_lived_token", lambda **_kw: {"access_token": "S", "user_id": "u1"}
    )
    monkeypatch.setattr(igmod, "exchange_for_long_lived_token", lambda **_kw: {"access_token": "L"})
    monkeypatch.setattr(igmod, "graph_verify_token", lambda uid, tok: {"username": "name", "account_type": "BUSINESS"})
    monkeypatch.setattr(igmod.token_store, "save_token", lambda *a: saved.append(a))
    monkeypatch.setattr(igmod.db, "upsert_account", lambda **_kw: "acc-1")
    r = client.get("/instagram-dm/oauth/callback", params={"state": "st-guard", "code": "c"})
    assert r.status_code == 200
    assert r.json() == {"account_id": "acc-1", "username": "name", "status": "connected"}
    assert saved == [("u1", "L")]


def test_simulate_matched_with_rule_none_does_not_crash(tmp_db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    acc, _ = _seed(tmp_db)
    monkeypatch.setattr(igmod.rule_engine, "evaluate", _matched_without_rule)
    app = FastAPI()
    app.include_router(igmod.instagram_dm_router)
    r = TestClient(app).post(
        "/instagram-dm/rules/simulate",
        json={"instagram_account_id": acc, "comment_text": "자료", "media_id": None},
    )
    assert r.status_code == 200
    assert r.json()["preview_dm"] is None
    assert r.json()["matched_rule"] is None
