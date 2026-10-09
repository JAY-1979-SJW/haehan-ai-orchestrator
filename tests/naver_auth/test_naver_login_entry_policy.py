from ai_orchestrator.external_sites.provider_registry import get_provider
from ai_orchestrator.sites.adapters.naver_cafe_adapter import NaverCafeAdapter
from core.agent_runtime.runtime.permission.content_workflow_policy import NAVER_LOGIN_DOMAIN
from scripts.auth.known_login_urls import get_known_login_url
from scripts.naver.common.auth import NAVER_LOGIN_URL
from scripts.site_engine.subdomain_registry import PROVIDERS as SSO_PROVIDERS


def test_naver_login_starts_from_naver_main():
    assert NAVER_LOGIN_URL == "https://www.naver.com/"
    assert NaverCafeAdapter.LOGIN_URL == "https://www.naver.com/"
    assert NAVER_LOGIN_DOMAIN == "www.naver.com"


def test_known_naver_login_urls_use_naver_main():
    for domain in (
        "mail.naver.com",
        "sell.smartstore.naver.com",
        "smartstore.naver.com",
        "commerce.naver.com",
        "center.shopping.naver.com",
        "adcenter.naver.com",
    ):
        assert get_known_login_url(domain) == "https://www.naver.com/"


def test_provider_registry_naver_login_uses_naver_main():
    naver = get_provider("NAVER")
    assert naver is not None
    assert naver.login_url == "https://www.naver.com/"


def test_sso_registry_naver_login_service_uses_naver_main():
    naver = next(p for p in SSO_PROVIDERS if p.provider_id == "naver")
    login_service = next(s for s in naver.services if s.key == "naver_login")
    assert naver.login_entry_url == "https://www.naver.com/"
    assert login_service.url == "https://www.naver.com/"
    assert login_service.host == "www.naver.com"
