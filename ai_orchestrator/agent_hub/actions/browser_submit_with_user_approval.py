"""browser.submit_with_user_approval — 사용자 승인 후 제출 실행 (1회용).

- USER_DIRECT: 승인 토큰 필수
- 승인 토큰 검증 (1회용 + 만료 + scope-bound)
- 실제 제출 클릭은 LOCAL_AGENT_REQUIRED로만 handoff
- 서버에서 직접 클릭 안 함
- 쿠키/session/storage_state 추출 안 함
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.agent_hub.action_evidence_collector import collect_evidence
from ai_orchestrator.agent_hub.action_registry import register_handler
from ai_orchestrator.agent_hub.policy.user_approval_gate import verify_and_consume_token

ACTION_NAME = "browser.submit_with_user_approval"


def execute(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page_url: str,
    submit_selector: str,
    approval_token: str,
    submit_button_text: str = "Submit",
    target_id: str = "",
    organization_name: str = "",
    amount: str = "",
    due_date: str = "",
    expected_result_markers: list[str] | None = None,
    evidence_requirements: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
    headless: bool = True,
) -> dict[str, Any]:
    """
    사용자 승인 후 제출 실행 handoff 생성.

    1. 승인 토큰 검증 (1회용 + 만료 + scope-bound)
    2. 토큰 PASS 시 local agent로 handoff payload 생성
    3. 실제 제출은 local agent에서만 수행
    4. 서버에서 직접 클릭 안 함

    반환: handoff payload (local agent가 실행할 정보)
    """
    if not page_url or not submit_selector:
        return {"ok": False, "verdict": "ERROR", "error": "page_url/submit_selector 필요"}

    if not approval_token:
        return {"ok": False, "verdict": "APPROVAL_REQUIRED", "error": "승인 토큰 필요"}

    # 승인 검증 (sanitize된 params hash로 검증)
    # prepare_submit의 summary_fields와 일치하는 필드만 포함
    params_for_verify = {
        "page_url": page_url,
        "submit_selector": submit_selector,
        "target_id": target_id,
        "organization_name": organization_name,
        "amount": amount,
        "due_date": due_date,
    }

    verify = verify_and_consume_token(approval_token, ACTION_NAME, params_for_verify)
    if not verify["ok"]:
        return {
            "ok": False,
            "verdict": "APPROVAL_REJECTED",
            "approval_status": "INVALID",
            "reason": verify["reason"],
        }

    # URL safe format
    try:
        parsed_url = urlparse(page_url)
        safe_url = f"{parsed_url.scheme}://{parsed_url.hostname or ''}{parsed_url.path or ''}"
    except Exception:  # noqa: BLE001 - 감사로그 표시용 safe_url 생성 실패 시 '(invalid_url)' 플레이스홀더 사용 — verify_and_consume_token 승인 검증을 이미 통과한 이후 단계이므로 게이트 판정과 무관
        safe_url = "(invalid_url)"

    # 실제 제출은 handoff로 — 서버에서 실행하지 않음
    handoff_payload = {
        "action_name": ACTION_NAME,
        "page_url_safe": safe_url,
        "submit_selector": submit_selector,
        "submit_button_text": submit_button_text,
        "target_id": target_id,
        "organization_name": organization_name,
        "amount": amount,
        "due_date": due_date,
        "approval_request_id": verify.get("request_id"),
        "approval_token": approval_token,  # local agent에서 evidence 기록용
        "expected_result_markers": expected_result_markers or [],
        "evidence_requirements": evidence_requirements or {},
        "timeout_seconds": timeout_seconds,
        "headless": headless,
        "created_at": datetime.now(UTC).isoformat(),
    }

    raw: dict[str, Any] = {
        "ok": True,
        "verdict": "SUBMIT_HANDOFF_READY",
        "approval_status": "APPROVED_AND_CONSUMED",
        "approval_request_id": verify.get("request_id"),
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "handoff_required": True,
        "handoff_payload": handoff_payload,
    }

    evidence = collect_evidence(ACTION_NAME, raw)
    raw["evidence"] = evidence

    return raw


# registry 등록
register_handler(ACTION_NAME, execute)
