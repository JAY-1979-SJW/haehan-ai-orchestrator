"""서버 사이드 브라우저 게이트 미들웨어 (4번 보완).

FastAPI 앱에 추가하면 /browser/* 경로의 모든 요청에 대해
action_gate.classify_action()과 동일한 정책을 서버 레벨에서 검사한다.

사용법
======
    from tools.gates.browser_gate_middleware import BrowserGateMiddleware
    app.add_middleware(BrowserGateMiddleware)

동작 방식
=========
- POST /browser/action 요청 body에서 action_type, label, url, params 추출
- classify_action() 호출 → verdict 판정
- APPROVE → 403 + {"verdict": "APPROVE", "category": ..., "approval_url": ...}
  (클라이언트는 approval_server를 통해 승인 획득 후 force=True로 재요청)
- NOTIFY  → 200 통과 + X-Gate-Verdict: NOTIFY 헤더
- AUTO    → 200 통과 (헤더 없음)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_GATE_PATHS = {"/browser/action", "/browser/submit", "/browser/type"}
_APPROVAL_UI = "http://127.0.0.1:7722/"


class BrowserGateMiddleware(BaseHTTPMiddleware):
    """브라우저 자동화 API 요청에 gate 정책 적용."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method != "POST" or request.url.path not in _GATE_PATHS:
            return await call_next(request)

        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes) if body_bytes else {}
        except Exception:  # noqa: BLE001 - 요청 body JSON 파싱 실패 시 빈 dict로 대체 — 이후 action_type/url이 빈 문자열이 되어 classify_action()이 intent 없음으로 판단해 NOTIFY를 반환(AUTO 아님), 실제 액션 실행에 필요한 파싱된 body가 없어 하위 핸들러도 정상 동작 불가 — 승인 우회 아님
            body = {}

        action_type = body.get("action_type", "")
        label = body.get("label", "")
        url = body.get("url", "")
        params = body.get("params") or {}

        # force=True면 승인 완료 신호 → 게이트 통과
        if body.get("force"):
            return await call_next(request)

        from scripts.browser.agent.action_gate import (
            GATE_APPROVE,
            GATE_NOTIFY,
            classify_action,
        )

        result = classify_action(
            action_type=action_type,
            label=label,
            url=url,
            params=params,
        )

        if result.verdict == GATE_APPROVE:
            logger.warning(
                "브라우저 게이트 APPROVE 차단 | action=%s label=%s category=%s",
                action_type,
                label,
                result.category,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "verdict": "APPROVE",
                    "category": result.category,
                    "reason": result.reason,
                    "matched_keyword": result.matched_keyword,
                    "approval_url": _APPROVAL_UI,
                    "message": (
                        f"이 액션은 사용자 승인이 필요합니다. {_APPROVAL_UI} 에서 승인 후 force=true로 재요청하세요."
                    ),
                },
            )

        # NOTIFY: 통과하되 헤더로 알림
        async def _body_receiver():
            return body_bytes

        request._body = body_bytes  # starlette body 재주입
        response = await call_next(request)

        if result.verdict == GATE_NOTIFY:
            response.headers["X-Gate-Verdict"] = "NOTIFY"
            response.headers["X-Gate-Reason"] = result.reason[:200]

        return response
