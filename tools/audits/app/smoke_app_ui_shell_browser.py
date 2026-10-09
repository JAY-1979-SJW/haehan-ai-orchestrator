"""APP_UI_SHELL_BROWSER_SMOKE_01 정적 smoke 분석 스크립트.

Next.js dev 서버 없이 TSX 파일 정적 분석으로 smoke 검측:
- 8개 route heading 마커 존재
- 금지 버튼/액션 패턴 없음
- secret/token/cookie 원문 없음
- mock provider 12개 존재
- DryRunNotice / ForbiddenActionBanner 사용 확인
- mutation (fetch POST/PUT/DELETE) 없음
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
ASSISTANT_APP = FRONTEND_ROOT / "app" / "assistant"
ASSISTANT_COMP = FRONTEND_ROOT / "components" / "assistant"
MOCK_FILE = FRONTEND_ROOT / "lib" / "assistant" / "mock.ts"


def _page(*parts: str) -> Path:
    """`app/assistant/<parts>` — 직접 경로 우선, 없으면 라우트 그룹 `(legacy)` 아래(URL 불변)."""
    direct = ASSISTANT_APP.joinpath(*parts)
    if direct.exists():
        return direct
    grouped = ASSISTANT_APP.joinpath("(legacy)", *parts)
    return grouped if grouped.exists() else direct


SMOKE_ID = "APP_UI_SHELL_BROWSER_SMOKE"

VERDICT_PASS = "BROWSER_SMOKE_PASS"
VERDICT_WARN = "BROWSER_SMOKE_WARN"
VERDICT_FAIL = "BROWSER_SMOKE_FAIL"

ROUTES = [
    ("page.tsx", "/assistant", "dashboard"),
    ("tasks/page.tsx", "/assistant/tasks", "tasks"),
    ("tasks/[id]/page.tsx", "/assistant/tasks/[id]", "task_detail"),
    ("approval/page.tsx", "/assistant/approval", "approval"),
    ("external-sites/page.tsx", "/assistant/external-sites", "external_sites"),
    ("logs/page.tsx", "/assistant/logs", "logs"),
    ("storage/page.tsx", "/assistant/storage", "storage"),
    ("deployment/page.tsx", "/assistant/deployment", "deployment"),
]

HEADING_MARKERS = {
    "page.tsx": ["어시스턴트", "대시보드", "Dashboard", "Assistant"],
    "tasks/page.tsx": ["태스크", "Task"],
    "tasks/[id]/page.tsx": ["상세", "Detail", "태스크"],
    "approval/page.tsx": ["승인", "Approval"],
    "external-sites/page.tsx": ["외부", "External", "사이트"],
    "logs/page.tsx": ["로그", "Log", "감사"],
    "storage/page.tsx": ["스토리지", "Storage"],
    "deployment/page.tsx": ["배포", "Deploy"],
}

FORBIDDEN_PATTERNS = [
    (r"onClick\s*=\s*\{[^}]*execute[^d]", "execute onClick"),
    (r"onClick\s*=\s*\{[^}]*approveExecute", "approve_execute onClick"),
    (r"onClick\s*=\s*\{[^}]*dryRunDisable", "dry_run_disable onClick"),
    (r"onClick\s*=\s*\{[^}]*serverRestart", "server_restart onClick"),
    (r"onClick\s*=\s*\{[^}]*dockerCompose", "docker_compose onClick"),
    (r"onClick\s*=\s*\{[^}]*payment[^F]", "payment onClick"),
    (r"onClick\s*=\s*\{[^}]*dnsSave", "dns_save onClick"),
    (r"fetch\s*\(.*['\"]POST['\"].*execute", "fetch POST execute"),
    (r"fetch\s*\(.*['\"]POST['\"].*approve.*exec", "fetch POST approve+exec"),
]

FORBIDDEN_BUTTON_TEXTS = [
    (r"<[Bb]utton[^>]*>실행하기", "실행하기 button"),
    (r"<[Bb]utton[^>]*>지금\s*실행", "지금 실행 button"),
    (r"<[Bb]utton[^>]*>DRY_RUN\s*해제", "DRY_RUN 해제 button"),
    (r"<[Bb]utton[^>]*>서버\s*재시작", "서버 재시작 button"),
    (r"<[Bb]utton[^>]*>compose\s*실행", "compose 실행 button"),
]

MUTATION_PATTERNS = [
    (r"fetch\s*\([^,)]+,\s*\{[^}]*method\s*:\s*['\"]POST['\"]", "fetch POST mutation"),
    (r"fetch\s*\([^,)]+,\s*\{[^}]*method\s*:\s*['\"]PUT['\"]", "fetch PUT mutation"),
    (r"fetch\s*\([^,)]+,\s*\{[^}]*method\s*:\s*['\"]DELETE['\"]", "fetch DELETE mutation"),
    (r"axios\s*\.\s*post\s*\(", "axios.post mutation"),
    (r"axios\s*\.\s*put\s*\(", "axios.put mutation"),
    (r"axios\s*\.\s*delete\s*\(", "axios.delete mutation"),
]

SECRET_PATTERNS = [
    (r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', "token raw value"),
    (r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', "cookie raw value"),
    (r'"password"\s*:\s*"[^"]{3,}"', "password raw value"),
    (r'"secret"\s*:\s*"[^"]{3,}"', "secret raw value"),
]

REQUIRED_PROVIDERS = [
    "GABIA",
    "KAKAO",
    "NAVER",
    "NAVER_SMARTSTORE",
    "GOOGLE",
    "HIWORKS",
    "G2B_NARA",
    "HOMETAX",
    "WETAX",
    "GOVERNMENT24",
    "EMAIL_GENERIC",
    "BANK_GENERIC",
]


@dataclass
class SmokeCheck:
    name: str
    status: Literal["PASS", "WARN", "FAIL"]
    message: str = ""


@dataclass
class SmokeReport:
    generated_at: str = ""
    smoke_id: str = SMOKE_ID
    checks: list[SmokeCheck] = field(default_factory=list)
    verdict: str = ""

    def add(self, name: str, status: Literal["PASS", "WARN", "FAIL"], message: str = "") -> None:
        self.checks.append(SmokeCheck(name, status, message))

    def summary(self) -> dict:
        passed = sum(1 for c in self.checks if c.status == "PASS")
        warned = sum(1 for c in self.checks if c.status == "WARN")
        failed = sum(1 for c in self.checks if c.status == "FAIL")
        return {
            "smoke_id": self.smoke_id,
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


def check_routes_exist(report: SmokeReport) -> None:
    for rel, url, slug in ROUTES:
        path = _page(*rel.split("/"))
        if path.exists():
            report.add(f"route_exists_{slug}", "PASS", f"{url} → {rel} 존재")
        else:
            report.add(f"route_exists_{slug}", "FAIL", f"{url} → {rel} 없음")


def check_heading_markers(report: SmokeReport) -> None:
    for rel, url, slug in ROUTES:
        path = _page(*rel.split("/"))
        if not path.exists():
            report.add(f"heading_{slug}", "FAIL", f"{rel} 없어서 heading 확인 불가")
            continue
        content = path.read_text(encoding="utf-8")
        markers = HEADING_MARKERS.get(rel, [])
        found = any(m in content for m in markers)
        if found:
            report.add(f"heading_{slug}", "PASS", f"{url} heading 마커 존재")
        else:
            report.add(f"heading_{slug}", "WARN", f"{url} heading 마커 미확인 (마커: {markers})")


def check_forbidden_actions(report: SmokeReport) -> None:
    violations: list[str] = []
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        for pattern, name in FORBIDDEN_PATTERNS:
            if re.search(pattern, content):
                violations.append(f"{f.name}: {name}")
    if not violations:
        report.add("forbidden_actions_clean", "PASS", "금지 액션 패턴 없음")
    else:
        for v in violations:
            report.add(f"forbidden_action_{v[:40].replace(' ', '_')}", "FAIL", v)


def check_forbidden_buttons(report: SmokeReport) -> None:
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


def check_mutation_free(report: SmokeReport) -> None:
    violations: list[str] = []
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        for pattern, name in MUTATION_PATTERNS:
            if re.search(pattern, content):
                violations.append(f"{f.name}: {name}")
    if not violations:
        report.add("mutation_free", "PASS", "fetch POST/PUT/DELETE mutation 없음")
    else:
        for v in violations:
            report.add(f"mutation_{v[:40].replace(' ', '_')}", "WARN", f"mutation 발견: {v}")


def check_mock_secrets(report: SmokeReport) -> None:
    if not MOCK_FILE.exists():
        report.add("mock_secret_check", "FAIL", "mock.ts 없음")
        return
    content = MOCK_FILE.read_text(encoding="utf-8")
    clean = True
    for pattern, name in SECRET_PATTERNS:
        if re.search(pattern, content):
            report.add(f"mock_secret_{name.replace(' ', '_')}", "FAIL", f"mock에 {name} 발견")
            clean = False
        else:
            report.add(f"mock_secret_{name.replace(' ', '_')}", "PASS", f"mock에 {name} 없음")
    if clean:
        report.add("mock_secrets_all_clean", "PASS", "mock secret 전부 없음")


def check_mock_providers(report: SmokeReport) -> None:
    if not MOCK_FILE.exists():
        report.add("mock_providers", "FAIL", "mock.ts 없음")
        return
    content = MOCK_FILE.read_text(encoding="utf-8")
    missing = [p for p in REQUIRED_PROVIDERS if p not in content]
    if not missing:
        report.add("mock_providers_12", "PASS", "12개 provider 모두 존재")
    else:
        report.add("mock_providers_12", "FAIL", f"누락: {missing}")


def _check_tasks_page_uses(report: SmokeReport, check_name: str, component: str) -> None:
    """tasks/page.tsx 가 component 를 쓰는지 확인(dry_run_notice_used·forbidden_banner_used 공용)."""
    tasks_page = _page("tasks", "page.tsx")
    if not tasks_page.exists():
        report.add(check_name, "FAIL", "tasks/page.tsx 없음")
        return
    content = tasks_page.read_text(encoding="utf-8")
    if component in content:
        report.add(check_name, "PASS", f"tasks/page.tsx에 {component} 사용")
    else:
        report.add(check_name, "FAIL", f"tasks/page.tsx에 {component} 없음")


def check_dry_run_notice_used(report: SmokeReport) -> None:
    _check_tasks_page_uses(report, "dry_run_notice_used", "DryRunNotice")


def check_forbidden_banner_used(report: SmokeReport) -> None:
    _check_tasks_page_uses(report, "forbidden_banner_used", "ForbiddenActionBanner")


def check_approval_no_execute_connection(report: SmokeReport) -> None:
    approval_page = ASSISTANT_APP / "approval" / "page.tsx"
    if not approval_page.exists():
        report.add("approval_no_execute_connection", "FAIL", "approval/page.tsx 없음")
        return
    content = approval_page.read_text(encoding="utf-8")
    ok = "approve→execute 미연결" in content or "display" in content.lower() or "ForbiddenActionBanner" in content
    if ok:
        report.add("approval_no_execute_connection", "PASS", "approve→execute 미연결 표시 확인")
    else:
        report.add("approval_no_execute_connection", "WARN", "approval 페이지 approve→execute 미연결 마커 미확인")


def check_deployment_no_restart(report: SmokeReport) -> None:
    deployment_page = _page("deployment", "page.tsx")
    if not deployment_page.exists():
        report.add("deployment_no_restart", "FAIL", "deployment/page.tsx 없음")
        return
    content = deployment_page.read_text(encoding="utf-8")
    if re.search(r"<[Bb]utton[^>]*>서버\s*재시작", content):
        report.add("deployment_no_restart", "FAIL", "deployment에 서버 재시작 버튼 발견")
    else:
        report.add("deployment_no_restart", "PASS", "deployment에 서버 재시작 버튼 없음")


def check_console_error_markers(report: SmokeReport) -> None:
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        if "console.error" in content or "throw new Error" in content:
            report.add(f"console_error_{f.stem}", "WARN", f"{f.name}에 console.error/throw 존재 — 의도적 여부 확인")
    report.add("console_error_scan_done", "PASS", "console.error 스캔 완료")


def run_smoke() -> SmokeReport:
    report = SmokeReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_routes_exist(report)
    check_heading_markers(report)
    check_forbidden_actions(report)
    check_forbidden_buttons(report)
    check_mutation_free(report)
    check_mock_secrets(report)
    check_mock_providers(report)
    check_dry_run_notice_used(report)
    check_forbidden_banner_used(report)
    check_approval_no_execute_connection(report)
    check_deployment_no_restart(report)
    check_console_error_markers(report)

    summary = report.summary()
    if summary["failed"] > 0:
        report.verdict = VERDICT_FAIL
    elif summary["warned"] > 0:
        report.verdict = VERDICT_WARN
    else:
        report.verdict = VERDICT_PASS
    return report


if __name__ == "__main__":
    report = run_smoke()
    summary = report.summary()

    out_path = REPO_ROOT / "data" / "app_ui_shell_browser_smoke_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{SMOKE_ID}] UI Shell Browser Smoke")
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
