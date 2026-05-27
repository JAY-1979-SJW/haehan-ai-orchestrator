"""Category selection boundary for SmartStore registration."""
from __future__ import annotations

from typing import Any

from scripts.smartstore.draft_fill import TEST_CATEGORY, select_test_category


def select_category(target_id: str, *, port: int, category: dict[str, Any] | None = None) -> dict[str, Any]:
    """Select a category in the registration form.

    This is a prepare-stage action. It must not click final save/register
    controls.
    """
    return select_test_category(target_id, port=port, category=category or TEST_CATEGORY)
