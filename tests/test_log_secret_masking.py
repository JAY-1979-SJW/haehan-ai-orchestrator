"""접근 로그에 데스크톱 키(?license=desktop-…)가 평문으로 남지 않는지 고정한다.

2026-10-08 실측: 옛 로컬 에이전트가 키를 WebSocket URL 쿼리로 보내 uvicorn 접근 로그(fastapi.log)에 그대로 기록됐다.
"""

import logging

from ai_orchestrator.connectors.smartstore import agent_ws
from ai_orchestrator.logging_setup import MaskSecretsFilter, mask_secrets, uvicorn_log_config

SECRET = "desktop-AbCdEf0123456789"


def test_mask_secrets_hides_query_values_only():
    out = mask_secrets(f"/api/v1/smartstore/agent/ws?license={SECRET}&x=1")
    assert SECRET not in out
    assert out == "/api/v1/smartstore/agent/ws?license=***&x=1"
    assert mask_secrets("/api/v1/health?foo=bar") == "/api/v1/health?foo=bar"


def _format_through_handler(logger_name: str, msg: str, args: tuple) -> str:
    """uvicorn 설정이 만든 핸들러(포맷터+필터)를 그대로 거쳐 출력될 최종 문자열."""
    import logging.config

    logging.config.dictConfig(uvicorn_log_config())
    handler = logging.getLogger("uvicorn").handlers[0]
    record = logging.LogRecord(logger_name, logging.INFO, __file__, 1, msg, args, None)
    assert handler.filter(record)
    return handler.format(record)


def test_uvicorn_access_line_is_masked():
    import logging.config

    logging.config.dictConfig(uvicorn_log_config())
    access = logging.getLogger("uvicorn.access").handlers[0]
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/x?license={SECRET}", "1.1", 200),
        None,
    )
    assert access.filter(record)
    line = access.format(record)
    assert SECRET not in line
    assert "license=***" in line


def test_uvicorn_websocket_line_is_masked():
    line = _format_through_handler(
        "uvicorn.error", '%s - "WebSocket %s" [accepted]', ("127.0.0.1:5000", f"/agent/ws?license={SECRET}")
    )
    assert SECRET not in line
    assert "license=***" in line


def test_filter_keeps_args_shape():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "%s %d", (f"?token={SECRET}", 7), None)
    assert MaskSecretsFilter().filter(record) is True
    assert record.args == ("?token=***", 7)


def test_agent_ws_accepts_key_from_header_not_only_query():
    import inspect

    params = inspect.signature(agent_ws.agent_ws).parameters
    assert "x_license_key" in params  # 헤더로 받는다
    assert params["license"].default is not ...  # 쿼리는 호환용 선택값
