"""L8 Server API — 회원가입 / 로그인 / 마이페이지 라우터."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator

from .. import config, user_db
from ..auth import require_role  # 관리자(Basic Auth) — 승인 등 owner 작업

user_auth_router = APIRouter(prefix="/users", tags=["users"])

_bearer = HTTPBearer(auto_error=False)


# ── JWT helpers ───────────────────────────────────────────────────────────────


def _make_token(user_id: str) -> str:
    exp = datetime.now(UTC) + timedelta(days=config.JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": exp},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM,
    )


def _decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_jwt_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not cred:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다")
    user_id = _decode_token(cred.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="토큰이 유효하지 않습니다")
    user = user_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다")
    return user


# 관리자 승인 작업은 ..auth.require_role(Basic Auth)로 게이트한다.
# (일반 사용자 인증은 JWT get_jwt_user, 관리자 작업은 Basic Auth — 기존 admin/licenses와 동일 모델)


# ── 요청/응답 모델 ─────────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    email: str
    name: str
    password: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("이름을 입력하세요")
        if len(v) > 50:
            raise ValueError("이름은 최대 50자입니다")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 최소 8자입니다")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_pw_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 최소 8자입니다")
        return v


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    plan: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class SignupResponse(BaseModel):
    status: str  # "pending_approval"
    message: str
    user: UserResponse


class PendingUserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: str


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────


@user_auth_router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(body: SignupRequest):
    """가입 접수 → enabled=0(승인 대기). 토큰 미발급 — 관리자 승인 후 로그인."""
    if user_db.email_exists(body.email):
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다")
    user = user_db.create_user(body.email, body.name, body.password)
    return SignupResponse(
        status="pending_approval",
        message="가입이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.",
        user=UserResponse(**user_db.safe_user(user)),
    )


@user_auth_router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest):
    # authenticate_user → get_user_by_email 은 enabled=1 만 통과시키므로
    # 승인 대기(enabled=0) 사용자는 자격 일치해도 로그인 불가.
    user = user_db.authenticate_user(body.email, body.password)
    if not user:
        # 비번이 '맞고' 승인 대기(enabled=0)인 경우에만 별도 안내.
        # (비번 오류 시에는 일반 401 — 이메일 존재 여부 노출 방지)
        if user_db.is_pending_login(body.email, body.password):
            raise HTTPException(status_code=403, detail="관리자 승인 대기 중입니다")
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")
    token = _make_token(user["id"])
    return AuthResponse(token=token, user=UserResponse(**user_db.safe_user(user)))


@user_auth_router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_jwt_user)):
    return UserResponse(**user_db.safe_user(user))


@user_auth_router.put("/me/password", status_code=204)
def change_password(body: PasswordChangeRequest, user: dict = Depends(get_jwt_user)):
    if not user_db.authenticate_user(user["email"], body.current_password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다")
    user_db.update_password(user["id"], body.new_password)


# ── 관리자 승인 (owner/admin 전용) ──────────────────────────────────────────────


@user_auth_router.get("/pending", response_model=list[PendingUserResponse])
def list_pending(_admin: dict = Depends(require_role("admin", "owner"))):
    """승인 대기 사용자 목록 (관리자 전용)."""
    return [
        PendingUserResponse(id=u["id"], email=u["email"], name=u["name"], created_at=u["created_at"])
        for u in user_db.list_pending_users()
    ]


@user_auth_router.post("/{user_id}/approve", status_code=200)
def approve(user_id: str, _admin: dict = Depends(require_role("admin", "owner"))):
    """승인 대기 사용자를 활성화(enabled=1) (관리자 전용)."""
    if not user_db.approve_user(user_id):
        raise HTTPException(status_code=404, detail="대상 사용자를 찾을 수 없습니다")
    return {"status": "approved", "user_id": user_id}
