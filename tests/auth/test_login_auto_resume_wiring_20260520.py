"""ORCHESTRATOR_LOGIN_AUTO_RESUME_WIRING_01 — production wiring 단위 검증.

실제 Chrome / 네이버 / 구글 호출 없음. 모두 monkeypatch 로 시뮬레이션.
"""

from __future__ import annotations

import asyncio

from core.agent_runtime.browser import login_state_detector as det
from core.agent_runtime.browser.login_auto_flow import (
    EVT_COMMAND_AUTO_RESUMED,
    EVT_COMMAND_RESUME_FAILED,
    EVT_LOGGED_IN_DETECTED,
    RESUME_DONE,
    LoginAutoFlowEngine,
    PendingCommand,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── 1. PendingCommand 확장 필드 ──────────────────────────────────────


def test_pending_command_has_extended_fields():
    cmd = PendingCommand(
        command_id="c1",
        action="blog_write",
        original_payload={"title": "T"},
        login_state_at_enqueue="LOGIN_REQUIRED",
    )
    assert cmd.original_payload == {"title": "T"}
    assert cmd.login_state_at_enqueue == "LOGIN_REQUIRED"
    assert cmd.resume_status == "pending"


# ── 2. blog_write precheck 시 enqueue 호출 ───────────────────────────

# ── 3. cafe_write precheck — 동일 패턴 ───────────────────────────────

# ── 4. LOGGED_IN 감지 시 pending command 자동 재개 ───────────────────


def test_logged_in_triggers_command_auto_resumed_via_executor():
    eng = LoginAutoFlowEngine()
    resumed: list[PendingCommand] = []

    def resume_fn(cmd: PendingCommand) -> bool:
        resumed.append(cmd)
        return True

    eng._resume_executor = resume_fn
    eng.enqueue_work_command(
        PendingCommand(
            command_id="c1",
            action="blog_write",
            original_payload={"title": "T"},
            login_state_at_enqueue=det.LOGIN_REQUIRED,
        )
    )
    # LOGIN_REQUIRED → LOGGED_IN
    eng.on_target_state(
        "T-1",
        det.classify("https://accounts.google.com/signin", title="Sign in"),
    )
    evs = eng.on_target_state(
        "T-1",
        det.classify(
            "https://mail.google.com/mail/u/0/",
            title="Inbox",
            body_sample="Sign out",
        ),
    )
    types = [e.type for e in evs]
    assert EVT_LOGGED_IN_DETECTED in types
    assert EVT_COMMAND_AUTO_RESUMED in types
    assert len(resumed) == 1
    assert resumed[0].resume_status == RESUME_DONE


# ── 5. 중복 LOGGED_IN 이벤트에도 재개 1회 ────────────────────────────


def test_duplicate_logged_in_resumes_only_once():
    eng = LoginAutoFlowEngine()
    calls = []

    def resume_fn(cmd: PendingCommand) -> bool:
        calls.append(cmd.command_id)
        return True

    eng._resume_executor = resume_fn
    eng.enqueue_work_command(PendingCommand(command_id="c1", action="blog_write"))
    eng.on_target_state(
        "T-1",
        det.classify("https://example.com/login", title="Login"),
    )
    eng.on_target_state(
        "T-1",
        det.classify("https://example.com/", title="Home", body_sample="Sign out"),
    )
    # LOGGED_IN 한 번 더 발생 시도 — 동일 상태 유지이므로 on_target_state 가
    # 새로운 LOGGED_IN 이벤트를 만들지 않아야 한다.
    evs2 = eng.on_target_state(
        "T-1",
        det.classify("https://example.com/", title="Home", body_sample="Sign out"),
    )
    assert all(e.type != EVT_COMMAND_AUTO_RESUMED for e in evs2)
    assert len(calls) == 1


# ── 6. enqueue 중복 호출 무시 ────────────────────────────────────────


def test_enqueue_same_command_id_is_idempotent():
    eng = LoginAutoFlowEngine()
    eng.enqueue_work_command(
        PendingCommand(
            command_id="c1",
            action="blog_write",
            original_payload={"v": 1},
        )
    )
    eng.enqueue_work_command(
        PendingCommand(
            command_id="c1",
            action="blog_write",
            original_payload={"v": 2},
        )
    )
    # 첫 enqueue 가 유지됨
    assert eng.pending_command is not None
    assert eng.pending_command.original_payload == {"v": 1}


# ── 7. resume executor 실패 시 RESUME_FAILED ─────────────────────────


def test_resume_failure_emits_command_resume_failed():
    eng = LoginAutoFlowEngine()

    def fail_resume(cmd: PendingCommand) -> bool:
        return False

    eng._resume_executor = fail_resume
    eng.enqueue_work_command(PendingCommand(command_id="cF", action="blog_write"))
    eng.on_target_state(
        "T-1",
        det.classify("https://example.com/login", title="Login"),
    )
    evs = eng.on_target_state(
        "T-1",
        det.classify("https://example.com/", title="Home", body_sample="Sign out"),
    )
    types = [e.type for e in evs]
    assert EVT_COMMAND_RESUME_FAILED in types


# ── 8. resume 후 pending 해제로 중복 발화 방지 ─────────────────────────


def test_pending_cleared_after_resume():
    eng = LoginAutoFlowEngine()
    eng._resume_executor = lambda cmd: True
    eng.enqueue_work_command(PendingCommand(command_id="c1", action="blog_write"))
    eng.on_target_state(
        "T-1",
        det.classify("https://example.com/login", title="Login"),
    )
    eng.on_target_state(
        "T-1",
        det.classify("https://example.com/", title="Home", body_sample="Sign out"),
    )
    assert eng.pending_command is None


# ── 9. _from_resume 페이로드는 precheck 통과 ──────────────────────────

# ── 10. 로그인 차단 상태가 없으면 정상 실행 (precheck 통과) ──────────
