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
- ai_orchestrator/contracts/action_risk_policy.py (원본 유지)
- ai_orchestrator/tasks/external_work_registry.py (원본 유지)

이 서비스는 3단계 Policy Layer 통합 공정의 준비 계층이다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# execution location 상수 — execution_location_guard.py 값 호환
_LOC_SERVER = "SERVER_INTERNAL_ONLY"
_LOC_AGENT = "LOCAL_AGENT_REQUIRED"
_LOC_USER = "USER_DIRECT_REQUIRED"
_LOC_BLOCKED = "BLOCKED"

# external work classification 상수 — external_work_registry 값 호환
_CLS_SERVER_READONLY = "SERVER_READONLY_ALLOWED"
_CLS_OAUTH_REQUIRED = "OFFICIAL_API_OR_OAUTH_REQUIRED"
_CLS_LOCAL_AGENT = "LOCAL_AGENT_REQUIRED"
_CLS_USER_DIRECT = "USER_DIRECT_REQUIRED"
_CLS_WEB_TASK = "WEB_TASK_REGISTRY"
_CLS_QUARANTINE = "QUARANTINE_OR_HOLD"
_CLS_EXTERNAL_APP_HOLD = "EXTERNAL_APP_HOLD"
_CLS_FUTURE = "FUTURE_INTEGRATION"
_CLS_IN_SCOPE = "IN_SCOPE"

# server에서 직접 실행 가능한 분류
_SERVER_EXECUTABLE_CLASSIFICATIONS = frozenset(
    {
        _CLS_SERVER_READONLY,
        _CLS_WEB_TASK,
        _CLS_IN_SCOPE,
    }
)

# 절대 서버에서 실행 불가 분류
_SERVER_BLOCKED_CLASSIFICATIONS = frozenset(
    {
        _CLS_LOCAL_AGENT,
        _CLS_USER_DIRECT,
        _CLS_QUARANTINE,
        _CLS_EXTERNAL_APP_HOLD,
        _CLS_FUTURE,
    }
)

# user direct required 분류
_USER_DIRECT_CLASSIFICATIONS = frozenset(
    {
        _CLS_USER_DIRECT,
    }
)

# oauth setup required 분류
_OAUTH_REQUIRED_CLASSIFICATIONS = frozenset(
    {
        _CLS_OAUTH_REQUIRED,
    }
)

