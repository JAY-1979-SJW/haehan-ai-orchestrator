"""Read-only backend runtime contract audit."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTATION_PATH = ROOT / "configs" / "route_count_expectation.json"


def load_route_count_expectation(path: Path = EXPECTATION_PATH) -> dict[str, int]:
    """라우트 개수 단일 정본(configs/route_count_expectation.json)을 읽는다. 형식이 틀리면 즉시 실패한다(조용히 넘어가지 않음)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for key in ("total", "http", "websocket", "post"):
        value = raw.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{path.name}: '{key}' 는 0 이상의 정수여야 한다(현재 {value!r})")
        counts[key] = value
    if counts["total"] != counts["http"] + counts["websocket"]:
        raise ValueError(
            f"{path.name}: total({counts['total']}) != http({counts['http']}) + websocket({counts['websocket']})"
        )
    return counts


_EXPECTED = load_route_count_expectation()
EXPECTED_HTTP_ROUTES = _EXPECTED["http"]
EXPECTED_WEBSOCKET_ROUTES = _EXPECTED["websocket"]
EXPECTED_POST_ROUTES = _EXPECTED["post"]
# 정본은 configs/route_count_expectation.json — 라우트를 추가·삭제하면 그 파일 한 곳만 고친다.
# 2026-10-07 M12 통합(stage/integrate-m12): 업무 후보·명세 /site-map/{host}/candidates GET·
# spec POST/GET 3개가 route_count_expectation.json에 반영됐다(아래 실측 확인). 이전 재고정
# 이력(M11 이전)은 git log(이 파일 과거 버전)로 확인한다 — 이 주석에 더는 누적하지 않는다.
EXPECTED_RUNTIME_ROUTES = _EXPECTED["total"]
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
    config_text = (ROOT / "ai_orchestrator" / "core" / "config.py").read_text(encoding="utf-8", errors="replace")
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
