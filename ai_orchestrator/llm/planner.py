import logging

from ..core.models import ExecutionPlan, RiskAssessment, TaskRequest
from tools.gates.policy import evaluate_request, load_policy
from tools.gates.risk_classifier import classify_risk

logger = logging.getLogger(__name__)


def plan(req: TaskRequest) -> tuple[RiskAssessment, ExecutionPlan]:
    risk = classify_risk(req)
    logger.info(
        "위험도 분류 | task=%s | level=%s | requires_approval=%s", req.task_id, risk.risk_level, risk.requires_approval
    )
    policy = load_policy()
    execution_plan = evaluate_request(req, risk, policy)
    logger.info(
        "실행 계획 수립 | task=%s | allowed=%s | blocked=%s",
        req.task_id,
        execution_plan.allowed,
        execution_plan.blocked_reasons or None,
    )
    return risk, execution_plan
