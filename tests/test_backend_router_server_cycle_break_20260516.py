"""ASSISTANT_BACKEND_ROUTER_SERVER_CYCLE_BREAK_01 — 순환 import 제거 회귀 테스트.

기존 cycle:
  router.py → action_router.py → server/action_task_api.py
  → server/__init__.py (server.py 즉시 실행)
  → server.py → from .router import router (초기화 중) → ImportError

해소:
  server/__init__.py에 __getattr__ lazy load 도입.
  패키지 import 시 server.py를 즉시 실행하지 않으므로 cycle 차단.
  from ai_orchestrator.server import app 패턴은 그대로 동작.

DB/서버/외부 URL/브라우저 실행 없음.
"""
from __future__ import annotations

import importlib
import sys
import pytest


# ---------------------------------------------------------------------------
# 1. router.py 직접 import — 순환 없음 고정
# ---------------------------------------------------------------------------

def test_router_direct_import_no_cycle():
    """ai_orchestrator.router를 직접 import해도 ImportError가 발생하지 않는다."""
    # sys.modules 제거 후 재import — 후속 테스트 오염 방지: purge 전 snapshot 저장 후 복원
    _snapshot = {k: v for k, v in sys.modules.items() if k.startswith("ai_orchestrator")}
    for m in list(_snapshot):
        sys.modules.pop(m, None)

    try:
        import ai_orchestrator.router as r
        assert r.router is not None
        assert hasattr(r, "router")
    finally:
        for k in [k for k in sys.modules if k.startswith("ai_orchestrator") and k not in _snapshot]:
            sys.modules.pop(k, None)
        sys.modules.update(_snapshot)


def test_router_module_defines_router_object():
    import ai_orchestrator.router as r
    from fastapi import APIRouter
    assert isinstance(r.router, APIRouter)


# ---------------------------------------------------------------------------
# 2. server/__init__.py → server.py 즉시 실행 금지 확인
# ---------------------------------------------------------------------------

def test_server_package_import_does_not_immediately_load_app():
    """server 패키지만 import할 때 app이 즉시 생성되지 않는다 (lazy)."""
    # sys.modules 제거 후 재import — 후속 테스트 오염 방지: purge 전 snapshot 저장 후 복원
    _snapshot = {k: v for k, v in sys.modules.items() if k.startswith("ai_orchestrator")}
    for k in list(_snapshot):
        sys.modules.pop(k, None)

    try:
        import ai_orchestrator.server as srv_pkg
        assert "app" not in vars(srv_pkg), (
            "server/__init__.py가 즉시 app을 생성하고 있음 — lazy load 위반"
        )
    finally:
        for k in [k for k in sys.modules if k.startswith("ai_orchestrator") and k not in _snapshot]:
            sys.modules.pop(k, None)
        sys.modules.update(_snapshot)


def test_server_app_accessible_via_getattr():
    """from ai_orchestrator.server import app 패턴이 정상 동작한다."""
    from ai_orchestrator.server import app
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)


def test_server_app_cached_on_second_access():
    """app 두 번째 접근 시 동일 객체가 반환된다 (캐시)."""
    from ai_orchestrator.server import app as a1
    from ai_orchestrator.server import app as a2
    assert a1 is a2


# ---------------------------------------------------------------------------
# 3. server.py → router.py 방향만 허용 (역방향 금지) 확인
# ---------------------------------------------------------------------------

def test_router_py_does_not_import_server_py_directly():
    """router.py 소스에 'from .server import' 또는 'import server' 가 없다."""
    import pathlib
    router_src = pathlib.Path("ai_orchestrator/router.py").read_text(encoding="utf-8")
    # server.py에서 정의된 app 객체를 router.py가 직접 import하지 않아야 한다
    assert "from .server import app" not in router_src
    assert "from ai_orchestrator.server import app" not in router_src
    # server/__init__ import 없음
    assert "from .server import" not in router_src or "server.action_" not in router_src


def test_action_router_does_not_import_app():
    """action_router.py가 app 객체를 직접 import하지 않는다."""
    import pathlib
    src = pathlib.Path("ai_orchestrator/action_router.py").read_text(encoding="utf-8")
    assert "import app" not in src
    assert "from ai_orchestrator.server import app" not in src


# ---------------------------------------------------------------------------
# 4. action_task_api cycle-free import
# ---------------------------------------------------------------------------

def test_action_task_api_imports_clean():
    """server/action_task_api.py가 cycle 없이 import된다."""
    import ai_orchestrator.server.action_task_api as m
    assert hasattr(m, "api_prepare_action")
    assert hasattr(m, "api_receive_evidence")
    assert callable(m.api_prepare_action)


# ---------------------------------------------------------------------------
# 5. canonical endpoint 53개 유지 확인 (TestClient 경유)
# ---------------------------------------------------------------------------

def test_canonical_endpoint_count_registered():
    """FastAPI app에 등록된 route 수가 정확히 50개이다.

    모듈 파일 기준 canonical 53개 중 naver_search_router(3개)는
    router.py include_router에 미등록 상태이므로 런타임 등록수는 50개.
    """
    from ai_orchestrator.server import app
    from fastapi.routing import APIRoute, APIWebSocketRoute
    routes = [
        r for r in app.routes
        if isinstance(r, (APIRoute, APIWebSocketRoute))
    ]
    assert len(routes) == 50, (
        f"등록된 route 수={len(routes)}, 기준=50"
    )


# ---------------------------------------------------------------------------
# 6. health endpoint 응답 구조 불변 확인
# ---------------------------------------------------------------------------

def test_health_endpoint_response_unchanged():
    from fastapi.testclient import TestClient
    from ai_orchestrator.server import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "service" in data
    assert "success" not in data  # ApiResponse 봉투 미적용 확인


# ---------------------------------------------------------------------------
# 7. SAFE_TO_ENVELOPE = 0 유지 (봉투 미적용 현황 고정)
# ---------------------------------------------------------------------------

def test_safe_to_envelope_still_zero():
    """기존 endpoint에 ApiResponse 봉투가 임의 적용되지 않았음을 고정한다."""
    from fastapi.testclient import TestClient
    from ai_orchestrator.server import app

    client = TestClient(app, raise_server_exceptions=False)

    # 대표 LEGACY_DIRECT_DICT endpoint — 최상위 success 키 없음
    r = client.get("/api/v1/logs")
    assert r.status_code == 200
    data = r.json()
    # list 반환이거나, dict 반환이어도 success 키 없음
    if isinstance(data, dict):
        assert "success" not in data
    # list면 통과 (봉투 없음)


# ---------------------------------------------------------------------------
# 8. domain 패키지 — cycle 없이 import
# ---------------------------------------------------------------------------

def test_domain_package_no_cycle_after_fix():
    from ai_orchestrator.domain.enums import RiskLevel, TaskStatus
    from ai_orchestrator.domain.response_envelope import api_success
    from ai_orchestrator.domain.response_adapter import wrap_legacy_dict
    assert RiskLevel.LOW == "low"
    assert api_success(data={"x": 1}).success is True
    assert wrap_legacy_dict({"y": 2}).data == {"y": 2}
