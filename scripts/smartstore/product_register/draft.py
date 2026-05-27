"""Draft-fill boundary for SmartStore product registration."""
from __future__ import annotations

from typing import Any

from scripts.smartstore.draft_fill import SmartStoreDraftFillReport, fill_product_draft
from scripts.smartstore.product_register.gates import require_action


def fill_draft(
    data: dict[str, Any],
    *,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 12.0,
) -> SmartStoreDraftFillReport:
    require_action("draft.fill")
    return fill_product_draft(data, allow_mixed_readonly=allow_mixed_readonly, wait_seconds=wait_seconds)
