"""APP_UI_SHELL_BROWSER_SMOKE_01 테스트.

정적 TSX 분석 기반 smoke 검증:
- 8개 route 존재/heading
- 금지 버튼/액션/mutation 없음
- mock secret 없음 / provider 12개
- DryRunNotice, ForbiddenActionBanner 사용 확인
- audit verdict PASS 또는 WARN
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


# ── 1. route 존재 ──────────────────────────────────────────────────────────────

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
def test_route_exists(route: str):
    assert (assistant_route(*route.split("/"))).exists(), f"/assistant/{route} 없음"


# ── 2. heading 마커 ────────────────────────────────────────────────────────────

HEADING_MARKERS = {
    "page.tsx": ["어시스턴트", "대시보드", "Dashboard", "Assistant"],
    "tasks/page.tsx": ["태스크", "Task"],
    "tasks/[id]/page.tsx": ["상세", "Detail", "태스크"],
    "approval/page.tsx": ["승인", "Approval"],
    "external-sites/page.tsx": ["외부", "External", "사이트"],
    "logs/page.tsx": ["로그", "Log", "감사"],
    "storage/page.tsx": ["스토리지", "Storage"],
    "deployment/page.tsx": ["배포", "Deploy"],
}


@pytest.mark.parametrize("route,markers", list(HEADING_MARKERS.items()))
def test_heading_marker(route: str, markers: list):
    path = assistant_route(*route.split("/"))
    if not path.exists():
        pytest.skip(f"{route} 없음")
    content = path.read_text(encoding="utf-8")
    assert any(m in content for m in markers), f"{route}: heading 마커 {markers} 없음"


# ── 3. 금지 액션 패턴 없음 ────────────────────────────────────────────────────

def _all_tsx() -> list[Path]:
    files = list(ASSISTANT_APP.rglob("*.tsx")) if ASSISTANT_APP.exists() else []
    if ASSISTANT_COMP.exists():
        files += list(ASSISTANT_COMP.rglob("*.tsx"))
    return files


@pytest.mark.parametrize("pattern,name", [
    (r"onClick.*execute[^d]", "execute onClick"),
    (r"onClick.*approveExecute", "approve_execute onClick"),
    (r"onClick.*dryRunDisable", "dry_run_disable onClick"),
    (r"onClick.*serverRestart", "server_restart onClick"),
    (r"onClick.*dockerCompose", "docker_compose onClick"),
    (r"onClick.*payment[^F]", "payment onClick"),
])
def test_forbidden_action_not_present(pattern: str, name: str):
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(pattern, content), f"{f.name}에 금지 액션 {name} 발견"


# ── 4. 금지 버튼 텍스트 없음 ─────────────────────────────────────────────────

@pytest.mark.parametrize("pattern,name", [
    (r"<[Bb]utton[^>]*>실행하기", "실행하기 button"),
    (r"<[Bb]utton[^>]*>지금\s*실행", "지금 실행 button"),
    (r"<[Bb]utton[^>]*>DRY_RUN\s*해제", "DRY_RUN 해제 button"),
    (r"<[Bb]utton[^>]*>서버\s*재시작", "서버 재시작 button"),
    (r"<[Bb]utton[^>]*>compose\s*실행", "compose 실행 button"),
])
def test_forbidden_button_text_not_present(pattern: str, name: str):
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(pattern, content), f"{f.name}에 금지 버튼 '{name}' 발견"


# ── 5. mutation 없음 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("pattern,name", [
    (r'fetch\s*\([^,)]+,\s*\{[^}]*method\s*:\s*[\'"]POST[\'"]', "fetch POST"),
    (r'fetch\s*\([^,)]+,\s*\{[^}]*method\s*:\s*[\'"]PUT[\'"]', "fetch PUT"),
    (r'fetch\s*\([^,)]+,\s*\{[^}]*method\s*:\s*[\'"]DELETE[\'"]', "fetch DELETE"),
])
def test_no_mutation_fetch(pattern: str, name: str):
    # 현행: (legacy)/cafe/tabs/AiAnalysisTab.tsx 의 카페 AI 분석 호출(POST /naver-cafe/ai-analyze)이 유일한 알려진 쓰기 fetch 다.
    # 그 한 파일·POST 만 허용하고, 그 외 파일의 POST 및 모든 PUT/DELETE 는 계속 금지한다.
    known = {"AiAnalysisTab.tsx"} if name == "fetch POST" else set()
    found = set()
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        if re.search(pattern, content):
            found.add(f.name)
    assert found == known, f"{name} mutation 파일 목록 변경: 현재={sorted(found)} 허용={sorted(known)}"


# ── 6. mock secret 없음 ───────────────────────────────────────────────────────

def test_mock_no_token():
    assert not re.search(r'"token"\s*:\s*"[A-Za-z0-9+/=]{20,}"', MOCK_FILE.read_text(encoding="utf-8"))


def test_mock_no_cookie():
    assert not re.search(r'"cookie"\s*:\s*"[A-Za-z0-9;=]{10,}"', MOCK_FILE.read_text(encoding="utf-8"))


def test_mock_no_password():
    assert not re.search(r'"password"\s*:\s*"[^"]{3,}"', MOCK_FILE.read_text(encoding="utf-8"))


def test_mock_no_secret():
    assert not re.search(r'"secret"\s*:\s*"[^"]{3,}"', MOCK_FILE.read_text(encoding="utf-8"))


# ── 7. provider 12개 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("provider", [
    "GABIA", "KAKAO", "NAVER", "NAVER_SMARTSTORE", "GOOGLE", "HIWORKS",
    "G2B_NARA", "HOMETAX", "WETAX", "GOVERNMENT24", "EMAIL_GENERIC", "BANK_GENERIC",
])
def test_mock_provider_present(provider: str):
    content = MOCK_FILE.read_text(encoding="utf-8")
    assert provider in content, f"mock에 provider {provider} 없음"


# ── 8. DryRunNotice / ForbiddenActionBanner ────────────────────────────────

def test_dry_run_notice_in_tasks():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "DryRunNotice" in content


def test_forbidden_banner_in_tasks():
    content = (assistant_route("tasks", "page.tsx")).read_text(encoding="utf-8")
    assert "ForbiddenActionBanner" in content


# ── 9. approval no execute ────────────────────────────────────────────────────

def test_approval_no_execute_connection():
    content = (assistant_route("approval", "page.tsx")).read_text(encoding="utf-8")
    ok = ("approve→execute 미연결" in content
          or "display" in content.lower()
          or "ForbiddenActionBanner" in content)
    assert ok


# ── 10. deployment no restart button ─────────────────────────────────────────

def test_deployment_no_restart_button():
    content = (assistant_route("deployment", "page.tsx")).read_text(encoding="utf-8")
    assert not re.search(r"<[Bb]utton[^>]*>서버\s*재시작", content)


# ── 11. fetch POST execute 없음 ───────────────────────────────────────────────

def test_no_fetch_post_execute():
    for f in _all_tsx():
        content = f.read_text(encoding="utf-8")
        assert not re.search(r"fetch.*POST.*execute", content), f"{f.name}에 fetch POST execute 발견"


# ── 12. audit verdict ─────────────────────────────────────────────────────────

def test_audit_verdict_pass_or_warn():
    import tools.audits.app.audit_app_ui_shell_browser_smoke as m
    report = m.run_audit()
    assert report.verdict in (m.VERDICT_PASS, m.VERDICT_WARN), f"verdict={report.verdict}"
