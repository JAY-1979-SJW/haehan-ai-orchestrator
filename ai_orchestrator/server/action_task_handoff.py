"""
서버 task API ↔ action_registry/user_approval_gate handoff 통합 layer.

목적:
- 서버 task API 진입 지점에서 action_registry를 조회하고
- requires_approval 정책을 적용하며
- user_approval_gate에 승인 요청을 위임하고
- LOCAL_AGENT_REQUIRED handoff payload를 생성한다.

이 모듈은 실제 제출/투찰/전자서명을 실행하지 않는다.
미구현(implemented=False) 액션은 task 생성 단계에서 verdict로 차단되며,
승인 토큰이 있어도 handler 미연결 상태이므로 실행이 불가능하다.

서버 보안 원칙:
- 외부 사이트 브라우저 실행 금지
- cookie/session/storage_state/password/otp/cert_password/private_key 미포함
- 승인 토큰은 1회용·만료·scope-bound (action_name + params_hash)
- 결과 evidence 정책에서 금지 필드 명시
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ai_orchestrator.agent_hub.action_registry import (
    get_action_spec,
    has_handler,
)
from ai_orchestrator.agent_hub.action_summary_builder import (
    build_action_summary,
)
from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    STATUS_PENDING,
    compute_params_hash,
    create_approval_request,
    sanitize_params,
    verify_and_consume_token,
)

# ── execution location ────────────────────────────────────────────────────────

EXEC_LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
EXEC_SERVER_DIRECT = "SERVER_DIRECT"  # 미사용. 모든 registry 액션은 LOCAL_AGENT_REQUIRED.

# ── verdict 상수 ──────────────────────────────────────────────────────────────

VERDICT_HANDOFF_READY = "HANDOFF_READY"
VERDICT_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
VERDICT_APPROVAL_INVALID = "APPROVAL_INVALID"
VERDICT_NOT_IMPLEMENTED = "ACTION_REGISTERED_NOT_IMPLEMENTED"
VERDICT_UNKNOWN_ACTION = "UNKNOWN_ACTION"
VERDICT_BLOCKED_SENSITIVE = "BLOCKED_SENSITIVE_PARAMS"

# ── approval status 상수 ──────────────────────────────────────────────────────

APPROVAL_NOT_REQUIRED = "NOT_REQUIRED"
APPROVAL_PENDING = STATUS_PENDING  # PENDING_USER_REVIEW
APPROVAL_CONSUMED = "APPROVED_AND_CONSUMED"
APPROVAL_INVALID = "INVALID"

# ── handoff payload 금지 필드 ─────────────────────────────────────────────────

FORBIDDEN_HANDOFF_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "cert_password",
        "certificate_password",
        "cookie",
        "cookies",
        "session",
        "storage_state",
        "private_key",
        "npki",
        "auth_header",
        "Authorization",
        "token",
        "access_token",
        "refresh_token",
        "certificate_file_path",
    }
)

# 결과 evidence에서 절대 허용하지 않는 필드 (task_protocol과 동기)
FORBIDDEN_RESULT_FIELDS: frozenset[str] = frozenset(
    {
        "cookie",
        "cookies",
        "session",
        "token",
        "password",
        "otp",
        "certificate_password",
        "cert_password",
        "auth_token",
        "access_token",
        "refresh_token",
        "npki_data",
        "private_key",
        "localStorage",
        "sessionStorage",
        "storage_state",
    }
)

# 민감 파라미터 키 (사용자 입력에 포함되면 sanitize 대상)
_SENSITIVE_PARAM_KEY_HINTS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "cert_password",
        "certificate_password",
        "cookie",
        "session",
        "token",
        "storage_state",
        "private_key",
        "npki",
        "auth_header",
        "authorization",
    }
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _has_sensitive_keys(params: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for k in params:
        kl = k.lower()
        if any(s in kl for s in _SENSITIVE_PARAM_KEY_HINTS):
            found.append(k)
    return found


def _verdict_envelope(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    action_name: str,
    spec,
    verdict: str,
    *,
    approval_status: str = APPROVAL_NOT_REQUIRED,
    approval_request_id: str | None = None,
    params_hash: str = "",
    summary: dict[str, Any] | None = None,
    handoff_required: bool = False,
    handoff_payload: dict[str, Any] | None = None,
    blocked_reason: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "action_name": action_name,
        "implemented": bool(spec.implemented) if spec else False,
        "risk_level": spec.risk_grade if spec else "",
        "requires_approval": bool(spec.requires_user_approval) if spec else False,
        "execution_location": EXEC_LOCAL_AGENT_REQUIRED,
        "verdict": verdict,
        "approval_status": approval_status,
        "approval_request_id": approval_request_id,
        "params_hash": params_hash,
        "summary": summary or {},
        "handoff_required": handoff_required,
        "handoff_target": EXEC_LOCAL_AGENT_REQUIRED if handoff_required else None,
        "handoff_payload": handoff_payload,
        "blocked_reason": blocked_reason,
        "warnings": list(warnings or []),
    }


def build_handoff_payload(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    action_name: str,
    spec,
    params_safe: dict[str, Any],
    params_hash: str,
    summary_safe: dict[str, Any],
    approval_status: str,
    approval_token_required: bool,
    duration_seconds: int = 300,
) -> dict[str, Any]:
    """
    LOCAL_AGENT_REQUIRED handoff payload — sanitize된 safe field만 포함.
    민감 데이터, cookie/session/storage_state 등은 절대 포함하지 않는다.
    """
    created = datetime.now(UTC)
    expires = created + timedelta(seconds=max(60, min(duration_seconds, 1800)))

    payload = {
        "action_name": action_name,
        "params_safe": dict(params_safe),
        "params_hash": params_hash,
        "execution_location": EXEC_LOCAL_AGENT_REQUIRED,
        "requires_approval": bool(spec.requires_user_approval),
        "approval_status": approval_status,
        "approval_token_required": bool(approval_token_required),
        "summary_safe": dict(summary_safe),
        "evidence_policy": {
            "allowed_result_fields": list(spec.evidence_fields),
            "forbidden_fields": sorted(FORBIDDEN_RESULT_FIELDS),
        },
        "created_at": created.isoformat(),
        "expires_at": expires.isoformat(),
        # 민감 데이터 미포함 플래그 (검증/감사용)
        "sensitive_data_included": False,
        "cookie_included": False,
        "session_included": False,
        "password_included": False,
        "otp_included": False,
        "cert_info_included": False,
        "storage_state_included": False,
    }
    return payload


def validate_handoff_payload(payload: dict[str, Any]) -> list[str]:
    """handoff payload에 금지 필드/플래그 위반이 없는지 검증."""
    violations: list[str] = []

    # 명시 플래그
    flag_checks = (
        "sensitive_data_included",
        "cookie_included",
        "session_included",
        "password_included",
        "otp_included",
        "cert_info_included",
        "storage_state_included",
    )
    for f in flag_checks:
        if payload.get(f) is True:
            violations.append(f"민감 플래그 True: {f!r}")

    # params_safe 안 키 검사
    params_safe = payload.get("params_safe") or {}
    if not isinstance(params_safe, dict):
        violations.append("params_safe 타입 오류")
    else:
        for k in params_safe:
            kl = k.lower()
            if any(s in kl for s in _SENSITIVE_PARAM_KEY_HINTS):
                violations.append(f"params_safe에 민감 키 노출: {k!r}")
            if k in FORBIDDEN_HANDOFF_FIELDS:
                violations.append(f"params_safe에 금지 필드: {k!r}")

    # evidence_policy
    ep = payload.get("evidence_policy") or {}
    forbidden = set(ep.get("forbidden_fields") or [])
    missing = FORBIDDEN_RESULT_FIELDS - forbidden
    if missing:
        violations.append(f"evidence_policy.forbidden_fields 누락: {sorted(missing)}")

    return violations


def prepare_action_task(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    action_name: str,
    params: dict[str, Any] | None = None,
    requested_by: str = "anonymous",
    approval_token: str | None = None,
    duration_seconds: int = 300,
    user_intent_summary: str = "",
    site_context: str = "",
    target_context: str = "",
) -> dict[str, Any]:
    """
    서버 task API의 action_registry/approval_gate/handoff 통합 진입점.

    흐름:
      1. ActionSpec 조회 (없으면 UNKNOWN_ACTION)
      2. 민감 키 차단 (BLOCKED_SENSITIVE_PARAMS)
      3. params sanitize + params_hash 계산
      4. summary 생성
      5. requires_approval=False:
         - implemented=False면 NOT_IMPLEMENTED
         - 그 외 HANDOFF_READY
      6. requires_approval=True:
         - approval_token 미제공 → APPROVAL_REQUIRED + 승인 요청 생성
         - approval_token 제공 → verify_and_consume_token
           실패 → APPROVAL_INVALID
           성공 → implemented=False면 NOT_IMPLEMENTED, 아니면 HANDOFF_READY
    """
    params = dict(params or {})
    spec = get_action_spec(action_name)

    if spec is None:
        return _verdict_envelope(
            action_name,
            None,
            VERDICT_UNKNOWN_ACTION,
            blocked_reason=f"등록되지 않은 action_name: {action_name!r}",
        )

    # 민감 키 입력 차단 (방어선 1)
    sensitive_keys = _has_sensitive_keys(params)
    if sensitive_keys:
        return _verdict_envelope(
            action_name,
            spec,
            VERDICT_BLOCKED_SENSITIVE,
            blocked_reason=f"민감 파라미터 입력 차단: {sensitive_keys}",
            warnings=[f"sanitize 대상 키: {sensitive_keys}"],
        )

    params_safe = sanitize_params(params)
    params_hash = compute_params_hash(params)
    summary_full = build_action_summary(action_name, params)
    summary_safe = summary_full.get("summary", {})

    warnings: list[str] = []
    if not has_handler(action_name) and spec.implemented:
        warnings.append("implemented=True지만 handler 미등록: 실행 시점에 차단 가능성")

    # 승인 불필요 경로
    if not spec.requires_user_approval:
        if not spec.implemented:
            return _verdict_envelope(
                action_name,
                spec,
                VERDICT_NOT_IMPLEMENTED,
                approval_status=APPROVAL_NOT_REQUIRED,
                params_hash=params_hash,
                summary=summary_safe,
                handoff_required=False,
                blocked_reason="ActionSpec.implemented=False — 실행 핸들러 미연결",
                warnings=warnings + ["향후 구현 예정 액션"],  # noqa: RUF005
            )
        handoff = build_handoff_payload(
            action_name=action_name,
            spec=spec,
            params_safe=params_safe,
            params_hash=params_hash,
            summary_safe=summary_safe,
            approval_status=APPROVAL_NOT_REQUIRED,
            approval_token_required=False,
            duration_seconds=duration_seconds,
        )
        return _verdict_envelope(
            action_name,
            spec,
            VERDICT_HANDOFF_READY,
            approval_status=APPROVAL_NOT_REQUIRED,
            params_hash=params_hash,
            summary=summary_safe,
            handoff_required=True,
            handoff_payload=handoff,
            warnings=warnings,
        )

    # 승인 필요 경로
    if approval_token is None:
        req = create_approval_request(
            action_name=action_name,
            params=params,
            summary={
                "user_intent_summary": user_intent_summary,
                "site_context": site_context,
                "target_context": target_context,
                **summary_safe,
            },
            user_id=requested_by,
            duration_seconds=duration_seconds,
        )
        return _verdict_envelope(
            action_name,
            spec,
            VERDICT_APPROVAL_REQUIRED,
            approval_status=APPROVAL_PENDING,
            approval_request_id=req["request_id"],
            params_hash=params_hash,
            summary=summary_safe,
            handoff_required=False,
            warnings=warnings
            + (["향후 구현 예정 액션 — 승인되어도 핸들러 미연결로 실행 불가"] if not spec.implemented else []),
        )

    # 승인 토큰 제공됨 → verify_and_consume
    verify = verify_and_consume_token(
        token=approval_token,
        action_name=action_name,
        params=params,
    )
    if not verify.get("ok"):
        return _verdict_envelope(
            action_name,
            spec,
            VERDICT_APPROVAL_INVALID,
            approval_status=APPROVAL_INVALID,
            params_hash=params_hash,
            summary=summary_safe,
            handoff_required=False,
            blocked_reason=str(verify.get("reason") or "승인 검증 실패"),
            warnings=warnings,
        )

    # 토큰 유효 → 미구현이면 차단
    if not spec.implemented:
        return _verdict_envelope(
            action_name,
            spec,
            VERDICT_NOT_IMPLEMENTED,
            approval_status=APPROVAL_CONSUMED,
            approval_request_id=verify.get("request_id"),
            params_hash=params_hash,
            summary=summary_safe,
            handoff_required=False,
            blocked_reason="ActionSpec.implemented=False — 승인은 소비됐으나 핸들러 미연결로 실행 차단",
            warnings=warnings + ["향후 구현 예정 액션"],  # noqa: RUF005
        )

    handoff = build_handoff_payload(
        action_name=action_name,
        spec=spec,
        params_safe=params_safe,
        params_hash=params_hash,
        summary_safe=summary_safe,
        approval_status=APPROVAL_CONSUMED,
        approval_token_required=True,
        duration_seconds=duration_seconds,
    )
    return _verdict_envelope(
        action_name,
        spec,
        VERDICT_HANDOFF_READY,
        approval_status=APPROVAL_CONSUMED,
        approval_request_id=verify.get("request_id"),
        params_hash=params_hash,
        summary=summary_safe,
        handoff_required=True,
        handoff_payload=handoff,
        warnings=warnings,
    )
