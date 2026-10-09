"""APP_FOUNDATION_MVP_PREP_01 테스트.

비서앱 1차 MVP 설계가 백엔드 Phase1 기준선 및 보안 정책과
충돌하지 않는지 검증한다. 구현 파일 수정 없음 — 설계/감리 전용.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ── 공통 fixture ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mvp():
    import tools.audits.app.audit_app_foundation_mvp_prep as m
    return m


@pytest.fixture(scope="module")
def audit_report(mvp):
    return mvp.run_audit()


# ── 1. 스크립트 import ────────────────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_foundation_mvp_prep  # noqa: F401


# ── 2. MVP 화면 목록 ──────────────────────────────────────────────────────────

def test_mvp_screens_count_at_least_8(mvp):
    assert len(mvp.MVP_SCREENS) >= 8


def test_mvp_screen_dashboard_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "dashboard" in ids


def test_mvp_screen_task_queue_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "task_queue" in ids


def test_mvp_screen_task_detail_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "task_detail" in ids


def test_mvp_screen_approval_gate_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "approval_gate" in ids


def test_mvp_screen_external_sites_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "external_sites" in ids


def test_mvp_screen_logs_audit_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "logs_audit" in ids


def test_mvp_screen_storage_status_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "storage_status" in ids


def test_mvp_screen_deployment_status_exists(mvp):
    ids = {s["id"] for s in mvp.MVP_SCREENS}
    assert "deployment_status" in ids


# ── 3. API Contract Matrix ────────────────────────────────────────────────────

def test_post_tasks_dry_run_only(mvp):
    ep = next((a for a in mvp.API_CONTRACT if a["endpoint"] == "POST /api/v1/tasks"), None)
    assert ep is not None
    assert ep["classification"] == "DRY_RUN_ALLOWED"


def test_approve_reject_display_only_or_blocked(mvp):
    for endpoint in ["POST /api/v1/tasks/{id}/approve", "POST /api/v1/tasks/{id}/reject"]:
        ep = next((a for a in mvp.API_CONTRACT if a["endpoint"] == endpoint), None)
        assert ep is not None, f"{endpoint} 미정의"
        assert ep["classification"] in ("APPROVAL_DISPLAY_ONLY", "BLOCKED"), \
            f"{endpoint} = {ep['classification']} (expected APPROVAL_DISPLAY_ONLY or BLOCKED)"


def test_execute_api_blocked(mvp):
    blocked = [a for a in mvp.API_CONTRACT
               if "execute" in a["endpoint"] and a["classification"] == "BLOCKED"]
    assert len(blocked) > 0, "execute endpoint BLOCKED 미정의"


# ── 4. 금지 버튼 목록 ─────────────────────────────────────────────────────────

def _all_forbidden(mvp) -> set:
    result = set()
    for s in mvp.MVP_SCREENS:
        result.update(s.get("forbidden_buttons", []))
    return result


def test_dry_run_disable_button_forbidden(mvp):
    assert "dry_run_disable" in _all_forbidden(mvp)


def test_approve_execute_button_forbidden(mvp):
    assert "approve_execute" in _all_forbidden(mvp)


def test_dns_save_button_forbidden(mvp):
    assert "dns_save" in _all_forbidden(mvp)


def test_payment_button_forbidden(mvp):
    assert "payment" in _all_forbidden(mvp)


def test_final_submit_button_forbidden(mvp):
    assert "final_submit" in _all_forbidden(mvp)


def test_server_restart_button_forbidden(mvp):
    assert "restart_server" in _all_forbidden(mvp)


def test_docker_compose_action_button_forbidden(mvp):
    assert "docker_compose_action" in _all_forbidden(mvp)


def test_execute_button_forbidden(mvp):
    assert "execute" in _all_forbidden(mvp)


# ── 5. Approval Gate Matrix ───────────────────────────────────────────────────

def _gate(mvp, gate_id: str) -> dict | None:
    return next((g for g in mvp.APPROVAL_GATE_MATRIX if g["gate_id"] == gate_id), None)


def test_approval_gate_matrix_exists(mvp):
    assert len(mvp.APPROVAL_GATE_MATRIX) > 0


def test_post_tasks_dry_run_disable_gate_exists(mvp):
    assert _gate(mvp, "POST_TASKS_DRY_RUN_DISABLE") is not None


def test_approve_execute_connect_gate_exists(mvp):
    assert _gate(mvp, "APPROVE_EXECUTE_CONNECT") is not None


def test_server_restart_gate_exists(mvp):
    assert _gate(mvp, "SERVER_RESTART") is not None


def test_docker_compose_action_gate_exists(mvp):
    assert _gate(mvp, "DOCKER_COMPOSE_ACTION") is not None


def test_all_gates_auto_execute_false(mvp):
    bad = [g for g in mvp.APPROVAL_GATE_MATRIX if g.get("auto_execute_allowed") is not False]
    assert mvp.APPROVAL_GATE_MATRIX, "mvp.APPROVAL_GATE_MATRIX 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not bad, f"auto_execute_allowed=True gate: {[g['gate_id'] for g in bad]}"


def test_post_tasks_dry_run_disable_hidden(mvp):
    g = _gate(mvp, "POST_TASKS_DRY_RUN_DISABLE")
    assert g["mvp_button_state"] in ("hidden", "disabled")


def test_approve_execute_connect_hidden(mvp):
    g = _gate(mvp, "APPROVE_EXECUTE_CONNECT")
    assert g["mvp_button_state"] in ("hidden", "disabled")


def test_server_restart_hidden(mvp):
    g = _gate(mvp, "SERVER_RESTART")
    assert g["mvp_button_state"] == "hidden"


def test_docker_compose_action_hidden(mvp):
    g = _gate(mvp, "DOCKER_COMPOSE_ACTION")
    assert g["mvp_button_state"] == "hidden"


# ── 6. Provider Registry ──────────────────────────────────────────────────────

def test_providers_12_reflected(mvp):
    assert len(mvp.PROVIDERS) == 12


def test_gabia_user_present_login_required(mvp):
    p = next((x for x in mvp.PROVIDERS if x["id"] == "GABIA"), None)
    assert p is not None
    assert p["user_present_required"] is True


def test_naver_smartstore_critical(mvp):
    p = next((x for x in mvp.PROVIDERS if x["id"] == "NAVER_SMARTSTORE"), None)
    assert p is not None
    assert p.get("risk_level") == "critical"


def test_g2b_nara_certificate_required(mvp):
    p = next((x for x in mvp.PROVIDERS if x["id"] == "G2B_NARA"), None)
    assert p is not None
    assert p.get("certificate_required") is True


def test_cookie_storage_forbidden_all_providers(mvp):
    bad = [p for p in mvp.PROVIDERS if not p.get("cookie_storage_forbidden")]
    assert mvp.PROVIDERS, "mvp.PROVIDERS 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not bad, f"cookie_storage_forbidden 미설정 provider: {[p['id'] for p in bad]}"


def test_token_raw_display_forbidden(mvp):
    logs_screen = next((s for s in mvp.MVP_SCREENS if s["id"] == "logs_audit"), None)
    assert logs_screen is not None
    assert "export_raw_token" in logs_screen.get("forbidden_buttons", [])


# ── 7. Known Backlog ──────────────────────────────────────────────────────────

def _backlog(mvp, item_id: str) -> dict | None:
    return next((b for b in mvp.KNOWN_BACKLOG if b["id"] == item_id), None)


def test_backlog_b1_approve_execute_not_connected(mvp):
    item = _backlog(mvp, "B-1")
    assert item is not None
    assert "실행 버튼 없음" in item["app_behavior"] or "execute" in item["app_behavior"].lower()


def test_backlog_b2_dry_run_not_disabled(mvp):
    item = _backlog(mvp, "B-2")
    assert item is not None
    assert "DRY_RUN" in item["title"]


def test_backlog_b3_approval_tokens_audit_pending(mvp):
    item = _backlog(mvp, "B-3")
    assert item is not None
    assert item["status"] == "audit_pending"


def test_backlog_kw1_chrome_monitor_state(mvp):
    item = _backlog(mvp, "KW-1")
    assert item is not None
    assert "runtime" in item["status"]


def test_backlog_kw4_docker_compose_version(mvp):
    item = _backlog(mvp, "KW-4")
    assert item is not None
    assert "docker" in item["title"].lower() or "compose" in item["title"].lower()


def test_backlog_external_cad_deselect_noted(mvp):
    item = _backlog(mvp, "EXT-CAD")
    assert item is not None
    assert "deselect" in item["status"] or "별도" in item["app_behavior"]


# ── 8. Storage 상태 ───────────────────────────────────────────────────────────

def test_storage_named_volume_defined(mvp):
    assert "named_volume" in mvp.STORAGE_MATRIX
    assert mvp.STORAGE_MATRIX["named_volume"]["path"] == "/app/ai_orchestrator/storage"


def test_app_logs_bind_mount_applied(mvp):
    bind = mvp.STORAGE_MATRIX.get("bind_mount_logs", {})
    assert bind.get("bind_mount_applied") is True


# ── 9. Deployment SOP ─────────────────────────────────────────────────────────

def test_deployment_sop_defined(mvp):
    assert len(mvp.DEPLOYMENT_SOP.get("steps", [])) >= 3


def test_deployment_restart_only_forbidden(mvp):
    assert mvp.DEPLOYMENT_SOP.get("restart_only_forbidden") is True


# ── 10. Pytest Baseline 반영 ──────────────────────────────────────────────────

def test_pytest_baseline_zero_failed_reflected(mvp):
    assert mvp.PYTEST_BASELINE["total_failed"] == 0


def test_pytest_baseline_tag_test_baseline_cleaned(mvp):
    assert mvp.PYTEST_BASELINE.get("baseline_tag") == "TEST_BASELINE_CLEANED"


# ── 11. Verdict ───────────────────────────────────────────────────────────────

def test_audit_verdict_ready_or_warn(audit_report):
    import tools.audits.app.audit_app_foundation_mvp_prep as m
    assert audit_report.verdict in (m.VERDICT_READY, m.VERDICT_WARN), \
        f"verdict = {audit_report.verdict} (expected READY or WITH_WARN)"


# ── 12. Backend Phase1 Closeout 충돌 없음 ─────────────────────────────────────

def test_no_conflict_with_backend_closeout():
    closeout_path = ROOT / "data" / "backend_operation_final_closeout_audit_latest.json"
    if not closeout_path.exists():
        pytest.skip("closeout audit JSON 없음 — 실행 후 재검증")
    d = json.loads(closeout_path.read_text(encoding="utf-8"))
    assert d.get("app_ready") is True, f"backend closeout app_ready=False: {d.get('verdict')}"


def test_dry_run_gate_active():
    import ai_orchestrator.routers.registry as router_mod
    assert getattr(router_mod, "POST_TASKS_DRY_RUN_ENABLED", False) is True
