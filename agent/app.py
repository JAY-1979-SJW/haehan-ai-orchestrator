"""로컬 에이전트 진입점.

- ``run(action, ...)`` 으로 한 번의 action 수행 후 표준 dict 반환.
- 모든 action 은 ``{ok, action, data, error}`` 공통 형식을 따른다.
- 에러 코드는 ``agent.errors`` 의 상수로 표준화.
- 로그 entry 는 ``agent.action_registry`` 의 category/risk_level 을 부가.
- 실제 브라우저 실행/정책 검증은 여전히 ``runner`` / ``policy`` 에 위임한다.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from . import action_registry, errors, file_policy, runner
from .connectors import excel_connector
from .models import AgentRequest, AgentResult
from .policy import is_allowed_action, is_browser_action, validate_url

logger = logging.getLogger(__name__)

# ── 표준 에러 코드 alias (외부/테스트 하위 호환) ────────────────────────
ERR_ACTION_NOT_ALLOWED = errors.ACTION_NOT_ALLOWED
ERR_URL_NOT_ALLOWED = errors.URL_NOT_ALLOWED
ERR_CONCURRENT_LIMIT = errors.CONCURRENT_BROWSER_LIMIT
ERR_SITE_KEY_REQUIRED = errors.SITE_KEY_REQUIRED
ERR_LOGIN_FAILED = errors.LOGIN_FAILED
ERR_TARGET_URL_REQUIRED = errors.TARGET_URL_REQUIRED


# ── 공통 유틸 ──────────────────────────────────────────────────────────
def _now_iso() -> str:
    return runner._iso_now()


def _result(
    ok: bool,
    action: str,
    *,
    data: dict | None = None,
    error: str | None = None,
) -> dict:
    return AgentResult(
        ok=ok,
        action=str(action) if action is not None else "",
        data=data or {},
        error=error,
    ).to_dict()


def _log_base(
    action: str,
    *,
    start_ts: str,
    site_key: str = "",
    target_url: str = "",
) -> dict:
    """모든 로그 엔트리가 공유하는 표준 베이스.

    공통 필드:
    ``action, category, risk_level, site_key, target_url, start, timestamp``
    — timestamp 는 emit 시 end_ts 로 덮어쓰인다.
    """
    meta = action_registry.get_meta(action)
    return {
        "action": action,
        "category": meta.category if meta else action_registry.CATEGORY_UNKNOWN,
        "risk_level": meta.risk_level if meta else action_registry.RISK_UNKNOWN,
        "site_key": site_key,
        "target_url": runner._safe_url(target_url) if target_url else "",
        "start": start_ts,
        "timestamp": start_ts,
    }


def _emit(
    base: dict,
    *,
    start_mono: float,
    ok: bool,
    **extra: Any,
) -> str:
    """로그 한 줄 emit 후 end_ts 반환.

    표준 필드(end, timestamp, ok, duration_ms) 를 항상 부여하고
    ``extra`` 로 action 별 필드(login_url, final_url, error 등) 를 합친다.
    """
    end_ts = _now_iso()
    duration_ms = int((time.monotonic() - start_mono) * 1000)
    entry = {
        **base,
        "end": end_ts,
        "timestamp": end_ts,
        "ok": bool(ok),
        "duration_ms": duration_ms,
        **extra,
    }
    runner.log_event(entry)
    return end_ts


# ── 진입점 ─────────────────────────────────────────────────────────────
def run(
    action: str,
    url: str = "",
    *,
    site_key: str = "",
    target_url: str = "",
    options: dict | None = None,
    **_ignored,
) -> dict:
    """에이전트 메인 진입. 한 번의 action 을 수행한다.

    Returns:
      {"ok": bool, "action": str, "data": dict, "error": Optional[str]}
    """
    req = AgentRequest.from_kwargs(
        action=action,
        url=url,
        site_key=site_key,
        target_url=target_url,
        options=options,
    )
    act = req.action
    start_ts = _now_iso()
    start_mono = time.monotonic()
    safe_url = runner._safe_url(req.url) if req.url else ""

    # 공통 log base — action 별 분기에서 site_key/target_url 업데이트.
    log_base = _log_base(act, start_ts=start_ts, target_url=req.url)

    # 1) 허용 action 화이트리스트
    if not is_allowed_action(act):
        _emit(
            log_base,
            start_mono=start_mono,
            ok=False,
            blocked_reason=ERR_ACTION_NOT_ALLOWED,
            error=ERR_ACTION_NOT_ALLOWED,
        )
        return _result(
            False, act, data={"url": safe_url}, error=ERR_ACTION_NOT_ALLOWED,
        )

    # 2) 비(非) 브라우저 action 분기 — lock 불필요
    if act == "ping":
        data = runner.ping()
        _emit(
            log_base,
            start_mono=start_mono,
            ok=True,
            result="pong",
        )
        return _result(True, act, data=data)

    if act == "get_system_info":
        data = runner.get_system_info()
        _emit(
            log_base,
            start_mono=start_mono,
            ok=True,
            result="system_info",
        )
        return _result(True, act, data=data)

    # 3) 로그인 action 분기 — URL 대신 site_key 로 라우팅
    if act == "login_with_secret":
        skey = req.site_key.strip()
        log_base["site_key"] = skey

        def _login_fail(err: str, data: dict | None = None) -> dict:
            d = data or {}
            payload = {
                "site_key": skey,
                "login_url": runner._safe_url(d.get("login_url") or ""),
                "final_url": runner._safe_url(d.get("final_url") or ""),
                "login_success": False,
            }
            if d.get("checked_by"):
                payload["checked_by"] = d["checked_by"]
            _emit(
                log_base,
                start_mono=start_mono,
                ok=False,
                login_url=payload["login_url"],
                final_url=payload["final_url"],
                error=err,
            )
            return _result(False, act, data=payload, error=err)

        if not skey:
            return _login_fail(ERR_SITE_KEY_REQUIRED)

        acquired = runner._browser_lock.acquire(blocking=False)
        if not acquired:
            return _login_fail(ERR_CONCURRENT_LIMIT)
        try:
            data, err = runner.login_with_secret(skey)
        finally:
            runner._browser_lock.release()

        if err and not data:
            return _login_fail(err)

        data = data or {}
        login_url_safe = runner._safe_url(data.get("login_url") or "")
        final_url_safe = runner._safe_url(data.get("final_url") or "")
        login_success = bool(data.get("login_success", False))
        checked_by = data.get("checked_by")

        payload = {
            "site_key": skey,
            "login_url": login_url_safe,
            "final_url": final_url_safe,
            "login_success": login_success,
        }
        if checked_by:
            payload["checked_by"] = checked_by

        end_ts = _emit(
            log_base,
            start_mono=start_mono,
            ok=(login_success and not err),
            login_url=login_url_safe,
            final_url=final_url_safe,
            checked_by=checked_by,
            error=err,
        )
        payload["fetched_at"] = end_ts

        if err:
            return _result(False, act, data=payload, error=err)
        if not login_success:
            return _result(False, act, data=payload, error=ERR_LOGIN_FAILED)
        return _result(True, act, data=payload)

    # 3b) 로그인 후 탐색 분기 — site_key + target_url, 읽기 전용
    if act == "inspect_after_login":
        skey = req.site_key.strip()
        turl_raw = req.target_url or req.url
        turl = turl_raw.strip() if isinstance(turl_raw, str) else ""
        turl_safe = runner._safe_url(turl) if turl else ""
        log_base["site_key"] = skey
        log_base["target_url"] = turl_safe

        def _inspect_fail(err: str, data: dict | None = None) -> dict:
            d = data or {}
            payload = {
                "site_key": skey,
                "target_url": turl_safe,
                "login_success": bool(d.get("login_success", False)),
            }
            if d.get("final_url"):
                payload["final_url"] = runner._safe_url(d.get("final_url") or "")
            if d.get("checked_by"):
                payload["checked_by"] = d["checked_by"]
            _emit(
                log_base,
                start_mono=start_mono,
                ok=False,
                login_url=runner._safe_url(d.get("login_url") or ""),
                final_url=runner._safe_url(d.get("final_url") or ""),
                checked_by=d.get("checked_by"),
                blocked_reason=err,
                error=err,
            )
            return _result(False, act, data=payload, error=err)

        if not skey:
            return _inspect_fail(ERR_SITE_KEY_REQUIRED)
        if not turl:
            return _inspect_fail(ERR_TARGET_URL_REQUIRED)

        acquired = runner._browser_lock.acquire(blocking=False)
        if not acquired:
            return _inspect_fail(ERR_CONCURRENT_LIMIT)
        try:
            data, err = runner.inspect_after_login(skey, turl)
        finally:
            runner._browser_lock.release()

        if err and data is None:
            return _inspect_fail(err)

        data = data or {}
        login_url_safe = runner._safe_url(data.get("login_url") or "")
        final_url_safe = runner._safe_url(data.get("final_url") or "")

        if err:
            # login 실패 또는 target navigation/검증 실패
            payload = {
                "site_key": skey,
                "target_url": turl_safe,
                "login_success": bool(data.get("login_success", False)),
            }
            if data.get("final_url"):
                payload["final_url"] = final_url_safe
            if data.get("checked_by"):
                payload["checked_by"] = data["checked_by"]
            _emit(
                log_base,
                start_mono=start_mono,
                ok=False,
                login_url=login_url_safe,
                final_url=final_url_safe,
                checked_by=data.get("checked_by"),
                error=err,
            )
            return _result(False, act, data=payload, error=err)

        # 성공 — 읽기 전용 필드 전체 반환
        top_links = data.get("top_links") or []
        top_buttons = data.get("top_buttons") or []
        if not isinstance(top_links, list):
            top_links = []
        if not isinstance(top_buttons, list):
            top_buttons = []

        end_ts = _emit(
            log_base,
            start_mono=start_mono,
            ok=True,
            login_url=login_url_safe,
            final_url=final_url_safe,
            checked_by=data.get("checked_by"),
        )

        payload = {
            "site_key": skey,
            "login_success": True,
            "target_url": turl,
            "final_url": final_url_safe,
            "title": data.get("title", ""),
            "snippet": data.get("snippet", ""),
            "input_count": int(data.get("input_count", 0) or 0),
            "button_count": int(data.get("button_count", 0) or 0),
            "link_count": int(data.get("link_count", 0) or 0),
            "table_count": int(data.get("table_count", 0) or 0),
            "heading_count": int(data.get("heading_count", 0) or 0),
            "form_count": int(data.get("form_count", 0) or 0),
            "visible_text_length": int(data.get("visible_text_length", 0) or 0),
            "top_links": top_links[:10],
            "top_buttons": top_buttons[:10],
            "page_kind": data.get("page_kind") or "unknown",
            "checked_by": data.get("checked_by"),
            "fetched_at": end_ts,
        }
        if data.get("inspect_checked_by"):
            payload["inspect_checked_by"] = data["inspect_checked_by"]
        return _result(True, act, data=payload)

    # 3c) Excel 분기 — URL/브라우저 미사용, 허용 경로 내 파일 I/O.
    _EXCEL_ACTIONS = (
        "excel_read_sheet",
        "excel_write_report_copy",
        "excel_describe_workbook",
        "excel_read_table",
    )
    if act in _EXCEL_ACTIONS:
        opts = req.options or {}
        file_path_raw = opts.get("file_path", "")
        sheet_name = opts.get("sheet_name")
        range_ref = opts.get("range_ref")

        def _excel_fail(err: str, data: dict | None = None) -> dict:
            payload = dict(data or {})
            _emit(
                log_base,
                start_mono=start_mono,
                ok=False,
                blocked_reason=err,
                error=err,
            )
            return _result(False, act, data=payload, error=err)

        src_path, err = file_policy.resolve_input_path(
            file_path_raw if isinstance(file_path_raw, str) else ""
        )
        if err:
            return _excel_fail(err, {"file_path": ""})

        if act == "excel_read_sheet":
            sheet_arg = sheet_name if isinstance(sheet_name, str) and sheet_name else None
            range_arg = range_ref if isinstance(range_ref, str) and range_ref else None
            data, err = excel_connector.excel_read_sheet(
                src_path, sheet_name=sheet_arg, range_ref=range_arg,
            )
            if err or data is None:
                return _excel_fail(err or errors.EXCEL_ERROR, {"file_path": str(src_path)})

            end_ts = _emit(
                log_base,
                start_mono=start_mono,
                ok=True,
                sheet_name=data.get("sheet_name", ""),
                row_count=data.get("row_count", 0),
                column_count=data.get("column_count", 0),
            )
            data = {**data, "fetched_at": end_ts}
            return _result(True, act, data=data)

        if act == "excel_describe_workbook":
            data, err = excel_connector.describe_workbook(src_path)
            if err or data is None:
                return _excel_fail(
                    err or errors.EXCEL_ERROR, {"file_path": str(src_path)},
                )
            end_ts = _emit(
                log_base,
                start_mono=start_mono,
                ok=True,
                sheet_count=data.get("sheet_count", 0),
            )
            data = {**data, "fetched_at": end_ts}
            return _result(True, act, data=data)

        if act == "excel_read_table":
            sheet_arg = sheet_name if isinstance(sheet_name, str) and sheet_name else None
            header_row = opts.get("header_row", 1)
            max_rows = opts.get("max_rows")
            data, err = excel_connector.read_table(
                src_path,
                sheet_name=sheet_arg,
                header_row=header_row,
                max_rows=max_rows,
            )
            if err or data is None:
                return _excel_fail(
                    err or errors.EXCEL_ERROR, {"file_path": str(src_path)},
                )
            end_ts = _emit(
                log_base,
                start_mono=start_mono,
                ok=True,
                sheet_name=data.get("sheet_name", ""),
                row_count=data.get("row_count", 0),
                truncated=bool(data.get("truncated", False)),
            )
            data = {**data, "fetched_at": end_ts}
            return _result(True, act, data=data)

        # excel_write_report_copy
        output_path_raw = opts.get("output_path", "")
        rows = opts.get("rows")

        out_path, err = file_policy.resolve_output_path(
            output_path_raw if isinstance(output_path_raw, str) else "",
            source_path=src_path,
        )
        if err:
            return _excel_fail(err, {"source_file_path": str(src_path)})

        if not isinstance(rows, list):
            return _excel_fail(
                errors.ROWS_REQUIRED,
                {"source_file_path": str(src_path), "output_path": str(out_path)},
            )

        data, err = excel_connector.excel_write_report_copy(src_path, out_path, rows)
        if err or data is None:
            return _excel_fail(
                err or errors.EXCEL_ERROR,
                {"source_file_path": str(src_path), "output_path": str(out_path)},
            )

        end_ts = _emit(
            log_base,
            start_mono=start_mono,
            ok=True,
            written_row_count=data.get("written_row_count", 0),
        )
        data = {**data, "fetched_at": end_ts}
        return _result(True, act, data=data)

    # 4) 브라우저 action → URL 검증 후 lock 경유 실행
    if is_browser_action(act):
        ok, reason = validate_url(req.url)
        if not ok:
            err = errors.with_reason(ERR_URL_NOT_ALLOWED, reason)
            _emit(
                log_base,
                start_mono=start_mono,
                ok=False,
                blocked_reason=err,
                error=err,
            )
            return _result(False, act, data={"url": safe_url}, error=err)

        acquired = runner._browser_lock.acquire(blocking=False)
        if not acquired:
            _emit(
                log_base,
                start_mono=start_mono,
                ok=False,
                blocked_reason=ERR_CONCURRENT_LIMIT,
                error=ERR_CONCURRENT_LIMIT,
            )
            return _result(
                False, act, data={"url": safe_url},
                error=ERR_CONCURRENT_LIMIT,
            )
        try:
            data, err = runner.browser_readonly(
                req.url.strip(), inspect=(act == "inspect_page"),
            )
        finally:
            runner._browser_lock.release()

        if err:
            _emit(
                log_base,
                start_mono=start_mono,
                ok=False,
                error=err,
            )
            return _result(False, act, data={"url": safe_url}, error=err)

        end_ts = _emit(
            log_base,
            start_mono=start_mono,
            ok=True,
            final_url=runner._safe_url(data.get("final_url") or ""),
        )
        data = {"url": safe_url, **data, "fetched_at": end_ts}
        return _result(True, act, data=data)

    # 5) 방어: 여기까지 오면 action whitelist 는 통과했으나 분기 누락
    _emit(
        log_base,
        start_mono=start_mono,
        ok=False,
        blocked_reason=ERR_ACTION_NOT_ALLOWED,
        error=ERR_ACTION_NOT_ALLOWED,
    )
    return _result(
        False, act, data={"url": safe_url}, error=ERR_ACTION_NOT_ALLOWED,
    )


__all__ = [
    "run",
    "ERR_ACTION_NOT_ALLOWED",
    "ERR_URL_NOT_ALLOWED",
    "ERR_CONCURRENT_LIMIT",
    "ERR_SITE_KEY_REQUIRED",
    "ERR_LOGIN_FAILED",
    "ERR_TARGET_URL_REQUIRED",
]
