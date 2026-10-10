"""Smoke: APP_TASK_QUEUE_READONLY_LIST_POLISH_01

Task Queue UI 정적 분석 스모크 — 브라우저 없이 파일 기반으로 주요 제약 확인.
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

SMOKE_ID = "APP_TASK_QUEUE_READONLY_LIST_POLISH_SMOKE_01"
VERDICT_PASS = f"{SMOKE_ID}_PASS"
VERDICT_WARN = f"{SMOKE_ID}_WARN"
VERDICT_FAIL = f"{SMOKE_ID}_FAIL"

results: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _smoke_page_table_checks(page, table):
    _check("tasks/page.tsx 존재", TASKS_PAGE.exists())
    _check("TaskTable.tsx 존재", TASK_TABLE.exists())
    _check("mock.ts 존재", MOCK_FILE.exists())
    _check("assistant.ts 존재", TYPES_FILE.exists())

    # ── 화면 헤딩 ────────────────────────────────────────────────────────────
    _check("작업 큐 헤딩 존재", "작업 큐" in page)
    _check("DRY_RUN_ONLY 뱃지 존재", "DRY_RUN_ONLY" in page)
    _check("MUTATION_BLOCKED 뱃지 존재", "MUTATION_BLOCKED" in page)

    # ── read-only 배너 ───────────────────────────────────────────────────────
    _check("ReadOnlyModeBanner 존재", "ReadOnlyModeBanner" in page)
    _check("ForbiddenActionBanner 존재", "ForbiddenActionBanner" in page)
    _check("DryRunNotice 존재", "DryRunNotice" in page)

    # ── mock fallback 존재 ───────────────────────────────────────────────────
    _check("MOCK_FALLBACK 상태 처리", "mock_fallback" in page)
    _check("EmptyStatePanel 존재", "EmptyStatePanel" in page)
    _check("error 상태 처리", "error" in page)

    # ── TaskTable 주요 컴포넌트 ──────────────────────────────────────────────
    _check("DryRunBadge 컴포넌트", "DryRunBadge" in table)
    _check("TokenDisplay 컴포넌트", "TokenDisplay" in table)
    _check("TaskStatusLegend 컴포넌트", "TaskStatusLegend" in table)
    _check("riskFilter 존재", "riskFilter" in table)
    _check("statusFilter 존재", "statusFilter" in table)


def _smoke_field_checks(table, page):
    # ── 필드 렌더링 ──────────────────────────────────────────────────────────
    _check("provider 렌더링", "provider" in table)
    _check("action_type 렌더링", "action_type" in table)
    _check("risk 렌더링", "risk" in table)
    _check("status 렌더링", "status" in table)
    _check("summary 렌더링", "summary" in table)

    # ── badge 종류 ───────────────────────────────────────────────────────────
    _check("RiskBadge 사용", "RiskBadge" in table)
    _check("StatusBadge 사용", "StatusBadge" in table)
    _check("DRY_RUN badge 텍스트", "DRY_RUN" in table)
    _check("TOKEN_BLOCKED badge 텍스트", "TOKEN_BLOCKED" in table)
    _check("redacted 표시 정책", "redacted" in table)

    # ── 실행 버튼 없음 (B-1, B-2) ────────────────────────────────────────────
    _check("execute 버튼 없음", "execute_btn" not in table and ">실행<" not in table)
    _check("approve_btn 없음", "approve_btn" not in table)
    _check("reject_btn 없음", "reject_btn" not in table)
    _check("submit 버튼 없음", "submit_btn" not in table)

    # ── POST mutation 없음 ───────────────────────────────────────────────────
    _check("POST method 없음 (table)", 'method: "POST"' not in table and "method: 'POST'" not in table)
    _check("POST method 없음 (page)", 'method: "POST"' not in page and "method: 'POST'" not in page)

    # ── 금지 URL 없음 ────────────────────────────────────────────────────────
    _check("execute_url 없음", "execute_url" not in page and "execute_url" not in table)
    _check("approve_url 없음", "approve_url" not in page and "approve_url" not in table)
    _check("submit_url 없음", "submit_url" not in page and "submit_url" not in table)


def _smoke_security_and_mock(page, table, mock, types):
    # ── 보안: 원문 금지 ─────────────────────────────────────────────────────
    _check("approval_token_raw 없음 (전체)", "approval_token_raw" not in page + table + mock)
    _check("cookie_value 없음 (전체)", "cookie_value" not in page + table + mock)

    # ── mock 다양성 ──────────────────────────────────────────────────────────
    _check("mock DRY_RUN 상태", '"DRY_RUN"' in mock)
    _check("mock BLOCKED 상태", '"BLOCKED"' in mock)
    _check("mock APPROVAL_DISPLAY_ONLY 상태", '"APPROVAL_DISPLAY_ONLY"' in mock)
    _check("mock READ_ONLY 상태", '"READ_ONLY"' in mock)
    _check("mock FUTURE 상태", '"FUTURE"' in mock)
    _check("mock dry_run null 존재", "dry_run: null" in mock)
    _check("mock blocked_reasons 존재", "blocked_reasons" in mock)

    # ── 타입 확장 ────────────────────────────────────────────────────────────
    _check("blocked_reasons 타입 존재", "blocked_reasons" in types)
    _check("approval_token_id 타입 존재", "approval_token_id" in types)
    _check("dry_run boolean|null 타입", "boolean | null" in types)


def run_smoke() -> None:
    page = _src(TASKS_PAGE)
    table = _src(TASK_TABLE)
    mock = _src(MOCK_FILE)
    types = _src(TYPES_FILE)

    # ── 파일 존재 ────────────────────────────────────────────────────────────
    _smoke_page_table_checks(page, table)

    _smoke_field_checks(table, page)

    _smoke_security_and_mock(page, table, mock, types)


def print_report() -> str:
    passed = sum(1 for _, r, _ in results if r)
    failed = sum(1 for _, r, _ in results if not r)

    print(f"\n{'=' * 64}")
    print(f"SMOKE: {SMOKE_ID}")
    print(f"{'=' * 64}")
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"{'=' * 64}")
    print(f"  총 {len(results)}개: PASS={passed}, FAIL={failed}")

    if failed == 0:
        verdict = VERDICT_PASS
    elif failed <= 2:
        verdict = VERDICT_WARN
    else:
        verdict = VERDICT_FAIL

    print(f"  최종 판정: {verdict}")
    print(f"{'=' * 64}\n")
    return verdict


if __name__ == "__main__":
    run_smoke()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_FAIL else 1)
