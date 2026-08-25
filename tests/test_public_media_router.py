from __future__ import annotations

from ai_orchestrator.connectors.public_media_router import _ALLOWED_EXT, _TOKEN_RE


def test_token_pattern_accepts_valid_hex_token():
    assert _TOKEN_RE.match("0123456789abcdef0123456789abcdef.mp4")
    assert _TOKEN_RE.match("0123456789abcdef0123456789abcdef.png")


def test_token_pattern_rejects_path_traversal_and_garbage():
    assert not _TOKEN_RE.match("../../etc/passwd")
    assert not _TOKEN_RE.match("not-a-hex-token.mp4")
    assert not _TOKEN_RE.match("0123456789abcdef0123456789abcdef")  # 확장자 없음
    assert not _TOKEN_RE.match("0123456789abcdef0123456789abcdef.mp4/../x")


def test_allowed_extensions_limited_to_media():
    assert _ALLOWED_EXT == {".mp4", ".mov", ".jpg", ".jpeg", ".png"}
    assert ".exe" not in _ALLOWED_EXT
    assert ".py" not in _ALLOWED_EXT
