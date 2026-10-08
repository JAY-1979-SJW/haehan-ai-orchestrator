"""승인 게이트 5단계: 알림·재시도 판단 테스트.

검증 항목:
  1. HARD_FAIL(만료 pending) → send_message 호출
  2. WARN 조건 필터 — SOFT_WARN 코드 분류 정상
  3. alert_enabled=False → send_message 미호출
  4. retry_candidate 판단 — STORAGE_READ_FAILED=True, 나머지=False
  5. 알림 메시지 내 secret/token/path 미노출
  6. 기존 audit() 회귀 — 리팩터 후 동일 동작 보장
"""

from __future__ import annotations

import json
import sys
import unittest.mock as mock
from datetime import UTC, datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import scripts.archive.debug.audit_dev_reg_approvals as _mod  # noqa: E402
from ai_orchestrator.notify.alert_classifier import (  # noqa: E402
    AlertClassification,
    build_alert_text,
    classify,
)

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _utc(delta_seconds: float = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=delta_seconds)).isoformat()


def _make_record(
    task_id: str,
    status: str = "pending",
    expires_at: str | None = None,
    created_at: str | None = None,
    executed_at: str | None = None,
    decided_at: str | None = None,
    summary: str = "업체명=테스트",
) -> dict:
    return {
        "task_id": task_id,
        "token_id": "tok-uuid-test",
        "approval_token_hash": "HASH_MUST_NOT_APPEAR",
        "provider": "hiworks",
        "action_type": "developer_apply",
        "risk_level": "medium",
        "status": status,
        "summary": summary,
        "target_url": "https://example.com/form",
        "screenshot_path": "/secret/full/path/shot.png",
        "requested_by": "agent@test",
        "approved_by": "",
        "expires_at": expires_at or _utc(3600),
        "created_at": created_at or _utc(-60),
        "decided_at": decided_at or "",
        "executed_at": executed_at or "",
        "reject_reason": "",
        "result": "",
        "error": "",
        "telegram_message_id": "",
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── 1. HARD_FAIL → send_message 호출 ─────────────────────────────────────────


def test_hard_fail_expired_pending_triggers_alert(tmp_path, capsys):
    """만료 지난 pending → HARD_FAIL 분류 → send_message 호출."""
    store = tmp_path / "dev_reg_approvals.jsonl"
    _write_jsonl(
        store,
        [
            _make_record("dr-exp-01", status="pending", expires_at=_utc(-3600)),
        ],
    )

    with mock.patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": True}) as mock_send:
        exit_code = _mod.audit_and_alert(store_path=store, alert_enabled=True, log_run=False)

    mock_send.assert_called_once()
    call_text = mock_send.call_args[0][0]
    assert "HARD_FAIL" in call_text
    assert exit_code == 2  # audit result = WARN


def test_storage_fail_triggers_alert(tmp_path, capsys):
    """스토리지 읽기 실패 → HARD_FAIL → send_message 호출."""
    store = tmp_path / "dev_reg_approvals.jsonl"
    store.write_text("dummy\n", encoding="utf-8")

    with (
        mock.patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": True}) as mock_send,
        mock.patch.object(_mod, "_load_records", return_value=([], "PermissionError: 거부")),
    ):
        exit_code = _mod.audit_and_alert(store_path=store, alert_enabled=True, log_run=False)

    mock_send.assert_called_once()
    call_text = mock_send.call_args[0][0]
    assert "HARD_FAIL" in call_text
    assert exit_code == 3  # audit result = FAIL


# ── 2. WARN 조건 필터 — SOFT_WARN 분류 ───────────────────────────────────────


def test_soft_warn_classification_pending_overload():
    classification = classify(
        ["PENDING_OVERLOAD:pending 12건 > 허용 10건"],
        "WARN",
    )
    assert classification.alert_type == "SOFT_WARN"
    assert classification.should_notify is True
    assert classification.retry_candidate is False


def test_soft_warn_classification_no_records():
    classification = classify(
        ["NO_RECORDS:저장소가 비어있거나 파일이 존재하지 않음"],
        "WARN",
    )
    assert classification.alert_type == "SOFT_WARN"
    assert classification.should_notify is True
    assert classification.retry_candidate is False


def test_hard_fail_classification_expired_pending():
    classification = classify(
        ["EXPIRED_PENDING_EXISTS:만료 지난 pending 2건 (task_id prefix: dr-abc)"],
        "WARN",
    )
    assert classification.alert_type == "HARD_FAIL"
    assert classification.should_notify is True


def test_hard_fail_overrides_soft_warn():
    """경고 목록에 SOFT_WARN 이 먼저 있어도 HARD_FAIL 이 우선해야 한다."""
    classification = classify(
        [
            "NO_RECORDS:저장소가 비어있거나 파일이 존재하지 않음",
            "EXPIRED_PENDING_EXISTS:만료 지난 pending 1건 (task_id prefix: dr-abc)",
        ],
        "WARN",
    )
    assert classification.alert_type == "HARD_FAIL"
    assert "EXPIRED_PENDING_EXISTS" in classification.reasons


def test_pass_no_classification():
    classification = classify([], "PASS")
    assert classification.alert_type == "NONE"
    assert classification.should_notify is False
    assert classification.retry_candidate is False


# ── 3. alert_enabled=False → send_message 미호출 ─────────────────────────────


def test_alert_disabled_no_send_on_warn(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    _write_jsonl(
        store,
        [
            _make_record("dr-exp-02", status="pending", expires_at=_utc(-3600)),
        ],
    )

    with mock.patch("ai_orchestrator.core.telegram_sender.send_message") as mock_send:
        _mod.audit_and_alert(store_path=store, alert_enabled=False, log_run=False)

    mock_send.assert_not_called()


def test_alert_disabled_no_send_on_fail(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"

    with (
        mock.patch("ai_orchestrator.core.telegram_sender.send_message") as mock_send,
        mock.patch.object(_mod, "_load_records", return_value=([], "OSError: 읽기 불가")),
    ):
        _mod.audit_and_alert(store_path=store, alert_enabled=False, log_run=False)

    mock_send.assert_not_called()


# ── 4. retry_candidate 판단 ───────────────────────────────────────────────────


def test_retry_candidate_true_for_storage_fail():
    c = classify(["STORAGE_READ_FAILED:OSError: 읽기 불가"], "FAIL")
    assert c.retry_candidate is True


def test_retry_candidate_false_for_expired_pending():
    c = classify(["EXPIRED_PENDING_EXISTS:만료 지난 pending 1건 (task_id prefix: dr-abc)"], "WARN")
    assert c.retry_candidate is False


def test_retry_candidate_false_for_no_records():
    c = classify(["NO_RECORDS:저장소가 비어있거나 파일이 존재하지 않음"], "WARN")
    assert c.retry_candidate is False


def test_retry_candidate_false_for_pending_overload():
    c = classify(["PENDING_OVERLOAD:pending 15건 > 허용 10건"], "WARN")
    assert c.retry_candidate is False


def test_retry_candidate_false_for_old_pending():
    c = classify(["OLD_PENDING_EXISTS:24h 이상 경과 pending 2건"], "WARN")
    assert c.retry_candidate is False


# ── 5. 알림 메시지 민감정보 미노출 ───────────────────────────────────────────


def test_alert_text_no_sensitive_data():
    token_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"  # noqa: S105
    raw_password = "super_secret_pw_xyz"  # noqa: S105
    screenshot_full = "/home/ubuntu/data/screenshots/shot.png"

    c = AlertClassification(
        alert_type="HARD_FAIL",
        should_notify=True,
        retry_candidate=False,
        reasons=["EXPIRED_PENDING_EXISTS"],
    )
    text = build_alert_text(
        c,
        pending_count=2,
        expired_pending_count=1,
        recent_executed=0,
        recent_failed=0,
        audit_time="2026-04-24T10:00:00Z",
    )

    assert token_hash not in text
    assert raw_password not in text
    assert screenshot_full not in text
    # 코드명·숫자·타임스탬프만 포함
    assert "EXPIRED_PENDING_EXISTS" in text
    assert "HARD_FAIL" in text
    assert "2026-04-24T10:00:00Z" in text
    assert "pending_count      : 2" in text


def test_alert_text_no_token_keyword():
    """알림 메시지 내 token/password/cookie 원문값 미포함."""
    c = AlertClassification("SOFT_WARN", True, False, ["NO_RECORDS"])
    text = build_alert_text(
        c,
        pending_count=0,
        expired_pending_count=0,
        recent_executed=0,
        recent_failed=0,
        audit_time="2026-04-24T10:00:00Z",
    )
    # 코드명 "token" 이 경고 reasons 에 없으므로 text에도 없어야 함
    assert "super_secret" not in text
    assert "password=" not in text
    assert "cookie=" not in text


# ── 6. 기존 audit() 회귀 보장 ────────────────────────────────────────────────


def test_regression_pass(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    _write_jsonl(
        store,
        [
            _make_record("dr-r01", status="executed", executed_at=_utc(-1800), decided_at=_utc(-1800)),
        ],
    )
    code = _mod.audit(store_path=store)
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip().splitlines()[-1] == "RESULT: PASS"


def test_regression_warn_expired(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    _write_jsonl(
        store,
        [
            _make_record("dr-r02", status="pending", expires_at=_utc(-7200)),
        ],
    )
    code = _mod.audit(store_path=store)
    out = capsys.readouterr().out
    assert code == 2
    assert "RESULT: WARN" in out
    assert "EXPIRED_PENDING_EXISTS" in out


def test_regression_warn_empty(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    code = _mod.audit(store_path=store)
    out = capsys.readouterr().out
    assert code == 2
    assert "RESULT: WARN" in out
    assert "NO_RECORDS" in out


def test_regression_fail_read_error(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    store.write_text("dummy\n", encoding="utf-8")
    with mock.patch("builtins.open", side_effect=PermissionError("접근 거부")):
        code = _mod.audit(store_path=store)
    out = capsys.readouterr().out
    assert code == 3
    assert "RESULT: FAIL" in out
    assert "STORAGE_READ_FAILED" in out


def test_regression_result_last_line(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    _write_jsonl(
        store,
        [
            _make_record("dr-r03", status="executed", executed_at=_utc(-100), decided_at=_utc(-100)),
        ],
    )
    _mod.audit(store_path=store)
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1].startswith("RESULT:")


def test_regression_no_sensitive_in_output(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    _write_jsonl(
        store,
        [
            {
                **_make_record("dr-r04", status="executed", executed_at=_utc(-60), decided_at=_utc(-60)),
                "approval_token_hash": "DEADBEEF" * 8,
                "screenshot_path": "/secret/path/shot.png",
            }
        ],
    )
    _mod.audit(store_path=store)
    out = capsys.readouterr().out
    assert "DEADBEEF" not in out
    assert "/secret/path/shot.png" not in out


# ── 실행 로그 기록 검증 ───────────────────────────────────────────────────────


def test_run_log_written_with_alert_fields(tmp_path, capsys):
    """audit_and_alert() 가 실행 로그에 alert_sent·alert_type·retry_candidate 를 기록한다."""
    from ai_orchestrator.dev_reg.dev_reg_audit_log import load_recent_runs

    store = tmp_path / "dev_reg_approvals.jsonl"
    log_path = tmp_path / "dev_reg_audit_runs.jsonl"
    _write_jsonl(
        store,
        [
            _make_record("dr-log-01", status="executed", executed_at=_utc(-300), decided_at=_utc(-300)),
        ],
    )

    with mock.patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": True}):
        _mod.audit_and_alert(store_path=store, alert_enabled=False, log_run=True, audit_log_path=log_path)

    runs = load_recent_runs(1, path=log_path)
    assert len(runs) == 1
    run = runs[0]
    assert "alert_sent" in run
    assert "alert_type" in run
    assert "retry_candidate" in run
    assert run["result"] == "PASS"
    assert run["alert_sent"] is False
    assert run["alert_type"] == "NONE"
    assert run["retry_candidate"] is False


def test_run_log_no_sensitive_fields(tmp_path, capsys):
    """실행 로그에 민감 필드(approval_token_hash 등)가 저장되지 않는다."""

    store = tmp_path / "dev_reg_approvals.jsonl"
    log_path = tmp_path / "dev_reg_audit_runs.jsonl"
    _write_jsonl(
        store,
        [
            {
                **_make_record("dr-log-02", status="pending"),
                "approval_token_hash": "SENSITIVE_HASH",
            }
        ],
    )

    with mock.patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": True}):
        _mod.audit_and_alert(store_path=store, alert_enabled=False, log_run=True, audit_log_path=log_path)

    with log_path.open(encoding="utf-8") as f:
        content = f.read()

    assert "SENSITIVE_HASH" not in content
    assert "approval_token_hash" not in content
