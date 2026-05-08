"""금융 read-only 명세서 조회 시나리오."""
from ai_orchestrator.local_agent.universal_workflow_runner import run_workflow

def run(site_id: str = "generic_financial_site", task_id: str | None = None):
    return run_workflow(site_id, "financial_readonly_statement_download", task_id=task_id)
