"""local_agent_router 모듈 분리 검증.

라우트군을 서브라우터로 분리하고 컴포지션 루트가 include_router 로 관리한다.
분리 전후 공개 라우트 경로가 보존되는지 검증한다. [docs/module_separation_standard.md]
"""


def _main_paths():
    from ai_orchestrator.local_agent_router import local_agent_router
    return {getattr(r, "path", "") for r in local_agent_router.routes}


def test_schemas_separated():
    """요청 모델은 schemas leaf 로 분리되고 파사드로 재노출된다."""
    from ai_orchestrator import local_agent_router_schemas as s
    for name in ("AgentRegisterRequest", "CaptureScreenshotRequest", "IssueRegistrationCodeRequest"):
        assert hasattr(s, name)
    # 파사드: 루트에서도 동일 이름 import 가능
    from ai_orchestrator.local_agent_router import AgentRegisterRequest  # noqa: F401


def test_query_router_separated():
    """진단 라우트군은 query leaf 서브라우터로 분리된다."""
    from ai_orchestrator.local_agent_router_query import query_router
    assert any("diagnostics" in getattr(r, "path", "") for r in query_router.routes)


def test_diagnostics_route_preserved_via_include():
    """분리 후에도 /diagnostics 경로가 컴포지션 루트에 포함되어 있어야 한다."""
    assert any("diagnostics" in p for p in _main_paths())


def test_list_collection_root_preserved():
    """컬렉션 루트(GET '') 는 보존된다."""
    # prefix 부착 전이라 빈 path 가 루트에 존재
    assert "" in _main_paths() or any(p == "" for p in _main_paths())
