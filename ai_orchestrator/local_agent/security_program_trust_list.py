"""Security Program Trust List — 신뢰된 설치파일 저장소 (in-memory)."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

# 저장 금지 prefix (security_program_install_result_sanitizer와 동일 정책)
_FORBIDDEN_PREFIXES = (
    "password", "otp", "cert_password", "cookie", "session",
    "token", "storage_state", "local_path", "full_path",
    "registry", "npki", "cert_file", "private_key",
)

# 상태
STATUS_ACTIVE = "ACTIVE"
STATUS_REVOKED = "REVOKED"
STATUS_EXPIRED = "EXPIRED"
STATUS_EXHAUSTED = "EXHAUSTED"

_LOCK = threading.Lock()
_TRUST_STORE: dict[str, dict[str, Any]] = {}


def add_trusted_installer(
    source_host: str,
    installer_safe_name: str,
    sha256: str,
    signer_subject: str,
    signature_status: str,
    product_hint: str = "",
    duration_days: int = 90,
    max_reuse_count: int = 50,
) -> dict[str, Any]:
    """신뢰된 설치파일을 trust list에 등록한다."""
    _validate_safe_input(source_host=source_host, installer_safe_name=installer_safe_name)

    if signature_status not in ("Valid",):
        raise ValueError(f"signature_status가 Valid가 아닙니다: {signature_status}")

    now = datetime.now(timezone.utc)
    entry = {
        "trust_id": str(uuid.uuid4()),
        "source_host": source_host,
        "installer_safe_name": _safe_name(installer_safe_name),
        "sha256": sha256.lower(),
        "signer_subject": signer_subject,
        "signature_status": signature_status,
        "product_hint": product_hint,
        "first_approved_at": now.isoformat(),
        "last_used_at": None,
        "expires_at": (now + timedelta(days=duration_days)).isoformat(),
        "max_reuse_count": max_reuse_count,
        "reuse_count": 0,
        "status": STATUS_ACTIVE,
    }
    with _LOCK:
        _TRUST_STORE[entry["trust_id"]] = entry
    return dict(entry)


def find_trusted_installer(
    source_host: str,
    installer_safe_name: str,
    sha256: str,
) -> dict[str, Any] | None:
    """source_host + safe_name + sha256 일치하는 trust 항목 검색."""
    with _LOCK:
        for entry in _TRUST_STORE.values():
            if (entry["source_host"] == source_host
                and entry["installer_safe_name"] == _safe_name(installer_safe_name)
                and entry["sha256"] == sha256.lower()):
                return dict(entry)
    return None


def revoke_trusted_installer(trust_id: str) -> bool:
    with _LOCK:
        entry = _TRUST_STORE.get(trust_id)
        if not entry:
            return False
        entry["status"] = STATUS_REVOKED
        return True


def expire_trusted_installer(trust_id: str) -> bool:
    with _LOCK:
        entry = _TRUST_STORE.get(trust_id)
        if not entry:
            return False
        entry["status"] = STATUS_EXPIRED
        return True


def increment_reuse_count(trust_id: str) -> dict[str, Any] | None:
    with _LOCK:
        entry = _TRUST_STORE.get(trust_id)
        if not entry:
            return None
        entry["reuse_count"] += 1
        entry["last_used_at"] = datetime.now(timezone.utc).isoformat()
        if entry["reuse_count"] >= entry["max_reuse_count"]:
            entry["status"] = STATUS_EXHAUSTED
        return dict(entry)


def validate_trust_scope(
    trust_entry: dict[str, Any],
    source_host: str,
    installer_safe_name: str,
    sha256: str,
    signer_subject: str | None = None,
) -> dict[str, Any]:
    """trust 항목의 적용 범위를 검증한다."""
    if trust_entry.get("status") != STATUS_ACTIVE:
        return _invalid(f"비활성 상태: {trust_entry.get('status')}")

    # 만료 확인
    try:
        expires = datetime.fromisoformat(trust_entry["expires_at"])
        if datetime.now(timezone.utc) > expires:
            return _invalid("만료됨")
    except (KeyError, ValueError):
        return _invalid("expires_at 파싱 오류")

    if trust_entry["source_host"] != source_host:
        return _invalid(f"source_host 불일치 — 차단")

    if trust_entry["sha256"] != sha256.lower():
        return _invalid("hash mismatch — 재승인 또는 차단 필요")

    if trust_entry["installer_safe_name"] != _safe_name(installer_safe_name):
        return _invalid("installer_name 불일치")

    if signer_subject and trust_entry["signer_subject"] != signer_subject:
        return {"valid": False, "reason": "signer mismatch — 재승인 필요",
                "requires_reapproval": True}

    if trust_entry["reuse_count"] >= trust_entry["max_reuse_count"]:
        return _invalid("재사용 한도 초과")

    return {"valid": True, "reason": None, "requires_reapproval": False}


def list_active_trusts() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(e) for e in _TRUST_STORE.values() if e["status"] == STATUS_ACTIVE]


def clear_all() -> None:
    with _LOCK:
        _TRUST_STORE.clear()


def _safe_name(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1]


def _validate_safe_input(**kwargs) -> None:
    for k, v in kwargs.items():
        if not isinstance(v, str):
            continue
        # 경로 구분자 포함 시 거부
        if k == "installer_safe_name" and ("/" in v or "\\" in v):
            raise ValueError(f"installer_safe_name에 경로 구분자 포함 — 거부")
        # 민감 prefix 체크
        for prefix in _FORBIDDEN_PREFIXES:
            if k.lower().startswith(prefix):
                raise ValueError(f"민감 필드 저장 거부: {k}")


def _invalid(reason: str) -> dict[str, Any]:
    return {"valid": False, "reason": reason, "requires_reapproval": False}
