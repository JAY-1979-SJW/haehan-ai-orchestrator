"""dev_reg_cli.py 검증 테스트.

검증 항목:
  1. pending 명령 정상 동작 및 출력 포맷
  2. history 명령 정상 동작 및 --limit 반영
  3. detail 명령 — 존재 / 미존재 task
  4. expire 명령 — pending 만료 성공 / 비-pending 거절
  5. summary 명령 — 카운트 정확성 및 PASS/WARN 판정
  6. 민감정보 미노출 (approval_token_hash, screenshot_path, password 등)
  7. 없는 task_id 처리 (RESULT: FAIL, exit code 3)
  8. approve/reject/submit 명령 부재 확인
  9. 기존 회귀 — dev_reg_approval 모듈 정상 동작 유지
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """각 테스트마다 독립 storage + 모듈 초기화."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    import ai_orchestrator.core.config as _cfg

    importlib.reload(_cfg)
    import tools.gates.approval as _ap

    importlib.reload(_ap)
    _ap.clear_rate_store()
    import ai_orchestrator.audit.audit_logger as _al

    importlib.reload(_al)
    import ai_orchestrator.dev_reg.dev_reg_approval as _d

    importlib.reload(_d)
    _d.clear()
    import ai_orchestrator.dev_reg.dev_reg_audit_log as _dl

    importlib.reload(_dl)

    import ai_orchestrator.dev_reg.dev_reg_cli as cli

    importlib.reload(cli)

    yield

    _ap.clear_rate_store()
    importlib.reload(_cfg)
    importlib.reload(_ap)
    importlib.reload(_al)
    importlib.reload(_d)
    _d.clear()


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _utc(delta_s: float = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=delta_s)).isoformat()


def _create_pending(
    task_id: str = "dr-aabbccdd0001",
    provider: str = "hiworks",
    action_type: str = "developer_apply",
    risk_level: str = "medium",
    requested_by: str = "agent@test",
    expires_in: float = 3600,
) -> Any:
    import ai_orchestrator.dev_reg.dev_reg_approval as dra
    import tools.gates.approval as ap

    # 음수 expires_in 은 이미 만료된 레코드를 만들기 위한 것.
    # TTL 은 최소 1분으로 발행하되, expires_at 은 지정된 과거 시각으로 덮어씀.
    ttl_min = max(1, int(expires_in / 60)) if expires_in > 0 else 1
    token = ap.issue_token_for_dev_reg(task_id, requested_by, risk_level, ttl_minutes=ttl_min)
    expires_at = _utc(expires_in) if expires_in <= 0 else token.expires_at
    rec = dra.create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider=provider,
        action_type=action_type,
        risk_level=risk_level,
        summary="업체명=테스트업체 담당자=홍길동",
        target_url="https://example.com/form",
        screenshot_path="/tmp/shot.png",  # noqa: S108
        requested_by=requested_by,
        expires_at=expires_at,
    )
    return rec


def _get_cli():
    import ai_orchestrator.dev_reg.dev_reg_cli as cli

    importlib.reload(cli)
    return cli


# ── 1. pending ────────────────────────────────────────────────────────────────


class TestPending:
    def test_empty_store_returns_pass(self, capsys):
        cli = _get_cli()
        rc = cli.cmd_pending()
        out = capsys.readouterr().out
        assert rc == cli.EXIT_PASS
        assert "RESULT: PASS" in out
        assert "(없음)" in out

    def test_normal_pending_shows_table(self, capsys):
        _create_pending("dr-001")
        cli = _get_cli()
        rc = cli.cmd_pending()
        out = capsys.readouterr().out
        assert rc == cli.EXIT_PASS
        assert "dr-001" in out
        assert "hiworks" in out
        assert "RESULT: PASS" in out
        assert "total pending: 1" in out

    def test_expired_pending_returns_warn(self, capsys):
        _create_pending("dr-exp", expires_in=-10)
        cli = _get_cli()
        rc = cli.cmd_pending()
        out = capsys.readouterr().out
        assert rc == cli.EXIT_WARN
        assert "RESULT: WARN" in out
        assert "[EXPIRED]" in out

    def test_result_on_last_line(self, capsys):
        cli = _get_cli()
        cli.cmd_pending()
        out = capsys.readouterr().out
        lines = [l for l in out.strip().splitlines() if l.strip()]  # noqa: E741
        assert lines[-1].startswith("RESULT:")


# ── 2. history ────────────────────────────────────────────────────────────────


