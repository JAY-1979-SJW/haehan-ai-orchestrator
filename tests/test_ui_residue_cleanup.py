from scripts import ui_residue_cleanup as cleanup


def test_cleanup_allowlist_does_not_include_active_ui():
    forbidden = set(cleanup.FORBIDDEN_DELETE)

    assert "desktop/ui_dist" in forbidden
    assert "desktop/ui_new" in forbidden
    assert "admin-web/src" in forbidden
    assert "ai_orchestrator/admin_ui_router.py" in forbidden
    assert not forbidden.intersection(cleanup.ALLOW_DELETE)


def test_cleanup_safety_boundary_blocks_forbidden_paths():
    assert cleanup._is_forbidden(cleanup.ROOT / "desktop" / "ui_dist")
    assert cleanup._is_forbidden(cleanup.ROOT / "admin-web" / "src")
    assert not cleanup._is_forbidden(cleanup.ROOT / "admin-web" / ".next")


def test_cleanup_dry_run_reports_existing_or_absent_paths():
    items = cleanup.cleanup(apply=False)

    assert items
    assert all(item.status in {"DRY_RUN", "PASS"} for item in items)
