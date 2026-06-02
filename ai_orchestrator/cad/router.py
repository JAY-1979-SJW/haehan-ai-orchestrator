"""/api/v1/cad/* 프록시 라우터.

독립 배포된 cad-backend(cad-quantity FastAPI :8000) 를 오케스트레이터
내부로 중계한다. **cad-backend 직접 노출은 금지**, 모든 호출은 이 라우터를
거쳐야 한다.

단계별 게이트(요청 순서):
    1) HTTP Basic 인증 ─ ``require_role(viewer/operator/admin/owner)``
    2) 쓰기 메서드(POST/PUT/PATCH/DELETE)는 추가로
         - role 이 operator 이상
         - X-Task-Id / X-Approval-Token-Id 헤더가 있고
         - ``approval.validate_token`` 이 True
       세 조건을 모두 만족해야 통과. 조건 미충족 → 403.
    3) 감사 로그 ``CAD_PROXY_CALL`` / ``CAD_PROXY_DENIED`` /
       ``CAD_PROXY_UPSTREAM_ERROR``.
    4) httpx 로 ``CAD_BACKEND_URL`` 에 중계하고 응답을 그대로 전달.

헤더 처리:
    - 상류로 **전달하지 않는 헤더**(누출 방지):
      ``host``, ``authorization``, ``cookie``, ``content-length``,
      ``x-task-id``, ``x-approval-token-id``.
    - ``X-Forwarded-For``, ``X-Orchestrator-Actor`` 를 부여해 상류 로그에서
      호출자 식별 가능.
    - 응답 헤더 중 hop-by-hop 은 제거 (``connection``, ``keep-alive``,
      ``transfer-encoding``, ``content-encoding`` 는 httpx 가 이미 해제).

범위 밖(차기 단계):
    - SSE / WebSocket 프록시 (현 cad-backend 에는 WS 경로 있음 — 차단).
    - 대용량 스트리밍 업로드 (현재는 body 버퍼링).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import httpx
from fastapi import APIRouter, Depends, Request, Response

from .. import approval, config
from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

cad_router = APIRouter(prefix="/cad", tags=["cad-proxy"])

# 쓰기 메서드 — 승인 토큰 필수
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# 쓰기 허용 role (기존 승인형 write 액션과 동일 수준)
_WRITE_ROLES = frozenset({"operator", "admin", "owner"})

# 상류로 **전달 금지** 헤더 (소문자로 비교)
_HOP_BY_HOP_REQUEST = frozenset(
    {
        "host",
        "authorization",
        "cookie",
        "content-length",
        "connection",
        "keep-alive",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        # 오케스트레이터 전용 — 상류에 노출 금지
        "x-task-id",
        "x-approval-token-id",
    }
)

# 응답에서 제거할 hop-by-hop 헤더
_HOP_BY_HOP_RESPONSE = frozenset(
    {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "proxy-authenticate",
        "content-encoding",  # httpx 가 이미 디코딩
        "content-length",  # Starlette 이 재계산
    }
)


def _filter_request_headers(
    raw: Iterable[tuple[str, str]],
    *,
    actor: str,
) -> dict:
    out: dict[str, str] = {}
    for k, v in raw:
        if k.lower() in _HOP_BY_HOP_REQUEST:
            continue
        out[k] = v
    # 상류 cad-backend 가 호출자 식별할 수 있게 최소한의 표시만 부여.
    # actor 값은 HTTP Basic 사용자명 그대로(서버에서 이미 검증됨).
    out["X-Forwarded-For"] = "orchestrator"
    out["X-Orchestrator-Actor"] = actor
    return out


def _filter_response_headers(
    raw: Iterable[tuple[str, str]],
) -> list[tuple[str, str]]:
    return [(k, v) for k, v in raw if k.lower() not in _HOP_BY_HOP_RESPONSE]


def _require_approval(
    method: str,
    role: str,
    task_id: str,
    token_id: str,
) -> str | None:
    """쓰기 메서드용 추가 게이트. 통과하면 None, 거절 시 사유 문자열."""
    if method.upper() not in _WRITE_METHODS:
        return None
    if role not in _WRITE_ROLES:
        return "role_insufficient"
    if not task_id or not token_id:
        return "approval_required"
    try:
        ok = approval.validate_token(token_id, task_id)
    except Exception:
        logger.exception("approval.validate_token 예외")
        return "approval_store_error"
    if not ok:
        return "approval_invalid_or_expired"
    return None


def _denial_event(
    *,
    path: str,
    method: str,
    actor: str,
    role: str,
    task_id: str,
    token_id: str,
    reason: str,
) -> None:
    log_event(
        "CAD_PROXY_DENIED",
        task_id=task_id or "-",
        action_type=f"cad_proxy:{method}",
        target=path,
        actor=actor,
        role=role,
        token_id=token_id or "",
        decision=reason,
        note=f"method={method} path={path}",
    )


@cad_router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def cad_proxy(
    path: str,
    request: Request,
    user: dict = Depends(
        require_role("viewer", "operator", "admin", "owner"),
    ),
) -> Response:
    """cad-backend 로 요청을 중계."""
    actor = user["actor"]
    role = user["role"]
    method = request.method.upper()
    # 경로 재구성 — cad-backend 가 이미 /api/v1/... 프리픽스를 쓰므로
    # 본 라우터에 들어온 {path} 를 그대로 상류 루트 뒤에 붙여 전달한다.
    # 예: /api/v1/cad/projects → cad-backend: /projects (X)
    # 클라이언트 관점의 URL 규약 안정성을 위해 cad-backend 의 원래
    # /api/v1/... 구조를 유지해야 한다. 따라서 상류 base 는 호스트만,
    # path 는 /api/v1/{path} 로 조립한다.
    upstream_path = f"/api/v1/{path.lstrip('/')}"
    query = request.url.query
    upstream_url = f"{config.CAD_BACKEND_URL}{upstream_path}"
    if query:
        upstream_url = f"{upstream_url}?{query}"

    # ── 승인 게이트 (쓰기 메서드) ───────────────────────────────────
    task_id = request.headers.get("x-task-id", "").strip()
    token_id = request.headers.get("x-approval-token-id", "").strip()
    reason = _require_approval(method, role, task_id, token_id)
    if reason is not None:
        _denial_event(
            path=upstream_path,
            method=method,
            actor=actor,
            role=role,
            task_id=task_id,
            token_id=token_id,
            reason=reason,
        )
        return Response(
            content=b'{"detail":{"error":"%s"}}' % reason.encode("ascii"),
            status_code=403,
            media_type="application/json",
        )

    # ── 요청 바디/헤더 준비 ─────────────────────────────────────────
    body = await request.body()
    fwd_headers = _filter_request_headers(request.headers.raw, actor=actor)

    # ── 상류 호출 ──────────────────────────────────────────────────
    timeout = httpx.Timeout(config.CAD_PROXY_TIMEOUT_SEC)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as hc:
            upstream = await hc.request(
                method=method,
                url=upstream_url,
                headers=fwd_headers,
                content=body if body else None,
            )
    except httpx.TimeoutException:
        log_event(
            "CAD_PROXY_UPSTREAM_ERROR",
            task_id=task_id or "-",
            action_type=f"cad_proxy:{method}",
            target=upstream_path,
            actor=actor,
            role=role,
            token_id=token_id or "",
            decision="timeout",
            note=f"timeout={config.CAD_PROXY_TIMEOUT_SEC}s",
        )
        return Response(
            content=b'{"detail":{"error":"upstream_timeout"}}',
            status_code=504,
            media_type="application/json",
        )
    except (httpx.ConnectError, httpx.NetworkError) as e:
        log_event(
            "CAD_PROXY_UPSTREAM_ERROR",
            task_id=task_id or "-",
            action_type=f"cad_proxy:{method}",
            target=upstream_path,
            actor=actor,
            role=role,
            token_id=token_id or "",
            decision="unreachable",
            note=f"{type(e).__name__}",
        )
        return Response(
            content=b'{"detail":{"error":"upstream_unreachable"}}',
            status_code=502,
            media_type="application/json",
        )

    # ── 감사 + 응답 ────────────────────────────────────────────────
    log_event(
        "CAD_PROXY_CALL",
        task_id=task_id or "-",
        action_type=f"cad_proxy:{method}",
        target=upstream_path,
        actor=actor,
        role=role,
        token_id=token_id or "",
        decision=str(upstream.status_code),
        note=f"method={method} upstream_status={upstream.status_code}",
    )
    resp_headers = _filter_response_headers(upstream.headers.multi_items())
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(resp_headers),
        media_type=upstream.headers.get("content-type"),
    )


__all__ = ["cad_router"]
