"""로그인 자동 흐름 엔진 — LOGIN_REQUIRED 감지 즉시 로그인 흐름 시작.

핵심:
  - 사용자에게 "로그인 됐나요?" 라고 묻지 않는다.
  - LOGIN_REQUIRED 감지 시 즉시 LOGIN_ACTION_STARTED 로 전환.
  - 로그인 target 선택 → 로그인 버튼 클릭 계획 → click_executor 가 있으면 실행.
  - CHALLENGE_REQUIRED / CONSENT_REQUIRED 는 자동 우회하지 않고 상태만 전달.
  - LOGGED_IN 감지 시 대기 중이던 원래 명령을 자동 재개(executor 가 있으면)
    또는 auto_resume_planned 이벤트 발행.

대표 결정 필요 항목(본 모듈은 결정하지 않음):
  - OTP/패스키/생체인증 자동 처리 — 모두 CHALLENGE_REQUIRED 로 표시만.
  - 쿠키/토큰 저장 또는 재사용 — 본 모듈 미관여.
  - 사이트별 로그인 자동화 깊이 — 본 모듈은 "로그인 버튼 1회 클릭" 까지만 계획.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from local_agent.login_state_detector import (
    CHALLENGE_REQUIRED,
    CONSENT_REQUIRED,
    DetectionResult,
    LOGGED_IN,
    LOGIN_ACTION_STARTED,
    LOGIN_FAILED,
    LOGIN_IN_PROGRESS,
    LOGIN_REQUIRED,
    SESSION_EXPIRED,
    mask_email,
)


# ── 이벤트 type 상수 ─────────────────────────────────────────────────

EVT_LOGIN_ACTION_STARTED = "login_action_started"
EVT_LOGIN_TARGET_SELECTED = "login_target_selected"
EVT_LOGIN_BUTTON_CLICKED = "login_button_clicked"
EVT_LOGIN_BUTTON_PLANNED = "login_button_planned"
EVT_ACCOUNT_PICKER_DETECTED = "account_picker_detected"
EVT_CHALLENGE_REQUIRED = "challenge_required"
EVT_CONSENT_REQUIRED = "consent_required"
EVT_LOGGED_IN_DETECTED = "logged_in_detected"
EVT_LOGIN_FAILED = "login_failed"
EVT_SESSION_EXPIRED = "session_expired"
EVT_COMMAND_AUTO_RESUMED = "command_auto_resumed"
EVT_AUTO_RESUME_PLANNED = "auto_resume_planned"


# ── 로그인 버튼 후보 (selector + 텍스트) ─────────────────────────────

LOGIN_BUTTON_CANDIDATES = [
    {"kind": "text", "needle": "Sign in", "weight": 9},
    {"kind": "text", "needle": "Sign In", "weight": 9},
    {"kind": "text", "needle": "Log in", "weight": 9},
    {"kind": "text", "needle": "Login", "weight": 9},
    {"kind": "text", "needle": "로그인", "weight": 10},
    {"kind": "text", "needle": "Google로 로그인", "weight": 10},
    {"kind": "text", "needle": "Sign in with Google", "weight": 10},
    {"kind": "selector", "value": "a[href*='login' i]", "weight": 7},
    {"kind": "selector", "value": "a[href*='signin' i]", "weight": 7},
    {"kind": "selector", "value": "button[aria-label*='login' i]", "weight": 6},
    {"kind": "selector", "value": "button[aria-label*='sign in' i]", "weight": 6},
    {"kind": "selector", "value": "[data-action*='login' i]", "weight": 5},
]


# ── 데이터 ───────────────────────────────────────────────────────────

@dataclass
class Event:
    type: str
    target_id: str = ""
    sanitized_url: str = ""
    title: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PendingCommand:
    command_id: str
    action: str
    target_id_hint: str = ""
    enqueued_at: float = 0.0


# ── 엔진 ─────────────────────────────────────────────────────────────

class LoginAutoFlowEngine:
    """target 단위 로그인 상태 추적 + 자동 흐름 트리거.

    click_executor / resume_executor 가 주입되면 즉시 실행,
    없으면 계획(planned) 이벤트로 끝낸다.
    """

    def __init__(
        self,
        *,
        click_executor: Callable[[str, dict[str, Any]], bool] | None = None,
        resume_executor: Callable[[PendingCommand], bool] | None = None,
    ) -> None:
        self._states: dict[str, str] = {}  # target_id → state
        self._login_target_id: str = ""
        self._login_flow_active: bool = False
        self._pending: PendingCommand | None = None
        self._click_executor = click_executor
        self._resume_executor = resume_executor

    # ── 명령 등록 ──────────────────────────────────────────────────

    def enqueue_work_command(self, command: PendingCommand) -> None:
        self._pending = command

    @property
    def pending_command(self) -> PendingCommand | None:
        return self._pending

    @property
    def login_target_id(self) -> str:
        return self._login_target_id

    @property
    def is_login_flow_active(self) -> bool:
        return self._login_flow_active

    # ── 상태 입력 ──────────────────────────────────────────────────

    def on_target_state(
        self,
        target_id: str,
        detection: DetectionResult,
    ) -> list[Event]:
        """target 의 로그인 상태 변화를 받아 이벤트 목록을 반환한다."""
        events: list[Event] = []
        prev = self._states.get(target_id, "")
        state = detection.state
        self._states[target_id] = state

        if state == prev:
            return events

        # account picker 는 어느 상태에서든 즉시 보고
        if detection.is_account_picker:
            events.append(Event(
                type=EVT_ACCOUNT_PICKER_DETECTED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
            ))

        if state == LOGIN_REQUIRED and not self._login_flow_active:
            self._login_flow_active = True
            self._login_target_id = target_id
            events.append(Event(
                type=EVT_LOGIN_TARGET_SELECTED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
                extra={"reason": detection.reason},
            ))
            events.append(Event(
                type=EVT_LOGIN_ACTION_STARTED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
            ))
            events.append(self._plan_or_click_login_button(target_id, detection))
            return events

        if state == LOGIN_IN_PROGRESS:
            # 사용자가 직접 로그인 중 — 추가 click 시도하지 않음
            return events

        if state == CHALLENGE_REQUIRED:
            events.append(Event(
                type=EVT_CHALLENGE_REQUIRED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
                extra={"reason": detection.reason},
            ))
            return events

        if state == CONSENT_REQUIRED:
            events.append(Event(
                type=EVT_CONSENT_REQUIRED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
                extra={"reason": detection.reason},
            ))
            return events

        if state == LOGIN_FAILED:
            events.append(Event(
                type=EVT_LOGIN_FAILED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
            ))
            return events

        if state == SESSION_EXPIRED:
            events.append(Event(
                type=EVT_SESSION_EXPIRED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
            ))
            # 만료 — 로그인 흐름 재진입 허용
            self._login_flow_active = False
            return events

        if state == LOGGED_IN:
            events.append(Event(
                type=EVT_LOGGED_IN_DETECTED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
                extra={"user_hint": mask_email(detection.detected_user_hint or "")},
            ))
            # 로그인 흐름 종료 + 작업 재개 처리
            self._login_flow_active = False
            if self._pending is not None:
                events.append(self._resume_or_plan(self._pending))
            return events

        return events

    # ── 내부: 로그인 버튼 클릭 / 계획 ──────────────────────────────

    def _plan_or_click_login_button(
        self,
        target_id: str,
        detection: DetectionResult,
    ) -> Event:
        plan = {
            "candidates": LOGIN_BUTTON_CANDIDATES,
            "max_attempts": 1,
            "reason_to_click": detection.reason,
        }
        if self._click_executor is None:
            return Event(
                type=EVT_LOGIN_BUTTON_PLANNED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
                extra={"plan": plan},
            )
        try:
            ok = bool(self._click_executor(target_id, plan))
        except Exception:
            ok = False
        return Event(
            type=EVT_LOGIN_BUTTON_CLICKED,
            target_id=target_id,
            sanitized_url=detection.sanitized_url,
            title=detection.title,
            extra={"ok": ok, "plan": plan},
        )

    # ── 내부: 작업 재개 ──────────────────────────────────────────────

    def _resume_or_plan(self, cmd: PendingCommand) -> Event:
        if self._resume_executor is None:
            return Event(
                type=EVT_AUTO_RESUME_PLANNED,
                target_id=cmd.target_id_hint,
                extra={"command_id": cmd.command_id, "action": cmd.action},
            )
        try:
            ok = bool(self._resume_executor(cmd))
        except Exception:
            ok = False
        # 1회 자동 재개 후 pending 해제
        self._pending = None
        return Event(
            type=EVT_COMMAND_AUTO_RESUMED,
            target_id=cmd.target_id_hint,
            extra={"command_id": cmd.command_id, "ok": ok},
        )
