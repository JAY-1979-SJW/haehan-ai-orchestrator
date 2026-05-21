# -*- coding: utf-8 -*-
"""CAD bridge proxy — desktop hub passthrough to local_bridge:8766.

CAD-DESKTOP-HUB-CAD-BRIDGE-PROXY-01.

정책:
- READ_ONLY + CANDIDATE_PAYLOAD path 만 허용.
- GET / POST 메서드만 허용. PUT/DELETE/PATCH 등 차단.
- mutating keyword (execute/apply/mutate/write/save/delete/remove/
  update/approve/reject/command/run 등) 포함 path 무조건 차단.
- /cad/bridge/proxy/ prefix 제거 후 upstream 전달.
- upstream base url: http://127.0.0.1:8766 (cad_bridge_registry 기본값).
- Host/Authorization 등 변조 가능 header 차단 — Content-Type/Accept 만 forward.
- response body / status / content-type 그대로 전달. _source / fallback
  marker / 성공 마커 일체 주입 0건.
- AutoCAD COM / DB write / subprocess / executor wiring 0건.
"""
from __future__ import annotations

import json
import logging
from typing import Mapping, Optional, Tuple

import httpx
from fastapi import Response

from .cad_bridge_registry import DEFAULT_CAD_BRIDGE_HOST, DEFAULT_CAD_BRIDGE_PORT

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Method + keyword 정책
# ──────────────────────────────────────────────

ALLOWED_METHODS = frozenset({"GET", "POST"})

# 경로에 등장 시 무조건 차단되는 mutating-style 키워드 (case-insensitive).
# 본 트랙은 read-only + candidate payload 만 통과.
MUTATING_KEYWORDS: Tuple[str, ...] = (
    "execute", "apply", "mutate", "write", "save",
    "delete", "remove", "update", "approve", "reject",
    "command/run", "command/execute", "cad-control/execute",
    "commit", "drop", "create-job", "run-job", "perform",
)

DEFAULT_PROXY_TIMEOUT_SECONDS = 5.0


# ──────────────────────────────────────────────
# Allow-list — command_contract registry 우선, static fallback
# ──────────────────────────────────────────────

# Static fallback (registry import 실패 시 사용)
_STATIC_POST_ALLOW: frozenset = frozenset({
    "acad/arch-quantity-tab/build-cards",
    "acad/inventory/analyze-drawing-inventory",
    "acad/schedule-tables/detect",
    "acad/construction-sequence/plan",
})

# Read-only / introspection endpoint 만 GET 허용
GET_ALLOW: frozenset = frozenset({
    "acad/health",
    "acad/openapi.json",
})


