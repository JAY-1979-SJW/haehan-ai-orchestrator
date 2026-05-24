from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.google import gmail_analysis


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
    temp_dir = Path(tempfile.mkdtemp(prefix="gmail-analysis-test-", dir="C:\\tmp"))
    monkeypatch.setattr(gmail_analysis, "REPORT_DIR", temp_dir)
    monkeypatch.setattr(gmail_analysis, "LATEST_REPORT", temp_dir / "latest.json")

    analysis = gmail_analysis.analyze_text(
        subject="Security token notice",
        sender="admin@example.com",
        body="token abc123 password value 010-9999-8888",
    )
    data, path = gmail_analysis.save_analysis(analysis)
    text = path.read_text(encoding="utf-8")

    assert data["state_change"] is False
    assert "010-9999-8888" not in text
    assert "password" not in text.lower()
    assert "token" not in text.lower()
    assert "[redacted-sensitive]" in text
    assert json.loads((temp_dir / "latest.json").read_text(encoding="utf-8"))["ok"] is True


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
