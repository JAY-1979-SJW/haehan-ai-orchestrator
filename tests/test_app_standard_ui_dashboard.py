from pathlib import Path

PAGE = Path("admin-web/src/app/page.tsx")
NAV = Path("admin-web/src/lib/nav.ts")

# 현행 정본: 홈 = 단일 AI 작업 콘솔(855d595a), 사이드바 정본은 lib/nav.ts NAV_GROUPS.


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_home_dashboard_uses_standard_ui_shell():
    src = _src()

    # 구 AppShell/Sidebar/Header/MetricCard/DataTable/ReportList 대시보드는 단일 콘솔로 대체됨
    assert "PageShell" in src
    assert "UniversalChat" in src
    assert 'data-testid="ai-agent-console"' in src
    for removed in ("AppShell", "MetricCard", "DataTable", "ReportList"):
        assert removed not in src


def test_home_dashboard_defines_required_navigation():
    nav = NAV.read_text(encoding="utf-8")

    for label in (
        "AI 콘솔",
        "운영센터",
        "메일 비서",
        "메일함",
        "하나팩스",
        "건설업 공무",
        "사이트 업무 지도",
        "구글 허브",
        "로그인 현황",
        "설정",
        "스토어 AI 채팅",
        "블로그 AI",
        "작업 목록",
        "승인 게이트",
        "예약 작업",
    ):
        assert label in nav
    assert '{ key: "home", label: "AI 콘솔"' in nav


def test_home_dashboard_is_server_first_static_dry_run():
    src = _src()

    # 정적 dry-run 계약 화면 문구는 제거됨 -> 서버(로그인 사용자) 기준 콘솔로 전환
    assert "static/dry-run 화면" not in src
    assert "서버 API 연결 전까지 정적 계약 화면" not in src
    assert "getMe()" in src
    assert 'router.replace("/about")' in src
    assert "실제 작업은 브라우저(CDP)에서 수행됩니다" in src


def test_home_dashboard_prioritizes_user_next_action():
    src = _src()

    # 승인 대기 우선 카드 대신 AI 콘솔 입력이 다음 행동의 단일 진입점
    assert "AI에게 작업을 요청하세요" in src
    assert 'title="Haehan AI 콘솔"' in src
    assert "승인 대기 우선" not in src
    assert "지금 처리할 일을 한 화면에서 확인합니다" not in src


def test_home_dashboard_has_consent_and_agent_sections():
    src = _src()

    # 동의/에이전트 연결 섹션은 홈에서 제거됨(부정 단언) - 대화형 콘솔만 유지
    assert 'UniversalChat domain="default" title="AI 작업 콘솔"' in src
    for removed in ("에이전트 연결", "동의 상태", "언제든 철회", "원문 프롬프트"):
        assert removed not in src


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
