"""browser.open_type_close_controlled mock backend 테스트."""

from ai_orchestrator.agent_hub.redaction import _RESULT_DATA_ALLOWED_KEYS
from ai_orchestrator.browser_tool.backend_policy import get_action_policy
from ai_orchestrator.browser_tool.mock_backend import _handle_open_type_close_controlled


class TestBrowserOpenTypeCloseControlledPolicy:
    """browser.open_type_close_controlled 정책 검증."""

    def test_open_type_close_controlled_policy_not_blocked(self):
        """open_type_close_controlled 정책이 blocked=False여야 함."""
        policy = get_action_policy("open_type_close_controlled")
        assert policy is not None
        assert policy.blocked is False

    def test_open_type_close_controlled_risk_level_medium(self):
        """open_type_close_controlled risk_level은 'medium'여야 함."""
        policy = get_action_policy("open_type_close_controlled")
        assert policy.risk_level == "medium"

    def test_open_type_close_controlled_approval_required(self):
        """open_type_close_controlled는 approval 필요."""
        policy = get_action_policy("open_type_close_controlled")
        assert policy.requires_approval is True


class TestBrowserOpenTypeCloseControlledMock:
    """browser.open_type_close_controlled mock 백엔드 테스트."""

    def test_open_type_close_controlled_valid_field_and_value(self):
        """유효한 field_id와 sample_value_id로 성공."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert result.data["typed"] is True
        assert result.data["field_id"] == "sample_text_field"
        assert result.data["field_role"] == "text_input"
        assert result.data["sample_value_id"] == "sample_text_short"
        assert result.data["executed"] is True
        assert result.data["requires_approval"] is True
        assert "lifecycle" in result.data
        assert result.data["lifecycle"]["opened"] is True
        assert result.data["lifecycle"]["typed"] is True
        assert result.data["lifecycle"]["closed"] is True

    def test_open_type_close_controlled_invalid_field(self):
        """invalid field_id 거부."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "invalid_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is False
        assert result.error_code == "INVALID_FIELD_ID"

    def test_open_type_close_controlled_missing_field(self):
        """missing field_id 거부."""
        result = _handle_open_type_close_controlled(
            {
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is False
        assert result.error_code == "INVALID_FIELD_ID"

    def test_open_type_close_controlled_invalid_sample_value(self):
        """invalid sample_value_id 거부."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "invalid_value",
                "url": "https://example.com",
            }
        )
        assert result.success is False
        assert result.error_code == "INVALID_SAMPLE_VALUE_ID"

    def test_open_type_close_controlled_missing_sample_value(self):
        """missing sample_value_id 거부."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "url": "https://example.com",
            }
        )
        assert result.success is False
        assert result.error_code == "INVALID_SAMPLE_VALUE_ID"

    def test_open_type_close_controlled_missing_url(self):
        """missing url 거부."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
            }
        )
        assert result.success is False
        assert result.error_code == "MISSING_URL"

    def test_open_type_close_controlled_search_field(self):
        """search field 지원."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_search_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert result.data["field_role"] == "search_input"

    def test_open_type_close_controlled_different_sample_values(self):
        """다양한 sample_value_id 지원."""
        for sample_value_id in ["sample_text_short", "sample_text_medium", "sample_number", "sample_date"]:
            result = _handle_open_type_close_controlled(
                {
                    "field_id": "sample_text_field",
                    "sample_value_id": sample_value_id,
                    "url": "https://example.com",
                }
            )
            assert result.success is True
            assert result.data["sample_value_id"] == sample_value_id

    def test_open_type_close_controlled_always_typed_true(self):
        """typed는 항상 True (실제 입력 모의)."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.data["typed"] is True

    def test_open_type_close_controlled_no_raw_input(self):
        """raw input value 미포함."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert "raw_value" not in result.data
        assert "actual_input" not in result.data
        assert "input_text" not in result.data

    def test_open_type_close_controlled_response_allowed_keys(self):
        """응답 필드가 redaction allowlist에 포함되는지 검증."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )

        required_keys = {
            "action",
            "typed",
            "field_id",
            "field_role",
            "sample_value_id",
            "executed",
            "requires_approval",
            "lifecycle",
            "timestamp",
        }
        assert required_keys.issubset(result.data.keys())

        # 모든 응답 key가 허용 목록에 포함되는지 확인
        for key in result.data:
            if key == "lifecycle":
                # lifecycle은 nested dict 이므로 특별 처리
                assert isinstance(result.data[key], dict)
                for nested_key in result.data[key]:
                    assert nested_key.lower() in ("opened", "typed", "closed"), f"lifecycle.{nested_key} not allowed"
            else:
                assert key in _RESULT_DATA_ALLOWED_KEYS or key == "timestamp", f"'{key}' not in allowlist"


class TestBrowserOpenTypeCloseControlledSecurity:
    """browser.open_type_close_controlled 보안 검증."""

    def test_no_password_field(self):
        """password 필드 없음."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "password_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is False

    def test_no_token_field(self):
        """token 필드 없음."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "token_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is False

    def test_no_secret_in_response(self):
        """응답에 secret/password/token 없음."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        data_str = str(result.data).lower()
        assert "secret" not in data_str
        assert "token" not in data_str
        assert "password" not in data_str

    def test_no_raw_selector_in_response(self):
        """raw selector/CSS/XPath 미포함."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        data_str = str(result.data).lower()
        assert "#sample-input" not in data_str  # CSS selector
        assert "//input" not in data_str  # XPath

    def test_no_dom_details_in_response(self):
        """DOM element details 미포함."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert "element" not in result.data
        assert "selector" not in result.data
        assert "dom" not in str(result.data).lower()

    def test_no_url_in_params_response(self):
        """응답에 URL parameter 미포함 (enum 값만)."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        # URL은 요청 param에만 있고 응답에는 없어야 함
        assert result.data.get("url") is None


class TestBrowserOpenTypeCloseControlledLifecycle:
    """browser.open_type_close_controlled lifecycle 검증."""

    def test_lifecycle_structure(self):
        """lifecycle 구조 확인."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert "lifecycle" in result.data
        assert isinstance(result.data["lifecycle"], dict)
        assert set(result.data["lifecycle"].keys()) == {"opened", "typed", "closed"}

    def test_lifecycle_all_true(self):
        """모든 lifecycle 단계가 True."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert result.data["lifecycle"]["opened"] is True
        assert result.data["lifecycle"]["typed"] is True
        assert result.data["lifecycle"]["closed"] is True

    def test_executed_flag_true(self):
        """executed flag는 True."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert result.data["executed"] is True

    def test_timestamp_present(self):
        """timestamp 필드 존재."""
        result = _handle_open_type_close_controlled(
            {
                "field_id": "sample_text_field",
                "sample_value_id": "sample_text_short",
                "url": "https://example.com",
            }
        )
        assert result.success is True
        assert "timestamp" in result.data
        assert isinstance(result.data["timestamp"], str)
        assert "T" in result.data["timestamp"]  # ISO format check
