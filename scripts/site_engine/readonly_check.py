"""Shared read-only check helpers for SSO subdomain services."""
from __future__ import annotations

from typing import Any

from scripts.site_engine.sso_runtime import dry_run_login_entry_task, dry_run_subdomain_readonly_task
from scripts.site_engine.subdomain_registry import get_provider


def build_provider_readonly_check_plan(provider_id: str) -> dict[str, Any]:
    provider = get_provider(provider_id)
    login = dry_run_login_entry_task(provider_id)
    services = [dry_run_subdomain_readonly_task(provider_id, service.key) for service in provider.services]
    return {
        "provider_id": provider.provider_id,
        "login_entry": login,
        "service_count": len(services),
        "services": services,
        "ok": bool(login.get("ok")) and all(bool(service.get("ok")) for service in services),
        "state_change": False,
    }

