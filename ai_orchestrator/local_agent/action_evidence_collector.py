"""Action Evidence Collector — 사후 실행 증거 수집 (민감정보 redaction)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_orchestrator.local_agent.action_schemas import all_specs

_SENSITIVE_KEYS = frozenset((
    "password", "otp", "cert_password", "certificate_password",
    "cookie", "session", "token", "storage_state", "private_key",
    "npki", "auth_header", "Authorization", "raw_html",
))

_SAFE_FIELDS = (
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
)


def _is_sensitive_key(key: str) -> bool:
    kl = key.lower()
    return any(s in kl for s in _SENSITIVE_KEYS)


def _safe_path(path: str) -> str:
    """파일명만 — full path 노출 차단."""
    if not path:
        return ""
    return path.replace("\\", "/").split("/")[-1]


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
            **{f: False for f in _SAFE_FIELDS},
        }

    evidence: dict[str, Any] = {}
    for field_name in spec.evidence_fields:
        if _is_sensitive_key(field_name):
            continue

        # 명시적 매핑 (path/url은 안전 변환)
        if field_name == "saved_safe_path":
            evidence[field_name] = _safe_path(raw_result.get("saved_path") or raw_result.get("downloaded_path") or "")
        elif field_name == "result_screen_safe":
            screen = raw_result.get("result_screen", "")
            if isinstance(screen, str):
                evidence[field_name] = screen[:300]  # 최대 300자
            else:
                evidence[field_name] = str(screen)[:300]
        elif field_name == "screenshot_path_safe":
            evidence[field_name] = _safe_path(screenshot_path or raw_result.get("screenshot_path") or "")
        elif field_name == "form_state_after":
            fs = raw_result.get("form_state_after") or {}
            if isinstance(fs, dict):
                evidence[field_name] = {k: v for k, v in fs.items() if not _is_sensitive_key(k)}
            else:
                evidence[field_name] = str(fs)[:200]
        elif field_name == "preview_state":
            ps = raw_result.get("preview_state") or {}
            if isinstance(ps, dict):
                evidence[field_name] = {k: v for k, v in ps.items() if not _is_sensitive_key(k)}
            else:
                evidence[field_name] = str(ps)[:200]
        elif field_name == "summary_payload":
            sp = raw_result.get("summary_payload") or {}
            if isinstance(sp, dict):
                evidence[field_name] = {k: v for k, v in sp.items() if not _is_sensitive_key(k)}
            else:
                evidence[field_name] = ""
        elif field_name == "downloaded_at":
            evidence[field_name] = raw_result.get("downloaded_at") or datetime.now(timezone.utc).isoformat()
        elif field_name == "attached_at":
            evidence[field_name] = raw_result.get("attached_at") or datetime.now(timezone.utc).isoformat()
        elif field_name == "submitted_at":
            evidence[field_name] = raw_result.get("submitted_at") or datetime.now(timezone.utc).isoformat()
        elif field_name == "signed_at":
            evidence[field_name] = raw_result.get("signed_at") or datetime.now(timezone.utc).isoformat()
        elif field_name == "document_hash_safe":
            h = raw_result.get("document_hash") or ""
            evidence[field_name] = h[:16] + "..." if len(h) > 16 else h
        elif field_name == "signer_info_safe":
            si = raw_result.get("signer_info") or {}
            if isinstance(si, dict):
                evidence[field_name] = {"subject_name": si.get("subject_name", "")}
            else:
                evidence[field_name] = ""
        elif field_name == "bid_payload_preview":
            bp = raw_result.get("bid_payload_preview") or {}
            if isinstance(bp, dict):
                evidence[field_name] = {k: v for k, v in bp.items() if not _is_sensitive_key(k)}
            else:
                evidence[field_name] = ""
        else:
            # 기타 필드 — 민감 키 제외하고 직접 매핑
            v = raw_result.get(field_name)
            if v is not None and not _is_sensitive_key(field_name):
                evidence[field_name] = v

    # safe field 강제 False
    for f in _SAFE_FIELDS:
        evidence[f] = False

    evidence["action_name"] = action_name
    evidence["collected_at"] = datetime.now(timezone.utc).isoformat()
    return evidence


def check_evidence_no_sensitive(evidence: dict[str, Any]) -> list[str]:
    """evidence에 민감 키가 남아있으면 위반 목록 반환.

    7개 safe field(cookie_exported 등 boolean 표시)는 예외 — 값이 False면 OK.
    """
    violations = []
    for k, v in evidence.items():
        if k in _SAFE_FIELDS:
            continue  # boolean 표시 필드는 별도 처리
        if _is_sensitive_key(k):
            violations.append(f"민감 키 발견: {k}")
    for f in _SAFE_FIELDS:
        if evidence.get(f) is True:
            violations.append(f"safe field 위반: {f} = True")
    return violations
