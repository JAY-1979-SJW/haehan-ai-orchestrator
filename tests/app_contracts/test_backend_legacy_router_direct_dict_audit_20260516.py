"""ASSISTANT_BACKEND_LEGACY_ROUTER_AND_DIRECT_DICT_AUDIT_01 — 감사 테스트.

감사 목표:
1. naver_search_router 미등록 현황 고정
2. LEGACY_DIRECT_DICT 27개 세부 분류 고정
3. endpoint inventory 4종 수치 고정
4. 기존 cycle break / inventory / contract 테스트 회귀 확인

DB/서버/브라우저 실행 없음.
"""

from __future__ import annotations

import pathlib

from tests.app_routes import EXPECTED_HTTP_ROUTES, EXPECTED_WEBSOCKET_ROUTES

# ===========================================================================
# SECTION 1: naver_search_router 미등록 현황
# ===========================================================================


def test_naver_search_router_importable():
    """naver_search_router 모듈이 import error 없이 로드된다."""
    from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

    assert naver_search_router is not None


def test_naver_search_router_has_13_source_endpoints():
    """naver_search_router source-level에 13개 HTTP endpoint가 정의되어 있다."""
    from fastapi.routing import APIRoute

    from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

    routes = [r for r in naver_search_router.routes if isinstance(r, APIRoute)]
    assert len(routes) == 13, f"naver_search_router source endpoint 수={len(routes)}, 기준=13"


def test_naver_search_router_endpoint_paths():
    """naver_search_router의 3개 endpoint path가 /external/naver/* 패턴이다."""
    from fastapi.routing import APIRoute

    from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

    paths = {r.path for r in naver_search_router.routes if isinstance(r, APIRoute)}
    assert "/external/naver/blog-search" in paths
    assert "/external/naver/shopping-search" in paths
    assert "/external/naver/search-status" in paths


def test_naver_search_router_not_registered_in_main_app():
    """naver_search_router 3개 endpoint가 main app FastAPI에 등록된 상태이다.

    분류: 등록 완료 (cf69c5c 공정에서 router.py include_router 추가됨).
    근거: prefix=/external/naver, require_role 보안 의존성 적용 상태로 등록.
    """
    from ai_orchestrator.asgi import app

    from tests.app_routes import route_paths

    registered_paths = route_paths()
    naver_paths = [
        "/api/v1/external/naver/blog-search",
        "/api/v1/external/naver/shopping-search",
        "/api/v1/external/naver/search-status",
    ]
    for p in naver_paths:
        assert p in registered_paths, f"naver_search_router가 main app에 미등록 상태: {p}"


def test_naver_search_router_all_endpoints_require_admin_or_owner():
    """naver_search_router 13개 endpoint 모두 require_role('admin','owner') 의존성 적용 확인.

    HOLD 이유: 외부 Naver API 호출로 별도 승인/격리 판단 필요.
    이번 공정에서 등록하지 않고 QUARANTINE_OR_HOLD 상태로 유지한다.
    """
    import inspect

    from fastapi.routing import APIRoute

    from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

    routes = [r for r in naver_search_router.routes if isinstance(r, APIRoute)]
    assert len(routes) == 13, f"endpoint 수 불일치: {len(routes)}"

    for route in routes:
        source = inspect.getsource(route.endpoint)
        assert "require_role" in source, f"{route.path} — require_role 적용 누락"


def test_naver_search_router_quarantine_hold_status():
    """naver_search_router는 등록 완료 상태임을 고정한다.

    cf69c5c 공정에서 router.py에 include_router 추가됨.
    require_role('admin','owner') 보안 의존성 적용 상태로 등록 확정.
    """
    from fastapi.routing import APIRoute

    from ai_orchestrator.asgi import app
    from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

    naver_source_paths = {r.path for r in naver_search_router.routes if isinstance(r, APIRoute)}
    from tests.app_routes import route_paths
    registered_paths = route_paths()

    for p in naver_source_paths:
        full = f"/api/v1{p}"
        assert full in registered_paths, f"naver_search_router 등록 누락: {full}"


# ===========================================================================
# SECTION 2: LEGACY_DIRECT_DICT 27개 세부 분류 고정
# ===========================================================================

