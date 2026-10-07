"""site_engine validators — 순수 검증 함수 모음.

실제 실행/DB/file/browser 접근 없음. 민감값 원문 출력 금지.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.site_engine.action_planner import ActionPlan, ActionPlanStatus
from scripts.site_engine.site_types import GateDecision
from scripts.site_engine.workflow_runner import WorkflowRunPlan

_SENSITIVE_PATTERNS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "secret",
        "cookie",
        "session",
        "credential",
        "api_key",
        "private_key",
        "otp",
        "certificate",
        "비밀번호",
        "토큰",
        "쿠키",
        "세션",
        "시크릿",
        "인증서",
    }
)

_MASK = "***REDACTED***"


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "ERROR"  # ERROR | WARN


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARN"]


def validate_no_plain_secret(data: dict[str, Any]) -> ValidationResult:
    """dict에 민감값 키가 평문으로 존재하는지 검사."""
    issues: list[ValidationIssue] = []
    for k in data:
        if any(p in k.lower() for p in _SENSITIVE_PATTERNS):
            issues.append(
                ValidationIssue(
                    code="PLAIN_SECRET_KEY",
                    message=f"Sensitive key detected: {k!r} — value must not be stored in plain",
                )
            )
    return ValidationResult(is_valid=len(issues) == 0, issues=issues)


def validate_no_executable_sensitive_step_without_gate(plan: ActionPlan) -> ValidationResult:
    """APPROVAL_REQUIRED step이 gate 없이 READY 상태인지 검사."""
    issues: list[ValidationIssue] = []
    for step in plan.steps:
        if (
            step.required_gate == GateDecision.APPROVAL_REQUIRED
            and step.status == ActionPlanStatus.READY
            and step.gate_result is None
        ):
            issues.append(
                ValidationIssue(
                    code="APPROVAL_REQUIRED_WITHOUT_GATE",
                    message=f"Step {step.step_id!r} ({step.capability}) is READY but has no gate_result",
                )
            )
    return ValidationResult(is_valid=len(issues) == 0, issues=issues)


def validate_no_blocked_step_executable(plan: ActionPlan) -> ValidationResult:
    """BLOCKED step이 실행 가능 상태로 표시됐는지 검사."""
    issues: list[ValidationIssue] = []
    for step in plan.steps:
        if step.status == ActionPlanStatus.BLOCKED and (step.gate_result is not None and step.gate_result.allowed):
            issues.append(
                ValidationIssue(
                    code="BLOCKED_STEP_MARKED_ALLOWED",
                    message=f"Step {step.step_id!r} is BLOCKED but gate_result says allowed",
                )
            )
    return ValidationResult(is_valid=len(issues) == 0, issues=issues)


def validate_workflow_has_profile(run_plan: WorkflowRunPlan) -> ValidationResult:
    """workflow definition에 site_key 또는 profile_key가 있는지 검사."""
    issues: list[ValidationIssue] = []
    d = run_plan.definition
    if not d.site_key and not d.profile_key:
        issues.append(
            ValidationIssue(
                code="MISSING_PROFILE",
                message="WorkflowDefinition must have site_key or profile_key",
            )
        )
    return ValidationResult(is_valid=len(issues) == 0, issues=issues)


def validate_action_plan_steps(plan: ActionPlan) -> ValidationResult:
    """action plan 전체 steps 검증."""
    issues: list[ValidationIssue] = []

    for step in plan.steps:
        # GATE_REQUIRED 상태면서 overall READY는 불가
        if step.status == ActionPlanStatus.GATE_REQUIRED and plan.overall_status == ActionPlanStatus.READY:
            issues.append(
                ValidationIssue(
                    code="GATE_REQUIRED_BUT_PLAN_READY",
                    message=f"Step {step.step_id!r} needs gate but plan is READY",
                )
            )

        # sensitive step에 value 필드가 있으면 오류
        if step.is_sensitive and hasattr(step, "value"):
            issues.append(
                ValidationIssue(
                    code="SENSITIVE_STEP_HAS_VALUE",
                    message=f"Step {step.step_id!r} is sensitive but has value field",
                )
            )

    return ValidationResult(is_valid=len(issues) == 0, issues=issues)


def validate_action_plan_safety(plan: ActionPlan) -> ValidationResult:
    """도구별 action plan 공용 검증 — steps·차단 단계 실행 불가·민감 단계 게이트 3종의 issue 를 합친다.

    gabia/google/hiworks/youtube validators 의 validate_<tool>_action_plan 이 똑같이 복사해 쓰던 본문을 한 곳으로 모았다.
    """
    r1 = validate_action_plan_steps(plan)
    r2 = validate_no_blocked_step_executable(plan)
    r3 = validate_no_executable_sensitive_step_without_gate(plan)
    issues = r1.issues + r2.issues + r3.issues
    return ValidationResult(is_valid=not issues, issues=issues)