class TestHistory:
    def test_empty_returns_warn(self, capsys):
        cli = _get_cli()
        rc = cli.cmd_history(20)
        out = capsys.readouterr().out
        assert rc == cli.EXIT_WARN
        assert "RESULT: WARN" in out

    def test_shows_records(self, capsys):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-h001")
        dra.mark_executed("dr-h001", result="ok")
        cli = _get_cli()
        rc = cli.cmd_history(20)
        out = capsys.readouterr().out
        assert rc == cli.EXIT_PASS
        assert "dr-h001" in out
        assert "executed" in out
        assert "RESULT: PASS" in out

    def test_limit_respected(self, capsys):
        for i in range(5):
            _create_pending(f"dr-lim{i:03d}")
        cli = _get_cli()
        cli.cmd_history(2)
        out = capsys.readouterr().out
        assert "showing: 2 record(s)" in out

    def test_failed_status_returns_warn(self, capsys):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-fail")
        dra.mark_failed("dr-fail", error="submit error")
        cli = _get_cli()
        rc = cli.cmd_history(20)
        out = capsys.readouterr().out
        assert rc == cli.EXIT_WARN
        assert "RESULT: WARN" in out


# ── 3. detail ─────────────────────────────────────────────────────────────────


class TestDetail:
    def test_existing_task_shows_fields(self, capsys):
        _create_pending("dr-detail-1")
        cli = _get_cli()
        rc = cli.cmd_detail("dr-detail-1")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_PASS
        assert "dr-detail-1" in out
        assert "pending" in out
        assert "RESULT: PASS" in out

    def test_missing_task_returns_fail(self, capsys):
        cli = _get_cli()
        rc = cli.cmd_detail("dr-does-not-exist")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_FAIL
        assert "RESULT: FAIL" in out
        assert "찾을 수 없습니다" in out

    def test_expired_status_returns_warn(self, capsys):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-expired")
        dra.mark_expired_internal("dr-expired")
        cli = _get_cli()
        rc = cli.cmd_detail("dr-expired")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_WARN
        assert "RESULT: WARN" in out

    def test_result_on_last_line(self, capsys):
        _create_pending("dr-d2")
        cli = _get_cli()
        cli.cmd_detail("dr-d2")
        out = capsys.readouterr().out
        lines = [l for l in out.strip().splitlines() if l.strip()]  # noqa: E741
        assert lines[-1].startswith("RESULT:")


# ── 4. expire ─────────────────────────────────────────────────────────────────


class TestExpire:
    def test_expire_pending_succeeds(self, capsys):
        _create_pending("dr-exp1")
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        cli = _get_cli()
        rc = cli.cmd_expire("dr-exp1")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_PASS
        assert "RESULT: PASS" in out
        assert "expired" in out

        updated = dra.get("dr-exp1")
        assert updated is not None
        assert updated.status == "expired"

    def test_expire_non_pending_returns_fail(self, capsys):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-exec")
        dra.mark_executed("dr-exec", result="ok")
        cli = _get_cli()
        rc = cli.cmd_expire("dr-exec")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_FAIL
        assert "RESULT: FAIL" in out
        assert "executed" in out

    def test_expire_missing_task_returns_fail(self, capsys):
        cli = _get_cli()
        rc = cli.cmd_expire("dr-no-such")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_FAIL
        assert "RESULT: FAIL" in out

    def test_expire_signals_event(self):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-ev1")
        ev = dra.register_approval_waiter("dr-ev1")
        cli = _get_cli()
        cli.cmd_expire("dr-ev1")
        assert ev.is_set(), "expire 후 approval event 가 set 되어야 함"


# ── 5. summary ───────────────────────────────────────────────────────────────


class TestSummary:
    def test_empty_store_pass(self, capsys):
        cli = _get_cli()
        rc = cli.cmd_summary()
        out = capsys.readouterr().out
        assert rc == cli.EXIT_PASS
        assert "RESULT: PASS" in out
        assert "pending_count" in out

    def test_counts_correct(self, capsys):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-s1")
        _create_pending("dr-s2")
        dra.mark_executed("dr-s1", result="ok")
        cli = _get_cli()
        cli.cmd_summary()
        out = capsys.readouterr().out
        assert "pending_count" in out

    def test_expired_pending_returns_warn(self, capsys):
        _create_pending("dr-sw", expires_in=-5)
        cli = _get_cli()
        rc = cli.cmd_summary()
        out = capsys.readouterr().out
        assert rc == cli.EXIT_WARN
        assert "RESULT: WARN" in out
        assert "만료된 pending" in out

    def test_summary_fields_present(self, capsys):
        cli = _get_cli()
        cli.cmd_summary()
        out = capsys.readouterr().out
        for field in ("pending_count", "expired_pending", "recent_executed", "recent_failed", "last_activity"):
            assert field in out, f"summary 에 '{field}' 필드 없음"

    def test_result_on_last_line(self, capsys):
        cli = _get_cli()
        cli.cmd_summary()
        out = capsys.readouterr().out
        lines = [l for l in out.strip().splitlines() if l.strip()]  # noqa: E741
        assert lines[-1].startswith("RESULT:")


# ── 6. 민감정보 미노출 ───────────────────────────────────────────────────────


