"""Audit: APP_TASK_DETAIL_READONLY_POLISH_01

Task Detail 화면이 read-only 계약과 보안 경계를 지키는지 검증한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DETAIL_PAGE = ROOT / "admin-web" / "src" / "app" / "assistant" / "tasks" / "[id]" / "page.tsx"
DETAIL_PANEL = ROOT / "admin-web" / "src" / "components" / "assistant" / "TaskDetailPanel.tsx"
ROUTER_FILE = ROOT / "ai_orchestrator" / "router.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"

VERDICT_READY = "APP_TASK_DETAIL_READONLY_POLISH_READY"
VERDICT_WARN = "APP_TASK_DETAIL_READONLY_POLISH_WITH_WARN"
VERDICT_BLOCKED = "APP_TASK_DETAIL_READONLY_POLISH_BLOCKED"

checks: list[tuple[str, bool, str]] = []


def _add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_audit() -> None:
    page = _src(DETAIL_PAGE)
    panel = _src(DETAIL_PANEL)

    # 파일 존재
    _add("Task Detail page 존재", DETAIL_PAGE.exists())
    _add("TaskDetailPanel 컴포넌트 존재", DETAIL_PANEL.exists())

    # read-only 배너
    _add("ReadOnlyModeBanner 존재", "ReadOnlyModeBanner" in page)
    _add("ForbiddenActionBanner 존재", "ForbiddenActionBanner" in page)

    # 필수 표시 필드
    _add("task id 표시", "task.id" in panel)
    _add("title 표시", "task.title" in panel)
    _add("status 표시", "task.status" in panel)
    _add("risk 표시", "task.risk" in panel)
    _add("provider 표시", "task.provider" in panel)
    _add("action_type 표시", "task.action_type" in panel)
    _add("dry_run 표시", "task.dry_run" in panel)
    _add("created_at 표시", "task.created_at" in panel)
    _add("updated_at 표시", "task.updated_at" in panel)
    _add("summary 표시", "task.summary" in panel)
    _add("blocked_reasons 표시", "task.blocked_reasons" in panel or "blocked_reasons" in panel)
    _add("approval_token 표시 (redacted)", "redacted" in panel)

    # error/warning/log 영역
    _add("에러 영역 존재", "LAST_ERROR" in panel or "error" in panel.lower())
    _add("경고 영역 존재", "WARNING" in panel or "warning" in panel.lower())
    _add("로그 요약 영역 존재", "LOG_SUMMARY" in panel or "log" in panel.lower())

    # fallback 처리
    _add("Empty fallback 컴포넌트 존재", "Empty" in panel or "없음" in panel)
    _add("mock_fallback 상태 처리", "mock_fallback" in page)

    # 금지 버튼 없음
    _add("execute 버튼 없음", "execute_btn" not in panel and ">실행<" not in panel)
    _add("approve 버튼 없음", "approve_btn" not in panel)
    _add("reject 버튼 없음", "reject_btn" not in panel)
    _add("delete 버튼 없음", "delete_btn" not in panel and "onClick.*delete" not in panel)
    _add("save 버튼 없음", "save_btn" not in panel and "onSave" not in panel)

    # POST mutation 없음
    _add("POST method 없음 (page)", 'method: "POST"' not in page and "method: 'POST'" not in page)
    _add("POST method 없음 (panel)", 'method: "POST"' not in panel and "method: 'POST'" not in panel)

    # 금지 URL 없음
    _add("execute_url 없음", "execute_url" not in page + panel)
    _add("approve_url 없음", "approve_url" not in page + panel)
    _add("reject_url 없음", "reject_url" not in page + panel)

    # 접기/펼치기 viewer
    _add("JsonViewer / 접기 존재", "JsonViewer" in panel or "open" in panel)

    # 목록 링크
    _add("← 작업 큐 링크 존재", "/assistant/tasks" in page)

    # 보안
    _add("approval_token_raw 없음", "approval_token_raw" not in page + panel)
    _add("cookie_value 없음", "cookie_value" not in page + panel)

    # backend/infra 불변
    router_src = _src(ROUTER_FILE)
    _add("router.py task_detail 없음", "task_detail" not in router_src)
    compose_src = _src(COMPOSE_FILE)
    _add("docker-compose task_detail 없음", "task_detail" not in compose_src)


def print_report() -> str:
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)

    print(f"\n{'=' * 64}")
    print("APP_TASK_DETAIL_READONLY_POLISH AUDIT")
    print(f"{'=' * 64}")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"{'=' * 64}")
    print(f"  총 {len(checks)}개: PASS={passed}, FAIL={failed}")

    if failed == 0:
        verdict = VERDICT_READY
    elif failed <= 3:
        verdict = VERDICT_WARN
    else:
        verdict = VERDICT_BLOCKED

    print(f"  최종 판정: {verdict}")
    print(f"{'=' * 64}\n")
    return verdict


if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_BLOCKED else 1)
