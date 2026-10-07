"""Unit tests for action_registry approval policy consistency.

Validates that RISK_HIGH and RISK_MEDIUM write actions have requires_approval=True.
"""

import ai_orchestrator.browser_tool.preflight.agent_action_registry as reg


def test_all_high_risk_write_actions_require_approval():
    """Verify that RISK_HIGH actions with read_only=False require approval."""
    actions = reg.list_actions()
    high_risk_write = [
        a for a in actions if reg.get_meta(a).risk_level == reg.RISK_HIGH and not reg.get_meta(a).read_only
    ]

    assert len(high_risk_write) > 0, "Expected at least one RISK_HIGH write action"

    for action in high_risk_write:
        meta = reg.get_meta(action)
        assert meta.requires_approval is True, (
            f"Action {action!r} (RISK_HIGH, write) must have requires_approval=True, got {meta.requires_approval}"
        )


def test_all_medium_risk_write_actions_require_approval():
    """Verify that RISK_MEDIUM actions with read_only=False require approval."""
    actions = reg.list_actions()
    medium_risk_write = [
        a for a in actions if reg.get_meta(a).risk_level == reg.RISK_MEDIUM and not reg.get_meta(a).read_only
    ]

    assert len(medium_risk_write) > 0, "Expected at least one RISK_MEDIUM write action"

    for action in medium_risk_write:
        meta = reg.get_meta(action)
        assert meta.requires_approval is True, (
            f"Action {action!r} (RISK_MEDIUM, write) must have requires_approval=True, got {meta.requires_approval}"
        )


def test_secret_actions_require_approval():
    """Verify that actions in CATEGORY_SECRET require approval."""
    actions = reg.list_actions()
    secret_actions = [a for a in actions if reg.get_meta(a).category == reg.CATEGORY_SECRET]

    assert len(secret_actions) > 0, "Expected at least one SECRET action"

    for action in secret_actions:
        meta = reg.get_meta(action)
        assert meta.requires_approval is True, f"Action {action!r} (SECRET) must have requires_approval=True"


def test_specific_write_actions_require_approval():
    """Verify specific known write actions require approval."""
    required_approval_actions = {
        "login_with_secret",
        "inspect_after_login",
        "excel_write_report_copy",
        "excel.write_cell",
        "excel.save_as",
        "excel.update_cell_by_header_copy",
        "excel.insert_row_by_header_copy",
        "excel.insert_column_by_header_copy",
        "excel.write_formula_by_header_copy",
        "excel.apply_change_plan_copy",
        "excel.create_review_summary_sheet_copy",
        "excel.export_pdf_copy",
        "excel.pack.review_estimate_copy",
        "excel.pack.review_settlement_copy",
        "excel.pack.check_material_prices_copy",
        "hancom.convert_hwp_to_hwpx_copy",
        "local_software.install",
    }

    for action in required_approval_actions:
        assert reg.is_known_action(action), f"Action {action!r} not found in registry"
        meta = reg.get_meta(action)
        assert meta.requires_approval is True, (
            f"Action {action!r} must have requires_approval=True, got {meta.requires_approval}"
        )


def test_privacy_scan_actions_require_approval():
    """Verify that privacy-impacting read-only actions require approval."""
    privacy_actions = {
        "local_inventory.scan",
        "local_inventory.build_app_map",
        "local_file_map.scan",
    }

    for action in privacy_actions:
        assert reg.is_known_action(action), f"Action {action!r} not found in registry"
        meta = reg.get_meta(action)
        assert meta.read_only is True, f"Action {action!r} should be read-only, got read_only={meta.read_only}"
        assert meta.requires_approval is True, (
            f"Action {action!r} (privacy scan, read-only) must have requires_approval=True"
        )


def test_read_only_browser_actions_no_approval_required():
    """Verify that read-only browser actions don't require approval (except for privacy scans)."""
    browser_readonly_actions = {
        "open_page_readonly",
        "inspect_page",
        "open_local_browser",
        "open_local_browser_probe",
        "observe_public_browser_page",
    }

    for action in browser_readonly_actions:
        if reg.is_known_action(action):
            meta = reg.get_meta(action)
            assert meta.read_only is True, f"Action {action!r} should be read-only"
            # Browser actions should not require approval (they are read-only observational)
            assert meta.requires_approval is False, f"Action {action!r} (read-only browser) should not require approval"


def test_read_only_safe_actions_no_approval_required():
    """Verify that simple read-only actions don't require approval."""
    safe_readonly_actions = {
        "ping",
        "system_info",
        "list_allowed_apps",
        "excel_read_sheet",
        "excel.read_cell",
        "local_inventory.status",
        "local_inventory.compare",
        "local_file_map.status",
    }

    for action in safe_readonly_actions:
        if reg.is_known_action(action):
            meta = reg.get_meta(action)
            assert meta.read_only is True, f"Action {action!r} should be read-only"
            assert meta.requires_approval is False, (
                f"Action {action!r} (safe read-only) should not require approval, got {meta.requires_approval}"
            )


def test_no_inconsistent_approval_settings():
    """Verify that no RISK_HIGH or RISK_MEDIUM write action has requires_approval=False."""
    actions = reg.list_actions()

    for action in actions:
        meta = reg.get_meta(action)

        # Check for inconsistency: high/medium risk with write capability
        is_high_or_medium = meta.risk_level in (reg.RISK_HIGH, reg.RISK_MEDIUM)
        is_write = not meta.read_only
        requires_no_approval = meta.requires_approval is False

        if is_high_or_medium and is_write and requires_no_approval:
            raise AssertionError(
                f"Inconsistency in action {action!r}: "
                f"risk_level={meta.risk_level}, read_only={meta.read_only}, "
                f"requires_approval={meta.requires_approval} — "
                f"write actions must require approval"
            )
