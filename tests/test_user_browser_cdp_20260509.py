"""user_browser_cdp 단위 테스트.

실제 Chrome 연결 없이 검증 가능한 부분만 테스트.
실전 CDP 연결은 별도 통합 테스트.
"""
from __future__ import annotations

import pytest

from ai_orchestrator.local_agent.user_browser_cdp import (
    cdp_endpoint, is_cdp_available, get_chrome_start_command,
    open_cdp_session, CDPConnectionError, CDPSession,
    DEFAULT_CDP_PORT, DEFAULT_CDP_HOST,
)


def test_cdp_endpoint_default():
    assert cdp_endpoint() == f"http://{DEFAULT_CDP_HOST}:{DEFAULT_CDP_PORT}"


def test_cdp_endpoint_custom():
    assert cdp_endpoint("127.0.0.1", 9999) == "http://127.0.0.1:9999"


def test_is_cdp_unavailable_returns_dict():
    # 사용하지 않는 포트로 확인
    result = is_cdp_available(port=59321, timeout=1.0)
    assert result["available"] is False
    assert "error" in result
    assert result["port"] == 59321


def test_chrome_start_command_includes_port():
    cmd = get_chrome_start_command(port=9222)
    assert "--remote-debugging-port=9222" in cmd
    assert "chrome.exe" in cmd.lower()


def test_chrome_start_command_custom_user_data_dir():
    cmd = get_chrome_start_command(user_data_dir=r"D:\test\profile", port=9999)
    assert "9999" in cmd
    assert "D:\\test\\profile" in cmd


def test_open_cdp_session_raises_when_no_chrome():
    # Chrome이 디버깅 모드로 실행 중이지 않으면 CDPConnectionError
    with pytest.raises(CDPConnectionError) as exc_info:
        with open_cdp_session(port=59322, require_existing_chrome=True):
            pass
    err_msg = str(exc_info.value)
    assert "9222" in err_msg or "59322" in err_msg
    assert "remote-debugging-port" in err_msg


def test_cdp_session_dataclass_fields():
    # CDPSession 생성 가능 확인
    session = CDPSession(playwright=None, browser=None, context=None)
    assert session.opened_pages == []
    session.opened_pages.append("dummy")
    assert len(session.opened_pages) == 1


def test_cdp_error_message_includes_helper_script_hint():
    with pytest.raises(CDPConnectionError) as exc_info:
        with open_cdp_session(port=59323, require_existing_chrome=True):
            pass
    assert "start_chrome_with_cdp.py" in str(exc_info.value)


def test_is_cdp_available_invalid_host_returns_unavailable():
    result = is_cdp_available(host="invalid.host.local.test.xyz", port=9222, timeout=1.0)
    assert result["available"] is False
