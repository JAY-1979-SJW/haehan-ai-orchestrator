from pathlib import Path


PAGE = Path("admin-web/src/app/page.tsx")


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_home_dashboard_uses_standard_ui_shell():
    src = _src()

    assert "AppShell" in src
    assert "Sidebar" in src
    assert "Header" in src
    assert "MetricCard" in src
    assert "DataTable" in src
    assert "ReportList" in src


def test_home_dashboard_defines_required_navigation():
    src = _src()

    for label in (
        "Dashboard",
        "Tasks",
        "Approvals",
        "Agents",
        "Tools",
        "Connections",
        "Audit",
        "Consent",
        "Reports",
        "Settings",
    ):
        assert label in src


def test_home_dashboard_is_server_first_static_dry_run():
    src = _src()

    assert "서버 기준 운영 앱" in src
    assert "static/dry-run 화면" in src
    assert "서버 API 연결 전까지 정적 계약 화면" in src
    assert "읽기 전용" in src


def test_home_dashboard_prioritizes_user_next_action():
    src = _src()

    assert "지금 처리할 일을 한 화면에서 확인합니다" in src
    assert "승인 대기 우선" in src
    assert "작업 보기" in src
    assert "감사 보기" in src


def test_home_dashboard_has_consent_and_agent_sections():
    src = _src()

    assert "에이전트 연결" in src
    assert "동의 상태" in src
    assert "언제든 철회" in src
    assert "원문 프롬프트" in src


def test_home_dashboard_has_no_direct_runtime_calls_or_sensitive_storage():
    src = _src()

    forbidden = (
        "fetch(",
        "axios.",
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "access_token",
        "refresh_token",
        "Bearer admin-token",
    )
    for pattern in forbidden:
        assert pattern not in src
