"""개발자 등록 신청 자동화 실행기.

흐름:
  1. adapter.fill_form(page, params)        — 신청 폼 자동 입력 (제출 버튼 제외)
  2. adapter.capture_screenshot(page, path)  — 현재 화면 캡처
  3. issue_token_for_dev_reg(...)            — 승인 토큰 발행
  4. dev_reg_approval.create_pending(...)    — 승인 대기 레코드 생성
  5. dev_reg_approval.register_approval_waiter(task_id)  — 이벤트 등록
  6. log_event("DEV_REG_TASK_CREATED", ...)  — 감사 로그
  7. telegram_sender.send_photo(...)         — 텔레그램 발송 (스크린샷 + 승인/거절 버튼)
  8. log_event("DEV_REG_TELEGRAM_SENT", ...)
  9. approval_event.wait(timeout=...)        — 웹훅 이벤트 대기 (비폴링)
     → telegram_webhook 에서 승인/거절 시 signal_approval_event() 호출로 즉시 재개
 10a. approved → adapter.submit_form(page)   — 폼 제출
 10b. rejected/expired → adapter.abort_form(page) — 세션 중단
 11. 감사 로그 기록 + DevRegApproval 상태 업데이트

금지 사항 — 이 모듈이 절대 하지 않는 것:
  - 승인 없이 submit_form 호출
  - 만료 토큰으로 submit_form 호출
  - CAPTCHA / 2FA / OTP 자동 우회
  - 로그에 패스워드·쿠키·세션 토큰 기록
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_orchestrator.audit.audit_logger import log_event
from ai_orchestrator.core import telegram_sender as _ts
from ai_orchestrator.dev_reg import dev_reg_approval as _dra
from ai_orchestrator.dev_reg.dev_reg_telegram import build_dev_reg_message
from ai_orchestrator.paths.runtime import storage_dir
from ai_orchestrator.sites.adapters.dev_reg_base import DevRegAdapterBase
from tools.gates.approval import get_token, issue_token_for_dev_reg

logger = logging.getLogger(__name__)

_SCREENSHOT_DIR = storage_dir() / "screenshots" / "dev_reg"
_DEFAULT_TTL_MINUTES = 30


@dataclass
class DevRegResult:
    task_id: str
    status: str  # "executed" / "rejected" / "expired" / "failed"
    result: str = ""
    error: str = ""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _resolve_final_status(token_id: str, expires_dt: datetime, clock: Callable[[], datetime]) -> str:
    """토큰 상태로 최종 판정(approved/rejected/expired 등)."""
    final_token = get_token(token_id)
    final_status = final_token.status if final_token else "expired"

    # timeout 으로 반환된 경우 token 이 아직 "issued" 면 expired 처리
    now = clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if final_status == "issued" or (final_token and now >= expires_dt):
        final_status = "expired"
    return final_status


def _submit_approved(
    adapter: DevRegAdapterBase,
    page,
    task_id: str,
    token_id: str,
    requested_by: str,
    target_url: str,
) -> DevRegResult:
    """승인된 건의 폼 제출 + 감사 로그."""
    try:
        submit_result = adapter.submit_form(page)
        result_str = submit_result.result_summary if submit_result.success else f"submit_failed:{submit_result.error}"
    except Exception as e:  # noqa: BLE001 - 개발자 등록 신청 승인 게이트 실행기 — submit_form은 텔레그램 승인(approved) 확인 후에만 호출되며, except는 폼입력/스크린샷/제출/중단 각 단계 실패를 로그와 명확한 실패 상태로 반환할 뿐 승인 절차를 우회하지 않음.
        result_str = f"submit_exception:{e}"
        logger.error("submit_form 예외 | task=%s | %s", task_id, e)

    _dra.mark_executed(task_id, result_str)
    log_event(
        "DEV_REG_EXECUTED",
        task_id,
        risk_level=adapter.risk_level,
        action_type=adapter.action_type,
        target=target_url,
        decision=result_str,
        actor=requested_by,
        token_id=token_id,
        note=f"provider={adapter.provider}",
    )
    return DevRegResult(task_id=task_id, status="executed", result=result_str)


def _abort_not_approved(
    adapter: DevRegAdapterBase,
    page,
    task_id: str,
    token_id: str,
    requested_by: str,
    final_status: str,
) -> DevRegResult:
    """거절/만료 건의 세션 중단 + 감사 로그."""
    try:
        adapter.abort_form(page)
    except Exception as e:  # noqa: BLE001 - 개발자 등록 신청 승인 게이트 실행기 — submit_form은 텔레그램 승인(approved) 확인 후에만 호출되며, except는 폼입력/스크린샷/제출/중단 각 단계 실패를 로그와 명확한 실패 상태로 반환할 뿐 승인 절차를 우회하지 않음.
        logger.warning("abort_form 실패 (무시) | task=%s | %s", task_id, e)

    if final_status == "rejected":
        _dra.mark_rejected_internal(task_id)
        log_event(
            "DEV_REG_REJECTED",
            task_id,
            risk_level=adapter.risk_level,
            action_type=adapter.action_type,
            actor=requested_by,
            token_id=token_id,
            note=f"provider={adapter.provider}",
        )
        return DevRegResult(task_id=task_id, status="rejected")
    _dra.mark_expired_internal(task_id)
    log_event(
        "DEV_REG_EXPIRED",
        task_id,
        risk_level=adapter.risk_level,
        action_type=adapter.action_type,
        actor=requested_by,
        token_id=token_id,
        note=f"provider={adapter.provider} token_status={final_status}",
    )
    return DevRegResult(task_id=task_id, status="expired")


def run_dev_reg(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    adapter: DevRegAdapterBase,
    page,
    params: dict,
    *,
    requested_by: str = "system",
    screenshot_dir: Path | None = None,
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
    clock: Callable[[], datetime] = _utc_now,
) -> DevRegResult:
    """개발자 등록 신청 승인 게이트 전체 실행.

    Args:
        adapter: 사이트별 어댑터 (HiworksDevRegAdapter / NaverDevRegAdapter 등).
        page: 열려있는 Playwright Page 객체.
        params: 신청 폼에 채울 비민감 파라미터 dict.
        requested_by: 요청자 식별자.
        screenshot_dir: 스크린샷 저장 디렉토리. None 이면 기본값 사용.
        ttl_minutes: 승인 토큰 유효 시간(분). 기본 30분.
        clock: 현재 시간 반환 함수 (테스트 주입용 — timeout 계산에 사용).
    """
    task_id = f"dr-{uuid.uuid4().hex[:12]}"
    ss_dir = screenshot_dir or _SCREENSHOT_DIR
    ss_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = ss_dir / f"{task_id}.png"

    # ── 1. 폼 자동 입력 ─────────────────────────────────────────────
    try:
        fill_result = adapter.fill_form(page, params)
    except Exception as e:  # noqa: BLE001 - 개발자 등록 신청 승인 게이트 실행기 — submit_form은 텔레그램 승인(approved) 확인 후에만 호출되며, except는 폼입력/스크린샷/제출/중단 각 단계 실패를 로그와 명확한 실패 상태로 반환할 뿐 승인 절차를 우회하지 않음.
        logger.error("폼 입력 예외 | task=%s | %s", task_id, e)
        log_event(
            "DEV_REG_FAILED",
            task_id,
            action_type=adapter.action_type,
            actor=requested_by,
            note=f"fill_form exception: {e}",
        )
        return DevRegResult(task_id=task_id, status="failed", error=str(e))

    if not fill_result.success:
        log_event(
            "DEV_REG_FAILED",
            task_id,
            action_type=adapter.action_type,
            actor=requested_by,
            note=f"fill_form failed: {fill_result.error}",
        )
        return DevRegResult(task_id=task_id, status="failed", error=fill_result.error)

    # ── 2. 스크린샷 캡처 ────────────────────────────────────────────
    try:
        adapter.capture_screenshot(page, screenshot_path)
    except Exception as e:  # noqa: BLE001 - 개발자 등록 신청 승인 게이트 실행기 — submit_form은 텔레그램 승인(approved) 확인 후에만 호출되며, except는 폼입력/스크린샷/제출/중단 각 단계 실패를 로그와 명확한 실패 상태로 반환할 뿐 승인 절차를 우회하지 않음.
        logger.warning("스크린샷 실패 (계속 진행) | %s", e)

    # ── 3. 승인 토큰 발행 ────────────────────────────────────────────
    token = issue_token_for_dev_reg(
        task_id=task_id,
        requested_by=requested_by,
        risk_level=adapter.risk_level,
        ttl_minutes=ttl_minutes,
    )
    token_id = token.token_id

    # ── 4. Pending 레코드 생성 ──────────────────────────────────────
    _dra.create_pending(
        task_id=task_id,
        token_id=token_id,
        provider=adapter.provider,
        action_type=adapter.action_type,
        risk_level=adapter.risk_level,
        summary=fill_result.summary,
        target_url=fill_result.target_url,
        screenshot_path=str(screenshot_path),
        requested_by=requested_by,
        expires_at=token.expires_at,
    )

    # ── 5. 이벤트 등록 — 텔레그램 발송 전에 등록하여 early webhook 을 놓치지 않는다
    expires_dt = datetime.fromisoformat(token.expires_at)
    approval_event = _dra.register_approval_waiter(task_id)

    # ── 6. 감사 로그 ─────────────────────────────────────────────────
    log_event(
        "DEV_REG_TASK_CREATED",
        task_id,
        risk_level=adapter.risk_level,
        action_type=adapter.action_type,
        target=fill_result.target_url,
        actor=requested_by,
        token_id=token_id,
        note=f"provider={adapter.provider}",
    )

    # ── 7. 텔레그램 발송 ─────────────────────────────────────────────
    msg = build_dev_reg_message(
        task_id=task_id,
        provider=adapter.provider,
        action_type=adapter.action_type,
        summary=fill_result.summary,
        risk_level=adapter.risk_level,
        target_url=fill_result.target_url,
        expires_at=token.expires_at,
        token_id=token_id,
    )
    send_result = _ts.send_photo(
        photo_path=screenshot_path,
        caption=msg["text"],
        reply_markup=msg["reply_markup"],
    )
    tg_msg_id = str((send_result.get("result") or {}).get("message_id", ""))
    _dra.mark_telegram_sent(task_id, message_id=tg_msg_id)

    # ── 8. 텔레그램 발송 감사 ────────────────────────────────────────
    log_event(
        "DEV_REG_TELEGRAM_SENT",
        task_id,
        risk_level=adapter.risk_level,
        action_type=adapter.action_type,
        actor="system",
        token_id=token_id,
        note=f"provider={adapter.provider} tg_ok={send_result.get('ok', False)}",
    )

    # ── 9. 승인 이벤트 대기 (비폴링) ────────────────────────────────
    # 만료 2분 전을 deadline 으로 사용. webhook 이 signal_approval_event() 를 호출하면 즉시 반환.
    now = clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    timeout_sec = max(0.0, (expires_dt - timedelta(minutes=2) - now).total_seconds())
    approval_event.wait(timeout=timeout_sec)
    _dra.unregister_approval_waiter(task_id)

    # ── 10. 최종 상태 판정 ──────────────────────────────────────────
    final_status = _resolve_final_status(token_id, expires_dt, clock)

    if final_status == "approved":
        # ── 10a. 승인 → 제출 ────────────────────────────────────────
        return _submit_approved(adapter, page, task_id, token_id, requested_by, fill_result.target_url)

    # ── 10b. 거절/만료 → 세션 중단 ─────────────────────────────
    return _abort_not_approved(adapter, page, task_id, token_id, requested_by, final_status)
