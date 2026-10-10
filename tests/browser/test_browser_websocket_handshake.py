"""Tests for read-only WebSocket handshake protocol.

Mock handshake flow validation without actual WebSocket connection.
"""

import json

import pytest

from core.agent_runtime.browser.bridge.browser_websocket_handshake import (
    AgentHeartbeatMessage,
    AgentHelloMessage,
    Capability,
    HandshakeMode,
    ServerPolicyMessage,
    safe_dict,
    validate_agent_heartbeat_message,
    validate_agent_hello_message,
    validate_handshake_message,
    validate_server_policy_message,
)

# ── AgentHelloMessage Tests ──────────────────────────────────────────


def test_agent_hello_message_validates():
    """agent.hello message should validate."""
    msg = AgentHelloMessage(
        agent_id="local-agent-1",
        agent_version="0.1.0",
        host_name_hash="abc123def456",
    )
    is_valid, err = validate_agent_hello_message(msg.to_dict())
    assert is_valid, err


def test_agent_hello_safe_dict_has_no_raw_hostname():
    """agent.hello safe_dict should not contain raw hostname."""
    msg = AgentHelloMessage(
        agent_id="local-agent-1",
        agent_version="0.1.0",
        host_name_hash="abc123def456",
    )
    safe = msg.safe_dict()
    assert "hostname" not in safe
    assert "host_name_hash" in safe


def test_agent_hello_safe_dict_has_no_username():
    """agent.hello safe_dict should not contain raw username."""
    # Even if someone tries to add username, safe_dict removes it
    msg_dict = AgentHelloMessage(
        agent_id="local-agent-1",
        agent_version="0.1.0",
        host_name_hash="abc123def456",
    ).to_dict()
    # Artificially add forbidden field
    msg_dict["username"] = "john_doe"
    safe = safe_dict(msg_dict)
    assert "username" not in safe


def test_agent_hello_rejects_non_read_only_mode():
    """agent.hello should reject non-read_only mode."""
    msg = {
        "message_type": "agent.hello",
        "agent_id": "local-agent-1",
        "agent_version": "0.1.0",
        "mode": "full",
    }
    is_valid, err = validate_agent_hello_message(msg)
    assert not is_valid
    assert "read_only" in err.lower()


def test_agent_hello_rejects_missing_agent_id():
    """agent.hello should require agent_id."""
    msg = {
        "message_type": "agent.hello",
        "agent_version": "0.1.0",
    }
    is_valid, err = validate_agent_hello_message(msg)
    assert not is_valid
    assert "agent_id" in err.lower()


# ── ServerPolicyMessage Tests ────────────────────────────────────────


def test_server_policy_read_only_validates():
    """server.policy read-only message should validate."""
    msg = ServerPolicyMessage()
    is_valid, err = validate_server_policy_message(msg.to_dict())
    assert is_valid, err


def test_server_policy_disallows_execute():
    """server.policy should disallow execute in read-only mode."""
    msg = ServerPolicyMessage()
    assert msg.allow_execute is False
    assert msg.allow_submit is False
    assert msg.allow_password_input is False
    assert msg.allow_otp_input is False


def test_server_policy_requires_approval():
    """server.policy should require approval in read-only mode."""
    msg = ServerPolicyMessage()
    assert msg.require_approval is True


def test_server_policy_rejects_execute_true():
    """server.policy should reject allow_execute=True."""
    msg = {
        "message_type": "server.policy",
        "mode": "read_only",
        "allow_execute": True,  # Not allowed
        "allow_submit": False,
        "allow_password_input": False,
        "allow_otp_input": False,
        "require_approval": True,
    }
    is_valid, err = validate_server_policy_message(msg)
    assert not is_valid
    assert "allow_execute" in err.lower()


def test_server_policy_rejects_approval_false():
    """server.policy should reject require_approval=False."""
    msg = {
        "message_type": "server.policy",
        "mode": "read_only",
        "allow_execute": False,
        "allow_submit": False,
        "allow_password_input": False,
        "allow_otp_input": False,
        "require_approval": False,  # Not allowed
    }
    is_valid, err = validate_server_policy_message(msg)
    assert not is_valid
    assert "require_approval" in err.lower()


# ── AgentHeartbeatMessage Tests ──────────────────────────────────────


def test_heartbeat_message_validates():
    """agent.heartbeat message should validate."""
    msg = AgentHeartbeatMessage(
        agent_id="local-agent-1",
        status="ready",
    )
    is_valid, err = validate_agent_heartbeat_message(msg.to_dict())
    assert is_valid, err


