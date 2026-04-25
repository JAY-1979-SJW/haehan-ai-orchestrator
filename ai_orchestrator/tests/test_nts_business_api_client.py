"""TAX-API-1 — nts_business_api_client 단위 테스트.

검증:
  - normalize_business_number 정규화 (대시/공백/숫자 외 문자 제거, 10자리만)
  - 빈 입력 차단
  - 100건 초과 차단
  - mock_or_disabled 모드 (live=False / 키 없음)
  - status payload 빌더
  - validate item coercion + payload 빌더
  - HTTP 호출 경로에서 _opener 주입으로 mock — service_key 가 응답에 echo 될
    경우 redacted 처리되는지
  - HTTP 에러 응답 요약
"""
from __future__ import annotations

import io
import json
import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_orchestrator.connectors.nts_business_api_client import (  # noqa: E402
    KIND_STATUS,
    KIND_VALIDATE,
    MODE_LIVE,
    MODE_MOCK_OR_DISABLED,
    STATUS_PATH,
    VALIDATE_PATH,
    build_status_payload,
    build_validate_payload,
    check_status,
    normalize_business_number,
    validate_businesses,
)
from ai_orchestrator.connectors.nts_business_api_config import (  # noqa: E402
    NtsBusinessApiConfig,
)


# ─── normalize ────────────────────────────────────────────────────────────

def test_normalize_strips_non_digits_and_keeps_10_digits():
    assert normalize_business_number("123-45-67890") == "1234567890"
    assert normalize_business_number(" 123 45 67890 ") == "1234567890"
    assert normalize_business_number("123.45.67890") == "1234567890"


def test_normalize_rejects_wrong_length():
    assert normalize_business_number("123456789") == ""
    assert normalize_business_number("12345678901") == ""
    assert normalize_business_number("") == ""
    assert normalize_business_number(None) == ""


def test_normalize_rejects_bool():
    assert normalize_business_number(True) == ""
    assert normalize_business_number(False) == ""


def test_normalize_accepts_int_like_string():
    assert normalize_business_number("1234567890") == "1234567890"


# ─── payload builders ────────────────────────────────────────────────────

def test_build_status_payload_shape():
    out = build_status_payload(["1234567890", "0987654321"])
    assert out == {"b_no": ["1234567890", "0987654321"]}


def test_build_validate_payload_shape():
    items = [{"b_no": "1234567890", "start_dt": "20200101", "p_nm": "홍길동"}]
    out = build_validate_payload(items)
    assert out == {"businesses": items}


# ─── disabled mode (mock_or_disabled) ────────────────────────────────────

def _disabled_cfg() -> NtsBusinessApiConfig:
    return NtsBusinessApiConfig(
        service_key=None,
        base_url="https://example.invalid/api",
        timeout_seconds=10.0,
        live_enabled=False,
        service_key_source="",
    )


def _live_cfg(key: str = "FAKE_KEY") -> NtsBusinessApiConfig:
    return NtsBusinessApiConfig(
        service_key=key,
        base_url="https://example.invalid/api",
        timeout_seconds=10.0,
        live_enabled=True,
        service_key_source="NTS_BUSINESS_API_SERVICE_KEY",
    )


def test_check_status_disabled_when_live_false():
    out = check_status(["1234567890"], config=_live_cfg(), live=False)
    assert out["mode"] == MODE_MOCK_OR_DISABLED
    assert out["kind"] == KIND_STATUS
    assert out["count"] == 1
    assert out["items"] == []
    assert "live_disabled_or_no_service_key" in out["warnings"]
    assert out["success"] is True


def test_check_status_disabled_when_no_key():
    out = check_status(["1234567890"], config=_disabled_cfg(), live=True)
    assert out["mode"] == MODE_MOCK_OR_DISABLED
    assert out["count"] == 1


def test_check_status_empty_input_blocked():
    out = check_status([], config=_live_cfg())
    assert out["mode"] == MODE_MOCK_OR_DISABLED
    assert out["count"] == 0
    assert "empty_input" in out["warnings"]


def test_check_status_invalid_only_input_blocked():
    out = check_status(["abc", "12"], config=_live_cfg())
    assert out["mode"] == MODE_MOCK_OR_DISABLED
    assert out["count"] == 0
    assert any(w.startswith("invalid_input:") for w in out["warnings"])


def test_check_status_batch_too_large_blocked():
    big = [f"1{str(i).zfill(9)}" for i in range(150)]
    out = check_status(big, config=_live_cfg())
    assert out["mode"] == MODE_MOCK_OR_DISABLED
    assert any(
        w.startswith("batch_too_large:") for w in out["warnings"]
    )


def test_check_status_dedupes_normalized_numbers():
    out = check_status(
        ["123-45-67890", "1234567890", "1234-5678-90"],
        config=_disabled_cfg(),
    )
    # 모두 같은 정규화 결과 → count=1
    assert out["count"] == 1


def test_validate_businesses_disabled_with_invalid_items():
    out = validate_businesses(
        [{"b_no": "1234567890"}],  # start_dt/p_nm 누락
        config=_live_cfg(),
    )
    assert out["mode"] == MODE_MOCK_OR_DISABLED
    assert out["count"] == 0
    assert "empty_input" in out["warnings"]


