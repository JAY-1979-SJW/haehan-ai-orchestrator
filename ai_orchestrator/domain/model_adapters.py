"""Domain Core 모델 ↔ 기존 registry/dict 변환 adapter.

역할:
- external_work_registry.ExternalWorkEntry → ExternalWork 변환 (read-only)
- 연동 정적 목록(domain/integrations_static) dict → Integration 변환 (read-only)
- External App Bridge 분류 → ExternalAppBridge 변환 (read-only)
- 기존 Safety Policy 분산 항목 → SafetyPolicy 요약 변환 (read-only)

금지:
- 기존 registry 원본 수정 금지
- 외부 호출 금지
- DB write 금지
- secret/token/password 포함 금지
"""

from __future__ import annotations

from typing import Any

from .models import (
    ExternalAppBridge,
    ExternalWork,
    HandoffMode,
    Integration,
    IntegrationStatus,
    SafetyDecision,
    SafetyPolicy,
)

# ===========================================================================
# ExternalWork adapter
# ===========================================================================


def adapt_external_work_entry(entry: Any) -> ExternalWork:
    """ExternalWorkEntry (기존 registry frozen dataclass) → ExternalWork 변환.

    기존 registry를 수정하지 않는 read-only 변환.
    """
    # 분류 → 상태 매핑
    classification = getattr(entry, "classification", "QUARANTINE_OR_HOLD")
    _status_map = {
        "SERVER_READONLY_ALLOWED": "active",
        "WEB_TASK_REGISTRY": "active",
        "LOCAL_AGENT_REQUIRED": "active",
        "OFFICIAL_API_OR_OAUTH_REQUIRED": "setup_required",
        "USER_DIRECT_REQUIRED": "active",
        "QUARANTINE_OR_HOLD": "hold",
        "EXTERNAL_APP_HOLD": "hold",
        "FUTURE_INTEGRATION": "future",
        "IN_SCOPE": "active",
    }
    status = _status_map.get(classification, "hold")

    # 승인 필요 여부: high/critical 또는 write 액션
    risk_level = getattr(entry, "risk_level", "low")
    approval_required = risk_level in ("high", "critical")

    # auth_mode 추정
    exec_loc = getattr(entry, "execution_location", "SERVER")
    _auth_map = {
        "SERVER": "none",
        "LOCAL_AGENT": "browser_session",
        "USER_DIRECT": "user_direct",
        "OFFICIAL_API": "oauth",
    }
    auth_mode = _auth_map.get(exec_loc, "unknown")

    # ExecutionLocation 값 정규화
    _exec_loc_map = {
        "SERVER": "SERVER_INTERNAL_ONLY",
        "LOCAL_AGENT": "LOCAL_AGENT_REQUIRED",
        "USER_DIRECT": "USER_DIRECT_REQUIRED",
        "OFFICIAL_API": "SERVER_INTERNAL_ONLY",
    }
    exec_location_normalized = _exec_loc_map.get(exec_loc, exec_loc)

    return ExternalWork(
        external_work_id=f"ew-{getattr(entry, 'work_key', 'unknown').replace('/', '-')}",
        provider=getattr(entry, "provider", "unknown"),
        action_type=getattr(entry, "work_type", "unknown"),
        category=classification,
        execution_location=exec_location_normalized,
        risk_level=risk_level,
        approval_required=approval_required,
        auth_mode=auth_mode,
        status=status,
        description=getattr(entry, "description", ""),
        safety_notice=getattr(entry, "safety_notice", ""),
    )


def list_external_works_as_models() -> list[ExternalWork]:
    """기존 external_work_registry 전체를 ExternalWork 모델 목록으로 반환."""
    try:
        from ai_orchestrator.tasks.external_work_registry import list_external_works

        entries = list_external_works()
        return [adapt_external_work_entry(e) for e in entries]
    except Exception:  # noqa: BLE001 - 외부 앱/작업 어댑터 목록 조회 -- 조회 실패 시 빈 리스트 반환, 읽기 전용
        return []


# ===========================================================================
# Integration adapter
# ===========================================================================

_AUTH_MODE_STATUS_MAP: dict[str, str] = {
    "none": IntegrationStatus.CONNECTED,
    "bot_token": IntegrationStatus.CONNECTED,
    "browser_session": IntegrationStatus.SETUP_REQUIRED,
    "oauth": IntegrationStatus.SETUP_REQUIRED,
    "api_key": IntegrationStatus.SETUP_REQUIRED,
}


