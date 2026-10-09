"""HTTP 인증/역할 토대 (1단계).

지금 단계에서는 구조만 추가하고, 라우터에는 적용하지 않는다.
AUTH_ENABLED=False 일 때는 무조건 dummy owner 를 반환한다.

TENANT-3: Minimal organization scope context support.
- get_current_user 반환값에 organization_ids/active_organization_id optional 추가
- build_tenant_context() helper 추가 (contract 기반)
- Backward compatible: 기존 actor/role 형식 유지
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from ai_orchestrator.core import config

logger = logging.getLogger(__name__)

_DUMMY_USER = {
    "actor": "system",
    "role": "owner",
    "organization_ids": ["default-org"],
    "active_organization_id": "default-org",
}

_security = HTTPBasic(auto_error=False)
_bearer = HTTPBearer(auto_error=False)

# 콘솔 JWT 수용(2026-10-07, 대표님 결정 A안): 로그인한 사용자의 Bearer JWT 도 Basic 과 같은 require_role 체계로 받는다.
# JWT 검증(서명·만료·사용자 조회)은 사용자 로그인 구현이 정본이라 이 게이트가 DB 를 직접 보지 않고,
# 그쪽(connectors/user_auth_router.py)이 시작할 때 검증 함수를 등록한다. 등록이 없으면 Bearer 는 전부 401(fail-closed).
_bearer_resolver: Callable[[str], dict | None] | None = None


def register_bearer_resolver(resolver: Callable[[str], dict | None]) -> None:
    """Bearer 토큰 → 활성 사용자 레코드(없으면 None)를 돌려주는 함수를 등록한다."""
    global _bearer_resolver
    _bearer_resolver = resolver


# JWT 사용자 role(users.role) → require_role 역할 매핑. 표에 있는 역할만 같은 이름의 권한을 얻는다.
# 그 밖의 값(가입 기본값 "user" 포함)은 "user" 로 취급해 어떤 require_role 라우트도 통과하지 못한다(최소 권한).
#   owner→owner · admin→admin · operator→operator · viewer→viewer · 그 외→user(통과 라우트 없음)
_JWT_ROLE_MAP = {"owner": "owner", "admin": "admin", "operator": "operator", "viewer": "viewer"}
_JWT_NO_PRIVILEGE_ROLE = "user"


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def desktop_owner_bootstrap_allowed() -> bool:
    """데스크톱 로컬 모드에서만 '첫 가입자 자동 owner 승인'을 허용한다(대표님 결정 A안, DESKTOP_RUNTIME_AUDIT D3).

    세 조건을 모두 만족해야 한다 — 하나라도 아니면 꺼짐(서버에서 누가 먼저 가입해 owner 를 가져가는 일을 막는다):
      1. AUTH_ENABLED=false (데스크톱은 단독 사용자 로컬 앱이라 인증 게이트를 끈다. 서버는 true)
      2. HAEHAN_DESKTOP=1 (Electron 이 서버를 띄울 때만 넣는 데스크톱 표지)
      3. 서버가 loopback(127.0.0.1/localhost) 에만 바인딩
    """
    import os

    return (
        not config.AUTH_ENABLED
        and os.environ.get("HAEHAN_DESKTOP", "").strip() == "1"
        and str(config.APP_HOST).strip().lower() in _LOOPBACK_HOSTS
    )


def is_owner_email(email: object) -> bool:
    """이메일이 설정(OWNER_EMAILS)에 있는가. 대소문자·앞뒤 공백 무시, 별칭(+tag)은 정확히 같아야 한다."""
    return str(email or "").strip().lower() in config.OWNER_EMAILS


def is_owner_email_account(record: dict) -> bool:
    """OWNER_EMAILS 의 owner 취급 대상인가: 설정된 이메일 + **승인된 활성 계정**(enabled=1)일 때만.

    미승인·비활성 계정, 활성 여부를 알 수 없는 레코드는 대상이 아니다(fail-closed)."""
    return record.get("enabled") in (1, True) and is_owner_email(record.get("email"))


_owner_email_logged: set[str] = set()


def _note_owner_email_grant(record: dict) -> None:
    """OWNER_EMAILS 로 owner 취급된 계정을 프로세스당 한 번 로그에 남긴다(이메일은 마스킹)."""
    key = str(record.get("id") or record.get("email"))
    if key in _owner_email_logged:
        return
    _owner_email_logged.add(key)
    local, _, domain = str(record.get("email") or "").partition("@")
    logger.info("[auth] OWNER_EMAILS 설정에 따라 owner 로 취급: %s***@%s (DB role=%s)", local[:1], domain, record.get("role"))


def _user_from_bearer(token: str) -> dict:
    """Bearer JWT → {actor, role}. 만료·위조·서명 불일치·미등록 사용자·승인 대기·검증기 미등록은 모두 401.

    role 은 DB role 을 표(_JWT_ROLE_MAP)로 매핑하되, OWNER_EMAILS 의 승인된 활성 계정이면 owner 로 올린다(올리기만 하고
    내리지 않으며, DB 는 바꾸지 않는다). 올린 경우 반환에 role_source="OWNER_EMAILS" 를 표시한다."""
    record = _bearer_resolver(token) if _bearer_resolver is not None else None
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 유효하지 않습니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = _JWT_ROLE_MAP.get(str(record.get("role", "")), _JWT_NO_PRIVILEGE_ROLE)
    user = {"actor": str(record.get("email") or record.get("id")), "role": role}
    if role != "owner" and is_owner_email_account(record):
        _note_owner_email_grant(record)
        user["role"] = "owner"
        user["role_source"] = "OWNER_EMAILS"
    return user


def _load_users() -> dict[str, dict]:
    """http_users.json 을 username → record dict 형태로 로드."""
    path = config.HTTP_USERS_PATH
    if not path.exists():
        logger.warning("HTTP 사용자 파일 없음: %s", path)
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("HTTP 사용자 파일 로드 실패: %s", e)
        return {}

    users: dict[str, dict] = {}
    if isinstance(raw, list):
        for rec in raw:
            if not isinstance(rec, dict):
                continue
            uname = rec.get("username")
            if not uname:
                continue
            users[uname] = rec
    return users


def _verify_password(candidate: str, stored_hash: str) -> bool:
    """운영은 salted SHA-256("sha256$<salt_hex>$<hash_hex>") 형식.

    - 새 형식 : sha256(salt_bytes + candidate) 가 저장 hash 와 일치하면 통과.
    - 레거시 형식(접두사 없음): 기존 평문 동치 비교(테스트 호환용). 운영에는 쓰지 말 것.
    """
    if not candidate or not stored_hash:
        return False
    if stored_hash.startswith("sha256$"):
        parts = stored_hash.split("$", 2)
        if len(parts) != 3:
            return False
        _, salt_hex, hash_hex = parts
        try:
            salt = bytes.fromhex(salt_hex)
        except ValueError:
            return False
        computed = hashlib.sha256(salt + candidate.encode("utf-8")).hexdigest()
        return secrets.compare_digest(computed, hash_hex)
    return secrets.compare_digest(candidate, stored_hash)


def get_current_user(
    credentials: HTTPBasicCredentials | None = Depends(_security),
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """현재 요청자 신원을 {actor, role} 로 반환.

    - AUTH_ENABLED=False  → 무조건 dummy owner
    - AUTH_ENABLED=True   → Bearer JWT(로그인 사용자, role 은 _JWT_ROLE_MAP 으로 매핑) 또는 Basic 자격증명 검증, 실패 시 401
      Authorization 헤더는 하나라 Bearer 와 Basic 은 동시에 오지 않는다. Bearer 가 실패하면 Basic 으로 되돌리지 않고 401.
    """
    if not config.AUTH_ENABLED:
        return dict(_DUMMY_USER)

    # 함수를 직접 호출하는 시험·코드에서는 Depends 객체가 기본값으로 남으므로 실제 자격증명만 인정한다.
    if isinstance(bearer, HTTPAuthorizationCredentials):
        return _user_from_bearer(bearer.credentials)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 필요",
            headers={"WWW-Authenticate": "Basic"},
        )

    users = _load_users()
    rec = users.get(credentials.username)
    if not rec or not rec.get("enabled", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 자격증명",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not _verify_password(credentials.password, rec.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 자격증명",
            headers={"WWW-Authenticate": "Basic"},
        )

    return {"actor": credentials.username, "role": rec.get("role", "viewer")}


def require_role(*roles: str):
    """FastAPI 의존성 팩토리. 지정한 role 중 하나가 아니면 403."""
    allowed = set(roles)

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="권한 부족",
            )
        return user

    return _dep


# ============================================================================
# TENANT-3: Minimal Organization Scope Context
# ============================================================================


def build_tenant_context(user: dict) -> dict:
    """Build tenant context from auth user dict.

    TENANT-3: Minimal organization scope context.
    Backward compatible: returns original user dict + org fields.

    Migration bridge:
    - If organization_ids missing, use ["default-org"] temporary fallback
    - If active_organization_id missing, use first organization_id
    - This fallback is temporary until full tenant DB schema

    Args:
        user: dict from get_current_user() with keys: actor, role

    Returns:
        dict with tenant context fields added:
        - actor_user_id: same as actor (temp mapping)
        - organization_ids: ["default-org"] or from user record
        - active_organization_id: first org or from user record
    """
    if not user:
        user = dict(_DUMMY_USER)

    # Ensure tenant fields exist (temporary migration bridge)
    if "organization_ids" not in user:
        user["organization_ids"] = ["default-org"]
    if "active_organization_id" not in user:
        user["active_organization_id"] = user.get("organization_ids", ["default-org"])[0]

    # Map actor → actor_user_id for contract compatibility
    if "actor_user_id" not in user:
        user["actor_user_id"] = user.get("actor", "unknown")

    return user


def require_active_organization(user: dict) -> str:
    """Require active organization in context.

    Args:
        user: auth context dict

    Returns:
        active_organization_id

    Raises:
        ValueError: if active_organization_id missing or invalid
    """
    user = build_tenant_context(user)

    active_org = user.get("active_organization_id")
    if not active_org:
        raise ValueError("active_organization_id required in auth context")

    org_ids = user.get("organization_ids", [])
    if active_org not in org_ids:
        raise ValueError(f"active_organization_id {active_org} not in organization_ids {org_ids}")

    return active_org


def require_membership(user: dict, organization_id: str) -> None:
    """Require user membership in organization.

    Args:
        user: auth context dict
        organization_id: target organization

    Raises:
        HTTPException: 403 if user not member of organization
    """
    user = build_tenant_context(user)

    org_ids = user.get("organization_ids", [])
    if organization_id not in org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No access to organization {organization_id}",
        )
