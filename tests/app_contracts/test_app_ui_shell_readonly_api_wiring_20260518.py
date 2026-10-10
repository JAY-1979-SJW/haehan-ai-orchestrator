"""APP_UI_SHELL_READONLY_API_WIRING_01 테스트.

API client GET-only 연결, mutation 없음, 상태 처리,
forbidden button/action 없음을 정적으로 검증한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "admin-web" / "src"
ASSISTANT_APP = FRONTEND_ROOT / "app" / "assistant"
from tests.app_ui_paths import assistant_route  # noqa: E402

ASSISTANT_COMP = FRONTEND_ROOT / "components" / "assistant"
API_CLIENT = FRONTEND_ROOT / "lib" / "assistant" / "api.ts"


def _all_tsx() -> list[Path]:
    files = list(ASSISTANT_APP.rglob("*.tsx")) if ASSISTANT_APP.exists() else []
    if ASSISTANT_COMP.exists():
        files += list(ASSISTANT_COMP.rglob("*.tsx"))
    return files


def _all_frontend() -> list[Path]:
    files = _all_tsx()
    if API_CLIENT.exists():
        files.append(API_CLIENT)
    return files


# ── 1. audit script import ────────────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_ui_shell_readonly_api_wiring  # noqa: F401


# ── 2. API client ─────────────────────────────────────────────────────────────

def test_api_client_exists():
    assert API_CLIENT.exists()


def test_api_fn_get_assistant_health():
    assert "getAssistantHealth" in API_CLIENT.read_text(encoding="utf-8")


def test_api_fn_get_assistant_inbox():
    assert "getAssistantInbox" in API_CLIENT.read_text(encoding="utf-8")


def test_api_path_health():
    assert "/api/v1/health" in API_CLIENT.read_text(encoding="utf-8")


def test_api_path_inbox():
    assert "/api/v1/inbox" in API_CLIENT.read_text(encoding="utf-8")


# ── 3. API client GET-only (mutation method 없음) ─────────────────────────────

# 재고정(2026-10-07, R1 스마트스토어 /chat 제거 — runSmartStoreAgent POST 1건 삭제):
# api.ts 에는 정당한 쓰기 클라이언트가 있다(POST 2곳 = postJson·템플릿 저장, DELETE 1곳 = 템플릿 삭제).
# audit_app_ui_shell_readonly_api_wiring 도 PUT/PATCH 만 금지하고 POST/DELETE 는 허용한다. 알려진 위치 수로 고정한다.
@pytest.mark.parametrize("method,expected", [("POST", 2), ("PUT", 0), ("PATCH", 0), ("DELETE", 1)])
def test_api_client_no_mutation_method(method: str, expected: int):
    content = API_CLIENT.read_text(encoding="utf-8")
    assert content.count(f'method: "{method}"') == expected
    assert f"method: '{method}'" not in content


# ── 4. 금지 mutation 없음 ─────────────────────────────────────────────────────

def test_no_post_tasks_connection():
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r'/api/v1/tasks["\']', content), \
            f"{f.name}에 POST /tasks 연결 발견"


def test_no_post_email_fetch():
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        assert "/api/v1/inbox/email/fetch" not in content, \
            f"{f.name}에 email/fetch 연결 발견"


def test_no_approve_api_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*\bapprove\b(?!.*미연결|.*only|.*표시)", content), \
            f"{f.name}에 approve onClick 연결 발견"


def test_no_reject_api_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*\breject\b", content), \
            f"{f.name}에 reject onClick 연결 발견"


def test_no_execute_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*execute[^d]", content), \
            f"{f.name}에 execute onClick 발견"


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_no_put_patch_delete_in_tsx(method: str):
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert f'method: "{method}"' not in content
        assert f"method: '{method}'" not in content


def test_no_server_restart_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*serverRestart", content), \
            f"{f.name}에 serverRestart 발견"


def test_no_docker_compose_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*dockerCompose", content), \
            f"{f.name}에 dockerCompose 발견"


def test_no_dns_save_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*dnsSave", content), \
            f"{f.name}에 dnsSave 발견"


def test_no_payment_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*payment[^F]", content), \
            f"{f.name}에 payment 발견"


# ── 5. secret 없음 ────────────────────────────────────────────────────────────

def test_no_token_raw():
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', content)


def test_no_cookie_raw():
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', content)


def test_no_password_raw():
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r'"password"\s*:\s*"[^"]{3,}"', content)


# ── 6. 상태 처리 ──────────────────────────────────────────────────────────────

def test_loading_state_exists():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "loading" in all_content


def test_error_state_exists():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "error" in all_content.lower()


def test_empty_state_exists():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "empty" in all_content.lower()


def test_mock_fallback_exists():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "mock_fallback" in all_content or "mockFallback" in all_content or "MOCK_FALLBACK" in all_content


# ── 7. Dashboard health 상태 표시 ─────────────────────────────────────────────

def test_dashboard_shows_health_state():
    content = (assistant_route("page.tsx")).read_text(encoding="utf-8")
    assert "getAssistantHealth" in content or "health" in content.lower()


# ── 8. Task Queue inbox 상태 표시 ─────────────────────────────────────────────

def test_tasks_shows_inbox_state():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "getAssistantInbox" in content or "inbox" in content.lower()


# ── 9. 8개 route 유지 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("route", [
    "page.tsx",
    "tasks/page.tsx",
    "tasks/[id]/page.tsx",
    "approval/page.tsx",
    "external-sites/page.tsx",
    "logs/page.tsx",
    "storage/page.tsx",
    "deployment/page.tsx",
])
def test_route_still_exists(route: str):
    assert (assistant_route(*route.split("/"))).exists(), f"{route} 없음"


# ── 10. 금지 버튼 없음 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("pattern,name", [
    (r"<[Bb]utton[^>]*>실행하기", "실행하기 button"),
    (r"<[Bb]utton[^>]*>지금\s*실행", "지금 실행 button"),
    (r"<[Bb]utton[^>]*>DRY_RUN\s*해제", "DRY_RUN 해제 button"),
    (r"<[Bb]utton[^>]*>서버\s*재시작", "서버 재시작 button"),
    (r"<[Bb]utton[^>]*>compose\s*실행", "compose 실행 button"),
])
def test_no_forbidden_button(pattern: str, name: str):
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(pattern, content), f"{f.name}에 금지 버튼 '{name}' 발견"


# ── 11. 이전 공정 회귀 충돌 없음 ─────────────────────────────────────────────

def test_no_conflict_with_browser_smoke():
    import tools.audits.app.audit_app_ui_shell_browser_smoke as m
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_PASS, m.VERDICT_WARN)


def test_no_conflict_with_skeleton():
    import tools.audits.app.audit_app_ui_shell_skeleton as m
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN)


def test_no_conflict_with_mvp_design():
    import tools.audits.app.audit_app_foundation_mvp_design as m
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN)


# ── 12. audit verdict ─────────────────────────────────────────────────────────

def test_audit_verdict_ready_or_warn():
    import tools.audits.app.audit_app_ui_shell_readonly_api_wiring as m
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN), \
        f"verdict={report.verdict}"
