"""정부 사이트 read-only 조회 시나리오."""
from ai_orchestrator.local_agent.universal_workflow_runner import run_workflow

def run(site_id: str = "g2b_public", task_id: str | None = None):
    return run_workflow(site_id, "government_readonly_status_check", task_id=task_id)
