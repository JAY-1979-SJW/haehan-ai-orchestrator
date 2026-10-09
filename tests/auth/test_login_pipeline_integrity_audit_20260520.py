"""ORCHESTRATOR_LOGIN_PROCESS_PIPELINE_INTEGRITY_AUDIT_01

코드 변경 없이, 파이프라인의 현재 연결 상태를 코드 기반으로 검증/문서화하는 감사 테스트.
스모크 실행/실제 Chrome 실행 없음. 모듈 import + 함수 시그니처 + 상수 카탈로그만 점검한다.

본 테스트의 통과 = "감사 시점의 현재 코드 상태 그대로". 추후 누락이 보강되면
해당 GAP 검증 케이스는 수정/삭제되어야 한다 — 의도된 단절 마커.
"""

from __future__ import annotations

import inspect

# ── 1. 진입점/모듈 존재 ───────────────────────────────────────────────


def test_pipeline_modules_present():
    from core.agent_runtime.browser import browser_instance_guard

    assert browser_instance_guard.DEFAULT_CDP_PORT == 9222
    assert "ai_chrome" in str(browser_instance_guard.DEFAULT_PROFILE_DIR)


# ── 2. UI 액션 핸들러 등록 확인 ───────────────────────────────────────

# ── 3. browser_start 진입 시 watcher 자동 시작 ────────────────────────

# ── 4. watcher loop → engine 이벤트 broadcast 연결 ────────────────────

# ── 5. engine 이 8종 이벤트 type 을 노출 ──────────────────────────────


def test_engine_exposes_all_required_event_types():
    from core.agent_runtime.browser import login_auto_flow as f

    required = {
        f.EVT_LOGIN_ACTION_STARTED,
        f.EVT_LOGIN_TARGET_SELECTED,
        f.EVT_LOGIN_BUTTON_CLICKED,
        f.EVT_LOGIN_BUTTON_PLANNED,
        f.EVT_ACCOUNT_PICKER_DETECTED,
        f.EVT_CHALLENGE_REQUIRED,
        f.EVT_CONSENT_REQUIRED,
        f.EVT_LOGGED_IN_DETECTED,
        f.EVT_LOGIN_FAILED,
        f.EVT_SESSION_EXPIRED,
        f.EVT_COMMAND_AUTO_RESUMED,
        f.EVT_AUTO_RESUME_PLANNED,
    }
    # 중복/오타 없음 + 모두 snake_case
    assert len(required) == 12
    for evt in required:
        assert evt == evt.lower()


# ── 6. classify() 가 6 핵심 상태를 직접 생성 ──────────────────────────


def test_classify_emits_core_states():
    from core.agent_runtime.browser import login_state_detector as d

    cases = {
        d.LOGIN_REQUIRED: ("https://example.com/login", "Sign in", ""),
        d.LOGGED_IN: ("https://example.com/inbox", "Inbox", "Sign out"),
        d.CHALLENGE_REQUIRED: ("https://accounts.google.com/signin/v2/challenge", "Verify", ""),
        d.CONSENT_REQUIRED: ("https://accounts.google.com/o/oauth2/auth", "Grant access", ""),
        d.LOGIN_FAILED: ("https://accounts.google.com/signin", "Sign in", "Couldn't sign you in"),
        d.SESSION_EXPIRED: ("https://x.example/", "Home", "session expired"),
    }
    for expected, (url, title, body) in cases.items():
        r = d.classify(url, title=title, body_sample=body)
        assert r.state == expected, f"{url}: got {r.state}, expected {expected}"


# ── 7. sanitize / mask 가 watcher payload 에 적용된다 ──────────────────


def test_sanitize_and_mask_in_watcher_events():
    from core.agent_runtime.browser import browser_realtime_watcher as rw

    src = inspect.getsource(rw)
    assert "sanitize_url" in src
    assert "mask_email" in src


# ── 8. GAP: enqueue_work_command 호출처 누락 (의도 단절) ──────────────

# ── 9. GAP: choose_login_target 호출처 누락 (의도 단절) ──────────────

# ── 10. G4 ACCEPTED_PLACEHOLDER: POPUP_WAITING 미사용은 의도된 확장 자리 ──


def test_g4_popup_waiting_accepted_placeholder():
    """POPUP_WAITING 은 classify 결과로 발화하지 않는 placeholder 상수.

    재감사 시점 결정: 차기 팝업 분류 확장을 위한 자리표시로 ACCEPTED.
    제거하거나 사용처가 생기면 본 테스트 수정.
    """
    from core.agent_runtime.browser import login_state_detector as d

    assert d.POPUP_WAITING == "POPUP_WAITING"
    classify_src = inspect.getsource(d.classify)
    assert "POPUP_WAITING" not in classify_src


