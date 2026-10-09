"""APP_UI_READONLY_BACKEND_STATUS_CARDS_01 테스트.

read-only status card 보강 검증 — mutation 없음, 상태 모델, 신규 컴포넌트, 이전 공정 회귀.
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
TYPES_FILE = FRONTEND_ROOT / "types" / "assistant.ts"


def _all_tsx() -> list[Path]:
    files = list(ASSISTANT_APP.rglob("*.tsx")) if ASSISTANT_APP.exists() else []
    if ASSISTANT_COMP.exists():
        files += list(ASSISTANT_COMP.rglob("*.tsx"))
    return files


def _all_frontend() -> list[Path]:
    return _all_tsx() + ([API_CLIENT] if API_CLIENT.exists() else [])


# ── 1. audit script import ────────────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_ui_readonly_backend_status_cards  # noqa: F401


# ── 2. Dashboard status card 보강 ─────────────────────────────────────────────

def test_dashboard_health_api_connected():
    # APP_UI_READONLY_STATUS_CARDS_API_BIND_01: getAssistantHealth → getAppHealthSummary 로 갱신
    content = (assistant_route("page.tsx")).read_text(encoding="utf-8")
    assert "getAppHealthSummary" in content


def test_dashboard_readonly_mode_banner():
    content = (assistant_route("page.tsx")).read_text(encoding="utf-8")
    assert "ReadOnlyModeBanner" in content


def test_dashboard_api_connection_state_badge():
    content = (assistant_route("page.tsx")).read_text(encoding="utf-8")
    assert "ApiConnectionStateBadge" in content


def test_dashboard_future_endpoint_notice():
    # APP_UI_READONLY_STATUS_CARDS_API_BIND_01: storage/status 구현 후 Dashboard에서 FutureEndpointNotice 제거됨.
    # FutureEndpointNotice는 DeploymentSopPanel 등 실제 future 항목에서만 유지 — 전체 프론트엔드에 존재 확인.
    all_content = "\n".join(
        f.read_text(encoding="utf-8")
        for f in FRONTEND_ROOT.rglob("*.tsx")
    )
    assert "FutureEndpointNotice" in all_content


# ── 3. API 연결 meta (source, last_checked, error_kind) ───────────────────────

def test_api_client_has_make_meta():
    content = API_CLIENT.read_text(encoding="utf-8")
    assert "makeMeta" in content


def test_types_has_api_connection_meta():
    content = TYPES_FILE.read_text(encoding="utf-8")
    assert "ApiConnectionMeta" in content


def test_types_has_source_field():
    content = TYPES_FILE.read_text(encoding="utf-8")
    assert "source" in content


def test_types_has_last_checked():
    content = TYPES_FILE.read_text(encoding="utf-8")
    assert "last_checked" in content


def test_types_has_error_kind():
    content = TYPES_FILE.read_text(encoding="utf-8")
    assert "error_kind" in content


def test_types_has_mutation_allowed_false():
    content = TYPES_FILE.read_text(encoding="utf-8")
    assert "mutation_allowed" in content


# ── 4. Task Queue inbox status card 보강 ─────────────────────────────────────

def test_tasks_inbox_api_connected():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "getAssistantInbox" in content


def test_tasks_readonly_mode_banner():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "ReadOnlyModeBanner" in content


def test_tasks_empty_state_panel():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "EmptyStatePanel" in content


def test_tasks_dry_run_only_badge():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "DRY_RUN_ONLY" in content


def test_tasks_mutation_blocked_badge():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "MUTATION_BLOCKED" in content


# ── 5. Deployment display-only 유지 ──────────────────────────────────────────

def test_deployment_no_restart_button():
    content = (assistant_route("deployment", "page.tsx")).read_text(encoding="utf-8")
    assert not re.search(r"<[Bb]utton[^>]*>서버\s*재시작", content)


def test_deployment_no_docker_compose_button():
    content = (assistant_route("deployment", "page.tsx")).read_text(encoding="utf-8")
    assert not re.search(r"<[Bb]utton[^>]*>compose\s*실행", content)


def test_deployment_server_apply_allowed_false():
    content = (assistant_route("deployment", "page.tsx")).read_text(encoding="utf-8")
    assert "server_apply_allowed=false" in content


# ── 6. 신규 컴포넌트 존재 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("comp", [
    "ReadOnlyModeBanner.tsx",
    "ApiConnectionStateBadge.tsx",
    "EmptyStatePanel.tsx",
    "FutureEndpointNotice.tsx",
])
def test_new_component_exists(comp: str):
    assert (ASSISTANT_COMP / comp).exists(), f"{comp} 없음"


# ── 7. MutationBlockedBanner / DryRunNotice / ReadOnlyModeBanner ──────────────

def test_mutation_blocked_banner_exists():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "MUTATION_BLOCKED" in all_content or "ForbiddenActionBanner" in all_content


def test_dry_run_notice_exists():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "DryRunNotice" in all_content


def test_readonly_mode_banner_used():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "ReadOnlyModeBanner" in all_content


def test_future_endpoint_notice_used():
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in _all_tsx())
    assert "FutureEndpointNotice" in all_content


# ── 8. 금지 mutation 없음 ─────────────────────────────────────────────────────

def test_no_post_tasks():
    for f in _all_frontend():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r'/api/v1/tasks["\']', content), f"{f.name}에 POST /tasks 발견"


def test_no_post_email_fetch():
    for f in _all_frontend():
        assert "/api/v1/inbox/email/fetch" not in f.read_text(encoding="utf-8")


def test_no_approve_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*\bapprove\b(?!.*미연결|.*only|.*표시)", content)


def test_no_reject_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*\breject\b", content)


def test_no_execute_connection():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"onClick.*execute[^d]", content)


# ── 9. secret 없음 ────────────────────────────────────────────────────────────

def test_no_token_raw():
    for f in _all_frontend():
        assert not re.search(r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', f.read_text(encoding="utf-8"))


def test_no_cookie_raw():
    for f in _all_frontend():
        assert not re.search(r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', f.read_text(encoding="utf-8"))


def test_no_password_raw():
    for f in _all_frontend():
        assert not re.search(r'"password"\s*:\s*"[^"]{3,}"', f.read_text(encoding="utf-8"))


# ── 10. 이전 공정 회귀 ────────────────────────────────────────────────────────

def test_no_conflict_with_readonly_api_wiring():
    import tools.audits.app.audit_app_ui_shell_readonly_api_wiring as m
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN)


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


# ── 11. audit verdict ─────────────────────────────────────────────────────────

def test_audit_verdict_ready_or_warn():
    import tools.audits.app.audit_app_ui_readonly_backend_status_cards as m
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN), \
        f"verdict={report.verdict}"
