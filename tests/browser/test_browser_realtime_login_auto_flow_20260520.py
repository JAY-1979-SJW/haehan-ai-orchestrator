"""ORCHESTRATOR_BROWSER_REALTIME_LOGIN_AUTO_FLOW_01 — 필수 테스트.

실제 Chrome/CDP/Playwright 미사용. 모든 함수는 pure 단위로 검증한다.
"""

from __future__ import annotations

from core.agent_runtime.browser import browser_realtime_watcher as rw
from core.agent_runtime.browser import login_state_detector as det
from core.agent_runtime.browser.login_auto_flow import (
    EVT_ACCOUNT_PICKER_DETECTED,
    EVT_AUTO_RESUME_PLANNED,
    EVT_CHALLENGE_REQUIRED,
    EVT_COMMAND_AUTO_RESUMED,
    EVT_CONSENT_REQUIRED,
    EVT_LOGGED_IN_DETECTED,
    EVT_LOGIN_ACTION_STARTED,
    EVT_LOGIN_BUTTON_CLICKED,
    EVT_LOGIN_BUTTON_PLANNED,
    EVT_LOGIN_FAILED,
    EVT_LOGIN_TARGET_SELECTED,
    LoginAutoFlowEngine,
    PendingCommand,
)

# ── login_state_detector ───────────────────────────────────────────


def test_login_required_when_on_signin_url():
    r = det.classify("https://example.com/login", title="로그인")
    assert r.state == det.LOGIN_REQUIRED


def test_logged_in_when_logout_signal():
    r = det.classify(
        "https://mail.google.com/mail/u/0/#inbox",
        title="Inbox - Gmail",
        body_sample="환영합니다 Sign out",
    )
    assert r.state == det.LOGGED_IN


def test_challenge_url_detected():
    r = det.classify(
        "https://accounts.google.com/signin/v2/challenge/totp",
        title="2-Step Verification",
    )
    assert r.state == det.CHALLENGE_REQUIRED


def test_consent_url_detected():
    r = det.classify(
        "https://accounts.google.com/o/oauth2/auth?scope=email",
        title="Grant access",
        body_sample="권한 허용 동의",
    )
    assert r.state == det.CONSENT_REQUIRED


def test_account_picker_url_pattern():
    r = det.classify(
        "https://accounts.google.com/signin/v2/identifier?continue=...",
        title="Choose an account",
    )
    assert r.is_account_picker is True
    assert r.state in (det.LOGIN_REQUIRED, det.LOGIN_IN_PROGRESS)


def test_session_expired_text_overrides():
    r = det.classify(
        "https://example.com/",
        title="Home",
        body_sample="세션이 만료되었습니다. 다시 로그인해 주세요.",
    )
    assert r.state == det.SESSION_EXPIRED


def test_login_failed_text():
    r = det.classify(
        "https://accounts.google.com/signin",
        title="Sign in",
        body_sample="Couldn't sign you in",
    )
    assert r.state == det.LOGIN_FAILED


def test_sanitize_url_strips_query_and_fragment():
    s = det.sanitize_url(
        "https://accounts.google.com/signin?token=abc&code=xyz#frag",
    )
    assert s == "https://accounts.google.com/signin"


def test_mask_email_partially():
    masked = det.mask_email("환영합니다 a@example.com — Sign out")
    assert "a@example.com" not in masked
    assert "***@example.com" in masked


# ── browser_realtime_watcher ───────────────────────────────────────


def _snap(tid, url="", title="", t=0.0):
    return rw.TargetSnapshot(target_id=tid, url=url, title=title, seen_at=t)


def test_target_created_and_auth_popup():
    prev = []
    curr = [_snap("T-1", "https://accounts.google.com/signin", "Sign in", t=1.0)]
    evs = rw.compute_events(prev, curr)
    types = [e.event_type for e in evs]
    assert rw.EVT_TARGET_CREATED in types
    assert rw.EVT_AUTH_POPUP_DETECTED in types


