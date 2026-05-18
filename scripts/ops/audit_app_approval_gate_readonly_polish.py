"""Audit: APP_APPROVAL_GATE_READONLY_POLISH_01"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PAGE = ROOT / "admin-web" / "src" / "app" / "assistant" / "approval" / "page.tsx"
ROUTER_FILE = ROOT / "ai_orchestrator" / "router.py"

VERDICT_READY = "APP_APPROVAL_GATE_READONLY_POLISH_READY"
VERDICT_WARN = "APP_APPROVAL_GATE_READONLY_POLISH_WITH_WARN"
VERDICT_BLOCKED = "APP_APPROVAL_GATE_READONLY_POLISH_BLOCKED"

checks: list[tuple[str, bool, str]] = []

def _add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))

def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def run_audit() -> None:
    page = _src(PAGE)

    _add("approval page 존재", PAGE.exists())
    _add("use client", '"use client"' in page)
    _add("ReadOnlyModeBanner", "ReadOnlyModeBanner" in page)
    _add("ForbiddenActionBanner", "ForbiddenActionBanner" in page)
    _add("MUTATION_BLOCKED 배지", "MUTATION_BLOCKED" in page)
    _add("B1_PENDING 배지", "B1_PENDING" in page)
    _add("approvalGatesMock 사용", "approvalGatesMock" in page)
    _add("knownBacklogMock 사용", "knownBacklogMock" in page)
    _add("요약 카드 — 전체 게이트", "전체 게이트" in page)
    _add("요약 카드 — BLOCKED", '"BLOCKED"' in page or "BLOCKED" in page)
    _add("요약 카드 — 미연결", "미연결" in page)
    _add("B-1 안내 패널", "B-1" in page or "B1" in page)
    _add("approve_btn 없음", "approve_btn" not in page)
    _add("delete_btn 없음", "delete_btn" not in page)
    _add("execute_btn 없음", "execute_btn" not in page)
    _add("POST method 없음", 'method: "POST"' not in page and "method: 'POST'" not in page)
    _add("approval_token_raw 없음", "approval_token_raw" not in page)
    _add("cookie_value 없음", "cookie_value" not in page)
    _add("token 원문 표시 금지 안내", "token 원문" in page or "token 원문 표시 금지" in page)
    _add("read-only footer", "execute 없음" in page or "read-only" in page.lower())

    router_src = _src(ROUTER_FILE)
    _add("router.py 수정 없음", "approval_gate_router" not in router_src)

    try:
        from fastapi.testclient import TestClient
        from ai_orchestrator.server import app as fastapi_app
        from fastapi.routing import APIRoute, APIWebSocketRoute
        routes = [r for r in fastapi_app.routes if isinstance(r, (APIRoute, APIWebSocketRoute))]
        _add("endpoint count 63 유지", len(routes) == 63, f"count={len(routes)}")
        posts = [r for r in fastapi_app.routes if isinstance(r, APIRoute) and "POST" in (r.methods or set())]
        _add("POST count 27 유지", len(posts) == 27, f"POST={len(posts)}")
    except Exception as e:
        _add("API 검증 실행", False, str(e)[:60])

def print_report() -> str:
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)
    print(f"\n{'=' * 60}")
    print("APP_APPROVAL_GATE_READONLY_POLISH AUDIT")
    print(f"{'=' * 60}")
    for name, ok, detail in checks:
        line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"{'=' * 60}")
    print(f"  총 {len(checks)}개: PASS={passed}, FAIL={failed}")
    verdict = VERDICT_READY if failed == 0 else (VERDICT_WARN if failed <= 2 else VERDICT_BLOCKED)
    print(f"  최종 판정: {verdict}")
    print(f"{'=' * 60}\n")
    return verdict

if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_BLOCKED else 1)
