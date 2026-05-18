"""Audit: APP_UI_READONLY_STATUS_CARDS_API_BIND_01

프론트엔드 상태 카드가 실제 read-only API 3개에 연결됐는지 검증한다.
mutation, secret, POST 없음.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

API_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "api.ts"
DASHBOARD_FILE = ROOT / "admin-web" / "src" / "app" / "assistant" / "page.tsx"
EXTERNAL_FILE = ROOT / "admin-web" / "src" / "app" / "assistant" / "external-sites" / "page.tsx"
STORAGE_FILE = ROOT / "admin-web" / "src" / "app" / "assistant" / "storage" / "page.tsx"
COMPOSE_FILE = ROOT / "docker-compose.yml"

VERDICT_READY = "APP_UI_READONLY_STATUS_CARDS_API_BIND_READY"
VERDICT_WARN = "APP_UI_READONLY_STATUS_CARDS_API_BIND_WITH_WARN"
VERDICT_BLOCKED = "APP_UI_READONLY_STATUS_CARDS_API_BIND_BLOCKED"

checks: list[tuple[str, bool, str]] = []


def _add(name: str, result: bool, detail: str = "") -> None:
    checks.append((name, result, detail))


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_audit() -> None:
    api = _src(API_FILE)
    dash = _src(DASHBOARD_FILE)
    ext = _src(EXTERNAL_FILE)
    stor = _src(STORAGE_FILE)

    # api.ts — 신규 함수 존재
    _add("api.ts 존재", API_FILE.exists())
    _add("getAppHealthSummary 정의", "getAppHealthSummary" in api)
    _add("getAppProviders 정의", "getAppProviders" in api)
    _add("getAppStorageStatus 정의", "getAppStorageStatus" in api)
    _add("AppHealthSummaryResponse 타입 정의", "AppHealthSummaryResponse" in api)
    _add("AppProvidersResponse 타입 정의", "AppProvidersResponse" in api)
    _add("AppStorageStatusResponse 타입 정의", "AppStorageStatusResponse" in api)
    _add("/api/v1/app/health/summary 경로", "/api/v1/app/health/summary" in api)
    _add("/api/v1/app/providers 경로", "/api/v1/app/providers" in api)
    _add("/api/v1/app/storage/status 경로", "/api/v1/app/storage/status" in api)

    # api.ts — GET만, POST/mutation 없음
    _add("api.ts POST 없음", "method: \"POST\"" not in api and "method: 'POST'" not in api)

    # Dashboard — getAppHealthSummary 연결
    _add("Dashboard getAppHealthSummary 사용", "getAppHealthSummary" in dash)
    _add("Dashboard mock_fallback 유지", "mock_fallback" in dash)
    _add("Dashboard POST 없음", "POST" not in dash or "mutation_allowed: false" in dash)

    # External Sites — getAppProviders 연결
    _add("ExternalSites getAppProviders 사용", "getAppProviders" in ext)
    _add("ExternalSites mock_fallback 유지", "mock_fallback" in ext)
    _add("ExternalSites mapProviders 매핑", "mapProviders" in ext)
    _add("ExternalSites cookie_storage_forbidden=true", "cookie_storage_forbidden: true" in ext)

    # Storage — getAppStorageStatus 연결
    _add("Storage getAppStorageStatus 사용", "getAppStorageStatus" in stor)
    _add("Storage mock_fallback 유지", "mock_fallback" in stor)
    _add("Storage mapStorage 매핑", "mapStorage" in stor)

    # 금지 사항
    for label, src in [("api.ts", api), ("Dashboard", dash), ("ExternalSites", ext), ("Storage", stor)]:
        _add(f"{label} approve/execute/reject 없음",
             "approve_token" not in src and "execute_url" not in src and "reject_token" not in src)
        _add(f"{label} raw token/cookie 없음",
             "approval_token_raw" not in src and "cookie_value" not in src and "password" not in src)

    # docker-compose 변경 없음
    compose = _src(COMPOSE_FILE)
    _add("docker-compose 수정 없음 (api_bind 없음)", "api_bind" not in compose)

    # backend smoke 여전히 PASS
    try:
        from scripts.ops.smoke_app_api_readonly_endpoints import run_smoke
        report = run_smoke()
        _add("backend smoke 여전히 PASS", report.verdict != "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_BLOCKED",
             report.verdict)
    except Exception as e:
        _add("backend smoke 여전히 PASS", False, str(e))


def print_report() -> str:
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)

    print(f"\n{'=' * 64}")
    print("APP_UI_READONLY_STATUS_CARDS_API_BIND AUDIT")
    print(f"{'=' * 64}")
    for name, result, detail in checks:
        status = "PASS" if result else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"{'=' * 64}")
    print(f"  총 {len(checks)}개 검사: PASS={passed}, FAIL={failed}")

    if failed == 0:
        verdict = VERDICT_READY
    elif failed <= 2:
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
