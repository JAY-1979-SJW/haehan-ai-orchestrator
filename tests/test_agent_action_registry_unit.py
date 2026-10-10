"""Unit tests for agent_action_registry — data structure only, no COM/external calls."""

import ai_orchestrator.browser_tool.preflight.agent_action_registry as reg


def test_risk_constants_exist():
    assert reg.RISK_LOW == "low"
    assert reg.RISK_MEDIUM == "medium"
    assert reg.RISK_HIGH == "high"
    assert reg.RISK_CRITICAL == "critical"
    assert reg.RISK_UNKNOWN == "unknown"


def test_category_constants_exist():
    assert reg.CATEGORY_UNKNOWN == "unknown"
    assert reg.CATEGORY_SYSTEM == "system"
    assert reg.CATEGORY_WEB == "web"


def test_known_action_returns_meta():
    meta = reg.get_meta("excel.write_cell")
    assert meta is not None
    assert meta.action == "excel.write_cell"
    assert meta.risk_level in reg.KNOWN_RISKS
    assert meta.category in reg.KNOWN_CATEGORIES


def test_unknown_action_returns_none_for_unregistered():
    meta = reg.get_meta("nonexistent.action.xyz")
    assert meta is None
    # category_of / risk_of should still return safe defaults
    assert reg.category_of("nonexistent.action.xyz") == reg.CATEGORY_UNKNOWN
    assert reg.risk_of("nonexistent.action.xyz") == reg.RISK_UNKNOWN


def test_is_known_action():
    assert reg.is_known_action("ping") is True
    assert reg.is_known_action("nonexistent.xyz") is False


def test_list_actions_returns_known_entries():
    actions = reg.list_actions()
    assert "ping" in actions
    assert "excel.write_cell" in actions


def test_excel_update_cell_by_header_copy_registered():
    assert reg.is_known_action("excel.update_cell_by_header_copy") is True
    meta = reg.get_meta("excel.update_cell_by_header_copy")
    assert meta is not None
    assert meta.action == "excel.update_cell_by_header_copy"
    assert meta.category == reg.CATEGORY_EXCEL_COM
    assert meta.risk_level == reg.RISK_MEDIUM
    assert meta.read_only is False
    assert meta.requires_file_path is False  # 실행 중인 Excel 대상
    assert meta.requires_save_as is True  # 복사본 저장 강제