def _derive_post_allow_from_registry() -> frozenset:
    """command_contract.DEFAULT_REGISTRY 의 CANDIDATE_PAYLOAD endpointPath 수집.

    import 실패 또는 endpointPath 부재 시 _STATIC_POST_ALLOW 로 fallback.
    """
    try:
        from local_agent.cad.command_contract import (  # noqa: WPS433
            DEFAULT_REGISTRY,
            RiskLevel,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("registry import failed, using static allow: %s", exc)
        return _STATIC_POST_ALLOW
    paths: set = set()
    try:
        for tool_id in DEFAULT_REGISTRY.list_by_risk(RiskLevel.CANDIDATE_PAYLOAD):
            entry = DEFAULT_REGISTRY.get(tool_id)
            if entry.endpointPath:
                paths.add(entry.endpointPath.lstrip("/"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("registry walk failed, using static allow: %s", exc)
        return _STATIC_POST_ALLOW
    if not paths:
        return _STATIC_POST_ALLOW
    # 정합성: registry 결과는 항상 static 의 superset 이어야 함 — 단순 union 채택
    return frozenset(paths | _STATIC_POST_ALLOW)


POST_ALLOW: frozenset = _derive_post_allow_from_registry()


# ──────────────────────────────────────────────
# Path normalization
# ──────────────────────────────────────────────

def normalize_proxy_path(path: str) -> str:
    """Proxy path 정규화. upstream 상대 경로 반환 (`acad/...` 형태).

    - 절대 URL injection (`://`, leading `//`) → ValueError
    - traversal (`..` segment) → ValueError
    - 백슬래시 → 슬래시 변환
    - 중복 슬래시 / 빈 segment 제거
    - leading/trailing slash 제거
    - "." segment 제거
    - 빈 경로면 빈 문자열 반환
    """
    if not isinstance(path, str):
        raise ValueError("path must be str")
    if "://" in path:
        raise ValueError("absolute URL injection blocked")
    if path.startswith("//") or path.startswith("\\\\"):
        raise ValueError("absolute URL injection blocked")
    parts = []
    for seg in path.replace("\\", "/").split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            raise ValueError("path traversal blocked")
        parts.append(seg)
    return "/".join(parts)


# ──────────────────────────────────────────────
# Allow check
# ──────────────────────────────────────────────

def is_allowed_cad_proxy_request(method: str, path: str) -> Tuple[bool, str]:
    """(allowed, reason) 반환. reason 은 진단/응답용 짧은 문자열.

    실제 호출 0건 — 정책 판정만.
    """
    m = (method or "").upper()
    if m not in ALLOWED_METHODS:
        return False, f"method_not_allowed:{m}"
    try:
        normalized = normalize_proxy_path(path)
    except ValueError as exc:
        return False, str(exc)
    if not normalized.startswith("acad/") and normalized != "acad":
        return False, "path_not_in_acad_namespace"

    lower = normalized.lower()
    for kw in MUTATING_KEYWORDS:
        if kw in lower:
            return False, f"mutating_keyword_blocked:{kw}"

    if m == "GET":
        if normalized in GET_ALLOW:
            return True, "allow:get_read_only"
        return False, "path_not_in_get_allowlist"

    # POST
    if normalized in POST_ALLOW:
        return True, "allow:candidate_payload"
    return False, "path_not_in_post_allowlist"


# ──────────────────────────────────────────────
# Upstream URL
# ──────────────────────────────────────────────

def build_cad_bridge_upstream_url(
    path: str, query: Optional[str] = None,
) -> str:
    """upstream local_bridge URL 구성. host/port 는 cad_bridge_registry 기본값."""
    normalized = normalize_proxy_path(path)
    base = f"http://{DEFAULT_CAD_BRIDGE_HOST}:{DEFAULT_CAD_BRIDGE_PORT}"
    url = f"{base}/{normalized}"
    if query:
        url = f"{url}?{query}"
    return url


# ──────────────────────────────────────────────
# Header forwarding (host/auth/cookie 차단)
# ──────────────────────────────────────────────

_FORWARDABLE_REQUEST_HEADERS: frozenset = frozenset({
    "content-type", "accept",
})

# upstream → client 로 전달 시 strip 할 header (raw bytes 충돌 방지)
_RESPONSE_STRIP_HEADERS: frozenset = frozenset({
    "content-encoding", "transfer-encoding",
    "connection", "keep-alive", "server", "date",
})


def _safe_forwarded_headers(headers: Optional[Mapping[str, str]]) -> dict:
    if not headers:
        return {}
    out = {}
    for k, v in headers.items():
        if k.lower() in _FORWARDABLE_REQUEST_HEADERS:
            out[k] = v
    return out


# ──────────────────────────────────────────────
# Response builders (markers 주입 0)
# ──────────────────────────────────────────────

def _blocked_response(reason: str) -> Response:
    """403 — allow-list 외 / mutating 키워드 / 잘못된 path."""
    payload = json.dumps({
        "ok": False,
        "blocked": True,
        "reason": reason,
        "policy": "cad-bridge-proxy-allowlist",
    }).encode("utf-8")
    return Response(
        content=payload, status_code=403, media_type="application/json",
    )


def _upstream_timeout_response() -> Response:
    payload = json.dumps({
        "ok": False, "error": "upstream_timeout",
    }).encode("utf-8")
    return Response(
        content=payload, status_code=504, media_type="application/json",
    )


def _upstream_unreachable_response(detail: str) -> Response:
    payload = json.dumps({
        "ok": False, "error": "upstream_unreachable", "detail": detail,
    }).encode("utf-8")
    return Response(
        content=payload, status_code=502, media_type="application/json",
    )


# ──────────────────────────────────────────────
# 메인 forward 함수
# ──────────────────────────────────────────────

async def proxy_cad_bridge_request(
    method: str,
    path: str,
    *,
    query: Optional[str] = None,
    body: Optional[bytes] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_PROXY_TIMEOUT_SECONDS,
) -> Response:
    """upstream CAD local_bridge 로 요청 전달. 정책 검증 + passthrough.

    절대 response 에 marker 주입하지 않는다 (live/fallback 구분은 응답
    body 의 _source 부재 여부로 caller 가 판별).
    """
    allowed, reason = is_allowed_cad_proxy_request(method, path)
    if not allowed:
        return _blocked_response(reason)

    try:
        url = build_cad_bridge_upstream_url(path, query)
    except ValueError as exc:
        return _blocked_response(f"invalid_path:{exc}")

    fwd_headers = _safe_forwarded_headers(headers)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method.upper() == "GET":
                resp = await client.get(url, headers=fwd_headers)
            else:  # POST (이미 method 검증 완료)
                resp = await client.post(
                    url, content=body, headers=fwd_headers,
                )
    except httpx.TimeoutException:
        return _upstream_timeout_response()
    except httpx.RequestError as exc:
        return _upstream_unreachable_response(str(exc))
    except Exception as exc:  # noqa: BLE001 — desktop 서버 보호
        logger.warning("cad_bridge_proxy unexpected error: %s", exc)
        return _upstream_unreachable_response(
            f"unexpected:{type(exc).__name__}",
        )

    # passthrough
    out_headers = {}
    for k, v in resp.headers.items():
        if k.lower() in _RESPONSE_STRIP_HEADERS:
            continue
        out_headers[k] = v
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=out_headers,
        media_type=resp.headers.get("content-type"),
    )


__all__ = [
    "ALLOWED_METHODS",
    "MUTATING_KEYWORDS",
    "GET_ALLOW",
    "POST_ALLOW",
    "DEFAULT_PROXY_TIMEOUT_SECONDS",
    "normalize_proxy_path",
    "is_allowed_cad_proxy_request",
    "build_cad_bridge_upstream_url",
    "proxy_cad_bridge_request",
]
