"""tests/test_action_registry_and_schemas_20260508.py"""

import pytest

import ai_orchestrator.agent_hub.actions  # noqa: F401  (액션 핸들러 등록 트리거)
from ai_orchestrator.agent_hub.action_registry import (
    get_action_spec,
    has_handler,
    list_implemented_actions,
    list_pair_actions,
    list_pending_actions,
    register_handler,
    requires_pre_execution_summary,
    requires_user_approval,
)
from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)
from ai_orchestrator.agent_hub.action_schemas import all_specs

# 액션 모듈 import 트리거 (registry 등록) — 위 import 블록의 `import ai_orchestrator.agent_hub.actions`


def test_all_specs_defined():
    specs = all_specs()
    expected = {
        "browser.download_file",
        "browser.attach_file",
        "browser.prepare_submit",
        "browser.submit_with_user_approval",
        "bid.prepare_bid",
        "bid.submit_with_user_approval",
        "esign.prepare_signature",
        "esign.execute_with_user_approval",
        "business.prepare_action",
        "business.execute_with_user_approval",
    }
    assert expected.issubset(set(specs.keys()))


def test_download_file_grade_auto_allowed():
    spec = get_action_spec("browser.download_file")
    assert spec.risk_grade == GRADE_AUTO_ALLOWED
    assert spec.requires_user_approval is False
    assert spec.implemented is True


def test_attach_file_grade_user_delegated():
    spec = get_action_spec("browser.attach_file")
    assert spec.risk_grade == GRADE_USER_DELEGATED
    assert spec.requires_user_approval is True
    assert spec.implemented is True


def test_submit_grade_user_direct():
    spec = get_action_spec("browser.submit_with_user_approval")
    assert spec.risk_grade == GRADE_USER_DIRECT
    assert spec.requires_user_approval is True
    assert spec.implemented is True


def test_bid_submit_grade_user_direct():
    spec = get_action_spec("bid.submit_with_user_approval")
    assert spec.risk_grade == GRADE_USER_DIRECT
    assert spec.requires_user_approval is True
    assert spec.implemented is False


def test_esign_execute_grade_user_direct():
    spec = get_action_spec("esign.execute_with_user_approval")
    assert spec.risk_grade == GRADE_USER_DIRECT
    assert spec.requires_user_approval is True
    assert spec.implemented is False


def test_prepare_actions_no_approval():
    """prepare 액션은 자동 허용, 실제 제출은 별도 액션."""
    for name in ("browser.prepare_submit", "bid.prepare_bid", "esign.prepare_signature", "business.prepare_action"):
        spec = get_action_spec(name)
        assert spec.risk_grade == GRADE_AUTO_ALLOWED, f"{name}"
        assert spec.requires_user_approval is False, f"{name}"


def test_pair_relationships():
    assert list_pair_actions("browser.prepare_submit") == "browser.submit_with_user_approval"
    assert list_pair_actions("bid.prepare_bid") == "bid.submit_with_user_approval"
    assert list_pair_actions("esign.prepare_signature") == "esign.execute_with_user_approval"
    assert list_pair_actions("business.prepare_action") == "business.execute_with_user_approval"


def test_unknown_action_returns_none():
    assert get_action_spec("nonexistent.action") is None


def test_list_implemented_includes_phase1():
    impl = list_implemented_actions()
    assert "browser.download_file" in impl
    assert "browser.attach_file" in impl


def test_list_pending_includes_future():
    pending = list_pending_actions()
    assert "bid.submit_with_user_approval" in pending
    assert "esign.execute_with_user_approval" in pending
    assert "bid.prepare_bid" in pending
    assert "esign.prepare_signature" in pending


def test_handler_registered_for_implemented():
    assert has_handler("browser.download_file") is True
    assert has_handler("browser.attach_file") is True
    assert has_handler("browser.prepare_submit") is True
    assert has_handler("browser.submit_with_user_approval") is True
    assert has_handler("business.prepare_action") is True
    assert has_handler("business.execute_with_user_approval") is True


def test_handler_not_registered_for_pending():
    assert has_handler("bid.submit_with_user_approval") is False
    assert has_handler("esign.execute_with_user_approval") is False
    assert has_handler("bid.prepare_bid") is False
    assert has_handler("esign.prepare_signature") is False


def test_register_handler_unknown_action_raises():
    with pytest.raises(ValueError):
        register_handler("nonexistent.action", lambda **kw: {})


def test_register_handler_pending_action_raises():
    """미구현 액션의 핸들러 등록 시도 시 거부."""
    with pytest.raises(ValueError):
        register_handler("bid.submit_with_user_approval", lambda **kw: {})


def test_requires_user_approval_helper():
    assert requires_user_approval("browser.download_file") is False
    assert requires_user_approval("browser.attach_file") is True
    assert requires_user_approval("bid.submit_with_user_approval") is True


def test_requires_pre_execution_summary_helper():
    assert requires_pre_execution_summary("browser.download_file") is False
    assert requires_pre_execution_summary("browser.attach_file") is True


def test_summary_fields_no_credential_keys():
    """summary_fields에 password/otp/cert_password 같은 민감 키 없음."""
    forbidden = ("password", "otp", "cert_password", "cookie", "session", "token", "private_key")
    for name, spec in all_specs().items():
        for f in spec.summary_fields:
            for fb in forbidden:
                assert fb not in f.lower(), f"{name}.{f}에 민감 키"


def test_evidence_fields_no_credential_keys():
    forbidden = ("password", "otp", "cert_password", "cookie", "session", "token", "private_key", "raw_html")
    for name, spec in all_specs().items():
        for f in spec.evidence_fields:
            for fb in forbidden:
                assert fb not in f.lower(), f"{name}.{f}에 민감 키"


def test_phase1_count():
    impl = list_implemented_actions()
    assert (
        len(impl) == 6
    )  # download_file + attach_file + prepare_submit + submit_with_user_approval + business_prepare + business_execute
