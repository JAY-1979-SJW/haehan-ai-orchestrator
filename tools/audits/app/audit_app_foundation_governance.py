"""App Foundation Governance 구조 감사 스크립트.

골격 문서 존재·필수 키워드·보안 정책 포함 여부를 read-only로 검사한다.
실제 기능 구현 없음. 감사만 수행.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

REQUIRED_DOCS = {
    "app_foundation_governance": ROOT / "docs/architecture/app_foundation_governance.md",
    "permission_approval_model": ROOT / "docs/architecture/permission_approval_model.md",
    "workflow_state_model": ROOT / "docs/architecture/workflow_state_model.md",
    "storage_audit_evidence_model": ROOT / "docs/architecture/storage_audit_evidence_model.md",
    "governance_gate_matrix": ROOT / "docs/architecture/governance_gate_matrix.md",
}

REQUIRED_LAYER_NAMES = [
    "UI Layer",
    "API",
    "Router",
    "Action Registry",
    "Permission",
    "Approval Gate",
    "Workflow",
    "Task",
    "Usecase",
    "Service",
    "Domain",
    "Policy",
    "Adapter",
    "Site Engine",
    "Local Agent",
    "Browser",
    "Repository",
    "Storage",
    "Audit",
    "Report",
    "Evidence",
    "Test",
    "Gate",
]

REQUIRED_DECISIONS = [
    "ALLOWED",
    "READ_ONLY_ALLOWED",
    "DRAFT_ALLOWED",
    "APPROVAL_REQUIRED",
    "USER_DIRECT_REQUIRED",
    "LOCAL_AGENT_REQUIRED",
    "BLOCKED",
]

REQUIRED_WORKFLOW_STATES = [
    "REQUESTED",
    "VALIDATED",
    "DRAFT_CREATED",
    "APPROVAL_REQUIRED",
    "APPROVED",
    "USER_DIRECT_REQUIRED",
    "LOCAL_AGENT_REQUIRED",
    "EXECUTION_READY",
    "EXECUTING",
    "EXECUTED",
    "EVIDENCE_COLLECTED",
    "COMPLETED",
    "REJECTED",
    "BLOCKED",
    "FAILED",
    "CANCELLED",
]

REQUIRED_STORAGE_CATEGORIES = [
    "Task Store",
    "Approval Store",
    "Draft Store",
    "Execution Plan",
    "Evidence Store",
    "Audit Log",
    "Report Store",
    "Artifact Store",
    "Manual Visit",
    "Session Store",
]

REQUIRED_GATE_CODES = [
    "FORBIDDEN_IMPORT",
    "CIRCULAR_IMPORT",
    "SECURITY_PATTERN",
    "FAT_SITE",
    "BLOCKED_SECRET_SESSION",
    "APPROVAL_REQUIRED_ACTION",
    "USER_DIRECT_REQUIRED_ACTION",
    "SERVER_BROWSER_GUARD",
    "ROUTER_THINNESS",
    "STORAGE_BOUNDARY",
]

REQUIRED_SECURITY_PHRASES = [
    "session",
    "cookie",
    "token",
    "BLOCKED",
    "USER_DIRECT_REQUIRED",
    "LOCAL_AGENT_REQUIRED",
]

REQUIRED_GATE_MATRIX_PRIORITIES = ["P0", "P1", "P2"]


@dataclass
class AuditIssue:
    severity: str
    code: str
    doc: str
    message: str


@dataclass
class AuditReport:
    generated_at: str = ""
    issues: list[AuditIssue] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)

    def add_check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            self.issues.append(AuditIssue("WARN", f"CHECK_FAILED_{name.upper()}", name, detail))

    @property
    def passed(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def summary(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "total_checks": len(self.checks),
            "passed": sum(1 for c in self.checks if c["passed"]),
            "failed": sum(1 for c in self.checks if not c["passed"]),
            "issues": [
                {"severity": i.severity, "code": i.code, "doc": i.doc, "message": i.message} for i in self.issues
            ],
            "checks": self.checks,
        }


def _read_doc(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def check_required_docs(report: AuditReport) -> None:
    for key, path in REQUIRED_DOCS.items():
        exists = path.exists() and path.stat().st_size > 100
        report.add_check(
            f"DOC_EXISTS_{key}",
            exists,
            f"{path.relative_to(ROOT)}" if exists else f"MISSING: {path.relative_to(ROOT)}",
        )


def check_layer_names(report: AuditReport) -> None:
    doc = _read_doc(REQUIRED_DOCS["app_foundation_governance"])
    for name in REQUIRED_LAYER_NAMES:
        found = name in doc
        report.add_check(f"LAYER_{name.replace(' ', '_').upper()}", found, name)


def check_decisions(report: AuditReport) -> None:
    doc = _read_doc(REQUIRED_DOCS["permission_approval_model"])
    for decision in REQUIRED_DECISIONS:
        found = decision in doc
        report.add_check(f"DECISION_{decision}", found, decision)


def check_workflow_states(report: AuditReport) -> None:
    doc = _read_doc(REQUIRED_DOCS["workflow_state_model"])
    for state in REQUIRED_WORKFLOW_STATES:
        found = state in doc
        report.add_check(f"STATE_{state}", found, state)


def check_storage_categories(report: AuditReport) -> None:
    doc = _read_doc(REQUIRED_DOCS["storage_audit_evidence_model"])
    for cat in REQUIRED_STORAGE_CATEGORIES:
        found = cat in doc
        report.add_check(f"STORAGE_{cat.replace(' ', '_').upper()}", found, cat)


def check_gate_matrix(report: AuditReport) -> None:
    doc = _read_doc(REQUIRED_DOCS["governance_gate_matrix"])
    for gate in REQUIRED_GATE_CODES:
        found = gate in doc
        report.add_check(f"GATE_{gate}", found, gate)
    for priority in REQUIRED_GATE_MATRIX_PRIORITIES:
        found = priority in doc
        report.add_check(f"GATE_PRIORITY_{priority}", found, priority)


def check_security_phrases(report: AuditReport) -> None:
    storage_doc = _read_doc(REQUIRED_DOCS["storage_audit_evidence_model"])
    permission_doc = _read_doc(REQUIRED_DOCS["permission_approval_model"])
    combined = storage_doc + permission_doc
    for phrase in REQUIRED_SECURITY_PHRASES:
        found = phrase in combined
        report.add_check(f"SECURITY_PHRASE_{phrase.upper()}", found, phrase)


def check_session_policy(report: AuditReport) -> None:
    storage_doc = _read_doc(REQUIRED_DOCS["storage_audit_evidence_model"])
    has_session_blocked = "Session Store" in storage_doc and "BLOCKED" in storage_doc
    report.add_check("SESSION_STORE_BLOCKED_POLICY", has_session_blocked, "Session Store에 BLOCKED 정책 명시 여부")
    has_forbidden = "금지" in storage_doc or "금지 대상" in storage_doc
    report.add_check("SESSION_FORBIDDEN_MARKED", has_forbidden, "Session Store에 금지 대상 명시 여부")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_required_docs(report)
    check_layer_names(report)
    check_decisions(report)
    check_workflow_states(report)
    check_storage_categories(report)
    check_gate_matrix(report)
    check_security_phrases(report)
    check_session_policy(report)
    return report


if __name__ == "__main__":
    report = run_audit()
    summary = report.summary()
    out_path = ROOT / "data" / "app_foundation_governance_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"총 검사: {summary['total_checks']}")
    print(f"통과:   {summary['passed']}")
    print(f"실패:   {summary['failed']}")
    for issue in summary["issues"]:
        print(f"  [{issue['severity']}] {issue['code']}: {issue['message']}")
    print(f"저장:   {out_path}")
    if summary["failed"] > 0:
        raise SystemExit(1)