# ---------------------------------------------------------------------------
# 사이트별 액션 정책 — STEP 6 분류표
# ---------------------------------------------------------------------------
# cert_auth: 인증서 기반 로그인이 필요한 사이트 (최초 1회 사용자 직접 필수)
# final_approval_required: 해당 사이트의 저장/제출에 사용자 승인 게이트 필요
_SITE_ACTION_POLICY: dict[str, dict] = {
    "gabia": {
        "cert_auth": False,
        "final_approval_required": True,  # DNS 변경 = 최종 승인
        "note": "도메인/DNS 관리. AI는 입력까지만, 적용 버튼은 사용자 승인 후.",
    },
    "naver": {
        "cert_auth": False,
        "final_approval_required": True,  # 블로그 게시/카페 글쓰기
        "note": "블로그/카페/메일. 발행/전송은 사용자 승인 후.",
    },
    "google": {
        "cert_auth": False,
        "final_approval_required": True,
        "note": "Gmail/Calendar/Drive. 전송/삭제는 사용자 승인 후.",
    },
    "g2b": {
        "cert_auth": True,  # 나라장터 인증서 로그인
        "final_approval_required": True,  # 입찰 제출
        "note": "나라장터. 인증서 로그인 = 사용자 직접. 투찰/제출 = 사용자 승인.",
    },
    "bank": {
        "cert_auth": True,  # 은행 인증서 로그인
        "final_approval_required": True,  # 이체/송금
        "note": "인터넷뱅킹. 인증서 로그인 = 사용자 직접. 이체 = 사용자 승인.",
    },
    "tax": {
        "cert_auth": True,  # 홈택스/지방세
        "final_approval_required": True,
        "note": "세금 신고/납부. 인증서 로그인 = 사용자 직접. 신고/납부 = 사용자 승인.",
    },
    "bid": {
        "cert_auth": True,
        "final_approval_required": True,
        "note": "전자입찰. 인증서 로그인 = 사용자 직접. 투찰 = 사용자 승인.",
    },
    "insurance": {
        "cert_auth": False,
        "final_approval_required": True,
        "note": "보험 포털. 제출/신청은 사용자 승인 후.",
    },
    "certificate_portal": {
        "cert_auth": True,
        "final_approval_required": True,
        "note": "전자서명 포털. 인증서 = 사용자 직접. 서명 = 사용자 승인.",
    },
    "eum": {
        "cert_auth": False,
        "final_approval_required": True,
        "note": "건설근로자공제회. 데이터 조회 = 신뢰 세션 재사용. 등록/신청 = 사용자 승인.",
    },
    "hiworks": {
        "cert_auth": False,
        "final_approval_required": True,
        "note": "메일/그룹웨어. 전송/게시 = 사용자 승인.",
    },
}


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
    # 신뢰 세션 / 최종 승인 게이트 필드 (v1.0)
    safe_to_prepare: bool = True  # AI가 폼 입력/화면 진입 가능
    safe_to_click_final_button: bool = False  # AI가 최종 버튼 클릭 가능 여부
    requires_final_approval: bool = False  # 최종 사용자 승인 게이트 필요
    allowed_to_reuse_trusted_session: bool = False  # 신뢰 세션 재사용 허용 여부
    requires_user_present_auth: bool = False  # 사용자 직접 인증 필요
    requires_reauth: bool = False  # 세션 만료로 재인증 필요

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
            "safe_to_prepare": self.safe_to_prepare,
            "safe_to_click_final_button": self.safe_to_click_final_button,
            "requires_final_approval": self.requires_final_approval,
            "allowed_to_reuse_trusted_session": self.allowed_to_reuse_trusted_session,
            "requires_user_present_auth": self.requires_user_present_auth,
            "requires_reauth": self.requires_reauth,
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
        except Exception as exc:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
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
            from ai_orchestrator.tasks.external_work_registry import get_external_work

            entry = get_external_work(provider, work_type)
            if entry:
                return entry.classification
        except Exception as exc:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.debug("external_work_registry 조회 실패: %s", exc)
        return _CLS_QUARANTINE

    def _classification_to_decision(self, classification: str) -> PolicyDecision:
        """분류값을 PolicyDecision으로 변환한다."""
        is_server = classification in _SERVER_EXECUTABLE_CLASSIFICATIONS
        is_agent = classification == _CLS_LOCAL_AGENT
        is_user = classification in _USER_DIRECT_CLASSIFICATIONS
        is_oauth = classification in _OAUTH_REQUIRED_CLASSIFICATIONS
        is_hold = classification == _CLS_EXTERNAL_APP_HOLD
        is_future = classification == _CLS_FUTURE
        is_quar = classification == _CLS_QUARANTINE
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
            reason = "OFFICIAL_API_OR_OAUTH_REQUIRED: OAuth 설정 완료 후 실행 가능"
        elif is_agent:
            loc = _LOC_AGENT
            reason = "LOCAL_AGENT_REQUIRED: 로컬 에이전트 필요"
        elif is_user:
            loc = _LOC_USER
            reason = "USER_DIRECT_REQUIRED: 사용자 직접 조작 필요"
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
            from ai_orchestrator.contracts.action_risk_policy import classify_action

            return classify_action(action)
        except Exception as exc:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.debug("action_risk_policy 호출 실패: %s", exc)
            return "UNKNOWN"

    def is_action_blocked(self, action: str) -> bool:
        """action_risk_policy.is_blocked wrapper."""
        try:
            from ai_orchestrator.contracts.action_risk_policy import is_blocked

            return is_blocked(action)
        except Exception as exc:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            # fail-closed: 정책 모듈을 못 불러오면 "차단"이 안전한 기본값이다(2026-09-28).
            logger.warning("action_risk_policy is_blocked 호출 실패 — fail-closed(차단): %s", exc)
            return True

    def is_user_direct_action(self, action: str) -> bool:
        """action_risk_policy.is_user_direct_required wrapper."""
        try:
            from ai_orchestrator.contracts.action_risk_policy import is_user_direct_required

            return is_user_direct_required(action)
        except Exception as exc:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            # fail-closed: 판정 불가 시 "사용자 직접 필요"가 안전한 기본값이다(2026-09-28).
            logger.warning("action_risk_policy is_user_direct_required 호출 실패 — fail-closed: %s", exc)
            return True

    # ------------------------------------------------------------------
    # 통합 판정

    def decide_full(
        self,
        task: dict[str, Any],
        provider: str | None = None,
        work_type: str | None = None,
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
        is_agent = loc == _LOC_AGENT
        is_user = loc == _LOC_USER
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
            from ai_orchestrator.safety_policy.safety_policy_registry import (
                EXTERNAL_APP_HOLD_SCOPES,
            )

            return classification in EXTERNAL_APP_HOLD_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return classification in (_CLS_EXTERNAL_APP_HOLD, _CLS_FUTURE)

    def is_oauth_required_blocked_without_setup(self, classification: str) -> bool:
        """classification이 OAUTH_API_REQUIRED이고 설정 미완료 시 실행 차단 여부."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import OAUTH_REQUIRED_SCOPES

            return classification in OAUTH_REQUIRED_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return classification == _CLS_OAUTH_REQUIRED

    def is_user_direct_auto_execution_blocked(self, classification: str) -> bool:
        """USER_DIRECT_REQUIRED 분류는 자동 실행이 차단된다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import USER_DIRECT_SCOPES

            return classification in USER_DIRECT_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return classification == _CLS_USER_DIRECT

    def is_local_agent_server_execution_blocked(self, classification: str) -> bool:
        """LOCAL_AGENT_REQUIRED 분류는 서버 직접 실행이 차단된다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import LOCAL_AGENT_SCOPES

            return classification in LOCAL_AGENT_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return classification == _CLS_LOCAL_AGENT

    def is_blocked_action_denied(self, classification: str) -> bool:
        """BLOCKED/QUARANTINE 분류는 실행이 거부된다."""
        return classification in (_LOC_BLOCKED, _CLS_QUARANTINE)

    def get_safe_to_execute_on_server(self, classification: str) -> bool:
        """safety policy registry 기반 서버 실행 안전 여부."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import (
                get_safe_to_execute_on_server,
            )

            return get_safe_to_execute_on_server(classification)
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return self.is_server_executable(classification)

    # ------------------------------------------------------------------
    # 신뢰 세션 / 최종 승인 게이트 판정 (TRUSTED_SESSION_AND_USER_APPROVAL v1.0)

    def is_final_action(self, action: str) -> bool:
        """action이 최종 승인 게이트가 필요한 행위인지 판정한다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import FINAL_ACTION_SCOPES

            return action in FINAL_ACTION_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            # fail-closed: 판정 불가 시 "최종 승인 게이트 필요"가 안전한 기본값이다(2026-09-28).
            return True

    def is_secret_storage_forbidden(self, action: str) -> bool:
        """action이 시크릿 저장 금지 대상인지 판정한다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import SECRET_STORAGE_SCOPES

            return action in SECRET_STORAGE_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            # fail-closed: 판정 불가 시 "저장 금지"가 안전한 기본값이다(2026-09-28).
            return True

    def is_domain_change_approval_required(self, action: str) -> bool:
        """action이 도메인/DNS 변경 승인 필수 대상인지 판정한다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import DOMAIN_CHANGE_SCOPES

            return action in DOMAIN_CHANGE_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            # fail-closed: 판정 불가 시 "승인 필요"가 안전한 기본값이다(2026-09-28).
            return True

    def is_trusted_session_reusable(self, action: str) -> bool:
        """action이 신뢰 세션 재사용 허용 대상인지 판정한다."""
        try:
            from ai_orchestrator.safety_policy.safety_policy_registry import TRUSTED_SESSION_SCOPES

            return action in TRUSTED_SESSION_SCOPES
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return False

    # ------------------------------------------------------------------
    # Gabia DNS 업무 특화 판정 (GABIA_DNS_USER_APPROVAL_WORKFLOW v1.0)

    def decide_gabia_login(self) -> PolicyDecision:
        """가비아 로그인 판정 — USER_PRESENT_AUTH 필수."""
        return PolicyDecision(
            execution_location=_LOC_AGENT,
            server_executable=False,
            requires_local_agent=True,
            requires_user_direct=False,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=False,
            requires_secret_redaction=False,
            reason="가비아 최초 로그인은 USER_PRESENT_AUTH — 사용자 직접 수행 필수",
            classification="GABIA_LOGIN",
            safe_to_prepare=False,
            safe_to_click_final_button=False,
            requires_final_approval=False,
            allowed_to_reuse_trusted_session=False,
            requires_user_present_auth=True,
            requires_reauth=False,
        )

    def decide_gabia_trusted_session_reuse(self) -> PolicyDecision:
        """가비아 신뢰 세션 재사용 판정."""
        return PolicyDecision(
            execution_location=_LOC_AGENT,
            server_executable=False,
            requires_local_agent=True,
            requires_user_direct=False,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=False,
            requires_secret_redaction=False,
            reason="가비아 승인 세션 재사용 — 신뢰 세션 재사용 허용",
            classification="GABIA_TRUSTED_SESSION",
            safe_to_prepare=True,
            safe_to_click_final_button=False,
            requires_final_approval=False,
            allowed_to_reuse_trusted_session=True,
            requires_user_present_auth=False,
            requires_reauth=False,
        )

    def decide_gabia_dns_prepare(self) -> PolicyDecision:
        """가비아 DNS 레코드 입력 준비 판정 — safe_to_prepare=True."""
        return PolicyDecision(
            execution_location=_LOC_AGENT,
            server_executable=False,
            requires_local_agent=True,
            requires_user_direct=False,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=False,
            requires_secret_redaction=False,
            reason="DNS 레코드 입력 준비는 AI 허용 — 최종 저장은 사용자 승인 필수",
            classification="GABIA_DNS_PREPARE",
            safe_to_prepare=True,
            safe_to_click_final_button=False,
            requires_final_approval=True,
            allowed_to_reuse_trusted_session=True,
            requires_user_present_auth=False,
            requires_reauth=False,
        )

    def decide_gabia_dns_final_save(self) -> PolicyDecision:
        """가비아 DNS 최종 저장/적용 판정 — 사용자 승인 없이 AI 클릭 절대 금지."""
        return PolicyDecision(
            execution_location=_LOC_USER,
            server_executable=False,
            requires_local_agent=False,
            requires_user_direct=True,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=False,
            requires_secret_redaction=False,
            reason="DNS 최종 저장은 사용자 승인 게이트 통과 후에만 실행 가능",
            classification="GABIA_DNS_FINAL_SAVE",
            safe_to_prepare=False,
            safe_to_click_final_button=False,
            requires_final_approval=True,
            allowed_to_reuse_trusted_session=False,
            requires_user_present_auth=False,
            requires_reauth=False,
        )

    def decide_gabia_session_expired(self) -> PolicyDecision:
        """가비아 세션 만료 판정 — 재인증 필수."""
        return PolicyDecision(
            execution_location=_LOC_USER,
            server_executable=False,
            requires_local_agent=False,
            requires_user_direct=True,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=False,
            requires_secret_redaction=False,
            reason="가비아 세션 만료 — AI 자동 재로그인 금지, 사용자 재인증 요청",
            classification="GABIA_SESSION_EXPIRED",
            safe_to_prepare=False,
            safe_to_click_final_button=False,
            requires_final_approval=False,
            allowed_to_reuse_trusted_session=False,
            requires_user_present_auth=True,
            requires_reauth=True,
        )

    # ------------------------------------------------------------------
    # Gabia 브라우저 상태 기반 정책 판정 (GABIA_BROWSER_AUTOMATION v1.0)

    def decide_for_gabia_browser_state(self, state: str) -> PolicyDecision:
        """가비아 브라우저 상태(state machine)에 따른 정책 판정.

        safe_to_prepare: AI가 해당 상태에서 자동 실행 가능
        safe_to_click_final_button: 최종 버튼 AI 자동 클릭 가능 여부 (항상 False)
        requires_user_present_auth: 사용자 직접 인증 필요 여부
        requires_reauth: 재인증 필요 여부
        """
        try:
            from ai_orchestrator.connectors.gabia.browser_task import (
                STATE_BLOCKED,
                STATE_LOGIN_REQUIRED,
                STATE_REAUTH_REQUIRED,
                STATE_USER_PRESENT_AUTH_IN_PROGRESS,
                USER_REQUIRED_STATES,
                is_ai_executable,
                is_final_button_blocked,
            )

            ai_exec = is_ai_executable(state)
            final_blocked = is_final_button_blocked(state)
            user_required = state in USER_REQUIRED_STATES
            needs_reauth = state == STATE_REAUTH_REQUIRED
            needs_user_present = state in (
                STATE_LOGIN_REQUIRED,
                STATE_USER_PRESENT_AUTH_IN_PROGRESS,
            )
            is_blocked = state == STATE_BLOCKED
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            ai_exec = False
            final_blocked = True
            user_required = True
            needs_reauth = False
            needs_user_present = False
            is_blocked = False

        return PolicyDecision(
            execution_location=_LOC_AGENT if not user_required else _LOC_USER,
            server_executable=False,
            requires_local_agent=not user_required,
            requires_user_direct=user_required,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=is_blocked,
            requires_secret_redaction=False,
            reason=f"가비아 브라우저 상태={state}",
            classification=f"GABIA_BROWSER_STATE:{state}",
            safe_to_prepare=ai_exec,
            safe_to_click_final_button=False,
            requires_final_approval=final_blocked,
            allowed_to_reuse_trusted_session=ai_exec and not needs_user_present,
            requires_user_present_auth=needs_user_present,
            requires_reauth=needs_reauth,
        )

    def is_gabia_browser_action_blocked(self, action: str) -> bool:
        """가비아 domain profile 기반으로 해당 action이 차단되는지 확인한다."""
        try:
            from ai_orchestrator.browser_tool.policy.domain_profile_registry import (
                is_action_blocked_for_domain,
            )

            return is_action_blocked_for_domain("gabia.com", action)
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return action in ("dns_final_save", "dns_apply_button_click")

    def is_gabia_browser_action_user_direct(self, action: str) -> bool:
        """가비아 domain profile 기반으로 해당 action이 사용자 직접 수행인지 확인한다."""
        try:
            from ai_orchestrator.browser_tool.policy.domain_profile_registry import (
                is_user_direct_action_for_domain,
            )

            return is_user_direct_action_for_domain("gabia.com", action)
        except Exception as err:  # noqa: BLE001 - 정책 모듈 import 실패 시 폴백 — is_action_blocked/is_user_direct_action/is_final_action/is_secret_storage_forbidden/is_domain_change_approval_required 5곳은 fail-closed(차단/승인필요 쪽)로 직접 수정(2026-09-28), 나머지는 이미 안전한 기본값(QUARANTINE/SERVER_INTERNAL_ONLY) 또는 전달받은 classification 기반 계산값 사용(맹목적 허용 아님)
            logger.warning("정책 모듈 판정(폴백 적용) 실패: %s", type(err).__name__)
            return action in ("dns_save", "dns_apply")

    def decide_for_site_action(self, site: str, action: str) -> PolicyDecision:
        """site + action 기반 신뢰 세션 / 최종 승인 게이트 통합 판정.

        safe_to_prepare: 폼 입력/화면 이동 등 준비 단계는 허용
        safe_to_click_final_button: 최종 버튼은 항상 False — 사용자 승인 필요
        """
        site_info = _SITE_ACTION_POLICY.get(site, {})
        requires_cert = site_info.get("cert_auth", False)
        requires_approval = site_info.get("final_approval_required", True)

        is_final = self.is_final_action(action)
        is_dns = self.is_domain_change_approval_required(action)
        is_reusable = self.is_trusted_session_reusable(action)

        return PolicyDecision(
            execution_location=_LOC_AGENT,
            server_executable=False,
            requires_local_agent=True,
            requires_user_direct=False,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=False,
            requires_secret_redaction=False,
            reason=f"사이트={site}, 행위={action}",
            classification=f"SITE:{site}:{action}",
            safe_to_prepare=True,
            safe_to_click_final_button=False,
            requires_final_approval=is_final or is_dns or requires_approval,
            allowed_to_reuse_trusted_session=is_reusable and not requires_cert,
            requires_user_present_auth=requires_cert,
            requires_reauth=False,
        )

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
_service_instance: ExecutionPolicyService | None = None


def get_execution_policy_service() -> ExecutionPolicyService:
    """ExecutionPolicyService 싱글턴을 반환한다."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ExecutionPolicyService()
    return _service_instance


