from scripts.browser.session import browser_cdp_selection_gate as gate


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


def test_naver_blocks_session_with_internal_profile_url_tab():
    report = gate.evaluate_sessions(
        "naver",
        [
            _session(
                9232,
                "https://www.naver.com/",
                "http://haehan-ai-orchestrator/data/browser_sessions/naver_parallel",
            )
        ],
    )

    assert report.ok is False
    assert report.code == gate.CODE_INFRASTRUCTURE_URL_TAB
    assert report.sessions[0]["infrastructure_urls"] == [
        "http://haehan-ai-orchestrator/data/browser_sessions/naver_parallel"
    ]


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


def test_smartstore_allows_parallel_naver_tab_when_task_tabs_are_not_duplicated():
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

    assert report.ok is True
    assert report.code == gate.CODE_OK
    assert report.selected_port == 9222


def test_naver_allows_parallel_smartstore_tab_when_task_tabs_are_not_duplicated():
    report = gate.evaluate_sessions(
        "naver",
        [
            _session(
                9222,
                "https://www.naver.com/",
                "https://sell.smartstore.naver.com/#/products/create",
            )
        ],
    )

    assert report.ok is True
    assert report.code == gate.CODE_OK
    assert report.selected_port == 9222


def test_smartstore_blocks_duplicate_task_domain_tabs():
    report = gate.evaluate_sessions(
        "smartstore",
        [
            _session(
                9232,
                "https://sell.smartstore.naver.com/#/products/create",
                "https://accounts.commerce.naver.com/login?url=https%3A%2F%2Fsell.smartstore.naver.com%2F",
            )
        ],
    )

    assert report.ok is False
    assert report.code == gate.CODE_TAB_LIMIT_EXCEEDED
    assert "too many task-domain tabs" in report.messages[0]


def test_naver_task_tab_count_does_not_count_smartstore_subdomains():
    session = _session(
        9232,
        "https://www.naver.com/",
        "https://sell.smartstore.naver.com/#/products/create",
        "https://accounts.commerce.naver.com/login",
    )

    assert gate._task_page_count("naver", session.pages) == 1
    assert gate._task_page_count("smartstore", session.pages) == 2


def test_smartstore_requires_explicit_choice_when_multiple_parallel_sessions_match():
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

    assert report.ok is False
    assert report.code == gate.CODE_AMBIGUOUS_DOMAIN_SESSION


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
    read_calls = []

    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda host, port, timeout=2.0: "ws://browser")
    monkeypatch.setattr(
        gate,
        "_send_browser_cdp",
        lambda browser_ws_url, method, params, *, timeout=5.0: calls.append((browser_ws_url, method, params, timeout))
        or {"result": {"targetId": "target-1"}},
    )
    def fake_read_pages(host, port, timeout=2.0):
        read_calls.append((host, port, timeout))
        if len(read_calls) == 1:
            return []
        return [{"id": "target-1", "url": "https://cafe.naver.com/royaltyserver", "title": "AI cafe", "type": "page"}]

    monkeypatch.setattr(gate, "_read_cdp_page_dicts", fake_read_pages)

    report = gate.create_isolated_target(
        task="naver",
        work="cafe:boards",
        port=9222,
        start_url="https://cafe.naver.com/royaltyserver",
        allow_create=True,
    )

    assert report.ok is True
    assert report.target_id == "target-1"
    assert report.page["title"] == "AI cafe"
    assert report.tab_limit == 1
    assert report.existing_task_tabs == 0
    assert calls == [
        (
            "ws://browser",
            "Target.createTarget",
            {"url": "https://cafe.naver.com/royaltyserver"},
            5.0,
        )
    ]
    assert "no browser launch" in report.messages[0]


