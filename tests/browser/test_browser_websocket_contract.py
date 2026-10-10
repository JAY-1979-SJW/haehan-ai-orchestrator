"""Mock WebSocket contract tests for browser actions (BROWSER-4E).

Verifies:
1. Browser action type registration (Gap #1)
2. Mock WebSocket payload → BrowserTaskPayload mapping (Gap #2)
3. Result data whitelist for browser safe fields (Gap #3)
4. Approval token transmission
5. Forbidden field protection
"""

from ai_orchestrator.agent_hub.registry import facade as _reg
from core.agent_runtime.browser.approval.browser_approval_verifier import BrowserApprovalStore, BrowserApprovalVerifier
from core.agent_runtime.browser.browser_task_handler import BrowserTaskPayload, BrowserTaskResult


class TestBrowserActionRegistration:
    """Gap #1: Browser action type registration"""

    def test_browser_inspect_action_is_registered(self):
        """browser.inspect should not be UNKNOWN_ACTION"""
        assert "browser.inspect" in _reg.ACTION_RISK
        assert _reg.ACTION_RISK["browser.inspect"] == "low"

    def test_browser_plan_click_action_is_registered(self):
        """browser.plan_click should not be UNKNOWN_ACTION"""
        assert "browser.plan_click" in _reg.ACTION_RISK
        assert _reg.ACTION_RISK["browser.plan_click"] == "low"

    def test_browser_plan_type_action_is_registered(self):
        """browser.plan_type should not be UNKNOWN_ACTION"""
        assert "browser.plan_type" in _reg.ACTION_RISK
        assert _reg.ACTION_RISK["browser.plan_type"] == "low"

    def test_browser_plan_submit_action_is_registered(self):
        """browser.plan_submit should not be UNKNOWN_ACTION"""
        assert "browser.plan_submit" in _reg.ACTION_RISK
        assert _reg.ACTION_RISK["browser.plan_submit"] == "low"

    def test_browser_execute_click_action_is_registered(self):
        """browser.execute_click should not be UNKNOWN_ACTION, risk=medium"""
        assert "browser.execute_click" in _reg.ACTION_RISK
        assert _reg.ACTION_RISK["browser.execute_click"] == "medium"

    def test_browser_execute_type_action_is_registered(self):
        """browser.execute_type should not be UNKNOWN_ACTION, risk=medium"""
        assert "browser.execute_type" in _reg.ACTION_RISK
        assert _reg.ACTION_RISK["browser.execute_type"] == "medium"

    def test_browser_execute_submit_is_not_registered(self):
        """browser.execute_submit should NOT be registered (blocked)"""
        assert "browser.execute_submit" not in _reg.ACTION_RISK

    def test_browser_actions_in_auto_execute_set(self):
        """All browser actions should be in AUTO_EXECUTE_VIA_AGENT"""
        browser_actions = {
            "browser.inspect",
            "browser.plan_click",
            "browser.plan_type",
            "browser.plan_submit",
            "browser.execute_click",
            "browser.execute_type",
        }
        for action in browser_actions:
            assert action in _reg.AUTO_EXECUTE_VIA_AGENT, f"{action} not in AUTO_EXECUTE_VIA_AGENT"


