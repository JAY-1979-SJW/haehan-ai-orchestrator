"""ai_orchestrator 최고급 백엔드 Domain Core 기준 모델.

이 파일은 기존 코드를 대체하지 않는다.
기존 task_state / approval / external_work_registry 모듈 는 그대로 유지된다.
이 파일은 다음 공정(Service Layer 추출)의 타입 계약 기준선 역할만 한다.

설계 원칙:
- frozen dataclass: 불변 계약 모델 (read-only)
- secret/token/password/session/cookie 필드 포함 금지
- DB와 직접 연결하지 않는다
- 기존 API 응답 구조를 변경하지 않는다
- 외부 호출 없음
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# ===========================================================================
# 보조 Enum — 기존 domain/enums.py 와 중복 없이 확장
# ===========================================================================


class WorkTradeScope(str, Enum):  # noqa: UP042
    """업무 분류 범위 (WorkTrade용).

    기존 external_work_registry.py 의 classification 문자열과 값 호환.
    """

    IN_SCOPE = "IN_SCOPE"
    SERVER_READONLY_ALLOWED = "SERVER_READONLY_ALLOWED"
    OFFICIAL_API_OR_OAUTH_REQUIRED = "OFFICIAL_API_OR_OAUTH_REQUIRED"
    LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
    USER_DIRECT_REQUIRED = "USER_DIRECT_REQUIRED"
    WEB_TASK_REGISTRY = "WEB_TASK_REGISTRY"
    EXTERNAL_APP_HOLD = "EXTERNAL_APP_HOLD"
    QUARANTINE_OR_HOLD = "QUARANTINE_OR_HOLD"
    FUTURE_INTEGRATION = "FUTURE_INTEGRATION"


class IntegrationStatus(str, Enum):  # noqa: UP042
    """연동 서비스 상태."""

    READY = "ready"
    SETUP_REQUIRED = "setup_required"
    HOLD = "hold"
    BLOCKED = "blocked"
    FUTURE_INTEGRATION = "future_integration"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class HandoffMode(str, Enum):  # noqa: UP042
    """외부 앱 브릿지 핸드오프 방식."""

    FILE_HANDOFF = "FILE_HANDOFF"
    USER_HANDOFF = "USER_HANDOFF"
    TEMPLATE_HANDOFF = "TEMPLATE_HANDOFF"
    API_HANDOFF = "API_HANDOFF"
    QUEUE_HANDOFF = "QUEUE_HANDOFF"
    NONE = "NONE"


class SafetyDecision(str, Enum):  # noqa: UP042
    """안전 정책 판정 결과."""

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    REQUIRE_LOCAL_AGENT = "require_local_agent"
    REQUIRE_USER_DIRECT = "require_user_direct"
    BLOCK = "block"
    HOLD = "hold"


class ArtifactType(str, Enum):  # noqa: UP042
    """증거/산출물 유형."""

    SCREENSHOT_REF = "screenshot_ref"  # 파일 경로 참조만 (바이너리 금지)
    FILE_REF = "file_ref"  # 파일 경로 참조만
    JSON_SUMMARY = "json_summary"  # 요약 JSON (safe fields만)
    TEXT_LOG = "text_log"  # 텍스트 로그
    HANDOFF_RECORD = "handoff_record"  # 외부 앱 핸드오프 기록
    AUDIT_ENTRY = "audit_entry"  # 감사 항목 참조


class EvidenceLevel(str, Enum):  # noqa: UP042
    """증거 신뢰 수준."""

    CONFIRMED = "confirmed"  # 실행 완료 확인
    PARTIAL = "partial"  # 일부 확인
    INFERRED = "inferred"  # 추정
    NONE = "none"


# ===========================================================================
# 핵심 Domain 모델
# ===========================================================================


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "") -> str:
    uid = str(uuid.uuid4())
    return f"{prefix}{uid}" if prefix else uid


# ---------------------------------------------------------------------------
# Task — 업무 지휘센터 핵심 업무 단위
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """최고급 백엔드 Task 도메인 모델.

    기존 task_state.py.TaskRecord 와 동시 공존.
    이 모델은 read-only 계약 기준선이다.

    금지 필드: password, token, session, cookie, otp, credential
    """

    task_id: str
    title: str
    provider: str  # naver / google / hiworks / etc.
    action_type: str  # blog_post / search / email_send / etc.
    execution_location: str  # ExecutionLocation 값
    risk_level: str  # RiskLevel 값
    approval_required: bool
    status: str  # TaskStatus 값
    requested_at: str = field(default_factory=_now_iso)
    expires_at: str | None = None
    requested_by: str = ""  # 요청자 식별자 (actor, not secret)
    work_trade_id: str | None = None
    artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    safety_policy_ids: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        """secret 필드 없는 직렬화 — 외부 노출용."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "provider": self.provider,
            "action_type": self.action_type,
            "execution_location": self.execution_location,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "status": self.status,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "requested_by": self.requested_by,
            "work_trade_id": self.work_trade_id,
            "artifact_refs": list(self.artifact_refs),
            "safety_policy_ids": list(self.safety_policy_ids),
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# WorkTrade — 업무 거래 단위 (지휘센터가 관리하는 업무 분류)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkTrade:
    """업무 거래 단위 도메인 모델.

    비서앱이 관리하는 업무 범주.
    WorkTradeScope로 현재 지원 범위를 명시한다.
    """

    work_trade_id: str
    name: str
    description: str
    scope: str  # WorkTradeScope 값
    execution_location: str  # ExecutionLocation 값
    external_app_hold: bool = False
    integration_id: str | None = None
    next_phase: str | None = None
    owner_layer: str = "SERVER"  # SERVER / LOCAL_AGENT / USER_DIRECT
    status: str = "active"

    def is_external_app_hold(self) -> bool:
        return self.external_app_hold or self.scope == WorkTradeScope.EXTERNAL_APP_HOLD

    def is_future_integration(self) -> bool:
        return self.scope == WorkTradeScope.FUTURE_INTEGRATION

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "work_trade_id": self.work_trade_id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "execution_location": self.execution_location,
            "external_app_hold": self.external_app_hold,
            "integration_id": self.integration_id,
            "next_phase": self.next_phase,
            "owner_layer": self.owner_layer,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# ExternalWork — 외부 웹 업무 항목 (표준 모델)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalWork:
    """외부 웹 업무 표준 도메인 모델.

    기존 external_work_registry.py.ExternalWorkEntry 와 동시 공존.
    이 모델은 read-only 계약 기준선이다.
    """

    external_work_id: str
    provider: str
    action_type: str
    category: str  # WorkTradeScope 값
    execution_location: str  # ExecutionLocation 값
    risk_level: str  # RiskLevel 값
    approval_required: bool
    auth_mode: str  # none / browser_session / oauth / bot_token
    status: str  # active / hold / blocked / future
    safety_notice: str = ""
    description: str = ""

    def is_executable(self) -> bool:
        return self.status == "active" and self.category not in (
            WorkTradeScope.QUARANTINE_OR_HOLD,
            WorkTradeScope.EXTERNAL_APP_HOLD,
            WorkTradeScope.FUTURE_INTEGRATION,
        )

    def requires_local_agent(self) -> bool:
        return self.execution_location == "LOCAL_AGENT_REQUIRED"

    def requires_user_direct(self) -> bool:
        return self.execution_location == "USER_DIRECT_REQUIRED"

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "external_work_id": self.external_work_id,
            "provider": self.provider,
            "action_type": self.action_type,
            "category": self.category,
            "execution_location": self.execution_location,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "auth_mode": self.auth_mode,
            "status": self.status,
            "safety_notice": self.safety_notice,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Integration — 연동 서비스 표준 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Integration:
    """연동 서비스 도메인 모델.

    기존 ops_router 모듈의 _STATIC_INTEGRATIONS 정적 dict 와 동시 공존.
    """

    integration_id: str
    name: str
    provider: str
    integration_type: str  # search / social / email / oauth / bot / etc.
    status: str  # IntegrationStatus 값
    auth_mode: str  # none / browser_session / oauth / bot_token / api_key
    connected: bool = False
    required_setup: str | None = None  # 설정 요약 (secret 원문 금지)
    health: str = "unknown"  # healthy / degraded / unknown
    last_seen_at: str | None = None
    notes: str = ""

    def is_ready(self) -> bool:
        return self.connected and self.status in (
            IntegrationStatus.READY,
            IntegrationStatus.CONNECTED,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "name": self.name,
            "provider": self.provider,
            "integration_type": self.integration_type,
            "status": self.status,
            "auth_mode": self.auth_mode,
            "connected": self.connected,
            "required_setup": self.required_setup,
            "health": self.health,
            "last_seen_at": self.last_seen_at,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Artifact — 증거/산출물 참조 모델 (경로 ref만, 실제 내용 금지)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """증거/산출물 참조 도메인 모델.

    바이너리 원문 저장 금지. 파일 경로 참조(storage_ref)만 허용.
    secret/token/password 포함 금지.
    """

    artifact_id: str
    artifact_type: str  # ArtifactType 값
    content_type: str  # 'text/plain' / 'application/json' / 'image/png-ref' / etc.
    storage_ref: str  # 파일 경로 또는 참조 ID (실제 내용 아님)
    safe_name: str  # 사람이 읽을 수 있는 이름
    created_at: str = field(default_factory=_now_iso)
    source_task_id: str | None = None
    evidence_level: str = EvidenceLevel.NONE
    summary: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "content_type": self.content_type,
            "storage_ref": self.storage_ref,
            "safe_name": self.safe_name,
            "created_at": self.created_at,
            "source_task_id": self.source_task_id,
            "evidence_level": self.evidence_level,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# SafetyPolicy — 안전 정책 단위 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SafetyPolicy:
    """안전 정책 단위 도메인 모델.

    각 정책은 decision 으로 실행 허용/차단/보류를 결정한다.
    기존 browser_tool/policy 모듈 / server_egress_policy 모듈 와 동시 공존.
    """

    policy_id: str
    name: str
    category: str  # execution / approval / redaction / hold / block
    severity: str  # info / warn / block / critical
    applies_to: tuple[str, ...]  # 정책 적용 대상 (provider / action_type / location)
    decision: str  # SafetyDecision 값
    reason: str
    required_execution_location: str | None = None  # 필요시 강제 위치

    def blocks_execution(self) -> bool:
        return self.decision in (SafetyDecision.BLOCK, SafetyDecision.HOLD)

    def requires_user_direct(self) -> bool:
        return self.decision == SafetyDecision.REQUIRE_USER_DIRECT

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "category": self.category,
            "severity": self.severity,
            "applies_to": list(self.applies_to),
            "decision": self.decision,
            "reason": self.reason,
            "required_execution_location": self.required_execution_location,
        }


