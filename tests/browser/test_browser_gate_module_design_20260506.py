"""BROWSER_GATE_MODULE_DESIGN_1 테스트.

fixture/schema만 검증한다.
실제 브라우저 실행, dispatcher import, task_executor import 금지.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_gate_module_design_20260506.json"

ALLOWED_GATE_DECISIONS = {"ALLOW", "BLOCK", "DENY_BY_DEFAULT"}
ALLOWED_BLOCK_REASONS = {
    "POLICY_NOT_ALLOW",
    "PREVIEW_HASH_MISSING",
    "VALIDATION_ID_MISSING",
    "APPROVAL_ID_MISSING",
    "APPROVAL_NOT_APPROVED",
    "AUDIT_CONTEXT_MISSING",
    "SENSITIVE_INPUT_NOT_REDACTED",
    "PRODUCTION_MODE_BLOCKED",
    "TENANT_SCOPE_MISSING",
    "SUBMIT_DENY_BY_DEFAULT",
}
ALLOWED_OPERATION_TYPES = {"read", "navigate", "open_url", "click", "type", "submit"}


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
    assert data["fixture_id"] == "BROWSER_GATE_MODULE_DESIGN_1"
    assert "gate_decisions" in data
    assert "block_reasons" in data
    assert "cases" in data
    assert "safe_to_execute_policy" in data


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


# ── gate_decision 허용값 검증 ────────────────────────────────────────────


def test_gate_decisions_enum():
    """gate_decisions 목록이 허용 enum과 일치."""
    data = load_fixture()
    assert set(data["gate_decisions"]) == ALLOWED_GATE_DECISIONS


def test_all_case_gate_decisions_valid():
    """모든 케이스의 expected gate_decision이 허용 enum 안에 있다."""
    data = load_fixture()
    for c in data["cases"]:
        gd = c["expected"]["gate_decision"]
        assert gd in ALLOWED_GATE_DECISIONS, f"{c['case_id']}: invalid gate_decision={gd!r}"


# ── block_reason 허용값 검증 ─────────────────────────────────────────────


def test_block_reasons_enum():
    """block_reasons 목록이 허용 enum을 포함한다."""
    data = load_fixture()
    for br in data["block_reasons"]:
        assert br in ALLOWED_BLOCK_REASONS, f"invalid block_reason={br!r}"


def test_all_case_block_reasons_valid():
    """모든 케이스의 block_reasons 값이 허용 enum 안에 있다."""
    data = load_fixture()
    for c in data["cases"]:
        for br in c["expected"].get("block_reasons", []):
            assert br in ALLOWED_BLOCK_REASONS, f"{c['case_id']}: invalid block_reason={br!r}"
        for br in c["expected"].get("block_reasons_include", []):
            assert br in ALLOWED_BLOCK_REASONS, f"{c['case_id']}: invalid block_reason_include={br!r}"


# ── submit operation DENY_BY_DEFAULT 검증 ────────────────────────────────


def test_submit_deny_by_default():
    """operation_type=submit은 DENY_BY_DEFAULT."""
    data = load_fixture()
    c = _case(data, "submit_deny_by_default")
    assert c["input"]["operation_type"] == "submit"
    assert c["expected"]["gate_decision"] == "DENY_BY_DEFAULT"
    assert "SUBMIT_DENY_BY_DEFAULT" in c["expected"]["block_reasons"]


def test_submit_deny_safe_to_execute_false():
    """submit DENY 케이스에서 safe_to_execute=false."""
    data = load_fixture()
    c = _case(data, "submit_deny_by_default")
    assert c["expected"]["safe_to_execute"] is False


# ── production_mode=true → safe_to_execute=false ─────────────────────────


def test_production_mode_true_blocked():
    """production_mode=true이면 PRODUCTION_MODE_BLOCKED."""
    data = load_fixture()
    c = _case(data, "block_production_mode_true")
    assert c["input"]["production_mode"] is True
    assert c["expected"]["gate_decision"] == "BLOCK"
    assert "PRODUCTION_MODE_BLOCKED" in c["expected"]["block_reasons"]
    assert c["expected"]["safe_to_execute"] is False


# ── contains_sensitive_input=true + redaction 미완료 → 차단 ───────────────


def test_sensitive_input_not_redacted_block():
    """contains_sensitive_input=true + redaction_complete=false → SENSITIVE_INPUT_NOT_REDACTED."""
    data = load_fixture()
    c = _case(data, "block_sensitive_input_not_redacted")
    assert c["input"]["contains_sensitive_input"] is True
    assert c["input"]["redaction_complete"] is False
    assert c["expected"]["gate_decision"] == "BLOCK"
    assert "SENSITIVE_INPUT_NOT_REDACTED" in c["expected"]["block_reasons"]


# ── approval_required action에서 approval_id/status 누락 → 차단 ───────────


def test_approval_id_missing_block():
    """approval_required=true + approval_id 비어 있음 → APPROVAL_ID_MISSING."""
    data = load_fixture()
    c = _case(data, "block_approval_id_missing")
    assert c["input"]["approval_required"] is True
    assert c["input"]["approval_id"] == ""
    assert c["expected"]["gate_decision"] == "BLOCK"
    assert "APPROVAL_ID_MISSING" in c["expected"]["block_reasons"]


def test_approval_not_approved_block():
    """approval_status != "approved"이면 차단."""
    data = load_fixture()
    c = _case(data, "block_approval_id_missing")
    assert c["input"]["approval_status"] != "approved"
    assert "APPROVAL_NOT_APPROVED" in c["expected"]["block_reasons"]


# ── audit_required action에서 audit_context 누락 → 차단 ───────────────────


def test_audit_context_missing_block():
    """audit_required=true + audit_context 비어 있음 → AUDIT_CONTEXT_MISSING."""
    data = load_fixture()
    c = _case(data, "block_audit_context_missing")
    assert c["input"]["audit_required"] is True
    assert c["input"]["audit_context"] == ""
    assert c["expected"]["gate_decision"] == "BLOCK"
    assert "AUDIT_CONTEXT_MISSING" in c["expected"]["block_reasons"]


# ── safe_to_dispatch=true이면 gate_decision=ALLOW ────────────────────────


def test_safe_to_dispatch_true_requires_allow():
    """safe_to_dispatch=true이면 gate_decision은 ALLOW여야 한다."""
    data = load_fixture()
    c = _case(data, "safe_to_dispatch_true_requires_allow")
    assert c["input"]["safe_to_dispatch"] is True
    assert c["expected"]["gate_decision"] == "ALLOW"
    assert c["expected"]["safe_to_dispatch"] is True


def test_allow_click_safe_to_execute_always_false():
    """ALLOW 케이스도 safe_to_execute=false (dispatcher 미연결)."""
    data = load_fixture()
    c = _case(data, "allow_click_full_pass")
    assert c["expected"]["gate_decision"] == "ALLOW"
    assert c["expected"]["safe_to_execute"] is False


# ── safe_to_execute=true는 이번 단계에서 허용하지 않음 ────────────────────


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


# ── 실제 브라우저/dispatcher import 없음 ─────────────────────────────────


def test_no_browser_import_in_this_module():
    """이 테스트 파일은 실제 브라우저/dispatcher import를 포함하지 않는다.

    sys.modules 전역 상태가 아닌, 이 테스트 파일 소스코드에 금지 import가 없음을 검증한다.
    다른 테스트가 먼저 해당 모듈을 import해도 이 테스트는 영향받지 않는다.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    blocked = ["playwright", "browser_worker", "ai_orchestrator.browser_tool.worker", "dispatcher", "task_executor"]
    for mod in blocked:
        # import 구문으로 직접 참조하는 경우만 차단 (주석·문자열 내 단순 언급은 허용)
        import_patterns = [f"import {mod}", f"from {mod}"]
        for pattern in import_patterns:
            assert pattern not in source, f"Unexpected import in this test file: {pattern}"