def test_heartbeat_does_not_include_secret_fields():
    """agent.heartbeat should not include secret fields."""
    msg_dict = {
        "message_type": "agent.heartbeat",
        "agent_id": "local-agent-1",
        "status": "ready",
        "mode": "read_only",
        "pending_tasks": 0,
        "approval_token": "secret_token",  # Forbidden
    }
    safe = safe_dict(msg_dict)
    assert "approval_token" not in safe


def test_heartbeat_with_error_message():
    """agent.heartbeat can include safe error summary."""
    msg = AgentHeartbeatMessage(
        agent_id="local-agent-1",
        status="error",
        last_error="Failed to connect to database",
    )
    is_valid, err = validate_agent_heartbeat_message(msg.to_dict())
    assert is_valid, err


def test_heartbeat_rejects_secret_in_error_message():
    """agent.heartbeat should reject secret fields in error message."""
    msg = {
        "message_type": "agent.heartbeat",
        "agent_id": "local-agent-1",
        "status": "error",
        "mode": "read_only",
        "pending_tasks": 0,
        "last_error": "Failed with approval_token=xyz",
    }
    is_valid, err = validate_agent_heartbeat_message(msg)
    assert not is_valid
    assert "forbidden field" in err.lower()


# ── Forbidden Fields Tests ───────────────────────────────────────────


def test_approval_token_rejected_from_handshake():
    """approval_token should be rejected from handshake."""
    msg = {
        "message_type": "agent.hello",
        "agent_id": "local-agent-1",
        "agent_version": "0.1.0",
        "approval_token": "secret_xyz",
    }
    is_valid, err = validate_agent_hello_message(msg)
    assert not is_valid
    assert "forbidden" in err.lower()


def test_token_hash_rejected_from_handshake():
    """token_hash should be rejected from handshake."""
    msg = {
        "message_type": "agent.hello",
        "agent_id": "local-agent-1",
        "agent_version": "0.1.0",
        "token_hash": "abc123",
    }
    is_valid, err = validate_agent_hello_message(msg)
    assert not is_valid
    assert "forbidden" in err.lower()


def test_password_otp_rejected_from_handshake():
    """password and otp should be rejected from handshake."""
    msg = {
        "message_type": "agent.hello",
        "agent_id": "local-agent-1",
        "agent_version": "0.1.0",
        "password": "secret123",
    }
    is_valid, err = validate_agent_hello_message(msg)
    assert not is_valid
    assert "forbidden" in err.lower()


def test_cookie_session_storage_rejected_from_handshake():
    """cookie, session, storage should be rejected."""
    msg = {
        "message_type": "agent.hello",
        "agent_id": "local-agent-1",
        "agent_version": "0.1.0",
        "cookie": "sessionid=xyz",
    }
    is_valid, err = validate_agent_hello_message(msg)
    assert not is_valid
    assert "forbidden" in err.lower()


# ── Mock Handshake Flow Tests ────────────────────────────────────────


def test_handshake_flow_mock_success():
    """Complete mock handshake flow should succeed."""
    # 1. Agent hello
    hello = AgentHelloMessage(
        agent_id="local-agent-1",
        agent_version="0.1.0",
        host_name_hash="abc123def456",
    )
    is_valid, err = validate_handshake_message(hello.to_dict())
    assert is_valid, f"agent.hello validation failed: {err}"

    # 2. Server ack (implicit, no validation needed)

    # 3. Server policy
    policy = ServerPolicyMessage()
    is_valid, err = validate_handshake_message(policy.to_dict())
    assert is_valid, f"server.policy validation failed: {err}"

    # 4. Agent ready (implicit, no validation needed)

    # 5. Heartbeat loop
    heartbeat = AgentHeartbeatMessage(
        agent_id="local-agent-1",
        status="ready",
        pending_tasks=0,
    )
    is_valid, err = validate_handshake_message(heartbeat.to_dict())
    assert is_valid, f"agent.heartbeat validation failed: {err}"


def test_read_only_policy_rejects_execute_click():
    """read-only policy should reject execute_click task."""
    policy = ServerPolicyMessage()
    assert policy.allow_execute is False
    assert policy.mode == HandshakeMode.READ_ONLY.value


def test_read_only_policy_rejects_execute_type():
    """read-only policy should reject execute_type task."""
    policy = ServerPolicyMessage()
    assert policy.allow_execute is False
    assert policy.mode == HandshakeMode.READ_ONLY.value


