from __future__ import annotations

from scripts.browser.cdp.cdp_session_selector import CdpCandidate, configured_ports, select_cdp_session


def _candidate(port: int, urls: list[str]) -> CdpCandidate:
    return CdpCandidate(port=port, available=True, tabs=[{"url": url, "title": "", "type": "page"} for url in urls])


def test_configured_ports_uses_valid_unique_values():
    assert configured_ports("9222, 9222, bad, 9333") == [9222, 9333]


def test_selects_existing_youtube_session_before_clean_session():
    result = select_cdp_session(
        target_domains=["youtube.com"],
        avoid_domains=["naver.com"],
        candidates=[
            _candidate(9222, []),
            _candidate(9333, ["https://www.youtube.com/watch?v=abc"]),
        ],
    )

    assert result["ok"] is True
    assert result["selected_cdp_port"] == 9333
    assert result["selected_reason"] == "existing_target_domain_tab"
    assert result["cross_work_conflict"] is False


def test_avoids_naver_session_for_youtube_work():
    result = select_cdp_session(
        target_domains=["youtube.com"],
        avoid_domains=["naver.com"],
        candidates=[
            _candidate(9222, ["https://mail.naver.com/"]),
            _candidate(9333, []),
        ],
    )

    assert result["ok"] is True
    assert result["selected_cdp_port"] == 9333
    assert result["selected_reason"] == "clean_available_session"
    assert result["detected_tabs"][0]["avoid_tab_count"] == 1


def test_blocks_mixed_youtube_and_naver_session_when_no_clean_option():
    result = select_cdp_session(
        target_domains=["youtube.com"],
        avoid_domains=["naver.com"],
        candidates=[
            _candidate(9222, ["https://www.youtube.com/watch?v=abc", "https://mail.naver.com/"]),
        ],
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["cross_work_conflict"] is True
    assert result["selected_cdp_port"] == 0
