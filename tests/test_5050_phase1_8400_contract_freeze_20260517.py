"""5050 Phase 1 — 8400 contract freeze 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1_8400_CONTRACT_FREEZE_01

실제 HTTP 호출 없이 정적 contract만 검증한다.

금지:
    실제 HTTP 호출 금지 / approve/reject 실행 금지 / execute 호출 금지
    5050 중단 금지 / nginx 변경 금지 / DB write 금지 / secret 출력 금지
    skip/xfail 금지 / 테스트 삭제 금지
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT_SCRIPT = ROOT / "scripts" / "ops" / "audit_5050_phase1_8400_contract_freeze.py"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1_8400_contract_freeze", AUDIT_SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audit():
    return _load().run_audit()


# ---------------------------------------------------------------------------
# 1. Phase 1 route가 정확히 5개
# ---------------------------------------------------------------------------

def test_phase1_routes_exactly_5():
    mod = _load()
    assert len(mod.PHASE1_CONTRACTS) == 5


def test_phase1_audit_total_5():
    audit = _audit()
    assert audit["summary"]["total_routes"] == 5


# ---------------------------------------------------------------------------
# 2. 대상 route 5개 path/method 정확히 일치
# ---------------------------------------------------------------------------

def test_phase1_includes_inbox_get():
    mod = _load()
    r = next((c for c in mod.PHASE1_CONTRACTS
               if c["legacy_path"] == "/api/v1/inbox" and c["legacy_method"] == "GET"), None)
    assert r is not None


def test_phase1_includes_inbox_email_fetch_post():
    mod = _load()
    r = next((c for c in mod.PHASE1_CONTRACTS
               if c["legacy_path"] == "/api/v1/inbox/email/fetch"
               and c["legacy_method"] == "POST"), None)
    assert r is not None


def test_phase1_includes_tasks_post():
    mod = _load()
    r = next((c for c in mod.PHASE1_CONTRACTS
               if c["legacy_path"] == "/api/v1/tasks" and c["legacy_method"] == "POST"), None)
    assert r is not None


def test_phase1_includes_tasks_approve_post():
    mod = _load()
    r = next((c for c in mod.PHASE1_CONTRACTS
               if "approve" in c["legacy_path"] and c["legacy_method"] == "POST"), None)
    assert r is not None


def test_phase1_includes_tasks_reject_post():
    mod = _load()
    r = next((c for c in mod.PHASE1_CONTRACTS
               if "reject" in c["legacy_path"] and c["legacy_method"] == "POST"), None)
    assert r is not None


# ---------------------------------------------------------------------------
# 3. SAME_CONTRACT가 정확히 2개
# ---------------------------------------------------------------------------

def test_same_contract_exactly_2():
    mod = _load()
    cnt = sum(1 for c in mod.PHASE1_CONTRACTS if c["overlap_class"] == "SAME_CONTRACT")
    assert cnt == 2


def test_same_contract_paths():
    mod = _load()
    same = [c["legacy_path"] for c in mod.PHASE1_CONTRACTS
            if c["overlap_class"] == "SAME_CONTRACT"]
    assert "/api/v1/inbox" in same
    assert "/api/v1/tasks" in same


def test_audit_same_contract_2():
    audit = _audit()
    assert audit["summary"]["same_contract"] == 2


# ---------------------------------------------------------------------------
# 4. COMPATIBLE_WITH_ADAPTER가 정확히 3개
# ---------------------------------------------------------------------------

def test_compat_adapter_exactly_3():
    mod = _load()
    cnt = sum(1 for c in mod.PHASE1_CONTRACTS
              if c["overlap_class"] == "COMPATIBLE_WITH_ADAPTER")
    assert cnt == 3


def test_compat_adapter_paths():
    mod = _load()
    compat = [c["legacy_path"] for c in mod.PHASE1_CONTRACTS
              if c["overlap_class"] == "COMPATIBLE_WITH_ADAPTER"]
    assert any("fetch" in p for p in compat)
    assert any("approve" in p for p in compat)
    assert any("reject" in p for p in compat)


def test_audit_compat_adapter_3():
    audit = _audit()
    assert audit["summary"]["compatible_with_adapter"] == 3


# ---------------------------------------------------------------------------
# 5. adapter_required=True가 정확히 3개
# ---------------------------------------------------------------------------

def test_adapter_required_exactly_3():
    mod = _load()
    cnt = sum(1 for c in mod.PHASE1_CONTRACTS if c["adapter_required"] is True)
    assert cnt == 3


def test_adapter_required_false_exactly_2():
    mod = _load()
    cnt = sum(1 for c in mod.PHASE1_CONTRACTS if c["adapter_required"] is False)
    assert cnt == 2


def test_audit_adapter_required_3():
    audit = _audit()
    assert audit["summary"]["adapter_required"] == 3


# ---------------------------------------------------------------------------
# 6. 모든 route가 side_effect_allowed=False
# ---------------------------------------------------------------------------

def test_all_side_effect_false():
    mod = _load()
    for c in mod.PHASE1_CONTRACTS:
        assert c["side_effect_allowed"] is False, f"{c['legacy_path']} side_effect_allowed must be False"


def test_audit_side_effect_false_5():
    audit = _audit()
    assert audit["summary"]["side_effect_allowed_false"] == 5


# ---------------------------------------------------------------------------
# 7. 모든 route가 do_not_call_live=True
# ---------------------------------------------------------------------------

def test_all_do_not_call_live():
    mod = _load()
    for c in mod.PHASE1_CONTRACTS:
        assert c["do_not_call_live"] is True, f"{c['legacy_path']} do_not_call_live must be True"


def test_audit_do_not_call_live_5():
    audit = _audit()
    assert audit["summary"]["do_not_call_live_true"] == 5


# ---------------------------------------------------------------------------
# 8. 모든 route가 do_not_stop_5050=True
# ---------------------------------------------------------------------------

def test_all_do_not_stop_5050():
    mod = _load()
    for c in mod.PHASE1_CONTRACTS:
        assert c["do_not_stop_5050"] is True, f"{c['legacy_path']} do_not_stop_5050 must be True"


def test_audit_do_not_stop_5050_5():
    audit = _audit()
    assert audit["summary"]["do_not_stop_5050_true"] == 5


# ---------------------------------------------------------------------------
# 9. 모든 route가 nginx_unchanged=True
# ---------------------------------------------------------------------------

def test_all_nginx_unchanged():
    mod = _load()
    for c in mod.PHASE1_CONTRACTS:
        assert c["nginx_unchanged"] is True, f"{c['legacy_path']} nginx_unchanged must be True"


def test_audit_nginx_unchanged_5():
    audit = _audit()
    assert audit["summary"]["nginx_unchanged_true"] == 5


# ---------------------------------------------------------------------------
# 10. approve/reject는 live_call_allowed=False
# ---------------------------------------------------------------------------

def test_approve_live_call_false():
    mod = _load()
    approve = next((c for c in mod.PHASE1_CONTRACTS if "approve" in c["legacy_path"]), None)
    assert approve is not None
    assert approve["live_call_allowed"] is False


def test_reject_live_call_false():
    mod = _load()
    reject = next((c for c in mod.PHASE1_CONTRACTS if "reject" in c["legacy_path"]), None)
    assert reject is not None
    assert reject["live_call_allowed"] is False


# ---------------------------------------------------------------------------
# 11. approve/reject는 risk_level=HIGH
# ---------------------------------------------------------------------------

def test_approve_risk_high():
    mod = _load()
    approve = next((c for c in mod.PHASE1_CONTRACTS if "approve" in c["legacy_path"]), None)
    assert approve["risk_level"] == "HIGH"


def test_reject_risk_high():
    mod = _load()
    reject = next((c for c in mod.PHASE1_CONTRACTS if "reject" in c["legacy_path"]), None)
    assert reject["risk_level"] == "HIGH"


# ---------------------------------------------------------------------------
# 12. email/fetch는 adapter_required=True
# ---------------------------------------------------------------------------

def test_email_fetch_adapter_required():
    mod = _load()
    fetch = next((c for c in mod.PHASE1_CONTRACTS if "fetch" in c["legacy_path"]), None)
    assert fetch is not None
    assert fetch["adapter_required"] is True


# ---------------------------------------------------------------------------
# 13. inbox GET은 adapter_required=False
# ---------------------------------------------------------------------------

def test_inbox_get_no_adapter():
    mod = _load()
    inbox = next((c for c in mod.PHASE1_CONTRACTS
                  if c["legacy_path"] == "/api/v1/inbox" and c["legacy_method"] == "GET"), None)
    assert inbox["adapter_required"] is False


# ---------------------------------------------------------------------------
# 14. tasks POST는 adapter_required=False
# ---------------------------------------------------------------------------

def test_tasks_post_no_adapter():
    mod = _load()
    tasks = next((c for c in mod.PHASE1_CONTRACTS
                  if c["legacy_path"] == "/api/v1/tasks" and c["legacy_method"] == "POST"), None)
    assert tasks["adapter_required"] is False


# ---------------------------------------------------------------------------
# 15. /execute가 Phase 1 대상에 절대 포함되지 않음
# ---------------------------------------------------------------------------

def test_execute_not_in_phase1():
    mod = _load()
    paths = [c["legacy_path"] for c in mod.PHASE1_CONTRACTS]
    assert not any("execute" in p for p in paths)


def test_execute_in_excluded():
    mod = _load()
    assert "/api/v1/tasks/<task_id>/execute" in mod.PHASE1_EXCLUDED["HOLD_DANGEROUS"]


# ---------------------------------------------------------------------------
# 16. webhook route가 Phase 1 대상에 절대 포함되지 않음
# ---------------------------------------------------------------------------

def test_webhook_not_in_phase1():
    mod = _load()
    paths = [c["legacy_path"] for c in mod.PHASE1_CONTRACTS]
    assert not any("webhook" in p for p in paths)


def test_webhooks_in_excluded():
    mod = _load()
    excluded = mod.PHASE1_EXCLUDED["DO_NOT_TOUCH"]
    assert any("kakaowork" in p for p in excluded)
    assert any("kakaotalk" in p for p in excluded)


# ---------------------------------------------------------------------------
# 17. dashboard route가 Phase 1 대상에 절대 포함되지 않음
# ---------------------------------------------------------------------------

def test_dashboard_not_in_phase1():
    mod = _load()
    paths = [c["legacy_path"] for c in mod.PHASE1_CONTRACTS]
    assert not any("/dashboard" in p for p in paths)


def test_dashboard_in_excluded():
    mod = _load()
    excluded = mod.PHASE1_EXCLUDED["HOLD_DASHBOARD"]
    assert any("/dashboard" == p for p in excluded)


# ---------------------------------------------------------------------------
# 18. freeze_verdict가 READY_FOR_COMPAT_TEST
# ---------------------------------------------------------------------------

def test_all_freeze_verdict_ready():
    mod = _load()
    for c in mod.PHASE1_CONTRACTS:
        assert c["freeze_verdict"] == "READY_FOR_COMPAT_TEST", (
            f"{c['legacy_path']} freeze_verdict must be READY_FOR_COMPAT_TEST"
        )


def test_audit_freeze_ready_5():
    audit = _audit()
    assert audit["summary"]["freeze_ready"] == 5


# ---------------------------------------------------------------------------
# 19. 감사 스크립트 결과가 PHASE1_CONTRACT_FREEZE_READY
# ---------------------------------------------------------------------------

def test_audit_verdict_phase1_ready():
    audit = _audit()
    assert audit["verdict"] == "PHASE1_CONTRACT_FREEZE_READY"


def test_audit_success_true():
    audit = _audit()
    assert audit["success"] is True


def test_audit_boundary_no_violations():
    audit = _audit()
    assert audit["safe_boundary"]["violations"] == []


# ---------------------------------------------------------------------------
# 20. 기존 characterization 20개 matrix와 Phase 1 5개가 충돌하지 않음
# ---------------------------------------------------------------------------

def test_phase1_paths_all_in_characterization():
    import importlib.util
    char_spec = importlib.util.spec_from_file_location(
        "audit_5050_legacy_characterization",
        ROOT / "scripts" / "ops" / "audit_5050_legacy_characterization.py"
    )
    char_mod = importlib.util.module_from_spec(char_spec)
    char_spec.loader.exec_module(char_mod)

    char_paths = [r["path"] for r in char_mod.ROUTE_MATRIX]
    freeze_mod = _load()

    for c in freeze_mod.PHASE1_CONTRACTS:
        assert c["legacy_path"] in char_paths, (
            f"{c['legacy_path']} not found in characterization matrix"
        )


def test_phase1_migration_class_consistent():
    import importlib.util
    char_spec = importlib.util.spec_from_file_location(
        "audit_5050_legacy_characterization",
        ROOT / "scripts" / "ops" / "audit_5050_legacy_characterization.py"
    )
    char_mod = importlib.util.module_from_spec(char_spec)
    char_spec.loader.exec_module(char_mod)

    freeze_mod = _load()
    for c in freeze_mod.PHASE1_CONTRACTS:
        char_route = next(
            (r for r in char_mod.ROUTE_MATRIX if r["path"] == c["legacy_path"]),
            None
        )
        assert char_route is not None
        assert char_route["migration_class"] == char_mod.MC_ALREADY_ROUTED, (
            f"{c['legacy_path']} should be ALREADY_ROUTED_TO_8400 in characterization"
        )


def test_phase1_safe_boundary_all_false():
    mod = _load()
    for k, v in mod.SAFE_BOUNDARY.items():
        assert v is False, f"SAFE_BOUNDARY[{k}] must be False"


def test_phase1_all_contracts_phase1():
    mod = _load()
    for c in mod.PHASE1_CONTRACTS:
        assert c["phase"] == "PHASE_1"
