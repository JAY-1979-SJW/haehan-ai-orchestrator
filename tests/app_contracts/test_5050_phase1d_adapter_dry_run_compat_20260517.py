"""5050 Phase 1-D — adapter dry-run compatibility 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1D_ADAPTER_DRY_RUN_COMPAT_TEST_01

실제 HTTP 호출 없이 dry-run fixture와 정적 compatibility contract만 검증한다.

금지:
    실제 HTTP 호출 금지 / email fetch 실행 금지 / approve/reject 실행 금지
    execute 호출 금지 / webhook 호출 금지 / DB write 금지
    5050 중단 금지 / nginx 변경 금지 / secret 출력 금지 / adapter 실제 구현 금지
    skip/xfail 금지 / 테스트 삭제 금지

예외(2026-10-09, PR #165 CI165, 대표님 승인): phase1b·phase1_8400·characterization 교차
일관성 시험 4개(test_phase1d_consistent_with_phase1b·test_phase1d_risk_consistent_with_phase1b·
test_phase1d_paths_in_phase1_contracts·test_phase1d_paths_in_characterization)는 커밋
c3e50f0c("사용처 0 확인한 일회성 8개와 그 전용 시험 5개 삭제")로 대상 감사 스크립트 3개가
전부 영구 삭제돼 교차 비교 자체가 불가능하다. 위 "skip 금지" 는 코드 안전성 검증을 회피하는
것을 막기 위한 원칙이라, 검증 대상이 아예 존재하지 않게 된 이 4건에 한해서만
`pytest.skip(reason=...)` 로 처리한다(다른 시험·다른 사유로 확대 적용 금지).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

AUDIT_SCRIPT = ROOT / "tools" / "audit_5050_phase1d_adapter_dry_run_compat.py"
PHASE1B_SCRIPT = ROOT / "scripts" / "ops" / "audit_5050_phase1b_adapter_contract_detail.py"
PHASE1_8400_SCRIPT = ROOT / "scripts" / "ops" / "audit_5050_phase1_8400_contract_freeze.py"
CHARACTERIZATION_SCRIPT = ROOT / "scripts" / "ops" / "audit_5050_legacy_characterization.py"
_DELETED_DEPENDENCY_REASON = (
    "의존 스크립트 삭제 확정(c3e50f0c, 2026-10-08)으로 교차 비교 불가 — {script} 없음"
)

# known baseline failures — 이번 공정과 무관한 기존 실패 목록 (문서성 상수)
# CAD 관련 4건은 2026-06-04 "CAD 모듈 전체 삭제"(17130f8e)로 그 시험 파일 자체가 없어져
# 목록에서 제거(tools/audit_5050_phase1d_adapter_dry_run_compat.py 와 동기, B0-a).
KNOWN_BASELINE_FAILURES = [
    "tests/app_contracts/test_app_foundation_p1_gates.py::test_server_browser_guard_no_violations",
    "tests/app_contracts/test_app_foundation_p1_gates.py::test_p1_gates_all_zero_new_violations",
]


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1d_adapter_dry_run_compat", AUDIT_SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audit():
    return _load().run_audit()


# ---------------------------------------------------------------------------
# 1. Phase 1-D dry-run case가 정확히 3개
# ---------------------------------------------------------------------------

def test_phase1d_dry_run_cases_exactly_3():
    mod = _load()
    assert len(mod.PHASE1D_DRY_RUN_CASES) == 3


def test_audit_total_cases_3():
    audit = _audit()
    assert audit["summary"]["total_dry_run_cases"] == 3


# ---------------------------------------------------------------------------
# 2. 대상 adapter가 정확히 3개
# ---------------------------------------------------------------------------

def test_includes_inbox_email_fetch_adapter():
    mod = _load()
    r = next((c for c in mod.PHASE1D_DRY_RUN_CASES
               if c["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert r is not None


def test_includes_task_approve_path_auth_adapter():
    mod = _load()
    r = next((c for c in mod.PHASE1D_DRY_RUN_CASES
               if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert r is not None


def test_includes_task_reject_path_auth_adapter():
    mod = _load()
    r = next((c for c in mod.PHASE1D_DRY_RUN_CASES
               if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert r is not None


# ---------------------------------------------------------------------------
# 3. 모든 case가 dry_run_only=True
# ---------------------------------------------------------------------------

def test_all_dry_run_only_true():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["dry_run_only"] is True, (
            f"{c['adapter_id']} dry_run_only must be True"
        )


def test_audit_dry_run_only_3():
    audit = _audit()
    assert audit["summary"]["dry_run_only_true"] == 3


# ---------------------------------------------------------------------------
# 4. 모든 case가 fixture_only=True
# ---------------------------------------------------------------------------

def test_all_fixture_only_true():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["fixture_only"] is True, (
            f"{c['adapter_id']} fixture_only must be True"
        )


def test_audit_fixture_only_3():
    audit = _audit()
    assert audit["summary"]["fixture_only_true"] == 3


# ---------------------------------------------------------------------------
# 5. 모든 case가 live_call_allowed=False
# ---------------------------------------------------------------------------

def test_all_live_call_false():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["live_call_allowed"] is False, (
            f"{c['adapter_id']} live_call_allowed must be False"
        )


def test_audit_live_call_false_3():
    audit = _audit()
    assert audit["summary"]["live_call_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 6. 모든 case가 side_effect_allowed=False
# ---------------------------------------------------------------------------

def test_all_side_effect_false():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["side_effect_allowed"] is False, (
            f"{c['adapter_id']} side_effect_allowed must be False"
        )


def test_audit_side_effect_false_3():
    audit = _audit()
    assert audit["summary"]["side_effect_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 7. 모든 case가 db_write_allowed=False
# ---------------------------------------------------------------------------

def test_all_db_write_false():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["db_write_allowed"] is False, (
            f"{c['adapter_id']} db_write_allowed must be False"
        )


def test_audit_db_write_false_3():
    audit = _audit()
    assert audit["summary"]["db_write_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 8. 모든 case가 secret_value_allowed=False
# ---------------------------------------------------------------------------

def test_all_secret_value_false():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["secret_value_allowed"] is False, (
            f"{c['adapter_id']} secret_value_allowed must be False"
        )


def test_audit_secret_false_3():
    audit = _audit()
    assert audit["summary"]["secret_value_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 9. email/fetch는 approval_gate_required=False
# ---------------------------------------------------------------------------

def test_fetch_approval_gate_false():
    mod = _load()
    fetch = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert fetch["approval_gate_required"] is False


# ---------------------------------------------------------------------------
# 10. approve/reject는 approval_gate_required=True
# ---------------------------------------------------------------------------

def test_approve_approval_gate_true():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["approval_gate_required"] is True


def test_reject_approval_gate_true():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["approval_gate_required"] is True


def test_audit_gate_true_2():
    audit = _audit()
    assert audit["summary"]["approval_gate_required_true"] == 2


# ---------------------------------------------------------------------------
# 11. email/fetch risk_level=MEDIUM
# ---------------------------------------------------------------------------

def test_fetch_risk_medium():
    mod = _load()
    fetch = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert fetch["risk_level"] == "MEDIUM"


# ---------------------------------------------------------------------------
# 12. approve/reject risk_level=HIGH
# ---------------------------------------------------------------------------

def test_approve_risk_high():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["risk_level"] == "HIGH"


def test_reject_risk_high():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["risk_level"] == "HIGH"


def test_audit_high_risk_2():
    audit = _audit()
    assert audit["summary"]["risk_level_HIGH"] == 2


def test_audit_medium_risk_1():
    audit = _audit()
    assert audit["summary"]["risk_level_MEDIUM"] == 1


# ---------------------------------------------------------------------------
# 13. approve legacy_path_template이 /api/v1/tasks/<id>/approve
# ---------------------------------------------------------------------------

def test_approve_legacy_path_template():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["legacy_path_template"] == "/api/v1/tasks/<id>/approve"


# ---------------------------------------------------------------------------
# 14. approve fastapi_path_template이 /api/v1/tasks/{id}/approve
# ---------------------------------------------------------------------------

def test_approve_fastapi_path_template():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["fastapi_path_template"] == "/api/v1/tasks/{id}/approve"


# ---------------------------------------------------------------------------
# 15. reject legacy_path_template이 /api/v1/tasks/<id>/reject
# ---------------------------------------------------------------------------

def test_reject_legacy_path_template():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["legacy_path_template"] == "/api/v1/tasks/<id>/reject"


# ---------------------------------------------------------------------------
# 16. reject fastapi_path_template이 /api/v1/tasks/{id}/reject
# ---------------------------------------------------------------------------

def test_reject_fastapi_path_template():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["fastapi_path_template"] == "/api/v1/tasks/{id}/reject"


# ---------------------------------------------------------------------------
# 17-20. sample path double slash 없음
# ---------------------------------------------------------------------------

def test_approve_sample_legacy_no_double_slash():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert "//" not in approve["sample_legacy_path"]


def test_approve_sample_fastapi_no_double_slash():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert "//" not in approve["sample_fastapi_path"]


def test_reject_sample_legacy_no_double_slash():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert "//" not in reject["sample_legacy_path"]


def test_reject_sample_fastapi_no_double_slash():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert "//" not in reject["sample_fastapi_path"]


# ---------------------------------------------------------------------------
# 21-22. /api/v1/tasks//approve, //reject 절대 생성되지 않음
# ---------------------------------------------------------------------------

def test_double_slash_approve_never_generated():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        for field in ("legacy_path_template", "fastapi_path_template",
                      "sample_legacy_path", "sample_fastapi_path"):
            val = c.get(field, "")
            assert val != "/api/v1/tasks//approve", (
                f"{c['adapter_id']} must never generate /api/v1/tasks//approve"
            )


def test_double_slash_reject_never_generated():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        for field in ("legacy_path_template", "fastapi_path_template",
                      "sample_legacy_path", "sample_fastapi_path"):
            val = c.get(field, "")
            assert val != "/api/v1/tasks//reject", (
                f"{c['adapter_id']} must never generate /api/v1/tasks//reject"
            )


def test_audit_no_double_slash():
    audit = _audit()
    assert audit["summary"]["no_double_slash"] is True


# ---------------------------------------------------------------------------
# 23. /execute가 Phase 1-D에 포함되지 않음
# ---------------------------------------------------------------------------

def test_execute_not_in_phase1d():
    mod = _load()
    paths = [c["legacy_path_template"] for c in mod.PHASE1D_DRY_RUN_CASES]
    assert not any("execute" in p for p in paths)


def test_execute_in_excluded():
    mod = _load()
    assert "/api/v1/tasks/<task_id>/execute" in mod.PHASE1D_EXCLUDED["HOLD_DANGEROUS"]


# ---------------------------------------------------------------------------
# 24. webhook route가 Phase 1-D에 포함되지 않음
# ---------------------------------------------------------------------------

def test_webhook_not_in_phase1d():
    mod = _load()
    paths = [c["legacy_path_template"] for c in mod.PHASE1D_DRY_RUN_CASES]
    assert not any("webhook" in p for p in paths)


def test_webhooks_in_excluded():
    mod = _load()
    excluded = mod.PHASE1D_EXCLUDED["DO_NOT_TOUCH"]
    assert any("kakaowork" in p for p in excluded)
    assert any("kakaotalk" in p for p in excluded)


# ---------------------------------------------------------------------------
# 25. dashboard route가 Phase 1-D에 포함되지 않음
# ---------------------------------------------------------------------------

def test_dashboard_not_in_phase1d():
    mod = _load()
    paths = [c["legacy_path_template"] for c in mod.PHASE1D_DRY_RUN_CASES]
    assert not any("/dashboard" in p for p in paths)


# ---------------------------------------------------------------------------
# 26. SAME_CONTRACT 2개가 Phase 1-D에 포함되지 않음
# ---------------------------------------------------------------------------

def test_inbox_get_not_in_phase1d():
    mod = _load()
    r = next((c for c in mod.PHASE1D_DRY_RUN_CASES
               if c["legacy_path_template"] == "/api/v1/inbox"
               and c["legacy_method"] == "GET"), None)
    assert r is None


def test_tasks_post_exact_not_in_phase1d():
    mod = _load()
    r = next((c for c in mod.PHASE1D_DRY_RUN_CASES
               if c["legacy_path_template"] == "/api/v1/tasks"
               and c["legacy_method"] == "POST"), None)
    assert r is None


def test_same_contract_in_excluded():
    mod = _load()
    skip = mod.PHASE1D_EXCLUDED["SAME_CONTRACT_SKIP"]
    assert "/api/v1/inbox" in skip
    assert "/api/v1/tasks" in skip


# ---------------------------------------------------------------------------
# 27. email/fetch credential_policy=SECRET_NAMES_ONLY_NO_SECRET_VALUES
# ---------------------------------------------------------------------------

def test_fetch_credential_policy():
    mod = _load()
    fetch = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert fetch["credential_policy"] == "SECRET_NAMES_ONLY_NO_SECRET_VALUES"


# ---------------------------------------------------------------------------
# 28. email/fetch request fixture에 secret value가 없음
# ---------------------------------------------------------------------------

def test_fetch_request_fixture_no_secret_value():
    mod = _load()
    fetch = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    fixture_str = str(fetch["request_fixture"])
    forbidden_patterns = ["password", "secret_key", "AKID", "-----BEGIN"]
    for pat in forbidden_patterns:
        assert pat not in fixture_str, (
            f"request_fixture must not contain secret value pattern: {pat}"
        )


# ---------------------------------------------------------------------------
# 29-30. approve/reject auth_policy=COMPARE_ONLY_NO_BYPASS
# ---------------------------------------------------------------------------

def test_approve_auth_policy():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["auth_policy"] == "COMPARE_ONLY_NO_BYPASS"


def test_reject_auth_policy():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["auth_policy"] == "COMPARE_ONLY_NO_BYPASS"


# ---------------------------------------------------------------------------
# 31-32. permission_policy
# ---------------------------------------------------------------------------

def test_approve_permission_policy():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["permission_policy"] == "APPROVAL_ACTION_REQUIRES_EXPLICIT_GATE"


def test_reject_permission_policy():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["permission_policy"] == "REJECT_ACTION_REQUIRES_EXPLICIT_GATE"


# ---------------------------------------------------------------------------
# 33-34. approval_gate_policy=GATE_REQUIRED_BUT_NOT_EXECUTED
# ---------------------------------------------------------------------------

def test_approve_gate_policy():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["approval_gate_policy"] == "GATE_REQUIRED_BUT_NOT_EXECUTED"


def test_reject_gate_policy():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["approval_gate_policy"] == "GATE_REQUIRED_BUT_NOT_EXECUTED"


# ---------------------------------------------------------------------------
# 35-36. approve/reject executor_boundary=APPROVAL_ROUTE_NOT_EXECUTOR
# ---------------------------------------------------------------------------

def test_approve_executor_boundary():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    assert approve["executor_boundary"] == "APPROVAL_ROUTE_NOT_EXECUTOR"


def test_reject_executor_boundary():
    mod = _load()
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)
    assert reject["executor_boundary"] == "APPROVAL_ROUTE_NOT_EXECUTOR"


# ---------------------------------------------------------------------------
# 37. email/fetch executor_boundary=NOT_EXECUTOR_ROUTE
# ---------------------------------------------------------------------------

def test_fetch_executor_boundary():
    mod = _load()
    fetch = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "INBOX_EMAIL_FETCH_ADAPTER"), None)
    assert fetch["executor_boundary"] == "NOT_EXECUTOR_ROUTE"


# ---------------------------------------------------------------------------
# 38-40. legacy/fastapi/normalized response fixture 존재
# ---------------------------------------------------------------------------

def test_all_legacy_response_fixture_exist():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert "legacy_response_fixture" in c, (
            f"{c['adapter_id']} must have legacy_response_fixture"
        )
        assert c["legacy_response_fixture"]


def test_all_fastapi_response_fixture_exist():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert "fastapi_response_fixture" in c, (
            f"{c['adapter_id']} must have fastapi_response_fixture"
        )
        assert c["fastapi_response_fixture"]


def test_all_normalized_response_exist():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert "expected_normalized_response" in c, (
            f"{c['adapter_id']} must have expected_normalized_response"
        )
        assert c["expected_normalized_response"]


# ---------------------------------------------------------------------------
# 41-43. policy 필드가 UNKNOWN이 아님
# ---------------------------------------------------------------------------

def test_response_mapping_policy_not_unknown():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["response_mapping_policy"] != "UNKNOWN", (
            f"{c['adapter_id']} response_mapping_policy must not be UNKNOWN"
        )


def test_request_mapping_policy_not_unknown():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["request_mapping_policy"] != "UNKNOWN", (
            f"{c['adapter_id']} request_mapping_policy must not be UNKNOWN"
        )


def test_status_code_policy_not_unknown():
    mod = _load()
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["status_code_policy"] != "UNKNOWN", (
            f"{c['adapter_id']} status_code_policy must not be UNKNOWN"
        )


# ---------------------------------------------------------------------------
# 44. 감사 스크립트 verdict=PHASE1D_ADAPTER_DRY_RUN_COMPAT_READY
# ---------------------------------------------------------------------------

def test_audit_verdict_phase1d_ready():
    audit = _audit()
    assert audit["verdict"] == "PHASE1D_ADAPTER_DRY_RUN_COMPAT_READY"


def test_audit_success_true():
    audit = _audit()
    assert audit["success"] is True


def test_audit_boundary_no_violations():
    audit = _audit()
    assert audit["safe_boundary"]["violations"] == []


# ---------------------------------------------------------------------------
# 45. Phase 1-B adapter contract matrix와 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1d_consistent_with_phase1b():
    if not PHASE1B_SCRIPT.is_file():
        pytest.skip(_DELETED_DEPENDENCY_REASON.format(script=PHASE1B_SCRIPT))
    import importlib.util
    phase1b_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1b_adapter_contract_detail",
        ROOT / "scripts" / "ops" / "audit_5050_phase1b_adapter_contract_detail.py"
    )
    phase1b_mod = importlib.util.module_from_spec(phase1b_spec)
    phase1b_spec.loader.exec_module(phase1b_mod)

    phase1d_mod = _load()
    phase1b_ids = [a["adapter_id"] for a in phase1b_mod.PHASE1B_ADAPTERS]

    for c in phase1d_mod.PHASE1D_DRY_RUN_CASES:
        assert c["adapter_id"] in phase1b_ids, (
            f"{c['adapter_id']} not found in Phase 1-B adapters"
        )


def test_phase1d_risk_consistent_with_phase1b():
    if not PHASE1B_SCRIPT.is_file():
        pytest.skip(_DELETED_DEPENDENCY_REASON.format(script=PHASE1B_SCRIPT))
    import importlib.util
    phase1b_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1b_adapter_contract_detail",
        ROOT / "scripts" / "ops" / "audit_5050_phase1b_adapter_contract_detail.py"
    )
    phase1b_mod = importlib.util.module_from_spec(phase1b_spec)
    phase1b_spec.loader.exec_module(phase1b_mod)

    phase1d_mod = _load()
    for c in phase1d_mod.PHASE1D_DRY_RUN_CASES:
        phase1b_adapter = next(
            (a for a in phase1b_mod.PHASE1B_ADAPTERS if a["adapter_id"] == c["adapter_id"]),
            None,
        )
        assert phase1b_adapter is not None
        assert phase1b_adapter["risk_level"] == c["risk_level"], (
            f"{c['adapter_id']} risk_level mismatch between Phase 1-B and 1-D"
        )


# ---------------------------------------------------------------------------
# 46. Phase 1 contract freeze matrix와 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1d_paths_in_phase1_contracts():
    if not PHASE1_8400_SCRIPT.is_file():
        pytest.skip(_DELETED_DEPENDENCY_REASON.format(script=PHASE1_8400_SCRIPT))
    import importlib.util
    phase1_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1_8400_contract_freeze",
        ROOT / "scripts" / "ops" / "audit_5050_phase1_8400_contract_freeze.py"
    )
    phase1_mod = importlib.util.module_from_spec(phase1_spec)
    phase1_spec.loader.exec_module(phase1_mod)

    phase1d_mod = _load()
    phase1_paths = [c["legacy_path"] for c in phase1_mod.PHASE1_CONTRACTS]

    for c in phase1d_mod.PHASE1D_DRY_RUN_CASES:
        normalized = c["legacy_path_template"].replace("<id>", "<task_id>")
        assert normalized in phase1_paths, (
            f"{c['legacy_path_template']} (normalized: {normalized}) not in Phase 1"
        )


# ---------------------------------------------------------------------------
# 47. 기존 5050 characterization matrix와 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1d_paths_in_characterization():
    if not CHARACTERIZATION_SCRIPT.is_file():
        pytest.skip(_DELETED_DEPENDENCY_REASON.format(script=CHARACTERIZATION_SCRIPT))
    import importlib.util
    char_spec = importlib.util.spec_from_file_location(
        "audit_5050_legacy_characterization",
        ROOT / "scripts" / "ops" / "audit_5050_legacy_characterization.py"
    )
    char_mod = importlib.util.module_from_spec(char_spec)
    char_spec.loader.exec_module(char_mod)

    phase1d_mod = _load()
    char_paths = [r["path"] for r in char_mod.ROUTE_MATRIX]

    for c in phase1d_mod.PHASE1D_DRY_RUN_CASES:
        normalized = c["legacy_path_template"].replace("<id>", "<task_id>")
        assert normalized in char_paths, (
            f"{c['legacy_path_template']} (normalized: {normalized}) not in characterization"
        )


# ---------------------------------------------------------------------------
# 48. 서버 반영/실호출/DB write 플래그 모두 False
# ---------------------------------------------------------------------------

def test_safe_boundary_all_false():
    mod = _load()
    for k, v in mod.SAFE_BOUNDARY.items():
        assert v is False, f"SAFE_BOUNDARY[{k}] must be False"


# ---------------------------------------------------------------------------
# 49. forbidden_routes에 위험 경로 포함, 대상 case에는 없음
# ---------------------------------------------------------------------------

def test_forbidden_routes_contain_execute_and_webhook():
    mod = _load()
    approve = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                    if c["adapter_id"] == "TASK_APPROVE_PATH_AUTH_ADAPTER"), None)
    reject = next((c for c in mod.PHASE1D_DRY_RUN_CASES
                   if c["adapter_id"] == "TASK_REJECT_PATH_AUTH_ADAPTER"), None)

    for c in (approve, reject):
        forbidden = c["forbidden_routes"]
        assert any("execute" in r for r in forbidden)
        assert any("kakaowork" in r for r in forbidden)

    # 대상 case path에는 없음
    for c in mod.PHASE1D_DRY_RUN_CASES:
        assert c["legacy_path_template"] not in [
            "/api/v1/tasks/<id>/execute",
            "/api/v1/webhooks/kakaowork",
        ]


def test_audit_no_forbidden_in_cases():
    audit = _audit()
    assert audit["summary"]["no_forbidden_route"] is True


# ---------------------------------------------------------------------------
# 50. known baseline failures 목록 문서 상수 존재 (Phase 1-D PASS와 혼동 방지)
# ---------------------------------------------------------------------------

def test_known_baseline_failures_documented():
    mod = _load()
    assert hasattr(mod, "KNOWN_BASELINE_FAILURES")
    assert len(mod.KNOWN_BASELINE_FAILURES) == 2


def test_known_baseline_count_matches_test_file():
    assert len(KNOWN_BASELINE_FAILURES) == 2


def test_known_baseline_no_longer_contains_cad_failures():
    """CAD 모듈 전체 삭제(17130f8e, 2026-06-04)로 그 시험 파일 자체가 없어져 목록에서도 제거됐다(B0-a)."""
    assert not any("cad" in f.lower() for f in KNOWN_BASELINE_FAILURES)


def test_known_baseline_contains_p1_gates():
    assert any("p1_gates" in f for f in KNOWN_BASELINE_FAILURES)


def test_phase1d_verdict_independent_of_baseline():
    audit = _audit()
    assert audit["verdict"] == "PHASE1D_ADAPTER_DRY_RUN_COMPAT_READY"
    assert len(audit["known_baseline_failures"]) == 2
