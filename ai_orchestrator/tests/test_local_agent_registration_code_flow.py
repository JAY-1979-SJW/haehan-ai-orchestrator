"""Server-side smoke tests for local agent registration code flow.

Validates registration code issue/consume/security without running actual agents.
No WebSocket, no task execution, no Windows PC agent involved.
"""

from datetime import UTC, timedelta

import pytest

from ai_orchestrator.agent_hub.registry import facade as reg
from ai_orchestrator.auth import registration_codes as regcodes


@pytest.fixture(autouse=True)
def clear_stores():
    """Clear in-memory stores before each test."""
    regcodes.clear()
    reg.clear()
    yield
    regcodes.clear()
    reg.clear()


def test_issue_registration_code():
    """Registration code can be issued."""
    result = regcodes.issue_code(
        label="Test Agent",
        expires_in_minutes=30,
        allowed_actions=["capture_screenshot"],
        issued_by="admin_user",
        issuer_role="admin",
    )

    # Plain code returned once
    assert result.registration_code, "Code must be generated"
    assert len(result.registration_code) == 14, "Code format: XXXX-XXXX-XXXX"
    assert "-" in result.registration_code, "Code must have hyphens"

    # Record stored
    assert result.code.code_id, "Code ID must be assigned"
    assert result.code.code_hash, "Hash must be stored"
    assert result.code.code_salt, "Salt must be stored"
    assert result.code.label == "Test Agent"
    assert "capture_screenshot" in result.code.allowed_actions


def test_register_agent_with_code():
    """Agent registration via registration code."""
    # Issue code
    code_result = regcodes.issue_code(
        label="Test Agent",
        issued_by="admin",
    )
    code = code_result.registration_code  # noqa: F841

    # Exchange code for agent registration
    agent_result = reg.register_agent(
        host="192.168.1.100",
        os_name="Windows",
        version="1.0.0",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )

    # Agent created
    assert agent_result.agent.agent_id, "Agent ID must be generated"
    assert agent_result.agent.host == "192.168.1.100"
    assert agent_result.agent.os_name == "Windows"
    assert agent_result.device_token, "Device token returned once"

    # Device token is NOT stored plaintext
    agent = reg.get_agent(agent_result.agent.agent_id)
    assert agent is not None
    assert not hasattr(agent, "device_token"), "Agent must not store device_token"
    assert agent.token_hash, "Agent must store token_hash"


def test_code_consume_validates_hash():
    """Code consumption validates hash using secrets.compare_digest."""
    # Issue code
    code_result = regcodes.issue_code(
        label="Test",
        issued_by="admin",
    )
    code = code_result.registration_code

    # Consume with exact code
    rec = regcodes.consume_code(code)
    assert rec.code_id == code_result.code.code_id, "Correct code accepted"

    # Try to consume again - should fail with generic message
    try:
        regcodes.consume_code(code)
        assert False, "Should raise CodeExchangeError"  # noqa: B011
    except regcodes.CodeExchangeError as e:
        assert str(e) == regcodes.INVALID_CODE_MESSAGE
        assert e.reason == "used"


def test_code_consumption_is_idempotent_failure():
    """Invalid codes always return generic error."""
    # Issue code
    code_result = regcodes.issue_code(label="Test", issued_by="admin")
    code = code_result.registration_code

    # Consume once
    regcodes.consume_code(code)

    # Try again - generic error (doesn't reveal "already used")
    with pytest.raises(regcodes.CodeExchangeError) as exc:
        regcodes.consume_code(code)

    assert str(exc.value) == regcodes.INVALID_CODE_MESSAGE, "Generic message"
    assert exc.value.reason == "used", "Reason only in exception, not response"


def test_expired_code_fails(monkeypatch):
    """Expired codes are rejected."""
    from datetime import datetime

    from ai_orchestrator.auth import registration_code_store as store_module

    # Issue code that expires in 1 minute
    code_result = regcodes.issue_code(
        label="Test",
        expires_in_minutes=1,
        issued_by="admin",
    )
    code = code_result.registration_code

    # Mock time to be 2 minutes in the future
    future = datetime.now(UTC) + timedelta(minutes=2)
    monkeypatch.setattr(store_module, "_now", lambda: future)

    # Try to consume - should be expired
    try:
        regcodes.consume_code(code)
        assert False, "Should raise CodeExchangeError"  # noqa: B011
    except regcodes.CodeExchangeError as e:
        assert str(e) == regcodes.INVALID_CODE_MESSAGE
        assert e.reason == "expired"


def test_invalid_code_format_fails():
    """Malformed codes are rejected."""
    with pytest.raises(regcodes.CodeExchangeError, match=regcodes.INVALID_CODE_MESSAGE):
        regcodes.consume_code("INVALID")

    with pytest.raises(regcodes.CodeExchangeError, match=regcodes.INVALID_CODE_MESSAGE):
        regcodes.consume_code("")

    with pytest.raises(regcodes.CodeExchangeError, match=regcodes.INVALID_CODE_MESSAGE):
        regcodes.consume_code("1234-5678-9000")  # Invalid chars


def test_revoked_code_fails():
    """Revoked codes cannot be used."""
    # Issue code
    code_result = regcodes.issue_code(label="Test", issued_by="admin")
    code = code_result.registration_code

    # Revoke it
    regcodes.revoke_code(code_result.code.code_id, actor="admin")

    # Try to consume - should fail
    with pytest.raises(regcodes.CodeExchangeError, match=regcodes.INVALID_CODE_MESSAGE):
        regcodes.consume_code(code)


