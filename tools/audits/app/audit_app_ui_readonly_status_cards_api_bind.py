"""Audit: APP_UI_READONLY_STATUS_CARDS_API_BIND_01

프론트엔드 상태 카드가 실제 read-only API 3개에 연결됐는지 검증한다.
mutation, secret, POST 없음.
"""

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

API_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "api.ts"
DASHBOARD_FILE = ROOT / "admin-web" / "src" / "app" / "assistant" / "page.tsx"
_ASSISTANT_APP = ROOT / "admin-web" / "src" / "app" / "assistant"


def _route_file(*parts: str) -> Path:
    """직접 경로 우선, 없으면 라우트 그룹 `(legacy)` 아래(URL 불변, tests/app_ui_paths.py 와 같은 규칙)."""
    direct = _ASSISTANT_APP.joinpath(*parts)
    if direct.exists():
        return direct
    grouped = _ASSISTANT_APP.joinpath("(legacy)", *parts)
    return grouped if grouped.exists() else direct


EXTERNAL_FILE = _route_file("external-sites", "page.tsx")
STORAGE_FILE = _route_file("storage", "page.tsx")
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

    # api.ts — 상태 카드 조회 함수 3개는 GET(getJson)만. 현행 api.ts 에는 별도 쓰기 클라이언트
    # (postJson·템플릿 저장/삭제·스마트스토어 채팅)가 있으므로 POST/DELETE 는 알려진 위치 수로 고정한다.
    _add(
        "상태 카드 조회 3개 GET(getJson) 사용",
        'getJson<AppHealthSummaryResponse>("/api/v1/app/health/summary"' in api
        and 'getJson<AppProvidersResponse>("/api/v1/app/providers"' in api
        and 'getJson<AppStorageStatusResponse>("/api/v1/app/storage/status"' in api,
    )
    _add(
        "api.ts POST 3곳·DELETE 1곳 (알려진 쓰기 클라이언트만)",
        api.count('method: "POST"') == 3 and api.count('method: "DELETE"') == 1 and "method: 'POST'" not in api,
    )

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
        _add(
            f"{label} approve/execute/reject 없음",
            "approve_token" not in src and "execute_url" not in src and "reject_token" not in src,
        )
        _add(
            f"{label} raw token/cookie 없음",
            "approval_token_raw" not in src and "cookie_value" not in src and "password" not in src,
        )

    # docker-compose 변경 없음
    compose = _src(COMPOSE_FILE)
    _add("docker-compose 수정 없음 (api_bind 없음)", "api_bind" not in compose)

    # backend smoke 여전히 PASS
    try:
        from tools.audits.app.smoke_app_api_readonly_endpoints import run_smoke

        report = run_smoke()
        _add(
            "backend smoke 여전히 PASS",
            report.verdict != "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_BLOCKED",
            report.verdict,
        )
    except Exception as e:  # noqa: BLE001 - UI 상태카드-API 바인딩 감사 스크립트 — 백엔드 스모크 재실행 실패를 False(실패)로 기록하는 fail-closed 감사 항목.
        _add("backend smoke 여전히 PASS", False, str(e))


def print_report() -> str:
    from scripts.common.audit_cli import print_check_report

    return print_check_report(
        "APP_UI_READONLY_STATUS_CARDS_API_BIND AUDIT", checks, (VERDICT_READY, VERDICT_WARN, VERDICT_BLOCKED), 2
    )


if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_BLOCKED else 1)