def test_create_isolated_target_blocks_when_task_tab_limit_reached(monkeypatch):
    monkeypatch.setattr(
        gate,
        "_read_cdp_page_dicts",
        lambda host, port, timeout=2.0: [
            {"id": "existing-1", "url": "https://mail.naver.com/", "title": "Naver Mail", "type": "page"}
        ],
    )
    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda *a, **k: "should-not-be-called")

    report = gate.create_isolated_target(
        task="naver",
        work="mail:read",
        port=9222,
        start_url="https://mail.naver.com/",
    )

    assert report.ok is False
    assert report.code == gate.CODE_TAB_LIMIT_EXCEEDED
    assert report.tab_limit == 1
    assert report.existing_task_tabs == 1
    assert "Reuse the existing tab" in report.messages[0]


def test_create_isolated_target_can_use_explicit_task_tab_limit(monkeypatch):
    calls = []
    read_calls = []

    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda host, port, timeout=2.0: "ws://browser")
    monkeypatch.setattr(
        gate,
        "_send_browser_cdp",
        lambda browser_ws_url, method, params, *, timeout=5.0: calls.append((browser_ws_url, method, params, timeout))
        or {"result": {"targetId": "target-2"}},
    )

    def fake_read_pages(host, port, timeout=2.0):
        read_calls.append((host, port, timeout))
        if len(read_calls) == 1:
            return [{"id": "existing-1", "url": "https://mail.naver.com/", "title": "Naver Mail", "type": "page"}]
        return [{"id": "target-2", "url": "https://cafe.naver.com/", "title": "Naver Cafe", "type": "page"}]

    monkeypatch.setattr(gate, "_read_cdp_page_dicts", fake_read_pages)

    report = gate.create_isolated_target(
        task="naver",
        work="cafe:read",
        port=9222,
        start_url="https://cafe.naver.com/",
        max_task_tabs=2,
        allow_create=True,
    )

    assert report.ok is True
    assert report.tab_limit == 2
    assert report.existing_task_tabs == 1
    assert calls


def test_create_isolated_target_blocks_when_total_tab_limit_reached(monkeypatch):
    monkeypatch.setattr(
        gate,
        "_read_cdp_page_dicts",
        lambda host, port, timeout=2.0: [
            {"id": "a", "url": "https://www.naver.com/", "title": "Naver", "type": "page"},
            {"id": "b", "url": "https://www.google.com/", "title": "Google", "type": "page"},
        ],
    )
    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda *a, **k: "should-not-be-called")

    report = gate.create_isolated_target(
        task="youtube",
        work="research",
        port=9222,
        start_url="https://www.youtube.com/",
        max_total_tabs=2,
    )

    assert report.ok is False
    assert report.code == gate.CODE_TAB_LIMIT_EXCEEDED
    assert report.existing_total_tabs == 2
    assert "clean up surplus tabs" in report.messages[0]


def test_create_isolated_target_reports_create_failure(monkeypatch):
    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda host, port, timeout=2.0: "ws://browser")
    monkeypatch.setattr(gate, "_send_browser_cdp", lambda *a, **k: {"result": {}})
    monkeypatch.setattr(gate, "_read_cdp_page_dicts", lambda host, port, timeout=2.0: [])

    report = gate.create_isolated_target(
        task="google",
        work="ads",
        port=9222,
        start_url="https://ads.google.com/",
        allow_create=True,
    )

    assert report.ok is False
    assert report.code == gate.CODE_TARGET_CREATE_FAILED


def test_create_isolated_target_blocks_target_creation_by_default(monkeypatch):
    monkeypatch.setattr(gate, "_read_cdp_page_dicts", lambda host, port, timeout=2.0: [])
    monkeypatch.setattr(gate, "_read_browser_ws_url", lambda *a, **k: "should-not-be-called")

    report = gate.create_isolated_target(
        task="youtube",
        work="research",
        port=9222,
        start_url="https://www.youtube.com/",
    )

    assert report.ok is False
    assert report.code == gate.CODE_TARGET_CREATE_BLOCKED
    assert "blocked by default" in report.messages[0]
