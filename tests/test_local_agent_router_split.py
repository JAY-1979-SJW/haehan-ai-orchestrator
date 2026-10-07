"""local_agent_router 모듈 분리 검증.

라우트군을 서브라우터로 분리하고 컴포지션 루트가 include_router 로 관리한다.
분리 전후 공개 라우트 경로가 보존되는지 검증한다. [docs/module_separation_standard.md]
"""


def _main_paths():
    # FastAPI 0.137+ 는 include_router 를 즉시 펼치지 않고 지연 래퍼(_IncludedRouter)로 저장해
    # router.routes 를 바로 훑으면 path 가 없다(defect_index #39·#40) — 공식 iter_route_contexts 로 펼친다.
    from fastapi.routing import iter_route_contexts

    from ai_orchestrator.agent_hub.router.root import local_agent_router

    return {ctx.path for ctx in iter_route_contexts(local_agent_router.routes)}


def test_schemas_separated():
    """요청 모델은 schemas leaf 로 분리되고 파사드로 재노출된다."""
    from ai_orchestrator.agent_hub.router import schemas as s

    for name in ("AgentRegisterRequest", "CaptureScreenshotRequest", "IssueRegistrationCodeRequest"):
        assert hasattr(s, name)
    # 파사드: 루트에서도 동일 이름 import 가능
    from ai_orchestrator.agent_hub.router.root import AgentRegisterRequest  # noqa: F401


def test_query_router_separated():
    """진단 라우트군은 query leaf 서브라우터로 분리된다."""
    from ai_orchestrator.agent_hub.router.query import query_router

    assert any("diagnostics" in getattr(r, "path", "") for r in query_router.routes)


def test_registration_router_separated():
    """등록 라우트군은 registration leaf 서브라우터로 분리된다."""
    from ai_orchestrator.agent_hub.router.registration import registration_router

    paths = " ".join(getattr(r, "path", "") for r in registration_router.routes)
    for kw in ("/register", "/registration-codes", "/register-with-code"):
        assert kw in paths, f"누락: {kw}"


def test_registration_routes_preserved_via_include():
    """분리 후에도 등록 경로들이 컴포지션 루트에 포함되어야 한다."""
    paths = " ".join(_main_paths())
    for kw in ("/register", "/registration-codes", "/register-with-code"):
        assert kw in paths, f"루트에서 누락: {kw}"


def test_validation_helpers_separated():
    """검증/감사노트 헬퍼는 validation 공유 leaf 로 분리되고 파사드로 재노출된다."""
    from ai_orchestrator.agent_hub.router import validation as v

    assert hasattr(v, "_validate_readonly_browser_instruction")
    assert hasattr(v, "_capture_approval_note")
    # 파사드: 루트에서도 동일 이름 사용 가능
    from ai_orchestrator.agent_hub.router.root import _validate_readonly_browser_instruction  # noqa: F401


def test_validation_blocks_unsafe_instruction():
    """검증 헬퍼가 위험 지시(click 등)를 400 으로 차단한다(이동 후 동작 보존)."""
    import pytest
    from fastapi import HTTPException

    from ai_orchestrator.agent_hub.router.schemas import BrowserReadonlyInstructionRequest
    from ai_orchestrator.agent_hub.router.validation import _validate_readonly_browser_instruction

    with pytest.raises(HTTPException):
        _validate_readonly_browser_instruction(
            BrowserReadonlyInstructionRequest(instruction="click login", url="https://x.com")
        )


def test_diagnostics_route_preserved_via_include():
    """분리 후에도 /diagnostics 경로가 컴포지션 루트에 포함되어 있어야 한다."""
    assert any("diagnostics" in p for p in _main_paths())


def test_list_collection_root_preserved():
    """컬렉션 루트(GET /local-agents) 는 루트에 보존된다."""
    # APIRouter(prefix='/local-agents') 가 prefix 를 붙여 path 는 '/local-agents'
    paths = _main_paths()
    assert any(p.endswith("/local-agents") for p in paths), paths


def test_up_queue_separated():
    """USER_PRESENT 전송 대기 큐 상태/함수는 up_queue 공유 leaf 로 분리된다."""
    from ai_orchestrator.agent_hub.router import up_queue as q

    assert hasattr(q, "_enqueue_up_task") and hasattr(q, "_drain_up_tasks")
    # 동작 보존: enqueue → drain
    q._enqueue_up_task("agentX", {"k": 1})
    drained = q._drain_up_tasks("agentX")
    assert drained == [{"k": 1}]
    # 파사드: 루트에서도 동일 함수 사용 가능
    from ai_orchestrator.agent_hub.router.root import _enqueue_up_task  # noqa: F401


def test_task_query_router_separated():
    """작업 조회(list/get) 라우트군은 task leaf 서브라우터로 분리된다."""
    from ai_orchestrator.agent_hub.router.task import task_router

    paths = " ".join(getattr(r, "path", "") for r in task_router.routes)
    assert "/{agent_id}/tasks" in paths
    # 컴포지션 루트에도 포함(include)
    assert any(p.endswith("/tasks") for p in _main_paths())


def test_task_approval_routes_in_task_router():
    """작업 처리(cancel/approve/reject) 라우트군도 task leaf 로 합류된다."""
    from ai_orchestrator.agent_hub.router.task import task_router

    paths = " ".join(getattr(r, "path", "") for r in task_router.routes)
    for kw in ("/cancel", "/approve", "/reject"):
        assert kw in paths, f"task_router 누락: {kw}"
    main = " ".join(_main_paths())
    for kw in ("/cancel", "/approve", "/reject"):
        assert kw in main, f"루트 include 누락: {kw}"


def test_browser_router_separated():
    """브라우저 라우트군은 browser leaf 서브라우터로 분리된다."""
    from ai_orchestrator.agent_hub.router.browser import browser_router

    paths = " ".join(getattr(r, "path", "") for r in browser_router.routes)
    for kw in ("browser-readonly", "capture-screenshot", "open-url-execution"):
        assert kw in paths, f"browser_router 누락: {kw}"
    main = " ".join(_main_paths())
    for kw in ("browser-readonly", "capture-screenshot", "open-url-execution"):
        assert kw in main, f"루트 include 누락: {kw}"


def test_user_present_router_separated():
    """사용자임장 라우트군은 user_present leaf 서브라우터로 분리된다."""
    from ai_orchestrator.agent_hub.router.user_present import user_present_router

    paths = " ".join(getattr(r, "path", "") for r in user_present_router.routes)
    assert "user-present" in paths
    assert any("user-present" in p for p in _main_paths())


def test_cleanup_router_separated():
    """정리(cleanup) 라우트군은 cleanup leaf 서브라우터로 분리된다."""
    from ai_orchestrator.agent_hub.router.cleanup import cleanup_router

    assert any("cleanup" in getattr(r, "path", "") for r in cleanup_router.routes)
    assert any("cleanup" in p for p in _main_paths())


def test_ws_router_separated():
    """WebSocket 엔드포인트는 ws leaf 서브라우터로 분리된다."""
    from ai_orchestrator.agent_hub.router.ws import ws_router

    assert any("WebSocket" in type(r).__name__ for r in ws_router.routes)


def test_main_is_thin_composition_root():
    """컴포지션 루트는 얇아야 한다(≤150 LOC) — 모든 라우트군이 leaf 로 분리됨."""
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "ai_orchestrator" / "agent_hub" / "router" / "root.py"
    loc = sum(1 for _ in p.open(encoding="utf-8"))
    assert loc <= 150, f"루트가 너무 큼: {loc} LOC"
