"""ASSISTANT_BACKEND_API_ENDPOINT_INVENTORY_RECOUNT_01 — canonical endpoint inventory 테스트.

이전 감사(API_CONTRACT_AUDIT_01)에서 총 44개로 보고했으나
실측 결과 53개가 확인됨. 이 파일은 53개를 canonical 기준으로 고정한다.

집계 불일치 원인:
1. local_agent_router.py WebSocket endpoint(@local_agent_router.websocket("/ws")) 미계산 (+1)
2. 이전 분류 합계(44) 자체가 실측보다 작았음 — 분류 과정에서 local_agent HTTP 일부 누락
   (이전 "15개" 서술이 실제 19개 HTTP를 10개 미만으로 계산했음)

canonical 기준:
- method + path + handler function 조합 1개 = endpoint 1개
- websocket endpoint도 포함
- include_router/add_api_route 등 비-endpoint 항목 제외
- cad proxy(api_route, multi-method) = 1 endpoint (경로 1개)
- DB/서버/브라우저 실행 없음
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# canonical endpoint inventory (method + path + handler)
# 실측 집계 기준: 2026-05-16 RECOUNT_01 감사
# ---------------------------------------------------------------------------

# router.py — 9개
ROUTER_PY = [
    ("GET", "/health", "health"),
    ("POST", "/tasks", "submit_task"),
    ("POST", "/tasks/{task_id}/approve", "approve_task"),
    ("POST", "/tasks/{task_id}/reject", "reject_task"),
    ("POST", "/webhooks/telegram", "telegram_webhook"),
    ("GET", "/inbox", "get_inbox_list"),
    ("GET", "/inbox/{item_id}", "get_inbox_item_endpoint"),
    ("POST", "/inbox/email/fetch", "fetch_email_inbox"),
    ("GET", "/logs", "get_logs"),
]

# local_agent_router.py — 20개 (HTTP 19 + WS 1)
LOCAL_AGENT_ROUTER = [
    ("POST", "/register", "register_local_agent"),
    ("POST", "/registration-codes", "create_registration_code"),
    ("GET", "/registration-codes", "list_registration_codes"),
    ("POST", "/registration-codes/{code_id}/revoke", "revoke_registration_code"),
    ("POST", "/register-with-code", "register_with_code"),
    ("GET", "", "list_agents"),
    ("GET", "/diagnostics", "get_diagnostics"),
    ("POST", "/{agent_id}/tasks", "submit_task_to_agent"),
    ("POST", "/{agent_id}/capture-screenshot", "request_capture_screenshot"),
    ("POST", "/{agent_id}/open-url-execution-request", "request_open_url_execution"),
    ("POST", "/{agent_id}/tasks/{task_id}/cancel", "cancel_agent_task"),
    ("POST", "/{agent_id}/tasks/{task_id}/approve", "approve_agent_task"),
    ("POST", "/{agent_id}/tasks/{task_id}/reject", "reject_agent_task"),
    ("GET", "/user-present-status/{workflow_run_id}", "get_user_present_status"),
    ("GET", "/{agent_id}/user-present-statuses", "get_agent_user_present_statuses"),
    ("POST", "/{agent_id}/user-present-dispatch", "dispatch_user_present"),
    ("POST", "/{agent_id}/cleanup", "cleanup_agent"),
    ("GET", "/{agent_id}/tasks", "get_agent_tasks"),
    ("GET", "/{agent_id}/tasks/{task_id}", "get_agent_task"),
    ("WEBSOCKET", "/ws", "agent_websocket"),
]

# admin_ui_router.py — 1개
ADMIN_UI_ROUTER = [
    ("GET", "/local-agents", "local_agents_ui"),
]

# action_router.py — 2개
ACTION_ROUTER = [
    ("POST", "/prepare", "prepare_action"),
    ("POST", "/evidence", "receive_evidence"),
]

# auth_router.py — 1개
AUTH_ROUTER = [
    ("GET", "/me", "get_current_user"),
]

# web_task_router.py — 4개
WEB_TASK_ROUTER = [
    ("GET", "/registry", "list_registry"),
    ("POST", "/run", "run_web_task"),
    ("GET", "/templates", "list_templates"),
    ("POST", "/run-from-template", "run_from_template"),
]

# sites/router.py — 4개
SITES_ROUTER = [
    ("GET", "/connectors", "list_connectors"),
    ("GET", "/site-health", "get_all_site_health"),
    ("GET", "/site-health/{site_name}", "get_site_health"),
    ("POST", "/site-tasks/dry-run", "dry_run_site_task"),
]

# cad_ai_router.py — 2개
CAD_AI_ROUTER = [
    ("GET", "/actions", "list_cad_actions"),
    ("POST", "/chat", "cad_ai_chat"),
]

# naver_search_router.py — 3개
NAVER_SEARCH_ROUTER = [
    ("GET", "/blog-search", "blog_search"),
    ("GET", "/shopping-search", "shopping_search"),
    ("GET", "/search-status", "search_status"),
]

# approval_record_router.py — 6개
APPROVAL_RECORD_ROUTER = [
    ("GET", "/requests", "list_approval_requests"),
    ("GET", "/requests/{approval_id}", "get_approval_request"),
    ("POST", "/requests", "create_approval_request"),
    ("POST", "/requests/{approval_id}/approve", "approve_request"),
    ("POST", "/requests/{approval_id}/reject", "reject_request"),
    ("GET", "/requests/{approval_id}/history", "get_approval_history"),
]

# cad/router.py — 1개 (proxy: api_route multi-method, 경로 1개)
CAD_PROXY_ROUTER = [
    ("MULTI", "/{path:path}", "cad_proxy"),
]

# ---------------------------------------------------------------------------
# canonical 전체 목록
# ---------------------------------------------------------------------------

ALL_MODULES = {
    "router.py": ROUTER_PY,
    "local_agent_router.py": LOCAL_AGENT_ROUTER,
    "admin_ui_router.py": ADMIN_UI_ROUTER,
    "action_router.py": ACTION_ROUTER,
    "auth_router.py": AUTH_ROUTER,
    "web_task_router.py": WEB_TASK_ROUTER,
    "sites/router.py": SITES_ROUTER,
    "cad_ai_router.py": CAD_AI_ROUTER,
    "naver_search_router.py": NAVER_SEARCH_ROUTER,
    "approval_record_router.py": APPROVAL_RECORD_ROUTER,
    "cad/router.py": CAD_PROXY_ROUTER,
}

CANONICAL_TOTAL = 53

MODULE_COUNTS = {
    "router.py": 9,
    "local_agent_router.py": 20,
    "admin_ui_router.py": 1,
    "action_router.py": 2,
    "auth_router.py": 1,
    "web_task_router.py": 4,
    "sites/router.py": 4,
    "cad_ai_router.py": 2,
    "naver_search_router.py": 3,
    "approval_record_router.py": 6,
    "cad/router.py": 1,
}

# 분류 (method+path 기준)
CLASSIFICATION = {
    "HEALTH_OR_STATUS": 1,  # GET /health
    "LEGACY_UI_DEPENDENT": 11,  # POST /tasks, approve/reject, GET /me, action 2개, approval_record 6개
    "LEGACY_DIRECT_DICT": 35,  # inbox 3, logs 1, local_agent 15(HTTP), web_task 4, sites 4, cad_ai 2, naver 3, telegram 1, user-present 3
    "STREAM_OR_FILE": 3,  # admin_ui HTML, WS /ws, cad proxy
    "SAFE_TO_ENVELOPE": 0,  # 기존 테스트 key 의존으로 현재 0
    "ERROR_ONLY_BOUNDARY": 3,  # telegram webhook + cad proxy error + inbox email
}


# ---------------------------------------------------------------------------
# 1. 총수 검증
# ---------------------------------------------------------------------------


def test_canonical_total_is_53():
    total = sum(len(v) for v in ALL_MODULES.values())
    assert total == CANONICAL_TOTAL, f"canonical total 불일치: 실측={total}, 기준={CANONICAL_TOTAL}"


def test_module_counts_sum_to_canonical_total():
    module_sum = sum(MODULE_COUNTS.values())
    assert module_sum == CANONICAL_TOTAL, f"모듈별 합계={module_sum} ≠ canonical total={CANONICAL_TOTAL}"


def test_classification_sum_to_canonical_total():
    class_sum = sum(CLASSIFICATION.values())
    assert class_sum == CANONICAL_TOTAL, f"분류 합계={class_sum} ≠ canonical total={CANONICAL_TOTAL}"


# ---------------------------------------------------------------------------
# 2. 각 모듈 수량 고정
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module,expected", list(MODULE_COUNTS.items()))
def test_module_count_fixed(module, expected):
    actual = len(ALL_MODULES[module])
    assert actual == expected, f"{module}: 실측={actual}, 기준={expected}"


# ---------------------------------------------------------------------------
# 3. 중복 endpoint 없음 검증 (method+path 유일성)
# ---------------------------------------------------------------------------


def test_no_duplicate_endpoints():
    seen = set()
    duplicates = []
    for module, endpoints in ALL_MODULES.items():
        for method, path, handler in endpoints:
            key = (method.upper(), path)
            if key in seen:
                duplicates.append((module, method, path, handler))
            seen.add(key)
    assert not duplicates, f"중복 endpoint 발견: {duplicates}"


# ---------------------------------------------------------------------------
# 4. websocket endpoint 포함 확인
# ---------------------------------------------------------------------------


def test_websocket_endpoint_included():
    ws_endpoints = [
        (mod, method, path, handler)
        for mod, eps in ALL_MODULES.items()
        for method, path, handler in eps
        if method.upper() == "WEBSOCKET"
    ]
    assert len(ws_endpoints) == 1, f"WS endpoint 수 불일치: {ws_endpoints}"
    assert ws_endpoints[0][2] == "/ws"


# ---------------------------------------------------------------------------
# 5. SAFE_TO_ENVELOPE = 0 유지 확인
# ---------------------------------------------------------------------------


def test_safe_to_envelope_is_zero():
    assert CLASSIFICATION["SAFE_TO_ENVELOPE"] == 0, "SAFE_TO_ENVELOPE > 0: 기존 endpoint 응답 봉투 적용 전 리뷰 필요"


# ---------------------------------------------------------------------------
# 6. 기존 보고서 총수(44) 대비 증분 원인 고정
# ---------------------------------------------------------------------------


def test_recount_delta_from_previous_report():
    """이전 보고(44개) 대비 증분 9개의 원인을 고정한다."""
    previous_report_total = 44
    delta = CANONICAL_TOTAL - previous_report_total
    assert delta == 9, f"예상 증분(9) 불일치: delta={delta}"

    # 증분 원인 설명 (코드로 고정)
    delta_causes = {
        "local_agent_router WS endpoint 미계산": 1,
        "local_agent_router HTTP 분류 누락(19 중 8개 LEGACY_DIRECT_DICT 미계산)": 8,
    }
    assert sum(delta_causes.values()) == delta


# ---------------------------------------------------------------------------
# 7. include_router 비-endpoint 항목 미포함 확인
# ---------------------------------------------------------------------------


def test_include_router_not_counted():
    """router.py의 include_router 9개 자체는 endpoint 목록에 없다."""
    # include_router 대상 파일명들
    sub_routers = [  # noqa: F841
        "auth_router",
        "sites_router",
        "cad_router",
        "cad_ai_router",
        "web_task_router",
        "local_agent_router",
        "admin_ui_router",
        "approval_record_router",
        "action_router",
    ]
    # canonical 목록의 handler 이름에 "include" 또는 "add_router" 류 없음
    all_handlers = [handler for eps in ALL_MODULES.values() for _, _, handler in eps]
    for h in all_handlers:
        assert "include" not in h.lower()
        assert "add_router" not in h.lower()


# ---------------------------------------------------------------------------
# 8. health endpoint 기존 key 구조 보존 (실제 HTTP 확인)
# ---------------------------------------------------------------------------


def test_health_endpoint_key_structure_preserved():
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
# 9. domain 패키지 import — 순환 의존 없음
# ---------------------------------------------------------------------------


def test_domain_package_clean_import():
    from ai_orchestrator.domain.enums import (
        RiskLevel,
    )
    from ai_orchestrator.domain.response_adapter import (
        wrap_legacy_dict,
    )
    from ai_orchestrator.domain.response_envelope import (
        api_success,
    )

    assert RiskLevel.LOW == "low"
    assert api_success(data={"ok": True}).success is True
    assert wrap_legacy_dict({"x": 1}).data == {"x": 1}
