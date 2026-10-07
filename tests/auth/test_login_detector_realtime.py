from pathlib import Path

from scripts.auth import login_detector


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakePage:
    def __init__(self, url, text="logout", pages=None):
        self.url = url
        self.context = FakeContext(pages if pages is not None else [self])
        self._text = text

    def evaluate(self, script):
        if "document.body.innerText" in script:
            return self._text
        return False


def test_unknown_logged_in_domain_uses_host_as_site_key(monkeypatch):
    page = FakePage("https://portal.example.com/home", text="")
    monkeypatch.setattr(
        login_detector,
        "detect_login_state",
        lambda page: {"logged_in": True, "on_login_page": False},
    )

    logged_in, site = login_detector.detect_login_on_current_tab(page)

    assert logged_in is True
    assert site == "portal.example.com"


def test_hiworks_mail_page_is_login_signal():
    page = FakePage("https://mails.office.hiworks.com/list/inbox?page=1", text="받은 메일함\n메일 쓰기")

    logged_in, site = login_detector.detect_login_on_current_tab(page)

    assert logged_in is True
    assert site == "hiworks"


def test_save_detected_login_saves_encrypted_session_and_db(monkeypatch, tmp_path):
    page = FakePage("https://dashboard.office.hiworks.com/")
    calls = {}

    def fake_save_session(host, page):
        calls["host"] = host
        return tmp_path / f"{host}.json"

    monkeypatch.setattr("scripts.auth.auth_session.save_session", fake_save_session)
    monkeypatch.setattr("scripts.common.realtime_audit.emit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(login_detector.cdp_db, "init_db", lambda: calls.setdefault("db_init", True))
    monkeypatch.setattr(
        login_detector.cdp_db,
        "upsert_session",
        lambda **kwargs: calls.setdefault("upsert", kwargs),
    )

    assert login_detector.save_detected_login("hiworks", page) is True

    assert calls["host"] == "office.hiworks.com"
    assert calls["upsert"]["site_name"] == "hiworks"
    assert calls["upsert"]["session_file"] == str(Path(tmp_path / "office.hiworks.com.json"))
    assert calls["upsert"]["login_event"] is True


def test_watch_all_logins_scans_every_open_tab_once(monkeypatch):
    p1 = FakePage("https://mail.google.com/", text="logout")
    p2 = FakePage("https://portal.example.com/", text="logout")
    pages = [p1, p2]
    p1.context = FakeContext(pages)
    p2.context = p1.context
    saved = []

    monkeypatch.setattr(login_detector, "_inject_login_watcher", lambda page: True)
    monkeypatch.setattr(login_detector, "save_detected_login", lambda site, page: saved.append(site) or True)

    result = login_detector.watch_all_logins(p1, check_interval=0, timeout_s=1)

    assert "google" in saved
    assert "portal.example.com" in saved
    assert result["checks"] >= 1
