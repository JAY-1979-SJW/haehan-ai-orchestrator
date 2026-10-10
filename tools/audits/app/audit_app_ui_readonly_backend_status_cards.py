"""APP_UI_READONLY_BACKEND_STATUS_CARDS_01 감사 스크립트.

read-only status card 보강이 mutation 금지 정책과 충돌하지 않는지 검증한다.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from tools.audits.app.audit_app_ui_shell_readonly_api_wiring import _route_page

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
FRONTEND_ROOT = REPO_ROOT / "admin-web" / "src"
AUDIT_ID = "APP_UI_READONLY_BACKEND_STATUS_CARDS"

VERDICT_READY = "APP_UI_READONLY_BACKEND_STATUS_CARDS_READY"
VERDICT_WARN = "APP_UI_READONLY_BACKEND_STATUS_CARDS_WITH_WARN"
VERDICT_BLOCKED = "APP_UI_READONLY_BACKEND_STATUS_CARDS_BLOCKED"

ASSISTANT_APP = FRONTEND_ROOT / "app" / "assistant"
ASSISTANT_COMP = FRONTEND_ROOT / "components" / "assistant"



API_CLIENT = FRONTEND_ROOT / "lib" / "assistant" / "api.ts"
TYPES_FILE = FRONTEND_ROOT / "types" / "assistant.ts"

REQUIRED_NEW_COMPONENTS = [
    "ReadOnlyModeBanner.tsx",
    "ApiConnectionStateBadge.tsx",
    "EmptyStatePanel.tsx",
    "FutureEndpointNotice.tsx",
]

FORBIDDEN_MUTATION_PATTERNS = [
    # POST/DELETE는 proxy·approval에서 정당 사용 — PUT/PATCH만 금지
    (r'method\s*:\s*["\']PUT["\']', "PUT method"),
    (r'method\s*:\s*["\']PATCH["\']', "PATCH method"),
    (r"/api/v1/inbox/email/fetch", "POST email/fetch"),
    (r"onClick.*execute[^d]", "execute onClick"),
    (r"onClick.*serverRestart", "server_restart onClick"),
    (r"onClick.*dockerCompose", "docker_compose onClick"),
    (r"onClick.*dnsSave", "dns_save onClick"),
    (r"onClick.*payment[^F]", "payment onClick"),
    (r"onClick.*finalSubmit", "final_submit onClick"),
]

FORBIDDEN_BUTTON_TEXTS = [
    (r"<[Bb]utton[^>]*>실행하기", "실행하기 button"),
    (r"<[Bb]utton[^>]*>지금\s*실행", "지금 실행 button"),
    (r"<[Bb]utton[^>]*>DRY_RUN\s*해제", "DRY_RUN 해제 button"),
    (r"<[Bb]utton[^>]*>서버\s*재시작", "서버 재시작 button"),
    (r"<[Bb]utton[^>]*>compose\s*실행", "compose 실행 button"),
]

SECRET_PATTERNS = [
    (r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', "token raw"),
    (r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', "cookie raw"),
    (r'"password"\s*:\s*"[^"]{3,}"', "password raw"),
    (r'"secret"\s*:\s*"[^"]{3,}"', "secret raw"),
]

PROTECTED_BACKEND_FILES = [
    "ai_orchestrator/routers/registry.py",
    "docker-compose.yml",
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


def _all_tsx() -> list[Path]:
    files = list(ASSISTANT_APP.rglob("*.tsx")) if ASSISTANT_APP.exists() else []
    if ASSISTANT_COMP.exists():
        files += list(ASSISTANT_COMP.rglob("*.tsx"))
    return files


def _all_frontend() -> list[Path]:
    return _all_tsx() + ([API_CLIENT] if API_CLIENT.exists() else [])


def check_new_components(report: AuditReport) -> None:
    for comp in REQUIRED_NEW_COMPONENTS:
        path = ASSISTANT_COMP / comp
        if path.exists():
            report.add(f"comp_{Path(comp).stem.lower()}", "PASS", f"{comp} 존재")
        else:
            report.add(f"comp_{Path(comp).stem.lower()}", "FAIL", f"{comp} 없음")


def check_dashboard_enhanced(report: AuditReport) -> None:
    dash = ASSISTANT_APP / "page.tsx"
    if not dash.exists():
        report.add("dashboard_enhanced", "FAIL", "page.tsx 없음")
        return
    content = dash.read_text(encoding="utf-8")
    checks = [
        ("getAppHealthSummary", "health API 연결"),
        ("ReadOnlyModeBanner", "ReadOnlyModeBanner 사용"),
        ("ApiConnectionStateBadge", "ApiConnectionStateBadge 사용"),
        ("makeMeta", "makeMeta 사용"),
    ]
    for key, label in checks:
        if key in content:
            report.add(f"dashboard_{key.lower()}", "PASS", f"Dashboard: {label}")
        else:
            report.add(f"dashboard_{key.lower()}", "WARN", f"Dashboard: {label} 미확인")
    # 현행 계약: 옛 getAssistantHealth·FutureEndpointNotice 는 대시보드에 없어야 한다
    # (APP_UI_READONLY_STATUS_CARDS_API_BIND_01 — getAppHealthSummary 로 대체, storage/status 구현 후 제거).
    for key, label in (
        ("getAssistantHealth", "legacy health API"),
        ("FutureEndpointNotice", "FutureEndpointNotice"),
    ):
        if key in content:
            report.add(f"dashboard_no_{key.lower()}", "WARN", f"Dashboard: {label} 잔존 (없어야 함)")
        else:
            report.add(f"dashboard_no_{key.lower()}", "PASS", f"Dashboard: {label} 없음")


def check_tasks_enhanced(report: AuditReport) -> None:
    tasks = _route_page("app/assistant/tasks/page.tsx")
    if not tasks.exists():
        report.add("tasks_enhanced", "FAIL", "tasks/page.tsx 없음")
        return
    content = tasks.read_text(encoding="utf-8")
    checks = [
        ("getAssistantInbox", "inbox API 연결"),
        ("ReadOnlyModeBanner", "ReadOnlyModeBanner 사용"),
        ("EmptyStatePanel", "EmptyStatePanel 사용"),
        ("DRY_RUN_ONLY", "DRY_RUN_ONLY 배지"),
        ("MUTATION_BLOCKED", "MUTATION_BLOCKED 배지"),
    ]
    for key, label in checks:
        if key in content:
            report.add(f"tasks_{key.lower()}", "PASS", f"Tasks: {label}")
        else:
            report.add(f"tasks_{key.lower()}", "WARN", f"Tasks: {label} 미확인")


def check_deployment_display_only(report: AuditReport) -> None:
    deploy = _route_page("app/assistant/deployment/page.tsx")
    if not deploy.exists():
        report.add("deployment_display_only", "FAIL", "deployment/page.tsx 없음")
        return
    content = deploy.read_text(encoding="utf-8")
    if re.search(r"<[Bb]utton[^>]*>서버\s*재시작", content):
        report.add("deployment_no_restart_btn", "FAIL", "deployment에 서버 재시작 버튼 발견")
    else:
        report.add("deployment_no_restart_btn", "PASS", "deployment 서버 재시작 버튼 없음")
    if "ReadOnlyModeBanner" in content:
        report.add("deployment_readonly_banner", "PASS", "deployment ReadOnlyModeBanner 존재")
    else:
        report.add("deployment_readonly_banner", "WARN", "deployment ReadOnlyModeBanner 미확인")
    if "server_apply_allowed=false" in content:
        report.add("deployment_server_apply_false", "PASS", "server_apply_allowed=false 표시")
    else:
        report.add("deployment_server_apply_false", "WARN", "server_apply_allowed=false 미확인")


def check_api_state_model(report: AuditReport) -> None:
    if not TYPES_FILE.exists():
        report.add("api_state_model", "FAIL", "types/assistant.ts 없음")
        return
    content = TYPES_FILE.read_text(encoding="utf-8")
    for key, label in [
        ("ApiConnectionMeta", "ApiConnectionMeta 인터페이스"),
        ("source", "source 필드"),
        ("last_checked", "last_checked 필드"),
        ("error_kind", "error_kind 필드"),
        ("mutation_allowed", "mutation_allowed 필드"),
        ("is_read_only", "is_read_only 필드"),
    ]:
        if key in content:
            report.add(f"model_{key.lower()}", "PASS", f"types: {label}")
        else:
            report.add(f"model_{key.lower()}", "FAIL", f"types: {label} 없음")


def check_get_only(report: AuditReport) -> None:
    # POST/DELETE는 proxy 엔드포인트·approval 큐에서 정당하게 사용됨 — PUT/PATCH만 금지
    if not API_CLIENT.exists():
        report.add("api_get_only", "FAIL", "api.ts 없음")
        return
    content = API_CLIENT.read_text(encoding="utf-8")
    for method in ["PUT", "PATCH"]:
        if f'method: "{method}"' in content or f"method: '{method}'" in content:
            report.add(f"api_no_{method.lower()}", "FAIL", f"api.ts에 {method} 발견")
        else:
            report.add(f"api_no_{method.lower()}", "PASS", f"api.ts에 {method} 없음")


def check_forbidden_mutations(report: AuditReport) -> None:
    violations: list[str] = []
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        for pattern, name in FORBIDDEN_MUTATION_PATTERNS:
            if re.search(pattern, content):
                violations.append(f"{f.name}: {name}")
    if not violations:
        report.add("forbidden_mutations_clean", "PASS", "금지 mutation 없음")
    else:
        for v in violations:
            report.add(f"mutation_violation_{v[:40].replace(' ', '_')}", "FAIL", v)


def check_forbidden_buttons(report: AuditReport) -> None:
    violations: list[str] = []
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        for pattern, name in FORBIDDEN_BUTTON_TEXTS:
            if re.search(pattern, content):
                violations.append(f"{f.name}: {name}")
    if not violations:
        report.add("forbidden_buttons_clean", "PASS", "금지 버튼 없음")
    else:
        for v in violations:
            report.add(f"forbidden_button_{v[:40].replace(' ', '_')}", "FAIL", v)


def check_secret_free(report: AuditReport) -> None:
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        for pattern, name in SECRET_PATTERNS:
            if re.search(pattern, content):
                report.add(f"secret_{name.replace(' ', '_')}_{f.stem}", "FAIL", f"{f.name}에 {name} 발견")
    report.add("secret_scan_done", "PASS", "secret 스캔 완료")


def check_backend_unchanged(report: AuditReport) -> None:
    for rel_path in PROTECTED_BACKEND_FILES:
        p = REPO_ROOT / rel_path
        if not p.exists():
            report.add(f"backend_{Path(rel_path).name}", "PASS", f"{rel_path} 없음")
            continue
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", rel_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO_ROOT,
        )
        if rel_path in result.stdout:
            report.add(f"backend_{Path(rel_path).name}", "FAIL", f"{rel_path} 변경됨 — 금지")
        else:
            report.add(f"backend_{Path(rel_path).name}", "PASS", f"{rel_path} 변경 없음")


def check_mock_fallback_policy(report: AuditReport) -> None:
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    if "mock_fallback" in all_content or "MOCK_FALLBACK" in all_content:
        report.add("mock_fallback_policy", "PASS", "mock fallback 정책 존재")
    else:
        report.add("mock_fallback_policy", "WARN", "mock fallback 정책 미확인")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_new_components(report)
    check_dashboard_enhanced(report)
    check_tasks_enhanced(report)
    check_deployment_display_only(report)
    check_api_state_model(report)
    check_get_only(report)
    check_forbidden_mutations(report)
    check_forbidden_buttons(report)
    check_secret_free(report)
    check_backend_unchanged(report)
    check_mock_fallback_policy(report)

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

    out_path = REPO_ROOT / "data" / "app_ui_readonly_backend_status_cards_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] Read-Only Backend Status Cards Audit")
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
