"""tools/audits/backend/audit_log_sensitive_scan.py 시험 — 가짜 로그로 건수·값 미출력·재작성 원자성 확인."""

from __future__ import annotations

import json
from pathlib import Path

from tools.audits.backend.audit_log_sensitive_scan import (
    Finding,
    main,
    rewrite_file,
    rotated_siblings,
    scan_file,
    scan_line,
)

FAKE_RRN = "901010-1234567"
FAKE_CARD = "1234-5678-9012-3456"
FAKE_JWT = "eyJ" + "a" * 20 + ".eyJ" + "a" * 20 + "." + "a" * 20
FAKE_OPENAI_KEY = "sk-" + "a" * 30
FAKE_TOKEN_ID = "tok_abc123"


def _write_log(path: Path, lines: list[dict | str]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            if isinstance(line, str):
                f.write(line + "\n")
            else:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")


def test_scan_line_finds_sensitive_key_without_value():
    findings = scan_line(1, json.dumps({"password": "real-secret-value"}))
    assert findings == [Finding(1, "password", "SENSITIVE_KEY:password")]


def test_scan_line_finds_value_pattern_in_non_sensitive_field():
    findings = scan_line(1, json.dumps({"note": f"token leaked: {FAKE_OPENAI_KEY}"}))
    assert any(f.rule == "OPENAI_KEY" for f in findings)


def test_scan_line_finds_rrn_and_card():
    findings = scan_line(1, json.dumps({"note": f"{FAKE_RRN} {FAKE_CARD}"}))
    rules = {f.rule for f in findings}
    assert "RRN" in rules
    assert "CARD" in rules


def test_scan_line_identifier_fields_not_flagged():
    findings = scan_line(1, json.dumps({"task_id": "T-001", "actor": "owner@example.com", "token_id": FAKE_TOKEN_ID}))
    # token_id는 민감 키("token" 부분일치)라 걸리지만 값은 안 담긴다
    assert all(f.field != "actor" for f in findings)
    assert all(f.field != "task_id" for f in findings)


def test_findings_never_contain_actual_value(tmp_path):
    """핵심 요구사항: 보고서 어디에도 실제 값이 들어가면 안 된다."""
    findings = scan_line(1, json.dumps({"note": f"secret={FAKE_OPENAI_KEY}"}))
    for f in findings:
        assert FAKE_OPENAI_KEY not in f.field
        assert FAKE_OPENAI_KEY not in f.rule


def test_scan_file_counts_across_lines(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    _write_log(
        log,
        [
            {"event_type": "LOGIN", "note": "ok"},
            {"event_type": "SIGNUP", "password": "hunter2"},
            {"event_type": "LEAK", "note": f"card {FAKE_CARD}"},
        ],
    )
    findings = scan_file(log)
    assert len(findings) == 2
    assert {f.line for f in findings} == {2, 3}


def test_non_json_line_scanned_as_freeform(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    _write_log(log, [f"plain text line with token {FAKE_OPENAI_KEY}"])
    findings = scan_file(log)
    assert len(findings) == 1
    assert findings[0].field == "(freeform line)"


def test_empty_lines_ignored(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    log.write_text("\n\n", encoding="utf-8")
    assert scan_file(log) == []


def test_rotated_siblings_discovered(tmp_path):
    base = tmp_path / "audit_logs.jsonl"
    base.write_text("{}\n", encoding="utf-8")
    (tmp_path / "audit_logs.jsonl.1").write_text("{}\n", encoding="utf-8")
    (tmp_path / "audit_logs.jsonl.2").write_text("{}\n", encoding="utf-8")
    siblings = rotated_siblings(base)
    assert [p.name for p in siblings] == ["audit_logs.jsonl", "audit_logs.jsonl.1", "audit_logs.jsonl.2"]


def test_rewrite_creates_backup_with_original_content(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    original_lines = [{"event_type": "SIGNUP", "password": "hunter2"}]
    _write_log(log, original_lines)
    original_bytes = log.read_bytes()

    backup = rewrite_file(log)

    assert backup.exists()
    assert backup.read_bytes() == original_bytes


def test_rewrite_masks_sensitive_key_and_keeps_identifiers(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    _write_log(log, [{"task_id": "T-001", "actor": "owner@example.com", "password": "hunter2"}])

    rewrite_file(log)

    rewritten = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert rewritten["password"] == "***"
    assert rewritten["task_id"] == "T-001"  # 식별 필드는 보존


def test_rewrite_masks_value_pattern_in_freeform_line(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    log.write_text(f"plain line {FAKE_OPENAI_KEY}\n", encoding="utf-8")

    rewrite_file(log)

    rewritten = log.read_text(encoding="utf-8")
    assert FAKE_OPENAI_KEY not in rewritten
    assert "[TOKEN_REDACTED]" in rewritten


def test_rewrite_no_tmp_file_left_behind(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    _write_log(log, [{"password": "hunter2"}])

    rewrite_file(log)

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


def test_main_readonly_does_not_modify_file(tmp_path, capsys):
    log = tmp_path / "audit_logs.jsonl"
    _write_log(log, [{"password": "hunter2"}])
    original = log.read_bytes()

    rc = main([str(log)])

    assert log.read_bytes() == original  # 기본은 읽기만
    assert rc == 1  # 발견 있으면 0이 아닌 코드
    out = capsys.readouterr().out
    assert "hunter2" not in out  # 출력에 실제 값이 없어야 함


def test_main_rewrite_flag_triggers_backup(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    _write_log(log, [{"password": "hunter2"}])

    rc = main([str(log), "--rewrite"])

    assert rc == 1
    backups = list(tmp_path.glob("audit_logs.jsonl.bak-*"))
    assert len(backups) == 1


def test_main_clean_file_returns_zero(tmp_path):
    log = tmp_path / "audit_logs.jsonl"
    _write_log(log, [{"event_type": "LOGIN", "task_id": "T-001"}])

    rc = main([str(log)])

    assert rc == 0


def test_main_missing_file_reports_error(tmp_path, capsys):
    rc = main([str(tmp_path / "does-not-exist.jsonl")])
    assert rc == 2
