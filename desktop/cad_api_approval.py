"""Approval boundary for desktop CAD bridge API calls.

This module is the only desktop runtime adapter that knows about the
local_agent CAD approval store. Callers receive a small boolean/error-code
contract and never handle store internals directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

CAD_API_APPROVAL_TOOL_ID = "cad_bridge_api"


@dataclass(frozen=True)
class CadApiApprovalResult:
    ok: bool
    error_code: str = ""
    approval_id: str = ""


def build_cad_api_command_id(method: str, path: str) -> str:
    return f"{method.upper()}:{path.strip()}"


def get_default_cad_api_approval_store() -> Any:
    from local_agent.cad.command_approval import DEFAULT_APPROVAL_STORE

    return DEFAULT_APPROVAL_STORE


def consume_cad_api_approval_request(
    req: dict,
    *,
    method: str,
    path: str,
    store: Any | None = None,
) -> CadApiApprovalResult:
    approval_id = str(req.get("approval_id") or req.get("_approval_id") or "").strip()
    approval_token = str(req.get("approval_token") or req.get("_approval_token") or "").strip()
    if not approval_id:
        return CadApiApprovalResult(False, "CAD_API_APPROVAL_ID_MISSING")
    if not approval_token:
        return CadApiApprovalResult(False, "CAD_API_APPROVAL_TOKEN_MISSING", approval_id)

    try:
        approval_store = store or get_default_cad_api_approval_store()
        record = approval_store.get_record(approval_id)
        expected_command = build_cad_api_command_id(method, path)
        if (
            record.commandId != expected_command
            or record.toolId != CAD_API_APPROVAL_TOOL_ID
        ):
            return CadApiApprovalResult(
                False,
                "CAD_API_APPROVAL_SCOPE_MISMATCH",
                approval_id,
            )
        if not approval_store.consume(approval_id, approval_token):
            return CadApiApprovalResult(False, "CAD_API_APPROVAL_INVALID", approval_id)
        return CadApiApprovalResult(True, approval_id=approval_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cad api approval verification failed: %s", type(exc).__name__)
        return CadApiApprovalResult(False, "CAD_API_APPROVAL_INVALID", approval_id)


__all__ = [
    "CAD_API_APPROVAL_TOOL_ID",
    "CadApiApprovalResult",
    "build_cad_api_command_id",
    "consume_cad_api_approval_request",
    "get_default_cad_api_approval_store",
]
