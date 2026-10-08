"""tests/app_contracts/test_server_egress_policy_20260508.py"""
import pytest
from ai_orchestrator.server.server_egress_policy import (
    is_internal_url, is_external_url, assert_server_egress_allowed,
    sanitize_blocked_url_for_log, get_blocked_host_category,
)


def test_localhost_is_internal():
    assert is_internal_url("http://localhost:8000/api") is True


def test_127_is_internal():
    assert is_internal_url("http://127.0.0.1:3000/") is True


def test_docker_service_name_is_internal():
    assert is_internal_url("http://haehan-ai-orchestrator-api:8400/") is True


def test_naver_is_external():
    assert is_external_url("https://naver.com/") is True


def test_g2b_is_external():
    assert is_external_url("https://www.g2b.go.kr/") is True


def test_assert_raises_for_external():
    with pytest.raises(PermissionError):
        assert_server_egress_allowed("https://kbstar.com/")


def test_assert_passes_for_internal():
    # localhost는 raise 안 함
    assert_server_egress_allowed("http://localhost:8000/health")


def test_sanitize_strips_query():
    s = sanitize_blocked_url_for_log("https://example.com/path?token=secret&u=admin")
    assert "secret" not in s
    assert "token" not in s
    assert "example.com" in s
    assert "/path" in s


def test_sanitize_handles_invalid_url():
    s = sanitize_blocked_url_for_log("not-a-url")
    # 유효하지 않은 URL이어도 예외 없이 리턴
    assert isinstance(s, str)


def test_get_category_government():
    assert get_blocked_host_category("https://www.g2b.go.kr/") == "GOVERNMENT"
    assert get_blocked_host_category("https://hometax.go.kr/") == "GOVERNMENT"


def test_get_category_bank():
    assert get_blocked_host_category("https://obank.kbstar.com/") == "BANK"
    assert get_blocked_host_category("https://wooribank.com/") == "BANK"


def test_get_category_portal():
    assert get_blocked_host_category("https://naver.com/") == "PORTAL"


def test_get_category_internal():
    assert get_blocked_host_category("http://localhost:8000/") == "INTERNAL"


def test_private_ip_internal():
    assert is_internal_url("http://192.168.1.10:8080/") is True
    assert is_internal_url("http://10.0.0.5:3000/") is True


def test_external_other_category():
    assert get_blocked_host_category("https://random-external-site.com/") == "EXTERNAL_OTHER"