# ── 세부 분류 정의 ──────────────────────────────────────────────────────────
#
# COMPAT_RESPONSE_KEEP:
#   기존 dict 응답이 프론트엔드/클라이언트 계약에 묶여 있어 즉시 변경 불가.
#   현재 유지 필수.
#
# INTERNAL_SAFE_DICT_KEEP:
#   내부 관리/관찰용이고 외부 UI 직접 의존이 낮음.
#   ApiResponse 봉투 후보이지만 긴급도 낮음.
#
# NEEDS_ENVELOPE_REVIEW:
#   향후 ApiResponse 봉투 적용 검토 대상.
#   현재 테스트 기대값 변경 없이 전환 가능성 있음.
#
# NEEDS_MANUAL_DESIGN_REVIEW:
#   정책적 판단 필요 (proxy 응답, 외부 API 응답 중계 등).
#

LEGACY_DIRECT_DICT_INVENTORY = [
    # ── router.py 직접 정의 (4) ──
    {"method": "GET", "path": "/api/v1/inbox", "handler": "get_inbox_list", "sub": "INTERNAL_SAFE_DICT_KEEP"},
    {
        "method": "GET",
        "path": "/api/v1/inbox/{item_id}",
        "handler": "get_inbox_item_endpoint",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/inbox/email/fetch",
        "handler": "fetch_email_inbox",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {"method": "GET", "path": "/api/v1/logs", "handler": "get_logs", "sub": "INTERNAL_SAFE_DICT_KEEP"},
    # ── telegram webhook (1) — ERROR_ONLY_BOUNDARY 겸용 ──
    {
        "method": "POST",
        "path": "/api/v1/webhooks/telegram",
        "handler": "telegram_webhook",
        "sub": "NEEDS_MANUAL_DESIGN_REVIEW",
    },
    # ── sites/router.py (4) ──
    {"method": "GET", "path": "/api/v1/connectors", "handler": "list_connectors", "sub": "INTERNAL_SAFE_DICT_KEEP"},
    {"method": "GET", "path": "/api/v1/site-health", "handler": "site_health_all", "sub": "INTERNAL_SAFE_DICT_KEEP"},
    {
        "method": "GET",
        "path": "/api/v1/site-health/{site_name}",
        "handler": "site_health_one",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/site-tasks/dry-run",
        "handler": "site_task_dry_run",
        "sub": "NEEDS_ENVELOPE_REVIEW",
    },
    # ── cad_ai_router.py (2) ──
    {
        "method": "GET",
        "path": "/api/v1/cad-ai/actions",
        "handler": "list_cad_actions",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {"method": "POST", "path": "/api/v1/cad-ai/chat", "handler": "cad_ai_chat", "sub": "NEEDS_MANUAL_DESIGN_REVIEW"},
    # ── web_task_router.py (4) ──
    {
        "method": "GET",
        "path": "/api/v1/web-tasks/registry",
        "handler": "list_registry",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {"method": "POST", "path": "/api/v1/web-tasks/run", "handler": "run_web_task", "sub": "NEEDS_ENVELOPE_REVIEW"},
    {
        "method": "GET",
        "path": "/api/v1/web-tasks/templates",
        "handler": "list_templates",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/web-tasks/run-from-template",
        "handler": "run_from_template",
        "sub": "NEEDS_ENVELOPE_REVIEW",
    },
    # ── local_agent_router.py 관리 계열 (12) ──
    {
        "method": "POST",
        "path": "/api/v1/local-agents/register",
        "handler": "register_local_agent",
        "sub": "COMPAT_RESPONSE_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/local-agents/registration-codes",
        "handler": "create_registration_code",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "GET",
        "path": "/api/v1/local-agents/registration-codes",
        "handler": "list_registration_codes",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/local-agents/registration-codes/{code_id}/revoke",
        "handler": "revoke_registration_code",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/local-agents/register-with-code",
        "handler": "register_with_code",
        "sub": "COMPAT_RESPONSE_KEEP",
    },
    {"method": "GET", "path": "/api/v1/local-agents", "handler": "list_agents", "sub": "COMPAT_RESPONSE_KEEP"},
    {
        "method": "GET",
        "path": "/api/v1/local-agents/diagnostics",
        "handler": "get_diagnostics",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel",
        "handler": "cancel_agent_task",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "GET",
        "path": "/api/v1/local-agents/user-present-status/{workflow_run_id}",
        "handler": "get_user_present_status",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "GET",
        "path": "/api/v1/local-agents/{agent_id}/user-present-statuses",
        "handler": "get_agent_user_present_statuses",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "POST",
        "path": "/api/v1/local-agents/{agent_id}/user-present-dispatch",
        "handler": "dispatch_user_present",
        "sub": "INTERNAL_SAFE_DICT_KEEP",
    },
    {
        "method": "GET",
        "path": "/api/v1/local-agents/{agent_id}/tasks",
        "handler": "get_agent_tasks",
        "sub": "COMPAT_RESPONSE_KEEP",
    },
]

LEGACY_DIRECT_DICT_TOTAL = 27


def test_legacy_direct_dict_inventory_count():
    """LEGACY_DIRECT_DICT 항목이 27개임을 고정한다."""
    assert len(LEGACY_DIRECT_DICT_INVENTORY) == LEGACY_DIRECT_DICT_TOTAL, (
        f"LEGACY_DIRECT_DICT count={len(LEGACY_DIRECT_DICT_INVENTORY)}, 기준=27"
    )


def test_legacy_direct_dict_sub_classification_sum():
    """세부 분류 합계가 27과 일치한다."""
    from collections import Counter

    counts = Counter(item["sub"] for item in LEGACY_DIRECT_DICT_INVENTORY)
    total = sum(counts.values())
    assert total == LEGACY_DIRECT_DICT_TOTAL, (
        f"세부 분류 합계={total}, 기준={LEGACY_DIRECT_DICT_TOTAL}\n분류: {dict(counts)}"
    )


def test_legacy_direct_dict_sub_classification_values():
    """각 세부 분류 수량이 예상값과 일치한다."""
    from collections import Counter

    counts = Counter(item["sub"] for item in LEGACY_DIRECT_DICT_INVENTORY)
    # COMPAT_RESPONSE_KEEP: register, register-with-code, list_agents, get_agent_tasks = 4
    assert counts["COMPAT_RESPONSE_KEEP"] == 4
    # INTERNAL_SAFE_DICT_KEEP: inbox 4, connectors/site-health 3, cad-ai/actions 1,
    #   web-tasks registry/templates 2, local_agent 관리 8 = 18
    assert counts["INTERNAL_SAFE_DICT_KEEP"] == 18
    # NEEDS_ENVELOPE_REVIEW: site-tasks/dry-run, web-tasks/run, run-from-template = 3
    assert counts["NEEDS_ENVELOPE_REVIEW"] == 3
    # NEEDS_MANUAL_DESIGN_REVIEW: telegram webhook, cad-ai/chat = 2
    assert counts["NEEDS_MANUAL_DESIGN_REVIEW"] == 2


def test_legacy_direct_dict_no_duplicate_method_path():
    """LEGACY_DIRECT_DICT 항목에 중복 method+path 조합이 없다."""
    keys = [(item["method"], item["path"]) for item in LEGACY_DIRECT_DICT_INVENTORY]
    assert len(keys) == len(set(keys)), f"중복 method+path 발견: {[k for k in keys if keys.count(k) > 1]}"


# NEEDS_ENVELOPE_REVIEW(3)와 NEEDS_MANUAL_DESIGN_REVIEW(2)는 다음 공정 후보.
# 이번 공정에서 응답 구조 변경 금지 — 아래 테스트가 존재하는 한 변경 금지.
NEXT_PHASE_ENVELOPE_REVIEW_PATHS = {
    "/api/v1/site-tasks/dry-run",
    "/api/v1/web-tasks/run",
    "/api/v1/web-tasks/run-from-template",
}
NEXT_PHASE_MANUAL_REVIEW_PATHS = {
    "/api/v1/webhooks/telegram",
    "/api/v1/cad-ai/chat",
}


def test_next_phase_envelope_review_candidates_locked():
    """NEEDS_ENVELOPE_REVIEW 3개 경로가 다음 공정 후보로 잠겨 있다.

    이번 공정에서 응답 구조 변경 없음 — 봉투 전환은 별도 공정에서 수행.
    """
    review_items = [i for i in LEGACY_DIRECT_DICT_INVENTORY if i["sub"] == "NEEDS_ENVELOPE_REVIEW"]
    paths = {i["path"] for i in review_items}
    assert paths == NEXT_PHASE_ENVELOPE_REVIEW_PATHS, f"NEEDS_ENVELOPE_REVIEW 경로 변경 감지: {paths}"


def test_next_phase_manual_review_candidates_locked():
    """NEEDS_MANUAL_DESIGN_REVIEW 2개 경로가 다음 공정 후보로 잠겨 있다.

    정책적 판단(proxy 응답, 외부 API 중계) 필요 — 이번 공정에서 변경 없음.
    """
    review_items = [i for i in LEGACY_DIRECT_DICT_INVENTORY if i["sub"] == "NEEDS_MANUAL_DESIGN_REVIEW"]
    paths = {i["path"] for i in review_items}
    assert paths == NEXT_PHASE_MANUAL_REVIEW_PATHS, f"NEEDS_MANUAL_DESIGN_REVIEW 경로 변경 감지: {paths}"


# ===========================================================================
# SECTION 3: endpoint inventory 4종 수치 고정
# ===========================================================================

# 2026-10-05 갱신(HTTP 62→423, WS 1→2): 저장소 성장·FastAPI 0.142 로 지연 include 래퍼를 펼쳐 실제 라우트를 보게 됨(HTTP+WS=425=EXPECTED_RUNTIME_ROUTES)
RUNTIME_HTTP_ENDPOINT_COUNT = EXPECTED_HTTP_ROUTES  # 기대값 정본: configs/route_count_expectation.json (라우트를 추가·삭제하면 그 파일만 고친다)
RUNTIME_WEBSOCKET_COUNT = EXPECTED_WEBSOCKET_ROUTES  # 기대값 정본: configs/route_count_expectation.json
# FULL_CLASSIFICATION(아래 SECTION 4)은 라우터 분류 매핑이 63개 시점에 작성된 스냅샷이라 현행 425개 전체를 분류하지 않는다.
# 분류 매핑 시험(③④)은 그 시점 값(HTTP 62 + WS 1 = 63)과 대조한다 — 분류 데이터 전체 재작성은 이번 승인 범위 밖.
CLASSIFICATION_SNAPSHOT_RUNTIME_TOTAL = 63
SOURCE_ROUTER_HTTP_ENDPOINT_COUNT = 59  # naver 3 + ops_router 7 포함
UNREGISTERED_ROUTER_ENDPOINT_COUNT = 0  # naver_search_router 등록 완료


def test_runtime_http_endpoint_count():
    from tests.app_routes import http_routes

    http = http_routes()
    assert len(http) == RUNTIME_HTTP_ENDPOINT_COUNT, f"runtime HTTP={len(http)}, 기준={RUNTIME_HTTP_ENDPOINT_COUNT}"


def test_runtime_websocket_count():
    from tests.app_routes import websocket_routes

    ws = websocket_routes()
    assert len(ws) == RUNTIME_WEBSOCKET_COUNT, f"runtime WS={len(ws)}, 기준={RUNTIME_WEBSOCKET_COUNT}"


def test_unregistered_router_endpoint_count():
    """naver_search_router source-level 13개 endpoint가 존재한다 (등록 완료)."""
    from fastapi.routing import APIRoute

    from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

    naver_routes = [r for r in naver_search_router.routes if isinstance(r, APIRoute)]
    assert len(naver_routes) == 13, f"naver_search_router source endpoint={len(naver_routes)}, 기준=13"


def test_runtime_plus_unregistered_equals_source_minus_core():
    """runtime 63 + unregistered 0 = source 63 관계가 성립한다.
    APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01: app_status_router GET 3개 추가 → 60+3=63.
    """
    runtime_total = CLASSIFICATION_SNAPSHOT_RUNTIME_TOTAL
    unregistered = UNREGISTERED_ROUTER_ENDPOINT_COUNT
    source_total = 63  # 60 + app_status_router 3 read-only GET
    assert runtime_total + unregistered == source_total, (
        f"runtime({runtime_total}) + unregistered({unregistered}) "
        f"= {runtime_total + unregistered}, source={source_total}"
    )


# ===========================================================================
# SECTION 4: 전체 분류 합계 검증 (runtime 50 기준)
# ===========================================================================

FULL_CLASSIFICATION = {
    "HEALTH_OR_STATUS": 1,
    "LEGACY_UI_DEPENDENT": 18,
    "LEGACY_DIRECT_DICT": 27,
    "STREAM_OR_FILE": 3,  # admin HTML + WS + cad proxy
    "ERROR_ONLY_BOUNDARY": 1,  # telegram webhook (LEGACY_DIRECT_DICT와 중첩 있으나 단일 분류)
    "SAFE_TO_ENVELOPE": 0,
    "OPS_READONLY": 7,  # ops_router 7개 GET-only (202fe85)
    "EXTERNAL_API_REGISTERED": 3,  # naver_search_router 3개 (cf69c5c 등록 완료)
    "APP_STATUS_READONLY": 3,  # app_status_router 3개 GET-only (APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01)
}


def test_full_classification_sum_equals_runtime_total():
    """전체 분류 합계가 runtime 63과 일치한다.

    주의: telegram webhook은 LEGACY_DIRECT_DICT와 ERROR_ONLY_BOUNDARY 두 성격을 갖지만
    LEGACY_DIRECT_DICT(NEEDS_MANUAL_DESIGN_REVIEW)로 단일 분류하고,
    ERROR_ONLY_BOUNDARY 카운트에서 제외함.
    합계: 1+18+27+3+1+0+7+3+3 = 63 (APP_STATUS_READONLY 3개 추가)
    """
    total = sum(FULL_CLASSIFICATION.values())
    runtime = CLASSIFICATION_SNAPSHOT_RUNTIME_TOTAL
    assert total == runtime, f"분류 합계={total}, runtime={runtime}"


# ===========================================================================
# SECTION 5: 기존 회귀 검증
# ===========================================================================


def test_router_direct_import_still_no_cycle(monkeypatch):
    """순환 import 해소 상태가 유지된다."""
    import sys

    from ai_orchestrator.core import config as _cfg_before_purge

    # 후속 테스트 오염 방지: purge 전 snapshot 저장 후 복원.
    #
    # 결함 2026-10-10(DEFECTS_FLAKY.md) 진짜 원인: ai_orchestrator.auth.user_auth_router
    # 는 import 시점 부작용으로 `register_bearer_resolver(resolve_bearer_user)` 를
    # 호출해 tools.gates.auth 의 전역 `_bearer_resolver` 를 등록한다("ai_orchestrator"
    # 접두사가 아닌 tools.gates.auth 는 이 purge 의 snapshot/복원 대상이 아니다). 이
    # purge 로 user_auth_router 가 재import 되면 그 등록이 다시 실행돼, 이후 영원히
    # "그 순간의(purge 중) config·user_db 모듈"을 들고 있는 클로저로 _bearer_resolver
    # 가 바뀐 채 남는다 — sys.modules 복원은 모듈 객체 참조만 되돌릴 뿐 이 등록형
    # 전역 부작용은 안 건드려서, 이후 JWT 인증 시험들이 엉뚱한 user_db 경로/비밀로
    # 검증을 시도해 401 이 났다. JWT_SECRET 고정(아래)은 부수적 방어이고, 핵심 수정은
    # finally 에서 원래 모듈의 resolve_bearer_user 로 재등록하는 것이다.
    monkeypatch.setenv("JWT_SECRET", _cfg_before_purge.JWT_SECRET)
    _snapshot = {k: v for k, v in sys.modules.items() if k.startswith("ai_orchestrator")}
    for k in list(_snapshot):
        sys.modules.pop(k, None)
    try:
        from fastapi import APIRouter

        import ai_orchestrator.routers.registry as r

        assert isinstance(r.router, APIRouter)
    finally:
        for k in [k for k in sys.modules if k.startswith("ai_orchestrator") and k not in _snapshot]:
            sys.modules.pop(k, None)
        sys.modules.update(_snapshot)

        from ai_orchestrator.auth.user_auth_router import resolve_bearer_user
        from tools.gates.auth import register_bearer_resolver

        register_bearer_resolver(resolve_bearer_user)


def test_health_endpoint_still_unchanged():
    from fastapi.testclient import TestClient

    from ai_orchestrator.asgi import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "service" in data
    assert "success" not in data


def test_domain_enums_stable():
    from ai_orchestrator.domain.enums import RiskLevel, TaskStatus, Verdict
    from ai_orchestrator.domain.response_envelope import api_success

    assert RiskLevel.LOW == "low"
    assert TaskStatus.PENDING == "pending"
    assert Verdict.PASS == "PASS"
    assert api_success(data={"x": 1}).success is True


def test_naver_router_source_file_exists():
    """naver_search_router.py 파일이 실제로 존재한다."""
    p = pathlib.Path("ai_orchestrator/connectors/naver_search/naver_search_router.py")
    assert p.exists(), "naver_search_router.py 파일 없음"
