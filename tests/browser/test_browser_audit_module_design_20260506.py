"""BROWSER_AUDIT_MODULE_DESIGN_1 테스트.

fixture/schema만 검증한다.
실제 브라우저 실행, dispatcher import, task_executor import 금지.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_audit_module_design_20260506.json"

ALLOWED_EVENT_STAGES = {
    "REQUEST_RECEIVED",
    "GATE_EVALUATED",
    "APPROVAL_CHECKED",
    "AUDIT_REQUIRED",
    "AUDIT_READY",
    "DISPATCH_BLOCKED",
    "DISPATCH_ALLOWED_DRY_RUN",
}

ALLOWED_GATE_DECISIONS = {"ALLOW", "BLOCK", "DENY_BY_DEFAULT"}

ALLOWED_BLOCK_REASONS = {
    "AUDIT_CONTEXT_MISSING",
    "SENSITIVE_INPUT_NOT_REDACTED",
    "PRODUCTION_MODE_BLOCKED",
    "TENANT_SCOPE_MISSING",
    "APPROVAL_NOT_APPROVED",
    "GATE_DECISION_NOT_ALLOW",
}

AUDIT_REQUIRED_OPS = {"click", "type", "submit"}


def load_fixture():
    assert FIXTURE_PATH.exists(), f"fixture not found: {FIXTURE_PATH}"
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _case(data, case_id):
    for c in data["cases"]:
        if c["case_id"] == case_id:
            return c
    raise KeyError(f"case not found: {case_id}")


# ── fixture schema 검증 ────────────────────────────────────────────────────


def test_fixture_schema_required_fields():
    """fixture schema 필수 필드 검증."""
    data = load_fixture()
    assert data["fixture_id"] == "BROWSER_AUDIT_MODULE_DESIGN_1"
    assert "audit_event_stages" in data
    assert "operation_audit_requirements" in data
    assert "cases" in data
    assert "safe_to_execute_policy" in data
    assert "sensitive_field_block_patterns" in data


def test_fixture_production_mode_false():
    """fixture 최상위 production_mode=false."""
    data = load_fixture()
    assert data["production_mode"] is False


def test_fixture_safe_to_execute_false():
    """fixture 최상위 safe_to_execute=false."""
    data = load_fixture()
    assert data["safe_to_execute"] is False


def test_fixture_dispatcher_not_connected():
    """dispatcher_connected=false."""
    data = load_fixture()
    assert data["dispatcher_connected"] is False


def test_fixture_task_executor_not_connected():
    """task_executor_connected=false."""
    data = load_fixture()
    assert data["task_executor_connected"] is False


# ── audit_event_stages 검증 ───────────────────────────────────────────────


def test_audit_event_stages_enum():
    """audit_event_stages 목록이 허용 enum과 일치."""
    data = load_fixture()
    assert set(data["audit_event_stages"]) == ALLOWED_EVENT_STAGES


def test_all_case_event_stages_valid():
    """모든 케이스의 expected event_stage가 허용 enum 안에 있다."""
    data = load_fixture()
    for c in data["cases"]:
        exp = c["expected"]
        if "event_stage" in exp:
            es = exp["event_stage"]
            assert es in ALLOWED_EVENT_STAGES, f"{c['case_id']}: invalid event_stage={es!r}"


def test_all_case_event_stages_order_valid():
    """event_stages_order가 있는 케이스의 각 단계가 허용 enum 안에 있다."""
    data = load_fixture()
    for c in data["cases"]:
        for es in c["expected"].get("event_stages_order", []):
            assert es in ALLOWED_EVENT_STAGES, f"{c['case_id']}: invalid stage in order={es!r}"


# ── operation_audit_requirements 검증 ────────────────────────────────────


def test_click_audit_required():
    """click은 audit_required=true."""
    data = load_fixture()
    assert data["operation_audit_requirements"]["click"]["audit_required"] is True


def test_type_audit_required():
    """type은 audit_required=true."""
    data = load_fixture()
    assert data["operation_audit_requirements"]["type"]["audit_required"] is True


def test_submit_audit_required():
    """submit은 audit_required=true."""
    data = load_fixture()
    assert data["operation_audit_requirements"]["submit"]["audit_required"] is True


def test_read_audit_not_required():
    """read는 audit_required=false."""
    data = load_fixture()
    assert data["operation_audit_requirements"]["read"]["audit_required"] is False


def test_navigate_audit_not_required():
    """navigate는 audit_required=false."""
    data = load_fixture()
    assert data["operation_audit_requirements"]["navigate"]["audit_required"] is False


def test_click_type_submit_approval_required():
    """click/type/submit은 approval_required=true."""
    data = load_fixture()
    req = data["operation_audit_requirements"]
    for op in ["click", "type", "submit"]:
        assert req[op]["approval_required"] is True, f"{op}: approval_required must be True"


# ── 차단 케이스 검증 ──────────────────────────────────────────────────────


def test_submit_deny_by_default_blocked():
    """gate_decision=DENY_BY_DEFAULT → dispatch_blocked=true."""
    data = load_fixture()
    c = _case(data, "audit_block_submit_deny_by_default")
    assert c["input"]["gate_decision"] == "DENY_BY_DEFAULT"
    assert c["expected"]["dispatch_blocked"] is True
    assert c["expected"]["event_stage"] == "DISPATCH_BLOCKED"


def test_audit_context_missing_blocked():
    """audit_required=true + audit_context 비어 있음 → DISPATCH_BLOCKED."""
    data = load_fixture()
    c = _case(data, "audit_block_audit_context_missing")
    assert c["input"]["audit_required"] is True
    assert c["input"]["audit_context"] == ""
    assert c["expected"]["dispatch_blocked"] is True
    assert c["expected"]["block_reason"] == "AUDIT_CONTEXT_MISSING"


def test_sensitive_not_redacted_blocked():
    """sensitive_input_present=true + raw_input_redacted=false → DISPATCH_BLOCKED."""
    data = load_fixture()
    c = _case(data, "audit_block_sensitive_not_redacted")
    assert c["input"]["sensitive_input_present"] is True
    assert c["input"]["raw_input_redacted"] is False
    assert c["expected"]["dispatch_blocked"] is True
    assert c["expected"]["block_reason"] == "SENSITIVE_INPUT_NOT_REDACTED"


def test_production_mode_blocked():
    """production_mode=true → DISPATCH_BLOCKED."""
    data = load_fixture()
    c = _case(data, "audit_block_production_mode_true")
    assert c["input"]["production_mode"] is True
    assert c["expected"]["dispatch_blocked"] is True
    assert c["expected"]["block_reason"] == "PRODUCTION_MODE_BLOCKED"


def test_tenant_scope_missing_blocked():
    """tenant_scope 비어 있음 → DISPATCH_BLOCKED."""
    data = load_fixture()
    c = _case(data, "audit_block_tenant_scope_missing")
    assert c["input"]["tenant_scope"] == ""
    assert c["expected"]["dispatch_blocked"] is True
    assert c["expected"]["block_reason"] == "TENANT_SCOPE_MISSING"


def test_approval_not_approved_blocked():
    """approval_status != approved → DISPATCH_BLOCKED."""
    data = load_fixture()
    c = _case(data, "audit_block_approval_not_approved")
    assert c["input"]["approval_status"] != "approved"
    assert c["expected"]["dispatch_blocked"] is True
    assert c["expected"]["block_reason"] == "APPROVAL_NOT_APPROVED"


def test_gate_decision_block_blocked():
    """gate_decision=BLOCK → DISPATCH_BLOCKED."""
    data = load_fixture()
    c = _case(data, "audit_block_gate_decision_block")
    assert c["input"]["gate_decision"] == "BLOCK"
    assert c["expected"]["dispatch_blocked"] is True
    assert c["expected"]["block_reason"] == "GATE_DECISION_NOT_ALLOW"


# ── 통과 케이스 검증 ──────────────────────────────────────────────────────


def test_click_full_pass_dispatch_allowed():
    """click 전체 통과 → DISPATCH_ALLOWED_DRY_RUN."""
    data = load_fixture()
    c = _case(data, "audit_ready_click_full_pass")
    assert c["expected"]["event_stage"] == "DISPATCH_ALLOWED_DRY_RUN"
    assert c["expected"]["audit_pass"] is True
    assert c["expected"]["dispatch_blocked"] is False


def test_type_full_pass_dispatch_allowed():
    """type 전체 통과 → DISPATCH_ALLOWED_DRY_RUN."""
    data = load_fixture()
    c = _case(data, "audit_ready_type_full_pass")
    assert c["expected"]["event_stage"] == "DISPATCH_ALLOWED_DRY_RUN"
    assert c["expected"]["audit_pass"] is True
    assert c["expected"]["dispatch_blocked"] is False


def test_read_no_audit_required_pass():
    """read는 audit 불필요 → DISPATCH_ALLOWED_DRY_RUN."""
    data = load_fixture()
    c = _case(data, "audit_read_no_audit_required")
    assert c["input"]["audit_required"] is False
    assert c["expected"]["audit_pass"] is True
    assert c["expected"]["dispatch_blocked"] is False


def test_sensitive_redacted_pass():
    """sensitive_input=true + redacted=true → 통과."""
    data = load_fixture()
    c = _case(data, "audit_sensitive_redacted_pass")
    assert c["input"]["sensitive_input_present"] is True
    assert c["input"]["raw_input_redacted"] is True
    assert c["expected"]["audit_pass"] is True
    assert c["expected"]["dispatch_blocked"] is False


# ── safe_to_execute 항상 false ────────────────────────────────────────────


def test_safe_to_execute_never_true_in_any_case():
    """이번 단계 어떤 케이스에서도 safe_to_execute=true이면 FAIL."""
    data = load_fixture()
    for c in data["cases"]:
        assert c["expected"].get("safe_to_execute") is False, (
            f"{c['case_id']}: safe_to_execute must be False this stage"
        )


def test_safe_to_execute_policy_not_allowed():
    """safe_to_execute_policy.safe_to_execute_allowed=false."""
    data = load_fixture()
    assert data["safe_to_execute_policy"]["safe_to_execute_allowed"] is False


# ── event_stages_order 검증 ───────────────────────────────────────────────


def test_event_stages_order_click_full_pass():
    """click full pass 케이스 event_stages_order에 최소 4개 단계 포함."""
    data = load_fixture()
    c = _case(data, "audit_event_stages_complete")
    order = c["expected"]["event_stages_order"]
    assert len(order) >= 4, f"Expected at least 4 stages, got {len(order)}"
    assert order[0] == "REQUEST_RECEIVED"
    assert order[-1] == "DISPATCH_ALLOWED_DRY_RUN"


def test_event_stages_order_contains_gate_evaluated():
    """event_stages_order에 GATE_EVALUATED 포함."""
    data = load_fixture()
    c = _case(data, "audit_event_stages_complete")
    assert "GATE_EVALUATED" in c["expected"]["event_stages_order"]


def test_event_stages_order_contains_audit_ready():
    """DISPATCH_ALLOWED_DRY_RUN 전에 AUDIT_READY 또는 APPROVAL_CHECKED 포함."""
    data = load_fixture()
    c = _case(data, "audit_event_stages_complete")
    order = c["expected"]["event_stages_order"]
    assert any(s in order for s in ["AUDIT_READY", "APPROVAL_CHECKED"])


# ── sensitive_field_block_patterns 검증 ──────────────────────────────────


def test_sensitive_field_patterns_include_password():
    """sensitive_field_block_patterns에 password 포함."""
    data = load_fixture()
    assert "password" in data["sensitive_field_block_patterns"]


def test_sensitive_field_patterns_include_token():
    """sensitive_field_block_patterns에 token 포함."""
    data = load_fixture()
    assert "token" in data["sensitive_field_block_patterns"]


def test_sensitive_field_patterns_include_secret():
    """sensitive_field_block_patterns에 secret 포함."""
    data = load_fixture()
    assert "secret" in data["sensitive_field_block_patterns"]


# ── block_reason 허용값 검증 ──────────────────────────────────────────────


def test_all_case_block_reasons_valid():
    """모든 케이스의 block_reason이 허용 enum 안에 있다."""
    data = load_fixture()
    for c in data["cases"]:
        br = c["expected"].get("block_reason")
        if br is not None:
            assert br in ALLOWED_BLOCK_REASONS, f"{c['case_id']}: invalid block_reason={br!r}"


# ── 기존 gate/allowlist fixture와의 연계 검증 ─────────────────────────────


def test_gate_fixture_gate_decisions_compatible():
    """기존 gate fixture의 gate_decisions가 audit 설계와 호환된다."""
    gate_fixture = Path(__file__).parent.parent / "fixtures" / "browser_gate_module_design_20260506.json"
    assert gate_fixture.exists(), "gate module fixture not found"
    with gate_fixture.open(encoding="utf-8") as f:
        g = json.load(f)
    assert set(g["gate_decisions"]) == ALLOWED_GATE_DECISIONS


def test_allowlist_fixture_submit_deny_by_default():
    """기존 allowlist fixture의 submit=DENY_BY_DEFAULT 유지."""
    allowlist = Path(__file__).parent.parent / "fixtures" / "browser_allowlist_policy_20260506.json"
    assert allowlist.exists(), "allowlist fixture not found"
    with allowlist.open(encoding="utf-8") as f:
        a = json.load(f)
    assert a["default_verdicts"]["submit"] == "DENY_BY_DEFAULT"


def test_untracked_preflight_md_not_deleted():
    """BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md untracked 유지 (삭제 금지)."""
    preflight = Path(__file__).parents[2] / "BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md"
    if not preflight.exists():
        pytest.skip("WARN: BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md not found")
    assert preflight.is_file()


# ── 실제 브라우저/dispatcher import 없음 ─────────────────────────────────


def test_no_browser_import_in_this_module():
    """이 테스트 파일 자체가 실제 브라우저/dispatcher를 직접 import하지 않는다."""
    import ast

    src = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    blocked = {"playwright", "browser_worker", "ai_orchestrator.browser_tool.worker", "dispatcher", "task_executor"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            for name in names:
                if name:
                    for b in blocked:
                        assert not name.startswith(b), f"이 파일이 직접 import: {name}"


def test_no_task_executor_import():
    """이 테스트 파일 자체가 task_executor / browser_worker를 직접 import하지 않는다."""
    import ast

    src = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    blocked = {"task_executor", "browser_worker", "ai_orchestrator.browser_tool.worker"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            for name in names:
                if name:
                    for b in blocked:
                        assert not name.startswith(b), f"이 파일이 직접 import: {name}"


# ── 최소 케이스 수 검증 ───────────────────────────────────────────────────


def test_fixture_min_case_count():
    """fixture에 최소 10개 이상의 케이스가 있다."""
    data = load_fixture()
    assert len(data["cases"]) >= 10, f"Expected at least 10 cases, got {len(data['cases'])}"


def test_all_cases_have_action_name():
    """모든 케이스에 action_name이 있다."""
    data = load_fixture()
    for c in data["cases"]:
        assert "action_name" in c["input"], f"{c['case_id']}: action_name missing"
        assert c["input"]["action_name"], f"{c['case_id']}: action_name empty"


def test_all_cases_have_operation_type():
    """모든 케이스에 operation_type이 있다."""
    data = load_fixture()
    allowed_ops = {"read", "navigate", "open_url", "click", "type", "submit"}
    for c in data["cases"]:
        ot = c["input"].get("operation_type")
        assert ot in allowed_ops, f"{c['case_id']}: invalid operation_type={ot!r}"


def test_all_cases_have_gate_decision_input():
    """모든 케이스의 input에 gate_decision이 있다."""
    data = load_fixture()
    for c in data["cases"]:
        gd = c["input"].get("gate_decision")
        assert gd in ALLOWED_GATE_DECISIONS, f"{c['case_id']}: invalid input gate_decision={gd!r}"
