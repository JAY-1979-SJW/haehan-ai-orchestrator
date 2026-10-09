"""Stage 12H — controlled browser open/observe fixture 테스트.

Stage 12G에서 정의한 정책을 코드로 고정한다. 실제 Playwright/Chrome/local-agent
프로세스 / HTTP 요청은 일절 발생시키지 않으며, fake page object 와
monkeypatch 만 사용한다.

검증 대상:
  1. about:blank — 현재 정책상 http(s) 외 차단 (보수적 안전 — 12I/12J에서 별도 정책 검토 후 허용 예정)
  2. 외부 사이트 URL validation 허용 vs 첫 단계 정책 차단 분리
  3. file:// / javascript: / data: URL → URL_SCHEME_BLOCKED
  4. localhost / private IP → URL_HOST_BLOCKED (allow_private_network=False)
  5. fake page 가 cookie / storage / evaluate 호출 시 예외
  6. password / hidden input value 가 결과에 포함되지 않음
  7. login_required_hint 가 password input 감지 시 True
  8. open_url_readonly 결과에 cookie / Authorization / session 키 부재
  9. 실제 subprocess / Playwright 실 호출 0건 (BROWSER_DEPENDENCY_MISSING 또는 fake factory 만 사용)

실행:
  pytest tests/test_browser_open_observe_fixture.py -v
"""

from __future__ import annotations

from datetime import UTC
from unittest.mock import patch

import pytest

from core.agent_runtime.browser import browser_reader as _br
from core.agent_runtime.browser import web_reader as _wr
from core.agent_runtime.common import audit as _audit_mod
from core.agent_runtime.connection import actions as _actions

# ── Audit capture (모든 테스트에 자동 적용) ─────────────────────────────────


@pytest.fixture(autouse=True)
def captured_audit(monkeypatch):
    """audit.log_local_event 를 in-memory list 로 캡처하여 디스크 IO 미발생."""
    events: list[dict] = []

    def _capture(event_type, **fields):
        from datetime import datetime

        events.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event_type": event_type,
                **fields,
            }
        )

    # browser_reader 가 import 한 audit 모듈 객체에도 패치
    monkeypatch.setattr(_audit_mod, "log_local_event", _capture)
    monkeypatch.setattr(_br._audit, "log_local_event", _capture)
    yield events


# ── Fake Playwright page / browser / context ─────────────────────────────────


class _RaiseOnAccess:
    """접근 시 무조건 예외. cookie/storage/evaluate 차단 검증용."""

    def __init__(self, name: str):
        self.name = name

    def __call__(self, *a, **kw):
        raise AssertionError(f"FORBIDDEN ACCESS: {self.name}")

    def __getattr__(self, item):
        raise AssertionError(f"FORBIDDEN ACCESS: {self.name}.{item}")


class FakePage:
    """read-only 관찰만 허용. cookie/storage/evaluate 접근 시 즉시 실패."""

    def __init__(self, *, title: str, url: str, html: str):
        self._title = title
        self.url = url
        self._html = html
        # 금지 속성: 접근 자체로 테스트 실패
        self.cookies = _RaiseOnAccess("page.cookies")
        self.evaluate = _RaiseOnAccess("page.evaluate")
        self.click = _RaiseOnAccess("page.click")
        self.fill = _RaiseOnAccess("page.fill")
        self.press = _RaiseOnAccess("page.press")

    def goto(self, url, **kw):
        return None

    def title(self):
        return self._title

    def content(self):
        return self._html

    def close(self):
        return None


class FakeContext:
    def __init__(self, page: FakePage):
        self._page = page
        # context-level 금지 속성
        self.cookies = _RaiseOnAccess("context.cookies")
        self.add_cookies = _RaiseOnAccess("context.add_cookies")
        self.storage_state = _RaiseOnAccess("context.storage_state")

    def new_page(self):
        return self._page

    def close(self):
        return None


class FakeBrowser:
    def __init__(self, page: FakePage):
        self._page = page

    def new_context(self):
        return FakeContext(self._page)

    def close(self):
        return None


class FakeChromium:
    def __init__(self, page: FakePage):
        self._page = page

    def launch(self, **kw):
        return FakeBrowser(self._page)


