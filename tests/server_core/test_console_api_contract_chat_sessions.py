"""콘솔 HTTP 계약 — /api/v1/chat/sessions (UniversalChat.tsx:162,176,273,281).

확인 항목: 인증 필요 여부(401/403), 정상 응답의 핵심 키, 잘못된 입력의 4xx.
대화기록 저장소는 임시 폴더로 바꿔 실제 data/chat_sessions.json 을 건드리지 않는다. 동작 변경 없음.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.tasks import chat_sessions as store
from tests.console_api_contract_support import (
    API,
    basic,
    disable_auth,
    enable_basic_auth,
    make_client,
)

URL = f"{API}/chat/sessions"


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_STORE_PATH", tmp_path / "chat_sessions.json")
    store._sessions.clear()
    yield
    store._sessions.clear()


@pytest.fixture
def client():
    return make_client()


# ── 인증 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", URL, None),
        ("post", URL, {"first_message": "x"}),
        ("get", f"{URL}/chat-x", None),
        ("post", f"{URL}/chat-x/messages", {"role": "user", "text": "x"}),
    ],
)
def test_auth_required_without_credentials(client, monkeypatch, tmp_path, method, path, body):
    enable_basic_auth(monkeypatch, tmp_path)
    r = client.request(method, path, json=body)
    assert r.status_code == 401


@pytest.mark.parametrize("method", ["get", "post"])
def test_viewer_role_is_forbidden(client, monkeypatch, tmp_path, method):
    # 대화기록 라우트는 admin/owner 전용 — viewer 는 403
    enable_basic_auth(monkeypatch, tmp_path)
    kwargs = {"json": {"first_message": "x"}} if method == "post" else {}
    r = getattr(client, method)(URL, headers=basic("viewer_u"), **kwargs)
    assert r.status_code == 403


@pytest.mark.parametrize("user", ["owner_u", "admin_u"])
def test_owner_and_admin_are_allowed(client, monkeypatch, tmp_path, user):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(URL, headers=basic(user)).status_code == 200


def test_wrong_password_is_unauthorized(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    bad = {"Authorization": basic("owner_u")["Authorization"][:-2] + "xx"}
    assert client.get(URL, headers=bad).status_code == 401


def test_auth_disabled_acts_as_owner(client, monkeypatch):
    # 자기완결 데스크톱(AUTH_ENABLED=false)은 인증 헤더 없이 통과
    disable_auth(monkeypatch)
    assert client.get(URL).status_code == 200


# ── 정상 응답 스키마 ─────────────────────────────────────────────────────────


def test_list_sessions_shape(client, monkeypatch):
    disable_auth(monkeypatch)
    r = client.get(URL)
    body = r.json()
    assert body["ok"] is True
    assert body["sessions"] == []
    assert body["supported_models"] == ["sonnet", "opus", "haiku", "fable"]


def test_create_session_shape_and_listing(client, monkeypatch):
    disable_auth(monkeypatch)
    r = client.post(URL, json={"first_message": "안녕하세요", "model": " opus "})
    assert r.status_code == 200
    session = r.json()["session"]
    assert r.json()["ok"] is True
    assert {"chat_id", "title", "model", "messages"} <= set(session)
    assert session["model"] == "opus"  # 앞뒤 공백 제거
    listed = client.get(URL).json()["sessions"]
    assert [s["chat_id"] for s in listed] == [session["chat_id"]]


def test_create_session_defaults_when_body_is_empty_object(client, monkeypatch):
    disable_auth(monkeypatch)
    r = client.post(URL, json={})
    assert r.status_code == 200
    assert r.json()["session"]["messages"] == []


def test_get_session_returns_detail(client, monkeypatch):
    disable_auth(monkeypatch)
    chat_id = client.post(URL, json={"first_message": "a"}).json()["session"]["chat_id"]
    r = client.get(f"{URL}/{chat_id}")
    assert r.status_code == 200
    assert r.json()["session"]["chat_id"] == chat_id


def test_add_message_appends_and_returns_session(client, monkeypatch):
    disable_auth(monkeypatch)
    chat_id = client.post(URL, json={}).json()["session"]["chat_id"]
    r = client.post(
        f"{URL}/{chat_id}/messages",
        json={
            "role": "assistant",
            "text": "완료",
            "task_id": "t1",
            "claude_session_id": "sess-1",
        },
    )
    assert r.status_code == 200
    messages = r.json()["session"]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert messages[0]["text"] == "완료"


# ── 잘못된 입력 ──────────────────────────────────────────────────────────────


def test_unknown_session_is_404(client, monkeypatch):
    disable_auth(monkeypatch)
    assert client.get(f"{URL}/chat-nope").status_code == 404
    r = client.post(f"{URL}/chat-nope/messages", json={"role": "user", "text": "x"})
    assert r.status_code == 404


def test_invalid_role_is_400(client, monkeypatch):
    disable_auth(monkeypatch)
    chat_id = client.post(URL, json={}).json()["session"]["chat_id"]
    r = client.post(f"{URL}/{chat_id}/messages", json={"role": "system", "text": "x"})
    assert r.status_code == 400


@pytest.mark.parametrize("body", [{}, {"role": "user"}, {"text": "x"}, {"role": 1, "text": "x"}])
def test_add_message_missing_fields_is_422(client, monkeypatch, body):
    disable_auth(monkeypatch)
    chat_id = client.post(URL, json={}).json()["session"]["chat_id"]
    assert client.post(f"{URL}/{chat_id}/messages", json=body).status_code == 422


def test_create_session_rejects_non_object_body(client, monkeypatch):
    disable_auth(monkeypatch)
    assert client.post(URL, json=["not", "an", "object"]).status_code == 422


def test_invalid_role_does_not_mutate_session(client, monkeypatch):
    disable_auth(monkeypatch)
    chat_id = client.post(URL, json={}).json()["session"]["chat_id"]
    client.post(f"{URL}/{chat_id}/messages", json={"role": "system", "text": "x"})
    assert client.get(f"{URL}/{chat_id}").json()["session"]["messages"] == []
