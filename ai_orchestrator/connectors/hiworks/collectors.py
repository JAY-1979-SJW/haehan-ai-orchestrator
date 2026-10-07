"""Hiworks 1차 수집 collector 골격.

수집 대상 (읽기 전용):
- 내 프로필
- 조직 단위 (부서/팀)
- 조직 구성원
- 근태 요약

규칙:
- 모든 collector 는 동일한 ``CollectorResult`` 스키마로 응답.
- 공식 엔드포인트는 앱 등록/문서 확인 전이므로 ``ENDPOINTS`` 에 placeholder
  로 두고, dry_run 모드에서는 mock 응답을 반환한다.
- 본 모듈은 직접 네트워크를 타지 않는다 — HiworksClient 로 위임.
- mock 응답에는 가짜 개인정보/시크릿을 넣지 않는다 (필드 키만 noting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import HiworksClient, HiworksResponse

# 공식 문서 확인 후 갱신될 placeholder.
# 실제 경로는 https://developers.hiworks.com 의 공식 OpenAPI 스펙에 맞춰 교체.
ENDPOINTS: dict[str, str] = {
    "my_profile": "/v1/me",
    "org_units": "/v1/org/units",
    "org_members": "/v1/org/members",
    "attendance_summary": "/v1/attendance/summary",
}


@dataclass
class CollectorResult:
    """모든 collector 가 따르는 공통 응답 스키마."""

    collector: str
    status: str  # "ok" | "dry_run" | "unconfigured" | "error"
    items: list = field(default_factory=list)
    item_count: int = 0
    raw: dict | None = None  # 원본 응답의 redacted 요약
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "collector": self.collector,
            "status": self.status,
            "items": self.items,
            "item_count": self.item_count,
            "raw": self.raw,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


# ── mock 응답 (dry_run 시 반환) ──────────────────────────────────
# 실제 인적정보 금지. 필드 키 구조만 보여주는 placeholder.
_MOCK_PAYLOADS: dict[str, list[dict]] = {
    "my_profile": [
        {"id": "<mock-user-id>", "display_name": "<mock>", "email_field": "present"},
    ],
    "org_units": [
        {"unit_id": "<mock-unit-1>", "name_field": "present", "parent_id": None},
    ],
    "org_members": [
        {"user_id": "<mock-user-1>", "unit_id": "<mock-unit-1>", "role_field": "present"},
    ],
    "attendance_summary": [
        {"user_id": "<mock-user-1>", "period_field": "present", "work_minutes_field": "present"},
    ],
}


def _from_response(name: str, resp: HiworksResponse) -> CollectorResult:
    """HiworksResponse → CollectorResult 변환. 민감 원문 노출 금지."""
    if resp.status == "dry_run":
        items = list(_MOCK_PAYLOADS.get(name, []))
        return CollectorResult(
            collector=name,
            status="dry_run",
            items=items,
            item_count=len(items),
            raw={"note": "dry_run mock", "request_summary": resp.request_summary},
        )
    if resp.status == "unconfigured":
        return CollectorResult(
            collector=name,
            status="unconfigured",
            error_code=resp.error_code,
            error_message=resp.error_message,
            raw={"request_summary": resp.request_summary},
        )
    if resp.status == "ok":
        # Hiworks 응답 포맷이 확정되면 키 매핑을 여기서 일관화한다.
        data = resp.data if isinstance(resp.data, dict) else {"value": resp.data}
        raw_items = data.get("items")
        items = raw_items if isinstance(raw_items, list) else []  # 타입 좁히기만(동작 불변)
        return CollectorResult(
            collector=name,
            status="ok",
            items=items,
            item_count=len(items),
            raw={"http_status": resp.http_status, "request_summary": resp.request_summary},
        )
    # error
    return CollectorResult(
        collector=name,
        status="error",
        error_code=resp.error_code or "UNKNOWN",
        error_message=resp.error_message or "",
        raw={"http_status": resp.http_status, "request_summary": resp.request_summary},
    )


def _client_or_default(client: HiworksClient | None) -> HiworksClient:
    return client if client is not None else HiworksClient()


# ── public collectors ───────────────────────────────────────────
def collect_my_profile(client: HiworksClient | None = None) -> CollectorResult:
    c = _client_or_default(client)
    resp = c.request("GET", ENDPOINTS["my_profile"])
    return _from_response("my_profile", resp)


def collect_org_units(client: HiworksClient | None = None) -> CollectorResult:
    c = _client_or_default(client)
    resp = c.request("GET", ENDPOINTS["org_units"])
    return _from_response("org_units", resp)


def collect_org_members(
    client: HiworksClient | None = None,
    *,
    unit_id: str | None = None,
) -> CollectorResult:
    c = _client_or_default(client)
    params: dict[str, Any] = {}
    if unit_id:
        params["unit_id"] = unit_id
    resp = c.request("GET", ENDPOINTS["org_members"], params=params or None)
    return _from_response("org_members", resp)


def collect_attendance_summary(
    client: HiworksClient | None = None,
    *,
    user_id: str | None = None,
    period: str | None = None,
) -> CollectorResult:
    c = _client_or_default(client)
    params: dict[str, Any] = {}
    if user_id:
        params["user_id"] = user_id
    if period:
        params["period"] = period
    resp = c.request("GET", ENDPOINTS["attendance_summary"], params=params or None)
    return _from_response("attendance_summary", resp)


__all__ = [
    "ENDPOINTS",
    "CollectorResult",
    "collect_attendance_summary",
    "collect_my_profile",
    "collect_org_members",
    "collect_org_units",
]
