"""Sanitize helpers for observe_summary and audit_summary from WebSocket results."""

from __future__ import annotations

from urllib.parse import urlparse

# ── observe_summary 정책 ─────────────────────────────────────────────────

_OBSERVE_SUMMARY_ALLOWED_KEYS: frozenset = frozenset(
    {
        "target_kind",
        "url_category",
        "final_url_sanitized",
        "title",
        "title_len",
        "status_category",
        "pages_observed_count",
        "error_category",
        "blocked_reason",
        "login_required_hint",
        "modal_candidates_count",
        "html_truncated",
        "page_structure_counts",
        "observed_at",
    }
)

_OBSERVE_FORBIDDEN_KEYS: frozenset = frozenset(
    {
        "cookie",
        "session",
        "token",
        "authorization",
        "password",
        "localstorage",
        "sessionstorage",
        "html",
        "content",
        "body",
        "query",
        "fragment",
        "headers",
        "login_reason",
        "modal_candidates",
        "page_structure",
        "current_url",
    }
)

# ── audit_summary 정책 ───────────────────────────────────────────────────

_AUDIT_SUMMARY_ALLOWED_KEYS: frozenset = frozenset(
    {
        # STORE_AND_DISPLAY
        "audit_event_count",
        "audit_window_started_at",
        "audit_window_ended_at",
        "audit_event_categories",
        "blocked_event_count",
        "allowed_event_count",
        "denied_event_count",
        "error_event_count",
        "last_event_category",
        "last_event_status",
        "policy_decision_counts",
        "target_kind_counts",
        "action_kind_counts",
        # STORE_ONLY
        "audit_schema_version",
        "local_audit_source",
        "agent_reported_event_count",
        "audit_summary_generated_at",
        "audit_summary_hash",
        "dropped_event_count",
        "redacted_field_count",
    }
)

_AUDIT_SUMMARY_FORBIDDEN_KEYS: frozenset = frozenset(
    {
        "raw_events",
        "events",
        "event_list",
        "event_payload",
        "raw_audit",
        "audit_jsonl",
        "current_url",
        "url",
        "query",
        "fragment",
        "html",
        "text",
        "page_text",
        "modal_text",
        "selector",
        "screenshot_path",
        "local_file_path",
        "path",
        "absolute_path",
        "cookie",
        "session",
        "token",
        "password",
        "authorization",
        "headers",
        "request_headers",
        "response_headers",
        "request_body",
        "response_body",
        "body",
        "localstorage",
        "sessionstorage",
        "clipboard",
        "typed_text",
        "form_input_value",
        "username",
        "pc_username",
        "ip",
        "host",
    }
)

_PAGE_STRUCTURE_COUNT_KEYS: tuple = (
    "headings",
    "links",
    "buttons",
    "inputs",
    "forms",
    "tables",
)


