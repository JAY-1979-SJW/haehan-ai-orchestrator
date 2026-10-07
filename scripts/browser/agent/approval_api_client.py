"""API-backed browser approval client.

This replaces the default local popup approval path. If the approval API is not
configured or does not explicitly approve, callers must fail closed.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class ApprovalApiResult:
    approved: bool
    status: str
    reason: str = ""


def approval_api_url() -> str:
    return (
        os.getenv("HAEHAN_BROWSER_APPROVAL_API_URL")
        or os.getenv("HAEHAN_APPROVAL_API_URL")
        or ""
    ).strip()


def approval_api_configured() -> bool:
    return bool(approval_api_url())


def _auth_header() -> dict[str, str]:
    token = (
        os.getenv("HAEHAN_BROWSER_APPROVAL_API_TOKEN")
        or os.getenv("HAEHAN_APPROVAL_API_TOKEN")
        or os.getenv("HAEHAN_AGENT_TOKEN")
        or ""
    ).strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def request_approval_via_api(
    *,
    action: str,
    label: str,
    category: str = "OTHER",
    detail: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ApprovalApiResult:
    url = approval_api_url()
    if not url:
        return ApprovalApiResult(False, "api_not_configured", "approval API URL is not configured")

    payload = {
        "action": action,
        "label": label,
        "category": category,
        "detail": detail or {},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **_auth_header(),
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return ApprovalApiResult(False, "api_error", type(exc).__name__)

    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return ApprovalApiResult(False, "api_invalid_json", "approval API returned non-json")

    decision = str(data.get("decision") or data.get("status") or "").lower()
    approved = data.get("approved") is True or decision in {"approved", "allow", "allowed"}
    if approved:
        return ApprovalApiResult(True, "approved")
    return ApprovalApiResult(False, decision or "not_approved", str(data.get("reason") or ""))