def adapt_static_integration(raw: dict[str, Any]) -> Integration:
    """ops_router._STATIC_INTEGRATIONS dict → Integration 모델 변환."""
    key = raw.get("key", "unknown")
    auth_method = raw.get("authMethod", "none")
    connected = raw.get("connected", False)

    if connected:
        status = IntegrationStatus.CONNECTED
    else:
        status = _AUTH_MODE_STATUS_MAP.get(auth_method, IntegrationStatus.SETUP_REQUIRED)

    classification = raw.get("classification", "IN_SCOPE")
    if classification == "QUARANTINE_OR_HOLD":
        status = IntegrationStatus.BLOCKED
    elif classification in ("FUTURE_INTEGRATION", "EXTERNAL_APP_HOLD"):
        status = IntegrationStatus.FUTURE_INTEGRATION

    return Integration(
        integration_id=f"int-{key}",
        name=raw.get("name", key),
        provider=key.split("-")[0] if "-" in key else key,
        integration_type=_infer_integration_type(key),
        status=status,
        auth_mode=auth_method,
        connected=connected,
        required_setup=raw.get("action") or raw.get("notes"),
        health="healthy" if connected else "unknown",
        notes=raw.get("notes", ""),
    )


def _infer_integration_type(key: str) -> str:
    _type_map = {
        "naver-search": "search",
        "naver-local-agent": "local_agent",
        "google-oauth": "oauth",
        "telegram": "bot",
        "hiworks": "email",
        "g2b": "government",
        "eum": "government",
    }
    for k, t in _type_map.items():
        if k in key:
            return t
    return "generic"


def list_integrations_as_models() -> list[Integration]:
    """연동 정적 목록(domain/integrations_static.py, ops_router 원본과 값 동기화) 전체를 Integration 모델 목록으로 반환."""
    try:
        from ai_orchestrator.domain.integrations_static import STATIC_INTEGRATIONS

        return [adapt_static_integration(raw) for raw in STATIC_INTEGRATIONS]
        # 참고: 레이어 위반 fix 시도(ops_router.py 직접 참조 제거)는 유지하되,
        # ops_router._STATIC_INTEGRATIONS 원본도 동일 값으로 존재함
        # (test_ops_router_read_only_20260516.py 가 ops_router.py 소스 텍스트에서
        # "cad-app" 리터럴을 직접 검사하므로 원본 리스트를 되돌림).
    except Exception:  # noqa: BLE001 - 외부 앱/작업 어댑터 목록 조회 -- 조회 실패 시 빈 리스트 반환, 읽기 전용
        return []


# ===========================================================================
# ExternalAppBridge adapter (분류 상수 기반)
# ===========================================================================

_BRIDGE_REGISTRY: dict[str, dict[str, Any]] = {
    "cad-bridge": {
        "app_type": "CAD",
        "capability": ("도면_작성", "도면_수정", "물량_산출", "내역서_연동"),
        "handoff_mode": HandoffMode.FILE_HANDOFF,
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "safety_policy_ids": ("pol-no-auto-submit", "pol-user-review"),
    },
    "hwpx-bridge": {
        "app_type": "HWPX",
        "capability": ("한글_문서_작성", "표_편집", "PDF_변환"),
        "handoff_mode": HandoffMode.FILE_HANDOFF,
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "safety_policy_ids": ("pol-no-auto-submit", "pol-user-review"),
    },
    "office-bridge": {
        "app_type": "OFFICE",
        "capability": ("Excel_작성", "Word_작성", "PowerPoint_작성"),
        "handoff_mode": HandoffMode.FILE_HANDOFF,
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "safety_policy_ids": ("pol-no-auto-submit", "pol-user-review"),
    },
    "tax-bridge": {
        "app_type": "TAX",
        "capability": ("세금계산서_조회", "부가세_신고_보조", "세무_서류_생성"),
        "handoff_mode": HandoffMode.USER_HANDOFF,
        "execution_location": "USER_DIRECT_REQUIRED",
        "safety_policy_ids": ("pol-user-direct-only", "pol-no-credential-store"),
    },
    "bid-bridge": {
        "app_type": "BID",
        "capability": ("나라장터_입찰", "전자입찰_보조", "입찰_현황_조회"),
        "handoff_mode": HandoffMode.USER_HANDOFF,
        "execution_location": "USER_DIRECT_REQUIRED",
        "safety_policy_ids": ("pol-no-bid-auto-execute", "pol-user-direct-only", "pol-no-credential-store"),
    },
    "doc-auto-bridge": {
        "app_type": "DOCUMENT_AUTOMATION",
        "capability": ("계약서_초안", "보고서_생성", "양식_자동완성"),
        "handoff_mode": HandoffMode.TEMPLATE_HANDOFF,
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "safety_policy_ids": ("pol-no-auto-sign", "pol-user-review"),
    },
}


def get_all_bridges() -> list[ExternalAppBridge]:
    """ExternalAppBridge 전체 목록을 반환 (FUTURE_INTEGRATION 상태)."""
    result = []
    for bridge_id, info in _BRIDGE_REGISTRY.items():
        result.append(
            ExternalAppBridge(
                bridge_id=bridge_id,
                app_type=info["app_type"],
                capability=info["capability"],
                handoff_mode=info["handoff_mode"],
                execution_location=info["execution_location"],
                approval_required=True,
                safety_policy_ids=info.get("safety_policy_ids", ()),
                status="FUTURE_INTEGRATION",
            )
        )
    return result


