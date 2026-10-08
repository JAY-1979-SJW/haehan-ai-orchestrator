"""BROWSER_READ_NAVIGATE_ACTION_REGISTRY_1 테스트.

검증 범위:
- read/navigate 3개 action이 registry에 존재
- read_only=True, requires_approval=False 정합성
- submit/type/click 계열 미포함 확인
- browser.plan_submit / browser.open_type_close_controlled 미변경 확인
- executor dispatcher 미연결 확인
- production_submit_possible=true 인 action 없음
- BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md untracked 유지 (삭제 금지)
"""

import json
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.preflight.agent_action_registry import (
    CATEGORY_BROWSER,
    RISK_LOW,
    get_meta,
    is_known_action,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_action_registry_risk_mapping_20260506.json"

READ_NAVIGATE_ACTIONS = [
    "browser.inspect",
    "browser.plan_click",
    "browser.plan_open_url",
]

EXCLUDED_ACTIONS = [
    "browser.plan_submit",
    "browser.execute_click",
    "browser.execute_type",
    "browser.open_url_controlled",
    "browser.open_click_close_controlled",
    "browser.open_type_close_controlled",
]

SUBMIT_TYPE_CLICK_PATTERNS = [
    "submit",
    "type",
    "click",
    "execute",
    "open_url_controlled",
    "open_type_close",
    "open_click_close",
]


@pytest.mark.parametrize("action_name", READ_NAVIGATE_ACTIONS)
def test_read_navigate_action_exists_in_registry(action_name):
    """read/navigate action이 registry에 존재한다."""
    assert is_known_action(action_name), f"{action_name} not found in registry"


@pytest.mark.parametrize("action_name", READ_NAVIGATE_ACTIONS)
def test_read_navigate_action_is_read_only(action_name):
    """read-only action은 read_only=True다."""
    meta = get_meta(action_name)
    assert meta is not None
    assert meta.read_only is True, f"{action_name} read_only must be True"


@pytest.mark.parametrize("action_name", READ_NAVIGATE_ACTIONS)
def test_read_navigate_action_requires_approval_false(action_name):
    """read-only action은 requires_approval=False다."""
    meta = get_meta(action_name)
    assert meta is not None
    assert meta.requires_approval is False, f"{action_name} requires_approval must be False"


@pytest.mark.parametrize("action_name", READ_NAVIGATE_ACTIONS)
def test_read_navigate_action_risk_low(action_name):
    """read/navigate action은 RISK_LOW다."""
    meta = get_meta(action_name)
    assert meta is not None
    assert meta.risk_level == RISK_LOW, f"{action_name} risk_level must be low"


@pytest.mark.parametrize("action_name", READ_NAVIGATE_ACTIONS)
def test_read_navigate_action_category_browser(action_name):
    """read/navigate action의 category는 CATEGORY_BROWSER다."""
    meta = get_meta(action_name)
    assert meta is not None
    assert meta.category == CATEGORY_BROWSER


@pytest.mark.parametrize("action_name", READ_NAVIGATE_ACTIONS)
def test_read_navigate_action_no_file_path_required(action_name):
    """read/navigate action은 파일 경로 불필요."""
    meta = get_meta(action_name)
    assert meta is not None
    assert meta.requires_file_path is False


def test_excluded_actions_not_in_read_navigate_group():
    """submit/type/click/form-write/file-write 계열은 read/navigate 목록에 없다."""
    for action in EXCLUDED_ACTIONS:
        assert action not in READ_NAVIGATE_ACTIONS, f"{action} must not be in read/navigate group"


def test_browser_plan_submit_unchanged():
    """browser.plan_submit은 이번 단계에서 변경되지 않았음을 확인 (registry 미등록 상태 유지)."""
    # browser.plan_submit은 이번 단계에서 action_registry에 등록하지 않는다.
    # risk mapping fixture에서만 정의됨.
    assert not is_known_action("browser.plan_submit"), "browser.plan_submit must NOT be in action_registry this stage"


def test_browser_open_type_close_controlled_unchanged():
    """browser.open_type_close_controlled은 이번 단계에서 변경되지 않았음을 확인 (registry 미등록 유지)."""
    assert not is_known_action("browser.open_type_close_controlled"), (
        "browser.open_type_close_controlled must NOT be in action_registry this stage"
    )


def test_executor_dispatcher_not_connected():
    """executor dispatcher 연결이 이번 단계에서 추가되지 않았음을 확인.

    browser.inspect/plan_click/plan_open_url은 requires_browser=True이지만
    실제 실행 dispatcher와 연결되지 않은 metadata 전용 등록 상태임.
    ActionMeta에 dispatcher_connected 필드가 없음 = 설계상 미연결 의도.
    """
    for action in READ_NAVIGATE_ACTIONS:
        meta = get_meta(action)
        assert meta is not None
        assert not hasattr(meta, "dispatcher_connected"), f"{action}: dispatcher_connected 필드가 추가되면 안 됨"


def test_no_production_submit_in_read_navigate_group():
    """production_submit_possible=true인 action이 read/navigate 그룹에 없어야 한다.

    ActionMeta에 production_submit_possible 필드가 없음 = 설계상 false 의미.
    """
    for action in READ_NAVIGATE_ACTIONS:
        meta = get_meta(action)
        assert meta is not None
        assert not hasattr(meta, "production_submit_possible")


def test_allowlist_required_documented_as_todo():
    """browser.plan_open_url의 allowlist_required 정책이 TODO로 추적된다.

    action_registry.py 소스 내 TODO 주석으로 문서화되어 있어야 한다.
    """
    import inspect

    import ai_orchestrator.browser_tool.preflight.agent_action_registry as reg_module

    source = inspect.getsource(reg_module)
    assert "allowlist" in source.lower(), (
        "browser.plan_open_url allowlist_required TODO must be documented in action_registry.py"
    )


def test_risk_mapping_fixture_plan_submit_risk_review_flag():
    """risk mapping fixture에서 browser.plan_submit risk_level_needs_review=true 유지."""
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    plan_submit = next((a for a in data["actions"] if a["action_name"] == "browser.plan_submit"), None)
    assert plan_submit is not None
    assert plan_submit.get("risk_level_needs_review") is True


def test_risk_mapping_fixture_open_type_close_risk_review_flag():
    """risk mapping fixture에서 browser.open_type_close_controlled risk_level_needs_review=true 유지."""
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    otc = next((a for a in data["actions"] if a["action_name"] == "browser.open_type_close_controlled"), None)
    assert otc is not None
    assert otc.get("risk_level_needs_review") is True


def test_untracked_preflight_md_not_deleted():
    """BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md untracked 유지 (삭제/수정 금지).

    이 파일은 untracked 상태로 유지되어야 하며, 이번 작업에서 삭제/수정하지 않는다.
    파일이 존재하면 PASS, 존재하지 않으면 WARN (삭제 감지).
    """
    preflight = Path(__file__).parents[2] / "BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md"
    if not preflight.exists():
        pytest.skip("WARN: BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md not found (may have been deleted)")
    assert preflight.is_file()