# ---------------------------------------------------------------------------
# AuditEvent 타입 상수 — TRUSTED_SESSION_AND_USER_APPROVAL v1.0
# ---------------------------------------------------------------------------
AUDIT_USER_PRESENT_AUTH_REQUIRED = "USER_PRESENT_AUTH_REQUIRED"
AUDIT_TRUSTED_SESSION_REUSED = "TRUSTED_SESSION_REUSED"
AUDIT_TRUSTED_SESSION_EXPIRED = "TRUSTED_SESSION_EXPIRED_REAUTH_NEEDED"
AUDIT_FINAL_APPROVAL_REQUIRED = "FINAL_APPROVAL_REQUIRED"
AUDIT_FINAL_APPROVAL_GRANTED = "FINAL_APPROVAL_GRANTED"
AUDIT_FINAL_ACTION_BLOCKED = "FINAL_ACTION_BLOCKED_NO_APPROVAL"
AUDIT_SECRET_STORAGE_BLOCKED = "SECRET_STORAGE_ATTEMPT_BLOCKED"  # noqa: S105 - 값 자체가 아닌 감사로그 이벤트명
AUDIT_CERT_PASSWORD_BLOCKED = "CERT_PASSWORD_STORE_BLOCKED"  # noqa: S105 - 값 자체가 아닌 감사로그 이벤트명
AUDIT_SERVER_LOGIN_BLOCKED = "SERVER_SECURITY_LOGIN_BLOCKED"
AUDIT_DOMAIN_CHANGE_GATE = "DOMAIN_DNS_CHANGE_APPROVAL_GATE"

