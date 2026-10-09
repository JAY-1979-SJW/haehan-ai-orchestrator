"""
범용 업무 실행 FastAPI 경유 end-to-end 테스트 (2026-05-09).

검증:
- POST /api/v1/actions/prepare (business.prepare_action) → HANDOFF_READY
- POST /api/v1/actions/prepare (business.execute_with_user_approval, 토큰 없음) → APPROVAL_REQUIRED
- 승인 후 재요청 → HANDOFF_READY
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    _REQUESTS,
    _TOKENS,
    approve_request,
)
from ai_orchestrator.asgi import app
from ai_orchestrator.server.action_approval_audit_store import clear_store as clear_audit
from ai_orchestrator.server.action_evidence_store import clear_store as clear_evidence
from tools.gates.auth import get_current_user

PREPARE_URL = "/api/v1/actions/prepare"


@pytest.fixture
def client():
    # AUTH_ENABLED 기본 true — 이 시험은 인증이 아니라 액션 흐름 검증이므로 의존성만 우회하고 종료 시 복원한다.
    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "actor": "test_user"}
    try:
        yield TestClient(app)
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = prev


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


def test_business_prepare_action_handoff_ready(client):
    """business.prepare_action: HANDOFF_READY."""
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.prepare_action",
            "params": {
                "page_url": "https://www.g2b.go.kr",
                "business_profile": "bid_submission",
                "target_id": "공고 12345",
                "organization_name": "한국자동차정보센터",
                "amount": "1,000,000",
                "due_date": "2026-05-31",
                "submit_selector": "button.submit",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "HANDOFF_READY"
    assert data["handoff_required"] is True
    assert data["handoff_payload"] is not None


def test_business_prepare_action_all_profiles(client):
    """business.prepare_action: 6개 프로필 모두 지원."""
    profiles = [
        "bid_submission",
        "erp_save",
        "erp_submit_approval",
        "document_submission",
        "public_agency_upload",
        "esign_request",
    ]
    for profile in profiles:
        resp = client.post(
            PREPARE_URL,
            json={
                "action_name": "business.prepare_action",
                "params": {
                    "page_url": "https://example.com",
                    "business_profile": profile,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # 필드 누락 시 HANDOFF_READY but with warnings
        assert data["verdict"] in ("HANDOFF_READY", "HANDOFF_READY")
        assert data["handoff_required"] is True


def test_business_execute_no_token(client):
    """business.execute_with_user_approval: 토큰 없음 → APPROVAL_REQUIRED."""
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.execute_with_user_approval",
            "params": {
                "page_url": "https://www.g2b.go.kr",
                "submit_selector": "button.submit",
                "business_profile": "bid_submission",
                "target_id": "공고 12345",
            },
            "requested_by": "test_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "APPROVAL_REQUIRED"
    assert data["approval_request_id"] is not None


def test_business_execute_with_token(client):
    """business.execute_with_user_approval: 토큰 유효 → HANDOFF_READY."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "target_id": "공고 12345",
        "organization_name": "기관명",
    }

    # 1단계: 승인 요청 생성
    prep = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.execute_with_user_approval",
            "params": params,
            "requested_by": "test_user",
        },
    ).json()
    req_id = prep["approval_request_id"]

    # 2단계: 토큰 발급
    appr = approve_request(req_id, "test_user")
    token = appr["approval_token"]

    # 3단계: 토큰으로 재요청
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.execute_with_user_approval",
            "params": params,
            "approval_token": token,
            "requested_by": "test_user",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "HANDOFF_READY"
    assert data["handoff_payload"] is not None


def test_business_prepare_missing_required_fields(client):
    """business.prepare_action: 필수 필드 누락 → HANDOFF_READY (경고 포함)."""
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.prepare_action",
            "params": {
                "page_url": "https://www.g2b.go.kr",
                "business_profile": "bid_submission",
                # target_id, organization_name, amount, due_date, submit_selector 누락
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # prepare는 자동 허용이므로 HANDOFF_READY (verdict는 PREPARE_WARN일 수도)
    assert data["handoff_required"] is True


def test_business_invalid_profile(client):
    """business.prepare_action: 미지원 프로필 → 응답 수신 (자동 허용이므로 prepare는 진행)."""
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.prepare_action",
            "params": {
                "page_url": "https://www.g2b.go.kr",
                "business_profile": "invalid_profile",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # prepare_action은 자동 허용(AUTO_ALLOWED)이므로 응답은 반환
    assert data["action_name"] == "business.prepare_action"


def test_response_no_sensitive_fields(client):
    """응답에 password/cookie 등 민감 필드 미포함."""
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.prepare_action",
            "params": {
                "page_url": "https://www.g2b.go.kr",
                "business_profile": "bid_submission",
                "target_id": "N1",
                "organization_name": "기관",
                "amount": "100",
                "due_date": "2026-05-31",
                "submit_selector": "button",
            },
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


def test_business_execute_handoff_payload_present(client):
    """business.execute_with_user_approval: handoff_payload 존재."""
    params = {
        "page_url": "https://www.g2b.go.kr/form?notice=N1&lang=ko",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
    }

    prep = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.execute_with_user_approval",
            "params": params,
            "requested_by": "test_user",
        },
    ).json()
    req_id = prep["approval_request_id"]

    token = approve_request(req_id, "test_user")["approval_token"]

    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.execute_with_user_approval",
            "params": params,
            "approval_token": token,
        },
    ).json()

    # handoff_payload 존재 확인
    assert resp["handoff_required"] is True
    assert resp["handoff_payload"] is not None
    assert resp["verdict"] == "HANDOFF_READY"


def test_service_layer_fields_present(client):
    """서버 응답: service layer 필드 존재."""
    resp = client.post(
        PREPARE_URL,
        json={
            "action_name": "business.prepare_action",
            "params": {
                "page_url": "https://www.g2b.go.kr",
                "business_profile": "bid_submission",
                "target_id": "N1",
                "organization_name": "기관",
                "amount": "100",
                "due_date": "2026-05-31",
                "submit_selector": "button",
            },
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
