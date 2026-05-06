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
    # safe_desktop_capability result metadata
    "capabilities",
    # safe_app_presence_known_paths result metadata
    "detection_mode", "apps",
    # browser.plan_open_url result metadata
    "plan", "target",
    # browser.inspect result metadata
    "inspection_mode",
    # browser.plan_click result metadata
    "click_target",
    # browser.plan_type result metadata
    "typed", "field_id", "field_role", "sample_value_id", "input_redacted", "timestamp",
    # browser.open_url_controlled result metadata
    "execution_mode", "approval_required", "browser",
    # browser.open_click_close_controlled result metadata
    "clicked_target", "url_info", "navigation", "cleanup",
})

# safe_desktop_capability capabilities 내부 허용 key (nested boolean allowlist)
# browser.inspect capabilities 내부 허용 key 포함
_CAPABILITIES_ALLOWED_KEYS: frozenset[str] = frozenset({
    "browser_supported", "office_supported", "cad_supported",
    "can_plan_inspection", "actual_inspection_enabled",
})

# safe_app_presence_known_paths 및 safe_app_capability_matrix apps 항목 내부 허용 key
_APPS_ITEM_ALLOWED_KEYS: frozenset[str] = frozenset({
    "app_id", "supported", "next_actions",
})

# safe_app_capability_matrix next_actions 허용 목록 (고정 allowlist)
_NEXT_ACTIONS_ALLOWED: frozenset[str] = frozenset({
    "browser_plan_open_url",
    "browser_inspect",
    "excel_plan_open_workbook",
    "cad_plan_open_file",
})

# browser.plan_open_url plan 내부 허용 key
# browser.inspect plan 내부 허용 key 포함
# browser.plan_click plan 내부 허용 key 포함
_PLAN_ALLOWED_KEYS: frozenset[str] = frozenset({
    "action_id", "will_open_browser", "will_navigate", "requires_approval",
    "will_access_dom", "will_capture_screenshot", "will_click",
})

# browser.plan_open_url target 내부 허용 key
_TARGET_ALLOWED_KEYS: frozenset[str] = frozenset({
    "scheme", "host_class", "url_redacted",
})

# browser.plan_open_url target scheme 허용값
_TARGET_SCHEME_ALLOWED: frozenset[str] = frozenset({
    "http", "https",
})

# browser.plan_open_url target host_class 허용값
_TARGET_HOST_CLASS_ALLOWED: frozenset[str] = frozenset({
    "public", "private_or_local", "blocked", "invalid", "sample",
})

# browser.inspect inspection_mode 허용값
_INSPECTION_MODE_ALLOWED: frozenset[str] = frozenset({
    "page_layout", "accessibility_tree",
})

# browser.open_url_controlled browser 내부 허용 key
_BROWSER_ALLOWED_KEYS: frozenset[str] = frozenset({
    "isolated_context", "used_existing_profile", "opened", "closed", "clicked",
})

# browser.plan_click click_target 내부 허용 key
_CLICK_TARGET_ALLOWED_KEYS: frozenset[str] = frozenset({
    "target_id", "target_role", "selector_redacted",
})

# browser.plan_click target_id 허용값
_CLICK_TARGET_ID_ALLOWED: frozenset[str] = frozenset({
    "sample_primary_action", "sample_secondary_action",
})

# browser.plan_click target_role 허용값
_CLICK_TARGET_ROLE_ALLOWED: frozenset[str] = frozenset({
    "primary_action", "secondary_action", "navigation_link",
})

# browser.open_click_close_controlled url_info 내부 허용 key
_URL_INFO_ALLOWED_KEYS: frozenset[str] = frozenset({
    "scheme", "host_class", "url_redacted",
})

# browser.open_click_close_controlled navigation 내부 허용 key
_NAVIGATION_ALLOWED_KEYS: frozenset[str] = frozenset({
    "will_navigate",
})

# browser.open_click_close_controlled cleanup 내부 허용 key
_CLEANUP_ALLOWED_KEYS: frozenset[str] = frozenset({
    "context_closed", "browser_closed", "temp_files_deleted",
})

# browser.open_click_close_controlled clicked_target 내부 허용 key
# browser.plan_click click_target과 동일
_CLICKED_TARGET_ALLOWED_KEYS: frozenset[str] = frozenset({
    "target_id", "target_role", "selector_redacted",
})


