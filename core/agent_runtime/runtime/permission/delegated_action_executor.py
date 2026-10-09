"""
사용자 위임 권한 기반 action 실행기

게이트 검증 → 콘텐츠 guard → 실행 → audit log → safe result 반환.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from core.agent_runtime.runtime.permission.approval_audit_log import (
    log_execution_blocked,
    log_execution_completed,
    log_execution_started,
)
from core.agent_runtime.runtime.permission.content_publish_guard import validate_publish_request
from core.agent_runtime.runtime.permission.delegated_permission_gate import (
    GATE_BLOCKED,
    GATE_NEED_PERMISSION,
    GATE_USER_DIRECT,
    evaluate_gate,
)
from core.agent_runtime.runtime.safe_write_result_sanitizer import (
    build_write_result,
    sanitize_write_result,
)

# ── 실행 결과 상수 ──────────────────────────────────────────────────────────────

EXEC_ALLOWED = "EXECUTION_ALLOWED"
EXEC_BLOCKED = "EXECUTION_BLOCKED"
EXEC_NEED_PERMISSION = "PERMISSION_REQUIRED"
EXEC_USER_DIRECT = "USER_DIRECT_REQUIRED"
EXEC_CONTENT_REJECTED = "CONTENT_REJECTED"

# write action 목록 (콘텐츠 guard 적용 대상)
_WRITE_ACTIONS = frozenset(
    {
        "blog_publish",
        "blog_schedule_publish",
        "blog_edit",
        "cafe_post_write",
        "cafe_post_edit",
        "cafe_comment_write",
        "cafe_comment_edit",
        "publish_with_attachment",
    }
)


def execute_delegated_action(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    action: str,
    domain: str,
    permission_id: str | None,
    content: str = "",
    approved_preview: str = "",
    account: str = "",
    task_scope: str = "",
    task_id: str | None = None,
    runner_fn: Callable[[dict], dict] | None = None,
) -> dict[str, Any]:
    """
    위임 권한 기반 action 실행.

    runner_fn: 실제 브라우저 실행 함수 (None이면 dry-run 반환).
    반환: {"status": EXEC_*, "ok": bool, "result": dict, "gate": dict}
    """
    _task_id = task_id or str(uuid.uuid4())
    gate = evaluate_gate(action, domain, permission_id, account, task_scope)

    if gate["gate"] == GATE_BLOCKED:
        log_execution_blocked(action, domain, gate["reason"], permission_id or "", _task_id)
        return {
            "status": EXEC_BLOCKED,
            "ok": False,
            "gate": gate,
            "result": build_write_result(
                task_id=_task_id,
                action=action,
                ok=False,
                domain=domain,
                message_ko=gate["reason"],
            ),
        }

    if gate["gate"] == GATE_USER_DIRECT:
        log_execution_blocked(action, domain, gate["reason"], permission_id or "", _task_id)
        return {
            "status": EXEC_USER_DIRECT,
            "ok": False,
            "gate": gate,
            "result": build_write_result(
                task_id=_task_id,
                action=action,
                ok=False,
                domain=domain,
                message_ko=gate["reason"],
            ),
        }

    if gate["gate"] == GATE_NEED_PERMISSION:
        log_execution_blocked(action, domain, gate["reason"], permission_id or "", _task_id)
        return {
            "status": EXEC_NEED_PERMISSION,
            "ok": False,
            "gate": gate,
            "result": build_write_result(
                task_id=_task_id,
                action=action,
                ok=False,
                domain=domain,
                message_ko=gate["reason"],
            ),
        }

    # GATE_PASS
    # 쓰기 action 콘텐츠 guard
    if action in _WRITE_ACTIONS and content:
        pub_check = validate_publish_request(
            action=action,
            domain=domain,
            content=content,
            approved_preview=approved_preview,
        )
        if not pub_check["allowed"]:
            log_execution_blocked(action, domain, pub_check["reason"], permission_id or "", _task_id)
            return {
                "status": EXEC_CONTENT_REJECTED,
                "ok": False,
                "gate": gate,
                "result": build_write_result(
                    task_id=_task_id,
                    action=action,
                    ok=False,
                    domain=domain,
                    message_ko=pub_check["reason"],
                ),
            }

    log_execution_started(permission_id or "", action, domain, _task_id, approved_preview)

    if runner_fn is not None:
        raw = runner_fn(
            {
                "task_id": _task_id,
                "action": action,
                "domain": domain,
                "content": content,
                "permission_id": permission_id,
            }
        )
        safe_result = sanitize_write_result(raw)
        ok = raw.get("ok", True)
    else:
        safe_result = build_write_result(
            task_id=_task_id,
            action=action,
            ok=True,
            domain=domain,
            permission_id=permission_id or "",
            message_ko=f"{action} 실행 완료 (dry-run)",
        )
        ok = True

    log_execution_completed(permission_id or "", action, domain, _task_id, ok)

    return {
        "status": EXEC_ALLOWED,
        "ok": ok,
        "gate": gate,
        "result": safe_result,
    }
