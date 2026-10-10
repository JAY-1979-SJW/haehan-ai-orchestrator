"""시험 공용 도우미 — 실행 중인 FastAPI app 의 실제 라우트 목록.

FastAPI 0.137+ 는 include_router() 를 즉시 펼치지 않고 지연 래퍼(_IncludedRouter)로 저장하므로
`app.routes` 를 바로 순회하면 서브라우터의 실제 라우트가 보이지 않는다(2026-09-29 defect_index #39·#40).
공식 `iter_route_contexts` 로 펼친 목록을 쓰는 `tools.audits.backend.audit_backend_runtime_contract.iter_runtime_routes`
를 재사용한다(새로 구현하지 않음).
"""

from __future__ import annotations

from typing import NamedTuple

from tools.audits.backend.audit_backend_runtime_contract import (
    EXPECTED_HTTP_ROUTES,
    EXPECTED_POST_ROUTES,
    EXPECTED_RUNTIME_ROUTES,
    EXPECTED_WEBSOCKET_ROUTES,
    iter_runtime_routes,
)

# 라우트 개수 기대값은 configs/route_count_expectation.json 한 곳이 정본이다(위 상수는 그것을 읽은 값). 시험에 숫자를 직접 적지 않는다.
__all__ = [
    "EXPECTED_HTTP_ROUTES",
    "EXPECTED_POST_ROUTES",
    "EXPECTED_RUNTIME_ROUTES",
    "EXPECTED_WEBSOCKET_ROUTES",
    "RuntimeRoute",
    "http_routes",
    "route_paths",
    "runtime_routes",
    "websocket_routes",
]


class RuntimeRoute(NamedTuple):
    method: str  # "GET" / "GET,POST" / "WEBSOCKET"
    path: str
    name: str


def runtime_routes() -> list[RuntimeRoute]:
    return [RuntimeRoute(*r) for r in iter_runtime_routes()]


def http_routes() -> list[RuntimeRoute]:
    return [r for r in runtime_routes() if r.method != "WEBSOCKET"]


def websocket_routes() -> list[RuntimeRoute]:
    return [r for r in runtime_routes() if r.method == "WEBSOCKET"]


def route_paths() -> set[str]:
    return {r.path for r in runtime_routes()}
