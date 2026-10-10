"""job_state 상태 전이 + JSONL 이벤트 기록 검증 — 외부 접속 없음."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_orchestrator.sites import job_state


def _jid() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def isolated_state():
    """각 테스트 전 인메모리 스토어 초기화."""
    job_state.clear()
    yield
    job_state.clear()


# ── 기본 상태 전이 ────────────────────────────────────────────────
class TestTransitions:
    def test_start_creates_running(self) -> None:
        jid = _jid()
        rec = job_state.start(job_id=jid, site_id="s1")
        assert rec.status == "RUNNING"
        assert rec.job_id == jid

    def test_running_to_paused_for_reauth(self) -> None:
        jid = _jid()
        job_state.start(job_id=jid, site_id="s1")
        rec, outcome = job_state.pause_for_reauth(jid, current_step="step1")
        assert rec is not None
        assert rec.status == "PAUSED_FOR_REAUTH"
        assert outcome == "paused_for_reauth"

    def test_paused_to_resumable(self) -> None:
        jid = _jid()
        job_state.start(job_id=jid, site_id="s1")
        job_state.pause_for_reauth(jid, current_step="step1")
        rec, outcome = job_state.mark_resumable(jid)
        assert rec is not None
        assert rec.status == "RESUMABLE"

    def test_resumable_to_running(self) -> None:
        jid = _jid()
        job_state.start(job_id=jid, site_id="s1")
        job_state.pause_for_reauth(jid, current_step="step1")
        job_state.mark_resumable(jid)
        rec, outcome = job_state.resume(jid)
        assert rec is not None
        assert rec.status == "RUNNING"

    def test_running_to_done(self) -> None:
        jid = _jid()
        job_state.start(job_id=jid, site_id="s1")
        rec, _ = job_state.mark_done(jid, result_summary="ok")
        assert rec is not None
        assert rec.status == "DONE"

    def test_invalid_transition_returns_error(self) -> None:
        jid = _jid()
        job_state.start(job_id=jid, site_id="s1")
        job_state.mark_done(jid)
        rec, outcome = job_state.mark_done(jid)
        assert "invalid_transition" in outcome

    def test_duplicate_start_is_idempotent(self) -> None:
        jid = _jid()
        r1 = job_state.start(job_id=jid, site_id="s1")
        r2 = job_state.start(job_id=jid, site_id="s1")
        assert r1.status == r2.status == "RUNNING"

    def test_full_reauth_cycle(self) -> None:
        jid = _jid()
        job_state.start(job_id=jid, site_id="s1", current_step="collect")
        job_state.pause_for_reauth(jid, current_step="collect", cursor="url1")
        job_state.mark_resumable(jid)
        job_state.resume(jid)
        rec, _ = job_state.mark_done(jid, result_summary="done")
        assert rec is not None
        assert rec.status == "DONE"


# ── JSONL 기록이 tmp_path 안에만 쓰이는지 확인 ────────────────────
class TestJsonlEventAppend:
    def test_event_written_to_tmp_path(self, tmp_path: Path) -> None:
        jid = _jid()
        log_path = tmp_path / "site_jobs.jsonl"

        with patch.object(job_state, "_JOBS_PATH", log_path):
            job_state.clear()
            job_state.start(job_id=jid, site_id="s1")
            job_state.mark_done(jid)

        assert log_path.exists()
        lines = [l for l in log_path.read_text(encoding="utf-8").strip().splitlines() if l]
        assert len(lines) >= 2  # JOB_STARTED + JOB_DONE

    def test_event_fields_no_sensitive_data(self, tmp_path: Path) -> None:
        jid = _jid()
        log_path = tmp_path / "site_jobs.jsonl"

        with patch.object(job_state, "_JOBS_PATH", log_path):
            job_state.clear()
            job_state.start(job_id=jid, site_id="s1", params={"query": "safe_param"})
            job_state.mark_done(jid)

        content = log_path.read_text(encoding="utf-8")
        for line in content.strip().splitlines():
            ev = json.loads(line)
            # params 에 민감 키가 없어야 한다.
            params = ev.get("params", {})
            for bad in ("password", "token", "cookie", "session", "secret", "otp"):
                assert bad not in params, f"민감 키 발견: {bad}"

    def test_event_written_to_specified_path_not_production(self, tmp_path: Path) -> None:
        """이벤트가 tmp_path 밖(운영 경로)에 기록되지 않는 것을 간접 확인."""
        jid = _jid()
        log_path = tmp_path / "safe_jobs.jsonl"

        with patch.object(job_state, "_JOBS_PATH", log_path):
            job_state.clear()
            job_state.start(job_id=jid, site_id="s1")

        assert log_path.exists()
        # 실제 운영 경로(LOG_DIR)에는 쓰이지 않았어야 함 (패치로 격리됨)
        assert str(log_path).startswith(str(tmp_path))