def test_read_only_policy_allows_inspect_capability():
    """read-only mode should declare inspect capabilities."""
    hello = AgentHelloMessage(
        agent_id="local-agent-1",
        agent_version="0.1.0",
        host_name_hash="abc123def456",
    )
    assert Capability.BROWSER_INSPECT.value in hello.capabilities
    assert Capability.BROWSER_PLAN_CLICK.value in hello.capabilities
    assert Capability.BROWSER_PLAN_TYPE.value in hello.capabilities


def test_unsupported_message_type_rejected():
    """Unsupported message type should be rejected."""
    msg = {
        "message_type": "unknown.type",
        "agent_id": "local-agent-1",
    }
    is_valid, err = validate_handshake_message(msg)
    assert not is_valid
    assert "unknown" in err.lower()


# ── Safe Dict Tests ──────────────────────────────────────────────────


def test_safe_dict_removes_approval_token():
    """safe_dict should remove approval_token."""
    data = {
        "agent_id": "local-agent-1",
        "approval_token": "secret",
        "final_approval_token": "secret2",
    }
    safe = safe_dict(data)
    assert "approval_token" not in safe
    assert "final_approval_token" not in safe
    assert "agent_id" in safe


def test_safe_dict_removes_token_hash():
    """safe_dict should remove token_hash."""
    data = {
        "agent_id": "local-agent-1",
        "token_hash": "abc123",
    }
    safe = safe_dict(data)
    assert "token_hash" not in safe
    assert "agent_id" in safe


def test_safe_dict_removes_password_otp():
    """safe_dict should remove password and otp."""
    data = {
        "agent_id": "local-agent-1",
        "password": "secret",
        "otp": "123456",
    }
    safe = safe_dict(data)
    assert "password" not in safe
    assert "otp" not in safe
    assert "agent_id" in safe


def test_safe_dict_removes_cookie_session():
    """safe_dict should remove cookie, session, storage."""
    data = {
        "agent_id": "local-agent-1",
        "cookie": "sessionid=xyz",
        "session": "session_data",
        "authorization": "Bearer xyz",
        "localStorage": {"key": "value"},
        "sessionStorage": {"key": "value"},
    }
    safe = safe_dict(data)
    assert "cookie" not in safe
    assert "session" not in safe
    assert "authorization" not in safe
    assert "localStorage" not in safe
    assert "sessionStorage" not in safe
    assert "agent_id" in safe


def test_safe_dict_recursive_removal():
    """safe_dict should remove forbidden fields recursively."""
    data = {
        "agent_id": "local-agent-1",
        "nested": {
            "approval_token": "secret",
            "agent_info": "safe",
        },
        "list": [
            {"password": "secret"},
            {"status": "ready"},
        ],
    }
    safe = safe_dict(data)
    assert safe["agent_id"] == "local-agent-1"
    assert "approval_token" not in safe.get("nested", {})
    assert safe["nested"]["agent_info"] == "safe"
    assert "password" not in safe["list"][0]
    assert safe["list"][1]["status"] == "ready"


def test_safe_dict_preserves_hash_values():
    """safe_dict should preserve hash values (safe)."""
    data = {
        "agent_id": "local-agent-1",
        "host_name_hash": "abc123def456",
        "machine_id_hash": "xyz789",
    }
    safe = safe_dict(data)
    assert safe["host_name_hash"] == "abc123def456"
    assert safe["machine_id_hash"] == "xyz789"


# ── Message JSON Serialization ───────────────────────────────────────


def test_agent_hello_to_json_str():
    """agent.hello should serialize to valid JSON."""
    msg = AgentHelloMessage(
        agent_id="local-agent-1",
        agent_version="0.1.0",
        host_name_hash="abc123def456",
    )
    json_str = msg.to_json_str()
    parsed = json.loads(json_str)
    assert parsed["message_type"] == "agent.hello"
    assert parsed["agent_id"] == "local-agent-1"


def test_server_policy_to_json_str():
    """server.policy should serialize to valid JSON."""
    msg = ServerPolicyMessage()
    json_str = msg.to_json_str()
    parsed = json.loads(json_str)
    assert parsed["message_type"] == "server.policy"
    assert parsed["allow_execute"] is False


def test_agent_heartbeat_to_json_str():
    """agent.heartbeat should serialize to valid JSON."""
    msg = AgentHeartbeatMessage(
        agent_id="local-agent-1",
        status="ready",
    )
    json_str = msg.to_json_str()
    parsed = json.loads(json_str)
    assert parsed["message_type"] == "agent.heartbeat"
    assert parsed["agent_id"] == "local-agent-1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
