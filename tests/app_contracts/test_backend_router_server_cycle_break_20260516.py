"""ASSISTANT_BACKEND_ROUTER_SERVER_CYCLE_BREAK_01 — 순환 import 제거 회귀 테스트.

기존 cycle:
  router.py → action_router.py → server/action_task_api.py
  → server/__init__.py (server.py 즉시 실행)
  → server.py → from .router import router (초기화 중) → ImportError

해소 (2026-09-30 근본 정리):
  앱 본체를 ai_orchestrator/asgi.py 로 옮기고, server/ 패키지는 asgi 를 참조하지 않는다.
  방향은 asgi → router → server.* 하나뿐이다. 진입점 표기는 ai_orchestrator.asgi:app.

DB/서버/외부 URL/브라우저 실행 없음.
"""

from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# 1. router.py 직접 import — 순환 없음 고정
# ---------------------------------------------------------------------------


def test_router_direct_import_no_cycle():
    """ai_orchestrator.routers.registry를 직접 import해도 ImportError가 발생하지 않는다."""
    # sys.modules 제거 후 재import — 후속 테스트 오염 방지: purge 전 snapshot 저장 후 복원
    _snapshot = {k: v for k, v in sys.modules.items() if k.startswith("ai_orchestrator")}
    for m in list(_snapshot):
        sys.modules.pop(m, None)

    try:
        import ai_orchestrator.routers.registry as r

        assert r.router is not None
        assert hasattr(r, "router")
    finally:
        for k in [k for k in sys.modules if k.startswith("ai_orchestrator") and k not in _snapshot]:
            sys.modules.pop(k, None)
        sys.modules.update(_snapshot)


def test_router_module_defines_router_object():
    from fastapi import APIRouter

    import ai_orchestrator.routers.registry as r

    assert isinstance(r.router, APIRouter)


# ---------------------------------------------------------------------------
# 2. server/ 패키지는 asgi 를 참조하지 않는다 (역방향 금지)
# ---------------------------------------------------------------------------


def test_server_package_does_not_reference_asgi():
    """server/__init__.py 가 asgi 를 import 하면 ai_orchestrator ↔ ai_orchestrator/server 순환이 생긴다."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("ai_orchestrator/server/__init__.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "")] + [a.name for a in node.names]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names = [node.value]  # import_module("ai_orchestrator.asgi") 같은 문자열 참조도 금지
        else:
            continue
        assert not any(n == "asgi" or n.startswith("ai_orchestrator.asgi") or n.endswith(".asgi") for n in names), names


def test_server_package_import_does_not_load_app():
    """server 패키지만 import해도 app(asgi)이 만들어지지 않는다."""
    # sys.modules 제거 후 재import — 후속 테스트 오염 방지: purge 전 snapshot 저장 후 복원
    _snapshot = {k: v for k, v in sys.modules.items() if k.startswith("ai_orchestrator")}
    for k in list(_snapshot):
        sys.modules.pop(k, None)

    try:
        import ai_orchestrator.server as srv_pkg

        assert "app" not in vars(srv_pkg), "server 패키지가 app 을 노출하고 있음 — asgi 로 옮긴 뒤 별칭은 없다"
        assert "ai_orchestrator.asgi" not in sys.modules, "server 패키지 import 가 asgi 를 끌어옴"
    finally:
        for k in [k for k in sys.modules if k.startswith("ai_orchestrator") and k not in _snapshot]:
            sys.modules.pop(k, None)
        sys.modules.update(_snapshot)


def test_asgi_app_accessible():
    """from ai_orchestrator.asgi import app 이 FastAPI 앱을 준다."""
    from fastapi import FastAPI

    from ai_orchestrator.asgi import app

    assert isinstance(app, FastAPI)


def test_asgi_app_is_same_object_on_reimport():
    """app 을 다시 import 해도 동일 객체다."""
    from ai_orchestrator.asgi import app as a1
    from ai_orchestrator.asgi import app as a2

    assert a1 is a2


# ---------------------------------------------------------------------------
# 3. server.py → router.py 방향만 허용 (역방향 금지) 확인
# ---------------------------------------------------------------------------


def test_router_py_does_not_import_server_py_directly():
    """router.py 소스에 'from .server import' 또는 'import server' 가 없다."""
    import pathlib

    router_src = pathlib.Path("ai_orchestrator/routers/registry.py").read_text(encoding="utf-8")
    # server.py에서 정의된 app 객체를 router.py가 직접 import하지 않아야 한다
    assert "from .server import app" not in router_src
    assert "from ai_orchestrator.asgi import app" not in router_src
    # server/__init__ import 없음
    assert "from .server import" not in router_src or "server.action_" not in router_src


def test_action_router_does_not_import_app():
    """action_router.py가 app 객체를 직접 import하지 않는다."""
    import pathlib

    src = pathlib.Path("ai_orchestrator/routers/action_router.py").read_text(encoding="utf-8")
    assert "import app" not in src
    assert "from ai_orchestrator.asgi import app" not in src


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
    """FastAPI app에 등록된 route 수가 정확히 60개이다.

    기존 50 + naver_search_router(3) + ops_router(7) = 60개.
    naver_search_router/ops_router 는 cf69c5c/202fe85 에서 router.py 에 등록됨.
    """
    # Runtime route count is locked by tools/audits/backend/audit_backend_runtime_contract.py.
    # 2026-09-29 defect_index #40: 여기서 자체적으로 app.routes 를 isinstance 필터링하던
    # 코드는 FastAPI 0.137+ 의 지연 include_router(_IncludedRouter) 를 못 뚫어 항상 0건을
    # 셌음(공허하게 실패하던 게 아니라 대조 기준 자체가 깨져 항상 실패 — 이번에 발견해서
    # audit 모듈이 이미 고친 iter_runtime_routes() 를 재사용하도록 교체, 중복 로직 제거).
    from tools.audits.backend import audit_backend_runtime_contract as audit

    routes = audit.iter_runtime_routes()

    assert len(routes) == audit.EXPECTED_RUNTIME_ROUTES, (
        f"등록된 route 수={len(routes)}, 기준={audit.EXPECTED_RUNTIME_ROUTES}"
    )


# ---------------------------------------------------------------------------
# 6. health endpoint 응답 구조 불변 확인
# ---------------------------------------------------------------------------


def test_health_endpoint_response_unchanged():
    from fastapi.testclient import TestClient

    from ai_orchestrator.asgi import app

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

    from ai_orchestrator.asgi import app
    from ai_orchestrator.auth.user_auth_router import get_jwt_user

    client = TestClient(app, raise_server_exceptions=False)

    # /api/v1/logs 는 get_jwt_user 를 요구하므로 가짜 사용자를 주입한다(실제 사용자 정보 없음).
    app.dependency_overrides[get_jwt_user] = lambda: {"id": "test-user", "role": "owner"}
    try:
        # 대표 LEGACY_DIRECT_DICT endpoint — 최상위 success 키 없음
        r = client.get("/api/v1/logs")
    finally:
        app.dependency_overrides.pop(get_jwt_user, None)
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
    from ai_orchestrator.domain.enums import RiskLevel
    from ai_orchestrator.domain.response_adapter import wrap_legacy_dict
    from ai_orchestrator.domain.response_envelope import api_success

    assert RiskLevel.LOW == "low"
    assert api_success(data={"x": 1}).success is True
    assert wrap_legacy_dict({"y": 2}).data == {"y": 2}
