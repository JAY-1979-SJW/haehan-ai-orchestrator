"""로컬 에이전트 민감정보 제거 정책 (Stage 1/2 공용).

params, result_data, observe_summary, audit_summary에서
민감 키(password/token/secret/cookie 등)를 필터링하고,
result_data는 명시적 허용 목록만 저장하는 정책을 정의한다.

정책:
  - _SENSITIVE_KEYS: params/result에서 절대 저장·노출 금지 (60개)
  - _strip_sensitive(): params 필터링 (저장 전)
  - _RESULT_DATA_ALLOWED_KEYS: result_data 저장 허용 목록 (명시적 허용)
  - _sanitize_url_for_storage(): URL 쿼리 제거
  - _strip_result_data(): result_data 필터링 (저장 전, 이중 방어)
"""

# params / result 에서 절대 저장·노출 금지인 키
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "session_token",
    "device_token", "approval_token", "final_approval_token", "token_hash",
    "cookie", "cookies", "session",
    "client_secret", "secret", "api_secret", "api_key",
    "auth", "authorization",
})


def _strip_sensitive(params: dict) -> dict:
    """민감 키를 제거한 새 dict 반환 (저장·로그용)."""
    if not params:
        return {}
    return {k: v for k, v in params.items() if k.lower() not in _SENSITIVE_KEYS}


# result_data 에 저장 허용된 key 목록 (명시적 허용 목록 방식)
_RESULT_DATA_ALLOWED_KEYS: frozenset[str] = frozenset({
    "action", "dry_run", "normalized_url", "url_scheme", "url_host",
    "would_open_browser", "external_network_call", "requires_approval",
    "policy_decision", "message", "reason", "error_code",
    "approval_id", "approved_by", "execution_task_id",
    # capture_screenshot safe metadata (Stage 13H-2)
    "screenshot_taken", "file_basename", "file_ext", "file_size_bytes",
    "image_width", "image_height", "storage_ref",
    "redaction_applied", "sensitive_screen_warning",
    # dry_run capture_screenshot self-check
    "screenshot_dir_ready", "backend_available", "upload",
    # browser action safe result metadata (BROWSER-4E)
    "status", "selector", "executed", "element_found", "risk_level",
    "final_approval_required", "result", "target_url_domain", "text_length",
    "text_preview", "error_message", "screenshot_ref",
})


def _sanitize_url_for_storage(url: str) -> str:
    """URL에서 query string을 제거하고 scheme+host+path만 반환."""
    from urllib.parse import urlparse, urlunparse
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return ""


def _strip_result_data(data: object) -> "dict | None":
    """agent result data를 안전 필터 후 반환.

    - 허용 key(_RESULT_DATA_ALLOWED_KEYS)만 저장
    - url 계열 값은 query string 제거
    - 민감 key(_SENSITIVE_KEYS)는 이중 방어로 항상 drop
    - 값이 dict/list 인 경우 재귀 없이 str 변환 후 저장
    - None 또는 빈 dict이면 None 반환
    """
    if not isinstance(data, dict) or not data:
        return None
    out: dict = {}
    for k, v in data.items():
        k_low = k.lower()
        if k_low in _SENSITIVE_KEYS:
            continue
        if k_low not in _RESULT_DATA_ALLOWED_KEYS:
            continue
        # url 계열 값 sanitize
        if k_low in ("normalized_url",) and isinstance(v, str):
            v = _sanitize_url_for_storage(v)
        # bool/int/None 은 그대로 저장, 나머지는 str로 제한
        if isinstance(v, (bool, int, float, type(None))):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:500]
        else:
            out[k] = str(v)[:500]
    return out or None
