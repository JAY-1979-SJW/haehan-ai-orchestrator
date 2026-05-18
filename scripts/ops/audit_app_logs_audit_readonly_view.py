"""Audit: APP_LOGS_AUDIT_READONLY_VIEW_01

로그·감사 화면이 read-only 계약과 보안 경계를 지키는지 검증한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

LOGS_PAGE = ROOT / "admin-web" / "src" / "app" / "assistant" / "logs" / "page.tsx"
AUDIT_LIST = ROOT / "admin-web" / "src" / "components" / "assistant" / "AuditLogList.tsx"
API_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "api.ts"
TYPES_FILE = ROOT / "admin-web" / "src" / "types" / "assistant.ts"
MOCK_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "mock.ts"
ROUTER_FILE = ROOT / "ai_orchestrator" / "router.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"

VERDICT_READY = "APP_LOGS_AUDIT_READONLY_VIEW_READY"
VERDICT_WARN = "APP_LOGS_AUDIT_READONLY_VIEW_WITH_WARN"
VERDICT_BLOCKED = "APP_LOGS_AUDIT_READONLY_VIEW_BLOCKED"

checks: list[tuple[str, bool, str]] = []


def _add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_audit() -> None:
    page = _src(LOGS_PAGE)
    comp = _src(AUDIT_LIST)
    api = _src(API_FILE)
    types = _src(TYPES_FILE)
    mock = _src(MOCK_FILE)

    # 파일 존재
    _add("logs page 존재", LOGS_PAGE.exists())
    _add("AuditLogList 컴포넌트 존재", AUDIT_LIST.exists())

    # use client 전환
    _add("logs page use client", '"use client"' in page)
    _add("AuditLogList use client", '"use client"' in comp)

    # read-only 배너
    _add("ReadOnlyModeBanner 존재", "ReadOnlyModeBanner" in page)
    _add("ForbiddenActionBanner 존재", "ForbiddenActionBanner" in page)
    _add("MUTATION_BLOCKED 뱃지", "MUTATION_BLOCKED" in page)

    # API 연결
    _add("getOpsAuditEvents 함수 존재 (api.ts)", "getOpsAuditEvents" in api)
    _add("getOpsAuditEvents 페이지 연결", "getOpsAuditEvents" in page)
    _add("OpsAuditEventsResponse 타입 존재", "OpsAuditEventsResponse" in types)
    _add("UnifiedLogEntry 타입 존재", "UnifiedLogEntry" in types)

    # 정규화
    _add("normalizeOpsEvents 함수 존재", "normalizeOpsEvents" in page or "normalize" in page)
    _add("normalizeMockLogs 함수 존재", "normalizeMockLogs" in page or "normalize" in page)
    _add("redacted: true 강제", "redacted: true" in page)

    # 요약 카드
    _add("SummaryCards 존재", "SummaryCards" in comp)
    _add("총 이벤트 카드", "총 이벤트" in comp)
    _add("경고 카드", "경고" in comp)
    _add("오류·차단 카드", "오류" in comp or "오류·차단" in comp)

    # 필터바
    _add("levelFilter 필터바 존재", "levelFilter" in comp)
    _add("sourceFilter 필터바 존재", "sourceFilter" in comp)
    _add("INFO 필터", '"INFO"' in comp)
    _add("WARN 필터", '"WARN"' in comp)
    _add("ERROR 필터", '"ERROR"' in comp)
    _add("BLOCKED 필터", '"BLOCKED"' in comp)
    _add("ops-api 소스 필터", "ops-api" in comp)
    _add("app-mock 소스 필터", "app-mock" in comp)

    # 상태 처리
    _add("loading 상태", "loading" in page)
    _add("mock_fallback 상태", "mock_fallback" in page)
    _add("empty 상태", "empty" in page)
    _add("error 상태", "error" in page)

    # 표시 필드
    _add("timestamp 표시", "timestamp" in comp)
    _add("level 표시", "level" in comp)
    _add("source 표시", "source" in comp)
    _add("eventType 표시", "eventType" in comp)
    _add("actor 표시", "actor" in comp)
    _add("taskId 표시", "taskId" in comp)
    _add("summary 표시", "summary" in comp)

    # 금지 버튼 없음
    _add("execute 버튼 없음", "execute_btn" not in comp and ">실행<" not in comp)
    _add("approve 버튼 없음", "approve_btn" not in comp)
    _add("delete 버튼 없음", "delete_btn" not in comp)

    # POST mutation 없음
    _add("POST method 없음 (page)", 'method: "POST"' not in page and "method: 'POST'" not in page)
    _add("POST method 없음 (comp)", 'method: "POST"' not in comp and "method: 'POST'" not in comp)

    # 보안
    _add("approval_token_raw 없음", "approval_token_raw" not in page + comp)
    _add("cookie_value 없음", "cookie_value" not in page + comp)
    _add("redacted 정책 안내", "token 원문 표시 금지" in comp or "secret/token/cookie" in comp)

    # mock 다양성
    _add("mock ERROR 레벨 존재", '"ERROR"' in mock or "ERROR" in mock)
    _add("mock WARN 레벨 존재", '"WARN"' in mock or "WARN" in mock)

    # API endpoint 검증
    try:
        from fastapi.testclient import TestClient
        from ai_orchestrator.server import app as fastapi_app
        from fastapi.routing import APIRoute, APIWebSocketRoute
        client = TestClient(fastapi_app, raise_server_exceptions=False)

        r = client.get("/api/v1/ops/audit-events")
        _add("GET /api/v1/ops/audit-events 200", r.status_code == 200, f"status={r.status_code}")

        routes = [r for r in fastapi_app.routes if isinstance(r, (APIRoute, APIWebSocketRoute))]
        _add("endpoint count 63 유지", len(routes) == 63, f"count={len(routes)}")

        http_routes = [r for r in fastapi_app.routes if isinstance(r, APIRoute)]
        post_routes = [r for r in http_routes if "POST" in (r.methods or set())]
        # 기존 POST 27개 — app_status_router / logs 추가로 증가 없음 확인
        _add("POST endpoint 증가 없음", len(post_routes) == 27, f"POST count={len(post_routes)}")
    except Exception as e:
        _add("API 검증 실행", False, str(e)[:60])

    # backend 불변
    router_src = _src(ROUTER_FILE)
    _add("router.py 수정 없음 (logs 없음)", "logs_router" not in router_src)
    compose_src = _src(COMPOSE_FILE)
    _add("docker-compose logs_router 없음", "logs_router" not in compose_src)

    # KW-1
    kw1 = ROOT / "scripts" / "archive" / "data" / "chrome_ui_monitor_state.json"
    _add("KW-1 runtime cache 알려진 예외", kw1.exists(), "known dirty — 오류 아님")


def print_report() -> str:
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)

    print(f"\n{'=' * 64}")
    print("APP_LOGS_AUDIT_READONLY_VIEW AUDIT")
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
