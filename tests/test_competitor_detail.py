"""경쟁사 상세 수집 모듈 테스트 (브라우저 없이 검증).

이 파일이 지키는 실제 사고(2026-08-15):
  1. 목록가는 최저 옵션가 — 25,000원 표시인데 실구매 33,000원 (48% 과소평가)
  2. 검색결과 링크는 전부 adcr(광고 클릭 추적) — 대량 자동 호출 시 부정클릭
  3. 폴백이 배송비 4,000원을 총액으로 오인 → 산술 자기검증으로 검출
  4. "틀린 값을 확신에 차서 반환"이 가장 위험 → 모르면 None + needs_review
"""

from __future__ import annotations

import inspect

from scripts.naver.shopping.competitor_detail import (
    CompetitorProduct,
    Field,
    OptionCombo,
    is_safe_product_url,
)
from scripts.naver.shopping.competitor_detail.detail_parser import (
    CompetitorDetailParser,
    _extra_won,
    _extra_won_opt,
    _won,
)


# ── adcr 차단 ────────────────────────────────────────────────────
def test_adcr_link_rejected():
    """광고 클릭 추적 링크는 절대 사용하면 안 된다(부정클릭 = 광고주 과금)."""
    assert is_safe_product_url("https://cr.shopping.naver.com/adcr?x=abc") is False


def test_direct_smartstore_url_accepted():
    assert is_safe_product_url("https://smartstore.naver.com/myeongjeong/products/13506323015")
    assert is_safe_product_url("smartstore.naver.com/main/products/6566948171")


def test_garbage_url_rejected():
    assert is_safe_product_url("") is False
    assert is_safe_product_url("https://example.com/products/1") is False


def test_parser_open_raises_on_adcr():
    """파서 진입점에서도 방어해야 한다."""
    p = CompetitorDetailParser.__new__(CompetitorDetailParser)
    try:
        CompetitorDetailParser.open(p, "https://cr.shopping.naver.com/adcr?x=z")
    except ValueError as e:
        assert "adcr" in str(e)
    else:
        raise AssertionError("adcr URL 인데 예외가 발생하지 않았다")


# ── 금액 파싱 ────────────────────────────────────────────────────
def test_won_parsing():
    assert _won("총 금액 33,000원") == 33000
    assert _won("가격 없음") is None


def test_extra_won_parsing():
    """옵션 추가금 '(+8,000원)' 을 읽어야 한다."""
    assert _extra_won("주광색 5700K ( 하얀색 불빛 ) (+8,000원)") == 8000
    assert _extra_won("600mm 일자 20W") == 0


def test_extra_won_opt_distinguishes_zero_from_unknown():
    """표기가 없으면 0 이 아니라 None — 이 구분이 오탐 유무를 가른다."""
    assert _extra_won_opt("주광색 5700K (+8,000원)") == 8000
    assert _extra_won_opt("1200mm 일자 40W") is None


# ── 자기검증 ─────────────────────────────────────────────────────
def test_option_verify_detects_total_below_base():
    """총액이 기본가보다 작을 수는 없다 — 배송비 4,000원을 총액으로 오인한 사고."""
    o = OptionCombo(labels=["600mm"], extra_won=0, total_won=4000)
    o.verify(base_price=25000)
    assert o.needs_review is True
    assert "총액 불신" in o.review_reason


def test_option_verify_detects_arithmetic_mismatch():
    """추가금을 아는데 합이 안 맞으면 잡아낸다."""
    o = OptionCombo(labels=["1200mm"], extra_won=8000, total_won=40000)
    o.verify(base_price=25000)
    assert o.needs_review is True
    assert "산술 불일치" in o.review_reason


def test_unknown_extra_does_not_false_alarm():
    """추가금 미표기 스토어(실측: 명정라이팅 1단 옵션)에서 거짓 경보를 내면 안 된다.

    extra_won=None 은 '0 원' 이 아니라 '모름' 이다. 모르는 것을 0 으로 단정해
    산술 불일치를 만들어내면 그 경보 자체가 오류다.
    """
    o = OptionCombo(labels=["1200mm 일자 40W"], extra_won=None, total_won=33000)
    o.verify(base_price=25000)
    assert o.needs_review is False, f"거짓 경보: {o.review_reason}"


def test_option_verify_passes_when_consistent():
    o = OptionCombo(labels=["1200mm", "주광색"], extra_won=8000, total_won=33000)
    o.verify(base_price=25000)
    assert o.needs_review is False


def test_option_verify_flags_missing_total():
    o = OptionCombo(labels=["600mm"], extra_won=0, total_won=None)
    o.verify(base_price=25000)
    assert o.needs_review is True
    assert "총금액 미확인" in o.review_reason


# ── 모르면 None (추측 금지) ──────────────────────────────────────
def test_field_unknown_by_default():
    f = Field()
    assert f.value is None
    assert f.known is False


def test_product_flags_when_no_options():
    """옵션을 못 모으면 실구매가 산정이 불가하므로 반드시 표시해야 한다."""
    p = CompetitorProduct(url="u", title=Field("t", "dom", "high"), base_price=Field(25000, "dom", "medium"))
    p.finalize()
    assert p.needs_review is True
    assert any("옵션 미수집" in r for r in p.review_reasons)


def test_price_range_none_when_unknown():
    """총액을 모르면 범위도 None — 0 이나 추정값을 만들지 않는다."""
    p = CompetitorProduct(options=[OptionCombo(labels=["a"], total_won=None)])
    assert p.price_range() == (None, None)


def test_price_range_computed_when_known():
    p = CompetitorProduct(
        options=[
            OptionCombo(labels=["a"], total_won=33000),
            OptionCombo(labels=["b"], total_won=25000),
        ]
    )
    assert p.price_range() == (25000, 33000)


# ── 안전장치 ─────────────────────────────────────────────────────
def test_parser_never_clicks_purchase():
    """구매/장바구니 버튼을 클릭 대상으로 두면 안 된다."""
    src = inspect.getsource(CompetitorDetailParser)
    # 클릭 호출이 들어간 라인에 금지어가 없어야 한다
    for line in src.splitlines():
        if ".click(" not in line:
            continue
        for bad in ("구매하기", "장바구니", "선물하기", "결제"):
            assert bad not in line, f"금지 버튼 클릭 시도: {line.strip()[:70]}"


def test_vision_fallback_exists():
    """DOM 파싱이 깨져도 스크린샷으로 판독할 경로가 있어야 한다."""
    assert hasattr(CompetitorDetailParser, "vision_manifest")
    assert hasattr(CompetitorDetailParser, "apply_vision")
    assert hasattr(CompetitorDetailParser, "_shot_price_area")


def test_apply_vision_fills_and_reverifies():
    """AI 판독값 반영 후 자기검증이 다시 돌아야 한다."""
    p = CompetitorProduct(base_price=Field(25000, "dom", "medium"), title=Field("t", "dom", "high"))
    p.options = [OptionCombo(labels=["1200mm", "주광색"], extra_won=None, total_won=None)]
    par = CompetitorDetailParser.__new__(CompetitorDetailParser)
    CompetitorDetailParser.apply_vision(par, p, {0: {"total": 33000, "extra": 8000}})
    assert p.options[0].total_won == 33000
    assert p.options[0].needs_review is False
    assert p.price_range() == (33000, 33000)