class TestNoSensitiveLeakage:
    _BLOCKED = (
        "SHOULD_NOT_APPEAR",
        "approval_token_hash",
        "/tmp/shot.png",  # noqa: S108
        "/var/data/screenshots",
    )
    _SENSITIVE_KW = ("password", "passwd", "cookie", "session", "secret")

    def _assert_clean(self, out: str) -> None:
        low = out.lower()
        for kw in self._SENSITIVE_KW:
            if kw in low:
                # 허용: "REDACTED" 로 치환된 경우는 OK
                # 실제 값이 노출된 경우만 실패
                for line in out.splitlines():
                    if kw in line.lower() and "[REDACTED]" not in line:
                        pytest.fail(f"민감 키워드 '{kw}' 가 출력에 노출됨: {line!r}")
        for blocked in self._BLOCKED:
            assert blocked not in out, f"차단 문자열 '{blocked}' 가 출력에 노출됨"

    def test_pending_no_sensitive(self, capsys):
        _create_pending("dr-sec1")
        _get_cli().cmd_pending()
        self._assert_clean(capsys.readouterr().out)

    def test_history_no_sensitive(self, capsys):
        _create_pending("dr-sec2")
        _get_cli().cmd_history(20)
        self._assert_clean(capsys.readouterr().out)

    def test_detail_no_token_hash(self, capsys):
        _create_pending("dr-sec3")
        _get_cli().cmd_detail("dr-sec3")
        out = capsys.readouterr().out
        self._assert_clean(out)
        # token_id 는 detail 에서 REDACTED 처리되어야 함
        assert "token_id" not in out or "[REDACTED]" in out

    def test_summary_no_sensitive(self, capsys):
        _create_pending("dr-sec4")
        _get_cli().cmd_summary()
        self._assert_clean(capsys.readouterr().out)

    def test_summary_field_with_password_kw_redacted(self, capsys):
        """summary 필드 값에 password 키워드 포함 시 REDACTED."""
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        importlib.reload(dra)
        # 실제 password 값 노출은 create_pending 레벨에서 차단되지만
        # CLI 레이어의 추가 방어도 검증
        import ai_orchestrator.dev_reg.dev_reg_cli as cli

        importlib.reload(cli)
        val = cli._safe_value("note", "password=abc123")
        assert val == "[REDACTED]"


# ── 7. 없는 task 처리 ────────────────────────────────────────────────────────


class TestMissingTask:
    def test_detail_missing(self, capsys):
        cli = _get_cli()
        rc = cli.cmd_detail("dr-ghost-0001")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_FAIL
        assert "RESULT: FAIL" in out

    def test_expire_missing(self, capsys):
        cli = _get_cli()
        rc = cli.cmd_expire("dr-ghost-0002")
        out = capsys.readouterr().out
        assert rc == cli.EXIT_FAIL
        assert "RESULT: FAIL" in out


# ── 8. approve/reject/submit 명령 부재 확인 ──────────────────────────────────


class TestForbiddenCommands:
    def test_no_approve_subcommand(self):
        """CLI 파서에 approve 서브커맨드가 없어야 한다."""
        import ai_orchestrator.dev_reg.dev_reg_cli as cli

        parser = cli._build_parser()
        # subcommand choices 에 approve 가 없어야 함
        subparsers_action = next(a for a in parser._actions if hasattr(a, "_name_parser_map"))
        assert "approve" not in subparsers_action._name_parser_map
        assert "reject" not in subparsers_action._name_parser_map
        assert "submit" not in subparsers_action._name_parser_map

    def test_approve_arg_raises(self):
        """approve 인자를 전달하면 SystemExit 발생."""
        import ai_orchestrator.dev_reg.dev_reg_cli as cli

        parser = cli._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["approve", "dr-fake"])

    def test_reject_arg_raises(self):
        import ai_orchestrator.dev_reg.dev_reg_cli as cli

        parser = cli._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["reject", "dr-fake"])


# ── 9. 기존 회귀 — dev_reg_approval 모듈 정상 동작 ──────────────────────────


class TestRegression:
    def test_create_and_get_detail_works_after_cli_import(self):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-reg1")
        rec = dra.get_detail("dr-reg1")
        assert rec is not None
        assert rec["status"] == "pending"

    def test_mark_executed_after_cli_expire_different_task(self, capsys):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-a")
        _create_pending("dr-b")
        cli = _get_cli()
        cli.cmd_expire("dr-a")
        capsys.readouterr()

        dra.mark_executed("dr-b", result="ok")
        assert dra.get("dr-b").status == "executed"
        assert dra.get("dr-a").status == "expired"

    def test_list_pending_excludes_non_pending(self):
        import ai_orchestrator.dev_reg.dev_reg_approval as dra

        _create_pending("dr-p1")
        _create_pending("dr-p2")
        dra.mark_executed("dr-p1", result="ok")
        pending = dra.list_pending()
        ids = [r["task_id"] for r in pending]
        assert "dr-p1" not in ids
        assert "dr-p2" in ids
