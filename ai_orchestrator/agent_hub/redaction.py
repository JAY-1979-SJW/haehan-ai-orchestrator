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

import re
from collections.abc import Callable

from ai_orchestrator.contracts.agent_result_limits import RESULT_FULL_MAX_CHARS

# params / result 에서 절대 저장·노출 금지인 키
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "session_token",
        "device_token",
        "approval_token",
        "final_approval_token",
        "token_hash",
        "cookie",
        "cookies",
        "session",
        "client_secret",
        "secret",
        "api_secret",
        "api_key",
        "auth",
        "authorization",
    }
)


def _strip_sensitive(params: dict) -> dict:
    """민감 키를 제거한 새 dict 반환 (저장·로그용)."""
    if not params:
        return {}
    return {k: v for k, v in params.items() if k.lower() not in _SENSITIVE_KEYS}


# result_data 에 저장 허용된 key 목록 (명시적 허용 목록 방식)
_RESULT_DATA_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "action",
        "dry_run",
        "normalized_url",
        "url_scheme",
        "url_host",
        "would_open_browser",
        "external_network_call",
        "requires_approval",
        "policy_decision",
        "message",
        "reason",
        "error_code",
        "approval_id",
        "approved_by",
        "execution_task_id",
        # capture_screenshot safe metadata (Stage 13H-2)
        "screenshot_taken",
        "file_basename",
        "file_ext",
        "file_size_bytes",
        "image_width",
        "image_height",
        "storage_ref",
        "redaction_applied",
        "sensitive_screen_warning",
        # dry_run capture_screenshot self-check
        "screenshot_dir_ready",
        "backend_available",
        "upload",
        # browser action safe result metadata (BROWSER-4E)
        "status",
        "selector",
        "executed",
        "element_found",
        "risk_level",
        "final_approval_required",
        "result",
        "result_full",  # 작업 분배용 긴 결과(run_claude_agent result_max_chars)
        "target_url_domain",
        "text_length",
        "text_preview",
        "error_message",
        "screenshot_ref",
        # safe_desktop_capability result metadata
        "capabilities",
        # safe_app_presence_known_paths result metadata
        "detection_mode",
        "apps",
        # browser.plan_open_url result metadata
        "plan",
        "target",
        # browser.inspect result metadata
        "inspection_mode",
        # browser.plan_click result metadata
        "click_target",
        # browser.plan_type result metadata
        "typed",
        "field_id",
        "field_role",
        "sample_value_id",
        "input_redacted",
        "timestamp",
        # browser.open_url_controlled result metadata
        "execution_mode",
        "approval_required",
        "browser",
        # browser.open_click_close_controlled result metadata
        "clicked_target",
        "url_info",
        "navigation",
        "cleanup",
        # browser.open_type_close_controlled result metadata
        "lifecycle",
        # run_claude_agent result metadata (2026-09-30, 대화 이어가기/비용 표시용)
        # — session_id는 자격증명이 아니라 Claude Code 대화 연속성 식별자(claude -r 재사용),
        #   cost_usd/num_turns는 UI 비용 표시용. 전부 credential/PII 아님.
        "session_id",
        "cost_usd",
        "num_turns",
    }
)

# safe_desktop_capability capabilities 내부 허용 key (nested boolean allowlist)
# browser.inspect capabilities 내부 허용 key 포함
_CAPABILITIES_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "browser_supported",
        "office_supported",
        "cad_supported",
        "can_plan_inspection",
        "actual_inspection_enabled",
    }
)

# safe_app_presence_known_paths 및 safe_app_capability_matrix apps 항목 내부 허용 key
_APPS_ITEM_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "app_id",
        "supported",
        "next_actions",
    }
)

# safe_app_capability_matrix next_actions 허용 목록 (고정 allowlist)
_NEXT_ACTIONS_ALLOWED: frozenset[str] = frozenset(
    {
        "browser_plan_open_url",
        "browser_inspect",
        "excel_plan_open_workbook",
        "cad_plan_open_file",
    }
)

# browser.plan_open_url plan 내부 허용 key
# browser.inspect plan 내부 허용 key 포함
# browser.plan_click plan 내부 허용 key 포함
_PLAN_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "action_id",
        "will_open_browser",
        "will_navigate",
        "requires_approval",
        "will_access_dom",
        "will_capture_screenshot",
        "will_click",
    }
)

