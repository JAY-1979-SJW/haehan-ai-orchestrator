"""live_inputs CDP 세션/연결 (공유 leaf).

직접 CDP 타깃 세션 생성/연결/식별/미완기록. config(공유 leaf)만 의존,
다른 live_inputs 함수 호출 없음. [docs/module_separation_standard.md]
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

import requests

from scripts.google.common.live_inputs_config import _cdp_websocket_timeout


class _CDPSessionManager:
    def __init__(self, session: Any):
        self._session = session

    def __enter__(self) -> Any:
        return self._session

    def __exit__(self, *_: Any) -> None:
        self._session.close()


def _new_cdp_target_session(target_url: str) -> _CDPSessionManager:
    from scripts.browser.cdp.cdp_console import CDPSession
    from scripts.common.config import CDP_HOST, CDP_PORT

    encoded_url = quote(target_url, safe=":/?&=%#")
    endpoint = f"http://{CDP_HOST}:{CDP_PORT}/json/new?{encoded_url}"
    timeout = min(max(5.0, _cdp_websocket_timeout()), 30.0)
    last_error: Exception | None = None
    for method in (requests.put, requests.get):
        try:
            response = method(endpoint, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            ws_url = payload.get("webSocketDebuggerUrl")
            if not ws_url:
                raise RuntimeError("CDP new target response did not include websocket URL")
            return _CDPSessionManager(CDPSession(ws_url, timeout=_cdp_websocket_timeout()))
        except Exception as exc:  # noqa: BLE001 - CDP 세션 연결 유틸 - 연결 실패를 경고 목록에 누적하며 다음 후보로 폴백, 최종 실패 시 명시적으로 raise
            last_error = exc
    raise RuntimeError(f"CDP new target unavailable: {last_error}")


def _live_input_target_url(action: dict, values: dict) -> str:
    target = action.get("target_url", "")
    if action.get("key") == "cloud_iam_change_role" and values.get("project") and "project=" not in target:
        separator = "&" if "?" in target else "?"
        target = f"{target}{separator}project={quote(str(values['project']), safe='')}"
    return target


def _connect_live_input_cdp(action: dict, result: dict) -> Any:
    from scripts.browser.cdp.cdp_console import connect

    target_url = action.get("target_url", "")
    try:
        return _new_cdp_target_session(target_url)
    except Exception as exc:  # noqa: BLE001 - CDP 세션 연결 유틸 - 연결 실패를 경고 목록에 누적하며 다음 후보로 폴백, 최종 실패 시 명시적으로 raise
        result["warnings"].append(f"cdp_new_target_unavailable: {exc}")

    host = urlsplit(target_url).netloc
    for token in (host, "google", ""):
        try:
            return connect(url_contains=token, websocket_timeout=_cdp_websocket_timeout())
        except Exception as exc:  # noqa: BLE001 - CDP 세션 연결 유틸 - 연결 실패를 경고 목록에 누적하며 다음 후보로 폴백, 최종 실패 시 명시적으로 raise
            result["warnings"].append(f"cdp_existing_tab_unavailable({token or 'any'}): {exc}")
    raise RuntimeError("no usable CDP tab")


def _safe_cdp_identity(session: Any, action: dict) -> dict:
    identity = {"current_url": "", "title": ""}
    if session is not None:
        try:
            identity["current_url"] = session.url
        except Exception:  # noqa: BLE001 - CDP 세션 연결 유틸 - 연결 실패를 경고 목록에 누적하며 다음 후보로 폴백, 최종 실패 시 명시적으로 raise
            identity["current_url"] = ""
        try:
            identity["title"] = session.title
        except Exception:  # noqa: BLE001 - CDP 세션 연결 유틸 - 연결 실패를 경고 목록에 누적하며 다음 후보로 폴백, 최종 실패 시 명시적으로 raise
            identity["title"] = ""
    if session is not None and not identity["current_url"] and action.get("target_url"):
        identity["current_url"] = action["target_url"]
    return identity


def _record_direct_cdp_incomplete(action: dict, result: dict, session: Any, exc: Exception) -> None:
    identity = _safe_cdp_identity(session, action)
    result.update(identity)
    current_url = identity.get("current_url", "")
    if current_url and current_url != "about:blank":
        result["status"] = "opened_no_final_submit"
        result["warnings"].append(f"direct_cdp_live_input_incomplete_after_open: {exc}")
    else:
        result["status"] = "blocked_browser_control_unavailable"
        result["warnings"].append(f"direct_cdp_live_input_blocked: {exc}")
    result["state_change_final_button_clicked"] = False
