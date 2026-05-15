"""Hiworks-specific validation helpers using site_engine validators."""
from __future__ import annotations

from scripts.site_engine.validators import (
    ValidationResult,
    validate_action_plan_steps,
    validate_no_blocked_step_executable,
    validate_no_executable_sensitive_step_without_gate,
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
    r1 = validate_action_plan_steps(plan)
    r2 = validate_no_blocked_step_executable(plan)
    r3 = validate_no_executable_sensitive_step_without_gate(plan)
    issues = r1.issues + r2.issues + r3.issues
    return ValidationResult(is_valid=not issues, issues=issues)


def validate_hiworks_workflow(run_plan) -> ValidationResult:
    """Validate a WorkflowRunPlan built for a Hiworks workflow."""
    return validate_workflow_has_profile(run_plan)


def validate_hiworks_no_plain_secret(data: dict) -> ValidationResult:
    """Ensure no plain secrets are present in a Hiworks data payload."""
    return validate_no_plain_secret(data)
