"""LOCAL_BROWSER_DEFAULT 아키텍처 전환 검증 테스트

외부 웹 작업이 기본적으로 로컬 에이전트에서 처리되는지,
서버가 외부 사이트 브라우저 접속을 시도하지 않는지 검증한다.
"""

from __future__ import annotations

from ai_orchestrator.browser_tool.policy.domain_profile_registry import (
    get_domain_profile,
)
from ai_orchestrator.browser_tool.routing.execution_location_policy import (
    BLOCKED,
    LOCAL_BROWSER_DEFAULT,
    SERVER_ALLOWED,
    USER_DIRECT_ONLY,
    classify_execution_location,
)
from ai_orchestrator.browser_tool.routing.local_agent_handoff import (
    build_local_agent_handoff,
)
from ai_orchestrator.browser_tool.routing.unified_execution_router import (
    route_browser_task,
)
from ai_orchestrator.browser_tool.unified_browser_safe_result import (
    EXEC_LOCAL_AGENT,
    EXEC_SERVER_BROWSER,
    STATUS_LOCAL_HANDOFF_CREATED,
)


def _task(**kw):
    base = {
        "task_id": "arch1",
        "action": "open",
        "target_url": "https://www.g2b.go.kr/notice/list",
    }
    base.update(kw)
    return base


# ── 1. 기본값 검증 ─────────────────────────────────────────────────────────────


class TestLocalBrowserDefaultIsDefault:
    def test_g2b_is_local_browser_default(self):
        r = classify_execution_location(_task(site_category="government_procurement"))
        assert r["execution_location"] == LOCAL_BROWSER_DEFAULT

    def test_hometax_is_local_browser_default(self):
        r = classify_execution_location(
            _task(
                site_category="government_tax",
                target_url="https://www.hometax.go.kr",
            )
        )
        assert r["execution_location"] == LOCAL_BROWSER_DEFAULT

    def test_bank_is_local_browser_default(self):
        r = classify_execution_location(_task(site_category="financial_banking"))
        assert r["execution_location"] == LOCAL_BROWSER_DEFAULT

    def test_unknown_external_url_is_local_browser_default(self):
        r = classify_execution_location(
            {
                "task_id": "t1",
                "action": "open",
                "target_url": "https://www.some-external-site.com",
            }
        )
        assert r["execution_location"] == LOCAL_BROWSER_DEFAULT

    def test_no_category_external_url_is_local_browser_default(self):
        r = classify_execution_location(
            {
                "task_id": "t1",
                "action": "open",
                "target_url": "https://www.association.or.kr",
            }
        )
        assert r["execution_location"] == LOCAL_BROWSER_DEFAULT


# ── 2. SERVER_ALLOWED 범위 검증 ────────────────────────────────────────────────


class TestServerAllowedScope:
    def test_report_generate_server_allowed(self):
        r = classify_execution_location(_task(action="report_generate"))
        assert r["execution_location"] == SERVER_ALLOWED

    def test_public_readonly_server_allowed(self):
        r = classify_execution_location(_task(action="read", site_category="public_readonly"))
        assert r["execution_location"] == SERVER_ALLOWED

    def test_internal_api_server_allowed(self):
        r = classify_execution_location(_task(action="api_call", site_category="internal_api"))
        assert r["execution_location"] == SERVER_ALLOWED

    def test_public_data_server_allowed(self):
        r = classify_execution_location(_task(action="public_data_fetch"))
        assert r["execution_location"] == SERVER_ALLOWED


# ── 3. USER_DIRECT_ONLY 범위 검증 ─────────────────────────────────────────────


class TestUserDirectOnlyScope:
    def test_otp_input_user_direct(self):
        r = classify_execution_location(_task(action="otp_input"))
        assert r["execution_location"] == USER_DIRECT_ONLY

    def test_cert_password_input_user_direct(self):
        r = classify_execution_location(_task(action="cert_password_input"))
        assert r["execution_location"] == USER_DIRECT_ONLY

    def test_final_submit_user_direct(self):
        r = classify_execution_location(_task(action="final_submit"))
        assert r["execution_location"] == USER_DIRECT_ONLY

    def test_sign_document_user_direct(self):
        r = classify_execution_location(_task(action="sign_document"))
        assert r["execution_location"] == USER_DIRECT_ONLY

    def test_confirm_payment_user_direct(self):
        r = classify_execution_location(_task(action="confirm_payment"))
        assert r["execution_location"] == USER_DIRECT_ONLY


# ── 4. BLOCKED 범위 검증 ───────────────────────────────────────────────────────


