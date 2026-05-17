"""External Site Automation Capability Registry.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

사이트별 AI 자동화 가능 범위와 금지 범위를 조회하는 인터페이스.
"""
from __future__ import annotations

from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY, get_provider


def get_allowed_scope(provider_id: str) -> list[str]:
    p = get_provider(provider_id)
    return list(p.allowed_automation_scope) if p else []


def get_forbidden_scope(provider_id: str) -> list[str]:
    p = get_provider(provider_id)
    return list(p.forbidden_automation_scope) if p else []


def is_cdp_allowed(provider_id: str) -> bool:
    p = get_provider(provider_id)
    return p.cdp_browser_allowed if p else False


def is_headless_allowed(provider_id: str) -> bool:
    p = get_provider(provider_id)
    return p.headless_allowed if p else False


def list_cdp_allowed_providers() -> list[str]:
    return [p.provider_id for p in PROVIDER_REGISTRY if p.cdp_browser_allowed]


def list_approval_required_providers() -> list[str]:
    return [p.provider_id for p in PROVIDER_REGISTRY if p.approval_gate_required]


__all__ = [
    "get_allowed_scope",
    "get_forbidden_scope",
    "is_cdp_allowed",
    "is_headless_allowed",
    "list_cdp_allowed_providers",
    "list_approval_required_providers",
]
