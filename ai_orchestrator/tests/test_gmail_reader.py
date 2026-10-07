import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))

import ai_orchestrator.connectors.google.gmail_reader as gr
from ai_orchestrator.tasks.inbox import exists_by_external_id


def _fake_msg(message_id: str, subject: str = "테스트 메일", body: str = "본문 내용") -> dict:
    """Gmail API 응답 형태의 가짜 메시지."""
    import base64

    body_b64 = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return {
        "id": message_id,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 01 Jan 2024 12:00:00 +0000"},
            ],
            "body": {"data": body_b64},
            "parts": [],
        },
    }


# ── 1. 이메일 → inbox 저장 ────────────────────────────────────────────
def test_collect_saves_email_to_inbox():
    msg_id = f"gmail-{uuid.uuid4().hex[:12]}"
    fake_msg = _fake_msg(msg_id, subject="저장 테스트")

    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {"messages": [{"id": msg_id}]}
    mock_service.users().messages().get().execute.return_value = fake_msg

    with patch.object(gr, "_get_service", return_value=mock_service):
        result = gr.collect_to_inbox(max_results=10, hours=1)

    assert result["saved"] == 1
    assert result["total"] == 1
    assert exists_by_external_id(msg_id, source_type="email")


# ── 2. 중복 message_id skip ──────────────────────────────────────────
def test_collect_skips_duplicate_message_id():
    msg_id = f"gmail-dup-{uuid.uuid4().hex[:12]}"
    fake_msg = _fake_msg(msg_id, subject="중복 방지 테스트")

    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {"messages": [{"id": msg_id}]}
    mock_service.users().messages().get().execute.return_value = fake_msg

    with patch.object(gr, "_get_service", return_value=mock_service):
        result1 = gr.collect_to_inbox(max_results=10, hours=1)
        result2 = gr.collect_to_inbox(max_results=10, hours=1)

    assert result1["saved"] == 1
    assert result2["saved"] == 0
    assert result2["skipped"] == 1


# ── 3. 빈 inbox — 메시지 없음 ────────────────────────────────────────
def test_collect_empty_when_no_messages():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {"messages": []}

    with patch.object(gr, "_get_service", return_value=mock_service):
        result = gr.collect_to_inbox(max_results=10, hours=1)

    assert result["saved"] == 0
    assert result["total"] == 0


# ── 4. credentials 없을 때 빈 리스트 반환 ────────────────────────────
def test_fetch_returns_empty_on_missing_credentials():
    with patch.object(gr, "_get_service", side_effect=FileNotFoundError("credentials 없음")):
        emails = gr.fetch_recent_emails()
    assert emails == []


# ── 5. _parse_message — 필드 누락 방어 ───────────────────────────────
def test_parse_message_missing_headers():
    msg = {"id": "test-id-missing", "payload": {"headers": [], "mimeType": "text/plain", "body": {}, "parts": []}}
    parsed = gr._parse_message(msg)
    assert parsed is not None
    assert parsed["message_id"] == "test-id-missing"
    assert parsed["from"] == ""
    assert parsed["subject"] == "(no subject)"


# ── 6. _parse_message — message_id 없으면 None ───────────────────────
def test_parse_message_no_id_returns_none():
    msg = {"payload": {"headers": []}}
    result = gr._parse_message(msg)
    assert result is None


# ── 7. _extract_body — multipart 재귀 추출 ───────────────────────────
def test_extract_body_multipart():
    import base64

    body_text = "멀티파트 본문"
    body_b64 = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")
    payload = {
        "mimeType": "multipart/mixed",
        "body": {},
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": base64.urlsafe_b64encode(b"<p>html</p>").decode().rstrip("=")},
                "parts": [],
            },
            {
                "mimeType": "text/plain",
                "body": {"data": body_b64},
                "parts": [],
            },
        ],
    }
    result = gr._extract_body(payload)
    assert body_text in result


if __name__ == "__main__":
    tests = [
        test_collect_saves_email_to_inbox,
        test_collect_skips_duplicate_message_id,
        test_collect_empty_when_no_messages,
        test_fetch_returns_empty_on_missing_credentials,
        test_parse_message_missing_headers,
        test_parse_message_no_id_returns_none,
        test_extract_body_multipart,
    ]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print("\n모든 gmail_reader 테스트 통과")
