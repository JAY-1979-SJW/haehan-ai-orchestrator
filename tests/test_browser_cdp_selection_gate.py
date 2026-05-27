from scripts import browser_cdp_selection_gate as gate


def _session(port: int, *urls: str) -> gate.CdpSession:
    return gate.CdpSession(
        host="127.0.0.1",
        port=port,
        pages=[gate.CdpPage(url=url, title=url) for url in urls],
    )


def test_selects_naver_session_by_open_tab_domain():
    report = gate.evaluate_sessions(
        "naver",
        [
            _session(9222, "https://www.youtube.com/"),
            _session(9223, "https://www.naver.com/"),
        ],
    )

    assert report.ok is True
    assert report.code == gate.CODE_OK
    assert report.selected_port == 9223


def test_selects_youtube_session_by_open_tab_domain():
    report = gate.evaluate_sessions(
        "youtube",
        [
            _session(9222, "https://www.naver.com/"),
            _session(9224, "https://www.youtube.com/watch?v=1"),
        ],
    )

    assert report.ok is True
    assert report.selected_port == 9224


def test_youtube_blocks_session_mixed_with_naver():
    report = gate.evaluate_sessions(
        "youtube",
        [
            _session(
                9222,
                "https://www.youtube.com/",
                "https://mail.naver.com/",
            )
        ],
    )

    assert report.ok is False
    assert report.code == gate.CODE_MIXED_DOMAIN_SESSION


def test_naver_blocks_session_mixed_with_youtube_or_google():
    report = gate.evaluate_sessions(
        "naver",
        [
            _session(
                9222,
                "https://www.naver.com/",
                "https://accounts.google.com/",
            )
        ],
    )

    assert report.ok is False
    assert report.code == gate.CODE_MIXED_DOMAIN_SESSION


def test_smartstore_is_separate_domain_group_from_naver():
    report = gate.evaluate_sessions(
        "smartstore",
        [
            _session(9222, "https://www.naver.com/"),
            _session(9225, "https://sell.smartstore.naver.com/#/home/dashboard"),
        ],
    )

    assert report.ok is True
    assert report.selected_port == 9225
    assert gate.session_domain_groups(_session(9225, "https://sell.smartstore.naver.com/#/home/dashboard")) == {
        "smartstore"
    }


def test_smartstore_login_redirect_is_smartstore_domain_group():
    login_url = (
        "https://accounts.commerce.naver.com/login?"
        "url=https%3A%2F%2Fsell.smartstore.naver.com%2F%23%2Fproducts%2Fstandard-group-product%2Fcreate"
    )

    report = gate.evaluate_sessions(
        "smartstore",
        [
            _session(9222, "https://www.naver.com/"),
            _session(9232, login_url),
        ],
    )

    assert report.ok is True
    assert report.selected_port == 9232
    assert gate.session_domain_groups(_session(9232, login_url)) == {"smartstore"}


def test_smartstore_blocks_session_mixed_with_naver():
    report = gate.evaluate_sessions(
        "smartstore",
        [
            _session(
                9222,
                "https://sell.smartstore.naver.com/#/home/dashboard",
                "https://mail.naver.com/",
            )
        ],
    )

    assert report.ok is False
    assert report.code == gate.CODE_MIXED_DOMAIN_SESSION


def test_smartstore_prefers_clean_session_over_mixed_session():
    report = gate.evaluate_sessions(
        "smartstore",
        [
            _session(
                9222,
                "https://sell.smartstore.naver.com/#/home/dashboard",
                "https://mail.naver.com/",
            ),
            _session(9231, "https://sell.smartstore.naver.com/#/home/dashboard"),
        ],
    )

    assert report.ok is True
    assert report.selected_port == 9231


def test_no_matching_domain_session_reports_not_found():
    report = gate.evaluate_sessions(
        "naver",
        [_session(9222, "https://example.com/")],
    )

    assert report.ok is False
    assert report.code == gate.CODE_NO_DOMAIN_SESSION


def test_multiple_same_domain_sessions_are_ambiguous():
    report = gate.evaluate_sessions(
        "naver",
        [
            _session(9222, "https://www.naver.com/"),
            _session(9223, "https://mail.naver.com/"),
        ],
    )

    assert report.ok is False
    assert report.code == gate.CODE_AMBIGUOUS_DOMAIN_SESSION


def test_parse_port_ranges():
    assert gate._parse_ports("9222,9224-9226") == [9222, 9224, 9225, 9226]


def test_create_isolated_target_uses_existing_cdp_browser(monkeypatch):
    calls = []

    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda host, port, timeout=2.0: "ws://browser")
    monkeypatch.setattr(
        gate,
        "_send_browser_cdp",
        lambda browser_ws_url, method, params, *, timeout=5.0: calls.append((browser_ws_url, method, params, timeout))
        or {"result": {"targetId": "target-1"}},
    )
    monkeypatch.setattr(
        gate,
        "_read_cdp_page_dicts",
        lambda host, port, timeout=2.0: [
            {"id": "target-1", "url": "https://cafe.naver.com/royaltyserver", "title": "AI cafe", "type": "page"}
        ],
    )

    report = gate.create_isolated_target(
        task="naver",
        work="cafe:boards",
        port=9222,
        start_url="https://cafe.naver.com/royaltyserver",
    )

    assert report.ok is True
    assert report.target_id == "target-1"
    assert report.page["title"] == "AI cafe"
    assert calls == [
        (
            "ws://browser",
            "Target.createTarget",
            {"url": "https://cafe.naver.com/royaltyserver"},
            5.0,
        )
    ]
    assert "no browser launch" in report.messages[0]


def test_create_isolated_target_reports_create_failure(monkeypatch):
    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda host, port, timeout=2.0: "ws://browser")
    monkeypatch.setattr(gate, "_send_browser_cdp", lambda *a, **k: {"result": {}})

    report = gate.create_isolated_target(
        task="google",
        work="ads",
        port=9222,
        start_url="https://ads.google.com/",
    )

    assert report.ok is False
    assert report.code == gate.CODE_TARGET_CREATE_FAILED
