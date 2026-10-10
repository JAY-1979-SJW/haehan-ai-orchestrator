"""앱 런타임 텍스트 생성 폴백 — 유료 AI API 호출 없음(2026-09-24 OpenAI 삭제).

과거에는 OPENAI_API_KEY 가 있으면 GPT를 호출했다. 이제 앱 런타임은 항상 결정론적
MOCK/템플릿 문자열을 반환한다. 실제 문구 작성은 Claude Code 가 MCP로 앱에 붙어 수행한다.
"""

import logging

from ..core.models import ExecutionPlan, RiskAssessment, TaskRequest

logger = logging.getLogger(__name__)

_MOCK_MODE = True


def generate_task_summary(req: TaskRequest, risk: RiskAssessment) -> str:
    return (
        f"[MOCK] 작업 '{req.action_type}' 대상 '{req.target}' | "
        f"위험도 {risk.risk_level.upper()}, 승인 필요: {risk.requires_approval}"
    )


def generate_approval_reason(req: TaskRequest, plan: ExecutionPlan) -> str:
    return (
        f"[MOCK] '{req.action_type}' 작업은 {plan.task_id} 계획에 따라 "
        f"승인이 필요합니다. 실행 전 검토 후 승인해 주세요."
    )


def generate_application_draft(grant: dict, company: dict) -> str:
    """정부 지원사업 신청서 초안 자리표시(템플릿). 실제 맞춤 초안은 Claude Code가 작성.

    grant: {title, deadline/dday, portal_name, matched, url, raw}
    company: 회사 프로필 dict (사업자번호 등 민감정보는 프롬프트에 미포함)
    """
    title = grant.get("title", "")
    safe_company = {k: v for k, v in company.items() if k not in ("business_no", "_note")}
    return (
        f"[초안(MOCK)] {title}\n\n"
        f"1. 신청 개요: {safe_company.get('company_name', '')}는 {safe_company.get('industry', '')} 역량으로 본 사업에 참여하고자 합니다.\n"
        f"2. 보유 역량: {', '.join(safe_company.get('core_competencies', []))}\n"
        f"3. 사업 연계성: {safe_company.get('strengths', '')}\n"
        f"4. 기대 효과: 공고 취지에 맞춘 실증·사업화 추진.\n"
        f"(맞춤 초안은 Claude Code가 MCP로 작성합니다.)"
    )


def is_mock_mode() -> bool:
    return _MOCK_MODE
