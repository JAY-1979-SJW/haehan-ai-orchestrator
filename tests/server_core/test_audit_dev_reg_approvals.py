"""audit_dev_reg_approvals.py 테스트.

검증 항목:
  1. 정상 저장소 → PASS
  2. 만료 지난 pending → WARN
  3. 빈 저장소(파일 없음) → WARN
  4. 읽기 실패(PermissionError) → FAIL / exit code 3
  5. RESULT 라인 출력 확인
  6. 민감정보 미노출 (approval_token_hash, screenshot_path 전체 경로, password 등)
"""

from __future__ import annotations

import json
import sys
import unittest.mock as mock
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import scripts.archive.debug.audit_dev_reg_approvals as _mod  # noqa: E402

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
        "token_id": "tok-uuid-1234",
        "approval_token_hash": "SHOULD_NOT_APPEAR_IN_OUTPUT",
        "provider": "hiworks",
        "action_type": "developer_apply",
        "risk_level": "medium",
        "status": status,
        "summary": summary,
        "target_url": "https://example.com/form",
        "screenshot_path": "/var/data/screenshots/shot.png",
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


# ── 테스트 1: 정상 저장소 → PASS ─────────────────────────────────────────────


def test_pass_normal_store(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    records = [
        _make_record("dr-001", status="executed", executed_at=_utc(-3600), decided_at=_utc(-3600)),
        _make_record("dr-002", status="pending", expires_at=_utc(7200), created_at=_utc(-120)),
    ]
    _write_jsonl(store, records)

    exit_code = _mod.audit(store_path=store)
    captured = capsys.readouterr().out

    assert exit_code == 0, f"exit_code should be 0 (PASS), got {exit_code}"
    assert "RESULT: PASS" in captured, "마지막 줄에 RESULT: PASS 없음"
    assert captured.strip().splitlines()[-1] == "RESULT: PASS"


# ── 테스트 2: 만료 지난 pending → WARN ───────────────────────────────────────


def test_warn_expired_pending(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    records = [
        # expires_at 가 2시간 전 → 만료 지남
        _make_record("dr-expired-01", status="pending", expires_at=_utc(-7200), created_at=_utc(-7200)),
    ]
    _write_jsonl(store, records)

    exit_code = _mod.audit(store_path=store)
    captured = capsys.readouterr().out

    assert exit_code == 2, f"exit_code should be 2 (WARN), got {exit_code}"
    assert "RESULT: WARN" in captured
    assert "EXPIRED_PENDING_EXISTS" in captured


# ── 테스트 3: 빈 저장소(파일 없음) → WARN ────────────────────────────────────


def test_warn_empty_store(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    # 파일 자체 없음

    exit_code = _mod.audit(store_path=store)
    captured = capsys.readouterr().out

    assert exit_code == 2, f"exit_code should be 2 (WARN), got {exit_code}"
    assert "RESULT: WARN" in captured
    assert "NO_RECORDS" in captured


# ── 테스트 4: 읽기 실패(PermissionError) → FAIL / exit code 3 ────────────────


def test_fail_read_error(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    store.write_text("dummy\n", encoding="utf-8")

    with mock.patch("builtins.open", side_effect=PermissionError("접근 거부")):
        exit_code = _mod.audit(store_path=store)

    captured = capsys.readouterr().out
    assert exit_code == 3, f"exit_code should be 3 (FAIL), got {exit_code}"
    assert "RESULT: FAIL" in captured
    assert "STORAGE_READ_FAILED" in captured


# ── 테스트 5: RESULT 라인 출력 — 항상 마지막 줄 ─────────────────────────────


@pytest.mark.parametrize("scenario", ["pass", "warn", "fail"])
def test_result_line_is_last(tmp_path, capsys, scenario):
    store = tmp_path / "dev_reg_approvals.jsonl"

    if scenario == "pass":
        records = [
            _make_record("dr-p1", status="executed", executed_at=_utc(-100), decided_at=_utc(-100)),
        ]
        _write_jsonl(store, records)
        exit_code = _mod.audit(store_path=store)
    elif scenario == "warn":
        # 빈 저장소
        exit_code = _mod.audit(store_path=store)
    else:
        store.write_text("{bad json}\n", encoding="utf-8")
        with mock.patch("builtins.open", side_effect=OSError("읽기 불가")):
            exit_code = _mod.audit(store_path=store)

    captured = capsys.readouterr().out
    last_line = captured.strip().splitlines()[-1]
    assert last_line.startswith("RESULT:"), f"마지막 줄이 RESULT: 로 시작하지 않음: {last_line!r}"
    assert exit_code in (0, 2, 3)


# ── 테스트 6: 민감정보 미노출 ───────────────────────────────────────────────


def test_sensitive_fields_not_exposed(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    token_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"  # noqa: S105
    screenshot_full = "/home/ubuntu/data/screenshots/shot_20240101.png"

    records = [
        {
            **_make_record("dr-sec-01", status="executed", executed_at=_utc(-60), decided_at=_utc(-60)),
            "approval_token_hash": token_hash,
            "screenshot_path": screenshot_full,
            "summary": "업체명=테스트코리아",
        }
    ]
    _write_jsonl(store, records)

    _mod.audit(store_path=store)
    captured = capsys.readouterr().out

    # approval_token_hash 전체 값 미노출
    assert token_hash not in captured, "approval_token_hash 가 출력에 노출됨"
    # screenshot 전체 경로 미노출
    assert screenshot_full not in captured, "screenshot_path 전체 경로가 출력에 노출됨"
    # 비밀 키워드 자체가 출력에 포함되면 안 됨 (WARN 메시지 키 이름 제외)
    # → summary 에 password 등이 없으므로 SUMMARY_LEAKAGE 경고 없어야 함
    assert "SUMMARY_LEAKAGE_DETECTED" not in captured


def test_sensitive_keywords_in_summary_detected_not_exposed(tmp_path, capsys):
    """summary 에 민감 키워드 포함 시 경고는 하되 값 자체는 출력 안 함."""
    store = tmp_path / "dev_reg_approvals.jsonl"
    raw_password = "super_secret_password_xyz"  # noqa: S105

    records = [
        {
            **_make_record("dr-leak-01", status="pending"),
            "summary": f"업체명=테스트, password={raw_password}",
        }
    ]
    _write_jsonl(store, records)

    _mod.audit(store_path=store)
    captured = capsys.readouterr().out

    # 실제 비밀값은 절대 출력 안 됨
    assert raw_password not in captured, "raw password 가 출력에 노출됨"
    # 경고는 기록됨 (키워드 이름 + task_id prefix 만)
    assert "SUMMARY_LEAKAGE_DETECTED" in captured or "SUMMARY_SENSITIVE_KEYWORD" in captured


# ── 추가: pending 과다 WARN ───────────────────────────────────────────────────


def test_warn_pending_overload(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    records = [
        _make_record(f"dr-overload-{i:02d}", status="pending", expires_at=_utc(3600))
        for i in range(12)  # pending_max=10 초과
    ]
    _write_jsonl(store, records)

    exit_code = _mod.audit(store_path=store, pending_max=10)
    captured = capsys.readouterr().out

    assert exit_code == 2
    assert "PENDING_OVERLOAD" in captured


# ── 추가: 오래된 pending WARN ─────────────────────────────────────────────────


def test_warn_old_pending(tmp_path, capsys):
    store = tmp_path / "dev_reg_approvals.jsonl"
    # 48시간 전에 생성된 pending (만료는 안 됨 — expires_at 는 미래)
    records = [
        _make_record("dr-old-01", status="pending", expires_at=_utc(7200), created_at=_utc(-48 * 3600)),
    ]
    _write_jsonl(store, records)

    exit_code = _mod.audit(store_path=store, pending_old_hours=24)
    captured = capsys.readouterr().out

    assert exit_code == 2
    assert "OLD_PENDING_EXISTS" in captured
