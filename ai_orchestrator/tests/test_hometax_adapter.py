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


# ─── F) F-4F-1 — extract_hometax_login_candidates ───────────────────────

def _make_observer_result(**overrides):
    """observe_public_browser_page 결과 모사 (필요 필드만 채움)."""
    base = {
        "success": True,
        "error_code": "",
        "warnings": [],
        "target_url": "https://www.hometax.go.kr/",
        "final_url_host_path": "www.hometax.go.kr/",
        "title": "국세청 홈택스 - 메인",
        "status_code": 200,
        "page_state": "public_page",
        "text_excerpt": "",
        "text_length": 0,
        "links_count": 0,
        "buttons_count": 0,
        "forms_count": 0,
        "inputs_count": 0,
        "links": [],
        "buttons": [],
        "forms": [],
        "input_types": [],
        "screenshot_path": None,
    }
    base.update(overrides)
    return base


def test_extract_login_candidates_finds_login_link():
    result = _make_observer_result(
        links=[
            {"text": "로그인", "href": "https://hometax.go.kr/login", "risk_hint": ""},
            {"text": "공지사항", "href": "https://hometax.go.kr/notice", "risk_hint": ""},
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["candidate_count"] == 1
    assert len(out["login_links"]) == 1
    cand = out["login_links"][0]
    assert cand["text"] == "로그인"
    assert "로그인" in cand["matched_tokens"]
    assert cand["href"] == "https://hometax.go.kr/login"


def test_extract_login_candidates_finds_certificate_link():
    result = _make_observer_result(
        links=[
            {"text": "공동인증서 로그인", "href": "https://hometax.go.kr/cert", "risk_hint": ""},
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert len(out["login_links"]) == 1
    matched = out["login_links"][0]["matched_tokens"]
    assert "공동인증서" in matched
    assert "로그인" in matched


def test_extract_login_candidates_finds_simple_auth_button():
    result = _make_observer_result(
        buttons=[
            {"text": "간편인증으로 로그인", "type": "button", "risk_level": "medium"},
            {"text": "조회", "type": "button", "risk_level": "low"},
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert len(out["login_buttons"]) == 1
    btn = out["login_buttons"][0]
    assert "간편인증" in btn["matched_tokens"]
    assert "로그인" in btn["matched_tokens"]
    assert btn["type"] == "button"


def test_extract_login_candidates_finds_id_login_button():
    result = _make_observer_result(
        buttons=[
            {"text": "아이디 로그인", "type": "submit", "risk_level": "high"},
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert len(out["login_buttons"]) == 1
    btn = out["login_buttons"][0]
    assert "아이디 로그인" in btn["matched_tokens"]


def test_extract_login_candidates_finds_password_form_without_text_token():
    """has_password=True 만으로도 후보 폼."""
    result = _make_observer_result(
        forms=[
            {
                "action": "/auth/submit",
                "method": "POST",
                "has_password": True,
                "input_count": 3,
                "risk_level": "high",
            },
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert len(out["login_forms"]) == 1
    f = out["login_forms"][0]
    assert f["has_password"] is True
    assert f["method"] == "POST"
    assert f["input_count"] == 3


def test_extract_login_candidates_finds_form_by_action_token():
    """action URL 의 login 토큰으로도 후보."""
    result = _make_observer_result(
        forms=[
            {
                "action": "https://hometax.go.kr/login",
                "method": "POST",
                "has_password": False,
                "input_count": 2,
                "risk_level": "medium",
            },
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert len(out["login_forms"]) == 1
    assert "login" in out["login_forms"][0]["matched_tokens"]


def test_extract_login_candidates_strips_query_fragment_in_href():
    """observer 가 빠뜨려도 추출기에서 query/fragment 한 번 더 제거."""
    result = _make_observer_result(
        links=[
            {
                "text": "로그인",
                "href": "https://hometax.go.kr/login?token=SECRET&user=me#frag",
                "risk_hint": "",
            },
        ],
        forms=[
            {
                "action": "/auth/submit?session=ABCDEF",
                "method": "POST",
                "has_password": True,
                "input_count": 2,
                "risk_level": "high",
            },
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    link_href = out["login_links"][0]["href"]
    form_action = out["login_forms"][0]["action"]
    # query/fragment 자체와 그 안의 키/값 토큰이 출력에 새면 안 된다.
    # 단순 2글자 부분문자열(host 와 우연히 겹치는 것) 은 제외.
    for sensitive in ("?", "#", "token=", "SECRET", "session=", "ABCDEF", "user=", "#frag"):
        assert sensitive not in link_href, link_href
        assert sensitive not in form_action, form_action


def test_extract_login_candidates_certificate_auth_signal():
    result = _make_observer_result(
        title="홈택스 로그인",
        text_excerpt="공동인증서로 로그인하세요",
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["auth_signals"]["certificate_auth"] is True


def test_extract_login_candidates_financial_certificate_signal():
    result = _make_observer_result(
        text_excerpt="금융인증서를 사용한 로그인 지원",
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["auth_signals"]["financial_certificate"] is True


def test_extract_login_candidates_simple_auth_signal():
    result = _make_observer_result(
        text_excerpt="간편인증 / 민간인증 사용 가능",
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["auth_signals"]["simple_auth"] is True


def test_extract_login_candidates_id_login_signal():
    result = _make_observer_result(
        text_excerpt="아이디로 로그인하기",
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["auth_signals"]["id_login"] is True


def test_extract_login_candidates_security_program_signal():
    result = _make_observer_result(
        text_excerpt="보안프로그램 설치가 필요합니다 (보안키패드)",
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["auth_signals"]["security_program"] is True


def test_extract_login_candidates_captcha_signal():
    result = _make_observer_result(
        text_excerpt="자동입력방지 보안문자를 입력하세요 (captcha)",
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["auth_signals"]["captcha_or_bot_check"] is True


def test_extract_login_candidates_empty_when_no_login():
    """후보가 없으면 candidate_count=0, 모든 신호 False."""
    result = _make_observer_result(
        links=[{"text": "공지사항", "href": "https://hometax.go.kr/notice", "risk_hint": ""}],
        buttons=[{"text": "조회", "type": "button", "risk_level": "low"}],
        text_excerpt="환영합니다",
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["candidate_count"] == 0
    assert out["login_links"] == []
    assert out["login_buttons"] == []
    assert out["login_forms"] == []
    for key in (
        "certificate_auth", "financial_certificate", "simple_auth",
        "id_login", "security_program", "captcha_or_bot_check",
    ):
        assert out["auth_signals"][key] is False


def test_extract_login_candidates_handles_non_dict_observer():
    """비정상 입력 — 예외 없이 warnings 에 기록."""
    out = hometax.extract_hometax_login_candidates("not a dict")
    assert out["candidate_count"] == 0
    assert out["login_links"] == []
    assert "observer_result_not_dict" in out["warnings"]


def test_extract_login_candidates_handles_non_list_fields():
    """links/buttons/forms 가 list 가 아니면 warnings 에 기록."""
    result = _make_observer_result()
    result["links"] = "not_a_list"
    result["buttons"] = 123
    result["forms"] = {"oops": True}
    out = hometax.extract_hometax_login_candidates(result)
    assert "links_not_list" in out["warnings"]
    assert "buttons_not_list" in out["warnings"]
    assert "forms_not_list" in out["warnings"]
    assert out["candidate_count"] == 0


def test_extract_login_candidates_does_not_emit_input_values():
    """입력 value 류 필드가 있어도 출력 dict 에 새지 않는다."""
    result = _make_observer_result(
        links=[
            {
                "text": "로그인",
                "href": "https://hometax.go.kr/login",
                "risk_hint": "",
                # observer 스키마 외 필드를 일부러 끼워서 무시되는지 확인.
                "value": "should_not_leak",
                "password": "PW123",
            },
        ],
        forms=[
            {
                "action": "/auth",
                "method": "POST",
                "has_password": True,
                "input_count": 2,
                "risk_level": "high",
                "value": "form_value",
                "password": "form_pw",
            },
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    for cand in out["login_links"] + out["login_forms"]:
        assert "value" not in cand
        assert "password" not in cand
        for v in cand.values():
            if isinstance(v, str):
                assert "PW123" not in v
                assert "form_pw" not in v
                assert "should_not_leak" not in v
                assert "form_value" not in v


def test_extract_login_candidates_sort_by_matched_tokens_then_length():
    """matched_tokens 수 많은 순 → 길이 짧은 순."""
    result = _make_observer_result(
        links=[
            {"text": "로그인 안내 페이지로 이동하기", "href": "https://hometax.go.kr/help", "risk_hint": ""},
            {"text": "로그인", "href": "https://hometax.go.kr/login", "risk_hint": ""},
            {"text": "공동인증서 간편인증 로그인", "href": "https://hometax.go.kr/cert", "risk_hint": ""},
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    texts = [c["text"] for c in out["login_links"]]
    # 첫 항목은 매칭 토큰이 가장 많은 "공동인증서 간편인증 로그인" (3개).
    assert texts[0] == "공동인증서 간편인증 로그인"
    # 동일 매칭 수면 짧은 text 가 먼저.
    assert texts[1] == "로그인"
    assert texts[2] == "로그인 안내 페이지로 이동하기"


def test_extract_login_candidates_count_matches_lists():
    result = _make_observer_result(
        links=[
            {"text": "로그인", "href": "https://hometax.go.kr/login", "risk_hint": ""},
        ],
        buttons=[
            {"text": "간편인증", "type": "button", "risk_level": "medium"},
        ],
        forms=[
            {
                "action": "/auth",
                "method": "POST",
                "has_password": True,
                "input_count": 2,
                "risk_level": "high",
            },
        ],
    )
    out = hometax.extract_hometax_login_candidates(result)
    assert out["candidate_count"] == 3
    assert len(out["login_links"]) == 1
    assert len(out["login_buttons"]) == 1
    assert len(out["login_forms"]) == 1


# ─── G) F-4G-1 — build_hometax_controlled_action_plan ───────────────────

def test_controlled_plan_classifies_links_into_categories():
    """홈택스 메인 observer fixture 에서 조회/다운로드/차단 후보 분류."""
    result = _make_observer_result(
        page_state="public_page",
        links=[
            {"text": "전자세금계산서 조회", "href": "https://hometax.go.kr/issued", "risk_hint": ""},
            {"text": "엑셀 다운로드", "href": "https://hometax.go.kr/excel", "risk_hint": ""},
            {"text": "신고서 제출", "href": "https://hometax.go.kr/submit", "risk_hint": ""},
            {"text": "공지사항", "href": "https://hometax.go.kr/notice", "risk_hint": ""},
        ],
    )
    plan = hometax.build_hometax_controlled_action_plan(result)
    assert plan["site_key"] == "hometax"
    read_texts = [c["text"] for c in plan["safe_read_candidates"]]
    download_texts = [c["text"] for c in plan["download_candidates"]]
    blocked_texts = [c["text"] for c in plan["blocked_candidates"]]
    assert "전자세금계산서 조회" in read_texts
    assert "엑셀 다운로드" in download_texts
    assert "신고서 제출" in blocked_texts


def test_controlled_plan_attaches_login_candidates_and_security_signals():
    """plan 결과에 login_candidates / security_program_signals dict 가 부착."""
    result = _make_observer_result(
        page_state="login_required",
        links=[
            {"text": "공동인증서 로그인", "href": "https://hometax.go.kr/cert", "risk_hint": ""},
        ],
        text_excerpt="보안프로그램 설치가 필요합니다",
    )
    plan = hometax.build_hometax_controlled_action_plan(result)
    assert plan["login_candidates"] is not None
    assert plan["login_candidates"]["candidate_count"] >= 1
    assert plan["security_program_signals"] is not None
    assert plan["security_program_signals"]["manual_action_required"] is True


def test_controlled_plan_login_required_sets_manual_action_required():
    plan = hometax.build_hometax_controlled_action_plan(
        _make_observer_result(page_state="login_required"),
    )
    assert plan["manual_action_required"] is True


def test_controlled_plan_security_program_required_sets_manual_action():
    plan = hometax.build_hometax_controlled_action_plan(
        _make_observer_result(page_state="security_program_required"),
    )
    assert plan["manual_action_required"] is True


def test_controlled_plan_unrecoverable_states_clear_candidates():
    plan = hometax.build_hometax_controlled_action_plan(
        _make_observer_result(
            page_state="not_found",
            links=[{"text": "조회", "href": "/x", "risk_hint": ""}],
        ),
    )
    assert plan["unrecoverable"] is True
    assert plan["safe_read_candidates"] == []


def test_controlled_plan_handles_non_dict_result():
    plan = hometax.build_hometax_controlled_action_plan("not a dict")
    assert plan["site_key"] == "hometax"
    assert plan["safe_read_candidates"] == []
    assert plan["download_candidates"] == []
    assert plan["blocked_candidates"] == []
    assert "observer_result_not_dict" in plan["warnings"]


def test_controlled_plan_strips_query_fragment_in_href():
    result = _make_observer_result(
        page_state="public_page",
        links=[{
            "text": "엑셀 다운로드",
            "href": "https://hometax.go.kr/excel?token=SECRET#frag",
            "risk_hint": "",
        }],
    )
    plan = hometax.build_hometax_controlled_action_plan(result)
    href = plan["download_candidates"][0]["href"]
    for sensitive in ("?", "#", "token=", "SECRET", "#frag"):
        assert sensitive not in href, href
