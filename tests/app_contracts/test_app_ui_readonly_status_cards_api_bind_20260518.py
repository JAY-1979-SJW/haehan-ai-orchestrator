"""Tests: APP_UI_READONLY_STATUS_CARDS_API_BIND_01 (2026-05-18)

프론트 상태 카드 3개가 실제 read-only API에 연결됐는지 검증.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

API_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "api.ts"
DASHBOARD_FILE = assistant_route("page.tsx")
EXTERNAL_FILE = assistant_route("external-sites", "page.tsx")
STORAGE_FILE = assistant_route("storage", "page.tsx")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── import 가능 여부 ──────────────────────────────────────────────────────────


def test_audit_script_import():
    import tools.audits.app.audit_app_ui_readonly_status_cards_api_bind  # noqa


# ── api.ts 신규 함수 ──────────────────────────────────────────────────────────


def test_api_file_exists():
    assert API_FILE.exists()


def test_api_get_app_health_summary():
    assert "getAppHealthSummary" in _read(API_FILE)


def test_api_get_app_providers():
    assert "getAppProviders" in _read(API_FILE)


def test_api_get_app_storage_status():
    assert "getAppStorageStatus" in _read(API_FILE)


def test_api_health_summary_type():
    assert "AppHealthSummaryResponse" in _read(API_FILE)


def test_api_providers_type():
    assert "AppProvidersResponse" in _read(API_FILE)


def test_api_storage_status_type():
    assert "AppStorageStatusResponse" in _read(API_FILE)


def test_api_health_path():
    assert "/api/v1/app/health/summary" in _read(API_FILE)


def test_api_providers_path():
    assert "/api/v1/app/providers" in _read(API_FILE)


def test_api_storage_path():
    assert "/api/v1/app/storage/status" in _read(API_FILE)


def test_api_no_post():
    src = _read(API_FILE)
    # 재고정(2026-10-07, R1 스마트스토어 /chat 제거 — runSmartStoreAgent POST 1건 삭제):
    # api.ts 에는 쓰기 클라이언트(postJson·템플릿 저장/삭제)가 있다. 상태 카드 조회 3개는
    # GET 전용을 유지하고, POST/DELETE 는 알려진 위치 수(POST 3→2·DELETE 1)로 고정해
    # 새 쓰기 호출이 조용히 늘면 실패한다.
    assert 'getJson<AppHealthSummaryResponse>("/api/v1/app/health/summary"' in src
    assert 'getJson<AppProvidersResponse>("/api/v1/app/providers"' in src
    assert 'getJson<AppStorageStatusResponse>("/api/v1/app/storage/status"' in src
    assert src.count('method: "POST"') == 2
    assert src.count('method: "DELETE"') == 1
    assert "method: 'POST'" not in src


# ── Dashboard 연결 ────────────────────────────────────────────────────────────


def test_dashboard_uses_get_app_health_summary():
    assert "getAppHealthSummary" in _read(DASHBOARD_FILE)


def test_dashboard_mock_fallback():
    assert "mock_fallback" in _read(DASHBOARD_FILE)


def test_dashboard_no_approve_execute():
    src = _read(DASHBOARD_FILE)
    assert "approve_token" not in src
    assert "execute_url" not in src


def test_dashboard_no_raw_token():
    src = _read(DASHBOARD_FILE)
    assert "approval_token_raw" not in src


# ── External Sites 연결 ──────────────────────────────────────────────────────


def test_external_uses_get_app_providers():
    assert "getAppProviders" in _read(EXTERNAL_FILE)


def test_external_mock_fallback():
    assert "mock_fallback" in _read(EXTERNAL_FILE)


def test_external_map_providers():
    assert "mapProviders" in _read(EXTERNAL_FILE)


def test_external_cookie_storage_forbidden_true():
    assert "cookie_storage_forbidden: true" in _read(EXTERNAL_FILE)


def test_external_no_raw_token():
    src = _read(EXTERNAL_FILE)
    assert "approval_token_raw" not in src


# ── Storage 연결 ─────────────────────────────────────────────────────────────


def test_storage_uses_get_app_storage_status():
    assert "getAppStorageStatus" in _read(STORAGE_FILE)


def test_storage_mock_fallback():
    assert "mock_fallback" in _read(STORAGE_FILE)


def test_storage_map_storage():
    assert "mapStorage" in _read(STORAGE_FILE)


def test_storage_no_raw_token():
    src = _read(STORAGE_FILE)
    assert "approval_token_raw" not in src


# ── 충돌 없음 ─────────────────────────────────────────────────────────────────


def test_no_conflict_with_implementation():
    import tests.app_contracts.test_app_api_readonly_endpoints_implementation_20260518  # noqa


def test_no_conflict_with_browser_smoke():
    import tests.app_contracts.test_app_api_readonly_endpoints_browser_smoke_20260518  # noqa


def test_no_conflict_with_plan():
    import tests.app_contracts.test_app_api_readonly_endpoints_implementation_plan_20260518  # noqa


# ── backend smoke 여전히 PASS ─────────────────────────────────────────────────


def test_backend_smoke_still_passes():
    from tools.audits.app.smoke_app_api_readonly_endpoints import run_smoke

    report = run_smoke()
    assert report.verdict != "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_BLOCKED"
    assert len(report.failed_endpoints) == 0


# ── audit verdict ─────────────────────────────────────────────────────────────


def test_audit_verdict():
    from tools.audits.app.audit_app_ui_readonly_status_cards_api_bind import print_report, run_audit

    run_audit()
    verdict = print_report()
    assert "BLOCKED" not in verdict, f"audit BLOCKED: {verdict}"
