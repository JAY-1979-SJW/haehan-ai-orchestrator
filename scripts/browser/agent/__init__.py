"""브라우저 자동화 패키지 — CDP 기반 사용자 Chrome 제어.

공개 API
========
from scripts.browser.agent import (
    # CDP 연결
    open_cdp_session, is_cdp_available, CDPSession, CDPConnectionError,

    # 액션 실행
    navigate, click, type_text, select_option, upload_file,
    screenshot, scroll, get_text, fill_form,
    GateApprovalRequired,

    # 승인 게이트
    classify_action, GATE_AUTO, GATE_NOTIFY, GATE_APPROVE,

    # 의도 토큰
    create_intent, validate_intent, IntentToken,
    SCOPE_READ_ONLY, SCOPE_INTERACTION,

    # 감사 로그
    log_action, read_log, summarize_log, mask_sensitive_data,

    # 보안 로그인
    ensure_logged_in, try_easy_auth, handle_cert_login,
    handle_two_factor, input_credential, detect_login_state,
    EASY_AUTH_KAKAO, EASY_AUTH_PASS, EASY_AUTH_NAVER,
    LOGIN_OK, LOGIN_REQUIRED, LOGIN_TWO_FACTOR, LOGIN_CERT,

    # 세션
    open_user_session,
)
"""

from scripts.browser.agent.action_gate import (
    GATE_APPROVE,
    GATE_AUTO,
    GATE_NOTIFY,
    GateResult,
    classify_action,
    is_auto,
    requires_approval,
    should_notify,
)
from scripts.browser.agent.actions import (
    ActionResult,
    GateApprovalRequired,
    accept_dialog,
    click,
    fill_form,
    get_attribute,
    get_text,
    navigate,
    screenshot,
    scroll,
    select_option,
    type_text,
    upload_file,
    wait_for_selector,
    wait_ms,
)
from scripts.browser.agent.audit_log import (
    get_audit_path,
    log_action,
    mask_sensitive_data,
    read_log,
    summarize_log,
)
from scripts.browser.agent.browser_session import open_user_session
from scripts.browser.agent.cdp import (
    DEFAULT_CDP_HOST,
    DEFAULT_CDP_PORT,
    CDPConnectionError,
    CDPSession,
    cdp_endpoint,
    get_chrome_start_command,
    is_cdp_available,
    open_cdp_session,
)
from scripts.browser.agent.intent_token import (
    INTENT_EXCEEDED,
    INTENT_EXPIRED,
    INTENT_INVALID,
    INTENT_OK,
    SCOPE_INTERACTION,
    SCOPE_READ_ONLY,
    IntentToken,
    add_origin,
    create_intent,
    expire_intent,
    increment_action,
    is_origin_allowed,
    list_active_intents,
    load_intent,
    save_intent,
    validate_intent,
)

__all__ = [
    # cdp
    "open_cdp_session",
    "is_cdp_available",
    "get_chrome_start_command",
    "cdp_endpoint",
    "CDPSession",
    "CDPConnectionError",
    "DEFAULT_CDP_PORT",
    "DEFAULT_CDP_HOST",
    # audit_log
    "log_action",
    "read_log",
    "summarize_log",
    "mask_sensitive_data",
    "get_audit_path",
    # intent_token
    "create_intent",
    "validate_intent",
    "is_origin_allowed",
    "increment_action",
    "add_origin",
    "save_intent",
    "load_intent",
    "expire_intent",
    "list_active_intents",
    "IntentToken",
    "SCOPE_READ_ONLY",
    "SCOPE_INTERACTION",
    "INTENT_OK",
    "INTENT_EXPIRED",
    "INTENT_EXCEEDED",
    "INTENT_INVALID",
    # action_gate
    "classify_action",
    "GateResult",
    "GATE_AUTO",
    "GATE_NOTIFY",
    "GATE_APPROVE",
    "is_auto",
    "requires_approval",
    "should_notify",
    # actions
    "navigate",
    "click",
    "type_text",
    "select_option",
    "upload_file",
    "screenshot",
    "scroll",
    "get_text",
    "get_attribute",
    "wait_for_selector",
    "accept_dialog",
    "fill_form",
    "wait_ms",
    "GateApprovalRequired",
    "ActionResult",
    # session
    "open_user_session",
]
