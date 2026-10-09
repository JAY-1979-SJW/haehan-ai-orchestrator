"""Audit: APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01

Priority 1 read-only endpoint 구현이 계약과 보안경계를 지키는지 검증한다.
"""

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "app_status_router.py"
MAIN_ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "registry.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"

checks: list[tuple[str, bool, str]] = []


def _add(name: str, result: bool, detail: str = "") -> None:
    checks.append((name, result, detail))


def _load_source(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_audit() -> None:
    src = _load_source(ROUTER_FILE)
    router_src = _load_source(MAIN_ROUTER_FILE)

    # 1. 파일 존재
    _add("app_status_router.py 존재", ROUTER_FILE.exists())

    # 2–5. endpoint 존재
    _add("GET /app/health/summary 정의", '"/health/summary"' in src or "'/health/summary'" in src)
    _add("GET /app/providers 정의", '"/providers"' in src or "'/providers'" in src)
    _add("GET /app/storage/status 정의", '"/storage/status"' in src or "'/storage/status'" in src)

    # 6. POST route 없음
    _add("POST route 없음", "@app_status_router.post" not in src)

    # 7. PUT/PATCH/DELETE route 없음
    _add(
        "PUT/PATCH/DELETE route 없음",
        "@app_status_router.put" not in src
        and "@app_status_router.patch" not in src
        and "@app_status_router.delete" not in src,
    )

    # 8. mutation_allowed=false
    _add("MUTATION_ALLOWED=False 선언", "MUTATION_ALLOWED = False" in src)

    # 9. server_action_allowed=false
    _add("SERVER_ACTION_ALLOWED=False 선언", "SERVER_ACTION_ALLOWED = False" in src)

    # 10. read_only=true
    _add("READ_ONLY_API_ENABLED=True 선언", "READ_ONLY_API_ENABLED = True" in src)

    # 11. raw token/cookie/password 반환 금지 선언
    _add("_FORBIDDEN_RESPONSE_FIELDS 선언", "_FORBIDDEN_RESPONSE_FIELDS" in src)
    _add("approval_token_raw forbidden 선언", "approval_token_raw" in src)
    _add("execute_url forbidden 선언", "execute_url" in src)

    # 14. provider 12개 반영
    try:
        from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY

        _add("provider 12개 반영", len(PROVIDER_REGISTRY) == 12, f"실제: {len(PROVIDER_REGISTRY)}")
    except Exception as e:  # noqa: BLE001 - 읽기전용 API 엔드포인트 구현 감사 스크립트 — provider 레지스트리 import/카운트 확인 실패를 False(실패)로 기록하는 fail-closed 감사 항목.
        _add("provider 12개 반영", False, str(e))

    # 15. cookie_storage_allowed=False 전체
    _add(
        "cookie_storage_allowed=False 강제",
        '"cookie_storage_allowed": False' in src or "'cookie_storage_allowed': False" in src,
    )

    # 16. named_volume_status 반영
    _add("named_volume_status 반영", "named_volume_status" in src)

    # 17. app_logs_bind_mount_status 반영
    _add("app_logs_bind_mount_status 반영", "app_logs_bind_mount_status" in src)

    # 18. post_tasks_dry_run_enabled 포함
    _add("post_tasks_dry_run_enabled 반영", "post_tasks_dry_run_enabled" in src)

    # 19. router.py 등록이 최소 범위
    _add("router.py에 app_status_router include", "app_status_router" in router_src)
    _add("router.py POST route 추가 없음 (app_status)", "app_status_router.post" not in router_src)

    # 20. POST /tasks 코드 변경 없음 — dry_run gate 유지 확인
    _add("POST_TASKS_DRY_RUN_ENABLED 유지", "POST_TASKS_DRY_RUN_ENABLED = True" in router_src)

    # 21. approve/reject/execute 코드 변경 없음
    _add("approve_token 함수 유지", "approve_token" in router_src)
    _add("reject_token 함수 유지", "reject_token" in router_src)

    # 22. docker-compose 변경 없음 (파일 내 app_status_router 없음)
    compose_src = _load_source(COMPOSE_FILE)
    _add("docker-compose.yml에 app_status_router 없음", "app_status_router" not in compose_src)


def print_report() -> str:
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)

    print(f"\n{'=' * 60}")
    print("APP_API_READONLY_ENDPOINTS_IMPLEMENTATION AUDIT")
    print(f"{'=' * 60}")
    for name, result, detail in checks:
        status = "PASS" if result else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"{'=' * 60}")
    print(f"  총 {len(checks)}개 검사: PASS={passed}, FAIL={failed}")

    if failed == 0:
        verdict = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_READY"
    elif failed <= 2:
        verdict = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_WITH_WARN"
    else:
        verdict = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_BLOCKED"

    print(f"  최종 판정: {verdict}")
    print(f"{'=' * 60}\n")
    return verdict


if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if "BLOCKED" not in verdict else 1)
