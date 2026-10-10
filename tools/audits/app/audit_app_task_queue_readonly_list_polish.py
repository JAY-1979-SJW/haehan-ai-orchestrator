"""Audit: APP_TASK_QUEUE_READONLY_LIST_POLISH_01

Task Queue UI polish가 read-only 계약과 보안경계를 지키는지 검증한다.
"""

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

TASKS_PAGE = ROOT / "admin-web" / "src" / "app" / "assistant" / "tasks" / "page.tsx"
TASK_TABLE = ROOT / "admin-web" / "src" / "components" / "assistant" / "TaskTable.tsx"
MOCK_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "mock.ts"
TYPES_FILE = ROOT / "admin-web" / "src" / "types" / "assistant.ts"
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "registry.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"

VERDICT_READY = "APP_TASK_QUEUE_READONLY_LIST_POLISH_READY"
VERDICT_WARN = "APP_TASK_QUEUE_READONLY_LIST_POLISH_WITH_WARN"
VERDICT_BLOCKED = "APP_TASK_QUEUE_READONLY_LIST_POLISH_BLOCKED"

checks: list[tuple[str, bool, str]] = []


def _add(name: str, result: bool, detail: str = "") -> None:
    checks.append((name, result, detail))


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_audit() -> None:
    page = _src(TASKS_PAGE)
    table = _src(TASK_TABLE)
    mock = _src(MOCK_FILE)
    _src(TYPES_FILE)

    # 1. Task Queue 화면 존재
    _add("Task Queue 페이지 존재", TASKS_PAGE.exists())

    # 2. TaskTable 보강 확인
    _add("TaskTable 존재", TASK_TABLE.exists())
    _add("TaskTable DryRunBadge 존재", "DryRunBadge" in table)
    _add("TaskTable TokenDisplay 존재", "TokenDisplay" in table)
    _add("TaskTable 필터바 존재", "riskFilter" in table or "statusFilter" in table)
    _add("TaskTable StatusLegend 존재", "TaskStatusLegend" in table or "Legend" in table)

    # 3–5. badge 존재
    _add("RiskBadge 사용", "RiskBadge" in table)
    _add("StatusBadge 사용", "StatusBadge" in table)
    _add("DRY_RUN badge 정책 존재", "DRY_RUN" in table)

    # 6–7. token 원문 금지
    _add("token 원문 표시 없음", "approval_token_raw" not in table and "approval_token_raw" not in page)
    _add("approval_token_id redacted 정책", "redacted" in table)

    # 8–9. 금지 버튼 없음
    _add("execute button 없음", not any(b in table for b in ["onClick.*execute", ">실행<", "execute_btn"]))
    _add("approve/reject button 없음", "approve_btn" not in table and "reject_btn" not in table)

    # 10. POST mutation 연결 없음
    _add("POST mutation 없음 (table)", 'method: "POST"' not in table and "method: 'POST'" not in table)
    _add("POST mutation 없음 (page)", 'method: "POST"' not in page and "method: 'POST'" not in page)

    # 11–13. 상태 패널
    _add("empty state 존재", "empty" in page and "EmptyStatePanel" in page)
    _add("error state 존재", "error" in page)
    _add("mock_fallback 존재", "mock_fallback" in page)

    # 14. read-only 안내
    _add("ReadOnlyModeBanner 존재", "ReadOnlyModeBanner" in page)
    _add("ForbiddenActionBanner 존재", "ForbiddenActionBanner" in page)

    # 15. 금지 액션 없음
    _add("execute_url 없음", "execute_url" not in page and "execute_url" not in table)
    _add("approve_url 없음", "approve_url" not in page and "approve_url" not in table)
    _add("submit_url 없음", "submit_url" not in page and "submit_url" not in table)

    # 16. 표시 필드 존재
    _add("provider 필드 표시", "provider" in table)
    _add("risk 필드 표시", "risk" in table)
    _add("status 필드 표시", "status" in table)
    _add("summary 필드 표시", "summary" in table)
    _add("action_type 필드 표시", "action_type" in table)

    # 17. mock data 다양한 상태
    _add("mock DRY_RUN task 존재", '"DRY_RUN"' in mock)
    _add("mock BLOCKED task 존재", '"BLOCKED"' in mock)
    _add("mock APPROVAL_DISPLAY_ONLY task 존재", '"APPROVAL_DISPLAY_ONLY"' in mock)
    _add("mock READ_ONLY task 존재", '"READ_ONLY"' in mock)
    _add("mock FUTURE task 존재", '"FUTURE"' in mock)
    _add("mock dry_run=null 존재 (safe)", "dry_run: null" in mock)
    _add("mock blocked_reasons 존재", "blocked_reasons" in mock)
    _add("mock summary 존재", "summary" in mock)

    # 18–19. backend/compose 수정 없음
    router_src = _src(ROUTER_FILE)
    _add("router.py에 task_queue 없음", "task_queue" not in router_src)

    compose_src = _src(COMPOSE_FILE)
    _add("docker-compose task_queue 없음", "task_queue" not in compose_src)

    # 보안 — token/cookie/password 원문 없음
    for label, src in [("mock", mock), ("page", page), ("table", table)]:
        _add(f"{label} approval_token_raw 없음", "approval_token_raw" not in src)
        _add(f"{label} cookie_value 없음", "cookie_value" not in src)
        _add(
            f"{label} password raw 없음",
            '"password"' not in src or "password" not in src.split('"password"')[1][:20]
            if '"password"' in src
            else True,
        )


def print_report() -> str:
    from scripts.common.audit_cli import print_check_report

    return print_check_report(
        "APP_TASK_QUEUE_READONLY_LIST_POLISH AUDIT", checks, (VERDICT_READY, VERDICT_WARN, VERDICT_BLOCKED), 3
    )


if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_BLOCKED else 1)
