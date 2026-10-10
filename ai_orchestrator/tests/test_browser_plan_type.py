"""browser.plan_type mock backend 테스트."""

from ai_orchestrator.agent_hub.redaction import _RESULT_DATA_ALLOWED_KEYS
from ai_orchestrator.browser_tool.backend_policy import get_action_policy
from ai_orchestrator.browser_tool.mock_backend import _handle_plan_type


class TestBrowserPlanTypePolicy:
    """browser.plan_type 정책 검증."""

    def test_plan_type_policy_not_blocked(self):
        """plan_type 정책이 blocked=False여야 함."""
        policy = get_action_policy("plan_type")
        assert policy is not None
        assert policy.blocked is False

    def test_plan_type_risk_level_low(self):
        """plan_type risk_level은 'low'여야 함."""
        policy = get_action_policy("plan_type")
        assert policy.risk_level == "low"

    def test_plan_type_no_approval_required(self):
        """plan_type은 approval 불필요."""
        policy = get_action_policy("plan_type")
        assert policy.requires_approval is False


class TestBrowserPlanTypeMock:
    """browser.plan_type mock 백엔드 테스트."""

    def test_plan_type_valid_field(self):
        """유효한 field_id로 성공."""
        result = _handle_plan_type(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is True
        assert result.data["typed"] is False
        assert result.data["field_role"] == "text_input"
        assert result.data["input_redacted"] is True

    def test_plan_type_invalid_field(self):
        """invalid field_id 거부."""
        result = _handle_plan_type(
            {
                "field_id": "invalid_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is False
        assert result.error_code == "INVALID_FIELD_ID"

    def test_plan_type_invalid_sample_value(self):
        """invalid sample_value_id 거부."""
        result = _handle_plan_type(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "invalid_value",
            }
        )
        assert result.success is False
        assert result.error_code == "INVALID_SAMPLE_VALUE_ID"

    def test_plan_type_search_field(self):
        """search field 지원."""
        result = _handle_plan_type(
            {
                "field_id": "sample_search_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is True
        assert result.data["field_role"] == "search_input"

    def test_plan_type_no_raw_input(self):
        """raw input value 미포함."""
        result = _handle_plan_type(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is True
        assert "raw_value" not in result.data
        assert result.data["input_redacted"] is True

    def test_plan_type_always_not_typed(self):
        """typed는 항상 False (plan-only)."""
        result = _handle_plan_type(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.data["typed"] is False

    def test_plan_type_response_allowed_keys(self):
        """응답 필드가 redaction allowlist에 포함되는지 검증."""
        result = _handle_plan_type(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
            }
        )

        required_keys = {"action", "typed", "field_id", "field_role", "sample_value_id", "input_redacted", "timestamp"}
        assert required_keys.issubset(result.data.keys())

        # 모든 응답 key가 허용 목록에 포함되는지 확인
        for key in result.data:
            assert key in _RESULT_DATA_ALLOWED_KEYS or key == "timestamp", f"'{key}' not in allowlist"


class TestBrowserPlanTypeSecurity:
    """browser.plan_type 보안 검증."""

    def test_no_password_field(self):
        """password 필드 없음."""
        result = _handle_plan_type(
            {
                "field_id": "password_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is False

    def test_no_token_field(self):
        """token 필드 없음."""
        result = _handle_plan_type(
            {
                "field_id": "token_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is False

    def test_no_secret_in_response(self):
        """응답에 secret 없음."""
        result = _handle_plan_type(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is True
        data_str = str(result.data).lower()
        assert "secret" not in data_str
        assert "token" not in data_str
        assert "password" not in data_str
