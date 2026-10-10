"""YouTube risk gate helpers using site_engine execution_gate."""
from __future__ import annotations

from scripts.site_engine.execution_gate import (
    ExecutionGateInput,
    ExecutionGateResult,
    evaluate_execution_gate,
)
from scripts.site_engine.site_types import SiteCapability


def gate_youtube_read() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="youtube",
            capability=SiteCapability.READ,
            action="read_page",
        )
    )


def gate_youtube_upload_plan() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="youtube",
            capability=SiteCapability.UPLOAD,
            action="upload_video",
        )
    )


def gate_youtube_publish_plan() -> ExecutionGateResult:
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="youtube",
            capability=SiteCapability.PUBLISH,
            action="publish_video",
        )
    )


def gate_youtube_oauth_required() -> ExecutionGateResult:
    """OAuth/credential 처리는 사용자 직접 수행 필요."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="youtube",
            capability=SiteCapability.SIGN,
            action="oauth_credential",
        )
    )
