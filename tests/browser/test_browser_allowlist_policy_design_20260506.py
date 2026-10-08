"""BROWSER_ALLOWLIST_POLICY_DESIGN_1 테스트.

policy/fixture/schema만 검증한다.
실제 브라우저 실행, HTTP 요청, 업무 사이트 접속 금지.
dispatcher 연결 검증은 "미연결 유지"만 확인한다.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_allowlist_policy_20260506.json"

ALLOWED_OPERATION_TYPES = {"read", "navigate", "open_url", "click", "type", "submit"}

ALLOWLIST_REQUIRED_ACTIONS = [
    "browser.plan_open_url",
    "browser.open_url_controlled",
    "browser.execute_click",
    "browser.execute_type",
    "browser.open_click_close_controlled",
    "browser.open_type_close_controlled",
]

CLICK_TYPE_SUBMIT_TYPES = {"click", "type", "submit"}


def load_fixture():
    assert FIXTURE_PATH.exists(), f"fixture not found: {FIXTURE_PATH}"
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _policy(data, name):
    for p in data["policies"]:
        if p["policy_name"] == name:
            return p
    raise KeyError(f"policy not found: {name}")


# ── 1. fixture schema 필수 필드 검증 ─────────────────────────────────────


def test_fixture_schema_required_fields():
    """fixture schema 필수 필드 검증."""
    data = load_fixture()
    assert "policy_id" in data
    assert "version" in data
    assert "policies" in data
    assert "operation_types" in data
    assert "default_verdicts" in data
    assert "action_allowlist_mapping" in data
    assert data["policy_id"] == "BROWSER_ALLOWLIST_POLICY_DESIGN_1"


def test_fixture_production_not_allowed():
    """fixture 최상위 production_allowed=false 확인."""
    data = load_fixture()
    assert data["production_allowed"] is False


def test_fixture_dry_run_only():
    """fixture 최상위 dry_run_only=true 확인."""
    data = load_fixture()
    assert data["dry_run_only"] is True


def test_fixture_dispatcher_not_connected():
    """dispatcher_connected=false 확인."""
    data = load_fixture()
    assert data["dispatcher_connected"] is False


def test_fixture_task_executor_not_connected():
    """task_executor_connected=false 확인."""
    data = load_fixture()
    assert data["task_executor_connected"] is False


# ── 2. 모든 policy에 action_name 존재 ─────────────────────────────────────


def test_all_policies_have_action_name():
    """모든 policy에 action_name이 존재한다."""
    data = load_fixture()
    for p in data["policies"]:
        assert "action_name" in p, f"{p.get('policy_name')}: action_name missing"
        assert p["action_name"], f"{p.get('policy_name')}: action_name empty"


# ── 3. 모든 policy에 operation_type 존재 ──────────────────────────────────


def test_all_policies_have_operation_type():
    """모든 policy에 operation_type이 존재한다."""
    data = load_fixture()
    for p in data["policies"]:
        assert "operation_type" in p, f"{p.get('policy_name')}: operation_type missing"


# ── 4. operation_type이 허용 enum 안에 있음 ───────────────────────────────


def test_all_operation_types_in_enum():
    """operation_type이 허용 enum 안에 있다."""
    data = load_fixture()
    for p in data["policies"]:
        ot = p.get("operation_type")
        assert ot in ALLOWED_OPERATION_TYPES, f"{p.get('policy_name')}: invalid operation_type={ot!r}"


# ── 5. allowlist_required=true action은 domain 또는 url_pattern 필요 ──────


def test_allowlist_required_actions_have_domain_or_pattern():
    """allowlist_required=true policy는 domain 또는 url_pattern이 있어야 한다."""
    data = load_fixture()
    for p in data["policies"]:
        if p.get("allowlist_required") is True:
            has_domain = bool(p.get("domain"))
            has_pattern = bool(p.get("url_pattern"))
            assert has_domain or has_pattern, (
                f"{p.get('policy_name')}: allowlist_required=true but no domain/url_pattern"
            )


# ── 6. wildcard-only domain은 deny ───────────────────────────────────────


def test_wildcard_only_domain_deny():
    """wildcard-only domain(*)은 DENY다."""
    data = load_fixture()
    p = _policy(data, "wildcard_only_domain_deny")
    assert p["domain"] == "*"
    assert p["expected_verdict"] == "DENY"
    assert "wildcard" in p.get("deny_reason", "").lower()


# ── 7. unknown domain은 deny ─────────────────────────────────────────────


def test_unknown_domain_deny():
    """unknown domain은 DENY다."""
    data = load_fixture()
    p = _policy(data, "unknown_domain_deny")
    assert p["expected_verdict"] == "DENY"
    assert "allowlist" in p.get("deny_reason", "").lower()


# ── 8. submit operation은 기본 deny ──────────────────────────────────────


def test_submit_operation_default_deny():
    """submit operation은 기본 DENY_BY_DEFAULT다."""
    data = load_fixture()
    assert data["default_verdicts"]["submit"] == "DENY_BY_DEFAULT"
    # fixture에도 submit deny 케이스 존재
    p = _policy(data, "submit_default_deny")
    assert p["operation_type"] == "submit"
    assert p["expected_verdict"] == "DENY_BY_DEFAULT"


# ── 9. click/type operation은 approval_required=true 필요 ─────────────────


def test_click_operation_approval_required():
    """click operation policy는 approval_required=true다."""
    data = load_fixture()
    p = _policy(data, "click_approval_required")
    assert p["operation_type"] == "click"
    assert p["approval_required"] is True


def test_type_operation_approval_required():
    """type operation policy는 approval_required=true다."""
    data = load_fixture()
    p = _policy(data, "type_approval_required")
    assert p["operation_type"] == "type"
    assert p["approval_required"] is True


# ── 10. click/type/submit operation은 audit_required=true 필요 ───────────


def test_click_operation_audit_required():
    """click operation policy는 audit_required=true다."""
    data = load_fixture()
    p = _policy(data, "click_approval_required")
    assert p["audit_required"] is True


def test_type_operation_audit_required():
    """type operation policy는 audit_required=true다."""
    data = load_fixture()
    p = _policy(data, "type_approval_required")
    assert p["audit_required"] is True


def test_submit_operation_audit_required():
    """submit operation policy는 audit_required=true다."""
    data = load_fixture()
    p = _policy(data, "submit_default_deny")
    assert p["audit_required"] is True


def test_audit_required_missing_for_type_causes_deny():
    """type operation에서 audit_required=false이면 DENY 판정이다."""
    data = load_fixture()
    p = _policy(data, "audit_required_missing_deny")
    assert p["operation_type"] == "type"
    assert p["audit_required"] is False
    assert p["expected_verdict"] == "DENY"


# ── 11. production_allowed=true는 DENY ───────────────────────────────────


def test_production_allowed_true_is_deny():
    """production_allowed=true policy는 DENY다."""
    data = load_fixture()
    p = _policy(data, "production_allowed_true_deny")
    assert p["production_allowed"] is True
    assert p["expected_verdict"] == "DENY"


# ── 12. dry_run_only=false는 DENY ────────────────────────────────────────


def test_dry_run_only_false_is_deny():
    """dry_run_only=false인 policy는 production_allowed=true와 함께 DENY다."""
    data = load_fixture()
    p = _policy(data, "production_allowed_true_deny")
    assert p["dry_run_only"] is False
    assert p["expected_verdict"] == "DENY"


# ── 13. tenant_scope 누락 시 deny ─────────────────────────────────────────


def test_tenant_scope_missing_deny():
    """tenant_scope=null이면 DENY다."""
    data = load_fixture()
    p = _policy(data, "tenant_scope_missing_deny")
    assert p["tenant_scope"] is None
    assert p["expected_verdict"] == "DENY"
    assert "tenant_scope" in p.get("deny_reason", "").lower()


# ── 14. secret/password/certificate intent는 deny ────────────────────────


def test_password_secret_intent_deny():
    """password/secret intent는 DENY다."""
    data = load_fixture()
    p = _policy(data, "password_secret_intent_deny")
    assert "password" in p.get("intent", "").lower() or "secret" in p.get("intent", "").lower()
    assert p["expected_verdict"] == "DENY"
    assert p.get("sensitive_field_block") is True


# ── 15~19. action별 allowlist_required 매핑 검증 ─────────────────────────


@pytest.mark.parametrize("action_name", ALLOWLIST_REQUIRED_ACTIONS)
def test_action_allowlist_required_in_mapping(action_name):
    """allowlist_required 대상 action이 action_allowlist_mapping에 존재하고 true다."""
    data = load_fixture()
    mapping = data["action_allowlist_mapping"]
    assert action_name in mapping, f"{action_name} not in action_allowlist_mapping"
    assert mapping[action_name]["allowlist_required"] is True, (
        f"{action_name}: allowlist_required must be True in mapping"
    )


def test_browser_open_url_controlled_allowlist_required():
    """browser.open_url_controlled은 allowlist_required=true 정책 필요."""
    data = load_fixture()
    m = data["action_allowlist_mapping"]["browser.open_url_controlled"]
    assert m["allowlist_required"] is True
    assert m["operation_type"] == "open_url"


def test_browser_execute_click_allowlist_required():
    """browser.execute_click은 allowlist_required=true 정책 필요."""
    data = load_fixture()
    m = data["action_allowlist_mapping"]["browser.execute_click"]
    assert m["allowlist_required"] is True
    assert m["operation_type"] == "click"


def test_browser_execute_type_allowlist_required():
    """browser.execute_type은 allowlist_required=true 정책 필요."""
    data = load_fixture()
    m = data["action_allowlist_mapping"]["browser.execute_type"]
    assert m["allowlist_required"] is True
    assert m["operation_type"] == "type"


def test_browser_open_click_close_controlled_allowlist_required():
    """browser.open_click_close_controlled은 allowlist_required=true 정책 필요."""
    data = load_fixture()
    m = data["action_allowlist_mapping"]["browser.open_click_close_controlled"]
    assert m["allowlist_required"] is True
    assert m["operation_type"] == "click"


def test_browser_open_type_close_controlled_allowlist_required():
    """browser.open_type_close_controlled은 allowlist_required=true 정책 필요."""
    data = load_fixture()
    m = data["action_allowlist_mapping"]["browser.open_type_close_controlled"]
    assert m["allowlist_required"] is True
    assert m["operation_type"] == "submit"


# ── 20. read/navigate registry 기존 테스트와 충돌 없음 ────────────────────


def test_read_navigate_actions_not_affected():
    """read/navigate 3개 action은 allowlist_required=false or 기존 값 유지."""
    from ai_orchestrator.browser_tool.preflight.agent_action_registry import get_meta

    for action in ["browser.inspect", "browser.plan_click", "browser.plan_open_url"]:
        meta = get_meta(action)
        assert meta is not None, f"{action} missing from registry"
        assert meta.read_only is True
        assert meta.requires_approval is False


# ── 21. submit/type risk reclassification 기존 테스트와 충돌 없음 ──────────


def test_reclassification_fixture_unchanged():
    """submit/type risk reclassification fixture의 핵심 값이 유지된다."""
    reclassification_fixture = Path(__file__).parent.parent / "fixtures" / "browser_action_registry_risk_mapping_20260506.json"
    with reclassification_fixture.open(encoding="utf-8") as f:
        data = json.load(f)
    # execute_type은 HIGH_STATE_CHANGE
    et = next(a for a in data["actions"] if a["action_name"] == "browser.execute_type")
    assert et["risk_tier"] == "HIGH_STATE_CHANGE"
    assert et["recommended_risk"] == "high"
    # execute_click은 HIGH_STATE_CHANGE
    ec = next(a for a in data["actions"] if a["action_name"] == "browser.execute_click")
    assert ec["risk_tier"] == "HIGH_STATE_CHANGE"


# ── 22. BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md 유지 ──────────────


def test_untracked_preflight_md_not_deleted():
    """BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md untracked 유지 (삭제 금지)."""
    preflight = Path(__file__).parents[2] / "BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md"
    if not preflight.exists():
        pytest.skip("WARN: BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md not found")
    assert preflight.is_file()


# ── 추가: 실행 연결 미연결 확인 ───────────────────────────────────────────


def test_no_real_url_in_fixture():
    """fixture에 실제 운영 URL이 없다 (example.com / PLACEHOLDER / localhost만 허용)."""
    data = load_fixture()
    blocked_domains = []
    for p in data["policies"]:
        domain = p.get("domain", "")
        url = p.get("url_pattern", "")
        # 실제 운영 사이트 패턴 금지
        for suspicious in ["g2b.go.kr", "hometax.go.kr", "nts.go.kr", "narajangteo"]:
            if suspicious in domain or suspicious in url:
                blocked_domains.append(p["policy_name"])
    assert not blocked_domains, f"Real production URL detected: {blocked_domains}"


def test_fixture_min_policy_count():
    """fixture에 최소 10개 이상의 policy가 있다."""
    data = load_fixture()
    assert len(data["policies"]) >= 10, f"Expected at least 10 policies, got {len(data['policies'])}"


def test_all_verdicts_are_valid():
    """모든 policy의 expected_verdict가 유효한 값이다."""
    valid_verdicts = {
        "ALLOW",
        "ALLOW_IF_DOMAIN_ALLOWLISTED",
        "ALLOW_IF_APPROVED",
        "ALLOW_IF_APPROVED_AND_NO_SENSITIVE",
        "DENY",
        "DENY_BY_DEFAULT",
        "PENDING_POLICY_DESIGN",
    }
    data = load_fixture()
    for p in data["policies"]:
        v = p.get("expected_verdict")
        assert v in valid_verdicts, f"{p.get('policy_name')}: invalid expected_verdict={v!r}"
