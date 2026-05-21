# -*- coding: utf-8 -*-
"""CAD agent command audit record + redaction helpers.

CAD-AGENT-CAD-CONTROL-COMMAND-CONTRACT-01.

dataclass + redaction 함수만. 실제 파일/DB write 0건. 본 트랙은
audit log persistence 를 하지 않는다 (D6). 후속 트랙에서 storage
가 붙을 때 본 모듈의 dataclass / redaction 을 그대로 재사용.

정책:
- secret / API key / OAuth token / raw_text 노출 0건.
- 너무 긴 값은 truncate.
- 알려진 비밀 키 (api_key, password, token, secret, ...) 은 항상 redact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from .command_contract import (
    ApprovalStatus,
    CadAgentCommand,
    CommandStatus,
    RiskLevel,
)


# ──────────────────────────────────────────────
# Redaction
# ──────────────────────────────────────────────

# 키 이름 패턴 (lower-case substring 매칭) 이면 값 자체를 마스킹
_REDACT_KEY_SUBSTRINGS: Tuple[str, ...] = (
    "api_key", "apikey", "api-key",
    "password", "passwd", "pwd",
    "secret", "token", "bearer", "authorization", "auth_header",
    "private_key", "client_secret", "refresh_token", "access_token",
    "session_id", "cookie",
)

# 값 길이 제한 (단순 string)
_MAX_VALUE_LEN = 200

_REDACTED_MARKER = "[REDACTED]"


def _is_secret_key(key: str) -> bool:
    k = (key or "").lower()
    return any(sub in k for sub in _REDACT_KEY_SUBSTRINGS)


def _truncate(value: str) -> str:
    if len(value) <= _MAX_VALUE_LEN:
        return value
    return value[:_MAX_VALUE_LEN] + "...[truncated]"


def redact_value(key: str, value: Any) -> Any:
    """secret key 면 redact, 그 외엔 길이 truncate."""
    if _is_secret_key(key):
        return _REDACTED_MARKER
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, dict):
        return redact_args(value)
    if isinstance(value, (list, tuple)):
        return [redact_value(key, v) for v in value]
    return value


def redact_args(args: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """dict 인자 전체 redaction. raw_text 키도 강제 redact."""
    if not args:
        return {}
    out: Dict[str, Any] = {}
    for k, v in args.items():
        if not isinstance(k, str):
            k = str(k)
        # raw_text 는 명시 금지
        if k.lower() == "raw_text":
            out[k] = _REDACTED_MARKER
            continue
        out[k] = redact_value(k, v)
    return out


def summarize_result(result: Any) -> Dict[str, Any]:
    """결과 객체 요약 — secret / raw_text 노출 0건.

    실제 응답 payload 는 본 트랙에서 audit 에 저장하지 않는다. 키 이름
    list 와 type 정도만 요약. 후속 트랙에서 schema 정착 시 확장.
    """
    if result is None:
        return {"type": "none", "keys": []}
    if isinstance(result, Mapping):
        return {
            "type": "dict",
            "keys": sorted(str(k) for k in result.keys()),
            "size": len(result),
        }
    if isinstance(result, (list, tuple)):
        return {"type": "list", "size": len(result)}
    return {"type": type(result).__name__}


# ──────────────────────────────────────────────
# Audit record dataclass
# ──────────────────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class CadCommandAuditRecord:
    """단일 CAD agent 명령 audit record.

    raw_text / secret 필드 0건. dataclass 로만 정의 — 본 트랙에서
    파일/DB write 0건.
    """
    commandId: str
    toolId: str
    risk: str  # RiskLevel.value
    status: str  # CommandStatus.value
    approvalStatus: str  # ApprovalStatus.value
    approvalId: Optional[str]
    redactedArgsSummary: Dict[str, Any]
    resultSummary: Dict[str, Any] = field(default_factory=dict)
    createdAt: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commandId": self.commandId,
            "toolId": self.toolId,
            "risk": self.risk,
            "status": self.status,
            "approvalStatus": self.approvalStatus,
            "approvalId": self.approvalId,
            "redactedArgsSummary": dict(self.redactedArgsSummary),
            "resultSummary": dict(self.resultSummary),
            "createdAt": self.createdAt,
        }


def build_audit_record(
    command: CadAgentCommand,
    *,
    result: Any = None,
) -> CadCommandAuditRecord:
    """CadAgentCommand → audit record. result 는 요약만 보존."""
    return CadCommandAuditRecord(
        commandId=command.commandId,
        toolId=command.toolId,
        risk=command.risk.value,
        status=command.status.value,
        approvalStatus=command.approvalStatus.value,
        approvalId=command.approvalId,
        redactedArgsSummary=redact_args(command.args),
        resultSummary=summarize_result(result),
    )


__all__ = [
    "redact_args",
    "redact_value",
    "summarize_result",
    "CadCommandAuditRecord",
    "build_audit_record",
]
