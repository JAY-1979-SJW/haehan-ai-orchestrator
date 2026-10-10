"""브라우저 액션 실행 파이프라인 (자동 재개 후 실제 조작 연결).

구성:
  - ActionRequest / ActionResult 표준 스키마
  - target 해석(browser_session_store + CDP target_id 기반)
  - runner injection 가능 (테스트 시 fake runner 주입)
  - default runner 는 scripts.browser.navigator.navigator 의 기본 함수에 위임 (Playwright 의존)

본 모듈은 Playwright import 를 함수 내부로 지연시켜, 단위 테스트에서
실제 브라우저 없이도 동작 검증할 수 있게 한다.

지원 액션:
  navigate / click / type / submit / get_current_url / get_title / wait_for_selector
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ── 액션 상수 ────────────────────────────────────────────────────────

ACT_NAVIGATE = "navigate"
ACT_CLICK = "click"
ACT_TYPE = "type"
ACT_SUBMIT = "submit"
ACT_GET_URL = "get_current_url"
ACT_GET_TITLE = "get_title"
ACT_WAIT_FOR_SELECTOR = "wait_for_selector"

SUPPORTED_ACTIONS = frozenset(
    {
        ACT_NAVIGATE,
        ACT_CLICK,
        ACT_TYPE,
        ACT_SUBMIT,
        ACT_GET_URL,
        ACT_GET_TITLE,
        ACT_WAIT_FOR_SELECTOR,
    }
)

# ── 에러 코드 ────────────────────────────────────────────────────────

ERR_TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
ERR_TARGET_CLOSED = "TARGET_CLOSED"
ERR_UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
ERR_INVALID_PARAMS = "INVALID_PARAMS"
ERR_RUNNER_FAILED = "RUNNER_FAILED"
ERR_TIMEOUT = "TIMEOUT"

RECOVERABLE_ERRORS = frozenset(
    {
        ERR_TIMEOUT,
        ERR_RUNNER_FAILED,
    }
)

# raw URL 식별 — 별칭(alias) 과 구분.
_RAW_URL_PREFIXES = ("http://", "https://", "about:", "data:", "file://")


def _is_raw_url(s: str) -> bool:
    if not s:
        return False
    low = s.strip().lower()
    return low.startswith(_RAW_URL_PREFIXES)


# ── 데이터 ───────────────────────────────────────────────────────────


@dataclass
class ActionRequest:
    command_id: str
    action_type: str
    target_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    requested_at: float = 0.0


@dataclass
class ActionResult:
    ok: bool
    command_id: str
    action_type: str
    target_id: str = ""
    result: Any = None
    url: str = ""
    title: str = ""
    error_code: str = ""
    reason: str = ""
    recoverable: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = {
            "ok": self.ok,
            "command_id": self.command_id,
            "action_type": self.action_type,
            "target_id": self.target_id,
            "url": self.url,
            "title": self.title,
        }
        if self.ok:
            d["result"] = self.result
        else:
            d["error_code"] = self.error_code
            d["reason"] = self.reason
            d["recoverable"] = self.recoverable
        return d


# ── target 해석 ─────────────────────────────────────────────────────


def default_target_resolver(target_id: str) -> dict[str, Any]:
    """target_id 가 주어지면 session store 에서 상태 조회.

    Returns:
        {"exists": bool, "closed": bool, "url": str, "title": str}
    """
    if not target_id:
        return {"exists": True, "closed": False, "url": "", "title": ""}
    from core.agent_runtime.browser.browser_session_store import TAB_CLOSED, default_store

    rec = default_store.get_tab(target_id)
    if rec is None:
        return {"exists": False, "closed": False, "url": "", "title": ""}
    return {
        "exists": True,
        "closed": rec.status == TAB_CLOSED,
        "url": rec.url,
        "title": rec.title,
    }


# ── default runner (Playwright 의존) ────────────────────────────────


def _run_navigate(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("url") or params.get("target") or "")
    if not url:
        return {"ok": False, "error_code": ERR_INVALID_PARAMS, "reason": "url required"}
    # raw URL(http/https/about/data/file) 은 Playwright page.goto 직행.
    # 그 외(별칭) 는 기존 navigator.goto 의 alias resolver 사용.
    if _is_raw_url(url):
        try:
            from scripts.browser.cdp.connection import get_page

            get_page().goto(
                url,
                timeout=int(params.get("timeout_ms", 60000)),
            )
            return {"ok": True, "url": url}
        except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
            return {
                "ok": False,
                "error_code": ERR_RUNNER_FAILED,
                "reason": f"{type(exc).__name__}: {str(exc)[:200]}",
            }
    try:
        from scripts.browser.navigator import navigator as nav

        nav.goto(url, timeout_ms=int(params.get("timeout_ms", 60000)))
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
        return {"ok": False, "error_code": ERR_RUNNER_FAILED, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _run_click(params: dict[str, Any]) -> dict[str, Any]:
    from scripts.browser.navigator import navigator as nav

    target = str(params.get("text") or params.get("target") or "")
    if not target:
        return {"ok": False, "error_code": ERR_INVALID_PARAMS, "reason": "text required"}
    try:
        kind = params.get("kind", "button")
        ok = nav.click_link(target) if kind == "link" else nav.click_button(target)
        return {"ok": bool(ok)}
    except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
        return {"ok": False, "error_code": ERR_RUNNER_FAILED, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _run_type(params: dict[str, Any]) -> dict[str, Any]:
    from scripts.browser.navigator import navigator as nav

    target = str(params.get("target") or "")
    text = str(params.get("text") or "")
    if not target:
        return {"ok": False, "error_code": ERR_INVALID_PARAMS, "reason": "target required"}
    try:
        ok = nav.type_into(target, text, clear=bool(params.get("clear", True)))
        return {"ok": bool(ok)}
    except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
        return {"ok": False, "error_code": ERR_RUNNER_FAILED, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _run_submit(params: dict[str, Any]) -> dict[str, Any]:
    # 명시적 submit 지원 안 함 — Enter/click_button 으로 대체할 것.
    return {
        "ok": False,
        "error_code": ERR_UNSUPPORTED_ACTION,
        "reason": "submit not supported; use click_button(submit_label)",
    }


def _run_get_url(params: dict[str, Any]) -> dict[str, Any]:
    try:
        from scripts.browser.cdp.connection import get_page

        return {"ok": True, "url": get_page().url}
    except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
        return {"ok": False, "error_code": ERR_RUNNER_FAILED, "reason": str(exc)[:200]}


def _run_get_title(params: dict[str, Any]) -> dict[str, Any]:
    try:
        from scripts.browser.cdp.connection import get_page

        return {"ok": True, "title": get_page().title()}
    except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
        return {"ok": False, "error_code": ERR_RUNNER_FAILED, "reason": str(exc)[:200]}


def _run_wait_for_selector(params: dict[str, Any]) -> dict[str, Any]:
    try:
        from scripts.browser.cdp.connection import get_page

        selector = str(params.get("selector") or "")
        if not selector:
            return {"ok": False, "error_code": ERR_INVALID_PARAMS, "reason": "selector required"}
        get_page().wait_for_selector(
            selector,
            timeout=int(params.get("timeout_ms", 10000)),
        )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
        return {"ok": False, "error_code": ERR_TIMEOUT, "reason": str(exc)[:200]}



def default_runner(action_type: str, params: dict[str, Any]) -> dict[str, Any]:
    """scripts.browser.navigator.navigator 의 primitive 함수에 위임.

    모든 import 는 함수 내부에서 지연 — 단위 테스트는 본 함수를 호출하지 않는다.
    """
    if action_type == ACT_NAVIGATE:
        return _run_navigate(params)

    if action_type == ACT_CLICK:
        return _run_click(params)

    if action_type == ACT_TYPE:
        return _run_type(params)

    if action_type == ACT_SUBMIT:
        return _run_submit(params)

    if action_type == ACT_GET_URL:
        return _run_get_url(params)

    if action_type == ACT_GET_TITLE:
        return _run_get_title(params)

    if action_type == ACT_WAIT_FOR_SELECTOR:
        return _run_wait_for_selector(params)

    return {"ok": False, "error_code": ERR_UNSUPPORTED_ACTION, "reason": f"unknown action: {action_type}"}


# ── 핵심 실행 ────────────────────────────────────────────────────────


def execute(
    request: ActionRequest,
    *,
    target_resolver: Callable[[str], dict[str, Any]] | None = None,
    runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> ActionResult:
    if request.action_type not in SUPPORTED_ACTIONS:
        return ActionResult(
            ok=False,
            command_id=request.command_id,
            action_type=request.action_type,
            target_id=request.target_id,
            error_code=ERR_UNSUPPORTED_ACTION,
            reason=f"unknown action: {request.action_type}",
            recoverable=False,
        )

    resolver = target_resolver or default_target_resolver
    target_info = resolver(request.target_id)

    if request.target_id and not target_info.get("exists", False):
        return ActionResult(
            ok=False,
            command_id=request.command_id,
            action_type=request.action_type,
            target_id=request.target_id,
            error_code=ERR_TARGET_NOT_FOUND,
            reason=f"target {request.target_id!r} not found",
            recoverable=False,
        )

    if target_info.get("closed", False):
        return ActionResult(
            ok=False,
            command_id=request.command_id,
            action_type=request.action_type,
            target_id=request.target_id,
            error_code=ERR_TARGET_CLOSED,
            reason=f"target {request.target_id!r} is closed",
            recoverable=False,
        )

    run = runner or default_runner
    try:
        raw = run(request.action_type, request.params or {})
    except Exception as exc:  # noqa: BLE001 - 범용 브라우저 액션 실행기(goto/click/type) - 모든 except 가 ok:False,error_code,reason 반환, ACT_SUBMIT 은 실제 제출 미지원
        return ActionResult(
            ok=False,
            command_id=request.command_id,
            action_type=request.action_type,
            target_id=request.target_id,
            error_code=ERR_RUNNER_FAILED,
            reason=f"{type(exc).__name__}: {str(exc)[:200]}",
            recoverable=True,
        )

    ok = bool(raw.get("ok"))
    if ok:
        return ActionResult(
            ok=True,
            command_id=request.command_id,
            action_type=request.action_type,
            target_id=request.target_id,
            result=raw.get("result"),
            url=str(raw.get("url") or target_info.get("url") or ""),
            title=str(raw.get("title") or target_info.get("title") or ""),
        )
    err_code = str(raw.get("error_code") or ERR_RUNNER_FAILED)
    return ActionResult(
        ok=False,
        command_id=request.command_id,
        action_type=request.action_type,
        target_id=request.target_id,
        error_code=err_code,
        reason=str(raw.get("reason") or ""),
        recoverable=err_code in RECOVERABLE_ERRORS,
    )


def build_request_from_payload(payload: dict[str, Any]) -> ActionRequest:
    """UI/서버 payload 에서 ActionRequest 생성."""
    return ActionRequest(
        command_id=str(payload.get("command_id") or f"cmd_{int(time.time() * 1000)}"),
        action_type=str(payload.get("action_type") or ""),
        target_id=str(payload.get("target_id") or ""),
        params=dict(payload.get("params") or {}),
        requested_at=time.time(),
    )