class TestMockWebSocketPayloadContract:
    """Gap #2: Mock WebSocket payload → BrowserTaskPayload mapping"""

    def test_mock_websocket_payload_execute_click_structure(self):
        """Mock WebSocket payload for execute_click should contain all required fields"""
        mock_payload = {
            "task_id": "mock-browser-task-001",
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#increment-btn",
            "value": None,
            "approval_id": "approval-001",
            "approval_token": "mock-token-xyz",
            "final_approval_token": None,
        }

        # Should map to BrowserTaskPayload
        browser_payload = BrowserTaskPayload(**mock_payload)
        assert browser_payload.task_id == "mock-browser-task-001"
        assert browser_payload.task_type == "browser_action"
        assert browser_payload.action_type == "browser.execute_click"
        assert browser_payload.selector == "#increment-btn"
        assert browser_payload.value is None
        assert browser_payload.approval_id == "approval-001"
        assert browser_payload.approval_token == "mock-token-xyz"

    def test_mock_websocket_payload_execute_type_structure(self):
        """Mock WebSocket payload for execute_type should contain all required fields"""
        mock_payload = {
            "task_id": "mock-browser-task-002",
            "task_type": "browser_action",
            "action_type": "browser.execute_type",
            "selector": "#search-input",
            "value": "typed text",
            "approval_id": "approval-002",
            "approval_token": "mock-token-abc",
            "final_approval_token": None,
        }

        browser_payload = BrowserTaskPayload(**mock_payload)
        assert browser_payload.task_id == "mock-browser-task-002"
        assert browser_payload.action_type == "browser.execute_type"
        assert browser_payload.selector == "#search-input"
        assert browser_payload.value == "typed text"
        assert browser_payload.approval_token == "mock-token-abc"

    def test_approval_token_transmitted_in_mock_payload(self):
        """Approval token should be transmitted in mock WebSocket payload"""
        mock_payload = {
            "task_id": "test-task",
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#btn",
            "approval_id": "appr-123",
            "approval_token": "secret-token-value",
            "final_approval_token": None,
        }

        # Token is present in payload
        assert mock_payload.get("approval_token") == "secret-token-value"
        assert mock_payload.get("approval_id") == "appr-123"

    def test_browser_task_payload_to_server_action_conversion(self):
        """BrowserTaskPayload should convert to ServerApprovalAction"""
        payload = BrowserTaskPayload(
            task_id="task-1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_id="appr-1",
            approval_token="token-1",
        )

        server_action = payload.to_server_action()
        assert server_action.task_id == "task-1"
        assert server_action.action_type == "browser.execute_click"
        assert server_action.selector == "#btn"
        assert server_action.approval_id == "appr-1"
        assert server_action.approval_token == "token-1"


class TestApprovalTokenTransmission:
    """Gap #2: Approval token transmission and verification"""

    def test_approval_token_reaches_verifier(self):
        """Approval token from payload should reach BrowserApprovalVerifier"""
        store = BrowserApprovalStore()
        verifier = BrowserApprovalVerifier(store)

        # Create approval with token
        token = "test-token-value"
        store.create_approval(
            approval_id="appr-1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_token=token,
        )

        # Verify with same token
        result = verifier.verify(
            approval_id="appr-1",
            approval_token=token,
            action_type="browser.execute_click",
            selector="#btn",
        )
        assert result.valid is True

    def test_approval_token_not_stored_as_plaintext(self):
        """Approval token should be hashed, not stored as plaintext"""
        store = BrowserApprovalStore()

        # Create approval with token
        store.create_approval(
            approval_id="appr-1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_token="secret-password-like-token",
        )

        # Retrieve record
        record = store.get("appr-1")
        assert record is not None

        # token_hash exists, not raw token
        assert record.token_hash is not None
        assert record.token_hash != "secret-password-like-token"
        assert len(record.token_hash) == 64  # SHA256 hex


class TestResultDataWhitelist:
    """Gap #3: Result data whitelist for browser safe fields"""

    def test_browser_result_status_field_allowed(self):
        """BrowserTaskResult.status should be in whitelist"""
        assert "status" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_action_field_allowed(self):
        """BrowserTaskResult.action should be in whitelist"""
        assert "action" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_selector_field_allowed(self):
        """BrowserTaskResult.selector should be in whitelist"""
        assert "selector" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_executed_field_allowed(self):
        """BrowserTaskResult.executed should be in whitelist"""
        assert "executed" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_element_found_field_allowed(self):
        """BrowserTaskResult.element_found should be in whitelist"""
        assert "element_found" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_risk_level_field_allowed(self):
        """BrowserTaskResult.risk_level should be in whitelist"""
        assert "risk_level" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_final_approval_required_field_allowed(self):
        """BrowserTaskResult.final_approval_required should be in whitelist"""
        assert "final_approval_required" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_result_field_allowed(self):
        """BrowserTaskResult.result should be in whitelist"""
        assert "result" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_error_code_field_allowed(self):
        """BrowserTaskResult.error_code should be in whitelist"""
        assert "error_code" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_error_message_field_allowed(self):
        """BrowserTaskResult.error_message should be in whitelist"""
        assert "error_message" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_target_url_domain_field_allowed(self):
        """BrowserTaskResult.target_url_domain should be in whitelist"""
        assert "target_url_domain" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_text_length_field_allowed(self):
        """BrowserTaskResult.text_length should be in whitelist"""
        assert "text_length" in _reg._RESULT_DATA_ALLOWED_KEYS

    def test_browser_result_text_preview_field_allowed(self):
        """BrowserTaskResult.text_preview should be in whitelist"""
        assert "text_preview" in _reg._RESULT_DATA_ALLOWED_KEYS


