"""5050 Flask legacy route characterization 테스트.

ASSISTANT_BACKEND_5050_LEGACY_CHARACTERIZATION_TEST_01

금지:
    5050 프로세스 중단 금지 / 실제 webhook POST 금지
    실제 task execute 금지 / 실제 approve/reject 금지
    실제 inbox fetch/classify 실행 금지 / secret 출력 금지
    skip/xfail 금지 / 테스트 삭제 금지
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT_SCRIPT = ROOT / "scripts" / "ops" / "audit_5050_legacy_characterization.py"


def _load_audit():
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_5050_legacy_characterization", AUDIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audit():
    return _load_audit().run_audit()


# ---------------------------------------------------------------------------
# 1. route matrix에 DASHBOARD_UI 카테고리 포함
# ---------------------------------------------------------------------------

def test_route_matrix_has_dashboard_category():
    audit = _audit()
    cats = {r["category"] for r in audit["route_matrix"]}
    assert "DASHBOARD_UI" in cats


def test_dashboard_routes_count():
    audit = _audit()
    dashboard = [r for r in audit["route_matrix"] if r["category"] == "DASHBOARD_UI"]
    assert len(dashboard) >= 4


def test_dashboard_paths_defined():
    audit = _audit()
    paths = [r["path"] for r in audit["route_matrix"] if r["category"] == "DASHBOARD_UI"]
    assert any("/dashboard" == p for p in paths)
    assert any("/dashboard/tasks" in p for p in paths)
    assert any("/dashboard/approve" in p for p in paths)
    assert any("/dashboard/reject" in p for p in paths)


# ---------------------------------------------------------------------------
# 2. route matrix에 WEBHOOK_LEGACY 카테고리 포함
# ---------------------------------------------------------------------------

def test_route_matrix_has_webhook_category():
    audit = _audit()
    cats = {r["category"] for r in audit["route_matrix"]}
    assert "WEBHOOK_LEGACY" in cats


def test_webhook_routes_count():
    audit = _audit()
    webhooks = [r for r in audit["route_matrix"] if r["category"] == "WEBHOOK_LEGACY"]
    assert len(webhooks) >= 2


# ---------------------------------------------------------------------------
# 3. route matrix에 INBOX_LEGACY 카테고리 포함
# ---------------------------------------------------------------------------

def test_route_matrix_has_inbox_category():
    audit = _audit()
    cats = {r["category"] for r in audit["route_matrix"]}
    assert "INBOX_LEGACY" in cats


def test_inbox_routes_count():
    audit = _audit()
    inbox = [r for r in audit["route_matrix"] if r["category"] == "INBOX_LEGACY"]
    assert len(inbox) >= 5


def test_inbox_paths_include_fetch_and_classify():
    audit = _audit()
    paths = [r["path"] for r in audit["route_matrix"] if r["category"] == "INBOX_LEGACY"]
    assert any("fetch" in p for p in paths)
    assert any("classify" in p for p in paths)
    assert any("candidates" in p for p in paths)


# ---------------------------------------------------------------------------
# 4. route matrix에 TASK_LEGACY 카테고리 포함
# ---------------------------------------------------------------------------

def test_route_matrix_has_task_category():
    audit = _audit()
    cats = {r["category"] for r in audit["route_matrix"]}
    assert "TASK_LEGACY" in cats


def test_task_routes_count():
    audit = _audit()
    tasks = [r for r in audit["route_matrix"] if r["category"] == "TASK_LEGACY"]
    assert len(tasks) >= 5


# ---------------------------------------------------------------------------
# 5. kakaowork/kakaotalk은 DO_NOT_TOUCH
# ---------------------------------------------------------------------------

def test_kakaowork_is_do_not_touch():
    mod = _load_audit()
    kakaowork = next((r for r in mod.ROUTE_MATRIX if "kakaowork" in r["path"]), None)
    assert kakaowork is not None
    assert kakaowork["migration_class"] == mod.MC_DO_NOT_TOUCH


def test_kakaotalk_is_do_not_touch():
    mod = _load_audit()
    kakaotalk = next((r for r in mod.ROUTE_MATRIX if "kakaotalk" in r["path"]), None)
    assert kakaotalk is not None
    assert kakaotalk["migration_class"] == mod.MC_DO_NOT_TOUCH


def test_do_not_touch_routes_in_audit():
    audit = _audit()
    assert len(audit["do_not_touch_routes"]) >= 2
    combined = " ".join(audit["do_not_touch_routes"])
    assert "kakaowork" in combined
    assert "kakaotalk" in combined


def test_webhook_do_not_touch_no_fastapi_overlap():
    mod = _load_audit()
    for r in mod.ROUTE_MATRIX:
        if r["migration_class"] == mod.MC_DO_NOT_TOUCH:
            assert r.get("fastapi_overlap") is False


# ---------------------------------------------------------------------------
# 6. tasks execute는 HOLD_DANGEROUS
# ---------------------------------------------------------------------------

def test_execute_is_hold_dangerous():
    mod = _load_audit()
    execute = next((r for r in mod.ROUTE_MATRIX if "execute" in r["path"]), None)
    assert execute is not None
    assert execute["migration_class"] == mod.MC_HOLD_DANGEROUS


def test_execute_risk_level_critical():
    mod = _load_audit()
    execute = next((r for r in mod.ROUTE_MATRIX if "execute" in r["path"]), None)
    assert execute["risk_level"] == "CRITICAL"


def test_execute_side_effect_false():
    mod = _load_audit()
    execute = next((r for r in mod.ROUTE_MATRIX if "execute" in r["path"]), None)
    assert execute["side_effect_allowed"] is False


def test_execute_in_dangerous_routes():
    audit = _audit()
    assert any("execute" in p for p in audit["dangerous_routes"])


# ---------------------------------------------------------------------------
# 7. dashboard routes는 auth 보호 확인
# ---------------------------------------------------------------------------

def test_dashboard_routes_auth_expected():
    mod = _load_audit()
    dashboard = [r for r in mod.ROUTE_MATRIX if r["category"] == "DASHBOARD_UI"]
    for r in dashboard:
        assert r["auth_expected"] is True, f"{r['path']} auth_expected should be True"


def test_dashboard_unauthenticated_status_not_200():
    mod = _load_audit()
    dashboard = [r for r in mod.ROUTE_MATRIX if r["category"] == "DASHBOARD_UI"]
    for r in dashboard:
        status = r["expected_status_without_auth"]
        assert "200" not in status, f"{r['path']} should not return 200 without auth"


def test_dashboard_migration_class_hold():
    mod = _load_audit()
    dashboard = [r for r in mod.ROUTE_MATRIX if r["category"] == "DASHBOARD_UI"]
    for r in dashboard:
        assert r["migration_class"] == mod.MC_HOLD


# ---------------------------------------------------------------------------
# 8. inbox classify/candidates는 LEGACY_ONLY_NEEDS_REVIEW
# ---------------------------------------------------------------------------

def test_inbox_classify_is_legacy_review():
    mod = _load_audit()
    classify_routes = [r for r in mod.ROUTE_MATRIX
                       if r["category"] == "INBOX_LEGACY" and "classify" in r["path"]]
    assert len(classify_routes) >= 1
    for r in classify_routes:
        assert r["migration_class"] == mod.MC_LEGACY_REVIEW


def test_inbox_candidates_is_legacy_review():
    mod = _load_audit()
    cand = next(
        (r for r in mod.ROUTE_MATRIX
         if r["category"] == "INBOX_LEGACY" and r["path"] == "/api/v1/inbox/candidates"),
        None
    )
    assert cand is not None
    assert cand["migration_class"] == mod.MC_LEGACY_REVIEW


# ---------------------------------------------------------------------------
# 9. 8400 overlap matrix에 5개 route 포함
# ---------------------------------------------------------------------------

def test_overlap_matrix_count():
    mod = _load_audit()
    assert len(mod.OVERLAP_MATRIX) >= 5


def test_overlap_matrix_paths():
    mod = _load_audit()
    paths = [o["5050_path"] for o in mod.OVERLAP_MATRIX]
    assert any("/api/v1/inbox" in p for p in paths)
    assert any("/api/v1/tasks" in p for p in paths)
    assert any("approve" in p for p in paths)
    assert any("reject" in p for p in paths)


def test_overlap_matrix_in_audit():
    audit = _audit()
    assert len(audit["overlap_matrix"]) >= 5


# ---------------------------------------------------------------------------
# 10. route characterization은 side_effect를 허용하지 않음
# ---------------------------------------------------------------------------

def test_no_route_allows_side_effect():
    mod = _load_audit()
    for r in mod.ROUTE_MATRIX:
        assert r["side_effect_allowed"] is False, f"{r['path']} side_effect_allowed must be False"


def test_safe_boundary_no_side_effect():
    mod = _load_audit()
    assert mod.SAFE_BOUNDARY["side_effect_execution"] is False


# ---------------------------------------------------------------------------
# 11. webhook 실제 호출 없음
# ---------------------------------------------------------------------------

def test_no_actual_webhook_call():
    mod = _load_audit()
    assert mod.SAFE_BOUNDARY["actual_webhook_call"] is False


def test_webhook_test_strategy_no_call():
    mod = _load_audit()
    for r in mod.ROUTE_MATRIX:
        if r["category"] == "WEBHOOK_LEGACY":
            assert "금지" in r["test_strategy"] or "실제 호출 금지" in r.get("test_strategy", "")


# ---------------------------------------------------------------------------
# 12. task execute 호출 없음
# ---------------------------------------------------------------------------

def test_no_actual_task_execute():
    mod = _load_audit()
    assert mod.SAFE_BOUNDARY["actual_task_execute"] is False


def test_execute_test_strategy_forbidden():
    mod = _load_audit()
    execute = next((r for r in mod.ROUTE_MATRIX if "execute" in r["path"]), None)
    assert "금지" in execute["test_strategy"] or "HOLD" in execute["test_strategy"]


# ---------------------------------------------------------------------------
# 13. 5050 do-not-stop 조건
# ---------------------------------------------------------------------------

def test_all_routes_have_do_not_stop():
    mod = _load_audit()
    for r in mod.ROUTE_MATRIX:
        assert r.get("do_not_stop_5050") is True, f"{r['path']} do_not_stop_5050 must be True"


def test_5050_do_not_stop_in_audit_checks():
    audit = _audit()
    assert audit["checks"]["5050_do_not_stop_all_routes"] is True


def test_5050_in_safe_boundary():
    mod = _load_audit()
    assert mod.SAFE_BOUNDARY["5050_stop"] is False


# ---------------------------------------------------------------------------
# 14. nginx unchanged 조건
# ---------------------------------------------------------------------------

def test_all_routes_nginx_unchanged():
    mod = _load_audit()
    for r in mod.ROUTE_MATRIX:
        assert r.get("nginx_unchanged") is True, f"{r['path']} nginx_unchanged must be True"


def test_nginx_unchanged_in_audit_checks():
    audit = _audit()
    assert audit["checks"]["nginx_unchanged_all_routes"] is True


def test_nginx_change_in_safe_boundary():
    mod = _load_audit()
    assert mod.SAFE_BOUNDARY["nginx_change"] is False


# ---------------------------------------------------------------------------
# 15. UI 파일 변경 없음
# ---------------------------------------------------------------------------

def test_no_ui_change():
    mod = _load_audit()
    assert mod.SAFE_BOUNDARY["actual_ui_change"] is False


def test_no_ui_change_in_audit():
    audit = _audit()
    assert audit["checks"]["no_ui_change"] is True


# ---------------------------------------------------------------------------
# 16. quality gate (audit 전체 PASS)
# ---------------------------------------------------------------------------

def test_audit_all_ok():
    audit = _audit()
    assert audit["all_ok"] is True, f"audit 실패: {audit['checks']}"


def test_audit_verdict_ready():
    audit = _audit()
    assert "READY" in audit["verdict"]


def test_audit_boundary_no_violations():
    audit = _audit()
    assert audit["safe_boundary"]["violations"] == []


def test_checklist_completeness():
    audit = _audit()
    assert len(audit["checks"].items()) > 0, "checks 가 비어 있음 — 아래 assert 가 공허하게 통과한다"
    failed = [k for k, v in audit["checks"].items() if not v]
    assert failed == [], f"checklist 실패: {failed}"


def test_total_routes_sufficient():
    audit = _audit()
    assert len(audit["route_matrix"]) >= 15


def test_next_migration_steps_exist():
    audit = _audit()
    steps = audit["next_migration_steps"]
    assert len(steps) >= 5
    phases = [s["phase"] for s in steps]
    assert 1 in phases
    assert "HOLD_DANGEROUS" in phases
    assert "DO_NOT_TOUCH" in phases


def test_approval_request_characterization_needed():
    mod = _load_audit()
    approval_req = next(
        (r for r in mod.ROUTE_MATRIX if "approval-request" in r["path"]),
        None
    )
    assert approval_req is not None
    assert approval_req["migration_class"] == mod.MC_CHAR_NEEDED


def test_task_approval_get_characterization_needed():
    mod = _load_audit()
    approval_get = next(
        (r for r in mod.ROUTE_MATRIX
         if r["path"].endswith("/approval") and r["method"] == ["GET"]),
        None
    )
    assert approval_get is not None
    assert approval_get["migration_class"] == mod.MC_CHAR_NEEDED