# browser.plan_open_url target 내부 허용 key
_TARGET_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "scheme",
        "host_class",
        "url_redacted",
    }
)

# browser.plan_open_url target scheme 허용값
_TARGET_SCHEME_ALLOWED: frozenset[str] = frozenset(
    {
        "http",
        "https",
    }
)

# browser.plan_open_url target host_class 허용값
_TARGET_HOST_CLASS_ALLOWED: frozenset[str] = frozenset(
    {
        "public",
        "private_or_local",
        "blocked",
        "invalid",
        "sample",
    }
)

# browser.inspect inspection_mode 허용값
_INSPECTION_MODE_ALLOWED: frozenset[str] = frozenset(
    {
        "page_layout",
        "accessibility_tree",
    }
)

# browser.open_url_controlled browser 내부 허용 key
_BROWSER_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "isolated_context",
        "used_existing_profile",
        "opened",
        "closed",
        "clicked",
    }
)

# browser.plan_click click_target 내부 허용 key
_CLICK_TARGET_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "target_id",
        "target_role",
        "selector_redacted",
    }
)

# browser.plan_click target_id 허용값
_CLICK_TARGET_ID_ALLOWED: frozenset[str] = frozenset(
    {
        "sample_primary_action",
        "sample_secondary_action",
    }
)

# browser.plan_click target_role 허용값
_CLICK_TARGET_ROLE_ALLOWED: frozenset[str] = frozenset(
    {
        "primary_action",
        "secondary_action",
        "navigation_link",
    }
)

# browser.open_click_close_controlled url_info 내부 허용 key
_URL_INFO_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "scheme",
        "host_class",
        "url_redacted",
    }
)

# browser.open_click_close_controlled navigation 내부 허용 key
_NAVIGATION_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "will_navigate",
    }
)

# browser.open_click_close_controlled cleanup 내부 허용 key
_CLEANUP_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "context_closed",
        "browser_closed",
        "temp_files_deleted",
    }
)

# browser.open_type_close_controlled lifecycle 내부 허용 key
_LIFECYCLE_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "opened",
        "typed",
        "closed",
    }
)

# browser.open_click_close_controlled clicked_target 내부 허용 key
# browser.plan_click click_target과 동일
_CLICKED_TARGET_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "target_id",
        "target_role",
        "selector_redacted",
    }
)


def _strip_bool_allowlist(value: object, allowed_keys: frozenset[str]) -> "dict | None":
    """공통 패턴(G12 중복정리, 2026-10-09): dict가 아니면 None, 허용 key만 유지, 값이
    bool 일 때만 저장(아니면 그 key 는 버림), 결과가 빈 dict면 None. _strip_capabilities·
    _strip_browser·_strip_cleanup·_strip_lifecycle 4개가 허용 key 목록만 다르고 로직은
    동일해서(구조동일 중복, dup_gate G12) 공통화했다 — 동작은 그대로, 각 함수는 자기 허용
    목록으로 이 함수를 부르는 1줄 래퍼."""
    if not isinstance(value, dict):
        return None
    out: dict = {}
    for k, v in value.items():
        if k.lower() not in allowed_keys:
            continue
        if isinstance(v, bool):
            out[k] = v
    return out if out else None


def _strip_capabilities(value: object) -> "dict | None":
    """capabilities nested allowlist: boolean 값만 저장(허용 key: browser_supported/
    office_supported/cad_supported)."""
    return _strip_bool_allowlist(value, _CAPABILITIES_ALLOWED_KEYS)


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
    except Exception:  # noqa: BLE001 - URL 쿼리 제거 후 저장용 sanitize 헬퍼 - urlparse 실패 시 원본 URL 대신 빈 문자열로 폴백(민감정보 노출 방지 방향), 쓰기 없음
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
        elif k_low in (
            "will_open_browser",
            "will_navigate",
            "will_access_dom",
            "will_capture_screenshot",
            "requires_approval",
        ) and isinstance(v, bool):
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
    """browser.open_url_controlled browser nested allowlist(허용 key: isolated_context/
    used_existing_profile/opened/closed, boolean 값만 저장)."""
    return _strip_bool_allowlist(value, _BROWSER_ALLOWED_KEYS)


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
    """browser.open_click_close_controlled cleanup nested allowlist(허용 key: context_closed/
    browser_closed/temp_files_deleted, boolean 값만 저장)."""
    return _strip_bool_allowlist(value, _CLEANUP_ALLOWED_KEYS)


