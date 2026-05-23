"""Allowlist boundary for desktop CAD bridge proxy paths."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

STATIC_POST_ALLOW: frozenset[str] = frozenset({
    "acad/arch-quantity-tab/build-cards",
    "acad/inventory/analyze-drawing-inventory",
    "acad/schedule-tables/detect",
    "acad/construction-sequence/plan",
})

GET_ALLOW: frozenset[str] = frozenset({
    "acad/health",
    "acad/openapi.json",
})


def derive_post_allow_from_registry() -> frozenset[str]:
    """Return candidate-payload CAD endpoints from the local command registry."""
    try:
        from local_agent.cad.command_contract import (  # noqa: WPS433
            DEFAULT_REGISTRY,
            RiskLevel,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("registry import failed, using static allow: %s", exc)
        return STATIC_POST_ALLOW

    paths: set[str] = set()
    try:
        for tool_id in DEFAULT_REGISTRY.list_by_risk(RiskLevel.CANDIDATE_PAYLOAD):
            entry = DEFAULT_REGISTRY.get(tool_id)
            if entry.endpointPath:
                paths.add(entry.endpointPath.lstrip("/"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("registry walk failed, using static allow: %s", exc)
        return STATIC_POST_ALLOW
    if not paths:
        return STATIC_POST_ALLOW
    return frozenset(paths | STATIC_POST_ALLOW)


POST_ALLOW: frozenset[str] = derive_post_allow_from_registry()


__all__ = [
    "GET_ALLOW",
    "POST_ALLOW",
    "STATIC_POST_ALLOW",
    "derive_post_allow_from_registry",
]
