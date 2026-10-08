"""Gabia Canonical Site Settings Registry.

[GABIA_SITE_SETTINGS_CANONICAL_REGISTRY_AUDIT_01]

실제 운영 상태와 코드 초안을 분리해 단일 소스로 관리한다.
DNS 저장/변경 없음. 서버 반영 없음. 쿠키 저장 없음.

상태 구분:
    CURRENT  — 현재 운영 중. Gabia DNS 등록 + SSL 발급 + nginx 활성
    PLANNED  — 계획됨. 아직 DNS 미등록
    HOLD     — 보류. 후보로 남겨 두되 현재 작업 범위 외
    LEGACY   — 기존 병행 경로. 신규 연결 없이 유지만
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 상태 상수
# ---------------------------------------------------------------------------

STATUS_CURRENT = "CURRENT"
STATUS_PLANNED = "PLANNED"
STATUS_HOLD = "HOLD"
STATUS_LEGACY = "LEGACY"

# ---------------------------------------------------------------------------
# SiteSettingsEntry — 개별 도메인/경로 설정 항목
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteSettingsEntry:
    entry_id: str
    fqdn: str
    record_type: str
    target_ip: str
    status: str
    ssl_status: str
    nginx_status: str
    purpose: str
    notes: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "fqdn": self.fqdn,
            "record_type": self.record_type,
            "target_ip": self.target_ip,
            "status": self.status,
            "ssl_status": self.ssl_status,
            "nginx_status": self.nginx_status,
            "purpose": self.purpose,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Canonical Registry
# ---------------------------------------------------------------------------

CANONICAL_SITE_SETTINGS: tuple[SiteSettingsEntry, ...] = (
    # ── CURRENT: 대표 AI 자동업무 본관 ───────────────────────────────────────
    SiteSettingsEntry(
        entry_id="autowork_haehan_ai_kr",
        fqdn="autowork.haehan-ai.kr",
        record_type="A",
        target_ip="1.201.176.236",
        status=STATUS_CURRENT,
        ssl_status="issued",
        nginx_status="active",
        purpose="AI 자동업무 본관 — 대표 서브도메인",
        notes="DNS A 레코드 등록 완료. SSL 발급 완료. nginx 활성.",
    ),
    # ── LEGACY: 기존 병행 경로 ────────────────────────────────────────────────
    SiteSettingsEntry(
        entry_id="orchestrator_path",
        fqdn="haehan-ai.kr/orchestrator/",
        record_type="PATH",
        target_ip="1.201.176.236",
        status=STATUS_LEGACY,
        ssl_status="issued",
        nginx_status="active",
        purpose="기존 orchestrator API 병행 경로 (신규 연결 없이 유지)",
        notes="autowork 전환 후에도 레거시 경로 병행 운영 중.",
    ),
    SiteSettingsEntry(
        entry_id="orchestrator_api_path",
        fqdn="haehan-ai.kr/orchestrator/api/",
        record_type="PATH",
        target_ip="1.201.176.236",
        status=STATUS_LEGACY,
        ssl_status="issued",
        nginx_status="active",
        purpose="기존 orchestrator API 경로 (레거시 병행)",
        notes="autowork 전환 후에도 레거시 경로 병행 운영 중.",
    ),
    # ── PLANNED / HOLD: 후보 서브도메인 ──────────────────────────────────────
    SiteSettingsEntry(
        entry_id="assistant_haehan_ai_kr",
        fqdn="assistant.haehan-ai.kr",
        record_type="A",
        target_ip="PENDING_USER_CONFIRMATION",
        status=STATUS_HOLD,
        ssl_status="not_issued",
        nginx_status="inactive",
        purpose="비서앱 admin-web 프론트엔드 후보 서브도메인",
        notes="현재 작업 범위 외. 별도 승인 후 진행.",
    ),
    SiteSettingsEntry(
        entry_id="assistant_api_haehan_ai_kr",
        fqdn="assistant-api.haehan-ai.kr",
        record_type="A",
        target_ip="PENDING_USER_CONFIRMATION",
        status=STATUS_HOLD,
        ssl_status="not_issued",
        nginx_status="inactive",
        purpose="비서앱 FastAPI 백엔드 API 후보 서브도메인",
        notes="현재 작업 범위 외. 별도 승인 후 진행.",
    ),
)

# ---------------------------------------------------------------------------
# 조회 API
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, SiteSettingsEntry] = {e.entry_id: e for e in CANONICAL_SITE_SETTINGS}


def get_entry(entry_id: str) -> SiteSettingsEntry | None:
    return _REGISTRY.get(entry_id)


def list_by_status(status: str) -> list[SiteSettingsEntry]:
    return [e for e in CANONICAL_SITE_SETTINGS if e.status == status]


def get_canonical_primary() -> SiteSettingsEntry:
    """대표 서브도메인(CURRENT) 항목 반환."""
    current = list_by_status(STATUS_CURRENT)
    if not current:
        raise RuntimeError("CURRENT 상태 항목 없음")
    return current[0]


__all__ = [
    "CANONICAL_SITE_SETTINGS",
    "STATUS_CURRENT",
    "STATUS_HOLD",
    "STATUS_LEGACY",
    "STATUS_PLANNED",
    "SiteSettingsEntry",
    "get_canonical_primary",
    "get_entry",
    "list_by_status",
]
