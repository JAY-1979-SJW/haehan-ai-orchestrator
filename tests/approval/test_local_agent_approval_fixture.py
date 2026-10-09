"""Stage 12E — local-agent approval 상태 전이 fixture 테스트.

검증 대상:
  1. waiting_approval 상태 작업 → approve 가능
  2. waiting_approval 상태 작업 → reject 가능
  3. 잘못된 token_id → not_found 차단
  4. 이미 처리된 token 재사용 → already_used 차단
  5. 권한 부족(viewer) → forbidden 차단
  6. critical 정책 기본 차단
  7. approve/reject 시 audit 이벤트 기록
  8. 실제 local-agent action 미실행 검증

실행 방법:
  pytest tests/test_local_agent_approval_fixture.py -v

제약:
  - 실제 HTTP 서버, local-agent 프로세스, 브라우저, 네트워크 요청 없음
  - in-memory fixture + monkeypatch + tmp_path 사용
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import ai_orchestrator.core.task_state as _ts

# ── import 대상 모듈 ────────────────────────────────────────────────────────
import tools.gates.approval as _appr
import tools.gates.policy as _policy

# ── 공통 픽스처 ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_approval_store(tmp_path, monkeypatch):
    """approval._store, _STORE_PATH, _load_store 를 tmp_path 기반으로 격리.

    approve_token / reject_token 내부의 _load_store() 가 _store 를 초기화하지
    않도록 no-op 으로 패치한다. 이벤트 기록(_append_event)은 실제 tmp 파일로 유지.
    """
    store_file = tmp_path / "approval_tokens.jsonl"
    monkeypatch.setattr(_appr, "_store", {})
    monkeypatch.setattr(_appr, "_STORE_PATH", store_file)
    monkeypatch.setattr(_appr, "_load_store", lambda: None)
    _appr.clear_rate_store()
    yield store_file
    _appr.clear_rate_store()


@pytest.fixture(autouse=True)
def isolated_task_state(monkeypatch):
    """task_state._store 와 _load 를 격리."""
    monkeypatch.setattr(_ts, "_store", {})
    monkeypatch.setattr(_ts, "_load", lambda: None)
    yield
    _ts.clear()


def _future_iso(minutes: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _past_iso(minutes: int = 30) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _seed_token(
    token_id: str,
    task_id: str,
    status: str = "issued",
    expires_at: str | None = None,
) -> dict:
    """approval._store 에 토큰 항목을 직접 삽입."""
    entry = {
        "token_id": token_id,
        "task_id": task_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": expires_at or _future_iso(30),
        "issued_by": "test-requester",
        "approved_by": None,
        "risk_level": "high",
        "status": status,
        "used_at": None,
        "result": "",
    }
    _appr._store[token_id] = entry
    return entry


# ── 1. waiting_approval → approve ──────────────────────────────────────────


class TestApproveSuccess:
    def test_approve_returns_approved_status(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-001"
        _seed_token(tid, task_id)

        token, status = _appr.approve_token(tid, task_id, "admin-user", "admin")

        assert status == "approved"
        assert token.status == "approved"
        assert token.approved_by == "admin-user"
        assert token.used_at is not None

    def test_approve_updates_store_status(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-002"
        _seed_token(tid, task_id)

        _appr.approve_token(tid, task_id, "owner-user", "owner")

        assert _appr._store[tid]["status"] == "approved"

    def test_task_state_pending_to_approved(self):
        task_id = "la-task-003"
        _ts.set_pending(
            task_id,
            risk_level="high",
            token_id="tok",
            requested_by="requester",
            actor_role="admin",
            action_type="capture_screenshot",
            target="screen",
            task_snapshot={},
        )
        rec, outcome = _ts.mark_approved(task_id, "admin-user", "admin")
        assert outcome == "approved"
        assert rec.state == "approved"


# ── 2. waiting_approval → reject ───────────────────────────────────────────


class TestRejectSuccess:
    def test_reject_returns_rejected_status(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-010"
        _seed_token(tid, task_id)

        token, status = _appr.reject_token(tid, task_id, "admin-user", "admin", reason="위험")

        assert status == "rejected"
        assert token.status == "rejected"
        assert "rejected" in token.result

    def test_reject_updates_store_status(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-011"
        _seed_token(tid, task_id)

        _appr.reject_token(tid, task_id, "owner-user", "owner")

        assert _appr._store[tid]["status"] == "rejected"

    def test_task_state_pending_to_rejected(self):
        task_id = "la-task-012"
        _ts.set_pending(
            task_id,
            risk_level="high",
            token_id="tok",
            requested_by="requester",
            actor_role="admin",
            action_type="capture_screenshot",
            target="screen",
            task_snapshot={},
        )
        rec, outcome = _ts.mark_rejected(task_id, "admin-user", "admin", reason="deny")
        assert outcome == "rejected"
        assert rec.state == "rejected"


# ── 3. 잘못된 token_id → not_found ─────────────────────────────────────────


class TestInvalidToken:
    def test_approve_nonexistent_token(self):
        fake_id = str(uuid.uuid4())
        _, status = _appr.approve_token(fake_id, "la-task-020", "admin", "admin")
        assert status == "not_found"

    def test_reject_nonexistent_token(self):
        fake_id = str(uuid.uuid4())
        _, status = _appr.reject_token(fake_id, "la-task-021", "admin", "admin")
        assert status == "not_found"

    def test_approve_task_id_mismatch(self):
        tid = str(uuid.uuid4())
        _seed_token(tid, "la-task-022")
        _, status = _appr.approve_token(tid, "la-task-WRONG", "admin", "admin")
        assert status == "task_mismatch"

    def test_validate_token_nonexistent(self):
        assert _appr.validate_token(str(uuid.uuid4()), "la-task-023") is False


# ── 4. token 재사용 차단 ───────────────────────────────────────────────────


class TestTokenReuse:
    def test_approve_already_approved_token(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-030"
        _seed_token(tid, task_id, status="approved")

        _, status = _appr.approve_token(tid, task_id, "admin", "admin")
        assert status == "already_used"

    def test_approve_already_rejected_token(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-031"
        _seed_token(tid, task_id, status="rejected")

        _, status = _appr.approve_token(tid, task_id, "admin", "admin")
        assert status == "already_used"

    def test_reject_already_approved_token(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-032"
        _seed_token(tid, task_id, status="approved")

        _, status = _appr.reject_token(tid, task_id, "admin", "admin")
        assert status == "already_used"

    def test_second_approve_after_first(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-033"
        _seed_token(tid, task_id)

        _, s1 = _appr.approve_token(tid, task_id, "admin", "admin")
        _, s2 = _appr.approve_token(tid, task_id, "admin", "admin")

        assert s1 == "approved"
        assert s2 == "already_used"


# ── 5. 권한 부족(viewer) 차단 ──────────────────────────────────────────────


class TestForbiddenRole:
    def test_viewer_cannot_approve(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-040"
        _seed_token(tid, task_id)

        _, status = _appr.approve_token(tid, task_id, "viewer-user", "viewer")
        assert status == "forbidden"

    def test_viewer_cannot_reject(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-041"
        _seed_token(tid, task_id)

        _, status = _appr.reject_token(tid, task_id, "viewer-user", "viewer")
        assert status == "forbidden"

    def test_unknown_role_is_forbidden(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-042"
        _seed_token(tid, task_id)

        _, status = _appr.approve_token(tid, task_id, "some-user", "unknown_role")
        assert status == "forbidden"

    def test_approver_alias_maps_to_admin(self):
        """role='approver' 는 admin 으로 정규화되어 승인 가능."""
        tid = str(uuid.uuid4())
        task_id = "la-task-043"
        _seed_token(tid, task_id)

        _, status = _appr.approve_token(tid, task_id, "approver-user", "approver")
        assert status == "approved"


# ── 6. critical 정책 기본 차단 ─────────────────────────────────────────────


class TestCriticalPolicy:
    """critical 정책 차단 검증 (policy.evaluate_request 직접 호출)."""

    def test_critical_risk_is_blocked(self):
        import pathlib

        import yaml

        from ai_orchestrator.core.models import RiskAssessment, TaskRequest

        policy_path = pathlib.Path("ai_orchestrator/policies/default_policy.yaml")
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))

        req = TaskRequest(
            task_id="la-task-crit-001",
            source="manual",
            action_type="delete_all",
            target="/",
            description="destructive test",
            requested_by="test-user",
        )
        risk = RiskAssessment(risk_level="critical", reasons=["destructive"])

        result = _policy.evaluate_request(req, risk, policy)
        assert result.allowed is False
        assert any("critical" in r for r in result.blocked_reasons)

    def test_high_risk_not_blocked_but_requires_approval(self):
        import pathlib

        import yaml

        from ai_orchestrator.core.models import RiskAssessment, TaskRequest

        policy_path = pathlib.Path("ai_orchestrator/policies/default_policy.yaml")
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))

        req = TaskRequest(
            task_id="la-task-high-001",
            source="manual",
            action_type="run_shell",
            target="ls /tmp",
            description="shell test",
            requested_by="test-user",
        )
        risk = RiskAssessment(risk_level="high", reasons=["shell"], requires_approval=True)

        result = _policy.evaluate_request(req, risk, policy)
        assert result.allowed is False or result.requires_approval is True


# ── 7. audit 이벤트 기록 검증 ──────────────────────────────────────────────


class TestAuditEvents:
    def test_approve_writes_event_to_jsonl(self, isolated_approval_store: Path):
        tid = str(uuid.uuid4())
        task_id = "la-task-audit-001"
        _seed_token(tid, task_id)

        _appr.approve_token(tid, task_id, "admin", "admin")

        lines = [l for l in isolated_approval_store.read_text(encoding="utf-8").splitlines() if l.strip()]  # noqa: E741
        import json

        events = [json.loads(l) for l in lines]  # noqa: E741
        event_types = [e.get("event_type") for e in events]
        assert "token_approved" in event_types

    def test_reject_writes_event_to_jsonl(self, isolated_approval_store: Path):
        tid = str(uuid.uuid4())
        task_id = "la-task-audit-002"
        _seed_token(tid, task_id)

        _appr.reject_token(tid, task_id, "admin", "admin", reason="test-reject")

        import json

        lines = [l for l in isolated_approval_store.read_text(encoding="utf-8").splitlines() if l.strip()]  # noqa: E741
        events = [json.loads(l) for l in lines]  # noqa: E741
        event_types = [e.get("event_type") for e in events]
        assert "token_rejected" in event_types

    def test_not_found_does_not_write_event(self, isolated_approval_store: Path):
        fake_id = str(uuid.uuid4())
        _appr.approve_token(fake_id, "la-task-audit-003", "admin", "admin")

        assert not isolated_approval_store.exists() or isolated_approval_store.stat().st_size == 0

    def test_task_state_approve_writes_event(self, tmp_path, monkeypatch):
        # sys.modules 정리 후 로컬 재-import 시 NEW 모듈이 반환되어 패치가 엇갈리는 flaky 원인 방지:
        # 파일 레벨 _ts (항상 동일 모듈 객체)에 직접 패치한다.
        monkeypatch.setattr(_ts, "_STATE_PATH", tmp_path / "task_states.jsonl")
        _ts.clear()

        task_id = "la-task-audit-010"
        _ts.set_pending(
            task_id,
            risk_level="high",
            token_id="tok",
            requested_by="req",
            actor_role="admin",
            action_type="capture_screenshot",
            target="screen",
            task_snapshot={},
        )
        _ts.mark_approved(task_id, "admin", "admin")

        import json

        state_file = tmp_path / "task_states.jsonl"
        events = [json.loads(l) for l in state_file.read_text(encoding="utf-8").splitlines() if l.strip()]  # noqa: E741
        event_types = [e.get("event_type") for e in events]
        assert "TASK_APPROVED" in event_types


# ── 8. 실제 action 미실행 검증 ────────────────────────────────────────────


class TestNoActualExecution:
    def test_approve_token_does_not_call_subprocess(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-noexec-001"
        _seed_token(tid, task_id)

        blocked_calls: list = []

        with patch("subprocess.run", side_effect=lambda *a, **k: blocked_calls.append(a)):
            with patch("subprocess.Popen", side_effect=lambda *a, **k: blocked_calls.append(a)):
                with patch("os.system", side_effect=lambda *a, **k: blocked_calls.append(a)):
                    _appr.approve_token(tid, task_id, "admin", "admin")

        assert blocked_calls == [], "approve_token 이 실제 프로세스를 실행해서는 안 됨"

    def test_reject_token_does_not_call_subprocess(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-noexec-002"
        _seed_token(tid, task_id)

        blocked_calls: list = []

        with patch("subprocess.run", side_effect=lambda *a, **k: blocked_calls.append(a)):
            with patch("subprocess.Popen", side_effect=lambda *a, **k: blocked_calls.append(a)):
                with patch("os.system", side_effect=lambda *a, **k: blocked_calls.append(a)):
                    _appr.reject_token(tid, task_id, "admin", "admin")

        assert blocked_calls == [], "reject_token 이 실제 프로세스를 실행해서는 안 됨"

    def test_mark_approved_does_not_call_subprocess(self):
        task_id = "la-task-noexec-003"
        _ts.set_pending(
            task_id,
            risk_level="high",
            token_id="tok",
            requested_by="req",
            actor_role="admin",
            action_type="capture_screenshot",
            target="screen",
            task_snapshot={},
        )

        blocked_calls: list = []

        with patch("subprocess.run", side_effect=lambda *a, **k: blocked_calls.append(a)):
            _ts.mark_approved(task_id, "admin", "admin")

        assert blocked_calls == []

    def test_expired_token_approve_blocked_without_execution(self):
        tid = str(uuid.uuid4())
        task_id = "la-task-noexec-004"
        _seed_token(tid, task_id, expires_at=_past_iso(60))

        _, status = _appr.approve_token(tid, task_id, "admin", "admin")
        assert status == "expired"
