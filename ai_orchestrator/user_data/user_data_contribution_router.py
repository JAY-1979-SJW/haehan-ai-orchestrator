"""User data contribution consent and safe development material export API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_orchestrator.user_data.user_data_contribution_store import (
    export_development_material,
    get_consent,
    grant_consent,
    list_consents,
    revoke_consent,
)
from tools.gates.auth import require_role

user_data_contribution_router = APIRouter(
    prefix="/data-contribution",
    tags=["data-contribution"],
)


class GrantConsentRequest(BaseModel):
    user_reference: str = ""
    organization_reference: str = ""
    purposes: list[str] = Field(default_factory=list)
    data_categories: list[str] = Field(default_factory=list)
    retention_days: int = 365


class ExportDevelopmentMaterialRequest(BaseModel):
    user_reference: str
    purpose: str
    records: list[dict[str, Any]] = Field(default_factory=list)


@user_data_contribution_router.post("/consents")
def create_data_contribution_consent(
    body: GrantConsentRequest,
    current_user: dict = Depends(require_role("operator", "admin", "owner")),
) -> dict[str, Any]:
    """Record explicit consent on the server."""
    user_reference = body.user_reference or current_user.get("actor", "")
    try:
        record = grant_consent(
            user_reference=user_reference,
            organization_reference=body.organization_reference,
            purposes=body.purposes,
            data_categories=body.data_categories,
            retention_days=body.retention_days,
            source="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": record}


@user_data_contribution_router.get("/consents/{consent_id}")
def read_data_contribution_consent(
    consent_id: str,
    current_user: dict = Depends(require_role("operator", "admin", "owner")),
) -> dict[str, Any]:
    """Read a consent record without exposing sensitive user content."""
    record = get_consent(consent_id)
    if not record:
        raise HTTPException(status_code=404, detail="consent not found")
    return {"ok": True, "data": record}


@user_data_contribution_router.get("/consents")
def read_data_contribution_consents(
    user_reference: str = "",
    status: str = "",
    limit: int = 50,
    current_user: dict = Depends(require_role("operator", "admin", "owner")),
) -> dict[str, Any]:
    """List consent records; this is metadata only."""
    records = list_consents(user_reference=user_reference, status=status, limit=limit)
    return {"ok": True, "data": {"consents": records}, "meta": {"count": len(records)}}


@user_data_contribution_router.post("/consents/{consent_id}/revoke")
def revoke_data_contribution_consent(
    consent_id: str,
    current_user: dict = Depends(require_role("operator", "admin", "owner")),
) -> dict[str, Any]:
    """Revoke consent while preserving the revocation record."""
    record = revoke_consent(consent_id)
    if not record:
        raise HTTPException(status_code=404, detail="consent not found")
    return {"ok": True, "data": record}


@user_data_contribution_router.post("/development-material/export")
def export_user_development_material(
    body: ExportDevelopmentMaterialRequest,
    current_user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Export only consent-gated, redacted, minimized development material."""
    result = export_development_material(
        user_reference=body.user_reference,
        purpose=body.purpose,
        records=body.records,
    )
    return {"ok": bool(result.get("accepted")), "data": result}