class FakePlaywrightCM:
    """sync_playwright().__enter__()/__exit__() 컨텍스트 매니저."""

    def __init__(self, page: FakePage):
        self.chromium = FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def make_factory(page: FakePage):
    """browser_reader 가 받는 _playwright_factory: () → context-manager."""
    return lambda: FakePlaywrightCM(page)


# ── 1. about:blank 현재 정책 ─────────────────────────────────────────────────


class TestAboutBlankPolicy:
    def test_about_blank_blocked_without_optin(self):
        """기본(opt-in 미사용) 시 about:blank 는 여전히 보수 차단."""
        result = _wr.validate_url_for_readonly_open("about:blank")
        assert result["ok"] is False
        assert result["error_code"] == "URL_SCHEME_BLOCKED"

    def test_about_blank_allowed_with_explicit_optin(self):
        """allow_about_blank=True 명시 시 정확히 'about:blank' 만 통과."""
        result = _wr.validate_url_for_readonly_open(
            "about:blank",
            allow_about_blank=True,
        )
        assert result["ok"] is True
        assert result.get("about_blank") is True
        assert result["scheme"] == "about"

    def test_about_blank_case_insensitive_with_optin(self):
        """대소문자 무시 + 양쪽 공백 허용은 strip 후 정확 일치."""
        for v in ("About:Blank", "ABOUT:BLANK", "  about:blank  "):
            result = _wr.validate_url_for_readonly_open(
                v,
                allow_about_blank=True,
            )
            assert result["ok"] is True, f"failed for: {v!r}"

    @pytest.mark.parametrize(
        "variant",
        [
            "about:srcdoc",
            "about:config",
            "about:newtab",
            "about:blank?x=1",
            "about:blank#frag",
            "about:blank/extra",
            "about:blanket",
            "about: blank",
        ],
    )
    def test_other_about_variants_blocked_even_with_optin(self, variant):
        """about:blank 외 다른 about:* 는 opt-in 이어도 모두 차단."""
        result = _wr.validate_url_for_readonly_open(
            variant,
            allow_about_blank=True,
        )
        assert result["ok"] is False
        assert result["error_code"] == "URL_SCHEME_BLOCKED"

    def test_about_blank_open_url_readonly_blocked_without_optin(self):
        result = _br.open_url_readonly(
            "about:blank",
            _playwright_factory=make_factory(FakePage(title="x", url="x", html="")),
        )
        assert result["ok"] is False
        assert result["error_code"] == "URL_SCHEME_BLOCKED"

    def test_about_blank_open_url_readonly_allowed_with_optin(self):
        """opt-in + fake factory 로 read-only observe 경로 동작 확인 (실제 브라우저 미기동)."""
        fake = FakePage(title="", url="about:blank", html="<html><head></head><body></body></html>")
        result = _br.open_url_readonly(
            "about:blank",
            allow_about_blank=True,
            _playwright_factory=make_factory(fake),
        )
        assert result["ok"] is True
        assert result["title"] == ""
        assert result["current_url"] == "about:blank"


# ── 2. 외부 사이트 URL validation 허용 vs 정책 분리 ─────────────────────────


class TestExternalUrl:
    def test_external_https_passes_url_validation(self):
        """validate_url_for_readonly_open 자체는 공개 http(s) 호스트 허용.
        12G 정책상 '외부 사이트 금지'는 호출자/정책 게이트 책임 영역."""
        result = _wr.validate_url_for_readonly_open("https://example.com/")
        assert result["ok"] is True
        assert result["scheme"] == "https"
        assert result["host"] == "example.com"

    def test_external_http_passes_url_validation(self):
        result = _wr.validate_url_for_readonly_open("http://example.com/page")
        assert result["ok"] is True


# ── 3. file:// / javascript: / data: 차단 ───────────────────────────────────


class TestDangerousSchemes:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "file://C:/Windows/System32/config",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://server/file",
            "ssh://host",
        ],
    )
    def test_dangerous_schemes_blocked(self, url):
        result = _wr.validate_url_for_readonly_open(url)
        assert result["ok"] is False
        assert result["error_code"] in ("URL_SCHEME_BLOCKED", "URL_NO_HOST")

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,<p>x</p>",
        ],
    )
    def test_action_open_url_blocks_dangerous_schemes(self, url):
        with patch("webbrowser.open") as mock_open:
            r = _actions.action_open_url({"url": url})
        assert r.success is False
        assert r.error_code in ("URL_SCHEME_NOT_ALLOWED", "INVALID_URL")
        mock_open.assert_not_called()


