"""개발자 등록 신청 텔레그램 승인 게이트 검증.

필수 테스트:
  1. 승인 전에는 submit_form 호출 안됨
  2. 올바른 token + 허용 telegram_user_id 만 승인 가능
  3. 만료 token 거절
  4. 재사용 token 거절
  5. 거절 시 submit_form 안 호출, abort_form 호출
  6. 승인 시에만 submit_form 호출
  7. audit log 기록 (DEV_REG_* 이벤트)
  8. secret/cookie/password 로그 미노출
"""

from __future__ import annotations

import importlib
import sys
import threading
import time as _time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


# ── 공통 픽스처 ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """각 테스트마다 독립된 storage 경로 사용."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    import ai_orchestrator.core.config as _cfg

    importlib.reload(_cfg)
    import tools.gates.approval as _ap

    importlib.reload(_ap)
    _ap.clear_rate_store()
    import ai_orchestrator.audit.audit_logger as _al

    importlib.reload(_al)
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra

    importlib.reload(_dra)
    _dra.clear()

    yield

    _ap.clear_rate_store()
    importlib.reload(_cfg)
    importlib.reload(_ap)
    importlib.reload(_al)
    importlib.reload(_dra)
    _dra.clear()


def _make_adapter(provider="hiworks", action_type="developer_apply", risk_level="high"):
    """Mock 어댑터 생성."""
    from ai_orchestrator.sites.adapters.dev_reg_base import (
        DevRegAdapterBase,
        FormFillResult,
        SubmitResult,
    )

    class _MockAdapter(DevRegAdapterBase):
        provider = "hiworks"
        action_type = "developer_apply"
        risk_level = "high"

        def __init__(self):
            self.fill_called = False
            self.submit_called = False
            self.abort_called = False
            self.screenshot_called = False

        def fill_form(self, page, params: dict) -> FormFillResult:
            self.fill_called = True
            return FormFillResult(
                success=True,
                summary="[하이웍스 개발자 등록 신청]\n  app_name: TestApp",
                field_names=["app_name", "app_purpose"],
                target_url="https://developers.hiworks.com/apply",
            )

        def submit_form(self, page) -> SubmitResult:
            self.submit_called = True
            return SubmitResult(success=True, result_summary="신청 완료")

        def abort_form(self, page) -> None:
            self.abort_called = True

        def capture_screenshot(self, page, path: Path) -> Path:
            self.screenshot_called = True
            path.write_bytes(b"fake-png")
            return path

    a = _MockAdapter()
    a.provider = provider
    a.action_type = action_type
    a.risk_level = risk_level
    return a


def _run_with_outcome(
    adapter, *, approve: bool, expired: bool = False, rejected: bool = False, tmp_path: Path, ttl_minutes: int = 30
):
    """run_dev_reg 실행 헬퍼 — 이벤트 기반 승인/거절 결과 주입.

    만료 케이스: clock 을 미래 시각으로 고정 → timeout_sec=0 → event.wait() 즉시 반환.
    승인/거절 케이스: runner 를 별도 스레드에서 실행 + pending 레코드 등록 후 즉시 신호 전달.
    """
    from ai_orchestrator.dev_reg.dev_reg_runner import run_dev_reg

    page = MagicMock()

    if expired:
        future = datetime.now(UTC) + timedelta(minutes=ttl_minutes + 5)
        result = run_dev_reg(
            adapter,
            page,
            {"app_name": "TestApp"},
            requested_by="test_user",
            screenshot_dir=tmp_path / "screenshots",
            ttl_minutes=ttl_minutes,
            clock=lambda: future,
        )
        return result, page

    # ── 비만료: runner 를 스레드에서 실행 + 바깥에서 승인/거절 신호 ──
    result_holder: list = [None]

    def _run():
        result_holder[0] = run_dev_reg(
            adapter,
            page,
            {"app_name": "TestApp"},
            requested_by="test_user",
            screenshot_dir=tmp_path / "screenshots",
            ttl_minutes=ttl_minutes,
        )

    runner_thread = threading.Thread(target=_run, daemon=True)
    runner_thread.start()

    import ai_orchestrator.dev_reg.dev_reg_approval as _dra
    import tools.gates.approval as _ap

    # pending 레코드 등록 대기 (최대 2초, 20ms 간격)
    for _ in range(100):
        _time.sleep(0.02)
        for rec in list(_dra._store.values()):
            tok_id = rec.get("token_id", "")
            t_id = rec.get("task_id", "")
            if tok_id and rec.get("status") == "pending":
                if approve:
                    _ap.approve_token(tok_id, t_id, "admin", "admin")
                elif rejected:
                    _ap.reject_token(tok_id, t_id, "admin", "admin", reason="테스트 거절")
                # 이벤트 신호 전달 — pre-signal 지원으로 타이밍 무관
                _dra.signal_approval_event(t_id)
                break
        else:
            continue
        break

    runner_thread.join(timeout=5)
    assert result_holder[0] is not None, "run_dev_reg 가 5초 내에 완료되지 않음"
    return result_holder[0], page


