"""Read-only backend runtime contract audit."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_RUNTIME_ROUTES = 429  # 2026-10-05 재고정: 지도 이력 /site-map/{host}/history·/diff GET 2개 추가(427→429, 삭제 0, M11); 이전: 2026-10-05 재고정: 사이트 사전 조사 /site-registry/{host}/preflight GET·POST 2개 추가(425→427, 삭제 0, M10); 이전: 2026-10-05 재고정: 가입 카페 변동 조회 GET /naver-cafe/my-cafes/changes 1개 추가(424→425, 삭제 0); 이전: 2026-10-05 재고정: 사이트 등록 /site-registry 5개 추가(GET 2·POST 2·PATCH 1, 419→424, 삭제 0, M7-S1); 이전: 2026-10-04 재고정: origin/master 402(/dev-reg/approvals GET 3개 복원) 위에 이 브랜치의 공무 AI 초안·사이트 업무 지도·벤더 조회 17개 추가(삭제 0); 이전(이 브랜치): 2026-10-04 재고정: 벤더 공식 API 조회 /vendors/lookup 1개 추가(415→416, 삭제 0); 이전: 2026-10-04 재고정: 사이트 업무 지도 M5 /site-map/{host}/run 1개 추가(414→415, 삭제 0); 이전: 2026-10-03 재고정: 공무 AI 초안 /gongmu/drafts 5개 + 사이트 업무 지도 /site-map 10개(조회·확정·결과 기록 5 + 탐색 요청 5) 추가(399→414, 삭제 0); 이전: 2026-10-02 재고정: 건설업 공무 업무판 /gongmu 19개 추가(380→399, 삭제 0); 이전: AI 작업 분배 /ai-agent/dispatch 5개 추가(375→380, 삭제 0). 기준값 369는 HEAD 실측 375 보다 6개 뒤처져 있었음(하나팩스 등 이후 라우트 미반영); 이전: 2026-10-02 메일 순차 대량 발송 /mail-bulk 13개 추가 + 하나팩스 미리보기(P4c, e88a39ea) 5개 실측 반영(351→369); 이전: 새 메일 알림 /inbox-watch +1; 재고정(2026-10-02): 네이버 메일함 탭 라우트 22개 추가 확인(삭제 0) — /naver-mailbox* 조회·첨부·삭제/이동·보내기 2단계 13 + AI 업무 창(새 메일·가벼운 상세·초안·업무 지침) 9. HEAD 실측 328 → 350.; 이전(master): 2026-10-04 재고정: 개발자 등록 승인 조회 /dev-reg/approvals(pending·history·{task_id}) GET 3개 복원(399→402, 삭제 0, 3c155f55 hotfix 때 빠졌던 것); 이전: 2026-10-02 재고정: 건설업 공무 업무판 /gongmu 19개 추가(380→399, 삭제 0); 이전: AI 작업 분배 /ai-agent/dispatch 5개 추가(375→380, 삭제 0). 기준값 369는 HEAD 실측 375 보다 6개 뒤처져 있었음(하나팩스 등 이후 라우트 미반영); 이전: 2026-10-02 메일 순차 대량 발송 /mail-bulk 13개 추가 + 하나팩스 미리보기(P4c, e88a39ea) 5개 실측 반영(351→369); 이전: 새 메일 알림 /inbox-watch +1; 재고정(2026-10-02): 네이버 메일함 탭 라우트 22개 추가 확인(삭제 0) — /naver-mailbox* 조회·첨부·삭제/이동·보내기 2단계 13 + AI 업무 창(새 메일·가벼운 상세·초안·업무 지침) 9. HEAD 실측 328 → 350.
# 이전 재고정(2026-10-01): 신규 기능 라우트 25개 추가 확인(삭제 0) — 예약 작업 12(/scheduled-jobs*)·블로그 자동화 11(/blog-automation*)·네이버 세션 2(/live·/ensure). 전 292→후 317.
# 이전 재고정(2026-09-30): 채팅 세션 라우트 5개(/chat/sessions*) 추가 + 로컬 FastAPI 를
# 0.142(iter_route_contexts 지원)로 올려 이 검사가 다시 실행되며 확인한 실측값(전 287→후 292).
# 이전 값: 284 (2026-09-29): FastAPI _IncludedRouter 지연평가 버그로
# 206 이후 실제 신규 라우트 다수가 계속 감지 안 되고 있었음(defect_index #39·#40) — 이번에
# iter_route_contexts 로 introspection 을 고친 뒤 실측한 정확한 현재 값으로 재고정.

REQUIRED_ROUTES = {
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/tasks"),
    ("POST", "/api/v1/local-agents/{agent_id}/tasks"),
    ("POST", "/api/v1/local-agents/{agent_id}/browser-readonly-instructions"),
    ("GET", "/api/v1/browser-approvals/requests"),
    ("POST", "/api/v1/browser-approvals/requests"),
    ("GET", "/api/v1/ops/summary"),
    ("GET", "/api/v1/app/health/summary"),
}

BACKEND_SOURCE_ROOTS = (
    ROOT / "ai_orchestrator",
    ROOT / "local_agent",
)

FORBIDDEN_BACKEND_PATTERNS = (
    re.compile(r"Bearer\s+admin-token"),
    re.compile(r"Authorization[^\n]{0,80}admin-token", re.IGNORECASE),
    re.compile(r"startswith\(\s*['\"]\/tmp"),
    re.compile(r"hardcoded\s+admin", re.IGNORECASE),
)


def iter_runtime_routes() -> list[tuple[str, str, str]]:
    # FastAPI 0.137+ 부터 include_router() 가 즉시 라우트를 펼치지 않고 지연 래퍼
    # (_IncludedRouter) 로 저장해 app.routes 를 바로 순회하면 서브라우터의 실제 라우트를
    # 거의 못 찾는다(2026-09-29 defect_index #39·#40, ai_orchestrator/routers/app_actions.py
    # 와 동일 근본원인 — 공식 fastapi.routing.iter_route_contexts 로 해결).
    from fastapi.routing import APIRoute, APIWebSocketRoute, iter_route_contexts

    from ai_orchestrator.asgi import app

    routes: list[tuple[str, str, str]] = []
    for ctx in iter_route_contexts(app.routes):
        route = ctx.original_route
        if isinstance(route, APIRoute):
            methods = sorted(ctx.methods or set())
            method_label = methods[0] if len(methods) == 1 else ",".join(methods)
            routes.append((method_label, ctx.path, ctx.name or ""))
        elif isinstance(route, APIWebSocketRoute):
            # RouteContext.path/path_format 이 웹소켓 라우트에서는 빈 문자열을 반환함
            # (2026-09-29 실측, fastapi 0.141.1 — APIRoute 는 정상). 내부 _effective_route
            # (_EffectiveRouteContext).starlette_route 에는 실제 prefix 가 반영된 경로가
            # 있어 그걸로 보완(비공개 속성 의존 — 이후 fastapi 버전에서 바뀔 수 있음,
            # RouteContext.path 가 웹소켓도 정상화되면 이 분기는 제거 가능).
            eff = getattr(ctx, "_effective_route", None)
            starlette_route = getattr(eff, "starlette_route", None)
            full_path = getattr(starlette_route, "path", None) or route.path
            routes.append(("WEBSOCKET", full_path, route.name))
    return sorted(routes)


def find_duplicate_routes(routes: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    for method, path, _name in routes:
        key = (method, path)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def scan_forbidden_backend_patterns() -> list[str]:
    findings: list[str] = []
    for root in BACKEND_SOURCE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in f"/{rel}/":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in FORBIDDEN_BACKEND_PATTERNS:
                if pattern.search(text):
                    findings.append(rel)
                    break
    return sorted(set(findings))


def auth_default_is_safe() -> bool:
    config_text = (ROOT / "ai_orchestrator" / "config.py").read_text(encoding="utf-8", errors="replace")
    return 'os.environ.get("AUTH_ENABLED", "true")' in config_text


def main() -> int:
    routes = iter_runtime_routes()
    route_keys = {(method, path) for method, path, _name in routes}
    failures: list[str] = []

    if len(routes) != EXPECTED_RUNTIME_ROUTES:
        failures.append(f"runtime route count {len(routes)} != {EXPECTED_RUNTIME_ROUTES}")

    missing = sorted(REQUIRED_ROUTES - route_keys)
    if missing:
        failures.append("missing required routes: " + ", ".join(f"{method} {path}" for method, path in missing))

    duplicates = find_duplicate_routes(routes)
    if duplicates:
        failures.append("duplicate routes: " + ", ".join(f"{method} {path}" for method, path in duplicates))

    forbidden = scan_forbidden_backend_patterns()
    if forbidden:
        failures.append("forbidden backend security pattern(s): " + ", ".join(forbidden))

    if not auth_default_is_safe():
        failures.append("AUTH_ENABLED default is not locked to true")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        print("RESULT=FAIL_BACKEND_RUNTIME_CONTRACT")
        return 1

    print(f"[PASS] runtime route count={len(routes)}")
    print("[PASS] required backend routes registered")
    print("[PASS] duplicate route check")
    print("[PASS] forbidden backend security pattern scan")
    print("[PASS] AUTH_ENABLED default is true")
    print("RESULT=PASS_BACKEND_RUNTIME_CONTRACT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
