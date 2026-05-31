"""L8 Server API — 회원가입 / 로그인 / 마이페이지 라우터."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator

from .. import config
from .. import user_db

user_auth_router = APIRouter(prefix="/users", tags=["users"])

_bearer = HTTPBearer(auto_error=False)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _make_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=config.JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": exp},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM,
    )


def _decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_jwt_user(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
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


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@user_auth_router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(body: SignupRequest):
    if user_db.email_exists(body.email):
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다")
    user = user_db.create_user(body.email, body.name, body.password)
    token = _make_token(user["id"])
    return AuthResponse(token=token, user=UserResponse(**user_db.safe_user(user)))


@user_auth_router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest):
    user = user_db.authenticate_user(body.email, body.password)
    if not user:
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
