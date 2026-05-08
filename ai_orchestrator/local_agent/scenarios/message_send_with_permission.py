"""메시지 발송 (권한 필요) 시나리오."""
from ai_orchestrator.local_agent.universal_workflow_runner import run_single_action

def run(site_id: str, domain: str, permission_id: str, content: str, task_id: str | None = None):
    return run_single_action(site_id, "send_message", domain=domain,
                              permission_id=permission_id, content=content, task_id=task_id)
