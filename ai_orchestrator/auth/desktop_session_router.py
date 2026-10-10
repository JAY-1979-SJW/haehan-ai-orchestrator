"""L3 Connector — 데스크톱 로컬 모드 전용 등록·자동 세션 (대표님 결정 B안).

흐름: 첫 실행에서 이름·이메일만 한 번 입력 → owner 생성 → 바로 토큰 발급. 이후 Electron 이 시작할 때마다
`POST /auth/desktop-session` 으로 새 토큰을 받아 webview 쿠키에 넣는다(30일 만료를 신경 쓰지 않아도 됨).
비밀번호는 쓰지 않는다 — owner 의 비밀번호 칸에는 무작위 값을 해시로만 넣어 로그인 경로(/users/login)로는 쓸 수 없다.

적용 범위: `desktop_owner_bootstrap_allowed()`(AUTH_ENABLED=false + HAEHAN_DESKTOP=1 + loopback) 가 참일 때만 동작한다.
아니면 세 엔드포인트 모두 404 — 서버 모드의 가입·로그인·승인 API(정식 관리 방식)는 그대로이고, 서버에서 누가 먼저
owner 를 가져가는 일이 없다. POST 는 사용자 지정 헤더(X-Haehan-Desktop: 1)를 요구해 다른 웹사이트가 브라우저로
이 엔드포인트를 몰래 호출하지 못하게 한다(사전 요청 + 로컬 출처만 CORS 허용).
"""

from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, field_validator

from ai_orchestrator.auth import auth_audit, user_db
from ai_orchestrator.auth.user_auth_router import (
    AuthResponse,
    UserResponse,
    _make_token,
)
from ai_orchestrator.contracts.display_name import validate_display_name
from tools.gates.auth import desktop_owner_bootstrap_allowed

desktop_session_router = APIRouter(prefix="/auth", tags=["desktop-session"])

DESKTOP_HEADER = "X-Haehan-Desktop"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_desktop_mode() -> None:
    if not desktop_owner_bootstrap_allowed():
        # 서버 모드에서는 이 엔드포인트가 존재하지 않는 것처럼 보이게 한다.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _require_desktop_header(value: str | None) -> None:
    if (value or "").strip() != "1":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="데스크톱 앱에서만 사용할 수 있습니다")


class DesktopSetupRequest(BaseModel):
    name: str
    email: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        return validate_display_name(v)

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 254 or not _EMAIL_RE.match(v):
            raise ValueError("이메일 형식이 올바르지 않습니다")
        return v


class DesktopSetupStatus(BaseModel):
    needs_setup: bool


@desktop_session_router.get("/desktop-setup-status", response_model=DesktopSetupStatus)
def desktop_setup_status():
    """첫 실행 설정이 필요한가(사용자가 한 명도 없음)."""
    _require_desktop_mode()
    return DesktopSetupStatus(needs_setup=user_db.count_users() == 0)


@desktop_session_router.post("/desktop-setup", response_model=AuthResponse, status_code=201)
def desktop_setup(body: DesktopSetupRequest, x_haehan_desktop: str | None = Header(default=None)):
    """첫 실행: 이름·이메일로 owner 를 만들고 즉시 토큰을 발급한다. 사용자가 이미 있으면 409(아무것도 만들지 않음)."""
    _require_desktop_mode()
    _require_desktop_header(x_haehan_desktop)
    # 비밀번호 칸은 무작위 값 — 아무도 모르므로 /users/login 으로는 이 계정에 들어갈 수 없다(자동 세션 전용 계정).
    user, bootstrapped = user_db.create_user_bootstrapping(
        body.email, body.name, secrets.token_urlsafe(32), allow_bootstrap=True, only_bootstrap=True
    )
    if not bootstrapped or user is None:
        auth_audit.record_auth_event("desktop_setup", "conflict", actor_id=body.email)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 설정되어 있습니다")
    user_db.touch_session(user["id"])
    # actor 는 식별 필드라 이메일 그대로(마스킹하지 않음). 감사 로그의 email 필드는 auth_audit 가 마스킹한다.
    auth_audit.record_auth_event("desktop_setup", "success", actor_id=body.email, email=body.email, user_id=user["id"])
    return AuthResponse(token=_make_token(user["id"]), user=UserResponse(**user_db.safe_user(user)))


@desktop_session_router.post("/desktop-session", response_model=AuthResponse)
def desktop_session(x_haehan_desktop: str | None = Header(default=None)):
    """시작할 때마다 새 토큰 발급. 사용자 DB 에 활성 owner 가 있으면(이행된 기존 DB 포함) 그 계정으로 만든다.

    owner 가 여럿이면 마지막으로 세션을 쓴 계정, 기록이 없으면 가장 먼저 만든 owner. 사용자가 없으면 409(첫 실행 설정 필요)."""
    _require_desktop_mode()
    _require_desktop_header(x_haehan_desktop)
    owner = user_db.select_desktop_owner()
    if owner is None:
        if user_db.count_users() == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="needs_setup")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no_active_owner")
    user_db.touch_session(owner["id"])
    auth_audit.record_auth_event(
        "desktop_session", "success", actor_id=owner["email"], email=owner["email"], user_id=owner["id"]
    )
    return AuthResponse(token=_make_token(owner["id"]), user=UserResponse(**user_db.safe_user(owner)))