# ── 4. localhost / private IP 차단 ───────────────────────────────────────────


class TestPrivateNetworkBlock:
    @pytest.mark.parametrize(
        "host",
        [
            "http://localhost/",
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://169.254.1.1/",
        ],
    )
    def test_private_hosts_blocked_by_default(self, host):
        result = _wr.validate_url_for_readonly_open(host)
        assert result["ok"] is False
        assert result["error_code"] == "URL_HOST_BLOCKED"

    def test_localhost_allowed_only_with_explicit_flag(self):
        result = _wr.validate_url_for_readonly_open("http://localhost/", allow_private_network=True)
        assert result["ok"] is True


# ── 5. 빈 URL 차단 ───────────────────────────────────────────────────────────


class TestEmptyUrl:
    def test_empty_url_blocked(self):
        result = _wr.validate_url_for_readonly_open("")
        assert result["ok"] is False
        assert result["error_code"] == "URL_EMPTY"

    def test_action_web_open_url_readonly_missing_url(self):
        r = _actions.action_web_open_url_readonly({})
        assert r.success is False
        assert r.error_code == "MISSING_URL"


# ── 6. fake page 로 read-only 관찰만 수행 ────────────────────────────────────


class TestReadOnlyObservation:
    def test_open_url_readonly_returns_only_safe_fields(self):
        fake = FakePage(
            title="Example Domain",
            url="https://example.com/final",
            html="<html><head><title>Example Domain</title></head><body><h1>Hi</h1></body></html>",
        )

        result = _br.open_url_readonly(
            "https://example.com/",
            _playwright_factory=make_factory(fake),
        )

        assert result["ok"] is True
        assert result["title"] == "Example Domain"
        assert result["current_url"] == "https://example.com/final"
        # 결과 dict 에 민감 키 부재
        for forbidden in (
            "cookie",
            "cookies",
            "Authorization",
            "authorization",
            "session",
            "localStorage",
            "sessionStorage",
            "password",
        ):
            assert forbidden not in result, f"forbidden key in result: {forbidden}"

    def test_observe_does_not_invoke_forbidden_apis(self):
        """fake page 의 cookie/evaluate/click 접근 시 _RaiseOnAccess 가 던짐.
        open_url_readonly 호출 중 어떤 forbidden API 도 호출되지 않아야 함."""
        fake = FakePage(
            title="t",
            url="https://example.com/",
            html="<html><body/></html>",
        )

        # 정상 종료 → forbidden API 호출 없음을 의미
        result = _br.open_url_readonly(
            "https://example.com/",
            _playwright_factory=make_factory(fake),
        )
        assert result["ok"] is True


# ── 7. password / hidden input value 미수집 ─────────────────────────────────


class TestSensitiveInputDrop:
    def test_password_value_not_in_page_structure(self):
        html = (
            "<html><body><form>"
            '<input type="text" name="user" value="alice">'
            '<input type="password" name="pw" value="SECRET-PASSWORD-123">'
            '<input type="hidden" name="csrf" value="HIDDEN-TOKEN-XYZ">'
            "</form></body></html>"
        )
        result = _wr.analyze_html_structure(html=html)

        # 결과 직렬화 어디에도 비밀값이 없어야 함
        import json

        blob = json.dumps(result, default=str)
        assert "SECRET-PASSWORD-123" not in blob
        assert "HIDDEN-TOKEN-XYZ" not in blob

    def test_login_hint_detected_when_password_input(self):
        fake = FakePage(
            title="Login",
            url="https://x.com/login",
            html='<html><body><form><input type="password" name="pw"><button>로그인</button></form></body></html>',
        )
        result = _br.open_url_readonly(
            "https://x.com/login",
            _playwright_factory=make_factory(fake),
        )
        assert result["ok"] is True
        assert result["login_required_hint"] is True
        assert "password_input_detected" in result["login_reason"]


# ── 8. forbidden keys 부재 ──────────────────────────────────────────────────


class TestNoSensitiveKeysInResult:
    def test_no_cookie_authorization_session_in_result_serialization(self):
        fake = FakePage(
            title="t",
            url="https://example.com/",
            html="<html><body>"
            '<meta name="authorization" content="Bearer xxx">'
            '<form><input type="hidden" name="csrf_token" value="abc"></form>'
            "</body></html>",
        )
        result = _br.open_url_readonly(
            "https://example.com/",
            _playwright_factory=make_factory(fake),
        )
        import json

        blob = json.dumps(result, default=str).lower()
        # 키 자체 부재 확인 (대소문자 무시)
        for k in ('"cookie"', '"set-cookie"', '"authorization"', '"session"', '"localstorage"', '"sessionstorage"'):
            assert k not in blob, f"sensitive key leaked: {k}"


