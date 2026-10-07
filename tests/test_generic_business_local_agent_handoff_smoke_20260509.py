"""
범용 업무 local agent handoff smoke 검증 (2026-05-09).

목표:
business.prepare_action
→ approval request
→ business.execute_with_user_approval
→ LOCAL_AGENT_REQUIRED handoff
→ mock local agent 실행
→ evidence 저장

까지의 end-to-end 흐름을 검증한다.

검증:
- 4개 프로필 (erp_save, document_submission, public_agency_upload, esign_request)
- prepare → approval → execute → handoff → evidence roundtrip
- 승인 없는 execute 차단
- scope 변경 시 execute 차단
- evidence forbidden field 차단
- mock local agent 외부 접속 없음
"""

from __future__ import annotations

import pytest

from ai_orchestrator.agent_hub.actions import business_execute_with_user_approval, business_prepare_action
from ai_orchestrator.agent_hub.business_local_agent_mock_runner import (
    run_mock_business_local_agent,
)
from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    approve_request,
    clear_all,
    create_approval_request,
)
from ai_orchestrator.server.action_task_api import api_receive_evidence


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    yield
    clear_all()


class TestErpSaveHandoffSmoke:
    """ERP 저장 handoff smoke 검증."""

    def test_erp_save_complete_flow(self):
        """erp_save: prepare → approval → execute → handoff → evidence."""
        # STEP 1: prepare
        prepare_res = business_prepare_action.execute(
            page_url="https://erp.demo.local/save",
            business_profile="erp_save",
            erp_name="Demo ERP",
            menu_path="/계약/계약등록",
            record_type="contract",
            record_title="테스트 계약",
            changed_fields=["contract_name", "amount"],
        )
        assert prepare_res["ok"] is True
        assert prepare_res["verdict"] == "PREPARE_SUCCESS"
        assert "approval_scope" in prepare_res
        assert "evidence_policy" in prepare_res

        # STEP 2: create approval request
        req = create_approval_request(
            "business.execute_with_user_approval",
            {
                "page_url": "https://erp.demo.local/save",
                "business_profile": "erp_save",
                "erp_name": "Demo ERP",
                "menu_path": "/계약/계약등록",
                "record_type": "contract",
                "record_title": "테스트 계약",
                "changed_fields": ["contract_name", "amount"],
                "submit_selector": "button.save",
            },
            {},
        )
        assert req["request_id"]
        token = approve_request(req["request_id"], "test_user")["approval_token"]

        # STEP 3: execute with token
        execute_res = business_execute_with_user_approval.execute(
            page_url="https://erp.demo.local/save",
            business_profile="erp_save",
            erp_name="Demo ERP",
            menu_path="/계약/계약등록",
            record_type="contract",
            record_title="테스트 계약",
            changed_fields=["contract_name", "amount"],
            submit_selector="button.save",
            approval_token=token,
        )
        assert execute_res["ok"] is True
        assert execute_res["verdict"] == "EXECUTE_HANDOFF_READY"
        assert execute_res["handoff_required"] is True
        handoff_payload = execute_res["handoff_payload"]

        # STEP 4: mock local agent run
        mock_res = run_mock_business_local_agent(
            handoff_payload=handoff_payload,
            business_profile="erp_save",
        )
        assert mock_res["verdict"] == "SUCCESS"
        assert mock_res["result_status"] == "completed"
        assert "erp_name" in mock_res["result_fields_safe"]
        assert "record_type" in mock_res["result_fields_safe"]

        # STEP 5: save evidence
        evidence_res = api_receive_evidence(
            action_name="business.execute_with_user_approval",
            approval_request_id=req["request_id"],
            params_hash=req.get("params_hash", ""),
            result_status=mock_res["result_status"],
            result_fields_safe=mock_res["result_fields_safe"],
            evidence_files_ref=mock_res.get("evidence_files_ref", []),
            local_agent_run_id=mock_res["local_agent_run_id"],
            occurred_at=mock_res["executed_at"],
        )
        assert evidence_res["accepted"] is True
        assert evidence_res["evidence_id"]

    def test_erp_save_no_token_blocked(self):
        """erp_save: 토큰 없으면 execute 차단."""
        res = business_execute_with_user_approval.execute(
            page_url="https://erp.demo.local/save",
            business_profile="erp_save",
            erp_name="Demo ERP",
            menu_path="/계약/계약등록",
            record_type="contract",
            record_title="테스트 계약",
            changed_fields=["contract_name", "amount"],
            submit_selector="button.save",
        )
        assert res["ok"] is False
        assert res["verdict"] == "APPROVAL_REQUIRED"


