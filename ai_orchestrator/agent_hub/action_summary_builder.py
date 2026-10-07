"""Action Summary Builder — 사용자 사전 review용 요약."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.agent_hub.action_schemas import all_specs

_SENSITIVE_PARAM_KEYS = frozenset(
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
    )
)


def _safe_url(url: str, length: int = 80) -> str:
    """URL — host + path만 노출."""
    if not url:
        return ""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.hostname or ''}{p.path or ''}"[:length]
    except Exception:  # noqa: BLE001 - 액션 요약 로그 생성 -- URL/경로 값을 요약용으로 안전하게 축약, 파싱 실패 시 빈 문자열/자리표시자로 대체(민감정보 노출 방지 목적)
        return "(invalid_url)"


def _safe_path(path: str) -> str:
    """파일명만 노출."""
    if not path:
        return ""
    return path.replace("\\", "/").split("/")[-1]


def _is_sensitive(key: str) -> bool:
    kl = key.lower()
    return any(s in kl for s in _SENSITIVE_PARAM_KEYS)


def _summary_site(params: dict[str, Any]) -> Any:
    url = params.get("url") or params.get("site_url") or params.get("source_url") or ""
    try:
        return (urlparse(url).hostname or "") if url else params.get("site", "")
    except Exception:  # noqa: BLE001 - 액션 요약 로그 생성 -- URL/경로 값을 요약용으로 안전하게 축약, 파싱 실패 시 빈 문자열/자리표시자로 대체(민감정보 노출 방지 목적)
        return ""


def _summary_document_hash_safe(params: dict[str, Any]) -> Any:
    h = params.get("document_hash") or ""
    return h[:16] + "..." if len(h) > 16 else h


def _summary_signer_info_safe(params: dict[str, Any]) -> Any:
    # 서명자 정보 — 인증서 본인명만 (비밀번호/시리얼 X)
    si = params.get("signer_info") or {}
    if isinstance(si, dict):
        return {
            "subject_name": si.get("subject_name", ""),
        }
    return ""


# field_name → params에서 요약 값을 만드는 함수 (명시적 매핑 테이블)
_FIELD_BUILDERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "source_url_safe": lambda p: _safe_url(p.get("source_url") or p.get("url") or ""),
    "expected_filename": lambda p: _safe_path(p.get("expected_filename") or p.get("file_name") or ""),
    "site": _summary_site,
    "file_name": lambda p: _safe_path(p.get("file_name") or p.get("attach_file") or ""),
    "form_field_label": lambda p: p.get("form_field_label") or p.get("input_label") or "",
    "file_size": lambda p: p.get("file_size") or 0,
    "file_signature": lambda p: p.get("file_signature") or "",
    "expected_result": lambda p: p.get("expected_result") or "",
    "notice_no": lambda p: p.get("notice_no") or p.get("bid_ntce_no") or "",
    "amount": lambda p: p.get("amount") or p.get("bid_amount") or "",
    "company": lambda p: p.get("company") or p.get("company_name") or "",
    # 계정 ID/이메일만 (비밀번호 절대 X)
    "account": lambda p: p.get("account_id") or p.get("user_id") or "",
    "deadline": lambda p: p.get("deadline") or "",
    "form_summary": lambda p: p.get("form_summary") or {},
    "bid_amount": lambda p: p.get("bid_amount") or 0,
    "bid_amount_summary": lambda p: p.get("bid_amount") or 0,
    "document_summary": lambda p: p.get("document_summary") or "",
    "document_name": lambda p: _safe_path(p.get("document_name") or ""),
    "document_hash_safe": _summary_document_hash_safe,
    "signer_info_safe": _summary_signer_info_safe,
    "purpose": lambda p: p.get("purpose") or "",
}


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

        builder = _FIELD_BUILDERS.get(field_name)
        if builder is not None:
            # 명시적 매핑
            summary[field_name] = builder(params)
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
