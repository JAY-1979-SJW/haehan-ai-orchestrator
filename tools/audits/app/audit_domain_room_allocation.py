"""Domain Room Allocation 구조 감사 스크립트.

집 배정 문서 존재·필수 방 항목·금지 정책 포함 여부를 read-only로 검사한다.
기능 코드 구현 없음. 감사만 수행.
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
    "domain_room_allocation_rule": ROOT / "docs/architecture/domain_room_allocation_rule.md",
    "gabia_room_allocation": ROOT / "docs/architecture/domain_units/gabia_room_allocation.md",
    "g2b_room_allocation": ROOT / "docs/architecture/domain_units/g2b_room_allocation.md",
    "common_domain_room_allocation": ROOT / "docs/architecture/domain_units/common_domain_room_allocation.md",
    "shared_facility_allocation": ROOT / "docs/architecture/shared_facility_allocation.md",
}

REQUIRED_ROOM_KEYWORDS = [
    "entrance/router",
    "resident-card/profile",
    "security-door/gates",
    "inspection/validators",
    "living-room/usecase",
    "external-door/adapter",
    "parking/workflow",
    "warehouse/storage",
    "cctv/audit",
    "alarm/tests",
    "rulebook/docs",
]

REQUIRED_GABIA_UNITS = [
    "gabia/domain-registration",
    "gabia/dns-management",
    "gabia/hosting-management",
    "gabia/mail-management",
    "gabia/account-readonly",
    "gabia/payment-billing",
]

REQUIRED_G2B_UNITS = [
    "g2b/public-notice",
    "g2b/notice-detail",
    "g2b/attachment-download",
    "g2b/openapi-collector",
    "g2b/login-restricted",
    "g2b/bid-analysis",
    "g2b/bid-submit",
    "g2b/e-sign",
    "g2b/evidence-report",
]

REQUIRED_COMMON_DOMAINS = [
    "Hiworks",
    "Google",
    "YouTube",
    "CAD",
    "HWPX",
    "문서 자동화",
    "출퇴근",
    "위험성평가",
]

REQUIRED_SHARED_FACILITIES = [
    "Action Registry",
    "Approval Gate",
    "Permission Model",
    "Workflow",
    "Local Agent Gateway",
    "Browser Execution Gateway",
    "Evidence Store",
    "Report Store",
    "Audit Log",
    "Admin Ops Center",
    "Notification Center",
]

REQUIRED_GATE_DECISIONS = [
    "USER_DIRECT_REQUIRED",
    "LOCAL_AGENT_REQUIRED",
    "BLOCKED",
    "READ_ONLY_ALLOWED",
    "DRAFT_ALLOWED",
]

REQUIRED_FORBIDDEN_PHRASES = [
    "cross-domain 직접 import 금지",
    "session",
    "BLOCKED",
    "USER_DIRECT_REQUIRED",
]


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
            self.issues.append(AuditIssue("WARN", f"ROOM_ALLOC_{name.upper()}", name, detail))

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


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def check_required_docs(report: AuditReport) -> None:
    for key, path in REQUIRED_DOCS.items():
        exists = path.exists() and path.stat().st_size > 100
        report.add_check(
            f"DOC_{key.upper()}",
            exists,
            str(path.relative_to(ROOT)) if exists else f"MISSING: {path.relative_to(ROOT)}",
        )


def check_room_structure_keywords(report: AuditReport) -> None:
    rule_doc = _read(REQUIRED_DOCS["domain_room_allocation_rule"])
    for kw in REQUIRED_ROOM_KEYWORDS:
        report.add_check(
            f"ROOM_KW_{kw.replace('/', '_').upper()}",
            kw in rule_doc,
            kw,
        )


def check_gabia_units(report: AuditReport) -> None:
    doc = _read(REQUIRED_DOCS["gabia_room_allocation"])
    for unit in REQUIRED_GABIA_UNITS:
        report.add_check(f"GABIA_UNIT_{unit.replace('/', '_').upper()}", unit in doc, unit)


def check_g2b_units(report: AuditReport) -> None:
    doc = _read(REQUIRED_DOCS["g2b_room_allocation"])
    for unit in REQUIRED_G2B_UNITS:
        report.add_check(f"G2B_UNIT_{unit.replace('/', '_').upper()}", unit in doc, unit)


def check_common_domains(report: AuditReport) -> None:
    doc = _read(REQUIRED_DOCS["common_domain_room_allocation"])
    for domain in REQUIRED_COMMON_DOMAINS:
        report.add_check(f"COMMON_{domain.replace(' ', '_').upper()}", domain in doc, domain)


def check_shared_facilities(report: AuditReport) -> None:
    doc = _read(REQUIRED_DOCS["shared_facility_allocation"])
    for facility in REQUIRED_SHARED_FACILITIES:
        report.add_check(
            f"FACILITY_{facility.replace(' ', '_').upper()}",
            facility in doc,
            facility,
        )


def check_gate_decisions(report: AuditReport) -> None:
    combined = "".join(_read(p) for p in REQUIRED_DOCS.values())
    for decision in REQUIRED_GATE_DECISIONS:
        report.add_check(f"GATE_DECISION_{decision}", decision in combined, decision)


def check_forbidden_phrases(report: AuditReport) -> None:
    combined = "".join(_read(p) for p in REQUIRED_DOCS.values())
    for phrase in REQUIRED_FORBIDDEN_PHRASES:
        report.add_check(
            f"FORBIDDEN_PHRASE_{phrase.replace(' ', '_').upper()}",
            phrase in combined,
            phrase,
        )


def check_cross_domain_prohibition(report: AuditReport) -> None:
    rule_doc = _read(REQUIRED_DOCS["domain_room_allocation_rule"])
    gabia_doc = _read(REQUIRED_DOCS["gabia_room_allocation"])
    g2b_doc = _read(REQUIRED_DOCS["g2b_room_allocation"])
    common_doc = _read(REQUIRED_DOCS["common_domain_room_allocation"])
    report.add_check(
        "CROSS_DOMAIN_PROHIBITION_IN_RULE",
        "다른 Domain Unit 직접 import 금지" in rule_doc,
        "domain_room_allocation_rule.md에 cross-domain 금지 문구",
    )
    report.add_check(
        "CROSS_DOMAIN_PROHIBITION_IN_GABIA",
        "cross-domain 직접 import 금지" in gabia_doc,
        "gabia_room_allocation.md에 cross-domain 금지 문구",
    )
    report.add_check(
        "CROSS_DOMAIN_PROHIBITION_IN_G2B",
        "cross-domain 직접 import 금지" in g2b_doc,
        "g2b_room_allocation.md에 cross-domain 금지 문구",
    )
    report.add_check(
        "CROSS_DOMAIN_PROHIBITION_IN_COMMON",
        "cross-domain 직접 import 금지" in common_doc,
        "common_domain_room_allocation.md에 cross-domain 금지 문구",
    )


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_required_docs(report)
    check_room_structure_keywords(report)
    check_gabia_units(report)
    check_g2b_units(report)
    check_common_domains(report)
    check_shared_facilities(report)
    check_gate_decisions(report)
    check_forbidden_phrases(report)
    check_cross_domain_prohibition(report)
    return report


if __name__ == "__main__":
    report = run_audit()
    summary = report.summary()
    out_path = ROOT / "data" / "domain_room_allocation_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"총 검사: {summary['total_checks']}")
    print(f"통과:   {summary['passed']}")
    print(f"실패:   {summary['failed']}")
    for issue in summary["issues"]:
        print(f"  [{issue['severity']}] {issue['code']}: {issue['message']}")
    print(f"저장:   {out_path}")
    if summary["failed"] > 0:
        raise SystemExit(1)
