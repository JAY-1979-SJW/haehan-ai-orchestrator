"""Audit: APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_01

smoke script 존재 및 실행 결과가 보안·read-only 계약을 지키는지 검증한다.
"""

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

SMOKE_SCRIPT = ROOT / "tools" / "audits" / "app" / "smoke_app_api_readonly_endpoints.py"
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "app_status_router.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"

VERDICT_READY = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_READY"
VERDICT_WARN = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_WITH_WARN"
VERDICT_BLOCKED = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_BLOCKED"

checks: list[tuple[str, bool, str]] = []


def _add(name: str, result: bool, detail: str = "") -> None:
    checks.append((name, result, detail))


def run_audit() -> None:
    # 1. smoke script 존재
    _add("smoke script 존재", SMOKE_SCRIPT.exists())

    # 2–6. smoke 실행 및 결과 검증
    try:
        from tools.audits.app.smoke_app_api_readonly_endpoints import ENDPOINTS, run_smoke

        report = run_smoke()

        _add("endpoint 3개 대상 확인", len(ENDPOINTS) == 3, f"실제: {len(ENDPOINTS)}")
        _add("health summary endpoint 포함", "/api/v1/app/health/summary" in ENDPOINTS)
        _add("providers endpoint 포함", "/api/v1/app/providers" in ENDPOINTS)
        _add("storage status endpoint 포함", "/api/v1/app/storage/status" in ENDPOINTS)

        all_passed = len(report.failed_endpoints) == 0
        _add("3개 endpoint 모두 PASS", all_passed, f"failed={report.failed_endpoints}")

        # 개별 endpoint 결과
        for res in report.results:
            label = res.path.split("/")[-1]
            _add(f"{label} HTTP 200", res.status_code == 200, f"status={res.status_code}")
            _add(f"{label} schema_ok", res.schema_ok)
            _add(f"{label} read_only=true", res.read_only_ok)
            _add(f"{label} mutation_allowed=false", res.mutation_allowed_ok)
            _add(f"{label} redaction_ok", res.redaction_ok)

        # provider 검증 (providers 결과에서)
        prov_res = next((r for r in report.results if "providers" in r.path), None)
        if prov_res:
            _add("providers schema_ok", prov_res.schema_ok)
        else:
            _add("providers schema_ok", False, "결과 없음")

        # safety counters
        _add("mutation_request_count=0", report.mutation_request_count == 0, str(report.mutation_request_count))
        _add("external_http_call_count=0", report.external_http_call_count == 0, str(report.external_http_call_count))
        _add("db_write_count=0", report.db_write_count == 0, str(report.db_write_count))
        _add("secret_output_count=0", report.secret_output_count == 0, str(report.secret_output_count))
        _add("redaction_violations=0", report.redaction_violations == 0, str(report.redaction_violations))

        # provider 12개, post_tasks_dry_run, post_tasks_dry_run
        _add("smoke verdict READY 또는 WARN", report.verdict != VERDICT_BLOCKED, report.verdict)

    except Exception as e:  # noqa: BLE001 - 읽기전용 API 엔드포인트 브라우저 스모크 감사 스크립트 — 개별 체크 실행 실패를 False(실패)로 _add 기록하는 fail-closed 감사 항목.
        _add("smoke 실행 가능", False, str(e))

    # POST route 없음 (router 파일 기준)
    src = ROUTER_FILE.read_text(encoding="utf-8") if ROUTER_FILE.exists() else ""
    _add("app_status_router POST route 없음", "@app_status_router.post" not in src)
    _add(
        "approve/reject/execute route 없음 (status_router)",
        "approve_token" not in src
        and "reject_token" not in src
        and "@app_status_router" in src
        and "execute(" not in src,
    )

    # docker-compose 변경 없음
    compose_src = COMPOSE_FILE.read_text(encoding="utf-8") if COMPOSE_FILE.exists() else ""
    _add("docker-compose에 smoke 코드 없음", "smoke_app_api" not in compose_src)


def print_report() -> str:
    from scripts.common.audit_cli import print_check_report

    return print_check_report(
        "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE AUDIT", checks, (VERDICT_READY, VERDICT_WARN, VERDICT_BLOCKED), 2
    )


if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_BLOCKED else 1)
