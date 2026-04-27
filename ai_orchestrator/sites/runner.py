"""사이트 자동화 job 러너.

역할:
    - job 시작 전 세션 유효성 확인 (ensure_session)
    - 세션 만료면 open_login_page + wait_for_human_reauth
    - 재인증 성공 시 RESUMABLE → RUNNING 으로 복귀
    - 재인증 실패 시 FAILED 처리 (작업 자체는 PAUSED 상태로 남기는 것이 안전하다면
      그대로 유지하도록 선택 가능)

이 러너는 **의존성 주입 중심**이다: Page/SiteAdapter/시간 함수를 모두 주입 받아
테스트에서 Playwright 없이 동작할 수 있다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import job_state, session_manager
from .site_adapter import LoginCheckResult, SiteAdapter

logger = logging.getLogger(__name__)


@dataclass
class EnsureSessionResult:
    """ensure_session 결과. ok=True 면 세션이 ACTIVE 이고 작업 진행 가능."""
    ok: bool
    status_message: str          # 사용자/UI 에 노출 가능한 짧은 메시지 (민감 원문 없음)
    login_check: Optional[LoginCheckResult] = None
    paused: bool = False         # 세션 만료로 job 이 PAUSED 상태로 전이됐는가


# 사용자/대시보드에 그대로 노출해도 되는 상태 메시지 (민감 원문 미포함).
MSG_SESSION_ACTIVE = "SESSION_ACTIVE"
MSG_SESSION_EXPIRED = "SESSION_EXPIRED_REAUTH_REQUIRED"
MSG_REAUTH_IN_PROGRESS = "REAUTH_IN_PROGRESS"
MSG_REAUTH_SUCCESS = "REAUTH_SUCCESS_RESUMING"
MSG_JOB_RESUMED = "JOB_RESUMED"
MSG_REAUTH_TIMED_OUT = "REAUTH_TIMED_OUT"


def ensure_session(
    adapter: SiteAdapter,
    page: Any,
    *,
    job_id: str,
    auto_reauth: bool = True,
    reauth_timeout_sec: Optional[int] = None,
    sleeper: Any = None,
    clock: Any = None,
) -> EnsureSessionResult:
    """작업 시작 전 세션 유효성 확인 + 필요 시 재인증 대기.

    흐름:
        1. adapter.open_home(page)
        2. adapter.check_logged_in(page)
        3. 로그인 상태면 mark_active → ok=True
        4. 미로그인이면:
            - auto_reauth=False 이면 세션 EXPIRED 로 표시하고 ok=False 즉시 반환
            - auto_reauth=True  이면 open_login_page → wait_for_human_reauth
                → 성공: mark_reauth_success, ok=True
                → 실패: mark_reauth_required (paused_job_id 보존) 후 ok=False
    """
    site_id = adapter.site_id

    # 1~2. home 진입 + 로그인 판정
    try:
        adapter.open_home(page)
    except Exception as e:  # noqa: BLE001
        logger.warning("[ENSURE-SESSION] open_home 실패 site=%s err=%s",
                       site_id, type(e).__name__)
        session_manager.mark_expired(site_id, reason="open_home_failed")
        return EnsureSessionResult(
            ok=False, status_message=MSG_SESSION_EXPIRED, paused=False,
        )

    check = adapter.check_logged_in(page)

    # 3. ACTIVE
    if check.is_logged_in:
        session_manager.mark_active(site_id, detected_url=check.detected_url)
        return EnsureSessionResult(
            ok=True, status_message=MSG_SESSION_ACTIVE, login_check=check,
        )

    # 4. 미로그인
    if not auto_reauth:
        session_manager.mark_reauth_required(
            site_id,
            reason=check.reason or "not_logged_in",
            detected_url=check.detected_url,
            paused_job_id=job_id,
        )
        return EnsureSessionResult(
            ok=False, status_message=MSG_SESSION_EXPIRED,
            login_check=check, paused=False,
        )

    # 4-a. 재인증 유도 + 대기
    session_manager.mark_reauth_required(
        site_id,
        reason=check.reason or "not_logged_in",
        detected_url=check.detected_url,
        paused_job_id=job_id,
    )
    try:
        adapter.open_login_page(page)
    except Exception as e:  # noqa: BLE001
        logger.warning("[ENSURE-SESSION] open_login_page 실패 site=%s err=%s",
                       site_id, type(e).__name__)
        return EnsureSessionResult(
            ok=False, status_message=MSG_SESSION_EXPIRED,
            login_check=check, paused=False,
        )

    logger.info("[ENSURE-SESSION] %s site=%s job=%s",
                MSG_REAUTH_IN_PROGRESS, site_id, job_id)
    wait = adapter.wait_for_human_reauth(
        page,
        timeout_sec=reauth_timeout_sec,
        sleeper=sleeper,
        clock=clock,
    )
    if wait.succeeded and wait.last_check:
        session_manager.mark_reauth_success(
            site_id, detected_url=wait.last_check.detected_url,
        )
        return EnsureSessionResult(
            ok=True, status_message=MSG_REAUTH_SUCCESS,
            login_check=wait.last_check,
        )

    # 타임아웃 또는 실패 — paused_job_id 유지, 세션은 REAUTH_REQUIRED 로 남긴다.
    session_manager.mark_reauth_required(
        site_id,
        reason="reauth_timed_out" if wait.timed_out else "reauth_failed",
        detected_url=(wait.last_check.detected_url if wait.last_check else ""),
        paused_job_id=job_id,
    )
    return EnsureSessionResult(
        ok=False, status_message=MSG_REAUTH_TIMED_OUT,
        login_check=wait.last_check, paused=False,
    )


def run_with_session(
    adapter: SiteAdapter,
    page: Any,
    *,
    job_id: str,
    site_id: str,
    work: Callable[[Any], str],
    current_step: str = "main",
    params: Optional[dict] = None,
    auto_reauth: bool = True,
    reauth_timeout_sec: Optional[int] = None,
    sleeper: Any = None,
    clock: Any = None,
) -> str:
    """job 하나를 세션 체크 → 실행 → 완료/일시정지 흐름으로 돌린다.

    `work(page) -> str` 는 실제 비즈니스 로직. 반환 문자열은 result_summary 로 저장된다.
    세션이 ensure 되면 RUNNING 상태로 실행하고, DONE 또는 FAILED 로 종료한다.
    세션 ensure 가 실패하면 job 을 PAUSED_FOR_REAUTH 로 보존하고 상태 메시지를 반환한다.

    반환값: 현재 상태 메시지 (MSG_*). 호출자는 메시지를 사용자에게 그대로 보여도 안전.
    """
    # job 등록 (idempotent)
    rec = job_state.start(
        job_id=job_id, site_id=site_id,
        current_step=current_step, params=params or {},
    )

    # 재개 경로: 이미 RESUMABLE 이면 RUNNING 으로 전이
    if rec.status == "RESUMABLE":
        job_state.resume(job_id)

    ensured = ensure_session(
        adapter, page,
        job_id=job_id,
        auto_reauth=auto_reauth,
        reauth_timeout_sec=reauth_timeout_sec,
        sleeper=sleeper, clock=clock,
    )
    if not ensured.ok:
        # 세션이 없거나 재인증 타임아웃 — job 은 PAUSED_FOR_REAUTH 로 보존
        job_state.pause_for_reauth(
            job_id,
            current_step=current_step,
            cursor=(params or {}).get("cursor", ""),
            paused_reason=ensured.status_message,
        )
        return ensured.status_message

    # 세션 OK — 실제 작업 수행
    try:
        summary = work(page)
    except _ReauthRequired as e:
        # 작업 중 세션 만료가 발견된 경우 (어댑터가 명시적으로 발생)
        job_state.pause_for_reauth(
            job_id,
            current_step=e.current_step or current_step,
            cursor=e.cursor or (params or {}).get("cursor", ""),
            paused_reason=e.reason or "session_expired_mid_job",
        )
        session_manager.mark_reauth_required(
            site_id,
            reason=e.reason or "session_expired_mid_job",
            paused_job_id=job_id,
        )
        return MSG_SESSION_EXPIRED
    except Exception as ex:  # noqa: BLE001
        logger.error("[RUN-FAIL] job=%s site=%s err=%s",
                     job_id, site_id, type(ex).__name__)
        job_state.mark_failed(job_id, reason=f"work_exception:{type(ex).__name__}")
        return "JOB_FAILED"

    job_state.mark_done(job_id, result_summary=summary)
    return "JOB_DONE"


class _ReauthRequired(Exception):
    """작업 중 세션 만료가 감지되면 어댑터가 발생시키는 신호 예외.

    민감 원문을 담지 말 것. reason 은 짧은 코드.
    """

    def __init__(self, *, reason: str = "session_expired_mid_job",
                 current_step: str = "", cursor: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.current_step = current_step
        self.cursor = cursor


# 외부 공개 alias — 어댑터 구현체가 raise 할 때 사용.
SessionExpiredMidJob = _ReauthRequired


def resume_job(
    adapter: SiteAdapter,
    page: Any,
    *,
    job_id: str,
    work: Callable[[Any], str],
    reauth_timeout_sec: Optional[int] = None,
    sleeper: Any = None,
    clock: Any = None,
) -> str:
    """PAUSED_FOR_REAUTH 상태인 job 을 다시 이어서 실행.

    1) 현재 세션이 ACTIVE 인지 재확인 (ensure_session)
    2) OK 면 RESUMABLE 로 전이 → RUNNING 으로 복귀시켜 work 실행
    3) 실패면 상태 유지 (여전히 PAUSED_FOR_REAUTH)
    """
    rec = job_state.get(job_id)
    if rec is None:
        return "JOB_NOT_FOUND"
    if rec.status not in ("PAUSED_FOR_REAUTH", "RESUMABLE"):
        return f"JOB_NOT_RESUMABLE:{rec.status}"

    ensured = ensure_session(
        adapter, page,
        job_id=job_id,
        auto_reauth=True,
        reauth_timeout_sec=reauth_timeout_sec,
        sleeper=sleeper, clock=clock,
    )
    if not ensured.ok:
        return ensured.status_message

    # PAUSED_FOR_REAUTH → RESUMABLE → RUNNING
    if rec.status == "PAUSED_FOR_REAUTH":
        job_state.mark_resumable(job_id)
    job_state.resume(job_id)
    logger.info("[JOB-RESUMED] %s job=%s site=%s", MSG_JOB_RESUMED, job_id, rec.site_id)

    try:
        summary = work(page)
    except _ReauthRequired as e:
        job_state.pause_for_reauth(
            job_id,
            current_step=e.current_step or rec.current_step,
            cursor=e.cursor or rec.cursor,
            paused_reason=e.reason or "session_expired_mid_job",
        )
        return MSG_SESSION_EXPIRED
    except Exception as ex:  # noqa: BLE001
        logger.error("[RESUME-FAIL] job=%s err=%s", job_id, type(ex).__name__)
        job_state.mark_failed(job_id, reason=f"work_exception:{type(ex).__name__}")
        return "JOB_FAILED"

    job_state.mark_done(job_id, result_summary=summary)
    return "JOB_DONE"


__all__ = [
    "EnsureSessionResult",
    "ensure_session",
    "run_with_session",
    "resume_job",
    "SessionExpiredMidJob",
    "MSG_SESSION_ACTIVE",
    "MSG_SESSION_EXPIRED",
    "MSG_REAUTH_IN_PROGRESS",
    "MSG_REAUTH_SUCCESS",
    "MSG_JOB_RESUMED",
    "MSG_REAUTH_TIMED_OUT",
]
