"""APP_UI_SHELL_SKELETON_01 감사 스크립트.

실제 생성된 UI shell 파일이 금지 정책을 위반하지 않는지 검증한다.
- 8개 화면 route 존재
- 공통 컴포넌트 10개 이상
- mock data 파일 존재
- 금지 버튼/액션 코드 없음
- secret/token/cookie raw mock 없음
- backend route 수정 없음
- docker-compose 수정 없음
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
FRONTEND_ROOT = REPO_ROOT / "admin-web" / "src"
AUDIT_ID = "APP_UI_SHELL_SKELETON"

VERDICT_READY = "APP_UI_SHELL_SKELETON_READY"
VERDICT_WARN = "APP_UI_SHELL_SKELETON_WITH_WARN"
VERDICT_BLOCKED = "APP_UI_SHELL_SKELETON_BLOCKED"

REQUIRED_ROUTES = [
    "app/assistant/page.tsx",
    "app/assistant/tasks/page.tsx",
    "app/assistant/tasks/[id]/page.tsx",
    "app/assistant/approval/page.tsx",
    "app/assistant/external-sites/page.tsx",
    "app/assistant/logs/page.tsx",
    "app/assistant/storage/page.tsx",
    "app/assistant/deployment/page.tsx",
]

REQUIRED_COMPONENTS = [
    "components/assistant/GateBadge.tsx",
    "components/assistant/BackendStatusCard.tsx",
    "components/assistant/StorageStatusCard.tsx",
    "components/assistant/ProviderCard.tsx",
    "components/assistant/TaskTable.tsx",
    "components/assistant/TaskDetailPanel.tsx",
    "components/assistant/AuditLogList.tsx",
    "components/assistant/ForbiddenActionBanner.tsx",
    "components/assistant/DryRunNotice.tsx",
    "components/assistant/DeploymentSopPanel.tsx",
]

MOCK_DATA_PATH = "lib/assistant/mock.ts"

FORBIDDEN_PATTERNS = [
    (r"onClick.*execute[^d]", "execute action onClick"),
    (r"onClick.*approveExecute", "approve_execute onClick"),
    (r"onClick.*dryRunDisable", "dry_run_disable onClick"),
    (r"onClick.*serverRestart", "server_restart onClick"),
    (r"onClick.*dockerCompose", "docker_compose onClick"),
    (r"onClick.*payment[^F]", "payment onClick"),
    (r"onClick.*dnsSave", "dns_save onClick"),
    (r"fetch.*POST.*execute", "fetch POST execute"),
    (r"fetch.*POST.*approve.*exec", "fetch POST approve+exec"),
]

FORBIDDEN_SECRET_PATTERNS = [
    (r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', "token raw value in mock"),
    (r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', "cookie raw value in mock"),
    (r'"password"\s*:\s*"[^"]{3,}"', "password raw value in mock"),
    (r'"secret"\s*:\s*"[^"]{3,}"', "secret raw value in mock"),
]

PROTECTED_BACKEND_FILES = [
    "ai_orchestrator/routers/registry.py",
    "ai_orchestrator/main.py",
    "docker-compose.yml",
    "docker-compose.yaml",
]


@dataclass
class CheckResult:
    name: str
    status: Literal["PASS", "WARN", "FAIL"]
    message: str = ""


@dataclass
class AuditReport:
    generated_at: str = ""
    audit_id: str = AUDIT_ID
    checks: list[CheckResult] = field(default_factory=list)
    verdict: str = ""

    def add(self, name: str, status: Literal["PASS", "WARN", "FAIL"], message: str = "") -> None:
        self.checks.append(CheckResult(name, status, message))

    def summary(self) -> dict:
        passed = sum(1 for c in self.checks if c.status == "PASS")
        warned = sum(1 for c in self.checks if c.status == "WARN")
        failed = sum(1 for c in self.checks if c.status == "FAIL")
        return {
            "audit_id": self.audit_id,
            "generated_at": self.generated_at,
            "verdict": self.verdict,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "total": len(self.checks),
            "checks": [{"name": c.name, "status": c.status, "message": c.message} for c in self.checks],
        }


def check_routes(report: AuditReport) -> None:
    missing = []
    for route in REQUIRED_ROUTES:
        path = FRONTEND_ROOT / route
        if not path.exists():
            # 라우트 그룹 `(legacy)` 로 옮겨진 화면도 같은 화면(URL 불변)
            path = FRONTEND_ROOT / route.replace("app/assistant/", "app/assistant/(legacy)/", 1)
        if path.exists():
            report.add(
                f"route_{route.replace('/', '_').replace('[', '').replace(']', '').replace('.tsx', '')}",
                "PASS",
                f"{route} 존재",
            )
        else:
            missing.append(route)
            report.add(
                f"route_{route.replace('/', '_').replace('[', '').replace(']', '').replace('.tsx', '')}",
                "FAIL",
                f"{route} 없음",
            )
    if not missing:
        report.add("routes_all_8_present", "PASS", "8개 화면 route 모두 존재")


def check_components(report: AuditReport) -> None:
    missing = []
    for comp in REQUIRED_COMPONENTS:
        path = FRONTEND_ROOT / comp
        if path.exists():
            report.add(f"comp_{Path(comp).stem.lower()}", "PASS", f"{comp} 존재")
        else:
            missing.append(comp)
            report.add(f"comp_{Path(comp).stem.lower()}", "FAIL", f"{comp} 없음")
    if len(missing) == 0:
        report.add("components_all_present", "PASS", f"{len(REQUIRED_COMPONENTS)}개 컴포넌트 모두 존재")


def check_mock_data(report: AuditReport) -> None:
    mock_path = FRONTEND_ROOT / MOCK_DATA_PATH
    if mock_path.exists():
        report.add("mock_data_file_exists", "PASS", f"{MOCK_DATA_PATH} 존재")
    else:
        report.add("mock_data_file_exists", "FAIL", f"{MOCK_DATA_PATH} 없음")
        return

    content = mock_path.read_text(encoding="utf-8")
    for pattern, name in FORBIDDEN_SECRET_PATTERNS:
        if re.search(pattern, content):
            report.add(f"mock_secret_{name.replace(' ', '_')}", "FAIL", f"mock에 {name} 발견")
        else:
            report.add(f"mock_secret_{name.replace(' ', '_')}", "PASS", f"mock에 {name} 없음")


def check_forbidden_actions(report: AuditReport) -> None:
    assistant_dir = FRONTEND_ROOT / "app" / "assistant"
    comp_dir = FRONTEND_ROOT / "components" / "assistant"
    files = (
        list(assistant_dir.rglob("*.tsx")) + list(comp_dir.rglob("*.tsx"))
        if comp_dir.exists()
        else list(assistant_dir.rglob("*.tsx"))
    )

    violations: list[str] = []
    for f in files:
        content = f.read_text(encoding="utf-8")
        for pattern, name in FORBIDDEN_PATTERNS:
            if re.search(pattern, content):
                violations.append(f"{f.name}: {name}")

    if not violations:
        report.add("forbidden_actions_clean", "PASS", "금지 액션 코드 없음")
    else:
        for v in violations:
            report.add(f"forbidden_violation_{v[:40].replace(' ', '_')}", "FAIL", v)


def check_backend_unchanged(report: AuditReport) -> None:
    for rel_path in PROTECTED_BACKEND_FILES:
        p = REPO_ROOT / rel_path
        if not p.exists():
            report.add(f"backend_protected_{Path(rel_path).name}", "PASS", f"{rel_path} 없음 — 수정 없음")
            continue
        # git diff로 스테이지/워킹 변경 확인
        import subprocess

        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", rel_path],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            encoding="utf-8",
        )
        changed = rel_path in result.stdout
        if changed:
            report.add(
                f"backend_protected_{Path(rel_path).name}", "FAIL", f"{rel_path} 변경됨 — backend route 수정 금지"
            )
        else:
            report.add(f"backend_protected_{Path(rel_path).name}", "PASS", f"{rel_path} 변경 없음")


def check_types_file(report: AuditReport) -> None:
    types_path = FRONTEND_ROOT / "types" / "assistant.ts"
    if types_path.exists():
        report.add("types_assistant_exists", "PASS", "types/assistant.ts 존재")
    else:
        report.add("types_assistant_exists", "WARN", "types/assistant.ts 없음 — 타입 선언 권장")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_routes(report)
    check_components(report)
    check_mock_data(report)
    check_forbidden_actions(report)
    check_backend_unchanged(report)
    check_types_file(report)

    summary = report.summary()
    if summary["failed"] > 0:
        report.verdict = VERDICT_BLOCKED
    elif summary["warned"] > 0:
        report.verdict = VERDICT_WARN
    else:
        report.verdict = VERDICT_READY
    return report


if __name__ == "__main__":
    report = run_audit()
    summary = report.summary()

    out_path = REPO_ROOT / "data" / "app_ui_shell_skeleton_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] UI Shell Skeleton Audit")
    print("=" * 70)
    for c in report.checks:
        mark = "✓" if c.status == "PASS" else ("△" if c.status == "WARN" else "✗")
        print(f"  [{c.status:<4}] {mark} {c.name}: {c.message}")
    print("=" * 70)
    print(f"PASS={summary['passed']} WARN={summary['warned']} FAIL={summary['failed']}")
    print(f"VERDICT: {report.verdict}")
    print("=" * 70)

    if summary["failed"] > 0:
        raise SystemExit(1)