# ── 9. 실제 Playwright/subprocess 미실행 검증 ───────────────────────────────


class TestNoActualLaunch:
    def test_no_subprocess_invoked_during_url_validation(self):
        blocked: list = []
        with patch("subprocess.run", side_effect=lambda *a, **k: blocked.append(("run", a))):
            with patch("subprocess.Popen", side_effect=lambda *a, **k: blocked.append(("Popen", a))):
                with patch("os.system", side_effect=lambda *a, **k: blocked.append(("system", a))):
                    _wr.validate_url_for_readonly_open("https://example.com/")
                    _wr.validate_url_for_readonly_open("file:///x")
                    _wr.validate_url_for_readonly_open("about:blank")
        assert blocked == []

    def test_no_subprocess_invoked_during_fake_open(self):
        fake = FakePage(title="t", url="https://x/", html="<html/>")
        blocked: list = []
        with patch("subprocess.run", side_effect=lambda *a, **k: blocked.append(("run", a))):
            with patch("subprocess.Popen", side_effect=lambda *a, **k: blocked.append(("Popen", a))):
                with patch("os.system", side_effect=lambda *a, **k: blocked.append(("system", a))):
                    _br.open_url_readonly(
                        "https://x/",
                        _playwright_factory=make_factory(fake),
                    )
        assert blocked == []

    def test_no_real_playwright_import_when_factory_provided(self):
        """_playwright_factory 가 주입되면 실제 playwright 모듈 import 없이 동작."""
        fake = FakePage(title="t", url="https://x/", html="<html/>")
        # 이 테스트가 실제 playwright 가 미설치된 환경에서도 통과해야 함
        result = _br.open_url_readonly(
            "https://x/",
            _playwright_factory=make_factory(fake),
        )
        assert result["ok"] is True

    def test_real_playwright_dependency_missing_returns_error_code(self):
        """factory 미주입 + playwright 미설치 → BROWSER_DEPENDENCY_MISSING.
        실제 브라우저 기동을 시도하지 않고 에러로 종료함을 확인."""
        # playwright 가 설치되어 있을 수도 있으므로 해당 경우는 skip
        try:
            import playwright  # noqa: F401

            pytest.skip("playwright installed; this assertion targets the missing case")
        except ImportError:
            pass

        result = _br.open_url_readonly("https://example.com/")
        assert result["ok"] is False
        assert result["error_code"] == "BROWSER_DEPENDENCY_MISSING"


# ── 10. POST/mutation 행위가 원천 부재인지 표면 검증 ────────────────────────


class TestNoMutationApiInPath:
    """browser_reader 모듈 자체에서 click/fill/press/post 등 mutation API 호출이
    텍스트 레벨로도 부재함을 확인 (정책 회귀 방어)."""

    def test_browser_reader_source_has_no_mutation_calls(self):
        import inspect

        src = inspect.getsource(_br)
        # 호출 흔적이 있으면 안 됨 (점(.) 또는 파라미터로 사용되는 mutation API)
        for forbidden in (
            ".click(",
            ".fill(",
            ".press(",
            ".set_cookie(",
            ".add_cookies(",
            ".evaluate(",
            ".storage_state(",
            ".accept_downloads",
        ):
            assert forbidden not in src, f"mutation API found in browser_reader: {forbidden}"


# ── 11. browser_open_* audit event wiring (Stage 12J) ───────────────────────


