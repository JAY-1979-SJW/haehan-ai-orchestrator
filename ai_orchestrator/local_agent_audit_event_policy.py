"""로컬 에이전트 감사 이벤트 정책 및 응답 빌더.

승인/거절 엔드포인트의 감사 이벤트 타입과 HTTP 상태 코드 매핑,
audit 노트 생성 로직을 중앙화한다.
"""
from __future__ import annotations

# ── 승인/거절 엔드포인트 HTTP 상태 코드 매핑 ────────────────────────────────────────

APPROVE_STATUS_HTTP = {
    "approved": 200,
    "not_found": 404,
    "task_mismatch": 400,
    "already_used": 409,
    "expired": 410,
    "forbidden": 403,
    "rate_limited": 429,
}

REJECT_STATUS_HTTP = {
    "rejected": 200,
    "not_found": 404,
    "task_mismatch": 400,
    "already_used": 409,
    "expired": 410,
    "forbidden": 403,
    "rate_limited": 429,
}


# ── 감사 이벤트 타입 매핑 ────────────────────────────────────────────────────────────

APPROVE_AUDIT_EVENT = {
    "approved": "LOCAL_AGENT_TASK_APPROVED",
    "not_found": "APPROVAL_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "LOCAL_AGENT_TASK_APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_DENIED",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}

REJECT_AUDIT_EVENT = {
    "rejected": "LOCAL_AGENT_TASK_REJECTED_BY_APPROVER",
    "not_found": "APPROVAL_REJECT_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_REJECT_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "LOCAL_AGENT_TASK_APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_REJECT_FORBIDDEN",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}


# ── HTTP 에러 응답 생성 헬퍼 ────────────────────────────────────────────────────────

def make_approval_error_detail(status: str, status_code_map: dict | None = None, event_map: dict | None = None) -> tuple[int, dict]:
    """승인 실패 응답 생성.

    Returns: (http_status_code, detail_dict)
    """
    if status_code_map is None:
        status_code_map = APPROVE_STATUS_HTTP
    http_code = status_code_map.get(status, 400)
    return http_code, {"error": status.upper(), "status": status}


def make_rejection_error_detail(status: str, status_code_map: dict | None = None, event_map: dict | None = None) -> tuple[int, dict]:
    """거절 실패 응답 생성.

    Returns: (http_status_code, detail_dict)
    """
    if status_code_map is None:
        status_code_map = REJECT_STATUS_HTTP
    http_code = status_code_map.get(status, 400)
    return http_code, {"error": status.upper(), "status": status}
