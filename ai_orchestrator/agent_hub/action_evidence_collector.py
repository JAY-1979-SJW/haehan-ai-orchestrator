"""Action Evidence Collector — 사후 실행 증거 수집 (민감정보 redaction)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator.agent_hub.action_schemas import all_specs

_SENSITIVE_KEYS = frozenset(
    (
        "password",
        "otp",
        "cert_password",
        "certificate_password",
        "cookie",
        "session",
        "token",
        "storage_state",
        "private_key",
        "npki",
        "auth_header",
        "Authorization",
        "raw_html",
    )
)

_SAFE_FIELDS = (
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
)


def _is_sensitive_key(key: str) -> bool:
    kl = key.lower()
    return any(s in kl for s in _SENSITIVE_KEYS)


def _safe_path(path: str) -> str:
    """파일명만 — full path 노출 차단."""
    if not path:
        return ""
    return path.replace("\\", "/").split("/")[-1]


def _filtered_dict_or(raw_result: dict[str, Any], key: str, fallback_str_len: int | None) -> Any:
    """dict면 민감 키 제거, 아니면 str 앞 N자(없으면 빈 문자열)."""
    val = raw_result.get(key) or {}
    if isinstance(val, dict):
        return {k: v for k, v in val.items() if not _is_sensitive_key(k)}
    return str(val)[:fallback_str_len] if fallback_str_len is not None else ""


def _ev_result_screen_safe(raw_result: dict[str, Any], _shot: str | None) -> Any:
    screen = raw_result.get("result_screen", "")
    if isinstance(screen, str):
        return screen[:300]  # 최대 300자
    return str(screen)[:300]


def _ev_document_hash_safe(raw_result: dict[str, Any], _shot: str | None) -> Any:
    h = raw_result.get("document_hash") or ""
    return h[:16] + "..." if len(h) > 16 else h


def _ev_signer_info_safe(raw_result: dict[str, Any], _shot: str | None) -> Any:
    si = raw_result.get("signer_info") or {}
    if isinstance(si, dict):
        return {"subject_name": si.get("subject_name", "")}
    return ""


def _ev_timestamp(key: str) -> Callable[[dict[str, Any], str | None], Any]:
    return lambda raw_result, _shot: raw_result.get(key) or datetime.now(UTC).isoformat()


# field_name → (raw_result, screenshot_path)로 증거 값을 만드는 함수 (명시적 매핑 테이블)
_EVIDENCE_BUILDERS: dict[str, Callable[[dict[str, Any], str | None], Any]] = {
    "saved_safe_path": lambda r, _s: _safe_path(r.get("saved_path") or r.get("downloaded_path") or ""),
    "result_screen_safe": _ev_result_screen_safe,
    "screenshot_path_safe": lambda r, s: _safe_path(s or r.get("screenshot_path") or ""),
    "form_state_after": lambda r, _s: _filtered_dict_or(r, "form_state_after", 200),
    "preview_state": lambda r, _s: _filtered_dict_or(r, "preview_state", 200),
    "summary_payload": lambda r, _s: _filtered_dict_or(r, "summary_payload", None),
    "downloaded_at": _ev_timestamp("downloaded_at"),
    "attached_at": _ev_timestamp("attached_at"),
    "submitted_at": _ev_timestamp("submitted_at"),
    "signed_at": _ev_timestamp("signed_at"),
    "document_hash_safe": _ev_document_hash_safe,
    "signer_info_safe": _ev_signer_info_safe,
    "bid_payload_preview": lambda r, _s: _filtered_dict_or(r, "bid_payload_preview", None),
}


def collect_evidence(
    action_name: str,
    raw_result: dict[str, Any],
    screenshot_path: str | None = None,
) -> dict[str, Any]:
    """
    실행 결과에서 spec.evidence_fields에 정의된 항목만 추출.
    민감 키는 모두 제거. 7개 safe field 강제 False.
    """
    spec = all_specs().get(action_name)
    if not spec:
        return {
            "action_name": action_name,
            "error": "UNKNOWN_ACTION",
            **dict.fromkeys(_SAFE_FIELDS, False),
        }

    evidence: dict[str, Any] = {}
    for field_name in spec.evidence_fields:
        if _is_sensitive_key(field_name):
            continue

        builder = _EVIDENCE_BUILDERS.get(field_name)
        if builder is not None:
            # 명시적 매핑 (path/url은 안전 변환)
            evidence[field_name] = builder(raw_result, screenshot_path)
        else:
            # 기타 필드 — 민감 키 제외하고 직접 매핑
            v = raw_result.get(field_name)
            if v is not None and not _is_sensitive_key(field_name):
                evidence[field_name] = v

    # safe field 강제 False
    for f in _SAFE_FIELDS:
        evidence[f] = False

    evidence["action_name"] = action_name
    evidence["collected_at"] = datetime.now(UTC).isoformat()
    return evidence


def check_evidence_no_sensitive(evidence: dict[str, Any]) -> list[str]:
    """evidence에 민감 키가 남아있으면 위반 목록 반환.

    7개 safe field(cookie_exported 등 boolean 표시)는 예외 — 값이 False면 OK.
    """
    violations = []
    for k, _v in evidence.items():
        if k in _SAFE_FIELDS:
            continue  # boolean 표시 필드는 별도 처리
        if _is_sensitive_key(k):
            violations.append(f"민감 키 발견: {k}")
    for f in _SAFE_FIELDS:
        if evidence.get(f) is True:
            violations.append(f"safe field 위반: {f} = True")
    return violations
