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

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ai_orchestrator import config

logger = logging.getLogger(__name__)

_DUMMY_USER = {
    "actor": "system",
    "role": "owner",
    "organization_ids": ["default-org"],
    "active_organization_id": "default-org",
}

_security = HTTPBasic(auto_error=False)


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
) -> dict:
    """현재 요청자 신원을 {actor, role} 로 반환.

    - AUTH_ENABLED=False  → 무조건 dummy owner
    - AUTH_ENABLED=True   → Basic 자격증명 검증, 실패 시 401
    """
    if not config.AUTH_ENABLED:
        return dict(_DUMMY_USER)

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
