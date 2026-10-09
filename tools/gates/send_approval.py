"""외부 발송 라우터 공통 — scripts.common.gate.require_side_effect 의 FastAPI 어댑터(GateBlocked → HTTP 403).

승인 문구는 사용자가 확인 단계에서 직접 입력한 값이어야 한다(코드·화면에 고정해 자동 전송 금지). 발송 호출·브라우저 조작
이전에 부르고, 수신거부 목록과 대조한다. 발송 건수는 제한하지 않는다.
"""

from __future__ import annotations

from email.utils import getaddresses

from fastapi import HTTPException

from tools.gates.gate_core import GateBlocked, require_side_effect


def addresses(header_value: str) -> list[str]:
    """'Name <a@b.c>, d@e.f' 형태의 수신자 값에서 주소만 뽑는다(수신거부 대조용)."""
    return [addr for _, addr in getaddresses([header_value]) if addr]


def require_send_approval(
    op_name: str,
    *,
    send_confirm: str | None,
    expected: str,
    recipients: list[str] | None = None,
    **meta: str,
) -> None:
    """승인 문구 + 수신거부 검사. 막히면 HTTP 403(detail 에 필요한 문구 안내)."""
    try:
        require_side_effect(op_name, approval=send_confirm, expected=expected, recipient=recipients, **meta)
    except GateBlocked as exc:
        raise HTTPException(
            status_code=403,
            # 승인 문구 자체는 응답에 담지 않는다 — 사람이 아는 통로는 화면 모달 안내와 CLI --help 뿐이다.
            detail=f"발송 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)",
        ) from exc
