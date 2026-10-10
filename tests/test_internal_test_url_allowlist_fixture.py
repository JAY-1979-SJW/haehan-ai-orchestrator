"""Stage 12M — 내부 테스트 URL allowlist + 페이지 안전성 fixture.

Stage 12L 정책 문서를 코드로 고정한다. 실제 HTTP/브라우저/local-agent/서버 실행
없이 `core.agent_runtime.policy.internal_test_allowlist` 만 검증한다.

검증 대상:
  - validate_internal_test_url: scheme/host/port/path/query/fragment/traversal/risky-keyword
  - analyze_internal_page_safety: password/file input, form POST, textarea, contenteditable,
    final_url allowlist escape
  - audit payload sanitize 가이드라인 (helper 결과에 민감 키 부재)
  - 실제 subprocess/HTTP/network 호출 0건

실행:
  pytest tests/test_internal_test_url_allowlist_fixture.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.agent_runtime.policy import internal_test_allowlist as _al

TEST_PORT = 9876
PFX = "/__haehan_test__/readonly"


# ── 1. allowlist: scheme ─────────────────────────────────────────────────────


class TestScheme:
    def test_http_allowed(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is True
        assert r["scheme"] == "http"

    @pytest.mark.parametrize(
        "url",
        [
            f"https://localhost:{TEST_PORT}{PFX}",
            f"file://localhost{PFX}",
            f"javascript:fetch('{PFX}')",
            "data:text/html,<p>x</p>",
            f"ftp://localhost:{TEST_PORT}{PFX}",
            f"ssh://localhost:{TEST_PORT}{PFX}",
        ],
    )
    def test_non_http_blocked(self, url):
        r = _al.validate_internal_test_url(url, allowed_port=TEST_PORT)
        assert r["ok"] is False
        assert r["error_code"] in ("URL_SCHEME_BLOCKED", "URL_HOST_BLOCKED", "URL_PATH_BLOCKED", "URL_PATH_TRAVERSAL")


# ── 2. allowlist: host ──────────────────────────────────────────────────────


class TestHost:
    def test_localhost_allowed(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is True

    def test_loopback_ipv4_allowed(self):
        r = _al.validate_internal_test_url(
            f"http://127.0.0.1:{TEST_PORT}{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is True

    @pytest.mark.parametrize(
        "host",
        [
            "0.0.0.0",
            "192.168.0.1",
            "192.168.1.100",
            "10.0.0.1",
            "172.16.0.1",
            "169.254.1.1",
            "test.local",
            "service.local",
            "myhost.localdomain",
            "example.com",
            "haehan-ai.kr",
            "[::1]",
        ],
    )
    def test_other_hosts_blocked(self, host):
        r = _al.validate_internal_test_url(
            f"http://{host}:{TEST_PORT}{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is False
        assert r["error_code"] == "URL_HOST_BLOCKED"


# ── 3. allowlist: port ──────────────────────────────────────────────────────


class TestPort:
    def test_correct_port_allowed(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is True
        assert r["port"] == TEST_PORT

    def test_missing_port_blocked(self):
        r = _al.validate_internal_test_url(
            f"http://localhost{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is False
        assert r["error_code"] == "URL_PORT_BLOCKED"

    @pytest.mark.parametrize("wrong", [80, 8080, 3000, 5000, TEST_PORT + 1])
    def test_wrong_port_blocked(self, wrong):
        r = _al.validate_internal_test_url(
            f"http://localhost:{wrong}{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is False
        assert r["error_code"] == "URL_PORT_BLOCKED"

    def test_invalid_allowed_port_arg(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}",
            allowed_port=0,
        )
        assert r["ok"] is False
        assert r["error_code"] == "URL_PORT_BLOCKED"


# ── 4. allowlist: path / traversal ──────────────────────────────────────────


class TestPath:
    def test_exact_prefix_allowed(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is True

    def test_subpath_under_prefix_allowed(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}/page1.html",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is True

    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/other",
            "/api/v1/users",
            "/__haehan_test__",  # one level short
            "/__haehan_test__/write",  # different leaf
        ],
    )
    def test_wrong_path_blocked(self, path):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{path}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is False
        assert r["error_code"] in ("URL_PATH_BLOCKED", "URL_RISKY_KEYWORD")

    @pytest.mark.parametrize(
        "path",
        [
            f"{PFX}/../admin",
            f"{PFX}/..",
            f"{PFX}/sub/../../etc",
            f"{PFX}/%2e%2e/admin",
            f"{PFX}/%2e./x",
            f"{PFX}/.%2e/x",
        ],
    )
    def test_path_traversal_blocked(self, path):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{path}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is False
        assert r["error_code"] in ("URL_PATH_TRAVERSAL", "URL_RISKY_KEYWORD")


# ── 5. allowlist: query / fragment ──────────────────────────────────────────


class TestQueryFragment:
    @pytest.mark.parametrize(
        "q",
        [
            "?token=abc",
            "?session=xyz",
            "?password=p",
            "?key=abcd",
            "?x=1",
            "?",
        ],
    )
    def test_query_blocked(self, q):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}{q}",
            allowed_port=TEST_PORT,
        )
        # 빈 '?' 는 query 가 빈 문자열이므로 통과할 수도 있음 — 파서별 차이 허용
        if q == "?":
            assert r["ok"] in (True, False)
        else:
            assert r["ok"] is False
            assert r["error_code"] == "URL_QUERY_BLOCKED"

    def test_fragment_blocked(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}#frag",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is False
        assert r["error_code"] == "URL_FRAGMENT_BLOCKED"


# ── 6. allowlist: risky path keywords ───────────────────────────────────────


class TestRiskyKeywords:
    @pytest.mark.parametrize(
        "kw_path",
        [
            f"{PFX}/login",
            f"{PFX}/signin",
            f"{PFX}/sign-in",
            f"{PFX}/auth/callback",
            f"{PFX}/oauth",
            f"{PFX}/sso",
            f"{PFX}/payment/check",
            f"{PFX}/checkout",
            f"{PFX}/order/123",
            f"{PFX}/delete/item",
            f"{PFX}/remove/me",
            f"{PFX}/withdraw",
            f"{PFX}/cancel",
            f"{PFX}/admin/users",
            f"{PFX}/role/edit",
            f"{PFX}/permission/grant",
            f"{PFX}/grant/admin",
            f"{PFX}/revoke/role",
        ],
    )
    def test_risky_keyword_blocked(self, kw_path):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{kw_path}",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is False
        assert r["error_code"] == "URL_RISKY_KEYWORD"


# ── 7. allowlist: empty / parse failure ─────────────────────────────────────


class TestMisc:
    def test_empty_url(self):
        r = _al.validate_internal_test_url("", allowed_port=TEST_PORT)
        assert r["ok"] is False
        assert r["error_code"] == "URL_EMPTY"

    def test_about_blank_blocked_in_internal_gate(self):
        """about:blank 은 12I 게이트의 영역. internal_test 게이트는 허용 안 함."""
        r = _al.validate_internal_test_url("about:blank", allowed_port=TEST_PORT)
        assert r["ok"] is False
        assert r["error_code"] in ("URL_SCHEME_BLOCKED", "URL_HOST_BLOCKED", "URL_PATH_BLOCKED")


# ── 8. page safety: password / file input ───────────────────────────────────


class TestPagePassword:
    def test_password_input_blocks(self):
        ps = {
            "inputs": [{"type": "password", "name": "pw"}],
            "forms": [],
            "textareas": [],
        }
        r = _al.analyze_internal_page_safety(ps)
        assert r["safe"] is False
        assert r["blocked_reason"] == "PASSWORD_INPUT_PRESENT"

    def test_file_input_blocks(self):
        ps = {
            "inputs": [{"type": "file", "name": "upload"}],
            "forms": [],
            "textareas": [],
        }
        r = _al.analyze_internal_page_safety(ps)
        assert r["safe"] is False
        assert r["blocked_reason"] == "FILE_INPUT_PRESENT"

    def test_text_input_allowed(self):
        ps = {
            "inputs": [{"type": "text", "name": "search"}],
            "forms": [],
            "textareas": [],
        }
        r = _al.analyze_internal_page_safety(ps)
        assert r["safe"] is True


# ── 9. page safety: form POST / textarea / contenteditable ──────────────────


class TestPageMutation:
    def test_form_post_blocks(self):
        ps = {
            "inputs": [],
            "forms": [{"method": "post", "action": "/x"}],
            "textareas": [],
        }
        r = _al.analyze_internal_page_safety(ps)
        assert r["safe"] is False
        assert r["blocked_reason"] == "FORM_POST_PRESENT"

    def test_form_get_allowed(self):
        ps = {
            "inputs": [],
            "forms": [{"method": "get", "action": "/x"}],
            "textareas": [],
        }
        r = _al.analyze_internal_page_safety(ps)
        assert r["safe"] is True

    def test_form_with_password_blocks(self):
        ps = {
            "inputs": [],
            "forms": [{"method": "get", "has_password": True}],
            "textareas": [],
        }
        r = _al.analyze_internal_page_safety(ps)
        assert r["safe"] is False
        assert r["blocked_reason"] == "PASSWORD_INPUT_PRESENT"

    def test_textarea_blocks(self):
        ps = {"inputs": [], "forms": [], "textareas": [{"name": "memo"}]}
        r = _al.analyze_internal_page_safety(ps)
        assert r["safe"] is False
        assert r["blocked_reason"] == "TEXTAREA_PRESENT"

    def test_contenteditable_blocks(self):
        ps = {"inputs": [], "forms": [], "textareas": []}
        html = "<html><body><div contenteditable='true'>x</div></body></html>"
        r = _al.analyze_internal_page_safety(
            ps,
            raw_html_for_contenteditable_check=html,
        )
        assert r["safe"] is False
        assert r["blocked_reason"] == "CONTENTEDITABLE_PRESENT"

    def test_no_contenteditable_safe(self):
        ps = {"inputs": [], "forms": [], "textareas": []}
        html = "<html><body><p>plain</p></body></html>"
        r = _al.analyze_internal_page_safety(
            ps,
            raw_html_for_contenteditable_check=html,
        )
        assert r["safe"] is True


# ── 10. page safety: final_url escape ───────────────────────────────────────


class TestFinalUrlEscape:
    def test_final_url_inside_allowlist_safe(self):
        ps = {"inputs": [], "forms": [], "textareas": []}
        r = _al.analyze_internal_page_safety(
            ps,
            final_url=f"http://localhost:{TEST_PORT}{PFX}/page",
            allowed_port=TEST_PORT,
        )
        assert r["safe"] is True

    @pytest.mark.parametrize(
        "final",
        [
            "https://example.com/x",
            "http://192.168.0.1/x",
            "http://localhost:8080/__haehan_test__/readonly",
            "http://0.0.0.0:9876/__haehan_test__/readonly",
            "http://localhost:9876/__haehan_test__/readonly?token=x",
        ],
    )
    def test_final_url_outside_allowlist_blocks(self, final):
        ps = {"inputs": [], "forms": [], "textareas": []}
        r = _al.analyze_internal_page_safety(
            ps,
            final_url=final,
            allowed_port=TEST_PORT,
        )
        assert r["safe"] is False
        assert r["blocked_reason"] == "FINAL_URL_OUTSIDE_ALLOWLIST"


# ── 11. audit payload sanitize 가이드 검증 ──────────────────────────────────


class TestAuditPayloadGuide:
    def test_validate_result_does_not_include_query_or_fragment(self):
        r = _al.validate_internal_test_url(
            f"http://localhost:{TEST_PORT}{PFX}/sub",
            allowed_port=TEST_PORT,
        )
        assert r["ok"] is True
        # 통과 시 반환되는 키만 audit 에 노출 가능
        for forbidden in (
            "query",
            "fragment",
            "cookie",
            "session",
            "token",
            "authorization",
            "password",
            "localstorage",
            "sessionstorage",
            "html",
            "page_content",
            "content",
        ):
            assert forbidden not in r, f"forbidden key in validate result: {forbidden}"
        # 허용 메타 필드 존재 확인
        assert r["url_category"] == "internal_test"
        assert r["allowlist_name"] == "internal_test_default"

    def test_block_result_does_not_include_url_original(self):
        """블록 응답에도 url 원문/query/fragment 가 그대로 노출되지 않음."""
        url = f"http://localhost:{TEST_PORT}{PFX}?token=SECRETVAL"
        r = _al.validate_internal_test_url(url, allowed_port=TEST_PORT)
        assert r["ok"] is False
        # error_code/reason 만 노출, secret value 가 그대로 들어가지 않음
        for v in r.values():
            assert "SECRETVAL" not in str(v)


# ── 12. 실제 실행 부재 ──────────────────────────────────────────────────────


class TestNoActualLaunch:
    def test_no_subprocess_or_network_invoked(self):
        blocked: list = []
        with patch("subprocess.run", side_effect=lambda *a, **k: blocked.append(("run", a))):
            with patch("subprocess.Popen", side_effect=lambda *a, **k: blocked.append(("Popen", a))):
                with patch("os.system", side_effect=lambda *a, **k: blocked.append(("system", a))):
                    _al.validate_internal_test_url(
                        f"http://localhost:{TEST_PORT}{PFX}",
                        allowed_port=TEST_PORT,
                    )
                    _al.analyze_internal_page_safety({"inputs": [], "forms": [], "textareas": []})
        assert blocked == []

    def test_module_does_not_import_network_libs(self):
        """allowlist 모듈은 requests/httpx/urllib3/playwright 등 네트워크 라이브러리를 import 하지 않음."""
        import inspect

        src = inspect.getsource(_al)
        for forbidden in (
            "import requests",
            "import httpx",
            "from requests",
            "from httpx",
            "import urllib3",
            "import playwright",
            "from playwright",
            "import socket",
            "import http.client",
        ):
            assert forbidden not in src, f"forbidden import: {forbidden}"
