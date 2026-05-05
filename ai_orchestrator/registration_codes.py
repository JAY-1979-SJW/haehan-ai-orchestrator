"""로컬 에이전트 등록코드 (REGCODE-1).

데스크톱 agent 가 admin Basic Auth 없이 1회용 코드로 등록할 수 있게 하는
저장소 + 발급/교환/조회/폐기 헬퍼.

저장소 선택 (backend):
  - memory: process-local in-memory (기본값, migration 전)
  - db: PostgreSQL-backed (migration 적용 후)

환경변수:
  LOCAL_AGENT_REGISTRATION_CODE_STORE=memory|db (기본값: memory)

보안:
  - registration_code 원문은 발급 직후 1회만 호출자에게 반환된다.
  - 서버는 SHA-256(salt + normalized_code) 만 저장한다.
  - 코드 원문/해시/salt 는 list/detail/audit 응답에 노출되지 않는다.
  - 1회 사용 후 status=used 로 잠긴다. 만료/폐기/사용 모두 일관 generic
    "invalid_registration_code" 결과로 처리해 외부에서 상태를 구분하지 못하게 한다.
"""
from __future__ import annotations

from typing import Optional

# Store 구조 import (REGCODE-2)
from .registration_code_store import (
    RegistrationCode,
    IssueResult,
    InvalidTTLError,
    CodeExchangeError,
    DEFAULT_TTL_MINUTES,
    MAX_TTL_MINUTES,
    INVALID_CODE_MESSAGE,
    get_registration_code_store,
    reset_store_for_tests,
    _now,
)

# Public API 래퍼 (기존 호출처 호환성 유지)


def issue_code(
    *,
    label: str,
    expires_in_minutes: int = DEFAULT_TTL_MINUTES,
    allowed_actions: Optional[list[str]] = None,
    note: str = "",
    issued_by: str,
    issuer_role: str = "",
) -> IssueResult:
    """새 등록코드 발급."""
    store = get_registration_code_store()
    return store.issue(
        label=label,
        expires_in_minutes=expires_in_minutes,
        allowed_actions=allowed_actions,
        note=note,
        issued_by=issued_by,
        issuer_role=issuer_role,
    )


def consume_code(raw_code: str) -> RegistrationCode:
    """raw 입력을 정규화·검증 후 사용 처리."""
    store = get_registration_code_store()
    return store.consume(raw_code)


def get_code(code_id: str) -> Optional[RegistrationCode]:
    """code_id로 code 조회."""
    store = get_registration_code_store()
    return store.get(code_id)


def list_codes() -> list[dict]:
    """모든 code (safe response) 조회."""
    store = get_registration_code_store()
    return store.list()


def revoke_code(code_id: str, *, actor: str) -> Optional[RegistrationCode]:
    """code 폐기."""
    store = get_registration_code_store()
    return store.revoke(code_id, actor=actor)


def attach_used_agent(code_id: str, agent_id: str) -> None:
    """사용된 code에 agent_id 연결."""
    store = get_registration_code_store()
    store.attach_used_agent(code_id, agent_id)


def clear() -> None:
    """테스트 전용: 저장소 초기화."""
    store = get_registration_code_store()
    store.clear_for_tests()


# Public exports (기존 호환성)
__all__ = [
    "RegistrationCode",
    "IssueResult",
    "InvalidTTLError",
    "CodeExchangeError",
    "DEFAULT_TTL_MINUTES",
    "MAX_TTL_MINUTES",
    "INVALID_CODE_MESSAGE",
    "issue_code",
    "consume_code",
    "get_code",
    "list_codes",
    "revoke_code",
    "attach_used_agent",
    "clear",
    "_now",
]
