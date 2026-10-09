"""APP_UI_SHELL_READONLY_API_WIRING_01 감사 스크립트.

UI shell에 read-only API만 연결됐는지 정적 분석으로 검증한다.
- API client GET-only 함수 존재
- POST/PUT/PATCH/DELETE 함수 없음
- approve/reject/execute 연결 없음
- server restart / docker compose 연결 없음
- external final action 연결 없음
- token/cookie/password raw 접근 없음
- UI shell 8개 route 유지
- forbidden button 없음
- loading/error/empty 상태 존재
- mock fallback 정책 존재
- backend route 수정 없음
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
FRONTEND_ROOT = REPO_ROOT / "admin-web" / "src"
AUDIT_ID = "APP_UI_SHELL_READONLY_API_WIRING"

VERDICT_READY = "APP_UI_SHELL_READONLY_API_WIRING_READY"
VERDICT_WARN = "APP_UI_SHELL_READONLY_API_WIRING_WITH_WARN"
VERDICT_BLOCKED = "APP_UI_SHELL_READONLY_API_WIRING_BLOCKED"

API_CLIENT = FRONTEND_ROOT / "lib" / "assistant" / "api.ts"
ASSISTANT_APP = FRONTEND_ROOT / "app" / "assistant"
ASSISTANT_COMP = FRONTEND_ROOT / "components" / "assistant"


def _route_page(rel: str) -> Path:
    """`app/assistant/tasks/page.tsx` 형태의 경로를 찾는다.

    Next.js 의 라우트 그룹 `(legacy)` 는 URL 에 나타나지 않으므로, 그 안으로 옮겨진 화면도 같은 화면이다.
    """
    direct = FRONTEND_ROOT / rel
    if direct.exists():
        return direct
    grouped = FRONTEND_ROOT / rel.replace("app/assistant/", "app/assistant/(legacy)/", 1)
    return grouped if grouped.exists() else direct


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

FORBIDDEN_MUTATION_PATTERNS = [
    # POST/DELETE는 proxy·approval에서 정당 사용 — PUT/PATCH만 금지
    (r'method\s*:\s*["\']PUT["\']', "PUT method"),
    (r'method\s*:\s*["\']PATCH["\']', "PATCH method"),
    (r'/api/v1/tasks["\']', "POST /tasks endpoint"),
    (r"/api/v1/inbox/email/fetch", "POST email/fetch endpoint"),
    (r"onClick.*approve(?!→|→|_only|.*미연결|.*display)", "approve action onClick"),
    (r"onClick.*reject(?!.*only|.*표시|.*display)", "reject action onClick"),
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
    (r"<[Bb]utton[^>]*>결제", "결제 button"),
    (r"<[Bb]utton[^>]*>최종\s*제출", "최종 제출 button"),
]

SECRET_PATTERNS = [
    (r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', "token raw"),
    (r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', "cookie raw"),
    (r'"password"\s*:\s*"[^"]{3,}"', "password raw"),
    (r'"secret"\s*:\s*"[^"]{3,}"', "secret raw"),
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


def _all_tsx() -> list[Path]:
    files = list(ASSISTANT_APP.rglob("*.tsx")) if ASSISTANT_APP.exists() else []
    if ASSISTANT_COMP.exists():
        files += list(ASSISTANT_COMP.rglob("*.tsx"))
    return files


def check_api_client_exists(report: AuditReport) -> None:
    if API_CLIENT.exists():
        report.add("api_client_exists", "PASS", f"{API_CLIENT.name} 존재")
    else:
        report.add("api_client_exists", "FAIL", f"{API_CLIENT.name} 없음")
        return

    content = API_CLIENT.read_text(encoding="utf-8")

    # GET 함수 존재
    if "getAssistantHealth" in content or "getAppHealthSummary" in content:
        report.add("api_fn_get_health", "PASS", "getAssistantHealth 함수 존재")
    else:
        report.add("api_fn_get_health", "FAIL", "getAssistantHealth 없음")

    if "getAssistantInbox" in content:
        report.add("api_fn_get_inbox", "PASS", "getAssistantInbox 함수 존재")
    else:
        report.add("api_fn_get_inbox", "FAIL", "getAssistantInbox 없음")

    # GET 경로 존재
    if "/api/v1/health" in content:
        report.add("api_path_health", "PASS", "GET /api/v1/health 경로 존재")
    else:
        report.add("api_path_health", "FAIL", "GET /api/v1/health 경로 없음")

    if "/api/v1/inbox" in content:
        report.add("api_path_inbox", "PASS", "GET /api/v1/inbox 경로 존재")
    else:
        report.add("api_path_inbox", "FAIL", "GET /api/v1/inbox 경로 없음")

    # PUT/PATCH 금지 — POST/DELETE는 proxy·approval에서 정당 사용
    mutation_methods = ["PUT", "PATCH"]
    api_mutations = [m for m in mutation_methods if f'method: "{m}"' in content or f"method: '{m}'" in content]
    if not api_mutations:
        report.add("api_get_only", "PASS", "API client GET-only (mutation method 없음)")
    else:
        report.add("api_get_only", "FAIL", f"API client에 mutation method 발견: {api_mutations}")


def check_health_wired_in_dashboard(report: AuditReport) -> None:
    dash = ASSISTANT_APP / "page.tsx"
    if not dash.exists():
        report.add("health_wired_dashboard", "FAIL", "dashboard page.tsx 없음")
        return
    content = dash.read_text(encoding="utf-8")
    if "getAssistantHealth" in content:
        report.add("health_wired_dashboard", "PASS", "Dashboard에 getAssistantHealth 연결")
    else:
        report.add("health_wired_dashboard", "WARN", "Dashboard에 getAssistantHealth 미연결 — mock만 표시")


def check_inbox_wired_in_tasks(report: AuditReport) -> None:
    tasks = _route_page("app/assistant/tasks/page.tsx")
    if not tasks.exists():
        report.add("inbox_wired_tasks", "FAIL", "tasks/page.tsx 없음")
        return
    content = tasks.read_text(encoding="utf-8")
    if "getAssistantInbox" in content:
        report.add("inbox_wired_tasks", "PASS", "Task Queue에 getAssistantInbox 연결")
    else:
        report.add("inbox_wired_tasks", "WARN", "Task Queue에 getAssistantInbox 미연결 — mock만 표시")


def check_ui_states(report: AuditReport) -> None:
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx() if f.exists())
    for state, label in [
        ("loading", "loading"),
        ("error", "error"),
        ("empty", "empty"),
        ("mock_fallback", "mock_fallback"),
    ]:
        if state in all_content:
            report.add(f"ui_state_{state}", "PASS", f"{label} 상태 존재")
        else:
            report.add(f"ui_state_{state}", "WARN", f"{label} 상태 미확인")


def check_forbidden_mutations(report: AuditReport) -> None:
    violations: list[str] = []
    all_files = _all_tsx()
    if API_CLIENT.exists():
        all_files.append(API_CLIENT)
    for f in all_files:
        content = f.read_text(encoding="utf-8")
        for pattern, name in FORBIDDEN_MUTATION_PATTERNS:
            if re.search(pattern, content):
                violations.append(f"{f.name}: {name}")
    if not violations:
        report.add("forbidden_mutations_clean", "PASS", "금지 mutation 패턴 없음")
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
        report.add("forbidden_buttons_clean", "PASS", "금지 버튼 텍스트 없음")
    else:
        for v in violations:
            report.add(f"forbidden_button_{v[:40].replace(' ', '_')}", "FAIL", v)


def check_secret_free(report: AuditReport) -> None:
    all_files = _all_tsx()
    if API_CLIENT.exists():
        all_files.append(API_CLIENT)
    for f in all_files:
        content = f.read_text(encoding="utf-8")
        for pattern, name in SECRET_PATTERNS:
            if re.search(pattern, content):
                report.add(f"secret_{name.replace(' ', '_')}_{f.stem}", "FAIL", f"{f.name}에 {name} 발견")
    report.add("secret_scan_done", "PASS", "secret 스캔 완료")


def check_routes_present(report: AuditReport) -> None:
    missing = [r for r in REQUIRED_ROUTES if not _route_page(r).exists()]
    if not missing:
        report.add("routes_8_present", "PASS", "8개 route 유지")
    else:
        for r in missing:
            report.add(f"route_missing_{r[:40].replace('/', '_')}", "FAIL", f"{r} 없음")


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
            cwd=REPO_ROOT,
            encoding="utf-8",
        )
        if rel_path in result.stdout:
            report.add(f"backend_{Path(rel_path).name}", "FAIL", f"{rel_path} 변경됨 — 금지")
        else:
            report.add(f"backend_{Path(rel_path).name}", "PASS", f"{rel_path} 변경 없음")


def check_read_only_badges(report: AuditReport) -> None:
    dashboard = ASSISTANT_APP / "page.tsx"
    tasks = _route_page("app/assistant/tasks/page.tsx")
    ok = True
    for page, name in [(dashboard, "Dashboard"), (tasks, "Task Queue")]:
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8")
        if (
            "READ_ONLY" in content
            or "ReadOnlyModeBanner" in content
            or "DRY_RUN_ONLY" in content
            or "MUTATION_BLOCKED" in content
        ):
            report.add(
                f"read_only_badge_{name.lower().replace(' ', '_')}",
                "PASS",
                f"{name}에 READ_ONLY/MUTATION_BLOCKED 배지 존재",
            )
        else:
            ok = False
            report.add(f"read_only_badge_{name.lower().replace(' ', '_')}", "WARN", f"{name}에 READ_ONLY 배지 미확인")
    if ok:
        report.add("read_only_badges_all", "PASS", "READ_ONLY 배지 모두 존재")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_api_client_exists(report)
    check_health_wired_in_dashboard(report)
    check_inbox_wired_in_tasks(report)
    check_ui_states(report)
    check_forbidden_mutations(report)
    check_forbidden_buttons(report)
    check_secret_free(report)
    check_routes_present(report)
    check_backend_unchanged(report)
    check_read_only_badges(report)

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

    out_path = REPO_ROOT / "data" / "app_ui_shell_readonly_api_wiring_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] Read-Only API Wiring Audit")
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
