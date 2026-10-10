"""browser.prepare_submit — 제출 직전 폼 상태 검증 + 요약 생성 (실제 제출 X).

- AUTO_ALLOWED: 사용자 승인 불필요
- 사전 제출 정보 검증
- 제출 요약 생성 (사용자 리뷰용)
- 실제 제출 버튼 클릭 안 함
- 쿠키/session/storage_state 추출 안 함
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.agent_hub.action_evidence_collector import collect_evidence
from ai_orchestrator.agent_hub.action_registry import register_handler

ACTION_NAME = "browser.prepare_submit"


def execute(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    page_url: str,
    page_title: str = "",
    submit_selector: str = "",
    submit_button_text: str = "",
    form_summary: str = "",
    attached_files: list[str] | None = None,
    target_site: str = "",
    target_title: str = "",
    target_id: str = "",
    organization_name: str = "",
    amount: str = "",
    due_date: str = "",
    risk_notes: str = "",
    timeout_seconds: int = 30,
    headless: bool = True,
) -> dict[str, Any]:
    """
    제출 직전 폼 상태 캡처 + 요약 빌드.

    1. page_url 검증 (host+path만 사용)
    2. submit_selector 존재 여부 확인 (없으면 WARN)
    3. 첨부파일 리스트 확인 (파일명만 사용)
    4. 사전 요약 생성 (제출 항목/금액/기관명/마감일 등)
    5. 민감 필드(password/otp/cert_password/cookie 등) 포함 시 차단
    6. 사후 액션: browser.submit_with_user_approval 안내
    """
    if not page_url:
        return {"ok": False, "verdict": "ERROR", "error": "page_url 필요"}

    try:
        parsed_url = urlparse(page_url)
        safe_url = f"{parsed_url.scheme}://{parsed_url.hostname or ''}{parsed_url.path or ''}"
    except Exception:  # noqa: BLE001 - 감사로그 표시용 safe_url 생성 실패 시 '(invalid_url)' 플레이스홀더 사용 — 승인 토큰 검증 등 실제 게이트 판정과 무관, 로그 표시 전용
        safe_url = "(invalid_url)"

    # 첨부파일 안전명 (파일명만)
    safe_files = []
    if attached_files:
        for f in attached_files:
            if f:
                safe_files.append(Path(f).name)

    # 민감 필드 확인 (input params에서)
    sensitive_keys = _find_sensitive_keys(
        {
            "form_summary": form_summary,
            "risk_notes": risk_notes,
        }
    )
    if sensitive_keys:
        return {
            "ok": False,
            "verdict": "BLOCKED_SENSITIVE",
            "error": f"민감 파라미터 포함: {sensitive_keys}",
            "warnings": [f"입력 파라미터에 민감 정보: {sensitive_keys}"],
        }

    raw: dict[str, Any] = {
        "verdict": "PREPARE_SUCCESS",
        "page_url_safe": safe_url,
        "page_title": page_title or "(no title)",
        "submit_selector": submit_selector,
        "submit_button_text": submit_button_text or "Submit",
        "form_summary": form_summary or "(no form summary)",
        "attached_files_safe": safe_files,
        "target_site": target_site or "(no target)",
        "target_title": target_title or "(no title)",
        "target_id": target_id or "(no id)",
        "organization_name": organization_name or "(no org)",
        "amount": amount or "(no amount)",
        "due_date": due_date or "(no deadline)",
        "prepared_at": datetime.now(UTC).isoformat(),
    }

    # 경고: selector 없음
    warnings = []
    if not submit_selector:
        warnings.append("submit_selector 미정의 — 제출 실패 가능성")
        raw["verdict"] = "PREPARE_WARN"

    if warnings:
        raw["warnings"] = warnings

    raw["ok"] = True
    evidence = collect_evidence(ACTION_NAME, raw)
    raw["evidence"] = evidence

    return raw


def _find_sensitive_keys(data: dict[str, Any]) -> list[str]:
    """민감 키 감지."""
    sensitive_hints = ("password", "otp", "cert_password", "cookie", "session", "token", "private_key", "npki")
    found = []
    for k, v in data.items():
        if not v:
            continue
        kl = k.lower()
        if any(s in kl for s in sensitive_hints):
            found.append(k)
        if isinstance(v, str):
            vl = v.lower()
            if "password" in vl or "otp" in vl or "cert_password" in vl:
                found.append(f"{k}(content)")
    return found


# registry 등록
register_handler(ACTION_NAME, execute)
