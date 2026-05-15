"""Hiworks risk gate helpers."""
from __future__ import annotations

from scripts.gate import check as gate_check
from scripts.site_engine.execution_gate import (
    ExecutionDecision,
    ExecutionGateInput,
    ExecutionGateResult,
    GateReason,
    evaluate_execution_gate,
)
from scripts.site_engine.types import GateDecision, SiteCapability


def check_read() -> None:
    gate_check("scan_page")


def check_prepare() -> None:
    gate_check("type_into")


def check_send(*, force: bool = False, **metadata) -> None:
    gate_check("mail_send", force=force, context="Hiworks state-changing action", **metadata)


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