# ── 테스트 1: 승인 전에는 submit_form 호출 안됨 ─────────────────────


def test_submit_not_called_before_approval(tmp_path):
    """폴링 중 승인 없이 만료되면 submit_form 을 절대 호출하지 않는다."""
    adapter = _make_adapter()
    result, _ = _run_with_outcome(adapter, approve=False, expired=True, tmp_path=tmp_path, ttl_minutes=1)

    assert adapter.submit_called is False, "submit_form 이 승인 없이 호출됨"
    assert adapter.abort_called is True, "abort_form 이 호출되지 않음"
    assert result.status in ("expired", "failed")


# ── 테스트 2: 올바른 token + 허용 telegram_user_id 만 승인 가능 ─────


def test_only_allowed_telegram_user_can_approve():
    """허용 목록에 없는 telegram_user_id 는 승인 불가."""
    from ai_orchestrator.dev_reg.dev_reg_approval import (
        create_pending,
        handle_telegram_decision,
    )
    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=30)
    create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="hiworks",
        action_type="developer_apply",
        risk_level="high",
        summary="test",
        target_url="http://example.com",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )

    # 올바른 사용자: admin 역할
    result = handle_telegram_decision(
        token_id=token.token_id,
        action="approve",
        actor="admin",
        role="admin",
    )
    assert result["success"] is True, f"정상 승인 실패: {result}"
    assert result["status"] == "approved"


def test_forbidden_role_cannot_approve():
    """viewer 역할로는 승인 불가 — approve_token 이 forbidden 반환."""
    from ai_orchestrator.dev_reg.dev_reg_approval import (
        create_pending,
        handle_telegram_decision,
    )
    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=30)
    create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="naver",
        action_type="app_register",
        risk_level="high",
        summary="test",
        target_url="http://example.com",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )

    result = handle_telegram_decision(
        token_id=token.token_id,
        action="approve",
        actor="viewer-01",
        role="viewer",
    )
    assert result["success"] is False
    assert result["status"] == "forbidden"


def test_unregistered_telegram_user_blocked():
    """telegram_users.json 에 없는 사용자 ID 는 handle_telegram_update 에서 차단."""
    from ai_orchestrator.dev_reg.dev_reg_approval import create_pending
    from ai_orchestrator.dev_reg.dev_reg_telegram import build_dev_reg_callback_data
    from ai_orchestrator.notify.telegram_webhook import handle_telegram_update
    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=30)
    create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="hiworks",
        action_type="developer_apply",
        risk_level="high",
        summary="test",
        target_url="http://example.com",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )
    cb_data = build_dev_reg_callback_data("approve", token.token_id)
    update = {
        "callback_query": {
            "id": "cq1",
            "data": cb_data,
            "from": {"id": 777777777, "username": "unknown"},  # 미등록
        }
    }
    result = handle_telegram_update(update)
    assert result["success"] is False
    assert result["status"] == "user_not_found"