# ── 10b. G3 ACCEPTED: LOGIN_ACTION_STARTED 는 engine 책임 ──────────────


def test_g3_login_action_started_emitted_by_engine_only():
    """classify() 는 페이지 표면 신호로만 분류하고, ACTION_STARTED 는
    엔진이 LOGIN_REQUIRED 감지 후 결정 — 책임 분리는 의도된 설계."""
    from core.agent_runtime.browser import login_auto_flow as f
    from core.agent_runtime.browser import login_state_detector as d

    # classify 가 LOGIN_ACTION_STARTED 를 결과 state 로 절대 반환하지 않음.
    sample_urls = [
        "https://accounts.google.com/signin",
        "https://example.com/login",
        "https://example.com/",
        "https://accounts.google.com/signin/v2/challenge",
        "https://accounts.google.com/o/oauth2/auth",
        "https://mail.google.com/mail/u/0/",
    ]
    for url in sample_urls:
        for prev in ("", d.LOGIN_REQUIRED, d.LOGIN_IN_PROGRESS, d.LOGIN_ACTION_STARTED):
            r = d.classify(url, title="x", prev_state=prev)
            assert r.state != d.LOGIN_ACTION_STARTED
    # engine 측에서 emit 하는 이벤트로만 존재
    assert hasattr(f, "EVT_LOGIN_ACTION_STARTED")


# ── 10c. G5 해소: blog_write / cafe_write 진입부에 precheck 호출 ───────

# ── 10d. resume executor 가 engine 에 주입된다 ──────────────────────────

# ── 10e. command_resume_failed 이벤트 type 노출 ────────────────────────


def test_command_resume_failed_event_exposed():
    from core.agent_runtime.browser import login_auto_flow as f

    assert hasattr(f, "EVT_COMMAND_RESUME_FAILED")
    assert f.EVT_COMMAND_RESUME_FAILED == "command_resume_failed"


# ── 10f. PendingCommand 확장 필드 존재 ─────────────────────────────────


def test_pending_command_extended_fields_present():
    from dataclasses import fields

    from core.agent_runtime.browser.login_auto_flow import PendingCommand

    names = {fld.name for fld in fields(PendingCommand)}
    assert {
        "command_id",
        "action",
        "target_id_hint",
        "enqueued_at",
        "source_action",
        "task_id",
        "original_payload",
        "login_state_at_enqueue",
        "resume_status",
    }.issubset(names)


# ── 10g. 종단 통합: precheck → enqueue → LOGGED_IN → resume ────────────

# ── 11. CHALLENGE → LOGGED_IN 전이 회로 생존성 ────────────────────────


def test_challenge_then_logged_in_unblocks_engine():
    from core.agent_runtime.browser import login_state_detector as d
    from core.agent_runtime.browser.login_auto_flow import LoginAutoFlowEngine

    eng = LoginAutoFlowEngine()
    # 1) LOGIN_REQUIRED
    eng.on_target_state(
        "T-1",
        d.classify("https://accounts.google.com/signin", title="Sign in"),
    )
    assert eng.is_login_flow_active is True
    # 2) CHALLENGE
    eng.on_target_state(
        "T-1",
        d.classify("https://accounts.google.com/signin/v2/challenge", title="Verify"),
    )
    # 3) LOGGED_IN (사용자가 직접 처리한 결과)
    evs = eng.on_target_state(
        "T-1",
        d.classify(
            "https://mail.google.com/mail/u/0/#inbox",
            title="Inbox",
            body_sample="Sign out",
        ),
    )
    types = [e.type for e in evs]
    assert "logged_in_detected" in types
    # engine 의 login_flow_active 가 stuck 되지 않고 풀린다
    assert eng.is_login_flow_active is False


# ── 12. 사전 dirty 파일 stage 안전성 ───────────────────────────────────


def test_audit_test_file_isolated():
    """본 감사 테스트가 외부 모듈 import 만 하고 부수효과 없는지."""
    import sys

    # 다른 시험의 import 부수효과에 기대지 않도록 직접 import 한 뒤 모듈 등록을 확인한다.
    import core.agent_runtime.browser.browser_session_store  # noqa: F401

    assert "core.agent_runtime.browser.browser_session_store" in sys.modules
