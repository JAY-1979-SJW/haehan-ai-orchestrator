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
