"""local_agent 라우트 공유 검증/감사노트 헬퍼 (공유 leaf).

여러 라우트군(browser-instruction, capture, task)이 공유하는 입력 검증과
감사 note 축약 로직. 라우트/상태 없음. 공유 계약(schemas)만 import.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import HTTPException

from .schemas import BrowserReadonlyInstructionRequest

logger = logging.getLogger(__name__)


def _capture_approval_note(task, agent_id: str, dry_run: bool) -> str:
    """CAPTURE_SCREENSHOT_APPROVAL_REQUESTED audit 용 note — reason/note 축약 포함.

    token 원문 / 파일명 / 전체 경로는 포함하지 않는다. reason/note 는 이미
    enqueue_task 단계에서 민감값 제거 후 저장되며, 본 함수는 추가 축약만 한다.
    """
    parts = [f"agent_id={agent_id}", f"dry_run={dry_run}"]
    try:
        params = task.params if task is not None else None
    except Exception as exc:  # noqa: BLE001 - 감사 note 축약용 헬퍼 - task.params 접근 실패 시 None 처리 후 reason/note 생략, 승인/차단 판정과 무관
        logger.debug("감사 note 용 task.params 읽기 실패: %s", type(exc).__name__)
        params = None
    if isinstance(params, dict):
        raw_reason = params.get("reason")
        if raw_reason:
            parts.append(f"reason={str(raw_reason)[:100]}")
        raw_note = params.get("note")
        if raw_note:
            parts.append(f"note={str(raw_note)[:100]}")
    return " ".join(parts)


_READONLY_WAIT_UNTIL_VALUES: frozenset[str] = frozenset(
    {
        "domcontentloaded",
        "load",
        "networkidle",
    }
)

_UNSAFE_BROWSER_INSTRUCTION_TERMS: frozenset[str] = frozenset(
    {
        "click",
        "submit",
        "type",
        "input",
        "login",
        "sign in",
        "password",
        "otp",
        "2fa",
        "pay",
        "purchase",
        "buy",
        "send",
        "transfer",
        "delete",
        "remove",
        "download",
        "upload",
        "save",
        "register",
        "create account",
        "approve",
        "confirm",
        "checkout",
        "클릭",
        "제출",
        "입력",
        "로그인",
        "비밀번호",
        "패스워드",
        "인증번호",
        "결제",
        "구매",
        "송금",
        "전송",
        "삭제",
        "다운로드",
        "업로드",
        "저장",
        "등록",
        "가입",
        "승인",
        "확인",
        "체크아웃",
    }
)


def _validate_readonly_browser_instruction(
    body: BrowserReadonlyInstructionRequest,
) -> tuple[str, str, str, int, int, int, str]:
    instruction = str(body.instruction or "").strip()
    if not instruction:
        raise HTTPException(
            status_code=400,
            detail={"error": "EMPTY_BROWSER_INSTRUCTION"},
        )
    if len(instruction) > 500:
        raise HTTPException(
            status_code=400,
            detail={"error": "BROWSER_INSTRUCTION_TOO_LONG"},
        )

    lowered = instruction.lower()
    blocked = next(
        (term for term in _UNSAFE_BROWSER_INSTRUCTION_TERMS if term in lowered),
        "",
    )
    if blocked:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UNSAFE_BROWSER_INSTRUCTION",
                "message": "readonly browser instructions cannot request input, auth, downloads, or state changes",
            },
        )

    url = str(body.url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_BROWSER_URL"},
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail={"error": "URL_CREDENTIALS_NOT_ALLOWED"},
        )

    wait_until = str(body.wait_until or "domcontentloaded").strip()
    if wait_until not in _READONLY_WAIT_UNTIL_VALUES:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_WAIT_UNTIL"},
        )

    timeout_ms = max(1000, min(int(body.timeout_ms), 30000))
    max_html_chars = max(1000, min(int(body.max_html_chars), 100000))
    keep_open_ms = max(0, min(int(body.keep_open_ms), 30000))
    browser_channel = str(body.browser_channel or "chromium").strip().lower()
    if browser_channel not in {"chromium", "chrome", "msedge"}:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_BROWSER_CHANNEL"},
        )
    host = parsed.hostname or parsed.netloc
    return instruction, url, host, timeout_ms, max_html_chars, keep_open_ms, browser_channel
