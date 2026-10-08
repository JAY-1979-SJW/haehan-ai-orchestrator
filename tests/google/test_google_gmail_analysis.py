from __future__ import annotations

import json
from pathlib import Path

from scripts.google.common import gmail_analysis


def test_analyze_text_redacts_and_extracts_business_signals() -> None:
    result = gmail_analysis.analyze_text(
        subject="긴급 견적 요청 5/30까지",
        sender="client@example.com",
        body=(
            "010-1234-5678 로 연락하지 말고 이메일로 회신 요청드립니다. "
            "예상 금액은 1,200,000원이며 첨부 파일 확인 부탁드립니다."
        ),
        mail_index=2,
    )

    assert result.ok is True
    assert result.category == "quote_request"
    assert result.priority == "high"
    assert result.attachment_hint is True
    assert result.final_send_clicked is False
    assert result.attachment_downloaded is False
    assert "010-1234-5678" not in result.body_preview_redacted
    assert result.money_hints
    assert result.deadline_hints
    assert result.action_items
    assert "회신" in result.reply_draft_suggestion


def test_save_analysis_does_not_write_raw_secret(monkeypatch) -> None:
    writes: dict[str, str] = {}

    def fake_mkdir(self: Path, *args, **kwargs) -> None:
        return None

    def fake_write_text(self: Path, text: str, *args, **kwargs) -> int:
        writes[str(self)] = text
        return len(text)

    latest = Path("virtual-gmail-analysis/latest.json")
    monkeypatch.setattr(gmail_analysis, "REPORT_DIR", Path("virtual-gmail-analysis/reports"))
    monkeypatch.setattr(gmail_analysis, "LATEST_REPORT", latest)
    monkeypatch.setattr(Path, "mkdir", fake_mkdir)
    monkeypatch.setattr(Path, "write_text", fake_write_text)

    analysis = gmail_analysis.analyze_text(
        subject="Security token notice",
        sender="admin@example.com",
        body="token abc123 password value 010-9999-8888",
    )
    data, path = gmail_analysis.save_analysis(analysis)
    text = writes[str(path)]

    assert data["state_change"] is False
    assert "010-9999-8888" not in text
    assert "password" not in text.lower()
    assert "token" not in text.lower()
    assert "[redacted-sensitive]" in text
    assert json.loads(writes[str(latest)])["ok"] is True


def test_print_summary_omits_body_text(capsys) -> None:
    result = gmail_analysis.analyze_text(
        subject="견적 요청",
        sender="client@example.com",
        body="원문 본문 내용은 콘솔에 나오면 안 됩니다.",
    ).to_dict()

    gmail_analysis.print_analysis_summary(result, Path("C:\\tmp\\report.json"))

    out = capsys.readouterr().out
    assert "원문 본문 내용" not in out
    assert "category:" in out