def get_bridge(bridge_id: str) -> ExternalAppBridge | None:
    """특정 bridge_id의 ExternalAppBridge 반환."""
    info = _BRIDGE_REGISTRY.get(bridge_id)
    if not info:
        return None
    return ExternalAppBridge(
        bridge_id=bridge_id,
        app_type=info["app_type"],
        capability=info["capability"],
        handoff_mode=info["handoff_mode"],
        execution_location=info["execution_location"],
        approval_required=True,
        safety_policy_ids=info.get("safety_policy_ids", ()),
        status="FUTURE_INTEGRATION",
    )


# ===========================================================================
# SafetyPolicy adapter (분산 정책 요약)
# ===========================================================================

_SAFETY_POLICY_SUMMARY: list[dict[str, Any]] = [
    {
        "policy_id": "pol-execution-location-guard",
        "name": "서버 외부 웹 실행 차단",
        "category": "execution",
        "severity": "critical",
        "applies_to": ("*",),
        "decision": SafetyDecision.BLOCK,
        "reason": "서버에서 외부 사이트 브라우저 접속 금지",
        "required_execution_location": "LOCAL_AGENT_REQUIRED",
        "impl": "server/execution_location_guard.py",
    },
    {
        "policy_id": "pol-approval-gate",
        "name": "고위험 작업 승인 게이트",
        "category": "approval",
        "severity": "block",
        "applies_to": ("risk_level:high", "risk_level:critical"),
        "decision": SafetyDecision.REQUIRE_APPROVAL,
        "reason": "high/critical 위험 작업은 승인 없이 실행 불가",
        "required_execution_location": None,
        "impl": "browser_tool/preflight/gate_approval_preflight.py",
    },
    {
        "policy_id": "pol-secret-redaction",
        "name": "Secret 차단 정책",
        "category": "redaction",
        "severity": "critical",
        "applies_to": ("*",),
        "decision": SafetyDecision.BLOCK,
        "reason": "password/otp/token/cookie 필드 출력/저장 금지",
        "required_execution_location": None,
        "impl": "local_agent/result_sanitizer.py + desktop/task_receiver.py",
    },
    {
        "policy_id": "pol-user-direct-required",
        "name": "사용자 직접 조작 필요 정책",
        "category": "execution",
        "severity": "warn",
        "applies_to": ("execution_location:USER_DIRECT_REQUIRED",),
        "decision": SafetyDecision.REQUIRE_USER_DIRECT,
        "reason": "비밀번호/OTP/전자서명은 사용자가 직접 입력해야 함",
        "required_execution_location": "USER_DIRECT_REQUIRED",
        "impl": "browser_tool/routing/execution_location_policy.py",
    },
    {
        "policy_id": "pol-external-app-hold",
        "name": "외부 전문 앱 보류 정책",
        "category": "hold",
        "severity": "warn",
        "applies_to": ("app_type:CAD", "app_type:HWPX", "app_type:OFFICE", "app_type:TAX", "app_type:BID"),
        "decision": SafetyDecision.HOLD,
        "reason": "전문 앱 기능은 외부 앱 브릿지 계약 완료 후 실행 가능",
        "required_execution_location": None,
        "impl": "external_work_registry.py (REGISTRY_ONLY, 강제 차단 미구현)",
    },
    {
        "policy_id": "pol-no-auto-submit",
        "name": "자동 제출 금지",
        "category": "execution",
        "severity": "block",
        "applies_to": ("action_type:submit", "action_type:bid", "action_type:sign"),
        "decision": SafetyDecision.BLOCK,
        "reason": "투찰/전자서명/결제는 자동 실행 금지",
        "required_execution_location": "USER_DIRECT_REQUIRED",
        "impl": "ai_orchestrator/local_agent/actions/browser_submit_with_user_approval.py",
    },
]


def list_safety_policies() -> list[SafetyPolicy]:
    """현재 구현된 SafetyPolicy 요약 목록을 반환."""
    result = []
    for info in _SAFETY_POLICY_SUMMARY:
        result.append(
            SafetyPolicy(
                policy_id=info["policy_id"],
                name=info["name"],
                category=info["category"],
                severity=info["severity"],
                applies_to=info["applies_to"],
                decision=info["decision"],
                reason=info["reason"],
                required_execution_location=info.get("required_execution_location"),
            )
        )
    return result


__all__ = [
    "adapt_external_work_entry",
    "adapt_static_integration",
    "get_all_bridges",
    "get_bridge",
    "list_external_works_as_models",
    "list_integrations_as_models",
    "list_safety_policies",
]
