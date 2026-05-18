"""Audit: APP_DEPLOYMENT_READONLY_POLISH_01"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PAGE = ROOT / "admin-web" / "src" / "app" / "assistant" / "deployment" / "page.tsx"
ROUTER_FILE = ROOT / "ai_orchestrator" / "router.py"

VERDICT_READY = "APP_DEPLOYMENT_READONLY_POLISH_READY"
VERDICT_WARN = "APP_DEPLOYMENT_READONLY_POLISH_WITH_WARN"
VERDICT_BLOCKED = "APP_DEPLOYMENT_READONLY_POLISH_BLOCKED"

checks: list[tuple[str, bool, str]] = []

def _add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))

def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def run_audit() -> None:
    page = _src(PAGE)

    _add("deployment page 존재", PAGE.exists())
    _add("use client", '"use client"' in page)
    _add("ReadOnlyModeBanner", "ReadOnlyModeBanner" in page)
    _add("ForbiddenActionBanner", "ForbiddenActionBanner" in page)
    _add("MUTATION_BLOCKED 배지", "MUTATION_BLOCKED" in page)
    _add("server_apply_allowed=false 배지", "server_apply_allowed=false" in page)
    _add("BAKED_IN_IMAGE SOP 안내", "BAKED_IN_IMAGE" in page)
    _add("RESTART_ALONE_FORBIDDEN 안내", "RESTART_ALONE_FORBIDDEN" in page)
    _add("SOP steps 표시", "sop_steps" in page)
    _add("DeploymentSopPanel 사용", "DeploymentSopPanel" in page)
    _add("deploymentStatusMock 사용", "deploymentStatusMock" in page)
    _add("요약 카드 — 서버 HEAD", "서버 HEAD" in page)
    _add("요약 카드 — 동기화 상태", "동기화 상태" in page)
    _add("요약 카드 — 빌드 필요", "빌드 필요" in page)
    _add("restart_btn 없음", "restart_btn" not in page)
    _add("compose_btn 없음", "compose_btn" not in page)
    _add("POST method 없음", 'method: "POST"' not in page and "method: 'POST'" not in page)
    _add("approval_token_raw 없음", "approval_token_raw" not in page)
    _add("router.py 수정 없음", "deployment_router" not in _src(ROUTER_FILE))

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
    print("APP_DEPLOYMENT_READONLY_POLISH AUDIT")
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