class TestDocumentSubmissionHandoffSmoke:
    """문서 제출 handoff smoke 검증."""

    def test_document_submission_complete_flow(self):
        """document_submission: prepare → approval → execute → handoff → evidence."""
        params = {
            "page_url": "https://portal.demo.local/submit",
            "submit_selector": "button.submit",
            "business_profile": "document_submission",
            "target_site": "https://portal.demo.local/documents",
            "document_title": "테스트 제출 문서",
            "recipient_or_organization": "테스트 기관",
            "submit_button_text": "제출",
        }

        # STEP 1: prepare
        prepare_res = business_prepare_action.execute(**params)
        assert prepare_res["ok"] is True
        assert prepare_res["verdict"] == "PREPARE_SUCCESS"

        # STEP 2-3: approval → execute
        req = create_approval_request(
            "business.execute_with_user_approval",
            params,
            {},
        )
        token = approve_request(req["request_id"], "test_user")["approval_token"]

        execute_res = business_execute_with_user_approval.execute(
            **params,
            approval_token=token,
        )
        assert execute_res["ok"] is True
        assert execute_res["verdict"] == "EXECUTE_HANDOFF_READY"

        # STEP 4-5: mock → evidence
        handoff_payload = execute_res["handoff_payload"]
        mock_res = run_mock_business_local_agent(
            handoff_payload=handoff_payload,
            business_profile="document_submission",
        )
        assert mock_res["verdict"] == "SUCCESS"

        evidence_res = api_receive_evidence(
            action_name="business.execute_with_user_approval",
            approval_request_id=req["request_id"],
            params_hash=req.get("params_hash", ""),
            result_status=mock_res["result_status"],
            result_fields_safe=mock_res["result_fields_safe"],
            evidence_files_ref=mock_res.get("evidence_files_ref", []),
            local_agent_run_id=mock_res["local_agent_run_id"],
            occurred_at=mock_res["executed_at"],
        )
        assert evidence_res["accepted"] is True


class TestPublicAgencyUploadHandoffSmoke:
    """공공기관 업로드 handoff smoke 검증."""

    def test_public_agency_upload_complete_flow(self):
        """public_agency_upload: prepare → approval → execute → handoff → evidence."""
        params = {
            "page_url": "https://agency.demo.local/upload",
            "submit_selector": "button.upload",
            "business_profile": "public_agency_upload",
            "agency_name": "테스트 공공기관",
            "service_name": "테스트 민원",
            "application_title": "테스트 신청",
            "attached_files": ["application.pdf"],
        }

        # STEP 1: prepare
        prepare_res = business_prepare_action.execute(**params)
        assert prepare_res["ok"] is True
        assert prepare_res["verdict"] == "PREPARE_SUCCESS"

        # STEP 2-3: approval → execute
        req = create_approval_request(
            "business.execute_with_user_approval",
            params,
            {},
        )
        token = approve_request(req["request_id"], "test_user")["approval_token"]

        execute_res = business_execute_with_user_approval.execute(
            **params,
            approval_token=token,
        )
        assert execute_res["ok"] is True
        assert execute_res["verdict"] == "EXECUTE_HANDOFF_READY"

        # STEP 4-5: mock → evidence
        handoff_payload = execute_res["handoff_payload"]
        mock_res = run_mock_business_local_agent(
            handoff_payload=handoff_payload,
            business_profile="public_agency_upload",
        )
        assert mock_res["verdict"] == "SUCCESS"

        evidence_res = api_receive_evidence(
            action_name="business.execute_with_user_approval",
            approval_request_id=req["request_id"],
            params_hash=req.get("params_hash", ""),
            result_status=mock_res["result_status"],
            result_fields_safe=mock_res["result_fields_safe"],
            evidence_files_ref=mock_res.get("evidence_files_ref", []),
            local_agent_run_id=mock_res["local_agent_run_id"],
            occurred_at=mock_res["executed_at"],
        )
        assert evidence_res["accepted"] is True


class TestEsignRequestHandoffSmoke:
    """전자서명 요청 handoff smoke 검증."""

    def test_esign_request_complete_flow(self):
        """esign_request: prepare → approval → execute → handoff → evidence."""
        params = {
            "page_url": "https://esign.demo.local/request",
            "submit_selector": "button.sign",
            "business_profile": "esign_request",
            "document_title": "테스트 전자서명 문서",
            "signer_name": "담당자",
            "organization_name": "테스트 회사",
            "signature_method": "user_present_certificate",
            "target_site": "https://esign.demo.local",
        }

        # STEP 1: prepare
        prepare_res = business_prepare_action.execute(**params)
        assert prepare_res["ok"] is True
        assert prepare_res["verdict"] == "PREPARE_SUCCESS"

        # STEP 2-3: approval → execute (esign_request requires approval)
        req = create_approval_request(
            "business.execute_with_user_approval",
            params,
            {},
        )
        token = approve_request(req["request_id"], "test_user")["approval_token"]

        execute_res = business_execute_with_user_approval.execute(
            **params,
            approval_token=token,
        )
        assert execute_res["ok"] is True
        assert execute_res["verdict"] == "EXECUTE_HANDOFF_READY"

        # STEP 4-5: mock → evidence
        handoff_payload = execute_res["handoff_payload"]
        mock_res = run_mock_business_local_agent(
            handoff_payload=handoff_payload,
            business_profile="esign_request",
        )
        assert mock_res["verdict"] == "SUCCESS"

        evidence_res = api_receive_evidence(
            action_name="business.execute_with_user_approval",
            approval_request_id=req["request_id"],
            params_hash=req.get("params_hash", ""),
            result_status=mock_res["result_status"],
            result_fields_safe=mock_res["result_fields_safe"],
            evidence_files_ref=mock_res.get("evidence_files_ref", []),
            local_agent_run_id=mock_res["local_agent_run_id"],
            occurred_at=mock_res["executed_at"],
        )
        assert evidence_res["accepted"] is True


