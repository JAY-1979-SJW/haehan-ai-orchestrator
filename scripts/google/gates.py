"""Google risk gate helpers using site_engine execution_gate."""
from __future__ import annotations

from scripts.site_engine.execution_gate import (
    ExecutionGateInput,
    ExecutionGateResult,
    evaluate_execution_gate,
)
from scripts.site_engine.site_types import SiteCapability


def gate_google_read() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="google",
            capability=SiteCapability.READ,
            action="read_page",
        )
    )


def gate_google_search() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="google",
            capability=SiteCapability.SEARCH,
            action="search",
        )
    )


def gate_google_send_plan() -> ExecutionGateResult:
    """Gmail send / 메일 발송 계획 — approval required."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="google",
            capability=SiteCapability.SEND,
            action="gmail_send",
        )
    )


def gate_google_submit_plan() -> ExecutionGateResult:
    """Google work execute (form submit) — approval required."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="google",
            capability=SiteCapability.SUBMIT,
            action="work_execute",
        )
    )


def gate_google_upload_plan() -> ExecutionGateResult:
    """Drive upload — approval required."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="google",
            capability=SiteCapability.UPLOAD,
            action="drive_upload",
        )
    )


def gate_google_publish_plan() -> ExecutionGateResult:
    """Google Workspace publish / 게시 — approval required."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="google",
            capability=SiteCapability.PUBLISH,
            action="publish",
        )
    )


def gate_google_oauth_required() -> ExecutionGateResult:
    """OAuth/로그인/credential 처리 — 사용자 직접 수행 필요."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="google",
            capability=SiteCapability.SIGN,
            action="oauth_credential",
        )
    )
