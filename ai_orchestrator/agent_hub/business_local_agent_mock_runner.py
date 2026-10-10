"""범용 업무 local agent mock runner — business.* handoff 검증용.

실제 브라우저, ERP, 파일 시스템을 사용하지 않고 mock 결과를 반환한다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def run_mock_business_local_agent(
    handoff_payload: dict[str, Any],
    business_profile: str,
) -> dict[str, Any]:
    """
    business.* handoff_payload를 받아 mock 실행 결과를 반환한다.

    입력:
    - handoff_payload: business.execute_with_user_approval이 생성한 payload
    - business_profile: bid_submission, erp_save, erp_submit_approval,
                       document_submission, public_agency_upload, esign_request

    출력:
    - result_status: "completed" 또는 "failed"
    - verdict: "SUCCESS" 또는 "ERROR"
    - business_profile: 입력과 동일
    - local_agent_run_id: UUID
    - executed_at: ISO 8601 timestamp
    - result_fields_safe: safe field만 포함
    - evidence_files_ref: (선택) 저장된 파일 참조

    금지:
    - 실제 브라우저 실행
    - 실제 외부 URL 접속
    - cookie, session, storage_state 반환
    - password, otp, cert_password, private_key 반환
    """
    run_id = str(uuid.uuid4())
    executed_at = datetime.now(timezone.utc).isoformat()

    if business_profile == "erp_save":
        return _mock_erp_save(handoff_payload, run_id, executed_at)
    elif business_profile == "document_submission":
        return _mock_document_submission(handoff_payload, run_id, executed_at)
    elif business_profile == "public_agency_upload":
        return _mock_public_agency_upload(handoff_payload, run_id, executed_at)
    elif business_profile == "esign_request":
        return _mock_esign_request(handoff_payload, run_id, executed_at)
    else:
        return {
            "result_status": "failed",
            "verdict": "ERROR",
            "business_profile": business_profile,
            "local_agent_run_id": run_id,
            "executed_at": executed_at,
            "error": f"미지원 프로필: {business_profile}",
            "result_fields_safe": {},
        }


def _mock_erp_save(
    payload: dict[str, Any],
    run_id: str,
    executed_at: str,
) -> dict[str, Any]:
    """ERP 저장 mock."""
    return {
        "result_status": "completed",
        "verdict": "SUCCESS",
        "business_profile": "erp_save",
        "local_agent_run_id": run_id,
        "executed_at": executed_at,
        "result_fields_safe": {
            "erp_name": payload.get("erp_name", ""),
            "record_type": payload.get("record_type", ""),
            "record_title": payload.get("record_title", ""),
            "saved_record_id": "ERP_REC_20260509_001",
            "save_status": "SUCCESS",
            "saved_at": executed_at,
        },
        "evidence_files_ref": [
            "erp_save_log_20260509.txt",
        ],
    }


def _mock_document_submission(
    payload: dict[str, Any],
    run_id: str,
    executed_at: str,
) -> dict[str, Any]:
    """문서 제출 mock."""
    return {
        "result_status": "completed",
        "verdict": "SUCCESS",
        "business_profile": "document_submission",
        "local_agent_run_id": run_id,
        "executed_at": executed_at,
        "result_fields_safe": {
            "document_title": payload.get("document_title", ""),
            "recipient_or_organization": payload.get("recipient_or_organization", ""),
            "submission_id": "DOC_SUB_20260509_001",
            "submission_status": "ACCEPTED",
            "submitted_at": executed_at,
        },
        "evidence_files_ref": [
            "document_submission_receipt.txt",
        ],
    }


def _mock_public_agency_upload(
    payload: dict[str, Any],
    run_id: str,
    executed_at: str,
) -> dict[str, Any]:
    """공공기관 업로드 mock."""
    return {
        "result_status": "completed",
        "verdict": "SUCCESS",
        "business_profile": "public_agency_upload",
        "local_agent_run_id": run_id,
        "executed_at": executed_at,
        "result_fields_safe": {
            "agency_name": payload.get("agency_name", ""),
            "application_title": payload.get("application_title", ""),
            "application_id": "PUB_AGCY_20260509_001",
            "upload_status": "COMPLETED",
            "uploaded_at": executed_at,
        },
        "evidence_files_ref": [
            "agency_upload_confirmation.txt",
        ],
    }


def _mock_esign_request(
    payload: dict[str, Any],
    run_id: str,
    executed_at: str,
) -> dict[str, Any]:
    """전자서명 요청 mock."""
    return {
        "result_status": "completed",
        "verdict": "SUCCESS",
        "business_profile": "esign_request",
        "local_agent_run_id": run_id,
        "executed_at": executed_at,
        "result_fields_safe": {
            "document_title": payload.get("document_title", ""),
            "signer_name": payload.get("signer_name", ""),
            "signature_request_id": "ESIGN_REQ_20260509_001",
            "signature_status": "PENDING_SIGNATURE",
            "requested_at": executed_at,
        },
        "evidence_files_ref": [
            "esign_request_confirmation.txt",
        ],
    }
