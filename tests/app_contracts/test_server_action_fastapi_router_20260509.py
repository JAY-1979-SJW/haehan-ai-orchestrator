"""
FastAPI action router 테스트:
  POST /api/v1/actions/prepare
  POST /api/v1/actions/evidence
"""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator.asgi import app
from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    _REQUESTS,
    _TOKENS,
    approve_request,
)
from ai_orchestrator.server.action_approval_audit_store import clear_store as clear_audit
from ai_orchestrator.server.action_evidence_store import clear_store as clear_evidence

PREPARE_URL = "/api/v1/actions/prepare"
EVIDENCE_URL = "/api/v1/actions/evidence"


@pytest.fixture
def client(monkeypatch, tmp_path):
    import ai_orchestrator.core.config as config

    users_path = tmp_path / "http_users.json"
    users_path.write_text(
        json.dumps(
            [
                {
                    "username": "operator_u",
                    "password_hash": "pw-operator",
                    "role": "operator",
                    "enabled": True,
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "HTTP_USERS_PATH", users_path)

    auth = base64.b64encode(b"operator_u:pw-operator").decode("ascii")
    client = TestClient(app)
    client.headers.update({"Authorization": f"Basic {auth}"})
    return client


@pytest.fixture(autouse=True)
def _clean():
    _REQUESTS.clear()
    _TOKENS.clear()
    clear_audit()
    clear_evidence()
    yield
    _REQUESTS.clear()
    _TOKENS.clear()
    clear_audit()
    clear_evidence()


# 1. POST /api/v1/actions/prepare browser.download_file → HANDOFF_READY
def test_prepare_download_file_handoff_ready(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.download_file",
            "params": {"url": "https://www.g2b.go.kr/file.pdf"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "HANDOFF_READY"
    assert data["handoff_required"] is True
    assert data["handoff_payload"] is not None


# 2. POST /api/v1/actions/prepare attach_file 토큰 없음 → APPROVAL_REQUIRED
def test_prepare_attach_file_no_token(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.attach_file",
            "params": {"file_path": "/tmp/bid.hwp", "field_selector": "#attach"},
            "requested_by": "test_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "APPROVAL_REQUIRED"
    assert data["approval_request_id"] is not None


# 3. POST /api/v1/actions/prepare attach_file 토큰 있음 → HANDOFF_READY
def test_prepare_attach_file_with_token(client):
    # 1단계: 승인 요청 생성
    prep = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.attach_file",
            "params": {"file_path": "/tmp/bid.hwp", "field_selector": "#attach"},
            "requested_by": "test_user",
        },
    ).json()
    req_id = prep["approval_request_id"]

    # 2단계: 승인 토큰 발급
    approval = approve_request(req_id, approver_user_id="test_user")
    assert approval["ok"] is True
    token = approval["approval_token"]

    # 3단계: 토큰으로 재요청
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.attach_file",
            "params": {"file_path": "/tmp/bid.hwp", "field_selector": "#attach"},
            "requested_by": "test_user",
            "approval_token": token,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "HANDOFF_READY"


# 4. POST /api/v1/actions/prepare unknown action → UNKNOWN_ACTION
def test_prepare_unknown_action(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "nonexistent.action",
            "params": {},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "UNKNOWN_ACTION"


# 5. submit/bid/esign 미구현 액션 — requires_approval=False 군 → NOT_IMPLEMENTED
@pytest.mark.parametrize(
    "action_name",
    [
        "bid.prepare_bid",
        "esign.prepare_signature",
    ],
)
def test_prepare_no_approval_unimplemented(client, action_name):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": action_name,
            "params": {"dummy": "val"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "ACTION_REGISTERED_NOT_IMPLEMENTED"
    assert data["implemented"] is False


# 6. submit/bid/esign 미구현 액션 — requires_approval=True 군, 토큰 없음 → APPROVAL_REQUIRED
@pytest.mark.parametrize(
    "action_name",
    [
        "bid.submit_with_user_approval",
        "esign.execute_with_user_approval",
    ],
)
def test_prepare_approval_unimplemented_no_token(client, action_name):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": action_name,
            "params": {"dummy": "val"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "APPROVAL_REQUIRED"
    assert data["implemented"] is False


# 7. POST /api/v1/actions/evidence safe result → 저장 성공
def test_evidence_safe_result(client):
    resp = client.post(
        EVIDENCE_URL,
        json={
            "action_name": "browser.download_file",
            "approval_request_id": "req-001",
            "params_hash": "abc123",
            "result_status": "SUCCESS",
            "result_fields_safe": {"downloaded_count": 1},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["evidence_id"] is not None


# 8. POST /api/v1/actions/evidence forbidden field → BLOCKED
def test_evidence_forbidden_field_blocked(client):
    resp = client.post(
        EVIDENCE_URL,
        json={
            "action_name": "browser.download_file",
            "approval_request_id": "req-001",
            "params_hash": "abc",
            "result_status": "SUCCESS",
            "result_fields_safe": {"cookie": "bad_value"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is False
    assert data["evidence_id"] is None


# 9. 응답에 민감 필드 미포함
def test_prepare_response_no_sensitive_fields(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.download_file",
            "params": {"url": "https://x.com/f.pdf"},
        },
    )
    body = resp.json()
    forbidden = {
        "password",
        "otp",
        "cert_password",
        "cookie",
        "session",
        "storage_state",
        "private_key",
    }
    for f in forbidden:
        assert f not in body, f"응답에 민감 필드 포함: {f}"


# 10. 라우터는 service layer 결과를 반환 — verdict 필드 존재 확인
def test_prepare_returns_service_layer_result(client):
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "browser.download_file",
            "params": {"url": "https://x.com/f.pdf"},
        },
    )
    data = resp.json()
    required_fields = {
        "action_name",
        "verdict",
        "implemented",
        "risk_level",
        "requires_approval",
        "approval_status",
        "params_hash",
        "handoff_required",
    }
    for f in required_fields:
        assert f in data, f"service layer 필드 누락: {f}"
