"""Gabia-specific validation helpers using site_engine validators."""
from __future__ import annotations

from scripts.site_engine.validators import (
    ValidationResult,
    validate_action_plan_safety,
    validate_no_plain_secret,
    validate_workflow_has_profile,
)

__all__ = [
    "validate_gabia_action_plan",
    "validate_gabia_workflow",
    "validate_gabia_no_plain_secret",
]


def validate_gabia_action_plan(plan) -> ValidationResult:
    return validate_action_plan_safety(plan)


def validate_gabia_workflow(run_plan) -> ValidationResult:
    return validate_workflow_has_profile(run_plan)


def validate_gabia_no_plain_secret(data: dict) -> ValidationResult:
    return validate_no_plain_secret(data)
