"""5050 Phase 1-E — adapter implementation plan 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1E_ADAPTER_IMPLEMENTATION_PLAN_01

실제 구현 없이 정적 implementation plan만 검증한다.

금지:
    실제 HTTP 호출 금지 / email fetch 실행 금지 / approve/reject 실행 금지
    execute 호출 금지 / webhook 호출 금지 / DB write 금지
    5050 중단 금지 / nginx 변경 금지 / secret 출력 금지
    adapter 실제 구현 금지 / route handler 변경 금지
    skip/xfail 금지 / 테스트 삭제 금지
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT_SCRIPT = ROOT / "scripts" / "ops" / "audit_5050_phase1e_adapter_implementation_plan.py"

# known baseline failures — 이번 공정과 무관 (문서성 상수)
KNOWN_BASELINE_FAILURES = [
    "tests/test_app_foundation_p1_gates.py::test_server_browser_guard_no_violations",
    "tests/test_app_foundation_p1_gates.py::test_p1_gates_all_zero_new_violations",
    "tests/test_cad_local_agent_adapter_20260509.py::test_cad_status_lists_physical_modules",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_cad_adapter_status_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_bridge_health_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_fastmcp_call_tool_invokes_local_cad_bridge_health",
]


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1e_adapter_implementation_plan", AUDIT_SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audit():
    return _load().run_audit()


# ---------------------------------------------------------------------------
# 1. Phase 1-E implementation plan이 정확히 3개
# ---------------------------------------------------------------------------

def test_phase1e_plans_exactly_3():
    mod = _load()
    assert len(mod.PHASE1E_IMPLEMENTATION_PLANS) == 3


def test_audit_total_plans_3():
    audit = _audit()
    assert audit["summary"]["total_plans"] == 3


# ---------------------------------------------------------------------------
# 2. 대상 adapter가 정확히 3개
# ---------------------------------------------------------------------------

def test_includes_inbox_email_fetch_adapter():
    mod = _load()
    r = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
               if p["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert r is not None


def test_includes_task_approve_adapter():
    mod = _load()
    r = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
               if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert r is not None


def test_includes_task_reject_adapter():
    mod = _load()
    r = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
               if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert r is not None


# ---------------------------------------------------------------------------
# 3. 모든 plan이 implementation_allowed=False
# ---------------------------------------------------------------------------

def test_all_implementation_allowed_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["implementation_allowed"] is False, (
            f"{p['adapter_id']} implementation_allowed must be False"
        )


def test_audit_implementation_allowed_false_3():
    audit = _audit()
    assert audit["summary"]["implementation_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 4. 모든 plan이 live_call_allowed=False
# ---------------------------------------------------------------------------

def test_all_live_call_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["live_call_allowed"] is False, (
            f"{p['adapter_id']} live_call_allowed must be False"
        )


def test_audit_live_call_false_3():
    audit = _audit()
    assert audit["summary"]["live_call_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 5. 모든 plan이 side_effect_allowed=False
# ---------------------------------------------------------------------------

def test_all_side_effect_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["side_effect_allowed"] is False, (
            f"{p['adapter_id']} side_effect_allowed must be False"
        )


def test_audit_side_effect_false_3():
    audit = _audit()
    assert audit["summary"]["side_effect_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 6. 모든 plan이 db_write_allowed=False
# ---------------------------------------------------------------------------

def test_all_db_write_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["db_write_allowed"] is False, (
            f"{p['adapter_id']} db_write_allowed must be False"
        )


def test_audit_db_write_false_3():
    audit = _audit()
    assert audit["summary"]["db_write_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 7. 모든 plan이 secret_value_allowed=False
# ---------------------------------------------------------------------------

def test_all_secret_value_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["secret_value_allowed"] is False, (
            f"{p['adapter_id']} secret_value_allowed must be False"
        )


def test_audit_secret_false_3():
    audit = _audit()
    assert audit["summary"]["secret_value_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 8. 모든 plan이 server_apply_allowed=False
# ---------------------------------------------------------------------------

def test_all_server_apply_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["server_apply_allowed"] is False, (
            f"{p['adapter_id']} server_apply_allowed must be False"
        )


def test_audit_server_apply_false_3():
    audit = _audit()
    assert audit["summary"]["server_apply_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 9. 모든 plan이 route_handler_change_allowed=False
# ---------------------------------------------------------------------------

def test_all_route_handler_change_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["route_handler_change_allowed"] is False, (
            f"{p['adapter_id']} route_handler_change_allowed must be False"
        )


def test_audit_route_handler_false_3():
    audit = _audit()
    assert audit["summary"]["route_handler_change_false"] == 3


# ---------------------------------------------------------------------------
# 10. 모든 plan이 nginx_change_allowed=False
# ---------------------------------------------------------------------------

def test_all_nginx_change_false():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["nginx_change_allowed"] is False, (
            f"{p['adapter_id']} nginx_change_allowed must be False"
        )


def test_audit_nginx_false_3():
    audit = _audit()
    assert audit["summary"]["nginx_change_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 11. 모든 plan이 rollback_required=True
# ---------------------------------------------------------------------------

def test_all_rollback_required_true():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["rollback_required"] is True, (
            f"{p['adapter_id']} rollback_required must be True"
        )


def test_audit_rollback_required_3():
    audit = _audit()
    assert audit["summary"]["rollback_required_true"] == 3


# ---------------------------------------------------------------------------
# 12. approve/reject만 approval_gate_required=True
# ---------------------------------------------------------------------------

def test_approve_approval_gate_true():
    mod = _load()
    approve = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["approval_gate_required"] is True


def test_reject_approval_gate_true():
    mod = _load()
    reject = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["approval_gate_required"] is True


def test_audit_gate_true_2():
    audit = _audit()
    assert audit["summary"]["approval_gate_required_true"] == 2


# ---------------------------------------------------------------------------
# 13. email/fetch는 approval_gate_required=False
# ---------------------------------------------------------------------------

def test_fetch_approval_gate_false():
    mod = _load()
    fetch = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert fetch["approval_gate_required"] is False


# ---------------------------------------------------------------------------
# 14. approve/reject risk_level=HIGH
# ---------------------------------------------------------------------------

def test_approve_risk_high():
    mod = _load()
    approve = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["risk_level"] == "HIGH"


def test_reject_risk_high():
    mod = _load()
    reject = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["risk_level"] == "HIGH"


def test_audit_high_risk_2():
    audit = _audit()
    assert audit["summary"]["risk_level_HIGH"] == 2


# ---------------------------------------------------------------------------
# 15. email/fetch risk_level=MEDIUM
# ---------------------------------------------------------------------------

def test_fetch_risk_medium():
    mod = _load()
    fetch = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert fetch["risk_level"] == "MEDIUM"


def test_audit_medium_risk_1():
    audit = _audit()
    assert audit["summary"]["risk_level_MEDIUM"] == 1


# ---------------------------------------------------------------------------
# 16-19. path template 정확성
# ---------------------------------------------------------------------------

def test_approve_legacy_path_template():
    mod = _load()
    approve = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["legacy_path_template"] == "/api/v1/tasks/<id>/approve"


def test_approve_fastapi_path_template():
    mod = _load()
    approve = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["fastapi_path_template"] == "/api/v1/tasks/{id}/approve"


def test_reject_legacy_path_template():
    mod = _load()
    reject = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["legacy_path_template"] == "/api/v1/tasks/<id>/reject"


def test_reject_fastapi_path_template():
    mod = _load()
    reject = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["fastapi_path_template"] == "/api/v1/tasks/{id}/reject"


# ---------------------------------------------------------------------------
# 20-21. /api/v1/tasks//approve, //reject 생성 금지
# ---------------------------------------------------------------------------

def test_double_slash_approve_never_in_plans():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        for field in ("legacy_path_template", "fastapi_path_template"):
            assert p[field] != "/api/v1/tasks//approve"


def test_double_slash_reject_never_in_plans():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        for field in ("legacy_path_template", "fastapi_path_template"):
            assert p[field] != "/api/v1/tasks//reject"


def test_no_double_slash_in_any_template():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert "//" not in p["legacy_path_template"]
        assert "//" not in p["fastapi_path_template"]


def test_audit_no_double_slash():
    audit = _audit()
    assert audit["summary"]["no_double_slash"] is True


# ---------------------------------------------------------------------------
# 22-25. 제외 경로 확인
# ---------------------------------------------------------------------------

def test_execute_not_in_phase1e():
    mod = _load()
    paths = [p["legacy_path_template"] for p in mod.PHASE1E_IMPLEMENTATION_PLANS]
    assert not any("execute" in p for p in paths)


def test_webhook_not_in_phase1e():
    mod = _load()
    paths = [p["legacy_path_template"] for p in mod.PHASE1E_IMPLEMENTATION_PLANS]
    assert not any("webhook" in p for p in paths)


def test_dashboard_not_in_phase1e():
    mod = _load()
    paths = [p["legacy_path_template"] for p in mod.PHASE1E_IMPLEMENTATION_PLANS]
    assert not any("/dashboard" in p for p in paths)


def test_same_contract_not_in_phase1e():
    mod = _load()
    r_inbox = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["legacy_path_template"] == "/api/v1/inbox"
                    and p["legacy_method"] == "GET"), None)
    r_tasks = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["legacy_path_template"] == "/api/v1/tasks"
                    and p["legacy_method"] == "POST"), None)
    assert r_inbox is None
    assert r_tasks is None


# ---------------------------------------------------------------------------
# 26-28. proposed module/function/test 비어있지 않음
# ---------------------------------------------------------------------------

def test_all_proposed_adapter_module_nonempty():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["proposed_adapter_module"], (
            f"{p['adapter_id']} proposed_adapter_module must not be empty"
        )


def test_all_proposed_adapter_function_nonempty():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["proposed_adapter_function"], (
            f"{p['adapter_id']} proposed_adapter_function must not be empty"
        )


def test_all_proposed_test_module_nonempty():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["proposed_test_module"], (
            f"{p['adapter_id']} proposed_test_module must not be empty"
        )


# ---------------------------------------------------------------------------
# 29-30. required_feature_flag / required_safety_gate 3개 존재
# ---------------------------------------------------------------------------

def test_all_required_feature_flag_exist():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p.get("required_feature_flag"), (
            f"{p['adapter_id']} required_feature_flag must exist"
        )


def test_all_required_safety_gate_exist():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p.get("required_safety_gate"), (
            f"{p['adapter_id']} required_safety_gate must exist"
        )


def test_audit_feature_flag_count_3():
    audit = _audit()
    assert audit["summary"]["feature_flag_plan_count"] == 3


# ---------------------------------------------------------------------------
# 31-33. feature flag 값 정확성
# ---------------------------------------------------------------------------

def test_fetch_feature_flag():
    mod = _load()
    fetch = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert fetch["required_feature_flag"] == "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED"


def test_approve_feature_flag():
    mod = _load()
    approve = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["required_feature_flag"] == "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED"


def test_reject_feature_flag():
    mod = _load()
    reject = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["required_feature_flag"] == "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED"


# ---------------------------------------------------------------------------
# 34-35. approve/reject permission plan이 explicit gate 요구
# ---------------------------------------------------------------------------

def test_approve_permission_requires_explicit_gate():
    mod = _load()
    approve = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert "GATE" in approve["permission_mapping_plan"].upper() or \
           "gate" in approve["permission_mapping_plan"]


def test_reject_permission_requires_explicit_gate():
    mod = _load()
    reject = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert "GATE" in reject["permission_mapping_plan"].upper() or \
           "gate" in reject["permission_mapping_plan"]


# ---------------------------------------------------------------------------
# 36. auth_mapping_plan이 no bypass
# ---------------------------------------------------------------------------

def test_all_auth_mapping_no_bypass():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        plan = p.get("auth_mapping_plan", "")
        assert "bypass" not in plan.lower() or "no_bypass" in plan.lower() or \
               "NO_BYPASS" in plan or "no bypass" in plan.lower(), (
            f"{p['adapter_id']} auth_mapping_plan must not allow bypass"
        )


def test_approve_auth_no_bypass():
    mod = _load()
    approve = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                    if p["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert "NO_BYPASS" in approve["auth_mapping_plan"] or "no bypass" in approve["auth_mapping_plan"].lower()


def test_reject_auth_no_bypass():
    mod = _load()
    reject = next((p for p in mod.PHASE1E_IMPLEMENTATION_PLANS
                   if p["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert "NO_BYPASS" in reject["auth_mapping_plan"] or "no bypass" in reject["auth_mapping_plan"].lower()


# ---------------------------------------------------------------------------
# 37-38. rollback_plan / stop_conditions 3개 존재
# ---------------------------------------------------------------------------

def test_all_rollback_plan_exist():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p.get("rollback_plan"), f"{p['adapter_id']} rollback_plan must exist"


def test_all_stop_conditions_exist():
    mod = _load()
    for p in mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p.get("stop_conditions") and len(p["stop_conditions"]) > 0, (
            f"{p['adapter_id']} stop_conditions must exist"
        )


# ---------------------------------------------------------------------------
# 39-43. 구현 단계 로드맵 Phase 1-F ~ 1-J 계획 존재
# ---------------------------------------------------------------------------

def test_phase1f_plan_exists():
    mod = _load()
    f = next((ph for ph in mod.IMPLEMENTATION_PHASE_PLAN
               if ph["phase"] == "PHASE_1F"), None)
    assert f is not None
    assert "skeleton" in f["label"].lower()


def test_phase1g_plan_exists():
    mod = _load()
    g = next((ph for ph in mod.IMPLEMENTATION_PHASE_PLAN
               if ph["phase"] == "PHASE_1G"), None)
    assert g is not None
    assert "unit" in g["label"].lower()


def test_phase1h_plan_exists():
    mod = _load()
    h = next((ph for ph in mod.IMPLEMENTATION_PHASE_PLAN
               if ph["phase"] == "PHASE_1H"), None)
    assert h is not None
    assert "flag" in h["label"].lower() or "wrapper" in h["label"].lower()


def test_phase1i_plan_exists():
    mod = _load()
    i = next((ph for ph in mod.IMPLEMENTATION_PHASE_PLAN
               if ph["phase"] == "PHASE_1I"), None)
    assert i is not None
    assert "smoke" in i["label"].lower() or "staging" in i["label"].lower()


def test_phase1j_plan_exists():
    mod = _load()
    j = next((ph for ph in mod.IMPLEMENTATION_PHASE_PLAN
               if ph["phase"] == "PHASE_1J"), None)
    assert j is not None
    assert "SAME_CONTRACT" in j["label"] or "legacy" in j["label"].lower()


def test_audit_phase_plan_count_5():
    audit = _audit()
    assert audit["summary"]["phase_plan_count"] == 5


# ---------------------------------------------------------------------------
# 44. 감사 스크립트 verdict=PHASE1E_ADAPTER_IMPLEMENTATION_PLAN_READY
# ---------------------------------------------------------------------------

def test_audit_verdict_phase1e_ready():
    audit = _audit()
    assert audit["verdict"] == "PHASE1E_ADAPTER_IMPLEMENTATION_PLAN_READY"


def test_audit_success_true():
    audit = _audit()
    assert audit["success"] is True


def test_audit_boundary_no_violations():
    audit = _audit()
    assert audit["safe_boundary"]["violations"] == []


# ---------------------------------------------------------------------------
# 45. Phase 1-D dry-run matrix와 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1e_consistent_with_phase1d():
    import importlib.util
    phase1d_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1d_adapter_dry_run_compat",
        ROOT / "scripts" / "ops" / "audit_5050_phase1d_adapter_dry_run_compat.py"
    )
    phase1d_mod = importlib.util.module_from_spec(phase1d_spec)
    phase1d_spec.loader.exec_module(phase1d_mod)

    phase1e_mod = _load()
    phase1d_ids = [c["adapter_id"] for c in phase1d_mod.PHASE1D_DRY_RUN_CASES]

    for p in phase1e_mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["adapter_id"] in phase1d_ids, (
            f"{p['adapter_id']} not found in Phase 1-D dry-run cases"
        )


# ---------------------------------------------------------------------------
# 46. Phase 1-B adapter contract matrix와 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1e_consistent_with_phase1b():
    import importlib.util
    phase1b_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1b_adapter_contract_detail",
        ROOT / "scripts" / "ops" / "audit_5050_phase1b_adapter_contract_detail.py"
    )
    phase1b_mod = importlib.util.module_from_spec(phase1b_spec)
    phase1b_spec.loader.exec_module(phase1b_mod)

    phase1e_mod = _load()
    phase1b_ids = [a["adapter_id"] for a in phase1b_mod.PHASE1B_ADAPTERS]

    for p in phase1e_mod.PHASE1E_IMPLEMENTATION_PLANS:
        assert p["adapter_id"] in phase1b_ids, (
            f"{p['adapter_id']} not found in Phase 1-B adapters"
        )


def test_phase1e_risk_consistent_with_phase1b():
    import importlib.util
    phase1b_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1b_adapter_contract_detail",
        ROOT / "scripts" / "ops" / "audit_5050_phase1b_adapter_contract_detail.py"
    )
    phase1b_mod = importlib.util.module_from_spec(phase1b_spec)
    phase1b_spec.loader.exec_module(phase1b_mod)

    phase1e_mod = _load()
    for p in phase1e_mod.PHASE1E_IMPLEMENTATION_PLANS:
        b = next((a for a in phase1b_mod.PHASE1B_ADAPTERS
                  if a["adapter_id"] == p["adapter_id"]), None)
        assert b is not None
        assert b["risk_level"] == p["risk_level"], (
            f"{p['adapter_id']} risk_level mismatch Phase 1-B vs 1-E"
        )


# ---------------------------------------------------------------------------
# 47. Phase 1 contract freeze matrix와 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1e_paths_in_phase1_contracts():
    import importlib.util
    phase1_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1_8400_contract_freeze",
        ROOT / "scripts" / "ops" / "audit_5050_phase1_8400_contract_freeze.py"
    )
    phase1_mod = importlib.util.module_from_spec(phase1_spec)
    phase1_spec.loader.exec_module(phase1_mod)

    phase1e_mod = _load()
    phase1_paths = [c["legacy_path"] for c in phase1_mod.PHASE1_CONTRACTS]

    for p in phase1e_mod.PHASE1E_IMPLEMENTATION_PLANS:
        normalized = p["legacy_path_template"].replace("<id>", "<task_id>")
        assert normalized in phase1_paths, (
            f"{p['legacy_path_template']} (normalized: {normalized}) not in Phase 1"
        )


# ---------------------------------------------------------------------------
# 48. 기존 5050 characterization matrix와 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1e_paths_in_characterization():
    import importlib.util
    char_spec = importlib.util.spec_from_file_location(
        "audit_5050_legacy_characterization",
        ROOT / "scripts" / "ops" / "audit_5050_legacy_characterization.py"
    )
    char_mod = importlib.util.module_from_spec(char_spec)
    char_spec.loader.exec_module(char_mod)

    phase1e_mod = _load()
    char_paths = [r["path"] for r in char_mod.ROUTE_MATRIX]

    for p in phase1e_mod.PHASE1E_IMPLEMENTATION_PLANS:
        normalized = p["legacy_path_template"].replace("<id>", "<task_id>")
        assert normalized in char_paths, (
            f"{p['legacy_path_template']} (normalized: {normalized}) not in characterization"
        )


# ---------------------------------------------------------------------------
# 49. 서버 반영/실호출/DB write 플래그 모두 False
# ---------------------------------------------------------------------------

def test_safe_boundary_all_false():
    mod = _load()
    for k, v in mod.SAFE_BOUNDARY.items():
        assert v is False, f"SAFE_BOUNDARY[{k}] must be False"


# ---------------------------------------------------------------------------
# 50. known baseline 6개 실패 목록 Phase 1-E PASS와 혼동 금지
# ---------------------------------------------------------------------------

def test_known_baseline_failures_documented():
    mod = _load()
    assert hasattr(mod, "KNOWN_BASELINE_FAILURES")
    assert len(mod.KNOWN_BASELINE_FAILURES) == 6


def test_known_baseline_count_matches():
    assert len(KNOWN_BASELINE_FAILURES) == 6


def test_known_baseline_cad_included():
    assert any("cad" in f.lower() for f in KNOWN_BASELINE_FAILURES)


def test_known_baseline_p1_gates_included():
    assert any("p1_gates" in f for f in KNOWN_BASELINE_FAILURES)


def test_phase1e_verdict_independent_of_baseline():
    audit = _audit()
    assert audit["verdict"] == "PHASE1E_ADAPTER_IMPLEMENTATION_PLAN_READY"
    assert len(audit["known_baseline_failures"]) == 6
