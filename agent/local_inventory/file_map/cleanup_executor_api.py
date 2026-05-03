"""cleanup_executor API 진입점: JSON 입력/출력."""

import json
import sys
from pathlib import Path
from dataclasses import asdict
from typing import Any

from agent.local_inventory.file_map.cleanup_executor import execute_moves, ExecutionResult
from agent.local_inventory.file_map.cleanup_preflight import run_preflight
from agent.local_inventory.file_map.cleanup_audit import (
    create_audit_records_from_execution,
    save_records,
)
from agent.local_inventory.file_map.cleanup_rollback import (
    create_manifest,
    save_manifest,
)


def main():
    """
    stdin에서 JSON을 읽고, cleanup_executor.execute_moves()를 호출한 후
    결과를 stdout에 JSON으로 출력.

    입력 JSON 형식:
    {
      "preflight_id": "...",
      "package_id": "...",
      "approval_token": "...",
      "user_confirmed_execution": true/false,
      "dry_run": true/false,
      "plans": [...],  (PreflightReport.items와 같은 구조)
      "base_target_dir": "..."
    }

    출력 JSON 형식:
    {
      "ok": true/false,
      "result": ExecutionResult dict,
      "error": "...(if ok=false)"
    }
    """
    try:
        input_data = json.load(sys.stdin)

        preflight_id = input_data.get("preflight_id")
        package_id = input_data.get("package_id")
        approval_token = input_data.get("approval_token")
        user_confirmed = input_data.get("user_confirmed_execution", False)
        dry_run = input_data.get("dry_run", True)
        plans = input_data.get("plans", [])
        base_target_dir = input_data.get("base_target_dir")
        include_sensitive = input_data.get("include_sensitive", False)

        if not plans or not base_target_dir:
            sys.stdout.write(
                json.dumps(
                    {
                        "ok": False,
                        "error": "plans와 base_target_dir이 필요합니다",
                    }
                )
            )
            return

        # 사전검사 실행
        preflight_report = run_preflight(plans, base_target_dir, include_sensitive)

        # 파일 이동 실행
        execution_result = execute_moves(
            preflight_report,
            package_id,
            approval_token,
            user_confirmed,
            dry_run=dry_run,
        )

        # 감사로그 저장 (dry_run도 기록)
        execution_result_dict = asdict(execution_result)
        audit_records = create_audit_records_from_execution(
            execution_result.run_id,
            execution_result.package_id,
            execution_result_dict,
        )
        save_records(audit_records)

        # 롤백 매니페스트 저장 (성공 항목만)
        if execution_result.success_count > 0:
            rollback_manifest = create_manifest(
                execution_result.run_id,
                execution_result.package_id,
                execution_result_dict,
            )
            save_manifest(rollback_manifest)

        # 결과 반환
        sys.stdout.write(
            json.dumps(
                {
                    "ok": True,
                    "result": execution_result_dict,
                }
            )
        )

    except ValueError as e:
        # 검증 실패 (승인 검증 등)
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "error": str(e),
                }
            )
        )
    except Exception as e:
        # 기타 오류
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "error": f"실행 실패: {str(e)}",
                }
            )
        )


if __name__ == "__main__":
    main()
