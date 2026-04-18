from .models import ExecutionPlan

# 이번 단계는 드라이런 전용. 실제 시스템 변경 없음.

def execute(plan: ExecutionPlan) -> str:
    if not plan.allowed:
        return f"BLOCKED: {'; '.join(plan.blocked_reasons)}"
    if plan.requires_approval:
        return "PENDING_APPROVAL"
    return "DRY_RUN_ONLY"
