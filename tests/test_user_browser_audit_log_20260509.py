"""user_browser_audit_log 단위 테스트."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from ai_orchestrator.local_agent.user_browser_audit_log import (
    log_action, read_log, summarize_log, mask_sensitive_data,
    get_audit_path,
)


def test_mask_password_key():
    masked = mask_sensitive_data({"username": "alice", "password": "s3cret"})
    assert masked["username"] == "alice"
    assert masked["password"] == "[REDACTED]"


def test_mask_api_key_variants():
    masked = mask_sensitive_data({
        "api_key": "abc",
        "apiKey": "def",
        "ACCESS_TOKEN": "xyz",
    })
    assert masked["api_key"] == "[REDACTED]"
    assert masked["apiKey"] == "[REDACTED]"
    assert masked["ACCESS_TOKEN"] == "[REDACTED]"


def test_mask_korean_sensitive_keys():
    masked = mask_sensitive_data({"주민번호": "900101-1234567", "계좌": "12345"})
    assert masked["주민번호"] == "[REDACTED]"
    assert masked["계좌"] == "[REDACTED]"


def test_mask_rrn_in_value():
    masked = mask_sensitive_data({"note": "주민번호는 900101-1234567 입니다"})
    assert "[RRN_REDACTED]" in masked["note"]
    assert "900101-1234567" not in masked["note"]


def test_mask_card_in_value():
    masked = mask_sensitive_data({"note": "카드 1234-5678-9012-3456"})
    assert "[CARD_REDACTED]" in masked["note"]


def test_mask_nested_dict():
    masked = mask_sensitive_data({
        "outer": {"password": "x", "name": "alice"},
    })
    assert masked["outer"]["password"] == "[REDACTED]"
    assert masked["outer"]["name"] == "alice"


def test_mask_list_of_dicts():
    masked = mask_sensitive_data({
        "items": [{"token": "a"}, {"token": "b"}],
    })
    assert masked["items"][0]["token"] == "[REDACTED]"
    assert masked["items"][1]["token"] == "[REDACTED]"


def test_log_action_creates_jsonl(tmp_path):
    path = tmp_path / "log.jsonl"
    entry = log_action("navigate", url="https://example.com", audit_path=path)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["action"] == "navigate"
    assert parsed["url"] == "https://example.com"
    assert "ts" in parsed


def test_log_action_appends(tmp_path):
    path = tmp_path / "log.jsonl"
    log_action("a", url="u1", audit_path=path)
    log_action("b", url="u2", audit_path=path)
    log_action("c", url="u3", audit_path=path)
    entries = read_log(audit_path=path)
    assert len(entries) == 3
    assert [e["action"] for e in entries] == ["a", "b", "c"]


def test_log_action_masks_params(tmp_path):
    path = tmp_path / "log.jsonl"
    log_action("type", params={"username": "alice", "password": "s3cret"},
               audit_path=path)
    entries = read_log(audit_path=path)
    assert entries[0]["params"]["password"] == "[REDACTED]"
    assert entries[0]["params"]["username"] == "alice"


def test_log_action_truncates_long_url(tmp_path):
    path = tmp_path / "log.jsonl"
    long_url = "https://example.com/" + "a" * 1000
    log_action("navigate", url=long_url, audit_path=path)
    entries = read_log(audit_path=path)
    assert len(entries[0]["url"]) <= 500


def test_log_action_with_risk_level_and_approval(tmp_path):
    path = tmp_path / "log.jsonl"
    log_action("submit", url="u", risk_level="APPROVE",
               approval_id="ap_123", audit_path=path)
    entries = read_log(audit_path=path)
    assert entries[0]["risk_level"] == "APPROVE"
    assert entries[0]["approval_id"] == "ap_123"


def test_summarize_log(tmp_path):
    path = tmp_path / "log.jsonl"
    log_action("navigate", url="u1", audit_path=path)
    log_action("navigate", url="u2", audit_path=path)
    log_action("click", url="u3", risk_level="NOTIFY", audit_path=path)
    log_action("submit", url="u4", risk_level="APPROVE", result="approved",
               audit_path=path)
    summary = summarize_log(audit_path=path)
    assert summary["total"] == 4
    assert summary["by_action"]["navigate"] == 2
    assert summary["by_action"]["click"] == 1
    assert summary["by_action"]["submit"] == 1
    assert summary["by_risk_level"]["AUTO"] == 2  # navigate 기본값
    assert summary["by_risk_level"]["APPROVE"] == 1
    assert summary["by_risk_level"]["NOTIFY"] == 1


def test_read_log_missing_file():
    entries = read_log(audit_path=Path("/nonexistent/file.jsonl"))
    assert entries == []


def test_get_audit_path_format():
    path = get_audit_path(date="20260509")
    assert path.name == "user_browser_cdp_20260509.jsonl"
    assert path.parent.name == "audit"


def test_log_action_with_error(tmp_path):
    path = tmp_path / "log.jsonl"
    log_action("click", url="u", result="error",
               error="element not found", audit_path=path)
    entries = read_log(audit_path=path)
    assert entries[0]["result"] == "error"
    assert entries[0]["error"] == "element not found"