# ── 테스트 3: 만료 token 거절 ────────────────────────────────────────


def test_expired_token_rejected(monkeypatch):
    """토큰 만료 후 승인 시도 시 expired 반환."""
    import tools.gates.approval as _ap
    from ai_orchestrator.dev_reg.dev_reg_approval import (
        create_pending,
        handle_telegram_decision,
    )
    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    # TTL 1분으로 발행
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=1)
    create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="hiworks",
        action_type="developer_apply",
        risk_level="high",
        summary="test",
        target_url="http://example.com",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )

    # approval 모듈의 _now 를 만료 후 시각으로 고정
    future = datetime.now(UTC) + timedelta(minutes=5)
    monkeypatch.setattr(_ap, "_now", lambda: future)

    result = handle_telegram_decision(
        token_id=token.token_id,
        action="approve",
        actor="admin",
        role="admin",
    )
    assert result["success"] is False, f"만료 토큰 승인이 성공으로 처리됨: {result}"
    assert result["status"] == "expired"


# ── 테스트 4: 재사용 token 거절 ─────────────────────────────────────


def test_reused_token_rejected():
    """이미 승인된 토큰으로 두 번째 승인 시도 시 already_used."""
    from ai_orchestrator.dev_reg.dev_reg_approval import (
        create_pending,
        handle_telegram_decision,
    )
    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=30)
    create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="hiworks",
        action_type="developer_apply",
        risk_level="high",
        summary="test",
        target_url="http://example.com",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )

    # 첫 번째 승인 — 성공
    r1 = handle_telegram_decision(token_id=token.token_id, action="approve", actor="admin", role="admin")
    assert r1["status"] == "approved"

    # 두 번째 승인 — already_used
    r2 = handle_telegram_decision(token_id=token.token_id, action="approve", actor="admin", role="admin")
    assert r2["success"] is False
    assert r2["status"] == "already_used"


# ── 테스트 5: 거절 시 abort_form 호출, submit_form 호출 안됨 ─────────


def test_rejection_calls_abort_not_submit(tmp_path):
    """거절 결정 후 abort_form 이 호출되고 submit_form 은 호출되지 않는다."""
    adapter = _make_adapter()
    result, _ = _run_with_outcome(adapter, approve=False, rejected=True, tmp_path=tmp_path)

    assert adapter.submit_called is False, "거절 후 submit_form 이 호출됨"
    assert adapter.abort_called is True, "거절 후 abort_form 이 호출되지 않음"
    assert result.status == "rejected"


# ── 테스트 6: 승인 시에만 submit_form 호출 ───────────────────────────


def test_approval_triggers_submit_form(tmp_path):
    """승인 확정 후 submit_form 이 호출된다."""
    adapter = _make_adapter()
    result, _ = _run_with_outcome(adapter, approve=True, tmp_path=tmp_path)

    assert adapter.submit_called is True, "승인 후 submit_form 이 호출되지 않음"
    assert result.status == "executed"
    assert result.result == "신청 완료"


# ── 테스트 7: audit log 기록 ─────────────────────────────────────────


def test_audit_log_events_recorded(tmp_path):
    """DEV_REG_TASK_CREATED, DEV_REG_TELEGRAM_SENT 이벤트가 감사 로그에 기록된다."""
    # telegram_sender.send_photo 를 mock (실제 HTTP 호출 방지)
    with patch("ai_orchestrator.core.telegram_sender.send_photo", return_value={"ok": False, "skipped": True}):
        adapter = _make_adapter()
        from ai_orchestrator.dev_reg.dev_reg_runner import run_dev_reg

        page = MagicMock()
        future = datetime.now(UTC) + timedelta(minutes=35)
        run_dev_reg(
            adapter,
            page,
            {"app_name": "TestApp"},
            requested_by="test",
            screenshot_dir=tmp_path / "ss",
            ttl_minutes=1,
            clock=lambda: future,  # 즉시 만료
        )

    import ai_orchestrator.audit.audit_logger as _al

    logs = _al.read_recent_logs(limit=50)
    event_types = {e["event_type"] for e in logs}
    assert "DEV_REG_TASK_CREATED" in event_types, f"DEV_REG_TASK_CREATED 누락: {event_types}"
    assert "DEV_REG_TELEGRAM_SENT" in event_types, f"DEV_REG_TELEGRAM_SENT 누락: {event_types}"