def test_target_closed():
    prev = [_snap("T-1", "https://example.com", t=1.0)]
    curr = []
    evs = rw.compute_events(prev, curr)
    assert any(e.event_type == rw.EVT_TARGET_CLOSED for e in evs)


def test_url_and_title_change():
    prev = [_snap("T-1", "https://example.com/", "A", t=1.0)]
    curr = [_snap("T-1", "https://example.com/inbox", "B", t=2.0)]
    evs = rw.compute_events(prev, curr)
    types = [e.event_type for e in evs]
    assert rw.EVT_TARGET_URL_CHANGED in types
    assert rw.EVT_TARGET_TITLE_CHANGED in types


def test_choose_login_target_prefers_auth_host():
    snaps = [
        _snap("T-work", "https://mail.google.com/mail/u/0/", t=1.0),
        _snap("T-auth", "https://accounts.google.com/signin", t=2.0),
    ]
    tid = rw.choose_login_target(snaps, work_target_id="T-work")
    assert tid == "T-auth"


def test_choose_login_target_uses_work_when_login_page():
    snaps = [
        _snap("T-work", "https://service.example/login", "Login", t=1.0),
    ]
    tid = rw.choose_login_target(snaps, work_target_id="T-work")
    assert tid == "T-work"


def test_from_cdp_targets_filters_non_page():
    rows = [
        {"id": "A", "type": "page", "url": "https://x", "title": "x"},
        {"id": "B", "type": "iframe", "url": "https://y", "title": "y"},
        {"id": "C", "type": "page", "url": "https://z", "title": "z"},
    ]
    out = rw.from_cdp_targets(rows)
    assert {s.target_id for s in out} == {"A", "C"}


def test_login_state_change_events_only_on_diff():
    prev_states = {"T-1": det.LOGIN_REQUIRED}
    curr = {
        "T-1": det.classify("https://example.com/", title="OK", body_sample="Sign out"),
        "T-2": det.classify("https://accounts.google.com/signin"),
    }
    evs = rw.login_state_change_events(prev_states, curr)
    types = [e.event_type for e in evs]
    assert all(t == rw.EVT_LOGIN_STATE_CHANGED for t in types)
    target_ids = sorted(e.target_id for e in evs)
    # T-1 변경(LOGIN_REQUIRED → LOGGED_IN) 및 T-2 신규(빈 prev → LOGIN_REQUIRED) 둘 다 변경
    assert target_ids == ["T-1", "T-2"]


# ── login_auto_flow ────────────────────────────────────────────────


def test_login_required_triggers_immediate_login_action():
    eng = LoginAutoFlowEngine()
    d = det.classify("https://accounts.google.com/signin", title="Sign in")
    evs = eng.on_target_state("T-auth", d)
    types = [e.type for e in evs]
    # 즉시 LOGIN_ACTION_STARTED 발생 — 대기 이벤트 없음
    assert EVT_LOGIN_TARGET_SELECTED in types
    assert EVT_LOGIN_ACTION_STARTED in types
    # click executor 미주입 → planned 이벤트
    assert EVT_LOGIN_BUTTON_PLANNED in types
    assert "command_waiting_for_login" not in types
    assert eng.is_login_flow_active is True
    assert eng.login_target_id == "T-auth"


def test_login_button_clicked_when_executor_provided():
    clicks: list[tuple[str, dict]] = []

    def click_fn(tid: str, plan: dict) -> bool:
        clicks.append((tid, plan))
        return True

    eng = LoginAutoFlowEngine(click_executor=click_fn)
    d = det.classify("https://example.com/login", title="Sign in")
    evs = eng.on_target_state("T-1", d)
    types = [e.type for e in evs]
    assert EVT_LOGIN_BUTTON_CLICKED in types
    assert clicks and clicks[0][0] == "T-1"


def test_account_picker_event_emitted():
    eng = LoginAutoFlowEngine()
    d = det.classify(
        "https://accounts.google.com/signin/v2/identifier",
        title="Choose an account",
    )
    evs = eng.on_target_state("T-pick", d)
    assert any(e.type == EVT_ACCOUNT_PICKER_DETECTED for e in evs)


