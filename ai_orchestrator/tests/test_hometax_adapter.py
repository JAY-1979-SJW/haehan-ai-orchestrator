"""F-4C — local_agent.site_adapters.hometax 단위 테스트.

검증:
  A) is_hometax_host
  B) classify_hometax_page — 우선순위 (sensitive > download > login > auth)
  C) build_hometax_download_plan — 정상/누락/잘못된 type/withholding presence
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent.site_adapters import hometax  # noqa: E402


# ─── A) is_hometax_host ──────────────────────────────────────────────────

@pytest.mark.parametrize("v", [
    "hometax.go.kr",
    "www.hometax.go.kr",
    "https://hometax.go.kr/",
    "https://teht.hometax.go.kr/abc",
])
def test_is_hometax_host_accepts(v):
    assert hometax.is_hometax_host(v) is True


@pytest.mark.parametrize("v", [
    "", None, "naver.com", "https://hometax.go.kr.evil.com/",
    "ftp://hometax.go.kr/",
])
def test_is_hometax_host_rejects(v):
    assert hometax.is_hometax_host(v) is False


# ─── B) classify_hometax_page ────────────────────────────────────────────

def test_login_required_classification():
    state = hometax.classify_hometax_page(
        title="홈택스 로그인",
        url="https://hometax.go.kr/login",
        text="공동인증서 / 간편인증 / 금융인증서 로 로그인하세요",
    )
    assert state == "login_required"
    assert hometax.is_hometax_login_required(
        title="홈택스 로그인", text="공동인증서로 로그인",
    )


def test_authenticated_classification():
    state = hometax.classify_hometax_page(
        title="마이홈택스",
        url="https://www.hometax.go.kr/main",
        text="납세자정보 기본정보 로그아웃",
    )
    assert state == "authenticated"
    assert hometax.is_hometax_authenticated(
        title="마이홈택스", text="로그아웃 납세자정보",
    )


def test_download_page_classification():
    state = hometax.classify_hometax_page(
        title="전자세금계산서 합계 조회",
        url="https://www.hometax.go.kr/somepage",
        text="발급내역 조회 - 엑셀 다운로드 - .xlsx 내려받기",
    )
    assert state == "download_page"
    assert hometax.is_hometax_download_page(
        title="발급내역 조회",
        text="엑셀 다운로드 / 내려받기",
    )


def test_sensitive_submission_classification():
    state = hometax.classify_hometax_page(
        title="부가가치세 신고서",
        url="https://hometax.go.kr/file",
        text="신고서 제출 / 최종 제출 / 전자납부",
    )
    assert state == "sensitive_submission"
    assert hometax.is_hometax_sensitive_submission(
        title="부가가치세",
        text="신고서 제출",
    )


def test_sensitive_priority_over_download_and_login():
    # 신고/납부/발행 토큰이 있으면 다운로드/로그인 토큰보다 우선.
    state = hometax.classify_hometax_page(
        title="홈택스",
        url="https://hometax.go.kr/x",
        text="공동인증서 로그인 후 엑셀 다운로드 하지만 세금계산서 발행 도 가능",
    )
    assert state == "sensitive_submission"


def test_download_priority_over_authenticated():
    # 다운로드 메뉴에는 보통 사이드바에 "로그아웃" 이 있어 auth 토큰과
    # 충돌. 다운로드 토큰이 더 명시적이므로 우선해야 한다.
    state = hometax.classify_hometax_page(
        title="발급내역 조회",
        url="https://www.hometax.go.kr/issued",
        text="로그아웃 마이홈택스 엑셀 다운로드",
    )
    assert state == "download_page"


def test_login_priority_over_authenticated_when_no_download():
    state = hometax.classify_hometax_page(
        title="로그인",
        url="https://hometax.go.kr/login",
        text="공동인증서",
    )
    assert state == "login_required"


def test_unknown_when_no_tokens():
    state = hometax.classify_hometax_page(
        title="홈택스",
        url="https://www.hometax.go.kr/",
        text="환영합니다",
    )
    assert state == "unknown"


# ─── C) build_hometax_download_plan ──────────────────────────────────────

@pytest.mark.parametrize("dt", list(hometax.DOWNLOAD_TYPES))
def test_download_plan_accepts_known_types(tmp_path, dt):
    out = hometax.build_hometax_download_plan(
        download_type=dt,
        period="2026-Q1",
        output_folder=str(tmp_path),
    )
    assert out["ok"] is True
    assert out["site_key"] == "hometax"
    assert out["download_type"] == dt
    assert out["period"] == "2026-Q1"
    assert out["output_folder"] == str(tmp_path)


def test_download_plan_rejects_unknown_type(tmp_path):
    out = hometax.build_hometax_download_plan(
        download_type="hack_all_taxes",
        period="2026-Q1",
        output_folder=str(tmp_path),
    )
    assert out["ok"] is False
    assert out["error_code"] == "INVALID_DOWNLOAD_TYPE"


def test_download_plan_rejects_missing_period(tmp_path):
    out = hometax.build_hometax_download_plan(
        download_type="tax_invoice_sales",
        period="",
        output_folder=str(tmp_path),
    )
    assert out["ok"] is False
    assert out["error_code"] == "MISSING_PERIOD"


def test_download_plan_rejects_missing_folder():
    out = hometax.build_hometax_download_plan(
        download_type="tax_invoice_sales",
        period="2026-Q1",
        output_folder="",
    )
    assert out["ok"] is False
    assert out["error_code"] == "MISSING_OUTPUT_FOLDER"


def test_withholding_plan_requires_user_presence(tmp_path):
    out = hometax.build_hometax_download_plan(
        download_type="withholding_docs",
        period="2026-04",
        output_folder=str(tmp_path),
    )
    assert out["ok"] is True
    assert out["requires_user_presence"] is True


def test_other_types_do_not_require_user_presence(tmp_path):
    out = hometax.build_hometax_download_plan(
        download_type="tax_invoice_purchases",
        period="2026-Q1",
        output_folder=str(tmp_path),
    )
    assert out["ok"] is True
    assert out["requires_user_presence"] is False


# ─── D) F-4F-0 — 메인 페이지 / 강한 신호 / 단독 토큰 ────────────────────

# 홈택스 메인 페이지의 실제 메뉴 카탈로그를 모사한 텍스트.  신고/납부/발급/
# 발행 같은 단어가 다수 노출되지만 "최종 제출", "납부하기" 같은 강한 신호는
# 없다.
_HOMETAX_MAIN_MENU_TEXT = (
    "조회/발급 신고/납부 신청/제출 상담/제보 세무대리·납세관리 "
    "전자세금계산서 현금영수증 연말정산 사업자등록 부가가치세 "
    "원천세 종합소득세 법인세 양도소득세 증권거래세 "
    "발급 발행 신고 납부 제출 조회 다운로드 "
    "공인인증센터 보안프로그램"
)


def test_main_page_with_menu_catalog_is_not_sensitive():
    """홈택스 메인 페이지: 메뉴 카탈로그에 신고/납부/발급/발행 단어가
    다수 있어도 sensitive_submission 으로 잡지 않는다."""
    state = hometax.classify_hometax_page(
        title="국세청 홈택스 - 메인",
        url="https://www.hometax.go.kr/",
        text=_HOMETAX_MAIN_MENU_TEXT,
    )
    assert state != "sensitive_submission"


def test_main_page_title_alone_not_sensitive():
    """title 이 \"국세청 홈택스 - 메인\" 이면 단독 신고/납부 단어로
    sensitive 검사를 건너뛴다."""
    state = hometax.classify_hometax_page(
        title="국세청 홈택스 - 메인",
        url="https://www.hometax.go.kr/index",
        text="신고 납부 발급 발행 조회",
    )
    assert state != "sensitive_submission"


def test_main_page_url_root_not_sensitive():
    """URL path 가 루트(/) 이면 메인 페이지 가드로 sensitive 검사 건너뜀."""
    state = hometax.classify_hometax_page(
        title="홈택스",
        url="https://www.hometax.go.kr/",
        text="신고 납부 발급 발행 결제 전송 위임 수임",
    )
    assert state != "sensitive_submission"


def test_main_page_websquare_path_not_sensitive():
    """websquare 진입 path 도 메인 형식 — sensitive 검사 건너뜀."""
    state = hometax.classify_hometax_page(
        title="홈택스",
        url="https://www.hometax.go.kr/websquare/websquare.html",
        text="신고 납부 발급 발행",
    )
    assert state != "sensitive_submission"


@pytest.mark.parametrize(
    "strong_text",
    [
        "신고서 제출",
        "최종 제출",
        "납부하기",
        "결제하기",
        "발행하기",
        "이체",
        "최종전송",
        "전송하기",
        "전자세금계산서 발행",
        "사업자정보 변경",
        "위임/수임 변경",
        "확인 후 제출",
        "최종 확인",
    ],
)
def test_strong_signals_classified_as_sensitive(strong_text):
    """메인이 아닌 페이지에서 강한 신호 토큰은 sensitive_submission."""
    state = hometax.classify_hometax_page(
        title="부가가치세 신고서",
        url="https://hometax.go.kr/file/some/path",
        text=strong_text,
    )
    assert state == "sensitive_submission", (strong_text, state)


@pytest.mark.parametrize(
    "weak_text",
    [
        "납부",       # 단독 단어
        "결제",       # 단독 단어
        "전송",       # 단독 단어
        "위임",       # 단독 단어
        "수임",       # 단독 단어
        "발급",       # 단독 단어
        "발행",       # 단독 단어
        "신고",       # 단독 단어
    ],
)
def test_standalone_menu_words_not_sensitive(weak_text):
    """비-메인 페이지에서도 단독 메뉴 단어만으로는 sensitive 잡지 않음."""
    state = hometax.classify_hometax_page(
        title="조회 화면",
        url="https://hometax.go.kr/some/page",
        text=weak_text,
    )
    assert state != "sensitive_submission", (weak_text, state)


def test_lookup_page_for_invoice_is_not_sensitive():
    """전자세금계산서 \"조회\" 는 sensitive 가 아닌 download_page 로."""
    state = hometax.classify_hometax_page(
        title="전자세금계산서 조회",
        url="https://www.hometax.go.kr/issued/lookup",
        text="발급내역 조회 합계 조회 엑셀 다운로드",
    )
    assert state == "download_page"


def test_download_word_classifies_as_download_page():
    """\"다운로드\" 단독으로도 download_page (메인이 아닐 때)."""
    state = hometax.classify_hometax_page(
        title="자료실",
        url="https://hometax.go.kr/board/files",
        text="첨부파일 다운로드",
    )
    assert state == "download_page"


# ─── E) 회귀 검증 — 기존 분류는 그대로 ──────────────────────────────────

def test_regression_login_required_classification():
    state = hometax.classify_hometax_page(
        title="홈택스 로그인",
        url="https://hometax.go.kr/login",
        text="공동인증서 / 간편인증 / 금융인증서",
    )
    assert state == "login_required"


def test_regression_authenticated_classification():
    state = hometax.classify_hometax_page(
        title="마이홈택스",
        url="https://www.hometax.go.kr/main",
        text="납세자정보 기본정보 로그아웃",
    )
    assert state == "authenticated"


def test_regression_download_page_classification():
    state = hometax.classify_hometax_page(
        title="전자세금계산서 합계 조회",
        url="https://www.hometax.go.kr/somepage",
        text="발급내역 조회 - 엑셀 다운로드 - .xlsx 내려받기",
    )
    assert state == "download_page"