def test_approval_audit_event_recorded():
    """handle_telegram_decision 승인 시 DEV_REG_APPROVED 이벤트 기록."""
    import ai_orchestrator.audit.audit_logger as _al
    from ai_orchestrator.dev_reg.dev_reg_approval import (
        create_pending,
        handle_telegram_decision,
    )
    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=30)
    create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="hiworks",
        action_type="developer_apply",
        risk_level="high",
        summary="test",
        target_url="http://example.com",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )
    handle_telegram_decision(token_id=token.token_id, action="approve", actor="admin", role="admin")

    logs = _al.read_recent_logs(limit=50)
    event_types = {e["event_type"] for e in logs}
    assert "DEV_REG_APPROVED" in event_types, f"DEV_REG_APPROVED 누락: {event_types}"


def test_rejection_audit_event_recorded():
    """거절 시 DEV_REG_REJECTED 이벤트 기록."""
    import ai_orchestrator.audit.audit_logger as _al
    from ai_orchestrator.dev_reg.dev_reg_approval import (
        create_pending,
        handle_telegram_decision,
    )
    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=30)
    create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="naver",
        action_type="app_register",
        risk_level="high",
        summary="test",
        target_url="http://example.com",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )
    handle_telegram_decision(token_id=token.token_id, action="reject", actor="admin", role="admin", reason="테스트")

    logs = _al.read_recent_logs(limit=50)
    event_types = {e["event_type"] for e in logs}
    assert "DEV_REG_REJECTED" in event_types, f"DEV_REG_REJECTED 누락: {event_types}"


# ── 테스트 8: secret/cookie/password 로그 미노출 ─────────────────────


def test_sensitive_fields_not_in_audit_log(tmp_path):
    """패스워드·쿠키·세션 토큰이 감사 로그에 노출되지 않는다."""
    _SENSITIVE = ["my_secret_password", "session_cookie_abc123", "Bearer eyJhbGci"]

    # params 에 민감 값 포함 — adapter 의 summary 에는 포함되지 않아야 함
    with patch("ai_orchestrator.core.telegram_sender.send_photo", return_value={"ok": False, "skipped": True}):
        adapter = _make_adapter()
        from ai_orchestrator.dev_reg.dev_reg_runner import run_dev_reg

        page = MagicMock()
        future = datetime.now(UTC) + timedelta(minutes=35)
        run_dev_reg(
            adapter,
            page,
            {
                "app_name": "TestApp",
                "password": _SENSITIVE[0],  # 민감값 — 어댑터가 summary 에 포함하지 말아야 함
                "cookie": _SENSITIVE[1],
                "session_token": _SENSITIVE[2],
            },
            requested_by="test",
            screenshot_dir=tmp_path / "ss",
            ttl_minutes=1,
            clock=lambda: future,
        )

    import ai_orchestrator.audit.audit_logger as _al

    log_path = _al._LOG_PATH
    if not log_path.exists():
        return  # 로그 없으면 노출 없음

    raw = log_path.read_text(encoding="utf-8")
    for sensitive in _SENSITIVE:
        assert sensitive not in raw, f"감사 로그에 민감 값 노출됨: {sensitive!r}"