def _strip_lifecycle(value: object) -> "dict | None":
    """browser.open_type_close_controlled lifecycle nested allowlist.

    허용 key(opened/typed/closed)만 유지, boolean 값만 저장."""
    return _strip_bool_allowlist(value, _LIFECYCLE_ALLOWED_KEYS)


def _strip_inspection_mode(v: object) -> object | None:
    """inspection_mode 특별 처리: enum 검증(2026-09-29 STD-08 분리, 로직 동일)."""
    return v if isinstance(v, str) and v in _INSPECTION_MODE_ALLOWED else None


# k_low(소문자 key) → 그 값을 필터링하는 함수. _strip_result_data() 의 원래 "if k_low ==
# 'X': 특별 처리; continue" 체인을 그대로 옮긴 것 — 함수가 None 을 반환하면 원본처럼 그 키를
# 버린다(2026-09-29 STD-08: C901=32 를 벗어나기 위해 if/elif 12개를 dict 조회로 바꿨다).
_RESULT_DATA_SPECIAL_HANDLERS: dict[str, Callable[[object], object | None]] = {
    "capabilities": _strip_capabilities,
    "apps": _strip_apps,
    "plan": _strip_plan,
    "target": _strip_target,
    "inspection_mode": _strip_inspection_mode,
    "browser": _strip_browser,
    "click_target": _strip_click_target,
    "clicked_target": _strip_click_target,  # click_target 과 동일 처리(원본과 동일)
    "url_info": _strip_url_info,
    "navigation": _strip_navigation,
    "cleanup": _strip_cleanup,
    "lifecycle": _strip_lifecycle,
}


# 문자열 값 기본 상한은 500자. 긴 결과가 정당한 키만 예외로 둔다.
_RESULT_DATA_LONG_KEYS: dict[str, int] = {"result_full": RESULT_FULL_MAX_CHARS}

# 값 수준 비밀 마스킹 — 키 이름 필터만으로는 본문 안에 섞인 키·토큰을 못 막는다
# (result_full 이 500→20000자로 늘면서 노출 가능 분량도 커졌다). 과마스킹을 피하려고
# 형식이 뚜렷한 것만 잡는다: sk-…, AIza…(Google API 키), Bearer <토큰>, 대문자 환경변수형 NAME_KEY=값.
_SECRET_MASK = "[REDACTED]"
_SECRET_VALUE_PATTERNS: tuple["re.Pattern[str]", ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
)
_SECRET_ASSIGN_PATTERN = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z0-9_]*)(\s*=\s*)"
    r"(?:\"[^\"\s]{8,}\"|'[^'\s]{8,}'|[^\s\"']{8,})"
)


def _mask_secret_values(text: str) -> str:
    """문자열 안의 비밀 값 모양을 `[REDACTED]` 로 바꾼다(이름·구분자는 남긴다)."""
    text = _SECRET_VALUE_PATTERNS[0].sub(_SECRET_MASK, text)
    text = _SECRET_VALUE_PATTERNS[1].sub(_SECRET_MASK, text)
    text = _SECRET_VALUE_PATTERNS[2].sub(lambda m: m.group(1) + _SECRET_MASK, text)
    return _SECRET_ASSIGN_PATTERN.sub(lambda m: m.group(1) + m.group(2) + _SECRET_MASK, text)


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
        handler = _RESULT_DATA_SPECIAL_HANDLERS.get(k_low)
        if handler is not None:
            stripped = handler(v)
            if stripped is not None:
                out[k] = stripped
            continue
        # url 계열 값 sanitize
        if k_low in ("normalized_url",) and isinstance(v, str):
            v = _sanitize_url_for_storage(v)
        # bool/int/None 은 그대로 저장, 나머지는 str로 제한
        if isinstance(v, (bool, int, float, type(None))):
            out[k] = v
        elif isinstance(v, str):
            # 자르기 전에 마스킹 — 비밀이 상한 경계에 걸쳐 일부만 남지 않게 한다.
            out[k] = _mask_secret_values(v)[: _RESULT_DATA_LONG_KEYS.get(k_low, 500)]
        else:
            out[k] = _mask_secret_values(str(v))[:500]
    return out or None
