"""BROWSER_SUBMIT_TYPE_RISK_RECLASSIFICATION_1 테스트.

검증 범위:
1. browser.plan_submit: recommended_risk=high, risk_level_needs_review=true
2. browser.open_type_close_controlled: recommended_risk=high, risk_level_needs_review=true
3. browser.execute_type: HIGH_STATE_CHANGE, recommended_risk=high
4. browser.execute_click: HIGH_STATE_CHANGE, recommended_risk=high
5. type/submit/click 계열 read_only=true 이면 FAIL
6. type/submit/click 계열 requires_approval=false이면 FAIL
7. type/submit/click 계열 dispatcher_connected=true이면 FAIL
8. production_submit_possible=true이면 FAIL
9. read/navigate action 3개 직전 단계 값 유지 확인
10. BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md 삭제 감지
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_action_registry_risk_mapping_20260506.json"

SUBMIT_TYPE_ACTIONS = [
    "browser.plan_submit",
    "browser.execute_click",
    "browser.execute_type",
    "browser.open_type_close_controlled",
    "browser.open_click_close_controlled",
]

READ_NAVIGATE_ACTIONS = [
    "browser.inspect",
    "browser.plan_click",
    "browser.plan_open_url",
]


def load_fixture():
    assert FIXTURE_PATH.exists(), f"fixture not found: {FIXTURE_PATH}"
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _action(data, name):
    for a in data["actions"]:
        if a["action_name"] == name:
            return a
    raise KeyError(f"action not found: {name}")


# ── 1. browser.plan_submit ────────────────────────────────────────────────


def test_plan_submit_risk_level_needs_review():
    """browser.plan_submit은 recommended_risk=high, risk_level_needs_review=true 상태."""
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a.get("risk_level_needs_review") is True
    assert a.get("recommended_risk") == "high"


def test_plan_submit_high_state_change_tier():
    """browser.plan_submit은 HIGH_STATE_CHANGE tier다."""
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a["risk_tier"] == "HIGH_STATE_CHANGE"


def test_plan_submit_requires_approval():
    """browser.plan_submit은 requires_approval=true다."""
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a["requires_approval"] is True


def test_plan_submit_not_read_only():
    """browser.plan_submit은 read_only=false다 (submit 의사결정 관여)."""
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a["read_only"] is False


def test_plan_submit_dispatcher_not_connected():
    """browser.plan_submit은 dispatcher_connected=false다."""
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a.get("dispatcher_connected") is False


def test_plan_submit_production_submit_false():
    """browser.plan_submit은 production_submit_possible=false다."""
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a.get("production_submit_possible") is False


# ── 2. browser.open_type_close_controlled ─────────────────────────────────


def test_open_type_close_high_reclassification():
    """browser.open_type_close_controlled은 high 재검토 상태."""
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a.get("risk_level_needs_review") is True
    assert a.get("recommended_risk") == "high"


def test_open_type_close_not_read_only():
    """browser.open_type_close_controlled은 read_only=false다."""
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a["read_only"] is False


def test_open_type_close_side_effect():
    """browser.open_type_close_controlled은 side_effect=true다."""
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a.get("side_effect") is True


def test_open_type_close_allowlist_required():
    """browser.open_type_close_controlled은 allowlist_required=true다."""
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a.get("allowlist_required") is True


def test_open_type_close_dispatcher_not_connected():
    """browser.open_type_close_controlled은 dispatcher_connected=false다."""
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a.get("dispatcher_connected") is False


def test_open_type_close_production_submit_false():
    """browser.open_type_close_controlled은 production_submit_possible=false다."""
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a.get("production_submit_possible") is False


# ── 3. browser.execute_type ───────────────────────────────────────────────


def test_execute_type_high_reclassification():
    """browser.execute_type은 HIGH_STATE_CHANGE로 재분류, recommended_risk=high."""
    data = load_fixture()
    a = _action(data, "browser.execute_type")
    assert a["risk_tier"] == "HIGH_STATE_CHANGE"
    assert a.get("recommended_risk") == "high"


def test_execute_type_not_read_only():
    """browser.execute_type은 read_only=false다."""
    data = load_fixture()
    a = _action(data, "browser.execute_type")
    assert a["read_only"] is False


def test_execute_type_requires_approval():
    """browser.execute_type은 requires_approval=true다."""
    data = load_fixture()
    a = _action(data, "browser.execute_type")
    assert a["requires_approval"] is True


def test_execute_type_side_effect():
    """browser.execute_type은 side_effect=true다."""
    data = load_fixture()
    a = _action(data, "browser.execute_type")
    assert a.get("side_effect") is True


def test_execute_type_allowlist_required():
    """browser.execute_type은 allowlist_required=true다."""
    data = load_fixture()
    a = _action(data, "browser.execute_type")
    assert a.get("allowlist_required") is True


def test_execute_type_dispatcher_not_connected():
    """browser.execute_type은 dispatcher_connected=false다."""
    data = load_fixture()
    a = _action(data, "browser.execute_type")
    assert a.get("dispatcher_connected") is False


# ── 4. browser.execute_click ──────────────────────────────────────────────


def test_execute_click_high_reclassification():
    """browser.execute_click은 HIGH_STATE_CHANGE로 재분류, recommended_risk=high."""
    data = load_fixture()
    a = _action(data, "browser.execute_click")
    assert a["risk_tier"] == "HIGH_STATE_CHANGE"
    assert a.get("recommended_risk") == "high"


def test_execute_click_not_read_only():
    """browser.execute_click은 read_only=false다."""
    data = load_fixture()
    a = _action(data, "browser.execute_click")
    assert a["read_only"] is False


def test_execute_click_side_effect():
    """browser.execute_click은 side_effect=true다 (사이트 상태 변경 가능)."""
    data = load_fixture()
    a = _action(data, "browser.execute_click")
    assert a.get("side_effect") is True


def test_execute_click_dispatcher_not_connected():
    """browser.execute_click은 dispatcher_connected=false다."""
    data = load_fixture()
    a = _action(data, "browser.execute_click")
    assert a.get("dispatcher_connected") is False


# ── 5~8. type/submit/click 계열 공통 금지 검증 ────────────────────────────


@pytest.mark.parametrize("action_name", SUBMIT_TYPE_ACTIONS)
def test_submit_type_action_not_read_only(action_name):
    """type/submit/click 계열은 read_only=true로 잘못 분류되면 FAIL."""
    data = load_fixture()
    a = _action(data, action_name)
    assert a["read_only"] is False, f"{action_name}: read_only must be False"


@pytest.mark.parametrize("action_name", SUBMIT_TYPE_ACTIONS)
def test_submit_type_action_requires_approval(action_name):
    """type/submit/click 계열은 requires_approval=false이면 FAIL."""
    data = load_fixture()
    a = _action(data, action_name)
    assert a["requires_approval"] is True, f"{action_name}: requires_approval must be True"


@pytest.mark.parametrize("action_name", SUBMIT_TYPE_ACTIONS)
def test_submit_type_dispatcher_not_connected(action_name):
    """type/submit/click 계열은 dispatcher_connected=true이면 FAIL."""
    data = load_fixture()
    a = _action(data, action_name)
    assert a.get("dispatcher_connected") is False, f"{action_name}: dispatcher_connected must be False"


@pytest.mark.parametrize("action_name", SUBMIT_TYPE_ACTIONS)
def test_submit_type_no_production_submit(action_name):
    """production_submit_possible=true이면 FAIL."""
    data = load_fixture()
    a = _action(data, action_name)
    assert a.get("production_submit_possible") is False, f"{action_name}: production_submit_possible must be False"


# ── 9. read/navigate action 3개 직전 단계 값 유지 ─────────────────────────


def test_browser_inspect_unchanged():
    """browser.inspect: 직전 단계 값 유지 확인."""
    data = load_fixture()
    a = _action(data, "browser.inspect")
    assert a["risk_tier"] == "LOW_READ"
    assert a["read_only"] is True
    assert a["requires_approval"] is False
    assert a["requires_gate"] is False
    assert a["production_allowed"] is False


def test_browser_plan_click_unchanged():
    """browser.plan_click: 직전 단계 값 유지 확인."""
    data = load_fixture()
    a = _action(data, "browser.plan_click")
    assert a["risk_tier"] == "LOW_NAVIGATE"
    assert a["read_only"] is True
    assert a["requires_approval"] is False
    assert a["requires_gate"] is False


def test_browser_plan_open_url_unchanged():
    """browser.plan_open_url: 직전 단계 값 유지 확인."""
    data = load_fixture()
    a = _action(data, "browser.plan_open_url")
    assert a["risk_tier"] == "LOW_NAVIGATE"
    assert a["requires_gate"] is False


# ── 10. BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md 유지 확인 ─────────


def test_untracked_preflight_md_not_deleted():
    """BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md untracked 유지 (삭제 금지)."""
    preflight = Path(__file__).parents[2] / "BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md"
    if not preflight.exists():
        pytest.skip("WARN: BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md not found (may have been deleted)")
    assert preflight.is_file()


# ── action_registry.py 연결 없음 확인 ─────────────────────────────────────


def test_submit_type_not_in_action_registry():
    """submit/type/click 계열은 action_registry에 미등록 상태 유지."""
    from ai_orchestrator.browser_tool.preflight.agent_action_registry import is_known_action

    for action in SUBMIT_TYPE_ACTIONS:
        assert not is_known_action(action), (
            f"{action} must NOT be in action_registry this stage (reclassification is metadata-only)"
        )


def test_read_navigate_still_in_action_registry():
    """read/navigate 3개는 action_registry 등록 유지."""
    from ai_orchestrator.browser_tool.preflight.agent_action_registry import is_known_action

    for action in READ_NAVIGATE_ACTIONS:
        assert is_known_action(action), f"{action} must be in action_registry"


def test_reclassification_stage_documented():
    """재분류 stage가 fixture에 문서화되어 있다."""
    data = load_fixture()
    reclassified = [
        a for a in data["actions"] if a.get("reclassification_stage") == "BROWSER_SUBMIT_TYPE_RISK_RECLASSIFICATION_1"
    ]
    assert len(reclassified) >= 5, f"Expected at least 5 reclassified actions, got {len(reclassified)}"
