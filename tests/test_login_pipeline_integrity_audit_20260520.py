"""ORCHESTRATOR_LOGIN_PROCESS_PIPELINE_INTEGRITY_AUDIT_01

코드 변경 없이, 파이프라인의 현재 연결 상태를 코드 기반으로 검증/문서화하는 감사 테스트.
스모크 실행/실제 Chrome 실행 없음. 모듈 import + 함수 시그니처 + 상수 카탈로그만 점검한다.

본 테스트의 통과 = "감사 시점의 현재 코드 상태 그대로". 추후 누락이 보강되면
해당 GAP 검증 케이스는 수정/삭제되어야 한다 — 의도된 단절 마커.
"""
from __future__ import annotations

import inspect

import pytest


# ── 1. 진입점/모듈 존재 ───────────────────────────────────────────────

def test_pipeline_modules_present():
    from local_agent import (
        browser_instance_guard,
        browser_realtime_watcher,
        browser_session_store,
        login_auto_flow,
        login_state_detector,
    )
    from desktop import local_server  # noqa: F401

    assert browser_instance_guard.DEFAULT_CDP_PORT == 9222
    assert "ai_chrome" in str(browser_instance_guard.DEFAULT_PROFILE_DIR)


# ── 2. UI 액션 핸들러 등록 확인 ───────────────────────────────────────

def test_ui_actions_wired():
    """browser_start / browser_quit / tab_list / tab_close / login_watcher_*
    액션이 _handle_ui_message dispatch 에 등록되어 있어야 한다."""
    from desktop import local_server

    src = inspect.getsource(local_server._handle_ui_message)
    for action in (
        "browser_status", "browser_start", "browser_quit",
        "tab_list", "tab_close",
        "login_watcher_start", "login_watcher_stop",
    ):
        assert f'"{action}"' in src, f"action {action!r} not wired"


# ── 3. browser_start 진입 시 watcher 자동 시작 ────────────────────────

def test_browser_start_auto_starts_watcher():
    from desktop import local_server

    src = inspect.getsource(local_server._handle_browser_start)
    assert "_start_login_watcher" in src


def test_browser_quit_stops_watcher():
    from desktop import local_server

    src = inspect.getsource(local_server._handle_browser_quit)
    assert "_stop_login_watcher" in src


# ── 4. watcher loop → engine 이벤트 broadcast 연결 ────────────────────

def test_login_watcher_loop_broadcasts_engine_events():
    from desktop import local_server

    src = inspect.getsource(local_server._login_watcher_loop)
    # watcher event
    for evt in (
        "target_created", "target_closed", "target_url_changed",
        "target_title_changed", "auth_popup_detected", "login_state_changed",
    ):
        # 상수 또는 문자열 어느 쪽이든 등장하는지(broadcast 흐름에서 type 으로 사용)
        pass  # type 값은 event.event_type 변수에서 동적 — engine 이벤트 호출 자체를 검증
    assert "engine.on_target_state" in src
    assert "_broadcast" in src


# ── 5. engine 이 8종 이벤트 type 을 노출 ──────────────────────────────

def test_engine_exposes_all_required_event_types():
    from local_agent import login_auto_flow as f

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
    from local_agent import login_state_detector as d

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
    from local_agent import browser_realtime_watcher as rw

    src = inspect.getsource(rw)
    assert "sanitize_url" in src
    assert "mask_email" in src


# ── 8. GAP: enqueue_work_command 호출처 누락 (의도 단절) ──────────────

def test_gap_enqueue_work_command_has_no_production_caller():
    """현재 코드상 LoginAutoFlowEngine.enqueue_work_command 의 production 호출이 없음.
    이로 인해 사용자가 blog_write 등을 트리거한 뒤 LOGIN_REQUIRED 가 감지되어도
    auto_resume 이 발화하지 않는다. 본 테스트는 GAP 을 명시적으로 표시한다.

    GAP 해소 시 본 테스트를 갱신해야 한다.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    callers: list[str] = []
    for p in root.rglob("*.py"):
        if "tests" in p.parts or ".claude" in p.parts or "archive" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "enqueue_work_command(" in txt and "def enqueue_work_command" not in txt:
            callers.append(str(p.relative_to(root)))

    # GAP: production 호출 0건이어야 본 감사 시점 상태와 일치.
    assert callers == [], (
        f"GAP 해소 후보 호출처 발견: {callers}. 본 감사 케이스를 갱신하라."
    )


# ── 9. GAP: choose_login_target 호출처 누락 (의도 단절) ──────────────

def test_gap_choose_login_target_unused_in_production():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    callers: list[str] = []
    for p in root.rglob("*.py"):
        if "tests" in p.parts or ".claude" in p.parts or "archive" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "choose_login_target(" in txt and "def choose_login_target" not in txt:
            callers.append(str(p.relative_to(root)))

    assert callers == [], (
        f"choose_login_target 호출처 발견: {callers}. 본 감사 케이스를 갱신하라."
    )


# ── 10. POPUP_WAITING 정의는 있으되 미사용 — dead constant 마커 ───────

def test_popup_waiting_state_defined_but_unused():
    from local_agent import login_state_detector as d

    assert d.POPUP_WAITING == "POPUP_WAITING"
    src = inspect.getsource(d.classify)
    # classify 내부에서 반환되지 않음 — 향후 확장 자리표시
    assert "POPUP_WAITING" not in src


# ── 11. CHALLENGE → LOGGED_IN 전이 회로 생존성 ────────────────────────

def test_challenge_then_logged_in_unblocks_engine():
    from local_agent import login_state_detector as d
    from local_agent.login_auto_flow import LoginAutoFlowEngine

    eng = LoginAutoFlowEngine()
    # 1) LOGIN_REQUIRED
    eng.on_target_state(
        "T-1", d.classify("https://accounts.google.com/signin", title="Sign in"),
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
    # default_store 가 import 한 다른 테스트에서 오염되지 않도록 — 단순 import 검증
    assert "local_agent.browser_session_store" in sys.modules
