"""
인증 후 자동 재개 모듈

인증 완료 후 중단된 read-only 작업을 자동으로 재개한다.
USER_DIRECT_ONLY 작업은 자동 재개하지 않는다.

허용 자동 재개 action:
- read_page, search, download_file, capture_screenshot
- extract_text, extract_table, detect_login_status

자동 재개 금지 action:
- submit, sign, payment, bid_submit, final_submit
- transfer, contract_submit
"""
from __future__ import annotations

from typing import Any

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_BLOCKED,
    STATUS_USER_ACTION_REQUIRED,
    build_result,
)
from core.agent_runtime.runtime.local_session_boundary import enforce_session_boundary
from core.agent_runtime.runtime.result_sanitizer import sanitize_result
from core.agent_runtime.runtime.security_guard import validate_task_before_run

# ── 자동 재개 허용 action ─────────────────────────────────────────────────────

_AUTO_RESUME_ALLOWED: frozenset[str] = frozenset({
    "read_page",
    "search",
    "download_file",
    "capture_screenshot",
    "extract_text",
    "extract_table",
    "detect_login_status",
})

# ── 자동 재개 금지 action (사용자 직접 수행 필요) ─────────────────────────────

_AUTO_RESUME_FORBIDDEN: frozenset[str] = frozenset({
    "submit",
    "sign",
    "payment",
    "bid_submit",
    "final_submit",
    "transfer",
    "contract_submit",
    "auto_sign",
    "auto_payment",
    "auto_bid_submit",
    "auto_final_submit",
})


def can_auto_resume(action: str) -> bool:
    """action이 자동 재개 허용 목록에 있는지 확인한다."""
    return action.lower() in _AUTO_RESUME_ALLOWED


def resume_after_auth(
    task: dict[str, Any],
    runner_fn: Any,
) -> dict[str, Any]:
    """
    인증 완료 후 task를 재개한다.

    runner_fn: playwright_runner.run_task 또는 동일 시그니처 callable
    반환: sanitize된 safe result
    """
    task_id = task.get("task_id", "")
    action = (task.get("action") or "").lower()

    # 자동 재개 금지 action 체크
    if action in _AUTO_RESUME_FORBIDDEN:
        return build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_USER_ACTION_REQUIRED,
            message_ko=(
                f"action={action!r}은 자동 재개 금지 작업입니다. "
                "사용자가 직접 수행해 주세요."
            ),
        )

    # 허용 목록에 없는 경우도 차단
    if not can_auto_resume(action):
        return build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_BLOCKED,
            message_ko=f"action={action!r}은 자동 재개 허용 목록에 없습니다.",
        )

    # 재개 전 security_guard 재검증
    guard = validate_task_before_run(task)
    if not guard["allowed"]:
        return build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_BLOCKED,
            message_ko=f"재개 전 보안 검증 실패: {guard['reason']}",
        )

    # 실행 및 sanitize + 세션 경계 강제
    raw_result = runner_fn(task)
    sanitized = sanitize_result(raw_result)
    return enforce_session_boundary(sanitized)


def classify_resume_eligibility(action: str) -> dict[str, Any]:
    """
    action의 자동 재개 가능 여부를 분류한다.

    반환:
      eligible: bool
      reason: str
    """
    lower = action.lower()
    if lower in _AUTO_RESUME_FORBIDDEN:
        return {
            "eligible": False,
            "reason": f"자동 재개 금지 action: {action!r}. 사용자 직접 수행 필요.",
        }
    if lower in _AUTO_RESUME_ALLOWED:
        return {"eligible": True, "reason": "자동 재개 허용 action."}
    return {
        "eligible": False,
        "reason": f"자동 재개 허용 목록에 없는 action: {action!r}.",
    }
