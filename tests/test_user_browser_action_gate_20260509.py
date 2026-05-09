"""user_browser_action_gate 단위 테스트."""
from __future__ import annotations

import pytest

from ai_orchestrator.local_agent.user_browser_action_gate import (
    classify_action, is_auto, is_blocked, requires_approval, should_notify,
    GATE_AUTO, GATE_NOTIFY, GATE_APPROVE, GATE_BLOCKED,
)
from ai_orchestrator.local_agent.user_browser_intent_token import create_intent


def _make_intent(origins=("developer.hancom.com",)):
    return create_intent(natural_language="한컴 SDK 가격 확인", allowed_origins=origins)


# ── BLOCKED ──────────────────────────────────────────────────────────────────

def test_blocked_password_field():
    r = classify_action(action_type="type", params={"password": "s3cret"})
    assert r.verdict == GATE_BLOCKED
    assert is_blocked(r)


def test_blocked_card_number_field():
    r = classify_action(action_type="type", params={"card_number": "1234"})
    assert r.verdict == GATE_BLOCKED


def test_blocked_rrn_field():
    r = classify_action(action_type="type", params={"주민번호": "900101-1234567"})
    assert r.verdict == GATE_BLOCKED


def test_blocked_otp_field():
    r = classify_action(action_type="type", params={"otp": "123456"})
    assert r.verdict == GATE_BLOCKED


def test_blocked_npki_field():
    r = classify_action(action_type="type", params={"npki": "cert_data"})
    assert r.verdict == GATE_BLOCKED


# ── APPROVE — 돈 이동 ────────────────────────────────────────────────────────

def test_approve_payment_label():
    r = classify_action(action_type="click", label="결제하기 버튼", url="https://shop.com")
    assert r.verdict == GATE_APPROVE
    assert r.category == "MONEY"


def test_approve_bid_label():
    r = classify_action(action_type="click", label="투찰 제출", url="https://g2b.go.kr")
    assert r.verdict == GATE_APPROVE


def test_approve_purchase_url():
    r = classify_action(action_type="navigate", label="", url="https://shop.com/purchase")
    assert r.verdict == GATE_APPROVE


def test_approve_transfer_label():
    r = classify_action(action_type="click", label="송금하기")
    assert r.verdict == GATE_APPROVE


# ── APPROVE — 법적 효력 ──────────────────────────────────────────────────────

def test_approve_esign_action_type():
    r = classify_action(action_type="esign", label="전자서명 완료")
    assert r.verdict == GATE_APPROVE


def test_approve_submit_action_type():
    # label에 "제출" 키워드가 있어 LEGAL 카테고리로 분류됨 (keyword 검사가 action_type보다 우선)
    r = classify_action(action_type="submit", label="서류 제출")
    assert r.verdict == GATE_APPROVE
    assert r.category in ("LEGAL", "SUBMIT")


def test_approve_submit_action_type_no_label():
    # "submit" 자체가 LEGAL 키워드로 매칭됨
    r = classify_action(action_type="submit", label="")
    assert r.verdict == GATE_APPROVE
    assert r.category in ("LEGAL", "SUBMIT")


def test_approve_contract_label():
    r = classify_action(action_type="click", label="계약 체결")
    assert r.verdict == GATE_APPROVE


# ── APPROVE — 계정 변경 ──────────────────────────────────────────────────────

def test_approve_withdraw_label():
    r = classify_action(action_type="click", label="회원탈퇴")
    assert r.verdict == GATE_APPROVE


# ── APPROVE — 외부 발송 ──────────────────────────────────────────────────────

def test_approve_send_email_label():
    r = classify_action(action_type="click", label="이메일 발송")
    assert r.verdict == GATE_APPROVE


# ── NOTIFY ───────────────────────────────────────────────────────────────────

def test_notify_no_intent():
    r = classify_action(action_type="navigate", url="https://developer.hancom.com/", intent=None)
    assert r.verdict == GATE_NOTIFY
    assert not r.intent_ok


def test_notify_download_action():
    intent = _make_intent()
    r = classify_action(action_type="download", url="https://developer.hancom.com/sdk.zip",
                        intent=intent)
    assert r.verdict == GATE_NOTIFY


def test_notify_popup_action():
    intent = _make_intent()
    r = classify_action(action_type="popup", intent=intent)
    assert r.verdict == GATE_NOTIFY


def test_notify_origin_out_of_scope():
    intent = _make_intent(origins=("developer.hancom.com",))
    r = classify_action(action_type="navigate", url="https://google.com", intent=intent)
    assert r.verdict == GATE_NOTIFY
    assert not r.origin_allowed


def test_notify_subdomain_not_allowed():
    intent = _make_intent(origins=("developer.hancom.com",))
    r = classify_action(action_type="navigate",
                        url="https://sub.developer.hancom.com/page", intent=intent)
    assert r.verdict == GATE_NOTIFY


# ── AUTO ─────────────────────────────────────────────────────────────────────

def test_auto_navigate_in_scope():
    intent = _make_intent()
    r = classify_action(action_type="navigate",
                        url="https://developer.hancom.com/sdk", intent=intent)
    assert r.verdict == GATE_AUTO
    assert is_auto(r)


def test_auto_click_in_scope():
    intent = _make_intent()
    r = classify_action(action_type="click", label="SDK 다운로드 목록 보기",
                        url="https://developer.hancom.com/list", intent=intent)
    assert r.verdict == GATE_AUTO


def test_auto_screenshot_in_scope():
    intent = _make_intent()
    r = classify_action(action_type="screenshot",
                        url="https://developer.hancom.com/", intent=intent)
    assert r.verdict == GATE_AUTO


def test_auto_type_non_sensitive():
    intent = _make_intent()
    r = classify_action(action_type="type", label="검색어 입력",
                        url="https://developer.hancom.com/search",
                        params={"query": "SDK"}, intent=intent)
    assert r.verdict == GATE_AUTO


def test_auto_scroll_in_scope():
    intent = _make_intent()
    r = classify_action(action_type="scroll",
                        url="https://developer.hancom.com/docs", intent=intent)
    assert r.verdict == GATE_AUTO


# ── helper functions ─────────────────────────────────────────────────────────

def test_requires_approval_helper():
    r = classify_action(action_type="click", label="결제하기")
    assert requires_approval(r)


def test_should_notify_helper():
    r = classify_action(action_type="navigate", url="https://google.com", intent=None)
    assert should_notify(r)


def test_gate_result_to_dict_approve():
    r = classify_action(action_type="click", label="투찰 제출",
                        url="https://g2b.go.kr")
    d = r.to_dict()
    assert d["verdict"] == GATE_APPROVE
    assert "matched_keyword" in d
    assert "category" in d


def test_gate_result_to_dict_blocked():
    r = classify_action(action_type="type", params={"password": "x"})
    d = r.to_dict()
    assert d["verdict"] == GATE_BLOCKED
    assert "blocked_field" in d


def test_gate_result_to_dict_auto_minimal():
    intent = _make_intent()
    r = classify_action(action_type="navigate",
                        url="https://developer.hancom.com/", intent=intent)
    d = r.to_dict()
    assert d["verdict"] == GATE_AUTO
    assert "blocked_field" not in d
    assert "matched_keyword" not in d
