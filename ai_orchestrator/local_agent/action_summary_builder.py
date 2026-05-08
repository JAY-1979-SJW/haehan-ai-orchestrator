"""Action Summary Builder — 사용자 사전 review용 요약."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.local_agent.action_schemas import all_specs

_SENSITIVE_PARAM_KEYS = frozenset((
    "password", "otp", "cert_password", "certificate_password",
    "cookie", "session", "token", "storage_state", "private_key",
    "npki", "auth_header", "Authorization",
))


def _safe_url(url: str, length: int = 80) -> str:
    """URL — host + path만 노출."""
    if not url:
        return ""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.hostname or ''}{p.path or ''}"[:length]
    except Exception:
        return "(invalid_url)"


def _safe_path(path: str) -> str:
    """파일명만 노출."""
    if not path:
        return ""
    return path.replace("\\", "/").split("/")[-1]


def _is_sensitive(key: str) -> bool:
    kl = key.lower()
    return any(s in kl for s in _SENSITIVE_PARAM_KEYS)


def build_action_summary(action_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    액션 스펙의 summary_fields에 정의된 필드만 노출.
    URL은 host+path만, 파일은 파일명만, 민감 필드는 제외.
    """
    spec = all_specs().get(action_name)
    if not spec:
        return {
            "action_name": action_name,
            "error": "UNKNOWN_ACTION",
            "summary": {},
        }

    summary: dict[str, Any] = {}
    for field_name in spec.summary_fields:
        # 민감 필드는 무시 (방어)
        if _is_sensitive(field_name):
            continue

        # 명시적 매핑
        if field_name == "source_url_safe":
            summary[field_name] = _safe_url(params.get("source_url") or params.get("url") or "")
        elif field_name == "expected_filename":
            summary[field_name] = _safe_path(params.get("expected_filename") or params.get("file_name") or "")
        elif field_name == "site":
            url = params.get("url") or params.get("site_url") or params.get("source_url") or ""
            try:
                summary[field_name] = (urlparse(url).hostname or "") if url else params.get("site", "")
            except Exception:
                summary[field_name] = ""
        elif field_name == "file_name":
            summary[field_name] = _safe_path(params.get("file_name") or params.get("attach_file") or "")
        elif field_name == "form_field_label":
            summary[field_name] = params.get("form_field_label") or params.get("input_label") or ""
        elif field_name == "file_size":
            summary[field_name] = params.get("file_size") or 0
        elif field_name == "file_signature":
            summary[field_name] = params.get("file_signature") or ""
        elif field_name == "expected_result":
            summary[field_name] = params.get("expected_result") or ""
        elif field_name == "notice_no":
            summary[field_name] = params.get("notice_no") or params.get("bid_ntce_no") or ""
        elif field_name == "amount":
            summary[field_name] = params.get("amount") or params.get("bid_amount") or ""
        elif field_name == "company":
            summary[field_name] = params.get("company") or params.get("company_name") or ""
        elif field_name == "account":
            # 계정 ID/이메일만 (비밀번호 절대 X)
            summary[field_name] = params.get("account_id") or params.get("user_id") or ""
        elif field_name == "deadline":
            summary[field_name] = params.get("deadline") or ""
        elif field_name == "form_summary":
            summary[field_name] = params.get("form_summary") or {}
        elif field_name == "bid_amount" or field_name == "bid_amount_summary":
            summary[field_name] = params.get("bid_amount") or 0
        elif field_name == "document_summary":
            summary[field_name] = params.get("document_summary") or ""
        elif field_name == "document_name":
            summary[field_name] = _safe_path(params.get("document_name") or "")
        elif field_name == "document_hash_safe":
            h = params.get("document_hash") or ""
            summary[field_name] = h[:16] + "..." if len(h) > 16 else h
        elif field_name == "signer_info_safe":
            # 서명자 정보 — 인증서 본인명만 (비밀번호/시리얼 X)
            si = params.get("signer_info") or {}
            if isinstance(si, dict):
                summary[field_name] = {
                    "subject_name": si.get("subject_name", ""),
                }
            else:
                summary[field_name] = ""
        elif field_name == "purpose":
            summary[field_name] = params.get("purpose") or ""
        else:
            # 일반 필드는 직접 매핑 (단, 민감하지 않은 경우만)
            v = params.get(field_name)
            if v is not None and not _is_sensitive(field_name):
                summary[field_name] = v

    return {
        "action_name": action_name,
        "risk_grade": spec.risk_grade,
        "requires_user_approval": spec.requires_user_approval,
        "summary": summary,
        "fields_count": len(summary),
    }


def format_summary_for_display(summary_result: dict[str, Any]) -> str:
    """사용자에게 보여줄 텍스트 포맷."""
    lines = []
    lines.append(f"=== 액션 요약: {summary_result.get('action_name')} ===")
    lines.append(f"위험 등급: {summary_result.get('risk_grade')}")
    lines.append(f"사용자 승인 필요: {summary_result.get('requires_user_approval')}")
    lines.append("--- 실행 내용 ---")
    for k, v in summary_result.get("summary", {}).items():
        lines.append(f"  {k}: {v}")
    lines.append("--- 위 내용을 확인하고 승인할지 결정해 주세요 ---")
    return "\n".join(lines)
