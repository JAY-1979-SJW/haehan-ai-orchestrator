"""local_agent 조회 라우트군 (list / diagnostics) — read-only leaf 서브라우터.

local_agent_router.py(컴포지션 루트)가 include_router 로 관리한다.
sibling leaf 를 직접 import 하지 않는다. [docs/module_separation_standard.md]
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .auth import require_role
from . import local_agent_registry as _reg
from . import local_agent_diagnostics

query_router = APIRouter()


@query_router.get("/diagnostics")
def get_local_agents_diagnostics(
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    """Local agent 운영 진단 정보 (read-only).

    agent/task 상태 집계, 민감정보 제외 (token_id, raw params, raw audit, raw html/url/secret 등).
    allowlist field만 반환 (counts, status, timestamps).
    """
    with _reg._lock:
        diagnostics = local_agent_diagnostics.build_local_agent_diagnostics()
    return diagnostics
