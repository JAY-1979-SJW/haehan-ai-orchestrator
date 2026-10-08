"""Tenant scope contracts for organization-based data separation.

TENANT-2: Minimal Organization Scope Contracts

이 모듈은 runtime enforcement가 아니라 contract/helper 수준의 타입과 검증 함수를 제공한다.

정의 범위:
- AuthTenantContext: 인증된 user의 조직별 권한
- Scope contracts: User, Organization, Membership, LocalAgent, BrowserTask, etc.
- Validation helpers: organization scope validation
- Safe dict: 민감정보 제거

금지:
- DB 접속
- 실제 role 조회 (향후 구현)
- secret 저장
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================================
# Auth Context (G1, G4)
# ============================================================================


@dataclass
class AuthTenantContext:
    """인증된 사용자의 조직별 권한 정보.

    G1: User model에 user_id 필요
    G4: Auth에 organization_ids 반환 필요
    """

    actor_user_id: str
    """UUID: 전역적으로 고유한 사용자 ID"""

    actor_email: str = ""
    """Optional: 사용자 이메일 (로그인용)"""

    actor_role: str = ""
    """현재 active_organization에서의 role
    (owner|admin|manager|operator|viewer|auditor|local_agent)
    """

    organization_ids: list[str] = field(default_factory=list)
    """사용자가 소속된 모든 조직 ID"""

    active_organization_id: str = ""
    """현재 활성 조직 ID (organization_ids에 포함되어야 함)"""

    is_local_agent: bool = False
    """local agent로 접속했는지 여부"""

    agent_id: str | None = None
    """agent로 접속한 경우에만 유입"""

    def __post_init__(self):
        """최소 요구사항 검증"""
        validate_auth_context(self)

    def has_access_to_organization(self, org_id: str) -> bool:
        """해당 조직에 접근 권한이 있는지 확인"""
        return org_id in self.organization_ids

    def require_access_to_organization(self, org_id: str) -> None:
        """해당 조직 접근 권한 필수, 없으면 raise ValueError"""
        if not self.has_access_to_organization(org_id):
            raise ValueError(f"User {self.actor_user_id} has no access to organization {org_id}")

    def can_perform_action(self, action: str, org_id: str) -> bool:
        """특정 조직에서 action 가능 여부 (향후 permission matrix 확장)"""
        return self.has_access_to_organization(org_id)


def validate_auth_context(ctx: AuthTenantContext) -> None:
    """Auth context 최소 요구사항 검증"""
    if not ctx.actor_user_id:
        raise ValueError("actor_user_id required")
    if not ctx.organization_ids:
        raise ValueError("organization_ids required (at least 1)")
    if not ctx.active_organization_id:
        raise ValueError("active_organization_id required")
    if ctx.active_organization_id not in ctx.organization_ids:
        raise ValueError(
            f"active_organization_id {ctx.active_organization_id} not in organization_ids {ctx.organization_ids}"
        )


def require_active_organization(ctx: AuthTenantContext) -> str:
    """active_organization_id 필수, 없으면 raise"""
    validate_auth_context(ctx)
    return ctx.active_organization_id


def require_membership(ctx: AuthTenantContext, org_id: str) -> None:
    """특정 조직 membership 필수"""
    if not ctx.has_access_to_organization(org_id):
        raise ValueError(f"User {ctx.actor_user_id} not member of organization {org_id}")


# ============================================================================
# Core Entity Scope Contracts
# ============================================================================


@dataclass
class LocalAgentScope:
    """로컬 에이전트 조직 범위 계약.

    G10: LocalAgent model에 organization_id 필수
    """

    agent_id: str
    organization_id: str
    """G10: Required - agent belongs to exactly one organization"""

    registered_by_user_id: str | None = None
    host_name_hash: str = ""
    """SHA256(hostname)[:12] - never raw hostname"""

    agent_version: str = ""
    capabilities: list[str] = field(default_factory=list)
    status: str = "ready"

    def __post_init__(self):
        if not self.organization_id:
            raise ValueError("LocalAgent requires organization_id (G10)")
        if self.host_name_hash and "hostname=" in self.host_name_hash.lower():
            raise ValueError("raw hostname not allowed; use host_name_hash")
        if not self.capabilities:
            self.capabilities = []

    def safe_dict(self) -> dict:
        """Safe representation (no secrets)"""
        return {
            "agent_id": self.agent_id,
            "organization_id": self.organization_id,
            "host_name_hash": self.host_name_hash,
            "agent_version": self.agent_version,
            "capabilities": self.capabilities,
            "status": self.status,
        }


@dataclass
class BrowserTaskScope:
    """브라우저 태스크 조직 범위 계약.

    G5: BrowserTask model에 organization_id 필수
    """

    task_id: str
    organization_id: str
    """G5: Required - task belongs to exactly one organization"""

    requested_by_user_id: str
    agent_id: str | None = None
    action_type: str = ""
    risk_level: str = "low"
    status: str = "pending"

    def __post_init__(self):
        if not self.organization_id:
            raise ValueError("BrowserTask requires organization_id (G5)")
        if not self.requested_by_user_id:
            raise ValueError("BrowserTask requires requested_by_user_id")


@dataclass
class BrowserApprovalScope:
    """브라우저 승인 조직 범위 계약.

    G6: BrowserApproval model에 organization_id 필수
    """

    approval_id: str
    task_id: str
    organization_id: str
    """G6: Required - must match task.organization_id"""

    requested_by_user_id: str
    approved_by_user_id: str | None = None
    risk_level: str = ""
    status: str = "pending"
    approval_token_hash: str = ""
    """SHA256 hash only, never plaintext token"""

    def __post_init__(self):
        if not self.organization_id:
            raise ValueError("BrowserApproval requires organization_id (G6)")
        if not self.approval_token_hash:
            raise ValueError("BrowserApproval requires approval_token_hash (not plaintext)")
        # Simple check: token should be hash format, not plaintext
        if "approval_token=" in self.approval_token_hash or self.approval_token_hash.startswith("token:"):
            raise ValueError("plaintext approval_token not allowed; use SHA256 hash")


@dataclass
class BrowserResultScope:
    """브라우저 결과 조직 범위 계약.

    G7: BrowserResult model에 organization_id 필수
    """

    result_id: str
    task_id: str
    organization_id: str
    """G7: Required - must match task.organization_id"""

    agent_id: str | None = None
    status: str = "completed"

    def __post_init__(self):
        if not self.organization_id:
            raise ValueError("BrowserResult requires organization_id (G7)")
        if not self.task_id:
            raise ValueError("BrowserResult requires task_id")


@dataclass
class BrowserAuditEventScope:
    """브라우저 감사 이벤트 조직 범위 계약.

    G8: BrowserAuditEvent factory에 organization_id 필수 (browser task 관련)
    """

    event_id: str
    event_type: str
    """BROWSER_TASK_*, BROWSER_APPROVAL_*, etc."""

    task_id: str | None = None
    approval_id: str | None = None
    organization_id: str | None = None
    """G8: Required for browser tasks, None for system events"""

    actor_user_id: str | None = None
    actor_role: str | None = None
    risk_level: str | None = None
    decision: str | None = None
    """approved|rejected|auto-allowed|blocked"""

    def __post_init__(self):
        # G8: browser task event는 organization_id 필수
        if self.event_type.startswith("BROWSER_") and not self.organization_id:
            raise ValueError(
                f"BrowserAuditEvent {self.event_type} requires organization_id (G8) for task {self.task_id}"
            )
        # system event (AGENT_*, etc.)는 organization_id nullable


@dataclass
class AppAuditLogScope:
    """앱 감사 로그 조직 범위 계약.

    G11: AppAuditLog에 organization_id 확인/확장
    """

    log_id: str
    event_type: str
    organization_id: str | None = None
    """None: system events, not None: user/task events"""

    actor_user_id: str | None = None
    actor_role: str | None = None
    target_type: str = ""
    target_id: str = ""

    def __post_init__(self):
        # G11: browser task 관련 event는 organization_id 필수
        if self.event_type.startswith("BROWSER_") and not self.organization_id:
            raise ValueError(f"AppAuditLog {self.event_type} requires organization_id (G11)")


# ============================================================================
# Cross-Organization Scope Rules
# ============================================================================


def assert_task_approval_agent_same_org(
    task: BrowserTaskScope, approval: BrowserApprovalScope, agent: LocalAgentScope
) -> None:
    """RULE: task.org_id == approval.org_id == agent.org_id

    위반 시: ValueError 발생 → task dispatch 거부

    Args:
        task: BrowserTaskScope
        approval: BrowserApprovalScope
        agent: LocalAgentScope

    Raises:
        ValueError: org_id mismatch
    """
    if task.organization_id != approval.organization_id:
        raise ValueError(
            f"task.organization_id={task.organization_id} != "
            f"approval.organization_id={approval.organization_id} "
            f"(task={task.task_id}, approval={approval.approval_id})"
        )

    if task.organization_id != agent.organization_id:
        raise ValueError(
            f"task.organization_id={task.organization_id} != "
            f"agent.organization_id={agent.organization_id} "
            f"(task={task.task_id}, agent={agent.agent_id})"
        )

    # All match: OK
    logger.debug(
        f"scope check PASS: task={task.task_id}, approval={approval.approval_id}, "
        f"agent={agent.agent_id}, org={task.organization_id}"
    )


def assert_result_task_same_org(result: BrowserResultScope, task: BrowserTaskScope) -> None:
    """RULE: result.org_id == task.org_id

    위반 시: ValueError 발생 → result 저장 거부

    Args:
        result: BrowserResultScope
        task: BrowserTaskScope

    Raises:
        ValueError: org_id mismatch
    """
    if result.organization_id != task.organization_id:
        raise ValueError(
            f"result.organization_id={result.organization_id} != "
            f"task.organization_id={task.organization_id} "
            f"(result={result.result_id}, task={task.task_id})"
        )

    logger.debug(f"result scope check PASS: result={result.result_id}, task={task.task_id}, org={task.organization_id}")


def assert_audit_task_same_org(audit_event: BrowserAuditEventScope, task: BrowserTaskScope) -> None:
    """RULE: audit.org_id == task.org_id

    위반 시: WARNING log → audit에 SCOPE_MISMATCH event 기록
    (복구 불가능하므로 blocking 아님)

    Args:
        audit_event: BrowserAuditEventScope
        task: BrowserTaskScope
    """
    if audit_event.organization_id and task.organization_id and audit_event.organization_id != task.organization_id:
        logger.warning(
            f"audit scope mismatch: audit.org={audit_event.organization_id} != "
            f"task.org={task.organization_id} "
            f"(audit_id={audit_event.event_id}, task={task.task_id})"
        )
        # Warning only (blocking 아님)
        return

    logger.debug(
        f"audit scope check PASS: event={audit_event.event_id}, task={task.task_id}, org={task.organization_id}"
    )


# ============================================================================
# Safe Dict / Sanitization
# ============================================================================


def safe_tenant_scope_dict(data: dict) -> dict:
    """Remove forbidden fields from dict recursively.

    Forbidden fields:
      - approval_token, final_approval_token, token_hash (secrets)
      - password, otp, cookie, session
      - hostname, username, ip (raw values only; hashes OK)

    Args:
        data: dict to sanitize

    Returns:
        dict with forbidden fields removed
    """
    forbidden_patterns = {
        "approval_token",
        "final_approval_token",
        "token_hash",
        "password",
        "otp",
        "cookie",
        "session",
        "authorization",
        "localstorage",
        "sessionstorage",
        "hostname",
        "username",
        "user_name",
        "ip_address",
        "machine_id",
        "device_id",
    }

    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items() if k.lower() not in forbidden_patterns}
        elif isinstance(obj, (list, tuple)):
            return type(obj)(_clean(item) for item in obj)
        return obj

    return _clean(data)


# ============================================================================
# Permission Matrix (Reference)
# ============================================================================

PERMISSION_MATRIX = {
    # Role: {action: bool}
    "owner": {
        "task_create": True,
        "task_approve": True,
        "task_reject": True,
        "task_view_all": True,
        "task_view_own": True,
        "result_view": True,
        "agent_view": True,
        "agent_register": True,
        "agent_disable": True,
        "audit_view_all": True,
        "audit_view_own": True,
        "user_invite": True,
        "user_delete": True,
        "org_settings": True,
    },
    "admin": {
        "task_create": True,
        "task_approve": True,
        "task_reject": True,
        "task_view_all": True,
        "task_view_own": True,
        "result_view": True,
        "agent_view": True,
        "agent_register": True,
        "agent_disable": True,
        "audit_view_all": True,
        "audit_view_own": True,
        "user_invite": False,
        "user_delete": False,
        "org_settings": False,
    },
    "manager": {
        "task_create": True,
        "task_approve": True,  # partial (own tasks)
        "task_reject": True,  # partial (own tasks)
        "task_view_all": False,
        "task_view_own": True,
        "result_view": True,
        "agent_view": False,
        "agent_register": False,
        "agent_disable": False,
        "audit_view_all": False,
        "audit_view_own": True,  # partial
        "user_invite": False,
        "user_delete": False,
        "org_settings": False,
    },
    "operator": {
        "task_create": False,
        "task_approve": False,
        "task_reject": False,
        "task_view_all": False,
        "task_view_own": True,
        "result_view": True,
        "agent_view": False,
        "agent_register": False,
        "agent_disable": False,
        "audit_view_all": False,
        "audit_view_own": False,
        "user_invite": False,
        "user_delete": False,
        "org_settings": False,
    },
    "viewer": {
        "task_create": False,
        "task_approve": False,
        "task_reject": False,
        "task_view_all": False,
        "task_view_own": False,
        "result_view": True,  # read-only
        "agent_view": False,
        "agent_register": False,
        "agent_disable": False,
        "audit_view_all": False,
        "audit_view_own": False,
        "user_invite": False,
        "user_delete": False,
        "org_settings": False,
    },
    "auditor": {
        "task_create": False,
        "task_approve": False,
        "task_reject": False,
        "task_view_all": False,
        "task_view_own": False,
        "result_view": False,
        "agent_view": False,
        "agent_register": False,
        "agent_disable": False,
        "audit_view_all": True,  # read-only
        "audit_view_own": True,  # read-only
        "user_invite": False,
        "user_delete": False,
        "org_settings": False,
    },
    "local_agent": {
        "task_create": False,
        "task_approve": False,
        "task_reject": False,
        "task_view_all": False,
        "task_view_own": False,  # but assigned tasks OK
        "result_view": False,
        "agent_view": False,
        "agent_register": False,
        "agent_disable": False,
        "audit_view_all": False,
        "audit_view_own": False,
        "user_invite": False,
        "user_delete": False,
        "org_settings": False,
    },
}


__all__ = [
    "PERMISSION_MATRIX",
    "AppAuditLogScope",
    "AuthTenantContext",
    "BrowserApprovalScope",
    "BrowserAuditEventScope",
    "BrowserResultScope",
    "BrowserTaskScope",
    "LocalAgentScope",
    "assert_audit_task_same_org",
    "assert_result_task_same_org",
    "assert_task_approval_agent_same_org",
    "require_active_organization",
    "require_membership",
    "safe_tenant_scope_dict",
    "validate_auth_context",
]
