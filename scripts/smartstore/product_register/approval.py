"""Approval-stage boundary for SmartStore product registration."""
from __future__ import annotations

from scripts.smartstore.approved_product_workflow import ApprovedProductWorkflowReport, approved_save_product
from scripts.smartstore.product_register.gates import APPROVAL_CONFIRM_TEXT, require_action


def save_product(
    *,
    approved: bool,
    confirm: str,
    allow_mixed_readonly: bool = False,
    cleanup: bool = False,
    wait_seconds: float = 10.0,
) -> ApprovedProductWorkflowReport:
    require_action("product.save", approved=approved, confirm=confirm)
    return approved_save_product(
        approved=approved,
        confirm=confirm,
        allow_mixed_readonly=allow_mixed_readonly,
        cleanup=cleanup,
        wait_seconds=wait_seconds,
    )


__all__ = ["APPROVAL_CONFIRM_TEXT", "save_product"]
