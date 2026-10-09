"""Local WebSocket bridge for approved browser tasks (BROWSER-6).

Bridges inbound mock WebSocket messages to BrowserTaskHandler and
emits safe outbound result callbacks via BrowserWebSocketTaskResultSchema.

Flow:
    inbound dict
    → BrowserWebSocketTaskPayloadSchema.from_dict()  (raises on invalid)
    → BrowserTaskPayload (via to_browser_task_payload)
    → BrowserTaskHandler.handle_task()  (async)
    → BrowserTaskResult (safe fields only)
    → BrowserWebSocketTaskResultSchema.from_task_result()
    → result_schema.safe_dict()
    → MockResultCallbackCollector.append()

Security invariants:
- approval_token / final_approval_token / token_hash NEVER reach callback
- typed_text / password / OTP / cookie / session NEVER reach callback
- Bridge does NOT open ws:// or wss:// connections — mock only
- Bridge does NOT call BrowserController directly — handler dispatch only
- Schema validation MUST run BEFORE handler dispatch
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from core.agent_runtime.browser.approval.browser_audit_contract import (
    BrowserAuditEvent,
    BrowserAuditEventType,
    build_browser_result_audit_event,
    build_browser_task_audit_event,
)
from core.agent_runtime.browser.bridge.browser_websocket_schema import (
    RESULT_DATA_FORBIDDEN_KEYS,
    VALID_TASK_STATUS,
    BrowserWebSocketTaskPayloadSchema,
    BrowserWebSocketTaskResultSchema,
)
from core.agent_runtime.browser.browser_task_handler import BrowserTaskHandler, BrowserTaskPayload, BrowserTaskResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock callback collector
# ---------------------------------------------------------------------------


class MockResultCallbackCollector:
    """Collects safe result dicts emitted by the bridge.

    Used in tests and local mock flows. Provides assertions to verify
    secret non-disclosure and message routing.
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def append(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def last_message(self) -> dict[str, Any] | None:
        return self.messages[-1] if self.messages else None

    def clear(self) -> None:
        self.messages.clear()

    def assert_no_secrets(self) -> None:
        """Raise AssertionError if any forbidden key appears in any message."""
        for msg in self.messages:
            self._assert_no_secrets_in_value(msg)

    @classmethod
    def _assert_no_secrets_in_value(cls, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if k.lower() in {fk.lower() for fk in RESULT_DATA_FORBIDDEN_KEYS}:
                    raise AssertionError(f"Forbidden key in callback: {k}")
                cls._assert_no_secrets_in_value(v)
        elif isinstance(value, list):
            for item in value:
                cls._assert_no_secrets_in_value(item)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload_to_task(schema: BrowserWebSocketTaskPayloadSchema) -> BrowserTaskPayload:
    """Convert validated WebSocket payload schema to BrowserTaskPayload."""
    return BrowserTaskPayload(
        task_id=schema.task_id,
        task_type=schema.task_type,
        action_type=schema.action_type,
        selector=schema.selector,
        value=schema.value,
        approval_id=schema.approval_id,
        approval_token=schema.approval_token,
        final_approval_token=schema.final_approval_token,
    )


def _task_result_to_schema(result: BrowserTaskResult) -> BrowserWebSocketTaskResultSchema:
    """Convert BrowserTaskResult → BrowserWebSocketTaskResultSchema (safe fields only)."""
    status = result.status if result.status in VALID_TASK_STATUS else "received"
    return BrowserWebSocketTaskResultSchema.from_task_result(
        task_id=result.task_id,
        status=status,
        action=result.action,
        selector=result.selector,
        executed=result.executed,
        element_found=result.element_found,
        risk_level=result.risk_level,
        final_approval_required=result.final_approval_required,
        result=result.result,
        error_code=result.error_code,
        error_message=result.error_message,
        target_url_domain=result.target_url_domain,
        text_length=result.text_length,
        text_preview="[REDACTED]",
    )


def _safe_failure_dict(
    task_id: str,
    action: str,
    selector: str,
    status: str,
    error_code: str,
    error_message: str,
) -> dict[str, Any]:
    """Build a safe failure callback dict via the result schema (no secrets)."""
    schema = BrowserWebSocketTaskResultSchema.from_task_result(
        task_id=task_id or "unknown",
        status=status if status in VALID_TASK_STATUS else "validation_failed",
        action=action,
        selector=selector,
        executed=False,
        element_found=False,
        result=error_code,
        error_code=error_code,
        error_message=error_message,
        text_preview="[REDACTED]",
    )
    return schema.safe_dict()


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class BrowserLocalWebSocketBridge:
    """Local mock WebSocket → BrowserTaskHandler bridge.

    Does NOT open real WebSocket connections. Accepts inbound dict messages
    via handle_inbound_message() and forwards safe results via callback.

    Flow guarantees:
    - Schema validation runs BEFORE handler dispatch (validation_failed otherwise)
    - All callbacks pass through BrowserWebSocketTaskResultSchema.safe_dict()
    - Tokens never appear in callbacks or logs
    """

    def __init__(
        self,
        task_handler: BrowserTaskHandler,
        callback: Callable[[dict[str, Any]], None] | None = None,
        audit_writer: Any | None = None,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        self._handler = task_handler
        self._callback = callback or (lambda _msg: None)
        self._audit_writer = audit_writer
        self._audit_context = dict(audit_context or {})

    # ------------------------------------------------------------------
    # Audit emission

    def _audit_actor(self) -> dict[str, Any]:
        ctx = self._audit_context
        return {
            "actor_user_id": ctx.get("actor_user_id"),
            "actor_role": ctx.get("actor_role") or "system",
            "organization_id": ctx.get("organization_id"),
        }

    def _emit_audit_event(self, event: BrowserAuditEvent) -> None:
        """Write audit event safely. Failures never break the bridge callback."""
        if self._audit_writer is None:
            return
        try:
            self._audit_writer.write(event)
        except Exception as exc:  # noqa: BLE001 - 브라우저 로컬 웹소켓 브리지 -- 감사 로그 기록 실패는 원본 스택 노출 없이 예외 타입명만 로깅(주석에 명시된 의도적 설계), 핸들러 예외는 안전한 실패 결과로 변환, 콜백 예외는 드롭
            # Safe summary only — never surface raw stack to caller or log.
            logger.error("audit writer failed: %s", type(exc).__name__)

    def _build_audit_event_from_validation_failure(
        self,
        *,
        task_id: str,
        action_type: str,
        selector: str,
        error_message: str,
    ) -> BrowserAuditEvent:
        actor = self._audit_actor()
        safe_task_id = task_id or "unknown"
        return build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_VALIDATION_FAILED,
            task_id=safe_task_id,
            action_type=action_type or "",
            selector=selector or "",
            error_code="schema_invalid",
            error_message=error_message,
            request_id=safe_task_id,
            **actor,
        )

    def _build_audit_event_from_handler_exception(
        self,
        *,
        task_id: str,
        action_type: str,
        selector: str,
        exc: BaseException,
    ) -> BrowserAuditEvent:
        actor = self._audit_actor()
        return build_browser_task_audit_event(
            event_type=BrowserAuditEventType.TASK_FAILED,
            task_id=task_id or "unknown",
            action_type=action_type or "",
            selector=selector or "",
            error_code="handler_exception",
            error_message=type(exc).__name__,  # class name only — no stack
            request_id=task_id or None,
            **actor,
        )

    def _build_audit_event_from_result(
        self,
        task_result: BrowserTaskResult,
        *,
        bridge_status: str = "callback_built",
    ) -> BrowserAuditEvent:
        actor = self._audit_actor()
        return build_browser_result_audit_event(
            task_result=task_result,
            bridge_status=bridge_status,
            request_id=getattr(task_result, "task_id", None),
            **actor,
        )

    # ------------------------------------------------------------------
    # Inbound message entrypoint

    async def handle_inbound_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Process one inbound mock message. Returns the safe callback dict."""
        # Step 1: schema validation — handler is NOT invoked on failure
        try:
            schema = BrowserWebSocketTaskPayloadSchema.from_dict(message or {})
        except (ValueError, TypeError) as exc:
            logger.info("inbound payload validation failed: %s", exc)
            task_id_str = str((message or {}).get("task_id") or "unknown")
            action_str = str((message or {}).get("action_type") or "")
            selector_str = str((message or {}).get("selector") or "")
            failure = _safe_failure_dict(
                task_id=task_id_str,
                action=action_str,
                selector=selector_str,
                status="validation_failed",
                error_code="schema_invalid",
                error_message=str(exc),
            )
            self._emit_audit_event(
                self._build_audit_event_from_validation_failure(
                    task_id=task_id_str,
                    action_type=action_str,
                    selector=selector_str,
                    error_message=str(exc),
                )
            )
            self._emit(failure)
            return failure

        is_valid, err = schema.validate()
        if not is_valid:
            failure = _safe_failure_dict(
                task_id=schema.task_id or "unknown",
                action=schema.action_type,
                selector=schema.selector,
                status="validation_failed",
                error_code="schema_invalid",
                error_message=err or "validation failed",
            )
            self._emit_audit_event(
                self._build_audit_event_from_validation_failure(
                    task_id=schema.task_id or "unknown",
                    action_type=schema.action_type,
                    selector=schema.selector,
                    error_message=err or "validation failed",
                )
            )
            self._emit(failure)
            return failure

        # Step 2: convert to handler payload
        payload = _payload_to_task(schema)

        # Step 3: dispatch to handler — never call adapter/controller directly
        try:
            task_result = await self._handler.handle_task(payload)
        except Exception as exc:
            logger.exception("task handler raised — returning safe failed result")
            failure = _safe_failure_dict(
                task_id=schema.task_id,
                action=schema.action_type,
                selector=schema.selector,
                status="failed",
                error_code="handler_exception",
                error_message=type(exc).__name__,  # class name only — no stack
            )
            self._emit_audit_event(
                self._build_audit_event_from_handler_exception(
                    task_id=schema.task_id,
                    action_type=schema.action_type,
                    selector=schema.selector,
                    exc=exc,
                )
            )
            self._emit(failure)
            return failure

        # Step 4: result → result schema → safe_dict
        result_schema = _task_result_to_schema(task_result)
        is_safe, err = result_schema.validate_safe_result()
        if not is_safe:
            # Defensive: drop the unsafe result, emit a sanitized failure
            logger.error("unsafe result detected — sanitizing: %s", err)
            failure = _safe_failure_dict(
                task_id=task_result.task_id,
                action=task_result.action,
                selector=task_result.selector,
                status="failed",
                error_code="unsafe_result",
                error_message="result schema validation failed",
            )
            actor = self._audit_actor()
            self._emit_audit_event(
                build_browser_task_audit_event(
                    event_type=BrowserAuditEventType.TASK_FAILED,
                    task_id=task_result.task_id or "unknown",
                    action_type=task_result.action or "",
                    selector=task_result.selector or "",
                    error_code="unsafe_result",
                    error_message="result schema validation failed",
                    request_id=task_result.task_id or None,
                    **actor,
                )
            )
            self._emit(failure)
            return failure

        safe = result_schema.safe_dict()
        self._emit_audit_event(self._build_audit_event_from_result(task_result))
        self._emit(safe)
        return safe

    # ------------------------------------------------------------------
    # Synchronous helper (for tests)

    def handle_inbound_message_sync(self, message: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self.handle_inbound_message(message))

    # ------------------------------------------------------------------
    # Internal

    def _emit(self, message: dict[str, Any]) -> None:
        """Emit safe message via callback. Strips any forbidden keys defensively."""
        # Defense in depth — never trust upstream to be clean
        forbidden = {fk.lower() for fk in RESULT_DATA_FORBIDDEN_KEYS}
        clean = {k: v for k, v in message.items() if k.lower() not in forbidden}
        try:
            self._callback(clean)
        except Exception as exc:  # noqa: BLE001 - 브라우저 로컬 웹소켓 브리지 -- 감사 로그 기록 실패는 원본 스택 노출 없이 예외 타입명만 로깅(주석에 명시된 의도적 설계), 핸들러 예외는 안전한 실패 결과로 변환, 콜백 예외는 드롭
            logger.error("callback raised — dropping: %s", exc)


__all__ = [
    "BrowserLocalWebSocketBridge",
    "MockResultCallbackCollector",
]
