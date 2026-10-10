"""APP_FOUNDATION_MVP_DESIGN_01 테스트.

비서앱 MVP UI shell 착공 전 상세 설계 검증.
설계/감리 전용 — 실제 앱 코드 수정 없음.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def design():
    import tools.audits.app.audit_app_foundation_mvp_design as m
    return m


@pytest.fixture(scope="module")
def audit_report(design):
    return design.run_audit()


# ── 1. import / AUDIT_ID ─────────────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_foundation_mvp_design  # noqa: F401


def test_audit_id_correct(design):
    assert design.AUDIT_ID == "APP_FOUNDATION_MVP_DESIGN"


# ── 2. 안전 잠금 ─────────────────────────────────────────────────────────────

def test_implementation_allowed_false(design):
    assert design.IMPLEMENTATION_ALLOWED is False


def test_frontend_code_change_allowed_false(design):
    assert design.FRONTEND_CODE_CHANGE_ALLOWED is False


def test_backend_code_change_allowed_false(design):
    assert design.BACKEND_CODE_CHANGE_ALLOWED is False


def test_server_apply_allowed_false(design):
    assert design.SERVER_APPLY_ALLOWED is False


# ── 3. 화면 설계 Matrix ───────────────────────────────────────────────────────

def test_screen_matrix_8_screens(design):
    assert len(design.SCREEN_DESIGN_MATRIX) >= 8


def test_screen_dashboard_design_exists(design):
    assert any(s["id"] == "dashboard" for s in design.SCREEN_DESIGN_MATRIX)


def test_screen_task_queue_design_exists(design):
    assert any(s["id"] == "task_queue" for s in design.SCREEN_DESIGN_MATRIX)


def test_screen_task_detail_design_exists(design):
    assert any(s["id"] == "task_detail" for s in design.SCREEN_DESIGN_MATRIX)


def test_screen_approval_gate_design_exists(design):
    assert any(s["id"] == "approval_gate" for s in design.SCREEN_DESIGN_MATRIX)


def test_screen_external_sites_design_exists(design):
    assert any(s["id"] == "external_sites" for s in design.SCREEN_DESIGN_MATRIX)


def test_screen_logs_audit_design_exists(design):
    assert any(s["id"] == "logs_audit" for s in design.SCREEN_DESIGN_MATRIX)


def test_screen_storage_status_design_exists(design):
    assert any(s["id"] == "storage_status" for s in design.SCREEN_DESIGN_MATRIX)


def test_screen_deployment_status_design_exists(design):
    assert any(s["id"] == "deployment_status" for s in design.SCREEN_DESIGN_MATRIX)


# ── 4. 컴포넌트 설계 Matrix ───────────────────────────────────────────────────

def test_component_matrix_at_least_10(design):
    assert len(design.COMPONENT_DESIGN_MATRIX) >= 10


def _component(design, comp_id: str) -> dict | None:
    return next((c for c in design.COMPONENT_DESIGN_MATRIX if c["id"] == comp_id), None)


def test_component_status_badge_exists(design):
    assert _component(design, "StatusBadge") is not None


def test_component_risk_badge_exists(design):
    assert _component(design, "RiskBadge") is not None


def test_component_provider_card_exists(design):
    assert _component(design, "ProviderCard") is not None


def test_component_task_table_exists(design):
    assert _component(design, "TaskTable") is not None


def test_component_task_detail_panel_exists(design):
    assert _component(design, "TaskDetailPanel") is not None


def test_component_audit_log_list_exists(design):
    assert _component(design, "AuditLogList") is not None


def test_component_dry_run_notice_exists(design):
    assert _component(design, "DryRunNotice") is not None


# ── 5. 상태 모델 ──────────────────────────────────────────────────────────────

def test_state_model_task_status(design):
    assert "TaskStatus" in design.STATE_MODEL_MATRIX
    assert "DRY_RUN" in design.STATE_MODEL_MATRIX["TaskStatus"]
    assert "BLOCKED" in design.STATE_MODEL_MATRIX["TaskStatus"]


def test_state_model_action_risk(design):
    assert "ActionRisk" in design.STATE_MODEL_MATRIX
    assert "CRITICAL" in design.STATE_MODEL_MATRIX["ActionRisk"]


def test_state_model_provider_status(design):
    assert "ProviderStatus" in design.STATE_MODEL_MATRIX


def test_state_model_gate_state(design):
    assert "GateState" in design.STATE_MODEL_MATRIX
    assert "HIDDEN" in design.STATE_MODEL_MATRIX["GateState"]


def test_state_model_backend_health(design):
    assert "BackendHealth" in design.STATE_MODEL_MATRIX


def test_state_model_storage_persistence(design):
    assert "StoragePersistence" in design.STATE_MODEL_MATRIX
    assert "DISPOSABLE" in design.STATE_MODEL_MATRIX["StoragePersistence"]


def test_state_model_deployment_state(design):
    assert "DeploymentState" in design.STATE_MODEL_MATRIX
    assert "BUILD_REQUIRED" in design.STATE_MODEL_MATRIX["DeploymentState"]


# ── 6. API 연결 정책 ──────────────────────────────────────────────────────────

def _api(design, endpoint: str) -> dict | None:
    return next((a for a in design.API_CONNECTION_POLICY_MATRIX if a["endpoint"] == endpoint), None)


def test_api_health_connect_now(design):
    a = _api(design, "GET /api/v1/health")
    assert a is not None
    assert a["policy"] == "CONNECT_NOW"


def test_api_post_tasks_dry_run_only_or_mock(design):
    a = _api(design, "POST /api/v1/tasks")
    assert a is not None
    assert a["policy"] in ("DRY_RUN_ONLY", "MOCK_ONLY")


def test_api_approve_blocked_or_display_only(design):
    a = _api(design, "POST /api/v1/tasks/{id}/approve")
    assert a is not None
    assert a["policy"] in ("BLOCKED", "DISPLAY_ONLY")


def test_api_reject_blocked_or_display_only(design):
    a = _api(design, "POST /api/v1/tasks/{id}/reject")
    assert a is not None
    assert a["policy"] in ("BLOCKED", "DISPLAY_ONLY")


def test_api_execute_blocked(design):
    blocked = [a for a in design.API_CONNECTION_POLICY_MATRIX
               if "execute" in a["endpoint"] and a["policy"] == "BLOCKED"]
    assert len(blocked) > 0


# ── 7. 금지 버튼 정책 ─────────────────────────────────────────────────────────

def _forbidden(design, action_id: str) -> dict | None:
    return next((a for a in design.FORBIDDEN_ACTION_MATRIX if a["action_id"] == action_id), None)


def test_forbidden_execute_defined(design):
    assert _forbidden(design, "execute") is not None


def test_forbidden_approve_execute_defined(design):
    assert _forbidden(design, "approve_execute") is not None


def test_forbidden_dry_run_disable_defined(design):
    assert _forbidden(design, "dry_run_disable") is not None


def test_forbidden_dns_save_defined(design):
    assert _forbidden(design, "dns_save") is not None


def test_forbidden_payment_defined(design):
    assert _forbidden(design, "payment") is not None


def test_forbidden_server_restart_defined(design):
    assert _forbidden(design, "server_restart") is not None


def test_forbidden_docker_compose_action_defined(design):
    assert _forbidden(design, "docker_compose_action") is not None


def test_all_forbidden_actions_auto_execute_false(design):
    bad = [a for a in design.FORBIDDEN_ACTION_MATRIX if a.get("auto_execute_allowed") is not False]
    assert design.FORBIDDEN_ACTION_MATRIX, "design.FORBIDDEN_ACTION_MATRIX 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not bad, f"auto_execute_allowed=True: {[a['action_id'] for a in bad]}"


# ── 8. Known Backlog 매핑 ─────────────────────────────────────────────────────

def _backlog(design, item_id: str) -> dict | None:
    return next((b for b in design.KNOWN_BACKLOG_MAPPING if b["id"] == item_id), None)


def test_known_backlog_b1_reflected(design):
    b = _backlog(design, "B-1")
    assert b is not None
    assert "approve" in b["design_impact"].lower() or "execute" in b["design_impact"].lower()


def test_known_backlog_b2_reflected(design):
    b = _backlog(design, "B-2")
    assert b is not None
    assert "DRY_RUN" in b["title"]


def test_known_backlog_b3_reflected(design):
    b = _backlog(design, "B-3")
    assert b is not None
    assert "token" in b["design_impact"].lower() or "approval" in b["title"].lower()


def test_known_backlog_kw1_reflected(design):
    b = _backlog(design, "KW-1")
    assert b is not None
    assert "RUNTIME_CACHE" in b["design_impact"] or "runtime" in b["design_impact"].lower()


def test_known_backlog_kw4_reflected(design):
    b = _backlog(design, "KW-4")
    assert b is not None
    assert "docker" in b["title"].lower() or "compose" in b["title"].lower()


def test_known_backlog_external_cad_deselect_noted(design):
    b = _backlog(design, "EXT-CAD")
    assert b is not None
    assert "별도" in b["design_impact"] or "deselect" in b["design_impact"].lower()


# ── 9. Verdict ────────────────────────────────────────────────────────────────

def test_audit_verdict_ready_or_warn(design, audit_report):
    assert audit_report.verdict in (design.VERDICT_READY, design.VERDICT_WARN), \
        f"verdict={audit_report.verdict}"


# ── 10. MVP Prep 충돌 없음 ────────────────────────────────────────────────────

def test_no_conflict_with_mvp_prep(design):
    prep = __import__("tools.audits.app.audit_app_foundation_mvp_prep",
                      fromlist=["MVP_SCREENS"])
    prep_screen_ids = {s["id"] for s in prep.MVP_SCREENS}
    design_screen_ids = {s["id"] for s in design.SCREEN_DESIGN_MATRIX}
    assert prep_screen_ids == design_screen_ids, \
        f"prep/design 화면 ID 불일치: prep={prep_screen_ids} design={design_screen_ids}"
