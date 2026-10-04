"""Shared SSO provider and subdomain service registry."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SubdomainService:
    key: str
    label: str
    url: str
    host: str
    risk_level: str = "read"
    default_action: str = "web_open_url_readonly"


@dataclass(frozen=True)
class SsoProvider:
    provider_id: str
    label: str
    primary_host: str
    login_entry_url: str
    account_entry_url: str
    login_policy: str
    services: tuple[SubdomainService, ...]


GOOGLE_SERVICES = (
    SubdomainService("google_home", "Google Home", "https://www.google.com/", "www.google.com"),
    SubdomainService("google_account", "Google Account", "https://myaccount.google.com/", "myaccount.google.com"),
    SubdomainService("gmail", "Gmail", "https://mail.google.com/mail/u/0/", "mail.google.com"),
    SubdomainService("drive", "Google Drive", "https://drive.google.com/drive/u/0/", "drive.google.com"),
    SubdomainService("calendar", "Google Calendar", "https://calendar.google.com/calendar/u/0/r", "calendar.google.com"),
    SubdomainService("docs", "Google Docs", "https://docs.google.com/document/u/0/", "docs.google.com"),
    SubdomainService("cloud_console", "Google Cloud Console", "https://console.cloud.google.com/", "console.cloud.google.com"),
    SubdomainService("youtube", "YouTube", "https://www.youtube.com/", "www.youtube.com"),
    SubdomainService("youtube_studio", "YouTube Studio", "https://studio.youtube.com/", "studio.youtube.com"),
    SubdomainService("search_console", "Google Search Console", "https://search.google.com/search-console", "search.google.com"),
    SubdomainService("ai_studio", "Google AI Studio", "https://aistudio.google.com/", "aistudio.google.com"),
    SubdomainService("gemini", "Gemini", "https://gemini.google.com/", "gemini.google.com"),
)

NAVER_SERVICES = (
    SubdomainService("naver_home", "Naver Home", "https://www.naver.com/", "www.naver.com"),
    SubdomainService("naver_login", "Naver Login", "https://www.naver.com/", "www.naver.com"),
    SubdomainService("naver_mail", "Naver Mail", "https://mail.naver.com/", "mail.naver.com"),
    SubdomainService("naver_cafe", "Naver Cafe", "https://cafe.naver.com/", "cafe.naver.com"),
    SubdomainService("naver_blog", "Naver Blog", "https://blog.naver.com/", "blog.naver.com"),
    SubdomainService("naver_mybox", "Naver MYBOX", "https://mybox.naver.com/", "mybox.naver.com"),
    SubdomainService("naver_calendar", "Naver Calendar", "https://calendar.naver.com/", "calendar.naver.com"),
    SubdomainService("naver_pay", "Naver Pay", "https://new-m.pay.naver.com/", "new-m.pay.naver.com"),
    SubdomainService("naver_smartstore", "Naver Smartstore Center", "https://sell.smartstore.naver.com/#/home/dashboard", "sell.smartstore.naver.com"),
    SubdomainService("naver_search_advisor", "Naver Search Advisor", "https://searchadvisor.naver.com/", "searchadvisor.naver.com"),
    SubdomainService("naver_place", "Naver SmartPlace", "https://new.smartplace.naver.com/", "new.smartplace.naver.com"),
)

PROVIDERS = (
    SsoProvider(
        provider_id="google",
        label="Google",
        primary_host="google.com",
        login_entry_url="https://www.google.com/",
        account_entry_url="https://myaccount.google.com/",
        login_policy="user_present_sso_profile",
        services=GOOGLE_SERVICES,
    ),
    SsoProvider(
        provider_id="naver",
        label="Naver",
        primary_host="naver.com",
        login_entry_url="https://www.naver.com/",
        account_entry_url="https://nid.naver.com/",
        login_policy="user_present_sso_profile",
        services=NAVER_SERVICES,
    ),
)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def list_providers() -> list[dict]:
    return [
        {
            **asdict(provider),
            "services": [asdict(service) for service in provider.services],
        }
        for provider in PROVIDERS
    ]


def get_provider(provider_id: str) -> SsoProvider:
    normalized = (provider_id or "").strip().lower()
    for provider in PROVIDERS:
        if provider.provider_id == normalized:
            return provider
    raise KeyError(f"unknown SSO provider: {provider_id}")


def get_service(provider_id: str, service_key: str) -> SubdomainService:
    provider = get_provider(provider_id)
    normalized = (service_key or "").strip().lower()
    for service in provider.services:
        if service.key == normalized:
            return service
    raise KeyError(f"unknown SSO service: {provider_id}/{service_key}")


def _validate_services(provider, errors):
    service_keys: set[str] = set()
    for service in provider.services:
        if service.key in service_keys:
            errors.append(f"{provider.provider_id}: duplicate service {service.key}")
        service_keys.add(service.key)
        if _host(service.url) != service.host:
            errors.append(f"{provider.provider_id}/{service.key}: host mismatch")
        if service.risk_level != "read":
            errors.append(f"{provider.provider_id}/{service.key}: risk_level must be read")
        if service.default_action != "web_open_url_readonly":
            errors.append(f"{provider.provider_id}/{service.key}: action must be web_open_url_readonly")


def validate_registry() -> list[str]:
    errors: list[str] = []
    provider_ids: set[str] = set()
    for provider in PROVIDERS:
        if provider.provider_id in provider_ids:
            errors.append(f"duplicate provider: {provider.provider_id}")
        provider_ids.add(provider.provider_id)
        if provider.login_policy != "user_present_sso_profile":
            errors.append(f"{provider.provider_id}: login_policy must be user_present_sso_profile")
        for url_field in (provider.login_entry_url, provider.account_entry_url):
            if not _host(url_field):
                errors.append(f"{provider.provider_id}: invalid provider URL {url_field!r}")
        _validate_services(provider, errors)
    return errors
