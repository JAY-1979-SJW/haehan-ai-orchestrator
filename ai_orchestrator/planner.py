from .models import TaskRequest, RiskAssessment, ExecutionPlan
from .risk_classifier import classify_risk
from .policy import load_policy, evaluate_request


def plan(req: TaskRequest) -> tuple[RiskAssessment, ExecutionPlan]:
    risk = classify_risk(req)
    policy = load_policy()
    execution_plan = evaluate_request(req, risk, policy)
    return risk, execution_plan
