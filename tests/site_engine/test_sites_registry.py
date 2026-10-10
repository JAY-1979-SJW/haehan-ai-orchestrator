"""Connector registry 로딩/등록/조회 테스트."""
from __future__ import annotations

from ai_orchestrator.sites import registry
from ai_orchestrator.sites.connector import SiteConnector
from ai_orchestrator.sites.models import SiteHealthStatus


def test_builtin_connectors_registered():
    names = set(registry.all_names())
    assert "dummy" in names
    assert "example_portal" in names


def test_get_returns_connector_instance():
    conn = registry.get("dummy")
    assert conn is not None
    assert conn.name == "dummy"
    assert "ping" in conn.supported_actions


def test_register_unregister_roundtrip():
    class _TempConn(SiteConnector):
        name = "temp_conn_for_test"
        supported_actions = ("noop",)

        def health_check(self) -> SiteHealthStatus:
            return SiteHealthStatus(site_name=self.name, connector_name=type(self).__name__)

    try:
        registry.register(_TempConn())
        assert registry.get("temp_conn_for_test") is not None
    finally:
        registry.unregister("temp_conn_for_test")
    assert registry.get("temp_conn_for_test") is None


def test_register_type_validation():
    try:
        registry.register("not-a-connector")  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("TypeError 가 발생해야 한다")
