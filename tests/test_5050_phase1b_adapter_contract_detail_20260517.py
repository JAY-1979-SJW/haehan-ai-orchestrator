"""5050 Phase 1-B — COMPATIBLE_WITH_ADAPTER adapter 상세 계약 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1B_ADAPTER_CONTRACT_DETAIL_01

실제 HTTP 호출 없이 정적 adapter contract만 검증한다.

금지:
    실제 HTTP 호출 금지 / email fetch 실행 금지 / approve/reject 실행 금지
    execute 호출 금지 / webhook 호출 금지 / DB write 금지
    5050 중단 금지 / nginx 변경 금지 / secret 출력 금지
    skip/xfail 금지 / 테스트 삭제 금지
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT_SCRIPT = ROOT / "scripts" / "archive" / "ops" / "audit_5050_phase1b_adapter_contract_detail.py"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1b_adapter_contract_detail", AUDIT_SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audit():
    return _load().run_audit()


# ---------------------------------------------------------------------------
# 1. Phase 1-B adapter가 정확히 3개
# ---------------------------------------------------------------------------

def test_phase1b_adapters_exactly_3():
    mod = _load()
    assert len(mod.PHASE1B_ADAPTERS) == 3


def test_audit_total_adapters_3():
    audit = _audit()
    assert audit["summary"]["total_adapters"] == 3


# ---------------------------------------------------------------------------
# 2. 대상 3개 path/method 정확히 일치
# ---------------------------------------------------------------------------

def test_phase1b_includes_inbox_email_fetch_post():
    mod = _load()
    r = next((a for a in mod.PHASE1B_ADAPTERS
               if a["legacy_path"] == "/api/v1/inbox/email/fetch"
               and a["legacy_method"] == "POST"), None)
    assert r is not None


def test_phase1b_includes_tasks_approve_post():
    mod = _load()
    r = next((a for a in mod.PHASE1B_ADAPTERS
               if "approve" in a["legacy_path"] and a["legacy_method"] == "POST"), None)
    assert r is not None


def test_phase1b_includes_tasks_reject_post():
    mod = _load()
    r = next((a for a in mod.PHASE1B_ADAPTERS
               if "reject" in a["legacy_path"] and a["legacy_method"] == "POST"), None)
    assert r is not None


# ---------------------------------------------------------------------------
# 3. 모두 COMPATIBLE_WITH_ADAPTER
# ---------------------------------------------------------------------------

def test_all_compatible_with_adapter():
    mod = _load()
    for a in mod.PHASE1B_ADAPTERS:
        assert a["overlap_class"] == "COMPATIBLE_WITH_ADAPTER", (
            f"{a['legacy_path']} overlap_class must be COMPATIBLE_WITH_ADAPTER"
        )


# ---------------------------------------------------------------------------
# 4. adapter_required=True가 정확히 3개
# ---------------------------------------------------------------------------

def test_adapter_required_true_exactly_3():
    mod = _load()
    cnt = sum(1 for a in mod.PHASE1B_ADAPTERS if a["adapter_required"] is True)
    assert cnt == 3


def test_audit_adapter_required_3():
    audit = _audit()
    assert audit["summary"]["adapter_required_true"] == 3


# ---------------------------------------------------------------------------
# 5. live_call_allowed=False가 정확히 3개
# ---------------------------------------------------------------------------

def test_live_call_false_exactly_3():
    mod = _load()
    cnt = sum(1 for a in mod.PHASE1B_ADAPTERS if a["live_call_allowed"] is False)
    assert cnt == 3


def test_audit_live_call_false_3():
    audit = _audit()
    assert audit["summary"]["live_call_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 6. side_effect_allowed=False가 정확히 3개
# ---------------------------------------------------------------------------

def test_side_effect_false_exactly_3():
    mod = _load()
    for a in mod.PHASE1B_ADAPTERS:
        assert a["side_effect_allowed"] is False, (
            f"{a['legacy_path']} side_effect_allowed must be False"
        )


def test_audit_side_effect_false_3():
    audit = _audit()
    assert audit["summary"]["side_effect_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 7. secret_value_allowed=False가 정확히 3개
# ---------------------------------------------------------------------------

def test_secret_value_false_exactly_3():
    mod = _load()
    for a in mod.PHASE1B_ADAPTERS:
        assert a["secret_value_allowed"] is False, (
            f"{a['legacy_path']} secret_value_allowed must be False"
        )


def test_audit_secret_false_3():
    audit = _audit()
    assert audit["summary"]["secret_value_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 8. db_write_allowed=False가 정확히 3개
# ---------------------------------------------------------------------------

def test_db_write_false_exactly_3():
    mod = _load()
    for a in mod.PHASE1B_ADAPTERS:
        assert a["db_write_allowed"] is False, (
            f"{a['legacy_path']} db_write_allowed must be False"
        )


def test_audit_db_false_3():
    audit = _audit()
    assert audit["summary"]["db_write_allowed_false"] == 3


# ---------------------------------------------------------------------------
# 9. credential_policy = SECRET_NAMES_ONLY_NO_SECRET_VALUES (3개 전체)
# ---------------------------------------------------------------------------

def test_all_credential_policy_secret_names_only():
    mod = _load()
    for a in mod.PHASE1B_ADAPTERS:
        assert a["credential_policy"] == "SECRET_NAMES_ONLY_NO_SECRET_VALUES", (
            f"{a['legacy_path']} credential_policy must be SECRET_NAMES_ONLY_NO_SECRET_VALUES"
        )


# ---------------------------------------------------------------------------
# 10. auth_policy: approve/reject는 COMPARE_ONLY_NO_BYPASS
# ---------------------------------------------------------------------------

def test_approve_auth_policy_compare_only():
    mod = _load()
    approve = next((a for a in mod.PHASE1B_ADAPTERS if "approve" in a["legacy_path"]), None)
    assert approve is not None
    assert approve["auth_policy"] == "COMPARE_ONLY_NO_BYPASS"


def test_reject_auth_policy_compare_only():
    mod = _load()
    reject = next((a for a in mod.PHASE1B_ADAPTERS if "reject" in a["legacy_path"]), None)
    assert reject is not None
    assert reject["auth_policy"] == "COMPARE_ONLY_NO_BYPASS"


# ---------------------------------------------------------------------------
# 11. approval_gate_required: approve/reject는 True, fetch는 False
# ---------------------------------------------------------------------------

def test_approve_approval_gate_true():
    mod = _load()
    approve = next((a for a in mod.PHASE1B_ADAPTERS if "approve" in a["legacy_path"]), None)
    assert approve["approval_gate_required"] is True


def test_reject_approval_gate_true():
    mod = _load()
    reject = next((a for a in mod.PHASE1B_ADAPTERS if "reject" in a["legacy_path"]), None)
    assert reject["approval_gate_required"] is True


def test_fetch_approval_gate_false():
    mod = _load()
    fetch = next((a for a in mod.PHASE1B_ADAPTERS if "fetch" in a["legacy_path"]), None)
    assert fetch["approval_gate_required"] is False


def test_audit_approval_gate_true_2():
    audit = _audit()
    assert audit["summary"]["approval_gate_required_true"] == 2


# ---------------------------------------------------------------------------
# 12. path_param_policy: approve/reject는 LEGACY_ANGLE_BRACKET_TO_FASTAPI_CURLY_BRACE
# ---------------------------------------------------------------------------

def test_approve_path_param_policy():
    mod = _load()
    approve = next((a for a in mod.PHASE1B_ADAPTERS if "approve" in a["legacy_path"]), None)
    assert approve["path_param_policy"] == "LEGACY_ANGLE_BRACKET_TO_FASTAPI_CURLY_BRACE"


def test_reject_path_param_policy():
    mod = _load()
    reject = next((a for a in mod.PHASE1B_ADAPTERS if "reject" in a["legacy_path"]), None)
    assert reject["path_param_policy"] == "LEGACY_ANGLE_BRACKET_TO_FASTAPI_CURLY_BRACE"


def test_audit_path_param_adapter_2():
    audit = _audit()
    assert audit["summary"]["path_param_adapter"] == 2


# ---------------------------------------------------------------------------
# 13. adapter_type 분포: PATH_PARAM_AND_AUTH_POLICY_ADAPTER=2, CREDENTIAL_ENV=1
# ---------------------------------------------------------------------------

def test_path_param_auth_adapter_exactly_2():
    mod = _load()
    cnt = sum(1 for a in mod.PHASE1B_ADAPTERS
              if a["adapter_type"] == "PATH_PARAM_AND_AUTH_POLICY_ADAPTER")
    assert cnt == 2


def test_credential_env_adapter_exactly_1():
    mod = _load()
    cnt = sum(1 for a in mod.PHASE1B_ADAPTERS
              if a["adapter_type"] == "CREDENTIAL_ENV_AND_RESPONSE_ADAPTER")
    assert cnt == 1


def test_audit_credential_env_1():
    audit = _audit()
    assert audit["summary"]["credential_env_adapter"] == 1


# ---------------------------------------------------------------------------
# 14. risk_level 분포: HIGH=2, MEDIUM=1
# ---------------------------------------------------------------------------

def test_high_risk_exactly_2():
    mod = _load()
    cnt = sum(1 for a in mod.PHASE1B_ADAPTERS if a["risk_level"] == "HIGH")
    assert cnt == 2


def test_medium_risk_exactly_1():
    mod = _load()
    cnt = sum(1 for a in mod.PHASE1B_ADAPTERS if a["risk_level"] == "MEDIUM")
    assert cnt == 1


def test_audit_high_risk_2():
    audit = _audit()
    assert audit["summary"]["risk_level_HIGH"] == 2


def test_audit_medium_risk_1():
    audit = _audit()
    assert audit["summary"]["risk_level_MEDIUM"] == 1


# ---------------------------------------------------------------------------
# 15. path param 표기 확인: legacy=<id>, fastapi={id} (double slash 절대 금지)
# ---------------------------------------------------------------------------

def test_approve_legacy_path_angle_bracket():
    mod = _load()
    approve = next((a for a in mod.PHASE1B_ADAPTERS if "approve" in a["legacy_path"]), None)
    assert "<id>" in approve["legacy_path"]


def test_approve_fastapi_path_curly_brace():
    mod = _load()
    approve = next((a for a in mod.PHASE1B_ADAPTERS if "approve" in a["legacy_path"]), None)
    assert "{id}" in approve["fastapi_path"]


def test_reject_legacy_path_angle_bracket():
    mod = _load()
    reject = next((a for a in mod.PHASE1B_ADAPTERS if "reject" in a["legacy_path"]), None)
    assert "<id>" in reject["legacy_path"]


def test_reject_fastapi_path_curly_brace():
    mod = _load()
    reject = next((a for a in mod.PHASE1B_ADAPTERS if "reject" in a["legacy_path"]), None)
    assert "{id}" in reject["fastapi_path"]


def test_no_double_slash_in_any_path():
    mod = _load()
    for a in mod.PHASE1B_ADAPTERS:
        assert "//" not in a["legacy_path"], (
            f"{a['adapter_id']} legacy_path contains double slash"
        )
        assert "//" not in a["fastapi_path"], (
            f"{a['adapter_id']} fastapi_path contains double slash"
        )


def test_audit_no_double_slash():
    audit = _audit()
    assert audit["summary"]["no_double_slash"] is True


# ---------------------------------------------------------------------------
# 16. double slash가 PHASE1B_EXCLUDED에 명시됨
# ---------------------------------------------------------------------------

def test_double_slash_approve_in_excluded():
    mod = _load()
    assert "/api/v1/tasks//approve" in mod.PHASE1B_EXCLUDED["DOUBLE_SLASH_FORBIDDEN"]


def test_double_slash_reject_in_excluded():
    mod = _load()
    assert "/api/v1/tasks//reject" in mod.PHASE1B_EXCLUDED["DOUBLE_SLASH_FORBIDDEN"]


# ---------------------------------------------------------------------------
# 17. /execute가 Phase 1-B 대상에 절대 포함되지 않음
# ---------------------------------------------------------------------------

def test_execute_not_in_phase1b():
    mod = _load()
    paths = [a["legacy_path"] for a in mod.PHASE1B_ADAPTERS]
    assert not any("execute" in p for p in paths)


def test_execute_in_excluded():
    mod = _load()
    assert "/api/v1/tasks/<task_id>/execute" in mod.PHASE1B_EXCLUDED["HOLD_DANGEROUS"]


# ---------------------------------------------------------------------------
# 18. webhook이 Phase 1-B 대상에 절대 포함되지 않음
# ---------------------------------------------------------------------------

def test_webhook_not_in_phase1b():
    mod = _load()
    paths = [a["legacy_path"] for a in mod.PHASE1B_ADAPTERS]
    assert not any("webhook" in p for p in paths)


def test_webhooks_in_excluded():
    mod = _load()
    excluded = mod.PHASE1B_EXCLUDED["DO_NOT_TOUCH"]
    assert any("kakaowork" in p for p in excluded)
    assert any("kakaotalk" in p for p in excluded)


# ---------------------------------------------------------------------------
# 19. SAME_CONTRACT route가 Phase 1-B에 포함되지 않음
# ---------------------------------------------------------------------------

def test_inbox_get_not_in_phase1b():
    mod = _load()
    r = next((a for a in mod.PHASE1B_ADAPTERS
               if a["legacy_path"] == "/api/v1/inbox" and a["legacy_method"] == "GET"), None)
    assert r is None


def test_tasks_post_not_in_phase1b():
    mod = _load()
    r = next((a for a in mod.PHASE1B_ADAPTERS
               if a["legacy_path"] == "/api/v1/tasks" and a["legacy_method"] == "POST"), None)
    assert r is None


def test_same_contract_in_excluded():
    mod = _load()
    same = mod.PHASE1B_EXCLUDED["SAME_CONTRACT"]
    assert "/api/v1/inbox" in same
    assert "/api/v1/tasks" in same


# ---------------------------------------------------------------------------
# 20. 감사 결과 PHASE1B_ADAPTER_CONTRACT_DETAIL_READY
# ---------------------------------------------------------------------------

def test_audit_verdict_phase1b_ready():
    audit = _audit()
    assert audit["verdict"] == "PHASE1B_ADAPTER_CONTRACT_DETAIL_READY"


def test_audit_success_true():
    audit = _audit()
    assert audit["success"] is True


def test_audit_boundary_no_violations():
    audit = _audit()
    assert audit["safe_boundary"]["violations"] == []


# ---------------------------------------------------------------------------
# 21. Phase 1 matrix와 일관성: fetch/approve/reject가 Phase 1에서 COMPATIBLE_WITH_ADAPTER
# ---------------------------------------------------------------------------

def test_phase1b_paths_in_phase1_contracts():
    import importlib.util
    phase1_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1_8400_contract_freeze",
        ROOT / "scripts" / "archive" / "ops" / "audit_5050_phase1_8400_contract_freeze.py"
    )
    phase1_mod = importlib.util.module_from_spec(phase1_spec)
    phase1_spec.loader.exec_module(phase1_mod)

    phase1b_mod = _load()
    phase1_paths = [c["legacy_path"] for c in phase1_mod.PHASE1_CONTRACTS]

    for a in phase1b_mod.PHASE1B_ADAPTERS:
        # Phase 1-B 경로는 Phase 1에 포함되어야 함 (<id> → <task_id> 변환 고려)
        normalized = a["legacy_path"].replace("<id>", "<task_id>")
        assert normalized in phase1_paths, (
            f"{a['legacy_path']} (normalized: {normalized}) not found in Phase 1 contracts"
        )


def test_phase1b_overlap_class_consistent_with_phase1():
    import importlib.util
    phase1_spec = importlib.util.spec_from_file_location(
        "audit_5050_phase1_8400_contract_freeze",
        ROOT / "scripts" / "archive" / "ops" / "audit_5050_phase1_8400_contract_freeze.py"
    )
    phase1_mod = importlib.util.module_from_spec(phase1_spec)
    phase1_spec.loader.exec_module(phase1_mod)

    phase1b_mod = _load()
    for a in phase1b_mod.PHASE1B_ADAPTERS:
        normalized = a["legacy_path"].replace("<id>", "<task_id>")
        phase1_contract = next(
            (c for c in phase1_mod.PHASE1_CONTRACTS if c["legacy_path"] == normalized),
            None,
        )
        assert phase1_contract is not None
        assert phase1_contract["overlap_class"] == "COMPATIBLE_WITH_ADAPTER", (
            f"{a['legacy_path']} must be COMPATIBLE_WITH_ADAPTER in Phase 1"
        )


# ---------------------------------------------------------------------------
# 22. characterization matrix와 일관성
# ---------------------------------------------------------------------------

def test_phase1b_paths_in_characterization():
    import importlib.util
    char_spec = importlib.util.spec_from_file_location(
        "audit_5050_legacy_characterization",
        ROOT / "scripts" / "archive" / "ops" / "audit_5050_legacy_characterization.py"
    )
    char_mod = importlib.util.module_from_spec(char_spec)
    char_spec.loader.exec_module(char_mod)

    phase1b_mod = _load()
    char_paths = [r["path"] for r in char_mod.ROUTE_MATRIX]

    for a in phase1b_mod.PHASE1B_ADAPTERS:
        normalized = a["legacy_path"].replace("<id>", "<task_id>")
        assert normalized in char_paths, (
            f"{a['legacy_path']} (normalized: {normalized}) not found in characterization matrix"
        )
