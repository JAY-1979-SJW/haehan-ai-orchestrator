"""Natural Language Task API — 자연어 지시를 agent 실행으로 연결한다."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from core.agent_runtime.runtime.universal.universal_ai_site_agent import run_agent
from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_FAILED,
)
from core.agent_runtime.runtime.universal.user_intent_parser import parse_intent

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]


def _build_page_data_from_url(url: str, fetch_fn: Callable | None = None) -> dict[str, Any]:
    """
    URL만 주어질 때 page_data를 구성한다.
    fetch_fn이 있으면 실제 관찰. 없으면 URL 기반 최소 구조.
    """
    if fetch_fn:
        return fetch_fn(url)

    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    return {
        "url": url,
        "title": host,
        "text_content": "",
        "buttons": [],
        "links": [],
        "form_labels": [],
        "heading_texts": [],
    }


def execute_natural_language_task(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    instruction: str,
    url: str | None = None,
    page_data: dict[str, Any] | None = None,
    permission_map: dict[str, bool] | None = None,
    runner_fn: Callable | None = None,
    page_fetch_fn: Callable | None = None,
    task_id: str | None = None,
    dry_run: bool = False,
    save_learned: bool = True,
) -> dict[str, Any]:
    """
    자연어 지시를 받아 agent를 실행하고 결과를 반환한다.

    Parameters:
        instruction: 자연어 지시문
        url: 현재 페이지 URL (page_data 없을 때 사용)
        page_data: 현재 페이지 관찰 데이터 (있으면 url 무시)
        permission_map: 권한 부여 map {action: bool}
        runner_fn: LOCAL_PLAYWRIGHT action 실행 함수
        page_fetch_fn: URL → page_data 변환 함수 (실제 playwright 관찰)
        task_id: 태스크 ID (없으면 자동 생성)
        dry_run: True이면 AUTO step 목록만 반환 (실행 없음)
        save_learned: 성공 시 learned profile 저장 여부

    Returns:
        universal result dict (safe fields 항상 False)
    """
    if not instruction or not instruction.strip():
        return {
            "status": STATUS_FAILED,
            "message_ko": "지시문이 비어 있습니다.",
            "task_id": task_id or str(uuid.uuid4()),
            **dict.fromkeys(_SAFE_FIELDS, False),
        }

    task_id = task_id or str(uuid.uuid4())

    # page_data 구성
    if page_data is None:
        if url:
            page_data = _build_page_data_from_url(url, page_fetch_fn)
        else:
            return {
                "status": STATUS_FAILED,
                "message_ko": "url 또는 page_data가 필요합니다.",
                "task_id": task_id,
                **dict.fromkeys(_SAFE_FIELDS, False),
            }

    result = run_agent(
        instruction=instruction,
        page_data=page_data,
        permission_map=permission_map,
        runner_fn=runner_fn,
        task_id=task_id,
        dry_run=dry_run,
        save_learned=save_learned,
    )

    # 응답에 intent 정보 추가
    intent_result = parse_intent(instruction)
    result["intent"] = intent_result["intent"]
    result["intent_auto_allowed"] = intent_result["auto_allowed"]
    result["raw_instruction"] = instruction

    # safe fields 강제 보장
    for f in _SAFE_FIELDS:
        result[f] = False

    return result


def build_task_summary(result: dict[str, Any]) -> str:
    """결과를 한글 요약 문자열로 변환."""
    status = result.get("status", "UNKNOWN")
    intent = result.get("intent", "UNKNOWN")
    msg = result.get("message_ko", "")
    actions = result.get("actions_executed", [])
    pending = result.get("actions_pending_permission", [])
    direct = result.get("actions_user_direct_required", [])

    lines = [
        f"[{status}] intent={intent}",
        f"실행된 action: {actions or '없음'}",
    ]
    if pending:
        lines.append(f"권한 필요: {pending}")
    if direct:
        lines.append(f"직접 조작 필요: {direct}")
    if msg:
        lines.append(f"메시지: {msg}")

    return "\n".join(lines)


def check_result_safety(result: dict[str, Any]) -> list[str]:
    """결과의 safe field 위반 여부를 확인한다."""
    violations = []
    for f in _SAFE_FIELDS:
        if result.get(f) is True:
            violations.append(f"{f} = True (위반)")
    return violations
