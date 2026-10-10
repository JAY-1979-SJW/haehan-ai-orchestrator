from scripts.browser.cdp import cdp_daemon


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_probe_live_cdp_reports_responding(monkeypatch):
    def fake_urlopen(url, timeout):
        assert "/json/version" in url
        assert timeout == 2
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    ok, detail = cdp_daemon._probe_live_cdp(9222)

    assert ok is True
    assert detail == "responding"


def test_cmd_start_does_not_claim_daemon_when_only_live_cdp(monkeypatch, capsys):
    monkeypatch.setattr(cdp_daemon, "_probe_live_cdp", lambda port: (True, "responding"))
    monkeypatch.setattr(cdp_daemon, "_load_state", lambda: cdp_daemon.DaemonState(running=False))

    cdp_daemon.cmd_start()

    out = capsys.readouterr().out
    assert "Live CDP endpoint is responding but daemon state is inactive" in out
    assert "daemon-managed endpoint" not in out
