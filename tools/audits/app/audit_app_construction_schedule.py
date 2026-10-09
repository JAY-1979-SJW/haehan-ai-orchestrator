"""App Construction Schedule 감사 스크립트.

공정 문서 존재·내용 검증·Phase A/B 완료 확인.
기능 테스트 아님 — 문서 구조 위반 감지만.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
ARCH = ROOT / "docs" / "architecture"
REPORTS = ROOT / "docs" / "reports"

REQUIRED_SCHEDULE_DOCS = {
    "master_schedule": ARCH / "app_construction_master_schedule.md",
    "as_built_matrix": ARCH / "app_construction_as_built_matrix.md",
    "completion_checklist": ARCH / "app_construction_completion_checklist.md",
    "next_sequence": ARCH / "app_construction_next_sequence.md",
}

REQUIRED_REPORT_DOCS = {
    "punch_list": REPORTS / "app_construction_punch_list_20260515.md",
    "schedule_report": REPORTS / "app_construction_schedule_documentation_20260515.md",
}

MASTER_SCHEDULE_PHASES = [
    "Phase A",
    "Phase B",
    "Phase C",
    "Phase D",
    "Phase E",
    "Phase F",
    "Phase G",
    "Phase H",
    "Phase I",
]
MASTER_SCHEDULE_KEYWORDS = ["FOUNDATION", "STRUCTURAL", "SHARED_FACILITY", "DOMAIN_SHELL", "DoD"]

PHASE_A_COMPLETE_MARKERS = [
    "codebase_layer_audit.py",
    "quality_gate.py",
    "governance_gate_matrix.md",
]

PHASE_B_COMPLETE_MARKERS = [
    "domain_room_allocation_rule.md",
    "shared_warehouse_model.md",
    "storage_boundary_policy.md",
    "shared_warehouse_manifest.json",
]

AS_BUILT_DOMAINS = ["gabia", "hiworks", "g2b", "eum", "google", "youtube", "cad", "hwpx"]

CHECKLIST_PHASES = ["Phase A", "Phase B", "Phase C", "Phase D", "Phase E", "Phase F", "Phase G", "Phase H", "Phase I"]

NEXT_SEQUENCE_KEYWORDS = ["G2B", "Eum", "Gabia", "CAD", "HWPX", "DoD"]

PUNCH_LIST_PRIORITIES = ["HIGH", "MEDIUM", "LOW"]


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
            self.issues.append(AuditIssue("WARN", f"SCHEDULE_{name.upper()}", name, detail))

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
        }


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def check_schedule_docs_exist(report: AuditReport) -> None:
    for key, path in REQUIRED_SCHEDULE_DOCS.items():
        exists = path.exists() and path.stat().st_size > 100
        report.add_check(f"DOC_{key.upper()}", exists, str(path.relative_to(ROOT)))


def check_report_docs_exist(report: AuditReport) -> None:
    for key, path in REQUIRED_REPORT_DOCS.items():
        exists = path.exists() and path.stat().st_size > 100
        report.add_check(f"REPORT_{key.upper()}", exists, str(path.relative_to(ROOT)))


def check_master_schedule_phases(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["master_schedule"])
    for phase in MASTER_SCHEDULE_PHASES:
        report.add_check(f"MASTER_{phase.replace(' ', '_').upper()}", phase in doc, phase)


def check_master_schedule_keywords(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["master_schedule"])
    for kw in MASTER_SCHEDULE_KEYWORDS:
        report.add_check(f"MASTER_KW_{kw.upper()}", kw in doc, kw)


def check_phase_a_complete_in_master(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["master_schedule"])
    for marker in PHASE_A_COMPLETE_MARKERS:
        report.add_check(f"PHASE_A_{marker.replace('.', '_').upper()}", marker in doc, marker)
    report.add_check("PHASE_A_STATUS_COMPLETE", "✅ 완료" in doc or "완료" in doc, "Phase A 완료 표시")


def check_phase_b_complete_in_master(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["master_schedule"])
    for marker in PHASE_B_COMPLETE_MARKERS:
        report.add_check(f"PHASE_B_{marker.replace('.', '_').replace('-', '_').upper()}", marker in doc, marker)


def check_as_built_matrix_domains(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["as_built_matrix"]).lower()
    for domain in AS_BUILT_DOMAINS:
        report.add_check(f"AS_BUILT_{domain.upper()}", domain.lower() in doc, domain)


def check_as_built_warehouse_table(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["as_built_matrix"])
    for warehouse in ["drafts", "approvals", "execution_plans", "evidence", "artifacts", "uploads"]:
        report.add_check(f"AS_BUILT_WH_{warehouse.upper()}", warehouse in doc, warehouse)
    report.add_check("AS_BUILT_SESSION_BLOCKED", "BLOCKED" in doc and "sessions" in doc, "session_store BLOCKED 표시")


def check_completion_checklist_phases(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["completion_checklist"])
    for phase in CHECKLIST_PHASES:
        report.add_check(f"CHECKLIST_{phase.replace(' ', '_').upper()}", phase in doc, phase)


def check_completion_checklist_dod(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["completion_checklist"])
    report.add_check("CHECKLIST_HAS_DOD", "완료 선언 조건" in doc, "완료 선언 조건 명시")
    report.add_check("CHECKLIST_HAS_FORBIDDEN", "FORBIDDEN_IMPORT=0" in doc, "FORBIDDEN_IMPORT=0 조건")
    report.add_check("CHECKLIST_HAS_SECURITY", "SECURITY_PATTERN=0" in doc, "SECURITY_PATTERN=0 조건")


def check_next_sequence_keywords(report: AuditReport) -> None:
    doc = _read(REQUIRED_SCHEDULE_DOCS["next_sequence"])
    for kw in NEXT_SEQUENCE_KEYWORDS:
        report.add_check(f"NEXT_SEQ_{kw.upper()}", kw in doc, kw)


def check_punch_list_priorities(report: AuditReport) -> None:
    doc = _read(REQUIRED_REPORT_DOCS["punch_list"])
    for priority in PUNCH_LIST_PRIORITIES:
        report.add_check(f"PUNCH_{priority}", priority in doc, priority)
    report.add_check("PUNCH_HAS_G2B", "G2B" in doc, "G2B 미처리 항목")
    report.add_check("PUNCH_HAS_EUM", "Eum" in doc or "eum" in doc, "Eum 미처리 항목")


def check_existing_governance_docs_intact(report: AuditReport) -> None:
    existing_docs = [
        ARCH / "governance_gate_matrix.md",
        ARCH / "shared_warehouse_model.md",
        ARCH / "domain_room_allocation_rule.md",
    ]
    for p in existing_docs:
        report.add_check(f"EXISTING_{p.stem.upper()}", p.exists(), str(p.relative_to(ROOT)))


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_schedule_docs_exist(report)
    check_report_docs_exist(report)
    check_master_schedule_phases(report)
    check_master_schedule_keywords(report)
    check_phase_a_complete_in_master(report)
    check_phase_b_complete_in_master(report)
    check_as_built_matrix_domains(report)
    check_as_built_warehouse_table(report)
    check_completion_checklist_phases(report)
    check_completion_checklist_dod(report)
    check_next_sequence_keywords(report)
    check_punch_list_priorities(report)
    check_existing_governance_docs_intact(report)
    return report


if __name__ == "__main__":
    report = run_audit()
    summary = report.summary()
    out_path = ROOT / "data" / "app_construction_schedule_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"총 검사: {summary['total_checks']}")
    print(f"통과:   {summary['passed']}")
    print(f"실패:   {summary['failed']}")
    for issue in summary["issues"]:
        print(f"  [{issue['severity']}] {issue['code']}: {issue['message']}")
    print(f"저장:   {out_path}")
    if summary["failed"] > 0:
        raise SystemExit(1)
