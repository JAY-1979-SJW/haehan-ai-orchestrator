"""site_engine audit event 빌더.

실제 파일/DB write는 수행하지 않는다.
이벤트 객체 생성과 민감값 masking만 담당한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from scripts.site_engine.types import GateDecision, SiteCapability

_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "token", "secret", "cookie", "session",
    "credential", "api_key", "apikey", "private_key",
    "비밀번호", "토큰", "쿠키", "세션", "시크릿", "인증서",
})

_MASK = "***REDACTED***"


@dataclass
class SiteEngineAuditEvent:
    site_key: str
    capability: SiteCapability
    gate_decision: GateDecision
    action: str
    actor: str = "system"
    approved_by: Optional[str] = None
    result: str = "pending"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def mask_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """민감 키 값을 REDACTED로 치환한 새 딕셔너리를 반환한다."""
    result: dict[str, Any] = {}
    for k, v in data.items():
        if _is_sensitive_key(k):
            result[k] = _MASK
        elif isinstance(v, dict):
            result[k] = mask_sensitive(v)
        else:
            result[k] = v
    return result


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return lower in _SENSITIVE_KEYS or any(s in lower for s in _SENSITIVE_KEYS)


def build_audit_event(
    *,
    site_key: str,
    capability: SiteCapability,
    gate_decision: GateDecision,
    action: str,
    actor: str = "system",
    approved_by: Optional[str] = None,
    result: str = "pending",
    reason: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> SiteEngineAuditEvent:
    safe_metadata = mask_sensitive(metadata or {})
    return SiteEngineAuditEvent(
        site_key=site_key,
        capability=capability,
        gate_decision=gate_decision,
        action=action,
        actor=actor,
        approved_by=approved_by,
        result=result,
        reason=reason,
        metadata=safe_metadata,
    )
