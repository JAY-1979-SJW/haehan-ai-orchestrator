"""tests/test_phase1_actions_20260508.py

1차 구현 액션 통합 검증.
Playwright 실제 호출은 mock — 외부 사이트 접속 없음.
"""

import pytest

from ai_orchestrator.agent_hub.action_registry import get_handler
from ai_orchestrator.agent_hub.actions import browser_attach_file, browser_download_file, future_action_stubs
from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    approve_request,
    clear_all,
    create_approval_request,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    yield
    clear_all()


# ── browser.download_file ────────────────────────────────────────────────


def test_download_file_handler_registered():
    h = get_handler("browser.download_file")
    assert h is not None
    assert callable(h)


def test_download_file_empty_url_returns_error():
    r = browser_download_file.execute(source_url="", out_dir="/tmp")
    assert r["ok"] is False
    assert r["verdict"] == "ERROR"


def test_file_signature_hwp_ole2(tmp_path):
    f = tmp_path / "test.hwp"
    f.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 100)
    sig = browser_download_file._file_signature(str(f))
    assert sig == "HWP_OLE2"


def test_file_signature_zip_hwpx(tmp_path):
    f = tmp_path / "test.hwpx"
    f.write_bytes(b"PK\x03\x04" + b"x" * 100)
    sig = browser_download_file._file_signature(str(f))
    assert sig == "ZIP_OR_HWPX"


def test_file_signature_pdf(tmp_path):
    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF-1.4\n" + b"x" * 100)
    sig = browser_download_file._file_signature(str(f))
    assert sig == "PDF"


def test_file_signature_html(tmp_path):
    f = tmp_path / "test.html"
    f.write_bytes(b"<!DOCTYPE html>\n<html>...")
    sig = browser_download_file._file_signature(str(f))
    assert sig == "HTML_RESPONSE"


def test_file_signature_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_bytes(b"")
    sig = browser_download_file._file_signature(str(f))
    assert sig == "EMPTY"


def test_file_signature_missing():
    sig = browser_download_file._file_signature("/nonexistent/path.xyz")
    assert sig == "MISSING"


# ── browser.attach_file ──────────────────────────────────────────────────


def test_attach_file_handler_registered():
    h = get_handler("browser.attach_file")
    assert h is not None


def test_attach_file_nonexistent_path():
    r = browser_attach_file.execute(
        page_url="https://e.com",
        file_path="/nonexistent/path.pdf",
        form_field_label="첨부",
        approval_token="any",
    )
    assert r["ok"] is False
    assert r["verdict"] == "ERROR"


def test_attach_file_invalid_token(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-x")
    r = browser_attach_file.execute(
        page_url="https://e.com",
        file_path=str(f),
        form_field_label="첨부",
        approval_token="invalid_token_xxx",
    )
    assert r["ok"] is False
    assert r["verdict"] == "APPROVAL_REJECTED"


def test_attach_file_token_consumed_once(tmp_path):
    """승인된 토큰은 한 번만 사용 가능 (실제 attach는 mock으로 검증)."""
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-x")
    file_name = f.name
    params = {
        "page_url": "https://e.com",
        "file_name": file_name,
        "form_field_label": "첨부",
    }
    req = create_approval_request("browser.attach_file", params, {})
    appr = approve_request(req["request_id"], "u")
    token = appr["approval_token"]

    # 토큰 검증 함수 직접 호출 — 1회 사용 후 EXHAUSTED
    from ai_orchestrator.agent_hub.policy.user_approval_gate import verify_and_consume_token

    v1 = verify_and_consume_token(token, "browser.attach_file", params)
    assert v1["ok"] is True
    v2 = verify_and_consume_token(token, "browser.attach_file", params)
    assert v2["ok"] is False


# ── future stubs ─────────────────────────────────────────────────────────


def test_future_actions_have_no_handler():
    """미구현 액션은 핸들러 미등록."""
    for name in future_action_stubs.PENDING_ACTIONS:
        assert get_handler(name) is None, f"{name}에 핸들러가 등록됨 (미구현이어야 함)"


def test_stub_response_shape():
    r = future_action_stubs.stub_not_implemented("bid.submit_with_user_approval")
    assert r["ok"] is False
    assert r["verdict"] == "ACTION_NOT_IMPLEMENTED"
    assert r["implemented"] is False
    # safe field 모두 False
    for f in (
        "cookie_exported",
        "session_exported",
        "password_collected",
        "otp_collected",
        "certificate_password_collected",
        "storage_state_exported",
        "server_browser_used",
    ):
        assert r[f] is False


def test_pending_actions_count_four():
    assert len(future_action_stubs.PENDING_ACTIONS) == 4
