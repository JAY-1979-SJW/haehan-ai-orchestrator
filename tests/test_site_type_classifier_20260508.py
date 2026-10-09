"""tests/test_site_type_classifier_20260508.py"""
from core.agent_runtime.runtime.site_profile.site_type_classifier import (
    SITE_BLOG,
    SITE_CAFE_OR_FORUM,
    SITE_CONTENT_PLATFORM,
    SITE_ECOMMERCE,
    SITE_FINANCIAL,
    SITE_GOVERNMENT,
    SITE_NOTICE_BOARD,
    SITE_UNKNOWN,
    classify_site,
    get_site_type_for_profile,
)


def _obs(host="", title="", text="", page_types=None):
    return {
        "host": host,
        "title": title,
        "text_content": text,
        "page_type_candidates": page_types or [],
    }


def test_g2b_domain_classified_government():
    r = classify_site(_obs(host="www.g2b.go.kr"))
    assert r["site_type"] == SITE_GOVERNMENT
    assert r["confidence"] == "high"
    assert r["is_known_site"] is True


def test_naver_blog_classified():
    r = classify_site(_obs(host="blog.naver.com"))
    # blog.naver.com은 known map에서 BLOG로, 없으면 naver.com subdomain으로 CONTENT_PLATFORM
    assert r["site_type"] in (SITE_BLOG, SITE_CONTENT_PLATFORM)
    assert r["confidence"] == "high"


def test_go_kr_domain_government():
    r = classify_site(_obs(host="some-agency.go.kr"))
    assert r["site_type"] == SITE_GOVERNMENT
    assert r["confidence"] == "high"


def test_financial_by_text():
    r = classify_site(_obs(host="unknown-bank.com", text="은행 예금 대출 금융"))
    assert r["site_type"] == SITE_FINANCIAL


def test_blog_by_text():
    r = classify_site(_obs(host="my-personal-blog.com", title="블로그 포스팅", text="블로그 글쓰기"))
    assert r["site_type"] == SITE_BLOG


def test_ecommerce_by_text():
    r = classify_site(_obs(host="shop.example.com", text="장바구니 결제 구매 배송"))
    assert r["site_type"] == SITE_ECOMMERCE


def test_notice_board_by_text():
    r = classify_site(_obs(host="corp.example.com", text="공지사항 공고 알림"))
    assert r["site_type"] == SITE_NOTICE_BOARD


def test_unknown_site_classified_unknown():
    r = classify_site(_obs(host="completely-random-xyz.io", title="xyz", text="random content"))
    assert r["site_type"] == SITE_UNKNOWN


def test_confidence_levels():
    r_high = classify_site(_obs(host="blog.naver.com"))
    assert r_high["confidence"] == "high"

    r_med = classify_site(_obs(host="unknown.com", text="블로그 포스팅"))
    assert r_med["confidence"] in ("medium", "low")


def test_get_site_type_for_profile():
    assert get_site_type_for_profile("naver_blog") == SITE_BLOG
    assert get_site_type_for_profile("g2b_public") == SITE_GOVERNMENT
    assert get_site_type_for_profile("bank_placeholder") == SITE_FINANCIAL
    assert get_site_type_for_profile("unknown_profile_xyz") == SITE_UNKNOWN


def test_matched_profile_id_returned():
    r = classify_site(_obs(host="www.g2b.go.kr"))
    assert r["matched_profile_id"] is not None


def test_naver_cafe_classified():
    r = classify_site(_obs(host="cafe.naver.com"))
    # cafe.naver.com은 known map에서 CAFE_OR_FORUM, 없으면 naver.com subdomain으로 CONTENT_PLATFORM
    assert r["site_type"] in (SITE_CAFE_OR_FORUM, SITE_CONTENT_PLATFORM)
    assert r["confidence"] == "high"
