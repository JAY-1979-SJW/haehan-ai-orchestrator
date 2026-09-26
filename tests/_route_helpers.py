"""라우트 스냅샷 테스트 공용 헬퍼: 정확 개수 대신 하한 + 필수 라우트 단언."""

from fastapi.routing import APIRoute, APIWebSocketRoute


def _app():
    from ai_orchestrator.server import app

    return app


def collect_routes():
    return [r for r in _app().routes if isinstance(r, (APIRoute, APIWebSocketRoute))]


def collect_post_routes():
    return [r for r in _app().routes if isinstance(r, APIRoute) and "POST" in (r.methods or set())]


def assert_routes_present(paths):
    have = {r.path for r in collect_routes()}
    missing = [p for p in paths if p not in have]
    assert not missing, f"필수 라우트 누락: {missing}"


def assert_route_floor(n, posts=None):
    assert len(collect_routes()) >= n, f"라우트 수 하한 미달: {len(collect_routes())} < {n}"
    if posts is not None:
        assert len(collect_post_routes()) >= posts, f"POST 수 하한 미달: {len(collect_post_routes())} < {posts}"
