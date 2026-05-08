"""문서 다운로드 시나리오."""
from ai_orchestrator.local_agent.universal_workflow_runner import run_workflow

def run(site_id: str = "g2b_public", task_id: str | None = None):
    return run_workflow(site_id, "download_documents", task_id=task_id)
