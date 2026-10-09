from __future__ import annotations

from tools.verify import verify_live_agent_smoke as smoke


class _Close:
    def __init__(self, code: int) -> None:
        self.code = code


class _ModernClosed:
    def __init__(self, code: int) -> None:
        self.rcvd = _Close(code)


class _LegacyClosed:
    def __init__(self, code: int) -> None:
        self.rcvd_close = _Close(code)


class _CodeClosed:
    def __init__(self, code: int) -> None:
        self.code = code


def test_websocket_close_code_supports_modern_websockets_shape():
    assert smoke._websocket_close_code(_ModernClosed(4401)) == 4401


def test_websocket_close_code_supports_legacy_websockets_shape():
    assert smoke._websocket_close_code(_LegacyClosed(4401)) == 4401


def test_websocket_close_code_supports_direct_code_shape():
    assert smoke._websocket_close_code(_CodeClosed(1011)) == 1011


def test_websocket_close_code_unknown_returns_none():
    assert smoke._websocket_close_code(object()) is None
