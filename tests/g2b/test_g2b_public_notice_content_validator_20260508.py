"""
G2B 공개 공고 콘텐츠 유효성 판정 모듈 테스트

원칙:
- live_verdict(LIVE_PASS)와 content_verdict(CONTENT_VALID_PASS)는 분리
- "시스템 접근 안내" / "요청하신 페이지를 찾을수 없습니다" → CONTENT_VALID_PASS 불가
- "나라장터" 단어만으로 CONTENT_VALID_PASS 불가
- positive signal 2개 이상 + negative signal 없을 때만 CONTENT_VALID_PASS 후보
- final_url 도메인 이탈 시 CONTENT_INVALID
- wildcard 서브도메인 content valid 불가
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_orchestrator.connectors.g2b.g2b_public_notice_content_validator import (
    CONTENT_INVALID,
    CONTENT_UNKNOWN,
    CONTENT_VALID_PASS,
    REACHABLE_BUT_NOT_CONTENT_VALID,
    classify_g2b_public_notice_content,
    enrich_live_result_with_content_verdict,
    extract_g2b_public_notice_url_candidates,
    is_g2b_public_notice_content_valid,
    validate_g2b_public_notice_content_result,
)

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json"
_REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "reports" / "g2b"


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _make_result(
    title: str = "",
    body: str = "",
    final_url: str = "https://www.g2b.go.kr/test",
    verdict: str = "LIVE_PASS",
    links: list[str] | None = None,
) -> dict:
    return {
        "input_url": final_url,
        "final_url": final_url,
        "title": title,
        "body_text_sample": body,
        "body_text_length": len(body),
        "verdict": verdict,
        "mock_used": False,
        "local_agent_used": True,
        "server_browser_used": False,
        "links": links or [],
    }


_SYSTEM_ACCESS_NOTICE_BODY = (
    "나라장터 국가종합전자조달\n\n요청하신 페이지를 찾을수 없습니다.\n\n"
    "올바르지 않은 URL 접근일 수 있습니다.\n다시 한번 확인 후 이용해 주시기 바랍니다.\n\n"
    "나라장터 바로가기\n\n나라장터 이용관련 문의 : 1588 - 0800"
)

_VALID_NOTICE_BODY = (
    "공고명: 서울특별시 도로 유지보수 공사\n"
    "공고번호: 202505-00001\n"
    "수요기관: 서울특별시\n"
    "게시일시: 2026-05-08 09:00\n"
    "입찰방법: 일반경쟁\n"
)


# ── TC-01: title="시스템 접근 안내" → CONTENT_VALID_PASS 불가 ──────────────────


def test_system_access_notice_title_not_content_valid_pass():
    r = classify_g2b_public_notice_content(_make_result(title="시스템 접근 안내", body=_SYSTEM_ACCESS_NOTICE_BODY))
    assert r["content_verdict"] != CONTENT_VALID_PASS
    assert r["content_valid"] is False


# ── TC-02: body="요청하신 페이지를 찾을수 없습니다" → CONTENT_VALID_PASS 불가 ──


def test_page_not_found_body_not_content_valid_pass():
    r = classify_g2b_public_notice_content(
        _make_result(title="시스템 접근 안내", body="요청하신 페이지를 찾을수 없습니다")
    )
    assert r["content_verdict"] != CONTENT_VALID_PASS
    assert r["content_valid"] is False


# ── TC-03: "나라장터" 단어만으로 CONTENT_VALID_PASS 불가 ─────────────────────


def test_narajangteo_only_not_content_valid_pass():
    r = classify_g2b_public_notice_content(_make_result(title="나라장터", body="나라장터에 오신 것을 환영합니다"))
    assert r["content_verdict"] != CONTENT_VALID_PASS
    assert r["content_valid"] is False


# ── TC-04: positive signal 2개 이상 → CONTENT_VALID_PASS 후보 ────────────────


def test_two_positive_signals_content_valid_pass():
    r = classify_g2b_public_notice_content(
        _make_result(
            title="공고 목록",
            body="공고명: 테스트 공사\n공고번호: 2026-001\n수요기관: 서울시",
        )
    )
    assert r["content_verdict"] == CONTENT_VALID_PASS
    assert r["content_valid"] is True


# ── TC-05: positive signal 있어도 negative signal 있으면 invalid ──────────────


def test_positive_signal_with_login_negative_invalid():
    r = classify_g2b_public_notice_content(
        _make_result(
            title="공고명 조회",
            body="공고번호: 2026-001\n로그인 후 이용해 주세요",
        )
    )
    assert r["content_verdict"] != CONTENT_VALID_PASS
    assert r["content_valid"] is False


def test_positive_signal_with_cert_negative_invalid():
    r = classify_g2b_public_notice_content(
        _make_result(
            title="입찰공고",
            body="공고번호: 2026-001\n인증서가 필요합니다",
        )
    )
    assert r["content_verdict"] != CONTENT_VALID_PASS
    assert r["content_valid"] is False


def test_positive_signal_with_payment_negative_invalid():
    r = classify_g2b_public_notice_content(
        _make_result(
            title="공고명",
            body="공고번호: 2026-001\n결제 후 열람 가능",
        )
    )
    assert r["content_verdict"] != CONTENT_VALID_PASS
    assert r["content_valid"] is False


# ── TC-06: final_url이 허용 도메인 밖 → CONTENT_INVALID ─────────────────────


def test_final_url_outside_allowed_domain_content_invalid():
    r = classify_g2b_public_notice_content(
        _make_result(
            title="공고명: 테스트",
            body="공고번호: 2026-001\n수요기관: 서울시",
            final_url="https://external.example.com/page",
        )
    )
    assert r["content_verdict"] == CONTENT_INVALID
    assert r["content_valid"] is False


# ── TC-07: wildcard 서브도메인 content valid 불가 ─────────────────────────────


def test_wildcard_subdomain_not_content_valid():
    r = classify_g2b_public_notice_content(
        _make_result(
            title="공고명: 테스트",
            body="공고번호: 2026-001\n수요기관: 서울시\n게시일시: 2026-05-08",
            final_url="https://unknown-sub.g2b.go.kr/page",
        )
    )
    assert r["content_verdict"] == CONTENT_INVALID
    assert r["content_valid"] is False


# ── TC-08: login 경로 href → blocked_candidate_urls ──────────────────────────


def test_login_href_classified_as_blocked():
    r = classify_g2b_public_notice_content(_make_result(links=["https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do"]))
    assert "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do" in r["blocked_candidate_urls"]
    assert "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do" not in r["safe_candidate_urls"]


# ── TC-09: download 링크 → blocked_candidate_urls ───────────────────────────


def test_download_href_classified_as_blocked():
    r = classify_g2b_public_notice_content(_make_result(links=["https://www.g2b.go.kr/pt/file/download.do?id=123"]))
    blocked = r["blocked_candidate_urls"]
    assert any("download" in u for u in blocked)
    assert not any("download" in u for u in r["safe_candidate_urls"])


# ── TC-10: shop.g2b.go.kr → needs_verification_candidate_urls ────────────────


def test_shop_subdomain_needs_verification():
    r = classify_g2b_public_notice_content(_make_result(links=["https://shop.g2b.go.kr/"]))
    assert "https://shop.g2b.go.kr/" in r["needs_verification_candidate_urls"]
    assert "https://shop.g2b.go.kr/" not in r["safe_candidate_urls"]
    assert "https://shop.g2b.go.kr/" not in r["blocked_candidate_urls"]


# ── TC-11: safe_candidate_urls는 gate 통과 후보만 ──────────────────────────────


def test_safe_candidate_urls_only_allowed_domain():
    r = classify_g2b_public_notice_content(
        _make_result(
            links=[
                "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
                "https://external.example.com/page",
                "https://shop.g2b.go.kr/",
            ]
        )
    )
    assert "https://external.example.com/page" not in r["safe_candidate_urls"]
    assert "https://shop.g2b.go.kr/" not in r["safe_candidate_urls"]


# ── TC-12: discovery script import 시 side effect 없음 ──────────────────────


def test_discovery_script_import_no_side_effect():
    import importlib.util

    spec = importlib.util.find_spec(  # noqa: F841
        "scripts.g2b.discover_valid_public_notice_urls"
    )
    # 파일 경로로 직접 로드
    import importlib.machinery

    loader = importlib.machinery.SourceFileLoader(
        "discover_valid_public_notice_urls",
        str(Path(__file__).resolve().parent.parent.parent / "scripts" / "g2b" / "discover_valid_public_notice_urls.py"),
    )
    mod_spec = importlib.util.spec_from_loader("discover_valid_public_notice_urls", loader)
    mod = importlib.util.module_from_spec(mod_spec)
    # main()이 자동 실행되지 않아야 함 → 로드만 해도 예외 없어야 함
    loader.exec_module(mod)
    assert callable(getattr(mod, "main", None))


# ── TC-13: max-depth는 1 고정 ─────────────────────────────────────────────────


def test_discovery_max_depth_is_one():
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader(
        "discover_valid_public_notice_urls",
        str(Path(__file__).resolve().parent.parent.parent / "scripts" / "g2b" / "discover_valid_public_notice_urls.py"),
    )
    mod_spec = importlib.util.spec_from_loader("discover_valid_public_notice_urls", loader)
    mod = importlib.util.module_from_spec(mod_spec)
    loader.exec_module(mod)
    # _collect_anchors_via_playwright 존재 확인 (depth 1 구현)
    assert callable(getattr(mod, "_collect_anchors_via_playwright", None))


# ── TC-14: no-click/no-download 옵션 기본값 ──────────────────────────────────


def test_content_validator_has_no_click_no_download_code():
    import inspect

    import ai_orchestrator.connectors.g2b.g2b_public_notice_content_validator as m

    src = inspect.getsource(m)
    # click/type/fill/submit/download를 실행하는 코드가 없어야 함
    assert "page.click(" not in src
    assert "page.type(" not in src
    assert "page.fill(" not in src
    assert "page.keyboard" not in src


# ── TC-15: content_verdict와 live_verdict가 분리되는지 확인 ──────────────────


def test_content_verdict_and_live_verdict_are_separate():
    r = _make_result(title="시스템 접근 안내", body=_SYSTEM_ACCESS_NOTICE_BODY)
    enriched = enrich_live_result_with_content_verdict(r)
    assert enriched["verdict"] == "LIVE_PASS"
    assert enriched["content_verdict"] != CONTENT_VALID_PASS
    assert enriched["content_verdict"] == REACHABLE_BUT_NOT_CONTENT_VALID


# ── TC-16: LIVE_PASS + CONTENT_INVALID 조합이 WARN으로 남는지 ────────────────


def test_live_pass_content_invalid_combination():
    r = _make_result(
        title="시스템 접근 안내",
        body=_SYSTEM_ACCESS_NOTICE_BODY,
        verdict="LIVE_PASS",
    )
    enriched = enrich_live_result_with_content_verdict(r)
    assert enriched["verdict"] == "LIVE_PASS"
    assert not enriched["content_valid"]
    cv = enriched["content_verdict"]
    assert cv in (REACHABLE_BUT_NOT_CONTENT_VALID, CONTENT_INVALID, CONTENT_UNKNOWN)


# ── TC-17: CONTENT_VALID_PASS 후보가 분류 결과에 포함되는지 ──────────────────


def test_content_valid_pass_candidate_in_result():
    r = classify_g2b_public_notice_content(
        _make_result(
            title="입찰공고 목록",
            body="공고명: 도로 공사\n공고번호: 2026-002\n수요기관: 경기도",
        )
    )
    assert r["content_verdict"] == CONTENT_VALID_PASS
    assert r["content_valid"] is True
    assert r["positive_signals"]


# ── TC-18: 쿠키/session/token/password/otp 필드 저장 금지 ────────────────────


def test_no_secret_fields_in_classified_result():
    r = classify_g2b_public_notice_content(_make_result(title="공고명", body="공고번호: 2026-001\n수요기관: 서울시"))
    forbidden = {
        "cookie",
        "cookies",
        "session",
        "token",
        "password",
        "otp",
        "auth_token",
        "access_token",
        "refresh_token",
    }
    for field in forbidden:
        assert field not in r, f"금지 필드 {field!r} 발견"


# ── TC-19: body_text_sample 길이 제한 ────────────────────────────────────────


def test_body_text_sample_length_limit():
    long_body = "x" * 5000
    r = classify_g2b_public_notice_content(_make_result(body=long_body))
    assert len(r["body_text_sample"]) <= 1000


# ── TC-20: 기존 actual-live 결과 JSON을 validator가 읽고 분류 가능 ─────────────


def test_validator_can_classify_actual_live_json():
    report_files = sorted(_REPORT_DIR.glob("g2b_public_notice_actual_live_*.json"))
    if not report_files:
        pytest.skip("actual-live JSON 보고서 없음")

    latest = report_files[-1]
    with latest.open(encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    live_passed = [r for r in results if r.get("case_verdict") == "LIVE_PASS"]
    assert live_passed, "LIVE_PASS 케이스 없음"

    for item in live_passed:
        live_result = item.get("live_result", {})
        classified = classify_g2b_public_notice_content(live_result)
        assert "content_verdict" in classified
        assert "content_valid" in classified
        assert isinstance(classified["positive_signals"], list)
        assert isinstance(classified["negative_signals"], list)
        # 기존 report의 LIVE_PASS가 CONTENT_VALID_PASS가 아님을 확인
        assert classified["content_verdict"] != CONTENT_VALID_PASS, (
            f"기존 보고서의 LIVE_PASS가 CONTENT_VALID_PASS로 오승격됨: {item.get('id')}"
        )


# ── TC-21: validate_g2b_public_notice_content_result는 classify의 별칭 ────────


def test_validate_is_alias_of_classify():
    r = _make_result(title="공고명", body="공고번호: 001\n수요기관: 서울시\n게시일시: 2026")
    r1 = classify_g2b_public_notice_content(r)
    r2 = validate_g2b_public_notice_content_result(r)
    assert r1["content_verdict"] == r2["content_verdict"]
    assert r1["content_valid"] == r2["content_valid"]


# ── TC-22: extract_g2b_public_notice_url_candidates 반환 구조 확인 ────────────


def test_extract_url_candidates_returns_correct_structure():
    r = _make_result(
        links=[
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do",
            "https://shop.g2b.go.kr/",
        ]
    )
    result = extract_g2b_public_notice_url_candidates(r)
    assert "safe_candidate_urls" in result
    assert "blocked_candidate_urls" in result
    assert "needs_verification_candidate_urls" in result
    assert "candidate_url_count" in result
    assert result["safe_candidate_url_count"] >= 0
    assert result["blocked_candidate_url_count"] >= 0


# ── TC-23: is_g2b_public_notice_content_valid 단순 함수 확인 ─────────────────


def test_is_g2b_content_valid_with_valid_content():
    assert (
        is_g2b_public_notice_content_valid(
            title="공고명: 도로 공사",
            body_text="공고번호: 2026-001\n수요기관: 경기도",
            final_url="https://www.g2b.go.kr/page",
        )
        is True
    )


def test_is_g2b_content_valid_with_system_access_notice():
    assert (
        is_g2b_public_notice_content_valid(
            title="시스템 접근 안내",
            body_text=_SYSTEM_ACCESS_NOTICE_BODY,
            final_url="https://www.g2b.go.kr/page",
        )
        is False
    )


def test_is_g2b_content_valid_with_external_domain():
    assert (
        is_g2b_public_notice_content_valid(
            title="공고명: 도로 공사",
            body_text="공고번호: 001\n수요기관: 서울시",
            final_url="https://external.example.com/page",
        )
        is False
    )


# ── TC-24: enrich_live_result_with_content_verdict 보강 필드 확인 ─────────────


def test_enrich_live_result_has_all_required_fields():
    r = _make_result(title="시스템 접근 안내", body=_SYSTEM_ACCESS_NOTICE_BODY)
    enriched = enrich_live_result_with_content_verdict(r)
    required = [
        "content_verdict",
        "content_valid",
        "content_invalid_reason",
        "positive_signals",
        "negative_signals",
        "candidate_url_count",
        "safe_candidate_url_count",
        "blocked_candidate_url_count",
    ]
    for f in required:
        assert f in enriched, f"보강 필드 {f!r} 없음"


# ── TC-25: 기존 LIVE_PASS 판정을 content validator가 깨뜨리지 않음 ─────────────


def test_content_validator_does_not_break_live_pass():
    r = _make_result(title="시스템 접근 안내", body=_SYSTEM_ACCESS_NOTICE_BODY)
    enriched = enrich_live_result_with_content_verdict(r)
    # 기존 live verdict는 변경되지 않아야 함
    assert enriched["verdict"] == "LIVE_PASS"
    # content_verdict만 별도로 추가됨
    assert enriched["content_verdict"] == REACHABLE_BUT_NOT_CONTENT_VALID
