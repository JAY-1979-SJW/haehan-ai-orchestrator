import json
import logging

from ai_orchestrator.openai_guard import assert_openai_allowed

from .config import OPENAI_API_KEY
from .models import ExecutionPlan, RiskAssessment, TaskRequest

logger = logging.getLogger(__name__)

_MOCK_MODE = not bool(OPENAI_API_KEY.strip())

if _MOCK_MODE:
    logger.warning("OPENAI_API_KEY 미설정 — MOCK 모드로 실행됩니다")


def _get_client():
    from openai import OpenAI

    return OpenAI(api_key=OPENAI_API_KEY)


def _call(system: str, user: str, fallback: str) -> str:
    assert_openai_allowed("openai_client.py:_call")
    if _MOCK_MODE:
        return fallback
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=200,
            timeout=10,
        )
        result = resp.choices[0].message.content.strip()
        logger.debug("OpenAI 호출 성공 | tokens=%s", resp.usage.total_tokens if resp.usage else "?")
        return result
    except Exception as e:
        logger.error("OpenAI 호출 실패: %s — fallback 반환", e)
        return fallback


def generate_task_summary(req: TaskRequest, risk: RiskAssessment) -> str:
    fallback = (
        f"[MOCK] 작업 '{req.action_type}' 대상 '{req.target}' | "
        f"위험도 {risk.risk_level.upper()}, 승인 필요: {risk.requires_approval}"
    )
    system = "당신은 IT 운영 AI 비서입니다. 작업 요청을 한 줄로 간결하게 요약합니다."
    user = (
        f"작업: {req.action_type}\n"
        f"대상: {req.target}\n"
        f"설명: {req.description}\n"
        f"위험도: {risk.risk_level}\n"
        f"한국어로 한 줄 요약해주세요."
    )
    return _call(system, user, fallback)


def generate_approval_reason(req: TaskRequest, plan: ExecutionPlan) -> str:
    fallback = (
        f"[MOCK] '{req.action_type}' 작업은 {plan.task_id} 계획에 따라 "
        f"승인이 필요합니다. 실행 전 검토 후 승인해 주세요."
    )
    system = "당신은 IT 운영 AI 비서입니다. 승인 요청 사유를 명확하게 작성합니다."
    user = (
        f"작업: {req.action_type}\n"
        f"대상: {req.target}\n"
        f"설명: {req.description}\n"
        f"차단 사유: {plan.blocked_reasons}\n"
        f"승인이 필요한 이유를 한국어 2문장으로 작성해주세요."
    )
    return _call(system, user, fallback)


def generate_plan_explanation(req: TaskRequest, plan: ExecutionPlan) -> str:
    fallback = (
        f"[MOCK] 실행 계획 설명 — 작업 {req.task_id}: "
        f"총 {len(plan.steps)}단계로 구성, "
        f"허용여부: {plan.allowed}, 승인필요: {plan.requires_approval}"
    )
    system = "당신은 IT 운영 AI 비서입니다. 실행 계획을 담당자가 이해하기 쉽게 설명합니다."
    user = f"작업ID: {req.task_id}\n단계: {chr(10).join(plan.steps)}\n실행 계획을 한국어 2문장으로 설명해주세요."
    return _call(system, user, fallback)


def generate_application_draft(grant: dict, company: dict) -> str:
    """정부 지원사업 신청서 초안 생성 (요약·작문). 미설정 시 MOCK 폴백.

    grant: {title, deadline/dday, portal_name, matched, url, raw}
    company: 회사 프로필 dict (사업자번호 등 민감정보는 프롬프트에 미포함)
    """
    title = grant.get("title", "")
    safe_company = {k: v for k, v in company.items() if k not in ("business_no", "_note")}
    fallback = (
        f"[초안(MOCK)] {title}\n\n"
        f"1. 신청 개요: {safe_company.get('company_name', '')}는 {safe_company.get('industry', '')} 역량으로 본 사업에 참여하고자 합니다.\n"
        f"2. 보유 역량: {', '.join(safe_company.get('core_competencies', []))}\n"
        f"3. 사업 연계성: {safe_company.get('strengths', '')}\n"
        f"4. 기대 효과: 공고 취지에 맞춘 실증·사업화 추진.\n"
        f"(OPENAI_API_KEY 설정 시 공고 맞춤 초안이 생성됩니다.)"
    )
    if _MOCK_MODE:
        return fallback
    try:
        client = _get_client()
        system = (
            "당신은 정부 지원사업 신청서 작성 전문가입니다. "
            "공고 취지와 회사 역량을 연결해 신청 개요·보유역량·사업연계성·추진계획·기대효과 "
            "구조의 한국어 초안을 작성합니다. 과장 없이 사실 기반으로, 빈칸은 [회사확인]으로 표시."
        )
        user = (
            f"[공고]\n제목: {title}\n출처: {grant.get('portal_name', '')}\n"
            f"마감: {grant.get('dday') or grant.get('deadline') or '미상'}\n"
            f"키워드: {', '.join(grant.get('matched', []))}\n원문: {grant.get('raw', '')[:400]}\n\n"
            f"[회사]\n{json.dumps(safe_company, ensure_ascii=False)}\n\n"
            f"위 회사가 이 공고에 제출할 신청서 초안을 작성하세요."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=900,
            timeout=30,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error("신청서 초안 생성 실패: %s — fallback 반환", e)
        return fallback


def is_mock_mode() -> bool:
    return _MOCK_MODE
