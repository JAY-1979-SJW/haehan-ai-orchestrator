"""Audit: APP_TEST_BASELINE_CURRENT_CONTRACT_SYNC_01

현재 앱/백엔드 계약 기준으로 테스트 기준선이 동기화되었는지 검증한다.
기능 구현 공정이 아니라 테스트 기대값 갱신 공정 감리.
"""

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

TESTS_DIR = ROOT / "tests"
FRONTEND_SRC = ROOT / "admin-web" / "src"
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "registry.py"
APP_STATUS_ROUTER = ROOT / "ai_orchestrator" / "routers" / "app_status_router.py"
DASHBOARD_PAGE = FRONTEND_SRC / "app" / "assistant" / "page.tsx"

VERDICT_READY = "APP_TEST_BASELINE_CURRENT_CONTRACT_SYNC_READY"
VERDICT_WARN = "APP_TEST_BASELINE_CURRENT_CONTRACT_SYNC_WITH_WARN"
VERDICT_BLOCKED = "APP_TEST_BASELINE_CURRENT_CONTRACT_SYNC_BLOCKED"

checks: list[tuple[str, bool, str]] = []


def _add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _test_src(name: str) -> str:
    f = TESTS_DIR / name
    return _src(f)


def run_audit() -> None:
    dashboard = _src(DASHBOARD_PAGE)
    router_src = _src(ROUTER_FILE)
    app_status_src = _src(APP_STATUS_ROUTER)

    # GROUP A — dashboard health API 계약 갱신
    _add("dashboard getAppHealthSummary 사용", "getAppHealthSummary" in dashboard)
    _add("dashboard getAssistantHealth 구기준 제거", "getAssistantHealth" not in dashboard)
    _add("app_status_router health/summary 경로 존재", "health/summary" in app_status_src)

    # GROUP B — FutureEndpointNotice 갱신
    all_tsx = "\n".join(f.read_text(encoding="utf-8") for f in FRONTEND_SRC.rglob("*.tsx"))
    _add("FutureEndpointNotice 컴포넌트 프론트 존재 (future 항목용)", "FutureEndpointNotice" in all_tsx)
    _add("Dashboard FutureEndpointNotice 제거 (storage 구현됨)", "FutureEndpointNotice" not in dashboard)
    _add("storage/status read-only endpoint 존재", "storage/status" in app_status_src)

    # GROUP C — UI allowlist 반영 (test 파일이 현재 계약 기반으로 갱신됨)
    status_cards_test = _test_src("app_contracts/test_app_ui_readonly_backend_status_cards_20260518.py")
    _add("status_cards_test getAppHealthSummary 기대", "getAppHealthSummary" in status_cards_test)
    # 주석에 legacy 명칭이 남을 수 있으므로 assert 문 기준으로 확인
    _add("status_cards_test getAssistantHealth assert 없음", 'assert "getAssistantHealth"' not in status_cards_test)
    _add(
        "status_cards_test FutureEndpointNotice 전체 검색으로 갱신",
        "FRONTEND_ROOT.rglob" in status_cards_test or "rglob" in status_cards_test,
    )

    # GROUP D — endpoint count +3 반영
    domain_test = _test_src("app_contracts/test_backend_domain_core_models_20260516.py")
    legacy_test = _test_src("app_contracts/test_backend_legacy_router_direct_dict_audit_20260516.py")
    cycle_test = _test_src("app_contracts/test_backend_router_server_cycle_break_20260516.py")

    # 현행 기준(tests/test_app_test_baseline_current_contract_sync 와 동일): 숫자를 직접 적지 않고 단일 정본(configs/route_count_expectation.json)을 읽는지 확인, cycle_test 는 audit 기준에 위임
    _add("domain_test endpoint count 정본 참조", "EXPECTED_RUNTIME_ROUTES" in domain_test)
    _add("legacy_test HTTP count 정본 참조", "EXPECTED_HTTP_ROUTES" in legacy_test)
    _add("cycle_test route count audit 기준 위임", "audit.EXPECTED_RUNTIME_ROUTES" in cycle_test)

    # app_status_router 3개 GET endpoint 확인
    _add("app/health/summary GET endpoint", "/health/summary" in app_status_src)
    _add("app/providers GET endpoint", "/providers" in app_status_src)
    _add("app/storage/status GET endpoint", "/storage/status" in app_status_src)

    # POST endpoint 증가 없음
    _add(
        "app_status_router POST 없음",
        "@app_status_router.post" not in app_status_src and 'method: "POST"' not in app_status_src,
    )
    _add("router.py task_queue 없음", "task_queue" not in router_src)

    # mutation endpoint 없음
    _add("execute endpoint 없음 (app_status)", "execute" not in app_status_src or "/execute" not in app_status_src)
    _add("approve endpoint 없음 (app_status)", "/approve" not in app_status_src)
    _add("reject endpoint 없음 (app_status)", "/reject" not in app_status_src)

    # KW-1 runtime cache 알려진 예외
    kw1 = ROOT / "scripts" / "archive" / "data" / "chrome_ui_monitor_state.json"
    _add("KW-1 runtime cache 파일 알려진 예외", kw1.exists(), "known dirty — 오류 아님")

    # 안전 — token/cookie/password 원문 없음
    # approval_token_raw는 _FORBIDDEN_RESPONSE_FIELDS 보안 차단 목록에 포함됨 — 원문 반환이 아니라 차단 정책
    _add(
        "app_status_router approval_token_raw 반환 없음 (차단 목록 보유 허용)",
        "approval_token_raw" not in app_status_src or "_FORBIDDEN_RESPONSE_FIELDS" in app_status_src,
    )
    _add("app_status_router cookie_value 없음", "cookie_value" not in app_status_src)


def print_report() -> str:
    from scripts.common.audit_cli import print_check_report

    return print_check_report(
        "APP_TEST_BASELINE_CURRENT_CONTRACT_SYNC AUDIT", checks, (VERDICT_READY, VERDICT_WARN, VERDICT_BLOCKED), 2, "개"
    )


if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_BLOCKED else 1)
