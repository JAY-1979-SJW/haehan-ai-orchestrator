"""카페 탐색 → 블로그 초안 시나리오."""
from ai_orchestrator.local_agent.universal_workflow_runner import run_workflow

def run(permission_map: dict | None = None, task_id: str | None = None):
    return run_workflow("naver_cafe", "cafe_to_blog_draft",
                        permission_map=permission_map, task_id=task_id)