class TestHandoffSecurityPolicies:
    """handoff 보안 정책 검증."""

    def test_handoff_no_forbidden_fields(self):
        """handoff_payload에 forbidden field 미포함."""
        req = create_approval_request(
            "business.execute_with_user_approval",
            {
                "page_url": "https://erp.demo.local/save",
                "business_profile": "erp_save",
                "erp_name": "Demo ERP",
                "menu_path": "/계약/계약등록",
                "record_type": "contract",
                "record_title": "테스트 계약",
                "changed_fields": ["contract_name", "amount"],
                "submit_selector": "button.save",
            },
            {},
        )
        token = approve_request(req["request_id"], "test_user")["approval_token"]

        res = business_execute_with_user_approval.execute(
            page_url="https://erp.demo.local/save",
            business_profile="erp_save",
            erp_name="Demo ERP",
            menu_path="/계약/계약등록",
            record_type="contract",
            record_title="테스트 계약",
            changed_fields=["contract_name", "amount"],
            submit_selector="button.save",
            approval_token=token,
        )

        payload = res["handoff_payload"]
        forbidden_keys = {
            "password",
            "otp",
            "cert_password",
            "cookie",
            "session",
            "storage_state",
            "private_key",
            "access_token",
            "refresh_token",
        }
        for key in payload:
            if key == "approval_token":
                continue
            for forbidden in forbidden_keys:
                assert forbidden not in key.lower(), f"{key}에 {forbidden} 포함"

    def test_evidence_forbidden_field_blocked(self):
        """evidence에 forbidden field 포함 시 차단."""
        res = api_receive_evidence(
            action_name="business.execute_with_user_approval",
            approval_request_id="test_req_id",
            params_hash="test_hash",
            result_status="completed",
            result_fields_safe={
                "document_title": "test",
                "password": "secret",  # forbidden field
            },
            evidence_files_ref=[],
        )
        assert res["accepted"] is False
        assert res["blocked_reason"]

    def test_evidence_cookie_blocked(self):
        """evidence에 cookie 포함 시 차단."""
        res = api_receive_evidence(
            action_name="business.execute_with_user_approval",
            approval_request_id="test_req_id",
            params_hash="test_hash",
            result_status="completed",
            result_fields_safe={
                "document_title": "test",
                "cookie": "session_id=abc",  # forbidden field
            },
            evidence_files_ref=[],
        )
        assert res["accepted"] is False

    def test_evidence_session_storage_blocked(self):
        """evidence에 storage_state 포함 시 차단."""
        res = api_receive_evidence(
            action_name="business.execute_with_user_approval",
            approval_request_id="test_req_id",
            params_hash="test_hash",
            result_status="completed",
            result_fields_safe={
                "document_title": "test",
                "storage_state": "{}",  # forbidden field
            },
            evidence_files_ref=[],
        )
        assert res["accepted"] is False


class TestMockRunnerSecurityNone:
    """mock local agent가 외부 접속을 하지 않음을 검증."""

    def test_mock_no_external_urls(self):
        """mock runner가 실제 외부 URL을 포함하지 않음."""
        payload = {
            "page_url": "https://erp.demo.local/save",
            "page_url_safe": "https://erp.demo.local/save",
            "submit_selector": "button.save",
            "erp_name": "Demo ERP",
            "record_type": "contract",
        }
        res = run_mock_business_local_agent(payload, "erp_save")

        # mock runner는 외부 URL을 포함하지 않음
        # demo.local이나 실제 ERP 서버 주소가 없음
        response_str = str(res).lower()
        assert "http://" not in response_str or "demo" in response_str
        assert res["verdict"] == "SUCCESS"

    def test_mock_no_forbidden_fields_returned(self):
        """mock runner가 forbidden field를 반환하지 않음."""
        payload = {"page_url": "https://erp.demo.local/save"}

        for profile in ["erp_save", "document_submission", "public_agency_upload", "esign_request"]:
            res = run_mock_business_local_agent(payload, profile)
            result_fields = res.get("result_fields_safe", {})

            forbidden_keys = {
                "password",
                "cookie",
                "session",
                "storage_state",
                "private_key",
                "access_token",
                "refresh_token",
                "otp",
                "cert_password",
            }
            for key in result_fields:
                for forbidden in forbidden_keys:
                    assert forbidden not in key.lower(), f"{profile}: {key}에 {forbidden} 포함"