def _strip_capabilities(value: object) -> "dict | None":
    """capabilities nested allowlist: boolean 값만 저장.

    - dict가 아니면 None 반환
    - 허용 key(browser_supported/office_supported/cad_supported)만 유지
    - 각 값이 bool일 때만 저장
    - bool이 아닌 값은 제거
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _CAPABILITIES_ALLOWED_KEYS:
            continue
        if isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_apps(value: object) -> "list | None":
    """apps nested allowlist: app_id/supported/next_actions만 저장.

    - list가 아니면 None 반환
    - 각 항목이 dict여야 함
    - 허용 key(app_id/supported/next_actions)만 유지
    - app_id는 str, supported는 bool만 저장
    - next_actions는 list이고, 각 항목은 _NEXT_ACTIONS_ALLOWED만 포함
    - 빈 list면 None 반환
    """
    if not isinstance(value, list):
        return None
    out: list = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entry: dict = {}
        for k, v in item.items():
            k_low = k.lower()
            if k_low not in _APPS_ITEM_ALLOWED_KEYS:
                continue
            if k_low == "supported" and isinstance(v, bool):
                entry[k] = v
            elif k_low == "app_id" and isinstance(v, str):
                entry[k] = v[:200]
            elif k_low == "next_actions" and isinstance(v, list):
                # next_actions allowlist: 허용된 action만 유지
                actions = [a for a in v if isinstance(a, str) and a in _NEXT_ACTIONS_ALLOWED]
                entry[k] = actions
        if entry and "app_id" in entry and "supported" in entry:
            out.append(entry)
    return out if out else None


def _sanitize_url_for_storage(url: str) -> str:
    """URL에서 query string을 제거하고 scheme+host+path만 반환."""
    from urllib.parse import urlparse, urlunparse
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return ""


def _strip_plan(value: object) -> "dict | None":
    """browser.plan_open_url/browser.inspect plan nested allowlist.

    - dict가 아니면 None 반환
    - 허용 key만 유지 (action_id, will_* 계열, requires_approval)
    - action_id는 str (길이 200 제한)
    - will_* 및 requires_approval은 bool만 저장
    - bool이 아닌 값은 제거
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _PLAN_ALLOWED_KEYS:
            continue
        if k_low == "action_id" and isinstance(v, str):
            out[k] = v[:200]
        elif k_low in ("will_open_browser", "will_navigate", "will_access_dom", "will_capture_screenshot", "requires_approval"):
            if isinstance(v, bool):
                out[k] = v
    return out if out else None


