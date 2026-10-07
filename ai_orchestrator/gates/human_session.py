"""사람 세션 증명 — 승인 발급(approve·reject·revoke) API 를 사람이 누른 화면 요청으로 한정한다 (R2d-2 P0c, 설계서 §13).

관리 화면의 서버 프록시(admin-web)가 `X-Approval-Proxy: <ts>.<nonce>.<hex>` 를 붙인다. hex 는 서버 비밀
`APPROVAL_PROXY_SECRET` 으로 만든 HMAC-SHA256 이고, 대상은 메서드·경로·시각·nonce·본문 해시·Bearer 해시다.
백엔드는 같은 비밀로 검증한다. 비밀이 없으면 발급은 503(fail-closed), 증명이 없거나 틀리면 403 — 응답에 비밀·기대값을 싣지 않는다.

- 인증 방식은 `Authorization` 스킴으로 도출한다(auth.py 와 `/auth/me` 계약은 건드리지 않는다).
- 허용: Bearer JWT + 역할 admin·owner, 또는 인증 꺼짐(단독 모드). Basic·MCP·viewer·operator 는 403.
- 이 모듈은 증명 검증만 한다. 승인 기록의 상태 전이는 human_approval 이 맡는다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time

from fastapi import Depends, HTTPException, Request

from .. import config
from .auth import get_current_user

SECRET_ENV = "APPROVAL_PROXY_SECRET"  # noqa: S105 - 환경변수 이름이지 비밀 값이 아니다
HEADER = "X-Approval-Proxy"
ISSUE_ROLES = frozenset({"admin", "owner"})
MAX_SKEW_S = 60
NONCE_MEMORY_S = 120  # 시각 허용 폭(±60초)의 두 배 — 이 안의 재전송은 nonce 로 막는다
_PREFIX = "HAEHAN-APPROVAL-V1"
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
LOCAL_ACTOR = "local-owner"  # 인증 꺼짐(단독 모드)에서의 승인자 이름

_seen: dict[str, float] = {}
_lock = threading.Lock()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(method: str, path: str, ts: str, nonce: str, body: bytes, bearer: str) -> str:
    """서명 대상 문자열. 프록시(approvalProxy.ts)와 글자 하나까지 같아야 한다(교차 언어 시험으로 고정)."""
    return "\n".join([_PREFIX, method.upper(), path, ts, nonce, _sha256(body), _sha256(bearer.encode("utf-8"))])


def sign(secret: str, method: str, path: str, ts: str, nonce: str, body: bytes, bearer: str) -> str:  # noqa: PLR0913 - 서명 입력 전부
    msg = canonical(method, path, ts, nonce, body, bearer).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _secret() -> str:
    return os.environ.get(SECRET_ENV, "").strip()


def _remember_nonce(nonce: str, now: float) -> bool:
    """처음 보는 nonce 면 기억하고 True, 이미 쓴 것이면 False. 기억 창이 지난 항목은 비운다."""
    with _lock:
        for key in [k for k, exp in _seen.items() if exp <= now]:
            del _seen[key]
        if nonce in _seen:
            return False
        _seen[nonce] = now + NONCE_MEMORY_S
        return True


def verify_proof(  # noqa: PLR0913 - 서명 입력 전부(메서드·경로·본문·Bearer·헤더·시각)가 서로 독립이라 줄이면 오히려 숨겨진다
    header: str | None,
    *,
    method: str,
    path: str,
    body: bytes,
    bearer: str,
    secret: str,
    now: float | None = None,
) -> bool:
    """증명 헤더가 유효하면 True. 형식 오류·서명 불일치·시각 초과·nonce 재사용은 모두 False(이유는 구분해 알리지 않는다)."""
    if not header:
        return False
    parts = header.strip().split(".")
    if len(parts) != 3:
        return False
    ts, nonce, given = parts
    if not ts.isdigit() or not _NONCE_RE.match(nonce):
        return False
    current = time.time() if now is None else now
    if abs(current - int(ts)) > MAX_SKEW_S:
        return False
    expected = sign(secret, method, path, ts, nonce, body, bearer)
    if not hmac.compare_digest(expected, given.lower()):
        return False
    return _remember_nonce(nonce, current)  # 서명이 맞은 요청만 nonce 를 소모한다(남이 nonce 를 미리 태우지 못하게)


def auth_scheme(request: Request) -> str:
    """요청의 인증 방식: 'disabled'(인증 꺼짐) · 'jwt' · 'basic' · 'none'."""
    if not config.AUTH_ENABLED:
        return "disabled"
    head = request.headers.get("authorization", "")
    scheme = head.split(" ", 1)[0].lower() if head else ""
    return {"bearer": "jwt", "basic": "basic"}.get(scheme, "none")


async def require_human_session(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """발급 API 용 의존성. 통과하면 {actor, role, approved_via} 를 돌려준다."""
    secret = _secret()
    if not secret:
        raise HTTPException(status_code=503, detail="승인 발급이 구성되지 않았습니다")
    scheme = auth_scheme(request)
    if scheme == "disabled":
        actor, role = LOCAL_ACTOR, "owner"
    elif scheme == "jwt" and user.get("role") in ISSUE_ROLES:
        actor, role = str(user.get("actor", "")), str(user.get("role"))
    else:
        raise HTTPException(status_code=403, detail="사람이 로그인한 관리 화면에서만 승인할 수 있습니다")
    head = request.headers.get("authorization", "")
    bearer = head.split(" ", 1)[1].strip() if scheme == "jwt" and " " in head else ""
    body = await request.body()
    if not verify_proof(
        request.headers.get(HEADER),
        method=request.method,
        path=request.url.path,
        body=body,
        bearer=bearer,
        secret=secret,
    ):
        raise HTTPException(status_code=403, detail="관리 화면을 거친 요청이 아닙니다")
    return {"actor": actor, "role": role, "approved_via": "jwt"}