def test_challenge_required_keeps_watcher_no_auto_input():
    eng = LoginAutoFlowEngine()
    d = det.classify(
        "https://accounts.google.com/signin/v2/challenge/totp",
        title="2-Step Verification",
    )
    evs = eng.on_target_state("T-ch", d)
    assert any(e.type == EVT_CHALLENGE_REQUIRED for e in evs)
    # OTP 자동 입력/우회 이벤트 없음
    assert all("otp" not in e.type.lower() for e in evs)


def test_consent_required_event():
    eng = LoginAutoFlowEngine()
    d = det.classify(
        "https://accounts.google.com/o/oauth2/auth",
        title="Grant access",
        body_sample="권한 허용",
    )
    evs = eng.on_target_state("T-co", d)
    assert any(e.type == EVT_CONSENT_REQUIRED for e in evs)


def test_logged_in_then_command_auto_resumed():
    resumed: list[PendingCommand] = []

    def resume_fn(cmd: PendingCommand) -> bool:
        resumed.append(cmd)
        return True

    eng = LoginAutoFlowEngine(resume_executor=resume_fn)
    eng.enqueue_work_command(PendingCommand(command_id="C-1", action="blog_write"))

    # 1) 로그인 흐름 시작
    eng.on_target_state(
        "T-1",
        det.classify("https://accounts.google.com/signin", title="Sign in"),
    )
    # 2) 로그인 완료 감지
    evs = eng.on_target_state(
        "T-1",
        det.classify(
            "https://mail.google.com/mail/u/0/#inbox",
            title="Inbox",
            body_sample="Sign out",
        ),
    )
    types = [e.type for e in evs]
    assert EVT_LOGGED_IN_DETECTED in types
    assert EVT_COMMAND_AUTO_RESUMED in types
    assert resumed and resumed[0].command_id == "C-1"


def test_logged_in_without_resume_executor_emits_auto_resume_planned():
    eng = LoginAutoFlowEngine()
    eng.enqueue_work_command(PendingCommand(command_id="C-X", action="navigate"))
    eng.on_target_state(
        "T-1",
        det.classify("https://example.com/login", title="Login"),
    )
    evs = eng.on_target_state(
        "T-1",
        det.classify(
            "https://example.com/inbox",
            title="Inbox",
            body_sample="로그아웃",
        ),
    )
    types = [e.type for e in evs]
    assert EVT_LOGGED_IN_DETECTED in types
    assert EVT_AUTO_RESUME_PLANNED in types


def test_login_failed_event():
    eng = LoginAutoFlowEngine()
    d = det.classify(
        "https://accounts.google.com/signin",
        title="Sign in",
        body_sample="Couldn't sign you in",
    )
    evs = eng.on_target_state("T-1", d)
    assert any(e.type == EVT_LOGIN_FAILED for e in evs)


def test_user_does_not_have_to_confirm_login_manually():
    """사용자 수동 입력 없이 상태만으로 LOGGED_IN 으로 자동 전이."""
    eng = LoginAutoFlowEngine()
    eng.on_target_state(
        "T-1",
        det.classify("https://example.com/login", title="Login"),
    )
    evs = eng.on_target_state(
        "T-1",
        det.classify("https://example.com/", title="Home", body_sample="Sign out"),
    )
    # "사용자 확인 요청" 류 이벤트가 없어야 한다
    forbidden_substrings = ("waiting_for_login", "ask_user", "prompt_user")
    for e in evs:
        for s in forbidden_substrings:
            assert s not in e.type.lower()
    assert any(e.type == EVT_LOGGED_IN_DETECTED for e in evs)


def test_sanitized_url_no_token_in_events():
    eng = LoginAutoFlowEngine()
    d = det.classify(
        "https://accounts.google.com/signin?token=SECRETTOKEN&code=XXX",
        title="Sign in",
    )
    evs = eng.on_target_state("T-1", d)
    for e in evs:
        assert "SECRETTOKEN" not in (e.sanitized_url or "")
        assert "token=" not in (e.sanitized_url or "")
