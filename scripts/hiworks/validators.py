"""Hiworks-specific validation helpers using site_engine validators."""
from __future__ import annotations

from scripts.site_engine.validators import (
    ValidationResult,
    validate_action_plan_safety,
    validate_no_plain_secret,
    validate_workflow_has_profile,
)

__all__ = [
    "validate_hiworks_action_plan",
    "validate_hiworks_workflow",
    "validate_hiworks_no_plain_secret",
]


def validate_hiworks_action_plan(plan) -> ValidationResult:
    """Validate an ActionPlan built for a Hiworks command."""
    return validate_action_plan_safety(plan)


def validate_hiworks_workflow(run_plan) -> ValidationResult:
    """Validate a WorkflowRunPlan built for a Hiworks workflow."""
    return validate_workflow_has_profile(run_plan)


def validate_hiworks_no_plain_secret(data: dict) -> ValidationResult:
    """Ensure no plain secrets are present in a Hiworks data payload."""
    return validate_no_plain_secret(data)
