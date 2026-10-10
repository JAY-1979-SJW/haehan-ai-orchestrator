"""site job_state 머신 검증 — RUNNING / PAUSED_FOR_REAUTH / RESUMABLE / DONE / FAILED."""
from __future__ import annotations

import pytest

from ai_orchestrator.sites import job_state


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path, monkeypatch):
    # LOG_DIR 을 tmp 로 돌려서 실 파일 오염 차단.
    monkeypatch.setattr(job_state, "_JOBS_PATH", tmp_path / "site_jobs.jsonl")
    job_state.clear()
    yield


def test_start_creates_running_job():
    rec = job_state.start(job_id="job-a", site_id="example_portal")
    assert rec.status == "RUNNING"
    assert rec.site_id == "example_portal"
    assert rec.created_at and rec.updated_at


def test_duplicate_start_is_idempotent():
    job_state.start(job_id="job-a", site_id="example_portal", current_step="step1")
    rec = job_state.start(job_id="job-a", site_id="example_portal", current_step="other")
    # 중복 start 는 기존 레코드 반환
    assert rec.current_step == "step1"


def test_pause_and_resume_transitions():
    job_state.start(job_id="job-a", site_id="example_portal", current_step="fetch")
    paused, status = job_state.pause_for_reauth(
        "job-a", current_step="fetch", cursor="page=3",
        paused_reason="redirected_to_login",
    )
    assert status == "paused_for_reauth"
    assert paused is not None
    assert paused.status == "PAUSED_FOR_REAUTH"
    assert paused.cursor == "page=3"
    assert paused.current_step == "fetch"

    # 중간 RESUMABLE 없이 바로 RUNNING 으로 가는 전이는 허용되지 않는다.
    _, invalid = job_state.resume("job-a")
    assert invalid.startswith("invalid_transition")

    resumable, status = job_state.mark_resumable("job-a")
    assert status == "resumable"
    assert resumable.status == "RESUMABLE"

    running, status = job_state.resume("job-a")
    assert status == "running"
    assert running.status == "RUNNING"


def test_done_is_terminal():
    job_state.start(job_id="job-b", site_id="example_portal")
    job_state.mark_done("job-b", result_summary="42 items")
    rec = job_state.get("job-b")
    assert rec.status == "DONE"
    assert rec.result_summary == "42 items"
    _, invalid = job_state.pause_for_reauth("job-b", current_step="x")
    assert invalid.startswith("invalid_transition")


def test_failed_from_paused():
    job_state.start(job_id="job-c", site_id="example_portal")
    job_state.pause_for_reauth("job-c", current_step="fetch")
    _, status = job_state.mark_failed("job-c", reason="reauth_timeout")
    assert status == "failed"
    assert job_state.get("job-c").status == "FAILED"


def test_list_by_status():
    job_state.start(job_id="job-r", site_id="s1")
    job_state.start(job_id="job-p", site_id="s2")
    job_state.pause_for_reauth("job-p", current_step="x")
    running = [j.job_id for j in job_state.list_by_status("RUNNING")]
    paused = [j.job_id for j in job_state.list_by_status("PAUSED_FOR_REAUTH")]
    assert "job-r" in running
    assert "job-p" in paused
