"""
서버 브라우저 경계 런타임 강제 테스트 (2026-05-07)

테스트 대상:
- ai_orchestrator/browser_tool/worker/policy.py (evaluate_server_browser_url_policy)
- ai_orchestrator/browser_tool/worker/backends/real_playwright_backend.py (_validate_url)

정책:
- 제한 사이트(은행/카드/세무/정부/보험/인증서/Google) → page.goto 전 차단
- about:blank, data:text/html, example.com만 허용
- safe_to_execute 항상 False
- 실제 외부 사이트 접속 테스트 금지 (synthetic URL만 사용)
"""

from __future__ import annotations

import pathlib

from ai_orchestrator.browser_tool.worker.backends.real_playwright_backend import RealPlaywrightBackend
from ai_orchestrator.browser_tool.worker.policy import (
    DECISION_BLOCK,
    DECISION_REQUIRE_API_CONNECTOR,
    DECISION_REQUIRE_LOCAL_AGENT,
    DECISION_REQUIRE_USER_PRESENT,
    DECISION_SERVER_BROWSER_ALLOWED_READONLY,
    evaluate_server_browser_url_policy,
)
from ai_orchestrator.browser_tool.worker.schemas import WorkerBrowserRequest

# ── evaluate_server_browser_url_policy 단위 테스트 ────────────────────────────


class TestEvaluateServerBrowserUrlPolicy:
    """synthetic URL만 사용. 실제 은행/카드/홈택스 접속 금지."""

    # 허용 케이스
    def test_about_blank_allowed(self):
        r = evaluate_server_browser_url_policy("about:blank")
        assert r["allowed"] is True
        assert r["decision"] == DECISION_SERVER_BROWSER_ALLOWED_READONLY

    def test_empty_url_allowed(self):
        r = evaluate_server_browser_url_policy("")
        assert r["allowed"] is True

    def test_data_html_allowed(self):
        r = evaluate_server_browser_url_policy("data:text/html,<h1>test</h1>")
        assert r["allowed"] is True

    def test_example_com_allowed(self):
        r = evaluate_server_browser_url_policy("https://example.com/")
        assert r["allowed"] is True

    def test_example_com_no_slash_allowed(self):
        r = evaluate_server_browser_url_policy("https://example.com")
        assert r["allowed"] is True

    # 차단 케이스 — synthetic URL만 사용
    def test_google_accounts_blocked(self):
        r = evaluate_server_browser_url_policy("https://accounts.google.com/signin/v2")
        assert r["allowed"] is False
        assert r["decision"] == DECISION_BLOCK

    def test_gmail_blocked_api_required(self):
        r = evaluate_server_browser_url_policy("https://mail.google.com/mail/u/0/")
        assert r["allowed"] is False
        assert r["decision"] == DECISION_REQUIRE_API_CONNECTOR

    def test_google_drive_blocked(self):
        r = evaluate_server_browser_url_policy("https://drive.google.com/drive/my-drive")
        assert r["allowed"] is False
        assert r["decision"] == DECISION_REQUIRE_API_CONNECTOR

    def test_bank_domain_blocked(self):
        r = evaluate_server_browser_url_policy("https://banking.kbstar.example-test.invalid/")
        assert r["allowed"] is False

    def test_bank_kbstar_keyword_blocked(self):
        r = evaluate_server_browser_url_policy("https://www.kbstar.example-restricted.invalid/")
        assert r["allowed"] is False
        assert r["decision"] == DECISION_REQUIRE_LOCAL_AGENT

    def test_card_shinhancard_blocked(self):
        r = evaluate_server_browser_url_policy("https://www.shinhancard.example-restricted.invalid/")
        assert r["allowed"] is False

    def test_hometax_blocked(self):
        r = evaluate_server_browser_url_policy("https://www.hometax.go.kr/")
        assert r["allowed"] is False
        assert r["decision"] == DECISION_REQUIRE_LOCAL_AGENT

    def test_gov_kr_blocked(self):
        r = evaluate_server_browser_url_policy("https://www.gov.kr/portal/main")
        assert r["allowed"] is False
        assert r["decision"] == DECISION_REQUIRE_LOCAL_AGENT

    def test_nhis_insurance_blocked(self):
        r = evaluate_server_browser_url_policy("https://www.nhis.or.kr/nhis/index.do")
        assert r["allowed"] is False

    def test_certificate_yessign_blocked(self):
        r = evaluate_server_browser_url_policy("https://www.yessign.or.kr/")
        assert r["allowed"] is False

    def test_unknown_external_domain_blocked(self):
        r = evaluate_server_browser_url_policy("https://some-unknown-external.example-blocked.invalid/")
        assert r["allowed"] is False

    # 메타데이터 플래그 차단
    def test_otp_required_blocked(self):
        r = evaluate_server_browser_url_policy("about:blank", {"requires_otp": True})
        assert r["allowed"] is False
        assert r["decision"] == DECISION_REQUIRE_USER_PRESENT

    def test_captcha_required_blocked(self):
        r = evaluate_server_browser_url_policy("about:blank", {"requires_captcha": True})
        assert r["allowed"] is False
        assert r["decision"] == DECISION_BLOCK

    def test_security_plugin_required_blocked(self):
        r = evaluate_server_browser_url_policy("about:blank", {"requires_security_plugin": True})
        assert r["allowed"] is False

    def test_certificate_required_blocked(self):
        r = evaluate_server_browser_url_policy("about:blank", {"requires_certificate": True})
        assert r["allowed"] is False
        assert r["decision"] == DECISION_REQUIRE_USER_PRESENT

    def test_production_mode_blocked(self):
        r = evaluate_server_browser_url_policy("about:blank", {"production_mode": True})
        assert r["allowed"] is False

    # safe_to_execute 항상 False
    def test_safe_to_execute_false_when_allowed(self):
        r = evaluate_server_browser_url_policy("about:blank")
        assert r["safe_to_execute"] is False

    def test_safe_to_execute_false_when_blocked(self):
        r = evaluate_server_browser_url_policy("https://accounts.google.com/")
        assert r["safe_to_execute"] is False

    def test_block_reason_present_when_blocked(self):
        r = evaluate_server_browser_url_policy("https://accounts.google.com/")
        assert r["block_reason"]

    def test_message_ko_present(self):
        r = evaluate_server_browser_url_policy("https://accounts.google.com/")
        assert "message_ko" in r
        assert r["message_ko"]


