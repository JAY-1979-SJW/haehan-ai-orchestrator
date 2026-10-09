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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.agent_runtime.browser.login_state_detector import (
    CHALLENGE_REQUIRED,
    CONSENT_REQUIRED,
    LOGGED_IN,
    LOGIN_FAILED,
    LOGIN_IN_PROGRESS,
    LOGIN_REQUIRED,
    SESSION_EXPIRED,
    DetectionResult,
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
EVT_COMMAND_RESUME_FAILED = "command_resume_failed"

# resume_status 값
RESUME_PENDING = "pending"
RESUME_IN_PROGRESS = "in_progress"
RESUME_DONE = "done"
RESUME_FAILED = "failed"


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
    # 보강 필드 — production wiring 용 (ORCHESTRATOR_LOGIN_AUTO_RESUME_WIRING_01)
    source_action: str = ""
    task_id: str = ""
    original_payload: dict[str, Any] = field(default_factory=dict)
    login_state_at_enqueue: str = ""
    resume_status: str = "pending"


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
        # 중복 enqueue 방지: 이미 동일 command_id 가 pending/in_progress 면 무시.
        if self._pending is not None and self._pending.command_id == command.command_id:
            if self._pending.resume_status in ("pending", "in_progress"):
                return
        command.resume_status = command.resume_status or "pending"
        if not command.source_action:
            command.source_action = command.action
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
            events.append(
                Event(
                    type=EVT_ACCOUNT_PICKER_DETECTED,
                    target_id=target_id,
                    sanitized_url=detection.sanitized_url,
                    title=detection.title,
                )
            )

        if state == LOGIN_REQUIRED and not self._login_flow_active:
            self._login_flow_active = True
            self._login_target_id = target_id
            events.append(
                Event(
                    type=EVT_LOGIN_TARGET_SELECTED,
                    target_id=target_id,
                    sanitized_url=detection.sanitized_url,
                    title=detection.title,
                    extra={"reason": detection.reason},
                )
            )
            events.append(
                Event(
                    type=EVT_LOGIN_ACTION_STARTED,
                    target_id=target_id,
                    sanitized_url=detection.sanitized_url,
                    title=detection.title,
                )
            )
            events.append(self._plan_or_click_login_button(target_id, detection))
            return events

        if state == LOGIN_IN_PROGRESS:
            # 사용자가 직접 로그인 중 — 추가 click 시도하지 않음
            return events

        simple_event = self._simple_state_event(state, target_id, detection)
        if simple_event is not None:
            events.append(simple_event)
            return events

        if state == SESSION_EXPIRED:
            events.append(
                Event(
                    type=EVT_SESSION_EXPIRED,
                    target_id=target_id,
                    sanitized_url=detection.sanitized_url,
                    title=detection.title,
                )
            )
            # 만료 — 로그인 흐름 재진입 허용
            self._login_flow_active = False
            return events

        if state == LOGGED_IN:
            events.append(
                Event(
                    type=EVT_LOGGED_IN_DETECTED,
                    target_id=target_id,
                    sanitized_url=detection.sanitized_url,
                    title=detection.title,
                    extra={"user_hint": mask_email(detection.detected_user_hint or "")},
                )
            )
            # 로그인 흐름 종료 + 작업 재개 처리
            self._login_flow_active = False
            if self._pending is not None:
                events.append(self._resume_or_plan(self._pending))
            return events

        return events

    @staticmethod
    def _simple_state_event(state: str, target_id: str, detection: DetectionResult) -> Event | None:
        """challenge / consent / login_failed 상태의 단순 보고 이벤트 (그 외 상태는 None)."""
        if state == CHALLENGE_REQUIRED:
            return Event(
                type=EVT_CHALLENGE_REQUIRED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
                extra={"reason": detection.reason},
            )
        if state == CONSENT_REQUIRED:
            return Event(
                type=EVT_CONSENT_REQUIRED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
                extra={"reason": detection.reason},
            )
        if state == LOGIN_FAILED:
            return Event(
                type=EVT_LOGIN_FAILED,
                target_id=target_id,
                sanitized_url=detection.sanitized_url,
                title=detection.title,
            )
        return None

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
        except Exception:  # noqa: BLE001 - 로그인 자동 재개 흐름 -- 클릭/재개 실행기 예외 시 ok=False로 처리(성공으로 오판하지 않음, fail-closed)
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
        # 멱등성: 이미 done/failed 처리된 command 는 재실행하지 않음.
        if cmd.resume_status in (RESUME_DONE, RESUME_FAILED):
            return Event(
                type=EVT_COMMAND_RESUME_FAILED,
                target_id=cmd.target_id_hint,
                extra={
                    "command_id": cmd.command_id,
                    "reason": "ALREADY_RESOLVED",
                    "prev_status": cmd.resume_status,
                },
            )
        if self._resume_executor is None:
            cmd.resume_status = RESUME_PENDING
            return Event(
                type=EVT_AUTO_RESUME_PLANNED,
                target_id=cmd.target_id_hint,
                extra={
                    "command_id": cmd.command_id,
                    "action": cmd.action,
                    "reason": "NO_RESUME_EXECUTOR",
                },
            )
        cmd.resume_status = RESUME_IN_PROGRESS
        ok = False
        err = ""
        try:
            ok = bool(self._resume_executor(cmd))
        except Exception as exc:  # noqa: BLE001 - 로그인 자동 재개 흐름 -- 클릭/재개 실행기 예외 시 ok=False로 처리(성공으로 오판하지 않음, fail-closed)
            ok = False
            err = type(exc).__name__
        cmd.resume_status = RESUME_DONE if ok else RESUME_FAILED
        # 1회 자동 재개 후 pending 해제 (성공/실패 무관) — 중복 발화 방지
        self._pending = None
        if ok:
            return Event(
                type=EVT_COMMAND_AUTO_RESUMED,
                target_id=cmd.target_id_hint,
                extra={"command_id": cmd.command_id, "ok": True},
            )
        return Event(
            type=EVT_COMMAND_RESUME_FAILED,
            target_id=cmd.target_id_hint,
            extra={
                "command_id": cmd.command_id,
                "ok": False,
                "error": err or "RESUME_EXECUTOR_RETURNED_FALSE",
            },
        )