def test_validate_businesses_normalizes_dashes_and_filters_invalid():
    out = validate_businesses(
        [
            {"b_no": "123-45-67890", "start_dt": "2020-01-01",
             "p_nm": " 홍길동 ", "b_nm": "테스트상사"},
            {"b_no": "bad"},
        ],
        config=_live_cfg(),
        live=False,
    )
    assert out["mode"] == MODE_MOCK_OR_DISABLED
    assert out["kind"] == KIND_VALIDATE
    assert out["count"] == 1
    # 무효 한 건은 invalid_input warning
    assert any(w.startswith("invalid_input:") for w in out["warnings"])


# ─── live path with mocked opener ────────────────────────────────────────

class _FakeResp:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _FakeUrlopen:
    """urlopen mock — 호출 인자를 캡처하고 미리 정한 응답을 돌려준다."""

    def __init__(self, status: int = 200, body: dict | None = None,
                 raw_body: bytes | None = None) -> None:
        self.status = status
        self.body = body
        self.raw_body = raw_body
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: float = 0.0) -> _FakeResp:
        # urllib.request.Request 의 method/full_url/data/headers 캡처.
        try:
            payload_bytes = request.data or b""
            payload = json.loads(payload_bytes.decode("utf-8")) if payload_bytes else None
        except Exception:
            payload = None
        self.calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "headers": dict(request.headers),
            "payload": payload,
            "timeout": timeout,
        })
        if self.raw_body is not None:
            return _FakeResp(self.status, self.raw_body)
        body_bytes = json.dumps(self.body or {}).encode("utf-8")
        return _FakeResp(self.status, body_bytes)


def test_check_status_live_calls_status_path_with_service_key_in_query():
    fake = _FakeUrlopen(status=200, body={
        "status_code": "OK",
        "match_cnt": 1,
        "request_cnt": 1,
        "data": [
            {"b_no": "1234567890", "b_stt": "계속사업자",
             "b_stt_cd": "01", "tax_type": "부가가치세 일반과세자",
             "tax_type_cd": "01"},
        ],
    })
    out = check_status(
        ["1234567890"], config=_live_cfg("MY_SECRET_KEY"), _opener=fake,
    )
    assert out["success"] is True
    assert out["mode"] == MODE_LIVE
    assert out["kind"] == KIND_STATUS
    assert out["count"] == 1
    assert len(out["items"]) == 1
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["method"] == "POST"
    assert STATUS_PATH in call["url"]
    assert "serviceKey=MY_SECRET_KEY" in call["url"]
    assert call["payload"] == {"b_no": ["1234567890"]}
    # Content-Type / Accept 헤더.
    norm_headers = {k.lower(): v for k, v in call["headers"].items()}
    assert "application/json" in norm_headers.get("content-type", "")
    # 결과 dict 의 url 필드는 redacted.
    assert "MY_SECRET_KEY" not in out["url"]
    assert "serviceKey=***" in out["url"]


def test_validate_businesses_live_calls_validate_path():
    fake = _FakeUrlopen(status=200, body={
        "status_code": "OK",
        "match_cnt": 1,
        "request_cnt": 1,
        "data": [
            {"b_no": "1234567890", "valid": "01", "valid_msg": ""},
        ],
    })
    items = [{"b_no": "1234567890", "start_dt": "20200101",
              "p_nm": "홍길동", "b_nm": "예시상사"}]
    out = validate_businesses(items, config=_live_cfg("KEY_A"), _opener=fake)
    assert out["mode"] == MODE_LIVE
    assert out["count"] == 1
    assert len(out["items"]) == 1
    call = fake.calls[0]
    assert VALIDATE_PATH in call["url"]
    assert "KEY_A" in call["url"]
    payload = call["payload"]
    assert "businesses" in payload
    assert payload["businesses"][0]["b_no"] == "1234567890"
    assert payload["businesses"][0]["start_dt"] == "20200101"
    assert payload["businesses"][0]["p_nm"] == "홍길동"
    assert payload["businesses"][0]["b_nm"] == "예시상사"


def test_live_http_error_returned_as_summary_with_redacted_url():
    # 400 응답 시 detail 에 service_key 가 echo 되어 들어와도 마스킹.
    secret = "ECHO_BACK_SECRET"
    fake = _FakeUrlopen(
        status=400,
        raw_body=(
            f"{{\"resultMessage\":\"INVALID serviceKey={secret}\"}}"
        ).encode("utf-8"),
    )
    out = check_status(["1234567890"], config=_live_cfg(secret), _opener=fake)
    assert out["success"] is False
    assert out["mode"] == MODE_LIVE
    assert out["status_code"] == 400
    assert secret not in out.get("detail", "")
    assert secret not in out.get("url", "")
    assert "***" in out.get("url", "")
    assert any(w == "HTTP_400" for w in out["warnings"])


def test_live_response_without_data_list_returns_empty_items():
    fake = _FakeUrlopen(status=200, body={
        "status_code": "OK", "match_cnt": 0, "request_cnt": 1,
    })
    out = check_status(["1234567890"], config=_live_cfg(), _opener=fake)
    assert out["success"] is True
    assert out["items"] == []


# ─── secret never logged through repr/json ───────────────────────────────

def test_disabled_payload_contains_no_service_key_value():
    cfg = _live_cfg("DO_NOT_LEAK_THIS")
    out = check_status(["1234567890"], config=cfg, live=False)
    s = json.dumps(out, ensure_ascii=False)
    assert "DO_NOT_LEAK_THIS" not in s
