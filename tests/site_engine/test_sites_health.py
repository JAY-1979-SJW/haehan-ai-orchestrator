"""SiteHealthService 기본 동작 및 graceful failure 테스트.

- credentials/session 파일 없음 상태에서 example_portal 은 unconfigured 이어야 한다.
- connector 가 예외를 던져도 서비스는 unavailable 상태로 반환해야 한다.
"""

from __future__ import annotations

from ai_orchestrator.sites import registry, secrets_policy
from ai_orchestrator.sites.connector import SiteConnector
from ai_orchestrator.sites.health import SiteHealthService
from ai_orchestrator.sites.models import SiteHealthStatus


def test_check_all_returns_results_for_all_connectors():
    svc = SiteHealthService()
    results = svc.check_all()
    names = {r.site_name for r in results}
    assert "dummy" in names
    assert "example_portal" in names


def test_example_portal_unconfigured_when_no_secrets(tmp_path, monkeypatch):
    # SECRETS_ROOT 를 임시 디렉터리로 옮기면 자격증명/세션 파일이 존재하지 않는다.
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path / "empty_secrets"))
    assert not secrets_policy.credentials_present("example_portal")
    assert not secrets_policy.session_state_present("example_portal")

    svc = SiteHealthService()
    status = svc.check_one("example_portal")
    assert status is not None
    assert status.state in {"unconfigured", "degraded"}
    assert status.credentials_present is False
    assert status.session_state_present is False


def test_check_one_returns_none_for_unknown_site():
    svc = SiteHealthService()
    assert svc.check_one("this-site-does-not-exist") is None


def test_connector_exception_is_swallowed_into_unavailable():
    class _Boom(SiteConnector):
        name = "boom_conn_for_test"
        supported_actions = ()

        def health_check(self) -> SiteHealthStatus:
            raise RuntimeError("db connection lost: password=hunter2")  # 민감 내용 모사

    try:
        registry.register(_Boom(), overwrite=True)
        svc = SiteHealthService()
        status = svc.check_one("boom_conn_for_test")
        assert status is not None
        assert status.state == "unavailable"
        assert status.error == "HEALTH_CHECK_EXCEPTION"
        # 민감 원문이 상태 객체에 새지 않아야 한다.
        assert "hunter2" not in (status.warning + status.error + repr(status.details))
    finally:
        registry.unregister("boom_conn_for_test")