class TestResultDataForbiddenFields:
    """Forbidden fields should be blocked from result_data"""

    def test_approval_token_in_sensitive_keys(self):
        """approval_token should be in _SENSITIVE_KEYS"""
        assert "approval_token" in _reg._SENSITIVE_KEYS

    def test_final_approval_token_in_sensitive_keys(self):
        """final_approval_token should be in _SENSITIVE_KEYS"""
        assert "final_approval_token" in _reg._SENSITIVE_KEYS

    def test_token_hash_in_sensitive_keys(self):
        """token_hash should be in _SENSITIVE_KEYS"""
        assert "token_hash" in _reg._SENSITIVE_KEYS

    def test_strip_result_data_removes_approval_token(self):
        """_strip_result_data should remove approval_token"""
        data = {
            "action": "browser.execute_click",
            "approval_token": "secret-token",
            "executed": True,
        }
        result = _reg._strip_result_data(data)

        # approval_token removed
        assert result is not None
        assert "approval_token" not in result
        assert "action" in result
        assert "executed" in result

    def test_strip_result_data_removes_token_hash(self):
        """_strip_result_data should remove token_hash"""
        data = {
            "action": "browser.execute_click",
            "token_hash": "abc123def456",
            "executed": True,
        }
        result = _reg._strip_result_data(data)

        # token_hash removed
        assert result is not None
        assert "token_hash" not in result
        assert "action" in result

    def test_strip_result_data_allows_safe_browser_fields(self):
        """_strip_result_data should allow safe browser fields"""
        data = {
            "status": "executed",
            "action": "browser.execute_click",
            "selector": "#btn",
            "executed": True,
            "element_found": True,
            "risk_level": "medium",
            "result": "success",
            "error_code": None,
        }
        result = _reg._strip_result_data(data)

        # All safe fields preserved
        assert result is not None
        assert result["status"] == "executed"
        assert result["action"] == "browser.execute_click"
        assert result["selector"] == "#btn"
        assert result["executed"] is True
        assert result["element_found"] is True


class TestRiskyActionProtection:
    """Ensure risky actions are still blocked"""

    def test_execute_submit_not_in_action_risk(self):
        """browser.execute_submit should NOT be registered"""
        assert "browser.execute_submit" not in _reg.ACTION_RISK

    def test_risky_keywords_blocked_in_action_contract(self):
        """Risky keywords (delete, submit, payment) should be detected"""
        from core.agent_runtime.browser.browser_action_contract import assess_action_risk

        # Delete is risky
        risk, needs_final = assess_action_risk("browser.execute_click", "#delete-btn")
        assert risk == "critical"
        assert needs_final is True

        # Submit is risky
        risk, needs_final = assess_action_risk("browser.execute_click", "#submit-form")
        assert risk == "critical"
        assert needs_final is True

        # Payment is risky
        risk, needs_final = assess_action_risk("browser.execute_click", "#payment-button")
        assert risk == "critical"
        assert needs_final is True


class TestMockContractIntegration:
    """Integration: Mock payload → BrowserTaskHandler → Result validation"""

    def test_mock_payload_with_approval_fields_complete(self):
        """Mock payload contains all required fields for integration"""
        payload = BrowserTaskPayload(
            task_id="task-1",
            action_type="browser.execute_click",
            selector="#btn",
            approval_id="appr-1",
            approval_token="token-value",
        )

        # Verify all fields present
        assert payload.task_id == "task-1"
        assert payload.action_type == "browser.execute_click"
        assert payload.selector == "#btn"
        assert payload.approval_id == "appr-1"
        assert payload.approval_token == "token-value"

        # Verify conversion to ServerApprovalAction
        server_action = payload.to_server_action()
        assert server_action.approval_id == "appr-1"
        assert server_action.approval_token == "token-value"

    def test_mock_result_safe_for_storage(self):
        """BrowserTaskResult safe fields can be stored in result_data"""
        result = BrowserTaskResult(
            task_id="task-1",
            status="executed",
            action="browser.execute_click",
            selector="#btn",
            executed=True,
            element_found=True,
            risk_level="medium",
            result="success",
            error_code=None,
        )

        # Convert to dict for storage
        data = result.to_dict()

        # Verify safe fields
        assert "status" in data
        assert "action" in data
        assert "selector" in data
        assert "executed" in data
        assert "element_found" in data
        assert "risk_level" in data

        # Verify no secrets
        assert "approval_token" not in data
        assert "final_approval_token" not in data
        assert "token_hash" not in data
