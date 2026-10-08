from scripts.browser.session.browser_cdp_selection_gate import CdpPage, CdpSession
from scripts.naver.mail import background_runner as br


def _session(port, urls):
    return CdpSession(
        host="127.0.0.1",
        port=port,
        pages=[CdpPage(url=url, title=url) for url in urls],
    )


def test_create_isolated_mail_target_uses_common_tab_gate(monkeypatch):
    calls = []
    waits = []

    class FakeIsolationReport:
        ok = True
        target_id = "mail-target"
        page = {"id": "mail-target", "url": "https://mail.naver.com/", "title": "Naver Mail"}

    def fake_create_isolated_target(**kwargs):
        calls.append(kwargs)
        return FakeIsolationReport()

    monkeypatch.setattr(br, "create_isolated_target", fake_create_isolated_target)
    monkeypatch.setattr(
        br.cdp,
        "wait_dom",
        lambda target_id, expr, *, timeout, port: waits.append((target_id, expr, timeout, port)) or True,
    )

    target_id, page = br.create_isolated_mail_target(port=9222)

    assert target_id == "mail-target"
    assert page["title"] == "Naver Mail"
    assert calls == [
        {
            "task": "naver",
            "work": "mail:background",
            "port": 9222,
            "start_url": "https://mail.naver.com/",
        }
    ]
    assert waits[0][0] == "mail-target"


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