class TestAuditWiring:
    def _types(self, events: list[dict]) -> list[str]:
        return [e["event_type"] for e in events]

    def test_about_blank_success_emits_full_sequence(self, captured_audit):
        fake = FakePage(title="", url="about:blank", html="<html><body/></html>")
        result = _br.open_url_readonly(
            "about:blank",
            allow_about_blank=True,
            _playwright_factory=make_factory(fake),
        )
        assert result["ok"] is True

        types = self._types(captured_audit)
        # 정상 경로 5종이 순서대로 기록
        for ev in (
            "browser_open_requested",
            "browser_open_dry_run_checked",
            "browser_open_started",
            "browser_open_observed",
            "browser_open_completed",
        ):
            assert ev in types, f"missing event: {ev} (got {types})"
        # 실패/차단 이벤트는 발생하지 않음
        assert "browser_open_blocked" not in types
        assert "browser_open_failed" not in types

    def test_url_scheme_blocked_emits_blocked(self, captured_audit):
        result = _br.open_url_readonly("javascript:alert(1)")
        assert result["ok"] is False

        types = self._types(captured_audit)
        assert "browser_open_requested" in types
        assert "browser_open_dry_run_checked" in types
        assert "browser_open_blocked" in types
        # 실 브라우저 기동 단계까지 가지 않음
        assert "browser_open_started" not in types
        assert "browser_open_observed" not in types
        assert "browser_open_completed" not in types

    def test_about_blank_without_optin_emits_blocked(self, captured_audit):
        result = _br.open_url_readonly("about:blank")
        assert result["ok"] is False

        types = self._types(captured_audit)
        assert "browser_open_blocked" in types
        # url_category 가 about_blank 이지만, opt-in 없이 차단됨을 audit 에서 확인
        blocked_events = [e for e in captured_audit if e["event_type"] == "browser_open_blocked"]
        assert blocked_events
        assert blocked_events[0]["url_category"] == "about_blank"
        assert blocked_events[0]["allow_about_blank"] is False

    def test_factory_exception_emits_failed(self, captured_audit):
        class BoomCM:
            def __enter__(self):
                raise RuntimeError("factory boom")

            def __exit__(self, *a):
                return False

        result = _br.open_url_readonly(
            "about:blank",
            allow_about_blank=True,
            _playwright_factory=lambda: BoomCM(),
        )
        assert result["ok"] is False
        assert result["error_code"] == "BROWSER_OPEN_FAILED"

        types = self._types(captured_audit)
        assert "browser_open_started" in types
        assert "browser_open_failed" in types
        assert "browser_open_completed" not in types

    def test_external_url_audit_does_not_log_full_url(self, captured_audit):
        """외부 URL 호출 시 url 원문이 audit payload 에 포함되면 안 됨."""
        fake = FakePage(title="t", url="https://example.com/secret-path?key=abc", html="<html/>")
        _br.open_url_readonly(
            "https://example.com/secret-path?key=abc",
            _playwright_factory=make_factory(fake),
        )
        for e in captured_audit:
            # url_category 는 허용. 단, 풀 URL/host/path/query 는 미기록
            assert "secret-path" not in str(e)
            assert "example.com" not in str(e)
            assert "key=abc" not in str(e)
            # url 키가 있다면 정확히 about:blank 만 허용
            if "url" in e:
                assert e["url"] == "about:blank"

    def test_audit_payload_strips_sensitive_keys(self, captured_audit):
        """browser_reader 가 audit 에 cookie/session/token/password/Authorization 류 키를
        직접 추가하지 않음. (audit 모듈의 _strip_sensitive 와 별도로 송출 자체에서 부재)"""
        fake = FakePage(title="", url="about:blank", html="<html/>")
        _br.open_url_readonly(
            "about:blank",
            allow_about_blank=True,
            _playwright_factory=make_factory(fake),
        )
        forbidden_keys = {
            "cookie",
            "cookies",
            "session",
            "session_token",
            "token",
            "access_token",
            "refresh_token",
            "password",
            "passwd",
            "pwd",
            "authorization",
            "auth",
            "localstorage",
            "sessionstorage",
            "html",
            "page_content",
            "content",
        }
        for e in captured_audit:
            for k in e:
                assert k.lower() not in forbidden_keys, f"forbidden key {k!r} in audit event {e['event_type']}"

    def test_url_categorize_helper(self):
        assert _br._categorize_url("about:blank") == "about_blank"
        assert _br._categorize_url("about:srcdoc") == "about_other"
        assert _br._categorize_url("about:config") == "about_other"
        assert _br._categorize_url("https://example.com/x") == "public_https"
        assert _br._categorize_url("http://x/") == "public_http"
        assert _br._categorize_url("file:///etc/passwd") == "blocked_scheme:file"
        assert _br._categorize_url("javascript:1") == "blocked_scheme:javascript"
        assert _br._categorize_url("") == "empty"
        assert _br._categorize_url(None) == "invalid"
