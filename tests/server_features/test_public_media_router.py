from __future__ import annotations

from ai_orchestrator.connectors.public_media_router import _ALLOWED_EXT, _TOKEN_RE, public_media_router


def test_media_route_accepts_get_and_head():
    """Instagram Graph API의 비디오 수집기는 GET 전에 HEAD로 먼저 확인한다 —
    HEAD가 405면 컨테이너 처리가 ERROR로 실패한다(2026-08-25 실측)."""
    route = next(r for r in public_media_router.routes if r.path == "/public-media/{token}")
    assert "GET" in route.methods
    assert "HEAD" in route.methods


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
