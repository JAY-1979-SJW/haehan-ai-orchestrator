"""AI 브라우저 에이전트 (/api/v1/browser-agent).

사용자 PC의 로그인된 로컬 CDP 브라우저를 AI가 운전해 지시를 수행한다.
서버 헤드리스가 아니라 '진짜 로그인된 로컬 브라우저'라 봇탐지/로그인 벽을 통과.

안전: 결제/구매/삭제/발송/제출 등 파괴적 클릭은 에이전트가 차단 → 승인 필요로 중단.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit_logger import log_event
from ..auth import require_role

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

browser_agent_router = APIRouter(prefix="/browser-agent", tags=["browser-agent"])


class AgentTaskRequest(BaseModel):
    instruction: str
    url: str | None = None  # 시작 URL(선택)
    max_steps: int = 12


@browser_agent_router.post("/run")
def run_task(body: AgentTaskRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """AI가 로컬 CDP 브라우저를 운전해 지시를 수행.

    파괴적 동작(결제/삭제/발송 등)은 차단되며 blocked=true 로 반환된다.
    """
    if not (body.instruction or "").strip():
        raise HTTPException(status_code=400, detail="지시(instruction)가 필요합니다")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from scripts.browser_agent.agent import run_browser_task
        from scripts.web_connector import get_domain_page, get_page, run_on_browser_thread

        _url = (body.url or "").strip() or None

        # 동일 도메인은 하나의 탭만(url 있을 때). Playwright(sync)는 단일 전용 스레드에서.
        def _do() -> dict:
            return run_browser_task(
                get_domain_page(_url) if _url else get_page(),
                instruction=body.instruction.strip(),
                start_url=_url,
                max_steps=max(1, min(body.max_steps, 25)),
            )

        result = run_on_browser_thread(_do, timeout=240)
    except Exception as e:
        logger.exception("browser agent error")
        raise HTTPException(status_code=500, detail=f"에이전트 실행 실패: {e}")

    log_event(
        "BROWSER_AGENT_RUN",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="blocked" if result.get("blocked") else ("ok" if result.get("ok") else "error"),
        note=f"steps={len(result.get('steps', []))} instr={body.instruction[:40]}",
    )
    return result
