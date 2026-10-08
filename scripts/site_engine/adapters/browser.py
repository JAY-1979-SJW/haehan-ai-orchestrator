"""site_engine browser adapter — 브라우저 액션 plan 생성 foundation.

실제 CDP/Playwright 실행은 없다. plan 객체만 생성한다.
실제 실행은 반드시 execution_gate decision을 거친 후 진행해야 한다.

기존 scripts/browser/cdp/cdp_client.py를 대체하지 않는다.
이 모듈은 site_engine 구조에서의 추상화 계층이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scripts.site_engine.site_types import GateDecision, SiteCapability


class BrowserActionKind(str, Enum):
    NAVIGATE = "NAVIGATE"
    CLICK = "CLICK"
    INPUT = "INPUT"
    DOWNLOAD = "DOWNLOAD"
    UPLOAD = "UPLOAD"
    SUBMIT = "SUBMIT"
    SCROLL = "SCROLL"
    SCREENSHOT = "SCREENSHOT"
    WAIT = "WAIT"


_APPROVAL_REQUIRED_KINDS = frozenset(
    {
        BrowserActionKind.SUBMIT,
        BrowserActionKind.UPLOAD,
    }
)

_SENSITIVE_INPUT_KEYWORDS = frozenset(
    {
        "password",
        "passwd",
        "otp",
        "pin",
        "secret",
        "token",
        "certificate",
        "cert",
        "private_key",
        "credential",
        "session",
        "cookie",
        "auth",
        "비밀번호",
        "인증서",
        "쿠키",
        "세션",
        "인증",
    }
)


@dataclass
class BrowserActionPlan:
    kind: BrowserActionKind
    target: str  # CSS selector, URL, 또는 설명
    capability: SiteCapability
    required_gate: GateDecision
    is_sensitive: bool = False
    sensitive_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # 실제 값 저장 금지 — value 필드 없음


@dataclass
class BrowserActionResult:
    plan: BrowserActionPlan
    executed: bool = False
    success: bool | None = None
    detail: str = ""


def _is_sensitive_input(field_name: str) -> bool:
    lower = field_name.lower()
    return any(k in lower for k in _SENSITIVE_INPUT_KEYWORDS)


def build_readonly_navigation_plan(url: str) -> BrowserActionPlan:
    return BrowserActionPlan(
        kind=BrowserActionKind.NAVIGATE,
        target=url,
        capability=SiteCapability.READ,
        required_gate=GateDecision.READ_ONLY_ALLOWED,
    )


def build_click_plan(selector: str, *, label: str = "") -> BrowserActionPlan:
    meta = {"label": label} if label else {}
    return BrowserActionPlan(
        kind=BrowserActionKind.CLICK,
        target=selector,
        capability=SiteCapability.FORM_FILL,
        required_gate=GateDecision.SERVER_BROWSER_ALLOWED,
        metadata=meta,
    )


def build_input_plan(selector: str, *, field_name: str = "") -> BrowserActionPlan:
    sensitive = _is_sensitive_input(field_name)
    return BrowserActionPlan(
        kind=BrowserActionKind.INPUT,
        target=selector,
        capability=SiteCapability.FORM_FILL,
        required_gate=(GateDecision.USER_DIRECT_REQUIRED if sensitive else GateDecision.SERVER_BROWSER_ALLOWED),
        is_sensitive=sensitive,
        sensitive_reason=f"field_name={field_name!r} matches sensitive keyword" if sensitive else "",
        metadata={"field_name": field_name} if field_name else {},
    )


def build_download_plan(url: str, *, filename: str = "") -> BrowserActionPlan:
    meta = {"filename": filename} if filename else {}
    return BrowserActionPlan(
        kind=BrowserActionKind.DOWNLOAD,
        target=url,
        capability=SiteCapability.DOWNLOAD,
        required_gate=GateDecision.SERVER_BROWSER_ALLOWED,
        metadata=meta,
    )


def build_upload_plan(selector: str, *, filename: str = "") -> BrowserActionPlan:
    meta = {"filename": filename} if filename else {}
    return BrowserActionPlan(
        kind=BrowserActionKind.UPLOAD,
        target=selector,
        capability=SiteCapability.UPLOAD,
        required_gate=GateDecision.APPROVAL_REQUIRED,
        metadata=meta,
    )


def build_submit_plan(selector: str, *, action_label: str = "") -> BrowserActionPlan:
    meta = {"action_label": action_label} if action_label else {}
    return BrowserActionPlan(
        kind=BrowserActionKind.SUBMIT,
        target=selector,
        capability=SiteCapability.SUBMIT,
        required_gate=GateDecision.APPROVAL_REQUIRED,
        metadata=meta,
    )
