"""콘텐츠 리서치 → 블로그 발행 시나리오."""
from ai_orchestrator.local_agent.universal_workflow_runner import run_workflow

def run(permission_map: dict | None = None, task_id: str | None = None):
    return run_workflow("naver_blog", "blog_publish_with_permission",
                        permission_map=permission_map, task_id=task_id)
