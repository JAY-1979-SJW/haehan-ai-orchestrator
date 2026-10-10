"""local_agent 등록 라우트군 — register / registration-codes / register-with-code.

leaf 서브라우터. 컴포지션 루트(local_agent_router)가 include_router 로 관리한다.
sibling leaf 는 직접 import 하지 않고 공유 계약(schemas)만 사용.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..registry import facade as _reg
from ...audit.audit_logger import log_event
from ...auth import registration_codes as _regcodes
from tools.gates.auth import require_role
from .schemas import (
    AgentRegisterRequest,
    IssueRegistrationCodeRequest,
    RegisterWithCodeRequest,
)

registration_router = APIRouter()


@registration_router.post("/register")
def register_local_agent(
    body: AgentRegisterRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """새 로컬 에이전트 등록. agent_id + device_token 발급.

    device_token 은 응답에 1회만 노출되며 서버는 SHA-256 해시만 저장한다.
    """
    actor = user["actor"]
    role = user["role"]
    result = _reg.register_agent(
        host=body.host,
        os_name=body.os_name,
        version=body.version,
        requested_by=actor,
    )

    # 감사 로그: token 원문 / 해시 모두 기록 금지. token_hash prefix 만 식별자로.
    log_event(
        "LOCAL_AGENT_REGISTERED",
        result.agent.agent_id,
        actor=actor,
        role=role,
        note=f"host={result.agent.host} os={result.agent.os_name} ver={result.agent.version}",
    )

    return {
        "agent_id": result.agent.agent_id,
        "device_token": result.device_token,  # 1회 노출, 클라이언트 책임 보관
        "host": result.agent.host,
        "os_name": result.agent.os_name,
        "version": result.agent.version,
        "registered_at": result.agent.registered_at,
    }


# ── registration-code (REGCODE-1) ───────────────────────────────────────

# allowed_actions 검증: ACTION_RISK 키 중 high-risk 직접 실행계열은 제외.
# (open_url_execute 는 별도 승인 흐름 — 등록코드 scope 에 직접 부여 금지)
_REGCODE_ALLOWED_ACTIONS: frozenset[str] = frozenset(set(_reg.ACTION_RISK.keys()) - {"open_url_execute"})


@registration_router.post("/registration-codes")
def issue_registration_code(
    body: IssueRegistrationCodeRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """admin/owner 가 1회용 등록코드 발급.

    응답에 registration_code 평문은 1회만 노출되며, 이후 어떤 조회 endpoint
    에서도 평문을 반환하지 않는다. 서버는 SHA-256(salt+code) 만 영속화한다.
    """
    actor = user["actor"]
    role = user["role"]

    # allowed_actions 검증 — 미등록 액션은 400.
    invalid = [a for a in (body.allowed_actions or []) if str(a).strip().lower() not in _REGCODE_ALLOWED_ACTIONS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_ALLOWED_ACTIONS",
                "message": f"unsupported actions: {invalid}",
            },
        )

    try:
        result = _regcodes.issue_code(
            label=body.label,
            expires_in_minutes=body.expires_in_minutes,
            allowed_actions=body.allowed_actions,
            note=body.note,
            issued_by=actor,
            issuer_role=role,
            smoke_test=body.smoke_test,
        )
    except _regcodes.InvalidTTLError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_TTL",
                "message": str(e),
            },
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REQUEST",
                "message": str(e),
            },
        ) from e

    # 감사 로그 — code 원문/hash/salt 절대 기록 금지. code_id 만.
    log_event(
        "REGISTRATION_CODE_ISSUED",
        result.code.code_id,
        actor=actor,
        role=role,
        note=f"label={result.code.label} expires_at={result.code.expires_at} "
        f"actions={','.join(result.code.allowed_actions) or '-'}",
    )

    return {
        "code_id": result.code.code_id,
        "registration_code": result.registration_code,  # 1회 노출
        "label": result.code.label,
        "allowed_actions": list(result.code.allowed_actions),
        "expires_at": result.code.expires_at,
        "created_at": result.code.created_at,
        "smoke_test": result.code.smoke_test,
    }


@registration_router.get("/registration-codes")
def list_registration_codes(
    user: dict = Depends(require_role("admin", "owner")),
):
    """등록코드 목록. 평문/hash/salt 노출 금지."""
    return {"codes": _regcodes.list_codes()}


@registration_router.post("/registration-codes/{code_id}/revoke")
def revoke_registration_code(
    code_id: str,
    user: dict = Depends(require_role("admin", "owner")),
):
    actor = user["actor"]
    role = user["role"]
    rec = _regcodes.revoke_code(code_id, actor=actor)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": "registration_code not found",
            },
        )
    log_event(
        "REGISTRATION_CODE_REVOKED",
        code_id,
        actor=actor,
        role=role,
        note=f"label={rec.label}",
    )
    return rec.to_safe()


@registration_router.post("/register-with-code")
def register_with_code(body: RegisterWithCodeRequest):
    """Basic Auth 없이 1회용 등록코드로 agent 등록.

    실패는 모두 400 + generic message — 외부에서 만료/사용/폐기/오타를
    구분할 수 없게 한다. audit 에는 reason 분류만 별도 기록.
    """
    try:
        rec = _regcodes.consume_code(body.registration_code)
    except _regcodes.CodeExchangeError as e:
        # audit 에는 reason 만, code 원문은 절대 기록 금지.
        log_event(
            "REGISTRATION_CODE_EXCHANGE_FAILED",
            "-",
            actor="agent",
            role="-",
            decision=e.reason,
            note="register-with-code rejected",
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REGISTRATION_CODE",
                "message": _regcodes.INVALID_CODE_MESSAGE,
            },
        ) from e

    result = _reg.register_agent(
        host=body.host,
        os_name=body.os_name,
        version=body.version,
        requested_by=f"registration_code:{rec.code_id}",
        smoke_test=rec.smoke_test,
    )
    _regcodes.attach_used_agent(rec.code_id, result.agent.agent_id)

    log_event(
        "REGISTRATION_CODE_USED",
        rec.code_id,
        actor="agent",
        role="-",
        note=f"agent_id={result.agent.agent_id} label={rec.label}",
    )
    log_event(
        "LOCAL_AGENT_REGISTERED",
        result.agent.agent_id,
        actor=f"registration_code:{rec.code_id}",
        role="-",
        note=f"host={result.agent.host} os={result.agent.os_name} ver={result.agent.version}",
    )

    return {
        "agent_id": result.agent.agent_id,
        "device_token": result.device_token,  # 1회 노출
        "host": result.agent.host,
        "os_name": result.agent.os_name,
        "version": result.agent.version,
        "registered_at": result.agent.registered_at,
        "code_id": rec.code_id,
        "label": rec.label,
        "allowed_actions": list(rec.allowed_actions),
        "smoke_test": result.agent.smoke_test,
    }
