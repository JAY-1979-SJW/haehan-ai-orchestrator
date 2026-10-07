"""Hiworks risk gate helpers."""

from __future__ import annotations

from scripts.common.gate import check as gate_check
from scripts.common.gate import require_side_effect
from scripts.site_engine.execution_gate import (
    ExecutionGateInput,
    ExecutionGateResult,
    evaluate_execution_gate,
)
from scripts.site_engine.site_types import SiteCapability


def check_read() -> None:
    gate_check("scan_page")


def check_prepare() -> None:
    gate_check("type_into")


def check_send(*, force: bool = False, **metadata) -> None:
    gate_check("mail_send", force=force, context="Hiworks state-changing action", **metadata)


def require_send(*, approval: str | None, expected: str, recipient: str | list[str] | None = None, **metadata):
    """하이웍스 발송·제출 직전 검사 — force 불리언이 아니라 사용자가 입력한 --confirm 문구와 대조한다."""
    return require_side_effect(
        "mail_send", approval=approval, expected=expected, recipient=recipient, context="Hiworks state-changing action", **metadata
    )


# ── site_engine ExecutionGateResult wrappers (non-breaking additions) ─


def gate_result_read() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="hiworks",
            capability=SiteCapability.READ,
            action="scan_page",
        )
    )


def gate_result_prepare() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="hiworks",
            capability=SiteCapability.FORM_FILL,
            action="type_into",
        )
    )


def gate_result_send() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="hiworks",
            capability=SiteCapability.SEND,
            action="mail_send",
        )
    )
