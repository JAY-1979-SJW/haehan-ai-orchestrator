"""Execution Policy Service — 실행 위치/위험도/hold/oauth/user-direct 판정 서비스.

책임:
- execution_location 판정 (기존 execution_location_guard.py 호출)
- external_app_hold 여부 판정 (기존 external_work_registry 호출)
- oauth/api required 여부 판정
- user_direct_required 여부 판정
- server_internal_allowed 여부 판정
- blocked 여부 판정
- secret redaction 필요 여부 판정

금지:
- 기존 guard/policy 대체 금지 (이번 공정은 얇은 조립 계층)
- 실제 실행 금지
- DB write 금지
- 기존 API 응답 변경 금지

기존 원본:
- ai_orchestrator/server/execution_location_guard.py (원본 유지)
- ai_orchestrator/local_agent/action_risk_policy.py (원본 유지)
- ai_orchestrator/external_work_registry.py (원본 유지)

이 서비스는 3단계 Policy Layer 통합 공정의 준비 계층이다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# execution location 상수 — execution_location_guard.py 값 호환
_LOC_SERVER   = "SERVER_INTERNAL_ONLY"
_LOC_AGENT    = "LOCAL_AGENT_REQUIRED"
_LOC_USER     = "USER_DIRECT_REQUIRED"
_LOC_BLOCKED  = "BLOCKED"

# external work classification 상수 — external_work_registry 값 호환
_CLS_SERVER_READONLY   = "SERVER_READONLY_ALLOWED"
_CLS_OAUTH_REQUIRED    = "OFFICIAL_API_OR_OAUTH_REQUIRED"
_CLS_LOCAL_AGENT       = "LOCAL_AGENT_REQUIRED"
_CLS_USER_DIRECT       = "USER_DIRECT_REQUIRED"
_CLS_WEB_TASK          = "WEB_TASK_REGISTRY"
_CLS_QUARANTINE        = "QUARANTINE_OR_HOLD"
_CLS_EXTERNAL_APP_HOLD = "EXTERNAL_APP_HOLD"
_CLS_FUTURE            = "FUTURE_INTEGRATION"
_CLS_IN_SCOPE          = "IN_SCOPE"

# server에서 직접 실행 가능한 분류
_SERVER_EXECUTABLE_CLASSIFICATIONS = frozenset({
    _CLS_SERVER_READONLY,
    _CLS_WEB_TASK,
    _CLS_IN_SCOPE,
})

# 절대 서버에서 실행 불가 분류
_SERVER_BLOCKED_CLASSIFICATIONS = frozenset({
    _CLS_LOCAL_AGENT,
    _CLS_USER_DIRECT,
    _CLS_QUARANTINE,
    _CLS_EXTERNAL_APP_HOLD,
    _CLS_FUTURE,
})

# user direct required 분류
_USER_DIRECT_CLASSIFICATIONS = frozenset({
    _CLS_USER_DIRECT,
})

# oauth setup required 분류
_OAUTH_REQUIRED_CLASSIFICATIONS = frozenset({
    _CLS_OAUTH_REQUIRED,
})


@dataclass
class PolicyDecision:
    """실행 정책 판정 결과 — 읽기 전용."""
    execution_location: str
    server_executable: bool
    requires_local_agent: bool
    requires_user_direct: bool
    requires_oauth_setup: bool
    is_external_app_hold: bool
    is_blocked: bool
    requires_secret_redaction: bool
    reason: str
    classification: str = ""
    risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_location": self.execution_location,
            "server_executable": self.server_executable,
            "requires_local_agent": self.requires_local_agent,
            "requires_user_direct": self.requires_user_direct,
            "requires_oauth_setup": self.requires_oauth_setup,
            "is_external_app_hold": self.is_external_app_hold,
            "is_blocked": self.is_blocked,
            "requires_secret_redaction": self.requires_secret_redaction,
            "reason": self.reason,
            "classification": self.classification,
            "risk_level": self.risk_level,
        }


class ExecutionPolicyService:
    """실행 위치/위험도/hold/oauth/user-direct 판정 서비스.

    기존 execution_location_guard, action_risk_policy, external_work_registry를
    얇게 감싸서 통합 판정 인터페이스를 제공한다.
    """

    # ------------------------------------------------------------------
    # 기본 위치 판정

    def classify_for_server(self, task: dict[str, Any]) -> dict[str, Any]:
        """기존 execution_location_guard 호출 wrapper."""
        try:
            from ai_orchestrator.server.execution_location_guard import (
                classify_execution_location_for_server,
            )
            return classify_execution_location_for_server(task)
        except Exception as exc:
            logger.debug("execution_location_guard 호출 실패: %s", exc)
            return {
                "execution_location": _LOC_SERVER,
                "reason": "guard 미사용 — 기본 SERVER_INTERNAL_ONLY",
                "blocked": False,
            }

    def get_location(self, task: dict[str, Any]) -> str:
        """task의 execution_location 문자열을 반환한다."""
        result = self.classify_for_server(task)
        return result.get("execution_location", _LOC_SERVER)

    # ------------------------------------------------------------------
    # external_work_registry 기반 판정

    def decide_for_external_work(
        self,
        provider: str,
        work_type: str,
    ) -> PolicyDecision:
        """provider/work_type 기반으로 실행 정책을 판정한다."""
        classification = self._get_classification(provider, work_type)
        return self._classification_to_decision(classification)

    def _get_classification(self, provider: str, work_type: str) -> str:
        """external_work_registry에서 분류값을 조회한다."""
        try:
            from ai_orchestrator.external_work_registry import get_external_work
            entry = get_external_work(provider, work_type)
            if entry:
                return entry.classification
        except Exception as exc:
            logger.debug("external_work_registry 조회 실패: %s", exc)
        return _CLS_QUARANTINE

    def _classification_to_decision(self, classification: str) -> PolicyDecision:
        """분류값을 PolicyDecision으로 변환한다."""
        is_server = classification in _SERVER_EXECUTABLE_CLASSIFICATIONS
        is_agent  = classification == _CLS_LOCAL_AGENT
        is_user   = classification in _USER_DIRECT_CLASSIFICATIONS
        is_oauth  = classification in _OAUTH_REQUIRED_CLASSIFICATIONS
        is_hold   = classification == _CLS_EXTERNAL_APP_HOLD
        is_future = classification == _CLS_FUTURE
        is_quar   = classification == _CLS_QUARANTINE
        is_blocked = is_hold or is_future or is_quar

        if is_hold:
            loc = _LOC_BLOCKED
            reason = f"EXTERNAL_APP_HOLD: {classification} — 전문 앱 계약 필요"
        elif is_future:
            loc = _LOC_BLOCKED
            reason = f"FUTURE_INTEGRATION: {classification} — 미구현"
        elif is_quar:
            loc = _LOC_BLOCKED
            reason = f"QUARANTINE_OR_HOLD: {classification} — 보안 검토 필요"
        elif is_oauth:
            loc = _LOC_SERVER
            reason = f"OFFICIAL_API_OR_OAUTH_REQUIRED: OAuth 설정 완료 후 실행 가능"
        elif is_agent:
            loc = _LOC_AGENT
            reason = f"LOCAL_AGENT_REQUIRED: 로컬 에이전트 필요"
        elif is_user:
            loc = _LOC_USER
            reason = f"USER_DIRECT_REQUIRED: 사용자 직접 조작 필요"
        else:
            loc = _LOC_SERVER
            reason = f"서버 실행 가능: {classification}"

        # redaction: 로컬 에이전트 또는 사용자 직접이면 필요
        needs_redaction = is_agent or is_user

        return PolicyDecision(
            execution_location=loc,
            server_executable=is_server or is_oauth,
            requires_local_agent=is_agent,
            requires_user_direct=is_user,
            requires_oauth_setup=is_oauth,
            is_external_app_hold=is_hold,
            is_blocked=is_blocked,
            requires_secret_redaction=needs_redaction,
            reason=reason,
            classification=classification,
        )

    # ------------------------------------------------------------------
    # 개별 판정 헬퍼 (직접 분류값 기반)

    def is_server_executable(self, classification: str) -> bool:
        """분류값 기반 서버 실행 가능 여부."""
        return classification in _SERVER_EXECUTABLE_CLASSIFICATIONS

    def is_local_agent_required(self, classification: str) -> bool:
        """분류값 기반 로컬 에이전트 필요 여부."""
        return classification == _CLS_LOCAL_AGENT

    def is_user_direct_required(self, classification: str) -> bool:
        """분류값 기반 사용자 직접 조작 필요 여부."""
        return classification in _USER_DIRECT_CLASSIFICATIONS

    def is_external_app_hold(self, classification: str) -> bool:
        """분류값 기반 외부 앱 보류 여부."""
        return classification == _CLS_EXTERNAL_APP_HOLD

    def is_oauth_required(self, classification: str) -> bool:
        """분류값 기반 OAuth 설정 필요 여부."""
        return classification in _OAUTH_REQUIRED_CLASSIFICATIONS

    def is_blocked_classification(self, classification: str) -> bool:
        """분류값 기반 차단 여부 (HOLD/FUTURE/QUARANTINE)."""
        return classification in _SERVER_BLOCKED_CLASSIFICATIONS

    # ------------------------------------------------------------------
    # action risk policy 기반 판정

    def classify_action_risk(self, action: str) -> str:
        """action_risk_policy.classify_action wrapper."""
        try:
            from ai_orchestrator.local_agent.action_risk_policy import classify_action
            return classify_action(action)
        except Exception as exc:
            logger.debug("action_risk_policy 호출 실패: %s", exc)
            return "UNKNOWN"

    def is_action_blocked(self, action: str) -> bool:
        """action_risk_policy.is_blocked wrapper."""
        try:
            from ai_orchestrator.local_agent.action_risk_policy import is_blocked
            return is_blocked(action)
        except Exception as exc:
            logger.debug("action_risk_policy is_blocked 호출 실패: %s", exc)
            return False

    def is_user_direct_action(self, action: str) -> bool:
        """action_risk_policy.is_user_direct_required wrapper."""
        try:
            from ai_orchestrator.local_agent.action_risk_policy import is_user_direct_required
            return is_user_direct_required(action)
        except Exception as exc:
            logger.debug("action_risk_policy is_user_direct_required 호출 실패: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 통합 판정

    def decide_full(
        self,
        task: dict[str, Any],
        provider: Optional[str] = None,
        work_type: Optional[str] = None,
    ) -> PolicyDecision:
        """task dict + optional provider/work_type 기반 통합 판정.

        1. task에 execution_location이 명시된 경우 우선 사용
        2. provider/work_type이 있으면 registry 조회
        3. 없으면 task URL/action 기반으로 guard 판정
        """
        # 1. 명시적 execution_location
        explicit_loc = task.get("execution_location", "")
        if explicit_loc:
            return self._location_to_decision(explicit_loc, "명시적 execution_location")

        # 2. registry 조회
        if provider and work_type:
            return self.decide_for_external_work(provider, work_type)

        # 3. URL/action 기반 guard
        guard_result = self.classify_for_server(task)
        loc = guard_result.get("execution_location", _LOC_SERVER)
        reason = guard_result.get("reason", "")
        return self._location_to_decision(loc, reason)

    def _location_to_decision(self, loc: str, reason: str) -> PolicyDecision:
        """execution_location 문자열을 PolicyDecision으로 변환한다."""
        is_agent  = loc == _LOC_AGENT
        is_user   = loc == _LOC_USER
        is_blocked = loc == _LOC_BLOCKED
        is_server = loc == _LOC_SERVER

        return PolicyDecision(
            execution_location=loc,
            server_executable=is_server,
            requires_local_agent=is_agent,
            requires_user_direct=is_user,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=is_blocked,
            requires_secret_redaction=is_agent or is_user,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Safety Policy Registry 연결 (STEP 5 보강)

    def is_external_app_hold_blocked(self, classification: str) -> bool:
        """classification이 EXTERNAL_APP_HOLD 정책에 의해 차단되는지 확인."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import EXTERNAL_APP_HOLD_SCOPES
            return classification in EXTERNAL_APP_HOLD_SCOPES
        except Exception:
            return classification in (_CLS_EXTERNAL_APP_HOLD, _CLS_FUTURE)

    def is_oauth_required_blocked_without_setup(self, classification: str) -> bool:
        """classification이 OAUTH_API_REQUIRED이고 설정 미완료 시 실행 차단 여부."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import OAUTH_REQUIRED_SCOPES
            return classification in OAUTH_REQUIRED_SCOPES
        except Exception:
            return classification == _CLS_OAUTH_REQUIRED

    def is_user_direct_auto_execution_blocked(self, classification: str) -> bool:
        """USER_DIRECT_REQUIRED 분류는 자동 실행이 차단된다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import USER_DIRECT_SCOPES
            return classification in USER_DIRECT_SCOPES
        except Exception:
            return classification == _CLS_USER_DIRECT

    def is_local_agent_server_execution_blocked(self, classification: str) -> bool:
        """LOCAL_AGENT_REQUIRED 분류는 서버 직접 실행이 차단된다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import LOCAL_AGENT_SCOPES
            return classification in LOCAL_AGENT_SCOPES
        except Exception:
            return classification == _CLS_LOCAL_AGENT

    def is_blocked_action_denied(self, classification: str) -> bool:
        """BLOCKED/QUARANTINE 분류는 실행이 거부된다."""
        return classification in (_LOC_BLOCKED, _CLS_QUARANTINE)

    def get_safe_to_execute_on_server(self, classification: str) -> bool:
        """safety policy registry 기반 서버 실행 안전 여부."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import get_safe_to_execute_on_server
            return get_safe_to_execute_on_server(classification)
        except Exception:
            return self.is_server_executable(classification)

    def decide_execution_policy(self, classification: str) -> PolicyDecision:
        """classification 기반으로 safety policy registry를 참조한 통합 판정.

        기존 _classification_to_decision()을 유지하면서 policy registry를 추가로 적용한다.
        """
        base = self._classification_to_decision(classification)

        # registry 기반 safe_to_execute_on_server 보강
        safe_on_server = self.get_safe_to_execute_on_server(classification)

        # external_app_hold → hold 강제
        if self.is_external_app_hold_blocked(classification):
            return PolicyDecision(
                execution_location=_LOC_BLOCKED,
                server_executable=False,
                requires_local_agent=False,
                requires_user_direct=False,
                requires_oauth_setup=False,
                is_external_app_hold=True,
                is_blocked=True,
                requires_secret_redaction=False,
                reason=f"EXTERNAL_APP_HOLD_BLOCK: {classification} — 계약·bridge 구현 전 실행 불가",
                classification=classification,
            )

        # oauth required → blocked until setup
        if self.is_oauth_required_blocked_without_setup(classification):
            return PolicyDecision(
                execution_location=_LOC_BLOCKED,
                server_executable=False,
                requires_local_agent=False,
                requires_user_direct=False,
                requires_oauth_setup=True,
                is_external_app_hold=False,
                is_blocked=True,
                requires_secret_redaction=False,
                reason=f"OAUTH_API_REQUIRED_BLOCK: {classification} — OAuth/API 설정 완료 전 실행 불가",
                classification=classification,
            )

        # base decision 반환 (safe_to_execute_on_server 반영)
        return PolicyDecision(
            execution_location=base.execution_location,
            server_executable=base.server_executable and safe_on_server,
            requires_local_agent=base.requires_local_agent,
            requires_user_direct=base.requires_user_direct,
            requires_oauth_setup=base.requires_oauth_setup,
            is_external_app_hold=base.is_external_app_hold,
            is_blocked=base.is_blocked,
            requires_secret_redaction=base.requires_secret_redaction,
            reason=base.reason,
            classification=classification,
            risk_level=base.risk_level,
        )


# 싱글턴 인스턴스 (경량 — 상태 없음)
_service_instance: Optional[ExecutionPolicyService] = None


def get_execution_policy_service() -> ExecutionPolicyService:
    """ExecutionPolicyService 싱글턴을 반환한다."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ExecutionPolicyService()
    return _service_instance
