"""로컬 에이전트 데이터 모델 (Stage 1/2 공용).

LocalAgent, LocalAgentTask, RegisterResult 데이터클래스와
응답 직렬화 메서드(to_safe, to_list_safe, to_dispatch)를 정의한다.

보안:
  - device_token 원문은 RegisterResult에 1회만 노출, 서버는 토큰 해시만 저장
  - LocalAgentTask.params 는 민감 키 제거된 상태로만 저장
  - to_safe() / to_list_safe() / to_dispatch() 는 외부 노출 전 필드 재확인
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass
class LocalAgent:
    agent_id: str
    host: str  # 사람이 식별 가능한 PC 이름 (예: "skyjw-desktop")
    os_name: str  # "Windows 11" 등 (개인정보 제외)
    version: str  # 에이전트 버전 (예: "0.1.0")
    registered_at: str
    requested_by: str  # 등록을 요청한 actor
    token_hash: str  # SHA-256(device_token) — 원문은 저장 금지
    smoke_test: bool = False  # smoke test marker for cleanup eligibility
    # Stage 11-6B: 연결 상태 타임스탬프 (저장 필드, agent_status는 계산값)
    connected_at: str = ""
    last_seen_at: str = ""
    disconnected_at: str = ""

    def to_safe(self, stats: Mapping[str, Any] | None = None) -> dict:
        """API 응답용 (token_hash 제외, 연결 상태 계산값 포함).

        연결 상태·작업 통계(agent_status, active_task_count, current_task_id, task_count, completed_task_count,
        failed_task_count)는 레지스트리가 계산해 `stats` 로 넘긴다 — 모델(L1)이 레지스트리를 import 하지 않도록
        의존 방향을 뒤집었다(2026-10-01 층간 위반 정리). `stats` 가 없으면 기본값(offline·0·"")이다.
        """
        stats = stats or {}
        return {
            "agent_id": self.agent_id,
            "host": self.host,
            "os_name": self.os_name,
            "version": self.version,
            "registered_at": self.registered_at,
            "requested_by": self.requested_by,
            "agent_status": stats.get("agent_status", "offline"),
            "smoke_test": self.smoke_test,
            "connected_at": self.connected_at,
            "last_seen_at": self.last_seen_at,
            "disconnected_at": self.disconnected_at,
            "active_task_count": stats.get("active_task_count", 0),
            "current_task_id": stats.get("current_task_id", ""),
            "task_count": stats.get("task_count", 0),
            "completed_task_count": stats.get("completed_task_count", 0),
            "failed_task_count": stats.get("failed_task_count", 0),
        }


@dataclass
class LocalAgentTask:
    task_id: str
    agent_id: str
    action: str
    params: dict  # 민감 키 제거된 상태로만 저장
    risk_level: str
    # queued / delivered / running / waiting_approval / completed / failed / rejected
    # cancel_requested / cancelled
    status: str
    requested_by: str
    created_at: str
    updated_at: str
    token_id: str = ""  # high risk 일 때만 채워짐 (서버 내부 검증용 secret-like)
    # Stage 13H-2E: 외부 노출용 public approval id (UI/result_data/audit).
    # token_id 는 result_data/WS dispatch 에 절대 노출되지 않으며, 본 필드만
    # public 식별자로 사용된다.
    approval_public_id: str = ""
    result_summary: str = ""
    # Stage 2 추가 필드
    delivered_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    error_summary: str = ""
    # Stage 3 추가 필드 — 승인 게이트 통과 흔적
    approved_at: str = ""
    approved_by: str = ""
    rejected_at: str = ""
    reject_reason: str = ""
    # Stage 11-3B 추가 필드 — timeout / 실패 분류
    failure_reason: str = ""  # agent_error | delivered_timeout | running_timeout | cancel_timeout | websocket_disconnected | invalid_transition | unknown_error
    timed_out_at: str = ""  # timeout 종결 시각 (timeout 케이스만)
    # Stage 11-7B 추가 필드 — 취소 흔적
    cancel_reason: str = ""  # 취소 사유 (최대 200자)
    cancel_requested_at: str = ""  # cancel_requested 전환 시각
    cancel_requested_by: str = ""  # 취소 요청자
    cancelled_at: str = ""  # 최종 cancelled 전환 시각
    # Stage 13B-3A: controlled browser observe 결과 구조화 요약 (sanitized, optional)
    observe_summary: dict | None = None
    # Stage 13C-2: audit summary (PC local audit 이벤트 safe 요약, optional)
    audit_summary: dict | None = None
    # Stage 13G-3A: agent result data 안전 저장 (허용 key만, 민감정보 제거)
    result_data: dict | None = None
    # 2026-09-30 추가: WS 연결 끊김(websocket_disconnected)으로 인한 자동 재큐잉 횟수.
    # 순수 연결 문제로 실패한 작업을 사용자에게 실패로 보여주지 않고 재연결 후
    # 자동 재시도하기 위함 — MAX_WS_DISCONNECT_RETRIES(local_agent_registry_common.py) 초과 시
    # 더 이상 재큐잉하지 않고 failed 로 종결(무한 재시도 방지).
    retry_count: int = 0

    def to_safe(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "params": self.params,  # 이미 민감값 제거됨
            "risk_level": self.risk_level,
            "status": self.status,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "token_id": self.token_id,
            "approval_id": self.approval_public_id,
            "approval_public_id": self.approval_public_id,
            "result_summary": self.result_summary,
            "delivered_at": self.delivered_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_summary": self.error_summary,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "rejected_at": self.rejected_at,
            "reject_reason": self.reject_reason,
            "failure_reason": self.failure_reason,
            "timed_out_at": self.timed_out_at,
            "cancel_reason": self.cancel_reason,
            "cancel_requested_at": self.cancel_requested_at,
            "cancel_requested_by": self.cancel_requested_by,
            "cancelled_at": self.cancelled_at,
            "observe_summary": self.observe_summary,
            "audit_summary": self.audit_summary,
            "result_data": self.result_data,
            "retry_count": self.retry_count,
        }

    def to_list_safe(self) -> dict:
        """목록 조회용 응답 — params/token_id/승인 필드 제외."""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "risk_level": self.risk_level,
            "status": self.status,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "delivered_at": self.delivered_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "failure_reason": self.failure_reason,
            "timed_out_at": self.timed_out_at,
            "error_summary": self.error_summary,
            "result_summary": self.result_summary,
            "cancel_reason": self.cancel_reason,
            "cancel_requested_at": self.cancel_requested_at,
            "cancel_requested_by": self.cancel_requested_by,
            "cancelled_at": self.cancelled_at,
        }

    def to_dispatch(self) -> dict:
        """WebSocket 전달용 페이로드 (민감 필드 제거 후).

        high risk 작업은 승인 후에만 queued → delivered 흐름을 타므로,
        dispatch 시점에 approved_at 이 반드시 세팅돼 있어야 한다.
        `approved: True` 플래그는 클라이언트가 high-risk 승인 분기를 구별하는
        용도 — 미승인 시 클라이언트는 NOT_IMPLEMENTED_STAGE2 로 즉시 거절한다.
        """
        approved_flag = bool(self.risk_level == "high" and self.approved_at)
        payload = {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "params": self.params,
            "risk_level": self.risk_level,
            "approved": approved_flag,
        }
        # high-risk 승인된 task 는 token_id 를 dispatch 에 포함해
        # client 가 result_data 의 approval_id audit trail 을 채울 수 있게 한다.
        # token_id 는 approval 참조 식별자(UUID)이며 secret 이 아니다 — auth/seed 에
        # 쓰이지 않고, validate 시 서버 DB 와 task_id 결합 검증을 통과해야만 효력을 갖는다.
        # Stage 13H-2E: dispatch 에는 public approval_id 만 노출한다.
        # token_id 는 서버 내부 승인 검증용 secret-like 값이므로 WS payload 와
        # result_data 에 포함되지 않는다. legacy fallback 으로 public_id 가
        # 비어있을 때만 token_id 를 approval_id 로 보낸다 (1릴리즈 호환).
        if approved_flag:
            public_id = self.approval_public_id or self.token_id
            if public_id:
                payload["approval_id"] = public_id
        return payload


class RegisterResult:
    """register_agent 반환 컨테이너 (token 원문은 1회만 노출)."""

    __slots__ = ("agent", "device_token")

    def __init__(self, agent: LocalAgent, device_token: str):
        self.agent = agent
        self.device_token = device_token
