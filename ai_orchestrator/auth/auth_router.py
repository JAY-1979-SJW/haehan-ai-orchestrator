"""auth/me endpoint.

현재 인증된 사용자의 actor와 role만 반환한다.
비밀번호·hash·token·session·cookie는 절대 반환하지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import get_current_user

auth_router = APIRouter(prefix="/auth", tags=["auth"])


class CurrentUserResponse(BaseModel):
    actor: str
    role: str


@auth_router.get("/me", response_model=CurrentUserResponse)
def get_me(user: dict = Depends(get_current_user)) -> CurrentUserResponse:
    """현재 인증된 사용자의 actor와 role을 반환한다.

    - AUTH_ENABLED=False 환경: {actor: "system", role: "owner"}
    - AUTH_ENABLED=True 환경: Basic 인증 성공 시 해당 사용자의 actor/role
    - 인증 실패 시 401
    반환 필드는 actor, role만이며 password·hash·token 등은 포함하지 않는다.
    """
    return CurrentUserResponse(actor=user["actor"], role=user["role"])