# ---------------------------------------------------------------------------
# ExternalAppBridge — 외부 전문 앱 브릿지 계약 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalAppBridge:
    """외부 전문 앱 브릿지 도메인 모델.

    CAD/HWPX/Excel/세무/입찰/문서자동화 등 전문 앱 연결 계약.
    현재 앱은 작업 생성/승인/상태/감사/결과 수신만 담당.
    전문 기능 자체 구현 금지.
    """

    bridge_id: str
    app_type: str  # CAD / HWPX / OFFICE / TAX / BID / DOCUMENT_AUTOMATION
    capability: tuple[str, ...]  # 지원 능력 목록
    handoff_mode: str  # HandoffMode 값
    execution_location: str  # 항상 LOCAL_AGENT_REQUIRED 또는 USER_DIRECT_REQUIRED
    approval_required: bool  # 항상 True — 외부 앱 실행은 승인 필수
    input_schema_ref: str | None = None  # 입력 스키마 참조 ID
    output_schema_ref: str | None = None  # 출력 스키마 참조 ID
    status: str = "FUTURE_INTEGRATION"  # 현재 미구현 고정
    safety_policy_ids: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def is_implemented(self) -> bool:
        return self.status not in ("FUTURE_INTEGRATION", "EXTERNAL_APP_HOLD")

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "bridge_id": self.bridge_id,
            "app_type": self.app_type,
            "capability": list(self.capability),
            "handoff_mode": self.handoff_mode,
            "execution_location": self.execution_location,
            "approval_required": self.approval_required,
            "input_schema_ref": self.input_schema_ref,
            "output_schema_ref": self.output_schema_ref,
            "status": self.status,
            "safety_policy_ids": list(self.safety_policy_ids),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# AuditEvent — 표준 감사 이벤트 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditEvent:
    """표준 감사 이벤트 도메인 모델.

    기존 audit_logger.py 와 동시 공존.
    표준 필드 11개 필수 (ASSISTANT_BACKEND_PREMIUM_ARCHITECTURE_REDESIGN_01 기준).

    금지 필드: password, otp, cookie, session, token, private_key,
               raw_screenshot, base64, localstorage, authorization
    """

    # 필수 11개 필드
    event_id: str
    event_type: str  # audit_logger.EVENT_TYPES 참조
    task_id: str
    provider: str
    action_type: str
    risk_level: str  # RiskLevel 값
    execution_location: str  # ExecutionLocation 값
    actor: str  # server / local_agent / user
    timestamp: str
    verdict: str  # Verdict 값
    summary: str
    # 선택 필드
    artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    evidence_id: str | None = None
    safety_verdict: str | None = None
    external_app_handoff_id: str | None = None
    user_direct_instruction_id: str | None = None
    parent_event_id: str | None = None
    redaction_applied: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    _REQUIRED_FIELDS: tuple[str, ...] = field(
        init=False,
        repr=False,
        compare=False,
        default=(
            "event_id",
            "event_type",
            "task_id",
            "provider",
            "action_type",
            "risk_level",
            "execution_location",
            "actor",
            "timestamp",
            "verdict",
            "summary",
        ),
    )

    def to_safe_dict(self) -> dict[str, Any]:
        """secret 필드 없는 직렬화."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "provider": self.provider,
            "action_type": self.action_type,
            "risk_level": self.risk_level,
            "execution_location": self.execution_location,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "verdict": self.verdict,
            "summary": self.summary,
            "artifact_refs": list(self.artifact_refs),
            "evidence_id": self.evidence_id,
            "safety_verdict": self.safety_verdict,
            "external_app_handoff_id": self.external_app_handoff_id,
            "redaction_applied": self.redaction_applied,
        }


# ===========================================================================
# 편의 팩토리 함수
# ===========================================================================


def make_task(
    title: str,
    provider: str,
    action_type: str,
    execution_location: str,
    risk_level: str,
    approval_required: bool,
    status: str = "pending",
    **kwargs: Any,
) -> Task:
    """Task 생성 팩토리 — task_id 자동 생성."""
    return Task(
        task_id=_new_id("task-"),
        title=title,
        provider=provider,
        action_type=action_type,
        execution_location=execution_location,
        risk_level=risk_level,
        approval_required=approval_required,
        status=status,
        **kwargs,
    )


def make_audit_event(
    event_type: str,
    task_id: str,
    provider: str,
    action_type: str,
    risk_level: str,
    execution_location: str,
    actor: str,
    verdict: str,
    summary: str,
    **kwargs: Any,
) -> AuditEvent:
    """AuditEvent 생성 팩토리 — event_id / timestamp 자동 생성."""
    return AuditEvent(
        event_id=_new_id("evt-"),
        event_type=event_type,
        task_id=task_id,
        provider=provider,
        action_type=action_type,
        risk_level=risk_level,
        execution_location=execution_location,
        actor=actor,
        timestamp=_now_iso(),
        verdict=verdict,
        summary=summary,
        **kwargs,
    )


# ===========================================================================
# 금지 필드 상수 (모든 to_safe_dict 직렬화에서 제외)
# ===========================================================================

DOMAIN_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "cert_password",
        "private_key",
        "cookie",
        "session",
        "token",
        "approval_token",
        "final_approval_token",
        "raw_screenshot",
        "base64",
        "localstorage",
        "sessionstorage",
        "authorization",
        "device_token",
        "npki_data",
        "auth_token",
        "certificate_file_path",
        "access_token",
        "refresh_token",
        "file_content",
        "file_bytes",
        "file_data",
        "attachment_content",
        "attachment_bytes",
    }
)


def assert_no_forbidden_fields(d: dict[str, Any]) -> list[str]:
    """직렬화 dict에 금지 필드가 없는지 검증. 위반 key 목록 반환."""
    violations = []
    for key in d:
        if key.lower() in DOMAIN_FORBIDDEN_FIELDS:
            violations.append(key)
    return violations


__all__ = [  # noqa: RUF022
    # Enum
    "WorkTradeScope",
    "IntegrationStatus",
    "HandoffMode",
    "SafetyDecision",
    "ArtifactType",
    "EvidenceLevel",
    # Models
    "Task",
    "WorkTrade",
    "ExternalWork",
    "Integration",
    "Artifact",
    "SafetyPolicy",
    "ExternalAppBridge",
    "AuditEvent",
    # Factories
    "make_task",
    "make_audit_event",
    # Security
    "DOMAIN_FORBIDDEN_FIELDS",
    "assert_no_forbidden_fields",
]