def _strip_target(value: object) -> "dict | None":
    """browser.plan_open_url target nested allowlist.

    - dict가 아니면 None 반환
    - 허용 key(scheme/host_class/url_redacted)만 유지
    - scheme은 str이고 _TARGET_SCHEME_ALLOWED에만 포함 (http/https)
    - host_class는 str이고 _TARGET_HOST_CLASS_ALLOWED에만 포함
    - url_redacted는 bool만 저장
    - 제한된 값만 저장
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _TARGET_ALLOWED_KEYS:
            continue
        if k_low == "scheme" and isinstance(v, str):
            if v.lower() in _TARGET_SCHEME_ALLOWED:
                out[k] = v.lower()
        elif k_low == "host_class" and isinstance(v, str):
            if v.lower() in _TARGET_HOST_CLASS_ALLOWED:
                out[k] = v.lower()
        elif k_low == "url_redacted" and isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_browser(value: object) -> "dict | None":
    """browser.open_url_controlled browser nested allowlist.

    - dict가 아니면 None 반환
    - 허용 key(isolated_context/used_existing_profile/opened/closed)만 유지
    - 각 값은 bool만 저장
    - bool이 아닌 값은 제거
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _BROWSER_ALLOWED_KEYS:
            continue
        if isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_click_target(value: object) -> "dict | None":
    """browser.plan_click click_target nested allowlist.

    - dict가 아니면 None 반환
    - 허용 key(target_id/target_role/selector_redacted)만 유지
    - target_id는 str이고 _CLICK_TARGET_ID_ALLOWED에만 포함
    - target_role은 str이고 _CLICK_TARGET_ROLE_ALLOWED에만 포함
    - selector_redacted는 bool만 저장
    - 제한된 값만 저장
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _CLICK_TARGET_ALLOWED_KEYS:
            continue
        if k_low == "target_id" and isinstance(v, str):
            if v in _CLICK_TARGET_ID_ALLOWED:
                out[k] = v
        elif k_low == "target_role" and isinstance(v, str):
            if v in _CLICK_TARGET_ROLE_ALLOWED:
                out[k] = v
        elif k_low == "selector_redacted" and isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_url_info(value: object) -> "dict | None":
    """browser.open_click_close_controlled url_info nested allowlist.

    - dict가 아니면 None 반환
    - 허용 key(scheme/host_class/url_redacted)만 유지
    - scheme은 _TARGET_SCHEME_ALLOWED에만 포함
    - host_class는 _TARGET_HOST_CLASS_ALLOWED에만 포함
    - url_redacted는 bool만 저장
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _URL_INFO_ALLOWED_KEYS:
            continue
        if k_low == "scheme" and isinstance(v, str):
            if v in _TARGET_SCHEME_ALLOWED:
                out[k] = v
        elif k_low == "host_class" and isinstance(v, str):
            if v in _TARGET_HOST_CLASS_ALLOWED:
                out[k] = v
        elif k_low == "url_redacted" and isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_navigation(value: object) -> "dict | None":
    """browser.open_click_close_controlled navigation nested allowlist.

    - dict가 아니면 None 반환
    - 허용 key(will_navigate)만 유지
    - will_navigate는 bool만 저장
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _NAVIGATION_ALLOWED_KEYS:
            continue
        if k_low == "will_navigate" and isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_cleanup(value: object) -> "dict | None":
    """browser.open_click_close_controlled cleanup nested allowlist.

    - dict가 아니면 None 반환
    - 허용 key(context_closed/browser_closed/temp_files_deleted)만 유지
    - 모든 value는 bool만 저장
    - 빈 dict면 None 반환
    """
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        k_low = k.lower()
        if k_low not in _CLEANUP_ALLOWED_KEYS:
            continue
        if isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_result_data(data: object) -> "dict | None":
    """agent result data를 안전 필터 후 반환.

    - 허용 key(_RESULT_DATA_ALLOWED_KEYS)만 저장
    - url 계열 값은 query string 제거
    - capabilities는 nested allowlist(_strip_capabilities) 적용
    - apps는 nested allowlist(_strip_apps) 적용
    - 민감 key(_SENSITIVE_KEYS)는 이중 방어로 항상 drop
    - 값이 dict/list 인 경우 재귀 없이 str 변환 후 저장 (capabilities, apps 제외)
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
        # capabilities 특별 처리: nested boolean allowlist
        if k_low == "capabilities":
            capabilities = _strip_capabilities(v)
            if capabilities is not None:
                out[k] = capabilities
            continue
        # apps 특별 처리: nested list allowlist
        if k_low == "apps":
            apps = _strip_apps(v)
            if apps is not None:
                out[k] = apps
            continue
        # plan 특별 처리: nested allowlist
        if k_low == "plan":
            plan = _strip_plan(v)
            if plan is not None:
                out[k] = plan
            continue
        # target 특별 처리: nested allowlist
        if k_low == "target":
            target = _strip_target(v)
            if target is not None:
                out[k] = target
            continue
        # inspection_mode 특별 처리: enum 검증
        if k_low == "inspection_mode":
            if isinstance(v, str) and v in _INSPECTION_MODE_ALLOWED:
                out[k] = v
            continue
        # browser 특별 처리: nested boolean allowlist
        if k_low == "browser":
            browser = _strip_browser(v)
            if browser is not None:
                out[k] = browser
            continue
        # click_target 특별 처리: nested enum allowlist
        if k_low == "click_target":
            click_target = _strip_click_target(v)
            if click_target is not None:
                out[k] = click_target
            continue
        # clicked_target 특별 처리: click_target과 동일
        if k_low == "clicked_target":
            clicked_target = _strip_click_target(v)
            if clicked_target is not None:
                out[k] = clicked_target
            continue
        # url_info 특별 처리: nested allowlist
        if k_low == "url_info":
            url_info = _strip_url_info(v)
            if url_info is not None:
                out[k] = url_info
            continue
        # navigation 특별 처리: nested allowlist
        if k_low == "navigation":
            navigation = _strip_navigation(v)
            if navigation is not None:
                out[k] = navigation
            continue
        # cleanup 특별 처리: nested allowlist
        if k_low == "cleanup":
            cleanup = _strip_cleanup(v)
            if cleanup is not None:
                out[k] = cleanup
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