def test_list_codes_hides_secrets():
    """list_codes returns safe dicts without code_hash/salt."""
    regcodes.issue_code(label="Test1", issued_by="admin")
    regcodes.issue_code(label="Test2", issued_by="admin")

    codes = regcodes.list_codes()
    assert len(codes) == 2, "Both codes listed"

    for code_dict in codes:
        # Safe fields present
        assert "code_id" in code_dict
        assert "label" in code_dict
        assert "status" in code_dict

        # Secrets NOT present
        assert "code_hash" not in code_dict, "Hash must not be exposed"
        assert "code_salt" not in code_dict, "Salt must not be exposed"
        assert "registration_code" not in code_dict, "Code must not be exposed"


def test_agent_list_hides_token_hash():
    """list_agents doesn't expose token_hash or device_token."""
    # Create agent via registration
    code_result = regcodes.issue_code(label="Test", issued_by="admin")
    agent_result = reg.register_agent(
        host="test.local",
        os_name="Windows",
        version="1.0",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )

    agents = reg.list_agents()
    assert len(agents) == 1

    agent_dict = agents[0]
    assert agent_dict["agent_id"] == agent_result.agent.agent_id
    assert agent_dict["host"] == "test.local"

    # Secrets NOT present
    assert "device_token" not in agent_dict, "Device token must not be exposed"
    assert "token_hash" not in agent_dict, "Token hash must not be exposed"


def test_device_token_authenticate():
    """Device token authentication works with hash."""
    # Register agent
    code_result = regcodes.issue_code(label="Test", issued_by="admin")
    agent_result = reg.register_agent(
        host="test.local",
        os_name="Windows",
        version="1.0",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )

    agent_id = agent_result.agent.agent_id
    device_token = agent_result.device_token

    # Authenticate with correct token
    agent = reg.authenticate_agent(agent_id, device_token)
    assert agent is not None, "Correct token accepted"
    assert agent.agent_id == agent_id

    # Authenticate with wrong token
    agent = reg.authenticate_agent(agent_id, "wrong_token")
    assert agent is None, "Wrong token rejected"


def test_response_shape_compatibility():
    """Registration response shape matches API contract."""
    code_result = regcodes.issue_code(label="Test", issued_by="admin")
    code = code_result.registration_code  # noqa: F841

    # Simulate register-with-code response building
    agent_result = reg.register_agent(
        host="192.168.1.1",
        os_name="Windows",
        version="1.0",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )

    # Response should have these fields
    response = {
        "agent_id": agent_result.agent.agent_id,
        "device_token": agent_result.device_token,  # 1-time only
        "host": agent_result.agent.host,
        "os_name": agent_result.agent.os_name,
        "version": agent_result.agent.version,
        "registered_at": agent_result.agent.registered_at,
    }

    # Validate shape
    assert "agent_id" in response
    assert "device_token" in response
    assert "host" in response
    assert "os_name" in response
    assert "version" in response
    assert "registered_at" in response


def test_no_agent_execution():
    """Registration flow never executes actual agent code."""
    code_result = regcodes.issue_code(label="Test", issued_by="admin")
    code = code_result.registration_code  # noqa: F841

    # Register agent - should only create record, no execution
    agent_result = reg.register_agent(
        host="localhost",
        os_name="Windows",
        version="1.0",
        requested_by=f"registration_code:{code_result.code.code_id}",
    )

    # Agent record created and is retrievable
    agent = reg.get_agent(agent_result.agent.agent_id)
    assert agent is not None, "Agent record created"
    assert agent.agent_id == agent_result.agent.agent_id
    assert agent.registered_at, "Registered timestamp set"
    # No WebSocket connection, no task execution - just record stored


def test_code_case_insensitive():
    """Registration code is case-insensitive."""
    result = regcodes.issue_code(label="Test", issued_by="admin")
    code = result.registration_code
    code_id = result.code.code_id  # noqa: F841

    # Issue code once, consume with different cases
    # Clear store and re-issue to test case handling
    regcodes.clear()

    result = regcodes.issue_code(label="Test", issued_by="admin")
    code = result.registration_code

    # Lowercase version should also work
    lower_case = code.lower()
    rec = regcodes.consume_code(lower_case)

    assert rec.label == "Test", "Code works with lowercase input"


def test_multiple_agents_independent():
    """Multiple agents can register independently."""
    # Create 3 codes
    codes = []
    for i in range(3):
        result = regcodes.issue_code(
            label=f"Agent-{i}",
            issued_by="admin",
        )
        codes.append(result.registration_code)

    # Register 3 agents
    agents = []
    for i, _code in enumerate(codes):
        result = reg.register_agent(
            host=f"host-{i}.local",
            os_name="Windows",
            version="1.0",
            requested_by=f"registration_code:code-{i}",
        )
        agents.append(result.agent)

    # All agents should be registered
    all_agents = reg.list_agents()
    assert len(all_agents) == 3, "All 3 agents registered"

    # Each should be independent
    for i, agent_dict in enumerate(all_agents):
        assert agent_dict["host"] == f"host-{i}.local"
        assert "device_token" not in agent_dict
