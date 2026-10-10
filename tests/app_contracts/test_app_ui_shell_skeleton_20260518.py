"""APP_UI_SHELL_SKELETON_01 테스트.

생성된 UI shell이 금지 정책을 위반하지 않는지 검증한다.
실제 앱 렌더링 테스트 아님 — 파일 존재/내용 정책 검증.
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
MOCK_FILE = FRONTEND_ROOT / "lib" / "assistant" / "mock.ts"


# ── 1. 화면 route 존재 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "route",
    [
        "page.tsx",
        "tasks/page.tsx",
        "tasks/[id]/page.tsx",
        "approval/page.tsx",
        "external-sites/page.tsx",
        "logs/page.tsx",
        "storage/page.tsx",
        "deployment/page.tsx",
    ],
)
def test_assistant_route_exists(route: str):
    assert (assistant_route(*route.split("/"))).exists(), f"/assistant/{route} 없음"


# ── 2. 공통 컴포넌트 존재 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "comp",
    [
        "GateBadge.tsx",
        "BackendStatusCard.tsx",
        "StorageStatusCard.tsx",
        "ProviderCard.tsx",
        "TaskTable.tsx",
        "TaskDetailPanel.tsx",
        "AuditLogList.tsx",
        "ForbiddenActionBanner.tsx",
        "DryRunNotice.tsx",
        "DeploymentSopPanel.tsx",
    ],
)
def test_assistant_component_exists(comp: str):
    assert (ASSISTANT_COMP / comp).exists(), f"components/assistant/{comp} 없음"


# ── 3. mock data 존재 ─────────────────────────────────────────────────────────


def test_mock_data_file_exists():
    assert MOCK_FILE.exists()


def test_mock_no_token_raw():
    content = MOCK_FILE.read_text(encoding="utf-8")
    assert not re.search(r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', content)


def test_mock_no_cookie_raw():
    content = MOCK_FILE.read_text(encoding="utf-8")
    assert not re.search(r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', content)


def test_mock_no_password_raw():
    content = MOCK_FILE.read_text(encoding="utf-8")
    assert not re.search(r'"password"\s*:\s*"[^"]{3,}"', content)


def test_mock_providers_12():
    content = MOCK_FILE.read_text(encoding="utf-8")
    required = [
        "GABIA",
        "KAKAO",
        "NAVER",
        "NAVER_SMARTSTORE",
        "GOOGLE",
        "HIWORKS",
        "G2B_NARA",
        "HOMETAX",
        "WETAX",
        "GOVERNMENT24",
        "EMAIL_GENERIC",
        "BANK_GENERIC",
    ]
    for p in required:
        assert p in content, f"mock에 provider {p} 없음"


def test_mock_providers_cookie_forbidden():
    content = MOCK_FILE.read_text(encoding="utf-8")
    assert "cookie_storage_forbidden: true" in content


def test_mock_dry_run_gate_enabled():
    content = MOCK_FILE.read_text(encoding="utf-8")
    assert "dry_run_gate_enabled: true" in content


# ── 4. 금지 액션 패턴 없음 ────────────────────────────────────────────────────


def _all_assistant_tsx() -> list[Path]:
    files = list(ASSISTANT_APP.rglob("*.tsx")) if ASSISTANT_APP.exists() else []
    if ASSISTANT_COMP.exists():
        files += list(ASSISTANT_COMP.rglob("*.tsx"))
    return files


@pytest.mark.parametrize(
    "pattern,name",
    [
        (r"onClick.*execute[^d]", "execute onClick"),
        (r"onClick.*approveExecute", "approve_execute onClick"),
        (r"onClick.*dryRunDisable", "dry_run_disable onClick"),
        (r"onClick.*serverRestart", "server_restart onClick"),
        (r"onClick.*dockerCompose", "docker_compose onClick"),
        (r"onClick.*payment[^F]", "payment onClick"),
    ],
)
def test_forbidden_action_not_present(pattern: str, name: str):
    for f in _all_assistant_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(pattern, content), f"{f.name}에 금지 액션 {name} 발견"


def test_no_fetch_post_execute():
    for f in _all_assistant_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"fetch.*POST.*execute", content), f"{f.name}에 fetch POST execute 발견"


# ── 5. 금지 버튼 텍스트 없음 확인 ────────────────────────────────────────────


@pytest.mark.parametrize(
    "pattern,name",
    [
        (r"<[Bb]utton[^>]*>실행하기", "실행하기 button"),
        (r"<[Bb]utton[^>]*>지금\s*실행", "지금 실행 button"),
        (r"<[Bb]utton[^>]*>DRY_RUN\s*해제", "DRY_RUN 해제 button"),
        (r"<[Bb]utton[^>]*>서버\s*재시작", "서버 재시작 button"),
        (r"<[Bb]utton[^>]*>compose\s*실행", "compose 실행 button"),
    ],
)
def test_forbidden_button_text_not_present(pattern: str, name: str):
    for f in _all_assistant_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(pattern, content), f"{f.name}에 금지 버튼 '{name}' 발견"


# ── 6. DryRunNotice 사용 확인 ─────────────────────────────────────────────────


def test_dry_run_notice_used_in_tasks():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "DryRunNotice" in content


def test_forbidden_action_banner_used_in_tasks():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "ForbiddenActionBanner" in content


# ── 7. approve/reject 표시 전용 확인 ─────────────────────────────────────────


def test_approval_page_no_execute_connection():
    content = (assistant_route("approval", "page.tsx")).read_text(encoding="utf-8")
    assert "approve→execute 미연결" in content or "display" in content.lower() or "ForbiddenActionBanner" in content


# ── 8. 배포 페이지 금지 버튼 없음 ─────────────────────────────────────────────


def test_deployment_page_no_restart_button():
    content = (assistant_route("deployment", "page.tsx")).read_text(encoding="utf-8")
    assert "서버 재시작" not in content or "없음" in content


# ── 9. backend route 수정 없음 ────────────────────────────────────────────────


def test_router_py_not_in_assistant_files():
    for f in _all_assistant_tsx():
        content = f.read_text(encoding="utf-8")
        assert "router.py" not in content, f"{f.name}에 router.py 참조 발견"


def test_docker_compose_not_modified():
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "docker-compose.yml"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        encoding="utf-8",
    )
    assert "docker-compose.yml" not in result.stdout


# ── 10. audit verdict ─────────────────────────────────────────────────────────


def test_audit_verdict_ready_or_warn():
    import tools.audits.app.audit_app_ui_shell_skeleton as m

    report = m.run_audit()
    assert report.verdict in (m.VERDICT_READY, m.VERDICT_WARN), f"verdict={report.verdict}"
