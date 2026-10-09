"""로컬 에이전트 등록·조회·작업 큐 API (Stage 1/2).

엔드포인트:
  POST /api/v1/local-agents/register                    (admin/owner)
  GET  /api/v1/local-agents                             (admin/owner/viewer)
  POST /api/v1/local-agents/{agent_id}/tasks            (admin/owner)
  GET  /api/v1/local-agents/{agent_id}/tasks            (admin/owner/viewer)
  GET  /api/v1/local-agents/{agent_id}/tasks/{task_id}  (admin/owner/viewer)
  WS   /api/v1/local-agents/ws                          (device_token 인증)

작업 흐름:
  - low + 서버 자동완료 (ping/system_info/list_allowed_apps) → status=completed
  - low + PC 의존 (open_url) → status=queued → (WS) delivered → running → completed/failed
  - medium (list_files_readonly) → status=queued → (WS) delivered → running → completed/failed
  - high (capture_screenshot) → issue_token_for_dev_reg + status=waiting_approval
    (Stage 2 에서도 실제 실행은 하지 않음 — 에이전트가 NOT_IMPLEMENTED_STAGE2 반환)

보안:
  - device_token 원문은 register 응답에 1회만 노출
  - params 의 민감 키는 등록 시점에 제거 (registry._strip_sensitive)
  - audit log 에 token 원문 / device_token 원문 절대 기록 금지
  - WS 인증 실패는 로그에 agent_id / 원인 코드만, token 원문은 기록/반영 금지
"""

# ruff: noqa: F401 — 파사드: 분리된 모듈의 이름을 그대로 재노출(테스트·호출처가 이 모듈 속성으로 접근). ruff --fix 가 지우지 않게.
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from .. import audit_builders as _audit
from ..policy import audit_event_policy as _policy
from ..registry import diagnostics as local_agent_diagnostics
from ..registry import facade as _reg
from . import guards as _guards
from ...audit.audit_logger import log_event
from ...auth import registration_codes as _regcodes
from tools.gates.approval import approve_token, issue_token_for_dev_reg, reject_token
from tools.gates.auth import require_role

try:
    from ..user_present_status_handler import (
        handle_user_present_status_event as _handle_up_status_event,
    )

    _UP_STATUS_HANDLER_AVAILABLE = True
except ImportError:
    _UP_STATUS_HANDLER_AVAILABLE = False

try:
    from ..user_present_status_store import (
        get_user_present_status as _get_up_status,
    )
    from ..user_present_status_store import (
        list_user_present_statuses as _list_up_statuses,
    )

    _UP_STATUS_STORE_AVAILABLE = True
except ImportError:
    _UP_STATUS_STORE_AVAILABLE = False

try:
    from ..user_present_dispatcher import (
        build_user_present_dispatch_response,
        should_dispatch_user_present_task,
    )

    _UP_DISPATCHER_AVAILABLE = True
except ImportError:
    _UP_DISPATCHER_AVAILABLE = False

# USER_PRESENT_TASK 전송 대기 큐는 local_agent_router_up_queue(공유 leaf)로 분리. 파사드 재노출.
from .up_queue import _drain_up_tasks, _enqueue_up_task

logger = logging.getLogger(__name__)

local_agent_router = APIRouter(prefix="/local-agents", tags=["local-agents"])


# ── 요청 모델 — local_agent_router_schemas 로 분리(공유 계약). 파사드 재노출 ──
# ── HTTP 라우트 ──────────────────────────────────────────────────────────
# 등록 라우트군은 local_agent_router_registration 으로 분리.
# 컴포지션 루트가 include_router 로 관리(경로 동일).
from .registration import registration_router as _registration_router  # noqa: E402
from .schemas import (  # noqa: E402
    AgentRegisterRequest,
    AgentTaskApprovalRequest,
    AgentTaskRequest,
    BrowserReadonlyInstructionRequest,
    CancelTaskRequest,
    CaptureScreenshotRequest,
    IssueRegistrationCodeRequest,
    RegisterWithCodeRequest,
)

# 검증/감사노트 헬퍼는 local_agent_router_validation(공유 leaf)로 분리. 파사드 재노출.
from .validation import (  # noqa: E402
    _capture_approval_note,
    _validate_readonly_browser_instruction,
)

local_agent_router.include_router(_registration_router)


@local_agent_router.get("")
def list_local_agents(
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    return {"agents": _reg.list_agents()}


# 진단 라우트군(/diagnostics 등 read-only)은 local_agent_router_query 로 분리.
# 컴포지션 루트가 include_router 로 관리(경로 동일).
from .query import query_router as _query_router  # noqa: E402

local_agent_router.include_router(_query_router)


# 브라우저 라우트군은 local_agent_router_browser 로 분리. 컴포지션 루트가 관리.
from .browser import browser_router as _browser_router  # noqa: E402

local_agent_router.include_router(_browser_router)


# 사용자임장 라우트군은 local_agent_router_user_present 로 분리. 컴포지션 루트가 관리.
from .user_present import user_present_router as _user_present_router  # noqa: E402

local_agent_router.include_router(_user_present_router)


# 정리(cleanup) 라우트군은 local_agent_router_cleanup 로 분리. 컴포지션 루트가 관리.
from .cleanup import cleanup_router as _cleanup_router  # noqa: E402

local_agent_router.include_router(_cleanup_router)


from .task import task_router as _task_router  # noqa: E402

local_agent_router.include_router(_task_router)


# WebSocket 엔드포인트는 local_agent_router_ws 로 분리. 컴포지션 루트가 관리.
from .ws import ws_router as _ws_router  # noqa: E402

local_agent_router.include_router(_ws_router)
