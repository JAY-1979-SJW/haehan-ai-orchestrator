"""tests/test_user_approval_gate_20260508.py"""

import pytest

from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    STATUS_EXHAUSTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    _params_hash,
    _sanitize_params,
    approve_request,
    clear_all,
    create_approval_request,
    get_request,
    list_pending,
    reject_request,
    revoke_approval,
    verify_and_consume_token,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    yield
    clear_all()


def test_create_returns_pending():
    r = create_approval_request(
        "browser.attach_file",
        params={"page_url": "https://example.com", "file_name": "a.pdf"},
        summary={"site": "example.com"},
    )
    assert r["status"] == STATUS_PENDING
    assert r["approval_token"] is None


def test_approve_returns_token():
    r = create_approval_request("browser.attach_file", params={"x": 1}, summary={})
    a = approve_request(r["request_id"], "user1")
    assert a["ok"] is True
    assert a["approval_token"]


def test_verify_token_with_matching_params():
    params = {"page_url": "https://e.com", "file_name": "a.pdf"}
    r = create_approval_request("browser.attach_file", params, {})
    a = approve_request(r["request_id"], "u1")
    v = verify_and_consume_token(a["approval_token"], "browser.attach_file", params)
    assert v["ok"] is True


def test_verify_rejects_wrong_action():
    params = {"x": 1}
    r = create_approval_request("browser.attach_file", params, {})
    a = approve_request(r["request_id"], "u1")
    v = verify_and_consume_token(a["approval_token"], "bid.submit_with_user_approval", params)
    assert v["ok"] is False
    assert "action_name" in v["reason"] or "스코프" in v["reason"]


def test_verify_rejects_wrong_params():
    """승인 범위(params) 이탈 차단."""
    r = create_approval_request("browser.attach_file", params={"file_name": "a.pdf"}, summary={})
    a = approve_request(r["request_id"], "u1")
    v = verify_and_consume_token(a["approval_token"], "browser.attach_file", params={"file_name": "different.pdf"})
    assert v["ok"] is False
    assert "params_hash" in v["reason"] or "범위" in v["reason"]


def test_token_single_use():
    """1회 사용 후 EXHAUSTED."""
    params = {"x": 1}
    r = create_approval_request("browser.attach_file", params, {})
    a = approve_request(r["request_id"], "u1")
    v1 = verify_and_consume_token(a["approval_token"], "browser.attach_file", params)
    assert v1["ok"] is True
    # 두 번째 시도 — 거부
    v2 = verify_and_consume_token(a["approval_token"], "browser.attach_file", params)
    assert v2["ok"] is False


def test_request_status_after_consume():
    params = {"x": 1}
    r = create_approval_request("browser.attach_file", params, {})
    a = approve_request(r["request_id"], "u1")
    verify_and_consume_token(a["approval_token"], "browser.attach_file", params)
    rec = get_request(r["request_id"])
    assert rec["status"] == STATUS_EXHAUSTED


def test_reject_request():
    r = create_approval_request("browser.attach_file", {}, {})
    ok = reject_request(r["request_id"], "사용자 거부")
    assert ok is True
    rec = get_request(r["request_id"])
    assert rec["status"] == STATUS_REJECTED


def test_revoke_approved_request():
    params = {"x": 1}
    r = create_approval_request("browser.attach_file", params, {})
    a = approve_request(r["request_id"], "u1")
    ok = revoke_approval(r["request_id"])
    assert ok is True
    # 토큰 사용 시도 — 거부
    v = verify_and_consume_token(a["approval_token"], "browser.attach_file", params)
    assert v["ok"] is False


def test_duration_out_of_range():
    with pytest.raises(ValueError):
        create_approval_request("browser.attach_file", {}, {}, duration_seconds=0)
    with pytest.raises(ValueError):
        create_approval_request("browser.attach_file", {}, {}, duration_seconds=99999)


def test_sanitize_strips_password():
    san = _sanitize_params({"file_name": "a.pdf", "password": "p123", "otp": "999"})
    assert "password" not in san
    assert "otp" not in san
    assert "file_name" in san


def test_sanitize_strips_cookie_session_storage():
    san = _sanitize_params(
        {
            "url": "x",
            "cookie_value": "c",
            "session_id": "s",
            "storage_state": "ss",
            "auth_header": "Bearer xxx",
        }
    )
    assert "url" in san
    assert "cookie_value" not in san
    assert "session_id" not in san
    assert "storage_state" not in san
    assert "auth_header" not in san


def test_params_hash_independent_of_sensitive_keys():
    """민감 키 유무는 hash에 영향 없음."""
    h1 = _params_hash({"x": 1, "password": "p1"})
    h2 = _params_hash({"x": 1, "password": "p2"})
    assert h1 == h2  # password는 sanitize되어 hash에서 제외
    h3 = _params_hash({"x": 2})
    assert h1 != h3  # 다른 비민감 값은 다른 hash


def test_list_pending():
    create_approval_request("browser.attach_file", {}, {})
    create_approval_request("browser.attach_file", {"x": 1}, {})
    r3 = create_approval_request("browser.attach_file", {"y": 2}, {})
    approve_request(r3["request_id"], "u")  # 1건은 approved 처리
    pending = list_pending()
    assert len(pending) == 2


def test_unknown_request_id():
    v = verify_and_consume_token("invalid_token", "any", {})
    assert v["ok"] is False


def test_empty_params_works():
    """빈 params도 정상 처리."""
    r = create_approval_request("browser.attach_file", {}, {})
    a = approve_request(r["request_id"], "u1")
    v = verify_and_consume_token(a["approval_token"], "browser.attach_file", {})
    assert v["ok"] is True