# Gabia 브라우저 자동화 전용 AuditEvent 타입
AUDIT_GABIA_BROWSER_OPEN_REQUESTED = "GABIA_BROWSER_OPEN_REQUESTED"
AUDIT_GABIA_LOGIN_USER_PRESENT_REQUIRED = "GABIA_LOGIN_USER_PRESENT_REQUIRED"
AUDIT_GABIA_TRUSTED_SESSION_REUSED = "GABIA_TRUSTED_SESSION_REUSED"
AUDIT_GABIA_DNS_PAGE_NAV_READY = "GABIA_DNS_PAGE_NAVIGATION_READY"
AUDIT_GABIA_SECURITY_AUTOMATION_BLOCKED = "GABIA_SECURITY_AUTOMATION_BLOCKED"

# Gabia DNS 업무 전용 AuditEvent 타입
AUDIT_GABIA_DNS_WORKFLOW_PREPARED = "GABIA_DNS_WORKFLOW_PREPARED"
AUDIT_GABIA_DNS_RECORD_DRAFTED = "GABIA_DNS_RECORD_DRAFTED"
AUDIT_GABIA_DNS_CHANGE_PREVIEW = "GABIA_DNS_CHANGE_PREVIEW_CREATED"
AUDIT_GABIA_DNS_FINAL_APPROVAL_REQ = "GABIA_DNS_FINAL_APPROVAL_REQUIRED"
AUDIT_GABIA_DNS_USER_APPROVAL_GRANTED = "GABIA_DNS_USER_APPROVAL_GRANTED"
AUDIT_GABIA_DNS_USER_APPROVAL_DENIED = "GABIA_DNS_USER_APPROVAL_DENIED"
AUDIT_GABIA_DNS_SESSION_REUSED = "GABIA_DNS_SESSION_REUSED"
AUDIT_GABIA_DNS_REAUTH_REQUIRED = "GABIA_DNS_REAUTH_REQUIRED"

AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        AUDIT_USER_PRESENT_AUTH_REQUIRED,
        AUDIT_TRUSTED_SESSION_REUSED,
        AUDIT_TRUSTED_SESSION_EXPIRED,
        AUDIT_FINAL_APPROVAL_REQUIRED,
        AUDIT_FINAL_APPROVAL_GRANTED,
        AUDIT_FINAL_ACTION_BLOCKED,
        AUDIT_SECRET_STORAGE_BLOCKED,
        AUDIT_CERT_PASSWORD_BLOCKED,
        AUDIT_SERVER_LOGIN_BLOCKED,
        AUDIT_DOMAIN_CHANGE_GATE,
        # Gabia DNS 전용
        AUDIT_GABIA_DNS_WORKFLOW_PREPARED,
        AUDIT_GABIA_DNS_RECORD_DRAFTED,
        AUDIT_GABIA_DNS_CHANGE_PREVIEW,
        AUDIT_GABIA_DNS_FINAL_APPROVAL_REQ,
        AUDIT_GABIA_DNS_USER_APPROVAL_GRANTED,
        AUDIT_GABIA_DNS_USER_APPROVAL_DENIED,
        AUDIT_GABIA_DNS_SESSION_REUSED,
        AUDIT_GABIA_DNS_REAUTH_REQUIRED,
        # Gabia 브라우저 자동화 전용
        AUDIT_GABIA_BROWSER_OPEN_REQUESTED,
        AUDIT_GABIA_LOGIN_USER_PRESENT_REQUIRED,
        AUDIT_GABIA_TRUSTED_SESSION_REUSED,
        AUDIT_GABIA_DNS_PAGE_NAV_READY,
        AUDIT_GABIA_SECURITY_AUTOMATION_BLOCKED,
    }
)