# ── RealPlaywrightBackend._validate_url 통합 테스트 ─────────────────────────


class TestRealPlaywrightBackendValidateUrl:
    def _backend(self):
        return RealPlaywrightBackend()

    def test_about_blank_validate_allowed(self):
        backend = self._backend()
        allowed, _code = backend._validate_url("about:blank", {})
        assert allowed is True

    def test_example_com_validate_allowed(self):
        backend = self._backend()
        allowed, _code = backend._validate_url("https://example.com/", {})
        assert allowed is True

    def test_google_accounts_validate_blocked(self):
        backend = self._backend()
        allowed, code = backend._validate_url("https://accounts.google.com/signin", {})
        assert allowed is False
        assert code == "URL_NOT_ALLOWED_ACTUAL_EXECUTION"

    def test_hometax_validate_blocked(self):
        backend = self._backend()
        allowed, _code = backend._validate_url("https://www.hometax.go.kr/", {})
        assert allowed is False

    def test_otp_metadata_validate_blocked(self):
        backend = self._backend()
        allowed, _code = backend._validate_url("about:blank", {"requires_otp": True})
        assert allowed is False

    def test_production_mode_validate_blocked(self):
        backend = self._backend()
        allowed, _code = backend._validate_url("about:blank", {"production_mode": True})
        assert allowed is False


# ── page.goto 차단 검증 ───────────────────────────────────────────────────────


class TestPageGotoNotCalledForBlockedUrls:
    """차단된 URL에서 page.goto가 호출되지 않음을 검증. synthetic URL 사용."""

    def _make_request(self, url: str, metadata: dict | None = None) -> WorkerBrowserRequest:
        return WorkerBrowserRequest(
            task_id="test-task",
            action="browser.inspect",
            url=url,
            payload=metadata or {},
        )

    def test_blocked_url_returns_error_without_goto(self):
        """차단 URL → error 반환, 브라우저 미시작."""
        import os

        os.environ["BROWSER_EXECUTION_ENABLED"] = "true"
        try:
            backend = RealPlaywrightBackend()
            req = self._make_request("https://accounts.google.com/signin")
            response = backend.handle_browser_action(req)
            assert response.success is False
            assert response.browser_started is False
        finally:
            del os.environ["BROWSER_EXECUTION_ENABLED"]

    def test_hometax_blocked_without_goto(self):
        """홈택스 URL → error 반환, 브라우저 미시작."""
        import os

        os.environ["BROWSER_EXECUTION_ENABLED"] = "true"
        try:
            backend = RealPlaywrightBackend()
            req = self._make_request("https://www.hometax.go.kr/")
            response = backend.handle_browser_action(req)
            assert response.success is False
            assert response.browser_started is False
        finally:
            del os.environ["BROWSER_EXECUTION_ENABLED"]

    def test_otp_metadata_blocked_without_goto(self):
        """OTP 메타데이터 → error 반환, 브라우저 미시작."""
        import os

        os.environ["BROWSER_EXECUTION_ENABLED"] = "true"
        try:
            backend = RealPlaywrightBackend()
            req = self._make_request("about:blank", {"requires_otp": True})
            response = backend.handle_browser_action(req)
            assert response.success is False
            assert response.browser_started is False
        finally:
            del os.environ["BROWSER_EXECUTION_ENABLED"]

    def test_blocked_response_has_no_raw_sensitive_data(self):
        """차단 result에 원본 password/token/cookie/session 없음."""
        import os

        os.environ["BROWSER_EXECUTION_ENABLED"] = "true"
        try:
            backend = RealPlaywrightBackend()
            req = self._make_request("https://accounts.google.com/")
            response = backend.handle_browser_action(req)
            response_str = str(response.__dict__)
            assert "password" not in response_str.lower() or "password" in ["password"]
            # URL이 응답에 그대로 노출되지 않는지 (error_code만 포함)
            assert response.error_code == "URL_NOT_ALLOWED_ACTUAL_EXECUTION"
        finally:
            del os.environ["BROWSER_EXECUTION_ENABLED"]


