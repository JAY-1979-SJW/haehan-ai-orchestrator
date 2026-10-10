"""tests/test_action_summary_and_evidence_20260508.py"""

from ai_orchestrator.agent_hub.action_evidence_collector import (
    check_evidence_no_sensitive,
    collect_evidence,
)
from ai_orchestrator.agent_hub.action_summary_builder import (
    build_action_summary,
    format_summary_for_display,
)

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]


# ── summary builder ──────────────────────────────────────────────────────


def test_summary_unknown_action():
    r = build_action_summary("nonexistent.action", {})
    assert r.get("error") == "UNKNOWN_ACTION"


def test_summary_download_file():
    r = build_action_summary(
        "browser.download_file",
        {
            "source_url": "https://example.com/path/file.hwpx?token=secret123",
            "expected_filename": "/some/dir/file.hwpx",
            "password": "should_not_appear",
        },
    )
    s = r["summary"]
    assert "secret123" not in s["source_url_safe"]
    assert s["expected_filename"] == "file.hwpx"
    assert "password" not in s


def test_summary_attach_file():
    r = build_action_summary(
        "browser.attach_file",
        {
            "url": "https://forms.example.com/upload",
            "file_name": "C:\\path\\to\\report.pdf",
            "form_field_label": "첨부파일",
            "file_size": 12345,
            "expected_result": "form 상태 변경",
            "password": "x",  # 무시되어야 함
        },
    )
    s = r["summary"]
    assert s["site"] == "forms.example.com"
    assert s["file_name"] == "report.pdf"
    assert s["form_field_label"] == "첨부파일"
    assert s["file_size"] == 12345
    assert "password" not in s


def test_summary_submit_with_user_approval_fields():
    r = build_action_summary(
        "browser.submit_with_user_approval",
        {
            "url": "https://bid.example.com/submit",
            "notice_no": "R26BK01462524",
            "file_name": "submit.pdf",
            "amount": 50000000,
            "company": "한컴",
            "account_id": "user01@example.com",
            "expected_result": "접수번호 발급",
            "password": "should_not_appear",
            "cert_password": "also_no",
        },
    )
    s = r["summary"]
    assert s["notice_no"] == "R26BK01462524"
    assert s["amount"] == 50000000
    assert s["company"] == "한컴"
    assert s["account"] == "user01@example.com"
    assert "password" not in s
    assert "cert_password" not in s


def test_summary_bid_submit_fields():
    r = build_action_summary(
        "bid.submit_with_user_approval",
        {
            "url": "https://www.g2b.go.kr/",
            "notice_no": "R26BK01999999",
            "bid_amount": 1234567890,
            "company": "한컴엔지니어링",
            "deadline": "2026-06-01T17:00",
        },
    )
    s = r["summary"]
    assert s["bid_amount"] == 1234567890
    assert s["deadline"] == "2026-06-01T17:00"


def test_summary_esign_signer_info_strips_sensitive():
    r = build_action_summary(
        "esign.execute_with_user_approval",
        {
            "url": "https://signing.example.com/",
            "document_name": "/path/contract.pdf",
            "document_hash": "a" * 64,
            "signer_info": {
                "subject_name": "한컴",
                "serial_number": "9999999",  # 노출되면 안 됨
                "private_key": "secret",  # 절대
            },
            "purpose": "계약 서명",
        },
    )
    s = r["summary"]
    assert s["document_name"] == "contract.pdf"
    assert "..." in s["document_hash_safe"]
    assert "subject_name" in s["signer_info_safe"]
    assert "serial_number" not in s["signer_info_safe"]
    assert "private_key" not in s["signer_info_safe"]


def test_summary_format_display():
    r = build_action_summary(
        "browser.attach_file",
        {
            "url": "https://e.com",
            "file_name": "a.pdf",
        },
    )
    text = format_summary_for_display(r)
    assert "browser.attach_file" in text
    assert "위험 등급" in text


# ── evidence collector ──────────────────────────────────────────────────


def test_evidence_unknown_action():
    e = collect_evidence("nonexistent.action", {})
    assert e.get("error") == "UNKNOWN_ACTION"


def test_evidence_download_file_safe_fields():
    e = collect_evidence(
        "browser.download_file",
        {
            "saved_path": "C:\\Users\\test\\Downloads\\file.hwpx",
            "file_size": 12345,
            "signature": "ZIP_OR_HWPX",
            "downloaded_at": "2026-05-08T22:00:00Z",
        },
    )
    # 파일명만 노출
    assert e["saved_safe_path"] == "file.hwpx"
    assert e["file_size"] == 12345
    assert e["signature"] == "ZIP_OR_HWPX"
    for f in _SAFE_FIELDS:
        assert e[f] is False


def test_evidence_attach_file_redacts_form_state():
    e = collect_evidence(
        "browser.attach_file",
        {
            "attached_file_name": "a.pdf",
            "attached_at": "2026-05-08T22:00:00Z",
            "form_state_after": {
                "field_label": "첨부",
                "filled": True,
                "password": "should_not_appear",  # redact
                "cookie_value": "c",  # redact
            },
        },
    )
    fs = e["form_state_after"]
    assert "password" not in fs
    assert "cookie_value" not in fs
    assert fs.get("filled") is True


def test_evidence_submit_with_screenshot_path_safe():
    e = collect_evidence(
        "browser.submit_with_user_approval",
        {
            "submission_status": "RECEIVED",
            "receipt_no": "RC-2026-0001",
            "submitted_at": "2026-05-08T22:30:00Z",
            "result_screen": "접수번호 RC-2026-0001 발급됨",
        },
        screenshot_path="C:\\Users\\skyjw\\screenshots\\submit_evidence.png",
    )
    assert e["screenshot_path_safe"] == "submit_evidence.png"
    assert "C:\\" not in e["screenshot_path_safe"]
    assert "접수번호" in e["result_screen_safe"]


def test_evidence_esign_redacts_cert():
    e = collect_evidence(
        "esign.execute_with_user_approval",
        {
            "signature_status": "SIGNED",
            "signed_at": "2026-05-08T22:00:00Z",
            "document_hash": "a" * 64,
            "signer_info": {"subject_name": "한컴", "serial_number": "9999"},
            "private_key": "secret",  # redact
            "cert_password": "x",  # redact
        },
    )
    assert "private_key" not in e
    assert "cert_password" not in e
    assert e["signer_info_safe"] == {"subject_name": "한컴"}


def test_check_no_sensitive_clean():
    e = collect_evidence("browser.download_file", {"saved_path": "x.pdf", "file_size": 1})
    assert check_evidence_no_sensitive(e) == []


def test_check_detects_safe_field_violation():
    e = collect_evidence("browser.download_file", {"saved_path": "x.pdf"})
    e["server_browser_used"] = True
    v = check_evidence_no_sensitive(e)
    assert any("server_browser_used" in s for s in v)


def test_check_detects_sensitive_key_remnant():
    e = collect_evidence("browser.download_file", {"saved_path": "x.pdf"})
    # 주입 시도
    e["password"] = "x"
    v = check_evidence_no_sensitive(e)
    assert any("password" in s for s in v)