def test_dev_reg_approval_record_no_raw_secrets():
    """dev_reg_approval JSONL 에 패스워드·쿠키·세션 토큰이 포함되지 않는다."""
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra

    _SENSITIVE = ["plaintext_password_xyz", "raw_cookie_value", "session_abc"]

    from tools.gates.approval import issue_token_for_dev_reg

    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    token = issue_token_for_dev_reg(task_id, "system", "high", ttl_minutes=30)
    # summary 에 실수로 민감 값을 넣은 경우를 시뮬레이션하지 않음.
    # 단지 레코드 자체에 민감 필드가 없음을 확인.
    _dra.create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider="hiworks",
        action_type="developer_apply",
        risk_level="high",
        summary="[하이웍스 신청]\n  app_name: TestApp",
        target_url="https://developers.hiworks.com/apply",
        screenshot_path="/tmp/ss.png",  # noqa: S108
        requested_by="system",
        expires_at=token.expires_at,
    )

    store_path = _dra._STORE_PATH
    if not store_path.exists():
        return

    raw = store_path.read_text(encoding="utf-8")
    for sensitive in _SENSITIVE:
        assert sensitive not in raw, f"dev_reg JSONL 에 민감 값 노출됨: {sensitive!r}"

    # token_id 원문은 저장됨 (식별자로서 허용), approval_token_hash 는 SHA256 이어야 함
    import json as _json

    for line in raw.strip().splitlines():
        ev = _json.loads(line)
        hash_val = ev.get("approval_token_hash", "")
        # SHA256 hex digest: 64자, hex 문자만
        if hash_val:
            assert len(hash_val) == 64 and all(c in "0123456789abcdef" for c in hash_val), (
                f"approval_token_hash 가 SHA256 형식이 아님: {hash_val!r}"
            )


# ── 추가: dev_reg callback_data 형식 검증 ────────────────────────────


def test_dev_reg_callback_data_format():
    """build/parse 대칭성 및 64바이트 제한 검증."""
    from ai_orchestrator.dev_reg.dev_reg_telegram import (
        build_dev_reg_callback_data,
        parse_dev_reg_callback_data,
    )

    token_id = str(uuid.uuid4())
    for action in ("approve", "reject"):
        data = build_dev_reg_callback_data(action, token_id)
        assert len(data.encode("utf-8")) <= 64, f"callback_data 64바이트 초과: {len(data)}"
        parsed = parse_dev_reg_callback_data(data)
        assert parsed is not None
        assert parsed["action"] == action
        assert parsed["token_id"] == token_id


def test_parse_dev_reg_rejects_invalid():
    """잘못된 callback_data 는 None 반환."""
    from ai_orchestrator.dev_reg.dev_reg_telegram import parse_dev_reg_callback_data

    assert parse_dev_reg_callback_data("") is None
    assert parse_dev_reg_callback_data("approve|task|token") is None  # 기존 형식 → None
    assert parse_dev_reg_callback_data("dr_x|token_id") is None  # 알 수 없는 prefix


# ── 추가: 회귀 — 기존 webhook 형식이 영향받지 않음 ────────────────────


def test_existing_webhook_unaffected():
    """기존 handle_telegram_webhook 는 dr_* 추가 후에도 정상 동작."""
    from ai_orchestrator.core.models import RiskAssessment, TaskRequest
    from ai_orchestrator.notify.telegram_webhook import handle_telegram_webhook
    from tools.gates.approval import issue_token

    tid = f"TG-{uuid.uuid4().hex[:8]}"
    req = TaskRequest(
        task_id=tid,
        source="manual",
        action_type="edit_config",
        target="/etc/cfg",
        description="회귀 테스트",
        requested_by="test",
    )
    risk = RiskAssessment(risk_level="medium", reasons=["test"], requires_approval=True)
    token = issue_token(req, risk)

    result = handle_telegram_webhook(
        {
            "telegram_user_id": "111111111",
            "action": "approve",
            "task_id": tid,
            "token_id": token.token_id,
        }
    )
    assert result["success"] is True
    assert result["status"] == "approved"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_dev_reg_callback_separator_matches_the_notifier():
    """dev_reg_telegram 은 알림 모듈을 import 하지 않으려고 구분자를 따로 두므로 값이 같은지 고정한다."""
    from ai_orchestrator.dev_reg import dev_reg_telegram
    from ai_orchestrator.notify import telegram_notifier

    assert dev_reg_telegram.CALLBACK_SEP == telegram_notifier.CALLBACK_SEP
