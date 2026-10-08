"""
카카오워크/카카오톡 채널 webhook 수신 테스트
1. 카카오워크 메시지 inbox 저장
2. 카카오워크 중복 방지
3. 카카오워크 invalid payload 방어
4. 카카오워크 필수 필드 누락 방어
5. 카카오톡 채널 메시지 inbox 저장
6. 카카오톡 채널 invalid payload 방어
7. 카카오톡 채널 source_type=kakaotalk_channel 저장 확인
8. 두 채널 데이터 독립 저장
9. 앱 부팅 + webhook 라우트 등록 확인
10. 기존 approval/telegram/mail 정책 무변경 검증
11. 카카오워크 서명 검증 (유효/무효/누락)
12. 카카오톡 채널 payload 검증 강화 (빈 utterance, userRequest 누락)
"""

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import orchestrator_v1.inbox.inbox_store as inbox_store
from orchestrator_v1.inbox import kakaowork_reader

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_inbox(tmp_path):
    return str(tmp_path / "inbox.jsonl")


@pytest.fixture
def flask_app():
    os.environ.setdefault("ORCH_DASHBOARD_USER", "test")
    os.environ.setdefault("ORCH_DASHBOARD_PASSWORD", "test")
    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as c:
        c.environ_base["HTTP_AUTHORIZATION"] = "Basic dGVzdDp0ZXN0"  # test:test
        yield c


_KAKAOWORK_PAYLOAD = {
    "type": "message",
    "user_id": "kw-user-001",
    "message": {
        "id": "msg-kakaowork-001",
        "text": "프로젝트 진행 상황 문의드립니다",
        "created_at": 1713751200000,
    },
    "channel": {"id": "ch-001"},
}

_KAKAOTALK_PAYLOAD = {
    "userRequest": {
        "utterance": "견적 요청드립니다",
        "user": {"id": "kt-user-001", "type": "botUserKey"},
    },
    "bot": {"id": "kt-bot-001"},
}


# ── 1. 카카오워크 메시지 inbox 저장 ──────────────────────────────────────────


def test_kakaowork_parse_and_save(tmp_inbox):
    """parse_webhook_payload → save_message 흐름 검증."""
    msg = kakaowork_reader.parse_webhook_payload(_KAKAOWORK_PAYLOAD)

    result = inbox_store.save_message(
        source_type=msg["source_type"],
        external_id=msg["external_id"],
        source_account=msg["source_account"],
        sender=msg["sender"],
        title=msg["title"],
        body_raw=msg["body_raw"],
        received_at=msg["received_at"],
        metadata=msg.get("metadata"),
        path=tmp_inbox,
    )

    assert result["status"] == "saved"
    items = inbox_store.list_inbox(source_type="kakaowork", path=tmp_inbox)
    assert len(items) == 1
    item = items[0]
    assert item["source_type"] == "kakaowork"
    assert item["status"] == "new"
    assert item["linked_task_id"] is None
    assert item["sender"] == "kw-user-001"
    assert "metadata" in item


def test_kakaowork_via_api(client):
    """POST /api/v1/webhooks/kakaowork → 200."""
    resp = client.post(
        "/api/v1/webhooks/kakaowork",
        json=_KAKAOWORK_PAYLOAD,
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] in ("saved", "skipped")


# ── 2. 카카오워크 중복 방지 ───────────────────────────────────────────────────


def test_kakaowork_duplicate_prevention(tmp_inbox):
    msg = kakaowork_reader.parse_webhook_payload(_KAKAOWORK_PAYLOAD)
    kwargs = {
        "source_type": msg["source_type"],
        "external_id": msg["external_id"],
        "source_account": msg["source_account"],
        "sender": msg["sender"],
        "title": msg["title"],
        "body_raw": msg["body_raw"],
        "received_at": msg["received_at"],
        "path": tmp_inbox,
    }
    r1 = inbox_store.save_message(**kwargs)
    r2 = inbox_store.save_message(**kwargs)

    assert r1["status"] == "saved"
    assert r2["status"] == "skipped"
    assert r2["reason"] == "duplicate"

    items = inbox_store.list_inbox(source_type="kakaowork", path=tmp_inbox)
    assert len(items) == 1


