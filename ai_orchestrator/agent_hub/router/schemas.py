"""local_agent_router 요청 스키마 (공유 계약).

local_agent_router 모듈(컴포지션 루트)에서 분리한 Pydantic 요청 모델군.
라우트 핸들러들이 공유하는 입력 계약만 둔다. 업무 로직/IO 없음.
[MODULE_SEPARATION_STANDARD] 참조: docs/module_separation_standard.md
"""

from __future__ import annotations

from pydantic import BaseModel

from ...auth import registration_codes as _regcodes


class AgentRegisterRequest(BaseModel):
    host: str = ""
    os_name: str = ""
    version: str = "0.1.0"


class AgentTaskRequest(BaseModel):
    action: str
    params: dict = {}


class BrowserReadonlyInstructionRequest(BaseModel):
    instruction: str
    url: str
    wait_until: str = "domcontentloaded"
    timeout_ms: int = 20000
    max_html_chars: int = 100000
    visible_browser: bool = False
    allow_background: bool = True
    keep_open_ms: int = 0
    browser_channel: str = "chromium"


class AgentTaskApprovalRequest(BaseModel):
    token_id: str
    reason: str = ""


class CancelTaskRequest(BaseModel):
    reason: str = ""


class IssueRegistrationCodeRequest(BaseModel):
    label: str
    expires_in_minutes: int = _regcodes.DEFAULT_TTL_MINUTES
    allowed_actions: list[str] = []
    note: str = ""
    smoke_test: bool = False  # smoke test marker for cleanup eligibility


class RegisterWithCodeRequest(BaseModel):
    registration_code: str
    host: str = ""
    os_name: str = ""
    version: str = "0.1.0"


class CaptureScreenshotRequest(BaseModel):
    """운영자 capture_screenshot 요청 body.

    - dry_run 기본값은 True. 생략/빈 body/{} 는 모두 dry_run=True 로 처리.
    - dry_run=False 는 명시적으로 false 를 전달한 경우에만 적용.
    - reason/note 는 감사 메모용 텍스트 (민감값 제거 로직을 거친 뒤 저장).
    """

    dry_run: bool = True
    reason: str = ""
    note: str = ""
