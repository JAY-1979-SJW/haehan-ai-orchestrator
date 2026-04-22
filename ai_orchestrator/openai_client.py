import logging

from .models import TaskRequest, RiskAssessment, ExecutionPlan
from .config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_MOCK_MODE = not bool(OPENAI_API_KEY.strip())

if _MOCK_MODE:
    logger.warning("OPENAI_API_KEY 미설정 — MOCK 모드로 실행됩니다")


def _get_client():
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)


def _call(system: str, user: str, fallback: str) -> str:
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
    user = (
        f"작업ID: {req.task_id}\n"
        f"단계: {chr(10).join(plan.steps)}\n"
        f"실행 계획을 한국어 2문장으로 설명해주세요."
    )
    return _call(system, user, fallback)


def is_mock_mode() -> bool:
    return _MOCK_MODE
