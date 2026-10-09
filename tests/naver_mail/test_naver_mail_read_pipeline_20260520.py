"""Naver mail_read 패키지 — 순수 함수 단위 테스트."""
from __future__ import annotations

import pytest

from scripts.naver.mail.read import body_reader as br
from scripts.naver.mail.read import classify as cls_mod
from scripts.naver.mail.read import list_collector as lc

# ── PII 마스킹 ───────────────────────────────────────────────────────


def test_redact_card_number():
    out = br.redact("카드 1234 5678 9012 3456 사용")
    assert "1234-****-****-3456" in out
    assert "5678" not in out
    assert "9012" not in out


def test_redact_long_number_continuous():
    out = br.redact("계좌 12345678901234 입금")
    assert "[NUMBER_MASKED]" in out
    assert "12345678" not in out


def test_redact_phone_number():
    out = br.redact("연락 010-1234-5678 로 주세요")
    assert "010-****-****" in out
    assert "1234-5678" not in out


def test_redact_rrn():
    out = br.redact("123456-1234567 본인확인")
    assert "[RRN_MASKED]" in out


def test_redact_email_localpart():
    out = br.redact("user@example.com 으로 발송")
    assert "us***@example.com" in out
    assert "user@example.com" not in out


def test_redact_short_email_local():
    out = br.redact("ab@x.com")
    assert "**@x.com" in out


def test_redact_otp_code():
    out = br.redact("인증번호 123456 입력")
    assert "[CODE_MASKED]" in out
    assert "123456" not in out


def test_redact_empty_safe():
    assert br.redact("") == ""
    assert br.redact(None) == ""  # type: ignore


# ── 링크 / 피싱 ─────────────────────────────────────────────────────


def test_link_domain_extracts_host():
    assert br.link_domain("https://www.coupang.com/x/y") == "www.coupang.com"
    assert br.link_domain("http://example.org") == "example.org"


def test_is_trusted_naver_subdomain():
    assert br.is_trusted("section.blog.naver.com") is True
    assert br.is_trusted("smartstore.naver.com") is True


def test_is_trusted_unknown_domain():
    assert br.is_trusted("unknown-tracker.example") is False


def test_is_phishing_suspect_suspicious_tld():
    assert br.is_phishing_suspect("http://win-prize.tk/x") is True
    assert br.is_phishing_suspect("http://shop.xyz/y") is True


def test_is_phishing_suspect_trusted_not_flagged():
    assert br.is_phishing_suspect("https://www.coupang.com/x") is False


# ── parse_body_payload ──────────────────────────────────────────────


def test_parse_body_payload_basic():
    payload = {
        "href": "https://mail.naver.com/v2/popup/read/0/123",
        "header": {"subject": "S", "sender_name": "N",
                   "sender_addr": "user@example.com", "date": "D"},
        "body": "본문 0000-0000-0000-1234 010-1234-5678",
        "body_len": 50,
        "links": ["https://www.coupang.com/a", "https://win-prize.tk/x",
                  "https://search.google.com/q"],
        "img_count": 2, "has_attach": True, "attach_names": ["a.docx"],
    }
    mb = br.parse_body_payload("123", payload)
    assert mb.sn == "123"
    assert mb.subject == "S"
    assert "us***@example.com" in mb.sender_addr_redacted
    assert "0000-****-****-1234" in mb.body_redacted
    assert "010-****-****" in mb.body_redacted
    assert "www.coupang.com" in mb.link_domains
    assert "win-prize.tk" in mb.link_domains
    assert any("win-prize.tk" in u for u in mb.phishing_links)
    assert mb.has_attach is True
    assert mb.attach_names == ["a.docx"]


def test_parse_body_payload_empty_safe():
    mb = br.parse_body_payload("0", {})
    assert mb.sn == "0"
    assert mb.body_redacted == ""
    assert mb.link_domains == {}


# ── 분류 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sender,subject,expected_label", [
    ("Support <sp_improve@coupang.com>",
     "[쿠팡] 고객센터 문의 답변지연으로 인한 전체 상품 노출 정지 안내",
     "ACTION_REQUIRED"),
    ("스마트스토어 센터 <smartstore_noreply@navercorp.com>",
     "스마트스토어 판매자 계정이 휴면 상태로 전환될 예정입니다.",
     "ACTION_REQUIRED"),
    ("Google Search Console Team <sc-noreply@google.com>",
     "haehan-ai.kr 사이트의 페이지에 대한 색인이 생성되지 않습니다",
     "REVIEW"),
    ("네이버 <account_noreply@navercorp.com>",
     "새로운 환경에서 로그인 되었습니다.",
     "INFO"),
    ("KB국민카드 <kbmail@kbmail.kbcard.com>",
     "표준 전자금융거래 기본약관 외 약관 1종 개정 안내",
     "CARD_NOTICE"),
    ("Miricanvas <notice@news.miricanvas.co.kr>",
     "[미리캔버스] 뉴스레터",
     "PROMO"),
    ("randomguy@unknown.org",
     "안녕하세요 그냥 메일",
     "OTHER"),
])
def test_classify_rules(sender, subject, expected_label):
    r = cls_mod.classify(sender, subject)
    assert r.label == expected_label


def test_classify_priority_ordering():
    a = cls_mod.classify("sp_improve@coupang.com", "노출 정지")
    b = cls_mod.classify("kbcard.com", "약관 안내")
    c = cls_mod.classify("unknown@x", "x")
    assert a.priority < b.priority < c.priority


# ── list parser ─────────────────────────────────────────────────────


def test_parse_list_payload_minimal():
    payload = {
        "href": "https://mail.naver.com/v2/folders/0/all",
        "title": "받은메일함(3) : 네이버 메일",
        "count": 2,
        "items": [
            {"sn": "100", "is_unread": True, "sender_name": "A",
             "sender_full": "A<a@x.com>", "subject": "s1",
             "time_txt": "오전 9:00", "size_txt": "1KB", "href": "/v2/popup/read/0/100"},
            {"sn": "101", "is_unread": False, "sender_name": "B",
             "sender_full": "B<b@y.com>", "subject": "s2",
             "time_txt": "오전 8:00", "size_txt": "2KB", "href": "/v2/popup/read/0/101"},
        ],
    }
    items = lc.parse_list_payload(payload)
    assert len(items) == 2
    assert items[0].sn == "100"
    assert items[0].is_unread is True
    assert items[1].is_unread is False


def test_parse_list_payload_empty():
    assert lc.parse_list_payload({}) == []
    assert lc.parse_list_payload({"items": []}) == []


# ── site_entry_policy 통합 ──────────────────────────────────────────


def test_pipeline_forbids_direct_login_url():
    from core.agent_runtime.policy import site_entry_policy as sep
    with pytest.raises(ValueError, match="FORBIDDEN_LOGIN_URL_DIRECT_ENTRY"):
        sep.assert_main_page_first("https://nid.naver.com/nidlogin.login", "naver")


def test_pipeline_accepts_mail_main_url():
    from core.agent_runtime.policy import site_entry_policy as sep
    # mail.naver.com 은 메인 페이지로 간주 (정책상 forbidden URL 아님)
    sep.assert_main_page_first("https://mail.naver.com/", "naver")