def test_kakaowork_duplicate_via_api(client):
    """동일 payload 두 번 POST → 두 번째는 skipped."""
    client.post("/api/v1/webhooks/kakaowork", json=_KAKAOWORK_PAYLOAD)
    resp = client.post("/api/v1/webhooks/kakaowork", json=_KAKAOWORK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "skipped"


# ── 3. 카카오워크 invalid payload 방어 ───────────────────────────────────────


def test_kakaowork_empty_payload_rejected(client):
    resp = client.post(
        "/api/v1/webhooks/kakaowork",
        data="not json",
        content_type="text/plain",
    )
    assert resp.status_code == 400


def test_kakaowork_null_payload_rejected(client):
    resp = client.post(
        "/api/v1/webhooks/kakaowork",
        json=None,
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── 4. 카카오워크 필수 필드 누락 방어 ────────────────────────────────────────


def test_kakaowork_missing_user_id_rejected(client):
    payload = {**_KAKAOWORK_PAYLOAD}
    del payload["user_id"]
    resp = client.post("/api/v1/webhooks/kakaowork", json=payload)
    assert resp.status_code == 400


def test_kakaowork_missing_type_rejected(client):
    payload = {k: v for k, v in _KAKAOWORK_PAYLOAD.items() if k != "type"}
    resp = client.post("/api/v1/webhooks/kakaowork", json=payload)
    assert resp.status_code == 400


def test_kakaowork_parse_raises_on_missing_user():
    with pytest.raises(ValueError, match="user_id"):
        kakaowork_reader.parse_webhook_payload(
            {
                "type": "message",
                "message": {"id": "msg-001", "text": "hello"},
            }
        )


# ── 5. 카카오톡 채널 메시지 inbox 저장 ───────────────────────────────────────


def test_kakaotalk_channel_via_api(client):
    """POST /api/v1/webhooks/kakaotalk-channel → 200."""
    resp = client.post(
        "/api/v1/webhooks/kakaotalk-channel",
        json=_KAKAOTALK_PAYLOAD,
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] in ("saved", "skipped")


# ── 6. 카카오톡 채널 invalid payload 방어 ────────────────────────────────────


def test_kakaotalk_channel_empty_payload_rejected(client):
    resp = client.post(
        "/api/v1/webhooks/kakaotalk-channel",
        data="garbage",
        content_type="text/plain",
    )
    assert resp.status_code == 400


def test_kakaotalk_channel_missing_user_id_rejected(client):
    payload = {
        "userRequest": {
            "utterance": "hello",
            "user": {"type": "botUserKey"},  # id 누락
        },
        "bot": {"id": "bot-001"},
    }
    resp = client.post("/api/v1/webhooks/kakaotalk-channel", json=payload)
    assert resp.status_code == 400


# ── 7. 카카오톡 채널 source_type=kakaotalk_channel 검증 ──────────────────────


def test_kakaotalk_channel_source_type(client, tmp_path):
    """source_type=kakaotalk_channel으로 저장되는지 inbox_store를 통해 검증."""
    from orchestrator_v1.webhooks.webhooks_router import _parse_kakaotalk_channel_payload

    msg = _parse_kakaotalk_channel_payload(_KAKAOTALK_PAYLOAD)
    assert msg["source_type"] == "kakaotalk_channel"
    assert msg["sender"] == "kt-user-001"
    assert "metadata" in msg
    assert msg["metadata"]["bot_id"] == "kt-bot-001"


# ── 8. 두 채널 데이터 독립 저장 ──────────────────────────────────────────────


def test_two_channels_stored_independently(tmp_inbox):
    """kakaowork와 kakaotalk_channel이 각각 독립 저장."""
    kw_msg = kakaowork_reader.parse_webhook_payload(_KAKAOWORK_PAYLOAD)
    inbox_store.save_message(
        source_type=kw_msg["source_type"],
        external_id=kw_msg["external_id"],
        source_account=kw_msg["source_account"],
        sender=kw_msg["sender"],
        title=kw_msg["title"],
        body_raw=kw_msg["body_raw"],
        received_at=kw_msg["received_at"],
        path=tmp_inbox,
    )

    from orchestrator_v1.webhooks.webhooks_router import _parse_kakaotalk_channel_payload

    kt_msg = _parse_kakaotalk_channel_payload(_KAKAOTALK_PAYLOAD)
    inbox_store.save_message(
        source_type=kt_msg["source_type"],
        external_id=kt_msg["external_id"],
        source_account=kt_msg["source_account"],
        sender=kt_msg["sender"],
        title=kt_msg["title"],
        body_raw=kt_msg["body_raw"],
        received_at=kt_msg["received_at"],
        path=tmp_inbox,
    )

    kw_items = inbox_store.list_inbox(source_type="kakaowork", path=tmp_inbox)
    kt_items = inbox_store.list_inbox(source_type="kakaotalk_channel", path=tmp_inbox)

    assert len(kw_items) == 1
    assert len(kt_items) == 1
    assert kw_items[0]["source_type"] == "kakaowork"
    assert kt_items[0]["source_type"] == "kakaotalk_channel"


# ── 9. 앱 부팅 + webhook 라우트 등록 확인 ────────────────────────────────────


def test_app_boot_with_webhook_routes(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}

    assert "/api/v1/webhooks/kakaowork" in rules
    assert "/api/v1/webhooks/kakaotalk-channel" in rules
    assert "/api/v1/webhooks/kakaotalk-skill" in rules

    # 기존 라우트 유지 확인
    assert "/api/v1/inbox/candidates/<item_id>/task" in rules
    assert "/api/v1/tasks/<task_id>/approval-request" in rules


# ── 10. 기존 정책 무변경 검증 ────────────────────────────────────────────────


def test_no_conflict_with_existing_policies(tmp_inbox):
    """카카오 webhook 수신이 기존 approval_manager/task_store에 영향 없음."""
    import orchestrator_v1.tasks.approval_manager as approval_manager
    import orchestrator_v1.tasks.task_store as task_store

    before_approval = dict(approval_manager._store)
    before_task = dict(task_store._store)

    kw_msg = kakaowork_reader.parse_webhook_payload(_KAKAOWORK_PAYLOAD)
    inbox_store.save_message(
        source_type=kw_msg["source_type"],
        external_id=kw_msg["external_id"],
        source_account=kw_msg["source_account"],
        sender=kw_msg["sender"],
        title=kw_msg["title"],
        body_raw=kw_msg["body_raw"],
        received_at=kw_msg["received_at"],
        path=tmp_inbox,
    )

    assert approval_manager._store == before_approval
    assert task_store._store == before_task


def test_kakao_does_not_auto_execute(client):
    """webhook 수신 후 자동 실행 미발생."""
    import orchestrator_v1.tasks.task_store as ts

    ts.clear()

    client.post("/api/v1/webhooks/kakaowork", json=_KAKAOWORK_PAYLOAD)
    client.post("/api/v1/webhooks/kakaotalk-channel", json=_KAKAOTALK_PAYLOAD)

    assert len(ts._store) == 0


# ── 11. 카카오워크 서명 검증 ──────────────────────────────────────────────────

_TEST_BOT_KEY = "test-bot-key-for-unit-tests"


def _make_kw_sig(body: bytes, key: str = _TEST_BOT_KEY) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def kw_secret_env(monkeypatch):
    monkeypatch.setenv("KAKAOWORK_BOT_KEY", _TEST_BOT_KEY)


def test_kakaowork_valid_signature(client, kw_secret_env):
    """올바른 서명 → 200 저장 성공."""
    body = json.dumps(_KAKAOWORK_PAYLOAD).encode()
    sig = _make_kw_sig(body)
    resp = client.post(
        "/api/v1/webhooks/kakaowork",
        data=body,
        content_type="application/json",
        headers={"X-Kakaowork-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] in ("saved", "skipped")


def test_kakaowork_invalid_signature(client, kw_secret_env):
    """잘못된 서명 → 401 거절."""
    body = json.dumps(_KAKAOWORK_PAYLOAD).encode()
    resp = client.post(
        "/api/v1/webhooks/kakaowork",
        data=body,
        content_type="application/json",
        headers={"X-Kakaowork-Signature": "deadbeef1234"},
    )
    assert resp.status_code == 401


def test_kakaowork_missing_signature(client, kw_secret_env):
    """서명 헤더 누락 → 401 거절."""
    body = json.dumps(_KAKAOWORK_PAYLOAD).encode()
    resp = client.post(
        "/api/v1/webhooks/kakaowork",
        data=body,
        content_type="application/json",
    )
    assert resp.status_code == 401


# ── 12. 카카오톡 채널 payload 검증 강화 ──────────────────────────────────────


def test_kakaotalk_channel_empty_utterance_rejected(client):
    """utterance 빈 문자열 → 400 거절."""
    payload = {
        "userRequest": {
            "utterance": "   ",
            "user": {"id": "kt-user-001", "type": "botUserKey"},
        },
        "bot": {"id": "kt-bot-001"},
    }
    resp = client.post("/api/v1/webhooks/kakaotalk-channel", json=payload)
    assert resp.status_code == 400


def test_kakaotalk_channel_missing_userrequest_rejected(client):
    """userRequest 누락 → 400 거절."""
    payload = {"bot": {"id": "kt-bot-001"}}
    resp = client.post("/api/v1/webhooks/kakaotalk-channel", json=payload)
    assert resp.status_code == 400


def test_kakaotalk_channel_oversized_utterance_rejected(client):
    """utterance 4096자 초과 → 400 거절."""
    payload = {
        "userRequest": {
            "utterance": "A" * 4097,
            "user": {"id": "kt-user-001", "type": "botUserKey"},
        },
        "bot": {"id": "kt-bot-001"},
    }
    resp = client.post("/api/v1/webhooks/kakaotalk-channel", json=payload)
    assert resp.status_code == 400


def test_kakaotalk_channel_normal_payload_saved(client):
    """정상 payload → 200 저장 유지."""
    payload = {
        "userRequest": {
            "utterance": "서비스 문의드립니다",
            "user": {"id": "kt-user-999", "type": "botUserKey"},
        },
        "bot": {"id": "kt-bot-001"},
    }
    resp = client.post("/api/v1/webhooks/kakaotalk-channel", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["status"] in ("saved", "skipped")


# ── 13. 카카오톡 스킬(오픈빌더) 응답 ──────────────────────────────────────────


def test_kakaotalk_skill_valid_payload_returns_skill_response(client):
    """정상 payload → 카카오 스킬 응답 규격(version 2.0, simpleText)으로 200."""
    payload = {
        "userRequest": {
            "utterance": "안녕하세요 견적 문의드립니다",
            "user": {"id": "kt-user-skill-001", "type": "botUserKey"},
        },
        "bot": {"id": "kt-bot-001"},
    }
    resp = client.post("/api/v1/webhooks/kakaotalk-skill", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["version"] == "2.0"
    text = data["template"]["outputs"][0]["simpleText"]["text"]
    assert "담당자" in text


def test_kakaotalk_skill_message_saved_to_inbox(client, tmp_path, monkeypatch):
    """스킬 요청도 inbox에 저장되어 사람이 이어서 확인 가능해야 한다."""
    import orchestrator_v1.inbox.inbox_store as inbox_store

    tmp_inbox = str(tmp_path / "inbox_skill.jsonl")
    monkeypatch.setattr(inbox_store, "_INBOX_PATH", tmp_inbox)

    payload = {
        "userRequest": {
            "utterance": "상담원 연결 부탁드립니다",
            "user": {"id": "kt-user-skill-002", "type": "botUserKey"},
        },
        "bot": {"id": "kt-bot-001"},
    }
    resp = client.post("/api/v1/webhooks/kakaotalk-skill", json=payload)
    assert resp.status_code == 200

    items = inbox_store.list_inbox(source_type="kakaotalk_channel", path=tmp_inbox)
    assert any(item["sender"] == "kt-user-skill-002" for item in items)


def test_kakaotalk_skill_invalid_payload_still_returns_valid_skill_response(client):
    """utterance 누락 등 잘못된 payload여도 카카오톡에는 에러 없이 안내 문구를 돌려준다."""
    payload = {"bot": {"id": "kt-bot-001"}}
    resp = client.post("/api/v1/webhooks/kakaotalk-skill", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["version"] == "2.0"
    assert "simpleText" in data["template"]["outputs"][0]


def test_kakaotalk_skill_no_auto_execute(client):
    """스킬 요청도 기존 task/approval 파이프라인을 건드리지 않는다."""
    import orchestrator_v1.tasks.task_store as ts

    ts.clear()

    payload = {
        "userRequest": {
            "utterance": "실행해줘",
            "user": {"id": "kt-user-skill-003", "type": "botUserKey"},
        },
        "bot": {"id": "kt-bot-001"},
    }
    client.post("/api/v1/webhooks/kakaotalk-skill", json=payload)
    assert len(ts._store) == 0