def _sanitize_final_url_value(raw: object) -> str | None:
    """final_url_sanitized 검증: query/fragment 제거, 허용 대상만 반환."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.lower() == "about:blank":
        return "about:blank"
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if host in ("127.0.0.1", "localhost"):
            port_str = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{host}{port_str}{parsed.path}"
    except Exception:  # noqa: S110, BLE001 - URL sanitize 헬퍼 - urlparse 실패 시 None 반환(원본 노출 안 함), 쓰기 없음
        pass
    return None


def _audit_copy_counts(raw: dict, out: dict) -> None:
    for key in (
        "audit_event_count",
        "blocked_event_count",
        "allowed_event_count",
        "denied_event_count",
        "error_event_count",
        "agent_reported_event_count",
        "dropped_event_count",
        "redacted_field_count",
        "audit_schema_version",
    ):
        val = raw.get(key)
        if val is not None:
            try:
                count = max(0, int(val))
                out[key] = count
            except (TypeError, ValueError):
                pass


def _audit_copy_strings(raw: dict, out: dict) -> None:
    for key in ("last_event_category", "last_event_status", "local_audit_source"):
        val = raw.get(key)
        if val is not None and isinstance(val, str):
            out[key] = str(val)[:80]

    _audit_copy_categories(raw, out)

    for key in ("audit_window_started_at", "audit_window_ended_at", "audit_summary_generated_at"):
        val = raw.get(key)
        if val is not None and isinstance(val, str):
            out[key] = str(val)[:50]

    hash_val = raw.get("audit_summary_hash")
    if hash_val is not None and isinstance(hash_val, str):
        out["audit_summary_hash"] = str(hash_val)[:128]


def _audit_copy_categories(raw: dict, out: dict) -> None:
    categories = raw.get("audit_event_categories")
    if isinstance(categories, list):
        safe_cats = []
        for cat in categories:
            if isinstance(cat, str):
                cat_str = str(cat)[:50]
                if cat_str not in safe_cats:
                    safe_cats.append(cat_str)
        if safe_cats:
            out["audit_event_categories"] = safe_cats


def _audit_copy_count_dicts(raw: dict, out: dict) -> None:
    for dict_key in ("policy_decision_counts", "target_kind_counts", "action_kind_counts"):
        dict_val = raw.get(dict_key)
        if isinstance(dict_val, dict):
            safe_dict = {}
            for k, v in dict_val.items():
                if not isinstance(k, str):
                    continue
                safe_k = str(k)[:40]
                try:
                    safe_v = max(0, int(v))
                    safe_dict[safe_k] = safe_v
                except (TypeError, ValueError):
                    pass
            if safe_dict:
                out[dict_key] = safe_dict


def _build_audit_summary(raw: dict | None) -> dict | None:
    """WS result에서 받은 raw audit_summary를 allowlist로 sanitize.

    PC local audit.jsonl 원문 절대 포함 금지.
    """
    if not isinstance(raw, dict):
        return None

    out: dict = {}

    for bad_key in _AUDIT_SUMMARY_FORBIDDEN_KEYS:
        if bad_key in raw:
            pass

    _audit_copy_counts(raw, out)
    _audit_copy_strings(raw, out)
    _audit_copy_count_dicts(raw, out)

    return out if out else None


def _observe_copy_basic(raw: dict, out: dict) -> None:
    for key in (
        "target_kind",
        "url_category",
        "status_category",
        "error_category",
        "blocked_reason",
        "browser_channel",
    ):
        val = raw.get(key)
        if val is not None:
            out[key] = str(val)[:80]

    out["final_url_sanitized"] = _sanitize_final_url_value(raw.get("final_url_sanitized"))

    title = str(raw.get("title") or "")[:300]
    out["title"] = title
    try:
        out["title_len"] = int(raw.get("title_len") or len(title))
    except (TypeError, ValueError):
        out["title_len"] = len(title)

    for key in ("login_required_hint", "html_truncated", "browser_headless"):
        if key in raw:
            out[key] = bool(raw[key])


def _observe_copy_counts(raw: dict, out: dict) -> None:
    for key in ("pages_observed_count", "modal_candidates_count", "browser_keep_open_ms"):
        val = raw.get(key)
        if val is not None:
            try:
                out[key] = max(0, int(val))
            except (TypeError, ValueError):
                out[key] = 0

    psc = raw.get("page_structure_counts")
    if isinstance(psc, dict):
        safe_counts: dict = {}
        for k in _PAGE_STRUCTURE_COUNT_KEYS:
            try:
                safe_counts[k] = max(0, int(psc.get(k) or 0))
            except (TypeError, ValueError):
                safe_counts[k] = 0
        out["page_structure_counts"] = safe_counts

    ts = raw.get("observed_at")
    if isinstance(ts, str) and ts:
        out["observed_at"] = ts[:40]


def _build_observe_summary(raw: dict | None) -> dict | None:
    """WS result에서 받은 raw observe_summary를 허용 필드만 추출/sanitize.

    금지 키(cookie/session/token/authorization/password/html 등)는 포함하지 않는다.
    final_url_sanitized는 반드시 재검증한다.
    """
    if not isinstance(raw, dict):
        return None

    out: dict = {}

    _observe_copy_basic(raw, out)
    _observe_copy_counts(raw, out)

    for bad_key in _OBSERVE_FORBIDDEN_KEYS:
        out.pop(bad_key, None)

    return out if out else None


__all__ = [
    "_AUDIT_SUMMARY_ALLOWED_KEYS",
    "_AUDIT_SUMMARY_FORBIDDEN_KEYS",
    "_OBSERVE_FORBIDDEN_KEYS",
    "_OBSERVE_SUMMARY_ALLOWED_KEYS",
    "_PAGE_STRUCTURE_COUNT_KEYS",
    "_build_audit_summary",
    "_build_observe_summary",
    "_sanitize_final_url_value",
]
