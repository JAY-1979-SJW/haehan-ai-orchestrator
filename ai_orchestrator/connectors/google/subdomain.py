"""Google 서브도메인 카탈로그 + 로그인 상태 라우트."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends

from tools.gates.auth import require_role

from ._helpers import audit, duration_ms

router = APIRouter()


@router.get("/subdomain-catalog")
def get_subdomain_catalog(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """등록된 Google 서브도메인 32개 카탈로그 반환."""
    t0 = time.monotonic()
    from scripts.google.common.subdomain_logic import build_google_subdomain_logic_catalog

    catalog = build_google_subdomain_logic_catalog()
    audit("GOOGLE_SUBDOMAIN_CATALOG_READ", user, status="ok", note=f"count={catalog['subdomain_count']}")
    return {**catalog, "duration_ms": duration_ms(t0)}


@router.get("/status")
def get_google_status(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Google 도구 전체 상태 요약."""
    t0 = time.monotonic()
    from scripts.google.common.domain_taxonomy import build_google_page_tab_catalog
    from scripts.google.common.subdomain_logic import build_google_subdomain_logic_catalog

    catalog = build_google_subdomain_logic_catalog()
    build_google_page_tab_catalog("all")
    audit("GOOGLE_STATUS_READ", user, status="ok")
    return {
        "ok": True,
        "subdomain_count": catalog["subdomain_count"],
        "login_policy": catalog["login_policy"],
        "same_profile_subdomain_navigation": catalog["same_profile_subdomain_navigation"],
        "subdomains": [
            {
                "host": s["host"],
                "sso_service_key": s["sso_service_key"],
                "read_actions": len(s["read_actions"]),
                "approval_actions": len(s["approval_actions"]),
                "risk_boundary": s["risk_boundary"],
            }
            for s in catalog["subdomains"]
        ],
        "duration_ms": duration_ms(t0),
    }