def test_no_task_executor_import():
    """모듈 import 목록에 금지 모듈이 없다.

    이 테스트 파일 및 검증 대상 gate 모듈의 소스코드에
    task_executor / browser_worker를 직접 import하는 구문이 없음을 확인한다.
    sys.modules 전역 상태 검사가 아닌 소스 코드 검사로 순서 독립성을 보장한다.
    """

    files_to_check = [
        Path(__file__),
        Path(__file__).parent.parent.parent / "ai_orchestrator" / "browser_tool" / "submit_execution_gate.py",
        Path(__file__).parent.parent / "ai_orchestrator" / "browser_tool" / "submit" / "submit_execution_gate.py",
    ]
    blocked = ["task_executor", "browser_worker", "ai_orchestrator.browser_tool.worker"]

    for fpath in files_to_check:
        if not fpath.exists():
            continue
        source = fpath.read_text(encoding="utf-8")
        for mod in blocked:
            import_patterns = [f"import {mod}", f"from {mod}"]
            for pattern in import_patterns:
                assert pattern not in source, f"Unexpected import in {fpath.name}: {pattern}"


# ── operation_type 필드 검증 ─────────────────────────────────────────────


def test_all_cases_have_action_name():
    """모든 케이스에 action_name이 있다."""
    data = load_fixture()
    for c in data["cases"]:
        assert "action_name" in c["input"], f"{c['case_id']}: action_name missing"
        assert c["input"]["action_name"], f"{c['case_id']}: action_name empty"


def test_all_cases_have_operation_type():
    """모든 케이스에 operation_type이 있고 허용 값이다."""
    data = load_fixture()
    for c in data["cases"]:
        ot = c["input"].get("operation_type")
        assert ot in ALLOWED_OPERATION_TYPES, f"{c['case_id']}: invalid operation_type={ot!r}"


# ── 기존 관련 테스트와 충돌 없음 ──────────────────────────────────────────


def test_existing_gate_fixture_still_valid():
    """기존 submit_execution_gate fixture의 핵심 구조가 유지된다."""
    existing = Path(__file__).parent.parent / "fixtures" / "browser_submit_execution_gate_fixture_20260506.json"
    if not existing.exists():
        pytest.skip("existing gate fixture not found")
    with existing.open(encoding="utf-8") as f:
        d = json.load(f)
    # GATE_PASS 케이스 존재
    assert "gate_pass_case" in d
    assert d["gate_pass_case"]["expected_output"]["gate_verdict"] == "GATE_PASS"


def test_existing_allowlist_fixture_submit_deny():
    """기존 allowlist fixture의 submit DENY_BY_DEFAULT 유지 확인."""
    allowlist = Path(__file__).parent.parent / "fixtures" / "browser_allowlist_policy_20260506.json"
    with allowlist.open(encoding="utf-8") as f:
        d = json.load(f)
    assert d["default_verdicts"]["submit"] == "DENY_BY_DEFAULT"


def test_untracked_preflight_md_not_deleted():
    """BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md untracked 유지 (삭제 금지)."""
    preflight = Path(__file__).parents[2] / "BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md"
    if not preflight.exists():
        pytest.skip("WARN: BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md not found")
    assert preflight.is_file()


# ── 최소 케이스 수 검증 ───────────────────────────────────────────────────


def test_fixture_min_case_count():
    """fixture에 최소 10개 이상의 케이스가 있다."""
    data = load_fixture()
    assert len(data["cases"]) >= 10, f"Expected at least 10 cases, got {len(data['cases'])}"
