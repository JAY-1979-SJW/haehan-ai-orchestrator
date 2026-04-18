from ai_orchestrator.models import TaskRequest
from ai_orchestrator.planner import plan
from ai_orchestrator.executor import execute


SAMPLE_REQUESTS = [
    TaskRequest(
        task_id="T001",
        source="manual",
        action_type="read_file",
        target="/var/log/app.log",
        description="서버 로그 파일 읽기",
        requested_by="admin",
    ),
    TaskRequest(
        task_id="T002",
        source="pc",
        action_type="summarize_text",
        target="/home/deploy/app/docs/report.txt",
        description="특정 문서 요약 요청",
        requested_by="admin",
    ),
    TaskRequest(
        task_id="T003",
        source="server",
        action_type="edit_config",
        target="/var/www/haehan/config.yaml",
        description="서비스 설정 파일 수정",
        payload={"key": "timeout", "value": 30},
        requested_by="deploy-bot",
    ),
    TaskRequest(
        task_id="T004",
        source="server",
        action_type="restart_service",
        target="haehan-api",
        description="API 서버 재시작",
        payload={"reason": "memory leak fix"},
        requested_by="deploy-bot",
    ),
    TaskRequest(
        task_id="T005",
        source="manual",
        action_type="delete_file",
        target="/var/www/haehan/old_backup.tar.gz",
        description="오래된 백업 파일 삭제",
        requested_by="admin",
    ),
]


def main():
    print("=" * 60)
    print("  승인형 AI 오케스트레이터 — 드라이런 결과")
    print("=" * 60)

    for req in SAMPLE_REQUESTS:
        risk, plan_result = plan(req)
        result = execute(plan_result)

        print(f"\n[{req.task_id}] {req.description}")
        print(f"  action_type      : {req.action_type}")
        print(f"  risk_level       : {risk.risk_level.upper()}")
        print(f"  requires_approval: {plan_result.requires_approval}")
        print(f"  allowed          : {plan_result.allowed}")
        print(f"  executor_result  : {result}")
        if plan_result.blocked_reasons:
            print(f"  blocked_reasons  :")
            for r in plan_result.blocked_reasons:
                print(f"    - {r}")
        print(f"  steps            :")
        for s in plan_result.steps:
            print(f"    {s}")
        print("-" * 60)


if __name__ == "__main__":
    main()
