"""Instagram OAuth 콜백 fail-closed — 가짜 객체만 사용, Meta 호출·keyring 접근 없음."""

from __future__ import annotations

import pytest

from ai_orchestrator.connectors.instagram import instagram_dm_router as igmod


def _setup(monkeypatch, short, long_):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(igmod.instagram_dm_router)
    monkeypatch.setattr(igmod, "_app_id", lambda: "app")
    monkeypatch.setattr(igmod, "_app_secret", lambda: "secret")
    monkeypatch.setattr(igmod, "_redirect_uri", lambda: "http://localhost/cb")
    monkeypatch.setattr(igmod.time, "time", lambda: 1000.0)
    igmod._oauth_state_add("st-fc")
    calls = {"save": [], "upsert": [], "verify": []}
    monkeypatch.setattr(igmod, "exchange_code_for_short_lived_token", lambda **_kw: short)
    monkeypatch.setattr(igmod, "exchange_for_long_lived_token", lambda **_kw: long_)
    monkeypatch.setattr(
        igmod, "graph_verify_token", lambda uid, tok: calls["verify"].append((uid, tok)) or {"username": "n"}
    )
    monkeypatch.setattr(igmod.token_store, "save_token", lambda *a: calls["save"].append(a))
    monkeypatch.setattr(igmod.db, "upsert_account", lambda **kw: calls["upsert"].append(kw) or "acc-1")
    return TestClient(app), calls


def _get(client):
    return client.get("/instagram-dm/oauth/callback", params={"state": "st-fc", "code": "c"})


@pytest.mark.parametrize("long_", [{}, {"access_token": None}, {"access_token": ""}])
def test_long_token_missing_does_not_store_short_token(monkeypatch, long_):
    client, calls = _setup(monkeypatch, {"access_token": "SHORT", "user_id": "u1"}, long_)
    r = _get(client)
    assert r.status_code == 502
    assert "SHORT" not in r.text
    assert calls == {"save": [], "upsert": [], "verify": []}


@pytest.mark.parametrize(
    "short",
    [{"access_token": "S"}, {"access_token": "S", "user_id": ""}, {"access_token": "S", "user_id": None}],
)
def test_empty_user_id_blocks_everything(monkeypatch, short):
    client, calls = _setup(monkeypatch, short, {"access_token": "LONG"})
    r = _get(client)
    assert r.status_code == 502
    assert "LONG" not in r.text
    assert calls == {"save": [], "upsert": [], "verify": []}


def test_normal_path_unchanged(monkeypatch):
    client, calls = _setup(monkeypatch, {"access_token": "S", "user_id": "u1"}, {"access_token": "L"})
    r = _get(client)
    assert r.status_code == 200
    assert r.json() == {"account_id": "acc-1", "username": "n", "status": "connected"}
    assert calls["save"] == [("u1", "L")]
    assert len(calls["upsert"]) == 1
