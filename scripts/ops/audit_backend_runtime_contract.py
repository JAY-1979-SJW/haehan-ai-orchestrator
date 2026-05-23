"""Read-only backend runtime contract audit."""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_RUNTIME_ROUTES = 84

REQUIRED_ROUTES = {
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/tasks"),
    ("POST", "/api/v1/local-agents/{agent_id}/tasks"),
    ("POST", "/api/v1/local-agents/{agent_id}/browser-readonly-instructions"),
    ("GET", "/api/v1/agent-ai/health"),
    ("POST", "/api/v1/agent-ai/chat"),
    ("GET", "/api/v1/browser-approvals/requests"),
    ("POST", "/api/v1/browser-approvals/requests"),
    ("GET", "/api/v1/ops/summary"),
    ("GET", "/api/v1/app/health/summary"),
}

BACKEND_SOURCE_ROOTS = (
    ROOT / "ai_orchestrator",
    ROOT / "local_agent",
    ROOT / "desktop",
)

FORBIDDEN_BACKEND_PATTERNS = (
    re.compile(r"Bearer\s+admin-token"),
    re.compile(r"Authorization[^\n]{0,80}admin-token", re.IGNORECASE),
    re.compile(r"startswith\(\s*['\"]\/tmp"),
    re.compile(r"hardcoded\s+admin", re.IGNORECASE),
)


def iter_runtime_routes() -> list[tuple[str, str, str]]:
    from ai_orchestrator.server import app
    from fastapi.routing import APIRoute, APIWebSocketRoute

    routes: list[tuple[str, str, str]] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = sorted(method.upper() for method in (route.methods or []))
            method_label = methods[0] if len(methods) == 1 else ",".join(methods)
            routes.append((method_label, route.path, route.name))
        elif isinstance(route, APIWebSocketRoute):
            routes.append(("WEBSOCKET", route.path, route.name))
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