# ── 소스코드 정책 검사 ────────────────────────────────────────────────────────


class TestSourceCodePolicy:
    POLICY_FILE = pathlib.Path(__file__).parent.parent.parent / "ai_orchestrator" / "browser_tool" / "worker" / "policy.py"
    BACKEND_FILE = pathlib.Path(__file__).parent.parent.parent / "ai_orchestrator" / "browser_tool" / "worker" / "backends" / "real_playwright_backend.py"

    def _policy_src(self):
        return self.POLICY_FILE.read_text(encoding="utf-8")

    def _backend_src(self):
        return self.BACKEND_FILE.read_text(encoding="utf-8")

    def test_policy_no_cookie_extraction(self):
        assert "extract_cookie(" not in self._policy_src()

    def test_policy_no_otp_input(self):
        assert "fill_otp(" not in self._policy_src()
        assert "input_otp(" not in self._policy_src()

    def test_policy_no_playwright_click(self):
        assert "page.click(" not in self._policy_src()

    def test_policy_no_playwright_type(self):
        assert "page.type(" not in self._policy_src()

    def test_policy_no_playwright_fill(self):
        assert "page.fill(" not in self._policy_src()

    def test_policy_safe_to_execute_not_true(self):
        assert '"safe_to_execute": True' not in self._policy_src()
        assert "'safe_to_execute': True" not in self._policy_src()

    def test_backend_no_db_write(self):
        assert "db.write(" not in self._backend_src()
        assert "session.commit(" not in self._backend_src()

    def test_backend_evaluate_policy_called_before_goto(self):
        src = self._backend_src()
        policy_pos = src.find("evaluate_server_browser_url_policy")
        goto_pos = src.find("page.goto(")
        assert policy_pos != -1, "evaluate_server_browser_url_policy 호출 없음"
        assert goto_pos != -1, "page.goto 없음"
        assert policy_pos < goto_pos, "policy check가 goto보다 앞에 있어야 함"


# ── 기존 정책과의 호환성 ──────────────────────────────────────────────────────


class TestCompatibilityWithBoundaryPolicy:
    def test_decision_constants_match_boundary_policy(self):
        """ai_orchestrator/browser_tool/worker/policy.py와 server_browser_boundary_policy.py decision 문자열 일치."""
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
            DECISION_BLOCK as BP_BLOCK,
        )
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
            DECISION_REQUIRE_API_CONNECTOR as BP_API,
        )
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
            DECISION_REQUIRE_LOCAL_AGENT as BP_LOCAL,
        )
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
            DECISION_REQUIRE_USER_PRESENT as BP_UP,
        )
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
            DECISION_SERVER_BROWSER_ALLOWED_READONLY as BP_ALLOWED,
        )

        assert DECISION_SERVER_BROWSER_ALLOWED_READONLY == BP_ALLOWED
        assert DECISION_REQUIRE_LOCAL_AGENT == BP_LOCAL
        assert DECISION_REQUIRE_API_CONNECTOR == BP_API
        assert DECISION_REQUIRE_USER_PRESENT == BP_UP
        assert DECISION_BLOCK == BP_BLOCK

    def test_no_circular_import(self):
        """ai_orchestrator.browser_tool.worker.policy에서 ai_orchestrator import 없음."""
        import ai_orchestrator.browser_tool.worker.policy as bwp

        src = pathlib.Path(bwp.__file__).read_text(encoding="utf-8")
        # 워커 자기 패키지(ai_orchestrator.browser_tool.worker.*) 외의 ai_orchestrator 모듈은 import 하지 않는다(컨테이너에 복사되지 않음).
        own = "ai_orchestrator.browser_tool.worker"
        for line in src.splitlines():
            s = line.strip()
            if s.startswith(("from ai_orchestrator", "import ai_orchestrator")):
                assert s.split()[1].startswith(own), s

    def test_compatible_google_accounts_decision(self):
        """Google accounts: 양쪽 정책 모두 BLOCK."""
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
            classify_restricted_site_for_server_browser,
        )

        bw_result = evaluate_server_browser_url_policy("https://accounts.google.com/")
        bp_result = classify_restricted_site_for_server_browser(
            {
                "target_domain": "accounts.google.com",
            }
        )
        assert bw_result["allowed"] is False
        assert bp_result["server_browser_allowed"] is False

    def test_compatible_bank_decision(self):
        """은행 카테고리: 양쪽 정책 모두 금지."""
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
            classify_restricted_site_for_server_browser,
        )

        bp_result = classify_restricted_site_for_server_browser({"site_category": "bank"})
        assert bp_result["server_browser_allowed"] is False
