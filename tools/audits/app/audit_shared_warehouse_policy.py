"""Shared Warehouse Policy 감사 스크립트.

공용창고 정책 문서 존재·manifest 검사·금지 경로·domain 배정을 read-only로 검사한다.
data/sessions 파일 내용 열람 금지. 존재 여부만 확인.
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
    "shared_warehouse_model": ROOT / "docs/architecture/shared_warehouse_model.md",
    "domain_warehouse_allocation": ROOT / "docs/architecture/domain_warehouse_allocation.md",
    "storage_boundary_policy": ROOT / "docs/architecture/storage_boundary_policy.md",
    "shared_warehouse_manifest": ROOT / "docs/architecture/shared_warehouse_manifest.json",
}

REQUIRED_WAREHOUSE_KEYS = [
    "draft",
    "approval",
    "execution_plan",
    "evidence",
    "report_human",
    "report_machine",
    "artifact",
    "upload",
    "audit_log",
    "manual_visit",
    "session_store",
]

REQUIRED_BLOCKED_PATTERNS = [
    "*cookie*",
    "*session*",
    "*token*",
    "*password*",
    "*.env",
    "*.pem",
    "*.key",
]

REQUIRED_DOMAINS = [
    "gabia",
    "g2b",
    "hiworks",
    "google",
    "youtube",
    "eum",
    "cad",
    "hwpx",
    "document_automation",
    "attendance",
    "safety_docs",
    "risk_assessment",
]

REQUIRED_POLICY_KEYWORDS_IN_BOUNDARY = [
    "BLOCKED",
    "data/sessions",
    "session/cookie/token/password 저장 금지",
    "READ_ONLY_EVIDENCE",
    "STORAGE_BOUNDARY",
    "task_id",
]

REQUIRED_FORBIDDEN_PHRASES_IN_MODEL = [
    "BLOCKED",
    "data/sessions",
    "봉인",
    "READ_ONLY_EVIDENCE",
    "task_id",
    "session/cookie/token/password",
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
            self.issues.append(AuditIssue("WARN", f"WAREHOUSE_{name.upper()}", name, detail))

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


def _load_manifest() -> dict:
    p = REQUIRED_DOCS["shared_warehouse_manifest"]
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def check_required_docs(report: AuditReport) -> None:
    for key, path in REQUIRED_DOCS.items():
        exists = path.exists() and path.stat().st_size > 100
        report.add_check(
            f"DOC_{key.upper()}",
            exists,
            str(path.relative_to(ROOT)) if exists else f"MISSING: {path.relative_to(ROOT)}",
        )


def check_manifest_parseable(report: AuditReport) -> None:
    manifest = _load_manifest()
    report.add_check("MANIFEST_PARSEABLE", bool(manifest), "manifest JSON parse 가능")


def check_manifest_warehouses(report: AuditReport) -> None:
    manifest = _load_manifest()
    warehouses = manifest.get("warehouses", {})
    for key in REQUIRED_WAREHOUSE_KEYS:
        report.add_check(f"WAREHOUSE_KEY_{key.upper()}", key in warehouses, key)


def check_session_blocked(report: AuditReport) -> None:
    manifest = _load_manifest()
    blocked_paths = manifest.get("blocked_paths", [])
    report.add_check(
        "SESSION_IN_BLOCKED_PATHS",
        "data/sessions" in blocked_paths,
        "blocked_paths에 data/sessions 포함",
    )
    session_policy = manifest.get("session_policy", "")
    report.add_check(
        "SESSION_POLICY_BLOCKED",
        session_policy == "BLOCKED",
        f"session_policy=BLOCKED (현재: {session_policy!r})",
    )
    warehouses = manifest.get("warehouses", {})
    session_store = warehouses.get("session_store", {})
    report.add_check(
        "SESSION_STORE_POLICY_BLOCKED",
        session_store.get("policy") == "BLOCKED",
        "warehouses.session_store.policy == BLOCKED",
    )


def check_manual_visit_policy(report: AuditReport) -> None:
    manifest = _load_manifest()
    policy = manifest.get("manual_visit_policy", "")
    report.add_check(
        "MANUAL_VISIT_POLICY_READ_ONLY",
        policy == "READ_ONLY_EVIDENCE",
        f"manual_visit_policy=READ_ONLY_EVIDENCE (현재: {policy!r})",
    )
    warehouses = manifest.get("warehouses", {})
    mv = warehouses.get("manual_visit", {})
    report.add_check(
        "MANUAL_VISIT_WAREHOUSE_READ_ONLY",
        mv.get("policy") == "READ_ONLY_EVIDENCE",
        "warehouses.manual_visit.policy == READ_ONLY_EVIDENCE",
    )


def check_required_task_scoped_paths(report: AuditReport) -> None:
    manifest = _load_manifest()
    scoped = manifest.get("required_task_scoped_paths", [])
    report.add_check(
        "TASK_SCOPED_PATHS_EXIST",
        len(scoped) >= 4,
        f"required_task_scoped_paths {len(scoped)}개 (최소 4개)",
    )
    for path_pattern in ("data/drafts", "data/evidence", "data/artifacts", "data/uploads"):
        found = any(path_pattern in p for p in scoped)
        report.add_check(f"TASK_SCOPE_{path_pattern.replace('/', '_').upper()}", found, path_pattern)


def check_report_evidence_separation(report: AuditReport) -> None:
    manifest = _load_manifest()
    report_paths = manifest.get("report_paths", {})
    evidence_paths = manifest.get("evidence_paths", {})
    report.add_check(
        "REPORT_EVIDENCE_SEPARATED",
        bool(report_paths) and bool(evidence_paths),
        "report_paths와 evidence_paths 분리 정의",
    )
    report.add_check(
        "DOCS_REPORTS_FOR_HUMAN",
        "docs/reports/" in report_paths.get("human_readable", ""),
        "docs/reports/가 human_readable report 경로",
    )
    report.add_check(
        "DATA_REPORTS_FOR_MACHINE",
        "data/reports/" in report_paths.get("machine_readable", ""),
        "data/reports/가 machine_readable report 경로",
    )


def check_domain_allocation(report: AuditReport) -> None:
    doc = _read(REQUIRED_DOCS["domain_warehouse_allocation"])
    for domain in REQUIRED_DOMAINS:
        report.add_check(f"DOMAIN_{domain.upper()}", domain in doc, domain)


def check_blocked_file_patterns(report: AuditReport) -> None:
    manifest = _load_manifest()
    patterns = manifest.get("blocked_file_patterns", [])
    for pattern in REQUIRED_BLOCKED_PATTERNS:
        report.add_check(
            f"BLOCKED_PATTERN_{pattern.replace('*', '').replace('.', '_').upper()}",
            pattern in patterns,
            pattern,
        )


def check_policy_keywords_in_boundary(report: AuditReport) -> None:
    doc = _read(REQUIRED_DOCS["storage_boundary_policy"])
    for kw in REQUIRED_POLICY_KEYWORDS_IN_BOUNDARY:
        report.add_check(
            f"BOUNDARY_KW_{kw.replace('/', '_').replace(' ', '_').upper()}",
            kw in doc,
            kw,
        )


def check_forbidden_phrases_in_model(report: AuditReport) -> None:
    doc = _read(REQUIRED_DOCS["shared_warehouse_model"])
    for phrase in REQUIRED_FORBIDDEN_PHRASES_IN_MODEL:
        report.add_check(
            f"MODEL_PHRASE_{phrase.replace('/', '_').replace(' ', '_').upper()}",
            phrase in doc,
            phrase,
        )


def check_sessions_not_read_in_policy(report: AuditReport) -> None:
    """sessions 파일 내용을 이 스크립트에서 열람하지 않음을 확인 (상수 검사)."""
    sessions_path = ROOT / "data" / "sessions"
    exists = sessions_path.exists()
    report.add_check(
        "SESSIONS_PATH_EXISTS_NOT_READ",
        True,
        f"data/sessions 존재={exists} (내용 열람 없음 — 정책 준수)",
    )


def check_approval_policy_fields(report: AuditReport) -> None:
    manifest = _load_manifest()
    approval = manifest.get("approval_policy", {})
    required_fields = approval.get("required_fields", [])
    for field_name in ("approver", "timestamp", "scope", "expiry", "decision"):
        report.add_check(
            f"APPROVAL_FIELD_{field_name.upper()}",
            field_name in required_fields,
            field_name,
        )
    report.add_check(
        "APPROVAL_IMMUTABLE",
        approval.get("immutable") is True,
        "approval 레코드 불변(immutable=true)",
    )
    report.add_check(
        "APPROVAL_BYPASS_BLOCKED",
        approval.get("bypass") == "BLOCKED",
        "approval bypass=BLOCKED",
    )


def check_audit_policy_fields(report: AuditReport) -> None:
    manifest = _load_manifest()
    audit = manifest.get("audit_policy", {})
    required_fields = audit.get("required_fields", [])
    for field_name in ("who", "when", "what", "result", "task_id"):
        report.add_check(
            f"AUDIT_FIELD_{field_name.upper()}",
            field_name in required_fields,
            field_name,
        )
    report.add_check(
        "AUDIT_MODE_APPEND_ONLY",
        audit.get("mode") == "APPEND_ONLY",
        "audit mode=APPEND_ONLY",
    )
    report.add_check(
        "AUDIT_DELETION_BLOCKED",
        audit.get("deletion") == "BLOCKED",
        "audit deletion=BLOCKED",
    )


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_required_docs(report)
    check_manifest_parseable(report)
    check_manifest_warehouses(report)
    check_session_blocked(report)
    check_manual_visit_policy(report)
    check_required_task_scoped_paths(report)
    check_report_evidence_separation(report)
    check_domain_allocation(report)
    check_blocked_file_patterns(report)
    check_policy_keywords_in_boundary(report)
    check_forbidden_phrases_in_model(report)
    check_sessions_not_read_in_policy(report)
    check_approval_policy_fields(report)
    check_audit_policy_fields(report)
    return report


if __name__ == "__main__":
    report = run_audit()
    summary = report.summary()
    out_path = ROOT / "data" / "shared_warehouse_policy_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"총 검사: {summary['total_checks']}")
    print(f"통과:   {summary['passed']}")
    print(f"실패:   {summary['failed']}")
    for issue in summary["issues"]:
        print(f"  [{issue['severity']}] {issue['code']}: {issue['message']}")
    print(f"저장:   {out_path}")
    if summary["failed"] > 0:
        raise SystemExit(1)
