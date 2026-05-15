"""Google-specific validation helpers using site_engine validators."""
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
    "validate_google_action_plan",
    "validate_google_workflow",
    "validate_google_no_plain_secret",
]


def validate_google_action_plan(plan) -> ValidationResult:
    r1 = validate_action_plan_steps(plan)
    r2 = validate_no_blocked_step_executable(plan)
    r3 = validate_no_executable_sensitive_step_without_gate(plan)
    issues = r1.issues + r2.issues + r3.issues
    return ValidationResult(is_valid=not issues, issues=issues)


def validate_google_workflow(run_plan) -> ValidationResult:
    return validate_workflow_has_profile(run_plan)


def validate_google_no_plain_secret(data: dict) -> ValidationResult:
    return validate_no_plain_secret(data)
