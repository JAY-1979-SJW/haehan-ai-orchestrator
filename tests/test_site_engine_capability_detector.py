"""Unit tests for scripts.site_engine.capability_detector."""

from typing import Any

from scripts.site_engine.capability_detector import (
    CapabilityDetectionInput,
    detect_capabilities_from_snapshot,
)
from scripts.site_engine.site_types import GateDecision, SiteCapability


def _inp(**kwargs) -> CapabilityDetectionInput:
    defaults: dict[str, Any] = {
        "page_url": "https://example.com",
        "page_title": "",
        "button_labels": [],
        "input_types": [],
        "has_file_input": False,
        "has_form": False,
        "has_table": False,
        "has_search_input": False,
        "page_text_snippet": "",
    }
    defaults.update(kwargs)
    return CapabilityDetectionInput(**defaults)


def test_read_always_detected():
    result = detect_capabilities_from_snapshot(_inp())
    assert SiteCapability.READ in result.detected_set


def test_search_detected_with_search_input():
    result = detect_capabilities_from_snapshot(_inp(has_search_input=True))
    assert SiteCapability.SEARCH in result.detected_set


def test_form_fill_detected_with_form():
    result = detect_capabilities_from_snapshot(_inp(has_form=True))
    assert SiteCapability.FORM_FILL in result.detected_set


def test_submit_detected_by_button_label():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["저장", "확인"]))
    assert SiteCapability.SUBMIT in result.detected_set


def test_send_detected_by_button_label():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["메일 보내기"]))
    assert SiteCapability.SEND in result.detected_set


def test_delete_detected_by_button_label():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["삭제"]))
    assert SiteCapability.DELETE in result.detected_set


def test_sign_detected_by_button_label():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["전자서명"]))
    assert SiteCapability.SIGN in result.detected_set


def test_upload_detected_with_file_input():
    result = detect_capabilities_from_snapshot(_inp(has_file_input=True))
    assert SiteCapability.UPLOAD in result.detected_set


def test_download_detected_by_button_label():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["다운로드"]))
    assert SiteCapability.DOWNLOAD in result.detected_set


def test_login_required_detected():
    result = detect_capabilities_from_snapshot(_inp(page_text_snippet="로그인 후 이용하실 수 있습니다"))
    assert result.login_required


def test_user_direct_required_for_sign():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["전자서명"]))
    assert result.user_direct_required


def test_submit_requires_approval():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["상신"]))
    submit_cap = next(c for c in result.capabilities if c.capability == SiteCapability.SUBMIT)
    assert submit_cap.requires_approval
    assert submit_cap.required_gate == GateDecision.APPROVAL_REQUIRED


def test_publish_requires_approval():
    result = detect_capabilities_from_snapshot(_inp(button_labels=["게시", "발행"]))
    assert SiteCapability.PUBLISH in result.detected_set
    pub = next(c for c in result.capabilities if c.capability == SiteCapability.PUBLISH)
    assert pub.requires_approval


def test_no_browser_execution():
    # snapshot 기반 — 외부 접속 없음을 smoke로 확인
    result = detect_capabilities_from_snapshot(_inp(page_url="https://bank.gov.kr"))
    assert result is not None


def test_no_unknown_capabilities_without_evidence():
    result = detect_capabilities_from_snapshot(_inp())
    # 증거 없이는 SUBMIT/DELETE/SEND 등 감지 안 됨
    assert SiteCapability.SUBMIT not in result.detected_set
    assert SiteCapability.DELETE not in result.detected_set
    assert SiteCapability.SEND not in result.detected_set


def test_execution_gate_import_no_conflict():
    from scripts.site_engine.execution_gate import GateDecision as GD
    from scripts.site_engine.site_types import GateDecision as GD2

    assert GD is GD2
