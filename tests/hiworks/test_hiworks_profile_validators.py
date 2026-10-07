"""Unit tests for hiworks profile and validators."""

from scripts.hiworks.site_profile import HIWORKS_PROFILE
from scripts.hiworks.validators import (
    validate_hiworks_no_plain_secret,
)
from scripts.site_engine.site_types import GateDecision, SiteCapability

# ── profile ──────────────────────────────────────────────────────────


def test_hiworks_profile_key():
    assert HIWORKS_PROFILE.key == "hiworks"


def test_hiworks_profile_send_approval_required():
    policy = HIWORKS_PROFILE.action_policies.get(SiteCapability.SEND)
    assert policy is not None
    assert policy.gate == GateDecision.APPROVAL_REQUIRED


def test_hiworks_profile_submit_approval_required():
    policy = HIWORKS_PROFILE.action_policies.get(SiteCapability.SUBMIT)
    assert policy is not None
    assert policy.gate == GateDecision.APPROVAL_REQUIRED


def test_hiworks_profile_read_allowed():
    assert SiteCapability.READ in HIWORKS_PROFILE.allowed_capabilities


def test_hiworks_profile_no_blocked_capabilities():
    assert len(HIWORKS_PROFILE.blocked_capabilities) == 0


# ── validators ───────────────────────────────────────────────────────


def test_no_plain_secret_clean():
    result = validate_hiworks_no_plain_secret({"to": "test@example.com", "subject": "test"})
    assert result.is_valid


def test_no_plain_secret_detects_password():
    result = validate_hiworks_no_plain_secret({"password": "hunter2"})
    assert not result.is_valid


def test_no_plain_secret_detects_token():
    result = validate_hiworks_no_plain_secret({"api_token": "secret"})
    assert not result.is_valid


# ── gates site_engine wrappers ────────────────────────────────────────


def test_gate_result_read_allowed():
    from scripts.hiworks.gates import gate_result_read
    from scripts.site_engine.execution_gate import ExecutionDecision

    result = gate_result_read()
    assert result.decision == ExecutionDecision.ALLOWED


def test_gate_result_prepare_allowed():
    from scripts.hiworks.gates import gate_result_prepare
    from scripts.site_engine.execution_gate import ExecutionDecision

    result = gate_result_prepare()
    assert result.decision == ExecutionDecision.ALLOWED


def test_gate_result_send_approval_required():
    from scripts.hiworks.gates import gate_result_send
    from scripts.site_engine.execution_gate import ExecutionDecision

    result = gate_result_send()
    assert result.decision == ExecutionDecision.APPROVAL_REQUIRED
