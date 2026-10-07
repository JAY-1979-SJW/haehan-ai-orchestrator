"""
G2B 기존 OpenAPI 앱 Bridge Contract 테스트

contract 문서와 fixture의 정책 준수를 정적으로 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

_CONTRACT_DOC = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "design" / "g2b_existing_openapi_bridge_contract_20260508.md"
)
_FIXTURE_SAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "g2b_existing_openapi_bridge_sample_20260508.json"
_FIXTURE_CANDIDATES = (
    Path(__file__).resolve().parent.parent / "fixtures" / "g2b_public_notice_existing_source_candidates_20260508.json"
)
_BRIDGE_MODULE = (
    Path(__file__).resolve().parent.parent.parent / "ai_orchestrator" / "connectors" / "g2b" / "g2b_existing_openapi_bridge.py"
)


# ── TC-01: contract 문서 존재 확인 ──────────────────────────────────────────


def test_contract_document_exists():
    assert _CONTRACT_DOC.exists(), "contract 문서 없음"


# ── TC-02: contract 문서에 'OpenAPI 직접 호출하지 않는다' 명시 ────────────────


def test_contract_document_no_direct_call_stated():
    content = _CONTRACT_DOC.read_text(encoding="utf-8")
    assert "직접 호출하지 않는다" in content or "직접 호출 없음" in content


# ── TC-03: contract 문서에 'source of truth' 명시 ────────────────────────────


def test_contract_document_source_of_truth_stated():
    content = _CONTRACT_DOC.read_text(encoding="utf-8")
    assert "source of truth" in content


# ── TC-04: contract 문서에 API key 금지 명시 ──────────────────────────────────


def test_contract_document_api_key_forbidden():
    content = _CONTRACT_DOC.read_text(encoding="utf-8")
    assert "api_key" in content.lower() or "API key" in content


# ── TC-05: sample fixture 존재 및 synthetic_sample 표시 ─────────────────────


def test_sample_fixture_exists_and_synthetic():
    assert _FIXTURE_SAMPLE.exists()
    with _FIXTURE_SAMPLE.open(encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("synthetic_sample") is True


# ── TC-06: sample fixture 정책 필드 고정값 확인 ──────────────────────────────


def test_sample_fixture_policy_fields_fixed():
    with _FIXTURE_SAMPLE.open(encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("api_key_used_by_current_app") is False
    assert data.get("api_key_value_exposed") is False
    assert data.get("db_read_direct") is False
    assert data.get("db_write") is False


# ── TC-07: sample fixture에 5개 item 포함 ────────────────────────────────────


def test_sample_fixture_has_five_items():
    with _FIXTURE_SAMPLE.open(encoding="utf-8") as f:
        data = json.load(f)
    assert len(data.get("items", [])) == 5


# ── TC-08: candidates fixture 존재 및 endpoint_confirmed=false ───────────────


def test_candidates_fixture_endpoint_not_confirmed():
    assert _FIXTURE_CANDIDATES.exists()
    with _FIXTURE_CANDIDATES.open(encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("endpoint_confirmed") is False


# ── TC-09: candidates fixture 정책 필드 ──────────────────────────────────────


def test_candidates_fixture_policy_fields():
    with _FIXTURE_CANDIDATES.open(encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("api_key_used_by_current_app") is False
    assert data.get("api_key_value_exposed") is False
    assert data.get("db_read_direct") is False
    assert data.get("db_write") is False


# ── TC-10: bridge 모듈에 click/submit/download 코드 없음 ─────────────────────


def test_bridge_module_no_click_submit_download():
    src = _BRIDGE_MODULE.read_text(encoding="utf-8")
    assert "page.click(" not in src
    assert "page.submit(" not in src
    assert "expect_download" not in src
    assert "save_as(" not in src


# ── TC-11: bridge 모듈에 DB write 코드 없음 ──────────────────────────────────


def test_bridge_module_no_db_write():
    src = _BRIDGE_MODULE.read_text(encoding="utf-8")
    forbidden = ["INSERT INTO", "UPDATE ", "DELETE FROM", "DROP TABLE", "TRUNCATE"]
    for f in forbidden:
        assert f not in src, f"DB write 패턴 {f!r} 발견"


# ── TC-12: bridge 모듈에 requests/httpx 직접 호출 없음 ───────────────────────


def test_bridge_module_no_http_call():
    src = _BRIDGE_MODULE.read_text(encoding="utf-8")
    assert "requests.get" not in src
    assert "httpx.get" not in src
    assert "urlopen" not in src


# ── TC-13: bridge_verdict가 CONTENT_VALID_PASS를 포함하지 않음 ──────────────


def test_bridge_verdict_not_content_valid_pass():
    from ai_orchestrator.connectors.g2b.g2b_existing_openapi_bridge import (
        build_g2b_notice_candidates_from_existing_source,
        classify_existing_source_bridge_result,
    )

    with _FIXTURE_SAMPLE.open(encoding="utf-8") as f:
        payload = json.load(f)
    result = build_g2b_notice_candidates_from_existing_source(payload)
    classified = classify_existing_source_bridge_result(result)
    assert classified["bridge_verdict"] != "CONTENT_VALID_PASS"
    assert classified["content_valid_pass_set_by_bridge"] is False


# ── TC-14: sample fixture의 blocked URL이 safe에 없음 ────────────────────────


def test_blocked_url_not_in_safe_candidates():
    from ai_orchestrator.connectors.g2b.g2b_existing_openapi_bridge import (
        build_g2b_notice_candidates_from_existing_source,
    )

    with _FIXTURE_SAMPLE.open(encoding="utf-8") as f:
        payload = json.load(f)
    result = build_g2b_notice_candidates_from_existing_source(payload)
    safe = result["safe_detail_url_candidates"]
    blocked = result["blocked_detail_url_candidates"]
    # downloadFile.do는 safe에 없어야 함
    for url in safe:
        assert "downloadfile" not in url.lower(), f"download URL이 safe에 포함됨: {url}"
    # blocked에 있어야 함
    assert any("downloadfile" in u.lower() for u in blocked)
