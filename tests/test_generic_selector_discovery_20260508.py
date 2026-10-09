"""tests/test_generic_selector_discovery_20260508.py"""

from core.agent_runtime.runtime.universal.generic_selector_discovery import (
    discover_selectors,
    has_risk_buttons,
)


def _obs(buttons=None, visible_actions=None, forms_detected=False, download_links=None):
    return {
        "buttons_observed": buttons or [],
        "visible_actions": visible_actions or [],
        "forms_detected": forms_detected,
        "download_candidates": download_links or [],
    }


def test_password_selector_never_discovered():
    disc = discover_selectors(_obs(buttons=["비밀번호 입력"], forms_detected=True))
    assert disc["password_selector_discovered"] is False


def test_otp_selector_never_discovered():
    disc = discover_selectors(_obs(buttons=["OTP 입력"], forms_detected=True))
    assert disc["otp_selector_discovered"] is False


def test_cert_password_selector_never_discovered():
    disc = discover_selectors(_obs(forms_detected=True))
    assert disc["cert_password_selector_discovered"] is False


def test_npki_selector_never_discovered():
    disc = discover_selectors(_obs(forms_detected=True))
    assert disc["npki_selector_discovered"] is False


def test_search_box_found_with_search_action():
    disc = discover_selectors(_obs(visible_actions=["search"]))
    assert len(disc["search_box"]) > 0


def test_search_box_empty_without_search_action():
    disc = discover_selectors(_obs(visible_actions=[]))
    assert disc["search_box"] == []


def test_list_items_always_present():
    disc = discover_selectors(_obs())
    assert len(disc["list_items"]) > 0


def test_download_links_with_download_action():
    disc = discover_selectors(_obs(visible_actions=["download"]))
    assert len(disc["download_links"]) > 0


def test_publish_button_detected():
    disc = discover_selectors(_obs(visible_actions=["publish"], buttons=["발행"]))
    assert len(disc["publish_button"]) > 0


def test_publish_button_discovery_only_no_execution():
    """publish_button은 발견만, 실행은 권한 gate 이후."""
    disc = discover_selectors(_obs(visible_actions=["publish"]))
    assert "publish_button" in disc
    # discovery 결과가 있더라도 실행 자체는 agent에서 권한 gate 이후 처리


def test_risk_buttons_payment_detected():
    disc = discover_selectors(_obs(buttons=["결제하기", "확인"]))
    assert "payment" in disc["risk_buttons_detected"]


def test_risk_buttons_sign_detected():
    disc = discover_selectors(_obs(buttons=["전자서명", "제출"]))
    assert "sign" in disc["risk_buttons_detected"]


def test_risk_buttons_bid_detected():
    disc = discover_selectors(_obs(buttons=["입찰하기"]))
    assert "bid" in disc["risk_buttons_detected"]


def test_has_risk_buttons():
    disc = discover_selectors(_obs(buttons=["결제"]))
    assert has_risk_buttons(disc) is True

    disc2 = discover_selectors(_obs(buttons=["검색"]))
    assert has_risk_buttons(disc2) is False


def test_form_selectors_only_with_forms():
    disc = discover_selectors(_obs(forms_detected=True))
    assert len(disc["title_input"]) > 0
    assert len(disc["body_editor"]) > 0

    disc2 = discover_selectors(_obs(forms_detected=False))
    assert disc2["title_input"] == []
    assert disc2["body_editor"] == []
