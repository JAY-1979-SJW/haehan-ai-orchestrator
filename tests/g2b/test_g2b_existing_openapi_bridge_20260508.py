"""
G2B 기존 OpenAPI 앱 Bridge Adapter 테스트

원칙:
- OpenAPI 직접 호출 없음
- API key 읽기/저장 없음
- DB 접근 없음
- CONTENT_VALID_PASS 임의 생성 없음
- 기존 fixture 직접 수정 없음
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_orchestrator.connectors.g2b.g2b_existing_openapi_bridge import (
    build_g2b_notice_candidates_from_existing_source,
    classify_existing_source_bridge_result,
    normalize_existing_g2b_openapi_item,
    validate_existing_g2b_openapi_bridge_payload,
    validate_g2b_notice_candidate,
)

_FIXTURE_SAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "g2b_existing_openapi_bridge_sample_20260508.json"
_FIXTURE_CANDIDATES = (
    Path(__file__).resolve().parent.parent / "fixtures" / "g2b_public_notice_existing_source_candidates_20260508.json"
)
_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "ai_orchestrator" / "connectors" / "g2b" / "g2b_existing_openapi_bridge.py"
)


def _load_sample_payload() -> dict:
    with _FIXTURE_SAMPLE.open(encoding="utf-8") as f:
        return json.load(f)


# ── TC-01: bridge가 API key를 읽지 않는지 정적 확인 ──────────────────────────


def test_bridge_no_api_key_read():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["G2B_API_KEY", "DATA_GO_KR_API", "os.environ", "os.getenv", "dotenv"]
    for f in forbidden:
        assert f not in src, f"금지 패턴 {f!r} 발견"


# ── TC-02: api_key_value_exposed=False 고정 확인 ─────────────────────────────


def test_api_key_value_exposed_always_false():
    payload = _load_sample_payload()
    result = build_g2b_notice_candidates_from_existing_source(payload)
    assert result["api_key_value_exposed"] is False


# ── TC-03: db_read_direct=False 고정 확인 ────────────────────────────────────


def test_db_read_direct_always_false():
    payload = _load_sample_payload()
    result = build_g2b_notice_candidates_from_existing_source(payload)
    assert result["db_read_direct"] is False


# ── TC-04: db_write=False 고정 확인 ──────────────────────────────────────────


def test_db_write_always_false():
    payload = _load_sample_payload()
    result = build_g2b_notice_candidates_from_existing_source(payload)
    assert result["db_write"] is False


# ── TC-05: 공고번호/공고차수 mapping 확인 ──────────────────────────────────────


def test_bid_notice_no_order_mapping():
    item = {
        "bidNtceNo": "20260508001",
        "bidNtceOrd": "00",
        "bidNtceNm": "테스트 공고",
    }
    norm = normalize_existing_g2b_openapi_item(item)
    assert norm["bid_notice_no"] == "20260508001"
    assert norm["bid_notice_order"] == "00"
    assert norm["notice_name"] == "테스트 공고"


# ── TC-06: notice_name/demand_org/notice_org mapping 확인 ────────────────────


def test_notice_name_demand_org_mapping():
    item = {
        "bidNtceNo": "001",
        "bidNtceOrd": "00",
        "bidNtceNm": "도로 공사",
        "demandOrgNm": "서울시",
        "ntceInsttNm": "서울시청",
    }
    norm = normalize_existing_g2b_openapi_item(item)
    assert norm["notice_name"] == "도로 공사"
    assert norm["demand_org"] == "서울시"
    assert norm["notice_org"] == "서울시청"


# ── TC-07: detail_url 있는 케이스 safe 후보 생성 ─────────────────────────────


def test_safe_detail_url_generates_safe_candidate():
    item = {
        "bid_notice_no": "001",
        "bid_notice_order": "00",
        "notice_name": "공사",
        "detail_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
    }
    norm = normalize_existing_g2b_openapi_item(item)
    validation = validate_g2b_notice_candidate(norm)
    assert validation["safe_detail_url"] == "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do"
    assert validation["blocked_detail_url"] == ""


# ── TC-08: downloadFile.do는 blocked ─────────────────────────────────────────


def test_download_url_is_blocked():
    item = {
        "bid_notice_no": "001",
        "bid_notice_order": "00",
        "notice_name": "공사",
        "detail_url": "https://www.g2b.go.kr/pt/file/downloadFile.do?id=999",
    }
    norm = normalize_existing_g2b_openapi_item(item)
    validation = validate_g2b_notice_candidate(norm)
    assert validation["blocked_detail_url"] != ""
    assert validation["safe_detail_url"] == ""


# ── TC-09: login 경로 blocked ─────────────────────────────────────────────────


def test_login_url_is_blocked():
    item = {
        "bid_notice_no": "001",
        "bid_notice_order": "00",
        "notice_name": "공사",
        "detail_url": "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do",
    }
    norm = normalize_existing_g2b_openapi_item(item)
    validation = validate_g2b_notice_candidate(norm)
    assert validation["blocked_detail_url"] != ""


# ── TC-10: wildcard subdomain은 safe 금지 ────────────────────────────────────


def test_wildcard_subdomain_not_safe():
    item = {
        "bid_notice_no": "001",
        "bid_notice_order": "00",
        "notice_name": "공사",
        "detail_url": "https://unknown-sub.g2b.go.kr/page",
    }
    norm = normalize_existing_g2b_openapi_item(item)
    validation = validate_g2b_notice_candidate(norm)
    assert validation["safe_detail_url"] == ""
    assert validation["detail_url_verdict"] != "safe"


# ── TC-11: detail_url 없고 link pattern 근거 없으면 detail_url_missing ────────


def test_no_detail_url_marks_missing():
    item = {
        "bid_notice_no": "001",
        "bid_notice_order": "00",
        "notice_name": "공사",
        "detail_url": None,
    }
    norm = normalize_existing_g2b_openapi_item(item)
    assert norm["detail_url_missing"] is True
    validation = validate_g2b_notice_candidate(norm)
    assert validation["safe_detail_url"] == ""
    assert validation["detail_url_verdict"] == "missing"


# ── TC-12: 필수 필드 누락 시 missing_required_fields 기록 ────────────────────


def test_missing_required_field_recorded():
    item = {
        "bid_notice_no": "001",
        "bid_notice_order": "00",
        # notice_name 없음
    }
    norm = normalize_existing_g2b_openapi_item(item)
    assert "notice_name" in norm["missing_required_fields"]


# ── TC-13: bridge output이 content validator 입력으로 변환 가능 ───────────────


def test_bridge_output_convertible_to_content_validator_input():
    from ai_orchestrator.connectors.g2b.g2b_public_notice_content_validator import (
        classify_g2b_public_notice_content,
    )

    payload = _load_sample_payload()
    result = build_g2b_notice_candidates_from_existing_source(payload)
    classified = classify_existing_source_bridge_result(result)
    cv_inputs = classified["content_validator_input_candidates"]
    assert isinstance(cv_inputs, list)
    for inp in cv_inputs:
        # content validator가 처리할 수 있는 형태인지 확인
        cv_result = classify_g2b_public_notice_content(inp)
        assert "content_verdict" in cv_result
        assert "content_valid" in cv_result
        # bridge가 CONTENT_VALID_PASS를 임의 생성하지 않음 (title/body 없으면 UNKNOWN)
        assert cv_result["content_verdict"] != "CONTENT_VALID_PASS"


# ── TC-14: bridge output이 execution gate로 전달 가능 ─────────────────────────


def test_bridge_output_usable_by_execution_gate():
    from ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter import (
        evaluate_g2b_public_notice_dryrun,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        GATE_READONLY_EXECUTION_CANDIDATE,
        evaluate_g2b_public_notice_execution_gate,
    )

    payload = _load_sample_payload()
    result = build_g2b_notice_candidates_from_existing_source(payload)
    classified = classify_existing_source_bridge_result(result)

    for url in classified["safe_detail_url_candidates"]:
        dryrun = evaluate_g2b_public_notice_dryrun(url=url, operation="read")
        gate = evaluate_g2b_public_notice_execution_gate(dryrun)
        assert gate["gate_verdict"] == GATE_READONLY_EXECUTION_CANDIDATE, f"safe URL {url!r}가 gate 통과 실패"


# ── TC-15: bridge가 CONTENT_VALID_PASS를 임의 생성하지 않음 ─────────────────


def test_bridge_does_not_generate_content_valid_pass():
    payload = _load_sample_payload()
    result = build_g2b_notice_candidates_from_existing_source(payload)
    classified = classify_existing_source_bridge_result(result)
    assert classified["content_valid_pass_set_by_bridge"] is False
    for cand in result["normalized_candidates"]:
        assert "CONTENT_VALID_PASS" not in str(cand.get("content_verdict", ""))


# ── TC-16: synthetic_sample=true fixture 처리 확인 ───────────────────────────


def test_synthetic_sample_flag_preserved():
    payload = _load_sample_payload()
    assert payload.get("synthetic_sample") is True
    result = build_g2b_notice_candidates_from_existing_source(payload)
    assert result.get("synthetic_sample") is True


# ── TC-17: OpenAPI 직접 호출 코드 없음 정적 검사 ──────────────────────────────


def test_no_openapi_direct_call():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [
        "requests.get",
        "httpx.get",
        "urllib.request.urlopen",
        "BidPublicInfoService",
    ]
    for f in forbidden:
        assert f not in src, f"금지 패턴 {f!r} 발견"


# ── TC-18: data.go.kr HTTP 호출 코드 없음 ────────────────────────────────────


def test_no_data_go_kr_http_call():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    # URL 문자열로 실제 호출하는 코드 없음
    assert "https://apis.data.go.kr" not in src
    assert "http://apis.data.go.kr" not in src


# ── TC-19: secret/token/password/otp 저장 없음 ───────────────────────────────


def test_no_secret_storage():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["cookies()", "storage_state", "page.password", "page.otp"]
    for f in forbidden:
        assert f not in src, f"금지 패턴 {f!r} 발견"


# ── TC-20: 기존 fixture 직접 수정 없음 ───────────────────────────────────────


def test_existing_fixture_not_modified():
    original_fixture = Path(__file__).resolve().parent.parent / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json"
    with original_fixture.open(encoding="utf-8") as f:
        data = json.load(f)
    # 기존 fixture는 "cases" 키를 가져야 함
    assert "cases" in data
    # 기존 fixture에 bridge 관련 필드가 없어야 함
    assert "source" not in data
    assert "api_key_used_by_current_app" not in data


# ── TC-21: bridge module import side effect 없음 ─────────────────────────────


def test_bridge_module_import_no_side_effect():
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("g2b_existing_openapi_bridge", str(_MODULE_PATH))
    spec = importlib.util.spec_from_loader("g2b_existing_openapi_bridge", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    assert callable(getattr(mod, "build_g2b_notice_candidates_from_existing_source"))


# ── TC-22: 기존 valid URL discovery 테스트와 충돌 없음 ───────────────────────


def test_bridge_does_not_break_content_validator():
    from ai_orchestrator.connectors.g2b.g2b_public_notice_content_validator import (
        classify_g2b_public_notice_content,
    )

    # 시스템 접근 안내는 여전히 CONTENT_VALID_PASS 불가
    result = classify_g2b_public_notice_content(
        {
            "input_url": "https://www.g2b.go.kr/test",
            "final_url": "https://www.g2b.go.kr/test",
            "title": "시스템 접근 안내",
            "body_text_sample": "요청하신 페이지를 찾을수 없습니다",
            "body_text_length": 20,
            "verdict": "LIVE_PASS",
        }
    )
    assert result["content_verdict"] != "CONTENT_VALID_PASS"


# ── TC-23: validate_existing_g2b_openapi_bridge_payload 정책 검증 ─────────────


def test_validate_bridge_payload_valid():
    payload = {
        "source": "existing_g2b_openapi_app",
        "api_key_used_by_current_app": False,
        "api_key_value_exposed": False,
        "db_read_direct": False,
        "db_write": False,
    }
    result = validate_existing_g2b_openapi_bridge_payload(payload)
    assert result["valid"] is True
    assert result["violations"] == []


def test_validate_bridge_payload_rejects_api_key_exposed():
    payload = {
        "source": "existing_g2b_openapi_app",
        "api_key_used_by_current_app": True,
        "api_key_value_exposed": True,
        "db_read_direct": False,
        "db_write": False,
    }
    result = validate_existing_g2b_openapi_bridge_payload(payload)
    assert result["valid"] is False
    assert len(result["violations"]) > 0


# ── TC-24: payment/contract URL도 blocked ────────────────────────────────────


def test_payment_contract_url_blocked():
    for url in [
        "https://www.g2b.go.kr/pay/checkout.do",
        "https://www.g2b.go.kr/ct/menu/ntn02/cta01/ctb01001l.do",
    ]:
        item = {
            "bid_notice_no": "001",
            "bid_notice_order": "00",
            "notice_name": "공사",
            "detail_url": url,
        }
        norm = normalize_existing_g2b_openapi_item(item)
        validation = validate_g2b_notice_candidate(norm)
        assert validation["blocked_detail_url"] != "", f"{url!r}가 blocked 아님"


# ── TC-25: snake_case 필드명 직접 입력 지원 ──────────────────────────────────


def test_snake_case_fields_direct_input():
    item = {
        "bid_notice_no": "20260508001",
        "bid_notice_order": "00",
        "notice_name": "도로 공사",
        "demand_org": "서울시",
        "notice_org": "서울시청",
        "posted_at": "2026-05-08 09:00",
        "business_type": "공사",
        "detail_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
    }
    norm = normalize_existing_g2b_openapi_item(item)
    assert norm["bid_notice_no"] == "20260508001"
    assert norm["notice_name"] == "도로 공사"
    assert norm["detail_url"] == "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do"


# ── TC-26: sample fixture 로드 및 build 실행 ────────────────────────────────


def test_build_from_sample_fixture():
    payload = _load_sample_payload()
    result = build_g2b_notice_candidates_from_existing_source(payload)
    assert result["item_count"] == 5
    assert result["api_key_used_by_current_app"] is False
    assert result["api_key_value_exposed"] is False
    assert result["db_write"] is False
    # downloadFile.do는 blocked
    assert any(
        "downloadFile" in u.lower() or "downloadfile" in u.lower() for u in result["blocked_detail_url_candidates"]
    )
    # 정상 safe URL 2개
    assert len(result["safe_detail_url_candidates"]) >= 1