class TestBlockedScope:
    def test_cookie_export_blocked(self):
        r = classify_execution_location(_task(action="cookie_export"))
        assert r["execution_location"] == BLOCKED

    def test_session_export_blocked(self):
        r = classify_execution_location(_task(action="session_export"))
        assert r["execution_location"] == BLOCKED

    def test_auto_sign_blocked(self):
        r = classify_execution_location(_task(action="auto_sign"))
        assert r["execution_location"] == BLOCKED

    def test_auto_payment_blocked(self):
        r = classify_execution_location(_task(action="auto_payment"))
        assert r["execution_location"] == BLOCKED

    def test_bid_submit_blocked(self):
        r = classify_execution_location(_task(action="bid_submit"))
        assert r["execution_location"] == BLOCKED

    def test_npki_access_blocked(self):
        r = classify_execution_location(_task(action="npki_access"))
        assert r["execution_location"] == BLOCKED

    def test_password_save_blocked(self):
        r = classify_execution_location(_task(action="password_save"))
        assert r["execution_location"] == BLOCKED


# ── 5. 라우터 - 서버 브라우저 외부 접속 금지 검증 ─────────────────────────────


class TestRouterNoServerBrowserForExternalSites:
    def test_g2b_open_does_not_use_server_browser(self):
        r = route_browser_task(_task())
        assert r["execution_used"] != EXEC_SERVER_BROWSER

    def test_g2b_login_does_not_use_server_browser(self):
        r = route_browser_task(_task(action="login"))
        assert r["execution_used"] != EXEC_SERVER_BROWSER

    def test_hometax_does_not_use_server_browser(self):
        r = route_browser_task(
            _task(
                action="open",
                target_url="https://www.hometax.go.kr/notice",
            )
        )
        assert r["execution_used"] != EXEC_SERVER_BROWSER

    def test_external_web_immediately_creates_handoff(self):
        r = route_browser_task(_task())
        assert r["execution_used"] == EXEC_LOCAL_AGENT
        assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED

    def test_no_server_result_needed_for_local(self):
        # server_result 없이도 LOCAL_BROWSER_DEFAULT는 즉시 handoff 생성
        r = route_browser_task(_task(), server_result=None)
        assert r["final_status"] == STATUS_LOCAL_HANDOFF_CREATED


# ── 6. domain profile LOCAL_BROWSER_DEFAULT 검증 ─────────────────────────────


class TestDomainProfileLocalBrowserDefault:
    def test_g2b_default_execution(self):
        p = get_domain_profile("g2b.go.kr")
        assert p["default_execution"] == "LOCAL_BROWSER_DEFAULT"

    def test_www_g2b_default_execution(self):
        p = get_domain_profile("www.g2b.go.kr")
        assert p["default_execution"] == "LOCAL_BROWSER_DEFAULT"

    def test_hometax_default_execution(self):
        p = get_domain_profile("hometax.go.kr")
        assert p["default_execution"] == "LOCAL_BROWSER_DEFAULT"

    def test_unknown_domain_default_execution(self):
        p = get_domain_profile("unknown-site.co.kr")
        assert p["default_execution"] == "LOCAL_BROWSER_DEFAULT"


# ── 7. handoff payload 검증 ───────────────────────────────────────────────────


class TestHandoffPayload:
    def test_local_browser_default_flag(self):
        h = build_local_agent_handoff(task=_task(), fallback_reason="LOCAL_BROWSER_DEFAULT")
        assert h.get("local_browser_default") is True

    def test_user_message_contains_pc(self):
        h = build_local_agent_handoff(task=_task())
        assert "사용자 PC" in h["user_message_ko"]

    def test_user_message_no_credential_storage(self):
        h = build_local_agent_handoff(task=_task())
        assert "저장하지 않습니다" in h["user_message_ko"]

    def test_readonly_always_true(self):
        h = build_local_agent_handoff(task=_task())
        assert h["readonly"] is True

    def test_router_handoff_message(self):
        r = route_browser_task(_task())
        assert "사용자 PC" in r["message_ko"]


# ── 8. 기존 SERVER_FIRST 잔존 여부 확인 ───────────────────────────────────────


class TestServerFirstLegacy:
    def test_server_first_is_alias_for_server_allowed(self):
        from ai_orchestrator.browser_tool.routing.execution_location_policy import SERVER_ALLOWED, SERVER_FIRST

        assert SERVER_FIRST == SERVER_ALLOWED

    def test_is_server_first_legacy_helper_works(self):
        from ai_orchestrator.browser_tool.routing.execution_location_policy import is_server_first

        # report_generate → SERVER_ALLOWED → is_server_first True (레거시 호환)
        assert is_server_first(_task(action="report_generate"))

    def test_g2b_not_server_first(self):
        from ai_orchestrator.browser_tool.routing.execution_location_policy import is_server_first

        assert not is_server_first(_task(action="open", site_category="government_procurement"))
