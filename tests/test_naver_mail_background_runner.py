from scripts.browser_cdp_selection_gate import CdpPage, CdpSession
from scripts.naver_mail import background_runner as br


def _session(port, urls):
    return CdpSession(
        host="127.0.0.1",
        port=port,
        pages=[CdpPage(url=url, title=url) for url in urls],
    )


def test_background_runner_strict_mode_rejects_mixed_naver_google_session():
    sessions = [_session(9222, ["https://mail.naver.com/", "https://accounts.google.com/"])]
    session, selection = br.select_naver_session(sessions=sessions, allow_mixed_readonly=False)
    assert session is None
    assert selection.code == "mixed_domain_session"


def test_background_runner_readonly_mode_can_select_mixed_naver_session():
    sessions = [_session(9222, ["https://mail.naver.com/", "https://accounts.google.com/"])]
    session, selection = br.select_naver_session(sessions=sessions, allow_mixed_readonly=True)
    assert session is not None
    assert session.port == 9222
    assert selection.code == "mixed_domain_session"


def test_background_report_serializes_policy_evidence():
    report = br.BackgroundReport(
        ok=True,
        code="ok",
        port=9222,
        mail_count=3,
        folder_kind_counts={"inbox": 1, "smart": 2},
        settings_menus=[{"name": "환경설정", "action": "inspect"}],
    )
    data = report.to_dict()
    assert data["ok"] is True
    assert data["folder_kind_counts"]["smart"] == 2
    assert data["settings_menus"][0]["name"] == "환경설정"
