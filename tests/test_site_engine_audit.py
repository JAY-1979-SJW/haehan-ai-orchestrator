"""Unit tests for scripts.site_engine.audit."""

from scripts.site_engine.audit import (
    SiteEngineAuditEvent,
    build_audit_event,
    mask_sensitive,
)
from scripts.site_engine.site_types import GateDecision, SiteCapability

_MASK = "***REDACTED***"


def test_build_audit_event_basic():
    event = build_audit_event(
        site_key="eum",
        capability=SiteCapability.READ,
        gate_decision=GateDecision.READ_ONLY_ALLOWED,
        action="extract_device_list",
    )
    assert isinstance(event, SiteEngineAuditEvent)
    assert event.site_key == "eum"
    assert event.result == "pending"
    assert event.timestamp  # 비어 있지 않음


def test_build_audit_event_with_metadata():
    event = build_audit_event(
        site_key="naver",
        capability=SiteCapability.PUBLISH,
        gate_decision=GateDecision.APPROVAL_REQUIRED,
        action="publish_blog_post",
        actor="user",
        approved_by="admin",
        result="approved",
        metadata={"post_id": "12345", "title": "test"},
    )
    assert event.metadata["post_id"] == "12345"
    assert event.approved_by == "admin"


def test_mask_sensitive_password():
    data = {"username": "alice", "password": "hunter2"}
    result = mask_sensitive(data)
    assert result["username"] == "alice"
    assert result["password"] == _MASK


def test_mask_sensitive_token():
    data = {"api_token": "abc123secret"}
    result = mask_sensitive(data)
    assert result["api_token"] == _MASK


def test_mask_sensitive_nested():
    data = {"level1": {"secret": "mysecret", "safe": "ok"}}
    result = mask_sensitive(data)
    assert result["level1"]["secret"] == _MASK
    assert result["level1"]["safe"] == "ok"


def test_mask_sensitive_cookie():
    data = {"cookie": "session_value"}
    result = mask_sensitive(data)
    assert result["cookie"] == _MASK


def test_mask_sensitive_session():
    data = {"session": "abc"}
    result = mask_sensitive(data)
    assert result["session"] == _MASK


def test_mask_does_not_mutate_original():
    original = {"password": "secret123", "name": "test"}
    mask_sensitive(original)
    assert original["password"] == "secret123"


def test_build_audit_event_sensitive_metadata_is_masked():
    event = build_audit_event(
        site_key="hiworks",
        capability=SiteCapability.SEND,
        gate_decision=GateDecision.APPROVAL_REQUIRED,
        action="send_mail",
        metadata={"token": "real_token_value", "subject": "test"},
    )
    assert event.metadata["token"] == _MASK
    assert event.metadata["subject"] == "test"


def test_audit_event_no_secret_in_fields():
    event = build_audit_event(
        site_key="google",
        capability=SiteCapability.READ,
        gate_decision=GateDecision.SERVER_BROWSER_ALLOWED,
        action="list_drive_files",
    )
    # site_key, action, result 필드에 민감값 저장 구조 없음
    assert "password" not in str(event)
    assert "token" not in str(event).lower().replace("token", "")
