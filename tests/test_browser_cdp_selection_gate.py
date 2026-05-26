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
